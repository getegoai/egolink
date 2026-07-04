"""Minimal Ego Link P0 HTTP message hub.

The first server path intentionally uses only the Python standard library so it
can run on a clean VPS before we introduce deployment complexity.
"""

from __future__ import annotations

import argparse
import base64
import binascii
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import threading
from typing import Any
from urllib.parse import unquote, urlparse

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pc_simulator import protocol


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = REPO_ROOT / "server" / "runtime" / "message_hub.db"
KEY_RELEASE_DIR = REPO_ROOT / "docs" / "current" / "key_releases"
DEFAULT_PRODUCT_DEMO_REPORTS = REPO_ROOT / "reports" / "product_demo"
MAX_BODY_BYTES = 1_000_000
RAW_FRAME_PROFILE = "raw-frame.p0.v1"
EALE_P0_GENERATOR_NAME = "EALE-P0"
EALE_P0_GENERATOR_VERSION = "0.1.0-alg001"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MessageHubError(Exception):
    def __init__(self, code: str, message: str, *, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


class MessageHubStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._raw_post_fail_once_seen: set[str] = set()
        self._raw_post_fail_once_lock = threading.Lock()
        self._init_schema()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def connection(self) -> Any:
        db = self.connect()
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def _init_schema(self) -> None:
        with self.connection() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS devices (
                    device_id TEXT PRIMARY KEY,
                    fw_version TEXT,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    last_message_type TEXT,
                    last_seq INTEGER,
                    last_status_json TEXT,
                    latest_telemetry_json TEXT,
                    last_error_json TEXT
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    message_type TEXT NOT NULL,
                    event_type TEXT,
                    seq INTEGER,
                    ts TEXT,
                    server_received_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_messages_device_time
                ON messages (device_id, id DESC);

                CREATE TABLE IF NOT EXISTS commands (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cmd_id TEXT NOT NULL UNIQUE,
                    device_id TEXT NOT NULL,
                    cmd TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    ack_at TEXT,
                    payload_json TEXT NOT NULL,
                    ack_json TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_commands_device_status
                ON commands (device_id, status, id);

                CREATE TABLE IF NOT EXISTS errors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    error_code TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    server_received_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS test_runs (
                    test_run_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS raw_frames (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    frame_id TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    frame_type TEXT,
                    seq INTEGER,
                    test_run_id TEXT,
                    fw_version TEXT,
                    content_type TEXT,
                    payload_len INTEGER,
                    payload_crc32 TEXT,
                    raw_payload_sha256 TEXT NOT NULL,
                    raw_payload_b64 TEXT NOT NULL,
                    server_received_at TEXT NOT NULL,
                    parse_status TEXT NOT NULL,
                    parse_error_code TEXT,
                    parse_reason TEXT,
                    derived_message_type TEXT,
                    derived_message_json TEXT,
                    record_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_raw_frames_device_time
                ON raw_frames (device_id, id DESC);

                CREATE INDEX IF NOT EXISTS idx_raw_frames_test_run
                ON raw_frames (test_run_id, id);

                CREATE TABLE IF NOT EXISTS location_memory (
                    device_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    radius_m REAL,
                    confidence REAL,
                    source_json TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    belief_updated_at TEXT,
                    last_test_run_id TEXT,
                    memory_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_location_memory_updated
                ON location_memory (updated_at DESC);
                """
            )

    def register_device(self, payload: dict[str, Any]) -> dict[str, Any]:
        device_id = require_text(payload, "device_id")
        now = utc_now()
        fw_version = str(payload.get("fw_version") or "unknown")
        with self.connection() as db:
            existing = db.execute(
                "SELECT device_id, first_seen_at FROM devices WHERE device_id = ?",
                (device_id,),
            ).fetchone()
            first_seen_at = existing["first_seen_at"] if existing else now
            db.execute(
                """
                INSERT INTO devices (
                    device_id, fw_version, first_seen_at, last_seen_at,
                    last_message_type, last_seq, last_status_json,
                    latest_telemetry_json, last_error_json
                )
                VALUES (?, ?, ?, ?, 'register', NULL, NULL, NULL, NULL)
                ON CONFLICT(device_id) DO UPDATE SET
                    fw_version = excluded.fw_version,
                    last_seen_at = excluded.last_seen_at,
                    last_message_type = 'register'
                """,
                (device_id, fw_version, first_seen_at, now),
            )
        return self.get_device(device_id)

    def ingest(self, device_id: str, endpoint_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        message = normalize_message(self, device_id, endpoint_type, payload)
        server_received_at = utc_now()
        message["server_received_at"] = server_received_at
        message_json = dumps(message)
        message_type = str(message["message_type"])
        event_type = str(message.get("event_type") or "")
        seq = message.get("seq")
        ts = str(message.get("ts") or "")
        fw_version = str(message.get("fw_version") or "unknown")

        with self.connection() as db:
            existing = db.execute(
                "SELECT first_seen_at FROM devices WHERE device_id = ?",
                (device_id,),
            ).fetchone()
            first_seen_at = existing["first_seen_at"] if existing else server_received_at
            db.execute(
                """
                INSERT INTO devices (
                    device_id, fw_version, first_seen_at, last_seen_at,
                    last_message_type, last_seq, last_status_json,
                    latest_telemetry_json, last_error_json
                )
                VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, NULL)
                ON CONFLICT(device_id) DO UPDATE SET
                    fw_version = COALESCE(NULLIF(excluded.fw_version, 'unknown'), devices.fw_version),
                    last_seen_at = excluded.last_seen_at,
                    last_message_type = excluded.last_message_type,
                    last_seq = excluded.last_seq
                """,
                (device_id, fw_version, first_seen_at, server_received_at, message_type, seq),
            )
            db.execute(
                """
                INSERT INTO messages (
                    device_id, message_type, event_type, seq, ts,
                    server_received_at, payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (device_id, message_type, event_type, seq, ts, server_received_at, message_json),
            )
            if message_type == "status":
                db.execute(
                    "UPDATE devices SET last_status_json = ? WHERE device_id = ?",
                    (message_json, device_id),
                )
            elif message_type == "event":
                db.execute(
                    "UPDATE devices SET latest_telemetry_json = ? WHERE device_id = ?",
                    (message_json, device_id),
                )
                if event_type in {"location_report", "location_observation"}:
                    self._record_location_memory(db, device_id, message, server_received_at)
            elif message_type == "ack":
                self._record_ack(db, device_id, message, server_received_at, message_json)
            elif message_type == "error":
                self._record_error(db, device_id, message, server_received_at, message_json)
        return message

    def _record_ack(
        self,
        db: sqlite3.Connection,
        device_id: str,
        message: dict[str, Any],
        server_received_at: str,
        message_json: str,
    ) -> None:
        cmd_id = require_text(message, "cmd_id")
        status = require_text(message, "status")
        db.execute(
            """
            UPDATE commands
            SET status = ?, updated_at = ?, ack_at = ?, ack_json = ?
            WHERE device_id = ? AND cmd_id = ?
            """,
            (status, server_received_at, server_received_at, message_json, device_id, cmd_id),
        )

    def _record_error(
        self,
        db: sqlite3.Connection,
        device_id: str,
        message: dict[str, Any],
        server_received_at: str,
        message_json: str,
    ) -> None:
        error_code = require_text(message, "error_code")
        severity = require_text(message, "severity")
        db.execute(
            """
            INSERT INTO errors (device_id, error_code, severity, server_received_at, payload_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (device_id, error_code, severity, server_received_at, message_json),
        )
        db.execute(
            "UPDATE devices SET last_error_json = ? WHERE device_id = ?",
            (message_json, device_id),
        )

    def _record_location_memory(
        self,
        db: sqlite3.Connection,
        device_id: str,
        message: dict[str, Any],
        server_received_at: str,
    ) -> None:
        existing = self._location_memory(db, device_id)
        memory = build_location_memory(device_id, message, server_received_at, existing)
        if not memory:
            return
        db.execute(
            """
            INSERT INTO location_memory (
                device_id, state, radius_m, confidence, source_json, reason,
                updated_at, belief_updated_at, last_test_run_id, memory_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(device_id) DO UPDATE SET
                state = excluded.state,
                radius_m = excluded.radius_m,
                confidence = excluded.confidence,
                source_json = excluded.source_json,
                reason = excluded.reason,
                updated_at = excluded.updated_at,
                belief_updated_at = excluded.belief_updated_at,
                last_test_run_id = excluded.last_test_run_id,
                memory_json = excluded.memory_json
            """,
            (
                device_id,
                str(memory.get("state") or "Unknown"),
                memory.get("radius_m"),
                memory.get("confidence"),
                dumps(memory.get("source") if isinstance(memory.get("source"), list) else []),
                str(memory.get("reason") or "no_location_memory"),
                str(memory.get("updated_at") or server_received_at),
                memory.get("belief_updated_at"),
                memory.get("last_test_run_id"),
                dumps(memory),
            ),
        )

    def next_seq(self, device_id: str) -> int:
        with self.connection() as db:
            row = db.execute(
                "SELECT COALESCE(MAX(seq), 0) AS max_seq FROM messages WHERE device_id = ?",
                (device_id,),
            ).fetchone()
        return int(row["max_seq"]) + 1

    def create_command(self, device_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        cmd = str(payload.get("cmd") or payload.get("type") or "")
        if not cmd:
            raise MessageHubError("missing_command", "command must include cmd")
        now = utc_now()
        with self.connection() as db:
            next_id = int(db.execute("SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM commands").fetchone()["next_id"])
        cmd_id = str(payload.get("cmd_id") or f"cmd-{next_id:06d}")
        command = dict(payload)
        command.update(
            {
                "protocol_version": protocol.PROTOCOL_VERSION,
                "message_type": "command",
                "device_id": device_id,
                "cmd_id": cmd_id,
                "cmd": cmd,
                "created_at": str(payload.get("created_at") or now),
            }
        )
        command_json = dumps(command)
        with self.connection() as db:
            db.execute(
                """
                INSERT INTO commands (
                    cmd_id, device_id, cmd, status, created_at, updated_at,
                    payload_json, ack_json
                )
                VALUES (?, ?, ?, 'pending', ?, ?, ?, NULL)
                """,
                (cmd_id, device_id, cmd, command["created_at"], now, command_json),
            )
        return command_with_status(command, "pending")

    def poll_commands(self, device_id: str) -> list[dict[str, Any]]:
        return self.list_commands(device_id, statuses={"pending"})

    def list_commands(self, device_id: str, statuses: set[str] | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM commands WHERE device_id = ?"
        args: list[Any] = [device_id]
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            sql += f" AND status IN ({placeholders})"
            args.extend(sorted(statuses))
        sql += " ORDER BY id DESC"
        with self.connection() as db:
            rows = db.execute(sql, args).fetchall()
        return [command_row(row) for row in rows]

    def list_devices(self) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute("SELECT * FROM devices ORDER BY last_seen_at DESC").fetchall()
            devices = [self._device_with_derived_state(db, row) for row in rows]
        return devices

    def get_device(self, device_id: str) -> dict[str, Any]:
        with self.connection() as db:
            row = db.execute("SELECT * FROM devices WHERE device_id = ?", (device_id,)).fetchone()
            if row is None:
                raise MessageHubError("device_not_found", f"unknown device: {device_id}", status=404)
            device = self._device_with_derived_state(db, row)
        return device

    def _device_with_derived_state(self, db: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
        device = device_row(row)
        device["latest_location"] = self._latest_location_event(db, device["device_id"])
        device["latest_location_observation"] = self._latest_event(db, device["device_id"], "location_observation")
        device["location_memory"] = self._location_memory(db, device["device_id"])
        device["last_command"] = self._latest_command(db, device["device_id"])
        device["observability"] = build_observability(device, device["last_command"])
        device["d1_link"] = build_d1_link_summary(device)
        return device

    def _location_memory(self, db: sqlite3.Connection, device_id: str) -> dict[str, Any] | None:
        row = db.execute(
            "SELECT memory_json FROM location_memory WHERE device_id = ?",
            (device_id,),
        ).fetchone()
        return json.loads(row["memory_json"]) if row else None

    def _latest_event(self, db: sqlite3.Connection, device_id: str, event_type: str) -> dict[str, Any] | None:
        row = db.execute(
            """
            SELECT payload_json FROM messages
            WHERE device_id = ?
              AND message_type = 'event'
              AND event_type = ?
            ORDER BY id DESC LIMIT 1
            """,
            (device_id, event_type),
        ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def _latest_location_event(self, db: sqlite3.Connection, device_id: str) -> dict[str, Any] | None:
        row = db.execute(
            """
            SELECT payload_json FROM messages
            WHERE device_id = ?
              AND message_type = 'event'
              AND event_type IN ('location_observation', 'location_report')
            ORDER BY id DESC LIMIT 1
            """,
            (device_id,),
        ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def _latest_command(self, db: sqlite3.Connection, device_id: str) -> dict[str, Any] | None:
        row = db.execute(
            """
            SELECT * FROM commands
            WHERE device_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            (device_id,),
        ).fetchone()
        return command_row(row) if row else None

    def latest_telemetry(self, device_id: str) -> dict[str, Any] | None:
        with self.connection() as db:
            row = db.execute(
                """
                SELECT payload_json FROM messages
                WHERE device_id = ? AND message_type IN ('status', 'event', 'error')
                ORDER BY id DESC LIMIT 1
                """,
                (device_id,),
            ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def telemetry_history(self, device_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute(
                """
                SELECT payload_json FROM messages
                WHERE device_id = ? AND message_type IN ('status', 'event', 'error', 'ack')
                ORDER BY id DESC LIMIT ?
                """,
                (device_id, limit),
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def recent_messages(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute("SELECT payload_json FROM messages ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def recent_commands(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute("SELECT * FROM commands ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [command_row(row) for row in rows]

    def ingest_raw_frame(
        self,
        device_id: str,
        raw_body: bytes,
        *,
        direction: str = "uplink",
        expected_frame_type: str | None = None,
        expected_cmd_id: str | None = None,
    ) -> dict[str, Any]:
        server_received_at = utc_now()
        raw_id, initial = self._insert_raw_frame_initial(device_id, raw_body, direction, server_received_at)
        record = parse_raw_frame_record(
            initial,
            raw_body,
            expected_frame_type=expected_frame_type,
            expected_cmd_id=expected_cmd_id,
        )
        derived_message = as_dict(record["parse_result"].get("derived_message"))
        endpoint = derived_endpoint(derived_message.get("message_type"))
        if record["parse_result"]["status"] == "ok" and endpoint:
            try:
                self.ingest(device_id, endpoint, derived_message)
            except MessageHubError as error:
                record["parse_result"].update(
                    {
                        "status": "malformed",
                        "error_code": "DERIVED_MESSAGE_REJECTED",
                        "reason": str(error),
                    }
                )
        self._update_raw_frame(raw_id, record)
        return record

    def claim_raw_post_fail_once(self, device_id: str, raw_body: bytes) -> dict[str, Any] | None:
        probe = parse_raw_frame_probe(device_id, raw_body)
        kv_payload = as_dict(probe.get("kv_payload"))
        if parse_bool_or_text(kv_payload.get("test-inject-raw-post-fail-once")) is not True:
            return None
        frame_id = str(probe.get("frame_id") or "unknown")
        key = f"{device_id}|{frame_id}|{probe['raw_payload_sha256']}"
        with self._raw_post_fail_once_lock:
            if key in self._raw_post_fail_once_seen:
                return None
            self._raw_post_fail_once_seen.add(key)
        return {"key": key, "frame_id": frame_id, "test_run_id": probe.get("test_run_id")}

    def ingest_raw_frame_injected_failure(
        self,
        device_id: str,
        raw_body: bytes,
        *,
        injection: dict[str, Any],
        direction: str = "uplink",
        expected_frame_type: str | None = None,
        expected_cmd_id: str | None = None,
    ) -> dict[str, Any]:
        server_received_at = utc_now()
        raw_id, initial = self._insert_raw_frame_initial(device_id, raw_body, direction, server_received_at)
        record = parse_raw_frame_record(
            initial,
            raw_body,
            expected_frame_type=expected_frame_type,
            expected_cmd_id=expected_cmd_id,
        )
        original_parse = as_dict(record.get("parse_result"))
        record["parse_result"] = {
            "status": "injected_failure",
            "error_code": "RAW_POST_FAIL_ONCE_INJECTED",
            "reason": "test requested fail-once raw POST injection; raw frame retained without deriving message",
            "derived_message_type": "unknown",
            "suppressed_derived_message_type": original_parse.get("derived_message_type"),
        }
        record["injection"] = {
            "name": "raw_post_fail_once",
            "status": "injected_failure",
            "key": injection.get("key"),
        }
        self._update_raw_frame(raw_id, record)
        return record

    def _insert_raw_frame_initial(
        self,
        device_id: str,
        raw_body: bytes,
        direction: str,
        server_received_at: str,
    ) -> tuple[int, dict[str, Any]]:
        record = initial_raw_frame_record(device_id, raw_body, direction, server_received_at)
        with self.connection() as db:
            cursor = db.execute(
                """
                INSERT INTO raw_frames (
                    frame_id, device_id, direction, frame_type, seq, test_run_id,
                    fw_version, content_type, payload_len, payload_crc32,
                    raw_payload_sha256, raw_payload_b64, server_received_at,
                    parse_status, parse_error_code, parse_reason,
                    derived_message_type, derived_message_json, record_json
                )
                VALUES (?, ?, ?, NULL, NULL, NULL, NULL, NULL, NULL, NULL, ?, ?, ?, ?, NULL, NULL, NULL, NULL, ?)
                """,
                (
                    record["frame_id"],
                    device_id,
                    direction,
                    record["raw_payload"]["sha256"],
                    record["raw_payload"]["data"],
                    server_received_at,
                    record["parse_result"]["status"],
                    dumps(record),
                ),
            )
            raw_id = int(cursor.lastrowid)
        record["raw_frame_row_id"] = raw_id
        return raw_id, record

    def _update_raw_frame(self, raw_id: int, record: dict[str, Any]) -> None:
        framing = as_dict(record.get("framing"))
        parse_result = as_dict(record.get("parse_result"))
        derived_message = as_dict(parse_result.get("derived_message"))
        with self.connection() as db:
            db.execute(
                """
                UPDATE raw_frames
                SET frame_id = ?,
                    frame_type = ?,
                    seq = ?,
                    test_run_id = ?,
                    fw_version = ?,
                    content_type = ?,
                    payload_len = ?,
                    payload_crc32 = ?,
                    parse_status = ?,
                    parse_error_code = ?,
                    parse_reason = ?,
                    derived_message_type = ?,
                    derived_message_json = ?,
                    record_json = ?
                WHERE id = ?
                """,
                (
                    record["frame_id"],
                    framing.get("frame_type"),
                    record.get("seq"),
                    record.get("test_run_id"),
                    record.get("fw_version"),
                    framing.get("content_type"),
                    framing.get("payload_len"),
                    framing.get("payload_crc32"),
                    parse_result.get("status"),
                    parse_result.get("error_code"),
                    parse_result.get("reason"),
                    parse_result.get("derived_message_type"),
                    dumps(derived_message) if derived_message else None,
                    dumps(record),
                    raw_id,
                ),
            )

    def list_raw_frames(self, device_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute(
                """
                SELECT record_json FROM raw_frames
                WHERE device_id = ?
                ORDER BY id DESC LIMIT ?
                """,
                (device_id, limit),
            ).fetchall()
        return [redact_raw_frame_record(json.loads(row["record_json"])) for row in rows]

    def recent_raw_frames(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute("SELECT record_json FROM raw_frames ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [redact_raw_frame_record(json.loads(row["record_json"])) for row in rows]

    def poll_commands_raw(self, device_id: str) -> tuple[bytes, dict[str, Any] | None]:
        pending = self.poll_commands(device_id)
        if not pending:
            return build_raw_command_frame(device_id, None), None
        command = pending[0]
        frame = build_raw_command_frame(device_id, command)
        record = self.ingest_raw_frame(
            device_id,
            frame,
            direction="downlink",
            expected_frame_type="command",
            expected_cmd_id=str(command["cmd_id"]),
        )
        return frame, record

    def create_test_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        test_run_id = str(payload.get("test_run_id") or f"test-run-{utc_now().replace(':', '').replace('+', 'Z')}")
        now = utc_now()
        metadata = dict(payload)
        metadata["test_run_id"] = test_run_id
        metadata.setdefault("created_at", now)
        metadata.setdefault("status", "active")
        with self.connection() as db:
            db.execute(
                """
                INSERT INTO test_runs (test_run_id, created_at, status, metadata_json)
                VALUES (?, ?, ?, ?)
                """,
                (test_run_id, metadata["created_at"], metadata["status"], dumps(metadata)),
            )
        return metadata

    def list_test_runs(self) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute("SELECT metadata_json FROM test_runs ORDER BY created_at DESC").fetchall()
        return [json.loads(row["metadata_json"]) for row in rows]

    def export_test_run(self, test_run_id: str) -> dict[str, Any]:
        with self.connection() as db:
            run = db.execute(
                "SELECT metadata_json FROM test_runs WHERE test_run_id = ?",
                (test_run_id,),
            ).fetchone()
            messages = db.execute(
                """
                SELECT payload_json FROM messages
                WHERE payload_json LIKE ?
                ORDER BY id
                """,
                (f'%"{test_run_id}"%',),
            ).fetchall()
            commands = db.execute(
                """
                SELECT * FROM commands
                WHERE payload_json LIKE ? OR ack_json LIKE ?
                ORDER BY id
                """,
                (f'%"{test_run_id}"%', f'%"{test_run_id}"%'),
            ).fetchall()
            raw_frames = db.execute(
                """
                SELECT record_json FROM raw_frames
                WHERE test_run_id = ? OR record_json LIKE ?
                ORDER BY id
                """,
                (test_run_id, f'%"{test_run_id}"%'),
            ).fetchall()
        if run is None:
            raise MessageHubError("test_run_not_found", f"unknown test run: {test_run_id}", status=404)
        test_run = json.loads(run["metadata_json"])
        message_list = [json.loads(row["payload_json"]) for row in messages]
        command_list = [command_row(row) for row in commands]
        raw_frame_list = [redact_raw_frame_record(json.loads(row["record_json"])) for row in raw_frames]
        observability_summary = summarize_test_run_observability(message_list, command_list, raw_frame_list)
        return {
            "test_run": test_run,
            "messages": message_list,
            "commands": command_list,
            "raw_frames": raw_frame_list,
            "observability_summary": observability_summary,
            "run_context": build_run_context(
                messages=message_list,
                commands=command_list,
                raw_frames=raw_frame_list,
                test_run=test_run,
                latest_observability=as_dict(observability_summary.get("latest_observability")),
            ),
        }


def normalize_message(
    store: MessageHubStore,
    device_id: str,
    endpoint_type: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    message = dict(payload)
    message["protocol_version"] = str(message.get("protocol_version") or protocol.PROTOCOL_VERSION)
    message["device_id"] = str(message.get("device_id") or device_id)
    if message["device_id"] != device_id:
        raise MessageHubError("device_id_mismatch", "path device_id and payload device_id differ", status=409)
    message.setdefault("ts", utc_now())
    message.setdefault("seq", store.next_seq(device_id))

    if endpoint_type == "heartbeat":
        message["message_type"] = "status"
        message.setdefault("battery", None)
        message.setdefault("link_type", "unknown")
        message.setdefault("guard_mode", "unknown")
        message.setdefault("queue_size", 0)
        protocol.require_fields(message, ["protocol_version", "device_id", "ts", "seq", "message_type"])
        return message

    if endpoint_type == "telemetry":
        message["message_type"] = "event"
        message.setdefault("event_type", "telemetry")
        message.setdefault("priority", "normal")
        protocol.require_fields(
            message,
            ["protocol_version", "device_id", "ts", "seq", "message_type", "event_type", "priority"],
        )
        return message

    if endpoint_type == "ack":
        message["message_type"] = "ack"
        protocol.require_fields(
            message,
            ["protocol_version", "device_id", "ts", "seq", "message_type", "cmd_id", "status"],
        )
        return message

    if endpoint_type == "error":
        message["message_type"] = "error"
        payload_obj = message.get("payload")
        if isinstance(payload_obj, dict):
            for field in ("error_code", "severity", "message", "recoverable"):
                if field in payload_obj and field not in message:
                    message[field] = payload_obj[field]
        protocol.require_fields(
            message,
            ["protocol_version", "device_id", "ts", "seq", "message_type", "error_code", "severity"],
        )
        return message

    raise MessageHubError("unknown_endpoint_type", f"unknown endpoint type: {endpoint_type}", status=500)


def make_handler(
    store: MessageHubStore,
    *,
    token: str | None = None,
    product_demo_root: Path = DEFAULT_PRODUCT_DEMO_REPORTS,
) -> type[BaseHTTPRequestHandler]:
    class MessageHubHandler(BaseHTTPRequestHandler):
        server_version = "EgoLinkMessageHub/0.1"

        def do_GET(self) -> None:
            try:
                self.route_get()
            except MessageHubError as error:
                self.respond_error(error)
            except Exception as error:  # pragma: no cover - defensive handler boundary.
                self.respond_error(MessageHubError("server_error", str(error), status=500))

        def do_POST(self) -> None:
            try:
                if not authorized(self.headers.get("Authorization"), token):
                    raise MessageHubError("unauthorized", "missing or invalid bearer token", status=401)
                self.route_post()
            except MessageHubError as error:
                self.respond_error(error)
            except json.JSONDecodeError:
                self.respond_error(MessageHubError("invalid_json", "request body is not valid JSON"))
            except Exception as error:  # pragma: no cover - defensive handler boundary.
                self.respond_error(MessageHubError("server_error", str(error), status=500))

        def route_get(self) -> None:
            path = urlparse(self.path).path
            segments = split_path(path)
            if path == "/":
                self.respond_html(render_dashboard())
                return
            if path == "/health":
                self.respond_json({"ok": True, "service": "egolink-message-hub", "time": utc_now()})
                return
            if segments and segments[0] == "api" and not authorized(self.headers.get("Authorization"), token):
                raise MessageHubError("unauthorized", "missing or invalid bearer token", status=401)
            if path == "/api/state":
                devices = store.list_devices()
                messages = store.recent_messages(20)
                commands = store.recent_commands(20)
                raw_frames = store.recent_raw_frames(20)
                product_demo = load_latest_product_demo_report(product_demo_root)
                self.respond_json(
                    {
                        "devices": devices,
                        "messages": messages,
                        "commands": commands,
                        "raw_frames": raw_frames,
                        "product_demo": product_demo,
                        "current_run": build_run_context(
                            messages=messages,
                            commands=commands,
                            raw_frames=raw_frames,
                            devices=devices,
                            test_runs=store.list_test_runs(),
                        ),
                    }
                )
                return
            if segments == ["api", "v1", "devices"]:
                self.respond_json({"devices": store.list_devices()})
                return
            if len(segments) == 4 and segments[:3] == ["api", "v1", "devices"]:
                self.respond_json({"device": store.get_device(segments[3])})
                return
            if len(segments) == 6 and segments[:3] == ["api", "v1", "devices"] and segments[4:] == [
                "telemetry",
                "latest",
            ]:
                self.respond_json({"telemetry": store.latest_telemetry(segments[3])})
                return
            if len(segments) == 6 and segments[:3] == ["api", "v1", "devices"] and segments[4:] == [
                "telemetry",
                "history",
            ]:
                self.respond_json({"telemetry": store.telemetry_history(segments[3])})
                return
            if len(segments) == 5 and segments[:3] == ["api", "v1", "devices"] and segments[4] == "commands":
                self.respond_json({"commands": store.list_commands(segments[3])})
                return
            if len(segments) == 5 and segments[:3] == ["api", "v1", "devices"] and segments[4] == "raw-frames":
                self.respond_json({"raw_frames": store.list_raw_frames(segments[3])})
                return
            if len(segments) == 6 and segments[:3] == ["api", "v1", "devices"] and segments[4:] == [
                "commands",
                "poll",
            ]:
                self.respond_json({"commands": store.poll_commands(segments[3])})
                return
            if len(segments) == 6 and segments[:3] == ["api", "v1", "devices"] and segments[4:] == [
                "commands",
                "poll.raw",
            ]:
                frame, record = store.poll_commands_raw(segments[3])
                self.respond_bytes(
                    frame,
                    content_type="text/x-egolink-frame; profile=raw-frame.p0.v1",
                    headers={"X-Ego-Link-Raw-Frame-Id": record["frame_id"] if record else "none"},
                )
                return
            if segments == ["api", "v1", "test-runs"]:
                self.respond_json({"test_runs": store.list_test_runs()})
                return
            if len(segments) == 5 and segments[:3] == ["api", "v1", "test-runs"] and segments[4] == "export":
                self.respond_json(store.export_test_run(segments[3]))
                return
            if segments == ["api", "v1", "product-demo", "latest"]:
                self.respond_json({"product_demo": load_latest_product_demo_report(product_demo_root)})
                return
            raise MessageHubError("not_found", "route not found", status=404)

        def route_post(self) -> None:
            segments = split_path(urlparse(self.path).path)
            if len(segments) == 5 and segments[:3] == ["api", "v1", "devices"] and segments[4] == "raw-ingest":
                device_id = segments[3]
                raw_body = self.read_raw_body()
                injection = store.claim_raw_post_fail_once(device_id, raw_body)
                if injection:
                    record = store.ingest_raw_frame_injected_failure(device_id, raw_body, injection=injection)
                    self.respond_json(
                        {
                            "ok": False,
                            "error": "raw_post_fail_once_injected",
                            "detail": "test requested fail-once raw POST injection",
                            "raw_frame": redact_raw_frame_record(record),
                        },
                        status=503,
                    )
                    return
                record = store.ingest_raw_frame(device_id, raw_body)
                self.respond_json({"ok": True, "raw_frame": redact_raw_frame_record(record)})
                return
            if (
                len(segments) == 7
                and segments[:3] == ["api", "v1", "devices"]
                and segments[4] == "commands"
                and segments[6] == "ack.raw"
            ):
                device_id = segments[3]
                record = store.ingest_raw_frame(
                    device_id,
                    self.read_raw_body(),
                    expected_frame_type="ack",
                    expected_cmd_id=segments[5],
                )
                self.respond_json({"ok": True, "raw_frame": redact_raw_frame_record(record)})
                return
            body = self.read_json_body()
            if segments == ["api", "v1", "devices", "register"]:
                self.respond_json({"ok": True, "device": store.register_device(body)})
                return
            if len(segments) == 5 and segments[:3] == ["api", "v1", "devices"]:
                device_id = segments[3]
                endpoint = segments[4]
                if endpoint in {"heartbeat", "telemetry", "ack", "error"}:
                    self.respond_json({"ok": True, "message": store.ingest(device_id, endpoint, body)})
                    return
                if endpoint == "commands":
                    self.respond_json({"ok": True, "command": store.create_command(device_id, body)})
                    return
            if (
                len(segments) == 7
                and segments[:3] == ["api", "v1", "devices"]
                and segments[4] == "commands"
                and segments[6] == "ack"
            ):
                device_id = segments[3]
                body.setdefault("cmd_id", segments[5])
                self.respond_json({"ok": True, "message": store.ingest(device_id, "ack", body)})
                return
            if segments == ["api", "v1", "test-runs"]:
                self.respond_json({"ok": True, "test_run": store.create_test_run(body)})
                return
            raise MessageHubError("not_found", "route not found", status=404)

        def read_json_body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or "0")
            if length <= 0:
                return {}
            if length > MAX_BODY_BYTES:
                raise MessageHubError("body_too_large", "request body is too large", status=413)
            value = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(value, dict):
                raise MessageHubError("invalid_json", "request body must be a JSON object")
            return value

        def read_raw_body(self) -> bytes:
            length = int(self.headers.get("Content-Length") or "0")
            if length <= 0:
                return b""
            if length > MAX_BODY_BYTES:
                raise MessageHubError("body_too_large", "request body is too large", status=413)
            return self.rfile.read(length)

        def respond_json(self, payload: dict[str, Any], status: int = 200) -> None:
            body = dumps(payload, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def respond_html(self, html: str, status: int = 200) -> None:
            body = html.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def respond_bytes(
            self,
            body: bytes,
            *,
            content_type: str,
            status: int = 200,
            headers: dict[str, str] | None = None,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def respond_error(self, error: MessageHubError) -> None:
            self.respond_json({"ok": False, "error": error.code, "detail": str(error)}, status=error.status)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return MessageHubHandler


def split_path(path: str) -> list[str]:
    return [unquote(segment) for segment in path.split("/") if segment]


def authorized(header: str | None, token: str | None) -> bool:
    if not token:
        return True
    return header == f"Bearer {token}"


def require_text(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if value is None or str(value) == "":
        raise MessageHubError("missing_field", f"missing required field: {field}")
    return str(value)


def dumps(payload: Any, *, indent: int | None = None) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":") if indent is None else None, indent=indent)


def sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def crc32_hex(value: bytes) -> str:
    return f"{binascii.crc32(value) & 0xFFFFFFFF:08X}"


def initial_raw_frame_record(
    device_id: str,
    raw_body: bytes,
    direction: str,
    server_received_at: str,
) -> dict[str, Any]:
    digest = sha256_hex(raw_body)
    return {
        "protocol_version": protocol.PROTOCOL_VERSION,
        "transport_profile": RAW_FRAME_PROFILE,
        "direction": direction,
        "device_id": device_id,
        "frame_id": f"raw-{digest[:12]}",
        "server_received_at": server_received_at,
        "raw_payload": {
            "encoding": "base64",
            "data": base64.b64encode(raw_body).decode("ascii"),
            "byte_len": len(raw_body),
            "sha256": digest,
            "crc32": crc32_hex(raw_body),
        },
        "parse_result": {
            "status": "not_attempted",
            "derived_message_type": "unknown",
        },
        "retention": {
            "privacy_class": "engineering",
            "redacted": False,
        },
    }


def parse_raw_frame_record(
    initial: dict[str, Any],
    raw_body: bytes,
    *,
    expected_frame_type: str | None = None,
    expected_cmd_id: str | None = None,
) -> dict[str, Any]:
    record = json.loads(dumps(initial))
    header_bytes, payload, has_separator = split_raw_frame_bytes(raw_body)
    if not has_separator:
        record["parse_result"] = {
            "status": "partial",
            "error_code": "RAW_FRAME_HEADER_INCOMPLETE",
            "reason": "raw frame is missing a blank line before payload",
            "derived_message_type": "unknown",
        }
        return record

    header = parse_raw_header(header_bytes)
    fields = header["fields"]
    metadata = header["metadata"]
    frame_id = first_known(fields.get("id"), fields.get("frame_id"), expected_cmd_id, record["frame_id"])
    frame_type = str(fields.get("type") or "raw")
    content_type = str(first_known(fields.get("content-type"), fields.get("content_type"), metadata.get("content-type"), "application/octet-stream"))
    seq = parse_optional_int(fields.get("seq"))
    declared_len = parse_optional_int(fields.get("len"))
    declared_crc = normalize_crc32(fields.get("crc32"))
    payload_crc = crc32_hex(payload)
    kv_payload = parse_kv_payload(payload) if content_type.startswith("text/x-egolink-kv") else {}

    record.update(
        {
            "frame_id": str(frame_id),
            "seq": seq,
            "fw_version": first_known(kv_payload.get("fw-version"), fields.get("fw"), fields.get("fw-version")),
            "test_run_id": first_known(kv_payload.get("test-run-id"), fields.get("test-run-id")),
            "framing": {
                "magic": "EGLK" if header["magic_ok"] else str(header["magic"]),
                "frame_version": header["frame_version"],
                "frame_type": frame_type,
                "content_type": content_type,
                "payload_len": declared_len if declared_len is not None else len(payload),
                "payload_crc32": declared_crc or payload_crc,
                "actual_payload_len": len(payload),
                "actual_payload_crc32": payload_crc,
            },
        }
    )

    parse_result = validate_raw_frame_header(
        header,
        frame_type,
        declared_len,
        declared_crc,
        payload,
        expected_frame_type=expected_frame_type,
    )
    if parse_result["status"] == "ok":
        derived = derive_raw_frame_message(record, kv_payload, expected_cmd_id=expected_cmd_id)
        parse_result.update(
            {
                "derived_message_type": str(derived.get("message_type") or "unknown"),
                "derived_message": derived,
            }
        )
        if expected_cmd_id and derived.get("cmd_id") and str(derived["cmd_id"]) != expected_cmd_id:
            parse_result.update(
                {
                    "status": "malformed",
                    "error_code": "RAW_FRAME_CMD_ID_MISMATCH",
                    "reason": "raw frame command ID does not match route command ID",
                }
            )
    record["parse_result"] = parse_result
    return record


def parse_raw_frame_probe(device_id: str, raw_body: bytes) -> dict[str, Any]:
    initial = initial_raw_frame_record(device_id, raw_body, "uplink", utc_now())
    header_bytes, payload, has_separator = split_raw_frame_bytes(raw_body)
    result: dict[str, Any] = {
        "device_id": device_id,
        "frame_id": initial["frame_id"],
        "raw_payload_sha256": initial["raw_payload"]["sha256"],
        "kv_payload": {},
        "test_run_id": None,
    }
    if not has_separator:
        return result
    header = parse_raw_header(header_bytes)
    fields = header["fields"]
    metadata = header["metadata"]
    content_type = str(
        first_known(
            fields.get("content-type"),
            fields.get("content_type"),
            metadata.get("content-type"),
            "application/octet-stream",
        )
    )
    kv_payload = parse_kv_payload(payload) if content_type.startswith("text/x-egolink-kv") else {}
    result.update(
        {
            "frame_id": str(first_known(fields.get("id"), fields.get("frame-id"), initial["frame_id"])),
            "kv_payload": kv_payload,
            "test_run_id": first_known(kv_payload.get("test-run-id"), fields.get("test-run-id")),
        }
    )
    return result


def split_raw_frame_bytes(raw_body: bytes) -> tuple[bytes, bytes, bool]:
    for separator in (b"\r\n\r\n", b"\n\n"):
        index = raw_body.find(separator)
        if index >= 0:
            return raw_body[:index], raw_body[index + len(separator) :], True
    return raw_body, b"", False


def parse_raw_header(header_bytes: bytes) -> dict[str, Any]:
    text = header_bytes.decode("ascii", errors="replace")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    first = lines[0] if lines else ""
    tokens = first.split()
    magic = tokens[0] if tokens else ""
    magic_match = re.fullmatch(r"EGLK/(\d+)", magic)
    fields = parse_key_tokens(tokens[1:])
    metadata: dict[str, str] = {}
    for line in lines[1:]:
        if ":" in line:
            key, value = line.split(":", 1)
        elif "=" in line:
            key, value = line.split("=", 1)
        else:
            continue
        metadata[normalize_key(key)] = value.strip()
    return {
        "magic": magic,
        "magic_ok": bool(magic_match),
        "frame_version": int(magic_match.group(1)) if magic_match else None,
        "fields": fields,
        "metadata": metadata,
    }


def parse_key_tokens(tokens: list[str]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for token in tokens:
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        fields[normalize_key(key)] = value.strip()
    return fields


def normalize_key(key: str) -> str:
    return key.strip().lower().replace("_", "-")


def normalize_crc32(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text.upper() if re.fullmatch(r"[0-9A-Fa-f]{8}", text) else text


def parse_optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(str(value), 10)
    except ValueError:
        return None


def validate_raw_frame_header(
    header: dict[str, Any],
    frame_type: str,
    declared_len: int | None,
    declared_crc: str | None,
    payload: bytes,
    *,
    expected_frame_type: str | None = None,
) -> dict[str, Any]:
    if not header["magic_ok"] or header["frame_version"] != 1:
        return {
            "status": "unsupported",
            "error_code": "RAW_FRAME_UNSUPPORTED_MAGIC",
            "reason": "raw frame magic/version is not EGLK/1",
            "derived_message_type": "unknown",
        }
    if frame_type not in {"status", "event", "command", "ack", "error", "log", "raw"}:
        return {
            "status": "unsupported",
            "error_code": "RAW_FRAME_UNSUPPORTED_TYPE",
            "reason": f"unsupported raw frame type: {frame_type}",
            "derived_message_type": "unknown",
        }
    if expected_frame_type and frame_type != expected_frame_type:
        return {
            "status": "malformed",
            "error_code": "RAW_FRAME_TYPE_MISMATCH",
            "reason": f"expected {expected_frame_type} frame, got {frame_type}",
            "derived_message_type": "unknown",
        }
    if declared_len is None or declared_crc is None:
        return {
            "status": "malformed",
            "error_code": "RAW_FRAME_MISSING_LENGTH_OR_CRC",
            "reason": "raw frame must include len and crc32",
            "derived_message_type": "unknown",
        }
    if len(payload) < declared_len:
        return {
            "status": "partial",
            "error_code": "RAW_FRAME_PAYLOAD_PARTIAL",
            "reason": f"payload has {len(payload)} bytes, expected {declared_len}",
            "derived_message_type": "unknown",
        }
    if len(payload) != declared_len:
        return {
            "status": "malformed",
            "error_code": "RAW_FRAME_PAYLOAD_LENGTH_MISMATCH",
            "reason": f"payload has {len(payload)} bytes, expected {declared_len}",
            "derived_message_type": "unknown",
        }
    if declared_crc.upper() != crc32_hex(payload):
        return {
            "status": "checksum_failed",
            "error_code": "RAW_FRAME_PAYLOAD_CRC_MISMATCH",
            "reason": "payload CRC32 does not match frame header",
            "derived_message_type": "unknown",
        }
    return {"status": "ok", "derived_message_type": "unknown"}


def parse_kv_payload(payload: bytes) -> dict[str, str]:
    text = payload.decode("utf-8", errors="replace")
    result: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[normalize_key(key)] = value.strip()
    return result


def raw_cell_from_kv(kv_payload: dict[str, str]) -> dict[str, Any]:
    return compact_dict(
        {
            "rat": kv_payload.get("cell-rat"),
            "operator": kv_payload.get("cell-operator"),
            "mcc": kv_payload.get("cell-mcc"),
            "mnc": kv_payload.get("cell-mnc"),
            "tac": kv_payload.get("cell-tac"),
            "cell_id": kv_payload.get("cell-id"),
            "rssi": parse_raw_scalar(kv_payload.get("cell-rssi")),
            "rsrp": parse_raw_scalar(kv_payload.get("cell-rsrp")),
            "rsrq": parse_raw_scalar(kv_payload.get("cell-rsrq")),
            "sinr": parse_raw_scalar(kv_payload.get("cell-sinr")),
            "sim_state": kv_payload.get("cell-sim-state"),
            "registration_state": kv_payload.get("cell-registration-state"),
            "pdp_state": kv_payload.get("cell-pdp-state"),
            "reason_code": first_known(kv_payload.get("cell-reason-code"), kv_payload.get("lte-reason-code")),
        }
    )


def raw_lte_from_kv(kv_payload: dict[str, str]) -> dict[str, Any]:
    return compact_dict(
        {
            "driver": first_known(kv_payload.get("lte-driver"), kv_payload.get("lte-http-driver")),
            "query_ok": parse_bool_or_text(kv_payload.get("lte-query-ok")),
            "uart_ready": parse_bool_or_text(kv_payload.get("lte-uart-ready")),
            "at_ok": parse_bool_or_text(kv_payload.get("lte-at-ok")),
            "sim_ready": parse_bool_or_text(kv_payload.get("lte-sim-ready")),
            "registered": parse_bool_or_text(kv_payload.get("lte-registered")),
            "attached": parse_bool_or_text(kv_payload.get("lte-attached")),
            "pdp_active": parse_bool_or_text(kv_payload.get("lte-pdp-active")),
            "ip_valid": parse_bool_or_text(kv_payload.get("lte-ip-valid")),
            "sim_state": kv_payload.get("lte-sim-state"),
            "registration_state": kv_payload.get("lte-registration-state"),
            "apn_state": kv_payload.get("lte-apn-state"),
            "pdp_state": kv_payload.get("lte-pdp-state"),
            "assigned_ip": kv_payload.get("lte-assigned-ip"),
            "reason_code": kv_payload.get("lte-reason-code"),
        }
    )


def raw_gnss_from_kv(kv_payload: dict[str, str]) -> dict[str, Any]:
    return compact_dict(
        {
            "fix": parse_bool_or_text(kv_payload.get("gnss-fix")),
            "state": kv_payload.get("gnss-state"),
            "source": kv_payload.get("gnss-source"),
            "driver": kv_payload.get("gnss-driver"),
            "query_ok": parse_bool_or_text(kv_payload.get("gnss-query-ok")),
            "hdop": parse_raw_scalar(kv_payload.get("gnss-hdop")),
            "satellites": parse_raw_scalar(kv_payload.get("gnss-satellites")),
        }
    )


def raw_wifi_from_kv(kv_payload: dict[str, str]) -> dict[str, Any]:
    return compact_dict(
        {
            "source": kv_payload.get("wifi-source"),
            "source_status": kv_payload.get("wifi-source-status"),
            "evidence_status": kv_payload.get("wifi-evidence-status"),
            "scan_enabled": parse_bool_or_text(kv_payload.get("wifi-scan-enabled")),
            "ap_count": parse_optional_int(kv_payload.get("wifi-ap-count")),
            "rssi": parse_raw_scalar(kv_payload.get("wifi-rssi")),
            "privacy": kv_payload.get("wifi-privacy"),
            "reason": kv_payload.get("wifi-reason"),
        }
    )


def raw_imu_from_kv(kv_payload: dict[str, str]) -> dict[str, Any]:
    return compact_dict(
        {
            "source": kv_payload.get("imu-source"),
            "source_status": kv_payload.get("imu-source-status"),
            "evidence_status": kv_payload.get("imu-evidence-status"),
            "motion": kv_payload.get("imu-motion"),
            "confidence": parse_raw_scalar(kv_payload.get("imu-confidence")),
            "hardware_present": parse_bool_or_text(kv_payload.get("imu-hardware-present")),
            "driver_enabled": parse_bool_or_text(kv_payload.get("imu-driver-enabled")),
            "data_is_mock": parse_bool_or_text(kv_payload.get("imu-data-is-mock")),
            "backend_status": kv_payload.get("imu-backend-status"),
            "reason": kv_payload.get("imu-reason"),
        }
    )


def raw_power_from_kv(kv_payload: dict[str, str]) -> dict[str, Any]:
    return compact_dict(
        {
            "source": kv_payload.get("power-source"),
            "source_status": kv_payload.get("power-source-status"),
            "evidence_status": kv_payload.get("power-evidence-status"),
            "battery_mv": parse_raw_scalar(kv_payload.get("power-battery-mv")),
            "soc_pct": parse_raw_scalar(kv_payload.get("power-soc-pct")),
            "charging": parse_bool_or_text(kv_payload.get("power-charging")),
            "battery_source": kv_payload.get("power-battery-source"),
            "charging_source": kv_payload.get("power-charging-source"),
            "state": kv_payload.get("power-state"),
            "marker_seq": parse_optional_int(kv_payload.get("power-marker-seq")),
            "reason": kv_payload.get("power-reason"),
        }
    )


def raw_reliability_from_kv(kv_payload: dict[str, str]) -> dict[str, Any]:
    network = compact_dict(
        {
            "mode": kv_payload.get("network-mode"),
            "rssi": parse_raw_scalar(kv_payload.get("network-rssi")),
            "reconnect_count": parse_optional_int(
                first_known(kv_payload.get("network-reconnect-count"), kv_payload.get("reconnect-count"))
            ),
            "last_error": first_known(kv_payload.get("network-last-error"), kv_payload.get("transport-last-error")),
            "last_reconnect_reason": kv_payload.get("network-last-reconnect-reason"),
            "state": kv_payload.get("network-state"),
            "raw_post_attempt_count": parse_optional_int(kv_payload.get("network-raw-post-attempt-count")),
            "raw_post_success_count": parse_optional_int(kv_payload.get("network-raw-post-success-count")),
            "raw_post_failure_count": parse_optional_int(kv_payload.get("network-raw-post-failure-count")),
        }
    )
    cache = compact_dict(
        {
            "queued_message_count": parse_optional_int(
                first_known(kv_payload.get("cache-queued-message-count"), kv_payload.get("queued-message-count"))
            ),
            "dropped_message_count": parse_optional_int(
                first_known(kv_payload.get("cache-dropped-message-count"), kv_payload.get("dropped-message-count"))
            ),
            "last_drop_reason": first_known(kv_payload.get("cache-last-drop-reason"), kv_payload.get("last-drop-reason")),
            "oldest_message_age_ms": parse_optional_int(kv_payload.get("cache-oldest-message-age-ms")),
            "state": kv_payload.get("cache-state"),
            "source_status": kv_payload.get("cache-source-status"),
            "retry_policy": kv_payload.get("cache-retry-policy"),
            "retry_attempt_count": parse_optional_int(kv_payload.get("cache-retry-attempt-count")),
            "retry_success_count": parse_optional_int(kv_payload.get("cache-retry-success-count")),
            "retry_failure_count": parse_optional_int(kv_payload.get("cache-retry-failure-count")),
            "flush_attempt_count": parse_optional_int(kv_payload.get("cache-flush-attempt-count")),
            "flush_success_count": parse_optional_int(kv_payload.get("cache-flush-success-count")),
            "flush_failure_count": parse_optional_int(kv_payload.get("cache-flush-failure-count")),
        }
    )
    return compact_dict({"network": network or None, "cache": cache or None})


def raw_location_belief_from_kv(kv_payload: dict[str, str]) -> dict[str, Any]:
    state = first_known(kv_payload.get("location-belief-state"), kv_payload.get("belief-state"))
    if state is None:
        return {}
    source_value = first_known(kv_payload.get("location-belief-source"), kv_payload.get("belief-source"))
    sources = [item.strip() for item in str(source_value or "").split(",") if item.strip()]
    return compact_dict(
        {
            "state": state,
            "radius_m": parse_raw_scalar(
                first_known(kv_payload.get("location-belief-radius-m"), kv_payload.get("belief-radius-m"))
            ),
            "confidence": parse_raw_scalar(
                first_known(kv_payload.get("location-belief-confidence"), kv_payload.get("belief-confidence"))
            ),
            "source": sources or None,
            "reason": first_known(kv_payload.get("location-belief-reason"), kv_payload.get("belief-reason")),
        }
    )


def derive_raw_frame_message(
    record: dict[str, Any],
    kv_payload: dict[str, str],
    *,
    expected_cmd_id: str | None = None,
) -> dict[str, Any]:
    framing = as_dict(record.get("framing"))
    frame_type = str(framing.get("frame_type") or "raw")
    seq = first_known(parse_optional_int(kv_payload.get("seq")), record.get("seq"), 0)
    common = {
        "protocol_version": protocol.PROTOCOL_VERSION,
        "device_id": record["device_id"],
        "fw_version": first_known(record.get("fw_version"), kv_payload.get("fw-version"), "unknown"),
        "seq": seq,
        "ts": first_known(kv_payload.get("ts"), f"raw_frame:{record['frame_id']}"),
        "test_run_id": record.get("test_run_id") or kv_payload.get("test-run-id"),
        "raw_frame": {
            "frame_id": record["frame_id"],
            "transport_profile": RAW_FRAME_PROFILE,
        },
    }
    if frame_type == "ack":
        cmd_id = first_known(expected_cmd_id, kv_payload.get("cmd-id"), kv_payload.get("cmd_id"), record["frame_id"])
        transport_type = kv_payload.get("transport-type")
        reliability = raw_reliability_from_kv(kv_payload)
        lte_http = compact_dict(
            {
                "phase": kv_payload.get("lte-http-phase"),
                "driver": kv_payload.get("lte-http-driver"),
                "poll_reason_code": kv_payload.get("lte-http-poll-reason-code"),
                "poll_status_code": parse_optional_int(kv_payload.get("lte-http-poll-status-code")),
                "poll_action_elapsed_ms": parse_optional_int(kv_payload.get("lte-http-poll-action-elapsed-ms")),
            }
        )
        command_obs = compact_dict(
            {
                "last_cmd_id": kv_payload.get("command-last-cmd-id"),
                "parse_status": kv_payload.get("command-parse-status"),
                "command_count": parse_optional_int(kv_payload.get("command-count")),
                "duplicate_local_execution_prevented": parse_bool_or_text(
                    kv_payload.get("duplicate-local-execution-prevented")
                ),
            }
        )
        return compact_dict(
            {
                **common,
                "message_type": "ack",
                "cmd_id": cmd_id,
                "status": first_known(kv_payload.get("status"), "ok"),
                "message": first_known(kv_payload.get("message"), "raw-frame ack"),
                "transport": compact_dict({"type": transport_type}) if transport_type else None,
                "lte_http": lte_http or None,
                "command": command_obs or None,
                "reliability": reliability or None,
            }
        )
    if frame_type == "command":
        cmd_id = first_known(expected_cmd_id, kv_payload.get("cmd-id"), kv_payload.get("cmd_id"), record["frame_id"])
        return compact_dict(
            {
                "protocol_version": protocol.PROTOCOL_VERSION,
                "message_type": "command",
                "device_id": record["device_id"],
                "cmd_id": cmd_id,
                "cmd": first_known(kv_payload.get("cmd"), "unknown"),
                "created_at": first_known(kv_payload.get("created-at"), kv_payload.get("created_at"), record["server_received_at"]),
                "test_run_id": record.get("test_run_id") or kv_payload.get("test-run-id"),
                "payload": raw_command_payload(kv_payload),
            }
        )
    if frame_type == "status":
        reliability = raw_reliability_from_kv(kv_payload)
        return compact_dict(
            {
                **common,
                "message_type": "status",
                "battery": parse_number_or_text(kv_payload.get("battery")),
                "link_type": first_known(kv_payload.get("link-type"), kv_payload.get("link_type"), "unknown"),
                "guard_mode": first_known(kv_payload.get("guard-mode"), kv_payload.get("guard_mode"), "unknown"),
                "queue_size": parse_optional_int(kv_payload.get("queue-size") or kv_payload.get("queue_size")) or 0,
                "reliability": reliability or None,
            }
        )
    if frame_type == "event":
        event_type = first_known(kv_payload.get("event-type"), kv_payload.get("event_type"), "raw_event")
        reliability = raw_reliability_from_kv(kv_payload)
        event = compact_dict(
            {
                **common,
                "message_type": "event",
                "event_type": event_type,
                "priority": first_known(kv_payload.get("priority"), "normal"),
                "source": kv_payload.get("source"),
                "source_status": kv_payload.get("source-status"),
                "reliability": reliability or None,
            }
        )
        if event_type == "location_report":
            event.update(
                compact_dict(
                    {
                        "fix": parse_bool_or_text(kv_payload.get("fix")),
                        "gnss_state": kv_payload.get("gnss-state"),
                        "gnss_source": kv_payload.get("gnss-source"),
                        "gnss_driver": kv_payload.get("gnss-driver"),
                        "gnss_query_ok": parse_bool_or_text(kv_payload.get("gnss-query-ok")),
                        "lat": parse_raw_scalar(kv_payload.get("lat")),
                        "lon": parse_raw_scalar(kv_payload.get("lon")),
                        "altitude_m": parse_raw_scalar(kv_payload.get("altitude-m")),
                        "speed_mps": parse_raw_scalar(kv_payload.get("speed-mps")),
                        "course_deg": parse_raw_scalar(kv_payload.get("course-deg")),
                        "pdop": parse_raw_scalar(kv_payload.get("pdop")),
                        "hdop": parse_raw_scalar(kv_payload.get("hdop")),
                        "vdop": parse_raw_scalar(kv_payload.get("vdop")),
                        "satellites": parse_raw_scalar(kv_payload.get("satellites")),
                        "utc_date": kv_payload.get("utc-date"),
                        "utc_time": kv_payload.get("utc-time"),
                        "location_request_cmd_id": kv_payload.get("location-request-cmd-id"),
                        "transport": compact_dict({"type": kv_payload.get("transport-type")})
                        if kv_payload.get("transport-type")
                        else None,
                        "lte_http": compact_dict(
                            {
                                "phase": kv_payload.get("lte-http-phase"),
                                "driver": kv_payload.get("lte-http-driver"),
                            }
                        ),
                    }
                )
            )
        if event_type == "location_observation":
            cell = raw_cell_from_kv(kv_payload)
            lte = raw_lte_from_kv(kv_payload)
            gnss = raw_gnss_from_kv(kv_payload)
            wifi = raw_wifi_from_kv(kv_payload)
            imu = raw_imu_from_kv(kv_payload)
            power = raw_power_from_kv(kv_payload)
            location_belief = raw_location_belief_from_kv(kv_payload)
            event.update(
                compact_dict(
                    {
                        "location_request_cmd_id": kv_payload.get("location-request-cmd-id"),
                        "cell": cell or None,
                        "lte": lte or None,
                        "gnss": gnss or None,
                        "wifi": wifi or None,
                        "imu": imu or None,
                        "power": power or None,
                        "location_belief": location_belief or None,
                        "transport": compact_dict({"type": kv_payload.get("transport-type")})
                        if kv_payload.get("transport-type")
                        else None,
                        "lte_http": compact_dict(
                            {
                                "phase": kv_payload.get("lte-http-phase"),
                                "driver": kv_payload.get("lte-http-driver"),
                            }
                        ),
                    }
                )
            )
        return event
    if frame_type == "error":
        return compact_dict(
            {
                **common,
                "message_type": "error",
                "error_code": first_known(kv_payload.get("error-code"), kv_payload.get("error_code"), "RAW_FRAME_ERROR"),
                "severity": first_known(kv_payload.get("severity"), "warning"),
                "message": kv_payload.get("message"),
            }
        )
    return {}


def raw_command_payload(kv_payload: dict[str, str]) -> dict[str, Any]:
    reserved = {
        "cmd",
        "cmd-id",
        "cmd_id",
        "created-at",
        "created_at",
        "device-id",
        "device_id",
        "fw-version",
        "fw_version",
        "seq",
        "status",
        "test-run-id",
        "test_run_id",
        "ts",
    }
    return {key.replace("-", "_"): parse_number_or_text(value) for key, value in kv_payload.items() if key not in reserved}


def parse_number_or_text(value: Any) -> Any:
    if value in (None, ""):
        return None
    text = str(value)
    try:
        return int(text, 10)
    except ValueError:
        try:
            return float(text)
        except ValueError:
            return text


def parse_raw_scalar(value: Any) -> Any:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if text.lower() == "null":
        return None
    parsed_bool = parse_bool_or_text(text)
    if isinstance(parsed_bool, bool):
        return parsed_bool
    return parse_number_or_text(text)


def parse_bool_or_text(value: Any) -> Any:
    if value in (None, ""):
        return None
    text = str(value).strip().lower()
    if text == "true":
        return True
    if text == "false":
        return False
    return value


def compact_dict(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def derived_endpoint(message_type: Any) -> str | None:
    return {
        "status": "heartbeat",
        "event": "telemetry",
        "ack": "ack",
        "error": "error",
    }.get(str(message_type or ""))


def redact_raw_frame_record(record: dict[str, Any]) -> dict[str, Any]:
    redacted = json.loads(dumps(record))
    raw_payload = as_dict(redacted.get("raw_payload"))
    if "data" in raw_payload:
        raw_payload.pop("data", None)
        raw_payload["data_redacted"] = True
    retention = as_dict(redacted.get("retention"))
    retention["redacted"] = True
    redacted["retention"] = retention
    return redacted


def build_raw_frame(
    frame_type: str,
    frame_id: str,
    payload: bytes,
    *,
    seq: int | None = None,
    content_type: str = "text/x-egolink-kv",
    metadata: dict[str, Any] | None = None,
) -> bytes:
    header_parts = [
        "EGLK/1",
        f"type={frame_type}",
        f"id={frame_id}",
        f"len={len(payload)}",
        f"crc32={crc32_hex(payload)}",
    ]
    if seq is not None:
        header_parts.insert(3, f"seq={seq}")
    lines = [" ".join(header_parts), f"content-type={content_type}"]
    for key, value in (metadata or {}).items():
        if value not in (None, ""):
            lines.append(f"{key}={value}")
    return ("\n".join(lines) + "\n\n").encode("ascii") + payload


def build_raw_command_frame(device_id: str, command: dict[str, Any] | None) -> bytes:
    if not command:
        return build_raw_frame(
            "command",
            "cmd-none",
            b"cmd=none\n",
            metadata={"device-id": device_id},
        )
    payload_lines = [
        f"cmd={command['cmd']}",
        f"cmd_id={command['cmd_id']}",
    ]
    payload = as_dict(command.get("payload"))
    for key, value in payload.items():
        if isinstance(value, (str, int, float, bool)):
            payload_lines.append(f"{key}={value}")
    if command.get("test_run_id"):
        payload_lines.append(f"test_run_id={command['test_run_id']}")
    return build_raw_frame(
        "command",
        str(command["cmd_id"]),
        ("\n".join(payload_lines) + "\n").encode("utf-8"),
        metadata={"device-id": device_id, "test-run-id": command.get("test_run_id")},
    )


def device_row(row: sqlite3.Row) -> dict[str, Any]:
    device = dict(row)
    for field in ("last_status_json", "latest_telemetry_json", "last_error_json"):
        if device.get(field):
            device[field.replace("_json", "")] = json.loads(str(device[field]))
        device.pop(field, None)
    return device


def command_row(row: sqlite3.Row) -> dict[str, Any]:
    command = json.loads(row["payload_json"])
    return command_with_status(command, row["status"], ack_json=row["ack_json"], updated_at=row["updated_at"])


def command_with_status(
    command: dict[str, Any],
    status: str,
    *,
    ack_json: str | None = None,
    updated_at: str | None = None,
) -> dict[str, Any]:
    enriched = dict(command)
    enriched["status"] = status
    if updated_at:
        enriched["updated_at"] = updated_at
    if ack_json:
        enriched["ack"] = json.loads(ack_json)
    return enriched


def dict_value(payload: dict[str, Any] | None, *path: str) -> Any:
    value: Any = payload
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def first_known(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if value in (None, ""):
        return None
    try:
        return float(str(value))
    except ValueError:
        return None


def normalize_location_state(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    return {
        "fine": "Fine",
        "coarse": "Coarse",
        "predicted": "Predicted",
        "unknown": "Unknown",
    }.get(text)


def source_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    if value not in (None, ""):
        return [str(value)]
    return []


def merge_sources(*values: Any) -> list[str]:
    merged: list[str] = []
    for value in values:
        for item in source_list(value):
            if item not in merged:
                merged.append(item)
    return merged


def has_predictable_location_memory(memory: dict[str, Any]) -> bool:
    return memory.get("state") in {"Fine", "Coarse", "Predicted"}


def derived_gnss_radius_m(message: dict[str, Any]) -> float:
    gnss = as_dict(message.get("gnss"))
    hdop = as_number(first_known(message.get("hdop"), gnss.get("hdop")))
    if hdop and hdop > 0:
        return round(max(8.0, hdop * 10.0), 1)
    return 25.0


def location_position(message: dict[str, Any]) -> dict[str, Any]:
    lat = first_known(message.get("lat"), dict_value(message, "location", "lat"))
    lon = first_known(message.get("lon"), dict_value(message, "location", "lon"))
    if lat is None or lon is None:
        return {}
    return compact_dict(
        {
            "lat": lat,
            "lon": lon,
            "altitude_m": first_known(message.get("altitude_m"), dict_value(message, "location", "altitude_m")),
            "speed_mps": message.get("speed_mps"),
            "course_deg": message.get("course_deg"),
            "hdop": first_known(message.get("hdop"), dict_value(message, "gnss", "hdop")),
            "satellites": first_known(message.get("satellites"), dict_value(message, "gnss", "satellites")),
            "source_status": message.get("source_status"),
        }
    )


def location_evidence_summary(message: dict[str, Any], server_received_at: str) -> dict[str, Any]:
    gnss = as_dict(message.get("gnss"))
    cell = as_dict(message.get("cell"))
    lte = as_dict(message.get("lte"))
    transport = as_dict(message.get("transport"))
    lte_http = as_dict(message.get("lte_http"))
    return compact_dict(
        {
            "event_type": message.get("event_type"),
            "seq": message.get("seq"),
            "ts": message.get("ts"),
            "server_received_at": server_received_at,
            "test_run_id": message.get("test_run_id"),
            "source": message.get("source"),
            "source_status": message.get("source_status"),
            "fix": first_known(message.get("fix"), gnss.get("fix")),
            "gnss_state": first_known(message.get("gnss_state"), gnss.get("state"), gnss.get("result")),
            "gnss_query_ok": first_known(message.get("gnss_query_ok"), gnss.get("query_ok")),
            "cell_rat": cell.get("rat"),
            "cell_id": first_known(cell.get("cell_id"), cell.get("scell_id"), cell.get("scellid")),
            "cell_registration_state": cell.get("registration_state"),
            "lte_reason_code": first_known(lte.get("reason_code"), cell.get("reason_code")),
            "location_request_cmd_id": message.get("location_request_cmd_id"),
            "transport_type": transport.get("type"),
            "lte_http_phase": lte_http.get("phase"),
        }
    )


def build_location_memory(
    device_id: str,
    message: dict[str, Any],
    server_received_at: str,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event_type = str(message.get("event_type") or "")
    if event_type not in {"location_report", "location_observation"}:
        return {}

    memory = dict(existing or {})
    memory["device_id"] = device_id
    memory["updated_at"] = server_received_at
    memory["last_test_run_id"] = first_known(message.get("test_run_id"), memory.get("last_test_run_id"))

    evidence = location_evidence_summary(message, server_received_at)
    position = location_position(message)
    gnss = as_dict(message.get("gnss"))
    payload = as_dict(message.get("payload"))
    belief = as_dict(first_known(message.get("location_belief"), payload.get("location_belief")))
    fix = first_known(message.get("fix"), gnss.get("fix"))

    if belief:
        state = normalize_location_state(belief.get("state")) or "Unknown"
        if state == "Unknown" and has_predictable_location_memory(memory):
            memory["updated_at"] = server_received_at
            memory["last_test_run_id"] = first_known(message.get("test_run_id"), memory.get("last_test_run_id"))
            memory["last_unknown_observation"] = evidence
            memory["last_evidence"] = evidence
            if fix is False:
                memory["last_no_fix"] = evidence
            return memory
        memory.update(
            compact_dict(
                {
                    "state": state,
                    "radius_m": belief.get("radius_m"),
                    "confidence": belief.get("confidence"),
                    "source": merge_sources(belief.get("source")),
                    "reason": first_known(belief.get("reason"), "location_observation_belief"),
                    "belief_updated_at": server_received_at,
                    "last_evidence": evidence,
                }
            )
        )
        if position:
            memory["last_known_location"] = {**position, "updated_at": server_received_at}
        if fix is False:
            memory["last_no_fix"] = evidence
        return memory

    if fix is True:
        source_status = str(message.get("source_status") or "unknown")
        confidence = 0.92 if source_status in {"verified", "observed", "pc_side_verified"} else 0.72
        memory.update(
            compact_dict(
                {
                    "state": "Fine",
                    "radius_m": derived_gnss_radius_m(message),
                    "confidence": confidence,
                    "source": merge_sources("gnss", message.get("source")),
                    "reason": "gnss_fix_calibration"
                    if source_status in {"verified", "observed", "pc_side_verified"}
                    else "gnss_fix_unverified",
                    "belief_updated_at": server_received_at,
                    "last_evidence": evidence,
                }
            )
        )
        if position:
            memory["last_known_location"] = {**position, "updated_at": server_received_at}
        return memory

    if fix is False:
        memory["last_no_fix"] = evidence
        memory.setdefault("state", "Unknown")
        memory.setdefault("radius_m", None)
        memory.setdefault("confidence", None)
        memory.setdefault("source", [])
        memory.setdefault("reason", "gnss_no_fix_no_location_memory")
        return memory

    if not memory:
        memory.update(
            {
                "state": "Unknown",
                "radius_m": None,
                "confidence": None,
                "source": [],
                "reason": "location_observation_without_belief",
                "last_evidence": evidence,
            }
        )
    return memory


def active_location_belief(
    field_message: dict[str, Any],
    field_payload: dict[str, Any],
    location_memory: dict[str, Any],
) -> dict[str, Any]:
    explicit = as_dict(first_known(field_message.get("location_belief"), field_payload.get("location_belief")))
    if explicit:
        state = normalize_location_state(explicit.get("state")) or first_known(explicit.get("state"), "unknown")
        if state == "Unknown" and has_predictable_location_memory(location_memory):
            confidence = as_number(location_memory.get("confidence"))
            return {
                "state": "Predicted",
                "radius_m": location_memory.get("radius_m"),
                "confidence": round(confidence * 0.75, 3) if confidence is not None else None,
                "source": merge_sources(location_memory.get("source"), "memory"),
                "reason": "last_known_after_unknown_location_observation",
                "updated_at": first_known(field_message.get("server_received_at"), location_memory.get("updated_at")),
            }
        return {
            "state": state,
            "radius_m": explicit.get("radius_m"),
            "confidence": explicit.get("confidence"),
            "source": source_list(explicit.get("source")),
            "reason": first_known(explicit.get("reason"), "location_observation_belief"),
            "updated_at": first_known(field_message.get("server_received_at"), explicit.get("updated_at")),
        }

    if not location_memory:
        return {
            "state": "unknown",
            "radius_m": None,
            "confidence": None,
            "source": [],
            "reason": "no_location_belief",
            "updated_at": field_message.get("server_received_at"),
        }

    gnss = as_dict(field_message.get("gnss"))
    fix = first_known(field_message.get("fix"), gnss.get("fix"))
    if fix is False and location_memory.get("state") in {"Fine", "Coarse", "Predicted"}:
        confidence = as_number(location_memory.get("confidence"))
        return {
            "state": "Predicted",
            "radius_m": location_memory.get("radius_m"),
            "confidence": round(confidence * 0.75, 3) if confidence is not None else None,
            "source": merge_sources(location_memory.get("source"), "memory"),
            "reason": "last_known_after_gnss_no_fix",
            "updated_at": first_known(field_message.get("server_received_at"), location_memory.get("updated_at")),
        }

    return {
        "state": first_known(location_memory.get("state"), "unknown"),
        "radius_m": location_memory.get("radius_m"),
        "confidence": location_memory.get("confidence"),
        "source": source_list(location_memory.get("source")),
        "reason": first_known(location_memory.get("reason"), "location_memory"),
        "updated_at": first_known(location_memory.get("belief_updated_at"), location_memory.get("updated_at")),
    }


def summarize_location_memory(messages: list[dict[str, Any]]) -> dict[str, Any]:
    memory: dict[str, Any] = {}
    for message in messages:
        if message.get("message_type") != "event":
            continue
        if message.get("event_type") not in {"location_report", "location_observation"}:
            continue
        memory = build_location_memory(
            str(message.get("device_id") or ""),
            message,
            str(message.get("server_received_at") or message.get("ts") or utc_now()),
            memory,
        )
    return memory


def parse_iso_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def elapsed_ms(start: Any, end: Any) -> int | None:
    start_dt = parse_iso_timestamp(start)
    end_dt = parse_iso_timestamp(end)
    if start_dt is None or end_dt is None:
        return None
    return int(max(0.0, (end_dt - start_dt).total_seconds()) * 1000)


def latest_message(messages: list[dict[str, Any]], *, message_type: str | None = None, event_type: str | None = None) -> dict[str, Any]:
    for message in reversed(messages):
        if message_type and message.get("message_type") != message_type:
            continue
        if event_type and message.get("event_type") != event_type:
            continue
        return message
    return {}


def latest_location_message(messages: list[dict[str, Any]]) -> dict[str, Any]:
    for message in reversed(messages):
        if message.get("message_type") != "event":
            continue
        if message.get("event_type") in {"location_observation", "location_report"}:
            return message
    return {}


def build_gnss_reason(fix: Any, state: Any, error_code: Any, latest_location: dict[str, Any]) -> str:
    if fix is True:
        return "GNSS_FIX"
    if error_code and "GNSS" in str(error_code):
        return str(error_code)
    if not latest_location:
        return "GNSS_NO_OBSERVATION"
    state_text = str(state or "unknown").strip().lower()
    if not state_text or state_text == "unknown":
        return "GNSS_UNKNOWN"
    return "GNSS_" + "".join(ch if ch.isalnum() else "_" for ch in state_text.upper()).strip("_")


def elapsed_seconds_since(value: Any) -> int | None:
    timestamp = parse_iso_timestamp(value)
    now = parse_iso_timestamp(utc_now())
    if timestamp is None or now is None:
        return None
    return int(max(0.0, (now - timestamp).total_seconds()))


def d1_observed_value(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"", "unknown"}
    return value not in (None, [], {})


def d1_component_seen(payload: dict[str, Any], keys: list[str]) -> bool:
    return any(d1_observed_value(payload.get(key)) for key in keys)


def build_d1_link_summary(device: dict[str, Any]) -> dict[str, Any]:
    latest_location = as_dict(device.get("latest_location"))
    location_memory = as_dict(device.get("location_memory"))
    observability = as_dict(device.get("observability"))
    belief = as_dict(observability.get("location_belief"))
    gnss = as_dict(observability.get("gnss"))
    cell = as_dict(observability.get("cell"))
    lte = as_dict(observability.get("lte"))
    imu = as_dict(observability.get("imu"))
    power = as_dict(observability.get("power"))
    transport = as_dict(observability.get("transport"))

    location_lat = first_known(latest_location.get("lat"), dict_value(latest_location, "location", "lat"))
    location_lon = first_known(latest_location.get("lon"), dict_value(latest_location, "location", "lon"))
    memory_lat = dict_value(location_memory, "last_known_location", "lat")
    memory_lon = dict_value(location_memory, "last_known_location", "lon")
    map_lat = first_known(location_lat, memory_lat)
    map_lon = first_known(location_lon, memory_lon)
    has_coordinate = map_lat is not None and map_lon is not None

    state = first_known(belief.get("state"), "unknown")
    estimate_available = bool(latest_location) or str(state).strip().lower() not in {"", "unknown"}
    if has_coordinate and location_lat is not None and location_lon is not None:
        map_mode = "coordinate"
    elif has_coordinate:
        map_mode = "memory_coordinate"
    elif estimate_available:
        map_mode = "estimate_without_coordinate"
    else:
        map_mode = "waiting_for_location_upload"
    if location_lat is not None and location_lon is not None:
        coordinate_source = "latest_location"
    elif has_coordinate:
        coordinate_source = "location_memory"
    else:
        coordinate_source = None

    last_location_upload_at = latest_location.get("server_received_at")
    last_device_upload_at = device.get("last_seen_at")
    freshness_anchor = first_known(last_location_upload_at, belief.get("updated_at"), last_device_upload_at)
    status = "estimate_visible" if estimate_available else "waiting_for_location_upload"
    cell_lte_seen = d1_component_seen(
        cell,
        ["rat", "operator", "mcc", "mnc", "tac", "cell_id", "rsrp", "rsrq", "rssi", "sinr", "registration_state", "pdp_state"],
    ) or d1_component_seen(
        lte,
        ["registered", "attached", "pdp_active", "assigned_ip", "registration_state", "pdp_state", "reason_code"],
    )

    return {
        "demo": "D1",
        "status": status,
        "location_estimate": {
            "available": estimate_available,
            "state": state,
            "radius_m": belief.get("radius_m"),
            "confidence": belief.get("confidence"),
            "source": belief.get("source") if isinstance(belief.get("source"), list) else [],
            "reason": first_known(belief.get("reason"), "no_location_estimate"),
            "updated_at": first_known(belief.get("updated_at"), last_location_upload_at),
            "accuracy_claim": "none",
        },
        "map_surface": {
            "visible": estimate_available or has_coordinate,
            "mode": map_mode,
            "lat": map_lat,
            "lon": map_lon,
            "coordinate_source": coordinate_source,
        },
        "upload_freshness": {
            "last_location_upload_at": last_location_upload_at,
            "last_device_upload_at": last_device_upload_at,
            "freshness_s": elapsed_seconds_since(freshness_anchor),
            "last_location_event_type": latest_location.get("event_type"),
            "last_seq": first_known(latest_location.get("seq"), device.get("last_seq")),
        },
        "evidence": {
            "transport_type": first_known(transport.get("type"), "unknown"),
            "components": {
                "gnss": {
                    "seen": bool(latest_location),
                    "fix": first_known(latest_location.get("fix"), gnss.get("fix")),
                    "state": first_known(latest_location.get("gnss_state"), gnss.get("state"), "unknown"),
                    "reason_code": gnss.get("reason_code"),
                },
                "cell_lte": {
                    "seen": cell_lte_seen,
                    "cell_id": cell.get("cell_id"),
                    "rat": cell.get("rat"),
                    "registration_state": first_known(cell.get("registration_state"), lte.get("registration_state")),
                    "pdp_state": first_known(cell.get("pdp_state"), lte.get("pdp_state")),
                },
                "imu": {
                    "seen": d1_component_seen(imu, ["motion", "confidence", "hardware_present", "driver_enabled", "data_is_mock", "backend_status", "source_status", "evidence_status"]),
                    "motion": imu.get("motion"),
                    "confidence": imu.get("confidence"),
                    "evidence_status": imu.get("evidence_status"),
                },
                "power": {
                    "seen": d1_component_seen(power, ["battery_mv", "soc_pct", "charging", "state", "marker_seq", "source_status", "evidence_status"]),
                    "battery_mv": power.get("battery_mv"),
                    "soc_pct": power.get("soc_pct"),
                    "evidence_status": power.get("evidence_status"),
                },
            },
        },
        "non_claims": ["location_accuracy_not_claimed", "battery_life_not_claimed"],
    }


def build_observability(device: dict[str, Any], latest_command: dict[str, Any] | None = None) -> dict[str, Any]:
    status = as_dict(device.get("last_status"))
    telemetry = as_dict(device.get("latest_telemetry"))
    latest_location = as_dict(device.get("latest_location"))
    latest_location_observation = as_dict(device.get("latest_location_observation"))
    location_memory = as_dict(device.get("location_memory"))
    field_message = latest_location if latest_location else telemetry
    error = as_dict(device.get("last_error"))
    latest_command = as_dict(latest_command)

    status_payload = as_dict(status.get("payload"))
    telemetry_payload = as_dict(telemetry.get("payload"))
    field_payload = as_dict(field_message.get("payload"))
    transport = as_dict(first_known(status.get("transport"), telemetry.get("transport"), field_message.get("transport")))
    runtime = as_dict(first_known(status.get("runtime"), telemetry.get("runtime")))
    power = as_dict(first_known(field_message.get("power"), telemetry.get("power"), status.get("power")))
    gnss = as_dict(first_known(field_message.get("gnss"), field_payload.get("gnss"), telemetry_payload.get("gnss")))
    cell = as_dict(first_known(field_message.get("cell"), telemetry.get("cell"), status.get("cell")))
    lte = as_dict(first_known(field_message.get("lte"), telemetry.get("lte"), status.get("lte")))
    wifi = as_dict(first_known(field_message.get("wifi"), telemetry.get("wifi"), status.get("wifi")))
    imu = as_dict(first_known(field_message.get("imu"), telemetry.get("imu"), status.get("imu")))
    location_belief = active_location_belief(field_message, field_payload, location_memory)
    ack = as_dict(latest_command.get("ack"))
    field_reliability = as_dict(field_message.get("reliability"))
    telemetry_reliability = as_dict(telemetry.get("reliability"))
    status_reliability = as_dict(status.get("reliability"))
    ack_reliability = as_dict(ack.get("reliability"))
    reliability_network = as_dict(
        first_known(
            field_reliability.get("network"),
            telemetry_reliability.get("network"),
            status_reliability.get("network"),
            ack_reliability.get("network"),
            field_message.get("network"),
            telemetry.get("network"),
            status.get("network"),
            ack.get("network"),
        )
    )
    reliability_cache = as_dict(
        first_known(
            field_reliability.get("cache"),
            telemetry_reliability.get("cache"),
            status_reliability.get("cache"),
            ack_reliability.get("cache"),
            field_message.get("cache"),
            telemetry.get("cache"),
            status.get("cache"),
            ack.get("cache"),
        )
    )

    boot_count = first_known(status.get("boot_count"), telemetry.get("boot_count"), runtime.get("boot_count"))
    boot_id = first_known(status.get("boot_id"), telemetry.get("boot_id"), runtime.get("boot_id"))
    if boot_id is None and boot_count is not None:
        boot_id = f"boot_count:{boot_count}"

    boot_uptime_ms = first_known(status.get("boot_uptime_ms"), telemetry.get("boot_uptime_ms"), runtime.get("boot_uptime_ms"))
    uptime_s = first_known(
        status.get("uptime_s"),
        status.get("uptime_sec"),
        status_payload.get("uptime_sec"),
        runtime.get("uptime_s"),
        (boot_uptime_ms / 1000.0) if isinstance(boot_uptime_ms, (int, float)) else None,
    )

    command_rtt_ms = first_known(
        latest_command.get("rtt_ms"),
        elapsed_ms(latest_command.get("created_at"), ack.get("server_received_at") or latest_command.get("updated_at")),
    )

    fix = first_known(field_message.get("fix"), gnss.get("fix"))
    gnss_state = first_known(field_message.get("gnss_state"), gnss.get("state"), gnss.get("result"))
    error_code = error.get("error_code")
    gnss_reason = build_gnss_reason(fix, gnss_state, error_code, latest_location)

    transport_last_error = first_known(transport.get("last_error"), status.get("transport_last_error"), error_code)
    lte_reason = first_known(lte.get("reason_code"), cell.get("reason_code"))
    reliability = compact_dict(
        {
            "network": compact_dict(
                {
                    "mode": first_known(
                        reliability_network.get("mode"),
                        status.get("network_mode"),
                        telemetry.get("network_mode"),
                    ),
                    "rssi": first_known(reliability_network.get("rssi"), status.get("network_rssi"), telemetry.get("network_rssi")),
                    "reconnect_count": first_known(
                        reliability_network.get("reconnect_count"),
                        status.get("network_reconnect_count"),
                        telemetry.get("network_reconnect_count"),
                        ack.get("network_reconnect_count"),
                        status.get("reconnect_count"),
                        telemetry.get("reconnect_count"),
                    ),
                    "last_error": first_known(
                        reliability_network.get("last_error"),
                        status.get("network_last_error"),
                        telemetry.get("network_last_error"),
                        ack.get("network_last_error"),
                    ),
                    "last_reconnect_reason": first_known(
                        reliability_network.get("last_reconnect_reason"),
                        status.get("network_last_reconnect_reason"),
                        telemetry.get("network_last_reconnect_reason"),
                    ),
                    "state": reliability_network.get("state"),
                    "raw_post_attempt_count": first_known(
                        reliability_network.get("raw_post_attempt_count"),
                        status.get("network_raw_post_attempt_count"),
                        telemetry.get("network_raw_post_attempt_count"),
                        ack.get("network_raw_post_attempt_count"),
                    ),
                    "raw_post_success_count": first_known(
                        reliability_network.get("raw_post_success_count"),
                        status.get("network_raw_post_success_count"),
                        telemetry.get("network_raw_post_success_count"),
                        ack.get("network_raw_post_success_count"),
                    ),
                    "raw_post_failure_count": first_known(
                        reliability_network.get("raw_post_failure_count"),
                        status.get("network_raw_post_failure_count"),
                        telemetry.get("network_raw_post_failure_count"),
                        ack.get("network_raw_post_failure_count"),
                    ),
                }
            )
            or None,
            "cache": compact_dict(
                {
                    "queued_message_count": first_known(
                        reliability_cache.get("queued_message_count"),
                        status.get("cache_queued_message_count"),
                        telemetry.get("cache_queued_message_count"),
                        ack.get("cache_queued_message_count"),
                        status.get("queued_message_count"),
                        telemetry.get("queued_message_count"),
                    ),
                    "dropped_message_count": first_known(
                        reliability_cache.get("dropped_message_count"),
                        status.get("cache_dropped_message_count"),
                        telemetry.get("cache_dropped_message_count"),
                        ack.get("cache_dropped_message_count"),
                        status.get("dropped_message_count"),
                        telemetry.get("dropped_message_count"),
                    ),
                    "last_drop_reason": first_known(
                        reliability_cache.get("last_drop_reason"),
                        status.get("cache_last_drop_reason"),
                        telemetry.get("cache_last_drop_reason"),
                    ),
                    "oldest_message_age_ms": first_known(
                        reliability_cache.get("oldest_message_age_ms"),
                        status.get("cache_oldest_message_age_ms"),
                        telemetry.get("cache_oldest_message_age_ms"),
                    ),
                    "state": reliability_cache.get("state"),
                    "source_status": reliability_cache.get("source_status"),
                    "retry_policy": first_known(
                        reliability_cache.get("retry_policy"),
                        status.get("cache_retry_policy"),
                        telemetry.get("cache_retry_policy"),
                        ack.get("cache_retry_policy"),
                    ),
                    "retry_attempt_count": first_known(
                        reliability_cache.get("retry_attempt_count"),
                        status.get("cache_retry_attempt_count"),
                        telemetry.get("cache_retry_attempt_count"),
                        ack.get("cache_retry_attempt_count"),
                    ),
                    "retry_success_count": first_known(
                        reliability_cache.get("retry_success_count"),
                        status.get("cache_retry_success_count"),
                        telemetry.get("cache_retry_success_count"),
                        ack.get("cache_retry_success_count"),
                    ),
                    "retry_failure_count": first_known(
                        reliability_cache.get("retry_failure_count"),
                        status.get("cache_retry_failure_count"),
                        telemetry.get("cache_retry_failure_count"),
                        ack.get("cache_retry_failure_count"),
                    ),
                    "flush_attempt_count": first_known(
                        reliability_cache.get("flush_attempt_count"),
                        status.get("cache_flush_attempt_count"),
                        telemetry.get("cache_flush_attempt_count"),
                        ack.get("cache_flush_attempt_count"),
                    ),
                    "flush_success_count": first_known(
                        reliability_cache.get("flush_success_count"),
                        status.get("cache_flush_success_count"),
                        telemetry.get("cache_flush_success_count"),
                        ack.get("cache_flush_success_count"),
                    ),
                    "flush_failure_count": first_known(
                        reliability_cache.get("flush_failure_count"),
                        status.get("cache_flush_failure_count"),
                        telemetry.get("cache_flush_failure_count"),
                        ack.get("cache_flush_failure_count"),
                    ),
                }
            )
            or None,
        }
    )
    reason_codes: list[str] = []
    reliability_network_error = dict_value(reliability, "network", "last_error")
    for candidate in (error_code, transport_last_error, reliability_network_error, gnss_reason, lte_reason):
        if candidate and candidate not in {"none", "unknown", "GNSS_FIX", "LTE_READY"} and candidate not in reason_codes:
            reason_codes.append(str(candidate))

    return {
        "message": {
            "seq": device.get("last_seq"),
            "last_seen_at": device.get("last_seen_at"),
            "last_message_type": device.get("last_message_type"),
            "fw_version": device.get("fw_version") or "unknown",
        },
        "transport": {
            "type": first_known(transport.get("type"), status.get("transport_type"), telemetry.get("transport_type"), status.get("link_type"), "unknown"),
            "rtt_ms": first_known(transport.get("rtt_ms"), status.get("transport_rtt_ms"), telemetry.get("transport_rtt_ms")),
            "last_error": transport_last_error,
        },
        "runtime": {
            "boot_id": boot_id or "unknown",
            "uptime_s": uptime_s,
            "free_heap": first_known(runtime.get("free_heap"), status.get("free_heap"), status_payload.get("free_heap"), telemetry.get("free_heap")),
            "last_reset_reason": first_known(runtime.get("last_reset_reason"), status.get("reset_reason"), telemetry.get("reset_reason"), "unknown"),
            "watchdog_count": first_known(runtime.get("watchdog_count"), status.get("watchdog_count"), telemetry.get("watchdog_count")),
        },
        "command": {
            "last_cmd_id": latest_command.get("cmd_id"),
            "last_cmd": latest_command.get("cmd"),
            "last_status": latest_command.get("status"),
            "last_ack_status": ack.get("status"),
            "rtt_ms": command_rtt_ms,
        },
        "reliability": reliability,
        "power": {
            "battery_mv": first_known(power.get("battery_mv"), status.get("battery_mv"), status_payload.get("battery_mv")),
            "soc_pct": first_known(power.get("soc_pct"), status.get("soc_pct"), status.get("battery_percent"), status.get("battery")),
            "charging": first_known(power.get("charging"), status.get("charging")),
            "source": first_known(power.get("source"), status.get("battery_source"), "unknown"),
            "source_status": first_known(power.get("source_status"), "unknown"),
            "evidence_status": first_known(power.get("evidence_status"), "unknown"),
            "state": power.get("state"),
            "marker_seq": power.get("marker_seq"),
            "reason": power.get("reason"),
        },
        "gnss": {
            "fix": fix,
            "state": first_known(gnss_state, "unknown"),
            "hdop": first_known(field_message.get("hdop"), gnss.get("hdop")),
            "satellites": first_known(field_message.get("satellites"), gnss.get("satellites"), gnss.get("no_sv")),
            "attempt_ms": first_known(field_message.get("attempt_ms"), field_message.get("gnss_attempt_ms"), gnss.get("attempt_ms")),
            "result": first_known(gnss.get("result"), gnss_state, "unknown"),
            "reason_code": gnss_reason,
        },
        "cell": {
            "rat": first_known(cell.get("rat"), cell.get("system_mode"), cell.get("mode")),
            "operator": cell.get("operator"),
            "mcc": cell.get("mcc"),
            "mnc": cell.get("mnc"),
            "tac": cell.get("tac"),
            "cell_id": first_known(cell.get("cell_id"), cell.get("scell_id"), cell.get("scellid")),
            "rsrp": cell.get("rsrp"),
            "rsrq": cell.get("rsrq"),
            "rssi": first_known(cell.get("rssi"), status.get("rssi"), telemetry.get("rssi")),
            "sinr": first_known(cell.get("sinr"), cell.get("rssnr")),
            "sim_state": first_known(cell.get("sim_state"), lte.get("sim_state")),
            "registration_state": first_known(cell.get("registration_state"), lte.get("registration_state")),
            "pdp_state": first_known(cell.get("pdp_state"), lte.get("pdp_state")),
            "reason_code": lte_reason,
        },
        "lte": {
            "driver": first_known(lte.get("driver"), "unknown"),
            "query_ok": lte.get("query_ok"),
            "uart_ready": lte.get("uart_ready"),
            "at_ok": lte.get("at_ok"),
            "sim_ready": lte.get("sim_ready"),
            "registered": lte.get("registered"),
            "attached": lte.get("attached"),
            "pdp_active": lte.get("pdp_active"),
            "ip_valid": lte.get("ip_valid"),
            "sim_state": first_known(lte.get("sim_state"), cell.get("sim_state"), "unknown"),
            "registration_state": first_known(lte.get("registration_state"), cell.get("registration_state"), "unknown"),
            "apn_state": first_known(lte.get("apn_state"), "unknown"),
            "pdp_state": first_known(lte.get("pdp_state"), cell.get("pdp_state"), "unknown"),
            "assigned_ip": first_known(lte.get("assigned_ip"), "unknown"),
            "reason_code": first_known(lte_reason, "unknown"),
        },
        "wifi": {
            "scan_enabled": first_known(wifi.get("scan_enabled"), False if wifi.get("aps") == [] else None),
            "ap_count": first_known(
                wifi.get("ap_count"),
                len(wifi.get("aps")) if isinstance(wifi.get("aps"), list) else None,
            ),
            "source_status": first_known(wifi.get("source_status"), "unknown"),
            "evidence_status": first_known(wifi.get("evidence_status"), "unknown"),
            "privacy": wifi.get("privacy"),
            "reason": wifi.get("reason"),
        },
        "imu": {
            "motion": first_known(imu.get("motion"), imu.get("state")),
            "confidence": imu.get("confidence"),
            "source_status": first_known(imu.get("source_status"), "unknown"),
            "evidence_status": first_known(imu.get("evidence_status"), "unknown"),
            "hardware_present": imu.get("hardware_present"),
            "driver_enabled": imu.get("driver_enabled"),
            "data_is_mock": imu.get("data_is_mock"),
            "backend_status": imu.get("backend_status"),
            "reason": imu.get("reason"),
        },
        "location_belief": {
            "state": first_known(location_belief.get("state"), "unknown"),
            "radius_m": location_belief.get("radius_m"),
            "confidence": location_belief.get("confidence"),
            "source": location_belief.get("source") if isinstance(location_belief.get("source"), list) else [],
            "reason": first_known(location_belief.get("reason"), "no_location_belief"),
            "updated_at": first_known(
                location_belief.get("updated_at"),
                field_message.get("server_received_at"),
                latest_location_observation.get("server_received_at"),
            ),
        },
        "location_memory": {
            "state": first_known(location_memory.get("state"), "unknown"),
            "radius_m": location_memory.get("radius_m"),
            "confidence": location_memory.get("confidence"),
            "source": location_memory.get("source") if isinstance(location_memory.get("source"), list) else [],
            "reason": first_known(location_memory.get("reason"), "no_location_memory"),
            "updated_at": location_memory.get("updated_at"),
            "belief_updated_at": location_memory.get("belief_updated_at"),
            "last_test_run_id": location_memory.get("last_test_run_id"),
            "last_no_fix_at": dict_value(location_memory, "last_no_fix", "server_received_at"),
        },
        "explainability": {
            "state": "warning" if reason_codes else "ok",
            "reason_codes": reason_codes,
        },
    }


def load_key_release_manifests(root: Path = KEY_RELEASE_DIR) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    manifests: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        manifest["_manifest_path"] = relative_repo_path(path)
        manifests.append(manifest)
    manifests.sort(key=lambda item: (str(item.get("release_date") or ""), str(item.get("release_id") or "")))
    return manifests


def product_demo_unavailable(reason: str = "no_product_demo_report") -> dict[str, Any]:
    return {
        "available": False,
        "status": "not_available",
        "candidate": "KR-008 / DEMO-008 Product Demo Closed Loop",
        "reason": reason,
        "ready_for_kr008_release": False,
        "warnings": [reason],
        "flow": {},
        "flow_status_counts": {},
        "location": {},
        "paths": {},
        "next_step": "Generate a DEMO-008 product demo report before Web review.",
    }


def latest_product_demo_report_path(root: Path = DEFAULT_PRODUCT_DEMO_REPORTS) -> Path | None:
    if not root.exists():
        return None
    try:
        candidates = [path for path in root.glob("**/product_demo_report.json") if path.is_file()]
    except OSError:
        return None
    if not candidates:
        return None
    return max(candidates, key=lambda path: (path.stat().st_mtime, str(path)))


def load_latest_product_demo_report(root: Path = DEFAULT_PRODUCT_DEMO_REPORTS) -> dict[str, Any]:
    path = latest_product_demo_report_path(root)
    if path is None:
        return product_demo_unavailable()
    try:
        report = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return product_demo_unavailable("product_demo_report_unreadable")
    if not isinstance(report, dict):
        return product_demo_unavailable("product_demo_report_invalid")

    result = as_dict(report.get("result"))
    demo = as_dict(report.get("demo"))
    source = as_dict(report.get("source"))
    evidence = as_dict(report.get("evidence_summary"))
    paths = as_dict(report.get("paths"))
    flow = as_dict(report.get("flow"))
    summarized_flow = {
        step: compact_dict(
            {
                "status": as_dict(gate).get("status"),
                "summary": as_dict(gate).get("summary"),
                "warnings": as_dict(gate).get("warnings"),
                "next_step": as_dict(gate).get("next_step"),
            }
        )
        for step, gate in flow.items()
    }
    markdown_path = paths.get("product_demo_report_markdown")
    if not markdown_path:
        markdown_candidate = path.with_suffix(".md")
        markdown_path = relative_repo_path(markdown_candidate) if markdown_candidate.exists() else None
    return compact_dict(
        {
            "available": True,
            "status": result.get("status", "unknown"),
            "candidate": demo.get("candidate", "KR-008 / DEMO-008 Product Demo Closed Loop"),
            "mode": demo.get("mode"),
            "product_ready": demo.get("product_ready", False),
            "ready_for_kr008_release": result.get("ready_for_kr008_release", False),
            "why_not_release_ready": result.get("why_not_release_ready"),
            "warnings": result.get("warnings"),
            "errors": result.get("errors"),
            "test_run_id": source.get("test_run_id"),
            "safety_session_id": source.get("safety_session_id"),
            "evidence_mode": source.get("evidence_mode"),
            "dataset_samples": source.get("dataset_samples"),
            "location": report.get("location"),
            "flow": summarized_flow,
            "flow_order": report.get("flow_order"),
            "flow_status_counts": evidence.get("flow_status_counts"),
            "feature_groups": evidence.get("feature_groups"),
            "raw_frame_refs": evidence.get("raw_frame_refs"),
            "derived_event_refs": evidence.get("derived_event_refs"),
            "training_readiness": evidence.get("training_readiness"),
            "release_gate_usage": evidence.get("release_gate_usage"),
            "report_path": relative_repo_path(path),
            "markdown_path": markdown_path,
            "paths": {
                key: value
                for key, value in paths.items()
                if key
                in {
                    "product_demo_report_json",
                    "product_demo_report_markdown",
                    "dataset_samples",
                    "dataset_manifest",
                    "eale_report_json",
                    "eale_report_markdown",
                }
            },
            "next_gates": report.get("next_gates"),
            "non_claims": report.get("non_claims"),
        }
    )


def relative_repo_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def key_release_summary(manifest: dict[str, Any] | None) -> dict[str, Any]:
    if not manifest:
        return {}
    return compact_dict(
        {
            "release_id": manifest.get("release_id"),
            "release_name": manifest.get("release_name"),
            "release_version": manifest.get("release_version"),
            "status": manifest.get("status"),
            "release_date": manifest.get("release_date"),
            "firmware_version": manifest.get("firmware_version"),
            "firmware_test_run_id": manifest.get("firmware_test_run_id"),
            "manifest_path": manifest.get("_manifest_path"),
        }
    )


def latest_released_manifest(manifests: list[dict[str, Any]]) -> dict[str, Any] | None:
    released = [item for item in manifests if item.get("status") == "released"]
    if released:
        return released[-1]
    return manifests[-1] if manifests else None


def resolve_key_release_context(
    test_run_id: Any,
    fw_version: Any,
    *,
    manifests: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    manifest_list = manifests if manifests is not None else load_key_release_manifests()
    test_run_text = str(test_run_id or "")
    fw_text = str(fw_version or "")
    for manifest in manifest_list:
        if test_run_text and str(manifest.get("firmware_test_run_id") or "") == test_run_text:
            return {
                "match": "firmware_test_run_id",
                **key_release_summary(manifest),
            }
    for manifest in manifest_list:
        if fw_text and str(manifest.get("firmware_version") or "") == fw_text:
            return {
                "match": "firmware_version",
                **key_release_summary(manifest),
            }
    baseline = key_release_summary(latest_released_manifest(manifest_list))
    return {
        "release_id": "unreleased",
        "release_name": "Unreleased run",
        "release_version": None,
        "status": "unreleased_run" if manifest_list else "unknown",
        "match": "none" if manifest_list else "manifest_unavailable",
        "baseline": baseline,
    }


def newest_record(items: list[dict[str, Any]], *timestamp_keys: str) -> dict[str, Any]:
    newest: dict[str, Any] = {}
    newest_ts: datetime | None = None
    for index, item in enumerate(items):
        timestamp_value = first_known(*(item.get(key) for key in timestamp_keys))
        parsed = parse_iso_timestamp(timestamp_value)
        if parsed is None:
            parsed = datetime.fromtimestamp(index, tz=timezone.utc)
        if newest_ts is None or parsed >= newest_ts:
            newest = item
            newest_ts = parsed
    return newest


def command_test_run_id(command: dict[str, Any]) -> Any:
    ack = as_dict(command.get("ack"))
    return first_known(
        command.get("test_run_id"),
        dict_value(command, "payload", "test_run_id"),
        ack.get("test_run_id"),
        dict_value(ack, "payload", "test_run_id"),
    )


def command_matches_test_run(command: dict[str, Any], test_run_id: Any) -> bool:
    if not test_run_id:
        return True
    test_run_text = str(test_run_id)
    ack = as_dict(command.get("ack"))
    candidates = [
        command.get("test_run_id"),
        dict_value(command, "payload", "test_run_id"),
        ack.get("test_run_id"),
        dict_value(ack, "payload", "test_run_id"),
    ]
    return test_run_text in {str(value) for value in candidates if value not in (None, "")}


def raw_frame_test_run_id(raw_frame: dict[str, Any]) -> Any:
    derived = as_dict(dict_value(raw_frame, "parse_result", "derived_message"))
    return first_known(raw_frame.get("test_run_id"), derived.get("test_run_id"))


def raw_frame_matches_test_run(raw_frame: dict[str, Any], test_run_id: Any) -> bool:
    if not test_run_id:
        return True
    return str(raw_frame_test_run_id(raw_frame) or "") == str(test_run_id)


def message_matches_test_run(message: dict[str, Any], test_run_id: Any) -> bool:
    if not test_run_id:
        return True
    return str(message.get("test_run_id") or "") == str(test_run_id)


def raw_frame_parse_status(raw_frame: dict[str, Any]) -> str:
    return str(first_known(dict_value(raw_frame, "parse_result", "status"), raw_frame.get("parse_status"), "unknown"))


def raw_frame_derived_type(raw_frame: dict[str, Any]) -> str:
    return str(first_known(dict_value(raw_frame, "parse_result", "derived_message_type"), raw_frame.get("derived_message_type"), "unknown"))


def raw_frame_type(raw_frame: dict[str, Any]) -> str:
    return str(first_known(dict_value(raw_frame, "framing", "frame_type"), raw_frame.get("frame_type"), "unknown"))


def raw_frame_problem(raw_frames: list[dict[str, Any]]) -> dict[str, Any]:
    problems = [
        raw_frame
        for raw_frame in raw_frames
        if raw_frame_parse_status(raw_frame) not in {"ok", "not_attempted", "unknown"}
    ]
    return newest_record(problems, "server_received_at") if problems else {}


def unique_text(values: list[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value in (None, "", "none", "unknown"):
            continue
        text = str(value)
        if text not in result:
            result.append(text)
    return result


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def confidence_bucket(value: Any) -> str:
    score = as_number(value)
    if score is None:
        return "unknown"
    if score >= 0.75:
        return "high"
    if score >= 0.45:
        return "medium"
    if score > 0:
        return "low"
    return "unknown"


def eale_source_status(value: Any) -> str:
    text = str(value or "unknown").strip().lower()
    return text or "unknown"


def eale_evidence_status(payload: dict[str, Any], source_status: str, present: bool) -> str:
    explicit = str(payload.get("evidence_status") or "").strip().lower()
    if explicit:
        return explicit
    if not present:
        return "missing"
    if source_status in {"disabled", "missing", "unknown"}:
        return "missing"
    if source_status in {"failed", "error"}:
        return "failed"
    if source_status in {"partial"}:
        return "partial"
    return "ok"


def eale_source_evidence(
    source: str,
    payload: dict[str, Any],
    *,
    present: bool | None = None,
    source_status: Any = None,
    server_received_at: Any = None,
    raw_frame_refs: list[dict[str, Any]] | None = None,
    derived_event_refs: list[dict[str, Any]] | None = None,
    privacy_class: str = "engineering",
) -> dict[str, Any]:
    status = eale_source_status(first_known(source_status, payload.get("source_status")))
    has_payload = present if present is not None else bool(payload)
    evidence_status = eale_evidence_status(payload, status, has_payload)
    return {
        "source": source,
        "present": bool(has_payload),
        "source_status": status,
        "evidence_status": evidence_status,
        "server_received_at": server_received_at,
        "raw_frame_refs": raw_frame_refs or [],
        "derived_event_refs": derived_event_refs or [],
        "quality_flags": [],
        "privacy_class": privacy_class,
        "redaction_state": "hashed" if source == "wifi" else "none",
    }


def eale_raw_frame_ref(raw_frame: dict[str, Any]) -> dict[str, Any]:
    raw_payload = as_dict(raw_frame.get("raw_payload"))
    framing = as_dict(raw_frame.get("framing"))
    parse = as_dict(raw_frame.get("parse_result"))
    derived = as_dict(parse.get("derived_message"))
    return compact_dict(
        {
            "frame_id": raw_frame.get("frame_id"),
            "direction": raw_frame.get("direction"),
            "device_id": first_known(raw_frame.get("device_id"), derived.get("device_id")),
            "test_run_id": first_known(raw_frame.get("test_run_id"), derived.get("test_run_id")),
            "cmd_id": first_known(raw_frame.get("cmd_id"), derived.get("cmd_id"), derived.get("location_request_cmd_id")),
            "seq": first_known(raw_frame.get("seq"), derived.get("seq")),
            "fw_version": first_known(raw_frame.get("fw_version"), derived.get("fw_version")),
            "frame_type": raw_frame_type(raw_frame),
            "server_received_at": raw_frame.get("server_received_at"),
            "byte_len": raw_payload.get("byte_len"),
            "sha256": raw_payload.get("sha256"),
            "crc32": first_known(raw_payload.get("crc32"), framing.get("payload_crc32")),
            "parse_status": raw_frame_parse_status(raw_frame),
            "parser_version": parse.get("parser_version"),
            "derived_message_type": raw_frame_derived_type(raw_frame),
        }
    )


def eale_derived_event_ref(message: dict[str, Any]) -> dict[str, Any]:
    return compact_dict(
        {
            "message_type": message.get("message_type"),
            "event_type": message.get("event_type"),
            "cmd_id": first_known(message.get("location_request_cmd_id"), message.get("cmd_id")),
            "frame_id": dict_value(message, "raw_frame", "frame_id"),
            "seq": message.get("seq"),
            "server_received_at": message.get("server_received_at"),
            "fw_version": message.get("fw_version"),
            "test_run_id": message.get("test_run_id"),
            "source": message.get("source"),
            "source_status": message.get("source_status"),
        }
    )


def eale_lineage_quality(raw_refs: list[dict[str, Any]], derived_refs: list[dict[str, Any]], anchor_cmd_id: Any, seq: Any) -> float:
    if raw_refs and derived_refs and anchor_cmd_id and seq is not None:
        return 1.0
    if derived_refs and anchor_cmd_id:
        return 0.7
    if raw_refs or derived_refs:
        return 0.4
    return 0.0


def eale_gnss_quality(report: dict[str, Any], lineage_quality: float, quality_flags: list[str]) -> tuple[float, float]:
    hdop = as_number(first_known(report.get("hdop"), dict_value(report, "gnss", "hdop")))
    satellites = as_number(first_known(report.get("satellites"), dict_value(report, "gnss", "satellites")))
    if hdop is None:
        hdop_score = 0.45
        quality_flags.append("gnss_hdop_missing")
    else:
        hdop_score = clamp((8.0 - hdop) / 7.0, 0.0, 1.0)
    if satellites is None:
        satellite_score = 0.45
        quality_flags.append("gnss_satellites_missing")
    else:
        satellite_score = clamp((satellites - 4.0) / 8.0, 0.0, 1.0)
    source_status = eale_source_status(report.get("source_status"))
    source_score = 1.0 if source_status in {"verified", "observed", "pc_side_verified"} else 0.5
    score = clamp(hdop_score * satellite_score * source_score * lineage_quality, 0.0, 1.0)
    radius = max(25.0, (hdop or 8.0) * 8.0)
    return round(score, 3), round(radius, 1)


def eale_latest_event(messages: list[dict[str, Any]], event_type: str) -> dict[str, Any]:
    matches = [
        message
        for message in messages
        if message.get("message_type") == "event" and message.get("event_type") == event_type
    ]
    return newest_record(matches, "server_received_at", "ts") if matches else {}


def eale_dataset_window_status(
    *,
    command: dict[str, Any],
    report: dict[str, Any],
    observation: dict[str, Any],
    raw_refs: list[dict[str, Any]],
    derived_refs: list[dict[str, Any]],
    failure_reason: Any,
    quality_flags: list[str],
) -> dict[str, Any]:
    has_location_command = command.get("cmd") == "request_location" or bool(first_known(report.get("location_request_cmd_id"), observation.get("location_request_cmd_id")))
    if report.get("fix") is True:
        sample_type = "known_place_calibration_window"
    elif failure_reason and str(failure_reason) not in {"none", "unknown"}:
        sample_type = "failure_window"
    elif has_location_command:
        sample_type = "location_request_window"
    else:
        sample_type = "passive_observation_window"

    blockers: list[str] = []
    warnings: list[str] = []
    if not raw_refs:
        warnings.append("missing_raw_frame_lineage")
    if not derived_refs:
        blockers.append("missing_derived_location_event")
    if command and command.get("status") == "pending":
        warnings.append("command_pending")
    if quality_flags:
        warnings.extend(quality_flags)
    status = "blocked" if blockers else ("candidate_with_warnings" if warnings else "candidate")
    return {
        "status": status,
        "sample_type": sample_type,
        "raw_frame_count": len(raw_refs),
        "derived_event_count": len(derived_refs),
        "training_allowed": False,
        "training_reason": "training_requires_explicit_privacy_and_label_policy",
        "blockers": unique_text(blockers),
        "warnings": unique_text(warnings),
    }


def build_eale_p0_location_belief(
    messages: list[dict[str, Any]],
    commands: list[dict[str, Any]],
    raw_frames: list[dict[str, Any]],
    latest_observability: dict[str, Any],
    failure_summary: dict[str, Any],
) -> dict[str, Any]:
    report = eale_latest_event(messages, "location_report")
    observation = eale_latest_event(messages, "location_observation")
    anchor = observation or report
    command = newest_record(commands, "updated_at", "created_at") if commands else {}
    raw_refs = [eale_raw_frame_ref(raw_frame) for raw_frame in raw_frames]
    derived_refs = [eale_derived_event_ref(message) for message in messages if message.get("message_type") == "event" and message.get("event_type") in {"location_report", "location_observation"}]
    anchor_cmd_id = first_known(
        observation.get("location_request_cmd_id"),
        report.get("location_request_cmd_id"),
        command.get("cmd_id"),
    )
    anchor_seq = first_known(observation.get("seq"), report.get("seq"))
    lineage_quality = eale_lineage_quality(raw_refs, derived_refs, anchor_cmd_id, anchor_seq)
    location_memory = as_dict(latest_observability.get("location_memory"))

    gnss = as_dict(first_known(report.get("gnss"), {}))
    cell = as_dict(first_known(observation.get("cell"), report.get("cell")))
    lte = as_dict(first_known(observation.get("lte"), report.get("lte")))
    wifi = as_dict(first_known(observation.get("wifi"), report.get("wifi")))
    imu = as_dict(first_known(observation.get("imu"), report.get("imu")))
    power = as_dict(first_known(observation.get("power"), report.get("power")))
    transport = as_dict(first_known(observation.get("transport"), report.get("transport"), dict_value(command, "ack", "transport")))
    runtime = as_dict(first_known(observation.get("runtime"), report.get("runtime")))

    evidence = {
        "gnss": eale_source_evidence(
            "gnss",
            gnss or report,
            present=bool(report),
            source_status=report.get("source_status"),
            server_received_at=report.get("server_received_at"),
            raw_frame_refs=raw_refs,
            derived_event_refs=[ref for ref in derived_refs if ref.get("event_type") == "location_report"],
            privacy_class="private_location" if report.get("lat") is not None or report.get("lon") is not None else "engineering",
        ),
        "cell_lte": eale_source_evidence(
            "cell_lte",
            {**cell, **lte},
            present=bool(cell or lte),
            source_status=first_known(cell.get("source_status"), lte.get("source_status"), "observed" if cell or lte else None),
            server_received_at=observation.get("server_received_at"),
            raw_frame_refs=raw_refs,
            derived_event_refs=[ref for ref in derived_refs if ref.get("event_type") == "location_observation"],
        ),
        "wifi": eale_source_evidence("wifi", wifi, present=bool(wifi), server_received_at=observation.get("server_received_at")),
        "imu": eale_source_evidence("imu", imu, present=bool(imu), server_received_at=observation.get("server_received_at")),
        "power": eale_source_evidence("power", power, present=bool(power), server_received_at=observation.get("server_received_at")),
        "transport": eale_source_evidence("transport", transport, present=bool(transport), source_status=transport.get("type"), server_received_at=anchor.get("server_received_at")),
        "runtime": eale_source_evidence("runtime", runtime, present=bool(runtime), server_received_at=anchor.get("server_received_at")),
        "memory": eale_source_evidence("memory", location_memory, present=bool(location_memory), source_status=location_memory.get("state"), server_received_at=location_memory.get("updated_at")),
    }

    quality_flags: list[str] = []
    for name, payload in (("wifi", wifi), ("imu", imu), ("power", power)):
        source_status = eale_source_status(payload.get("source_status"))
        evidence_status = eale_evidence_status(payload, source_status, bool(payload))
        if evidence_status == "missing":
            quality_flags.append(f"{name}_{source_status if source_status != 'unknown' else 'missing'}")
        elif source_status in {"unverified", "mock"}:
            quality_flags.append(f"{name}_{source_status}")
        elif evidence_status in {"failed", "partial"}:
            quality_flags.append(f"{name}_{evidence_status}")
    if cell or lte:
        quality_flags.append("cell_lte_not_position_source")
    if lineage_quality < 1.0:
        quality_flags.append("partial_lineage")

    fix = first_known(report.get("fix"), gnss.get("fix"))
    source_status = eale_source_status(report.get("source_status"))
    failure_reason = failure_summary.get("reason") if failure_summary.get("state") != "ok" else None
    state = "Unknown"
    substate = "no_precise_fix"
    source: list[str] = []
    radius_m: float | None = None
    confidence: float | None = None
    reason = "no_location_evidence"

    if fix is True and report.get("lat") is not None and report.get("lon") is not None:
        if source_status in {"verified", "observed", "pc_side_verified"}:
            confidence, radius_m = eale_gnss_quality(report, lineage_quality, quality_flags)
            state = "Fine"
            substate = "gnss_fix"
            source = ["gnss"]
            reason = "gnss_fix_valid"
            failure_reason = None
        else:
            confidence = 0.2
            state = "Unknown"
            substate = "failure"
            source = ["gnss"]
            reason = "gnss_fix_untrusted_source"
            failure_reason = "gnss_fix_untrusted_source"
            quality_flags.append("gnss_source_untrusted")
    elif has_predictable_location_memory(location_memory) and fix is False:
        memory_confidence = as_number(location_memory.get("confidence"))
        confidence = round(memory_confidence * 0.55, 3) if memory_confidence is not None else 0.35
        radius_m = as_number(location_memory.get("radius_m"))
        state = "Predicted"
        substate = "last_known_hold"
        source = merge_sources(location_memory.get("source"), "memory")
        reason = "last_known_after_gnss_no_fix"
        quality_flags.append("gnss_no_fix")
    elif report and fix is False and (cell or lte):
        confidence = 0.2
        state = "Unknown"
        substate = "no_precise_fix"
        source = ["gnss", "cell_lte"]
        reason = "gnss_no_fix_cell_lte_observed_no_position_memory"
        quality_flags.append("gnss_no_fix")
    elif report and fix is False:
        confidence = 0.1
        state = "Unknown"
        substate = "failure"
        source = ["gnss"]
        reason = "gnss_no_fix"
        quality_flags.append("gnss_no_fix")
    elif command and not report:
        confidence = 0.0
        state = "Unknown"
        substate = "failure"
        source = ["runtime"]
        reason = "missing_location_report_after_command"
        failure_reason = first_known(failure_reason, "missing_location_report")
        quality_flags.append("missing_location_report")
    elif cell or lte:
        confidence = 0.15
        state = "Unknown"
        substate = "no_precise_fix"
        source = ["cell_lte"]
        reason = "cell_lte_observed_without_position_memory"
    else:
        confidence = None
        failure_reason = first_known(failure_reason, "no_runtime_evidence")

    quality_flags = unique_text(quality_flags)
    dataset_window = eale_dataset_window_status(
        command=command,
        report=report,
        observation=observation,
        raw_refs=raw_refs,
        derived_refs=derived_refs,
        failure_reason=failure_reason,
        quality_flags=quality_flags,
    )

    return {
        "location_belief": {
            "state": state,
            "substate": substate,
            "source": source,
            "lat": None,
            "lon": None,
            "place_id": None,
            "radius_m": radius_m,
            "confidence": confidence,
            "confidence_bucket": confidence_bucket(confidence),
            "freshness_s": None,
            "reason": reason,
            "failure_reason": failure_reason,
            "quality_flags": quality_flags,
            "evidence_refs": {
                "raw_frame_refs": raw_refs,
                "derived_event_refs": derived_refs,
                "anchor_cmd_id": anchor_cmd_id,
                "anchor_event_id": first_known(dict_value(observation, "raw_frame", "frame_id"), dict_value(report, "raw_frame", "frame_id")),
            },
            "privacy": {
                "privacy_class": "private_location" if report.get("lat") is not None or report.get("lon") is not None else "engineering",
                "redaction_state": "bounded_export_only" if report.get("lat") is not None or report.get("lon") is not None else "none",
                "training_allowed": False,
            },
            "generator": {
                "name": EALE_P0_GENERATOR_NAME,
                "version": EALE_P0_GENERATOR_VERSION,
                "config_hash": None,
            },
        },
        "evidence": evidence,
        "dataset_window": dataset_window,
    }


def build_failure_summary(
    messages: list[dict[str, Any]],
    commands: list[dict[str, Any]],
    raw_frames: list[dict[str, Any]],
    latest_observability: dict[str, Any],
) -> dict[str, Any]:
    reason_codes: list[str] = []
    for message in messages:
        if message.get("error_code"):
            reason_codes = unique_text(reason_codes + [message.get("error_code")])
        if message.get("message_type") == "event" and message.get("event_type") in {"location_report", "location_observation"}:
            gnss = as_dict(message.get("gnss"))
            gnss_reason = build_gnss_reason(
                first_known(message.get("fix"), gnss.get("fix")),
                first_known(message.get("gnss_state"), gnss.get("state"), gnss.get("result")),
                message.get("error_code"),
                message,
            )
            if gnss_reason not in {"GNSS_FIX", "GNSS_UNKNOWN"}:
                reason_codes = unique_text(reason_codes + [gnss_reason])
    reason_codes = unique_text(reason_codes + list(as_dict(latest_observability.get("explainability")).get("reason_codes") or []))

    problem_frame = raw_frame_problem(raw_frames)
    if problem_frame:
        parse = as_dict(problem_frame.get("parse_result"))
        code = first_known(parse.get("error_code"), raw_frame_parse_status(problem_frame))
        return {
            "state": "failure",
            "reason": "raw_frame_parse_failed",
            "reason_codes": unique_text([code] + reason_codes),
            "evidence": {
                "frame_id": problem_frame.get("frame_id"),
                "parse_status": raw_frame_parse_status(problem_frame),
                "parse_error_code": parse.get("error_code"),
                "parse_reason": parse.get("reason"),
            },
        }

    pending = [command for command in commands if command.get("status") == "pending"]
    if pending:
        command = newest_record(pending, "updated_at", "created_at")
        return {
            "state": "pending",
            "reason": "command_pending_ack_missing",
            "reason_codes": unique_text(["COMMAND_PENDING_ACK_MISSING"] + reason_codes),
            "evidence": {
                "cmd_id": command.get("cmd_id"),
                "cmd": command.get("cmd"),
                "created_at": command.get("created_at"),
                "updated_at": command.get("updated_at"),
            },
        }

    if not messages and not raw_frames:
        return {
            "state": "unknown",
            "reason": "no_runtime_evidence",
            "reason_codes": ["NO_RUNTIME_EVIDENCE"],
            "evidence": {},
        }

    if reason_codes:
        return {
            "state": "warning",
            "reason": reason_codes[0],
            "reason_codes": reason_codes,
            "evidence": {},
        }

    return {
        "state": "ok",
        "reason": "none",
        "reason_codes": [],
        "evidence": {},
    }


def build_run_context(
    *,
    messages: list[dict[str, Any]],
    commands: list[dict[str, Any]],
    raw_frames: list[dict[str, Any]],
    devices: list[dict[str, Any]] | None = None,
    test_run: dict[str, Any] | None = None,
    test_runs: list[dict[str, Any]] | None = None,
    latest_observability: dict[str, Any] | None = None,
) -> dict[str, Any]:
    devices = devices or []
    test_run = test_run or {}
    test_runs = test_runs or []
    latest_device = newest_record(devices, "last_seen_at") if devices else {}
    latest_message = newest_record(messages, "server_received_at", "ts") if messages else {}
    latest_command = newest_record(commands, "updated_at", "created_at") if commands else {}
    latest_raw = newest_record(raw_frames, "server_received_at") if raw_frames else {}
    location_messages = [
        message
        for message in messages
        if message.get("message_type") == "event" and message.get("event_type") in {"location_observation", "location_report"}
    ]
    latest_location = newest_record(location_messages, "server_received_at", "ts") if location_messages else {}
    latest_observability = as_dict(latest_observability or latest_device.get("observability"))

    test_run_id = first_known(
        test_run.get("test_run_id"),
        latest_location.get("test_run_id"),
        latest_message.get("test_run_id"),
        command_test_run_id(latest_command),
        raw_frame_test_run_id(latest_raw),
        dict_value(latest_observability, "location_memory", "last_test_run_id"),
    )
    if not test_run and test_run_id:
        for candidate in test_runs:
            if str(candidate.get("test_run_id") or "") == str(test_run_id):
                test_run = candidate
                break

    context_messages = [message for message in messages if message_matches_test_run(message, test_run_id)]
    context_commands = [command for command in commands if command_matches_test_run(command, test_run_id)]
    context_raw_frames = [raw_frame for raw_frame in raw_frames if raw_frame_matches_test_run(raw_frame, test_run_id)]
    if context_messages:
        latest_message = newest_record(context_messages, "server_received_at", "ts")
        location_messages = [
            message
            for message in context_messages
            if message.get("message_type") == "event"
            and message.get("event_type") in {"location_observation", "location_report"}
        ]
        latest_location = newest_record(location_messages, "server_received_at", "ts") if location_messages else {}
    if context_commands:
        latest_command = newest_record(context_commands, "updated_at", "created_at")
    if context_raw_frames:
        latest_raw = newest_record(context_raw_frames, "server_received_at")

    fw_version = first_known(
        latest_location.get("fw_version"),
        latest_message.get("fw_version"),
        latest_raw.get("fw_version"),
        latest_device.get("fw_version"),
        dict_value(latest_command, "ack", "fw_version"),
    )
    command_ack = as_dict(latest_command.get("ack"))
    location_belief = as_dict(latest_observability.get("location_belief"))
    reliability = as_dict(latest_observability.get("reliability"))
    raw_parse = as_dict(latest_raw.get("parse_result"))
    key_release = resolve_key_release_context(test_run_id, fw_version)
    failure = build_failure_summary(context_messages, context_commands, context_raw_frames, latest_observability)
    eale_p0 = build_eale_p0_location_belief(
        context_messages,
        context_commands,
        context_raw_frames,
        latest_observability,
        failure,
    )

    return {
        "test_run_id": first_known(test_run_id, "unknown"),
        "test_run_status": first_known(test_run.get("status"), "unknown"),
        "device_id": first_known(latest_device.get("device_id"), latest_message.get("device_id"), latest_raw.get("device_id"), "unknown"),
        "fw_version": first_known(fw_version, "unknown"),
        "last_seen_at": first_known(latest_device.get("last_seen_at"), latest_message.get("server_received_at"), latest_raw.get("server_received_at")),
        "key_release": key_release,
        "command": {
            "cmd_id": latest_command.get("cmd_id"),
            "cmd": latest_command.get("cmd"),
            "status": latest_command.get("status"),
            "ack_status": command_ack.get("status"),
            "ack_transport": dict_value(command_ack, "transport", "type"),
            "ack_test_run_id": command_ack.get("test_run_id"),
        },
        "raw_frame": {
            "frame_id": latest_raw.get("frame_id"),
            "direction": latest_raw.get("direction"),
            "frame_type": raw_frame_type(latest_raw),
            "parse_status": raw_frame_parse_status(latest_raw),
            "derived_message_type": raw_frame_derived_type(latest_raw),
            "parse_reason": first_known(raw_parse.get("reason"), raw_parse.get("error_code")),
        },
        "location": {
            "event_type": latest_location.get("event_type"),
            "seq": latest_location.get("seq"),
            "fix": first_known(latest_location.get("fix"), dict_value(latest_location, "gnss", "fix")),
            "gnss_state": first_known(latest_location.get("gnss_state"), dict_value(latest_location, "gnss", "state")),
            "location_request_cmd_id": latest_location.get("location_request_cmd_id"),
            "belief_state": location_belief.get("state"),
            "belief_reason": location_belief.get("reason"),
        },
        "failure": failure,
        "reliability": reliability,
        "eale_p0": eale_p0,
        "evidence_counts": {
            "messages": len(context_messages),
            "commands": len(context_commands),
            "raw_frames": len(context_raw_frames),
        },
    }


def summarize_test_run_observability(
    messages: list[dict[str, Any]],
    commands: list[dict[str, Any]],
    raw_frames: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    raw_frame_list = raw_frames or []
    if not messages:
        failure_summary = build_failure_summary([], commands, raw_frame_list, {})
        eale_summary = build_eale_p0_location_belief([], commands, raw_frame_list, {}, failure_summary)
        return {
            "message_count": 0,
            "latest_observability": None,
            "reason_codes": failure_summary["reason_codes"],
            "failure_summary": failure_summary,
            "eale_p0": eale_summary,
        }
    latest = messages[-1]
    device = {
        "device_id": latest.get("device_id"),
        "fw_version": latest.get("fw_version") or "unknown",
        "last_seen_at": latest.get("server_received_at"),
        "last_message_type": latest.get("message_type"),
        "last_seq": latest.get("seq"),
        "last_status": latest_message(messages, message_type="status"),
        "latest_telemetry": latest_message(messages, message_type="event"),
        "latest_location": latest_location_message(messages),
        "latest_location_observation": latest_message(messages, message_type="event", event_type="location_observation"),
        "location_memory": summarize_location_memory(messages),
        "last_error": latest_message(messages, message_type="error"),
    }
    latest_observability = build_observability(device, commands[-1] if commands else None)
    reason_codes: list[str] = []
    for message in messages:
        error_code = message.get("error_code")
        if error_code and error_code not in reason_codes:
            reason_codes.append(str(error_code))
    for code in latest_observability["explainability"]["reason_codes"]:
        if code not in reason_codes:
            reason_codes.append(code)
    failure_summary = build_failure_summary(messages, commands, raw_frame_list, latest_observability)
    return {
        "message_count": len(messages),
        "command_count": len(commands),
        "latest_observability": latest_observability,
        "reason_codes": reason_codes,
        "failure_summary": failure_summary,
        "eale_p0": build_eale_p0_location_belief(
            messages,
            commands,
            raw_frame_list,
            latest_observability,
            failure_summary,
        ),
    }


def render_dashboard() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Ego Link Message Hub</title>
  <style>
    body { margin: 0; font-family: Segoe UI, Arial, sans-serif; background: #f6f7f9; color: #17202a; }
    header { padding: 14px 20px; background: #fff; border-bottom: 1px solid #d8dde6; display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
    h1 { margin: 0; font-size: 22px; letter-spacing: 0; }
    .auth { display: flex; align-items: center; gap: 8px; }
    input { width: min(360px, 56vw); padding: 8px 10px; border: 1px solid #c8d0dc; border-radius: 6px; font: inherit; }
    button { padding: 8px 12px; border: 1px solid #1f6feb; border-radius: 6px; background: #1f6feb; color: #fff; font: inherit; cursor: pointer; }
    #authStatus { min-width: 92px; color: #667085; font-size: 13px; }
    main { padding: 16px; display: grid; grid-template-columns: 380px 1fr; gap: 16px; }
    .stack { display: grid; gap: 16px; }
    section { background: #fff; border: 1px solid #d8dde6; border-radius: 8px; padding: 14px; }
    h2 { margin: 0 0 10px; font-size: 16px; letter-spacing: 0; }
    .metric { display: grid; grid-template-columns: 132px 1fr; gap: 8px; padding: 7px 0; border-bottom: 1px solid #edf0f5; font-size: 14px; }
    .metric span:first-child { color: #667085; }
    .ok { color: #0f766e; font-weight: 600; }
    .warn { color: #b45309; font-weight: 600; }
    .bad { color: #c2410c; font-weight: 600; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { text-align: left; padding: 8px; border-bottom: 1px solid #edf0f5; vertical-align: top; }
    th { color: #667085; }
    .empty { color: #667085; }
    .map-surface { min-height: 150px; border: 1px solid #c8d0dc; border-radius: 8px; background: #eef2f6; position: relative; display: grid; place-items: center; margin-bottom: 10px; overflow: hidden; }
    .map-grid { position: absolute; inset: 0; background-image: linear-gradient(#d9e0ea 1px, transparent 1px), linear-gradient(90deg, #d9e0ea 1px, transparent 1px); background-size: 28px 28px; }
    .map-dot { width: 14px; height: 14px; border-radius: 50%; background: #1f6feb; border: 3px solid #fff; box-shadow: 0 0 0 2px #1f6feb; z-index: 1; }
    .map-caption { position: absolute; left: 10px; right: 10px; bottom: 8px; z-index: 1; color: #344054; font-size: 12px; text-align: center; background: rgba(255, 255, 255, 0.82); border: 1px solid #d8dde6; border-radius: 6px; padding: 4px 6px; }
    @media (max-width: 800px) { main { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <header>
    <h1>Ego Link Message Hub</h1>
    <div class="auth">
      <input id="tokenInput" type="password" autocomplete="off" placeholder="Bearer token" />
      <button id="saveToken" type="button">Save</button>
      <span id="authStatus"></span>
    </div>
  </header>
  <main>
    <div class="stack">
      <section>
        <h2>Devices</h2>
        <div id="devices"></div>
      </section>
      <section>
        <h2>Run Context</h2>
        <div id="runContext"></div>
      </section>
      <section>
        <h2>Commands</h2>
        <div id="commands"></div>
      </section>
      <section>
        <h2>Raw Frames</h2>
        <div id="rawFrames"></div>
      </section>
    </div>
    <div class="stack">
      <section>
        <h2>Product Demo</h2>
        <div id="productDemo"></div>
      </section>
      <section>
        <h2>D1 Link Through</h2>
        <div id="d1Link"></div>
      </section>
      <section>
        <h2>Latest Field State</h2>
        <div id="fieldState"></div>
      </section>
      <section>
        <h2>Recent Messages</h2>
        <table><thead><tr><th>Device</th><th>Type</th><th>Seq</th><th>Detail</th><th>Received</th></tr></thead><tbody id="messages"></tbody></table>
      </section>
    </div>
  </main>
  <script>
    function escapeHtml(value) {
      return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
    }
    function detail(message) {
      return message.event_type || message.cmd_id || message.error_code || message.link_type || message.status || '';
    }
    function ageClass(lastSeen) {
      if (!lastSeen) return 'bad';
      const ageMs = Date.now() - Date.parse(lastSeen);
      if (!Number.isFinite(ageMs)) return 'warn';
      if (ageMs < 30000) return 'ok';
      if (ageMs < 120000) return 'warn';
      return 'bad';
    }
    function onlineLabel(lastSeen) {
      const cls = ageClass(lastSeen);
      if (cls === 'ok') return 'online';
      if (cls === 'warn') return 'stale';
      return 'offline';
    }
    function gnssField(telemetry, key, fallback = 'unknown') {
      const nested = telemetry.gnss || (telemetry.payload && telemetry.payload.gnss ? telemetry.payload.gnss : {});
      const alias = key === 'gnss_state' ? (nested.state ?? nested.result) : undefined;
      const value = telemetry[key] ?? nested[key] ?? alias;
      return value === undefined || value === null || value === '' ? fallback : value;
    }
    function currentToken() {
      return localStorage.getItem('egolinkHubToken') || '';
    }
    function authHeaders() {
      const token = currentToken();
      return token ? { Authorization: `Bearer ${token}` } : {};
    }
    function showStateMessage(message) {
      const html = `<span class="empty">${escapeHtml(message)}</span>`;
      devices.innerHTML = html;
      runContext.innerHTML = html;
      commands.innerHTML = html;
      rawFrames.innerHTML = html;
      productDemo.innerHTML = html;
      d1Link.innerHTML = html;
      fieldState.innerHTML = html;
      messages.innerHTML = `<tr><td colspan="5" class="empty">${escapeHtml(message)}</td></tr>`;
    }
    tokenInput.value = currentToken();
    saveToken.addEventListener('click', () => {
      localStorage.setItem('egolinkHubToken', tokenInput.value.trim());
      refresh();
    });
    function parseResult(rawFrame) {
      return rawFrame.parse_result || {};
    }
    function framing(rawFrame) {
      return rawFrame.framing || {};
    }
    function rawFrameStatus(rawFrame) {
      return parseResult(rawFrame).status || rawFrame.parse_status || 'unknown';
    }
    function rawFrameClass(rawFrame) {
      const status = rawFrameStatus(rawFrame);
      if (status === 'ok') return 'ok';
      if (status === 'partial' || status === 'not_attempted') return 'warn';
      return 'bad';
    }
    function rawFrameSummary(rawFrame) {
      const parsed = parseResult(rawFrame);
      const frame = framing(rawFrame);
      return `${rawFrame.direction || 'unknown'} ${frame.frame_type || rawFrame.frame_type || 'raw'} / ${rawFrameStatus(rawFrame)} / ${parsed.derived_message_type || 'unknown'}`;
    }
    function latestRawFrameForDevice(rawFrames, deviceId) {
      return (rawFrames || []).find(frame => frame.device_id === deviceId) || {};
    }
    function releaseLabel(release) {
      if (!release || !release.release_id) return 'unknown';
      const version = release.release_version ? ` / ${release.release_version}` : '';
      const match = release.match ? ` / ${release.match}` : '';
      return `${release.release_id}${version}${match}`;
    }
    function runContextPanel(run) {
      const release = run.key_release || {};
      const baseline = release.baseline || {};
      const command = run.command || {};
      const rawFrame = run.raw_frame || {};
      const location = run.location || {};
      const failure = run.failure || {};
      const reliability = run.reliability || {};
      const relNetwork = reliability.network || {};
      const relCache = reliability.cache || {};
      const eale = run.eale_p0 || {};
      const ealeBelief = eale.location_belief || {};
      const ealeDataset = eale.dataset_window || {};
      const counts = run.evidence_counts || {};
      return `
        <div class="metric"><span>Current Run</span><b>${escapeHtml(run.test_run_id || 'unknown')}</b></div>
        <div class="metric"><span>Key Release</span><span>${escapeHtml(releaseLabel(release))}</span></div>
        <div class="metric"><span>Baseline</span><span>${escapeHtml(baseline.release_id || 'none')} ${escapeHtml(baseline.release_version || '')}</span></div>
        <div class="metric"><span>Firmware</span><span>${escapeHtml(run.fw_version || 'unknown')}</span></div>
        <div class="metric"><span>Run Device</span><span>${escapeHtml(run.device_id || 'unknown')}</span></div>
        <div class="metric"><span>Command Chain</span><span>${escapeHtml(command.cmd_id || 'none')} / ${escapeHtml(command.cmd || 'none')} / ${escapeHtml(command.status || 'unknown')} / ACK ${escapeHtml(command.ack_status || 'none')}</span></div>
        <div class="metric"><span>Raw Evidence</span><span>${escapeHtml(rawFrame.frame_id || 'none')} / ${escapeHtml(rawFrame.frame_type || 'unknown')} / ${escapeHtml(rawFrame.parse_status || 'unknown')} / ${escapeHtml(rawFrame.derived_message_type || 'unknown')}</span></div>
        <div class="metric"><span>Derived Location</span><span>${escapeHtml(location.event_type || 'none')} seq ${escapeHtml(location.seq ?? 'unknown')} / fix ${escapeHtml(location.fix ?? 'unknown')} / ${escapeHtml(location.gnss_state || 'unknown')}</span></div>
        <div class="metric"><span>Failure State</span><span class="${failure.state === 'ok' ? 'ok' : failure.state === 'pending' || failure.state === 'warning' ? 'warn' : 'bad'}">${escapeHtml(failure.state || 'unknown')}</span></div>
        <div class="metric"><span>Failure Reason</span><span>${escapeHtml(failure.reason || 'unknown')}</span></div>
        <div class="metric"><span>Network Reconnect</span><span>${escapeHtml(relNetwork.reconnect_count ?? 'unknown')} / ${escapeHtml(relNetwork.last_reconnect_reason || relNetwork.state || 'unknown')}</span></div>
        <div class="metric"><span>Network Error</span><span>${escapeHtml(relNetwork.last_error || 'none')}</span></div>
        <div class="metric"><span>Raw POST</span><span>${escapeHtml(relNetwork.raw_post_success_count ?? 'unknown')} ok / ${escapeHtml(relNetwork.raw_post_failure_count ?? 'unknown')} fail / ${escapeHtml(relNetwork.raw_post_attempt_count ?? 'unknown')} attempts</span></div>
        <div class="metric"><span>Cache Queue</span><span>${escapeHtml(relCache.queued_message_count ?? 'unknown')} queued / ${escapeHtml(relCache.oldest_message_age_ms ?? 'unknown')} ms oldest</span></div>
        <div class="metric"><span>Cache Retry</span><span>${escapeHtml(relCache.retry_success_count ?? 'unknown')} ok / ${escapeHtml(relCache.retry_failure_count ?? 'unknown')} fail / ${escapeHtml(relCache.retry_attempt_count ?? 'unknown')} attempts / ${escapeHtml(relCache.retry_policy || 'none')}</span></div>
        <div class="metric"><span>Cache Flush</span><span>${escapeHtml(relCache.flush_success_count ?? 'unknown')} ok / ${escapeHtml(relCache.flush_failure_count ?? 'unknown')} fail / ${escapeHtml(relCache.flush_attempt_count ?? 'unknown')} attempts</span></div>
        <div class="metric"><span>Cache Drops</span><span>${escapeHtml(relCache.dropped_message_count ?? 'unknown')} / ${escapeHtml(relCache.last_drop_reason || 'none')}</span></div>
        <div class="metric"><span>EALE-P0</span><span>${escapeHtml(ealeBelief.state || 'unknown')} / ${escapeHtml(ealeBelief.substate || 'unknown')} / ${escapeHtml(ealeBelief.confidence_bucket || 'unknown')}</span></div>
        <div class="metric"><span>EALE Reason</span><span>${escapeHtml(ealeBelief.reason || 'unknown')}</span></div>
        <div class="metric"><span>EALE Failure</span><span>${escapeHtml(ealeBelief.failure_reason || 'none')}</span></div>
        <div class="metric"><span>Dataset Window</span><span>${escapeHtml(ealeDataset.sample_type || 'unknown')} / ${escapeHtml(ealeDataset.status || 'unknown')}</span></div>
        <div class="metric"><span>Dataset Training</span><span>${escapeHtml(ealeDataset.training_allowed ?? false)} / ${escapeHtml(ealeDataset.training_reason || 'unknown')}</span></div>
        <div class="metric"><span>Quality Flags</span><span>${escapeHtml((ealeBelief.quality_flags || []).join(', ') || 'none')}</span></div>
        <div class="metric"><span>Evidence Counts</span><span>${escapeHtml(counts.messages ?? 0)} messages / ${escapeHtml(counts.commands ?? 0)} commands / ${escapeHtml(counts.raw_frames ?? 0)} raw_frames</span></div>
      `;
    }
    function statusClass(status) {
      if (status === 'pass' || status === 'released') return 'ok';
      if (status === 'warn' || status === 'not_run' || status === 'release_candidate') return 'warn';
      return status === 'not_available' ? 'empty' : 'bad';
    }
    function productDemoPanel(demo) {
      if (!demo || !demo.available) {
        return `
          <div class="metric"><span>Candidate</span><b>KR-008 / DEMO-008</b></div>
          <div class="metric"><span>Result</span><span class="empty">${escapeHtml(demo && demo.status || 'not_available')}</span></div>
          <div class="metric"><span>Next Step</span><span>${escapeHtml(demo && demo.next_step || 'Generate a product demo report')}</span></div>
        `;
      }
      const location = demo.location || {};
      const training = demo.training_readiness || {};
      const webGate = (demo.flow || {}).web_console_replay_review || {};
      const counts = demo.flow_status_counts || {};
      const warnings = demo.warnings || [];
      return `
        <div class="metric"><span>Candidate</span><b>${escapeHtml(demo.candidate || 'KR-008 / DEMO-008')}</b></div>
        <div class="metric"><span>Result</span><span class="${statusClass(demo.status)}">${escapeHtml(demo.status || 'unknown')}</span></div>
        <div class="metric"><span>Release Ready</span><span>${escapeHtml(demo.ready_for_kr008_release ?? false)}</span></div>
        <div class="metric"><span>Evidence Mode</span><span>${escapeHtml(demo.evidence_mode || 'unknown')}</span></div>
        <div class="metric"><span>Test Run</span><span>${escapeHtml(demo.test_run_id || 'unknown')}</span></div>
        <div class="metric"><span>Safety Session</span><span>${escapeHtml(demo.safety_session_id || 'none')}</span></div>
        <div class="metric"><span>Location Belief</span><span>${escapeHtml(location.state || 'Unknown')} / ${escapeHtml(location.belief_reason || (location.failure_modes || []).join(', ') || 'unknown')}</span></div>
        <div class="metric"><span>GNSS</span><span>fix ${escapeHtml(location.gnss_fix ?? 'unknown')} / ${escapeHtml(location.gnss_state || 'unknown')}</span></div>
        <div class="metric"><span>Flow Gates</span><span>${escapeHtml(counts.pass ?? 0)} pass / ${escapeHtml(counts.warn ?? 0)} warn / ${escapeHtml(counts.not_run ?? 0)} not_run / ${escapeHtml(counts.fail ?? 0)} fail</span></div>
        <div class="metric"><span>Web Review</span><span class="${statusClass(webGate.status)}">${escapeHtml(webGate.status || 'unknown')} / ${escapeHtml(webGate.summary || 'unknown')}</span></div>
        <div class="metric"><span>Raw Evidence</span><span>${escapeHtml(demo.raw_frame_refs ?? 0)} raw refs / ${escapeHtml(demo.derived_event_refs ?? 0)} derived refs</span></div>
        <div class="metric"><span>Dataset Training</span><span>${escapeHtml(training.model_training_ready ?? false)} / ${escapeHtml(training.reason || 'unknown')}</span></div>
        <div class="metric"><span>Report</span><span>${escapeHtml(demo.markdown_path || demo.report_path || 'unknown')}</span></div>
        <div class="metric"><span>Warnings</span><span>${escapeHtml(warnings.join(', ') || 'none')}</span></div>
      `;
    }
    function d1StatusClass(status) {
      if (status === 'estimate_visible') return 'ok';
      if (status === 'waiting_for_location_upload') return 'warn';
      return 'empty';
    }
    function coordinateLabel(lat, lon) {
      const parsedLat = Number(lat);
      const parsedLon = Number(lon);
      if (Number.isFinite(parsedLat) && Number.isFinite(parsedLon)) {
        return `${parsedLat.toFixed(6)}, ${parsedLon.toFixed(6)}`;
      }
      return 'no coordinate';
    }
    function d1MapSurface(map, estimate) {
      const mode = map.mode || 'waiting_for_location_upload';
      const caption = map.visible
        ? `${mode} / ${estimate.state || 'unknown'} / ${coordinateLabel(map.lat, map.lon)}`
        : 'waiting for location upload';
      return `
        <div class="map-surface" data-d1-map-mode="${escapeHtml(mode)}">
          <div class="map-grid"></div>
          <div class="map-dot" title="${escapeHtml(caption)}"></div>
          <div class="map-caption">${escapeHtml(caption)}</div>
        </div>
      `;
    }
    function d1LinkPanel(devices) {
      if (!devices.length) return '<span class="empty">No device data yet</span>';
      const d = devices[0];
      const d1 = d.d1_link || {};
      const estimate = d1.location_estimate || {};
      const map = d1.map_surface || {};
      const freshness = d1.upload_freshness || {};
      const evidence = d1.evidence || {};
      const components = evidence.components || {};
      const gnss = components.gnss || {};
      const cellLte = components.cell_lte || {};
      const imu = components.imu || {};
      const power = components.power || {};
      return `
        ${d1MapSurface(map, estimate)}
        <div class="metric"><span>Map Surface</span><span>${escapeHtml(map.mode || 'waiting_for_location_upload')}</span></div>
        <div class="metric"><span>D1 Status</span><span class="${d1StatusClass(d1.status)}">${escapeHtml(d1.status || 'unknown')}</span></div>
        <div class="metric"><span>Location Estimate</span><span>${escapeHtml(estimate.state || 'unknown')} / ${escapeHtml(estimate.confidence ?? 'unknown')} / ${escapeHtml(estimate.radius_m ?? 'unknown')} m</span></div>
        <div class="metric"><span>Estimate Reason</span><span>${escapeHtml(estimate.reason || 'unknown')}</span></div>
        <div class="metric"><span>Estimate Source</span><span>${escapeHtml((estimate.source || []).join(', ') || 'none')}</span></div>
        <div class="metric"><span>Accuracy Claim</span><span>${escapeHtml(estimate.accuracy_claim || 'none')}</span></div>
        <div class="metric"><span>Location Upload</span><span>${escapeHtml(freshness.last_location_upload_at || 'none')}</span></div>
        <div class="metric"><span>Upload Freshness</span><span>${escapeHtml(freshness.freshness_s ?? 'unknown')} s / seq ${escapeHtml(freshness.last_seq ?? 'unknown')}</span></div>
        <div class="metric"><span>Transport</span><span>${escapeHtml(evidence.transport_type || 'unknown')}</span></div>
        <div class="metric"><span>GNSS Evidence</span><span>${escapeHtml(gnss.seen ?? false)} / fix ${escapeHtml(gnss.fix ?? 'unknown')} / ${escapeHtml(gnss.state || 'unknown')}</span></div>
        <div class="metric"><span>Cell/LTE Evidence</span><span>${escapeHtml(cellLte.seen ?? false)} / ${escapeHtml(cellLte.rat || 'unknown')} / ${escapeHtml(cellLte.registration_state || 'unknown')}</span></div>
        <div class="metric"><span>IMU Evidence</span><span>${escapeHtml(imu.seen ?? false)} / ${escapeHtml(imu.motion || 'unknown')} / ${escapeHtml(imu.evidence_status || 'unknown')}</span></div>
        <div class="metric"><span>Power Evidence</span><span>${escapeHtml(power.seen ?? false)} / ${escapeHtml(power.battery_mv ?? 'unknown')} mV / ${escapeHtml(power.soc_pct ?? 'unknown')}%</span></div>
      `;
    }
    function latestFieldState(devices, rawFrames) {
      if (!devices.length) return '<span class="empty">No device data yet</span>';
      const d = devices[0];
      const latestRaw = latestRawFrameForDevice(rawFrames, d.device_id);
      const latestRawParsed = parseResult(latestRaw);
      const latestRawFraming = framing(latestRaw);
      const obs = d.observability || {};
      const obsTransport = obs.transport || {};
      const obsRuntime = obs.runtime || {};
      const obsCommand = obs.command || {};
      const obsPower = obs.power || {};
      const obsGnss = obs.gnss || {};
      const obsCell = obs.cell || {};
      const obsLte = obs.lte || {};
      const obsWifi = obs.wifi || {};
      const obsImu = obs.imu || {};
      const obsReliability = obs.reliability || {};
      const obsRelNetwork = obsReliability.network || {};
      const obsRelCache = obsReliability.cache || {};
      const obsBelief = obs.location_belief || {};
      const obsMemory = obs.location_memory || {};
      const obsExplainability = obs.explainability || {};
      const location = d.latest_location || {};
      const telemetry = d.latest_telemetry || {};
      const fieldTelemetry = ['location_report', 'location_observation'].includes(location.event_type) ? location : telemetry;
      const status = d.last_status || {};
      const error = d.last_error || {};
      const lat = gnssField(fieldTelemetry, 'lat');
      const lon = gnssField(fieldTelemetry, 'lon');
      return `
        <div class="metric"><span>Observed Device</span><b>${escapeHtml(d.device_id)}</b></div>
        <div class="metric"><span>Online Status</span><span class="${ageClass(d.last_seen_at)}">${escapeHtml(onlineLabel(d.last_seen_at))}</span></div>
        <div class="metric"><span>Last Seen</span><span>${escapeHtml(d.last_seen_at)}</span></div>
        <div class="metric"><span>Location Updated</span><span>${escapeHtml(fieldTelemetry.server_received_at || 'none')}</span></div>
        <div class="metric"><span>Field Message</span><span>${escapeHtml(fieldTelemetry.event_type || fieldTelemetry.message_type || 'unknown')}</span></div>
        <div class="metric"><span>Location State</span><span>${escapeHtml(obsBelief.state || 'unknown')}</span></div>
        <div class="metric"><span>Belief</span><span>${escapeHtml(obsBelief.confidence ?? 'unknown')} / ${escapeHtml(obsBelief.radius_m ?? 'unknown')} m</span></div>
        <div class="metric"><span>Belief Source</span><span>${escapeHtml((obsBelief.source || []).join(', ') || 'none')}</span></div>
        <div class="metric"><span>Belief Reason</span><span>${escapeHtml(obsBelief.reason || 'unknown')}</span></div>
        <div class="metric"><span>Memory State</span><span>${escapeHtml(obsMemory.state || 'unknown')}</span></div>
        <div class="metric"><span>Memory Updated</span><span>${escapeHtml(obsMemory.belief_updated_at || obsMemory.updated_at || 'none')}</span></div>
        <div class="metric"><span>Memory Reason</span><span>${escapeHtml(obsMemory.reason || 'unknown')}</span></div>
        <div class="metric"><span>GNSS State</span><span>${escapeHtml(gnssField(fieldTelemetry, 'gnss_state', fieldTelemetry.event_type || status.gnss_state || 'unknown'))}</span></div>
        <div class="metric"><span>Fix</span><span>${escapeHtml(gnssField(fieldTelemetry, 'fix'))}</span></div>
        <div class="metric"><span>Position</span><span>${escapeHtml(lat)}, ${escapeHtml(lon)}</span></div>
        <div class="metric"><span>Satellites</span><span>${escapeHtml(gnssField(fieldTelemetry, 'satellites'))}</span></div>
        <div class="metric"><span>HDOP</span><span>${escapeHtml(gnssField(fieldTelemetry, 'hdop'))}</span></div>
        <div class="metric"><span>Source Status</span><span>${escapeHtml(gnssField(fieldTelemetry, 'source_status'))}</span></div>
        <div class="metric"><span>Transport</span><span>${escapeHtml(obsTransport.type || status.link_type || 'unknown')}</span></div>
        <div class="metric"><span>Transport Error</span><span>${escapeHtml(obsTransport.last_error || 'none')}</span></div>
        <div class="metric"><span>Network Reconnect</span><span>${escapeHtml(obsRelNetwork.reconnect_count ?? 'unknown')} / ${escapeHtml(obsRelNetwork.last_reconnect_reason || obsRelNetwork.state || 'unknown')}</span></div>
        <div class="metric"><span>Network Error</span><span>${escapeHtml(obsRelNetwork.last_error || 'none')}</span></div>
        <div class="metric"><span>Raw POST</span><span>${escapeHtml(obsRelNetwork.raw_post_success_count ?? 'unknown')} ok / ${escapeHtml(obsRelNetwork.raw_post_failure_count ?? 'unknown')} fail / ${escapeHtml(obsRelNetwork.raw_post_attempt_count ?? 'unknown')} attempts</span></div>
        <div class="metric"><span>Cache Queue</span><span>${escapeHtml(obsRelCache.queued_message_count ?? 'unknown')} queued / ${escapeHtml(obsRelCache.oldest_message_age_ms ?? 'unknown')} ms oldest</span></div>
        <div class="metric"><span>Cache Retry</span><span>${escapeHtml(obsRelCache.retry_success_count ?? 'unknown')} ok / ${escapeHtml(obsRelCache.retry_failure_count ?? 'unknown')} fail / ${escapeHtml(obsRelCache.retry_attempt_count ?? 'unknown')} attempts / ${escapeHtml(obsRelCache.retry_policy || 'none')}</span></div>
        <div class="metric"><span>Cache Flush</span><span>${escapeHtml(obsRelCache.flush_success_count ?? 'unknown')} ok / ${escapeHtml(obsRelCache.flush_failure_count ?? 'unknown')} fail / ${escapeHtml(obsRelCache.flush_attempt_count ?? 'unknown')} attempts</span></div>
        <div class="metric"><span>Cache Drops</span><span>${escapeHtml(obsRelCache.dropped_message_count ?? 'unknown')} / ${escapeHtml(obsRelCache.last_drop_reason || 'none')}</span></div>
        <div class="metric"><span>Runtime Reset</span><span>${escapeHtml(obsRuntime.last_reset_reason || 'unknown')}</span></div>
        <div class="metric"><span>Boot</span><span>${escapeHtml(obsRuntime.boot_id || 'unknown')}</span></div>
        <div class="metric"><span>Command</span><span>${escapeHtml(obsCommand.last_cmd_id || 'none')} / ${escapeHtml(obsCommand.last_ack_status || obsCommand.last_status || 'none')}</span></div>
        <div class="metric"><span>Raw Frame</span><span class="${rawFrameClass(latestRaw)}">${escapeHtml(rawFrameSummary(latestRaw))}</span></div>
        <div class="metric"><span>Raw Frame ID</span><span>${escapeHtml(latestRaw.frame_id || 'none')}</span></div>
        <div class="metric"><span>Raw Derived</span><span>${escapeHtml(latestRawParsed.derived_message_type || 'unknown')} / ${escapeHtml(latestRawFraming.content_type || 'unknown')}</span></div>
        <div class="metric"><span>Power</span><span>${escapeHtml(obsPower.battery_mv ?? 'unknown')} mV / ${escapeHtml(obsPower.soc_pct ?? status.battery ?? 'unknown')}% / ${escapeHtml(obsPower.evidence_status || obsPower.source_status || obsPower.source || 'unknown')}</span></div>
        <div class="metric"><span>Cell</span><span>${escapeHtml(obsCell.rat || 'unknown')} ${escapeHtml(obsCell.cell_id || '')} RSRP ${escapeHtml(obsCell.rsrp ?? 'unknown')}</span></div>
        <div class="metric"><span>LTE</span><span>${escapeHtml(obsLte.registration_state || obsCell.registration_state || 'unknown')} / PDP ${escapeHtml(obsLte.pdp_state || obsCell.pdp_state || 'unknown')} / SIM ${escapeHtml(obsLte.sim_state || obsCell.sim_state || 'unknown')}</span></div>
        <div class="metric"><span>LTE Reason</span><span>${escapeHtml(obsLte.reason_code || obsCell.reason_code || 'unknown')}</span></div>
        <div class="metric"><span>Wi-Fi</span><span>${escapeHtml(obsWifi.scan_enabled ?? 'unknown')} / APs ${escapeHtml(obsWifi.ap_count ?? 'unknown')} / ${escapeHtml(obsWifi.evidence_status || obsWifi.source_status || 'unknown')}</span></div>
        <div class="metric"><span>IMU</span><span>${escapeHtml(obsImu.motion || 'unknown')} ${escapeHtml(obsImu.confidence ?? '')} / ${escapeHtml(obsImu.evidence_status || obsImu.source_status || 'unknown')}</span></div>
        <div class="metric"><span>GNSS Reason</span><span>${escapeHtml(obsGnss.reason_code || 'unknown')}</span></div>
        <div class="metric"><span>Reason Codes</span><span>${escapeHtml((obsExplainability.reason_codes || []).join(', ') || 'none')}</span></div>
        <div class="metric"><span>Last Error</span><span>${escapeHtml(error.error_code || 'none')}</span></div>
      `;
    }
    async function refresh() {
      const response = await fetch('/api/state', { headers: authHeaders() });
      if (response.status === 401) {
        authStatus.textContent = 'token required';
        showStateMessage('API token required');
        return;
      }
      if (!response.ok) {
        authStatus.textContent = `HTTP ${response.status}`;
        showStateMessage(`API error HTTP ${response.status}`);
        return;
      }
      authStatus.textContent = 'connected';
      const data = await response.json();
      runContext.innerHTML = runContextPanel(data.current_run || {});
      productDemo.innerHTML = productDemoPanel(data.product_demo || {});
      d1Link.innerHTML = d1LinkPanel(data.devices || []);
      devices.innerHTML = data.devices.map(d => `
        <div class="metric"><span>Device</span><b>${escapeHtml(d.device_id)}</b></div>
        <div class="metric"><span>Status</span><span class="${ageClass(d.last_seen_at)}">${escapeHtml(onlineLabel(d.last_seen_at))}</span></div>
        <div class="metric"><span>Last Seen</span><span>${escapeHtml(d.last_seen_at)}</span></div>
        <div class="metric"><span>Last Type</span><span>${escapeHtml(d.last_message_type)}</span></div>
        <div class="metric"><span>Seq</span><span>${escapeHtml(d.last_seq)}</span></div>
      `).join('') || '<span>No devices yet</span>';
      fieldState.innerHTML = latestFieldState(data.devices, data.raw_frames || []);
      commands.innerHTML = data.commands.map(c => `
        <div class="metric"><span>${escapeHtml(c.cmd_id)}</span><span class="${c.status === 'ok' ? 'ok' : c.status === 'pending' ? 'warn' : 'bad'}">${escapeHtml(c.cmd)} / ${escapeHtml(c.status)}</span></div>
      `).join('') || '<span class="empty">No commands yet</span>';
      rawFrames.innerHTML = (data.raw_frames || []).map(frame => {
        const parsed = parseResult(frame);
        const frameMeta = framing(frame);
        const reason = parsed.reason || parsed.error_code || 'none';
        return `
          <div class="metric"><span>${escapeHtml(frame.frame_id || 'raw')}</span><span class="${rawFrameClass(frame)}">${escapeHtml(rawFrameSummary(frame))}</span></div>
          <div class="metric"><span>Received</span><span>${escapeHtml(frame.server_received_at || 'unknown')}</span></div>
          <div class="metric"><span>Payload</span><span>${escapeHtml(frameMeta.payload_len ?? 'unknown')} bytes / ${escapeHtml(frameMeta.payload_crc32 || 'unknown')}</span></div>
          <div class="metric"><span>Reason</span><span>${escapeHtml(reason)}</span></div>
        `;
      }).join('') || '<span class="empty">No raw frames yet</span>';
      messages.innerHTML = data.messages.map(m => `
        <tr>
          <td>${escapeHtml(m.device_id)}</td>
          <td>${escapeHtml(m.message_type)}</td>
          <td>${escapeHtml(m.seq)}</td>
          <td>${escapeHtml(detail(m))}</td>
          <td>${escapeHtml(m.server_received_at)}</td>
        </tr>
      `).join('') || '<tr><td colspan="5" class="empty">No messages yet</td></tr>';
    }
    refresh();
    setInterval(refresh, 3000);
  </script>
</body>
</html>"""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Ego Link P0 HTTP message hub.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8790)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument(
        "--token-env",
        default="EGOLINK_MESSAGE_HUB_TOKEN",
        help="Environment variable containing the optional bearer token.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    store = MessageHubStore(args.db)
    token = os.environ.get(args.token_env) or None
    server = ThreadingHTTPServer((args.host, args.port), make_handler(store, token=token))
    print(f"Ego Link Message Hub running at http://{args.host}:{args.port}")
    print(f"SQLite database: {args.db}")
    if token:
        print("Bearer token authentication: enabled")
    else:
        print("Bearer token authentication: disabled")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

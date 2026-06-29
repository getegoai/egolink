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
from typing import Any
from urllib.parse import unquote, urlparse

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pc_simulator import protocol


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = REPO_ROOT / "server" / "runtime" / "message_hub.db"
MAX_BODY_BYTES = 1_000_000
RAW_FRAME_PROFILE = "raw-frame.p0.v1"


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
        device["last_command"] = self._latest_command(db, device["device_id"])
        device["observability"] = build_observability(device, device["last_command"])
        return device

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
        message_list = [json.loads(row["payload_json"]) for row in messages]
        command_list = [command_row(row) for row in commands]
        raw_frame_list = [redact_raw_frame_record(json.loads(row["record_json"])) for row in raw_frames]
        return {
            "test_run": json.loads(run["metadata_json"]),
            "messages": message_list,
            "commands": command_list,
            "raw_frames": raw_frame_list,
            "observability_summary": summarize_test_run_observability(message_list, command_list),
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


def make_handler(store: MessageHubStore, *, token: str | None = None) -> type[BaseHTTPRequestHandler]:
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
                self.respond_json(
                    {
                        "devices": store.list_devices(),
                        "messages": store.recent_messages(20),
                        "commands": store.recent_commands(20),
                        "raw_frames": store.recent_raw_frames(20),
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
            raise MessageHubError("not_found", "route not found", status=404)

        def route_post(self) -> None:
            segments = split_path(urlparse(self.path).path)
            if len(segments) == 5 and segments[:3] == ["api", "v1", "devices"] and segments[4] == "raw-ingest":
                device_id = segments[3]
                record = store.ingest_raw_frame(device_id, self.read_raw_body())
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
        return compact_dict(
            {
                **common,
                "message_type": "ack",
                "cmd_id": cmd_id,
                "status": first_known(kv_payload.get("status"), "ok"),
                "message": first_known(kv_payload.get("message"), "raw-frame ack"),
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
        return compact_dict(
            {
                **common,
                "message_type": "status",
                "battery": parse_number_or_text(kv_payload.get("battery")),
                "link_type": first_known(kv_payload.get("link-type"), kv_payload.get("link_type"), "unknown"),
                "guard_mode": first_known(kv_payload.get("guard-mode"), kv_payload.get("guard_mode"), "unknown"),
                "queue_size": parse_optional_int(kv_payload.get("queue-size") or kv_payload.get("queue_size")) or 0,
            }
        )
    if frame_type == "event":
        return compact_dict(
            {
                **common,
                "message_type": "event",
                "event_type": first_known(kv_payload.get("event-type"), kv_payload.get("event_type"), "raw_event"),
                "priority": first_known(kv_payload.get("priority"), "normal"),
            }
        )
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


def build_observability(device: dict[str, Any], latest_command: dict[str, Any] | None = None) -> dict[str, Any]:
    status = as_dict(device.get("last_status"))
    telemetry = as_dict(device.get("latest_telemetry"))
    latest_location = as_dict(device.get("latest_location"))
    latest_location_observation = as_dict(device.get("latest_location_observation"))
    field_message = latest_location if latest_location else telemetry
    error = as_dict(device.get("last_error"))
    latest_command = as_dict(latest_command)

    status_payload = as_dict(status.get("payload"))
    telemetry_payload = as_dict(telemetry.get("payload"))
    field_payload = as_dict(field_message.get("payload"))
    transport = as_dict(first_known(status.get("transport"), telemetry.get("transport"), field_message.get("transport")))
    runtime = as_dict(first_known(status.get("runtime"), telemetry.get("runtime")))
    power = as_dict(first_known(status.get("power"), telemetry.get("power"), field_message.get("power")))
    gnss = as_dict(first_known(field_message.get("gnss"), field_payload.get("gnss"), telemetry_payload.get("gnss")))
    cell = as_dict(first_known(field_message.get("cell"), telemetry.get("cell"), status.get("cell")))
    lte = as_dict(first_known(field_message.get("lte"), telemetry.get("lte"), status.get("lte")))
    wifi = as_dict(first_known(field_message.get("wifi"), telemetry.get("wifi"), status.get("wifi")))
    imu = as_dict(first_known(field_message.get("imu"), telemetry.get("imu"), status.get("imu")))
    location_belief = as_dict(first_known(field_message.get("location_belief"), field_payload.get("location_belief")))
    ack = as_dict(latest_command.get("ack"))

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
    reason_codes: list[str] = []
    for candidate in (error_code, transport_last_error, gnss_reason, lte_reason):
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
        "power": {
            "battery_mv": first_known(power.get("battery_mv"), status.get("battery_mv"), status_payload.get("battery_mv")),
            "soc_pct": first_known(power.get("soc_pct"), status.get("soc_pct"), status.get("battery_percent"), status.get("battery")),
            "charging": first_known(power.get("charging"), status.get("charging")),
            "source": first_known(power.get("source"), status.get("battery_source"), "unknown"),
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
            "ap_count": len(wifi.get("aps")) if isinstance(wifi.get("aps"), list) else None,
        },
        "imu": {
            "motion": first_known(imu.get("motion"), imu.get("state")),
            "confidence": imu.get("confidence"),
        },
        "location_belief": {
            "state": first_known(location_belief.get("state"), "unknown"),
            "radius_m": location_belief.get("radius_m"),
            "confidence": location_belief.get("confidence"),
            "source": location_belief.get("source") if isinstance(location_belief.get("source"), list) else [],
            "reason": first_known(location_belief.get("reason"), "no_location_belief"),
            "updated_at": first_known(field_message.get("server_received_at"), latest_location_observation.get("server_received_at")),
        },
        "explainability": {
            "state": "warning" if reason_codes else "ok",
            "reason_codes": reason_codes,
        },
    }


def summarize_test_run_observability(messages: list[dict[str, Any]], commands: list[dict[str, Any]]) -> dict[str, Any]:
    if not messages:
        return {"message_count": 0, "latest_observability": None, "reason_codes": []}
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
    return {
        "message_count": len(messages),
        "command_count": len(commands),
        "latest_observability": latest_observability,
        "reason_codes": reason_codes,
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
        <h2>Commands</h2>
        <div id="commands"></div>
      </section>
    </div>
    <div class="stack">
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
      commands.innerHTML = html;
      fieldState.innerHTML = html;
      messages.innerHTML = `<tr><td colspan="5" class="empty">${escapeHtml(message)}</td></tr>`;
    }
    tokenInput.value = currentToken();
    saveToken.addEventListener('click', () => {
      localStorage.setItem('egolinkHubToken', tokenInput.value.trim());
      refresh();
    });
    function latestFieldState(devices) {
      if (!devices.length) return '<span class="empty">No device data yet</span>';
      const d = devices[0];
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
      const obsBelief = obs.location_belief || {};
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
        <div class="metric"><span>GNSS State</span><span>${escapeHtml(gnssField(fieldTelemetry, 'gnss_state', fieldTelemetry.event_type || status.gnss_state || 'unknown'))}</span></div>
        <div class="metric"><span>Fix</span><span>${escapeHtml(gnssField(fieldTelemetry, 'fix'))}</span></div>
        <div class="metric"><span>Position</span><span>${escapeHtml(lat)}, ${escapeHtml(lon)}</span></div>
        <div class="metric"><span>Satellites</span><span>${escapeHtml(gnssField(fieldTelemetry, 'satellites'))}</span></div>
        <div class="metric"><span>HDOP</span><span>${escapeHtml(gnssField(fieldTelemetry, 'hdop'))}</span></div>
        <div class="metric"><span>Source Status</span><span>${escapeHtml(gnssField(fieldTelemetry, 'source_status'))}</span></div>
        <div class="metric"><span>Transport</span><span>${escapeHtml(obsTransport.type || status.link_type || 'unknown')}</span></div>
        <div class="metric"><span>Transport Error</span><span>${escapeHtml(obsTransport.last_error || 'none')}</span></div>
        <div class="metric"><span>Runtime Reset</span><span>${escapeHtml(obsRuntime.last_reset_reason || 'unknown')}</span></div>
        <div class="metric"><span>Boot</span><span>${escapeHtml(obsRuntime.boot_id || 'unknown')}</span></div>
        <div class="metric"><span>Command</span><span>${escapeHtml(obsCommand.last_cmd_id || 'none')} / ${escapeHtml(obsCommand.last_ack_status || obsCommand.last_status || 'none')}</span></div>
        <div class="metric"><span>Power</span><span>${escapeHtml(obsPower.battery_mv ?? 'unknown')} mV / ${escapeHtml(obsPower.soc_pct ?? status.battery ?? 'unknown')}%</span></div>
        <div class="metric"><span>Cell</span><span>${escapeHtml(obsCell.rat || 'unknown')} ${escapeHtml(obsCell.cell_id || '')} RSRP ${escapeHtml(obsCell.rsrp ?? 'unknown')}</span></div>
        <div class="metric"><span>LTE</span><span>${escapeHtml(obsLte.registration_state || obsCell.registration_state || 'unknown')} / PDP ${escapeHtml(obsLte.pdp_state || obsCell.pdp_state || 'unknown')} / SIM ${escapeHtml(obsLte.sim_state || obsCell.sim_state || 'unknown')}</span></div>
        <div class="metric"><span>LTE Reason</span><span>${escapeHtml(obsLte.reason_code || obsCell.reason_code || 'unknown')}</span></div>
        <div class="metric"><span>Wi-Fi</span><span>${escapeHtml(obsWifi.scan_enabled ?? 'unknown')} / APs ${escapeHtml(obsWifi.ap_count ?? 'unknown')}</span></div>
        <div class="metric"><span>IMU</span><span>${escapeHtml(obsImu.motion || 'unknown')} ${escapeHtml(obsImu.confidence ?? '')}</span></div>
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
      devices.innerHTML = data.devices.map(d => `
        <div class="metric"><span>Device</span><b>${escapeHtml(d.device_id)}</b></div>
        <div class="metric"><span>Status</span><span class="${ageClass(d.last_seen_at)}">${escapeHtml(onlineLabel(d.last_seen_at))}</span></div>
        <div class="metric"><span>Last Seen</span><span>${escapeHtml(d.last_seen_at)}</span></div>
        <div class="metric"><span>Last Type</span><span>${escapeHtml(d.last_message_type)}</span></div>
        <div class="metric"><span>Seq</span><span>${escapeHtml(d.last_seq)}</span></div>
      `).join('') || '<span>No devices yet</span>';
      fieldState.innerHTML = latestFieldState(data.devices);
      commands.innerHTML = data.commands.map(c => `
        <div class="metric"><span>${escapeHtml(c.cmd_id)}</span><span class="${c.status === 'ok' ? 'ok' : c.status === 'pending' ? 'warn' : 'bad'}">${escapeHtml(c.cmd)} / ${escapeHtml(c.status)}</span></div>
      `).join('') || '<span class="empty">No commands yet</span>';
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

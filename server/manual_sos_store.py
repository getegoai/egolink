"""Strict, durable manual-SOS ingest and Guardian projection.

This module implements a narrow runtime validator for the coordinate-free
``manual_sos`` subset emitted by the existing device orchestrator.  The shared
``safety_event.schema.json`` remains the contract; this is not a second schema.

The exact authenticated request bytes are retained in the SQLite timeline so
the server ACK can bind the bytes held by the device outbox.  The raw bytes are
never returned by the public projection.  SQLite provides integrity and
transactional durability here, not at-rest confidentiality.
"""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import threading
import time
from typing import Any, Mapping


MAX_MANUAL_SOS_BODY_BYTES = 1024
SQLITE_SIGNED_INT64_MAX = (1 << 63) - 1
SAFETY_EVENT_CONTRACT_VERSION = "1.0.0"
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$")
_EVENT_ID = re.compile(
    r"^sos-b(0|[1-9][0-9]*)-q(0|[1-9][0-9]*)-t(0|[1-9][0-9]*)$"
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

_ROOT_FIELDS = frozenset(
    {
        "contract_version",
        "event_id",
        "device_id",
        "timestamp_ms",
        "sequence",
        "event_type",
        "priority",
        "source",
        "model_result",
        "context",
        "evidence",
        "privacy",
    }
)
_MODEL_FIELDS = frozenset(
    {
        "manual_input",
        "qualified_long_press",
        "time_source",
        "boot_count",
        "session_id",
        "source_sequence",
    }
)
_CONTEXT_FIELDS = frozenset(
    {"mode", "battery_percent", "base_online", "upload_available"}
)
_EVIDENCE_FIELDS = frozenset(
    {"audio_clip_ref", "image_ref", "imu_window_ref", "location_fresh"}
)
_PRIVACY_FIELDS = frozenset(
    {"privacy_mode", "raw_evidence_allowed", "retention_seconds"}
)


class ManualSosStoreError(RuntimeError):
    """Base class for sanitized manual-SOS store failures."""


class ManualSosValidationError(ManualSosStoreError, ValueError):
    """Raised before mutation when input is outside the frozen subset."""


class ManualSosConflictError(ManualSosStoreError):
    """Raised when an immutable durable identity is reused with other bytes."""


class ManualSosNotFoundError(ManualSosStoreError):
    """Raised when a Guardian acknowledgement names no durable event."""


class ManualSosStoreCorruptionError(ManualSosStoreError):
    """Raised when the durable timeline cannot be validated on recovery."""


def _exact_object(
    value: Any,
    *,
    fields: frozenset[str],
    name: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or frozenset(value) != fields:
        raise ManualSosValidationError(
            f"{name} must contain exactly the accepted manual-SOS fields"
        )
    return value


def _safe_id(value: Any, name: str) -> str:
    if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
        raise ManualSosValidationError(
            f"{name} must be a 1-128 character outbox-safe identifier"
        )
    return value


def _sqlite_non_negative_integer(value: Any, name: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value > SQLITE_SIGNED_INT64_MAX
    ):
        raise ManualSosValidationError(
            f"{name} must fit a non-negative SQLite signed integer"
        )
    return value


def _exact_bool(value: Any, expected: bool, name: str) -> bool:
    if not isinstance(value, bool) or value is not expected:
        raise ManualSosValidationError(f"{name} must be {str(expected).lower()}")
    return value


def _reject_duplicate_members(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ManualSosValidationError(
                "manual SOS JSON contains a duplicate member"
            )
        result[key] = value
    return result


def _reject_non_finite(value: str) -> Any:
    raise ManualSosValidationError(
        "manual SOS JSON contains a non-finite numeric constant"
    )


@dataclass(frozen=True)
class ValidatedManualSos:
    document: Mapping[str, Any] = field(repr=False)
    device_id: str
    event_id: str
    boot_count: int
    session_id: str
    source_event_time_ms: int
    source_sequence: int
    battery_percent: int | None
    base_online: bool
    upload_available: bool

    @property
    def identity(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "event_id": self.event_id,
            "boot_count": self.boot_count,
            "session_id": self.session_id,
            "source_event_time_ms": self.source_event_time_ms,
            "source_sequence": self.source_sequence,
        }


def validate_manual_sos_payload(raw_payload: bytes) -> ValidatedManualSos:
    """Validate exact input bytes against the C-orchestrator subset."""

    if not isinstance(raw_payload, bytes):
        raise ManualSosValidationError("manual SOS payload must be bytes")
    if not raw_payload or len(raw_payload) > MAX_MANUAL_SOS_BODY_BYTES:
        raise ManualSosValidationError(
            f"manual SOS payload must be 1-{MAX_MANUAL_SOS_BODY_BYTES} bytes"
        )
    try:
        text = raw_payload.decode("utf-8")
        document = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_members,
            parse_constant=_reject_non_finite,
        )
    except ManualSosValidationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise ManualSosValidationError(
            "manual SOS payload must be valid UTF-8 JSON"
        ) from error

    root = _exact_object(document, fields=_ROOT_FIELDS, name="safety event")
    if root["contract_version"] != SAFETY_EVENT_CONTRACT_VERSION:
        raise ManualSosValidationError("contract_version is unsupported")
    device_id = _safe_id(root["device_id"], "device_id")
    event_id = _safe_id(root["event_id"], "event_id")
    match = _EVENT_ID.fullmatch(event_id)
    if match is None:
        raise ManualSosValidationError(
            "event_id must encode deterministic manual-SOS lineage"
        )
    source_event_time_ms = _sqlite_non_negative_integer(
        root["timestamp_ms"], "timestamp_ms"
    )
    sequence = _sqlite_non_negative_integer(root["sequence"], "sequence")
    if root["event_type"] != "manual_sos":
        raise ManualSosValidationError("event_type must be manual_sos")
    if root["priority"] != "critical":
        raise ManualSosValidationError("priority must be critical")
    if root["source"] != "device_rule":
        raise ManualSosValidationError("source must be device_rule")

    model = _exact_object(
        root["model_result"], fields=_MODEL_FIELDS, name="model_result"
    )
    _exact_bool(model["manual_input"], True, "model_result.manual_input")
    _exact_bool(
        model["qualified_long_press"],
        True,
        "model_result.qualified_long_press",
    )
    if model["time_source"] != "boot_monotonic_ms":
        raise ManualSosValidationError(
            "model_result.time_source must be boot_monotonic_ms"
        )
    boot_count = _sqlite_non_negative_integer(
        model["boot_count"], "model_result.boot_count"
    )
    session_id = _safe_id(model["session_id"], "model_result.session_id")
    source_sequence = _sqlite_non_negative_integer(
        model["source_sequence"], "model_result.source_sequence"
    )
    encoded_boot, encoded_sequence, encoded_time = (
        _sqlite_non_negative_integer(int(value), "event_id lineage")
        for value in match.groups()
    )
    if (
        encoded_boot != boot_count
        or encoded_sequence != source_sequence
        or encoded_time != source_event_time_ms
        or sequence != source_sequence
    ):
        raise ManualSosValidationError(
            "event_id, sequence and boot-monotonic lineage must match"
        )

    context = _exact_object(
        root["context"], fields=_CONTEXT_FIELDS, name="context"
    )
    if context["mode"] != "manual_sos":
        raise ManualSosValidationError("context.mode must be manual_sos")
    battery_value = context["battery_percent"]
    if battery_value is None:
        battery_percent = None
    elif (
        isinstance(battery_value, bool)
        or not isinstance(battery_value, int)
        or battery_value < 0
        or battery_value > 100
    ):
        raise ManualSosValidationError(
            "context.battery_percent must be an integer from 0 to 100 or null"
        )
    else:
        battery_percent = battery_value
    if not isinstance(context["base_online"], bool):
        raise ManualSosValidationError("context.base_online must be boolean")
    if not isinstance(context["upload_available"], bool):
        raise ManualSosValidationError(
            "context.upload_available must be boolean"
        )

    evidence = _exact_object(
        root["evidence"], fields=_EVIDENCE_FIELDS, name="evidence"
    )
    for name in ("audio_clip_ref", "image_ref", "imu_window_ref"):
        if evidence[name] is not None:
            raise ManualSosValidationError(
                f"evidence.{name} must be null for this coordinate-free subset"
            )
    _exact_bool(evidence["location_fresh"], False, "evidence.location_fresh")

    privacy = _exact_object(
        root["privacy"], fields=_PRIVACY_FIELDS, name="privacy"
    )
    _exact_bool(privacy["privacy_mode"], True, "privacy.privacy_mode")
    _exact_bool(
        privacy["raw_evidence_allowed"],
        False,
        "privacy.raw_evidence_allowed",
    )
    if privacy["retention_seconds"] != 86400:
        raise ManualSosValidationError(
            "privacy.retention_seconds must match the orchestrator subset"
        )

    return ValidatedManualSos(
        document=root,
        device_id=device_id,
        event_id=event_id,
        boot_count=boot_count,
        session_id=session_id,
        source_event_time_ms=source_event_time_ms,
        source_sequence=source_sequence,
        battery_percent=battery_percent,
        base_online=context["base_online"],
        upload_available=context["upload_available"],
    )


class ManualSosStore:
    """Thread-serialized SQLite timeline with a rebuildable current cache."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_schema()
        self._recover_and_validate()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def _init_schema(self) -> None:
        with closing(self._connect()) as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS manual_sos_timeline (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    boot_count INTEGER NOT NULL,
                    session_id TEXT NOT NULL,
                    source_event_time_ms INTEGER NOT NULL,
                    source_sequence INTEGER NOT NULL,
                    battery_percent INTEGER,
                    base_online INTEGER NOT NULL,
                    upload_available INTEGER NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    raw_payload BLOB NOT NULL,
                    server_receive_time_ms INTEGER NOT NULL,
                    UNIQUE(device_id, event_id),
                    UNIQUE(device_id, boot_count, session_id, source_sequence)
                );
                CREATE INDEX IF NOT EXISTS idx_manual_sos_timeline_device
                ON manual_sos_timeline(device_id, id);
                CREATE TABLE IF NOT EXISTS manual_sos_current (
                    device_id TEXT PRIMARY KEY,
                    timeline_id INTEGER NOT NULL,
                    FOREIGN KEY(timeline_id) REFERENCES manual_sos_timeline(id)
                );
                CREATE TABLE IF NOT EXISTS manual_sos_guardian_ack (
                    device_id TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    timeline_id INTEGER NOT NULL,
                    guardian_id TEXT NOT NULL,
                    acknowledged_at_ms INTEGER NOT NULL,
                    PRIMARY KEY(device_id, event_id),
                    FOREIGN KEY(timeline_id) REFERENCES manual_sos_timeline(id)
                );
                """
            )

    @staticmethod
    def _row_payload(row: sqlite3.Row) -> bytes:
        value = row["raw_payload"]
        if not isinstance(value, bytes):
            raise ManualSosStoreCorruptionError(
                "manual SOS timeline raw payload is not a BLOB"
            )
        return value

    @classmethod
    def _validated_row(cls, row: sqlite3.Row) -> ValidatedManualSos:
        raw_payload = cls._row_payload(row)
        digest = hashlib.sha256(raw_payload).hexdigest()
        try:
            event = validate_manual_sos_payload(raw_payload)
        except ManualSosValidationError as error:
            raise ManualSosStoreCorruptionError(
                "manual SOS timeline payload failed validation"
            ) from error
        expected = {
            "device_id": event.device_id,
            "event_id": event.event_id,
            "boot_count": event.boot_count,
            "session_id": event.session_id,
            "source_event_time_ms": event.source_event_time_ms,
            "source_sequence": event.source_sequence,
            "battery_percent": event.battery_percent,
            "base_online": int(event.base_online),
            "upload_available": int(event.upload_available),
            "payload_sha256": digest,
        }
        if any(row[name] != value for name, value in expected.items()):
            raise ManualSosStoreCorruptionError(
                "manual SOS timeline index does not match its exact payload"
            )
        if (
            not isinstance(row["server_receive_time_ms"], int)
            or row["server_receive_time_ms"] < 0
            or row["server_receive_time_ms"] > SQLITE_SIGNED_INT64_MAX
        ):
            raise ManualSosStoreCorruptionError(
                "manual SOS timeline receive time is invalid"
            )
        return event

    @staticmethod
    def _current_order(event: ValidatedManualSos) -> tuple[int, int, int]:
        """Comparable device lineage; event time is a consistency tie-break."""

        return (
            event.boot_count,
            event.source_sequence,
            event.source_event_time_ms,
        )

    def _recover_and_validate(self) -> None:
        with self._lock, closing(self._connect()) as db:
            try:
                db.execute("BEGIN IMMEDIATE")
                rows = db.execute(
                    "SELECT * FROM manual_sos_timeline ORDER BY id"
                ).fetchall()
                current_candidates: dict[
                    str, tuple[tuple[int, int, int], int]
                ] = {}
                valid_identities: set[tuple[str, str, int]] = set()
                boot_sessions: dict[tuple[str, int], str] = {}
                streams: dict[
                    tuple[str, int, str], list[ValidatedManualSos]
                ] = {}
                for row in rows:
                    event = self._validated_row(row)
                    boot_key = (event.device_id, event.boot_count)
                    prior_session = boot_sessions.setdefault(
                        boot_key, event.session_id
                    )
                    if prior_session != event.session_id:
                        raise ManualSosStoreCorruptionError(
                            "one device boot is bound to multiple SOS sessions"
                        )
                    streams.setdefault(
                        (event.device_id, event.boot_count, event.session_id), []
                    ).append(event)
                    order = self._current_order(event)
                    candidate = current_candidates.get(event.device_id)
                    if candidate is None or order > candidate[0]:
                        current_candidates[event.device_id] = (
                            order,
                            int(row["id"]),
                        )
                    valid_identities.add(
                        (event.device_id, event.event_id, int(row["id"]))
                    )

                for stream in streams.values():
                    ordered = sorted(
                        stream, key=lambda item: item.source_sequence
                    )
                    for previous, following in zip(ordered, ordered[1:]):
                        if (
                            previous.source_sequence
                            >= following.source_sequence
                            or previous.source_event_time_ms
                            > following.source_event_time_ms
                        ):
                            raise ManualSosStoreCorruptionError(
                                "manual SOS boot-monotonic lineage regressed"
                            )

                expected_current = {
                    device_id: candidate[1]
                    for device_id, candidate in current_candidates.items()
                }

                ack_rows = db.execute(
                    "SELECT * FROM manual_sos_guardian_ack"
                ).fetchall()
                for row in ack_rows:
                    if (
                        (row["device_id"], row["event_id"], row["timeline_id"])
                        not in valid_identities
                        or _SAFE_ID.fullmatch(str(row["guardian_id"])) is None
                        or not isinstance(row["acknowledged_at_ms"], int)
                        or row["acknowledged_at_ms"] < 0
                        or row["acknowledged_at_ms"] > SQLITE_SIGNED_INT64_MAX
                    ):
                        raise ManualSosStoreCorruptionError(
                            "manual SOS Guardian acknowledgement is corrupt"
                        )

                actual_current = {
                    str(row["device_id"]): int(row["timeline_id"])
                    for row in db.execute(
                        "SELECT device_id,timeline_id FROM manual_sos_current"
                    ).fetchall()
                }
                if actual_current != expected_current:
                    db.execute("DELETE FROM manual_sos_current")
                    db.executemany(
                        "INSERT INTO manual_sos_current(device_id,timeline_id) "
                        "VALUES(?,?)",
                        sorted(expected_current.items()),
                    )
                db.commit()
            except ManualSosStoreCorruptionError:
                db.rollback()
                raise
            except (sqlite3.DatabaseError, KeyError, TypeError, ValueError) as error:
                db.rollback()
                raise ManualSosStoreCorruptionError(
                    "manual SOS store recovery failed closed"
                ) from error

    @staticmethod
    def _result(
        status: str,
        event: ValidatedManualSos,
        *,
        timeline_id: int,
        payload_sha256: str,
        server_receive_time_ms: int,
        current_updated: bool,
    ) -> dict[str, Any]:
        return {
            "status": status,
            "identity": event.identity,
            "timeline_id": timeline_id,
            "payload_sha256": payload_sha256,
            "server_receive_time_ms": server_receive_time_ms,
            "current_updated": current_updated,
        }

    def ingest(
        self,
        raw_payload: bytes,
        *,
        server_receive_time_ms: int | None = None,
    ) -> dict[str, Any]:
        event = validate_manual_sos_payload(raw_payload)
        received = (
            int(time.time() * 1000)
            if server_receive_time_ms is None
            else server_receive_time_ms
        )
        received = _sqlite_non_negative_integer(
            received, "server_receive_time_ms"
        )
        digest = hashlib.sha256(raw_payload).hexdigest()

        with self._lock, closing(self._connect()) as db:
            try:
                db.execute("BEGIN IMMEDIATE")
                existing = db.execute(
                    "SELECT * FROM manual_sos_timeline "
                    "WHERE device_id=? AND event_id=?",
                    (event.device_id, event.event_id),
                ).fetchone()
                if existing is not None:
                    self._validated_row(existing)
                    if (
                        existing["payload_sha256"] != digest
                        or self._row_payload(existing) != raw_payload
                    ):
                        raise ManualSosConflictError(
                            "manual SOS durable identity conflicts with exact bytes"
                        )
                    db.commit()
                    return self._result(
                        "duplicate",
                        event,
                        timeline_id=int(existing["id"]),
                        payload_sha256=digest,
                        server_receive_time_ms=int(
                            existing["server_receive_time_ms"]
                        ),
                        current_updated=False,
                    )

                other_session = db.execute(
                    "SELECT session_id FROM manual_sos_timeline WHERE "
                    "device_id=? AND boot_count=? AND session_id<>? LIMIT 1",
                    (event.device_id, event.boot_count, event.session_id),
                ).fetchone()
                if other_session is not None:
                    raise ManualSosConflictError(
                        "one device boot cannot use multiple SOS sessions"
                    )
                lineage = db.execute(
                    "SELECT event_id FROM manual_sos_timeline WHERE "
                    "device_id=? AND boot_count=? AND session_id=? "
                    "AND source_sequence=?",
                    (
                        event.device_id,
                        event.boot_count,
                        event.session_id,
                        event.source_sequence,
                    ),
                ).fetchone()
                if lineage is not None:
                    raise ManualSosConflictError(
                        "manual SOS physical-edge lineage is already bound"
                    )

                predecessor = db.execute(
                    "SELECT source_event_time_ms FROM manual_sos_timeline "
                    "WHERE device_id=? AND boot_count=? AND session_id=? "
                    "AND source_sequence<? ORDER BY source_sequence DESC LIMIT 1",
                    (
                        event.device_id,
                        event.boot_count,
                        event.session_id,
                        event.source_sequence,
                    ),
                ).fetchone()
                successor = db.execute(
                    "SELECT source_event_time_ms FROM manual_sos_timeline "
                    "WHERE device_id=? AND boot_count=? AND session_id=? "
                    "AND source_sequence>? ORDER BY source_sequence LIMIT 1",
                    (
                        event.device_id,
                        event.boot_count,
                        event.session_id,
                        event.source_sequence,
                    ),
                ).fetchone()
                if (
                    predecessor is not None
                    and int(predecessor["source_event_time_ms"])
                    > event.source_event_time_ms
                ) or (
                    successor is not None
                    and event.source_event_time_ms
                    > int(successor["source_event_time_ms"])
                ):
                    raise ManualSosConflictError(
                        "manual SOS boot-monotonic lineage regressed"
                    )

                current_row = db.execute(
                    """SELECT t.* FROM manual_sos_current c
                    JOIN manual_sos_timeline t ON t.id=c.timeline_id
                    WHERE c.device_id=?""",
                    (event.device_id,),
                ).fetchone()
                current_event = (
                    self._validated_row(current_row)
                    if current_row is not None
                    else None
                )
                promote_current = (
                    current_event is None
                    or self._current_order(event)
                    > self._current_order(current_event)
                )

                cursor = db.execute(
                    """INSERT INTO manual_sos_timeline (
                    device_id,event_id,boot_count,session_id,
                    source_event_time_ms,source_sequence,battery_percent,
                    base_online,upload_available,payload_sha256,raw_payload,
                    server_receive_time_ms
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        event.device_id,
                        event.event_id,
                        event.boot_count,
                        event.session_id,
                        event.source_event_time_ms,
                        event.source_sequence,
                        event.battery_percent,
                        int(event.base_online),
                        int(event.upload_available),
                        digest,
                        sqlite3.Binary(raw_payload),
                        received,
                    ),
                )
                timeline_id = int(cursor.lastrowid)
                if promote_current:
                    db.execute(
                        """INSERT INTO manual_sos_current(device_id,timeline_id)
                        VALUES(?,?) ON CONFLICT(device_id) DO UPDATE SET
                        timeline_id=excluded.timeline_id""",
                        (event.device_id, timeline_id),
                    )
                db.commit()
                return self._result(
                    "accepted",
                    event,
                    timeline_id=timeline_id,
                    payload_sha256=digest,
                    server_receive_time_ms=received,
                    current_updated=promote_current,
                )
            except (ManualSosConflictError, ManualSosStoreCorruptionError):
                db.rollback()
                raise
            except sqlite3.IntegrityError as error:
                db.rollback()
                raise ManualSosConflictError(
                    "manual SOS durable identity conflicts"
                ) from error
            except sqlite3.DatabaseError as error:
                db.rollback()
                raise ManualSosStoreError(
                    "manual SOS durable transaction failed"
                ) from error

    def latest_alert(
        self,
        device_id: str,
        *,
        authorization_subject: str,
    ) -> dict[str, Any]:
        # The HTTP boundary must already have authenticated this subject and
        # proved its exact device binding. This argument records that explicit
        # precondition; the store is not a second row-level authorizer.
        device = _safe_id(device_id, "device_id")
        _safe_id(authorization_subject, "authorization_subject")
        with self._lock, closing(self._connect()) as db:
            try:
                row = db.execute(
                    """SELECT t.*,a.acknowledged_at_ms
                    FROM manual_sos_current c
                    JOIN manual_sos_timeline t ON t.id=c.timeline_id
                    LEFT JOIN manual_sos_guardian_ack a
                      ON a.device_id=t.device_id AND a.event_id=t.event_id
                    WHERE c.device_id=?""",
                    (device,),
                ).fetchone()
            except sqlite3.DatabaseError as error:
                raise ManualSosStoreError(
                    "manual SOS latest-alert query failed"
                ) from error
        if row is None:
            return {
                "available": False,
                "device_id": device,
                "event_type": "manual_sos",
                "guardian_ack_state": "not_applicable",
                "call_state": "not_reported",
                "reason": "no_durable_manual_sos",
            }
        event = self._validated_row(row)
        acknowledged_at = row["acknowledged_at_ms"]
        if acknowledged_at is not None:
            _sqlite_non_negative_integer(
                acknowledged_at, "acknowledged_at_ms"
            )
        return {
            "available": True,
            "device_id": event.device_id,
            "event_id": event.event_id,
            "event_type": "manual_sos",
            "priority": "critical",
            "source": "device_rule",
            "source_event_time_ms": event.source_event_time_ms,
            "time_source": "boot_monotonic_ms",
            "battery": {
                "percent": event.battery_percent,
                "state": "unknown" if event.battery_percent is None else "reported",
            },
            "server_receipt": {
                "state": "durably_received",
                "received_at_ms": int(row["server_receive_time_ms"]),
            },
            "delivery_state": "server_durable_ingest_only",
            "guardian_ack_state": (
                "acknowledged"
                if acknowledged_at is not None
                else "not_acknowledged"
            ),
            "guardian_acknowledged_at_ms": acknowledged_at,
            "call_state": "not_reported",
            "non_claims": [
                "guardian_push_not_implemented",
                "human_notification_not_proven",
                "call_state_not_reported",
            ],
        }

    def acknowledge(
        self,
        device_id: str,
        event_id: str,
        *,
        guardian_id: str,
        acknowledged_at_ms: int | None = None,
    ) -> dict[str, Any]:
        device = _safe_id(device_id, "device_id")
        event = _safe_id(event_id, "event_id")
        guardian = _safe_id(guardian_id, "guardian_id")
        acknowledged = (
            int(time.time() * 1000)
            if acknowledged_at_ms is None
            else acknowledged_at_ms
        )
        acknowledged = _sqlite_non_negative_integer(
            acknowledged, "acknowledged_at_ms"
        )

        with self._lock, closing(self._connect()) as db:
            try:
                db.execute("BEGIN IMMEDIATE")
                timeline = db.execute(
                    "SELECT id FROM manual_sos_timeline "
                    "WHERE device_id=? AND event_id=?",
                    (device, event),
                ).fetchone()
                if timeline is None:
                    raise ManualSosNotFoundError(
                        "manual SOS event is not durably stored"
                    )
                existing = db.execute(
                    "SELECT acknowledged_at_ms FROM manual_sos_guardian_ack "
                    "WHERE device_id=? AND event_id=?",
                    (device, event),
                ).fetchone()
                if existing is not None:
                    db.commit()
                    return {
                        "status": "duplicate",
                        "device_id": device,
                        "event_id": event,
                        "guardian_ack_state": "acknowledged",
                        "acknowledged_at_ms": int(
                            existing["acknowledged_at_ms"]
                        ),
                        "call_state": "not_reported",
                    }
                db.execute(
                    """INSERT INTO manual_sos_guardian_ack(
                    device_id,event_id,timeline_id,guardian_id,
                    acknowledged_at_ms) VALUES(?,?,?,?,?)""",
                    (
                        device,
                        event,
                        int(timeline["id"]),
                        guardian,
                        acknowledged,
                    ),
                )
                db.commit()
                return {
                    "status": "accepted",
                    "device_id": device,
                    "event_id": event,
                    "guardian_ack_state": "acknowledged",
                    "acknowledged_at_ms": acknowledged,
                    "call_state": "not_reported",
                }
            except ManualSosNotFoundError:
                db.rollback()
                raise
            except sqlite3.DatabaseError as error:
                db.rollback()
                raise ManualSosStoreError(
                    "manual SOS Guardian acknowledgement failed"
                ) from error

    def timeline_length(self, device_id: str) -> int:
        device = _safe_id(device_id, "device_id")
        with self._lock, closing(self._connect()) as db:
            return int(
                db.execute(
                    "SELECT COUNT(*) FROM manual_sos_timeline WHERE device_id=?",
                    (device,),
                ).fetchone()[0]
            )


__all__ = [
    "MAX_MANUAL_SOS_BODY_BYTES",
    "ManualSosConflictError",
    "ManualSosNotFoundError",
    "ManualSosStore",
    "ManualSosStoreCorruptionError",
    "ManualSosStoreError",
    "ManualSosValidationError",
    "SQLITE_SIGNED_INT64_MAX",
    "ValidatedManualSos",
    "validate_manual_sos_payload",
]

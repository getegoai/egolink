"""SQLite persistence boundary for the stdlib Location State runtime."""

from __future__ import annotations

from copy import deepcopy
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any, Mapping

from server.location_state_runtime import (
    DEFAULT_SENSOR_POLICY_CONFIG,
    LocationStateConflictError,
    LocationStateMirrorError,
    LocationStateRuntimeMirror,
    LocationStateValidationError,
)


SQLITE_INTEGER_MAX = (1 << 63) - 1


def _sqlite_non_negative_integer(value: Any, name: str) -> int:
    """Validate values persisted in SQLite INTEGER columns before staging."""

    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value > SQLITE_INTEGER_MAX
    ):
        raise LocationStateValidationError(
            f"{name} must fit a non-negative SQLite integer"
        )
    return value


class LocationStateStore:
    """Append accepted envelopes and recover the derived mirror after restart."""

    def __init__(self, db_path: str | Path, policy_config: str | Path = DEFAULT_SENSOR_POLICY_CONFIG) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._policy_config = Path(policy_config)
        self._mirror = self._new_mirror()
        if self._mirror.policy_identity["config_hash"] != "c9445e465f22d732c07477d6d32b7985db6478871355df96b5285086ba6ded6d":
            raise LocationStateValidationError("sensor policy configuration hash is not the deployed accepted identity")
        self._init_schema()
        self._mirror = self._load_mirror()

    def _new_mirror(self) -> LocationStateRuntimeMirror:
        return LocationStateRuntimeMirror(self._policy_config)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path)
        db.row_factory = sqlite3.Row
        return db

    def _init_schema(self) -> None:
        with closing(self._connect()) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS location_state_timeline (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    boot_count INTEGER NOT NULL,
                    session_id TEXT NOT NULL,
                    event_time_ns INTEGER NOT NULL,
                    sequence_id INTEGER NOT NULL,
                    observation_id TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    envelope_json TEXT NOT NULL,
                    server_receive_time_ms INTEGER NOT NULL,
                    UNIQUE(device_id, boot_count, session_id, event_time_ns, sequence_id, observation_id),
                    UNIQUE(device_id, observation_id),
                    UNIQUE(device_id, boot_count, session_id, sequence_id)
                );
                CREATE INDEX IF NOT EXISTS idx_location_state_timeline_device
                ON location_state_timeline(device_id, id);
                CREATE TABLE IF NOT EXISTS location_state_current (
                    device_id TEXT PRIMARY KEY,
                    timeline_id INTEGER NOT NULL,
                    envelope_json TEXT NOT NULL,
                    FOREIGN KEY(timeline_id) REFERENCES location_state_timeline(id)
                );
            """)

    def _load_mirror(self) -> LocationStateRuntimeMirror:
        mirror = self._new_mirror()
        with closing(self._connect()) as db:
            try:
                # Hold one SQLite write transaction while validating the source
                # timeline and reconciling its derived-current cache. This keeps
                # a repair atomic relative to other SQLite writers.
                db.execute("BEGIN IMMEDIATE")
                rows = db.execute(
                    """SELECT id,device_id,boot_count,session_id,event_time_ns,
                    sequence_id,observation_id,content_hash,envelope_json,
                    server_receive_time_ms
                    FROM location_state_timeline ORDER BY id"""
                ).fetchall()
                expected_current: dict[str, tuple[int, str]] = {}
                for row in rows:
                    try:
                        envelope = json.loads(row["envelope_json"])
                        if not isinstance(envelope, Mapping):
                            raise LocationStateValidationError(
                                "persisted location envelope must be an object"
                            )
                        if envelope.get("server_receive_time_ms") != row["server_receive_time_ms"]:
                            raise LocationStateValidationError("persisted receive-time evidence mismatch")
                        result = mirror.ingest(envelope)
                        if result["status"] != "accepted":
                            raise LocationStateValidationError(
                                "persisted location timeline contains a duplicate identity"
                            )
                        identity = result["identity"]
                        indexed_values = {
                            "device_id": identity["device_id"],
                            "boot_count": identity["boot_count"],
                            "session_id": identity["session_id"],
                            "event_time_ns": envelope["event_time_ns"],
                            "sequence_id": identity["sequence_id"],
                            "observation_id": identity["observation_id"],
                        }
                        if any(row[field] != value for field, value in indexed_values.items()):
                            raise LocationStateValidationError(
                                "persisted location timeline index does not match its envelope"
                            )
                        record = mirror.current_record(identity["device_id"])
                        if record is None or record["content_hash"] != row["content_hash"]:
                            raise LocationStateValidationError("persisted location content hash mismatch")
                        expected_current[identity["device_id"]] = (
                            row["id"],
                            row["envelope_json"],
                        )
                    except (
                        json.JSONDecodeError,
                        LocationStateMirrorError,
                        TypeError,
                    ) as exc:
                        raise LocationStateValidationError(
                            "persisted location timeline failed closed during recovery"
                        ) from exc

                actual_rows = db.execute(
                    "SELECT device_id,timeline_id,envelope_json FROM location_state_current"
                ).fetchall()
                actual_current = {
                    row["device_id"]: (row["timeline_id"], row["envelope_json"])
                    for row in actual_rows
                }
                if actual_current != expected_current:
                    db.execute("DELETE FROM location_state_current")
                    db.executemany(
                        """INSERT INTO location_state_current
                        (device_id,timeline_id,envelope_json) VALUES(?,?,?)""",
                        [
                            (device_id, timeline_id, envelope_json)
                            for device_id, (timeline_id, envelope_json) in sorted(
                                expected_current.items()
                            )
                        ],
                    )
                db.commit()
            except Exception:
                db.rollback()
                raise
        return mirror

    @property
    def policy_identity(self) -> dict[str, str]:
        with self._lock:
            return self._mirror.policy_identity

    def ingest(self, envelope: Mapping[str, Any], *, server_receive_time_ms: int | None = None) -> dict[str, Any]:
        received = int(time.time() * 1000) if server_receive_time_ms is None else server_receive_time_ms
        received = _sqlite_non_negative_integer(received, "server receive time")
        accepted = deepcopy(dict(envelope))
        # JSON integers are unbounded, whereas SQLite INTEGER is signed int64.
        # Reject incompatible source identities at the adapter boundary so a
        # contract-valid hostile value becomes a stable 422 instead of a 500.
        for field in ("boot_count", "event_time_ns", "sequence_id"):
            _sqlite_non_negative_integer(accepted.get(field), field)
        accepted["server_receive_time_ms"] = received
        with self._lock:
            # The live mirror is already the validated durable state from
            # startup or the last committed ingest. Clone it for transactional
            # staging instead of replaying the full SQLite timeline (and
            # taking a database write lock) for every observation.
            staging = deepcopy(self._mirror)
            result = staging.ingest(accepted)
            identity = result["identity"]
            record = staging.current_record(identity["device_id"])
            assert record is not None
            payload = json.dumps(accepted, sort_keys=True, separators=(",", ":"), allow_nan=False)
            self._persist(result, identity, record, accepted, payload, received)
            self._mirror = staging
            return result

    def _persist(self, result: dict[str, Any], identity: dict[str, Any], record: dict[str, Any], accepted: dict[str, Any], payload: str, received: int) -> None:
        with closing(self._connect()) as db:
            try:
                if result["status"] == "duplicate":
                    row = db.execute(
                        "SELECT server_receive_time_ms FROM location_state_timeline WHERE device_id=? AND observation_id=?",
                        (identity["device_id"], identity["observation_id"]),
                    ).fetchone()
                    if row is None:
                        raise LocationStateConflictError("runtime/database location identity mismatch")
                    return
                cursor = db.execute(
                    """INSERT INTO location_state_timeline
                    (device_id,boot_count,session_id,event_time_ns,sequence_id,observation_id,content_hash,envelope_json,server_receive_time_ms)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                    (identity["device_id"], identity["boot_count"], identity["session_id"],
                     accepted["event_time_ns"], identity["sequence_id"], identity["observation_id"],
                     record["content_hash"], payload, received),
                )
                db.execute(
                    """INSERT INTO location_state_current(device_id,timeline_id,envelope_json) VALUES(?,?,?)
                    ON CONFLICT(device_id) DO UPDATE SET timeline_id=excluded.timeline_id,envelope_json=excluded.envelope_json""",
                    (identity["device_id"], cursor.lastrowid, payload),
                )
                db.commit()
            except Exception:
                db.rollback()
                raise

    def current(self, device_id: str, *, location_access_authorized: bool = False, **view: Any) -> dict[str, Any]:
        with self._lock:
            return self._mirror.guardian_snapshot(
                device_id,
                location_access_authorized=location_access_authorized,
                **view,
            )

    def timeline_length(self, device_id: str) -> int:
        with self._lock:
            return len(self._mirror.timeline(device_id))

    def authenticated_current(
        self,
        device_id: str,
        *,
        utc_now_ns: int,
        location_access_authorized: bool = False,
        authorization_subject: str | None = None,
    ) -> dict[str, Any]:
        """Return an exact position only after an external device binding."""

        if location_access_authorized and not authorization_subject:
            raise LocationStateValidationError(
                "authorized location view requires an authorization subject"
            )
        authorization_fields = {
            "authorization_scope": (
                "binding_file"
                if location_access_authorized
                else "single_token_redacted"
            ),
            "authorization_subject": (
                authorization_subject if location_access_authorized else None
            ),
        }
        with self._lock:
            record = self._mirror.current_record(device_id)
            if record is None:
                snapshot = self._mirror.guardian_snapshot(
                    device_id,
                    view_event_time_ns=utc_now_ns,
                    view_event_time_source="timestamp_utc_ns",
                    stale_after_ms=300_000,
                    offline_after_ms=900_000,
                    location_access_authorized=location_access_authorized,
                )
                snapshot.update(
                    {
                        "freshness": "unavailable",
                        "reason": "no_accepted_location_state",
                        "non_claims": (
                            ["no_accepted_location_state"]
                            if location_access_authorized
                            else [
                                "single_token_has_no_guardian_device_binding",
                                "exact_position_authorization_unavailable",
                            ]
                        ),
                        **authorization_fields,
                    }
                )
                return snapshot
            clock = record["event_clock"]
            if clock["event_time_source"] == "timestamp_monotonic_ns":
                return self._unavailable_freshness_current(
                    device_id,
                    record=record,
                    reason="monotonic_clock_mapping_unavailable",
                    location_access_authorized=location_access_authorized,
                    authorization_subject=authorization_subject,
                )
            if utc_now_ns < clock["event_time_ns"]:
                return self._unavailable_freshness_current(
                    device_id,
                    record=record,
                    reason="source_clock_ahead",
                    location_access_authorized=location_access_authorized,
                    authorization_subject=authorization_subject,
                )
            snapshot = self._mirror.guardian_snapshot(
                device_id,
                view_event_time_ns=utc_now_ns,
                view_event_time_source="timestamp_utc_ns",
                stale_after_ms=300_000,
                offline_after_ms=900_000,
                location_access_authorized=location_access_authorized,
            )
            snapshot.update(
                {
                    "freshness": "stale" if snapshot["stale"] else "fresh",
                    "reason": "source_clock_comparable",
                    "non_claims": (
                        []
                        if location_access_authorized
                        else [
                            "single_token_has_no_guardian_device_binding",
                            "exact_position_authorization_unavailable",
                        ]
                    ),
                    **authorization_fields,
                }
            )
            return snapshot

    def _unavailable_freshness_current(
        self,
        device_id: str,
        *,
        record: Mapping[str, Any],
        reason: str,
        location_access_authorized: bool = False,
        authorization_subject: str | None = None,
    ) -> dict[str, Any]:
        """Project validated state while keeping all time-derived truth unknown."""

        clock = record["event_clock"]
        # Reuse the accepted projection at the source event itself only to
        # retain non-age state fields. None of its derived age/connectivity
        # values survive below, so this cannot present event age zero as fresh.
        snapshot = self._mirror.guardian_snapshot(
            device_id,
            view_event_time_ns=clock["event_time_ns"],
            view_event_time_source=clock["event_time_source"],
            monotonic_clock_domain_id=clock["monotonic_clock_domain_id"],
            stale_after_ms=300_000,
            offline_after_ms=900_000,
            location_access_authorized=location_access_authorized,
        )
        snapshot.update(
            {
                "position": (
                    snapshot.get("position")
                    if location_access_authorized
                    else None
                ),
                "state_age_ms": None,
                "location_age_ms": None,
                "location_age_status": "unavailable",
                "freshness": "unavailable",
                "stale": None,
                "offline": None,
                "offline_status": "unavailable",
                "freshness_reason_codes": [reason],
                "reason": reason,
                "non_claims": (
                    ["receive_time_not_used_as_event_time"]
                    if location_access_authorized
                    else [
                        "single_token_has_no_guardian_device_binding",
                        "receive_time_not_used_as_event_time",
                        "exact_position_authorization_unavailable",
                    ]
                ),
                "authorization_scope": (
                    "binding_file"
                    if location_access_authorized
                    else "single_token_redacted"
                ),
                "authorization_subject": (
                    authorization_subject
                    if location_access_authorized
                    else None
                ),
            }
        )
        return snapshot

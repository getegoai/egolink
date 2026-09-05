from __future__ import annotations

from contextlib import closing
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

from jsonschema import Draft202012Validator

from server.manual_sos_store import (
    MAX_MANUAL_SOS_BODY_BYTES,
    ManualSosConflictError,
    ManualSosNotFoundError,
    ManualSosStore,
    ManualSosStoreCorruptionError,
    ManualSosValidationError,
    SQLITE_SIGNED_INT64_MAX,
    validate_manual_sos_payload,
)


DEVICE_ID = "wearable-node-001"


def manual_sos_document(
    *,
    device_id: str = DEVICE_ID,
    boot_count: int = 7,
    session_id: str = "boot-session-007",
    source_sequence: int = 11,
    source_event_time_ms: int = 42_050,
    battery_percent: int | None = None,
) -> dict[str, object]:
    event_id = (
        f"sos-b{boot_count}-q{source_sequence}-t{source_event_time_ms}"
    )
    return {
        "contract_version": "1.0.0",
        "event_id": event_id,
        "device_id": device_id,
        "timestamp_ms": source_event_time_ms,
        "sequence": source_sequence,
        "event_type": "manual_sos",
        "priority": "critical",
        "source": "device_rule",
        "model_result": {
            "manual_input": True,
            "qualified_long_press": True,
            "time_source": "boot_monotonic_ms",
            "boot_count": boot_count,
            "session_id": session_id,
            "source_sequence": source_sequence,
        },
        "context": {
            "mode": "manual_sos",
            "battery_percent": battery_percent,
            "base_online": False,
            "upload_available": False,
        },
        "evidence": {
            "audio_clip_ref": None,
            "image_ref": None,
            "imu_window_ref": None,
            "location_fresh": False,
        },
        "privacy": {
            "privacy_mode": True,
            "raw_evidence_allowed": False,
            "retention_seconds": 86400,
        },
    }


def manual_sos_raw(**values: object) -> bytes:
    return json.dumps(
        manual_sos_document(**values),
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


class ManualSosStoreTests(unittest.TestCase):
    def test_device_subset_is_valid_under_the_existing_safety_event_contract(self) -> None:
        schema = json.loads(
            (
                Path(__file__).resolve().parents[1]
                / "shared"
                / "contracts"
                / "safety_event.schema.json"
            ).read_text(encoding="utf-8")
        )
        Draft202012Validator.check_schema(schema)
        for battery in (None, 0, 100):
            self.assertEqual(
                [],
                list(
                    Draft202012Validator(schema).iter_errors(
                        manual_sos_document(battery_percent=battery)
                    )
                ),
            )

    def test_exact_bytes_are_durable_duplicate_is_idempotent_and_conflict_is_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            db_path = Path(root) / "hub.db"
            store = ManualSosStore(db_path)
            raw = manual_sos_raw(battery_percent=63)
            first = store.ingest(raw, server_receive_time_ms=1000)
            duplicate = store.ingest(raw, server_receive_time_ms=2000)
            reformatted = json.dumps(
                manual_sos_document(battery_percent=63), indent=2
            ).encode("utf-8")
            with self.assertRaises(ManualSosConflictError):
                store.ingest(reformatted, server_receive_time_ms=3000)

            with closing(sqlite3.connect(db_path)) as db:
                row = db.execute(
                    "SELECT raw_payload,payload_sha256,server_receive_time_ms "
                    "FROM manual_sos_timeline"
                ).fetchone()
                timeline_count = db.execute(
                    "SELECT COUNT(*) FROM manual_sos_timeline"
                ).fetchone()[0]

        digest = hashlib.sha256(raw).hexdigest()
        self.assertEqual("accepted", first["status"])
        self.assertTrue(first["current_updated"])
        self.assertEqual("duplicate", duplicate["status"])
        self.assertFalse(duplicate["current_updated"])
        self.assertEqual(1000, duplicate["server_receive_time_ms"])
        self.assertEqual(digest, first["payload_sha256"])
        self.assertEqual(raw, row[0])
        self.assertEqual(digest, row[1])
        self.assertEqual(1000, row[2])
        self.assertEqual(1, timeline_count)

    def test_strict_subset_rejects_ambiguity_coordinates_media_nan_and_integer_overflow(self) -> None:
        valid = manual_sos_document()
        cases: dict[str, bytes] = {}

        duplicate = manual_sos_raw().replace(
            b'"device_id":"wearable-node-001"',
            b'"device_id":"wearable-node-001","device_id":"other"',
            1,
        )
        cases["duplicate member"] = duplicate

        coordinate = deepcopy(valid)
        coordinate["context"]["latitude"] = 22.5  # type: ignore[index]
        cases["coordinate"] = json.dumps(coordinate).encode()

        media = deepcopy(valid)
        media["evidence"]["audio_clip_ref"] = "secret-audio"  # type: ignore[index]
        cases["media"] = json.dumps(media).encode()

        nan = deepcopy(valid)
        nan["context"]["battery_percent"] = float("nan")  # type: ignore[index]
        cases["non-finite"] = json.dumps(nan, allow_nan=True).encode()

        float_battery = deepcopy(valid)
        float_battery["context"]["battery_percent"] = 12.5  # type: ignore[index]
        cases["non-device battery"] = json.dumps(float_battery).encode()

        bad_lineage = deepcopy(valid)
        bad_lineage["sequence"] = 12
        cases["lineage mismatch"] = json.dumps(bad_lineage).encode()

        overflow = manual_sos_document(
            boot_count=SQLITE_SIGNED_INT64_MAX + 1,
            session_id="overflow-session",
        )
        cases["SQLite overflow"] = json.dumps(overflow).encode()

        wrong_priority = deepcopy(valid)
        wrong_priority["priority"] = "high"
        cases["wrong priority"] = json.dumps(wrong_priority).encode()

        boolean_sequence = deepcopy(valid)
        boolean_sequence["sequence"] = True
        cases["boolean integer"] = json.dumps(boolean_sequence).encode()

        cases["oversized"] = b"{" + b" " * MAX_MANUAL_SOS_BODY_BYTES

        with tempfile.TemporaryDirectory() as root:
            db_path = Path(root) / "hub.db"
            store = ManualSosStore(db_path)
            for name, raw in cases.items():
                with self.subTest(name=name):
                    with self.assertRaises(ManualSosValidationError):
                        store.ingest(raw, server_receive_time_ms=1)
            with closing(sqlite3.connect(db_path)) as db:
                count = db.execute(
                    "SELECT COUNT(*) FROM manual_sos_timeline"
                ).fetchone()[0]
        self.assertEqual(0, count)

    def test_current_uses_device_lineage_not_arrival_order_and_rebuild_matches(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            db_path = Path(root) / "hub.db"
            store = ManualSosStore(db_path)
            newest = manual_sos_raw(
                boot_count=9,
                session_id="boot-9",
                source_sequence=3,
                source_event_time_ms=9000,
            )
            old_boot_late = manual_sos_raw(
                boot_count=8,
                session_id="boot-8",
                source_sequence=99,
                source_event_time_ms=99_000,
            )
            older_same_stream = manual_sos_raw(
                boot_count=9,
                session_id="boot-9",
                source_sequence=2,
                source_event_time_ms=8000,
            )
            self.assertTrue(
                store.ingest(newest, server_receive_time_ms=100)[
                    "current_updated"
                ]
            )
            self.assertFalse(
                store.ingest(old_boot_late, server_receive_time_ms=200)[
                    "current_updated"
                ]
            )
            self.assertFalse(
                store.ingest(older_same_stream, server_receive_time_ms=300)[
                    "current_updated"
                ]
            )
            alert = store.latest_alert(
                DEVICE_ID, authorization_subject="guardian-001"
            )
            self.assertEqual("sos-b9-q3-t9000", alert["event_id"])

            with closing(sqlite3.connect(db_path)) as db:
                old_id = db.execute(
                    "SELECT id FROM manual_sos_timeline WHERE boot_count=8"
                ).fetchone()[0]
                db.execute(
                    "UPDATE manual_sos_current SET timeline_id=? WHERE device_id=?",
                    (old_id, DEVICE_ID),
                )
                db.commit()

            reopened = ManualSosStore(db_path)
            repaired = reopened.latest_alert(
                DEVICE_ID, authorization_subject="guardian-001"
            )
            self.assertEqual("sos-b9-q3-t9000", repaired["event_id"])
            self.assertEqual(3, reopened.timeline_length(DEVICE_ID))

    def test_same_boot_session_ambiguity_and_monotonic_regression_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            store = ManualSosStore(Path(root) / "hub.db")
            store.ingest(
                manual_sos_raw(
                    boot_count=4,
                    session_id="boot-4",
                    source_sequence=2,
                    source_event_time_ms=2000,
                ),
                server_receive_time_ms=1,
            )
            for raw in (
                manual_sos_raw(
                    boot_count=4,
                    session_id="other-session",
                    source_sequence=3,
                    source_event_time_ms=3000,
                ),
                manual_sos_raw(
                    boot_count=4,
                    session_id="boot-4",
                    source_sequence=3,
                    source_event_time_ms=1000,
                ),
                manual_sos_raw(
                    boot_count=4,
                    session_id="boot-4",
                    source_sequence=1,
                    source_event_time_ms=3000,
                ),
            ):
                with self.assertRaises(ManualSosConflictError):
                    store.ingest(raw, server_receive_time_ms=2)
            self.assertEqual(1, store.timeline_length(DEVICE_ID))

    def test_guardian_ack_is_separate_durable_idempotent_and_never_deletes_event(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            db_path = Path(root) / "hub.db"
            store = ManualSosStore(db_path)
            result = store.ingest(manual_sos_raw(), server_receive_time_ms=10)
            event_id = result["identity"]["event_id"]
            first = store.acknowledge(
                DEVICE_ID,
                event_id,
                guardian_id="guardian-001",
                acknowledged_at_ms=20,
            )
            duplicate = store.acknowledge(
                DEVICE_ID,
                event_id,
                guardian_id="guardian-002",
                acknowledged_at_ms=30,
            )
            with self.assertRaises(ManualSosNotFoundError):
                store.acknowledge(
                    DEVICE_ID,
                    "sos-b7-q99-t99999",
                    guardian_id="guardian-001",
                    acknowledged_at_ms=40,
                )

            reopened = ManualSosStore(db_path)
            alert = reopened.latest_alert(
                DEVICE_ID, authorization_subject="guardian-001"
            )
            with closing(sqlite3.connect(db_path)) as db:
                timeline = db.execute(
                    "SELECT COUNT(*) FROM manual_sos_timeline"
                ).fetchone()[0]
                ack_count = db.execute(
                    "SELECT COUNT(*) FROM manual_sos_guardian_ack"
                ).fetchone()[0]

        self.assertEqual("accepted", first["status"])
        self.assertEqual("duplicate", duplicate["status"])
        self.assertEqual(20, duplicate["acknowledged_at_ms"])
        self.assertEqual("acknowledged", alert["guardian_ack_state"])
        self.assertEqual("not_reported", alert["call_state"])
        self.assertEqual(1, timeline)
        self.assertEqual(1, ack_count)

    def test_projection_is_metadata_only_and_unknown_battery_stays_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            store = ManualSosStore(Path(root) / "hub.db")
            store.ingest(manual_sos_raw(), server_receive_time_ms=10)
            alert = store.latest_alert(
                DEVICE_ID, authorization_subject="guardian-001"
            )
        serialized = json.dumps(alert, sort_keys=True)
        self.assertIsNone(alert["battery"]["percent"])
        self.assertEqual("unknown", alert["battery"]["state"])
        self.assertEqual("not_acknowledged", alert["guardian_ack_state"])
        self.assertEqual("not_reported", alert["call_state"])
        for forbidden in (
            "raw_payload",
            "payload_sha256",
            "session_id",
            "boot_count",
            "source_sequence",
            "audio_clip_ref",
            "image_ref",
            "imu_window_ref",
            "latitude",
            "longitude",
            "coordinate",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_restart_fails_closed_when_timeline_exact_bytes_are_corrupt(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            db_path = Path(root) / "hub.db"
            store = ManualSosStore(db_path)
            store.ingest(manual_sos_raw(), server_receive_time_ms=10)
            with closing(sqlite3.connect(db_path)) as db:
                db.execute(
                    "UPDATE manual_sos_timeline SET raw_payload=?",
                    (sqlite3.Binary(b"{}"),),
                )
                db.commit()
            with self.assertRaises(ManualSosStoreCorruptionError):
                ManualSosStore(db_path)

    def test_concurrent_exact_replays_create_one_timeline_row(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            store = ManualSosStore(Path(root) / "hub.db")
            raw = manual_sos_raw()
            statuses: list[str] = []
            failures: list[BaseException] = []
            lock = threading.Lock()

            def ingest() -> None:
                try:
                    status = store.ingest(
                        raw, server_receive_time_ms=50
                    )["status"]
                    with lock:
                        statuses.append(status)
                except BaseException as error:  # pragma: no cover - assertion aid.
                    with lock:
                        failures.append(error)

            threads = [threading.Thread(target=ingest) for _ in range(8)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=5)

            self.assertFalse(failures)
            self.assertEqual(1, statuses.count("accepted"))
            self.assertEqual(7, statuses.count("duplicate"))
            self.assertEqual(1, store.timeline_length(DEVICE_ID))

    def test_sqlite_time_bounds_apply_before_any_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            store = ManualSosStore(Path(root) / "hub.db")
            with self.assertRaises(ManualSosValidationError):
                store.ingest(
                    manual_sos_raw(),
                    server_receive_time_ms=SQLITE_SIGNED_INT64_MAX + 1,
                )
            self.assertEqual(0, store.timeline_length(DEVICE_ID))

        validated = validate_manual_sos_payload(manual_sos_raw())
        self.assertEqual(DEVICE_ID, validated.device_id)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from jsonschema import Draft202012Validator

from pc_simulator.persistent_priority_outbox import (
    ACK_CONTRACT_VERSION,
    MIRROR_FILE_NAME,
    PRIMARY_FILE_NAME,
    OutboxConfigurationError,
    OutboxCorruptionError,
    OutboxFullError,
    OutboxIdentityConflictError,
    OutboxOverflowError,
    OutboxPrivacyError,
    OutboxValidationError,
    PersistentPriorityOutbox,
    positive_ack_for,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = (
    ROOT / "shared" / "contracts" / "persistent_priority_outbox_v0.schema.json"
)
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


class PersistentPriorityOutboxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.storage_dir = Path(self.temp.name)
        self.validator = Draft202012Validator(SCHEMA)
        self.outbox = PersistentPriorityOutbox(
            self.storage_dir,
            device_id="ego-test-device-1",
            max_records=4,
            reserved_critical_records=1,
            max_total_payload_bytes=4096,
            max_payload_bytes=1024,
            base_retry_ms=100,
            max_retry_ms=250,
            tombstone_capacity=2,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def enqueue(
        self,
        event_id: str = "event-1",
        *,
        event_type: str = "status_observation",
        priority: str = "normal",
        payload: dict | None = None,
        now_ms: int = 1_000,
        source_event_time_ms: int = 900,
        boot_count: int = 7,
        session_id: str = "boot-session-7",
        source_sequence: int = 12,
    ) -> dict:
        return self.outbox.enqueue(
            event_id=event_id,
            event_type=event_type,
            priority=priority,
            payload=payload or {"state": "pending", "belief_ref": "belief-12"},
            source_event_time_ms=source_event_time_ms,
            boot_count=boot_count,
            session_id=session_id,
            source_sequence=source_sequence,
            now_ms=now_ms,
        )

    def assert_schema_valid(self, document: dict) -> None:
        errors = sorted(
            self.validator.iter_errors(document), key=lambda error: error.json_path
        )
        self.assertEqual(
            [], [f"{error.json_path}: {error.message}" for error in errors]
        )

    def test_schema_is_well_formed_and_persisted_document_validates(self) -> None:
        Draft202012Validator.check_schema(SCHEMA)
        self.enqueue()
        document = self.outbox.export_storage_document()
        self.assert_schema_valid(document)

        primary = json.loads(
            (self.storage_dir / PRIMARY_FILE_NAME).read_text(encoding="utf-8")
        )
        mirror = json.loads(
            (self.storage_dir / MIRROR_FILE_NAME).read_text(encoding="utf-8")
        )
        self.assertEqual(primary, mirror)
        self.assert_schema_valid(primary)
        self.assertFalse(list(self.storage_dir.glob("*.tmp")))

    def test_enqueue_is_durable_before_send_selection_and_identity_is_stable(self) -> None:
        record = self.enqueue()
        primary = json.loads(
            (self.storage_dir / PRIMARY_FILE_NAME).read_text(encoding="utf-8")
        )
        self.assertEqual("event-1", primary["records"][0]["event_id"])
        self.assertEqual(record["payload_sha256"], primary["records"][0]["payload_sha256"])

        attempt = self.outbox.begin_send_attempt(now_ms=1_000)
        self.assertIsNotNone(attempt)
        for immutable in (
            "device_id",
            "event_id",
            "payload_sha256",
            "identity_sha256",
            "source_event_time_ms",
            "boot_count",
            "session_id",
            "source_sequence",
        ):
            self.assertEqual(record[immutable], attempt[immutable])
        persisted = json.loads(
            (self.storage_dir / PRIMARY_FILE_NAME).read_text(encoding="utf-8")
        )
        self.assertEqual("attempt_started", persisted["records"][0]["send_state"])
        self.assertEqual(attempt["last_attempt_token"], persisted["records"][0]["last_attempt_token"])

    def test_failed_send_uses_bounded_exponential_backoff_across_retries(self) -> None:
        original = self.enqueue()
        expected = [(1_000, 1_100), (1_100, 1_300), (1_300, 1_550), (1_550, 1_800)]
        tokens: list[str] = []
        for attempt_time, expected_retry in expected:
            attempt = self.outbox.begin_send_attempt(now_ms=attempt_time)
            self.assertIsNotNone(attempt)
            tokens.append(attempt["last_attempt_token"])
            self.assertEqual(expected_retry, attempt["next_retry_time_ms"])
            self.assertEqual(original["identity_sha256"], attempt["identity_sha256"])
            result = self.outbox.record_transport_result(
                attempt_token=attempt["last_attempt_token"],
                accepted_by_transport=False,
                now_ms=attempt_time + 1,
                error_code="NETWORK_UNAVAILABLE",
            )
            self.assertEqual("recorded", result)
            self.assertEqual(
                "duplicate",
                self.outbox.record_transport_result(
                    attempt_token=attempt["last_attempt_token"],
                    accepted_by_transport=False,
                    now_ms=attempt_time + 1,
                    error_code="NETWORK_UNAVAILABLE",
                ),
            )
            self.assertIsNone(
                self.outbox.begin_send_attempt(now_ms=expected_retry - 1)
            )
        self.assertEqual(4, len(set(tokens)))
        snapshot = self.outbox.snapshot(now_ms=1_600)
        self.assertEqual(4, snapshot["metrics"]["send_attempt_count"])
        self.assertEqual(4, snapshot["metrics"]["send_failure_count"])
        self.assertEqual("retry_wait", snapshot["records"][0]["send_state"])

    def test_transport_acceptance_never_deletes_without_matching_positive_ack(self) -> None:
        record = self.enqueue()
        attempt = self.outbox.begin_send_attempt(now_ms=1_000)
        self.outbox.record_transport_result(
            attempt_token=attempt["last_attempt_token"],
            accepted_by_transport=True,
            now_ms=1_010,
        )
        snapshot = self.outbox.snapshot(now_ms=1_011)
        self.assertEqual(1, snapshot["queued_count"])
        self.assertEqual(1, snapshot["awaiting_positive_ack_count"])

        negative = positive_ack_for(record, ack_id="ack-negative", ack_time_ms=1_020)
        negative["status"] = "rejected"
        self.assertEqual("negative_ack", self.outbox.handle_ack(negative))
        self.assertEqual(1, self.outbox.snapshot(now_ms=1_020)["queued_count"])

        wrong_payload = positive_ack_for(
            record, ack_id="ack-wrong-payload", ack_time_ms=1_030
        )
        wrong_payload["payload_sha256"] = "0" * 64
        self.assertEqual("identity_mismatch", self.outbox.handle_ack(wrong_payload))
        self.assertEqual(1, self.outbox.snapshot(now_ms=1_030)["queued_count"])

        wrong_device = positive_ack_for(
            record, ack_id="ack-wrong-device", ack_time_ms=1_040
        )
        wrong_device["device_id"] = "another-device"
        self.assertEqual("identity_mismatch", self.outbox.handle_ack(wrong_device))
        self.assertEqual(1, self.outbox.snapshot(now_ms=1_040)["queued_count"])

        accepted = positive_ack_for(record, ack_id="ack-valid", ack_time_ms=1_050)
        self.assertEqual(
            "deleted_after_positive_ack", self.outbox.handle_ack(accepted)
        )
        self.assertEqual(0, self.outbox.snapshot(now_ms=1_050)["queued_count"])
        self.assertEqual(
            "duplicate_positive_ack", self.outbox.handle_ack(accepted)
        )
        snapshot = self.outbox.snapshot(now_ms=1_051)
        self.assertEqual(1, snapshot["metrics"]["ack_delete_count"])
        self.assertEqual(1, snapshot["metrics"]["duplicate_ack_count"])

    def test_unknown_and_malformed_ack_fail_closed(self) -> None:
        record = self.enqueue()
        unknown = positive_ack_for(record, ack_id="ack-unknown", ack_time_ms=2_000)
        unknown["event_id"] = "unknown-event"
        self.assertEqual("stale_or_unknown", self.outbox.handle_ack(unknown))
        self.assertEqual(1, self.outbox.snapshot(now_ms=2_000)["queued_count"])

        malformed = positive_ack_for(record, ack_id="ack-malformed", ack_time_ms=2_001)
        malformed["authenticated"] = True
        with self.assertRaises(OutboxValidationError):
            self.outbox.handle_ack(malformed)
        self.assertEqual(1, self.outbox.snapshot(now_ms=2_001)["queued_count"])

    def test_retry_and_identity_survive_reopen(self) -> None:
        original = self.enqueue()
        attempt = self.outbox.begin_send_attempt(now_ms=1_000)
        self.outbox.record_transport_result(
            attempt_token=attempt["last_attempt_token"],
            accepted_by_transport=False,
            now_ms=1_001,
            error_code="NETWORK_UNAVAILABLE",
        )

        reopened = PersistentPriorityOutbox(
            self.storage_dir,
            device_id="ego-test-device-1",
            max_records=4,
            reserved_critical_records=1,
            max_total_payload_bytes=4096,
            max_payload_bytes=1024,
            base_retry_ms=100,
            max_retry_ms=250,
            tombstone_capacity=2,
        )
        snapshot = reopened.snapshot(now_ms=1_050)
        recovered = snapshot["records"][0]
        self.assertEqual(original["identity_sha256"], recovered["identity_sha256"])
        self.assertEqual(original["source_event_time_ms"], recovered["source_event_time_ms"])
        self.assertEqual(1, recovered["attempt_count"])
        self.assertEqual(1_100, recovered["next_retry_time_ms"])
        self.assertIsNone(reopened.begin_send_attempt(now_ms=1_099))
        self.assertIsNotNone(reopened.begin_send_attempt(now_ms=1_100))

    def test_one_corrupt_mirror_is_repaired_and_observable(self) -> None:
        original = self.enqueue()
        (self.storage_dir / PRIMARY_FILE_NAME).write_text(
            "{corrupt", encoding="utf-8"
        )
        reopened = PersistentPriorityOutbox(
            self.storage_dir,
            device_id="ego-test-device-1",
            max_records=4,
            reserved_critical_records=1,
            max_total_payload_bytes=4096,
            max_payload_bytes=1024,
            base_retry_ms=100,
            max_retry_ms=250,
            tombstone_capacity=2,
        )
        snapshot = reopened.snapshot(now_ms=1_100)
        self.assertEqual(original["identity_sha256"], snapshot["records"][0]["identity_sha256"])
        self.assertEqual(1, snapshot["metrics"]["corruption_detected_count"])
        self.assertEqual(1, snapshot["metrics"]["recovery_count"])
        self.assertEqual(
            "invalid_mirror_repaired",
            snapshot["metrics"]["last_recovery_reason"],
        )
        primary = json.loads(
            (self.storage_dir / PRIMARY_FILE_NAME).read_text(encoding="utf-8")
        )
        mirror = json.loads(
            (self.storage_dir / MIRROR_FILE_NAME).read_text(encoding="utf-8")
        )
        self.assertEqual(primary, mirror)
        self.assert_schema_valid(primary)

    def test_interrupted_two_slot_generation_is_recovered_without_losing_latest(self) -> None:
        self.enqueue("event-old")
        stale_primary = (self.storage_dir / PRIMARY_FILE_NAME).read_bytes()
        latest = self.enqueue("event-latest", now_ms=1_100, source_event_time_ms=1_000)
        (self.storage_dir / PRIMARY_FILE_NAME).write_bytes(stale_primary)

        reopened = PersistentPriorityOutbox(
            self.storage_dir,
            device_id="ego-test-device-1",
            max_records=4,
            reserved_critical_records=1,
            max_total_payload_bytes=4096,
            max_payload_bytes=1024,
            base_retry_ms=100,
            max_retry_ms=250,
            tombstone_capacity=2,
        )
        snapshot = reopened.snapshot(now_ms=1_200)
        self.assertEqual(
            {"event-old", latest["event_id"]},
            {record["event_id"] for record in snapshot["records"]},
        )
        self.assertEqual(1, snapshot["metrics"]["recovery_count"])
        self.assertEqual(
            "generation_divergence_repaired",
            snapshot["metrics"]["last_recovery_reason"],
        )

    def test_both_corrupt_mirrors_stop_instead_of_reinitializing(self) -> None:
        self.enqueue()
        for name in (PRIMARY_FILE_NAME, MIRROR_FILE_NAME):
            (self.storage_dir / name).write_text("not-json", encoding="utf-8")
        with self.assertRaisesRegex(OutboxCorruptionError, "no trustworthy"):
            PersistentPriorityOutbox(
                self.storage_dir,
                device_id="ego-test-device-1",
                max_records=4,
                reserved_critical_records=1,
                max_total_payload_bytes=4096,
                max_payload_bytes=1024,
                base_retry_ms=100,
                max_retry_ms=250,
                tombstone_capacity=2,
            )

    def test_priority_reserve_has_no_silent_eviction_and_critical_full_is_explicit(self) -> None:
        local = PersistentPriorityOutbox(
            self.storage_dir / "priority",
            device_id="priority-device",
            max_records=3,
            reserved_critical_records=1,
            max_total_payload_bytes=4096,
            max_payload_bytes=1024,
        )

        def add(event_id: str, *, priority: str = "normal", event_type: str = "status") -> dict:
            return local.enqueue(
                event_id=event_id,
                event_type=event_type,
                priority=priority,
                payload={"status_ref": event_id},
                source_event_time_ms=100,
                boot_count=1,
                session_id="session-1",
                source_sequence=1,
                now_ms=100,
            )

        add("normal-1")
        add("normal-2")
        with self.assertRaises(OutboxFullError):
            add("normal-3")
        before_critical = local.snapshot(now_ms=101)
        self.assertEqual({"normal-1", "normal-2"}, {r["event_id"] for r in before_critical["records"]})
        self.assertEqual("critical_reserve_protected", before_critical["metrics"]["last_drop_reason"])

        add("sos-1", priority="critical", event_type="manual_sos")
        full = local.snapshot(now_ms=102)
        self.assertEqual({"normal-1", "normal-2", "sos-1"}, {r["event_id"] for r in full["records"]})
        with self.assertRaises(OutboxFullError):
            add("sos-2", priority="critical", event_type="manual_sos")
        failed = local.snapshot(now_ms=103)
        self.assertEqual(3, failed["queued_count"])
        self.assertEqual("critical_capacity_exhausted", failed["metrics"]["last_drop_reason"])
        self.assertGreaterEqual(failed["metrics"]["priority_overflow_count"], 2)

    def test_payload_overflow_is_explicit_and_payload_is_not_cached(self) -> None:
        local = PersistentPriorityOutbox(
            self.storage_dir / "overflow",
            device_id="overflow-device",
            max_records=2,
            reserved_critical_records=1,
            max_total_payload_bytes=80,
            max_payload_bytes=64,
        )
        with self.assertRaises(OutboxOverflowError):
            local.enqueue(
                event_id="large-event",
                event_type="status",
                priority="critical",
                payload={"status": "x" * 100},
                source_event_time_ms=1,
                boot_count=1,
                session_id="session-1",
                source_sequence=1,
                now_ms=1,
            )
        snapshot = local.snapshot(now_ms=2)
        self.assertEqual(0, snapshot["queued_count"])
        self.assertEqual(1, snapshot["metrics"]["payload_overflow_count"])
        self.assertEqual("payload_exceeds_record_limit", snapshot["last_failure"]["reason"])

    def test_noncritical_payloads_cannot_consume_critical_byte_reserve(self) -> None:
        local = PersistentPriorityOutbox(
            self.storage_dir / "byte-reserve",
            device_id="byte-reserve-device",
            max_records=5,
            reserved_critical_records=1,
            max_total_payload_bytes=120,
            max_payload_bytes=40,
        )

        def add(event_id: str, *, critical: bool = False) -> dict:
            return local.enqueue(
                event_id=event_id,
                event_type="manual_sos" if critical else "status",
                priority="critical" if critical else "normal",
                payload={"status": "x" * 20},
                source_event_time_ms=1,
                boot_count=1,
                session_id="session-1",
                source_sequence=1,
                now_ms=1,
            )

        add("normal-byte-1")
        add("normal-byte-2")
        with self.assertRaises(OutboxOverflowError):
            add("normal-byte-3")
        reserved = local.snapshot(now_ms=2)
        self.assertEqual(2, reserved["queued_count"])
        self.assertEqual(40, reserved["reserved_critical_payload_bytes"])
        self.assertEqual(
            "critical_payload_reserve_protected",
            reserved["metrics"]["last_drop_reason"],
        )

        add("critical-byte-1", critical=True)
        self.assertEqual(3, local.snapshot(now_ms=3)["queued_count"])
        with self.assertRaises(OutboxOverflowError):
            add("critical-byte-2", critical=True)
        exhausted = local.snapshot(now_ms=4)
        self.assertEqual(3, exhausted["queued_count"])
        self.assertEqual(
            "total_payload_capacity_exhausted",
            exhausted["metrics"]["last_drop_reason"],
        )

    def test_duplicate_enqueue_is_idempotent_but_identity_change_conflicts(self) -> None:
        original = self.enqueue()
        duplicate = self.enqueue()
        self.assertEqual(original, duplicate)
        snapshot = self.outbox.snapshot(now_ms=1_001)
        self.assertEqual(1, snapshot["queued_count"])
        self.assertEqual(1, snapshot["metrics"]["duplicate_enqueue_count"])

        with self.assertRaises(OutboxIdentityConflictError):
            self.enqueue(payload={"state": "changed"})
        with self.assertRaises(OutboxIdentityConflictError):
            self.enqueue(event_type="different_event_type")
        with self.assertRaises(OutboxIdentityConflictError):
            self.enqueue(priority="high")
        self.assertEqual(1, self.outbox.snapshot(now_ms=1_002)["queued_count"])

    def test_private_coordinates_media_and_nonfinite_values_are_rejected(self) -> None:
        with self.assertRaises(OutboxPrivacyError):
            self.enqueue(payload={"location": {"latitude": 22.5}})
        with self.assertRaises(OutboxPrivacyError):
            self.enqueue(payload={"evidence": {"audio": "base64-data"}})
        with self.assertRaises(OutboxPrivacyError):
            self.enqueue(payload={"attachment": b"raw-bytes"})
        with self.assertRaises(OutboxValidationError):
            self.enqueue(payload={"score": float("nan")})
        self.assertEqual(0, self.outbox.snapshot(now_ms=1_001)["queued_count"])

    def test_snapshot_exposes_operational_metadata_but_not_payload(self) -> None:
        self.enqueue(payload={"state": "pending", "guardian_alert_ref": "alert-1"})
        snapshot = self.outbox.snapshot(now_ms=2_000)
        self.assertEqual("host_atomic_json_mirror_reference", snapshot["storage_backend"])
        self.assertEqual("host_reference_only_not_product_nvs", snapshot["durability_claim"])
        self.assertEqual(1, snapshot["queued_count"])
        self.assertEqual(1_000, snapshot["oldest_age_ms"])
        self.assertNotIn("payload", snapshot["records"][0])
        self.assertNotIn("guardian_alert_ref", json.dumps(snapshot, sort_keys=True))

    def test_tombstones_are_bounded_and_pruning_is_visible(self) -> None:
        records = []
        for index in range(3):
            record = self.enqueue(
                f"acked-{index}",
                now_ms=1_000 + index,
                source_event_time_ms=900 + index,
                source_sequence=index,
            )
            records.append(record)
            ack = positive_ack_for(
                record, ack_id=f"ack-{index}", ack_time_ms=2_000 + index
            )
            self.assertEqual("deleted_after_positive_ack", self.outbox.handle_ack(ack))
        snapshot = self.outbox.snapshot(now_ms=2_100)
        self.assertEqual(0, snapshot["queued_count"])
        self.assertEqual(2, snapshot["ack_tombstone_count"])
        self.assertEqual(1, snapshot["metrics"]["tombstone_pruned_count"])
        old_ack = positive_ack_for(records[0], ack_id="ack-0-repeat", ack_time_ms=2_200)
        self.assertEqual("stale_or_unknown", self.outbox.handle_ack(old_ack))

    def test_configuration_identity_mismatch_refuses_reinterpretation(self) -> None:
        self.enqueue()
        with self.assertRaises(OutboxConfigurationError):
            PersistentPriorityOutbox(
                self.storage_dir,
                device_id="ego-test-device-1",
                max_records=5,
                reserved_critical_records=1,
                max_total_payload_bytes=4096,
                max_payload_bytes=1024,
                base_retry_ms=100,
                max_retry_ms=250,
                tombstone_capacity=2,
            )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator

from pc_simulator.location_engine_v0 import LocationEngineV0
from server.location_state_mirror import (
    LocationStateConflictError,
    LocationStateMirror,
    LocationStateRegressionError,
    LocationStateValidationError,
)


ROOT = Path(__file__).resolve().parents[1]
POLICY_CONFIG_PATH = ROOT / "shared" / "config" / "sensor_policy_v0.json"
ENVELOPE_SCHEMA_PATH = (
    ROOT / "shared" / "contracts" / "location_state_envelope_v0.schema.json"
)


def location_state(
    event_time_ms: int,
    *,
    boot_count: int = 1,
    clock_source: str = "timestamp_utc_ns",
    clock_domain: str | None = None,
    lte_state: str = "online",
    with_fix: bool = True,
) -> dict:
    engine = LocationEngineV0()
    engine.process(
        {
            "event_type": "lte_state",
            "event_time_ms": max(0, min(event_time_ms, 900)),
            "lte_state": lte_state,
        }
    )
    if not with_fix:
        return engine.snapshot(event_time_ms)

    fix_time_ms = min(event_time_ms, 1_000)
    lineage = {
        "observation_id": f"synthetic-fix-{boot_count}-{fix_time_ms}",
        "source_status": "observed",
        "stream_id": "synthetic-location-stream",
        "sequence_id": 1,
        "device_run_id": "synthetic-device-run",
        "boot_count": boot_count,
    }
    if clock_source == "timestamp_monotonic_ns":
        lineage["timestamp_monotonic_ns"] = fix_time_ms * 1_000_000
        lineage["monotonic_clock_domain_id"] = clock_domain or f"boot-{boot_count}"
    else:
        lineage[clock_source] = fix_time_ms * 1_000_000
    engine.process(
        {
            "event_type": "gnss_fix",
            "event_time_ms": fix_time_ms,
            "latitude_deg": 10.123456,
            "longitude_deg": 20.654321,
            "accuracy_m": 12.0,
            "lineage": lineage,
        }
    )
    return engine.snapshot(event_time_ms)


def envelope(
    mirror: LocationStateMirror,
    state: dict,
    *,
    device_id: str = "synthetic-device-001",
    boot_count: int = 1,
    session_id: str = "synthetic-session-001",
    sequence_id: int = 1,
    observation_id: str = "synthetic-state-001",
    event_time_source: str = "timestamp_utc_ns",
    monotonic_clock_domain_id: str | None = None,
    server_receive_time_ms: int | None = 10_000,
) -> dict:
    result = {
        "envelope_contract_version": "egolink.location_state_envelope.v0.1",
        "device_id": device_id,
        "boot_count": boot_count,
        "session_id": session_id,
        "event_time_ms": state["event_time_ms"],
        "event_time_source": event_time_source,
        "event_time_ns": state["event_time_ms"] * 1_000_000,
        "monotonic_clock_domain_id": monotonic_clock_domain_id,
        "sequence_id": sequence_id,
        "observation_id": observation_id,
        "policy_identity": mirror.policy_identity,
        "location_state": deepcopy(state),
    }
    if server_receive_time_ms is not None:
        result["server_receive_time_ms"] = server_receive_time_ms
    return result


class LocationStateMirrorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mirror = LocationStateMirror()

    def test_additive_envelope_schema_is_well_formed_and_versioned(self) -> None:
        schema = json.loads(ENVELOPE_SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        self.assertEqual(
            schema["properties"]["envelope_contract_version"]["const"],
            "egolink.location_state_envelope.v0.1",
        )

    def test_envelope_version_and_unknown_fields_fail_closed(self) -> None:
        state = location_state(1_000)
        wrong_version = envelope(self.mirror, state)
        wrong_version["envelope_contract_version"] = (
            "egolink.location_state_envelope.v9"
        )
        with self.assertRaises(LocationStateValidationError):
            self.mirror.ingest(wrong_version)

        unknown_field = envelope(self.mirror, state)
        unknown_field["uncontracted_receive_time"] = 123
        with self.assertRaises(LocationStateValidationError):
            self.mirror.ingest(unknown_field)

    def test_expected_policy_identity_is_semantically_validated_and_stable(self) -> None:
        identity = self.mirror.policy_identity
        self.assertEqual(
            identity["semantic_validation"],
            "egolink.sensor_policy.semantic.v0.1",
        )
        self.assertEqual(
            identity["contract_version"],
            "egolink.sensor_policy_config.v0.1",
        )
        self.assertEqual(len(identity["config_hash"]), 64)
        identity["config_id"] = "caller-mutation"
        self.assertNotEqual(identity, self.mirror.policy_identity)

    def test_semantically_invalid_policy_config_is_rejected_at_construction(self) -> None:
        config = json.loads(POLICY_CONFIG_PATH.read_text(encoding="utf-8"))
        config["low_battery"]["critical_percent"] = 30
        with self.assertRaises(LocationStateValidationError):
            LocationStateMirror(config)

    def test_accepts_contract_state_and_builds_guardian_truth_projection(self) -> None:
        state = location_state(1_000)
        accepted = self.mirror.ingest(envelope(self.mirror, state))
        self.assertEqual(accepted["status"], "accepted")

        snapshot = self.mirror.guardian_snapshot(
            "synthetic-device-001",
            view_event_time_ns=6_000_000_000,
            view_event_time_source="timestamp_utc_ns",
            stale_after_ms=10_000,
            offline_after_ms=20_000,
            location_access_authorized=True,
        )
        self.assertTrue(snapshot["available"])
        self.assertEqual(snapshot["location_belief"], "Fine")
        self.assertEqual(snapshot["location_source"], "gnss")
        self.assertEqual(snapshot["state_age_ms"], 5_000)
        self.assertEqual(snapshot["location_age_ms"], 5_000)
        self.assertTrue(snapshot["accuracy"]["applicable"])
        self.assertFalse(snapshot["confidence"]["calibrated"])
        self.assertTrue(snapshot["uncertainty"]["applicable"])
        self.assertEqual(snapshot["battery"]["state"], "unknown")
        self.assertFalse(snapshot["stale"])
        self.assertFalse(snapshot["offline"])
        self.assertEqual(snapshot["offline_status"], "online")
        self.assertTrue(snapshot["location_access_authorized"])
        self.assertNotIn("server_receive_time_ms", snapshot)

    def test_location_contract_failure_is_sanitized_and_atomic(self) -> None:
        state = location_state(1_000)
        invalid = envelope(self.mirror, state)
        invalid["location_state"]["last_trusted_location"]["latitude_deg"] = 91.234567
        with self.assertRaises(LocationStateValidationError) as caught:
            self.mirror.ingest(invalid)
        self.assertNotIn("91.234567", str(caught.exception))
        self.assertEqual(self.mirror.timeline("synthetic-device-001"), [])
        self.assertIsNone(self.mirror.current_record("synthetic-device-001"))

    def test_state_event_time_and_capture_binding_are_enforced(self) -> None:
        state = location_state(1_000)
        mismatched_state = envelope(self.mirror, state)
        mismatched_state["location_state"]["event_time_ms"] = 1_001
        with self.assertRaises(LocationStateValidationError):
            self.mirror.ingest(mismatched_state)

        malformed_capture = envelope(self.mirror, state)
        malformed_capture["location_state"]["last_trusted_location"][
            "evidence_ref"
        ]["capture_time_ns"] += 1_000_000
        with self.assertRaises(LocationStateValidationError):
            self.mirror.ingest(malformed_capture)

    def test_schema_valid_cross_field_state_conflicts_are_rejected(self) -> None:
        state = location_state(1_000)
        mutations = []

        future_trusted = deepcopy(state)
        future_trusted["last_trusted_time_ms"] = 1_001
        future_evidence = future_trusted["last_trusted_location"]["evidence_ref"]
        future_evidence["event_time_ms"] = 1_001
        future_evidence["capture_time_ns"] = 1_001_000_000
        mutations.append(future_trusted)

        mismatched_source = deepcopy(state)
        mismatched_source["last_trusted_location"]["source"] = "cell_reference"
        mutations.append(mismatched_source)

        mismatched_accuracy = deepcopy(state)
        mismatched_accuracy["location_accuracy_m"] = 13.0
        mutations.append(mismatched_accuracy)

        mismatched_uncertainty = deepcopy(state)
        mismatched_uncertainty["location_uncertainty_m"] = 13.0
        mutations.append(mismatched_uncertainty)

        for index, mutated in enumerate(mutations):
            with self.subTest(index=index):
                with self.assertRaises(LocationStateValidationError):
                    self.mirror.ingest(envelope(self.mirror, mutated))

    def test_new_trusted_state_must_bind_to_same_source_clock(self) -> None:
        state = location_state(1_000)
        wrong_clock = envelope(
            self.mirror,
            state,
            event_time_source="gnss_source_utc_ns",
        )
        with self.assertRaises(LocationStateValidationError):
            self.mirror.ingest(wrong_clock)

    def test_every_policy_identity_field_must_match(self) -> None:
        state = location_state(1_000)
        replacements = {
            "contract_version": "egolink.sensor_policy_config.v9",
            "semantic_validation": "egolink.sensor_policy.semantic.v9",
            "config_id": "different-config",
            "config_hash": "0" * 64,
        }
        for field, replacement in replacements.items():
            with self.subTest(field=field):
                candidate = envelope(self.mirror, state)
                candidate["policy_identity"][field] = replacement
                with self.assertRaises(LocationStateValidationError):
                    self.mirror.ingest(candidate)

    def test_duplicate_is_idempotent_even_when_receive_time_changes(self) -> None:
        state = location_state(1_000)
        first = envelope(self.mirror, state, server_receive_time_ms=20_000)
        duplicate = deepcopy(first)
        duplicate["server_receive_time_ms"] = 90_000
        self.assertEqual(self.mirror.ingest(first)["status"], "accepted")
        result = self.mirror.ingest(duplicate)
        self.assertEqual(result["status"], "duplicate")
        self.assertEqual(result["timeline_length"], 1)
        self.assertEqual(
            self.mirror.timeline("synthetic-device-001")[0][
                "server_receive_time_ms"
            ],
            20_000,
        )

    def test_exact_identity_conflict_is_rejected_without_mutation(self) -> None:
        state = location_state(1_000)
        original = envelope(self.mirror, state)
        self.mirror.ingest(original)
        conflict = deepcopy(original)
        conflict["location_state"]["battery_percent"] = 50.0
        with self.assertRaises(LocationStateConflictError):
            self.mirror.ingest(conflict)
        self.assertEqual(len(self.mirror.timeline("synthetic-device-001")), 1)

    def test_observation_and_sequence_id_reuse_are_conflicts(self) -> None:
        first_state = location_state(1_000)
        self.mirror.ingest(envelope(self.mirror, first_state))

        observation_reuse = envelope(
            self.mirror,
            location_state(2_000),
            sequence_id=2,
            observation_id="synthetic-state-001",
        )
        with self.assertRaises(LocationStateConflictError):
            self.mirror.ingest(observation_reuse)

        sequence_reuse = envelope(
            self.mirror,
            location_state(2_000),
            sequence_id=1,
            observation_id="synthetic-state-002",
        )
        with self.assertRaises(LocationStateConflictError):
            self.mirror.ingest(sequence_reuse)
        self.assertEqual(len(self.mirror.timeline("synthetic-device-001")), 1)

    def test_receive_time_cannot_promote_regressed_event_time(self) -> None:
        self.mirror.ingest(
            envelope(
                self.mirror,
                location_state(2_000),
                server_receive_time_ms=5_000,
            )
        )
        late_older_event = envelope(
            self.mirror,
            location_state(1_500),
            sequence_id=2,
            observation_id="synthetic-state-002",
            server_receive_time_ms=999_000,
        )
        with self.assertRaises(LocationStateRegressionError):
            self.mirror.ingest(late_older_event)
        current = self.mirror.current_record("synthetic-device-001")
        self.assertEqual(current["identity"]["event_time_ms"], 2_000)

    def test_later_event_accepts_even_when_receive_time_is_earlier(self) -> None:
        self.mirror.ingest(
            envelope(
                self.mirror,
                location_state(1_000),
                server_receive_time_ms=100_000,
            )
        )
        result = self.mirror.ingest(
            envelope(
                self.mirror,
                location_state(2_000),
                sequence_id=2,
                observation_id="synthetic-state-002",
                server_receive_time_ms=500,
            )
        )
        self.assertEqual(result["status"], "accepted")
        self.assertEqual(result["current_event_time_ms"], 2_000)

    def test_sequence_must_advance_inside_one_boot_session(self) -> None:
        self.mirror.ingest(
            envelope(self.mirror, location_state(1_000), sequence_id=5)
        )
        regressed = envelope(
            self.mirror,
            location_state(2_000),
            sequence_id=4,
            observation_id="synthetic-state-002",
        )
        with self.assertRaises(LocationStateRegressionError):
            self.mirror.ingest(regressed)

    def test_nanosecond_event_clock_cannot_regress_inside_same_millisecond(self) -> None:
        unknown = location_state(1_000, with_fix=False)
        first = envelope(self.mirror, unknown)
        first["event_time_ns"] = 1_000_900_000
        self.mirror.ingest(first)

        regressed = envelope(
            self.mirror,
            unknown,
            sequence_id=2,
            observation_id="synthetic-state-002",
        )
        regressed["event_time_ns"] = 1_000_100_000
        with self.assertRaises(LocationStateRegressionError):
            self.mirror.ingest(regressed)

    def test_new_monotonic_boot_can_reset_time_but_old_boot_cannot_return(self) -> None:
        boot_one_domain = "synthetic-boot-domain-1"
        first = location_state(
            5_000,
            boot_count=1,
            clock_source="timestamp_monotonic_ns",
            clock_domain=boot_one_domain,
        )
        self.mirror.ingest(
            envelope(
                self.mirror,
                first,
                event_time_source="timestamp_monotonic_ns",
                monotonic_clock_domain_id=boot_one_domain,
            )
        )

        boot_two_domain = "synthetic-boot-domain-2"
        second = location_state(
            1_000,
            boot_count=2,
            clock_source="timestamp_monotonic_ns",
            clock_domain=boot_two_domain,
        )
        accepted = self.mirror.ingest(
            envelope(
                self.mirror,
                second,
                boot_count=2,
                session_id="synthetic-session-002",
                observation_id="synthetic-state-002",
                event_time_source="timestamp_monotonic_ns",
                monotonic_clock_domain_id=boot_two_domain,
            )
        )
        self.assertEqual(accepted["status"], "accepted")

        old_boot = envelope(
            self.mirror,
            location_state(
                6_000,
                boot_count=1,
                clock_source="timestamp_monotonic_ns",
                clock_domain=boot_one_domain,
            ),
            boot_count=1,
            sequence_id=2,
            observation_id="synthetic-state-003",
            event_time_source="timestamp_monotonic_ns",
            monotonic_clock_domain_id=boot_one_domain,
        )
        with self.assertRaises(LocationStateRegressionError):
            self.mirror.ingest(old_boot)

    def test_active_monotonic_location_cannot_cross_boot_scope(self) -> None:
        prior_boot_state = location_state(
            1_000,
            boot_count=1,
            clock_source="timestamp_monotonic_ns",
            clock_domain="reused-domain",
        )
        cross_boot = envelope(
            self.mirror,
            prior_boot_state,
            boot_count=2,
            session_id="synthetic-session-002",
            event_time_source="timestamp_monotonic_ns",
            monotonic_clock_domain_id="reused-domain",
        )
        with self.assertRaises(LocationStateValidationError):
            self.mirror.ingest(cross_boot)

    def test_utc_time_cannot_regress_across_new_boot(self) -> None:
        self.mirror.ingest(envelope(self.mirror, location_state(5_000)))
        regressed = envelope(
            self.mirror,
            location_state(1_000, boot_count=2),
            boot_count=2,
            session_id="synthetic-session-002",
            observation_id="synthetic-state-002",
        )
        with self.assertRaises(LocationStateRegressionError):
            self.mirror.ingest(regressed)

    def test_session_or_clock_domain_change_in_same_boot_is_conflict(self) -> None:
        domain = "synthetic-boot-domain-1"
        first = location_state(
            1_000,
            clock_source="timestamp_monotonic_ns",
            clock_domain=domain,
        )
        self.mirror.ingest(
            envelope(
                self.mirror,
                first,
                event_time_source="timestamp_monotonic_ns",
                monotonic_clock_domain_id=domain,
            )
        )
        changed_session = envelope(
            self.mirror,
            location_state(
                2_000,
                clock_source="timestamp_monotonic_ns",
                clock_domain=domain,
            ),
            session_id="different-session",
            sequence_id=2,
            observation_id="synthetic-state-002",
            event_time_source="timestamp_monotonic_ns",
            monotonic_clock_domain_id=domain,
        )
        with self.assertRaises(LocationStateConflictError):
            self.mirror.ingest(changed_session)

        changed_domain = deepcopy(changed_session)
        changed_domain["session_id"] = "synthetic-session-001"
        changed_domain["monotonic_clock_domain_id"] = "other-clock-domain"
        with self.assertRaises(LocationStateValidationError):
            self.mirror.ingest(changed_domain)

    def test_devices_are_ordered_independently(self) -> None:
        self.mirror.ingest(envelope(self.mirror, location_state(5_000)))
        other = envelope(
            self.mirror,
            location_state(1_000),
            device_id="synthetic-device-002",
            observation_id="synthetic-state-001",
        )
        self.assertEqual(self.mirror.ingest(other)["status"], "accepted")
        self.assertEqual(len(self.mirror.timeline("synthetic-device-001")), 1)
        self.assertEqual(len(self.mirror.timeline("synthetic-device-002")), 1)

    def test_timeline_and_current_are_defensive_and_separate(self) -> None:
        self.mirror.ingest(envelope(self.mirror, location_state(1_000)))
        returned_timeline = self.mirror.timeline("synthetic-device-001")
        returned_timeline[0]["location_state"]["location_belief"] = "Unknown"
        current = self.mirror.current_record("synthetic-device-001")
        self.assertEqual(current["location_state"]["location_belief"], "Fine")

    def test_guardian_predicted_accuracy_stale_and_offline_are_honest(self) -> None:
        predicted = location_state(40_000)
        self.mirror.ingest(envelope(self.mirror, predicted))
        snapshot = self.mirror.guardian_snapshot(
            "synthetic-device-001",
            view_event_time_ns=65_000_000_000,
            view_event_time_source="timestamp_utc_ns",
            stale_after_ms=10_000,
            offline_after_ms=20_000,
            location_access_authorized=True,
        )
        self.assertEqual(snapshot["location_belief"], "Predicted")
        self.assertEqual(snapshot["position_status"], "last_trusted_predicted")
        self.assertFalse(snapshot["accuracy"]["applicable"])
        self.assertIsNone(snapshot["accuracy"]["value_m"])
        self.assertTrue(snapshot["uncertainty"]["applicable"])
        self.assertTrue(snapshot["stale"])
        self.assertTrue(snapshot["offline"])
        self.assertEqual(snapshot["offline_status"], "offline")

    def test_guardian_position_is_redacted_without_explicit_authorization(self) -> None:
        self.mirror.ingest(envelope(self.mirror, location_state(1_000)))
        snapshot = self.mirror.guardian_snapshot(
            "synthetic-device-001",
            view_event_time_ns=2_000_000_000,
            view_event_time_source="timestamp_utc_ns",
            stale_after_ms=10_000,
            offline_after_ms=20_000,
        )
        self.assertFalse(snapshot["location_access_authorized"])
        self.assertIsNone(snapshot["position"])
        self.assertEqual(snapshot["position_status"], "redacted_unauthorized")

    def test_guardian_unknown_and_missing_state_do_not_invent_location(self) -> None:
        missing = self.mirror.guardian_snapshot(
            "never-seen-device",
            view_event_time_ns=1_000_000_000,
            view_event_time_source="timestamp_utc_ns",
            stale_after_ms=10_000,
            offline_after_ms=20_000,
        )
        self.assertFalse(missing["available"])
        self.assertEqual(missing["location_belief"], "Unknown")
        self.assertIsNone(missing["position"])
        self.assertTrue(missing["offline"])

        unknown = location_state(1_000, with_fix=False, lte_state="unknown")
        self.mirror.ingest(envelope(self.mirror, unknown))
        snapshot = self.mirror.guardian_snapshot(
            "synthetic-device-001",
            view_event_time_ns=2_000_000_000,
            view_event_time_source="timestamp_utc_ns",
            stale_after_ms=10_000,
            offline_after_ms=20_000,
        )
        self.assertEqual(snapshot["location_belief"], "Unknown")
        self.assertIsNone(snapshot["position"])
        self.assertFalse(snapshot["accuracy"]["applicable"])
        self.assertIsNone(snapshot["offline"])
        self.assertEqual(snapshot["offline_status"], "unknown")

    def test_guardian_requires_comparable_non_regressed_event_clock(self) -> None:
        domain = "synthetic-boot-domain-1"
        state = location_state(
            2_000,
            clock_source="timestamp_monotonic_ns",
            clock_domain=domain,
        )
        self.mirror.ingest(
            envelope(
                self.mirror,
                state,
                event_time_source="timestamp_monotonic_ns",
                monotonic_clock_domain_id=domain,
            )
        )
        with self.assertRaises(LocationStateValidationError):
            self.mirror.guardian_snapshot(
                "synthetic-device-001",
                view_event_time_ns=3_000_000_000,
                view_event_time_source="timestamp_monotonic_ns",
                monotonic_clock_domain_id="different-domain",
                stale_after_ms=10_000,
                offline_after_ms=20_000,
            )
        with self.assertRaises(LocationStateRegressionError):
            self.mirror.guardian_snapshot(
                "synthetic-device-001",
                view_event_time_ns=1_000_000_000,
                view_event_time_source="timestamp_monotonic_ns",
                monotonic_clock_domain_id=domain,
                stale_after_ms=10_000,
                offline_after_ms=20_000,
            )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator

from pc_simulator.location_engine_v0 import (
    LocationEngineConfig,
    LocationEngineError,
    LocationEngineV0,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads(
    (ROOT / "shared" / "contracts" / "location_engine_v0.schema.json").read_text(
        encoding="utf-8"
    )
)


class LocationEngineV0Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = Draft202012Validator(SCHEMA)

    def assert_valid(self, state: dict) -> None:
        errors = sorted(self.validator.iter_errors(state), key=lambda error: error.json_path)
        self.assertEqual([], [f"{error.json_path}: {error.message}" for error in errors])

    @staticmethod
    def capture_evidence(
        event_time_ms: int, *, source_status: str = "observed"
    ) -> dict:
        return {
            "observation_id": f"capture-{event_time_ms}",
            "source_status": source_status,
            "stream_id": "test-stream",
            "sequence_id": event_time_ms,
            "device_run_id": "test-run",
            "boot_count": 1,
            "timestamp_utc_ns": event_time_ms * 1_000_000,
            "event_time_source": "capture_event",
        }

    @staticmethod
    def accepted_fix(event_time_ms: int = 1_000) -> dict:
        return {
            "event_type": "gnss_fix",
            "event_time_ms": event_time_ms,
            "latitude_deg": 22.543096,
            "longitude_deg": 114.057865,
            "accuracy_m": 12.0,
            "evidence": LocationEngineV0Tests.capture_evidence(event_time_ms),
        }

    def test_initial_and_fix_states_validate_against_contract(self) -> None:
        engine = LocationEngineV0()
        initial = engine.snapshot()
        fixed = engine.process(self.accepted_fix())

        self.assert_valid(initial)
        self.assert_valid(fixed)
        self.assertEqual("Unknown", initial["location_belief"])
        self.assertIsNone(initial["last_trusted_location"])
        self.assertEqual("Fine", fixed["location_belief"])
        self.assertEqual("gnss", fixed["location_source"])
        self.assertEqual(12.0, fixed["location_uncertainty_m"])
        self.assertEqual("source_reported", fixed["location_accuracy_status"])
        self.assertFalse(fixed["location_confidence_calibrated"])

    def test_no_fix_preserves_last_trusted_and_ages_uncertainty(self) -> None:
        config = LocationEngineConfig(
            fine_freshness_ms=10_000,
            coarse_freshness_ms=20_000,
            prediction_horizon_ms=120_000,
            uncertainty_growth_mps=2.0,
        )
        engine = LocationEngineV0(config)
        engine.process(self.accepted_fix(1_000))
        no_fix = engine.process(
            {
                "event_type": "gnss_no_fix",
                "event_time_ms": 11_000,
                "evidence": self.capture_evidence(11_000),
            }
        )
        later = engine.process({"event_type": "tick", "event_time_ms": 21_000})

        self.assertEqual("Predicted", no_fix["location_belief"])
        self.assertEqual("last_trusted", no_fix["location_source"])
        self.assertEqual(32.0, no_fix["location_uncertainty_m"])
        self.assertIsNone(no_fix["location_accuracy_m"])
        self.assertEqual(52.0, later["location_uncertainty_m"])
        self.assertEqual(
            no_fix["last_trusted_location"], later["last_trusted_location"]
        )
        self.assert_valid(no_fix)
        self.assert_valid(later)

    def test_prediction_horizon_becomes_unknown_without_erasing_memory(self) -> None:
        engine = LocationEngineV0(
            LocationEngineConfig(
                fine_freshness_ms=1_000,
                coarse_freshness_ms=1_000,
                prediction_horizon_ms=2_000,
            )
        )
        engine.process(self.accepted_fix(1_000))
        expired = engine.process({"event_type": "tick", "event_time_ms": 3_001})

        self.assertEqual("Unknown", expired["location_belief"])
        self.assertIsNotNone(expired["last_trusted_location"])
        self.assertEqual(1_000, expired["last_trusted_time_ms"])
        self.assert_valid(expired)

    def test_cell_imu_and_battery_cannot_fabricate_coordinates(self) -> None:
        engine = LocationEngineV0()
        states = [
            engine.process({"event_type": "cell_observation", "event_time_ms": 1}),
            engine.process(
                {
                    "event_type": "mobility",
                    "event_time_ms": 2,
                    "mobility_state": "moving",
                    "evidence": self.capture_evidence(2),
                }
            ),
            engine.process(
                {
                    "event_type": "battery",
                    "event_time_ms": 3,
                    "battery_state": "low",
                    "battery_percent": 18,
                }
            ),
        ]

        for state in states:
            self.assertEqual("Unknown", state["location_belief"])
            self.assertIsNone(state["last_trusted_location"])
            self.assertIsNone(state["location_uncertainty_m"])
            self.assert_valid(state)

    def test_unqualified_or_inaccurate_fix_is_rejected_honestly(self) -> None:
        engine = LocationEngineV0(LocationEngineConfig(fine_max_accuracy_m=50.0))
        missing_accuracy = engine.process(
            {
                "event_type": "gnss_fix",
                "event_time_ms": 1,
                "latitude_deg": 22.5,
                "longitude_deg": 114.0,
                "evidence": self.capture_evidence(1),
            }
        )
        inaccurate = engine.process(
            {
                "event_type": "gnss_fix",
                "event_time_ms": 2,
                "latitude_deg": 22.5,
                "longitude_deg": 114.0,
                "accuracy_m": 100.0,
                "evidence": self.capture_evidence(2),
            }
        )

        self.assertEqual("fix_rejected", missing_accuracy["gnss_state"])
        self.assertEqual("Unknown", missing_accuracy["location_belief"])
        self.assertIn(
            "gnss_fix_rejected_reported_accuracy", inaccurate["reason_codes"]
        )
        self.assertIsNone(inaccurate["last_trusted_location"])

    def test_explicit_coarse_reference_is_allowed_but_raw_cell_is_not(self) -> None:
        engine = LocationEngineV0()
        engine.process({"event_type": "cell_observation", "event_time_ms": 1})
        coarse = engine.process(
            {
                "event_type": "coarse_location",
                "event_time_ms": 2,
                "source": "cell_reference",
                "reference_id": "cell-memory-v1:A",
                "latitude_deg": 22.54,
                "longitude_deg": 114.05,
                "accuracy_m": 500.0,
                "evidence": self.capture_evidence(2, source_status="verified"),
            }
        )

        self.assertEqual("Coarse", coarse["location_belief"])
        self.assertEqual("cell_reference", coarse["location_source"])
        self.assert_valid(coarse)

    def test_mock_or_lineage_free_fix_cannot_become_trusted(self) -> None:
        engine = LocationEngineV0()
        mock_fix = self.accepted_fix(1)
        mock_fix["evidence"]["source_status"] = "mock"
        rejected_mock = engine.process(mock_fix)
        no_lineage = self.accepted_fix(2)
        no_lineage.pop("evidence")
        rejected_unbound = engine.process(no_lineage)

        self.assertEqual("fix_rejected", rejected_mock["gnss_state"])
        self.assertEqual("Unknown", rejected_mock["location_belief"])
        self.assertIn("gnss_fix_rejected_untrusted_lineage", rejected_mock["reason_codes"])
        self.assertEqual("Unknown", rejected_unbound["location_belief"])
        self.assertIsNone(rejected_unbound["last_trusted_location"])

    def test_rule_derived_mobility_requires_attributable_basis(self) -> None:
        engine = LocationEngineV0()
        weak = {
            "event_type": "mobility",
            "event_time_ms": 1,
            "mobility_state": "moving",
            "evidence": {"source_status": "rule_derived"},
        }
        with self.assertRaisesRegex(LocationEngineError, "trusted lineage"):
            engine.process(weak)

        accepted = engine.process(
            {
                "event_type": "mobility",
                "event_time_ms": 2,
                "mobility_state": "moving",
                "evidence": {
                    "observation_id": "mobility-rule-2",
                    "source_status": "rule_derived",
                    "event_time_source": "policy_rule_v0",
                    "basis_observation_ids": ["imu-1", "imu-2"],
                },
            }
        )
        self.assertEqual("moving", accepted["mobility_state"])

    def test_hdop_fix_keeps_accuracy_unavailable_and_uncertainty_explicit(self) -> None:
        event = self.accepted_fix(1)
        event.pop("accuracy_m")
        event["hdop"] = 1.4
        state = LocationEngineV0().process(event)

        self.assertEqual("Fine", state["location_belief"])
        self.assertIsNone(state["location_accuracy_m"])
        self.assertEqual("unavailable", state["location_accuracy_status"])
        self.assertEqual(7.0, state["location_uncertainty_m"])
        self.assertEqual("hdop_rule_heuristic_v0", state["location_uncertainty_basis"])
        self.assert_valid(state)

    def test_capture_time_is_real_bound_and_preserved(self) -> None:
        engine = LocationEngineV0()
        weak = self.accepted_fix(1)
        weak["evidence"].pop("timestamp_utc_ns")
        rejected_weak = engine.process(weak)
        self.assertEqual("fix_rejected", rejected_weak["gnss_state"])

        mismatched = self.accepted_fix(2)
        mismatched["evidence"]["timestamp_utc_ns"] = 3_000_000
        rejected_mismatch = engine.process(mismatched)
        self.assertEqual("fix_rejected", rejected_mismatch["gnss_state"])

        accepted = LocationEngineV0().process(self.accepted_fix(4))
        ref = accepted["last_trusted_location"]["evidence_ref"]
        self.assertEqual(4, ref["event_time_ms"])
        self.assertEqual(4_000_000, ref["capture_time_ns"])
        self.assertEqual("timestamp_utc_ns", ref["event_time_source"])
        self.assert_valid(accepted)

    def test_monotonic_capture_requires_boot_and_clock_domain(self) -> None:
        event = self.accepted_fix(5)
        evidence = event["evidence"]
        evidence.pop("timestamp_utc_ns")
        evidence["timestamp_monotonic_ns"] = 5_000_000
        rejected = LocationEngineV0().process(event)
        self.assertEqual("fix_rejected", rejected["gnss_state"])

        evidence["monotonic_clock_domain_id"] = "imu-clock:boot-1"
        accepted = LocationEngineV0().process(event)
        ref = accepted["last_trusted_location"]["evidence_ref"]
        self.assertEqual("timestamp_monotonic_ns", ref["event_time_source"])
        self.assertEqual("imu-clock:boot-1", ref["monotonic_clock_domain_id"])
        self.assert_valid(accepted)

    def test_invalid_optional_lineage_cannot_create_invalid_output(self) -> None:
        for field, value in (
            ("stream_id", ""),
            ("sequence_id", -1),
            ("boot_count", -1),
        ):
            with self.subTest(field=field):
                event = self.accepted_fix(1)
                event["evidence"][field] = value
                state = LocationEngineV0().process(event)
                self.assertEqual("fix_rejected", state["gnss_state"])
                self.assertIsNone(state["last_trusted_location"])
                self.assert_valid(state)

    def test_explicit_bad_accuracy_cannot_fall_back_to_hdop(self) -> None:
        event = self.accepted_fix(1)
        event["accuracy_m"] = 1_000
        event["hdop"] = 1.0
        state = LocationEngineV0().process(event)

        self.assertEqual("fix_rejected", state["gnss_state"])
        self.assertEqual("Unknown", state["location_belief"])
        self.assertIn("gnss_fix_rejected_reported_accuracy", state["reason_codes"])

    def test_gnss_lifecycle_requires_observed_or_policy_action_lineage(self) -> None:
        engine = LocationEngineV0()
        before = engine.snapshot()
        with self.assertRaisesRegex(LocationEngineError, "lineage"):
            engine.process({"event_type": "gnss_no_fix", "event_time_ms": 1})
        self.assertEqual(before, engine.snapshot())

        state = engine.process(
            {
                "event_type": "gnss_no_fix",
                "event_time_ms": 1,
                "evidence": {
                    "observation_id": "policy-action:no-fix:1",
                    "source_status": "rule_derived",
                    "event_time_source": "policy_action_v0",
                    "basis_observation_ids": ["gnss-start:0"],
                },
            }
        )
        self.assertEqual("no_fix", state["gnss_state"])

    def test_invalid_event_is_transactional(self) -> None:
        engine = LocationEngineV0()
        before = engine.snapshot()
        with self.assertRaisesRegex(LocationEngineError, "battery_percent"):
            engine.process(
                {
                    "event_type": "battery",
                    "event_time_ms": 100,
                    "battery_state": "low",
                    "battery_percent": 101,
                }
            )
        self.assertEqual(before, engine.snapshot())
        corrected = engine.process({"event_type": "tick", "event_time_ms": 99})
        self.assertEqual(99, corrected["event_time_ms"])

    def test_nonfinite_config_is_rejected(self) -> None:
        with self.assertRaises(LocationEngineError):
            LocationEngineConfig(uncertainty_growth_mps=float("nan"))
        with self.assertRaises(LocationEngineError):
            LocationEngineConfig(fine_max_accuracy_m=float("inf"))

    def test_event_time_regression_is_rejected(self) -> None:
        engine = LocationEngineV0()
        engine.process({"event_type": "tick", "event_time_ms": 10})
        with self.assertRaisesRegex(LocationEngineError, "event_time_ms regression"):
            engine.process({"event_type": "tick", "event_time_ms": 9})

    def test_same_observation_sequence_is_deterministic(self) -> None:
        events = [
            self.accepted_fix(1_000),
            {
                "event_type": "mobility",
                "event_time_ms": 2_000,
                "mobility_state": "moving",
                "evidence": self.capture_evidence(2_000),
            },
            {
                "event_type": "gnss_no_fix",
                "event_time_ms": 3_000,
                "evidence": self.capture_evidence(3_000),
            },
            {"event_type": "battery", "event_time_ms": 4_000, "battery_state": "low"},
            {"event_type": "sos", "event_time_ms": 5_000, "active": True},
        ]

        def run() -> list[dict]:
            engine = LocationEngineV0()
            return [engine.process(event) for event in events]

        self.assertEqual(run(), run())


if __name__ == "__main__":
    unittest.main()

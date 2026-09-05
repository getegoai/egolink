from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator

from pc_simulator.location_engine_v0 import LocationEngineV0
from pc_simulator.sensor_policy_v0 import (
    SensorPolicyConfig,
    SensorPolicyError,
    SensorPolicyV0,
    load_sensor_policy_config,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "shared" / "config" / "sensor_policy_v0.json"
CONFIG_SCHEMA = json.loads(
    (ROOT / "shared" / "contracts" / "sensor_policy_v0.schema.json").read_text(
        encoding="utf-8"
    )
)
DECISION_SCHEMA = json.loads(
    (
        ROOT
        / "shared"
        / "contracts"
        / "sensor_policy_decision_v0.schema.json"
    ).read_text(encoding="utf-8")
)


def evidence(event_time_ms: int, *, source_status: str = "observed") -> dict:
    return {
        "observation_id": f"policy-test-{event_time_ms}",
        "source_status": source_status,
        "stream_id": "policy-test-stream",
        "sequence_id": event_time_ms,
        "device_run_id": "policy-test-run",
        "boot_count": 1,
        "timestamp_utc_ns": event_time_ms * 1_000_000,
        "event_time_source": "capture_event",
    }


class SensorPolicyV0Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.raw_config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        self.config = load_sensor_policy_config(CONFIG_PATH)
        self.engine = LocationEngineV0(self.config.location_engine_config())
        self.policy = SensorPolicyV0(self.config)
        self.config_validator = Draft202012Validator(CONFIG_SCHEMA)
        self.decision_validator = Draft202012Validator(DECISION_SCHEMA)

    def decision(self, observation: dict) -> tuple[dict, dict]:
        observation = deepcopy(observation)
        if observation["event_type"] in {
            "gnss_started",
            "gnss_stopped",
            "gnss_fix",
            "gnss_no_fix",
            "gnss_error",
            "mobility",
            "coarse_location",
        }:
            observation.setdefault("evidence", evidence(observation["event_time_ms"]))
        state = self.engine.process(observation)
        decision = self.policy.evaluate(
            state,
            event_type=observation["event_type"],
            observation=observation,
        )
        self.assert_decision_valid(decision)
        self.engine.set_policy_context(decision["policy_mode"])
        state = self.engine.snapshot(observation["event_time_ms"])
        return state, decision

    def assert_decision_valid(self, decision: dict) -> None:
        errors = sorted(
            self.decision_validator.iter_errors(decision), key=lambda error: error.json_path
        )
        self.assertEqual([], [f"{error.json_path}: {error.message}" for error in errors])

    def test_default_config_and_decision_validate(self) -> None:
        Draft202012Validator.check_schema(CONFIG_SCHEMA)
        Draft202012Validator.check_schema(DECISION_SCHEMA)
        self.assertEqual([], list(self.config_validator.iter_errors(self.raw_config)))
        _, decision = self.decision({"event_type": "tick", "event_time_ms": 0})
        self.assert_decision_valid(decision)
        self.assertEqual("LOCATION_UNCERTAIN", decision["policy_mode"])
        self.assertEqual("start", decision["actions"]["gnss"]["action"])
        self.assertEqual("observe", decision["actions"]["cell"]["action"])
        self.assertEqual(10_000, decision["next_evaluation_ms"])
        self.assertFalse(decision["actions"]["camera"]["requested"])
        self.assertEqual("OFF", decision["actions"]["camera"]["action"])

    def test_state_priority_and_independent_conditions(self) -> None:
        self.decision(
            {
                "event_type": "gnss_fix",
                "event_time_ms": 1,
                "latitude_deg": 22.5,
                "longitude_deg": 114.0,
                "accuracy_m": 10,
            }
        )
        _, stable = self.decision(
            {"event_type": "mobility", "event_time_ms": 2, "mobility_state": "stable"}
        )
        _, moving = self.decision(
            {"event_type": "mobility", "event_time_ms": 3, "mobility_state": "moving"}
        )
        _, low = self.decision(
            {
                "event_type": "battery",
                "event_time_ms": 4,
                "battery_state": "low",
                "battery_percent": 18,
            }
        )
        _, sos = self.decision({"event_type": "sos", "event_time_ms": 5, "active": True})

        self.assertEqual("STABLE", stable["policy_mode"])
        self.assertEqual("MOVING", moving["policy_mode"])
        self.assertEqual("LOW_BATTERY", low["policy_mode"])
        self.assertEqual("SOS", sos["policy_mode"])
        self.assertTrue(sos["conditions"]["low_battery"])
        self.assertTrue(sos["conditions"]["moving"])
        self.assertTrue(sos["actions"]["lte"]["keep_connected"])
        self.assertTrue(sos["actions"]["ego_call"]["start_now"])
        for item in (stable, moving, low, sos):
            self.assert_decision_valid(item)

    def test_no_fix_uses_backoff_instead_of_immediate_retry(self) -> None:
        self.decision({"event_type": "tick", "event_time_ms": 0})
        _, failed = self.decision({"event_type": "gnss_no_fix", "event_time_ms": 45_000})
        _, early = self.decision({"event_type": "tick", "event_time_ms": 45_001})
        _, due = self.decision({"event_type": "tick", "event_time_ms": 105_000})

        self.assertEqual("wait_backoff", failed["actions"]["gnss"]["action"])
        self.assertEqual(105_000, failed["actions"]["gnss"]["retry_not_before_ms"])
        self.assertEqual("wait_backoff", early["actions"]["gnss"]["action"])
        self.assertEqual("start", due["actions"]["gnss"]["action"])
        self.assertIsNone(due["actions"]["gnss"]["retry_not_before_ms"])
        self.assertIsNone(due["runtime"]["retry_not_before_ms"])

    def test_gnss_timeout_stops_once_then_recovers_after_backoff(self) -> None:
        self.decision({"event_type": "tick", "event_time_ms": 0})
        _, before = self.decision({"event_type": "tick", "event_time_ms": 44_999})
        _, timeout = self.decision({"event_type": "tick", "event_time_ms": 45_000})
        _, waiting = self.decision({"event_type": "tick", "event_time_ms": 45_001})
        _, retry = self.decision({"event_type": "tick", "event_time_ms": 105_000})

        self.assertEqual("continue", before["actions"]["gnss"]["action"])
        self.assertEqual("stop_timeout", timeout["actions"]["gnss"]["action"])
        self.assertEqual(1, timeout["runtime"]["consecutive_no_fix"])
        self.assertEqual("wait_backoff", waiting["actions"]["gnss"]["action"])
        self.assertEqual("start", retry["actions"]["gnss"]["action"])

    def test_sos_retry_interval_is_exact_and_not_exponential(self) -> None:
        self.decision({"event_type": "tick", "event_time_ms": 0})
        self.decision({"event_type": "gnss_no_fix", "event_time_ms": 45_000})
        _, sos = self.decision({"event_type": "sos", "event_time_ms": 46_000, "active": True})
        _, failed_once = self.decision(
            {"event_type": "gnss_no_fix", "event_time_ms": 106_000}
        )
        _, retry_once = self.decision({"event_type": "tick", "event_time_ms": 136_000})
        _, failed_twice = self.decision(
            {"event_type": "gnss_no_fix", "event_time_ms": 196_000}
        )

        self.assertEqual("start", sos["actions"]["gnss"]["action"])
        self.assertTrue(sos["actions"]["location"]["upload_now"])
        self.assertTrue(sos["actions"]["ego_call"]["start_now"])
        self.assertEqual(136_000, failed_once["actions"]["gnss"]["retry_not_before_ms"])
        self.assertEqual("start", retry_once["actions"]["gnss"]["action"])
        self.assertEqual(226_000, failed_twice["actions"]["gnss"]["retry_not_before_ms"])

    def test_rejected_fix_is_failure_and_never_uploaded(self) -> None:
        self.decision({"event_type": "tick", "event_time_ms": 0})
        _, rejected = self.decision(
            {
                "event_type": "gnss_fix",
                "event_time_ms": 1_000,
                "latitude_deg": 22.5,
                "longitude_deg": 114.0,
                "accuracy_m": 10,
                "evidence": evidence(1_000, source_status="mock"),
            }
        )

        self.assertFalse(rejected["actions"]["location"]["upload_now"])
        self.assertEqual(1, rejected["runtime"]["consecutive_no_fix"])
        self.assertEqual(61_000, rejected["runtime"]["retry_not_before_ms"])
        self.assertEqual("wait_backoff", rejected["actions"]["gnss"]["action"])

    def test_fresh_coarse_reference_exits_uncertain_even_after_no_fix(self) -> None:
        self.decision({"event_type": "gnss_no_fix", "event_time_ms": 0})
        _, coarse = self.decision(
            {
                "event_type": "coarse_location",
                "event_time_ms": 1,
                "source": "cell_reference",
                "reference_id": "frozen-cell-map-v1:A",
                "latitude_deg": 22.5,
                "longitude_deg": 114.0,
                "uncertainty_m": 100,
            }
        )

        self.assertEqual("STABLE", coarse["policy_mode"])
        self.assertFalse(coarse["conditions"]["location_uncertain"])
        self.assertTrue(coarse["actions"]["location"]["upload_now"])

    def test_low_battery_hysteresis_does_not_suppress_sos(self) -> None:
        _, entered = self.decision(
            {
                "event_type": "battery",
                "event_time_ms": 1,
                "battery_state": "normal",
                "battery_percent": 20,
            }
        )
        _, held = self.decision(
            {
                "event_type": "battery",
                "event_time_ms": 2,
                "battery_state": "normal",
                "battery_percent": 23,
            }
        )
        _, exited = self.decision(
            {
                "event_type": "battery",
                "event_time_ms": 3,
                "battery_state": "normal",
                "battery_percent": 25,
            }
        )
        _, sos = self.decision({"event_type": "sos", "event_time_ms": 4, "active": True})

        self.assertTrue(entered["conditions"]["low_battery"])
        self.assertTrue(held["conditions"]["low_battery"])
        self.assertFalse(exited["conditions"]["low_battery"])
        self.assertEqual("SOS", sos["policy_mode"])

    def test_critical_threshold_is_explainable_inside_low_battery_mode(self) -> None:
        _, critical = self.decision(
            {
                "event_type": "battery",
                "event_time_ms": 1,
                "battery_state": "normal",
                "battery_percent": 10,
            }
        )
        _, low_only = self.decision(
            {
                "event_type": "battery",
                "event_time_ms": 2,
                "battery_state": "normal",
                "battery_percent": 15,
            }
        )

        self.assertEqual("LOW_BATTERY", critical["policy_mode"])
        self.assertTrue(critical["conditions"]["critical_battery"])
        self.assertTrue(low_only["conditions"]["low_battery"])
        self.assertFalse(low_only["conditions"]["critical_battery"])

    def test_raw_imu_hysteresis_derives_moving_then_stable(self) -> None:
        last_decision: dict | None = None
        event_time_ms = 0
        for vector in ([0.0, 0.0, 12.0], [0.0, 0.0, 12.0]):
            for _ in range(21):
                _, last_decision = self.decision(
                    {
                        "event_type": "imu_sample",
                        "event_time_ms": event_time_ms,
                        "accel_m_s2": vector,
                    }
                )
                event_time_ms += 100
        self.assertIsNotNone(last_decision)
        self.assertEqual("moving", last_decision["derived_mobility_state"])

        for vector in ([0.0, 0.0, 9.80665], [0.0, 0.0, 9.80665]):
            for _ in range(21):
                _, last_decision = self.decision(
                    {
                        "event_type": "imu_sample",
                        "event_time_ms": event_time_ms,
                        "accel_m_s2": vector,
                    }
                )
                event_time_ms += 100
        self.assertEqual("stable", last_decision["derived_mobility_state"])

    def test_observed_mobility_expires_instead_of_sticking_forever(self) -> None:
        _, moving = self.decision(
            {"event_type": "mobility", "event_time_ms": 0, "mobility_state": "moving"}
        )
        _, stale = self.decision({"event_type": "tick", "event_time_ms": 10_001})

        self.assertEqual("moving", moving["derived_mobility_state"])
        self.assertEqual("unknown", stale["derived_mobility_state"])
        self.assertFalse(stale["conditions"]["moving"])

    def test_cell_timeout_backoff_and_recovery_are_bounded(self) -> None:
        _, started = self.decision({"event_type": "tick", "event_time_ms": 0})
        _, timed_out = self.decision({"event_type": "tick", "event_time_ms": 10_000})
        _, waiting = self.decision({"event_type": "tick", "event_time_ms": 29_999})
        _, retry = self.decision({"event_type": "tick", "event_time_ms": 30_000})
        _, observed = self.decision(
            {"event_type": "cell_observation", "event_time_ms": 30_001}
        )

        self.assertEqual("observe", started["actions"]["cell"]["action"])
        self.assertEqual("timeout", timed_out["actions"]["cell"]["action"])
        self.assertEqual(30_000, timed_out["actions"]["cell"]["retry_not_before_ms"])
        self.assertEqual("wait_backoff", waiting["actions"]["cell"]["action"])
        self.assertEqual("observe", retry["actions"]["cell"]["action"])
        self.assertIsNone(retry["runtime"]["cell_retry_not_before_ms"])
        self.assertEqual(0, observed["runtime"]["consecutive_cell_timeouts"])

    def test_next_evaluation_covers_belief_and_mobility_deadlines(self) -> None:
        self.decision(
            {
                "event_type": "gnss_fix",
                "event_time_ms": 0,
                "latitude_deg": 22.5,
                "longitude_deg": 114.0,
                "accuracy_m": 10,
            }
        )
        _, cell_ack = self.decision(
            {"event_type": "cell_observation", "event_time_ms": 1}
        )
        self.assertEqual(30_001, cell_ack["next_evaluation_ms"])

        _, moving = self.decision(
            {"event_type": "mobility", "event_time_ms": 2, "mobility_state": "moving"}
        )
        self.assertEqual(10_003, moving["next_evaluation_ms"])
        _, mobility_expired = self.decision(
            {"event_type": "tick", "event_time_ms": 10_003}
        )
        self.assertEqual("unknown", mobility_expired["derived_mobility_state"])

        _, aged = self.decision(
            {"event_type": "tick", "event_time_ms": 30_001}
        )
        self.assertEqual("LOCATION_UNCERTAIN", aged["policy_mode"])

    def test_prediction_horizon_is_a_policy_wakeup_deadline(self) -> None:
        raw = deepcopy(self.raw_config)
        for section in ("stationary", "moving", "location_uncertain"):
            raw[section]["gnss_interval_s"] = 2_000
            raw[section]["cell_interval_s"] = 2_000
        config = SensorPolicyConfig.from_mapping(raw)
        engine = LocationEngineV0(config.location_engine_config())
        policy = SensorPolicyV0(config)

        fix = {
            "event_type": "gnss_fix",
            "event_time_ms": 0,
            "latitude_deg": 22.5,
            "longitude_deg": 114.0,
            "accuracy_m": 10,
            "evidence": evidence(0),
        }
        state = engine.process(fix)
        policy.evaluate(state, event_type="gnss_fix", observation=fix)
        cell = {"event_type": "cell_observation", "event_time_ms": 1}
        state = engine.process(cell)
        policy.evaluate(state, event_type="cell_observation", observation=cell)
        tick = {"event_type": "tick", "event_time_ms": 30_001}
        state = engine.process(tick)
        decision = policy.evaluate(state, event_type="tick", observation=tick)

        self.assertEqual(900_001, decision["next_evaluation_ms"])
        horizon_tick = {"event_type": "tick", "event_time_ms": 900_001}
        state = engine.process(horizon_tick)
        decision = policy.evaluate(
            state, event_type="tick", observation=horizon_tick
        )
        self.assertEqual("Unknown", state["location_belief"])
        self.assertEqual("LOCATION_UNCERTAIN", decision["policy_mode"])

    def test_policy_rejects_time_regression_and_rolls_back_invalid_input(self) -> None:
        state, _ = self.decision({"event_type": "tick", "event_time_ms": 100})
        before = self.policy.runtime.snapshot()
        regressed = deepcopy(state)
        regressed["event_time_ms"] = 99
        with self.assertRaisesRegex(SensorPolicyError, "regression"):
            self.policy.evaluate(
                regressed,
                event_type="tick",
                observation={"event_type": "tick", "event_time_ms": 99},
            )
        self.assertEqual(before, self.policy.runtime.snapshot())

        bad_observation = {
            "event_type": "imu_sample",
            "event_time_ms": 101,
            "accel_m_s2": [0.0, 1.0],
        }
        bad_state = self.engine.process(bad_observation)
        with self.assertRaisesRegex(SensorPolicyError, "three finite"):
            self.policy.evaluate(
                bad_state, event_type="imu_sample", observation=bad_observation
            )
        self.assertEqual(before, self.policy.runtime.snapshot())

        corrected = {**bad_observation, "accel_m_s2": [0.0, 0.0, 9.80665]}
        decision = self.policy.evaluate(
            bad_state, event_type="imu_sample", observation=corrected
        )
        self.assertEqual(101, decision["runtime"]["last_evaluation_ms"])

    def test_config_rejects_unknown_and_relationally_invalid_values(self) -> None:
        with_camera = deepcopy(self.raw_config)
        with_camera["camera"] = {"enabled": True}
        with self.assertRaisesRegex(SensorPolicyError, "extra=.*camera"):
            SensorPolicyConfig.from_mapping(with_camera)

        invalid_backoff = deepcopy(self.raw_config)
        invalid_backoff["gnss"]["max_retry_backoff_s"] = 1
        with self.assertRaisesRegex(SensorPolicyError, "max_retry_backoff_s"):
            SensorPolicyConfig.from_mapping(invalid_backoff)

        invalid_movement = deepcopy(self.raw_config)
        invalid_movement["movement"]["exit_rms_m_s2"] = 2.0
        with self.assertRaisesRegex(SensorPolicyError, "exit_rms_m_s2"):
            SensorPolicyConfig.from_mapping(invalid_movement)

        invalid_confidence = deepcopy(self.raw_config)
        invalid_confidence["location"]["predicted_min_confidence"] = 0.8
        with self.assertRaisesRegex(SensorPolicyError, "predicted_min_confidence"):
            SensorPolicyConfig.from_mapping(invalid_confidence)

        nonfinite = deepcopy(self.raw_config)
        nonfinite["stationary"]["gnss_interval_s"] = float("inf")
        with self.assertRaisesRegex(SensorPolicyError, "finite"):
            SensorPolicyConfig.from_mapping(nonfinite)

        sub_millisecond = deepcopy(self.raw_config)
        sub_millisecond["gnss"]["retry_backoff_s"] = 0.0001
        with self.assertRaisesRegex(SensorPolicyError, "one millisecond"):
            SensorPolicyConfig.from_mapping(sub_millisecond)

        semantic = CONFIG_SCHEMA["x-egolink-semantic-validation"]
        self.assertEqual(self.raw_config["semantic_validation"], semantic["validator_id"])
        self.assertGreaterEqual(len(semantic["rules"]), 8)

    def test_sos_new_fix_upload_is_not_suppressed_by_last_trusted_toggle(self) -> None:
        raw = deepcopy(self.raw_config)
        raw["sos"]["upload_last_trusted"] = False
        config = SensorPolicyConfig.from_mapping(raw)
        engine = LocationEngineV0(config.location_engine_config())
        policy = SensorPolicyV0(config)

        sos = {"event_type": "sos", "event_time_ms": 0, "active": True}
        state = engine.process(sos)
        entered = policy.evaluate(state, event_type="sos", observation=sos)
        self.assertFalse(entered["actions"]["location"]["upload_now"])

        fix = {
            "event_type": "gnss_fix",
            "event_time_ms": 1,
            "latitude_deg": 22.5,
            "longitude_deg": 114.0,
            "accuracy_m": 10,
            "evidence": evidence(1),
        }
        state = engine.process(fix)
        decision = policy.evaluate(state, event_type="gnss_fix", observation=fix)
        self.assertEqual("fix", state["gnss_state"])
        self.assertTrue(decision["actions"]["location"]["upload_now"])

    def test_same_state_sequence_and_config_are_deterministic(self) -> None:
        events = [
            {"event_type": "tick", "event_time_ms": 0},
            {
                "event_type": "gnss_no_fix",
                "event_time_ms": 45_000,
                "evidence": evidence(45_000),
            },
            {
                "event_type": "mobility",
                "event_time_ms": 46_000,
                "mobility_state": "moving",
                "evidence": evidence(46_000),
            },
            {"event_type": "sos", "event_time_ms": 47_000, "active": True},
        ]

        def run() -> list[dict]:
            config = SensorPolicyConfig.from_mapping(self.raw_config)
            engine = LocationEngineV0(config.location_engine_config())
            policy = SensorPolicyV0(config)
            decisions = []
            for event in events:
                state = engine.process(event)
                decision = policy.evaluate(
                    state,
                    event_type=event["event_type"],
                    observation=event,
                )
                engine.set_policy_context(decision["policy_mode"])
                decisions.append(decision)
            return decisions

        self.assertEqual(run(), run())


if __name__ == "__main__":
    unittest.main()

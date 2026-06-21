from __future__ import annotations

import json
from pathlib import Path
import unittest

from pc_simulator import safety_companion


REPO_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_PATH = REPO_ROOT / "model_lab" / "safety_companion" / "datasets" / "samples" / "scenario_suite.json"
SENSOR_FRAMES_PATH = REPO_ROOT / "model_lab" / "safety_companion" / "datasets" / "samples" / "sensor_frames.jsonl"


def load_scenarios() -> dict[str, dict]:
    return {item["id"]: item for item in json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))}


def load_sensor_frames() -> list[dict]:
    return [json.loads(line) for line in SENSOR_FRAMES_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


class SafetyCompanionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scenarios = load_scenarios()

    def test_evaluate_model_input_handles_normal_walk(self) -> None:
        output = safety_companion.evaluate_model_input(self.scenarios["normal_walk"]["input"])

        self.assertEqual(output["contract_version"], safety_companion.CONTRACT_VERSION)
        self.assertEqual(output["risk_type"], "none")
        self.assertEqual(output["recommended_action"], "ignore")
        self.assertEqual(output["priority"], "info")

    def test_evaluate_model_input_handles_manual_sos(self) -> None:
        output = safety_companion.evaluate_model_input(self.scenarios["manual_sos"]["input"])

        self.assertEqual(output["risk_type"], "manual_sos")
        self.assertEqual(output["recommended_action"], "urgent_escalation")
        self.assertIn("manual_sos_pressed", output["reason_codes"])

    def test_evaluate_model_input_handles_post_impact_inactivity(self) -> None:
        output = safety_companion.evaluate_model_input(self.scenarios["post_impact_inactivity"]["input"])

        self.assertEqual(output["risk_type"], "post_impact_inactivity")
        self.assertEqual(output["recommended_action"], "ask_user")
        self.assertIn("post_impact_stationary", output["reason_codes"])

    def test_privacy_mode_filters_raw_audio_and_image_requests(self) -> None:
        output = safety_companion.evaluate_model_input(self.scenarios["privacy_restricted_impact"]["input"])

        self.assertEqual(output["risk_type"], "post_impact_inactivity")
        self.assertNotIn("audio_5s", output["evidence_request"])
        self.assertNotIn("image_single", output["evidence_request"])
        self.assertIn("privacy_restricted_raw_evidence", output["reason_codes"])

    def test_evaluate_sensor_frame_uses_package_feature_extractor(self) -> None:
        normal, sos = load_sensor_frames()

        normal_output = safety_companion.evaluate_sensor_frame(normal)
        sos_output = safety_companion.evaluate_sensor_frame(sos)

        self.assertEqual(normal_output["risk_type"], "none")
        self.assertEqual(sos_output["risk_type"], "manual_sos")
        self.assertEqual(sos_output["recommended_action"], "urgent_escalation")

    def test_evaluate_converts_non_none_output_to_safety_event(self) -> None:
        result = safety_companion.evaluate(
            [
                {
                    "event_type": "sos_pressed",
                    "ts": "2026-06-21T02:00:00+00:00",
                    "priority": "critical",
                    "battery": 87,
                }
            ],
            {
                "device_id": "ego-link-001",
                "online": True,
                "battery": 87,
                "rssi": -55,
                "guard_mode": "child_safety",
                "lat": 22.5,
                "lon": 114.0,
            },
        )

        self.assertEqual(result["model_input"]["contract_version"], safety_companion.CONTRACT_VERSION)
        self.assertEqual(result["sensor_frame"]["metadata"]["source_event_type"], "sos_pressed")
        self.assertEqual(result["model_output"]["risk_type"], "manual_sos")
        self.assertEqual(result["safety_event"]["event_type"], "manual_sos")
        self.assertEqual(result["safety_event"]["model_result"]["recommended_action"], "urgent_escalation")

    def test_location_no_fix_is_not_promoted_to_model_risk_by_adapter(self) -> None:
        result = safety_companion.evaluate(
            [
                {
                    "event_type": "location_report",
                    "ts": "2026-06-21T02:11:43+00:00",
                    "source": "sim7670g_gnss",
                    "fix": False,
                    "gnss_state": "no_fix",
                }
            ],
            {
                "device_id": "ego-link-001",
                "online": True,
                "battery": 87,
                "rssi": -61,
                "guard_mode": "child_safety",
            },
        )

        self.assertFalse(result["sensor_frame"]["sensors"]["location"]["fix_valid"])
        self.assertEqual(result["model_output"]["risk_type"], "none")
        self.assertEqual(result["model_output"]["recommended_action"], "ignore")

    def test_model_input_uses_event_timestamp_ms(self) -> None:
        result = safety_companion.evaluate(
            [{"event_type": "wake_detected", "ts": "2026-06-21T00:00:00+00:00"}],
            {"device_id": "ego-link-001", "online": True, "battery": 90, "rssi": -55},
        )

        self.assertEqual(result["model_input"]["timestamp_ms"], 1782000000000)

    def test_request_rejects_missing_payload_type(self) -> None:
        with self.assertRaises(ValueError):
            safety_companion.evaluate_request({"hello": "world"})


if __name__ == "__main__":
    unittest.main()

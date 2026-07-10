from __future__ import annotations

import json
from pathlib import Path
import unittest


CONTRACT_VERSION = "1.0.0"
CONTRACT_FILES = (
    "sensor_frame.schema.json",
    "safety_event.schema.json",
    "model_input.schema.json",
    "model_output.schema.json",
    "base_command.schema.json",
    "safety_annotation.schema.json",
)


class SafetyCompanionContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[2]
        self.contract_dir = self.repo_root / "shared" / "contracts"

    def load_schema(self, name: str) -> dict:
        path = self.contract_dir / name
        self.assertTrue(path.is_file(), f"Missing contract schema: {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    def test_contract_files_are_valid_json(self) -> None:
        for name in CONTRACT_FILES:
            with self.subTest(schema=name):
                schema = self.load_schema(name)

            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertEqual(schema["type"], "object")
            self.assertFalse(schema.get("additionalProperties", True))

    def test_contract_version_is_consistent(self) -> None:
        for name in CONTRACT_FILES:
            with self.subTest(schema=name):
                schema = self.load_schema(name)

            version = schema["properties"]["contract_version"]
            self.assertEqual(version["const"], CONTRACT_VERSION)
            self.assertIn("contract_version", schema["required"])

    def test_model_input_keeps_stable_required_sections(self) -> None:
        schema = self.load_schema("model_input.schema.json")

        self.assertEqual(
            schema["required"],
            [
                "contract_version",
                "input_id",
                "device_id",
                "timestamp_ms",
                "mode",
                "features",
                "evidence_available",
            ],
        )
        self.assertEqual(
            schema["properties"]["features"]["required"],
            ["motion", "audio", "location", "network", "device", "history", "user"],
        )

    def test_model_output_has_safety_action_enums(self) -> None:
        schema = self.load_schema("model_output.schema.json")
        actions = schema["properties"]["recommended_action"]["enum"]
        risk_types = schema["properties"]["risk_type"]["enum"]

        self.assertIn("ask_user", actions)
        self.assertIn("send_summary", actions)
        self.assertIn("urgent_escalation", actions)
        self.assertIn("manual_sos", risk_types)
        self.assertIn("post_impact_inactivity", risk_types)
        self.assertIn("communication_loss", risk_types)

    def test_safety_event_covers_p0_event_classes(self) -> None:
        schema = self.load_schema("safety_event.schema.json")
        event_types = set(schema["properties"]["event_type"]["enum"])

        self.assertTrue(
            {
                "manual_sos",
                "possible_fall",
                "possible_collision",
                "post_impact_inactivity",
                "geofence_exit",
                "abnormal_dwell",
                "distress_audio",
                "low_battery",
                "communication_loss",
            }.issubset(event_types)
        )


if __name__ == "__main__":
    unittest.main()

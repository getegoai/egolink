from __future__ import annotations

import json
import unittest
from pathlib import Path

from model_lab.safety_companion.src.baseline_router import RuleRouter
from model_lab.safety_companion.src.contract_validation import (
    ContractValidationError,
    load_schema,
    validate_instance,
)
from model_lab.safety_companion.src.event_builder import build_safety_event
from model_lab.safety_companion.src.feature_extractor import build_model_input
from model_lab.safety_companion.src.scenario_generator import build_scenario_suite, sample_sensor_frames


ROOT = Path(__file__).resolve().parents[2]


class ContractTests(unittest.TestCase):
    def test_all_contract_files_are_valid_json(self) -> None:
        schema_dir = ROOT / "shared" / "contracts"
        paths = sorted(schema_dir.glob("*.schema.json"))
        self.assertGreaterEqual(len(paths), 6)
        for path in paths:
            with self.subTest(path=path.name):
                value = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(value.get("type"), "object")
                self.assertIn("contract", value.get("$id", ""))

    def test_all_scenario_inputs_match_contract(self) -> None:
        schema = load_schema("model_input.schema.json")
        for scenario in build_scenario_suite():
            with self.subTest(scenario=scenario["id"]):
                validate_instance(scenario["input"], schema)

    def test_all_sensor_frames_and_extracted_inputs_match_contracts(self) -> None:
        frame_schema = load_schema("sensor_frame.schema.json")
        input_schema = load_schema("model_input.schema.json")
        for frame in sample_sensor_frames():
            with self.subTest(frame=frame["frame_id"]):
                validate_instance(frame, frame_schema)
                model_input = build_model_input(frame)
                validate_instance(model_input, input_schema)

    def test_invalid_contract_is_rejected(self) -> None:
        value = build_scenario_suite()[0]["input"]
        value["features"]["device"]["battery_percent"] = 101
        with self.assertRaises(ContractValidationError):
            validate_instance(value, load_schema("model_input.schema.json"))

    def test_non_none_result_can_build_safety_event(self) -> None:
        scenario = next(item for item in build_scenario_suite() if item["id"] == "manual_sos")
        result = RuleRouter().evaluate(scenario["input"])
        event = build_safety_event(scenario["input"], result, sequence=99)
        self.assertIsNotNone(event)
        validate_instance(event, load_schema("safety_event.schema.json"))
        self.assertEqual(event["priority"], "critical")


if __name__ == "__main__":
    unittest.main()

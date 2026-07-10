from __future__ import annotations

import json
import unittest
from pathlib import Path

from model_lab.safety_companion.src.contract_validation import load_schema, validate_instance
from model_lab.safety_companion.src.replay import iter_jsonl


ROOT = Path(__file__).resolve().parents[2]
SAMPLES = ROOT / "model_lab" / "safety_companion" / "datasets" / "samples"


class SampleFileTests(unittest.TestCase):
    def test_scenario_suite_file(self) -> None:
        path = SAMPLES / "scenario_suite.json"
        suite = json.loads(path.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(suite), 10)
        schema = load_schema("model_input.schema.json")
        for scenario in suite:
            validate_instance(scenario["input"], schema)

    def test_sensor_frames_jsonl(self) -> None:
        schema = load_schema("sensor_frame.schema.json")
        values = list(iter_jsonl(SAMPLES / "sensor_frames.jsonl"))
        self.assertGreaterEqual(len(values), 2)
        for value in values:
            validate_instance(value, schema)

    def test_model_inputs_jsonl(self) -> None:
        schema = load_schema("model_input.schema.json")
        values = list(iter_jsonl(SAMPLES / "model_inputs.jsonl"))
        self.assertGreaterEqual(len(values), 10)
        for value in values:
            validate_instance(value, schema)


if __name__ == "__main__":
    unittest.main()

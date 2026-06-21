from __future__ import annotations

import unittest

from model_lab.safety_companion.src.baseline_router import RuleRouter
from model_lab.safety_companion.src.contract_validation import load_schema, validate_instance
from model_lab.safety_companion.src.scenario_generator import build_scenario_suite


class BaselineRouterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.router = RuleRouter()

    def test_scenario_suite(self) -> None:
        output_schema = load_schema("model_output.schema.json")
        for scenario in build_scenario_suite():
            with self.subTest(scenario=scenario["id"]):
                output = self.router.evaluate(scenario["input"])
                expected = scenario["expected"]
                validate_instance(output, output_schema)
                self.assertEqual(output["risk_type"], expected["risk_type"])
                self.assertEqual(output["recommended_action"], expected["recommended_action"])
                self.assertEqual(output["priority"], expected["priority"])
                self.assertFalse(
                    set(expected.get("forbidden_evidence", [])) & set(output["evidence_request"])
                )

    def test_manual_sos_always_wins(self) -> None:
        scenario = build_scenario_suite()[0]["input"]
        scenario["features"]["user"]["sos_pressed"] = True
        scenario["features"]["device"]["battery_percent"] = 1.0
        scenario["features"]["network"]["offline_seconds"] = 5000.0
        output = self.router.evaluate(scenario)
        self.assertEqual(output["risk_type"], "manual_sos")
        self.assertTrue(output["safety_rule_applied"])

    def test_privacy_mode_filters_raw_evidence(self) -> None:
        scenario = next(item for item in build_scenario_suite() if item["id"] == "privacy_restricted_impact")
        output = self.router.evaluate(scenario["input"])
        self.assertNotIn("audio_5s", output["evidence_request"])
        self.assertNotIn("image_single", output["evidence_request"])
        self.assertIn("privacy_restricted_raw_evidence", output["reason_codes"])

    def test_result_is_deterministic(self) -> None:
        scenario = next(item for item in build_scenario_suite() if item["id"] == "possible_fall")
        first = self.router.evaluate(scenario["input"])
        second = self.router.evaluate(scenario["input"])
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()

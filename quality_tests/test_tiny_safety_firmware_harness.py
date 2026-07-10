from __future__ import annotations

import json
import math
from pathlib import Path
import re
import unittest


NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?f?")


class TinySafetyFirmwareHarnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.component_dir = (
            self.repo_root / "firmware" / "mqtt_heartbeat" / "components" / "safety_model"
        )
        self.public_header = (self.component_dir / "include" / "safety_model.h").read_text(
            encoding="utf-8"
        )
        self.harness_source = (self.component_dir / "tiny_safety_harness.c").read_text(
            encoding="utf-8"
        )
        self.app_main = (
            self.repo_root / "firmware" / "mqtt_heartbeat" / "main" / "app_main.c"
        ).read_text(encoding="utf-8")
        self.component_cmake = (self.component_dir / "CMakeLists.txt").read_text(encoding="utf-8")
        self.export_dir = (
            self.repo_root
            / "model_artifacts"
            / "tiny_safety_model"
            / "MODEL-DEVICE-001-tiny-safety-v0-20260707"
            / "export"
        )
        self.model_header = (self.export_dir / "tiny_safety_model.h").read_text(encoding="utf-8")
        self.vector_payload = json.loads(
            (self.export_dir / "tiny_safety_test_vectors.json").read_text(encoding="utf-8")
        )

    def parse_float_matrix(self, name: str) -> list[list[float]]:
        match = re.search(
            rf"static const float {name}\[[^\]]+\]\[[^\]]+\]\s*=\s*\{{(?P<body>.*?)\n\}};",
            self.model_header,
            re.DOTALL,
        )
        self.assertIsNotNone(match, f"missing matrix {name}")
        rows = re.findall(r"\{([^{}]+)\}", match.group("body"))
        return [
            [float(value.rstrip("f")) for value in NUMBER_RE.findall(row)]
            for row in rows
        ]

    def parse_float_vector(self, name: str) -> list[float]:
        match = re.search(
            rf"static const float {name}\[[^\]]+\]\s*=\s*\{{(?P<body>.*?)\n\}};",
            self.model_header,
            re.DOTALL,
        )
        self.assertIsNotNone(match, f"missing vector {name}")
        return [float(value.rstrip("f")) for value in NUMBER_RE.findall(match.group("body"))]

    def parse_u8_vector(self, name: str) -> list[int]:
        match = re.search(
            rf"static const uint8_t {name}\[[^\]]+\]\s*=\s*\{{(?P<body>.*?)\n\}};",
            self.model_header,
            re.DOTALL,
        )
        self.assertIsNotNone(match, f"missing vector {name}")
        return [int(value.rstrip("f")) for value in NUMBER_RE.findall(match.group("body"))]

    def test_cmake_wires_generated_model_header_as_read_only_source(self) -> None:
        self.assertIn('"tiny_safety_harness.c"', self.component_cmake)
        self.assertIn("MODEL-DEVICE-001-tiny-safety-v0-20260707/export", self.component_cmake)
        self.assertIn('#include "tiny_safety_model.h"', self.harness_source)
        self.assertIn("EGO_TINY_SAFETY_MODEL_ID", self.harness_source)
        self.assertIn("ego_tiny_safety_weights", self.harness_source)
        self.assertIn("ego_tiny_safety_test_features", self.harness_source)

    def test_public_api_is_explicitly_dry_run_and_candidate_only(self) -> None:
        for symbol in [
            "safety_model_tiny_harness_version",
            "safety_model_tiny_model_id",
            "safety_model_tiny_features_from_input",
            "safety_model_tiny_predict_features",
            "safety_model_tiny_predict_input",
            "safety_model_tiny_self_test",
        ]:
            with self.subTest(symbol=symbol):
                self.assertIn(symbol, self.public_header)

        self.assertIn("synthetic_only", self.public_header)
        self.assertIn("safety_rule_required", self.public_header)
        self.assertNotIn("recommended_action", self.harness_source)
        for forbidden in [
            "EGO_SC_ACTION_URGENT_ESCALATION",
            "EGO_SC_ACTION_SEND_SUMMARY",
            "EGO_SC_ACTION_SEND_EVIDENCE",
            "ATD",
            "CMGS",
            "send_sms",
            "place_call",
            "dispatch",
        ]:
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.harness_source)

    def test_sos_and_cancel_are_declined_to_safety_kernel(self) -> None:
        self.assertIn("SAFETY_MODEL_TINY_SAFETY_RULE_CLASS_INDEX", self.public_header)
        self.assertIn("input->sos_pressed || input->cancel_pressed", self.harness_source)
        self.assertIn('"safety_rule_required"', self.harness_source)
        self.assertIn("result->safety_rule_required = true", self.harness_source)
        self.assertIn("result->synthetic_only = true", self.harness_source)

    def test_firmware_cli_exposes_tiny_closed_loop_without_external_actions(self) -> None:
        for command in [
            "safety tiny status",
            "safety tiny selftest",
            "safety tiny demo ",
        ]:
            with self.subTest(command=command):
                self.assertIn(command, self.app_main)
        for demo_name in ["normal", "uncertain", "needs_check", "possible_risk", "sos", "cancel"]:
            with self.subTest(demo_name=demo_name):
                self.assertIn(f'"{demo_name}"', self.app_main)

        for marker in [
            "TINY_SAFETY_STATUS",
            "TINY_SAFETY_SELFTEST",
            "TINY_SAFETY_DEMO",
            "dry_run=true",
            "synthetic_only=true",
            "external_actions=false",
        ]:
            with self.subTest(marker=marker):
                self.assertIn(marker, self.app_main)

        tiny_lines = [
            line
            for line in self.app_main.splitlines()
            if "TINY_SAFETY" in line or "safety_model_tiny" in line
        ]
        tiny_text = "\n".join(tiny_lines)
        for forbidden in [
            "EGO_SC_ACTION_URGENT_ESCALATION",
            "EGO_SC_ACTION_SEND_SUMMARY",
            "EGO_SC_ACTION_SEND_EVIDENCE",
            "ATD",
            "CMGS",
            "send_sms",
            "place_call",
            "dispatch",
        ]:
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, tiny_text)

    def test_feature_adapter_matches_model_device_001_feature_order(self) -> None:
        expected_fragments = [
            "features[0] = clamp01(input->impact_score)",
            "features[1] = clamp01(input->fall_score)",
            "features[2] = clamp01(input->stationary_seconds / 120.0f)",
            "features[3] = clamp01(input->activity_confidence)",
            "features[4] = input->device_worn == 1 ? 1.0f : 0.0f",
            "features[5] = clamp01(input->distress_score)",
            "features[6] = clamp01(input->impact_sound_score)",
            "features[7] = clamp01(input->unknown_loud_sound_score)",
            "features[8] = bool_feature(input->outside_safe_zone)",
            "features[9] = clamp01(input->dwell_seconds / 1800.0f)",
            "features[10] = clamp01(input->connectivity_score)",
            "features[11] = clamp01(input->offline_seconds / 1800.0f)",
            "features[12] = clamp01((100.0f - input->battery_percent) / 100.0f)",
            "features[13] = clamp01((float)input->recent_risk_count_5m / 5.0f)",
        ]
        for fragment in expected_fragments:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.harness_source)

    def test_exported_header_test_vectors_classify_consistently(self) -> None:
        weights = self.parse_float_matrix("ego_tiny_safety_weights")
        biases = self.parse_float_vector("ego_tiny_safety_biases")
        features = self.parse_float_matrix("ego_tiny_safety_test_features")
        expected = self.parse_u8_vector("ego_tiny_safety_test_expected")
        labels = self.vector_payload["state_labels"]

        self.assertEqual(len(weights), len(labels))
        self.assertEqual(len(biases), len(labels))
        self.assertEqual(len(features), len(expected))
        self.assertEqual(len(self.vector_payload["test_vectors"]), len(features))

        for index, vector in enumerate(features):
            raw_scores = [
                biases[class_index]
                + sum(weight * value for weight, value in zip(weights[class_index], vector))
                for class_index in range(len(labels))
            ]
            peak = max(raw_scores)
            probabilities = [math.exp(score - peak) for score in raw_scores]
            total = sum(probabilities)
            best_index = max(range(len(labels)), key=lambda class_index: probabilities[class_index])
            confidence = probabilities[best_index] / total

            with self.subTest(vector=index):
                self.assertEqual(best_index, expected[index])
                self.assertEqual(
                    labels[best_index],
                    self.vector_payload["test_vectors"][index]["expected_label"],
                )
                self.assertAlmostEqual(
                    confidence,
                    self.vector_payload["test_vectors"][index]["confidence"],
                    delta=0.05,
                )


if __name__ == "__main__":
    unittest.main()

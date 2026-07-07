from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from model_lab.safety_companion.evaluation import evaluate_tiny_safety_synthetic_stress as stress
from model_lab.safety_companion.src import tiny_safety_model


def write_artifact(path: Path) -> Path:
    rows = tiny_safety_model.synthetic_training_rows(samples_per_class=12, seed=17)
    training_rows, holdout_rows = tiny_safety_model.split_rows(rows)
    artifact = tiny_safety_model.build_artifact(
        model_id="unit-stress-model",
        generated_at="2026-07-07T00:00:00+00:00",
        training_rows=training_rows,
        holdout_rows=holdout_rows,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


class TinySafetySyntheticStressTests(unittest.TestCase):
    def test_generate_cases_is_deterministic_and_synthetic_only(self) -> None:
        first = stress.generate_cases()
        second = stress.generate_cases()

        self.assertEqual(first, second)
        self.assertEqual(len(first), 540)
        self.assertEqual(first[0]["row_id"], "stress-i000-f000-s000-d000")
        self.assertTrue(all(row["synthetic_only"] for row in first))
        self.assertEqual(
            {row["expected_label"] for row in first},
            {"normal", "uncertain", "needs_check", "possible_risk"},
        )

    def test_build_report_preserves_non_claim_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_path = write_artifact(Path(tmp) / "tiny_safety_model.json")
            report = stress.build_report(
                artifact_path=artifact_path,
                evaluated_at="2026-07-07T00:00:00+00:00",
                low_confidence_threshold=0.45,
                low_margin_threshold=0.08,
                max_examples=8,
            )

        self.assertEqual(report["schema_version"], "egolink.tiny_safety_synthetic_stress.v0.1")
        self.assertEqual(report["evaluation"]["case_count"], 540)
        self.assertGreaterEqual(report["evaluation"]["synthetic_agreement_rate"], 0.0)
        self.assertLessEqual(report["evaluation"]["synthetic_agreement_rate"], 1.0)
        self.assertLessEqual(len(report["evaluation"]["hard_case_examples"]), 8)
        self.assertTrue(report["scope"]["synthetic_only"])
        self.assertFalse(report["scope"]["hardware_contacted"])
        self.assertFalse(report["scope"]["model_behavior_changed"])
        self.assertFalse(report["scope"]["field_or_private_data_read"])
        self.assertFalse(report["scope"]["real_accuracy_claimed"])
        self.assertIn("Synthetic oracle agreement is not real-world accuracy.", report["known_gaps"])
        self.assertIn("No real-world fall detection", " ".join(report["non_claims"]))

    def test_cli_writes_report_and_sha(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact_path = write_artifact(root / "tiny_safety_model.json")
            output_dir = root / "evaluation"
            exit_code = stress.main(
                [
                    "--model-artifact",
                    str(artifact_path),
                    "--output-dir",
                    str(output_dir),
                    "--evaluated-at",
                    "2026-07-07T00:00:00+00:00",
                    "--max-examples",
                    "5",
                ]
            )
            report = json.loads((output_dir / stress.REPORT_JSON).read_text(encoding="utf-8"))
            markdown = (output_dir / stress.REPORT_MARKDOWN).read_text(encoding="utf-8")
            sha = (output_dir / stress.SHA256).read_text(encoding="utf-8")

        self.assertEqual(exit_code, 0)
        self.assertIn("Tiny Safety Synthetic Stress Evaluation", markdown)
        self.assertEqual(len(report["evaluation"]["hard_case_examples"]), 5)
        self.assertIn(stress.REPORT_JSON, sha)
        self.assertIn(stress.REPORT_MARKDOWN, sha)


if __name__ == "__main__":
    unittest.main()

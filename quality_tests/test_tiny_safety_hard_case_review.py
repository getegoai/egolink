from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from model_lab.safety_companion.evaluation import evaluate_tiny_safety_synthetic_stress as stress
from model_lab.safety_companion.evaluation import export_tiny_safety_hard_case_review as review
from model_lab.safety_companion.src import tiny_safety_model


def write_artifact(path: Path) -> Path:
    rows = tiny_safety_model.synthetic_training_rows(samples_per_class=12, seed=17)
    training_rows, holdout_rows = tiny_safety_model.split_rows(rows)
    artifact = tiny_safety_model.build_artifact(
        model_id="unit-hard-case-model",
        generated_at="2026-07-07T00:00:00+00:00",
        training_rows=training_rows,
        holdout_rows=holdout_rows,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_stress_report(path: Path, *, max_examples: int = 8) -> Path:
    artifact_path = write_artifact(path.parent / "tiny_safety_model.json")
    report = stress.build_report(
        artifact_path=artifact_path,
        evaluated_at="2026-07-07T00:00:00+00:00",
        low_confidence_threshold=0.45,
        low_margin_threshold=0.08,
        max_examples=max_examples,
    )
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


class TinySafetyHardCaseReviewTests(unittest.TestCase):
    def test_build_packet_is_deterministic_and_training_disallowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stress_path = write_stress_report(Path(tmp) / "tiny_safety_synthetic_stress.json", max_examples=10)
            first_manifest, first_records = review.build_packet(
                stress_report_path=stress_path,
                generated_at="2026-07-07T01:00:00+00:00",
                review_set_id="unit-review",
                max_records=5,
            )
            second_manifest, second_records = review.build_packet(
                stress_report_path=stress_path,
                generated_at="2026-07-07T01:00:00+00:00",
                review_set_id="unit-review",
                max_records=5,
            )

        self.assertEqual(first_manifest, second_manifest)
        self.assertEqual(first_records, second_records)
        self.assertEqual(first_manifest["schema_version"], review.MANIFEST_SCHEMA_VERSION)
        self.assertEqual(first_manifest["status"], "ready_for_synthetic_review")
        self.assertFalse(first_manifest["review_policy"]["training_allowed"])
        self.assertFalse(first_manifest["gates"]["human_review_completed"])
        self.assertEqual(first_manifest["gates"]["model_training"], "not_run")
        self.assertEqual(len(first_records), 5)
        self.assertTrue(all(record["review"]["state"] == "needs_human_review" for record in first_records))
        self.assertTrue(all(record["review"]["reviewer_label"] is None for record in first_records))
        self.assertTrue(all(record["privacy"]["synthetic_only"] for record in first_records))
        self.assertTrue(all(not record["privacy"]["field_or_private_data"] for record in first_records))

    def test_records_preserve_lineage_without_private_or_raw_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            stress_path = write_stress_report(tmp_path / "tiny_safety_synthetic_stress.json", max_examples=6)
            manifest, records = review.build_packet(
                stress_report_path=stress_path,
                generated_at="2026-07-07T01:05:00+00:00",
                review_set_id="unit-lineage",
                max_records=3,
            )
            payload = json.dumps({"manifest": manifest, "records": records}, ensure_ascii=False)

        self.assertEqual(manifest["counts"]["records_exported"], 3)
        self.assertIn("synthetic_oracle_disagreement", manifest["counts"]["priority_reasons"])
        self.assertIn(records[0]["model"]["predicted_label"], tiny_safety_model.STATE_LABELS)
        self.assertIn(records[0]["synthetic_oracle"]["label"], tiny_safety_model.STATE_LABELS)
        self.assertFalse(records[0]["synthetic_oracle"]["is_truth_source"])
        self.assertIn("motion_impact_score", records[0]["features"])
        self.assertNotIn(str(tmp_path), payload)
        self.assertNotIn("raw_payload", payload)
        self.assertNotIn("recording_path", payload)
        self.assertNotIn("candidate.db", payload)
        self.assertNotIn("private_coordinates", json.dumps(records[0]["features"], ensure_ascii=False))

    def test_cli_writes_manifest_records_markdown_and_sha(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stress_path = write_stress_report(root / "tiny_safety_synthetic_stress.json", max_examples=7)
            output_dir = root / "label_review"
            with redirect_stdout(StringIO()) as output:
                exit_code = review.main(
                    [
                        "--stress-report",
                        str(stress_path),
                        "--output-dir",
                        str(output_dir),
                        "--review-set-id",
                        "unit-cli-review",
                        "--generated-at",
                        "2026-07-07T01:10:00+00:00",
                        "--max-records",
                        "4",
                        "--json",
                    ]
                )
            payload = json.loads(output.getvalue())
            manifest = json.loads((output_dir / review.MANIFEST_JSON).read_text(encoding="utf-8"))
            records = [
                json.loads(line)
                for line in (output_dir / review.RECORDS_JSONL).read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            markdown = (output_dir / review.REPORT_MARKDOWN).read_text(encoding="utf-8")
            sha = (output_dir / review.SHA256).read_text(encoding="utf-8")

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["review_set_id"], "unit-cli-review")
        self.assertEqual(manifest["counts"]["records_exported"], 4)
        self.assertEqual(len(records), 4)
        self.assertIn("Tiny Safety Hard-Case Review Packet", markdown)
        self.assertIn(review.MANIFEST_JSON, sha)
        self.assertIn(review.RECORDS_JSONL, sha)
        self.assertIn(review.REPORT_MARKDOWN, sha)


if __name__ == "__main__":
    unittest.main()

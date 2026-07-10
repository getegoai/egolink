from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest

from quality_tests.test_location_fusion_dataset_export import FIXED_CREATED_AT, kr003_like_export
from scripts import evaluate_eale_p0_dataset as evaluator
from scripts import export_location_fusion_dataset as exporter


def build_dataset(export: dict, **kwargs: object) -> tuple[list[dict], dict]:
    options = {"created_at": FIXED_CREATED_AT}
    options.update(kwargs)
    return exporter.build_dataset(export, **options)


class EaleP0DatasetEvaluationTests(unittest.TestCase):
    def test_evaluates_failure_window_without_losing_lineage(self) -> None:
        samples, manifest = build_dataset(kr003_like_export(), split_name="holdout")

        report = evaluator.evaluate_dataset(
            samples,
            manifest,
            created_at=FIXED_CREATED_AT,
            samples_path=Path("samples.jsonl"),
            manifest_path=Path("manifest.json"),
        )

        self.assertEqual(report["result"]["status"], "warn")
        self.assertIn("failure_windows_retained_for_diagnosis", report["result"]["warnings"])
        self.assertEqual(report["counts"]["samples"], 1)
        self.assertEqual(report["counts"]["sample_types"], {"failure_window": 1})
        self.assertEqual(report["counts"]["failure_modes"]["gnss_no_fix"], 1)
        self.assertEqual(report["coverage"]["lineage"]["raw_frame_refs_total"], 3)
        self.assertEqual(report["coverage"]["lineage"]["derived_event_refs_total"], 2)
        self.assertEqual(report["coverage"]["feature_groups"]["gnss"], 1)
        self.assertEqual(report["coverage"]["feature_groups"]["cell"], 1)
        self.assertEqual(report["coverage"]["feature_groups"]["lte"], 1)
        self.assertEqual(report["eale_p0"]["failure_window_retained"], 1)
        self.assertEqual(report["eale_p0"]["unknown_no_precise_fix"], 1)
        self.assertEqual(report["eale_p0"]["cell_lte_without_position"], 1)
        self.assertFalse(report["training_readiness"]["model_training_ready"])
        self.assertFalse(report["release_gate_usage"]["can_support_product_accuracy_claim"])

    def test_fine_private_sample_can_be_training_ready_only_when_explicitly_allowed(self) -> None:
        export = deepcopy(kr003_like_export())
        report_message = export["messages"][0]
        report_message["fix"] = True
        report_message["gnss_state"] = "fixed"
        report_message["lat"] = 22.123456
        report_message["lon"] = 113.123456
        export["messages"][1]["location_belief"] = {
            "state": "Fine",
            "confidence": 0.95,
            "source": "gnss_report",
            "reason": "trusted_gnss_fix",
        }

        samples, manifest = build_dataset(
            export,
            include_private_location=True,
            allow_private_location_training=True,
        )
        report = evaluator.evaluate_dataset(samples, manifest, created_at=FIXED_CREATED_AT)

        self.assertEqual(report["result"]["status"], "pass")
        self.assertEqual(report["counts"]["sample_types"], {"known_place_calibration_window": 1})
        self.assertEqual(report["counts"]["label_states"], {"Fine": 1})
        self.assertEqual(report["coverage"]["privacy"]["training_allowed"], 1)
        self.assertEqual(report["eale_p0"]["fine_candidates"], 1)
        self.assertTrue(report["training_readiness"]["model_training_ready"])

    def test_cli_writes_json_and_markdown_report(self) -> None:
        samples, manifest = build_dataset(kr003_like_export())

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            dataset_dir = tmp_path / "dataset"
            output_dir = tmp_path / "report"
            dataset_dir.mkdir()
            (dataset_dir / "samples.jsonl").write_text(
                "\n".join(json.dumps(sample, sort_keys=True) for sample in samples) + "\n",
                encoding="utf-8",
            )
            (dataset_dir / "manifest.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = evaluator.main(
                    [
                        "--dataset-dir",
                        str(dataset_dir),
                        "--output-dir",
                        str(output_dir),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertIn("WARN EALE-P0 dataset evaluation", stdout.getvalue())
            report_json = json.loads((output_dir / evaluator.REPORT_JSON).read_text(encoding="utf-8"))
            report_md = (output_dir / evaluator.REPORT_MARKDOWN).read_text(encoding="utf-8")
            self.assertEqual(report_json["result"]["status"], "warn")
            self.assertIn("EALE-P0 DATA-001 Evaluation Report", report_md)
            self.assertIn("Failure windows retained: 1", report_md)


if __name__ == "__main__":
    unittest.main()

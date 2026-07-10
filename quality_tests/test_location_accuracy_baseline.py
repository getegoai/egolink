from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from quality_tests.test_gnss_acceptance_analysis import BASE_LAT, BASE_LON, FIXED_CREATED_AT, synthetic_fixture
from scripts import analyze_location_accuracy_baseline as baseline


class LocationAccuracyBaselineTests(unittest.TestCase):
    def test_d2_baseline_report_computes_metrics_without_raw_coordinates(self) -> None:
        export, manifest = synthetic_fixture()
        manifest["reference_points"][0]["name"] = "private-home-reference"
        export["raw_reference_points"] = [{"lat": BASE_LAT, "lon": BASE_LON, "label": "private-home"}]

        report = baseline.build_location_accuracy_report(
            export,
            manifest,
            created_at=FIXED_CREATED_AT,
        )

        self.assertEqual(report["schema_version"], "egolink.d2_location_accuracy_report.v0.1")
        self.assertEqual(report["result"]["status"], "PASS")
        self.assertEqual(report["metrics"]["reference_point_count"], 3)
        self.assertEqual(report["metrics"]["attempt_count"], 30)
        self.assertEqual(report["metrics"]["fix_rate"], 1.0)
        self.assertEqual(report["metrics"]["ttff_median_s"], 18.0)
        self.assertGreater(report["metrics"]["median_error_m"], 0.0)
        self.assertGreaterEqual(report["metrics"]["p90_error_m"], report["metrics"]["median_error_m"])
        self.assertEqual(len(report["per_point"]), 3)
        self.assertFalse(report["scope"]["location_accuracy_claimed"])
        self.assertFalse(report["scope"]["model_training_started"])
        self.assertTrue(report["scope"]["engineering_baseline_only"])
        self.assertFalse(report["privacy"]["raw_coordinates_exposed"])
        self.assertFalse(report["privacy"]["exact_coordinates_copied"])
        payload = json.dumps(report)
        self.assertNotIn(f"{BASE_LAT:.6f}", payload)
        self.assertNotIn(f"{BASE_LON:.6f}", payload)
        self.assertNotIn("private-home", payload)
        self.assertNotIn("selected_observation", payload)

    def test_cli_writes_location_accuracy_json_and_markdown(self) -> None:
        export, manifest = synthetic_fixture()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "test_run_export.json"
            manifest_path = tmp_path / "field_manifest.json"
            output_dir = tmp_path / "location_accuracy"
            input_path.write_text(json.dumps(export, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = baseline.main(
                    [
                        "--input",
                        str(input_path),
                        "--manifest",
                        str(manifest_path),
                        "--output-dir",
                        str(output_dir),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertIn("PASS D2 location accuracy baseline", stdout.getvalue())
            report_json = json.loads((output_dir / baseline.REPORT_JSON).read_text(encoding="utf-8"))
            report_md = (output_dir / baseline.REPORT_MARKDOWN).read_text(encoding="utf-8")
            self.assertEqual(report_json["result"]["status"], "PASS")
            self.assertIsNotNone(report_json["metrics"]["p90_error_m"])
            self.assertEqual(report_json["privacy"]["static_report_policy"], "bounded_summary_no_raw_coordinates")
            self.assertIn("D2 Location Accuracy Baseline", report_md)
            self.assertIn("Core Metrics", report_md)
            self.assertIn("Non-Claims", report_md)


if __name__ == "__main__":
    unittest.main()

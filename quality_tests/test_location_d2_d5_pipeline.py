from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from quality_tests.test_gnss_acceptance_analysis import BASE_LAT, BASE_LON, synthetic_fixture
from scripts import analyze_location_accuracy_baseline as baseline
from scripts import run_location_d2_d5_pipeline as pipeline
from scripts import summarize_location_data_flywheel as flywheel
from server import message_hub


class LocationD2D5PipelineTests(unittest.TestCase):
    def test_cli_runs_d2_baseline_and_d5_flywheel_from_explicit_inputs(self) -> None:
        export, manifest = synthetic_fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "test_run_export.json"
            manifest_path = root / "field_manifest.json"
            location_root = root / "location_accuracy"
            flywheel_root = root / "data_flywheel"
            pipeline_root = root / "location_pipeline"
            input_path.write_text(json.dumps(export, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = pipeline.main(
                    [
                        "--input",
                        str(input_path),
                        "--manifest",
                        str(manifest_path),
                        "--location-output-root",
                        str(location_root),
                        "--flywheel-output-root",
                        str(flywheel_root),
                        "--pipeline-output-root",
                        str(pipeline_root),
                        "--run-id",
                        "unit-location-pipeline",
                        "--generated-at",
                        "2026-07-09T12:30:00+00:00",
                        "--json",
                    ]
                )
            summary = json.loads(stdout.getvalue())
            dashboard = message_hub.load_latest_data_flywheel_status(flywheel_root)
            d2_report_exists = (location_root / "unit-location-pipeline" / baseline.REPORT_JSON).exists()
            d5_status_exists = (
                flywheel_root
                / "unit-location-pipeline-data-flywheel"
                / flywheel.STATUS_JSON
            ).exists()
            pipeline_report_exists = (
                pipeline_root
                / "unit-location-pipeline"
                / pipeline.SUMMARY_JSON
            ).exists()

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["schema_version"], "egolink.location_d2_d5_pipeline.v0.2")
        self.assertEqual(summary["status"], "needs_location_review")
        self.assertEqual(summary["d2_baseline"]["status"], "PASS")
        self.assertEqual(summary["d2_baseline"]["reference_points"], 3)
        self.assertEqual(summary["d5_flywheel"]["review_records"], 3)
        self.assertFalse(summary["d5_flywheel"]["model_training_ready"])
        self.assertTrue(d2_report_exists)
        self.assertTrue(d5_status_exists)
        self.assertTrue(pipeline_report_exists)
        self.assertTrue(dashboard["available"])
        self.assertEqual(dashboard["counts"]["location_baseline_reports"], 1)
        self.assertEqual(dashboard["counts"]["reference_points"], 3)
        payload = json.dumps(summary, ensure_ascii=False)
        self.assertNotIn(f"{BASE_LAT:.6f}", payload)
        self.assertNotIn(f"{BASE_LON:.6f}", payload)
        self.assertNotIn("selected_observation", payload)

    def test_cli_can_fetch_read_only_export_and_preserve_it_in_gnss_evidence(self) -> None:
        export, manifest = synthetic_fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = root / "field_manifest.json"
            token_path = root / "token.txt"
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            token_path.write_text("unit-secret-token\n", encoding="utf-8")
            stdout = io.StringIO()
            with mock.patch.object(pipeline, "fetch_message_hub_export", return_value=export) as fetch:
                with redirect_stdout(stdout):
                    exit_code = pipeline.main(
                        [
                            "--hub",
                            "http://hub.example:8790",
                            "--test-run-id",
                            "FIELD-003-remote-unit",
                            "--token-file",
                            str(token_path),
                            "--manifest",
                            str(manifest_path),
                            "--run-id",
                            "remote-unit",
                            "--gnss-output-root",
                            str(root / "gnss"),
                            "--location-output-root",
                            str(root / "location"),
                            "--flywheel-output-root",
                            str(root / "flywheel"),
                            "--pipeline-output-root",
                            str(root / "pipeline"),
                            "--generated-at",
                            "2026-07-11T01:00:00+00:00",
                            "--json",
                        ]
                    )
            summary = json.loads(stdout.getvalue())
            preserved_export = root / "gnss" / "remote-unit" / "test_run_export.json"
            preserved_export_exists = preserved_export.exists()

        self.assertEqual(exit_code, 0)
        self.assertTrue(preserved_export_exists)
        fetch.assert_called_once_with(
            hub_url="http://hub.example:8790",
            test_run_id="FIELD-003-remote-unit",
            token="unit-secret-token",
            timeout_sec=120.0,
        )
        self.assertNotIn("unit-secret-token", json.dumps(summary))
        self.assertTrue(summary["input_refs"]["test_run_export"].endswith("test_run_export.json"))

    def test_cli_rejects_ambiguous_input_sources(self) -> None:
        export, manifest = synthetic_fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "test_run_export.json"
            manifest_path = root / "field_manifest.json"
            input_path.write_text(json.dumps(export), encoding="utf-8")
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with mock.patch("sys.stderr", new=io.StringIO()):
                with redirect_stdout(io.StringIO()):
                    exit_code = pipeline.main(
                        [
                            "--input",
                            str(input_path),
                            "--hub",
                            "http://hub.example:8790",
                            "--test-run-id",
                            "run-unit",
                            "--manifest",
                            str(manifest_path),
                        ]
                    )

        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()

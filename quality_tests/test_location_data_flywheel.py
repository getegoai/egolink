from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from quality_tests.test_gnss_acceptance_analysis import BASE_LAT, BASE_LON, FIXED_CREATED_AT, synthetic_fixture
from scripts import analyze_location_accuracy_baseline as baseline
from scripts import summarize_location_data_flywheel as flywheel
from server import message_hub


class LocationDataFlywheelTests(unittest.TestCase):
    def write_baseline_report(self, root: Path) -> Path:
        export, manifest = synthetic_fixture()
        manifest["reference_points"][0]["name"] = "private-home-reference"
        report = baseline.build_location_accuracy_report(
            export,
            manifest,
            created_at=FIXED_CREATED_AT,
        )
        report_dir = root / "location_accuracy" / "FIELD-003-20260703-unit"
        report_dir.mkdir(parents=True)
        report_path = report_dir / baseline.REPORT_JSON
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return report_path

    def test_location_data_flywheel_builds_review_packet_without_training_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_path = self.write_baseline_report(root)

            bundle = flywheel.build_location_data_flywheel(
                baseline_report_path=report_path,
                generated_at="2026-07-09T12:00:00+00:00",
                run_id="unit-location-flywheel",
            )

        status = bundle["data_flywheel_status"]
        packet = bundle["review_packet"]
        manifest = bundle["dataset_manifest"]
        self.assertEqual(status["schema_version"], "egolink.data_flywheel_status.v0.1")
        self.assertEqual(status["status"], "needs_review")
        self.assertEqual(status["pipeline_stage"], "location_review_packet_pending")
        self.assertEqual(status["counts"]["records_total"], 3)
        self.assertEqual(status["counts"]["reference_points"], 3)
        self.assertEqual(status["review_queue"]["pending_records"], 3)
        self.assertEqual(status["candidate_type_counts"]["location_reference_point"], 3)
        self.assertFalse(status["readiness"]["model_training_ready"])
        self.assertFalse(status["readiness"]["dataset_manifest_ready"])
        self.assertEqual(manifest["status"], "not_ready")
        self.assertEqual(manifest["reason"], "explicit_selection_missing")
        self.assertIn("location_no_fix", packet["record_type_templates"])
        self.assertIn("location_bad_fix", packet["record_type_templates"])
        self.assertIn("location_known_place", packet["record_type_templates"])
        payload = json.dumps(bundle, ensure_ascii=False)
        self.assertNotIn(f"{BASE_LAT:.6f}", payload)
        self.assertNotIn(f"{BASE_LON:.6f}", payload)
        self.assertNotIn("private-home", payload)
        self.assertNotIn("selected_observation", payload)

    def test_cli_writes_dashboard_compatible_status_and_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_path = self.write_baseline_report(root)
            output_root = root / "data_flywheel"

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = flywheel.main(
                    [
                        "--baseline-report",
                        str(report_path),
                        "--output-root",
                        str(output_root),
                        "--run-id",
                        "unit-location-flywheel",
                        "--generated-at",
                        "2026-07-09T12:00:00+00:00",
                        "--json",
                    ]
            )
            status = json.loads(stdout.getvalue())
            dashboard = message_hub.load_latest_data_flywheel_status(output_root)
            status_exists = (output_root / "unit-location-flywheel" / flywheel.STATUS_JSON).exists()
            packet_exists = (output_root / "unit-location-flywheel" / flywheel.REVIEW_PACKET_JSON).exists()
            manifest_exists = (output_root / "unit-location-flywheel" / flywheel.DATASET_MANIFEST_JSON).exists()

        self.assertEqual(exit_code, 0)
        self.assertEqual(status["run_id"], "unit-location-flywheel")
        self.assertEqual(status["counts"]["records_total"], 3)
        self.assertTrue(status_exists)
        self.assertTrue(packet_exists)
        self.assertTrue(manifest_exists)
        self.assertTrue(dashboard["available"])
        self.assertEqual(dashboard["status"], "needs_review")
        self.assertEqual(dashboard["counts"]["records_total"], 3)
        self.assertEqual(dashboard["review_queue"]["pending_records"], 3)
        self.assertFalse(dashboard["readiness"]["model_training_ready"])
        self.assertIn("mark_labelled", dashboard["review_queue"]["available_actions"])
        payload = json.dumps(dashboard, ensure_ascii=False)
        self.assertNotIn(f"{BASE_LAT:.6f}", payload)

    def test_dataset_manifest_requires_explicit_reviewed_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_path = self.write_baseline_report(root)
            initial = flywheel.build_location_data_flywheel(
                baseline_report_path=report_path,
                generated_at="2026-07-09T12:00:00+00:00",
                run_id="unit-location-flywheel",
            )
            record_id = initial["review_packet"]["review_records"][0]["record_id"]
            selection_path = root / "selection.json"
            selection_path.write_text(
                json.dumps(
                    {
                        "selected_records": [
                            {
                                "record_id": record_id,
                                "operator_label": "reference_point_quality_reviewed",
                                "quality_reviewed": True,
                                "privacy_reviewed": True,
                                "training_allowed": True,
                                "split_name": "field_session_unit_train",
                                "split_leakage_checked": True,
                                "candidate_decision": "ready_for_dataset",
                            }
                        ]
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            selected = flywheel.build_location_data_flywheel(
                baseline_report_path=report_path,
                selection_path=selection_path,
                generated_at="2026-07-09T12:01:00+00:00",
                run_id="unit-location-flywheel-selected",
            )

        manifest = selected["dataset_manifest"]
        status = selected["data_flywheel_status"]
        self.assertEqual(manifest["status"], "ready_for_evaluation_handoff")
        self.assertEqual(manifest["counts"]["eligible_records"], 1)
        self.assertTrue(status["readiness"]["dataset_manifest_ready"])
        self.assertFalse(status["readiness"]["model_training_ready"])
        self.assertEqual(status["readiness"]["reason"], "founder_model_task_approval_required")


if __name__ == "__main__":
    unittest.main()

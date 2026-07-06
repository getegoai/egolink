from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from scripts import assess_d1_training_readiness


class D1TrainingReadinessTests(unittest.TestCase):
    def run_assessment(self, args: list[str]) -> tuple[int, dict[str, object], str]:
        with redirect_stdout(StringIO()) as output:
            exit_code = assess_d1_training_readiness.main(args + ["--json"])
        text = output.getvalue()
        return exit_code, json.loads(text), text

    def test_completed_field_report_becomes_labeling_review_ready_without_training_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            observation = root / "d1_field_observation" / "field-run"
            output_root = root / "d1_training_readiness"
            observation.mkdir(parents=True)
            report_path = observation / "d1_field_observation_report.json"
            report_path.write_text(
                json.dumps(
                    {
                        "tool": "observe_d1_field_run",
                        "result": "PASS",
                        "created_at": "2026-07-06T11:20:43+00:00",
                        "run_id": "field-run-private-coord",
                        "device_id": "ego-link-r1-connectivity-001",
                        "summary": {
                            "sample_count": 5,
                            "successful_sample_count": 5,
                            "fetch_error_count": 0,
                            "stale_sample_count": 0,
                            "coordinate_sample_count": 5,
                            "max_freshness_s": 62.0,
                            "last_seq": 52,
                            "first_location_upload_at": "2026-07-06T11:19:10+00:00",
                            "last_location_upload_at": "2026-07-06T11:20:18+00:00",
                            "raw_post_success_delta": 2,
                            "raw_post_failure_delta": 0,
                            "location_event_count_delta": 0,
                            "power_sample_count_delta": 0,
                            "map_modes": ["memory_coordinate"],
                            "cell_registration_states": ["registered_home"],
                            "cell_pdp_states": ["active"],
                            "gnss_states": ["unknown"],
                            "imu_evidence_statuses": ["mock"],
                            "power_evidence_statuses": ["measured"],
                            "lat": 31.123456,
                            "lon": 121.654321,
                        },
                        "raw_payload": {"lat": 31.123456, "lon": 121.654321},
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            exit_code, payload, stdout_text = self.run_assessment(
                [
                    "--field-observation-report",
                    str(report_path),
                    "--run-id",
                    "unit-d1-training-readiness",
                    "--generated-at",
                    "2026-07-06T11:30:00+00:00",
                    "--output-root",
                    str(output_root),
                ]
            )
            run_dir = output_root / "unit-d1-training-readiness"
            summary_json = run_dir / "d1_training_readiness.json"
            summary_md = run_dir / "d1_training_readiness.md"
            output_text = stdout_text + summary_json.read_text(encoding="utf-8") + summary_md.read_text(encoding="utf-8")
            summary_json_exists = summary_json.is_file()
            summary_md_exists = summary_md.is_file()

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["schema_version"], "egolink.d1_training_readiness.v0.1")
        self.assertEqual(payload["serves_demo"], "D5")
        self.assertEqual(payload["status"], "ready_for_labeling_review")
        self.assertTrue(payload["readiness"]["ready_for_labeling_review"])
        self.assertFalse(payload["readiness"]["ready_for_training_handoff"])
        self.assertFalse(payload["readiness"]["training_allowed"])
        self.assertFalse(payload["scope"]["sample_jsonl_read"])
        self.assertFalse(payload["scope"]["model_training_started"])
        self.assertEqual(payload["gates"]["privacy"]["status"], "blocked")
        self.assertEqual(payload["gates"]["labels"]["status"], "blocked")
        self.assertEqual(payload["evidence_coverage"]["transport"]["raw_post_success_delta"], 2)
        self.assertEqual(payload["evidence_coverage"]["location"]["coordinate_sample_count"], 5)
        self.assertFalse(payload["evidence_coverage"]["location"]["coordinate_values_copied"])
        self.assertIn("operator_or_user_labels_missing", payload["readiness"]["blockers"])
        self.assertTrue(summary_json_exists)
        self.assertTrue(summary_md_exists)
        self.assertNotIn("31.123456", output_text)
        self.assertNotIn("121.654321", output_text)
        self.assertNotIn("raw_payload", output_text)
        self.assertNotIn("d1_field_samples.jsonl", output_text)
        self.assertNotIn('"features":', output_text)
        self.assertNotIn('"target":', output_text)

    def test_running_status_is_bounded_and_needs_capture_when_no_samples(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            status_path = root / "run" / "d1_field_observation_status.json"
            status_path.parent.mkdir(parents=True)
            status_path.write_text(
                json.dumps(
                    {
                        "status": "running",
                        "run_id": "field-running",
                        "device_id": "ego-link-r1-connectivity-001",
                        "sample_count": 0,
                        "successful_sample_count": 0,
                        "fetch_error_count": 0,
                        "latest_seq": None,
                        "samples_path": "private/d1_field_samples.jsonl",
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            exit_code, payload, stdout_text = self.run_assessment(
                [
                    "--field-observation-status",
                    str(status_path),
                    "--run-id",
                    "unit-running-status",
                    "--output-root",
                    str(root / "out"),
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "needs_capture")
        self.assertFalse(payload["readiness"]["ready_for_labeling_review"])
        self.assertEqual(payload["source_observation"]["source"], "field_observation_status")
        self.assertFalse(payload["source_observation"]["samples_jsonl_read"])
        self.assertNotIn("d1_field_samples.jsonl", stdout_text)


if __name__ == "__main__":
    unittest.main()

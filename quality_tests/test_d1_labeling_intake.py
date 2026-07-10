from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from scripts import build_d1_labeling_intake


class D1LabelingIntakeTests(unittest.TestCase):
    def run_builder(self, args: list[str]) -> tuple[int, dict[str, object], str]:
        with redirect_stdout(StringIO()) as output:
            exit_code = build_d1_labeling_intake.main(args + ["--json"])
        text = output.getvalue()
        return exit_code, json.loads(text), text

    def write_readiness_report(self, path: Path, *, status: str, ready: bool) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "tool": "assess_d1_training_readiness",
                    "schema_version": "egolink.d1_training_readiness.v0.1",
                    "run_id": "field-run-training-readiness",
                    "generated_at": "2026-07-06T11:30:00+00:00",
                    "status": status,
                    "reason": "field_observation_can_enter_human_review_but_not_training",
                    "source_observation": {
                        "run_id": "field-run-private-coord",
                        "source": "field_observation_report",
                        "status": "completed",
                        "result": "PASS",
                        "device_id": "ego-link-r1-connectivity-001",
                        "sample_count": 5,
                        "successful_sample_count": 5,
                        "fetch_error_count": 0,
                        "latest_seq": 52,
                        "max_freshness_s": 62,
                        "last_location_upload_at": "2026-07-06T11:20:18+00:00",
                        "report_path": "C:/private/local/d1_field_observation_report.json",
                        "status_path": "C:/private/local/d1_field_observation_status.json",
                        "samples_path": "C:/private/local/d1_field_samples.jsonl",
                        "lat": 31.123456,
                        "lon": 121.654321,
                    },
                    "evidence_coverage": {
                        "capture": {
                            "sample_count": 5,
                            "successful_sample_count": 5,
                            "fetch_error_count": 0,
                            "ready_for_review": ready,
                        },
                        "transport": {
                            "raw_post_success_delta": 2,
                            "raw_post_failure_delta": 0,
                            "lte_registration_seen": True,
                            "pdp_active_seen": True,
                        },
                        "location": {
                            "coordinate_sample_count": 5,
                            "location_event_count_delta": 3,
                            "map_modes": ["memory_coordinate"],
                            "gnss_states": ["unknown"],
                            "gnss_fix_seen": False,
                            "coordinate_values_copied": False,
                            "accuracy_claimed": False,
                            "lat": 31.123456,
                            "lon": 121.654321,
                        },
                        "sensors": {
                            "imu_evidence_statuses": ["mock"],
                            "power_evidence_statuses": ["measured"],
                            "power_measured_seen": True,
                            "real_imu_seen": False,
                        },
                    },
                    "readiness": {
                        "ready_for_labeling_review": ready,
                        "ready_for_training_handoff": False,
                        "training_allowed": False,
                        "consent_status": "not_reviewed",
                        "privacy_review": "required",
                        "label_review_state": "missing",
                        "split_leakage_checked": False,
                        "quality_gaps": ["gnss_fix_not_seen", "imu_real_evidence_missing"],
                        "blockers": [
                            "privacy_review_required",
                            "training_consent_not_granted",
                            "operator_or_user_labels_missing",
                            "split_plan_missing",
                        ],
                    },
                    "scope": {
                        "sample_jsonl_read": False,
                        "model_training_started": False,
                        "model_artifact_written": False,
                    },
                    "raw_payload": {"lat": 31.123456, "lon": 121.654321},
                    "features": {"private": "do-not-copy"},
                    "target": {"private": "do-not-copy"},
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def test_ready_readiness_report_becomes_pending_human_review_without_private_details(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readiness_path = root / "d1_training_readiness" / "run" / "d1_training_readiness.json"
            output_root = root / "d1_labeling_intake"
            self.write_readiness_report(readiness_path, status="ready_for_labeling_review", ready=True)

            exit_code, payload, stdout_text = self.run_builder(
                [
                    "--training-readiness-report",
                    str(readiness_path),
                    "--run-id",
                    "unit-d1-labeling-intake",
                    "--generated-at",
                    "2026-07-06T11:35:00+00:00",
                    "--output-root",
                    str(output_root),
                ]
            )
            run_dir = output_root / "unit-d1-labeling-intake"
            summary_json = run_dir / "d1_labeling_intake.json"
            summary_md = run_dir / "d1_labeling_intake.md"
            output_text = stdout_text + summary_json.read_text(encoding="utf-8") + summary_md.read_text(encoding="utf-8")
            summary_json_exists = summary_json.is_file()
            summary_md_exists = summary_md.is_file()

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["schema_version"], "egolink.d1_labeling_intake.v0.1")
        self.assertEqual(payload["serves_demo"], "D5")
        self.assertEqual(payload["status"], "pending_human_review")
        self.assertEqual(payload["intake_queue"]["pending_items"], 1)
        self.assertEqual(payload["intake_queue"]["items"][0]["status"], "pending_label_privacy_split")
        self.assertFalse(payload["intake_queue"]["items"][0]["training_allowed"])
        self.assertFalse(payload["intake_queue"]["items"][0]["candidate_record_written"])
        self.assertEqual(payload["review_gates"]["candidate_store"], "not_written")
        self.assertEqual(payload["review_gates"]["model_training"], "not_run")
        self.assertFalse(payload["scope"]["sample_jsonl_read"])
        self.assertFalse(payload["scope"]["candidate_db_written"])
        self.assertFalse(payload["scope"]["exact_coordinates_copied"])
        self.assertTrue(summary_json_exists)
        self.assertTrue(summary_md_exists)
        self.assertNotIn("31.123456", output_text)
        self.assertNotIn("121.654321", output_text)
        self.assertNotIn("raw_payload", output_text)
        self.assertNotIn("d1_field_samples.jsonl", output_text)
        self.assertNotIn('"features"', output_text)
        self.assertNotIn('"target"', output_text)
        self.assertNotIn("C:/private", output_text)

    def test_not_ready_readiness_report_does_not_enter_intake_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readiness_path = root / "d1_training_readiness" / "run" / "d1_training_readiness.json"
            self.write_readiness_report(readiness_path, status="needs_capture", ready=False)

            exit_code, payload, stdout_text = self.run_builder(
                [
                    "--training-readiness-report",
                    str(readiness_path),
                    "--run-id",
                    "unit-d1-labeling-intake-not-ready",
                    "--output-root",
                    str(root / "out"),
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "not_ready_for_labeling_intake")
        self.assertEqual(payload["intake_queue"]["pending_items"], 0)
        self.assertFalse(payload["intake_queue"]["available"])
        self.assertEqual(payload["review_gates"]["training_readiness"], "blocked")
        self.assertNotIn("31.123456", stdout_text)


if __name__ == "__main__":
    unittest.main()

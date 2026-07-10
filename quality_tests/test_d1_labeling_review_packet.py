from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from scripts import build_d1_labeling_review_packet


class D1LabelingReviewPacketTests(unittest.TestCase):
    def run_builder(self, args: list[str]) -> tuple[int, dict[str, object], str]:
        with redirect_stdout(StringIO()) as output:
            exit_code = build_d1_labeling_review_packet.main(args + ["--json"])
        text = output.getvalue()
        return exit_code, json.loads(text), text

    def write_queue_report(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "tool": "summarize_d1_labeling_queue",
            "schema_version": "egolink.d1_labeling_queue.v0.1",
            "run_id": "unit-labeling-queue",
            "generated_at": "2026-07-06T12:05:00+00:00",
            "serves_demo": "D5",
            "status": "pending_human_review",
            "summary": {
                "intake_report_count": 1,
                "pending_item_count": 1,
                "not_ready_report_count": 0,
                "training_allowed_count": 0,
                "candidate_record_written_count": 0,
            },
            "queue": {
                "next_queue": "training_candidate_store_after_review",
                "items": [
                    {
                        "intake_id": "d1-intake-unit-private",
                        "intake_run_id": "unit-intake",
                        "source_run_id": "field-run-private-coord",
                        "readiness_run_id": "field-run-training-readiness",
                        "device_id": "ego-link-r1-connectivity-001",
                        "status": "pending_label_privacy_split",
                        "review_state": {
                            "operator_label": "missing",
                            "privacy_review": "required",
                            "training_consent": "not_reviewed",
                            "split_plan": "missing",
                            "quality_gaps": ["gnss_fix_not_seen"],
                        },
                        "evidence_summary": {
                            "samples": 5,
                            "latest_seq": 52,
                            "raw_post_success_delta": 2,
                            "raw_post_failure_delta": 0,
                            "coordinate_sample_count": 5,
                            "gnss_fix_seen": False,
                            "imu_evidence_statuses": ["mock"],
                            "power_evidence_statuses": ["measured"],
                            "lat": 31.123456,
                            "lon": 121.654321,
                            "private_coordinates": [31.123456, 121.654321],
                        },
                        "requested_actions": ["attach_operator_or_user_label"],
                        "available_decisions": ["needs_more_capture", "reject_for_training"],
                        "training_allowed": True,
                        "candidate_record_written": True,
                        "raw_payload": {"secret": True},
                    }
                ],
            },
            "intake_reports": [
                {
                    "run_id": "unit-intake",
                    "status": "pending_human_review",
                    "report_path": "C:/private/d1_labeling_intake.json",
                }
            ],
            "scope": {
                "sample_jsonl_read": False,
                "candidate_db_written": False,
                "exact_coordinates_copied": False,
            },
            "paths": {
                "private_candidate_db": "C:/private/training_candidates.db",
                "sample_jsonl": "C:/private/d1_field_samples.jsonl",
            },
            "raw_payload": {"private": True},
            "features": {"private": "do-not-expose"},
            "target": {"private": "do-not-expose"},
        }
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def test_review_packet_lists_decision_slots_without_private_details(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            queue_path = root / "queue" / "d1_labeling_queue.json"
            output_root = root / "reviews"
            self.write_queue_report(queue_path)

            exit_code, payload, stdout_text = self.run_builder(
                [
                    "--labeling-queue-report",
                    str(queue_path),
                    "--labeling-queue-root",
                    str(root / "queue"),
                    "--run-id",
                    "unit-review-packet",
                    "--generated-at",
                    "2026-07-06T12:10:00+00:00",
                    "--output-root",
                    str(output_root),
                ]
            )
            run_dir = output_root / "unit-review-packet"
            summary_json = run_dir / "d1_labeling_review_packet.json"
            summary_md = run_dir / "d1_labeling_review_packet.md"
            output_text = stdout_text + summary_json.read_text(encoding="utf-8") + summary_md.read_text(encoding="utf-8")

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["schema_version"], "egolink.d1_labeling_review_packet.v0.1")
        self.assertEqual(payload["serves_demo"], "D5")
        self.assertEqual(payload["status"], "needs_human_review")
        self.assertEqual(payload["summary"]["queue_pending_items"], 1)
        self.assertEqual(payload["summary"]["review_packet_items"], 1)
        self.assertEqual(payload["summary"]["needs_operator_label"], 1)
        self.assertEqual(payload["summary"]["candidate_record_written_count"], 0)
        self.assertEqual(payload["summary"]["training_allowed_count"], 0)
        item = payload["review_packet"]["items"][0]
        self.assertEqual(item["intake_id"], "d1-intake-unit-private")
        self.assertEqual(item["decision_slots"]["operator_label"]["current"], "missing")
        self.assertIn("safe", item["decision_slots"]["operator_label"]["allowed_values"])
        self.assertIn("approved_bounded_summary_only", item["decision_slots"]["privacy_review"]["allowed_values"])
        self.assertFalse(item["candidate_record_written"])
        self.assertFalse(item["training_allowed"])
        self.assertFalse(payload["scope"]["sample_jsonl_read"])
        self.assertFalse(payload["scope"]["candidate_db_written"])
        self.assertFalse(payload["scope"]["exact_coordinates_copied"])
        self.assertNotIn("31.123456", output_text)
        self.assertNotIn("121.654321", output_text)
        self.assertNotIn("raw_payload", output_text)
        self.assertNotIn("d1_field_samples.jsonl", output_text)
        self.assertNotIn('"features"', output_text)
        self.assertNotIn('"target"', output_text)
        self.assertNotIn("C:/private", output_text)

    def test_missing_queue_writes_explainable_empty_packet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exit_code, payload, stdout_text = self.run_builder(
                [
                    "--labeling-queue-root",
                    str(root / "missing"),
                    "--run-id",
                    "unit-missing-review-packet",
                    "--output-root",
                    str(root / "reviews"),
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "no_labeling_queue")
        self.assertEqual(payload["summary"]["review_packet_items"], 0)
        self.assertFalse(payload["scope"]["sample_jsonl_read"])
        self.assertNotIn("d1_field_samples.jsonl", stdout_text)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from scripts import build_d1_labeling_decision_template


class D1LabelingDecisionTemplateTests(unittest.TestCase):
    def run_builder(self, args: list[str]) -> tuple[int, dict[str, object], str]:
        with redirect_stdout(StringIO()) as output:
            exit_code = build_d1_labeling_decision_template.main(args + ["--json"])
        text = output.getvalue()
        return exit_code, json.loads(text), text

    def write_review_packet(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "tool": "build_d1_labeling_review_packet",
            "schema_version": "egolink.d1_labeling_review_packet.v0.1",
            "run_id": "unit-review-packet",
            "generated_at": "2026-07-06T12:10:00+00:00",
            "serves_demo": "D5",
            "status": "needs_human_review",
            "summary": {
                "queue_pending_items": 1,
                "review_packet_items": 1,
                "needs_operator_label": 1,
                "needs_privacy_review": 1,
                "needs_training_consent": 1,
                "needs_split_plan": 1,
                "candidate_record_written_count": 0,
                "training_allowed_count": 0,
            },
            "review_packet": {
                "status": "open",
                "items": [
                    {
                        "packet_item_id": "d1-review-unit",
                        "intake_id": "d1-intake-unit-private",
                        "source_run_id": "field-run-private-coord",
                        "readiness_run_id": "field-run-training-readiness",
                        "device_id": "ego-link-r1-connectivity-001",
                        "queue_status": "pending_label_privacy_split",
                        "current_review_state": {
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
                        "decision_slots": {
                            "operator_label": {
                                "required": True,
                                "current": "missing",
                                "selected": None,
                                "allowed_values": ["safe", "needs_help"],
                                "reviewed_by": "private-operator",
                            },
                            "privacy_review": {
                                "required": True,
                                "current": "required",
                                "selected": None,
                                "allowed_values": ["approved_bounded_summary_only"],
                                "reviewed_at": "private-time",
                            },
                            "candidate_decision": {
                                "required": True,
                                "current": "not_reviewed",
                                "selected": None,
                                "allowed_values": ["ready_for_candidate_store", "reject_for_training"],
                            },
                        },
                        "requested_actions": ["attach_operator_or_user_label"],
                        "available_decisions": ["needs_more_capture", "reject_for_training"],
                        "training_allowed": True,
                        "candidate_record_written": True,
                        "raw_payload": {"secret": True},
                    }
                ],
                "decision_schema": {
                    "operator_label": ["safe", "needs_help", "no_response", "uncertain"],
                    "privacy_review": ["approved_bounded_summary_only", "reject_private_data_risk"],
                    "training_consent": ["approved_for_training", "not_approved_for_training"],
                    "split_plan": ["train", "validation", "test", "holdout", "exclude"],
                    "candidate_decision": ["ready_for_candidate_store", "needs_more_capture", "reject_for_training"],
                },
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

    def test_decision_template_lists_fillable_fields_without_private_details(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review_path = root / "review" / "d1_labeling_review_packet.json"
            output_root = root / "decisions"
            self.write_review_packet(review_path)

            exit_code, payload, stdout_text = self.run_builder(
                [
                    "--review-packet-report",
                    str(review_path),
                    "--review-packet-root",
                    str(root / "review"),
                    "--run-id",
                    "unit-decision-template",
                    "--generated-at",
                    "2026-07-06T12:20:00+00:00",
                    "--output-root",
                    str(output_root),
                ]
            )
            run_dir = output_root / "unit-decision-template"
            summary_json = run_dir / "d1_labeling_decision_template.json"
            summary_md = run_dir / "d1_labeling_decision_template.md"
            output_text = stdout_text + summary_json.read_text(encoding="utf-8") + summary_md.read_text(encoding="utf-8")

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["schema_version"], "egolink.d1_labeling_decision_template.v0.1")
        self.assertEqual(payload["serves_demo"], "D5")
        self.assertEqual(payload["status"], "ready_for_human_input")
        self.assertEqual(payload["summary"]["template_items"], 1)
        self.assertEqual(payload["summary"]["required_decision_fields"], 5)
        self.assertEqual(payload["summary"]["selected_decision_fields"], 0)
        self.assertFalse(payload["summary"]["ready_for_candidate_promotion"])
        item = payload["decision_template"]["items"][0]
        self.assertEqual(item["packet_item_id"], "d1-review-unit")
        self.assertIn("safe", item["decision_fields"]["operator_label"]["allowed_values"])
        self.assertIn("approved_bounded_summary_only", item["decision_fields"]["privacy_review"]["allowed_values"])
        self.assertIsNone(item["decision_fields"]["operator_label"]["selected"])
        self.assertFalse(item["candidate_record_written"])
        self.assertFalse(item["training_allowed"])
        self.assertFalse(payload["scope"]["sample_jsonl_read"])
        self.assertFalse(payload["scope"]["candidate_db_written"])
        self.assertFalse(payload["scope"]["exact_coordinates_copied"])
        self.assertIn("TODO", output_text)
        self.assertNotIn("31.123456", output_text)
        self.assertNotIn("121.654321", output_text)
        self.assertNotIn("raw_payload", output_text)
        self.assertNotIn("private-operator", output_text)
        self.assertNotIn("private-time", output_text)
        self.assertNotIn("d1_field_samples.jsonl", output_text)
        self.assertNotIn('"features"', output_text)
        self.assertNotIn('"target"', output_text)
        self.assertNotIn("C:/private", output_text)

    def test_missing_review_packet_writes_explainable_empty_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exit_code, payload, stdout_text = self.run_builder(
                [
                    "--review-packet-root",
                    str(root / "missing"),
                    "--run-id",
                    "unit-missing-decision-template",
                    "--output-root",
                    str(root / "decisions"),
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "no_labeling_review_packet")
        self.assertEqual(payload["summary"]["template_items"], 0)
        self.assertFalse(payload["scope"]["sample_jsonl_read"])
        self.assertNotIn("d1_field_samples.jsonl", stdout_text)


if __name__ == "__main__":
    unittest.main()

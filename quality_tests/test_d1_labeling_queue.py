from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from scripts import summarize_d1_labeling_queue


class D1LabelingQueueTests(unittest.TestCase):
    def run_builder(self, args: list[str]) -> tuple[int, dict[str, object], str]:
        with redirect_stdout(StringIO()) as output:
            exit_code = summarize_d1_labeling_queue.main(args + ["--json"])
        text = output.getvalue()
        return exit_code, json.loads(text), text

    def write_intake_report(self, path: Path, *, status: str, pending_items: int) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        items = []
        if pending_items:
            items.append(
                {
                    "intake_id": "d1-intake-unit-private",
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
                    },
                    "requested_actions": [
                        "attach_operator_or_user_label",
                        "complete_privacy_review",
                    ],
                    "available_decisions": ["needs_more_capture", "reject_for_training"],
                    "training_allowed": True,
                    "candidate_record_written": True,
                }
            )
        payload = {
            "tool": "build_d1_labeling_intake",
            "schema_version": "egolink.d1_labeling_intake.v0.1",
            "run_id": path.parent.name,
            "generated_at": "2026-07-06T12:00:00+00:00",
            "status": status,
            "reason": "unit",
            "source_readiness": {
                "run_id": "field-run-training-readiness",
                "status": "ready_for_labeling_review" if pending_items else "needs_capture",
                "report_path": "C:/private/d1_training_readiness.json",
            },
            "source_observation": {
                "run_id": "field-run-private-coord",
                "status": "completed",
                "device_id": "ego-link-r1-connectivity-001",
                "samples_path": "C:/private/d1_field_samples.jsonl",
                "lat": 31.123456,
                "lon": 121.654321,
            },
            "intake_queue": {
                "available": bool(pending_items),
                "pending_items": pending_items,
                "items": items,
                "next_queue": "training_candidate_store_after_review",
            },
            "review_gates": {
                "candidate_store": "not_written",
                "model_training": "not_run",
            },
            "blockers": ["privacy_review_required", "operator_label_missing"],
            "scope": {
                "sample_jsonl_read": False,
                "candidate_db_written": False,
                "exact_coordinates_copied": False,
            },
            "raw_payload": {"lat": 31.123456, "lon": 121.654321},
            "features": {"private": "do-not-copy"},
            "target": {"private": "do-not-copy"},
            "paths": {
                "d1_labeling_intake_json": str(path),
                "d1_labeling_intake_markdown": str(path.with_suffix(".md")),
            },
        }
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        path.with_suffix(".md").write_text("# intake\n", encoding="utf-8")

    def test_queue_summarizes_pending_items_without_private_details(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake_root = root / "d1_labeling_intake"
            output_root = root / "d1_labeling_queue"
            self.write_intake_report(
                intake_root / "ready" / "d1_labeling_intake.json",
                status="pending_human_review",
                pending_items=1,
            )
            self.write_intake_report(
                intake_root / "not-ready" / "d1_labeling_intake.json",
                status="not_ready_for_labeling_intake",
                pending_items=0,
            )

            exit_code, payload, stdout_text = self.run_builder(
                [
                    "--intake-root",
                    str(intake_root),
                    "--run-id",
                    "unit-d1-labeling-queue",
                    "--generated-at",
                    "2026-07-06T12:05:00+00:00",
                    "--output-root",
                    str(output_root),
                ]
            )
            run_dir = output_root / "unit-d1-labeling-queue"
            summary_json = run_dir / "d1_labeling_queue.json"
            summary_md = run_dir / "d1_labeling_queue.md"
            output_text = stdout_text + summary_json.read_text(encoding="utf-8") + summary_md.read_text(encoding="utf-8")
            summary_json_exists = summary_json.is_file()
            summary_md_exists = summary_md.is_file()

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["schema_version"], "egolink.d1_labeling_queue.v0.1")
        self.assertEqual(payload["serves_demo"], "D5")
        self.assertEqual(payload["status"], "pending_human_review")
        self.assertEqual(payload["summary"]["intake_report_count"], 2)
        self.assertEqual(payload["summary"]["pending_item_count"], 1)
        self.assertEqual(payload["summary"]["not_ready_report_count"], 1)
        self.assertEqual(payload["summary"]["training_allowed_count"], 0)
        self.assertEqual(payload["summary"]["candidate_record_written_count"], 0)
        self.assertEqual(payload["queue"]["items"][0]["status"], "pending_label_privacy_split")
        self.assertFalse(payload["queue"]["items"][0]["training_allowed"])
        self.assertFalse(payload["queue"]["items"][0]["candidate_record_written"])
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

    def test_empty_intake_root_writes_no_report_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exit_code, payload, stdout_text = self.run_builder(
                [
                    "--intake-root",
                    str(root / "missing"),
                    "--run-id",
                    "unit-empty-queue",
                    "--output-root",
                    str(root / "out"),
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "no_intake_reports")
        self.assertEqual(payload["summary"]["intake_report_count"], 0)
        self.assertEqual(payload["summary"]["pending_item_count"], 0)
        self.assertNotIn("d1_field_samples.jsonl", stdout_text)


if __name__ == "__main__":
    unittest.main()

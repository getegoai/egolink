from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from scripts import validate_d1_labeling_decision_template


class D1LabelingDecisionValidationTests(unittest.TestCase):
    def run_validator(self, args: list[str]) -> tuple[int, dict[str, object], str]:
        with redirect_stdout(StringIO()) as output:
            exit_code = validate_d1_labeling_decision_template.main(args + ["--json"])
        text = output.getvalue()
        return exit_code, json.loads(text), text

    def write_template(self, path: Path, *, selections: dict[str, str | None]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fields = {
            "operator_label": {
                "required": True,
                "current": "missing",
                "allowed_values": ["safe", "needs_help", "no_response", "uncertain", "not_training_relevant"],
                "selected": selections.get("operator_label"),
                "operator_note": "private-note",
            },
            "privacy_review": {
                "required": True,
                "current": "required",
                "allowed_values": ["approved_bounded_summary_only", "reject_private_data_risk", "needs_redaction_review"],
                "selected": selections.get("privacy_review"),
                "operator_note": "private-privacy-note",
            },
            "training_consent": {
                "required": True,
                "current": "not_reviewed",
                "allowed_values": ["approved_for_training", "not_approved_for_training", "defer"],
                "selected": selections.get("training_consent"),
            },
            "split_plan": {
                "required": True,
                "current": "missing",
                "allowed_values": ["train", "validation", "test", "holdout", "exclude"],
                "selected": selections.get("split_plan"),
            },
            "candidate_decision": {
                "required": True,
                "current": "not_reviewed",
                "allowed_values": ["ready_for_candidate_store", "needs_more_capture", "reject_for_training"],
                "selected": selections.get("candidate_decision"),
            },
        }
        payload = {
            "tool": "build_d1_labeling_decision_template",
            "schema_version": "egolink.d1_labeling_decision_template.v0.1",
            "run_id": "unit-decision-template",
            "generated_at": "2026-07-06T12:20:00+00:00",
            "serves_demo": "D5",
            "status": "ready_for_human_input",
            "summary": {
                "template_items": 1,
                "required_decision_fields": 5,
                "selected_decision_fields": len([value for value in selections.values() if value]),
                "candidate_record_written_count": 0,
                "training_allowed_count": 0,
            },
            "decision_template": {
                "status": "open",
                "items": [
                    {
                        "packet_item_id": "d1-review-unit",
                        "intake_id": "d1-intake-unit-private",
                        "source_run_id": "field-run-private-coord",
                        "readiness_run_id": "field-run-training-readiness",
                        "device_id": "ego-link-r1-connectivity-001",
                        "evidence_summary": {
                            "samples": 5,
                            "latest_seq": 52,
                            "coordinate_sample_count": 5,
                            "lat": 31.123456,
                            "lon": 121.654321,
                            "private_coordinates": [31.123456, 121.654321],
                        },
                        "decision_fields": fields,
                        "operator_note": "private-note",
                        "candidate_record_written": True,
                        "training_allowed": True,
                        "raw_payload": {"secret": True},
                    }
                ],
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

    def test_unfilled_template_needs_decisions_without_private_details(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            template_path = root / "decisions" / "d1_labeling_decision_template.json"
            output_root = root / "validations"
            self.write_template(
                template_path,
                selections={
                    "operator_label": None,
                    "privacy_review": None,
                    "training_consent": None,
                    "split_plan": None,
                    "candidate_decision": None,
                },
            )

            exit_code, payload, stdout_text = self.run_validator(
                [
                    "--decision-template-report",
                    str(template_path),
                    "--decision-template-root",
                    str(root / "decisions"),
                    "--run-id",
                    "unit-decision-validation",
                    "--generated-at",
                    "2026-07-06T12:30:00+00:00",
                    "--output-root",
                    str(output_root),
                ]
            )
            run_dir = output_root / "unit-decision-validation"
            summary_json = run_dir / "d1_labeling_decision_validation.json"
            summary_md = run_dir / "d1_labeling_decision_validation.md"
            output_text = stdout_text + summary_json.read_text(encoding="utf-8") + summary_md.read_text(encoding="utf-8")

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["schema_version"], "egolink.d1_labeling_decision_validation.v0.1")
        self.assertEqual(payload["serves_demo"], "D5")
        self.assertEqual(payload["status"], "needs_decisions")
        self.assertEqual(payload["summary"]["missing_decision_fields"], 5)
        self.assertEqual(payload["summary"]["candidate_promotion_ready_items"], 0)
        self.assertFalse(payload["summary"]["ready_for_candidate_promotion"])
        item = payload["validation"]["items"][0]
        self.assertEqual(item["decision_status"], "needs_decisions")
        self.assertEqual(item["missing_fields"], list(validate_d1_labeling_decision_template.REQUIRED_FIELDS))
        self.assertFalse(item["candidate_record_written"])
        self.assertFalse(item["training_allowed"])
        self.assertFalse(payload["scope"]["sample_jsonl_read"])
        self.assertFalse(payload["scope"]["candidate_db_written"])
        self.assertFalse(payload["scope"]["model_training_started"])
        self.assertNotIn("31.123456", output_text)
        self.assertNotIn("121.654321", output_text)
        self.assertNotIn("raw_payload", output_text)
        self.assertNotIn("private-note", output_text)
        self.assertNotIn("d1_field_samples.jsonl", output_text)
        self.assertNotIn('"features"', output_text)
        self.assertNotIn('"target"', output_text)
        self.assertNotIn("C:/private", output_text)

    def test_complete_approved_template_is_ready_without_writing_candidate_db(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            template_path = root / "decisions" / "d1_labeling_decision_template.json"
            self.write_template(
                template_path,
                selections={
                    "operator_label": "safe",
                    "privacy_review": "approved_bounded_summary_only",
                    "training_consent": "approved_for_training",
                    "split_plan": "train",
                    "candidate_decision": "ready_for_candidate_store",
                },
            )

            exit_code, payload, stdout_text = self.run_validator(
                [
                    "--decision-template-report",
                    str(template_path),
                    "--decision-template-root",
                    str(root / "decisions"),
                    "--run-id",
                    "unit-ready-validation",
                    "--output-root",
                    str(root / "validations"),
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "ready_for_candidate_promotion")
        self.assertEqual(payload["summary"]["selected_decision_fields"], 5)
        self.assertEqual(payload["summary"]["missing_decision_fields"], 0)
        self.assertEqual(payload["summary"]["invalid_decision_fields"], 0)
        self.assertEqual(payload["summary"]["candidate_promotion_ready_items"], 1)
        self.assertTrue(payload["summary"]["ready_for_candidate_promotion"])
        self.assertEqual(payload["summary"]["candidate_record_written_count"], 0)
        self.assertEqual(payload["summary"]["training_allowed_count"], 0)
        item = payload["validation"]["items"][0]
        self.assertEqual(item["decision_status"], "ready_for_candidate_promotion")
        self.assertTrue(item["ready_for_candidate_promotion"])
        self.assertFalse(item["candidate_record_written"])
        self.assertFalse(item["training_allowed"])
        self.assertFalse(payload["scope"]["candidate_db_written"])
        self.assertNotIn("C:/private", stdout_text)

    def test_invalid_selected_value_blocks_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            template_path = root / "decisions" / "d1_labeling_decision_template.json"
            self.write_template(
                template_path,
                selections={
                    "operator_label": "safe",
                    "privacy_review": "approved_bounded_summary_only",
                    "training_consent": "approved_for_training",
                    "split_plan": "train",
                    "candidate_decision": "ship_it",
                },
            )

            exit_code, payload, _stdout_text = self.run_validator(
                [
                    "--decision-template-report",
                    str(template_path),
                    "--decision-template-root",
                    str(root / "decisions"),
                    "--run-id",
                    "unit-invalid-validation",
                    "--output-root",
                    str(root / "validations"),
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "invalid_decisions")
        self.assertEqual(payload["summary"]["invalid_decision_fields"], 1)
        self.assertEqual(payload["validation"]["items"][0]["invalid_fields"][0]["field"], "candidate_decision")
        self.assertFalse(payload["summary"]["ready_for_candidate_promotion"])

    def test_missing_template_writes_explainable_empty_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exit_code, payload, stdout_text = self.run_validator(
                [
                    "--decision-template-root",
                    str(root / "missing"),
                    "--run-id",
                    "unit-missing-decision-validation",
                    "--output-root",
                    str(root / "validations"),
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "no_decision_template")
        self.assertEqual(payload["summary"]["validation_items"], 0)
        self.assertFalse(payload["scope"]["sample_jsonl_read"])
        self.assertNotIn("d1_field_samples.jsonl", stdout_text)


if __name__ == "__main__":
    unittest.main()

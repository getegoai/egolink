from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from pc_simulator import session_annotations, session_recorder, training_candidate_store
from scripts import build_training_candidate_store, summarize_data_flywheel
from quality_tests.test_session_recorder import sample_events


class TrainingCandidateStoreTests(unittest.TestCase):
    def write_recording(self, recording_dir: Path) -> None:
        recording = session_recorder.build_recording(
            sample_events(),
            event_log=Path("events.jsonl"),
            session_id="candidate-session",
            created_at="2026-07-04T12:00:00+00:00",
        )
        session_recorder.write_recording(recording, recording_dir)

    def add_annotation(self, recording_dir: Path, *, training_allowed: bool = True) -> None:
        target = next(
            item
            for item in session_annotations.annotation_targets(recording_dir)
            if item.get("event_type") == "sos_pressed"
        )
        session_annotations.annotate_recording(
            recording_dir,
            source_event_key=target["source_event_key"],
            label="needs_help",
            annotator_type="human",
            annotation_id="ann-candidate-needs-help",
            created_at="2026-07-04T12:01:00+00:00",
            training_allowed=training_allowed,
        )

    def read_records(self, db_path: Path) -> list[dict[str, object]]:
        db = sqlite3.connect(db_path)
        try:
            rows = db.execute(
                "SELECT record_json FROM training_candidate_records ORDER BY record_id"
            ).fetchall()
        finally:
            db.close()
        return [json.loads(row[0]) for row in rows]

    def test_store_recording_writes_bounded_candidate_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recording_dir = root / "recording"
            db_path = root / "candidates.db"
            self.write_recording(recording_dir)
            self.add_annotation(recording_dir, training_allowed=True)

            summary = training_candidate_store.store_recording(recording_dir, db_path)
            records = self.read_records(db_path)

        self.assertTrue(summary["ok"])
        self.assertEqual(summary["records_written"], 1)
        self.assertEqual(summary["training_allowed_records"], 0)
        record = records[0]
        self.assertEqual(record["schema_version"], "egolink.training_candidate_record.v0.1")
        self.assertEqual(record["state"], "candidate")
        self.assertFalse(record["training_allowed"])
        self.assertTrue(record["review_required"])
        self.assertEqual(record["consent"]["consent_status"], "training_requested_pending_review")
        self.assertFalse(record["consent"]["training_allowed"])
        self.assertEqual(record["labels"]["label_set"]["label"], "needs_help")
        self.assertEqual(record["privacy"]["coordinate_redaction"], "raw_coordinates_not_copied")
        self.assertFalse(record["evidence"]["payload_bytes_retained"])
        self.assertEqual(record["split"]["split_strategy"], "session_blocked")
        self.assertIn("source_manifest_hash", record["lineage"])
        self.assertIn("raw_dashboard_payload", record["quality"]["excluded_evidence"])
        self.assertNotIn("raw_payload", json.dumps(record))

    def test_recording_without_annotations_creates_session_but_no_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recording_dir = root / "recording"
            db_path = root / "candidates.db"
            self.write_recording(recording_dir)

            summary = training_candidate_store.store_recording(recording_dir, db_path)
            records = self.read_records(db_path)

        self.assertEqual(summary["records_written"], 0)
        self.assertEqual(records, [])
        self.assertEqual(summary["warnings"], ["no_annotations_no_candidate_records"])

    def test_failed_quality_gate_blocks_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recording_dir = root / "recording"
            db_path = root / "candidates.db"
            self.write_recording(recording_dir)
            self.add_annotation(recording_dir, training_allowed=True)
            manifest_path = recording_dir / "session_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["record_counts"]["events"] = 999
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

            summary = training_candidate_store.store_recording(recording_dir, db_path)
            records = self.read_records(db_path)

        self.assertEqual(summary["quality_gate"], "fail")
        self.assertEqual(records[0]["state"], "quality_blocked")
        self.assertFalse(records[0]["training_allowed"])
        self.assertIn("record_count_mismatch", records[0]["quality"]["blockers"])

    def test_cli_builds_store_from_recording(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recording_dir = root / "recording"
            db_path = root / "cli.db"
            self.write_recording(recording_dir)
            self.add_annotation(recording_dir)

            with redirect_stdout(StringIO()) as output:
                exit_code = build_training_candidate_store.main(
                    [
                        "--recording-dir",
                        str(recording_dir),
                        "--db",
                        str(db_path),
                        "--json",
                    ]
                )
            payload = json.loads(output.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["records_written"], 1)
        self.assertEqual(payload["training_allowed_records"], 0)

    def test_data_flywheel_status_summarizes_candidate_store_without_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recording_dir = root / "recording"
            db_path = root / "candidates.db"
            report_dir = root / "status"
            self.write_recording(recording_dir)
            self.add_annotation(recording_dir)
            training_candidate_store.store_recording(
                recording_dir,
                db_path,
                generated_at="2026-07-04T12:02:00+00:00",
            )

            summary = training_candidate_store.summarize_candidate_store(
                db_path,
                generated_at="2026-07-04T12:03:00+00:00",
            )
            written = training_candidate_store.write_data_flywheel_status_report(summary, report_dir)
            json_exists = (report_dir / "data_flywheel_status.json").exists()
            markdown_exists = (report_dir / "data_flywheel_status.md").exists()

        self.assertEqual(summary["schema_version"], "egolink.data_flywheel_status.v0.1")
        self.assertEqual(summary["status"], "needs_review")
        self.assertEqual(summary["counts"]["sessions_total"], 1)
        self.assertEqual(summary["counts"]["records_total"], 1)
        self.assertEqual(summary["counts"]["training_allowed_records"], 0)
        self.assertEqual(summary["review"]["label_review_pending_records"], 1)
        self.assertEqual(summary["review"]["split_leakage_unchecked_records"], 1)
        self.assertFalse(summary["readiness"]["model_training_ready"])
        self.assertIn("label_review_pending", summary["blockers"])
        self.assertIn("split_leakage_review_pending", summary["blockers"])
        payload = json.dumps(written, ensure_ascii=False)
        self.assertNotIn("record_json", payload)
        self.assertNotIn("raw_payload", payload)
        self.assertTrue(json_exists)
        self.assertTrue(markdown_exists)

    def test_data_flywheel_cli_writes_status_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recording_dir = root / "recording"
            db_path = root / "candidates.db"
            output_root = root / "reports"
            self.write_recording(recording_dir)
            self.add_annotation(recording_dir)
            training_candidate_store.store_recording(recording_dir, db_path)

            with redirect_stdout(StringIO()) as output:
                exit_code = summarize_data_flywheel.main(
                    [
                        "--db",
                        str(db_path),
                        "--output-root",
                        str(output_root),
                        "--run-id",
                        "unit-data-flywheel",
                        "--generated-at",
                        "2026-07-04T12:04:00+00:00",
                        "--json",
                    ]
                )
            payload = json.loads(output.getvalue())
            report_exists = (output_root / "unit-data-flywheel" / "data_flywheel_status.json").exists()

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["run_id"], "unit-data-flywheel")
        self.assertEqual(payload["counts"]["records_total"], 1)
        self.assertFalse(payload["readiness"]["model_training_ready"])
        self.assertTrue(report_exists)


if __name__ == "__main__":
    unittest.main()

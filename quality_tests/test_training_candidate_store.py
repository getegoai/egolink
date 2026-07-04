from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from pc_simulator import session_annotations, session_recorder, training_candidate_store
from scripts import (
    build_training_candidate_store,
    export_training_dataset_manifest,
    review_training_candidates,
    run_data_flywheel_pipeline,
    summarize_data_flywheel,
)
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
        self.assertEqual(summary["review_queue"]["pending_records"], 1)
        self.assertEqual(summary["review_queue"]["sample_records"][0]["label"], "needs_help")
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

    def test_candidate_review_queue_is_bounded_without_raw_records_or_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recording_dir = root / "recording"
            db_path = root / "candidates.db"
            self.write_recording(recording_dir)
            self.add_annotation(recording_dir)
            training_candidate_store.store_recording(recording_dir, db_path)

            queue = training_candidate_store.candidate_review_queue(db_path, limit=5)

        self.assertTrue(queue["available"])
        self.assertEqual(queue["pending_records"], 1)
        self.assertEqual(queue["records"][0]["label"], "needs_help")
        payload = json.dumps(queue, ensure_ascii=False)
        self.assertNotIn("record_json", payload)
        self.assertNotIn("raw_payload", payload)
        self.assertNotIn("recording_path", payload)
        self.assertNotIn(str(recording_dir), payload)

    def test_review_approval_requires_all_training_gates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recording_dir = root / "recording"
            db_path = root / "candidates.db"
            self.write_recording(recording_dir)
            self.add_annotation(recording_dir)
            training_candidate_store.store_recording(recording_dir, db_path)
            record_id = self.read_records(db_path)[0]["record_id"]

            with self.assertRaises(training_candidate_store.CandidateStoreError) as raised:
                training_candidate_store.review_candidate_record(
                    db_path,
                    record_id=record_id,
                    decision="approve_for_training",
                    reviewer="unit",
                    split_name="train",
                    privacy_reviewed=True,
                    quality_reviewed=True,
                )

        self.assertIn("split_leakage_not_checked", str(raised.exception))

    def test_review_approval_promotes_candidate_and_status_becomes_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recording_dir = root / "recording"
            db_path = root / "candidates.db"
            self.write_recording(recording_dir)
            self.add_annotation(recording_dir)
            training_candidate_store.store_recording(
                recording_dir,
                db_path,
                generated_at="2026-07-04T12:02:00+00:00",
            )
            record_id = self.read_records(db_path)[0]["record_id"]

            review = training_candidate_store.review_candidate_record(
                db_path,
                record_id=record_id,
                decision="approve_for_training",
                reviewer="unit",
                split_name="train",
                split_leakage_checked=True,
                privacy_reviewed=True,
                quality_reviewed=True,
                reviewed_at="2026-07-04T12:05:00+00:00",
                notes="unit approval",
            )
            records = self.read_records(db_path)
            summary = training_candidate_store.summarize_candidate_store(
                db_path,
                generated_at="2026-07-04T12:06:00+00:00",
            )

        self.assertTrue(review["ok"])
        self.assertEqual(review["record"]["state"], "reviewed_training_candidate")
        self.assertTrue(review["record"]["training_allowed"])
        self.assertEqual(records[0]["state"], "reviewed_training_candidate")
        self.assertTrue(records[0]["training_allowed"])
        self.assertFalse(records[0]["review_required"])
        self.assertEqual(records[0]["split"]["split_name"], "train")
        self.assertTrue(records[0]["split"]["split_leakage_checked"])
        self.assertEqual(summary["status"], "ready_for_experiment")
        self.assertTrue(summary["readiness"]["model_training_ready"])
        self.assertEqual(summary["review_queue"]["pending_records"], 0)

    def test_review_reject_does_not_enable_training(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recording_dir = root / "recording"
            db_path = root / "candidates.db"
            self.write_recording(recording_dir)
            self.add_annotation(recording_dir)
            training_candidate_store.store_recording(recording_dir, db_path)
            record_id = self.read_records(db_path)[0]["record_id"]

            review = training_candidate_store.review_candidate_record(
                db_path,
                record_id=record_id,
                decision="reject",
                reviewer="unit",
                reviewed_at="2026-07-04T12:07:00+00:00",
            )
            records = self.read_records(db_path)
            summary = training_candidate_store.summarize_candidate_store(db_path)

        self.assertEqual(review["record"]["state"], "review_rejected")
        self.assertFalse(review["record"]["training_allowed"])
        self.assertFalse(records[0]["training_allowed"])
        self.assertEqual(summary["review_queue"]["pending_records"], 0)
        self.assertEqual(summary["review"]["split_leakage_unchecked_records"], 0)

    def test_review_cli_lists_and_approves_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recording_dir = root / "recording"
            db_path = root / "candidates.db"
            self.write_recording(recording_dir)
            self.add_annotation(recording_dir)
            training_candidate_store.store_recording(recording_dir, db_path)
            record_id = self.read_records(db_path)[0]["record_id"]

            with redirect_stdout(StringIO()) as queue_output:
                list_exit = review_training_candidates.main(
                    ["--db", str(db_path), "--json"]
                )
            queue_payload = json.loads(queue_output.getvalue())
            with redirect_stdout(StringIO()) as review_output:
                review_exit = review_training_candidates.main(
                    [
                        "--db",
                        str(db_path),
                        "--record-id",
                        record_id,
                        "--decision",
                        "approve_for_training",
                        "--reviewer",
                        "unit",
                        "--split-name",
                        "train",
                        "--split-leakage-checked",
                        "--privacy-reviewed",
                        "--quality-reviewed",
                        "--reviewed-at",
                        "2026-07-04T12:08:00+00:00",
                        "--json",
                    ]
                )
            review_payload = json.loads(review_output.getvalue())

        self.assertEqual(list_exit, 0)
        self.assertEqual(queue_payload["pending_records"], 1)
        self.assertEqual(review_exit, 0)
        self.assertEqual(review_payload["record"]["state"], "reviewed_training_candidate")
        self.assertTrue(review_payload["record"]["training_allowed"])

    def test_dataset_manifest_reports_not_ready_without_reviewed_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recording_dir = root / "recording"
            db_path = root / "candidates.db"
            output_dir = root / "dataset"
            self.write_recording(recording_dir)
            self.add_annotation(recording_dir)
            training_candidate_store.store_recording(recording_dir, db_path)

            manifest = training_candidate_store.build_training_dataset_manifest(
                db_path,
                dataset_id="dataset-unit-empty",
                generated_at="2026-07-04T12:09:00+00:00",
            )
            written = training_candidate_store.write_training_dataset_manifest(manifest, output_dir)
            json_exists = (output_dir / "training_dataset_manifest.json").exists()
            markdown_exists = (output_dir / "training_dataset_manifest.md").exists()

        self.assertEqual(manifest["status"], "not_ready")
        self.assertEqual(manifest["reason"], "no_reviewed_training_candidates")
        self.assertEqual(manifest["counts"]["eligible_records"], 0)
        self.assertEqual(manifest["records"], [])
        payload = json.dumps(written, ensure_ascii=False)
        self.assertNotIn("record_json", payload)
        self.assertNotIn("raw_payload", payload)
        self.assertNotIn(str(recording_dir), payload)
        self.assertTrue(json_exists)
        self.assertTrue(markdown_exists)

    def test_dataset_manifest_exports_only_reviewed_training_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recording_dir = root / "recording"
            db_path = root / "candidates.db"
            self.write_recording(recording_dir)
            self.add_annotation(recording_dir)
            training_candidate_store.store_recording(recording_dir, db_path)
            record_id = self.read_records(db_path)[0]["record_id"]
            training_candidate_store.review_candidate_record(
                db_path,
                record_id=record_id,
                decision="approve_for_training",
                reviewer="unit",
                split_name="train",
                split_leakage_checked=True,
                privacy_reviewed=True,
                quality_reviewed=True,
                reviewed_at="2026-07-04T12:10:00+00:00",
            )

            manifest = training_candidate_store.build_training_dataset_manifest(
                db_path,
                dataset_id="dataset-unit-ready",
                generated_at="2026-07-04T12:11:00+00:00",
            )

        self.assertEqual(manifest["status"], "ready_for_training_handoff")
        self.assertEqual(manifest["reason"], "reviewed_candidates_available")
        self.assertEqual(manifest["counts"]["eligible_records"], 1)
        self.assertEqual(manifest["split_counts"], {"train": 1})
        record = manifest["records"][0]
        self.assertEqual(record["record_id"], record_id)
        self.assertEqual(record["label"], "needs_help")
        self.assertEqual(record["split_name"], "train")
        self.assertEqual(record["label_review_state"], "reviewed")
        self.assertIn("source_manifest_hash", record)
        payload = json.dumps(manifest, ensure_ascii=False)
        self.assertNotIn("record_json", payload)
        self.assertNotIn("raw_payload", payload)
        self.assertNotIn("recording_path", payload)

    def test_dataset_manifest_cli_writes_ready_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recording_dir = root / "recording"
            db_path = root / "candidates.db"
            output_root = root / "manifests"
            self.write_recording(recording_dir)
            self.add_annotation(recording_dir)
            training_candidate_store.store_recording(recording_dir, db_path)
            record_id = self.read_records(db_path)[0]["record_id"]
            training_candidate_store.review_candidate_record(
                db_path,
                record_id=record_id,
                decision="approve_for_training",
                reviewer="unit",
                split_name="train",
                split_leakage_checked=True,
                privacy_reviewed=True,
                quality_reviewed=True,
                reviewed_at="2026-07-04T12:12:00+00:00",
            )

            with redirect_stdout(StringIO()) as output:
                exit_code = export_training_dataset_manifest.main(
                    [
                        "--db",
                        str(db_path),
                        "--output-root",
                        str(output_root),
                        "--dataset-id",
                        "dataset-cli-ready",
                        "--generated-at",
                        "2026-07-04T12:13:00+00:00",
                        "--require-ready",
                        "--json",
                    ]
                )
            payload = json.loads(output.getvalue())
            manifest_exists = (output_root / "dataset-cli-ready" / "training_dataset_manifest.json").exists()

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "ready_for_training_handoff")
        self.assertEqual(payload["counts"]["eligible_records"], 1)
        self.assertTrue(manifest_exists)

    def test_data_flywheel_pipeline_empty_run_does_not_scan_runtime_or_expose_db_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "missing" / "candidates.db"
            output_root = root / "pipeline"
            data_flywheel_root = root / "flywheel"
            dataset_root = root / "dataset"

            with redirect_stdout(StringIO()) as output:
                exit_code = run_data_flywheel_pipeline.main(
                    [
                        "--db",
                        str(db_path),
                        "--output-root",
                        str(output_root),
                        "--data-flywheel-output-root",
                        str(data_flywheel_root),
                        "--dataset-output-root",
                        str(dataset_root),
                        "--run-id",
                        "unit-empty-pipeline",
                        "--dataset-id",
                        "unit-empty-dataset",
                        "--generated-at",
                        "2026-07-04T12:14:00+00:00",
                        "--json",
                    ]
                )
            payload = json.loads(output.getvalue())
            pipeline_exists = (
                output_root / "unit-empty-pipeline" / "data_flywheel_pipeline_run.json"
            ).exists()
            status_exists = (
                data_flywheel_root
                / "unit-empty-pipeline-data-flywheel"
                / "data_flywheel_status.json"
            ).exists()
            manifest_exists = (
                dataset_root / "unit-empty-dataset" / "training_dataset_manifest.json"
            ).exists()

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["schema_version"], "egolink.data_flywheel_pipeline_run.v0.1")
        self.assertEqual(payload["status"], "needs_recordings")
        self.assertEqual(payload["recordings_requested"], 0)
        self.assertEqual(payload["recordings_ingested"], [])
        self.assertEqual(payload["data_flywheel"]["pipeline_stage"], "candidate_store_missing")
        self.assertEqual(payload["dataset_manifest"]["status"], "not_ready")
        self.assertEqual(payload["dataset_manifest"]["reason"], "candidate_store_missing")
        payload_text = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("record_json", payload_text)
        self.assertNotIn("raw_payload", payload_text)
        self.assertNotIn(str(db_path), payload_text)
        self.assertTrue(pipeline_exists)
        self.assertTrue(status_exists)
        self.assertTrue(manifest_exists)

    def test_data_flywheel_pipeline_ingests_named_recording_and_reports_needs_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recording_dir = root / "recording"
            db_path = root / "candidates.db"
            output_root = root / "pipeline"
            data_flywheel_root = root / "flywheel"
            dataset_root = root / "dataset"
            self.write_recording(recording_dir)
            self.add_annotation(recording_dir)

            with redirect_stdout(StringIO()) as output:
                exit_code = run_data_flywheel_pipeline.main(
                    [
                        "--recording-dir",
                        str(recording_dir),
                        "--db",
                        str(db_path),
                        "--output-root",
                        str(output_root),
                        "--data-flywheel-output-root",
                        str(data_flywheel_root),
                        "--dataset-output-root",
                        str(dataset_root),
                        "--run-id",
                        "unit-ingest-pipeline",
                        "--dataset-id",
                        "unit-ingest-dataset",
                        "--generated-at",
                        "2026-07-04T12:15:00+00:00",
                        "--json",
                    ]
                )
            payload = json.loads(output.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "needs_review")
        self.assertEqual(payload["recordings_requested"], 1)
        self.assertEqual(payload["recordings_ingested"][0]["recording_ref"], "recording")
        self.assertEqual(payload["recordings_ingested"][0]["records_written"], 1)
        self.assertEqual(payload["data_flywheel"]["counts"]["records_total"], 1)
        self.assertEqual(payload["data_flywheel"]["review_queue"]["pending_records"], 1)
        self.assertEqual(payload["dataset_manifest"]["status"], "not_ready")
        self.assertEqual(payload["dataset_manifest"]["reason"], "no_reviewed_training_candidates")
        payload_text = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("record_json", payload_text)
        self.assertNotIn("raw_payload", payload_text)
        self.assertNotIn(str(recording_dir), payload_text)
        self.assertNotIn(str(db_path), payload_text)

    def test_data_flywheel_pipeline_exports_ready_manifest_after_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recording_dir = root / "recording"
            db_path = root / "candidates.db"
            output_root = root / "pipeline"
            data_flywheel_root = root / "flywheel"
            dataset_root = root / "dataset"
            self.write_recording(recording_dir)
            self.add_annotation(recording_dir)
            training_candidate_store.store_recording(recording_dir, db_path)
            record_id = self.read_records(db_path)[0]["record_id"]
            training_candidate_store.review_candidate_record(
                db_path,
                record_id=record_id,
                decision="approve_for_training",
                reviewer="unit",
                split_name="train",
                split_leakage_checked=True,
                privacy_reviewed=True,
                quality_reviewed=True,
                reviewed_at="2026-07-04T12:16:00+00:00",
            )

            with redirect_stdout(StringIO()) as output:
                exit_code = run_data_flywheel_pipeline.main(
                    [
                        "--db",
                        str(db_path),
                        "--output-root",
                        str(output_root),
                        "--data-flywheel-output-root",
                        str(data_flywheel_root),
                        "--dataset-output-root",
                        str(dataset_root),
                        "--run-id",
                        "unit-ready-pipeline",
                        "--dataset-id",
                        "unit-ready-dataset",
                        "--generated-at",
                        "2026-07-04T12:17:00+00:00",
                        "--require-ready",
                        "--json",
                    ]
                )
            payload = json.loads(output.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "ready_for_training_handoff")
        self.assertEqual(payload["data_flywheel"]["status"], "ready_for_experiment")
        self.assertEqual(payload["dataset_manifest"]["status"], "ready_for_training_handoff")
        self.assertEqual(payload["dataset_manifest"]["counts"]["eligible_records"], 1)
        self.assertEqual(payload["dataset_manifest"]["record_sample"][0]["record_id"], record_id)


if __name__ == "__main__":
    unittest.main()

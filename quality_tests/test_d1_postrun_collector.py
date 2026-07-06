from __future__ import annotations

from contextlib import redirect_stdout
from http.server import ThreadingHTTPServer
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

from pc_simulator import protocol, session_annotations, session_recorder, training_candidate_store
from scripts import collect_d1_postrun as collector
from server import message_hub
from quality_tests.test_session_recorder import sample_events


DEVICE_ID = "ego-link-r1-connectivity-001"
TEST_RUN_ID = "d1-postrun-unit-message-run"
TOKEN = "unit-token"


def add_d1_messages(store: message_hub.MessageHubStore) -> None:
    store.create_test_run({"test_run_id": TEST_RUN_ID, "created_at": "2026-07-05T01:00:00+00:00"})
    store.ingest(
        DEVICE_ID,
        "heartbeat",
        protocol.status_message(
            DEVICE_ID,
            "2026-07-05T01:00:00+00:00",
            1,
            test_run_id=TEST_RUN_ID,
            fw_version="0.1.0-d1-periodic-location",
            battery=91,
            link_type="lte",
            guard_mode="child_safety",
            queue_size=0,
            transport={"type": "lte"},
            power={
                "battery_mv": 4090,
                "soc_pct": 91,
                "charging": False,
                "source": "max17048_i2c",
                "source_status": "measured",
                "evidence_status": "measured",
                "state": "guarding",
            },
        ),
    )

    store.ingest(
        DEVICE_ID,
        "telemetry",
        protocol.event_message(
            DEVICE_ID,
            "2026-07-05T02:00:00+00:00",
            2,
            "location_report",
            "normal",
            test_run_id=TEST_RUN_ID,
            fw_version="0.1.0-d1-periodic-location",
            source="sim7670g_firmware_gnss",
            source_status="observed",
            fix=False,
            gnss_state="no_fix",
            power={
                "battery_mv": 4070,
                "soc_pct": 90,
                "charging": False,
                "source": "max17048_i2c",
                "source_status": "measured",
                "evidence_status": "measured",
                "state": "upload",
            },
            transport={"type": "lte"},
            reliability={
                "network": {
                    "raw_post_attempt_count": 2,
                    "raw_post_success_count": 2,
                    "raw_post_failure_count": 0,
                }
            },
        ),
    )
    store.ingest(
        DEVICE_ID,
        "telemetry",
        protocol.event_message(
            DEVICE_ID,
            "2026-07-05T03:00:00+00:00",
            3,
            "location_observation",
            "normal",
            test_run_id=TEST_RUN_ID,
            fw_version="0.1.0-d1-periodic-location",
            source="d1_postrun_unit",
            source_status="observed",
            gnss={"fix": False, "state": "no_fix", "reason_code": "GNSS_NO_FIX"},
            cell={"rat": "LTE", "cell_id": "180571649", "registration_state": "registered_home"},
            lte={"registered": True, "pdp_active": True, "reason_code": "LTE_READY", "pdp_state": "active"},
            imu={"motion": "stationary", "confidence": 0.91, "evidence_status": "observed"},
            power={
                "battery_mv": 4050,
                "soc_pct": 89,
                "charging": False,
                "source": "max17048_i2c",
                "source_status": "measured",
                "evidence_status": "measured",
                "state": "upload",
            },
            transport={"type": "lte"},
            reliability={
                "network": {
                    "raw_post_attempt_count": 3,
                    "raw_post_success_count": 3,
                    "raw_post_failure_count": 0,
                }
            },
            location_belief={
                "state": "Coarse",
                "radius_m": 250,
                "confidence": 0.68,
                "source": ["cell_lte"],
                "reason": "unit_test_cell_observation",
            },
        ),
    )


def write_reviewed_candidate_store(root: Path) -> Path:
    recording_dir = root / "recording"
    db_path = root / "candidates.db"
    recording = session_recorder.build_recording(
        sample_events(),
        event_log=Path("events.jsonl"),
        session_id="postrun-training-session",
        created_at="2026-07-05T04:00:00+00:00",
    )
    session_recorder.write_recording(recording, recording_dir)
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
        annotation_id="ann-postrun-training",
        created_at="2026-07-05T04:01:00+00:00",
        training_allowed=True,
    )
    training_candidate_store.store_recording(recording_dir, db_path, generated_at="2026-07-05T04:02:00+00:00")
    connection = sqlite3.connect(db_path)
    try:
        record_id = str(
            connection.execute(
                "SELECT record_id FROM training_candidate_records ORDER BY record_id LIMIT 1"
            ).fetchone()[0]
        )
    finally:
        connection.close()
    training_candidate_store.review_candidate_record(
        db_path,
        record_id=record_id,
        decision="approve_for_training",
        reviewer="unit",
        split_name="train",
        split_leakage_checked=True,
        privacy_reviewed=True,
        quality_reviewed=True,
        reviewed_at="2026-07-05T04:03:00+00:00",
    )
    return db_path


class D1PostrunCollectorTests(unittest.TestCase):
    def test_collector_composes_postrun_reports_without_secret_leak(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            token_file = root / "token.txt"
            token_file.write_text(f"{TOKEN}\n", encoding="utf-8")
            store = message_hub.MessageHubStore(root / "hub.db")
            add_d1_messages(store)
            server = ThreadingHTTPServer(("127.0.0.1", 0), message_hub.make_handler(store, token=TOKEN))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    exit_code = collector.main(
                        [
                            "--run-id",
                            "D1-POSTRUN-unit",
                            "--hub-url",
                            base_url,
                            "--token-file",
                            str(token_file),
                            "--device-id",
                            DEVICE_ID,
                            "--message-test-run-id",
                            TEST_RUN_ID,
                            "--output-root",
                            str(root / "postrun"),
                            "--web-api-output-dir",
                            str(root / "web"),
                            "--power-output-dir",
                            str(root / "power"),
                            "--d1-demo-output-dir",
                            str(root / "demo"),
                            "--db",
                            str(root / "candidates.db"),
                            "--data-flywheel-pipeline-output-root",
                            str(root / "pipeline"),
                            "--data-flywheel-output-root",
                            str(root / "flywheel"),
                            "--dataset-output-root",
                            str(root / "datasets"),
                            "--experiment-output-root",
                            str(root / "experiments"),
                            "--min-duration-hours",
                            "2",
                            "--battery-capacity-mah",
                            "1000",
                            "--created-at",
                            "2026-07-05T03:30:00+00:00",
                            "--json",
                        ]
                    )
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

            payload = json.loads(stdout.getvalue())
            summary_path = root / "postrun" / "D1-POSTRUN-unit" / collector.SUMMARY_JSON
            summary_md = root / "postrun" / "D1-POSTRUN-unit" / collector.SUMMARY_MARKDOWN

            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["schema_version"], collector.SCHEMA_VERSION)
            self.assertEqual(payload["result"], "WARN")
            self.assertEqual(payload["components"]["web_api"]["result"], "PASS")
            self.assertIn(payload["components"]["power_curve"]["result"], {"PASS", "WARN"})
            self.assertIn(payload["components"]["d1_demo"]["result"], {"PASS", "WARN"})
            self.assertGreaterEqual(payload["components"]["power_curve"]["counts"]["measured_power_samples"], 1)
            self.assertEqual(payload["components"]["data_flywheel_pipeline"]["status"], "needs_recordings")
            self.assertEqual(payload["components"]["field_observation"]["status"], "skipped")
            self.assertEqual(payload["components"]["field_observation"]["reason"], "field_observation_report_missing")
            self.assertEqual(payload["components"]["training_readiness"]["status"], "skipped")
            self.assertEqual(
                payload["components"]["training_readiness"]["reason"],
                "field_observation_not_available_for_training_readiness",
            )
            self.assertEqual(payload["components"]["labeling_intake"]["status"], "skipped")
            self.assertEqual(
                payload["components"]["labeling_intake"]["reason"],
                "training_readiness_not_available_for_labeling_intake",
            )
            self.assertEqual(payload["components"]["labeling_queue"]["status"], "skipped")
            self.assertEqual(
                payload["components"]["labeling_queue"]["reason"],
                "labeling_intake_not_available_for_queue",
            )
            self.assertEqual(
                payload["components"]["data_flywheel_pipeline"]["training_experiment"]["status"],
                "blocked_dataset_not_ready",
            )
            self.assertEqual(payload["components"]["training_chain"]["status"], "skipped")
            self.assertEqual(payload["components"]["training_chain"]["reason"], "data_flywheel_pipeline_not_ready")
            self.assertFalse(payload["scope"]["hardware_contacted"])
            self.assertFalse(payload["scope"]["commands_sent"])
            self.assertFalse(payload["scope"]["model_training_started"])
            self.assertFalse(payload["scope"]["model_artifact_written"])
            self.assertTrue(summary_path.is_file())
            self.assertTrue(summary_md.is_file())
            self.assertTrue((root / "web" / "d1_web_api_report.json").is_file())
            self.assertTrue((root / "power" / "test_run_export.json").is_file())
            self.assertTrue((root / "power" / "power_curve_report.json").is_file())
            self.assertTrue((root / "demo" / "d1_demo_report.json").is_file())
            self.assertTrue(
                (root / "pipeline" / "D1-POSTRUN-unit-data-pipeline" / "data_flywheel_pipeline_run.json").is_file()
            )
            self.assertTrue((root / "datasets" / "D1-POSTRUN-unit-dataset" / "training_dataset_manifest.json").is_file())
            self.assertTrue(
                (root / "experiments" / "D1-POSTRUN-unit-data-pipeline-experiment" / "training_experiment_plan.json").is_file()
            )
            output_text = stdout.getvalue() + summary_path.read_text(encoding="utf-8") + summary_md.read_text(encoding="utf-8")
            self.assertNotIn(TOKEN, output_text)
            self.assertNotIn(str(root / "candidates.db"), output_text)

    def test_collector_runs_training_chain_when_dataset_handoff_is_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = write_reviewed_candidate_store(root)
            field_dir = root / "field_observation"
            field_dir.mkdir()
            field_status = field_dir / "d1_field_observation_status.json"
            field_report = field_dir / "d1_field_observation_report.json"
            field_status.write_text(
                json.dumps(
                    {
                        "status": "completed",
                        "result": "WARN",
                        "run_id": "D1-POSTRUN-ready-training",
                        "sample_count": 2,
                        "successful_sample_count": 2,
                        "fetch_error_count": 0,
                        "latest_seq": 11,
                        "latest_freshness_s": 31,
                        "report_path": str(field_report),
                        "samples_path": str(field_dir / "d1_field_samples.jsonl"),
                    }
                ),
                encoding="utf-8",
            )
            field_report.write_text(
                json.dumps(
                    {
                        "result": "WARN",
                        "observer_version": "D1.field_observer.v2",
                        "run_id": "D1-POSTRUN-ready-training",
                        "summary": {
                            "sample_count": 2,
                            "successful_sample_count": 2,
                            "fetch_error_count": 0,
                            "last_seq": 11,
                            "last_location_upload_at": "2026-07-05T04:20:00+00:00",
                            "max_freshness_s": 31,
                            "raw_post_success_delta": 2,
                            "location_event_count_delta": 1,
                            "power_sample_count_delta": 1,
                        },
                        "warnings": ["d1_coordinate_not_observed"],
                        "errors": [],
                        "samples_path": str(field_dir / "d1_field_samples.jsonl"),
                        "status_path": str(field_status),
                        "report_path": str(field_report),
                        "markdown_report_path": str(field_dir / "d1_field_observation_report.md"),
                    }
                ),
                encoding="utf-8",
            )
            store = message_hub.MessageHubStore(root / "hub.db")
            add_d1_messages(store)
            server = ThreadingHTTPServer(("127.0.0.1", 0), message_hub.make_handler(store))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    exit_code = collector.main(
                        [
                            "--run-id",
                            "D1-POSTRUN-ready-training",
                            "--hub-url",
                            base_url,
                            "--device-id",
                            DEVICE_ID,
                            "--skip-power",
                            "--db",
                            str(db_path),
                            "--data-flywheel-pipeline-output-root",
                            str(root / "pipeline"),
                            "--data-flywheel-output-root",
                            str(root / "flywheel"),
                            "--dataset-output-root",
                            str(root / "datasets"),
                            "--experiment-output-root",
                            str(root / "experiments"),
                            "--training-run-output-root",
                            str(root / "training_runs"),
                            "--training-feature-output-root",
                            str(root / "features"),
                            "--training-runner-dry-run-output-root",
                            str(root / "runner"),
                            "--training-baseline-eval-output-root",
                            str(root / "baselines"),
                            "--training-handoff-output-root",
                            str(root / "handoffs"),
                            "--training-job-output-root",
                            str(root / "jobs"),
                            "--output-root",
                            str(root / "postrun"),
                            "--web-api-output-dir",
                            str(root / "web"),
                            "--d1-demo-output-dir",
                            str(root / "demo"),
                            "--field-observation-report",
                            str(field_report),
                            "--field-observation-status",
                            str(field_status),
                            "--training-readiness-output-root",
                            str(root / "d1_training_readiness"),
                            "--labeling-intake-output-root",
                            str(root / "d1_labeling_intake"),
                            "--labeling-queue-output-root",
                            str(root / "d1_labeling_queue"),
                            "--created-at",
                            "2026-07-05T04:30:00+00:00",
                            "--json",
                        ]
                    )
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

            payload = json.loads(stdout.getvalue())
            output_text = stdout.getvalue() + json.dumps(payload, ensure_ascii=False)

            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["components"]["field_observation"]["result"], "WARN")
            self.assertEqual(payload["components"]["field_observation"]["sample_count"], 2)
            self.assertEqual(payload["components"]["field_observation"]["last_seq"], 11)
            training_readiness = payload["components"]["training_readiness"]
            self.assertEqual(training_readiness["status"], "ready_for_labeling_review")
            self.assertTrue(training_readiness["ready_for_labeling_review"])
            self.assertFalse(training_readiness["ready_for_training_handoff"])
            self.assertFalse(training_readiness["training_allowed"])
            self.assertIn("privacy_review_required", training_readiness["blockers"])
            self.assertTrue(
                (
                    root
                    / "d1_training_readiness"
                    / "D1-POSTRUN-ready-training-training-readiness"
                    / "d1_training_readiness.json"
                ).is_file()
            )
            labeling_intake = payload["components"]["labeling_intake"]
            self.assertEqual(labeling_intake["status"], "pending_human_review")
            self.assertEqual(labeling_intake["pending_items"], 1)
            self.assertEqual(labeling_intake["operator_label"], "missing")
            self.assertEqual(labeling_intake["privacy_review"], "required")
            self.assertEqual(labeling_intake["candidate_store_gate"], "not_written")
            self.assertTrue(
                (
                    root
                    / "d1_labeling_intake"
                    / "D1-POSTRUN-ready-training-labeling-intake"
                    / "d1_labeling_intake.json"
                ).is_file()
            )
            labeling_queue = payload["components"]["labeling_queue"]
            self.assertEqual(labeling_queue["status"], "pending_human_review")
            self.assertEqual(labeling_queue["intake_report_count"], 1)
            self.assertEqual(labeling_queue["pending_item_count"], 1)
            self.assertEqual(labeling_queue["first_operator_label"], "missing")
            self.assertEqual(labeling_queue["first_privacy_review"], "required")
            self.assertEqual(labeling_queue["first_source_run_id"], "D1-POSTRUN-ready-training")
            self.assertTrue(
                (
                    root
                    / "d1_labeling_queue"
                    / "D1-POSTRUN-ready-training-labeling-queue"
                    / "d1_labeling_queue.json"
                ).is_file()
            )
            self.assertEqual(payload["components"]["data_flywheel_pipeline"]["status"], "ready_for_training_handoff")
            self.assertEqual(
                payload["components"]["data_flywheel_pipeline"]["training_experiment"]["status"],
                "ready_for_runner",
            )
            training_chain = payload["components"]["training_chain"]
            self.assertEqual(training_chain["status"], "ready_for_runner_queue")
            self.assertEqual(training_chain["preflight"]["status"], "ready_for_training_runner")
            self.assertEqual(training_chain["feature_manifest"]["status"], "ready_for_feature_runner")
            self.assertEqual(training_chain["feature_manifest"]["row_count"], 1)
            self.assertEqual(training_chain["runner_dry_run"]["status"], "ready_for_runner_execution")
            self.assertEqual(training_chain["baseline_eval"]["status"], "baseline_eval_complete")
            self.assertEqual(training_chain["baseline_eval"]["metric_scope"], "reviewed_engineering_dataset")
            self.assertEqual(training_chain["handoff_bundle"]["status"], "ready_for_training_server_handoff")
            self.assertEqual(training_chain["handoff_bundle"]["handoff_id"], "D1-POSTRUN-ready-training-training-handoff")
            self.assertEqual(training_chain["handoff_bundle"]["training_server"], "not_configured")
            self.assertFalse(training_chain["handoff_bundle"]["dry_run_only"])
            self.assertEqual(training_chain["job_plan"]["status"], "ready_for_runner_queue")
            self.assertEqual(training_chain["job_plan"]["job_id"], "D1-POSTRUN-ready-training-training-job")
            self.assertEqual(training_chain["job_plan"]["queue_state"], "plan_only")
            self.assertFalse(training_chain["job_plan"]["dry_run_only"])
            self.assertTrue(
                (
                    root
                    / "training_runs"
                    / "D1-POSTRUN-ready-training-training-preflight"
                    / "training_run_preflight.json"
                ).is_file()
            )
            self.assertTrue(
                (
                    root
                    / "features"
                    / "D1-POSTRUN-ready-training-features"
                    / "training_feature_manifest.json"
                ).is_file()
            )
            self.assertTrue(
                (
                    root
                    / "features"
                    / "D1-POSTRUN-ready-training-features"
                    / "training_feature_rows.jsonl"
                ).is_file()
            )
            self.assertTrue(
                (
                    root
                    / "runner"
                    / "D1-POSTRUN-ready-training-runner-dry-run"
                    / "training_runner_dry_run.json"
                ).is_file()
            )
            self.assertTrue(
                (
                    root
                    / "baselines"
                    / "D1-POSTRUN-ready-training-baseline-eval"
                    / "training_baseline_eval.json"
                ).is_file()
            )
            self.assertTrue(
                (
                    root
                    / "handoffs"
                    / "D1-POSTRUN-ready-training-training-handoff"
                    / "training_handoff_bundle.json"
                ).is_file()
            )
            self.assertTrue(
                (
                    root
                    / "jobs"
                    / "D1-POSTRUN-ready-training-training-job"
                    / "training_job_plan.json"
                ).is_file()
            )
            self.assertEqual(
                payload["artifacts"]["training_job_plan"],
                "training_job_plan.json",
            )
            self.assertEqual(payload["artifacts"]["field_observation_report"], str(field_report))
            self.assertEqual(payload["artifacts"]["field_observation_status"], str(field_status))
            self.assertEqual(payload["artifacts"]["d1_training_readiness"], "d1_training_readiness.json")
            self.assertEqual(payload["artifacts"]["d1_labeling_intake"], "d1_labeling_intake.json")
            self.assertEqual(payload["artifacts"]["d1_labeling_queue"], "d1_labeling_queue.json")
            self.assertFalse(payload["scope"]["model_training_started"])
            self.assertFalse(payload["scope"]["model_evaluation_started"])
            self.assertFalse(payload["scope"]["model_artifact_written"])
            self.assertFalse(payload["scope"]["sample_jsonl_read_for_training_readiness"])
            self.assertFalse(payload["scope"]["sample_jsonl_read_for_labeling_intake"])
            self.assertFalse(payload["scope"]["sample_jsonl_read_for_labeling_queue"])
            self.assertFalse(payload["scope"]["candidate_db_written_for_labeling_intake"])
            self.assertFalse(payload["scope"]["candidate_db_written_for_labeling_queue"])
            self.assertNotIn(str(db_path), output_text)
            self.assertNotIn("record_json", output_text)
            self.assertNotIn("raw_payload", output_text)

    def test_collector_skip_power_keeps_summary_writeable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = message_hub.MessageHubStore(root / "hub.db")
            add_d1_messages(store)
            server = ThreadingHTTPServer(("127.0.0.1", 0), message_hub.make_handler(store))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    exit_code = collector.main(
                        [
                            "--run-id",
                            "D1-POSTRUN-skip-power",
                            "--hub-url",
                            base_url,
                            "--device-id",
                            DEVICE_ID,
                            "--skip-power",
                            "--skip-data-flywheel",
                            "--output-root",
                            str(root / "postrun"),
                            "--web-api-output-dir",
                            str(root / "web"),
                            "--d1-demo-output-dir",
                            str(root / "demo"),
                            "--json",
                        ]
                    )
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

            payload = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["result"], "WARN")
        self.assertEqual(payload["components"]["web_api"]["result"], "PASS")
        self.assertEqual(payload["components"]["power_curve"]["status"], "skipped")
        self.assertEqual(payload["components"]["power_curve"]["reason"], "skip_power_requested")
        self.assertEqual(payload["components"]["d1_demo"]["result"], "WARN")
        self.assertEqual(payload["components"]["data_flywheel_pipeline"]["status"], "skipped")
        self.assertEqual(payload["components"]["training_readiness"]["status"], "skipped")
        self.assertEqual(payload["components"]["labeling_intake"]["status"], "skipped")
        self.assertEqual(payload["components"]["labeling_queue"]["status"], "skipped")
        self.assertEqual(payload["components"]["training_chain"]["status"], "skipped")
        self.assertEqual(payload["components"]["training_chain"]["reason"], "data_flywheel_pipeline_missing")


if __name__ == "__main__":
    unittest.main()

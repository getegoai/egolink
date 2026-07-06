from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest

from server import message_hub


class MessageHubDashboardTests(unittest.TestCase):
    def test_dashboard_exposes_field_state_and_command_panels(self) -> None:
        html = message_hub.render_dashboard()

        self.assertIn("Latest Field State", html)
        self.assertIn("Run Context", html)
        self.assertIn("Commands", html)
        self.assertIn("Raw Frames", html)
        self.assertIn("Product Demo", html)
        self.assertIn("Field Test Results", html)
        self.assertIn("Data Flywheel", html)
        self.assertIn("Training Experiments", html)
        self.assertIn("Training Run Preflight", html)
        self.assertIn("Training Feature Manifest", html)
        self.assertIn("Training Runner Dry-Run", html)
        self.assertIn("Training Baseline Eval", html)
        self.assertIn("Training Handoff Bundle", html)
        self.assertIn("Training Job Plan", html)
        self.assertIn("Synthetic Training Chain", html)
        self.assertIn("D1 Training Readiness", html)
        self.assertIn("D1 Labeling Intake", html)
        self.assertIn("D1 Link Through", html)
        self.assertIn("dashboard-shell", html)
        self.assertIn("Field live view", html)
        self.assertIn("runContext", html)
        self.assertIn("rawFrames", html)
        self.assertIn("productDemo", html)
        self.assertIn("fieldResults", html)
        self.assertIn("dataFlywheel", html)
        self.assertIn("trainingExperiment", html)
        self.assertIn("trainingRunPreflight", html)
        self.assertIn("trainingFeatureManifest", html)
        self.assertIn("trainingRunnerDryRun", html)
        self.assertIn("trainingBaselineEval", html)
        self.assertIn("trainingHandoffBundle", html)
        self.assertIn("trainingJobPlan", html)
        self.assertIn("syntheticTrainingChain", html)
        self.assertIn("d1TrainingReadiness", html)
        self.assertIn("d1LabelingIntake", html)
        self.assertIn("d1Link", html)
        self.assertIn("d1_link", html)
        self.assertIn("field_results", html)
        self.assertIn("data_flywheel", html)
        self.assertIn("dataFlywheelPanel", html)
        self.assertIn("training_experiment", html)
        self.assertIn("trainingExperimentPanel", html)
        self.assertIn("training_run_preflight", html)
        self.assertIn("trainingRunPreflightPanel", html)
        self.assertIn("training_feature_manifest", html)
        self.assertIn("trainingFeatureManifestPanel", html)
        self.assertIn("training_runner_dry_run", html)
        self.assertIn("trainingRunnerDryRunPanel", html)
        self.assertIn("training_baseline_eval", html)
        self.assertIn("trainingBaselineEvalPanel", html)
        self.assertIn("training_handoff_bundle", html)
        self.assertIn("trainingHandoffBundlePanel", html)
        self.assertIn("training_job_plan", html)
        self.assertIn("trainingJobPlanPanel", html)
        self.assertIn("synthetic_training_chain", html)
        self.assertIn("syntheticTrainingChainPanel", html)
        self.assertIn("d1_training_readiness", html)
        self.assertIn("d1TrainingReadinessPanel", html)
        self.assertIn("d1_labeling_intake", html)
        self.assertIn("d1LabelingIntakePanel", html)
        self.assertIn("Runner Handoff", html)
        self.assertIn("Runner Ready", html)
        self.assertIn("Feature Rows", html)
        self.assertIn("Target Boundary", html)
        self.assertIn("Source Match", html)
        self.assertIn("Runner Input", html)
        self.assertIn("Target Guard", html)
        self.assertIn("Metric Scope", html)
        self.assertIn("Performance Claim", html)
        self.assertIn("Source Refs", html)
        self.assertIn("raw_rows_exposed", html)
        self.assertIn("Runner Queue", html)
        self.assertIn("Planned Metrics", html)
        self.assertIn("Synthetic Review", html)
        self.assertIn("Data Pipeline", html)
        self.assertIn("Review Ready", html)
        self.assertIn("First Intake", html)
        self.assertIn("Label Groups", html)
        self.assertIn("Sensor Gaps", html)
        self.assertIn("Synthetic Gate", html)
        self.assertIn("Measured Metrics", html)
        self.assertIn("Classification Metrics", html)
        self.assertIn("Footprint Metrics", html)
        self.assertIn("Candidate Records", html)
        self.assertIn("Training Gate", html)
        self.assertIn("Review Queues", html)
        self.assertIn("Review Queue", html)
        self.assertIn("review_queue", html)
        self.assertIn("sample_records", html)
        self.assertIn("available_actions", html)
        self.assertIn("Training Server", html)
        self.assertIn("fieldResultsPanel", html)
        self.assertIn("fieldResultsCards", html)
        self.assertIn("d1FieldOverview", html)
        self.assertIn("d1StatusStrip", html)
        self.assertIn("d1FreshnessBadge", html)
        self.assertIn("d1FieldReadyBadge", html)
        self.assertIn("field_readiness", html)
        self.assertIn("Field Ready", html)
        self.assertIn("Ready Reason", html)
        self.assertIn("Operator Action", html)
        self.assertIn("Freshness Gate", html)
        self.assertIn("readinessClass", html)
        self.assertIn("readinessHeadline", html)
        self.assertIn("status-chip", html)
        self.assertIn("d1-card", html)
        self.assertIn("D1 Status", html)
        self.assertIn("Map Surface", html)
        self.assertIn("map-surface", html)
        self.assertIn("data-d1-map-mode", html)
        self.assertIn("Accuracy Claim", html)
        self.assertIn("Upload Freshness", html)
        self.assertIn("Upload Success", html)
        self.assertIn("Location Uploads", html)
        self.assertIn("Power Curve", html)
        self.assertIn("Power Delta", html)
        self.assertIn("Battery Claim", html)
        self.assertIn("uplink_metrics", html)
        self.assertIn("power_curve", html)
        self.assertIn("raw_post_success_rate", html)
        self.assertIn("battery_life_claim", html)
        self.assertIn("GNSS Evidence", html)
        self.assertIn("Cell/LTE Evidence", html)
        self.assertIn("IMU Evidence", html)
        self.assertIn("Power Evidence", html)
        self.assertIn("product_demo", html)
        self.assertIn("KR-008", html)
        self.assertIn("DEMO-008", html)
        self.assertIn("Evidence Mode", html)
        self.assertIn("Web Review", html)
        self.assertIn("Release Ready", html)
        self.assertIn("raw_frames", html)
        self.assertIn("current_run", html)
        self.assertIn("Current Run", html)
        self.assertIn("Key Release", html)
        self.assertIn("Baseline", html)
        self.assertIn("Command Chain", html)
        self.assertIn("Raw Evidence", html)
        self.assertIn("Derived Location", html)
        self.assertIn("Failure State", html)
        self.assertIn("Failure Reason", html)
        self.assertIn("Network Reconnect", html)
        self.assertIn("Network Error", html)
        self.assertIn("Raw POST", html)
        self.assertIn("raw_post_attempt_count", html)
        self.assertIn("raw_post_success_count", html)
        self.assertIn("raw_post_failure_count", html)
        self.assertIn("Cache Queue", html)
        self.assertIn("Cache Retry", html)
        self.assertIn("retry_attempt_count", html)
        self.assertIn("retry_success_count", html)
        self.assertIn("retry_failure_count", html)
        self.assertIn("Cache Flush", html)
        self.assertIn("flush_attempt_count", html)
        self.assertIn("flush_success_count", html)
        self.assertIn("flush_failure_count", html)
        self.assertIn("Cache Drops", html)
        self.assertIn("EALE-P0", html)
        self.assertIn("EALE Reason", html)
        self.assertIn("EALE Failure", html)
        self.assertIn("Dataset Window", html)
        self.assertIn("Dataset Training", html)
        self.assertIn("Quality Flags", html)
        self.assertIn("rawFrameStatus", html)
        self.assertIn("Raw Frame ID", html)
        self.assertIn("Raw Derived", html)
        self.assertIn("onlineLabel", html)
        self.assertIn("GNSS State", html)
        self.assertIn("gnssField", html)
        self.assertIn("Fix", html)
        self.assertIn("Satellites", html)
        self.assertIn("HDOP", html)
        self.assertIn("Source Status", html)
        self.assertIn("Location Updated", html)
        self.assertIn("Field Message", html)
        self.assertIn("Location State", html)
        self.assertIn("Belief", html)
        self.assertIn("Belief Source", html)
        self.assertIn("Belief Reason", html)
        self.assertIn("Memory State", html)
        self.assertIn("Memory Updated", html)
        self.assertIn("Memory Reason", html)
        self.assertIn("Transport", html)
        self.assertIn("Runtime Reset", html)
        self.assertIn("obsReliability", html)
        self.assertIn("obsRelNetwork", html)
        self.assertIn("obsRelCache", html)
        self.assertIn("Command", html)
        self.assertIn("Power", html)
        self.assertIn("Cell", html)
        self.assertIn("LTE", html)
        self.assertIn("LTE Reason", html)
        self.assertIn("Wi-Fi", html)
        self.assertIn("IMU", html)
        self.assertIn("evidence_status", html)
        self.assertIn("source_status", html)
        self.assertIn("GNSS Reason", html)
        self.assertIn("Reason Codes", html)
        self.assertIn("observability", html)
        self.assertIn("latest_location", html)
        self.assertIn("location_memory", html)
        self.assertIn("API token required", html)
        self.assertIn("Last Error", html)
        self.assertIn("tokenInput", html)
        self.assertIn("Authorization: `Bearer ${token}`", html)

    def test_d1_link_summary_marks_fresh_periodic_upload_ready(self) -> None:
        now = message_hub.utc_now()
        location = {
            "message_type": "event",
            "event_type": "location_report",
            "seq": 42,
            "server_received_at": now,
            "fix": False,
            "gnss_state": "no_fix",
        }
        device = {
            "device_id": "ego-link-r1-connectivity-001",
            "last_seen_at": now,
            "last_seq": 42,
            "latest_location": location,
            "observability": {
                "location_belief": {
                    "state": "Predicted",
                    "reason": "unit_fresh_periodic_upload",
                    "updated_at": now,
                },
                "transport": {"type": "lte"},
            },
        }
        messages = [
            {
                **location,
                "reliability": {
                    "network": {
                        "raw_post_attempt_count": 4,
                        "raw_post_success_count": 4,
                        "raw_post_failure_count": 0,
                    }
                },
            }
        ]

        summary = message_hub.build_d1_link_summary(device, messages)

        readiness = summary["field_readiness"]
        self.assertTrue(readiness["ready"])
        self.assertEqual(readiness["state"], "ready")
        self.assertEqual(readiness["reason"], "fresh_periodic_upload")
        self.assertEqual(readiness["operator_action"], "go_test")
        self.assertLessEqual(readiness["freshness_s"], message_hub.D1_FIELD_READY_FRESHNESS_S)
        self.assertEqual(readiness["raw_post_health"], "ok")
        self.assertIn("location_accuracy_not_claimed", readiness["non_claims"])

    def test_d1_link_summary_waits_without_periodic_location_upload(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        device = {
            "device_id": "ego-link-r1-connectivity-001",
            "last_seen_at": now,
            "last_seq": 7,
            "observability": {"transport": {"type": "lte"}},
        }

        summary = message_hub.build_d1_link_summary(device, messages=[])

        readiness = summary["field_readiness"]
        self.assertFalse(readiness["ready"])
        self.assertEqual(readiness["state"], "waiting_for_data")
        self.assertEqual(readiness["reason"], "no_periodic_location_upload")
        self.assertEqual(readiness["operator_action"], "wait_for_new_dashboard_data")

    def test_d1_link_summary_marks_old_periodic_upload_not_ready(self) -> None:
        old = (datetime.now(timezone.utc) - timedelta(seconds=message_hub.D1_FIELD_STALE_FRESHNESS_S + 60)).isoformat()
        location = {
            "message_type": "event",
            "event_type": "location_observation",
            "seq": 8,
            "server_received_at": old,
        }
        device = {
            "device_id": "ego-link-r1-connectivity-001",
            "last_seen_at": old,
            "last_seq": 8,
            "latest_location": location,
            "observability": {"location_belief": {"state": "Predicted", "updated_at": old}},
        }

        summary = message_hub.build_d1_link_summary(device, messages=[location])

        readiness = summary["field_readiness"]
        self.assertFalse(readiness["ready"])
        self.assertEqual(readiness["state"], "not_ready")
        self.assertEqual(readiness["reason"], "periodic_upload_too_old")
        self.assertEqual(readiness["operator_action"], "check_power_sim_lte_or_reboot")

    def test_latest_field_results_summary_is_bounded_for_dashboard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            d1_dir = root / "d1_web_api" / "run-a"
            d1_dir.mkdir(parents=True)
            (d1_dir / "d1_web_api_report.json").write_text(
                json.dumps(
                    {
                        "result": "PASS",
                        "created_at": "2026-07-04T11:18:46+00:00",
                        "review_id": "ui001-web-vps-20260704",
                        "device_id": "ego-link-r1-connectivity-001",
                        "d1": {
                            "status": "estimate_visible",
                            "upload_freshness": {"freshness_s": 30},
                            "uplink_metrics": {
                                "raw_post_success_count": 45,
                                "raw_post_failure_count": 0,
                                "location_event_count": 22,
                            },
                            "power_curve": {"sample_count": 11, "window_s": 680},
                        },
                        "scope": {"commands_sent": False},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (d1_dir / "d1_web_api_report.md").write_text("# D1\n", encoding="utf-8")

            amoled_dir = root / "amoled_visible_status" / "run-b"
            amoled_dir.mkdir(parents=True)
            (amoled_dir / "run-b.summary.json").write_text(
                json.dumps(
                    {
                        "ok": True,
                        "session_id": "run-b",
                        "command_ack_count": 1,
                        "status_rendered_count": 1,
                        "last_status_payload": {
                            "summary": "LIVE fresh 58s",
                            "location": "Coord 0.37919,1.23713",
                            "battery": "88% / 4052mV",
                        },
                        "jsonl_path": "reports/amoled_visible_status/run-b/run-b.jsonl",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            companion_dir = root / "d1_field_companion" / "run-c"
            companion_dir.mkdir(parents=True)
            (companion_dir / "d1_field_companion_summary.json").write_text(
                json.dumps(
                    {
                        "result": "PASS",
                        "run_id": "run-c",
                        "created_at": "2026-07-04T11:30:00+00:00",
                        "children": [
                            {
                                "name": "d1_observer",
                                "summary": {
                                    "device_id": "ego-link-r1-connectivity-001",
                                    "summary": {
                                        "sample_count": 2,
                                        "successful_sample_count": 2,
                                        "coordinate_sample_count": 1,
                                        "max_freshness_s": 40,
                                    },
                                    "warnings": [],
                                    "errors": [],
                                },
                            },
                            {"name": "amoled_sidecar", "summary": {"status_rendered_count": 2}},
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            observation_dir = root / "d1_field_observation" / "run-d"
            observation_dir.mkdir(parents=True)
            (observation_dir / "d1_field_observation_status.json").write_text(
                json.dumps(
                    {
                        "status": "completed",
                        "result": "WARN",
                        "run_id": "run-d",
                        "sample_count": 4,
                        "successful_sample_count": 4,
                        "fetch_error_count": 0,
                        "latest_seq": 42,
                        "latest_freshness_s": 33,
                        "report_path": "C:/private/local/d1_field_observation_report.json",
                        "samples_path": "C:/private/local/d1_field_samples.jsonl",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (observation_dir / "d1_field_observation_report.json").write_text(
                json.dumps(
                    {
                        "result": "WARN",
                        "observer_version": "D1.field_observer.v2",
                        "run_id": "run-d",
                        "created_at": "2026-07-04T11:40:00+00:00",
                        "device_id": "ego-link-r1-connectivity-001",
                        "summary": {
                            "sample_count": 4,
                            "successful_sample_count": 4,
                            "fetch_error_count": 0,
                            "last_seq": 42,
                            "last_location_upload_at": "2026-07-04T11:39:00+00:00",
                            "max_freshness_s": 44,
                            "raw_post_success_delta": 3,
                            "location_event_count_delta": 2,
                            "power_sample_count_delta": 1,
                            "battery_mv_first": 4100,
                            "battery_mv_last": 4090,
                        },
                        "warnings": ["d1_coordinate_not_observed"],
                        "errors": [],
                        "samples_path": "C:/private/local/d1_field_samples.jsonl",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (observation_dir / "d1_field_observation_report.md").write_text("# Observation\n", encoding="utf-8")
            live_observation_dir = root / "d1_field_observation" / "run-e"
            live_observation_dir.mkdir(parents=True)
            live_status_path = live_observation_dir / "d1_field_observation_status.json"
            live_status_path.write_text(
                json.dumps(
                    {
                        "status": "running",
                        "run_id": "run-e",
                        "sample_count": 6,
                        "successful_sample_count": 6,
                        "fetch_error_count": 0,
                        "latest_seq": 100,
                        "latest_freshness_s": 12,
                        "report_path": "C:/private/local/live_report.json",
                        "samples_path": "C:/private/local/d1_field_samples.jsonl",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            os.utime(live_status_path, (2_000_000_000, 2_000_000_000))

            summary = message_hub.load_latest_field_results(root)

        self.assertTrue(summary["available"])
        self.assertEqual(summary["status"], "running")
        self.assertEqual(summary["report_count"], 4)
        kinds = {item["kind"] for item in summary["reports"]}
        self.assertEqual(kinds, {"d1_web_api", "amoled_status", "d1_field_companion", "d1_field_observation"})
        amoled = next(item for item in summary["reports"] if item["kind"] == "amoled_status")
        self.assertNotIn("jsonl_path", json.dumps(amoled))
        self.assertEqual(amoled["metrics"]["command_ack_count"], 1)
        observation = next(item for item in summary["reports"] if item["kind"] == "d1_field_observation")
        self.assertEqual(observation["status"], "running")
        self.assertEqual(observation["run_id"], "run-e")
        self.assertEqual(observation["metrics"]["sample_count"], 6)
        self.assertEqual(observation["metrics"]["latest_seq"], 100)
        observation_payload = json.dumps(observation)
        self.assertNotIn("d1_field_samples.jsonl", observation_payload)
        self.assertNotIn("C:/private", observation_payload)

    def test_field_results_missing_returns_explainable_not_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary = message_hub.load_latest_field_results(Path(tmp))

        self.assertFalse(summary["available"])
        self.assertEqual(summary["status"], "not_available")
        self.assertEqual(summary["reason"], "no_field_result_reports")

    def test_latest_data_flywheel_status_summary_is_bounded_for_dashboard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_dir = root / "run-a"
            report_dir.mkdir(parents=True)
            (report_dir / "data_flywheel_status.json").write_text(
                json.dumps(
                    {
                        "schema_version": "egolink.data_flywheel_status.v0.1",
                        "run_id": "unit-data-flywheel",
                        "generated_at": "2026-07-04T12:04:00+00:00",
                        "status": "needs_review",
                        "pipeline_stage": "candidate_review_pending",
                        "candidate_store": {
                            "available": True,
                            "db_path": "C:/private/path/training_candidates.db",
                            "schema_version": "egolink.training_candidate_store.v0.1",
                            "latest_updated_at": "2026-07-04T12:03:00+00:00",
                        },
                        "counts": {
                            "sessions_total": 1,
                            "records_total": 3,
                            "needs_review_records": 3,
                            "training_allowed_records": 0,
                            "reviewed_training_candidate_records": 0,
                            "experiment_input_records": 0,
                        },
                        "state_counts": {"candidate": 3},
                        "candidate_type_counts": {"needs_help": 3},
                        "quality_gate_counts": {"pass": 3},
                        "label_review_state_counts": {"pending": 3},
                        "review": {
                            "label_review_pending_records": 3,
                            "split_leakage_unchecked_records": 3,
                            "privacy_or_consent_blocked_records": 0,
                            "quality_blocked_records": 0,
                        },
                        "review_queue": {
                            "available": True,
                            "pending_records": 3,
                            "available_actions": ["approve_for_training", "reject", "needs_changes"],
                            "sample_records": [
                                {
                                    "record_id": "cand-unit",
                                    "session_id": "session-unit",
                                    "state": "candidate",
                                    "label": "needs_help",
                                    "split_name": "unassigned",
                                    "label_review_state": "pending",
                                }
                            ],
                        },
                        "readiness": {
                            "model_training_ready": False,
                            "reason": "candidate_review_not_complete",
                            "dataset_manifest_ready": False,
                            "training_server_ready": False,
                            "on_device_deployment_ready": False,
                        },
                        "blockers": ["label_review_pending", "split_leakage_review_pending"],
                        "warnings": [],
                        "next_step": "Create the labeling/review loop.",
                        "paths": {
                            "data_flywheel_status_markdown": "reports/data_flywheel/run-a/data_flywheel_status.md"
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            summary = message_hub.load_latest_data_flywheel_status(root)

        self.assertTrue(summary["available"])
        self.assertEqual(summary["status"], "needs_review")
        self.assertEqual(summary["counts"]["records_total"], 3)
        self.assertEqual(summary["review"]["label_review_pending_records"], 3)
        self.assertEqual(summary["review_queue"]["pending_records"], 3)
        self.assertEqual(summary["review_queue"]["sample_records"][0]["record_id"], "cand-unit")
        self.assertIn("approve_for_training", summary["review_queue"]["available_actions"])
        self.assertFalse(summary["readiness"]["model_training_ready"])
        payload = json.dumps(summary)
        self.assertNotIn("training_candidates.db", payload)
        self.assertNotIn("record_json", payload)

    def test_data_flywheel_missing_returns_explainable_not_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary = message_hub.load_latest_data_flywheel_status(Path(tmp))

        self.assertFalse(summary["available"])
        self.assertEqual(summary["status"], "not_available")
        self.assertEqual(summary["reason"], "no_data_flywheel_status_report")

    def test_latest_training_experiment_summary_is_bounded_for_dashboard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_dir = root / "unit-experiment"
            report_dir.mkdir(parents=True)
            (report_dir / "training_experiment_plan.json").write_text(
                json.dumps(
                    {
                        "schema_version": "egolink.training_experiment_plan.v0.1",
                        "builder_version": "train-002.0",
                        "experiment_id": "unit-experiment",
                        "created_at": "2026-07-05T06:20:00+00:00",
                        "status": "ready_for_runner",
                        "reason": "reviewed_dataset_manifest_available",
                        "dataset": {
                            "dataset_id": "unit-dataset",
                            "manifest_status": "ready_for_training_handoff",
                            "manifest_reason": "reviewed_candidates_available",
                            "records_total": 1,
                            "eligible_records": 1,
                            "reviewed_training_candidate_records": 1,
                            "split_counts": {"train": 1},
                            "record_sample": [
                                {
                                    "record_id": "cand-unit",
                                    "session_id": "session-unit",
                                    "candidate_type": "sos_confirmation",
                                    "label": "needs_help",
                                    "split_name": "train",
                                    "source_manifest_hash": "abc123",
                                    "recording_path": "C:/private/raw/session",
                                }
                            ],
                        },
                        "model_track": {
                            "track": "motionnet",
                            "candidate_model": "motionnet-v0.1-planned",
                            "baseline_model": "m0_rule_router",
                        },
                        "runner": {
                            "integration": "not_integrated",
                            "ready_for_handoff": True,
                            "training_server_endpoint": "https://private.example.invalid",
                            "next_command": "Integrate a runner task.",
                        },
                        "metrics_plan": {
                            "classification": {
                                "accuracy": "planned_not_measured",
                                "false_positive_rate": "planned_not_measured",
                            },
                            "operations": {
                                "latency_ms": "planned_not_measured",
                                "ram_bytes": "planned_not_measured",
                                "energy_per_inference": "planned_not_measured",
                            },
                        },
                        "gates": {
                            "dataset_ready": True,
                            "privacy_review": "inherited_from_dataset_manifest",
                            "consent_review": "inherited_from_dataset_manifest",
                            "split_leakage": "inherited_from_dataset_manifest",
                            "baseline_comparison": "planned_not_run",
                            "footprint": "planned_not_measured",
                            "power": "planned_not_measured",
                            "rollback_plan": "planned_not_written",
                        },
                        "non_claims": ["No model training has run."],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (report_dir / "training_experiment_plan.md").write_text("# Plan\n", encoding="utf-8")

            summary = message_hub.load_latest_training_experiment_plan(root)

        self.assertTrue(summary["available"])
        self.assertEqual(summary["status"], "ready_for_runner")
        self.assertEqual(summary["experiment_id"], "unit-experiment")
        self.assertEqual(summary["dataset"]["eligible_records"], 1)
        self.assertTrue(summary["runner"]["ready_for_handoff"])
        self.assertEqual(summary["runner"]["integration"], "not_integrated")
        self.assertEqual(summary["metrics_plan"]["operations"]["latency_ms"], "planned_not_measured")
        self.assertEqual(summary["gates"]["baseline_comparison"], "planned_not_run")
        self.assertEqual(summary["dataset"]["record_sample"][0]["record_id"], "cand-unit")
        payload = json.dumps(summary)
        self.assertNotIn("recording_path", payload)
        self.assertNotIn("C:/private", payload)
        self.assertNotIn("private.example.invalid", payload)
        self.assertNotIn("record_json", payload)

    def test_training_experiment_missing_returns_explainable_not_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary = message_hub.load_latest_training_experiment_plan(Path(tmp))

        self.assertFalse(summary["available"])
        self.assertEqual(summary["status"], "not_available")
        self.assertEqual(summary["reason"], "no_training_experiment_plan")

    def test_latest_training_run_preflight_summary_is_bounded_for_dashboard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_dir = root / "unit-preflight"
            report_dir.mkdir(parents=True)
            (report_dir / "training_run_preflight.json").write_text(
                json.dumps(
                    {
                        "schema_version": "egolink.training_run_preflight.v0.1",
                        "builder_version": "train-003.0",
                        "run_id": "unit-preflight",
                        "created_at": "2026-07-05T11:30:00+00:00",
                        "status": "ready_for_training_runner",
                        "reason": "bounded_dataset_and_experiment_handoff_ready",
                        "experiment": {
                            "experiment_id": "unit-experiment",
                            "status": "ready_for_runner",
                            "reason": "reviewed_dataset_manifest_available",
                            "model_track": {
                                "track": "motionnet",
                                "candidate_model": "motionnet-v0.1-planned",
                                "baseline_model": "m0_rule_router",
                            },
                            "plan_ref": "training_experiment_plan.json",
                            "private_plan_path": "C:/private/training_experiment_plan.json",
                        },
                        "dataset": {
                            "dataset_id": "unit-dataset",
                            "status": "ready_for_training_handoff",
                            "reason": "reviewed_candidates_available",
                            "manifest_ref": "training_dataset_manifest.json",
                            "private_manifest_path": "C:/private/training_dataset_manifest.json",
                            "records_total": 1,
                            "eligible_records": 1,
                            "reviewed_training_candidate_records": 1,
                            "experiment_records_total": 1,
                            "split_counts": {"train": 1},
                            "label_counts": {"needs_help": 1},
                            "source_status_counts": {"synthetic_generated": 1},
                            "synthetic_records": 1,
                            "synthetic_allowed_for_dry_run": True,
                            "record_sample": [
                                {
                                    "record_id": "cand-unit",
                                    "session_id": "session-unit",
                                    "candidate_type": "uncertain",
                                    "label": "needs_help",
                                    "split_name": "train",
                                    "source_status": "synthetic_generated",
                                    "source_manifest_hash": "abc123",
                                    "recording_path": "C:/private/raw/session",
                                }
                            ],
                        },
                        "checks": {
                            "experiment_ready": True,
                            "dataset_ready": True,
                            "has_eligible_records": True,
                            "required_record_fields": "pass",
                            "missing_record_fields": {},
                            "split_counts": {"train": 1},
                            "synthetic_record_policy": "acknowledged",
                        },
                        "runner": {
                            "integration": "local_preflight_only",
                            "ready_for_training_runner": True,
                            "training_server_endpoint": "https://private.example.invalid",
                            "next_step": "Connect a runner.",
                        },
                        "metrics_plan": {
                            "planned": {"classification": {"accuracy": "planned_not_measured"}},
                            "measured": {
                                "classification": "not_run",
                                "operations": "not_run",
                                "footprint": "not_run",
                                "power": "not_run",
                            },
                        },
                        "gates": {
                            "preflight_ready": True,
                            "dataset_gate": "ready_for_training_handoff",
                            "experiment_gate": "ready_for_runner",
                            "synthetic_gate": "acknowledged",
                            "model_training": "not_run",
                            "model_evaluation": "not_run",
                            "model_artifact": "not_produced",
                            "training_server": "not_integrated",
                            "device_deployment": "not_started",
                        },
                        "next_step": "Connect a runner.",
                        "non_claims": ["No model training has run."],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (report_dir / "training_run_preflight.md").write_text("# Preflight\n", encoding="utf-8")

            summary = message_hub.load_latest_training_run_preflight(root)

        self.assertTrue(summary["available"])
        self.assertEqual(summary["status"], "ready_for_training_runner")
        self.assertEqual(summary["run_id"], "unit-preflight")
        self.assertEqual(summary["dataset"]["eligible_records"], 1)
        self.assertEqual(summary["dataset"]["synthetic_records"], 1)
        self.assertTrue(summary["runner"]["ready_for_training_runner"])
        self.assertEqual(summary["checks"]["synthetic_record_policy"], "acknowledged")
        self.assertEqual(summary["metrics_plan"]["measured"]["classification"], "not_run")
        self.assertEqual(summary["gates"]["model_artifact"], "not_produced")
        self.assertEqual(summary["dataset"]["record_sample"][0]["record_id"], "cand-unit")
        payload = json.dumps(summary)
        self.assertNotIn("recording_path", payload)
        self.assertNotIn("private_manifest_path", payload)
        self.assertNotIn("C:/private", payload)
        self.assertNotIn("private.example.invalid", payload)
        self.assertNotIn("record_json", payload)

    def test_training_run_preflight_missing_returns_explainable_not_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary = message_hub.load_latest_training_run_preflight(Path(tmp))

        self.assertFalse(summary["available"])
        self.assertEqual(summary["status"], "not_available")
        self.assertEqual(summary["reason"], "no_training_run_preflight")

    def test_latest_training_feature_manifest_summary_is_bounded_for_dashboard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_dir = root / "unit-features"
            report_dir.mkdir(parents=True)
            (report_dir / "training_feature_manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": "egolink.training_feature_manifest.v0.1",
                        "builder_version": "train-004.0",
                        "feature_set_id": "unit-features",
                        "generated_at": "2026-07-05T12:00:00+00:00",
                        "status": "ready_for_synthetic_feature_dry_run",
                        "reason": "bounded_synthetic_feature_rows_ready_for_runner_dry_run",
                        "source_refs": {
                            "dataset_manifest_ref": "training_dataset_manifest.json",
                            "private_dataset_manifest_path": "C:/private/training_dataset_manifest.json",
                        },
                        "dataset": {
                            "dataset_id": "unit-dataset",
                            "status": "ready_for_training_handoff",
                            "reason": "reviewed_candidates_available",
                            "records_total": 1,
                            "eligible_records": 1,
                            "reviewed_training_candidate_records": 1,
                            "split_counts": {"train": 1},
                            "label_counts": {"needs_help": 1},
                            "source_status_counts": {"synthetic_generated": 1},
                            "synthetic_records": 1,
                            "synthetic_allowed_for_dry_run": True,
                            "recording_path": "C:/private/raw/session",
                        },
                        "preflight": {
                            "run_id": "unit-preflight",
                            "status": "ready_for_training_runner",
                            "reason": "bounded_dataset_and_experiment_handoff_ready",
                            "dataset_id": "unit-dataset",
                            "runner_ready": True,
                            "metrics_measured": {
                                "classification": "not_run",
                                "operations": "not_run",
                                "power": "not_run",
                            },
                            "training_server_endpoint": "https://private.example.invalid",
                        },
                        "feature_rows": {
                            "row_schema_version": "egolink.training_feature_row.v0.1",
                            "row_count": 1,
                            "rows_ref": "training_feature_rows.jsonl",
                            "feature_groups": ["imu_motion"],
                            "feature_scope": "manifest_summary_features",
                            "target_separated_from_features": True,
                            "row_sample": [{"raw_payload": "secret"}],
                        },
                        "checks": {
                            "dataset_ready": True,
                            "preflight_ready": True,
                            "source_match": True,
                            "has_records": True,
                            "required_record_fields": "pass",
                            "missing_record_fields": {},
                            "synthetic_record_policy": "acknowledged",
                            "label_leakage_guard": "target_separated_from_features",
                        },
                        "gates": {
                            "feature_export": "pass",
                            "training_runner": "not_integrated",
                            "model_training": "not_run",
                            "model_evaluation": "not_run",
                            "model_artifact": "not_produced",
                            "training_server": "not_integrated",
                            "device_deployment": "not_started",
                        },
                        "paths": {
                            "training_feature_manifest_json": "training_feature_manifest.json",
                            "training_feature_rows_jsonl": "C:/private/training_feature_rows.jsonl",
                        },
                        "next_step": "Dry-run only.",
                        "non_claims": ["No model training has run."],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (report_dir / "training_feature_manifest.md").write_text("# Feature Manifest\n", encoding="utf-8")

            summary = message_hub.load_latest_training_feature_manifest(root)

        self.assertTrue(summary["available"])
        self.assertEqual(summary["status"], "ready_for_synthetic_feature_dry_run")
        self.assertEqual(summary["feature_set_id"], "unit-features")
        self.assertEqual(summary["dataset"]["eligible_records"], 1)
        self.assertEqual(summary["preflight"]["run_id"], "unit-preflight")
        self.assertTrue(summary["preflight"]["runner_ready"])
        self.assertEqual(summary["feature_rows"]["row_count"], 1)
        self.assertEqual(summary["feature_rows"]["feature_scope"], "manifest_summary_features")
        self.assertTrue(summary["feature_rows"]["target_separated_from_features"])
        self.assertEqual(summary["checks"]["label_leakage_guard"], "target_separated_from_features")
        self.assertEqual(summary["gates"]["model_artifact"], "not_produced")
        payload = json.dumps(summary)
        self.assertNotIn("recording_path", payload)
        self.assertNotIn("private_dataset_manifest_path", payload)
        self.assertNotIn("row_sample", payload)
        self.assertNotIn("raw_payload", payload)
        self.assertNotIn("C:/private", payload)
        self.assertNotIn("private.example.invalid", payload)

    def test_training_feature_manifest_missing_returns_explainable_not_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary = message_hub.load_latest_training_feature_manifest(Path(tmp))

        self.assertFalse(summary["available"])
        self.assertEqual(summary["status"], "not_available")
        self.assertEqual(summary["reason"], "no_training_feature_manifest")

    def test_latest_training_runner_dry_run_summary_is_bounded_for_dashboard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_dir = root / "unit-runner"
            report_dir.mkdir(parents=True)
            (report_dir / "training_runner_dry_run.json").write_text(
                json.dumps(
                    {
                        "schema_version": "egolink.training_runner_dry_run.v0.1",
                        "builder_version": "train-005.0",
                        "run_id": "unit-runner",
                        "created_at": "2026-07-05T12:45:00+00:00",
                        "status": "synthetic_runner_dry_run_complete",
                        "reason": "runner_input_contract_validated_with_synthetic_dry_run_rows",
                        "feature_manifest": {
                            "feature_set_id": "unit-features",
                            "status": "ready_for_synthetic_feature_dry_run",
                            "reason": "bounded_synthetic_feature_rows_ready_for_runner_dry_run",
                            "feature_scope": "manifest_summary_features",
                            "target_separated_from_features": True,
                            "private_manifest_path": "C:/private/training_feature_manifest.json",
                        },
                        "dataset": {
                            "dataset_id": "unit-dataset",
                            "status": "ready_for_training_handoff",
                            "eligible_records": 1,
                            "synthetic_records": 1,
                            "recording_path": "C:/private/raw/session",
                        },
                        "preflight": {
                            "run_id": "unit-preflight",
                            "status": "ready_for_training_runner",
                            "runner_ready": True,
                            "metrics_measured": {
                                "classification": "not_run",
                                "operations": "not_run",
                                "power": "not_run",
                            },
                            "training_server_endpoint": "https://private.example.invalid",
                        },
                        "feature_rows": {
                            "expected_row_count": 1,
                            "actual_row_count": 1,
                            "row_count_matches": True,
                            "feature_set_mismatch_count": 0,
                            "split_counts": {"train": 1},
                            "label_counts": {"needs_help": 1},
                            "source_status_counts": {"synthetic_generated": 1},
                            "feature_group_counts": {"imu_motion": 1},
                            "synthetic_rows": 1,
                            "synthetic_allowed_for_dry_run": True,
                            "row_sample": [{"raw_payload": "secret"}],
                        },
                        "checks": {
                            "feature_manifest_ready": True,
                            "feature_rows_readable": True,
                            "row_count_matches": True,
                            "required_row_fields": "pass",
                            "missing_row_fields": {},
                            "target_leakage_guard": "pass",
                            "target_leakage_violations": {},
                            "synthetic_row_policy": "acknowledged",
                            "manifest_feature_export_gate": "pass",
                        },
                        "runner": {
                            "integration": "local_runner_dry_run",
                            "ready_for_real_runner": False,
                            "dry_run_only": True,
                            "training_server_endpoint": "https://private.example.invalid",
                            "next_step": "Dry-run only.",
                        },
                        "metrics_plan": {
                            "measured": {
                                "classification": "not_run",
                                "operations": "not_run",
                                "power": "not_run",
                            },
                            "dry_run_summary": {
                                "labels": {"needs_help": 1},
                                "splits": {"train": 1},
                                "feature_groups": {"imu_motion": 1},
                            },
                        },
                        "gates": {
                            "runner_input": "pass",
                            "model_training": "not_run",
                            "model_evaluation": "not_run",
                            "model_artifact": "not_produced",
                            "training_server": "not_integrated",
                            "device_deployment": "not_started",
                        },
                        "paths": {
                            "training_runner_dry_run_json": "training_runner_dry_run.json",
                            "private_artifact_path": "C:/private/model.bin",
                        },
                        "next_step": "Dry-run only.",
                        "non_claims": ["No model training has run."],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (report_dir / "training_runner_dry_run.md").write_text("# Runner Dry-Run\n", encoding="utf-8")

            summary = message_hub.load_latest_training_runner_dry_run(root)

        self.assertTrue(summary["available"])
        self.assertEqual(summary["status"], "synthetic_runner_dry_run_complete")
        self.assertEqual(summary["run_id"], "unit-runner")
        self.assertEqual(summary["feature_manifest"]["feature_set_id"], "unit-features")
        self.assertEqual(summary["feature_rows"]["actual_row_count"], 1)
        self.assertEqual(summary["feature_rows"]["label_counts"], {"needs_help": 1})
        self.assertTrue(summary["runner"]["dry_run_only"])
        self.assertEqual(summary["checks"]["target_leakage_guard"], "pass")
        self.assertEqual(summary["metrics_plan"]["measured"]["classification"], "not_run")
        self.assertEqual(summary["gates"]["model_artifact"], "not_produced")
        payload = json.dumps(summary)
        self.assertNotIn("recording_path", payload)
        self.assertNotIn("private_manifest_path", payload)
        self.assertNotIn("row_sample", payload)
        self.assertNotIn("raw_payload", payload)
        self.assertNotIn("private_artifact_path", payload)
        self.assertNotIn("C:/private", payload)
        self.assertNotIn("private.example.invalid", payload)

    def test_training_runner_dry_run_missing_returns_explainable_not_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary = message_hub.load_latest_training_runner_dry_run(Path(tmp))

        self.assertFalse(summary["available"])
        self.assertEqual(summary["status"], "not_available")
        self.assertEqual(summary["reason"], "no_training_runner_dry_run")

    def test_latest_training_baseline_eval_summary_is_bounded_for_dashboard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_dir = root / "unit-eval"
            report_dir.mkdir()
            (report_dir / "training_baseline_eval.json").write_text(
                json.dumps(
                    {
                        "schema_version": "egolink.training_baseline_eval.v0.1",
                        "eval_id": "unit-eval",
                        "created_at": "2026-07-06T00:30:00+00:00",
                        "status": "synthetic_baseline_eval_complete",
                        "reason": "synthetic_rows_evaluated_for_runner_integration_only",
                        "feature_manifest": {
                            "feature_set_id": "unit-features",
                            "status": "ready_for_synthetic_feature_dry_run",
                            "feature_scope": "manifest_summary_features",
                            "target_separated_from_features": True,
                        },
                        "runner_dry_run": {
                            "run_id": "unit-runner",
                            "status": "synthetic_runner_dry_run_complete",
                            "runner_input_gate": "pass",
                            "dry_run_only": True,
                        },
                        "dataset": {
                            "dataset_id": "unit-dataset",
                            "status": "ready_for_training_handoff",
                            "eligible_records": 1,
                            "synthetic_records": 1,
                        },
                        "feature_rows": {
                            "expected_row_count": 1,
                            "actual_row_count": 1,
                            "row_count_matches": True,
                            "runner_actual_row_count": 1,
                            "runner_row_count_matches": True,
                            "split_counts": {"test": 1},
                            "label_counts": {"needs_help": 1},
                            "risk_type_counts": {"uncertain": 1},
                            "candidate_type_counts": {"uncertain": 1},
                            "source_status_counts": {"synthetic_generated": 1},
                            "synthetic_rows": 1,
                            "synthetic_allowed_for_eval": True,
                            "row_sample": [{"private": "do-not-expose"}],
                        },
                        "checks": {
                            "feature_manifest_ready": True,
                            "runner_dry_run_ready": True,
                            "feature_rows_readable": True,
                            "row_count_matches": True,
                            "required_row_fields": "pass",
                            "missing_row_fields": {},
                            "target_leakage_guard": "pass",
                            "target_leakage_violations": {},
                            "synthetic_row_policy": "acknowledged",
                        },
                        "metrics": {
                            "scope": "synthetic_integration_only",
                            "measured_from_rows": True,
                            "classification": {
                                "baselines": [
                                    {
                                        "name": "candidate_type_risk_baseline",
                                        "overall": {"total": 1, "correct": 1, "accuracy": 1.0},
                                        "private_case_rows": [{"row_id": "secret"}],
                                    }
                                ],
                                "product_performance_claim": False,
                                "release_metric": False,
                            },
                            "operations": "not_run",
                            "footprint": "not_run",
                            "power": "not_run",
                        },
                        "gates": {
                            "baseline_evaluation": "pass",
                            "model_training": "not_run",
                            "model_artifact": "not_produced",
                            "model_card": "not_produced",
                            "training_server": "not_integrated",
                            "model_registry": "not_integrated",
                            "device_deployment": "not_started",
                            "release_claim": "not_allowed",
                        },
                        "source_refs": {
                            "feature_rows_ref": "training_feature_rows.jsonl",
                            "private_training_endpoint": "https://private.example.invalid",
                        },
                        "private_artifact_path": "C:/private/model.bin",
                        "non_claims": ["Synthetic baseline metrics are integration metrics only."],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (report_dir / "training_baseline_eval.md").write_text("# Baseline Eval\n", encoding="utf-8")

            summary = message_hub.load_latest_training_baseline_eval(root)

        self.assertTrue(summary["available"])
        self.assertEqual(summary["status"], "synthetic_baseline_eval_complete")
        self.assertEqual(summary["eval_id"], "unit-eval")
        self.assertEqual(summary["feature_rows"]["actual_row_count"], 1)
        self.assertEqual(summary["feature_rows"]["risk_type_counts"], {"uncertain": 1})
        self.assertEqual(summary["checks"]["synthetic_row_policy"], "acknowledged")
        self.assertEqual(summary["metrics"]["scope"], "synthetic_integration_only")
        self.assertEqual(summary["metrics"]["classification"]["baselines"][0]["overall"]["accuracy"], 1.0)
        self.assertFalse(summary["metrics"]["classification"]["product_performance_claim"])
        self.assertEqual(summary["gates"]["model_artifact"], "not_produced")
        self.assertEqual(summary["gates"]["release_claim"], "not_allowed")
        payload = json.dumps(summary)
        self.assertNotIn("row_sample", payload)
        self.assertNotIn("private_case_rows", payload)
        self.assertNotIn("private_artifact_path", payload)
        self.assertNotIn("C:/private", payload)
        self.assertNotIn("private.example.invalid", payload)

    def test_training_baseline_eval_missing_returns_explainable_not_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary = message_hub.load_latest_training_baseline_eval(Path(tmp))

        self.assertFalse(summary["available"])
        self.assertEqual(summary["status"], "not_available")
        self.assertEqual(summary["reason"], "no_training_baseline_eval")

    def test_latest_d1_labeling_intake_summary_is_bounded_for_dashboard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_dir = root / "unit-intake"
            report_dir.mkdir()
            (report_dir / "d1_labeling_intake.json").write_text(
                json.dumps(
                    {
                        "schema_version": "egolink.d1_labeling_intake.v0.1",
                        "run_id": "unit-intake",
                        "generated_at": "2026-07-06T11:35:00+00:00",
                        "serves_demo": "D5",
                        "status": "pending_human_review",
                        "reason": "d1_run_waiting_for_label_privacy_consent_and_split_review",
                        "source_readiness": {
                            "run_id": "unit-readiness",
                            "status": "ready_for_labeling_review",
                            "reason": "field_observation_can_enter_human_review_but_not_training",
                            "report_path": "reports/d1_training_readiness/unit/d1_training_readiness.json",
                        },
                        "source_observation": {
                            "run_id": "field-private",
                            "status": "completed",
                            "result": "PASS",
                            "device_id": "ego-link-r1-connectivity-001",
                            "sample_count": 5,
                            "successful_sample_count": 5,
                            "latest_seq": 52,
                            "max_freshness_s": 62,
                            "last_location_upload_at": "2026-07-06T11:20:18+00:00",
                            "samples_jsonl_read": False,
                            "coordinate_values_copied": False,
                            "lat": 31.123456,
                            "lon": 121.654321,
                        },
                        "evidence_coverage": {
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
                                "raw_location": {"lat": 31.123456, "lon": 121.654321},
                            },
                            "sensors": {
                                "imu_evidence_statuses": ["mock"],
                                "power_evidence_statuses": ["measured"],
                                "power_measured_seen": True,
                                "real_imu_seen": False,
                            },
                        },
                        "intake_queue": {
                            "available": True,
                            "pending_items": 1,
                            "next_queue": "training_candidate_store_after_review",
                            "items": [
                                {
                                    "intake_id": "d1-intake-unit",
                                    "source_run_id": "field-private",
                                    "readiness_run_id": "unit-readiness",
                                    "device_id": "ego-link-r1-connectivity-001",
                                    "status": "pending_label_privacy_split",
                                    "training_allowed": False,
                                    "candidate_record_written": False,
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
                                        "private_coordinates": [31.123456, 121.654321],
                                    },
                                    "requested_actions": ["attach_operator_or_user_label"],
                                    "available_decisions": ["needs_more_capture", "ready_for_candidate_store"],
                                    "raw_payload": {"secret": True},
                                }
                            ],
                        },
                        "labeling_request": {
                            "taxonomy_version": "d1_location_review.v0.1",
                            "requested_label_groups": ["collection_context", "location_quality"],
                            "free_text_policy": "redacted_or_absent",
                            "exact_coordinates_visible": False,
                            "raw_payload_visible": False,
                        },
                        "review_gates": {
                            "training_readiness": "pass",
                            "operator_label": "blocked",
                            "privacy_review": "blocked",
                            "candidate_store": "not_written",
                            "model_training": "not_run",
                        },
                        "blockers": ["operator_label_missing", "privacy_review_required"],
                        "scope": {
                            "training_readiness_report_read": True,
                            "sample_jsonl_read": False,
                            "hardware_contacted": False,
                            "candidate_db_written": False,
                            "model_training_started": False,
                            "model_artifact_written": False,
                            "exact_coordinates_copied": False,
                            "release_claim_allowed": False,
                        },
                        "paths": {
                            "d1_labeling_intake_json": "reports/d1_labeling_intake/unit/d1_labeling_intake.json",
                            "private_candidate_db": "C:/private/training_candidates.db",
                        },
                        "raw_payload": {"private": True},
                        "features": {"private": "do-not-expose"},
                        "target": {"private": "do-not-expose"},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (report_dir / "d1_labeling_intake.md").write_text("# D1 Intake\n", encoding="utf-8")

            summary = message_hub.load_latest_d1_labeling_intake(root)

        self.assertTrue(summary["available"])
        self.assertEqual(summary["status"], "pending_human_review")
        self.assertEqual(summary["run_id"], "unit-intake")
        self.assertEqual(summary["intake_queue"]["pending_items"], 1)
        self.assertEqual(summary["intake_queue"]["items"][0]["intake_id"], "d1-intake-unit")
        self.assertFalse(summary["intake_queue"]["items"][0]["training_allowed"])
        self.assertFalse(summary["intake_queue"]["items"][0]["candidate_record_written"])
        self.assertEqual(summary["review_gates"]["candidate_store"], "not_written")
        self.assertFalse(summary["scope"]["sample_jsonl_read"])
        self.assertFalse(summary["scope"]["candidate_db_written"])
        self.assertFalse(summary["scope"]["exact_coordinates_copied"])
        self.assertEqual(summary["labeling_request"]["requested_label_groups"], ["collection_context", "location_quality"])
        payload = json.dumps(summary)
        self.assertNotIn("31.123456", payload)
        self.assertNotIn("121.654321", payload)
        self.assertNotIn("raw_payload", payload)
        self.assertNotIn("features", payload)
        self.assertNotIn("target", payload)
        self.assertNotIn("private_candidate_db", payload)
        self.assertNotIn("C:/private", payload)

    def test_d1_labeling_intake_missing_returns_explainable_not_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary = message_hub.load_latest_d1_labeling_intake(Path(tmp))

        self.assertFalse(summary["available"])
        self.assertEqual(summary["status"], "not_available")
        self.assertEqual(summary["reason"], "no_d1_labeling_intake")

    def test_deploy_script_can_include_curated_field_report_summaries(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        script = (repo_root / "scripts" / "deploy_message_hub_vps.ps1").read_text(encoding="utf-8")

        self.assertIn("IncludeFieldReportSummaries", script)
        self.assertIn("IncludeDataFlywheelSummaries", script)
        self.assertIn("IncludeTrainingExperimentSummaries", script)
        self.assertIn("IncludeTrainingRunSummaries", script)
        self.assertIn("IncludeTrainingFeatureSummaries", script)
        self.assertIn("IncludeTrainingRunnerDryRunSummaries", script)
        self.assertIn("IncludeTrainingBaselineEvalSummaries", script)
        self.assertIn("IncludeTrainingHandoffSummaries", script)
        self.assertIn("IncludeTrainingJobSummaries", script)
        self.assertIn("IncludeSyntheticTrainingChainSummaries", script)
        self.assertIn("IncludeD1TrainingReadinessSummaries", script)
        self.assertIn("IncludeD1LabelingIntakeSummaries", script)
        self.assertIn("Copy-FieldReportSummaries", script)
        self.assertIn("Copy-DataFlywheelSummaries", script)
        self.assertIn("Copy-TrainingExperimentSummaries", script)
        self.assertIn("Copy-TrainingRunSummaries", script)
        self.assertIn("Copy-TrainingFeatureSummaries", script)
        self.assertIn("Copy-TrainingRunnerDryRunSummaries", script)
        self.assertIn("Copy-TrainingBaselineEvalSummaries", script)
        self.assertIn("Copy-TrainingHandoffSummaries", script)
        self.assertIn("Copy-TrainingJobSummaries", script)
        self.assertIn("Copy-SyntheticTrainingChainSummaries", script)
        self.assertIn("Copy-D1TrainingReadinessSummaries", script)
        self.assertIn("Copy-D1LabelingIntakeSummaries", script)
        self.assertIn("d1_web_api_report.json", script)
        self.assertIn("d1_field_companion_summary.json", script)
        self.assertIn("d1_field_observation_report.json", script)
        self.assertIn("d1_field_observation_report.md", script)
        self.assertIn("d1_field_observation_status.json", script)
        self.assertIn("data_flywheel_status.json", script)
        self.assertIn("data_flywheel_status.md", script)
        self.assertIn("training_experiment_plan.json", script)
        self.assertIn("training_experiment_plan.md", script)
        self.assertIn("training_run_preflight.json", script)
        self.assertIn("training_run_preflight.md", script)
        self.assertIn("training_feature_manifest.json", script)
        self.assertIn("training_feature_manifest.md", script)
        self.assertNotIn("training_feature_rows.jsonl", script)
        self.assertIn("training_runner_dry_run.json", script)
        self.assertIn("training_runner_dry_run.md", script)
        self.assertIn("training_baseline_eval.json", script)
        self.assertIn("training_baseline_eval.md", script)
        self.assertIn("training_handoff_bundle.json", script)
        self.assertIn("training_handoff_bundle.md", script)
        self.assertIn("training_job_plan.json", script)
        self.assertIn("training_job_plan.md", script)
        self.assertIn("synthetic_training_chain.json", script)
        self.assertIn("synthetic_training_chain.md", script)
        self.assertIn("d1_training_readiness.json", script)
        self.assertIn("d1_training_readiness.md", script)
        self.assertIn("d1_labeling_intake.json", script)
        self.assertIn("d1_labeling_intake.md", script)
        self.assertIn("*.summary.json", script)
        self.assertNotIn("*.jsonl", script)
        self.assertNotIn("d1_field_samples.jsonl", script)
        self.assertNotIn("*.db", script)

    def test_latest_product_demo_report_summary_is_bounded_for_dashboard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_dir = root / "run-a"
            report_dir.mkdir()
            (report_dir / "product_demo_report.json").write_text(
                """
{
  "demo": {"candidate": "KR-008 / DEMO-008 Product Demo Closed Loop", "mode": "offline_evidence_composition", "product_ready": false},
  "source": {"test_run_id": "lte011-unit", "safety_session_id": "demo-unit", "evidence_mode": "composite_existing_evidence", "dataset_samples": 1},
  "result": {"status": "warn", "ready_for_kr008_release": false, "warnings": ["web_console_product_demo_review_pending"], "errors": [], "why_not_release_ready": ["web_console_product_demo_review_pending"]},
  "location": {"state": "Unknown", "gnss_fix": false, "gnss_state": "no_fix", "belief_reason": "cell_observation_without_position_fix"},
  "flow_order": ["report_export", "web_console_replay_review"],
  "flow": {
    "report_export": {"status": "pass", "summary": "report exported"},
    "web_console_replay_review": {"status": "not_run", "summary": "pending"}
  },
  "evidence_summary": {"flow_status_counts": {"pass": 7, "not_run": 1}, "feature_groups": ["gnss", "cell", "lte"], "raw_frame_refs": 3, "derived_event_refs": 2, "training_readiness": {"model_training_ready": false, "reason": "not_ready"}, "release_gate_usage": {"can_support_release_review": true}},
  "paths": {"product_demo_report_json": "reports/product_demo/run-a/product_demo_report.json", "product_demo_report_markdown": "reports/product_demo/run-a/product_demo_report.md"},
  "next_gates": ["Expose through Dashboard"],
  "non_claims": ["No product readiness claim."]
}
""".strip()
                + "\n",
                encoding="utf-8",
            )

            summary = message_hub.load_latest_product_demo_report(root)

        self.assertTrue(summary["available"])
        self.assertEqual(summary["status"], "warn")
        self.assertEqual(summary["candidate"], "KR-008 / DEMO-008 Product Demo Closed Loop")
        self.assertEqual(summary["evidence_mode"], "composite_existing_evidence")
        self.assertFalse(summary["ready_for_kr008_release"])
        self.assertEqual(summary["flow"]["web_console_replay_review"]["status"], "not_run")
        self.assertEqual(summary["location"]["state"], "Unknown")
        self.assertEqual(summary["raw_frame_refs"], 3)

    def test_product_demo_report_missing_returns_explainable_not_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary = message_hub.load_latest_product_demo_report(Path(tmp))

        self.assertFalse(summary["available"])
        self.assertEqual(summary["status"], "not_available")
        self.assertEqual(summary["reason"], "no_product_demo_report")

    def test_state_api_includes_recent_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            store.create_command("ego-link-001", {"cmd": "set_report_interval"})

            commands = store.recent_commands()

        self.assertEqual(commands[0]["cmd"], "set_report_interval")
        self.assertEqual(commands[0]["status"], "pending")

    def test_state_api_raw_frames_are_redacted_and_explainable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            raw = message_hub.build_raw_frame("event", "raw-dashboard-test", b"event_type=dashboard_smoke\n")
            record = store.ingest_raw_frame("ego-link-001", raw)
            raw_frames = store.recent_raw_frames()

        self.assertEqual(record["parse_result"]["status"], "ok")
        self.assertEqual(raw_frames[0]["parse_result"]["status"], "ok")
        self.assertEqual(raw_frames[0]["parse_result"]["derived_message_type"], "event")
        self.assertTrue(raw_frames[0]["raw_payload"]["data_redacted"])
        self.assertNotIn("data", raw_frames[0]["raw_payload"])


if __name__ == "__main__":
    unittest.main()

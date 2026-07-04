from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
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
        self.assertIn("D1 Link Through", html)
        self.assertIn("dashboard-shell", html)
        self.assertIn("Field live view", html)
        self.assertIn("runContext", html)
        self.assertIn("rawFrames", html)
        self.assertIn("productDemo", html)
        self.assertIn("fieldResults", html)
        self.assertIn("dataFlywheel", html)
        self.assertIn("d1Link", html)
        self.assertIn("d1_link", html)
        self.assertIn("field_results", html)
        self.assertIn("data_flywheel", html)
        self.assertIn("dataFlywheelPanel", html)
        self.assertIn("Candidate Records", html)
        self.assertIn("Training Gate", html)
        self.assertIn("Review Queues", html)
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

            summary = message_hub.load_latest_field_results(root)

        self.assertTrue(summary["available"])
        self.assertEqual(summary["status"], "pass")
        self.assertEqual(summary["report_count"], 3)
        kinds = {item["kind"] for item in summary["reports"]}
        self.assertEqual(kinds, {"d1_web_api", "amoled_status", "d1_field_companion"})
        amoled = next(item for item in summary["reports"] if item["kind"] == "amoled_status")
        self.assertNotIn("jsonl_path", json.dumps(amoled))
        self.assertEqual(amoled["metrics"]["command_ack_count"], 1)

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

    def test_deploy_script_can_include_curated_field_report_summaries(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        script = (repo_root / "scripts" / "deploy_message_hub_vps.ps1").read_text(encoding="utf-8")

        self.assertIn("IncludeFieldReportSummaries", script)
        self.assertIn("IncludeDataFlywheelSummaries", script)
        self.assertIn("Copy-FieldReportSummaries", script)
        self.assertIn("Copy-DataFlywheelSummaries", script)
        self.assertIn("d1_web_api_report.json", script)
        self.assertIn("d1_field_companion_summary.json", script)
        self.assertIn("data_flywheel_status.json", script)
        self.assertIn("data_flywheel_status.md", script)
        self.assertIn("*.summary.json", script)
        self.assertNotIn("*.jsonl", script)
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

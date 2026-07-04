from __future__ import annotations

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
        self.assertIn("D1 Link Through", html)
        self.assertIn("runContext", html)
        self.assertIn("rawFrames", html)
        self.assertIn("productDemo", html)
        self.assertIn("d1Link", html)
        self.assertIn("d1_link", html)
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

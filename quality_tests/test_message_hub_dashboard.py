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
        self.assertIn("runContext", html)
        self.assertIn("rawFrames", html)
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

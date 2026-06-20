from __future__ import annotations

import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import pc_simulator.app as app


class PcSimulatorTests(unittest.TestCase):
    def setUp(self) -> None:
        app.STATE = app.DeviceState(last_seen_at=app.utc_now())
        app.EVENTS.clear()

    def test_events_increment_seq_and_update_snapshot(self) -> None:
        heartbeat = app.heartbeat()
        location = app.location_report()
        wake = app.wake_detected()

        self.assertEqual(heartbeat["seq"], 1)
        self.assertEqual(location["seq"], 2)
        self.assertEqual(wake["seq"], 3)
        self.assertEqual(app.snapshot()["device"]["seq"], 3)
        self.assertEqual(app.snapshot()["events"][0]["event_type"], "wake_detected")

    def test_sos_event_is_critical(self) -> None:
        event = app.sos_pressed()

        self.assertEqual(event["event_type"], "sos_pressed")
        self.assertEqual(event["priority"], "critical")

    def test_event_log_is_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "events.jsonl"
            with patch.object(app, "EVENT_LOG", log_path), patch.object(app, "RUNTIME_DIR", Path(tmp)):
                event = app.command_sent("play_prompt", "test")

            line = log_path.read_text(encoding="utf-8").strip()
            self.assertIn('"event_type":"command_sent"', line)
            self.assertIn(event["device_id"], line)


if __name__ == "__main__":
    unittest.main()

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
        self.runtime = tempfile.TemporaryDirectory()
        self.addCleanup(self.runtime.cleanup)
        runtime_path = Path(self.runtime.name)
        runtime_patch = patch.object(app, "RUNTIME_DIR", runtime_path)
        event_log_patch = patch.object(app, "EVENT_LOG", runtime_path / "events.jsonl")
        runtime_patch.start()
        event_log_patch.start()
        self.addCleanup(runtime_patch.stop)
        self.addCleanup(event_log_patch.stop)

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

    def test_snapshot_reads_mqtt_status_from_event_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "events.jsonl"
            app.event_store.append_jsonl(
                log_path,
                {
                    "protocol_version": "egolink.p0.v1",
                    "device_id": "ego-link-001",
                    "ts": "uptime_ms:12345",
                    "seq": 42,
                    "message_type": "status",
                    "event_type": "mqtt_status",
                    "battery": 76,
                    "link_type": "mock_4g_over_wifi",
                    "rssi": -55,
                    "guard_mode": "child_safety",
                    "queue_size": 3,
                    "mqtt_topic": "ego/link/ego-link-001/status",
                    "ingest_source": "pc_simulator.mqtt_worker",
                    "received_at": "2026-06-20T09:26:52+00:00",
                },
            )

            with patch.object(app, "EVENT_LOG", log_path), patch.object(app, "RUNTIME_DIR", Path(tmp)):
                data = app.snapshot()

        self.assertEqual(data["device"]["seq"], 42)
        self.assertEqual(data["device"]["battery"], 76)
        self.assertEqual(data["device"]["rssi"], -55)
        self.assertEqual(data["device"]["queue_size"], 3)
        self.assertEqual(data["device"]["last_seen_source"], "mqtt")
        self.assertEqual(data["events"][0]["event_type"], "mqtt_status")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import tempfile
import threading
from pathlib import Path
import urllib.request
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

    def test_snapshot_includes_mqtt_event_and_ack_from_event_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "events.jsonl"
            app.event_store.append_jsonl(
                log_path,
                {
                    "protocol_version": "egolink.p0.v1",
                    "device_id": "ego-link-001",
                    "ts": "2026-06-20T10:01:00+00:00",
                    "seq": 50,
                    "message_type": "event",
                    "event_type": "wake_detected",
                    "priority": "normal",
                    "keyword": "Ego",
                    "mqtt_topic": "ego/link/ego-link-001/event",
                    "ingest_source": "pc_simulator.mqtt_worker",
                    "received_at": "2026-06-20T10:01:01+00:00",
                },
            )
            app.event_store.append_jsonl(
                log_path,
                {
                    "protocol_version": "egolink.p0.v1",
                    "device_id": "ego-link-001",
                    "ts": "2026-06-20T10:01:02+00:00",
                    "seq": 51,
                    "message_type": "ack",
                    "event_type": "mqtt_ack",
                    "cmd_id": "cmd-0001",
                    "status": "ok",
                    "mqtt_topic": "ego/link/ego-link-001/ack",
                    "ingest_source": "pc_simulator.mqtt_worker",
                    "received_at": "2026-06-20T10:01:03+00:00",
                },
            )

            with patch.object(app, "EVENT_LOG", log_path), patch.object(app, "RUNTIME_DIR", Path(tmp)):
                data = app.snapshot()

        self.assertEqual([event["event_type"] for event in data["events"][:2]], ["mqtt_ack", "wake_detected"])
        self.assertEqual(data["events"][0]["cmd_id"], "cmd-0001")
        self.assertEqual(data["events"][1]["keyword"], "Ego")

    def test_snapshot_applies_location_report_from_event_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "events.jsonl"
            app.event_store.append_jsonl(
                log_path,
                {
                    "protocol_version": "egolink.p0.v1",
                    "device_id": "ego-link-001",
                    "ts": "2026-06-21T01:09:00+00:00",
                    "seq": 59,
                    "message_type": "status",
                    "event_type": "mqtt_status",
                    "battery": 76,
                    "link_type": "mock_4g_over_wifi",
                    "rssi": -55,
                    "guard_mode": "child_safety",
                    "gnss_state": "mock_fix",
                    "queue_size": 3,
                    "received_at": "2026-06-21T01:09:01+00:00",
                },
            )
            app.event_store.append_jsonl(
                log_path,
                {
                    "protocol_version": "egolink.p0.v1",
                    "device_id": "ego-link-001",
                    "ts": "2026-06-21T01:10:00+00:00",
                    "seq": 60,
                    "message_type": "event",
                    "event_type": "location_report",
                    "priority": "normal",
                    "source": "sim7670g_gnss",
                    "fix": True,
                    "gnss_state": "fix",
                    "lat": 31.222177,
                    "lon": 121.354376,
                    "received_at": "2026-06-21T01:10:01+00:00",
                },
            )

            with patch.object(app, "EVENT_LOG", log_path), patch.object(app, "RUNTIME_DIR", Path(tmp)):
                data = app.snapshot()

        self.assertEqual(data["device"]["lat"], 31.222177)
        self.assertEqual(data["device"]["lon"], 121.354376)
        self.assertEqual(data["device"]["gnss_state"], "fix")
        self.assertEqual(data["device"]["last_seen_source"], "sim7670g_gnss")

    def test_snapshot_includes_safety_companion_output(self) -> None:
        event = app.sos_pressed()
        data = app.snapshot()

        self.assertEqual(event["event_type"], "sos_pressed")
        self.assertEqual(data["safety_companion"]["sensor_frame"]["metadata"]["source_event_type"], "sos_pressed")
        self.assertEqual(data["safety_companion"]["model_output"]["risk_type"], "manual_sos")
        self.assertEqual(data["safety_companion"]["model_output"]["recommended_action"], "urgent_escalation")
        self.assertEqual(data["safety_companion"]["safety_event"]["event_type"], "manual_sos")

    def test_safety_evaluate_endpoint_accepts_model_input(self) -> None:
        scenarios_path = (
            Path(__file__).resolve().parents[1]
            / "model_lab"
            / "safety_companion"
            / "datasets"
            / "samples"
            / "scenario_suite.json"
        )
        scenarios = {item["id"]: item for item in json.loads(scenarios_path.read_text(encoding="utf-8"))}
        server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.SimulatorHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            body = json.dumps({"model_input": scenarios["manual_sos"]["input"]}).encode("utf-8")
            request = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/api/safety/evaluate",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["input_type"], "model_input")
        self.assertEqual(payload["model_output"]["risk_type"], "manual_sos")
        self.assertEqual(payload["model_output"]["recommended_action"], "urgent_escalation")
        self.assertEqual(payload["base_command"]["command"], "ask_user")

    def test_safety_replay_endpoint_persists_events_and_simulated_commands(self) -> None:
        server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.SimulatorHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            request = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/api/safety/replay",
                data=b"",
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["summary"], {"total": 4, "safety_events": 3, "base_commands": 3})
        self.assertEqual(len(payload["persisted_events"]), 6)
        event_types = [event["event_type"] for event in payload["persisted_events"]]
        self.assertEqual(event_types.count("safety_event"), 3)
        self.assertEqual(event_types.count("command_sent"), 3)
        commands = [event["base_command"] for event in payload["persisted_events"] if event["event_type"] == "command_sent"]
        self.assertEqual({command["command"] for command in commands}, {"ask_user"})
        for command in commands:
            self.assertTrue(command["args"]["no_external_side_effects"])

    def test_dashboard_renders_safety_event_detail_logic(self) -> None:
        html = app.render_dashboard()

        self.assertIn("safety_event", html)
        self.assertIn("evidence_request", html)
        self.assertIn("privacy mode", html)

    def test_dashboard_renders_sensor_sample_detail_logic(self) -> None:
        html = app.render_dashboard()

        self.assertIn("eventDetail(e)", html)
        self.assertIn("sensor_sample", html)
        self.assertIn("wifi_rssi", html)
        self.assertIn("free_heap_bytes", html)
        self.assertIn("safety_risk", html)

    def test_dashboard_renders_location_report_detail_logic(self) -> None:
        html = app.render_dashboard()

        self.assertIn("location_report", html)
        self.assertIn("GNSS no fix", html)
        self.assertIn("satellites", html)


if __name__ == "__main__":
    unittest.main()

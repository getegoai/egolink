from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from pc_simulator import live_safety_demo, session_inspector
from scripts import run_demo_v0_3_live_safety_loop


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("\n".join(json.dumps(row, separators=(",", ":")) for row in rows) + "\n", encoding="utf-8")


def amoled_rows(cmd_id: str = "demo-v0-3-cmd") -> list[dict[str, object]]:
    return [
        {
            "type": "command_ack",
            "device_id": "wearable-node-001",
            "role": "wearable_node",
            "protocol_version": "0.2",
            "seq": 3,
            "device_monotonic_ms": 15526,
            "source": "amoled_touch_demo",
            "cmd": "ask_user",
            "cmd_id": cmd_id,
            "ack_status": "ok",
        },
        {
            "type": "ask_user_rendered",
            "device_id": "wearable-node-001",
            "role": "wearable_node",
            "protocol_version": "0.2",
            "seq": 4,
            "device_monotonic_ms": 15527,
            "source": "amoled_touch_demo",
            "response": "pending",
            "cmd_id": cmd_id,
        },
        {
            "type": "user_confirmation",
            "device_id": "wearable-node-001",
            "role": "wearable_node",
            "protocol_version": "0.2",
            "seq": 5,
            "device_monotonic_ms": 71522,
            "source": "amoled_touch_demo",
            "response": "safe",
            "cmd_id": cmd_id,
        },
    ]


def location_event() -> dict[str, object]:
    return {
        "protocol_version": "egolink.p0.v1",
        "device_id": "connectivity-node-001",
        "ts": "2026-06-25T08:00:00+00:00",
        "seq": 1,
        "message_type": "event",
        "event_type": "location_report",
        "priority": "normal",
        "source": "sim7670g_gnss",
        "fix": False,
        "gnss_state": "no_fix",
        "port": "COM6",
        "gnss_power_state": "1",
        "raw_command": "AT+CGNSSINFO",
        "raw_response": "+CGNSSINFO:,,,,,,,,,,,,,,,,,",
    }


class LiveSafetyDemoTests(unittest.TestCase):
    def test_build_live_events_preserves_real_touch_and_requests_location(self) -> None:
        events = live_safety_demo.build_live_events(
            amoled_messages=amoled_rows(),
            location_event=location_event(),
            session_id="demo-v0-3-test",
            selected_gnss_port="COM6",
            now=live_safety_demo.minimal_safety_demo.DemoClock(),
        )

        event_types = [event["event_type"] for event in events]
        self.assertEqual(
            event_types,
            [
                "board_hello",
                "board_hello",
                "motion_event",
                "command_sent",
                "command_ack",
                "ask_user_rendered",
                "user_confirmation",
                "command_sent",
                "command_ack",
                "location_report",
                "safety_event",
            ],
        )
        ask_user = events[3]
        confirmation = events[6]
        request_location = events[7]
        location = events[9]
        safety = events[10]

        self.assertEqual(ask_user["cmd"], "ask_user")
        self.assertEqual(ask_user["cmd_id"], "demo-v0-3-cmd")
        self.assertEqual(confirmation["response"], "safe")
        self.assertEqual(confirmation["source_event_key"], live_safety_demo.minimal_safety_demo.source_event_key(ask_user))
        self.assertEqual(request_location["cmd"], "request_location")
        self.assertEqual(location["device_id"], "connectivity-node-001")
        self.assertEqual(location["source_event_type"], "command_ack")
        self.assertEqual(safety["outcome"], "confirmed_safe")
        self.assertEqual(safety["demo_version"], live_safety_demo.LIVE_DEMO_VERSION)

    def test_run_live_demo_writes_quality_checked_recording(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            amoled = root / "amoled.jsonl"
            event_log = root / "events.jsonl"
            recording_dir = root / "recording"
            write_jsonl(amoled, amoled_rows())

            result = live_safety_demo.run_live_demo(
                amoled_jsonl=amoled,
                location_event=location_event(),
                event_log=event_log,
                recording_dir=recording_dir,
                session_id="demo-v0-3-recording",
                selected_gnss_port="COM6",
                now=live_safety_demo.minimal_safety_demo.DemoClock(),
            )
            quality = session_inspector.inspect_recording(recording_dir)
            event_log_text = event_log.read_text(encoding="utf-8")

            self.assertTrue(result["ok"])
            self.assertTrue(quality["passed"])
            self.assertEqual(result["response"], "safe")
            self.assertEqual(result["event_counts"]["safety_event"], 1)
            self.assertIn("request_location", event_log_text)

    def test_cli_can_run_from_existing_evidence_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            amoled = root / "amoled.jsonl"
            location = root / "location.json"
            event_log = root / "events.jsonl"
            recording_dir = root / "recording"
            write_jsonl(amoled, amoled_rows())
            location.write_text(json.dumps(location_event()), encoding="utf-8")

            with redirect_stdout(StringIO()) as output:
                exit_code = run_demo_v0_3_live_safety_loop.main(
                    [
                        "--session-id",
                        "demo-v0-3-cli",
                        "--amoled-jsonl",
                        str(amoled),
                        "--location-event-json",
                        str(location),
                        "--event-log",
                        str(event_log),
                        "--output-dir",
                        str(recording_dir),
                        "--json",
                    ]
            )
            payload = json.loads(output.getvalue())

            self.assertEqual(exit_code, 0)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["response"], "safe")
            self.assertTrue(Path(payload["quality_report"]["path"]).exists())


if __name__ == "__main__":
    unittest.main()

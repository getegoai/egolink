from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from pc_simulator import event_store, session_recorder
from scripts import session_recorder as session_recorder_cli


def sample_events() -> list[dict[str, object]]:
    return [
        {
            "message_type": "status",
            "event_type": "mqtt_status",
            "device_id": "ego-link-001",
            "seq": 10,
            "ts": "uptime_ms:1000",
            "battery": 87,
            "charging": False,
            "link_type": "wifi",
            "guard_mode": "child_safety",
            "queue_size": 0,
            "rssi": -45,
            "modem_state": "mock_data_ready",
            "gnss_state": "mock_fix",
        },
        {
            "message_type": "event",
            "event_type": "sensor_sample",
            "sensor_kind": "device_health",
            "device_id": "ego-link-001",
            "seq": 11,
            "ts": "uptime_ms:2000",
            "wifi_rssi": -46,
            "free_heap_bytes": 212000,
            "min_free_heap_bytes": 198000,
            "battery": 87,
            "charging": False,
            "modem_state": "mock_data_ready",
            "gnss_state": "mock_fix",
        },
        {
            "event_type": "location_report",
            "device_id": "ego-link-001",
            "seq": 12,
            "ts": "2026-06-21T08:00:00+00:00",
            "source": "sim7670g_gnss",
            "fix": False,
            "gnss_power_state": 1,
            "satellites": 0,
        },
        {
            "event_type": "sos_pressed",
            "device_id": "ego-link-001",
            "seq": 13,
            "ts": "2026-06-21T08:00:01+00:00",
            "source": "dashboard_button",
            "priority": "critical",
        },
        {
            "event_type": "safety_evaluation",
            "device_id": "ego-link-001",
            "seq": 14,
            "ts": "2026-06-21T08:00:02+00:00",
            "source_event_key": "ego-link-001:sos_pressed:13",
            "source_event_type": "sos_pressed",
            "risk_type": "manual_sos",
            "risk_score": 1.0,
            "confidence": 1.0,
            "recommended_action": "urgent_escalation",
        },
        {
            "event_type": "command_sent",
            "device_id": "ego-link-001",
            "seq": 15,
            "ts": "2026-06-21T08:00:03+00:00",
            "cmd": "ask_user",
            "command_id": "cmd-0015",
        },
    ]


class SessionRecorderTests(unittest.TestCase):
    def test_build_recording_marks_unavailable_sources_and_extracts_frames(self) -> None:
        recording = session_recorder.build_recording(
            sample_events(),
            event_log=Path("events.jsonl"),
            session_id="test-session",
            created_at="2026-06-21T08:00:10+00:00",
        )

        manifest = recording["manifest"]
        self.assertEqual(manifest["session_id"], "test-session")
        self.assertEqual(manifest["sensor_sources"]["imu"]["availability"], "not_available")
        self.assertEqual(manifest["sensor_sources"]["microphone"]["status"], "missing_or_unknown")
        self.assertEqual(manifest["sensor_sources"]["battery_telemetry"]["availability"], "mock")
        self.assertFalse(manifest["privacy"]["raw_audio_allowed"])
        self.assertFalse(manifest["privacy"]["raw_image_allowed"])

        frames = recording["sensor_frames"]
        self.assertEqual([frame["frame_type"] for frame in frames], ["device_status", "device_health", "gnss_report"])
        self.assertEqual(frames[1]["monotonic_ms"], 2000)
        self.assertEqual(frames[1]["wifi_rssi"], -46)
        self.assertEqual(frames[2]["source_availability"], "pc_side_probe")
        self.assertEqual(frames[2]["fix"], False)

        event_types = [event["event_type"] for event in recording["events"]]
        self.assertEqual(event_types, ["sos_pressed", "safety_evaluation", "command_sent"])

    def test_write_recording_outputs_manifest_jsonl_annotations_and_summary(self) -> None:
        recording = session_recorder.build_recording(
            sample_events(),
            event_log=Path("events.jsonl"),
            session_id="write-session",
            created_at="2026-06-21T08:00:10+00:00",
        )

        with tempfile.TemporaryDirectory() as tmp:
            paths = session_recorder.write_recording(recording, Path(tmp))
            manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
            file_manifest = json.loads(paths["file_manifest"].read_text(encoding="utf-8"))
            frames = [json.loads(line) for line in paths["sensor_frames"].read_text(encoding="utf-8").splitlines()]
            events = [json.loads(line) for line in paths["events"].read_text(encoding="utf-8").splitlines()]
            annotations = paths["annotations"].read_text(encoding="utf-8")
            summary = paths["summary"].read_text(encoding="utf-8")

        self.assertEqual(manifest["record_counts"]["sensor_frames"], 3)
        self.assertEqual(manifest["outputs"]["file_manifest"], "file_manifest.json")
        self.assertEqual(file_manifest["hash_algorithm"], "sha256")
        self.assertIn("manifest", file_manifest["files"])
        self.assertIn("sensor_frames", file_manifest["files"])
        self.assertEqual(len(file_manifest["files"]["events"]["sha256"]), 64)
        self.assertEqual(len(frames), 3)
        self.assertEqual(events[-1]["command"], "ask_user")
        self.assertEqual(annotations, "")
        self.assertIn("write-session", summary)
        self.assertIn("physical_sos_gpio", summary)

    def test_cli_writes_recording_from_event_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            event_log = root / "events.jsonl"
            output_dir = root / "recording"
            for event in sample_events():
                event_store.append_jsonl(event_log, event)

            with redirect_stdout(StringIO()):
                exit_code = session_recorder_cli.main(
                    [
                        "--event-log",
                        str(event_log),
                        "--session-id",
                        "cli-session",
                        "--output-dir",
                        str(output_dir),
                        "--limit",
                        "20",
                        "--json",
                    ]
                )

            manifest = json.loads((output_dir / "session_manifest.json").read_text(encoding="utf-8"))
            file_manifest = json.loads((output_dir / "file_manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(manifest["session_id"], "cli-session")
        self.assertEqual(manifest["record_counts"]["events"], 3)
        self.assertIn("annotations", file_manifest["files"])


if __name__ == "__main__":
    unittest.main()

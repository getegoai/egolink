from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from pc_simulator import full_safety_demo, minimal_safety_demo
from scripts import run_full_safety_demo
from quality_tests.test_live_safety_demo import amoled_rows_with_motion, location_event, write_jsonl


class FullSafetyDemoTests(unittest.TestCase):
    def test_build_full_events_adds_mock_audio_chain(self) -> None:
        events = full_safety_demo.build_full_events(
            amoled_messages=amoled_rows_with_motion(),
            location_event=location_event(),
            session_id="demo-full-events",
            selected_gnss_port="COM6",
            now=minimal_safety_demo.DemoClock(),
        )

        self.assertEqual(events[-3]["cmd"], "capture_audio")
        self.assertEqual(events[-2]["event_type"], "command_ack")
        self.assertEqual(events[-2]["ack_status"], "mock_only")
        self.assertEqual(events[-1]["event_type"], "wake_detected")
        self.assertEqual(events[-1]["source_status"], "mock_only")
        self.assertFalse(events[-1]["raw_audio_captured"])
        self.assertEqual(events[-1]["full_demo_version"], full_safety_demo.FULL_DEMO_VERSION)

    def test_run_full_demo_writes_quality_replay_and_privacy_safe_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            amoled = root / "amoled.jsonl"
            event_log = root / "events.jsonl"
            recording_dir = root / "recording"
            write_jsonl(amoled, amoled_rows_with_motion())

            result = full_safety_demo.run_full_demo(
                amoled_jsonl=amoled,
                location_event=location_event(),
                event_log=event_log,
                recording_dir=recording_dir,
                session_id="demo-full-recording",
                selected_gnss_port="COM6",
                created_at="2026-06-26T00:00:00+00:00",
                now=minimal_safety_demo.DemoClock(),
            )

            manifest = json.loads((recording_dir / "session_manifest.json").read_text(encoding="utf-8"))
            replay = json.loads((recording_dir / "session_replay_report.json").read_text(encoding="utf-8"))

        self.assertTrue(result["ok"])
        self.assertTrue(all(stage["passed"] for stage in result["stages"].values()))
        self.assertEqual(result["event_counts"]["wake_detected"], 1)
        self.assertEqual(manifest["sensor_sources"]["microphone"]["availability"], "mock")
        self.assertEqual(manifest["sensor_sources"]["microphone"]["status"], "mock_only")
        self.assertFalse(manifest["privacy"]["raw_audio_allowed"])
        self.assertFalse(result["privacy"]["raw_audio_captured"])
        self.assertTrue(replay["passed"])
        self.assertGreaterEqual(replay["summary"]["replayed_inputs"], 1)

    def test_cli_runs_from_existing_evidence_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            amoled = root / "amoled.jsonl"
            location = root / "location.json"
            event_log = root / "events.jsonl"
            recording_dir = root / "recording"
            write_jsonl(amoled, amoled_rows_with_motion())
            location.write_text(
                json.dumps(
                    {
                        "summary": {"at_ok": True, "fix": False, "selected_port": "COM6"},
                        "event": location_event(),
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()) as output:
                exit_code = run_full_safety_demo.main(
                    [
                        "--session-id",
                        "demo-full-cli",
                        "--amoled-jsonl",
                        str(amoled),
                        "--location-event-json",
                        str(location),
                        "--event-log",
                        str(event_log),
                        "--output-dir",
                        str(recording_dir),
                        "--runtime-dir",
                        str(root),
                        "--json",
                    ]
                )
            payload = json.loads(output.getvalue())
            summary_exists = Path(payload["summary_path"]).exists()

        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["stages"]["demo_v0_5"]["passed"])
        self.assertEqual(payload["attempts"][0]["label"], "amoled_capture")
        self.assertEqual(payload["attempts"][1]["label"], "gnss_probe")
        self.assertEqual(payload["gnss"]["selected_port"], "COM6")
        self.assertTrue(summary_exists)


if __name__ == "__main__":
    unittest.main()

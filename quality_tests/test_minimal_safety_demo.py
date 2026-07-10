from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from pc_simulator import minimal_safety_demo, session_inspector, session_replay
from scripts import run_minimal_safety_demo


def event_types(path: Path) -> list[str]:
    return [json.loads(line)["event_type"] for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class MinimalSafetyDemoTests(unittest.TestCase):
    def test_build_demo_events_runs_core_product_loop(self) -> None:
        events = minimal_safety_demo.build_demo_events(
            session_id="demo-test",
            user_response="help",
            now=minimal_safety_demo.DemoClock(),
        )

        self.assertEqual(
            [event["event_type"] for event in events],
            [
                "board_hello",
                "board_hello",
                "motion_event",
                "command_sent",
                "user_confirmation",
                "command_sent",
                "command_ack",
                "location_report",
                "safety_event",
            ],
        )
        self.assertEqual(events[3]["cmd"], "ask_user")
        self.assertEqual(events[4]["response"], "help")
        self.assertEqual(events[5]["cmd"], "request_location")
        self.assertEqual(events[-1]["outcome"], "needs_help")
        self.assertEqual(events[-1]["recommended_action"], "prepare_help")

    def test_run_demo_writes_quality_checked_recording(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            event_log = root / "demo.events.jsonl"
            recording_dir = root / "recording"
            result = minimal_safety_demo.run_demo(
                event_log=event_log,
                recording_dir=recording_dir,
                session_id="demo-recording",
                user_response="safe",
                created_at="2026-06-24T00:00:00+00:00",
                now=minimal_safety_demo.DemoClock(),
            )
            quality = session_inspector.inspect_recording(recording_dir)
            replay = session_replay.replay_recording(recording_dir)
            written_event_types = event_types(event_log)

        self.assertTrue(result["ok"])
        self.assertTrue(quality["passed"])
        self.assertEqual(result["counts"]["events_written"], 9)
        self.assertEqual(written_event_types[-1], "safety_event")
        self.assertGreaterEqual(replay["summary"]["replayed_inputs"], 1)
        self.assertIn("capture_more", replay["summary"]["recommended_actions"])

    def test_cli_outputs_json_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with redirect_stdout(StringIO()) as output:
                exit_code = run_minimal_safety_demo.main(
                    [
                        "--session-id",
                        "demo-cli",
                        "--event-log",
                        str(root / "events.jsonl"),
                        "--output-dir",
                        str(root / "recording"),
                        "--response",
                        "help",
                        "--json",
                    ]
                )
            payload = json.loads(output.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["response"], "help")
        self.assertEqual(payload["counts"]["events_written"], 9)


if __name__ == "__main__":
    unittest.main()

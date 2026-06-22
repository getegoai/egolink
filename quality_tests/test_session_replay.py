from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from pc_simulator import session_recorder, session_replay
from scripts import replay_session_recording
from quality_tests.test_session_recorder import sample_events


class SessionReplayTests(unittest.TestCase):
    def write_sample_recording(self, output_dir: Path) -> None:
        recording = session_recorder.build_recording(
            sample_events(),
            event_log=Path("events.jsonl"),
            session_id="replay-session",
            created_at="2026-06-21T08:00:10+00:00",
        )
        session_recorder.write_recording(recording, output_dir)

    def test_replay_recording_runs_quality_gate_and_router(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            recording_dir = Path(tmp)
            self.write_sample_recording(recording_dir)

            report = session_replay.replay_recording(
                recording_dir,
                generated_at="2026-06-21T08:01:00+00:00",
            )

        self.assertTrue(report["passed"])
        self.assertTrue(report["quality_gate"]["passed"])
        self.assertEqual(report["session_id"], "replay-session")
        self.assertEqual(report["summary"]["timeline_records"], 6)
        self.assertEqual(report["summary"]["sensor_frames"], 3)
        self.assertEqual(report["summary"]["events"], 3)
        self.assertEqual(report["summary"]["replayed_inputs"], 4)
        self.assertEqual(report["summary"]["skipped_records"], 2)
        self.assertEqual(report["summary"]["safety_events"], 1)
        self.assertEqual(report["summary"]["base_commands"], 1)
        self.assertEqual(report["summary"]["risk_types"], {"manual_sos": 1, "none": 3})

        seqs = [record["seq"] for record in report["records"]]
        self.assertEqual(seqs, [10, 11, 12, 13, 14, 15])
        sos_record = next(record for record in report["records"] if record.get("event_type") == "sos_pressed")
        self.assertTrue(sos_record["replayed"])
        self.assertEqual(sos_record["sensor_frame"]["source"], "replay")
        self.assertEqual(sos_record["model_output"]["risk_type"], "manual_sos")
        self.assertEqual(sos_record["base_command"]["command"], "ask_user")
        self.assertEqual(sos_record["sensor_frame"]["metadata"]["recording_session_id"], "replay-session")

    def test_replay_refuses_failed_quality_gate_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            recording_dir = Path(tmp)
            self.write_sample_recording(recording_dir)
            events_path = recording_dir / "events.jsonl"
            events_path.write_text(events_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

            report = session_replay.replay_recording(recording_dir)

        self.assertFalse(report["passed"])
        self.assertEqual(report["summary"]["replayed_inputs"], 0)
        self.assertEqual(report["records"], [])
        self.assertIn("quality_gate_failed", {error["code"] for error in report["errors"]})
        self.assertIn("file_hash_mismatch", {error["code"] for error in report["quality_errors"]})

    def test_write_report_outputs_json_and_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            recording_dir = Path(tmp)
            self.write_sample_recording(recording_dir)
            report = session_replay.replay_recording(recording_dir)
            json_path, markdown_path = session_replay.write_report(report)

            saved = json.loads(json_path.read_text(encoding="utf-8"))
            markdown = markdown_path.read_text(encoding="utf-8")

        self.assertEqual(saved["schema_version"], session_replay.REPLAY_SCHEMA_VERSION)
        self.assertIn("Session Replay Report", markdown)
        self.assertIn("manual_sos", markdown)

    def test_cli_returns_success_for_valid_recording(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            recording_dir = Path(tmp)
            self.write_sample_recording(recording_dir)

            with redirect_stdout(StringIO()):
                exit_code = replay_session_recording.main([str(recording_dir), "--json"])

            report_path = recording_dir / "session_replay_report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            markdown_exists = (recording_dir / "session_replay_report.md").is_file()

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["summary"]["replayed_inputs"], 4)
        self.assertTrue(markdown_exists)


if __name__ == "__main__":
    unittest.main()

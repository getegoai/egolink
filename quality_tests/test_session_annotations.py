from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from pc_simulator import session_annotations, session_inspector, session_recorder, session_replay
from scripts import annotate_session_recording
from quality_tests.test_session_recorder import sample_events


class SessionAnnotationTests(unittest.TestCase):
    def write_sample_recording(self, output_dir: Path) -> None:
        recording = session_recorder.build_recording(
            sample_events(),
            event_log=Path("events.jsonl"),
            session_id="annotation-session",
            created_at="2026-06-21T08:00:10+00:00",
        )
        session_recorder.write_recording(recording, output_dir)

    def test_annotate_recording_updates_counts_hashes_and_quality_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            recording_dir = Path(tmp)
            self.write_sample_recording(recording_dir)
            target = next(
                row
                for row in session_annotations.annotation_targets(recording_dir)
                if row.get("event_type") == "sos_pressed"
            )

            result = session_annotations.annotate_recording(
                recording_dir,
                source_event_key=target["source_event_key"],
                label="needs_help",
                annotator_type="human",
                notes="confirmed during local smoke test",
                created_at="2026-06-21T08:01:00+00:00",
                annotation_id="ann-unit-needs-help",
                training_allowed=True,
            )
            report = session_inspector.inspect_recording(recording_dir)
            manifest = json.loads((recording_dir / "session_manifest.json").read_text(encoding="utf-8"))
            summary = (recording_dir / "session_recording.md").read_text(encoding="utf-8")

        self.assertEqual(result["annotation"]["label"], "needs_help")
        self.assertEqual(result["annotation"]["model_labels"]["action_outcome"], "help_requested")
        self.assertEqual(result["record_counts"]["annotations"], 1)
        self.assertEqual(manifest["record_counts"]["annotations"], 1)
        self.assertIn("Annotations: `1`", summary)
        self.assertTrue(report["passed"])
        self.assertEqual(report["summary"]["annotations"], 1)
        self.assertEqual(report["summary"]["annotation_labels"], {"needs_help": 1})
        self.assertEqual(report["summary"]["annotation_outcomes"], {"help_requested": 1})
        self.assertNotIn("annotations_empty", {warning["code"] for warning in report["warnings"]})
        self.assertNotIn("file_hash_mismatch", {error["code"] for error in report["errors"]})

    def test_annotation_cli_can_list_targets_and_append_by_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            recording_dir = Path(tmp)
            self.write_sample_recording(recording_dir)

            with redirect_stdout(StringIO()) as list_output:
                list_code = annotate_session_recording.main([str(recording_dir), "--list-targets", "--json"])
            targets = json.loads(list_output.getvalue())["targets"]
            target_index = next(row["index"] for row in targets if row.get("frame_type") == "device_health")

            with redirect_stdout(StringIO()) as append_output:
                append_code = annotate_session_recording.main(
                    [
                        str(recording_dir),
                        "--target-index",
                        str(target_index),
                        "--label",
                        "safe",
                        "--annotation-id",
                        "ann-cli-safe",
                        "--created-at",
                        "2026-06-21T08:02:00+00:00",
                        "--json",
                    ]
                )
            payload = json.loads(append_output.getvalue())
            report = session_inspector.inspect_recording(recording_dir)

        self.assertEqual(list_code, 0)
        self.assertEqual(append_code, 0)
        self.assertEqual(payload["annotation"]["label"], "safe")
        self.assertEqual(report["summary"]["annotation_labels"], {"safe": 1})
        self.assertTrue(report["passed"])

    def test_replay_report_includes_annotation_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            recording_dir = Path(tmp)
            self.write_sample_recording(recording_dir)
            target = session_annotations.annotation_targets(recording_dir)[0]
            session_annotations.annotate_recording(
                recording_dir,
                source_event_key=target["source_event_key"],
                label="false_alarm",
                annotation_id="ann-replay-false-alarm",
                created_at="2026-06-21T08:03:00+00:00",
            )

            report = session_replay.replay_recording(recording_dir)
            _, markdown_path = session_replay.write_report(report)
            markdown = markdown_path.read_text(encoding="utf-8")

        self.assertTrue(report["passed"])
        self.assertEqual(report["summary"]["annotations"], 1)
        self.assertEqual(report["summary"]["annotation_labels"], {"false_alarm": 1})
        self.assertEqual(report["summary"]["annotation_outcomes"], {"false_alarm": 1})
        self.assertIn("Annotation Labels", markdown)
        self.assertIn("false_alarm", markdown)


if __name__ == "__main__":
    unittest.main()

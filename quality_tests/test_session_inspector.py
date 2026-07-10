from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from pc_simulator import event_store, session_inspector, session_recorder
from scripts import inspect_session_recording
from quality_tests.test_session_recorder import sample_events


class SessionInspectorTests(unittest.TestCase):
    def write_sample_recording(self, output_dir: Path) -> dict[str, object]:
        recording = session_recorder.build_recording(
            sample_events(),
            event_log=Path("events.jsonl"),
            session_id="inspect-session",
            created_at="2026-06-21T08:00:10+00:00",
        )
        session_recorder.write_recording(recording, output_dir)
        return recording

    def test_inspector_passes_valid_recording_with_expected_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            recording_dir = Path(tmp)
            self.write_sample_recording(recording_dir)

            report = session_inspector.inspect_recording(
                recording_dir,
                generated_at="2026-06-21T08:00:20+00:00",
            )

        self.assertTrue(report["passed"])
        self.assertEqual(report["summary"]["sensor_frames"], 3)
        self.assertEqual(report["summary"]["events"], 3)
        self.assertEqual(report["summary"]["annotations"], 0)
        self.assertEqual(report["summary"]["integrity_files"], 5)
        warning_codes = {warning["code"] for warning in report["warnings"]}
        self.assertIn("annotations_empty", warning_codes)
        self.assertIn("firmware_version_unknown", warning_codes)
        self.assertEqual(report["summary"]["frame_types"]["device_health"], 1)

    def test_inspector_rejects_count_mismatch_and_real_unverified_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            recording_dir = Path(tmp)
            self.write_sample_recording(recording_dir)
            manifest_path = recording_dir / "session_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["record_counts"]["sensor_frames"] = 99
            manifest["sensor_sources"]["imu"]["availability"] = "real"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

            report = session_inspector.inspect_recording(recording_dir)

        self.assertFalse(report["passed"])
        error_codes = {error["code"] for error in report["errors"]}
        self.assertIn("record_count_mismatch", error_codes)
        self.assertIn("unverified_source_marked_real", error_codes)
        self.assertIn("file_size_mismatch", error_codes)
        self.assertIn("file_hash_mismatch", error_codes)

    def test_inspector_rejects_duplicate_source_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            recording_dir = Path(tmp)
            self.write_sample_recording(recording_dir)
            event_log = recording_dir / "events.jsonl"
            rows = [json.loads(line) for line in event_log.read_text(encoding="utf-8").splitlines()]
            duplicate = dict(rows[0])
            event_store.append_jsonl(event_log, duplicate)
            manifest_path = recording_dir / "session_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["record_counts"]["events"] = len(rows) + 1
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

            report = session_inspector.inspect_recording(recording_dir)

        self.assertFalse(report["passed"])
        self.assertIn("duplicate_source_event_key", {error["code"] for error in report["errors"]})
        self.assertIn("file_size_mismatch", {error["code"] for error in report["errors"]})

    def test_inspector_rejects_tampered_recording_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            recording_dir = Path(tmp)
            self.write_sample_recording(recording_dir)
            events_path = recording_dir / "events.jsonl"
            events_path.write_text(events_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

            report = session_inspector.inspect_recording(recording_dir)

        self.assertFalse(report["passed"])
        error_codes = {error["code"] for error in report["errors"]}
        self.assertIn("file_size_mismatch", error_codes)
        self.assertIn("file_hash_mismatch", error_codes)

    def test_write_report_outputs_json_and_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            recording_dir = Path(tmp)
            self.write_sample_recording(recording_dir)
            report = session_inspector.inspect_recording(recording_dir)
            json_path, markdown_path = session_inspector.write_report(report)

            payload = json.loads(json_path.read_text(encoding="utf-8"))
            markdown = markdown_path.read_text(encoding="utf-8")

        self.assertTrue(payload["passed"])
        self.assertIn("Ego Link Session Quality Report", markdown)
        self.assertIn("Quality score", markdown)

    def test_cli_returns_success_for_valid_recording(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            recording_dir = Path(tmp)
            self.write_sample_recording(recording_dir)
            with redirect_stdout(StringIO()):
                exit_code = inspect_session_recording.main([str(recording_dir), "--json"])

            report_path = recording_dir / "session_quality_report.json"
            report_exists = report_path.is_file()

        self.assertEqual(exit_code, 0)
        self.assertTrue(report_exists)


if __name__ == "__main__":
    unittest.main()

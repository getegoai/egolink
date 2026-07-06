from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from scripts import observe_d1_field_run
from scripts import summarize_d1_field_observations as indexer


class D1FieldObservationIndexTests(unittest.TestCase):
    def test_index_prefers_running_status_and_excludes_sample_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "d1_field_observation"
            completed_dir = root / "run-a"
            completed_dir.mkdir(parents=True)
            (completed_dir / observe_d1_field_run.REPORT_JSON).write_text(
                json.dumps(
                    {
                        "run_id": "run-a",
                        "result": "WARN",
                        "created_at": "2026-07-06T01:00:00+00:00",
                        "device_id": "ego-link-r1-connectivity-001",
                        "summary": {
                            "sample_count": 4,
                            "successful_sample_count": 4,
                            "fetch_error_count": 0,
                            "last_seq": 42,
                            "max_freshness_s": 90,
                            "last_location_upload_at": "2026-07-06T01:02:00+00:00",
                            "coordinate_sample_count": 0,
                            "raw_post_success_delta": 2,
                            "raw_post_failure_delta": 0,
                            "location_event_count_delta": 2,
                            "power_sample_count_delta": 2,
                        },
                        "samples_path": "C:/private/local/d1_field_samples.jsonl",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            running_dir = root / "run-b"
            running_dir.mkdir(parents=True)
            (running_dir / observe_d1_field_run.STATUS_JSON).write_text(
                json.dumps(
                    {
                        "status": "running",
                        "run_id": "run-b",
                        "device_id": "ego-link-r1-connectivity-001",
                        "updated_at": "2030-07-06T02:00:00+00:00",
                        "planned_sample_count": 60,
                        "sample_count": 7,
                        "successful_sample_count": 7,
                        "fetch_error_count": 0,
                        "latest_seq": 100,
                        "latest_freshness_s": 12,
                        "latest_location_upload_at": "2026-07-06T01:59:48+00:00",
                        "latest_d1_status": "estimate_visible",
                        "samples_path": "C:/private/local/d1_field_samples.jsonl",
                        "report_path": "C:/private/local/report.json",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            payload = indexer.build_index(root=root, generated_at="2026-07-06T02:01:00+00:00")

        text = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(payload["summary"]["run_count"], 2)
        self.assertEqual(payload["summary"]["running_count"], 1)
        self.assertEqual(payload["summary"]["latest_run_id"], "run-b")
        self.assertEqual(payload["runs"][0]["status"], "running")
        self.assertEqual(payload["runs"][0]["sample_count"], 7)
        self.assertEqual(payload["runs"][0]["latest_seq"], 100)
        self.assertNotIn("d1_field_samples.jsonl", text)
        self.assertNotIn("C:/private", text)
        self.assertFalse(payload["scope"]["message_hub_called"])
        self.assertFalse(payload["scope"]["samples_jsonl_read"])

    def test_cli_writes_json_and_markdown_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "d1_field_observation"
            output_dir = Path(tmp) / "index"
            run_dir = root / "run-cli"
            run_dir.mkdir(parents=True)
            (run_dir / observe_d1_field_run.STATUS_JSON).write_text(
                json.dumps(
                    {
                        "status": "running",
                        "run_id": "run-cli",
                        "updated_at": "2026-07-06T02:00:00+00:00",
                        "sample_count": 1,
                        "successful_sample_count": 1,
                        "latest_seq": 9,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = indexer.main(
                    [
                        "--root",
                        str(root),
                        "--output-dir",
                        str(output_dir),
                        "--generated-at",
                        "2026-07-06T02:01:00+00:00",
                        "--json",
                    ]
                )
            payload = json.loads(stdout.getvalue())

            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["summary"]["latest_run_id"], "run-cli")
            self.assertTrue((output_dir / indexer.INDEX_JSON).is_file())
            self.assertTrue((output_dir / indexer.INDEX_MARKDOWN).is_file())


if __name__ == "__main__":
    unittest.main()

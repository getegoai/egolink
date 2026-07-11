from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts import build_d2_historical_baseline as baseline


class D2HistoricalBaselineTests(unittest.TestCase):
    def test_builds_provisional_report_without_copying_coordinates(self) -> None:
        export = {
            "window": {"complete": True, "truncated": {}},
            "messages": [
                {
                    "device_id": "device-unit",
                    "message_type": "event",
                    "event_type": "location_report",
                    "seq": 1,
                    "server_received_at": "2026-07-01T00:01:00Z",
                    "fix": False,
                    "lat": 31.123456,
                    "lon": 121.654321,
                    "imu": {"source_status": "mock"},
                },
                {
                    "device_id": "device-unit",
                    "message_type": "event",
                    "event_type": "location_report",
                    "seq": 2,
                    "server_received_at": "2026-07-01T00:02:00Z",
                    "fix": True,
                    "lat": 31.123499,
                    "lon": 121.654399,
                    "gnss": {"attempt_ms": 12000, "speed_mps": 2.5},
                    "imu": {"source_status": "observed"},
                },
            ],
        }
        windows = [
            {
                "run_id": "field-unit",
                "device_id": "device-unit",
                "started_at": "2026-07-01T00:00:00+00:00",
                "ended_at": "2026-07-01T01:00:00+00:00",
                "observer_report": "reports/unit/report.json",
            }
        ]
        with mock.patch.object(baseline.pipeline, "fetch_device_window_export", return_value=export):
            report = baseline.build_report(
                run_id="historical-unit",
                generated_at="2026-07-11T10:00:00+00:00",
                hub_url="http://hub.example:8790",
                device_id="device-unit",
                windows=windows,
                token="secret-unit-token",
                request_timeout_sec=10,
                max_records=100,
            )

        self.assertEqual(report["status"], "WARN")
        self.assertEqual(report["metrics"]["fix_rate"], 0.5)
        self.assertEqual(report["metrics"]["ttff_median_s"], 12.0)
        self.assertIsNone(report["metrics"]["median_error_m"])
        self.assertFalse(report["result"]["strict_d2_acceptance_ready"])
        payload = json.dumps(report)
        self.assertNotIn("31.123456", payload)
        self.assertNotIn("121.654321", payload)
        self.assertNotIn("secret-unit-token", payload)

    def test_cli_reads_observer_window_and_writes_one_page_report(self) -> None:
        export = {
            "window": {"complete": True, "truncated": {}},
            "messages": [
                {
                    "device_id": "device-unit",
                    "message_type": "event",
                    "event_type": "location_report",
                    "seq": 1,
                    "server_received_at": "2026-07-01T00:01:00Z",
                    "fix": True,
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            observer = root / "d1_field_observation_report.json"
            observer.write_text(
                json.dumps(
                    {
                        "run_id": "field-unit",
                        "device_id": "device-unit",
                        "summary": {
                            "first_device_upload_at": "2026-07-01T00:00:00Z",
                            "last_device_upload_at": "2026-07-01T01:00:00Z",
                        },
                    }
                ),
                encoding="utf-8",
            )
            output = root / "output"
            stdout = io.StringIO()
            with mock.patch.object(baseline.pipeline, "fetch_device_window_export", return_value=export) as fetch:
                with redirect_stdout(stdout):
                    exit_code = baseline.main(
                        [
                            "--hub",
                            "http://hub.example:8790",
                            "--device-id",
                            "device-unit",
                            "--observer-report",
                            str(observer),
                            "--output-dir",
                            str(output),
                            "--run-id",
                            "historical-unit",
                            "--generated-at",
                            "2026-07-11T10:00:00+00:00",
                            "--token-file",
                            str(root / "missing-token.txt"),
                            "--margin-sec",
                            "60",
                            "--json",
                        ]
                    )
            report = json.loads(stdout.getvalue())
            markdown = (output / baseline.REPORT_MARKDOWN).read_text(encoding="utf-8")

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["metrics"]["fix_rate"], 1.0)
        self.assertIn("Median position error: **not measurable**", markdown)
        self.assertLessEqual(len(markdown.splitlines()), 40)
        fetch.assert_called_once_with(
            hub_url="http://hub.example:8790",
            device_id="device-unit",
            started_at="2026-06-30T23:59:00+00:00",
            ended_at="2026-07-01T01:01:00+00:00",
            max_records=10000,
            token=None,
            timeout_sec=180.0,
        )


if __name__ == "__main__":
    unittest.main()

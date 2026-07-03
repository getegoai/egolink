from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from scripts import analyze_power_curve as analyzer


FIXED_CREATED_AT = "2026-07-03T00:00:00+00:00"


def synthetic_export() -> dict:
    messages = []
    for index, hour in enumerate((0, 1, 2), start=1):
        messages.append(
            {
                "protocol_version": "egolink.p0.v1",
                "device_id": "ego-link-r1-connectivity-001",
                "message_type": "event",
                "event_type": "location_observation" if index == 2 else "sensor_sample",
                "seq": index,
                "server_received_at": f"2026-07-03T0{hour}:00:00+00:00",
                "transport": {"type": "lte" if index == 2 else "wifi"},
                "power": {
                    "battery_mv": 4100 - index * 20,
                    "soc_pct": 90 - index,
                    "charging": False,
                    "source": "max17048_i2c",
                    "source_status": "measured",
                    "evidence_status": "measured",
                    "state": "upload" if index == 2 else "guarding",
                },
            }
        )
    return {"test_run": {"id": "PWR-001-unit"}, "messages": messages, "raw_frames": []}


class PowerCurveAnalysisTests(unittest.TestCase):
    def test_synthetic_export_computes_curve_and_average_current(self) -> None:
        report = analyzer.evaluate_power_curve(
            synthetic_export(),
            created_at=FIXED_CREATED_AT,
            min_duration_hours=1.0,
            battery_capacity_mah=1000,
        )

        self.assertEqual(report["result"]["status"], "PASS")
        self.assertEqual(report["counts"]["samples"], 3)
        self.assertEqual(report["duration_hours"], 2.0)
        self.assertEqual(report["battery_mv"]["first"], 4080.0)
        self.assertEqual(report["battery_mv"]["last"], 4040.0)
        self.assertEqual(report["soc_pct"]["delta"], -2.0)
        self.assertEqual(report["consumption_estimate"]["status"], "estimated")
        self.assertAlmostEqual(report["consumption_estimate"]["average_current_ma"], 10.0)
        self.assertEqual(report["transport_overlay"]["transport_counts"]["lte"], 1)

    def test_missing_power_samples_fails(self) -> None:
        report = analyzer.evaluate_power_curve(
            {"test_run": {"id": "empty"}, "messages": [{"message_type": "status"}]},
            created_at=FIXED_CREATED_AT,
        )

        self.assertEqual(report["result"]["status"], "FAIL")
        self.assertIn("export contains no power samples", report["result"]["errors"])

    def test_cli_writes_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "test_run_export.json"
            output_dir = tmp_path / "out"
            input_path.write_text(json.dumps(synthetic_export(), indent=2) + "\n", encoding="utf-8")

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = analyzer.main(
                    [
                        "--input",
                        str(input_path),
                        "--output-dir",
                        str(output_dir),
                        "--min-duration-hours",
                        "1",
                        "--battery-capacity-mah",
                        "1000",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertIn("PASS PWR-001 power curve", stdout.getvalue())
            report_json = json.loads((output_dir / analyzer.REPORT_JSON).read_text(encoding="utf-8"))
            report_md = (output_dir / analyzer.REPORT_MARKDOWN).read_text(encoding="utf-8")
            self.assertEqual(report_json["result"]["status"], "PASS")
            self.assertIn("PWR-001 Power Curve Report", report_md)
            self.assertIn("Transport Overlay", report_md)


if __name__ == "__main__":
    unittest.main()

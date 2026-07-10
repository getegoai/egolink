from __future__ import annotations

from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import tempfile
import threading
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
        self.assertEqual(report["counts"]["measured_power_samples"], 3)
        self.assertEqual(report["duration_hours"], 2.0)
        self.assertEqual(report["battery_mv"]["first"], 4080.0)
        self.assertEqual(report["battery_mv"]["last"], 4040.0)
        self.assertEqual(report["soc_pct"]["delta"], -2.0)
        self.assertEqual(report["consumption_estimate"]["status"], "estimated")
        self.assertAlmostEqual(report["consumption_estimate"]["average_current_ma"], 10.0)
        self.assertEqual(report["target_comparison"]["status"], "estimated")
        self.assertAlmostEqual(report["target_comparison"]["target_average_current_ma"], 1000 * 0.8 / 48)
        self.assertAlmostEqual(report["target_comparison"]["gap_vs_target_ma"], 10.0 - (1000 * 0.8 / 48))
        self.assertEqual(report["target_comparison"]["engineering_status"], "within_48h_budget")
        self.assertEqual(report["target_comparison"]["claim_status"], "engineering_gap_only_not_product_life_claim")
        self.assertEqual(report["transport_overlay"]["transport_counts"]["lte"], 1)
        self.assertEqual(report["transport_overlay"]["power_source_status_counts"]["measured"], 3)

    def test_missing_power_samples_fails(self) -> None:
        report = analyzer.evaluate_power_curve(
            {"test_run": {"id": "empty"}, "messages": [{"message_type": "status"}]},
            created_at=FIXED_CREATED_AT,
        )

        self.assertEqual(report["result"]["status"], "FAIL")
        self.assertIn("export contains no power samples", report["result"]["errors"])

    def test_mock_only_power_samples_fail_pwr001_gate(self) -> None:
        export = synthetic_export()
        for message in export["messages"]:
            power = message["power"]
            power["source"] = "mock"
            power["source_status"] = "mock"
            power["evidence_status"] = "mock"

        report = analyzer.evaluate_power_curve(
            export,
            created_at=FIXED_CREATED_AT,
            min_duration_hours=1.0,
            battery_capacity_mah=1000,
        )

        self.assertEqual(report["result"]["status"], "FAIL")
        self.assertEqual(report["counts"]["measured_power_samples"], 0)
        self.assertIn("export contains no measured power samples", report["result"]["errors"])
        self.assertIn("3 samples are still marked mock", report["result"]["warnings"])

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
            self.assertIn("Measured power samples: 3 / 3", report_md)
            self.assertIn("48h target current budget", report_md)
            self.assertIn("48h target gap", report_md)
            self.assertIn("This report does not prove 48h or 7d product battery life.", report_md)

    def test_cli_can_fetch_message_hub_export(self) -> None:
        class ExportHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                self.server.seen_path = self.path  # type: ignore[attr-defined]
                self.server.seen_auth = self.headers.get("Authorization")  # type: ignore[attr-defined]
                if self.path != "/api/v1/test-runs/PWR-001-hub/export":
                    self.send_response(404)
                    self.end_headers()
                    return
                body = json.dumps(synthetic_export()).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), ExportHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                output_dir = tmp_path / "out"
                token_file = tmp_path / "token.txt"
                token_file.write_text("unit-token\n", encoding="utf-8")

                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    exit_code = analyzer.main(
                        [
                            "--hub",
                            f"http://127.0.0.1:{server.server_port}",
                            "--test-run-id",
                            "PWR-001-hub",
                            "--token-file",
                            str(token_file),
                            "--output-dir",
                            str(output_dir),
                            "--min-duration-hours",
                            "1",
                            "--battery-capacity-mah",
                            "1000",
                        ]
                    )

                self.assertEqual(exit_code, 0)
                self.assertEqual(server.seen_path, "/api/v1/test-runs/PWR-001-hub/export")  # type: ignore[attr-defined]
                self.assertEqual(server.seen_auth, "Bearer unit-token")  # type: ignore[attr-defined]
                self.assertNotIn("unit-token", stdout.getvalue())
                self.assertTrue((output_dir / "test_run_export.json").is_file())
                self.assertTrue((output_dir / analyzer.REPORT_JSON).is_file())
                self.assertTrue((output_dir / analyzer.REPORT_MARKDOWN).is_file())
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()

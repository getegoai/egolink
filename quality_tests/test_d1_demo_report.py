from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from scripts import build_d1_demo_report as d1_demo


FIXED_CREATED_AT = "2026-07-04T12:00:00+00:00"


def web_report() -> dict:
    return {
        "result": "PASS",
        "report_path": "reports/d1_web_api/d1-unit/d1_web_api_report.json",
        "device_id": "ego-link-001",
        "d1": {
            "status": "estimate_visible",
            "location_estimate": {"available": True, "state": "Coarse", "accuracy_claim": "none"},
            "map_surface": {"visible": True, "mode": "estimate_without_coordinate"},
            "upload_freshness": {"last_location_upload_at": "2026-07-04T00:00:01Z"},
            "uplink_metrics": {
                "location_event_count": 2,
                "raw_post_attempt_count": 2,
                "raw_post_success_count": 2,
                "raw_post_failure_count": 0,
            },
            "power_curve": {"sample_count": 3, "delta_battery_mv": -30, "battery_life_claim": "none"},
            "non_claims": ["location_accuracy_not_claimed", "battery_life_not_claimed"],
        },
        "scope": {
            "hardware_contacted": False,
            "firmware_changed": False,
            "commands_sent": False,
            "gitlab_modified": False,
            "location_accuracy_claimed": False,
            "battery_life_claimed": False,
        },
    }


def power_report(*, status: str = "PASS", measured_samples: int = 3) -> dict:
    return {
        "result": {"status": status, "errors": [] if status != "FAIL" else ["export contains no measured power samples"]},
        "report_path": "reports/power/pwr-unit/power_curve_report.json",
        "markdown_report_path": "reports/power/pwr-unit/power_curve_report.md",
        "source": {"test_run_id": "pwr-unit"},
        "duration_hours": 24.25,
        "counts": {"samples": 3, "measured_power_samples": measured_samples},
        "consumption_estimate": {"status": "estimated", "average_current_ma": 12.0},
        "target_comparison": {"status": "estimated", "gap_vs_target_ma": -4.67},
    }


class D1DemoReportTests(unittest.TestCase):
    def test_web_and_measured_power_reports_are_founder_review_ready(self) -> None:
        report = d1_demo.evaluate_d1_demo_report(
            web_report=web_report(),
            power_report=power_report(),
            report_id="d1-unit",
            created_at=FIXED_CREATED_AT,
        )

        self.assertEqual(report["result"], "PASS")
        self.assertTrue(report["ready_for_founder_review"])
        self.assertFalse(report["boundaries"]["hardware_contacted"])
        self.assertFalse(report["boundaries"]["battery_life_claimed"])
        self.assertEqual(report["power"]["counts"]["measured_power_samples"], 3)

    def test_missing_power_report_keeps_d1_demo_at_warn(self) -> None:
        report = d1_demo.evaluate_d1_demo_report(
            web_report=web_report(),
            power_report=None,
            report_id="d1-no-power",
            created_at=FIXED_CREATED_AT,
        )

        self.assertEqual(report["result"], "WARN")
        self.assertFalse(report["ready_for_founder_review"])
        self.assertIn("pwr001_power_report_missing", report["gates"][1]["warnings"])

    def test_failed_power_report_blocks_founder_review(self) -> None:
        report = d1_demo.evaluate_d1_demo_report(
            web_report=web_report(),
            power_report=power_report(status="FAIL", measured_samples=0),
            report_id="d1-failed-power",
            created_at=FIXED_CREATED_AT,
        )

        self.assertEqual(report["result"], "FAIL")
        self.assertFalse(report["ready_for_founder_review"])
        self.assertIn("pwr001_power_report_failed", report["gates"][1]["errors"])
        self.assertIn("pwr001_measured_power_samples_missing", report["gates"][1]["errors"])

    def test_cli_writes_json_and_markdown_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            web_path = tmp_path / "d1_web_api_report.json"
            power_path = tmp_path / "power_curve_report.json"
            output_dir = tmp_path / "out"
            web_path.write_text(json.dumps(web_report()) + "\n", encoding="utf-8")
            power_path.write_text(json.dumps(power_report()) + "\n", encoding="utf-8")

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = d1_demo.main(
                    [
                        "--web-api-report",
                        str(web_path),
                        "--power-curve-report",
                        str(power_path),
                        "--output-dir",
                        str(output_dir),
                        "--report-id",
                        "d1-cli-unit",
                        "--json",
                    ]
                )

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["result"], "PASS")
            self.assertTrue((output_dir / d1_demo.REPORT_JSON).is_file())
            report_md = (output_dir / d1_demo.REPORT_MARKDOWN).read_text(encoding="utf-8")
            self.assertIn("D1 Demo Evidence Report", report_md)
            self.assertIn("Founder-review readiness requires both D1 Web/API gate PASS", report_md)


if __name__ == "__main__":
    unittest.main()

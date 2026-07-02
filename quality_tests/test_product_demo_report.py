from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from quality_tests.test_location_fusion_dataset_export import FIXED_CREATED_AT, kr003_like_export
from scripts import build_product_demo_report as product_demo


def safety_summary() -> dict:
    return {
        "ok": True,
        "demo_version": "egolink.demo.full_safety_loop.v0.5",
        "session_id": "demo-full-unit",
        "event_counts": {
            "motion_event": 1,
            "ask_user_rendered": 1,
            "user_confirmation": 1,
            "safety_event": 1,
            "command_sent": 2,
            "command_ack": 2,
            "location_report": 1,
        },
        "stages": {
            "demo_v0_1": {"passed": True},
            "demo_v0_5": {"passed": True},
        },
        "quality_report": {"passed": True, "quality_score": 0.94, "path": "session_quality_report.json"},
        "replay_report": {"passed": True, "summary": {"replayed_inputs": 3}, "path": "session_replay_report.json"},
        "privacy": {"raw_audio_captured": False, "raw_image_captured": False},
    }


class ProductDemoReportTests(unittest.TestCase):
    def test_builds_warn_report_without_claiming_kr008_release(self) -> None:
        report, samples, manifest, eale_report = product_demo.build_product_demo_report(
            kr003_like_export(),
            safety_summary=safety_summary(),
            created_at=FIXED_CREATED_AT,
        )

        self.assertEqual(report["result"]["status"], "warn")
        self.assertFalse(report["result"]["ready_for_kr008_release"])
        self.assertFalse(report["demo"]["hardware_contacted"])
        self.assertFalse(report["demo"]["vps_contacted"])
        self.assertFalse(report["demo"]["product_ready"])
        self.assertEqual(report["source"]["evidence_mode"], "composite_existing_evidence")
        self.assertEqual(report["flow"]["user_trigger_or_safety_event"]["status"], "pass")
        self.assertEqual(report["flow"]["lte_raw_frame_uplink"]["status"], "pass")
        self.assertEqual(report["flow"]["eale_p0_location_belief"]["status"], "pass")
        self.assertEqual(report["flow"]["web_console_replay_review"]["status"], "not_run")
        self.assertIn("composite_evidence_not_same_run", report["result"]["warnings"])
        self.assertIn("web_console_product_demo_review_pending", report["result"]["warnings"])
        self.assertEqual(report["location"]["state"], "Unknown")
        self.assertIn("gnss_no_fix", report["location"]["failure_modes"])
        self.assertEqual(report["evidence_summary"]["raw_frame_refs"], 3)
        self.assertEqual(len(samples), 1)
        self.assertEqual(manifest["source"]["test_run_id"], "loc-fusion-unit")
        self.assertNotEqual(eale_report["result"]["status"], "fail")

    def test_cli_writes_report_dataset_and_eale_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            export_path = root / "test_run_export.json"
            safety_path = root / "safety_summary.json"
            output_dir = root / "product_demo"
            export_path.write_text(json.dumps(kr003_like_export(), indent=2) + "\n", encoding="utf-8")
            safety_path.write_text(json.dumps(safety_summary(), indent=2) + "\n", encoding="utf-8")

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = product_demo.main(
                    [
                        "--test-run-export",
                        str(export_path),
                        "--safety-demo-summary",
                        str(safety_path),
                        "--output-dir",
                        str(output_dir),
                        "--created-at",
                        FIXED_CREATED_AT,
                        "--json",
                    ]
                )

            payload = json.loads(stdout.getvalue())
            report_json = output_dir / product_demo.REPORT_JSON
            report_md = output_dir / product_demo.REPORT_MARKDOWN
            dataset_dir = output_dir / "location_dataset"

            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["result"]["status"], "warn")
            self.assertTrue(report_json.is_file())
            self.assertTrue(report_md.is_file())
            self.assertTrue((dataset_dir / "samples.jsonl").is_file())
            self.assertTrue((dataset_dir / "manifest.json").is_file())
            self.assertTrue((dataset_dir / "eale_p0_dataset_report.json").is_file())
            self.assertTrue((dataset_dir / "eale_p0_dataset_report.md").is_file())
            self.assertIn("Product Demo Closed Loop Report", report_md.read_text(encoding="utf-8"))
            saved = json.loads(report_json.read_text(encoding="utf-8"))
            self.assertIn("paths", saved)
            self.assertIn("No product readiness claim.", saved["non_claims"])


if __name__ == "__main__":
    unittest.main()

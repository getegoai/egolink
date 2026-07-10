from __future__ import annotations

from contextlib import redirect_stdout
from http.server import ThreadingHTTPServer
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest

from scripts import validate_product_demo_web_review as web_review
from server import message_hub


def product_demo_summary() -> dict:
    return {
        "available": True,
        "status": "warn",
        "candidate": "KR-008 / DEMO-008 Product Demo Closed Loop",
        "ready_for_kr008_release": False,
        "why_not_release_ready": ["web_console_product_demo_review_pending"],
        "warnings": ["web_console_product_demo_review_pending"],
        "test_run_id": "lte011-unit",
        "safety_session_id": "demo-unit",
        "evidence_mode": "composite_existing_evidence",
        "location": {"state": "Unknown", "gnss_fix": False, "gnss_state": "no_fix"},
        "flow": {
            "web_console_replay_review": {"status": "not_run", "summary": "pending"},
        },
        "flow_status_counts": {"pass": 7, "not_run": 1},
        "raw_frame_refs": 3,
        "derived_event_refs": 2,
        "training_readiness": {"model_training_ready": False, "reason": "not_ready"},
        "report_path": "reports/product_demo/kr008-unit/product_demo_report.json",
        "markdown_path": "reports/product_demo/kr008-unit/product_demo_report.md",
    }


def product_demo_report() -> dict:
    summary = product_demo_summary()
    return {
        "demo": {
            "candidate": summary["candidate"],
            "mode": "offline_evidence_composition",
            "product_ready": False,
        },
        "source": {
            "test_run_id": summary["test_run_id"],
            "safety_session_id": summary["safety_session_id"],
            "evidence_mode": summary["evidence_mode"],
            "dataset_samples": 1,
        },
        "result": {
            "status": summary["status"],
            "ready_for_kr008_release": summary["ready_for_kr008_release"],
            "warnings": summary["warnings"],
            "errors": [],
            "why_not_release_ready": summary["why_not_release_ready"],
        },
        "location": summary["location"],
        "flow": {
            "report_export": {"status": "pass", "summary": "report exported"},
            "web_console_replay_review": summary["flow"]["web_console_replay_review"],
        },
        "evidence_summary": {
            "flow_status_counts": summary["flow_status_counts"],
            "raw_frame_refs": summary["raw_frame_refs"],
            "derived_event_refs": summary["derived_event_refs"],
            "training_readiness": summary["training_readiness"],
        },
        "paths": {
            "product_demo_report_json": summary["report_path"],
            "product_demo_report_markdown": summary["markdown_path"],
        },
    }


class ProductDemoWebReviewTests(unittest.TestCase):
    def test_evaluate_passes_web_surface_without_claiming_kr008_release(self) -> None:
        summary = product_demo_summary()
        report = web_review.evaluate_product_demo_web_review(
            health={"ok": True, "service": "egolink-message-hub", "time": "2026-07-02T00:00:00Z"},
            latest={"product_demo": summary},
            state={"product_demo": summary},
            dashboard_html="<html>Product Demo productDemoPanel KR-008 DEMO-008</html>",
            hub_url="http://127.0.0.1:8790",
            review_id="demo010-unit",
        )

        self.assertEqual(report["result"], "PASS")
        self.assertFalse(report["kr008_release_ready"])
        self.assertFalse(report["scope"]["hardware_contacted"])
        self.assertFalse(report["scope"]["commands_sent"])
        self.assertIn("web_console_product_demo_review_pending", report["release_blockers"])
        self.assertIn("underlying_product_demo_web_flow_still_pending", report["warnings"])
        self.assertEqual(report["product_demo"]["web_console_replay_review_status"], "not_run")
        self.assertTrue(all(item["status"] == "PASS" for item in report["gates"]))

    def test_missing_dashboard_marker_fails_explainably(self) -> None:
        summary = product_demo_summary()
        report = web_review.evaluate_product_demo_web_review(
            health={"ok": True},
            latest={"product_demo": summary},
            state={"product_demo": summary},
            dashboard_html="<html>Product Demo KR-008</html>",
            hub_url="http://127.0.0.1:8790",
            review_id="demo010-missing-marker",
        )

        self.assertEqual(report["result"], "FAIL")
        self.assertIn("dashboard_product_demo_markers_missing", report["errors"])

    def test_cli_writes_report_against_token_protected_local_server(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report_root = tmp_path / "product_demo"
            report_dir = report_root / "kr008-unit"
            report_dir.mkdir(parents=True)
            (report_dir / "product_demo_report.json").write_text(
                json.dumps(product_demo_report(), indent=2) + "\n",
                encoding="utf-8",
            )
            token_file = tmp_path / "token.txt"
            token_file.write_text("secret-token\n", encoding="utf-8")
            output_dir = tmp_path / "review"
            store = message_hub.MessageHubStore(tmp_path / "hub.db")
            server = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                message_hub.make_handler(store, token="secret-token", product_demo_root=report_root),
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    exit_code = web_review.main(
                        [
                            "--hub-url",
                            base_url,
                            "--token-file",
                            str(token_file),
                            "--output-dir",
                            str(output_dir),
                            "--review-id",
                            "demo010-cli-unit",
                            "--json",
                        ]
                    )
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["result"], "PASS")
            self.assertNotIn("secret-token", stdout.getvalue())
            self.assertTrue((output_dir / "product_demo_web_review_report.json").is_file())
            self.assertTrue((output_dir / "product_demo_web_review_report.md").is_file())
            self.assertFalse(payload["kr008_release_ready"])


if __name__ == "__main__":
    unittest.main()

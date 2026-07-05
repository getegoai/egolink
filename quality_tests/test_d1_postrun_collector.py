from __future__ import annotations

from contextlib import redirect_stdout
from http.server import ThreadingHTTPServer
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest

from pc_simulator import protocol
from scripts import collect_d1_postrun as collector
from server import message_hub


DEVICE_ID = "ego-link-r1-connectivity-001"
TEST_RUN_ID = "d1-postrun-unit-message-run"
TOKEN = "unit-token"


def add_d1_messages(store: message_hub.MessageHubStore) -> None:
    store.create_test_run({"test_run_id": TEST_RUN_ID, "created_at": "2026-07-05T01:00:00+00:00"})
    store.ingest(
        DEVICE_ID,
        "heartbeat",
        protocol.status_message(
            DEVICE_ID,
            "2026-07-05T01:00:00+00:00",
            1,
            test_run_id=TEST_RUN_ID,
            fw_version="0.1.0-d1-periodic-location",
            battery=91,
            link_type="lte",
            guard_mode="child_safety",
            queue_size=0,
            transport={"type": "lte"},
            power={
                "battery_mv": 4090,
                "soc_pct": 91,
                "charging": False,
                "source": "max17048_i2c",
                "source_status": "measured",
                "evidence_status": "measured",
                "state": "guarding",
            },
        ),
    )
    store.ingest(
        DEVICE_ID,
        "telemetry",
        protocol.event_message(
            DEVICE_ID,
            "2026-07-05T02:00:00+00:00",
            2,
            "location_report",
            "normal",
            test_run_id=TEST_RUN_ID,
            fw_version="0.1.0-d1-periodic-location",
            source="sim7670g_firmware_gnss",
            source_status="observed",
            fix=False,
            gnss_state="no_fix",
            power={
                "battery_mv": 4070,
                "soc_pct": 90,
                "charging": False,
                "source": "max17048_i2c",
                "source_status": "measured",
                "evidence_status": "measured",
                "state": "upload",
            },
            transport={"type": "lte"},
            reliability={
                "network": {
                    "raw_post_attempt_count": 2,
                    "raw_post_success_count": 2,
                    "raw_post_failure_count": 0,
                }
            },
        ),
    )
    store.ingest(
        DEVICE_ID,
        "telemetry",
        protocol.event_message(
            DEVICE_ID,
            "2026-07-05T03:00:00+00:00",
            3,
            "location_observation",
            "normal",
            test_run_id=TEST_RUN_ID,
            fw_version="0.1.0-d1-periodic-location",
            source="d1_postrun_unit",
            source_status="observed",
            gnss={"fix": False, "state": "no_fix", "reason_code": "GNSS_NO_FIX"},
            cell={"rat": "LTE", "cell_id": "180571649", "registration_state": "registered_home"},
            lte={"registered": True, "pdp_active": True, "reason_code": "LTE_READY", "pdp_state": "active"},
            imu={"motion": "stationary", "confidence": 0.91, "evidence_status": "observed"},
            power={
                "battery_mv": 4050,
                "soc_pct": 89,
                "charging": False,
                "source": "max17048_i2c",
                "source_status": "measured",
                "evidence_status": "measured",
                "state": "upload",
            },
            transport={"type": "lte"},
            reliability={
                "network": {
                    "raw_post_attempt_count": 3,
                    "raw_post_success_count": 3,
                    "raw_post_failure_count": 0,
                }
            },
            location_belief={
                "state": "Coarse",
                "radius_m": 250,
                "confidence": 0.68,
                "source": ["cell_lte"],
                "reason": "unit_test_cell_observation",
            },
        ),
    )


class D1PostrunCollectorTests(unittest.TestCase):
    def test_collector_composes_postrun_reports_without_secret_leak(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            token_file = root / "token.txt"
            token_file.write_text(f"{TOKEN}\n", encoding="utf-8")
            store = message_hub.MessageHubStore(root / "hub.db")
            add_d1_messages(store)
            server = ThreadingHTTPServer(("127.0.0.1", 0), message_hub.make_handler(store, token=TOKEN))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    exit_code = collector.main(
                        [
                            "--run-id",
                            "D1-POSTRUN-unit",
                            "--hub-url",
                            base_url,
                            "--token-file",
                            str(token_file),
                            "--device-id",
                            DEVICE_ID,
                            "--message-test-run-id",
                            TEST_RUN_ID,
                            "--output-root",
                            str(root / "postrun"),
                            "--web-api-output-dir",
                            str(root / "web"),
                            "--power-output-dir",
                            str(root / "power"),
                            "--d1-demo-output-dir",
                            str(root / "demo"),
                            "--db",
                            str(root / "candidates.db"),
                            "--data-flywheel-pipeline-output-root",
                            str(root / "pipeline"),
                            "--data-flywheel-output-root",
                            str(root / "flywheel"),
                            "--dataset-output-root",
                            str(root / "datasets"),
                            "--experiment-output-root",
                            str(root / "experiments"),
                            "--min-duration-hours",
                            "2",
                            "--battery-capacity-mah",
                            "1000",
                            "--created-at",
                            "2026-07-05T03:30:00+00:00",
                            "--json",
                        ]
                    )
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

            payload = json.loads(stdout.getvalue())
            summary_path = root / "postrun" / "D1-POSTRUN-unit" / collector.SUMMARY_JSON
            summary_md = root / "postrun" / "D1-POSTRUN-unit" / collector.SUMMARY_MARKDOWN

            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["schema_version"], collector.SCHEMA_VERSION)
            self.assertEqual(payload["result"], "WARN")
            self.assertEqual(payload["components"]["web_api"]["result"], "PASS")
            self.assertIn(payload["components"]["power_curve"]["result"], {"PASS", "WARN"})
            self.assertIn(payload["components"]["d1_demo"]["result"], {"PASS", "WARN"})
            self.assertGreaterEqual(payload["components"]["power_curve"]["counts"]["measured_power_samples"], 1)
            self.assertEqual(payload["components"]["data_flywheel_pipeline"]["status"], "needs_recordings")
            self.assertEqual(
                payload["components"]["data_flywheel_pipeline"]["training_experiment"]["status"],
                "blocked_dataset_not_ready",
            )
            self.assertFalse(payload["scope"]["hardware_contacted"])
            self.assertFalse(payload["scope"]["commands_sent"])
            self.assertFalse(payload["scope"]["model_training_started"])
            self.assertTrue(summary_path.is_file())
            self.assertTrue(summary_md.is_file())
            self.assertTrue((root / "web" / "d1_web_api_report.json").is_file())
            self.assertTrue((root / "power" / "test_run_export.json").is_file())
            self.assertTrue((root / "power" / "power_curve_report.json").is_file())
            self.assertTrue((root / "demo" / "d1_demo_report.json").is_file())
            self.assertTrue(
                (root / "pipeline" / "D1-POSTRUN-unit-data-pipeline" / "data_flywheel_pipeline_run.json").is_file()
            )
            self.assertTrue((root / "datasets" / "D1-POSTRUN-unit-dataset" / "training_dataset_manifest.json").is_file())
            self.assertTrue(
                (root / "experiments" / "D1-POSTRUN-unit-data-pipeline-experiment" / "training_experiment_plan.json").is_file()
            )
            output_text = stdout.getvalue() + summary_path.read_text(encoding="utf-8") + summary_md.read_text(encoding="utf-8")
            self.assertNotIn(TOKEN, output_text)
            self.assertNotIn(str(root / "candidates.db"), output_text)

    def test_collector_skip_power_keeps_summary_writeable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = message_hub.MessageHubStore(root / "hub.db")
            add_d1_messages(store)
            server = ThreadingHTTPServer(("127.0.0.1", 0), message_hub.make_handler(store))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    exit_code = collector.main(
                        [
                            "--run-id",
                            "D1-POSTRUN-skip-power",
                            "--hub-url",
                            base_url,
                            "--device-id",
                            DEVICE_ID,
                            "--skip-power",
                            "--skip-data-flywheel",
                            "--output-root",
                            str(root / "postrun"),
                            "--web-api-output-dir",
                            str(root / "web"),
                            "--d1-demo-output-dir",
                            str(root / "demo"),
                            "--json",
                        ]
                    )
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

            payload = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["result"], "WARN")
        self.assertEqual(payload["components"]["web_api"]["result"], "PASS")
        self.assertEqual(payload["components"]["power_curve"]["status"], "skipped")
        self.assertEqual(payload["components"]["power_curve"]["reason"], "skip_power_requested")
        self.assertEqual(payload["components"]["d1_demo"]["result"], "WARN")
        self.assertEqual(payload["components"]["data_flywheel_pipeline"]["status"], "skipped")


if __name__ == "__main__":
    unittest.main()

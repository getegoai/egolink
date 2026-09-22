from __future__ import annotations

from pathlib import Path
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer
import unittest
from unittest import mock

from pc_simulator import protocol
from scripts import observe_field_readiness
from server import message_hub


class FieldReadinessObserverTests(unittest.TestCase):
    def setUp(self) -> None:
        # The observer integrates with HTTP and a real temporary store, but
        # optional report availability must not depend on an operator's reports/.
        summaries = {
            "load_latest_field_results": {
                "available": True, "status": "pass", "report_count": 1,
                "reports": [{"kind": "unit_fixture", "status": "pass"}],
            },
            "load_latest_data_flywheel_status": {
                "available": True, "status": "unit_fixture",
                "counts": {}, "readiness": {"model_training_ready": False},
            },
        }
        for name, summary in summaries.items():
            patcher = mock.patch.object(message_hub, name, return_value=summary)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_missing_optional_reports_still_warn(self) -> None:
        sample = {
            "ok": True, "health_ok": True, "device_found": True, "field_ready": True,
            "dashboard": {"markers_present": True},
            "data_flywheel": {"available": False}, "field_results": {"available": False},
        }
        report = observe_field_readiness.evaluate_samples(
            [sample], run_id="field-readiness-no-reports", hub_url="http://127.0.0.1",
            device_id="ego-link-r1-test", require_fresh=True,
            require_dashboard_markers=True, min_success_samples=1,
        )
        self.assertEqual(report["result"], "WARN")
        self.assertEqual(report["errors"], [])
        self.assertEqual(set(report["warnings"]), {
            "data_flywheel_summary_not_available", "field_results_summary_not_available",
        })

    def test_observer_passes_on_fresh_server_dashboard_without_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            store = message_hub.MessageHubStore(tmp_path / "hub.db")
            self._seed_ready_device(store, "ego-link-r1-test")
            requested_paths: list[str] = []
            base_handler = message_hub.make_handler(store)

            class RecordingHandler(base_handler):
                def do_GET(self) -> None:
                    requested_paths.append(self.path)
                    super().do_GET()

            server = ThreadingHTTPServer(("127.0.0.1", 0), RecordingHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                report = observe_field_readiness.observe_field_readiness(
                    hub_url=f"http://127.0.0.1:{server.server_port}",
                    device_id="ego-link-r1-test",
                    token=None,
                    run_id="field-readiness-unit",
                    output_dir=tmp_path / "report",
                    duration_sec=0.0,
                    poll_interval_sec=0.01,
                    request_timeout_sec=5.0,
                )
                commands = store.list_commands("ego-link-r1-test")
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

            self.assertEqual(report["result"], "PASS")
            self.assertTrue(report["latest"]["health_ok"])
            self.assertTrue(report["latest"]["field_ready"])
            self.assertEqual(report["latest"]["field_readiness"]["reason"], "fresh_periodic_upload")
            self.assertTrue(report["latest"]["dashboard"]["markers_present"])
            self.assertIn("/engineering", requested_paths)
            self.assertNotIn("/", requested_paths)
            self.assertEqual(commands, [])
            self.assertTrue((tmp_path / "report" / "field_readiness_report.json").is_file())
            self.assertTrue((tmp_path / "report" / "field_readiness_report.md").is_file())
            self.assertTrue((tmp_path / "report" / "field_readiness_samples.jsonl").is_file())
            self.assertTrue((tmp_path / "report" / "field_readiness_status.json").is_file())

    def test_observer_fails_when_target_device_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            store = message_hub.MessageHubStore(tmp_path / "hub.db")
            server = ThreadingHTTPServer(("127.0.0.1", 0), message_hub.make_handler(store))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with self.assertRaisesRegex(observe_field_readiness.FieldValidationError, "target_device_not_found"):
                    observe_field_readiness.observe_field_readiness(
                        hub_url=f"http://127.0.0.1:{server.server_port}",
                        device_id="ego-link-r1-test",
                        token=None,
                        run_id="field-readiness-missing-device",
                        output_dir=tmp_path / "report",
                        duration_sec=0.0,
                        poll_interval_sec=0.01,
                        request_timeout_sec=5.0,
                    )
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

            saved = (tmp_path / "report" / "field_readiness_report.json").read_text(encoding="utf-8")
            self.assertIn("target_device_not_found", saved)

    def test_long_observation_records_multiple_samples_and_upload_progress(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            store = message_hub.MessageHubStore(tmp_path / "hub.db")
            self._seed_ready_device(store, "ego-link-r1-test", seq=1)
            server = ThreadingHTTPServer(("127.0.0.1", 0), message_hub.make_handler(store))
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            device_thread = threading.Thread(
                target=self._advance_device,
                args=(store, "ego-link-r1-test"),
                daemon=True,
            )
            try:
                device_thread.start()
                report = observe_field_readiness.observe_field_readiness(
                    hub_url=f"http://127.0.0.1:{server.server_port}",
                    device_id="ego-link-r1-test",
                    token=None,
                    run_id="field-readiness-window",
                    output_dir=tmp_path / "report",
                    duration_sec=0.25,
                    poll_interval_sec=0.05,
                    request_timeout_sec=5.0,
                )
            finally:
                device_thread.join(timeout=2)
                server.shutdown()
                server_thread.join(timeout=5)
                server.server_close()

            self.assertEqual(report["result"], "PASS")
            self.assertGreaterEqual(report["sample_count"], 2)
            self.assertTrue(report["new_upload_observed"])
            samples = (tmp_path / "report" / "field_readiness_samples.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertGreaterEqual(len(samples), 2)

    @staticmethod
    def _seed_ready_device(store: message_hub.MessageHubStore, device_id: str, *, seq: int = 10) -> None:
        store.ingest(
            device_id,
            "heartbeat",
            protocol.status_message(
                device_id,
                "2026-07-10T00:00:00Z",
                seq,
                fw_version="0.1.0-field-readiness-test",
                battery=87,
                battery_mv=3920,
                charging=False,
                link_type="lte",
                guard_mode="child_safety",
                queue_size=0,
                transport={"type": "lte", "rtt_ms": 80},
                runtime={"boot_id": "boot-unit", "uptime_s": 12, "watchdog_count": 0},
                power={"battery_mv": 3920, "soc_pct": 87, "charging": False, "source_status": "mock"},
            ),
        )
        for offset, point in enumerate(((31.2000, 121.4000), (31.2002, 121.4002)), start=1):
            store.ingest(
                device_id,
                "telemetry",
                protocol.event_message(
                    device_id,
                    f"2026-07-10T00:00:0{offset}Z",
                    seq + offset,
                    "location_report",
                    "normal",
                    fw_version="0.1.0-field-readiness-test",
                    test_run_id="field-readiness-unit",
                    source="unit_field_readiness",
                    source_status="observed",
                    fix=True,
                    lat=point[0],
                    lon=point[1],
                    gnss_state="fix",
                    gnss={"fix": True, "hdop": 0.9, "satellites": 11},
                    cell={"rat": "LTE", "cell_id": "unit-cell", "registration_state": "registered_home"},
                    imu={"motion": "walking", "confidence": 0.8, "source_status": "mock"},
                    power={"battery_mv": 3915 - offset, "soc_pct": 86, "evidence_status": "mock"},
                    transport={"type": "lte"},
                    reliability={
                        "network": {
                            "raw_post_attempt_count": seq + offset,
                            "raw_post_success_count": seq + offset,
                            "raw_post_failure_count": 0,
                        }
                    },
                ),
            )

    @staticmethod
    def _advance_device(store: message_hub.MessageHubStore, device_id: str) -> None:
        time.sleep(0.12)
        store.ingest(
            device_id,
            "telemetry",
            protocol.event_message(
                device_id,
                "2026-07-10T00:00:09Z",
                99,
                "location_report",
                "normal",
                fw_version="0.1.0-field-readiness-test",
                test_run_id="field-readiness-unit",
                source="unit_field_readiness",
                source_status="observed",
                fix=True,
                lat=31.2005,
                lon=121.4005,
                gnss_state="fix",
                gnss={"fix": True, "hdop": 0.9, "satellites": 11},
                cell={"rat": "LTE", "cell_id": "unit-cell", "registration_state": "registered_home"},
                imu={"motion": "walking", "confidence": 0.8, "source_status": "mock"},
                power={"battery_mv": 3910, "soc_pct": 86, "evidence_status": "mock"},
                transport={"type": "lte"},
                reliability={
                    "network": {
                        "raw_post_attempt_count": 99,
                        "raw_post_success_count": 99,
                        "raw_post_failure_count": 0,
                    }
                },
            ),
        )


if __name__ == "__main__":
    unittest.main()

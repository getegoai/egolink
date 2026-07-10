from __future__ import annotations

from pathlib import Path
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer
import unittest

from pc_simulator import protocol
from scripts import validate_fw002_location_loop
from server import message_hub


class FW002GnssScaffoldTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.app_main = (self.repo_root / "firmware" / "mqtt_heartbeat" / "main" / "app_main.c").read_text(
            encoding="utf-8"
        )
        self.kconfig = (
            self.repo_root / "firmware" / "mqtt_heartbeat" / "main" / "Kconfig.projbuild"
        ).read_text(encoding="utf-8")
        self.protocol_doc = (self.repo_root / "docs" / "development" / "PROTOCOL.md").read_text(encoding="utf-8")

    def test_firmware_has_request_location_scaffold_shape(self) -> None:
        for token in [
            "config EGOLINK_GNSS_LOCATION_SCAFFOLD_ENABLED",
            "build_location_report_payload",
            "message_hub_publish_location_report",
            '\\"event_type\\":\\"location_report\\"',
            "firmware_gnss_scaffold",
            "source_status = \"unverified\"",
            "bool fix = false",
            "driver_not_integrated",
            '\\"location_request_cmd_id\\":\\"%s\\"',
            'strcmp(cmd_name, "request_location")',
            "firmware uploaded location_report scaffold",
        ]:
            with self.subTest(token=token):
                self.assertIn(token, self.app_main + self.kconfig)

    def test_protocol_documents_request_location_and_scaffold_boundary(self) -> None:
        self.assertIn("request_location", self.protocol_doc)
        self.assertIn("location_request_cmd_id", self.protocol_doc)
        self.assertIn("driver_not_integrated", self.protocol_doc)
        self.assertIn("source_status", self.protocol_doc)

    def test_validation_script_observes_location_report_and_ack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            server = ThreadingHTTPServer(("127.0.0.1", 0), message_hub.make_handler(store))
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            hub_url = f"http://127.0.0.1:{server.server_port}"
            try:
                device_thread = threading.Thread(
                    target=self._fake_fw002_http_device,
                    args=(hub_url, "ego-link-r1-test", "field-fw002-unit"),
                    daemon=True,
                )
                device_thread.start()

                report = validate_fw002_location_loop.run_validation(
                    hub_url=hub_url,
                    device_id="ego-link-r1-test",
                    token=None,
                    output_dir=Path(tmp) / "report",
                    test_run_id="field-fw002-unit",
                    board_id="connectivity-node-001",
                    connection_path="independent_power_usb_disconnected",
                    timeout_sec=5.0,
                    poll_interval_sec=0.05,
                    require_fix=False,
                )
            finally:
                server.shutdown()
                server_thread.join(timeout=5)
                server.server_close()

            self.assertEqual(report["result"], "PASS")
            self.assertEqual(report["command"]["cmd"], "request_location")
            self.assertEqual(report["command"]["status"], "ok")
            self.assertEqual(report["location_report"]["event_type"], "location_report")
            self.assertEqual(report["location_report"]["test_run_id"], "field-fw002-unit")
            self.assertIs(report["location_report"]["fix"], False)
            self.assertEqual(report["location_report"]["source_status"], "unverified")
            self.assertTrue((Path(tmp) / "report" / "field_validation_report.json").is_file())
            self.assertTrue((Path(tmp) / "report" / "field_validation_report.md").is_file())
            self.assertTrue((Path(tmp) / "report" / "test_run_export.json").is_file())

    def test_validation_script_writes_failure_report_when_fix_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            server = ThreadingHTTPServer(("127.0.0.1", 0), message_hub.make_handler(store))
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            hub_url = f"http://127.0.0.1:{server.server_port}"
            try:
                device_thread = threading.Thread(
                    target=self._fake_fw002_http_device,
                    args=(hub_url, "ego-link-r1-test", "field-fw002-require-fix"),
                    daemon=True,
                )
                device_thread.start()

                report = validate_fw002_location_loop.run_validation(
                    hub_url=hub_url,
                    device_id="ego-link-r1-test",
                    token=None,
                    output_dir=Path(tmp) / "report",
                    test_run_id="field-fw002-require-fix",
                    board_id="connectivity-node-001",
                    connection_path="independent_power_usb_disconnected",
                    timeout_sec=5.0,
                    poll_interval_sec=0.05,
                    require_fix=True,
                )
            finally:
                server.shutdown()
                server_thread.join(timeout=5)
                server.server_close()

            self.assertEqual(report["result"], "FAIL")
            self.assertIn("location_report did not contain a real fix", report["errors"][0])
            self.assertIs(report["location_report"]["fix"], False)
            self.assertTrue((Path(tmp) / "report" / "field_validation_report.json").is_file())
            self.assertTrue((Path(tmp) / "report" / "field_validation_report.md").is_file())
            self.assertTrue((Path(tmp) / "report" / "test_run_export.json").is_file())

    def test_validation_script_writes_failure_report_for_fixed_unverified_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            server = ThreadingHTTPServer(("127.0.0.1", 0), message_hub.make_handler(store))
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            hub_url = f"http://127.0.0.1:{server.server_port}"
            try:
                device_thread = threading.Thread(
                    target=self._fake_fw002_http_device,
                    args=(hub_url, "ego-link-r1-test", "field-fw002-fixed-unverified"),
                    kwargs={"fix": True, "gnss_state": "fix", "lat": 12.3456789, "lon": 98.7654321},
                    daemon=True,
                )
                device_thread.start()

                report = validate_fw002_location_loop.run_validation(
                    hub_url=hub_url,
                    device_id="ego-link-r1-test",
                    token=None,
                    output_dir=Path(tmp) / "report",
                    test_run_id="field-fw002-fixed-unverified",
                    board_id="connectivity-node-001",
                    connection_path="independent_power_usb_disconnected",
                    timeout_sec=5.0,
                    poll_interval_sec=0.05,
                    require_fix=True,
                )
            finally:
                server.shutdown()
                server_thread.join(timeout=5)
                server.server_close()

            self.assertEqual(report["result"], "FAIL")
            self.assertIn("fixed location_report must use verified or observed source_status", report["errors"][0])
            self.assertIs(report["location_report"]["fix"], True)
            self.assertEqual(report["location_report"]["source_status"], "unverified")
            self.assertTrue((Path(tmp) / "report" / "field_validation_report.json").is_file())

    def test_validation_script_can_reuse_existing_test_run_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            server = ThreadingHTTPServer(("127.0.0.1", 0), message_hub.make_handler(store))
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            hub_url = f"http://127.0.0.1:{server.server_port}"
            try:
                client = validate_fw002_location_loop.HubClient(hub_url)
                client.post(
                    "/api/v1/test-runs",
                    {
                        "test_run_id": "field-fw002-reused",
                        "task_id": "FW-002",
                        "board_id": "connectivity-node-001",
                        "device_id": "ego-link-r1-test",
                    },
                )
                device_thread = threading.Thread(
                    target=self._fake_fw002_http_device,
                    args=(hub_url, "ego-link-r1-test", "field-fw002-reused"),
                    daemon=True,
                )
                device_thread.start()

                report = validate_fw002_location_loop.run_validation(
                    hub_url=hub_url,
                    device_id="ego-link-r1-test",
                    token=None,
                    output_dir=Path(tmp) / "report",
                    test_run_id="field-fw002-reused",
                    board_id="connectivity-node-001",
                    connection_path="independent_power_usb_disconnected",
                    timeout_sec=5.0,
                    poll_interval_sec=0.05,
                    require_fix=False,
                )
            finally:
                server.shutdown()
                server_thread.join(timeout=5)
                server.server_close()

            self.assertEqual(report["result"], "PASS")
            self.assertTrue(report["test_run"]["reused_existing"])
            self.assertEqual(report["command"]["cmd"], "request_location")

    @staticmethod
    def _fake_fw002_http_device(
        hub_url: str,
        device_id: str,
        test_run_id: str,
        *,
        fix: bool = False,
        gnss_state: str = "driver_not_integrated",
        lat: float | None = None,
        lon: float | None = None,
    ) -> None:
        client = validate_fw002_location_loop.HubClient(hub_url)
        time.sleep(0.1)
        client.post("/api/v1/devices/register", {"device_id": device_id, "fw_version": "0.1.0-fw002-test"})
        heartbeat = protocol.status_message(
            device_id,
            "uptime_ms:1000",
            1,
            fw_version="0.1.0-fw002-test",
            battery=87,
            charging=False,
            link_type="mock_4g_over_wifi",
            rssi=-61,
            modem_state="mock_data_ready",
            gnss_state="driver_not_integrated",
            guard_mode="child_safety",
            queue_size=0,
        )
        heartbeat["test_run_id"] = test_run_id
        client.post(f"/api/v1/devices/{device_id}/heartbeat", heartbeat)

        deadline = time.monotonic() + 4.0
        while time.monotonic() < deadline:
            commands = client.get(f"/api/v1/devices/{device_id}/commands/poll").get("commands") or []
            if commands:
                command = commands[0]
                cmd_id = str(command["cmd_id"])
                location = protocol.event_message(
                    device_id,
                    "uptime_ms:1200",
                    2,
                    "location_report",
                    "normal",
                    fw_version="0.1.0-fw002-test",
                    source="firmware_gnss_scaffold",
                    source_status="unverified",
                    fix=fix,
                    gnss_state=gnss_state,
                    gnss_source="sim7670g_scaffold",
                    gnss_driver="not_integrated",
                    lat=lat,
                    lon=lon,
                    satellites=6 if fix else 0,
                    hdop=1.3 if fix else None,
                    location_request_cmd_id=cmd_id,
                    test_run_id=test_run_id,
                )
                client.post(f"/api/v1/devices/{device_id}/telemetry", location)
                ack = protocol.ack_message(device_id, "uptime_ms:1300", 3, cmd_id, "ok")
                ack["fw_version"] = "0.1.0-fw002-test"
                ack["message"] = "firmware uploaded location_report scaffold"
                ack["test_run_id"] = test_run_id
                client.post(f"/api/v1/devices/{device_id}/commands/{cmd_id}/ack", ack)
                return
            time.sleep(0.05)


if __name__ == "__main__":
    unittest.main()

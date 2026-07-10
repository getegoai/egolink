from __future__ import annotations

from pathlib import Path
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer
import unittest

from pc_simulator import protocol
from scripts import validate_fw001_hw_loop
from server import message_hub


class FW001HardwareValidationScriptTests(unittest.TestCase):
    def test_validation_script_observes_heartbeat_queues_command_and_exports_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            server = ThreadingHTTPServer(("127.0.0.1", 0), message_hub.make_handler(store))
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            hub_url = f"http://127.0.0.1:{server.server_port}"
            try:
                device_thread = threading.Thread(
                    target=self._fake_fw001_http_device,
                    args=(hub_url, "ego-link-r1-test", "field-r1-unit"),
                    daemon=True,
                )
                device_thread.start()

                report = validate_fw001_hw_loop.run_validation(
                    hub_url=hub_url,
                    device_id="ego-link-r1-test",
                    token=None,
                    output_dir=Path(tmp) / "report",
                    test_run_id="field-r1-unit",
                    board_id="connectivity-node-001",
                    connection_path="independent_power_usb_disconnected",
                    timeout_sec=5.0,
                    poll_interval_sec=0.05,
                    command_name="set_report_interval",
                    interval_ms=10000,
                )
            finally:
                server.shutdown()
                server_thread.join(timeout=5)
                server.server_close()

            self.assertEqual(report["result"], "PASS")
            self.assertEqual(report["fresh_heartbeat"]["test_run_id"], "field-r1-unit")
            self.assertEqual(report["command"]["status"], "ok")
            self.assertEqual(report["command"]["ack"]["test_run_id"], "field-r1-unit")
            self.assertTrue((Path(tmp) / "report" / "field_validation_report.json").is_file())
            self.assertTrue((Path(tmp) / "report" / "field_validation_report.md").is_file())
            self.assertTrue((Path(tmp) / "report" / "test_run_export.json").is_file())

    @staticmethod
    def _fake_fw001_http_device(hub_url: str, device_id: str, test_run_id: str) -> None:
        client = validate_fw001_hw_loop.HubClient(hub_url)
        time.sleep(0.1)
        client.post("/api/v1/devices/register", {"device_id": device_id, "fw_version": "0.1.0-test"})
        heartbeat = protocol.status_message(
            device_id,
            "uptime_ms:1000",
            1,
            fw_version="0.1.0-test",
            battery=87,
            charging=False,
            link_type="mock_4g_over_wifi",
            rssi=-61,
            modem_state="mock_data_ready",
            gnss_state="mock_fix",
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
                ack = protocol.ack_message(device_id, "uptime_ms:1200", 2, str(command["cmd_id"]), "ok")
                ack["fw_version"] = "0.1.0-test"
                ack["test_run_id"] = test_run_id
                client.post(f"/api/v1/devices/{device_id}/commands/{command['cmd_id']}/ack", ack)
                return
            time.sleep(0.05)


if __name__ == "__main__":
    unittest.main()

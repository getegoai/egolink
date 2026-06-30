from __future__ import annotations

import json
from pathlib import Path
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer
import unittest

from pc_simulator import protocol
from scripts import validate_lte_command_loop
from scripts.validate_fw001_hw_loop import FieldValidationError, HubClient
from server import message_hub


class LteCommandLoopValidationTests(unittest.TestCase):
    def test_validation_accepts_lte_marked_command_ack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            server = ThreadingHTTPServer(("127.0.0.1", 0), message_hub.make_handler(store))
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            hub_url = f"http://127.0.0.1:{server.server_port}"
            device_thread = threading.Thread(
                target=self._poll_and_ack_once,
                args=(hub_url,),
                kwargs={
                    "device_id": "ego-link-r1-test",
                    "fw_version": "0.1.0-lte003-command-loop",
                    "test_run_id": "lte003-unit",
                    "transport_type": "lte",
                    "poll_reason_code": "LTE_HTTP_OK",
                    "poll_status_code": 200,
                },
                daemon=True,
            )
            try:
                device_thread.start()
                report = validate_lte_command_loop.validate_lte_command_loop(
                    hub_url=hub_url,
                    device_id="ego-link-r1-test",
                    token=None,
                    output_dir=Path(tmp) / "report",
                    test_run_id="lte003-unit",
                    board_id="connectivity-node-001",
                    connection_path="independent_power_usb_disconnected",
                    timeout_sec=1.0,
                    poll_interval_sec=0.05,
                    expected_fw_version="0.1.0-lte003-command-loop",
                    command_name="set_report_interval",
                    interval_ms=10000,
                )
            finally:
                device_thread.join(timeout=2)
                server.shutdown()
                server_thread.join(timeout=5)
                server.server_close()

            self.assertEqual(report["result"], "PASS")
            self.assertEqual(report["ack_summary"]["transport_type"], "lte")
            self.assertEqual(report["ack_summary"]["poll_reason_code"], "LTE_HTTP_OK")
            self.assertTrue((Path(tmp) / "report" / "lte_command_loop_report.json").is_file())
            self.assertTrue((Path(tmp) / "report" / "lte_command_loop_report.md").is_file())
            self.assertTrue((Path(tmp) / "report" / "commands.json").is_file())
            self.assertTrue((Path(tmp) / "report" / "test_run_export.json").is_file())

    def test_validation_accepts_explicit_firmware_ack_test_run_id_for_repeat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            server = ThreadingHTTPServer(("127.0.0.1", 0), message_hub.make_handler(store))
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            hub_url = f"http://127.0.0.1:{server.server_port}"
            device_thread = threading.Thread(
                target=self._poll_and_ack_once,
                args=(hub_url,),
                kwargs={
                    "device_id": "ego-link-r1-test",
                    "fw_version": "0.1.0-fw003-raw-command-loop",
                    "test_run_id": "fw003-build-unit",
                    "transport_type": "lte",
                    "poll_reason_code": "LTE_HTTP_OK",
                    "poll_status_code": 200,
                },
                daemon=True,
            )
            try:
                device_thread.start()
                report = validate_lte_command_loop.validate_lte_command_loop(
                    hub_url=hub_url,
                    device_id="ego-link-r1-test",
                    token=None,
                    output_dir=Path(tmp) / "report",
                    test_run_id="raw-lte-repeat-unit",
                    board_id="connectivity-node-001",
                    connection_path="independent_power_usb_disconnected",
                    timeout_sec=1.0,
                    poll_interval_sec=0.05,
                    expected_fw_version="0.1.0-fw003-raw-command-loop",
                    expected_ack_test_run_id="fw003-build-unit",
                    command_name="set_report_interval",
                    interval_ms=10000,
                )
            finally:
                device_thread.join(timeout=2)
                server.shutdown()
                server_thread.join(timeout=5)
                server.server_close()

            self.assertEqual(report["result"], "PASS")
            self.assertEqual(report["test_run_id"], "raw-lte-repeat-unit")
            self.assertEqual(report["expected_ack_test_run_id"], "fw003-build-unit")
            self.assertEqual(report["effective_expected_ack_test_run_id"], "fw003-build-unit")
            self.assertEqual(report["ack_summary"]["ack_test_run_id"], "fw003-build-unit")

    def test_validation_can_require_lte_location_report_for_request_location(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            server = ThreadingHTTPServer(("127.0.0.1", 0), message_hub.make_handler(store))
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            hub_url = f"http://127.0.0.1:{server.server_port}"
            device_thread = threading.Thread(
                target=self._poll_and_ack_once,
                args=(hub_url,),
                kwargs={
                    "device_id": "ego-link-r1-test",
                    "fw_version": "0.1.0-lte004-raw-lte-location",
                    "test_run_id": "lte004-unit",
                    "transport_type": "lte",
                    "poll_reason_code": "LTE_HTTP_OK",
                    "poll_status_code": 200,
                    "post_location_report": True,
                },
                daemon=True,
            )
            try:
                device_thread.start()
                report = validate_lte_command_loop.validate_lte_command_loop(
                    hub_url=hub_url,
                    device_id="ego-link-r1-test",
                    token=None,
                    output_dir=Path(tmp) / "report",
                    test_run_id="lte004-unit",
                    board_id="connectivity-node-001",
                    connection_path="independent_power_usb_disconnected",
                    timeout_sec=1.0,
                    poll_interval_sec=0.05,
                    expected_fw_version="0.1.0-lte004-raw-lte-location",
                    command_name="request_location",
                    interval_ms=10000,
                    require_location_report=True,
                )
            finally:
                device_thread.join(timeout=2)
                server.shutdown()
                server_thread.join(timeout=5)
                server.server_close()

            self.assertEqual(report["result"], "PASS")
            self.assertEqual(report["command"]["cmd"], "request_location")
            self.assertEqual(report["location_report"]["event_type"], "location_report")
            self.assertEqual(report["location_report"]["location_request_cmd_id"], report["command"]["cmd_id"])
            self.assertEqual(report["location_report"]["transport"]["type"], "lte")
            self.assertIs(report["location_report"]["fix"], False)
            markdown = (Path(tmp) / "report" / "lte_command_loop_report.md").read_text(encoding="utf-8")
            self.assertIn("# LTE HTTP Command Loop Report", markdown)
            self.assertIn("Command under validation: `request_location`", markdown)
            self.assertIn("location_report transport only", markdown)
            self.assertNotIn("The command is intentionally harmless: set_report_interval", markdown)

    def test_validation_rejects_non_lte_ack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            server = ThreadingHTTPServer(("127.0.0.1", 0), message_hub.make_handler(store))
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            hub_url = f"http://127.0.0.1:{server.server_port}"
            device_thread = threading.Thread(
                target=self._poll_and_ack_once,
                args=(hub_url,),
                kwargs={
                    "device_id": "ego-link-r1-test",
                    "fw_version": "0.1.0-lte003-command-loop",
                    "test_run_id": "lte003-unit",
                    "transport_type": "wifi",
                    "poll_reason_code": "LTE_HTTP_OK",
                    "poll_status_code": 200,
                },
                daemon=True,
            )
            try:
                device_thread.start()
                with self.assertRaises(FieldValidationError) as context:
                    validate_lte_command_loop.validate_lte_command_loop(
                        hub_url=hub_url,
                        device_id="ego-link-r1-test",
                        token=None,
                        output_dir=Path(tmp) / "report",
                        test_run_id="lte003-unit",
                        board_id="connectivity-node-001",
                        connection_path="independent_power_usb_disconnected",
                        timeout_sec=1.0,
                        poll_interval_sec=0.05,
                        expected_fw_version="0.1.0-lte003-command-loop",
                        command_name="set_report_interval",
                        interval_ms=10000,
                    )
            finally:
                device_thread.join(timeout=2)
                server.shutdown()
                server_thread.join(timeout=5)
                server.server_close()

        self.assertIn("transport.type=wifi", str(context.exception))

    def test_validation_can_wait_for_existing_pending_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            server = ThreadingHTTPServer(("127.0.0.1", 0), message_hub.make_handler(store))
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            hub_url = f"http://127.0.0.1:{server.server_port}"
            client = HubClient(hub_url)
            try:
                client.post(
                    "/api/v1/test-runs",
                    {
                        "test_run_id": "lte003-unit",
                        "task_id": "LTE-003",
                        "board_id": "connectivity-node-001",
                        "device_id": "ego-link-r1-test",
                        "connection_path": "independent_power_usb_disconnected",
                        "started_at": "2026-06-28T00:00:00+00:00",
                        "status": "active",
                        "goal": "existing command test",
                    },
                )
                command = client.post(
                    "/api/v1/devices/ego-link-r1-test/commands",
                    {
                        "cmd": "set_report_interval",
                        "test_run_id": "lte003-unit",
                        "payload": {"interval_ms": 10000, "test_run_id": "lte003-unit"},
                    },
                )["command"]
                device_thread = threading.Thread(
                    target=self._poll_and_ack_once,
                    args=(hub_url,),
                    kwargs={
                        "device_id": "ego-link-r1-test",
                        "fw_version": "0.1.0-lte003-command-loop",
                        "test_run_id": "lte003-unit",
                        "transport_type": "lte",
                        "poll_reason_code": "LTE_HTTP_OK",
                        "poll_status_code": 200,
                    },
                    daemon=True,
                )
                device_thread.start()
                report = validate_lte_command_loop.validate_lte_command_loop(
                    hub_url=hub_url,
                    device_id="ego-link-r1-test",
                    token=None,
                    output_dir=Path(tmp) / "report",
                    test_run_id="lte003-unit",
                    board_id="connectivity-node-001",
                    connection_path="independent_power_usb_disconnected",
                    timeout_sec=1.0,
                    poll_interval_sec=0.05,
                    expected_fw_version="0.1.0-lte003-command-loop",
                    command_name="set_report_interval",
                    interval_ms=10000,
                    existing_command_id=str(command["cmd_id"]),
                )
            finally:
                server.shutdown()
                server_thread.join(timeout=5)
                server.server_close()

            self.assertEqual(report["result"], "PASS")
            self.assertEqual(report["command"]["cmd_id"], command["cmd_id"])
            self.assertEqual(report["existing_command_id"], command["cmd_id"])

    def test_validation_timeout_writes_failure_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            server = ThreadingHTTPServer(("127.0.0.1", 0), message_hub.make_handler(store))
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            hub_url = f"http://127.0.0.1:{server.server_port}"
            try:
                with self.assertRaises(FieldValidationError) as context:
                    validate_lte_command_loop.validate_lte_command_loop(
                        hub_url=hub_url,
                        device_id="ego-link-r1-test",
                        token=None,
                        output_dir=Path(tmp) / "report",
                        test_run_id="lte003-unit",
                        board_id="connectivity-node-001",
                        connection_path="independent_power_usb_disconnected",
                        timeout_sec=0.1,
                        poll_interval_sec=0.05,
                        expected_fw_version="0.1.0-lte003-command-loop",
                        command_name="set_report_interval",
                        interval_ms=10000,
                    )
            finally:
                server.shutdown()
                server_thread.join(timeout=5)
                server.server_close()

            self.assertIn("timed out waiting for LTE ACK", str(context.exception))
            report_path = Path(tmp) / "report" / "lte_command_loop_report.json"
            self.assertTrue(report_path.is_file())
            self.assertEqual(json.loads(report_path.read_text(encoding="utf-8"))["result"], "FAIL")

    @staticmethod
    def _poll_and_ack_once(
        hub_url: str,
        *,
        device_id: str,
        fw_version: str,
        test_run_id: str,
        transport_type: str,
        poll_reason_code: str,
        poll_status_code: int,
        post_location_report: bool = False,
    ) -> None:
        client = HubClient(hub_url)
        deadline = time.monotonic() + 2.0
        command: dict | None = None
        while time.monotonic() < deadline:
            commands = client.get(f"/api/v1/devices/{device_id}/commands/poll").get("commands") or []
            if commands:
                command = commands[0]
                break
            time.sleep(0.05)
        if command is None:
            return
        if post_location_report:
            client.post(
                f"/api/v1/devices/{device_id}/telemetry",
                {
                    "protocol_version": "egolink.p0.v1",
                    "device_id": device_id,
                    "ts": "uptime_ms:2100",
                    "seq": 6,
                    "message_type": "event",
                    "event_type": "location_report",
                    "priority": "normal",
                    "fw_version": fw_version,
                    "test_run_id": test_run_id,
                    "source": "sim7670g_firmware_gnss",
                    "source_status": "unverified",
                    "fix": False,
                    "gnss_state": "no_fix",
                    "gnss_source": "sim7670g_uart_at",
                    "gnss_driver": "uart_at",
                    "gnss_query_ok": True,
                    "lat": None,
                    "lon": None,
                    "satellites": 0,
                    "location_request_cmd_id": command["cmd_id"],
                    "transport": {"type": "lte"},
                    "lte_http": {"phase": "location_report", "driver": "sim7670g_uart_at_http"},
                },
            )
        ack = protocol.ack_message(device_id, "uptime_ms:2000", 7, str(command["cmd_id"]), "ok")
        ack.update(
            {
                "fw_version": fw_version,
                "test_run_id": test_run_id,
                "message": "lte command loop acknowledged set_report_interval",
                "transport": {"type": transport_type, "rtt_ms": 123, "last_error": None},
                "lte_http": {
                    "phase": "command_ack",
                    "driver": "sim7670g_uart_at_http",
                    "poll_reason_code": poll_reason_code,
                    "poll_status_code": poll_status_code,
                    "poll_action_elapsed_ms": 123,
                },
                "command": {
                    "last_cmd_id": command["cmd_id"],
                    "last_status": "ok",
                    "last_ack_status": "ok",
                    "duplicate_local_execution_prevented": False,
                },
            }
        )
        client.post(f"/api/v1/devices/{device_id}/commands/{command['cmd_id']}/ack", ack)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer
import urllib.error
import urllib.request
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

    def test_validation_can_require_lte_location_observation_for_request_location(self) -> None:
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
                    "fw_version": "0.1.0-loc004a-cell-observation",
                    "test_run_id": "loc004a-unit",
                    "transport_type": "lte",
                    "poll_reason_code": "LTE_HTTP_OK",
                    "poll_status_code": 200,
                    "post_location_report": True,
                    "post_location_observation": True,
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
                    test_run_id="loc004a-unit",
                    board_id="connectivity-node-001",
                    connection_path="independent_power_usb_disconnected",
                    timeout_sec=1.0,
                    poll_interval_sec=0.05,
                    expected_fw_version="0.1.0-loc004a-cell-observation",
                    command_name="request_location",
                    interval_ms=10000,
                    require_location_report=True,
                    require_location_observation=True,
                )
            finally:
                device_thread.join(timeout=2)
                server.shutdown()
                server_thread.join(timeout=5)
                server.server_close()

            self.assertEqual(report["result"], "PASS")
            self.assertTrue(report["require_location_observation"])
            self.assertEqual(report["location_observation"]["event_type"], "location_observation")
            self.assertEqual(
                report["location_observation"]["location_request_cmd_id"],
                report["command"]["cmd_id"],
            )
            self.assertEqual(report["location_observation"]["cell"]["rat"], "LTE")
            self.assertEqual(report["location_observation"]["lte"]["reason_code"], "LTE_READY")
            markdown = (Path(tmp) / "report" / "lte_command_loop_report.md").read_text(encoding="utf-8")
            self.assertIn("location_observation validates command-scoped firmware-side cell/LTE evidence", markdown)

    def test_validation_can_require_raw_post_fail_once_retry_evidence(self) -> None:
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
                    "fw_version": "0.1.0-lte009-raw-post-retry-fault",
                    "test_run_id": "lte009-unit",
                    "transport_type": "lte",
                    "poll_reason_code": "LTE_HTTP_OK",
                    "poll_status_code": 200,
                    "post_raw_location_report_fail_once": True,
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
                    test_run_id="lte009-unit",
                    board_id="connectivity-node-001",
                    connection_path="independent_power_usb_disconnected",
                    timeout_sec=1.0,
                    poll_interval_sec=0.05,
                    expected_fw_version="0.1.0-lte009-raw-post-retry-fault",
                    command_name="request_location",
                    interval_ms=10000,
                    require_raw_post_fail_once=True,
                )
            finally:
                device_thread.join(timeout=2)
                server.shutdown()
                server_thread.join(timeout=5)
                server.server_close()

            self.assertEqual(report["result"], "PASS")
            self.assertTrue(report["require_location_report"])
            self.assertTrue(report["require_raw_post_fail_once"])
            self.assertEqual(report["location_report"]["event_type"], "location_report")
            self.assertEqual(report["raw_post_retry"]["status"], "ok")
            self.assertEqual(report["raw_post_retry"]["statuses"], ["injected_failure", "ok"])
            self.assertEqual(report["raw_post_retry"]["injected_failure_count"], 1)
            self.assertEqual(report["raw_post_retry"]["ok_location_report_count"], 1)
            markdown = (Path(tmp) / "report" / "lte_command_loop_report.md").read_text(encoding="utf-8")
            self.assertIn("raw POST fail-once validates retained failed raw evidence", markdown)

    def test_existing_command_reconciliation_accepts_pre_validator_location_evidence(self) -> None:
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
                        "test_run_id": "loc004a-runtime-unit",
                        "task_id": "LOC-004A",
                        "board_id": "connectivity-node-001",
                        "device_id": "ego-link-r1-test",
                        "connection_path": "independent_power_usb_disconnected",
                        "started_at": "2026-06-30T00:00:00+00:00",
                        "status": "active",
                        "goal": "existing command location reconciliation",
                    },
                )
                command = client.post(
                    "/api/v1/devices/ego-link-r1-test/commands",
                    {
                        "cmd": "request_location",
                        "test_run_id": "loc004a-runtime-unit",
                        "payload": {
                            "reason": "loc004a_reconcile_unit",
                            "test_run_id": "loc004a-runtime-unit",
                        },
                    },
                )["command"]
                device_thread = threading.Thread(
                    target=self._poll_and_ack_once,
                    args=(hub_url,),
                    kwargs={
                        "device_id": "ego-link-r1-test",
                        "fw_version": "0.1.0-loc004a-cell-observation",
                        "test_run_id": "loc004a-firmware-unit",
                        "transport_type": "lte",
                        "poll_reason_code": "LTE_HTTP_OK",
                        "poll_status_code": 200,
                        "post_location_report": True,
                        "post_location_observation": True,
                    },
                    daemon=True,
                )
                device_thread.start()
                device_thread.join(timeout=2)

                report = validate_lte_command_loop.validate_lte_command_loop(
                    hub_url=hub_url,
                    device_id="ego-link-r1-test",
                    token=None,
                    output_dir=Path(tmp) / "report",
                    test_run_id="loc004a-runtime-unit",
                    board_id="connectivity-node-001",
                    connection_path="independent_power_usb_disconnected",
                    timeout_sec=1.0,
                    poll_interval_sec=0.05,
                    expected_fw_version="0.1.0-loc004a-cell-observation",
                    expected_ack_test_run_id="loc004a-firmware-unit",
                    expected_message_test_run_id="loc004a-firmware-unit",
                    command_name="request_location",
                    interval_ms=10000,
                    existing_command_id=str(command["cmd_id"]),
                    require_location_report=True,
                    require_location_observation=True,
                )
            finally:
                server.shutdown()
                server_thread.join(timeout=5)
                server.server_close()

            self.assertEqual(report["result"], "PASS")
            self.assertEqual(report["evidence_since"], "command_created")
            self.assertEqual(report["evidence_since_resolution"], "command_created")
            self.assertEqual(report["effective_expected_ack_test_run_id"], "loc004a-firmware-unit")
            self.assertEqual(report["effective_expected_message_test_run_id"], "loc004a-firmware-unit")
            self.assertEqual(report["command"]["cmd_id"], command["cmd_id"])
            self.assertEqual(report["location_report"]["location_request_cmd_id"], command["cmd_id"])
            self.assertEqual(report["location_observation"]["location_request_cmd_id"], command["cmd_id"])

    def test_arm_only_creates_command_without_waiting_for_ack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            server = ThreadingHTTPServer(("127.0.0.1", 0), message_hub.make_handler(store))
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            hub_url = f"http://127.0.0.1:{server.server_port}"
            try:
                report = validate_lte_command_loop.validate_lte_command_loop(
                    hub_url=hub_url,
                    device_id="ego-link-r1-test",
                    token=None,
                    output_dir=Path(tmp) / "report",
                    test_run_id="loc004a-arm-unit",
                    board_id="connectivity-node-001",
                    connection_path="independent_power_usb_disconnected",
                    timeout_sec=1.0,
                    poll_interval_sec=0.05,
                    expected_fw_version="0.1.0-loc004a-cell-observation",
                    command_name="request_location",
                    interval_ms=10000,
                    require_location_report=True,
                    require_location_observation=True,
                    arm_only=True,
                )
            finally:
                server.shutdown()
                server_thread.join(timeout=5)
                server.server_close()

            self.assertEqual(report["result"], "ARMED")
            self.assertTrue(report["arm_only"])
            self.assertEqual(report["command"]["cmd"], "request_location")
            self.assertEqual(report["command"]["status"], "pending")
            markdown = (Path(tmp) / "report" / "lte_command_loop_report.md").read_text(encoding="utf-8")
            self.assertIn("Arm-only mode enqueued or selected the command", markdown)

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
        post_location_observation: bool = False,
        post_raw_location_report_fail_once: bool = False,
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
        if post_raw_location_report_fail_once:
            payload = (
                "event_type=location_report\n"
                "seq=6\n"
                f"device_id={device_id}\n"
                f"fw_version={fw_version}\n"
                f"test_run_id={test_run_id}\n"
                "source=sim7670g_firmware_gnss\n"
                "source_status=unverified\n"
                "fix=false\n"
                "gnss_state=no_fix\n"
                "gnss_source=sim7670g_uart_at\n"
                "gnss_driver=uart_at\n"
                "gnss_query_ok=true\n"
                f"location_request_cmd_id={command['cmd_id']}\n"
                "transport_type=lte\n"
                "lte_http_phase=location_report\n"
                "lte_http_driver=sim7670g_uart_at_http\n"
                "test_inject_raw_post_fail_once=true\n"
            ).encode("utf-8")
            frame = message_hub.build_raw_frame(
                "event",
                f"loc-{command['cmd_id']}",
                payload,
                seq=6,
                metadata={"test-run-id": test_run_id},
            )
            LteCommandLoopValidationTests._post_raw_frame_expect_status(
                hub_url,
                device_id,
                frame,
                expected_status=503,
            )
            LteCommandLoopValidationTests._post_raw_frame_expect_status(
                hub_url,
                device_id,
                frame,
                expected_status=200,
            )
        elif post_location_report:
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
        if post_location_observation:
            client.post(
                f"/api/v1/devices/{device_id}/telemetry",
                {
                    "protocol_version": "egolink.p0.v1",
                    "device_id": device_id,
                    "ts": "uptime_ms:2200",
                    "seq": 7,
                    "message_type": "event",
                    "event_type": "location_observation",
                    "priority": "normal",
                    "fw_version": fw_version,
                    "test_run_id": test_run_id,
                    "source": "sim7670g_firmware_cell",
                    "source_status": "observed",
                    "location_request_cmd_id": command["cmd_id"],
                    "cell": {
                        "rat": "LTE",
                        "cell_id": "unit-cell-001",
                        "registration_state": "registered_home",
                        "pdp_state": "active",
                        "reason_code": "LTE_READY",
                    },
                    "lte": {
                        "driver": "sim7670g_uart_at",
                        "query_ok": True,
                        "sim_state": "READY",
                        "registration_state": "registered_home",
                        "pdp_state": "active",
                        "assigned_ip": "10.1.2.3",
                        "reason_code": "LTE_READY",
                    },
                    "location_belief": {
                        "state": "Unknown",
                        "source": ["cell", "lte"],
                        "reason": "cell_observation_without_position_fix",
                    },
                    "transport": {"type": "lte"},
                    "lte_http": {"phase": "location_observation", "driver": "sim7670g_uart_at_http"},
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

    @staticmethod
    def _post_raw_frame_expect_status(hub_url: str, device_id: str, frame: bytes, *, expected_status: int) -> None:
        req = urllib.request.Request(
            f"{hub_url}/api/v1/devices/{device_id}/raw-ingest",
            data=frame,
            headers={"Content-Type": "text/x-egolink-frame"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=2) as response:
                body = response.read()
                status = response.status
        except urllib.error.HTTPError as exc:
            body = exc.read()
            status = exc.code
        if status != expected_status:
            raise AssertionError(f"raw frame POST returned HTTP {status}, expected {expected_status}: {body!r}")


if __name__ == "__main__":
    unittest.main()

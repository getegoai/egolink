from __future__ import annotations

from pathlib import Path
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer
import unittest

from pc_simulator import protocol
from scripts import validate_lte_http_probe
from scripts.validate_fw001_hw_loop import FieldValidationError, HubClient
from server import message_hub


class LteHttpProbeValidationTests(unittest.TestCase):
    def test_validation_accepts_successful_lte_http_result_probe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            server = ThreadingHTTPServer(("127.0.0.1", 0), message_hub.make_handler(store))
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            hub_url = f"http://127.0.0.1:{server.server_port}"
            device_thread = threading.Thread(
                target=self._delayed_post_lte_http_probe,
                args=(hub_url,),
                kwargs={
                    "device_id": "ego-link-r1-test",
                    "fw_version": "0.1.0-lte002-lte-http-probe",
                    "test_run_id": "lte002-unit",
                    "include_result": True,
                },
                daemon=True,
            )
            try:
                device_thread.start()

                report = validate_lte_http_probe.validate_lte_http_probe(
                    hub_url=hub_url,
                    device_id="ego-link-r1-test",
                    token=None,
                    output_dir=Path(tmp) / "report",
                    observation_id="lte002-unit",
                    board_id="connectivity-node-001",
                    connection_path="independent_power_usb_disconnected",
                    timeout_sec=1.0,
                    poll_interval_sec=0.05,
                    expected_fw_version="0.1.0-lte002-lte-http-probe",
                    expected_test_run_id="lte002-unit",
                )
            finally:
                device_thread.join(timeout=2)
                server.shutdown()
                server_thread.join(timeout=5)
                server.server_close()

            self.assertEqual(report["result"], "PASS")
            self.assertEqual(report["lte_http"]["reason_code"], "LTE_HTTP_OK")
            self.assertEqual(report["lte_http"]["transport_type"], "lte")
            self.assertEqual(report["lte_http"]["lte_reason_code"], "LTE_READY")
            self.assertTrue((Path(tmp) / "report" / "lte_http_probe_report.json").is_file())
            self.assertTrue((Path(tmp) / "report" / "lte_http_probe_report.md").is_file())
            self.assertTrue((Path(tmp) / "report" / "device_state.json").is_file())
            self.assertTrue((Path(tmp) / "report" / "test_run_export.json").is_file())

    def test_validation_reports_attempt_without_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            server = ThreadingHTTPServer(("127.0.0.1", 0), message_hub.make_handler(store))
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            hub_url = f"http://127.0.0.1:{server.server_port}"
            device_thread = threading.Thread(
                target=self._delayed_post_lte_http_probe,
                args=(hub_url,),
                kwargs={
                    "device_id": "ego-link-r1-test",
                    "fw_version": "0.1.0-lte002-lte-http-probe",
                    "test_run_id": "lte002-unit",
                    "include_result": False,
                },
                daemon=True,
            )
            try:
                device_thread.start()

                with self.assertRaises(FieldValidationError) as context:
                    validate_lte_http_probe.validate_lte_http_probe(
                        hub_url=hub_url,
                        device_id="ego-link-r1-test",
                        token=None,
                        output_dir=Path(tmp) / "report",
                        observation_id="lte002-unit",
                        board_id="connectivity-node-001",
                        connection_path="independent_power_usb_disconnected",
                        timeout_sec=0.4,
                        poll_interval_sec=0.05,
                        expected_fw_version="0.1.0-lte002-lte-http-probe",
                        expected_test_run_id="lte002-unit",
                    )
            finally:
                device_thread.join(timeout=2)
                server.shutdown()
                server_thread.join(timeout=5)
                server.server_close()

        self.assertIn("attempt reached Message Hub", str(context.exception))

    @staticmethod
    def _post_lte_http_probe(
        hub_url: str,
        *,
        device_id: str,
        fw_version: str,
        test_run_id: str,
        include_result: bool,
    ) -> None:
        client = HubClient(hub_url)
        base_fields = {
            "fw_version": fw_version,
            "source": "sim7670g_lte_http_probe",
            "source_status": "observed",
            "test_run_id": test_run_id,
            "transport": {"type": "lte", "rtt_ms": 123, "last_error": None},
            "cell": {
                "rat": "LTE",
                "operator": "unit-operator",
                "cell_id": "unit-cell",
                "rssi": -69,
                "rsrp": -96,
                "rsrq": -12,
                "sinr": 18,
                "sim_state": "READY",
                "registration_state": "registered_home",
                "pdp_state": "active",
                "reason_code": "LTE_READY",
            },
            "lte": {
                "driver": "sim7670g_uart_at",
                "query_ok": True,
                "uart_ready": True,
                "at_ok": True,
                "sim_state": "READY",
                "registration_state": "registered_home",
                "apn_state": "configured",
                "pdp_state": "active",
                "assigned_ip": "10.1.2.3",
                "reason_code": "LTE_READY",
            },
        }
        attempt = protocol.event_message(
            device_id,
            "uptime_ms:1000",
            1,
            "lte_http_probe",
            "normal",
            **base_fields,
            lte_http={
                "phase": "attempt",
                "driver": "sim7670g_uart_at_http",
                "reason_code": "LTE_HTTP_ATTEMPTING",
                "status_code": None,
            },
        )
        client.post(f"/api/v1/devices/{device_id}/telemetry", attempt)
        if include_result:
            result = protocol.event_message(
                device_id,
                "uptime_ms:2000",
                2,
                "lte_http_probe",
                "normal",
                **base_fields,
                lte_http={
                    "phase": "result",
                    "driver": "sim7670g_uart_at_http",
                    "reason_code": "LTE_HTTP_OK",
                    "status_code": 200,
                    "action_elapsed_ms": 123,
                    "http_action_ok": True,
                },
            )
            client.post(f"/api/v1/devices/{device_id}/telemetry", result)
        time.sleep(0.05)

    @classmethod
    def _delayed_post_lte_http_probe(cls, hub_url: str, **kwargs: str) -> None:
        time.sleep(0.1)
        cls._post_lte_http_probe(hub_url, **kwargs)


if __name__ == "__main__":
    unittest.main()

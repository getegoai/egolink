from __future__ import annotations

from pathlib import Path
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer
import unittest

from pc_simulator import protocol
from scripts import validate_lte_observability
from scripts.validate_fw001_hw_loop import FieldValidationError, HubClient
from server import message_hub


class LteObservabilityValidationTests(unittest.TestCase):
    def test_validation_accepts_explainable_non_ready_lte_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            server = ThreadingHTTPServer(("127.0.0.1", 0), message_hub.make_handler(store))
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            hub_url = f"http://127.0.0.1:{server.server_port}"
            device_thread = threading.Thread(
                target=self._delayed_post_lte_status,
                args=(hub_url,),
                kwargs={
                    "device_id": "ego-link-r1-test",
                    "fw_version": "0.1.0-lte001a-observe",
                    "test_run_id": "lte001b-unit",
                    "reason_code": "LTE_NOT_REGISTERED",
                },
                daemon=True,
            )
            try:
                device_thread.start()

                report = validate_lte_observability.validate_lte_observability(
                    hub_url=hub_url,
                    device_id="ego-link-r1-test",
                    token=None,
                    output_dir=Path(tmp) / "report",
                    observation_id="lte001b-unit",
                    board_id="connectivity-node-001",
                    connection_path="independent_power_usb_disconnected",
                    timeout_sec=1.0,
                    poll_interval_sec=0.05,
                    expected_fw_version="0.1.0-lte001a-observe",
                    expected_test_run_id="lte001b-unit",
                )
            finally:
                device_thread.join(timeout=2)
                server.shutdown()
                server_thread.join(timeout=5)
                server.server_close()

            self.assertEqual(report["result"], "PASS")
            self.assertEqual(report["lte"]["reason_code"], "LTE_NOT_REGISTERED")
            self.assertEqual(report["lte"]["sim_state"], "READY")
            self.assertTrue((Path(tmp) / "report" / "lte_observability_report.json").is_file())
            self.assertTrue((Path(tmp) / "report" / "lte_observability_report.md").is_file())
            self.assertTrue((Path(tmp) / "report" / "device_state.json").is_file())

    def test_validation_can_require_lte_ready_for_later_gates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            server = ThreadingHTTPServer(("127.0.0.1", 0), message_hub.make_handler(store))
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            hub_url = f"http://127.0.0.1:{server.server_port}"
            try:
                self._post_lte_status(
                    hub_url,
                    device_id="ego-link-r1-test",
                    fw_version="0.1.0-lte001a-observe",
                    test_run_id="lte001b-unit",
                    reason_code="LTE_PDP_INACTIVE",
                )

                with self.assertRaises(FieldValidationError) as context:
                    validate_lte_observability.validate_lte_observability(
                        hub_url=hub_url,
                        device_id="ego-link-r1-test",
                        token=None,
                        output_dir=Path(tmp) / "report",
                        observation_id="lte001b-unit",
                        board_id="connectivity-node-001",
                        connection_path="independent_power_usb_disconnected",
                        timeout_sec=0.1,
                        poll_interval_sec=0.05,
                        expected_fw_version="0.1.0-lte001a-observe",
                        expected_test_run_id="lte001b-unit",
                        require_lte_ready=True,
                    )
            finally:
                server.shutdown()
                server_thread.join(timeout=5)
                server.server_close()

        self.assertIn("LTE_READY was required", str(context.exception))

    def test_validation_rejects_missing_lte_reason(self) -> None:
        summary = validate_lte_observability.observed_lte_summary({"observability": {"lte": {}}})

        self.assertFalse(validate_lte_observability.lte_summary_is_observed(summary))

    @staticmethod
    def _post_lte_status(
        hub_url: str,
        *,
        device_id: str,
        fw_version: str,
        test_run_id: str,
        reason_code: str,
    ) -> None:
        client = HubClient(hub_url)
        client.post("/api/v1/devices/register", {"device_id": device_id, "fw_version": fw_version})
        heartbeat = protocol.status_message(
            device_id,
            "uptime_ms:1000",
            1,
            fw_version=fw_version,
            battery=87,
            charging=False,
            link_type="mock_4g_over_wifi",
            rssi=-55,
            modem_state="mock_data_ready",
            gnss_state="fix",
            guard_mode="child_safety",
            queue_size=0,
            cell={
                "rat": "LTE",
                "operator": "unit-operator",
                "cell_id": "unit-cell",
                "rssi": -69,
                "rsrp": -96,
                "rsrq": -12,
                "sinr": 18,
                "sim_state": "READY",
                "registration_state": "searching",
                "pdp_state": "inactive",
                "reason_code": reason_code,
            },
            lte={
                "driver": "sim7670g_uart_at",
                "query_ok": True,
                "uart_ready": True,
                "at_ok": True,
                "sim_state": "READY",
                "registration_state": "searching",
                "apn_state": "configured",
                "pdp_state": "inactive",
                "assigned_ip": "unknown",
                "reason_code": reason_code,
            },
        )
        heartbeat["test_run_id"] = test_run_id
        client.post(f"/api/v1/devices/{device_id}/heartbeat", heartbeat)
        time.sleep(0.05)

    @classmethod
    def _delayed_post_lte_status(cls, hub_url: str, **kwargs: str) -> None:
        time.sleep(0.1)
        cls._post_lte_status(hub_url, **kwargs)


if __name__ == "__main__":
    unittest.main()

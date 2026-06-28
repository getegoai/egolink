from __future__ import annotations

from pathlib import Path
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer
import unittest

from pc_simulator import protocol
from scripts import validate_message_hub_stability
from scripts.validate_fw001_hw_loop import HubClient
from server import message_hub


class MessageHubStabilityValidationTests(unittest.TestCase):
    def test_observation_passes_without_enqueuing_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            server = ThreadingHTTPServer(("127.0.0.1", 0), message_hub.make_handler(store))
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            hub_url = f"http://127.0.0.1:{server.server_port}"
            device_thread = threading.Thread(
                target=self._fake_reporting_device,
                args=(hub_url, "ego-link-r1-test", "0.1.0-fw002b-test", "field-stability-unit"),
                daemon=True,
            )
            try:
                device_thread.start()

                report = validate_message_hub_stability.observe_stability(
                    hub_url=hub_url,
                    device_id="ego-link-r1-test",
                    token=None,
                    output_dir=Path(tmp) / "report",
                    observation_id="field-stability-unit",
                    board_id="connectivity-node-001",
                    connection_path="independent_power_usb_disconnected",
                    duration_sec=0.45,
                    poll_interval_sec=0.05,
                    min_messages=2,
                    max_last_seen_age_sec=5.0,
                    max_message_gap_sec_value=5.0,
                    expected_fw_version="0.1.0-fw002b-test",
                    expected_message_test_run_id="field-stability-unit",
                )
                commands = store.list_commands("ego-link-r1-test")
            finally:
                device_thread.join(timeout=2)
                server.shutdown()
                server_thread.join(timeout=5)
                server.server_close()

            self.assertEqual(report["result"], "PASS")
            self.assertGreaterEqual(report["summary"]["observed_message_count"], 2)
            self.assertEqual(report["summary"]["seq_regressions"], 0)
            self.assertEqual(commands, [])
            self.assertTrue((Path(tmp) / "report" / "stability_observation_report.json").is_file())
            self.assertTrue((Path(tmp) / "report" / "stability_observation_report.md").is_file())
            self.assertTrue((Path(tmp) / "report" / "observed_messages.json").is_file())
            self.assertTrue((Path(tmp) / "report" / "device_snapshots.json").is_file())

    def test_observation_fails_on_sequence_regression_by_default(self) -> None:
        messages = [
            {"server_received_at": "2026-06-27T00:00:00+00:00", "message_type": "status", "seq": 10},
            {"server_received_at": "2026-06-27T00:00:05+00:00", "message_type": "status", "seq": 1},
        ]

        summary = validate_message_hub_stability.summarize_messages(messages)

        self.assertEqual(summary["seq_regressions"], 1)

    @staticmethod
    def _fake_reporting_device(hub_url: str, device_id: str, fw_version: str, test_run_id: str) -> None:
        client = HubClient(hub_url)
        time.sleep(0.08)
        client.post("/api/v1/devices/register", {"device_id": device_id, "fw_version": fw_version})
        for seq in range(1, 5):
            heartbeat = protocol.status_message(
                device_id,
                f"uptime_ms:{seq * 1000}",
                seq,
                fw_version=fw_version,
                battery=87,
                charging=False,
                link_type="mock_4g_over_wifi",
                rssi=-55,
                modem_state="mock_data_ready",
                gnss_state="no_fix",
                guard_mode="child_safety",
                queue_size=0,
            )
            heartbeat["test_run_id"] = test_run_id
            client.post(f"/api/v1/devices/{device_id}/heartbeat", heartbeat)
            time.sleep(0.08)


if __name__ == "__main__":
    unittest.main()

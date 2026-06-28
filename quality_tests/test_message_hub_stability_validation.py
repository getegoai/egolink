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
                    min_location_observations=0,
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

    def test_stab001a_gate_requires_observation_belief_ack_and_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            server = ThreadingHTTPServer(("127.0.0.1", 0), message_hub.make_handler(store))
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            hub_url = f"http://127.0.0.1:{server.server_port}"
            test_run_id = "stab001a-unit"
            client = HubClient(hub_url)
            device_thread = threading.Thread(
                target=self._fake_stab001a_device,
                args=(hub_url, "ego-link-r1-test", "0.1.0-fw002c-test", test_run_id),
                daemon=True,
            )
            try:
                client.post(
                    "/api/v1/test-runs",
                    {
                        "test_run_id": test_run_id,
                        "task_id": "STAB-001A",
                        "device_id": "ego-link-r1-test",
                        "status": "active",
                    },
                )
                client.post(
                    "/api/v1/devices/ego-link-r1-test/commands",
                    {
                        "cmd": "set_report_interval",
                        "test_run_id": test_run_id,
                        "payload": {"interval_ms": 5000, "test_run_id": test_run_id},
                    },
                )
                device_thread.start()

                report = validate_message_hub_stability.observe_stability(
                    hub_url=hub_url,
                    device_id="ego-link-r1-test",
                    token=None,
                    output_dir=Path(tmp) / "report",
                    observation_id=test_run_id,
                    board_id="connectivity-node-001",
                    connection_path="independent_power_usb_disconnected",
                    duration_sec=0.65,
                    poll_interval_sec=0.05,
                    min_messages=3,
                    min_location_observations=1,
                    max_last_seen_age_sec=5.0,
                    max_message_gap_sec_value=5.0,
                    expected_fw_version="0.1.0-fw002c-test",
                    expected_message_test_run_id=test_run_id,
                    require_observability=True,
                    require_location_belief=True,
                    require_command_ack=True,
                    require_test_run_export=True,
                )
            finally:
                device_thread.join(timeout=2)
                server.shutdown()
                server_thread.join(timeout=5)
                server.server_close()

            gate = report["gate_summary"]
            self.assertEqual(report["result"], "PASS")
            self.assertEqual(gate["location_observation_count"], 1)
            self.assertEqual(gate["latest_location_event"], "location_observation")
            self.assertEqual(gate["location_belief_state"], "Fine")
            self.assertEqual(gate["location_belief_reason"], "gnss_fix_hdop_good")
            self.assertEqual(gate["command_last_ack_status"], "ok")
            self.assertTrue(gate["test_run_export_available"])
            self.assertTrue((Path(tmp) / "report" / "test_run_export.json").is_file())

    def test_observation_fails_on_sequence_regression_by_default(self) -> None:
        messages = [
            {"server_received_at": "2026-06-27T00:00:00+00:00", "message_type": "status", "seq": 10},
            {"server_received_at": "2026-06-27T00:00:05+00:00", "message_type": "status", "seq": 1},
        ]

        summary = validate_message_hub_stability.summarize_messages(messages)

        self.assertEqual(summary["seq_regressions"], 1)

    def test_gate_does_not_accept_default_missing_location_belief(self) -> None:
        gate = validate_message_hub_stability.summarize_gate(
            {
                "observability": {
                    "location_belief": {"state": "unknown", "reason": "no_location_belief"},
                },
            },
            {"location_observation_count": 0, "latest_location": {}},
            None,
            None,
        )

        self.assertFalse(gate["location_belief_present"])

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

    @staticmethod
    def _fake_stab001a_device(hub_url: str, device_id: str, fw_version: str, test_run_id: str) -> None:
        client = HubClient(hub_url)
        time.sleep(0.08)
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
            transport={"type": "mock_4g_over_wifi", "rtt_ms": 42, "last_error": None},
            runtime={"boot_id": "boot-unit", "uptime_s": 1, "last_reset_reason": "poweron", "watchdog_count": 0},
            power={"battery_mv": 3920, "soc_pct": 87, "charging": False, "source": "mock"},
        )
        heartbeat["test_run_id"] = test_run_id
        client.post(f"/api/v1/devices/{device_id}/heartbeat", heartbeat)
        observation = protocol.event_message(
            device_id,
            "2026-06-28T00:00:01Z",
            2,
            "location_observation",
            "normal",
            fw_version=fw_version,
            test_run_id=test_run_id,
            source="unit_stab001a",
            source_status="mock",
            transport={"type": "mock_4g_over_wifi", "rtt_ms": 38, "last_error": None},
            gnss={"enabled": True, "fix": True, "hdop": 0.9, "satellites": 12, "attempt_ms": 18000},
            cell={"rat": "LTE", "cell_id": "mock-cell-001", "rsrp": -67},
            wifi={"scan_enabled": True, "aps": [{"bssid_hash": "mock_hash_1", "rssi": -62}]},
            imu={"motion": "stationary", "confidence": 0.93},
            power={"battery_mv": 3920, "soc_pct": 87, "charging": False, "source": "mock"},
            location_belief={
                "state": "Fine",
                "radius_m": 15,
                "confidence": 0.91,
                "source": ["gnss"],
                "reason": "gnss_fix_hdop_good",
            },
        )
        client.post(f"/api/v1/devices/{device_id}/telemetry", observation)
        deadline = time.monotonic() + 0.7
        while time.monotonic() < deadline:
            commands = client.get(f"/api/v1/devices/{device_id}/commands/poll").get("commands") or []
            if commands:
                ack = protocol.ack_message(device_id, "2026-06-28T00:00:02Z", 3, commands[0]["cmd_id"], "ok")
                ack["fw_version"] = fw_version
                ack["test_run_id"] = test_run_id
                client.post(f"/api/v1/devices/{device_id}/commands/{commands[0]['cmd_id']}/ack", ack)
                return
            time.sleep(0.05)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from pathlib import Path
import tempfile
import threading
from http.server import ThreadingHTTPServer
import unittest

from pc_simulator import message_hub_client, protocol
from server import message_hub


class MessageHubClientTests(unittest.TestCase):
    def test_simulated_device_builds_current_protocol_messages(self) -> None:
        device = message_hub_client.SimulatedDevice(device_id="ego-link-r0-sim", test_run_id="pc-sim-unit")

        heartbeat = device.heartbeat()
        location = device.location_report()
        observation = device.location_observation()
        ack = device.ack({"cmd_id": "cmd-0001", "cmd": "set_report_interval"})

        self.assertEqual(heartbeat["protocol_version"], protocol.PROTOCOL_VERSION)
        self.assertEqual(heartbeat["message_type"], "status")
        self.assertEqual(heartbeat["test_run_id"], "pc-sim-unit")
        self.assertEqual(location["event_type"], "location_report")
        self.assertEqual(location["source_status"], "mock")
        self.assertEqual(observation["event_type"], "location_observation")
        self.assertEqual(observation["test_run_id"], "pc-sim-unit")
        self.assertEqual(observation["location_belief"]["state"], "Fine")
        self.assertEqual(observation["cell"]["rat"], "LTE")
        self.assertEqual(observation["wifi"]["aps"][0]["bssid_hash"], "mock_hash_home_1")
        self.assertEqual(ack["message_type"], "ack")
        self.assertEqual(ack["cmd_id"], "cmd-0001")
        self.assertEqual(ack["test_run_id"], "pc-sim-unit")

    def test_run_once_drives_register_heartbeat_location_poll_and_ack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            server = ThreadingHTTPServer(("127.0.0.1", 0), message_hub.make_handler(store))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            hub_url = f"http://127.0.0.1:{server.server_port}"
            try:
                result = message_hub_client.run_once(
                    hub_url=hub_url,
                    device_id="ego-link-r0-sim",
                    create_demo_command=True,
                    test_run_id="pc-sim-run-once",
                )
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertTrue(result["ok"])
        self.assertEqual(result["test_run"]["test_run"]["test_run_id"], "pc-sim-run-once")
        self.assertEqual(result["heartbeat"]["message"]["message_type"], "status")
        self.assertEqual(result["heartbeat"]["message"]["test_run_id"], "pc-sim-run-once")
        self.assertEqual(result["location"]["message"]["event_type"], "location_report")
        self.assertEqual(result["location_observation"]["message"]["event_type"], "location_observation")
        self.assertEqual(result["location_observation"]["message"]["test_run_id"], "pc-sim-run-once")
        device_state = result["state"]["devices"][0]
        self.assertEqual(device_state["latest_location"]["event_type"], "location_observation")
        self.assertEqual(device_state["observability"]["location_belief"]["state"], "Fine")
        self.assertEqual(len(result["polled_commands"]), 1)
        self.assertEqual(len(result["acks"]), 1)
        self.assertEqual(result["acks"][0]["message"]["status"], "ok")
        self.assertEqual(result["acks"][0]["message"]["test_run_id"], "pc-sim-run-once")
        self.assertEqual(result["test_run_export"]["observability_summary"]["message_count"], 4)
        self.assertEqual(result["state"]["devices"][0]["device_id"], "ego-link-r0-sim")


if __name__ == "__main__":
    unittest.main()

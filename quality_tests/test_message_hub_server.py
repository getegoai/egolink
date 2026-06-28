from __future__ import annotations

import json
from pathlib import Path
import tempfile
import threading
from http.server import ThreadingHTTPServer
import unittest
from urllib import error, request

from pc_simulator import protocol
from server import message_hub


def post_json(base_url: str, path: str, payload: dict[str, object]) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        base_url + path,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def get_json(base_url: str, path: str, headers: dict[str, str] | None = None) -> dict:
    req = request.Request(base_url + path, headers=headers or {}, method="GET")
    with request.urlopen(req, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


class MessageHubStoreTests(unittest.TestCase):
    def test_store_runs_register_telemetry_command_ack_loop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")

            device = store.register_device({"device_id": "ego-link-001", "fw_version": "0.1.0-sim"})
            status = store.ingest(
                "ego-link-001",
                "heartbeat",
                protocol.status_message(
                    "ego-link-001",
                    "2026-06-27T00:00:00Z",
                    1,
                    battery=87,
                    link_type="mock_4g_over_wifi",
                    guard_mode="child_safety",
                    queue_size=0,
                    transport={"type": "wifi", "rtt_ms": 42, "last_error": None},
                    runtime={"free_heap": 123456, "last_reset_reason": "poweron", "watchdog_count": 0},
                    power={"battery_mv": 3920, "soc_pct": 87, "charging": False, "source": "estimated"},
                ),
            )
            telemetry = store.ingest(
                "ego-link-001",
                "telemetry",
                protocol.event_message(
                    "ego-link-001",
                    "2026-06-27T00:00:01Z",
                    2,
                    "location_report",
                    "normal",
                    source="mock_gnss",
                    lat=22.5431,
                    lon=114.0579,
                    gnss={"fix": True, "hdop": 0.9, "satellites": 12, "attempt_ms": 18000},
                    cell={
                        "rat": "LTE",
                        "cell_id": "cell-001",
                        "rsrp": -67,
                        "rsrq": -21,
                        "sinr": 19,
                        "registration_state": "registered_home",
                        "pdp_state": "active",
                        "sim_state": "READY",
                    },
                    lte={
                        "driver": "sim7670g_uart_at",
                        "query_ok": True,
                        "sim_state": "READY",
                        "registration_state": "registered_home",
                        "apn_state": "configured",
                        "pdp_state": "active",
                        "assigned_ip": "10.1.2.3",
                        "reason_code": "LTE_READY",
                    },
                ),
            )
            command = store.create_command("ego-link-001", {"cmd": "set_report_interval", "payload": {"interval_ms": 5000}})
            ack = store.ingest(
                "ego-link-001",
                "ack",
                protocol.ack_message("ego-link-001", "2026-06-27T00:00:02Z", 3, command["cmd_id"], "ok"),
            )

            commands = store.list_commands("ego-link-001")
            latest = store.latest_telemetry("ego-link-001")
            device_state = store.get_device("ego-link-001")

        self.assertEqual(device["device_id"], "ego-link-001")
        self.assertEqual(status["server_received_at"] > "", True)
        self.assertEqual(telemetry["event_type"], "location_report")
        self.assertEqual(ack["status"], "ok")
        self.assertEqual(commands[0]["status"], "ok")
        self.assertEqual(latest["event_type"], "location_report")
        observability = device_state["observability"]
        self.assertEqual(observability["transport"]["type"], "wifi")
        self.assertEqual(observability["runtime"]["free_heap"], 123456)
        self.assertEqual(observability["power"]["battery_mv"], 3920)
        self.assertEqual(observability["gnss"]["reason_code"], "GNSS_FIX")
        self.assertEqual(observability["cell"]["cell_id"], "cell-001")
        self.assertEqual(observability["cell"]["registration_state"], "registered_home")
        self.assertEqual(observability["lte"]["reason_code"], "LTE_READY")
        self.assertEqual(observability["lte"]["assigned_ip"], "10.1.2.3")
        self.assertEqual(observability["command"]["last_ack_status"], "ok")

    def test_error_ingest_updates_device_error_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            store.ingest(
                "ego-link-001",
                "error",
                {
                    "protocol_version": protocol.PROTOCOL_VERSION,
                    "device_id": "ego-link-001",
                    "ts": "2026-06-27T00:00:00Z",
                    "seq": 1,
                    "error_code": "GNSS_NO_FIX_TIMEOUT",
                    "severity": "warning",
                },
            )
            device = store.get_device("ego-link-001")

        self.assertEqual(device["last_error"]["error_code"], "GNSS_NO_FIX_TIMEOUT")

    def test_device_state_preserves_latest_location_after_newer_sensor_sample(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            store.ingest(
                "ego-link-001",
                "telemetry",
                protocol.event_message(
                    "ego-link-001",
                    "2026-06-27T00:00:01Z",
                    1,
                    "location_report",
                    "normal",
                    source="firmware_gnss_scaffold",
                    fix=False,
                    gnss_state="driver_not_integrated",
                    source_status="unverified",
                ),
            )
            store.ingest(
                "ego-link-001",
                "telemetry",
                protocol.event_message(
                    "ego-link-001",
                    "2026-06-27T00:00:02Z",
                    2,
                    "sensor_sample",
                    "normal",
                    payload={"uptime_ms": 1000},
                    gnss_state="mock_fix",
                ),
            )
            device = store.get_device("ego-link-001")

        self.assertEqual(device["latest_telemetry"]["event_type"], "sensor_sample")
        self.assertEqual(device["latest_location"]["event_type"], "location_report")
        self.assertEqual(device["latest_location"]["gnss_state"], "driver_not_integrated")
        self.assertEqual(device["latest_location"]["source_status"], "unverified")

    def test_location_observation_updates_latest_location_and_belief(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            store.ingest(
                "ego-link-001",
                "telemetry",
                protocol.event_message(
                    "ego-link-001",
                    "2026-06-27T00:00:01Z",
                    1,
                    "location_report",
                    "normal",
                    source="mock_gnss",
                    source_status="mock",
                    fix=True,
                    lat=22.5431,
                    lon=114.0579,
                    gnss_state="fix",
                ),
            )
            store.ingest(
                "ego-link-001",
                "telemetry",
                protocol.event_message(
                    "ego-link-001",
                    "2026-06-27T00:00:02Z",
                    2,
                    "location_observation",
                    "normal",
                    source="pc_simulator_location_observation",
                    source_status="mock",
                    gnss={"enabled": True, "fix": False, "state": "no_fix", "attempt_ms": 30000},
                    cell={"rat": "LTE", "cell_id": "mock-cell-001", "rsrp": -71},
                    wifi={"scan_enabled": True, "aps": [{"bssid_hash": "mock_hash_1", "rssi": -62}]},
                    imu={"motion": "stationary", "confidence": 0.93},
                    location_belief={
                        "state": "Coarse",
                        "radius_m": 180,
                        "confidence": 0.72,
                        "source": ["cell", "wifi_memory"],
                        "reason": "matched_mock_known_place",
                    },
                ),
            )
            device = store.get_device("ego-link-001")

        self.assertEqual(device["latest_location"]["event_type"], "location_observation")
        self.assertEqual(device["latest_location_observation"]["event_type"], "location_observation")
        observability = device["observability"]
        self.assertEqual(observability["gnss"]["reason_code"], "GNSS_NO_FIX")
        self.assertEqual(observability["cell"]["cell_id"], "mock-cell-001")
        self.assertEqual(observability["wifi"]["ap_count"], 1)
        self.assertEqual(observability["imu"]["motion"], "stationary")
        self.assertEqual(observability["location_belief"]["state"], "Coarse")
        self.assertEqual(observability["location_belief"]["radius_m"], 180)

    def test_lte_reason_code_is_part_of_observability_explainability(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            store.ingest(
                "ego-link-001",
                "heartbeat",
                protocol.status_message(
                    "ego-link-001",
                    "2026-06-27T00:00:00Z",
                    1,
                    battery=87,
                    link_type="mock_4g_over_wifi",
                    guard_mode="child_safety",
                    queue_size=0,
                    cell={"rat": "unknown", "registration_state": "searching", "reason_code": "LTE_NOT_REGISTERED"},
                    lte={
                        "driver": "sim7670g_uart_at",
                        "query_ok": True,
                        "sim_state": "READY",
                        "registration_state": "searching",
                        "pdp_state": "inactive",
                        "reason_code": "LTE_NOT_REGISTERED",
                    },
                ),
            )
            device = store.get_device("ego-link-001")

        observability = device["observability"]
        self.assertEqual(observability["lte"]["registration_state"], "searching")
        self.assertEqual(observability["lte"]["reason_code"], "LTE_NOT_REGISTERED")
        self.assertIn("LTE_NOT_REGISTERED", observability["explainability"]["reason_codes"])


class MessageHubDeployScriptTests(unittest.TestCase):
    def test_deploy_package_excludes_runtime_secret_files(self) -> None:
        script = (Path(__file__).resolve().parents[1] / "scripts" / "deploy_message_hub_vps.ps1").read_text(
            encoding="utf-8"
        )

        self.assertIn("function Copy-ServerSource", script)
        self.assertIn('rm -rf \'$RemoteDir/server/runtime\' \'$RemoteDir/server/__pycache__\'', script)
        self.assertNotIn('Copy-RelativePath "server"', script)


class MessageHubHttpTests(unittest.TestCase):
    def test_http_api_supports_r0_device_command_ack_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            server = ThreadingHTTPServer(("127.0.0.1", 0), message_hub.make_handler(store))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                register = post_json(base_url, "/api/v1/devices/register", {"device_id": "ego-link-001"})
                heartbeat = post_json(
                    base_url,
                    "/api/v1/devices/ego-link-001/heartbeat",
                    {
                        "battery": 87,
                        "link_type": "mock_4g_over_wifi",
                        "guard_mode": "child_safety",
                        "queue_size": 0,
                    },
                )
                command = post_json(
                    base_url,
                    "/api/v1/devices/ego-link-001/commands",
                    {"cmd": "set_report_interval", "payload": {"interval_ms": 5000}},
                )["command"]
                polled = get_json(base_url, "/api/v1/devices/ego-link-001/commands/poll")
                ack = post_json(
                    base_url,
                    f"/api/v1/devices/ego-link-001/commands/{command['cmd_id']}/ack",
                    {"status": "ok"},
                )
                state = get_json(base_url, "/api/state")
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertTrue(register["ok"])
        self.assertEqual(heartbeat["message"]["message_type"], "status")
        self.assertEqual(polled["commands"][0]["cmd_id"], command["cmd_id"])
        self.assertEqual(ack["message"]["status"], "ok")
        self.assertEqual(state["devices"][0]["device_id"], "ego-link-001")
        self.assertIn("latest_location", state["devices"][0])

    def test_test_run_export_route_includes_matching_messages_and_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            server = ThreadingHTTPServer(("127.0.0.1", 0), message_hub.make_handler(store))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                post_json(base_url, "/api/v1/test-runs", {"test_run_id": "field-r1-test"})
                post_json(
                    base_url,
                    "/api/v1/devices/ego-link-001/heartbeat",
                    {
                        "device_id": "ego-link-001",
                        "seq": 1,
                        "test_run_id": "field-r1-test",
                        "battery": 87,
                        "link_type": "mock_4g_over_wifi",
                        "guard_mode": "child_safety",
                        "queue_size": 0,
                    },
                )
                command = post_json(
                    base_url,
                    "/api/v1/devices/ego-link-001/commands",
                    {
                        "cmd": "set_report_interval",
                        "test_run_id": "field-r1-test",
                        "payload": {"interval_ms": 10000},
                    },
                )["command"]
                post_json(
                    base_url,
                    f"/api/v1/devices/ego-link-001/commands/{command['cmd_id']}/ack",
                    {
                        "device_id": "ego-link-001",
                        "seq": 2,
                        "status": "ok",
                        "test_run_id": "field-r1-test",
                    },
                )
                exported = get_json(base_url, "/api/v1/test-runs/field-r1-test/export")
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertEqual(exported["test_run"]["test_run_id"], "field-r1-test")
        self.assertEqual(exported["messages"][0]["test_run_id"], "field-r1-test")
        self.assertEqual(exported["commands"][0]["cmd"], "set_report_interval")
        self.assertEqual(exported["commands"][0]["ack"]["test_run_id"], "field-r1-test")
        self.assertEqual(exported["observability_summary"]["message_count"], 2)
        self.assertEqual(
            exported["observability_summary"]["latest_observability"]["transport"]["type"],
            "mock_4g_over_wifi",
        )
        self.assertIn("GNSS_NO_OBSERVATION", exported["observability_summary"]["reason_codes"])

    def test_get_api_requires_token_when_auth_is_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            server = ThreadingHTTPServer(("127.0.0.1", 0), message_hub.make_handler(store, token="secret"))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                health = get_json(base_url, "/health")
                with self.assertRaises(error.HTTPError) as context:
                    get_json(base_url, "/api/state")
                state = get_json(base_url, "/api/state", headers={"Authorization": "Bearer secret"})
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertTrue(health["ok"])
        self.assertEqual(context.exception.code, 401)
        self.assertEqual(state["devices"], [])


if __name__ == "__main__":
    unittest.main()

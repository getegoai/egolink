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


def post_bytes(base_url: str, path: str, body: bytes, content_type: str = "text/x-egolink-frame") -> dict:
    req = request.Request(
        base_url + path,
        data=body,
        headers={"Content-Type": content_type},
        method="POST",
    )
    with request.urlopen(req, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def get_json(base_url: str, path: str, headers: dict[str, str] | None = None) -> dict:
    req = request.Request(base_url + path, headers=headers or {}, method="GET")
    with request.urlopen(req, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def get_bytes(base_url: str, path: str) -> tuple[bytes, str]:
    req = request.Request(base_url + path, method="GET")
    with request.urlopen(req, timeout=5) as response:
        return response.read(), response.headers.get("Content-Type", "")


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

    def test_reliability_observability_exposes_network_and_cache_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            store.create_test_run({"test_run_id": "reliability-unit"})
            store.ingest(
                "ego-link-001",
                "heartbeat",
                protocol.status_message(
                    "ego-link-001",
                    "2026-06-27T00:00:00Z",
                    1,
                    battery=87,
                    link_type="lte",
                    guard_mode="field_test",
                    queue_size=0,
                    test_run_id="reliability-unit",
                    transport={"type": "lte", "rtt_ms": 380, "last_error": None},
                    reliability={
                        "network": {
                            "mode": "LTE",
                            "rssi": -89,
                            "reconnect_count": 2,
                            "last_error": "LTE_RECONNECT_TIMEOUT",
                            "last_reconnect_reason": "pdp_reactivate",
                            "state": "reconnecting",
                        },
                        "cache": {
                            "queued_message_count": 3,
                            "dropped_message_count": 1,
                            "last_drop_reason": "cache_full",
                            "oldest_message_age_ms": 42000,
                            "state": "store_forward",
                        },
                    },
                ),
            )
            device = store.get_device("ego-link-001")
            exported = store.export_test_run("reliability-unit")

        reliability = device["observability"]["reliability"]
        self.assertEqual(reliability["network"]["reconnect_count"], 2)
        self.assertEqual(reliability["network"]["last_error"], "LTE_RECONNECT_TIMEOUT")
        self.assertEqual(reliability["cache"]["queued_message_count"], 3)
        self.assertEqual(reliability["cache"]["dropped_message_count"], 1)
        self.assertIn("LTE_RECONNECT_TIMEOUT", device["observability"]["explainability"]["reason_codes"])
        self.assertEqual(
            exported["observability_summary"]["latest_observability"]["reliability"]["cache"]["last_drop_reason"],
            "cache_full",
        )
        self.assertEqual(exported["run_context"]["reliability"]["network"]["last_reconnect_reason"], "pdp_reactivate")

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
        self.assertEqual(device["location_memory"]["state"], "Coarse")
        self.assertEqual(device["location_memory"]["reason"], "matched_mock_known_place")
        self.assertEqual(observability["location_memory"]["state"], "Coarse")

    def test_location_memory_preserves_calibration_after_later_no_fix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            store.create_test_run({"test_run_id": "location-memory-unit"})
            store.ingest(
                "ego-link-001",
                "telemetry",
                protocol.event_message(
                    "ego-link-001",
                    "2026-06-27T00:00:01Z",
                    1,
                    "location_report",
                    "normal",
                    source="sim7670g_firmware_gnss",
                    source_status="observed",
                    fix=True,
                    lat=22.5431,
                    lon=114.0579,
                    hdop=0.9,
                    satellites=12,
                    gnss_state="fix",
                    test_run_id="location-memory-unit",
                ),
            )
            store.ingest(
                "ego-link-001",
                "telemetry",
                protocol.event_message(
                    "ego-link-001",
                    "2026-06-27T00:01:01Z",
                    2,
                    "location_report",
                    "normal",
                    source="sim7670g_firmware_gnss",
                    source_status="unverified",
                    fix=False,
                    lat=None,
                    lon=None,
                    gnss_state="no_fix",
                    gnss_query_ok=True,
                    test_run_id="location-memory-unit",
                    location_request_cmd_id="cmd-location-memory",
                ),
            )
            device = store.get_device("ego-link-001")
            exported = store.export_test_run("location-memory-unit")

        self.assertEqual(device["latest_location"]["gnss_state"], "no_fix")
        self.assertEqual(device["location_memory"]["state"], "Fine")
        self.assertEqual(device["location_memory"]["reason"], "gnss_fix_calibration")
        self.assertEqual(device["location_memory"]["last_no_fix"]["gnss_state"], "no_fix")
        self.assertEqual(device["location_memory"]["last_known_location"]["lat"], 22.5431)
        self.assertEqual(device["observability"]["location_belief"]["state"], "Predicted")
        self.assertEqual(device["observability"]["location_belief"]["reason"], "last_known_after_gnss_no_fix")
        self.assertEqual(device["observability"]["location_memory"]["state"], "Fine")
        self.assertEqual(exported["observability_summary"]["latest_observability"]["location_belief"]["state"], "Predicted")
        self.assertEqual(exported["observability_summary"]["latest_observability"]["location_memory"]["state"], "Fine")

    def test_unknown_location_observation_preserves_prior_location_memory(self) -> None:
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
                    source="sim7670g_firmware_gnss",
                    source_status="observed",
                    fix=True,
                    lat=22.5431,
                    lon=114.0579,
                    hdop=0.9,
                    satellites=12,
                    gnss_state="fix",
                ),
            )
            store.ingest(
                "ego-link-001",
                "telemetry",
                protocol.event_message(
                    "ego-link-001",
                    "2026-06-27T00:02:01Z",
                    2,
                    "location_observation",
                    "normal",
                    source="sim7670g_firmware_cell",
                    source_status="observed",
                    cell={"rat": "LTE", "cell_id": "cell-002", "registration_state": "registered_home"},
                    lte={"reason_code": "LTE_READY", "query_ok": True},
                    location_belief={
                        "state": "Unknown",
                        "source": ["cell"],
                        "reason": "cell_observation_without_position_fix",
                    },
                ),
            )
            device = store.get_device("ego-link-001")

        self.assertEqual(device["latest_location"]["event_type"], "location_observation")
        self.assertEqual(device["location_memory"]["state"], "Fine")
        self.assertEqual(device["location_memory"]["reason"], "gnss_fix_calibration")
        self.assertEqual(device["location_memory"]["last_unknown_observation"]["cell_id"], "cell-002")
        self.assertEqual(device["observability"]["location_belief"]["state"], "Predicted")
        self.assertEqual(
            device["observability"]["location_belief"]["reason"],
            "last_known_after_unknown_location_observation",
        )

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

    def test_raw_frame_ingest_retains_checksum_failed_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            raw = (
                b"EGLK/1 type=event id=bad-frame seq=1 len=7 crc32=00000000\n"
                b"content-type=text/x-egolink-kv\n\n"
                b"foo=bar"
            )
            record = store.ingest_raw_frame("ego-link-001", raw)
            listed = store.list_raw_frames("ego-link-001")

        self.assertEqual(record["parse_result"]["status"], "checksum_failed")
        self.assertEqual(record["parse_result"]["error_code"], "RAW_FRAME_PAYLOAD_CRC_MISMATCH")
        self.assertEqual(record["raw_payload"]["byte_len"], len(raw))
        self.assertIn("data", record["raw_payload"])
        self.assertEqual(listed[0]["frame_id"], "bad-frame")
        self.assertTrue(listed[0]["raw_payload"]["data_redacted"])
        self.assertNotIn("data", listed[0]["raw_payload"])

    def test_raw_ack_frame_updates_command_after_raw_storage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            store.create_test_run({"test_run_id": "raw-frame-test"})
            command = store.create_command(
                "ego-link-001",
                {"cmd": "set_report_interval", "test_run_id": "raw-frame-test", "payload": {"interval_ms": 5000}},
            )
            payload = (
                f"cmd_id={command['cmd_id']}\n"
                "status=ok\n"
                "test_run_id=raw-frame-test\n"
            ).encode("utf-8")
            frame = message_hub.build_raw_frame(
                "ack",
                command["cmd_id"],
                payload,
                metadata={"test-run-id": "raw-frame-test"},
            )
            record = store.ingest_raw_frame(
                "ego-link-001",
                frame,
                expected_frame_type="ack",
                expected_cmd_id=command["cmd_id"],
            )
            commands = store.list_commands("ego-link-001")
            exported = store.export_test_run("raw-frame-test")

        self.assertEqual(record["parse_result"]["status"], "ok")
        self.assertEqual(record["parse_result"]["derived_message_type"], "ack")
        self.assertEqual(commands[0]["status"], "ok")
        self.assertEqual(commands[0]["ack"]["cmd_id"], command["cmd_id"])
        self.assertEqual(commands[0]["ack"]["raw_frame"]["transport_profile"], "raw-frame.p0.v1")
        self.assertEqual(exported["raw_frames"][0]["frame_id"], command["cmd_id"])
        self.assertTrue(exported["raw_frames"][0]["raw_payload"]["data_redacted"])

    def test_raw_location_event_derives_location_report_after_raw_storage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            store.create_test_run({"test_run_id": "raw-location-test"})
            payload = (
                "event_type=location_report\n"
                "priority=normal\n"
                "fw_version=0.1.0-lte004-raw-lte-location\n"
                "test_run_id=raw-location-test\n"
                "seq=42\n"
                "source=sim7670g_firmware_gnss\n"
                "source_status=unverified\n"
                "fix=false\n"
                "gnss_state=no_fix\n"
                "gnss_source=sim7670g_uart_at\n"
                "gnss_driver=uart_at\n"
                "gnss_query_ok=true\n"
                "lat=null\n"
                "lon=null\n"
                "satellites=0\n"
                "location_request_cmd_id=cmd-raw-location\n"
                "transport_type=lte\n"
                "lte_http_phase=location_report\n"
                "lte_http_driver=sim7670g_uart_at_http\n"
            ).encode("utf-8")
            frame = message_hub.build_raw_frame(
                "event",
                "loc-cmd-raw-location",
                payload,
                metadata={"test-run-id": "raw-location-test"},
            )
            record = store.ingest_raw_frame("ego-link-001", frame)
            history = store.telemetry_history("ego-link-001")
            device = store.get_device("ego-link-001")
            exported = store.export_test_run("raw-location-test")

        self.assertEqual(record["parse_result"]["status"], "ok")
        self.assertEqual(record["parse_result"]["derived_message_type"], "event")
        self.assertEqual(history[0]["event_type"], "location_report")
        self.assertEqual(history[0]["test_run_id"], "raw-location-test")
        self.assertIs(history[0]["fix"], False)
        self.assertIsNone(history[0].get("lat"))
        self.assertEqual(history[0]["gnss_state"], "no_fix")
        self.assertEqual(history[0]["gnss_query_ok"], True)
        self.assertEqual(history[0]["location_request_cmd_id"], "cmd-raw-location")
        self.assertEqual(history[0]["transport"]["type"], "lte")
        self.assertEqual(history[0]["lte_http"]["phase"], "location_report")
        self.assertEqual(device["latest_location"]["event_type"], "location_report")
        self.assertEqual(device["location_memory"]["state"], "Unknown")
        self.assertEqual(device["location_memory"]["reason"], "gnss_no_fix_no_location_memory")
        self.assertEqual(exported["raw_frames"][0]["frame_id"], "loc-cmd-raw-location")
        self.assertTrue(exported["raw_frames"][0]["raw_payload"]["data_redacted"])

    def test_raw_location_observation_derives_cell_lte_after_raw_storage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            store.create_test_run({"test_run_id": "raw-cell-observation-test"})
            payload = (
                "event_type=location_observation\n"
                "priority=normal\n"
                "fw_version=0.1.0-loc004a-cell-observation\n"
                "test_run_id=raw-cell-observation-test\n"
                "seq=43\n"
                "source=sim7670g_firmware_cell\n"
                "source_status=observed\n"
                "location_request_cmd_id=cmd-raw-observation\n"
                "cell_rat=LTE\n"
                "cell_mcc=460\n"
                "cell_mnc=01\n"
                "cell_tac=2A0B\n"
                "cell_id=01AF23\n"
                "cell_rssi=-63\n"
                "cell_rsrp=-91\n"
                "cell_rsrq=-12\n"
                "cell_sinr=17\n"
                "cell_registration_state=registered_home\n"
                "cell_pdp_state=active\n"
                "lte_driver=sim7670g_uart_at\n"
                "lte_query_ok=true\n"
                "lte_uart_ready=true\n"
                "lte_at_ok=true\n"
                "lte_sim_ready=true\n"
                "lte_registered=true\n"
                "lte_attached=true\n"
                "lte_pdp_active=true\n"
                "lte_ip_valid=true\n"
                "lte_sim_state=READY\n"
                "lte_registration_state=registered_home\n"
                "lte_apn_state=configured\n"
                "lte_pdp_state=active\n"
                "lte_assigned_ip=10.1.2.3\n"
                "lte_reason_code=LTE_READY\n"
                "wifi_source=esp_wifi_sta\n"
                "wifi_source_status=disabled\n"
                "wifi_evidence_status=missing\n"
                "wifi_scan_enabled=false\n"
                "wifi_ap_count=0\n"
                "wifi_privacy=raw_bssid_not_collected\n"
                "wifi_reason=wifi_disabled_in_lte_location_observation\n"
                "imu_source=platform_imu\n"
                "imu_source_status=unverified\n"
                "imu_evidence_status=mock\n"
                "imu_motion=unknown\n"
                "imu_confidence=null\n"
                "imu_hardware_present=false\n"
                "imu_driver_enabled=false\n"
                "imu_data_is_mock=true\n"
                "imu_backend_status=mock_stationary\n"
                "imu_reason=imu_backend_not_product_verified\n"
                "power_source=platform_power\n"
                "power_source_status=mock\n"
                "power_evidence_status=mock\n"
                "power_soc_pct=87\n"
                "power_charging=false\n"
                "power_battery_source=mock_battery_percent\n"
                "power_charging_source=mock_charging_state\n"
                "power_state=upload\n"
                "power_marker_seq=12\n"
                "power_reason=platform_power_source_not_product_meter\n"
                "network_mode=LTE\n"
                "network_raw_post_attempt_count=5\n"
                "network_raw_post_success_count=4\n"
                "network_raw_post_failure_count=1\n"
                "network_reconnect_count=2\n"
                "network_last_error=LTE_RECONNECT_TIMEOUT\n"
                "network_last_reconnect_reason=pdp_reactivate\n"
                "cache_queued_message_count=3\n"
                "cache_dropped_message_count=1\n"
                "cache_last_drop_reason=cache_full\n"
                "cache_oldest_message_age_ms=42000\n"
                "cache_state=store_forward\n"
                "cache_retry_policy=single_retry_current_boot\n"
                "cache_retry_attempt_count=2\n"
                "cache_retry_success_count=1\n"
                "cache_retry_failure_count=1\n"
                "location_belief_state=Unknown\n"
                "location_belief_source=cell,lte,wifi,imu,power\n"
                "location_belief_reason=cell_observation_without_position_fix\n"
                "transport_type=lte\n"
                "lte_http_phase=location_observation\n"
                "lte_http_driver=sim7670g_uart_at_http\n"
            ).encode("utf-8")
            frame = message_hub.build_raw_frame(
                "event",
                "obs-cmd-raw-observation",
                payload,
                metadata={"test-run-id": "raw-cell-observation-test"},
            )
            record = store.ingest_raw_frame("ego-link-001", frame)
            history = store.telemetry_history("ego-link-001")
            device = store.get_device("ego-link-001")
            exported = store.export_test_run("raw-cell-observation-test")

        self.assertEqual(record["parse_result"]["status"], "ok")
        self.assertEqual(record["parse_result"]["derived_message_type"], "event")
        self.assertEqual(history[0]["event_type"], "location_observation")
        self.assertEqual(history[0]["cell"]["rat"], "LTE")
        self.assertEqual(history[0]["cell"]["cell_id"], "01AF23")
        self.assertEqual(history[0]["cell"]["rsrp"], -91)
        self.assertTrue(history[0]["lte"]["query_ok"])
        self.assertEqual(history[0]["lte"]["reason_code"], "LTE_READY")
        self.assertFalse(history[0]["wifi"]["scan_enabled"])
        self.assertEqual(history[0]["wifi"]["source_status"], "disabled")
        self.assertEqual(history[0]["wifi"]["evidence_status"], "missing")
        self.assertEqual(history[0]["wifi"]["ap_count"], 0)
        self.assertEqual(history[0]["imu"]["evidence_status"], "mock")
        self.assertEqual(history[0]["imu"]["motion"], "unknown")
        self.assertTrue(history[0]["imu"]["data_is_mock"])
        self.assertEqual(history[0]["power"]["evidence_status"], "mock")
        self.assertEqual(history[0]["power"]["soc_pct"], 87)
        self.assertEqual(history[0]["power"]["marker_seq"], 12)
        self.assertEqual(history[0]["reliability"]["network"]["raw_post_attempt_count"], 5)
        self.assertEqual(history[0]["reliability"]["network"]["raw_post_success_count"], 4)
        self.assertEqual(history[0]["reliability"]["network"]["raw_post_failure_count"], 1)
        self.assertEqual(history[0]["reliability"]["network"]["reconnect_count"], 2)
        self.assertEqual(history[0]["reliability"]["cache"]["dropped_message_count"], 1)
        self.assertEqual(history[0]["reliability"]["cache"]["retry_policy"], "single_retry_current_boot")
        self.assertEqual(history[0]["reliability"]["cache"]["retry_attempt_count"], 2)
        self.assertEqual(history[0]["reliability"]["cache"]["retry_success_count"], 1)
        self.assertEqual(history[0]["reliability"]["cache"]["retry_failure_count"], 1)
        self.assertEqual(history[0]["location_belief"]["state"], "Unknown")
        self.assertEqual(history[0]["location_belief"]["source"], ["cell", "lte", "wifi", "imu", "power"])
        self.assertEqual(device["latest_location"]["event_type"], "location_observation")
        self.assertEqual(device["observability"]["cell"]["cell_id"], "01AF23")
        self.assertEqual(device["observability"]["lte"]["reason_code"], "LTE_READY")
        self.assertEqual(device["observability"]["wifi"]["evidence_status"], "missing")
        self.assertEqual(device["observability"]["imu"]["evidence_status"], "mock")
        self.assertEqual(device["observability"]["power"]["evidence_status"], "mock")
        self.assertEqual(device["observability"]["reliability"]["network"]["last_error"], "LTE_RECONNECT_TIMEOUT")
        self.assertEqual(device["observability"]["reliability"]["network"]["raw_post_success_count"], 4)
        self.assertEqual(device["observability"]["reliability"]["cache"]["queued_message_count"], 3)
        self.assertEqual(device["observability"]["reliability"]["cache"]["retry_attempt_count"], 2)
        self.assertEqual(device["location_memory"]["state"], "Unknown")
        self.assertEqual(device["location_memory"]["reason"], "cell_observation_without_position_fix")
        self.assertEqual(exported["raw_frames"][0]["frame_id"], "obs-cmd-raw-observation")
        self.assertTrue(exported["raw_frames"][0]["raw_payload"]["data_redacted"])


class MessageHubDeployScriptTests(unittest.TestCase):
    def test_deploy_package_excludes_runtime_secret_files(self) -> None:
        script = (Path(__file__).resolve().parents[1] / "scripts" / "deploy_message_hub_vps.ps1").read_text(
            encoding="utf-8"
        )

        self.assertIn("function Copy-ServerSource", script)
        self.assertIn('rm -rf \'$RemoteDir/server/runtime\' \'$RemoteDir/server/__pycache__\'', script)
        self.assertIn('Copy-RelativePath "docs\\current\\key_releases"', script)
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
        self.assertEqual(exported["run_context"]["test_run_id"], "field-r1-test")
        self.assertEqual(exported["run_context"]["command"]["ack_status"], "ok")
        self.assertEqual(exported["run_context"]["failure"]["reason"], "GNSS_NO_OBSERVATION")
        self.assertEqual(exported["run_context"]["eale_p0"]["location_belief"]["state"], "Unknown")
        self.assertEqual(exported["observability_summary"]["eale_p0"]["location_belief"]["generator"]["name"], "EALE-P0")
        self.assertEqual(exported["observability_summary"]["failure_summary"]["reason"], "GNSS_NO_OBSERVATION")

    def test_state_api_includes_current_run_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            server = ThreadingHTTPServer(("127.0.0.1", 0), message_hub.make_handler(store))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                post_json(base_url, "/api/v1/test-runs", {"test_run_id": "obs003-unit"})
                post_json(
                    base_url,
                    "/api/v1/devices/ego-link-001/telemetry",
                    protocol.event_message(
                        "ego-link-001",
                        "2026-06-30T00:00:01Z",
                        1,
                        "location_report",
                        "normal",
                        fw_version="0.1.0-loc005a-source-states-unit",
                        source="sim7670g_firmware_gnss",
                        source_status="unverified",
                        fix=False,
                        gnss_state="no_fix",
                        test_run_id="obs003-unit",
                    ),
                )
                post_json(
                    base_url,
                    "/api/v1/devices/ego-link-001/commands",
                    {
                        "cmd": "set_report_interval",
                        "test_run_id": "old-pending-run",
                        "payload": {"interval_ms": 10000},
                    },
                )
                state = get_json(base_url, "/api/state")
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        current_run = state["current_run"]
        self.assertEqual(current_run["test_run_id"], "obs003-unit")
        self.assertEqual(current_run["fw_version"], "0.1.0-loc005a-source-states-unit")
        self.assertEqual(current_run["key_release"]["release_id"], "unreleased")
        self.assertEqual(current_run["key_release"]["status"], "unreleased_run")
        self.assertIn("baseline", current_run["key_release"])
        self.assertEqual(current_run["location"]["event_type"], "location_report")
        self.assertEqual(current_run["failure"]["state"], "warning")
        self.assertNotEqual(current_run["failure"]["reason"], "command_pending_ack_missing")
        self.assertIn("GNSS_NO_FIX", current_run["failure"]["reason_codes"])
        self.assertEqual(current_run["eale_p0"]["location_belief"]["state"], "Unknown")
        self.assertEqual(current_run["eale_p0"]["location_belief"]["failure_reason"], "GNSS_NO_FIX")
        self.assertEqual(current_run["evidence_counts"]["commands"], 0)

    def test_eale_p0_summary_uses_source_states_and_dataset_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            server = ThreadingHTTPServer(("127.0.0.1", 0), message_hub.make_handler(store))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                post_json(base_url, "/api/v1/test-runs", {"test_run_id": "alg001-unit"})
                command = post_json(
                    base_url,
                    "/api/v1/devices/ego-link-001/commands",
                    {"cmd": "request_location", "test_run_id": "alg001-unit"},
                )["command"]
                post_json(
                    base_url,
                    "/api/v1/devices/ego-link-001/telemetry",
                    protocol.event_message(
                        "ego-link-001",
                        "2026-06-30T00:00:01Z",
                        1,
                        "location_report",
                        "normal",
                        fw_version="0.1.0-loc005a-source-states",
                        source="sim7670g_firmware_gnss",
                        source_status="unverified",
                        fix=False,
                        gnss_state="no_fix",
                        gnss_query_ok=True,
                        location_request_cmd_id=command["cmd_id"],
                        transport={"type": "lte"},
                        test_run_id="alg001-unit",
                    ),
                )
                post_json(
                    base_url,
                    "/api/v1/devices/ego-link-001/telemetry",
                    protocol.event_message(
                        "ego-link-001",
                        "2026-06-30T00:00:02Z",
                        2,
                        "location_observation",
                        "normal",
                        fw_version="0.1.0-loc005a-source-states",
                        location_request_cmd_id=command["cmd_id"],
                        cell={"rat": "LTE", "cell_id": "180571649", "rsrp": -98},
                        lte={"reason_code": "LTE_READY", "assigned_ip": "10.0.0.8"},
                        wifi={"source_status": "disabled", "evidence_status": "missing"},
                        imu={"source_status": "unverified", "evidence_status": "ok"},
                        power={"source_status": "mock", "evidence_status": "ok"},
                        location_belief={"state": "Unknown", "reason": "cell_lte_only"},
                        transport={"type": "lte"},
                        test_run_id="alg001-unit",
                    ),
                )
                post_json(
                    base_url,
                    f"/api/v1/devices/ego-link-001/commands/{command['cmd_id']}/ack",
                    {
                        "device_id": "ego-link-001",
                        "seq": 3,
                        "status": "ok",
                        "test_run_id": "alg001-unit",
                        "transport": {"type": "lte"},
                    },
                )
                state = get_json(base_url, "/api/state")
                exported = get_json(base_url, "/api/v1/test-runs/alg001-unit/export")
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        eale = state["current_run"]["eale_p0"]
        belief = eale["location_belief"]
        dataset = eale["dataset_window"]
        self.assertEqual(belief["state"], "Unknown")
        self.assertEqual(belief["substate"], "no_precise_fix")
        self.assertEqual(belief["reason"], "gnss_no_fix_cell_lte_observed_no_position_memory")
        self.assertEqual(belief["failure_reason"], "GNSS_NO_FIX")
        self.assertIn("cell_lte", belief["source"])
        self.assertIn("cell_lte_not_position_source", belief["quality_flags"])
        self.assertIn("wifi_disabled", belief["quality_flags"])
        self.assertIn("imu_unverified", belief["quality_flags"])
        self.assertIn("power_mock", belief["quality_flags"])
        self.assertEqual(dataset["sample_type"], "failure_window")
        self.assertEqual(dataset["status"], "candidate_with_warnings")
        self.assertFalse(dataset["training_allowed"])
        self.assertEqual(exported["run_context"]["eale_p0"]["location_belief"]["reason"], belief["reason"])
        self.assertEqual(exported["observability_summary"]["eale_p0"]["dataset_window"]["sample_type"], "failure_window")

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

    def test_http_raw_command_poll_and_ack_routes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            server = ThreadingHTTPServer(("127.0.0.1", 0), message_hub.make_handler(store))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                command = post_json(
                    base_url,
                    "/api/v1/devices/ego-link-001/commands",
                    {"cmd": "set_report_interval", "payload": {"interval_ms": 5000}},
                )["command"]
                raw_command, content_type = get_bytes(base_url, "/api/v1/devices/ego-link-001/commands/poll.raw")
                ack_payload = (
                    f"cmd_id={command['cmd_id']}\n"
                    "status=ok\n"
                    "message=lte raw command loop acknowledged set_report_interval\n"
                    "fw_version=0.1.0-fw003-raw-command-loop\n"
                    "test_run_id=raw-frame-test\n"
                    "transport_type=lte\n"
                    "lte_http_phase=command_ack\n"
                    "lte_http_poll_reason_code=LTE_HTTP_OK\n"
                    "lte_http_poll_status_code=200\n"
                    "lte_http_poll_action_elapsed_ms=1234\n"
                    "command_parse_status=raw_command_selected\n"
                    "command_count=1\n"
                    "duplicate_local_execution_prevented=false\n"
                ).encode("utf-8")
                raw_ack = message_hub.build_raw_frame("ack", command["cmd_id"], ack_payload)
                ack = post_bytes(
                    base_url,
                    f"/api/v1/devices/ego-link-001/commands/{command['cmd_id']}/ack.raw",
                    raw_ack,
                )
                raw_frames = get_json(base_url, "/api/v1/devices/ego-link-001/raw-frames")["raw_frames"]
                commands = get_json(base_url, "/api/v1/devices/ego-link-001/commands")["commands"]
                state = get_json(base_url, "/api/state")
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertTrue(raw_command.startswith(b"EGLK/1 type=command"))
        self.assertIn("raw-frame.p0.v1", content_type)
        self.assertEqual(ack["raw_frame"]["parse_result"]["status"], "ok")
        self.assertEqual(commands[0]["status"], "ok")
        self.assertEqual(commands[0]["ack"]["fw_version"], "0.1.0-fw003-raw-command-loop")
        self.assertEqual(commands[0]["ack"]["test_run_id"], "raw-frame-test")
        self.assertEqual(commands[0]["ack"]["transport"]["type"], "lte")
        self.assertEqual(commands[0]["ack"]["lte_http"]["phase"], "command_ack")
        self.assertEqual(commands[0]["ack"]["lte_http"]["poll_reason_code"], "LTE_HTTP_OK")
        self.assertEqual(commands[0]["ack"]["lte_http"]["poll_status_code"], 200)
        self.assertEqual(commands[0]["ack"]["command"]["parse_status"], "raw_command_selected")
        self.assertFalse(commands[0]["ack"]["command"]["duplicate_local_execution_prevented"])
        self.assertGreaterEqual(len(raw_frames), 2)
        self.assertNotIn("data", raw_frames[0]["raw_payload"])
        self.assertIn("raw_frames", state)


if __name__ == "__main__":
    unittest.main()

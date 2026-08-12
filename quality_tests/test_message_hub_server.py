from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import threading
from http.server import ThreadingHTTPServer
import unittest
from unittest import mock
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
                            "flush_attempt_count": 2,
                            "flush_success_count": 1,
                            "flush_failure_count": 1,
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
        self.assertEqual(reliability["cache"]["flush_success_count"], 1)
        self.assertIn("LTE_RECONNECT_TIMEOUT", device["observability"]["explainability"]["reason_codes"])
        self.assertEqual(
            exported["observability_summary"]["latest_observability"]["reliability"]["cache"]["last_drop_reason"],
            "cache_full",
        )
        self.assertEqual(exported["run_context"]["reliability"]["network"]["last_reconnect_reason"], "pdp_reactivate")
        self.assertEqual(exported["run_context"]["reliability"]["cache"]["flush_attempt_count"], 2)

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

    def test_d1_track_points_survive_long_indoor_no_fix_burst(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            base = datetime.now(timezone.utc) - timedelta(seconds=700)

            def ts(offset: int) -> str:
                return (base + timedelta(seconds=offset)).isoformat()

            for seq, lat, lon in (
                (1, 22.5431, 113.9321),
                (2, 22.5438, 113.9328),
            ):
                store.ingest(
                    "ego-link-001",
                    "telemetry",
                    protocol.event_message(
                        "ego-link-001",
                        ts(seq),
                        seq,
                        "location_report",
                        "normal",
                        source="sim7670g_firmware_gnss",
                        source_status="observed",
                        fix=True,
                        lat=lat,
                        lon=lon,
                        gnss={"fix": True, "state": "fix"},
                        cell={"rat": "LTE", "cell_id": "unit-cell", "registration_state": "registered_home"},
                        lte={"registered": True, "pdp_active": True, "reason_code": "LTE_READY"},
                        imu={"motion": "walking", "evidence_status": "mock"},
                        power={"battery_mv": 4100 - seq, "soc_pct": 90, "evidence_status": "measured"},
                        reliability={
                            "network": {
                                "raw_post_attempt_count": seq,
                                "raw_post_success_count": seq,
                                "raw_post_failure_count": 0,
                            }
                        },
                    ),
                )

            for seq in range(3, 603):
                store.ingest(
                    "ego-link-001",
                    "telemetry",
                    protocol.event_message(
                        "ego-link-001",
                        ts(seq),
                        seq,
                        "location_observation",
                        "normal",
                        source="sim7670g_firmware_cell",
                        source_status="observed",
                        cell={"rat": "LTE", "cell_id": "unit-cell", "registration_state": "registered_home"},
                        lte={"registered": True, "pdp_active": True, "reason_code": "LTE_READY"},
                        imu={"motion": "stationary", "evidence_status": "mock"},
                        power={"battery_mv": 4090 - (seq % 5), "soc_pct": 89, "evidence_status": "measured"},
                        location_belief={
                            "state": "Unknown",
                            "reason": "cell_observation_without_position_fix",
                            "source": ["cell", "lte", "imu", "power"],
                        },
                        reliability={
                            "network": {
                                "raw_post_attempt_count": seq,
                                "raw_post_success_count": seq,
                                "raw_post_failure_count": 0,
                            }
                        },
                    ),
                )

            d1 = store.get_device("ego-link-001")["d1_link"]

        diagnostics = d1["map_surface"]["coordinate_diagnostics"]
        self.assertEqual(d1["acceptance_gate"]["status"], "ready")
        self.assertEqual(d1["acceptance_gate"]["track_points"], 2)
        self.assertEqual(diagnostics["location_event_count"], message_hub.D1_SUMMARY_MESSAGE_LIMIT + 2)
        self.assertEqual(diagnostics["coordinate_event_count"], 2)
        self.assertEqual(diagnostics["missing_coordinate_event_count"], message_hub.D1_SUMMARY_MESSAGE_LIMIT)
        self.assertEqual(diagnostics["latest_missing_reason"], "cell_observation_without_position_fix")

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
                "power_battery_mv=3920\n"
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
                "cache_flush_attempt_count=2\n"
                "cache_flush_success_count=1\n"
                "cache_flush_failure_count=1\n"
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
        self.assertEqual(history[0]["power"]["battery_mv"], 3920)
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
        self.assertEqual(history[0]["reliability"]["cache"]["flush_attempt_count"], 2)
        self.assertEqual(history[0]["reliability"]["cache"]["flush_success_count"], 1)
        self.assertEqual(history[0]["reliability"]["cache"]["flush_failure_count"], 1)
        self.assertEqual(history[0]["location_belief"]["state"], "Unknown")
        self.assertEqual(history[0]["location_belief"]["source"], ["cell", "lte", "wifi", "imu", "power"])
        self.assertEqual(device["latest_location"]["event_type"], "location_observation")
        self.assertEqual(device["observability"]["cell"]["cell_id"], "01AF23")
        self.assertEqual(device["observability"]["lte"]["reason_code"], "LTE_READY")
        self.assertEqual(device["observability"]["wifi"]["evidence_status"], "missing")
        self.assertEqual(device["observability"]["imu"]["evidence_status"], "mock")
        self.assertEqual(device["observability"]["power"]["evidence_status"], "mock")
        self.assertEqual(device["observability"]["power"]["battery_mv"], 3920)
        self.assertEqual(device["observability"]["reliability"]["network"]["last_error"], "LTE_RECONNECT_TIMEOUT")
        self.assertEqual(device["observability"]["reliability"]["network"]["raw_post_success_count"], 4)
        self.assertEqual(device["observability"]["reliability"]["cache"]["queued_message_count"], 3)
        self.assertEqual(device["observability"]["reliability"]["cache"]["retry_attempt_count"], 2)
        self.assertEqual(device["observability"]["reliability"]["cache"]["flush_success_count"], 1)
        self.assertEqual(device["location_memory"]["state"], "Unknown")
        self.assertEqual(device["location_memory"]["reason"], "cell_observation_without_position_fix")
        self.assertEqual(exported["raw_frames"][0]["frame_id"], "obs-cmd-raw-observation")
        self.assertTrue(exported["raw_frames"][0]["raw_payload"]["data_redacted"])

    def test_raw_location_observation_preserves_measured_power_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            store.create_test_run({"test_run_id": "pwr001-measured-power"})
            payload = (
                "event_type=location_observation\n"
                "priority=normal\n"
                "fw_version=0.1.0-pwr001-measured-power\n"
                "test_run_id=pwr001-measured-power\n"
                "seq=44\n"
                "source=sim7670g_firmware_cell\n"
                "source_status=observed\n"
                "location_request_cmd_id=cmd-pwr001-measured\n"
                "cell_rat=LTE\n"
                "cell_id=180571649\n"
                "lte_reason_code=LTE_READY\n"
                "power_source=platform_power\n"
                "power_source_status=measured\n"
                "power_evidence_status=measured\n"
                "power_battery_mv=4012\n"
                "power_soc_pct=78\n"
                "power_charging=false\n"
                "power_battery_source=max17048_i2c\n"
                "power_charging_source=mock\n"
                "power_state=UPLOAD\n"
                "power_marker_seq=22\n"
                "power_reason=max17048_sample_ok\n"
                "location_belief_state=Unknown\n"
                "location_belief_source=cell,lte,power\n"
                "location_belief_reason=cell_observation_without_position_fix\n"
                "transport_type=lte\n"
                "lte_http_phase=location_observation\n"
                "lte_http_driver=sim7670g_uart_at_http\n"
            ).encode("utf-8")
            frame = message_hub.build_raw_frame(
                "event",
                "obs-pwr001-measured",
                payload,
                metadata={"test-run-id": "pwr001-measured-power"},
            )
            record = store.ingest_raw_frame("ego-link-001", frame)
            history = store.telemetry_history("ego-link-001")
            device = store.get_device("ego-link-001")
            exported = store.export_test_run("pwr001-measured-power")

        self.assertEqual(record["parse_result"]["status"], "ok")
        self.assertEqual(record["parse_result"]["derived_message_type"], "event")
        self.assertEqual(history[0]["power"]["source"], "platform_power")
        self.assertEqual(history[0]["power"]["source_status"], "measured")
        self.assertEqual(history[0]["power"]["evidence_status"], "measured")
        self.assertEqual(history[0]["power"]["battery_mv"], 4012)
        self.assertEqual(history[0]["power"]["soc_pct"], 78)
        self.assertFalse(history[0]["power"]["charging"])
        self.assertEqual(history[0]["power"]["battery_source"], "max17048_i2c")
        self.assertEqual(history[0]["power"]["charging_source"], "mock")
        self.assertEqual(history[0]["power"]["state"], "UPLOAD")
        self.assertEqual(history[0]["power"]["marker_seq"], 22)
        self.assertEqual(device["observability"]["power"]["source_status"], "measured")
        self.assertEqual(device["observability"]["power"]["evidence_status"], "measured")
        self.assertEqual(device["observability"]["power"]["battery_mv"], 4012)
        self.assertEqual(device["observability"]["power"]["soc_pct"], 78)
        d1_power_curve = device["d1_link"]["power_curve"]
        self.assertEqual(d1_power_curve["sample_count"], 1)
        self.assertEqual(d1_power_curve["latest"]["source_status"], "measured")
        self.assertEqual(d1_power_curve["latest"]["evidence_status"], "measured")
        self.assertEqual(d1_power_curve["latest"]["battery_mv"], 4012)
        self.assertEqual(exported["messages"][0]["power"]["source_status"], "measured")
        self.assertEqual(exported["messages"][0]["power"]["battery_source"], "max17048_i2c")


class MessageHubDeployScriptTests(unittest.TestCase):
    def test_deploy_package_excludes_runtime_secret_files(self) -> None:
        script = (Path(__file__).resolve().parents[1] / "scripts" / "deploy_message_hub_vps.ps1").read_text(
            encoding="utf-8"
        )

        self.assertIn("function Copy-ServerSource", script)
        self.assertIn('rm -rf \'$RemoteDir/server/runtime\' \'$RemoteDir/server/__pycache__\'', script)
        self.assertIn('Copy-RelativePath "docs\\current\\key_releases"', script)
        self.assertIn('Copy-RelativePath "docs\\generated\\progress_board.json"', script)
        self.assertIn('$remoteScript = $remoteScript.Replace("`r", "")', script)
        self.assertNotIn('Copy-RelativePath "server"', script)

    def test_runtime_secret_files_are_ignored_but_example_is_tracked(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        ignore_file = (repo_root / ".gitignore").read_text(encoding="utf-8")
        example = (repo_root / "server" / ".env.example").read_text(encoding="utf-8")

        self.assertIn("**/.env", ignore_file)
        self.assertIn("**/.env.*", ignore_file)
        self.assertIn("!**/.env.example", ignore_file)
        self.assertIn("EGOLINK_AMAP_JS_API_KEY=replace-with-amap-js-api-key", example)
        self.assertIn("EGOLINK_AMAP_SECURITY_JS_CODE=replace-with-amap-security-js-code", example)

    def test_deploy_runtime_environment_uses_fixed_atomic_upsert(self) -> None:
        script = (Path(__file__).resolve().parents[1] / "scripts" / "deploy_message_hub_vps.ps1").read_text(
            encoding="utf-8"
        )

        self.assertIn('"EGOLINK_MESSAGE_HUB_TOKEN"', script)
        self.assertIn('"EGOLINK_AMAP_JS_API_KEY"', script)
        self.assertIn('"EGOLINK_AMAP_SECURITY_JS_CODE"', script)
        self.assertIn("must be a single-line runtime value", script)
        self.assertIn("mktemp /etc/egolink-message-hub.env.XXXXXX", script)
        self.assertIn("grep -Ev '^(__UPSERT_NAMES__)='", script)
        self.assertIn('mv -f "$env_tmp" /etc/egolink-message-hub.env', script)
        self.assertIn("chmod 600", script)
        self.assertNotIn(">/etc/egolink-message-hub.env", script)


class MessageHubAmapCoordinateTrustTests(unittest.TestCase):
    def test_location_memory_without_lineage_is_never_amap_eligible(self) -> None:
        surface = message_hub.build_d1_map_surface(
            messages=[],
            latest_location={},
            location_memory={
                "updated_at": "2026-08-12T10:00:00+00:00",
                "last_known_location": {
                    "lat": 22.5431,
                    "lon": 114.0579,
                    "updated_at": "2026-08-12T09:00:00+00:00",
                },
            },
            map_mode="memory_coordinate",
            map_lat=22.5431,
            map_lon=114.0579,
            coordinate_source="location_memory",
            visible=True,
        )

        self.assertEqual(surface["amap_eligible_point_count"], 0)
        self.assertEqual(surface["amap_hidden_point_count"], 1)
        self.assertFalse(surface["points"][0]["amap_eligible"])
        self.assertEqual(surface["points"][0]["fw_version"], "unknown")
        self.assertEqual(
            surface["points"][0]["amap_exclusion_reason"],
            "location_memory_has_no_coordinate_provenance",
        )

    def test_only_allowlisted_fixed_location_report_is_wgs84_eligible(self) -> None:
        base = {
            "message_type": "event",
            "event_type": "location_report",
            "fix": True,
            "lat": 22.5431,
            "lon": 114.0579,
            "server_received_at": "2026-08-12T10:00:00+00:00",
        }
        trusted = message_hub.d1_location_point(
            {**base, "fw_version": "0.1.0-fw005-gnss-correctness"},
            source="unit",
        )
        old = message_hub.d1_location_point(
            {**base, "fw_version": "0.1.0-field011-gnss-imu"},
            source="unit",
        )
        unknown = message_hub.d1_location_point(base, source="unit")
        no_fix = message_hub.d1_location_point(
            {**base, "fw_version": "0.1.0-fw005-gnss-correctness", "fix": False},
            source="unit",
        )
        observation = message_hub.d1_location_point(
            {
                **base,
                "event_type": "location_observation",
                "fw_version": "0.1.0-fw005-gnss-correctness",
            },
            source="unit",
        )

        self.assertIsNotNone(trusted)
        self.assertTrue(trusted["amap_eligible"])
        self.assertEqual(trusted["coordinate_contract"], "wgs84")
        for point in (old, unknown, no_fix, observation):
            self.assertIsNotNone(point)
            self.assertFalse(point["amap_eligible"])
            self.assertEqual(point["coordinate_contract"], "unknown")

    def test_out_of_range_location_is_rejected_before_amap_provenance(self) -> None:
        point = message_hub.d1_location_point(
            {
                "message_type": "event",
                "event_type": "location_report",
                "fw_version": "0.1.0-fw005-gnss-correctness",
                "fix": True,
                "lat": 91,
                "lon": 181,
            },
            source="unit",
        )

        self.assertIsNone(point)


class MessageHubHttpTests(unittest.TestCase):
    def test_amap_proxy_target_is_fixed_and_overrides_client_jscode(self) -> None:
        host, target = message_hub.amap_proxy_target(
            "/_AMapService/v3/assistant/coordinate/convert",
            "locations=116.3,39.9&coordsys=gps&key=attacker&KEY=attacker2&jscode=attacker&JSCODE=attacker2",
            "public_JS_key_1234",
            "server_security_1234",
        )
        style_host, style_target = message_hub.amap_proxy_target(
            "/_AMapService/v4/map/styles",
            "styleid=unit",
            "public_JS_key_1234",
            "server_security_1234",
        )
        log_host, log_target = message_hub.amap_proxy_target(
            "/_AMapService/v3/log/init",
            "eventId=resource.load&platform=JS&key=attacker",
            "public_JS_key_1234",
            "server_security_1234",
        )

        self.assertEqual(host, "restapi.amap.com")
        self.assertEqual(style_host, "webapi.amap.com")
        self.assertEqual(log_host, "restapi.amap.com")
        self.assertIn("/v3/log/init?", log_target)
        self.assertIn("eventId=resource.load", log_target)
        self.assertNotIn("attacker", log_target)
        self.assertNotIn("attacker", target)
        self.assertEqual(target.count("key="), 1)
        self.assertEqual(target.count("jscode="), 1)
        self.assertIn("key=public_JS_key_1234", target)
        self.assertIn("jscode=server_security_1234", target)
        self.assertIn("key=public_JS_key_1234", style_target)
        self.assertIn("jscode=server_security_1234", style_target)
        with self.assertRaises(message_hub.MessageHubError):
            message_hub.amap_proxy_target(
                "/_AMapService/v3/config/district",
                "",
                "public_JS_key_1234",
                "server_security_1234",
            )
        for noncanonical_path in (
            "/_AMapService/v3//assistant/coordinate/convert",
            "/_AMapService/v3/assistant/coordinate/convert/",
            "/_AMapService/v4//map/styles",
            "/_AMapService/v4/map/styles/",
        ):
            with self.assertRaises(message_hub.MessageHubError):
                message_hub.amap_proxy_target(
                    noncanonical_path,
                    "",
                    "public_JS_key_1234",
                    "server_security_1234",
                )

    def test_amap_cookie_is_short_lived_signed_and_path_scoped(self) -> None:
        secret = message_hub.amap_proxy_cookie_secret("hub-token", "server_security_1234")
        set_cookie = message_hub.issue_amap_proxy_cookie(secret, now=1_000)
        cookie_pair = set_cookie.split(";", 1)[0]

        self.assertIn("HttpOnly", set_cookie)
        self.assertIn("SameSite=Strict", set_cookie)
        self.assertIn("Path=/_AMapService", set_cookie)
        self.assertIn("Secure", set_cookie)
        self.assertTrue(message_hub.amap_proxy_cookie_valid(cookie_pair, secret, now=1_001))
        self.assertFalse(message_hub.amap_proxy_cookie_valid(cookie_pair, secret, now=1_301))
        self.assertFalse(message_hub.amap_proxy_cookie_valid(cookie_pair + "tampered", secret, now=1_001))
        self.assertNotIn("server_security_1234", set_cookie)
        self.assertNotIn("hub-token", set_cookie)

    def test_amap_proxy_requires_signed_cookie_even_with_forged_origin_headers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            hub_token = "unit-hub-token"
            environment = {
                message_hub.AMAP_JS_API_KEY_ENV: "public_JS_key_1234",
                message_hub.AMAP_SECURITY_JS_CODE_ENV: "server_security_1234",
            }
            with mock.patch.dict("os.environ", environment, clear=False):
                server = ThreadingHTTPServer(("127.0.0.1", 0), message_hub.make_handler(store, token=hub_token))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                with self.assertRaises(error.HTTPError) as forged_headers:
                    req = request.Request(
                        base_url + "/_AMapService/v3/assistant/coordinate/convert?locations=116.3,39.9&coordsys=gps",
                        headers={
                            "Host": f"127.0.0.1:{server.server_port}",
                            "Origin": base_url,
                            "Referer": base_url + "/",
                            "Sec-Fetch-Site": "same-origin",
                        },
                    )
                    request.urlopen(req, timeout=5)
                forged_headers.exception.close()
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertEqual(forged_headers.exception.code, 403)

    def test_authenticated_state_issues_amap_cookie_without_exposing_secret(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            environment = {
                message_hub.AMAP_JS_API_KEY_ENV: "public_JS_key_1234",
                message_hub.AMAP_SECURITY_JS_CODE_ENV: "server_security_1234",
            }
            with mock.patch.dict("os.environ", environment, clear=False):
                server = ThreadingHTTPServer(
                    ("127.0.0.1", 0),
                    message_hub.make_handler(store, token="secret"),
                )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                req = request.Request(
                    base_url + "/api/state",
                    headers={"Authorization": "Bearer secret"},
                )
                with request.urlopen(req, timeout=5) as response:
                    payload = response.read()
                    set_cookie = response.headers.get("Set-Cookie") or ""
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertIn(f"{message_hub.AMAP_PROXY_COOKIE_NAME}=", set_cookie)
        self.assertIn("HttpOnly", set_cookie)
        self.assertIn("SameSite=Strict", set_cookie)
        self.assertIn("Secure", set_cookie)
        self.assertNotIn("server_security_1234", set_cookie)
        self.assertNotIn(b"server_security_1234", payload)

    def test_amap_proxy_response_is_bounded_no_store_and_nosniff(self) -> None:
        class FakeResponse:
            status = 200

            def __init__(self) -> None:
                self.chunks = [b'{"locations":["116.3,39.9"]}', b""]

            def getheader(self, name: str) -> str | None:
                return {
                    "Content-Length": "31",
                    "Content-Type": "application/json; charset=utf-8",
                }.get(name)

            def read(self, _size: int) -> bytes:
                return self.chunks.pop(0)

        class FakeConnection:
            instances: list["FakeConnection"] = []

            def __init__(self, host: str, timeout: float) -> None:
                self.host = host
                self.timeout = timeout
                self.target = ""
                self.sock = None
                self.__class__.instances.append(self)

            def request(self, method: str, target: str, headers: dict[str, str]) -> None:
                self.target = target

            def getresponse(self) -> FakeResponse:
                return FakeResponse()

            def close(self) -> None:
                return

        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            environment = {
                message_hub.AMAP_JS_API_KEY_ENV: "public_JS_key_1234",
                message_hub.AMAP_SECURITY_JS_CODE_ENV: "server_security_1234",
            }
            with mock.patch.dict("os.environ", environment, clear=False):
                handler = message_hub.make_handler(store, token="secret")
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                state_request = request.Request(
                    base_url + "/api/state",
                    headers={"Authorization": "Bearer secret"},
                )
                with request.urlopen(state_request, timeout=5) as response:
                    cookie = (response.headers.get("Set-Cookie") or "").split(";", 1)[0]
                proxy_request = request.Request(
                    base_url + "/_AMapService/v3/assistant/coordinate/convert?locations=116.3,39.9&coordsys=gps&key=attacker",
                    headers={
                        "Cookie": cookie,
                        "Origin": base_url,
                        "Sec-Fetch-Site": "same-origin",
                    },
                )
                with mock.patch.object(message_hub.http.client, "HTTPSConnection", FakeConnection):
                    with request.urlopen(proxy_request, timeout=5) as response:
                        response.read()
                        cache_control = response.headers.get("Cache-Control")
                        content_type = response.headers.get("Content-Type")
                        nosniff = response.headers.get("X-Content-Type-Options")
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertEqual(cache_control, "no-store")
        self.assertEqual(content_type, "application/json")
        self.assertEqual(nosniff, "nosniff")
        self.assertEqual(FakeConnection.instances[-1].host, "restapi.amap.com")
        self.assertNotIn("attacker", FakeConnection.instances[-1].target)
        self.assertEqual(FakeConnection.instances[-1].target.count("key="), 1)
        self.assertEqual(FakeConnection.instances[-1].target.count("jscode="), 1)

    def test_amap_response_content_type_and_size_are_fail_closed(self) -> None:
        self.assertEqual(message_hub.safe_amap_content_type("text/html; charset=utf-8"), "application/octet-stream")
        self.assertEqual(message_hub.safe_amap_content_type("application/json; charset=utf-8"), "application/json")
        self.assertEqual(
            message_hub.amap_proxy_content_type(
                "/v3/log/init?callback=safe_callback",
                "application/octet-stream",
            ),
            "application/javascript",
        )
        self.assertEqual(
            message_hub.amap_proxy_content_type(
                "/v3/assistant/coordinate/convert?locations=116.3,39.9",
                "text/html; charset=utf-8",
            ),
            "application/octet-stream",
        )

        class OversizeResponse:
            status = 200

            def getheader(self, name: str) -> str | None:
                if name == "Content-Length":
                    return str(message_hub.AMAP_PROXY_MAX_RESPONSE_BYTES + 1)
                return "application/json" if name == "Content-Type" else None

            def read(self, _size: int) -> bytes:
                raise AssertionError("oversized declared response must not be read")

        class OversizeConnection:
            def __init__(self, _host: str, timeout: float) -> None:
                self.timeout = timeout
                self.sock = None

            def request(self, _method: str, _target: str, headers: dict[str, str]) -> None:
                return

            def getresponse(self) -> OversizeResponse:
                return OversizeResponse()

            def close(self) -> None:
                return

        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            environment = {
                message_hub.AMAP_JS_API_KEY_ENV: "public_JS_key_1234",
                message_hub.AMAP_SECURITY_JS_CODE_ENV: "server_security_1234",
            }
            with mock.patch.dict("os.environ", environment, clear=False):
                handler = message_hub.make_handler(store, token="secret")
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                state_request = request.Request(
                    base_url + "/api/state",
                    headers={"Authorization": "Bearer secret"},
                )
                with request.urlopen(state_request, timeout=5) as response:
                    cookie = (response.headers.get("Set-Cookie") or "").split(";", 1)[0]
                proxy_request = request.Request(
                    base_url + "/_AMapService/v3/assistant/coordinate/convert?locations=116.3,39.9&coordsys=gps",
                    headers={
                        "Cookie": cookie,
                        "Origin": base_url,
                        "Sec-Fetch-Site": "same-origin",
                    },
                )
                with mock.patch.object(message_hub.http.client, "HTTPSConnection", OversizeConnection):
                    with self.assertRaises(error.HTTPError) as oversized:
                        request.urlopen(proxy_request, timeout=5)
                    oversized.exception.close()
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertEqual(oversized.exception.code, 502)

    def test_amap_security_code_never_enters_dashboard_or_state_api(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            security_code = "server_security_1234"
            environment = {
                message_hub.AMAP_JS_API_KEY_ENV: "public_JS_key_1234",
                message_hub.AMAP_SECURITY_JS_CODE_ENV: security_code,
            }
            with mock.patch.dict("os.environ", environment, clear=False):
                server = ThreadingHTTPServer(("127.0.0.1", 0), message_hub.make_handler(store, token="secret"))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                dashboard, _ = get_bytes(base_url, "/")
                state = get_json(base_url, "/api/state", headers={"Authorization": "Bearer secret"})
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertIn(b"public_JS_key_1234", dashboard)
        self.assertNotIn(security_code.encode(), dashboard)
        self.assertNotIn(security_code, json.dumps(state))

    def test_progress_board_is_available_in_state_and_dedicated_route(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = message_hub.MessageHubStore(root / "hub.db")
            progress_path = root / "progress_board.json"
            progress_path.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-07-11 15:00 UTC",
                        "git": {"branch": "main", "head": "abc123 test"},
                        "current_focus": "QMI bring-up",
                        "milestones": [{"id": "D2", "title": "Location", "done": 8, "total": 10}],
                        "operator_asks": ["Connect QMI8658"],
                        "active_tasks": [],
                        "recent_done": [],
                        "key_releases": [],
                    }
                ),
                encoding="utf-8",
            )
            server = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                message_hub.make_handler(store, progress_board_path=progress_path),
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                state = get_json(base_url, "/api/state")
                dedicated = get_json(base_url, "/api/v1/progress/latest")
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertEqual(state["progress_board"]["status"], "available")
        self.assertEqual(state["progress_board"]["current_focus"], "QMI bring-up")
        self.assertEqual(dedicated["progress_board"]["milestones"][0]["done"], 8)

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

    def test_device_field_export_is_authenticated_bounded_and_time_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            store.register_device({"device_id": "field-device", "fw_version": "field-fw"})
            store.register_device({"device_id": "other-device", "fw_version": "other-fw"})
            for device_id, seq in (
                ("field-device", 1),
                ("field-device", 2),
                ("other-device", 3),
                ("field-device", 4),
            ):
                store.ingest(
                    device_id,
                    "heartbeat",
                    {
                        "device_id": device_id,
                        "seq": seq,
                        "battery": 80,
                        "link_type": "lte",
                        "guard_mode": "field",
                        "queue_size": 0,
                    },
                )
            command = store.create_command("field-device", {"cmd": "status_snapshot", "payload": {}})
            raw_record = store.ingest_raw_frame("field-device", b"malformed-field-frame")
            with store.connection() as db:
                message_rows = db.execute(
                    "SELECT id, payload_json FROM messages ORDER BY id"
                ).fetchall()
                message_times = (
                    "2026-07-10T23:59:00+00:00",
                    "2026-07-11T00:30:00+00:00",
                    "2026-07-11T00:30:00+00:00",
                    "2026-07-11T00:50:00+00:00",
                )
                for row, received_at in zip(message_rows, message_times, strict=True):
                    payload = json.loads(row["payload_json"])
                    payload["server_received_at"] = received_at
                    db.execute(
                        "UPDATE messages SET server_received_at = ?, payload_json = ? WHERE id = ?",
                        (received_at, message_hub.dumps(payload), row["id"]),
                    )
                db.execute(
                    "UPDATE commands SET created_at = ?, updated_at = ? WHERE cmd_id = ?",
                    ("2026-07-11T00:20:00+00:00", "2026-07-11T00:20:00+00:00", command["cmd_id"]),
                )
                raw_row = db.execute(
                    "SELECT id, record_json FROM raw_frames WHERE frame_id = ?",
                    (raw_record["frame_id"],),
                ).fetchone()
                raw_payload = json.loads(raw_row["record_json"])
                raw_payload["server_received_at"] = "2026-07-11T00:40:00+00:00"
                db.execute(
                    "UPDATE raw_frames SET server_received_at = ?, record_json = ? WHERE id = ?",
                    (
                        "2026-07-11T00:40:00+00:00",
                        message_hub.dumps(raw_payload),
                        raw_row["id"],
                    ),
                )

            server = ThreadingHTTPServer(("127.0.0.1", 0), message_hub.make_handler(store, token="secret"))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            route = (
                "/api/v1/devices/field-device/field-export"
                "?started_at=2026-07-11T00%3A00%3A00Z"
                "&ended_at=2026-07-11T01%3A00%3A00Z&max_records=10"
            )
            try:
                with self.assertRaises(error.HTTPError) as unauthorized:
                    get_json(base_url, route)
                exported = get_json(base_url, route, headers={"Authorization": "Bearer secret"})
                limited = get_json(
                    base_url,
                    route.replace("max_records=10", "max_records=1"),
                    headers={"Authorization": "Bearer secret"},
                )
                with self.assertRaises(error.HTTPError) as too_wide:
                    get_json(
                        base_url,
                        "/api/v1/devices/field-device/field-export"
                        "?started_at=2026-07-01T00%3A00%3A00Z&ended_at=2026-07-11T00%3A00%3A00Z",
                        headers={"Authorization": "Bearer secret"},
                    )
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertEqual(unauthorized.exception.code, 401)
        self.assertEqual(exported["window"]["device_id"], "field-device")
        self.assertEqual(exported["window"]["duration_s"], 3600)
        self.assertTrue(exported["window"]["complete"])
        self.assertEqual(len(exported["messages"]), 2)
        self.assertEqual(exported["messages"][0]["seq"], 2)
        self.assertEqual(len(exported["commands"]), 1)
        self.assertEqual(len(exported["raw_frames"]), 1)
        self.assertNotIn("data", exported["raw_frames"][0].get("raw_payload", {}))
        self.assertTrue(limited["window"]["truncated"]["messages"])
        self.assertFalse(limited["window"]["complete"])
        self.assertEqual(too_wide.exception.code, 400)

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

    def test_state_api_exposes_d1_location_estimate_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            server = ThreadingHTTPServer(("127.0.0.1", 0), message_hub.make_handler(store))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                post_json(
                    base_url,
                    "/api/v1/devices/ego-link-001/heartbeat",
                    {
                        "device_id": "ego-link-001",
                        "seq": 0,
                        "battery": 90,
                        "battery_mv": 3990,
                        "link_type": "lte",
                        "guard_mode": "child_safety",
                        "queue_size": 0,
                    },
                )
                post_json(
                    base_url,
                    "/api/v1/devices/ego-link-001/telemetry",
                    protocol.event_message(
                        "ego-link-001",
                        "2026-07-04T00:00:00Z",
                        1,
                        "location_report",
                        "normal",
                        source="no_hardware_d1_fixture",
                        source_status="mock",
                        fix=False,
                        gnss_state="no_fix",
                        power={"battery_mv": 3980, "soc_pct": 87, "evidence_status": "mock"},
                        transport={"type": "lte"},
                        reliability={"network": {"raw_post_attempt_count": 1, "raw_post_success_count": 1, "raw_post_failure_count": 0}},
                    ),
                )
                post_json(
                    base_url,
                    "/api/v1/devices/ego-link-001/telemetry",
                    protocol.event_message(
                        "ego-link-001",
                        "2026-07-04T00:00:01Z",
                        2,
                        "location_observation",
                        "normal",
                        source="no_hardware_d1_fixture",
                        source_status="mock",
                        gnss={"enabled": True, "fix": False, "state": "no_fix", "attempt_ms": 30000},
                        cell={"rat": "LTE", "cell_id": "mock-cell-d1", "registration_state": "registered", "rsrp": -74},
                        lte={"registered": True, "pdp_active": True, "reason_code": "LTE_READY"},
                        imu={"motion": "stationary", "confidence": 0.9, "evidence_status": "mock"},
                        power={"battery_mv": 3960, "soc_pct": 82, "evidence_status": "mock"},
                        transport={"type": "lte"},
                        reliability={"network": {"raw_post_attempt_count": 2, "raw_post_success_count": 2, "raw_post_failure_count": 0}},
                        location_belief={
                            "state": "Coarse",
                            "radius_m": 250,
                            "confidence": 0.62,
                            "source": ["cell_lte", "wifi_memory"],
                            "reason": "no_hardware_d1_fixture_estimate",
                        },
                    ),
                )
                state = get_json(base_url, "/api/state")
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        d1 = state["devices"][0]["d1_link"]
        self.assertEqual(d1["demo"], "D1")
        self.assertEqual(d1["status"], "estimate_visible")
        self.assertTrue(d1["location_estimate"]["available"])
        self.assertEqual(d1["location_estimate"]["state"], "Coarse")
        self.assertEqual(d1["location_estimate"]["accuracy_claim"], "none")
        self.assertEqual(d1["map_surface"]["mode"], "estimate_without_coordinate")
        self.assertTrue(d1["map_surface"]["visible"])
        self.assertEqual(d1["upload_freshness"]["last_location_event_type"], "location_observation")
        self.assertIsInstance(d1["upload_freshness"]["freshness_s"], int)
        self.assertEqual(d1["uplink_metrics"]["basis"], "device_raw_post_counters")
        self.assertEqual(d1["uplink_metrics"]["location_event_count"], 2)
        self.assertEqual(d1["uplink_metrics"]["raw_post_attempt_count"], 2)
        self.assertEqual(d1["uplink_metrics"]["raw_post_success_count"], 2)
        self.assertEqual(d1["uplink_metrics"]["raw_post_failure_count"], 0)
        self.assertEqual(d1["uplink_metrics"]["raw_post_success_rate"], 1.0)
        self.assertEqual(d1["power_curve"]["sample_count"], 3)
        self.assertEqual(d1["power_curve"]["delta_battery_mv"], -30)
        self.assertEqual(d1["power_curve"]["delta_soc_pct"], -8.0)
        self.assertEqual(d1["power_curve"]["latest"]["battery_mv"], 3960)
        self.assertEqual(d1["power_curve"]["battery_life_claim"], "none")
        self.assertTrue(d1["evidence"]["components"]["gnss"]["seen"])
        self.assertTrue(d1["evidence"]["components"]["cell_lte"]["seen"])
        self.assertTrue(d1["evidence"]["components"]["imu"]["seen"])
        self.assertTrue(d1["evidence"]["components"]["power"]["seen"])
        self.assertIn("location_accuracy_not_claimed", d1["non_claims"])

    def test_state_api_and_product_demo_route_include_latest_demo_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report_root = tmp_path / "product_demo"
            report_dir = report_root / "kr008-unit"
            report_dir.mkdir(parents=True)
            (report_dir / "product_demo_report.json").write_text(
                json.dumps(
                    {
                        "demo": {
                            "candidate": "KR-008 / DEMO-008 Product Demo Closed Loop",
                            "mode": "offline_evidence_composition",
                            "product_ready": False,
                        },
                        "source": {
                            "test_run_id": "lte011-unit",
                            "safety_session_id": "demo-unit",
                            "evidence_mode": "composite_existing_evidence",
                            "dataset_samples": 1,
                        },
                        "result": {
                            "status": "warn",
                            "ready_for_kr008_release": False,
                            "warnings": ["web_console_product_demo_review_pending"],
                            "errors": [],
                            "why_not_release_ready": ["web_console_product_demo_review_pending"],
                        },
                        "location": {
                            "state": "Unknown",
                            "gnss_fix": False,
                            "gnss_state": "no_fix",
                            "belief_reason": "cell_observation_without_position_fix",
                        },
                        "flow": {
                            "report_export": {"status": "pass", "summary": "report exported"},
                            "web_console_replay_review": {"status": "not_run", "summary": "pending"},
                        },
                        "evidence_summary": {
                            "flow_status_counts": {"pass": 7, "not_run": 1},
                            "feature_groups": ["gnss", "cell", "lte"],
                            "raw_frame_refs": 3,
                            "derived_event_refs": 2,
                            "training_readiness": {"model_training_ready": False, "reason": "not_ready"},
                            "release_gate_usage": {"can_support_release_review": True},
                        },
                        "paths": {
                            "product_demo_report_json": "reports/product_demo/kr008-unit/product_demo_report.json",
                            "product_demo_report_markdown": "reports/product_demo/kr008-unit/product_demo_report.md",
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            store = message_hub.MessageHubStore(tmp_path / "hub.db")
            server = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                message_hub.make_handler(store, product_demo_root=report_root),
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                state = get_json(base_url, "/api/state")
                latest = get_json(base_url, "/api/v1/product-demo/latest")
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertEqual(state["product_demo"]["status"], "warn")
        self.assertEqual(state["product_demo"]["candidate"], "KR-008 / DEMO-008 Product Demo Closed Loop")
        self.assertEqual(state["product_demo"]["flow"]["web_console_replay_review"]["status"], "not_run")
        self.assertFalse(state["product_demo"]["ready_for_kr008_release"])
        self.assertEqual(latest["product_demo"]["test_run_id"], "lte011-unit")
        self.assertEqual(latest["product_demo"]["evidence_mode"], "composite_existing_evidence")

    def test_state_api_and_training_experiment_route_include_latest_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report_root = tmp_path / "training_experiments"
            report_dir = report_root / "unit-experiment"
            report_dir.mkdir(parents=True)
            (report_dir / "training_experiment_plan.json").write_text(
                json.dumps(
                    {
                        "schema_version": "egolink.training_experiment_plan.v0.1",
                        "experiment_id": "unit-experiment",
                        "created_at": "2026-07-05T06:30:00+00:00",
                        "status": "blocked_dataset_not_ready",
                        "reason": "candidate_store_missing",
                        "dataset": {
                            "dataset_id": "unit-dataset",
                            "manifest_status": "not_ready",
                            "manifest_reason": "candidate_store_missing",
                            "records_total": 0,
                            "eligible_records": 0,
                            "record_sample": [],
                        },
                        "model_track": {
                            "track": "motionnet",
                            "candidate_model": "motionnet-v0.1-planned",
                            "baseline_model": "m0_rule_router",
                        },
                        "runner": {
                            "integration": "not_integrated",
                            "ready_for_handoff": False,
                            "next_command": "Complete review gates.",
                        },
                        "metrics_plan": {
                            "classification": {"accuracy": "planned_not_measured"},
                            "operations": {"latency_ms": "planned_not_measured"},
                        },
                        "gates": {"dataset_ready": False, "baseline_comparison": "planned_not_run"},
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            store = message_hub.MessageHubStore(tmp_path / "hub.db")
            server = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                message_hub.make_handler(store, training_experiment_root=report_root),
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                state = get_json(base_url, "/api/state")
                latest = get_json(base_url, "/api/v1/training-experiments/latest")
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertEqual(state["training_experiment"]["status"], "blocked_dataset_not_ready")
        self.assertEqual(state["training_experiment"]["reason"], "candidate_store_missing")
        self.assertEqual(latest["training_experiment"]["experiment_id"], "unit-experiment")
        self.assertEqual(latest["training_experiment"]["dataset"]["eligible_records"], 0)
        self.assertEqual(
            latest["training_experiment"]["metrics_plan"]["classification"]["accuracy"],
            "planned_not_measured",
        )

    def test_state_api_and_training_run_route_include_latest_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report_root = tmp_path / "training_runs"
            report_dir = report_root / "unit-preflight"
            report_dir.mkdir(parents=True)
            (report_dir / "training_run_preflight.json").write_text(
                json.dumps(
                    {
                        "schema_version": "egolink.training_run_preflight.v0.1",
                        "run_id": "unit-preflight",
                        "created_at": "2026-07-05T11:30:00+00:00",
                        "status": "ready_for_training_runner",
                        "reason": "bounded_dataset_and_experiment_handoff_ready",
                        "experiment": {
                            "experiment_id": "unit-experiment",
                            "status": "ready_for_runner",
                            "model_track": {"track": "motionnet"},
                        },
                        "dataset": {
                            "dataset_id": "unit-dataset",
                            "status": "ready_for_training_handoff",
                            "records_total": 1,
                            "eligible_records": 1,
                            "reviewed_training_candidate_records": 1,
                            "experiment_records_total": 1,
                            "split_counts": {"train": 1},
                            "label_counts": {"safe": 1},
                            "source_status_counts": {"synthetic_generated": 1},
                            "synthetic_records": 1,
                            "synthetic_allowed_for_dry_run": True,
                            "record_sample": [
                                {
                                    "record_id": "cand-unit",
                                    "session_id": "session-unit",
                                    "label": "safe",
                                    "split_name": "train",
                                    "source_status": "synthetic_generated",
                                    "source_manifest_hash": "abc123",
                                }
                            ],
                        },
                        "checks": {
                            "experiment_ready": True,
                            "dataset_ready": True,
                            "has_eligible_records": True,
                            "required_record_fields": "pass",
                            "synthetic_record_policy": "acknowledged",
                        },
                        "runner": {
                            "integration": "local_preflight_only",
                            "ready_for_training_runner": True,
                            "next_step": "Connect a runner.",
                        },
                        "metrics_plan": {
                            "measured": {
                                "classification": "not_run",
                                "operations": "not_run",
                                "power": "not_run",
                            }
                        },
                        "gates": {
                            "preflight_ready": True,
                            "model_training": "not_run",
                            "model_artifact": "not_produced",
                            "training_server": "not_integrated",
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            store = message_hub.MessageHubStore(tmp_path / "hub.db")
            server = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                message_hub.make_handler(store, training_run_root=report_root),
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                state = get_json(base_url, "/api/state")
                latest = get_json(base_url, "/api/v1/training-runs/latest")
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertEqual(state["training_run_preflight"]["status"], "ready_for_training_runner")
        self.assertEqual(state["training_run_preflight"]["dataset"]["synthetic_records"], 1)
        self.assertEqual(latest["training_run_preflight"]["run_id"], "unit-preflight")
        self.assertTrue(latest["training_run_preflight"]["runner"]["ready_for_training_runner"])
        self.assertEqual(latest["training_run_preflight"]["metrics_plan"]["measured"]["classification"], "not_run")

    def test_state_api_and_training_feature_route_include_latest_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report_root = tmp_path / "training_features"
            report_dir = report_root / "unit-features"
            report_dir.mkdir(parents=True)
            (report_dir / "training_feature_manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": "egolink.training_feature_manifest.v0.1",
                        "feature_set_id": "unit-features",
                        "generated_at": "2026-07-05T12:00:00+00:00",
                        "status": "ready_for_synthetic_feature_dry_run",
                        "reason": "bounded_synthetic_feature_rows_ready_for_runner_dry_run",
                        "dataset": {
                            "dataset_id": "unit-dataset",
                            "status": "ready_for_training_handoff",
                            "records_total": 1,
                            "eligible_records": 1,
                            "reviewed_training_candidate_records": 1,
                            "split_counts": {"train": 1},
                            "label_counts": {"safe": 1},
                            "source_status_counts": {"synthetic_generated": 1},
                            "synthetic_records": 1,
                            "synthetic_allowed_for_dry_run": True,
                        },
                        "preflight": {
                            "run_id": "unit-preflight",
                            "status": "ready_for_training_runner",
                            "dataset_id": "unit-dataset",
                            "runner_ready": True,
                            "metrics_measured": {
                                "classification": "not_run",
                                "operations": "not_run",
                                "power": "not_run",
                            },
                        },
                        "feature_rows": {
                            "row_schema_version": "egolink.training_feature_row.v0.1",
                            "row_count": 1,
                            "rows_ref": "training_feature_rows.jsonl",
                            "feature_groups": ["imu_motion"],
                            "feature_scope": "manifest_summary_features",
                            "target_separated_from_features": True,
                        },
                        "checks": {
                            "dataset_ready": True,
                            "preflight_ready": True,
                            "source_match": True,
                            "has_records": True,
                            "required_record_fields": "pass",
                            "synthetic_record_policy": "acknowledged",
                            "label_leakage_guard": "target_separated_from_features",
                        },
                        "gates": {
                            "feature_export": "pass",
                            "model_training": "not_run",
                            "model_artifact": "not_produced",
                            "training_server": "not_integrated",
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            store = message_hub.MessageHubStore(tmp_path / "hub.db")
            server = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                message_hub.make_handler(store, training_feature_root=report_root),
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                state = get_json(base_url, "/api/state")
                latest = get_json(base_url, "/api/v1/training-features/latest")
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertEqual(state["training_feature_manifest"]["status"], "ready_for_synthetic_feature_dry_run")
        self.assertEqual(state["training_feature_manifest"]["feature_rows"]["row_count"], 1)
        self.assertEqual(latest["training_feature_manifest"]["feature_set_id"], "unit-features")
        self.assertTrue(latest["training_feature_manifest"]["preflight"]["runner_ready"])
        self.assertEqual(latest["training_feature_manifest"]["checks"]["synthetic_record_policy"], "acknowledged")
        self.assertEqual(latest["training_feature_manifest"]["gates"]["model_artifact"], "not_produced")

    def test_state_api_and_training_runner_dry_run_route_include_latest_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report_root = tmp_path / "training_runner_dry_runs"
            report_dir = report_root / "unit-runner"
            report_dir.mkdir(parents=True)
            (report_dir / "training_runner_dry_run.json").write_text(
                json.dumps(
                    {
                        "schema_version": "egolink.training_runner_dry_run.v0.1",
                        "run_id": "unit-runner",
                        "created_at": "2026-07-05T12:45:00+00:00",
                        "status": "synthetic_runner_dry_run_complete",
                        "reason": "runner_input_contract_validated_with_synthetic_dry_run_rows",
                        "feature_manifest": {
                            "feature_set_id": "unit-features",
                            "status": "ready_for_synthetic_feature_dry_run",
                            "feature_scope": "manifest_summary_features",
                            "target_separated_from_features": True,
                        },
                        "dataset": {
                            "dataset_id": "unit-dataset",
                            "status": "ready_for_training_handoff",
                            "eligible_records": 1,
                            "synthetic_records": 1,
                        },
                        "preflight": {
                            "run_id": "unit-preflight",
                            "status": "ready_for_training_runner",
                            "runner_ready": True,
                            "metrics_measured": {
                                "classification": "not_run",
                                "operations": "not_run",
                                "power": "not_run",
                            },
                        },
                        "feature_rows": {
                            "expected_row_count": 1,
                            "actual_row_count": 1,
                            "row_count_matches": True,
                            "feature_set_mismatch_count": 0,
                            "split_counts": {"train": 1},
                            "label_counts": {"safe": 1},
                            "source_status_counts": {"synthetic_generated": 1},
                            "feature_group_counts": {"imu_motion": 1},
                            "synthetic_rows": 1,
                            "synthetic_allowed_for_dry_run": True,
                        },
                        "checks": {
                            "feature_manifest_ready": True,
                            "feature_rows_readable": True,
                            "row_count_matches": True,
                            "required_row_fields": "pass",
                            "missing_row_fields": {},
                            "target_leakage_guard": "pass",
                            "target_leakage_violations": {},
                            "synthetic_row_policy": "acknowledged",
                            "manifest_feature_export_gate": "pass",
                        },
                        "runner": {
                            "integration": "local_runner_dry_run",
                            "ready_for_real_runner": False,
                            "dry_run_only": True,
                            "next_step": "Dry-run only.",
                        },
                        "metrics_plan": {
                            "measured": {
                                "classification": "not_run",
                                "operations": "not_run",
                                "power": "not_run",
                            },
                            "dry_run_summary": {
                                "labels": {"safe": 1},
                                "splits": {"train": 1},
                                "feature_groups": {"imu_motion": 1},
                            },
                        },
                        "gates": {
                            "runner_input": "pass",
                            "model_training": "not_run",
                            "model_artifact": "not_produced",
                            "training_server": "not_integrated",
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            store = message_hub.MessageHubStore(tmp_path / "hub.db")
            server = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                message_hub.make_handler(store, training_runner_dry_run_root=report_root),
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                state = get_json(base_url, "/api/state")
                latest = get_json(base_url, "/api/v1/training-runner-dry-runs/latest")
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertEqual(state["training_runner_dry_run"]["status"], "synthetic_runner_dry_run_complete")
        self.assertEqual(state["training_runner_dry_run"]["feature_rows"]["actual_row_count"], 1)
        self.assertEqual(latest["training_runner_dry_run"]["run_id"], "unit-runner")
        self.assertTrue(latest["training_runner_dry_run"]["runner"]["dry_run_only"])
        self.assertEqual(latest["training_runner_dry_run"]["checks"]["synthetic_row_policy"], "acknowledged")
        self.assertEqual(latest["training_runner_dry_run"]["gates"]["model_artifact"], "not_produced")

    def test_state_api_and_training_baseline_eval_route_include_latest_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report_root = tmp_path / "training_baseline_evals"
            report_dir = report_root / "unit-eval"
            report_dir.mkdir(parents=True)
            (report_dir / "training_baseline_eval.json").write_text(
                json.dumps(
                    {
                        "schema_version": "egolink.training_baseline_eval.v0.1",
                        "eval_id": "unit-eval",
                        "created_at": "2026-07-06T00:30:00+00:00",
                        "status": "synthetic_baseline_eval_complete",
                        "reason": "synthetic_rows_evaluated_for_runner_integration_only",
                        "feature_manifest": {
                            "feature_set_id": "unit-features",
                            "status": "ready_for_synthetic_feature_dry_run",
                            "feature_scope": "manifest_summary_features",
                            "target_separated_from_features": True,
                        },
                        "runner_dry_run": {
                            "run_id": "unit-runner",
                            "status": "synthetic_runner_dry_run_complete",
                            "runner_input_gate": "pass",
                            "dry_run_only": True,
                        },
                        "dataset": {
                            "dataset_id": "unit-dataset",
                            "status": "ready_for_training_handoff",
                            "eligible_records": 1,
                            "synthetic_records": 1,
                        },
                        "feature_rows": {
                            "expected_row_count": 1,
                            "actual_row_count": 1,
                            "row_count_matches": True,
                            "split_counts": {"test": 1},
                            "label_counts": {"needs_help": 1},
                            "risk_type_counts": {"uncertain": 1},
                            "candidate_type_counts": {"uncertain": 1},
                            "source_status_counts": {"synthetic_generated": 1},
                            "synthetic_rows": 1,
                            "synthetic_allowed_for_eval": True,
                        },
                        "checks": {
                            "feature_manifest_ready": True,
                            "runner_dry_run_ready": True,
                            "feature_rows_readable": True,
                            "row_count_matches": True,
                            "required_row_fields": "pass",
                            "missing_row_fields": {},
                            "target_leakage_guard": "pass",
                            "target_leakage_violations": {},
                            "synthetic_row_policy": "acknowledged",
                        },
                        "metrics": {
                            "scope": "synthetic_integration_only",
                            "measured_from_rows": True,
                            "classification": {
                                "baselines": [
                                    {
                                        "name": "candidate_type_risk_baseline",
                                        "overall": {"total": 1, "correct": 1, "accuracy": 1.0},
                                        "private_case_rows": [{"row_id": "secret"}],
                                    }
                                ],
                                "product_performance_claim": False,
                                "release_metric": False,
                            },
                            "operations": "not_run",
                            "footprint": "not_run",
                            "power": "not_run",
                        },
                        "gates": {
                            "baseline_evaluation": "pass",
                            "model_training": "not_run",
                            "model_artifact": "not_produced",
                            "model_card": "not_produced",
                            "training_server": "not_integrated",
                            "model_registry": "not_integrated",
                            "device_deployment": "not_started",
                            "release_claim": "not_allowed",
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            store = message_hub.MessageHubStore(tmp_path / "hub.db")
            server = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                message_hub.make_handler(store, training_baseline_eval_root=report_root),
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                state = get_json(base_url, "/api/state")
                latest = get_json(base_url, "/api/v1/training-baseline-evals/latest")
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertEqual(state["training_baseline_eval"]["status"], "synthetic_baseline_eval_complete")
        self.assertEqual(state["training_baseline_eval"]["feature_rows"]["actual_row_count"], 1)
        self.assertEqual(latest["training_baseline_eval"]["eval_id"], "unit-eval")
        self.assertEqual(latest["training_baseline_eval"]["metrics"]["scope"], "synthetic_integration_only")
        self.assertEqual(latest["training_baseline_eval"]["metrics"]["classification"]["baselines"][0]["overall"]["accuracy"], 1.0)
        self.assertNotIn("private_case_rows", json.dumps(latest))
        self.assertEqual(latest["training_baseline_eval"]["gates"]["model_artifact"], "not_produced")
        self.assertEqual(latest["training_baseline_eval"]["gates"]["release_claim"], "not_allowed")

    def test_state_api_and_training_handoff_bundle_route_include_latest_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report_root = tmp_path / "training_handoffs"
            report_dir = report_root / "unit-handoff"
            report_dir.mkdir(parents=True)
            (report_dir / "training_handoff_bundle.json").write_text(
                json.dumps(
                    {
                        "schema_version": "egolink.training_handoff_bundle.v0.1",
                        "handoff_id": "unit-handoff",
                        "created_at": "2026-07-06T01:30:00+00:00",
                        "status": "synthetic_handoff_dry_run_only",
                        "reason": "synthetic_inputs_bound_for_dry_run_only",
                        "source_refs": {
                            "training_feature_rows": {
                                "ref": "reports/training_features/unit/training_feature_rows.jsonl",
                                "sha256": "abc123",
                                "bytes": 42,
                                "content_copied": False,
                                "private_row": {"target": "secret"},
                            }
                        },
                        "dataset": {
                            "dataset_id": "unit-dataset",
                            "status": "ready_for_training_handoff",
                            "eligible_records": 1,
                            "split_counts": {"test": 1},
                        },
                        "training_run_preflight": {
                            "run_id": "unit-preflight",
                            "status": "ready_for_training_runner",
                            "runner_ready": True,
                        },
                        "feature_manifest": {
                            "feature_set_id": "unit-features",
                            "status": "ready_for_synthetic_feature_dry_run",
                            "row_count": 1,
                            "feature_scope": "manifest_summary_features",
                            "target_separated_from_features": True,
                        },
                        "feature_rows": {
                            "row_count": 1,
                            "content_copied": False,
                            "raw_rows_exposed": False,
                            "rows": [{"target": {"label": "secret"}, "features": {"candidate": "secret"}}],
                        },
                        "runner_dry_run": {
                            "run_id": "unit-runner",
                            "status": "synthetic_runner_dry_run_complete",
                            "runner_input_gate": "pass",
                        },
                        "baseline_eval": {
                            "eval_id": "unit-eval",
                            "status": "synthetic_baseline_eval_complete",
                            "metric_scope": "synthetic_integration_only",
                            "product_performance_claim": False,
                        },
                        "checks": {
                            "source_ids_match": True,
                            "feature_row_count_matches": True,
                            "synthetic_input_seen": True,
                            "synthetic_policy": "acknowledged",
                        },
                        "training_server": {
                            "integration": "not_configured",
                            "endpoint": "https://private.example.invalid/train",
                            "bundle_ready_for_future_runner": False,
                            "dry_run_only": True,
                        },
                        "gates": {
                            "training_handoff": "dry_run_only",
                            "model_training": "not_run",
                            "model_artifact": "not_produced",
                            "model_card": "not_produced",
                            "training_server": "not_integrated",
                            "model_registry": "not_integrated",
                            "device_deployment": "not_started",
                            "release_claim": "not_allowed",
                        },
                        "next_step": "repeat_with_reviewed_real_rows",
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            store = message_hub.MessageHubStore(tmp_path / "hub.db")
            server = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                message_hub.make_handler(store, training_handoff_root=report_root),
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                state = get_json(base_url, "/api/state")
                latest = get_json(base_url, "/api/v1/training-handoffs/latest")
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertEqual(state["training_handoff_bundle"]["status"], "synthetic_handoff_dry_run_only")
        self.assertEqual(state["training_handoff_bundle"]["feature_rows"]["row_count"], 1)
        self.assertFalse(state["training_handoff_bundle"]["feature_rows"]["content_copied"])
        self.assertFalse(state["training_handoff_bundle"]["feature_rows"]["raw_rows_exposed"])
        self.assertEqual(latest["training_handoff_bundle"]["handoff_id"], "unit-handoff")
        self.assertEqual(latest["training_handoff_bundle"]["training_server"]["integration"], "not_configured")
        self.assertTrue(latest["training_handoff_bundle"]["training_server"]["dry_run_only"])
        self.assertEqual(latest["training_handoff_bundle"]["gates"]["model_artifact"], "not_produced")
        payload_text = json.dumps(latest, sort_keys=True)
        self.assertIn("sha256", payload_text)
        self.assertNotIn("private.example", payload_text)
        self.assertNotIn("private_row", payload_text)
        self.assertNotIn('"target"', payload_text)
        self.assertNotIn('"features"', payload_text)

    def test_state_api_and_training_job_plan_route_include_latest_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report_root = tmp_path / "training_jobs"
            report_dir = report_root / "unit-job"
            report_dir.mkdir(parents=True)
            (report_dir / "training_job_plan.json").write_text(
                json.dumps(
                    {
                        "schema_version": "egolink.training_job_plan.v0.1",
                        "job_id": "unit-job",
                        "created_at": "2026-07-06T02:40:00+00:00",
                        "status": "ready_for_runner_queue",
                        "reason": "reviewed_handoff_ready_for_future_runner_queue",
                        "source_handoff": {
                            "handoff_id": "unit-handoff",
                            "status": "ready_for_training_server_handoff",
                            "ref": {
                                "ref": "reports/training_handoffs/unit/training_handoff_bundle.json",
                                "sha256": "def456",
                                "bytes": 128,
                                "content_copied": False,
                                "private_row": {"target": "secret"},
                            },
                        },
                        "dataset": {
                            "dataset_id": "unit-dataset",
                            "status": "ready_for_training_handoff",
                            "eligible_records": 1,
                        },
                        "feature_input": {
                            "feature_set_id": "unit-features",
                            "feature_manifest_status": "ready_for_feature_runner",
                            "feature_scope": "manifest_summary_features",
                            "row_count": 1,
                            "row_contents_copied": False,
                            "raw_rows_exposed": False,
                            "rows": [{"target": "secret", "features": {"x": 1}}],
                        },
                        "model_plan": {
                            "model_track": "motionnet",
                            "candidate_model": "motionnet_v0_candidate",
                            "baseline_model": "rule_router_baseline",
                            "task_type": "classification",
                            "baseline_eval_id": "unit-eval",
                            "baseline_metric_scope": "reviewed_engineering_dataset",
                            "product_performance_claim": False,
                        },
                        "runner_plan": {
                            "runner_profile": "local_runner_planned",
                            "queue_state": "plan_only",
                            "training_server_integration": "not_configured",
                            "training_server_endpoint": "https://private.example.invalid/train",
                            "bundle_ready_for_future_runner": True,
                            "dry_run_only": False,
                            "uses_feature_row_refs_only": True,
                        },
                        "metrics_plan": {
                            "classification": {"accuracy": "planned_not_measured"},
                            "operations": {"latency_ms": "planned_not_measured"},
                            "power": {"energy_per_inference": "planned_not_measured"},
                        },
                        "checks": {
                            "handoff_ready": True,
                            "handoff_gate": "pass",
                            "synthetic_input_seen": False,
                            "synthetic_policy": "not_present",
                            "row_contents_copied": False,
                            "private_endpoint_exposed": False,
                        },
                        "gates": {
                            "training_job": "pass",
                            "model_training": "not_run",
                            "model_artifact": "not_produced",
                            "model_card": "not_produced",
                            "training_server": "not_integrated",
                            "model_registry": "not_integrated",
                            "device_deployment": "not_started",
                            "release_claim": "not_allowed",
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            store = message_hub.MessageHubStore(tmp_path / "hub.db")
            server = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                message_hub.make_handler(store, training_job_root=report_root),
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                state = get_json(base_url, "/api/state")
                latest = get_json(base_url, "/api/v1/training-jobs/latest")
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertEqual(state["training_job_plan"]["status"], "ready_for_runner_queue")
        self.assertEqual(state["training_job_plan"]["feature_input"]["row_count"], 1)
        self.assertFalse(state["training_job_plan"]["feature_input"]["row_contents_copied"])
        self.assertFalse(state["training_job_plan"]["feature_input"]["raw_rows_exposed"])
        self.assertEqual(latest["training_job_plan"]["job_id"], "unit-job")
        self.assertEqual(latest["training_job_plan"]["runner_plan"]["training_server_integration"], "not_configured")
        self.assertIsNone(latest["training_job_plan"]["runner_plan"]["training_server_endpoint"])
        self.assertEqual(latest["training_job_plan"]["gates"]["model_training"], "not_run")
        payload_text = json.dumps(latest, sort_keys=True)
        self.assertIn("sha256", payload_text)
        self.assertNotIn("private.example", payload_text)
        self.assertNotIn("private_row", payload_text)
        self.assertNotIn('"target"', payload_text)
        self.assertNotIn('"features"', payload_text)

    def test_state_api_and_synthetic_training_chain_route_include_latest_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report_root = tmp_path / "synthetic_training_chain"
            report_dir = report_root / "unit-chain"
            report_dir.mkdir(parents=True)
            (report_dir / "synthetic_training_chain.json").write_text(
                json.dumps(
                    {
                        "schema_version": "egolink.synthetic_training_chain.v0.1",
                        "run_id": "unit-chain",
                        "generated_at": "2026-07-06T06:30:00+00:00",
                        "serves_demo": "D5",
                        "status": "synthetic_training_chain_complete",
                        "synthetic_only": True,
                        "scenarios": ["normal_walk", "no_response"],
                        "counts": {
                            "recordings": 2,
                            "reviewed_records": 2,
                            "review_failures": 0,
                            "feature_rows": 2,
                        },
                        "components": {
                            "synthetic_scenarios": {
                                "status": "synthetic_ready_for_runner",
                                "recordings": 2,
                                "reviewed_records": 2,
                                "failed_reviews": 0,
                                "seed": 42,
                                "report": {"ref": "synthetic_scenario_run.json", "content_copied": False},
                                "candidate_db": "candidate_store.sqlite3",
                            },
                            "data_flywheel": {
                                "initial": {
                                    "run_id": "unit-initial",
                                    "status": "needs_review",
                                    "candidate_records": 2,
                                    "pending_review": 2,
                                    "dataset_status": "not_ready",
                                },
                                "reviewed": {
                                    "run_id": "unit-reviewed",
                                    "status": "ready_for_training_handoff",
                                    "eligible_records": 2,
                                    "experiment_status": "ready_for_runner",
                                    "runner_ready": True,
                                },
                            },
                            "training_chain": {
                                "status": "synthetic_runner_queue_dry_run_only",
                                "reason": "synthetic_handoff_bound_for_runner_queue_dry_run_only",
                                "components": {
                                    "preflight": {
                                        "status": "ready_for_training_runner",
                                        "run_id": "unit-preflight",
                                    },
                                    "feature_manifest": {
                                        "status": "ready_for_synthetic_feature_dry_run",
                                        "feature_set_id": "unit-features",
                                        "row_count": 2,
                                        "rows": [{"features": {"x": "secret"}, "target": {"label": "secret"}}],
                                    },
                                    "runner_dry_run": {
                                        "status": "synthetic_runner_dry_run_complete",
                                        "row_count": 2,
                                    },
                                    "baseline_eval": {
                                        "status": "synthetic_baseline_eval_complete",
                                        "metric_scope": "synthetic_integration_only",
                                        "product_performance_claim": False,
                                    },
                                    "handoff_bundle": {
                                        "status": "synthetic_handoff_dry_run_only",
                                        "training_server": "not_configured",
                                        "dry_run_only": True,
                                        "private_endpoint": "https://private.example.invalid/train",
                                    },
                                    "job_plan": {
                                        "status": "synthetic_runner_queue_dry_run_only",
                                        "job_id": "unit-job",
                                        "queue_state": "plan_only",
                                        "runner_profile": "ci_dry_run",
                                        "dry_run_only": True,
                                    },
                                },
                                "next_step": "Repeat with reviewed real records.",
                            },
                        },
                        "scope": {
                            "hardware_contacted": False,
                            "message_hub_contacted": False,
                            "model_training_started": False,
                            "model_artifact_written": False,
                            "release_claim_allowed": False,
                        },
                        "next_step": "Repeat with reviewed real records.",
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (report_dir / "synthetic_training_chain.md").write_text("# Synthetic chain\n", encoding="utf-8")
            store = message_hub.MessageHubStore(tmp_path / "hub.db")
            server = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                message_hub.make_handler(store, synthetic_training_chain_root=report_root),
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                state = get_json(base_url, "/api/state")
                latest = get_json(base_url, "/api/v1/synthetic-training-chains/latest")
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertEqual(state["synthetic_training_chain"]["status"], "synthetic_training_chain_complete")
        self.assertEqual(state["synthetic_training_chain"]["counts"]["feature_rows"], 2)
        self.assertEqual(
            state["synthetic_training_chain"]["components"]["data_flywheel"]["reviewed"]["status"],
            "ready_for_training_handoff",
        )
        chain = latest["synthetic_training_chain"]
        self.assertEqual(chain["run_id"], "unit-chain")
        self.assertEqual(chain["components"]["training_chain"]["job_plan"]["status"], "synthetic_runner_queue_dry_run_only")
        self.assertEqual(chain["components"]["training_chain"]["job_plan"]["runner_profile"], "ci_dry_run")
        self.assertFalse(chain["scope"]["hardware_contacted"])
        self.assertFalse(chain["scope"]["model_training_started"])
        self.assertFalse(chain["scope"]["release_claim_allowed"])
        self.assertEqual(chain["markdown_path"], str(report_dir / "synthetic_training_chain.md"))
        payload_text = json.dumps(latest, sort_keys=True)
        self.assertNotIn("candidate_store.sqlite3", payload_text)
        self.assertNotIn("private.example", payload_text)
        self.assertNotIn('"target"', payload_text)
        self.assertNotIn('"features"', payload_text)
        self.assertNotIn("raw_payload", payload_text)

    def test_state_api_and_d1_training_readiness_route_include_latest_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report_root = tmp_path / "d1_training_readiness"
            report_dir = report_root / "unit-d1-readiness"
            report_dir.mkdir(parents=True)
            (report_dir / "d1_training_readiness.json").write_text(
                json.dumps(
                    {
                        "schema_version": "egolink.d1_training_readiness.v0.1",
                        "run_id": "unit-d1-readiness",
                        "generated_at": "2026-07-06T11:30:00+00:00",
                        "serves_demo": "D5",
                        "status": "ready_for_labeling_review",
                        "reason": "field_observation_can_enter_human_review_but_not_training",
                        "source_observation": {
                            "run_id": "field-private",
                            "source": "field_observation_report",
                            "status": "completed",
                            "result": "PASS",
                            "device_id": "ego-link-r1-connectivity-001",
                            "sample_count": 5,
                            "successful_sample_count": 5,
                            "latest_seq": 52,
                            "max_freshness_s": 62.0,
                            "last_location_upload_at": "2026-07-06T11:20:18+00:00",
                            "report_path": "reports/d1_field_observation/field/d1_field_observation_report.json",
                            "status_path": "reports/d1_field_observation/field/d1_field_observation_status.json",
                            "samples_path": "reports/d1_field_observation/field/d1_field_samples.jsonl",
                            "samples_jsonl_read": False,
                            "lat": 31.123456,
                            "lon": 121.654321,
                        },
                        "evidence_coverage": {
                            "capture": {
                                "sample_count": 5,
                                "successful_sample_count": 5,
                                "fetch_error_count": 0,
                                "ready_for_review": True,
                            },
                            "transport": {
                                "raw_post_success_delta": 2,
                                "raw_post_failure_delta": 0,
                                "lte_registration_seen": True,
                                "pdp_active_seen": True,
                            },
                            "location": {
                                "coordinate_sample_count": 5,
                                "location_event_count_delta": 0,
                                "map_modes": ["memory_coordinate"],
                                "gnss_states": ["unknown"],
                                "gnss_fix_seen": False,
                                "coordinate_values_copied": False,
                                "accuracy_claimed": False,
                                "coordinates": {"lat": 31.123456, "lon": 121.654321},
                            },
                            "sensors": {
                                "imu_evidence_statuses": ["mock"],
                                "power_evidence_statuses": ["measured"],
                                "power_measured_seen": True,
                                "real_imu_seen": False,
                            },
                        },
                        "readiness": {
                            "ready_for_labeling_review": True,
                            "ready_for_training_handoff": False,
                            "training_allowed": False,
                            "consent_status": "not_reviewed",
                            "privacy_review": "required",
                            "label_review_state": "missing",
                            "split_leakage_checked": False,
                            "quality_gaps": ["gnss_fix_not_seen"],
                            "blockers": [
                                "privacy_review_required",
                                "training_consent_not_granted",
                                "operator_or_user_labels_missing",
                                "split_plan_missing",
                            ],
                        },
                        "gates": {
                            "field_observation": {
                                "status": "pass",
                                "reason": "field_observation_summary_has_successful_samples",
                                "evidence": {"sample_count": 5},
                            },
                            "transport": {"status": "pass", "reason": "raw_post_failures_absent"},
                            "privacy": {"status": "blocked", "reason": "privacy_review_required_before_training_use"},
                            "labels": {"status": "blocked", "reason": "operator_or_user_labels_missing"},
                            "split_leakage": {"status": "blocked", "reason": "split_plan_missing_for_real_field_data"},
                            "release_claim": {"status": "not_allowed", "reason": "readiness_report_is_not_product_metric"},
                        },
                        "scope": {
                            "sample_jsonl_read": False,
                            "message_hub_contacted": False,
                            "hardware_contacted": False,
                            "training_samples_written": False,
                            "model_training_started": False,
                            "model_artifact_written": False,
                            "location_accuracy_claimed": False,
                            "battery_life_claimed": False,
                            "release_claim_allowed": False,
                        },
                        "next_step": "Attach labels and privacy review.",
                        "raw_payload": {"secret": "do-not-copy"},
                        "features": {"private": True},
                        "target": {"label": "secret"},
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (report_dir / "d1_training_readiness.md").write_text("# D1 readiness\n", encoding="utf-8")
            store = message_hub.MessageHubStore(tmp_path / "hub.db")
            server = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                message_hub.make_handler(store, d1_training_readiness_root=report_root),
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                state = get_json(base_url, "/api/state")
                latest = get_json(base_url, "/api/v1/d1-training-readiness/latest")
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertEqual(state["d1_training_readiness"]["status"], "ready_for_labeling_review")
        self.assertTrue(state["d1_training_readiness"]["readiness"]["ready_for_labeling_review"])
        self.assertFalse(state["d1_training_readiness"]["readiness"]["ready_for_training_handoff"])
        self.assertFalse(state["d1_training_readiness"]["readiness"]["training_allowed"])
        self.assertEqual(latest["d1_training_readiness"]["source_observation"]["sample_count"], 5)
        self.assertEqual(latest["d1_training_readiness"]["evidence_coverage"]["transport"]["raw_post_success_delta"], 2)
        self.assertFalse(latest["d1_training_readiness"]["scope"]["sample_jsonl_read"])
        self.assertEqual(latest["d1_training_readiness"]["markdown_path"], str(report_dir / "d1_training_readiness.md"))
        payload_text = json.dumps(latest, sort_keys=True)
        self.assertNotIn("31.123456", payload_text)
        self.assertNotIn("121.654321", payload_text)
        self.assertNotIn("raw_payload", payload_text)
        self.assertNotIn("d1_field_samples.jsonl", payload_text)
        self.assertNotIn('"features"', payload_text)
        self.assertNotIn('"target"', payload_text)

    def test_state_api_and_d1_labeling_intake_route_include_latest_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report_root = tmp_path / "d1_labeling_intake"
            report_dir = report_root / "unit-d1-intake"
            report_dir.mkdir(parents=True)
            (report_dir / "d1_labeling_intake.json").write_text(
                json.dumps(
                    {
                        "schema_version": "egolink.d1_labeling_intake.v0.1",
                        "run_id": "unit-d1-intake",
                        "generated_at": "2026-07-06T11:35:00+00:00",
                        "serves_demo": "D5",
                        "status": "pending_human_review",
                        "reason": "d1_run_waiting_for_label_privacy_consent_and_split_review",
                        "source_readiness": {
                            "run_id": "unit-d1-readiness",
                            "status": "ready_for_labeling_review",
                            "reason": "field_observation_can_enter_human_review_but_not_training",
                            "report_path": "reports/d1_training_readiness/unit/d1_training_readiness.json",
                        },
                        "source_observation": {
                            "run_id": "field-private",
                            "status": "completed",
                            "result": "PASS",
                            "device_id": "ego-link-r1-connectivity-001",
                            "sample_count": 5,
                            "successful_sample_count": 5,
                            "latest_seq": 52,
                            "max_freshness_s": 62.0,
                            "last_location_upload_at": "2026-07-06T11:20:18+00:00",
                            "samples_jsonl_read": False,
                            "coordinate_values_copied": False,
                            "lat": 31.123456,
                            "lon": 121.654321,
                        },
                        "evidence_coverage": {
                            "transport": {
                                "raw_post_success_delta": 2,
                                "raw_post_failure_delta": 0,
                                "lte_registration_seen": True,
                                "pdp_active_seen": True,
                            },
                            "location": {
                                "coordinate_sample_count": 5,
                                "location_event_count_delta": 0,
                                "map_modes": ["memory_coordinate"],
                                "gnss_states": ["unknown"],
                                "gnss_fix_seen": False,
                                "coordinate_values_copied": False,
                                "accuracy_claimed": False,
                                "coordinates": {"lat": 31.123456, "lon": 121.654321},
                            },
                            "sensors": {
                                "imu_evidence_statuses": ["mock"],
                                "power_evidence_statuses": ["measured"],
                                "power_measured_seen": True,
                                "real_imu_seen": False,
                            },
                        },
                        "intake_queue": {
                            "available": True,
                            "pending_items": 1,
                            "next_queue": "training_candidate_store_after_review",
                            "items": [
                                {
                                    "intake_id": "d1-intake-unit",
                                    "source_run_id": "field-private",
                                    "readiness_run_id": "unit-d1-readiness",
                                    "device_id": "ego-link-r1-connectivity-001",
                                    "status": "pending_label_privacy_split",
                                    "training_allowed": False,
                                    "candidate_record_written": False,
                                    "review_state": {
                                        "operator_label": "missing",
                                        "privacy_review": "required",
                                        "training_consent": "not_reviewed",
                                        "split_plan": "missing",
                                        "quality_gaps": ["gnss_fix_not_seen"],
                                    },
                                    "evidence_summary": {
                                        "samples": 5,
                                        "latest_seq": 52,
                                        "raw_post_success_delta": 2,
                                        "raw_post_failure_delta": 0,
                                        "coordinate_sample_count": 5,
                                        "gnss_fix_seen": False,
                                        "imu_evidence_statuses": ["mock"],
                                        "power_evidence_statuses": ["measured"],
                                        "private_coordinates": [31.123456, 121.654321],
                                    },
                                    "requested_actions": ["attach_operator_or_user_label"],
                                    "available_decisions": ["needs_more_capture", "ready_for_candidate_store"],
                                    "raw_payload": {"secret": "do-not-copy"},
                                }
                            ],
                        },
                        "labeling_request": {
                            "taxonomy_version": "d1_location_review.v0.1",
                            "requested_label_groups": ["collection_context", "location_quality"],
                            "free_text_policy": "redacted_or_absent",
                            "exact_coordinates_visible": False,
                            "raw_payload_visible": False,
                        },
                        "review_gates": {
                            "training_readiness": "pass",
                            "operator_label": "blocked",
                            "privacy_review": "blocked",
                            "candidate_store": "not_written",
                            "model_training": "not_run",
                        },
                        "blockers": ["operator_label_missing", "privacy_review_required"],
                        "scope": {
                            "training_readiness_report_read": True,
                            "sample_jsonl_read": False,
                            "hardware_contacted": False,
                            "candidate_db_written": False,
                            "model_training_started": False,
                            "model_artifact_written": False,
                            "exact_coordinates_copied": False,
                            "release_claim_allowed": False,
                        },
                        "next_step": "Collect labels and reviews.",
                        "raw_payload": {"secret": "do-not-copy"},
                        "features": {"private": True},
                        "target": {"label": "secret"},
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (report_dir / "d1_labeling_intake.md").write_text("# D1 intake\n", encoding="utf-8")
            store = message_hub.MessageHubStore(tmp_path / "hub.db")
            server = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                message_hub.make_handler(store, d1_labeling_intake_root=report_root),
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                state = get_json(base_url, "/api/state")
                latest = get_json(base_url, "/api/v1/d1-labeling-intake/latest")
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertEqual(state["d1_labeling_intake"]["status"], "pending_human_review")
        self.assertEqual(state["d1_labeling_intake"]["intake_queue"]["pending_items"], 1)
        self.assertEqual(latest["d1_labeling_intake"]["intake_queue"]["items"][0]["intake_id"], "d1-intake-unit")
        self.assertFalse(latest["d1_labeling_intake"]["scope"]["sample_jsonl_read"])
        self.assertFalse(latest["d1_labeling_intake"]["scope"]["candidate_db_written"])
        self.assertEqual(latest["d1_labeling_intake"]["review_gates"]["candidate_store"], "not_written")
        self.assertEqual(latest["d1_labeling_intake"]["markdown_path"], str(report_dir / "d1_labeling_intake.md"))
        payload_text = json.dumps(latest, sort_keys=True)
        self.assertNotIn("31.123456", payload_text)
        self.assertNotIn("121.654321", payload_text)
        self.assertNotIn("raw_payload", payload_text)
        self.assertNotIn('"features"', payload_text)
        self.assertNotIn('"target"', payload_text)

    def test_state_api_and_endpoint_include_latest_d1_labeling_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report_root = tmp_path / "d1_labeling_queue"
            report_dir = report_root / "unit-queue"
            report_dir.mkdir(parents=True)
            (report_dir / "d1_labeling_queue.json").write_text(
                json.dumps(
                    {
                        "schema_version": "egolink.d1_labeling_queue.v0.1",
                        "run_id": "unit-labeling-queue",
                        "generated_at": "2026-07-06T12:05:00+00:00",
                        "serves_demo": "D5",
                        "status": "pending_human_review",
                        "summary": {
                            "intake_report_count": 1,
                            "pending_item_count": 1,
                            "not_ready_report_count": 0,
                            "training_allowed_count": 0,
                            "candidate_record_written_count": 0,
                        },
                        "queue": {
                            "next_queue": "training_candidate_store_after_review",
                            "items": [
                                {
                                    "intake_id": "d1-intake-unit",
                                    "source_run_id": "field-private",
                                    "readiness_run_id": "unit-readiness",
                                    "device_id": "ego-link-r1-connectivity-001",
                                    "status": "pending_label_privacy_split",
                                    "review_state": {
                                        "operator_label": "missing",
                                        "privacy_review": "required",
                                        "training_consent": "not_reviewed",
                                        "split_plan": "missing",
                                        "quality_gaps": ["gnss_fix_not_seen"],
                                    },
                                    "evidence_summary": {
                                        "samples": 5,
                                        "latest_seq": 52,
                                        "raw_post_success_delta": 2,
                                        "raw_post_failure_delta": 0,
                                        "coordinate_sample_count": 5,
                                        "gnss_fix_seen": False,
                                        "imu_evidence_statuses": ["mock"],
                                        "power_evidence_statuses": ["measured"],
                                        "private_coordinates": [31.123456, 121.654321],
                                    },
                                    "requested_actions": ["attach_operator_or_user_label"],
                                    "available_decisions": ["needs_more_capture", "reject_for_training"],
                                    "training_allowed": True,
                                    "candidate_record_written": True,
                                    "raw_payload": {"secret": "do-not-copy"},
                                }
                            ],
                        },
                        "intake_reports": [
                            {
                                "run_id": "unit-intake",
                                "status": "pending_human_review",
                                "pending_items": 1,
                                "report_path": "ready/d1_labeling_intake.json",
                                "markdown_report_path": "ready/d1_labeling_intake.md",
                                "training_allowed": True,
                                "candidate_record_written": True,
                            }
                        ],
                        "review_gates": {
                            "labeling_intake": "pass",
                            "operator_label": "blocked",
                            "privacy_review": "blocked",
                            "candidate_store": "not_written",
                            "model_training": "not_run",
                        },
                        "scope": {
                            "intake_summaries_read": True,
                            "sample_jsonl_read": False,
                            "candidate_db_written": False,
                            "exact_coordinates_copied": False,
                        },
                        "next_step": "Review queue items.",
                        "raw_payload": {"secret": "do-not-copy"},
                        "features": {"private": True},
                        "target": {"label": "secret"},
                        "paths": {"private_candidate_db": "C:/private/training_candidates.db"},
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (report_dir / "d1_labeling_queue.md").write_text("# D1 queue\n", encoding="utf-8")
            store = message_hub.MessageHubStore(tmp_path / "hub.db")
            server = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                message_hub.make_handler(store, d1_labeling_queue_root=report_root),
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                state = get_json(base_url, "/api/state")
                latest = get_json(base_url, "/api/v1/d1-labeling-queue/latest")
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertEqual(state["d1_labeling_queue"]["status"], "pending_human_review")
        self.assertEqual(state["d1_labeling_queue"]["summary"]["pending_items"], 1)
        self.assertEqual(latest["d1_labeling_queue"]["queue"]["items"][0]["intake_id"], "d1-intake-unit")
        self.assertFalse(latest["d1_labeling_queue"]["queue"]["items"][0]["training_allowed"])
        self.assertFalse(latest["d1_labeling_queue"]["queue"]["items"][0]["candidate_record_written"])
        self.assertFalse(latest["d1_labeling_queue"]["scope"]["sample_jsonl_read"])
        self.assertFalse(latest["d1_labeling_queue"]["scope"]["candidate_db_written"])
        self.assertEqual(latest["d1_labeling_queue"]["review_gates"]["candidate_store"], "not_written")
        self.assertEqual(latest["d1_labeling_queue"]["markdown_path"], str(report_dir / "d1_labeling_queue.md"))
        payload_text = json.dumps(latest, sort_keys=True)
        self.assertNotIn("31.123456", payload_text)
        self.assertNotIn("121.654321", payload_text)
        self.assertNotIn("raw_payload", payload_text)
        self.assertNotIn('"features"', payload_text)
        self.assertNotIn('"target"', payload_text)
        self.assertNotIn("C:/private", payload_text)

    def test_state_api_and_endpoint_include_latest_d1_labeling_review_packet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report_root = tmp_path / "d1_labeling_reviews"
            report_dir = report_root / "unit-review"
            report_dir.mkdir(parents=True)
            (report_dir / "d1_labeling_review_packet.json").write_text(
                json.dumps(
                    {
                        "schema_version": "egolink.d1_labeling_review_packet.v0.1",
                        "run_id": "unit-labeling-review",
                        "generated_at": "2026-07-06T12:10:00+00:00",
                        "serves_demo": "D5",
                        "status": "needs_human_review",
                        "source_queue": {
                            "available": True,
                            "run_id": "unit-labeling-queue",
                            "status": "pending_human_review",
                            "report_path": "reports/d1_labeling_queue/unit/d1_labeling_queue.json",
                            "pending_item_count": 1,
                            "intake_report_count": 1,
                        },
                        "summary": {
                            "queue_pending_items": 1,
                            "review_packet_items": 1,
                            "needs_operator_label": 1,
                            "needs_privacy_review": 1,
                            "needs_training_consent": 1,
                            "needs_split_plan": 1,
                            "candidate_record_written_count": 0,
                            "training_allowed_count": 0,
                        },
                        "review_packet": {
                            "status": "open",
                            "items": [
                                {
                                    "packet_item_id": "d1-review-unit",
                                    "intake_id": "d1-intake-unit",
                                    "source_run_id": "field-private",
                                    "readiness_run_id": "unit-readiness",
                                    "device_id": "ego-link-r1-connectivity-001",
                                    "queue_status": "pending_label_privacy_split",
                                    "current_review_state": {
                                        "operator_label": "missing",
                                        "privacy_review": "required",
                                        "training_consent": "not_reviewed",
                                        "split_plan": "missing",
                                        "quality_gaps": ["gnss_fix_not_seen"],
                                    },
                                    "evidence_summary": {
                                        "samples": 5,
                                        "latest_seq": 52,
                                        "raw_post_success_delta": 2,
                                        "raw_post_failure_delta": 0,
                                        "coordinate_sample_count": 5,
                                        "gnss_fix_seen": False,
                                        "imu_evidence_statuses": ["mock"],
                                        "power_evidence_statuses": ["measured"],
                                        "private_coordinates": [31.123456, 121.654321],
                                    },
                                    "decision_slots": {
                                        "operator_label": {
                                            "required": True,
                                            "current": "missing",
                                            "selected": None,
                                            "allowed_values": ["safe", "needs_help"],
                                            "reviewed_by": "private-operator",
                                        },
                                        "candidate_decision": {
                                            "required": True,
                                            "current": "not_reviewed",
                                            "selected": None,
                                            "allowed_values": ["ready_for_candidate_store", "reject_for_training"],
                                        },
                                    },
                                    "requested_actions": ["attach_operator_or_user_label"],
                                    "available_decisions": ["needs_more_capture", "reject_for_training"],
                                    "training_allowed": True,
                                    "candidate_record_written": True,
                                    "raw_payload": {"secret": "do-not-copy"},
                                }
                            ],
                        },
                        "scope": {
                            "labeling_queue_summary_read": True,
                            "sample_jsonl_read": False,
                            "payload_bytes_copied": False,
                            "exact_coordinates_copied": False,
                            "feature_rows_copied": False,
                            "target_labels_written": False,
                            "candidate_db_written": False,
                            "training_samples_written": False,
                            "model_training_started": False,
                            "model_artifact_written": False,
                            "release_claim_allowed": False,
                        },
                        "next_step": "Fill review decisions.",
                        "raw_payload": {"secret": "do-not-copy"},
                        "features": {"private": True},
                        "target": {"label": "secret"},
                        "paths": {"private_candidate_db": "C:/private/training_candidates.db"},
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (report_dir / "d1_labeling_review_packet.md").write_text("# D1 review\n", encoding="utf-8")
            store = message_hub.MessageHubStore(tmp_path / "hub.db")
            server = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                message_hub.make_handler(store, d1_labeling_review_root=report_root),
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                state = get_json(base_url, "/api/state")
                latest = get_json(base_url, "/api/v1/d1-labeling-review-packet/latest")
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertEqual(state["d1_labeling_review_packet"]["status"], "needs_human_review")
        self.assertEqual(state["d1_labeling_review_packet"]["summary"]["review_packet_items"], 1)
        packet = latest["d1_labeling_review_packet"]["review_packet"]
        self.assertEqual(packet["items"][0]["packet_item_id"], "d1-review-unit")
        self.assertFalse(packet["items"][0]["training_allowed"])
        self.assertFalse(packet["items"][0]["candidate_record_written"])
        self.assertEqual(packet["items"][0]["decision_slots"]["operator_label"]["current"], "missing")
        self.assertFalse(latest["d1_labeling_review_packet"]["scope"]["sample_jsonl_read"])
        self.assertFalse(latest["d1_labeling_review_packet"]["scope"]["payload_bytes_copied"])
        self.assertFalse(latest["d1_labeling_review_packet"]["scope"]["candidate_db_written"])
        self.assertEqual(latest["d1_labeling_review_packet"]["review_gates"]["candidate_store"], "not_written")
        self.assertEqual(
            latest["d1_labeling_review_packet"]["markdown_path"],
            str(report_dir / "d1_labeling_review_packet.md"),
        )
        payload_text = json.dumps(latest, sort_keys=True)
        self.assertNotIn("31.123456", payload_text)
        self.assertNotIn("121.654321", payload_text)
        self.assertNotIn("raw_payload", payload_text)
        self.assertNotIn("private-operator", payload_text)
        self.assertNotIn('"features"', payload_text)
        self.assertNotIn('"target"', payload_text)
        self.assertNotIn("C:/private", payload_text)

    def test_state_api_and_endpoint_include_latest_d1_labeling_decision_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report_root = tmp_path / "d1_labeling_decisions"
            report_dir = report_root / "unit-decisions"
            report_dir.mkdir(parents=True)
            (report_dir / "d1_labeling_decision_template.json").write_text(
                json.dumps(
                    {
                        "schema_version": "egolink.d1_labeling_decision_template.v0.1",
                        "run_id": "unit-labeling-decisions",
                        "generated_at": "2026-07-06T12:20:00+00:00",
                        "serves_demo": "D5",
                        "status": "ready_for_human_input",
                        "source_review_packet": {
                            "available": True,
                            "run_id": "unit-labeling-review",
                            "status": "needs_human_review",
                            "report_path": "reports/d1_labeling_reviews/unit/d1_labeling_review_packet.json",
                            "review_packet_items": 1,
                        },
                        "summary": {
                            "template_items": 1,
                            "review_packet_items": 1,
                            "queue_pending_items": 1,
                            "required_decision_fields": 5,
                            "selected_decision_fields": 0,
                            "items_ready_for_validation": 0,
                            "candidate_record_written_count": 0,
                            "training_allowed_count": 0,
                            "ready_for_candidate_promotion": False,
                        },
                        "decision_template": {
                            "status": "open",
                            "items": [
                                {
                                    "packet_item_id": "d1-review-unit",
                                    "intake_id": "d1-intake-unit",
                                    "source_run_id": "field-private",
                                    "readiness_run_id": "unit-readiness",
                                    "device_id": "ego-link-r1-connectivity-001",
                                    "queue_status": "pending_label_privacy_split",
                                    "current_review_state": {
                                        "operator_label": "missing",
                                        "privacy_review": "required",
                                        "training_consent": "not_reviewed",
                                        "split_plan": "missing",
                                        "quality_gaps": ["gnss_fix_not_seen"],
                                    },
                                    "evidence_summary": {
                                        "samples": 5,
                                        "latest_seq": 52,
                                        "raw_post_success_delta": 2,
                                        "raw_post_failure_delta": 0,
                                        "coordinate_sample_count": 5,
                                        "gnss_fix_seen": False,
                                        "imu_evidence_statuses": ["mock"],
                                        "power_evidence_statuses": ["measured"],
                                        "private_coordinates": [31.123456, 121.654321],
                                    },
                                    "decision_fields": {
                                        "operator_label": {
                                            "required": True,
                                            "current": "missing",
                                            "selected": None,
                                            "allowed_values": ["safe", "needs_help"],
                                            "operator_note": "private-note",
                                        },
                                        "candidate_decision": {
                                            "required": True,
                                            "current": "not_reviewed",
                                            "selected": None,
                                            "allowed_values": ["ready_for_candidate_store", "reject_for_training"],
                                        },
                                    },
                                    "requested_actions": ["attach_operator_or_user_label"],
                                    "available_decisions": ["needs_more_capture", "reject_for_training"],
                                    "validation_state": "not_submitted",
                                    "training_allowed": True,
                                    "candidate_record_written": True,
                                    "raw_payload": {"secret": "do-not-copy"},
                                }
                            ],
                        },
                        "scope": {
                            "review_packet_summary_read": True,
                            "sample_jsonl_read": False,
                            "payload_bytes_copied": False,
                            "exact_coordinates_copied": False,
                            "feature_rows_copied": False,
                            "target_labels_written": False,
                            "candidate_db_written": False,
                            "training_samples_written": False,
                            "model_training_started": False,
                            "model_artifact_written": False,
                            "release_claim_allowed": False,
                        },
                        "next_step": "Fill selected values.",
                        "raw_payload": {"secret": "do-not-copy"},
                        "features": {"private": True},
                        "target": {"label": "secret"},
                        "paths": {"private_candidate_db": "C:/private/training_candidates.db"},
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (report_dir / "d1_labeling_decision_template.md").write_text("# D1 decisions\n", encoding="utf-8")
            store = message_hub.MessageHubStore(tmp_path / "hub.db")
            server = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                message_hub.make_handler(store, d1_labeling_decision_root=report_root),
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                state = get_json(base_url, "/api/state")
                latest = get_json(base_url, "/api/v1/d1-labeling-decision-template/latest")
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertEqual(state["d1_labeling_decision_template"]["status"], "ready_for_human_input")
        self.assertEqual(state["d1_labeling_decision_template"]["summary"]["template_items"], 1)
        template = latest["d1_labeling_decision_template"]["decision_template"]
        self.assertEqual(template["items"][0]["packet_item_id"], "d1-review-unit")
        self.assertFalse(template["items"][0]["training_allowed"])
        self.assertFalse(template["items"][0]["candidate_record_written"])
        self.assertEqual(template["items"][0]["decision_fields"]["operator_label"]["current"], "missing")
        self.assertIsNone(template["items"][0]["decision_fields"]["operator_label"].get("selected"))
        self.assertFalse(latest["d1_labeling_decision_template"]["scope"]["sample_jsonl_read"])
        self.assertFalse(latest["d1_labeling_decision_template"]["scope"]["payload_bytes_copied"])
        self.assertFalse(latest["d1_labeling_decision_template"]["scope"]["candidate_db_written"])
        self.assertEqual(latest["d1_labeling_decision_template"]["review_gates"]["candidate_store"], "not_written")
        self.assertEqual(
            latest["d1_labeling_decision_template"]["markdown_path"],
            str(report_dir / "d1_labeling_decision_template.md"),
        )
        payload_text = json.dumps(latest, sort_keys=True)
        self.assertNotIn("31.123456", payload_text)
        self.assertNotIn("121.654321", payload_text)
        self.assertNotIn("raw_payload", payload_text)
        self.assertNotIn("private-note", payload_text)
        self.assertNotIn('"features"', payload_text)
        self.assertNotIn('"target"', payload_text)
        self.assertNotIn("C:/private", payload_text)

    def test_raw_ingest_fail_once_injection_retains_raw_frame_without_deriving(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            server = ThreadingHTTPServer(("127.0.0.1", 0), message_hub.make_handler(store))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            payload = (
                "event_type=location_report\n"
                "priority=normal\n"
                "fw_version=0.1.0-lte009-raw-post-retry-fault\n"
                "test_run_id=lte009-fail-once-unit\n"
                "seq=7\n"
                "source=sim7670g_firmware_gnss\n"
                "source_status=unverified\n"
                "fix=false\n"
                "gnss_state=no_fix\n"
                "location_request_cmd_id=cmd-fail-once\n"
                "transport_type=lte\n"
                "lte_http_phase=location_report\n"
                "test_inject_raw_post_fail_once=true\n"
            ).encode("utf-8")
            frame = message_hub.build_raw_frame(
                "event",
                "loc-cmd-fail-once",
                payload,
                seq=7,
                metadata={"test-run-id": "lte009-fail-once-unit"},
            )
            try:
                post_json(base_url, "/api/v1/test-runs", {"test_run_id": "lte009-fail-once-unit"})
                with self.assertRaises(error.HTTPError) as raised:
                    post_bytes(base_url, "/api/v1/devices/ego-link-001/raw-ingest", frame)
                failure_body = json.loads(raised.exception.read().decode("utf-8"))
                raw_after_fail = get_json(base_url, "/api/v1/devices/ego-link-001/raw-frames")["raw_frames"]
                history_after_fail = get_json(base_url, "/api/v1/devices/ego-link-001/telemetry/history")[
                    "telemetry"
                ]

                success = post_bytes(base_url, "/api/v1/devices/ego-link-001/raw-ingest", frame)
                history_after_retry = get_json(base_url, "/api/v1/devices/ego-link-001/telemetry/history")[
                    "telemetry"
                ]
                exported = get_json(base_url, "/api/v1/test-runs/lte009-fail-once-unit/export")
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertEqual(raised.exception.code, 503)
        self.assertFalse(failure_body["ok"])
        self.assertEqual(failure_body["error"], "raw_post_fail_once_injected")
        self.assertEqual(failure_body["raw_frame"]["parse_result"]["status"], "injected_failure")
        self.assertEqual(raw_after_fail[0]["parse_result"]["status"], "injected_failure")
        self.assertEqual(raw_after_fail[0]["parse_result"]["error_code"], "RAW_POST_FAIL_ONCE_INJECTED")
        self.assertEqual(history_after_fail, [])
        self.assertTrue(success["ok"])
        self.assertEqual(success["raw_frame"]["parse_result"]["status"], "ok")
        self.assertEqual(history_after_retry[0]["event_type"], "location_report")
        self.assertEqual(history_after_retry[0]["raw_frame"]["frame_id"], "loc-cmd-fail-once")
        raw_statuses = [frame["parse_result"]["status"] for frame in exported["raw_frames"]]
        self.assertIn("injected_failure", raw_statuses)
        self.assertIn("ok", raw_statuses)

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
            server = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                message_hub.make_handler(
                    store,
                    token="secret",
                    training_experiment_root=Path(tmp) / "empty_training_experiments",
                    training_run_root=Path(tmp) / "empty_training_runs",
                    training_feature_root=Path(tmp) / "empty_training_features",
                    training_runner_dry_run_root=Path(tmp) / "empty_training_runner_dry_runs",
                    training_baseline_eval_root=Path(tmp) / "empty_training_baseline_evals",
                    training_handoff_root=Path(tmp) / "empty_training_handoffs",
                    training_job_root=Path(tmp) / "empty_training_jobs",
                    synthetic_training_chain_root=Path(tmp) / "empty_synthetic_training_chains",
                ),
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                health = get_json(base_url, "/health")
                capture_body, capture_type = get_bytes(base_url, "/d2-reference-capture")
                with self.assertRaises(error.HTTPError) as context:
                    get_json(base_url, "/api/state")
                state = get_json(base_url, "/api/state", headers={"Authorization": "Bearer secret"})
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertTrue(health["ok"])
        self.assertIn("text/html", capture_type)
        self.assertIn(b"D2 Reference Capture", capture_body)
        self.assertIn(b"localStorage", capture_body)
        self.assertEqual(context.exception.code, 401)
        self.assertEqual(state["devices"], [])
        self.assertIn("training_experiment", state)
        self.assertEqual(state["training_experiment"]["reason"], "no_training_experiment_plan")
        self.assertIn("training_run_preflight", state)
        self.assertEqual(state["training_run_preflight"]["reason"], "no_training_run_preflight")
        self.assertIn("training_feature_manifest", state)
        self.assertEqual(state["training_feature_manifest"]["reason"], "no_training_feature_manifest")
        self.assertIn("training_runner_dry_run", state)
        self.assertEqual(state["training_runner_dry_run"]["reason"], "no_training_runner_dry_run")
        self.assertIn("training_baseline_eval", state)
        self.assertEqual(state["training_baseline_eval"]["reason"], "no_training_baseline_eval")
        self.assertIn("training_handoff_bundle", state)
        self.assertEqual(state["training_handoff_bundle"]["reason"], "no_training_handoff_bundle")
        self.assertIn("training_job_plan", state)
        self.assertEqual(state["training_job_plan"]["reason"], "no_training_job_plan")
        self.assertIn("synthetic_training_chain", state)
        self.assertEqual(state["synthetic_training_chain"]["reason"], "no_synthetic_training_chain")

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

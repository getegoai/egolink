from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from scripts import validate_lte_reliability_gate


class LteReliabilityGateTests(unittest.TestCase):
    def test_loc_like_export_warns_without_reconnect_cache_observation(self) -> None:
        report = validate_lte_reliability_gate.evaluate_lte_reliability_export(
            self._loc005a_like_export(),
            input_path=Path("fixture/test_run_export.json"),
        )

        self.assertEqual(report["result"], "WARN")
        self.assertEqual(report["errors"], [])
        self.assertEqual(self._gate(report, "G1_COMMAND_STATE_VISIBLE")["status"], "PASS")
        self.assertEqual(self._gate(report, "G3_DUPLICATE_EXECUTION_GUARD")["status"], "PASS")
        self.assertEqual(self._gate(report, "G4_LTE_TRANSPORT_EVIDENCE")["status"], "PASS")
        self.assertEqual(self._gate(report, "G5_FAILURE_REASON_VISIBLE")["status"], "PASS")
        self.assertEqual(self._gate(report, "G7_RAW_FRAME_RETENTION")["status"], "PASS")
        self.assertEqual(self._gate(report, "G6_RECONNECT_CACHE_OBSERVABILITY")["status"], "WARN")

    def test_stale_pending_command_passes_when_ack_missing_reason_is_visible(self) -> None:
        export = self._loc005a_like_export()
        export["messages"] = [
            {
                "message_type": "event",
                "event_type": "lte_http_command_diag",
                "seq": 1,
                "server_received_at": "2026-06-30T10:15:00+00:00",
                "fw_version": "0.1.0-fw003-raw-command-loop",
                "test_run_id": "lte005-stale-unit",
                "transport": {"type": "lte"},
                "lte_http": {"phase": "poll_no_ack", "poll_reason_code": "LTE_HTTP_OK"},
                "command": {"command_count": 0, "parse_status": "raw_no_command"},
            }
        ]
        export["commands"] = [
            {
                "cmd_id": "cmd-stale-001",
                "cmd": "request_location",
                "status": "pending",
                "created_at": "2026-06-30T10:00:00+00:00",
                "updated_at": "2026-06-30T10:00:00+00:00",
            }
        ]
        export["observability_summary"] = {
            "failure_summary": {
                "state": "pending",
                "reason": "command_pending_ack_missing",
                "reason_codes": ["COMMAND_PENDING_ACK_MISSING"],
            },
            "reason_codes": ["COMMAND_PENDING_ACK_MISSING"],
        }

        report = validate_lte_reliability_gate.evaluate_lte_reliability_export(
            export,
            stale_command_sec=300,
        )

        self.assertEqual(self._gate(report, "G2_STALE_PENDING_VISIBLE")["status"], "PASS")
        self.assertNotIn("stale_pending_command_without_failure_reason", report["errors"])

    def test_cache_not_enabled_explains_but_does_not_pass_cache_observability(self) -> None:
        export = self._loc005a_like_export()
        export["messages"][1]["reliability"] = {
            "network": {"mode": "LTE", "state": "ready", "last_error": "none"},
            "cache": {
                "state": "not_enabled",
                "source_status": "unverified",
                "last_drop_reason": "cache_not_enabled",
            },
        }

        report = validate_lte_reliability_gate.evaluate_lte_reliability_export(export)
        gate = self._gate(report, "G6_RECONNECT_CACHE_OBSERVABILITY")

        self.assertEqual(report["result"], "WARN")
        self.assertEqual(gate["status"], "WARN")
        self.assertIn("cache_capability_not_enabled", gate["warnings"])
        self.assertEqual(gate["evidence"]["cache_evidence_hits"], [])
        self.assertTrue(gate["evidence"]["cache_nonclaim_hits"])

    def test_duplicate_command_without_prevention_fails(self) -> None:
        export = self._loc005a_like_export()
        export["commands"][0]["ack"]["command"]["command_count"] = 2
        export["commands"][0]["ack"]["command"]["duplicate_local_execution_prevented"] = False
        export["messages"][-1]["command"]["command_count"] = 2
        export["messages"][-1]["command"]["duplicate_local_execution_prevented"] = False

        report = validate_lte_reliability_gate.evaluate_lte_reliability_export(export)

        self.assertEqual(report["result"], "FAIL")
        self.assertIn("duplicate_command_execution_risk", report["errors"])
        self.assertEqual(self._gate(report, "G3_DUPLICATE_EXECUTION_GUARD")["status"], "FAIL")

    def test_cli_writes_json_and_markdown_reports_for_warn_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "test_run_export.json"
            output_dir = tmp_path / "out"
            input_path.write_text(json.dumps(self._loc005a_like_export(), ensure_ascii=False), encoding="utf-8")

            with redirect_stdout(StringIO()):
                exit_code = validate_lte_reliability_gate.main(
                    [
                        "--input",
                        str(input_path),
                        "--output-dir",
                        str(output_dir),
                    ]
                )

            self.assertEqual(exit_code, 0)
            report_path = output_dir / "lte_reliability_gate_report.json"
            markdown_path = output_dir / "lte_reliability_gate_report.md"
            self.assertTrue(report_path.is_file())
            self.assertTrue(markdown_path.is_file())
            saved = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["result"], "WARN")
            self.assertIn("LTE-005 Reliability Gate Report", markdown_path.read_text(encoding="utf-8"))

    @staticmethod
    def _gate(report: dict, gate_id: str) -> dict:
        for gate in report["gates"]:
            if gate["id"] == gate_id:
                return gate
        raise AssertionError(f"missing gate {gate_id}")

    @staticmethod
    def _loc005a_like_export() -> dict:
        ack = {
            "protocol_version": "egolink.p0.v1",
            "device_id": "ego-link-r1-connectivity-001",
            "message_type": "ack",
            "cmd_id": "cmd-000024",
            "status": "ok",
            "seq": 4,
            "server_received_at": "2026-06-30T09:06:05+00:00",
            "fw_version": "0.1.0-loc005a-source-states",
            "test_run_id": "loc005a-source-states-20260630-001",
            "transport": {"type": "lte"},
            "lte_http": {
                "phase": "command_ack",
                "poll_reason_code": "LTE_HTTP_OK",
                "poll_status_code": 200,
                "poll_action_elapsed_ms": 460,
            },
            "command": {
                "last_cmd_id": "cmd-000024",
                "last_status": "ok",
                "last_ack_status": "ok",
                "parse_status": "raw_command_selected",
                "command_count": 1,
                "duplicate_local_execution_prevented": False,
            },
        }
        messages = [
            {
                "protocol_version": "egolink.p0.v1",
                "device_id": "ego-link-r1-connectivity-001",
                "message_type": "event",
                "event_type": "location_report",
                "seq": 2,
                "server_received_at": "2026-06-30T09:06:01+00:00",
                "fw_version": "0.1.0-loc005a-source-states",
                "test_run_id": "loc005a-source-states-20260630-001",
                "source_status": "unverified",
                "fix": False,
                "gnss_state": "no_fix",
                "location_request_cmd_id": "cmd-000024",
                "transport": {"type": "lte"},
                "lte_http": {"phase": "location_report", "driver": "sim7670g_uart_at_http"},
            },
            {
                "protocol_version": "egolink.p0.v1",
                "device_id": "ego-link-r1-connectivity-001",
                "message_type": "event",
                "event_type": "location_observation",
                "seq": 3,
                "server_received_at": "2026-06-30T09:06:04+00:00",
                "fw_version": "0.1.0-loc005a-source-states",
                "test_run_id": "loc005a-source-states-20260630-001",
                "source_status": "observed",
                "location_request_cmd_id": "cmd-000024",
                "cell": {"rat": "LTE", "cell_id": "180571649", "reason_code": "LTE_READY"},
                "lte": {"reason_code": "LTE_READY", "pdp_state": "active"},
                "wifi": {"source_status": "disabled", "evidence_status": "missing"},
                "imu": {"source_status": "unverified", "evidence_status": "mock"},
                "power": {"source_status": "mock", "evidence_status": "mock"},
                "transport": {"type": "lte"},
                "lte_http": {"phase": "location_observation", "driver": "sim7670g_uart_at_http"},
            },
            ack,
        ]
        return {
            "test_run": {
                "test_run_id": "loc005a-source-states-20260630-001",
                "task_id": "LTE-005",
                "board_id": "connectivity-node-001",
                "device_id": "ego-link-r1-connectivity-001",
                "connection_path": "independent_power_usb_disconnected",
                "started_at": "2026-06-30T08:56:56+00:00",
                "status": "active",
            },
            "commands": [
                {
                    "protocol_version": "egolink.p0.v1",
                    "device_id": "ego-link-r1-connectivity-001",
                    "message_type": "command",
                    "cmd_id": "cmd-000024",
                    "cmd": "request_location",
                    "status": "ok",
                    "created_at": "2026-06-30T08:56:56+00:00",
                    "updated_at": "2026-06-30T09:06:05+00:00",
                    "test_run_id": "loc005a-source-states-20260630-001",
                    "ack": ack,
                }
            ],
            "messages": messages,
            "raw_frames": [
                self_frame("cmd-000024", "downlink", "command", None),
                self_frame("loc-cmd-000024", "uplink", "event", 2),
                self_frame("obs-cmd-000024", "uplink", "event", 3),
                self_frame("cmd-000024", "uplink", "ack", 4),
            ],
            "observability_summary": {
                "message_count": 3,
                "command_count": 1,
                "reason_codes": ["GNSS_NO_FIX"],
                "latest_observability": {
                    "runtime": {"last_reset_reason": "poweron", "boot_id": "boot_count:1"},
                    "transport": {"type": "lte", "last_error": None},
                },
            },
        }


def self_frame(frame_id: str, direction: str, frame_type: str, seq: int | None) -> dict:
    return {
        "device_id": "ego-link-r1-connectivity-001",
        "direction": direction,
        "frame_id": frame_id,
        "seq": seq,
        "server_received_at": "2026-06-30T09:06:00+00:00",
        "test_run_id": "loc005a-source-states-20260630-001",
        "transport_profile": "raw-frame.p0.v1",
        "framing": {
            "frame_type": frame_type,
            "payload_len": 64,
            "payload_crc32": "ABCD1234",
            "actual_payload_len": 64,
            "actual_payload_crc32": "ABCD1234",
        },
        "raw_payload": {
            "byte_len": 128,
            "crc32": "ABCD1234",
            "sha256": f"{frame_id}-sha256",
            "encoding": "base64",
            "data_redacted": True,
        },
        "parse_result": {"status": "ok", "derived_message_type": frame_type},
    }


if __name__ == "__main__":
    unittest.main()

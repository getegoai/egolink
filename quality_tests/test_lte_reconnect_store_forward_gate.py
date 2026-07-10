from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from scripts import validate_lte_reconnect_store_forward_gate


class LteReconnectStoreForwardGateTests(unittest.TestCase):
    def test_lte009_like_export_warns_without_reconnect_or_store_forward(self) -> None:
        report = validate_lte_reconnect_store_forward_gate.evaluate_lte_reconnect_store_forward_export(
            self._lte009_like_export()
        )

        self.assertEqual(report["result"], "WARN")
        self.assertEqual(report["errors"], [])
        self.assertEqual(self._gate(report, "G1_LTE_RUNTIME_CHAIN")["status"], "PASS")
        self.assertEqual(self._gate(report, "G2_RECONNECT_ATTEMPT_VISIBLE")["status"], "NOT_OBSERVED")
        self.assertEqual(self._gate(report, "G4_POST_RECONNECT_RECOVERY")["status"], "NOT_OBSERVED")
        self.assertEqual(self._gate(report, "G5_STORE_FORWARD_EVIDENCE")["status"], "WARN")
        self.assertIn("reconnect_attempt_not_observed", report["warnings"])
        self.assertIn("volatile_or_nonclaim_cache_only", report["warnings"])

    def test_full_reconnect_and_store_forward_evidence_passes(self) -> None:
        report = validate_lte_reconnect_store_forward_gate.evaluate_lte_reconnect_store_forward_export(
            self._recovered_store_forward_export()
        )

        self.assertEqual(report["result"], "PASS")
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["warnings"], [])
        self.assertEqual(self._gate(report, "G2_RECONNECT_ATTEMPT_VISIBLE")["status"], "PASS")
        self.assertEqual(self._gate(report, "G3_RECONNECT_FAILURE_REASON")["status"], "PASS")
        self.assertEqual(self._gate(report, "G4_POST_RECONNECT_RECOVERY")["status"], "PASS")
        self.assertEqual(self._gate(report, "G5_STORE_FORWARD_EVIDENCE")["status"], "PASS")

    def test_reconnect_claim_without_later_lte_ack_fails(self) -> None:
        export = self._recovered_store_forward_export()
        export["commands"][0]["ack"] = {}
        export["commands"][0]["status"] = "pending"
        export["messages"] = export["messages"][:-1]

        report = validate_lte_reconnect_store_forward_gate.evaluate_lte_reconnect_store_forward_export(export)

        self.assertEqual(report["result"], "FAIL")
        self.assertIn("post_reconnect_lte_ack_missing", report["errors"])
        self.assertEqual(self._gate(report, "G4_POST_RECONNECT_RECOVERY")["status"], "FAIL")

    def test_store_forward_claim_without_counters_fails(self) -> None:
        export = self._recovered_store_forward_export()
        export["messages"][0]["reliability"]["cache"] = {
            "state": "store_forward",
            "source_status": "observed",
        }

        report = validate_lte_reconnect_store_forward_gate.evaluate_lte_reconnect_store_forward_export(export)

        self.assertEqual(report["result"], "FAIL")
        self.assertIn("store_forward_evidence_incomplete", report["errors"])

    def test_cli_writes_reports_for_warn_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "test_run_export.json"
            output_dir = tmp_path / "out"
            input_path.write_text(json.dumps(self._lte009_like_export(), ensure_ascii=False), encoding="utf-8")

            with redirect_stdout(StringIO()):
                exit_code = validate_lte_reconnect_store_forward_gate.main(
                    [
                        "--input",
                        str(input_path),
                        "--output-dir",
                        str(output_dir),
                    ]
                )

            self.assertEqual(exit_code, 0)
            report_path = output_dir / "lte_reconnect_store_forward_gate_report.json"
            markdown_path = output_dir / "lte_reconnect_store_forward_gate_report.md"
            self.assertTrue(report_path.is_file())
            self.assertTrue(markdown_path.is_file())
            saved = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["result"], "WARN")
            self.assertIn("LTE-010 Reconnect Store-Forward", markdown_path.read_text(encoding="utf-8"))

    @staticmethod
    def _gate(report: dict, gate_id: str) -> dict:
        for gate in report["gates"]:
            if gate["id"] == gate_id:
                return gate
        raise AssertionError(f"missing gate {gate_id}")

    @staticmethod
    def _lte009_like_export() -> dict:
        ack = {
            "protocol_version": "egolink.p0.v1",
            "device_id": "ego-link-r1-connectivity-001",
            "message_type": "ack",
            "cmd_id": "cmd-000031",
            "status": "ok",
            "seq": 29,
            "server_received_at": "2026-07-01T13:37:16+00:00",
            "fw_version": "0.1.0-lte009-raw-post-retry-fault",
            "test_run_id": "lte009-raw-post-retry-fault-20260701-001",
            "transport": {"type": "lte"},
            "lte_http": {"phase": "command_ack", "poll_reason_code": "LTE_HTTP_OK", "poll_status_code": 200},
            "reliability": {
                "network": {"raw_post_attempt_count": 3, "raw_post_success_count": 2, "raw_post_failure_count": 1},
                "cache": {
                    "state": "volatile_outbox",
                    "source_status": "observed",
                    "queued_message_count": 0,
                    "dropped_message_count": 0,
                    "oldest_message_age_ms": 0,
                    "last_drop_reason": "none",
                    "retry_policy": "single_retry_current_boot",
                    "retry_attempt_count": 1,
                    "retry_success_count": 1,
                    "retry_failure_count": 0,
                },
            },
            "command": {"last_cmd_id": "cmd-000031", "last_status": "ok", "parse_status": "raw_command_selected"},
        }
        messages = [
            {
                "protocol_version": "egolink.p0.v1",
                "device_id": "ego-link-r1-connectivity-001",
                "message_type": "event",
                "event_type": "location_report",
                "seq": 27,
                "server_received_at": "2026-07-01T13:37:11+00:00",
                "fw_version": "0.1.0-lte009-raw-post-retry-fault",
                "test_run_id": "lte009-raw-post-retry-fault-20260701-001",
                "transport": {"type": "lte"},
                "lte_http": {"phase": "location_report"},
                "fix": False,
                "gnss_state": "no_fix",
            },
            {
                "protocol_version": "egolink.p0.v1",
                "device_id": "ego-link-r1-connectivity-001",
                "message_type": "event",
                "event_type": "location_observation",
                "seq": 28,
                "server_received_at": "2026-07-01T13:37:14+00:00",
                "fw_version": "0.1.0-lte009-raw-post-retry-fault",
                "test_run_id": "lte009-raw-post-retry-fault-20260701-001",
                "transport": {"type": "lte"},
                "lte": {"reason_code": "LTE_READY"},
                "reliability": ack["reliability"],
            },
            ack,
        ]
        return base_export(messages, ack)

    @staticmethod
    def _recovered_store_forward_export() -> dict:
        reconnect_diag = {
            "protocol_version": "egolink.p0.v1",
            "device_id": "ego-link-r1-connectivity-001",
            "message_type": "event",
            "event_type": "lte_reconnect_diag",
            "seq": 40,
            "server_received_at": "2026-07-01T14:00:00+00:00",
            "fw_version": "0.1.0-lte010-reconnect-store-forward",
            "test_run_id": "lte010-reconnect-store-forward-unit",
            "transport": {"type": "lte", "last_error": "LTE_HTTP_ACTION_FAILED"},
            "lte_http": {"phase": "reconnect", "poll_reason_code": "LTE_HTTP_ACTION_FAILED"},
            "reliability": {
                "network": {
                    "mode": "LTE",
                    "state": "reconnecting",
                    "reconnect_count": 1,
                    "last_error": "LTE_HTTP_ACTION_FAILED",
                    "last_reconnect_reason": "pdp_reactivate",
                },
                "cache": {
                    "state": "store_forward",
                    "source_status": "observed",
                    "queued_message_count": 1,
                    "dropped_message_count": 0,
                    "oldest_message_age_ms": 12000,
                    "last_drop_reason": "none",
                    "flush_attempt_count": 1,
                    "flush_success_count": 1,
                    "flush_failure_count": 0,
                },
            },
        }
        ack = {
            "protocol_version": "egolink.p0.v1",
            "device_id": "ego-link-r1-connectivity-001",
            "message_type": "ack",
            "cmd_id": "cmd-000040",
            "status": "ok",
            "seq": 41,
            "server_received_at": "2026-07-01T14:00:15+00:00",
            "fw_version": "0.1.0-lte010-reconnect-store-forward",
            "test_run_id": "lte010-reconnect-store-forward-unit",
            "transport": {"type": "lte"},
            "lte_http": {"phase": "command_ack", "poll_reason_code": "LTE_HTTP_OK", "poll_status_code": 200},
            "reliability": {
                "network": {
                    "mode": "LTE",
                    "state": "ready",
                    "reconnect_count": 1,
                    "last_error": "none",
                    "last_reconnect_reason": "pdp_reactivate",
                },
                "cache": {
                    "state": "store_forward",
                    "source_status": "observed",
                    "queued_message_count": 0,
                    "dropped_message_count": 0,
                    "oldest_message_age_ms": 0,
                    "last_drop_reason": "none",
                    "flush_attempt_count": 1,
                    "flush_success_count": 1,
                    "flush_failure_count": 0,
                },
            },
            "command": {"last_cmd_id": "cmd-000040", "last_status": "ok", "parse_status": "raw_command_selected"},
        }
        return base_export([reconnect_diag, ack], ack, test_run_id="lte010-reconnect-store-forward-unit")


def base_export(messages: list[dict], ack: dict, test_run_id: str = "lte009-raw-post-retry-fault-20260701-001") -> dict:
    return {
        "test_run": {
            "test_run_id": test_run_id,
            "task_id": "LTE-010",
            "board_id": "connectivity-node-001",
            "device_id": "ego-link-r1-connectivity-001",
            "connection_path": "independent_power_usb_disconnected",
            "started_at": "2026-07-01T13:37:04+00:00",
            "status": "active",
        },
        "commands": [
            {
                "protocol_version": "egolink.p0.v1",
                "device_id": "ego-link-r1-connectivity-001",
                "message_type": "command",
                "cmd_id": ack.get("cmd_id", "cmd-000031"),
                "cmd": "request_location",
                "status": ack.get("status", "ok"),
                "created_at": "2026-07-01T13:37:05+00:00",
                "updated_at": ack.get("server_received_at"),
                "test_run_id": test_run_id,
                "ack": ack,
            }
        ],
        "messages": messages,
        "raw_frames": [
            self_frame("cmd-000031", "downlink", "command", None, test_run_id),
            self_frame("loc-cmd-000031", "uplink", "event", 27, test_run_id),
            self_frame("obs-cmd-000031", "uplink", "event", 28, test_run_id),
            self_frame(ack.get("cmd_id", "cmd-000031"), "uplink", "ack", ack.get("seq", 29), test_run_id),
        ],
    }


def self_frame(frame_id: str, direction: str, frame_type: str, seq: int | None, test_run_id: str) -> dict:
    return {
        "device_id": "ego-link-r1-connectivity-001",
        "direction": direction,
        "frame_id": frame_id,
        "seq": seq,
        "server_received_at": "2026-07-01T13:37:06+00:00",
        "test_run_id": test_run_id,
        "transport_profile": "raw-frame.p0.v1",
        "framing": {"frame_type": frame_type, "payload_len": 64, "payload_crc32": "ABCD1234"},
        "raw_payload": {"byte_len": 128, "crc32": "ABCD1234", "sha256": f"{frame_id}-sha256"},
        "parse_result": {"status": "ok", "derived_message_type": frame_type},
    }


if __name__ == "__main__":
    unittest.main()

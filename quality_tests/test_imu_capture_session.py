from __future__ import annotations

import copy
import json
import unittest

from scripts import run_imu_capture_session as capture


def valid_plan() -> dict:
    return {
        "schema_version": capture.PLAN_SCHEMA_VERSION,
        "plan_id": "d5-002-seed-01",
        "device_id": "ego-link-r1-connectivity-001",
        "test_run_id": "d5-002-seed-01",
        "sample_count": 100,
        "interval_ms": 50,
        "sessions": [
            {
                "session_id": "session-still",
                "split_name": "train",
                "windows": [{"cmd_id": "d5002-still", "planned_activity": "stationary"}],
            },
            {
                "session_id": "session-walk",
                "split_name": "validation",
                "windows": [{"cmd_id": "d5002-walk", "planned_activity": "walking"}],
            },
            {
                "session_id": "session-transition",
                "split_name": "test",
                "windows": [{"cmd_id": "d5002-trans", "planned_activity": "transition_or_unknown"}],
            },
        ],
    }


def raw_window(
    cmd_id: str,
    test_run_id: str,
    ordinal: int,
    *,
    transport_type: str = "wifi",
    boot_count: int = 1,
) -> list[dict]:
    common = {
        "contract_version": "egolink.imu_window.v1",
        "window_id": f"imuw-{cmd_id}-b1",
        "capture_cmd_id": cmd_id,
        "test_run_id": test_run_id,
        "transport_type": transport_type,
        "source": "qmi8658_i2c",
        "source_status": "observed",
        "training_allowed": False,
        "boot_count": boot_count,
    }
    frames = []
    for index in range(10):
        frames.append(
            {
                "frame_id": f"chunk-{ordinal}-{index}",
                "parse_result": {
                    "status": "ok",
                    "derived_message": {
                        "event_type": "imu_window_chunk",
                        "imu_window": {**common, "chunk_index": index},
                    },
                },
            }
        )
    frames.append(
        {
            "frame_id": f"manifest-{ordinal}",
            "parse_result": {
                "status": "ok",
                "derived_message": {
                    "event_type": "imu_window_manifest",
                    "imu_window": {
                        **common,
                        "sample_count": 100,
                        "requested_interval_us": 50000,
                        "capture_start_uptime_us": ordinal * 10_000_000,
                        "capture_end_uptime_us": ordinal * 10_000_000 + 4_950_000,
                        "chunk_count": 10,
                        "uploaded_chunk_count": 10,
                        "read_failure_count": 0,
                        "mock_sample_count": 0,
                        "min_interval_us": 49900,
                        "mean_interval_us": 50000,
                        "max_interval_us": 50100,
                        "deadline_miss_count": 0,
                        "samples_crc32": f"{ordinal:08X}",
                    },
                },
            },
        }
    )
    return frames


class FakeHubClient:
    def __init__(
        self,
        plan: dict,
        *,
        fail_status: str | None = None,
        duplicate: bool = False,
        in_progress_before_ok: bool = False,
        ack_transport: str | None = None,
        raw_transport: str | None = None,
    ) -> None:
        self.plan = plan
        self.fail_status = fail_status
        self.duplicate = duplicate
        self.in_progress_before_ok = in_progress_before_ok
        self.expected_transport = capture.plan_transport_type(plan)
        self.ack_transport = ack_transport
        self.raw_transport = raw_transport
        self.events: list[str] = []
        self.current_cmd: str | None = None
        self.completed: list[str] = []
        self.ack_polls: dict[str, int] = {}
        self.test_run_payload: dict | None = None

    def post(self, path: str, payload: dict) -> dict:
        if path == "/api/v1/test-runs":
            self.events.append("post:test-run")
            self.test_run_payload = copy.deepcopy(payload)
            return {"ok": True, "test_run": dict(payload)}
        cmd_id = payload["cmd_id"]
        self.events.append(f"post:{cmd_id}")
        self.current_cmd = cmd_id
        self.assert_payload(payload)
        return {"command": {**payload, "status": "pending"}}

    def assert_payload(self, payload: dict) -> None:
        if payload != {
            "cmd": "capture_imu_window",
            "cmd_id": payload["cmd_id"],
            "test_run_id": self.plan["test_run_id"],
            "payload": {"sample_count": 100, "interval_ms": 50},
        }:
            raise AssertionError(f"unexpected command payload: {payload}")

    def get(self, path: str) -> dict:
        assert self.current_cmd is not None
        cmd_id = self.current_cmd
        if path.endswith("/commands"):
            self.events.append(f"ack:{cmd_id}")
            self.ack_polls[cmd_id] = self.ack_polls.get(cmd_id, 0) + 1
            if self.in_progress_before_ok and self.ack_polls[cmd_id] == 1:
                return {"commands": [{"cmd_id": cmd_id, "status": "in_progress"}]}
            status = self.fail_status if not self.completed and self.fail_status else "ok"
            return {
                "commands": [
                    {
                        "cmd_id": cmd_id,
                        "status": status,
                        "ack": {
                            "cmd_id": cmd_id,
                            "status": status,
                            "test_run_id": self.plan["test_run_id"],
                            "transport": {
                                "type": self.expected_transport if self.ack_transport is None else self.ack_transport
                            },
                            "command": {"duplicate_local_execution_prevented": self.duplicate},
                        },
                    }
                ]
            }
        self.events.append(f"raw:{cmd_id}")
        ordinal = len(self.completed) + 1
        frames = raw_window(
            cmd_id,
            self.plan["test_run_id"],
            ordinal,
            transport_type=self.expected_transport if self.raw_transport is None else self.raw_transport,
        )
        self.completed.append(cmd_id)
        return {"raw_frames": frames}


class RaisingClient:
    def __init__(self, secret: str) -> None:
        self.secret = secret

    def post(self, path: str, payload: dict) -> dict:
        raise RuntimeError(f"request failed with token {self.secret}")


class ImuCaptureSessionTests(unittest.TestCase):
    def test_window_evidence_rejects_bad_capture_span_and_mixed_boot(self) -> None:
        tiny_span = raw_window("d5002-span", "d5-002-seed-01", 1)
        tiny_span[-1]["parse_result"]["derived_message"]["imu_window"].update(
            {"capture_start_uptime_us": 1_000_000, "capture_end_uptime_us": 1_000_001}
        )
        with self.assertRaisesRegex(capture.CaptureSessionError, "capture/cadence"):
            capture._window_evidence(
                tiny_span,
                cmd_id="d5002-span",
                test_run_id="d5-002-seed-01",
                transport_type="wifi",
            )

        mixed_boot = raw_window("d5002-boot", "d5-002-seed-01", 1)
        mixed_boot[0]["parse_result"]["derived_message"]["imu_window"]["boot_count"] = 2
        with self.assertRaisesRegex(capture.CaptureSessionError, "boot_count"):
            capture._window_evidence(
                mixed_boot,
                cmd_id="d5002-boot",
                test_run_id="d5-002-seed-01",
                transport_type="wifi",
            )

        bool_alias_boot = raw_window("d5002-bool-boot", "d5-002-seed-01", 1)
        bool_alias_boot[0]["parse_result"]["derived_message"]["imu_window"][
            "boot_count"
        ] = True
        with self.assertRaisesRegex(capture.CaptureSessionError, "boot_count"):
            capture._window_evidence(
                bool_alias_boot,
                cmd_id="d5002-bool-boot",
                test_run_id="d5-002-seed-01",
                transport_type="wifi",
            )

    def test_default_dry_run_makes_no_hub_calls(self) -> None:
        class NoCalls:
            def __getattr__(self, name):
                raise AssertionError("dry-run touched the Message Hub")

        result = capture.run_session(valid_plan(), plan_sha256="a" * 64, client=NoCalls())
        self.assertEqual(result["status"], "dry_run_ready")
        self.assertEqual(result["transport_type"], "wifi")
        self.assertEqual([item["state"] for item in result["results"]], ["planned"] * 3)
        self.assertTrue(all(item["transport_type"] == "wifi" for item in result["results"]))
        self.assertFalse(result["training_allowed"])
        self.assertNotIn("activity_label", json.dumps(result))

    def test_execute_runs_three_commands_strictly_in_order(self) -> None:
        plan = valid_plan()
        client = FakeHubClient(plan)
        result = capture.run_session(plan, plan_sha256="a" * 64, execute=True, client=client)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["completed_window_count"], 3)
        self.assertEqual(
            client.events,
            [
                "post:test-run",
                "post:d5002-still", "ack:d5002-still", "raw:d5002-still",
                "post:d5002-walk", "ack:d5002-walk", "raw:d5002-walk",
                "post:d5002-trans", "ack:d5002-trans", "raw:d5002-trans",
            ],
        )
        self.assertTrue(all(item["state"] == "ok" for item in result["results"]))
        self.assertTrue(all(item["window"]["training_allowed"] is False for item in result["results"]))
        self.assertTrue(result["test_run_created"])
        self.assertEqual(client.test_run_payload["task_id"], "D5-002")
        self.assertEqual(client.test_run_payload["goal"], "bounded three-window Wi-Fi QMI8658 pipeline seed")
        self.assertEqual(result["commands_created"], ["d5002-still", "d5002-walk", "d5002-trans"])
        self.assertEqual(len(result["external_actions"]), 4)

    def test_explicit_lte_executes_three_windows_with_lte_lineage(self) -> None:
        plan = valid_plan()
        plan["transport_type"] = "lte"
        client = FakeHubClient(plan)

        result = capture.run_session(plan, plan_sha256="a" * 64, execute=True, client=client)

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["transport_type"], "lte")
        self.assertEqual(result["completed_window_count"], 3)
        self.assertEqual(client.test_run_payload["task_id"], "FIELD-011")
        self.assertEqual(client.test_run_payload["goal"], "bounded three-window LTE QMI8658 pipeline seed")
        self.assertEqual(
            [event for event in client.events if event.startswith("post:")],
            ["post:test-run", "post:d5002-still", "post:d5002-walk", "post:d5002-trans"],
        )
        self.assertTrue(all(item["transport_type"] == "lte" for item in result["results"]))
        self.assertTrue(all(item["ack"]["transport_type"] == "lte" for item in result["results"]))
        self.assertTrue(all(item["window"]["transport_type"] == "lte" for item in result["results"]))

    def test_lte_plan_fails_closed_on_wrong_ack_transport(self) -> None:
        plan = valid_plan()
        plan["transport_type"] = "lte"
        client = FakeHubClient(plan, ack_transport="wifi")

        result = capture.run_session(plan, plan_sha256="a" * 64, execute=True, client=client)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["completed_window_count"], 0)
        self.assertIn("ACK transport must be lte", result["results"][0]["error"])
        self.assertEqual(
            [event for event in client.events if event.startswith("post:")],
            ["post:test-run", "post:d5002-still"],
        )
        self.assertFalse(any(event.startswith("raw:") for event in client.events))

    def test_lte_plan_fails_closed_on_wrong_raw_window_transport(self) -> None:
        plan = valid_plan()
        plan["transport_type"] = "lte"
        client = FakeHubClient(plan, raw_transport="wifi")

        result = capture.run_session(plan, plan_sha256="a" * 64, execute=True, client=client)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["completed_window_count"], 0)
        self.assertIn("invalid IMU source/transport/privacy lineage", result["results"][0]["error"])
        self.assertEqual(
            [event for event in client.events if event.startswith("post:")],
            ["post:test-run", "post:d5002-still"],
        )

    def test_first_non_ok_ack_stops_before_next_command(self) -> None:
        plan = valid_plan()
        client = FakeHubClient(plan, fail_status="error")
        result = capture.run_session(plan, plan_sha256="a" * 64, execute=True, client=client)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["completed_window_count"], 0)
        self.assertEqual(
            [event for event in client.events if event.startswith("post:")],
            ["post:test-run", "post:d5002-still"],
        )

    def test_in_progress_is_waited_until_ok_ack(self) -> None:
        plan = valid_plan()
        client = FakeHubClient(plan, in_progress_before_ok=True)
        result = capture.run_session(
            plan,
            plan_sha256="a" * 64,
            execute=True,
            client=client,
            sleep_fn=lambda _: None,
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["completed_window_count"], 3)
        self.assertEqual(client.ack_polls, {"d5002-still": 2, "d5002-walk": 2, "d5002-trans": 2})

    def test_duplicate_ack_marker_stops_before_next_command(self) -> None:
        plan = valid_plan()
        client = FakeHubClient(plan, duplicate=True)
        result = capture.run_session(plan, plan_sha256="a" * 64, execute=True, client=client)
        self.assertEqual(result["status"], "failed")
        self.assertIn("duplicate", result["results"][0]["error"])
        self.assertEqual(
            [event for event in client.events if event.startswith("post:")],
            ["post:test-run", "post:d5002-still"],
        )

    def test_plan_rejects_unsafe_labels_cross_split_and_privacy_override(self) -> None:
        for unsafe in ("running", "impact", "fall", "vehicle"):
            plan = valid_plan()
            plan["sessions"][0]["windows"][0]["planned_activity"] = unsafe
            with self.subTest(unsafe=unsafe), self.assertRaises(capture.CaptureSessionError):
                capture.validate_plan(plan)

        crossed = valid_plan()
        crossed["sessions"][1]["session_id"] = crossed["sessions"][0]["session_id"]
        with self.assertRaisesRegex(capture.CaptureSessionError, "crosses split"):
            capture.validate_plan(crossed)

        overridden = valid_plan()
        overridden["training_allowed"] = True
        with self.assertRaisesRegex(capture.CaptureSessionError, "unexpected"):
            capture.validate_plan(overridden)

        for invalid_transport in ("usb", "WiFi", "LTE", "", None, ["lte"]):
            plan = valid_plan()
            plan["transport_type"] = invalid_transport
            with self.subTest(transport_type=invalid_transport), self.assertRaisesRegex(
                capture.CaptureSessionError, "transport_type"
            ):
                capture.validate_plan(plan)

    def test_error_record_redacts_token(self) -> None:
        secret = "do-not-write-this-token"
        result = capture.run_session(
            valid_plan(),
            plan_sha256="a" * 64,
            execute=True,
            client=RaisingClient(secret),
            redaction_values=(secret,),
        )
        payload = json.dumps(result)
        self.assertNotIn(secret, payload)
        self.assertIn("[REDACTED]", payload)


if __name__ == "__main__":
    unittest.main()

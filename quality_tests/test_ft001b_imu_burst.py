from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools import run_ft001b_imu_burst as burst


class FT001BImuBurstTests(unittest.TestCase):
    def test_dry_run_uses_frozen_window_and_disclaims_continuity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "burst.json"
            result = burst.main(
                [
                    "--test-run-id",
                    "ft001b-unit",
                    "--window-count",
                    "2",
                    "--output",
                    str(output),
                ]
            )
            record = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(result, 0)
        self.assertEqual(record["planned_sample_count_per_window"], 100)
        self.assertEqual(record["planned_total_samples"], 200)
        self.assertEqual(len(record["command_id_namespace"]), 10)
        self.assertTrue(all(len(row["cmd_id"]) <= 16 for row in record["results"]))
        self.assertIn("discrete", record["honesty_note"])
        self.assertIn("not continuous IMU acceptance", record["honesty_note"])

    def test_variable_window_is_rejected_before_output_or_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "burst.json"
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                result = burst.main(
                    [
                        "--test-run-id",
                        "ft001b-unit",
                        "--sample-count",
                        "300",
                        "--execute",
                        "--output",
                        str(output),
                    ]
                )

            output_exists = output.exists()

        self.assertEqual(result, 2)
        self.assertFalse(output_exists)
        self.assertIn("sample-count must be exactly 100", stderr.getvalue())

    def test_invalid_execution_input_is_rejected_before_token_or_hub(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "burst.json"
            stderr = io.StringIO()
            with (
                contextlib.redirect_stderr(stderr),
                mock.patch.object(
                    burst,
                    "load_token",
                    side_effect=AssertionError("invalid input attempted token access"),
                ),
                mock.patch.object(
                    burst,
                    "HubClient",
                    side_effect=AssertionError("invalid input attempted a Hub connection"),
                ),
            ):
                result = burst.main(
                    [
                        "--test-run-id",
                        "bad id",
                        "--execute",
                        "--output",
                        str(output),
                    ]
                )

        self.assertEqual(result, 2)
        self.assertFalse(output.exists())
        self.assertIn("test-run-id must be 1..32 safe characters", stderr.getvalue())

    def test_command_ids_are_globally_namespaced_per_field_session(self) -> None:
        namespace_a, ids_a = burst.make_command_ids(
            cmd_prefix="ftb",
            test_run_id="ft001b-repeatable",
            field_session_id="FS-20260823T080000Z-aaaaaaaaaaaa",
            window_count=10,
        )
        namespace_b, ids_b = burst.make_command_ids(
            cmd_prefix="ftb",
            test_run_id="ft001b-repeatable",
            field_session_id="FS-20260823T080001Z-bbbbbbbbbbbb",
            window_count=10,
        )

        self.assertNotEqual(namespace_a, namespace_b)
        self.assertTrue(set(ids_a).isdisjoint(ids_b))
        self.assertTrue(all(burst.CMD_ID_RE.fullmatch(cmd_id) for cmd_id in ids_a + ids_b))

    def test_execute_partial_window_set_is_not_reported_as_completed(self) -> None:
        class FakeClient:
            def __init__(self, *_args, **_kwargs):
                pass

            def post(self, path, payload):
                if path == "/api/v1/test-runs":
                    return {"test_run": {"test_run_id": payload["test_run_id"]}}
                return {
                    "command": {
                        "cmd_id": payload["cmd_id"],
                        "status": "pending",
                    }
                }

        evidence = {
            "window_id": "window-001",
            "boot_count": 7,
            "capture_start_uptime_us": 1_000_000,
            "capture_end_uptime_us": 5_950_000,
            "cadence": {"mean_interval_us": 50000},
            "cadence_quality_status": "valid",
            "samples_crc32": "AABBCCDD",
        }
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "burst.json"
            with (
                mock.patch.object(burst, "HubClient", FakeClient),
                mock.patch.object(burst, "_wait_for_ack", return_value={"status": "ok"}),
                mock.patch.object(
                    burst,
                    "_wait_for_window",
                    side_effect=[evidence, burst.CaptureSessionError("second window missing")],
                ),
            ):
                result = burst.main(
                    [
                        "--test-run-id",
                        "ft001b-partial",
                        "--window-count",
                        "2",
                        "--inter-window-delay-sec",
                        "0",
                        "--execute",
                        "--output",
                        str(output),
                    ]
                )
            record = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(result, 2)
        self.assertEqual(record["status"], "partial")
        self.assertEqual(record["completed_window_count"], 1)
        self.assertEqual(record["failed_window_count"], 1)
        self.assertEqual(record["completion_ratio"], 0.5)
        self.assertTrue(record["boot_scope_consistent"])
        self.assertFalse(record["ft001b_imu_requirement_ready"])

    def test_three_good_windows_satisfy_imu_minimum_even_if_later_window_fails(self) -> None:
        class FakeClient:
            def __init__(self, *_args, **_kwargs):
                pass

            def post(self, path, payload):
                if path == "/api/v1/test-runs":
                    return {"test_run": {"test_run_id": payload["test_run_id"]}}
                return {"command": {"cmd_id": payload["cmd_id"], "status": "pending"}}

        evidence = {
            "window_id": "window-001",
            "boot_count": 7,
            "capture_start_uptime_us": 1_000_000,
            "capture_end_uptime_us": 5_950_000,
            "cadence": {"mean_interval_us": 50000},
            "cadence_quality_status": "valid",
            "samples_crc32": "AABBCCDD",
        }
        good_windows = [
            {
                **evidence,
                "window_id": f"window-{index:03d}",
                "capture_start_uptime_us": 1_000_000 + index * 10_000_000,
                "capture_end_uptime_us": 5_950_000 + index * 10_000_000,
            }
            for index in range(1, 4)
        ]
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "burst.json"
            with (
                mock.patch.object(burst, "HubClient", FakeClient),
                mock.patch.object(burst, "_wait_for_ack", return_value={"status": "ok"}),
                mock.patch.object(
                    burst,
                    "_wait_for_window",
                    side_effect=[
                        *good_windows,
                        burst.CaptureSessionError("fourth window missing"),
                    ],
                ),
            ):
                result = burst.main(
                    [
                        "--test-run-id",
                        "ft001b-minimum",
                        "--window-count",
                        "4",
                        "--inter-window-delay-sec",
                        "0",
                        "--execute",
                        "--output",
                        str(output),
                    ]
                )
            record = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(result, 2)
        self.assertEqual(record["status"], "partial")
        self.assertEqual(record["completed_window_count"], 3)
        self.assertEqual(record["failed_window_count"], 1)
        self.assertTrue(record["boot_scope_consistent"])
        self.assertTrue(record["ft001b_imu_requirement_ready"])
        self.assertFalse(record["ft001b_acceptance"])

    def test_execute_rejects_windows_that_cross_boot_scope(self) -> None:
        class FakeClient:
            def __init__(self, *_args, **_kwargs):
                pass

            def post(self, path, payload):
                if path == "/api/v1/test-runs":
                    return {"test_run": {"test_run_id": payload["test_run_id"]}}
                return {"command": {"cmd_id": payload["cmd_id"], "status": "pending"}}

        evidence = {
            "window_id": "window-001",
            "boot_count": 7,
            "capture_start_uptime_us": 1_000_000,
            "capture_end_uptime_us": 5_950_000,
            "cadence": {"mean_interval_us": 50000},
            "cadence_quality_status": "valid",
            "samples_crc32": "AABBCCDD",
        }
        rebooted = {**evidence, "window_id": "window-002", "boot_count": 8}
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "burst.json"
            with (
                mock.patch.object(burst, "HubClient", FakeClient),
                mock.patch.object(burst, "_wait_for_ack", return_value={"status": "ok"}),
                mock.patch.object(burst, "_wait_for_window", side_effect=[evidence, rebooted]),
            ):
                result = burst.main(
                    [
                        "--test-run-id",
                        "ft001b-cross-boot",
                        "--window-count",
                        "2",
                        "--inter-window-delay-sec",
                        "0",
                        "--execute",
                        "--output",
                        str(output),
                    ]
                )
            record = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(result, 2)
        self.assertEqual(record["status"], "partial")
        self.assertEqual(record["observed_boot_count"], 7)
        self.assertFalse(record["boot_scope_consistent"])
        self.assertFalse(record["ft001b_imu_requirement_ready"])
        self.assertIn("crossed device boots", record["results"][1]["error"])


if __name__ == "__main__":
    unittest.main()

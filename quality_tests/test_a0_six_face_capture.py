from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from quality_tests.test_imu_capture_session import raw_window
from scripts import run_a0_six_face_capture as capture


DEVICE_ID = "ego-link-a0001-unit"
TEST_RUN_ID = "A0-001-UNIT-001"
TRANSPORT = "wifi"


class FakeHub:
    def __init__(self, *, existing_test_runs: list[dict] | None = None) -> None:
        self.test_runs = list(existing_test_runs or [])
        self.events: list[str] = []
        self.current_cmd: str | None = None
        self.completed: list[str] = []

    def post(self, path: str, payload: dict) -> dict:
        if path == "/api/v1/test-runs":
            self.events.append("post:test-run")
            self.test_runs.append(dict(payload))
            return {"ok": True, "test_run": dict(payload)}
        self.current_cmd = payload["cmd_id"]
        self.events.append(f"post:{payload['cmd_id']}")
        return {"command": {**payload, "status": "pending"}}

    def get(self, path: str) -> dict:
        if path == "/api/v1/test-runs":
            self.events.append("get:test-runs")
            return {"test_runs": self.test_runs}
        assert self.current_cmd is not None
        cmd_id = self.current_cmd
        if path.endswith("/commands"):
            return {
                "commands": [
                    {
                        "cmd_id": cmd_id,
                        "status": "ok",
                        "ack": {
                            "cmd_id": cmd_id,
                            "status": "ok",
                            "test_run_id": TEST_RUN_ID,
                            "transport": {"type": TRANSPORT},
                            "command": {"duplicate_local_execution_prevented": False},
                        },
                    }
                ]
            }
        frames = raw_window(cmd_id, TEST_RUN_ID, len(self.completed) + 1, transport_type=TRANSPORT)
        self.completed.append(cmd_id)
        return {"raw_frames": frames}


def run(**overrides):
    kwargs = {
        "pose": "z_positive",
        "cmd_id": "a0001-zp",
        "device_id": DEVICE_ID,
        "test_run_id": TEST_RUN_ID,
        "transport_type": TRANSPORT,
        "sleep_fn": lambda _seconds: None,
    }
    kwargs.update(overrides)
    return capture.capture_pose(**kwargs)


class A0SixFaceCaptureTests(unittest.TestCase):
    def test_dry_run_never_contacts_the_device(self) -> None:
        hub = FakeHub()
        record = run(client=hub)

        self.assertEqual(record["mode"], "dry_run")
        self.assertEqual(record["status"], "dry_run_ready")
        self.assertEqual(hub.events, [])
        self.assertEqual(record["external_actions"], [])
        self.assertFalse(record["operator_confirmed_stationary"])
        self.assertFalse(record["hardware_gate_passed"])
        self.assertIsNone(record["hub_url"])

    def test_one_invocation_creates_exactly_one_bounded_command(self) -> None:
        hub = FakeHub(existing_test_runs=[{"test_run_id": TEST_RUN_ID, "device_id": DEVICE_ID}])
        record = run(execute=True, client=hub)

        self.assertEqual(record["status"], "completed")
        self.assertEqual([event for event in hub.events if event.startswith("post:")], ["post:a0001-zp"])
        self.assertEqual(record["command"], {"cmd": "capture_imu_window", "sample_count": 100, "interval_ms": 50})
        self.assertTrue(record["test_run_reused"])
        self.assertFalse(record["test_run_created"])
        self.assertFalse(record["training_allowed"])
        self.assertFalse(record["production_ready"])
        self.assertFalse(record["hardware_gate_passed"])

    def test_later_poses_reuse_the_calibration_test_run_instead_of_recreating_it(self) -> None:
        hub = FakeHub()
        first = run(execute=True, client=hub, create_test_run=True, pose="x_positive", cmd_id="a0001-xp")
        second = run(execute=True, client=hub, pose="x_negative", cmd_id="a0001-xn")

        self.assertEqual(first["status"], "completed")
        self.assertEqual(second["status"], "completed")
        self.assertTrue(first["test_run_created"])
        self.assertTrue(second["test_run_reused"])
        self.assertFalse(second["test_run_created"])
        self.assertEqual(hub.events.count("post:test-run"), 1)
        self.assertEqual(len(hub.test_runs), 1)

    def test_missing_test_run_without_explicit_creation_fails_closed(self) -> None:
        hub = FakeHub()
        record = run(execute=True, client=hub)

        self.assertEqual(record["status"], "failed")
        self.assertIn("--create-test-run", record["error"])
        self.assertEqual([event for event in hub.events if event.startswith("post:")], [])

    def test_test_run_bound_to_another_device_fails_closed(self) -> None:
        hub = FakeHub(existing_test_runs=[{"test_run_id": TEST_RUN_ID, "device_id": "some-other-device"}])
        record = run(execute=True, client=hub)

        self.assertEqual(record["status"], "failed")
        self.assertIn("bound to device", record["error"])
        self.assertEqual([event for event in hub.events if event.startswith("post:")], [])

    def test_pose_and_command_identifiers_are_validated(self) -> None:
        with self.assertRaisesRegex(capture.SixFaceCaptureError, "pose must be one of"):
            run(pose="x_diagonal")
        with self.assertRaisesRegex(capture.SixFaceCaptureError, "cmd_id"):
            run(cmd_id="a" * 17)
        with self.assertRaisesRegex(capture.SixFaceCaptureError, "transport type"):
            run(transport_type="usb")

    def test_existing_pose_record_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir_raw:
            path = Path(temp_dir_raw) / "z_positive.json"
            capture.write_record(path, run())
            with self.assertRaisesRegex(capture.SixFaceCaptureError, "will not be overwritten"):
                capture.write_record(path, run())
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["pose"], "z_positive")

    def test_hub_failure_is_recorded_with_the_token_redacted(self) -> None:
        secret = "super-secret-token"

        class RaisingHub:
            def get(self, path: str) -> dict:
                raise RuntimeError(f"request failed with token {secret}")

        record = run(execute=True, client=RaisingHub(), redaction_values=(secret,))

        self.assertEqual(record["status"], "failed")
        self.assertNotIn(secret, json.dumps(record))
        self.assertIn("[REDACTED]", record["error"])

    def test_every_calibration_pose_is_addressable(self) -> None:
        for pose in capture.SOURCE_ROLES:
            with self.subTest(pose=pose):
                record = run(pose=pose, cmd_id=f"a0001-{pose[:6]}")
                self.assertEqual(record["pose"], pose)
                self.assertEqual(record["task_id"], "A0-001")


if __name__ == "__main__":
    unittest.main()

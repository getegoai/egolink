from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from pc_simulator.imu_pose_quality import analyze_pose_quality, format_pose_markdown
from pc_simulator.imu_quality import load_jsonl


def _fixture_messages(
    accel_mg: list[int],
    *,
    gyro_mdps: list[int] | None = None,
    samples: int = 50,
    source_status: str = "unverified",
) -> list[dict]:
    gyro_mdps = gyro_mdps or [100, 200, -100]
    messages: list[dict] = [
        {
            "type": "hello",
            "device_id": "wearable-node-001",
            "role": "wearable_node",
            "seq": 1,
        },
        {
            "type": "imu_whoami",
            "device_id": "wearable-node-001",
            "role": "wearable_node",
            "seq": 2,
            "device_monotonic_ms": 1000,
            "sensor_kind": "imu",
            "sensor_model": "QMI8658",
            "source_availability": "bridge_uplink",
            "source_status": source_status,
            "sample_hz": 20,
            "payload": {
                "axp2101_present": True,
                "axp2101_chip_id": 74,
                "qmi8658_addr": 107,
                "whoami": 5,
                "whoami_expected": 5,
            },
        },
    ]
    for index in range(samples):
        jitter = -1 if index % 2 else 1
        messages.append(
            {
                "type": "imu_sample",
                "device_id": "wearable-node-001",
                "role": "wearable_node",
                "seq": index + 3,
                "device_monotonic_ms": 1100 + index * 50,
                "sensor_kind": "imu",
                "sensor_model": "QMI8658",
                "source_availability": "bridge_uplink",
                "source_status": source_status,
                "sample_hz": 20,
                "payload": {
                    "sample_index": index,
                    "qmi_timestamp": 100 + index * 45,
                    "status0": 1,
                    "status_int": 0,
                    "accel_mg": [accel_mg[0] + jitter, accel_mg[1], accel_mg[2] - jitter],
                    "gyro_mdps": gyro_mdps,
                    "raw_accel": [0, 0, 0],
                    "raw_gyro": [0, 0, 0],
                    "temp_raw": 10350,
                },
            }
        )
    messages.append(
        {
            "type": "amoled_bridge_done",
            "device_id": "wearable-node-001",
            "role": "wearable_node",
            "seq": samples + 3,
            "device_monotonic_ms": 1100 + samples * 50,
            "payload": {
                "samples_requested": samples,
                "samples_emitted": samples,
                "read_errors": 0,
                "not_ready_count": 0,
                "sample_interval_ms": 50,
            },
        }
    )
    return messages


class ImuPoseQualityTests(unittest.TestCase):
    def test_three_static_poses_pass_pose_quality_but_not_formal_acceptance(self) -> None:
        report = analyze_pose_quality(
            {
                "z_negative": _fixture_messages([40, 20, -1005]),
                "x_positive": _fixture_messages([1000, 30, -10]),
                "y_positive": _fixture_messages([20, 1002, 15]),
            }
        )

        self.assertTrue(report["quality_gates_passed"])
        self.assertTrue(report["gates"]["pose_or_motion_evidence"]["passed"])
        self.assertTrue(report["gates"]["pose_label_match"]["passed"])
        self.assertFalse(report["formal_imu_acceptance"])
        self.assertIn("source_status_unverified", report["formal_imu_acceptance_reasons"])

    def test_single_static_pose_fails_coverage_without_motion_window(self) -> None:
        report = analyze_pose_quality({"z_negative": _fixture_messages([55, 25, -1025])})

        self.assertFalse(report["quality_gates_passed"])
        self.assertFalse(report["gates"]["pose_count"]["passed"])
        self.assertFalse(report["gates"]["axis_coverage"]["passed"])
        self.assertIn("multi_pose_coverage_incomplete", report["formal_imu_acceptance_reasons"])
        self.assertIn("motion_window_missing", report["formal_imu_acceptance_reasons"])

    def test_mislabeled_pose_fails_label_match(self) -> None:
        report = analyze_pose_quality({"x_positive": _fixture_messages([55, 25, -1025])})

        self.assertFalse(report["quality_gates_passed"])
        self.assertFalse(report["gates"]["pose_label_match"]["passed"])
        self.assertEqual(report["pose_reports"]["x_positive"]["dominant_axis"]["axis"], "z")
        self.assertEqual(report["pose_reports"]["x_positive"]["dominant_axis"]["sign"], "negative")

    def test_motion_window_can_satisfy_motion_evidence(self) -> None:
        motion = _fixture_messages([0, 0, -1000], samples=40)
        for index, event in enumerate(message for message in motion if message.get("type") == "imu_sample"):
            event["payload"]["gyro_mdps"] = [30000 if index % 2 == 0 else -30000, 100, 100]

        report = analyze_pose_quality(
            {"z_negative": _fixture_messages([55, 25, -1025])},
            motion_messages=motion,
        )

        self.assertFalse(report["quality_gates_passed"])
        self.assertTrue(report["gates"]["motion_sanity"]["passed"])
        self.assertTrue(report["gates"]["pose_or_motion_evidence"]["passed"])
        self.assertFalse(report["gates"]["pose_count"]["passed"])

    def test_markdown_and_jsonl_loading(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "z_negative.jsonl"
            path.write_text(
                "\n".join(json.dumps(message) for message in _fixture_messages([55, 25, -1025])),
                encoding="utf-8",
            )
            messages = load_jsonl(path)
            report = analyze_pose_quality({"z_negative": messages})
            markdown = format_pose_markdown(report, {"z_negative": path})

        self.assertIn("# TIMU-004 QMI8658 Pose Quality Report", markdown)
        self.assertIn("| `z_negative` |", markdown)
        self.assertIn("| `pose_count` | FAIL |", markdown)


if __name__ == "__main__":
    unittest.main()

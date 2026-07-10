from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from pc_simulator import imu_calibration


def raw_pose_messages(accel_mg: list[int], *, samples: int = 50) -> list[dict]:
    messages: list[dict] = []
    for index in range(samples):
        messages.append(
            {
                "type": "imu_sample",
                "seq": index + 1,
                "device_monotonic_ms": index * 50,
                "source_availability": "bridge_uplink",
                "source_status": "unverified",
                "payload": {
                    "accel_mg": accel_mg,
                    "gyro_mdps": [100, 200, -100],
                },
            }
        )
    return messages


def sample_pose_quality_report() -> dict:
    def pose(label: str, axis: str, sign: str, mean_axes: list[float], offset: list[float]) -> dict:
        return {
            "label": label,
            "expected_pose": {"axis": axis, "sign": sign},
            "sample_count": 115,
            "mean_axes_mg": mean_axes,
            "axis_stddev_mg": [1.0, 1.0, 1.0],
            "dominant_axis": {
                "axis": axis,
                "sign": sign,
                "mean_mg": mean_axes[("x", "y", "z").index(axis)],
            },
            "accel_magnitude_mg": {"mean": 1030.0},
            "gyro_abs_mdps": {"mean": 900.0},
            "calibration_offset_mg": offset,
            "static_passed": True,
            "label_match": True,
            "calibration_offset_passed": True,
        }

    return {
        "schema_version": "egolink.imu_pose_quality_report.v0.1",
        "pose_count": 3,
        "pose_reports": {
            "z_negative": pose("z_negative", "z", "negative", [56.6, 23.0, -1030.5], [56.6, 23.0, -30.5]),
            "x_positive": pose("x_positive", "x", "positive", [1032.0, 22.0, -18.0], [32.0, 22.0, -18.0]),
            "y_positive": pose("y_positive", "y", "positive", [55.0, 1031.0, -20.0], [55.0, 31.0, -20.0]),
        },
        "motion_report": None,
        "gates": {
            "source_boundary": {
                "passed": True,
                "reason": "source remains bridge_uplink/unverified until formal acceptance",
            }
        },
        "quality_gates_passed": True,
        "formal_imu_acceptance": False,
        "formal_imu_acceptance_reasons": ["source_status_unverified"],
    }


class ImuCalibrationTests(unittest.TestCase):
    def test_engineering_profile_is_not_production_ready(self) -> None:
        profile = imu_calibration.build_engineering_calibration_profile(
            sample_pose_quality_report(),
            profile_id="timu009a-qmi8658-engineering",
            hardware_profile="esp32-s3-touch-amoled-2.06-qmi8658",
            source_report="pose_quality.json",
            generated_at="2026-06-24T00:00:00+00:00",
        )

        self.assertEqual(profile["schema_version"], imu_calibration.PROFILE_SCHEMA_VERSION)
        self.assertEqual(profile["stage"], "engineering")
        self.assertTrue(profile["usable_for_engineering"])
        self.assertFalse(profile["production_ready"])
        self.assertFalse(profile["formal_imu_acceptance"])
        self.assertIn("imu_mounting_position_change", profile["recalibration_required_after"])
        self.assertIn("production_calibration", profile["boundary"]["must_not_use_for"])
        self.assertIn("motionnet_training", profile["boundary"]["must_not_use_for"])

    def test_profile_contains_axis_map_and_conservative_offset(self) -> None:
        profile = imu_calibration.build_engineering_calibration_profile(
            sample_pose_quality_report(),
            profile_id="timu009a-qmi8658-engineering",
            hardware_profile="esp32-s3-touch-amoled-2.06-qmi8658",
            source_report="pose_quality.json",
            generated_at="2026-06-24T00:00:00+00:00",
        )

        self.assertEqual(profile["axis_map"]["x"]["measured_axis"], "x")
        self.assertEqual(profile["axis_map"]["y"]["measured_axis"], "y")
        self.assertEqual(profile["axis_map"]["z"]["measured_axis"], "z")
        self.assertEqual(profile["axis_map"]["x"]["sign"], 1)
        offset = profile["accel_calibration"]["offset_mg_xyz"]
        self.assertAlmostEqual(offset[0], (56.6 + 32.0 + 55.0) / 3.0)
        self.assertAlmostEqual(offset[1], (23.0 + 22.0 + 31.0) / 3.0)
        self.assertAlmostEqual(offset[2], (-30.5 - 18.0 - 20.0) / 3.0)
        self.assertIsNone(profile["accel_calibration"]["scale_matrix"])
        self.assertIsNone(profile["gyro_calibration"]["bias_mdps_xyz"])

    def test_cli_writes_json_and_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report_path = root / "pose_quality.json"
            json_path = root / "calibration.json"
            markdown_path = root / "calibration.md"
            report_path.write_text(json.dumps(sample_pose_quality_report()), encoding="utf-8")

            exit_code = imu_calibration.main(
                [
                    "--pose-quality-json",
                    str(report_path),
                    "--profile-id",
                    "timu009a-qmi8658-engineering",
                    "--hardware-profile",
                    "esp32-s3-touch-amoled-2.06-qmi8658",
                    "--output-json",
                    str(json_path),
                    "--markdown",
                    str(markdown_path),
                ]
            )

            self.assertEqual(exit_code, 0)
            profile = json.loads(json_path.read_text(encoding="utf-8"))
            markdown = markdown_path.read_text(encoding="utf-8")
            self.assertFalse(profile["production_ready"])
            self.assertIn("# TIMU-009A IMU Engineering Calibration Profile", markdown)
            self.assertIn("engineering", markdown)
            self.assertIn("Production ready: `False`", markdown)

    def test_cli_can_analyze_raw_pose_jsonl_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pose_paths = {
                "z_negative": root / "z.jsonl",
                "x_positive": root / "x.jsonl",
                "y_positive": root / "y.jsonl",
            }
            fixtures = {
                "z_negative": raw_pose_messages([50, 20, -1020]),
                "x_positive": raw_pose_messages([1020, 20, -20]),
                "y_positive": raw_pose_messages([20, 1020, -20]),
            }
            for label, path in pose_paths.items():
                path.write_text(
                    "\n".join(json.dumps(row) for row in fixtures[label]) + "\n",
                    encoding="utf-8",
                )
            json_path = root / "calibration.json"

            exit_code = imu_calibration.main(
                [
                    "--pose",
                    f"z_negative={pose_paths['z_negative']}",
                    "--pose",
                    f"x_positive={pose_paths['x_positive']}",
                    "--pose",
                    f"y_positive={pose_paths['y_positive']}",
                    "--profile-id",
                    "raw-pose-engineering",
                    "--hardware-profile",
                    "esp32-s3-touch-amoled-2.06-qmi8658",
                    "--output-json",
                    str(json_path),
                ]
            )

            self.assertEqual(exit_code, 0)
            profile = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertTrue(profile["usable_for_engineering"])
            self.assertFalse(profile["production_ready"])
            self.assertEqual(set(profile["axis_map"]), {"x", "y", "z"})


if __name__ == "__main__":
    unittest.main()

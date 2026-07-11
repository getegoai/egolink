from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from scripts import assess_motion_data_readiness as readiness


def sensor_message(timestamp: datetime, seq: int, *, mock: bool = False) -> dict[str, object]:
    return {
        "message_type": "event",
        "event_type": "sensor_sample",
        "device_id": "private-device-unit",
        "seq": seq,
        "server_received_at": timestamp.isoformat(),
        "imu_hardware_present": True,
        "imu_driver_enabled": True,
        "imu_sample_mock": mock,
        "imu_accel_mg_x": 1,
        "imu_accel_mg_y": 2,
        "imu_accel_mg_z": 1000,
        "imu_gyro_mdps_x": 3,
        "imu_gyro_mdps_y": 4,
        "imu_gyro_mdps_z": 5,
    }


def speed_message(timestamp: datetime, seq: int, speed: float) -> dict[str, object]:
    return {
        "message_type": "event",
        "event_type": "location_report",
        "device_id": "private-device-unit",
        "seq": seq,
        "server_received_at": timestamp.isoformat(),
        "fix": True,
        "speed_mps": speed,
        "hdop": 1.2,
        "lat": 31.123456,
        "lon": 121.654321,
    }


class MotionDataReadinessTests(unittest.TestCase):
    def test_real_high_rate_samples_and_speed_coverage_can_pass_export_gate(self) -> None:
        start = datetime(2026, 7, 11, tzinfo=timezone.utc)
        messages: list[dict[str, object]] = []
        for index in range(60):
            messages.append(sensor_message(start + timedelta(milliseconds=50 * index), index + 1))
        messages.extend(
            [
                speed_message(start, 1001, 0.0),
                speed_message(start + timedelta(seconds=2), 1002, 0.1),
            ]
        )
        moving_start = start + timedelta(minutes=10)
        for index in range(60):
            messages.append(sensor_message(moving_start + timedelta(milliseconds=50 * index), index + 101))
        messages.extend(
            [
                speed_message(moving_start, 1003, 3.0),
                speed_message(moving_start + timedelta(seconds=2), 1004, 3.2),
            ]
        )
        report = readiness.build_report(
            {"window": {"complete": True}, "messages": messages},
            run_id="motion-unit",
            created_at="2026-07-11T00:00:00+00:00",
        )

        self.assertEqual(report["status"], "PASS")
        self.assertTrue(report["result"]["ready_for_motion_dataset_export"])
        self.assertFalse(report["result"]["training_allowed"])
        self.assertFalse(report["result"]["three_class_labels_ready"])
        self.assertEqual(report["metrics"]["real_imu_sample_count"], 120)
        self.assertEqual(report["metrics"]["observed_imu_metadata_count"], 120)
        self.assertEqual(report["metrics"]["weak_label_counts"]["stationary_candidate"], 60)
        self.assertEqual(report["metrics"]["weak_label_counts"]["moving_candidate"], 60)
        self.assertFalse(report["label_boundary"]["walking_or_vehicle_generated"])

    def test_mock_or_sparse_evidence_reports_blockers_without_private_data(self) -> None:
        start = datetime(2026, 7, 11, tzinfo=timezone.utc)
        export = {
            "window": {"complete": True},
            "messages": [
                sensor_message(start, 1, mock=True),
                speed_message(start, 2, 2.5),
            ],
        }
        report = readiness.build_report(
            export,
            run_id="motion-private-unit",
            created_at="2026-07-11T00:00:00+00:00",
        )
        payload = json.dumps(report)

        self.assertEqual(report["status"], "WARN")
        self.assertEqual(report["metrics"]["real_imu_sample_count"], 0)
        self.assertEqual(report["metrics"]["mock_imu_metadata_count"], 1)
        self.assertIn("insufficient_real_imu_samples", report["result"]["blockers"])
        self.assertNotIn("private-device-unit", payload)
        self.assertNotIn("31.123456", payload)
        self.assertNotIn("121.654321", payload)
        self.assertFalse(report["scope"]["raw_coordinates_written"])
        self.assertFalse(report["scope"]["training_rows_written"])

    def test_cli_writes_aggregate_one_page_report(self) -> None:
        start = datetime(2026, 7, 11, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "field-export.json"
            input_path.write_text(
                json.dumps(
                    {
                        "window": {"complete": True},
                        "messages": [sensor_message(start, 1, mock=True)],
                    }
                ),
                encoding="utf-8",
            )
            output_dir = root / "output"
            exit_code = readiness.main(
                [
                    "--input-export",
                    str(input_path),
                    "--run-id",
                    "motion-cli-unit",
                    "--created-at",
                    "2026-07-11T00:00:00+00:00",
                    "--output-dir",
                    str(output_dir),
                ]
            )
            report = json.loads((output_dir / readiness.REPORT_JSON).read_text(encoding="utf-8"))
            markdown = (output_dir / readiness.REPORT_MARKDOWN).read_text(encoding="utf-8")

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["status"], "WARN")
        self.assertIn("GNSS speed does not generate walking or vehicle ground truth", markdown)
        self.assertLessEqual(len(markdown.splitlines()), 30)

    def test_incomplete_export_is_rejected(self) -> None:
        with self.assertRaises(readiness.MotionDataReadinessError):
            readiness.build_report(
                {"window": {"complete": False}, "messages": []},
                run_id="motion-incomplete",
                created_at="2026-07-11T00:00:00+00:00",
            )

    def test_nested_imu_mock_state_is_authoritative(self) -> None:
        metadata = readiness.imu_metadata(
            {
                "imu_sample_mock": False,
                "imu": {
                    "data_is_mock": True,
                    "source_status": "unverified",
                    "evidence_status": "mock",
                },
            }
        )
        self.assertIsNotNone(metadata)
        self.assertTrue(metadata["mock"])
        self.assertFalse(metadata["observed"])


if __name__ == "__main__":
    unittest.main()

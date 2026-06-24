from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from pc_simulator.imu_quality import analyze_imu_messages, format_markdown, load_jsonl


def _fixture_messages(
    interval_ms: int = 50,
    source_status: str = "unverified",
    sample_count: int = 40,
    stationary: bool = True,
    jitter_at: int | None = None,
    jitter_ms: int = 0,
) -> list[dict]:
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
                "revision": 124,
                "reset_result": 128,
            },
        },
    ]
    for index in range(sample_count):
        monotonic_ms = 1100 + index * interval_ms
        if jitter_at is not None and index >= jitter_at:
            monotonic_ms += jitter_ms
        accel = [55, 25, -1025] if stationary else [55 + (index % 9) * 45, 25, -880 + (index % 5) * 80]
        gyro = [100, 900, -100] if stationary else [10000 + index * 10, 35000, -18000]
        messages.append(
            {
                "type": "imu_sample",
                "device_id": "wearable-node-001",
                "role": "wearable_node",
                "seq": index + 3,
                "device_monotonic_ms": monotonic_ms,
                "sensor_kind": "imu",
                "sensor_model": "QMI8658",
                "source_availability": "bridge_uplink",
                "source_status": source_status,
                "sample_hz": 20,
                "payload": {
                    "sample_index": index,
                    "qmi_timestamp": 100 + index * 50,
                    "status0": 1,
                    "status_int": 0,
                    "accel_mg": accel,
                    "gyro_mdps": gyro,
                    "raw_accel": [450, 205, -8400],
                    "raw_gyro": [6, 57, -6],
                    "temp_raw": 10350,
                },
            }
        )
    messages.append(
        {
            "type": "amoled_bridge_done",
            "device_id": "wearable-node-001",
            "role": "wearable_node",
            "seq": sample_count + 3,
            "device_monotonic_ms": 1100 + sample_count * interval_ms,
            "payload": {
                "samples_requested": sample_count,
                "samples_emitted": sample_count,
                "read_errors": 0,
                "not_ready_count": 0,
                "sample_interval_ms": 50,
                "requested_window_ms": sample_count * 50,
            },
        }
    )
    return messages


class ImuQualityTests(unittest.TestCase):
    def test_stable_static_capture_passes_quality_gates_but_not_formal_acceptance(self) -> None:
        report = analyze_imu_messages(_fixture_messages())

        self.assertTrue(report["quality_gates_passed"])
        self.assertFalse(report["formal_imu_acceptance"])
        self.assertIn("source_status_unverified", report["formal_imu_acceptance_reasons"])
        self.assertEqual(report["static_orientation"]["dominant_axis"]["axis"], "z")
        self.assertEqual(report["static_orientation"]["dominant_axis"]["sign"], "negative")

    def test_timing_gate_fails_when_observed_period_drifts_from_request(self) -> None:
        report = analyze_imu_messages(_fixture_messages(interval_ms=82))

        self.assertFalse(report["quality_gates_passed"])
        self.assertFalse(report["gates"]["device_timing"]["passed"])
        self.assertIn("device_timing_gate_failed", report["formal_imu_acceptance_reasons"])
        self.assertIn("device_jitter_gate_failed", report["formal_imu_acceptance_reasons"])

    def test_long_window_mode_ignores_static_pose_gates_but_checks_timing(self) -> None:
        report = analyze_imu_messages(
            _fixture_messages(sample_count=600, stationary=False),
            min_samples=500,
            require_static=False,
            max_interval_jitter_ms=25.0,
        )

        self.assertEqual(report["analysis_mode"], "long_window_timing")
        self.assertTrue(report["quality_gates_passed"])
        self.assertFalse(report["gates"]["static_orientation"]["passed"])
        self.assertFalse(report["gates"]["static_gyro"]["passed"])
        self.assertTrue(report["gates"]["device_jitter"]["passed"])
        self.assertEqual(report["message_counts"]["imu_sample"], 600)

    def test_long_window_jitter_gate_fails_on_interval_spike(self) -> None:
        report = analyze_imu_messages(
            _fixture_messages(sample_count=80, stationary=False, jitter_at=30, jitter_ms=80),
            min_samples=80,
            require_static=False,
            max_interval_jitter_ms=25.0,
        )

        self.assertFalse(report["quality_gates_passed"])
        self.assertFalse(report["gates"]["device_jitter"]["passed"])
        self.assertIn("device_jitter_gate_failed", report["formal_imu_acceptance_reasons"])

    def test_source_status_verified_is_rejected_at_boundary(self) -> None:
        report = analyze_imu_messages(_fixture_messages(source_status="verified"))

        self.assertFalse(report["quality_gates_passed"])
        self.assertFalse(report["gates"]["source_boundary"]["passed"])
        self.assertFalse(report["formal_imu_acceptance"])

    def test_load_jsonl_and_markdown_report(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "capture.jsonl"
            path.write_text(
                "\n".join(json.dumps(message) for message in _fixture_messages()),
                encoding="utf-8",
            )

            report = analyze_imu_messages(load_jsonl(path))
            markdown = format_markdown(report, path)

        self.assertIn("# TIMU-002 QMI8658 Sample Quality Report", markdown)
        self.assertIn("| `identity` | PASS |", markdown)
        self.assertIn("Formal IMU acceptance: `False`", markdown)

    def test_load_jsonl_accepts_windows_utf8_bom_capture(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "capture.jsonl"
            path.write_text(
                "\n".join(json.dumps(message) for message in _fixture_messages()),
                encoding="utf-8-sig",
            )

            report = analyze_imu_messages(load_jsonl(path))

        self.assertTrue(report["quality_gates_passed"])
        self.assertEqual(report["message_counts"]["imu_sample"], 40)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from pathlib import Path
import unittest


class HardwareSensorMatrixTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.matrix_path = self.repo_root / "docs" / "modeling" / "HARDWARE_SENSOR_MATRIX.md"
        self.content = self.matrix_path.read_text(encoding="utf-8")

    def test_matrix_exists_with_m1_scope(self) -> None:
        self.assertTrue(self.matrix_path.is_file())
        self.assertIn("# Ego Link M1 Hardware Sensor Matrix", self.content)
        self.assertIn("M1-001", self.content)
        self.assertIn("M1-002 recorder", self.content)

    def test_key_sensor_statuses_are_explicit(self) -> None:
        required_terms = [
            "ESP32-S3",
            "SIM7670G-MNGV",
            "sensor_sample/device_health",
            "Wi-Fi RSSI",
            "SIM7670G GNSS no-fix",
            "摄像头单帧",
            "IMU",
            "麦克风",
            "物理 SOS 按键",
            "SD / 本地存储",
            "电量/充电",
        ]

        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, self.content)

    def test_unknown_and_mock_boundaries_are_not_hidden(self) -> None:
        required_boundaries = [
            "`missing_or_unknown`",
            "`mock_only`",
            "当前仓库无真实 IMU",
            "当前仓库无真实麦克风",
            "真实按键 GPIO 未验证",
            "battery=87",
            "M0 Safety Companion 是确定性规则基线",
            "不是已验证的真实跌倒、呼救或事故识别模型",
        ]

        for boundary in required_boundaries:
            with self.subTest(boundary=boundary):
                self.assertIn(boundary, self.content)

    def test_evidence_paths_are_traceable(self) -> None:
        evidence_paths = [
            "reports/board_validation/20260621-091239/probe.md",
            "reports/gnss_validation/20260621-161721/gnss_probe.md",
            "firmware/mqtt_heartbeat/main/app_main.c",
            "firmware/camera_smoke/main/app_main.c",
            "firmware/camera_smoke/README.md",
        ]

        for evidence_path in evidence_paths:
            with self.subTest(evidence_path=evidence_path):
                self.assertIn(evidence_path, self.content)


if __name__ == "__main__":
    unittest.main()

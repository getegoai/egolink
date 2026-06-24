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
        self.assertIn("HCTX-001", self.content)
        self.assertIn("M1-002 recorder", self.content)
        self.assertIn("Waveshare ESP32-S3-SIM7670G-4G", self.content)

    def test_key_sensor_statuses_are_explicit(self) -> None:
        required_terms = [
            "ESP32-S3",
            "SIM7670G-MNGV",
            "sensor_sample/device_health",
            "Wi-Fi RSSI",
            "SIM7670G GNSS no-fix",
            "摄像头多帧 smoke",
            "AMOLED 板 QMI8658 IMU via PC Bridge",
            "IMU",
            "麦克风",
            "物理 SOS 按键",
            "SD / 本地存储",
            "电量/充电",
            "电源控制 / 功耗状态",
            "STM32U5A5",
            "Apollo4",
            "ESP32-P4",
            "Alif B1",
        ]

        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, self.content)

    def test_unknown_and_mock_boundaries_are_not_hidden(self) -> None:
        required_boundaries = [
            "`missing_or_unknown`",
            "`mock_only`",
            "当前 P0 4G 主控板无真实 IMU 证据",
            "当前仓库无真实麦克风",
            "真实按键 GPIO 未验证",
            "battery=87",
            "采购清单和候选平台不等于已到货、已接线或已验证",
            "M0 Safety Companion 是确定性规则基线",
            "不是已验证的真实跌倒、呼救或事故识别模型",
            "48 小时和 5-7 天续航是工程目标",
        ]

        for boundary in required_boundaries:
            with self.subTest(boundary=boundary):
                self.assertIn(boundary, self.content)

    def test_evidence_paths_are_traceable(self) -> None:
        evidence_paths = [
            "docs/hardware/HARDWARE_USABILITY_VALIDATION.md",
            "reports/board_validation/20260622-181619/probe.md",
            "reports/gnss_validation/20260622-181804/gnss_probe.md",
            "pc_simulator/runtime/recordings/t038-hardware-usability-smoke/session_quality_report.md",
            "reports/board_validation/20260621-091239/probe.md",
            "reports/gnss_validation/20260621-161721/gnss_probe.md",
            "firmware/mqtt_heartbeat/main/app_main.c",
            "firmware/camera_smoke/main/app_main.c",
            "firmware/camera_smoke/README.md",
            "docs/hardware/TCAM_001_CAMERA_SMOKE_LIVE_CAPTURE_20260623.md",
            "docs/hardware/HDBRIDGE_001_DUAL_BOARD_PC_BRIDGE_POC_20260623.md",
            "docs/hardware/HDBRIDGE_002_AMOLED_QMI8658_LIVE_CAPTURE_20260623.md",
            "docs/hardware/TIMU_002_QMI8658_SAMPLE_QUALITY_20260623.md",
            "docs/hardware/TIMU_003_QMI8658_TIMING_RETEST_20260623.md",
            "docs/hardware/TIMU_004_QMI8658_POSE_QUALITY_20260623.md",
            "docs/hardware/TIMU_004B_QMI8658_MANUAL_CAPTURE_20260623.md",
            "docs/hardware/TIMU_005_QMI8658_MOTION_WINDOW_20260624.md",
            "docs/hardware/TIMU_006_QMI8658_LONG_WINDOW_20260624.md",
            "docs/hardware/TIMU_007_PLATFORM_IMU_REAL_BACKEND_POC_20260624.md",
            "docs/hardware/TIMU_008_PLATFORM_IMU_QMI_BACKEND_LIVE_CAPTURE_20260624.md",
            "docs/hardware/TIMU_009A_QMI8658_ENGINEERING_CALIBRATION_PROFILE_20260624.md",
            "docs/hardware/TIMU_009A_QMI8658_ENGINEERING_CALIBRATION_PROFILE_20260624.json",
            "docs/hardware/TIMU_009B_QMI8658_PRODUCT_ACCEPTANCE_PREFLIGHT_20260624.md",
            "docs/hardware/TIMU_009B_QMI8658_PRODUCT_ACCEPTANCE_PREFLIGHT_20260624.json",
            "docs/hardware/TIMU_009C_QMI8658_BACKEND_READINESS_CAPTURE_20260624.md",
            "docs/hardware/TIMU_009C_B0_QMI8658_PRODUCT_MOUNTING_EVIDENCE_TEMPLATE_20260624.json",
            "docs/hardware/TIMU_009C_B0_QMI8658_PRODUCT_MOUNTING_EVIDENCE_TEMPLATE_20260624.md",
            "pc_simulator/board_bridge.py",
            "pc_simulator/imu_quality.py",
            "pc_simulator/imu_pose_quality.py",
            "pc_simulator/imu_calibration.py",
            "pc_simulator/imu_acceptance.py",
            "scripts/generate_imu_calibration_profile.py",
            "scripts/check_imu_acceptance.py",
            "scripts/capture_amoled_qmi8658_pose_set.ps1",
            "docs/hardware/EGOLINK_HARDWARE_PLATFORM_CONTEXT.md",
            "docs/hardware/HARDWARE_EVALUATION_AND_PROCUREMENT_PLAN.md",
        ]

        for evidence_path in evidence_paths:
            with self.subTest(evidence_path=evidence_path):
                self.assertIn(evidence_path, self.content)

    def test_hctx_outputs_are_present(self) -> None:
        required_sections = [
            "阻塞 M1 数据采集的缺失硬件或驱动",
            "HARCH-001 应重点审计的耦合点",
            "platform_modem",
            "platform_gnss",
            "platform_power",
            "capability descriptor",
        ]

        for section in required_sections:
            with self.subTest(section=section):
                self.assertIn(section, self.content)


if __name__ == "__main__":
    unittest.main()

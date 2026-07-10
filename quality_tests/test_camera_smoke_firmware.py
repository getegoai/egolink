from __future__ import annotations

from pathlib import Path
import re
import unittest


class CameraSmokeFirmwareTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.app_path = self.repo_root / "firmware" / "camera_smoke" / "main" / "app_main.c"
        self.readme_path = self.repo_root / "firmware" / "camera_smoke" / "README.md"
        self.evidence_path = self.repo_root / "docs" / "hardware" / "TCAM_001_CAMERA_SMOKE_LIVE_CAPTURE_20260623.md"
        self.status_path = self.repo_root / "docs" / "STATUS.md"
        self.matrix_path = self.repo_root / "docs" / "modeling" / "HARDWARE_SENSOR_MATRIX.md"
        self.app = self.app_path.read_text(encoding="utf-8")
        self.readme = self.readme_path.read_text(encoding="utf-8")
        self.evidence = self.evidence_path.read_text(encoding="utf-8")
        self.status = self.status_path.read_text(encoding="utf-8")
        self.matrix = self.matrix_path.read_text(encoding="utf-8")

    def test_waveshare_camera_pin_profile_is_explicit(self) -> None:
        expected_assignments = {
            ".pin_xclk": "39",
            ".pin_sccb_sda": "15",
            ".pin_sccb_scl": "16",
            ".pin_d7": "14",
            ".pin_d6": "13",
            ".pin_d5": "12",
            ".pin_d4": "11",
            ".pin_d3": "10",
            ".pin_d2": "9",
            ".pin_d1": "8",
            ".pin_d0": "7",
            ".pin_vsync": "42",
            ".pin_href": "41",
            ".pin_pclk": "46",
        }

        for field, value in expected_assignments.items():
            with self.subTest(field=field):
                self.assertRegex(self.app, rf"{re.escape(field)}\s*=\s*{value}\s*,")

    def test_startup_capture_sequence_is_bounded_and_catchable(self) -> None:
        required_terms = [
            "#define CAMERA_SMOKE_BOOT_CAPTURE_DELAY_MS 5000",
            "#define CAMERA_SMOKE_CAPTURE_COUNT 3",
            "#define CAMERA_SMOKE_CAPTURE_INTERVAL_MS 3000",
            "CAMERA_SMOKE_CAPTURE_SEQUENCE",
            "capture_startup_sequence();",
        ]

        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, self.app)

    def test_capture_log_contains_verifiable_jpeg_fields(self) -> None:
        required_terms = [
            "CAMERA_SMOKE_CAPTURE_OK capture_index=%",
            "bytes=%u",
            "checksum=%08",
            "width=%u height=%u format=%u",
            "jpeg_soi=%02x%02x",
            "jpeg_eoi=%02x%02x",
            "fnv1a32",
        ]

        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, self.app)

    def test_readme_documents_live_capture_pass_criteria(self) -> None:
        required_terms = [
            "Waits 5 seconds",
            "captures 3 JPEG frames",
            "CAMERA_SMOKE_CAPTURE_SEQUENCE delay_ms=5000 count=3 interval_ms=3000",
            "CAMERA_SMOKE_CAPTURE_OK capture_index=1",
            "CAMERA_SMOKE_CAPTURE_OK capture_index=2",
            "CAMERA_SMOKE_CAPTURE_OK capture_index=3",
            "jpeg_soi=ffd8 jpeg_eoi=ffd9",
        ]

        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, self.readme)

    def test_live_capture_evidence_is_recorded_without_product_claims(self) -> None:
        required_terms = [
            "TCAM-001 Camera Smoke Live Capture",
            "Detected OV5640 camera",
            "CAMERA_SMOKE_INIT_OK profile=waveshare_esp32s3_sim7670g_4g",
            "2893",
            "3708",
            "3700",
            "a5db84d7",
            "94301dec",
            "7a151b26",
            "Current board firmware after this task is `firmware/camera_smoke`",
            "Still not verified: product `mqtt_heartbeat` camera integration",
        ]

        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, self.evidence)

    def test_status_and_matrix_preserve_camera_boundary(self) -> None:
        required_pairs = [
            (self.status, "TCAM-001：摄像头 smoke live capture 完成"),
            (self.status, "当前开发板已从 MQTT heartbeat 固件切换为 camera smoke 固件"),
            (self.matrix, "TCAM-001 camera smoke UART live capture"),
            (self.matrix, "摄像头多帧 smoke"),
            (self.matrix, "当前运行固件是 camera smoke，不是 MQTT heartbeat"),
        ]

        for content, term in required_pairs:
            with self.subTest(term=term):
                self.assertIn(term, content)


if __name__ == "__main__":
    unittest.main()

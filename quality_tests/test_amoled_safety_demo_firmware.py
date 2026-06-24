from __future__ import annotations

from pathlib import Path
import unittest


class AmoledSafetyDemoFirmwareTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.app_dir = self.repo_root / "firmware" / "amoled_safety_demo"
        self.app = (self.app_dir / "main" / "app_main.c").read_text(encoding="utf-8")
        self.manifest = (self.app_dir / "main" / "idf_component.yml").read_text(encoding="utf-8")
        self.readme = (self.app_dir / "README.md").read_text(encoding="utf-8")
        self.sdkconfig = (self.app_dir / "sdkconfig.defaults").read_text(encoding="utf-8")

    def test_uses_waveshare_bsp_and_lvgl_for_visible_prompt(self) -> None:
        required_terms = [
            "waveshare/esp32_s3_touch_amoled_2_06",
            "espressif/esp_lvgl_port",
            'version: "2.3.2"',
            "lvgl/lvgl",
            "bsp_display_start()",
            "lv_button_create",
            "Impact detected",
            "Are you safe?",
            "SAFE",
            "HELP",
        ]
        joined = self.app + "\n" + self.manifest + "\n" + self.readme
        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, joined)

    def test_serial_contract_outputs_hello_render_and_confirmation(self) -> None:
        required_terms = [
            '\\"type\\":\\"hello\\"',
            '\\"role\\":\\"%s\\"',
            "DEMO_ROLE",
            '"0.2"',
            "ask_user_rendered",
            "user_confirmation",
            "response_button_cb",
            '\\"response\\":\\"%s\\"',
            "wearable-node-001",
        ]
        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, self.app)

    def test_readme_keeps_demo_boundary_clear(self) -> None:
        required_terms = [
            "DEMO-002",
            "does not yet run MotionNet",
            "real fall detection",
            "GNSS",
            "4G",
            "merge this UI with the QMI8658 IMU bridge",
            "CJK font",
            "does not compile against LVGL 9.2.0",
        ]
        joined = self.readme + "\n" + self.sdkconfig
        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, joined)


if __name__ == "__main__":
    unittest.main()

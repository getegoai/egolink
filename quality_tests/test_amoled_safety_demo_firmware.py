from __future__ import annotations

from pathlib import Path
import unittest


class AmoledSafetyDemoFirmwareTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.app_dir = self.repo_root / "firmware" / "amoled_safety_demo"
        self.app = (self.app_dir / "main" / "app_main.c").read_text(encoding="utf-8")
        self.cmake = (self.app_dir / "main" / "CMakeLists.txt").read_text(encoding="utf-8")
        self.manifest = (self.app_dir / "main" / "idf_component.yml").read_text(encoding="utf-8")
        self.lock = (self.app_dir / "dependencies.lock").read_text(encoding="utf-8")
        self.readme = (self.app_dir / "README.md").read_text(encoding="utf-8")
        self.sdkconfig = (self.app_dir / "sdkconfig.defaults").read_text(encoding="utf-8")

    def test_uses_waveshare_bsp_and_lvgl_for_visible_prompt(self) -> None:
        required_terms = [
            "waveshare/esp32_s3_touch_amoled_2_06",
            "espressif/esp_lvgl_port",
            'version: "1.0.3"',
            "waveshare/esp_lcd_sh8601",
            'version: "1.0.2"',
            'version: "2.6.0"',
            "lvgl/lvgl",
            "bsp_display_start()",
            "lv_button_create",
            "Impact detected",
            "Are you safe?",
            "SAFE",
            "HELP",
        ]
        joined = self.app + "\n" + self.manifest + "\n" + self.lock + "\n" + self.readme
        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, joined)

    def test_serial_contract_outputs_hello_render_and_confirmation(self) -> None:
        required_terms = [
            '\\"type\\":\\"hello\\"',
            '\\"role\\":\\"%s\\"',
            "DEMO_ROLE",
            '"0.2"',
            "Waiting for PC Bridge",
            "command_reader_task",
            "fgetc(stdin)",
            "command_is_ask_user",
            "command_ack",
            "cmd_id",
            "cJSON_Parse",
            "payload",
            "prompt",
            "severity",
            "ask_user_rendered",
            "status_update",
            "display_status",
            "status_rendered",
            "command_error",
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
            "PC Bridge `ask_user`",
            "status_update",
            "run_amoled_ask_user_demo.ps1",
            "QMI8658 engineering sampler",
            "CJK font",
            "official Waveshare ESP-IDF v5.4.2 LVGL demo set",
            "rendered corrupt frames",
        ]
        joined = self.readme + "\n" + self.sdkconfig
        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, joined)

    def test_serial_contract_outputs_imu_events(self) -> None:
        required_terms = [
            "imu_whoami",
            "imu_sampler_task",
            "qmi8658_demo",
            "motion_event",
            "demo_unverified_heuristic",
            "accel_mg",
            "gyro_mdps",
            "impact_score",
            "fall_score",
            "sensor_kind",
            "sensor_model",
            "imu_source",
            "source_availability",
            "trigger_reason",
            "accel_peak_mg",
            "gyro_peak_mdps",
            "accel_delta_mg",
            "imu_sample",
            "unverified_demo_only",
            '\\"QMI8658\\"',
            '\\"qmi8658_i2c\\"',
            '\\"bridge_uplink\\"',
        ]
        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, self.app)

        import re
        impact_match = re.search(r'\\"impact_score\\":([0-9.]+)', self.app)
        self.assertIsNotNone(impact_match, "Could not find impact_score in app_main.c")
        impact_score = float(impact_match.group(1))
        self.assertTrue(impact_score >= 0.8, f"Impact score {impact_score} is not >= 0.8")

        fall_match = re.search(r'\\"fall_score\\":([0-9.]+)', self.app)
        self.assertIsNotNone(fall_match, "Could not find fall_score in app_main.c")
        fall_score = float(fall_match.group(1))
        self.assertTrue(fall_score >= 0.7, f"Fall score {fall_score} is not >= 0.7")

    def test_amoled_i2c_uses_bsp_new_driver(self) -> None:
        required_terms = [
            "driver/i2c_master.h",
            "bsp_i2c_init()",
            "bsp_i2c_get_handle()",
            "i2c_master_bus_add_device",
            "i2c_master_transmit_receive",
            "i2c_master_transmit",
        ]
        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, self.app)
        self.assertNotIn('#include "driver/i2c.h"', self.app)

    def test_serial_downlink_uses_structured_json_parser(self) -> None:
        required_terms = [
            '#include "cJSON.h"',
            "REQUIRES json",
            "cJSON_Parse(line)",
            "cJSON_Delete(root)",
            "cJSON_GetObjectItemCaseSensitive",
            "json_payload_object",
            "json_string_from_root_or_payload",
            "json_number_from_root_or_payload",
        ]
        joined = self.app + "\n" + self.cmake
        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, joined)

        forbidden_terms = [
            "extract_json_string",
            "strstr(line",
            "strchr(",
        ]
        for term in forbidden_terms:
            with self.subTest(term=term):
                self.assertNotIn(term, self.app)

    def test_no_broken_printf_concatenation(self) -> None:
        # Prevent broken format strings like %\" PRI...
        self.assertNotIn('%\\" PRI', self.app)


if __name__ == "__main__":
    unittest.main()

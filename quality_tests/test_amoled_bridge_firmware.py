from __future__ import annotations

from pathlib import Path
import unittest


class AmoledBridgeFirmwareTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.app_dir = self.repo_root / "firmware" / "amoled_bridge"
        self.app_path = self.app_dir / "main" / "app_main.c"
        self.readme_path = self.app_dir / "README.md"
        self.sdkconfig_defaults_path = self.app_dir / "sdkconfig.defaults"
        self.app = self.app_path.read_text(encoding="utf-8")
        self.readme = self.readme_path.read_text(encoding="utf-8")
        self.sdkconfig_defaults = self.sdkconfig_defaults_path.read_text(encoding="utf-8")

    def test_vendor_pin_map_and_i2c_devices_are_explicit(self) -> None:
        required_terms = [
            "#define AMOLED_I2C_SDA_GPIO 15",
            "#define AMOLED_I2C_SCL_GPIO 14",
            "#define AXP2101_ADDR 0x34",
            "#define AXP2101_EXPECTED_CHIP_ID 0x4A",
            "#define QMI8658_ADDR 0x6B",
            "#define QMI8658_WHOAMI_EXPECTED 0x05",
            "I2C SDA = GPIO15",
            "I2C SCL = GPIO14",
        ]

        joined = self.app + "\n" + self.readme + "\n" + self.sdkconfig_defaults
        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, joined)

    def test_output_contract_matches_pc_bridge_shape(self) -> None:
        required_terms = [
            '\\"type\\":\\"hello\\"',
            '\\"role\\":\\"%s\\"',
            'AMOLED_BRIDGE_ROLE',
            '\\"type\\":\\"imu_whoami\\"',
            '\\"type\\":\\"imu_sample\\"',
            '\\"sensor_model\\":\\"QMI8658\\"',
            '\\"source_availability\\":\\"bridge_uplink\\"',
            '\\"source_status\\":\\"unverified\\"',
            '\\"imu_source\\":\\"qmi8658_i2c\\"',
            '\\"type\\":\\"amoled_bridge_done\\"',
        ]

        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, self.app)

    def test_sample_window_is_bounded_and_not_a_validation_claim(self) -> None:
        required_terms = [
            "#define AMOLED_BOOT_JSON_DELAY_MS 5000",
            "CONFIG_EGOLINK_AMOLED_SAMPLE_COUNT",
            "CONFIG_EGOLINK_AMOLED_SAMPLE_INTERVAL_MS",
            "CONFIG_EGOLINK_AMOLED_SAMPLE_COUNT=600",
            "CONFIG_EGOLINK_AMOLED_SAMPLE_INTERVAL_MS=50",
            "#define AMOLED_TIMING_MODE \"vTaskDelayUntil\"",
            "vTaskDelayUntil(&last_wake_tick, sample_interval_ticks)",
            '\\"timing_mode\\":\\"%s\\"',
            '\\"requested_window_ms\\":%d',
            '\\"missed_deadlines\\":%',
            "identity_and_configurable_window_only",
            "600 samples",
            "not yet an ODR, jitter, drop-rate, orientation, calibration",
        ]

        joined = self.app + "\n" + self.readme + "\n" + self.sdkconfig_defaults
        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, joined)

        self.assertNotIn('"source_status":"verified"', self.app)
        self.assertNotIn("source_status=verified", self.readme)

    def test_axp2101_bringup_is_conservative(self) -> None:
        required_terms = [
            "AXP2101_DC1_3300MV_VALUE",
            "AXP2101_ALDO1_3300MV_VALUE",
            "i2c_update_bits(AXP2101_ADDR, AXP2101_DC_ONOFF_DVM_CTRL, 0x01, 0x01)",
            "i2c_update_bits(AXP2101_ADDR, AXP2101_LDO_ONOFF_CTRL0, 0x01, 0x01)",
            "It does not",
            "disable any rail",
        ]

        joined = self.app + "\n" + self.readme
        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, joined)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from pathlib import Path
import unittest


class PlatformPowerFirmwareTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.component_dir = self.repo_root / "firmware" / "mqtt_heartbeat" / "components" / "platform_power"
        self.header = (self.component_dir / "include" / "platform_power.h").read_text(encoding="utf-8")
        self.source = (self.component_dir / "platform_power.c").read_text(encoding="utf-8")
        self.component_cmake = (self.component_dir / "CMakeLists.txt").read_text(encoding="utf-8")
        self.kconfig = (self.component_dir / "Kconfig.projbuild").read_text(encoding="utf-8")
        self.main_cmake = (
            self.repo_root / "firmware" / "mqtt_heartbeat" / "main" / "CMakeLists.txt"
        ).read_text(encoding="utf-8")
        self.app_main = (
            self.repo_root / "firmware" / "mqtt_heartbeat" / "main" / "app_main.c"
        ).read_text(encoding="utf-8")
        self.readme = (self.repo_root / "firmware" / "mqtt_heartbeat" / "README.md").read_text(encoding="utf-8")

    def test_component_exposes_minimal_power_api(self) -> None:
        self.assertIn('SRCS "platform_power.c"', self.component_cmake)
        self.assertIn('REQUIRES esp_timer log', self.component_cmake)
        for symbol in [
            "platform_power_init",
            "platform_power_enter_state",
            "platform_power_leave_state",
            "platform_power_mark",
            "platform_power_get_snapshot",
            "platform_power_state_name",
            "platform_power_event_kind_name",
        ]:
            with self.subTest(symbol=symbol):
                self.assertIn(symbol, self.header)
                self.assertIn(symbol, self.source)

    def test_power_states_cover_hpwr_marker_vocabulary(self) -> None:
        for state in [
            "BOOT",
            "ACTIVE",
            "GUARDING",
            "NETWORK_ATTACH",
            "GNSS_FIX",
            "CAPTURE_AUDIO",
            "CAPTURE_IMAGE",
            "STORAGE_WRITE",
            "UPLOAD",
            "EMERGENCY",
            "LIGHT_SLEEP",
            "DEEP_SLEEP",
        ]:
            with self.subTest(state=state):
                self.assertIn(f"PLATFORM_POWER_STATE_{state}", self.header)
                self.assertIn(f'return "{state}"', self.source)

    def test_mock_battery_boundary_is_explicit(self) -> None:
        self.assertIn("PLATFORM_POWER_MOCK_BATTERY_PERCENT 87", self.source)
        self.assertIn("bool battery_is_mock = true", self.source)
        self.assertIn(".charging_is_mock = true", self.source)
        self.assertIn('const char *battery_source = "mock"', self.source)
        self.assertIn('.charging_source = "mock"', self.source)

    def test_max17048_backend_is_explicit_opt_in_with_documented_pins(self) -> None:
        self.assertIn("CONFIG_EGOLINK_PLATFORM_POWER_BACKEND_MAX17048", self.source)
        self.assertIn("MAX17048_I2C_ADDR 0x36", self.source)
        self.assertIn("i2c_master_write_read_device", self.source)
        self.assertIn("config EGOLINK_PLATFORM_POWER_BACKEND_MAX17048", self.kconfig)
        self.assertIn("default EGOLINK_PLATFORM_POWER_BACKEND_MOCK", self.kconfig)
        self.assertIn("default 15", self.kconfig)
        self.assertIn("default 16", self.kconfig)
        self.assertIn("SDA GPIO15 / SCL GPIO16", self.kconfig)
        self.assertIn("SDA GPIO3 / SCL GPIO2", self.kconfig)

    def test_max17048_transaction_takes_and_releases_shared_bus_lease(self) -> None:
        read = self.source.split("static esp_err_t max17048_read_u16", 1)[1].split(
            "static void max17048_init", 1
        )[0]
        self.assertIn("platform_i2c_bus_lease_acquire", read)
        self.assertIn("i2c_master_write_read_device", read)
        self.assertIn("platform_i2c_bus_lease_release", read)
        self.assertLess(
            read.index("platform_i2c_bus_lease_acquire"),
            read.index("i2c_master_write_read_device"),
        )
        self.assertLess(
            read.index("i2c_master_write_read_device"),
            read.index("platform_i2c_bus_lease_release"),
        )

    def test_hpwr_marker_metadata_is_log_only(self) -> None:
        for token in [
            "platform_power_event_kind_t",
            "platform_power_marker_t",
            "state_elapsed_ms",
            "state_cumulative_ms",
            "serial_marker_id",
            "gpio_marker_enabled",
        ]:
            with self.subTest(token=token):
                self.assertIn(token, self.header)
        self.assertIn("s_state_cumulative_ms", self.source)
        self.assertIn("PLATFORM_POWER_EVENT", self.source)
        self.assertIn("state_total_ms", self.source)
        self.assertIn("POWER_MARKER_%06", self.source)
        self.assertIn('s_gpio_marker_id = "disabled"', self.source)
        self.assertIn("s_gpio_marker_enabled = false", self.source)
        self.assertIn("gpio_marker_enabled=%s", self.source)

    def test_main_uses_platform_power_without_real_driver_claims(self) -> None:
        for component in [
            "safety_model",
            "platform_power",
            "esp_common",
            "esp_event",
            "esp_netif",
            "esp_system",
            "esp_timer",
            "esp_wifi",
            "freertos",
            "log",
            "mqtt",
            "nvs_flash",
        ]:
            with self.subTest(component=component):
                self.assertIn(component, self.main_cmake)
        self.assertIn('#include "platform_power.h"', self.app_main)
        self.assertIn("platform_power_init", self.app_main)
        self.assertIn("platform_power_get_snapshot", self.app_main)
        self.assertIn("platform_power_mark", self.app_main)
        self.assertIn('\\"battery_source\\":\\"%s\\"', self.app_main)
        self.assertIn('\\"battery_mv\\":%s', self.app_main)
        self.assertIn('\\"charging_source\\":\\"%s\\"', self.app_main)
        self.assertIn('\\"power_state\\":\\"%s\\"', self.app_main)
        self.assertIn('\\"power_state_elapsed_ms\\":%" PRId64', self.app_main)
        self.assertIn('\\"power_state_cumulative_ms\\":%" PRId64', self.app_main)
        self.assertIn('\\"power_marker_seq\\":%" PRIu32', self.app_main)
        self.assertIn('\\"power_serial_marker_id\\":\\"%s\\"', self.app_main)
        self.assertIn('\\"power_gpio_marker_enabled\\":%s', self.app_main)
        self.assertIn("PLATFORM_POWER_STATE_UPLOAD", self.app_main)
        self.assertIn("status_publish_done", self.app_main)
        self.assertIn("sensor_publish_done", self.app_main)

    def test_readme_keeps_real_power_unverified(self) -> None:
        self.assertIn("platform_power", self.readme)
        self.assertIn("battery_source=mock", self.readme)
        self.assertIn("MAX17048", self.readme)
        self.assertIn("default backend remains", self.readme)
        self.assertIn("mock: MQTT status", self.readme)
        self.assertIn("PLATFORM_POWER_EVENT", self.readme)
        self.assertIn("The GPIO marker", self.readme)
        self.assertIn("remains disabled", self.readme)


if __name__ == "__main__":
    unittest.main()

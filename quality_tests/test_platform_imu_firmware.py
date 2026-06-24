from __future__ import annotations

from pathlib import Path
import unittest


class PlatformImuFirmwareTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.component_dir = self.repo_root / "firmware" / "mqtt_heartbeat" / "components" / "platform_imu"
        self.header = (self.component_dir / "include" / "platform_imu.h").read_text(encoding="utf-8")
        self.source = (self.component_dir / "platform_imu.c").read_text(encoding="utf-8")
        self.component_cmake = (self.component_dir / "CMakeLists.txt").read_text(encoding="utf-8")
        self.component_kconfig = (self.component_dir / "Kconfig.projbuild").read_text(encoding="utf-8")
        self.sdkconfig_defaults = (
            self.repo_root / "firmware" / "mqtt_heartbeat" / "sdkconfig.defaults"
        ).read_text(encoding="utf-8")
        self.qmi8658_defaults = (
            self.repo_root / "firmware" / "mqtt_heartbeat" / "sdkconfig.qmi8658.defaults"
        ).read_text(encoding="utf-8")
        self.main_cmake = (
            self.repo_root / "firmware" / "mqtt_heartbeat" / "main" / "CMakeLists.txt"
        ).read_text(encoding="utf-8")
        self.app_main = (
            self.repo_root / "firmware" / "mqtt_heartbeat" / "main" / "app_main.c"
        ).read_text(encoding="utf-8")
        self.readme = (self.repo_root / "firmware" / "mqtt_heartbeat" / "README.md").read_text(encoding="utf-8")

    def test_component_exposes_minimal_imu_api(self) -> None:
        self.assertIn('SRCS "platform_imu.c"', self.component_cmake)
        self.assertIn("REQUIRES esp_timer log driver", self.component_cmake)
        for symbol in [
            "PLATFORM_IMU_RING_CAPACITY",
            "platform_imu_backend_t",
            "platform_imu_sample_t",
            "platform_imu_snapshot_t",
            "platform_imu_init",
            "platform_imu_sample",
            "platform_imu_sample_mock",
            "platform_imu_push_sample",
            "platform_imu_get_snapshot",
            "platform_imu_read_recent",
        ]:
            with self.subTest(symbol=symbol):
                self.assertIn(symbol, self.header)
                self.assertIn(symbol, self.source)

    def test_ring_buffer_skeleton_is_bounded_and_ordered(self) -> None:
        self.assertIn("#define PLATFORM_IMU_RING_CAPACITY 32", self.header)
        for token in [
            "s_ring[PLATFORM_IMU_RING_CAPACITY]",
            "s_write_index",
            "s_count",
            "s_dropped_samples",
            "% PLATFORM_IMU_RING_CAPACITY",
            "oldest_index",
            "start_offset",
        ]:
            with self.subTest(token=token):
                self.assertIn(token, self.source)

    def test_mock_boundary_is_explicit(self) -> None:
        for token in [
            'PLATFORM_IMU_SOURCE_MOCK = "mock_stationary"',
            "s_hardware_present = false",
            "s_driver_enabled = false",
            "s_data_is_mock = true",
            ".sample_is_mock = true",
            "PLATFORM_IMU_SAMPLE",
        ]:
            with self.subTest(token=token):
                self.assertIn(token, self.source)

    def test_qmi8658_backend_is_opt_in_and_default_mock(self) -> None:
        self.assertIn("choice EGOLINK_PLATFORM_IMU_BACKEND", self.component_kconfig)
        self.assertIn("default EGOLINK_PLATFORM_IMU_BACKEND_MOCK", self.component_kconfig)
        self.assertIn("config EGOLINK_PLATFORM_IMU_BACKEND_QMI8658", self.component_kconfig)
        self.assertIn("CONFIG_EGOLINK_PLATFORM_IMU_BACKEND_MOCK=y", self.sdkconfig_defaults)
        self.assertIn("CONFIG_EGOLINK_PLATFORM_IMU_BACKEND_QMI8658=y", self.qmi8658_defaults)
        self.assertIn("# CONFIG_EGOLINK_PLATFORM_IMU_BACKEND_MOCK is not set", self.qmi8658_defaults)
        for token in [
            "#if CONFIG_EGOLINK_PLATFORM_IMU_BACKEND_QMI8658",
            'PLATFORM_IMU_SOURCE_QMI8658 = "qmi8658_i2c"',
            'PLATFORM_IMU_SENSOR_MODEL_QMI8658 = "QMI8658"',
            "QMI8658_WHOAMI_EXPECTED",
            "platform_imu_init_qmi8658",
            "platform_imu_sample_qmi8658",
            ".sample_is_mock = false",
            "qmi8658_unavailable_mock_fallback",
        ]:
            with self.subTest(token=token):
                self.assertIn(token, self.source)

    def test_main_publishes_imu_metadata_without_direct_backend_coupling(self) -> None:
        self.assertIn("platform_imu", self.main_cmake)
        self.assertIn('#include "platform_imu.h"', self.app_main)
        self.assertIn("platform_imu_init", self.app_main)
        self.assertIn("platform_imu_sample();", self.app_main)
        self.assertNotIn("platform_imu_sample_mock();", self.app_main)
        self.assertIn("platform_imu_get_snapshot", self.app_main)
        for field in [
            '\\"imu_source\\":\\"%s\\"',
            '\\"imu_hardware_present\\":%s',
            '\\"imu_driver_enabled\\":%s',
            '\\"imu_sample_mock\\":%s',
            '\\"imu_ring_capacity\\":%u',
            '\\"imu_ring_count\\":%u',
            '\\"imu_dropped_samples\\":%" PRIu32',
            '\\"imu_latest_seq\\":%" PRIu32',
            '\\"imu_accel_mg_x\\":%d',
            '\\"imu_gyro_mdps_z\\":%d',
        ]:
            with self.subTest(field=field):
                self.assertIn(field, self.app_main)

    def test_sensor_payload_keeps_large_json_buffer_off_task_stack(self) -> None:
        self.assertIn("static char payload[1536];", self.app_main)
        self.assertIn('xTaskCreate(sensor_task, "sensor_task", 6144', self.app_main)
        self.assertNotIn("\n    char payload[1536];", self.app_main)

    def test_readme_keeps_real_imu_unverified(self) -> None:
        self.assertIn("platform_imu", self.readme)
        self.assertIn("mock_stationary", self.readme)
        self.assertIn("QMI8658", self.readme)
        self.assertIn("opt-in", self.readme)
        self.assertIn("ring buffer", self.readme)
        self.assertIn("does not prove a real IMU", self.readme)


if __name__ == "__main__":
    unittest.main()

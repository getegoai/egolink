from __future__ import annotations

from pathlib import Path
import re
import unittest


REPO = Path(__file__).resolve().parents[1]
FIRMWARE = REPO / "firmware" / "mqtt_heartbeat"


def _config_block(kconfig: str, name: str) -> str:
    match = re.search(
        rf"^config {re.escape(name)}\n(?P<body>.*?)(?=^config |^endmenu)",
        kconfig,
        flags=re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing Kconfig symbol: {name}")
    return match.group("body")


class CollectionRateProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.kconfig = (FIRMWARE / "main" / "Kconfig.projbuild").read_text(
            encoding="utf-8"
        )
        self.source = (FIRMWARE / "main" / "collection_main.c").read_text(
            encoding="utf-8"
        )
        self.legacy = (FIRMWARE / "sdkconfig.collection.defaults").read_text(
            encoding="utf-8"
        )
        self.field = (FIRMWARE / "sdkconfig.field020.defaults").read_text(
            encoding="utf-8"
        )

    def test_generic_defaults_preserve_existing_collection_cadence(self) -> None:
        expected = {
            "EGOLINK_COLLECTION_IMU_CHUNK_SAMPLES": ("range 20 100", "default 20"),
            "EGOLINK_COLLECTION_LTE_INTERVAL_MS": ("range 1000 600000", "default 10000"),
            "EGOLINK_COLLECTION_HEALTH_INTERVAL_MS": ("range 1000 600000", "default 10000"),
            "EGOLINK_COLLECTION_WIFI_SCAN_INTERVAL_MS": ("range 5000 600000", "default 45000"),
        }
        for name, clauses in expected.items():
            with self.subTest(name=name):
                block = _config_block(self.kconfig, name)
                self.assertIn("depends on EGOLINK_COLLECTION_PROFILE", block)
                for clause in clauses:
                    self.assertIn(clause, block)
        self.assertIn("CONFIG_EGOLINK_COLLECTION_GNSS_INTERVAL_MS=5000", self.legacy)
        self.assertNotIn("CONFIG_EGOLINK_COLLECTION_IMU_CHUNK_SAMPLES", self.legacy)

    def test_field_overlay_reduces_record_overhead_without_decimating_imu(self) -> None:
        for setting in (
            "CONFIG_EGOLINK_PLATFORM_IMU_QMI8658_SAMPLE_INTERVAL_MS=50",
            "CONFIG_EGOLINK_COLLECTION_IMU_CHUNK_SAMPLES=100",
            "CONFIG_EGOLINK_COLLECTION_GNSS_INTERVAL_MS=15000",
            "CONFIG_EGOLINK_COLLECTION_LTE_INTERVAL_MS=30000",
            "CONFIG_EGOLINK_COLLECTION_HEALTH_INTERVAL_MS=30000",
            "CONFIG_EGOLINK_COLLECTION_WIFI_SCAN_INTERVAL_MS=45000",
        ):
            with self.subTest(setting=setting):
                self.assertIn(setting, self.field)
        for forbidden in ("SSID", "PASSWORD", "BEARER", "DEVICE_ID", "VENDOR_ID", "PRODUCT_ID"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.field)

    def test_runtime_uses_effective_values_and_reports_session_provenance(self) -> None:
        for token in (
            "#ifndef CONFIG_EGOLINK_COLLECTION_NO_SIM",
            "#define CONFIG_EGOLINK_COLLECTION_NO_SIM 0",
            "#ifndef CONFIG_EGOLINK_COLLECTION_LTE_USB_HOST_ALREADY_INSTALLED",
            "#define CONFIG_EGOLINK_COLLECTION_LTE_USB_HOST_ALREADY_INSTALLED 0",
            "count==CONFIG_EGOLINK_COLLECTION_IMU_CHUNK_SAMPLES",
            "COLLECTION_IMU_SAMPLE_INTERVAL_MS 50U",
            "CONFIG_EGOLINK_COLLECTION_LTE_INTERVAL_MS*1000LL",
            "CONFIG_EGOLINK_COLLECTION_HEALTH_INTERVAL_MS*1000LL",
            "CONFIG_EGOLINK_COLLECTION_WIFI_SCAN_INTERVAL_MS*1000LL",
            "COLLECTION_IMU_TASK_STACK_BYTES,NULL,6,NULL,1",
            '"collection_rate_profile_version","collection-rate-v1"',
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.source)
        for field in (
            "imu_sample_interval_us",
            "imu_chunk_samples",
            "imu_task_stack_bytes",
            "gnss_interval_ms",
            "lte_interval_ms",
            "health_interval_ms",
            "wifi_scan_interval_ms",
            "wifi_initial_scan_delay_ms",
        ):
            with self.subTest(field=field):
                self.assertIn(f'"{field}"', self.source)
        self.assertNotIn("next_cell=now+10000000;", self.source)
        self.assertNotIn("next_scan=now_us()+45000000;", self.source)
        self.assertNotIn("next_health=now_us()+10000000;", self.source)

    def test_hundred_sample_block_stays_below_firmware_frame_budget(self) -> None:
        sample_bytes = 16
        sample_count = 100
        base64_capacity = ((sample_count * sample_bytes + 2) // 3) * 4 + 1
        self.assertEqual(2137, base64_capacity)
        self.assertLessEqual(base64_capacity + 1600, 4000)
        self.assertIn("COLLECTION_IMU_FRAME_NON_SAMPLE_BUDGET 1600U", self.source)
        self.assertIn("<= COLLECTION_FRAME_CAPACITY", self.source)
        self.assertIn("#if CONFIG_EGOLINK_COLLECTION_IMU_CHUNK_SAMPLES > 20", self.source)
        self.assertIn("#define COLLECTION_IMU_TASK_STACK_BYTES 10240U", self.source)
        self.assertIn("#define COLLECTION_IMU_TASK_STACK_BYTES 6144U", self.source)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from pathlib import Path
import unittest


class MqttHeartbeatFirmwareTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.app_main = (self.repo_root / "firmware" / "mqtt_heartbeat" / "main" / "app_main.c").read_text(
            encoding="utf-8"
        )
        self.kconfig = (
            self.repo_root / "firmware" / "mqtt_heartbeat" / "main" / "Kconfig.projbuild"
        ).read_text(encoding="utf-8")
        self.readme = (self.repo_root / "firmware" / "mqtt_heartbeat" / "README.md").read_text(encoding="utf-8")

    def test_sensor_event_topic_and_interval_are_configurable(self) -> None:
        self.assertIn("config EGOLINK_EVENT_TOPIC", self.kconfig)
        self.assertIn('default "ego/link/ego-link-001/event"', self.kconfig)
        self.assertIn("config EGOLINK_SENSOR_EVENT_INTERVAL_SEC", self.kconfig)

    def test_sensor_payload_contains_device_health_fields(self) -> None:
        self.assertIn("build_sensor_payload", self.app_main)
        self.assertIn('\\"message_type\\":\\"event\\"', self.app_main)
        self.assertIn('\\"event_type\\":\\"sensor_sample\\"', self.app_main)
        self.assertIn('\\"sensor_kind\\":\\"device_health\\"', self.app_main)
        self.assertIn("esp_get_free_heap_size", self.app_main)
        self.assertIn("esp_get_minimum_free_heap_size", self.app_main)
        self.assertIn("refresh_wifi_rssi", self.app_main)

    def test_sensor_sample_is_published_to_event_topic(self) -> None:
        self.assertIn("CONFIG_EGOLINK_EVENT_TOPIC", self.app_main)
        self.assertIn("MQTT_SENSOR_PUBLISH_OK", self.app_main)
        self.assertIn("xTaskCreate(sensor_task", self.app_main)
        self.assertIn("ego/link/ego-link-001/event", self.readme)


if __name__ == "__main__":
    unittest.main()

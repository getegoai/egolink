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
        self.main_cmake = (
            self.repo_root / "firmware" / "mqtt_heartbeat" / "main" / "CMakeLists.txt"
        ).read_text(encoding="utf-8")
        self.readme = (self.repo_root / "firmware" / "mqtt_heartbeat" / "README.md").read_text(encoding="utf-8")
        self.vps_http_defaults = (
            self.repo_root / "firmware" / "mqtt_heartbeat" / "sdkconfig.vps_http.defaults.example"
        ).read_text(encoding="utf-8")

    def test_sensor_event_topic_and_interval_are_configurable(self) -> None:
        self.assertIn("config EGOLINK_EVENT_TOPIC", self.kconfig)
        self.assertIn('default "ego/link/ego-link-001/event"', self.kconfig)
        self.assertIn("config EGOLINK_SENSOR_EVENT_INTERVAL_SEC", self.kconfig)

    def test_sensor_payload_contains_device_health_fields(self) -> None:
        self.assertIn("build_sensor_payload", self.app_main)
        self.assertIn('\\"message_type\\":\\"event\\"', self.app_main)
        self.assertIn('\\"event_type\\":\\"sensor_sample\\"', self.app_main)
        self.assertIn('\\"sensor_kind\\":\\"device_health\\"', self.app_main)
        self.assertIn('\\"reset_reason\\":\\"%s\\"', self.app_main)
        self.assertIn('\\"boot_count\\":%" PRIu32', self.app_main)
        self.assertIn("esp_get_free_heap_size", self.app_main)
        self.assertIn("esp_get_minimum_free_heap_size", self.app_main)
        self.assertIn("refresh_wifi_rssi", self.app_main)

    def test_reset_diagnostics_are_reported_without_serial_logs(self) -> None:
        for token in [
            "reset_reason_name",
            "esp_reset_reason()",
            "init_boot_diagnostics",
            'nvs_open("egolink", NVS_READWRITE',
            'nvs_get_u32(handle, "boot_count"',
            'nvs_set_u32(handle, "boot_count"',
            '\\"boot_uptime_ms\\":%" PRId64',
            "BOOT_DIAGNOSTICS",
        ]:
            with self.subTest(token=token):
                self.assertIn(token, self.app_main)

    def test_sensor_sample_is_published_to_event_topic(self) -> None:
        self.assertIn("CONFIG_EGOLINK_EVENT_TOPIC", self.app_main)
        self.assertIn("MQTT_SENSOR_PUBLISH_OK", self.app_main)
        self.assertIn("xTaskCreate(sensor_task", self.app_main)
        self.assertIn("ego/link/ego-link-001/event", self.readme)

    def test_http_message_hub_mode_is_opt_in(self) -> None:
        self.assertIn("config EGOLINK_MESSAGE_HUB_HTTP_ENABLED", self.kconfig)
        self.assertIn("default n", self.kconfig)
        self.assertIn("config EGOLINK_MESSAGE_HUB_BASE_URL", self.kconfig)
        self.assertIn("config EGOLINK_MESSAGE_HUB_BEARER_TOKEN", self.kconfig)
        self.assertIn("config EGOLINK_FW_VERSION", self.kconfig)
        self.assertIn("config EGOLINK_TEST_RUN_ID", self.kconfig)
        self.assertIn("esp_http_client", self.main_cmake)
        self.assertIn("json", self.main_cmake)

    def test_http_message_hub_posts_heartbeat_and_acks_commands(self) -> None:
        for token in [
            "#if CONFIG_EGOLINK_MESSAGE_HUB_HTTP_ENABLED",
            "message_hub_register_device",
            "/api/v1/devices/register",
            "/api/v1/devices/%s/heartbeat",
            "/api/v1/devices/%s/telemetry",
            "/api/v1/devices/%s/commands/poll",
            "/api/v1/devices/%s/commands/%s/ack",
            "Authorization",
            "Bearer %s",
            "build_ack_payload",
            "append_test_run_id_and_close_json",
            "CONFIG_EGOLINK_TEST_RUN_ID",
            '\\"test_run_id\\":\\"%s\\"',
            "cJSON_Parse",
            "xTaskCreate(command_poll_task",
        ]:
            with self.subTest(token=token):
                self.assertIn(token, self.app_main)

    def test_status_payload_buffer_has_margin_for_reset_diagnostics(self) -> None:
        heartbeat_body = self.app_main.split("static void publish_heartbeat", 1)[1].split(
            "static void publish_sensor_sample", 1
        )[0]
        self.assertIn("#define HEARTBEAT_TASK_STACK_SIZE 12288", self.app_main)
        self.assertIn("static char payload[3072];", heartbeat_body)
        self.assertIn('xTaskCreate(heartbeat_task, "heartbeat_task", HEARTBEAT_TASK_STACK_SIZE', self.app_main)
        self.assertNotIn("\n    char payload[3072];", heartbeat_body)
        self.assertIn('\\"reset_reason\\":\\"%s\\"', self.app_main)
        self.assertIn('\\"boot_uptime_ms\\":%" PRId64', self.app_main)

    def test_lte_observation_payload_is_optional_and_explainable(self) -> None:
        for token in [
            "build_lte_observation_fragment",
            "#if CONFIG_EGOLINK_SIM7670_LTE_STATUS_ENABLED",
            "sim7670_lte_query_status",
            '\\"cell\\":{\\"rat\\":\\"%s\\"',
            '\\"lte\\":{\\"driver\\":\\"%s\\"',
            '\\"registration_state\\":\\"%s\\"',
            '\\"pdp_state\\":\\"%s\\"',
            '\\"reason_code\\":\\"%s\\"',
            '\\"raw_command\\":\\"%s\\"',
            "static char payload[4096];",
            "#define LTE_OBSERVATION_FRAGMENT_MAX 2300",
            "#define SENSOR_TASK_STACK_SIZE 12288",
            "static char s_status_lte_fragment[LTE_OBSERVATION_FRAGMENT_MAX];",
            "static char s_sensor_lte_fragment[LTE_OBSERVATION_FRAGMENT_MAX];",
            'xTaskCreate(sensor_task, "sensor_task", SENSOR_TASK_STACK_SIZE',
        ]:
            with self.subTest(token=token):
                self.assertIn(token, self.app_main)
        self.assertNotIn("char lte_fragment[LTE_OBSERVATION_FRAGMENT_MAX];", self.app_main)

    def test_http_mode_docs_keep_secret_and_capability_boundaries(self) -> None:
        self.assertIn("sdkconfig.vps.local", self.readme)
        self.assertIn("Do not commit real VPS addresses", self.readme)
        self.assertIn("does not prove real GNSS", self.readme)
        self.assertIn("<operator-vps>", self.vps_http_defaults)
        self.assertIn("<runtime-token>", self.vps_http_defaults)
        self.assertIn("CONFIG_EGOLINK_TEST_RUN_ID", self.vps_http_defaults)
        self.assertIn("server exports can bind", self.readme)


if __name__ == "__main__":
    unittest.main()

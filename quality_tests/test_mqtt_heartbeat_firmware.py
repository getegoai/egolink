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
        self.sim7670_kconfig = (
            self.repo_root / "firmware" / "mqtt_heartbeat" / "components" / "sim7670_gnss" / "Kconfig.projbuild"
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

    def test_lte_http_probe_mode_is_opt_in_and_skips_wifi_runtime_path(self) -> None:
        for token in [
            "CONFIG_EGOLINK_SIM7670_LTE_HTTP_PROBE_ENABLED",
            "wait_for_lte_ready_for_http_probe",
            "publish_lte_http_probe_once",
            "publish_lte_http_probe_with_retries",
            "lte_http_probe_task",
            "build_lte_http_probe_payload",
            "build_lte_http_probe_lte_fragment",
            "#define LTE_HTTP_PROBE_TASK_STACK_SIZE 12288",
            '\\"event_type\\":\\"lte_http_probe\\"',
            '\\"transport\\":{\\"type\\":\\"lte\\"',
            '\\"lte_http\\":{\\"phase\\":\\"%s\\"',
            "sim7670_lte_http_post_json",
            "LTE_HTTP_PROBE_ATTEMPT_PAYLOAD_BYTES",
            "LTE_HTTP_PROBE_RESULT_PAYLOAD_BYTES",
            "LTE_HTTP_PROBE_READY_CHECK",
            "LTE_HTTP_PROBE_ROUND_START",
            "LTE_HTTP_PROBE_ROUND_DONE",
            "LTE_HTTP_PROBE_RETRY_DELAY",
            "LTE_HTTP_PROBE_ATTEMPT_DONE",
            "LTE_HTTP_PROBE_RESULT_DONE",
            "lte_http_probe_done",
        ]:
            with self.subTest(token=token):
                self.assertIn(token, self.app_main)
        self.assertIn(
            'xTaskCreate(lte_http_probe_task, "lte_http_probe_task", LTE_HTTP_PROBE_TASK_STACK_SIZE',
            self.app_main,
        )
        app_main_body = self.app_main.split("void app_main", 1)[1]
        probe_branch = app_main_body.split(
            "#elif CONFIG_EGOLINK_MESSAGE_HUB_HTTP_ENABLED && CONFIG_EGOLINK_SIM7670_LTE_HTTP_PROBE_ENABLED",
            1,
        )[1].split("#else", 1)[0]
        self.assertIn("xTaskCreate(lte_http_probe_task", probe_branch)
        self.assertNotIn("publish_lte_http_probe_with_retries", probe_branch)
        self.assertNotIn("start_wifi()", probe_branch)
        self.assertNotIn("xTaskCreate(command_poll_task", probe_branch)

    def test_lte_http_command_loop_mode_is_opt_in_and_skips_wifi_runtime_path(self) -> None:
        for token in [
            "CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED",
            "sim7670_lte_http_get_raw",
            "sim7670_lte_http_post_raw",
            "lte_http_command_task",
            "egolink_crc32",
            "build_lte_raw_frame",
            "build_lte_command_ack_payload",
            "build_lte_command_diag_payload",
            "lte_http_ack_command",
            "lte_http_post_command_diag",
            "lte_http_poll_commands_once",
            "/commands/poll.raw",
            "/ack.raw",
            "EGLK/1 type=%s id=%s seq=%",
            "content-type=text/x-egolink-kv",
            "text/x-egolink-frame; profile=raw-frame.p0.v1",
            "#define LTE_HTTP_COMMAND_TASK_STACK_SIZE 16384",
            '\\"event_type\\":\\"lte_http_command_diag\\"',
            '\\"transport\\":{\\"type\\":\\"lte\\"',
            '\\"poll_reason_code\\":\\"%s\\"',
            '\\"poll_data_len\\":%s',
            '\\"parse_status\\":\\"%s\\"',
            '\\"command_count\\":%d',
            '\\"ack_observed\\":%s',
            "duplicate_local_execution_prevented=%s",
            "transport_type=lte",
            "lte_http_phase=command_ack",
            "set_lte_command_parse_status",
            '"raw_http_ok_body_received"',
            '"raw_header_incomplete"',
            '"raw_len_mismatch"',
            '"raw_crc_mismatch"',
            '"raw_no_command"',
            '"raw_command_selected"',
            "LTE_HTTP_COMMAND_POLL_ROUND_START",
            "LTE_HTTP_COMMAND_POLL_ROUND_DONE",
            "LTE_HTTP_COMMAND_RAW_ACK_FRAME_BYTES",
            "LTE_HTTP_COMMAND_RAW_ACK_DONE",
            "LTE_HTTP_COMMAND_DIAG_PAYLOAD_BYTES",
            "LTE_HTTP_COMMAND_DIAG_POST_DONE",
            '"ready"',
            '"poll_no_ack"',
            '"command_ack_observed"',
            "lte_http_command_done",
        ]:
            with self.subTest(token=token):
                self.assertIn(token, self.app_main)
        self.assertIn("config EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED", self.sim7670_kconfig)
        self.assertIn("config EGOLINK_SIM7670_LTE_HTTP_COMMAND_POLL_MAX_ATTEMPTS", self.sim7670_kconfig)
        self.assertIn("default 120", self.sim7670_kconfig)
        self.assertIn("config EGOLINK_SIM7670_LTE_HTTP_COMMAND_POLL_INTERVAL_SEC", self.sim7670_kconfig)
        app_main_body = self.app_main.split("void app_main", 1)[1]
        command_branch = app_main_body.split(
            "#if CONFIG_EGOLINK_MESSAGE_HUB_HTTP_ENABLED && CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED",
            1,
        )[1].split("#elif", 1)[0]
        self.assertIn("xTaskCreate(lte_http_command_task", command_branch)
        self.assertNotIn("start_wifi()", command_branch)
        self.assertNotIn("xTaskCreate(command_poll_task", command_branch)

    def test_lte_http_probe_payload_stays_compact_for_simcom_httpdata(self) -> None:
        probe_payload = self.app_main.split("static void build_lte_http_probe_payload", 1)[1].split(
            "static bool publish_lte_http_probe_once", 1
        )[0]
        compact_fragment = self.app_main.split("static void build_lte_http_probe_lte_fragment", 1)[1].split(
            "#if CONFIG_EGOLINK_MESSAGE_HUB_HTTP_ENABLED && (CONFIG_EGOLINK_SIM7670_LTE_HTTP_PROBE_ENABLED || CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED)",
            1,
        )[0]

        self.assertIn('\\"status_code\\":%s', probe_payload)
        self.assertIn('\\"data_len\\":%s', probe_payload)
        self.assertIn('\\"action_elapsed_ms\\":%s', probe_payload)
        self.assertNotIn('\\"raw_command\\":\\"%s\\"', probe_payload)
        self.assertNotIn('\\"raw_response\\":\\"%s\\"', probe_payload)
        self.assertNotIn('\\"operator\\":\\"%s\\"', compact_fragment)
        self.assertNotIn('\\"raw_command\\":\\"%s\\"', compact_fragment)
        self.assertIn('\\"assigned_ip\\":\\"%s\\"', compact_fragment)
        self.assertIn('\\"registration_state\\":\\"%s\\"', compact_fragment)
        self.assertIn('\\"pdp_state\\":\\"%s\\"', compact_fragment)

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

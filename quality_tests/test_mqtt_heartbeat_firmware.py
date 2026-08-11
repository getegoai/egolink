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
            "build_lte_location_report_kv_payload",
            "lte_http_publish_raw_location_report",
            "build_lte_command_ack_payload",
            "build_lte_command_diag_payload",
            "lte_http_ack_command",
            "lte_http_post_command_diag",
            "lte_http_poll_commands_once",
            "/commands/poll.raw",
            "/ack.raw",
            "/raw-ingest",
            "EGLK/1 type=%s id=%s seq=%",
            "content-type=text/x-egolink-kv",
            "text/x-egolink-frame; profile=raw-frame.p0.v1",
            "event_type=location_report",
            "location_request_cmd_id=%s",
            "lte_http_phase=location_report",
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
            "LTE_HTTP_LOCATION_RAW_FRAME_BYTES",
            "LTE_HTTP_LOCATION_RAW_POST_DONE",
            "LTE_HTTP_COMMAND_DIAG_PAYLOAD_BYTES",
            "LTE_HTTP_COMMAND_DIAG_POST_DONE",
            'strcmp(command->cmd, "request_location")',
            "lte raw location_report upload failed",
            "lte raw location_observation upload failed",
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

    def test_raw_lte_location_observation_mode_is_opt_in_and_explainable(self) -> None:
        for token in [
            "config EGOLINK_SIM7670_LOCATION_OBSERVATION_ENABLED",
            "CONFIG_EGOLINK_SIM7670_LOCATION_OBSERVATION_ENABLED",
            "build_lte_location_observation_kv_payload",
            "lte_http_publish_raw_location_observation",
            "event_type=location_observation",
            "source=sim7670g_firmware_cell",
            "source_status=observed",
            "cell_rat=%s",
            "cell_id=%s",
            "cell_rsrp=%s",
            "cell_registration_state=%s",
            "cell_reason_code=%s",
            "lte_query_ok=%s",
            "lte_registered=%s",
            "lte_pdp_active=%s",
            "lte_reason_code=%s",
            "wifi_source_status=disabled",
            "wifi_evidence_status=missing",
            "wifi_scan_enabled=false",
            "wifi_privacy=raw_bssid_not_collected",
            "imu_source_status=%s",
            "imu_evidence_status=%s",
            "imu_data_is_mock=%s",
            "imu_backend_status=%s",
            "power_source_status=%s",
            "power_evidence_status=%s",
            "power_soc_pct=%d",
            "power_battery_mv=%s",
            "location_belief_state=Unknown",
            "location_belief_source=cell,lte,wifi,imu,power",
            "location_belief_reason=cell_observation_without_position_fix",
            "lte_http_phase=location_observation",
            "network_mode=LTE",
            "network_rssi=%s",
            "network_state=%s",
            "network_last_error=%s",
            "network_reconnect_count=%",
            "network_last_reconnect_reason=%s",
            "network_raw_post_attempt_count=%",
            "network_raw_post_success_count=%",
            "network_raw_post_failure_count=%",
            "cache_state=%s",
            "cache_source_status=%s",
            "cache_retry_policy=single_retry_current_boot",
            "cache_retry_attempt_count=%",
            "cache_retry_success_count=%",
            "cache_retry_failure_count=%",
            "cache_queued_message_count=%",
            "cache_dropped_message_count=%",
            "cache_oldest_message_age_ms=%",
            "cache_last_drop_reason=%s",
            "cache_flush_attempt_count=%",
            "cache_flush_success_count=%",
            "cache_flush_failure_count=%",
            "CONFIG_EGOLINK_SIM7670_LTE_HTTP_RAW_POST_FAIL_ONCE_TEST",
            "CONFIG_EGOLINK_SIM7670_LTE_RECONNECT_STORE_FORWARD_TEST",
            "test_inject_raw_post_fail_once=true",
            "lte_reliability_evidence_fields_for_observation",
            "lte_reliability_evidence_fields_for_ack",
            "volatile_outbox",
            "store_forward",
            "ready_after_reconnect",
            "LTE_HTTP_ACTION_FAILED",
            "pdp_reactivate",
            "retry_attempt_count",
            "retry_success_count",
            "retry_failure_count",
            "lte_raw_outbox_post_raw_with_retry",
            "LTE_HTTP_RAW_POST_RETRY",
            "lte_raw_outbox_record_post_result",
            "lte_raw_outbox_record_retry_result",
            "lte_raw_outbox_record_drop",
            "char payload[2050]",
            "char frame[2400]",
            "LTE_HTTP_LOCATION_OBSERVATION_PAYLOAD_TRUNCATED",
            "LTE_HTTP_LOCATION_OBSERVATION_RAW_FRAME_BYTES",
            "LTE_HTTP_LOCATION_OBSERVATION_RAW_POST_DONE",
            "firmware uploaded SIM7670G GNSS location_report and cell location_observation",
        ]:
            with self.subTest(token=token):
                self.assertIn(token, self.app_main + self.sim7670_kconfig)
        self.assertIn(
            "depends on EGOLINK_MESSAGE_HUB_HTTP_ENABLED && EGOLINK_GNSS_LOCATION_SCAFFOLD_ENABLED",
            self.sim7670_kconfig,
        )
        observation_payload = self.app_main.split("static bool build_lte_location_observation_kv_payload", 1)[1].split(
            "static bool lte_http_publish_raw_location_observation", 1
        )[0]
        self.assertIn('power.battery_is_mock ? "mock" : "measured"', observation_payload)
        self.assertNotIn("power.battery_is_mock || power.charging_is_mock", observation_payload)
        for token in [
            "cell_operator=%s",
            "cell_mcc=%s",
            "cell_mnc=%s",
            "cell_tac=%s",
            "cell_sim_state=%s",
            "lte_uart_ready=%s",
            "lte_at_ok=%s",
            "lte_sim_ready=%s",
            "lte_attached=%s",
            "lte_ip_valid=%s",
            "lte_sim_state=%s",
            "lte_registration_state=%s",
            "lte_apn_state=%s",
            "lte_pdp_state=%s",
            "power_battery_source=%s",
            "power_charging_source=%s",
            "power_marker_seq=%",
            "wifi_reason=wifi_disabled_in_lte_location_observation",
            "imu_reason=imu_backend_not_product_verified",
            "power_reason=platform_power_source_not_product_meter",
            "cache_state=not_enabled",
            "cache_source_status=unverified",
            "cache_last_drop_reason=cache_not_enabled",
        ]:
            with self.subTest(compact_token=token):
                self.assertNotIn(token, observation_payload)
        self.assertIn("config EGOLINK_SIM7670_LTE_HTTP_RAW_POST_FAIL_ONCE_TEST", self.sim7670_kconfig)
        self.assertIn("default n", self.sim7670_kconfig)

    def test_bounded_imu_window_captures_before_shared_chunked_upload(self) -> None:
        for token in [
            '#define IMU_WINDOW_SAMPLE_COUNT 100u',
            '#define IMU_WINDOW_INTERVAL_MS 50u',
            '#define IMU_WINDOW_WARMUP_SAMPLE_COUNT 10u',
            '#define IMU_WINDOW_RECORD_BYTES 28u',
            '#define IMU_WINDOW_SAMPLES_PER_CHUNK 10u',
            '#define IMU_WINDOW_RAW_FRAME_MAX_BYTES 1200u',
            '#define IMU_WINDOW_CAPTURE_CMD_ID_MAX 16u',
            'static uint8_t s_imu_window_binary[',
            'platform_imu_capture_begin()',
            'platform_imu_sample_real(&sample)',
            'vTaskDelayUntil(',
            'platform_imu_capture_end()',
            'event_type=imu_window_chunk',
            'event_type=imu_window_manifest',
            'samples_b64=%s',
            'training_allowed=false',
            'activity_label=unknown',
            'axis_mapping_status=unrecorded',
            'boot_count=%',
            'warmup_sample_count=%',
            'strcmp(command->cmd, "capture_imu_window")',
            'command->test_run_id',
            'capture_command_payload_shape_valid(payload)',
            'command->sample_count != IMU_WINDOW_SAMPLE_COUNT',
            'command->interval_ms != IMU_WINDOW_INTERVAL_MS',
            'IMU_WINDOW_CHUNK_POST_DONE',
            'IMU_WINDOW_MANIFEST_POST_DONE',
            'LTE_HTTP_COMMAND_DUPLICATE_RESULT_REPLAY',
            'LTE_EXECUTED_COMMAND_CACHE_SIZE CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_POLL_MAX_ATTEMPTS',
            'find_executed_command_result(command->cmd_id)',
            'manifest_frame_preflight_over_1200_bytes',
            's_boot_count_persisted',
            'IMU_WINDOW_ACK_SUPPRESSED stop_not_confirmed=true',
        ]:
            with self.subTest(token=token):
                self.assertIn(token, self.app_main)

        capture = self.app_main.split("static bool capture_real_imu_window", 1)[1].split(
            "static bool build_imu_window_manifest_frame", 1
        )[0]
        upload = self.app_main.split("static bool publish_imu_window", 1)[1].split(
            "#if CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED", 1
        )[0]
        self.assertNotIn("sim7670_lte_http_post_raw", capture)
        self.assertNotIn("lte_raw_outbox_post_raw_with_retry", capture)
        self.assertIn("capture_real_imu_window(&capture)", upload)
        self.assertLess(upload.index("capture_real_imu_window(&capture)"), upload.index("IMU_WINDOW_CHUNK_POST_DONE"))
        self.assertLess(upload.index("manifest_frame_preflight_over_1200_bytes"), upload.index("IMU_WINDOW_CHUNK_POST_DONE"))
        self.assertIn("strlen(s_imu_window_frame) > IMU_WINDOW_RAW_FRAME_MAX_BYTES", upload)

    def test_wifi_imu_window_profile_reuses_raw_parser_and_shared_publisher(self) -> None:
        for token in [
            "config EGOLINK_WIFI_IMU_WINDOW_COMMAND_ENABLED",
            "depends on EGOLINK_MESSAGE_HUB_HTTP_ENABLED && EGOLINK_PLATFORM_IMU_BACKEND_QMI8658",
            "config EGOLINK_WIFI_IMU_WINDOW_POLL_MAX_ATTEMPTS",
            "default 120",
            "config EGOLINK_WIFI_IMU_WINDOW_MAX_SUCCESSFUL_COMMANDS",
            "default 1",
            "range 1 4",
            "CONFIG_EGOLINK_WIFI_IMU_WINDOW_COMMAND_ENABLED",
            "message_hub_request_with_content_type",
            "message_hub_post_raw",
            '"text/x-egolink-frame; profile=raw-frame.p0.v1"',
            "wifi_http_poll_imu_window_command_once",
            "WIFI_IMU_WINDOW_POLL_NO_COMMAND",
            "WIFI_IMU_WINDOW_POLL_PARSE_ERROR",
            "WIFI_IMU_WINDOW_POLL_COMMAND_OK",
            "WIFI_IMU_WINDOW_POLL_COMMAND_FAILED",
            "WIFI_IMU_WINDOW_POLL_COMMAND_DUPLICATE",
            "CONFIG_EGOLINK_WIFI_IMU_WINDOW_POLL_MAX_ATTEMPTS",
            "CONFIG_EGOLINK_WIFI_IMU_WINDOW_MAX_SUCCESSFUL_COMMANDS",
            "WIFI_IMU_WINDOW_COMMAND_TASK_DONE",
            "/commands/poll.raw",
            "parse_lte_raw_command_frame(response, &command)",
            "wifi_http_execute_and_ack_raw_command",
            "wifi_http_ack_raw_command",
            "/ack.raw",
            'publish_imu_window(command->cmd_id, command->test_run_id, "wifi")',
            'publish_imu_window(command->cmd_id, command->test_run_id, "lte")',
            '"transport_type=%s\\n"',
            '"transport_type=wifi\\n"',
            "WIFI_IMU_WINDOW_DUPLICATE_RESULT_REPLAY",
            "WIFI_IMU_WINDOW_COMMAND_DUPLICATE",
            "find_executed_command_result(command->cmd_id)",
            "Wi-Fi IMU executed-command cache must cover the configured successful-command limit",
            "command->test_run_id",
            "#if !CONFIG_EGOLINK_WIFI_IMU_WINDOW_COMMAND_ENABLED",
        ]:
            with self.subTest(token=token):
                self.assertIn(token, self.app_main + self.kconfig)

        self.assertEqual(self.app_main.count("static bool capture_real_imu_window("), 1)
        self.assertEqual(self.app_main.count("static bool publish_imu_window("), 1)
        self.assertEqual(self.app_main.count("static bool parse_lte_raw_command_frame("), 1)
        capture = self.app_main.split("static bool capture_real_imu_window", 1)[1].split(
            "static bool build_imu_window_manifest_frame", 1
        )[0]
        self.assertNotIn("message_hub_post_raw", capture)
        self.assertNotIn("message_hub_request", capture)
        wifi_execute = self.app_main.split(
            "static wifi_imu_window_command_result_t wifi_http_execute_and_ack_raw_command", 1
        )[1].split(
            "static bool wifi_http_poll_imu_window_command_once", 1
        )[0]
        self.assertNotIn("capture_real_imu_window", wifi_execute)
        self.assertLess(
            wifi_execute.index('publish_imu_window(command->cmd_id, command->test_run_id, "wifi")'),
            wifi_execute.index("wifi_http_ack_raw_command(command, status, message, duplicate)"),
        )
        self.assertLess(
            wifi_execute.index("wifi_http_ack_raw_command(command, status, message, duplicate)"),
            wifi_execute.index("return WIFI_IMU_WINDOW_COMMAND_OK"),
        )
        self.assertIn('if (!ack_ok || strcmp(status, "ok") != 0)', wifi_execute)
        self.assertIn("return WIFI_IMU_WINDOW_COMMAND_DUPLICATE", wifi_execute)
        command_task = self.app_main.split("static void command_poll_task", 1)[1].split(
            "static void wifi_event_handler", 1
        )[0]
        self.assertIn("wifi_http_poll_imu_window_command_once", command_task)
        self.assertIn("message_hub_poll_commands", command_task)
        self.assertIn("for (int attempt = 1;", command_task)
        self.assertIn("++successful_commands", command_task)
        self.assertIn("result != WIFI_IMU_WINDOW_POLL_NO_COMMAND", command_task)
        self.assertIn("result != WIFI_IMU_WINDOW_POLL_COMMAND_OK", command_task)
        self.assertIn(
            "successful_commands >= CONFIG_EGOLINK_WIFI_IMU_WINDOW_MAX_SUCCESSFUL_COMMANDS",
            command_task,
        )
        self.assertIn("vTaskDelete(NULL)", command_task)
        self.assertNotIn("while (true)", command_task.split("#else", 1)[0])
        lte_ready_section = self.app_main.split("static bool wait_for_lte_ready_for_http_probe", 1)[0]
        self.assertTrue(
            lte_ready_section.rstrip().endswith(
                "#if CONFIG_EGOLINK_SIM7670_LTE_HTTP_PROBE_ENABLED || CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED"
            )
        )

    def test_d1_periodic_location_mode_is_opt_in_and_keeps_lte_loop_running(self) -> None:
        for token in [
            "config EGOLINK_SIM7670_D1_PERIODIC_LOCATION_ENABLED",
            "default n",
            "depends on EGOLINK_SIM7670_LOCATION_OBSERVATION_ENABLED",
            "config EGOLINK_SIM7670_D1_PERIODIC_LOCATION_INTERVAL_SEC",
            "range 15 3600",
            "CONFIG_EGOLINK_SIM7670_D1_PERIODIC_LOCATION_ENABLED",
            "lte_http_publish_d1_periodic_location_once",
            "d1-periodic-%",
            "LTE_HTTP_D1_PERIODIC_LOCATION_START",
            "LTE_HTTP_D1_PERIODIC_LOCATION_DONE",
            "LTE_HTTP_D1_PERIODIC_LOCATION_SCHEDULED",
            "CONFIG_EGOLINK_SIM7670_D1_PERIODIC_LOCATION_INTERVAL_SEC",
            "periodic_location=true",
        ]:
            with self.subTest(token=token):
                self.assertIn(token, self.app_main + self.sim7670_kconfig)
        command_branch = self.app_main.split("static void lte_http_command_task", 1)[1].split(
            "static void build_status_payload",
            1,
        )[0]
        periodic_branch = command_branch.split("#if CONFIG_EGOLINK_SIM7670_D1_PERIODIC_LOCATION_ENABLED", 1)[1].split(
            "#else",
            1,
        )[0]
        self.assertIn("for (int attempt = 1;; ++attempt)", periodic_branch)
        self.assertIn("lte_http_poll_commands_once", periodic_branch)
        self.assertIn("lte_http_publish_d1_periodic_location_once", periodic_branch)
        self.assertIn("vTaskDelay", periodic_branch)
        self.assertNotIn("vTaskDelete(NULL)", periodic_branch)
        self.assertIn("Test-only LTE-009 switch", self.sim7670_kconfig)
        self.assertIn("config EGOLINK_SIM7670_LTE_RECONNECT_STORE_FORWARD_TEST", self.sim7670_kconfig)
        self.assertIn("Test-only LTE-011 switch", self.sim7670_kconfig)

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

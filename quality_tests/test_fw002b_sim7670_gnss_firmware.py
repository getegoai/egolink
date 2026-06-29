from __future__ import annotations

from pathlib import Path
import unittest


class FW002BSim7670GnssFirmwareTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.component_dir = self.repo_root / "firmware" / "mqtt_heartbeat" / "components" / "sim7670_gnss"
        self.kconfig = (self.component_dir / "Kconfig.projbuild").read_text(encoding="utf-8")
        self.header = (self.component_dir / "include" / "sim7670_gnss.h").read_text(encoding="utf-8")
        self.source = (self.component_dir / "sim7670_gnss.c").read_text(encoding="utf-8")
        self.app_main = (self.repo_root / "firmware" / "mqtt_heartbeat" / "main" / "app_main.c").read_text(
            encoding="utf-8"
        )
        self.main_cmake = (
            self.repo_root / "firmware" / "mqtt_heartbeat" / "main" / "CMakeLists.txt"
        ).read_text(encoding="utf-8")
        self.readme = (self.repo_root / "firmware" / "mqtt_heartbeat" / "README.md").read_text(encoding="utf-8")
        self.protocol_doc = (self.repo_root / "docs" / "development" / "PROTOCOL.md").read_text(encoding="utf-8")
        self.defaults = (
            self.repo_root / "firmware" / "mqtt_heartbeat" / "sdkconfig.vps_http.defaults.example"
        ).read_text(encoding="utf-8")

    def test_backend_is_explicit_opt_in_with_waveshare_uart_defaults(self) -> None:
        for token in [
            "config EGOLINK_SIM7670_GNSS_ENABLED",
            "config EGOLINK_SIM7670_LTE_STATUS_ENABLED",
            "config EGOLINK_SIM7670_LTE_HTTP_PROBE_ENABLED",
            "default n",
            "depends on EGOLINK_MESSAGE_HUB_HTTP_ENABLED",
            "config EGOLINK_SIM7670_UART_NUM",
            "default 1",
            "EGOLINK_SIM7670_LTE_HTTP_PROBE_ENABLED",
            "config EGOLINK_SIM7670_UART_RX_GPIO",
            "default 17",
            "config EGOLINK_SIM7670_UART_TX_GPIO",
            "default 18",
            "config EGOLINK_SIM7670_UART_BAUD",
            "default 115200",
        ]:
            with self.subTest(token=token):
                self.assertIn(token, self.kconfig)

    def test_lte_status_backend_is_opt_in_and_reports_explainable_states(self) -> None:
        combined = self.header + self.source
        for token in [
            "sim7670_lte_report_t",
            "sim7670_lte_query_status",
            "sim7670_lte_backend_name",
            "AT+CPIN?",
            "AT+COPS?",
            "AT+CEREG?",
            "AT+CGATT?",
            "AT+CGDCONT?",
            "AT+CGACT?",
            "AT+CGPADDR=1",
            "AT+CSQ",
            "AT+CPSI?",
            "LTE_AT_UNREACHABLE",
            "LTE_SIM_NOT_READY",
            "LTE_NOT_REGISTERED",
            "LTE_NOT_ATTACHED",
            "LTE_PDP_INACTIVE",
            "LTE_READY",
            "parse_cpsi",
            "parse_cereg",
        ]:
            with self.subTest(token=token):
                self.assertIn(token, combined)

    def test_lte_http_probe_backend_is_opt_in_and_does_not_log_token(self) -> None:
        combined = self.kconfig + self.header + self.source + self.app_main
        for token in [
            "sim7670_lte_http_probe_result_t",
            "sim7670_lte_http_post_json",
            "sim7670_lte_http_backend_name",
            "AT+HTTPINIT",
            "AT+HTTPPARA=USERDATA",
            "CONFIG_EGOLINK_SIM7670_LTE_HTTP_SET_CID_PARAM",
            "AT+HTTPDATA",
            "AT+HTTPACTION=1",
            "AT+HTTPREAD",
            "LTE_HTTP_OK",
            "LTE_HTTP_DATA_FAILED",
            "LTE_HTTP_ACTION_FAILED",
            "LTE_HTTP_CLIENT_ERROR",
            "sim7670_send_at_labeled",
            "config EGOLINK_SIM7670_LTE_HTTP_READY_WAIT_SEC",
            "default 120",
            "config EGOLINK_SIM7670_LTE_HTTP_PROBE_MAX_ATTEMPTS",
            "default 6",
            "config EGOLINK_SIM7670_LTE_HTTP_PROBE_RETRY_INTERVAL_SEC",
            "default 20",
            "publish_lte_http_probe_with_retries",
            "LTE_HTTP_PROBE_ROUND_START",
            "LTE_HTTP_PROBE_ROUND_DONE",
            "LTE_HTTP_PROBE_RETRY_DELAY",
            "LTE_HTTP_PROBE_ATTEMPT_DONE",
            "LTE_HTTP_PROBE_RESULT_DONE",
            "LTE_HTTP_PROBE_READY_CHECK",
            "LTE_HTTP_PROBE_READY_RESULT",
        ]:
            with self.subTest(token=token):
                self.assertIn(token, combined)
        cid_config = self.kconfig.split("config EGOLINK_SIM7670_LTE_HTTP_SET_CID_PARAM", 1)[1]
        self.assertIn("default n", cid_config.split("config ", 1)[0])
        cid_block = self.source.split("#if CONFIG_EGOLINK_SIM7670_LTE_HTTP_SET_CID_PARAM", 1)[1]
        self.assertIn('AT+HTTPPARA=\\"CID\\",1', cid_block)
        self.assertNotIn("command=AT+HTTPPARA=\\\"USERDATA\\\"", self.source)

    def test_lte_http_read_buffer_has_margin_for_command_poll_body(self) -> None:
        self.assertIn("#define AT_RESPONSE_BUFFER_SIZE 1536", self.source)
        self.assertIn("uart_driver_install(uart_num, AT_RESPONSE_BUFFER_SIZE * 2", self.source)
        self.assertIn('"AT+HTTPREAD", "OK", CONFIG_EGOLINK_SIM7670_LTE_HTTP_ACTION_TIMEOUT_MS', self.source)
        self.assertIn("LTE_HTTP_READ_AT_FAILED", self.source)
        self.assertIn("LTE_HTTP_READ_BODY_PARSE_FAILED", self.source)

    def test_component_sends_bounded_at_queries_and_parses_common_gnss_lines(self) -> None:
        combined = self.header + self.source
        for token in [
            "sim7670_gnss_request_location",
            "SIM7670_GNSS_RAW_RESPONSE_MAX",
            "AT+CGNSSPWR=1",
            "AT+CGNSSINFO",
            "AT+CGPSINFO",
            "+CGNSSINFO:",
            "+CGPSINFO:",
            "parse_coordinate",
            "KNOT_TO_MPS",
            "at_unreachable",
            "uart_init_failed",
            "no_fix",
            'report->fix ? "observed" : "unverified"',
        ]:
            with self.subTest(token=token):
                self.assertIn(token, combined)

    def test_request_location_uses_sim7670_backend_without_changing_envelope(self) -> None:
        combined = self.app_main + self.main_cmake
        for token in [
            '#include "sim7670_gnss.h"',
            "sim7670_gnss",
            "sim7670_gnss_request_location",
            '\\"event_type\\":\\"location_report\\"',
            '\\"source\\":\\"%s\\"',
            "sim7670g_firmware_gnss",
            "sim7670g_uart_at",
            "uart_at",
            '\\"gnss_query_ok\\":%s',
            '\\"raw_command\\":\\"%s\\"',
            '\\"raw_response\\":\\"%s\\"',
            "firmware uploaded SIM7670G GNSS location_report",
        ]:
            with self.subTest(token=token):
                self.assertIn(token, combined)

    def test_command_poll_task_has_stack_margin_for_gnss_location_path(self) -> None:
        self.assertIn("#define COMMAND_POLL_TASK_STACK_SIZE 12288", self.app_main)
        self.assertIn(
            'xTaskCreate(command_poll_task, "command_poll_task", COMMAND_POLL_TASK_STACK_SIZE',
            self.app_main,
        )

    def test_docs_keep_fw002b_capability_boundary_clear(self) -> None:
        for token in [
            "FW-002B SIM7670G firmware GNSS AT query",
            "source=sim7670g_firmware_gnss",
            "source_status=unverified",
            "source_status=observed",
            "prove outdoor GNSS acceptance",
            "Outdoor USB-Free validation remains a separate",
            "CONFIG_EGOLINK_SIM7670_GNSS_ENABLED is not set",
            "CONFIG_EGOLINK_SIM7670_LTE_STATUS_ENABLED",
            "gnss_state=at_unreachable",
        ]:
            with self.subTest(token=token):
                self.assertIn(token, self.readme + self.protocol_doc + self.defaults)


if __name__ == "__main__":
    unittest.main()

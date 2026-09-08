"""Offline LOC-021P checks for bounded SIM7670 sensor callbacks.

No test initializes UART, invokes a callback, starts a task, controls a modem,
or contacts a SIM/network. The actual target sources and API harness are only
strictly cross-compiled and relocatable-linked for ESP32-S3.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ROOT / "firmware" / "mqtt_heartbeat" / "components"
ADAPTER = COMPONENTS / "sim7670_location_modem_adapter"
ADAPTER_HEADER = ADAPTER / "include" / "sim7670_location_modem_adapter.h"
ADAPTER_SOURCE = ADAPTER / "sim7670_location_modem_adapter.c"
ADAPTER_CMAKE = ADAPTER / "CMakeLists.txt"
SIM = COMPONENTS / "sim7670_gnss"
SIM_HEADER = SIM / "include" / "sim7670_gnss.h"
SIM_SOURCE = SIM / "sim7670_gnss.c"
SIM_CMAKE = SIM / "CMakeLists.txt"
APP_MAIN = ROOT / "firmware" / "mqtt_heartbeat" / "main" / "app_main.c"


def _function(source: str, start: str, end: str) -> str:
    begin = source.index(start)
    return source[begin : source.index(end, begin)]


def _sim_compile_entry() -> tuple[dict[str, str], Path] | None:
    wanted = SIM_SOURCE.resolve()
    candidates = sorted(
        (ROOT / "tmp").glob("*/compile_commands.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for database in candidates:
        try:
            entries = json.loads(database.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for entry in entries:
            try:
                if Path(entry["file"]).resolve() == wanted and entry.get("command"):
                    return entry, database.parent
            except (KeyError, OSError):
                continue
    return None


def _additional_includes(idf: Path) -> tuple[Path, ...]:
    return (
        ADAPTER / "include",
        COMPONENTS / "location_modem_executor" / "include",
        COMPONENTS / "location_modem_arbiter" / "include",
        COMPONENTS / "location_hardware_adapter" / "include",
        COMPONENTS / "device_location_runtime" / "include",
        COMPONENTS / "location_runtime_pipeline" / "include",
        COMPONENTS / "location_engine_core" / "include",
        COMPONENTS / "location_policy_core" / "include",
        COMPONENTS / "location_state_emitter" / "include",
        COMPONENTS / "location_outbox_adapter" / "include",
        COMPONENTS / "persistent_priority_outbox" / "include",
        COMPONENTS / "platform_imu" / "include",
        COMPONENTS / "p0_delivery_runtime" / "include",
        COMPONENTS / "p0_outbox_dispatcher" / "include",
        COMPONENTS / "sos_outbox_adapter" / "include",
        idf / "components" / "esp_timer" / "include",
        idf / "components" / "mbedtls" / "mbedtls" / "include",
        idf / "components" / "mbedtls" / "port" / "include",
    )


def _compile_command(
    base_command: str,
    source: Path,
    output: Path,
    idf: Path,
) -> str:
    includes = " ".join(
        f'-I"{path}"' for path in _additional_includes(idf)
    )
    strict = (
        "-Wall -Wextra -Werror -Wconversion -Wformat=2 "
        "-Wshadow -Wsign-conversion"
    )
    replacement = f' {includes} {strict} -o "{output}" -c "{source}"'
    command, substitutions = re.subn(
        r"\s-o\s+(?:\"[^\"]+\"|\S+)\s+-c\s+.+$",
        lambda _match: replacement,
        base_command,
        count=1,
    )
    if substitutions != 1:
        raise AssertionError("could not replace compile output/source")
    return command


class Sim7670LocationModemAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.header = ADAPTER_HEADER.read_text(encoding="utf-8")
        cls.source = ADAPTER_SOURCE.read_text(encoding="utf-8")
        cls.cmake = ADAPTER_CMAKE.read_text(encoding="utf-8")
        cls.sim_header = SIM_HEADER.read_text(encoding="utf-8")
        cls.sim_source = SIM_SOURCE.read_text(encoding="utf-8")

    def test_adapter_is_default_off_unwired_and_creates_no_task(self) -> None:
        default = _function(
            self.source,
            "void egolink_sim7670_location_modem_adapter_default_config(",
            "void egolink_sim7670_location_modem_adapter_legacy_fail_closed_config(",
        )
        self.assertIn("config->enabled = false", default)
        self.assertNotIn(
            "sim7670_location_modem_adapter",
            APP_MAIN.read_text(encoding="utf-8"),
        )
        for forbidden in ("xTaskCreate", "ESP_LOG", "esp_http_client", "socket("):
            self.assertNotIn(forbidden.casefold(), self.source.casefold())
        for dependency in (
            "esp_timer",
            "freertos",
            "location_modem_executor",
            "sim7670_gnss",
        ):
            self.assertIn(dependency, self.cmake)

    def test_legacy_whole_transaction_api_is_bound_fail_closed_without_io(self) -> None:
        self.assertIn(
            "EGOLINK_SIM7670_BLOCKER_REQUEST_DEADLINE_UNSUPPORTED",
            self.source,
        )
        self.assertIn(
            "EGOLINK_SIM7670_BLOCKER_BETWEEN_AT_CANCEL_UNSUPPORTED",
            self.source,
        )
        self.assertNotIn("sim7670_gnss_request_location(", self.source)
        self.assertNotIn("sim7670_lte_query_status(", self.source)
        begin = _function(
            self.source,
            "static bool begin_callback(",
            "static egolink_modem_callback_outcome_t finish_driver_call(",
        )
        self.assertIn("CURRENT_SYNCHRONOUS_FAIL_CLOSED", begin)
        self.assertIn("DEFINITE_NO_EFFECT_FAILURE", begin)

    def test_native_binding_uses_only_additive_bounded_driver_api(self) -> None:
        self.assertIn(
            "egolink_sim7670_location_modem_adapter_bounded_config", self.source
        )
        self.assertIn("EGOLINK_SIM7670_DRIVER_NATIVE_BOUNDED", self.source)
        self.assertIn("sim7670_gnss_request_location_bounded(", self.source)
        self.assertIn("sim7670_lte_query_status_bounded(", self.source)
        self.assertNotIn("bounded_gnss_fn", self.header)
        self.assertNotIn("bounded_lte_fn", self.header)
        bind = _function(
            self.source,
            "egolink_sim7670_location_modem_adapter_bind_executor_config(",
            "egolink_sim7670_location_modem_adapter_current_status(",
        )
        self.assertIn("executor_config->execute_gnss", bind)
        self.assertIn("executor_config->execute_cell", bind)

    def test_o_and_adapter_share_esp_timer_domain_and_zero_budget_never_calls_io(self) -> None:
        normalized = " ".join(self.header.split())
        self.assertIn("esp_timer boot-monotonic milliseconds", normalized)
        begin = _function(
            self.source,
            "static bool begin_callback(",
            "static egolink_modem_callback_outcome_t finish_driver_call(",
        )
        self.assertIn("*entry_time_ms >= *deadline_time_ms", begin)
        self.assertLess(
            begin.index("*entry_time_ms >= *deadline_time_ms"),
            begin.index("return true;"),
        )
        self.assertIn("esp_timer_get_time", self.source)

    def test_bounded_driver_requires_prior_uart_init_and_keeps_legacy_apis(self) -> None:
        bounded_gnss = _function(
            self.sim_source,
            "sim7670_gnss_request_location_bounded(",
            "sim7670_lte_query_status_bounded(",
        )
        bounded_lte = _function(
            self.sim_source,
            "sim7670_lte_query_status_bounded(",
            "bool sim7670_gnss_request_location(",
        )
        for body in (bounded_gnss, bounded_lte):
            self.assertIn("sim7670_at_backend_is_initialized", body)
            self.assertIn("UART_NOT_INITIALIZED", body)
            self.assertNotIn("sim7670_gnss_init()", body)
            self.assertIn("DEFINITE_NO_EFFECT_FAILURE", body)
        legacy_gnss = _function(
            self.sim_source,
            "bool sim7670_gnss_request_location(",
            "bool sim7670_lte_query_status(",
        )
        legacy_lte = _function(
            self.sim_source,
            "bool sim7670_lte_query_status(",
            "static bool sim7670_lte_http_post_payload(",
        )
        self.assertIn("sim7670_gnss_init()", legacy_gnss)
        self.assertIn("sim7670_gnss_init()", legacy_lte)
        self.assertIn("sim7670_send_at(", legacy_gnss)
        self.assertIn("run_lte_status_query(", legacy_lte)

    def test_exclusive_uart_claim_is_task_bound_and_rejects_legacy_preclaim(self) -> None:
        for token in (
            "sim7670_at_backend_init_exclusive_current_task",
            "sim7670_at_backend_current_task_is_exclusive_owner",
            "SIM7670_LOCATION_BOUNDED_REASON_EXCLUSIVE_OWNER_MISMATCH",
        ):
            self.assertIn(token, self.sim_header)
        exclusive_init = _function(
            self.sim_source,
            "esp_err_t sim7670_at_backend_init_exclusive_current_task(",
            "esp_err_t sim7670_gnss_init(",
        )
        self.assertIn("xTaskGetCurrentTaskHandle()", exclusive_init)
        self.assertIn("s_exclusive_owner_task == current_task", exclusive_init)
        self.assertIn("s_uart_mutex != NULL", exclusive_init)
        self.assertIn("err != ESP_OK", exclusive_init)
        self.assertIn("uart_driver_delete", exclusive_init)
        self.assertNotIn("err != ESP_OK && err != ESP_ERR_INVALID_STATE", exclusive_init)
        legacy_init = _function(
            self.sim_source,
            "esp_err_t sim7670_gnss_init(",
            "static void set_status(",
        )
        self.assertIn("sim7670_at_backend_current_task_is_allowed", legacy_init)
        self.assertIn("ESP_ERR_INVALID_STATE", legacy_init)

    def test_bounded_queries_reject_foreign_task_under_exclusive_claim(self) -> None:
        bounded_gnss = _function(
            self.sim_source,
            "sim7670_gnss_request_location_bounded(",
            "sim7670_gnss_power_off_bounded(",
        )
        bounded_lte = _function(
            self.sim_source,
            "sim7670_lte_query_status_bounded(",
            "bool sim7670_gnss_request_location(",
        )
        for body in (bounded_gnss, bounded_lte):
            self.assertIn("sim7670_at_backend_current_task_is_allowed", body)
            self.assertIn(
                "SIM7670_LOCATION_BOUNDED_REASON_EXCLUSIVE_OWNER_MISMATCH",
                body,
            )
            self.assertLess(
                body.index("sim7670_at_backend_current_task_is_allowed"),
                body.index("bounded_begin("),
            )

    def test_gnss_power_off_is_one_bounded_confirmed_command(self) -> None:
        self.assertIn("sim7670_gnss_power_off_bounded", self.sim_header)
        power_off = _function(
            self.sim_source,
            "sim7670_location_bounded_outcome_t sim7670_gnss_power_off_bounded(",
            "sim7670_location_bounded_outcome_t sim7670_lte_query_status_bounded(",
        )
        self.assertIn('"AT+CGNSSPWR=0", "OK"', power_off)
        self.assertIn("bounded_begin(", power_off)
        self.assertIn("traced_at(request,", power_off)
        trace = _function(self.sim_source,
            "static sim7670_bounded_at_status_t traced_at(",
            "static sim7670_location_bounded_reason_t bounded_reason_from_at(")
        self.assertEqual(1, trace.count("sim7670_send_at_complete_bounded("))
        self.assertIn("SIM7670_LOCATION_BOUNDED_REPORT_READY", power_off)
        self.assertIn("sim7670_at_backend_current_task_is_allowed", power_off)
        self.assertNotIn("sim7670_gnss_init()", power_off)
        self.assertNotIn("uart_driver_install", power_off)

    def test_total_and_per_command_deadlines_do_not_round_waits_up(self) -> None:
        wait = _function(
            self.sim_source,
            "static TickType_t bounded_wait_ticks_floor(",
            "static int64_t bounded_command_deadline_us(",
        )
        self.assertIn("remaining_ms / tick_period_ms", wait)
        self.assertNotIn("pdMS_TO_TICKS", wait)
        send = _function(
            self.sim_source,
            "static sim7670_bounded_at_status_t sim7670_send_at_complete_bounded(",
            "static sim7670_location_bounded_reason_t bounded_reason_from_at(",
        )
        self.assertIn("bounded_command_deadline_us", send)
        command_deadline_checks = (
            send.count("now_us > command_deadline_us")
            + send.count("now_us >= command_deadline_us")
        )
        self.assertGreaterEqual(command_deadline_checks, 5)
        acquire = send.index("xSemaphoreTake")
        post_acquire = send.index("now_us = bounded_now_us()", acquire)
        flush = send.index("uart_flush_input", post_acquire)
        self.assertLess(post_acquire, flush)
        read = send.index("uart_read_bytes")
        post_read = send.index("now_us = bounded_now_us()", read)
        self.assertLess(post_read, send.index("if (read < 0)", post_read))
        finish = _function(
            self.sim_source,
            "static void bounded_finish(",
            "static bool bounded_cancel_requested(",
        )
        self.assertIn("finish_us > deadline_us", finish)
        self.assertNotIn("finish_us > deadline_us &&", finish)

    def test_tx_is_nonblocking_complete_command_plus_crlf_or_unknown(self) -> None:
        send = _function(
            self.sim_source,
            "static sim7670_bounded_at_status_t sim7670_send_at_complete_bounded(",
            "static sim7670_location_bounded_reason_t bounded_reason_from_at(",
        )
        self.assertIn("transmit[command_length] = '\\r'", send)
        self.assertIn("transmit[command_length + 1U] = '\\n'", send)
        self.assertIn("uart_tx_chars", send)
        self.assertNotIn("uart_write_bytes", send)
        self.assertIn("transmitted != transmit_length", send)
        self.assertIn("SIM7670_BOUNDED_AT_TX_INCOMPLETE", send)
        self.assertIn("commands_tx_complete", send)

    def test_cancel_is_checked_only_at_explicit_at_boundaries_without_hard_claim(self) -> None:
        prose = " ".join(self.sim_header.split())
        self.assertIn("between AT commands", prose)
        self.assertIn("never represented as hard-cancelled", prose)
        self.assertIn("bounded_cancel_at_boundary", self.sim_source)
        self.assertGreaterEqual(self.sim_source.count("bounded_cancel_at_boundary("), 5)
        self.assertIn("bool hard_cancel_supported;", self.header)
        self.assertIn("snapshot->hard_cancel_supported = false", self.source)
        self.assertIn("xPortGetCoreID", self.source)
        self.assertIn("atomic_compare_exchange_strong_explicit", self.source)

    def test_cross_core_rejection_and_snapshot_metadata_use_short_portmux(self) -> None:
        self.assertIn("portMUX_TYPE metadata_lock", self.source)
        self.assertIn("portMUX_INITIALIZE(&internal->metadata_lock)", self.source)
        record = _function(
            self.source,
            "static void record_outcome(",
            "static bool valid_request_common(",
        )
        self.assertIn("taskENTER_CRITICAL(&internal->metadata_lock)", record)
        self.assertIn("taskEXIT_CRITICAL(&internal->metadata_lock)", record)
        snapshot = _function(
            self.source,
            "egolink_sim7670_location_modem_adapter_current_status(",
            "const char *egolink_sim7670_location_adapter_status_name(",
        )
        self.assertIn("taskENTER_CRITICAL", snapshot)
        self.assertIn("taskEXIT_CRITICAL", snapshot)
        for forbidden in (
            "sim7670_gnss_request_location_bounded",
            "sim7670_lte_query_status_bounded",
            "cancel_requested(",
        ):
            self.assertNotIn(forbidden, record)

    def test_timeout_partial_parse_and_invalid_evidence_are_unknown(self) -> None:
        self.assertIn("partial_or_unknown", self.sim_header)
        self.assertIn("SIM7670_LOCATION_BOUNDED_OUTCOME_UNKNOWN", self.sim_source)
        self.assertIn("SIM7670_LOCATION_BOUNDED_REASON_PARSE_INVALID", self.sim_source)
        finish = _function(
            self.source,
            "static egolink_modem_callback_outcome_t finish_driver_call(",
            "typedef struct {\n    const egolink_location_modem_sensor_request_t *request;",
        )
        self.assertIn("REPORT_INCOMPLETE_OR_AMBIGUOUS", finish)
        self.assertIn("EGOLINK_MODEM_CALLBACK_OUTCOME_UNKNOWN", finish)
        self.assertIn("native_result_contract_valid", self.source)
        self.assertIn("sim7670_gnss_report_init(report)", self.source)
        self.assertIn("sim7670_lte_report_init(report)", self.source)

    def test_report_classifiers_require_all_m_evidence_and_exact_no_fix(self) -> None:
        gnss = _function(
            self.source,
            "egolink_sim7670_location_classify_gnss_report(",
            "static bool complete_at_query(",
        )
        self.assertIn("complete_gnss_query(&report->cgnssinfo_query)", gnss)
        self.assertIn("complete_gnss_query(&report->cgpsinfo_query)", gnss)
        self.assertIn("cgnssinfo_query.no_fix_observed", gnss)
        self.assertIn("cgpsinfo_query.no_fix_observed", gnss)
        self.assertIn("no_gnss_measurement_is_marked_valid", gnss)
        lte = _function(
            self.source,
            "egolink_sim7670_location_classify_lte_report(",
            "static bool now_ms(",
        )
        for query in (
            "cpin_query",
            "cops_query",
            "cereg_query",
            "cgatt_query",
            "cgdcont_query",
            "cgact_query",
            "cgpaddr_query",
            "csq_query",
            "cpsi_query",
        ):
            self.assertIn(f"complete_at_query(&report->{query})", lte)
        for field in ("mcc", "mnc", "tac", "cell_id"):
            self.assertIn(f"report->{field}", self.source)

    def test_audit_snapshot_has_no_sensitive_report_content(self) -> None:
        marker = "/* This snapshot deliberately contains no report"
        start = self.header.index("typedef struct {", self.header.index(marker))
        snapshot = self.header[
            start : self.header.index(
                "} egolink_sim7670_location_modem_adapter_snapshot_t;"
            )
        ]
        for forbidden in (
            "sim7670_gnss_report_t",
            "sim7670_lte_report_t",
            "coordinate",
            "latitude",
            "longitude",
            "cell_id",
            "raw_response",
            "credential",
        ):
            self.assertNotIn(forbidden, snapshot.casefold())

    def test_actual_sources_and_api_harness_strictly_cross_compile_and_link(self) -> None:
        found = _sim_compile_entry()
        if found is None:
            self.skipTest("generated ESP32-S3 SIM7670 compile entry unavailable")
        entry, directory = found
        idf = Path(os.environ.get("IDF_PATH", "C:/Espressif/v5.4.2/esp-idf"))
        self.assertTrue(idf.is_dir())
        harness_text = textwrap.dedent(
            """
            #include "sim7670_location_modem_adapter.h"

            static egolink_sim7670_location_modem_adapter_t adapter;
            static volatile unsigned int sink;

            void sim7670_location_adapter_link_probe(void)
            {
                egolink_sim7670_location_modem_adapter_config_t config;
                egolink_sim7670_location_modem_adapter_snapshot_t snapshot;
                egolink_location_modem_executor_config_t executor_config;
                sim7670_gnss_report_t gnss = {0};
                sim7670_lte_report_t lte = {0};
                sim7670_location_bounded_result_t bounded;

                egolink_sim7670_location_modem_adapter_default_config(&config);
                sink = (unsigned int)
                    egolink_sim7670_location_modem_adapter_init(&adapter, &config);
                egolink_sim7670_location_modem_adapter_legacy_fail_closed_config(
                    &config, 0);
                sink = (unsigned int)
                    egolink_sim7670_location_modem_adapter_init(&adapter, &config);
                egolink_sim7670_location_modem_adapter_bounded_config(
                    &config, 0,
                    EGOLINK_SIM7670_LOCATION_DEFAULT_COMMAND_CAP_MS);
                sink = (unsigned int)
                    egolink_sim7670_location_modem_adapter_init(&adapter, &config);
                egolink_location_modem_executor_default_config(&executor_config);
                sink = (unsigned int)
                    egolink_sim7670_location_modem_adapter_bind_executor_config(
                        &adapter, &executor_config);
                sink = (unsigned int)
                    egolink_sim7670_location_classify_gnss_report(&gnss);
                sink = (unsigned int)
                    egolink_sim7670_location_classify_lte_report(&lte);
                sim7670_location_bounded_result_init(&bounded);
                sink = (unsigned int)
                    egolink_sim7670_location_modem_adapter_current_status(
                        &adapter, &snapshot);
                sink += (unsigned int)
                    egolink_sim7670_location_adapter_status_name(
                        snapshot.last_status)[0];
            }
            """
        )
        with tempfile.TemporaryDirectory(prefix="egolink-loc021p-") as temporary:
            temp = Path(temporary)
            harness = temp / "adapter_harness.c"
            adapter_object = temp / "adapter.o"
            harness_object = temp / "harness.o"
            linked = temp / "adapter_linked.o"
            harness.write_text(harness_text, encoding="utf-8")
            for source, output in (
                (ADAPTER_SOURCE, adapter_object),
                (harness, harness_object),
            ):
                command = _compile_command(
                    entry["command"], source, output, idf
                )
                result = subprocess.run(
                    command,
                    cwd=directory,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                    env=os.environ.copy(),
                )
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            compiler = entry["command"].split(" ", 1)[0]
            result = subprocess.run(
                [
                    compiler,
                    "-nostdlib",
                    "-Wl,-r",
                    str(adapter_object),
                    str(harness_object),
                    "-o",
                    str(linked),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertGreater(linked.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()

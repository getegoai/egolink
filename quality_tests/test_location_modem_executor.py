"""Focused LOC-021O checks for the dormant no-I/O modem composition seam.

The production source and an API harness are strictly ESP32-S3 compiled and
relocatable-linked. No target code runs and no task, UART, SIM or network API
is invoked by this suite.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ROOT / "firmware" / "mqtt_heartbeat" / "components"
COMPONENT = COMPONENTS / "location_modem_executor"
ARBITER = COMPONENTS / "location_modem_arbiter"
HEADER = COMPONENT / "include" / "location_modem_executor.h"
SOURCE = COMPONENT / "location_modem_executor.c"
CMAKE = COMPONENT / "CMakeLists.txt"
APP_MAIN = ROOT / "firmware" / "mqtt_heartbeat" / "main" / "app_main.c"
PACKET = ROOT / "docs" / "tasks" / "active" / "LOC-021_DEVICE_LOCATION_INTEGRATION.md"


def _toolchain() -> tuple[Path, Path, Path] | None:
    compiler_candidates = (
        shutil.which("xtensa-esp32s3-elf-gcc"),
        Path(
            "C:/Espressif/tools/xtensa-esp-elf/esp-14.2.0_20241119/"
            "xtensa-esp-elf/bin/xtensa-esp32s3-elf-gcc.exe"
        ),
    )
    compiler = next(
        (Path(value) for value in compiler_candidates if value and Path(value).is_file()),
        None,
    )
    idf_candidates = (
        Path(os.environ["IDF_PATH"]) if os.environ.get("IDF_PATH") else None,
        Path("C:/Espressif/v5.4.2/esp-idf"),
    )
    idf = next((value for value in idf_candidates if value and value.is_dir()), None)
    configs = sorted((ROOT / "tmp").glob("*/config/sdkconfig.h"))
    if compiler is None or idf is None or not configs:
        return None
    return compiler, idf, configs[-1].parent


def _include_paths(idf: Path, config: Path) -> tuple[Path, ...]:
    return (
        config,
        COMPONENT / "include",
        ARBITER / "include",
        COMPONENTS / "location_hardware_adapter" / "include",
        COMPONENTS / "device_location_runtime" / "include",
        COMPONENTS / "location_runtime_pipeline" / "include",
        COMPONENTS / "location_engine_core" / "include",
        COMPONENTS / "location_policy_core" / "include",
        COMPONENTS / "location_state_emitter" / "include",
        COMPONENTS / "location_outbox_adapter" / "include",
        COMPONENTS / "persistent_priority_outbox" / "include",
        COMPONENTS / "platform_imu" / "include",
        COMPONENTS / "sim7670_gnss" / "include",
        COMPONENTS / "p0_delivery_runtime" / "include",
        COMPONENTS / "p0_outbox_dispatcher" / "include",
        COMPONENTS / "sos_outbox_adapter" / "include",
        idf / "components" / "esp_common" / "include",
        idf / "components" / "mbedtls" / "mbedtls" / "include",
        idf / "components" / "mbedtls" / "port" / "include",
    )


def _function(source: str, start: str, end: str) -> str:
    begin = source.index(start)
    return source[begin : source.index(end, begin)]


def _api_harness() -> str:
    return textwrap.dedent(
        r"""
        #include <stdint.h>
        #include "location_modem_executor.h"

        static egolink_location_modem_executor_t executor;
        static egolink_outbox_t outbox;
        static egolink_location_outbox_adapter_t location_adapter;
        static egolink_p0_delivery_runtime_t delivery;
        static egolink_location_runtime_scratch_t scratch;
        static volatile unsigned int sink;

        void location_modem_executor_link_probe(void)
        {
            egolink_location_modem_executor_config_t config;
            egolink_location_modem_executor_snapshot_t snapshot;
            egolink_location_modem_enqueue_result_t sos;
            egolink_location_modem_enqueue_result_t urgent;
            egolink_location_modem_prepare_result_t prepare;
            egolink_location_modem_execute_result_t execute;
            egolink_location_modem_settle_result_t settle;
            egolink_location_modem_process_result_t process;
            egolink_location_hardware_mapped_input_t mapped = {0};

            egolink_location_modem_executor_default_config(&config);
            sink = (unsigned int)egolink_location_modem_executor_init(
                &executor, &config, &outbox, &location_adapter, &delivery);
            config.enabled = true;
            sink = (unsigned int)egolink_location_modem_executor_init(
                &executor, &config, &outbox, &location_adapter, &delivery);
            sink = (unsigned int)
                egolink_location_modem_executor_process_mapped_input(
                    &executor, &mapped, UINT64_C(1), &scratch, &process);
            sink = (unsigned int)
                egolink_location_modem_executor_signal_durable_sos(
                    &executor,
                    EGOLINK_MODEM_DURABLE_SOS_COMMITTED_OR_DUPLICATE,
                    UINT64_C(30000), &sos, &urgent);
            sink = (unsigned int)
                egolink_location_modem_executor_request_gnss_status(
                    &executor, UINT64_C(10000), &urgent);
            sink = (unsigned int)egolink_location_modem_executor_prepare_next(
                &executor, UINT64_C(2), &prepare);
            sink = (unsigned int)
                egolink_location_modem_executor_execute_prepared(
                    &executor, UINT64_C(3), &execute);
            sink = (unsigned int)
                egolink_location_modem_executor_settle_prepared(
                    &executor, (const egolink_location_hardware_identity_t *)0,
                    UINT64_C(4), &scratch, &settle);
            sink = (unsigned int)
                egolink_location_modem_executor_current_status(
                    &executor, &snapshot);
            sink += (unsigned int)
                egolink_location_modem_executor_status_name(snapshot.enabled
                    ? EGOLINK_MODEM_EXECUTOR_OK
                    : EGOLINK_MODEM_EXECUTOR_DISABLED_STATUS)[0];
        }
        """
    )


class LocationModemExecutorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.header = HEADER.read_text(encoding="utf-8")
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.cmake = CMAKE.read_text(encoding="utf-8")

    def test_component_is_default_off_unwired_and_has_no_direct_io(self) -> None:
        self.assertIn("config->enabled = false", self.source)
        self.assertNotIn("location_modem_executor", APP_MAIN.read_text(encoding="utf-8"))
        for dependency in (
            "device_location_runtime",
            "location_hardware_adapter",
            "location_modem_arbiter",
            "p0_delivery_runtime",
        ):
            self.assertIn(dependency, self.cmake)
        for forbidden in (
            "xTaskCreate",
            "uart_",
            "sim7670_gnss_request_location",
            "sim7670_lte_query_status",
            "esp_http_client",
            "socket(",
        ):
            self.assertNotIn(forbidden.casefold(), self.source.casefold())

    def test_init_never_reads_uninitialized_opaque_storage(self) -> None:
        init = _function(
            self.source,
            "egolink_modem_executor_status_t egolink_location_modem_executor_init(",
            "static void update_process_queue_state(",
        )
        clear = init.index("(void)memset(executor, 0, sizeof(*executor))")
        derive = init.index("internal_of(executor)")
        self.assertLess(clear, derive)
        self.assertNotIn("valid_magic", init[:derive])
        self.assertIn(
            "egolink_p0_delivery_runtime_dependencies_match", init
        )
        self.assertIn("delivery_runtime, shared_outbox, location_adapter", init)

    def test_external_owner_contract_allows_only_locked_sos_during_execute(self) -> None:
        prose = " ".join(self.header.split())
        self.assertIn("complete O signal API is not", prose)
        self.assertIn("acquire the same owner and call signal_durable_sos", prose)
        self.assertIn("signal_durable_sos directly from an ISR", prose)
        self.assertIn("Settle starts only after execute_prepared has returned", prose)

    def test_storage_is_fixed_and_not_an_outbox(self) -> None:
        self.assertIn("CONTEXT_BYTES (24U * 1024U)", self.header)
        self.assertIn("sizeof(modem_executor_internal_t)", self.source)
        self.assertNotRegex(self.source, r"\b(malloc|calloc|realloc|free)\s*\(")
        for token in ("payload[", "response[", "authorization", "credential"):
            self.assertNotIn(token.casefold(), self.source.casefold())

    def test_k_commit_and_queued_attempts_are_separate_truths(self) -> None:
        process = _function(
            self.source,
            "egolink_location_modem_executor_process_mapped_input(",
            "egolink_location_modem_executor_signal_durable_sos(",
        )
        self.assertIn("egolink_device_location_runtime_process", process)
        self.assertIn("new_input_committed", process)
        self.assertIn("pipeline->published", process)
        self.assertNotIn("EGOLINK_DEVICE_LOCATION_ACTION_SUCCEEDED", self.source)
        self.assertIn("arbiter admission is exposed only as O QUEUED", self.header)
        self.assertIn("k_partial_failure_preserved", self.header)

    def test_durable_sos_signal_orders_transport_before_urgent_gnss(self) -> None:
        signal = _function(
            self.source,
            "egolink_location_modem_executor_signal_durable_sos(",
            "egolink_location_modem_executor_request_gnss_status(",
        )
        preempt = signal.index("egolink_p0_delivery_runtime_signal_durable_sos")
        critical = signal.index(
            "EGOLINK_MODEM_COMMAND_DURABLE_SOS_TRANSPORT", preempt
        )
        urgent = signal.index(
            "EGOLINK_MODEM_COMMAND_SOS_URGENT_GNSS_ACQUIRE", critical
        )
        self.assertLess(preempt, critical)
        self.assertLess(critical, urgent)
        self.assertIn("COMMITTED_OR_DUPLICATE", signal)

    def test_split_phase_releases_owner_around_only_execution(self) -> None:
        prepare = _function(
            self.source,
            "egolink_location_modem_executor_prepare_next(",
            "static bool completion_time_within_bound(",
        )
        execute = _function(
            self.source,
            "egolink_location_modem_executor_execute_prepared(",
            "static egolink_modem_reported_outcome_t transport_reported_outcome(",
        )
        settle = _function(
            self.source,
            "egolink_location_modem_executor_settle_prepared(",
            "egolink_location_modem_executor_current_status(",
        )
        self.assertIn("egolink_p0_delivery_runtime_prepare", prepare)
        self.assertIn("egolink_modem_arbiter_mark_execution_started", prepare)
        self.assertNotIn("execute_gnss(", prepare)
        self.assertIn("egolink_p0_delivery_runtime_execute_prepared", execute)
        self.assertIn("internal->execute_gnss(", execute)
        self.assertNotIn("egolink_device_location_runtime_process", execute)
        self.assertIn("egolink_p0_delivery_runtime_settle_prepared", settle)
        self.assertIn("egolink_modem_arbiter_complete", settle)

    def test_both_route_mismatches_retarget_exact_prepared_ticket(self) -> None:
        prepare = _function(
            self.source,
            "egolink_location_modem_executor_prepare_next(",
            "static bool completion_time_within_bound(",
        )
        route_map = _function(
            self.source,
            "static egolink_modem_command_kind_t kind_for_route(",
            "static void reconcile_enqueue_removals(",
        )
        self.assertIn("EGOLINK_P0_OUTBOX_ROUTE_MANUAL_SOS", route_map)
        self.assertIn("EGOLINK_MODEM_COMMAND_DURABLE_SOS_TRANSPORT", route_map)
        self.assertIn("EGOLINK_P0_OUTBOX_ROUTE_LOCATION_STATE", route_map)
        self.assertIn("EGOLINK_MODEM_COMMAND_LOCATION_TRANSPORT", route_map)
        self.assertIn("result->p0_result.route != expected_route", prepare)
        mismatch = prepare[prepare.index("result->p0_result.route != expected_route") :]
        self.assertIn("egolink_modem_arbiter_retarget_prepared", mismatch)
        self.assertIn("prepared_ticket_cancelled_without_execution", prepare)
        self.assertIn("prepared_ticket_retargeted", prepare)
        self.assertIn("egolink_modem_arbiter_mark_execution_started", mismatch)
        self.assertNotIn("release_active(internal)", mismatch)
        self.assertIn("EGOLINK_MODEM_EXECUTOR_PHASE_EXECUTION_READY", mismatch)
        self.assertIn("EGOLINK_MODEM_EXECUTOR_PHASE_RESULT_READY", mismatch)

    def test_repeated_sos_signal_is_bounded_but_repeats_p0_hint(self) -> None:
        signal = _function(
            self.source,
            "egolink_location_modem_executor_signal_durable_sos(",
            "egolink_location_modem_executor_request_gnss_status(",
        )
        self.assertIn("egolink_p0_delivery_runtime_signal_durable_sos", signal)
        self.assertIn("internal->sos_transport_outstanding", signal)
        self.assertIn("followup_scan_deferred = true", signal)
        self.assertIn("internal->deferred_sos_transport = true", signal)
        self.assertIn("internal->urgent_gnss_outstanding", signal)
        self.assertIn("already_outstanding = true", signal)
        deferred = _function(
            self.source,
            "static egolink_modem_executor_status_t requeue_one_deferred(",
            "egolink_location_modem_executor_prepare_next(",
        )
        self.assertIn("!internal->sos_transport_outstanding", deferred)

    def test_sensor_timeout_cancel_and_report_mapping_fail_closed(self) -> None:
        execute = _function(
            self.source,
            "egolink_location_modem_executor_execute_prepared(",
            "static egolink_modem_reported_outcome_t transport_reported_outcome(",
        )
        settle = _function(
            self.source,
            "egolink_location_modem_executor_settle_prepared(",
            "egolink_location_modem_executor_current_status(",
        )
        self.assertIn("EGOLINK_MODEM_SAFE_POINT_BETWEEN_AT_COMMANDS", execute)
        self.assertIn(".hard_cancel_supported = false", execute)
        self.assertIn("completion_time_within_bound", execute)
        self.assertIn("egolink_modem_arbiter_cancel_requested", execute)
        self.assertIn("EGOLINK_MODEM_REPORTED_OUTCOME_UNKNOWN", settle)
        self.assertIn("egolink_location_hardware_map_gnss", self.source)
        self.assertIn("egolink_location_hardware_map_cell", self.source)
        self.assertIn("EGOLINK_LOCATION_HARDWARE_MAP_CELL_ID_UNAVAILABLE", self.source)
        self.assertIn("egolink_location_hardware_map_lte_state", self.source)

    def test_cancel_first_discards_late_executor_claim_as_unknown(self) -> None:
        settle = _function(
            self.source,
            "egolink_location_modem_executor_settle_prepared(",
            "egolink_location_modem_executor_current_status(",
        )
        cancel_branch = settle[
            settle.index("if (cancel_won)") : settle.index(
                "} else if (!internal->active_callback_contract_valid)"
            )
        ]
        self.assertIn("EGOLINK_MODEM_REPORTED_OUTCOME_UNKNOWN", cancel_branch)
        arbiter_complete = (ARBITER / "location_modem_arbiter.c").read_text(
            encoding="utf-8"
        )
        self.assertIn("late_executor_result_discarded = true", arbiter_complete)

    def test_packet_records_o_boundaries_and_non_claims(self) -> None:
        packet = PACKET.read_text(encoding="utf-8")
        self.assertIn("LOC-021O", packet)
        self.assertIn("location_modem_executor", packet)
        self.assertIn("queued", packet.casefold())
        self.assertIn("ACTION_SUCCEEDED", packet)
        self.assertIn("P0-LOC", packet)
        self.assertIn("NOT_RUN", packet)

    def test_actual_sources_and_api_harness_strictly_cross_compile_and_link(self) -> None:
        toolchain = _toolchain()
        if toolchain is None:
            self.skipTest("ESP32-S3 compiler/IDF config is unavailable")
        compiler, idf, config = toolchain
        common = [
            str(compiler),
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wconversion",
            "-Wformat=2",
            "-Wshadow",
            "-Wsign-conversion",
            "-fstack-usage",
        ]
        for include in _include_paths(idf, config):
            common.extend(("-I", str(include)))
        with tempfile.TemporaryDirectory(prefix="egolink-modem-executor-") as temporary:
            temp = Path(temporary)
            harness_source = temp / "location_modem_executor_harness.c"
            harness_source.write_text(_api_harness(), encoding="utf-8")
            objects = []
            for source in (SOURCE, ARBITER / "location_modem_arbiter.c", harness_source):
                output = temp / f"{source.stem}.o"
                result = subprocess.run(
                    [*common, "-c", str(source), "-o", str(output)],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
                self.assertEqual(0, result.returncode, msg=result.stdout + result.stderr)
                objects.append(output)
            linked = temp / "location_modem_executor_linked.o"
            result = subprocess.run(
                [str(compiler), "-nostdlib", "-Wl,-r", *map(str, objects), "-o", str(linked)],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            self.assertEqual(0, result.returncode, msg=result.stdout + result.stderr)
            self.assertGreater(linked.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()

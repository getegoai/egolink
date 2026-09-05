"""Offline LOC-021Q checks for the dormant exclusive modem owner.

The suite reads source and strictly cross-compiles/relocatable-links target C.
It never calls start(), initializes UART, creates a task, or touches hardware,
a SIM, storage, transport, or a network.
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
OWNER = COMPONENTS / "sim7670_location_modem_owner"
HEADER = OWNER / "include" / "sim7670_location_modem_owner.h"
SOURCE = OWNER / "sim7670_location_modem_owner.c"
CMAKE = OWNER / "CMakeLists.txt"
KCONFIG = OWNER / "Kconfig.projbuild"
SIM = COMPONENTS / "sim7670_gnss"
SIM_SOURCE = SIM / "sim7670_gnss.c"
APP_MAIN = ROOT / "firmware" / "mqtt_heartbeat" / "main" / "app_main.c"
PACKET = ROOT / "docs" / "tasks" / "active" / "LOC-021_DEVICE_LOCATION_INTEGRATION.md"


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
        OWNER / "include",
        SIM / "include",
        COMPONENTS / "sim7670_location_modem_adapter" / "include",
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
    includes = " ".join(f'-I"{path}"' for path in _additional_includes(idf))
    strict = (
        "-Wall -Wextra -Werror -Wconversion -Wformat=2 "
        "-Wshadow -Wsign-conversion -fstack-usage"
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


class Sim7670LocationModemOwnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.header = HEADER.read_text(encoding="utf-8")
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.cmake = CMAKE.read_text(encoding="utf-8")
        cls.kconfig = KCONFIG.read_text(encoding="utf-8")

    def test_compile_boundary_is_default_off_and_explicitly_unwired(self) -> None:
        self.assertRegex(
            self.kconfig,
            r"config EGOLINK_SIM7670_LOCATION_MODEM_OWNER_ENABLED\s+"
            r"bool[\s\S]+?default n",
        )
        self.assertIn("Compile-only boundary", self.kconfig)
        self.assertIn("LTE status itself still has direct callers", self.kconfig)
        self.assertNotIn(
            "sim7670_location_modem_owner",
            APP_MAIN.read_text(encoding="utf-8"),
        )
        default = _function(
            self.source,
            "void egolink_sim7670_location_modem_owner_default_config(",
            "egolink_sim7670_modem_owner_status_t\n"
            "egolink_sim7670_location_modem_owner_init(",
        )
        self.assertIn("config->enabled = false", default)
        init = _function(
            self.source,
            "egolink_sim7670_location_modem_owner_init(",
            "egolink_sim7670_modem_owner_status_t\n"
            "egolink_sim7670_location_modem_owner_start(",
        )
        self.assertIn("EGOLINK_SIM7670_MODEM_OWNER_BUILD_DISABLED", init)

    def test_one_static_pinned_boot_long_task_and_no_delete(self) -> None:
        self.assertEqual(1, self.source.count("xTaskCreateStaticPinnedToCore("))
        self.assertNotIn("xTaskCreatePinnedToCore(", self.source)
        self.assertNotIn("xTaskCreate(", self.source)
        self.assertNotIn("vTaskDelete", self.source)
        self.assertIn("boot-long", self.header)
        self.assertIn("There is no delete/deinit API", self.header)
        self.assertIn("StaticTask_t task_storage", self.source)
        self.assertIn("StackType_t task_stack", self.source)
        start = _function(
            self.source,
            "egolink_sim7670_location_modem_owner_start(",
            "static egolink_sim7670_modem_owner_status_t external_gate(",
        )
        claim = start.index("internal->start_claimed = true")
        create = start.index("xTaskCreateStaticPinnedToCore(", claim)
        publish = start.index("internal->task_created = true", create)
        self.assertLess(claim, create)
        self.assertLess(create, publish)
        self.assertIn("internal->start_claimed = false", start)
        self.assertIn("metadata-locked claim", self.header)
        self.assertIn("sizeof(StackType_t) == 1U", self.source)
        self.assertIn("TASK_STACK_BYTES (16U * 1024U)", self.header)
        self.assertNotRegex(self.source, r"\b(malloc|calloc|realloc|free)\s*\(")

    def test_owner_task_exclusively_initializes_uart_before_any_work(self) -> None:
        task = _function(
            self.source,
            "static void owner_task_main(void *context)",
            "static bool valid_publish_intent(",
        )
        exclusive_init = task.index(
            "sim7670_at_backend_init_exclusive_current_task()"
        )
        owner_proof = task.index(
            "sim7670_at_backend_current_task_is_exclusive_owner()",
            exclusive_init,
        )
        initial_stop = task.index("run_gnss_power_off(", owner_proof)
        active = task.index("EGOLINK_SIM7670_MODEM_OWNER_ACTIVE", initial_stop)
        drive = task.index("drive_one_command(internal)", active)
        self.assertLess(exclusive_init, owner_proof)
        self.assertLess(owner_proof, initial_stop)
        self.assertLess(initial_stop, active)
        self.assertLess(active, drive)
        self.assertEqual(
            1,
            self.source.count("sim7670_at_backend_init_exclusive_current_task()"),
        )
        self.assertNotIn("sim7670_gnss_init()", self.source)

    def test_composes_existing_adapter_and_executor_with_exact_borrowed_dependencies(self) -> None:
        init = _function(
            self.source,
            "egolink_sim7670_location_modem_owner_init(",
            "egolink_sim7670_modem_owner_status_t\n"
            "egolink_sim7670_location_modem_owner_start(",
        )
        bounded = init.index(
            "egolink_sim7670_location_modem_adapter_bounded_config"
        )
        adapter_init = init.index(
            "egolink_sim7670_location_modem_adapter_init", bounded
        )
        bind = init.index(
            "egolink_sim7670_location_modem_adapter_bind_executor_config",
            adapter_init,
        )
        wrap = init.index(
            "executor_config.execute_gnss = execute_gnss_with_power_off", bind
        )
        executor_init = init.index("egolink_location_modem_executor_init", wrap)
        self.assertLess(bounded, adapter_init)
        self.assertLess(adapter_init, bind)
        self.assertLess(bind, wrap)
        self.assertLess(wrap, executor_init)
        self.assertIn(
            "shared_outbox,\n        location_adapter, delivery_runtime",
            init,
        )
        for forbidden in (
            "egolink_modem_arbiter_init",
            "egolink_device_location_runtime_init",
            "egolink_location_runtime_pipeline_init",
            "egolink_p0_delivery_runtime_init",
            "egolink_location_outbox_adapter_init",
        ):
            self.assertNotIn(forbidden, self.source)

    def test_execute_is_the_only_unlocked_o_phase_and_sos_is_the_only_racing_ingress(self) -> None:
        drive = _function(
            self.source,
            "static owner_drive_result_t drive_one_command(",
            "static void signal_startup_once(",
        )
        release = drive.index("xSemaphoreGive(internal->owner_mutex)")
        execute = drive.index(
            "egolink_location_modem_executor_execute_prepared", release
        )
        reacquire = drive.index(
            "xSemaphoreTake(internal->owner_mutex, portMAX_DELAY)", execute
        )
        settle = drive.index("settle_ready_command(", reacquire)
        self.assertLess(release, execute)
        self.assertLess(execute, reacquire)
        self.assertLess(reacquire, settle)
        self.assertIn("execution_active, true", drive)
        self.assertIn("execution_active, false", drive)

        process = _function(
            self.source,
            "egolink_sim7670_location_modem_owner_process_mapped_input(",
            "egolink_sim7670_modem_owner_status_t\n"
            "egolink_sim7670_location_modem_owner_signal_durable_sos(",
        )
        request = _function(
            self.source,
            "egolink_sim7670_location_modem_owner_request_gnss_status(",
            "egolink_sim7670_modem_owner_status_t\n"
            "egolink_sim7670_location_modem_owner_current_status(",
        )
        signal = _function(
            self.source,
            "egolink_sim7670_location_modem_owner_signal_durable_sos(",
            "egolink_sim7670_modem_owner_status_t\n"
            "egolink_sim7670_location_modem_owner_request_gnss_status(",
        )
        self.assertIn("external_gate(internal, false, false)", process)
        self.assertIn("external_gate(internal, false, false)", request)
        self.assertIn("external_gate(internal, true, true)", signal)
        gate = _function(
            self.source,
            "static egolink_sim7670_modem_owner_status_t external_gate(",
            "static bool take_external_owner(",
        )
        self.assertIn("fatal_recovery_required", gate)
        self.assertIn("cleanup_recovery_required", gate)
        self.assertIn("Never call this from an ISR", self.header)

        self.assertIn(
            "EGOLINK_MODEM_EXECUTOR_INPUT_COMMITTED_QUEUE_PARTIAL", process
        )
        self.assertIn("MAPPED_INPUT_PARTIAL", process)
        self.assertIn("SOS_SIGNAL_PARTIAL", signal)
        self.assertNotRegex(
            signal,
            r"EGOLINK_MODEM_EXECUTOR_QUEUE_PARTIAL\)\s*\{\s*"
            r"record_status\([^;]+OWNER_QUEUED",
        )

    def test_full_durable_sos_ingress_delegates_to_o_only_when_idle(self) -> None:
        wrapper = _function(
            self.source,
            "egolink_sim7670_location_modem_owner_process_durable_sos(",
            "egolink_sim7670_modem_owner_status_t\n"
            "egolink_sim7670_location_modem_owner_signal_durable_sos(",
        )
        self.assertIn("external_gate(internal, false, true)", wrapper)
        self.assertIn(
            "egolink_location_modem_executor_process_durable_sos", wrapper
        )
        self.assertIn("&internal->scratch", wrapper)
        self.assertIn("update_sequence_after_durable_sos", wrapper)
        self.assertIn("DURABLE_SOS_ACCEPTED", wrapper)
        self.assertIn("DURABLE_SOS_PARTIAL", wrapper)
        prose = " ".join(self.header.split())
        self.assertIn("If SOS arrives during", prose)
        self.assertIn("first use signal_durable_sos", prose)
        self.assertIn("future shared replayable", prose)
        self.assertIn("snapshot telemetry is never an identity reservation", prose)
        self.assertIn("physical edge occurrence time", prose)
        self.assertIn("processing time or snapshot-read time", prose)
        snapshot_start = self.header.index(
            "typedef struct {", self.header.index("/* No coordinate, cell identity")
        )
        snapshot = self.header[
            snapshot_start : self.header.index(
                "} egolink_sim7670_location_modem_owner_snapshot_t;",
                snapshot_start,
            )
        ]
        self.assertNotIn("next_capture_sequence_id", snapshot)

    def test_gnss_budget_reserves_never_cancelled_power_off(self) -> None:
        wrapper = _function(
            self.source,
            "static egolink_modem_callback_outcome_t execute_gnss_with_power_off(",
            "static bool build_capture_identity(",
        )
        admission = wrapper.index(
            "remaining_ms <= internal->gnss_power_off_timeout_ms"
        )
        reserve = wrapper.index(
            "acquisition_request.timeout_ms = request->timeout_ms -",
            admission,
        )
        acquire = wrapper.index("internal->native_gnss_execute(", reserve)
        remaining = wrapper.index(
            "remaining_before_deadline_ms(request, &remaining_ms)", acquire
        )
        truncate = wrapper.index(
            "remaining_ms < internal->gnss_power_off_timeout_ms", remaining
        )
        stop = wrapper.index("run_gnss_power_off(", truncate)
        release_report = wrapper.index(
            "acquisition_outcome == EGOLINK_MODEM_CALLBACK_REPORT_AVAILABLE",
            stop,
        )
        self.assertLess(admission, reserve)
        self.assertLess(reserve, acquire)
        self.assertLess(acquire, remaining)
        self.assertLess(remaining, truncate)
        self.assertLess(acquire, stop)
        self.assertLess(stop, release_report)
        self.assertIn("sim7670_gnss_report_init(report)", wrapper)
        self.assertIn("within_original_bound", wrapper)
        self.assertIn("require_cleanup_recovery(internal)", wrapper)

        remaining_helper = _function(
            self.source,
            "static bool remaining_before_deadline_ms(",
            "static void require_cleanup_recovery(",
        )
        self.assertIn(
            "request->begin_time_ms + request->timeout_ms", remaining_helper
        )
        self.assertIn("now_ms >= deadline_ms", remaining_helper)
        self.assertIn("deadline_ms - now_ms", remaining_helper)

        cleanup = _function(
            self.source,
            "static bool run_gnss_power_off(",
            "/*\n * O calls this only after releasing",
        )
        self.assertIn("sim7670_gnss_power_off_bounded", cleanup)
        self.assertIn(".timeout_ms = timeout_ms", cleanup)
        self.assertIn(".cancel_requested = never_cancel", cleanup)
        self.assertIn("cleanup_recovery_required, !confirmed", cleanup)
        self.assertIn("GNSS_POWER_OFF_UNCONFIRMED", cleanup)
        self.assertNotIn("request->cancel", cleanup)

    def test_unconfirmed_cleanup_blocks_ordinary_work_and_retries_with_backoff(self) -> None:
        task = _function(
            self.source,
            "static void owner_task_main(void *context)",
            "static bool valid_publish_intent(",
        )
        cleanup_gate = task.index("cleanup_recovery_required")
        retry_wait = task.index("recovery_retry_backoff_ms", cleanup_gate)
        retry = task.index("run_gnss_power_off(", retry_wait)
        drive = task.index("drive_one_command(internal)", retry)
        self.assertLess(cleanup_gate, retry_wait)
        self.assertLess(retry_wait, retry)
        self.assertLess(retry, drive)
        self.assertIn("fatal_recovery_required", task)
        self.assertNotIn("vTaskDelay", task)

    def test_capture_identity_is_boot_monotonic_and_mapped_input_is_never_queued(self) -> None:
        identity = _function(
            self.source,
            "static bool build_capture_identity(",
            "static void update_sequence_after_external_input(",
        )
        self.assertIn("EGOLINK_LOCATION_TIME_TIMESTAMP_MONOTONIC_NS", identity)
        self.assertIn("completion_time_ms * UINT64_C(1000000)", identity)
        self.assertIn("locq-%", identity)
        self.assertIn("sequence_exhausted", identity)
        process = _function(
            self.source,
            "egolink_sim7670_location_modem_owner_process_mapped_input(",
            "egolink_sim7670_modem_owner_status_t\n"
            "egolink_sim7670_location_modem_owner_signal_durable_sos(",
        )
        self.assertIn(
            "egolink_location_modem_executor_process_mapped_input", process
        )
        self.assertNotIn("memcpy", process)
        self.assertNotIn("xQueue", self.source)
        self.assertIn("mapped is never\n * copied", self.header)

    def test_snapshot_and_source_retain_no_sensitive_modem_or_location_data(self) -> None:
        marker = "/* No coordinate, cell identity, payload"
        start = self.header.index("typedef struct {", self.header.index(marker))
        snapshot = self.header[
            start : self.header.index(
                "} egolink_sim7670_location_modem_owner_snapshot_t;", start
            )
        ]
        for forbidden in (
            "latitude",
            "longitude",
            "cell_id",
            "raw_response",
            "payload[",
            "credential",
            "device_id",
            "session_id",
            "observation_id",
        ):
            self.assertNotIn(forbidden, snapshot.casefold())
        for forbidden in (
            "ESP_LOG",
            "printf(\"",
            "uart_driver_install",
            "uart_write_bytes",
            "uart_read_bytes",
            "socket(",
        ):
            self.assertNotIn(forbidden.casefold(), self.source.casefold())

    def test_packet_records_q_static_boundary_and_live_profile_blocker(self) -> None:
        packet = PACKET.read_text(encoding="utf-8")
        self.assertIn("LOC-021Q", packet)
        self.assertIn("sim7670_location_modem_owner", packet)
        self.assertIn("exclusive", packet.casefold())
        self.assertIn("legacy direct", packet.casefold())
        self.assertIn("app_main", packet)
        self.assertIn("P0-LOC", packet)
        self.assertIn("NOT_RUN", packet)

    def test_actual_owner_and_api_harness_strictly_cross_compile_and_link(self) -> None:
        found = _sim_compile_entry()
        if found is None:
            self.skipTest("generated ESP32-S3 SIM7670 compile entry unavailable")
        entry, directory = found
        idf = Path(os.environ.get("IDF_PATH", "C:/Espressif/v5.4.2/esp-idf"))
        self.assertTrue(idf.is_dir())
        harness_text = textwrap.dedent(
            """
            #include "sim7670_location_modem_owner.h"

            static egolink_sim7670_location_modem_owner_t owner;
            static egolink_outbox_t outbox;
            static egolink_location_outbox_adapter_t location_adapter;
            static egolink_p0_delivery_runtime_t delivery_runtime;
            static volatile unsigned int sink;

            void sim7670_location_modem_owner_link_probe(void)
            {
                egolink_sim7670_location_modem_owner_config_t config;
                egolink_sim7670_location_modem_owner_snapshot_t snapshot;
                egolink_location_modem_process_result_t process;
                egolink_location_modem_durable_sos_result_t durable_sos;
                egolink_location_modem_enqueue_result_t sos;
                egolink_location_modem_enqueue_result_t urgent;
                egolink_location_hardware_mapped_input_t mapped = {0};
                egolink_location_runtime_identity_t identity = {0};

                egolink_sim7670_location_modem_owner_default_config(&config);
                sink = (unsigned int)egolink_sim7670_location_modem_owner_init(
                    &owner, &config, &outbox, &location_adapter,
                    &delivery_runtime);
                sink = (unsigned int)egolink_sim7670_location_modem_owner_start(
                    &owner);
                sink = (unsigned int)
                    egolink_sim7670_location_modem_owner_process_mapped_input(
                        &owner, &mapped, UINT64_C(1), &process);
                sink = (unsigned int)
                    egolink_sim7670_location_modem_owner_process_durable_sos(
                        &owner, &identity,
                        EGOLINK_MODEM_DURABLE_SOS_COMMITTED_OR_DUPLICATE,
                        UINT64_C(30000), UINT64_C(2), &durable_sos);
                sink = (unsigned int)
                    egolink_sim7670_location_modem_owner_signal_durable_sos(
                        &owner,
                        EGOLINK_MODEM_DURABLE_SOS_COMMITTED_OR_DUPLICATE,
                        UINT64_C(30000), &sos, &urgent);
                sink = (unsigned int)
                    egolink_sim7670_location_modem_owner_request_gnss_status(
                        &owner, UINT64_C(10000), &urgent);
                sink = (unsigned int)
                    egolink_sim7670_location_modem_owner_current_status(
                        &owner, &snapshot);
                sink += (unsigned int)egolink_sim7670_modem_owner_status_name(
                    snapshot.last_status)[0];
            }
            """
        )
        with tempfile.TemporaryDirectory(prefix="egolink-loc021q-") as temporary:
            temp = Path(temporary)
            harness = temp / "owner_harness.c"
            owner_object = temp / "owner.o"
            harness_object = temp / "harness.o"
            linked = temp / "owner_linked.o"
            harness.write_text(harness_text, encoding="utf-8")
            for source, output in ((SOURCE, owner_object), (harness, harness_object)):
                command = _compile_command(entry["command"], source, output, idf)
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
                    str(owner_object),
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

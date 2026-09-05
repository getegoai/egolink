"""Focused LOC-021R checks for the durable SOS Location ingress.

The suite protects the no-I/O composition contract and strictly cross-compiles
the production source plus an API harness for ESP32-S3. It does not execute
target code or touch GPIO, flash, a modem, a device, a network, or a journal.
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


def _function(source: str, start: str, end: str) -> str:
    begin = source.index(start)
    return source[begin : source.index(end, begin)]


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


def _api_harness() -> str:
    return textwrap.dedent(
        r"""
        #include <stdint.h>
        #include "location_modem_executor.h"

        #define TEXT(value) \
            (egolink_location_runtime_text_t){(value), sizeof(value) - 1U}

        static egolink_location_modem_executor_t executor;
        static egolink_location_runtime_scratch_t scratch;
        static volatile unsigned int sink;

        void location_modem_executor_durable_sos_link_probe(void)
        {
            const egolink_location_runtime_identity_t identity = {
                .device_id = TEXT("device-r"),
                .boot_count = UINT64_C(7),
                .session_id = TEXT("session-r"),
                .stream_id = TEXT("location-stream-r"),
                .sequence_id = UINT64_C(19),
                .observation_id = TEXT("physical-sos-r"),
                .event_time_ms = UINT64_C(1234),
                .event_time_source =
                    EGOLINK_LOCATION_TIME_TIMESTAMP_MONOTONIC_NS,
                .event_time_ns = UINT64_C(1234000000),
                .monotonic_clock_domain_id = TEXT("boot-clock-r"),
            };
            egolink_location_modem_durable_sos_result_t result;
            sink = (unsigned int)
                egolink_location_modem_executor_process_durable_sos(
                    &executor, &identity,
                    EGOLINK_MODEM_DURABLE_SOS_COMMITTED_OR_DUPLICATE,
                    UINT64_C(30000), UINT64_C(1234), &scratch, &result);
            sink += (unsigned int)result.location_input_duplicate;
            sink += (unsigned int)result.partial_failure;
        }
        """
    )


class LocationModemExecutorDurableSosTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.header = HEADER.read_text(encoding="utf-8")
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.cmake = CMAKE.read_text(encoding="utf-8")
        cls.api = _function(
            cls.source,
            "egolink_location_modem_executor_process_durable_sos(",
            "static egolink_modem_executor_status_t requeue_one_deferred(",
        )

    def test_api_requires_caller_owned_location_stream_identity(self) -> None:
        normalized = " ".join(self.header.split())
        self.assertIn(
            "const egolink_location_runtime_identity_t *location_identity",
            self.header,
        )
        self.assertIn("next identity from that same Location stream", normalized)
        self.assertIn("SOS journal sequence is not a substitute", normalized)
        self.assertIn("Text views are borrowed only", normalized)
        self.assertNotIn("sequence_id++", self.api)
        self.assertNotIn("event_time_ms++", self.api)

    def test_only_committed_or_duplicate_durable_evidence_is_accepted(self) -> None:
        validation = self.api[: self.api.index("modem_executor_internal_t *internal")]
        self.assertIn(
            "evidence != EGOLINK_MODEM_DURABLE_SOS_COMMITTED_OR_DUPLICATE",
            validation,
        )
        self.assertIn("EGOLINK_MODEM_EXECUTOR_INVALID_ARGUMENT", validation)
        self.assertIn("result->durable_evidence_accepted = true", self.api)

    def test_private_k_receives_one_pure_coordinate_free_sos_observation(self) -> None:
        builder = _function(
            self.source,
            "static void build_durable_sos_input(",
            "static bool usable_sos_preemption_signal(",
        )
        self.assertIn("input->identity = *identity", builder)
        self.assertIn("EGOLINK_LOCATION_RUNTIME_PUBLISH_NONE", builder)
        self.assertIn("EGOLINK_LOCATION_ENGINE_EVENT_SOS", builder)
        self.assertIn("sos_active_present = true", builder)
        self.assertIn("sos_active = true", builder)
        self.assertIn("EGOLINK_LOCATION_ENGINE_SOURCE_STATUS_OBSERVED", builder)
        for field in (
            "observation_id",
            "stream_id",
            "sequence_id",
            "device_run_id",
            "boot_count",
            "gnss_source_utc_ns",
            "timestamp_utc_ns",
            "timestamp_monotonic_ns",
            "monotonic_clock_domain_id",
        ):
            self.assertIn(field, builder)
        for forbidden in (
            "latitude_deg",
            "longitude_deg",
            "accuracy_m",
            "uncertainty_m",
            "reference_id",
        ):
            self.assertNotIn(forbidden, builder)
        self.assertIn("egolink_device_location_runtime_process", self.api)
        self.assertNotIn("egolink_location_hardware_map_", self.api)

    def test_safety_signals_precede_k_and_k_failure_cannot_skip_them(self) -> None:
        signal_call = self.api.index(
            "egolink_location_modem_executor_signal_durable_sos"
        )
        location_call = self.api.index(
            "egolink_device_location_runtime_process", signal_call
        )
        location_kick = self.api.index(
            "EGOLINK_MODEM_COMMAND_LOCATION_TRANSPORT", location_call
        )
        self.assertLess(signal_call, location_call)
        self.assertLess(location_call, location_kick)
        self.assertNotIn("return ", self.api[signal_call:location_call])
        self.assertIn("!result->location_branch_satisfied", self.api)
        self.assertIn("!result->manual_sos_transport_signal_satisfied", self.api)
        self.assertIn("!result->urgent_gnss_signal_satisfied", self.api)
        self.assertIn("EGOLINK_MODEM_EXECUTOR_DURABLE_SOS_PARTIAL", self.api)

    def test_full_ingress_rejects_execution_phase_and_documents_two_step_path(self) -> None:
        lifecycle_end = self.api.index("result->durable_evidence_accepted = true")
        guard = self.api[:lifecycle_end]
        self.assertIn(
            "internal->phase != EGOLINK_MODEM_EXECUTOR_PHASE_IDLE", guard
        )
        self.assertIn("EGOLINK_MODEM_EXECUTOR_IN_FLIGHT", guard)
        normalized = " ".join(self.header.split())
        self.assertIn("process_durable_sos is a full K/outbox composition", normalized)
        self.assertIn("call only", normalized)
        self.assertIn("signal_durable_sos under the owner", normalized)
        self.assertIn("finish execute/settle", normalized)

    def test_exact_replay_uses_k_duplicate_and_bounded_existing_signal(self) -> None:
        self.assertIn("EGOLINK_DEVICE_LOCATION_RUNTIME_DUPLICATE_INPUT", self.api)
        self.assertIn("result->location_input_duplicate ||", self.api)
        envelope_assignment = self.api[
            self.api.index("result->location_envelope_enqueued_now =") :
            self.api.index("result->location_action_partial_failure_preserved")
        ]
        self.assertNotIn("location_input_duplicate", envelope_assignment)
        self.assertIn("result->location_input_committed &&", self.api)
        signal = _function(
            self.source,
            "egolink_location_modem_executor_signal_durable_sos(",
            "egolink_location_modem_executor_request_gnss_status(",
        )
        self.assertIn("internal->sos_transport_outstanding", signal)
        self.assertIn("internal->deferred_sos_transport = true", signal)
        self.assertIn("internal->urgent_gnss_outstanding", signal)
        self.assertIn("already_outstanding = true", signal)
        self.assertIn("internal->deferred_location_transport = true", self.api)

    def test_exact_replay_cannot_hide_a_deferred_cell_observation(self) -> None:
        self.assertIn("bool deferred_cell_observe", self.header)
        self.assertIn("uint64_t deferred_cell_timeout_ms", self.header)
        self.assertIn(
            "result->location_input_duplicate &&\n"
            "               internal->deferred_cell_observe",
            self.api,
        )
        self.assertIn("result->policy_cell_observe_requested = true", self.api)
        self.assertIn("internal->deferred_cell_timeout_ms, &result->cell", self.api)
        self.assertIn("result->policy_cell_attempt_satisfied = result->cell.admitted", self.api)
        self.assertIn("result->cell.followup_scan_deferred = true", self.api)
        normalized = " ".join(self.header.split()).casefold()
        self.assertIn(
            "cannot silently upgrade that partial result to accepted",
            normalized,
        )

    def test_rejected_or_urgent_coalesced_cell_keeps_bounded_retry(self) -> None:
        reconcile = _function(
            self.source,
            "static void reconcile_enqueue_removals(",
            "static egolink_modem_executor_status_t enqueue_command(",
        )
        deferred = _function(
            self.source,
            "static egolink_modem_executor_status_t requeue_one_deferred(",
            "egolink_location_modem_executor_prepare_next(",
        )
        self.assertIn("coalesced->kind == EGOLINK_MODEM_COMMAND_CELL_OBSERVE", reconcile)
        self.assertIn("defer_cell_observe(internal, coalesced->timeout_ms)", reconcile)
        self.assertIn("internal->deferred_cell_observe", deferred)
        self.assertIn("internal->deferred_cell_timeout_ms", deferred)
        self.assertIn("EGOLINK_MODEM_COMMAND_CELL_OBSERVE", deferred)
        self.assertIn("internal->deferred_cell_observe = false", deferred)

    def test_sos_policy_cell_is_scheduled_without_a_second_gnss_attempt(self) -> None:
        policy_start = self.api.index("result->policy_decision_available")
        policy = self.api[
            policy_start :
            self.api.index("if (result->location_input_committed &&", policy_start)
        ]
        self.assertIn("decision->cell_observe_now", policy)
        self.assertIn("EGOLINK_MODEM_COMMAND_CELL_OBSERVE", policy)
        self.assertIn("decision->cell_request_timeout_ms", policy)
        self.assertIn("result->policy_cell_attempt_satisfied", policy)
        self.assertIn("result->policy_gnss_start_covered_by_urgent", policy)
        self.assertNotIn("EGOLINK_MODEM_COMMAND_GNSS_ACQUIRE", self.api)
        self.assertIn("cell_partial", self.api)

    def test_remaining_policy_intents_are_explicit_product_owner_work(self) -> None:
        for field in (
            "policy_gnss_stop_requires_product_owner",
            "policy_imu_rate_requires_product_owner",
            "policy_lte_keep_connected_requires_product_owner",
            "policy_ego_call_requires_product_owner",
            "policy_upload_transport_owned_by_executor",
        ):
            self.assertIn(field, self.header)
            self.assertIn(f"result->{field}", self.api)
        self.assertNotIn("EGOLINK_DEVICE_LOCATION_ACTION_SUCCEEDED", self.source)
        normalized = " ".join(self.header.split())
        self.assertIn("preserve IMU/LTE/Call responsibility", normalized)
        self.assertIn("instead of treating ACTION_PARTIAL_FAILURE as success", normalized)

    def test_result_does_not_claim_delivery_fix_or_guardian_success(self) -> None:
        result_decl = self.header[
            self.header.index("typedef struct {", self.header.index("This result reports")) :
            self.header.index("} egolink_location_modem_durable_sos_result_t;")
        ]
        for field in (
            "location_input_committed",
            "location_input_duplicate",
            "location_envelope_enqueued_now",
            "location_branch_satisfied",
            "manual_sos_transport_signal_satisfied",
            "urgent_gnss_signal_satisfied",
            "policy_cell_observe_requested",
            "policy_cell_attempt_satisfied",
            "partial_failure",
        ):
            self.assertIn(field, result_decl)
        for forbidden in (
            "delivered",
            "gnss_fix",
            "guardian_notified",
            "latitude",
            "longitude",
            "payload[",
            "credential",
        ):
            self.assertNotIn(forbidden, result_decl.casefold())
        normalized = " ".join(self.header.split()).casefold()
        self.assertIn("it is never a", normalized)
        self.assertIn("delivery, gnss-fix or", normalized)
        self.assertIn("guardian-notification claim", normalized)
        self.assertIn("does not prove that its earlier location outbox", normalized)
        self.assertIn("record remains present after ack/deletion", normalized)

    def test_slice_is_default_off_unwired_and_adds_no_io_dependency(self) -> None:
        self.assertIn("config->enabled = false", self.source)
        self.assertNotIn("process_durable_sos", APP_MAIN.read_text(encoding="utf-8"))
        for forbidden_dependency in (
            "sos_input",
            "sos_pending_edge_journal",
            "sos_delivery_composition",
        ):
            self.assertNotIn(forbidden_dependency, self.cmake)
        for forbidden in (
            "xTaskCreate",
            "gpio_",
            "nvs_",
            "uart_",
            "esp_http_client",
            "socket(",
        ):
            self.assertNotIn(forbidden.casefold(), self.source.casefold())

    def test_new_api_and_actual_source_strictly_cross_compile_and_link(self) -> None:
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
        with tempfile.TemporaryDirectory(prefix="egolink-loc021r-") as temporary:
            temp = Path(temporary)
            harness_source = temp / "location_modem_executor_durable_sos_harness.c"
            harness_source.write_text(_api_harness(), encoding="utf-8")
            objects = []
            for source in (SOURCE, ARBITER / "location_modem_arbiter.c", harness_source):
                output = temp / f"{source.stem}.o"
                completed = subprocess.run(
                    [*common, "-c", str(source), "-o", str(output)],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
                self.assertEqual(
                    0, completed.returncode, completed.stdout + completed.stderr
                )
                objects.append(output)
            linked = temp / "location_modem_executor_durable_sos_linked.o"
            completed = subprocess.run(
                [
                    str(compiler),
                    "-nostdlib",
                    "-Wl,-r",
                    *map(str, objects),
                    "-o",
                    str(linked),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            self.assertEqual(
                0, completed.returncode, completed.stdout + completed.stderr
            )
            self.assertGreater(linked.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()

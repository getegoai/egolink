"""Focused SOS-010F/G checks for the dormant device SOS runtime owner.

The actual C runtime is always cross-compiled for ESP32-S3. A native harness
runs the runtime, input and orchestrator C together only when a real host
GCC/Clang exists. No test touches GPIO, flash, network, audio or a device.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ROOT / "firmware" / "mqtt_heartbeat" / "components"
COMPONENT = COMPONENTS / "sos_device_runtime"
SOURCE = COMPONENT / "sos_device_runtime.c"
HEADER = COMPONENT / "include" / "sos_device_runtime.h"
CMAKE = COMPONENT / "CMakeLists.txt"
APP_MAIN = ROOT / "firmware" / "mqtt_heartbeat" / "main" / "app_main.c"
PACKET = ROOT / "docs" / "tasks" / "active" / "SOS-010_SOS_WALKING_SKELETON.md"


def _esp_toolchain() -> tuple[Path, Path] | None:
    compiler_candidates = (
        shutil.which("xtensa-esp32s3-elf-gcc"),
        Path(
            "C:/Espressif/tools/xtensa-esp-elf/esp-14.2.0_20241119/"
            "xtensa-esp-elf/bin/xtensa-esp32s3-elf-gcc.exe"
        ),
    )
    compiler = next(
        (
            Path(candidate)
            for candidate in compiler_candidates
            if candidate and Path(candidate).is_file()
        ),
        None,
    )
    idf_candidates = (
        Path(os.environ["IDF_PATH"]) if os.environ.get("IDF_PATH") else None,
        Path("C:/Espressif/v5.4.2/esp-idf"),
    )
    idf = next(
        (candidate for candidate in idf_candidates if candidate and candidate.is_dir()),
        None,
    )
    return None if compiler is None or idf is None else (compiler, idf)


def _native_compiler() -> Path | None:
    candidates = (
        os.environ.get("CC"),
        shutil.which("gcc"),
        shutil.which("clang"),
        "C:/Program Files/LLVM/bin/clang.exe",
    )
    for candidate in candidates:
        if not candidate:
            continue
        resolved = shutil.which(str(candidate)) or str(candidate)
        path = Path(resolved)
        lowered = path.name.casefold()
        if (
            not path.is_file()
            or not ("gcc" in lowered or "clang" in lowered)
            or "xtensa" in lowered
            or "riscv" in lowered
        ):
            continue
        probe = subprocess.run(
            [str(path), "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if probe.returncode == 0:
            return path
    return None


def _include_paths() -> tuple[Path, ...]:
    return (
        COMPONENT / "include",
        COMPONENTS / "sos_input" / "include",
        COMPONENTS / "sos_orchestrator" / "include",
        COMPONENTS / "sos_outbox_adapter" / "include",
        COMPONENTS / "sos_pending_edge_journal" / "include",
        COMPONENTS / "persistent_priority_outbox" / "include",
        COMPONENTS / "location_policy_core" / "include",
    )


def _behavioral_harness_source() -> str:
    return textwrap.dedent(
        r"""
        #include "sos_device_runtime.h"

        #include <stdint.h>
        #include <string.h>

        #define REQUIRE(condition) do { if (!(condition)) { return __LINE__; } } while (0)

        static egolink_outbox_status_t enqueue_status;
        static bool feedback_ok;
        static bool location_ok;
        static bool call_ok;
        static bool wake_ok;
        static unsigned int enqueue_count;
        static unsigned int callback_count;
        static char callback_order[32];
        static uint8_t pending_wire[EGOLINK_SOS_PENDING_EDGE_RECORD_BYTES];
        static bool pending_present;
        static bool pending_failure;
        static unsigned recognized_count;

        static void reset_scenario(void)
        {
            enqueue_status = EGOLINK_OUTBOX_OK;
            feedback_ok = true;
            location_ok = true;
            call_ok = true;
            wake_ok = true;
            enqueue_count = 0U;
            callback_count = 0U;
            pending_present = false;
            (void)memset(pending_wire, 0, sizeof(pending_wire));
            (void)memset(callback_order, 0, sizeof(callback_order));
        }

        static egolink_sos_pending_edge_storage_result_t pending_load(
            void *context,
            void *destination,
            size_t capacity,
            size_t *actual_length)
        {
            (void)context;
            REQUIRE(destination != NULL && actual_length != NULL);
            if (!pending_present) {
                *actual_length = 0U;
                return EGOLINK_SOS_PENDING_EDGE_STORAGE_NOT_FOUND;
            }
            REQUIRE(capacity >= sizeof(pending_wire));
            (void)memcpy(destination, pending_wire, sizeof(pending_wire));
            *actual_length = sizeof(pending_wire);
            return EGOLINK_SOS_PENDING_EDGE_STORAGE_OK;
        }

        static egolink_sos_pending_edge_storage_result_t pending_store(
            void *context,
            const void *source,
            size_t source_length)
        {
            (void)context;
            REQUIRE(source != NULL && source_length == sizeof(pending_wire));
            REQUIRE(recognized_count > 0U);
            if (pending_failure) return EGOLINK_SOS_PENDING_EDGE_STORAGE_IO_ERROR;
            (void)memcpy(pending_wire, source, sizeof(pending_wire));
            pending_present = true;
            return EGOLINK_SOS_PENDING_EDGE_STORAGE_OK;
        }

        static egolink_sos_pending_edge_storage_result_t pending_clear(
            void *context)
        {
            (void)context;
            pending_present = false;
            (void)memset(pending_wire, 0, sizeof(pending_wire));
            return EGOLINK_SOS_PENDING_EDGE_STORAGE_OK;
        }

        egolink_outbox_status_t egolink_outbox_enqueue(
            egolink_outbox_t *outbox,
            const egolink_outbox_enqueue_request_t *request,
            uint64_t now_ms,
            egolink_outbox_record_view_t *record_view)
        {
            static const char digest[] =
                "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
            (void)outbox;
            (void)now_ms;
            REQUIRE(request != NULL);
            REQUIRE(request->priority == EGOLINK_OUTBOX_PRIORITY_CRITICAL);
            REQUIRE(strcmp(request->event_type, "manual_sos") == 0);
            callback_order[callback_count++] = 'd';
            ++enqueue_count;
            if (enqueue_status == EGOLINK_OUTBOX_OK ||
                enqueue_status == EGOLINK_OUTBOX_DUPLICATE) {
                (void)memset(record_view, 0, sizeof(*record_view));
                (void)memcpy(record_view->payload_sha256, digest, sizeof(digest));
            }
            return enqueue_status;
        }

        egolink_location_policy_result_t egolink_location_policy_evaluate(
            egolink_location_policy_core_t *core,
            const egolink_location_policy_snapshot_t *snapshot,
            const egolink_location_policy_event_t *event,
            egolink_location_policy_decision_t *decision)
        {
            REQUIRE(core != NULL && core->initialized);
            REQUIRE(snapshot != NULL && snapshot->sos_active);
            REQUIRE(event != NULL && event->type == EGOLINK_LOCATION_POLICY_EVENT_SOS);
            callback_order[callback_count++] = 'p';
            (void)memset(decision, 0, sizeof(*decision));
            decision->policy_mode = EGOLINK_LOCATION_POLICY_SOS;
            decision->conditions.sos_active = true;
            return EGOLINK_LOCATION_POLICY_OK;
        }

        static bool recognized(void *context, const egolink_sos_input_output_t *edge)
        {
            (void)context;
            REQUIRE(edge && edge->sos_edge);
            ++recognized_count;
            callback_order[callback_count++] = 'r';
            return true;
        }

        static bool feedback(
            void *context,
            const egolink_sos_branch_identity_t *identity)
        {
            (void)context;
            REQUIRE(identity != NULL && identity->event_id != NULL);
            callback_order[callback_count++] = 'f';
            return feedback_ok;
        }

        static bool location(
            void *context,
            const egolink_sos_location_enqueue_request_t *request)
        {
            (void)context;
            REQUIRE(request != NULL && request->urgent);
            REQUIRE(request->request_last_trusted && request->request_current);
            callback_order[callback_count++] = 'l';
            return location_ok;
        }

        static bool call(
            void *context,
            const egolink_sos_call_request_t *request)
        {
            (void)context;
            REQUIRE(request != NULL && request->manual_sos);
            callback_order[callback_count++] = 'c';
            return call_ok;
        }

        static bool wake(
            void *context,
            const egolink_sos_sender_wake_request_t *request)
        {
            (void)context;
            REQUIRE(request != NULL && request->identity != NULL);
            callback_order[callback_count++] = 'w';
            return wake_ok;
        }

        static egolink_sos_device_runtime_status_t initialize(
            egolink_sos_device_runtime_t *runtime,
            egolink_outbox_t *outbox,
            egolink_sos_outbox_adapter_t *adapter,
            egolink_sos_pending_edge_journal_t *journal,
            egolink_location_policy_core_t *policy,
            bool held)
        {
            egolink_sos_device_runtime_config_t config;
            egolink_sos_device_runtime_default_config(&config);
            config.enabled = true;
            config.input.debounce_ms = 50U;
            config.input.long_press_ms = 500U;
            config.device_id = "wearable-1";
            config.boot_count = 7U;
            config.session_id = "boot-session-7";
            config.first_source_sequence = 1U;
            config.callbacks.input_recognized = recognized;
            config.callbacks.local_feedback = feedback;
            config.callbacks.request_urgent_location = location;
            config.callbacks.request_call = call;
            config.callbacks.wake_sender = wake;
            policy->initialized = true;
            (void)memset(adapter, 0, sizeof(*adapter));
            adapter->outbox = outbox;
            adapter->initialized = true;
            (void)memcpy(adapter->device_id, "wearable-1", sizeof("wearable-1"));
            const egolink_sos_pending_edge_storage_t storage = {
                .load_record = pending_load,
                .store_record = pending_store,
                .clear_record = pending_clear,
            };
            REQUIRE(egolink_sos_pending_edge_journal_init(
                journal, &storage, "wearable-1") ==
                EGOLINK_SOS_PENDING_EDGE_OK);
            return egolink_sos_device_runtime_init(
                runtime, &config, outbox, adapter, journal, policy, held, 0U);
        }

        static int trigger(
            egolink_sos_device_runtime_t *runtime,
            uint64_t press_ms,
            uint64_t trigger_ms,
            egolink_sos_device_runtime_result_t *result)
        {
            REQUIRE(egolink_sos_device_runtime_process_sample(
                runtime, true, press_ms, result) ==
                EGOLINK_SOS_DEVICE_RUNTIME_NO_EDGE);
            REQUIRE(egolink_sos_device_runtime_process_sample(
                runtime, true, press_ms + 50U, result) ==
                EGOLINK_SOS_DEVICE_RUNTIME_NO_EDGE);
            (void)egolink_sos_device_runtime_process_sample(
                runtime, true, trigger_ms, result);
            return 0;
        }

        int main(void)
        {
            egolink_outbox_t outbox;
            egolink_location_policy_core_t policy;
            egolink_sos_outbox_adapter_t adapter;
            egolink_sos_pending_edge_journal_t journal;
            egolink_sos_device_runtime_t runtime;
            egolink_sos_device_runtime_result_t result;
            egolink_sos_device_runtime_snapshot_t snapshot;
            egolink_sos_device_runtime_shutdown_result_t shutdown;
            (void)memset(&outbox, 0, sizeof(outbox));
            (void)memset(&policy, 0, sizeof(policy));
            (void)memset(&runtime, 0, sizeof(runtime));

            reset_scenario();
            REQUIRE(initialize(
                &runtime, &outbox, &adapter, &journal, &policy, true) ==
                    EGOLINK_SOS_DEVICE_RUNTIME_OK);
            REQUIRE(egolink_sos_device_runtime_process_sample(
                &runtime, true, 1000U, &result) ==
                EGOLINK_SOS_DEVICE_RUNTIME_NO_EDGE);
            REQUIRE(enqueue_count == 0U);
            REQUIRE(egolink_sos_device_runtime_process_sample(
                &runtime, false, 1000U, &result) ==
                EGOLINK_SOS_DEVICE_RUNTIME_NO_EDGE);
            REQUIRE(egolink_sos_device_runtime_process_sample(
                &runtime, false, 1050U, &result) ==
                EGOLINK_SOS_DEVICE_RUNTIME_NO_EDGE);
            REQUIRE(trigger(&runtime, 1100U, 1650U, &result) == 0);
            REQUIRE(result.status == EGOLINK_SOS_DEVICE_RUNTIME_OK);
            REQUIRE(result.qualified_edge && result.source_sequence == 1U);
            REQUIRE(result.durable_manual_sos_available);
            REQUIRE(strcmp(callback_order, "rdwfplc") == 0);
            REQUIRE(egolink_sos_device_runtime_process_sample(
                &runtime, true, 1700U, &result) ==
                EGOLINK_SOS_DEVICE_RUNTIME_NO_EDGE);
            REQUIRE(enqueue_count == 1U);

            REQUIRE(egolink_sos_device_runtime_process_sample(
                &runtime, false, 1800U, &result) ==
                EGOLINK_SOS_DEVICE_RUNTIME_NO_EDGE);
            REQUIRE(egolink_sos_device_runtime_process_sample(
                &runtime, false, 1850U, &result) ==
                EGOLINK_SOS_DEVICE_RUNTIME_NO_EDGE);
            callback_count = 0U;
            (void)memset(callback_order, 0, sizeof(callback_order));
            location_ok = false;
            REQUIRE(trigger(&runtime, 1900U, 2450U, &result) == 0);
            REQUIRE(result.status ==
                    EGOLINK_SOS_DEVICE_RUNTIME_PARTIAL_FAILURE);
            REQUIRE(result.source_sequence == 2U);
            REQUIRE(result.orchestration.location_enqueue ==
                    EGOLINK_SOS_BRANCH_FAILED);
            REQUIRE(result.orchestration.call_request ==
                    EGOLINK_SOS_BRANCH_SUCCEEDED);
            REQUIRE(strcmp(callback_order, "rdwfplc") == 0);
            REQUIRE(enqueue_count == 2U);

            REQUIRE(egolink_sos_device_runtime_process_sample(
                &runtime, false, 2500U, &result) ==
                EGOLINK_SOS_DEVICE_RUNTIME_NO_EDGE);
            REQUIRE(egolink_sos_device_runtime_process_sample(
                &runtime, false, 2550U, &result) ==
                EGOLINK_SOS_DEVICE_RUNTIME_NO_EDGE);
            callback_count = 0U;
            (void)memset(callback_order, 0, sizeof(callback_order));
            location_ok = true;
            call_ok = false;
            enqueue_status = EGOLINK_OUTBOX_STORAGE_ERROR;
            REQUIRE(trigger(&runtime, 2600U, 3150U, &result) == 0);
            REQUIRE(result.status ==
                    EGOLINK_SOS_DEVICE_RUNTIME_PARTIAL_FAILURE);
            REQUIRE(!result.durable_manual_sos_available);
            REQUIRE(result.orchestration.local_feedback ==
                    EGOLINK_SOS_BRANCH_SUCCEEDED);
            REQUIRE(result.orchestration.location_enqueue ==
                    EGOLINK_SOS_BRANCH_SUCCEEDED);
            REQUIRE(result.orchestration.call_request ==
                    EGOLINK_SOS_BRANCH_FAILED);
            REQUIRE(strcmp(callback_order, "rdfplc") == 0);

            /* Lost ACK/recovered input cannot reopen a call which ended. */
            call_ok = true;
            enqueue_status = EGOLINK_OUTBOX_DUPLICATE;
            callback_count = 0U;
            memset(callback_order, 0, sizeof(callback_order));
            unsigned recognized_before = recognized_count;
            (void)egolink_sos_device_runtime_replay_pending(&runtime, 3200U, &result);
            REQUIRE(result.replayed_pending_edge);
            REQUIRE(result.orchestration.call_request == EGOLINK_SOS_BRANCH_RECOVERY_SUPPRESSED);
            REQUIRE(strchr(callback_order, 'c') == NULL);
            REQUIRE(recognized_count == recognized_before);

            adapter.attempt_active = true;
            REQUIRE(egolink_sos_device_runtime_cancel(
                &runtime, &shutdown) ==
                EGOLINK_SOS_DEVICE_RUNTIME_CANCELLED_STATUS);
            REQUIRE(shutdown.durable_records_retained);
            REQUIRE(shutdown.dispatcher_attempt_untouched);
            REQUIRE(shutdown.pending_edge_journal_untouched);
            REQUIRE(adapter.initialized && adapter.outbox == &outbox);
            REQUIRE(adapter.attempt_active);
            REQUIRE(egolink_sos_device_runtime_current_status(
                &runtime, &snapshot) ==
                EGOLINK_SOS_DEVICE_RUNTIME_CANCELLED_STATUS);
            REQUIRE(snapshot.lifecycle == EGOLINK_SOS_DEVICE_RUNTIME_CANCELLED);
            REQUIRE(!snapshot.dependencies_bound);
            REQUIRE(egolink_sos_device_runtime_close(
                &runtime, &shutdown) ==
                EGOLINK_SOS_DEVICE_RUNTIME_CLOSED_STATUS);
            REQUIRE(shutdown.durable_records_retained);
            REQUIRE(shutdown.pending_edge_journal_untouched);
            memset(&runtime,0,sizeof(runtime)); reset_scenario();
            REQUIRE(initialize(&runtime,&outbox,&adapter,&journal,&policy,false)==EGOLINK_SOS_DEVICE_RUNTIME_OK);
            pending_failure=true;enqueue_status=EGOLINK_OUTBOX_STORAGE_ERROR;call_ok=true;
            REQUIRE(trigger(&runtime,100U,650U,&result)==0);
            REQUIRE(result.status==EGOLINK_SOS_DEVICE_RUNTIME_JOURNAL_FAILED);
            REQUIRE(result.input_recognition==EGOLINK_SOS_BRANCH_SUCCEEDED);
            REQUIRE(!result.pending_edge_durable && !result.durable_manual_sos_available);
            REQUIRE(result.orchestration.local_feedback==EGOLINK_SOS_BRANCH_SUCCEEDED);
            REQUIRE(result.orchestration.location_enqueue==EGOLINK_SOS_BRANCH_SUCCEEDED);
            REQUIRE(result.orchestration.call_request==EGOLINK_SOS_BRANCH_SUCCEEDED);
            REQUIRE(strcmp(callback_order,"rdfplc")==0);
            return 0;
        }
        """
    )


class SosDeviceRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.header = HEADER.read_text(encoding="utf-8")
        cls.cmake = CMAKE.read_text(encoding="utf-8")
        cls.packet = PACKET.read_text(encoding="utf-8")

    def test_component_is_default_disabled_and_dormant(self) -> None:
        self.assertIn('SRCS "sos_device_runtime.c"', self.cmake)
        for dependency in (
            "sos_input",
            "sos_orchestrator",
            "sos_outbox_adapter",
            "sos_pending_edge_journal",
            "persistent_priority_outbox",
            "location_policy_core",
        ):
            self.assertIn(dependency, self.cmake)
        self.assertIn("config->enabled = false", self.source)
        for forbidden in (
            "app_main",
            "gpio_",
            "esp_http_client",
            "mqtt_client",
            "esp_wifi",
            "freertos/",
            "esp_partition",
            "nvs_",
            "esp_log",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.source.casefold())
        self.assertNotIn("sos_device_runtime", APP_MAIN.read_text(encoding="utf-8"))

    def test_process_surface_only_accepts_pressed_time_and_result(self) -> None:
        declaration = re.search(
            r"egolink_sos_device_runtime_process_sample\(.*?\);",
            self.header,
            re.DOTALL,
        )
        self.assertIsNotNone(declaration)
        text = declaration.group(0)
        self.assertIn("bool raw_pressed", text)
        self.assertIn("uint64_t now_ms", text)
        for forbidden in ("battery", "camera", "ai_", "coordinate", "gpio"):
            self.assertNotIn(forbidden, text.casefold())

    def test_qualified_edge_delegates_to_orchestrator_and_maps_early_wake(self) -> None:
        process = self.source[
            self.source.index("static egolink_sos_device_runtime_status_t run_pending_edge(") :
            self.source.index("static egolink_sos_device_runtime_status_t runtime_ready(")
        ]
        store_at = process.index("egolink_sos_pending_edge_journal_store(")
        orchestrate_at = process.index("egolink_sos_orchestrate_edge(")
        wake_at = process.index("result->sender_wake = result->orchestration.durable_ready")
        self.assertLess(store_at, orchestrate_at)
        self.assertLess(orchestrate_at, wake_at)
        self.assertIn("battery_percent_available = false", process)
        self.assertIn("EGOLINK_LOCATION_POLICY_BATTERY_UNKNOWN", self.source)

    def test_journal_store_precedes_orchestration_and_sequence_consumption(self) -> None:
        process = self.source[
            self.source.index("egolink_sos_device_runtime_process_sample(") :
            self.source.index("static void clear_bound_state(")
        ]
        drive = self.source[
            self.source.index("static egolink_sos_device_runtime_status_t run_pending_edge(") :
            self.source.index("static egolink_sos_device_runtime_status_t runtime_ready(")
        ]
        store_at = drive.index("egolink_sos_pending_edge_journal_store(")
        sequence_at = drive.index("consume_pending_sequence(internal)")
        orchestration_at = drive.index("egolink_sos_orchestrate_edge(")
        clear_at = drive.index("egolink_sos_pending_edge_journal_clear(")
        wake_at = drive.index("result->sender_wake = result->orchestration.durable_ready")
        self.assertLess(store_at, sequence_at)
        self.assertLess(sequence_at, orchestration_at)
        self.assertLess(orchestration_at, clear_at)
        self.assertLess(orchestration_at, wake_at)
        self.assertNotIn("battery", self.header[
            self.header.index("typedef struct {\n    bool enabled;") :
            self.header.index("} egolink_sos_device_runtime_config_t;")
        ].casefold())

    def test_location_is_an_identified_intent_not_a_fabricated_observation(self) -> None:
        normalized = " ".join(
            (self.header + self.packet).replace("*", " ").split()
        ).casefold()
        for phrase in (
            "identified intent seam",
            "must resolve last-trusted/current state",
            "without retaining borrowed pointers",
            "no safe api here for constructing a unique durable sos observation",
        ):
            self.assertIn(phrase, normalized)
        self.assertNotIn("latitude", self.source.casefold())
        self.assertNotIn("longitude", self.source.casefold())

    def test_single_bound_adapter_is_borrowed_and_dispatcher_keeps_send_ownership(self) -> None:
        self.assertIn("egolink_sos_outbox_adapter_t *delivery_adapter", self.header)
        self.assertIn("delivery_adapter->outbox != shared_outbox", self.source)
        self.assertIn("strcmp(config->device_id, delivery_adapter->device_id)", self.source)
        for forbidden in (
            "egolink_sos_outbox_adapter_bind(",
            "egolink_sos_outbox_adapter_unbind(",
            "egolink_sos_outbox_begin_attempt(",
            "egolink_sos_outbox_finish_attempt(",
        ):
            self.assertNotIn(forbidden, self.source)
        normalized = " ".join(
            (self.header + self.packet).replace("*", " ").split()
        ).casefold()
        self.assertIn("dispatcher remains the only", normalized)
        self.assertIn("never creates, binds or drives a second adapter", normalized)

    def test_cancel_and_close_retain_queue_and_never_positive_ack_or_deinit(self) -> None:
        shutdown = self.source[
            self.source.index("static egolink_sos_device_runtime_status_t shutdown_runtime(") :
            self.source.index("egolink_sos_device_runtime_current_status(")
        ]
        self.assertIn("result->durable_records_retained = true", shutdown)
        self.assertIn("result->dispatcher_attempt_untouched = true", shutdown)
        self.assertIn("result->pending_edge_journal_untouched = true", shutdown)
        self.assertNotIn("egolink_sos_outbox_", shutdown)
        self.assertNotIn("egolink_outbox_", shutdown)
        self.assertNotIn("egolink_outbox_handle_ack", shutdown)
        self.assertNotIn("egolink_outbox_deinit", shutdown)
        self.assertNotIn("EGOLINK_OUTBOX_ACK_ACCEPTED", shutdown)

    def test_single_owner_and_payload_nonclaims_are_explicit(self) -> None:
        normalized = " ".join(
            (self.header + self.packet).replace("*", " ").split()
        ).casefold()
        for phrase in (
            "exactly one external task or mutex must serialize",
            "local busy guard rejects recursion but is not a lock",
            "never initializes",
            "deinitializes or deletes",
            "no safety-event payload, coordinate, media, secret",
            "sequence is consumed only after that exact lineage is durably recoverable",
            "journal is cleared only after",
            "p0-sos",
        ):
            self.assertIn(phrase, normalized)
        self.assertIsNone(re.search(r"\b(?:malloc|calloc|realloc|free)\s*\(", self.source))

    def test_actual_c_cross_compiles_for_esp32s3_with_warnings_as_errors(self) -> None:
        toolchain = _esp_toolchain()
        if toolchain is None:
            self.skipTest("ESP32-S3 cross compiler or ESP-IDF unavailable")
        compiler, _ = toolchain
        with tempfile.TemporaryDirectory(prefix="egolink-sos-runtime-cross-") as temp:
            output = Path(temp) / "sos_device_runtime.o"
            completed = subprocess.run(
                [
                    str(compiler),
                    "-std=c11",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-Wconversion",
                    "-Wformat=2",
                    "-Wshadow",
                    "-Wsign-conversion",
                    *(f"-I{path}" for path in _include_paths()),
                    "-c",
                    str(SOURCE),
                    "-o",
                    str(output),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertTrue(output.is_file())

            harness = Path(temp) / "composition_harness.c"
            harness.write_text(_behavioral_harness_source(), encoding="utf-8")
            harness_output = Path(temp) / "composition_harness.elf"
            harness_build = subprocess.run(
                [
                    str(compiler),
                    "-std=c11",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-Wconversion",
                    "-Wformat=2",
                    "-Wshadow",
                    "-Wsign-conversion",
                    *(f"-I{path}" for path in _include_paths()),
                    str(SOURCE),
                    str(COMPONENTS / "sos_input" / "sos_input.c"),
                    str(COMPONENTS / "sos_orchestrator" / "sos_orchestrator.c"),
                    str(COMPONENTS / "sos_pending_edge_journal" / "sos_pending_edge_journal.c"),
                    str(harness),
                    "-o",
                    str(harness_output),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(0, harness_build.returncode, harness_build.stderr)
            self.assertTrue(harness_output.is_file())

    def test_native_c_composition_when_host_compiler_is_available(self) -> None:
        compiler = _native_compiler()
        if compiler is None:
            self.skipTest("native host GCC/Clang unavailable")
        with tempfile.TemporaryDirectory(prefix="egolink-sos-runtime-native-") as temp:
            temp_path = Path(temp)
            harness = temp_path / "harness.c"
            harness.write_text(_behavioral_harness_source(), encoding="utf-8")
            executable = temp_path / "harness.exe"
            completed = subprocess.run(
                [
                    str(compiler),
                    "-std=c11",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-Wconversion",
                    "-Wformat=2",
                    "-Wshadow",
                    "-Wsign-conversion",
                    *(f"-I{path}" for path in _include_paths()),
                    str(SOURCE),
                    str(COMPONENTS / "sos_input" / "sos_input.c"),
                    str(COMPONENTS / "sos_orchestrator" / "sos_orchestrator.c"),
                    str(COMPONENTS / "sos_pending_edge_journal" / "sos_pending_edge_journal.c"),
                    str(harness),
                    "-o",
                    str(executable),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            executed = subprocess.run(
                [str(executable)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(0, executed.returncode, executed.stderr)


if __name__ == "__main__":
    unittest.main()

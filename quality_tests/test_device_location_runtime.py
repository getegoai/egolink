"""Focused LOC-021K checks for the dormant device location runtime owner.

The actual C owner is cross-compiled for ESP32-S3. Its host executable harness
runs only when a real native GCC/Clang is installed; the Xtensa compiler is
never treated as executable host evidence. No test performs storage, network,
device, flash, sensor, actuator, SOS, or transport I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
COMPONENT = COMPONENTS / "device_location_runtime"
SOURCE = COMPONENT / "device_location_runtime.c"
HEADER = COMPONENT / "include" / "device_location_runtime.h"
CMAKE = COMPONENT / "CMakeLists.txt"
APP_MAIN = ROOT / "firmware" / "mqtt_heartbeat" / "main" / "app_main.c"


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


def _include_paths(idf: Path | None = None) -> tuple[Path, ...]:
    paths = (
        COMPONENT / "include",
        COMPONENTS / "location_runtime_pipeline" / "include",
        COMPONENTS / "location_engine_core" / "include",
        COMPONENTS / "location_policy_core" / "include",
        COMPONENTS / "location_state_emitter" / "include",
        COMPONENTS / "location_outbox_adapter" / "include",
        COMPONENTS / "persistent_priority_outbox" / "include",
    )
    if idf is None:
        return paths
    return paths + (
        idf / "components" / "mbedtls" / "mbedtls" / "include",
        idf / "components" / "mbedtls" / "port" / "include",
    )


def _behavioral_harness_source() -> str:
    return textwrap.dedent(
        r"""
        #include "device_location_runtime.h"

        #include <stdint.h>
        #include <string.h>

        #define REQUIRE(condition) do { if (!(condition)) { return __LINE__; } } while (0)
        #define TEXT(value) \
            (egolink_location_runtime_text_t){(value), sizeof(value) - 1U}

        static egolink_location_runtime_status_t next_pipeline_status;
        static bool next_policy_evaluated;
        static bool next_published;
        static egolink_location_policy_gnss_action_t next_gnss_action;
        static bool next_cell_observe;
        static double next_imu_rate_hz;
        static bool next_lte_keep_connected;
        static bool fail_cell;
        static bool fail_imu;
        static bool fail_lte;
        static unsigned int callback_count;
        static unsigned int cancel_count;
        static char callback_order[16];

        egolink_location_runtime_status_t egolink_location_runtime_pipeline_init(
            egolink_location_runtime_pipeline_t *pipeline,
            egolink_location_outbox_adapter_t *adapter,
            const egolink_location_runtime_owner_t *owner)
        {
            (void)pipeline;
            (void)adapter;
            (void)owner;
            return EGOLINK_LOCATION_RUNTIME_OK_NO_PUBLISH;
        }

        egolink_location_runtime_status_t egolink_location_runtime_pipeline_process(
            egolink_location_runtime_pipeline_t *pipeline,
            const egolink_location_runtime_input_t *input,
            uint64_t outbox_now_ms,
            egolink_location_runtime_scratch_t *scratch,
            egolink_location_runtime_result_t *result)
        {
            (void)pipeline;
            (void)input;
            (void)outbox_now_ms;
            (void)scratch;
            (void)memset(result, 0, sizeof(*result));
            result->status = next_pipeline_status;
            result->policy_evaluated = next_policy_evaluated;
            result->published = next_published;
            if (next_policy_evaluated) {
                result->policy_decision.policy_mode =
                    EGOLINK_LOCATION_POLICY_LOCATION_UNCERTAIN;
                result->policy_decision.gnss_action =
                    next_gnss_action;
                result->policy_decision.gnss_acquisition_timeout_ms = UINT64_C(45000);
                result->policy_decision.cell_observe_now = next_cell_observe;
                result->policy_decision.cell_request_timeout_ms = UINT64_C(15000);
                result->policy_decision.imu_rate_hz = next_imu_rate_hz;
                result->policy_decision.lte_keep_connected =
                    next_lte_keep_connected;
            }
            if (next_published) {
                static const char digest[] =
                    "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
                (void)memcpy(result->enqueue_result.event_id, "loc-", 4U);
                (void)memcpy(result->enqueue_result.event_id + 4U,
                             digest, sizeof(digest));
                (void)memcpy(result->enqueue_result.payload_sha256,
                             digest, sizeof(digest));
                result->enqueue_result.payload_length = 1800U;
                result->enqueue_result.priority = EGOLINK_OUTBOX_PRIORITY_NORMAL;
                result->publish_reasons =
                    EGOLINK_LOCATION_RUNTIME_PUBLISH_REASON_POLICY_ACTION;
            }
            return next_pipeline_status;
        }

        static bool gnss_start(
            void *context,
            const egolink_device_location_gnss_start_request_t *request)
        {
            (void)context;
            REQUIRE(request->identity != NULL);
            REQUIRE(request->acquisition_timeout_ms == UINT64_C(45000));
            callback_order[callback_count++] = 'g';
            return true;
        }

        static bool gnss_stop(
            void *context,
            const egolink_device_location_gnss_stop_request_t *request)
        {
            (void)context;
            REQUIRE(request->identity != NULL && request->timeout_stop);
            callback_order[callback_count++] = 's';
            return true;
        }

        static bool cell_observe(
            void *context,
            const egolink_device_location_cell_observe_request_t *request)
        {
            (void)context;
            REQUIRE(request->identity != NULL);
            REQUIRE(request->request_timeout_ms == UINT64_C(15000));
            callback_order[callback_count++] = 'c';
            return !fail_cell;
        }

        static bool imu_rate(
            void *context,
            const egolink_device_location_imu_rate_request_t *request)
        {
            (void)context;
            REQUIRE(request->identity != NULL);
            REQUIRE(request->rate_hz == next_imu_rate_hz);
            callback_order[callback_count++] = 'i';
            return !fail_imu;
        }

        static bool lte_keep_connected(
            void *context,
            const egolink_device_location_lte_connection_request_t *request)
        {
            (void)context;
            REQUIRE(request->identity != NULL);
            REQUIRE(request->keep_connected == next_lte_keep_connected);
            callback_order[callback_count++] = 'l';
            return !fail_lte;
        }

        static bool upload(
            void *context,
            const egolink_device_location_upload_intent_t *request)
        {
            (void)context;
            REQUIRE(request->identity != NULL);
            REQUIRE(request->durable_envelope_present);
            REQUIRE(request->event_id != NULL && request->payload_sha256 != NULL);
            REQUIRE(request->payload_length == 1800U);
            callback_order[callback_count++] = 'u';
            return true;
        }

        static bool cancel(
            void *context,
            const egolink_device_location_cancel_request_t *request)
        {
            (void)context;
            REQUIRE(request->durable_envelopes_retained);
            ++cancel_count;
            return true;
        }

        static egolink_location_runtime_input_t input(void)
        {
            egolink_location_runtime_input_t value = {0};
            value.identity.device_id = TEXT("loc021k-device");
            value.identity.boot_count = UINT64_C(7);
            value.identity.session_id = TEXT("loc021k-session");
            value.identity.stream_id = TEXT("loc021k-stream");
            value.identity.sequence_id = UINT64_C(1);
            value.identity.observation_id = TEXT("loc021k-observation-1");
            value.identity.event_time_ms = UINT64_C(1);
            value.identity.event_time_source =
                EGOLINK_LOCATION_TIME_TIMESTAMP_UTC_NS;
            value.identity.event_time_ns = UINT64_C(1000000);
            value.observation.type = EGOLINK_LOCATION_ENGINE_EVENT_TICK;
            value.observation.event_time_ms = UINT64_C(1);
            return value;
        }

        int main(void)
        {
            static egolink_outbox_t outbox;
            static egolink_outbox_t wrong_outbox;
            static egolink_location_outbox_adapter_t adapter;
            static egolink_device_location_runtime_t disabled;
            static egolink_device_location_runtime_t runtime;
            static egolink_device_location_runtime_t mismatch;
            static egolink_location_runtime_scratch_t scratch;
            egolink_device_location_runtime_config_t config;
            egolink_device_location_runtime_result_t result;
            egolink_device_location_runtime_snapshot_t status;
            egolink_device_location_action_outcome_t cancel_action;
            egolink_location_runtime_input_t item = input();

            egolink_device_location_runtime_default_config(&config);
            REQUIRE(!config.enabled);
            REQUIRE(egolink_device_location_runtime_init(
                        &disabled, &config, NULL, NULL) ==
                    EGOLINK_DEVICE_LOCATION_RUNTIME_DISABLED_STATUS);
            REQUIRE(egolink_device_location_runtime_process(
                        &disabled, &item, UINT64_C(1), &scratch, &result) ==
                    EGOLINK_DEVICE_LOCATION_RUNTIME_DISABLED_STATUS);
            REQUIRE(egolink_device_location_runtime_close(
                        &disabled, &cancel_action) ==
                    EGOLINK_DEVICE_LOCATION_RUNTIME_CLOSED_STATUS);

            config.enabled = true;
            config.pipeline_owner.device_id = TEXT("loc021k-device");
            config.pipeline_owner.boot_count = UINT64_C(7);
            config.pipeline_owner.session_id = TEXT("loc021k-session");
            config.pipeline_owner.stream_id = TEXT("loc021k-stream");
            config.pipeline_owner.clock_domain = EGOLINK_LOCATION_RUNTIME_CLOCK_UTC;
            config.callbacks.gnss_start = gnss_start;
            config.callbacks.gnss_stop = gnss_stop;
            config.callbacks.cell_observe = cell_observe;
            config.callbacks.set_imu_rate = imu_rate;
            config.callbacks.set_lte_keep_connected = lte_keep_connected;
            config.callbacks.upload_intent = upload;
            config.callbacks.safe_cancel = cancel;
            adapter.outbox = &outbox;
            adapter.initialized = true;

            REQUIRE(egolink_device_location_runtime_init(
                        &runtime, &config, &outbox, &adapter) ==
                    EGOLINK_DEVICE_LOCATION_RUNTIME_OK);
            next_pipeline_status = EGOLINK_LOCATION_RUNTIME_OK_PUBLISHED;
            next_policy_evaluated = true;
            next_published = true;
            next_gnss_action = EGOLINK_LOCATION_POLICY_GNSS_ACTION_START;
            next_cell_observe = true;
            next_imu_rate_hz = 12.5;
            next_lte_keep_connected = true;
            fail_cell = true;
            REQUIRE(egolink_device_location_runtime_process(
                        &runtime, &item, UINT64_C(1), &scratch, &result) ==
                    EGOLINK_DEVICE_LOCATION_RUNTIME_ACTION_PARTIAL_FAILURE);
            REQUIRE(result.new_input_committed && result.durable_envelope_present);
            REQUIRE(result.action_failure_after_commit);
            REQUIRE(result.actions.gnss_start ==
                    EGOLINK_DEVICE_LOCATION_ACTION_SUCCEEDED);
            REQUIRE(result.actions.cell_observe ==
                    EGOLINK_DEVICE_LOCATION_ACTION_FAILED);
            REQUIRE(result.actions.imu_rate ==
                    EGOLINK_DEVICE_LOCATION_ACTION_SUCCEEDED);
            REQUIRE(result.actions.lte_keep_connected ==
                    EGOLINK_DEVICE_LOCATION_ACTION_SUCCEEDED);
            REQUIRE(result.actions.upload_intent ==
                    EGOLINK_DEVICE_LOCATION_ACTION_SUCCEEDED);
            REQUIRE(callback_count == 5U);
            REQUIRE(memcmp(callback_order, "gcilu", 5U) == 0);

            next_pipeline_status = EGOLINK_LOCATION_RUNTIME_DUPLICATE_INPUT;
            next_policy_evaluated = false;
            next_published = false;
            REQUIRE(egolink_device_location_runtime_process(
                    &runtime, &item, UINT64_C(2), &scratch, &result) ==
                    EGOLINK_DEVICE_LOCATION_RUNTIME_DUPLICATE_INPUT);
            REQUIRE(callback_count == 5U);

            next_pipeline_status = EGOLINK_LOCATION_RUNTIME_OK_NO_PUBLISH;
            next_policy_evaluated = true;
            next_gnss_action = EGOLINK_LOCATION_POLICY_GNSS_ACTION_WAIT_INTERVAL;
            next_cell_observe = false;
            ++item.identity.sequence_id;
            ++item.identity.event_time_ms;
            item.observation.event_time_ms = item.identity.event_time_ms;
            REQUIRE(egolink_device_location_runtime_process(
                        &runtime, &item, UINT64_C(3), &scratch, &result) ==
                    EGOLINK_DEVICE_LOCATION_RUNTIME_OK);
            REQUIRE(result.actions.imu_rate ==
                    EGOLINK_DEVICE_LOCATION_ACTION_NOT_REQUESTED);
            REQUIRE(result.actions.lte_keep_connected ==
                    EGOLINK_DEVICE_LOCATION_ACTION_NOT_REQUESTED);
            REQUIRE(callback_count == 5U);

            next_imu_rate_hz = 25.0;
            next_lte_keep_connected = false;
            fail_imu = true;
            fail_lte = true;
            ++item.identity.sequence_id;
            ++item.identity.event_time_ms;
            item.observation.event_time_ms = item.identity.event_time_ms;
            REQUIRE(egolink_device_location_runtime_process(
                        &runtime, &item, UINT64_C(4), &scratch, &result) ==
                    EGOLINK_DEVICE_LOCATION_RUNTIME_ACTION_PARTIAL_FAILURE);
            REQUIRE(result.actions.imu_rate ==
                    EGOLINK_DEVICE_LOCATION_ACTION_FAILED);
            REQUIRE(result.actions.lte_keep_connected ==
                    EGOLINK_DEVICE_LOCATION_ACTION_FAILED);
            REQUIRE(callback_count == 7U);
            REQUIRE(memcmp(callback_order, "gciluil", 7U) == 0);

            fail_imu = false;
            fail_lte = false;
            ++item.identity.sequence_id;
            ++item.identity.event_time_ms;
            item.observation.event_time_ms = item.identity.event_time_ms;
            REQUIRE(egolink_device_location_runtime_process(
                        &runtime, &item, UINT64_C(5), &scratch, &result) ==
                    EGOLINK_DEVICE_LOCATION_RUNTIME_OK);
            REQUIRE(result.actions.imu_rate ==
                    EGOLINK_DEVICE_LOCATION_ACTION_SUCCEEDED);
            REQUIRE(result.actions.lte_keep_connected ==
                    EGOLINK_DEVICE_LOCATION_ACTION_SUCCEEDED);
            REQUIRE(callback_count == 9U);
            REQUIRE(memcmp(callback_order, "gciluilil", 9U) == 0);

            next_pipeline_status = EGOLINK_LOCATION_RUNTIME_RETRY_REQUIRED;
            next_policy_evaluated = false;
            ++item.identity.sequence_id;
            ++item.identity.event_time_ms;
            item.observation.event_time_ms = item.identity.event_time_ms;
            REQUIRE(egolink_device_location_runtime_process(
                        &runtime, &item, UINT64_C(6), &scratch, &result) ==
                    EGOLINK_DEVICE_LOCATION_RUNTIME_PIPELINE_RETRY_REQUIRED);
            REQUIRE(callback_count == 9U);

            REQUIRE(egolink_device_location_runtime_current_status(
                        &runtime, &status) == EGOLINK_DEVICE_LOCATION_RUNTIME_OK);
            REQUIRE(status.committed_inputs == UINT64_C(4));
            REQUIRE(status.duplicate_inputs == UINT64_C(1));
            REQUIRE(status.durable_envelopes == UINT64_C(1));
            REQUIRE(status.pipeline_failures == UINT64_C(1));
            REQUIRE(status.action_requests == UINT64_C(9));
            REQUIRE(status.action_failures == UINT64_C(3));

            REQUIRE(egolink_device_location_runtime_cancel(
                        &runtime, &cancel_action) ==
                    EGOLINK_DEVICE_LOCATION_RUNTIME_CANCELLED_STATUS);
            REQUIRE(cancel_action == EGOLINK_DEVICE_LOCATION_ACTION_SUCCEEDED);
            REQUIRE(cancel_count == 1U);
            REQUIRE(egolink_device_location_runtime_process(
                        &runtime, &item, UINT64_C(7), &scratch, &result) ==
                    EGOLINK_DEVICE_LOCATION_RUNTIME_CANCELLED_STATUS);
            REQUIRE(egolink_device_location_runtime_close(
                        &runtime, &cancel_action) ==
                    EGOLINK_DEVICE_LOCATION_RUNTIME_CLOSED_STATUS);
            REQUIRE(cancel_count == 1U);
            REQUIRE(egolink_device_location_runtime_current_status(
                        &runtime, &status) ==
                    EGOLINK_DEVICE_LOCATION_RUNTIME_CLOSED_STATUS);
            REQUIRE(!status.dependency_bound);

            adapter.outbox = &wrong_outbox;
            REQUIRE(egolink_device_location_runtime_init(
                        &mismatch, &config, &outbox, &adapter) ==
                    EGOLINK_DEVICE_LOCATION_RUNTIME_DEPENDENCY_MISMATCH);
            return 0;
        }
        """
    )


@dataclass
class _OwnerOracle:
    pipeline_commits: int = 0
    durable_envelopes: int = 0
    callback_order: list[str] = field(default_factory=list)
    automatic_retries: int = 0
    applied_imu_rate_hz: float | None = None
    applied_lte_keep_connected: bool | None = None

    def process_published(self, outcomes: dict[str, bool]) -> str:
        self.pipeline_commits += 1
        self.durable_envelopes += 1
        failed = False
        for name in (
            "gnss_start",
            "cell_observe",
            "imu_rate",
            "lte_keep_connected",
            "upload_intent",
        ):
            self.callback_order.append(name)
            failed = not outcomes[name] or failed
        return "partial" if failed else "ok"

    def apply_declarations(
        self,
        imu_rate_hz: float,
        lte_keep_connected: bool,
        outcomes: dict[str, bool],
    ) -> str:
        failed = False
        if self.applied_imu_rate_hz != imu_rate_hz:
            self.callback_order.append("imu_rate")
            if outcomes["imu_rate"]:
                self.applied_imu_rate_hz = imu_rate_hz
            else:
                failed = True
        if self.applied_lte_keep_connected != lte_keep_connected:
            self.callback_order.append("lte_keep_connected")
            if outcomes["lte_keep_connected"]:
                self.applied_lte_keep_connected = lte_keep_connected
            else:
                failed = True
        return "partial" if failed else "ok"


class DeviceLocationRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.header = HEADER.read_text(encoding="utf-8")
        cls.cmake = CMAKE.read_text(encoding="utf-8")

    def _function(self, name: str, next_name: str) -> str:
        start = self.source.index(name)
        return self.source[start:self.source.index(next_name, start + len(name))]

    def test_component_is_default_off_dormant_and_has_no_automatic_io(self) -> None:
        self.assertIn('SRCS "device_location_runtime.c"', self.cmake)
        for dependency in (
            "location_runtime_pipeline",
            "location_outbox_adapter",
            "persistent_priority_outbox",
        ):
            self.assertIn(dependency, self.cmake)
        for option in (
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wconversion",
            "-Wformat=2",
            "-Wshadow",
            "-Wsign-conversion",
        ):
            self.assertIn(option, self.cmake)
        default = self._function(
            "void egolink_device_location_runtime_default_config(",
            "egolink_device_location_runtime_status_t\n"
            "egolink_device_location_runtime_init(",
        )
        self.assertIn("config->enabled = false", default)
        for forbidden in (
            "xTaskCreate",
            "freertos/",
            "esp_http",
            "esp_partition",
            "nvs_",
            "gpio_",
            "socket(",
            "esp_log",
            "printf(",
            "egolink_location_outbox_adapter_init(",
            "egolink_location_outbox_adapter_deinit(",
            "egolink_outbox_init(",
            "egolink_outbox_deinit(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden.casefold(), self.source.casefold())
        self.assertNotIn("device_location_runtime", APP_MAIN.read_text(encoding="utf-8"))

    def test_shared_outbox_identity_and_single_owner_boundary_are_explicit(self) -> None:
        initialize = self._function(
            "egolink_device_location_runtime_init(",
            "egolink_device_location_runtime_process(",
        )
        check = "location_adapter->outbox != shared_outbox"
        self.assertIn(check, initialize)
        self.assertLess(
            initialize.index(check),
            initialize.index("egolink_location_runtime_pipeline_init("),
        )
        normalized = " ".join(self.header.split())
        for phrase in (
            "already be initialized by one external owner",
            "identical shared_outbox pointer",
            "supplied to SOS orchestration",
            "serialize process/cancel/close with SOS enqueue",
            "not a cross-task lock",
        ):
            self.assertIn(phrase, normalized)

    def test_pipeline_commits_before_fixed_order_actions(self) -> None:
        process = self._function(
            "egolink_device_location_runtime_process(",
            "egolink_device_location_runtime_cancel(",
        )
        pipeline = process.index("egolink_location_runtime_pipeline_process(")
        committed = process.index("result->new_input_committed = true")
        gnss_start = process.index("invoke_gnss_start(")
        gnss_stop = process.index("invoke_gnss_stop(")
        cell = process.index("invoke_cell_observe(")
        imu = process.index("invoke_imu_rate(")
        lte = process.index("invoke_lte_keep_connected(")
        upload = process.index("invoke_upload_intent(")
        self.assertLess(pipeline, committed)
        self.assertLess(committed, gnss_start)
        self.assertLess(gnss_start, gnss_stop)
        self.assertLess(gnss_stop, cell)
        self.assertLess(cell, imu)
        self.assertLess(imu, lte)
        self.assertLess(lte, upload)
        duplicate_return = process.index(
            "EGOLINK_DEVICE_LOCATION_RUNTIME_DUPLICATE_INPUT"
        )
        failure_return = process.index(
            "EGOLINK_DEVICE_LOCATION_RUNTIME_PIPELINE_RETRY_REQUIRED"
        )
        self.assertLess(duplicate_return, gnss_start)
        self.assertLess(failure_return, gnss_start)

    def test_policy_actions_have_exact_narrow_mapping(self) -> None:
        for marker in (
            "EGOLINK_LOCATION_POLICY_GNSS_ACTION_START",
            "EGOLINK_LOCATION_POLICY_GNSS_ACTION_STOP_TIMEOUT",
            "decision->cell_observe_now",
            "decision->imu_rate_hz",
            "decision->lte_keep_connected",
            "pipeline_result->published",
        ):
            self.assertIn(marker, self.source)
        for callback in (
            "gnss_start",
            "gnss_stop",
            "cell_observe",
            "set_imu_rate",
            "set_lte_keep_connected",
            "upload_intent",
            "safe_cancel",
        ):
            self.assertIn(callback, self.header)
        result_definition = self.header[
            self.header.index("typedef struct {\n    egolink_device_location_runtime_status_t status;"):
            self.header.index("} egolink_device_location_runtime_result_t;")
        ]
        for private in ("latitude", "longitude", "observation payload", "media"):
            self.assertNotIn(private, result_definition.casefold())
        self.assertNotRegex(result_definition, r"char\s+\w+\[")

    def test_action_failure_cannot_rollback_durable_envelope_or_auto_retry(self) -> None:
        oracle = _OwnerOracle()
        result = oracle.process_published(
            {
                "gnss_start": True,
                "cell_observe": False,
                "imu_rate": True,
                "lte_keep_connected": True,
                "upload_intent": True,
            }
        )
        self.assertEqual("partial", result)
        self.assertEqual(1, oracle.pipeline_commits)
        self.assertEqual(1, oracle.durable_envelopes)
        self.assertEqual(
            [
                "gnss_start",
                "cell_observe",
                "imu_rate",
                "lte_keep_connected",
                "upload_intent",
            ],
            oracle.callback_order,
        )
        self.assertEqual(0, oracle.automatic_retries)
        process = self._function(
            "egolink_device_location_runtime_process(",
            "egolink_device_location_runtime_cancel(",
        )
        self.assertNotIn("while (", process)
        self.assertNotIn("for (", process)
        normalized = " ".join(self.header.split())
        self.assertIn("never roll back a committed", normalized)
        self.assertIn("There is no background task or implicit", normalized)

    def test_imu_and_lte_declarations_are_deduplicated_and_retry_after_failure(
        self,
    ) -> None:
        oracle = _OwnerOracle()
        self.assertEqual(
            "ok",
            oracle.apply_declarations(
                12.5,
                True,
                {"imu_rate": True, "lte_keep_connected": True},
            ),
        )
        self.assertEqual(["imu_rate", "lte_keep_connected"], oracle.callback_order)
        self.assertEqual(
            "ok",
            oracle.apply_declarations(
                12.5,
                True,
                {"imu_rate": True, "lte_keep_connected": True},
            ),
        )
        self.assertEqual(["imu_rate", "lte_keep_connected"], oracle.callback_order)
        self.assertEqual(
            "partial",
            oracle.apply_declarations(
                25.0,
                False,
                {"imu_rate": False, "lte_keep_connected": False},
            ),
        )
        self.assertEqual(12.5, oracle.applied_imu_rate_hz)
        self.assertTrue(oracle.applied_lte_keep_connected)
        self.assertEqual(
            "ok",
            oracle.apply_declarations(
                25.0,
                False,
                {"imu_rate": True, "lte_keep_connected": True},
            ),
        )
        self.assertEqual(
            [
                "imu_rate",
                "lte_keep_connected",
                "imu_rate",
                "lte_keep_connected",
                "imu_rate",
                "lte_keep_connected",
            ],
            oracle.callback_order,
        )
        self.assertEqual(25.0, oracle.applied_imu_rate_hz)
        self.assertFalse(oracle.applied_lte_keep_connected)

    def test_cancel_and_close_are_terminal_and_do_not_close_dependencies(self) -> None:
        cancel = self._function(
            "egolink_device_location_runtime_cancel(",
            "egolink_device_location_runtime_close(",
        )
        close = self._function(
            "egolink_device_location_runtime_close(",
            "egolink_device_location_runtime_current_status(",
        )
        self.assertEqual(1, cancel.count("perform_cancel("))
        self.assertEqual(1, close.count("perform_cancel("))
        self.assertIn("EGOLINK_DEVICE_LOCATION_RUNTIME_CANCELLED", cancel)
        self.assertIn("EGOLINK_DEVICE_LOCATION_RUNTIME_CLOSED", close)
        self.assertIn("clear_bound_runtime(internal)", cancel)
        self.assertIn("clear_bound_runtime(internal)", close)
        for body in (cancel, close):
            self.assertNotIn("deinit", body.casefold())
        normalized = " ".join(self.header.split())
        self.assertIn("durable outbox data", normalized)
        self.assertIn("does not claim reboot/cancel equivalence", normalized)

    def test_actual_c_native_behavior_when_host_compiler_exists(self) -> None:
        compiler = _native_compiler()
        if compiler is None:
            self.skipTest("native host GCC/Clang unavailable; Xtensa is not executed")
        with tempfile.TemporaryDirectory(prefix="egolink-loc021k-native-") as temporary:
            temp = Path(temporary)
            harness = temp / "device_location_runtime_harness.c"
            executable = temp / "device_location_runtime_harness.exe"
            harness.write_text(_behavioral_harness_source(), encoding="utf-8")
            build = subprocess.run(
                [
                    str(compiler),
                    "-std=c11",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    *(f"-I{path}" for path in _include_paths()),
                    str(SOURCE),
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
            self.assertEqual(0, build.returncode, build.stderr)
            run = subprocess.run(
                [str(executable)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        self.assertEqual(0, run.returncode, run.stderr)

    def test_actual_source_and_behavioral_harness_cross_compile_for_esp32s3(self) -> None:
        toolchain = _esp_toolchain()
        if toolchain is None:
            self.skipTest("ESP32-S3 compiler or ESP-IDF headers unavailable")
        compiler, idf = toolchain
        flags = [
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wconversion",
            "-Wformat=2",
            "-Wshadow",
            "-Wsign-conversion",
            *(f"-I{path}" for path in _include_paths(idf)),
        ]
        with tempfile.TemporaryDirectory(prefix="egolink-loc021k-cross-") as temporary:
            temp = Path(temporary)
            harness = temp / "device_location_runtime_harness.c"
            harness.write_text(_behavioral_harness_source(), encoding="utf-8")
            commands = (
                [*flags, "-fstack-usage", "-c", str(SOURCE), "-o", str(temp / "owner.o")],
                [*flags, "-c", str(harness), "-o", str(temp / "harness.o")],
            )
            for command in commands:
                result = subprocess.run(
                    [str(compiler), *command],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                self.assertEqual(0, result.returncode, result.stderr)
            stack = (temp / "owner.su").read_text(encoding="utf-8")
        expected = {
            "egolink_device_location_runtime_init": 128,
            "egolink_device_location_runtime_process": 128,
            "egolink_device_location_runtime_cancel": 128,
            "egolink_device_location_runtime_close": 128,
            "egolink_device_location_runtime_current_status": 128,
        }
        for function, ceiling in expected.items():
            match = re.search(rf"{function}\t(\d+)\t", stack)
            self.assertIsNotNone(match, function)
            self.assertLessEqual(int(match.group(1)), ceiling)

    def test_target_context_result_snapshot_and_scratch_sizes_are_explicit(self) -> None:
        toolchain = _esp_toolchain()
        if toolchain is None:
            self.skipTest("ESP32-S3 compiler or ESP-IDF headers unavailable")
        compiler, idf = toolchain
        nm = compiler.with_name("xtensa-esp32s3-elf-nm.exe")
        if not nm.is_file():
            self.skipTest("ESP32-S3 nm unavailable")
        probe_source = textwrap.dedent(
            """
            #include "device_location_runtime.h"
            unsigned char size_owner_context[sizeof(egolink_device_location_runtime_t)];
            unsigned char size_owner_result[sizeof(egolink_device_location_runtime_result_t)];
            unsigned char size_owner_snapshot[sizeof(egolink_device_location_runtime_snapshot_t)];
            unsigned char size_pipeline_scratch[sizeof(egolink_location_runtime_scratch_t)];
            """
        )
        with tempfile.TemporaryDirectory(prefix="egolink-loc021k-size-") as temporary:
            temp = Path(temporary)
            probe = temp / "size_probe.c"
            object_path = temp / "size_probe.o"
            probe.write_text(probe_source, encoding="utf-8")
            build = subprocess.run(
                [
                    str(compiler),
                    "-std=c11",
                    *(f"-I{path}" for path in _include_paths(idf)),
                    "-c",
                    str(probe),
                    "-o",
                    str(object_path),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(0, build.returncode, build.stderr)
            symbols = subprocess.run(
                [str(nm), "-S", "--size-sort", str(object_path)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(0, symbols.returncode, symbols.stderr)
        sizes = {
            match.group(2): int(match.group(1), 16)
            for match in re.finditer(
                r"^[0-9a-fA-F]+\s+([0-9a-fA-F]+)\s+[A-Za-z]\s+(size_[A-Za-z0-9_]+)$",
                symbols.stdout,
                re.MULTILINE,
            )
        }
        self.assertEqual(10 * 1024, sizes["size_owner_context"])
        self.assertLess(sizes["size_owner_result"], 1024)
        self.assertLess(sizes["size_owner_snapshot"], 512)
        self.assertEqual(7170, sizes["size_pipeline_scratch"])


if __name__ == "__main__":
    unittest.main()

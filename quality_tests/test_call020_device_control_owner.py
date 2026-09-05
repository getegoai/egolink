"""Offline source/boundary checks for the CALL-020R device owner.

The failure-injection harness compiles the actual owner C for every injected
cleanup stage and runs it only when native Windows LLVM tooling is available.
No serial, audio, modem or network path is opened. ESP-IDF compile/link remains
a separate build-only gate.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "firmware/audio_loop/main"
OWNER_H = MAIN / "call020_device_control_owner.h"
OWNER_C = MAIN / "call020_device_control_owner.c"
OWNER_BOOT = MAIN / "call020_device_control_owner_boot.c"
RESPONDER_H = MAIN / "call020_device_control_responder.h"
RESPONDER_C = MAIN / "call020_device_control_responder.c"
CMAKE = MAIN / "CMakeLists.txt"
KCONFIG = MAIN / "Kconfig.projbuild"
DEFAULTS = ROOT / "firmware/audio_loop/sdkconfig.call020_device_owner.defaults"
RUNNER_DEFAULTS = ROOT / "firmware/audio_loop/sdkconfig.call020_operator_runner.defaults"
APP_MAIN = MAIN / "app_main.c"
PACKET = ROOT / "docs/tasks/active/CALL-020_LTE_DATA_VOICE_POC.md"


def _native_tools() -> tuple[Path, Path] | None:
    root = Path("C:/Espressif/tools/esp-clang/esp-18.1.2_20240912/esp-clang/bin")
    clang = root / "clang.exe"
    linker = root / "lld.exe"
    if not clang.is_file() or not linker.is_file():
        return None
    probe = subprocess.run(
        [str(clang), "--print-targets"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if probe.returncode != 0 or "x86" not in probe.stdout.casefold():
        return None
    return clang, linker


def _cross_compiler() -> Path | None:
    candidates = (
        shutil.which("xtensa-esp32s3-elf-gcc"),
        "C:/Espressif/tools/xtensa-esp-elf/esp-14.2.0_20241119/"
        "xtensa-esp-elf/bin/xtensa-esp32s3-elf-gcc.exe",
    )
    return next(
        (Path(value) for value in candidates if value and Path(value).is_file()),
        None,
    )


OWNER_RECOVERY_HARNESS = r"""
#include <stddef.h>
#include <stdint.h>
#include "call020_device_control_owner.c"

static call020_device_control_responder_metadata_t fake_responder_metadata;
static uint32_t fake_finish_calls;
static uint32_t fake_delay_calls;
static uint32_t fake_abort_calls;

void *memset(void *destination, int value, size_t bytes) {
    unsigned char *cursor = (unsigned char *)destination;
    while (bytes-- > 0U) {
        *cursor++ = (unsigned char)value;
    }
    return destination;
}

int64_t esp_timer_get_time(void) {
    static int64_t now = 1000;
    static uint32_t calls;
    calls++;
#if POST_SERVE_BOUNDARY == 1
    if (calls == 3U) return 1002000;
#elif POST_SERVE_BOUNDARY == 2
    if (calls == 3U) return -1;
#endif
    now += 1000;
    return now;
}

int xPortGetCoreID(void) { return 0; }
void taskYIELD(void) {}
void vTaskDelay(TickType_t ticks) {
    if (ticks == 0U) {
        fake_delay_calls = UINT32_MAX;
    } else {
        fake_delay_calls++;
    }
}

esp_err_t call020_device_control_responder_init(
    call020_device_control_responder_t *responder,
    const call020_device_control_responder_config_t *config) {
    (void)responder;
    (void)config;
    memset(&fake_responder_metadata, 0, sizeof(fake_responder_metadata));
    fake_responder_metadata.state = CALL020_DEVICE_CONTROL_DORMANT;
    return ESP_OK;
}

esp_err_t call020_device_control_responder_open_control(
    call020_device_control_responder_t *responder) {
    (void)responder;
    fake_responder_metadata.state = CALL020_DEVICE_CONTROL_OWNED;
    fake_responder_metadata.lease_installed = true;
    return ESP_OK;
}

call020_device_control_serve_result_t
call020_device_control_responder_serve_once(
    call020_device_control_responder_t *responder) {
    (void)responder;
    fake_responder_metadata.state = CALL020_DEVICE_CONTROL_MEDIA;
    fake_responder_metadata.media_started = true;
    return CALL020_DEVICE_CONTROL_SERVE_MEDIA_STARTED;
}

esp_err_t call020_device_control_responder_abort_local(
    call020_device_control_responder_t *responder) {
    (void)responder;
    fake_abort_calls++;
    return ESP_ERR_INVALID_STATE;
}

esp_err_t call020_device_control_responder_finish_media_local(
    call020_device_control_responder_t *responder) {
    (void)responder;
    fake_finish_calls++;
    if (fake_finish_calls == 1U) {
        fake_responder_metadata.state = CALL020_DEVICE_CONTROL_TERMINAL;
        fake_responder_metadata.first_error = FAILURE_CODE;
        fake_responder_metadata.terminal_reason =
            CALL020_DEVICE_CONTROL_TERMINAL_LOCAL_CLEANUP;
#if FAILURE_STAGE >= 2
        fake_responder_metadata.media_workers_quiescent = true;
        fake_responder_metadata.media_output_safe_verified = true;
#endif
#if FAILURE_STAGE >= 3
        fake_responder_metadata.media_runner_resources_closed = true;
#endif
#if FAILURE_STAGE >= 4
        fake_responder_metadata.media_driver_lease_returned = true;
#endif
        return FAILURE_CODE;
    }
    fake_responder_metadata.state = CALL020_DEVICE_CONTROL_CLOSED;
    fake_responder_metadata.lease_installed = false;
    fake_responder_metadata.media_workers_quiescent = true;
    fake_responder_metadata.media_output_safe_verified = true;
    fake_responder_metadata.media_runner_resources_closed = true;
    fake_responder_metadata.media_driver_lease_returned = true;
    fake_responder_metadata.physical_driver_close_confirmed = true;
    fake_responder_metadata.device_runtime_termination_proven = true;
    return ESP_OK;
}

esp_err_t call020_device_control_responder_get_metadata(
    const call020_device_control_responder_t *responder,
    call020_device_control_responder_metadata_t *metadata) {
    (void)responder;
    *metadata = fake_responder_metadata;
    return ESP_OK;
}

esp_err_t call020_operator_runner_cancel(void) { return ESP_OK; }
esp_err_t call020_operator_runner_get_metadata(
    call020_operator_runner_metadata_t *metadata) {
    memset(metadata, 0, sizeof(*metadata));
    return ESP_OK;
}

int mainCRTStartup(void) {
    const call020_device_control_owner_config_t config = {
        .enabled = true,
        .control_total_timeout_us = UINT64_C(1000000),
        .poll_slice_ms = UINT32_C(1),
        .media_quiesce_grace_us = UINT64_C(200000),
        .responder = {
            .enabled = true,
            .frame_wait_timeout_ms = UINT32_C(10),
            .max_operation_timeout_ms = UINT32_C(100),
            .result_phase_enabled = false,
            .runner = {.max_runtime_us = UINT64_C(10000)},
        },
    };
    if (call020_device_control_owner_init(&config) != ESP_OK) return 10;
    if (call020_device_control_owner_init(&config) != ESP_ERR_INVALID_STATE) {
        return 11;
    }
    esp_err_t run_result = call020_device_control_owner_run();
#if POST_SERVE_BOUNDARY == 1
    if (run_result != ESP_ERR_TIMEOUT) return 12;
#elif POST_SERVE_BOUNDARY == 2
    if (run_result != ESP_ERR_INVALID_STATE) return 12;
#else
    if (run_result != FAILURE_CODE) return 12;
#endif
    call020_device_control_owner_metadata_t metadata = {0};
    if (call020_device_control_owner_get_metadata(&metadata) != ESP_OK) return 13;
    if (metadata.state != CALL020_DEVICE_OWNER_CLOSED) return 14;
    if (!metadata.cleanup_complete ||
        !metadata.device_runtime_termination_proven ||
        !metadata.physical_driver_close_confirmed) return 15;
    if (metadata.cleanup_recovery_attempts != 1U ||
        metadata.cleanup_backoff_waits != 1U || fake_delay_calls != 1U) {
        return 16;
    }
    if (metadata.media_finalize_calls != 2U || fake_finish_calls != 2U) return 17;
    if (fake_abort_calls != 0U) return 20;
    if (metadata.responder_first_error != FAILURE_CODE ||
        metadata.responder_terminal_reason !=
            CALL020_DEVICE_CONTROL_TERMINAL_LOCAL_CLEANUP) return 18;
    if (call020_device_control_owner_init(&config) != ESP_ERR_INVALID_STATE) {
        return 19;
    }
    return 0;
}
"""


class Call020DeviceControlOwnerContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.header = OWNER_H.read_text(encoding="utf-8")
        cls.source = OWNER_C.read_text(encoding="utf-8")
        cls.boot = OWNER_BOOT.read_text(encoding="utf-8")
        cls.responder_h = RESPONDER_H.read_text(encoding="utf-8")
        cls.responder_c = RESPONDER_C.read_text(encoding="utf-8")
        cls.cmake = CMAKE.read_text(encoding="utf-8")
        cls.kconfig = KCONFIG.read_text(encoding="utf-8")
        cls.defaults = DEFAULTS.read_text(encoding="utf-8")
        cls.runner_defaults = RUNNER_DEFAULTS.read_text(encoding="utf-8")
        cls.packet = PACKET.read_text(encoding="utf-8")

    def test_task_packet_explicitly_allows_the_r_slice(self) -> None:
        for relative in (
            "firmware/audio_loop/main/call020_device_control_owner.c",
            "firmware/audio_loop/main/call020_device_control_owner.h",
            "firmware/audio_loop/main/call020_device_control_owner_boot.c",
            "firmware/audio_loop/sdkconfig.call020_device_owner.defaults",
            "quality_tests/test_call020_device_control_owner.py",
        ):
            self.assertIn(f"  - {relative}", self.packet)

    def test_owner_is_default_off_and_only_new_profile_boots_it(self) -> None:
        block = re.search(
            r"config EGOLINK_CALL020_DEVICE_CONTROL_OWNER(?P<body>.*?)"
            r"\n\nconfig EGOLINK_CALL020_DEVICE_OWNER_CONTROL_TIMEOUT_MS",
            self.kconfig,
            re.S,
        )
        self.assertIsNotNone(block)
        self.assertIn("default n", block.group("body"))
        self.assertIn(
            "depends on EGOLINK_CALL020_DEVICE_CONTROL_RESPONDER",
            block.group("body"),
        )
        self.assertIn(
            "CONFIG_EGOLINK_CALL020_DEVICE_CONTROL_OWNER=y", self.defaults
        )
        self.assertNotIn(
            "CONFIG_EGOLINK_CALL020_DEVICE_CONTROL_OWNER=y",
            self.runner_defaults,
        )
        self.assertNotIn(
            "call020_device_control_owner",
            APP_MAIN.read_text(encoding="utf-8"),
        )
        self.assertIn("if(CONFIG_EGOLINK_CALL020_DEVICE_CONTROL_OWNER)", self.cmake)
        self.assertIn('"call020_device_control_owner_boot.c"', self.cmake)
        self.assertIn("elseif(CONFIG_EGOLINK_CALL020_OPERATOR_RUNNER)", self.cmake)

    def test_exactly_one_pinned_task_is_the_mutating_owner(self) -> None:
        self.assertEqual(self.boot.count("xTaskCreatePinnedToCore("), 1)
        self.assertEqual(self.boot.count("call020_device_control_owner_run()"), 1)
        self.assertIn("CONFIG_EGOLINK_CALL020_DEVICE_OWNER_TASK_CORE", self.boot)
        self.assertIn("s_owner.metadata.owner_core_id = (int)xPortGetCoreID()", self.source)
        self.assertIn("One global context makes a second lifecycle owner", self.source)
        self.assertNotIn("xTaskCreate", self.source)
        self.assertIn("if (created != pdPASS)", self.boot)
        self.assertIn("No owner API or hardware boundary has run", self.boot)

    def test_control_has_one_absolute_total_deadline(self) -> None:
        run = re.search(
            r"esp_err_t call020_device_control_owner_run\(void\)"
            r"(?P<body>.*?)\n}\n\nesp_err_t call020_device_control_owner_get_metadata",
            self.source,
            re.S,
        )
        self.assertIsNotNone(run)
        body = run.group("body")
        anchor = body.index("control_total_timeout_us")
        open_at = body.index("call020_device_control_responder_open_control(")
        loop_at = body.index("for (;;)", open_at)
        remaining_guard = body.index(
            "control_deadline_us - current_us < complete_serve_budget_us", loop_at
        )
        serve_at = body.index("call020_device_control_responder_serve_once(", loop_at)
        post_check = body.index("current_us >= control_deadline_us", serve_at)
        self.assertLess(anchor, open_at)
        self.assertLess(remaining_guard, serve_at)
        self.assertLess(serve_at, post_check)
        self.assertIn("max_operation_timeout_ms", body[anchor:serve_at])

    def test_media_owner_forces_cancel_then_waits_for_all_four(self) -> None:
        finish = re.search(
            r"static esp_err_t finish_media\(.*?(?P<body>.*?)"
            r"\n}\n\nconst char \*call020_device_control_owner_version",
            self.source,
            re.S,
        )
        self.assertIsNotNone(finish)
        body = finish.group("body")
        cancel = body.index("call020_operator_runner_cancel()")
        workers = body.index("four_workers_finished(&runner)", cancel)
        finalize = body.index("finalize_media_and_close()", workers)
        self.assertLess(cancel, workers)
        self.assertLess(workers, finalize)
        self.assertIn("media_quiesce_grace_us", body)
        self.assertIn("all_four_workers_terminal = true", body)
        self.assertIn("responder.media_workers_quiescent", self.source)
        self.assertRegex(
            body,
            r"media_terminal_observed\(&runner\)\s*\|\|\s*"
            r"four_workers_finished\(&runner\)",
        )

    def test_media_failure_survives_cleanup_but_normal_run_limit_does_not(self) -> None:
        reported = re.search(
            r"static esp_err_t runner_reported_failure\(.*?(?P<body>.*?)"
            r"\n}\n\nstatic bool copy_responder_state",
            self.source,
            re.S,
        )
        self.assertIsNotNone(reported)
        body = reported.group("body")
        self.assertIn("runner->first_error", body)
        self.assertIn("runner->composition.first_error", body)
        self.assertIn("runner->composition.run_limit_reached", body)
        self.assertIn("CALL020_WEARABLE_TERMINAL_RUNTIME", body)
        self.assertIn("media_failure_observed = true", body)

        finalize = re.search(
            r"static esp_err_t finalize_media_and_close\(void\)"
            r"(?P<body>.*?)\n}\n\nstatic esp_err_t finish_media",
            self.source,
            re.S,
        )
        self.assertIsNotNone(finalize)
        self.assertIn("runner_reported_failure(&runner)", finalize.group("body"))
        self.assertIn(
            "if (cleanup_proven)", finalize.group("body")
        )
        self.assertIn("return s_owner.metadata.first_error", finalize.group("body"))

    def test_cleanup_is_phase_reentrant_and_boot_never_abandons_owner(self) -> None:
        self.assertIn("bool recovery_entry", self.responder_c)
        self.assertIn("!internal->metadata.media_workers_quiescent", self.responder_c)
        self.assertIn("if (!internal->runner_closed)", self.responder_c)
        self.assertIn("already_physically_closed", self.responder_c)
        self.assertIn("CALL020_DEVICE_OWNER_RECOVERING", self.header)
        self.assertIn("cleanup_recovery_backoff()", self.source)
        self.assertIn("metadata.cleanup_complete", self.boot)
        parked = self.boot.index("for (;;)" )
        delayed = self.boot.index("vTaskDelay(", parked)
        self.assertLess(parked, delayed)
        self.assertNotIn(
            "(void)call020_device_control_owner_run();\n    }\n    vTaskDelete(NULL)",
            self.boot,
        )

    def test_singleton_reinit_and_precise_responder_diagnostics_are_guarded(self) -> None:
        init = re.search(
            r"call020_device_control_owner_init\(.*?(?P<body>.*?)"
            r"\n}\n\nesp_err_t call020_device_control_owner_run",
            self.source,
            re.S,
        )
        self.assertIsNotNone(init)
        body = init.group("body")
        claim = body.index("s_owner_init_claimed")
        clear = body.index("memset(&s_owner")
        self.assertLess(claim, clear)
        self.assertIn("return ESP_ERR_INVALID_STATE", body[:clear])
        self.assertIn("responder_first_error", self.header)
        self.assertIn("responder_terminal_reason", self.header)
        self.assertIn("precise_reason", self.source)

    def test_every_post_start_deadline_or_clock_failure_runs_local_finalizer(self) -> None:
        finish = re.search(
            r"static esp_err_t finish_media\(.*?(?P<body>.*?)"
            r"\n}\n\nconst char \*call020_device_control_owner_version",
            self.source,
            re.S,
        )
        self.assertIsNotNone(finish)
        body = finish.group("body")
        overflow = re.search(
            r"if \(!checked_add_u64\(.*?\)\) \{(?P<branch>.*?)\n    \}",
            body,
            re.S,
        )
        self.assertIsNotNone(overflow)
        self.assertIn("call020_operator_runner_cancel()", overflow.group("branch"))
        self.assertIn("finalize_media_and_close()", overflow.group("branch"))
        self.assertIn("if (!clock_valid)", body)
        self.assertIn("return finalize_media_and_close();", body)

    def test_responder_local_finalize_orders_join_close_return_and_physical_close(self) -> None:
        finalize = re.search(
            r"call020_device_control_responder_finish_media_local\("
            r"(?P<body>.*?)\n}\n\nesp_err_t "
            r"call020_device_control_responder_get_metadata",
            self.responder_c,
            re.S,
        )
        self.assertIsNotNone(finalize)
        body = finalize.group("body")
        cancel = body.index("call020_operator_runner_cancel()")
        join = body.index("call020_operator_runner_join()", cancel)
        four = body.index("workers_created == UINT32_C(4)", join)
        close = body.index("call020_operator_runner_close()", four)
        returned = body.index("CALL020_USB_DRIVER_LEASE_MEDIA_RETURNED", close)
        physical = body.index("call020_usb_driver_lease_close(", returned)
        proof = body.index("device_runtime_termination_proven = true", physical)
        self.assertLess(cancel, join)
        self.assertLess(join, four)
        self.assertLess(four, close)
        self.assertLess(close, returned)
        self.assertLess(returned, physical)
        self.assertLess(physical, proof)
        self.assertIn("pa_off_verified", body)
        self.assertIn("codec_muted_verified", body)
        self.assertIn("physical_driver_close_confirmed", self.responder_h)

    def test_no_result_or_post_start_control_path_is_added(self) -> None:
        finish = re.search(
            r"static esp_err_t finish_media\(.*?(?P<body>.*?)"
            r"\n}\n\nconst char \*call020_device_control_owner_version",
            self.source,
            re.S,
        )
        self.assertIsNotNone(finish)
        post_media = finish.group("body")
        for forbidden in (
            "serve_once(&s_owner.responder)",
            "usb_serial_jtag_write_bytes",
            "write_exact_and_drain",
            "reclaim_for_result",
            "RESULT_OWNED",
        ):
            self.assertNotIn(forbidden, post_media)
        self.assertIn("emitted_post_start_control = false", self.source)
        self.assertIn("result_phase_enabled = false", self.source)
        self.assertIn(".result_phase_enabled = false", self.boot)

    def test_no_authentication_or_product_claim_is_smuggled_in(self) -> None:
        combined = self.header + self.source + self.boot
        lowered = combined.lower()
        for forbidden in (
            "esp_log",
            "printf(",
            "fopen(",
            "socket(",
            "connect(",
            "mqtt",
            "http",
            "tls",
            "credential",
            "password",
        ):
            self.assertNotIn(forbidden, lowered)
        self.assertIn("not authentication", self.defaults)
        self.assertIn("raw_audio_logged_or_persisted = false", self.source)

    def test_actual_owner_c_failure_harnesses_compile_and_run_when_available(
        self,
    ) -> None:
        native_tools = _native_tools()
        cross_compiler = _cross_compiler()
        if native_tools is None and cross_compiler is None:
            self.skipTest("no native or ESP32-S3 C compiler for failure harness")
        responder_header = r"""
#pragma once
#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"

typedef enum {
    CALL020_DEVICE_CONTROL_DORMANT = 1,
    CALL020_DEVICE_CONTROL_OWNED,
    CALL020_DEVICE_CONTROL_MEDIA,
    CALL020_DEVICE_CONTROL_CLOSED,
    CALL020_DEVICE_CONTROL_TERMINAL,
} call020_device_control_state_t;
typedef enum {
    CALL020_DEVICE_CONTROL_TERMINAL_NONE = 0,
    CALL020_DEVICE_CONTROL_TERMINAL_LOCAL_CLEANUP = 10,
} call020_device_control_terminal_reason_t;
typedef enum {
    CALL020_DEVICE_CONTROL_SERVE_IDLE = 0,
    CALL020_DEVICE_CONTROL_SERVE_MEDIA_STARTED,
    CALL020_DEVICE_CONTROL_SERVE_CLOSE_COMPLETE,
    CALL020_DEVICE_CONTROL_SERVE_TERMINAL,
} call020_device_control_serve_result_t;
typedef struct {
    uint64_t max_runtime_us;
} call020_operator_runner_config_t;
typedef struct {
    bool enabled;
    uint32_t frame_wait_timeout_ms;
    uint32_t max_operation_timeout_ms;
    bool result_phase_enabled;
    call020_operator_runner_config_t runner;
} call020_device_control_responder_config_t;
typedef struct { uint64_t words[4]; } call020_device_control_responder_t;
typedef struct {
    call020_device_control_state_t state;
    call020_device_control_terminal_reason_t terminal_reason;
    esp_err_t first_error;
    bool lease_installed;
    bool media_started;
    bool media_workers_quiescent;
    bool media_output_safe_verified;
    bool media_runner_resources_closed;
    bool media_driver_lease_returned;
    bool physical_driver_close_confirmed;
    bool device_runtime_termination_proven;
} call020_device_control_responder_metadata_t;
typedef enum {
    CALL020_OPERATOR_DORMANT = 0,
    CALL020_OPERATOR_STOPPING,
    CALL020_OPERATOR_JOINED,
    CALL020_OPERATOR_TERMINAL,
    CALL020_OPERATOR_CLOSED,
} call020_operator_runner_state_t;
typedef enum {
    CALL020_WEARABLE_TERMINAL_NONE = 0,
    CALL020_WEARABLE_TERMINAL_RUNTIME,
} call020_wearable_terminal_reason_t;
typedef enum {
    CALL020_WEARABLE_RUNNING = 0,
    CALL020_WEARABLE_STOPPING,
    CALL020_WEARABLE_STOPPED,
    CALL020_WEARABLE_TERMINAL,
} call020_wearable_state_t;
typedef struct {
    call020_wearable_state_t state;
    uint32_t workers_created;
    uint32_t workers_finished;
    bool run_limit_reached;
    bool pa_off_verified;
    bool codec_muted_verified;
    call020_wearable_terminal_reason_t terminal_reason;
    esp_err_t first_error;
} fake_composition_metadata_t;
typedef struct {
    call020_operator_runner_state_t state;
    esp_err_t first_error;
    fake_composition_metadata_t composition;
} call020_operator_runner_metadata_t;

esp_err_t call020_device_control_responder_init(
    call020_device_control_responder_t *,
    const call020_device_control_responder_config_t *);
esp_err_t call020_device_control_responder_open_control(
    call020_device_control_responder_t *);
call020_device_control_serve_result_t
call020_device_control_responder_serve_once(
    call020_device_control_responder_t *);
esp_err_t call020_device_control_responder_abort_local(
    call020_device_control_responder_t *);
esp_err_t call020_device_control_responder_finish_media_local(
    call020_device_control_responder_t *);
esp_err_t call020_device_control_responder_get_metadata(
    const call020_device_control_responder_t *,
    call020_device_control_responder_metadata_t *);
esp_err_t call020_operator_runner_cancel(void);
esp_err_t call020_operator_runner_get_metadata(
    call020_operator_runner_metadata_t *);
"""
        stubs = {
            "call020_device_control_responder.h": responder_header,
            "esp_err.h": """
#pragma once
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL 0x101
#define ESP_ERR_NO_MEM 0x102
#define ESP_ERR_INVALID_ARG 0x103
#define ESP_ERR_INVALID_STATE 0x104
#define ESP_ERR_NOT_FOUND 0x105
#define ESP_ERR_NOT_SUPPORTED 0x106
#define ESP_ERR_TIMEOUT 0x107
""",
            "esp_timer.h": """
#pragma once
#include <stdint.h>
int64_t esp_timer_get_time(void);
""",
            "freertos/FreeRTOS.h": """
#pragma once
#include <stdint.h>
typedef uint32_t TickType_t;
#define configTICK_RATE_HZ 1000
#define pdMS_TO_TICKS(ms) ((TickType_t)(ms))
""",
            "freertos/portmacro.h": """
#pragma once
typedef int portMUX_TYPE;
#define portMUX_INITIALIZER_UNLOCKED 0
#define portENTER_CRITICAL(lock) ((void)(lock))
#define portEXIT_CRITICAL(lock) ((void)(lock))
""",
            "freertos/task.h": """
#pragma once
#include "freertos/FreeRTOS.h"
int xPortGetCoreID(void);
void vTaskDelay(TickType_t ticks);
void taskYIELD(void);
""",
            "sdkconfig.h": """
#pragma once
#define CONFIG_EGOLINK_CALL020_DEVICE_CONTROL_OWNER 1
#define CONFIG_EGOLINK_CALL020_DEVICE_CONTROL_RESPONDER 1
#define CONFIG_EGOLINK_CALL020_OPERATOR_RUNNER 1
#define CONFIG_ESP_CONSOLE_NONE 1
#define CONFIG_ESP_CONSOLE_SECONDARY_NONE 1
#define CONFIG_LOG_DEFAULT_LEVEL_NONE 1
#define CONFIG_BOOTLOADER_LOG_LEVEL_NONE 1
""",
        }
        scenarios = (
            (1, "ESP_ERR_TIMEOUT", 0),
            (2, "ESP_FAIL", 0),
            (3, "ESP_ERR_INVALID_STATE", 0),
            (4, "ESP_ERR_NOT_FOUND", 0),
            (4, "ESP_ERR_NOT_FOUND", 1),
            (4, "ESP_ERR_NOT_FOUND", 2),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            shutil.copy2(OWNER_C, temp / OWNER_C.name)
            shutil.copy2(OWNER_H, temp / OWNER_H.name)
            for relative, content in stubs.items():
                path = temp / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content.strip() + "\n", encoding="utf-8")
            harness = temp / "owner_recovery_harness.c"
            harness.write_text(OWNER_RECOVERY_HARNESS, encoding="utf-8")
            for stage, failure_code, boundary in scenarios:
                obj = temp / f"owner_recovery_{stage}_{boundary}.o"
                if native_tools is not None:
                    compiler = native_tools[0]
                    target_flags = ["--target=x86_64-pc-windows-msvc"]
                else:
                    compiler = cross_compiler
                    target_flags = []
                compile_result = subprocess.run(
                    [
                        str(compiler),
                        *target_flags,
                        "-std=c11",
                        "-ffreestanding",
                        "-fno-builtin",
                        "-fno-stack-protector",
                        "-Wall",
                        "-Wextra",
                        "-Werror",
                        "-I",
                        str(temp),
                        f"-DFAILURE_STAGE={stage}",
                        f"-DFAILURE_CODE={failure_code}",
                        f"-DPOST_SERVE_BOUNDARY={boundary}",
                        "-c",
                        str(harness),
                        "-o",
                        str(obj),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
                self.assertEqual(
                    0,
                    compile_result.returncode,
                    msg=compile_result.stdout + compile_result.stderr,
                )
                if native_tools is None:
                    continue
                executable = temp / f"owner_recovery_{stage}_{boundary}.exe"
                link_result = subprocess.run(
                    [
                        str(native_tools[1]),
                        "-flavor",
                        "link",
                        "/entry:mainCRTStartup",
                        "/subsystem:console",
                        "/nodefaultlib",
                        "/machine:x64",
                        f"/out:{executable}",
                        str(obj),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
                self.assertEqual(
                    0,
                    link_result.returncode,
                    msg=link_result.stdout + link_result.stderr,
                )
                executed = subprocess.run(
                    [str(executable)], capture_output=True, timeout=30, check=False
                )
                self.assertEqual(
                    0,
                    executed.returncode,
                    msg=(
                        f"cleanup failure stage {stage}, boundary {boundary} "
                        f"exited {executed.returncode}"
                    ),
                )


if __name__ == "__main__":
    unittest.main()

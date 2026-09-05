from __future__ import annotations

from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "firmware" / "audio_loop"
SOURCE = TARGET / "main" / "call020_usb_serial_jtag_endpoint.c"
HEADER = TARGET / "main" / "call020_usb_serial_jtag_endpoint.h"
APP_MAIN = TARGET / "main" / "app_main.c"
MAIN_CMAKE = TARGET / "main" / "CMakeLists.txt"
KCONFIG = TARGET / "main" / "Kconfig.projbuild"
DEDICATED_DEFAULTS = TARGET / "sdkconfig.call020_usb_endpoint.defaults"
README = TARGET / "README.md"
PACKET = ROOT / "docs" / "tasks" / "active" / "CALL-020_LTE_DATA_VOICE_POC.md"


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


LEASE_LIFECYCLE_HARNESS = r"""
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"

static bool fake_driver_installed;
static int fake_core_id;
static int64_t fake_now_us = 1000;
static esp_err_t fake_install_result = ESP_OK;
static esp_err_t fake_uninstall_result = ESP_OK;
static uint32_t fake_install_calls;
static uint32_t fake_uninstall_calls;

#define CALL020_USB_ENDPOINT_TEST_HOOKS 1
#include "call020_usb_serial_jtag_endpoint.c"

bool usb_serial_jtag_is_driver_installed(void) {
    return fake_driver_installed;
}

esp_err_t usb_serial_jtag_driver_install(
    const usb_serial_jtag_driver_config_t *config) {
    ++fake_install_calls;
    if (config == NULL || fake_install_result != ESP_OK) {
        return config == NULL ? ESP_ERR_INVALID_ARG : fake_install_result;
    }
    fake_driver_installed = true;
    return ESP_OK;
}

esp_err_t usb_serial_jtag_driver_uninstall(void) {
    ++fake_uninstall_calls;
    if (fake_uninstall_result != ESP_OK) {
        return fake_uninstall_result;
    }
    fake_driver_installed = false;
    return ESP_OK;
}

int usb_serial_jtag_read_bytes(void *buffer, size_t bytes, TickType_t wait) {
    (void)buffer;
    (void)bytes;
    (void)wait;
    return 0;
}

int usb_serial_jtag_write_bytes(
    const void *buffer, size_t bytes, TickType_t wait) {
    (void)buffer;
    (void)bytes;
    (void)wait;
    return 0;
}

esp_err_t usb_serial_jtag_wait_tx_done(TickType_t wait) {
    (void)wait;
    return ESP_OK;
}

int64_t esp_timer_get_time(void) {
    return fake_now_us++;
}

int xPortGetCoreID(void) {
    return fake_core_id;
}

void vTaskDelay(TickType_t ticks) {
    (void)ticks;
}

void taskYIELD(void) {
}

#define CHECK(condition, code) \
    do { if (!(condition)) return (code); } while (0)

static call020_usb_endpoint_config_t valid_config(void) {
    const call020_usb_endpoint_config_t config = {
        .tx_buffer_bytes = 256U,
        .rx_buffer_bytes = 256U,
        .io_wait_slice_ms = 5U,
        .max_operation_us = 100000U,
        .close_timeout_us = 100000U,
    };
    return config;
}

int mainCRTStartup(void) {
    const call020_usb_endpoint_config_t config = valid_config();
    call020_usb_endpoint_config_t mismatch = config;
    mismatch.tx_buffer_bytes = 512U;

    /* A failed install leaves neither a physical driver nor a registry owner. */
    call020_usb_driver_lease_t failed_install = {0};
    fake_install_result = ESP_FAIL;
    CHECK(call020_usb_driver_lease_install(&failed_install, &config) == ESP_FAIL, 10);
    CHECK(!failed_install.initialized, 11);
    CHECK(!fake_driver_installed, 12);
    CHECK(s_driver_owner_kind == DRIVER_OWNER_NONE, 13);
    CHECK(s_driver_owner_context == NULL, 14);
    fake_install_result = ESP_OK;

    /* Config mismatch poisons handoff closed, but the real owner can clean it. */
    call020_usb_driver_lease_t mismatch_lease = {0};
    call020_usb_serial_jtag_endpoint_t mismatch_endpoint = {0};
    CHECK(call020_usb_driver_lease_install(&mismatch_lease, &config) == ESP_OK, 20);
    CHECK(call020_usb_driver_lease_begin_media_handoff(&mismatch_lease) == ESP_OK, 21);
    CHECK(call020_usb_serial_jtag_endpoint_adopt_lease(
        &mismatch_endpoint, &mismatch, &mismatch_lease) == ESP_ERR_INVALID_STATE, 22);
    CHECK(mismatch_lease.state == CALL020_USB_DRIVER_LEASE_TERMINAL, 23);
    CHECK(mismatch_lease.terminal_reason == CALL020_USB_DRIVER_LEASE_TERMINAL_BINDING, 24);
    CHECK(fake_driver_installed, 25);
    uint32_t uninstalls_before = fake_uninstall_calls;
    fake_core_id = 1;
    CHECK(call020_usb_driver_lease_close(&mismatch_lease) == ESP_ERR_INVALID_STATE, 26);
    CHECK(fake_uninstall_calls == uninstalls_before, 27);
    CHECK(s_driver_owner_context == &mismatch_lease, 28);
    fake_core_id = 0;
    CHECK(call020_usb_driver_lease_close(&mismatch_lease) == ESP_OK, 29);
    CHECK(mismatch_lease.state == CALL020_USB_DRIVER_LEASE_CLOSED, 30);
    CHECK(mismatch_lease.metadata.uninstall_attempts == 1U, 31);
    CHECK(mismatch_lease.metadata.uninstall_successes == 1U, 32);
    CHECK(!fake_driver_installed && s_driver_owner_kind == DRIVER_OWNER_NONE, 33);

    call020_usb_driver_lease_t result_mismatch = {0};
    call020_usb_serial_jtag_endpoint_t result_mismatch_endpoint = {0};
    CHECK(call020_usb_driver_lease_install(&result_mismatch, &config) == ESP_OK, 130);
    CHECK(call020_usb_driver_lease_begin_media_handoff(&result_mismatch) == ESP_OK, 131);
    CHECK(call020_usb_serial_jtag_endpoint_adopt_lease(
        &result_mismatch_endpoint, &config, &result_mismatch) == ESP_OK, 132);
    CHECK(call020_usb_serial_jtag_endpoint_close(&result_mismatch_endpoint) == ESP_OK, 133);
    CHECK(result_mismatch.state == CALL020_USB_DRIVER_LEASE_MEDIA_RETURNED, 134);
    CHECK(call020_usb_driver_lease_reclaim_for_result(
        &result_mismatch, &mismatch) == ESP_ERR_INVALID_STATE, 135);
    CHECK(result_mismatch.state == CALL020_USB_DRIVER_LEASE_TERMINAL, 136);
    CHECK(result_mismatch.terminal_reason ==
        CALL020_USB_DRIVER_LEASE_TERMINAL_BINDING, 137);
    CHECK(fake_driver_installed && s_driver_owner_context == &result_mismatch, 138);
    CHECK(call020_usb_driver_lease_close(&result_mismatch) == ESP_OK, 139);
    CHECK(!fake_driver_installed && s_driver_owner_kind == DRIVER_OWNER_NONE, 140);

    call020_usb_driver_lease_t tampered = {0};
    call020_usb_serial_jtag_endpoint_t tampered_endpoint = {0};
    CHECK(call020_usb_driver_lease_install(&tampered, &config) == ESP_OK, 150);
    CHECK(call020_usb_driver_lease_begin_media_handoff(&tampered) == ESP_OK, 151);
    tampered.bound_config = mismatch;
    CHECK(call020_usb_serial_jtag_endpoint_adopt_lease(
        &tampered_endpoint, &mismatch, &tampered) == ESP_ERR_INVALID_STATE, 152);
    CHECK(tampered.state == CALL020_USB_DRIVER_LEASE_TERMINAL, 153);
    CHECK(fake_driver_installed && s_driver_owner_context == &tampered, 154);
    CHECK(call020_usb_driver_lease_close(&tampered) == ESP_OK, 155);
    CHECK(!fake_driver_installed && s_driver_owner_kind == DRIVER_OWNER_NONE, 156);

    /* Duplicate/wrong-core calls cannot steal or prematurely uninstall. */
    call020_usb_driver_lease_t lease = {0};
    call020_usb_serial_jtag_endpoint_t first = {0};
    call020_usb_serial_jtag_endpoint_t duplicate = {0};
    call020_usb_serial_jtag_endpoint_t wrong_core = {0};
    CHECK(call020_usb_driver_lease_install(&lease, &config) == ESP_OK, 40);
    const uint64_t generation = lease.generation;
    fake_core_id = 1;
    CHECK(call020_usb_driver_lease_begin_media_handoff(&lease) == ESP_ERR_INVALID_STATE, 41);
    CHECK(lease.state == CALL020_USB_DRIVER_LEASE_CONTROL_OWNED, 42);
    CHECK(s_driver_owner_context == &lease && fake_driver_installed, 43);
    fake_core_id = 0;
    CHECK(call020_usb_driver_lease_begin_media_handoff(&lease) == ESP_OK, 44);
    fake_core_id = 1;
    CHECK(call020_usb_serial_jtag_endpoint_adopt_lease(
        &wrong_core, &config, &lease) == ESP_ERR_INVALID_STATE, 45);
    CHECK(lease.state == CALL020_USB_DRIVER_LEASE_HANDOFF_READY, 46);
    fake_core_id = 0;
    call020_usb_driver_lease_t forged = lease;
    CHECK(call020_usb_serial_jtag_endpoint_adopt_lease(
        &duplicate, &config, &forged) == ESP_ERR_INVALID_STATE, 157);
    CHECK(forged.state == CALL020_USB_DRIVER_LEASE_TERMINAL &&
        forged.terminal_reason == CALL020_USB_DRIVER_LEASE_TERMINAL_REGISTRY &&
        forged.metadata.binding_rejections == 1U, 166);
    CHECK(lease.state == CALL020_USB_DRIVER_LEASE_HANDOFF_READY, 158);
    CHECK(s_driver_owner_context == &lease && fake_driver_installed, 159);
    CHECK(call020_usb_serial_jtag_endpoint_adopt_lease(
        &first, &config, &lease) == ESP_OK, 47);
    CHECK(lease.state == CALL020_USB_DRIVER_LEASE_MEDIA_BORROWED, 48);
    CHECK(call020_usb_serial_jtag_endpoint_adopt_lease(
        &duplicate, &config, &lease) == ESP_ERR_INVALID_STATE, 49);
    CHECK(lease.state == CALL020_USB_DRIVER_LEASE_MEDIA_BORROWED, 50);
    CHECK(lease.generation == generation && lease.metadata.media_adoptions == 1U, 51);
    uninstalls_before = fake_uninstall_calls;
    CHECK(call020_usb_driver_lease_close(&lease) == ESP_ERR_INVALID_STATE, 52);
    CHECK(fake_uninstall_calls == uninstalls_before && fake_driver_installed, 53);
    CHECK(s_driver_owner_context == &lease, 54);

    fake_core_id = 1;
    CHECK(call020_usb_serial_jtag_endpoint_close(&first) == ESP_ERR_INVALID_STATE, 55);
    CHECK(lease.state == CALL020_USB_DRIVER_LEASE_MEDIA_BORROWED, 56);
    CHECK(fake_uninstall_calls == uninstalls_before && s_driver_owner_context == &lease, 57);
    fake_core_id = 0;
    CHECK(call020_usb_serial_jtag_endpoint_close(&first) == ESP_OK, 58);
    CHECK(lease.state == CALL020_USB_DRIVER_LEASE_MEDIA_RETURNED, 59);
    CHECK(first.metadata.binding_closed && first.metadata.lease_returned, 60);
    CHECK(first.metadata.driver_installed, 61);
    CHECK(!first.metadata.driver_uninstalled_by_endpoint, 62);
    CHECK(fake_uninstall_calls == uninstalls_before && fake_driver_installed, 63);

    fake_core_id = 1;
    CHECK(call020_usb_driver_lease_reclaim_for_result(
        &lease, &config) == ESP_ERR_INVALID_STATE, 64);
    CHECK(lease.state == CALL020_USB_DRIVER_LEASE_MEDIA_RETURNED, 65);
    CHECK(fake_uninstall_calls == uninstalls_before && s_driver_owner_context == &lease, 66);
    fake_core_id = 0;
    CHECK(call020_usb_driver_lease_reclaim_for_result(
        &lease, &config) == ESP_OK, 67);
    CHECK(lease.state == CALL020_USB_DRIVER_LEASE_RESULT_OWNED, 68);
    CHECK(lease.metadata.result_reclaims == 1U, 69);
    CHECK(lease.metadata.media_binding_returned && lease.metadata.result_owned, 160);
    CHECK(call020_usb_driver_lease_reclaim_for_result(
        &lease, &config) == ESP_ERR_INVALID_STATE, 70);
    CHECK(lease.state == CALL020_USB_DRIVER_LEASE_RESULT_OWNED, 71);
    CHECK(call020_usb_serial_jtag_endpoint_adopt_lease(
        &duplicate, &config, &lease) == ESP_ERR_INVALID_STATE, 72);
    CHECK(lease.state == CALL020_USB_DRIVER_LEASE_RESULT_OWNED, 73);
    fake_core_id = 1;
    CHECK(call020_usb_driver_lease_close(&lease) == ESP_ERR_INVALID_STATE, 74);
    CHECK(lease.state == CALL020_USB_DRIVER_LEASE_RESULT_OWNED, 75);
    CHECK(fake_uninstall_calls == uninstalls_before && s_driver_owner_context == &lease, 76);
    fake_core_id = 0;
    fake_uninstall_result = ESP_FAIL;
    CHECK(call020_usb_driver_lease_close(&lease) == ESP_FAIL, 77);
    CHECK(lease.state == CALL020_USB_DRIVER_LEASE_TERMINAL, 78);
    CHECK(lease.metadata.driver_installed && fake_driver_installed, 79);
    CHECK(s_driver_owner_context == &lease, 80);
    CHECK(lease.metadata.uninstall_attempts == 1U &&
        lease.metadata.uninstall_successes == 0U, 81);
    fake_uninstall_result = ESP_OK;
    CHECK(call020_usb_driver_lease_close(&lease) == ESP_OK, 82);
    CHECK(lease.state == CALL020_USB_DRIVER_LEASE_CLOSED, 83);
    CHECK(!lease.metadata.driver_installed && !fake_driver_installed, 84);
    CHECK(lease.metadata.uninstall_attempts == 2U &&
        lease.metadata.uninstall_successes == 1U, 85);
    CHECK(s_driver_owner_kind == DRIVER_OWNER_NONE, 86);
    uninstalls_before = fake_uninstall_calls;
    CHECK(call020_usb_driver_lease_close(&lease) == ESP_OK, 161);
    CHECK(call020_usb_driver_lease_begin_media_handoff(
        &lease) == ESP_ERR_INVALID_STATE, 162);
    CHECK(call020_usb_driver_lease_reclaim_for_result(
        &lease, &config) == ESP_ERR_INVALID_STATE, 163);
    CHECK(lease.state == CALL020_USB_DRIVER_LEASE_CLOSED, 164);
    CHECK(fake_uninstall_calls == uninstalls_before, 165);

    /* Forced activation rollback failure retains exact recovery ownership. */
    call020_usb_driver_lease_t recovery = {0};
    fake_uninstall_result = ESP_FAIL;
    s_test_reject_next_owner_activation = true;
    CHECK(call020_usb_driver_lease_install(&recovery, &config) == ESP_FAIL, 90);
    CHECK(recovery.initialized && recovery.metadata.driver_installed, 91);
    CHECK(recovery.state == CALL020_USB_DRIVER_LEASE_TERMINAL, 92);
    CHECK(s_driver_owner_kind == DRIVER_OWNER_LEASE_INSTALLING, 93);
    CHECK(s_driver_owner_context == &recovery && fake_driver_installed, 94);
    CHECK(recovery.metadata.uninstall_attempts == 1U &&
        recovery.metadata.uninstall_successes == 0U, 95);
    fake_uninstall_result = ESP_OK;
    CHECK(call020_usb_driver_lease_close(&recovery) == ESP_OK, 96);
    CHECK(recovery.state == CALL020_USB_DRIVER_LEASE_CLOSED, 97);
    CHECK(recovery.metadata.uninstall_attempts == 2U &&
        recovery.metadata.uninstall_successes == 1U, 98);
    CHECK(!fake_driver_installed && s_driver_owner_kind == DRIVER_OWNER_NONE, 99);

    call020_usb_serial_jtag_endpoint_t endpoint_recovery = {0};
    fake_uninstall_result = ESP_FAIL;
    s_test_reject_next_owner_activation = true;
    CHECK(call020_usb_serial_jtag_endpoint_install(
        &endpoint_recovery, &config) == ESP_FAIL, 100);
    CHECK(endpoint_recovery.initialized && endpoint_recovery.driver_installed, 101);
    CHECK(endpoint_recovery.state == CALL020_USB_ENDPOINT_TERMINAL, 102);
    CHECK(s_driver_owner_kind == DRIVER_OWNER_ENDPOINT_INSTALLING, 103);
    CHECK(s_driver_owner_context == &endpoint_recovery, 104);
    fake_uninstall_result = ESP_OK;
    CHECK(call020_usb_serial_jtag_endpoint_close(&endpoint_recovery) == ESP_OK, 105);
    CHECK(endpoint_recovery.metadata.driver_uninstall_attempts == 2U, 106);
    CHECK(endpoint_recovery.metadata.driver_uninstall_successes == 1U, 107);
    CHECK(endpoint_recovery.metadata.driver_uninstalled_by_endpoint, 108);
    CHECK(!fake_driver_installed && s_driver_owner_kind == DRIVER_OWNER_NONE, 109);

    call020_usb_serial_jtag_endpoint_t missing_driver = {0};
    CHECK(call020_usb_serial_jtag_endpoint_install(&missing_driver, &config) == ESP_OK, 141);
    fake_driver_installed = false;
    CHECK(call020_usb_serial_jtag_endpoint_close(
        &missing_driver) == ESP_ERR_INVALID_STATE, 142);
    CHECK(missing_driver.state == CALL020_USB_ENDPOINT_TERMINAL, 143);
    CHECK(!missing_driver.metadata.driver_installed, 144);
    CHECK(missing_driver.metadata.binding_closed, 145);
    CHECK(!missing_driver.metadata.driver_uninstalled_by_endpoint, 146);
    CHECK(s_driver_owner_kind == DRIVER_OWNER_NONE &&
        s_driver_owner_context == NULL, 147);

    /* The legacy self-owned endpoint still installs and uninstalls itself. */
    call020_usb_serial_jtag_endpoint_t ordinary = {0};
    CHECK(call020_usb_serial_jtag_endpoint_install(&ordinary, &config) == ESP_OK, 110);
    uninstalls_before = fake_uninstall_calls;
    fake_core_id = 1;
    CHECK(call020_usb_serial_jtag_endpoint_close(&ordinary) == ESP_ERR_INVALID_STATE, 111);
    CHECK(fake_driver_installed && fake_uninstall_calls == uninstalls_before, 112);
    CHECK(s_driver_owner_context == &ordinary, 113);
    fake_core_id = 0;
    CHECK(call020_usb_serial_jtag_endpoint_close(&ordinary) == ESP_OK, 114);
    CHECK(ordinary.metadata.binding_closed, 115);
    CHECK(ordinary.metadata.driver_uninstalled_by_endpoint, 116);
    CHECK(!ordinary.metadata.driver_installed && !ordinary.metadata.lease_returned, 117);
    CHECK(!fake_driver_installed && s_driver_owner_kind == DRIVER_OWNER_NONE, 118);
    uninstalls_before = fake_uninstall_calls;
    CHECK(call020_usb_serial_jtag_endpoint_close(&ordinary) == ESP_OK, 119);
    CHECK(fake_uninstall_calls == uninstalls_before, 120);
    return 0;
}
"""


class Call020UsbSerialJtagEndpointStaticTests(unittest.TestCase):
    """Source/contract checks only; these tests never execute the C endpoint."""

    def test_static_wiring_is_default_disabled_and_uninstantiated(self) -> None:
        cmake = MAIN_CMAKE.read_text(encoding="utf-8")
        kconfig = KCONFIG.read_text(encoding="utf-8")
        app_main = APP_MAIN.read_text(encoding="utf-8")

        self.assertIn('"call020_usb_serial_jtag_endpoint.c"', cmake)
        self.assertIn("esp_driver_usb_serial_jtag", cmake)
        option = re.search(
            r"config EGOLINK_CALL020_USB_SERIAL_JTAG_ENDPOINT"
            r"(?P<body>.*?)\nendmenu",
            kconfig,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(option)
        self.assertIn("default n", option.group("body"))
        self.assertNotIn("call020_usb_serial_jtag_endpoint", app_main)
        self.assertNotIn("EGOLINK_CALL020_USB_SERIAL_JTAG_ENDPOINT", app_main)

    def test_dedicated_compile_profile_resolves_exclusive_owner_settings(self) -> None:
        defaults = DEDICATED_DEFAULTS.read_text(encoding="utf-8")

        for enabled in (
            "CONFIG_EGOLINK_CALL020_MEDIA_ADAPTER_CORE=y",
            "CONFIG_EGOLINK_CALL020_USB_SERIAL_JTAG_ENDPOINT=y",
            "CONFIG_ESP_CONSOLE_NONE=y",
            "CONFIG_ESP_CONSOLE_SECONDARY_NONE=y",
            "CONFIG_LOG_DEFAULT_LEVEL_NONE=y",
            "CONFIG_BOOTLOADER_LOG_LEVEL_NONE=y",
        ):
            self.assertIn(enabled, defaults)
        for disabled in (
            "# CONFIG_ESP_CONSOLE_USB_CDC is not set",
            "# CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG is not set",
            "# CONFIG_ESP_CONSOLE_SECONDARY_USB_SERIAL_JTAG is not set",
            "# CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG_ENABLED is not set",
            "# CONFIG_LOG_DEFAULT_LEVEL_INFO is not set",
            "# CONFIG_BOOTLOADER_LOG_LEVEL_INFO is not set",
        ):
            self.assertIn(disabled, defaults)
        self.assertIn("does not authorize flashing", defaults)

    def test_kconfig_and_source_require_exclusive_console_log_ownership(self) -> None:
        kconfig = KCONFIG.read_text(encoding="utf-8")
        source = SOURCE.read_text(encoding="utf-8")

        for dependency in (
            "depends on EGOLINK_CALL020_MEDIA_ADAPTER_CORE",
            "depends on ESP_CONSOLE_NONE",
            "depends on ESP_CONSOLE_SECONDARY_NONE",
            "depends on LOG_DEFAULT_LEVEL_NONE",
            "depends on BOOTLOADER_LOG_LEVEL_NONE",
        ):
            self.assertIn(dependency, kconfig)
        for guard in (
            'CALL-020E requires CONFIG_ESP_CONSOLE_NONE',
            'CALL-020E requires CONFIG_ESP_CONSOLE_SECONDARY_NONE',
            'CALL-020E requires CONFIG_LOG_DEFAULT_LEVEL_NONE',
            'CALL-020E requires CONFIG_BOOTLOADER_LOG_LEVEL_NONE',
        ):
            self.assertIn(guard, source)
        self.assertIn("usb_serial_jtag_is_driver_installed()", source)
        self.assertIn("return ESP_ERR_NOT_SUPPORTED", source)

    def test_api_is_caller_owned_and_all_sizes_and_timeouts_are_bounded(self) -> None:
        header = HEADER.read_text(encoding="utf-8")
        source = SOURCE.read_text(encoding="utf-8")

        for bound in (
            "CALL020_USB_ENDPOINT_MIN_DRIVER_BUFFER_BYTES UINT32_C(128)",
            "CALL020_USB_ENDPOINT_MAX_DRIVER_BUFFER_BYTES UINT32_C(16384)",
            "CALL020_USB_ENDPOINT_MAX_TRANSFER_BYTES",
            "CALL020_USB_ENDPOINT_MAX_IO_SLICE_MS UINT32_C(20)",
            "CALL020_USB_ENDPOINT_MAX_OPERATION_US UINT64_C(1000000)",
            "CALL020_USB_ENDPOINT_MAX_CLOSE_TIMEOUT_US UINT64_C(1000000)",
        ):
            self.assertIn(bound, header)
        self.assertIn("call020_usb_endpoint_config_t", header)
        self.assertIn("call020_usb_serial_jtag_endpoint_t *endpoint", header)
        self.assertIn(
            "requested_bytes > CALL020_USB_ENDPOINT_MAX_TRANSFER_BYTES", source
        )
        self.assertIn("absolute_deadline_us - *now_us > endpoint->max_operation_us", source)
        self.assertIn("remaining_us < slice_us ? remaining_us : slice_us", source)

    def test_driver_read_accumulates_one_exact_transfer_and_fails_partial(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")

        read = re.search(
            r"call020_usb_serial_jtag_endpoint_read_exact\((?P<body>.*?)"
            r"\n}\n\ncall020_usb_endpoint_transfer_result_t\n"
            r"call020_usb_serial_jtag_endpoint_write_exact",
            source,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(read)
        body = read.group("body")
        self.assertIn("while (transferred < requested_bytes)", body)
        self.assertIn("usb_serial_jtag_read_bytes", body)
        self.assertIn("classify_read_stop(endpoint, transferred, false)", body)
        self.assertIn("CALL020_USB_ENDPOINT_TERMINAL_RX_UNKNOWN", body)
        self.assertIn("secure_zero(destination, requested_bytes)", body)

    def test_driver_write_handles_all_progress_classes_without_blind_retry(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")

        write = re.search(
            r"call020_usb_serial_jtag_endpoint_write_exact\((?P<body>.*?)"
            r"\n}\n\ncall020_media_transfer_result_t\n"
            r"call020_usb_serial_jtag_endpoint_write_wire",
            source,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(write)
        body = write.group("body")
        self.assertIn("usb_serial_jtag_write_bytes", body)
        self.assertIn("accepted > 0 && (size_t)accepted < requested_bytes", body)
        self.assertIn("CALL020_USB_ENDPOINT_TRANSFER_TIMEOUT_PARTIAL", body)
        self.assertIn("usb_serial_jtag_wait_tx_done", body)
        self.assertIn("classify_write_unknown(endpoint, false)", body)
        self.assertIn("CALL020_USB_ENDPOINT_TRANSFER_TIMEOUT_ZERO_PROGRESS", body)

    def test_only_proven_zero_progress_timeout_maps_to_core_retryable_result(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")

        adapter = re.search(
            r"call020_usb_serial_jtag_endpoint_write_wire\((?P<body>.*?)"
            r"\n}\n\nesp_err_t call020_usb_serial_jtag_endpoint_request_cancel",
            source,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(adapter)
        body = adapter.group("body")
        zero = re.search(
            r"case CALL020_USB_ENDPOINT_TRANSFER_TIMEOUT_ZERO_PROGRESS:"
            r"(?P<body>.*?)case CALL020_USB_ENDPOINT_TRANSFER_TIMEOUT_PARTIAL:",
            body,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(zero)
        self.assertIn("CALL020_MEDIA_TRANSFER_TIMEOUT_ZERO_PROGRESS", zero.group("body"))
        self.assertIn("CALL020_MEDIA_TRANSFER_TIMEOUT_PARTIAL", body)
        self.assertIn("CALL020_MEDIA_TRANSFER_TIMEOUT_UNKNOWN", body)
        cancelled_zero = re.search(
            r"case CALL020_USB_ENDPOINT_TRANSFER_CANCELLED_ZERO_PROGRESS:"
            r"(?P<body>.*?)default:",
            body,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(cancelled_zero)
        self.assertIn(
            "CALL020_USB_ENDPOINT_TRANSFER_DRIVER_ERROR",
            cancelled_zero.group("body"),
        )
        self.assertIn("default:\n        return CALL020_MEDIA_TRANSFER_ERROR", body)

    def test_cancel_and_close_quiesce_before_same_core_uninstall(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        header = HEADER.read_text(encoding="utf-8")

        self.assertIn("Cancel is non-blocking", header)
        self.assertIn("active driver calls use at most io_wait_slice_ms", header.lower())
        close = re.search(
            r"esp_err_t call020_usb_serial_jtag_endpoint_close\((?P<body>.*?)"
            r"\n}\n\nesp_err_t call020_usb_serial_jtag_endpoint_get_metadata",
            source,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(close)
        body = close.group("body")
        self.assertLess(body.index("bool active"), body.index("usb_serial_jtag_driver_uninstall"))
        self.assertIn("now_us >= deadline_us", body)
        self.assertIn("CALL020_USB_ENDPOINT_TERMINAL_CLOSE_TIMEOUT", body)
        self.assertIn("xPortGetCoreID() != endpoint->install_core_id", body)
        self.assertIn("CALL020_USB_ENDPOINT_TERMINAL_WRONG_CORE", body)

    def test_driver_lease_is_registry_backed_config_bound_and_generation_scoped(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        header = HEADER.read_text(encoding="utf-8")

        for state in (
            "CALL020_USB_DRIVER_LEASE_CONTROL_OWNED",
            "CALL020_USB_DRIVER_LEASE_HANDOFF_READY",
            "CALL020_USB_DRIVER_LEASE_MEDIA_BORROWED",
            "CALL020_USB_DRIVER_LEASE_MEDIA_RETURNED",
            "CALL020_USB_DRIVER_LEASE_RESULT_OWNED",
            "CALL020_USB_DRIVER_LEASE_CLOSED",
        ):
            self.assertIn(state, header)
        self.assertIn("static void *s_driver_owner_context", source)
        self.assertIn("static uint64_t s_driver_owner_generation", source)
        self.assertIn(
            "static call020_usb_endpoint_config_t s_driver_owner_config", source
        )
        self.assertIn("static bool s_driver_owner_config_bound", source)
        self.assertIn("static uint64_t s_next_driver_generation", source)
        self.assertIn("s_driver_owner_context == lease", source)
        self.assertIn("s_driver_owner_generation == lease->generation", source)
        self.assertIn("config_equal(&s_driver_owner_config, config)", source)
        self.assertIn("lease->generation != 0U", source)
        self.assertIn("public fields are observability, not authority", header)

    def test_lease_handoff_is_irreversible_single_adoption_and_same_core(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")

        self.assertIn("call020_usb_driver_lease_begin_media_handoff", source)
        self.assertIn(
            "lease->state = CALL020_USB_DRIVER_LEASE_HANDOFF_READY",
            source,
        )
        self.assertIn(
            "lease->state = CALL020_USB_DRIVER_LEASE_MEDIA_BORROWED",
            source,
        )
        self.assertIn(
            "lease->state = CALL020_USB_DRIVER_LEASE_MEDIA_RETURNED",
            source,
        )
        self.assertIn("lease->metadata.media_adoptions++", source)
        self.assertIn("lease->metadata.media_returns++", source)
        self.assertIn("lease->metadata.wrong_core_rejections++", source)
        self.assertIn(
            "lease->state != CALL020_USB_DRIVER_LEASE_MEDIA_BORROWED",
            source,
        )
        self.assertIn("The first endpoint remains the only media owner", source)

    def test_result_reclaim_is_registry_config_generation_and_core_bound(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        header = HEADER.read_text(encoding="utf-8")

        self.assertIn("call020_usb_driver_lease_reclaim_for_result", header)
        reclaim = re.search(
            r"call020_usb_driver_lease_reclaim_for_result\((?P<body>.*?)"
            r"\n}\n\nesp_err_t call020_usb_driver_lease_close",
            source,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(reclaim)
        body = reclaim.group("body")
        self.assertIn("xPortGetCoreID() != lease->owner_core_id", body)
        self.assertIn("s_driver_owner_context == lease", body)
        self.assertIn("s_driver_owner_generation == lease->generation", body)
        self.assertIn("config_equal(&s_driver_owner_config, config)", body)
        self.assertIn("CALL020_USB_DRIVER_LEASE_MEDIA_RETURNED", body)
        self.assertIn("CALL020_USB_DRIVER_LEASE_RESULT_OWNED", body)
        self.assertIn("lease->metadata.result_reclaims++", body)
        self.assertIn("Never poison an active MEDIA or RESULT owner", body)
        self.assertIn("media_binding_returned", header)
        self.assertIn("result_owned", header)

    def test_activation_uninstall_and_missing_driver_paths_retain_truthful_ownership(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")

        self.assertIn("DRIVER_OWNER_LEASE_INSTALLING &&", source)
        self.assertIn("DRIVER_OWNER_ENDPOINT_INSTALLING &&", source)
        self.assertIn("s_test_reject_next_owner_activation", source)
        self.assertIn("lease->metadata.uninstall_attempts++", source)
        self.assertIn("lease->metadata.uninstall_successes++", source)
        self.assertIn("lease->state = CALL020_USB_DRIVER_LEASE_TERMINAL", source)
        self.assertIn("endpoint->metadata.driver_uninstall_attempts++", source)
        self.assertIn("endpoint->metadata.driver_uninstall_successes++", source)
        self.assertIn("release_self_owned_endpoint_registry(endpoint)", source)
        self.assertIn("endpoint->binding_closed = binding_released", source)
        self.assertIn("endpoint->driver_uninstalled_by_endpoint = true", source)

    def test_borrowed_endpoint_returns_lease_without_install_or_uninstall(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")

        adopt = re.search(
            r"call020_usb_serial_jtag_endpoint_adopt_lease\((?P<body>.*?)"
            r"\n}\n\ncall020_usb_endpoint_transfer_result_t",
            source,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(adopt)
        self.assertIn("claim_lease_for_media", adopt.group("body"))
        self.assertNotIn("usb_serial_jtag_driver_install", adopt.group("body"))
        self.assertNotIn("usb_serial_jtag_driver_uninstall", adopt.group("body"))

        close = re.search(
            r"esp_err_t call020_usb_serial_jtag_endpoint_close\((?P<body>.*?)"
            r"\n}\n\nesp_err_t call020_usb_serial_jtag_endpoint_get_metadata",
            source,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(close)
        normal_close = close.group("body")[
            close.group("body").index("endpoint->metadata.driver_uninstall_attempts++") :
        ]
        borrowed = re.search(
            r"CALL020_USB_ENDPOINT_DRIVER_LEASE_BORROWED\) \{(?P<body>.*?)"
            r"\n    } else \{",
            normal_close,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(borrowed)
        self.assertIn("return_lease_from_media(endpoint)", borrowed.group("body"))
        self.assertNotIn("usb_serial_jtag_driver_uninstall", borrowed.group("body"))
        self.assertIn("endpoint->lease_returned = true", source)

    def test_only_lease_owner_can_uninstall_after_media_return(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")

        lease_close = re.search(
            r"call020_usb_driver_lease_close\((?P<body>.*?)"
            r"\n}\n\nesp_err_t call020_usb_driver_lease_get_metadata",
            source,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(lease_close)
        body = lease_close.group("body")
        self.assertIn("CALL020_USB_DRIVER_LEASE_MEDIA_RETURNED", body)
        self.assertNotIn("CALL020_USB_DRIVER_LEASE_MEDIA_BORROWED ||", body)
        self.assertIn("usb_serial_jtag_driver_uninstall()", body)
        self.assertLess(
            body.index("usb_serial_jtag_driver_uninstall()"),
            body.rindex("CALL020_USB_DRIVER_LEASE_CLOSED"),
        )

    def test_mocked_c_driver_lease_lifecycle_and_failure_recovery(self) -> None:
        """Compile, and when available execute, the C owner against IDF fakes."""
        tools = _native_tools()
        with tempfile.TemporaryDirectory(prefix="egolink-call020o-native-") as temp:
            temp_path = Path(temp)
            (temp_path / "driver").mkdir()
            (temp_path / "freertos").mkdir()
            (temp_path / SOURCE.name).write_text(
                SOURCE.read_text(encoding="utf-8"), encoding="utf-8"
            )
            (temp_path / HEADER.name).write_text(
                HEADER.read_text(encoding="utf-8"), encoding="utf-8"
            )
            stubs = {
                "esp_err.h": """
#pragma once
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL (-1)
#define ESP_ERR_INVALID_ARG 0x102
#define ESP_ERR_INVALID_STATE 0x103
#define ESP_ERR_INVALID_SIZE 0x104
#define ESP_ERR_NOT_SUPPORTED 0x106
#define ESP_ERR_TIMEOUT 0x107
""",
                "call020_media_adapter_core.h": """
#pragma once
#include <stdint.h>
#define CALL020_MEDIA_WIRE_MAX_BYTES UINT32_C(1190)
typedef enum {
    CALL020_MEDIA_TRANSFER_OK = 0,
    CALL020_MEDIA_TRANSFER_TIMEOUT_ZERO_PROGRESS,
    CALL020_MEDIA_TRANSFER_TIMEOUT_PARTIAL,
    CALL020_MEDIA_TRANSFER_TIMEOUT_UNKNOWN,
    CALL020_MEDIA_TRANSFER_ERROR,
} call020_media_transfer_result_t;
""",
                "freertos/FreeRTOS.h": """
#pragma once
#include <stdint.h>
typedef uint32_t TickType_t;
#define configTICK_RATE_HZ 1000
#define portMAX_DELAY UINT32_MAX
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
                "driver/usb_serial_jtag.h": """
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include "esp_err.h"
#include "freertos/FreeRTOS.h"
typedef struct {
    size_t tx_buffer_size;
    size_t rx_buffer_size;
} usb_serial_jtag_driver_config_t;
bool usb_serial_jtag_is_driver_installed(void);
esp_err_t usb_serial_jtag_driver_install(
    const usb_serial_jtag_driver_config_t *config);
esp_err_t usb_serial_jtag_driver_uninstall(void);
int usb_serial_jtag_read_bytes(void *buffer, size_t bytes, TickType_t wait);
int usb_serial_jtag_write_bytes(
    const void *buffer, size_t bytes, TickType_t wait);
esp_err_t usb_serial_jtag_wait_tx_done(TickType_t wait);
""",
                "esp_timer.h": """
#pragma once
#include <stdint.h>
int64_t esp_timer_get_time(void);
""",
                "sdkconfig.h": """
#pragma once
#define CONFIG_EGOLINK_CALL020_USB_SERIAL_JTAG_ENDPOINT 1
#define CONFIG_EGOLINK_CALL020_MEDIA_ADAPTER_CORE 1
#define CONFIG_ESP_CONSOLE_NONE 1
#define CONFIG_ESP_CONSOLE_SECONDARY_NONE 1
#define CONFIG_LOG_DEFAULT_LEVEL_NONE 1
#define CONFIG_BOOTLOADER_LOG_LEVEL_NONE 1
""",
            }
            for relative, text in stubs.items():
                path = temp_path / relative
                path.write_text(text.strip() + "\n", encoding="utf-8")
            harness = temp_path / "lease_lifecycle_harness.c"
            harness.write_text(LEASE_LIFECYCLE_HARNESS, encoding="utf-8")
            if tools is None:
                compiler = Path(
                    "C:/Espressif/tools/xtensa-esp-elf/"
                    "esp-14.2.0_20241119/xtensa-esp-elf/bin/"
                    "xtensa-esp32s3-elf-gcc.exe"
                )
                if not compiler.is_file():
                    self.skipTest("no C compiler is available for the fake harness")
                cross_object = temp_path / "lease_lifecycle_harness.xtensa.o"
                cross_compiled = subprocess.run(
                    [
                        str(compiler),
                        "-std=c11",
                        "-ffreestanding",
                        "-Wall",
                        "-Wextra",
                        "-Werror",
                        "-I",
                        str(temp_path),
                        "-c",
                        str(harness),
                        "-o",
                        str(cross_object),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
                self.assertEqual(
                    0,
                    cross_compiled.returncode,
                    msg=cross_compiled.stdout + cross_compiled.stderr,
                )
                self.skipTest(
                    "mocked lifecycle cross-compiled; no executable host C target"
                )
            clang, linker = tools
            obj = temp_path / "lease_lifecycle_harness.obj"
            compiled = subprocess.run(
                [
                    str(clang),
                    "--target=x86_64-pc-windows-msvc",
                    "-std=c11",
                    "-ffreestanding",
                    "-fno-builtin",
                    "-fno-stack-protector",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-I",
                    str(temp_path),
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
                0, compiled.returncode, msg=compiled.stdout + compiled.stderr
            )
            executable = temp_path / "lease_lifecycle_harness.exe"
            linked = subprocess.run(
                [
                    str(linker),
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
            self.assertEqual(0, linked.returncode, msg=linked.stdout + linked.stderr)
            executed = subprocess.run(
                [str(executable)], capture_output=True, timeout=30, check=False
            )
            self.assertEqual(
                0,
                executed.returncode,
                msg=f"mocked C lease lifecycle failed at code {executed.returncode}",
            )

    def test_read_and_write_directions_have_independent_single_operation_guards(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        header = HEADER.read_text(encoding="utf-8")

        self.assertIn("bool read_active", header)
        self.assertIn("bool write_active", header)
        self.assertIn("direction == OPERATION_READ", source)
        self.assertIn("? &endpoint->read_active", source)
        self.assertIn(": &endpoint->write_active", source)
        self.assertIn("!endpoint->cancel_requested && !*active", source)

    def test_endpoint_has_no_media_log_persistence_or_hardware_side_effect_scope(self) -> None:
        source = SOURCE.read_text(encoding="utf-8").lower()
        header = HEADER.read_text(encoding="utf-8").lower()

        for forbidden in (
            "esp_log",
            "printf(",
            "fopen(",
            "fwrite(",
            "nvs_",
            "littlefs",
            "spiffs",
            "socket(",
            "http",
            "mqtt",
            "i2s_",
            "esp_codec",
            "gpio_",
        ):
            self.assertNotIn(forbidden, source)
        self.assertNotRegex(source, r"\bvoid\s+app_main\s*\(")
        self.assertNotRegex(header, r"uint8_t\s+[^;]*\[")
        self.assertIn("stores and reports only state/counters", PACKET.read_text(encoding="utf-8"))

    def test_docs_state_compile_only_boundary_and_remaining_hardware_prerequisites(self) -> None:
        readme = README.read_text(encoding="utf-8")
        packet = PACKET.read_text(encoding="utf-8")

        for statement in (
            "source and compile evidence only",
            "No endpoint instance has run",
            "exact enclosure connector/USB controller path",
            "final driver\nuninstall API itself has no timeout parameter",
        ):
            self.assertIn(statement, readme)
        self.assertIn("temporarily sacrifices the operator console", packet)
        self.assertIn("No device, USB, serial,\naudio, modem or network action", packet)
        self.assertIn("`P0-CALL` evidence", packet)


if __name__ == "__main__":
    unittest.main()

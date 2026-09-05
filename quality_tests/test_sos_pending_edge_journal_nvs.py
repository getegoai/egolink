"""Focused SOS-010H build-only NVS pending-edge adapter checks.

The actual adapter and a fake-NVS fault harness are cross-compiled for
ESP32-S3. The harness runs only when a native compiler is available. No test
opens real NVS, flashes a device, or supplies power-loss/hardware evidence.
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
COMPONENT = COMPONENTS / "sos_pending_edge_journal_nvs"
HEADER = COMPONENT / "include" / "sos_pending_edge_journal_nvs.h"
SOURCE = COMPONENT / "sos_pending_edge_journal_nvs.c"
CMAKE = COMPONENT / "CMakeLists.txt"
JOURNAL_HEADER = (
    COMPONENTS / "sos_pending_edge_journal" / "include" /
    "sos_pending_edge_journal.h"
)
PACKET = ROOT / "docs" / "tasks" / "active" / "SOS-010_SOS_WALKING_SKELETON.md"
APP_MAIN = ROOT / "firmware" / "mqtt_heartbeat" / "main" / "app_main.c"


def _esp_compiler() -> Path | None:
    candidates = (
        shutil.which("xtensa-esp32s3-elf-gcc"),
        Path(
            "C:/Espressif/tools/xtensa-esp-elf/esp-14.2.0_20241119/"
            "xtensa-esp-elf/bin/xtensa-esp32s3-elf-gcc.exe"
        ),
    )
    return next(
        (Path(item) for item in candidates if item and Path(item).is_file()),
        None,
    )


def _native_compiler() -> Path | None:
    for candidate in (
        os.environ.get("CC"),
        shutil.which("gcc"),
        shutil.which("clang"),
        "C:/Program Files/LLVM/bin/clang.exe",
    ):
        if not candidate:
            continue
        resolved = Path(shutil.which(str(candidate)) or str(candidate))
        name = resolved.name.casefold()
        if (
            resolved.is_file()
            and ("gcc" in name or "clang" in name)
            and "xtensa" not in name
            and "riscv" not in name
        ):
            return resolved
    return None


def _fake_nvs_header() -> str:
    return textwrap.dedent(
        r"""
        #ifndef TEST_FAKE_NVS_H
        #define TEST_FAKE_NVS_H
        #include <stddef.h>
        #include <stdint.h>
        typedef int32_t esp_err_t;
        typedef uint32_t nvs_handle_t;
        typedef enum { NVS_READONLY = 0, NVS_READWRITE = 1 } nvs_open_mode_t;
        #define ESP_OK INT32_C(0)
        #define ESP_FAIL INT32_C(-1)
        #define ESP_ERR_NVS_NOT_FOUND INT32_C(0x1102)
        #define ESP_ERR_NVS_INVALID_LENGTH INT32_C(0x110c)
        #define NVS_PART_NAME_MAX_SIZE 16U
        #define NVS_KEY_NAME_MAX_SIZE 16U
        #define NVS_NS_NAME_MAX_SIZE NVS_KEY_NAME_MAX_SIZE
        esp_err_t nvs_open_from_partition(
            const char *, const char *, nvs_open_mode_t, nvs_handle_t *);
        esp_err_t nvs_get_blob(nvs_handle_t, const char *, void *, size_t *);
        esp_err_t nvs_set_blob(
            nvs_handle_t, const char *, const void *, size_t);
        esp_err_t nvs_erase_key(nvs_handle_t, const char *);
        esp_err_t nvs_commit(nvs_handle_t);
        void nvs_close(nvs_handle_t);
        #endif
        """
    )


def _fault_harness() -> str:
    return textwrap.dedent(
        r"""
        #include "sos_pending_edge_journal_nvs.h"

        #include <stdbool.h>
        #include <stddef.h>
        #include <stdint.h>
        #include <string.h>

        #include "nvs.h"

        #define REQUIRE(condition) do { if (!(condition)) { return __LINE__; } } while (0)

        static bool namespace_exists;
        static bool key_exists;
        static bool commit_fails;
        static uint8_t blob[EGOLINK_SOS_PENDING_EDGE_RECORD_BYTES];
        static size_t blob_length;
        static uint64_t open_count;
        static uint64_t close_count;

        esp_err_t nvs_open_from_partition(
            const char *partition,
            const char *name_space,
            nvs_open_mode_t mode,
            nvs_handle_t *handle)
        {
            if (partition == NULL || name_space == NULL || handle == NULL ||
                strcmp(partition, "nvs") != 0 ||
                strcmp(name_space, "ego_sos_pend") != 0) {
                return ESP_FAIL;
            }
            if (mode == NVS_READONLY && !namespace_exists) {
                return ESP_ERR_NVS_NOT_FOUND;
            }
            if (mode == NVS_READWRITE) {
                namespace_exists = true;
            }
            *handle = UINT32_C(7);
            ++open_count;
            return ESP_OK;
        }

        esp_err_t nvs_get_blob(
            nvs_handle_t handle,
            const char *key,
            void *output,
            size_t *length)
        {
            if (handle != UINT32_C(7) || key == NULL || length == NULL ||
                strcmp(key, "edge_v1") != 0) {
                return ESP_FAIL;
            }
            if (!key_exists) {
                return ESP_ERR_NVS_NOT_FOUND;
            }
            if (output == NULL) {
                *length = blob_length;
                return ESP_OK;
            }
            if (*length < blob_length) {
                *length = blob_length;
                return ESP_ERR_NVS_INVALID_LENGTH;
            }
            (void)memcpy(output, blob, blob_length);
            *length = blob_length;
            return ESP_OK;
        }

        esp_err_t nvs_set_blob(
            nvs_handle_t handle,
            const char *key,
            const void *input,
            size_t length)
        {
            if (handle != UINT32_C(7) || key == NULL || input == NULL ||
                strcmp(key, "edge_v1") != 0 || length > sizeof(blob)) {
                return ESP_FAIL;
            }
            (void)memcpy(blob, input, length);
            blob_length = length;
            key_exists = true;
            return ESP_OK;
        }

        esp_err_t nvs_erase_key(nvs_handle_t handle, const char *key)
        {
            if (handle != UINT32_C(7) || key == NULL ||
                strcmp(key, "edge_v1") != 0) {
                return ESP_FAIL;
            }
            if (!key_exists) {
                return ESP_ERR_NVS_NOT_FOUND;
            }
            key_exists = false;
            blob_length = 0U;
            return ESP_OK;
        }

        esp_err_t nvs_commit(nvs_handle_t handle)
        {
            return handle == UINT32_C(7) && !commit_fails
                ? ESP_OK
                : ESP_FAIL;
        }

        void nvs_close(nvs_handle_t handle)
        {
            if (handle == UINT32_C(7)) {
                ++close_count;
            }
        }

        int main(void)
        {
            egolink_sos_pending_edge_nvs_t adapter;
            egolink_sos_pending_edge_storage_t storage;
            egolink_sos_pending_edge_nvs_metrics_t metrics;
            uint8_t input[EGOLINK_SOS_PENDING_EDGE_RECORD_BYTES];
            uint8_t output[EGOLINK_SOS_PENDING_EDGE_RECORD_BYTES];
            size_t actual = 99U;
            for (size_t index = 0U; index < sizeof(input); ++index) {
                input[index] = (uint8_t)index;
            }

            REQUIRE(egolink_sos_pending_edge_nvs_init(&adapter, &storage) ==
                EGOLINK_SOS_PENDING_EDGE_NVS_OK);
            REQUIRE(open_count == 0U && close_count == 0U);
            REQUIRE(storage.load_record(
                storage.context, output, sizeof(output), &actual) ==
                EGOLINK_SOS_PENDING_EDGE_STORAGE_NOT_FOUND);
            REQUIRE(actual == 0U && !namespace_exists);
            REQUIRE(storage.clear_record(storage.context) ==
                EGOLINK_SOS_PENDING_EDGE_STORAGE_NOT_FOUND);
            REQUIRE(!namespace_exists);
            REQUIRE(storage.store_record(
                storage.context, input, sizeof(input) - 1U) ==
                EGOLINK_SOS_PENDING_EDGE_STORAGE_IO_ERROR);
            REQUIRE(!namespace_exists);

            commit_fails = true;
            REQUIRE(storage.store_record(
                storage.context, input, sizeof(input)) ==
                EGOLINK_SOS_PENDING_EDGE_STORAGE_IO_ERROR);
            REQUIRE(namespace_exists && key_exists);
            commit_fails = false;
            REQUIRE(storage.load_record(
                storage.context, output, sizeof(output), &actual) ==
                EGOLINK_SOS_PENDING_EDGE_STORAGE_OK);
            REQUIRE(actual == sizeof(output));
            REQUIRE(memcmp(input, output, sizeof(input)) == 0);

            blob_length = 12U;
            REQUIRE(storage.load_record(
                storage.context, output, sizeof(output), &actual) ==
                EGOLINK_SOS_PENDING_EDGE_STORAGE_IO_ERROR);
            REQUIRE(storage.clear_record(storage.context) ==
                EGOLINK_SOS_PENDING_EDGE_STORAGE_IO_ERROR);
            blob_length = sizeof(blob);

            commit_fails = true;
            REQUIRE(storage.clear_record(storage.context) ==
                EGOLINK_SOS_PENDING_EDGE_STORAGE_IO_ERROR);
            REQUIRE(!key_exists);
            commit_fails = false;
            REQUIRE(storage.load_record(
                storage.context, output, sizeof(output), &actual) ==
                EGOLINK_SOS_PENDING_EDGE_STORAGE_NOT_FOUND);
            REQUIRE(open_count == close_count);
            REQUIRE(egolink_sos_pending_edge_nvs_get_metrics(
                &adapter, &metrics) == EGOLINK_SOS_PENDING_EDGE_NVS_OK);
            REQUIRE(metrics.handles_opened == metrics.handles_closed);
            REQUIRE(metrics.size_mismatches == 3U);
            REQUIRE(metrics.blob_read_success_bytes == sizeof(blob));
            REQUIRE(metrics.blob_set_success_bytes == sizeof(blob));
            return 0;
        }
        """
    )


class SosPendingEdgeJournalNvsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.header = HEADER.read_text(encoding="utf-8")
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.cmake = CMAKE.read_text(encoding="utf-8")
        cls.packet = PACKET.read_text(encoding="utf-8")
        cls.app_main = APP_MAIN.read_text(encoding="utf-8")

    def test_fixed_partition_namespace_key_and_exact_wire_size(self) -> None:
        self.assertIn('NVS_PARTITION_LABEL "nvs"', self.header)
        self.assertIn('NVS_NAMESPACE "ego_sos_pend"', self.header)
        self.assertIn('NVS_KEY "edge_v1"', self.header)
        self.assertIn("EGOLINK_SOS_PENDING_EDGE_RECORD_BYTES == 320U", self.source)
        self.assertIn("source_length != EGOLINK_SOS_PENDING_EDGE_RECORD_BYTES", self.source)
        self.assertIn("required_length != EGOLINK_SOS_PENDING_EDGE_RECORD_BYTES", self.source)
        self.assertIn(
            "EGOLINK_SOS_PENDING_EDGE_RECORD_BYTES 320U",
            JOURNAL_HEADER.read_text(encoding="utf-8"),
        )

    def test_init_is_ram_only_and_default_app_remains_unwired(self) -> None:
        start = self.source.index("egolink_sos_pending_edge_nvs_init(")
        end = self.source.index("egolink_sos_pending_edge_nvs_is_initialized(")
        init = self.source[start:end]
        self.assertNotRegex(init, r"\bnvs_[a-z_]+\s*\(")
        self.assertNotIn("sos_pending_edge_journal_nvs", self.app_main)
        self.assertNotIn("egolink_sos_pending_edge_nvs_", self.app_main)
        combined = self.source.casefold()
        for forbidden in (
            "nvs_flash_init",
            "nvs_flash_erase",
            "esp_restart",
            "app_main",
            "esp_log",
            "malloc(",
            "calloc(",
            "realloc(",
            "free(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, combined)

    def test_load_is_read_only_and_maps_missing_namespace_or_key(self) -> None:
        load = self.source[
            self.source.index("static egolink_sos_pending_edge_storage_result_t load_record(") :
            self.source.index("static egolink_sos_pending_edge_storage_result_t store_record(")
        ]
        self.assertIn("NVS_READONLY", load)
        self.assertNotIn("NVS_READWRITE", load)
        self.assertIn("if (error == ESP_ERR_NVS_NOT_FOUND)", load)
        self.assertIn("EGOLINK_SOS_PENDING_EDGE_STORAGE_NOT_FOUND", load)
        self.assertLess(
            load.index("NULL,\n        &required_length"),
            load.index("destination,\n        &read_length"),
        )
        self.assertIn("close_handle(internal, handle)", load)

    def test_store_is_only_namespace_creator_and_commits_after_exact_set(self) -> None:
        store = self.source[
            self.source.index("static egolink_sos_pending_edge_storage_result_t store_record(") :
            self.source.index("static egolink_sos_pending_edge_storage_result_t clear_record(")
        ]
        self.assertIn("NVS_READWRITE", store)
        self.assertLess(store.index("nvs_set_blob("), store.index("nvs_commit("))
        self.assertLess(store.index("nvs_commit("), store.rindex("close_handle("))
        self.assertIn("store_commit_successes", store)
        self.assertEqual(2, self.source.count("NVS_READWRITE"))

    def test_clear_readonly_preflight_prevents_empty_namespace_creation(self) -> None:
        clear = self.source[
            self.source.index("static egolink_sos_pending_edge_storage_result_t clear_record(") :
            self.source.index(
                "egolink_sos_pending_edge_nvs_status_t\n"
                "egolink_sos_pending_edge_nvs_init("
            )
        ]
        self.assertLess(clear.index("NVS_READONLY"), clear.index("NVS_READWRITE"))
        self.assertLess(clear.index("nvs_get_blob("), clear.index("nvs_erase_key("))
        self.assertLess(clear.index("nvs_erase_key("), clear.index("nvs_commit("))
        self.assertIn("avoids creating an empty namespace", clear)
        self.assertEqual(4, clear.count("close_handle(internal, handle)"))

    def test_metrics_are_ram_only_saturating_and_payload_free(self) -> None:
        for field in (
            "handles_opened",
            "handles_closed",
            "blob_read_success_bytes",
            "blob_set_success_bytes",
            "size_mismatches",
            "store_commit_successes",
            "clear_commit_successes",
        ):
            self.assertIn(field, self.header)
        normalized = " ".join(self.header.replace("*", " ").split()).lower()
        self.assertIn("ram-only saturating diagnostic counters", normalized)
        self.assertIn("contain no payload or identity", normalized)
        self.assertIn("not persistent lifetime/endurance evidence", normalized)
        self.assertIn("if (*value != UINT64_MAX)", self.source)
        self.assertIn("UINT64_MAX - *value < amount", self.source)

    def test_nvs_ownership_single_owner_and_nonclaims_are_explicit(self) -> None:
        normalized = " ".join((self.header + self.packet).replace("*", " ").split()).lower()
        for phrase in (
            "does not open, initialize, erase, format or otherwise access nvs",
            "only store may create namespace",
            "every successful nvs open is closed",
            "one external owner task or mutex must serialize",
            "does not claim brownout atomicity",
            "flash endurance",
            "flash encryption",
            "secure erase",
        ):
            self.assertIn(phrase, normalized)
        self.assertIn("REQUIRES sos_pending_edge_journal nvs_flash", self.cmake)
        for flag in ("-Wall", "-Wextra", "-Werror", "-Wconversion", "-Wshadow"):
            self.assertIn(flag, self.cmake)

    def _compile_harness(self, compiler: Path, output: Path, temp: Path) -> None:
        fake_header = temp / "nvs.h"
        harness = temp / "nvs_backend_harness.c"
        fake_header.write_text(_fake_nvs_header(), encoding="utf-8")
        harness.write_text(_fault_harness(), encoding="utf-8")
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
                f"-I{temp}",
                f"-I{COMPONENT / 'include'}",
                f"-I{COMPONENTS / 'sos_pending_edge_journal' / 'include'}",
                f"-I{COMPONENTS / 'persistent_priority_outbox' / 'include'}",
                str(SOURCE),
                str(harness),
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

    def test_actual_adapter_and_fault_harness_cross_compile_for_esp32s3(self) -> None:
        compiler = _esp_compiler()
        if compiler is None:
            self.skipTest("ESP32-S3 cross compiler unavailable")
        with tempfile.TemporaryDirectory(prefix="egolink-sos-nvs-cross-") as raw:
            temp = Path(raw)
            self._compile_harness(compiler, temp / "nvs_backend.elf", temp)

    def test_actual_adapter_fault_harness_runs_with_native_compiler(self) -> None:
        compiler = _native_compiler()
        if compiler is None:
            self.skipTest("native host GCC/Clang unavailable")
        with tempfile.TemporaryDirectory(prefix="egolink-sos-nvs-native-") as raw:
            temp = Path(raw)
            executable = temp / "nvs_backend.exe"
            self._compile_harness(compiler, executable, temp)
            completed = subprocess.run(
                [str(executable)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)


if __name__ == "__main__":
    unittest.main()

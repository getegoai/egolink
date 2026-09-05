"""Source/static guards for CALL-020G.

These tests inspect source and build wiring only. They do not compile or run C,
start a FreeRTOS task, or open GPIO, codec, I2S, USB, modem, or network I/O.
Actual compile/link evidence is produced by separate ESP-IDF builds.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "firmware/audio_loop/main/call020_operator_runner.c"
HEADER = ROOT / "firmware/audio_loop/main/call020_operator_runner.h"
COMPOSITION_SOURCE = ROOT / "firmware/audio_loop/main/call020_wearable_composition.c"
COMPOSITION_HEADER = ROOT / "firmware/audio_loop/main/call020_wearable_composition.h"
CMAKE = ROOT / "firmware/audio_loop/main/CMakeLists.txt"
BOOT_STUB = ROOT / "firmware/audio_loop/main/call020_operator_runner_boot_stub.c"
KCONFIG = ROOT / "firmware/audio_loop/main/Kconfig.projbuild"
DEFAULTS = ROOT / "firmware/audio_loop/sdkconfig.call020_operator_runner.defaults"
APP_MAIN = ROOT / "firmware/audio_loop/main/app_main.c"
README = ROOT / "firmware/audio_loop/README.md"
PACKET = ROOT / "docs/tasks/active/CALL-020_LTE_DATA_VOICE_POC.md"


def function_body(source: str, name: str, next_name: str) -> str:
    match = re.search(
        rf"esp_err_t {name}\((?P<body>.*?)\n\}}\n\nesp_err_t {next_name}\(",
        source,
        flags=re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"could not isolate {name}")
    return match.group("body")


class Call020OperatorRunnerStaticTests(unittest.TestCase):
    def test_source_is_default_disabled_and_ordinary_app_main_is_untouched(self) -> None:
        cmake = CMAKE.read_text(encoding="utf-8")
        kconfig = KCONFIG.read_text(encoding="utf-8")
        app_main = APP_MAIN.read_text(encoding="utf-8")

        self.assertIn('"call020_operator_runner.c"', cmake)
        block = re.search(
            r"config EGOLINK_CALL020_OPERATOR_RUNNER(?P<body>.*?)\n\nendmenu",
            kconfig,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(block)
        self.assertIn("default n", block.group("body"))
        self.assertIn("depends on EGOLINK_CALL020_WEARABLE_COMPOSITION", block.group("body"))
        self.assertIn("depends on !EGOLINK_AUDIO_LOOP_AUTORUN", block.group("body"))
        self.assertNotIn("call020_operator_runner", app_main.lower())

    def test_dedicated_boot_entry_is_inert_and_default_uses_ordinary_app_main(self) -> None:
        cmake = CMAKE.read_text(encoding="utf-8")
        stub = BOOT_STUB.read_text(encoding="utf-8")

        self.assertIn("if(CONFIG_EGOLINK_CALL020_OPERATOR_RUNNER)", cmake)
        self.assertIn('"call020_operator_runner_boot_stub.c"', cmake)
        self.assertIn('list(APPEND call020_audio_loop_sources "app_main.c")', cmake)
        self.assertRegex(stub, r"void\s+app_main\s*\(void\)\s*\{\s*\}")
        for forbidden in (
            "call020_operator_runner_prepare",
            "call020_operator_runner_start",
            "gpio_",
            "i2s_",
            "usb_",
            "xTaskCreate",
            "printf(",
            "ESP_LOG",
        ):
            self.assertNotIn(forbidden, stub)

    def test_dedicated_profile_retains_entry_and_excludes_console_logs(self) -> None:
        cmake = CMAKE.read_text(encoding="utf-8")
        defaults = DEFAULTS.read_text(encoding="utf-8")

        self.assertIn("if(CONFIG_EGOLINK_CALL020_OPERATOR_RUNNER)", cmake)
        self.assertIn("-u call020_operator_runner_retained_entry", cmake)
        for setting in (
            "CONFIG_EGOLINK_AUDIO_LOOP_AUTORUN=n",
            "CONFIG_EGOLINK_CALL020_MEDIA_ADAPTER_CORE=y",
            "CONFIG_EGOLINK_CALL020_USB_SERIAL_JTAG_ENDPOINT=y",
            "CONFIG_EGOLINK_CALL020_WEARABLE_COMPOSITION=y",
            "CONFIG_EGOLINK_CALL020_OPERATOR_RUNNER=y",
            "CONFIG_EGOLINK_CALL020_OUTPUT_VOLUME=55",
            "CONFIG_ESP_CONSOLE_NONE=y",
            "CONFIG_ESP_CONSOLE_SECONDARY_NONE=y",
            "CONFIG_LOG_DEFAULT_LEVEL_NONE=y",
            "CONFIG_BOOTLOADER_LOG_LEVEL_NONE=y",
            "CONFIG_FREERTOS_PLACE_FUNCTIONS_INTO_FLASH=y",
            "CONFIG_RINGBUF_PLACE_FUNCTIONS_INTO_FLASH=y",
            "# CONFIG_RINGBUF_PLACE_ISR_FUNCTIONS_INTO_FLASH is not set",
        ):
            self.assertIn(setting, defaults)
        self.assertIn("# CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG is not set", defaults)
        self.assertIn(
            "# CONFIG_ESP_CONSOLE_SECONDARY_USB_SERIAL_JTAG is not set",
            defaults,
        )

    def test_large_composition_is_global_internal_dram_not_automatic(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")

        self.assertIn("call020_wearable_composition_t composition;", source)
        self.assertIn(
            "static call020_operator_runner_context_t s_runner;",
            source,
        )
        self.assertIn("never an automatic variable or task-stack local", source)
        self.assertEqual(source.count("call020_wearable_composition_t composition;"), 1)
        for function in re.findall(
            r"(?:static\s+)?(?:esp_err_t|bool|void|const char \*)\s+"
            r"[A-Za-z0-9_]+\([^)]*\)\s*\{(?P<body>.*?)\n\}",
            source,
            flags=re.DOTALL,
        ):
            self.assertNotIn("call020_wearable_composition_t ", function)

    def test_prepare_only_validates_and_generates_no_device_io(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        prepare = re.search(
            r"esp_err_t call020_operator_runner_prepare\((?P<body>.*?)"
            r"\n}\n\nstatic esp_err_t runner_start_internal\(",
            source,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(prepare)
        body = prepare.group("body")

        self.assertIn("runner_config_valid(config)", body)
        self.assertIn("generate_descriptor", body)
        self.assertIn("xPortGetCoreID()", body)
        for forbidden in (
            "call020_wearable_composition_install",
            "call020_wearable_composition_start",
            "call010_safe_audio_v1_init",
            "usb_serial_jtag_driver_install",
            "gpio_set_level",
            "i2s_channel_",
            "xTaskCreate",
        ):
            self.assertNotIn(forbidden, body)

    def test_start_is_the_only_explicit_install_and_start_boundary(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        internal = re.search(
            r"static esp_err_t runner_start_internal\((?P<body>.*?)"
            r"\n}\n\nesp_err_t call020_operator_runner_start\(",
            source,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(internal)
        body = internal.group("body")

        self.assertIn("call020_wearable_composition_install", body)
        self.assertIn("call020_wearable_composition_start", body)
        self.assertIn("CALL020_WEARABLE_IDENTITY_RUNTIME_EPHEMERAL", body)
        self.assertEqual(source.count("call020_wearable_composition_install("), 1)
        self.assertEqual(source.count("call020_wearable_composition_start("), 1)
        self.assertNotRegex(source, r"\bvoid\s+app_main\s*\(")

    def test_additive_start_with_lease_preserves_ordinary_start_and_v1_table(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        header = HEADER.read_text(encoding="utf-8")

        self.assertIn("call020_operator_runner_start_with_usb_driver_lease", header)
        self.assertIn("runner_start_internal(NULL)", source)
        self.assertIn("runner_start_internal(lease)", source)
        self.assertIn(
            "call020_wearable_composition_install_with_usb_driver_lease",
            source,
        )
        table = re.search(
            r"static const call020_operator_runner_api_t s_retained_api = \{"
            r"(?P<body>.*?)\n};",
            source,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(table)
        self.assertIn(".start = call020_operator_runner_start", table.group("body"))
        self.assertNotIn("start_with_usb_driver_lease", table.group("body"))
        self.assertIn("v1 retained remote table remains unchanged", header)

    def test_runner_lease_metadata_distinguishes_return_from_uninstall(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        header = HEADER.read_text(encoding="utf-8")

        for field in (
            "usb_driver_lease_supplied",
            "usb_driver_lease_borrowed",
            "usb_driver_binding_closed",
            "usb_driver_lease_returned",
            "usb_driver_uninstalled_by_runner",
            "usb_driver_lease_generation",
        ):
            self.assertIn(field, header)
            self.assertIn(field, source)
        self.assertIn("CALL020_USB_ENDPOINT_DRIVER_LEASE_BORROWED", source)
        self.assertIn("metadata.usb_driver_uninstalled_by_composition", source)

    def test_random_nonce_claims_are_honest_and_role_ids_are_correlated(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        header = HEADER.read_text(encoding="utf-8")
        defaults = DEFAULTS.read_text(encoding="utf-8")

        self.assertIn("esp_fill_random(nonce, sizeof(nonce))", source)
        self.assertIn("nonce_is_nonzero", source)
        self.assertIn("secure_zero(nonce, sizeof(nonce))", source)
        self.assertIn("uint32_t nonce_bits", header)
        self.assertIn("CALL020_OPERATOR_RANDOM_SOURCE_ESP_FILL_RANDOM", header)
        self.assertIn("CALL020_OPERATOR_RANDOM_QUALITY_UNVERIFIED", header)
        self.assertIn("bool correlated_routing_ids", header)
        self.assertIn("non-secret", header)
        self.assertIn("not authentication", header)
        self.assertIn("quality is unverified", defaults)
        self.assertNotIn("entropy_bits", source + header)

    def test_runner_accepts_no_identity_strings_or_build_fixtures(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        header = HEADER.read_text(encoding="utf-8")
        defaults = DEFAULTS.read_text(encoding="utf-8")

        config = re.search(
            r"typedef struct \{(?P<body>.*?)\} call020_operator_runner_config_t;",
            header,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(config)
        for identity in (
            "session_id",
            "device_id",
            "guardian_id",
            "uplink_clock_id",
            "downlink_clock_id",
        ):
            self.assertNotIn(identity, config.group("body"))
        self.assertIn("There are intentionally no identity", defaults)
        self.assertNotIn("build-only-session", source)
        self.assertNotIn("wearable-node-001", source)

    def test_mutating_lifecycle_is_same_core_and_serialized_by_contract(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        header = HEADER.read_text(encoding="utf-8")

        self.assertIn("captured by prepare", header)
        internal = re.search(
            r"static esp_err_t runner_start_internal\((?P<body>.*?)"
            r"\n}\n\nesp_err_t call020_operator_runner_start\(",
            source,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(internal)
        self.assertIn("on_owner_core()", internal.group("body"))
        self.assertIn("reject_wrong_core()", internal.group("body"))
        for name, next_name in (
            ("call020_operator_runner_cancel", "call020_operator_runner_join"),
            ("call020_operator_runner_join", "call020_operator_runner_close"),
            ("call020_operator_runner_close", "call020_operator_runner_get_descriptor"),
        ):
            body = function_body(source, name, next_name)
            self.assertIn("on_owner_core()", body)
            self.assertIn("reject_wrong_core()", body)
        self.assertIn("portMUX_TYPE s_runner_lock", source)

    def test_every_installed_failure_path_has_verified_safe_control(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        composition_source = COMPOSITION_SOURCE.read_text(encoding="utf-8")
        composition_header = COMPOSITION_HEADER.read_text(encoding="utf-8")

        self.assertIn("force_safe_if_installed", source)
        self.assertGreaterEqual(source.count("force_safe_if_installed()"), 7)
        self.assertIn("call020_wearable_composition_force_safe", source)
        self.assertIn("call020_wearable_composition_force_safe", composition_header)
        safety = re.search(
            r"esp_err_t call020_wearable_composition_force_safe\((?P<body>.*?)\n\}",
            composition_source,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(safety)
        self.assertIn("set_cancel_and_wake", safety.group("body"))
        self.assertIn("force_output_safe", safety.group("body"))

    def test_retained_api_table_references_complete_control_surface(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        header = HEADER.read_text(encoding="utf-8")

        self.assertIn("static const call020_operator_runner_api_t s_retained_api", source)
        for member in (
            ".prepare = call020_operator_runner_prepare",
            ".start = call020_operator_runner_start",
            ".cancel = call020_operator_runner_cancel",
            ".join = call020_operator_runner_join",
            ".close = call020_operator_runner_close",
        ):
            self.assertIn(member, source)
        self.assertIn("return &s_retained_api;", source)
        self.assertIn("call020_operator_runner_retained_entry", header)

    def test_all_configured_lengths_and_waits_are_bounded(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")

        for bound in (
            "CALL020_WEARABLE_HANDOFF_QUEUE_MAX_FRAMES",
            "CALL020_WEARABLE_AUDIO_IO_TIMEOUT_MAX_US",
            "CALL020_WEARABLE_USB_READ_POLL_MAX_US",
            "CALL020_WEARABLE_JOIN_TIMEOUT_MAX_US",
            "CALL020_MEDIA_MAX_RUNTIME_US",
            "CALL020_USB_ENDPOINT_MAX_IO_SLICE_MS",
            "CALL020_USB_ENDPOINT_MAX_OPERATION_US",
            "CALL020_USB_ENDPOINT_MAX_CLOSE_TIMEOUT_US",
            "CALL020_USB_ENDPOINT_MAX_DRIVER_BUFFER_BYTES",
        ):
            self.assertIn(bound, source)
        self.assertIn("CALL020_OPERATOR_EXPECTED_WIRE_BYTES", source)
        self.assertIn("CALL020_OPERATOR_USB_BUFFER_MAX_BYTES", source)
        self.assertNotIn(
            "config->usb_endpoint.tx_buffer_bytes <=\n"
            "            CALL020_USB_ENDPOINT_MAX_DRIVER_BUFFER_BYTES",
            source,
        )

    def test_memory_tuning_keeps_isr_ring_paths_internal(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        defaults = DEFAULTS.read_text(encoding="utf-8")

        self.assertIn("CONFIG_FREERTOS_PLACE_FUNCTIONS_INTO_FLASH", source)
        self.assertIn("CONFIG_RINGBUF_PLACE_FUNCTIONS_INTO_FLASH", source)
        self.assertIn("CONFIG_RINGBUF_PLACE_ISR_FUNCTIONS_INTO_FLASH", source)
        self.assertIn("does not perform OTA", defaults)
        self.assertIn("cache-off operation", defaults)
        self.assertIn("keep all ISR ring-buffer", defaults)

    def test_runner_has_no_media_log_storage_network_or_credentials(self) -> None:
        source = SOURCE.read_text(encoding="utf-8").lower()

        for forbidden in (
            "esp_log",
            "printf(",
            "fopen(",
            "fwrite(",
            "nvs_",
            "littlefs",
            "spiffs",
            "socket(",
            "connect(",
            "http",
            "mqtt",
            "tls",
            "password",
            "secret",
        ):
            self.assertNotIn(forbidden, source)

    def test_packet_declares_narrow_offline_ownership_and_nonclaims(self) -> None:
        packet = PACKET.read_text(encoding="utf-8")

        for path in (
            "firmware/audio_loop/main/call020_operator_runner.c",
            "firmware/audio_loop/main/call020_operator_runner.h",
            "firmware/audio_loop/main/call020_operator_runner_boot_stub.c",
            "firmware/audio_loop/sdkconfig.call020_operator_runner.defaults",
            "quality_tests/test_call020_operator_runner.py",
        ):
            self.assertIn(path, packet)
        self.assertIn("CALL-020G Retained non-autorun operator runner ownership", packet)
        self.assertIn("flashing, opening USB/audio", packet)


if __name__ == "__main__":
    unittest.main()

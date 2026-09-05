from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "firmware" / "audio_loop"
SOURCE = TARGET / "main" / "call020_wearable_composition.c"
HEADER = TARGET / "main" / "call020_wearable_composition.h"
APP_MAIN = TARGET / "main" / "app_main.c"
MAIN_CMAKE = TARGET / "main" / "CMakeLists.txt"
KCONFIG = TARGET / "main" / "Kconfig.projbuild"
DEDICATED_DEFAULTS = TARGET / "sdkconfig.call020_wearable.defaults"
README = TARGET / "README.md"
PACKET = ROOT / "docs" / "tasks" / "active" / "CALL-020_LTE_DATA_VOICE_POC.md"


class Call020WearableCompositionStaticTests(unittest.TestCase):
    """Source/contract assertions only; these tests never execute C or I/O."""

    def test_static_wiring_is_default_disabled_and_app_main_uninstantiated(self) -> None:
        cmake = MAIN_CMAKE.read_text(encoding="utf-8")
        kconfig = KCONFIG.read_text(encoding="utf-8")
        app_main = APP_MAIN.read_text(encoding="utf-8")

        self.assertIn('"call020_wearable_composition.c"', cmake)
        option = re.search(
            r"config EGOLINK_CALL020_WEARABLE_COMPOSITION"
            r"(?P<body>.*?)\nendmenu",
            kconfig,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(option)
        self.assertIn("default n", option.group("body"))
        self.assertNotIn("call020_wearable_composition", app_main)
        self.assertNotIn("EGOLINK_CALL020_WEARABLE_COMPOSITION", app_main)

    def test_dedicated_profile_excludes_console_logs_and_autorun(self) -> None:
        defaults = DEDICATED_DEFAULTS.read_text(encoding="utf-8")
        kconfig = KCONFIG.read_text(encoding="utf-8")
        source = SOURCE.read_text(encoding="utf-8")

        for enabled in (
            "CONFIG_EGOLINK_CALL020_MEDIA_ADAPTER_CORE=y",
            "CONFIG_EGOLINK_CALL020_USB_SERIAL_JTAG_ENDPOINT=y",
            "CONFIG_EGOLINK_CALL020_WEARABLE_COMPOSITION=y",
            "CONFIG_ESP_CONSOLE_NONE=y",
            "CONFIG_ESP_CONSOLE_SECONDARY_NONE=y",
            "CONFIG_LOG_DEFAULT_LEVEL_NONE=y",
            "CONFIG_BOOTLOADER_LOG_LEVEL_NONE=y",
        ):
            self.assertIn(enabled, defaults)
        for disabled in (
            "CONFIG_EGOLINK_AUDIO_LOOP_AUTORUN=n",
            "# CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG is not set",
            "# CONFIG_ESP_CONSOLE_SECONDARY_USB_SERIAL_JTAG is not set",
        ):
            self.assertIn(disabled, defaults)
        for dependency in (
            "depends on EGOLINK_CALL020_USB_SERIAL_JTAG_ENDPOINT",
            "depends on !EGOLINK_AUDIO_LOOP_AUTORUN",
            "depends on ESP_CONSOLE_NONE",
            "depends on ESP_CONSOLE_SECONDARY_NONE",
            "depends on LOG_DEFAULT_LEVEL_NONE",
            "depends on BOOTLOADER_LOG_LEVEL_NONE",
        ):
            self.assertIn(dependency, kconfig)
        self.assertIn("CALL-020F requires CONFIG_ESP_CONSOLE_NONE", source)
        self.assertIn("CALL-020F cannot share the CALL-010 autorun owner", source)

    def test_exact_twenty_ms_audio_profile_and_actual_safe_path_are_bound(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")

        self.assertIn("CALL020_MEDIA_FRAME_MS == 20U", source)
        self.assertIn("CALL020_MEDIA_STEREO_BYTES == 1280U", source)
        self.assertIn("CALL020_MEDIA_MONO_BYTES == 640U", source)
        self.assertIn("call010_safe_audio_v1_init(", source)
        self.assertIn("CALL020_MEDIA_SAMPLE_RATE_HZ", source)
        self.assertIn("esp_codec_dev_open(composition->audio.speaker", source)
        self.assertIn("esp_codec_dev_open(composition->audio.microphone", source)
        self.assertIn("CONFIG_EGOLINK_CALL020_OUTPUT_VOLUME", source)
        self.assertIn("CALL020_OUTPUT_VOLUME_MAX 85", source)
        self.assertIn("ES8311_DAC_VOLUME_REGISTER", source)
        self.assertIn("metadata.output_volume_verified", source)
        volume_option = re.search(
            r"config EGOLINK_CALL020_OUTPUT_VOLUME(?P<body>.*?)\nendmenu",
            KCONFIG.read_text(encoding="utf-8"),
            flags=re.DOTALL,
        )
        self.assertIsNotNone(volume_option)
        self.assertIn("range 1 85", volume_option.group("body"))
        self.assertIn("default 55", volume_option.group("body"))
        self.assertIn("i2s_channel_read(", source)
        self.assertIn("i2s_channel_write(", source)
        self.assertIn("bytes_read != CALL020_MEDIA_STEREO_BYTES", source)
        self.assertIn("bytes_written != CALL020_MEDIA_STEREO_BYTES", source)

    def test_four_workers_use_directional_queues_and_two_single_owner_cores(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        header = HEADER.read_text(encoding="utf-8")

        for worker in (
            "audio_capture_worker",
            "usb_uplink_worker",
            "usb_downlink_worker",
            "audio_output_worker",
        ):
            self.assertIn(f"static void {worker}", source)
            self.assertIn(f"composition, {worker}", source)
        self.assertEqual(source.count("xTaskCreate("), 1)
        self.assertIn("QueueHandle_t uplink_handoff_queue", header)
        self.assertIn("QueueHandle_t downlink_handoff_queue", header)
        self.assertIn("call020_media_adapter_core_t uplink_core", header)
        self.assertIn("call020_media_adapter_core_t downlink_core", header)
        self.assertIn("No core mutex is held over", header)
        self.assertNotIn("SemaphoreHandle_t", header)

    def test_complete_wire_size_is_identity_derived_and_read_in_one_exact_call(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        header = HEADER.read_text(encoding="utf-8")

        for identifier in (
            "config->session_id",
            "config->guardian_id",
            "config->device_id",
            "config->downlink_clock_id",
        ):
            self.assertIn(identifier, source)
        self.assertIn("CALL020_MEDIA_WIRE_HEADER_BYTES", source)
        self.assertIn("CALL020_MEDIA_MONO_BYTES", source)
        self.assertIn("CALL020_MEDIA_WIRE_CRC_BYTES", source)
        self.assertIn("call020_usb_serial_jtag_endpoint_read_exact(", source)
        self.assertIn("composition->expected_downlink_wire_bytes", source)
        self.assertIn("uint8_t wire[CALL020_MEDIA_WIRE_MAX_BYTES]", header)

    def test_deadline_run_limit_and_terminal_progress_are_fail_closed(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")

        self.assertIn("esp_timer_get_time()", source)
        self.assertIn("composition->runtime_deadline_us", source)
        self.assertIn("CALL020_WEARABLE_TERMINAL_RUNTIME", source)
        self.assertIn("CALL020_USB_ENDPOINT_TRANSFER_TIMEOUT_ZERO_PROGRESS", source)
        self.assertIn("composition->metadata.zero_progress_read_timeouts++", source)
        self.assertIn("composition->metadata.zero_progress_write_timeouts++", source)
        self.assertIn("transfer != CALL020_USB_ENDPOINT_TRANSFER_OK", source)
        self.assertIn("CALL020_WEARABLE_TERMINAL_USB_DOWNLINK", source)
        self.assertIn("CALL020_MEDIA_CORE_TERMINAL", source)

    def test_cancellation_and_join_precede_endpoint_uninstall(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        header = HEADER.read_text(encoding="utf-8")

        close = re.search(
            r"esp_err_t call020_wearable_composition_close\((?P<body>.*?)"
            r"\n}\n\nesp_err_t call020_wearable_composition_get_metadata",
            source,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(close)
        body = close.group("body")
        self.assertLess(
            body.index("call020_wearable_composition_request_cancel"),
            body.index("call020_wearable_composition_join"),
        )
        self.assertLess(
            body.index("call020_wearable_composition_join"),
            body.index("call020_usb_serial_jtag_endpoint_close"),
        )
        self.assertIn("if (join_result != ESP_OK)", body)
        self.assertIn("leaves endpoint/audio installed for a later retry", header)
        self.assertIn("now_us < previous_now_us", source)

    def test_additive_lease_install_adopts_only_after_all_fallible_setup(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        header = HEADER.read_text(encoding="utf-8")

        self.assertIn(
            "call020_wearable_composition_install_with_usb_driver_lease",
            header,
        )
        self.assertIn("composition_install_internal", source)
        self.assertIn("usb_driver_lease == NULL", source)
        self.assertIn("call020_usb_serial_jtag_endpoint_install(", source)
        self.assertIn("call020_usb_serial_jtag_endpoint_adopt_lease(", source)
        self.assertLess(
            source.index("call020_media_adapter_core_init("),
            source.index("call020_usb_serial_jtag_endpoint_adopt_lease("),
        )
        self.assertIn("atomic final resource step", source)
        self.assertIn("return composition_install_internal(composition, config, NULL)", source)

    def test_composition_reports_borrowed_generation_and_returned_lifetime(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        header = HEADER.read_text(encoding="utf-8")

        for field in (
            "usb_driver_ownership",
            "usb_driver_lease_generation",
            "usb_driver_binding_closed",
            "usb_driver_uninstalled_by_composition",
            "usb_driver_lease_returned",
            "usb_driver_lifetime_owned_by_caller",
        ):
            self.assertIn(field, header)
            self.assertIn(field, source)
        self.assertIn("endpoint_borrowed_from_lease", header)
        self.assertIn("usb_driver_lease != NULL", source)
        self.assertIn("call020_usb_serial_jtag_endpoint_close", source)
        self.assertIn("Close returns the driver to", header)

    def test_output_is_fail_closed_and_owned_media_is_cleared(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        header = HEADER.read_text(encoding="utf-8")

        self.assertIn("esp_codec_dev_set_out_mute", source)
        self.assertIn("ES8311_DAC_MUTE_REGISTER", source)
        self.assertIn("gpio_set_level(BSP_POWER_AMP_IO, 0)", source)
        self.assertIn("gpio_get_level(BSP_POWER_AMP_IO) == 0", source)
        self.assertIn("force_output_safe(composition)", source)
        self.assertGreaterEqual(source.count("secure_zero("), 12)
        for owned in (
            "uplink_handoff_queue_storage",
            "downlink_handoff_queue_storage",
            "capture_scratch",
            "uplink_scratch",
            "usb_rx_scratch",
            "downlink_scratch",
        ):
            self.assertIn(owned, header)
            self.assertIn(owned, source)

    def test_identity_is_explicit_and_build_fixtures_are_rejected_nonproduction(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        header = HEADER.read_text(encoding="utf-8")
        defaults = DEDICATED_DEFAULTS.read_text(encoding="utf-8")

        for field in (
            "const char *session_id",
            "const char *device_id",
            "const char *guardian_id",
            "const char *uplink_clock_id",
            "const char *downlink_clock_id",
        ):
            self.assertIn(field, header)
        self.assertIn("CALL020_WEARABLE_IDENTITY_OPERATOR_SUPPLIED", source)
        self.assertIn("CALL020_WEARABLE_IDENTITY_NONPRODUCTION_BUILD_FIXTURE", source)
        self.assertIn("ESP_ERR_NOT_SUPPORTED", source)
        self.assertIn("documentation-only", defaults.lower())
        self.assertIn("MUST NOT be accepted", defaults)
        self.assertIn("CONFIG_EGOLINK_CALL020_OUTPUT_VOLUME=55", defaults)
        self.assertNotIn('"call020f-build-only-session"', source)

    def test_composition_has_no_raw_media_logging_storage_network_or_secret(self) -> None:
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
            "token",
            "password",
            "secret",
        ):
            self.assertNotIn(forbidden, source)
        self.assertNotRegex(source, r"\bvoid\s+app_main\s*\(")

    def test_docs_are_compile_only_and_list_operator_prerequisites(self) -> None:
        readme = README.read_text(encoding="utf-8")
        packet = PACKET.read_text(encoding="utf-8")

        for statement in (
            "CALL-020F dormant wearable composition",
            "source and ESP-IDF compile evidence only",
            "dedicated non-autorun runner",
            "drains/resynchronizes any ROM prefix",
            "authenticated\nTLS relay/RTC endpoint",
            "No composition instance",
        ):
            self.assertIn(statement, readme)
        self.assertIn("CALL-020F", packet)
        self.assertIn("build-only", packet)
        self.assertIn("`P0-CALL`", packet)


if __name__ == "__main__":
    unittest.main()

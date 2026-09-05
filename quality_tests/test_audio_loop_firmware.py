from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "firmware" / "audio_loop"
SOURCE = TARGET / "main" / "app_main.c"
SAFE_INITIALIZER = TARGET / "main" / "safe_audio_initializer_v1.c"
SAFE_INITIALIZER_HEADER = TARGET / "main" / "safe_audio_initializer_v1.h"
KCONFIG = TARGET / "main" / "Kconfig.projbuild"
MANIFEST = TARGET / "main" / "idf_component.yml"
README = TARGET / "README.md"
OPERATOR_DEFAULTS = TARGET / "sdkconfig.operator_test.defaults"
OUTPUT_DIAGNOSTIC_DEFAULTS = TARGET / "sdkconfig.output_diagnostic.defaults"
HARDWARE_RUNNER = TARGET / "run_call010_hardware.ps1"
OUTPUT_DIAGNOSTIC_RUNNER = TARGET / "run_call010_output_debug.ps1"


class AudioLoopFirmwareStaticTests(unittest.TestCase):
    def test_target_is_isolated_and_dependencies_are_pinned(self) -> None:
        cmake = (TARGET / "CMakeLists.txt").read_text(encoding="utf-8")
        main_cmake = (TARGET / "main" / "CMakeLists.txt").read_text(encoding="utf-8")
        manifest = MANIFEST.read_text(encoding="utf-8")
        source = SOURCE.read_text(encoding="utf-8")

        self.assertIn("project(egolink_call010_audio_loop)", cmake)
        self.assertIn('"safe_audio_initializer_v1.c"', main_cmake)
        self.assertIn('version: "1.0.3"', manifest)
        self.assertIn('version: "1.3.6"', manifest)
        self.assertIn('version: "2.6.0"', manifest)
        self.assertIn('version: "9.2.0"', manifest)
        self.assertIn('version: "1.0.2"', manifest)
        for forbidden_include in (
            "esp_wifi.h",
            "esp_http_client.h",
            "mqtt_client.h",
            "sim7670",
        ):
            self.assertNotIn(forbidden_include, source.lower())

    def test_local_initializer_excludes_codec_pa_and_owns_all_resources(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        initializer = SAFE_INITIALIZER.read_text(encoding="utf-8")
        header = SAFE_INITIALIZER_HEADER.read_text(encoding="utf-8")

        self.assertIn("CALL010_SAFE_AUDIO_INITIALIZER_VERSION", header)
        self.assertIn('"call010-safe-audio-init-v1"', header)
        self.assertIn(".pa_pin = -1", initializer)
        self.assertIn(".gpio_if = NULL", initializer)
        self.assertNotIn("BSP_POWER_AMP_IO", initializer)
        self.assertNotIn("bsp_audio_codec_speaker_init", source + initializer)
        self.assertNotIn("bsp_audio_codec_microphone_init", source + initializer)
        self.assertNotIn("bsp_audio_init", source + initializer)
        self.assertIn("bsp_i2c_init()", initializer)
        self.assertIn("bsp_i2c_get_handle()", initializer)
        self.assertIn("audio_codec_new_i2s_data", initializer)
        self.assertIn("es8311_codec_new", initializer)
        self.assertIn("es7210_codec_new", initializer)
        self.assertIn("ES7120_SEL_MIC1 | ES7120_SEL_MIC2", initializer)
        self.assertEqual(
            initializer.count(".data_if = context->shared_i2s_data_if"), 2
        )
        for cleanup_api in (
            "esp_codec_dev_delete",
            "audio_codec_delete_codec_if",
            "audio_codec_delete_ctrl_if",
            "audio_codec_delete_data_if",
            "i2s_del_channel",
            "bsp_i2c_deinit",
        ):
            self.assertIn(cleanup_api, initializer)
        self.assertIn("fail:\n    call010_safe_audio_v1_deinit(context);", initializer)
        self.assertLess(
            source.index("esp_err_t result = pa_prepare_off();"),
            source.index(
                "result = call010_safe_audio_v1_init(&audio, AUDIO_SAMPLE_RATE_HZ);"
            ),
        )
        pa_prepare = re.search(
            r"static esp_err_t pa_prepare_off\(void\)(?P<body>.*?)"
            r"\n}\n\nstatic esp_err_t pa_enable",
            source,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(pa_prepare)
        self.assertLess(
            pa_prepare.group("body").index("gpio_set_level"),
            pa_prepare.group("body").index("gpio_config"),
        )
        self.assertIn("pa_force_off()", pa_prepare.group("body"))
        self.assertIn("GPIO_MODE_INPUT_OUTPUT", pa_prepare.group("body"))
        pa_force = re.search(
            r"static esp_err_t pa_force_off\(void\)(?P<body>.*?)"
            r"\n}\n\nstatic esp_err_t pa_prepare_off",
            source,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(pa_force)
        self.assertIn("gpio_get_level", pa_force.group("body"))

    def test_default_is_dormant_and_hardware_sequence_is_bounded(self) -> None:
        kconfig = KCONFIG.read_text(encoding="utf-8")
        source = SOURCE.read_text(encoding="utf-8")

        autorun = re.search(
            r"config EGOLINK_AUDIO_LOOP_AUTORUN(?P<body>.*?)(?:\nconfig|\nendmenu)",
            kconfig,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(autorun)
        self.assertIn("default n", autorun.group("body"))
        self.assertIn("range 1 20", kconfig)
        self.assertIn("default 30", kconfig)
        self.assertIn("default 120", kconfig)
        self.assertIn("AUDIO_FRAME_MS 20", source)
        self.assertIn("AUDIO_PHASE_OUTPUT_CHIRP", source)
        self.assertIn("AUDIO_PHASE_INPUT_METRICS", source)
        self.assertIn("AUDIO_PHASE_ATTENUATED_LOOP", source)
        self.assertIn("CONFIG_EGOLINK_AUDIO_LOOP_AUTORUN=y", OPERATOR_DEFAULTS.read_text(encoding="utf-8"))
        self.assertIn("claim_one_run_per_power_cycle", source)
        self.assertIn("RTC_NOINIT_ATTR static volatile uint32_t s_audio_run_latch", source)
        self.assertIn("DORMANT_LATCH_CLEARED", source)
        self.assertRegex(
            source,
            r"if \(!CONFIG_EGOLINK_AUDIO_LOOP_AUTORUN\) \{\s*"
            r"s_audio_run_latch = 0;",
        )
        self.assertIn("audio_deadline_callback", source)
        self.assertIn("if (s_audio_deadline_expired)", source)
        app_main = re.search(
            r"void app_main\(void\)(?P<body>.*)\Z", source, flags=re.DOTALL
        )
        self.assertIsNotNone(app_main)
        app_main_body = app_main.group("body")
        self.assertLess(
            app_main_body.index("startup_pa_off = pa_prepare_off()"),
            app_main_body.index("if (!CONFIG_EGOLINK_AUDIO_LOOP_AUTORUN)"),
        )
        startup_check = re.search(
            r"startup_pa_off = pa_prepare_off\(\);\s*"
            r"if \(startup_pa_off != ESP_OK\) \{(?P<body>.*?)\n    \}",
            app_main_body,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(startup_check)
        self.assertIn("return;", startup_check.group("body"))

    def test_privacy_metrics_and_fail_closed_mute_are_explicit(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        readme = README.read_text(encoding="utf-8")

        self.assertIn("speaker_set_output_enabled", source)
        self.assertIn("verify_codec_mute", source)
        self.assertIn("ES8311_MUTE_READBACK_ATTEMPTS 3", source)
        self.assertIn("retry_codec_mute_register_once", source)
        self.assertIn("one bounded direct register retry", source)
        self.assertIn("esp_codec_dev_write_reg", source)
        self.assertIn("ES8311_SAFE_VOLUME_READBACK", source)
        self.assertIn("ES8311_SAFE_VOLUME_REGISTER", source)
        self.assertIn("set_safe_output_volume_verified(speaker)", source)
        self.assertIn("? mute_bits == ES8311_DAC_MUTE_MASK", source)
        self.assertIn(": mute_bits == 0", source)
        self.assertLess(
            source.index("esp_err_t result = pa_force_off();"),
            source.index("result = retry_codec_mute_register_once"),
        )
        self.assertLess(
            source.index("result = set_safe_output_volume_verified(speaker)"),
            source.index("const audio_phase_t phases[]"),
        )
        self.assertIn("pa_force_off", source)
        self.assertIn("speaker_pa_off_verified=%s", source)
        self.assertNotIn(
            "speaker_muted=true",
            source[: source.index("static esp_err_t output_diagnostic_countdown")],
        )
        for field in (
            "rms=",
            "peak=",
            "clipped_ratio=",
            "zero_ratio=",
            "frame_seq_gaps=",
            "processing_time_p50_us=",
            "processing_time_p95_us=",
        ):
            self.assertIn(field, source)
        self.assertNotRegex(
            source + SAFE_INITIALIZER.read_text(encoding="utf-8"),
            r"f(open|write|read)\s*\(",
        )
        self.assertIn("never logged or\nstored", readme)
        self.assertIn("explicitly zeroed on exit", readme)
        self.assertIn("exact physical PCB revision: `unknown`", readme)

    def test_output_diagnostic_is_tx_only_capped_and_byte_verified(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        initializer = SAFE_INITIALIZER.read_text(encoding="utf-8")
        header = SAFE_INITIALIZER_HEADER.read_text(encoding="utf-8")
        kconfig = KCONFIG.read_text(encoding="utf-8")
        defaults = OUTPUT_DIAGNOSTIC_DEFAULTS.read_text(encoding="utf-8")
        readme = README.read_text(encoding="utf-8")

        self.assertIn("config EGOLINK_AUDIO_OUTPUT_DIAGNOSTIC", kconfig)
        self.assertRegex(
            kconfig,
            r"(?s)config EGOLINK_AUDIO_OUTPUT_DIAGNOSTIC.*?"
            r"depends on EGOLINK_AUDIO_LOOP_AUTORUN.*?default n",
        )
        self.assertIn("CONFIG_EGOLINK_AUDIO_LOOP_AUTORUN=y", defaults)
        self.assertIn("CONFIG_EGOLINK_AUDIO_OUTPUT_DIAGNOSTIC=y", defaults)

        self.assertIn("call010_safe_audio_v1_init_output_only", header)
        self.assertIn("call010_safe_audio_v1_init_output_only", initializer)
        self.assertRegex(
            initializer,
            r"include_microphone\s*\? &context->rx_channel",
        )
        self.assertIn(
            "include_microphone ? BSP_I2S_DSIN : I2S_GPIO_UNUSED",
            initializer,
        )
        for microphone_resource in (
            "microphone_ctrl_if",
            "microphone_codec_if",
            "microphone_device_config",
        ):
            self.assertRegex(
                initializer,
                rf"(?s)if \(include_microphone\) \{{.*?{microphone_resource}",
            )

        for declaration in (
            "AUDIO_OUTPUT_DIAGNOSTIC_COUNTDOWN_SECONDS 15",
            "AUDIO_OUTPUT_DIAGNOSTIC_STAGE_SECONDS 2",
            "AUDIO_OUTPUT_DIAGNOSTIC_GAP_SECONDS 2",
            "AUDIO_OUTPUT_DIAGNOSTIC_VOLUME_1 55",
            "AUDIO_OUTPUT_DIAGNOSTIC_VOLUME_2 70",
            "AUDIO_OUTPUT_DIAGNOSTIC_VOLUME_3 85",
            "AUDIO_OUTPUT_DIAGNOSTIC_MAX_VOLUME 85",
            "AUDIO_OUTPUT_DIAGNOSTIC_PCM_PEAK 5000",
            "AUDIO_OUTPUT_DIAGNOSTIC_FREQUENCY_HZ 1000",
            "AUDIO_OUTPUT_DIAGNOSTIC_DEADLINE_SECONDS 30",
        ):
            self.assertIn(declaration, source)
        self.assertIn(
            "AUDIO_OUTPUT_DIAGNOSTIC_VOLUME_3 <= "
            "AUDIO_OUTPUT_DIAGNOSTIC_MAX_VOLUME",
            source,
        )

        diagnostic_sequence = re.search(
            r"static esp_err_t run_bounded_output_diagnostic\(void\)"
            r"(?P<body>.*?)\n}\n\nvoid app_main",
            source,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(diagnostic_sequence)
        self.assertIn(
            "call010_safe_audio_v1_init_output_only",
            diagnostic_sequence.group("body"),
        )
        self.assertNotIn("esp_codec_dev_read(", diagnostic_sequence.group("body"))
        self.assertNotIn("esp_codec_dev_set_in_gain", diagnostic_sequence.group("body"))
        self.assertIn(
            "open_output_diagnostic_codec_prearmed(&audio, &format)",
            diagnostic_sequence.group("body"),
        )
        self.assertNotIn(
            "esp_codec_dev_open(speaker, &format)",
            diagnostic_sequence.group("body"),
        )

        prearmed_open = re.search(
            r"static esp_err_t open_output_diagnostic_codec_prearmed\(.*?"
            r"(?P<body>.*?)\n}\n\nstatic void audio_deadline_callback",
            source,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(prearmed_open)
        prearmed_body = prearmed_open.group("body")
        self.assertLess(
            prearmed_body.index("pa_force_off()"),
            prearmed_body.index("i2s_channel_enable(audio->tx_channel)"),
        )
        self.assertLess(
            prearmed_body.index("i2s_channel_enable(audio->tx_channel)"),
            prearmed_body.index("esp_codec_dev_open(audio->speaker, format)"),
        )
        self.assertIn("audio->rx_channel != NULL", prearmed_body)
        self.assertIn("audio->microphone != NULL", prearmed_body)
        self.assertIn("esp_codec_dev_close(audio->speaker)", prearmed_body)
        self.assertGreaterEqual(prearmed_body.count("pa_force_off()"), 4)
        self.assertIn("AUDIO_OUTPUT_TX_PREARM", prearmed_body)

        stage = re.search(
            r"static esp_err_t run_output_diagnostic_stage\(.*?"
            r"(?P<body>.*?)\n}\n\nstatic esp_err_t output_diagnostic_gap",
            source,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(stage)
        stage_body = stage.group("body")
        self.assertIn("i2s_channel_write", stage_body)
        self.assertIn("bytes_written != bytes_per_frame", stage_body)
        self.assertIn("metrics.actual_bytes_written += bytes_written", stage_body)
        self.assertIn("metrics.actual_bytes_written == expected_bytes", stage_body)
        self.assertIn("speaker_set_output_enabled(audio->speaker, false)", stage_body)
        self.assertLess(
            stage_body.index("speaker_set_output_enabled(audio->speaker, false)"),
            stage_body.index('"AUDIO_OUTPUT_STAGE_END'),
        )
        self.assertIn("AUDIO_OUTPUT_STAGE_ABORT", stage_body)
        self.assertIn("AUDIO_OUTPUT_DIAGNOSTIC_COMPLETE", source)
        self.assertIn("microphone_reads=0 raw_audio_retained=false", source)

        self.assertIn("15-second warning countdown", readme)
        self.assertIn("volumes 55, 70, and 85", readme)
        self.assertIn("128000/128000 bytes", readme)
        self.assertIn("at least one metre from", readme)

    def test_readme_does_not_promote_static_build_to_product_evidence(self) -> None:
        readme = README.read_text(encoding="utf-8")
        self.assertIn("does not authorize flashing", readme)
        self.assertIn("does not pass `P0-CALL`", readme)
        self.assertIn("no proof", readme)

    def test_hardware_runner_is_wearable_only_bounded_and_privacy_safe(self) -> None:
        runner = HARDWARE_RUNNER.read_text(encoding="utf-8")

        self.assertIn("OperatorAuthorized", runner)
        self.assertIn("RunId", runner)
        self.assertIn("EvidenceDir leaf must exactly match RunId", runner)
        self.assertIn("VID_303A&PID_1001", runner)
        self.assertIn("VID_1A86|VID_05C6|VID_1E0E", runner)
        self.assertIn("ExpectedAppSha256", runner)
        self.assertIn("CaptureTimeoutSeconds = 215", runner)
        self.assertIn("System.IO.Ports.SerialPort", runner)
        self.assertIn("Microsoft.v5.4.2.PowerShell_profile.ps1", runner)
        self.assertIn("--before default_reset --after no_reset write_flash", runner)
        self.assertIn("& $idfPython -m esptool --port $Port chip_id", runner)
        self.assertIn("Push-Location $resolvedBuildDir", runner)
        self.assertLess(runner.index("$serial.Open()"), runner.index("$serial.RtsEnable = $true"))
        self.assertLess(runner.index("$serial.DiscardInBuffer()"), runner.index("$serial.RtsEnable = $true"))
        self.assertIn("no_audio_storage = $true", runner)
        self.assertIn("AUDIO_SEQUENCE_COMPLETE", runner)
        self.assertIn("speaker_pa_off_verified=true", runner)
        self.assertNotIn("COM3", runner)
        self.assertNotIn("COM4", runner)

    def test_output_diagnostic_runner_matches_profile_and_fails_closed(self) -> None:
        runner = OUTPUT_DIAGNOSTIC_RUNNER.read_text(encoding="utf-8")

        self.assertIn("OutputDiagnosticAuthorized", runner)
        self.assertIn("build_output_diagnostic_static", runner)
        self.assertIn("CONFIG_EGOLINK_AUDIO_LOOP_AUTORUN=y", runner)
        self.assertIn("CONFIG_EGOLINK_AUDIO_OUTPUT_DIAGNOSTIC=y", runner)
        self.assertIn("VID_303A&PID_1001", runner)
        self.assertIn("VID_1A86|VID_05C6|VID_1E0E", runner)
        self.assertIn("02:00:00:00:00:01", runner)
        self.assertIn("ExpectedAppSha256", runner)
        self.assertIn("CaptureTimeoutSeconds = 45", runner)
        self.assertIn("--after',\n                'no_reset'", runner)
        self.assertLess(
            runner.index("$serial.Open()"),
            runner.index("$serial.RtsEnable = $true"),
        )
        for marker in (
            "AUDIO_OUTPUT_DIAGNOSTIC_ARMED",
            "AUDIO_OUTPUT_COUNTDOWN",
            "AUDIO_OUTPUT_STAGE_START",
            "AUDIO_OUTPUT_STAGE_END",
            "actual_bytes_written=$expectedBytesPerStage",
            "AUDIO_OUTPUT_STAGE_GAP",
            "AUDIO_OUTPUT_DIAGNOSTIC_COMPLETE",
            "mode=output_diagnostic",
        ):
            self.assertIn(marker, runner)
        self.assertIn("microphone_constructed = $false", runner)
        self.assertIn("microphone_capture_performed = $false", runner)
        self.assertIn("raw_audio_retained = $false", runner)
        self.assertIn("connectivity_board_targeted = $false", runner)
        self.assertIn("Caller must restore in a finally path", runner)
        self.assertNotIn("COM3", runner)
        self.assertNotIn("COM4", runner)


if __name__ == "__main__":
    unittest.main()

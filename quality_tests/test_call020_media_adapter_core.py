from __future__ import annotations

from pathlib import Path
import re
import struct
import unittest
import zlib

from pc_simulator.ego_call_media_io import EndpointIdentity, FrameCodec, MediaFrame


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "firmware" / "audio_loop"
SOURCE = TARGET / "main" / "call020_media_adapter_core.c"
HEADER = TARGET / "main" / "call020_media_adapter_core.h"
APP_MAIN = TARGET / "main" / "app_main.c"
MAIN_CMAKE = TARGET / "main" / "CMakeLists.txt"
KCONFIG = TARGET / "main" / "Kconfig.projbuild"
README = TARGET / "README.md"
PACKET = ROOT / "docs" / "tasks" / "active" / "CALL-020_LTE_DATA_VOICE_POC.md"


class Call020MediaAdapterCoreStaticTests(unittest.TestCase):
    def test_component_compiles_but_default_application_does_not_instantiate_it(self) -> None:
        cmake = MAIN_CMAKE.read_text(encoding="utf-8")
        kconfig = KCONFIG.read_text(encoding="utf-8")
        app_main = APP_MAIN.read_text(encoding="utf-8")

        self.assertIn('"call020_media_adapter_core.c"', cmake)
        option = re.search(
            r"config EGOLINK_CALL020_MEDIA_ADAPTER_CORE(?P<body>.*?)\nendmenu",
            kconfig,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(option)
        self.assertIn("default n", option.group("body"))
        self.assertNotIn("call020_media_adapter_core", app_main)
        self.assertNotIn("CONFIG_EGOLINK_CALL020_MEDIA_ADAPTER_CORE", app_main)

    def test_name_and_dependencies_do_not_claim_or_open_a_usb_cdc_endpoint(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        header = HEADER.read_text(encoding="utf-8")
        readme = README.read_text(encoding="utf-8")

        self.assertIn("framing/queue core only", source)
        self.assertIn("not a USB CDC endpoint", header)
        self.assertIn("USB Serial/JTAG console", readme)
        self.assertIn("unverified", readme)
        for forbidden in (
            "tinyusb.h",
            "tusb.h",
            "tinyusb_cdc_acm",
            "usb_serial_jtag_driver_install",
            "uart_driver_install",
            "esp_codec_dev_open",
            "bsp_power_amp_io",
            "gpio_set_level",
            "mqtt",
            "socket(",
            "fopen(",
        ):
            self.assertNotIn(forbidden, source.lower())

    def test_pcm_profile_and_explicit_stereo_compatibility_mapping_are_fixed(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        header = HEADER.read_text(encoding="utf-8")

        for declaration in (
            "CALL020_MEDIA_SAMPLE_RATE_HZ UINT32_C(16000)",
            "CALL020_MEDIA_FRAME_MS UINT32_C(20)",
            "CALL020_MEDIA_MONO_SAMPLES UINT32_C(320)",
            "CALL020_MEDIA_MONO_BYTES UINT32_C(640)",
            "CALL020_MEDIA_STEREO_BYTES UINT32_C(1280)",
        ):
            self.assertIn(declaration, header)
        self.assertIn("downmix_stereo_to_mono", source)
        self.assertRegex(
            source,
            r"(?s)int32_t sum = .*?stereo\[sample \* 2U\].*?"
            r"stereo\[sample \* 2U \+ 1U\].*?sum / 2",
        )
        self.assertIn("expand_mono_to_stereo", source)
        self.assertIn("stereo[sample * 2U] = value", source)
        self.assertIn("stereo[sample * 2U + 1U] = value", source)

    def test_wire_mapping_matches_call020b_header_and_crc_semantics(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        identity = EndpointIdentity(
            session_id="s",
            device_id="d",
            guardian_id="g",
            uplink_clock_id="u",
            downlink_clock_id="v",
        )
        media = bytearray((index * 13) & 0xFF for index in range(640))
        frame = MediaFrame(
            session_id=identity.session_id,
            direction="uplink",
            source_role="device",
            source_id=identity.device_id,
            target_role="guardian",
            target_id=identity.guardian_id,
            sequence=7,
            source_clock_id=identity.uplink_clock_id,
            source_time_ns=140_000_000,
            media=media,
        )
        wire = FrameCodec.encode(frame)
        try:
            header = struct.unpack("!4sBBBBQQHHHHH", wire[:34])
            self.assertEqual(
                header,
                (b"EGLM", 1, 1, 1, 2, 7, 140_000_000, 1, 1, 1, 1, 640),
            )
            self.assertEqual(
                struct.unpack("!I", wire[-4:])[0],
                zlib.crc32(wire[:-4]) & 0xFFFFFFFF,
            )
        finally:
            wire[:] = b"\x00" * len(wire)
            frame.dispose()

        for mapping in (
            "static const uint8_t CALL020_WIRE_MAGIC[4] = {'E', 'G', 'L', 'M'}",
            "CALL020_WIRE_VERSION UINT8_C(1)",
            "CALL020_DIRECTION_UPLINK UINT8_C(1)",
            "CALL020_DIRECTION_DOWNLINK UINT8_C(2)",
            "CALL020_ROLE_DEVICE UINT8_C(1)",
            "CALL020_ROLE_GUARDIAN UINT8_C(2)",
            "put_be64(&wire[8], slot->sequence)",
            "put_be64(&wire[16], slot->source_time_ns)",
            "put_be16(&wire[32], (uint16_t)CALL020_MEDIA_MONO_BYTES)",
            "put_be32(&wire[cursor], crc32(wire, cursor))",
        ):
            self.assertIn(mapping, source)

    def test_session_roles_clocks_crc_and_sequences_fail_closed(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")

        for identity in (
            "core->session_id",
            "core->guardian_id",
            "core->device_id",
            "core->downlink_clock_id",
        ):
            self.assertIn(identity, source)
        self.assertIn("wire[5] != CALL020_DIRECTION_DOWNLINK", source)
        self.assertIn("wire[6] != CALL020_ROLE_GUARDIAN", source)
        self.assertIn("wire[7] != CALL020_ROLE_DEVICE", source)
        self.assertIn("sequence != core->expected_downlink_sequence", source)
        self.assertIn("source_time_ns > INT64_MAX", source)
        self.assertIn("source_time_ns <= core->last_uplink_source_time_ns", source)
        self.assertIn("source_time_ns <= core->last_downlink_source_time_ns", source)
        self.assertIn("crc32(wire, wire_bytes - CALL020_MEDIA_WIRE_CRC_BYTES)", source)
        self.assertIn("protocol_failure(core)", source)
        self.assertIn("CALL020_MEDIA_TERMINAL_PROTOCOL", source)

    def test_one_start_per_identity_prevents_sequence_zero_reuse(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        readme = README.read_text(encoding="utf-8")

        start = re.search(
            r"esp_err_t call020_media_adapter_core_start\((?P<body>.*?)"
            r"\n}\n\nesp_err_t call020_media_adapter_core_offer_uplink_stereo",
            source,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(start)
        self.assertIn("core->state != CALL020_MEDIA_CORE_READY", start.group("body"))
        self.assertNotIn("CALL020_MEDIA_CORE_STOPPED", start.group("body"))
        self.assertIn("deinitialize and initialize with a fresh session", readme)

        stop = re.search(
            r"esp_err_t call020_media_adapter_core_stop\((?P<body>.*?)"
            r"\n}\n\nesp_err_t call020_media_adapter_core_deinit",
            source,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(stop)
        self.assertIn("was_terminal", stop.group("body"))
        self.assertIn("prior_reason", stop.group("body"))

    def test_direction_queues_are_independent_fixed_and_overflow_is_terminal(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        header = HEADER.read_text(encoding="utf-8")

        self.assertIn("CALL020_MEDIA_QUEUE_MAX_FRAMES UINT32_C(8)", header)
        self.assertIn("call020_media_queue_t uplink_queue", header)
        self.assertIn("call020_media_queue_t downlink_queue", header)
        self.assertIn(
            "core->uplink_queue.count >= core->queue_capacity_frames", source
        )
        self.assertIn(
            "core->downlink_queue.count >= core->queue_capacity_frames", source
        )
        self.assertGreaterEqual(
            source.count("CALL020_MEDIA_TERMINAL_QUEUE_OVERFLOW"), 2
        )
        self.assertGreaterEqual(source.count("metadata.queue_overflows++"), 2)

    def test_monotonic_20ms_cadence_runtime_and_frame_deadlines_are_bounded(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        header = HEADER.read_text(encoding="utf-8")

        self.assertIn("CALL020_FRAME_INTERVAL_US UINT64_C(20000)", source)
        self.assertIn("CALL020_MEDIA_MAX_RUNTIME_US UINT64_C(600000000)", header)
        self.assertIn("now_us < core->last_now_us", source)
        self.assertIn("now_us > core->runtime_deadline_us", source)
        self.assertIn("monotonic_now_us > slot->deadline_us", source)
        self.assertIn(
            "core->next_uplink_due_us, CALL020_FRAME_INTERVAL_US", source
        )
        self.assertIn(
            "core->next_downlink_due_us, CALL020_FRAME_INTERVAL_US", source
        )
        self.assertIn("call020_media_adapter_core_tick", source)

    def test_timeout_progress_is_explicit_and_only_zero_progress_is_retryable(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        header = HEADER.read_text(encoding="utf-8")

        self.assertIn("TIMEOUT_ZERO_PROGRESS", header)
        self.assertIn("TIMEOUT_PARTIAL", header)
        self.assertIn("TIMEOUT_UNKNOWN", header)
        zero_case = re.search(
            r"case CALL020_MEDIA_TRANSFER_TIMEOUT_ZERO_PROGRESS:(?P<body>.*?)"
            r"case CALL020_MEDIA_TRANSFER_TIMEOUT_PARTIAL:",
            source,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(zero_case)
        self.assertIn("return ESP_ERR_TIMEOUT", zero_case.group("body"))
        self.assertNotIn("terminate(", zero_case.group("body"))
        self.assertGreaterEqual(
            source.count("CALL020_MEDIA_TERMINAL_PARTIAL_TIMEOUT"), 2
        )
        self.assertGreaterEqual(
            source.count("CALL020_MEDIA_TERMINAL_UNKNOWN_TIMEOUT"), 2
        )

    def test_pa_fail_off_and_owned_media_zeroing_cover_terminal_stop_and_io(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")

        terminate = re.search(
            r"static esp_err_t terminate\((?P<body>.*?)\n}\n\nstatic esp_err_t check_running_time",
            source,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(terminate)
        self.assertIn("clear_owned_media(core)", terminate.group("body"))
        self.assertIn("force_pa_off(core)", terminate.group("body"))
        self.assertIn("volatile uint8_t *cursor", source)
        self.assertIn(
            "secure_zero(stereo_values, CALL020_MEDIA_STEREO_BYTES)", source
        )
        self.assertIn("secure_zero(wire, wire_bytes)", source)
        self.assertGreaterEqual(
            source.count("secure_zero(core->wire_scratch"), 3
        )
        self.assertGreaterEqual(
            source.count("secure_zero(core->stereo_scratch"), 2
        )
        stop = re.search(
            r"esp_err_t call020_media_adapter_core_stop\((?P<body>.*?)"
            r"\n}\n\nesp_err_t call020_media_adapter_core_deinit",
            source,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(stop)
        self.assertIn("clear_owned_media(core)", stop.group("body"))
        self.assertIn("force_pa_off(core)", stop.group("body"))

    def test_results_are_metadata_only_and_nonclaims_remain_explicit(self) -> None:
        header = HEADER.read_text(encoding="utf-8")
        readme = README.read_text(encoding="utf-8")
        packet = PACKET.read_text(encoding="utf-8")

        metadata = re.search(
            r"typedef struct \{\s*"
            r"call020_media_core_state_t state;(?P<body>.*?)\}\s*"
            r"call020_media_adapter_metadata_t;",
            header,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(metadata)
        for forbidden in ("media[", "wire[", "session_id", "device_id", "guardian_id"):
            self.assertNotIn(forbidden, metadata.group("body"))
        for claim in (
            "not USB CDC",
            "full-duplex audio",
            "LTE or RTC evidence",
        ):
            self.assertIn(claim, readme)
        self.assertIn("USB CDC ownership and routing therefore remain", packet)
        self.assertIn("`unverified`", packet)
        self.assertIn("unresolved USB integration choice is explicit", packet)
        self.assertIn("`P0-CALL` evidence", packet)


if __name__ == "__main__":
    unittest.main()

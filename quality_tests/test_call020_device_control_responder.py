from __future__ import annotations

import re
import unittest
import zlib
from pathlib import Path

from pc_simulator import ego_call_single_usb_phase_connector as host_wire


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "firmware/audio_loop/main"
WIRE_H = MAIN / "call020_device_control_wire.h"
WIRE_C = MAIN / "call020_device_control_wire.c"
RESPONDER_H = MAIN / "call020_device_control_responder.h"
RESPONDER_C = MAIN / "call020_device_control_responder.c"
CMAKE = MAIN / "CMakeLists.txt"
KCONFIG = MAIN / "Kconfig.projbuild"
DEFAULTS = ROOT / "firmware/audio_loop/sdkconfig.call020_operator_runner.defaults"
APP_MAIN = MAIN / "app_main.c"
BOOT_STUB = MAIN / "call020_operator_runner_boot_stub.c"
README = ROOT / "firmware/audio_loop/README.md"


class Call020DeviceControlResponderContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.wire_h = WIRE_H.read_text(encoding="utf-8")
        cls.wire_c = WIRE_C.read_text(encoding="utf-8")
        cls.header = RESPONDER_H.read_text(encoding="utf-8")
        cls.source = RESPONDER_C.read_text(encoding="utf-8")
        cls.cmake = CMAKE.read_text(encoding="utf-8")
        cls.kconfig = KCONFIG.read_text(encoding="utf-8")
        cls.defaults = DEFAULTS.read_text(encoding="utf-8")
        cls.readme = README.read_text(encoding="utf-8")

    def test_wire_contract_matches_call020p_fixed_envelope(self) -> None:
        self.assertEqual(host_wire.CONTROL_MAGIC, b"EGLC")
        self.assertEqual(host_wire.CONTROL_VERSION, 1)
        self.assertEqual(host_wire.MAX_CONTROL_PAYLOAD_BYTES, 2_048)
        for token in (
            "CALL020_CONTROL_HEADER_BYTES UINT32_C(8)",
            "CALL020_CONTROL_MAX_PAYLOAD_BYTES UINT32_C(2048)",
            "CALL020_CONTROL_MAX_FRAME_BYTES",
            'UINT8_C(\'E\'), UINT8_C(\'G\'), UINT8_C(\'L\'), UINT8_C(\'C\')',
            "UINT32_C(0xedb88320)",
            "header[4] != EGLC_VERSION",
            "frame[5] != call020_control_wire_request_type(request->action)",
            "call020_control_wire_request_frame_bytes_from_header",
        ):
            self.assertIn(token, self.wire_h + self.wire_c)
        self.assertIn("CRC32 protects framing", self.wire_h)
        self.assertIn("not authentication", self.wire_h)

    def test_request_parser_accepts_only_canonical_fixed_schema(self) -> None:
        ordered_literals = (
            '{\\\"action\\\":',
            ',\\\"operation_id\\\":',
            ',\\\"run_id\\\":',
            ',\\\"timeout_ms\\\":',
        )
        positions = [self.wire_c.index(value) for value in ordered_literals]
        self.assertEqual(positions, sorted(positions))
        for forbidden_general_parser in ("cJSON_Parse", "json_parse", "strtod"):
            self.assertNotIn(forbidden_general_parser, self.wire_c)
        self.assertIn("identifier_character", self.wire_c)
        self.assertIn("value > UINT32_C(10000)", self.wire_c)
        self.assertIn("cursor == end", self.wire_c)

    def test_response_json_is_canonical_and_host_decodable_by_schema(self) -> None:
        # These are the fixed values used by the C formatter. Encoding them
        # through the host implementation protects message numbers, key order,
        # JSON booleans and CRC convention at the cross-language boundary.
        request = {
            "action": "start",
            "operation_id": "run-1:start:1",
            "run_id": "run-1",
            "timeout_ms": 1000,
        }
        request_frame = host_wire.encode_control_frame("start_request", request)
        self.assertEqual(request_frame[:4], b"EGLC")
        self.assertEqual(
            int.from_bytes(request_frame[-4:], "big"),
            zlib.crc32(request_frame[:-4]) & 0xFFFFFFFF,
        )
        ack = {
            "accepted": True,
            "action": "start",
            "duplicate": False,
            "operation_id": "run-1:start:1",
            "run_id": "run-1",
            "state": "STARTING",
        }
        name, decoded = host_wire.decode_control_frame(
            host_wire.encode_control_frame("start_ack", ack)
        )
        self.assertEqual((name, decoded), ("start_ack", ack))
        for ordered_key in (
            '{\\"accepted\\":%s,\\"action\\":\\"%s\\",\\"duplicate\\":%s,',
            '\\"operation_id\\":\\"%s\\",\\"run_id\\":\\"%s\\",',
            '\\"state\\":\\"%s\\"}',
        ):
            self.assertIn(ordered_key, self.wire_c)

    def test_prepare_ack_contains_runtime_descriptor_and_real_prestart_shape(self) -> None:
        for token in (
            '"correlated_routing_ids\\\":true',
            '"phase\\\":\\\"pre_start\\\"',
            '"worker_stack_high_watermark_bytes\\\":[]',
            '"provenance\\\":\\\"runtime_ephemeral_generated\\\"',
            '"random_quality\\\":\\\"unverified\\\"',
            '"runner_version\\\":\\\"call020-operator-runner-v1\\\"',
            "heap_caps_get_free_size(MALLOC_CAP_INTERNAL)",
            "heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL)",
        ):
            self.assertIn(token, self.wire_c + self.source)
        self.assertNotIn("worker_stack_high_watermark_bytes\\\":[[", self.wire_c)

        capture = re.search(
            r"static bool capture_telemetry\((?P<body>.*?)"
            r"\n}\n\nstatic bool request_allowed",
            self.source,
            re.S,
        )
        self.assertIsNotNone(capture)
        capture_body = capture.group("body")
        self.assertNotIn("free_bytes == 0U", capture_body)
        self.assertNotIn("minimum_bytes == 0U", capture_body)
        self.assertIn("minimum_bytes > free_bytes", capture_body)
        self.assertIn("return true", capture_body)
        for encoder in (
            "call020_control_wire_encode_prepare_ack",
            "call020_control_wire_encode_telemetry_unavailable_ack",
        ):
            encoder_body = re.search(
                rf"{encoder}\((?P<body>.*?)(?:\n}}\n\n|\Z)",
                self.wire_c,
                re.S,
            )
            self.assertIsNotNone(encoder_body)
            self.assertNotIn(
                "telemetry->free_internal_heap_bytes == 0U",
                encoder_body.group("body"),
            )
            self.assertNotIn(
                "telemetry->minimum_free_internal_heap_bytes == 0U",
                encoder_body.group("body"),
            )

    def test_default_off_inert_link_profile_and_exclusive_console(self) -> None:
        self.assertIn('"call020_device_control_wire.c"', self.cmake)
        self.assertIn('"call020_device_control_responder.c"', self.cmake)
        self.assertIn(
            "-u call020_device_control_responder_retained_entry", self.cmake
        )
        block = re.search(
            r"config EGOLINK_CALL020_DEVICE_CONTROL_RESPONDER(?P<body>.*?)endmenu",
            self.kconfig,
            re.S,
        )
        self.assertIsNotNone(block)
        self.assertIn("default n", block.group("body"))
        self.assertIn("depends on EGOLINK_CALL020_OPERATOR_RUNNER", block.group("body"))
        self.assertIn("depends on ESP_CONSOLE_NONE", block.group("body"))
        self.assertIn("depends on LOG_DEFAULT_LEVEL_NONE", block.group("body"))
        self.assertIn(
            "CONFIG_EGOLINK_CALL020_DEVICE_CONTROL_RESPONDER=y", self.defaults
        )
        for token in (
            "CONFIG_ESP_CONSOLE_NONE=y",
            "CONFIG_ESP_CONSOLE_SECONDARY_NONE=y",
            "CONFIG_LOG_DEFAULT_LEVEL_NONE=y",
            "CONFIG_BOOTLOADER_LOG_LEVEL_NONE=y",
        ):
            self.assertIn(token, self.defaults)
        self.assertNotIn(
            "call020_device_control_responder", APP_MAIN.read_text(encoding="utf-8")
        )
        self.assertNotIn(
            "call020_device_control_responder", BOOT_STUB.read_text(encoding="utf-8")
        )

    def test_single_owner_same_core_and_registered_lease_only(self) -> None:
        for token in (
            "call020_usb_driver_lease_install(",
            "call020_usb_driver_lease_begin_media_handoff(",
            "call020_operator_runner_start_with_usb_driver_lease(",
            "xPortGetCoreID() == internal->metadata.owner_core_id",
            "CALL020_DEVICE_CONTROL_TERMINAL_WRONG_CORE",
        ):
            self.assertIn(token, self.source)
        self.assertNotIn("usb_serial_jtag_driver_install", self.source)
        self.assertNotIn("usb_serial_jtag_driver_uninstall", self.source)

    def test_failed_install_retains_and_attempts_cleanup_of_initialized_lease(self) -> None:
        open_control = re.search(
            r"call020_device_control_responder_open_control\((?P<body>.*?)"
            r"\n}\n\ncall020_device_control_serve_result_t",
            self.source,
            re.S,
        )
        self.assertIsNotNone(open_control)
        body = open_control.group("body")
        install = body.index("call020_usb_driver_lease_install(")
        retain = body.index(
            "lease_cleanup_required = internal->lease.initialized", install
        )
        inspect = body.index("call020_usb_driver_lease_get_metadata(", retain)
        failure = body.index("if (result != ESP_OK)", inspect)
        cleanup = body.index("local_cleanup(internal)", failure)
        self.assertLess(install, retain)
        self.assertLess(retain, inspect)
        self.assertLess(inspect, failure)
        self.assertLess(failure, cleanup)

        local_cleanup = re.search(
            r"static esp_err_t local_cleanup\((?P<body>.*?)"
            r"\n}\n\nconst char \*call020_device_control_responder_version",
            self.source,
            re.S,
        )
        self.assertIsNotNone(local_cleanup)
        self.assertIn(
            "if (internal->lease_cleanup_required)",
            local_cleanup.group("body"),
        )

    def test_prepare_ownership_is_recorded_before_telemetry_can_fail(self) -> None:
        prepare = re.search(
            r"static esp_err_t prepare_new_operation\((?P<body>.*?)"
            r"\n}\n\nstatic call020_control_wire_result_t encode_cached_response",
            self.source,
            re.S,
        )
        self.assertIsNotNone(prepare)
        body = prepare.group("body")
        runner = body.index("call020_operator_runner_prepare(")
        owned = body.index("internal->runner_prepared = true", runner)
        telemetry = body.index("capture_telemetry(&entry->telemetry)", owned)
        self.assertLess(runner, owned)
        self.assertLess(owned, telemetry)

    def test_expired_complete_frame_and_late_runner_callbacks_fail_closed(self) -> None:
        serve = re.search(
            r"call020_device_control_responder_serve_once\((?P<body>.*?)"
            r"\n}\n\nesp_err_t call020_device_control_responder_abort_local",
            self.source,
            re.S,
        )
        self.assertIsNotNone(serve)
        serve_body = serve.group("body")
        decode = serve_body.index("call020_control_wire_decode_request(")
        expired_frame = serve_body.index(
            "if (!operation_budget_available(operation_deadline_us))", decode
        )
        bind = serve_body.index("if (!bind_run(internal, &request))", expired_frame)
        self.assertLess(expired_frame, bind)
        self.assertIn(
            "CALL020_DEVICE_CONTROL_TERMINAL_OPERATION_DEADLINE", self.header
        )

        prepare = re.search(
            r"static esp_err_t prepare_new_operation\((?P<body>.*?)"
            r"\n}\n\nstatic call020_control_wire_result_t encode_cached_response",
            self.source,
            re.S,
        )
        self.assertIsNotNone(prepare)
        prepare_body = prepare.group("body")
        for callback in (
            "call020_operator_runner_prepare(",
            "call020_operator_runner_cancel()",
            "call020_operator_runner_join()",
            "call020_operator_runner_close()",
        ):
            at = prepare_body.index(callback)
            before = prepare_body.rfind("operation_budget_available", 0, at)
            after = prepare_body.index(
                "operation_completed_within_deadline", at
            )
            self.assertGreater(before, -1)
            self.assertGreater(after, at)

        start_ack = serve_body.index("start_ack_fully_transmitted = true")
        handoff = serve_body.index(
            "call020_usb_driver_lease_begin_media_handoff(", start_ack
        )
        runner_start = serve_body.index(
            "call020_operator_runner_start_with_usb_driver_lease(", handoff
        )
        self.assertGreater(
            serve_body.rfind("operation_budget_available", start_ack, handoff),
            start_ack,
        )
        self.assertGreater(
            serve_body.index("operation_completed_within_deadline", handoff),
            handoff,
        )
        self.assertGreater(
            serve_body.rfind(
                "operation_budget_available", handoff, runner_start
            ),
            handoff,
        )
        self.assertGreater(
            serve_body.index(
                "operation_completed_within_deadline", runner_start
            ),
            runner_start,
        )
        self.assertIn("latch_operation_deadline(internal, result, true)", serve_body)

    def test_operation_budget_starts_after_complete_valid_frame(self) -> None:
        serve = re.search(
            r"call020_device_control_responder_serve_once\((?P<body>.*?)"
            r"\n}\n\nesp_err_t call020_device_control_responder_abort_local",
            self.source,
            re.S,
        )
        self.assertIsNotNone(serve)
        body = serve.group("body")
        acquisition = body.index(
            "started_us,\n            internal->config.frame_wait_timeout_ms"
        )
        decode = body.index("call020_control_wire_decode_request(", acquisition)
        accepted = body.index("now_us(&request_accepted_us)", decode)
        operation = body.index(
            "request_accepted_us,\n            request.timeout_ms", accepted
        )
        self.assertLess(acquisition, decode)
        self.assertLess(decode, accepted)
        self.assertLess(accepted, operation)
        self.assertNotIn("started_us, request.timeout_ms", body)
        self.assertNotRegex(
            body,
            r"started_us\s*,\s*request\.timeout_ms",
        )

        # A request accepted 900 ms into a 1000-ms acquisition wait still gets
        # its declared 1000-ms device-operation budget.  Host total timeout is
        # independent and is intentionally outside this device-side model.
        serve_started_us = 0
        request_accepted_us = 900_000
        timeout_us = 1_000_000
        self.assertEqual(request_accepted_us + timeout_us, 1_900_000)
        self.assertNotEqual(serve_started_us + timeout_us, 1_900_000)

    def test_start_ack_is_last_control_write_before_irreversible_handoff(self) -> None:
        serve = re.search(
            r"call020_device_control_responder_serve_once\((?P<body>.*?)"
            r"\n}\n\nesp_err_t call020_device_control_responder_abort_local",
            self.source,
            re.S,
        )
        self.assertIsNotNone(serve)
        body = serve.group("body")
        write_at = body.index("write_exact_and_drain(")
        ack_at = body.index("start_ack_fully_transmitted = true")
        disable_at = body.index("control_writes_permanently_disabled = true", ack_at)
        handoff_at = body.index("call020_usb_driver_lease_begin_media_handoff(")
        start_at = body.index(
            "call020_operator_runner_start_with_usb_driver_lease(", handoff_at
        )
        self.assertLess(write_at, ack_at)
        self.assertLess(ack_at, disable_at)
        self.assertLess(disable_at, handoff_at)
        self.assertLess(handoff_at, start_at)
        self.assertNotIn("write_exact_and_drain(", body[start_at:])
        self.assertNotIn("usb_serial_jtag_write_bytes", body[start_at:])

    def test_partial_progress_is_terminal_and_only_zero_progress_retries(self) -> None:
        self.assertIn("TRANSFER_ZERO_PROGRESS", self.source)
        self.assertIn("TRANSFER_PARTIAL", self.source)
        self.assertIn("TRANSFER_UNKNOWN", self.source)
        self.assertIn(
            "CALL020_DEVICE_CONTROL_SERVE_RETRYABLE_ZERO_PROGRESS", self.source
        )
        self.assertIn(
            "CALL020_DEVICE_CONTROL_TERMINAL_WRITE_PARTIAL_OR_UNKNOWN", self.source
        )
        self.assertIn(
            "CALL020_DEVICE_CONTROL_TERMINAL_READ_PARTIAL_OR_UNKNOWN", self.source
        )

    def test_sub_tick_budget_uses_zero_tick_poll_without_extending_deadline(self) -> None:
        bounded = re.search(
            r"static TickType_t bounded_ticks\((?P<body>.*?)"
            r"\n}\n\nstatic void clear_io_buffers",
            self.source,
            re.S,
        )
        self.assertIsNotNone(bounded)
        body = bounded.group("body")
        self.assertIn(
            "(wait_us * (uint64_t)configTICK_RATE_HZ) / UINT64_C(1000000)",
            body,
        )
        self.assertNotIn("UINT64_C(999999)", body)
        self.assertNotRegex(body, r"if \(ticks == 0U\).*?ticks = 1U")
        self.assertIn("zero-tick poll is intentional", body)

        # A 999-us remainder at a 1-kHz tick rate must remain a nonblocking
        # poll; ceiling it to one tick would exceed the monotonic budget.
        remaining_us = 999
        tick_rate_hz = 1_000
        self.assertEqual((remaining_us * tick_rate_hz) // 1_000_000, 0)

    def test_final_read_that_crosses_deadline_is_never_accepted(self) -> None:
        read_exact = re.search(
            r"static control_transfer_result_t read_exact\((?P<body>.*?)"
            r"\n}\n\nstatic control_transfer_result_t write_exact_and_drain",
            self.source,
            re.S,
        )
        self.assertIsNotNone(read_exact)
        body = read_exact.group("body")
        driver_return = body.index("usb_serial_jtag_read_bytes(")
        account_progress = body.index("*transferred += (size_t)count", driver_return)
        observe_completion = body.index("now_us(&completed_us)", account_progress)
        reject_late = body.index("completed_us > deadline_us", observe_completion)
        success = body.rindex("return TRANSFER_OK")
        self.assertLess(driver_return, account_progress)
        self.assertLess(account_progress, observe_completion)
        self.assertLess(observe_completion, reject_late)
        self.assertLess(reject_late, success)
        self.assertIn("TRANSFER_PARTIAL", body[reject_late:success])

        # Model the pinned branch: even a final complete read is partial when
        # its post-call timestamp is one microsecond beyond the deadline.
        bytes_requested = 8
        transferred = 0 + bytes_requested
        completed_us, deadline_us = 1_001, 1_000
        result = "partial" if completed_us > deadline_us and transferred else "ok"
        self.assertEqual(result, "partial")

    def test_final_write_and_drain_crossing_deadline_cannot_handoff(self) -> None:
        write = re.search(
            r"static control_transfer_result_t write_exact_and_drain\("
            r"(?P<body>.*?)\n}\n\nstatic operation_cache_entry_t \*find_operation",
            self.source,
            re.S,
        )
        self.assertIsNotNone(write)
        body = write.group("body")
        driver_return = body.index("usb_serial_jtag_write_bytes(")
        account_progress = body.index("*transferred += (size_t)count", driver_return)
        write_completion = body.index("now_us(&completed_us)", account_progress)
        write_late = body.index("completed_us > deadline_us", write_completion)
        drain = body.index("usb_serial_jtag_wait_tx_done(", write_late)
        drain_completion = body.index("now_us(&completed_us)", drain)
        drain_late = body.index("completed_us > deadline_us", drain_completion)
        success = body.rindex("return TRANSFER_OK")
        self.assertLess(write_late, drain)
        self.assertLess(drain, drain_completion)
        self.assertLess(drain_completion, drain_late)
        self.assertLess(drain_late, success)

        serve = re.search(
            r"call020_device_control_responder_serve_once\((?P<body>.*?)"
            r"\n}\n\nesp_err_t call020_device_control_responder_abort_local",
            self.source,
            re.S,
        )
        self.assertIsNotNone(serve)
        serve_body = serve.group("body")
        transfer_ok = serve_body.index("if (write_result != TRANSFER_OK)")
        ack_complete = serve_body.index("start_ack_fully_transmitted = true")
        handoff = serve_body.index("call020_usb_driver_lease_begin_media_handoff(")
        self.assertLess(transfer_ok, ack_complete)
        self.assertLess(ack_complete, handoff)

        # A full write whose drain reports success after the deadline is still
        # unknown and therefore cannot reach the ACK-complete/handoff branch.
        drain_status = "ESP_OK"
        completed_us, deadline_us = 2_001, 2_000
        result = (
            "unknown"
            if drain_status == "ESP_OK" and completed_us > deadline_us
            else "ok"
        )
        self.assertEqual(result, "unknown")

    def test_idempotency_binds_full_fingerprint_and_capacity(self) -> None:
        find = re.search(
            r"static operation_cache_entry_t \*find_operation\((?P<body>.*?)"
            r"\n}\n\nstatic bool bind_run",
            self.source,
            re.S,
        )
        self.assertIsNotNone(find)
        body = find.group("body")
        for token in (
            "entry->operation_id",
            "entry->action != request->action",
            "entry->timeout_ms != request->timeout_ms",
            "entry->run_id, request->run_id",
            "CALL020_DEVICE_CONTROL_MAX_OPERATION_CACHE",
            "index + UINT32_C(1) != internal->operation_count",
        ):
            self.assertIn(token, body)
        self.assertIn(
            "CALL020_DEVICE_CONTROL_MAX_OPERATION_CACHE UINT32_C(16)", self.header
        )

    def test_only_adjacent_lost_ack_replay_survives_newer_operation(self) -> None:
        find = re.search(
            r"static operation_cache_entry_t \*find_operation\((?P<body>.*?)"
            r"\n}\n\nstatic bool bind_run",
            self.source,
            re.S,
        )
        self.assertIsNotNone(find)
        body = find.group("body")
        stale_guard = body.index(
            "index + UINT32_C(1) != internal->operation_count"
        )
        duplicate_accept = body.index("*duplicate = true", stale_guard)
        self.assertLess(stale_guard, duplicate_accept)

        prepare = ("run-1", "run-1:prepare:1", "prepare", 1_000)
        start = ("run-1", "run-1:start:1", "start", 1_000)
        operations = [prepare]
        self.assertEqual(operations.index(prepare) + 1, len(operations))
        operations.append(start)
        self.assertNotEqual(operations.index(prepare) + 1, len(operations))
        self.assertEqual(operations.index(start) + 1, len(operations))

        serve = re.search(
            r"call020_device_control_responder_serve_once\((?P<body>.*?)"
            r"\n}\n\nesp_err_t call020_device_control_responder_abort_local",
            self.source,
            re.S,
        )
        self.assertIsNotNone(serve)
        serve_body = serve.group("body")
        zero_progress = serve_body.index(
            "if (write_result == TRANSFER_ZERO_PROGRESS)"
        )
        retry_return = serve_body.index(
            "CALL020_DEVICE_CONTROL_SERVE_RETRYABLE_ZERO_PROGRESS",
            zero_progress,
        )
        start_dispatch = serve_body.index(
            "if (request.action == CALL020_CONTROL_ACTION_START)", retry_return
        )
        close_dispatch = serve_body.index(
            "if (request.action == CALL020_CONTROL_ACTION_CLOSE)", start_dispatch
        )
        self.assertLess(retry_return, start_dispatch)
        self.assertLess(retry_return, close_dispatch)
        self.assertNotIn(
            "clear_control_identities", serve_body[zero_progress:retry_return]
        )

    def test_header_is_validated_before_declared_remainder_read(self) -> None:
        serve = re.search(
            r"call020_device_control_responder_serve_once\((?P<body>.*?)"
            r"\n}\n\nesp_err_t call020_device_control_responder_abort_local",
            self.source,
            re.S,
        )
        self.assertIsNotNone(serve)
        body = serve.group("body")
        first_read = body.index("read_exact(")
        header_check = body.index(
            "call020_control_wire_request_frame_bytes_from_header("
        )
        second_read = body.index("read_exact(", first_read + 1)
        self.assertLess(first_read, header_check)
        self.assertLess(header_check, second_read)

    def test_post_stop_telemetry_and_result_remain_honestly_disabled(self) -> None:
        for token in (
            '"accepted\\\":false',
            '"phase\\\":\\\"post_stop\\\"',
            '"worker_stack_high_watermark_bytes\\\":[]',
            "CALL020_DEVICE_CONTROL_TERMINAL_POST_STOP_TELEMETRY_UNAVAILABLE",
            "result_phase_enabled == false",
            "remote_cleanup_acknowledged_after_media = false",
            "device_runtime_termination_proven = false",
        ):
            self.assertIn(token, self.wire_c + self.source)
        self.assertIn("RESULT", self.readme)
        self.assertIn("disabled/unverified", self.readme)

    def test_local_close_boundary_measurement_propagates_once_without_result(
        self,
    ) -> None:
        retain = re.search(
            r"static void retain_close_boundary_measurement\((?P<body>.*?)"
            r"\n}\n\nstatic const responder_internal_t",
            self.source,
            re.S,
        )
        self.assertIsNotNone(retain)
        body = retain.group("body")
        self.assertIn("!internal->metadata.close_boundary_measurement.valid", body)
        self.assertIn("runner->close_boundary_measurement.valid", body)
        self.assertIn("runner->close_boundary_measurement", body)

        finish = re.search(
            r"call020_device_control_responder_finish_media_local\("
            r"(?P<body>.*?)\n}\n\nesp_err_t "
            r"call020_device_control_responder_get_metadata",
            self.source,
            re.S,
        )
        self.assertIsNotNone(finish)
        finish_body = finish.group("body")
        close_at = finish_body.index("call020_operator_runner_close()")
        metadata_at = finish_body.index(
            "call020_operator_runner_get_metadata(", close_at
        )
        retain_at = finish_body.index("retain_close_boundary_measurement", metadata_at)
        self.assertLess(close_at, metadata_at)
        self.assertLess(metadata_at, retain_at)
        self.assertIn("close_boundary_measurement", self.header)
        self.assertIn("post_stop_telemetry_supported = false", self.source)
        self.assertIn("result_phase_enabled = false", self.source)
        self.assertNotIn("RESULT_READY", self.wire_h + self.wire_c + self.source)

    def test_no_logging_recording_network_or_identifier_metadata(self) -> None:
        lowered = self.source.lower()
        for forbidden in (
            "esp_log",
            "printf(",
            "fopen(",
            "socket(",
            "connect(",
            "mqtt",
            "http",
        ):
            self.assertNotIn(forbidden, lowered)
        metadata = re.search(
            r"typedef struct \{(?P<body>.*?)"
            r"\} call020_device_control_responder_metadata_t;",
            self.header,
            re.S,
        )
        self.assertIsNotNone(metadata)
        for forbidden in ("run_id[", "operation_id[", "session_id[", "payload["):
            self.assertNotIn(forbidden, metadata.group("body"))
        self.assertIn("raw_audio_logged_or_persisted = false", self.source)
        self.assertIn("identifiers_or_payload_logged = false", self.source)


if __name__ == "__main__":
    unittest.main()

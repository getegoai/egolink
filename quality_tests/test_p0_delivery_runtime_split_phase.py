"""Focused OUTBOX-010H checks for split-phase delivery and SOS preemption.

The C harness is compiled and linked against the actual runtime with an
offline dispatcher double.  The available Xtensa toolchain cannot execute a
host binary, so this suite labels that limitation explicitly; source-level
checks still pin the state-machine and ownership boundaries.  No network,
storage, GPIO, task, modem or hardware operation is performed.
"""

from __future__ import annotations

from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from quality_tests.test_p0_delivery_runtime import (
    COMPONENT,
    HARNESS,
    HEADER,
    PACKET,
    SOURCE,
    _esp_toolchain,
    _function_body,
    _include_paths,
)


def _split_harness() -> str:
    harness = HARNESS.replace(
        "static bool captured_error_present;",
        "static bool captured_error_present;\n"
        "static const char *captured_error_code;",
        1,
    )
    harness = harness.replace(
        "captured_error_present = transport_error_code != NULL;",
        "captured_error_present = transport_error_code != NULL;\n"
        "    captured_error_code = transport_error_code;",
        1,
    )
    callback_extension = r"""
    if (callback_mode == 6U) {
        CHECK(request->cancel_requested != NULL, 81U);
        CHECK(request->cancel_context == &runtime_object, 82U);
        CHECK(request->transfer_generation != UINT32_C(0), 83U);
        CHECK(
            egolink_p0_delivery_runtime_signal_durable_sos(&runtime_object) ==
                EGOLINK_P0_DELIVERY_SOS_PREEMPT_REQUESTED,
            84U);
        CHECK(
            request->cancel_requested(
                request->cancel_context, request->transfer_generation),
            85U);
        CHECK(
            egolink_p0_delivery_runtime_cancel(
                &runtime_object, callback_begin_time, &nested_result) ==
                EGOLINK_P0_DELIVERY_REENTRANT_CALL,
            86U);
        CHECK(
            egolink_p0_delivery_runtime_close(
                &runtime_object, callback_begin_time, &nested_result) ==
                EGOLINK_P0_DELIVERY_REENTRANT_CALL,
            87U);
        result->completion_time_ms = callback_begin_time + UINT64_C(1);
        return EGOLINK_P0_DELIVERY_POST_CANCELLED;
    }
    if (callback_mode == 7U) {
        CHECK(
            egolink_p0_delivery_runtime_signal_durable_sos(&runtime_object) ==
                EGOLINK_P0_DELIVERY_SOS_PREEMPT_REQUESTED,
            88U);
        request->response[0] = (uint8_t)'{';
        request->response[1] = (uint8_t)'}';
        result->http_status_code = UINT16_C(200);
        result->response_length = 2U;
        result->completion_time_ms = callback_begin_time + UINT64_C(1);
        return EGOLINK_P0_DELIVERY_POST_HTTP_RESPONSE;
    }
"""
    marker = "    return EGOLINK_P0_DELIVERY_POST_CALLBACK_FAILED;\n}"
    if harness.count(marker) != 1:
        raise AssertionError("legacy callback insertion marker drifted")
    harness = harness.replace(marker, callback_extension + marker, 1)

    split_checks = r"""

    begin_recovery_mode = 0U;
    control_must_recover = 0U;
    cancel_returns_retained = 0U;
    finish_recoveries = 0U;

    /* Cancellation already requested before execute: no POST was entered. */
    selected_route = EGOLINK_P0_OUTBOX_ROUTE_LOCATION_STATE;
    callback_mode = 1U;
    callback_begin_time = UINT64_C(2000);
    const unsigned int before_prepare_begin = begin_calls;
    const unsigned int before_prepare_post = post_calls;
    const unsigned int before_prepare_finish = finish_calls;
    CHECK(
        egolink_p0_delivery_runtime_prepare(
            &runtime_object, callback_begin_time, &runtime_result) ==
                EGOLINK_P0_DELIVERY_PREPARED,
        89U);
    CHECK(runtime_result.begin_called, 90U);
    CHECK(runtime_result.prepared_snapshot_available, 91U);
    CHECK(begin_calls == before_prepare_begin + 1U, 92U);
    CHECK(post_calls == before_prepare_post, 93U);
    CHECK(finish_calls == before_prepare_finish, 94U);
    const uint32_t first_generation = runtime_result.transfer_generation;
    CHECK(first_generation != UINT32_C(0), 95U);
    CHECK(
        egolink_p0_delivery_runtime_signal_durable_sos(&runtime_object) ==
            EGOLINK_P0_DELIVERY_SOS_PREEMPT_REQUESTED,
        96U);
    CHECK(
        egolink_p0_delivery_runtime_signal_durable_sos(&runtime_object) ==
            EGOLINK_P0_DELIVERY_SOS_PREEMPT_ALREADY_REQUESTED,
        97U);
    CHECK(
        egolink_p0_delivery_runtime_execute_prepared(
            &runtime_object, &runtime_result) ==
                EGOLINK_P0_DELIVERY_TRANSPORT_RESULT_READY,
        98U);
    CHECK(!runtime_result.post_called, 99U);
    CHECK(runtime_result.durable_sos_preemption_won, 100U);
    CHECK(!runtime_result.transport_acceptance_may_be_unknown, 101U);
    CHECK(!runtime_result.late_transport_result_discarded, 102U);
    const unsigned int before_guard_cancel = cancel_calls;
    const unsigned int before_guard_close = close_calls;
    CHECK(
        egolink_p0_delivery_runtime_cancel(
            &runtime_object, UINT64_C(2001), &nested_result) ==
                EGOLINK_P0_DELIVERY_TRANSPORT_RESULT_READY,
        103U);
    CHECK(
        egolink_p0_delivery_runtime_close(
            &runtime_object, UINT64_C(2001), &nested_result) ==
                EGOLINK_P0_DELIVERY_TRANSPORT_RESULT_READY,
        104U);
    CHECK(cancel_calls == before_guard_cancel, 105U);
    CHECK(close_calls == before_guard_close, 106U);
    CHECK(
        egolink_p0_delivery_runtime_settle_prepared(
            &runtime_object, UINT64_C(2001), &runtime_result) ==
                EGOLINK_P0_DELIVERY_ATTEMPT_RETAINED,
        107U);
    CHECK(finish_calls == before_prepare_finish + 1U, 108U);
    CHECK(captured_http_status == UINT16_C(0), 109U);
    CHECK(captured_error_code != NULL, 110U);
    CHECK(strcmp(captured_error_code, "P0_DELIVERY_CANCELLED") == 0, 111U);
    CHECK(cancel_calls == before_guard_cancel, 112U);

    /* Existing priority selector can immediately expose the durable SOS. */
    selected_route = EGOLINK_P0_OUTBOX_ROUTE_MANUAL_SOS;
    callback_mode = 1U;
    callback_begin_time = UINT64_C(2100);
    CHECK(
        egolink_p0_delivery_runtime_prepare(
            &runtime_object, callback_begin_time, &runtime_result) ==
                EGOLINK_P0_DELIVERY_PREPARED,
        113U);
    CHECK(runtime_result.route == EGOLINK_P0_OUTBOX_ROUTE_MANUAL_SOS, 114U);
    CHECK(runtime_result.transfer_generation != first_generation, 115U);
    CHECK(
        !egolink_p0_delivery_runtime_location_cancel_requested(
            &runtime_object, first_generation),
        116U);
    CHECK(
        egolink_p0_delivery_runtime_signal_durable_sos(&runtime_object) ==
            EGOLINK_P0_DELIVERY_SOS_PREEMPT_ROUTE_NOT_CANCELLABLE,
        117U);
    CHECK(
        egolink_p0_delivery_runtime_execute_prepared(
            &runtime_object, &runtime_result) ==
                EGOLINK_P0_DELIVERY_TRANSPORT_RESULT_READY,
        118U);
    CHECK(runtime_result.post_called, 119U);
    CHECK(!runtime_result.durable_sos_preemption_won, 120U);
    CHECK(
        egolink_p0_delivery_runtime_settle_prepared(
            &runtime_object, UINT64_C(2101), &runtime_result) ==
                EGOLINK_P0_DELIVERY_ATTEMPT_RETAINED,
        121U);

    /* Cooperative callback observes cancellation; acceptance stays unknown. */
    selected_route = EGOLINK_P0_OUTBOX_ROUTE_LOCATION_STATE;
    callback_mode = 6U;
    callback_begin_time = UINT64_C(2200);
    CHECK(
        egolink_p0_delivery_runtime_prepare(
            &runtime_object, callback_begin_time, &runtime_result) ==
                EGOLINK_P0_DELIVERY_PREPARED,
        122U);
    CHECK(
        egolink_p0_delivery_runtime_execute_prepared(
            &runtime_object, &runtime_result) ==
                EGOLINK_P0_DELIVERY_TRANSPORT_RESULT_READY,
        123U);
    CHECK(runtime_result.post_called, 124U);
    CHECK(runtime_result.durable_sos_preemption_won, 125U);
    CHECK(runtime_result.transport_acceptance_may_be_unknown, 126U);
    CHECK(!runtime_result.late_transport_result_discarded, 127U);
    CHECK(
        egolink_p0_delivery_runtime_settle_prepared(
            &runtime_object, UINT64_C(2201), &runtime_result) ==
                EGOLINK_P0_DELIVERY_ATTEMPT_RETAINED,
        128U);
    CHECK(strcmp(captured_error_code, "P0_DELIVERY_CANCELLED") == 0, 129U);

    /* A non-cooperative callback is not interrupted; its late ACK is ignored. */
    callback_mode = 7U;
    callback_begin_time = UINT64_C(2300);
    CHECK(
        egolink_p0_delivery_runtime_prepare(
            &runtime_object, callback_begin_time, &runtime_result) ==
                EGOLINK_P0_DELIVERY_PREPARED,
        130U);
    CHECK(
        egolink_p0_delivery_runtime_execute_prepared(
            &runtime_object, &runtime_result) ==
                EGOLINK_P0_DELIVERY_TRANSPORT_RESULT_READY,
        131U);
    CHECK(runtime_result.post_called, 132U);
    CHECK(runtime_result.transport_acceptance_may_be_unknown, 133U);
    CHECK(runtime_result.late_transport_result_discarded, 134U);
    CHECK(runtime_result.http_status_code == UINT16_C(0), 135U);
    CHECK(runtime_result.response_length == 0U, 136U);
    CHECK(
        egolink_p0_delivery_runtime_settle_prepared(
            &runtime_object, UINT64_C(2301), &runtime_result) ==
                EGOLINK_P0_DELIVERY_ATTEMPT_RETAINED,
        137U);
    CHECK(captured_http_status == UINT16_C(0), 138U);

    /* The transport-result CAS can win; a later SOS preserves the real ACK. */
    callback_mode = 1U;
    callback_begin_time = UINT64_C(2400);
    CHECK(
        egolink_p0_delivery_runtime_prepare(
            &runtime_object, callback_begin_time, &runtime_result) ==
                EGOLINK_P0_DELIVERY_PREPARED,
        139U);
    CHECK(
        egolink_p0_delivery_runtime_execute_prepared(
            &runtime_object, &runtime_result) ==
                EGOLINK_P0_DELIVERY_TRANSPORT_RESULT_READY,
        140U);
    CHECK(
        egolink_p0_delivery_runtime_signal_durable_sos(&runtime_object) ==
            EGOLINK_P0_DELIVERY_SOS_PREEMPT_RESULT_ALREADY_READY,
        141U);
    CHECK(runtime_result.http_status_code == UINT16_C(200), 142U);
    CHECK(!runtime_result.durable_sos_preemption_won, 143U);
    CHECK(!runtime_result.transport_acceptance_may_be_unknown, 144U);
    CHECK(
        egolink_p0_delivery_runtime_settle_prepared(
            &runtime_object, UINT64_C(2401), &runtime_result) ==
                EGOLINK_P0_DELIVERY_ATTEMPT_RETAINED,
        145U);
    CHECK(captured_http_status == UINT16_C(200), 146U);
    CHECK(!captured_error_present, 147U);

    /* A finish storage failure retains settlement and never re-POSTs. */
    callback_mode = 1U;
    callback_begin_time = UINT64_C(2500);
    CHECK(
        egolink_p0_delivery_runtime_prepare(
            &runtime_object, callback_begin_time, &runtime_result) ==
                EGOLINK_P0_DELIVERY_PREPARED,
        148U);
    CHECK(
        egolink_p0_delivery_runtime_execute_prepared(
            &runtime_object, &runtime_result) ==
                EGOLINK_P0_DELIVERY_TRANSPORT_RESULT_READY,
        149U);
    const unsigned int post_before_recovery = post_calls;
    finish_recoveries = 1U;
    CHECK(
        egolink_p0_delivery_runtime_settle_prepared(
            &runtime_object, UINT64_C(2501), &runtime_result) ==
                EGOLINK_P0_DELIVERY_FINISH_RECOVERY_REQUIRED,
        150U);
    CHECK(
        egolink_p0_delivery_runtime_retry_finish(
            &runtime_object, UINT64_C(2502), &runtime_result) ==
                EGOLINK_P0_DELIVERY_ATTEMPT_RETAINED,
        151U);
    CHECK(post_calls == post_before_recovery, 152U);

    egolink_p0_delivery_runtime_snapshot_t split_snapshot;
    CHECK(
        egolink_p0_delivery_runtime_current_status(
            &runtime_object, &split_snapshot) == EGOLINK_P0_DELIVERY_OK,
        153U);
    CHECK(split_snapshot.prepared_calls >= UINT64_C(6), 154U);
    CHECK(split_snapshot.execute_prepared_calls >= UINT64_C(6), 155U);
    CHECK(split_snapshot.settle_prepared_calls >= UINT64_C(6), 156U);
    CHECK(split_snapshot.durable_sos_preemption_wins >= UINT32_C(3), 157U);
    CHECK(
        egolink_p0_delivery_runtime_signal_durable_sos(&runtime_object) ==
            EGOLINK_P0_DELIVERY_SOS_PREEMPT_NO_ACTIVE_LOCATION,
        158U);

    /* Split APIs stay dormant under the default-off configuration. */
    (void)memset(&runtime_object, 0, sizeof(runtime_object));
    egolink_p0_delivery_runtime_config_t split_disabled;
    egolink_p0_delivery_runtime_default_config(&split_disabled);
    CHECK(
        egolink_p0_delivery_runtime_init(
            &runtime_object, &split_disabled, NULL) ==
                EGOLINK_P0_DELIVERY_DISABLED_STATUS,
        159U);
    CHECK(
        egolink_p0_delivery_runtime_prepare(
            &runtime_object, UINT64_C(2600), &runtime_result) ==
                EGOLINK_P0_DELIVERY_DISABLED_STATUS,
        160U);
    CHECK(
        egolink_p0_delivery_runtime_execute_prepared(
            &runtime_object, &runtime_result) ==
                EGOLINK_P0_DELIVERY_DISABLED_STATUS,
        161U);
    CHECK(
        egolink_p0_delivery_runtime_settle_prepared(
            &runtime_object, UINT64_C(2600), &runtime_result) ==
                EGOLINK_P0_DELIVERY_DISABLED_STATUS,
        162U);
"""
    marker = "    return (int)failure;\n}"
    if harness.count(marker) != 1:
        raise AssertionError("legacy main insertion marker drifted")
    return harness.replace(marker, split_checks + marker, 1)


class P0DeliveryRuntimeSplitPhaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.header = HEADER.read_text(encoding="utf-8")
        cls.packet = PACKET.read_text(encoding="utf-8")

    def test_split_api_is_additive_and_owner_boundary_is_explicit(self) -> None:
        prose = " ".join(self.header.split())
        for function in (
            "egolink_p0_delivery_runtime_prepare(",
            "egolink_p0_delivery_runtime_execute_prepared(",
            "egolink_p0_delivery_runtime_settle_prepared(",
            "egolink_p0_delivery_runtime_signal_durable_sos(",
            "egolink_p0_delivery_runtime_location_cancel_requested(",
            "egolink_p0_delivery_runtime_drive_once(",
        ):
            self.assertIn(function, self.header)
            self.assertIn(function, self.source)
        self.assertIn("prepare and settle_prepared must run under", prose)
        self.assertIn("execute_prepared must run without that shared owner held", prose)
        self.assertIn("not allocate or make a second 4096-byte payload copy", prose)
        self.assertIn("cannot be hard-preempted", prose)
        self.assertIn("dispatcher cancel: once the POST callback", prose)
        self.assertIn("OUTBOX-010H", self.packet)
        self.assertIn("Split-phase Delivery Runtime", self.packet)
        self.assertIn("cooperative cancellation only", self.packet)
        self.assertIn("race paths remain `NOT_RUN`", self.packet)

    def test_each_phase_has_only_its_authorized_side_effect(self) -> None:
        prepare = _function_body(
            self.source, "egolink_p0_delivery_runtime_prepare("
        )
        execute = _function_body(
            self.source, "egolink_p0_delivery_runtime_execute_prepared("
        )
        settle = _function_body(
            self.source, "egolink_p0_delivery_runtime_settle_prepared("
        )
        signal = _function_body(
            self.source, "egolink_p0_delivery_runtime_signal_durable_sos("
        )
        self.assertEqual(1, prepare.count("egolink_p0_outbox_dispatcher_begin("))
        self.assertNotIn("internal->http_post(", prepare)
        self.assertNotIn("finish_once(", prepare)
        self.assertNotIn("dispatcher_cancel(", prepare)
        self.assertEqual(1, execute.count("internal->http_post("))
        for forbidden in (
            "dispatcher_begin(",
            "dispatcher_finish(",
            "dispatcher_cancel(",
            "egolink_outbox_",
        ):
            self.assertNotIn(forbidden, execute)
        self.assertEqual(1, settle.count("finish_once("))
        self.assertNotIn("dispatcher_cancel(", settle)
        self.assertNotIn("internal->http_post(", settle)
        self.assertIn("atomic_compare_exchange_weak_explicit", signal)
        for forbidden in ("dispatcher", "outbox", "http_post", "storage"):
            self.assertNotIn(forbidden, signal.casefold())

    def test_transitive_dependency_proof_binds_exact_composition(self) -> None:
        name = "egolink_p0_delivery_runtime_dependencies_match("
        self.assertIn(name, self.header)
        proof = _function_body(self.source, name)
        self.assertIn("internal->dispatcher_bound", proof)
        self.assertIn("EGOLINK_P0_DELIVERY_RUNTIME_ACTIVE", proof)
        self.assertIn("egolink_p0_outbox_dispatcher_dependencies_match", proof)
        self.assertIn("shared_outbox, location_adapter", proof)
        for forbidden in ("dispatcher_begin(", "dispatcher_finish(", "http_post("):
            self.assertNotIn(forbidden, proof)

    def test_cancel_race_and_truthful_unknown_acceptance_are_pinned(self) -> None:
        execute = _function_body(
            self.source, "egolink_p0_delivery_runtime_execute_prepared("
        )
        cancel_settlement = _function_body(
            self.source, "static void prepare_cancelled_settlement("
        )
        cancel_control = _function_body(
            self.source, "egolink_p0_delivery_runtime_cancel("
        )
        close_control = _function_body(
            self.source, "egolink_p0_delivery_runtime_close("
        )
        self.assertIn("atomic_compare_exchange_strong_explicit", execute)
        self.assertIn("outcome != EGOLINK_P0_DELIVERY_POST_CANCELLED", execute)
        self.assertIn("P0_SETTLEMENT_CANCELLED", cancel_settlement)
        self.assertIn(
            "internal->transport_acceptance_may_be_unknown = post_was_entered",
            cancel_settlement,
        )
        self.assertIn("internal->post_outcome = post_was_entered", cancel_settlement)
        for body in (cancel_control, close_control):
            guard = body.index("EGOLINK_P0_DELIVERY_PHASE_TRANSPORT_RESULT_READY")
            effect = body.index("internal->busy = true", guard)
            self.assertLess(guard, effect)

    def test_lock_free_generation_is_required_and_storage_is_bounded(self) -> None:
        self.assertIn("#if ATOMIC_INT_LOCK_FREE != 2", self.source)
        self.assertIn("sizeof(unsigned int) == sizeof(uint32_t)", self.source)
        self.assertIn("transfer_control_generation", self.source)
        self.assertIn("transfer_generation", self.header)
        self.assertNotRegex(self.source, r"\b(malloc|calloc|realloc|free)\s*\(")
        self.assertEqual(
            1,
            len(
                re.findall(
                    r"uint8_t\s+response\s*\[EGOLINK_P0_DELIVERY_RUNTIME_RESPONSE_BYTES\]",
                    self.source,
                )
            ),
        )
        for forbidden in ("xTaskCreate", "gpio_", "esp_http_client", "mqtt_client"):
            self.assertNotIn(forbidden.casefold(), self.source.casefold())

    def test_actual_c_split_harness_cross_compiles_and_links(self) -> None:
        toolchain = _esp_toolchain()
        if toolchain is None:
            self.skipTest("ESP32-S3 compiler or ESP-IDF 5.4.2 is unavailable")
        compiler, idf = toolchain
        includes = [
            argument
            for path in _include_paths(idf)
            for argument in ("-I", str(path))
        ]
        common = [
            str(compiler),
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wconversion",
            "-Wformat=2",
            "-Wshadow",
            "-Wsign-conversion",
            "-fstack-usage",
            *includes,
        ]
        with tempfile.TemporaryDirectory(
            prefix="egolink-p0-delivery-split-"
        ) as temporary:
            temp = Path(temporary)
            runtime_object = temp / "runtime.o"
            harness_source = temp / "split_harness.c"
            harness_object = temp / "split_harness.o"
            harness_elf = temp / "split_harness.elf"
            harness_source.write_text(_split_harness(), encoding="utf-8")
            for source, output, extra in (
                (SOURCE, runtime_object, ()),
                (
                    harness_source,
                    harness_object,
                    ("-ffreestanding", "-fno-builtin"),
                ),
            ):
                compiled = subprocess.run(
                    [*common, *extra, "-c", str(source), "-o", str(output)],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
                self.assertEqual(
                    0,
                    compiled.returncode,
                    msg=compiled.stdout + compiled.stderr,
                )
            linked = subprocess.run(
                [
                    str(compiler),
                    "-nostdlib",
                    "-Wl,-e,mainCRTStartup",
                    str(runtime_object),
                    str(harness_object),
                    "-o",
                    str(harness_elf),
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            self.assertEqual(0, linked.returncode, msg=linked.stdout + linked.stderr)
            self.assertGreater(harness_elf.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()

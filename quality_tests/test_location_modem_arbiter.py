"""Focused LOC-021N checks for the dormant SIM7670 arbitration core.

The tests never start a task, open UART, invoke a modem, contact a network or
run target code.  The production source and an API behavior harness are
strictly cross-compiled and relocatable-linked for ESP32-S3.
"""

from __future__ import annotations

from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
COMPONENT = (
    ROOT
    / "firmware"
    / "mqtt_heartbeat"
    / "components"
    / "location_modem_arbiter"
)
HEADER = COMPONENT / "include" / "location_modem_arbiter.h"
SOURCE = COMPONENT / "location_modem_arbiter.c"
CMAKE = COMPONENT / "CMakeLists.txt"
APP_MAIN = ROOT / "firmware" / "mqtt_heartbeat" / "main" / "app_main.c"
PACKET = ROOT / "docs" / "tasks" / "active" / "LOC-021_DEVICE_LOCATION_INTEGRATION.md"


def _compiler() -> Path | None:
    candidates = (
        shutil.which("xtensa-esp32s3-elf-gcc"),
        Path(
            "C:/Espressif/tools/xtensa-esp-elf/esp-14.2.0_20241119/"
            "xtensa-esp-elf/bin/xtensa-esp32s3-elf-gcc.exe"
        ),
    )
    return next(
        (Path(value) for value in candidates if value and Path(value).is_file()),
        None,
    )


def _api_harness() -> str:
    return textwrap.dedent(
        r"""
        #include <stdbool.h>
        #include <stddef.h>
        #include <stdint.h>

        #include "location_modem_arbiter.h"

        static egolink_modem_arbiter_t arbiter;
        static volatile unsigned int status_sink;

        static egolink_modem_arbiter_text_t text_of(
            const char *value, size_t length)
        {
            egolink_modem_arbiter_text_t text = {value, length};
            return text;
        }

        void location_modem_arbiter_link_probe(void)
        {
            egolink_modem_arbiter_config_t config;
            egolink_modem_arbiter_enqueue_result_t enqueue_result;
            egolink_modem_arbiter_completion_result_t completion_result;
            egolink_modem_arbiter_snapshot_t snapshot;
            egolink_modem_arbiter_ticket_t location_ticket;
            egolink_modem_arbiter_ticket_t sos_ticket;
            egolink_modem_arbiter_ticket_t prepared_ticket;
            egolink_modem_arbiter_ticket_t replacement_ticket;
            const char location_id[] = "loc-attempt:0001";
            const char sos_id[] = "sos-attempt:0001";
            const char urgent_id[] = "sos-gnss-attempt:0001";
            egolink_modem_arbiter_request_t request = {
                .kind = EGOLINK_MODEM_COMMAND_LOCATION_TRANSPORT,
                .priority = EGOLINK_MODEM_PRIORITY_NORMAL,
                .operation_id = text_of(location_id, sizeof(location_id) - 1U),
            };

            egolink_modem_arbiter_default_config(&config);
            config.enabled = true;
            status_sink = (unsigned int)egolink_modem_arbiter_init(
                &arbiter, &config);
            status_sink = (unsigned int)egolink_modem_arbiter_enqueue(
                &arbiter, &request, &enqueue_result);
            status_sink = (unsigned int)egolink_modem_arbiter_take_next(
                &arbiter, &location_ticket);
            status_sink = (unsigned int)
                egolink_modem_arbiter_mark_execution_started(
                    &arbiter, &location_ticket);

            request.kind = EGOLINK_MODEM_COMMAND_DURABLE_SOS_TRANSPORT;
            request.priority = EGOLINK_MODEM_PRIORITY_CRITICAL;
            request.operation_id = text_of(sos_id, sizeof(sos_id) - 1U);
            status_sink = (unsigned int)egolink_modem_arbiter_enqueue(
                &arbiter, &request, &enqueue_result);
            if (egolink_modem_arbiter_location_cancel_requested(
                    &arbiter, location_ticket.generation)) {
                ++status_sink;
            }
            status_sink = (unsigned int)egolink_modem_arbiter_complete(
                &arbiter,
                &location_ticket,
                EGOLINK_MODEM_REPORTED_SUCCEEDED,
                &completion_result);

            status_sink = (unsigned int)egolink_modem_arbiter_take_next(
                &arbiter, &sos_ticket);
            status_sink = (unsigned int)
                egolink_modem_arbiter_mark_execution_started(
                    &arbiter, &sos_ticket);
            status_sink = (unsigned int)egolink_modem_arbiter_complete(
                &arbiter,
                &sos_ticket,
                EGOLINK_MODEM_REPORTED_OUTCOME_UNKNOWN,
                &completion_result);

            request.kind = EGOLINK_MODEM_COMMAND_SOS_URGENT_GNSS_ACQUIRE;
            request.priority = EGOLINK_MODEM_PRIORITY_URGENT;
            request.operation_id = text_of(
                urgent_id, sizeof(urgent_id) - 1U);
            status_sink = (unsigned int)egolink_modem_arbiter_enqueue(
                &arbiter, &request, &enqueue_result);
            status_sink = (unsigned int)egolink_modem_arbiter_take_next(
                &arbiter, &prepared_ticket);
            status_sink = (unsigned int)egolink_modem_arbiter_cancel_prepared(
                &arbiter, &prepared_ticket, &completion_result);
            if (egolink_modem_arbiter_cancel_requested(
                    &arbiter, prepared_ticket.generation,
                    prepared_ticket.kind)) {
                ++status_sink;
            }

            request.kind = EGOLINK_MODEM_COMMAND_LOCATION_TRANSPORT;
            request.priority = EGOLINK_MODEM_PRIORITY_NORMAL;
            request.operation_id = text_of(location_id, sizeof(location_id) - 1U);
            status_sink = (unsigned int)egolink_modem_arbiter_enqueue(
                &arbiter, &request, &enqueue_result);
            status_sink = (unsigned int)egolink_modem_arbiter_take_next(
                &arbiter, &prepared_ticket);
            request.kind = EGOLINK_MODEM_COMMAND_DURABLE_SOS_TRANSPORT;
            request.priority = EGOLINK_MODEM_PRIORITY_CRITICAL;
            request.operation_id = text_of(sos_id, sizeof(sos_id) - 1U);
            status_sink = (unsigned int)egolink_modem_arbiter_retarget_prepared(
                &arbiter, &prepared_ticket, &request, &replacement_ticket,
                &completion_result);
            status_sink = (unsigned int)egolink_modem_arbiter_complete(
                &arbiter,
                &location_ticket,
                EGOLINK_MODEM_REPORTED_DEFINITE_FAILURE,
                &completion_result);
            status_sink = (unsigned int)egolink_modem_arbiter_current_status(
                &arbiter, &snapshot);
            status_sink += (unsigned int)snapshot.queued_count;
            status_sink += (unsigned int)
                egolink_modem_arbiter_status_name(snapshot.initialized
                    ? EGOLINK_MODEM_ARBITER_OK
                    : EGOLINK_MODEM_ARBITER_NOT_INITIALIZED)[0];
            status_sink += (unsigned int)
                egolink_modem_command_kind_name(sos_ticket.kind)[0];
            status_sink += (unsigned int)
                egolink_modem_completion_name(completion_result.completion)[0];
        }
        """
    )


class LocationModemArbiterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.header = HEADER.read_text(encoding="utf-8")
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.cmake = CMAKE.read_text(encoding="utf-8")
        cls.app_main = APP_MAIN.read_text(encoding="utf-8")

    def test_component_is_default_off_dormant_and_has_no_hardware_io(self) -> None:
        self.assertIn("config->enabled = false", self.source)
        self.assertNotIn("location_modem_arbiter", self.app_main)
        self.assertIn('SRCS "location_modem_arbiter.c"', self.cmake)
        forbidden = (
            "xTaskCreate",
            "uart_",
            "sim7670_",
            "esp_http_client",
            "mqtt_",
            "gpio_",
            "esp_wifi",
            "socket(",
        )
        for token in forbidden:
            self.assertNotIn(token.casefold(), self.source.casefold())

    def test_init_overwrites_opaque_storage_before_deriving_internal_view(self) -> None:
        init = self.source[
            self.source.index("egolink_modem_arbiter_status_t egolink_modem_arbiter_init") :
            self.source.index("egolink_modem_arbiter_status_t egolink_modem_arbiter_enqueue")
        ]
        clear = init.index("(void)memset(arbiter, 0, sizeof(*arbiter))")
        derive = init.index("internal_of(arbiter)")
        self.assertLess(clear, derive)
        self.assertNotIn("valid_magic", init[:derive])

    def test_command_taxonomy_and_priority_pairing_are_closed(self) -> None:
        for token in (
            "EGOLINK_MODEM_COMMAND_DURABLE_SOS_TRANSPORT",
            "EGOLINK_MODEM_COMMAND_LOCATION_TRANSPORT",
            "EGOLINK_MODEM_COMMAND_GNSS_ACQUIRE",
            "EGOLINK_MODEM_COMMAND_GNSS_STATUS",
            "EGOLINK_MODEM_COMMAND_CELL_OBSERVE",
            "EGOLINK_MODEM_COMMAND_SOS_URGENT_GNSS_ACQUIRE",
        ):
            self.assertIn(token, self.header)
        pairing = self.source[
            self.source.index("static bool valid_pairing") :
            self.source.index("static bool operation_id_char_allowed")
        ]
        self.assertIn("DURABLE_SOS_TRANSPORT", pairing)
        self.assertIn("EGOLINK_MODEM_PRIORITY_CRITICAL", pairing)
        self.assertIn("EGOLINK_MODEM_PRIORITY_URGENT", pairing)
        self.assertRegex(
            pairing,
            r"return priority == EGOLINK_MODEM_PRIORITY_NORMAL\s*;",
        )

    def test_storage_is_fixed_bounded_and_not_a_second_durable_queue(self) -> None:
        self.assertIn("EGOLINK_MODEM_ARBITER_QUEUE_CAPACITY 8U", self.header)
        self.assertIn("EGOLINK_MODEM_ARBITER_CRITICAL_RESERVED_SLOTS 1U", self.header)
        self.assertIn("EGOLINK_MODEM_ARBITER_CONTEXT_BYTES 4096U", self.header)
        self.assertIn("sizeof(modem_arbiter_internal_t)", self.source)
        self.assertNotRegex(self.source, r"\b(malloc|calloc|realloc|free)\s*\(")
        for forbidden in (
            "payload",
            "credential",
            "authorization",
            "p0_outbox",
            "persistent_priority_outbox",
            "ACTION_SUCCEEDED",
        ):
            self.assertNotIn(forbidden.casefold(), self.source.casefold())

    def test_attempt_identity_is_bounded_exact_and_generation_bound(self) -> None:
        self.assertIn("EGOLINK_MODEM_ARBITER_OPERATION_ID_MAX_BYTES 128U", self.header)
        for allowed in ("value == '.'", "value == '_'", "value == ':'", "value == '-'"):
            self.assertIn(allowed, self.source)
        self.assertIn("memcmp(stored, candidate.data, candidate.length)", self.source)
        self.assertIn("ticket->generation == internal->generation", self.source)
        self.assertIn("MODEM_ARBITER_GENERATION_MAX", self.source)
        self.assertIn("EGOLINK_MODEM_ARBITER_STALE_OPERATION", self.source)

    def test_one_in_flight_and_split_phase_are_explicit(self) -> None:
        self.assertIn("EGOLINK_MODEM_ARBITER_FLIGHT_PREPARED", self.header)
        self.assertIn("EGOLINK_MODEM_ARBITER_FLIGHT_EXECUTING", self.header)
        self.assertIn("EGOLINK_MODEM_ARBITER_IN_FLIGHT", self.source)
        self.assertIn("egolink_modem_arbiter_mark_execution_started", self.source)
        self.assertIn("The owner must\n * not be held while modem execution runs", self.header)
        self.assertNotRegex(self.header, r"typedef\s+[^;]*\(\s*\*[^)]*callback")

    def test_critical_reserve_and_explicit_sos_supersession_are_explicit(self) -> None:
        enqueue = self.source[
            self.source.index("egolink_modem_arbiter_status_t egolink_modem_arbiter_enqueue") :
            self.source.index("egolink_modem_arbiter_status_t egolink_modem_arbiter_take_next")
        ]
        self.assertIn("NORMAL_CAPACITY_RESERVED", enqueue)
        self.assertIn("newest_queued_location_index", enqueue)
        self.assertIn("displaced_queued_operation_id", enqueue)
        self.assertIn("prepared_location_preempted", enqueue)
        self.assertIn("CANCELLED_BEFORE_EXECUTION", enqueue)
        self.assertIn("newest_queued_normal_sensor_index", enqueue)
        self.assertIn("queued_sensor_coalesced", enqueue)
        self.assertIn("coalesced_queued_operation_id", enqueue)
        self.assertIn(
            "EGOLINK_MODEM_COALESCE_SOS_URGENT_SUPERSEDES_NORMAL_SENSOR",
            enqueue,
        )
        self.assertIn("queued_location_replaced_for_urgent", enqueue)
        self.assertIn(
            "EGOLINK_MODEM_COALESCE_SOS_URGENT_REPLACES_NORMAL_LOCATION_FOR_RESERVE",
            enqueue,
        )

    def test_urgent_gnss_replaces_location_without_consuming_critical_reserve(self) -> None:
        enqueue = self.source[
            self.source.index("egolink_modem_arbiter_status_t egolink_modem_arbiter_enqueue") :
            self.source.index("egolink_modem_arbiter_status_t egolink_modem_arbiter_take_next")
        ]
        urgent_branch = enqueue[
            enqueue.index("if (urgent_gnss)") :
            enqueue.index("if (!critical_sos", enqueue.index("if (urgent_gnss)"))
        ]
        self.assertIn("noncritical_queued_count", urgent_branch)
        self.assertIn("newest_queued_location_index", urgent_branch)
        self.assertIn("replace_location_for_urgent = true", urgent_branch)
        reserve_guard = enqueue[
            enqueue.index("if (!critical_sos") :
            enqueue.index("if (target ==", enqueue.index("if (!critical_sos"))
        ]
        self.assertIn("!replace_location_for_urgent", reserve_guard)
        self.assertIn("durable Location remains in the", self.header)

    def test_exhaustion_guards_precede_queue_or_flight_removal(self) -> None:
        enqueue = self.source[
            self.source.index("egolink_modem_arbiter_status_t egolink_modem_arbiter_enqueue") :
            self.source.index("egolink_modem_arbiter_status_t egolink_modem_arbiter_take_next")
        ]
        order_guard = enqueue.index("if (internal->next_order == UINT64_MAX)")
        order_return = enqueue.index("EGOLINK_MODEM_ARBITER_ORDER_EXHAUSTED")
        self.assertLess(order_guard, order_return)
        self.assertNotIn("latch_fault", enqueue[order_guard:order_return])
        self.assertLess(
            order_guard,
            enqueue.index("remember_completion(internal, &internal->queue[target]"),
        )
        self.assertLess(order_guard, enqueue.index("--internal->queued_count"))
        self.assertLess(order_guard, enqueue.index("entry->occupied = true"))

        take = self.source[
            self.source.index("egolink_modem_arbiter_status_t egolink_modem_arbiter_take_next") :
            self.source.index("egolink_modem_arbiter_status_t egolink_modem_arbiter_mark_execution_started")
        ]
        generation_guard = take.index(
            "if (internal->generation >= MODEM_ARBITER_GENERATION_MAX)"
        )
        generation_return = take.index("EGOLINK_MODEM_ARBITER_GENERATION_EXHAUSTED")
        self.assertNotIn("latch_fault", take[generation_guard:generation_return])
        self.assertLess(
            generation_guard,
            take.index("internal->flight = internal->queue[selected]"),
        )
        self.assertLess(
            generation_guard,
            take.index("--internal->queued_count"),
        )

    def test_duplicate_conflict_and_recent_attempts_are_not_silent(self) -> None:
        for token in (
            "EGOLINK_MODEM_DUPLICATE_QUEUED",
            "EGOLINK_MODEM_DUPLICATE_IN_FLIGHT",
            "EGOLINK_MODEM_DUPLICATE_RECENTLY_COMPLETED",
            "EGOLINK_MODEM_ARBITER_IDENTITY_CONFLICT",
            "remember_completion",
        ):
            self.assertIn(token, self.source)
        self.assertIn("operation_id identifies one execution attempt", self.header)
        self.assertIn("durable retry must use a new operation_id", self.header)

    def test_cancel_is_lock_free_cooperative_and_late_result_is_unknown(self) -> None:
        self.assertIn("#if ATOMIC_INT_LOCK_FREE != 2", self.source)
        self.assertIn("atomic_compare_exchange_strong_explicit", self.source)
        self.assertIn("MODEM_CONTROL_CANCEL_REQUESTED", self.source)
        self.assertIn("control_kind(observed) == kind", self.source)
        self.assertIn("egolink_modem_arbiter_cancel_prepared", self.source)
        self.assertIn("EGOLINK_MODEM_REPORTED_NOT_EXECUTED", self.source)
        self.assertIn("memory_order_acquire", self.source)
        complete = self.source[
            self.source.index("egolink_modem_arbiter_status_t egolink_modem_arbiter_complete") :
            self.source.index("egolink_modem_arbiter_status_t egolink_modem_arbiter_current_status")
        ]
        self.assertIn("late_executor_result_discarded", complete)
        self.assertIn("transport_acceptance_may_be_unknown", complete)
        self.assertIn("transport_kind(internal->flight.kind)", complete)
        self.assertIn("EGOLINK_MODEM_COMPLETION_CANCELLED_AFTER_START", complete)
        for forbidden in ("abort", "terminate", "kill", "force_stop"):
            self.assertNotRegex(self.source.casefold(), rf"\b{forbidden}\s*\(")

    def test_prepared_route_retarget_is_exact_generation_bound_and_no_io(self) -> None:
        body = self.source[
            self.source.index("egolink_modem_arbiter_status_t egolink_modem_arbiter_retarget_prepared") :
            self.source.index("bool egolink_modem_arbiter_cancel_requested")
        ]
        self.assertIn("ticket_matches(internal, current_ticket)", body)
        self.assertIn("MODEM_ARBITER_GENERATION_MAX", body)
        self.assertLess(
            body.index("MODEM_ARBITER_GENERATION_MAX"),
            body.index("remember_completion"),
        )
        self.assertIn("EGOLINK_MODEM_REPORTED_NOT_EXECUTED", body)
        self.assertIn("EGOLINK_MODEM_COMPLETION_CANCELLED_BEFORE_EXECUTION", body)
        self.assertIn("++internal->generation", body)
        self.assertIn("fill_ticket(internal, replacement_ticket)", body)
        self.assertIn("never settles, ACKs or deletes", self.header)

    def test_packet_records_scope_and_non_claims(self) -> None:
        packet = PACKET.read_text(encoding="utf-8")
        self.assertIn("LOC-021N", packet)
        self.assertIn("location_modem_arbiter", packet)
        self.assertIn("transient", packet.casefold())
        self.assertIn("durability remains", packet.casefold())
        self.assertIn("ACTION_SUCCEEDED", packet)
        self.assertIn("P0-LOC", packet)
        self.assertIn("NOT_RUN", packet)

    def test_actual_source_and_api_harness_strictly_cross_compile_and_link(self) -> None:
        compiler = _compiler()
        if compiler is None:
            self.skipTest("ESP32-S3 compiler is unavailable")
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
            "-I",
            str(COMPONENT / "include"),
        ]
        with tempfile.TemporaryDirectory(prefix="egolink-modem-arbiter-") as temporary:
            temp = Path(temporary)
            source_object = temp / "location_modem_arbiter.o"
            harness_source = temp / "location_modem_arbiter_harness.c"
            harness_object = temp / "location_modem_arbiter_harness.o"
            linked = temp / "location_modem_arbiter_linked.o"
            harness_source.write_text(_api_harness(), encoding="utf-8")
            for source, output in (
                (SOURCE, source_object),
                (harness_source, harness_object),
            ):
                result = subprocess.run(
                    [*common, "-c", str(source), "-o", str(output)],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
                self.assertEqual(0, result.returncode, msg=result.stdout + result.stderr)
            result = subprocess.run(
                [
                    str(compiler),
                    "-nostdlib",
                    "-Wl,-r",
                    str(source_object),
                    str(harness_object),
                    "-o",
                    str(linked),
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            self.assertEqual(0, result.returncode, msg=result.stdout + result.stderr)
            self.assertGreater(linked.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()

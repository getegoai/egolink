"""Static/spec checks for OUTBOX-010B.

These tests inspect the isolated C component and exercise existing Python
contract fixtures. They do not execute Xtensa C and are not NVS, reboot,
brownout, hardware, or product-durability evidence.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import unittest

from quality_tests.test_location_state_device_emitter import (
    _compact,
    _emit_fixture,
    _fine_state,
)


ROOT = Path(__file__).resolve().parents[1]
COMPONENT = (
    ROOT
    / "firmware"
    / "mqtt_heartbeat"
    / "components"
    / "persistent_priority_outbox"
)
HEADER = COMPONENT / "include" / "persistent_priority_outbox.h"
SOURCE = COMPONENT / "persistent_priority_outbox.c"
CMAKE = COMPONENT / "CMakeLists.txt"
PACKET = ROOT / "docs" / "tasks" / "active" / "OUTBOX-010_PERSISTENT_PRIORITY_OUTBOX.md"


class PersistentPriorityOutboxDeviceCoreStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.header = HEADER.read_text(encoding="utf-8")
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.cmake = CMAKE.read_text(encoding="utf-8")
        cls.packet = PACKET.read_text(encoding="utf-8")

    def function_body(self, name: str, next_name: str) -> str:
        start = self.source.index(name)
        end = self.source.index(next_name, start + len(name))
        return self.source[start:end]

    def constant(self, name: str) -> int:
        match = re.search(rf"#define {name} (\d+)U", self.header)
        self.assertIsNotNone(match, name)
        return int(match.group(1))

    def test_slice_is_isolated_and_builds_with_local_warnings_as_errors(self) -> None:
        self.assertIn('SRCS "persistent_priority_outbox.c"', self.cmake)
        self.assertIn("REQUIRES json mbedtls", self.cmake)
        for option in ("-Wall", "-Wextra", "-Werror", "-Wconversion", "-Wshadow"):
            self.assertIn(option, self.cmake)
        for forbidden in (
            "app_main",
            "esp_http_client",
            "esp_wifi",
            "sim7670",
            "mqtt_client",
            "gpio_",
            "nvs_",
            "freertos/",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.source.casefold())

    def test_fixed_limits_are_explicit_and_not_labelled_product_sizing(self) -> None:
        self.assertEqual(4, self.constant("EGOLINK_OUTBOX_MAX_RECORDS"))
        self.assertEqual(4096, self.constant("EGOLINK_OUTBOX_MAX_PAYLOAD_BYTES"))
        self.assertEqual(129, self.constant("EGOLINK_OUTBOX_ID_CAPACITY"))
        self.assertEqual(
            22240, self.constant("EGOLINK_OUTBOX_STORAGE_IMAGE_V1_BYTES")
        )
        self.assertIn("EGOLINK_OUTBOX_CORE_STORAGE_BYTES (48U * 1024U)", self.header)
        self.assertIn("not product queue sizing", " ".join(self.packet.split()))
        self.assertIn("roughly 1.8 KiB representative", self.packet)
        self.assertIn("44,480", self.packet)
        self.assertIn("24,576", self.packet)

    def test_raw_storage_layout_and_single_owner_constraints_are_explicit(self) -> None:
        self.assertIn(
            "sizeof(storage_image_t) == EGOLINK_OUTBOX_STORAGE_IMAGE_V1_BYTES",
            self.source,
        )
        self.assertIn("version and migration are required", self.source)
        self.assertIn("no internal lock", self.header)
        self.assertIn("caller-owned mutex", self.header)
        self.assertIn("must not call\n * back into this core", self.header)
        self.assertIn("does not provide an NVS adapter", self.header)
        self.assertIn("current firmware partition table", self.header)
        self.assertIn("not on a normal task stack", self.header)

    def test_representative_loc_envelope_over_one_kib_is_statically_admissible(self) -> None:
        state_json = _compact(_fine_state(1_000))
        status, nul_terminated = _emit_fixture(
            state_json=state_json,
            event_time_ms=1_000,
            event_time_ns=1_000_000_000,
            device_id="ego-device-001",
            session_id="boot-session-007",
            observation_id="location-state-000041",
        )
        self.assertEqual("ok", status)
        payload = nul_terminated[:-1]
        self.assertGreater(len(payload), 1024)
        self.assertLessEqual(len(payload), self.constant("EGOLINK_OUTBOX_MAX_PAYLOAD_BYTES"))
        self.assertIsInstance(json.loads(payload), dict)
        self.assertIn("EGOLINK_OUTBOX_PAYLOAD_EVENT_JSON", self.header)
        self.assertIn(
            "request->payload_length > implementation->state.configuration.max_payload_bytes",
            self.source,
        )

    def test_payload_hash_is_over_exact_persisted_and_returned_bytes(self) -> None:
        enqueue = self.function_body(
            "egolink_outbox_status_t egolink_outbox_enqueue(",
            "egolink_outbox_status_t egolink_outbox_begin_send_attempt(",
        )
        begin_send = self.function_body(
            "egolink_outbox_status_t egolink_outbox_begin_send_attempt(",
            "egolink_outbox_status_t egolink_outbox_record_transport_result(",
        )
        self.assertRegex(
            enqueue,
            r"sha256_bytes\(\s*request->payload,\s*request->payload_length,\s*payload_sha256\)",
        )
        self.assertIn(
            "memcpy(proposed->payload, request->payload, request->payload_length)",
            re.sub(r"\s+", " ", enqueue),
        )
        self.assertIn(
            "memcpy( send_item->payload, selected->payload, selected->payload_length)",
            re.sub(r"\s+", " ", begin_send),
        )
        self.assertNotIn("canonical", enqueue.casefold())
        self.assertIn("performs no canonicalization", self.header)

    def test_payload_validation_and_enqueue_do_not_use_payload_sized_stack_copies(self) -> None:
        validation = self.function_body(
            "static egolink_outbox_status_t validate_payload(",
            "static void hash_builder_begin(",
        )
        enqueue = self.function_body(
            "egolink_outbox_status_t egolink_outbox_enqueue(",
            "egolink_outbox_status_t egolink_outbox_begin_send_attempt(",
        )
        self.assertNotIn("char text[EGOLINK_OUTBOX_MAX_PAYLOAD_BYTES", validation)
        self.assertNotIn("stored_record_t proposed;", enqueue)
        self.assertIn("cJSON_ParseWithLengthOpts", validation)
        self.assertIn("parse_end != payload_end", validation)

    def test_write_before_send_attempt_and_partial_commit_fail_closed(self) -> None:
        begin_send = self.function_body(
            "egolink_outbox_status_t egolink_outbox_begin_send_attempt(",
            "egolink_outbox_status_t egolink_outbox_record_transport_result(",
        )
        self.assertLess(
            begin_send.index("commit_mutation(implementation)"),
            begin_send.index("send_item->payload_length"),
        )
        commit = self.function_body(
            "static egolink_outbox_status_t commit_mutation(",
            "static bool can_increment(",
        )
        self.assertIn("1U - implementation->active_slot", commit)
        self.assertLess(commit.index("write_slot("), commit.index("active_slot = target_slot"))
        self.assertIn("abort_mutation(implementation)", commit)
        self.assertIn("implementation->fault_latched = true", commit)

    def test_transport_acceptance_only_waits_for_ack(self) -> None:
        transport = self.function_body(
            "egolink_outbox_status_t egolink_outbox_record_transport_result(",
            "static egolink_outbox_status_t persist_ack_rejection(",
        )
        self.assertIn("EGOLINK_OUTBOX_SEND_AWAITING_POSITIVE_ACK", transport)
        self.assertNotIn("--implementation->state.record_count", transport)
        self.assertNotIn("++implementation->state.tombstone_count", transport)
        self.assertNotIn("tombstone", transport.casefold())
        self.assertIn("A transport/HTTP success only enters AWAITING_POSITIVE_ACK", self.header)

    def test_only_exact_positive_ack_deletes(self) -> None:
        ack = self.function_body(
            "egolink_outbox_status_t egolink_outbox_handle_ack(",
            "egolink_outbox_status_t egolink_outbox_snapshot(",
        )
        for identity_member in (
            "ack->status != EGOLINK_OUTBOX_ACK_ACCEPTED",
            "ack->device_id",
            "ack->event_id",
            "acknowledged_payload_hash",
            "record->payload_sha256",
        ):
            self.assertIn(identity_member, ack)
        self.assertLess(ack.index("identity_matches"), ack.index("--implementation->state.record_count"))
        self.assertIn("EGOLINK_OUTBOX_DELETED_AFTER_POSITIVE_ACK", ack)
        self.assertIn("EGOLINK_OUTBOX_DUPLICATE_POSITIVE_ACK", ack)

    def test_dual_slot_recovery_hash_and_generation_ambiguity_are_explicit(self) -> None:
        init = self.function_body(
            "egolink_outbox_status_t egolink_outbox_init(",
            "void egolink_outbox_deinit(",
        )
        for marker in (
            "read_and_assess_slot(\n        implementation, 0U",
            "read_and_assess_slot(\n        implementation, 1U",
            "EGOLINK_OUTBOX_RECOVERY_LATEST_GENERATION_SELECTED",
            "EGOLINK_OUTBOX_RECOVERY_GENERATION_GAP",
            "EGOLINK_OUTBOX_RECOVERY_SINGLE_VALID_SLOT",
            "EGOLINK_OUTBOX_CONFIGURATION_MISMATCH",
        ):
            self.assertIn(marker, init)
        self.assertIn("same-generation", self.packet.casefold())
        self.assertIn("storage_sha256", self.source)
        self.assertIn("memcmp(\n                    &implementation->state", init)

    def test_capacity_checks_protect_critical_slots_and_bytes_without_eviction(self) -> None:
        enqueue = self.function_body(
            "egolink_outbox_status_t egolink_outbox_enqueue(",
            "egolink_outbox_status_t egolink_outbox_begin_send_attempt(",
        )
        for marker in (
            "EGOLINK_OUTBOX_FAILURE_CRITICAL_PAYLOAD_RESERVE_PROTECTED",
            "EGOLINK_OUTBOX_FAILURE_TOTAL_PAYLOAD_CAPACITY_EXHAUSTED",
            "EGOLINK_OUTBOX_FAILURE_CRITICAL_RESERVE_PROTECTED",
            "EGOLINK_OUTBOX_FAILURE_CRITICAL_CAPACITY_EXHAUSTED",
        ):
            self.assertIn(marker, enqueue)
        self.assertNotIn("memmove", enqueue)
        self.assertNotIn("--implementation->state.record_count", enqueue)

    def test_integer_and_runtime_epoch_edges_are_fail_closed(self) -> None:
        self.assertIn("selected->attempt_count == UINT32_MAX", self.source)
        self.assertIn("now_ms > UINT64_MAX - delay", self.source)
        self.assertIn("scratch.generation == UINT64_MAX", self.source)
        self.assertIn("uint64_t maximum_epoch = maximum_runtime_epoch(image)", self.source)
        self.assertIn("runtime_epoch < maximum_epoch", self.source)
        self.assertIn("now_ms < candidate->last_now_ms", self.source)
        self.assertIn("EGOLINK_OUTBOX_TIME_ROLLBACK", self.source)

    def test_media_is_explicitly_rejected_and_no_payload_appears_in_snapshot(self) -> None:
        for marker in (
            "EGOLINK_OUTBOX_PAYLOAD_RTC_MEDIA",
            "EGOLINK_OUTBOX_PAYLOAD_AUDIO",
            "EGOLINK_OUTBOX_PAYLOAD_IMAGE",
            "EGOLINK_OUTBOX_PAYLOAD_VIDEO",
        ):
            self.assertIn(marker, self.header)
        for media_key in ('"audio"', '"pcm"', '"opus"', '"recording"', '"video"'):
            self.assertIn(media_key, self.source)
        snapshot = self.function_body(
            "egolink_outbox_status_t egolink_outbox_snapshot(",
            "const char *egolink_outbox_status_name(",
        )
        self.assertNotIn("record->payload", snapshot)
        self.assertIn("adapter_unverified_not_product_nvs", snapshot)

    def test_static_nonclaims_are_recorded(self) -> None:
        for statement in (
            "supplies no NVS adapter",
            "no NVS, flash-endurance, brownout-atomicity",
            "do not execute Xtensa C",
        ):
            self.assertIn(statement, self.packet)


if __name__ == "__main__":
    unittest.main()

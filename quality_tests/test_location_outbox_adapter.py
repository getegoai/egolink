"""Static/spec coverage for dormant LOC-021G device delivery wiring.

The Python fixtures exercise the frozen emitter/server boundary and inspect the
actual adapter source. They do not execute Xtensa code and are not NVS,
transport, reboot, hardware, Guardian-delivery, or P0-LOC evidence.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from quality_tests.test_location_state_device_emitter import (
    _compact,
    _emit_fixture,
    _fine_state,
)
from server.location_delivery_ack import build_location_state_delivery_ack


ROOT = Path(__file__).resolve().parents[1]
COMPONENT = (
    ROOT
    / "firmware"
    / "mqtt_heartbeat"
    / "components"
    / "location_outbox_adapter"
)
SOURCE = COMPONENT / "location_outbox_adapter.c"
HEADER = COMPONENT / "include" / "location_outbox_adapter.h"
CMAKE = COMPONENT / "CMakeLists.txt"
PACKET = ROOT / "docs" / "tasks" / "active" / "LOC-021_DEVICE_LOCATION_INTEGRATION.md"

ACK_VERSION = "egolink.persistent_priority_outbox.ack.v0.1"
DELIVERY_SCOPE = "server_durable_ingest_only"
ACK_FIELDS = {
    "contract_version",
    "ack_id",
    "device_id",
    "event_id",
    "payload_sha256",
    "status",
    "ack_time_ms",
}
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$")


def _representative_envelope() -> tuple[bytes, dict]:
    state = _fine_state(1_700_000_000_123)
    status, emitted = _emit_fixture(
        state_json=_compact(state),
        event_time_ms=state["event_time_ms"],
        event_time_ns=state["event_time_ms"] * 1_000_000,
        device_id="ego-device-001",
        boot_count=7,
        session_id="boot-session-007",
        sequence_id=41,
        observation_id="location-state-000041",
    )
    if status != "ok":
        raise AssertionError(status)
    payload = emitted[:-1]
    return payload, json.loads(payload)


def _server_response(payload: bytes, envelope: dict) -> dict:
    identity = {
        field: envelope[field]
        for field in (
            "device_id",
            "boot_count",
            "session_id",
            "event_time_ms",
            "sequence_id",
            "observation_id",
        )
    }
    result = {"status": "accepted", "identity": identity}
    return {
        "ok": True,
        "result": result,
        "delivery_ack": build_location_state_delivery_ack(
            payload, envelope, result, ack_time_ms=1_700_000_001_000
        ),
        "delivery_scope": DELIVERY_SCOPE,
    }


def _strict_positive_ack(
    *,
    transport_accepted: bool,
    response_bytes: bytes,
    expected_device_id: str,
    expected_event_id: str,
    expected_payload_sha256: str,
) -> bool:
    """Spec oracle for deletion eligibility, not a second runtime."""

    if not transport_accepted:
        return False
    if not response_bytes or len(response_bytes) > 8192:
        return False
    if b"\0" in response_bytes or b"\\" in response_bytes:
        return False
    try:
        response = json.loads(response_bytes)
    except (UnicodeDecodeError, ValueError):
        return False
    if not isinstance(response, dict) or response.get("ok") is not True:
        return False
    if response.get("delivery_scope") != DELIVERY_SCOPE:
        return False
    ack = response.get("delivery_ack")
    if not isinstance(ack, dict) or set(ack) != ACK_FIELDS:
        return False
    digest = ack.get("payload_sha256")
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        return False
    ack_time = ack.get("ack_time_ms")
    if type(ack_time) is not int or not 0 <= ack_time <= (1 << 53) - 1:
        return False
    if (
        ack.get("contract_version") != ACK_VERSION
        or ack.get("status") != "accepted"
        or not isinstance(ack.get("device_id"), str)
        or SAFE_ID.fullmatch(ack["device_id"]) is None
        or ack.get("event_id") != "loc-" + digest
        or ack.get("ack_id") != "ack-" + digest
    ):
        return False
    return (
        ack["device_id"] == expected_device_id
        and ack["event_id"] == expected_event_id
        and digest == expected_payload_sha256
    )


class LocationOutboxAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.header = HEADER.read_text(encoding="utf-8")
        cls.cmake = CMAKE.read_text(encoding="utf-8")
        cls.packet = PACKET.read_text(encoding="utf-8")

    def function_body(self, name: str, next_name: str) -> str:
        start = self.source.index(name)
        end = self.source.index(next_name, start + len(name))
        return self.source[start:end]

    def test_component_is_dormant_transport_neutral_and_locally_strict(self) -> None:
        self.assertIn('SRCS "location_outbox_adapter.c"', self.cmake)
        self.assertIn(
            "REQUIRES location_state_emitter persistent_priority_outbox json mbedtls",
            self.cmake,
        )
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
            "esp_log",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.source.casefold())

    def test_representative_emitter_bytes_match_server_ack_identity(self) -> None:
        payload, envelope = _representative_envelope()
        self.assertGreater(len(payload), 1800)
        self.assertLessEqual(len(payload), 4096)
        digest = hashlib.sha256(payload).hexdigest()
        response = _server_response(payload, envelope)
        ack = response["delivery_ack"]
        self.assertEqual(digest, ack["payload_sha256"])
        self.assertEqual("loc-" + digest, ack["event_id"])
        self.assertEqual("ack-" + digest, ack["ack_id"])
        wire_response = json.dumps(
            response, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        self.assertTrue(
            _strict_positive_ack(
                transport_accepted=True,
                response_bytes=wire_response,
                expected_device_id=envelope["device_id"],
                expected_event_id="loc-" + digest,
                expected_payload_sha256=digest,
            )
        )

    def test_enqueue_hashes_emitter_bytes_and_writes_before_send(self) -> None:
        body = self.function_body(
            "egolink_location_outbox_emit_and_enqueue(",
            "static size_t object_member_count(",
        )
        self.assertLess(
            body.index("egolink_location_state_emit("),
            body.index("exact_sha256(scratch, payload_length, digest)"),
        )
        self.assertLess(
            body.index("exact_sha256(scratch, payload_length, digest)"),
            body.index("egolink_outbox_enqueue("),
        )
        self.assertIn(".payload = (const uint8_t *)scratch", body)
        self.assertIn(".payload_length = payload_length", body)
        self.assertIn("EGOLINK_LOCATION_OUTBOX_EVENT_PREFIX", body)
        self.assertIn("EGOLINK_OUTBOX_MAX_PAYLOAD_BYTES", body)
        self.assertNotIn("canonical", body.casefold())

    def test_adapter_owns_outbox_init_and_rejects_wrong_device_before_mutation(self) -> None:
        init = self.function_body(
            "egolink_location_outbox_adapter_init(",
            "void egolink_location_outbox_adapter_deinit(",
        )
        self.assertIn("egolink_outbox_init(", init)
        self.assertIn("config->device_id", init)
        self.assertIn("adapter->device_id", init)

        enqueue = self.function_body(
            "egolink_location_outbox_emit_and_enqueue(",
            "static size_t object_member_count(",
        )
        mismatch_at = enqueue.index(
            "if (!adapter_device_matches(adapter, input->device_id))"
        )
        emit_at = enqueue.index("egolink_location_state_emit(")
        persist_at = enqueue.index("egolink_outbox_enqueue(")
        self.assertLess(mismatch_at, emit_at)
        self.assertLess(mismatch_at, persist_at)
        self.assertIn("EGOLINK_LOCATION_OUTBOX_ENQUEUE_DEVICE_MISMATCH", enqueue)

    def test_source_lineage_and_clock_kind_are_preserved(self) -> None:
        body = self.function_body(
            "egolink_location_outbox_emit_and_enqueue(",
            "static size_t object_member_count(",
        )
        for binding in (
            ".source_event_time_ms = input->event_time_ms",
            ".boot_count = input->boot_count",
            ".session_id = session_id",
            ".source_sequence = input->sequence_id",
            "EGOLINK_OUTBOX_SOURCE_TIME_BOOT_MONOTONIC_MS",
            "EGOLINK_OUTBOX_SOURCE_TIME_UTC_MS",
        ):
            self.assertIn(binding, body)

    def test_sos_only_promotes_location_priority(self) -> None:
        body = self.function_body(
            "egolink_location_outbox_emit_and_enqueue(",
            "static size_t object_member_count(",
        )
        self.assertIn("EGOLINK_OUTBOX_PRIORITY_NORMAL", body)
        self.assertIn("EGOLINK_OUTBOX_PRIORITY_CRITICAL", body)
        self.assertIn(
            ".event_type = EGOLINK_LOCATION_OUTBOX_EVENT_TYPE",
            body,
        )
        self.assertEqual("location_state", re.search(
            r'#define EGOLINK_LOCATION_OUTBOX_EVENT_TYPE "([^"]+)"', self.header
        ).group(1))
        self.assertNotIn('"manual_sos"', self.source)

    def test_nonaccepted_transport_never_reaches_ack_parser_or_delete(self) -> None:
        body = self.function_body(
            "egolink_location_outbox_finish_attempt(",
            "const char *egolink_location_outbox_enqueue_status_name(",
        )
        record_at = body.index("egolink_outbox_record_transport_result(")
        transport_guard_at = body.index("if (!accepted_by_transport)")
        parse_at = body.index("parse_delivery_ack(")
        delete_at = body.index("egolink_outbox_handle_ack(")
        self.assertLess(record_at, transport_guard_at)
        self.assertLess(transport_guard_at, parse_at)
        self.assertLess(parse_at, delete_at)

        payload, envelope = _representative_envelope()
        digest = hashlib.sha256(payload).hexdigest()
        response_bytes = json.dumps(
            _server_response(payload, envelope), separators=(",", ":")
        ).encode("utf-8")
        self.assertFalse(
            _strict_positive_ack(
                transport_accepted=False,
                response_bytes=response_bytes,
                expected_device_id=envelope["device_id"],
                expected_event_id="loc-" + digest,
                expected_payload_sha256=digest,
            )
        )

    def test_missing_wrong_scope_negative_or_mismatched_ack_never_qualifies(self) -> None:
        payload, envelope = _representative_envelope()
        digest = hashlib.sha256(payload).hexdigest()
        event_id = "loc-" + digest
        base = _server_response(payload, envelope)
        cases: list[dict] = []
        missing = deepcopy(base)
        del missing["delivery_ack"]
        cases.append(missing)
        wrong_scope = deepcopy(base)
        wrong_scope["delivery_scope"] = "guardian_delivered"
        cases.append(wrong_scope)
        negative = deepcopy(base)
        negative["delivery_ack"]["status"] = "rejected"
        cases.append(negative)
        wrong_device = deepcopy(base)
        wrong_device["delivery_ack"]["device_id"] = "other-device"
        cases.append(wrong_device)
        wrong_event = deepcopy(base)
        wrong_event["delivery_ack"]["event_id"] = "loc-" + ("0" * 64)
        cases.append(wrong_event)
        extra_ack_field = deepcopy(base)
        extra_ack_field["delivery_ack"]["guardian_delivered"] = True
        cases.append(extra_ack_field)

        for candidate in cases:
            with self.subTest(keys=sorted(candidate)):
                encoded = json.dumps(candidate, separators=(",", ":")).encode("utf-8")
                self.assertFalse(
                    _strict_positive_ack(
                        transport_accepted=True,
                        response_bytes=encoded,
                        expected_device_id=envelope["device_id"],
                        expected_event_id=event_id,
                        expected_payload_sha256=digest,
                    )
                )

    def test_ack_parser_is_bounded_exact_and_coordinate_free(self) -> None:
        parse = self.function_body(
            "static parse_ack_status_t parse_delivery_ack(",
            "egolink_location_outbox_finish_status_t\n",
        )
        for marker in (
            "EGOLINK_LOCATION_OUTBOX_RESPONSE_MAX_BYTES",
            'memchr(response_json, 0, response_length)',
            "exact_ack_shape(ack)",
            "EGOLINK_LOCATION_OUTBOX_DELIVERY_SCOPE",
            "EGOLINK_OUTBOX_ACK_CONTRACT_VERSION",
            'string_item_equals(status, "accepted")',
            "EGOLINK_LOCATION_OUTBOX_EVENT_PREFIX",
            "EGOLINK_LOCATION_OUTBOX_ACK_PREFIX",
        ):
            self.assertIn(marker, parse)
        self.assertIn("EGOLINK_LOCATION_OUTBOX_JSON_SAFE_INTEGER_MAX", self.source)
        for private in ("latitude", "longitude", "coordinate"):
            self.assertNotIn(private, self.source.casefold())

    def test_scratch_is_cleared_and_results_do_not_contain_payload(self) -> None:
        body = self.function_body(
            "egolink_location_outbox_emit_and_enqueue(",
            "static size_t object_member_count(",
        )
        self.assertGreaterEqual(body.count("clear_scratch(scratch, scratch_capacity)"), 6)
        result_definition = self.header[
            self.header.index("typedef struct {\n    egolink_location_state_emit_result_t"):
            self.header.index("} egolink_location_outbox_enqueue_result_t;")
        ]
        self.assertNotIn("char payload[", result_definition)
        self.assertNotIn("char envelope[", result_definition)

    def test_serialization_and_exactly_once_nonclaims_are_explicit(self) -> None:
        normalized = " ".join(self.header.split())
        self.assertIn("caller-owned mutex", normalized)
        self.assertIn("deduplicated before policy reduction", normalized)
        self.assertIn("exactly-once delivery", normalized)

    def test_component_cross_compiles_for_esp32s3_with_warnings_as_errors(self) -> None:
        compiler_candidates = [
            shutil.which("xtensa-esp32s3-elf-gcc"),
            Path(
                "C:/Espressif/tools/xtensa-esp-elf/esp-14.2.0_20241119/"
                "xtensa-esp-elf/bin/xtensa-esp32s3-elf-gcc.exe"
            ),
        ]
        compiler = next(
            (
                Path(candidate)
                for candidate in compiler_candidates
                if candidate and Path(candidate).is_file()
            ),
            None,
        )
        idf_candidates = [
            Path(os.environ["IDF_PATH"]) if os.environ.get("IDF_PATH") else None,
            Path("C:/Espressif/v5.4.2/esp-idf"),
        ]
        idf_path = next(
            (candidate for candidate in idf_candidates if candidate and candidate.is_dir()),
            None,
        )
        if compiler is None or idf_path is None:
            self.skipTest("ESP cross compiler or ESP-IDF headers unavailable")

        include_paths = (
            COMPONENT / "include",
            COMPONENT.parent / "location_state_emitter" / "include",
            COMPONENT.parent / "persistent_priority_outbox" / "include",
            idf_path / "components" / "json" / "cJSON",
            idf_path / "components" / "mbedtls" / "mbedtls" / "include",
        )
        with tempfile.TemporaryDirectory(prefix="egolink-loc-outbox-") as temp_dir:
            result = subprocess.run(
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
                    *(f"-I{path}" for path in include_paths),
                    "-c",
                    str(SOURCE),
                    "-o",
                    str(Path(temp_dir) / "location_outbox_adapter.o"),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()

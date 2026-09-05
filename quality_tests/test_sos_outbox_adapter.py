"""Static/spec coverage for the dormant SOS-010E delivery adapter.

The Python oracle checks the existing SOS-010D wire response and exact-byte
identity rules. It does not execute the Xtensa object and is not transport,
flash, reboot, Guardian-delivery, hardware, or P0-SOS evidence.
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

from quality_tests.test_sos_orchestrator_firmware import _payload
from pc_simulator.persistent_priority_outbox import PersistentPriorityOutbox
from server.manual_sos_delivery_ack import (
    ACK_CONTRACT_VERSION,
    DELIVERY_SCOPE,
    build_manual_sos_delivery_ack,
)
from server.manual_sos_store import ManualSosStore


ROOT = Path(__file__).resolve().parents[1]
COMPONENT = (
    ROOT / "firmware" / "mqtt_heartbeat" / "components" / "sos_outbox_adapter"
)
SOURCE = COMPONENT / "sos_outbox_adapter.c"
HEADER = COMPONENT / "include" / "sos_outbox_adapter.h"
CMAKE = COMPONENT / "CMakeLists.txt"
ORCHESTRATOR_SOURCE = (
    COMPONENT.parent / "sos_orchestrator" / "sos_orchestrator.c"
)
APP_MAIN = ROOT / "firmware" / "mqtt_heartbeat" / "main" / "app_main.c"
PACKET = ROOT / "docs" / "tasks" / "active" / "SOS-010_SOS_WALKING_SKELETON.md"

ACK_FIELDS = {
    "contract_version",
    "ack_id",
    "device_id",
    "event_id",
    "payload_sha256",
    "status",
    "ack_time_ms",
}
RESPONSE_FIELDS = {"ok", "result", "delivery_ack", "delivery_scope"}
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
JSON_SAFE_INTEGER_MAX = (1 << 53) - 1


class _DuplicateKey(ValueError):
    pass


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey(key)
        result[key] = value
    return result


def _reject_constant(value: str):
    raise ValueError(value)


def _server_response(
    payload: bytes,
    *,
    store_status: str,
    device_id: str,
    event_id: str,
) -> dict:
    digest = hashlib.sha256(payload).hexdigest()
    ingest_result = {
        "status": store_status,
        "identity": {"device_id": device_id, "event_id": event_id},
        "payload_sha256": digest,
    }
    return {
        "ok": True,
        "result": {"status": store_status},
        "delivery_ack": build_manual_sos_delivery_ack(
            payload, ingest_result, ack_time_ms=1_800_000_003_000
        ),
        "delivery_scope": DELIVERY_SCOPE,
    }


def _encode(response: dict) -> bytes:
    return json.dumps(response, sort_keys=True, separators=(",", ":")).encode(
        "ascii"
    )


def _strict_positive_response(
    *,
    http_status: int,
    response_bytes: bytes,
    expected_device_id: str,
    expected_event_id: str,
    expected_payload_sha256: str,
) -> bool:
    """Deletion-eligibility oracle, not a second device runtime."""

    if not 200 <= http_status <= 299:
        return False
    if not response_bytes or len(response_bytes) > 2048:
        return False
    if b"\0" in response_bytes or b"\\" in response_bytes:
        return False
    if any(
        byte not in (9, 10, 13) and not 0x20 <= byte <= 0x7E
        for byte in response_bytes
    ):
        return False
    try:
        response = json.loads(
            response_bytes,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, ValueError, _DuplicateKey):
        return False
    if not isinstance(response, dict) or set(response) != RESPONSE_FIELDS:
        return False
    if response["ok"] is not True or response["delivery_scope"] != DELIVERY_SCOPE:
        return False
    result = response["result"]
    if (
        not isinstance(result, dict)
        or set(result) != {"status"}
        or result["status"] not in {"accepted", "duplicate"}
    ):
        return False
    ack = response["delivery_ack"]
    if not isinstance(ack, dict) or set(ack) != ACK_FIELDS:
        return False
    digest = ack.get("payload_sha256")
    ack_time = ack.get("ack_time_ms")
    if not isinstance(digest, str) or SHA256.fullmatch(digest) is None:
        return False
    if type(ack_time) is not int or not 0 <= ack_time <= JSON_SAFE_INTEGER_MAX:
        return False
    if (
        ack.get("contract_version") != ACK_CONTRACT_VERSION
        or ack.get("status") != "accepted"
        or not isinstance(ack.get("device_id"), str)
        or SAFE_ID.fullmatch(ack["device_id"]) is None
        or not isinstance(ack.get("event_id"), str)
        or SAFE_ID.fullmatch(ack["event_id"]) is None
        or ack.get("ack_id") != "ack-" + digest
    ):
        return False
    return (
        ack["device_id"] == expected_device_id
        and ack["event_id"] == expected_event_id
        and digest == expected_payload_sha256
    )


class SosOutboxAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.header = HEADER.read_text(encoding="utf-8")
        cls.cmake = CMAKE.read_text(encoding="utf-8")
        cls.orchestrator = ORCHESTRATOR_SOURCE.read_text(encoding="utf-8")
        cls.packet = PACKET.read_text(encoding="utf-8")

    def function_body(self, name: str, next_name: str) -> str:
        start = self.source.index(name)
        end = self.source.index(next_name, start + len(name))
        return self.source[start:end]

    def representative(self) -> tuple[str, bytes, str]:
        event_id, payload, _ = _payload(
            device_id="wearable-1",
            boot_count=7,
            session_id="boot-session-7",
            sequence=41,
            edge_time_ms=1_800_000_002_160,
        )
        return event_id, payload, hashlib.sha256(payload).hexdigest()

    def test_component_is_dormant_and_has_no_transport_or_hardware_owner(self) -> None:
        self.assertIn('SRCS "sos_outbox_adapter.c"', self.cmake)
        self.assertIn(
            "REQUIRES sos_orchestrator persistent_priority_outbox json mbedtls",
            self.cmake,
        )
        for option in (
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wconversion",
            "-Wformat=2",
            "-Wshadow",
            "-Wsign-conversion",
        ):
            self.assertIn(option, self.cmake)
        for forbidden in (
            "app_main",
            "esp_http_client",
            "esp_wifi",
            "sim7670",
            "mqtt_client",
            "gpio_",
            "nvs_",
            "esp_partition",
            "freertos/",
            "esp_log",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.source.casefold())
        self.assertNotIn("sos_outbox_adapter", APP_MAIN.read_text(encoding="utf-8"))

    def test_orchestrator_remains_the_only_manual_sos_enqueue_path(self) -> None:
        self.assertIn("egolink_outbox_enqueue(", self.orchestrator)
        self.assertIn("EGOLINK_OUTBOX_PRIORITY_CRITICAL", self.orchestrator)
        self.assertNotIn("egolink_outbox_enqueue(", self.source)
        normalized = " ".join((self.header + self.packet).split())
        self.assertIn("does not initialize or own, the shared outbox", normalized)
        self.assertIn("must not enqueue a second copy", normalized)

    def test_exact_orchestrator_bytes_match_accepted_and_duplicate_server_ack(self) -> None:
        event_id, payload, digest = self.representative()
        with tempfile.TemporaryDirectory(prefix="egolink-sos-e-store-") as temp:
            store = ManualSosStore(Path(temp) / "message_hub.sqlite3")
            accepted = store.ingest(payload, server_receive_time_ms=1000)
            duplicate = store.ingest(payload, server_receive_time_ms=1001)
        self.assertEqual("accepted", accepted["status"])
        self.assertEqual("duplicate", duplicate["status"])
        for result in (accepted, duplicate):
            response = _server_response(
                payload,
                store_status=result["status"],
                device_id="wearable-1",
                event_id=event_id,
            )
            self.assertTrue(
                _strict_positive_response(
                    http_status=200,
                    response_bytes=_encode(response),
                    expected_device_id="wearable-1",
                    expected_event_id=event_id,
                    expected_payload_sha256=digest,
                )
            )
            self.assertEqual("ack-" + digest, response["delivery_ack"]["ack_id"])

    def test_missing_conflicting_negative_and_extra_semantics_never_qualify(self) -> None:
        event_id, payload, digest = self.representative()
        base = _server_response(
            payload,
            store_status="accepted",
            device_id="wearable-1",
            event_id=event_id,
        )
        candidates = []
        for root_key in RESPONSE_FIELDS:
            candidate = deepcopy(base)
            del candidate[root_key]
            candidates.append(candidate)
        extra_root = deepcopy(base)
        extra_root["guardian_delivered"] = True
        candidates.append(extra_root)
        for invalid_result in ("pending", "rejected", "ok"):
            candidate = deepcopy(base)
            candidate["result"]["status"] = invalid_result
            candidates.append(candidate)
        extra_result = deepcopy(base)
        extra_result["result"]["delivery"] = "accepted"
        candidates.append(extra_result)
        wrong_scope = deepcopy(base)
        wrong_scope["delivery_scope"] = "guardian_delivered"
        candidates.append(wrong_scope)
        for field, value in (
            ("contract_version", "wrong"),
            ("status", "rejected"),
            ("ack_id", "ack-" + "0" * 64),
            ("device_id", "another-device"),
            ("event_id", "sos-b7-q42-t1800000002160"),
            ("payload_sha256", "0" * 64),
            ("ack_time_ms", -1),
        ):
            candidate = deepcopy(base)
            candidate["delivery_ack"][field] = value
            candidates.append(candidate)
        extra_ack = deepcopy(base)
        extra_ack["delivery_ack"]["guardian_acknowledged"] = True
        candidates.append(extra_ack)

        for candidate in candidates:
            with self.subTest(candidate=candidate):
                self.assertFalse(
                    _strict_positive_response(
                        http_status=200,
                        response_bytes=_encode(candidate),
                        expected_device_id="wearable-1",
                        expected_event_id=event_id,
                        expected_payload_sha256=digest,
                    )
                )

    def test_non_2xx_duplicate_keys_truncation_and_oversize_never_qualify(self) -> None:
        event_id, payload, digest = self.representative()
        response = _encode(
            _server_response(
                payload,
                store_status="accepted",
                device_id="wearable-1",
                event_id=event_id,
            )
        )
        common = {
            "expected_device_id": "wearable-1",
            "expected_event_id": event_id,
            "expected_payload_sha256": digest,
        }
        for status in (0, 199, 300, 400, 500):
            self.assertFalse(
                _strict_positive_response(
                    http_status=status, response_bytes=response, **common
                )
            )
        duplicate = response.replace(b'{"delivery_ack":', b'{"ok":true,"delivery_ack":', 1)
        malformed = (
            response[:-1],
            duplicate,
            response + b" trailing",
            response.replace(b'"accepted"', b'"acc\\u0065pted"', 1),
            response + b"\0",
            b"{" + b" " * 2048 + b"}",
        )
        for candidate in malformed:
            with self.subTest(length=len(candidate)):
                self.assertFalse(
                    _strict_positive_response(
                        http_status=200, response_bytes=candidate, **common
                    )
                )

    def test_begin_selects_once_and_never_constructs_sos_view_for_non_sos(self) -> None:
        body = self.function_body(
            "egolink_sos_outbox_begin_status_t egolink_sos_outbox_begin_attempt(",
            "static bool active_item_matches(",
        )
        begin_at = body.index("egolink_outbox_begin_send_attempt(")
        event_guard_at = body.index("send_item->record.event_type")
        view_at = body.index("send_view->payload = send_item->payload")
        self.assertLess(begin_at, event_guard_at)
        self.assertLess(event_guard_at, view_at)
        self.assertIn("EGOLINK_SOS_OUTBOX_BEGIN_NON_SOS_HEAD", body)
        self.assertIn("if (adapter->attempt_active)", body)
        self.assertIn("manual_sos_send_item_valid(adapter, send_item)", body)
        self.assertIn("egolink_outbox_record_transport_result(", body)
        self.assertIn("SOS_RECORD_INVALID_ERROR_CODE", body)
        non_sos_section = body[
            body.index("if (strcmp("):body.index("if (!manual_sos_send_item_valid")
        ]
        self.assertNotIn("send_view->payload", non_sos_section)

    def test_record_validation_binds_critical_lineage_and_exact_payload_hash(self) -> None:
        validation = self.function_body(
            "static bool manual_sos_send_item_valid(",
            "static void clear_active(",
        )
        for marker in (
            "EGOLINK_SOS_ORCHESTRATOR_EVENT_TYPE",
            "EGOLINK_OUTBOX_PRIORITY_CRITICAL",
            "EGOLINK_OUTBOX_SOURCE_TIME_BOOT_MONOTONIC_MS",
            "EGOLINK_OUTBOX_SEND_ATTEMPT_STARTED",
            "EGOLINK_OUTBOX_ATTEMPT_PENDING",
            "EGOLINK_SOS_ORCHESTRATOR_PAYLOAD_MAX_BYTES",
            "event_id_matches_lineage(record)",
            "exact_payload_hash(",
        ):
            self.assertIn(marker, validation)
        self.assertIn('static const char prefix[] = "sos-b"', self.source)
        self.assertIn("UINT64_MAX - digit", self.source)

    def test_strict_parse_precedes_transport_accept_and_positive_ack(self) -> None:
        body = self.function_body(
            "egolink_sos_outbox_finish_status_t egolink_sos_outbox_finish_attempt(",
            "const char *egolink_sos_outbox_begin_status_name(",
        )
        precondition_at = body.index("active_item_matches(adapter, send_item)")
        http_guard_at = body.index("if (!http_success)")
        parse_at = body.index("parse_delivery_response(")
        accepted_transport_at = body.index(
            "result->transport_status = egolink_outbox_record_transport_result(",
            parse_at,
        )
        ack_at = body.index("egolink_outbox_handle_ack(")
        self.assertLess(precondition_at, http_guard_at)
        self.assertLess(http_guard_at, parse_at)
        self.assertLess(parse_at, accepted_transport_at)
        self.assertLess(accepted_transport_at, ack_at)
        for marker in (
            "exact_object_shape(",
            "EGOLINK_SOS_OUTBOX_RESPONSE_MAX_BYTES",
            "EGOLINK_SOS_OUTBOX_DELIVERY_SCOPE",
            "EGOLINK_OUTBOX_ACK_CONTRACT_VERSION",
            'string_item_equals(result_status, "accepted")',
            'string_item_equals(result_status, "duplicate")',
            "adapter->active_event_id",
            "adapter->active_payload_sha256",
            "adapter->device_id",
        ):
            self.assertIn(marker, self.source)

    def test_bad_2xx_retries_then_duplicate_server_ack_deletes(self) -> None:
        event_id, original_payload, event = _payload(
            device_id="wearable-1",
            boot_count=7,
            session_id="boot-session-7",
            sequence=41,
            edge_time_ms=1_800_000_002_160,
        )
        self.assertTrue(original_payload)
        exact_payload = json.dumps(
            event, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        digest = hashlib.sha256(exact_payload).hexdigest()
        with tempfile.TemporaryDirectory(prefix="egolink-sos-e-retry-") as temp:
            store = ManualSosStore(Path(temp) / "message_hub.sqlite3")
            outbox = PersistentPriorityOutbox(
                Path(temp) / "outbox",
                device_id="wearable-1",
                max_records=4,
                reserved_critical_records=1,
                max_total_payload_bytes=4096,
                max_payload_bytes=2048,
                base_retry_ms=1000,
                max_retry_ms=4000,
                tombstone_capacity=4,
            )
            record = outbox.enqueue(
                event_id=event_id,
                event_type="manual_sos",
                priority="critical",
                payload=event,
                source_event_time_ms=event["timestamp_ms"],
                boot_count=event["model_result"]["boot_count"],
                session_id=event["model_result"]["session_id"],
                source_sequence=event["model_result"]["source_sequence"],
                now_ms=0,
            )
            self.assertEqual(digest, record["payload_sha256"])
            first_attempt = outbox.begin_send_attempt(now_ms=0)
            accepted = store.ingest(exact_payload, server_receive_time_ms=100)
            self.assertEqual("accepted", accepted["status"])
            valid_accepted = _encode(
                _server_response(
                    exact_payload,
                    store_status="accepted",
                    device_id="wearable-1",
                    event_id=event_id,
                )
            )
            self.assertFalse(
                _strict_positive_response(
                    http_status=200,
                    response_bytes=valid_accepted[:-1],
                    expected_device_id="wearable-1",
                    expected_event_id=event_id,
                    expected_payload_sha256=digest,
                )
            )
            outbox.record_transport_result(
                attempt_token=first_attempt["last_attempt_token"],
                accepted_by_transport=False,
                now_ms=100,
                error_code="SOS_RESPONSE_INVALID",
            )
            retained = outbox.snapshot(now_ms=100)["records"][0]
            self.assertEqual("retry_wait", retained["send_state"])
            self.assertIsNone(outbox.begin_send_attempt(now_ms=999))

            second_attempt = outbox.begin_send_attempt(now_ms=1000)
            duplicate = store.ingest(exact_payload, server_receive_time_ms=1100)
            self.assertEqual("duplicate", duplicate["status"])
            valid_duplicate = _encode(
                _server_response(
                    exact_payload,
                    store_status="duplicate",
                    device_id="wearable-1",
                    event_id=event_id,
                )
            )
            self.assertTrue(
                _strict_positive_response(
                    http_status=200,
                    response_bytes=valid_duplicate,
                    expected_device_id="wearable-1",
                    expected_event_id=event_id,
                    expected_payload_sha256=digest,
                )
            )
            outbox.record_transport_result(
                attempt_token=second_attempt["last_attempt_token"],
                accepted_by_transport=True,
                now_ms=1100,
            )
            response = json.loads(valid_duplicate)
            self.assertEqual(
                "deleted_after_positive_ack",
                outbox.handle_ack(response["delivery_ack"]),
            )
            self.assertEqual(0, outbox.snapshot(now_ms=1100)["queued_count"])

    def test_ack_commit_failure_keeps_active_item_and_requires_core_recovery(self) -> None:
        body = self.function_body(
            "egolink_sos_outbox_finish_status_t egolink_sos_outbox_finish_attempt(",
            "const char *egolink_sos_outbox_begin_status_name(",
        )
        ack_at = body.index("result->ack_status = egolink_outbox_handle_ack(")
        failure_return = body.index(
            "return EGOLINK_SOS_OUTBOX_FINISH_ACK_STATE_FAILED", ack_at
        )
        success_consume = body.index("consume_active_attempt(adapter, send_item)", ack_at)
        self.assertLess(success_consume, failure_return)
        failure_branch = body[success_consume:failure_return]
        self.assertEqual(2, failure_branch.count("consume_active_attempt"))
        trailing_failure = body[body.rfind("if (result->ack_status", ack_at):failure_return]
        self.assertNotIn("consume_active_attempt", trailing_failure.split("return", 1)[-1])
        normalized = " ".join((self.header + self.packet).split()).casefold()
        self.assertIn("latches any slot-write failure", normalized)
        self.assertIn("reinitialize from the last valid mirror", normalized)
        self.assertIn("new attempt", normalized)

    def test_payload_is_borrowed_bounded_and_securely_wiped(self) -> None:
        adapter_definition = self.header[
            self.header.index("typedef struct {\n    egolink_outbox_t *outbox;"):
            self.header.index("} egolink_sos_outbox_adapter_t;")
        ]
        result_definitions = self.header[
            self.header.index("typedef struct {\n    egolink_outbox_status_t outbox_status;"):
            self.header.index("/* Binding is memory-only")
        ]
        self.assertNotIn("uint8_t payload[", adapter_definition)
        self.assertNotIn("uint8_t payload[", result_definitions)
        self.assertIn("const uint8_t *payload", self.header)
        self.assertIn("exact persisted byte range", self.header)
        self.assertIn("volatile uint8_t *cursor", self.source)
        self.assertIn(
            "secure_zero(send_item, sizeof(*send_item))",
            self.source,
        )
        self.assertIsNone(
            re.search(r"\b(?:malloc|calloc|realloc|free)\s*\(", self.source)
        )

    def test_single_owner_and_nonclaims_are_explicit(self) -> None:
        normalized = " ".join((self.header + self.packet).split()).casefold()
        for phrase in (
            "exactly one caller must serialize",
            "non-sos head",
            "already-initialized outbox",
            "does not initialize or own",
            "http success alone",
            "adds no transport",
            "default-unwired",
        ):
            self.assertIn(phrase, normalized)

    def test_actual_c_cross_compiles_for_esp32s3_with_warnings_as_errors(self) -> None:
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
            self.skipTest("ESP32-S3 cross compiler or ESP-IDF headers unavailable")

        include_paths = (
            COMPONENT / "include",
            COMPONENT.parent / "sos_orchestrator" / "include",
            COMPONENT.parent / "sos_input" / "include",
            COMPONENT.parent / "persistent_priority_outbox" / "include",
            COMPONENT.parent / "location_policy_core" / "include",
            idf_path / "components" / "json" / "cJSON",
            idf_path / "components" / "mbedtls" / "mbedtls" / "include",
        )
        with tempfile.TemporaryDirectory(prefix="egolink-sos-outbox-") as temp:
            output = Path(temp) / "sos_outbox_adapter.o"
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
                    str(output),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue(output.is_file())


if __name__ == "__main__":
    unittest.main()

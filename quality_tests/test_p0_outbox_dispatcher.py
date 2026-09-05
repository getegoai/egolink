"""Focused OUTBOX-010E checks for the dormant unified P0 dispatcher.

The actual C source is cross-compiled for ESP32-S3. The executable Python
scenarios exercise the accepted host outbox and server durable-ACK helpers;
they are not target runtime, flash, reboot, network, Guardian/human delivery,
hardware, or P0 gate evidence.
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
import textwrap
import unittest

from pc_simulator.persistent_priority_outbox import PersistentPriorityOutbox
from quality_tests.test_location_state_mirror import envelope, location_state
from server.location_delivery_ack import build_location_state_delivery_ack
from server.location_state_runtime import LocationStateRuntimeMirror
from server.location_state_store import LocationStateStore


ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ROOT / "firmware" / "mqtt_heartbeat" / "components"
COMPONENT = COMPONENTS / "p0_outbox_dispatcher"
SOURCE = COMPONENT / "p0_outbox_dispatcher.c"
HEADER = COMPONENT / "include" / "p0_outbox_dispatcher.h"
CMAKE = COMPONENT / "CMakeLists.txt"
APP_MAIN = ROOT / "firmware" / "mqtt_heartbeat" / "main" / "app_main.c"
PACKET = (
    ROOT / "docs" / "tasks" / "active" / "OUTBOX-010_PERSISTENT_PRIORITY_OUTBOX.md"
)


def _esp_toolchain() -> tuple[Path, Path] | None:
    compiler_candidates = (
        shutil.which("xtensa-esp32s3-elf-gcc"),
        Path(
            "C:/Espressif/tools/xtensa-esp-elf/esp-14.2.0_20241119/"
            "xtensa-esp-elf/bin/xtensa-esp32s3-elf-gcc.exe"
        ),
    )
    compiler = next(
        (
            Path(candidate)
            for candidate in compiler_candidates
            if candidate and Path(candidate).is_file()
        ),
        None,
    )
    idf_candidates = (
        Path(os.environ["IDF_PATH"]) if os.environ.get("IDF_PATH") else None,
        Path("C:/Espressif/v5.4.2/esp-idf"),
    )
    idf = next(
        (candidate for candidate in idf_candidates if candidate and candidate.is_dir()),
        None,
    )
    return None if compiler is None or idf is None else (compiler, idf)


def _include_paths(idf: Path) -> tuple[Path, ...]:
    return (
        COMPONENT / "include",
        COMPONENTS / "location_outbox_adapter" / "include",
        COMPONENTS / "location_state_emitter" / "include",
        COMPONENTS / "persistent_priority_outbox" / "include",
        COMPONENTS / "sos_outbox_adapter" / "include",
        idf / "components" / "mbedtls" / "port" / "include",
        idf / "components" / "mbedtls" / "mbedtls" / "include",
        idf / "components" / "mbedtls" / "mbedtls" / "library",
    )


def _location_envelope(*, with_fix: bool) -> dict:
    seed = LocationStateRuntimeMirror()
    value = envelope(seed, location_state(1_000, with_fix=with_fix))
    value.pop("server_receive_time_ms", None)
    return value


def _wire(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _normalized_prose(value: str) -> str:
    without_comment_leaders = re.sub(r"(?m)^\s*\*\s?", "", value)
    return " ".join(without_comment_leaders.split())


class P0OutboxDispatcherTests(unittest.TestCase):
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

    def test_component_is_dormant_transport_free_and_warnings_are_errors(self) -> None:
        self.assertIn('SRCS "p0_outbox_dispatcher.c"', self.cmake)
        for dependency in (
            "location_outbox_adapter",
            "persistent_priority_outbox",
            "sos_outbox_adapter",
        ):
            self.assertIn(dependency, self.cmake)
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
            "esp_http_client",
            "esp_wifi",
            "mqtt_client",
            "freertos/",
            "xtaskcreate",
            "gpio_",
            "nvs_",
            "esp_partition",
            "esp_log",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.source.casefold())
        self.assertNotIn("p0_outbox_dispatcher", APP_MAIN.read_text(encoding="utf-8"))
        self.assertIn("config->enabled = false", self.source)

    def test_binding_enforces_one_shared_outbox_and_one_selector_owner(self) -> None:
        init_body = self.function_body(
            "egolink_p0_outbox_dispatcher_init(",
            "egolink_p0_outbox_dispatcher_begin(",
        )
        self.assertIn("location_adapter->outbox == internal->shared_outbox", self.source)
        self.assertIn("sos_adapter->outbox == internal->shared_outbox", self.source)
        self.assertIn("sos_adapter->attempt_active", init_body)
        self.assertEqual(1, self.source.count("egolink_sos_outbox_begin_attempt("))
        self.assertNotIn("egolink_outbox_begin_send_attempt(", self.source)
        normalized = _normalized_prose(self.header + self.packet)
        self.assertIn("only this dispatcher owner may invoke its begin/finish", normalized)
        self.assertIn("no second adapter or selector is allowed", normalized)
        for forbidden in (
            "egolink_location_outbox_adapter_init(",
            "egolink_location_outbox_adapter_deinit(",
            "egolink_sos_outbox_adapter_bind(",
            "egolink_sos_outbox_adapter_unbind(",
            "egolink_outbox_init(",
            "egolink_outbox_deinit(",
        ):
            self.assertNotIn(forbidden, self.source)

    def test_read_only_dependency_proof_is_exact_and_side_effect_free(self) -> None:
        name = "egolink_p0_outbox_dispatcher_dependencies_match("
        self.assertIn(name, self.header)
        body = self.function_body(name, "egolink_p0_outbox_dispatcher_status_name(")
        self.assertIn("internal->shared_outbox == shared_outbox", body)
        self.assertIn("internal->location_adapter == location_adapter", body)
        self.assertIn("adapters_bound(internal)", body)
        for forbidden in (
            "dispatcher_begin(",
            "dispatcher_finish(",
            "egolink_outbox_begin_send_attempt(",
            "egolink_outbox_finish_send_attempt(",
            "egolink_outbox_snapshot(",
            "http",
        ):
            self.assertNotIn(forbidden, body)

    def test_typed_view_borrows_exact_bytes_without_transport_secret(self) -> None:
        view_match = re.search(
            r"typedef struct \{(?P<body>[^{}]*const uint8_t \*payload;[^{}]*)\}\s*"
            r"egolink_p0_outbox_send_view_t;",
            self.header,
            re.DOTALL,
        )
        self.assertIsNotNone(view_match)
        body = view_match.group("body")
        for field in (
            "payload_length",
            "endpoint_path",
            "response_max_bytes",
            "completion_only",
            "attempt",
        ):
            self.assertIn(field, body)
        for secret in ("bearer", "authorization", "credential", "guardian_token"):
            self.assertNotIn(secret, body.casefold())
        self.assertIn('"/api/v1/safety-events/manual-sos"', self.header)
        self.assertIn('"/api/v1/location-states"', self.header)
        self.assertIn("send_view->payload = internal->canonical_item.payload", self.source)

    def test_only_manual_sos_or_exact_hashed_location_can_be_sent(self) -> None:
        begin_body = self.function_body(
            "egolink_p0_outbox_dispatcher_begin(", "map_sos_finish("
        )
        validator = self.function_body("location_send_item_valid(", "capture_attempt(")
        self.assertIn("EGOLINK_SOS_OUTBOX_BEGIN_READY", begin_body)
        self.assertIn("EGOLINK_SOS_OUTBOX_BEGIN_NON_SOS_HEAD", begin_body)
        self.assertIn("EGOLINK_LOCATION_OUTBOX_EVENT_TYPE", validator)
        self.assertIn("location_event_id_matches_hash(record)", validator)
        self.assertIn("exact_payload_hash(send_item)", validator)
        self.assertIn("EGOLINK_OUTBOX_SEND_ATTEMPT_STARTED", validator)
        self.assertIn("EGOLINK_OUTBOX_ATTEMPT_PENDING", validator)
        self.assertIn("mbedtls_sha256(", self.source)
        self.assertNotIn("cJSON", self.source)
        normalized = _normalized_prose(self.header)
        self.assertIn(
            "Full envelope semantics remain the responsibility of the only admitted producer, location_outbox_adapter",
            normalized,
        )

    def test_unknown_or_invalid_head_is_durably_failed_and_retained(self) -> None:
        body = self.function_body("settle_invalid_event(", "settle_invalid_sos_view(")
        self.assertIn("egolink_outbox_record_transport_result(", body)
        self.assertIn("false", body)
        self.assertIn("P0_INVALID_ROUTE_ERROR", body)
        self.assertIn("durable_failure_recorded = true", body)
        self.assertIn("durable_record_retained = true", body)
        self.assertIn("clear_active(internal)", body)
        self.assertIn("EGOLINK_P0_OUTBOX_INVALID_EVENT_RETAINED", body)

    def test_attempt_identity_and_internal_route_bind_finish(self) -> None:
        finish_body = self.function_body(
            "egolink_p0_outbox_dispatcher_finish(", "cancel_active("
        )
        routed = self.function_body("finish_active(", "egolink_p0_outbox_dispatcher_finish(")
        identity = self.function_body("attempt_identity_matches(", "active_view_matches(")
        for field in (
            "route",
            "device_id",
            "event_id",
            "payload_sha256",
            "attempt_token",
            "priority",
            "source_time_kind",
            "source_event_time_ms",
            "boot_count",
            "session_id",
            "source_sequence",
            "attempt_count",
        ):
            self.assertIn(field, identity)
        self.assertLess(
            finish_body.index("active_view_matches"),
            finish_body.index("finish_active("),
        )
        self.assertIn("internal->status.active_route", routed)
        self.assertEqual(1, routed.count("egolink_sos_outbox_finish_attempt("))
        self.assertEqual(1, routed.count("egolink_location_outbox_finish_attempt("))
        self.assertNotIn("send_view->attempt.route ==", routed)

    def test_location_semantic_ack_failures_end_attempt_but_state_faults_recover(self) -> None:
        body = self.function_body("map_location_finish(", "finish_active(")
        for terminal in (
            "EGOLINK_LOCATION_OUTBOX_FINISH_INVALID_RESPONSE",
            "EGOLINK_LOCATION_OUTBOX_FINISH_INVALID_SCOPE",
            "EGOLINK_LOCATION_OUTBOX_FINISH_INVALID_ACK",
            "EGOLINK_OUTBOX_STALE_OR_UNKNOWN_ACK",
            "EGOLINK_OUTBOX_ACK_IDENTITY_MISMATCH",
        ):
            self.assertIn(terminal, body)
        for recovery in (
            "EGOLINK_OUTBOX_FAULT_LATCHED",
            "EGOLINK_OUTBOX_COUNTER_OVERFLOW",
            "EGOLINK_OUTBOX_STORAGE_ERROR",
            "EGOLINK_OUTBOX_CRYPTO_ERROR",
        ):
            self.assertIn(recovery, body)
        terminal_block = body[
            body.index("case EGOLINK_OUTBOX_NEGATIVE_ACK:") :
            body.index("case EGOLINK_OUTBOX_NOT_INITIALIZED:")
        ]
        self.assertIn("clear_active(internal)", terminal_block)
        self.assertIn("EGOLINK_P0_OUTBOX_FINISHED_RETAINED", terminal_block)
        self.assertNotIn("EGOLINK_P0_OUTBOX_PHASE_RECOVERY_REQUIRED", terminal_block)

    def test_sos_state_failure_keeps_private_canonical_but_clears_outward_view(self) -> None:
        body = self.function_body("map_sos_finish(", "map_location_finish(")
        recovery = body[
            body.index("case EGOLINK_SOS_OUTBOX_FINISH_ACK_STATE_FAILED:") :
            body.index("case EGOLINK_SOS_OUTBOX_FINISH_ATTEMPT_MISMATCH:")
        ]
        self.assertIn("private_canonical_item_retained = true", recovery)
        self.assertIn("EGOLINK_P0_OUTBOX_PHASE_RECOVERY_REQUIRED", recovery)
        self.assertIn("EGOLINK_P0_OUTBOX_MUST_FINISH_OR_RECOVER", recovery)
        finish_active = self.function_body(
            "finish_active(", "egolink_p0_outbox_dispatcher_finish("
        )
        self.assertLess(
            finish_active.index("invalidate_payload_view(send_view)"),
            finish_active.index("egolink_sos_outbox_finish_attempt("),
        )
        normalized = _normalized_prose(self.header + self.packet)
        self.assertIn("private canonical item to remain for exact retry/recovery", normalized)

    def test_cancel_and_close_settle_send_ready_and_never_close_dependencies(self) -> None:
        cancel = self.function_body(
            "egolink_p0_outbox_dispatcher_cancel(", "close_bindings("
        )
        close = self.function_body(
            "egolink_p0_outbox_dispatcher_close(",
            "egolink_p0_outbox_dispatcher_current_status(",
        )
        self.assertIn("cancel_active(", cancel)
        self.assertIn("P0_CANCELLED_ERROR", self.source)
        self.assertIn("EGOLINK_P0_OUTBOX_MUST_FINISH_OR_RECOVER", cancel + close)
        for forbidden in (
            "egolink_outbox_deinit(",
            "egolink_location_outbox_adapter_deinit(",
            "egolink_sos_outbox_adapter_unbind(",
        ):
            self.assertNotIn(forbidden, cancel + close)

    def test_bad_2xx_ack_backs_off_then_duplicate_server_ack_deletes(self) -> None:
        value = _location_envelope(with_fix=False)
        payload = _wire(value)
        digest = hashlib.sha256(payload).hexdigest()
        event_id = "loc-" + digest

        with tempfile.TemporaryDirectory(prefix="egolink-p0-dispatch-") as temp:
            root = Path(temp)
            outbox = PersistentPriorityOutbox(
                root / "outbox", device_id=value["device_id"]
            )
            record = outbox.enqueue(
                event_id=event_id,
                event_type="location_state",
                priority="normal",
                payload=value,
                source_event_time_ms=value["event_time_ms"],
                boot_count=value["boot_count"],
                session_id=value["session_id"],
                source_sequence=value["sequence_id"],
                now_ms=0,
            )
            self.assertEqual(digest, record["payload_sha256"])
            first = outbox.begin_send_attempt(now_ms=0)
            self.assertIsNotNone(first)

            store = LocationStateStore(root / "location.sqlite3")
            accepted = store.ingest(value, server_receive_time_ms=10_000)
            correct = build_location_state_delivery_ack(
                payload, value, accepted, ack_time_ms=10_001
            )
            wrong = deepcopy(correct)
            wrong["device_id"] = "wrong-device"
            self.assertEqual(
                "recorded",
                outbox.record_transport_result(
                    attempt_token=first["last_attempt_token"],
                    accepted_by_transport=True,
                    now_ms=1,
                ),
            )
            self.assertEqual("identity_mismatch", outbox.handle_ack(wrong))
            retained = outbox.snapshot(now_ms=2)
            self.assertEqual(1, retained["queued_count"])
            self.assertEqual(1, retained["awaiting_positive_ack_count"])
            self.assertEqual("awaiting_positive_ack", retained["records"][0]["send_state"])
            self.assertIsNone(outbox.begin_send_attempt(now_ms=999))

            second = outbox.begin_send_attempt(now_ms=1_000)
            self.assertIsNotNone(second)
            self.assertNotEqual(first["last_attempt_token"], second["last_attempt_token"])
            duplicate = store.ingest(value, server_receive_time_ms=10_002)
            self.assertEqual("duplicate", duplicate["status"])
            ack = build_location_state_delivery_ack(
                payload, value, duplicate, ack_time_ms=10_003
            )
            self.assertEqual(
                "recorded",
                outbox.record_transport_result(
                    attempt_token=second["last_attempt_token"],
                    accepted_by_transport=True,
                    now_ms=1_001,
                ),
            )
            self.assertEqual("deleted_after_positive_ack", outbox.handle_ack(ack))
            deleted = outbox.snapshot(now_ms=1_002)
            self.assertEqual(0, deleted["queued_count"])
            self.assertEqual(1, deleted["ack_tombstone_count"])

    def test_representative_1_8kib_location_bytes_bind_accepted_and_duplicate_ack(self) -> None:
        value = _location_envelope(with_fix=True)
        payload = _wire(value)
        self.assertGreaterEqual(len(payload), 1_750)
        self.assertLessEqual(len(payload), 2_048)
        digest = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory(prefix="egolink-p0-location-ack-") as temp:
            store = LocationStateStore(Path(temp) / "location.sqlite3")
            accepted = store.ingest(value, server_receive_time_ms=11_000)
            duplicate = store.ingest(value, server_receive_time_ms=11_001)
        first = build_location_state_delivery_ack(
            payload, value, accepted, ack_time_ms=11_002
        )
        second = build_location_state_delivery_ack(
            payload, value, duplicate, ack_time_ms=11_003
        )
        self.assertEqual("accepted", accepted["status"])
        self.assertEqual("duplicate", duplicate["status"])
        self.assertEqual("loc-" + digest, first["event_id"])
        self.assertEqual("ack-" + digest, first["ack_id"])
        self.assertEqual(first["event_id"], second["event_id"])
        self.assertEqual(first["payload_sha256"], second["payload_sha256"])

    def test_actual_source_cross_compiles_and_sizes_are_bounded(self) -> None:
        toolchain = _esp_toolchain()
        if toolchain is None:
            self.skipTest("ESP32-S3 compiler or ESP-IDF 5.4.2 is unavailable")
        compiler, idf = toolchain
        includes = [argument for path in _include_paths(idf) for argument in ("-I", str(path))]
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
        with tempfile.TemporaryDirectory(prefix="egolink-p0-dispatch-compile-") as temp:
            temp_path = Path(temp)
            source_object = temp_path / "dispatcher.o"
            compile_source = subprocess.run(
                [*common, "-c", str(SOURCE), "-o", str(source_object)],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            self.assertEqual(
                0,
                compile_source.returncode,
                msg=compile_source.stdout + compile_source.stderr,
            )

            probe_source = temp_path / "probe.c"
            probe_source.write_text(
                textwrap.dedent(
                    """
                    #include "p0_outbox_dispatcher.h"
                    char probe_context[sizeof(egolink_p0_outbox_dispatcher_t)];
                    char probe_send_view[sizeof(egolink_p0_outbox_send_view_t)];
                    char probe_snapshot[sizeof(egolink_p0_outbox_dispatcher_snapshot_t)];
                    char probe_begin_result[sizeof(egolink_p0_outbox_begin_result_t)];
                    char probe_finish_result[sizeof(egolink_p0_outbox_finish_result_t)];
                    _Static_assert(sizeof(egolink_p0_outbox_dispatcher_t) == 8192U,
                                   "public context drift");
                    int p0_dispatcher_header_probe(void) { return 0; }
                    """
                ),
                encoding="utf-8",
            )
            probe_object = temp_path / "probe.o"
            compile_probe = subprocess.run(
                [*common, "-c", str(probe_source), "-o", str(probe_object)],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            self.assertEqual(
                0,
                compile_probe.returncode,
                msg=compile_probe.stdout + compile_probe.stderr,
            )

            internal_source = temp_path / "internal_probe.c"
            internal_source.write_text(
                '#include "p0_outbox_dispatcher.c"\n'
                "char probe_internal[sizeof(p0_outbox_dispatcher_internal_t)];\n",
                encoding="utf-8",
            )
            internal_object = temp_path / "internal_probe.o"
            compile_internal = subprocess.run(
                [
                    *common,
                    "-I",
                    str(COMPONENT),
                    "-c",
                    str(internal_source),
                    "-o",
                    str(internal_object),
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            self.assertEqual(
                0,
                compile_internal.returncode,
                msg=compile_internal.stdout + compile_internal.stderr,
            )

            nm = compiler.with_name(compiler.name.replace("gcc", "nm"))
            self.assertTrue(nm.is_file(), msg=f"missing size tool: {nm}")
            sizes: dict[str, int] = {}
            for object_path in (probe_object, internal_object):
                listing = subprocess.run(
                    [str(nm), "-S", str(object_path)],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                self.assertEqual(0, listing.returncode, msg=listing.stderr)
                for line in listing.stdout.splitlines():
                    match = re.search(
                        r"^[0-9a-fA-F]+\s+([0-9a-fA-F]+)\s+\w\s+(probe_\w+)$",
                        line.strip(),
                    )
                    if match:
                        sizes[match.group(2)] = int(match.group(1), 16)

            self.assertEqual(8192, sizes["probe_context"])
            self.assertLessEqual(sizes["probe_internal"], sizes["probe_context"])
            self.assertLessEqual(sizes["probe_send_view"], 768)
            self.assertLessEqual(sizes["probe_snapshot"], 1024)
            self.assertLessEqual(sizes["probe_begin_result"], 128)
            self.assertLessEqual(sizes["probe_finish_result"], 128)

            stack_file = source_object.with_suffix(".su")
            stack_sizes = []
            for line in stack_file.read_text(encoding="utf-8").splitlines():
                fields = line.split("\t")
                if len(fields) >= 2 and fields[1].isdigit():
                    stack_sizes.append(int(fields[1]))
            self.assertTrue(stack_sizes)
            self.assertLessEqual(max(stack_sizes), 192)


if __name__ == "__main__":
    unittest.main()

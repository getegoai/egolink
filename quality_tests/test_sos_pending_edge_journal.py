"""Focused SOS-010G pending-edge journal/replay checks.

The Python reference below executes the frozen wire/integrity and transition
semantics. The actual C sources and an integration harness are cross-compiled
for ESP32-S3; the harness runs only if a real native GCC/Clang is available.
No test supplies a real persistence backend or touches hardware/network.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import textwrap
import unittest
import zlib


ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ROOT / "firmware" / "mqtt_heartbeat" / "components"
JOURNAL = COMPONENTS / "sos_pending_edge_journal"
SOURCE = JOURNAL / "sos_pending_edge_journal.c"
HEADER = JOURNAL / "include" / "sos_pending_edge_journal.h"
CMAKE = JOURNAL / "CMakeLists.txt"
RUNTIME = COMPONENTS / "sos_device_runtime" / "sos_device_runtime.c"
RUNTIME_HEADER = COMPONENTS / "sos_device_runtime" / "include" / "sos_device_runtime.h"
ORCHESTRATOR = COMPONENTS / "sos_orchestrator" / "sos_orchestrator.c"
ORCHESTRATOR_HEADER = COMPONENTS / "sos_orchestrator" / "include" / "sos_orchestrator.h"
INPUT = COMPONENTS / "sos_input" / "sos_input.c"
PACKET = ROOT / "docs" / "tasks" / "active" / "SOS-010_SOS_WALKING_SKELETON.md"
APP_MAIN = ROOT / "firmware" / "mqtt_heartbeat" / "main" / "app_main.c"

RECORD_BYTES = 320
CRC_OFFSET = 316
JSON_SAFE_MAX = (1 << 53) - 1


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


def _native_compiler() -> Path | None:
    for candidate in (
        os.environ.get("CC"),
        shutil.which("gcc"),
        shutil.which("clang"),
        "C:/Program Files/LLVM/bin/clang.exe",
    ):
        if not candidate:
            continue
        resolved = shutil.which(str(candidate)) or str(candidate)
        path = Path(resolved)
        lowered = path.name.casefold()
        if (
            path.is_file()
            and ("gcc" in lowered or "clang" in lowered)
            and "xtensa" not in lowered
            and "riscv" not in lowered
        ):
            return path
    return None


def _include_paths() -> tuple[Path, ...]:
    return (
        JOURNAL / "include",
        COMPONENTS / "sos_device_runtime" / "include",
        COMPONENTS / "sos_input" / "include",
        COMPONENTS / "sos_orchestrator" / "include",
        COMPONENTS / "sos_outbox_adapter" / "include",
        COMPONENTS / "persistent_priority_outbox" / "include",
        COMPONENTS / "location_policy_core" / "include",
    )


@dataclass(frozen=True)
class Edge:
    device_id: str
    boot_count: int
    session_id: str
    sequence: int
    edge_time_ms: int

    @property
    def event_id(self) -> str:
        return f"sos-b{self.boot_count}-q{self.sequence}-t{self.edge_time_ms}"


def _wire(edge: Edge) -> bytes:
    device = edge.device_id.encode("ascii")
    session = edge.session_id.encode("ascii")
    if not (0 < len(device) < 129 and 0 < len(session) < 129):
        raise ValueError("unsafe identity length")
    if not all(0 <= item <= JSON_SAFE_MAX for item in (
        edge.boot_count,
        edge.sequence,
        edge.edge_time_ms,
    )):
        raise ValueError("unsafe lineage integer")
    output = bytearray(RECORD_BYTES)
    struct.pack_into(
        "<IHHIIQQQHHI",
        output,
        0,
        0x45534F53,
        1,
        48,
        RECORD_BYTES,
        0,
        edge.boot_count,
        edge.sequence,
        edge.edge_time_ms,
        len(device),
        len(session),
        0,
    )
    output[48 : 48 + len(device)] = device
    output[177 : 177 + len(session)] = session
    struct.pack_into("<I", output, CRC_OFFSET, zlib.crc32(output[:CRC_OFFSET]))
    return bytes(output)


def _decode(wire: bytes, expected_device: str) -> Edge:
    if len(wire) != RECORD_BYTES:
        raise ValueError("size")
    magic, version, header, total, flags = struct.unpack_from("<IHHII", wire)
    if (magic, version, header, total) != (0x45534F53, 1, 48, RECORD_BYTES):
        raise ValueError("format")
    if flags or struct.unpack_from("<I", wire, 44)[0] or any(wire[306:316]):
        raise ValueError("reserved")
    if struct.unpack_from("<I", wire, CRC_OFFSET)[0] != zlib.crc32(
        wire[:CRC_OFFSET]
    ):
        raise ValueError("crc")
    boot, sequence, edge_time, device_len, session_len = struct.unpack_from(
        "<QQQHH", wire, 16
    )
    if not (0 < device_len < 129 and 0 < session_len < 129):
        raise ValueError("length")
    if any(wire[48 + device_len : 177]) or any(
        wire[177 + session_len : 306]
    ):
        raise ValueError("terminator")
    device = wire[48 : 48 + device_len].decode("ascii")
    session = wire[177 : 177 + session_len].decode("ascii")
    if device != expected_device:
        raise ValueError("device")
    return Edge(device, boot, session, sequence, edge_time)


class MemoryBackend:
    def __init__(self) -> None:
        self.raw: bytes | None = None
        self.store_mode = "ok"
        self.clear_mode = "ok"

    def store(self, raw: bytes) -> bool:
        if self.store_mode == "fail_before":
            return False
        self.raw = raw
        return self.store_mode == "ok"

    def clear(self) -> bool:
        if self.clear_mode == "fail_before":
            return False
        self.raw = None
        return self.clear_mode == "ok"


class JournalReference:
    """Executable spec only; it does not call the target C object."""

    def __init__(self, backend: MemoryBackend, device_id: str) -> None:
        self.backend = backend
        self.device_id = device_id

    def load(self) -> Edge | None:
        return None if self.backend.raw is None else _decode(
            self.backend.raw, self.device_id
        )

    def store(self, edge: Edge) -> str:
        current = self.load()
        if current is not None:
            return "duplicate" if current == edge else "occupied"
        self.backend.store(_wire(edge))
        current = self.load()
        return "ok" if current == edge else "storage_error"

    def clear(self, expected: Edge) -> str:
        current = self.load()
        if current is None:
            return "not_found"
        if current != expected:
            return "occupied"
        self.backend.clear()
        return "ok" if self.load() is None else "clear_failed"


class RuntimeReference:
    """Executable F/G state model; it does not execute the target C object."""

    def __init__(
        self,
        journal: JournalReference,
        boot: int,
        session: str,
        first_sequence: int,
    ) -> None:
        self.journal = journal
        self.boot = boot
        self.session = session
        self.next_sequence = first_sequence
        self.sequence_exhausted = False
        self.pending = journal.load()
        self.pending_durable = self.pending is not None
        self.pending_consumed = self.pending is not None
        self.outbox: dict[str, Edge] = {}
        self.callbacks: list[str] = []
        self.outbox_now: list[int] = []
        self.policy_action_time: list[int] = []
        self.outbox_fail = False
        if self.pending is not None:
            if self.pending.boot_count > boot:
                raise ValueError("future boot")
            if self.pending.boot_count == boot:
                if self.pending.session_id != session:
                    raise ValueError("same boot different session")
                if self.pending.sequence >= self.next_sequence:
                    if self.pending.sequence == JSON_SAFE_MAX:
                        self.next_sequence = JSON_SAFE_MAX
                        self.sequence_exhausted = True
                    else:
                        self.next_sequence = self.pending.sequence + 1

    def qualify(self, edge_time_ms: int, now_ms: int) -> str:
        if self.pending is not None:
            return "pending_replay_required"
        if self.sequence_exhausted:
            return "sequence_exhausted"
        self.pending = Edge(
            self.journal.device_id,
            self.boot,
            self.session,
            self.next_sequence,
            edge_time_ms,
        )
        self.pending_durable = False
        self.pending_consumed = False
        return self._drive(now_ms, replayed=False)

    def replay(self, now_ms: int) -> str:
        if self.pending is None:
            return "no_pending_edge"
        return self._drive(now_ms, replayed=True)

    def _drive(self, now_ms: int, *, replayed: bool) -> str:
        assert self.pending is not None
        journal_failed = False
        if not self.pending_durable:
            if self.journal.store(self.pending) not in {"ok", "duplicate"}:
                journal_failed = True
            else:
                self.pending_durable = True
        if self.pending_durable and not self.pending_consumed:
            if self.pending.sequence == JSON_SAFE_MAX:
                self.sequence_exhausted = True
            else:
                self.next_sequence = self.pending.sequence + 1
            self.pending_consumed = True
        if not replayed and self.pending.edge_time_ms > now_ms:
            return "invalid_context"
        self.outbox_now.append(now_ms)
        self.policy_action_time.append(now_ms if replayed else self.pending.edge_time_ms)
        event_id = self.pending.event_id
        if self.outbox_fail:
            persistence = "failed"
        elif event_id in self.outbox:
            if self.outbox[event_id] != self.pending:
                return "identity_conflict"
            persistence = "duplicate"
        else:
            self.outbox[event_id] = self.pending
            persistence = "committed"
        self.callbacks.extend([event_id] * (4 if replayed else 5))
        if journal_failed:
            return "journal_failed"
        if persistence in {"committed", "duplicate"}:
            if self.journal.clear(self.pending) in {"ok", "not_found"}:
                self.pending = None
                self.pending_durable = False
                self.pending_consumed = False
                return "partial" if replayed else "ok"
        return "partial"

    def shutdown(self) -> bool:
        if self.pending is not None and not self.pending_durable:
            return False
        return True


def _integration_harness() -> str:
    return textwrap.dedent(
        r"""
        #include "sos_device_runtime.h"

        #include <stdint.h>
        #include <string.h>

        #define REQUIRE(condition) do { if (!(condition)) { return __LINE__; } } while (0)

        static uint8_t wire[EGOLINK_SOS_PENDING_EDGE_RECORD_BYTES];
        static bool present;
        static bool store_fail_before;
        static bool clear_fail_before;
        static egolink_outbox_status_t enqueue_status;
        static unsigned int enqueue_calls;
        static unsigned int branch_calls;
        static uint64_t observed_now_ms;
        static uint64_t observed_boot;
        static uint64_t observed_sequence;
        static uint64_t observed_edge_time;
        static uint64_t observed_policy_snapshot_time;
        static uint64_t observed_policy_event_time;
        static char observed_session[EGOLINK_OUTBOX_ID_CAPACITY];

        static egolink_sos_pending_edge_storage_result_t load_record(
            void *context, void *destination, size_t capacity, size_t *actual)
        {
            (void)context;
            REQUIRE(destination != NULL && actual != NULL);
            if (!present) {
                *actual = 0U;
                return EGOLINK_SOS_PENDING_EDGE_STORAGE_NOT_FOUND;
            }
            REQUIRE(capacity >= sizeof(wire));
            (void)memcpy(destination, wire, sizeof(wire));
            *actual = sizeof(wire);
            return EGOLINK_SOS_PENDING_EDGE_STORAGE_OK;
        }

        static egolink_sos_pending_edge_storage_result_t store_record(
            void *context, const void *source, size_t length)
        {
            (void)context;
            REQUIRE(source != NULL && length == sizeof(wire));
            if (store_fail_before) {
                return EGOLINK_SOS_PENDING_EDGE_STORAGE_IO_ERROR;
            }
            (void)memcpy(wire, source, sizeof(wire));
            present = true;
            return EGOLINK_SOS_PENDING_EDGE_STORAGE_OK;
        }

        static egolink_sos_pending_edge_storage_result_t clear_record(void *context)
        {
            (void)context;
            if (clear_fail_before) {
                return EGOLINK_SOS_PENDING_EDGE_STORAGE_IO_ERROR;
            }
            present = false;
            (void)memset(wire, 0, sizeof(wire));
            return EGOLINK_SOS_PENDING_EDGE_STORAGE_OK;
        }

        egolink_outbox_status_t egolink_outbox_enqueue(
            egolink_outbox_t *outbox,
            const egolink_outbox_enqueue_request_t *request,
            uint64_t now_ms,
            egolink_outbox_record_view_t *record)
        {
            static const char digest[] =
                "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
            (void)outbox;
            REQUIRE(request != NULL && record != NULL);
            ++enqueue_calls;
            observed_now_ms = now_ms;
            observed_boot = request->boot_count;
            observed_sequence = request->source_sequence;
            observed_edge_time = request->source_event_time_ms;
            (void)memset(observed_session, 0, sizeof(observed_session));
            (void)memcpy(
                observed_session,
                request->session_id,
                strlen(request->session_id) + 1U);
            (void)memset(record, 0, sizeof(*record));
            (void)memcpy(record->payload_sha256, digest, sizeof(digest));
            return enqueue_status;
        }

        egolink_location_policy_result_t egolink_location_policy_evaluate(
            egolink_location_policy_core_t *core,
            const egolink_location_policy_snapshot_t *snapshot,
            const egolink_location_policy_event_t *event,
            egolink_location_policy_decision_t *decision)
        {
            REQUIRE(core != NULL && core->initialized);
            REQUIRE(snapshot != NULL && event != NULL && decision != NULL);
            observed_policy_snapshot_time = snapshot->event_time_ms;
            observed_policy_event_time = event->event_time_ms;
            (void)memset(decision, 0, sizeof(*decision));
            decision->policy_mode = EGOLINK_LOCATION_POLICY_SOS;
            decision->conditions.sos_active = true;
            ++branch_calls;
            return EGOLINK_LOCATION_POLICY_OK;
        }

        static bool feedback(void *context, const egolink_sos_branch_identity_t *identity)
        {
            (void)context;
            REQUIRE(identity != NULL);
            ++branch_calls;
            return true;
        }

        static bool location(
            void *context, const egolink_sos_location_enqueue_request_t *request)
        {
            (void)context;
            REQUIRE(request != NULL);
            ++branch_calls;
            return true;
        }

        static bool call(void *context, const egolink_sos_call_request_t *request)
        {
            (void)context;
            REQUIRE(request != NULL);
            ++branch_calls;
            return true;
        }

        static bool wake(void *context, const egolink_sos_sender_wake_request_t *request)
        {
            (void)context;
            REQUIRE(request != NULL);
            ++branch_calls;
            return true;
        }

        static int initialize(
            egolink_sos_device_runtime_t *runtime,
            egolink_sos_pending_edge_journal_t *journal,
            egolink_outbox_t *outbox,
            egolink_sos_outbox_adapter_t *adapter,
            egolink_location_policy_core_t *policy,
            uint64_t boot,
            const char *session,
            uint64_t first_sequence,
            uint64_t now_ms)
        {
            const egolink_sos_pending_edge_storage_t storage = {
                .load_record = load_record,
                .store_record = store_record,
                .clear_record = clear_record,
            };
            REQUIRE(egolink_sos_pending_edge_journal_init(
                journal, &storage, "wearable-1") == EGOLINK_SOS_PENDING_EDGE_OK);
            (void)memset(adapter, 0, sizeof(*adapter));
            adapter->initialized = true;
            adapter->outbox = outbox;
            (void)memcpy(adapter->device_id, "wearable-1", sizeof("wearable-1"));
            policy->initialized = true;
            egolink_sos_device_runtime_config_t config;
            egolink_sos_device_runtime_default_config(&config);
            config.enabled = true;
            config.input.debounce_ms = 5U;
            config.input.long_press_ms = 500U;
            config.device_id = "wearable-1";
            config.boot_count = boot;
            config.session_id = session;
            config.first_source_sequence = first_sequence;
            config.callbacks.local_feedback = feedback;
            config.callbacks.request_urgent_location = location;
            config.callbacks.request_call = call;
            config.callbacks.wake_sender = wake;
            return (int)egolink_sos_device_runtime_init(
                runtime, &config, outbox, adapter, journal, policy, false, now_ms);
        }

        static int trigger(
            egolink_sos_device_runtime_t *runtime,
            uint64_t press_ms,
            egolink_sos_device_runtime_result_t *result)
        {
            REQUIRE(egolink_sos_device_runtime_process_sample(
                runtime, true, press_ms, result) == EGOLINK_SOS_DEVICE_RUNTIME_NO_EDGE);
            REQUIRE(egolink_sos_device_runtime_process_sample(
                runtime, true, press_ms + 5U, result) == EGOLINK_SOS_DEVICE_RUNTIME_NO_EDGE);
            return (int)egolink_sos_device_runtime_process_sample(
                runtime, true, press_ms + 505U, result);
        }

        int main(void)
        {
            egolink_outbox_t outbox;
            egolink_sos_outbox_adapter_t adapter;
            egolink_location_policy_core_t policy;
            egolink_sos_pending_edge_journal_t journal;
            egolink_sos_device_runtime_t runtime;
            egolink_sos_device_runtime_result_t result;
            egolink_sos_device_runtime_snapshot_t snapshot;
            egolink_sos_device_runtime_shutdown_result_t shutdown;
            (void)memset(&outbox, 0, sizeof(outbox));
            (void)memset(&policy, 0, sizeof(policy));
            (void)memset(&runtime, 0, sizeof(runtime));

            REQUIRE(initialize(
                &runtime, &journal, &outbox, &adapter, &policy,
                7U, "boot-7", 1U, 0U) == EGOLINK_SOS_DEVICE_RUNTIME_OK);
            store_fail_before = true;
            enqueue_status = EGOLINK_OUTBOX_OK;
            REQUIRE(trigger(&runtime, 10U, &result) ==
                EGOLINK_SOS_DEVICE_RUNTIME_JOURNAL_FAILED);
            REQUIRE(enqueue_calls == 1U && branch_calls == 5U);
            REQUIRE(result.source_sequence == 1U && !result.pending_edge_durable);
            REQUIRE(egolink_sos_device_runtime_current_status(
                &runtime, &snapshot) ==
                EGOLINK_SOS_DEVICE_RUNTIME_PENDING_REPLAY_REQUIRED);
            REQUIRE(snapshot.next_source_sequence == 1U);
            REQUIRE(egolink_sos_device_runtime_process_sample(
                &runtime, false, 600U, &result) ==
                EGOLINK_SOS_DEVICE_RUNTIME_PENDING_REPLAY_REQUIRED);
            REQUIRE(egolink_sos_device_runtime_cancel(&runtime, &shutdown) ==
                EGOLINK_SOS_DEVICE_RUNTIME_PENDING_REPLAY_REQUIRED);

            store_fail_before = false;
            REQUIRE(egolink_sos_device_runtime_replay_pending(
                &runtime, 600U, &result) == EGOLINK_SOS_DEVICE_RUNTIME_PARTIAL_FAILURE);
            REQUIRE(result.replayed_pending_edge && !present);
            REQUIRE(enqueue_calls == 2U && branch_calls == 9U);
            REQUIRE(result.orchestration.call_request == EGOLINK_SOS_BRANCH_RECOVERY_SUPPRESSED);
            REQUIRE(observed_boot == 7U && observed_sequence == 1U);
            REQUIRE(observed_edge_time == 515U && observed_now_ms == 600U);

            /* Leave a committed edge journaled by failing clear. */
            REQUIRE(egolink_sos_device_runtime_process_sample(
                &runtime, false, 700U, &result) == EGOLINK_SOS_DEVICE_RUNTIME_NO_EDGE);
            REQUIRE(egolink_sos_device_runtime_process_sample(
                &runtime, false, 705U, &result) == EGOLINK_SOS_DEVICE_RUNTIME_NO_EDGE);
            clear_fail_before = true;
            REQUIRE(trigger(&runtime, 710U, &result) ==
                EGOLINK_SOS_DEVICE_RUNTIME_PARTIAL_FAILURE);
            REQUIRE(result.source_sequence == 2U && present);
            char first_event[EGOLINK_SOS_ORCHESTRATOR_EVENT_ID_CAPACITY];
            (void)memcpy(first_event, result.orchestration.event_id, sizeof(first_event));

            /* Simulated reboot: old boot/session remain in the fixed record. */
            (void)memset(&runtime, 0, sizeof(runtime));
            (void)memset(&journal, 0, sizeof(journal));
            (void)memset(&policy, 0, sizeof(policy));
            REQUIRE(initialize(
                &runtime, &journal, &outbox, &adapter, &policy,
                8U, "boot-8", 1U, 10U) ==
                EGOLINK_SOS_DEVICE_RUNTIME_PENDING_REPLAY_REQUIRED);
            REQUIRE(egolink_sos_device_runtime_current_status(
                &runtime, &snapshot) ==
                EGOLINK_SOS_DEVICE_RUNTIME_PENDING_REPLAY_REQUIRED);
            REQUIRE(snapshot.next_source_sequence == 1U);
            clear_fail_before = false;
            enqueue_status = EGOLINK_OUTBOX_DUPLICATE;
            REQUIRE(egolink_sos_device_runtime_replay_pending(
                &runtime, 10U, &result) == EGOLINK_SOS_DEVICE_RUNTIME_PARTIAL_FAILURE);
            REQUIRE(result.orchestration.call_request == EGOLINK_SOS_BRANCH_RECOVERY_SUPPRESSED);
            REQUIRE(strcmp(first_event, result.orchestration.event_id) == 0);
            REQUIRE(observed_now_ms == 10U);
            REQUIRE(observed_boot == 7U && observed_sequence == 2U);
            REQUIRE(strcmp(observed_session, "boot-7") == 0);
            REQUIRE(observed_edge_time == 1215U);
            REQUIRE(observed_policy_snapshot_time == 10U);
            REQUIRE(observed_policy_event_time == 10U);
            REQUIRE(!present);
            REQUIRE(egolink_sos_device_runtime_current_status(
                &runtime, &snapshot) == EGOLINK_SOS_DEVICE_RUNTIME_OK);
            REQUIRE(snapshot.next_source_sequence == 1U);
            return 0;
        }
        """
    )


class SosPendingEdgeJournalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.header = HEADER.read_text(encoding="utf-8")
        cls.cmake = CMAKE.read_text(encoding="utf-8")
        cls.runtime = RUNTIME.read_text(encoding="utf-8")
        cls.runtime_header = RUNTIME_HEADER.read_text(encoding="utf-8")
        cls.orchestrator = ORCHESTRATOR.read_text(encoding="utf-8")
        cls.orchestrator_header = ORCHESTRATOR_HEADER.read_text(encoding="utf-8")
        cls.packet = PACKET.read_text(encoding="utf-8")

    def test_fixed_pointer_free_versioned_wire_and_integrity(self) -> None:
        self.assertIn("EGOLINK_SOS_PENDING_EDGE_RECORD_BYTES 320U", self.header)
        self.assertIn("EGOLINK_SOS_PENDING_EDGE_FORMAT_VERSION UINT16_C(1)", self.header)
        self.assertIn("SOS_PENDING_WIRE_CRC_OFFSET 316U", self.source)
        self.assertIn("_Static_assert(", self.source)
        record = self.header[
            self.header.index("typedef struct {\n    char device_id") :
            self.header.index("} egolink_sos_pending_edge_record_t;")
        ]
        self.assertNotIn("*", record)
        self.assertIn("crc32_bytes(wire, SOS_PENDING_WIRE_CRC_OFFSET)", self.source)
        edge = Edge("wearable-1", 7, "boot-7", 9, 12345)
        raw = _wire(edge)
        self.assertEqual(RECORD_BYTES, len(raw))
        self.assertEqual(edge, _decode(raw, "wearable-1"))
        damaged = bytearray(raw)
        damaged[24] ^= 0x01
        with self.assertRaisesRegex(ValueError, "crc"):
            _decode(bytes(damaged), "wearable-1")

    def test_reference_store_readback_ambiguity_occupied_and_clear_retry(self) -> None:
        backend = MemoryBackend()
        journal = JournalReference(backend, "wearable-1")
        first = Edge("wearable-1", 7, "boot-7", 1, 515)
        second = Edge("wearable-1", 7, "boot-7", 2, 1515)
        backend.store_mode = "ambiguous_commit"
        self.assertEqual("ok", journal.store(first))
        self.assertEqual("duplicate", journal.store(first))
        self.assertEqual("occupied", journal.store(second))
        backend.clear_mode = "fail_before"
        self.assertEqual("clear_failed", journal.clear(first))
        self.assertEqual(first, journal.load())
        backend.clear_mode = "ambiguous_commit"
        self.assertEqual("ok", journal.clear(first))
        self.assertIsNone(journal.load())

    def test_corrupt_wrong_device_wrong_size_and_reserved_bytes_fail_closed(self) -> None:
        edge = Edge("wearable-1", 3, "boot-3", 4, 900)
        raw = _wire(edge)
        with self.assertRaisesRegex(ValueError, "size"):
            _decode(raw[:-1], "wearable-1")
        with self.assertRaisesRegex(ValueError, "device"):
            _decode(raw, "wearable-2")
        reserved = bytearray(raw)
        reserved[306] = 1
        struct.pack_into("<I", reserved, CRC_OFFSET, zlib.crc32(reserved[:CRC_OFFSET]))
        with self.assertRaisesRegex(ValueError, "reserved"):
            _decode(bytes(reserved), "wearable-1")
        embedded = bytearray(raw)
        embedded[50] = 0
        struct.pack_into("<I", embedded, CRC_OFFSET, zlib.crc32(embedded[:CRC_OFFSET]))
        with self.assertRaises((ValueError, UnicodeDecodeError)):
            _decode(bytes(embedded), "wearable-1")
        noncanonical_padding = bytearray(raw)
        noncanonical_padding[100] = 0x5A
        struct.pack_into(
            "<I",
            noncanonical_padding,
            CRC_OFFSET,
            zlib.crc32(noncanonical_padding[:CRC_OFFSET]),
        )
        with self.assertRaisesRegex(ValueError, "terminator"):
            _decode(bytes(noncanonical_padding), "wearable-1")
        self.assertIn(
            "wire[SOS_PENDING_WIRE_DEVICE_OFFSET + index] != 0U",
            self.source,
        )

    def test_init_never_erases_and_backend_guarantees_are_explicit(self) -> None:
        init = self.source[
            self.source.index("egolink_sos_pending_edge_journal_init(") :
            self.source.index("egolink_sos_pending_edge_journal_load(")
        ]
        self.assertNotIn("store_record(", init)
        self.assertNotIn("clear_record(", init)
        normalized = " ".join((self.header + self.packet).replace("*", " ").split()).lower()
        for phrase in (
            "atomically replace",
            "only after all 320 bytes are durable",
            "not authentication or confidentiality",
            "no nvs/partition implementation",
            "exactly one external task or mutex must serialize",
        ):
            self.assertIn(phrase, normalized)

    def test_runtime_stores_before_f_and_blocks_samples_until_clear(self) -> None:
        drive = self.runtime[
            self.runtime.index("static egolink_sos_device_runtime_status_t run_pending_edge(") :
            self.runtime.index("static egolink_sos_device_runtime_status_t runtime_ready(")
        ]
        self.assertLess(
            drive.index("egolink_sos_pending_edge_journal_store("),
            drive.index("egolink_sos_orchestrate_edge("),
        )
        self.assertLess(
            drive.index("persistence_succeeded("),
            drive.index("egolink_sos_pending_edge_journal_clear("),
        )
        process = self.runtime[
            self.runtime.index("egolink_sos_device_runtime_process_sample(") :
            self.runtime.index("egolink_sos_device_runtime_replay_pending(")
        ]
        self.assertLess(
            process.index("if (internal->pending_edge_available)"),
            process.index("egolink_sos_input_process("),
        )
        self.assertIn("!internal->pending_edge_durable", self.runtime)
        self.assertIn("EGOLINK_SOS_DEVICE_RUNTIME_PENDING_REPLAY_REQUIRED", self.runtime)

    def test_executable_runtime_reference_covers_store_failure_and_clear_retry(self) -> None:
        backend = MemoryBackend()
        journal = JournalReference(backend, "wearable-1")
        runtime = RuntimeReference(journal, 7, "boot-7", 1)
        backend.store_mode = "fail_before"
        self.assertEqual("journal_failed", runtime.qualify(515, 515))
        self.assertEqual(1, runtime.next_sequence)
        original_id = Edge("wearable-1", 7, "boot-7", 1, 515).event_id
        self.assertEqual([original_id] * 5, runtime.callbacks)
        self.assertEqual("pending_replay_required", runtime.qualify(900, 900))
        self.assertFalse(runtime.shutdown())

        backend.store_mode = "ok"
        backend.clear_mode = "fail_before"
        self.assertEqual("partial", runtime.replay(600))
        original_id = Edge("wearable-1", 7, "boot-7", 1, 515).event_id
        self.assertEqual([original_id] * 9, runtime.callbacks)
        self.assertEqual("pending_replay_required", runtime.qualify(1000, 1000))
        self.assertTrue(runtime.shutdown())
        self.assertEqual(original_id, journal.load().event_id)

        backend.clear_mode = "ambiguous_commit"
        self.assertEqual("partial", runtime.replay(700))
        self.assertEqual([original_id] * 13, runtime.callbacks)
        self.assertEqual({original_id}, set(runtime.outbox))
        self.assertIsNone(runtime.pending)
        self.assertEqual([515, 600, 700], runtime.outbox_now)

        future_source_backend = MemoryBackend()
        future_source = RuntimeReference(
            JournalReference(future_source_backend, "wearable-1"),
            9,
            "boot-9",
            1,
        )
        self.assertEqual("invalid_context", future_source.qualify(1000, 999))
        self.assertEqual([], future_source.callbacks)
        self.assertEqual("partial", future_source.replay(1))

    def test_executable_runtime_reference_covers_restart_and_sequence_rules(self) -> None:
        backend = MemoryBackend()
        journal = JournalReference(backend, "wearable-1")
        old_edge = Edge("wearable-1", 7, "boot-7", 9, 50_000)
        self.assertEqual("ok", journal.store(old_edge))
        restarted = RuntimeReference(journal, 8, "boot-8", 1)
        self.assertEqual(1, restarted.next_sequence)
        self.assertEqual("partial", restarted.replay(10))
        self.assertEqual(old_edge.event_id, restarted.callbacks[0])
        self.assertEqual([10], restarted.outbox_now)
        self.assertEqual([10], restarted.policy_action_time)

        same_boot_backend = MemoryBackend()
        same_boot_journal = JournalReference(same_boot_backend, "wearable-1")
        same_edge = Edge("wearable-1", 11, "boot-11", 9, 500)
        self.assertEqual("ok", same_boot_journal.store(same_edge))
        same_boot = RuntimeReference(same_boot_journal, 11, "boot-11", 4)
        self.assertEqual(10, same_boot.next_sequence)

        max_backend = MemoryBackend()
        max_journal = JournalReference(max_backend, "wearable-1")
        maximum = Edge("wearable-1", 12, "boot-12", JSON_SAFE_MAX, 500)
        self.assertEqual("ok", max_journal.store(maximum))
        exhausted = RuntimeReference(max_journal, 12, "boot-12", 1)
        self.assertEqual(JSON_SAFE_MAX, exhausted.next_sequence)
        self.assertTrue(exhausted.sequence_exhausted)

        with self.assertRaisesRegex(ValueError, "different session"):
            RuntimeReference(same_boot_journal, 11, "other-session", 1)
        with self.assertRaisesRegex(ValueError, "future boot"):
            RuntimeReference(same_boot_journal, 10, "boot-10", 1)

    def test_restart_lineage_and_cross_boot_clock_are_safe_and_exact(self) -> None:
        self.assertIn("recovered_pending_edge", self.orchestrator_header)
        self.assertIn(
            "(!event_context->recovered_pending_edge &&",
            self.orchestrator,
        )
        self.assertIn(
            "event_context->recovered_pending_edge\n        ? now_ms",
            self.orchestrator,
        )
        drive = self.runtime[
            self.runtime.index("static egolink_sos_device_runtime_status_t run_pending_edge(") :
            self.runtime.index("static egolink_sos_device_runtime_status_t runtime_ready(")
        ]
        self.assertIn(".recovered_pending_edge = replayed", drive)
        self.assertIn("now_ms,", drive)
        self.assertNotIn("edge_record.edge_time_ms > now_ms", drive)
        self.assertNotIn("now_ms = edge_record.edge_time_ms", drive)
        init = self.runtime[
            self.runtime.index("egolink_sos_device_runtime_status_t egolink_sos_device_runtime_init(") :
            self.runtime.index("static bool journal_store_succeeded(")
        ]
        self.assertIn("recovered_edge.boot_count > internal->boot_count", init)
        self.assertIn("recovered_edge.source_sequence + UINT64_C(1)", init)
        self.assertIn("recovered_edge.boot_count == internal->boot_count", init)
        normalized = " ".join((self.runtime_header + self.packet).replace("*", " ").split()).lower()
        self.assertIn("exact original boot/session/sequence/edge time", normalized)
        self.assertIn("callbacks are at-least-once", normalized)
        self.assertNotIn("recovered_pending_edge", self.runtime_header)

    def test_component_is_offline_unwired_and_has_no_allocation(self) -> None:
        self.assertIn('SRCS "sos_pending_edge_journal.c"', self.cmake)
        combined = (self.source + self.runtime).casefold()
        for forbidden in (
            "app_main",
            "gpio_",
            "esp_http",
            "mqtt_client",
            "freertos/",
            "esp_partition",
            "nvs_",
            "esp_log",
            "malloc(",
            "calloc(",
            "realloc(",
            "free(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, combined)
        self.assertNotIn("sos_pending_edge_journal", APP_MAIN.read_text(encoding="utf-8"))

    def _compile_integration(self, compiler: Path, output: Path, harness: Path) -> None:
        completed = subprocess.run(
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
                *(f"-I{path}" for path in _include_paths()),
                str(SOURCE),
                str(RUNTIME),
                str(ORCHESTRATOR),
                str(INPUT),
                str(harness),
                "-o",
                str(output),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertTrue(output.is_file())

    def test_actual_c_and_fault_harness_cross_compile_for_esp32s3(self) -> None:
        toolchain = _esp_toolchain()
        if toolchain is None:
            self.skipTest("ESP32-S3 cross compiler or ESP-IDF unavailable")
        compiler, _ = toolchain
        with tempfile.TemporaryDirectory(prefix="egolink-sos-pending-cross-") as temp:
            temp_path = Path(temp)
            harness = temp_path / "pending_harness.c"
            harness.write_text(_integration_harness(), encoding="utf-8")
            self._compile_integration(compiler, temp_path / "pending.elf", harness)

    def test_actual_c_fault_harness_runs_when_native_compiler_is_available(self) -> None:
        compiler = _native_compiler()
        if compiler is None:
            self.skipTest("native host GCC/Clang unavailable")
        with tempfile.TemporaryDirectory(prefix="egolink-sos-pending-native-") as temp:
            temp_path = Path(temp)
            harness = temp_path / "pending_harness.c"
            harness.write_text(_integration_harness(), encoding="utf-8")
            executable = temp_path / "pending.exe"
            self._compile_integration(compiler, executable, harness)
            executed = subprocess.run(
                [str(executable)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(0, executed.returncode, executed.stderr)


if __name__ == "__main__":
    unittest.main()

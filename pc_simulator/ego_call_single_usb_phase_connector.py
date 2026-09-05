"""CALL-020P offline-first single-handle CONTROL-to-MEDIA connector.

This module never opens, enumerates, guesses, or reopens an OS serial port. A
caller may inject one already-open exact driver. Ownership remains with the
caller until the first explicit ``prepare`` call successfully validates and
claims it. A complete START acknowledgement makes the phase transition
irreversible; a one-shot ``open_explicit`` factory then lends the same
underlying handle to CALL-020K through a borrowed-driver facade. Closing K
returns the handle to this phase owner instead of physically closing it.

CONTROL frames use a private engineering envelope with fixed magic/version,
message type, bounded canonical JSON payload and CRC32. CRC is framing
integrity, not authentication. Before its first PREPARE write, CONTROL performs
one bounded zero-progress-terminated drain of permitted text ROM/boot residue;
EGLC magic or ambiguous progress fails closed and later reads never resync.
After MEDIA transfer this connector emits no
control bytes. RESULT is deliberately disabled in this slice; after media
quiescence the returned host handle can only be closed locally. Device runtime
termination, mute/PA cleanup, and a remote CLOSED acknowledgement therefore
remain unverified.
"""

from __future__ import annotations

import json
import math
import struct
import threading
import time
import zlib
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from pc_simulator import ego_call_operator_control as operator_control
from pc_simulator.ego_call_os_serial_wrapper import (
    DEFAULT_BAUDRATE,
    DriverIoTimeout,
    ExplicitOsSerialConfig,
    OpenedSerialDriver,
)


SINGLE_USB_CONNECTOR_VERSION = "egolink.ego_call_single_usb_phase_connector.v0.1"
CONTROL_MAGIC = b"EGLC"
CONTROL_VERSION = 1
CONTROL_HEADER = struct.Struct(">4sBBH")
CONTROL_CRC = struct.Struct(">I")
MAX_CONTROL_PAYLOAD_BYTES = 2_048
MAX_CONTROL_FRAME_BYTES = (
    CONTROL_HEADER.size + MAX_CONTROL_PAYLOAD_BYTES + CONTROL_CRC.size
)
MAX_CONTROL_IO_CALLS = 64
MAX_CONTROL_OPERATIONS = 16
MAX_PRE_CONTROL_DRAIN_BYTES = 4_096
MAX_PRE_CONTROL_DRAIN_CALLS = 128
PRE_CONTROL_DRAIN_CHUNK_BYTES = 64

MESSAGE_TYPES = {
    "prepare_request": 1,
    "prepare_ack": 2,
    "start_request": 3,
    "start_ack": 4,
    "cancel_request": 5,
    "cancel_ack": 6,
    "join_request": 7,
    "join_ack": 8,
    "close_request": 9,
    "close_ack": 10,
    "telemetry_request": 11,
    "telemetry_ack": 12,
}
MESSAGE_NAMES = {value: key for key, value in MESSAGE_TYPES.items()}


class MonotonicClock(Protocol):
    def monotonic_ns(self) -> int: ...


class SystemMonotonicClock:
    def monotonic_ns(self) -> int:
        return time.monotonic_ns()


class SingleUsbPhaseError(ValueError):
    """Base error for rejected offline single-handle operations."""


class SingleUsbPhaseBlocked(SingleUsbPhaseError):
    """Redacted failure; never includes port, identity, payload, or media."""

    def __init__(self, reason_code: str, *, stage: str) -> None:
        super().__init__("CALL-020P single USB phase operation blocked")
        self.reason_code = reason_code
        self.metadata = {
            "connector_version": SINGLE_USB_CONNECTOR_VERSION,
            "result": "BLOCKED",
            "stage": stage,
            "reason_code": reason_code,
            "port_driver_generation_or_identity_exposed": False,
            "control_payload_exposed": False,
            "raw_audio_logged_or_persisted": False,
            "device_runtime_termination_proven": False,
            "remote_cleanup_acknowledged": False,
            "hardware_or_serial_io_evidence": "NOT_RUN",
            "p0_call": "NOT_RUN",
        }


class _TransferTimeout(TimeoutError):
    def __init__(self, *, phase: str, progress: int | None) -> None:
        super().__init__("bounded control transfer timed out")
        self.phase = phase
        self.progress = progress


def _bounded_int(value: object, *, label: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise SingleUsbPhaseError(
            f"{label} must be an integer in [{minimum}, {maximum}]"
        )
    return value


def _clock_now(clock: MonotonicClock) -> int:
    value = clock.monotonic_ns()
    if type(value) is not int or not 0 <= value <= 2**63 - 1:
        raise SingleUsbPhaseError("monotonic clock returned an invalid value")
    return value


def _exact_keys(payload: object, expected: set[str], *, label: str) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != expected:
        raise SingleUsbPhaseError(f"{label} fields do not match the fixed schema")
    if any(not isinstance(key, str) for key in payload):
        raise SingleUsbPhaseError(f"{label} keys must be strings")
    return payload


def _pairs_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SingleUsbPhaseError("control JSON contains a duplicate key")
        result[key] = value
    return result


def _validate_json_tree(value: object, *, depth: int = 0) -> None:
    if depth > 5:
        raise SingleUsbPhaseError("control JSON nesting exceeds its bound")
    if value is None or type(value) in {bool, int, str}:
        if isinstance(value, str):
            if len(value) > 256 or any(ord(character) < 0x20 for character in value):
                raise SingleUsbPhaseError("control JSON string exceeds its bound")
        elif type(value) is int and not -(2**63) <= value <= 2**63 - 1:
            raise SingleUsbPhaseError("control JSON integer exceeds its bound")
        return
    if isinstance(value, list):
        if len(value) > 16:
            raise SingleUsbPhaseError("control JSON list exceeds its bound")
        for item in value:
            _validate_json_tree(item, depth=depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > 24:
            raise SingleUsbPhaseError("control JSON object exceeds its bound")
        for key, item in value.items():
            if not isinstance(key, str) or not key or len(key) > 64:
                raise SingleUsbPhaseError("control JSON key is invalid")
            _validate_json_tree(item, depth=depth + 1)
        return
    raise SingleUsbPhaseError("control JSON contains an unsupported value")


def encode_control_frame(message_name: str, payload: Mapping[str, Any]) -> bytes:
    """Encode one complete canonical control frame without performing I/O."""

    if message_name not in MESSAGE_TYPES or not isinstance(payload, Mapping):
        raise SingleUsbPhaseError("control message type or payload is invalid")
    material = dict(payload)
    _validate_json_tree(material)
    try:
        payload_bytes = json.dumps(
            material,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeError):
        raise SingleUsbPhaseError("control payload cannot be encoded") from None
    if not 2 <= len(payload_bytes) <= MAX_CONTROL_PAYLOAD_BYTES:
        raise SingleUsbPhaseError("control payload length exceeds its bound")
    header = CONTROL_HEADER.pack(
        CONTROL_MAGIC,
        CONTROL_VERSION,
        MESSAGE_TYPES[message_name],
        len(payload_bytes),
    )
    checksum = zlib.crc32(header + payload_bytes) & 0xFFFFFFFF
    return header + payload_bytes + CONTROL_CRC.pack(checksum)


def decode_control_frame(frame: bytes | bytearray | memoryview) -> tuple[str, dict[str, Any]]:
    """Decode one exact complete control frame; no resynchronization is attempted."""

    try:
        material = bytes(frame)
    except Exception:
        raise SingleUsbPhaseError("control frame is not byte-addressable") from None
    if not CONTROL_HEADER.size + 2 + CONTROL_CRC.size <= len(material) <= MAX_CONTROL_FRAME_BYTES:
        raise SingleUsbPhaseError("control frame length is outside its bound")
    magic, version, message_type, payload_length = CONTROL_HEADER.unpack_from(material)
    if magic != CONTROL_MAGIC or version != CONTROL_VERSION:
        raise SingleUsbPhaseError("control magic or version mismatch")
    message_name = MESSAGE_NAMES.get(message_type)
    if message_name is None:
        raise SingleUsbPhaseError("control message type is unknown")
    expected_length = CONTROL_HEADER.size + payload_length + CONTROL_CRC.size
    if payload_length > MAX_CONTROL_PAYLOAD_BYTES or len(material) != expected_length:
        raise SingleUsbPhaseError("control payload length mismatch")
    expected_crc = CONTROL_CRC.unpack_from(material, len(material) - CONTROL_CRC.size)[0]
    actual_crc = zlib.crc32(material[:-CONTROL_CRC.size]) & 0xFFFFFFFF
    if actual_crc != expected_crc:
        raise SingleUsbPhaseError("control CRC mismatch")
    payload_bytes = material[CONTROL_HEADER.size:-CONTROL_CRC.size]
    try:
        payload = json.loads(
            payload_bytes.decode("ascii"),
            object_pairs_hook=_pairs_without_duplicates,
        )
    except SingleUsbPhaseError:
        raise
    except (UnicodeError, json.JSONDecodeError):
        raise SingleUsbPhaseError("control JSON is invalid") from None
    if not isinstance(payload, dict):
        raise SingleUsbPhaseError("control JSON root must be an object")
    _validate_json_tree(payload)
    if encode_control_frame(message_name, payload) != material:
        raise SingleUsbPhaseError("control JSON is not canonical")
    return message_name, payload


@dataclass(frozen=True)
class SingleUsbPhaseConfig:
    exact_port: str
    enabled: bool = False
    baudrate: int = DEFAULT_BAUDRATE
    read_timeout_ms: int = 20
    write_timeout_ms: int = 20
    max_io_calls: int = MAX_CONTROL_IO_CALLS
    pre_control_drain_max_bytes: int = 1_024
    pre_control_drain_max_calls: int = 32
    pre_control_drain_timeout_ms: int = 100
    result_phase_enabled: bool = False

    def validate(self) -> None:
        if type(self.enabled) is not bool or type(self.result_phase_enabled) is not bool:
            raise SingleUsbPhaseError("phase enable flags must be explicit booleans")
        if self.result_phase_enabled:
            raise SingleUsbPhaseError("CALL-020P RESULT wire phase is not implemented")
        _bounded_int(
            self.max_io_calls,
            label="control max I/O calls",
            minimum=2,
            maximum=MAX_CONTROL_IO_CALLS,
        )
        _bounded_int(
            self.pre_control_drain_max_bytes,
            label="pre-control drain byte bound",
            minimum=1,
            maximum=MAX_PRE_CONTROL_DRAIN_BYTES,
        )
        _bounded_int(
            self.pre_control_drain_max_calls,
            label="pre-control drain call bound",
            minimum=1,
            maximum=MAX_PRE_CONTROL_DRAIN_CALLS,
        )
        _bounded_int(
            self.pre_control_drain_timeout_ms,
            label="pre-control drain total timeout",
            minimum=1,
            maximum=1_000,
        )
        try:
            ExplicitOsSerialConfig(
                port_name=self.exact_port,
                connection_id="call020p-validation-only",
                enabled=False,
                baudrate=self.baudrate,
                read_timeout_ms=self.read_timeout_ms,
                write_timeout_ms=self.write_timeout_ms,
                exclusive=True,
            ).validate()
        except Exception:
            raise SingleUsbPhaseError("single USB exact serial config is invalid") from None

    def validate_for_control(self) -> None:
        self.validate()
        if self.enabled is not True:
            raise SingleUsbPhaseBlocked("single_usb_connector_disabled", stage="control")


class SingleUsbLeaseRegistry:
    """One authoritative registry's pointer tombstones and monotonic generations.

    The default instance is process-global for this module. Tests/callers may
    inject an isolated registry, so alias detection is guaranteed within the
    selected authoritative instance, not against a malicious parallel registry.
    """

    def __init__(self, *, capacity: int = 256) -> None:
        self.capacity = _bounded_int(
            capacity, label="single USB registry capacity", minimum=1, maximum=4_096
        )
        self._lock = threading.Lock()
        self._next_generation = 1
        self._entries: dict[int, tuple[int, str]] = {}

    def claim(self, driver: object) -> int:
        pointer = id(driver)
        with self._lock:
            if pointer in self._entries:
                raise SingleUsbPhaseError("single USB driver pointer was already claimed")
            if len(self._entries) >= self.capacity or self._next_generation > 2**63 - 1:
                raise SingleUsbPhaseError("single USB lease registry is exhausted")
            generation = self._next_generation
            self._next_generation += 1
            self._entries[pointer] = (generation, "control")
            return generation

    def transition(
        self,
        driver: object,
        generation: int,
        *,
        expected: str,
        target: str,
    ) -> None:
        pointer = id(driver)
        with self._lock:
            if self._entries.get(pointer) != (generation, expected):
                raise SingleUsbPhaseError("single USB lease binding or owner mismatch")
            self._entries[pointer] = (generation, target)

    def audit(self) -> dict[str, Any]:
        with self._lock:
            states = {
                "control": 0,
                "media": 0,
                "returned": 0,
                "closing": 0,
                "closed": 0,
            }
            for _, state in self._entries.values():
                states[state] += 1
            return {
                "capacity": self.capacity,
                "lease_count": len(self._entries),
                "next_generation_is_monotonic": True,
                "state_counts": states,
                "pointer_or_generation_exposed": False,
            }


_DEFAULT_LEASE_REGISTRY = SingleUsbLeaseRegistry()


def _timeout_matches(value: object, expected_ms: int) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
        and math.isclose(value, expected_ms / 1_000, rel_tol=0, abs_tol=1e-9)
    )


def _apply_finite_timeout(driver: object, attribute: str, value: float) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise SingleUsbPhaseError("computed control timeout is invalid")
    try:
        setattr(driver, attribute, value)
        applied = getattr(driver, attribute)
    except Exception:
        raise SingleUsbPhaseError("control timeout application failed") from None
    if (
        isinstance(applied, bool)
        or not isinstance(applied, (int, float))
        or not math.isfinite(applied)
        or applied <= 0
        or applied > value + 1e-9
    ):
        raise SingleUsbPhaseError("driver did not retain the finite timeout bound")


def _validate_opened_driver(driver: object, config: SingleUsbPhaseConfig) -> None:
    for name in ("readinto", "write", "cancel_read", "cancel_write", "close"):
        if not callable(getattr(driver, name, None)):
            raise SingleUsbPhaseError("injected opened driver shape is incomplete")
    if (
        getattr(driver, "is_open", None) is not True
        or getattr(driver, "port", None) != config.exact_port
        or getattr(driver, "baudrate", None) != config.baudrate
        or getattr(driver, "exclusive", None) is not True
        or not _timeout_matches(getattr(driver, "timeout", None), config.read_timeout_ms)
        or not _timeout_matches(
            getattr(driver, "write_timeout", None), config.write_timeout_ms
        )
    ):
        raise SingleUsbPhaseError("injected opened driver identity/config mismatch")


def _telemetry_from_payload(
    value: object, *, expected_phase: str
) -> operator_control.RuntimeTelemetrySnapshot:
    payload = _exact_keys(
        value,
        {
            "phase",
            "captured_at_monotonic_ns",
            "free_internal_heap_bytes",
            "minimum_free_internal_heap_bytes",
            "worker_stack_high_watermark_bytes",
            "externally_attested_runtime_measurement",
        },
        label="telemetry",
    )
    workers = payload["worker_stack_high_watermark_bytes"]
    if not isinstance(workers, list) or len(workers) > 4:
        raise SingleUsbPhaseError("telemetry worker set is invalid")
    worker_values: list[tuple[str, int]] = []
    for item in workers:
        if not isinstance(item, list) or len(item) != 2:
            raise SingleUsbPhaseError("telemetry worker entry is invalid")
        worker_values.append((item[0], item[1]))
    snapshot = operator_control.RuntimeTelemetrySnapshot(
        phase=payload["phase"],
        captured_at_monotonic_ns=payload["captured_at_monotonic_ns"],
        free_internal_heap_bytes=payload["free_internal_heap_bytes"],
        minimum_free_internal_heap_bytes=payload["minimum_free_internal_heap_bytes"],
        worker_stack_high_watermark_bytes=tuple(worker_values),
        externally_attested_runtime_measurement=payload[
            "externally_attested_runtime_measurement"
        ],
    )
    snapshot.validate(expected_phase=expected_phase)
    if snapshot.externally_attested_runtime_measurement is not True:
        raise SingleUsbPhaseError("telemetry lacks external runtime attestation")
    return snapshot


def _parse_prepare(
    payload_value: object,
    command: operator_control.ControlCommand,
) -> operator_control.WearablePreparedSession:
    payload = _exact_keys(
        payload_value,
        {
            "run_id",
            "operation_id",
            "runner_version",
            "runner_api_version",
            "state",
            "session_id",
            "device_id",
            "guardian_id",
            "uplink_clock_id",
            "downlink_clock_id",
            "nonce_bits",
            "correlated_routing_ids",
            "random_quality",
            "provenance",
            "pre_start_telemetry",
            "duplicate",
        },
        label="prepare acknowledgement",
    )
    if type(payload["duplicate"]) is not bool:
        raise SingleUsbPhaseError("prepare duplicate flag is invalid")
    result = operator_control.WearablePreparedSession(
        run_id=payload["run_id"],
        operation_id=payload["operation_id"],
        runner_version=payload["runner_version"],
        runner_api_version=payload["runner_api_version"],
        state=payload["state"],
        session_id=payload["session_id"],
        device_id=payload["device_id"],
        guardian_id=payload["guardian_id"],
        uplink_clock_id=payload["uplink_clock_id"],
        downlink_clock_id=payload["downlink_clock_id"],
        nonce_bits=payload["nonce_bits"],
        correlated_routing_ids=payload["correlated_routing_ids"],
        random_quality=payload["random_quality"],
        provenance=payload["provenance"],
        pre_start_telemetry=_telemetry_from_payload(
            payload["pre_start_telemetry"], expected_phase="pre_start"
        ),
        duplicate=payload["duplicate"],
    )
    result.validate(command)
    return result


def _parse_ack(
    payload_value: object,
    command: operator_control.ControlCommand,
    *,
    states: set[str],
) -> operator_control.WearableControlAck:
    payload = _exact_keys(
        payload_value,
        {"run_id", "operation_id", "action", "accepted", "state", "duplicate"},
        label="control acknowledgement",
    )
    result = operator_control.WearableControlAck(
        run_id=payload["run_id"],
        operation_id=payload["operation_id"],
        action=payload["action"],
        accepted=payload["accepted"],
        state=payload["state"],
        duplicate=payload["duplicate"],
    )
    result.validate(command, states=states)
    return result


class _BorrowedMediaDriver:
    """K-facing facade which returns, rather than closes, the exact handle."""

    def __init__(
        self,
        owner: "SingleUsbPhaseConnector",
        driver: OpenedSerialDriver,
        generation: int,
    ) -> None:
        self._owner = owner
        self._driver: OpenedSerialDriver | None = driver
        self._generation = generation
        self._lock = threading.Lock()

    def _active(self) -> OpenedSerialDriver:
        with self._lock:
            driver = self._driver
        if driver is None:
            raise OSError("borrowed media handle was returned")
        return driver

    @property
    def port(self) -> str:
        return self._active().port

    @property
    def baudrate(self) -> int:
        return self._active().baudrate

    @property
    def exclusive(self) -> bool | None:
        return self._active().exclusive

    @property
    def is_open(self) -> bool:
        return self._active().is_open

    @property
    def timeout(self) -> float | None:
        return self._active().timeout

    @timeout.setter
    def timeout(self, value: float | None) -> None:
        self._active().timeout = value

    @property
    def write_timeout(self) -> float | None:
        return self._active().write_timeout

    @write_timeout.setter
    def write_timeout(self, value: float | None) -> None:
        self._active().write_timeout = value

    def readinto(self, target: memoryview) -> int:
        return self._active().readinto(target)

    def write(self, source: memoryview) -> int:
        return self._active().write(source)

    def cancel_read(self) -> None:
        self._active().cancel_read()

    def cancel_write(self) -> None:
        self._active().cancel_write()

    def close(self) -> None:
        with self._lock:
            driver = self._driver
            if driver is None:
                return
            self._owner._return_from_media(driver, self._generation)
            self._driver = None


class SingleUsbPhaseConnector:
    """M wearable connector plus one-shot K factory over one injected handle."""

    def __init__(
        self,
        config: SingleUsbPhaseConfig,
        *,
        opened_driver: OpenedSerialDriver,
        registry: SingleUsbLeaseRegistry | None = None,
        clock: MonotonicClock | None = None,
    ) -> None:
        if not isinstance(config, SingleUsbPhaseConfig):
            raise SingleUsbPhaseError("SingleUsbPhaseConfig is required")
        config.validate()
        if opened_driver is None:
            raise SingleUsbPhaseError("one caller-injected opened driver is required")
        self._config = config
        self._driver: OpenedSerialDriver | None = opened_driver
        self._registry = registry or _DEFAULT_LEASE_REGISTRY
        if not isinstance(self._registry, SingleUsbLeaseRegistry):
            raise SingleUsbPhaseError("SingleUsbLeaseRegistry is required")
        self._clock = clock or SystemMonotonicClock()
        self._lifecycle_lock = threading.RLock()
        self._state = "dormant"
        self._generation: int | None = None
        self._driver_pointer: int | None = None
        self._ownership_claimed = False
        self._ownership_transfer_count = 0
        self._ownership_return_count = 0
        self._physical_close_confirmed = False
        self._driver_close_callback_completed = False
        self._registry_close_pending = False
        self._borrowed: _BorrowedMediaDriver | None = None
        self._remote_cleanup_acknowledged = False
        self._request_send_counts: dict[str, int] = {}
        self._operation_fingerprints: dict[str, tuple[str, str, int]] = {}
        self._completed: dict[str, object] = {}
        self._read_calls = 0
        self._write_calls = 0
        self._read_bytes = 0
        self._written_bytes = 0
        self._zero_progress_timeouts = 0
        self._partial_or_unknown_failures = 0
        self._duplicate_cache_hits = 0
        self._late_callbacks = 0
        self._cleanup_errors = 0
        self._control_buffers_zeroized = 0
        self._pre_control_drain_attempted = False
        self._pre_control_drain_completed = False
        self._pre_control_drain_calls = 0
        self._pre_control_drain_bytes = 0
        self._pre_control_drain_zero_progress_quiescence = False

    def _activate(self) -> None:
        if self._state != "dormant":
            return
        self._config.validate_for_control()
        driver = self._driver
        if driver is None:
            raise SingleUsbPhaseError("single USB driver reference is unavailable")
        _validate_opened_driver(driver, self._config)
        generation = self._registry.claim(driver)
        self._generation = generation
        self._driver_pointer = id(driver)
        self._ownership_claimed = True
        self._state = "CONTROL_OWNED"

    def _active_control_driver(self) -> OpenedSerialDriver:
        driver = self._driver
        if (
            driver is None
            or not self._ownership_claimed
            or self._generation is None
            or id(driver) != self._driver_pointer
            or self._state
            in {
                "HANDOFF_READY",
                "REMOTE_CLOSED_LOCAL_CLOSING",
                "MEDIA_TRANSFERRED",
                "MEDIA_RETURNED",
                "LOCAL_CLOSED",
            }
        ):
            raise SingleUsbPhaseError("single USB control owner is unavailable")
        try:
            driver.timeout = self._config.read_timeout_ms / 1_000
            driver.write_timeout = self._config.write_timeout_ms / 1_000
        except Exception:
            self._state = "FAILED"
            raise SingleUsbPhaseError(
                "single USB control timeout reset failed"
            ) from None
        _validate_opened_driver(driver, self._config)
        return driver

    def _remaining_seconds(self, *, started_ns: int, timeout_ms: int) -> float:
        now_ns = _clock_now(self._clock)
        if now_ns < started_ns:
            raise SingleUsbPhaseError("control monotonic clock regressed")
        remaining_ns = timeout_ms * 1_000_000 - (now_ns - started_ns)
        if remaining_ns <= 0:
            raise _TransferTimeout(phase="deadline", progress=0)
        return min(
            self._config.read_timeout_ms / 1_000,
            self._config.write_timeout_ms / 1_000,
            remaining_ns / 1_000_000_000,
        )

    def _write_all(
        self,
        driver: OpenedSerialDriver,
        frame: bytearray,
        *,
        started_ns: int,
        timeout_ms: int,
    ) -> None:
        offset = 0
        calls = 0
        while offset < len(frame):
            calls += 1
            if calls > self._config.max_io_calls:
                raise _TransferTimeout(phase="write", progress=offset)
            try:
                _apply_finite_timeout(
                    driver,
                    "write_timeout",
                    self._remaining_seconds(
                        started_ns=started_ns, timeout_ms=timeout_ms
                    ),
                )
            except _TransferTimeout:
                raise _TransferTimeout(phase="write", progress=offset) from None
            view = memoryview(frame)[offset:]
            try:
                count = driver.write(view)
            except DriverIoTimeout as error:
                progress = (
                    None if error.progress is None else offset + error.progress
                )
                raise _TransferTimeout(phase="write", progress=progress) from None
            except TimeoutError:
                raise _TransferTimeout(phase="write", progress=None) from None
            except Exception:
                raise SingleUsbPhaseError("control write callback failed") from None
            finally:
                view.release()
            if type(count) is not int or not 0 <= count <= len(frame) - offset:
                raise SingleUsbPhaseError("control write count is invalid")
            self._write_calls += 1
            self._written_bytes += count
            if count == 0:
                raise _TransferTimeout(phase="write", progress=offset)
            offset += count

    def _read_exact(
        self,
        driver: OpenedSerialDriver,
        size: int,
        *,
        started_ns: int,
        timeout_ms: int,
    ) -> bytearray:
        target = bytearray(size)
        offset = 0
        calls = 0
        try:
            while offset < size:
                calls += 1
                if calls > self._config.max_io_calls:
                    raise _TransferTimeout(phase="read", progress=offset)
                try:
                    _apply_finite_timeout(
                        driver,
                        "timeout",
                        self._remaining_seconds(
                            started_ns=started_ns, timeout_ms=timeout_ms
                        ),
                    )
                except _TransferTimeout:
                    raise _TransferTimeout(phase="read", progress=offset) from None
                view = memoryview(target)[offset:]
                try:
                    count = driver.readinto(view)
                except DriverIoTimeout as error:
                    progress = (
                        None if error.progress is None else offset + error.progress
                    )
                    raise _TransferTimeout(
                        phase="read", progress=progress
                    ) from None
                except TimeoutError:
                    raise _TransferTimeout(phase="read", progress=None) from None
                except Exception:
                    raise SingleUsbPhaseError("control read callback failed") from None
                finally:
                    view.release()
                if type(count) is not int or not 0 <= count <= size - offset:
                    raise SingleUsbPhaseError("control read count is invalid")
                self._read_calls += 1
                self._read_bytes += count
                if count == 0:
                    raise _TransferTimeout(phase="read", progress=offset)
                offset += count
            return target
        except Exception:
            target[:] = b"\x00" * len(target)
            self._control_buffers_zeroized += 1
            raise

    def _read_frame(
        self,
        driver: OpenedSerialDriver,
        *,
        started_ns: int,
        timeout_ms: int,
    ) -> tuple[str, dict[str, Any]]:
        header = self._read_exact(
            driver,
            CONTROL_HEADER.size,
            started_ns=started_ns,
            timeout_ms=timeout_ms,
        )
        remainder: bytearray | None = None
        frame: bytearray | None = None
        try:
            magic, version, message_type, payload_length = CONTROL_HEADER.unpack(header)
            if (
                magic != CONTROL_MAGIC
                or version != CONTROL_VERSION
                or message_type not in MESSAGE_NAMES
                or not 2 <= payload_length <= MAX_CONTROL_PAYLOAD_BYTES
            ):
                raise SingleUsbPhaseError("control response header is invalid")
            try:
                remainder = self._read_exact(
                    driver,
                    payload_length + CONTROL_CRC.size,
                    started_ns=started_ns,
                    timeout_ms=timeout_ms,
                )
            except _TransferTimeout as error:
                progress = (
                    None
                    if error.progress is None
                    else CONTROL_HEADER.size + error.progress
                )
                raise _TransferTimeout(phase="read", progress=progress) from None
            frame = bytearray(header)
            frame.extend(remainder)
            return decode_control_frame(frame)
        finally:
            header[:] = b"\x00" * len(header)
            self._control_buffers_zeroized += 1
            if remainder is not None:
                remainder[:] = b"\x00" * len(remainder)
                self._control_buffers_zeroized += 1
            if frame is not None:
                frame[:] = b"\x00" * len(frame)
                self._control_buffers_zeroized += 1

    @staticmethod
    def _allowed_boot_prefix_byte(value: int) -> bool:
        return value in {0x09, 0x0A, 0x0D} or 0x20 <= value <= 0x7E

    @staticmethod
    def _magic_suffix_length(material: bytearray) -> int:
        if CONTROL_MAGIC in material:
            raise SingleUsbPhaseError("pre-control RX contains an EGLC frame")
        maximum = min(len(material), len(CONTROL_MAGIC) - 1)
        for length in range(maximum, 0, -1):
            start = len(material) - length
            if all(
                material[start + index] == CONTROL_MAGIC[index]
                for index in range(length)
            ):
                return length
        return 0

    def _drain_pre_control_rx(self, driver: OpenedSerialDriver) -> None:
        """Discard one bounded text boot prefix before the first PREPARE write.

        A zero-progress read/timeout proves the bounded quiet point. Any full
        or trailing partial EGLC magic is treated as an ambiguous prior control
        frame and fails closed; later response reads remain exact-frame only.
        """

        if self._pre_control_drain_completed:
            return
        if self._pre_control_drain_attempted:
            self._state = "FAILED"
            raise SingleUsbPhaseBlocked(
                "pre_control_drain_not_repeatable", stage="prepare"
            )
        self._pre_control_drain_attempted = True
        started_ns = _clock_now(self._clock)
        scratch = bytearray(PRE_CONTROL_DRAIN_CHUNK_BYTES)
        magic_tail = bytearray()
        try:
            while True:
                if self._pre_control_drain_calls >= self._config.pre_control_drain_max_calls:
                    raise SingleUsbPhaseError("pre-control RX call bound exceeded")
                remaining_byte_budget = (
                    self._config.pre_control_drain_max_bytes
                    - self._pre_control_drain_bytes
                )
                if remaining_byte_budget <= 0:
                    raise SingleUsbPhaseError("pre-control RX byte bound exhausted")
                now_ns = _clock_now(self._clock)
                if now_ns < started_ns:
                    raise SingleUsbPhaseError("pre-control drain clock regressed")
                remaining_ns = (
                    self._config.pre_control_drain_timeout_ms * 1_000_000
                    - (now_ns - started_ns)
                )
                if remaining_ns <= 0:
                    raise SingleUsbPhaseError("pre-control RX deadline exhausted")
                timeout_seconds = min(
                    self._config.read_timeout_ms / 1_000,
                    remaining_ns / 1_000_000_000,
                )
                _apply_finite_timeout(driver, "timeout", timeout_seconds)
                view = memoryview(scratch)[: min(len(scratch), remaining_byte_budget)]
                try:
                    self._pre_control_drain_calls += 1
                    try:
                        count = driver.readinto(view)
                    except DriverIoTimeout as error:
                        if error.progress == 0:
                            count = 0
                        else:
                            raise SingleUsbPhaseError(
                                "pre-control RX timeout progress is not safely known"
                            ) from None
                    except TimeoutError:
                        raise SingleUsbPhaseError(
                            "pre-control RX timeout progress is unknown"
                        ) from None
                    except Exception:
                        raise SingleUsbPhaseError(
                            "pre-control RX callback failed"
                        ) from None
                finally:
                    view.release()
                ended_ns = _clock_now(self._clock)
                if (
                    ended_ns < started_ns
                    or ended_ns - started_ns
                    > self._config.pre_control_drain_timeout_ms * 1_000_000
                ):
                    raise SingleUsbPhaseError(
                        "pre-control RX callback exceeded the total deadline"
                    )
                if type(count) is not int or not 0 <= count <= len(scratch):
                    raise SingleUsbPhaseError("pre-control RX count is invalid")
                self._read_calls += 1
                self._read_bytes += count
                if count == 0:
                    if magic_tail:
                        raise SingleUsbPhaseError(
                            "pre-control RX ends with partial EGLC magic"
                        )
                    self._pre_control_drain_zero_progress_quiescence = True
                    self._pre_control_drain_completed = True
                    return
                self._pre_control_drain_bytes += count
                if self._pre_control_drain_bytes > self._config.pre_control_drain_max_bytes:
                    raise SingleUsbPhaseError("pre-control RX byte bound exceeded")
                combined = bytearray(magic_tail)
                chunk_view = memoryview(scratch)[:count]
                try:
                    if any(
                        not self._allowed_boot_prefix_byte(value)
                        for value in chunk_view
                    ):
                        raise SingleUsbPhaseError(
                            "pre-control RX contains a disallowed startup byte"
                        )
                    combined.extend(chunk_view)
                    suffix_length = self._magic_suffix_length(combined)
                    magic_tail.clear()
                    if suffix_length:
                        suffix_view = memoryview(combined)[-suffix_length:]
                        try:
                            magic_tail.extend(suffix_view)
                        finally:
                            suffix_view.release()
                finally:
                    chunk_view.release()
                    combined[:] = b"\x00" * len(combined)
                    self._control_buffers_zeroized += 1
                scratch[:] = b"\x00" * len(scratch)
                self._control_buffers_zeroized += 1
        except SingleUsbPhaseBlocked:
            raise
        except Exception:
            self._state = "FAILED"
            raise SingleUsbPhaseBlocked(
                "pre_control_rx_not_quiescent", stage="prepare"
            ) from None
        finally:
            scratch[:] = b"\x00" * len(scratch)
            magic_tail[:] = b"\x00" * len(magic_tail)
            self._control_buffers_zeroized += 2

    def _command_fingerprint(
        self, command: operator_control.ControlCommand, action: str
    ) -> tuple[str, str, int]:
        command.validate()
        if command.action != action:
            raise SingleUsbPhaseError("control command action mismatch")
        return command.run_id, action, command.timeout_ms

    def _cached(
        self, command: operator_control.ControlCommand, action: str
    ) -> object | None:
        fingerprint = self._command_fingerprint(command, action)
        existing = self._operation_fingerprints.get(command.operation_id)
        if existing is not None and existing != fingerprint:
            # A conflicting control request is terminal only while CONTROL is
            # still authoritative. It must never corrupt the lease state after
            # START/HANDOFF: doing so could prevent the exact media borrower
            # from returning the handle without emitting a single wire byte.
            if self._state not in {
                "HANDOFF_READY",
                "START_UNCERTAIN",
                "REMOTE_CLOSED_LOCAL_CLOSING",
                "MEDIA_TRANSFERRED",
                "MEDIA_RETURNED",
                "LOCAL_CLOSED",
            }:
                self._state = "FAILED"
            raise SingleUsbPhaseBlocked("control_operation_identity_reused", stage=action)
        if command.operation_id in self._completed:
            self._duplicate_cache_hits += 1
            return self._completed[command.operation_id]
        if existing is None:
            if len(self._operation_fingerprints) >= MAX_CONTROL_OPERATIONS:
                raise SingleUsbPhaseBlocked("control_operation_capacity_exhausted", stage=action)
            self._operation_fingerprints[command.operation_id] = fingerprint
        return None

    def _request_payload(
        self, command: operator_control.ControlCommand
    ) -> dict[str, Any]:
        return {
            "action": command.action,
            "operation_id": command.operation_id,
            "run_id": command.run_id,
            "timeout_ms": command.timeout_ms,
        }

    def _exchange_payload(
        self,
        command: operator_control.ControlCommand,
        *,
        expected_message: str,
    ) -> dict[str, Any]:
        action = command.action
        driver = self._active_control_driver()
        started_ns = _clock_now(self._clock)
        frame = bytearray(
            encode_control_frame(f"{action}_request", self._request_payload(command))
        )
        request_sent = False
        try:
            self._write_all(
                driver,
                frame,
                started_ns=started_ns,
                timeout_ms=command.timeout_ms,
            )
            request_sent = True
            self._request_send_counts[command.operation_id] = (
                self._request_send_counts.get(command.operation_id, 0) + 1
            )
            message_name, payload = self._read_frame(
                driver,
                started_ns=started_ns,
                timeout_ms=command.timeout_ms,
            )
            ended_ns = _clock_now(self._clock)
            if ended_ns < started_ns or ended_ns - started_ns > command.timeout_ms * 1_000_000:
                self._late_callbacks += 1
                raise SingleUsbPhaseError("control exchange exceeded its timeout")
            if message_name != expected_message:
                raise SingleUsbPhaseError("control response message type mismatch")
            duplicate = payload.get("duplicate")
            if type(duplicate) is not bool:
                raise SingleUsbPhaseError("control response duplicate flag is invalid")
            send_count = self._request_send_counts[command.operation_id]
            if send_count == 1 and duplicate is not False:
                raise SingleUsbPhaseError(
                    "first operation response unexpectedly claims a duplicate"
                )
            if send_count > 1 and duplicate is not True:
                raise SingleUsbPhaseError("retried operation lacks duplicate acknowledgement")
            return payload
        except _TransferTimeout as error:
            safe_zero_progress = error.progress == 0
            if safe_zero_progress and (not request_sent or action != "start"):
                self._zero_progress_timeouts += 1
            else:
                self._partial_or_unknown_failures += 1
                self._state = "START_UNCERTAIN" if action == "start" else "FAILED"
            raise SingleUsbPhaseBlocked(
                "control_zero_progress_timeout"
                if safe_zero_progress
                else "control_partial_or_unknown_progress",
                stage=action,
            ) from None
        except SingleUsbPhaseBlocked:
            raise
        except Exception:
            self._partial_or_unknown_failures += 1
            self._state = "START_UNCERTAIN" if action == "start" else "FAILED"
            raise SingleUsbPhaseBlocked("control_frame_or_callback_rejected", stage=action) from None
        finally:
            frame[:] = b"\x00" * len(frame)
            self._control_buffers_zeroized += 1

    def _complete(self, command: operator_control.ControlCommand, result: object) -> None:
        self._completed[command.operation_id] = result

    def prepare(
        self, command: operator_control.ControlCommand
    ) -> operator_control.WearablePreparedSession:
        with self._lifecycle_lock:
            cached = self._cached(command, "prepare")
            if cached is not None:
                if not isinstance(cached, operator_control.WearablePreparedSession):
                    raise SingleUsbPhaseError("cached prepare result is invalid")
                return cached
            self._activate()
            if self._state != "CONTROL_OWNED":
                raise SingleUsbPhaseBlocked("prepare_phase_rejected", stage="prepare")
            self._drain_pre_control_rx(self._active_control_driver())
            payload = self._exchange_payload(
                command, expected_message="prepare_ack"
            )
            try:
                result = _parse_prepare(payload, command)
            except Exception:
                self._partial_or_unknown_failures += 1
                self._state = "FAILED"
                raise SingleUsbPhaseBlocked(
                    "prepare_acknowledgement_rejected", stage="prepare"
                ) from None
            self._complete(command, result)
            self._state = "PREPARED"
            return result

    def _ack_operation(
        self,
        command: operator_control.ControlCommand,
        *,
        action: str,
        allowed_before: set[str],
        ack_states: set[str],
        state_after: str,
    ) -> operator_control.WearableControlAck:
        cached = self._cached(command, action)
        if cached is not None:
            if not isinstance(cached, operator_control.WearableControlAck):
                raise SingleUsbPhaseError("cached control result is invalid")
            return cached
        if self._state not in allowed_before:
            raise SingleUsbPhaseBlocked("control_phase_rejected", stage=action)
        payload = self._exchange_payload(
            command, expected_message=f"{action}_ack"
        )
        try:
            result = _parse_ack(payload, command, states=ack_states)
        except Exception:
            self._partial_or_unknown_failures += 1
            self._state = "START_UNCERTAIN" if action == "start" else "FAILED"
            raise SingleUsbPhaseBlocked(
                "control_acknowledgement_rejected", stage=action
            ) from None
        self._complete(command, result)
        self._state = state_after
        return result

    def start(
        self, command: operator_control.ControlCommand
    ) -> operator_control.WearableControlAck:
        with self._lifecycle_lock:
            result = self._ack_operation(
                command,
                action="start",
                allowed_before={"PREPARED"},
                ack_states={"STARTING", "RUNNING"},
                state_after="HANDOFF_READY",
            )
            return result

    def cancel(
        self, command: operator_control.ControlCommand
    ) -> operator_control.WearableControlAck:
        with self._lifecycle_lock:
            return self._ack_operation(
                command,
                action="cancel",
                allowed_before={"CONTROL_OWNED", "PREPARED"},
                ack_states={"STOPPING", "TERMINAL"},
                state_after="STOPPING",
            )

    def join(
        self, command: operator_control.ControlCommand
    ) -> operator_control.WearableControlAck:
        with self._lifecycle_lock:
            return self._ack_operation(
                command,
                action="join",
                allowed_before={"STOPPING"},
                ack_states={"JOINED", "TERMINAL"},
                state_after="JOINED",
            )

    def close(
        self, command: operator_control.ControlCommand
    ) -> operator_control.WearableControlAck:
        with self._lifecycle_lock:
            cached = self._cached(command, "close")
            if cached is None:
                if self._state not in {"CONTROL_OWNED", "PREPARED", "STOPPING", "JOINED"}:
                    raise SingleUsbPhaseBlocked("control_phase_rejected", stage="close")
                payload = self._exchange_payload(
                    command, expected_message="close_ack"
                )
                try:
                    cached = _parse_ack(payload, command, states={"CLOSED"})
                except Exception:
                    self._partial_or_unknown_failures += 1
                    self._state = "FAILED"
                    raise SingleUsbPhaseBlocked(
                        "control_acknowledgement_rejected", stage="close"
                    ) from None
                self._complete(command, cached)
                self._remote_cleanup_acknowledged = True
                self._state = "REMOTE_CLOSED_LOCAL_CLOSING"
            if not isinstance(cached, operator_control.WearableControlAck):
                raise SingleUsbPhaseError("cached close result is invalid")
            if not self._close_owned_driver(expected_states={self._state}):
                raise SingleUsbPhaseBlocked("control_handle_close_unconfirmed", stage="close")
            return cached

    def telemetry(
        self, command: operator_control.ControlCommand
    ) -> operator_control.RuntimeTelemetrySnapshot:
        with self._lifecycle_lock:
            cached = self._cached(command, "telemetry")
            if cached is not None:
                if not isinstance(cached, operator_control.RuntimeTelemetrySnapshot):
                    raise SingleUsbPhaseError("cached telemetry result is invalid")
                return cached
            if self._state not in {"CONTROL_OWNED", "PREPARED", "STOPPING", "JOINED"}:
                raise SingleUsbPhaseBlocked("control_phase_rejected", stage="telemetry")
            payload = self._exchange_payload(
                command, expected_message="telemetry_ack"
            )
            try:
                payload = _exact_keys(
                    payload,
                    {
                        "run_id",
                        "operation_id",
                        "action",
                        "accepted",
                        "duplicate",
                        "snapshot",
                    },
                    label="telemetry acknowledgement",
                )
                if (
                    payload["run_id"] != command.run_id
                    or payload["operation_id"] != command.operation_id
                    or payload["action"] != "telemetry"
                    or payload["accepted"] is not True
                    or type(payload["duplicate"]) is not bool
                ):
                    raise SingleUsbPhaseError(
                        "telemetry acknowledgement identity mismatch"
                    )
                result = _telemetry_from_payload(
                    payload["snapshot"], expected_phase="post_stop"
                )
            except Exception:
                self._partial_or_unknown_failures += 1
                self._state = "FAILED"
                raise SingleUsbPhaseBlocked(
                    "telemetry_acknowledgement_rejected", stage="telemetry"
                ) from None
            self._complete(command, result)
            return result

    def open_explicit(
        self,
        *,
        port_name: str,
        baudrate: int,
        read_timeout_ms: int,
        write_timeout_ms: int,
        exclusive: bool,
    ) -> OpenedSerialDriver:
        """One-shot K factory; returns a facade over the same underlying handle."""

        with self._lifecycle_lock:
            if self._state != "HANDOFF_READY":
                raise SingleUsbPhaseBlocked("media_transfer_phase_rejected", stage="handoff")
            if (
                port_name != self._config.exact_port
                or baudrate != self._config.baudrate
                or read_timeout_ms != self._config.read_timeout_ms
                or write_timeout_ms != self._config.write_timeout_ms
                or exclusive is not True
            ):
                raise SingleUsbPhaseBlocked("media_transfer_config_mismatch", stage="handoff")
            driver = self._driver
            generation = self._generation
            if (
                driver is None
                or generation is None
                or id(driver) != self._driver_pointer
            ):
                raise SingleUsbPhaseBlocked("media_transfer_binding_mismatch", stage="handoff")
            driver.timeout = read_timeout_ms / 1_000
            driver.write_timeout = write_timeout_ms / 1_000
            _validate_opened_driver(driver, self._config)
            # Allocate the non-owning facade before changing the authoritative
            # registry owner.  A MemoryError cannot otherwise orphan a lease
            # already marked MEDIA without a borrower able to return it.
            borrowed = _BorrowedMediaDriver(self, driver, generation)
            self._registry.transition(
                driver,
                generation,
                expected="control",
                target="media",
            )
            self._driver = None
            self._borrowed = borrowed
            self._ownership_transfer_count += 1
            self._state = "MEDIA_TRANSFERRED"
            return borrowed

    def _return_from_media(self, driver: OpenedSerialDriver, generation: int) -> None:
        with self._lifecycle_lock:
            if (
                self._state != "MEDIA_TRANSFERRED"
                or self._driver is not None
                or self._generation != generation
                or id(driver) != self._driver_pointer
            ):
                raise SingleUsbPhaseError("returned media handle binding mismatch")
            self._registry.transition(
                driver,
                generation,
                expected="media",
                target="returned",
            )
            self._driver = driver
            self._borrowed = None
            self._ownership_return_count += 1
            self._state = "MEDIA_RETURNED"

    def _close_owned_driver(self, *, expected_states: set[str]) -> bool:
        if self._state == "LOCAL_CLOSED":
            return True
        if self._state not in expected_states:
            return False
        driver = self._driver
        generation = self._generation
        if (
            driver is None
            or generation is None
            or id(driver) != self._driver_pointer
        ):
            return False
        for name in ("cancel_read", "cancel_write"):
            try:
                callback = getattr(driver, name, None)
                if callable(callback):
                    callback()
                else:
                    self._cleanup_errors += 1
            except Exception:
                self._cleanup_errors += 1
        expected_registry_state = (
            "returned" if self._state == "MEDIA_RETURNED" else "control"
        )
        if not self._registry_close_pending:
            try:
                self._registry.transition(
                    driver,
                    generation,
                    expected=expected_registry_state,
                    target="closing",
                )
            except Exception:
                self._cleanup_errors += 1
                return False
            self._registry_close_pending = True
        if not self._driver_close_callback_completed:
            try:
                driver.close()
            except Exception:
                self._cleanup_errors += 1
                return False
            self._driver_close_callback_completed = True
        try:
            is_open = driver.is_open
        except Exception:
            self._cleanup_errors += 1
            return False
        if is_open is not False:
            # A returning close callback is not proof that the physical
            # driver released the handle.  Keep the exact resource and the
            # registry's CLOSING owner for an explicit bounded retry.
            self._driver_close_callback_completed = False
            self._cleanup_errors += 1
            return False
        try:
            self._registry.transition(
                driver,
                generation,
                expected="closing",
                target="closed",
            )
        except Exception:
            self._cleanup_errors += 1
            return False
        self._driver = None
        self._borrowed = None
        self._physical_close_confirmed = True
        self._registry_close_pending = False
        self._ownership_claimed = False
        self._state = "LOCAL_CLOSED"
        return True

    def abort_before_media_transfer(self) -> bool:
        """Local-only cleanup; never emits a post-START control frame."""

        with self._lifecycle_lock:
            if self._state == "LOCAL_CLOSED":
                return True
            if self._state in {"MEDIA_TRANSFERRED", "MEDIA_RETURNED"}:
                return False
            if not self._ownership_claimed:
                return True
            return self._close_owned_driver(expected_states={self._state})

    def close_returned_handle(self) -> bool:
        """Close locally only after K returned the quiescent borrowed facade."""

        with self._lifecycle_lock:
            return self._close_owned_driver(expected_states={"MEDIA_RETURNED"})

    def recover_media_return_after_quiescence(self) -> bool:
        """Retry only the facade return after M has joined/closed local media.

        The connector deliberately cannot establish quiescence itself.  The
        owner may call this recovery seam only after the K/L operation has
        returned and its media worker is no longer alive.  It never closes the
        physical driver and never emits CONTROL or RESULT bytes.
        """

        with self._lifecycle_lock:
            if self._state in {"MEDIA_RETURNED", "LOCAL_CLOSED"}:
                return True
            if self._state != "MEDIA_TRANSFERRED" or self._borrowed is None:
                return False
            borrowed = self._borrowed
        # Borrowed.close acquires facade -> connector. Do not hold the
        # connector lock here: keeping one global lock order prevents a
        # deadlock even if a caller incorrectly races the quiescent recovery
        # seam with K's ordinary facade return.
        try:
            borrowed.close()
        except Exception:
            with self._lifecycle_lock:
                self._cleanup_errors += 1
            return False
        with self._lifecycle_lock:
            return self._state in {"MEDIA_RETURNED", "LOCAL_CLOSED"}

    def phase_snapshot(self) -> dict[str, Any]:
        """Return only safe phase/ownership metadata; never exact identities."""

        with self._lifecycle_lock:
            return {
                "connector_version": SINGLE_USB_CONNECTOR_VERSION,
                "state": self._state,
                "default_enabled": False,
                "ownership_claimed": self._ownership_claimed,
                "generation_assigned": self._generation is not None,
                "underlying_pointer_identity_recorded": self._driver_pointer is not None,
                "ownership_transfer_count": self._ownership_transfer_count,
                "ownership_return_count": self._ownership_return_count,
                "single_owner_enforced": True,
                "single_owner_scope": "AUTHORITATIVE_REGISTRY_INSTANCE",
                "cross_registry_alias_detection": False,
                "same_underlying_handle_required": True,
                "physical_close_confirmed": self._physical_close_confirmed,
                "physical_close_callback_completed": self._driver_close_callback_completed,
                "registry_close_pending": self._registry_close_pending,
                "remote_cleanup_acknowledged": self._remote_cleanup_acknowledged,
                "device_runtime_termination_proven": False,
                "result_phase": "DISABLED_NOT_RUN",
                "control_writes_forbidden_after_start_ack": True,
                "connector_holds_driver_reference": self._driver is not None,
                "driver_reference_held_by_phase_owner": (
                    self._driver is not None and self._ownership_claimed
                ),
                "unclaimed_driver_retained_for_caller": (
                    self._driver is not None
                    and not self._ownership_claimed
                    and self._state == "dormant"
                ),
                "port_driver_pointer_generation_or_identity_exposed": False,
                "raw_audio_logged_or_persisted": False,
                "hardware_or_serial_io_evidence": "NOT_RUN",
                "p0_call": "NOT_RUN",
            }

    def audit(self) -> dict[str, Any]:
        with self._lifecycle_lock:
            snapshot = self.phase_snapshot()
            snapshot.update(
                {
                    "read_calls": self._read_calls,
                    "write_calls": self._write_calls,
                    "read_bytes_exposed": False,
                    "written_bytes_exposed": False,
                    "zero_progress_timeouts": self._zero_progress_timeouts,
                    "partial_or_unknown_failures": self._partial_or_unknown_failures,
                    "duplicate_cache_hits": self._duplicate_cache_hits,
                    "late_callbacks": self._late_callbacks,
                    "cleanup_errors": self._cleanup_errors,
                    "control_buffers_zeroized": self._control_buffers_zeroized,
                    "pre_control_drain_attempted": self._pre_control_drain_attempted,
                    "pre_control_drain_completed": self._pre_control_drain_completed,
                    "pre_control_drain_calls": self._pre_control_drain_calls,
                    "pre_control_drain_bytes": self._pre_control_drain_bytes,
                    "pre_control_drain_zero_progress_quiescence": (
                        self._pre_control_drain_zero_progress_quiescence
                    ),
                    "callback_timeout_is_post_return_check_only": True,
                    "port_opened_enumerated_guessed_or_reopened": False,
                    "control_payload_or_routing_identity_exposed": False,
                }
            )
            return snapshot


__all__ = [
    "CONTROL_CRC",
    "CONTROL_HEADER",
    "CONTROL_MAGIC",
    "CONTROL_VERSION",
    "MAX_CONTROL_FRAME_BYTES",
    "MAX_CONTROL_PAYLOAD_BYTES",
    "MAX_PRE_CONTROL_DRAIN_BYTES",
    "MAX_PRE_CONTROL_DRAIN_CALLS",
    "MESSAGE_NAMES",
    "MESSAGE_TYPES",
    "SINGLE_USB_CONNECTOR_VERSION",
    "SingleUsbLeaseRegistry",
    "SingleUsbPhaseBlocked",
    "SingleUsbPhaseConfig",
    "SingleUsbPhaseConnector",
    "SingleUsbPhaseError",
    "decode_control_frame",
    "encode_control_frame",
]

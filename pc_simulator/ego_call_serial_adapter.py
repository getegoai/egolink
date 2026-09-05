"""CALL-020H caller-injected host serial transport and EGLM resynchronizer.

This module never enumerates or opens a serial port.  The caller supplies an
already-created ordered full-duplex object implementing :class:`InjectedSerial`.
The object must honor every ``timeout_ms`` argument; Python cannot preempt a
misbehaving callback, so that requirement still needs runtime verification for
the eventual OS/driver wrapper.

Only the private CALL-020 EGLM media stream belongs here.  A future operator
control trigger is a separate, unimplemented channel and must not inject bytes
into this stream.  The adapter logs and persists no media.  Its mutable scan,
candidate, validation, and write buffers are bounded and zeroed on transfer,
rejection, timeout, or close.  Buffers owned by the injected object or by the
existing :class:`~pc_simulator.ego_call_media_io.FrameCodec` remain outside
that erasure boundary.
"""

from __future__ import annotations

import threading
import time
import zlib
from dataclasses import dataclass
from typing import Any, Protocol

from pc_simulator.ego_call_media_io import (
    FRAME_BYTES,
    MAX_IDENTIFIER_BYTES,
    WIRE_MAGIC,
    EndpointIdentity,
    FrameCodec,
    FramedEndpoint,
    MediaFrame,
    MediaIoError,
    MediaIoProtocolError,
    MediaIoTimeout,
    _CRC,
    _HEADER,
    _zero,
)


SERIAL_ADAPTER_VERSION = "egolink.ego_call_serial_adapter.v0.1"
MIN_WIRE_BYTES = _HEADER.size + 4 + FRAME_BYTES + _CRC.size
MAX_WIRE_BYTES = (
    _HEADER.size + 4 * MAX_IDENTIFIER_BYTES + FRAME_BYTES + _CRC.size
)
_NS_PER_MS = 1_000_000


class InjectedSerial(Protocol):
    """Caller-provided ordered transport; it does not imply ``pyserial``.

    ``readinto`` returns the number of bytes placed in ``target``.  ``write``
    returns the number consumed from ``source``.  Returning zero means a
    proven zero-progress timeout.  A callback that times out after known or
    unknown progress raises :class:`InjectedSerialTimeout`.

    Read and write may be called concurrently.  ``cancel_pending_io`` is an
    out-of-band local lifecycle callback; it must never write control bytes.
    The caller retains ownership of the object and closes the OS handle after
    this adapter is closed.
    """

    def readinto(self, target: memoryview, *, timeout_ms: int) -> int: ...

    def write(self, source: memoryview, *, timeout_ms: int) -> int: ...

    def cancel_pending_io(self) -> None: ...


class MonotonicClock(Protocol):
    def monotonic_ns(self) -> int: ...


class SystemMonotonicClock:
    def monotonic_ns(self) -> int:
        return time.monotonic_ns()


class InjectedSerialTimeout(TimeoutError):
    """Explicit progress report from the caller's serial wrapper.

    ``progress=0`` is retryable only if the enclosing exact operation has made
    no progress.  A positive value or ``None`` (unknown) is terminal.
    """

    def __init__(self, message: str, *, progress: int | None):
        super().__init__(message)
        if progress is not None and (type(progress) is not int or progress < 0):
            raise ValueError("serial timeout progress must be a non-negative int or None")
        self.progress = progress


@dataclass(frozen=True)
class HostSerialAdapterConfig:
    per_call_timeout_ms: int = 20
    max_operation_timeout_ms: int = 1_000
    max_resync_discard_bytes: int = 4_096
    max_invalid_candidates: int = 64
    max_serial_calls_per_operation: int = 8_192
    read_chunk_bytes: int = 256

    def validate(self) -> None:
        _bounded_int(
            self.per_call_timeout_ms,
            label="per_call_timeout_ms",
            minimum=1,
            maximum=1_000,
        )
        _bounded_int(
            self.max_operation_timeout_ms,
            label="max_operation_timeout_ms",
            minimum=self.per_call_timeout_ms,
            maximum=30_000,
        )
        _bounded_int(
            self.max_resync_discard_bytes,
            label="max_resync_discard_bytes",
            minimum=0,
            maximum=65_536,
        )
        _bounded_int(
            self.max_invalid_candidates,
            label="max_invalid_candidates",
            minimum=1,
            maximum=1_024,
        )
        _bounded_int(
            self.max_serial_calls_per_operation,
            label="max_serial_calls_per_operation",
            minimum=self.max_resync_discard_bytes + MAX_WIRE_BYTES,
            maximum=131_072,
        )
        _bounded_int(
            self.read_chunk_bytes,
            label="read_chunk_bytes",
            minimum=1,
            maximum=MAX_WIRE_BYTES,
        )


@dataclass(slots=True)
class _OperationBudget:
    deadline_ns: int
    last_clock_ns: int
    calls: int = 0
    progress_bytes: int = 0
    discarded_bytes: int = 0
    invalid_candidates: int = 0


class _CandidateStream:
    """Bounded in-memory view used only by the existing FrameCodec validator."""

    def __init__(self, wire: bytearray):
        self._wire = wire
        self._offset = 0

    def read_exact(self, size: int, *, timeout_steps: int) -> bytearray:
        del timeout_steps
        if type(size) is not int or size < 1 or self._offset + size > len(self._wire):
            raise MediaIoProtocolError("candidate wire length is inconsistent")
        result = bytearray(size)
        result[:] = self._wire[self._offset : self._offset + size]
        self._offset += size
        return result

    def write_all(self, data: memoryview, *, timeout_steps: int) -> None:
        del data, timeout_steps
        raise AssertionError("candidate validation never writes")

    def close(self) -> None:
        return None

    @property
    def consumed(self) -> int:
        return self._offset


def _bounded_int(value: object, *, label: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise MediaIoError(f"{label} must be an integer in [{minimum}, {maximum}]")
    return value


def _validate_serial_shape(serial_port: object) -> None:
    for name in ("readinto", "write", "cancel_pending_io"):
        if not callable(getattr(serial_port, name, None)):
            raise MediaIoError(
                "caller-injected serial object must provide readinto, write, "
                "and cancel_pending_io"
            )


class HostSerialOrderedByteStream:
    """Bounded, resynchronizing ByteStream for one wearable serial endpoint.

    One read worker and one write worker may use the instance concurrently.
    Direction-specific locks are independent.  A terminal error closes the
    adapter and requests out-of-band cancellation exactly once; it never emits
    an in-band control byte and never closes the caller-owned serial handle.
    """

    def __init__(
        self,
        serial_port: InjectedSerial,
        identity: EndpointIdentity,
        *,
        inbound_direction: str = "uplink",
        outbound_direction: str = "downlink",
        config: HostSerialAdapterConfig | None = None,
        clock: MonotonicClock | None = None,
    ):
        _validate_serial_shape(serial_port)
        identity.validate()
        if {inbound_direction, outbound_direction} != {"uplink", "downlink"}:
            raise MediaIoProtocolError("serial endpoint directions must be opposite")
        self.serial_port = serial_port
        self.identity = identity
        self.inbound_direction = inbound_direction
        self.outbound_direction = outbound_direction
        self.config = config or HostSerialAdapterConfig()
        self.config.validate()
        self.clock = clock or SystemMonotonicClock()

        self._read_lock = threading.RLock()
        self._write_lock = threading.RLock()
        self._state_lock = threading.Lock()
        self._scan = bytearray()
        self._ready_wire = bytearray()
        self._ready_offset = 0
        self._closed = False
        self._terminal = False
        self._cancel_requested = False
        self._cancel_error = False
        self._frames_admitted = 0
        self._frames_written = 0
        self._prefix_bytes_discarded = 0
        self._invalid_candidates = 0
        self._zero_progress_timeouts = 0
        self._terminal_errors = 0

    def _clock_now(self) -> int:
        now = self.clock.monotonic_ns()
        if type(now) is not int or now < 0:
            raise MediaIoError("serial adapter clock must be a non-negative integer")
        return now

    def _new_budget(self, timeout_steps: int) -> _OperationBudget:
        steps = _bounded_int(
            timeout_steps, label="timeout_steps", minimum=1, maximum=1_000
        )
        start_ns = self._clock_now()
        timeout_ms = min(
            self.config.max_operation_timeout_ms,
            steps * self.config.per_call_timeout_ms,
        )
        return _OperationBudget(
            deadline_ns=start_ns + timeout_ms * _NS_PER_MS,
            last_clock_ns=start_ns,
        )

    def _remaining_timeout_ms(self, budget: _OperationBudget) -> int:
        now = self._clock_now()
        if now < budget.last_clock_ns:
            self._fail_terminal()
            raise MediaIoProtocolError("serial adapter monotonic clock regressed")
        budget.last_clock_ns = now
        remaining_ns = budget.deadline_ns - now
        if remaining_ns <= 0:
            self._raise_progress_timeout(budget, "serial operation deadline expired")
        return min(
            self.config.per_call_timeout_ms,
            max(1, (remaining_ns + _NS_PER_MS - 1) // _NS_PER_MS),
        )

    def _ensure_open(self) -> None:
        with self._state_lock:
            if self._closed:
                raise MediaIoError("host serial adapter is closed")

    def _request_cancel_once(self) -> None:
        with self._state_lock:
            if self._cancel_requested:
                return
            self._cancel_requested = True
        try:
            self.serial_port.cancel_pending_io()
        except Exception:
            with self._state_lock:
                self._cancel_error = True

    def _fail_terminal(self) -> None:
        with self._state_lock:
            self._terminal = True
            self._closed = True
            self._terminal_errors += 1
        self._request_cancel_once()

    def _raise_progress_timeout(
        self, budget: _OperationBudget, message: str, *, explicit_progress: int | None = 0
    ) -> None:
        retry_safe = budget.progress_bytes == 0 and explicit_progress == 0
        if retry_safe:
            with self._state_lock:
                self._zero_progress_timeouts += 1
        else:
            self._fail_terminal()
        raise MediaIoTimeout(message, retry_safe=retry_safe)

    def _before_serial_call(self, budget: _OperationBudget) -> int:
        if budget.calls >= self.config.max_serial_calls_per_operation:
            self._raise_progress_timeout(
                budget, "serial operation exhausted its bounded callback count"
            )
        timeout_ms = self._remaining_timeout_ms(budget)
        budget.calls += 1
        return timeout_ms

    def _check_after_serial_call(self, budget: _OperationBudget) -> None:
        now = self._clock_now()
        if now < budget.last_clock_ns:
            self._fail_terminal()
            raise MediaIoProtocolError("serial adapter monotonic clock regressed")
        budget.last_clock_ns = now
        if now > budget.deadline_ns:
            self._raise_progress_timeout(
                budget,
                "serial operation completed after its bounded deadline",
                explicit_progress=None,
            )

    def _read_more(self, required: int, budget: _OperationBudget) -> None:
        self._ensure_open()
        count_requested = min(required, self.config.read_chunk_bytes)
        scratch = bytearray(count_requested)
        view = memoryview(scratch)
        try:
            timeout_ms = self._before_serial_call(budget)
            try:
                count = self.serial_port.readinto(view, timeout_ms=timeout_ms)
            except InjectedSerialTimeout as error:
                self._raise_progress_timeout(
                    budget,
                    "injected serial read timed out",
                    explicit_progress=error.progress,
                )
            except Exception as error:
                self._fail_terminal()
                raise MediaIoError(
                    "injected serial read failed with unknown progress"
                ) from error
            if type(count) is not int or not 0 <= count <= count_requested:
                self._fail_terminal()
                raise MediaIoProtocolError(
                    "injected serial read returned an invalid progress count"
                )
            if count == 0:
                self._raise_progress_timeout(
                    budget, "injected serial read made zero progress"
                )
            budget.progress_bytes += count
            self._scan.extend(view[:count])
            self._check_after_serial_call(budget)
        finally:
            view.release()
            _zero(scratch)

    def _fill_scan(self, target_size: int, budget: _OperationBudget) -> None:
        if target_size > MAX_WIRE_BYTES:
            self._fail_terminal()
            raise MediaIoProtocolError("serial candidate exceeds bounded wire size")
        while len(self._scan) < target_size:
            self._read_more(target_size - len(self._scan), budget)

    def _discard_scan_prefix(self, count: int, budget: _OperationBudget) -> None:
        if not 0 <= count <= len(self._scan):
            self._fail_terminal()
            raise MediaIoProtocolError("serial resynchronizer internal discard error")
        if count:
            self._scan[:count] = b"\x00" * count
            del self._scan[:count]
            budget.discarded_bytes += count
            with self._state_lock:
                self._prefix_bytes_discarded += count
        if budget.discarded_bytes > self.config.max_resync_discard_bytes:
            self._fail_terminal()
            raise MediaIoProtocolError("bounded serial resynchronization limit exceeded")

    def _align_magic(self, budget: _OperationBudget) -> None:
        while True:
            index = self._scan.find(WIRE_MAGIC)
            if index >= 0:
                self._discard_scan_prefix(index, budget)
                return

            keep = 0
            maximum = min(len(self._scan), len(WIRE_MAGIC) - 1)
            for size in range(maximum, 0, -1):
                if self._scan[-size:] == WIRE_MAGIC[:size]:
                    keep = size
                    break
            self._discard_scan_prefix(len(self._scan) - keep, budget)
            self._fill_scan(len(WIRE_MAGIC), budget)

    def _reject_false_candidate(self, budget: _OperationBudget) -> None:
        budget.invalid_candidates += 1
        with self._state_lock:
            self._invalid_candidates += 1
        if budget.invalid_candidates > self.config.max_invalid_candidates:
            self._fail_terminal()
            raise MediaIoProtocolError("bounded invalid serial candidate limit exceeded")
        self._discard_scan_prefix(1, budget)

    @staticmethod
    def _candidate_length(header_fields: tuple[Any, ...]) -> int | None:
        identifier_sizes = tuple(header_fields[7:11])
        media_size = header_fields[11]
        if any(not 1 <= size <= MAX_IDENTIFIER_BYTES for size in identifier_sizes):
            return None
        if media_size != FRAME_BYTES:
            return None
        total = _HEADER.size + sum(identifier_sizes) + media_size + _CRC.size
        if not MIN_WIRE_BYTES <= total <= MAX_WIRE_BYTES:
            return None
        return total

    def _validate_candidate(self, candidate: bytearray) -> None:
        stream = _CandidateStream(candidate)
        frame: MediaFrame | None = None
        try:
            frame = FrameCodec.read(stream, timeout_steps=1)
            if stream.consumed != len(candidate):
                raise MediaIoProtocolError("serial candidate contains trailing bytes")
            if frame.direction != self.inbound_direction:
                raise MediaIoProtocolError("unexpected serial inbound media direction")
            expected = self.identity.values_for(self.inbound_direction)
            actual = (
                frame.source_role,
                frame.source_id,
                frame.target_role,
                frame.target_id,
                frame.source_clock_id,
            )
            if frame.session_id != self.identity.session_id:
                raise MediaIoProtocolError("serial media session identity mismatch")
            if actual != expected:
                raise MediaIoProtocolError(
                    "serial media endpoint role, identity, or source clock mismatch"
                )
        finally:
            if frame is not None:
                frame.dispose()

    def _load_next_valid_wire(self, budget: _OperationBudget) -> None:
        while True:
            self._align_magic(budget)
            self._fill_scan(_HEADER.size, budget)
            header_fields = _HEADER.unpack_from(self._scan)
            total_size = self._candidate_length(header_fields)
            if total_size is None:
                self._reject_false_candidate(budget)
                continue
            self._fill_scan(total_size, budget)
            expected_crc = _CRC.unpack_from(self._scan, total_size - _CRC.size)[0]
            candidate_view = memoryview(self._scan)[: total_size - _CRC.size]
            try:
                actual_crc = zlib.crc32(candidate_view) & 0xFFFFFFFF
            finally:
                candidate_view.release()
            if actual_crc != expected_crc:
                self._reject_false_candidate(budget)
                continue

            candidate = bytearray(self._scan[:total_size])
            self._scan[:total_size] = b"\x00" * total_size
            del self._scan[:total_size]
            try:
                self._validate_candidate(candidate)
            except Exception:
                _zero(candidate)
                self._fail_terminal()
                raise
            self._ready_wire = candidate
            self._ready_offset = 0
            with self._state_lock:
                self._frames_admitted += 1
            return

    def read_exact(self, size: int, *, timeout_steps: int) -> bytearray:
        requested = _bounded_int(
            size, label="read size", minimum=1, maximum=MAX_WIRE_BYTES
        )
        with self._read_lock:
            self._ensure_open()
            if not self._ready_wire:
                budget = self._new_budget(timeout_steps)
                try:
                    self._load_next_valid_wire(budget)
                except MediaIoTimeout:
                    if budget.progress_bytes:
                        _zero(self._scan)
                        self._scan.clear()
                    raise
                except Exception:
                    _zero(self._scan)
                    self._scan.clear()
                    raise
            remaining = len(self._ready_wire) - self._ready_offset
            if requested > remaining:
                self._fail_terminal()
                _zero(self._ready_wire)
                self._ready_wire.clear()
                raise MediaIoProtocolError(
                    "exact read crosses a validated serial frame boundary"
                )
            result = bytearray(requested)
            end = self._ready_offset + requested
            result[:] = self._ready_wire[self._ready_offset : end]
            self._ready_wire[self._ready_offset : end] = b"\x00" * requested
            self._ready_offset = end
            if self._ready_offset == len(self._ready_wire):
                _zero(self._ready_wire)
                self._ready_wire.clear()
                self._ready_offset = 0
            return result

    def _validate_outbound_wire(self, wire: bytearray) -> None:
        if not MIN_WIRE_BYTES <= len(wire) <= MAX_WIRE_BYTES:
            raise MediaIoProtocolError("serial write must be one bounded EGLM frame")
        if len(wire) < _HEADER.size or bytes(wire[: len(WIRE_MAGIC)]) != WIRE_MAGIC:
            raise MediaIoProtocolError("serial write must start with EGLM magic")
        header_fields = _HEADER.unpack_from(wire)
        expected_size = self._candidate_length(header_fields)
        if expected_size is None or expected_size != len(wire):
            raise MediaIoProtocolError("serial write header or length is invalid")
        expected_crc = _CRC.unpack_from(wire, len(wire) - _CRC.size)[0]
        wire_view = memoryview(wire)[: -_CRC.size]
        try:
            actual_crc = zlib.crc32(wire_view) & 0xFFFFFFFF
        finally:
            wire_view.release()
        if actual_crc != expected_crc:
            raise MediaIoProtocolError("serial write frame integrity check failed")

        stream = _CandidateStream(wire)
        frame: MediaFrame | None = None
        try:
            frame = FrameCodec.read(stream, timeout_steps=1)
            if stream.consumed != len(wire) or frame.direction != self.outbound_direction:
                raise MediaIoProtocolError("unexpected serial outbound media direction")
            expected = self.identity.values_for(self.outbound_direction)
            actual = (
                frame.source_role,
                frame.source_id,
                frame.target_role,
                frame.target_id,
                frame.source_clock_id,
            )
            if frame.session_id != self.identity.session_id or actual != expected:
                raise MediaIoProtocolError(
                    "serial outbound session, role, identity, or source clock mismatch"
                )
        finally:
            if frame is not None:
                frame.dispose()

    def write_all(self, data: memoryview, *, timeout_steps: int) -> None:
        if not isinstance(data, memoryview):
            raise MediaIoError("serial write requires a memoryview")
        if data.ndim != 1 or not data.c_contiguous:
            raise MediaIoError("serial write buffer must be one contiguous byte view")
        with self._write_lock:
            self._ensure_open()
            wire = bytearray(data)
            try:
                self._validate_outbound_wire(wire)
                budget = self._new_budget(timeout_steps)
                offset = 0
                while offset < len(wire):
                    self._ensure_open()
                    timeout_ms = self._before_serial_call(budget)
                    view = memoryview(wire)[offset:]
                    try:
                        try:
                            count = self.serial_port.write(view, timeout_ms=timeout_ms)
                        except InjectedSerialTimeout as error:
                            self._raise_progress_timeout(
                                budget,
                                "injected serial write timed out",
                                explicit_progress=error.progress,
                            )
                        except Exception as error:
                            self._fail_terminal()
                            raise MediaIoError(
                                "injected serial write failed with unknown progress"
                            ) from error
                    finally:
                        view.release()
                    remaining = len(wire) - offset
                    if type(count) is not int or not 0 <= count <= remaining:
                        self._fail_terminal()
                        raise MediaIoProtocolError(
                            "injected serial write returned an invalid progress count"
                        )
                    if count == 0:
                        self._raise_progress_timeout(
                            budget, "injected serial write made zero progress"
                        )
                    offset += count
                    budget.progress_bytes += count
                    self._check_after_serial_call(budget)
                with self._state_lock:
                    self._frames_written += 1
            finally:
                _zero(wire)

    def close(self) -> None:
        with self._state_lock:
            self._closed = True
        self._request_cancel_once()
        with self._read_lock, self._write_lock:
            _zero(self._scan)
            self._scan.clear()
            _zero(self._ready_wire)
            self._ready_wire.clear()
            self._ready_offset = 0

    def audit(self) -> dict[str, Any]:
        """Return bounded transport metadata without identities or media bytes."""

        with self._state_lock:
            result = {
                "adapter_version": SERIAL_ADAPTER_VERSION,
                "caller_injected_serial": True,
                "serial_enumerated_or_opened_by_adapter": False,
                "caller_owns_serial_close": True,
                "control_plane": "separate_unimplemented_no_in_band_control",
                "frames_admitted": self._frames_admitted,
                "frames_written": self._frames_written,
                "prefix_bytes_discarded": self._prefix_bytes_discarded,
                "invalid_candidates": self._invalid_candidates,
                "zero_progress_timeouts": self._zero_progress_timeouts,
                "terminal_errors": self._terminal_errors,
                "closed": self._closed,
                "terminal": self._terminal,
                "cancel_requested": self._cancel_requested,
                "cancel_error": self._cancel_error,
                "media_logged": False,
                "media_persisted": False,
            }
        return result


def make_wearable_serial_endpoint(
    serial_port: InjectedSerial,
    identity: EndpointIdentity,
    *,
    config: HostSerialAdapterConfig | None = None,
    clock: MonotonicClock | None = None,
) -> FramedEndpoint:
    """Create the existing strict endpoint without enumerating/opening a port."""

    stream = HostSerialOrderedByteStream(
        serial_port,
        identity,
        inbound_direction="uplink",
        outbound_direction="downlink",
        config=config,
        clock=clock,
    )
    return FramedEndpoint(
        stream,
        identity,
        inbound_direction="uplink",
        outbound_direction="downlink",
    )

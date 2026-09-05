"""CALL-020B private framed-media I/O seam.

This module keeps the CALL media plane separate from the Message Hub and from
``egolink.p0.v1``.  It defines one temporary engineering profile (PCM S16LE,
16 kHz, mono, 20 ms, exactly 640 bytes), strict binary framing, bounded duplex
queues, an in-memory byte-stream test double, and a fail-closed TLS relay
connector boundary.

The CLI is deliberately offline: it can run a fake duplex loop or validate
locally injected TLS inputs, but it has no option that opens a socket, serial
port, audio device, or hardware interface.  A real connector call additionally
requires an explicit ``operator_authorized=True`` argument.  No media is
written to disk or logs.  Runtime-owned mutable buffers are zeroed after
delivery, rejection, or cleanup.  External streams, sinks, operating systems,
and TLS implementations may make independent copies; this module cannot erase
or govern those copies.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import socket
import ssl
import struct
import zlib
from collections import deque
from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from pc_simulator.ego_call_media_probe import MediaTraceError, evaluate_media_trace
from pc_simulator.ego_call_media_runtime import (
    EvaluationBudget,
    FRAME_DURATION_NS,
    Pcm16EngineeringProfile,
)


IO_VERSION = "egolink.ego_call_media_io.v0.1"
WIRE_MAGIC = b"EGLM"
WIRE_VERSION = 1
AUTH_MAGIC = b"EGLA"
AUTH_ACK = b"EGLK\x01"
FRAME_BYTES = 640
MAX_IDENTIFIER_BYTES = 128
MAX_TOKEN_BYTES = 4096
MAX_FRAME_COUNT = 30_000
_HEADER = struct.Struct("!4sBBBBQQHHHHH")
_CRC = struct.Struct("!I")
_AUTH_HEADER = struct.Struct("!4sBH")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9._:-]+$")
_DIRECTION_CODE = {"uplink": 1, "downlink": 2}
_CODE_DIRECTION = {value: key for key, value in _DIRECTION_CODE.items()}
_ROLE_CODE = {"device": 1, "guardian": 2}
_CODE_ROLE = {value: key for key, value in _ROLE_CODE.items()}


class MediaIoError(ValueError):
    """Base error for a rejected CALL-020B I/O operation."""


class MediaIoTimeout(MediaIoError):
    """A bounded stream operation timed out.

    ``retry_safe`` is true only when the adapter proves that zero bytes were
    consumed or emitted.  Ordered streams with partial or unknown progress
    must be treated as terminal so a retry cannot duplicate bytes or lose the
    frame boundary.
    """

    def __init__(self, message: str, *, retry_safe: bool = False):
        super().__init__(message)
        self.retry_safe = retry_safe


class MediaIoProtocolError(MediaIoError):
    """A binary frame violated the private CALL-020B media contract."""


def _zero(buffer: bytearray) -> None:
    buffer[:] = b"\x00" * len(buffer)


def _all_zero(buffer: bytearray) -> bool:
    return all(value == 0 for value in buffer)


def _identifier(value: object, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value.encode("ascii", errors="ignore")) != len(value)
        or len(value) > MAX_IDENTIFIER_BYTES
        or _IDENTIFIER.fullmatch(value) is None
    ):
        raise MediaIoProtocolError(
            f"{label} must be 1-{MAX_IDENTIFIER_BYTES} ASCII identifier characters"
        )
    return value


def _bounded_int(value: object, *, label: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise MediaIoError(f"{label} must be an integer in [{minimum}, {maximum}]")
    return value


def _roles(direction: str) -> tuple[str, str]:
    if direction == "uplink":
        return "device", "guardian"
    if direction == "downlink":
        return "guardian", "device"
    raise MediaIoProtocolError("direction must be uplink or downlink")


def _assert_metadata_only(value: object, *, path: str = "result") -> None:
    if isinstance(value, (bytes, bytearray, memoryview)):
        raise MediaIoError(f"binary material escaped into {path}")
    if isinstance(value, Mapping):
        for key, item in value.items():
            _assert_metadata_only(item, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _assert_metadata_only(item, path=f"{path}[{index}]")


@dataclass(slots=True)
class MediaFrame:
    """One owned mutable media frame; callers must dispose it after use."""

    session_id: str
    direction: str
    source_role: str
    source_id: str
    target_role: str
    target_id: str
    sequence: int
    source_clock_id: str
    source_time_ns: int
    media: bytearray

    def validate(self) -> None:
        _identifier(self.session_id, label="session_id")
        expected_source, expected_target = _roles(self.direction)
        if self.source_role != expected_source or self.target_role != expected_target:
            raise MediaIoProtocolError("frame roles do not match direction")
        _identifier(self.source_id, label="source_id")
        _identifier(self.target_id, label="target_id")
        _identifier(self.source_clock_id, label="source_clock_id")
        _bounded_int(self.sequence, label="sequence", minimum=0, maximum=2**63 - 1)
        _bounded_int(
            self.source_time_ns,
            label="source_time_ns",
            minimum=0,
            maximum=2**63 - 1,
        )
        if not isinstance(self.media, bytearray) or len(self.media) != FRAME_BYTES:
            raise MediaIoProtocolError("media must be one mutable 640-byte frame")

    def dispose(self) -> None:
        _zero(self.media)


class ByteStream(Protocol):
    """Minimal ordered byte stream used by future USB CDC and TLS adapters."""

    def read_exact(self, size: int, *, timeout_steps: int) -> bytearray: ...

    def write_all(self, data: memoryview, *, timeout_steps: int) -> None: ...

    def close(self) -> None: ...


@dataclass(slots=True)
class _PipeChunk:
    data: bytearray
    offset: int = 0


class _MemoryPipe:
    def __init__(self, capacity_bytes: int):
        self.capacity_bytes = capacity_bytes
        self.pending_bytes = 0
        self.closed = False
        self.chunks: deque[_PipeChunk] = deque()
        self.all_buffers: list[bytearray] = []

    def append(self, data: memoryview) -> None:
        if self.closed:
            raise MediaIoError("memory transport is closed")
        if self.pending_bytes + len(data) > self.capacity_bytes:
            raise MediaIoTimeout(
                "memory transport capacity exhausted", retry_safe=True
            )
        owned = bytearray(data)
        self.all_buffers.append(owned)
        self.chunks.append(_PipeChunk(owned))
        self.pending_bytes += len(owned)

    def take(self, size: int) -> bytearray:
        if self.closed:
            raise MediaIoError("memory transport is closed")
        if self.pending_bytes < size:
            raise MediaIoTimeout(
                "bounded read has no complete frame", retry_safe=True
            )
        result = bytearray(size)
        written = 0
        while written < size:
            chunk = self.chunks[0]
            available = len(chunk.data) - chunk.offset
            count = min(size - written, available)
            result[written : written + count] = chunk.data[
                chunk.offset : chunk.offset + count
            ]
            chunk.data[chunk.offset : chunk.offset + count] = b"\x00" * count
            chunk.offset += count
            written += count
            self.pending_bytes -= count
            if chunk.offset == len(chunk.data):
                self.chunks.popleft()
        return result

    def dispose(self) -> None:
        self.closed = True
        for chunk in self.chunks:
            _zero(chunk.data)
        self.chunks.clear()
        self.pending_bytes = 0

    def audit(self) -> dict[str, Any]:
        return {
            "owned_buffer_count": len(self.all_buffers),
            "owned_buffers_zeroized": all(_all_zero(item) for item in self.all_buffers),
            "pending_bytes": self.pending_bytes,
        }


class InMemoryByteStream:
    """Bounded ordered fake-serial stream; no OS handle or socket is opened."""

    def __init__(self, incoming: _MemoryPipe, outgoing: _MemoryPipe):
        self._incoming = incoming
        self._outgoing = outgoing
        self._read_timeouts = 0
        self._write_timeouts = 0
        self._closed = False

    def inject_read_timeouts(self, count: int) -> None:
        self._read_timeouts += _bounded_int(
            count, label="read timeout count", minimum=0, maximum=100_000
        )

    def inject_write_timeouts(self, count: int) -> None:
        self._write_timeouts += _bounded_int(
            count, label="write timeout count", minimum=0, maximum=100_000
        )

    def read_exact(self, size: int, *, timeout_steps: int) -> bytearray:
        _bounded_int(size, label="read size", minimum=1, maximum=4096)
        _bounded_int(timeout_steps, label="timeout_steps", minimum=1, maximum=1000)
        if self._closed:
            raise MediaIoError("memory stream is closed")
        if self._read_timeouts:
            self._read_timeouts -= 1
            raise MediaIoTimeout(
                "scripted bounded read timeout", retry_safe=True
            )
        return self._incoming.take(size)

    def write_all(self, data: memoryview, *, timeout_steps: int) -> None:
        _bounded_int(timeout_steps, label="timeout_steps", minimum=1, maximum=1000)
        if self._closed:
            raise MediaIoError("memory stream is closed")
        if self._write_timeouts:
            self._write_timeouts -= 1
            raise MediaIoTimeout(
                "scripted bounded write timeout", retry_safe=True
            )
        self._outgoing.append(data)

    def close(self) -> None:
        self._closed = True

    def dispose_transport_buffers(self) -> None:
        self._incoming.dispose()
        self._outgoing.dispose()

    def audit(self) -> dict[str, Any]:
        incoming = self._incoming.audit()
        outgoing = self._outgoing.audit()
        return {
            "owned_buffer_count": (
                incoming["owned_buffer_count"] + outgoing["owned_buffer_count"]
            ),
            "owned_buffers_zeroized": (
                incoming["owned_buffers_zeroized"]
                and outgoing["owned_buffers_zeroized"]
            ),
            "pending_bytes": incoming["pending_bytes"] + outgoing["pending_bytes"],
        }


def memory_stream_pair(*, capacity_bytes: int = 2_000_000) -> tuple[
    InMemoryByteStream, InMemoryByteStream
]:
    _bounded_int(
        capacity_bytes,
        label="capacity_bytes",
        minimum=1024,
        maximum=64_000_000,
    )
    left_to_right = _MemoryPipe(capacity_bytes)
    right_to_left = _MemoryPipe(capacity_bytes)
    return (
        InMemoryByteStream(right_to_left, left_to_right),
        InMemoryByteStream(left_to_right, right_to_left),
    )


class FrameCodec:
    """Encode/decode one private media frame without changing public contracts."""

    @staticmethod
    def encode(frame: MediaFrame) -> bytearray:
        frame.validate()
        identifiers = tuple(
            value.encode("ascii")
            for value in (
                frame.session_id,
                frame.source_id,
                frame.target_id,
                frame.source_clock_id,
            )
        )
        header = _HEADER.pack(
            WIRE_MAGIC,
            WIRE_VERSION,
            _DIRECTION_CODE[frame.direction],
            _ROLE_CODE[frame.source_role],
            _ROLE_CODE[frame.target_role],
            frame.sequence,
            frame.source_time_ns,
            *(len(value) for value in identifiers),
            len(frame.media),
        )
        wire = bytearray(header)
        for value in identifiers:
            wire.extend(value)
        wire.extend(frame.media)
        wire.extend(_CRC.pack(zlib.crc32(wire) & 0xFFFFFFFF))
        return wire

    @staticmethod
    def read(stream: ByteStream, *, timeout_steps: int) -> MediaFrame:
        header = stream.read_exact(_HEADER.size, timeout_steps=timeout_steps)
        tail: bytearray | None = None
        try:
            if len(header) != _HEADER.size:
                raise MediaIoProtocolError("short media header")
            unpacked = _HEADER.unpack(header)
            (
                magic,
                version,
                direction_code,
                source_code,
                target_code,
                sequence,
                source_time_ns,
                session_size,
                source_id_size,
                target_id_size,
                clock_size,
                media_size,
            ) = unpacked
            if magic != WIRE_MAGIC or version != WIRE_VERSION:
                raise MediaIoProtocolError("unknown media framing version")
            if direction_code not in _CODE_DIRECTION:
                raise MediaIoProtocolError("unknown media direction")
            if source_code not in _CODE_ROLE or target_code not in _CODE_ROLE:
                raise MediaIoProtocolError("unknown media endpoint role")
            identifier_sizes = (
                session_size,
                source_id_size,
                target_id_size,
                clock_size,
            )
            if any(not 1 <= size <= MAX_IDENTIFIER_BYTES for size in identifier_sizes):
                raise MediaIoProtocolError("invalid media identifier length")
            if media_size != FRAME_BYTES:
                raise MediaIoProtocolError("wire frame must contain exactly 640 media bytes")
            body_size = sum(identifier_sizes) + media_size
            try:
                tail = stream.read_exact(
                    body_size + _CRC.size, timeout_steps=timeout_steps
                )
            except MediaIoTimeout as error:
                # The header is already consumed.  Retrying at the endpoint
                # would interpret the body as a new header and lose framing.
                stream.close()
                raise MediaIoProtocolError(
                    "ordered media frame timed out after header consumption"
                ) from error
            expected_crc = _CRC.unpack(tail[-_CRC.size :])[0]
            actual_crc = zlib.crc32(header)
            actual_crc = zlib.crc32(tail[:-_CRC.size], actual_crc) & 0xFFFFFFFF
            if actual_crc != expected_crc:
                raise MediaIoProtocolError("media frame integrity check failed")
            cursor = 0
            decoded: list[str] = []
            for size in identifier_sizes:
                raw_identifier = bytes(tail[cursor : cursor + size])
                cursor += size
                try:
                    decoded.append(raw_identifier.decode("ascii"))
                except UnicodeDecodeError as error:
                    raise MediaIoProtocolError("media identifier is not ASCII") from error
            session_id, source_id, target_id, source_clock_id = decoded
            media = bytearray(tail[cursor : cursor + media_size])
            frame = MediaFrame(
                session_id=session_id,
                direction=_CODE_DIRECTION[direction_code],
                source_role=_CODE_ROLE[source_code],
                source_id=source_id,
                target_role=_CODE_ROLE[target_code],
                target_id=target_id,
                sequence=sequence,
                source_clock_id=source_clock_id,
                source_time_ns=source_time_ns,
                media=media,
            )
            try:
                frame.validate()
            except Exception:
                frame.dispose()
                raise
            return frame
        finally:
            _zero(header)
            if tail is not None:
                _zero(tail)


@dataclass(frozen=True)
class EndpointIdentity:
    session_id: str
    device_id: str
    guardian_id: str
    uplink_clock_id: str
    downlink_clock_id: str

    def validate(self) -> None:
        for label in (
            "session_id",
            "device_id",
            "guardian_id",
            "uplink_clock_id",
            "downlink_clock_id",
        ):
            _identifier(getattr(self, label), label=label)
        if self.device_id == self.guardian_id:
            raise MediaIoProtocolError("device and guardian identities must differ")
        if self.uplink_clock_id == self.downlink_clock_id:
            raise MediaIoProtocolError("direction source clocks must differ")

    def values_for(self, direction: str) -> tuple[str, str, str, str, str]:
        source_role, target_role = _roles(direction)
        if direction == "uplink":
            return (
                source_role,
                self.device_id,
                target_role,
                self.guardian_id,
                self.uplink_clock_id,
            )
        return (
            source_role,
            self.guardian_id,
            target_role,
            self.device_id,
            self.downlink_clock_id,
        )


class FramedEndpoint:
    """Strict session/role/sequence wrapper over an ordered byte stream."""

    def __init__(
        self,
        stream: ByteStream,
        identity: EndpointIdentity,
        *,
        inbound_direction: str,
        outbound_direction: str,
    ):
        identity.validate()
        if {inbound_direction, outbound_direction} != {"uplink", "downlink"}:
            raise MediaIoProtocolError("endpoint directions must be opposite")
        self.stream = stream
        self.identity = identity
        self.inbound_direction = inbound_direction
        self.outbound_direction = outbound_direction
        self.expected_inbound_sequence = 0
        self.expected_outbound_sequence = 0

    def _validate_identity(self, frame: MediaFrame, *, direction: str) -> None:
        expected = self.identity.values_for(direction)
        actual = (
            frame.source_role,
            frame.source_id,
            frame.target_role,
            frame.target_id,
            frame.source_clock_id,
        )
        if frame.session_id != self.identity.session_id:
            raise MediaIoProtocolError("media session identity mismatch")
        if actual != expected:
            raise MediaIoProtocolError("media endpoint or source-clock identity mismatch")

    def receive(self, *, timeout_steps: int, attempts: int) -> tuple[MediaFrame, int]:
        _bounded_int(attempts, label="receive attempts", minimum=1, maximum=16)
        for attempt in range(1, attempts + 1):
            try:
                frame = FrameCodec.read(self.stream, timeout_steps=timeout_steps)
            except MediaIoTimeout as error:
                if not error.retry_safe:
                    self.stream.close()
                    raise MediaIoProtocolError(
                        "ordered media receive timed out with unknown progress"
                    ) from error
                if attempt == attempts:
                    raise
                continue
            try:
                if frame.direction != self.inbound_direction:
                    raise MediaIoProtocolError("unexpected inbound media direction")
                self._validate_identity(frame, direction=frame.direction)
                if frame.sequence != self.expected_inbound_sequence:
                    raise MediaIoProtocolError("non-contiguous inbound media sequence")
            except Exception:
                frame.dispose()
                raise
            self.expected_inbound_sequence += 1
            return frame, attempt
        raise AssertionError("bounded receive loop did not terminate")

    def send(
        self,
        frame: MediaFrame,
        *,
        timeout_steps: int,
        attempts: int,
    ) -> int:
        _bounded_int(attempts, label="send attempts", minimum=1, maximum=16)
        wire: bytearray | None = None
        try:
            if frame.direction != self.outbound_direction:
                raise MediaIoProtocolError("unexpected outbound media direction")
            self._validate_identity(frame, direction=frame.direction)
            if frame.sequence != self.expected_outbound_sequence:
                raise MediaIoProtocolError("non-contiguous outbound media sequence")
            wire = FrameCodec.encode(frame)
            for attempt in range(1, attempts + 1):
                try:
                    self.stream.write_all(memoryview(wire), timeout_steps=timeout_steps)
                except MediaIoTimeout as error:
                    if not error.retry_safe:
                        self.stream.close()
                        raise MediaIoProtocolError(
                            "ordered media send timed out with unknown progress"
                        ) from error
                    if attempt == attempts:
                        raise
                    continue
                self.expected_outbound_sequence += 1
                return attempt
            raise AssertionError("bounded send loop did not terminate")
        finally:
            if wire is not None:
                _zero(wire)
            frame.dispose()


@dataclass(frozen=True)
class MediaIoConfig:
    identity: EndpointIdentity = field(
        default_factory=lambda: EndpointIdentity(
            session_id="call020b-local-session-001",
            device_id="wearable-node-001",
            guardian_id="guardian-fixture-001",
            uplink_clock_id="wearable-clock-001",
            downlink_clock_id="guardian-clock-001",
        )
    )
    bridge_clock_id: str = "pc-bridge-clock-001"
    frame_count: int = 12
    max_cycles: int = 24
    timeout_steps: int = 1
    receive_attempts: int = 2
    send_attempts: int = 2
    uplink_queue_capacity: int = 4
    downlink_queue_capacity: int = 4
    uplink_service_interval_cycles: int = 1
    downlink_service_interval_cycles: int = 1
    evaluation: EvaluationBudget = field(default_factory=EvaluationBudget)
    profile: Pcm16EngineeringProfile = field(default_factory=Pcm16EngineeringProfile)

    def validate(self) -> dict[str, Any]:
        self.identity.validate()
        _identifier(self.bridge_clock_id, label="bridge_clock_id")
        frame_count = _bounded_int(
            self.frame_count,
            label="frame_count",
            minimum=2,
            maximum=MAX_FRAME_COUNT,
        )
        _bounded_int(
            self.max_cycles,
            label="max_cycles",
            minimum=frame_count,
            maximum=MAX_FRAME_COUNT + 10_000,
        )
        _bounded_int(self.timeout_steps, label="timeout_steps", minimum=1, maximum=1000)
        _bounded_int(
            self.receive_attempts, label="receive_attempts", minimum=1, maximum=16
        )
        _bounded_int(self.send_attempts, label="send_attempts", minimum=1, maximum=16)
        for label in ("uplink_queue_capacity", "downlink_queue_capacity"):
            _bounded_int(getattr(self, label), label=label, minimum=1, maximum=512)
        for label in (
            "uplink_service_interval_cycles",
            "downlink_service_interval_cycles",
        ):
            _bounded_int(getattr(self, label), label=label, minimum=1, maximum=1024)
        self.profile.validate()
        if self.profile.frame_bytes != FRAME_BYTES:
            raise MediaIoError("CALL-020B profile must produce exactly 640 bytes")
        return self.evaluation.trace_config(frame_count=frame_count)


class DuplexMediaBridge:
    """Bounded independent uplink/downlink pump over two framed endpoints."""

    def __init__(self, config: MediaIoConfig):
        self.config = config

    def run(
        self, *, wearable: FramedEndpoint, relay: FramedEndpoint
    ) -> dict[str, Any]:
        config = self.config
        trace_config = config.validate()
        if wearable.inbound_direction != "uplink" or wearable.outbound_direction != "downlink":
            raise MediaIoProtocolError("wearable bridge endpoint directions are invalid")
        if relay.inbound_direction != "downlink" or relay.outbound_direction != "uplink":
            raise MediaIoProtocolError("relay bridge endpoint directions are invalid")
        if wearable.identity != config.identity or relay.identity != config.identity:
            raise MediaIoProtocolError(
                "bridge endpoint identity must match the configured session before I/O"
            )
        queues: dict[str, deque[MediaFrame]] = {
            "uplink": deque(),
            "downlink": deque(),
        }
        capacities = {
            "uplink": config.uplink_queue_capacity,
            "downlink": config.downlink_queue_capacity,
        }
        intervals = {
            "uplink": config.uplink_service_interval_cycles,
            "downlink": config.downlink_service_interval_cycles,
        }
        inbound = {"uplink": wearable, "downlink": relay}
        outbound = {"uplink": relay, "downlink": wearable}
        stats = {
            direction: {
                "frames_received": 0,
                "frames_forwarded": 0,
                "receive_retry_count": 0,
                "send_retry_count": 0,
                "receive_timeout_exhaustions": 0,
                "send_timeout_exhaustions": 0,
                "protocol_failures": 0,
                "backpressure_drops": 0,
                "peak_queue_depth": 0,
                "cleanup_drops": 0,
            }
            for direction in ("uplink", "downlink")
        }
        records: list[dict[str, Any]] = []
        stopped = {"uplink": False, "downlink": False}
        executed_cycles = 0
        bridge_slot = 0
        last_trace_time = -1

        try:
            for cycle in range(config.max_cycles):
                executed_cycles = cycle + 1
                for direction in ("uplink", "downlink"):
                    if stopped[direction] or stats[direction]["frames_received"] >= config.frame_count:
                        continue
                    try:
                        frame, attempts = inbound[direction].receive(
                            timeout_steps=config.timeout_steps,
                            attempts=config.receive_attempts,
                        )
                    except MediaIoTimeout:
                        stats[direction]["receive_timeout_exhaustions"] += 1
                        continue
                    except MediaIoProtocolError:
                        stats[direction]["protocol_failures"] += 1
                        stopped[direction] = True
                        continue
                    stats[direction]["receive_retry_count"] += attempts - 1
                    stats[direction]["frames_received"] += 1
                    if len(queues[direction]) >= capacities[direction]:
                        stats[direction]["backpressure_drops"] += 1
                        frame.dispose()
                        stopped[direction] = True
                        continue
                    queues[direction].append(frame)
                    stats[direction]["peak_queue_depth"] = max(
                        stats[direction]["peak_queue_depth"], len(queues[direction])
                    )

                for direction in ("uplink", "downlink"):
                    if not queues[direction] or (cycle + 1) % intervals[direction] != 0:
                        continue
                    frame = queues[direction].popleft()
                    frame_metadata = {
                        "session_id": frame.session_id,
                        "direction": frame.direction,
                        "source_role": frame.source_role,
                        "source_id": frame.source_id,
                        "target_role": frame.target_role,
                        "target_id": frame.target_id,
                        "sequence": frame.sequence,
                        "source_clock_id": frame.source_clock_id,
                        "source_time_ns": frame.source_time_ns,
                    }
                    try:
                        attempts = outbound[direction].send(
                            frame,
                            timeout_steps=config.timeout_steps,
                            attempts=config.send_attempts,
                        )
                    except MediaIoTimeout:
                        stats[direction]["send_timeout_exhaustions"] += 1
                        stopped[direction] = True
                        continue
                    except MediaIoProtocolError:
                        stats[direction]["protocol_failures"] += 1
                        stopped[direction] = True
                        continue
                    stats[direction]["send_retry_count"] += attempts - 1
                    stats[direction]["frames_forwarded"] += 1
                    bridge_slot += 1
                    trace_time = cycle * FRAME_DURATION_NS + bridge_slot
                    if trace_time <= last_trace_time:
                        raise MediaIoError("bridge monotonic timestamp invariant failed")
                    last_trace_time = trace_time
                    records.append(
                        {
                            "observation_id": (
                                f"call020b:{direction}:{frame_metadata['sequence']}:forward"
                            ),
                            "packet_id": (
                                f"{frame_metadata['session_id']}:{direction}:"
                                f"{frame_metadata['sequence']}"
                            ),
                            **frame_metadata,
                            "trace_clock_id": config.bridge_clock_id,
                            "trace_time_ns": trace_time,
                            "encoded_size_bytes": FRAME_BYTES,
                        }
                    )

                complete = all(
                    stats[direction]["frames_received"] >= config.frame_count
                    and not queues[direction]
                    for direction in ("uplink", "downlink")
                )
                if complete:
                    break
        finally:
            for direction in ("uplink", "downlink"):
                while queues[direction]:
                    queues[direction].popleft().dispose()
                    stats[direction]["cleanup_drops"] += 1

        trace_end = max(
            FRAME_DURATION_NS,
            executed_cycles * FRAME_DURATION_NS,
            last_trace_time + FRAME_DURATION_NS,
        )
        trace = {
            "trace_version": "egolink.ego_call_media_trace.v0.1",
            "trace_id": "call020b-bridge-trace-001",
            "session_id": config.identity.session_id,
            "trace_clock_id": config.bridge_clock_id,
            "trace_start_time_ns": 0,
            "trace_end_time_ns": trace_end,
            "endpoints": {
                "device_id": config.identity.device_id,
                "guardian_id": config.identity.guardian_id,
            },
            "source_clock_ids": {
                "uplink": config.identity.uplink_clock_id,
                "downlink": config.identity.downlink_clock_id,
            },
            "config": trace_config,
            "records": records,
        }
        try:
            evaluation = evaluate_media_trace(trace)
        except MediaTraceError as error:
            raise MediaIoError("metadata evaluator rejected bridge trace") from error
        result = {
            "io_version": IO_VERSION,
            "result": evaluation["evaluation_result"],
            "profile": config.profile.metadata(),
            "transport_boundary": {
                "media_plane": "private_call020b_binary_framing",
                "control_plane": "egolink.p0.v1_message_hub_separate_not_used",
                "signaling": "out_of_band_fixture_only",
                "fake_stream": True,
                "tls_required_for_real_relay": True,
                "production_rtc_selected": False,
                "pump_model": "sequential_deterministic_fake_steps",
                "real_concurrent_20ms_pump": "not_implemented",
                "real_deadline_model": "not_implemented",
            },
            "bounded_run": {
                "requested_frames_per_direction": config.frame_count,
                "maximum_cycles": config.max_cycles,
                "executed_cycles": executed_cycles,
                "bridge_metadata_records": len(records),
                "raw_audio_persisted": False,
                "raw_audio_logged": False,
                "network_serial_audio_hardware_used": False,
            },
            "direction_stats": stats,
            "evaluation": evaluation,
            "privacy_boundary": {
                "runtime_owned_mutable_buffers_zeroed": True,
                "external_adapter_or_sink_copies": "not_controlled_by_this_runtime",
            },
            "claims": {
                "local_framed_io": "verified",
                "wearable_usb_cdc_media": "unverified",
                "source_bound_lte_egress": "unverified",
                "tls_relay_media": "unverified",
                "actual_io_ready": False,
                "device_audio": "unverified",
                "p0_call": "NOT_RUN",
            },
        }
        _assert_metadata_only(result)
        return result


def _make_frame(config: MediaIoConfig, direction: str, sequence: int) -> MediaFrame:
    source_role, source_id, target_role, target_id, clock_id = (
        config.identity.values_for(direction)
    )
    seed = (sequence * 31 + (11 if direction == "uplink" else 173)) & 0xFF
    return MediaFrame(
        session_id=config.identity.session_id,
        direction=direction,
        source_role=source_role,
        source_id=source_id,
        target_role=target_role,
        target_id=target_id,
        sequence=sequence,
        source_clock_id=clock_id,
        source_time_ns=sequence * FRAME_DURATION_NS,
        media=bytearray([seed or 1]) * FRAME_BYTES,
    )


def _endpoint(
    stream: ByteStream,
    config: MediaIoConfig,
    *,
    inbound: str,
    outbound: str,
) -> FramedEndpoint:
    return FramedEndpoint(
        stream,
        config.identity,
        inbound_direction=inbound,
        outbound_direction=outbound,
    )


def run_fake_duplex(
    config: MediaIoConfig | None = None,
    *,
    scenario: str = "healthy",
) -> dict[str, Any]:
    """Run an end-to-end fake-serial/relay scenario and return metadata only."""

    if scenario not in {
        "healthy",
        "one-way",
        "timeout-recovery",
        "timeout-failure",
        "backpressure",
    }:
        raise MediaIoError("unknown fake duplex scenario")
    active = config or MediaIoConfig()
    active.validate()
    wearable_peer_stream, wearable_bridge_stream = memory_stream_pair()
    relay_bridge_stream, relay_peer_stream = memory_stream_pair()
    wearable_peer = _endpoint(
        wearable_peer_stream, active, inbound="downlink", outbound="uplink"
    )
    wearable_bridge = _endpoint(
        wearable_bridge_stream, active, inbound="uplink", outbound="downlink"
    )
    relay_bridge = _endpoint(
        relay_bridge_stream, active, inbound="downlink", outbound="uplink"
    )
    relay_peer = _endpoint(
        relay_peer_stream, active, inbound="uplink", outbound="downlink"
    )
    payload_refs: list[bytearray] = []
    sink_counts = {"uplink": 0, "downlink": 0}
    try:
        for sequence in range(active.frame_count):
            uplink = _make_frame(active, "uplink", sequence)
            payload_refs.append(uplink.media)
            wearable_peer.send(
                uplink, timeout_steps=active.timeout_steps, attempts=active.send_attempts
            )
            if scenario != "one-way":
                downlink = _make_frame(active, "downlink", sequence)
                payload_refs.append(downlink.media)
                relay_peer.send(
                    downlink,
                    timeout_steps=active.timeout_steps,
                    attempts=active.send_attempts,
                )

        if scenario == "timeout-recovery":
            relay_bridge_stream.inject_read_timeouts(1)
        elif scenario == "timeout-failure":
            relay_bridge_stream.inject_read_timeouts(
                active.max_cycles * active.receive_attempts
            )

        result = DuplexMediaBridge(active).run(
            wearable=wearable_bridge, relay=relay_bridge
        )
        for direction, peer in (("uplink", relay_peer), ("downlink", wearable_peer)):
            forwarded = result["direction_stats"][direction]["frames_forwarded"]
            for _ in range(forwarded):
                received, _ = peer.receive(
                    timeout_steps=active.timeout_steps,
                    attempts=active.receive_attempts,
                )
                payload_refs.append(received.media)
                received.dispose()
                sink_counts[direction] += 1
    finally:
        for stream in (
            wearable_peer_stream,
            wearable_bridge_stream,
            relay_bridge_stream,
            relay_peer_stream,
        ):
            stream.close()
            stream.dispose_transport_buffers()

    transport_audits = (
        wearable_peer_stream.audit(),
        wearable_bridge_stream.audit(),
        relay_bridge_stream.audit(),
        relay_peer_stream.audit(),
    )
    result["end_to_end"] = {
        "sink_frames": sink_counts,
        "fake_serial_endpoint": "in_memory_ordered_byte_stream",
        "fake_relay_endpoint": "in_memory_ordered_byte_stream",
    }
    result["buffer_lifecycle"] = {
        "media_buffer_count": len(payload_refs),
        "all_runtime_media_buffers_zeroized": all(
            _all_zero(item) for item in payload_refs
        ),
        "all_fake_transport_buffers_zeroized": all(
            item["owned_buffers_zeroized"] and item["pending_bytes"] == 0
            for item in transport_audits
        ),
        "external_copy_control": "not_enforced",
    }
    result["scenario"] = scenario
    _assert_metadata_only(result)
    return result


@dataclass(frozen=True)
class TlsRelayConfig:
    """Inputs for an explicitly source-bound future TLS relay connection."""

    relay_host: str
    relay_port: int
    server_hostname: str
    source_ipv4: str
    interface_name: str
    ca_file: Path
    token_env_var: str | None = None
    token_file: Path | None = None
    client_cert_file: Path | None = None
    client_key_file: Path | None = None
    connect_timeout_seconds: int = 8

    def validate(self) -> None:
        if not isinstance(self.relay_host, str) or not self.relay_host.strip():
            raise MediaIoError("relay host must be configured")
        if not isinstance(self.server_hostname, str) or not self.server_hostname.strip():
            raise MediaIoError("TLS server hostname must be configured")
        _bounded_int(self.relay_port, label="relay_port", minimum=1, maximum=65535)
        _bounded_int(
            self.connect_timeout_seconds,
            label="connect_timeout_seconds",
            minimum=1,
            maximum=30,
        )
        try:
            address = ipaddress.IPv4Address(self.source_ipv4)
        except ipaddress.AddressValueError as error:
            raise MediaIoError("source_ipv4 must be an explicit IPv4 address") from error
        if address.is_unspecified or address.is_multicast or address.is_loopback:
            raise MediaIoError("source_ipv4 must identify the intended non-loopback interface")
        if (
            not isinstance(self.interface_name, str)
            or not self.interface_name.strip()
            or len(self.interface_name) > 128
            or any(ord(char) < 32 for char in self.interface_name)
        ):
            raise MediaIoError("interface_name must explicitly identify the intended adapter")
        if (self.token_env_var is None) == (self.token_file is None):
            raise MediaIoError("configure exactly one token source: environment or file")
        if self.token_env_var is not None:
            _identifier(self.token_env_var, label="token_env_var")
        if (self.client_cert_file is None) != (self.client_key_file is None):
            raise MediaIoError("client certificate and key must be configured together")
        required_files = [self.ca_file]
        if self.token_file is not None:
            required_files.append(self.token_file)
        if self.client_cert_file is not None:
            required_files.extend((self.client_cert_file, self.client_key_file))
        for path in required_files:
            if not isinstance(path, Path) or not path.is_file():
                raise MediaIoError("a required TLS/auth input file is unavailable")


def _load_token(
    config: TlsRelayConfig,
    *,
    environ: Mapping[str, str] | None = None,
) -> bytearray:
    source = os.environ if environ is None else environ
    token = bytearray()
    if config.token_env_var is not None:
        raw = source.get(config.token_env_var)
        if raw is None:
            raise MediaIoError("configured token environment variable is unavailable")
        if len(raw) > MAX_TOKEN_BYTES:
            raise MediaIoError("relay token length/content is invalid")
        token = bytearray(raw, "utf-8")
    else:
        try:
            with config.token_file.open("rb") as token_stream:  # type: ignore[union-attr]
                file_size = os.fstat(token_stream.fileno()).st_size
                if not 1 <= file_size <= MAX_TOKEN_BYTES + 1:
                    raise MediaIoError("relay token length/content is invalid")
                token = bytearray(file_size)
                token_view = memoryview(token)
                read_count = 0
                try:
                    while read_count < file_size:
                        count = token_stream.readinto(token_view[read_count:])
                        if not count:
                            raise MediaIoError("configured token file is incomplete")
                        read_count += count
                finally:
                    token_view.release()
        except MediaIoError:
            _zero(token)
            raise
        except OSError as error:
            _zero(token)
            raise MediaIoError("configured token file cannot be read") from error
    while token and token[-1] in b"\r\n":
        token.pop()
    if not token or len(token) > MAX_TOKEN_BYTES or b"\x00" in token:
        _zero(token)
        raise MediaIoError("relay token length/content is invalid")
    return token


def offline_tls_preflight(
    config: TlsRelayConfig,
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Validate local inputs only; deliberately perform no DNS/socket/traffic."""

    config.validate()
    token = _load_token(config, environ=environ)
    try:
        auth_source = "environment" if config.token_env_var is not None else "file"
    finally:
        _zero(token)
    result = {
        "io_version": IO_VERSION,
        "preflight_result": "BLOCKED_PENDING_AUTHORIZED_EGRESS_PROBE",
        "source_binding": {
            "interface_name": config.interface_name,
            "source_ipv4": config.source_ipv4,
            "socket_bind_required_before_connect": True,
            "connector_binding_mechanism": "source_ipv4_only",
            "interface_name_to_ipv4_os_mapping": "unverified_offline",
        },
        "tls": {
            "minimum_version": "TLSv1.2",
            "server_hostname_verification_required": True,
            "ca_file_configured": True,
            "mutual_tls_configured": config.client_cert_file is not None,
        },
        "authentication": {
            "source": auth_source,
            "loaded_for_validation": True,
            "value_or_source_name_exposed": False,
            "runtime_copy_zeroized": True,
            "external_environment_or_file_copy_control": "not_enforced",
        },
        "execution": {
            "operator_authorized": False,
            "dns_performed": False,
            "socket_opened": False,
            "outbound_traffic_sent": False,
        },
        "data_plane": {
            "os_rndis_enumeration": "observed_in_separate_evidence",
            "prior_explicit_source_bound_external_probe": "timed_out",
            "current_lte_pdp_egress": "unverified",
            "fail_closed_until_tls_handshake_and_auth_ack": True,
        },
        "claims": {
            "local_configuration": "validated",
            "lte_egress": "NOT_RUN",
            "tls_relay": "NOT_RUN",
            "media": "NOT_RUN",
            "p0_call": "NOT_RUN",
        },
    }
    _assert_metadata_only(result)
    return result


class SocketByteStream:
    """Ordered TLS socket adapter returned only by an authorized connector."""

    def __init__(self, tls_socket: ssl.SSLSocket):
        self._socket = tls_socket

    def read_exact(self, size: int, *, timeout_steps: int) -> bytearray:
        _bounded_int(size, label="read size", minimum=1, maximum=4096)
        _bounded_int(timeout_steps, label="timeout_steps", minimum=1, maximum=1000)
        result = bytearray(size)
        view = memoryview(result)
        offset = 0
        try:
            while offset < size:
                count = self._socket.recv_into(view[offset:], size - offset)
                if not count:
                    raise MediaIoError("TLS relay closed during bounded read")
                offset += count
            return result
        except socket.timeout as error:
            _zero(result)
            raise MediaIoTimeout(
                "TLS relay bounded read timed out", retry_safe=False
            ) from error
        except Exception:
            _zero(result)
            raise
        finally:
            view.release()

    def write_all(self, data: memoryview, *, timeout_steps: int) -> None:
        _bounded_int(timeout_steps, label="timeout_steps", minimum=1, maximum=1000)
        try:
            self._socket.sendall(data)
        except socket.timeout as error:
            raise MediaIoTimeout(
                "TLS relay bounded write timed out", retry_safe=False
            ) from error

    def close(self) -> None:
        self._socket.close()


class AuthorizedTlsRelayConnector:
    """Stdlib TLS client boundary; caller must separately authorize real traffic.

    The connector binds ``source_ipv4`` before connect.  ``interface_name`` is
    an operator/audit identity only; this portable stdlib seam does not prove
    that the operating system currently maps that name to the configured IP.
    That mapping and actual egress must be checked by an authorized real-run
    preflight.
    """

    @staticmethod
    def connect(
        config: TlsRelayConfig,
        *,
        operator_authorized: bool = False,
        environ: Mapping[str, str] | None = None,
    ) -> SocketByteStream:
        if operator_authorized is not True:
            raise MediaIoError("real TLS connection requires explicit operator authorization")
        config.validate()
        token = _load_token(config, environ=environ)
        raw_socket: socket.socket | None = None
        tls_socket: ssl.SSLSocket | None = None
        auth_wire: bytearray | None = None
        ack: bytearray | None = None
        try:
            context = ssl.create_default_context(cafile=str(config.ca_file))
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.check_hostname = True
            context.verify_mode = ssl.CERT_REQUIRED
            if config.client_cert_file is not None:
                context.load_cert_chain(
                    certfile=str(config.client_cert_file),
                    keyfile=str(config.client_key_file),
                )
            raw_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            raw_socket.settimeout(config.connect_timeout_seconds)
            raw_socket.bind((config.source_ipv4, 0))
            raw_socket.connect((config.relay_host, config.relay_port))
            tls_socket = context.wrap_socket(
                raw_socket, server_hostname=config.server_hostname
            )
            raw_socket = None
            auth_wire = bytearray(
                _AUTH_HEADER.pack(AUTH_MAGIC, WIRE_VERSION, len(token))
            )
            auth_wire.extend(token)
            tls_socket.sendall(auth_wire)
            ack = bytearray()
            while len(ack) < len(AUTH_ACK):
                chunk = tls_socket.recv(len(AUTH_ACK) - len(ack))
                if not chunk:
                    raise MediaIoError("TLS relay closed before authentication acknowledgement")
                ack.extend(chunk)
            if bytes(ack) != AUTH_ACK:
                raise MediaIoProtocolError("TLS relay authentication acknowledgement invalid")
            return SocketByteStream(tls_socket)
        except Exception:
            if tls_socket is not None:
                tls_socket.close()
            elif raw_socket is not None:
                raw_socket.close()
            raise
        finally:
            _zero(token)
            if auth_wire is not None:
                _zero(auth_wire)
            if ack is not None:
                _zero(ack)


def _cli_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    """Strip trace/session identifiers while retaining operational metadata."""

    return {
        "io_version": result["io_version"],
        "result": result["result"],
        "scenario": result["scenario"],
        "profile": result["profile"],
        "transport_boundary": result["transport_boundary"],
        "bounded_run": result["bounded_run"],
        "direction_stats": result["direction_stats"],
        "end_to_end": result["end_to_end"],
        "buffer_lifecycle": result["buffer_lifecycle"],
        "claims": result["claims"],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run CALL-020B local framing or offline TLS-input preflight; this CLI "
            "cannot open sockets, serial ports, audio devices, or hardware."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    loopback = subparsers.add_parser("loopback")
    loopback.add_argument("--frames", type=int, default=12)
    loopback.add_argument(
        "--scenario",
        choices=(
            "healthy",
            "one-way",
            "timeout-recovery",
            "timeout-failure",
            "backpressure",
        ),
        default="healthy",
    )
    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("--relay-host", required=True)
    preflight.add_argument("--relay-port", required=True, type=int)
    preflight.add_argument("--server-hostname", required=True)
    preflight.add_argument("--source-ipv4", required=True)
    preflight.add_argument("--interface-name", required=True)
    preflight.add_argument("--ca-file", required=True, type=Path)
    token_group = preflight.add_mutually_exclusive_group(required=True)
    token_group.add_argument("--token-env")
    token_group.add_argument("--token-file", type=Path)
    preflight.add_argument("--client-cert-file", type=Path)
    preflight.add_argument("--client-key-file", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "loopback":
            config = MediaIoConfig(frame_count=args.frames, max_cycles=max(2 * args.frames, 4))
            if args.scenario == "backpressure":
                config = MediaIoConfig(
                    frame_count=args.frames,
                    max_cycles=max(2 * args.frames, 4),
                    downlink_queue_capacity=1,
                    downlink_service_interval_cycles=4,
                )
            result = run_fake_duplex(config, scenario=args.scenario)
            output = _cli_summary(result)
            exit_code = 0 if result["result"] == "PASS" else 1
        else:
            config = TlsRelayConfig(
                relay_host=args.relay_host,
                relay_port=args.relay_port,
                server_hostname=args.server_hostname,
                source_ipv4=args.source_ipv4,
                interface_name=args.interface_name,
                ca_file=args.ca_file,
                token_env_var=args.token_env,
                token_file=args.token_file,
                client_cert_file=args.client_cert_file,
                client_key_file=args.client_key_file,
            )
            output = offline_tls_preflight(config)
            exit_code = 1
    except MediaIoError as error:
        parser.exit(2, f"CALL-020B rejected: {error}\n")
    print(json.dumps(output, indent=2, sort_keys=True, allow_nan=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

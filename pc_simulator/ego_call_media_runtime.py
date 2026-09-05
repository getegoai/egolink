"""Deterministic, process-local CALL-020A duplex media runtime seam.

The runtime deliberately stops at an in-process datagram boundary.  It moves
short-lived mutable PCM frames through independent bounded direction queues,
zeroes every accepted buffer after delivery or drop, and submits only packet
metadata to :func:`evaluate_media_trace`.  It cannot prevent a caller-provided
source or sink from making its own copy; adapters remain responsible for the
no-copy/no-persistence policy.  This module opens no serial port, socket,
network connection, audio device, or hardware interface.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from pc_simulator.ego_call_media_probe import MediaTraceError, evaluate_media_trace


RUNTIME_VERSION = "egolink.ego_call_media_runtime.v0.1"
TRACE_VERSION = "egolink.ego_call_media_trace.v0.1"
DIRECTIONS = ("uplink", "downlink")
FRAME_DURATION_NS = 20_000_000
MAX_FRAMES_PER_DIRECTION = 30_000  # ten minutes at 20 ms
MAX_TOTAL_TICKS = 40_000
_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]+$")

FrameFactory = Callable[[str, int, int], bytearray]
FrameSink = Callable[[str, int, bytearray], None]


class MediaRuntimeError(ValueError):
    """Raised when the local runtime cannot execute without inventing state."""


def _bounded_int(
    value: object, *, label: str, minimum: int, maximum: int
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or value > maximum
    ):
        raise MediaRuntimeError(
            f"{label} must be an integer in [{minimum}, {maximum}]"
        )
    return value


def _identifier(value: object, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 128
        or _ID_PATTERN.fullmatch(value) is None
    ):
        raise MediaRuntimeError(
            f"{label} must be 1-128 identifier characters [A-Za-z0-9._:-]"
        )
    return value


@dataclass(frozen=True)
class Pcm16EngineeringProfile:
    """The one explicit, temporary CALL-020A engineering media profile."""

    encoding: str = "PCM_S16LE"
    sample_rate_hz: int = 16_000
    channels: int = 1
    sample_width_bytes: int = 2
    frame_duration_ms: int = 20

    def validate(self) -> None:
        expected = ("PCM_S16LE", 16_000, 1, 2, 20)
        actual = (
            self.encoding,
            self.sample_rate_hz,
            self.channels,
            self.sample_width_bytes,
            self.frame_duration_ms,
        )
        numeric_values = (
            self.sample_rate_hz,
            self.channels,
            self.sample_width_bytes,
            self.frame_duration_ms,
        )
        if (
            not isinstance(self.encoding, str)
            or any(type(value) is not int for value in numeric_values)
            or actual != expected
        ):
            raise MediaRuntimeError(
                "profile must be PCM_S16LE/16000 Hz/mono/16-bit/20 ms"
            )

    @property
    def samples_per_frame(self) -> int:
        return self.sample_rate_hz * self.frame_duration_ms // 1000

    @property
    def frame_bytes(self) -> int:
        return self.samples_per_frame * self.channels * self.sample_width_bytes

    def metadata(self) -> dict[str, Any]:
        return {
            "encoding": self.encoding,
            "sample_rate_hz": self.sample_rate_hz,
            "channels": self.channels,
            "sample_width_bytes": self.sample_width_bytes,
            "frame_duration_ms": self.frame_duration_ms,
            "samples_per_frame": self.samples_per_frame,
            "frame_bytes": self.frame_bytes,
        }


@dataclass(frozen=True)
class ProcessLocalBoundary:
    """Explicitly non-production signaling, transport, and encryption boundary."""

    transport: str = "in_process_memory_datagram"
    signaling: str = "in_process_fixture"
    encryption: str = "not_applicable_process_local"
    network_io: bool = False
    credentials_present: bool = False
    production_media_requirement: str = "managed_rtc_encrypted"

    def validate(self) -> None:
        expected = (
            "in_process_memory_datagram",
            "in_process_fixture",
            "not_applicable_process_local",
            False,
            False,
            "managed_rtc_encrypted",
        )
        actual = (
            self.transport,
            self.signaling,
            self.encryption,
            self.network_io,
            self.credentials_present,
            self.production_media_requirement,
        )
        if (
            not all(
                isinstance(value, str)
                for value in (
                    self.transport,
                    self.signaling,
                    self.encryption,
                    self.production_media_requirement,
                )
            )
            or type(self.network_io) is not bool
            or type(self.credentials_present) is not bool
            or actual != expected
        ):
            raise MediaRuntimeError(
                "runtime boundary must remain process-local, credential-free, and "
                "must retain the managed encrypted RTC production requirement"
            )

    def metadata(self) -> dict[str, Any]:
        return {
            "transport": self.transport,
            "signaling": self.signaling,
            "encryption": self.encryption,
            "network_io": self.network_io,
            "credentials_present": self.credentials_present,
            "production_media_requirement": self.production_media_requirement,
            "external_adapter_copy_control": "not_enforced_by_runtime",
        }


@dataclass(frozen=True)
class DirectionQueueConfig:
    capacity_frames: int = 8
    service_interval_frames: int = 1
    service_batch_frames: int = 1

    def validate(self, *, label: str) -> None:
        capacity = _bounded_int(
            self.capacity_frames, label=f"{label}.capacity_frames", minimum=1, maximum=512
        )
        _bounded_int(
            self.service_interval_frames,
            label=f"{label}.service_interval_frames",
            minimum=1,
            maximum=1024,
        )
        batch = _bounded_int(
            self.service_batch_frames,
            label=f"{label}.service_batch_frames",
            minimum=1,
            maximum=512,
        )
        if batch > capacity:
            raise MediaRuntimeError(
                f"{label}.service_batch_frames must not exceed capacity_frames"
            )

    def metadata(self) -> dict[str, int]:
        return {
            "capacity_frames": self.capacity_frames,
            "service_interval_frames": self.service_interval_frames,
            "service_batch_frames": self.service_batch_frames,
        }


@dataclass(frozen=True)
class BlackoutFault:
    direction: str
    start_sequence: int
    end_sequence: int


@dataclass(frozen=True)
class DelayFault:
    direction: str
    sequence: int
    delay_frames: int


@dataclass(frozen=True)
class DeterministicFaultPlan:
    blackouts: tuple[BlackoutFault, ...] = ()
    delays: tuple[DelayFault, ...] = ()

    def validate(self, *, frame_count: int) -> None:
        covered: dict[str, set[int]] = {direction: set() for direction in DIRECTIONS}
        for index, blackout in enumerate(self.blackouts):
            if blackout.direction not in DIRECTIONS:
                raise MediaRuntimeError(f"blackouts[{index}].direction is invalid")
            start = _bounded_int(
                blackout.start_sequence,
                label=f"blackouts[{index}].start_sequence",
                minimum=0,
                maximum=frame_count - 1,
            )
            end = _bounded_int(
                blackout.end_sequence,
                label=f"blackouts[{index}].end_sequence",
                minimum=start,
                maximum=frame_count - 1,
            )
            window = set(range(start, end + 1))
            if covered[blackout.direction] & window:
                raise MediaRuntimeError("blackout windows must not overlap")
            covered[blackout.direction].update(window)

        delayed: set[tuple[str, int]] = set()
        for index, delay in enumerate(self.delays):
            if delay.direction not in DIRECTIONS:
                raise MediaRuntimeError(f"delays[{index}].direction is invalid")
            sequence = _bounded_int(
                delay.sequence,
                label=f"delays[{index}].sequence",
                minimum=0,
                maximum=frame_count - 1,
            )
            _bounded_int(
                delay.delay_frames,
                label=f"delays[{index}].delay_frames",
                minimum=1,
                maximum=10_000,
            )
            key = (delay.direction, sequence)
            if key in delayed:
                raise MediaRuntimeError("each direction/sequence may have one delay")
            if sequence in covered[delay.direction]:
                raise MediaRuntimeError("a frame cannot be both delayed and blacked out")
            delayed.add(key)

    def blackout_sequences(self) -> dict[str, set[int]]:
        result = {direction: set() for direction in DIRECTIONS}
        for blackout in self.blackouts:
            result[blackout.direction].update(
                range(blackout.start_sequence, blackout.end_sequence + 1)
            )
        return result

    def delay_frames(self) -> dict[tuple[str, int], int]:
        return {
            (delay.direction, delay.sequence): delay.delay_frames
            for delay in self.delays
        }

    def metadata(self) -> dict[str, Any]:
        return {
            "blackouts": [
                {
                    "direction": item.direction,
                    "start_sequence": item.start_sequence,
                    "end_sequence": item.end_sequence,
                }
                for item in sorted(
                    self.blackouts,
                    key=lambda item: (
                        item.direction,
                        item.start_sequence,
                        item.end_sequence,
                    ),
                )
            ],
            "delays": [
                {
                    "direction": item.direction,
                    "sequence": item.sequence,
                    "delay_frames": item.delay_frames,
                }
                for item in sorted(
                    self.delays,
                    key=lambda item: (item.direction, item.sequence),
                )
            ],
        }


@dataclass(frozen=True)
class EvaluationBudget:
    minimum_packets_per_direction_for_connected: int = 2
    duplex_window_ns: int = 40_000_000
    setup_timeout_ns: int = 100_000_000
    max_loss_ratio: float = 0.0
    max_jitter_ns: int = 100_000_000
    max_gap_ns: int = 120_000_000
    blackout_threshold_ns: int = 60_000_000
    max_recovery_ns: int = 60_000_000

    def trace_config(self, *, frame_count: int) -> dict[str, Any]:
        minimum = _bounded_int(
            self.minimum_packets_per_direction_for_connected,
            label="evaluation.minimum_packets_per_direction_for_connected",
            minimum=1,
            maximum=frame_count,
        )
        duplex = _bounded_int(
            self.duplex_window_ns,
            label="evaluation.duplex_window_ns",
            minimum=1,
            maximum=10_000_000_000,
        )
        setup = _bounded_int(
            self.setup_timeout_ns,
            label="evaluation.setup_timeout_ns",
            minimum=1,
            maximum=600_000_000_000,
        )
        if (
            isinstance(self.max_loss_ratio, bool)
            or not isinstance(self.max_loss_ratio, (int, float))
            or not math.isfinite(float(self.max_loss_ratio))
            or not 0.0 <= float(self.max_loss_ratio) <= 1.0
        ):
            raise MediaRuntimeError("evaluation.max_loss_ratio must be finite in [0, 1]")
        jitter = _bounded_int(
            self.max_jitter_ns,
            label="evaluation.max_jitter_ns",
            minimum=0,
            maximum=600_000_000_000,
        )
        gap = _bounded_int(
            self.max_gap_ns,
            label="evaluation.max_gap_ns",
            minimum=1,
            maximum=600_000_000_000,
        )
        blackout = _bounded_int(
            self.blackout_threshold_ns,
            label="evaluation.blackout_threshold_ns",
            minimum=1,
            maximum=600_000_000_000,
        )
        recovery = _bounded_int(
            self.max_recovery_ns,
            label="evaluation.max_recovery_ns",
            minimum=0,
            maximum=600_000_000_000,
        )
        if gap < blackout:
            raise MediaRuntimeError("evaluation.max_gap_ns must cover blackout threshold")
        if duplex > blackout:
            raise MediaRuntimeError(
                "evaluation.duplex_window_ns must not exceed blackout threshold"
            )
        return {
            "expected_packet_count": {
                "uplink": frame_count,
                "downlink": frame_count,
            },
            "nominal_packet_interval_ns": FRAME_DURATION_NS,
            "minimum_packets_per_direction_for_connected": minimum,
            "duplex_window_ns": duplex,
            "setup_timeout_ns": setup,
            "max_loss_ratio": float(self.max_loss_ratio),
            "max_jitter_ns": jitter,
            "max_gap_ns": gap,
            "blackout_threshold_ns": blackout,
            "max_recovery_ns": recovery,
        }


@dataclass(frozen=True)
class MediaRuntimeConfig:
    session_id: str = "call020a-local-session-001"
    trace_id: str = "call020a-local-trace-001"
    device_id: str = "device-fixture-001"
    guardian_id: str = "guardian-fixture-001"
    uplink_source_clock_id: str = "device-clock-boot-001"
    downlink_source_clock_id: str = "guardian-clock-boot-001"
    bridge_clock_id: str = "pc-bridge-clock-boot-001"
    frame_count: int = 12
    flush_frame_budget: int = 16
    profile: Pcm16EngineeringProfile = field(
        default_factory=Pcm16EngineeringProfile
    )
    boundary: ProcessLocalBoundary = field(default_factory=ProcessLocalBoundary)
    uplink_queue: DirectionQueueConfig = field(default_factory=DirectionQueueConfig)
    downlink_queue: DirectionQueueConfig = field(default_factory=DirectionQueueConfig)
    evaluation: EvaluationBudget = field(default_factory=EvaluationBudget)
    faults: DeterministicFaultPlan = field(default_factory=DeterministicFaultPlan)

    def validate(self) -> dict[str, Any]:
        for label in (
            "session_id",
            "trace_id",
            "device_id",
            "guardian_id",
            "uplink_source_clock_id",
            "downlink_source_clock_id",
            "bridge_clock_id",
        ):
            _identifier(getattr(self, label), label=label)
        if self.device_id == self.guardian_id:
            raise MediaRuntimeError("device_id and guardian_id must be distinct")
        clocks = {
            self.uplink_source_clock_id,
            self.downlink_source_clock_id,
            self.bridge_clock_id,
        }
        if len(clocks) != 3:
            raise MediaRuntimeError("direction source clocks and bridge clock must differ")
        frame_count = _bounded_int(
            self.frame_count,
            label="frame_count",
            minimum=2,
            maximum=MAX_FRAMES_PER_DIRECTION,
        )
        flush = _bounded_int(
            self.flush_frame_budget,
            label="flush_frame_budget",
            minimum=0,
            maximum=10_000,
        )
        if frame_count + flush > MAX_TOTAL_TICKS:
            raise MediaRuntimeError("frame_count plus flush budget exceeds runtime bound")
        self.profile.validate()
        if self.profile.frame_bytes != 640:
            raise MediaRuntimeError("engineering profile must produce exactly 640 bytes")
        self.boundary.validate()
        self.uplink_queue.validate(label="uplink_queue")
        self.downlink_queue.validate(label="downlink_queue")
        self.faults.validate(frame_count=frame_count)
        return self.evaluation.trace_config(frame_count=frame_count)


@dataclass(slots=True)
class _QueuedFrame:
    direction: str
    sequence: int
    source_time_ns: int
    enqueued_tick: int
    due_tick: int
    payload: bytearray


def _default_frame_factory(direction: str, sequence: int, frame_bytes: int) -> bytearray:
    seed = (sequence * 29 + (17 if direction == "uplink" else 149)) & 0xFF
    return bytearray([seed or 1]) * frame_bytes


def _zeroize(payload: bytearray) -> None:
    payload[:] = b"\x00" * len(payload)


def _assert_metadata_only(value: object, *, path: str = "result") -> None:
    if isinstance(value, (bytes, bytearray, memoryview)):
        raise MediaRuntimeError(f"binary media escaped into {path}")
    if isinstance(value, dict):
        for key, item in value.items():
            _assert_metadata_only(item, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _assert_metadata_only(item, path=f"{path}[{index}]")


class InProcessDuplexMediaRuntime:
    """Execute one bounded deterministic full-duplex process-local run.

    ``frame_sink`` borrows each mutable frame only for the duration of the
    callback.  The runtime zeroes that same object in ``finally`` immediately
    after the callback returns or raises.  A retained callback reference can
    therefore observe only zeros after delivery.  A callback can still make an
    independent copy; preventing or disposing such a copy is outside this seam
    and must be enforced by the real adapter.
    """

    def __init__(self, config: MediaRuntimeConfig):
        self._config = config

    def run(
        self,
        *,
        frame_factory: FrameFactory | None = None,
        frame_sink: FrameSink | None = None,
    ) -> dict[str, Any]:
        config = self._config
        trace_config = config.validate()
        factory = frame_factory or _default_frame_factory
        queues: dict[str, list[_QueuedFrame]] = {
            direction: [] for direction in DIRECTIONS
        }
        queue_configs = {
            "uplink": config.uplink_queue,
            "downlink": config.downlink_queue,
        }
        blackout_sequences = config.faults.blackout_sequences()
        delay_frames = config.faults.delay_frames()
        records: list[dict[str, Any]] = []
        buffer_stats = {
            "created_mutable_buffers": 0,
            "zeroized_after_delivery": 0,
            "zeroized_after_drop": 0,
            "zeroized_during_cleanup": 0,
            "outstanding_mutable_buffers": 0,
        }
        stats: dict[str, dict[str, Any]] = {
            direction: {
                **queue_configs[direction].metadata(),
                "frames_generated": 0,
                "frames_enqueued": 0,
                "frames_delivered": 0,
                "frames_dropped_blackout": 0,
                "frames_dropped_backpressure": 0,
                "frames_dropped_deadline": 0,
                "configured_delayed_frames": 0,
                "delivered_after_queue_delay": 0,
                "max_queue_delay_frames": 0,
                "reordered_delivery_count": 0,
                "peak_queue_depth": 0,
                "final_queue_depth": 0,
            }
            for direction in DIRECTIONS
        }
        highest_delivered = {direction: -1 for direction in DIRECTIONS}
        executed_ticks = 0

        def dispose(frame: _QueuedFrame, *, disposition: str) -> None:
            _zeroize(frame.payload)
            if disposition == "delivery":
                buffer_stats["zeroized_after_delivery"] += 1
            elif disposition == "cleanup":
                buffer_stats["zeroized_during_cleanup"] += 1
            else:
                buffer_stats["zeroized_after_drop"] += 1

        try:
            maximum_ticks = config.frame_count + config.flush_frame_budget
            for tick in range(maximum_ticks):
                executed_ticks = tick + 1
                if tick < config.frame_count:
                    for direction in DIRECTIONS:
                        payload = factory(direction, tick, config.profile.frame_bytes)
                        if not isinstance(payload, bytearray):
                            raise MediaRuntimeError(
                                "frame_factory must return a mutable bytearray"
                            )
                        buffer_stats["created_mutable_buffers"] += 1
                        if len(payload) != config.profile.frame_bytes:
                            _zeroize(payload)
                            buffer_stats["zeroized_after_drop"] += 1
                            raise MediaRuntimeError(
                                "frame_factory returned a frame with the wrong byte length"
                            )
                        frame = _QueuedFrame(
                            direction=direction,
                            sequence=tick,
                            source_time_ns=tick * FRAME_DURATION_NS,
                            enqueued_tick=tick,
                            due_tick=tick + delay_frames.get((direction, tick), 0),
                            payload=payload,
                        )
                        direction_stats = stats[direction]
                        direction_stats["frames_generated"] += 1
                        if tick in blackout_sequences[direction]:
                            direction_stats["frames_dropped_blackout"] += 1
                            dispose(frame, disposition="blackout")
                            continue
                        if (direction, tick) in delay_frames:
                            direction_stats["configured_delayed_frames"] += 1
                        if len(queues[direction]) >= queue_configs[direction].capacity_frames:
                            direction_stats["frames_dropped_backpressure"] += 1
                            dispose(frame, disposition="backpressure")
                            continue
                        queues[direction].append(frame)
                        direction_stats["frames_enqueued"] += 1
                        direction_stats["peak_queue_depth"] = max(
                            direction_stats["peak_queue_depth"], len(queues[direction])
                        )

                bridge_slot = 0
                for direction in DIRECTIONS:
                    queue_config = queue_configs[direction]
                    if tick % queue_config.service_interval_frames != 0:
                        continue
                    eligible = sorted(
                        (
                            frame
                            for frame in queues[direction]
                            if frame.due_tick <= tick
                        ),
                        key=lambda frame: (frame.due_tick, frame.enqueued_tick),
                    )[: queue_config.service_batch_frames]
                    for frame in eligible:
                        queues[direction].remove(frame)
                        bridge_slot += 1
                        trace_time_ns = tick * FRAME_DURATION_NS + 1_000_000 + bridge_slot
                        direction_stats = stats[direction]
                        queue_delay = tick - frame.enqueued_tick
                        if queue_delay:
                            direction_stats["delivered_after_queue_delay"] += 1
                        direction_stats["max_queue_delay_frames"] = max(
                            direction_stats["max_queue_delay_frames"], queue_delay
                        )
                        if frame.sequence < highest_delivered[direction]:
                            direction_stats["reordered_delivery_count"] += 1
                        highest_delivered[direction] = max(
                            highest_delivered[direction], frame.sequence
                        )
                        try:
                            if frame_sink is not None:
                                frame_sink(direction, frame.sequence, frame.payload)
                            records.append(
                                {
                                    "observation_id": (
                                        f"{config.trace_id}:{direction}:"
                                        f"{frame.sequence}:delivery"
                                    ),
                                    "packet_id": (
                                        f"{config.session_id}:{direction}:{frame.sequence}"
                                    ),
                                    "session_id": config.session_id,
                                    "direction": direction,
                                    "source_role": (
                                        "device" if direction == "uplink" else "guardian"
                                    ),
                                    "source_id": (
                                        config.device_id
                                        if direction == "uplink"
                                        else config.guardian_id
                                    ),
                                    "target_role": (
                                        "guardian" if direction == "uplink" else "device"
                                    ),
                                    "target_id": (
                                        config.guardian_id
                                        if direction == "uplink"
                                        else config.device_id
                                    ),
                                    "sequence": frame.sequence,
                                    "source_clock_id": (
                                        config.uplink_source_clock_id
                                        if direction == "uplink"
                                        else config.downlink_source_clock_id
                                    ),
                                    "source_time_ns": frame.source_time_ns,
                                    "trace_clock_id": config.bridge_clock_id,
                                    "trace_time_ns": trace_time_ns,
                                    "encoded_size_bytes": config.profile.frame_bytes,
                                }
                            )
                            direction_stats["frames_delivered"] += 1
                        finally:
                            dispose(frame, disposition="delivery")

                if tick >= config.frame_count - 1 and not any(queues.values()):
                    break

            for direction in DIRECTIONS:
                for frame in queues[direction]:
                    stats[direction]["frames_dropped_deadline"] += 1
                    dispose(frame, disposition="deadline")
                queues[direction].clear()
        finally:
            for direction in DIRECTIONS:
                for frame in queues[direction]:
                    dispose(frame, disposition="cleanup")
                queues[direction].clear()

        zeroized = (
            buffer_stats["zeroized_after_delivery"]
            + buffer_stats["zeroized_after_drop"]
            + buffer_stats["zeroized_during_cleanup"]
        )
        buffer_stats["outstanding_mutable_buffers"] = (
            buffer_stats["created_mutable_buffers"] - zeroized
        )
        if buffer_stats["outstanding_mutable_buffers"] != 0:
            raise MediaRuntimeError("mutable frame buffer accounting did not close")

        for direction in DIRECTIONS:
            stats[direction]["final_queue_depth"] = 0
            stats[direction]["frames_dropped_total"] = (
                stats[direction]["frames_dropped_blackout"]
                + stats[direction]["frames_dropped_backpressure"]
                + stats[direction]["frames_dropped_deadline"]
            )

        trace_end_time_ns = max(1, executed_ticks) * FRAME_DURATION_NS
        metadata_trace = {
            "trace_version": TRACE_VERSION,
            "trace_id": config.trace_id,
            "session_id": config.session_id,
            "trace_clock_id": config.bridge_clock_id,
            "trace_start_time_ns": 0,
            "trace_end_time_ns": trace_end_time_ns,
            "endpoints": {
                "device_id": config.device_id,
                "guardian_id": config.guardian_id,
            },
            "source_clock_ids": {
                "uplink": config.uplink_source_clock_id,
                "downlink": config.downlink_source_clock_id,
            },
            "config": trace_config,
            "records": records,
        }
        try:
            evaluation = evaluate_media_trace(metadata_trace)
        except MediaTraceError as error:
            raise MediaRuntimeError(f"generated metadata trace was rejected: {error}") from error

        result = {
            "runtime_version": RUNTIME_VERSION,
            "runtime_result": evaluation["evaluation_result"],
            "session_id": config.session_id,
            "trace_id": config.trace_id,
            "profile": config.profile.metadata(),
            "boundary": config.boundary.metadata(),
            "clock_lineage": {
                "bridge_clock_id": config.bridge_clock_id,
                "source_clock_ids": {
                    "uplink": config.uplink_source_clock_id,
                    "downlink": config.downlink_source_clock_id,
                },
                "source_frame_interval_ns": FRAME_DURATION_NS,
                "bridge_timestamps_strictly_monotonic": all(
                    previous["trace_time_ns"] < current["trace_time_ns"]
                    for previous, current in zip(records, records[1:])
                ),
            },
            "bounded_run": {
                "requested_frames_per_direction": config.frame_count,
                "flush_frame_budget": config.flush_frame_budget,
                "maximum_ticks": config.frame_count + config.flush_frame_budget,
                "executed_ticks": executed_ticks,
                "metadata_records_submitted": len(records),
                "raw_audio_persisted": False,
                "raw_audio_logged": False,
                "socket_network_hardware_used": False,
            },
            "fault_plan": config.faults.metadata(),
            "direction_runtime_stats": stats,
            "buffer_lifecycle": buffer_stats,
            "evaluation": evaluation,
            "claims": {
                "process_local_runtime": "verified",
                "audio_content_retained": False,
                "device_audio": "unverified",
                "sim_lte_media": "unverified",
                "vps_rtc": "unverified",
                "production_rtc_provider": "not_selected",
                "p0_call": "NOT_RUN",
            },
        }
        _assert_metadata_only(result)
        return result


def run_media_runtime(
    config: MediaRuntimeConfig | None = None,
    *,
    frame_factory: FrameFactory | None = None,
    frame_sink: FrameSink | None = None,
) -> dict[str, Any]:
    """Convenience API for one deterministic bounded process-local run."""

    return InProcessDuplexMediaRuntime(config or MediaRuntimeConfig()).run(
        frame_factory=frame_factory,
        frame_sink=frame_sink,
    )


def _demo_config(scenario: str, frame_count: int) -> MediaRuntimeConfig:
    if scenario == "healthy":
        return MediaRuntimeConfig(frame_count=frame_count)
    if scenario == "one-way":
        return MediaRuntimeConfig(
            frame_count=frame_count,
            faults=DeterministicFaultPlan(
                blackouts=(BlackoutFault("downlink", 0, frame_count - 1),)
            ),
        )
    if frame_count < 12:
        raise MediaRuntimeError(f"{scenario} demo requires at least 12 frames")
    if scenario in {"blackout-recovery", "blackout-failure"}:
        return MediaRuntimeConfig(
            frame_count=frame_count,
            evaluation=EvaluationBudget(
                max_loss_ratio=0.5,
                max_recovery_ns=(40_000_000 if scenario == "blackout-recovery" else 20_000_000),
            ),
            faults=DeterministicFaultPlan(
                blackouts=(BlackoutFault("uplink", 4, 7),)
            ),
        )
    if scenario == "backpressure":
        return MediaRuntimeConfig(
            frame_count=frame_count,
            downlink_queue=DirectionQueueConfig(
                capacity_frames=2,
                service_interval_frames=4,
                service_batch_frames=1,
            ),
        )
    raise MediaRuntimeError(f"unknown demo scenario {scenario!r}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run a bounded process-local CALL-020A PCM frame simulation and emit "
            "metadata-only JSON; no audio, socket, network, or hardware I/O."
        )
    )
    parser.add_argument("--frames", type=int, default=12)
    parser.add_argument(
        "--scenario",
        choices=(
            "healthy",
            "one-way",
            "blackout-recovery",
            "blackout-failure",
            "backpressure",
        ),
        default="healthy",
    )
    args = parser.parse_args(argv)
    try:
        result = run_media_runtime(_demo_config(args.scenario, args.frames))
    except MediaRuntimeError as error:
        parser.exit(2, f"media runtime rejected: {error}\n")
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0 if result["runtime_result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

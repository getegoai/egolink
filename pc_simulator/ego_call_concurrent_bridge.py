"""CALL-020C bounded concurrent media-bridge structure.

This module advances only the process-local PC-bridge structure.  It runs one
reader and one writer worker per media direction, with an independent bounded
queue for each direction and absolute 20 ms monotonic scheduling.  It accepts
the strict :class:`~pc_simulator.ego_call_media_io.FramedEndpoint` boundary
implemented by CALL-020B; it does not open a socket, serial port, audio device,
network connection, or hardware interface itself.

Every mutable media frame returned by an endpoint is owned by this bridge
until it is handed to the outbound ``FramedEndpoint``.  The bridge zeroes the
same buffer on forwarding, rejection, deadline failure, cancellation, worker
failure, and coordinator cleanup.  Endpoint/OS/TLS implementations can still
make independent copies and remain responsible for their own disposal policy.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from pc_simulator.ego_call_media_io import (
    FRAME_BYTES,
    EndpointIdentity,
    FramedEndpoint,
    MediaFrame,
    MediaIoConfig,
    MediaIoError,
    MediaIoProtocolError,
)
from pc_simulator.ego_call_media_probe import MediaTraceError, evaluate_media_trace
from pc_simulator.ego_call_media_runtime import (
    EvaluationBudget,
    FRAME_DURATION_NS,
    Pcm16EngineeringProfile,
)


BRIDGE_VERSION = "egolink.ego_call_concurrent_bridge.v0.1"
_DIRECTIONS = ("uplink", "downlink")
_WORKER_COUNT = 4


class ConcurrentBridgeError(MediaIoError):
    """Base error for a rejected or failed CALL-020C bridge run."""


class ConcurrentBridgeBackpressure(ConcurrentBridgeError):
    """A direction queue filled before its writer could make progress."""


class ConcurrentBridgeDeadline(ConcurrentBridgeError):
    """A frame missed its absolute monotonic forwarding deadline."""


class ConcurrentBridgeRunFailed(ConcurrentBridgeError):
    """A bounded concurrent run failed and retained only failure metadata."""

    def __init__(self, message: str, *, metadata: Mapping[str, Any]):
        super().__init__(message)
        self.metadata = dict(metadata)


class BridgeClock(Protocol):
    """Injectable monotonic clock used for schedule and deadline decisions."""

    def monotonic_ns(self) -> int: ...

    def wait_until(self, target_ns: int, stop_event: threading.Event) -> bool: ...


class SystemMonotonicClock:
    """Production-shaped clock backed only by ``time.monotonic_ns``."""

    def monotonic_ns(self) -> int:
        return time.monotonic_ns()

    def wait_until(self, target_ns: int, stop_event: threading.Event) -> bool:
        while not stop_event.is_set():
            remaining_ns = target_ns - time.monotonic_ns()
            if remaining_ns <= 0:
                return True
            if stop_event.wait(remaining_ns / 1_000_000_000):
                return False
        return False


def _bounded_int(
    value: object, *, label: str, minimum: int, maximum: int
) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ConcurrentBridgeError(
            f"{label} must be an integer in [{minimum}, {maximum}]"
        )
    return value


def _assert_metadata_only(value: object, *, path: str = "result") -> None:
    if isinstance(value, (bytes, bytearray, memoryview)):
        raise ConcurrentBridgeError(f"binary media escaped into {path}")
    if isinstance(value, Mapping):
        for key, item in value.items():
            _assert_metadata_only(item, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _assert_metadata_only(item, path=f"{path}[{index}]")


@dataclass(frozen=True)
class ConcurrentBridgeConfig:
    """Bounded scheduling and ownership policy for one offline bridge run."""

    identity: EndpointIdentity = field(
        default_factory=lambda: MediaIoConfig().identity
    )
    bridge_clock_id: str = "pc-concurrent-bridge-clock-001"
    frame_count: int = 12
    uplink_queue_capacity: int = 8
    downlink_queue_capacity: int = 8
    timeout_steps: int = 1
    receive_attempts: int = 2
    send_attempts: int = 2
    startup_grace_ns: int = FRAME_DURATION_NS
    frame_deadline_ns: int = 100_000_000
    max_runtime_ms: int = 5_000
    join_timeout_ms: int = 1_000
    profile: Pcm16EngineeringProfile = field(
        default_factory=Pcm16EngineeringProfile
    )
    evaluation: EvaluationBudget = field(default_factory=EvaluationBudget)

    def validate(self) -> dict[str, Any]:
        self.identity.validate()
        if (
            not isinstance(self.bridge_clock_id, str)
            or not self.bridge_clock_id
            or len(self.bridge_clock_id) > 128
        ):
            raise ConcurrentBridgeError(
                "bridge_clock_id must be a non-empty string of at most 128 characters"
            )
        frame_count = _bounded_int(
            self.frame_count, label="frame_count", minimum=2, maximum=30_000
        )
        for label in ("uplink_queue_capacity", "downlink_queue_capacity"):
            _bounded_int(
                getattr(self, label), label=label, minimum=1, maximum=512
            )
        _bounded_int(
            self.timeout_steps, label="timeout_steps", minimum=1, maximum=1_000
        )
        _bounded_int(
            self.receive_attempts,
            label="receive_attempts",
            minimum=1,
            maximum=16,
        )
        _bounded_int(
            self.send_attempts, label="send_attempts", minimum=1, maximum=16
        )
        startup_grace_ns = _bounded_int(
            self.startup_grace_ns,
            label="startup_grace_ns",
            minimum=0,
            maximum=1_000_000_000,
        )
        frame_deadline_ns = _bounded_int(
            self.frame_deadline_ns,
            label="frame_deadline_ns",
            minimum=1_000_000,
            maximum=5_000_000_000,
        )
        max_runtime_ms = _bounded_int(
            self.max_runtime_ms,
            label="max_runtime_ms",
            minimum=50,
            maximum=600_000,
        )
        _bounded_int(
            self.join_timeout_ms,
            label="join_timeout_ms",
            minimum=10,
            maximum=10_000,
        )
        minimum_schedule_ns = (
            startup_grace_ns + (frame_count - 1) * FRAME_DURATION_NS
        )
        if max_runtime_ms * 1_000_000 <= minimum_schedule_ns:
            raise ConcurrentBridgeError(
                "max_runtime_ms must exceed the absolute 20 ms frame schedule"
            )
        self.profile.validate()
        if self.profile.frame_bytes != FRAME_BYTES:
            raise ConcurrentBridgeError(
                "CALL-020C profile must remain 640-byte PCM S16LE frames"
            )
        # Validation also proves the evaluator can represent the declared run.
        trace_config = self.evaluation.trace_config(frame_count=frame_count)
        if trace_config["nominal_packet_interval_ns"] != FRAME_DURATION_NS:
            raise ConcurrentBridgeError("CALL-020C cadence must remain exactly 20 ms")
        if frame_deadline_ns >= max_runtime_ms * 1_000_000:
            raise ConcurrentBridgeError(
                "frame_deadline_ns must be smaller than the total runtime bound"
            )
        return trace_config


@dataclass(frozen=True)
class _WorkerFailure:
    direction: str
    stage: str
    cause: Exception


class _DirectionQueue:
    """Small condition-backed queue that wakes immediately on stop."""

    def __init__(self, capacity: int):
        self._capacity = capacity
        self._frames: deque[MediaFrame] = deque()
        self._condition = threading.Condition()

    def put_nowait(self, frame: MediaFrame) -> tuple[bool, int]:
        with self._condition:
            if len(self._frames) >= self._capacity:
                return False, len(self._frames)
            self._frames.append(frame)
            depth = len(self._frames)
            self._condition.notify()
            return True, depth

    def get(
        self,
        *,
        stop_event: threading.Event,
        reader_done: threading.Event,
    ) -> MediaFrame | None:
        with self._condition:
            while (
                not self._frames
                and not stop_event.is_set()
                and not reader_done.is_set()
            ):
                self._condition.wait()
            if stop_event.is_set() or not self._frames:
                return None
            return self._frames.popleft()

    def wake_all(self) -> None:
        with self._condition:
            self._condition.notify_all()

    def drain(self) -> list[MediaFrame]:
        with self._condition:
            result = list(self._frames)
            self._frames.clear()
            return result


class _BufferLedger:
    """Tracks each accepted mutable payload until its terminal disposition."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._owned: dict[int, bytearray] = {}
        self._accepted = 0
        self._dispositions: dict[str, int] = {
            "forwarded": 0,
            "backpressure": 0,
            "deadline": 0,
            "cancelled": 0,
            "worker_failure": 0,
            "coordinator_cleanup": 0,
        }

    def accept(self, frame: MediaFrame) -> None:
        payload = frame.media
        key = id(payload)
        with self._lock:
            if key in self._owned:
                raise ConcurrentBridgeError(
                    "one mutable media buffer cannot be owned twice concurrently"
                )
            self._owned[key] = payload
            self._accepted += 1

    def dispose(self, frame: MediaFrame, *, disposition: str) -> None:
        key = id(frame.media)
        frame.dispose()
        with self._lock:
            if self._owned.pop(key, None) is not None:
                self._dispositions[disposition] += 1

    def zero_all(self) -> None:
        with self._lock:
            buffers = list(self._owned.values())
            self._owned.clear()
            self._dispositions["coordinator_cleanup"] += len(buffers)
        for payload in buffers:
            payload[:] = b"\x00" * len(payload)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            outstanding = len(self._owned)
            dispositions = dict(self._dispositions)
            accepted = self._accepted
        disposed = sum(dispositions.values())
        return {
            "accepted_mutable_media_buffers": accepted,
            "zeroized_by_disposition": dispositions,
            "zeroized_mutable_media_buffers": disposed,
            "outstanding_mutable_media_buffers": outstanding,
            "all_accepted_mutable_media_zeroized": (
                outstanding == 0 and disposed == accepted
            ),
            "external_stream_os_tls_copy_control": "not_enforced",
        }


class _MonotonicRecorder:
    """Turns monotonic wall readings into unique relative trace timestamps."""

    def __init__(self, clock: BridgeClock, start_ns: int):
        self._clock = clock
        self._start_ns = start_ns
        self._lock = threading.Lock()
        self._last_relative_ns = 0
        self.collision_adjustments = 0

    def stamp(self) -> tuple[int, int]:
        raw_ns = self._clock.monotonic_ns()
        if type(raw_ns) is not int or raw_ns < self._start_ns:
            raise ConcurrentBridgeError("monotonic bridge clock regressed")
        with self._lock:
            relative_ns = raw_ns - self._start_ns
            if relative_ns <= self._last_relative_ns:
                relative_ns = self._last_relative_ns + 1
                self.collision_adjustments += 1
            self._last_relative_ns = relative_ns
        return raw_ns, relative_ns

    @property
    def last_relative_ns(self) -> int:
        with self._lock:
            return self._last_relative_ns


class ConcurrentDuplexMediaBridge:
    """Run four bounded workers without performing or constructing real I/O.

    ``wearable`` must receive uplink and send downlink. ``relay`` must receive
    downlink and send uplink.  Both must be the CALL-020B ``FramedEndpoint``
    type and bind the exact configured session identity.  Callers provide the
    streams; this class never opens one.

    ``request_stop`` is thread-safe.  The synchronous ``run`` method owns all
    worker joins and either returns a metadata-only result or raises
    :class:`ConcurrentBridgeRunFailed` with metadata and the original worker
    exception as ``__cause__``.
    """

    def __init__(
        self,
        config: ConcurrentBridgeConfig | None = None,
        *,
        clock: BridgeClock | None = None,
    ):
        self.config = config or ConcurrentBridgeConfig()
        self.clock = clock or SystemMonotonicClock()
        self._stop_event = threading.Event()
        self._terminal_event = threading.Event()
        self._state_lock = threading.Lock()
        self._queues: dict[str, _DirectionQueue] = {}
        self._external_stop_requested = False
        self._run_started = False

    def request_stop(self) -> None:
        with self._state_lock:
            self._external_stop_requested = True
            self._stop_event.set()
            queues = tuple(self._queues.values())
        for direction_queue in queues:
            direction_queue.wake_all()
        self._terminal_event.set()

    def _preflight(
        self, *, wearable: FramedEndpoint, relay: FramedEndpoint
    ) -> dict[str, Any]:
        trace_config = self.config.validate()
        if not isinstance(wearable, FramedEndpoint) or not isinstance(
            relay, FramedEndpoint
        ):
            raise MediaIoProtocolError(
                "CALL-020C requires existing strict FramedEndpoint instances"
            )
        if (
            wearable.inbound_direction != "uplink"
            or wearable.outbound_direction != "downlink"
        ):
            raise MediaIoProtocolError("wearable endpoint directions are invalid")
        if (
            relay.inbound_direction != "downlink"
            or relay.outbound_direction != "uplink"
        ):
            raise MediaIoProtocolError("relay endpoint directions are invalid")
        if (
            wearable.identity != self.config.identity
            or relay.identity != self.config.identity
        ):
            raise MediaIoProtocolError(
                "bridge endpoint identity must match the configured session before I/O"
            )
        return trace_config

    @staticmethod
    def _close_endpoint_streams(
        wearable: FramedEndpoint, relay: FramedEndpoint
    ) -> int:
        close_errors = 0
        seen: set[int] = set()
        for stream in (wearable.stream, relay.stream):
            if id(stream) in seen:
                continue
            seen.add(id(stream))
            try:
                stream.close()
            except Exception:
                close_errors += 1
        return close_errors

    def run(
        self, *, wearable: FramedEndpoint, relay: FramedEndpoint
    ) -> dict[str, Any]:
        trace_config = self._preflight(wearable=wearable, relay=relay)
        with self._state_lock:
            if self._run_started:
                raise ConcurrentBridgeError("a concurrent bridge instance is single-use")
            self._run_started = True
            if self._external_stop_requested:
                raise ConcurrentBridgeRunFailed(
                    "concurrent bridge was cancelled before start",
                    metadata={
                        "bridge_version": BRIDGE_VERSION,
                        "result": "FAIL",
                        "failure": {
                            "direction": "both",
                            "stage": "cancelled_before_start",
                            "cause_type": "operator_stop",
                        },
                        "connection_truth": {
                            "offline_fixture_full_duplex_completed": False,
                            "actual_endpoint_connection": "NOT_RUN",
                            "reported_connected": False,
                        },
                    },
                )

        start_ns = self.clock.monotonic_ns()
        if type(start_ns) is not int or start_ns < 0:
            raise ConcurrentBridgeError(
                "bridge clock must return a non-negative monotonic integer"
            )
        recorder = _MonotonicRecorder(self.clock, start_ns)
        ledger = _BufferLedger()
        queues = {
            "uplink": _DirectionQueue(self.config.uplink_queue_capacity),
            "downlink": _DirectionQueue(self.config.downlink_queue_capacity),
        }
        reader_done = {direction: threading.Event() for direction in _DIRECTIONS}
        inbound = {"uplink": wearable, "downlink": relay}
        outbound = {"uplink": relay, "downlink": wearable}
        stats: dict[str, dict[str, Any]] = {
            direction: {
                "frames_expected": self.config.frame_count,
                "frames_received": 0,
                "frames_enqueued": 0,
                "frames_forwarded": 0,
                "receive_retry_count": 0,
                "send_retry_count": 0,
                "backpressure_drops": 0,
                "deadline_misses_before_send": 0,
                "deadline_misses_after_send": 0,
                "cancelled_frames": 0,
                "worker_failures": 0,
                "peak_queue_depth": 0,
                "max_schedule_lateness_ns": 0,
            }
            for direction in _DIRECTIONS
        }
        stats_lock = threading.Lock()
        records: list[dict[str, Any]] = []
        records_lock = threading.Lock()
        failures: list[_WorkerFailure] = []
        failure_lock = threading.Lock()
        finished_workers = 0
        finish_lock = threading.Lock()

        with self._state_lock:
            self._queues = queues

        def wake_queues() -> None:
            for direction_queue in queues.values():
                direction_queue.wake_all()

        def record_failure(direction: str, stage: str, cause: Exception) -> None:
            with failure_lock:
                if failures:
                    return
                failures.append(_WorkerFailure(direction, stage, cause))
            with stats_lock:
                stats[direction]["worker_failures"] += 1
            self._stop_event.set()
            wake_queues()
            self._terminal_event.set()

        def mark_finished() -> None:
            nonlocal finished_workers
            with finish_lock:
                finished_workers += 1
                complete = finished_workers == _WORKER_COUNT
            if complete:
                self._terminal_event.set()

        def reader_worker(direction: str) -> None:
            stage = "receive"
            frame: MediaFrame | None = None
            try:
                while (
                    not self._stop_event.is_set()
                    and stats[direction]["frames_received"]
                    < self.config.frame_count
                ):
                    stage = "receive"
                    frame, attempts = inbound[direction].receive(
                        timeout_steps=self.config.timeout_steps,
                        attempts=self.config.receive_attempts,
                    )
                    ledger.accept(frame)
                    with stats_lock:
                        stats[direction]["frames_received"] += 1
                        stats[direction]["receive_retry_count"] += attempts - 1
                    if self._stop_event.is_set():
                        ledger.dispose(frame, disposition="cancelled")
                        with stats_lock:
                            stats[direction]["cancelled_frames"] += 1
                        frame = None
                        break
                    stage = "enqueue"
                    accepted, depth = queues[direction].put_nowait(frame)
                    if not accepted:
                        ledger.dispose(frame, disposition="backpressure")
                        frame = None
                        with stats_lock:
                            stats[direction]["backpressure_drops"] += 1
                        raise ConcurrentBridgeBackpressure(
                            f"{direction} queue reached its bounded capacity"
                        )
                    frame = None  # ownership transferred to the direction queue
                    with stats_lock:
                        stats[direction]["frames_enqueued"] += 1
                        stats[direction]["peak_queue_depth"] = max(
                            stats[direction]["peak_queue_depth"], depth
                        )
            except Exception as error:
                if frame is not None:
                    ledger.dispose(frame, disposition="worker_failure")
                    frame = None
                if not self._stop_event.is_set() or not failures:
                    record_failure(direction, stage, error)
            finally:
                reader_done[direction].set()
                queues[direction].wake_all()
                mark_finished()

        def writer_worker(direction: str) -> None:
            stage = "dequeue"
            frame: MediaFrame | None = None
            disposition = "worker_failure"
            try:
                while not self._stop_event.is_set():
                    stage = "dequeue"
                    frame = queues[direction].get(
                        stop_event=self._stop_event,
                        reader_done=reader_done[direction],
                    )
                    if frame is None:
                        return
                    disposition = "worker_failure"
                    due_ns = (
                        start_ns
                        + self.config.startup_grace_ns
                        + frame.sequence * FRAME_DURATION_NS
                    )
                    deadline_ns = due_ns + self.config.frame_deadline_ns
                    stage = "cadence_wait"
                    if not self.clock.wait_until(due_ns, self._stop_event):
                        disposition = "cancelled"
                        with stats_lock:
                            stats[direction]["cancelled_frames"] += 1
                        return
                    before_send_ns = self.clock.monotonic_ns()
                    if type(before_send_ns) is not int or before_send_ns < due_ns:
                        raise ConcurrentBridgeError(
                            "bridge clock returned before the requested monotonic deadline"
                        )
                    lateness_ns = before_send_ns - due_ns
                    with stats_lock:
                        stats[direction]["max_schedule_lateness_ns"] = max(
                            stats[direction]["max_schedule_lateness_ns"], lateness_ns
                        )
                    if before_send_ns > deadline_ns:
                        disposition = "deadline"
                        with stats_lock:
                            stats[direction]["deadline_misses_before_send"] += 1
                        stage = "send_deadline"
                        raise ConcurrentBridgeDeadline(
                            f"{direction} frame missed its pre-send deadline"
                        )

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
                    stage = "send"
                    attempts = outbound[direction].send(
                        frame,
                        timeout_steps=self.config.timeout_steps,
                        attempts=self.config.send_attempts,
                    )
                    # FramedEndpoint.send zeroes the media buffer in its own
                    # finally; the ledger repeats zeroing below to keep this
                    # bridge safe even for a future conforming subclass.
                    disposition = "forwarded"
                    completed_ns, trace_time_ns = recorder.stamp()
                    with stats_lock:
                        stats[direction]["frames_forwarded"] += 1
                        stats[direction]["send_retry_count"] += attempts - 1
                        completion_lateness_ns = max(0, completed_ns - due_ns)
                        stats[direction]["max_schedule_lateness_ns"] = max(
                            stats[direction]["max_schedule_lateness_ns"],
                            completion_lateness_ns,
                        )
                    with records_lock:
                        records.append(
                            {
                                "observation_id": (
                                    f"call020c:{direction}:"
                                    f"{frame_metadata['sequence']}:forward"
                                ),
                                "packet_id": (
                                    f"{frame_metadata['session_id']}:{direction}:"
                                    f"{frame_metadata['sequence']}"
                                ),
                                **frame_metadata,
                                "trace_clock_id": self.config.bridge_clock_id,
                                "trace_time_ns": trace_time_ns,
                                "encoded_size_bytes": FRAME_BYTES,
                            }
                        )
                    if completed_ns > deadline_ns:
                        with stats_lock:
                            stats[direction]["deadline_misses_after_send"] += 1
                        stage = "send_deadline"
                        raise ConcurrentBridgeDeadline(
                            f"{direction} frame completed after its deadline"
                        )
                    ledger.dispose(frame, disposition=disposition)
                    frame = None
            except Exception as error:
                if frame is not None:
                    ledger.dispose(frame, disposition=disposition)
                    frame = None
                if not self._stop_event.is_set() or not failures:
                    record_failure(direction, stage, error)
            finally:
                if frame is not None:
                    ledger.dispose(frame, disposition=disposition)
                mark_finished()

        threads = [
            threading.Thread(
                name=f"ego-call-{direction}-writer",
                target=writer_worker,
                args=(direction,),
                daemon=True,
            )
            for direction in _DIRECTIONS
        ] + [
            threading.Thread(
                name=f"ego-call-{direction}-reader",
                target=reader_worker,
                args=(direction,),
                daemon=True,
            )
            for direction in _DIRECTIONS
        ]

        runtime_started = time.monotonic()
        for thread in threads:
            thread.start()

        max_runtime_seconds = self.config.max_runtime_ms / 1000
        terminal_signalled = self._terminal_event.wait(max_runtime_seconds)
        runtime_timed_out = not terminal_signalled
        with failure_lock:
            worker_failure = failures[0] if failures else None
        with self._state_lock:
            externally_cancelled = self._external_stop_requested

        failure_kind: tuple[str, str, Exception | None] | None = None
        if runtime_timed_out:
            failure_kind = (
                "both",
                "runtime_timeout",
                ConcurrentBridgeDeadline("bounded bridge runtime expired"),
            )
        elif worker_failure is not None:
            failure_kind = (
                worker_failure.direction,
                worker_failure.stage,
                worker_failure.cause,
            )
        elif externally_cancelled:
            failure_kind = ("both", "cancelled", None)

        close_errors = 0
        if failure_kind is not None:
            self._stop_event.set()
            wake_queues()
            close_errors = self._close_endpoint_streams(wearable, relay)

        join_deadline = time.monotonic() + self.config.join_timeout_ms / 1000
        for thread in threads:
            remaining = max(0.0, join_deadline - time.monotonic())
            thread.join(remaining)
        alive_workers = sorted(thread.name for thread in threads if thread.is_alive())
        if alive_workers and failure_kind is None:
            failure_kind = (
                "both",
                "join_timeout",
                ConcurrentBridgeDeadline("workers exceeded the bounded join"),
            )
        if alive_workers:
            self._stop_event.set()
            wake_queues()
            close_errors += self._close_endpoint_streams(wearable, relay)

        for direction in _DIRECTIONS:
            for queued_frame in queues[direction].drain():
                ledger.dispose(queued_frame, disposition="coordinator_cleanup")
        # This also covers a frame held by a non-conforming worker that did not
        # honor stream close within the join bound.
        ledger.zero_all()
        buffer_lifecycle = ledger.snapshot()
        runtime_elapsed_ms = int((time.monotonic() - runtime_started) * 1000)

        with stats_lock:
            stats_snapshot = {
                direction: dict(stats[direction]) for direction in _DIRECTIONS
            }
        with finish_lock:
            finished_snapshot = finished_workers

        if not buffer_lifecycle["all_accepted_mutable_media_zeroized"]:
            failure_kind = (
                "both",
                "buffer_lifecycle",
                ConcurrentBridgeError("mutable media ownership did not close"),
            )

        if failure_kind is not None:
            direction, stage, cause = failure_kind
            failure_metadata = {
                "bridge_version": BRIDGE_VERSION,
                "result": "FAIL",
                "failure": {
                    "direction": direction,
                    "stage": stage,
                    "cause_type": (
                        type(cause).__name__ if cause is not None else "operator_stop"
                    ),
                    "cause_message_retained": False,
                },
                "worker_model": {
                    "reader_workers": 2,
                    "writer_workers": 2,
                    "independent_direction_queues": True,
                    "alive_after_join": alive_workers,
                    "finished_workers": finished_snapshot,
                    "close_errors": close_errors,
                },
                "bounded_run": {
                    "maximum_runtime_ms": self.config.max_runtime_ms,
                    "join_timeout_ms": self.config.join_timeout_ms,
                    "elapsed_ms": runtime_elapsed_ms,
                    "stop_requested": self._stop_event.is_set(),
                },
                "direction_stats": stats_snapshot,
                "buffer_lifecycle": buffer_lifecycle,
                "connection_truth": {
                    "offline_fixture_full_duplex_completed": False,
                    "actual_endpoint_connection": "NOT_RUN",
                    "reported_connected": False,
                },
                "claims": {
                    "real_io_ready": False,
                    "wearable_usb_cdc_media": "unverified",
                    "tls_relay_media": "unverified",
                    "source_bound_lte_egress": "unverified",
                    "p0_call": "NOT_RUN",
                },
            }
            _assert_metadata_only(failure_metadata)
            failed = ConcurrentBridgeRunFailed(
                "bounded concurrent media bridge failed",
                metadata=failure_metadata,
            )
            if cause is None:
                raise failed
            raise failed from cause

        with records_lock:
            ordered_records = sorted(
                (dict(record) for record in records),
                key=lambda record: record["trace_time_ns"],
            )
        trace_end_ns = max(1, recorder.last_relative_ns + 1)
        trace = {
            "trace_version": "egolink.ego_call_media_trace.v0.1",
            "trace_id": "call020c-concurrent-trace-001",
            "session_id": self.config.identity.session_id,
            "trace_clock_id": self.config.bridge_clock_id,
            "trace_start_time_ns": 0,
            "trace_end_time_ns": trace_end_ns,
            "endpoints": {
                "device_id": self.config.identity.device_id,
                "guardian_id": self.config.identity.guardian_id,
            },
            "source_clock_ids": {
                "uplink": self.config.identity.uplink_clock_id,
                "downlink": self.config.identity.downlink_clock_id,
            },
            "config": trace_config,
            "records": ordered_records,
        }
        try:
            evaluation = evaluate_media_trace(trace)
        except MediaTraceError as error:
            raise ConcurrentBridgeError(
                "metadata evaluator rejected the concurrent bridge trace"
            ) from error

        forwarded_all = all(
            stats_snapshot[direction]["frames_forwarded"]
            == self.config.frame_count
            for direction in _DIRECTIONS
        )
        fixture_pass = evaluation["evaluation_result"] == "PASS" and forwarded_all
        result = {
            "bridge_version": BRIDGE_VERSION,
            "result": "PASS" if fixture_pass else "FAIL",
            "profile": self.config.profile.metadata(),
            "worker_model": {
                "reader_workers": 2,
                "writer_workers": 2,
                "independent_direction_queues": True,
                "independent_failure_detection": True,
                "failure_in_one_direction_terminates_session": True,
                "all_workers_joined": finished_snapshot == _WORKER_COUNT,
                "alive_after_join": alive_workers,
            },
            "clock_and_deadline": {
                "clock": "monotonic_wall_clock",
                "source_clock_preserved_per_direction": True,
                "absolute_frame_cadence_ns": FRAME_DURATION_NS,
                "startup_grace_ns": self.config.startup_grace_ns,
                "frame_deadline_ns": self.config.frame_deadline_ns,
                "trace_timestamp_collision_adjustments": (
                    recorder.collision_adjustments
                ),
            },
            "bounded_run": {
                "requested_frames_per_direction": self.config.frame_count,
                "maximum_runtime_ms": self.config.max_runtime_ms,
                "join_timeout_ms": self.config.join_timeout_ms,
                "elapsed_ms": runtime_elapsed_ms,
                "stop_requested": False,
                "raw_audio_persisted": False,
                "raw_audio_logged": False,
                "socket_serial_audio_network_hardware_opened_by_bridge": False,
            },
            "direction_stats": stats_snapshot,
            "buffer_lifecycle": buffer_lifecycle,
            "offline_evaluation": {
                "evaluation_result": evaluation["evaluation_result"],
                "full_duplex_metadata_observed": evaluation[
                    "full_duplex_observed"
                ],
                "direction_metrics": evaluation["direction_metrics"],
                "failure_reasons": evaluation["failure_reasons"],
            },
            "connection_truth": {
                "offline_fixture_full_duplex_completed": fixture_pass,
                "actual_endpoint_connection": "NOT_RUN",
                "reported_connected": False,
            },
            "determinism_boundary": {
                "worker_interleaving_and_wall_timestamps": (
                    "runtime_observations_not_bitwise_deterministic"
                ),
                "per_direction_sequence_and_source_cadence": "deterministic",
                "metadata_evaluation_given_same_trace": "deterministic",
            },
            "claims": {
                "offline_concurrent_worker_structure": "verified",
                "real_io_ready": False,
                "wearable_usb_cdc_media": "unverified",
                "tls_relay_media": "unverified",
                "source_bound_lte_egress": "unverified",
                "device_audio": "unverified_in_this_slice",
                "production_rtc_provider": "not_selected",
                "p0_call": "NOT_RUN",
            },
        }
        _assert_metadata_only(result)
        return result


__all__ = [
    "BRIDGE_VERSION",
    "BridgeClock",
    "ConcurrentBridgeBackpressure",
    "ConcurrentBridgeConfig",
    "ConcurrentBridgeDeadline",
    "ConcurrentBridgeError",
    "ConcurrentBridgeRunFailed",
    "ConcurrentDuplexMediaBridge",
    "SystemMonotonicClock",
]

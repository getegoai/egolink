from __future__ import annotations

import json
import threading
import time
import unittest
from dataclasses import replace

from pc_simulator import ego_call_concurrent_bridge as concurrent
from pc_simulator import ego_call_media_io as media_io


class _ScriptedByteStream:
    """Thread-safe, process-local ordered-stream double with explicit gates."""

    def __init__(
        self,
        incoming: bytearray,
        *,
        block_first_read: bool = False,
        block_first_write: bool = False,
        fail_read_call: int | None = None,
        read_failure: Exception | None = None,
        fail_write_call: int | None = None,
        write_failure: Exception | None = None,
        expected_writes: int | None = None,
    ) -> None:
        self.incoming = incoming
        self._offset = 0
        self._lock = threading.Lock()
        self._closed = threading.Event()
        self.read_entered = threading.Event()
        self.read_release = threading.Event()
        self.write_entered = threading.Event()
        self.write_release = threading.Event()
        self.expected_writes_reached = threading.Event()
        self.block_first_read = block_first_read
        self.block_first_write = block_first_write
        self.fail_read_call = fail_read_call
        self.read_failure = read_failure
        self.fail_write_call = fail_write_call
        self.write_failure = write_failure
        self.expected_writes = expected_writes
        self.read_calls = 0
        self.write_calls = 0
        self.retained_write_buffers: list[bytearray] = []

    def _wait_gate(
        self, entered: threading.Event, release: threading.Event
    ) -> None:
        entered.set()
        while not release.wait(0.01):
            if self._closed.is_set():
                raise media_io.MediaIoError("scripted stream closed while blocked")

    def read_exact(self, size: int, *, timeout_steps: int) -> bytearray:
        del timeout_steps
        with self._lock:
            self.read_calls += 1
            call = self.read_calls
        if self.block_first_read and call == 1:
            self._wait_gate(self.read_entered, self.read_release)
        if self._closed.is_set():
            raise media_io.MediaIoError("scripted stream is closed")
        if self.fail_read_call == call:
            raise self.read_failure or media_io.MediaIoError("scripted read failure")
        with self._lock:
            end = self._offset + size
            if end > len(self.incoming):
                raise media_io.MediaIoTimeout(
                    "scripted zero-progress read timeout", retry_safe=True
                )
            result = bytearray(self.incoming[self._offset : end])
            self.incoming[self._offset : end] = b"\x00" * size
            self._offset = end
            return result

    def write_all(self, data: memoryview, *, timeout_steps: int) -> None:
        del timeout_steps
        with self._lock:
            self.write_calls += 1
            call = self.write_calls
            self.retained_write_buffers.append(data.obj)
        if self.block_first_write and call == 1:
            self._wait_gate(self.write_entered, self.write_release)
        if self._closed.is_set():
            raise media_io.MediaIoError("scripted stream is closed")
        if self.fail_write_call == call:
            raise self.write_failure or media_io.MediaIoError("scripted write failure")
        if self.expected_writes is not None and call >= self.expected_writes:
            self.expected_writes_reached.set()

    def close(self) -> None:
        self._closed.set()
        with self._lock:
            self.incoming[self._offset :] = b"\x00" * (
                len(self.incoming) - self._offset
            )

    def buffers_are_zero(self) -> bool:
        with self._lock:
            return all(value == 0 for value in self.incoming) and all(
                all(value == 0 for value in item)
                for item in self.retained_write_buffers
            )


class _InspectingEndpoint(media_io.FramedEndpoint):
    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.accepted_media_refs: list[bytearray] = []

    def receive(
        self, *, timeout_steps: int, attempts: int
    ) -> tuple[media_io.MediaFrame, int]:
        frame, used_attempts = super().receive(
            timeout_steps=timeout_steps, attempts=attempts
        )
        self.accepted_media_refs.append(frame.media)
        return frame, used_attempts


class _OffsetMonotonicClock:
    """Controllable monotonic clock; tests advance it only behind barriers."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._offset_ns = 0

    def advance(self, delta_ns: int) -> None:
        with self._lock:
            self._offset_ns += delta_ns

    def monotonic_ns(self) -> int:
        with self._lock:
            offset_ns = self._offset_ns
        return time.monotonic_ns() + offset_ns

    def wait_until(self, target_ns: int, stop_event: threading.Event) -> bool:
        while not stop_event.is_set():
            remaining_ns = target_ns - self.monotonic_ns()
            if remaining_ns <= 0:
                return True
            if stop_event.wait(remaining_ns / 1_000_000_000):
                return False
        return False


def _wire_frames(
    config: concurrent.ConcurrentBridgeConfig, direction: str
) -> bytearray:
    io_config = media_io.MediaIoConfig(
        identity=config.identity,
        bridge_clock_id=config.bridge_clock_id,
        frame_count=config.frame_count,
        max_cycles=config.frame_count,
    )
    aggregate = bytearray()
    for sequence in range(config.frame_count):
        frame = media_io._make_frame(io_config, direction, sequence)
        wire = media_io.FrameCodec.encode(frame)
        try:
            aggregate.extend(wire)
        finally:
            media_io._zero(wire)
            frame.dispose()
    return aggregate


def _endpoints(
    config: concurrent.ConcurrentBridgeConfig,
    *,
    wearable_options: dict[str, object] | None = None,
    relay_options: dict[str, object] | None = None,
) -> tuple[
    _InspectingEndpoint,
    _InspectingEndpoint,
    _ScriptedByteStream,
    _ScriptedByteStream,
]:
    wearable_stream = _ScriptedByteStream(
        _wire_frames(config, "uplink"), **(wearable_options or {})
    )
    relay_stream = _ScriptedByteStream(
        _wire_frames(config, "downlink"), **(relay_options or {})
    )
    wearable = _InspectingEndpoint(
        wearable_stream,
        config.identity,
        inbound_direction="uplink",
        outbound_direction="downlink",
    )
    relay = _InspectingEndpoint(
        relay_stream,
        config.identity,
        inbound_direction="downlink",
        outbound_direction="uplink",
    )
    return wearable, relay, wearable_stream, relay_stream


class EgoCallConcurrentBridgeTests(unittest.TestCase):
    def config(self, **changes: object) -> concurrent.ConcurrentBridgeConfig:
        base = concurrent.ConcurrentBridgeConfig(
            frame_count=4,
            max_runtime_ms=1_500,
            join_timeout_ms=500,
            frame_deadline_ns=300_000_000,
        )
        return replace(base, **changes)

    def assert_media_zeroed(
        self,
        wearable: _InspectingEndpoint,
        relay: _InspectingEndpoint,
        wearable_stream: _ScriptedByteStream,
        relay_stream: _ScriptedByteStream,
    ) -> None:
        self.assertTrue(
            all(
                all(value == 0 for value in payload)
                for endpoint in (wearable, relay)
                for payload in endpoint.accepted_media_refs
            )
        )
        self.assertTrue(wearable_stream.buffers_are_zero())
        self.assertTrue(relay_stream.buffers_are_zero())

    def test_healthy_run_uses_four_workers_twenty_ms_cadence_and_metadata_only(self) -> None:
        config = self.config()
        wearable, relay, wearable_stream, relay_stream = _endpoints(config)

        result = concurrent.ConcurrentDuplexMediaBridge(config).run(
            wearable=wearable, relay=relay
        )

        self.assertEqual(result["result"], "PASS")
        self.assertEqual(result["worker_model"]["reader_workers"], 2)
        self.assertEqual(result["worker_model"]["writer_workers"], 2)
        self.assertTrue(result["worker_model"]["all_workers_joined"])
        self.assertTrue(result["worker_model"]["independent_failure_detection"])
        self.assertTrue(
            result["worker_model"]["failure_in_one_direction_terminates_session"]
        )
        self.assertNotIn(
            "uplink_and_downlink_failure_isolation", result["worker_model"]
        )
        self.assertEqual(
            result["clock_and_deadline"]["absolute_frame_cadence_ns"],
            20_000_000,
        )
        self.assertEqual(
            result["direction_stats"]["uplink"]["frames_forwarded"], 4
        )
        self.assertEqual(
            result["direction_stats"]["downlink"]["frames_forwarded"], 4
        )
        self.assertTrue(
            result["buffer_lifecycle"]["all_accepted_mutable_media_zeroized"]
        )
        self.assertTrue(
            result["connection_truth"]["offline_fixture_full_duplex_completed"]
        )
        self.assertEqual(
            result["connection_truth"]["actual_endpoint_connection"], "NOT_RUN"
        )
        self.assertFalse(result["connection_truth"]["reported_connected"])
        self.assertFalse(result["claims"]["real_io_ready"])
        self.assertNotIn("bytearray", json.dumps(result, sort_keys=True))
        self.assert_media_zeroed(wearable, relay, wearable_stream, relay_stream)

    def test_blocked_uplink_reader_does_not_starve_downlink_worker(self) -> None:
        config = self.config(frame_deadline_ns=700_000_000)
        wearable, relay, wearable_stream, relay_stream = _endpoints(
            config,
            wearable_options={
                "block_first_read": True,
                "expected_writes": config.frame_count,
            },
        )
        bridge = concurrent.ConcurrentDuplexMediaBridge(config)
        outcome: dict[str, object] = {}

        def run() -> None:
            try:
                outcome["result"] = bridge.run(wearable=wearable, relay=relay)
            except Exception as error:  # pragma: no cover - asserted below
                outcome["error"] = error

        runner = threading.Thread(target=run)
        runner.start()
        self.assertTrue(wearable_stream.read_entered.wait(0.5))
        self.assertTrue(wearable_stream.expected_writes_reached.wait(0.5))
        self.assertTrue(runner.is_alive())
        wearable_stream.read_release.set()
        runner.join(1.0)

        self.assertFalse(runner.is_alive())
        self.assertNotIn("error", outcome)
        result = outcome["result"]
        self.assertEqual(result["result"], "PASS")
        self.assertEqual(
            result["direction_stats"]["downlink"]["frames_forwarded"], 4
        )
        self.assert_media_zeroed(wearable, relay, wearable_stream, relay_stream)

    def test_blocked_send_exposes_deadline_failure_and_never_reports_connected(self) -> None:
        config = self.config(frame_deadline_ns=300_000_000)
        clock = _OffsetMonotonicClock()
        wearable, relay, wearable_stream, relay_stream = _endpoints(
            config,
            wearable_options={"expected_writes": config.frame_count},
            relay_options={"block_first_write": True},
        )
        bridge = concurrent.ConcurrentDuplexMediaBridge(config, clock=clock)
        outcome: dict[str, object] = {}

        def run() -> None:
            try:
                bridge.run(wearable=wearable, relay=relay)
            except Exception as error:
                outcome["error"] = error

        runner = threading.Thread(target=run)
        runner.start()
        self.assertTrue(relay_stream.write_entered.wait(0.5))
        self.assertTrue(wearable_stream.expected_writes_reached.wait(0.5))
        clock.advance(500_000_000)
        relay_stream.write_release.set()
        runner.join(1.0)

        self.assertFalse(runner.is_alive())
        error = outcome["error"]
        self.assertIsInstance(error, concurrent.ConcurrentBridgeRunFailed)
        self.assertEqual(error.metadata["failure"]["direction"], "uplink")
        self.assertEqual(error.metadata["failure"]["stage"], "send_deadline")
        self.assertIsInstance(error.__cause__, concurrent.ConcurrentBridgeDeadline)
        self.assertFalse(
            error.metadata["connection_truth"]["offline_fixture_full_duplex_completed"]
        )
        self.assertFalse(error.metadata["connection_truth"]["reported_connected"])
        self.assert_media_zeroed(wearable, relay, wearable_stream, relay_stream)

    def test_blocked_writer_causes_only_bounded_queue_backpressure(self) -> None:
        config = self.config(
            frame_count=8,
            uplink_queue_capacity=1,
            max_runtime_ms=2_000,
            frame_deadline_ns=800_000_000,
        )
        wearable, relay, wearable_stream, relay_stream = _endpoints(
            config, relay_options={"block_first_write": True}
        )

        with self.assertRaises(concurrent.ConcurrentBridgeRunFailed) as raised:
            concurrent.ConcurrentDuplexMediaBridge(config).run(
                wearable=wearable, relay=relay
            )

        metadata = raised.exception.metadata
        self.assertEqual(metadata["failure"]["direction"], "uplink")
        self.assertEqual(metadata["failure"]["stage"], "enqueue")
        self.assertEqual(
            metadata["direction_stats"]["uplink"]["backpressure_drops"], 1
        )
        self.assertEqual(metadata["worker_model"]["alive_after_join"], [])
        self.assertTrue(
            metadata["buffer_lifecycle"]["all_accepted_mutable_media_zeroized"]
        )
        self.assert_media_zeroed(wearable, relay, wearable_stream, relay_stream)

    def test_unknown_progress_receive_timeout_is_terminal_and_not_retried(self) -> None:
        config = self.config(receive_attempts=3)
        unknown_timeout = media_io.MediaIoTimeout(
            "unknown progress must remain terminal", retry_safe=False
        )
        wearable, relay, wearable_stream, relay_stream = _endpoints(
            config,
            wearable_options={
                "fail_read_call": 1,
                "read_failure": unknown_timeout,
            },
        )

        with self.assertRaises(concurrent.ConcurrentBridgeRunFailed) as raised:
            concurrent.ConcurrentDuplexMediaBridge(config).run(
                wearable=wearable, relay=relay
            )

        self.assertEqual(wearable_stream.read_calls, 1)
        self.assertEqual(raised.exception.metadata["failure"]["stage"], "receive")
        self.assertIsInstance(raised.exception.__cause__, media_io.MediaIoProtocolError)
        self.assertIs(raised.exception.__cause__.__cause__, unknown_timeout)
        self.assertFalse(
            raised.exception.metadata["connection_truth"]["reported_connected"]
        )
        self.assert_media_zeroed(wearable, relay, wearable_stream, relay_stream)

    def test_timeout_after_consumed_header_is_terminal(self) -> None:
        config = self.config(receive_attempts=3)
        tail_timeout = media_io.MediaIoTimeout(
            "zero progress on tail is unsafe after header", retry_safe=True
        )
        wearable, relay, wearable_stream, relay_stream = _endpoints(
            config,
            wearable_options={
                "fail_read_call": 2,
                "read_failure": tail_timeout,
            },
        )

        with self.assertRaises(concurrent.ConcurrentBridgeRunFailed) as raised:
            concurrent.ConcurrentDuplexMediaBridge(config).run(
                wearable=wearable, relay=relay
            )

        self.assertEqual(wearable_stream.read_calls, 2)
        self.assertIsInstance(raised.exception.__cause__, media_io.MediaIoProtocolError)
        self.assertIn("header consumption", str(raised.exception.__cause__))
        self.assert_media_zeroed(wearable, relay, wearable_stream, relay_stream)

    def test_worker_exception_propagates_as_cause_without_message_in_metadata(self) -> None:
        config = self.config()
        secret_message = "private-media-like-fixture-value"
        write_error = RuntimeError(secret_message)
        wearable, relay, wearable_stream, relay_stream = _endpoints(
            config,
            relay_options={
                "fail_write_call": 1,
                "write_failure": write_error,
            },
        )

        with self.assertRaises(concurrent.ConcurrentBridgeRunFailed) as raised:
            concurrent.ConcurrentDuplexMediaBridge(config).run(
                wearable=wearable, relay=relay
            )

        self.assertIs(raised.exception.__cause__, write_error)
        serialized = json.dumps(raised.exception.metadata, sort_keys=True)
        self.assertNotIn(secret_message, serialized)
        self.assertEqual(
            raised.exception.metadata["failure"]["cause_type"], "RuntimeError"
        )
        self.assertFalse(
            raised.exception.metadata["failure"]["cause_message_retained"]
        )
        self.assert_media_zeroed(wearable, relay, wearable_stream, relay_stream)

    def test_external_stop_closes_blocking_workers_and_joins_within_bound(self) -> None:
        config = self.config(max_runtime_ms=2_000, join_timeout_ms=300)
        wearable, relay, wearable_stream, relay_stream = _endpoints(
            config,
            wearable_options={"block_first_read": True},
            relay_options={"block_first_read": True},
        )
        bridge = concurrent.ConcurrentDuplexMediaBridge(config)
        outcome: dict[str, object] = {}

        def run() -> None:
            try:
                bridge.run(wearable=wearable, relay=relay)
            except Exception as error:
                outcome["error"] = error

        runner = threading.Thread(target=run)
        runner.start()
        self.assertTrue(wearable_stream.read_entered.wait(0.5))
        self.assertTrue(relay_stream.read_entered.wait(0.5))
        started = time.monotonic()
        bridge.request_stop()
        runner.join(0.8)
        elapsed = time.monotonic() - started

        self.assertFalse(runner.is_alive())
        self.assertLess(elapsed, 0.8)
        error = outcome["error"]
        self.assertIsInstance(error, concurrent.ConcurrentBridgeRunFailed)
        self.assertEqual(error.metadata["failure"]["stage"], "cancelled")
        self.assertEqual(error.metadata["worker_model"]["alive_after_join"], [])
        self.assertTrue(error.metadata["bounded_run"]["stop_requested"])
        self.assert_media_zeroed(wearable, relay, wearable_stream, relay_stream)

    def test_preflight_identity_rejection_occurs_before_stream_io(self) -> None:
        config = self.config()
        wearable, relay, wearable_stream, relay_stream = _endpoints(config)
        relay.identity = replace(config.identity, session_id="another-session")

        with self.assertRaisesRegex(media_io.MediaIoProtocolError, "before I/O"):
            concurrent.ConcurrentDuplexMediaBridge(config).run(
                wearable=wearable, relay=relay
            )

        self.assertEqual(wearable_stream.read_calls, 0)
        self.assertEqual(wearable_stream.write_calls, 0)
        self.assertEqual(relay_stream.read_calls, 0)
        self.assertEqual(relay_stream.write_calls, 0)
        wearable_stream.close()
        relay_stream.close()
        self.assert_media_zeroed(wearable, relay, wearable_stream, relay_stream)

    def test_determinism_boundary_is_explicit_while_counts_stay_stable(self) -> None:
        results = []
        endpoints = []
        for _ in range(2):
            config = self.config()
            wearable, relay, wearable_stream, relay_stream = _endpoints(config)
            result = concurrent.ConcurrentDuplexMediaBridge(config).run(
                wearable=wearable, relay=relay
            )
            results.append(result)
            endpoints.append((wearable, relay, wearable_stream, relay_stream))

        self.assertEqual(
            results[0]["determinism_boundary"],
            {
                "worker_interleaving_and_wall_timestamps": (
                    "runtime_observations_not_bitwise_deterministic"
                ),
                "per_direction_sequence_and_source_cadence": "deterministic",
                "metadata_evaluation_given_same_trace": "deterministic",
            },
        )
        for direction in ("uplink", "downlink"):
            self.assertEqual(
                results[0]["direction_stats"][direction]["frames_forwarded"],
                results[1]["direction_stats"][direction]["frames_forwarded"],
            )
            self.assertEqual(
                results[0]["offline_evaluation"]["direction_metrics"][direction][
                    "max_source_cadence_error_ns"
                ],
                0,
            )
        for endpoint_set in endpoints:
            self.assert_media_zeroed(*endpoint_set)


if __name__ == "__main__":
    unittest.main()

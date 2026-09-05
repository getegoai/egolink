from __future__ import annotations

import json
import threading
import time
import unittest
from dataclasses import replace
from pathlib import Path

from pc_simulator import ego_call_authenticated_relay as relay_core
from pc_simulator import ego_call_concurrent_bridge as concurrent
from pc_simulator import ego_call_media_io as media_io


IDENTITY = media_io.EndpointIdentity(
    session_id="call020i-session",
    device_id="call020i-device",
    guardian_id="call020i-guardian",
    uplink_clock_id="call020i-device-clock",
    downlink_clock_id="call020i-guardian-clock",
)


def _wire_frames(identity: media_io.EndpointIdentity, direction: str, count: int) -> bytearray:
    config = media_io.MediaIoConfig(
        identity=identity,
        frame_count=count,
        max_cycles=count,
    )
    aggregate = bytearray()
    for sequence in range(count):
        frame = media_io._make_frame(config, direction, sequence)
        wire = media_io.FrameCodec.encode(frame)
        try:
            aggregate.extend(wire)
        finally:
            media_io._zero(wire)
            frame.dispose()
    return aggregate


class _InjectedTlsStream:
    """Caller-owned ordered-stream double; it creates no socket or connection."""

    def __init__(
        self,
        incoming: bytearray | None = None,
        *,
        connection_id: str,
        disconnect_on_read: bool = False,
        block_read_until_close: bool = False,
    ) -> None:
        self.connection_id = connection_id
        self.incoming = incoming or bytearray()
        self.offset = 0
        self.disconnect_on_read = disconnect_on_read
        self.block_read_until_close = block_read_until_close
        self.read_calls = 0
        self.write_calls = 0
        self.close_calls = 0
        self.closed = threading.Event()
        self.read_entered = threading.Event()
        self.retained_writes: list[bytearray] = []
        self._read_lock = threading.Lock()
        self._write_lock = threading.Lock()

    def read_exact(self, size: int, *, timeout_steps: int) -> bytearray:
        del timeout_steps
        self.read_calls += 1
        self.read_entered.set()
        if self.block_read_until_close:
            self.closed.wait(1.0)
            raise media_io.MediaIoError("injected TLS fixture closed")
        with self._read_lock:
            if self.closed.is_set() or self.disconnect_on_read:
                raise media_io.MediaIoError("injected TLS fixture disconnected")
            end = self.offset + size
            if end > len(self.incoming):
                raise media_io.MediaIoError("injected TLS fixture ended")
            result = bytearray(self.incoming[self.offset : end])
            self.incoming[self.offset : end] = b"\x00" * size
            self.offset = end
            return result

    def write_all(self, data: memoryview, *, timeout_steps: int) -> None:
        del timeout_steps
        with self._write_lock:
            self.write_calls += 1
            if self.closed.is_set():
                raise media_io.MediaIoError("injected TLS fixture disconnected")
            self.retained_writes.append(data.obj)

    def close(self) -> None:
        self.close_calls += 1
        self.closed.set()
        with self._read_lock:
            self.incoming[self.offset :] = b"\x00" * (len(self.incoming) - self.offset)

    def buffers_are_zero(self) -> bool:
        return all(value == 0 for value in self.incoming) and all(
            all(value == 0 for value in item) for item in self.retained_writes
        )


def _config(
    identity: media_io.EndpointIdentity = IDENTITY,
    *,
    frame_count: int = 2,
) -> relay_core.AuthenticatedRelayConfig:
    return relay_core.AuthenticatedRelayConfig(
        bridge=concurrent.ConcurrentBridgeConfig(
            identity=identity,
            bridge_clock_id=f"bridge-{identity.session_id}",
            frame_count=frame_count,
            receive_attempts=1,
            send_attempts=1,
            timeout_steps=1,
            max_runtime_ms=2_000,
            join_timeout_ms=500,
            frame_deadline_ns=500_000_000,
        )
    )


def _decisions(
    identity: media_io.EndpointIdentity = IDENTITY,
    *,
    device_connection: str = "device-connection-001",
    guardian_connection: str = "guardian-connection-001",
    device_decision_id: str = "device-decision-001",
    guardian_decision_id: str = "guardian-decision-001",
    device_authenticated: bool = True,
    guardian_authenticated: bool = True,
) -> tuple[
    relay_core.ExternalAuthenticationDecision,
    relay_core.ExternalAuthenticationDecision,
]:
    now = time.monotonic_ns()
    device_binding = relay_core.RelayEndpointBinding(
        session_id=identity.session_id,
        role="device",
        endpoint_id=identity.device_id,
        peer_endpoint_id=identity.guardian_id,
        source_clock_id=identity.uplink_clock_id,
        connection_id=device_connection,
    )
    guardian_binding = relay_core.RelayEndpointBinding(
        session_id=identity.session_id,
        role="guardian",
        endpoint_id=identity.guardian_id,
        peer_endpoint_id=identity.device_id,
        source_clock_id=identity.downlink_clock_id,
        connection_id=guardian_connection,
    )
    return (
        relay_core.ExternalAuthenticationDecision(
            decision_id=device_decision_id,
            authenticated=device_authenticated,
            binding=device_binding,
            valid_from_monotonic_ns=now - 1_000_000,
            expires_at_monotonic_ns=now + 10_000_000_000,
        ),
        relay_core.ExternalAuthenticationDecision(
            decision_id=guardian_decision_id,
            authenticated=guardian_authenticated,
            binding=guardian_binding,
            valid_from_monotonic_ns=now - 1_000_000,
            expires_at_monotonic_ns=now + 10_000_000_000,
        ),
    )


def _run_healthy(
    registry: relay_core.RelayAdmissionRegistry,
    *,
    identity: media_io.EndpointIdentity = IDENTITY,
    decisions: tuple[
        relay_core.ExternalAuthenticationDecision,
        relay_core.ExternalAuthenticationDecision,
    ] | None = None,
    frame_count: int = 2,
) -> tuple[
    dict[str, object],
    relay_core.ProcessLocalAuthenticatedRelay,
    _InjectedTlsStream,
    _InjectedTlsStream,
]:
    device_decision, guardian_decision = decisions or _decisions(identity)
    device_stream = _InjectedTlsStream(
        _wire_frames(identity, "uplink", frame_count),
        connection_id=device_decision.binding.connection_id,
    )
    guardian_stream = _InjectedTlsStream(
        _wire_frames(identity, "downlink", frame_count),
        connection_id=guardian_decision.binding.connection_id,
    )
    relay = relay_core.ProcessLocalAuthenticatedRelay(
        _config(identity, frame_count=frame_count), registry
    )
    result = relay.run(
        device_stream=device_stream,
        guardian_stream=guardian_stream,
        device_decision=device_decision,
        guardian_decision=guardian_decision,
    )
    return result, relay, device_stream, guardian_stream


class EgoCallAuthenticatedRelayTests(unittest.TestCase):
    def test_cancel_before_first_run_closes_without_auth_or_registry_reservation(self) -> None:
        registry = relay_core.RelayAdmissionRegistry()
        device_decision, guardian_decision = _decisions()
        device_stream = _InjectedTlsStream(
            _wire_frames(IDENTITY, "uplink", 2),
            connection_id=device_decision.binding.connection_id,
        )
        guardian_stream = _InjectedTlsStream(
            _wire_frames(IDENTITY, "downlink", 2),
            connection_id=guardian_decision.binding.connection_id,
        )
        relay = relay_core.ProcessLocalAuthenticatedRelay(_config(), registry)
        relay.request_cancel()

        with self.assertRaises(relay_core.RelayAdmissionError) as raised:
            relay.run(
                device_stream=device_stream,
                guardian_stream=guardian_stream,
                device_decision=device_decision,
                guardian_decision=guardian_decision,
            )

        self.assertEqual(raised.exception.reason_code, "cancelled_before_admission")
        self.assertEqual(device_stream.read_calls + guardian_stream.read_calls, 0)
        self.assertEqual(device_stream.write_calls + guardian_stream.write_calls, 0)
        self.assertTrue(device_stream.closed.is_set())
        self.assertTrue(guardian_stream.closed.is_set())
        self.assertTrue(device_stream.buffers_are_zero())
        self.assertTrue(guardian_stream.buffers_are_zero())
        self.assertEqual(registry.audit()["session_count"], 0)
        self.assertEqual(relay.audit()["state"], "cancelled")
        self.assertFalse(relay.audit()["pair_reserved_before_media"])

    def test_both_external_decisions_are_required_before_any_media_io(self) -> None:
        registry = relay_core.RelayAdmissionRegistry()
        device_decision, guardian_decision = _decisions(
            guardian_authenticated=False
        )
        device_stream = _InjectedTlsStream(
            _wire_frames(IDENTITY, "uplink", 1),
            connection_id=device_decision.binding.connection_id,
        )
        guardian_stream = _InjectedTlsStream(
            _wire_frames(IDENTITY, "downlink", 1),
            connection_id=guardian_decision.binding.connection_id,
        )
        relay = relay_core.ProcessLocalAuthenticatedRelay(_config(frame_count=2), registry)

        with self.assertRaises(relay_core.RelayAdmissionError) as raised:
            relay.run(
                device_stream=device_stream,
                guardian_stream=guardian_stream,
                device_decision=device_decision,
                guardian_decision=guardian_decision,
            )

        self.assertEqual(raised.exception.reason_code, "both_endpoints_must_authenticate")
        self.assertEqual((device_stream.read_calls, device_stream.write_calls), (0, 0))
        self.assertEqual((guardian_stream.read_calls, guardian_stream.write_calls), (0, 0))
        self.assertTrue(device_stream.closed.is_set())
        self.assertTrue(guardian_stream.closed.is_set())
        self.assertFalse(raised.exception.metadata["reported_connected"])
        self.assertTrue(device_stream.buffers_are_zero())
        self.assertTrue(guardian_stream.buffers_are_zero())

    def test_exact_session_role_endpoint_and_clock_bindings_fail_closed_pre_io(self) -> None:
        mutations = {
            "session": lambda binding: replace(binding, session_id="other-session"),
            "role": lambda binding: replace(binding, role="guardian"),
            "endpoint": lambda binding: replace(binding, endpoint_id="other-device"),
            "clock": lambda binding: replace(binding, source_clock_id="other-clock"),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                registry = relay_core.RelayAdmissionRegistry()
                device_decision, guardian_decision = _decisions()
                device_decision = replace(
                    device_decision, binding=mutate(device_decision.binding)
                )
                device_stream = _InjectedTlsStream(
                    _wire_frames(IDENTITY, "uplink", 1),
                    connection_id=device_decision.binding.connection_id,
                )
                guardian_stream = _InjectedTlsStream(
                    _wire_frames(IDENTITY, "downlink", 1),
                    connection_id=guardian_decision.binding.connection_id,
                )
                relay = relay_core.ProcessLocalAuthenticatedRelay(
                    _config(frame_count=2), registry
                )
                with self.assertRaises(relay_core.RelayAdmissionError) as raised:
                    relay.run(
                        device_stream=device_stream,
                        guardian_stream=guardian_stream,
                        device_decision=device_decision,
                        guardian_decision=guardian_decision,
                    )
                self.assertFalse(raised.exception.metadata["media_io_started"])
                self.assertFalse(raised.exception.metadata["reported_connected"])
                self.assertEqual(device_stream.read_calls + guardian_stream.read_calls, 0)
                self.assertEqual(device_stream.write_calls + guardian_stream.write_calls, 0)
                self.assertTrue(device_stream.buffers_are_zero())
                self.assertTrue(guardian_stream.buffers_are_zero())

    def test_expired_or_overlong_authentication_decision_is_rejected_pre_io(self) -> None:
        for label, mutate in (
            (
                "expired",
                lambda decision, now: replace(
                    decision,
                    valid_from_monotonic_ns=now - 2_000_000,
                    expires_at_monotonic_ns=now - 1_000_000,
                ),
            ),
            (
                "overlong",
                lambda decision, now: replace(
                    decision,
                    valid_from_monotonic_ns=now,
                    expires_at_monotonic_ns=now + relay_core.MAX_AUTH_WINDOW_NS + 1,
                ),
            ),
        ):
            with self.subTest(label=label):
                now = time.monotonic_ns()
                device_decision, guardian_decision = _decisions()
                device_decision = mutate(device_decision, now)
                device_stream = _InjectedTlsStream(
                    connection_id=device_decision.binding.connection_id
                )
                guardian_stream = _InjectedTlsStream(
                    connection_id=guardian_decision.binding.connection_id
                )
                relay = relay_core.ProcessLocalAuthenticatedRelay(
                    _config(frame_count=2), relay_core.RelayAdmissionRegistry()
                )
                with self.assertRaises(relay_core.RelayAdmissionError):
                    relay.run(
                        device_stream=device_stream,
                        guardian_stream=guardian_stream,
                        device_decision=device_decision,
                        guardian_decision=guardian_decision,
                    )
                self.assertEqual(device_stream.read_calls + guardian_stream.read_calls, 0)
                self.assertTrue(device_stream.closed.is_set())
                self.assertTrue(guardian_stream.closed.is_set())

    def test_swapped_or_mismatched_authenticated_stream_connection_is_rejected(self) -> None:
        device_decision, guardian_decision = _decisions()
        cases = (
            (
                "swapped",
                guardian_decision.binding.connection_id,
                device_decision.binding.connection_id,
            ),
            (
                "device-mismatch",
                "unbound-device-stream",
                guardian_decision.binding.connection_id,
            ),
        )
        for label, device_connection, guardian_connection in cases:
            with self.subTest(label=label):
                device_stream = _InjectedTlsStream(
                    _wire_frames(IDENTITY, "uplink", 1),
                    connection_id=device_connection,
                )
                guardian_stream = _InjectedTlsStream(
                    _wire_frames(IDENTITY, "downlink", 1),
                    connection_id=guardian_connection,
                )
                relay = relay_core.ProcessLocalAuthenticatedRelay(
                    _config(frame_count=2), relay_core.RelayAdmissionRegistry()
                )

                with self.assertRaises(relay_core.RelayAdmissionError) as raised:
                    relay.run(
                        device_stream=device_stream,
                        guardian_stream=guardian_stream,
                        device_decision=device_decision,
                        guardian_decision=guardian_decision,
                    )

                self.assertIn("stream_binding_mismatch", raised.exception.reason_code)
                self.assertEqual(device_stream.read_calls + guardian_stream.read_calls, 0)
                self.assertEqual(device_stream.write_calls + guardian_stream.write_calls, 0)
                self.assertTrue(device_stream.closed.is_set())
                self.assertTrue(guardian_stream.closed.is_set())
                self.assertTrue(device_stream.buffers_are_zero())
                self.assertTrue(guardian_stream.buffers_are_zero())

    def test_healthy_pair_reuses_existing_four_worker_bridge(self) -> None:
        registry = relay_core.RelayAdmissionRegistry()

        result, relay, device_stream, guardian_stream = _run_healthy(registry)

        self.assertEqual(result["result"], "PASS")
        self.assertEqual(
            result["forwarding"]["engine"], "existing_call020c_concurrent_bridge"
        )
        self.assertEqual(result["forwarding"]["reader_workers"], 2)
        self.assertEqual(result["forwarding"]["writer_workers"], 2)
        self.assertTrue(result["forwarding"]["independent_direction_queues"])
        self.assertEqual(
            result["forwarding"]["clock_and_deadline"][
                "absolute_frame_cadence_ns"
            ],
            20_000_000,
        )
        self.assertEqual(
            result["forwarding"]["direction_stats"]["uplink"]["frames_forwarded"],
            2,
        )
        self.assertEqual(
            result["forwarding"]["direction_stats"]["downlink"]["frames_forwarded"],
            2,
        )
        self.assertTrue(result["connection_truth"]["both_endpoints_authenticated"])
        self.assertTrue(
            result["connection_truth"]["process_local_full_duplex_completed"]
        )
        self.assertFalse(result["connection_truth"]["reported_connected"])
        self.assertEqual(result["claims"]["tls_stream_security"], "unverified_caller_injected_stream")
        self.assertTrue(device_stream.buffers_are_zero())
        self.assertTrue(guardian_stream.buffers_are_zero())
        self.assertEqual(relay.audit()["state"], "completed")
        self.assertEqual(registry.audit()["state_counts"]["completed"], 1)
        self.assertFalse(_contains_binary(result))

    def test_duplicate_session_admission_is_rejected_and_new_streams_close(self) -> None:
        registry = relay_core.RelayAdmissionRegistry()
        _run_healthy(registry, frame_count=2)
        device_decision, guardian_decision = _decisions(
            device_decision_id="device-decision-duplicate",
            guardian_decision_id="guardian-decision-duplicate",
        )
        duplicate_device = _InjectedTlsStream(
            _wire_frames(IDENTITY, "uplink", 1),
            connection_id=device_decision.binding.connection_id,
        )
        duplicate_guardian = _InjectedTlsStream(
            _wire_frames(IDENTITY, "downlink", 1),
            connection_id=guardian_decision.binding.connection_id,
        )
        duplicate = relay_core.ProcessLocalAuthenticatedRelay(
            _config(frame_count=2), registry
        )

        with self.assertRaises(relay_core.RelayAdmissionError) as raised:
            duplicate.run(
                device_stream=duplicate_device,
                guardian_stream=duplicate_guardian,
                device_decision=device_decision,
                guardian_decision=guardian_decision,
            )

        self.assertEqual(raised.exception.reason_code, "duplicate_session_admission")
        self.assertEqual(duplicate_device.read_calls + duplicate_guardian.read_calls, 0)
        self.assertTrue(duplicate_device.closed.is_set())
        self.assertTrue(duplicate_guardian.closed.is_set())
        self.assertFalse(raised.exception.metadata["reported_connected"])

    def test_session_hijack_and_cross_session_connection_reuse_fail_closed(self) -> None:
        registry = relay_core.RelayAdmissionRegistry()
        _run_healthy(registry, frame_count=2)

        hijack_decisions = _decisions(
            device_connection="hijack-device-connection",
            guardian_connection="hijack-guardian-connection",
            device_decision_id="hijack-device-decision",
            guardian_decision_id="hijack-guardian-decision",
        )
        hijack = relay_core.ProcessLocalAuthenticatedRelay(_config(frame_count=2), registry)
        hijack_device = _InjectedTlsStream(
            connection_id=hijack_decisions[0].binding.connection_id
        )
        hijack_guardian = _InjectedTlsStream(
            connection_id=hijack_decisions[1].binding.connection_id
        )
        with self.assertRaises(relay_core.RelayAdmissionError) as raised_hijack:
            hijack.run(
                device_stream=hijack_device,
                guardian_stream=hijack_guardian,
                device_decision=hijack_decisions[0],
                guardian_decision=hijack_decisions[1],
            )
        self.assertEqual(raised_hijack.exception.reason_code, "session_hijack_attempt")

        other_identity = replace(IDENTITY, session_id="call020i-other-session")
        cross_decisions = _decisions(
            other_identity,
            device_connection="device-connection-001",
            guardian_connection="other-guardian-connection",
            device_decision_id="other-device-decision",
            guardian_decision_id="other-guardian-decision",
        )
        cross = relay_core.ProcessLocalAuthenticatedRelay(
            _config(other_identity, frame_count=2), registry
        )
        cross_device = _InjectedTlsStream(
            connection_id=cross_decisions[0].binding.connection_id
        )
        cross_guardian = _InjectedTlsStream(
            connection_id=cross_decisions[1].binding.connection_id
        )
        with self.assertRaises(relay_core.RelayAdmissionError) as raised_cross:
            cross.run(
                device_stream=cross_device,
                guardian_stream=cross_guardian,
                device_decision=cross_decisions[0],
                guardian_decision=cross_decisions[1],
            )
        self.assertEqual(
            raised_cross.exception.reason_code, "cross_session_connection_reuse"
        )
        for stream in (
            hijack_device,
            hijack_guardian,
            cross_device,
            cross_guardian,
        ):
            self.assertTrue(stream.closed.is_set())
            self.assertEqual(stream.read_calls + stream.write_calls, 0)

    def test_duplicate_connection_or_decision_inside_pair_fails_pre_io(self) -> None:
        for label, decisions, reason in (
            (
                "connection",
                _decisions(guardian_connection="device-connection-001"),
                "duplicate_endpoint_connection",
            ),
            (
                "decision",
                _decisions(guardian_decision_id="device-decision-001"),
                "duplicate_authentication_decision",
            ),
        ):
            with self.subTest(label=label):
                device_stream = _InjectedTlsStream(
                    connection_id=decisions[0].binding.connection_id
                )
                guardian_stream = _InjectedTlsStream(
                    connection_id=decisions[1].binding.connection_id
                )
                relay = relay_core.ProcessLocalAuthenticatedRelay(
                    _config(frame_count=2), relay_core.RelayAdmissionRegistry()
                )
                with self.assertRaises(relay_core.RelayAdmissionError) as raised:
                    relay.run(
                        device_stream=device_stream,
                        guardian_stream=guardian_stream,
                        device_decision=decisions[0],
                        guardian_decision=decisions[1],
                    )
                self.assertEqual(raised.exception.reason_code, reason)
                self.assertEqual(device_stream.read_calls + guardian_stream.read_calls, 0)
                self.assertTrue(device_stream.closed.is_set())
                self.assertTrue(guardian_stream.closed.is_set())

    def test_endpoint_disconnect_terminates_pair_and_never_reports_connected(self) -> None:
        device_decision, guardian_decision = _decisions()
        device_stream = _InjectedTlsStream(
            connection_id=device_decision.binding.connection_id,
            disconnect_on_read=True,
        )
        guardian_stream = _InjectedTlsStream(
            _wire_frames(IDENTITY, "downlink", 1),
            connection_id=guardian_decision.binding.connection_id,
        )
        registry = relay_core.RelayAdmissionRegistry()
        relay = relay_core.ProcessLocalAuthenticatedRelay(
            _config(frame_count=2), registry
        )

        with self.assertRaises(relay_core.AuthenticatedRelayRunFailed) as raised:
            relay.run(
                device_stream=device_stream,
                guardian_stream=guardian_stream,
                device_decision=device_decision,
                guardian_decision=guardian_decision,
            )

        metadata = raised.exception.metadata
        self.assertEqual(metadata["result"], "FAIL")
        self.assertFalse(metadata["connection_truth"]["process_local_full_duplex_completed"])
        self.assertFalse(metadata["connection_truth"]["reported_connected"])
        self.assertTrue(device_stream.closed.is_set())
        self.assertTrue(guardian_stream.closed.is_set())
        self.assertTrue(device_stream.buffers_are_zero())
        self.assertTrue(guardian_stream.buffers_are_zero())
        self.assertEqual(registry.audit()["state_counts"]["failed"], 1)
        self.assertFalse(_contains_binary(metadata))

    def test_external_cancel_closes_both_streams_and_joins_delegated_workers(self) -> None:
        device_decision, guardian_decision = _decisions()
        device_stream = _InjectedTlsStream(
            connection_id=device_decision.binding.connection_id,
            block_read_until_close=True,
        )
        guardian_stream = _InjectedTlsStream(
            connection_id=guardian_decision.binding.connection_id,
            block_read_until_close=True,
        )
        registry = relay_core.RelayAdmissionRegistry()
        relay = relay_core.ProcessLocalAuthenticatedRelay(
            _config(frame_count=2), registry
        )
        failures: list[Exception] = []

        def run() -> None:
            try:
                relay.run(
                    device_stream=device_stream,
                    guardian_stream=guardian_stream,
                    device_decision=device_decision,
                    guardian_decision=guardian_decision,
                )
            except Exception as error:
                failures.append(error)

        thread = threading.Thread(target=run)
        thread.start()
        self.assertTrue(device_stream.read_entered.wait(1.0))
        self.assertTrue(guardian_stream.read_entered.wait(1.0))

        relay.request_cancel()
        thread.join(1.0)

        self.assertFalse(thread.is_alive())
        self.assertEqual(len(failures), 1)
        self.assertIsInstance(failures[0], relay_core.AuthenticatedRelayRunFailed)
        self.assertFalse(failures[0].metadata["connection_truth"]["reported_connected"])
        self.assertTrue(device_stream.closed.is_set())
        self.assertTrue(guardian_stream.closed.is_set())
        self.assertTrue(device_stream.buffers_are_zero())
        self.assertTrue(guardian_stream.buffers_are_zero())
        self.assertTrue(relay.audit()["cancel_requested"])
        self.assertEqual(registry.audit()["state_counts"]["cancelled"], 1)

    def test_concurrent_second_run_closes_only_new_streams_and_preserves_running_state(self) -> None:
        device_decision, guardian_decision = _decisions()
        first_device = _InjectedTlsStream(
            connection_id=device_decision.binding.connection_id,
            block_read_until_close=True,
        )
        first_guardian = _InjectedTlsStream(
            connection_id=guardian_decision.binding.connection_id,
            block_read_until_close=True,
        )
        relay = relay_core.ProcessLocalAuthenticatedRelay(
            _config(frame_count=2), relay_core.RelayAdmissionRegistry()
        )
        first_failures: list[Exception] = []

        def first_run() -> None:
            try:
                relay.run(
                    device_stream=first_device,
                    guardian_stream=first_guardian,
                    device_decision=device_decision,
                    guardian_decision=guardian_decision,
                )
            except Exception as error:
                first_failures.append(error)

        thread = threading.Thread(target=first_run)
        thread.start()
        self.assertTrue(first_device.read_entered.wait(1.0))
        self.assertTrue(first_guardian.read_entered.wait(1.0))
        second_device = _InjectedTlsStream(connection_id="second-device-stream")
        second_guardian = _InjectedTlsStream(connection_id="second-guardian-stream")

        with self.assertRaises(relay_core.RelayAdmissionError) as raised:
            relay.run(
                device_stream=second_device,
                guardian_stream=second_guardian,
                device_decision=device_decision,
                guardian_decision=guardian_decision,
            )

        self.assertEqual(raised.exception.reason_code, "relay_instance_is_single_use")
        self.assertEqual(relay.audit()["state"], "running")
        self.assertTrue(second_device.closed.is_set())
        self.assertTrue(second_guardian.closed.is_set())
        self.assertFalse(first_device.closed.is_set())
        self.assertFalse(first_guardian.closed.is_set())

        same_new_stream = _InjectedTlsStream(connection_id="same-new-stream")
        with self.assertRaises(relay_core.RelayAdmissionError) as same_raised:
            relay.run(
                device_stream=same_new_stream,
                guardian_stream=same_new_stream,
                device_decision=device_decision,
                guardian_decision=guardian_decision,
            )
        self.assertEqual(
            same_raised.exception.reason_code, "relay_instance_is_single_use"
        )
        self.assertEqual(relay.audit()["state"], "running")
        self.assertTrue(same_new_stream.closed.is_set())

        relay.request_cancel()
        thread.join(1.0)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(first_failures), 1)
        self.assertEqual(relay.audit()["state"], "cancelled")

    def test_registry_capacity_is_bounded_and_non_evicting(self) -> None:
        registry = relay_core.RelayAdmissionRegistry(max_sessions=1)
        _run_healthy(registry, frame_count=2)
        other_identity = replace(IDENTITY, session_id="capacity-other-session")
        decisions = _decisions(
            other_identity,
            device_connection="capacity-device-2",
            guardian_connection="capacity-guardian-2",
            device_decision_id="capacity-device-decision-2",
            guardian_decision_id="capacity-guardian-decision-2",
        )
        relay = relay_core.ProcessLocalAuthenticatedRelay(
            _config(other_identity, frame_count=2), registry
        )
        device_stream = _InjectedTlsStream(
            connection_id=decisions[0].binding.connection_id
        )
        guardian_stream = _InjectedTlsStream(
            connection_id=decisions[1].binding.connection_id
        )

        with self.assertRaises(relay_core.RelayAdmissionError) as raised:
            relay.run(
                device_stream=device_stream,
                guardian_stream=guardian_stream,
                device_decision=decisions[0],
                guardian_decision=decisions[1],
            )

        self.assertEqual(
            raised.exception.reason_code, "admission_registry_capacity_exhausted"
        )
        self.assertEqual(registry.audit()["session_count"], 1)
        self.assertTrue(registry.audit()["non_evicting_duplicate_guard"])
        self.assertTrue(device_stream.closed.is_set())
        self.assertTrue(guardian_stream.closed.is_set())

    def test_audits_and_failures_are_metadata_only_and_redacted(self) -> None:
        registry = relay_core.RelayAdmissionRegistry()
        result, relay, _, _ = _run_healthy(registry, frame_count=2)
        relay_audit = relay.audit()
        registry_audit = registry.audit()
        values = (result, relay_audit, registry_audit)
        serialized = json.dumps(values, sort_keys=True, allow_nan=False)

        self.assertFalse(_contains_binary(values))
        for identity_value in (
            IDENTITY.session_id,
            IDENTITY.device_id,
            IDENTITY.guardian_id,
            IDENTITY.uplink_clock_id,
            IDENTITY.downlink_clock_id,
            "device-decision-001",
            "guardian-decision-001",
            "device-connection-001",
            "guardian-connection-001",
        ):
            self.assertNotIn(identity_value, serialized)
        self.assertFalse(result["privacy"]["media_recorded"])
        self.assertFalse(result["privacy"]["media_persisted"])
        self.assertFalse(result["privacy"]["media_logged"])
        self.assertTrue(
            result["privacy"][
                "raw_routing_ids_retained_in_process_for_duplicate_guard"
            ]
        )
        self.assertTrue(
            registry_audit[
                "raw_routing_ids_retained_in_process_for_duplicate_guard"
            ]
        )
        self.assertFalse(registry_audit["identity_values_exposed"])
        self.assertFalse(registry_audit["identity_values_logged_or_persisted"])
        self.assertTrue(
            relay_audit[
                "raw_routing_ids_retained_in_process_for_duplicate_guard"
            ]
        )

    def test_module_has_no_network_listener_connector_secret_or_message_hub(self) -> None:
        source = Path("pc_simulator/ego_call_authenticated_relay.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("import socket", source)
        self.assertNotIn("import ssl", source)
        self.assertNotIn("MessageHub", source)
        self.assertNotIn("message_hub", source)
        self.assertNotIn("listen(", source)
        self.assertNotIn("accept(", source)
        self.assertNotIn("socket(", source)
        self.assertNotIn("connect(", source)
        self.assertNotIn("password", source.lower())
        self.assertNotIn("private_key", source.lower())
        self.assertNotIn("bearer", source.lower())
        self.assertNotIn("def main(", source)
        self.assertIn("ConcurrentDuplexMediaBridge", source)
        self.assertIn("complete_eglm_frames_only", source)


def _contains_binary(value: object) -> bool:
    if isinstance(value, (bytes, bytearray, memoryview)):
        return True
    if isinstance(value, dict):
        return any(_contains_binary(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_binary(item) for item in value)
    return False


if __name__ == "__main__":
    unittest.main()

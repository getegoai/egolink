from __future__ import annotations

import json
import threading
import time
import unittest
from array import array
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

from pc_simulator import ego_call_authenticated_relay as relay_core
from pc_simulator import ego_call_concurrent_bridge as concurrent
from pc_simulator import ego_call_media_io as media_io
from pc_simulator import ego_call_tls_stream_adapter as tls_adapter


IDENTITY = media_io.EndpointIdentity(
    session_id="call020j-session",
    device_id="call020j-device",
    guardian_id="call020j-guardian",
    uplink_clock_id="call020j-device-clock",
    downlink_clock_id="call020j-guardian-clock",
)
ALPN = tls_adapter.DEFAULT_ALPN


class _FakeConnectedTlsSocket:
    """No-network TLS-socket-shaped fixture with bounded scripted callbacks."""

    def __init__(
        self,
        *,
        connection_id: str,
        incoming: bytearray | None = None,
        recv_actions: list[object] | None = None,
        send_actions: list[object] | None = None,
        alpn: str | None = ALPN,
        tls_version: str | None = "TLSv1.3",
        timeout_seconds: float | None = 0.001,
    ) -> None:
        self.connection_id = connection_id
        self.incoming = incoming if incoming is not None else bytearray()
        self.outgoing = bytearray()
        self.recv_actions = list(recv_actions or [])
        self.send_actions = list(send_actions or [])
        self.alpn = alpn
        self.tls_version = tls_version
        self.timeout_seconds = timeout_seconds
        self.recv_calls = 0
        self.send_calls = 0
        self.metadata_calls = 0
        self.cancel_calls = 0
        self.close_calls = 0
        self.cancelled = threading.Event()
        self.recv_entered = threading.Event()
        self.send_entered = threading.Event()
        self.retained_recv_buffers: list[bytearray] = []
        self.retained_send_buffers: list[bytearray] = []

    @staticmethod
    def _action(actions: list[object], maximum: int) -> object:
        return actions.pop(0) if actions else maximum

    def recv_into(self, target: memoryview, size: int) -> int:
        self.recv_calls += 1
        self.recv_entered.set()
        self.retained_recv_buffers.append(target.obj)
        action = self._action(self.recv_actions, min(size, len(self.incoming)))
        if action == "block":
            self.cancelled.wait(1.0)
            raise tls_adapter.InjectedTlsSocketTimeout(
                "cancelled blocking receive", progress=None
            )
        if isinstance(action, BaseException):
            raise action
        if type(action) is not int:
            raise AssertionError("invalid receive fixture action")
        count = action
        if count > 0:
            copied = min(count, size, len(self.incoming))
            target[:copied] = self.incoming[:copied]
            self.incoming[:copied] = b"\x00" * copied
            del self.incoming[:copied]
        return count

    def send(self, source: memoryview) -> int:
        self.send_calls += 1
        self.send_entered.set()
        self.retained_send_buffers.append(source.obj)
        action = self._action(self.send_actions, len(source))
        if action == "block":
            self.cancelled.wait(1.0)
            raise tls_adapter.InjectedTlsSocketTimeout(
                "cancelled blocking send", progress=None
            )
        if isinstance(action, BaseException):
            raise action
        if type(action) is not int:
            raise AssertionError("invalid send fixture action")
        if action > 0:
            self.outgoing.extend(source[: min(action, len(source))])
        return action

    def gettimeout(self) -> float | None:
        self.metadata_calls += 1
        return self.timeout_seconds

    def selected_alpn_protocol(self) -> str | None:
        self.metadata_calls += 1
        return self.alpn

    def version(self) -> str | None:
        self.metadata_calls += 1
        return self.tls_version

    def cancel_pending_io(self) -> None:
        self.cancel_calls += 1
        self.cancelled.set()

    def close(self) -> None:
        self.close_calls += 1
        self.cancelled.set()
        self.incoming[:] = b"\x00" * len(self.incoming)
        self.outgoing[:] = b"\x00" * len(self.outgoing)

    def retained_adapter_buffers_are_zero(self) -> bool:
        return all(
            all(value == 0 for value in buffer)
            for buffer in self.retained_recv_buffers + self.retained_send_buffers
        )


def _binding(role: str, connection_id: str) -> relay_core.RelayEndpointBinding:
    if role == "device":
        return relay_core.RelayEndpointBinding(
            session_id=IDENTITY.session_id,
            role="device",
            endpoint_id=IDENTITY.device_id,
            peer_endpoint_id=IDENTITY.guardian_id,
            source_clock_id=IDENTITY.uplink_clock_id,
            connection_id=connection_id,
        )
    return relay_core.RelayEndpointBinding(
        session_id=IDENTITY.session_id,
        role="guardian",
        endpoint_id=IDENTITY.guardian_id,
        peer_endpoint_id=IDENTITY.device_id,
        source_clock_id=IDENTITY.downlink_clock_id,
        connection_id=connection_id,
    )


def _decision(
    role: str,
    connection_id: str,
    *,
    authenticated: bool = True,
) -> relay_core.ExternalAuthenticationDecision:
    now = time.monotonic_ns()
    return relay_core.ExternalAuthenticationDecision(
        decision_id=f"call020j-{role}-decision",
        authenticated=authenticated,
        binding=_binding(role, connection_id),
        valid_from_monotonic_ns=now - 1_000_000,
        expires_at_monotonic_ns=now + 5_000_000_000,
    )


def _attestation(
    role: str,
    connection_id: str,
) -> tls_adapter.InjectedTlsConnectionAttestation:
    return tls_adapter.InjectedTlsConnectionAttestation(
        handshake_complete=True,
        certificate_chain_verified=True,
        peer_identity_verified=True,
        peer_identity=(IDENTITY.device_id if role == "device" else IDENTITY.guardian_id),
        selected_alpn=ALPN,
        tls_version="TLSv1.3",
        connection_id=connection_id,
    )


def _config(
    role: str,
    *,
    enabled: bool = True,
    max_socket_calls: int = 4_096,
) -> tls_adapter.ConnectedTlsStreamConfig:
    return tls_adapter.ConnectedTlsStreamConfig(
        identity=IDENTITY,
        role=role,
        enabled=enabled,
        max_socket_calls_per_operation=max_socket_calls,
    )


def _stream(
    role: str = "device",
    *,
    socket: _FakeConnectedTlsSocket | None = None,
    connection_id: str | None = None,
    attestation: tls_adapter.InjectedTlsConnectionAttestation | None = None,
    decision: relay_core.ExternalAuthenticationDecision | None = None,
    config: tls_adapter.ConnectedTlsStreamConfig | None = None,
) -> tuple[
    tls_adapter.ConnectedTlsOrderedByteStream,
    _FakeConnectedTlsSocket,
]:
    actual_connection = connection_id or f"call020j-{role}-connection"
    fake = socket or _FakeConnectedTlsSocket(connection_id=actual_connection)
    stream = tls_adapter.ConnectedTlsOrderedByteStream(
        fake,
        attestation or _attestation(role, actual_connection),
        decision or _decision(role, actual_connection),
        config or _config(role),
    )
    return stream, fake


def _wire_frames(direction: str, count: int) -> bytearray:
    aggregate = bytearray()
    config = media_io.MediaIoConfig(
        identity=IDENTITY,
        frame_count=count,
        max_cycles=count,
    )
    for sequence in range(count):
        frame = media_io._make_frame(config, direction, sequence)
        wire = media_io.FrameCodec.encode(frame)
        try:
            aggregate.extend(wire)
        finally:
            media_io._zero(wire)
            frame.dispose()
    return aggregate


def _contains_binary(value: object) -> bool:
    if isinstance(value, (bytes, bytearray, memoryview)):
        return True
    if isinstance(value, dict):
        return any(_contains_binary(item) for item in value.values())
    if isinstance(value, (tuple, list)):
        return any(_contains_binary(item) for item in value)
    return False


class EgoCallTlsStreamAdapterTests(unittest.TestCase):
    def test_default_disabled_does_not_query_or_use_media_and_closes_socket(self) -> None:
        connection_id = "call020j-disabled-connection"
        fake = _FakeConnectedTlsSocket(connection_id=connection_id)

        with self.assertRaises(tls_adapter.TlsStreamAdmissionError) as raised:
            tls_adapter.ConnectedTlsOrderedByteStream(
                fake,
                _attestation("device", connection_id),
                _decision("device", connection_id),
                _config("device", enabled=False),
            )

        self.assertEqual(raised.exception.reason_code, "tls_stream_adapter_disabled")
        self.assertEqual(fake.metadata_calls, 0)
        self.assertEqual(fake.recv_calls + fake.send_calls, 0)
        self.assertEqual((fake.cancel_calls, fake.close_calls), (1, 1))
        self.assertEqual(raised.exception.metadata["cancel_errors"], 0)
        self.assertEqual(raised.exception.metadata["close_errors"], 0)

    def test_invalid_enabled_config_closes_socket_without_media(self) -> None:
        connection_id = "call020j-invalid-config-connection"
        fake = _FakeConnectedTlsSocket(connection_id=connection_id)
        invalid_config = replace(_config("device"), per_call_timeout_ms=0)

        with self.assertRaises(tls_adapter.TlsStreamAdmissionError) as raised:
            tls_adapter.ConnectedTlsOrderedByteStream(
                fake,
                _attestation("device", connection_id),
                _decision("device", connection_id),
                invalid_config,
            )

        self.assertEqual(
            raised.exception.reason_code,
            "tls_stream_attestation_or_socket_invalid",
        )
        self.assertEqual(fake.metadata_calls, 0)
        self.assertEqual(fake.recv_calls + fake.send_calls, 0)
        self.assertEqual((fake.cancel_calls, fake.close_calls), (1, 1))

    def test_attestation_is_frozen_and_contains_no_certificate_material(self) -> None:
        attestation = _attestation("device", "call020j-frozen-connection")
        with self.assertRaises(FrozenInstanceError):
            attestation.peer_identity = "mutated"  # type: ignore[misc]
        values = vars(attestation)
        self.assertFalse(_contains_binary(values))
        for forbidden_field in (
            "certificate_bytes",
            "certificate_pem",
            "certificate_der",
            "private_key",
            "credential",
            "token",
        ):
            self.assertNotIn(forbidden_field, values)

    def test_healthy_short_reads_and_writes_are_exact_and_bounded(self) -> None:
        fake = _FakeConnectedTlsSocket(
            connection_id="call020j-device-connection",
            incoming=bytearray(b"abcdef"),
            recv_actions=[2, 1, 3],
            send_actions=[1, 2, 3],
        )
        stream, _ = _stream(socket=fake, connection_id=fake.connection_id)

        received = stream.read_exact(6, timeout_steps=10)
        self.assertEqual(received, bytearray(b"abcdef"))
        outgoing = bytearray(b"uvwxyz")
        stream.write_all(memoryview(outgoing), timeout_steps=10)
        self.assertEqual(fake.outgoing, outgoing)
        self.assertTrue(
            all(all(value == 0 for value in item) for item in fake.retained_send_buffers)
        )
        audit = stream.audit()
        self.assertEqual((audit["read_operations"], audit["write_operations"]), (1, 1))
        self.assertEqual((audit["read_bytes"], audit["written_bytes"]), (6, 6))
        media_io._zero(received)
        media_io._zero(outgoing)
        stream.close()
        self.assertTrue(fake.retained_adapter_buffers_are_zero())

    def test_admission_rejects_unverified_attestation_and_closes_claimed_socket(self) -> None:
        connection_id = "call020j-unverified-connection"
        base = _attestation("device", connection_id)
        for label, attestation in (
            ("handshake", replace(base, handshake_complete=False)),
            ("chain", replace(base, certificate_chain_verified=False)),
            ("peer", replace(base, peer_identity_verified=False)),
        ):
            with self.subTest(label=label):
                fake = _FakeConnectedTlsSocket(connection_id=connection_id)
                with self.assertRaises(tls_adapter.TlsStreamAdmissionError) as raised:
                    tls_adapter.ConnectedTlsOrderedByteStream(
                        fake,
                        attestation,
                        _decision("device", connection_id),
                        _config("device"),
                    )
                self.assertEqual(
                    raised.exception.reason_code,
                    "tls_certificate_or_peer_not_verified",
                )
                self.assertEqual(fake.recv_calls + fake.send_calls, 0)
                self.assertEqual((fake.cancel_calls, fake.close_calls), (1, 1))
                self.assertFalse(raised.exception.metadata["media_io_started"])

    def test_exact_peer_alpn_version_connection_and_session_binding_is_pre_io(self) -> None:
        connection_id = "call020j-binding-connection"
        cases: tuple[tuple[str, object, object, object, str], ...] = (
            (
                "peer",
                _FakeConnectedTlsSocket(connection_id=connection_id),
                replace(_attestation("device", connection_id), peer_identity="other-device"),
                _decision("device", connection_id),
                "tls_attested_peer_identity_mismatch",
            ),
            (
                "attested-alpn",
                _FakeConnectedTlsSocket(connection_id=connection_id),
                replace(_attestation("device", connection_id), selected_alpn="other-alpn"),
                _decision("device", connection_id),
                "tls_attested_alpn_mismatch",
            ),
            (
                "socket-alpn",
                _FakeConnectedTlsSocket(connection_id=connection_id, alpn="other-alpn"),
                _attestation("device", connection_id),
                _decision("device", connection_id),
                "tls_socket_alpn_mismatch",
            ),
            (
                "version",
                _FakeConnectedTlsSocket(connection_id=connection_id, tls_version="TLSv1.2"),
                _attestation("device", connection_id),
                _decision("device", connection_id),
                "tls_socket_version_mismatch",
            ),
            (
                "attested-connection",
                _FakeConnectedTlsSocket(connection_id=connection_id),
                replace(_attestation("device", connection_id), connection_id="other-connection"),
                _decision("device", connection_id),
                "tls_attestation_connection_mismatch",
            ),
            (
                "socket-connection",
                _FakeConnectedTlsSocket(connection_id="other-socket-connection"),
                _attestation("device", connection_id),
                _decision("device", connection_id),
                "tls_stream_session_binding_mismatch",
            ),
            (
                "decision-session",
                _FakeConnectedTlsSocket(connection_id=connection_id),
                _attestation("device", connection_id),
                replace(
                    _decision("device", connection_id),
                    binding=replace(
                        _binding("device", connection_id),
                        session_id="other-session",
                    ),
                ),
                "tls_stream_session_binding_mismatch",
            ),
            (
                "decision-clock",
                _FakeConnectedTlsSocket(connection_id=connection_id),
                _attestation("device", connection_id),
                replace(
                    _decision("device", connection_id),
                    binding=replace(
                        _binding("device", connection_id),
                        source_clock_id="other-clock",
                    ),
                ),
                "tls_stream_session_binding_mismatch",
            ),
        )
        for label, socket, attestation, decision, reason in cases:
            with self.subTest(label=label):
                fake = socket
                with self.assertRaises(tls_adapter.TlsStreamAdmissionError) as raised:
                    tls_adapter.ConnectedTlsOrderedByteStream(
                        fake,
                        attestation,
                        decision,
                        _config("device"),
                    )
                self.assertEqual(raised.exception.reason_code, reason)
                self.assertEqual(fake.recv_calls + fake.send_calls, 0)
                self.assertEqual((fake.cancel_calls, fake.close_calls), (1, 1))

    def test_decision_must_be_current_and_authenticated(self) -> None:
        connection_id = "call020j-decision-connection"
        now = time.monotonic_ns()
        expired = replace(
            _decision("device", connection_id),
            valid_from_monotonic_ns=now - 2_000_000,
            expires_at_monotonic_ns=now - 1_000_000,
        )
        cases = (
            (expired, "tls_attestation_or_authentication_decision_invalid"),
            (
                _decision("device", connection_id, authenticated=False),
                "external_authentication_rejected",
            ),
        )
        for decision, reason in cases:
            fake = _FakeConnectedTlsSocket(connection_id=connection_id)
            with self.assertRaises(tls_adapter.TlsStreamAdmissionError) as raised:
                tls_adapter.ConnectedTlsOrderedByteStream(
                    fake,
                    _attestation("device", connection_id),
                    decision,
                    _config("device"),
                )
            self.assertEqual(raised.exception.reason_code, reason)
            self.assertEqual((fake.cancel_calls, fake.close_calls), (1, 1))

    def test_socket_timeout_must_be_positive_finite_and_within_slice(self) -> None:
        for timeout_value in (None, 0.0, float("inf"), 0.021):
            with self.subTest(timeout=timeout_value):
                connection_id = "call020j-timeout-connection"
                fake = _FakeConnectedTlsSocket(
                    connection_id=connection_id,
                    timeout_seconds=timeout_value,
                )
                with self.assertRaises(tls_adapter.TlsStreamAdmissionError) as raised:
                    tls_adapter.ConnectedTlsOrderedByteStream(
                        fake,
                        _attestation("device", connection_id),
                        _decision("device", connection_id),
                        _config("device"),
                    )
                self.assertEqual(
                    raised.exception.reason_code,
                    "tls_socket_timeout_is_not_finite_and_bounded",
                )
                self.assertEqual((fake.cancel_calls, fake.close_calls), (1, 1))

    def test_zero_progress_receive_timeout_is_retryable_but_partial_is_terminal(self) -> None:
        for label, action in (
            ("explicit", tls_adapter.InjectedTlsSocketTimeout("zero", progress=0)),
            ("plain", TimeoutError("socket receive timeout")),
        ):
            with self.subTest(zero_timeout=label):
                zero_fake = _FakeConnectedTlsSocket(
                    connection_id=f"call020j-zero-{label}-read",
                    recv_actions=[action],
                )
                zero_stream, _ = _stream(
                    socket=zero_fake, connection_id=zero_fake.connection_id
                )
                with self.assertRaises(media_io.MediaIoTimeout) as zero_raised:
                    zero_stream.read_exact(4, timeout_steps=2)
                self.assertTrue(zero_raised.exception.retry_safe)
                self.assertEqual(zero_stream.audit()["state"], "ready")
                self.assertTrue(zero_fake.retained_adapter_buffers_are_zero())
                zero_stream.close()

        partial_fake = _FakeConnectedTlsSocket(
            connection_id="call020j-partial-read",
            incoming=bytearray(b"ab"),
            recv_actions=[2, tls_adapter.InjectedTlsSocketTimeout("zero", progress=0)],
        )
        partial_stream, _ = _stream(
            socket=partial_fake, connection_id=partial_fake.connection_id
        )
        with self.assertRaises(media_io.MediaIoTimeout) as partial_raised:
            partial_stream.read_exact(4, timeout_steps=2)
        self.assertFalse(partial_raised.exception.retry_safe)
        self.assertEqual(partial_stream.audit()["state"], "terminal")
        self.assertTrue(partial_fake.retained_adapter_buffers_are_zero())
        partial_stream.close()

    def test_receive_eof_and_unknown_progress_are_terminal_and_clear_buffer(self) -> None:
        for label, action in (
            ("eof", 0),
            (
                "unknown",
                tls_adapter.InjectedTlsSocketTimeout("unknown", progress=None),
            ),
        ):
            with self.subTest(label=label):
                fake = _FakeConnectedTlsSocket(
                    connection_id=f"call020j-{label}-read",
                    recv_actions=[action],
                )
                stream, _ = _stream(socket=fake, connection_id=fake.connection_id)
                with self.assertRaises(media_io.MediaIoError):
                    stream.read_exact(8, timeout_steps=2)
                self.assertEqual(stream.audit()["state"], "terminal")
                self.assertTrue(fake.retained_adapter_buffers_are_zero())
                stream.close()

    def test_send_timeout_progress_rules_and_zero_return_fail_closed(self) -> None:
        cases = (
            (
                "zero-explicit",
                [tls_adapter.InjectedTlsSocketTimeout("zero", progress=0)],
                True,
            ),
            (
                "unknown-explicit",
                [tls_adapter.InjectedTlsSocketTimeout("unknown", progress=None)],
                False,
            ),
            ("plain-timeout", [TimeoutError("unknown TLS send progress")], False),
            ("zero-return", [0], False),
            (
                "partial-then-timeout",
                [2, tls_adapter.InjectedTlsSocketTimeout("zero", progress=0)],
                False,
            ),
        )
        for label, actions, retry_safe in cases:
            with self.subTest(label=label):
                fake = _FakeConnectedTlsSocket(
                    connection_id=f"call020j-{label}-write",
                    send_actions=actions,
                )
                stream, _ = _stream(socket=fake, connection_id=fake.connection_id)
                payload = bytearray(b"abcdef")
                with self.assertRaises(media_io.MediaIoError) as raised:
                    stream.write_all(memoryview(payload), timeout_steps=2)
                if isinstance(raised.exception, media_io.MediaIoTimeout):
                    self.assertEqual(raised.exception.retry_safe, retry_safe)
                else:
                    self.assertFalse(retry_safe)
                self.assertTrue(fake.retained_adapter_buffers_are_zero())
                self.assertEqual(
                    stream.audit()["state"], "ready" if retry_safe else "terminal"
                )
                media_io._zero(payload)
                stream.close()

    def test_callback_count_and_transfer_size_are_bounded(self) -> None:
        fake = _FakeConnectedTlsSocket(
            connection_id="call020j-callback-bound",
            incoming=bytearray(b"ab"),
            recv_actions=[1, 1],
        )
        stream, _ = _stream(
            socket=fake,
            connection_id=fake.connection_id,
            config=_config("device", max_socket_calls=1),
        )
        with self.assertRaises(media_io.MediaIoTimeout) as raised:
            stream.read_exact(2, timeout_steps=2)
        self.assertFalse(raised.exception.retry_safe)
        self.assertEqual(fake.recv_calls, 1)
        self.assertTrue(fake.retained_adapter_buffers_are_zero())
        stream.close()

        bounded, _ = _stream(connection_id="call020j-transfer-bound")
        with self.assertRaises(media_io.MediaIoError):
            bounded.read_exact(tls_adapter.MAX_TRANSFER_BYTES + 1, timeout_steps=1)
        oversized = bytearray(tls_adapter.MAX_TRANSFER_BYTES + 1)
        with self.assertRaises(media_io.MediaIoError):
            bounded.write_all(memoryview(oversized), timeout_steps=1)
        media_io._zero(oversized)
        bounded.close()

    def test_multibyte_memoryview_is_rejected_before_owned_copy_or_send(self) -> None:
        stream, fake = _stream(connection_id="call020j-multibyte-view")
        values = array("I", [1] * 2_000)
        view = memoryview(values)
        self.assertGreater(view.nbytes, tls_adapter.MAX_TRANSFER_BYTES)

        with self.assertRaises(media_io.MediaIoError):
            stream.write_all(view, timeout_steps=1)

        self.assertEqual(fake.send_calls, 0)
        self.assertEqual(fake.retained_send_buffers, [])
        view.release()
        stream.close()

    def test_connection_identity_change_after_admission_is_terminal_pre_io(self) -> None:
        stream, fake = _stream(connection_id="call020j-stable-connection")
        fake.connection_id = "call020j-replaced-connection"

        with self.assertRaises(media_io.MediaIoProtocolError):
            stream.read_exact(1, timeout_steps=1)

        self.assertEqual(fake.recv_calls, 0)
        self.assertEqual(stream.audit()["state"], "terminal")
        stream.close()

    def test_close_cancels_and_waits_for_blocking_receive_and_send_cleanup(self) -> None:
        fake = _FakeConnectedTlsSocket(
            connection_id="call020j-blocking-close",
            recv_actions=["block"],
            send_actions=["block"],
        )
        stream, _ = _stream(socket=fake, connection_id=fake.connection_id)
        failures: list[Exception] = []
        payload = bytearray(b"bounded-media")

        def reader() -> None:
            try:
                stream.read_exact(16, timeout_steps=50)
            except Exception as error:
                failures.append(error)

        def writer() -> None:
            try:
                stream.write_all(memoryview(payload), timeout_steps=50)
            except Exception as error:
                failures.append(error)

        read_thread = threading.Thread(target=reader)
        write_thread = threading.Thread(target=writer)
        read_thread.start()
        write_thread.start()
        self.assertTrue(fake.recv_entered.wait(1.0))
        self.assertTrue(fake.send_entered.wait(1.0))

        stream.close()

        read_thread.join(1.0)
        write_thread.join(1.0)
        self.assertFalse(read_thread.is_alive())
        self.assertFalse(write_thread.is_alive())
        self.assertEqual(len(failures), 2)
        self.assertEqual((fake.cancel_calls, fake.close_calls), (1, 1))
        self.assertTrue(fake.retained_adapter_buffers_are_zero())
        audit = stream.audit()
        self.assertTrue(audit["sensitive_references_cleared"])
        self.assertTrue(audit["socket_reference_cleared"])
        self.assertTrue(audit["session_config_reference_cleared"])
        with self.assertRaises(media_io.MediaIoError):
            _ = stream.connection_id
        media_io._zero(payload)

    def test_two_adapters_feed_authenticated_relay_without_real_network(self) -> None:
        frame_count = 2
        device_connection = "call020j-relay-device-connection"
        guardian_connection = "call020j-relay-guardian-connection"
        device_decision = _decision("device", device_connection)
        guardian_decision = _decision("guardian", guardian_connection)
        device_socket = _FakeConnectedTlsSocket(
            connection_id=device_connection,
            incoming=_wire_frames("uplink", frame_count),
        )
        guardian_socket = _FakeConnectedTlsSocket(
            connection_id=guardian_connection,
            incoming=_wire_frames("downlink", frame_count),
        )
        device_stream = tls_adapter.ConnectedTlsOrderedByteStream(
            device_socket,
            _attestation("device", device_connection),
            device_decision,
            _config("device"),
        )
        guardian_stream = tls_adapter.ConnectedTlsOrderedByteStream(
            guardian_socket,
            _attestation("guardian", guardian_connection),
            guardian_decision,
            _config("guardian"),
        )
        relay = relay_core.ProcessLocalAuthenticatedRelay(
            relay_core.AuthenticatedRelayConfig(
                bridge=concurrent.ConcurrentBridgeConfig(
                    identity=IDENTITY,
                    bridge_clock_id="call020j-bridge-clock",
                    frame_count=frame_count,
                    timeout_steps=10,
                    receive_attempts=1,
                    send_attempts=1,
                    max_runtime_ms=2_000,
                    join_timeout_ms=500,
                    frame_deadline_ns=500_000_000,
                )
            ),
            relay_core.RelayAdmissionRegistry(),
        )

        result = relay.run(
            device_stream=device_stream,
            guardian_stream=guardian_stream,
            device_decision=device_decision,
            guardian_decision=guardian_decision,
        )

        self.assertEqual(result["result"], "PASS")
        self.assertEqual(
            result["forwarding"]["engine"],
            "existing_call020c_concurrent_bridge",
        )
        self.assertFalse(result["connection_truth"]["reported_connected"])
        self.assertFalse(_contains_binary(result))
        relay.close()
        self.assertTrue(device_socket.retained_adapter_buffers_are_zero())
        self.assertTrue(guardian_socket.retained_adapter_buffers_are_zero())
        self.assertTrue(device_stream.audit()["sensitive_references_cleared"])
        self.assertTrue(guardian_stream.audit()["sensitive_references_cleared"])

    def test_audit_and_admission_error_are_metadata_only_and_redacted(self) -> None:
        stream, _ = _stream(connection_id="call020j-secret-routing-value")
        audit = stream.audit()
        serialized = json.dumps(audit, sort_keys=True, allow_nan=False)
        self.assertFalse(_contains_binary(audit))
        self.assertNotIn("call020j-secret-routing-value", serialized)
        self.assertNotIn(IDENTITY.session_id, serialized)
        self.assertFalse(audit["media_logged"])
        self.assertFalse(audit["media_persisted"])
        self.assertFalse(audit["certificate_verified_by_adapter"])
        stream.close()

        connection_id = "call020j-redacted-rejection"
        fake = _FakeConnectedTlsSocket(connection_id=connection_id)
        with self.assertRaises(tls_adapter.TlsStreamAdmissionError) as raised:
            tls_adapter.ConnectedTlsOrderedByteStream(
                fake,
                replace(_attestation("device", connection_id), peer_identity="wrong-peer"),
                _decision("device", connection_id),
                _config("device"),
            )
        serialized_error = json.dumps(raised.exception.metadata, sort_keys=True)
        self.assertNotIn(connection_id, serialized_error)
        self.assertNotIn("wrong-peer", serialized_error)
        self.assertFalse(_contains_binary(raised.exception.metadata))

    def test_module_has_no_connector_listener_dns_credentials_media_log_or_main(self) -> None:
        source = Path("pc_simulator/ego_call_tls_stream_adapter.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("import socket", source)
        self.assertNotIn("import ssl", source)
        self.assertNotIn(".connect(", source)
        self.assertNotIn(".listen(", source)
        self.assertNotIn("getaddrinfo", source)
        self.assertNotIn("create_connection", source)
        self.assertNotIn("password", source.lower())
        self.assertNotIn("private_key", source.lower())
        self.assertNotIn("bearer", source.lower())
        self.assertNotIn("logging", source)
        self.assertNotIn("open(", source)
        self.assertNotIn("def main(", source)
        self.assertIn("enabled: bool = False", source)
        self.assertIn("ExternalAuthenticationDecision", source)
        self.assertIn("certificate_verified_by_adapter", source)


if __name__ == "__main__":
    unittest.main()

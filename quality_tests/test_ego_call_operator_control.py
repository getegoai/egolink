from __future__ import annotations

import contextlib
import io
import json
import socket
import ssl
import threading
import time
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import patch

from pc_simulator import ego_call_authenticated_relay as relay
from pc_simulator import ego_call_media_io as media_io
from pc_simulator import ego_call_operator_control as control
from pc_simulator import ego_call_tls_stream_adapter as tls


RUN_ID = "call020m-offline-run-001"
PORT = "CALL020M-EXACT-FAKE-PORT"
TOKEN_BYTES = b"one-shot-offline-token-material"
CALL020N_CA_PEM = """-----BEGIN CERTIFICATE-----
offline-fake-ca-material
-----END CERTIFICATE-----"""


class _Verifier:
    def __init__(self, *, accepted: bool = True) -> None:
        self.accepted = accepted
        self.calls = 0
        self.observed_length = 0

    def authorize_once(
        self,
        *,
        run_id: str,
        action: str,
        token: memoryview,
        timeout_ms: int,
    ) -> bool:
        self.calls += 1
        self.observed_length = len(token)
        if run_id != RUN_ID or action != control.AUTHORIZATION_ACTION:
            return False
        if timeout_ms <= 0:
            return False
        return self.accepted and bytes(token) == TOKEN_BYTES


class _FakeSerialFactory:
    def __init__(self) -> None:
        self.calls = 0

    def open_explicit(self, **_: Any) -> object:
        self.calls += 1
        raise AssertionError("the fake endpoint must not open a serial driver")


class _FixedClock:
    def __init__(self, now_ns: int) -> None:
        self.now_ns = now_ns

    def monotonic_ns(self) -> int:
        return self.now_ns


class _FakeSocket:
    def __init__(self, connection_id: str) -> None:
        self.connection_id = connection_id
        self.cancel_calls = 0
        self.close_calls = 0

    def cancel_pending_io(self) -> None:
        self.cancel_calls += 1

    def close(self) -> None:
        self.close_calls += 1


def _pre_start_telemetry() -> control.RuntimeTelemetrySnapshot:
    return control.RuntimeTelemetrySnapshot(
        phase="pre_start",
        captured_at_monotonic_ns=time.monotonic_ns(),
        free_internal_heap_bytes=96_000,
        minimum_free_internal_heap_bytes=95_000,
        externally_attested_runtime_measurement=True,
    )


def _post_stop_telemetry() -> control.RuntimeTelemetrySnapshot:
    return control.RuntimeTelemetrySnapshot(
        phase="post_stop",
        captured_at_monotonic_ns=time.monotonic_ns(),
        free_internal_heap_bytes=88_000,
        minimum_free_internal_heap_bytes=80_000,
        worker_stack_high_watermark_bytes=(
            ("audio_capture", 1_024),
            ("usb_uplink", 1_100),
            ("usb_downlink", 1_080),
            ("audio_output", 1_040),
        ),
        externally_attested_runtime_measurement=True,
    )


class _FakeWearable:
    def __init__(
        self,
        *,
        wrong_prepare_operation: bool = False,
        raise_during_prepare: bool = False,
        block_start: bool = False,
        close_failures: int = 0,
    ) -> None:
        self.actions: list[str] = []
        self.commands: list[control.ControlCommand] = []
        self.wrong_prepare_operation = wrong_prepare_operation
        self.raise_during_prepare = raise_during_prepare
        self.block_start = block_start
        self.close_failures = close_failures
        self.start_entered = threading.Event()
        self.start_release = threading.Event()

    def _remember(self, command: control.ControlCommand) -> None:
        self.actions.append(command.action)
        self.commands.append(command)

    def prepare(
        self, command: control.ControlCommand
    ) -> control.WearablePreparedSession:
        self._remember(command)
        if self.raise_during_prepare:
            raise RuntimeError("accepted remotely then reply lost")
        return control.WearablePreparedSession(
            run_id=command.run_id,
            operation_id=(
                "wrong-operation"
                if self.wrong_prepare_operation
                else command.operation_id
            ),
            runner_version=control.WEARABLE_RUNNER_VERSION,
            runner_api_version=control.WEARABLE_RUNNER_API_VERSION,
            state="PREPARED",
            session_id="s-call020m-private",
            device_id="d-call020m-private",
            guardian_id="g-call020m-private",
            uplink_clock_id="u-call020m-private",
            downlink_clock_id="v-call020m-private",
            nonce_bits=128,
            correlated_routing_ids=True,
            random_quality="unverified",
            provenance="runtime_ephemeral_generated",
            pre_start_telemetry=_pre_start_telemetry(),
        )

    def _ack(
        self, command: control.ControlCommand, state: str
    ) -> control.WearableControlAck:
        self._remember(command)
        return control.WearableControlAck(
            run_id=command.run_id,
            operation_id=command.operation_id,
            action=command.action,
            accepted=True,
            state=state,
        )

    def start(self, command: control.ControlCommand) -> control.WearableControlAck:
        self.start_entered.set()
        if self.block_start:
            self.start_release.wait(2.0)
        return self._ack(command, "RUNNING")

    def cancel(self, command: control.ControlCommand) -> control.WearableControlAck:
        return self._ack(command, "STOPPING")

    def join(self, command: control.ControlCommand) -> control.WearableControlAck:
        return self._ack(command, "JOINED")

    def close(self, command: control.ControlCommand) -> control.WearableControlAck:
        if self.close_failures > 0:
            self.close_failures -= 1
            self._remember(command)
            raise RuntimeError("transient control close failure")
        return self._ack(command, "CLOSED")

    def telemetry(
        self, command: control.ControlCommand
    ) -> control.RuntimeTelemetrySnapshot:
        self._remember(command)
        return _post_stop_telemetry()


class _FakeTlsConnector:
    def __init__(
        self, *, block_open: bool = False, return_delay_seconds: float = 0.0
    ) -> None:
        self.calls = 0
        self.requests: list[control.TlsOpenRequest] = []
        self.socket: _FakeSocket | None = None
        self.block_open = block_open
        self.return_delay_seconds = return_delay_seconds
        self.open_entered = threading.Event()
        self.open_release = threading.Event()

    def open_verified(
        self, request: control.TlsOpenRequest
    ) -> control.VerifiedTlsOpenResult:
        self.calls += 1
        self.requests.append(request)
        self.open_entered.set()
        if self.block_open:
            self.open_release.wait(2.0)
        connection_id = "call020m-tls-connection-private"
        self.socket = _FakeSocket(connection_id)
        binding = relay.RelayEndpointBinding(
            session_id=request.identity.session_id,
            role="device",
            endpoint_id=request.identity.device_id,
            peer_endpoint_id=request.identity.guardian_id,
            source_clock_id=request.identity.uplink_clock_id,
            connection_id=connection_id,
        )
        now = time.monotonic_ns()
        decision = relay.ExternalAuthenticationDecision(
            decision_id="call020m-auth-decision-private",
            authenticated=True,
            binding=binding,
            valid_from_monotonic_ns=now - 1_000_000,
            expires_at_monotonic_ns=now + 5_000_000_000,
        )
        attestation = tls.InjectedTlsConnectionAttestation(
            handshake_complete=True,
            certificate_chain_verified=True,
            peer_identity_verified=True,
            peer_identity=request.identity.device_id,
            selected_alpn=tls.DEFAULT_ALPN,
            tls_version="TLSv1.3",
            connection_id=connection_id,
        )
        if self.return_delay_seconds:
            time.sleep(self.return_delay_seconds)
        return control.VerifiedTlsOpenResult(
            tls_socket=self.socket,
            tls_attestation=attestation,
            authentication_decision=decision,
        )


class _FakeHostRawSocket:
    def __init__(
        self,
        *,
        fail_connect: bool = False,
        reported_source_ipv4: str | None = None,
        reported_peer: tuple[str, int] | None = None,
    ) -> None:
        self.fail_connect = fail_connect
        self.reported_source_ipv4 = reported_source_ipv4
        self.reported_peer = reported_peer
        self.timeouts: list[float] = []
        self.bound_to: tuple[str, int] | None = None
        self.connected_to: tuple[str, int] | None = None
        self.shutdown_calls = 0
        self.close_calls = 0

    def settimeout(self, value: float) -> None:
        self.timeouts.append(value)

    def bind(self, target: tuple[str, int]) -> None:
        self.bound_to = target

    def connect(self, target: tuple[str, int]) -> None:
        self.connected_to = target
        if self.fail_connect:
            raise OSError("offline injected connect failure")

    def getsockname(self) -> tuple[str, int]:
        if self.bound_to is None:
            raise OSError("offline fake is not bound")
        return (self.reported_source_ipv4 or self.bound_to[0], 49_152)

    def getpeername(self) -> tuple[str, int]:
        if self.connected_to is None:
            raise OSError("offline fake is not connected")
        return self.reported_peer or self.connected_to

    def shutdown(self, _: int) -> None:
        self.shutdown_calls += 1

    def close(self) -> None:
        self.close_calls += 1


class _FakeHostTlsSocket:
    def __init__(
        self,
        raw: _FakeHostRawSocket,
        *,
        fail_handshake: bool = False,
        alpn: str = control.DEFAULT_ALPN,
        tls_version: str = "TLSv1.3",
        peer_certificate: bytes = b"offline-fake-peer-certificate",
        close_failures: int = 0,
    ) -> None:
        self.raw = raw
        self.fail_handshake = fail_handshake
        self.alpn = alpn
        self.tls_version = tls_version
        self.peer_certificate = peer_certificate
        self.close_failures = close_failures
        self.timeout = 5.0
        self.handshake_calls = 0
        self.shutdown_calls = 0
        self.close_calls = 0

    def do_handshake(self) -> None:
        self.handshake_calls += 1
        if self.fail_handshake:
            raise ssl.SSLError("offline injected handshake failure")

    def settimeout(self, value: float) -> None:
        self.timeout = value

    def gettimeout(self) -> float:
        return self.timeout

    def selected_alpn_protocol(self) -> str:
        return self.alpn

    def version(self) -> str:
        return self.tls_version

    def getpeercert(self, *, binary_form: bool = False) -> bytes | dict[str, Any]:
        return self.peer_certificate if binary_form else {}

    def recv_into(self, _: memoryview, __: int) -> int:
        raise AssertionError("CALL-020N offline tests do not read media")

    def send(self, _: memoryview) -> int:
        raise AssertionError("CALL-020N offline tests do not write media")

    def shutdown(self, _: int) -> None:
        self.shutdown_calls += 1

    def close(self) -> None:
        self.close_calls += 1
        if self.close_failures > 0:
            self.close_failures -= 1
            raise OSError("offline injected TLS close failure")
        self.raw.close()


class _FakeHostTlsContext:
    def __init__(
        self,
        tls_socket: _FakeHostTlsSocket,
        *,
        fail_wrap: bool = False,
    ) -> None:
        self.tls_socket = tls_socket
        self.fail_wrap = fail_wrap
        self.check_hostname = False
        self.verify_mode = ssl.CERT_NONE
        self.minimum_version: ssl.TLSVersion | None = None
        self.maximum_version: ssl.TLSVersion | None = None
        self.hostname_checks_common_name = True
        self.options = 0
        self.alpn_protocols: list[str] = []
        self.ca_kwargs: dict[str, object] | None = None
        self.wrap_kwargs: dict[str, object] | None = None

    def set_alpn_protocols(self, protocols: list[str]) -> None:
        self.alpn_protocols = list(protocols)

    def load_verify_locations(self, **kwargs: object) -> None:
        self.ca_kwargs = dict(kwargs)

    def wrap_socket(self, raw: object, **kwargs: object) -> _FakeHostTlsSocket:
        self.wrap_kwargs = dict(kwargs)
        if raw is not self.tls_socket.raw:
            raise AssertionError("unexpected raw socket")
        if self.fail_wrap:
            raise ssl.SSLError("offline injected wrap failure")
        return self.tls_socket


class _FakeHostSocketFactory:
    def __init__(self, raw: _FakeHostRawSocket) -> None:
        self.raw = raw
        self.calls: list[tuple[int, int, int]] = []

    def __call__(self, family: int, kind: int, protocol: int) -> _FakeHostRawSocket:
        self.calls.append((family, kind, protocol))
        return self.raw


class _FakeConnectedSessionAuthenticator:
    def __init__(self, *, wrong_binding: bool = False, invalid_result: bool = False):
        self.wrong_binding = wrong_binding
        self.invalid_result = invalid_result
        self.calls = 0
        self.evidence: control.HostTlsPeerEvidence | None = None

    def authorize_connected_session(
        self,
        *,
        evidence: control.HostTlsPeerEvidence,
        timeout_ms: int,
    ) -> relay.ExternalAuthenticationDecision | object:
        self.calls += 1
        self.evidence = evidence
        if self.invalid_result:
            return object()
        binding = relay.RelayEndpointBinding(
            session_id=evidence.identity.session_id,
            role="device",
            endpoint_id=(
                "different-device"
                if self.wrong_binding
                else evidence.identity.device_id
            ),
            peer_endpoint_id=evidence.identity.guardian_id,
            source_clock_id=evidence.identity.uplink_clock_id,
            connection_id=evidence.connection_id,
        )
        now = time.monotonic_ns()
        return relay.ExternalAuthenticationDecision(
            decision_id="call020n-external-auth-decision",
            authenticated=True,
            binding=binding,
            valid_from_monotonic_ns=now - 1_000_000,
            expires_at_monotonic_ns=now + 5_000_000_000,
        )


class _FakeEndpoint:
    instances: list["_FakeEndpoint"] = []
    block = False
    fail_open = False
    close_failures = 0

    def __init__(self, config: object) -> None:
        self.config = config
        self.open_kwargs: dict[str, Any] | None = None
        self.start_calls = 0
        self.cancel_calls = 0
        self.close_calls = 0
        self.cancelled = threading.Event()
        self.started = threading.Event()
        self.__class__.instances.append(self)

    def open(self, **kwargs: Any) -> None:
        self.open_kwargs = kwargs
        if self.fail_open:
            socket = kwargs["tls_socket"]
            socket.cancel_pending_io()
            socket.close()
            raise RuntimeError("raw fake endpoint failure")

    def start(self) -> dict[str, Any]:
        self.start_calls += 1
        self.started.set()
        if self.block:
            self.cancelled.wait(2.0)
            raise RuntimeError("expected cancellation")
        return {
            "result": "PASS",
            "direction_stats": {
                "uplink": {
                    "frames_expected": 2,
                    "frames_received": 2,
                    "frames_forwarded": 2,
                    "receive_retry_count": 0,
                    "send_retry_count": 0,
                    "backpressure_drops": 0,
                    "deadline_misses_before_send": 0,
                    "deadline_misses_after_send": 0,
                },
                "downlink": {
                    "frames_expected": 2,
                    "frames_received": 2,
                    "frames_forwarded": 2,
                    "receive_retry_count": 0,
                    "send_retry_count": 0,
                    "backpressure_drops": 0,
                    "deadline_misses_before_send": 0,
                    "deadline_misses_after_send": 0,
                },
            },
        }

    def request_cancel(self) -> None:
        self.cancel_calls += 1
        self.cancelled.set()

    def close(self) -> None:
        self.close_calls += 1
        self.cancelled.set()
        if self.__class__.close_failures > 0:
            self.__class__.close_failures -= 1
            raise RuntimeError("transient endpoint close failure")
        if self.open_kwargs is not None:
            socket = self.open_kwargs["tls_socket"]
            socket.cancel_pending_io()
            socket.close()

    def audit(self) -> dict[str, Any]:
        return {"state": "fake"}


def _config(*, enabled: bool = True, plan_only: bool = False) -> control.HostControlConfig:
    return control.HostControlConfig(
        run_id=RUN_ID,
        exact_port=PORT,
        enabled=enabled,
        plan_only=plan_only,
        frame_count=2,
        max_runtime_ms=1_000,
    )


def _authorization() -> tuple[control.OneShotOperatorAuthorization, bytearray]:
    token = bytearray(TOKEN_BYTES)
    return (
        control.OneShotOperatorAuthorization(
            run_id=RUN_ID,
            token=token,
            operator_authorized=True,
            expires_at_monotonic_ns=time.monotonic_ns() + 10_000_000_000,
        ),
        token,
    )


def _wearable_attestation() -> control.WearableControlAttestation:
    return control.WearableControlAttestation(
        runner_version=control.WEARABLE_RUNNER_VERSION,
        runner_api_version=control.WEARABLE_RUNNER_API_VERSION,
        externally_attested=True,
        exact_prepare_start_cancel_join_close=True,
        out_of_band_from_media=True,
        finite_timeout_contract=True,
        runtime_telemetry_supported=True,
        max_operation_timeout_ms=1_000,
    )


def _same_handle_wearable_attestation() -> control.WearableControlAttestation:
    return replace(
        _wearable_attestation(),
        out_of_band_from_media=False,
        logically_separate_and_not_interleaved_with_media=True,
    )


def _tls_attestation() -> control.TlsConnectorAttestation:
    return control.TlsConnectorAttestation(
        externally_attested=True,
        returns_connected_socket_only=True,
        verifies_chain_and_peer_identity=True,
        exact_session_binding=True,
        finite_timeout_contract=True,
        cleans_partial_open_before_raise=True,
        no_credential_or_media_result=True,
    )


def _retained_tls_attestation() -> control.TlsConnectorAttestation:
    return replace(
        _tls_attestation(),
        cleans_partial_open_before_raise=False,
        retains_partial_open_for_bounded_retry=True,
    )


def _host_tls_config(
    *, enabled: bool = True, ca_file: str | None = None
) -> control.HostTlsConnectorConfig:
    return control.HostTlsConnectorConfig(
        peer_ipv4="203.0.113.20",
        peer_port=443,
        source_ipv4="192.0.2.10",
        tls_hostname="relay.egolink.example",
        ca_pem=None if ca_file is not None else CALL020N_CA_PEM,
        ca_file=ca_file,
        enabled=enabled,
        expected_alpn=control.DEFAULT_ALPN,
        overall_timeout_ms=5_000,
        tcp_connect_timeout_ms=1_500,
        handshake_timeout_ms=2_000,
        read_timeout_ms=20,
        write_timeout_ms=40,
        authentication_timeout_ms=1_000,
    )


def _host_tls_request() -> control.TlsOpenRequest:
    return control.TlsOpenRequest(
        run_id=RUN_ID,
        identity=media_io.EndpointIdentity(
            session_id="s-call020n-private",
            device_id="d-call020n-private",
            guardian_id="g-call020n-private",
            uplink_clock_id="u-call020n-private",
            downlink_clock_id="v-call020n-private",
        ),
        expected_alpn=control.DEFAULT_ALPN,
        connect_timeout_ms=5_000,
    )


def _host_tls_fakes(
    *,
    config: control.HostTlsConnectorConfig | None = None,
    raw: _FakeHostRawSocket | None = None,
    tls_socket: _FakeHostTlsSocket | None = None,
    context: _FakeHostTlsContext | None = None,
    authenticator: _FakeConnectedSessionAuthenticator | None = None,
) -> tuple[
    control.DefaultOffHostTlsConnector,
    _FakeHostRawSocket,
    _FakeHostTlsSocket,
    _FakeHostTlsContext,
    _FakeHostSocketFactory,
    _FakeConnectedSessionAuthenticator,
]:
    actual_raw = raw or _FakeHostRawSocket()
    actual_tls = tls_socket or _FakeHostTlsSocket(actual_raw)
    actual_context = context or _FakeHostTlsContext(actual_tls)
    socket_factory = _FakeHostSocketFactory(actual_raw)
    actual_authenticator = authenticator or _FakeConnectedSessionAuthenticator()
    connector = control.DefaultOffHostTlsConnector(
        config or _host_tls_config(),
        authenticator=actual_authenticator,
        socket_factory=socket_factory,
        ssl_context_factory=lambda: actual_context,
        connection_id_factory=lambda: "call020n-private-connection",
    )
    return (
        connector,
        actual_raw,
        actual_tls,
        actual_context,
        socket_factory,
        actual_authenticator,
    )


def _prepared_session(
    *,
    wearable: _FakeWearable | None = None,
    wearable_attestation: control.WearableControlAttestation | None = None,
    tls_connector: control.ExternallyVerifiedTlsConnector | None = None,
    tls_connector_attestation: control.TlsConnectorAttestation | None = None,
) -> tuple[
    control.HostControlSession,
    _FakeWearable,
    control.ExternallyVerifiedTlsConnector,
    _FakeSerialFactory,
]:
    _FakeEndpoint.instances.clear()
    session = control.HostControlSession(
        _config(),
        run_registry=control.RunIdentityRegistry(),
        endpoint_factory=_FakeEndpoint,
    )
    authorization, token = _authorization()
    session.prepare(authorization=authorization, verifier=_Verifier())
    assert all(value == 0 for value in token)
    fake_wearable = wearable or _FakeWearable()
    tls_connector = tls_connector or _FakeTlsConnector()
    serial_factory = _FakeSerialFactory()
    session.preflight(
        wearable_control=fake_wearable,
        wearable_attestation=wearable_attestation or _wearable_attestation(),
        tls_connector=tls_connector,
        tls_connector_attestation=tls_connector_attestation or _tls_attestation(),
        serial_factory=serial_factory,
    )
    return session, fake_wearable, tls_connector, serial_factory


def _contains_binary(value: object) -> bool:
    if isinstance(value, (bytes, bytearray, memoryview)):
        return True
    if isinstance(value, dict):
        return any(_contains_binary(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_binary(item) for item in value)
    return False


class EgoCallOperatorControlTests(unittest.TestCase):
    def tearDown(self) -> None:
        _FakeEndpoint.instances.clear()
        _FakeEndpoint.block = False
        _FakeEndpoint.fail_open = False
        _FakeEndpoint.close_failures = 0

    def test_default_plan_is_inert_and_names_honest_repository_blockers(self) -> None:
        session = control.HostControlSession(
            _config(enabled=False, plan_only=True),
            run_registry=control.RunIdentityRegistry(),
            endpoint_factory=_FakeEndpoint,
        )

        plan = session.plan()

        self.assertEqual(plan["mode"], "plan_only")
        self.assertEqual(plan["phase_order"], list(control.CONTROL_PHASES))
        self.assertFalse(plan["launchable_from_repository_alone"])
        self.assertIn(
            "wearable_call020g_remote_control_connector_not_implemented",
            plan["repository_blockers"],
        )
        self.assertIn(
            "same_handle_device_control_counterpart_and_runtime_not_verified",
            plan["repository_blockers"],
        )
        self.assertIn(
            "same_handle_result_wire_and_quiescence_proof_not_implemented",
            plan["repository_blockers"],
        )
        self.assertIn(
            "external_callback_hard_preemption_not_implemented_or_verified",
            plan["repository_blockers"],
        )
        self.assertIn(
            "real_tls_connector_offline_implemented_not_runtime_verified",
            plan["repository_blockers"],
        )
        self.assertIn(
            "external_tls_session_authenticator_not_implemented_or_verified",
            plan["repository_blockers"],
        )
        self.assertTrue(all(value is False for value in plan["io_truth"].values()))
        self.assertEqual(plan["p0_call"], "NOT_RUN")
        self.assertEqual(_FakeEndpoint.instances, [])

    def test_plan_only_cli_outputs_metadata_and_has_no_execution_switch(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = control.main(
                [
                    "--plan-only",
                    "--run-id",
                    RUN_ID,
                    "--exact-port",
                    PORT,
                    "--frame-count",
                    "2",
                    "--max-runtime-ms",
                    "1000",
                ]
            )
        payload = json.loads(output.getvalue())
        self.assertEqual(result, 0)
        self.assertEqual(payload["mode"], "plan_only")
        self.assertFalse(payload["io_truth"]["serial_enumerated_or_opened"])
        self.assertNotIn(PORT, output.getvalue())
        self.assertNotIn(RUN_ID, output.getvalue())
        parser_help = control.build_parser().format_help()
        self.assertNotIn("--start", parser_help)
        self.assertNotIn("--execute", parser_help)

    def test_exact_port_validation_rejects_wildcard_url_and_whitespace(self) -> None:
        for port in ("COM*", "https://device", " COM8", "COM8 "):
            with self.subTest(port=port):
                with self.assertRaises(
                    (control.HostControlError, media_io.MediaIoError)
                ):
                    replace(_config(), exact_port=port).validate()

    def test_prepare_consumes_and_zeroes_one_shot_authorization(self) -> None:
        session = control.HostControlSession(
            _config(),
            run_registry=control.RunIdentityRegistry(),
            endpoint_factory=_FakeEndpoint,
        )
        authorization, token = _authorization()
        verifier = _Verifier()

        result = session.prepare(authorization=authorization, verifier=verifier)

        self.assertEqual(result["state"], "prepared")
        self.assertEqual(verifier.calls, 1)
        self.assertEqual(verifier.observed_length, len(TOKEN_BYTES))
        self.assertTrue(all(value == 0 for value in token))
        self.assertTrue(result["authorization"]["token_cleared"])
        with self.assertRaises(control.HostControlStateError):
            session.prepare(authorization=authorization, verifier=verifier)

    def test_disabled_or_plan_only_prepare_fails_before_verifier(self) -> None:
        for enabled, plan_only in ((False, False), (True, True), (False, True)):
            with self.subTest(enabled=enabled, plan_only=plan_only):
                session = control.HostControlSession(
                    _config(enabled=enabled, plan_only=plan_only),
                    run_registry=control.RunIdentityRegistry(),
                    endpoint_factory=_FakeEndpoint,
                )
                authorization, token = _authorization()
                verifier = _Verifier()
                with self.assertRaises(control.HostControlBlocked) as raised:
                    session.prepare(
                        authorization=authorization,
                        verifier=verifier,
                    )
                self.assertEqual(
                    raised.exception.reason_code, "execution_not_explicitly_enabled"
                )
                self.assertEqual(verifier.calls, 0)
                self.assertTrue(all(value == 0 for value in token))
                self.assertTrue(authorization.audit()["token_cleared"])

    def test_fresh_run_registry_rejects_reuse_after_consuming_second_token(self) -> None:
        registry = control.RunIdentityRegistry()
        first = control.HostControlSession(
            _config(), run_registry=registry, endpoint_factory=_FakeEndpoint
        )
        authorization, _ = _authorization()
        first.prepare(authorization=authorization, verifier=_Verifier())
        second = control.HostControlSession(
            _config(), run_registry=registry, endpoint_factory=_FakeEndpoint
        )
        authorization2, token2 = _authorization()
        with self.assertRaises(control.HostControlBlocked) as raised:
            second.prepare(authorization=authorization2, verifier=_Verifier())
        self.assertEqual(raised.exception.reason_code, "run_identity_reused")
        self.assertTrue(all(value == 0 for value in token2))

    def test_missing_wearable_connector_is_fail_closed_before_other_io(self) -> None:
        session = control.HostControlSession(
            _config(),
            run_registry=control.RunIdentityRegistry(),
            endpoint_factory=_FakeEndpoint,
        )
        authorization, _ = _authorization()
        session.prepare(authorization=authorization, verifier=_Verifier())
        tls_connector = _FakeTlsConnector()
        serial_factory = _FakeSerialFactory()

        with self.assertRaises(control.HostControlBlocked) as raised:
            session.preflight(
                wearable_control=None,
                wearable_attestation=None,
                tls_connector=tls_connector,
                tls_connector_attestation=_tls_attestation(),
                serial_factory=serial_factory,
            )

        self.assertEqual(
            raised.exception.reason_code, "wearable_control_connector_missing"
        )
        self.assertEqual(tls_connector.calls, 0)
        self.assertEqual(serial_factory.calls, 0)
        self.assertEqual(_FakeEndpoint.instances, [])
        self.assertFalse(raised.exception.metadata["wearable_control_proven"])

    def test_preflight_only_validates_injected_shapes_and_performs_no_calls(self) -> None:
        session, wearable, tls_connector, serial_factory = _prepared_session()

        audit = session.audit()

        self.assertEqual(audit["state"], "preflighted")
        self.assertEqual(wearable.actions, [])
        self.assertEqual(tls_connector.calls, 0)
        self.assertEqual(serial_factory.calls, 0)
        self.assertEqual(_FakeEndpoint.instances, [])

    def test_wearable_control_attestation_accepts_legacy_or_logical_separation(
        self,
    ) -> None:
        legacy = _wearable_attestation()
        logical = _same_handle_wearable_attestation()

        legacy.validate(required_timeout_ms=1_000)
        logical.validate(required_timeout_ms=1_000)
        with self.assertRaises(control.HostControlError):
            replace(
                legacy,
                out_of_band_from_media=False,
                logically_separate_and_not_interleaved_with_media=False,
            ).validate(required_timeout_ms=1_000)

    def test_same_handle_preflight_requires_one_concrete_dual_role_connector(self) -> None:
        session = control.HostControlSession(
            _config(),
            run_registry=control.RunIdentityRegistry(),
            endpoint_factory=_FakeEndpoint,
        )
        authorization, _ = _authorization()
        session.prepare(authorization=authorization, verifier=_Verifier())
        wearable = _FakeWearable()
        tls_connector = _FakeTlsConnector()
        serial_factory = _FakeSerialFactory()
        with self.assertRaises(control.HostControlBlocked) as raised:
            session.preflight(
                wearable_control=wearable,
                wearable_attestation=_same_handle_wearable_attestation(),
                tls_connector=tls_connector,
                tls_connector_attestation=_tls_attestation(),
                serial_factory=serial_factory,
            )

        self.assertEqual(
            raised.exception.reason_code,
            "external_connector_attestation_rejected",
        )
        self.assertEqual(tls_connector.calls, 0)  # type: ignore[attr-defined]
        self.assertEqual(serial_factory.calls, 0)
        self.assertEqual(_FakeEndpoint.instances, [])
        self.assertEqual(wearable.actions, [])
        self.assertEqual(session.close()["state"], "closed")
        self.assertEqual(wearable.actions, [])

    def test_tls_partial_open_self_cleanup_attestation_is_mandatory(self) -> None:
        session = control.HostControlSession(
            _config(),
            run_registry=control.RunIdentityRegistry(),
            endpoint_factory=_FakeEndpoint,
        )
        authorization, _ = _authorization()
        session.prepare(authorization=authorization, verifier=_Verifier())
        wearable = _FakeWearable()
        tls_connector = _FakeTlsConnector()
        serial_factory = _FakeSerialFactory()

        with self.assertRaises(control.HostControlBlocked) as raised:
            session.preflight(
                wearable_control=wearable,
                wearable_attestation=_wearable_attestation(),
                tls_connector=tls_connector,
                tls_connector_attestation=replace(
                    _tls_attestation(), cleans_partial_open_before_raise=False
                ),
                serial_factory=serial_factory,
            )

        self.assertEqual(
            raised.exception.reason_code,
            "external_connector_attestation_rejected",
        )
        self.assertEqual(wearable.actions, [])
        self.assertEqual(tls_connector.calls, 0)
        self.assertEqual(serial_factory.calls, 0)

    def test_retained_tls_cleanup_attestation_requires_retry_shape(self) -> None:
        session = control.HostControlSession(
            _config(),
            run_registry=control.RunIdentityRegistry(),
            endpoint_factory=_FakeEndpoint,
        )
        authorization, _ = _authorization()
        session.prepare(authorization=authorization, verifier=_Verifier())
        wearable = _FakeWearable()
        tls_connector = _FakeTlsConnector()
        serial_factory = _FakeSerialFactory()

        with self.assertRaises(control.HostControlBlocked) as raised:
            session.preflight(
                wearable_control=wearable,
                wearable_attestation=_wearable_attestation(),
                tls_connector=tls_connector,
                tls_connector_attestation=_retained_tls_attestation(),
                serial_factory=serial_factory,
            )

        self.assertEqual(
            raised.exception.reason_code,
            "external_connector_attestation_rejected",
        )
        self.assertEqual(wearable.actions, [])
        self.assertEqual(tls_connector.calls, 0)
        self.assertEqual(serial_factory.calls, 0)

    def test_m_requires_retained_cleanup_contract_for_n_connector(self) -> None:
        connector, _, _, _, socket_factory, authenticator = _host_tls_fakes()
        session = control.HostControlSession(
            _config(),
            run_registry=control.RunIdentityRegistry(),
            endpoint_factory=_FakeEndpoint,
        )
        authorization, _ = _authorization()
        session.prepare(authorization=authorization, verifier=_Verifier())

        with self.assertRaises(control.HostControlBlocked) as raised:
            session.preflight(
                wearable_control=_FakeWearable(),
                wearable_attestation=_wearable_attestation(),
                tls_connector=connector,
                tls_connector_attestation=_tls_attestation(),
                serial_factory=_FakeSerialFactory(),
            )

        self.assertEqual(
            raised.exception.reason_code,
            "external_connector_attestation_rejected",
        )
        self.assertEqual(socket_factory.calls, [])
        self.assertEqual(authenticator.calls, 0)

    def test_host_tls_connector_is_default_off_and_inert(self) -> None:
        raw = _FakeHostRawSocket()
        tls_socket = _FakeHostTlsSocket(raw)
        context = _FakeHostTlsContext(tls_socket)
        socket_factory = _FakeHostSocketFactory(raw)
        authenticator = _FakeConnectedSessionAuthenticator()
        connector = control.DefaultOffHostTlsConnector(
            _host_tls_config(enabled=False),
            authenticator=authenticator,
            socket_factory=socket_factory,
            ssl_context_factory=lambda: context,
            connection_id_factory=lambda: "call020n-disabled-connection",
        )

        before = connector.audit()
        with self.assertRaises(control.HostTlsConnectorBlocked) as raised:
            connector.open_verified(_host_tls_request())

        self.assertEqual(raised.exception.reason_code, "host_tls_connector_disabled")
        self.assertEqual(before["state"], "dormant")
        self.assertEqual(socket_factory.calls, [])
        self.assertEqual(authenticator.calls, 0)
        self.assertFalse(connector.audit()["numeric_connect_attempted"])

    def test_host_tls_submillisecond_auth_budget_fails_instead_of_extending_deadline(
        self,
    ) -> None:
        now_ns = 2_000_000_000
        raw = _FakeHostRawSocket()
        tls_socket = _FakeHostTlsSocket(raw)
        context = _FakeHostTlsContext(tls_socket)
        connector = control.DefaultOffHostTlsConnector(
            _host_tls_config(enabled=False),
            authenticator=_FakeConnectedSessionAuthenticator(),
            clock=_FixedClock(now_ns),
            socket_factory=_FakeHostSocketFactory(raw),
            ssl_context_factory=lambda: context,
        )

        with self.assertRaises(control.HostControlError):
            connector._remaining_timeout_ms(
                deadline_ns=now_ns + 999_999,
                cap_ms=1_000,
            )

    def test_host_tls_config_requires_exact_route_hostname_and_one_ca(self) -> None:
        valid = _host_tls_config(enabled=False)
        valid.validate()
        invalid = (
            replace(valid, peer_ipv4="relay.egolink.example"),
            replace(valid, peer_ipv4="203.0.113.020"),
            replace(valid, source_ipv4="0.0.0.0"),
            replace(valid, tls_hostname="203.0.113.20"),
            replace(valid, tls_hostname="*.egolink.example"),
            replace(valid, tls_hostname="Relay.egolink.example"),
            replace(valid, ca_pem=None, ca_file=None),
            replace(valid, ca_file=str(Path.cwd() / "ca.pem")),
            replace(valid, ca_pem=None, ca_file="relative-ca.pem"),
            replace(
                valid,
                overall_timeout_ms=1_000,
                tcp_connect_timeout_ms=500,
                handshake_timeout_ms=500,
                authentication_timeout_ms=500,
            ),
        )
        for config in invalid:
            with self.subTest(config=config):
                with self.assertRaises(control.HostControlError):
                    config.validate()

    def test_host_tls_missing_external_authenticator_fails_before_socket(self) -> None:
        raw = _FakeHostRawSocket()
        tls_socket = _FakeHostTlsSocket(raw)
        context = _FakeHostTlsContext(tls_socket)
        socket_factory = _FakeHostSocketFactory(raw)
        connector = control.DefaultOffHostTlsConnector(
            _host_tls_config(),
            authenticator=None,
            socket_factory=socket_factory,
            ssl_context_factory=lambda: context,
        )

        with self.assertRaises(control.HostTlsConnectorBlocked) as raised:
            connector.open_verified(_host_tls_request())

        self.assertEqual(
            raised.exception.reason_code, "external_session_authenticator_missing"
        )
        self.assertEqual(socket_factory.calls, [])
        self.assertFalse(raised.exception.metadata["authentication_decision_fabricated"])
        self.assertFalse(raised.exception.metadata["network_attempted"])

    def test_windows_interface_index_is_strict_and_optional(self) -> None:
        valid = _host_tls_config()
        with patch.object(control.sys, "platform", "win32"):
            for index in (None, 1, 19, 0xFFFFFF):
                replace(valid, windows_ipv4_interface_index=index).validate()
            for index in (0, -1, 0x1000000, True, False, 1.0, "19"):
                with self.subTest(index=index), self.assertRaises(control.HostControlError):
                    replace(valid, windows_ipv4_interface_index=index).validate()
        with patch.object(control.sys, "platform", "linux"):
            valid.validate()  # unconfigured behavior stays portable
            with self.assertRaises(control.HostControlError):
                _host_tls_fakes(config=replace(valid, windows_ipv4_interface_index=1))

    def test_windows_interface_pin_is_revalidated_before_socket_open(self) -> None:
        with patch.object(control.sys, "platform", "win32"):
            connector, _, _, _, factory, authenticator = _host_tls_fakes(
                config=replace(_host_tls_config(), windows_ipv4_interface_index=1)
            )
        with patch.object(control.sys, "platform", "linux"):
            with self.assertRaises(control.HostTlsConnectorBlocked) as raised:
                connector.open_verified(_host_tls_request())
        self.assertEqual(raised.exception.reason_code, "host_tls_preconnect_rejected")
        self.assertEqual(factory.calls, [])
        self.assertEqual(authenticator.calls, 0)
        self.assertFalse(connector.audit()["numeric_connect_attempted"])

    def test_host_tls_fake_success_uses_numeric_route_sni_ca_tls_and_alpn(self) -> None:
        (
            connector,
            raw,
            tls_socket,
            context,
            socket_factory,
            authenticator,
        ) = _host_tls_fakes()
        request = _host_tls_request()

        result = connector.open_verified(request)

        self.assertEqual(
            socket_factory.calls,
            [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP)],
        )
        self.assertEqual(raw.bound_to, ("192.0.2.10", 0))
        self.assertEqual(raw.connected_to, ("203.0.113.20", 443))
        self.assertEqual(context.ca_kwargs, {"cadata": CALL020N_CA_PEM})
        self.assertEqual(
            context.wrap_kwargs,
            {
                "server_hostname": "relay.egolink.example",
                "do_handshake_on_connect": False,
            },
        )
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)
        self.assertEqual(context.maximum_version, ssl.TLSVersion.TLSv1_3)
        self.assertFalse(context.hostname_checks_common_name)
        self.assertEqual(context.alpn_protocols, [control.DEFAULT_ALPN])
        self.assertEqual(tls_socket.handshake_calls, 1)
        self.assertEqual(tls_socket.gettimeout(), 0.02)
        self.assertEqual(authenticator.calls, 1)
        self.assertIsNotNone(authenticator.evidence)
        self.assertEqual(
            result.tls_attestation.verified_server_hostname,
            "relay.egolink.example",
        )
        self.assertEqual(
            result.authentication_decision.binding.connection_id,
            result.tls_socket.connection_id,
        )
        self.assertEqual(connector.audit()["state"], "transferred")
        self.assertTrue(connector.audit()["connected_source_binding_verified"])
        self.assertTrue(connector.audit()["connected_numeric_peer_verified"])
        self.assertFalse(connector.audit()["dns_resolution_used"])
        self.assertFalse(connector.audit()["authentication_decision_fabricated"])
        result.tls_socket.close()

    def test_host_tls_rejects_connected_route_mismatch_before_tls_wrap(self) -> None:
        for raw in (
            _FakeHostRawSocket(reported_source_ipv4="192.0.2.11"),
            _FakeHostRawSocket(reported_peer=("203.0.113.21", 443)),
        ):
            with self.subTest(raw=raw):
                connector, _, tls_socket, context, _, authenticator = (
                    _host_tls_fakes(raw=raw)
                )

                with self.assertRaises(control.HostTlsConnectorBlocked) as raised:
                    connector.open_verified(_host_tls_request())

                self.assertEqual(
                    raised.exception.reason_code, "connected_exact_route_mismatch"
                )
                self.assertGreaterEqual(raw.close_calls, 1)
                self.assertEqual(tls_socket.handshake_calls, 0)
                self.assertIsNone(context.wrap_kwargs)
                self.assertEqual(authenticator.calls, 0)

    def test_host_tls_exact_absolute_ca_path_is_passed_without_discovery(self) -> None:
        ca_path = str((Path.cwd() / "offline" / "exact-ca.pem").resolve())
        connector, _, _, context, _, _ = _host_tls_fakes(
            config=_host_tls_config(ca_file=ca_path)
        )

        result = connector.open_verified(_host_tls_request())

        self.assertEqual(context.ca_kwargs, {"cafile": ca_path})
        result.tls_socket.close()

    def test_host_tls_partial_failures_close_every_created_transport(self) -> None:
        raw_connect = _FakeHostRawSocket(fail_connect=True)
        connector, _, _, _, _, _ = _host_tls_fakes(raw=raw_connect)
        with self.assertRaises(control.HostTlsConnectorBlocked) as connect_error:
            connector.open_verified(_host_tls_request())
        self.assertEqual(connect_error.exception.reason_code, "numeric_tls_connect_failed")
        self.assertGreaterEqual(raw_connect.close_calls, 1)
        self.assertTrue(connect_error.exception.metadata["partial_cleanup_confirmed"])

        raw_handshake = _FakeHostRawSocket()
        tls_handshake = _FakeHostTlsSocket(raw_handshake, fail_handshake=True)
        connector, _, _, _, _, _ = _host_tls_fakes(
            raw=raw_handshake, tls_socket=tls_handshake
        )
        with self.assertRaises(control.HostTlsConnectorBlocked) as handshake_error:
            connector.open_verified(_host_tls_request())
        self.assertEqual(
            handshake_error.exception.reason_code, "tls_wrap_or_handshake_failed"
        )
        self.assertGreaterEqual(tls_handshake.close_calls, 1)
        self.assertTrue(handshake_error.exception.metadata["partial_cleanup_confirmed"])

        raw_alpn = _FakeHostRawSocket()
        tls_alpn = _FakeHostTlsSocket(raw_alpn, alpn="wrong-alpn")
        connector, _, _, _, _, _ = _host_tls_fakes(
            raw=raw_alpn, tls_socket=tls_alpn
        )
        with self.assertRaises(control.HostTlsConnectorBlocked) as alpn_error:
            connector.open_verified(_host_tls_request())
        self.assertEqual(alpn_error.exception.reason_code, "tls_alpn_mismatch")
        self.assertGreaterEqual(tls_alpn.close_calls, 1)

    def test_host_tls_invalid_external_decision_closes_and_never_fabricates(self) -> None:
        for authenticator in (
            _FakeConnectedSessionAuthenticator(wrong_binding=True),
            _FakeConnectedSessionAuthenticator(invalid_result=True),
        ):
            with self.subTest(authenticator=type(authenticator).__name__):
                connector, _, tls_socket, _, _, _ = _host_tls_fakes(
                    authenticator=authenticator
                )
                with self.assertRaises(control.HostTlsConnectorBlocked) as raised:
                    connector.open_verified(_host_tls_request())
                self.assertEqual(
                    raised.exception.reason_code,
                    "external_session_authentication_failed",
                )
                self.assertEqual(authenticator.calls, 1)
                self.assertGreaterEqual(tls_socket.close_calls, 1)
                self.assertFalse(
                    raised.exception.metadata["authentication_decision_fabricated"]
                )

    def test_host_tls_retains_same_partial_target_until_cleanup_confirms(self) -> None:
        raw = _FakeHostRawSocket()
        tls_socket = _FakeHostTlsSocket(
            raw,
            fail_handshake=True,
            close_failures=control.HOST_TLS_CLEANUP_ATTEMPTS,
        )
        connector, _, _, _, _, _ = _host_tls_fakes(
            raw=raw, tls_socket=tls_socket
        )

        with self.assertRaises(control.HostTlsConnectorBlocked) as raised:
            connector.open_verified(_host_tls_request())

        self.assertFalse(raised.exception.metadata["partial_cleanup_confirmed"])
        self.assertEqual(connector.audit()["state"], "cleanup_failed")
        self.assertTrue(connector.audit()["partial_cleanup_target_retained"])
        self.assertEqual(tls_socket.close_calls, control.HOST_TLS_CLEANUP_ATTEMPTS)

        self.assertTrue(connector.retry_failed_open_cleanup())
        self.assertFalse(connector.audit()["partial_cleanup_target_retained"])
        self.assertTrue(connector.audit()["partial_cleanup_confirmed"])
        self.assertEqual(tls_socket.close_calls, control.HOST_TLS_CLEANUP_ATTEMPTS + 1)

    def test_host_tls_result_is_accepted_by_existing_j_types_without_media(self) -> None:
        connector, _, _, _, _, _ = _host_tls_fakes()
        request = _host_tls_request()
        result = connector.open_verified(request)
        stream = tls.ConnectedTlsOrderedByteStream(
            result.tls_socket,
            result.tls_attestation,
            result.authentication_decision,
            tls.ConnectedTlsStreamConfig(
                identity=request.identity,
                role="device",
                enabled=True,
                expected_alpn=control.DEFAULT_ALPN,
                per_call_timeout_ms=20,
                max_operation_timeout_ms=1_000,
            ),
        )

        audit = stream.audit()

        self.assertEqual(audit["state"], "ready")
        self.assertEqual(audit["read_operations"], 0)
        self.assertEqual(audit["write_operations"], 0)
        stream.close()

    def test_host_tls_connector_injects_into_m_without_control_endpoint_assumption(self) -> None:
        connector, _, _, _, _, _ = _host_tls_fakes()
        session, _, _, serial_factory = _prepared_session(
            tls_connector=connector,
            tls_connector_attestation=_retained_tls_attestation(),
        )

        opened = session.open()

        self.assertEqual(opened["state"], "open")
        self.assertEqual(connector.audit()["state"], "transferred")
        self.assertEqual(serial_factory.calls, 0)
        self.assertEqual(_FakeEndpoint.instances[-1].start_calls, 0)
        session.close()

    def test_m_retries_n_retained_partial_open_cleanup_before_closed(self) -> None:
        raw = _FakeHostRawSocket()
        tls_socket = _FakeHostTlsSocket(
            raw,
            fail_handshake=True,
            close_failures=control.HOST_TLS_CLEANUP_ATTEMPTS * 2,
        )
        connector, _, _, _, _, _ = _host_tls_fakes(
            raw=raw, tls_socket=tls_socket
        )
        session, _, _, _ = _prepared_session(
            tls_connector=connector,
            tls_connector_attestation=_retained_tls_attestation(),
        )

        with self.assertRaises(control.HostControlBlocked) as raised:
            session.open()

        self.assertEqual(raised.exception.reason_code, "external_tls_connector_failed")
        self.assertTrue(session.audit()["tls_connector_cleanup_pending"])
        self.assertTrue(connector.audit()["partial_cleanup_target_retained"])
        self.assertEqual(
            tls_socket.close_calls, control.HOST_TLS_CLEANUP_ATTEMPTS * 2
        )

        closed = session.close()
        self.assertEqual(closed["state"], "closed")
        self.assertFalse(closed["tls_connector_cleanup_pending"])
        self.assertFalse(connector.audit()["partial_cleanup_target_retained"])
        self.assertEqual(
            tls_socket.close_calls, control.HOST_TLS_CLEANUP_ATTEMPTS * 2 + 1
        )

    def test_m_never_closes_while_n_partial_cleanup_stays_unconfirmed(self) -> None:
        raw = _FakeHostRawSocket()
        tls_socket = _FakeHostTlsSocket(
            raw,
            fail_handshake=True,
            close_failures=100,
        )
        connector, _, _, _, _, _ = _host_tls_fakes(
            raw=raw, tls_socket=tls_socket
        )
        session, _, _, _ = _prepared_session(
            tls_connector=connector,
            tls_connector_attestation=_retained_tls_attestation(),
        )

        with self.assertRaises(control.HostControlBlocked):
            session.open()

        for _ in range(2):
            with self.assertRaises(control.HostControlBlocked) as raised:
                session.close()
            self.assertEqual(
                raised.exception.reason_code,
                "tls_connector_cleanup_not_confirmed",
            )
            audit = session.audit()
            self.assertEqual(audit["state"], "failed")
            self.assertTrue(audit["tls_connector_cleanup_pending"])
            self.assertFalse(audit["references_cleared"])
            self.assertTrue(connector.audit()["partial_cleanup_target_retained"])

    def test_m_closes_valid_bundle_returned_after_overall_deadline(self) -> None:
        connector = _FakeTlsConnector(return_delay_seconds=0.03)
        session, wearable, _, _ = _prepared_session(
            tls_connector=connector,
            tls_connector_attestation=replace(
                _tls_attestation(), max_connect_timeout_ms=10
            ),
        )

        with self.assertRaises(control.HostControlBlocked) as raised:
            session.open()

        self.assertEqual(raised.exception.reason_code, "external_tls_connector_failed")
        self.assertIsNotNone(connector.socket)
        assert connector.socket is not None
        self.assertGreaterEqual(connector.socket.cancel_calls, 1)
        self.assertGreaterEqual(connector.socket.close_calls, 1)
        self.assertIn("close", wearable.actions)
        self.assertFalse(session.audit()["tls_connector_cleanup_pending"])
        session.close()

    def test_host_tls_source_contains_no_dns_or_executable_cli_path(self) -> None:
        source = Path("pc_simulator/ego_call_operator_control.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("getaddrinfo(", source)
        self.assertNotIn("create_connection(", source)
        self.assertIn("socket_module.AF_INET", source)
        parser_help = control.build_parser().format_help()
        self.assertNotIn("--execute", parser_help)
        self.assertNotIn("--start", parser_help)

    def test_open_maps_call020g_descriptor_into_existing_l_configuration(self) -> None:
        session, wearable, tls_connector, serial_factory = _prepared_session()

        result = session.open()

        endpoint = _FakeEndpoint.instances[-1]
        config = endpoint.config
        self.assertEqual(result["state"], "open")
        self.assertEqual(wearable.actions, ["prepare"])
        self.assertEqual(tls_connector.calls, 1)
        self.assertEqual(serial_factory.calls, 0)
        self.assertEqual(config.serial.port_name, PORT)
        self.assertEqual(config.identity, tls_connector.requests[0].identity)
        self.assertEqual(config.identity.session_id, "s-call020m-private")
        self.assertTrue(config.enabled)
        self.assertTrue(config.serial.enabled)
        self.assertTrue(config.tls.enabled)
        self.assertIs(endpoint.open_kwargs["serial_factory"], serial_factory)
        self.assertIsNotNone(result["pre_start_telemetry"])
        session.close()

    def test_start_stop_close_use_stable_idempotency_keys_and_metadata_only(self) -> None:
        session, wearable, _, _ = _prepared_session()
        session.open()

        session.start()
        self.assertTrue(_FakeEndpoint.instances[-1].started.wait(1.0))
        for _ in range(100):
            if session.audit()["media_thread_done"]:
                break
            time.sleep(0.005)
        stopped = session.stop()
        stopped_again = session.stop()
        closed = session.close()
        closed_again = session.close()

        self.assertEqual(stopped["state"], "stopped")
        self.assertEqual(stopped_again["control_calls"], stopped["control_calls"])
        self.assertEqual(closed["state"], "closed")
        self.assertEqual(closed_again, closed)
        self.assertEqual(
            wearable.actions,
            ["prepare", "start", "cancel", "join", "telemetry", "close"],
        )
        operation_ids = {item.action: item.operation_id for item in wearable.commands}
        for action, operation_id in operation_ids.items():
            self.assertEqual(operation_id, f"{RUN_ID}:{action}:1")
        self.assertEqual(stopped["media_result"]["result"], "PASS")
        expected_counters = {
            "frames_expected",
            "frames_received",
            "frames_forwarded",
            "receive_retry_count",
            "send_retry_count",
            "backpressure_drops",
            "deadline_misses_before_send",
            "deadline_misses_after_send",
        }
        for direction in ("uplink", "downlink"):
            self.assertEqual(
                set(stopped["media_result"]["directions"][direction]),
                expected_counters,
            )
        self.assertIsInstance(stopped["host_monotonic_run_elapsed_ms"], int)
        self.assertEqual(stopped["media_termination_reason"], "bridge_completed")
        self.assertFalse(_contains_binary((stopped, closed)))

    def test_stop_cancels_blocking_media_and_joins_within_bound(self) -> None:
        _FakeEndpoint.block = True
        session, wearable, _, _ = _prepared_session()
        session.open()
        session.start()
        endpoint = _FakeEndpoint.instances[-1]
        self.assertTrue(endpoint.started.wait(1.0))

        stopped = session.stop()
        session.close()

        self.assertEqual(stopped["state"], "stopped")
        self.assertEqual(endpoint.cancel_calls, 1)
        self.assertTrue(stopped["media_thread_done"])
        self.assertIn("cancel", wearable.actions)
        self.assertIn("join", wearable.actions)

    def test_close_racing_start_rechecks_state_and_joins_media_before_closed(self) -> None:
        _FakeEndpoint.block = True
        wearable = _FakeWearable(block_start=True)
        session, _, _, _ = _prepared_session(wearable=wearable)
        session.open()
        start_errors: list[Exception] = []
        close_errors: list[Exception] = []

        def start_session() -> None:
            try:
                session.start()
            except Exception as error:
                start_errors.append(error)

        def close_session() -> None:
            try:
                session.close()
            except Exception as error:
                close_errors.append(error)

        start_thread = threading.Thread(target=start_session)
        start_thread.start()
        self.assertTrue(wearable.start_entered.wait(1.0))
        self.assertEqual(session.audit()["state"], "starting")
        close_thread = threading.Thread(target=close_session)
        close_thread.start()
        time.sleep(0.02)
        self.assertTrue(close_thread.is_alive())

        wearable.start_release.set()
        start_thread.join(1.0)
        close_thread.join(1.0)

        self.assertFalse(start_thread.is_alive())
        self.assertFalse(close_thread.is_alive())
        self.assertEqual(start_errors, [])
        self.assertEqual(close_errors, [])
        endpoint = _FakeEndpoint.instances[-1]
        self.assertGreaterEqual(endpoint.cancel_calls, 1)
        audit = session.audit()
        self.assertEqual(audit["state"], "closed")
        self.assertTrue(audit["media_thread_done"])
        self.assertTrue(audit["references_cleared"])

    def test_close_racing_open_waits_then_stops_prepared_wearable(self) -> None:
        tls_connector = _FakeTlsConnector(block_open=True)
        session, wearable, _, _ = _prepared_session(
            tls_connector=tls_connector
        )
        open_errors: list[Exception] = []
        close_errors: list[Exception] = []

        def open_session() -> None:
            try:
                session.open()
            except Exception as error:
                open_errors.append(error)

        def close_session() -> None:
            try:
                session.close()
            except Exception as error:
                close_errors.append(error)

        open_thread = threading.Thread(target=open_session)
        open_thread.start()
        self.assertTrue(tls_connector.open_entered.wait(1.0))
        self.assertEqual(session.audit()["state"], "opening")
        close_thread = threading.Thread(target=close_session)
        close_thread.start()
        time.sleep(0.02)
        self.assertTrue(close_thread.is_alive())

        tls_connector.open_release.set()
        open_thread.join(1.0)
        close_thread.join(1.0)

        self.assertFalse(open_thread.is_alive())
        self.assertFalse(close_thread.is_alive())
        self.assertEqual(open_errors, [])
        self.assertEqual(close_errors, [])
        self.assertEqual(session.audit()["state"], "closed")
        self.assertEqual(
            wearable.actions, ["prepare", "cancel", "join", "telemetry", "close"]
        )
        self.assertEqual(_FakeEndpoint.instances[-1].start_calls, 0)

    def test_malformed_prepare_reply_runs_fail_closed_cancel_join_close(self) -> None:
        wearable = _FakeWearable(wrong_prepare_operation=True)
        session, _, tls_connector, serial_factory = _prepared_session(
            wearable=wearable
        )

        with self.assertRaises(control.HostControlBlocked) as raised:
            session.open()

        self.assertEqual(raised.exception.reason_code, "wearable_prepare_failed")
        self.assertEqual(
            wearable.actions, ["prepare", "cancel", "join", "close"]
        )
        self.assertEqual(tls_connector.calls, 0)
        self.assertEqual(serial_factory.calls, 0)
        self.assertEqual(_FakeEndpoint.instances, [])

    def test_prepare_reply_loss_still_runs_idempotent_cleanup(self) -> None:
        wearable = _FakeWearable(raise_during_prepare=True)
        session, _, tls_connector, serial_factory = _prepared_session(
            wearable=wearable
        )

        with self.assertRaises(control.HostControlBlocked) as raised:
            session.open()

        self.assertEqual(raised.exception.reason_code, "wearable_prepare_failed")
        self.assertEqual(
            wearable.actions, ["prepare", "cancel", "join", "close"]
        )
        self.assertEqual(tls_connector.calls, 0)
        self.assertEqual(serial_factory.calls, 0)

    def test_endpoint_open_failure_cleans_tls_and_prepared_wearable(self) -> None:
        _FakeEndpoint.fail_open = True
        session, wearable, tls_connector, _ = _prepared_session()

        with self.assertRaises(control.HostControlBlocked) as raised:
            session.open()

        self.assertEqual(
            raised.exception.reason_code, "pc_endpoint_composition_open_failed"
        )
        self.assertEqual(
            wearable.actions, ["prepare", "cancel", "join", "close"]
        )
        self.assertIsNotNone(tls_connector.socket)
        self.assertGreaterEqual(tls_connector.socket.close_calls, 1)
        self.assertEqual(session.audit()["state"], "failed")

    def test_unconfirmed_wearable_close_retains_refs_until_bounded_retry_recovers(self) -> None:
        _FakeEndpoint.fail_open = True
        wearable = _FakeWearable(close_failures=2)
        session, _, _, _ = _prepared_session(wearable=wearable)

        with self.assertRaises(control.HostControlBlocked) as raised:
            session.open()

        self.assertEqual(
            raised.exception.reason_code, "pc_endpoint_composition_open_failed"
        )
        failed = session.audit()
        self.assertEqual(failed["state"], "failed")
        self.assertFalse(failed["references_cleared"])
        self.assertEqual(failed["control_calls"]["close"], 2)

        closed = session.close()

        self.assertEqual(closed["state"], "closed")
        self.assertTrue(closed["references_cleared"])
        self.assertEqual(closed["control_calls"]["close"], 3)
        self.assertGreaterEqual(closed["control_retry_attempts"], 1)

    def test_permanent_wearable_close_failure_never_reports_closed(self) -> None:
        _FakeEndpoint.fail_open = True
        wearable = _FakeWearable(close_failures=10)
        session, _, _, _ = _prepared_session(wearable=wearable)
        with self.assertRaises(control.HostControlBlocked):
            session.open()

        with self.assertRaises(control.HostControlBlocked) as raised:
            session.close()

        self.assertEqual(
            raised.exception.reason_code, "wearable_close_not_confirmed"
        )
        audit = session.audit()
        self.assertEqual(audit["state"], "failed")
        self.assertFalse(audit["references_cleared"])

    def test_transient_endpoint_close_failure_retries_same_endpoint(self) -> None:
        _FakeEndpoint.close_failures = 1
        session, _, _, _ = _prepared_session()
        session.open()
        endpoint = _FakeEndpoint.instances[-1]

        with self.assertRaises(control.HostControlBlocked) as raised:
            session.close()

        self.assertEqual(
            raised.exception.reason_code, "pc_endpoint_close_not_confirmed"
        )
        failed = session.audit()
        self.assertEqual(failed["state"], "failed")
        self.assertFalse(failed["pc_endpoint_close_confirmed"])
        self.assertFalse(failed["references_cleared"])
        self.assertEqual(endpoint.close_calls, 1)

        closed = session.close()

        self.assertEqual(closed["state"], "closed")
        self.assertTrue(closed["pc_endpoint_close_confirmed"])
        self.assertTrue(closed["references_cleared"])
        self.assertEqual(endpoint.close_calls, 2)

    def test_permanent_endpoint_close_failure_never_reports_closed(self) -> None:
        _FakeEndpoint.close_failures = 10
        session, _, _, _ = _prepared_session()
        session.open()
        endpoint = _FakeEndpoint.instances[-1]

        for expected_calls in (1, 2):
            with self.assertRaises(control.HostControlBlocked) as raised:
                session.close()
            self.assertEqual(
                raised.exception.reason_code, "pc_endpoint_close_not_confirmed"
            )
            audit = session.audit()
            self.assertEqual(audit["state"], "failed")
            self.assertFalse(audit["pc_endpoint_close_confirmed"])
            self.assertFalse(audit["references_cleared"])
            self.assertEqual(endpoint.close_calls, expected_calls)

    def test_telemetry_contract_rejects_missing_exact_worker_set(self) -> None:
        invalid = replace(
            _post_stop_telemetry(),
            worker_stack_high_watermark_bytes=(("audio_capture", 1_024),),
        )
        with self.assertRaises(control.HostControlError):
            invalid.validate(expected_phase="post_stop")

    def test_results_errors_and_plan_redact_port_run_ids_routing_and_token(self) -> None:
        session = control.HostControlSession(
            _config(),
            run_registry=control.RunIdentityRegistry(),
            endpoint_factory=_FakeEndpoint,
        )
        authorization, token = _authorization()
        session.prepare(authorization=authorization, verifier=_Verifier())
        with self.assertRaises(control.HostControlBlocked) as raised:
            session.preflight(
                wearable_control=None,
                wearable_attestation=None,
                tls_connector=None,
                tls_connector_attestation=None,
                serial_factory=None,
            )
        values = (session.audit(), raised.exception.metadata)
        serialized = json.dumps(values, sort_keys=True, allow_nan=False)
        self.assertFalse(_contains_binary(values))
        for forbidden in (PORT, RUN_ID, TOKEN_BYTES.decode("ascii")):
            self.assertNotIn(forbidden, serialized)
        self.assertTrue(all(value == 0 for value in token))

    def test_source_has_no_transport_discovery_logging_storage_or_serial_connector(self) -> None:
        source = Path("pc_simulator/ego_call_operator_control.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("import serial", source)
        self.assertNotIn("list_ports", source)
        self.assertNotIn("create_connection", source)
        self.assertNotIn("getaddrinfo", source)
        self.assertNotIn("logging", source)
        self.assertNotIn("Path.write", source)
        self.assertNotIn("wave.open", source)
        self.assertIn("enabled: bool = False", source)
        self.assertIn("PcEndpointComposition", source)
        self.assertIn("wearable_call020g_remote_control_connector_not_implemented", source)
        self.assertIn("if __name__ == \"__main__\"", source)


if __name__ == "__main__":
    unittest.main()

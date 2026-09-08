"""One-run CALL-020 mTLS admission and EGLM relay; no media persistence.

Reuses CALL-020N/J/I/C.  The private, length-delimited admission exchange is
complete before EGLM starts. A pinned client certificate authorizes one role
in one operator-named run; the runtime descriptor is conveyed to that run's
Guardian in memory. There is no listener or device access on import.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import secrets
import socket
import ssl
import struct
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from pc_simulator import ego_call_operator_control as control
from pc_simulator.ego_call_authenticated_relay import (
    AuthenticatedRelayConfig, ExternalAuthenticationDecision,
    ProcessLocalAuthenticatedRelay, RelayAdmissionRegistry, RelayEndpointBinding,
)
from pc_simulator.ego_call_concurrent_bridge import ConcurrentBridgeConfig
from pc_simulator.ego_call_media_io import EndpointIdentity, _identifier
from pc_simulator.ego_call_tls_stream_adapter import (
    ConnectedTlsOrderedByteStream, ConnectedTlsStreamConfig, DEFAULT_ALPN,
    InjectedTlsConnectionAttestation,
)

MAX_ADMISSION_BYTES = 4096
ADMISSION_VERSION = "egolink.call020.mtls.v1"


class LiveAdmissionError(ValueError):
    """Intentionally redacted: no credential, peer address or session identity."""


def _remaining(deadline: float) -> None:
    if time.monotonic() >= deadline:
        raise LiveAdmissionError("admission deadline expired")


def _read_exact(stream: Any, size: int, deadline: float) -> bytearray:
    result = bytearray(size)
    offset = 0
    try:
        while offset < size:
            _remaining(deadline)
            try:
                count = stream.recv_into(memoryview(result)[offset:], size - offset)
            except TimeoutError:
                continue  # recv consumed no returned application bytes
            if type(count) is not int or not 0 < count <= size - offset:
                raise LiveAdmissionError("admission EOF or invalid progress")
            offset += count
        _remaining(deadline)
        return result
    except BaseException:
        result[:] = b"\x00" * len(result)
        raise


def _json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise LiveAdmissionError("duplicate admission field")
        result[key] = value
    return result


def _receive(stream: Any, deadline: float) -> dict[str, Any]:
    header = _read_exact(stream, 4, deadline)
    length = struct.unpack("!I", header)[0]
    if not 1 <= length <= MAX_ADMISSION_BYTES:
        raise LiveAdmissionError("admission length outside bound")
    raw = _read_exact(stream, length, deadline)
    try:
        result = json.loads(raw, object_pairs_hook=_json_pairs)
        if not isinstance(result, dict):
            raise LiveAdmissionError("admission object required")
        return result
    finally:
        raw[:] = b"\x00" * len(raw)


def _send(stream: Any, value: dict[str, Any], deadline: float) -> None:
    raw = bytearray(json.dumps(value, separators=(",", ":"), sort_keys=True).encode())
    if not 1 <= len(raw) <= MAX_ADMISSION_BYTES:
        raise LiveAdmissionError("admission length outside bound")
    packet = bytearray(struct.pack("!I", len(raw))) + raw
    try:
        offset = 0
        while offset < len(packet):
            _remaining(deadline)
            # A send timeout has unknown progress: never resend the frame.
            count = stream.send(memoryview(packet)[offset:])
            if type(count) is not int or not 0 < count <= len(packet) - offset:
                raise LiveAdmissionError("admission write progress invalid")
            offset += count
        _remaining(deadline)
    finally:
        raw[:] = b"\x00" * len(raw)
        packet[:] = b"\x00" * len(packet)


def _binding(identity: EndpointIdentity, role: str, connection_id: str) -> RelayEndpointBinding:
    if role not in {"device", "guardian"}:
        raise LiveAdmissionError("unknown endpoint role")
    return RelayEndpointBinding(
        identity.session_id, role,
        identity.device_id if role == "device" else identity.guardian_id,
        identity.guardian_id if role == "device" else identity.device_id,
        identity.uplink_clock_id if role == "device" else identity.downlink_clock_id,
        connection_id,
    )


def _decision(identity: EndpointIdentity, role: str, connection_id: str) -> ExternalAuthenticationDecision:
    now = time.monotonic_ns()
    return ExternalAuthenticationDecision(
        "mtls-" + secrets.token_hex(16), True, _binding(identity, role, connection_id),
        now, now + 30_000_000_000,
    )


def _hello(run_id: str, role: str, connection_id: str, identity: EndpointIdentity | None) -> dict[str, Any]:
    return {"version": ADMISSION_VERSION, "run_id": run_id, "role": role,
            "connection_id": connection_id,
            "identity": asdict(identity) if identity is not None else None}


def _validate_hello(value: dict[str, Any], run_id: str) -> None:
    if set(value) != {"version", "run_id", "role", "connection_id", "identity"}:
        raise LiveAdmissionError("admission fields mismatch")
    if value["version"] != ADMISSION_VERSION or value["run_id"] != run_id:
        raise LiveAdmissionError("admission version or run mismatch")
    if value["role"] not in {"device", "guardian"}:
        raise LiveAdmissionError("admission role rejected")
    _identifier(value["connection_id"], label="connection id")
    if value["identity"] is not None:
        if not isinstance(value["identity"], dict):
            raise LiveAdmissionError("identity object required")
        EndpointIdentity(**value["identity"]).validate()
    elif value["role"] != "guardian":
        raise LiveAdmissionError("device descriptor required")


class MtlsSessionAuthenticator:
    """Real exchange on N's already-verified socket; no manufactured callback."""

    def authorize_tls_stream(self, *, evidence: control.HostTlsPeerEvidence,
                             tls_socket: Any, timeout_ms: int) -> ExternalAuthenticationDecision:
        evidence.validate()
        deadline = time.monotonic() + timeout_ms / 1000
        request = _hello(evidence.run_id, evidence.role, evidence.connection_id, evidence.identity)
        _send(tls_socket, request, deadline)
        response = _receive(tls_socket, deadline)
        if response.get("accepted") is not True or response != {**request, "accepted": True}:
            raise LiveAdmissionError("exact admission acknowledgement mismatch")
        return _decision(evidence.identity, evidence.role, evidence.connection_id)


def client_context(cert_file: str, key_file: str) -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_cert_chain(cert_file, key_file)
    return context


def make_connector(config: control.HostTlsConnectorConfig, *, cert_file: str,
                   key_file: str) -> control.DefaultOffHostTlsConnector:
    return control.DefaultOffHostTlsConnector(
        config, authenticator=MtlsSessionAuthenticator(),
        ssl_context_factory=lambda: client_context(cert_file, key_file),
    )


@dataclass(frozen=True)
class RelayRunConfig:
    run_id: str
    listen_ipv4: str
    port: int
    ca_file: str
    cert_file: str
    key_file: str
    device_certificate_sha256: str
    guardian_certificate_sha256: str
    frame_count: int = 500
    max_runtime_ms: int = 15000
    setup_timeout_ms: int = 15000
    enabled: bool = False

    def validate(self) -> None:
        _identifier(self.run_id, label="run id")
        control._exact_ipv4(self.listen_ipv4, label="listen address")
        if type(self.port) is not int or not 0 <= self.port <= 65535:
            raise LiveAdmissionError("listen port invalid")
        for digest in (self.device_certificate_sha256, self.guardian_certificate_sha256):
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise LiveAdmissionError("exact role certificate pin required")
        if self.device_certificate_sha256 == self.guardian_certificate_sha256:
            raise LiveAdmissionError("device and Guardian credentials must differ")
        if type(self.setup_timeout_ms) is not int or not 100 <= self.setup_timeout_ms <= 30000:
            raise LiveAdmissionError("setup deadline invalid")
        ConcurrentBridgeConfig(frame_count=self.frame_count, max_runtime_ms=self.max_runtime_ms).validate()


class LiveMtlsRelay:
    """One bounded pair, one run, no reconnect/replay and no background service."""

    def __init__(self, config: RelayRunConfig):
        config.validate()
        self.config = config
        self._listener: socket.socket | None = None
        self._context: ssl.SSLContext | None = None
        self._started = False

    def listen(self) -> int:
        if self.config.enabled is not True or self._started:
            raise LiveAdmissionError("relay disabled or already used")
        self._started = True
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.maximum_version = ssl.TLSVersion.TLSv1_3
        context.verify_mode = ssl.CERT_REQUIRED
        context.load_verify_locations(cafile=self.config.ca_file)
        context.load_cert_chain(self.config.cert_file, self.config.key_file)
        context.set_alpn_protocols([DEFAULT_ALPN])
        self._context = context
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            listener.bind((self.config.listen_ipv4, self.config.port))
            listener.listen(2)
            listener.settimeout(0.02)
            self._listener = listener
            return listener.getsockname()[1]
        except BaseException:
            listener.close()
            raise

    def run(self) -> dict[str, Any]:
        config = self.config
        if self._listener is None:
            raise LiveAdmissionError("explicit listen required")
        streams: dict[str, Any] = {}
        identities: dict[str, EndpointIdentity] = {}
        decisions: dict[str, ExternalAuthenticationDecision] = {}
        sockets: list[Any] = []
        errors: list[bool] = []
        condition = threading.Condition()
        deadline = time.monotonic() + config.setup_timeout_ms / 1000
        workers: list[threading.Thread] = []
        context = self._context

        def admit(raw: socket.socket) -> None:
            wrapped = None
            try:
                raw.settimeout(min(2.0, max(0.001, deadline - time.monotonic())))
                wrapped = context.wrap_socket(raw, server_side=True)
                with condition:
                    sockets.append(wrapped)
                wrapped.settimeout(0.02)
                if wrapped.selected_alpn_protocol() != DEFAULT_ALPN:
                    raise LiveAdmissionError("ALPN mismatch")
                hello = _receive(wrapped, deadline)
                _validate_hello(hello, config.run_id)
                role = hello["role"]
                pin = getattr(config, role + "_certificate_sha256")
                if not hmac.compare_digest(hashlib.sha256(wrapped.getpeercert(binary_form=True)).hexdigest(), pin):
                    raise LiveAdmissionError("role certificate not authorized for run")
                with condition:
                    if role in identities or role in streams:
                        raise LiveAdmissionError("duplicate role rejected")
                    streams[role] = None  # reserve before waiting
                    if hello["identity"] is not None:
                        identities[role] = EndpointIdentity(**hello["identity"])
                    condition.notify_all()
                    while "device" not in identities:
                        _remaining(deadline)
                        if errors:
                            raise LiveAdmissionError("other endpoint failed")
                        condition.wait(min(0.02, max(0, deadline - time.monotonic())))
                    identity = identities["device"]
                    if role in identities and identities[role] != identity:
                        raise LiveAdmissionError("cross-session pair rejected")
                    identities[role] = identity
                    condition.notify_all()
                    while set(identities) != {"device", "guardian"}:
                        _remaining(deadline)
                        if errors:
                            raise LiveAdmissionError("other endpoint failed")
                        condition.wait(min(0.02, max(0, deadline - time.monotonic())))
                    if identities["guardian"] != identities["device"]:
                        raise LiveAdmissionError("cross-session pair rejected")
                response = {**hello, "identity": asdict(identity), "accepted": True}
                _send(wrapped, response, deadline)
                owned = control._OwnedHostTlsSocket(wrapped, connection_id=hello["connection_id"])
                decision = _decision(identity, role, hello["connection_id"])
                attestation = InjectedTlsConnectionAttestation(
                    True, True, True, decision.binding.endpoint_id, DEFAULT_ALPN,
                    wrapped.version(), hello["connection_id"],
                )
                stream = ConnectedTlsOrderedByteStream(
                    owned, attestation, decision,
                    ConnectedTlsStreamConfig(identity, role, enabled=True),
                )
                with condition:
                    streams[role] = stream
                    decisions[role] = decision
                    condition.notify_all()
            except BaseException:
                with condition:
                    errors.append(True)
                    condition.notify_all()
                (wrapped or raw).close()

        try:
            while len(workers) < 2:
                _remaining(deadline)
                if errors:
                    raise LiveAdmissionError("endpoint admission rejected")
                try:
                    raw, _ = self._listener.accept()
                except TimeoutError:
                    continue
                sockets.append(raw)
                worker = threading.Thread(target=admit, args=(raw,), daemon=True)
                workers.append(worker)
                worker.start()
            for worker in workers:
                worker.join(max(0, deadline - time.monotonic()))
            if errors or any(worker.is_alive() for worker in workers) or set(decisions) != {"device", "guardian"}:
                raise LiveAdmissionError("paired admission incomplete")
            self._listener.close()
            self._listener = None
            identity = identities["device"]
            bridge = ConcurrentBridgeConfig(
                identity=identity, frame_count=config.frame_count,
                max_runtime_ms=config.max_runtime_ms, timeout_steps=25,
                startup_grace_ns=20_000_000, frame_deadline_ns=1_000_000_000,
            )
            relay = ProcessLocalAuthenticatedRelay(AuthenticatedRelayConfig(bridge), RelayAdmissionRegistry())
            result = relay.run(device_stream=streams["device"], guardian_stream=streams["guardian"],
                               device_decision=decisions["device"], guardian_decision=decisions["guardian"])
            return {"result": result["result"], "mtls_role_admission": True,
                    "actual_mtls_connections": 2, "paired_media": result,
                    "p0_call": "NOT_RUN", "media_persisted": False}
        finally:
            if self._listener is not None:
                self._listener.close()
                self._listener = None
            for stream in list(streams.values()):
                if stream is not None:
                    stream.close()
            for item in sockets:
                try:
                    item.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                item.close()
            for worker in workers:
                worker.join(2.1)


def guardian_join(config: control.HostTlsConnectorConfig, *, run_id: str,
                  cert_file: str, key_file: str) -> tuple[EndpointIdentity, ConnectedTlsOrderedByteStream]:
    """Join an authorized run and receive its runtime descriptor over mTLS."""
    config.validate_for_open()
    _identifier(run_id, label="run id")
    deadline = time.monotonic() + config.overall_timeout_ms / 1000
    raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    wrapped = None
    try:
        context = client_context(cert_file, key_file)
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.maximum_version = ssl.TLSVersion.TLSv1_3
        context.hostname_checks_common_name = False
        context.set_alpn_protocols([DEFAULT_ALPN])
        context.load_verify_locations(cafile=config.ca_file, cadata=config.ca_pem)
        control._pin_windows_ipv4_interface(raw, config.windows_ipv4_interface_index)
        raw.bind((config.source_ipv4, 0))
        raw.settimeout(min(config.tcp_connect_timeout_ms / 1000, max(.001, deadline - time.monotonic())))
        raw.connect((config.peer_ipv4, config.peer_port))
        if raw.getsockname()[0] != config.source_ipv4 or raw.getpeername() != (config.peer_ipv4, config.peer_port):
            raise LiveAdmissionError("exact route mismatch")
        raw.settimeout(min(config.handshake_timeout_ms / 1000, max(.001, deadline - time.monotonic())))
        wrapped = context.wrap_socket(raw, server_hostname=config.tls_hostname)
        if wrapped.selected_alpn_protocol() != DEFAULT_ALPN:
            raise LiveAdmissionError("ALPN mismatch")
        wrapped.settimeout(.02)
        connection_id = "guardian-" + secrets.token_hex(16)
        request = _hello(run_id, "guardian", connection_id, None)
        _send(wrapped, request, deadline)
        response = _receive(wrapped, deadline)
        descriptor = response.get("identity")
        if (response.get("accepted") is not True
                or response != {**request, "identity": descriptor, "accepted": True}
                or not isinstance(descriptor, dict)):
            raise LiveAdmissionError("exact Guardian admission mismatch")
        identity = EndpointIdentity(**descriptor)
        identity.validate()
        decision = _decision(identity, "guardian", connection_id)
        attestation = InjectedTlsConnectionAttestation(
            True, True, True, identity.guardian_id, DEFAULT_ALPN, wrapped.version(),
            connection_id, config.tls_hostname,
        )
        owned = control._OwnedHostTlsSocket(wrapped, connection_id=connection_id)
        return identity, ConnectedTlsOrderedByteStream(
            owned, attestation, decision, ConnectedTlsStreamConfig(identity, "guardian", enabled=True),
        )
    except BaseException:
        (wrapped or raw).close()
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="One bounded mTLS CALL-020 relay. Configuration paths are private.")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--execute-authorized-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        values = json.loads(args.config.read_text(encoding="utf-8"))
        values["enabled"] = args.execute_authorized_run
        config = RelayRunConfig(**values)
        config.validate()
        if not args.execute_authorized_run:
            result = {"mode": "plan_only", "external_io_performed": False, "p0_call": "NOT_RUN"}
        else:
            relay = LiveMtlsRelay(config)
            relay.listen()
            result = relay.run()
        print(json.dumps(result, sort_keys=True))
        return 0 if result.get("result") != "FAIL" else 2
    except Exception:
        print(json.dumps({"result": "FAIL", "reason": "live_relay_failed", "p0_call": "NOT_RUN"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

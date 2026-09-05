"""CALL-020I process-local authenticated relay admission core.

The caller supplies two already-created, TLS-shaped ordered byte streams and
two distinct endpoint-specific external authentication decisions.  This module never listens,
connects, resolves DNS, opens a socket, loads a credential, or chooses an RTC
provider.  It verifies exact session/role/endpoint/source-clock ownership before
constructing existing CALL-020B ``FramedEndpoint`` objects, then delegates all
bounded full-duplex forwarding to the existing CALL-020C concurrent bridge.

Each injected stream wrapper must expose the connection identifier bound by its
external authenticator.  This core compares that identifier before media I/O;
it does not establish or verify the wrapper's TLS security itself.

The admission layer does not interpret a codec/media payload or persist it.
The reused strict framing layer necessarily parses each complete EGLM envelope
and CRC, transiently owns mutable payload buffers, and clears them; the
concurrent bridge retains metadata only.  Injected stream implementations and
external authenticators may make their own copies outside this module's
erasure boundary.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

from pc_simulator.ego_call_concurrent_bridge import (
    BridgeClock,
    ConcurrentBridgeConfig,
    ConcurrentBridgeRunFailed,
    ConcurrentDuplexMediaBridge,
    SystemMonotonicClock,
)
from pc_simulator.ego_call_media_io import (
    ByteStream,
    EndpointIdentity,
    FramedEndpoint,
    MediaIoError,
    MediaIoProtocolError,
    _identifier,
)


AUTHENTICATED_RELAY_VERSION = "egolink.ego_call_authenticated_relay.v0.1"
DEFAULT_AUTH_WINDOW_NS = 30_000_000_000
MAX_AUTH_WINDOW_NS = 300_000_000_000


def _bounded_int(value: object, *, label: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise MediaIoError(f"{label} must be an integer in [{minimum}, {maximum}]")
    return value


def _validate_stream_shape(stream: object) -> str:
    if any(
        not callable(getattr(stream, name, None))
        for name in ("read_exact", "write_all", "close")
    ):
        raise MediaIoError(
            "caller-injected TLS stream must provide read_exact, write_all, and close"
        )
    connection_id = getattr(stream, "connection_id", None)
    return _identifier(connection_id, label="injected_stream.connection_id")


@dataclass(frozen=True)
class RelayEndpointBinding:
    """Credential-free routing binding asserted by an external authenticator."""

    session_id: str
    role: str
    endpoint_id: str
    peer_endpoint_id: str
    source_clock_id: str
    connection_id: str

    def validate(self) -> None:
        for name in (
            "session_id",
            "endpoint_id",
            "peer_endpoint_id",
            "source_clock_id",
            "connection_id",
        ):
            _identifier(getattr(self, name), label=name)
        if self.role not in {"device", "guardian"}:
            raise MediaIoProtocolError("relay endpoint role must be device or guardian")
        if self.endpoint_id == self.peer_endpoint_id:
            raise MediaIoProtocolError("relay endpoint and peer identities must differ")


@dataclass(frozen=True)
class ExternalAuthenticationDecision:
    """An injected decision, not a credential verifier or authentication token."""

    decision_id: str
    authenticated: bool
    binding: RelayEndpointBinding
    valid_from_monotonic_ns: int
    expires_at_monotonic_ns: int

    def validate(self, *, now_ns: int, max_window_ns: int) -> None:
        _identifier(self.decision_id, label="decision_id")
        self.binding.validate()
        if type(self.authenticated) is not bool:
            raise MediaIoProtocolError("authenticated must be an explicit boolean")
        start = _bounded_int(
            self.valid_from_monotonic_ns,
            label="valid_from_monotonic_ns",
            minimum=0,
            maximum=2**63 - 1,
        )
        end = _bounded_int(
            self.expires_at_monotonic_ns,
            label="expires_at_monotonic_ns",
            minimum=0,
            maximum=2**63 - 1,
        )
        if end <= start or end - start > max_window_ns:
            raise MediaIoProtocolError("external authentication decision window is invalid")
        if not start <= now_ns < end:
            raise MediaIoProtocolError("external authentication decision is not currently valid")


@dataclass(frozen=True)
class AuthenticatedRelayConfig:
    bridge: ConcurrentBridgeConfig
    max_auth_window_ns: int = DEFAULT_AUTH_WINDOW_NS

    def validate(self) -> None:
        self.bridge.validate()
        _bounded_int(
            self.max_auth_window_ns,
            label="max_auth_window_ns",
            minimum=1_000_000,
            maximum=MAX_AUTH_WINDOW_NS,
        )


@dataclass(frozen=True)
class _Reservation:
    device_connection_id: str
    guardian_connection_id: str
    device_decision_id: str
    guardian_decision_id: str
    binding_fingerprint: tuple[str, ...]
    state: str


class RelayAdmissionError(MediaIoProtocolError):
    """Fail-closed admission rejection with redacted metadata."""

    def __init__(self, reason_code: str, *, close_errors: int = 0):
        super().__init__("authenticated relay admission rejected")
        self.reason_code = reason_code
        self.metadata = {
            "relay_version": AUTHENTICATED_RELAY_VERSION,
            "result": "FAIL",
            "stage": "admission",
            "reason_code": reason_code,
            "close_errors": close_errors,
            "media_io_started": False,
            "reported_connected": False,
            "identity_or_decision_value_exposed": False,
            "media_retained": False,
        }


class AuthenticatedRelayRunFailed(MediaIoError):
    """Bounded forwarding failure with metadata but no media or identities."""

    def __init__(self, metadata: dict[str, Any]):
        super().__init__("authenticated process-local relay run failed")
        self.metadata = metadata


class RelayAdmissionRegistry:
    """Bounded process-local ownership registry with non-evicting tombstones."""

    def __init__(self, *, max_sessions: int = 128):
        self.max_sessions = _bounded_int(
            max_sessions, label="max_sessions", minimum=1, maximum=4_096
        )
        self._lock = threading.Lock()
        self._sessions: dict[str, _Reservation] = {}
        self._connections: dict[str, tuple[str, str]] = {}
        self._decisions: dict[str, tuple[str, str]] = {}

    def reserve(
        self,
        *,
        device: ExternalAuthenticationDecision,
        guardian: ExternalAuthenticationDecision,
    ) -> None:
        session_id = device.binding.session_id
        fingerprint = (
            device.binding.role,
            device.binding.endpoint_id,
            device.binding.peer_endpoint_id,
            device.binding.source_clock_id,
            guardian.binding.role,
            guardian.binding.endpoint_id,
            guardian.binding.peer_endpoint_id,
            guardian.binding.source_clock_id,
        )
        reservation = _Reservation(
            device_connection_id=device.binding.connection_id,
            guardian_connection_id=guardian.binding.connection_id,
            device_decision_id=device.decision_id,
            guardian_decision_id=guardian.decision_id,
            binding_fingerprint=fingerprint,
            state="reserved",
        )
        with self._lock:
            previous = self._sessions.get(session_id)
            if previous is not None:
                exact = (
                    previous.device_connection_id == reservation.device_connection_id
                    and previous.guardian_connection_id
                    == reservation.guardian_connection_id
                    and previous.binding_fingerprint == fingerprint
                )
                raise RelayAdmissionError(
                    "duplicate_session_admission" if exact else "session_hijack_attempt"
                )
            for role, connection_id in (
                ("device", reservation.device_connection_id),
                ("guardian", reservation.guardian_connection_id),
            ):
                owner = self._connections.get(connection_id)
                if owner is not None:
                    reason = (
                        "duplicate_connection_admission"
                        if owner == (session_id, role)
                        else "cross_session_connection_reuse"
                    )
                    raise RelayAdmissionError(reason)
            for role, decision_id in (
                ("device", reservation.device_decision_id),
                ("guardian", reservation.guardian_decision_id),
            ):
                owner = self._decisions.get(decision_id)
                if owner is not None:
                    reason = (
                        "duplicate_authentication_decision"
                        if owner == (session_id, role)
                        else "cross_session_decision_reuse"
                    )
                    raise RelayAdmissionError(reason)
            if len(self._sessions) >= self.max_sessions:
                raise RelayAdmissionError("admission_registry_capacity_exhausted")
            self._sessions[session_id] = reservation
            self._connections[reservation.device_connection_id] = (
                session_id,
                "device",
            )
            self._connections[reservation.guardian_connection_id] = (
                session_id,
                "guardian",
            )
            self._decisions[reservation.device_decision_id] = (
                session_id,
                "device",
            )
            self._decisions[reservation.guardian_decision_id] = (
                session_id,
                "guardian",
            )

    def mark_terminal(self, session_id: str, state: str) -> None:
        if state not in {"completed", "failed", "cancelled"}:
            raise MediaIoError("registry terminal state is invalid")
        with self._lock:
            current = self._sessions.get(session_id)
            if current is None:
                return
            self._sessions[session_id] = _Reservation(
                device_connection_id=current.device_connection_id,
                guardian_connection_id=current.guardian_connection_id,
                device_decision_id=current.device_decision_id,
                guardian_decision_id=current.guardian_decision_id,
                binding_fingerprint=current.binding_fingerprint,
                state=state,
            )

    def audit(self) -> dict[str, Any]:
        with self._lock:
            states = {"reserved": 0, "completed": 0, "failed": 0, "cancelled": 0}
            for reservation in self._sessions.values():
                states[reservation.state] += 1
            return {
                "capacity": self.max_sessions,
                "session_count": len(self._sessions),
                "state_counts": states,
                "non_evicting_duplicate_guard": True,
                "raw_routing_ids_retained_in_process_for_duplicate_guard": True,
                "identity_values_exposed": False,
                "identity_values_logged_or_persisted": False,
            }


def _expected_binding(identity: EndpointIdentity, role: str) -> tuple[str, ...]:
    if role == "device":
        return (
            identity.session_id,
            "device",
            identity.device_id,
            identity.guardian_id,
            identity.uplink_clock_id,
        )
    return (
        identity.session_id,
        "guardian",
        identity.guardian_id,
        identity.device_id,
        identity.downlink_clock_id,
    )


def _binding_values(binding: RelayEndpointBinding) -> tuple[str, ...]:
    return (
        binding.session_id,
        binding.role,
        binding.endpoint_id,
        binding.peer_endpoint_id,
        binding.source_clock_id,
    )


def _close_streams(device_stream: ByteStream, guardian_stream: ByteStream) -> int:
    errors = 0
    seen: set[int] = set()
    for stream in (device_stream, guardian_stream):
        if id(stream) in seen:
            continue
        seen.add(id(stream))
        try:
            stream.close()
        except Exception:
            errors += 1
    return errors


class ProcessLocalAuthenticatedRelay:
    """Single-use paired admission plus delegated four-worker media forwarding."""

    def __init__(
        self,
        config: AuthenticatedRelayConfig,
        registry: RelayAdmissionRegistry,
        *,
        clock: BridgeClock | None = None,
    ):
        config.validate()
        if not isinstance(registry, RelayAdmissionRegistry):
            raise MediaIoError("a process-scoped RelayAdmissionRegistry is required")
        self.config = config
        self.registry = registry
        self.clock = clock or SystemMonotonicClock()
        self._lock = threading.Lock()
        self._state = "new"
        self._bridge: ConcurrentDuplexMediaBridge | None = None
        self._device_stream: ByteStream | None = None
        self._guardian_stream: ByteStream | None = None
        self._device_authenticated = False
        self._guardian_authenticated = False
        self._pair_reserved = False
        self._cancel_requested = False
        self._close_errors = 0

    def _now(self) -> int:
        now = self.clock.monotonic_ns()
        if type(now) is not int or now < 0:
            raise MediaIoError("relay clock must return a non-negative integer")
        return now

    def _reject(
        self,
        reason_code: str,
        device_stream: ByteStream,
        guardian_stream: ByteStream,
        *,
        terminal_state: str | None = "failed",
    ) -> RelayAdmissionError:
        close_errors = _close_streams(device_stream, guardian_stream)
        with self._lock:
            if terminal_state is not None:
                self._state = terminal_state
            self._close_errors += close_errors
        return RelayAdmissionError(reason_code, close_errors=close_errors)

    def _validate_admission_pair(
        self,
        *,
        device: ExternalAuthenticationDecision,
        guardian: ExternalAuthenticationDecision,
        device_stream_connection_id: str,
        guardian_stream_connection_id: str,
    ) -> None:
        now = self._now()
        device.validate(now_ns=now, max_window_ns=self.config.max_auth_window_ns)
        guardian.validate(now_ns=now, max_window_ns=self.config.max_auth_window_ns)
        if device.binding.role != "device" or guardian.binding.role != "guardian":
            raise RelayAdmissionError("endpoint_roles_not_distinctly_bound")
        if not device.authenticated or not guardian.authenticated:
            raise RelayAdmissionError("both_endpoints_must_authenticate")
        if device.decision_id == guardian.decision_id:
            raise RelayAdmissionError("duplicate_authentication_decision")
        if device.binding.connection_id == guardian.binding.connection_id:
            raise RelayAdmissionError("duplicate_endpoint_connection")
        if device.binding.connection_id != device_stream_connection_id:
            raise RelayAdmissionError("device_authenticated_stream_binding_mismatch")
        if guardian.binding.connection_id != guardian_stream_connection_id:
            raise RelayAdmissionError("guardian_authenticated_stream_binding_mismatch")
        identity = self.config.bridge.identity
        if _binding_values(device.binding) != _expected_binding(identity, "device"):
            raise RelayAdmissionError("device_session_role_endpoint_or_clock_mismatch")
        if _binding_values(guardian.binding) != _expected_binding(identity, "guardian"):
            raise RelayAdmissionError("guardian_session_role_endpoint_or_clock_mismatch")

    def run(
        self,
        *,
        device_stream: ByteStream,
        guardian_stream: ByteStream,
        device_decision: ExternalAuthenticationDecision,
        guardian_decision: ExternalAuthenticationDecision,
    ) -> dict[str, Any]:
        device_stream_connection_id = _validate_stream_shape(device_stream)
        guardian_stream_connection_id = _validate_stream_shape(guardian_stream)
        with self._lock:
            if self._state != "new":
                already_used = True
                cancelled_before_admission = False
            elif self._cancel_requested:
                already_used = False
                cancelled_before_admission = True
                self._state = "cancelled"
            else:
                already_used = False
                cancelled_before_admission = False
                self._state = "admitting"
                self._device_stream = device_stream
                self._guardian_stream = guardian_stream
        if already_used:
            raise self._reject(
                "relay_instance_is_single_use",
                device_stream,
                guardian_stream,
                terminal_state=None,
            )
        if cancelled_before_admission:
            raise self._reject(
                "cancelled_before_admission",
                device_stream,
                guardian_stream,
                terminal_state="cancelled",
            )
        if device_stream is guardian_stream:
            raise self._reject(
                "endpoint_streams_must_be_distinct", device_stream, guardian_stream
            )

        try:
            self._validate_admission_pair(
                device=device_decision,
                guardian=guardian_decision,
                device_stream_connection_id=device_stream_connection_id,
                guardian_stream_connection_id=guardian_stream_connection_id,
            )
        except RelayAdmissionError as error:
            rejected = self._reject(
                error.reason_code, device_stream, guardian_stream
            )
            raise rejected from error
        except Exception as error:
            rejected = self._reject(
                "authentication_decision_invalid", device_stream, guardian_stream
            )
            raise rejected from error

        reservation_error: Exception | None = None
        with self._lock:
            cancelled_before_reserve = self._cancel_requested
            if cancelled_before_reserve:
                self._state = "cancelled"
            else:
                try:
                    self.registry.reserve(
                        device=device_decision, guardian=guardian_decision
                    )
                except Exception as error:
                    reservation_error = error
                else:
                    self._device_authenticated = True
                    self._guardian_authenticated = True
                    self._pair_reserved = True
                    self._state = "admitted"
        if cancelled_before_reserve:
            raise self._reject(
                "cancelled_before_admission",
                device_stream,
                guardian_stream,
                terminal_state="cancelled",
            )
        if reservation_error is not None:
            if isinstance(reservation_error, RelayAdmissionError):
                rejected = self._reject(
                    reservation_error.reason_code, device_stream, guardian_stream
                )
            else:
                rejected = self._reject(
                    "admission_registry_failure", device_stream, guardian_stream
                )
            raise rejected from reservation_error

        with self._lock:
            cancelled_before_run = self._cancel_requested
        if cancelled_before_run:
            self.registry.mark_terminal(
                self.config.bridge.identity.session_id, "cancelled"
            )
            raise self._reject(
                "cancelled_before_media",
                device_stream,
                guardian_stream,
                terminal_state="cancelled",
            )

        identity = self.config.bridge.identity
        device_endpoint = FramedEndpoint(
            device_stream,
            identity,
            inbound_direction="uplink",
            outbound_direction="downlink",
        )
        guardian_endpoint = FramedEndpoint(
            guardian_stream,
            identity,
            inbound_direction="downlink",
            outbound_direction="uplink",
        )
        bridge = ConcurrentDuplexMediaBridge(self.config.bridge, clock=self.clock)
        with self._lock:
            self._bridge = bridge
            self._state = "running"
            cancel_now = self._cancel_requested
        if cancel_now:
            bridge.request_stop()

        try:
            bridge_result = bridge.run(
                wearable=device_endpoint,
                relay=guardian_endpoint,
            )
        except ConcurrentBridgeRunFailed as error:
            with self._lock:
                cancelled = self._cancel_requested
                self._state = "cancelled" if cancelled else "failed"
            terminal_state = "cancelled" if cancelled else "failed"
            self.registry.mark_terminal(identity.session_id, terminal_state)
            failure = {
                "relay_version": AUTHENTICATED_RELAY_VERSION,
                "result": "FAIL",
                "stage": "forwarding",
                "reason_code": "cancelled" if cancelled else "endpoint_or_bridge_failure",
                "authentication": {
                    "device": "accepted",
                    "guardian": "accepted",
                    "paired_before_media": True,
                },
                "worker_model": error.metadata.get("worker_model", {}),
                "direction_stats": error.metadata.get("direction_stats", {}),
                "buffer_lifecycle": error.metadata.get("buffer_lifecycle", {}),
                "connection_truth": {
                    "both_endpoints_authenticated": True,
                    "process_local_full_duplex_completed": False,
                    "actual_tls_endpoint_connection": "NOT_RUN",
                    "reported_connected": False,
                },
                "failure_message_retained": False,
                "media_retained_or_logged": False,
                "identity_or_decision_value_exposed": False,
                "raw_routing_ids_retained_in_process_for_duplicate_guard": True,
                "p0_call": "NOT_RUN",
            }
            raise AuthenticatedRelayRunFailed(failure) from error
        except Exception as error:
            _close_streams(device_stream, guardian_stream)
            with self._lock:
                cancelled = self._cancel_requested
                self._state = "cancelled" if cancelled else "failed"
            self.registry.mark_terminal(
                identity.session_id, "cancelled" if cancelled else "failed"
            )
            failure = {
                "relay_version": AUTHENTICATED_RELAY_VERSION,
                "result": "FAIL",
                "stage": "forwarding",
                "reason_code": "cancelled" if cancelled else "relay_internal_failure",
                "authentication": {
                    "device": "accepted",
                    "guardian": "accepted",
                    "paired_before_media": True,
                },
                "connection_truth": {
                    "both_endpoints_authenticated": True,
                    "process_local_full_duplex_completed": False,
                    "actual_tls_endpoint_connection": "NOT_RUN",
                    "reported_connected": False,
                },
                "failure_message_retained": False,
                "media_retained_or_logged": False,
                "identity_or_decision_value_exposed": False,
                "raw_routing_ids_retained_in_process_for_duplicate_guard": True,
                "p0_call": "NOT_RUN",
            }
            raise AuthenticatedRelayRunFailed(failure) from error

        succeeded = bridge_result.get("result") == "PASS"
        with self._lock:
            self._state = "completed" if succeeded else "failed"
        self.registry.mark_terminal(
            identity.session_id, "completed" if succeeded else "failed"
        )
        result = {
            "relay_version": AUTHENTICATED_RELAY_VERSION,
            "result": "PASS" if succeeded else "FAIL",
            "authentication": {
                "device": "accepted",
                "guardian": "accepted",
                "distinct_endpoint_decisions": True,
                "exact_pair_reserved_before_media": True,
                "credential_material_received": False,
            },
            "forwarding": {
                "engine": "existing_call020c_concurrent_bridge",
                "complete_eglm_frames_only": True,
                "reader_workers": bridge_result["worker_model"]["reader_workers"],
                "writer_workers": bridge_result["worker_model"]["writer_workers"],
                "independent_direction_queues": bridge_result["worker_model"][
                    "independent_direction_queues"
                ],
                "clock_and_deadline": bridge_result["clock_and_deadline"],
                "direction_stats": bridge_result["direction_stats"],
                "buffer_lifecycle": bridge_result["buffer_lifecycle"],
            },
            "connection_truth": {
                "both_endpoints_authenticated": True,
                "process_local_full_duplex_completed": succeeded,
                "actual_tls_endpoint_connection": "NOT_RUN",
                "reported_connected": False,
            },
            "privacy": {
                "media_decoded_by_relay_admission": False,
                "media_recorded": False,
                "media_persisted": False,
                "media_logged": False,
                "identity_or_decision_value_in_audit": False,
                "raw_routing_ids_retained_in_process_for_duplicate_guard": True,
            },
            "claims": {
                "listener_or_outbound_connection": "NOT_RUN",
                "external_authenticator_security": "unverified_injected_decision",
                "tls_stream_security": "unverified_caller_injected_stream",
                "provider_selected": False,
                "p0_call": "NOT_RUN",
            },
        }
        return result

    def request_cancel(self) -> None:
        with self._lock:
            self._cancel_requested = True
            bridge = self._bridge
            device_stream = self._device_stream
            guardian_stream = self._guardian_stream
        if bridge is not None:
            bridge.request_stop()
        if device_stream is not None and guardian_stream is not None:
            close_errors = _close_streams(device_stream, guardian_stream)
            with self._lock:
                self._close_errors += close_errors

    def close(self) -> None:
        self.request_cancel()

    def audit(self) -> dict[str, Any]:
        with self._lock:
            state = self._state
            return {
                "relay_version": AUTHENTICATED_RELAY_VERSION,
                "state": state,
                "device_authenticated": self._device_authenticated,
                "guardian_authenticated": self._guardian_authenticated,
                "pair_reserved_before_media": self._pair_reserved,
                "cancel_requested": self._cancel_requested,
                "close_errors": self._close_errors,
                "reported_connected": False,
                "identity_or_decision_value_exposed": False,
                "raw_routing_ids_retained_in_process_for_duplicate_guard": True,
                "media_recorded_persisted_or_logged": False,
                "listener_socket_or_connection_created": False,
            }

"""CALL-020J strict adapter for a caller-injected connected TLS socket.

This module never creates, connects, listens on, or resolves anything.  The
caller supplies an already-connected TLS socket-shaped object, a finite socket
timeout, an immutable attestation produced by the caller's TLS/authentication
layer, and the matching CALL-020I external authentication decision. Passing the
socket to the constructor transfers close responsibility to this adapter;
every construction rejection performs best-effort out-of-band cancellation
and close.

Python's ``ssl.SSLSocket`` does not expose a trustworthy "certificate chain was
verified" result after construction, nor does this module parse certificates.
Certificate and peer-identity verification are therefore explicit attestation
inputs and remain outside this adapter's trust boundary.  The adapter does
cross-check the attested ALPN and TLS version against the injected socket and
binds the socket's connection identifier to the exact CALL-020I decision before
any media I/O.

One read and one write may proceed concurrently.  Operations are bounded by a
finite preconfigured socket timeout, a monotonic operation deadline, a callback
count, and a transfer-size cap.  The adapter cannot preempt a socket wrapper
that violates its timeout/cancellation contract.  It never logs or persists
media.  Mutable write copies and failed read buffers are cleared in ``finally``;
successfully returned read buffers transfer to the caller's ownership.
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from typing import Any, Protocol

from pc_simulator.ego_call_authenticated_relay import (
    DEFAULT_AUTH_WINDOW_NS,
    MAX_AUTH_WINDOW_NS,
    ExternalAuthenticationDecision,
)
from pc_simulator.ego_call_media_io import (
    EndpointIdentity,
    MediaIoError,
    MediaIoProtocolError,
    MediaIoTimeout,
    _identifier,
    _zero,
)


TLS_STREAM_ADAPTER_VERSION = "egolink.ego_call_tls_stream_adapter.v0.1"
DEFAULT_ALPN = "egolink-call020-media-v1"
MAX_TRANSFER_BYTES = 4_096
_NS_PER_MS = 1_000_000
_SUPPORTED_TLS_VERSIONS = {"TLSv1.2", "TLSv1.3"}


class InjectedConnectedTlsSocket(Protocol):
    """Caller-created connected TLS wrapper whose close ownership is transferred.

    ``recv_into`` and ``send`` have the usual blocking socket shape and must
    honor the finite value returned by ``gettimeout``. ``cancel_pending_io`` is
    an out-of-band lifecycle hook supplied by the caller because Python cannot
    portably and synchronously preempt an arbitrary TLS operation.
    """

    connection_id: str

    def recv_into(self, target: memoryview, size: int) -> int: ...

    def send(self, source: memoryview) -> int: ...

    def gettimeout(self) -> float | None: ...

    def selected_alpn_protocol(self) -> str | None: ...

    def version(self) -> str | None: ...

    def cancel_pending_io(self) -> None: ...

    def close(self) -> None: ...


class MonotonicClock(Protocol):
    def monotonic_ns(self) -> int: ...


class SystemMonotonicClock:
    def monotonic_ns(self) -> int:
        return time.monotonic_ns()


class InjectedTlsSocketTimeout(TimeoutError):
    """Optional precise timeout raised by the injected socket wrapper.

    ``progress=0`` proves zero application-byte progress.  A positive value or
    ``None`` means partial or unknown progress and is terminal for an ordered
    byte stream.  A plain ``TimeoutError`` is treated as zero progress for a
    receive call but unknown progress for a send call.
    """

    def __init__(self, message: str, *, progress: int | None):
        super().__init__(message)
        if progress is not None and (type(progress) is not int or progress < 0):
            raise ValueError("TLS timeout progress must be a non-negative int or None")
        self.progress = progress


@dataclass(frozen=True)
class InjectedTlsConnectionAttestation:
    """Immutable facts asserted by the external TLS/authentication layer.

    No certificate, credential, key, token, or subject-alt-name list is stored
    here.  This object is evidence supplied by the caller, not cryptographic
    verification performed by this module.
    """

    handshake_complete: bool
    certificate_chain_verified: bool
    peer_identity_verified: bool
    peer_identity: str
    selected_alpn: str
    tls_version: str
    connection_id: str
    verified_server_hostname: str | None = None

    def validate(self) -> None:
        for name in (
            "handshake_complete",
            "certificate_chain_verified",
            "peer_identity_verified",
        ):
            if type(getattr(self, name)) is not bool:
                raise MediaIoProtocolError(f"{name} must be an explicit boolean")
        _identifier(self.peer_identity, label="attested peer_identity")
        _identifier(self.connection_id, label="attested connection_id")
        _bounded_ascii_token(self.selected_alpn, label="attested selected_alpn")
        if self.tls_version not in _SUPPORTED_TLS_VERSIONS:
            raise MediaIoProtocolError("attested TLS version must be TLSv1.2 or TLSv1.3")
        if self.verified_server_hostname is not None:
            _bounded_ascii_token(
                self.verified_server_hostname,
                label="attested verified_server_hostname",
            )


@dataclass(frozen=True)
class ConnectedTlsStreamConfig:
    """Role/session expectation and finite I/O bounds; disabled by default."""

    identity: EndpointIdentity
    role: str
    enabled: bool = False
    expected_alpn: str = DEFAULT_ALPN
    per_call_timeout_ms: int = 20
    max_operation_timeout_ms: int = 1_000
    max_socket_calls_per_operation: int = 4_096
    max_transfer_bytes: int = MAX_TRANSFER_BYTES
    max_auth_window_ns: int = DEFAULT_AUTH_WINDOW_NS

    def validate(self) -> None:
        if type(self.enabled) is not bool:
            raise MediaIoError("enabled must be an explicit boolean")
        self.identity.validate()
        if self.role not in {"device", "guardian"}:
            raise MediaIoProtocolError("TLS stream role must be device or guardian")
        _bounded_ascii_token(self.expected_alpn, label="expected_alpn")
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
            self.max_socket_calls_per_operation,
            label="max_socket_calls_per_operation",
            minimum=1,
            maximum=65_536,
        )
        _bounded_int(
            self.max_transfer_bytes,
            label="max_transfer_bytes",
            minimum=1,
            maximum=MAX_TRANSFER_BYTES,
        )
        _bounded_int(
            self.max_auth_window_ns,
            label="max_auth_window_ns",
            minimum=1_000_000,
            maximum=MAX_AUTH_WINDOW_NS,
        )


@dataclass(slots=True)
class _OperationBudget:
    deadline_ns: int
    last_clock_ns: int
    calls: int = 0
    progress_bytes: int = 0


class TlsStreamAdmissionError(MediaIoProtocolError):
    """Pre-media rejection with redacted, metadata-only evidence."""

    def __init__(self, reason_code: str, *, cancel_errors: int = 0, close_errors: int = 0):
        super().__init__("connected TLS stream admission rejected")
        self.reason_code = reason_code
        self.metadata = {
            "adapter_version": TLS_STREAM_ADAPTER_VERSION,
            "result": "FAIL",
            "stage": "tls_stream_admission",
            "reason_code": reason_code,
            "media_io_started": False,
            "socket_connected_by_adapter": False,
            "tls_handshake_performed_by_adapter": False,
            "certificate_verified_by_adapter": False,
            "identity_or_connection_value_exposed": False,
            "cancel_errors": cancel_errors,
            "close_errors": close_errors,
            "media_logged_or_persisted": False,
        }


def _bounded_int(value: object, *, label: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise MediaIoError(f"{label} must be an integer in [{minimum}, {maximum}]")
    return value


def _bounded_ascii_token(value: object, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 128
        or len(value.encode("ascii", errors="ignore")) != len(value)
        or any(ord(character) < 0x21 or ord(character) > 0x7E for character in value)
    ):
        raise MediaIoProtocolError(
            f"{label} must be 1-128 visible ASCII characters"
        )
    return value


def _validate_socket_shape(tls_socket: object) -> None:
    for name in (
        "recv_into",
        "send",
        "gettimeout",
        "selected_alpn_protocol",
        "version",
        "cancel_pending_io",
        "close",
    ):
        if not callable(getattr(tls_socket, name, None)):
            raise TlsStreamAdmissionError("injected_tls_socket_shape_invalid")
    _identifier(
        getattr(tls_socket, "connection_id", None),
        label="injected TLS socket connection_id",
    )


def _expected_binding_values(
    identity: EndpointIdentity, role: str, connection_id: str
) -> tuple[str, ...]:
    if role == "device":
        return (
            identity.session_id,
            "device",
            identity.device_id,
            identity.guardian_id,
            identity.uplink_clock_id,
            connection_id,
        )
    return (
        identity.session_id,
        "guardian",
        identity.guardian_id,
        identity.device_id,
        identity.downlink_clock_id,
        connection_id,
    )


def _decision_binding_values(
    decision: ExternalAuthenticationDecision,
) -> tuple[str, ...]:
    binding = decision.binding
    return (
        binding.session_id,
        binding.role,
        binding.endpoint_id,
        binding.peer_endpoint_id,
        binding.source_clock_id,
        binding.connection_id,
    )


def _cancel_and_close_rejected_socket(tls_socket: object) -> tuple[int, int]:
    cancel_errors = 0
    close_errors = 0
    cancel = getattr(tls_socket, "cancel_pending_io", None)
    if callable(cancel):
        try:
            cancel()
        except Exception:
            cancel_errors += 1
    else:
        cancel_errors += 1
    close = getattr(tls_socket, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            close_errors += 1
    else:
        close_errors += 1
    return cancel_errors, close_errors


class ConnectedTlsOrderedByteStream:
    """Strict, single-connection ByteStream consumed by CALL-020I.

    After explicit enable/config validation, construction performs only metadata
    queries against a caller-injected, already-connected TLS socket. Rejection
    may cancel/close it but issues no media call. No media call is issued until
    ``read_exact`` or ``write_all`` is invoked by the framed relay bridge.
    """

    def __init__(
        self,
        tls_socket: InjectedConnectedTlsSocket,
        attestation: InjectedTlsConnectionAttestation,
        decision: ExternalAuthenticationDecision,
        config: ConnectedTlsStreamConfig,
        *,
        clock: MonotonicClock | None = None,
    ):
        if not isinstance(config, ConnectedTlsStreamConfig):
            cancel_errors, close_errors = _cancel_and_close_rejected_socket(tls_socket)
            raise TlsStreamAdmissionError(
                "tls_stream_config_required",
                cancel_errors=cancel_errors,
                close_errors=close_errors,
            )
        if config.enabled is not True:
            cancel_errors, close_errors = _cancel_and_close_rejected_socket(tls_socket)
            raise TlsStreamAdmissionError(
                "tls_stream_adapter_disabled",
                cancel_errors=cancel_errors,
                close_errors=close_errors,
            )

        self._read_lock = threading.RLock()
        self._write_lock = threading.RLock()
        self._close_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._clock = clock or SystemMonotonicClock()
        self._socket: InjectedConnectedTlsSocket | None = tls_socket
        self._config: ConnectedTlsStreamConfig | None = config
        self._connection_id: str | None = None
        self._closed = False
        self._terminal = False
        self._cancel_requested = False
        self._cancel_sent = False
        self._attestation_accepted = False
        self._sensitive_references_cleared = False
        self._read_bytes = 0
        self._written_bytes = 0
        self._read_operations = 0
        self._write_operations = 0
        self._zero_progress_timeouts = 0
        self._terminal_errors = 0
        self._cancel_errors = 0
        self._close_errors = 0
        self._owned_buffer_zeroization_failures = 0

        try:
            config.validate()
            self._admit(tls_socket, attestation, decision, config)
        except TlsStreamAdmissionError as error:
            cancel_errors, close_errors = _cancel_and_close_rejected_socket(tls_socket)
            with self._state_lock:
                self._closed = True
                self._terminal = True
                self._socket = None
                self._config = None
                self._connection_id = None
                self._sensitive_references_cleared = True
            raise TlsStreamAdmissionError(
                error.reason_code,
                cancel_errors=cancel_errors,
                close_errors=close_errors,
            ) from error
        except Exception as error:
            cancel_errors, close_errors = _cancel_and_close_rejected_socket(tls_socket)
            with self._state_lock:
                self._closed = True
                self._terminal = True
                self._socket = None
                self._config = None
                self._connection_id = None
                self._sensitive_references_cleared = True
            raise TlsStreamAdmissionError(
                "tls_stream_attestation_or_socket_invalid",
                cancel_errors=cancel_errors,
                close_errors=close_errors,
            ) from error

    @property
    def connection_id(self) -> str:
        """Return the admitted routing ID required by CALL-020I, never audit it."""

        with self._state_lock:
            connection_id = self._connection_id
        if connection_id is None:
            raise MediaIoError("TLS stream connection identity is unavailable")
        return connection_id

    def _clock_now(self) -> int:
        now = self._clock.monotonic_ns()
        if type(now) is not int or now < 0:
            raise MediaIoError("TLS stream clock must return a non-negative integer")
        return now

    def _admit(
        self,
        tls_socket: InjectedConnectedTlsSocket,
        attestation: InjectedTlsConnectionAttestation,
        decision: ExternalAuthenticationDecision,
        config: ConnectedTlsStreamConfig,
    ) -> None:
        _validate_socket_shape(tls_socket)
        if not isinstance(attestation, InjectedTlsConnectionAttestation):
            raise TlsStreamAdmissionError("immutable_tls_attestation_required")
        if not isinstance(decision, ExternalAuthenticationDecision):
            raise TlsStreamAdmissionError("external_authentication_decision_required")
        try:
            attestation.validate()
            now_ns = self._clock_now()
            decision.validate(
                now_ns=now_ns, max_window_ns=config.max_auth_window_ns
            )
        except Exception as error:
            raise TlsStreamAdmissionError(
                "tls_attestation_or_authentication_decision_invalid"
            ) from error
        if not (
            attestation.handshake_complete
            and attestation.certificate_chain_verified
            and attestation.peer_identity_verified
        ):
            raise TlsStreamAdmissionError("tls_certificate_or_peer_not_verified")
        if not decision.authenticated:
            raise TlsStreamAdmissionError("external_authentication_rejected")

        socket_connection_id = _identifier(
            getattr(tls_socket, "connection_id", None),
            label="injected TLS socket connection_id",
        )
        expected_binding = _expected_binding_values(
            config.identity, config.role, socket_connection_id
        )
        if _decision_binding_values(decision) != expected_binding:
            raise TlsStreamAdmissionError("tls_stream_session_binding_mismatch")
        if attestation.connection_id != socket_connection_id:
            raise TlsStreamAdmissionError("tls_attestation_connection_mismatch")
        if attestation.peer_identity != decision.binding.endpoint_id:
            raise TlsStreamAdmissionError("tls_attested_peer_identity_mismatch")
        if attestation.selected_alpn != config.expected_alpn:
            raise TlsStreamAdmissionError("tls_attested_alpn_mismatch")

        try:
            actual_alpn = tls_socket.selected_alpn_protocol()
            actual_tls_version = tls_socket.version()
            socket_timeout_seconds = tls_socket.gettimeout()
        except Exception as error:
            raise TlsStreamAdmissionError("tls_socket_metadata_query_failed") from error
        if actual_alpn != attestation.selected_alpn:
            raise TlsStreamAdmissionError("tls_socket_alpn_mismatch")
        if actual_tls_version != attestation.tls_version:
            raise TlsStreamAdmissionError("tls_socket_version_mismatch")
        if (
            isinstance(socket_timeout_seconds, bool)
            or not isinstance(socket_timeout_seconds, (int, float))
            or not math.isfinite(socket_timeout_seconds)
            or socket_timeout_seconds <= 0
            or socket_timeout_seconds * 1_000 > config.per_call_timeout_ms
        ):
            raise TlsStreamAdmissionError("tls_socket_timeout_is_not_finite_and_bounded")

        with self._state_lock:
            self._connection_id = socket_connection_id
            self._attestation_accepted = True

    def _active_config(self) -> ConnectedTlsStreamConfig:
        with self._state_lock:
            config = self._config
            closed = self._closed
            cancelled = self._cancel_requested
        if closed or cancelled or config is None:
            raise MediaIoError("connected TLS ordered stream is closed or cancelled")
        return config

    def _active_socket(self) -> InjectedConnectedTlsSocket:
        with self._state_lock:
            tls_socket = self._socket
            expected_connection_id = self._connection_id
            closed = self._closed
            cancelled = self._cancel_requested
        if closed or cancelled or tls_socket is None or expected_connection_id is None:
            raise MediaIoError("connected TLS ordered stream is closed or cancelled")
        try:
            actual_connection_id = _identifier(
                getattr(tls_socket, "connection_id", None),
                label="injected TLS socket connection_id",
            )
        except Exception as error:
            self._fail_terminal()
            raise MediaIoProtocolError(
                "injected TLS socket connection identity became invalid"
            ) from error
        if actual_connection_id != expected_connection_id:
            self._fail_terminal()
            raise MediaIoProtocolError(
                "injected TLS socket connection identity changed after admission"
            )
        return tls_socket

    def _new_budget(
        self, timeout_steps: int, config: ConnectedTlsStreamConfig
    ) -> _OperationBudget:
        steps = _bounded_int(
            timeout_steps, label="timeout_steps", minimum=1, maximum=1_000
        )
        start_ns = self._clock_now()
        timeout_ms = min(
            config.max_operation_timeout_ms,
            steps * config.per_call_timeout_ms,
        )
        return _OperationBudget(
            deadline_ns=start_ns + timeout_ms * _NS_PER_MS,
            last_clock_ns=start_ns,
        )

    def _remaining(self, budget: _OperationBudget) -> None:
        now = self._clock_now()
        if now < budget.last_clock_ns:
            self._fail_terminal()
            raise MediaIoProtocolError("TLS stream monotonic clock regressed")
        budget.last_clock_ns = now
        if now >= budget.deadline_ns:
            self._raise_timeout(
                budget,
                "TLS ordered-stream operation deadline expired",
                explicit_progress=None if budget.progress_bytes else 0,
            )

    def _before_socket_call(
        self, budget: _OperationBudget, config: ConnectedTlsStreamConfig
    ) -> InjectedConnectedTlsSocket:
        if budget.calls >= config.max_socket_calls_per_operation:
            self._raise_timeout(
                budget,
                "TLS ordered-stream callback budget exhausted",
                explicit_progress=None if budget.progress_bytes else 0,
            )
        self._remaining(budget)
        tls_socket = self._active_socket()
        budget.calls += 1
        return tls_socket

    def _check_after_socket_call(self, budget: _OperationBudget) -> None:
        with self._state_lock:
            cancelled = self._cancel_requested
        if cancelled:
            raise MediaIoError("connected TLS ordered stream was cancelled")
        now = self._clock_now()
        if now < budget.last_clock_ns:
            self._fail_terminal()
            raise MediaIoProtocolError("TLS stream monotonic clock regressed")
        budget.last_clock_ns = now
        if now > budget.deadline_ns:
            self._raise_timeout(
                budget,
                "TLS ordered-stream callback completed after its deadline",
                explicit_progress=None,
            )

    def _request_cancel_once(self) -> None:
        with self._state_lock:
            self._cancel_requested = True
            if self._cancel_sent:
                return
            self._cancel_sent = True
            tls_socket = self._socket
        if tls_socket is None:
            return
        try:
            tls_socket.cancel_pending_io()
        except Exception:
            with self._state_lock:
                self._cancel_errors += 1

    def _fail_terminal(self) -> None:
        with self._state_lock:
            if not self._terminal:
                self._terminal_errors += 1
            self._terminal = True
            self._closed = True
        self._request_cancel_once()

    def _raise_timeout(
        self,
        budget: _OperationBudget,
        message: str,
        *,
        explicit_progress: int | None,
    ) -> None:
        retry_safe = budget.progress_bytes == 0 and explicit_progress == 0
        if retry_safe:
            with self._state_lock:
                self._zero_progress_timeouts += 1
        else:
            self._fail_terminal()
        raise MediaIoTimeout(message, retry_safe=retry_safe)

    def read_exact(self, size: int, *, timeout_steps: int) -> bytearray:
        with self._read_lock:
            config = self._active_config()
            requested = _bounded_int(
                size,
                label="read size",
                minimum=1,
                maximum=config.max_transfer_bytes,
            )
            budget = self._new_budget(timeout_steps, config)
            result = bytearray(requested)
            result_view = memoryview(result)
            offset = 0
            success = False
            try:
                while offset < requested:
                    tls_socket = self._before_socket_call(budget, config)
                    remaining = requested - offset
                    target = result_view[offset:]
                    try:
                        try:
                            count = tls_socket.recv_into(target, remaining)
                        except InjectedTlsSocketTimeout as error:
                            self._raise_timeout(
                                budget,
                                "injected TLS receive timed out",
                                explicit_progress=error.progress,
                            )
                        except TimeoutError as error:
                            self._raise_timeout(
                                budget,
                                "injected TLS receive timed out",
                                explicit_progress=0,
                            )
                        except Exception as error:
                            self._fail_terminal()
                            raise MediaIoError(
                                "injected TLS receive failed with unknown progress"
                            ) from error
                    finally:
                        target.release()
                    if type(count) is not int or not 0 <= count <= remaining:
                        self._fail_terminal()
                        raise MediaIoProtocolError(
                            "injected TLS receive returned an invalid byte count"
                        )
                    if count == 0:
                        self._fail_terminal()
                        raise MediaIoError("injected TLS peer reached EOF during exact read")
                    offset += count
                    budget.progress_bytes += count
                    self._check_after_socket_call(budget)
                with self._state_lock:
                    self._read_operations += 1
                    self._read_bytes += requested
                success = True
                return result
            finally:
                result_view.release()
                if not success:
                    _zero(result)

    def write_all(self, data: memoryview, *, timeout_steps: int) -> None:
        if not isinstance(data, memoryview):
            raise MediaIoError("TLS write requires a memoryview")
        if (
            data.ndim != 1
            or not data.c_contiguous
            or data.itemsize != 1
            or data.nbytes != len(data)
        ):
            raise MediaIoError(
                "TLS write buffer must be one contiguous single-byte view"
            )
        with self._write_lock:
            config = self._active_config()
            _bounded_int(
                len(data),
                label="write size",
                minimum=1,
                maximum=config.max_transfer_bytes,
            )
            budget = self._new_budget(timeout_steps, config)
            owned = bytearray(data)
            offset = 0
            try:
                while offset < len(owned):
                    tls_socket = self._before_socket_call(budget, config)
                    source = memoryview(owned)[offset:]
                    try:
                        try:
                            count = tls_socket.send(source)
                        except InjectedTlsSocketTimeout as error:
                            self._raise_timeout(
                                budget,
                                "injected TLS send timed out",
                                explicit_progress=error.progress,
                            )
                        except TimeoutError as error:
                            self._raise_timeout(
                                budget,
                                "injected TLS send timed out with unknown progress",
                                explicit_progress=None,
                            )
                        except Exception as error:
                            self._fail_terminal()
                            raise MediaIoError(
                                "injected TLS send failed with unknown progress"
                            ) from error
                    finally:
                        source.release()
                    remaining = len(owned) - offset
                    if type(count) is not int or not 0 <= count <= remaining:
                        self._fail_terminal()
                        raise MediaIoProtocolError(
                            "injected TLS send returned an invalid byte count"
                        )
                    if count == 0:
                        self._fail_terminal()
                        raise MediaIoError("injected TLS peer closed during exact write")
                    offset += count
                    budget.progress_bytes += count
                    self._check_after_socket_call(budget)
                with self._state_lock:
                    self._write_operations += 1
                    self._written_bytes += len(owned)
            finally:
                _zero(owned)

    def request_cancel(self) -> None:
        """Request out-of-band cancellation without emitting media/control bytes."""

        self._request_cancel_once()

    def close(self) -> None:
        """Cancel, quiesce both directions, close the injected socket, and clear."""

        with self._close_lock:
            with self._state_lock:
                self._closed = True
            self._request_cancel_once()
            with self._read_lock, self._write_lock:
                with self._state_lock:
                    tls_socket = self._socket
                    self._socket = None
                    self._config = None
                    self._connection_id = None
                    self._sensitive_references_cleared = True
                if tls_socket is not None:
                    try:
                        tls_socket.close()
                    except Exception:
                        with self._state_lock:
                            self._close_errors += 1

    def audit(self) -> dict[str, Any]:
        """Return only bounded counters and trust-boundary facts."""

        with self._state_lock:
            return {
                "adapter_version": TLS_STREAM_ADAPTER_VERSION,
                "state": (
                    "terminal"
                    if self._terminal
                    else "closed"
                    if self._closed
                    else "cancelled"
                    if self._cancel_requested
                    else "ready"
                ),
                "default_enabled": False,
                "attestation_accepted": self._attestation_accepted,
                "read_operations": self._read_operations,
                "write_operations": self._write_operations,
                "read_bytes": self._read_bytes,
                "written_bytes": self._written_bytes,
                "zero_progress_timeouts": self._zero_progress_timeouts,
                "terminal_errors": self._terminal_errors,
                "cancel_requested": self._cancel_requested,
                "cancel_errors": self._cancel_errors,
                "close_errors": self._close_errors,
                "owned_buffer_zeroization_failures": (
                    self._owned_buffer_zeroization_failures
                ),
                "sensitive_references_cleared": self._sensitive_references_cleared,
                "socket_reference_cleared": self._socket is None,
                "connection_identity_exposed_in_audit": False,
                "peer_or_routing_identity_exposed_in_audit": False,
                "certificate_material_received_or_retained": False,
                "session_config_reference_cleared": self._config is None,
                "socket_connected_by_adapter": False,
                "tls_handshake_performed_by_adapter": False,
                "certificate_verified_by_adapter": False,
                "attestation_verification_source": "caller_injected_unverified",
                "media_logged": False,
                "media_persisted": False,
                "control_plane": "separate_unimplemented_no_in_band_control",
            }


__all__ = [
    "ConnectedTlsOrderedByteStream",
    "ConnectedTlsStreamConfig",
    "DEFAULT_ALPN",
    "InjectedConnectedTlsSocket",
    "InjectedTlsConnectionAttestation",
    "InjectedTlsSocketTimeout",
    "MAX_TRANSFER_BYTES",
    "MonotonicClock",
    "SystemMonotonicClock",
    "TLS_STREAM_ADAPTER_VERSION",
    "TlsStreamAdmissionError",
]

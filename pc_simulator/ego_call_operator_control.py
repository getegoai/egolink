"""CALL-020M default-off host control entry and CALL-020N TLS connector.

The repository does not currently implement a host-to-wearable transport for
the retained CALL-020G C API. This module therefore defines, but does not
implement, a connector that may be physically out-of-band or may use a
strictly non-interleaved CONTROL -> MEDIA -> RESULT handle handoff. A missing
connector is a fail-closed preflight blocker; control bytes are never placed
in an active CALL-020 media phase.

Construction, :meth:`HostControlSession.plan`, and the CLI are inert.  An
executable session requires all of the following through the Python API:

* one exact serial port (never discovery or guessing);
* a fresh process-local run identity and a consumed one-shot operator token;
* an externally attested connector for the exact CALL-020G lifecycle;
* an externally attested TLS connector which returns an already-connected
  socket plus the CALL-020J attestation/authentication inputs; and
* a caller-supplied exact serial factory for CALL-020K.

Only metadata is returned.  Raw audio is never accepted by this control API,
logged, or persisted. CALL-020N adds a default-off standard-library host TLS
connector that can be injected into M, but it still requires an independent
application authenticator to return the exact session-bound decision. Its
construction and CLI path are inert; this offline slice never invokes its real
socket defaults.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import re
import secrets
import select
import socket as socket_module
import ssl as ssl_module
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, Sequence

from pc_simulator.ego_call_authenticated_relay import (
    DEFAULT_AUTH_WINDOW_NS,
    ExternalAuthenticationDecision,
)
from pc_simulator.ego_call_concurrent_bridge import ConcurrentBridgeConfig
from pc_simulator.ego_call_media_io import EndpointIdentity, MediaIoError
from pc_simulator.ego_call_os_serial_wrapper import (
    ExplicitOsSerialConfig,
    ExplicitSerialFactory,
    OsSerialConnectionRegistry,
)
from pc_simulator.ego_call_pc_endpoint_composition import (
    PcEndpointComposition,
    PcEndpointCompositionConfig,
)
from pc_simulator.ego_call_serial_adapter import HostSerialAdapterConfig
from pc_simulator.ego_call_tls_stream_adapter import (
    DEFAULT_ALPN,
    ConnectedTlsStreamConfig,
    InjectedConnectedTlsSocket,
    InjectedTlsConnectionAttestation,
)


HOST_CONTROL_VERSION = "egolink.ego_call_operator_control.v0.1"
HOST_TLS_CONNECTOR_VERSION = "egolink.ego_call_host_tls_connector.v0.1"
WEARABLE_RUNNER_VERSION = "call020-operator-runner-v1"
WEARABLE_RUNNER_API_VERSION = 1
AUTHORIZATION_ACTION = "call020_operator_run_once"
CONTROL_PHASES = ("prepare", "preflight", "open", "start", "stop", "close")
WORKER_NAMES = ("audio_capture", "usb_uplink", "usb_downlink", "audio_output")
CONTROL_CLEANUP_ATTEMPTS = 2
HOST_TLS_CLEANUP_ATTEMPTS = 2
MAX_CA_PEM_BYTES = 262_144
# Windows SDK ws2ipdef.h: IP_UNICAST_IF = 31. Some Python builds omit it.
# https://learn.microsoft.com/en-us/windows/win32/winsock/ipproto-ip-socket-options
# Set a four-byte network-order index; getsockopt returns a host-order DWORD.
_WINDOWS_IP_UNICAST_IF = 31
_IDENTIFIER = re.compile(r"^[A-Za-z0-9._:-]+$")
_DNS_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


class HostControlError(ValueError):
    """Base error for a rejected CALL-020M lifecycle operation."""


class HostControlStateError(HostControlError):
    """A lifecycle operation was attempted from the wrong phase."""


class HostControlBlocked(HostControlError):
    """A fixed, redacted fail-closed result from an executable phase."""

    def __init__(self, reason_code: str, *, stage: str, cleanup_errors: int = 0):
        super().__init__("CALL-020M host control phase blocked")
        self.reason_code = reason_code
        self.metadata = {
            "control_version": HOST_CONTROL_VERSION,
            "result": "BLOCKED",
            "stage": stage,
            "reason_code": reason_code,
            "cleanup_errors": cleanup_errors,
            "routing_port_or_token_exposed": False,
            "raw_audio_logged_or_persisted": False,
            "wearable_control_proven": False,
            "p0_call": "NOT_RUN",
        }


class MonotonicClock(Protocol):
    def monotonic_ns(self) -> int: ...


class SystemMonotonicClock:
    def monotonic_ns(self) -> int:
        return time.monotonic_ns()


class AuthorizationVerifier(Protocol):
    """External verifier; the token view is valid only during this callback."""

    def authorize_once(
        self,
        *,
        run_id: str,
        action: str,
        token: memoryview,
        timeout_ms: int,
    ) -> bool: ...


def _identifier(value: object, *, label: str, maximum: int = 64) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or len(value.encode("ascii", errors="ignore")) != len(value)
        or _IDENTIFIER.fullmatch(value) is None
    ):
        raise HostControlError(
            f"{label} must be a 1-{maximum} character ASCII identifier"
        )
    return value


def _bounded_int(
    value: object, *, label: str, minimum: int, maximum: int
) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise HostControlError(
            f"{label} must be an integer in [{minimum}, {maximum}]"
        )
    return value


def _zero(buffer: bytearray) -> None:
    buffer[:] = b"\x00" * len(buffer)


def _clock_now(clock: MonotonicClock) -> int:
    value = clock.monotonic_ns()
    if type(value) is not int or value < 0:
        raise HostControlError("monotonic clock returned an invalid value")
    return value


class OneShotOperatorAuthorization:
    """Own and erase one explicit operator-intent token after one verification.

    This is an authorization-intent seam, not an authentication scheme.  Token
    meaning and verification remain with the injected verifier. Ownership of
    the mutable token transfers at construction. ``consume`` always clears it;
    callers that abandon the authorization before consume must call
    :meth:`zeroize`. Host ``prepare`` does this automatically when execution is
    disabled or plan-only.
    """

    def __init__(
        self,
        *,
        run_id: str,
        token: bytearray,
        operator_authorized: bool,
        expires_at_monotonic_ns: int,
        action: str = AUTHORIZATION_ACTION,
    ) -> None:
        self._run_id = _identifier(run_id, label="authorization run_id")
        if not isinstance(token, bytearray) or not 16 <= len(token) <= 256:
            raise HostControlError(
                "authorization token must be a mutable 16-256 byte buffer"
            )
        if type(operator_authorized) is not bool:
            raise HostControlError("operator_authorized must be an explicit boolean")
        if action != AUTHORIZATION_ACTION:
            raise HostControlError("authorization action is not CALL-020M")
        self._token: bytearray | None = token
        self._operator_authorized = operator_authorized
        self._expires_at = _bounded_int(
            expires_at_monotonic_ns,
            label="authorization expiry",
            minimum=1,
            maximum=2**63 - 1,
        )
        self._action = action
        self._consumed = False
        self._accepted = False
        self._token_cleared = False
        self._lock = threading.Lock()

    def consume(
        self,
        *,
        expected_run_id: str,
        verifier: AuthorizationVerifier,
        clock: MonotonicClock,
        timeout_ms: int,
    ) -> None:
        with self._lock:
            if self._consumed:
                raise HostControlBlocked(
                    "authorization_already_consumed", stage="prepare"
                )
            self._consumed = True
            token = self._token
            self._token = None
            start_ns = _clock_now(clock)
            try:
                if (
                    token is None
                    or self._run_id != expected_run_id
                    or self._action != AUTHORIZATION_ACTION
                    or self._operator_authorized is not True
                    or start_ns >= self._expires_at
                ):
                    raise HostControlBlocked(
                        "authorization_intent_or_freshness_rejected",
                        stage="prepare",
                    )
                callback = getattr(verifier, "authorize_once", None)
                if not callable(callback):
                    raise HostControlBlocked(
                        "authorization_verifier_missing", stage="prepare"
                    )
                token_view = memoryview(token)
                try:
                    accepted = callback(
                        run_id=expected_run_id,
                        action=AUTHORIZATION_ACTION,
                        token=token_view,
                        timeout_ms=timeout_ms,
                    )
                except HostControlBlocked:
                    raise
                except Exception:
                    raise HostControlBlocked(
                        "authorization_verifier_failed", stage="prepare"
                    ) from None
                finally:
                    token_view.release()
                end_ns = _clock_now(clock)
                if end_ns < start_ns:
                    raise HostControlBlocked(
                        "authorization_clock_regressed", stage="prepare"
                    )
                if end_ns - start_ns > timeout_ms * 1_000_000:
                    raise HostControlBlocked(
                        "authorization_verifier_exceeded_bound", stage="prepare"
                    )
                if end_ns >= self._expires_at:
                    raise HostControlBlocked(
                        "authorization_expired_during_verification", stage="prepare"
                    )
                if accepted is not True:
                    raise HostControlBlocked(
                        "authorization_verifier_rejected", stage="prepare"
                    )
                self._accepted = True
            finally:
                if token is not None:
                    _zero(token)
                    self._token_cleared = True

    def zeroize(self) -> None:
        """Irreversibly dispose an authorization that will not be consumed."""

        with self._lock:
            token = self._token
            self._token = None
            self._consumed = True
            if token is not None:
                _zero(token)
            self._token_cleared = True

    def audit(self) -> dict[str, Any]:
        with self._lock:
            return {
                "consumed": self._consumed,
                "accepted": self._accepted,
                "token_cleared": self._token_cleared,
                "token_or_run_identity_exposed": False,
            }


class RunIdentityRegistry:
    """Bounded process-local tombstones prevent accidental run-ID reuse."""

    def __init__(self, *, capacity: int = 256) -> None:
        self.capacity = _bounded_int(
            capacity, label="run registry capacity", minimum=1, maximum=4096
        )
        self._lock = threading.Lock()
        self._run_ids: set[str] = set()

    def reserve(self, run_id: str) -> None:
        run_id = _identifier(run_id, label="run_id")
        with self._lock:
            if run_id in self._run_ids:
                raise HostControlBlocked("run_identity_reused", stage="prepare")
            if len(self._run_ids) >= self.capacity:
                raise HostControlBlocked("run_identity_registry_full", stage="prepare")
            self._run_ids.add(run_id)

    def audit(self) -> dict[str, Any]:
        with self._lock:
            return {
                "capacity": self.capacity,
                "retained_run_identity_count": len(self._run_ids),
                "raw_run_id_retained_for_nonreuse": True,
                "run_id_exposed": False,
                "cross_process_freshness_proven": False,
            }


@dataclass(frozen=True)
class HostControlConfig:
    run_id: str
    exact_port: str
    enabled: bool = False
    plan_only: bool = True
    frame_count: int = 500
    max_runtime_ms: int = 15_000
    frame_deadline_ms: int = 500
    serial_baudrate: int = 115_200
    transport_call_timeout_ms: int = 20
    transport_operation_timeout_ms: int = 1_000
    control_timeout_ms: int = 1_000
    stop_join_timeout_ms: int = 3_000

    def validate(self) -> None:
        _identifier(self.run_id, label="run_id")
        if type(self.enabled) is not bool or type(self.plan_only) is not bool:
            raise HostControlError("enabled and plan_only must be explicit booleans")
        _bounded_int(self.frame_count, label="frame_count", minimum=2, maximum=30_000)
        _bounded_int(
            self.max_runtime_ms,
            label="max_runtime_ms",
            minimum=50,
            maximum=600_000,
        )
        _bounded_int(
            self.frame_deadline_ms,
            label="frame_deadline_ms",
            minimum=1,
            maximum=5_000,
        )
        _bounded_int(
            self.serial_baudrate,
            label="serial_baudrate",
            minimum=1_200,
            maximum=4_000_000,
        )
        _bounded_int(
            self.transport_call_timeout_ms,
            label="transport_call_timeout_ms",
            minimum=1,
            maximum=1_000,
        )
        _bounded_int(
            self.transport_operation_timeout_ms,
            label="transport_operation_timeout_ms",
            minimum=self.transport_call_timeout_ms,
            maximum=30_000,
        )
        _bounded_int(
            self.control_timeout_ms,
            label="control_timeout_ms",
            minimum=10,
            maximum=10_000,
        )
        _bounded_int(
            self.stop_join_timeout_ms,
            label="stop_join_timeout_ms",
            minimum=10,
            maximum=10_000,
        )
        if self.frame_deadline_ms >= self.max_runtime_ms:
            raise HostControlError("frame deadline must be below total runtime")
        minimum_schedule_ms = (self.frame_count - 1) * 20
        if self.max_runtime_ms <= minimum_schedule_ms:
            raise HostControlError("runtime must exceed the exact 20 ms frame schedule")
        # Reuse K's exact-port validation without opening or retaining a driver.
        ExplicitOsSerialConfig(
            port_name=self.exact_port,
            connection_id=f"serial-{self.run_id}",
            enabled=False,
            baudrate=self.serial_baudrate,
            read_timeout_ms=self.transport_call_timeout_ms,
            write_timeout_ms=self.transport_call_timeout_ms,
        ).validate()

    def validate_for_execution(self) -> None:
        self.validate()
        if self.enabled is not True or self.plan_only is not False:
            raise HostControlBlocked("execution_not_explicitly_enabled", stage="prepare")


@dataclass(frozen=True)
class WearableControlAttestation:
    runner_version: str
    runner_api_version: int
    externally_attested: bool
    exact_prepare_start_cancel_join_close: bool
    out_of_band_from_media: bool
    finite_timeout_contract: bool
    runtime_telemetry_supported: bool
    max_operation_timeout_ms: int
    logically_separate_and_not_interleaved_with_media: bool = False

    def validate(self, *, required_timeout_ms: int) -> None:
        if self.runner_version != WEARABLE_RUNNER_VERSION:
            raise HostControlError("wearable runner version is not CALL-020G")
        if self.runner_api_version != WEARABLE_RUNNER_API_VERSION:
            raise HostControlError("wearable runner API version is not supported")
        for name in (
            "externally_attested",
            "exact_prepare_start_cancel_join_close",
            "finite_timeout_contract",
            "runtime_telemetry_supported",
        ):
            if getattr(self, name) is not True:
                raise HostControlError(f"wearable control attestation lacks {name}")
        logical_separation = self.logically_separate_and_not_interleaved_with_media
        if (
            type(self.out_of_band_from_media) is not bool
            or type(logical_separation) is not bool
            or not (self.out_of_band_from_media or logical_separation)
        ):
            raise HostControlError(
                "wearable control must be out-of-band or logically phase-separated"
            )
        bound = _bounded_int(
            self.max_operation_timeout_ms,
            label="wearable maximum operation timeout",
            minimum=1,
            maximum=10_000,
        )
        if bound > required_timeout_ms:
            raise HostControlError("wearable control bound exceeds host control bound")


@dataclass(frozen=True)
class TlsConnectorAttestation:
    externally_attested: bool
    returns_connected_socket_only: bool
    verifies_chain_and_peer_identity: bool
    exact_session_binding: bool
    finite_timeout_contract: bool
    cleans_partial_open_before_raise: bool
    no_credential_or_media_result: bool
    expected_alpn: str = DEFAULT_ALPN
    max_connect_timeout_ms: int = 5_000
    retains_partial_open_for_bounded_retry: bool = False

    def validate(self) -> None:
        for name in (
            "externally_attested",
            "returns_connected_socket_only",
            "verifies_chain_and_peer_identity",
            "exact_session_binding",
            "finite_timeout_contract",
            "no_credential_or_media_result",
        ):
            if getattr(self, name) is not True:
                raise HostControlError(f"TLS connector attestation lacks {name}")
        if (
            type(self.cleans_partial_open_before_raise) is not bool
            or type(self.retains_partial_open_for_bounded_retry) is not bool
            or not (
                self.cleans_partial_open_before_raise
                or self.retains_partial_open_for_bounded_retry
            )
        ):
            raise HostControlError(
                "TLS connector must clean before raise or retain for bounded retry"
            )
        if self.expected_alpn != DEFAULT_ALPN:
            raise HostControlError("TLS connector ALPN does not match CALL-020J")
        _bounded_int(
            self.max_connect_timeout_ms,
            label="TLS overall open timeout",
            minimum=10,
            maximum=30_000,
        )


@dataclass(frozen=True)
class RuntimeTelemetrySnapshot:
    phase: str
    captured_at_monotonic_ns: int
    free_internal_heap_bytes: int
    minimum_free_internal_heap_bytes: int
    worker_stack_high_watermark_bytes: tuple[tuple[str, int], ...] = ()
    externally_attested_runtime_measurement: bool = False

    def validate(self, *, expected_phase: str) -> None:
        if self.phase != expected_phase or expected_phase not in {
            "pre_start",
            "post_stop",
        }:
            raise HostControlError("runtime telemetry phase mismatch")
        _bounded_int(
            self.captured_at_monotonic_ns,
            label="telemetry monotonic timestamp",
            minimum=0,
            maximum=2**63 - 1,
        )
        free_heap = _bounded_int(
            self.free_internal_heap_bytes,
            label="free internal heap",
            minimum=1,
            maximum=2**31 - 1,
        )
        minimum_heap = _bounded_int(
            self.minimum_free_internal_heap_bytes,
            label="minimum free internal heap",
            minimum=1,
            maximum=2**31 - 1,
        )
        if minimum_heap > free_heap:
            raise HostControlError("minimum free heap cannot exceed current free heap")
        if type(self.externally_attested_runtime_measurement) is not bool:
            raise HostControlError("telemetry measurement flag must be boolean")
        names: list[str] = []
        for name, value in self.worker_stack_high_watermark_bytes:
            names.append(name)
            _bounded_int(
                value,
                label="worker stack high-watermark",
                minimum=1,
                maximum=2**31 - 1,
            )
        if expected_phase == "pre_start" and names:
            raise HostControlError("pre-start telemetry cannot claim worker watermarks")
        if expected_phase == "post_stop" and tuple(names) != WORKER_NAMES:
            raise HostControlError("post-stop telemetry must cover four exact workers")

    def summary(self) -> dict[str, Any]:
        values = dict(self.worker_stack_high_watermark_bytes)
        return {
            "phase": self.phase,
            "free_internal_heap_bytes": self.free_internal_heap_bytes,
            "minimum_free_internal_heap_bytes": self.minimum_free_internal_heap_bytes,
            "worker_stack_watermark_count": len(values),
            "minimum_worker_stack_high_watermark_bytes": (
                min(values.values()) if values else None
            ),
            "externally_attested_runtime_measurement": (
                self.externally_attested_runtime_measurement
            ),
            "snapshot_source": "caller_injected_not_measured_by_call020m",
        }


@dataclass(frozen=True)
class ControlCommand:
    run_id: str
    operation_id: str
    action: str
    timeout_ms: int

    def validate(self) -> None:
        _identifier(self.run_id, label="control run_id")
        _identifier(self.operation_id, label="control operation_id", maximum=128)
        if self.action not in {"prepare", "start", "cancel", "join", "close", "telemetry"}:
            raise HostControlError("unknown wearable control action")
        _bounded_int(
            self.timeout_ms,
            label="control timeout",
            minimum=1,
            maximum=10_000,
        )


@dataclass(frozen=True)
class WearablePreparedSession:
    run_id: str
    operation_id: str
    runner_version: str
    runner_api_version: int
    state: str
    session_id: str
    device_id: str
    guardian_id: str
    uplink_clock_id: str
    downlink_clock_id: str
    nonce_bits: int
    correlated_routing_ids: bool
    random_quality: str
    provenance: str
    pre_start_telemetry: RuntimeTelemetrySnapshot
    duplicate: bool = False

    def validate(self, command: ControlCommand) -> EndpointIdentity:
        if self.run_id != command.run_id or self.operation_id != command.operation_id:
            raise HostControlError("wearable prepare idempotency binding mismatch")
        if (
            self.runner_version != WEARABLE_RUNNER_VERSION
            or self.runner_api_version != WEARABLE_RUNNER_API_VERSION
            or self.state != "PREPARED"
        ):
            raise HostControlError("wearable did not attest CALL-020G PREPARED")
        if self.nonce_bits < 128 or self.correlated_routing_ids is not True:
            raise HostControlError("wearable descriptor nonce lineage is invalid")
        if self.random_quality != "unverified":
            raise HostControlError("wearable random-quality claim is unsupported")
        if self.provenance != "runtime_ephemeral_generated":
            raise HostControlError("wearable descriptor provenance is invalid")
        if type(self.duplicate) is not bool:
            raise HostControlError("wearable prepare duplicate flag must be boolean")
        identity = EndpointIdentity(
            session_id=self.session_id,
            device_id=self.device_id,
            guardian_id=self.guardian_id,
            uplink_clock_id=self.uplink_clock_id,
            downlink_clock_id=self.downlink_clock_id,
        )
        identity.validate()
        self.pre_start_telemetry.validate(expected_phase="pre_start")
        if not self.pre_start_telemetry.externally_attested_runtime_measurement:
            raise HostControlError("pre-start runtime telemetry is not attested")
        return identity


@dataclass(frozen=True)
class WearableControlAck:
    run_id: str
    operation_id: str
    action: str
    accepted: bool
    state: str
    duplicate: bool = False

    def validate(self, command: ControlCommand, *, states: set[str]) -> None:
        if (
            self.run_id != command.run_id
            or self.operation_id != command.operation_id
            or self.action != command.action
            or self.accepted is not True
            or type(self.duplicate) is not bool
            or self.state not in states
        ):
            raise HostControlError("wearable control acknowledgement mismatch")


class WearableControlConnector(Protocol):
    """Phase-safe bridge to CALL-020G.

    CALL-020P supplies an offline host same-handle implementation. The matching
    device wire counterpart and runtime evidence are not bundled or inferred.
    """

    def prepare(self, command: ControlCommand) -> WearablePreparedSession: ...

    def start(self, command: ControlCommand) -> WearableControlAck: ...

    def cancel(self, command: ControlCommand) -> WearableControlAck: ...

    def join(self, command: ControlCommand) -> WearableControlAck: ...

    def close(self, command: ControlCommand) -> WearableControlAck: ...

    def telemetry(self, command: ControlCommand) -> RuntimeTelemetrySnapshot: ...


@dataclass(frozen=True)
class TlsOpenRequest:
    run_id: str
    identity: EndpointIdentity
    expected_alpn: str
    connect_timeout_ms: int
    role: str = "device"

    def validate(self) -> None:
        _identifier(self.run_id, label="TLS request run_id")
        self.identity.validate()
        if self.role not in {"device", "guardian"}:
            raise HostControlError("TLS request role must be device or guardian")
        if self.expected_alpn != DEFAULT_ALPN:
            raise HostControlError("TLS request ALPN mismatch")
        _bounded_int(
            self.connect_timeout_ms,
            # Legacy field name retained for M compatibility. This is the
            # whole connector-open budget, not a fresh budget for each stage.
            label="TLS request overall-open timeout",
            minimum=10,
            maximum=30_000,
        )


@dataclass(frozen=True)
class VerifiedTlsOpenResult:
    tls_socket: InjectedConnectedTlsSocket
    tls_attestation: InjectedTlsConnectionAttestation
    authentication_decision: ExternalAuthenticationDecision

    def validate(self, request: TlsOpenRequest) -> None:
        if not isinstance(self.tls_attestation, InjectedTlsConnectionAttestation):
            raise HostControlError("external TLS connector omitted immutable attestation")
        if not isinstance(self.authentication_decision, ExternalAuthenticationDecision):
            raise HostControlError("external TLS connector omitted auth decision")
        self.tls_attestation.validate()
        binding = self.authentication_decision.binding
        expected = (
            request.identity.session_id,
            request.role,
            request.identity.device_id if request.role == "device" else request.identity.guardian_id,
            request.identity.guardian_id if request.role == "device" else request.identity.device_id,
            request.identity.uplink_clock_id if request.role == "device" else request.identity.downlink_clock_id,
        )
        actual = (
            binding.session_id,
            binding.role,
            binding.endpoint_id,
            binding.peer_endpoint_id,
            binding.source_clock_id,
        )
        if actual != expected:
            raise HostControlError("TLS connector result identity binding mismatch")
        if self.tls_attestation.connection_id != binding.connection_id:
            raise HostControlError("TLS connector connection binding mismatch")


class ExternallyVerifiedTlsConnector(Protocol):
    """Injected connector which performs TLS/PKI/auth work outside M/J.

    Ownership transfers only when ``open_verified`` returns a valid bundle.
    If it raises after allocating any socket or authentication resource, the
    connector must attempt cancel/close without losing ownership. CALL-020N
    retains an unconfirmed target behind ``retry_failed_open_cleanup`` and M
    refuses ``CLOSED`` until that retry confirms cleanup. Its declared overall
    timeout is caller-enforced plus checked after return; Python cannot
    hard-preempt a connector which violates that callback contract.
    """

    def open_verified(self, request: TlsOpenRequest) -> VerifiedTlsOpenResult: ...


def _exact_ipv4(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise HostControlError(f"{label} must be one exact numeric IPv4 address")
    try:
        parsed = ipaddress.ip_address(value)
    except ValueError:
        raise HostControlError(
            f"{label} must be one exact numeric IPv4 address"
        ) from None
    if (
        not isinstance(parsed, ipaddress.IPv4Address)
        or str(parsed) != value
        or parsed.is_unspecified
        or parsed.is_multicast
        or value == "255.255.255.255"
    ):
        raise HostControlError(f"{label} is not an admissible exact IPv4 address")
    return value


def _exact_tls_hostname(value: object) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 253
        or value.strip() != value
        or value != value.lower()
        or value.endswith(".")
        or "*" in value
        or len(value.encode("ascii", errors="ignore")) != len(value)
    ):
        raise HostControlError("TLS hostname/SNI must be exact canonical ASCII")
    try:
        ipaddress.ip_address(value)
    except ValueError:
        pass
    else:
        raise HostControlError("TLS hostname/SNI cannot be a numeric address")
    labels = value.split(".")
    if len(labels) < 2 or any(_DNS_LABEL.fullmatch(label) is None for label in labels):
        raise HostControlError("TLS hostname/SNI is not a canonical DNS name")
    return value


def _validate_windows_ipv4_interface_index(interface_index: int | None) -> None:
    if interface_index is None:
        return
    _bounded_int(interface_index, label="Windows IPv4 interface index",
                 minimum=1, maximum=0xFFFFFF)
    if sys.platform != "win32":
        raise HostControlError("Windows IPv4 interface pin requires Windows")


def _pin_windows_ipv4_interface(raw_socket: Any, interface_index: int | None) -> bool:
    """Apply the optional exact Windows egress constraint before bind/connect."""
    _validate_windows_ipv4_interface_index(interface_index)
    if interface_index is None:
        return False
    raw_socket.setsockopt(socket_module.IPPROTO_IP, _WINDOWS_IP_UNICAST_IF,
                          interface_index.to_bytes(4, "big"))
    actual = raw_socket.getsockopt(socket_module.IPPROTO_IP, _WINDOWS_IP_UNICAST_IF)
    if type(actual) is not int or actual != interface_index:
        raise HostControlError("Windows IPv4 interface readback mismatch")
    return True


@dataclass(frozen=True)
class HostTlsConnectorConfig:
    """Exact, caller-owned TLS route and trust input; disabled by default."""

    peer_ipv4: str
    peer_port: int
    source_ipv4: str
    tls_hostname: str
    ca_pem: str | None = None
    ca_file: str | None = None
    enabled: bool = False
    expected_alpn: str = DEFAULT_ALPN
    overall_timeout_ms: int = 5_000
    tcp_connect_timeout_ms: int = 2_000
    handshake_timeout_ms: int = 2_000
    read_timeout_ms: int = 20
    write_timeout_ms: int = 20
    authentication_timeout_ms: int = 1_000
    max_auth_window_ns: int = DEFAULT_AUTH_WINDOW_NS
    windows_ipv4_interface_index: int | None = None

    def validate(self) -> None:
        if type(self.enabled) is not bool:
            raise HostControlError("host TLS enabled must be an explicit boolean")
        _exact_ipv4(self.peer_ipv4, label="TLS peer")
        _exact_ipv4(self.source_ipv4, label="TLS source bind")
        _validate_windows_ipv4_interface_index(self.windows_ipv4_interface_index)
        _exact_tls_hostname(self.tls_hostname)
        _bounded_int(self.peer_port, label="TLS peer port", minimum=1, maximum=65535)
        if self.expected_alpn != DEFAULT_ALPN:
            raise HostControlError("host TLS ALPN must match CALL-020J")
        for label, value in (
            ("TLS overall open timeout", self.overall_timeout_ms),
            ("TLS TCP connect timeout", self.tcp_connect_timeout_ms),
            ("TLS handshake timeout", self.handshake_timeout_ms),
            ("TLS read timeout", self.read_timeout_ms),
            ("TLS write timeout", self.write_timeout_ms),
            ("TLS authentication timeout", self.authentication_timeout_ms),
        ):
            _bounded_int(value, label=label, minimum=1, maximum=30_000)
        if (
            self.tcp_connect_timeout_ms
            + self.handshake_timeout_ms
            + self.authentication_timeout_ms
            > self.overall_timeout_ms
        ):
            raise HostControlError(
                "TLS stage budgets must fit the overall open deadline"
            )
        _bounded_int(
            self.max_auth_window_ns,
            label="TLS authentication window",
            minimum=1_000_000,
            maximum=300_000_000_000,
        )
        if (self.ca_pem is None) == (self.ca_file is None):
            raise HostControlError("exactly one caller CA PEM or CA path is required")
        if self.ca_pem is not None:
            try:
                encoded = self.ca_pem.encode("ascii")
            except (AttributeError, UnicodeEncodeError):
                raise HostControlError("caller CA PEM must be bounded ASCII") from None
            if (
                not 1 <= len(encoded) <= MAX_CA_PEM_BYTES
                or "-----BEGIN CERTIFICATE-----" not in self.ca_pem
                or "-----END CERTIFICATE-----" not in self.ca_pem
            ):
                raise HostControlError("caller CA PEM is missing or outside its bound")
        if self.ca_file is not None:
            if (
                not isinstance(self.ca_file, str)
                or not self.ca_file
                or self.ca_file.strip() != self.ca_file
                or "\x00" in self.ca_file
                or "*" in self.ca_file
                or "?" in self.ca_file
                or not Path(self.ca_file).is_absolute()
            ):
                raise HostControlError("caller CA path must be exact and absolute")

    def validate_for_open(self) -> None:
        self.validate()
        if self.enabled is not True:
            raise HostTlsConnectorBlocked(
                "host_tls_connector_disabled", network_attempted=False
            )


@dataclass(frozen=True)
class HostTlsPeerEvidence:
    """Private callback input; never included in connector audit or errors."""

    run_id: str
    identity: EndpointIdentity
    connection_id: str
    peer_ipv4: str
    tls_hostname: str
    selected_alpn: str
    tls_version: str
    peer_certificate_sha256: str
    captured_at_monotonic_ns: int
    role: str = "device"

    def validate(self) -> None:
        _identifier(self.run_id, label="TLS evidence run_id")
        self.identity.validate()
        if self.role not in {"device", "guardian"}:
            raise HostControlError("TLS evidence role must be device or guardian")
        _identifier(self.connection_id, label="TLS evidence connection_id")
        _exact_ipv4(self.peer_ipv4, label="TLS evidence peer")
        _exact_tls_hostname(self.tls_hostname)
        if self.selected_alpn != DEFAULT_ALPN:
            raise HostControlError("TLS evidence ALPN mismatch")
        if self.tls_version not in {"TLSv1.2", "TLSv1.3"}:
            raise HostControlError("TLS evidence protocol is below TLSv1.2")
        if not re.fullmatch(r"[0-9a-f]{64}", self.peer_certificate_sha256):
            raise HostControlError("TLS evidence certificate digest is invalid")
        _bounded_int(
            self.captured_at_monotonic_ns,
            label="TLS evidence timestamp",
            minimum=0,
            maximum=2**63 - 1,
        )


class ConnectedTlsSessionAuthenticator(Protocol):
    """External application authenticator; N never invents its decision."""

    def authorize_connected_session(
        self, *, evidence: HostTlsPeerEvidence, timeout_ms: int
    ) -> ExternalAuthenticationDecision: ...


class HostTlsConnectorBlocked(HostControlError):
    """Redacted CALL-020N failure after bounded partial-resource cleanup."""

    def __init__(
        self,
        reason_code: str,
        *,
        cleanup_confirmed: bool = True,
        cleanup_errors: int = 0,
        network_attempted: bool = False,
    ) -> None:
        super().__init__("CALL-020N host TLS connector blocked")
        self.reason_code = reason_code
        self.metadata = {
            "connector_version": HOST_TLS_CONNECTOR_VERSION,
            "result": "BLOCKED",
            "stage": "tls_open",
            "reason_code": reason_code,
            "partial_cleanup_confirmed": cleanup_confirmed,
            "cleanup_errors": cleanup_errors,
            "network_attempted": network_attempted,
            "numeric_peer_used_without_dns": True,
            "identity_hostname_ca_or_credential_exposed": False,
            "authentication_decision_fabricated": False,
            "raw_audio_logged_or_persisted": False,
            "p0_call": "NOT_RUN",
        }


class _OwnedHostTlsSocket:
    """Bounded native TLS facade with serialized OpenSSL access.

    Native SSL calls run nonblocking under one lock; readiness waits happen
    outside it so the other media direction can progress. Concurrent blocking
    calls on one SSLSocket can corrupt OpenSSL record state. Test doubles keep
    their existing finite-timeout contract.
    """

    def __init__(self, tls_socket: object, *, connection_id: str) -> None:
        self.connection_id = _identifier(
            connection_id, label="host TLS connection_id"
        )
        self._socket: object | None = tls_socket
        self._lifecycle_lock = threading.Lock()
        self._ssl_lock = threading.Lock()
        self._native = isinstance(tls_socket, ssl_module.SSLSocket)
        self._native_timeout = None
        if self._native:
            self._native_timeout = tls_socket.gettimeout()
            if self._native_timeout is None or self._native_timeout <= 0:
                raise HostControlError("native TLS facade requires a finite timeout")
            tls_socket.setblocking(False)

    def _active(self) -> object:
        with self._lifecycle_lock:
            current = self._socket
        if current is None:
            raise OSError("TLS socket is closed")
        return current

    def recv_into(self, target: memoryview, size: int) -> int:
        return self._io("recv_into", target, size)

    def send(self, source: memoryview) -> int:
        return self._io("send", source)

    def _io(self, operation: str, *args: object) -> int:
        if not self._native:
            return getattr(self._active(), operation)(*args)
        deadline = time.monotonic() + self._native_timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not self._ssl_lock.acquire(timeout=remaining):
                raise TimeoutError("native TLS I/O deadline")
            try:
                current = self._active()
                try:
                    return getattr(current, operation)(*args)
                except ssl_module.SSLWantReadError:
                    want_read = True
                except ssl_module.SSLWantWriteError:
                    want_read = False
            finally:
                self._ssl_lock.release()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("native TLS readiness deadline")
            ready = select.select([current] if want_read else [],
                                  [] if want_read else [current], [], remaining)
            if not ready[0] and not ready[1]:
                raise TimeoutError("native TLS readiness deadline")

    def gettimeout(self) -> float | None:
        if self._native:
            self._active()
            return self._native_timeout
        return self._active().gettimeout()

    def selected_alpn_protocol(self) -> str | None:
        return self._active().selected_alpn_protocol()

    def version(self) -> str | None:
        return self._active().version()

    def cancel_pending_io(self) -> None:
        current = self._active()
        try:
            current.shutdown(socket_module.SHUT_RDWR)
        except OSError:
            # Already-disconnected is a quiescent cancellation outcome.
            pass

    def close(self) -> None:
        with self._lifecycle_lock:
            current = self._socket
            if current is None:
                return
            current.close()
            self._socket = None


def _cleanup_host_tls_socket(target: object | None) -> tuple[bool, int]:
    if target is None:
        return True, 0
    errors = 0
    shutdown = getattr(target, "shutdown", None)
    if callable(shutdown):
        try:
            shutdown(socket_module.SHUT_RDWR)
        except OSError:
            pass
        except Exception:
            errors += 1
    close = getattr(target, "close", None)
    if not callable(close):
        return False, errors + 1
    for _ in range(HOST_TLS_CLEANUP_ATTEMPTS):
        try:
            close()
            return True, errors
        except Exception:
            errors += 1
    return False, errors


class DefaultOffHostTlsConnector:
    """One-shot exact-route TLS client suitable for injection into CALL-020M.

    The production defaults use ``AF_INET`` directly and never invoke a name
    resolver. TLS server authentication is provided by one caller CA source,
    exact hostname/SNI, ``CERT_REQUIRED`` and a successful handshake. The
    separate application authenticator must return the exact endpoint/session/
    clock/connection-bound ``ExternalAuthenticationDecision``; N never creates
    or signs that decision.

    Factories are injectable solely for offline tests. Their use does not turn
    a fake handshake or authentication response into runtime evidence.
    """

    def __init__(
        self,
        config: HostTlsConnectorConfig,
        *,
        authenticator: ConnectedTlsSessionAuthenticator | None,
        clock: MonotonicClock | None = None,
        socket_factory: Any = socket_module.socket,
        ssl_context_factory: Any = None,
        connection_id_factory: Any = None,
    ) -> None:
        if not isinstance(config, HostTlsConnectorConfig):
            raise HostControlError("HostTlsConnectorConfig is required")
        config.validate()
        self._config = config
        self._authenticator = authenticator
        self._clock = clock or SystemMonotonicClock()
        self._socket_factory = socket_factory
        self._ssl_context_factory = ssl_context_factory or (
            lambda: ssl_module.SSLContext(ssl_module.PROTOCOL_TLS_CLIENT)
        )
        self._connection_id_factory = connection_id_factory or (
            lambda: f"call020n-{secrets.token_hex(16)}"
        )
        self._lock = threading.Lock()
        self._state = "dormant"
        self._socket_created = False
        self._source_bound = False
        self._source_binding_verified = False
        self._windows_ipv4_interface_verified = False
        self._numeric_connect_attempted = False
        self._numeric_peer_verified = False
        self._handshake_attempted = False
        self._authentication_callback_calls = 0
        self._ownership_transferred = False
        self._partial_cleanup_confirmed = True
        self._cleanup_errors = 0
        self._cleanup_target: object | None = None
        self._cleanup_lock = threading.Lock()

    def _set_failed(self) -> None:
        with self._lock:
            self._state = "failed"

    def _raise_blocked(
        self,
        reason_code: str,
        *,
        target: object | None = None,
    ) -> None:
        cleanup_confirmed, cleanup_errors = _cleanup_host_tls_socket(target)
        with self._lock:
            self._partial_cleanup_confirmed = cleanup_confirmed
            self._cleanup_errors += cleanup_errors
            self._cleanup_target = None if cleanup_confirmed else target
            self._state = "failed" if cleanup_confirmed else "cleanup_failed"
        raise HostTlsConnectorBlocked(
            reason_code,
            cleanup_confirmed=cleanup_confirmed,
            cleanup_errors=cleanup_errors,
            network_attempted=self._numeric_connect_attempted,
        ) from None

    def retry_failed_open_cleanup(self) -> bool:
        """Retry one retained partial-open target without reopening anything."""

        with self._cleanup_lock:
            with self._lock:
                target = self._cleanup_target
            if target is None:
                return True
            cleanup_confirmed, cleanup_errors = _cleanup_host_tls_socket(target)
            with self._lock:
                self._cleanup_errors += cleanup_errors
                self._partial_cleanup_confirmed = cleanup_confirmed
                if cleanup_confirmed:
                    self._cleanup_target = None
                    self._state = "failed"
                else:
                    self._state = "cleanup_failed"
            return cleanup_confirmed

    def _remaining_timeout_seconds(self, *, deadline_ns: int, cap_ms: int) -> float:
        now_ns = _clock_now(self._clock)
        remaining_ns = deadline_ns - now_ns
        if remaining_ns <= 0:
            raise HostControlError("host TLS overall deadline exhausted")
        return min(cap_ms / 1_000, remaining_ns / 1_000_000_000)

    def _remaining_timeout_ms(self, *, deadline_ns: int, cap_ms: int) -> int:
        now_ns = _clock_now(self._clock)
        remaining_ns = deadline_ns - now_ns
        remaining_ms = remaining_ns // 1_000_000
        if remaining_ms < 1:
            raise HostControlError(
                "host TLS overall deadline lacks one callback millisecond"
            )
        return min(cap_ms, int(remaining_ms))

    def _new_context(self) -> object:
        config = self._config
        try:
            context = self._ssl_context_factory()
            context.check_hostname = True
            context.verify_mode = ssl_module.CERT_REQUIRED
            context.minimum_version = ssl_module.TLSVersion.TLSv1_2
            context.maximum_version = ssl_module.TLSVersion.TLSv1_3
            if hasattr(context, "hostname_checks_common_name"):
                context.hostname_checks_common_name = False
            context.options |= ssl_module.OP_NO_COMPRESSION
            context.set_alpn_protocols([config.expected_alpn])
            if config.ca_file is not None:
                context.load_verify_locations(cafile=config.ca_file)
            else:
                context.load_verify_locations(cadata=config.ca_pem)
        except Exception:
            raise HostTlsConnectorBlocked(
                "tls_context_or_caller_ca_rejected",
                network_attempted=False,
            ) from None
        return context

    def _validate_decision(
        self,
        decision: object,
        *,
        request: TlsOpenRequest,
        connection_id: str,
    ) -> ExternalAuthenticationDecision:
        if not isinstance(decision, ExternalAuthenticationDecision):
            raise HostControlError("external authentication decision is required")
        now_ns = _clock_now(self._clock)
        decision.validate(now_ns=now_ns, max_window_ns=self._config.max_auth_window_ns)
        binding = decision.binding
        expected = (
            request.identity.session_id,
            request.role,
            request.identity.device_id if request.role == "device" else request.identity.guardian_id,
            request.identity.guardian_id if request.role == "device" else request.identity.device_id,
            request.identity.uplink_clock_id if request.role == "device" else request.identity.downlink_clock_id,
            connection_id,
        )
        actual = (
            binding.session_id,
            binding.role,
            binding.endpoint_id,
            binding.peer_endpoint_id,
            binding.source_clock_id,
            binding.connection_id,
        )
        if decision.authenticated is not True or actual != expected:
            raise HostControlError("external authentication binding mismatch")
        return decision

    def open_verified(self, request: TlsOpenRequest) -> VerifiedTlsOpenResult:
        config = self._config
        try:
            config.validate_for_open()
            if not isinstance(request, TlsOpenRequest):
                raise HostControlError("TlsOpenRequest is required")
            request.validate()
            if (
                request.expected_alpn != config.expected_alpn
                or request.connect_timeout_ms != config.overall_timeout_ms
            ):
                raise HostControlError("TLS request and exact connector route differ")
            callback = getattr(
                self._authenticator, "authorize_connected_session", None
            )
            stream_callback = getattr(self._authenticator, "authorize_tls_stream", None)
            if not callable(callback) and not callable(stream_callback):
                raise HostTlsConnectorBlocked(
                    "external_session_authenticator_missing",
                    network_attempted=False,
                )
            if any(
                not callable(value)
                for value in (
                    self._socket_factory,
                    self._ssl_context_factory,
                    self._connection_id_factory,
                )
            ):
                raise HostControlError("host TLS dependency shape is invalid")
        except HostTlsConnectorBlocked:
            self._set_failed()
            raise
        except Exception:
            self._set_failed()
            raise HostTlsConnectorBlocked(
                "host_tls_preconnect_rejected", network_attempted=False
            ) from None

        with self._lock:
            if self._state != "dormant":
                raise HostTlsConnectorBlocked(
                    "host_tls_connector_single_use", network_attempted=False
                )
            self._state = "opening"

        open_started_ns = _clock_now(self._clock)
        deadline_ns = open_started_ns + config.overall_timeout_ms * 1_000_000
        if deadline_ns > 2**63 - 1:
            self._set_failed()
            raise HostTlsConnectorBlocked(
                "host_tls_overall_deadline_invalid", network_attempted=False
            )
        try:
            context = self._new_context()
            self._remaining_timeout_seconds(
                deadline_ns=deadline_ns,
                cap_ms=config.overall_timeout_ms,
            )
        except HostTlsConnectorBlocked:
            self._set_failed()
            raise
        except Exception:
            self._set_failed()
            raise HostTlsConnectorBlocked(
                "host_tls_overall_deadline_exceeded", network_attempted=False
            ) from None
        raw_socket: object | None = None
        tls_socket: object | None = None
        owned_socket: _OwnedHostTlsSocket | None = None
        reason = "host_tls_socket_create_failed"
        try:
            raw_socket = self._socket_factory(
                socket_module.AF_INET,
                socket_module.SOCK_STREAM,
                socket_module.IPPROTO_TCP,
            )
            self._socket_created = True
            for name in (
                "settimeout",
                "bind",
                "connect",
                "getsockname",
                "getpeername",
                "shutdown",
                "close",
            ):
                if not callable(getattr(raw_socket, name, None)):
                    raise HostControlError("raw socket shape is incomplete")
            raw_socket.settimeout(
                self._remaining_timeout_seconds(
                    deadline_ns=deadline_ns,
                    cap_ms=config.tcp_connect_timeout_ms,
                )
            )
            if config.windows_ipv4_interface_index is not None:
                reason = "windows_ipv4_interface_pin_failed"
                self._windows_ipv4_interface_verified = _pin_windows_ipv4_interface(
                    raw_socket, config.windows_ipv4_interface_index
                )
            reason = "host_tls_socket_create_failed"
            raw_socket.bind((config.source_ipv4, 0))
            self._source_bound = True
            reason = "numeric_tls_connect_failed"
            self._numeric_connect_attempted = True
            raw_socket.connect((config.peer_ipv4, config.peer_port))

            reason = "connected_exact_route_mismatch"
            local_address = raw_socket.getsockname()
            peer_address = raw_socket.getpeername()
            if (
                not isinstance(local_address, tuple)
                or len(local_address) != 2
                or local_address[0] != config.source_ipv4
                or type(local_address[1]) is not int
                or not 1 <= local_address[1] <= 65_535
            ):
                raise HostControlError("connected TLS source route differs")
            self._source_binding_verified = True
            if peer_address != (config.peer_ipv4, config.peer_port):
                raise HostControlError("connected TLS peer route differs")
            self._numeric_peer_verified = True

            reason = "tls_wrap_or_handshake_failed"
            raw_socket.settimeout(
                self._remaining_timeout_seconds(
                    deadline_ns=deadline_ns,
                    cap_ms=config.handshake_timeout_ms,
                )
            )
            tls_socket = context.wrap_socket(
                raw_socket,
                server_hostname=config.tls_hostname,
                do_handshake_on_connect=False,
            )
            raw_socket = None
            for name in (
                "do_handshake",
                "settimeout",
                "gettimeout",
                "selected_alpn_protocol",
                "version",
                "getpeercert",
                "recv_into",
                "send",
                "shutdown",
                "close",
            ):
                if not callable(getattr(tls_socket, name, None)):
                    raise HostControlError("TLS socket shape is incomplete")
            tls_socket.settimeout(
                self._remaining_timeout_seconds(
                    deadline_ns=deadline_ns,
                    cap_ms=config.handshake_timeout_ms,
                )
            )
            self._handshake_attempted = True
            tls_socket.do_handshake()
            negotiated_alpn = tls_socket.selected_alpn_protocol()
            negotiated_version = tls_socket.version()
            peer_certificate = tls_socket.getpeercert(binary_form=True)
            if negotiated_alpn != config.expected_alpn:
                reason = "tls_alpn_mismatch"
                raise HostControlError("TLS ALPN mismatch")
            if negotiated_version not in {"TLSv1.2", "TLSv1.3"}:
                reason = "tls_version_below_or_outside_supported_range"
                raise HostControlError("TLS version is unsupported")
            if not isinstance(peer_certificate, bytes) or not peer_certificate:
                reason = "verified_peer_certificate_missing"
                raise HostControlError("verified peer certificate is unavailable")
            tls_socket.settimeout(
                min(config.read_timeout_ms, config.write_timeout_ms) / 1_000
            )

            reason = "connection_identity_generation_failed"
            connection_id = _identifier(
                self._connection_id_factory(),
                label="host TLS connection_id",
            )
            owned_socket = _OwnedHostTlsSocket(
                tls_socket, connection_id=connection_id
            )
            tls_socket = None
            captured_ns = _clock_now(self._clock)
            evidence = HostTlsPeerEvidence(
                run_id=request.run_id,
                identity=request.identity,
                connection_id=connection_id,
                peer_ipv4=config.peer_ipv4,
                tls_hostname=config.tls_hostname,
                selected_alpn=negotiated_alpn,
                tls_version=negotiated_version,
                peer_certificate_sha256=hashlib.sha256(peer_certificate).hexdigest(),
                captured_at_monotonic_ns=captured_ns,
                role=request.role,
            )
            evidence.validate()

            reason = "external_session_authentication_failed"
            auth_start_ns = _clock_now(self._clock)
            authentication_timeout_ms = self._remaining_timeout_ms(
                deadline_ns=deadline_ns,
                cap_ms=config.authentication_timeout_ms,
            )
            self._authentication_callback_calls += 1
            if callable(stream_callback):
                decision = stream_callback(
                    evidence=evidence,
                    tls_socket=owned_socket,
                    timeout_ms=authentication_timeout_ms,
                )
            else:
                decision = callback(
                    evidence=evidence,
                    timeout_ms=authentication_timeout_ms,
                )
            auth_end_ns = _clock_now(self._clock)
            if (
                auth_end_ns < auth_start_ns
                or auth_end_ns - auth_start_ns
                > authentication_timeout_ms * 1_000_000
            ):
                reason = "external_session_authenticator_exceeded_bound"
                raise HostControlError("external authenticator exceeded its bound")
            decision = self._validate_decision(
                decision,
                request=request,
                connection_id=connection_id,
            )
            attestation = InjectedTlsConnectionAttestation(
                handshake_complete=True,
                certificate_chain_verified=True,
                peer_identity_verified=True,
                peer_identity=(request.identity.device_id if request.role == "device"
                               else request.identity.guardian_id),
                selected_alpn=negotiated_alpn,
                tls_version=negotiated_version,
                connection_id=connection_id,
                verified_server_hostname=config.tls_hostname,
            )
            result = VerifiedTlsOpenResult(
                tls_socket=owned_socket,
                tls_attestation=attestation,
                authentication_decision=decision,
            )
            result.validate(request)
            self._remaining_timeout_seconds(
                deadline_ns=deadline_ns,
                cap_ms=config.overall_timeout_ms,
            )
            with self._lock:
                self._state = "transferred"
                self._ownership_transferred = True
            owned_socket = None
            return result
        except Exception:
            target = owned_socket or tls_socket or raw_socket
            self._raise_blocked(reason, target=target)

    def audit(self) -> dict[str, Any]:
        with self._lock:
            return {
                "connector_version": HOST_TLS_CONNECTOR_VERSION,
                "state": self._state,
                "default_enabled": False,
                "exact_numeric_peer_configured": True,
                "exact_source_ipv4_bind_configured": True,
                "windows_ipv4_interface_configured": self._config.windows_ipv4_interface_index is not None,
                "windows_ipv4_interface_verified": self._windows_ipv4_interface_verified,
                "exact_tls_hostname_and_sni_configured": True,
                "caller_ca_source_count": 1,
                "minimum_tls_version": "TLSv1.2",
                "maximum_tls_version": "TLSv1.3",
                "alpn_required": True,
                "socket_created": self._socket_created,
                "source_bound": self._source_bound,
                "connected_source_binding_verified": self._source_binding_verified,
                "numeric_connect_attempted": self._numeric_connect_attempted,
                "connected_numeric_peer_verified": self._numeric_peer_verified,
                "handshake_attempted": self._handshake_attempted,
                "authentication_callback_calls": self._authentication_callback_calls,
                "authentication_decision_fabricated": False,
                "authentication_callback_timeout_is_post_return_check_only": True,
                "one_overall_open_deadline_with_remaining_stage_budgets": True,
                "ownership_transferred": self._ownership_transferred,
                "partial_cleanup_confirmed": self._partial_cleanup_confirmed,
                "partial_cleanup_target_retained": self._cleanup_target is not None,
                "cleanup_errors": self._cleanup_errors,
                "dns_resolution_used": False,
                "route_hostname_ca_identity_or_connection_exposed": False,
                "raw_audio_logged_or_persisted": False,
                "hardware_or_network_evidence": "NOT_RUN",
                "p0_call": "NOT_RUN",
            }


class _EndpointComposition(Protocol):
    def open(self, **kwargs: Any) -> None: ...

    def start(self) -> dict[str, Any]: ...

    def request_cancel(self) -> None: ...

    def close(self) -> None: ...

    def audit(self) -> dict[str, Any]: ...


_GLOBAL_RUN_REGISTRY = RunIdentityRegistry()


def _plan(config: HostControlConfig) -> dict[str, Any]:
    config.validate()
    return {
        "control_version": HOST_CONTROL_VERSION,
        "mode": "plan_only",
        "default_enabled": False,
        "phase_order": list(CONTROL_PHASES),
        "requested": {
            "exact_port_supplied": True,
            "run_identity_supplied": True,
            "frame_count": config.frame_count,
            "maximum_runtime_ms": config.max_runtime_ms,
        },
        "required_external_inputs": [
            "fresh_one_shot_operator_authorization",
            "exact_serial_factory_no_discovery",
            "attested_phase_safe_call020g_control_connector",
            "attested_connected_tls_connector",
            "pre_start_runtime_telemetry_snapshot",
            "post_stop_runtime_telemetry_snapshot_legacy_oob_only",
        ],
        "repository_blockers": [
            "wearable_call020g_remote_control_connector_not_implemented",
            "same_handle_device_control_counterpart_and_runtime_not_verified",
            "same_handle_result_wire_and_quiescence_proof_not_implemented",
            "real_tls_connector_offline_implemented_not_runtime_verified",
            "external_tls_session_authenticator_not_implemented_or_verified",
            "external_callback_hard_preemption_not_implemented_or_verified",
            "exact_board_usb_media_and_control_coexistence_not_verified",
        ],
        "io_truth": {
            "serial_enumerated_or_opened": False,
            "tls_socket_opened": False,
            "network_contacted": False,
            "wearable_controlled": False,
            "audio_captured_or_played": False,
            "raw_audio_logged_or_persisted": False,
        },
        "launchable_from_repository_alone": False,
        "p0_call": "NOT_RUN",
    }


def _cancel_close_socket(tls_socket: object) -> int:
    errors = 0
    for name in ("cancel_pending_io", "close"):
        callback = getattr(tls_socket, name, None)
        if not callable(callback):
            errors += 1
            continue
        try:
            callback()
        except Exception:
            errors += 1
    return errors


class HostControlSession:
    """Strict, default-off prepare/preflight/open/start/stop/close owner."""

    def __init__(
        self,
        config: HostControlConfig,
        *,
        clock: MonotonicClock | None = None,
        run_registry: RunIdentityRegistry | None = None,
        serial_registry: OsSerialConnectionRegistry | None = None,
        endpoint_factory: Any = PcEndpointComposition,
    ) -> None:
        if not isinstance(config, HostControlConfig):
            raise HostControlError("HostControlConfig is required")
        config.validate()
        self._config: HostControlConfig | None = config
        self._clock = clock or SystemMonotonicClock()
        self._run_registry = run_registry or _GLOBAL_RUN_REGISTRY
        self._serial_registry = serial_registry or OsSerialConnectionRegistry()
        self._endpoint_factory = endpoint_factory
        self._state_lock = threading.Lock()
        self._lifecycle_lock = threading.Lock()
        self._state = "dormant"
        self._authorization_audit: dict[str, Any] | None = None
        self._wearable: WearableControlConnector | None = None
        self._tls_connector: ExternallyVerifiedTlsConnector | None = None
        self._serial_factory: ExplicitSerialFactory | None = None
        self._wearable_attestation: WearableControlAttestation | None = None
        self._tls_connector_attestation: TlsConnectorAttestation | None = None
        self._endpoint: _EndpointComposition | None = None
        self._endpoint_close_confirmed = True
        self._endpoint_close_callback_returned = True
        self._media_thread: threading.Thread | None = None
        self._media_done = threading.Event()
        self._media_result: dict[str, Any] | None = None
        self._media_failure: str | None = None
        self._media_elapsed_ms: int | None = None
        self._media_termination_reason: str | None = None
        self._pre_start_telemetry: RuntimeTelemetrySnapshot | None = None
        self._post_stop_telemetry: RuntimeTelemetrySnapshot | None = None
        self._wearable_prepared = False
        self._wearable_started = False
        self._wearable_topology_contract: str | None = None
        self._same_handle_mode = False
        self._same_handle_start_acknowledged = False
        self._same_handle_media_transfer_confirmed = False
        self._same_handle_local_cleanup_confirmed = False
        self._same_handle_lease_never_acquired_caller_retains_handle = False
        self._same_handle_last_phase: str | None = None
        self._same_handle_remote_cleanup_acknowledged = False
        self._control_calls = {name: 0 for name in (
            "prepare", "start", "cancel", "join", "close", "telemetry"
        )}
        self._late_control_calls = 0
        self._control_retry_attempts = 0
        self._cleanup_errors = 0
        self._tls_connector_cleanup_pending = False
        self._stop_requested = False
        self._references_cleared = False

    def plan(self) -> dict[str, Any]:
        config = self._config
        if config is None:
            raise HostControlStateError("session configuration was already cleared")
        return _plan(config)

    def _require_state(self, expected: str) -> HostControlConfig:
        with self._state_lock:
            if self._state != expected or self._config is None:
                raise HostControlStateError(
                    f"CALL-020M phase requires {expected} state"
                )
            return self._config

    def _set_state(self, state: str) -> None:
        with self._state_lock:
            self._state = state

    def prepare(
        self,
        *,
        authorization: OneShotOperatorAuthorization,
        verifier: AuthorizationVerifier,
    ) -> dict[str, Any]:
        with self._lifecycle_lock:
            config = self._require_state("dormant")
            try:
                config.validate_for_execution()
            except Exception:
                authorization.zeroize()
                self._authorization_audit = authorization.audit()
                raise
            try:
                authorization.consume(
                    expected_run_id=config.run_id,
                    verifier=verifier,
                    clock=self._clock,
                    timeout_ms=config.control_timeout_ms,
                )
                self._authorization_audit = authorization.audit()
                self._run_registry.reserve(config.run_id)
            except HostControlBlocked:
                self._authorization_audit = authorization.audit()
                self._set_state("failed")
                raise
            self._set_state("prepared")
            return self.audit()

    def preflight(
        self,
        *,
        wearable_control: WearableControlConnector | None,
        wearable_attestation: WearableControlAttestation | None,
        tls_connector: ExternallyVerifiedTlsConnector | None,
        tls_connector_attestation: TlsConnectorAttestation | None,
        serial_factory: ExplicitSerialFactory | None,
    ) -> dict[str, Any]:
        with self._lifecycle_lock:
            config = self._require_state("prepared")
            if wearable_control is None or wearable_attestation is None:
                self._set_state("failed")
                raise HostControlBlocked(
                    "wearable_control_connector_missing", stage="preflight"
                )
            if tls_connector is None or tls_connector_attestation is None:
                self._set_state("failed")
                raise HostControlBlocked(
                    "externally_verified_tls_connector_missing", stage="preflight"
                )
            if serial_factory is None:
                self._set_state("failed")
                raise HostControlBlocked(
                    "explicit_serial_factory_missing", stage="preflight"
                )
            try:
                wearable_attestation.validate(
                    required_timeout_ms=config.control_timeout_ms
                )
                tls_connector_attestation.validate()
                retention_callback = getattr(
                    tls_connector, "retry_failed_open_cleanup", None
                )
                retains_partial = (
                    tls_connector_attestation.retains_partial_open_for_bounded_retry
                )
                if (
                    retains_partial and not callable(retention_callback)
                ):
                    raise HostControlError(
                        "retained TLS cleanup contract lacks retry operation"
                    )
                if (
                    isinstance(tls_connector, DefaultOffHostTlsConnector)
                    and (
                        tls_connector_attestation.cleans_partial_open_before_raise
                        or not retains_partial
                    )
                ):
                    raise HostControlError(
                        "CALL-020N requires the retained TLS cleanup contract"
                    )
                for connector, names in (
                    (
                        wearable_control,
                        ("prepare", "start", "cancel", "join", "close", "telemetry"),
                    ),
                    (tls_connector, ("open_verified",)),
                    (serial_factory, ("open_explicit",)),
                ):
                    if any(not callable(getattr(connector, name, None)) for name in names):
                        raise HostControlError("external connector shape is incomplete")
                logical_separation = (
                    wearable_attestation.logically_separate_and_not_interleaved_with_media
                    and not wearable_attestation.out_of_band_from_media
                )
                if logical_separation:
                    if wearable_control is not serial_factory:
                        raise HostControlError(
                            "same-handle control and media require one connector object"
                        )
                    required_phase_operations = (
                        "phase_snapshot",
                        "abort_before_media_transfer",
                        "recover_media_return_after_quiescence",
                        "close_returned_handle",
                    )
                    if any(
                        not callable(getattr(wearable_control, name, None))
                        for name in required_phase_operations
                    ):
                        raise HostControlError(
                            "same-handle connector lifecycle shape is incomplete"
                        )
            except Exception:
                self._set_state("failed")
                raise HostControlBlocked(
                    "external_connector_attestation_rejected", stage="preflight"
                ) from None
            self._wearable = wearable_control
            self._wearable_attestation = wearable_attestation
            logical_separation = (
                wearable_attestation.logically_separate_and_not_interleaved_with_media
                and not wearable_attestation.out_of_band_from_media
            )
            self._wearable_topology_contract = (
                "logical_phase_separation"
                if logical_separation
                else "legacy_out_of_band"
            )
            self._same_handle_mode = logical_separation
            self._tls_connector = tls_connector
            self._tls_connector_attestation = tls_connector_attestation
            self._serial_factory = serial_factory
            self._set_state("preflighted")
            return self.audit()

    def _command(self, action: str) -> ControlCommand:
        config = self._config
        if config is None:
            raise HostControlStateError("session configuration is unavailable")
        command = ControlCommand(
            run_id=config.run_id,
            operation_id=f"{config.run_id}:{action}:1",
            action=action,
            timeout_ms=config.control_timeout_ms,
        )
        command.validate()
        return command

    def _invoke_wearable(self, action: str) -> object:
        wearable = self._wearable
        if wearable is None:
            raise HostControlError("wearable connector is unavailable")
        command = self._command(action)
        callback = getattr(wearable, action, None)
        if not callable(callback):
            raise HostControlError("wearable connector operation is unavailable")
        start_ns = _clock_now(self._clock)
        self._control_calls[action] += 1
        try:
            result = callback(command)
        except Exception:
            raise HostControlError("wearable connector operation failed") from None
        end_ns = _clock_now(self._clock)
        if end_ns < start_ns:
            raise HostControlError("wearable control clock regressed")
        if end_ns - start_ns > command.timeout_ms * 1_000_000:
            self._late_control_calls += 1
            raise HostControlError("wearable connector exceeded its timeout contract")
        return result

    def _invoke_ack(self, action: str, *, states: set[str]) -> WearableControlAck:
        command = self._command(action)
        result = self._invoke_wearable(action)
        if not isinstance(result, WearableControlAck):
            raise HostControlError("wearable connector returned an invalid ack")
        result.validate(command, states=states)
        return result

    def _invoke_ack_with_retry(self, action: str, *, states: set[str]) -> bool:
        """Bound cleanup retries with one stable operation ID per action."""

        for attempt in range(CONTROL_CLEANUP_ATTEMPTS):
            try:
                self._invoke_ack(action, states=states)
                return True
            except Exception:
                if attempt + 1 < CONTROL_CLEANUP_ATTEMPTS:
                    self._control_retry_attempts += 1
        return False

    def _retry_failed_tls_connector_cleanup(self) -> bool:
        connector = self._tls_connector
        callback = getattr(connector, "retry_failed_open_cleanup", None)
        if not callable(callback):
            attestation = self._tls_connector_attestation
            # Legacy connectors may attest complete cleanup before raising.
            # A retained-resource contract must keep its retry operation
            # callable for the full M lifecycle.
            return not (
                attestation is not None
                and attestation.retains_partial_open_for_bounded_retry
            )
        try:
            return callback() is True
        except Exception:
            return False

    def _build_endpoint_config(
        self, identity: EndpointIdentity
    ) -> PcEndpointCompositionConfig:
        config = self._config
        if config is None:
            raise HostControlStateError("session configuration is unavailable")
        serial = ExplicitOsSerialConfig(
            port_name=config.exact_port,
            connection_id=f"serial-{config.run_id}",
            enabled=True,
            baudrate=config.serial_baudrate,
            read_timeout_ms=config.transport_call_timeout_ms,
            write_timeout_ms=config.transport_call_timeout_ms,
        )
        serial_adapter = HostSerialAdapterConfig(
            per_call_timeout_ms=config.transport_call_timeout_ms,
            max_operation_timeout_ms=config.transport_operation_timeout_ms,
        )
        tls = ConnectedTlsStreamConfig(
            identity=identity,
            role="device",
            enabled=True,
            expected_alpn=DEFAULT_ALPN,
            per_call_timeout_ms=config.transport_call_timeout_ms,
            max_operation_timeout_ms=config.transport_operation_timeout_ms,
        )
        bridge = ConcurrentBridgeConfig(
            identity=identity,
            bridge_clock_id=f"pc-{config.run_id}",
            frame_count=config.frame_count,
            timeout_steps=max(
                1,
                config.transport_operation_timeout_ms
                // config.transport_call_timeout_ms,
            ),
            receive_attempts=1,
            send_attempts=1,
            startup_grace_ns=20_000_000,
            frame_deadline_ns=config.frame_deadline_ms * 1_000_000,
            max_runtime_ms=config.max_runtime_ms,
            join_timeout_ms=config.stop_join_timeout_ms,
        )
        return PcEndpointCompositionConfig(
            identity=identity,
            serial=serial,
            serial_adapter=serial_adapter,
            tls=tls,
            bridge=bridge,
            enabled=True,
        )

    def _cleanup_prepared_wearable(self) -> int:
        if not self._wearable_prepared or self._wearable is None:
            return 0
        errors = 0
        close_confirmed = False
        for action, states in (
            ("cancel", {"STOPPING", "JOINED", "TERMINAL", "CLOSED"}),
            ("join", {"JOINED", "TERMINAL", "CLOSED"}),
            ("close", {"CLOSED"}),
        ):
            confirmed = self._invoke_ack_with_retry(action, states=states)
            if not confirmed:
                errors += 1
            if action == "close":
                close_confirmed = confirmed
        if close_confirmed:
            self._wearable_prepared = False
            self._wearable_started = False
            if self._same_handle_mode:
                self._same_handle_remote_cleanup_acknowledged = True
        return errors

    def _same_handle_phase(self) -> str | None:
        """Read one redacted connector phase; never infer device state from it."""

        if not self._same_handle_mode or self._wearable is None:
            return None
        callback = getattr(self._wearable, "phase_snapshot", None)
        if not callable(callback):
            return None
        try:
            snapshot = callback()
        except Exception:
            return None
        if not isinstance(snapshot, dict):
            return None
        phase = snapshot.get("state")
        if not isinstance(phase, str) or phase not in {
            "dormant",
            "CONTROL_OWNED",
            "PREPARED",
            "STOPPING",
            "JOINED",
            "HANDOFF_READY",
            "START_UNCERTAIN",
            "FAILED",
            "REMOTE_CLOSED_LOCAL_CLOSING",
            "MEDIA_TRANSFERRED",
            "MEDIA_RETURNED",
            "LOCAL_CLOSED",
        }:
            return None
        self._same_handle_last_phase = phase
        return phase

    def _cleanup_same_handle_local(self, *, media_quiescent: bool) -> bool:
        """Clean only host ownership; this never sends CONTROL/RESULT bytes.

        Once START may have been accepted, remote cancel/join/close/telemetry
        is forbidden on the media handle.  Recovery of a facade return is
        permitted only after M has joined the worker and L/K close returned.
        """

        connector = self._wearable
        if not self._same_handle_mode or connector is None:
            return False
        phase = self._same_handle_phase()
        if phase == "LOCAL_CLOSED":
            self._same_handle_local_cleanup_confirmed = True
            return True
        if media_quiescent and phase == "MEDIA_TRANSFERRED":
            callback = getattr(
                connector, "recover_media_return_after_quiescence", None
            )
            try:
                recovered = callable(callback) and callback() is True
            except Exception:
                recovered = False
            if recovered:
                phase = self._same_handle_phase()
        if phase == "MEDIA_RETURNED":
            callback = getattr(connector, "close_returned_handle", None)
            try:
                closed = callable(callback) and callback() is True
            except Exception:
                closed = False
            if closed:
                phase = self._same_handle_phase()
        elif phase != "MEDIA_TRANSFERRED":
            callback = getattr(connector, "abort_before_media_transfer", None)
            try:
                closed = callable(callback) and callback() is True
            except Exception:
                closed = False
            if closed:
                phase = self._same_handle_phase()
                # dormant means M never acquired ownership; the injecting
                # caller retains it under the constructor contract.
                if phase == "dormant":
                    self._same_handle_lease_never_acquired_caller_retains_handle = True
                    self._same_handle_local_cleanup_confirmed = False
                    return True
        confirmed = phase == "LOCAL_CLOSED"
        self._same_handle_local_cleanup_confirmed = confirmed
        if confirmed:
            self._wearable_prepared = False
            self._wearable_started = False
        return confirmed

    def _cleanup_same_handle_after_failure(self, *, media_quiescent: bool) -> int:
        """Use remote cleanup only while START is definitely not accepted."""

        phase = self._same_handle_phase()
        errors = 0
        if (
            not self._same_handle_start_acknowledged
            and phase in {"CONTROL_OWNED", "PREPARED", "STOPPING", "JOINED"}
            and self._wearable_prepared
        ):
            errors += self._cleanup_prepared_wearable()
            if self._same_handle_phase() == "LOCAL_CLOSED":
                self._same_handle_local_cleanup_confirmed = True
            elif not self._cleanup_same_handle_local(
                media_quiescent=media_quiescent
            ):
                errors += 1
        else:
            if not self._cleanup_same_handle_local(media_quiescent=media_quiescent):
                errors += 1
        return errors

    def _close_endpoint_once(self) -> bool:
        """Close one retained endpoint and verify L's cleanup audit when present."""

        endpoint = self._endpoint
        if endpoint is None:
            self._endpoint_close_confirmed = True
            return True
        if self._endpoint_close_confirmed:
            return True
        try:
            endpoint.close()
        except Exception:
            return False
        self._endpoint_close_callback_returned = True
        audit_callback = getattr(endpoint, "audit", None)
        if callable(audit_callback):
            try:
                endpoint_audit = audit_callback()
            except Exception:
                return False
            if not isinstance(endpoint_audit, dict):
                return False
            # Repository L exposes these fields. External test doubles without
            # its version remain governed by the close callback contract.
            if "composition_version" in endpoint_audit:
                if (
                    endpoint_audit.get("state") != "closed"
                    or endpoint_audit.get("both_legs_quiesced") is not True
                    or endpoint_audit.get("transport_references_cleared") is not True
                    or endpoint_audit.get("close_errors") != 0
                    or endpoint_audit.get("rollback_errors") != 0
                ):
                    return False
        self._endpoint_close_confirmed = True
        return True

    def open(self) -> dict[str, Any]:
        with self._lifecycle_lock:
            config = self._require_state("preflighted")
            self._set_state("opening")
            tls_socket: object | None = None
            tls_transferred = False
            reason = "wearable_prepare_failed"
            try:
                prepare_command = self._command("prepare")
                # Acceptance is unknown once the external callback is entered.
                # Cleanup is therefore required even if the callback raises or
                # returns a malformed object.
                self._wearable_prepared = True
                prepared = self._invoke_wearable("prepare")
                if not isinstance(prepared, WearablePreparedSession):
                    raise HostControlError("wearable prepare result shape is invalid")
                identity = prepared.validate(prepare_command)
                self._pre_start_telemetry = prepared.pre_start_telemetry

                reason = "external_tls_connector_failed"
                tls_connector = self._tls_connector
                if tls_connector is None:
                    raise HostControlError("TLS connector is unavailable")
                connector_attestation = self._tls_connector_attestation
                if connector_attestation is None:
                    raise HostControlError("TLS connector attestation is unavailable")
                request = TlsOpenRequest(
                    run_id=config.run_id,
                    identity=identity,
                    expected_alpn=connector_attestation.expected_alpn,
                    connect_timeout_ms=connector_attestation.max_connect_timeout_ms,
                )
                request.validate()
                tls_open_start_ns = _clock_now(self._clock)
                try:
                    bundle = tls_connector.open_verified(request)
                except Exception:
                    self._tls_connector_cleanup_pending = not (
                        self._retry_failed_tls_connector_cleanup()
                    )
                    raise HostControlError("external TLS connector failed") from None
                if not isinstance(bundle, VerifiedTlsOpenResult):
                    raise HostControlError("TLS connector result shape is invalid")
                # Take ownership before every post-return check so a late or
                # otherwise rejected valid bundle cannot leak its socket.
                tls_socket = bundle.tls_socket
                tls_open_end_ns = _clock_now(self._clock)
                if tls_open_end_ns < tls_open_start_ns:
                    raise HostControlError("TLS connector clock regressed")
                if (
                    tls_open_end_ns - tls_open_start_ns
                    > request.connect_timeout_ms * 1_000_000
                ):
                    raise HostControlError("TLS connector exceeded its timeout contract")
                bundle.validate(request)

                if self._same_handle_mode:
                    # START/ACK is deliberately the last CONTROL exchange.
                    # L may ask K for the serial driver only after this returns.
                    reason = "same_handle_start_or_handoff_failed"
                    self._invoke_ack("start", states={"STARTING", "RUNNING"})
                    self._wearable_started = True
                    self._same_handle_start_acknowledged = True
                    if self._same_handle_phase() != "HANDOFF_READY":
                        raise HostControlError(
                            "same-handle connector did not enter handoff-ready phase"
                        )

                reason = "pc_endpoint_composition_open_failed"
                endpoint = self._endpoint_factory(self._build_endpoint_config(identity))
                self._endpoint = endpoint
                self._endpoint_close_confirmed = False
                self._endpoint_close_callback_returned = False
                serial_factory = self._serial_factory
                if serial_factory is None:
                    raise HostControlError("serial factory is unavailable")
                tls_transferred = True
                endpoint.open(
                    serial_factory=serial_factory,
                    serial_registry=self._serial_registry,
                    tls_socket=bundle.tls_socket,
                    tls_attestation=bundle.tls_attestation,
                    authentication_decision=bundle.authentication_decision,
                )
                if self._same_handle_mode:
                    if self._same_handle_phase() != "MEDIA_TRANSFERRED":
                        raise HostControlError(
                            "same-handle endpoint did not adopt the media lease"
                        )
                    self._same_handle_media_transfer_confirmed = True
                bundle = None
                tls_socket = None
                self._set_state("open")
                return self.audit()
            except Exception:
                errors = 0
                if self._tls_connector_cleanup_pending:
                    errors += 1
                if tls_socket is not None and not tls_transferred:
                    errors += _cancel_close_socket(tls_socket)
                endpoint = self._endpoint
                if endpoint is not None:
                    if not self._close_endpoint_once():
                        errors += 1
                if self._same_handle_mode:
                    thread = self._media_thread
                    media_quiescent = (
                        self._endpoint_close_callback_returned
                        and (thread is None or not thread.is_alive())
                    )
                    errors += self._cleanup_same_handle_after_failure(
                        media_quiescent=media_quiescent
                    )
                else:
                    errors += self._cleanup_prepared_wearable()
                self._cleanup_errors += errors
                self._set_state("failed")
                raise HostControlBlocked(
                    reason, stage="open", cleanup_errors=errors
                ) from None

    def _media_worker(self) -> None:
        endpoint = self._endpoint
        started_ns = _clock_now(self._clock)
        try:
            if endpoint is None:
                raise HostControlError("PC endpoint is unavailable")
            result = endpoint.start()
            if not isinstance(result, dict) or result.get("result") != "PASS":
                raise HostControlError("PC endpoint returned an invalid result")
            direction_stats = result.get("direction_stats")
            if not isinstance(direction_stats, dict):
                raise HostControlError("PC endpoint result lacks direction counters")
            safe: dict[str, dict[str, int]] = {}
            for direction in ("uplink", "downlink"):
                values = direction_stats.get(direction)
                if not isinstance(values, dict):
                    raise HostControlError("PC endpoint direction counters are invalid")
                safe[direction] = {
                    name: _bounded_int(
                        values.get(name),
                        label=name,
                        minimum=0,
                        maximum=2**31 - 1,
                    )
                    for name in (
                        "frames_expected",
                        "frames_received",
                        "frames_forwarded",
                        "receive_retry_count",
                        "send_retry_count",
                        "backpressure_drops",
                        "deadline_misses_before_send",
                        "deadline_misses_after_send",
                    )
                }
            self._media_result = {
                "result": "PASS",
                "directions": safe,
                "raw_audio_present": False,
                "transport_provenance_proven": False,
            }
            self._media_termination_reason = "bridge_completed"
        except Exception:
            self._media_failure = "pc_endpoint_run_failed"
            self._media_termination_reason = (
                "operator_stop_requested"
                if self._stop_requested
                else "bridge_failed"
            )
        finally:
            finished_ns = _clock_now(self._clock)
            if finished_ns < started_ns:
                self._media_failure = "host_monotonic_clock_regressed"
                self._media_termination_reason = "clock_failure"
            else:
                self._media_elapsed_ms = (finished_ns - started_ns) // 1_000_000
            self._media_done.set()

    def start(self) -> dict[str, Any]:
        with self._lifecycle_lock:
            self._require_state("open")
            self._set_state("starting")
            try:
                if self._same_handle_mode:
                    if (
                        not self._same_handle_start_acknowledged
                        or not self._same_handle_media_transfer_confirmed
                        or self._same_handle_phase() != "MEDIA_TRANSFERRED"
                    ):
                        raise HostControlError(
                            "same-handle media lease is not ready"
                        )
                else:
                    self._invoke_ack("start", states={"STARTING", "RUNNING"})
                    self._wearable_started = True
                thread = threading.Thread(
                    target=self._media_worker,
                    name="call020m-media-owner",
                    daemon=True,
                )
                self._media_thread = thread
                self._set_state("running")
                thread.start()
            except Exception:
                errors = 0
                if self._same_handle_mode:
                    endpoint = self._endpoint
                    if endpoint is not None and not self._endpoint_close_confirmed:
                        if not self._close_endpoint_once():
                            errors += 1
                    thread = self._media_thread
                    media_quiescent = (
                        self._endpoint_close_callback_returned
                        and (thread is None or not thread.is_alive())
                    )
                    errors += self._cleanup_same_handle_after_failure(
                        media_quiescent=media_quiescent
                    )
                else:
                    errors = self._cleanup_prepared_wearable()
                self._cleanup_errors += errors
                self._set_state("failed")
                raise HostControlBlocked(
                    "start_or_media_worker_failed",
                    stage="start",
                    cleanup_errors=errors,
                ) from None
            return self.audit()

    def stop(self) -> dict[str, Any]:
        with self._lifecycle_lock:
            return self._stop_locked()

    def _stop_locked(self) -> dict[str, Any]:
        """Stop while the caller owns ``_lifecycle_lock``."""

        with self._state_lock:
            state = self._state
            if state == "stopped":
                return self._audit_locked()
            if state not in {"open", "running", "failed"}:
                raise HostControlStateError(
                    "CALL-020M stop requires open, running, or failed state"
                )
            self._state = "stopping"
            self._stop_requested = True
            thread = self._media_thread
            endpoint = self._endpoint
        errors = 0
        media_was_done = self._media_done.is_set()
        if endpoint is not None and thread is not None and not media_was_done:
            try:
                endpoint.request_cancel()
            except Exception:
                errors += 1
        if self._wearable_prepared and not self._same_handle_mode:
            if not self._invoke_ack_with_retry(
                "cancel",
                states={"STOPPING", "JOINED", "TERMINAL", "CLOSED"},
            ):
                errors += 1
        if thread is not None:
            config = self._config
            timeout_ms = config.stop_join_timeout_ms if config else 10
            thread.join(timeout_ms / 1_000)
            if thread.is_alive():
                errors += 1
        if self._wearable_prepared and not self._same_handle_mode:
            if not self._invoke_ack_with_retry(
                "join", states={"JOINED", "TERMINAL", "CLOSED"}
            ):
                errors += 1
            try:
                telemetry = self._invoke_wearable("telemetry")
                if not isinstance(telemetry, RuntimeTelemetrySnapshot):
                    raise HostControlError("post-stop telemetry shape is invalid")
                telemetry.validate(expected_phase="post_stop")
                if not telemetry.externally_attested_runtime_measurement:
                    raise HostControlError("post-stop telemetry is not attested")
                self._post_stop_telemetry = telemetry
            except Exception:
                errors += 1
        if self._same_handle_mode:
            # No CONTROL or RESULT byte is legal while/after MEDIA ownership.
            # This observation is local metadata only and is not termination
            # proof for the device runtime.
            self._same_handle_phase()
        if self._media_failure is not None and not (
            self._stop_requested and not media_was_done
        ):
            errors += 1
        self._cleanup_errors += errors
        self._set_state("stopped" if errors == 0 else "failed")
        if errors:
            raise HostControlBlocked(
                "stop_or_quiescence_failed",
                stage="stop",
                cleanup_errors=errors,
            )
        return self.audit()

    def close(self) -> dict[str, Any]:
        with self._lifecycle_lock:
            # Re-read only after any in-flight open/start releases the same
            # lifecycle owner.  This prevents a stale STARTING/OPENING read
            # from skipping stop and clearing live resources.
            with self._state_lock:
                if self._state == "closed":
                    return self._audit_locked()
                state = self._state
            errors = 0
            if state in {"open", "running", "failed"}:
                try:
                    self._stop_locked()
                except Exception:
                    errors += 1
            endpoint = self._endpoint
            if endpoint is not None and not self._endpoint_close_confirmed:
                if not self._close_endpoint_once():
                    errors += 1
            thread = self._media_thread
            if thread is not None and thread.is_alive():
                config = self._config
                timeout_ms = config.stop_join_timeout_ms if config else 10
                thread.join(timeout_ms / 1_000)
            if thread is not None and thread.is_alive():
                # Keep every reference for a later cleanup attempt.  A CLOSED
                # result is forbidden while the media owner may still use it.
                self._cleanup_errors += errors + 1
                self._set_state("failed")
                raise HostControlBlocked(
                    "media_thread_not_quiescent",
                    stage="close",
                    cleanup_errors=errors + 1,
                )
            if self._same_handle_mode:
                if not (
                    self._same_handle_local_cleanup_confirmed
                    or self._same_handle_lease_never_acquired_caller_retains_handle
                ):
                    errors += self._cleanup_same_handle_after_failure(
                        media_quiescent=self._endpoint_close_callback_returned
                    )
                if not (
                    self._same_handle_local_cleanup_confirmed
                    or self._same_handle_lease_never_acquired_caller_retains_handle
                ):
                    self._cleanup_errors += errors + 1
                    self._set_state("failed")
                    raise HostControlBlocked(
                        "same_handle_local_cleanup_not_confirmed",
                        stage="close",
                        cleanup_errors=errors + 1,
                    )
                self._wearable_prepared = False
                self._wearable_started = False
            elif self._wearable_prepared:
                close_confirmed = self._invoke_ack_with_retry(
                    "close", states={"CLOSED"}
                )
                if not close_confirmed:
                    self._cleanup_errors += errors + 1
                    self._set_state("failed")
                    raise HostControlBlocked(
                        "wearable_close_not_confirmed",
                        stage="close",
                        cleanup_errors=errors + 1,
                    )
                self._wearable_prepared = False
                self._wearable_started = False
            if self._tls_connector_cleanup_pending:
                if not self._retry_failed_tls_connector_cleanup():
                    self._cleanup_errors += errors + 1
                    self._set_state("failed")
                    raise HostControlBlocked(
                        "tls_connector_cleanup_not_confirmed",
                        stage="close",
                        cleanup_errors=errors + 1,
                    )
                self._tls_connector_cleanup_pending = False
            if not self._endpoint_close_confirmed:
                # Local endpoint ownership is independent of stop telemetry or
                # wearable closure.  Retain the exact object and every other
                # reference until a later close confirms its cleanup.
                self._cleanup_errors += errors
                self._set_state("failed")
                raise HostControlBlocked(
                    "pc_endpoint_close_not_confirmed",
                    stage="close",
                    cleanup_errors=errors,
                )
            self._endpoint = None
            self._wearable = None
            self._tls_connector = None
            self._serial_factory = None
            self._wearable_attestation = None
            self._tls_connector_attestation = None
            self._config = None
            self._references_cleared = True
            self._cleanup_errors += errors
            self._set_state("closed")
            return self.audit()

    def _audit_locked(self) -> dict[str, Any]:
        authorization = self._authorization_audit or {
            "consumed": False,
            "accepted": False,
            "token_cleared": False,
            "token_or_run_identity_exposed": False,
        }
        return {
            "control_version": HOST_CONTROL_VERSION,
            "state": self._state,
            "default_enabled": False,
            "phase_order": list(CONTROL_PHASES),
            "authorization": dict(authorization),
            "control_calls": dict(self._control_calls),
            "late_control_calls": self._late_control_calls,
            "control_retry_attempts": self._control_retry_attempts,
            "stop_requested": self._stop_requested,
            "media_thread_started": self._media_thread is not None,
            "media_thread_done": self._media_done.is_set(),
            "media_result": dict(self._media_result) if self._media_result else None,
            "media_failure_code": self._media_failure,
            "host_monotonic_run_elapsed_ms": self._media_elapsed_ms,
            "media_termination_reason": self._media_termination_reason,
            "pre_start_telemetry": (
                self._pre_start_telemetry.summary()
                if self._pre_start_telemetry
                else None
            ),
            "post_stop_telemetry": (
                self._post_stop_telemetry.summary()
                if self._post_stop_telemetry
                else None
            ),
            "cleanup_errors": self._cleanup_errors,
            "tls_connector_cleanup_pending": self._tls_connector_cleanup_pending,
            "pc_endpoint_close_confirmed": self._endpoint_close_confirmed,
            "pc_endpoint_close_callback_returned": (
                self._endpoint_close_callback_returned
            ),
            "references_cleared": self._references_cleared,
            "exact_port_value_exposed": False,
            "run_or_routing_identity_exposed": False,
            "raw_audio_logged_or_persisted": False,
            "control_in_media_stream": False,
            "control_media_non_interleaving_required": True,
            "physical_out_of_band_control_proven_by_repository": False,
            "wearable_control_topology_contract": self._wearable_topology_contract,
            "media_open_requires_prepare_handoff": True,
            "same_handle_mode": self._same_handle_mode,
            "same_handle_start_acknowledged": (
                self._same_handle_start_acknowledged
            ),
            "same_handle_media_transfer_confirmed": (
                self._same_handle_media_transfer_confirmed
            ),
            "same_handle_last_local_phase": self._same_handle_last_phase,
            "same_handle_local_handle_cleanup_confirmed": (
                self._same_handle_local_cleanup_confirmed
            ),
            "same_handle_lease_never_acquired_caller_retains_handle": (
                self._same_handle_lease_never_acquired_caller_retains_handle
            ),
            "same_handle_remote_cleanup_acknowledged": (
                self._same_handle_remote_cleanup_acknowledged
            ),
            "same_handle_device_runtime_termination_proven": False,
            "same_handle_optional_result_phase": "DISABLED_NOT_RUN",
            "same_handle_media_open_blocked_pending_connector": False,
            "same_handle_connector_implemented_by_repository": True,
            "same_handle_runtime_integration": (
                "OFFLINE_HOST_CONTRACT_ONLY_NOT_VERIFIED"
            ),
            "closed_scope": "HOST_RESOURCES_ONLY_REMOTE_RUNTIME_UNCONFIRMED",
            "wearable_control_connector_implemented_by_repository": False,
            "tls_connector_implemented_by_repository": True,
            "tls_connector_default_off": True,
            "tls_session_authenticator_implemented_by_repository": False,
            "injected_connector_attestation_is_consistency_not_proof": True,
            "external_callback_timeout_is_post_return_check_only": True,
            "real_connector_enablement_blocked_pending_bounded_cancel_review": True,
            "hardware_or_network_evidence": "NOT_RUN",
            "p0_call": "NOT_RUN",
        }

    def audit(self) -> dict[str, Any]:
        with self._state_lock:
            return self._audit_locked()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render an inert CALL-020M operator plan; never execute I/O."
    )
    parser.add_argument("--plan-only", action="store_true", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--exact-port", required=True)
    parser.add_argument("--frame-count", type=int, default=500)
    parser.add_argument("--max-runtime-ms", type=int, default=15_000)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = HostControlConfig(
            run_id=args.run_id,
            exact_port=args.exact_port,
            enabled=False,
            plan_only=True,
            frame_count=args.frame_count,
            max_runtime_ms=args.max_runtime_ms,
        )
        result = _plan(config)
    except Exception:
        result = {
            "control_version": HOST_CONTROL_VERSION,
            "mode": "plan_only",
            "result": "BLOCKED",
            "reason_code": "plan_input_rejected",
            "routing_port_or_run_identity_exposed": False,
            "external_io_performed": False,
            "p0_call": "NOT_RUN",
        }
        print(json.dumps(result, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "AUTHORIZATION_ACTION",
    "CONTROL_PHASES",
    "ExternallyVerifiedTlsConnector",
    "HOST_CONTROL_VERSION",
    "HOST_TLS_CONNECTOR_VERSION",
    "ConnectedTlsSessionAuthenticator",
    "DefaultOffHostTlsConnector",
    "HostControlBlocked",
    "HostControlConfig",
    "HostControlError",
    "HostControlSession",
    "HostControlStateError",
    "HostTlsConnectorBlocked",
    "HostTlsConnectorConfig",
    "HostTlsPeerEvidence",
    "OneShotOperatorAuthorization",
    "RunIdentityRegistry",
    "RuntimeTelemetrySnapshot",
    "TlsConnectorAttestation",
    "TlsOpenRequest",
    "VerifiedTlsOpenResult",
    "WEARABLE_RUNNER_API_VERSION",
    "WEARABLE_RUNNER_VERSION",
    "WearableControlAck",
    "WearableControlAttestation",
    "WearableControlConnector",
    "WearablePreparedSession",
    "build_parser",
    "main",
]

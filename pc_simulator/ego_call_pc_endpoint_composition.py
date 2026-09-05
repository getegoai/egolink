"""CALL-020L default-off PC serial-to-TLS endpoint composition.

This module composes existing seams; it does not discover or construct any
transport.  Construction is inert.  The caller must invoke :meth:`open`
explicitly and transfer an exact serial factory plus an already-connected TLS
socket, frozen TLS attestation, and matching external authentication decision.
Only :meth:`open` may ask CALL-020K for the exact configured serial driver. In
CALL-020P the injected factory lends a facade over an already-open same handle
after a complete CONTROL START/ACK; L neither reopens that handle nor emits a
control byte, and closing K returns the facade to the external phase owner.

The wearable leg is K -> H -> ``FramedEndpoint``.  The relay-facing leg is
J -> ``FramedEndpoint``.  :meth:`start` invokes the existing CALL-020C four-
worker ``ConcurrentDuplexMediaBridge`` synchronously.  This layer never emits
in-band control, creates a socket, performs TLS/PKI/authentication, logs or
persists media, or exposes routing identities in results/audit output.
"""

from __future__ import annotations

import threading
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pc_simulator.ego_call_authenticated_relay import (
    ExternalAuthenticationDecision,
)
from pc_simulator.ego_call_concurrent_bridge import (
    BridgeClock,
    ConcurrentBridgeConfig,
    ConcurrentBridgeRunFailed,
    ConcurrentDuplexMediaBridge,
)
from pc_simulator.ego_call_media_io import (
    FRAME_BYTES,
    EndpointIdentity,
    FramedEndpoint,
    MediaIoError,
    MediaIoProtocolError,
)
from pc_simulator.ego_call_os_serial_wrapper import (
    ExplicitOsSerialConfig,
    ExplicitOsSerialConnection,
    ExplicitSerialFactory,
    OsSerialConnectionRegistry,
)
from pc_simulator.ego_call_serial_adapter import (
    MAX_WIRE_BYTES,
    HostSerialAdapterConfig,
    MonotonicClock as SerialClock,
    make_wearable_serial_endpoint,
)
from pc_simulator.ego_call_tls_stream_adapter import (
    ConnectedTlsOrderedByteStream,
    ConnectedTlsStreamConfig,
    InjectedConnectedTlsSocket,
    InjectedTlsConnectionAttestation,
    MonotonicClock as TlsClock,
)


PC_ENDPOINT_COMPOSITION_VERSION = "egolink.ego_call_pc_endpoint_composition.v0.1"


class PcEndpointCompositionError(MediaIoError):
    """Base error for the explicit PC endpoint lifecycle."""


class PcEndpointStateError(PcEndpointCompositionError):
    """A single-use lifecycle operation was attempted in the wrong state."""


class PcEndpointOpenError(MediaIoProtocolError):
    """Redacted explicit-open rejection with no routing or raw OS/TLS error."""

    def __init__(
        self,
        reason_code: str,
        *,
        serial_leg_created: bool = False,
        tls_leg_created: bool = False,
        rollback_errors: int = 0,
    ) -> None:
        super().__init__("PC endpoint composition open failed")
        self.reason_code = reason_code
        self.metadata = {
            "composition_version": PC_ENDPOINT_COMPOSITION_VERSION,
            "result": "FAIL",
            "stage": "explicit_open",
            "reason_code": reason_code,
            "serial_leg_created": serial_leg_created,
            "tls_leg_created": tls_leg_created,
            "rollback_errors": rollback_errors,
            "implicit_transport_open": False,
            "routing_or_media_exposed": False,
            "media_logged_or_persisted": False,
        }


class PcEndpointRunFailed(PcEndpointCompositionError):
    """Redacted terminal run result."""

    def __init__(self, reason_code: str, metadata: Mapping[str, Any]) -> None:
        super().__init__("PC endpoint composition run failed")
        self.reason_code = reason_code
        self.metadata = dict(metadata)


@dataclass(frozen=True)
class PcEndpointCompositionConfig:
    """One exact identity/profile shared by K, H, J and CALL-020C.

    ``serial.connection_id`` identifies the local OS-handle lifetime.  The TLS
    connection identity is supplied by the socket/attestation/decision trio at
    explicit open.  They are independent transport lifetimes; each must remain
    internally exact and neither is an authentication credential.
    """

    identity: EndpointIdentity
    serial: ExplicitOsSerialConfig
    serial_adapter: HostSerialAdapterConfig
    tls: ConnectedTlsStreamConfig
    bridge: ConcurrentBridgeConfig
    enabled: bool = False

    def validate(self) -> None:
        if type(self.enabled) is not bool:
            raise PcEndpointCompositionError("enabled must be an explicit boolean")
        self.identity.validate()
        self.serial.validate()
        self.serial_adapter.validate()
        self.tls.validate()
        self.bridge.validate()
        if self.tls.identity != self.identity or self.bridge.identity != self.identity:
            raise PcEndpointCompositionError(
                "serial/TLS/bridge session identity must be exactly shared"
            )
        if self.tls.role != "device":
            raise PcEndpointCompositionError(
                "the PC relay-facing TLS leg must bind the device role"
            )
        if self.serial.max_io_bytes < MAX_WIRE_BYTES:
            raise PcEndpointCompositionError(
                "serial max_io_bytes must carry one maximum EGLM wire"
            )
        if self.tls.max_transfer_bytes < MAX_WIRE_BYTES:
            raise PcEndpointCompositionError(
                "TLS max_transfer_bytes must carry one maximum EGLM wire"
            )
        if (
            self.serial.read_timeout_ms < self.serial_adapter.per_call_timeout_ms
            or self.serial.write_timeout_ms
            < self.serial_adapter.per_call_timeout_ms
        ):
            raise PcEndpointCompositionError(
                "K timeouts must cover H's bounded per-call timeout"
            )

    def validate_for_open(self) -> None:
        self.validate()
        if self.enabled is not True:
            raise PcEndpointCompositionError("PC endpoint composition is disabled")
        if self.serial.enabled is not True:
            raise PcEndpointCompositionError("explicit OS serial leg is disabled")
        if self.tls.enabled is not True:
            raise PcEndpointCompositionError("connected TLS leg is disabled")


def _cancel_close_unadmitted_tls_socket(tls_socket: object) -> int:
    errors = 0
    for name in ("cancel_pending_io", "close"):
        try:
            callback = getattr(tls_socket, name, None)
        except Exception:
            errors += 1
            continue
        if not callable(callback):
            errors += 1
            continue
        try:
            callback()
        except Exception:
            errors += 1
    return errors


def _device_binding_values(
    decision: ExternalAuthenticationDecision,
) -> tuple[str, ...]:
    binding = decision.binding
    return (
        binding.session_id,
        binding.role,
        binding.endpoint_id,
        binding.peer_endpoint_id,
        binding.source_clock_id,
    )


def _validate_explicit_tls_inputs(
    identity: EndpointIdentity,
    attestation: object,
    decision: object,
) -> None:
    if not isinstance(attestation, InjectedTlsConnectionAttestation):
        raise PcEndpointCompositionError("immutable TLS attestation is required")
    if not isinstance(decision, ExternalAuthenticationDecision):
        raise PcEndpointCompositionError(
            "external authentication decision is required"
        )
    expected = (
        identity.session_id,
        "device",
        identity.device_id,
        identity.guardian_id,
        identity.uplink_clock_id,
    )
    if _device_binding_values(decision) != expected:
        raise PcEndpointCompositionError(
            "TLS decision session, role, endpoints, or clock do not match"
        )
    if attestation.connection_id != decision.binding.connection_id:
        raise PcEndpointCompositionError(
            "TLS socket attestation and decision connection identities differ"
        )


def _bounded_counter(value: object) -> int:
    if type(value) is not int or value < 0:
        raise PcEndpointCompositionError("bridge returned an invalid counter")
    return value


def _summarize_bridge_result(result: object) -> dict[str, Any]:
    if not isinstance(result, Mapping) or result.get("result") != "PASS":
        raise PcEndpointCompositionError("bridge did not return a PASS result")
    worker_model = result.get("worker_model")
    direction_stats = result.get("direction_stats")
    buffer_lifecycle = result.get("buffer_lifecycle")
    if (
        not isinstance(worker_model, Mapping)
        or not isinstance(direction_stats, Mapping)
        or not isinstance(buffer_lifecycle, Mapping)
    ):
        raise PcEndpointCompositionError("bridge result shape is invalid")
    safe_directions: dict[str, dict[str, int]] = {}
    for direction in ("uplink", "downlink"):
        values = direction_stats.get(direction)
        if not isinstance(values, Mapping):
            raise PcEndpointCompositionError("bridge direction result is missing")
        safe_directions[direction] = {
            name: _bounded_counter(values.get(name))
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
    if worker_model.get("all_workers_joined") is not True:
        raise PcEndpointCompositionError("bridge workers did not all join")
    if buffer_lifecycle.get("all_accepted_mutable_media_zeroized") is not True:
        raise PcEndpointCompositionError("bridge media buffers were not all zeroized")
    return {
        "composition_version": PC_ENDPOINT_COMPOSITION_VERSION,
        "result": "PASS",
        "bridge_invoked": True,
        "profile": {
            "frame_duration_ms": 20,
            "frame_bytes": FRAME_BYTES,
            "full_duplex": True,
        },
        "worker_model": {
            "reader_workers": 2,
            "writer_workers": 2,
            "independent_direction_queues": True,
            "all_workers_joined": True,
        },
        "direction_stats": safe_directions,
        "buffer_lifecycle": {
            "all_accepted_mutable_media_zeroized": True,
            "external_serial_tls_copies_controlled": False,
        },
        "connection_truth": {
            "bridge_full_duplex_completed": True,
            "transport_evidence_evaluated_by_this_layer": False,
            "real_serial_or_tls_connection_proven": False,
            "reported_connected": False,
            "p0_call": "NOT_RUN",
        },
        "routing_or_media_exposed": False,
        "media_logged_or_persisted": False,
    }


class PcEndpointComposition:
    """Explicit-open, synchronous-start, single-use PC media endpoint."""

    def __init__(self, config: PcEndpointCompositionConfig) -> None:
        if not isinstance(config, PcEndpointCompositionConfig):
            raise PcEndpointCompositionError(
                "PcEndpointCompositionConfig is required"
            )
        config.validate()
        self._operation_lock = threading.Lock()
        self._close_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._config: PcEndpointCompositionConfig | None = config
        self._serial_connection: ExplicitOsSerialConnection | None = None
        self._wearable_endpoint: FramedEndpoint | None = None
        self._tls_stream: ConnectedTlsOrderedByteStream | None = None
        self._relay_endpoint: FramedEndpoint | None = None
        self._bridge: ConcurrentDuplexMediaBridge | None = None
        self._state = "dormant"
        self._open_attempted = False
        self._start_attempted = False
        self._cancel_requested = False
        self._bridge_invocations = 0
        self._rollback_errors = 0
        self._close_errors = 0
        self._legs_quiesced = False
        self._references_cleared = False

    def _cancelled(self) -> bool:
        with self._state_lock:
            return self._cancel_requested

    def open(
        self,
        *,
        serial_factory: ExplicitSerialFactory,
        tls_socket: InjectedConnectedTlsSocket,
        tls_attestation: InjectedTlsConnectionAttestation,
        authentication_decision: ExternalAuthenticationDecision,
        serial_registry: OsSerialConnectionRegistry | None = None,
        serial_clock: SerialClock | None = None,
        tls_clock: TlsClock | None = None,
        bridge_clock: BridgeClock | None = None,
    ) -> None:
        """Explicitly create both legs; ownership transfers at method entry."""

        with self._operation_lock:
            with self._state_lock:
                invalid_state = self._open_attempted or self._state != "dormant"
                if not invalid_state:
                    self._open_attempted = True
                    self._state = "opening"
                    config = self._config
                else:
                    config = None
            if invalid_state:
                _cancel_close_unadmitted_tls_socket(tls_socket)
                raise PcEndpointStateError(
                    "PC endpoint explicit open is single-use"
                )

            tls_leg_created = False
            serial_leg_created = False
            raw_tls_owned = True
            reason = "endpoint_open_failed"
            try:
                if config is None:
                    reason = "composition_configuration_unavailable"
                    raise PcEndpointCompositionError(reason)
                reason = "composition_configuration_rejected"
                config.validate_for_open()
                reason = "tls_binding_rejected"
                _validate_explicit_tls_inputs(
                    config.identity, tls_attestation, authentication_decision
                )
                if self._cancelled():
                    reason = "cancelled_during_open"
                    raise PcEndpointCompositionError(reason)

                reason = "tls_leg_rejected"
                tls_stream = ConnectedTlsOrderedByteStream(
                    tls_socket,
                    tls_attestation,
                    authentication_decision,
                    config.tls,
                    clock=tls_clock,
                )
                raw_tls_owned = False
                tls_leg_created = True
                with self._state_lock:
                    self._tls_stream = tls_stream
                relay_endpoint = FramedEndpoint(
                    tls_stream,
                    config.identity,
                    inbound_direction="downlink",
                    outbound_direction="uplink",
                )
                with self._state_lock:
                    self._relay_endpoint = relay_endpoint
                if self._cancelled():
                    reason = "cancelled_during_open"
                    raise PcEndpointCompositionError(reason)

                reason = "serial_leg_rejected"
                serial_connection = ExplicitOsSerialConnection.open_explicit(
                    config.serial,
                    factory=serial_factory,
                    registry=serial_registry,
                )
                serial_leg_created = True
                with self._state_lock:
                    self._serial_connection = serial_connection
                reason = "serial_framing_leg_rejected"
                wearable_endpoint = make_wearable_serial_endpoint(
                    serial_connection,
                    config.identity,
                    config=config.serial_adapter,
                    clock=serial_clock,
                )
                with self._state_lock:
                    self._wearable_endpoint = wearable_endpoint
                if self._cancelled():
                    reason = "cancelled_during_open"
                    raise PcEndpointCompositionError(reason)

                reason = "bridge_composition_rejected"
                bridge = ConcurrentDuplexMediaBridge(
                    config.bridge,
                    clock=bridge_clock,
                )
                with self._state_lock:
                    self._bridge = bridge
                    self._state = "ready"
                return
            except Exception:
                unadmitted_errors = 0
                if raw_tls_owned:
                    unadmitted_errors = _cancel_close_unadmitted_tls_socket(
                        tls_socket
                    )
                rollback = self._close_resources(clear_config=True)
                rollback += unadmitted_errors
                with self._state_lock:
                    self._rollback_errors += rollback
                    cancelled = self._cancel_requested
                    self._state = "cancelled" if cancelled else "failed"
                raise PcEndpointOpenError(
                    reason,
                    serial_leg_created=serial_leg_created,
                    tls_leg_created=tls_leg_created,
                    rollback_errors=rollback,
                ) from None

    def request_cancel(self) -> None:
        """Prompt out-of-band request; never writes a media/control byte."""

        with self._state_lock:
            self._cancel_requested = True
            bridge = self._bridge
            serial_connection = self._serial_connection
            tls_stream = self._tls_stream
            if self._state == "ready":
                self._state = "cancelled"
        for resource, name in (
            (bridge, "request_stop"),
            (serial_connection, "cancel_pending_io"),
            (tls_stream, "request_cancel"),
        ):
            try:
                callback = getattr(resource, name, None)
            except Exception:
                with self._state_lock:
                    self._close_errors += 1
                continue
            if callable(callback):
                try:
                    callback()
                except Exception:
                    with self._state_lock:
                        self._close_errors += 1

    def _close_resources(self, *, clear_config: bool) -> int:
        with self._close_lock:
            with self._state_lock:
                wearable_endpoint = self._wearable_endpoint
                tls_stream = self._tls_stream
                serial_connection = self._serial_connection
                self._wearable_endpoint = None
                self._relay_endpoint = None
                self._tls_stream = None
                self._serial_connection = None
                self._bridge = None
                if clear_config:
                    self._config = None
                    self._references_cleared = True
            errors = 0
            serial_stream = (
                wearable_endpoint.stream if wearable_endpoint is not None else None
            )
            for resource in (serial_stream, tls_stream, serial_connection):
                if resource is None:
                    continue
                try:
                    resource.close()
                except Exception:
                    errors += 1
            clean = errors == 0
            for resource in (serial_stream, tls_stream, serial_connection):
                if resource is None:
                    continue
                try:
                    audit_callback = getattr(resource, "audit", None)
                    if not callable(audit_callback):
                        continue
                    audit = audit_callback()
                    reported_error = bool(
                        audit.get("close_errors", 0)
                        or audit.get("cancel_errors", 0)
                        or audit.get("cancel_error", False)
                        or audit.get("registry_errors", 0)
                        or audit.get("owned_buffer_zeroization_failures", 0)
                    )
                    if reported_error:
                        errors += 1
                        clean = False
                except Exception:
                    errors += 1
                    clean = False
            with self._state_lock:
                self._close_errors += errors
                self._legs_quiesced = clean
            return errors

    def start(self) -> dict[str, Any]:
        """Run CALL-020C synchronously once, then close and clear both legs."""

        with self._operation_lock:
            with self._state_lock:
                if self._start_attempted:
                    raise PcEndpointStateError("PC endpoint start is single-use")
                if self._state != "ready" or self._cancel_requested:
                    raise PcEndpointStateError(
                        "PC endpoint must be ready and not cancelled before start"
                    )
                self._start_attempted = True
                self._state = "running"
                bridge = self._bridge
                wearable_endpoint = self._wearable_endpoint
                relay_endpoint = self._relay_endpoint
                self._bridge_invocations += 1
            if (
                bridge is None
                or wearable_endpoint is None
                or relay_endpoint is None
            ):
                self._close_resources(clear_config=True)
                with self._state_lock:
                    self._state = "failed"
                raise PcEndpointRunFailed(
                    "composition_not_ready",
                    self._failure_metadata("composition_not_ready"),
                ) from None

            summary: dict[str, Any] | None = None
            reason: str | None = None
            try:
                bridge_result = bridge.run(
                    wearable=wearable_endpoint,
                    relay=relay_endpoint,
                )
                summary = _summarize_bridge_result(bridge_result)
                bridge_result = None
            except ConcurrentBridgeRunFailed:
                reason = "concurrent_bridge_failed"
            except Exception:
                reason = "endpoint_or_bridge_failed"
            finally:
                self._close_resources(clear_config=True)

            with self._state_lock:
                cancelled = self._cancel_requested
                quiesced = self._legs_quiesced
                self._state = (
                    "cancelled"
                    if cancelled
                    else "completed"
                    if reason is None and quiesced
                    else "failed"
                )
            if cancelled:
                reason = "cancelled"
            elif not quiesced:
                reason = "endpoint_close_not_clean"
            if reason is not None or summary is None:
                reason = reason or "endpoint_run_failed"
                raise PcEndpointRunFailed(
                    reason,
                    self._failure_metadata(reason),
                ) from None
            return summary

    def _failure_metadata(self, reason_code: str) -> dict[str, Any]:
        with self._state_lock:
            return {
                "composition_version": PC_ENDPOINT_COMPOSITION_VERSION,
                "result": "FAIL",
                "reason_code": reason_code,
                "bridge_invoked": self._bridge_invocations > 0,
                "cancel_requested": self._cancel_requested,
                "both_legs_quiesced": self._legs_quiesced,
                "close_errors": self._close_errors,
                "routing_or_media_exposed": False,
                "media_logged_or_persisted": False,
                "reported_connected": False,
                "p0_call": "NOT_RUN",
            }

    def close(self) -> None:
        """Cancel promptly, then wait for open/start and both leg closes."""

        self.request_cancel()
        with self._operation_lock:
            self._close_resources(clear_config=True)
            with self._state_lock:
                self._state = "closed"

    def audit(self) -> dict[str, Any]:
        """Return lifecycle counters only; never routing identities or media."""

        with self._state_lock:
            return {
                "composition_version": PC_ENDPOINT_COMPOSITION_VERSION,
                "state": self._state,
                "default_enabled": False,
                "open_attempted": self._open_attempted,
                "start_attempted": self._start_attempted,
                "bridge_invocations": self._bridge_invocations,
                "cancel_requested": self._cancel_requested,
                "rollback_errors": self._rollback_errors,
                "close_errors": self._close_errors,
                "both_legs_quiesced": self._legs_quiesced,
                "transport_references_cleared": self._references_cleared,
                "implicit_serial_or_socket_open": False,
                "listener_dns_socket_tls_handshake_or_pki_performed": False,
                "control_plane": "separate_unimplemented_no_in_band_control",
                "external_logical_phase_factory_supported": True,
                "same_handle_physical_close_or_result_owned_by_l": False,
                "routing_values_exposed": False,
                "media_logged": False,
                "media_persisted": False,
                "p0_call": "NOT_RUN",
            }


__all__ = [
    "PC_ENDPOINT_COMPOSITION_VERSION",
    "PcEndpointComposition",
    "PcEndpointCompositionConfig",
    "PcEndpointCompositionError",
    "PcEndpointOpenError",
    "PcEndpointRunFailed",
    "PcEndpointStateError",
]

from __future__ import annotations

import json
import threading
import time
import unittest
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from unittest import mock

from pc_simulator import ego_call_authenticated_relay as relay_core
from pc_simulator import ego_call_concurrent_bridge as concurrent
from pc_simulator import ego_call_media_io as media_io
from pc_simulator import ego_call_os_serial_wrapper as os_serial
from pc_simulator import ego_call_pc_endpoint_composition as composition
from pc_simulator import ego_call_serial_adapter as serial_adapter
from pc_simulator import ego_call_tls_stream_adapter as tls_adapter


IDENTITY = media_io.EndpointIdentity(
    session_id="call020l-session-private",
    device_id="call020l-device-private",
    guardian_id="call020l-guardian-private",
    uplink_clock_id="call020l-device-clock-private",
    downlink_clock_id="call020l-guardian-clock-private",
)
ALPN = tls_adapter.DEFAULT_ALPN


def _zero(value: bytearray) -> None:
    value[:] = b"\x00" * len(value)


def _wire_frames(direction: str, count: int) -> bytearray:
    result = bytearray()
    config = media_io.MediaIoConfig(
        identity=IDENTITY,
        frame_count=count,
        max_cycles=count,
    )
    for sequence in range(count):
        frame = media_io._make_frame(config, direction, sequence)
        wire = media_io.FrameCodec.encode(frame)
        try:
            result.extend(wire)
        finally:
            media_io._zero(wire)
            frame.dispose()
    return result


class _FakeSerialDriver:
    def __init__(
        self,
        *,
        port: str,
        incoming: bytearray | None = None,
        block_reads: bool = False,
    ) -> None:
        self.port = port
        self.baudrate = 115_200
        self.timeout: float | None = 0.02
        self.write_timeout: float | None = 0.02
        self.exclusive = True
        self.is_open = True
        self.incoming = incoming if incoming is not None else bytearray()
        self.outgoing = bytearray()
        self.block_reads = block_reads
        self.cancelled = threading.Event()
        self.read_entered = threading.Event()
        self.read_calls = 0
        self.write_calls = 0
        self.cancel_read_calls = 0
        self.cancel_write_calls = 0
        self.close_calls = 0
        self.bytes_read = 0
        self.bytes_written = 0
        self.retained_buffers: list[bytearray] = []

    def readinto(self, target: memoryview) -> int:
        self.read_calls += 1
        self.read_entered.set()
        self.retained_buffers.append(target.obj)
        if self.block_reads:
            self.cancelled.wait(1.0)
            raise os_serial.DriverIoTimeout("cancelled fake read", progress=None)
        count = min(len(target), len(self.incoming), 37)
        if count:
            target[:count] = self.incoming[:count]
            self.incoming[:count] = b"\x00" * count
            del self.incoming[:count]
            self.bytes_read += count
        return count

    def write(self, source: memoryview) -> int:
        self.write_calls += 1
        self.retained_buffers.append(source.obj)
        count = min(len(source), 41)
        self.outgoing.extend(source[:count])
        self.bytes_written += count
        return count

    def cancel_read(self) -> None:
        self.cancel_read_calls += 1
        self.cancelled.set()

    def cancel_write(self) -> None:
        self.cancel_write_calls += 1
        self.cancelled.set()

    def close(self) -> None:
        self.close_calls += 1
        self.is_open = False
        self.cancelled.set()
        _zero(self.incoming)
        _zero(self.outgoing)

    def retained_buffers_are_zero(self) -> bool:
        return all(all(byte == 0 for byte in value) for value in self.retained_buffers)


class _FakeSerialFactory:
    def __init__(
        self,
        driver: _FakeSerialDriver | None,
        *,
        failure: Exception | None = None,
    ) -> None:
        self.driver = driver
        self.failure = failure
        self.calls: list[dict[str, object]] = []

    def open_explicit(self, **kwargs: object) -> _FakeSerialDriver:
        self.calls.append(dict(kwargs))
        if self.failure is not None:
            raise self.failure
        if self.driver is None:
            raise AssertionError("missing fake serial driver")
        return self.driver


class _FakeTlsSocket:
    def __init__(
        self,
        *,
        connection_id: str,
        incoming: bytearray | None = None,
        block_reads: bool = False,
    ) -> None:
        self.connection_id = connection_id
        self.incoming = incoming if incoming is not None else bytearray()
        self.outgoing = bytearray()
        self.block_reads = block_reads
        self.cancelled = threading.Event()
        self.recv_entered = threading.Event()
        self.timeout_seconds = 0.02
        self.recv_calls = 0
        self.send_calls = 0
        self.metadata_calls = 0
        self.cancel_calls = 0
        self.close_calls = 0
        self.bytes_received = 0
        self.bytes_sent = 0
        self.retained_buffers: list[bytearray] = []

    def recv_into(self, target: memoryview, size: int) -> int:
        self.recv_calls += 1
        self.recv_entered.set()
        self.retained_buffers.append(target.obj)
        if self.block_reads:
            self.cancelled.wait(1.0)
            raise tls_adapter.InjectedTlsSocketTimeout(
                "cancelled fake receive", progress=None
            )
        count = min(len(target), size, len(self.incoming), 43)
        if count:
            target[:count] = self.incoming[:count]
            self.incoming[:count] = b"\x00" * count
            del self.incoming[:count]
            self.bytes_received += count
        return count

    def send(self, source: memoryview) -> int:
        self.send_calls += 1
        self.retained_buffers.append(source.obj)
        count = min(len(source), 47)
        self.outgoing.extend(source[:count])
        self.bytes_sent += count
        return count

    def gettimeout(self) -> float:
        self.metadata_calls += 1
        return self.timeout_seconds

    def selected_alpn_protocol(self) -> str:
        self.metadata_calls += 1
        return ALPN

    def version(self) -> str:
        self.metadata_calls += 1
        return "TLSv1.3"

    def cancel_pending_io(self) -> None:
        self.cancel_calls += 1
        self.cancelled.set()

    def close(self) -> None:
        self.close_calls += 1
        self.cancelled.set()
        _zero(self.incoming)
        _zero(self.outgoing)

    def retained_buffers_are_zero(self) -> bool:
        return all(all(byte == 0 for byte in value) for value in self.retained_buffers)


def _binding(connection_id: str) -> relay_core.RelayEndpointBinding:
    return relay_core.RelayEndpointBinding(
        session_id=IDENTITY.session_id,
        role="device",
        endpoint_id=IDENTITY.device_id,
        peer_endpoint_id=IDENTITY.guardian_id,
        source_clock_id=IDENTITY.uplink_clock_id,
        connection_id=connection_id,
    )


def _decision(
    connection_id: str,
    *,
    binding: relay_core.RelayEndpointBinding | None = None,
) -> relay_core.ExternalAuthenticationDecision:
    now = time.monotonic_ns()
    return relay_core.ExternalAuthenticationDecision(
        decision_id="call020l-device-decision-private",
        authenticated=True,
        binding=binding or _binding(connection_id),
        valid_from_monotonic_ns=now - 1_000_000,
        expires_at_monotonic_ns=now + 5_000_000_000,
    )


def _attestation(connection_id: str) -> tls_adapter.InjectedTlsConnectionAttestation:
    return tls_adapter.InjectedTlsConnectionAttestation(
        handshake_complete=True,
        certificate_chain_verified=True,
        peer_identity_verified=True,
        peer_identity=IDENTITY.device_id,
        selected_alpn=ALPN,
        tls_version="TLSv1.3",
        connection_id=connection_id,
    )


def _config(
    *,
    enabled: bool = True,
    identity: media_io.EndpointIdentity = IDENTITY,
    frame_count: int = 2,
) -> composition.PcEndpointCompositionConfig:
    serial = os_serial.ExplicitOsSerialConfig(
        port_name="CALL020L-EXACT-FAKE-PORT",
        connection_id="call020l-serial-connection-private",
        enabled=True,
    )
    serial_config = serial_adapter.HostSerialAdapterConfig(
        per_call_timeout_ms=20,
        max_operation_timeout_ms=1_000,
    )
    tls = tls_adapter.ConnectedTlsStreamConfig(
        identity=identity,
        role="device",
        enabled=True,
        per_call_timeout_ms=20,
        max_operation_timeout_ms=1_000,
    )
    bridge = concurrent.ConcurrentBridgeConfig(
        identity=identity,
        bridge_clock_id="call020l-pc-bridge-clock-private",
        frame_count=frame_count,
        timeout_steps=10,
        receive_attempts=1,
        send_attempts=1,
        startup_grace_ns=20_000_000,
        frame_deadline_ns=500_000_000,
        max_runtime_ms=2_000,
        join_timeout_ms=500,
    )
    return composition.PcEndpointCompositionConfig(
        identity=identity,
        serial=serial,
        serial_adapter=serial_config,
        tls=tls,
        bridge=bridge,
        enabled=enabled,
    )


def _inputs(
    *,
    serial_driver: _FakeSerialDriver | None = None,
    serial_factory: _FakeSerialFactory | None = None,
    tls_socket: _FakeTlsSocket | None = None,
    tls_connection_id: str = "call020l-tls-connection-private",
) -> tuple[_FakeSerialFactory, _FakeSerialDriver, _FakeTlsSocket, dict[str, object]]:
    driver = serial_driver or _FakeSerialDriver(
        port="CALL020L-EXACT-FAKE-PORT"
    )
    factory = serial_factory or _FakeSerialFactory(driver)
    socket = tls_socket or _FakeTlsSocket(connection_id=tls_connection_id)
    arguments: dict[str, object] = {
        "serial_factory": factory,
        "serial_registry": os_serial.OsSerialConnectionRegistry(),
        "tls_socket": socket,
        "tls_attestation": _attestation(tls_connection_id),
        "authentication_decision": _decision(tls_connection_id),
    }
    return factory, driver, socket, arguments


def _contains_binary(value: object) -> bool:
    if isinstance(value, (bytes, bytearray, memoryview)):
        return True
    if isinstance(value, Mapping):
        return any(_contains_binary(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_binary(item) for item in value)
    return False


class EgoCallPcEndpointCompositionTests(unittest.TestCase):
    def test_constructor_is_inert_and_default_disabled_open_does_not_call_factory(self) -> None:
        factory, driver, socket, arguments = _inputs()
        endpoint = composition.PcEndpointComposition(_config(enabled=False))
        self.assertEqual((factory.calls, socket.metadata_calls), ([], 0))
        self.assertEqual(driver.read_calls + driver.write_calls, 0)

        with self.assertRaises(composition.PcEndpointOpenError) as raised:
            endpoint.open(**arguments)

        self.assertEqual(
            raised.exception.reason_code, "composition_configuration_rejected"
        )
        self.assertEqual(factory.calls, [])
        self.assertEqual(socket.metadata_calls + socket.recv_calls + socket.send_calls, 0)
        self.assertEqual((socket.cancel_calls, socket.close_calls), (1, 1))
        self.assertTrue(endpoint.audit()["transport_references_cleared"])

    def test_open_is_explicit_and_performs_no_media_before_start(self) -> None:
        factory, driver, socket, arguments = _inputs()
        endpoint = composition.PcEndpointComposition(_config())

        endpoint.open(**arguments)

        self.assertEqual(len(factory.calls), 1)
        self.assertGreaterEqual(socket.metadata_calls, 3)
        self.assertEqual(driver.read_calls + driver.write_calls, 0)
        self.assertEqual(socket.recv_calls + socket.send_calls, 0)
        self.assertEqual(endpoint.audit()["state"], "ready")
        endpoint.close()
        self.assertGreaterEqual(driver.close_calls, 1)
        self.assertGreaterEqual(socket.close_calls, 1)

    def test_healthy_fake_serial_to_tls_composition_runs_existing_bridge(self) -> None:
        frame_count = 2
        uplink = _wire_frames("uplink", frame_count)
        downlink = _wire_frames("downlink", frame_count)
        serial_incoming = bytearray(b"ESP-ROM:boot\r\n")
        serial_incoming.extend(uplink)
        driver = _FakeSerialDriver(
            port="CALL020L-EXACT-FAKE-PORT",
            incoming=serial_incoming,
        )
        socket = _FakeTlsSocket(
            connection_id="call020l-healthy-tls-connection",
            incoming=bytearray(downlink),
        )
        factory, _, _, arguments = _inputs(
            serial_driver=driver,
            tls_socket=socket,
            tls_connection_id=socket.connection_id,
        )
        endpoint = composition.PcEndpointComposition(
            _config(frame_count=frame_count)
        )

        endpoint.open(**arguments)
        bridge_calls = 0
        actual_run = concurrent.ConcurrentDuplexMediaBridge.run

        def observed_run(
            bridge: concurrent.ConcurrentDuplexMediaBridge,
            *,
            wearable: media_io.FramedEndpoint,
            relay: media_io.FramedEndpoint,
        ) -> dict[str, object]:
            nonlocal bridge_calls
            bridge_calls += 1
            self.assertEqual(
                (wearable.inbound_direction, wearable.outbound_direction),
                ("uplink", "downlink"),
            )
            self.assertEqual(
                (relay.inbound_direction, relay.outbound_direction),
                ("downlink", "uplink"),
            )
            self.assertEqual(wearable.identity, IDENTITY)
            self.assertEqual(relay.identity, IDENTITY)
            return actual_run(bridge, wearable=wearable, relay=relay)

        with mock.patch.object(
            composition.ConcurrentDuplexMediaBridge,
            "run",
            new=observed_run,
        ):
            result = endpoint.start()

        self.assertEqual(result["result"], "PASS")
        self.assertEqual(bridge_calls, 1)
        self.assertTrue(result["bridge_invoked"])
        self.assertEqual(
            result["direction_stats"]["uplink"]["frames_forwarded"],
            frame_count,
        )
        self.assertEqual(
            result["direction_stats"]["downlink"]["frames_forwarded"],
            frame_count,
        )
        self.assertEqual(driver.bytes_written, len(downlink))
        self.assertEqual(socket.bytes_sent, len(uplink))
        self.assertEqual(len(factory.calls), 1)
        self.assertTrue(
            result["connection_truth"]["bridge_full_duplex_completed"]
        )
        self.assertFalse(
            result["connection_truth"][
                "transport_evidence_evaluated_by_this_layer"
            ]
        )
        self.assertFalse(
            result["connection_truth"]["real_serial_or_tls_connection_proven"]
        )
        self.assertEqual(endpoint.audit()["bridge_invocations"], 1)
        self.assertEqual(endpoint.audit()["state"], "completed")
        self.assertTrue(endpoint.audit()["both_legs_quiesced"])
        self.assertTrue(driver.retained_buffers_are_zero())
        self.assertTrue(socket.retained_buffers_are_zero())
        _zero(uplink)
        _zero(downlink)

    def test_identity_config_mismatch_rejects_during_inert_construction(self) -> None:
        other = replace(IDENTITY, session_id="call020l-wrong-session")
        config = _config()
        mismatched = replace(config, tls=replace(config.tls, identity=other))
        with self.assertRaises(composition.PcEndpointCompositionError):
            composition.PcEndpointComposition(mismatched)

    def test_tls_binding_mismatch_closes_socket_before_serial_open(self) -> None:
        factory, _, socket, arguments = _inputs()
        wrong_binding = replace(
            _binding(socket.connection_id),
            source_clock_id="call020l-wrong-clock",
        )
        arguments["authentication_decision"] = _decision(
            socket.connection_id,
            binding=wrong_binding,
        )
        endpoint = composition.PcEndpointComposition(_config())

        with self.assertRaises(composition.PcEndpointOpenError) as raised:
            endpoint.open(**arguments)

        self.assertEqual(raised.exception.reason_code, "tls_binding_rejected")
        self.assertEqual(factory.calls, [])
        self.assertEqual(socket.recv_calls + socket.send_calls, 0)
        self.assertGreaterEqual(socket.close_calls, 1)

    def test_actual_tls_connection_mismatch_rejects_before_serial_open(self) -> None:
        factory, _, socket, arguments = _inputs()
        socket.connection_id = "call020l-swapped-live-connection"
        endpoint = composition.PcEndpointComposition(_config())

        with self.assertRaises(composition.PcEndpointOpenError) as raised:
            endpoint.open(**arguments)

        self.assertEqual(raised.exception.reason_code, "tls_leg_rejected")
        self.assertEqual(factory.calls, [])
        self.assertEqual(socket.recv_calls + socket.send_calls, 0)
        self.assertGreaterEqual(socket.close_calls, 1)

    def test_serial_open_failure_rolls_back_admitted_tls_leg(self) -> None:
        driver = _FakeSerialDriver(port="CALL020L-EXACT-FAKE-PORT")
        factory = _FakeSerialFactory(
            driver,
            failure=RuntimeError("raw COM and routing detail"),
        )
        _, _, socket, arguments = _inputs(
            serial_driver=driver,
            serial_factory=factory,
        )
        endpoint = composition.PcEndpointComposition(_config())

        with self.assertRaises(composition.PcEndpointOpenError) as raised:
            endpoint.open(**arguments)

        self.assertEqual(raised.exception.reason_code, "serial_leg_rejected")
        self.assertIsNone(raised.exception.__cause__)
        self.assertNotIn("raw COM", repr(raised.exception))
        self.assertEqual(len(factory.calls), 1)
        self.assertGreaterEqual(socket.close_calls, 1)
        self.assertTrue(endpoint.audit()["transport_references_cleared"])

    def test_wiring_failure_closes_both_created_legs(self) -> None:
        factory, driver, socket, arguments = _inputs()
        endpoint = composition.PcEndpointComposition(_config())
        with mock.patch(
            "pc_simulator.ego_call_pc_endpoint_composition.make_wearable_serial_endpoint",
            side_effect=RuntimeError("raw routing detail"),
        ):
            with self.assertRaises(composition.PcEndpointOpenError) as raised:
                endpoint.open(**arguments)

        self.assertEqual(
            raised.exception.reason_code, "serial_framing_leg_rejected"
        )
        self.assertEqual(len(factory.calls), 1)
        self.assertGreaterEqual(driver.close_calls, 1)
        self.assertGreaterEqual(socket.close_calls, 1)
        self.assertNotIn("raw routing", repr(raised.exception))

    def test_close_before_start_cancels_and_quiesces_both_legs(self) -> None:
        _, driver, socket, arguments = _inputs()
        endpoint = composition.PcEndpointComposition(_config())
        endpoint.open(**arguments)

        endpoint.close()

        self.assertEqual(endpoint.audit()["state"], "closed")
        self.assertTrue(endpoint.audit()["both_legs_quiesced"])
        self.assertGreaterEqual(driver.cancel_read_calls, 1)
        self.assertGreaterEqual(socket.cancel_calls, 1)
        with self.assertRaises(composition.PcEndpointStateError):
            endpoint.start()

    def test_open_and_start_are_single_use_and_rejected_socket_is_closed(self) -> None:
        frame_count = 2
        uplink = _wire_frames("uplink", frame_count)
        downlink = _wire_frames("downlink", frame_count)
        driver = _FakeSerialDriver(
            port="CALL020L-EXACT-FAKE-PORT", incoming=uplink
        )
        socket = _FakeTlsSocket(
            connection_id="call020l-single-use-tls", incoming=downlink
        )
        _, _, _, arguments = _inputs(
            serial_driver=driver,
            tls_socket=socket,
            tls_connection_id=socket.connection_id,
        )
        endpoint = composition.PcEndpointComposition(_config())
        endpoint.open(**arguments)
        second_socket = _FakeTlsSocket(connection_id="call020l-second-socket")
        second_arguments = dict(arguments)
        second_arguments.update(
            tls_socket=second_socket,
            tls_attestation=_attestation(second_socket.connection_id),
            authentication_decision=_decision(second_socket.connection_id),
        )
        with self.assertRaises(composition.PcEndpointStateError):
            endpoint.open(**second_arguments)
        self.assertEqual((second_socket.cancel_calls, second_socket.close_calls), (1, 1))

        endpoint.start()
        with self.assertRaises(composition.PcEndpointStateError):
            endpoint.start()
        _zero(uplink)
        _zero(downlink)

    def test_external_cancel_interrupts_run_and_close_waits_for_quiescence(self) -> None:
        driver = _FakeSerialDriver(
            port="CALL020L-EXACT-FAKE-PORT", block_reads=True
        )
        socket = _FakeTlsSocket(
            connection_id="call020l-cancel-tls", block_reads=True
        )
        _, _, _, arguments = _inputs(
            serial_driver=driver,
            tls_socket=socket,
            tls_connection_id=socket.connection_id,
        )
        endpoint = composition.PcEndpointComposition(_config())
        endpoint.open(**arguments)
        failures: list[Exception] = []

        def run() -> None:
            try:
                endpoint.start()
            except Exception as error:
                failures.append(error)

        thread = threading.Thread(target=run)
        thread.start()
        self.assertTrue(driver.read_entered.wait(1.0))
        self.assertTrue(socket.recv_entered.wait(1.0))

        endpoint.request_cancel()
        endpoint.close()
        thread.join(1.0)

        self.assertFalse(thread.is_alive())
        self.assertEqual(len(failures), 1)
        self.assertIsInstance(failures[0], composition.PcEndpointRunFailed)
        self.assertGreaterEqual(driver.close_calls, 1)
        self.assertGreaterEqual(socket.close_calls, 1)
        self.assertEqual(endpoint.audit()["state"], "closed")
        self.assertTrue(endpoint.audit()["transport_references_cleared"])

    def test_runtime_leg_failure_closes_other_leg_and_redacts_failure(self) -> None:
        uplink = _wire_frames("uplink", 2)
        driver = _FakeSerialDriver(
            port="CALL020L-EXACT-FAKE-PORT", incoming=uplink
        )
        socket = _FakeTlsSocket(connection_id="call020l-runtime-failure")
        _, _, _, arguments = _inputs(
            serial_driver=driver,
            tls_socket=socket,
            tls_connection_id=socket.connection_id,
        )
        endpoint = composition.PcEndpointComposition(_config())
        endpoint.open(**arguments)

        with self.assertRaises(composition.PcEndpointRunFailed) as raised:
            endpoint.start()

        self.assertIsNone(raised.exception.__cause__)
        self.assertFalse(_contains_binary(raised.exception.metadata))
        self.assertGreaterEqual(driver.close_calls, 1)
        self.assertGreaterEqual(socket.close_calls, 1)
        self.assertFalse(raised.exception.metadata["reported_connected"])
        _zero(uplink)

    def test_bounds_reject_unusable_serial_or_tls_wire_capacity(self) -> None:
        config = _config()
        cases = (
            replace(
                config,
                serial=replace(config.serial, max_io_bytes=serial_adapter.MAX_WIRE_BYTES - 1),
            ),
            replace(
                config,
                tls=replace(config.tls, max_transfer_bytes=serial_adapter.MAX_WIRE_BYTES - 1),
            ),
            replace(
                config,
                serial=replace(config.serial, read_timeout_ms=10),
            ),
        )
        for invalid in cases:
            with self.subTest(serial=invalid.serial, tls=invalid.tls):
                with self.assertRaises(composition.PcEndpointCompositionError):
                    composition.PcEndpointComposition(invalid)

    def test_result_audit_and_errors_are_metadata_only_and_redacted(self) -> None:
        endpoint = composition.PcEndpointComposition(_config(enabled=False))
        _, _, socket, arguments = _inputs()
        with self.assertRaises(composition.PcEndpointOpenError) as raised:
            endpoint.open(**arguments)
        values = (endpoint.audit(), raised.exception.metadata)
        serialized = json.dumps(values, sort_keys=True, allow_nan=False)
        self.assertFalse(_contains_binary(values))
        for secret in (
            IDENTITY.session_id,
            IDENTITY.device_id,
            IDENTITY.guardian_id,
            IDENTITY.uplink_clock_id,
            IDENTITY.downlink_clock_id,
            socket.connection_id,
            "CALL020L-EXACT-FAKE-PORT",
        ):
            self.assertNotIn(secret, serialized)

    def test_module_has_no_autorun_discovery_socket_creation_logging_or_storage(self) -> None:
        source = Path(
            "pc_simulator/ego_call_pc_endpoint_composition.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("def main(", source)
        self.assertNotIn("if __name__", source)
        self.assertNotIn("import socket", source)
        self.assertNotIn("import ssl", source)
        self.assertNotIn("create_connection", source)
        self.assertNotIn("getaddrinfo", source)
        self.assertNotIn("list_ports", source)
        self.assertNotIn("logging", source)
        self.assertNotIn("Path.write", source)
        self.assertIn("enabled: bool = False", source)
        self.assertIn("ConcurrentDuplexMediaBridge", source)
        self.assertIn("separate_unimplemented_no_in_band_control", source)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import struct
import threading
import time
import unittest
import zlib
from pathlib import Path
from typing import Any, Callable

from pc_simulator import ego_call_authenticated_relay as relay
from pc_simulator import ego_call_operator_control as control
from pc_simulator import ego_call_single_usb_phase_connector as phase
from pc_simulator import ego_call_tls_stream_adapter as tls
from pc_simulator.ego_call_os_serial_wrapper import (
    DriverIoTimeout,
    ExplicitOsSerialConfig,
    ExplicitOsSerialConnection,
    OsSerialConnectionRegistry,
)


RUN_ID = "call020p-offline-run-001"
PORT = "CALL020P-EXACT-FAKE-PORT"
TOKEN = b"call020p-one-shot-operator-token"


def _command(action: str, *, timeout_ms: int = 1_000) -> control.ControlCommand:
    return control.ControlCommand(
        run_id=RUN_ID,
        operation_id=f"{RUN_ID}:{action}:1",
        action=action,
        timeout_ms=timeout_ms,
    )


def _telemetry(phase_name: str) -> dict[str, Any]:
    workers: list[list[object]] = []
    if phase_name == "post_stop":
        workers = [
            ["audio_capture", 1_024],
            ["usb_uplink", 1_100],
            ["usb_downlink", 1_080],
            ["audio_output", 1_040],
        ]
    return {
        "phase": phase_name,
        "captured_at_monotonic_ns": 1,
        "free_internal_heap_bytes": 96_000,
        "minimum_free_internal_heap_bytes": 90_000,
        "worker_stack_high_watermark_bytes": workers,
        "externally_attested_runtime_measurement": True,
    }


class _ControlResponder:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.actions: list[str] = []
        self.drop_first: set[str] = set()
        self.corrupt_crc_for: set[str] = set()
        self.wrong_operation_for: set[str] = set()
        self.force_duplicate_first_for: set[str] = set()
        self.block_action: str | None = None
        self.block_entered = threading.Event()
        self.block_release = threading.Event()

    def __call__(self, frame: bytes) -> bytes | None:
        message, request = phase.decode_control_frame(frame)
        action = request["action"]
        self.actions.append(action)
        self.counts[action] = self.counts.get(action, 0) + 1
        if message != f"{action}_request":
            raise AssertionError("request type/action mismatch")
        if self.block_action == action:
            self.block_entered.set()
            if not self.block_release.wait(1.0):
                raise AssertionError("offline response fixture was not released")
        if action in self.drop_first and self.counts[action] == 1:
            return None
        duplicate = (
            self.counts[action] > 1
            or action in self.force_duplicate_first_for
        )
        operation_id = request["operation_id"]
        if action in self.wrong_operation_for:
            operation_id = "wrong-operation-id"
        if action == "prepare":
            payload = {
                "run_id": request["run_id"],
                "operation_id": operation_id,
                "runner_version": control.WEARABLE_RUNNER_VERSION,
                "runner_api_version": control.WEARABLE_RUNNER_API_VERSION,
                "state": "PREPARED",
                "session_id": "call020p-session-private",
                "device_id": "call020p-device-private",
                "guardian_id": "call020p-guardian-private",
                "uplink_clock_id": "call020p-uplink-clock-private",
                "downlink_clock_id": "call020p-downlink-clock-private",
                "nonce_bits": 128,
                "correlated_routing_ids": True,
                "random_quality": "unverified",
                "provenance": "runtime_ephemeral_generated",
                "pre_start_telemetry": _telemetry("pre_start"),
                "duplicate": duplicate,
            }
        elif action == "telemetry":
            payload = {
                "run_id": request["run_id"],
                "operation_id": operation_id,
                "action": action,
                "accepted": True,
                "duplicate": duplicate,
                "snapshot": _telemetry("post_stop"),
            }
        else:
            states = {
                "start": "RUNNING",
                "cancel": "STOPPING",
                "join": "JOINED",
                "close": "CLOSED",
            }
            payload = {
                "run_id": request["run_id"],
                "operation_id": operation_id,
                "action": action,
                "accepted": True,
                "state": states[action],
                "duplicate": duplicate,
            }
        response = bytearray(phase.encode_control_frame(f"{action}_ack", payload))
        if action in self.corrupt_crc_for:
            response[-1] ^= 0x80
        return bytes(response)


class _FakeOpenedDriver:
    def __init__(
        self,
        responder: Callable[[bytes], bytes | None],
        *,
        port: str = PORT,
        read_chunk: int = 4_096,
        write_chunk: int = 4_096,
        close_failures: int = 0,
        close_leaves_open: int = 0,
        initial_rx: bytes = b"",
    ) -> None:
        self.port = port
        self.baudrate = 115_200
        self.timeout: float | None = 0.02
        self.write_timeout: float | None = 0.02
        self.exclusive: bool | None = True
        self.is_open = True
        self.responder = responder
        self.read_chunk = read_chunk
        self.write_chunk = write_chunk
        self.close_failures = close_failures
        self.close_leaves_open = close_leaves_open
        self.request_buffer = bytearray()
        self.response_buffer = bytearray(initial_rx)
        self.complete_requests: list[bytes] = []
        self.read_actions: list[object] = []
        self.write_actions: list[object] = []
        self.cancel_read_calls = 0
        self.cancel_write_calls = 0
        self.close_calls = 0
        self.read_calls = 0
        self.write_calls = 0
        self._lock = threading.Lock()

    def _queue_complete_requests(self) -> None:
        while len(self.request_buffer) >= phase.CONTROL_HEADER.size:
            _, _, _, payload_length = phase.CONTROL_HEADER.unpack_from(
                self.request_buffer
            )
            frame_length = (
                phase.CONTROL_HEADER.size + payload_length + phase.CONTROL_CRC.size
            )
            if len(self.request_buffer) < frame_length:
                return
            frame = bytes(self.request_buffer[:frame_length])
            del self.request_buffer[:frame_length]
            self.complete_requests.append(frame)
            response = self.responder(frame)
            if response is not None:
                self.response_buffer.extend(response)

    def readinto(self, target: memoryview) -> int:
        with self._lock:
            self.read_calls += 1
            if self.read_actions:
                action = self.read_actions.pop(0)
                if isinstance(action, BaseException):
                    raise action
                limit = int(action)
            else:
                limit = self.read_chunk
            if not self.response_buffer:
                return 0
            count = min(len(target), len(self.response_buffer), limit)
            target[:count] = self.response_buffer[:count]
            del self.response_buffer[:count]
            return count

    def write(self, source: memoryview) -> int:
        with self._lock:
            self.write_calls += 1
            if self.write_actions:
                action = self.write_actions.pop(0)
                if isinstance(action, BaseException):
                    raise action
                limit = int(action)
            else:
                limit = self.write_chunk
            count = min(len(source), limit)
            self.request_buffer.extend(source[:count])
            self._queue_complete_requests()
            return count

    def cancel_read(self) -> None:
        self.cancel_read_calls += 1

    def cancel_write(self) -> None:
        self.cancel_write_calls += 1

    def close(self) -> None:
        self.close_calls += 1
        if self.close_failures:
            self.close_failures -= 1
            raise OSError("offline injected close failure")
        if self.close_leaves_open:
            self.close_leaves_open -= 1
            return
        self.is_open = False


def _config(*, enabled: bool = True) -> phase.SingleUsbPhaseConfig:
    return phase.SingleUsbPhaseConfig(exact_port=PORT, enabled=enabled)


def _connector(
    *,
    enabled: bool = True,
    responder: _ControlResponder | None = None,
    driver: _FakeOpenedDriver | None = None,
) -> tuple[phase.SingleUsbPhaseConnector, _FakeOpenedDriver, _ControlResponder]:
    actual_responder = responder or _ControlResponder()
    actual_driver = driver or _FakeOpenedDriver(actual_responder)
    connector = phase.SingleUsbPhaseConnector(
        _config(enabled=enabled),
        opened_driver=actual_driver,
        registry=phase.SingleUsbLeaseRegistry(),
    )
    return connector, actual_driver, actual_responder


class _Verifier:
    def authorize_once(
        self,
        *,
        run_id: str,
        action: str,
        token: memoryview,
        timeout_ms: int,
    ) -> bool:
        return (
            run_id == RUN_ID
            and action == control.AUTHORIZATION_ACTION
            and bytes(token) == TOKEN
            and timeout_ms > 0
        )


class _StepClock:
    def __init__(self, *, step_ns: int) -> None:
        self.value = 0
        self.step_ns = step_ns

    def monotonic_ns(self) -> int:
        result = self.value
        self.value += self.step_ns
        return result


class _FakeTlsSocket:
    def __init__(self, connection_id: str) -> None:
        self.connection_id = connection_id
        self.cancel_calls = 0
        self.close_calls = 0

    def cancel_pending_io(self) -> None:
        self.cancel_calls += 1

    def close(self) -> None:
        self.close_calls += 1


class _FakeTlsConnector:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.socket: _FakeTlsSocket | None = None

    def open_verified(
        self, request: control.TlsOpenRequest
    ) -> control.VerifiedTlsOpenResult:
        self.events.append("tls")
        connection_id = "call020p-tls-private"
        self.socket = _FakeTlsSocket(connection_id)
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
            decision_id="call020p-auth-private",
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
        return control.VerifiedTlsOpenResult(
            tls_socket=self.socket,
            tls_attestation=attestation,
            authentication_decision=decision,
        )


class _LeaseEndpoint:
    instances: list["_LeaseEndpoint"] = []
    events: list[str] = []
    block = False
    fail_after_transfer = False

    def __init__(self, config: Any) -> None:
        self.config = config
        self.serial: ExplicitOsSerialConnection | None = None
        self.socket: _FakeTlsSocket | None = None
        self.cancelled = False
        self.started = threading.Event()
        self.cancel_event = threading.Event()
        self.__class__.instances.append(self)

    def open(self, **kwargs: Any) -> None:
        self.__class__.events.append("endpoint_open")
        self.socket = kwargs["tls_socket"]
        self.serial = ExplicitOsSerialConnection.open_explicit(
            self.config.serial,
            factory=kwargs["serial_factory"],
            registry=kwargs["serial_registry"],
        )
        if self.fail_after_transfer:
            raise RuntimeError("offline failure after media lease transfer")

    def request_cancel(self) -> None:
        self.cancelled = True
        self.cancel_event.set()
        if self.serial is not None:
            self.serial.cancel_pending_io()

    def _close_resources(self) -> None:
        serial, self.serial = self.serial, None
        if serial is not None:
            serial.close()
        socket, self.socket = self.socket, None
        if socket is not None:
            socket.cancel_pending_io()
            socket.close()

    def start(self) -> dict[str, Any]:
        self.started.set()
        if self.block:
            if not self.cancel_event.wait(1.0):
                raise RuntimeError("offline cancellation did not arrive")
            self._close_resources()
            raise RuntimeError("offline media cancelled")
        self._close_resources()
        counters = {
            "frames_expected": 2,
            "frames_received": 2,
            "frames_forwarded": 2,
            "receive_retry_count": 0,
            "send_retry_count": 0,
            "backpressure_drops": 0,
            "deadline_misses_before_send": 0,
            "deadline_misses_after_send": 0,
        }
        return {
            "result": "PASS",
            "direction_stats": {"uplink": dict(counters), "downlink": dict(counters)},
        }

    def close(self) -> None:
        self._close_resources()

    def audit(self) -> dict[str, Any]:
        return {"state": "offline_fake"}


class EgoCallSingleUsbPhaseConnectorTests(unittest.TestCase):
    def tearDown(self) -> None:
        _LeaseEndpoint.instances.clear()
        _LeaseEndpoint.events.clear()
        _LeaseEndpoint.block = False
        _LeaseEndpoint.fail_after_transfer = False

    def test_codec_round_trip_and_strict_crc_length_version_and_json(self) -> None:
        encoded = phase.encode_control_frame(
            "cancel_request",
            {"action": "cancel", "operation_id": "op-1", "run_id": RUN_ID, "timeout_ms": 10},
        )
        name, payload = phase.decode_control_frame(encoded)
        self.assertEqual(name, "cancel_request")
        self.assertEqual(payload["operation_id"], "op-1")

        corrupt = bytearray(encoded)
        corrupt[-1] ^= 1
        with self.assertRaises(phase.SingleUsbPhaseError):
            phase.decode_control_frame(corrupt)
        wrong_version = bytearray(encoded)
        wrong_version[4] = 2
        with self.assertRaises(phase.SingleUsbPhaseError):
            phase.decode_control_frame(wrong_version)
        with self.assertRaises(phase.SingleUsbPhaseError):
            phase.decode_control_frame(encoded + b"x")

        duplicate_json = b'{"a":1,"a":1}'
        header = phase.CONTROL_HEADER.pack(
            phase.CONTROL_MAGIC,
            phase.CONTROL_VERSION,
            phase.MESSAGE_TYPES["cancel_ack"],
            len(duplicate_json),
        )
        duplicate_frame = header + duplicate_json
        duplicate_frame += struct.pack(">I", zlib.crc32(duplicate_frame) & 0xFFFFFFFF)
        with self.assertRaises(phase.SingleUsbPhaseError):
            phase.decode_control_frame(duplicate_frame)
        with self.assertRaises(phase.SingleUsbPhaseError):
            phase.encode_control_frame("cancel_ack", {"value": "x" * 2_049})

    def test_default_off_is_inert_and_caller_keeps_unclaimed_driver(self) -> None:
        connector, driver, responder = _connector(enabled=False)
        with self.assertRaises(phase.SingleUsbPhaseBlocked) as raised:
            connector.prepare(_command("prepare"))
        self.assertEqual(raised.exception.reason_code, "single_usb_connector_disabled")
        self.assertEqual(responder.actions, [])
        self.assertEqual(driver.complete_requests, [])
        self.assertEqual(driver.close_calls, 0)
        snapshot = connector.phase_snapshot()
        self.assertEqual(snapshot["state"], "dormant")
        self.assertTrue(snapshot["unclaimed_driver_retained_for_caller"])
        self.assertFalse(snapshot["driver_reference_held_by_phase_owner"])
        self.assertTrue(connector.abort_before_media_transfer())
        self.assertTrue(driver.is_open)

    def test_prepare_drains_bounded_rom_text_before_first_control_write(self) -> None:
        responder = _ControlResponder()
        boot_prefix = b"ESP-ROM:esp32s3\r\nboot:0x8\r\n"
        driver = _FakeOpenedDriver(
            responder,
            initial_rx=boot_prefix,
            read_chunk=64,
        )
        connector, _, _ = _connector(responder=responder, driver=driver)

        prepared = connector.prepare(_command("prepare"))

        self.assertEqual(prepared.state, "PREPARED")
        self.assertEqual(responder.actions, ["prepare"])
        audit = connector.audit()
        self.assertTrue(audit["pre_control_drain_completed"])
        self.assertEqual(audit["pre_control_drain_bytes"], len(boot_prefix))
        self.assertTrue(audit["pre_control_drain_zero_progress_quiescence"])
        self.assertGreaterEqual(audit["pre_control_drain_calls"], 2)
        self.assertTrue(connector.abort_before_media_transfer())

    def test_ambiguous_or_disallowed_boot_rx_blocks_before_write(self) -> None:
        for label, initial_rx in (
            ("fragmented-full", b"ROM\r\nEGLC"),
            ("trailing-partial", b"ROM\r\nEGL"),
            ("binary", b"ROM\x00"),
        ):
            with self.subTest(label=label):
                responder = _ControlResponder()
                driver = _FakeOpenedDriver(
                    responder,
                    initial_rx=initial_rx,
                    read_chunk=1,
                )
                connector, _, _ = _connector(responder=responder, driver=driver)

                with self.assertRaises(phase.SingleUsbPhaseBlocked) as raised:
                    connector.prepare(_command("prepare"))

                self.assertEqual(
                    raised.exception.reason_code, "pre_control_rx_not_quiescent"
                )
                self.assertEqual(driver.write_calls, 0)
                self.assertEqual(driver.complete_requests, [])
                self.assertEqual(connector.phase_snapshot()["state"], "FAILED")
                self.assertTrue(connector.abort_before_media_transfer())

    def test_pre_control_drain_byte_and_call_bounds_block_before_write(self) -> None:
        cases = (
            (
                "bytes",
                phase.SingleUsbPhaseConfig(
                    exact_port=PORT,
                    enabled=True,
                    pre_control_drain_max_bytes=8,
                ),
                _FakeOpenedDriver(_ControlResponder(), initial_rx=b"123456789"),
            ),
            (
                "calls",
                phase.SingleUsbPhaseConfig(
                    exact_port=PORT,
                    enabled=True,
                    pre_control_drain_max_calls=2,
                ),
                _FakeOpenedDriver(
                    _ControlResponder(),
                    initial_rx=b"startup",
                    read_chunk=1,
                ),
            ),
        )
        for label, config, driver in cases:
            with self.subTest(label=label):
                connector = phase.SingleUsbPhaseConnector(
                    config,
                    opened_driver=driver,
                    registry=phase.SingleUsbLeaseRegistry(),
                )
                with self.assertRaises(phase.SingleUsbPhaseBlocked):
                    connector.prepare(_command("prepare"))
                self.assertEqual(driver.write_calls, 0)
                self.assertFalse(connector.audit()["pre_control_drain_completed"])
                self.assertTrue(connector.abort_before_media_transfer())

    def test_zero_progress_timeout_is_quiet_but_unknown_or_partial_is_not(self) -> None:
        responder = _ControlResponder()
        quiet_driver = _FakeOpenedDriver(responder)
        quiet_driver.read_actions = [DriverIoTimeout("quiet", progress=0)]
        quiet, _, _ = _connector(responder=responder, driver=quiet_driver)
        self.assertEqual(quiet.prepare(_command("prepare")).state, "PREPARED")
        self.assertTrue(quiet.audit()["pre_control_drain_completed"])
        self.assertTrue(quiet.abort_before_media_transfer())

        for label, progress in (("unknown", None), ("partial", 1)):
            with self.subTest(label=label):
                blocked_responder = _ControlResponder()
                driver = _FakeOpenedDriver(blocked_responder)
                driver.read_actions = [
                    DriverIoTimeout("not quiet", progress=progress)
                ]
                connector, _, _ = _connector(
                    responder=blocked_responder, driver=driver
                )
                with self.assertRaises(phase.SingleUsbPhaseBlocked):
                    connector.prepare(_command("prepare"))
                self.assertEqual(driver.write_calls, 0)
                self.assertFalse(connector.audit()["pre_control_drain_completed"])
                self.assertTrue(connector.abort_before_media_transfer())

    def test_pre_control_total_deadline_exhausts_before_read_or_write(self) -> None:
        responder = _ControlResponder()
        driver = _FakeOpenedDriver(responder, initial_rx=b"ROM\r\n")
        connector = phase.SingleUsbPhaseConnector(
            phase.SingleUsbPhaseConfig(
                exact_port=PORT,
                enabled=True,
                pre_control_drain_timeout_ms=1,
            ),
            opened_driver=driver,
            registry=phase.SingleUsbLeaseRegistry(),
            clock=_StepClock(step_ns=2_000_000),
        )

        with self.assertRaises(phase.SingleUsbPhaseBlocked):
            connector.prepare(_command("prepare"))

        self.assertEqual(driver.read_calls, 0)
        self.assertEqual(driver.write_calls, 0)
        self.assertFalse(connector.audit()["pre_control_drain_completed"])
        self.assertTrue(connector.abort_before_media_transfer())

    def test_fragmented_control_lifecycle_uses_stable_operations(self) -> None:
        responder = _ControlResponder()
        driver = _FakeOpenedDriver(responder, read_chunk=37, write_chunk=31)
        connector, _, _ = _connector(responder=responder, driver=driver)

        prepared = connector.prepare(_command("prepare"))
        self.assertEqual(prepared.state, "PREPARED")
        self.assertIs(connector.prepare(_command("prepare")), prepared)
        connector.cancel(_command("cancel"))
        connector.join(_command("join"))
        closed = connector.close(_command("close"))

        self.assertEqual(closed.state, "CLOSED")
        self.assertEqual(responder.actions, ["prepare", "cancel", "join", "close"])
        self.assertEqual(driver.close_calls, 1)
        self.assertFalse(driver.is_open)
        audit = connector.audit()
        self.assertEqual(audit["state"], "LOCAL_CLOSED")
        self.assertTrue(audit["remote_cleanup_acknowledged"])
        self.assertFalse(audit["raw_audio_logged_or_persisted"])

    def test_lost_prepare_ack_retries_same_id_and_requires_duplicate_ack(self) -> None:
        responder = _ControlResponder()
        responder.drop_first.add("prepare")
        connector, driver, _ = _connector(responder=responder)
        command = _command("prepare")

        with self.assertRaises(phase.SingleUsbPhaseBlocked) as first:
            connector.prepare(command)
        self.assertEqual(first.exception.reason_code, "control_zero_progress_timeout")
        prepared = connector.prepare(command)

        self.assertTrue(prepared.duplicate)
        self.assertEqual(responder.counts["prepare"], 2)
        self.assertEqual(connector.audit()["pre_control_drain_calls"], 1)
        self.assertTrue(connector.abort_before_media_transfer())
        self.assertFalse(driver.is_open)

    def test_lost_cleanup_ack_retries_with_duplicate_proof(self) -> None:
        responder = _ControlResponder()
        responder.drop_first.add("cancel")
        connector, driver, _ = _connector(responder=responder)
        connector.prepare(_command("prepare"))
        command = _command("cancel")
        with self.assertRaises(phase.SingleUsbPhaseBlocked):
            connector.cancel(command)
        acknowledgement = connector.cancel(command)
        self.assertTrue(acknowledgement.duplicate)
        connector.join(_command("join"))
        connector.close(_command("close"))
        self.assertEqual(responder.counts["cancel"], 2)
        self.assertFalse(driver.is_open)

    def test_start_ack_loss_is_uncertain_and_forbids_any_more_control(self) -> None:
        responder = _ControlResponder()
        responder.drop_first.add("start")
        connector, driver, _ = _connector(responder=responder)
        connector.prepare(_command("prepare"))

        with self.assertRaises(phase.SingleUsbPhaseBlocked):
            connector.start(_command("start"))
        writes_after_start = len(driver.complete_requests)
        self.assertEqual(connector.phase_snapshot()["state"], "START_UNCERTAIN")
        with self.assertRaises(phase.SingleUsbPhaseBlocked):
            connector.cancel(_command("cancel"))
        self.assertEqual(len(driver.complete_requests), writes_after_start)
        self.assertTrue(connector.abort_before_media_transfer())
        self.assertFalse(driver.is_open)

    def test_handoff_preserves_handle_and_media_close_only_returns_it(self) -> None:
        connector, driver, responder = _connector()
        connector.prepare(_command("prepare"))
        connector.start(_command("start"))
        with self.assertRaises(phase.SingleUsbPhaseBlocked):
            connector.open_explicit(
                port_name="CALL020P-WRONG-EXACT-PORT",
                baudrate=115_200,
                read_timeout_ms=20,
                write_timeout_ms=20,
                exclusive=True,
            )
        self.assertEqual(connector.phase_snapshot()["state"], "HANDOFF_READY")
        serial = ExplicitOsSerialConnection.open_explicit(
            ExplicitOsSerialConfig(
                port_name=PORT,
                connection_id="call020p-media-private",
                enabled=True,
            ),
            factory=connector,
            registry=OsSerialConnectionRegistry(),
        )
        self.assertEqual(connector.phase_snapshot()["state"], "MEDIA_TRANSFERRED")
        writes_at_transfer = len(driver.complete_requests)
        with self.assertRaises(phase.SingleUsbPhaseBlocked):
            connector.cancel(_command("cancel"))
        self.assertEqual(len(driver.complete_requests), writes_at_transfer)

        serial.close()
        self.assertEqual(connector.phase_snapshot()["state"], "MEDIA_RETURNED")
        self.assertEqual(driver.close_calls, 0)
        self.assertTrue(driver.is_open)
        self.assertTrue(connector.close_returned_handle())
        self.assertEqual(driver.close_calls, 1)
        self.assertFalse(driver.is_open)
        self.assertEqual(responder.actions, ["prepare", "start"])

    def test_start_and_factory_race_is_serialized_after_complete_ack(self) -> None:
        responder = _ControlResponder()
        responder.block_action = "start"
        connector, driver, _ = _connector(responder=responder)
        connector.prepare(_command("prepare"))
        errors: list[Exception] = []
        borrowed: list[object] = []

        def start() -> None:
            try:
                connector.start(_command("start"))
            except Exception as error:
                errors.append(error)

        def transfer() -> None:
            try:
                borrowed.append(
                    connector.open_explicit(
                        port_name=PORT,
                        baudrate=115_200,
                        read_timeout_ms=20,
                        write_timeout_ms=20,
                        exclusive=True,
                    )
                )
            except Exception as error:
                errors.append(error)

        start_thread = threading.Thread(target=start)
        start_thread.start()
        self.assertTrue(responder.block_entered.wait(1.0))
        transfer_thread = threading.Thread(target=transfer)
        transfer_thread.start()
        time.sleep(0.01)
        self.assertTrue(transfer_thread.is_alive())
        responder.block_release.set()
        start_thread.join(1.0)
        transfer_thread.join(1.0)

        self.assertEqual(errors, [])
        self.assertEqual(len(borrowed), 1)
        borrowed[0].close()  # type: ignore[attr-defined]
        self.assertTrue(connector.close_returned_handle())
        self.assertFalse(driver.is_open)

    def test_facade_return_and_quiescent_recovery_race_has_one_lock_order(self) -> None:
        connector, driver, _ = _connector()
        connector.prepare(_command("prepare"))
        connector.start(_command("start"))
        borrowed = connector.open_explicit(
            port_name=PORT,
            baudrate=115_200,
            read_timeout_ms=20,
            write_timeout_ms=20,
            exclusive=True,
        )
        barrier = threading.Barrier(3)
        errors: list[Exception] = []

        def ordinary_return() -> None:
            try:
                barrier.wait()
                borrowed.close()
            except Exception as error:
                errors.append(error)

        def recovery_return() -> None:
            try:
                barrier.wait()
                connector.recover_media_return_after_quiescence()
            except Exception as error:
                errors.append(error)

        ordinary = threading.Thread(target=ordinary_return)
        recovery = threading.Thread(target=recovery_return)
        ordinary.start()
        recovery.start()
        barrier.wait()
        ordinary.join(1.0)
        recovery.join(1.0)

        self.assertFalse(ordinary.is_alive())
        self.assertFalse(recovery.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(connector.phase_snapshot()["state"], "MEDIA_RETURNED")
        self.assertTrue(connector.close_returned_handle())
        self.assertFalse(driver.is_open)

    def test_partial_progress_and_bad_identity_are_terminal_but_locally_cleanable(self) -> None:
        responder = _ControlResponder()
        driver = _FakeOpenedDriver(responder)
        driver.write_actions = [3, DriverIoTimeout("partial", progress=1)]
        connector, _, _ = _connector(responder=responder, driver=driver)
        with self.assertRaises(phase.SingleUsbPhaseBlocked) as partial:
            connector.prepare(_command("prepare"))
        self.assertEqual(partial.exception.reason_code, "control_partial_or_unknown_progress")
        self.assertEqual(connector.phase_snapshot()["state"], "FAILED")
        self.assertTrue(connector.abort_before_media_transfer())

        bad_responder = _ControlResponder()
        bad_responder.wrong_operation_for.add("prepare")
        bad, bad_driver, _ = _connector(responder=bad_responder)
        with self.assertRaises(phase.SingleUsbPhaseBlocked) as identity:
            bad.prepare(_command("prepare"))
        self.assertEqual(identity.exception.reason_code, "prepare_acknowledgement_rejected")
        self.assertEqual(bad.phase_snapshot()["state"], "FAILED")
        self.assertTrue(bad.abort_before_media_transfer())
        self.assertFalse(bad_driver.is_open)

    def test_header_consumed_then_body_timeout_is_partial_not_retryable(self) -> None:
        responder = _ControlResponder()
        driver = _FakeOpenedDriver(responder)
        driver.read_actions = [0, phase.CONTROL_HEADER.size, 0]
        connector, _, _ = _connector(responder=responder, driver=driver)
        with self.assertRaises(phase.SingleUsbPhaseBlocked) as raised:
            connector.prepare(_command("prepare"))
        self.assertEqual(
            raised.exception.reason_code, "control_partial_or_unknown_progress"
        )
        self.assertEqual(connector.phase_snapshot()["state"], "FAILED")
        self.assertTrue(connector.abort_before_media_transfer())

    def test_same_operation_id_with_changed_timeout_is_rejected(self) -> None:
        connector, driver, _ = _connector()
        connector.prepare(_command("prepare", timeout_ms=1_000))
        with self.assertRaises(phase.SingleUsbPhaseBlocked) as raised:
            connector.prepare(_command("prepare", timeout_ms=999))
        self.assertEqual(raised.exception.reason_code, "control_operation_identity_reused")
        self.assertTrue(connector.abort_before_media_transfer())
        self.assertFalse(driver.is_open)

    def test_conflicting_operation_id_cannot_poison_active_media_lease(self) -> None:
        connector, driver, _ = _connector()
        connector.prepare(_command("prepare"))
        connector.start(_command("start"))
        borrowed = connector.open_explicit(
            port_name=PORT,
            baudrate=115_200,
            read_timeout_ms=20,
            write_timeout_ms=20,
            exclusive=True,
        )
        conflicting = control.ControlCommand(
            run_id=RUN_ID,
            operation_id=_command("prepare").operation_id,
            action="cancel",
            timeout_ms=1_000,
        )
        with self.assertRaises(phase.SingleUsbPhaseBlocked):
            connector.cancel(conflicting)
        self.assertEqual(connector.phase_snapshot()["state"], "MEDIA_TRANSFERRED")

        borrowed.close()
        self.assertEqual(connector.phase_snapshot()["state"], "MEDIA_RETURNED")
        self.assertTrue(connector.close_returned_handle())
        self.assertFalse(driver.is_open)

    def test_close_requires_observed_closed_driver_and_retries_same_resource(self) -> None:
        responder = _ControlResponder()
        driver = _FakeOpenedDriver(responder, close_leaves_open=1)
        connector, _, _ = _connector(responder=responder, driver=driver)
        connector.prepare(_command("prepare"))
        connector.cancel(_command("cancel"))
        connector.join(_command("join"))
        with self.assertRaises(phase.SingleUsbPhaseBlocked):
            connector.close(_command("close"))
        self.assertTrue(driver.is_open)
        self.assertEqual(
            connector.phase_snapshot()["state"],
            "REMOTE_CLOSED_LOCAL_CLOSING",
        )

        connector.close(_command("close"))
        self.assertFalse(driver.is_open)
        self.assertEqual(driver.close_calls, 2)
        self.assertEqual(responder.counts["close"], 1)

    def test_unexpected_duplicate_on_first_response_fails_closed(self) -> None:
        responder = _ControlResponder()
        responder.force_duplicate_first_for.add("prepare")
        connector, driver, _ = _connector(responder=responder)
        with self.assertRaises(phase.SingleUsbPhaseBlocked):
            connector.prepare(_command("prepare"))
        self.assertEqual(connector.phase_snapshot()["state"], "FAILED")
        self.assertTrue(connector.abort_before_media_transfer())
        self.assertFalse(driver.is_open)

    def test_permanently_unconfirmed_physical_close_never_reports_local_closed(self) -> None:
        responder = _ControlResponder()
        driver = _FakeOpenedDriver(responder, close_leaves_open=10)
        connector, _, _ = _connector(responder=responder, driver=driver)
        connector.prepare(_command("prepare"))
        connector.cancel(_command("cancel"))
        connector.join(_command("join"))

        for _ in range(2):
            with self.assertRaises(phase.SingleUsbPhaseBlocked):
                connector.close(_command("close"))
            snapshot = connector.phase_snapshot()
            self.assertEqual(snapshot["state"], "REMOTE_CLOSED_LOCAL_CLOSING")
            self.assertFalse(snapshot["physical_close_confirmed"])
            self.assertTrue(driver.is_open)
        self.assertEqual(responder.counts["close"], 1)

    def test_bad_crc_never_resynchronizes_or_sends_followup_control(self) -> None:
        responder = _ControlResponder()
        responder.corrupt_crc_for.add("prepare")
        connector, driver, _ = _connector(responder=responder)
        with self.assertRaises(phase.SingleUsbPhaseBlocked):
            connector.prepare(_command("prepare"))
        writes = len(driver.complete_requests)
        self.assertEqual(connector.phase_snapshot()["state"], "FAILED")
        with self.assertRaises(phase.SingleUsbPhaseBlocked):
            connector.cancel(_command("cancel"))
        self.assertEqual(len(driver.complete_requests), writes)
        self.assertTrue(connector.abort_before_media_transfer())

    def test_m_orders_control_tls_handoff_media_and_never_fakes_result(self) -> None:
        events: list[str] = []
        responder = _ControlResponder()

        def recorded(frame: bytes) -> bytes | None:
            _, payload = phase.decode_control_frame(frame)
            events.append(payload["action"])
            return responder(frame)

        driver = _FakeOpenedDriver(recorded)
        connector = phase.SingleUsbPhaseConnector(
            _config(),
            opened_driver=driver,
            registry=phase.SingleUsbLeaseRegistry(),
        )
        tls_connector = _FakeTlsConnector(events)
        host = control.HostControlSession(
            control.HostControlConfig(
                run_id=RUN_ID,
                exact_port=PORT,
                enabled=True,
                plan_only=False,
                frame_count=2,
                max_runtime_ms=1_000,
            ),
            run_registry=control.RunIdentityRegistry(),
            endpoint_factory=_LeaseEndpoint,
        )
        authorization_bytes = bytearray(TOKEN)
        authorization = control.OneShotOperatorAuthorization(
            run_id=RUN_ID,
            token=authorization_bytes,
            operator_authorized=True,
            expires_at_monotonic_ns=time.monotonic_ns() + 5_000_000_000,
        )
        host.prepare(authorization=authorization, verifier=_Verifier())
        host.preflight(
            wearable_control=connector,
            wearable_attestation=control.WearableControlAttestation(
                runner_version=control.WEARABLE_RUNNER_VERSION,
                runner_api_version=control.WEARABLE_RUNNER_API_VERSION,
                externally_attested=True,
                exact_prepare_start_cancel_join_close=True,
                out_of_band_from_media=False,
                finite_timeout_contract=True,
                runtime_telemetry_supported=True,
                max_operation_timeout_ms=1_000,
                logically_separate_and_not_interleaved_with_media=True,
            ),
            tls_connector=tls_connector,
            tls_connector_attestation=control.TlsConnectorAttestation(
                externally_attested=True,
                returns_connected_socket_only=True,
                verifies_chain_and_peer_identity=True,
                exact_session_binding=True,
                finite_timeout_contract=True,
                cleans_partial_open_before_raise=True,
                no_credential_or_media_result=True,
            ),
            serial_factory=connector,
        )
        _LeaseEndpoint.events = events
        opened = host.open()
        self.assertEqual(events, ["prepare", "tls", "start", "endpoint_open"])
        self.assertTrue(opened["same_handle_media_transfer_confirmed"])
        host.start()
        for _ in range(100):
            if host.audit()["media_thread_done"]:
                break
            time.sleep(0.005)
        stopped = host.stop()
        closed = host.close()

        self.assertEqual(responder.actions, ["prepare", "start"])
        self.assertEqual(stopped["same_handle_optional_result_phase"], "DISABLED_NOT_RUN")
        self.assertTrue(closed["same_handle_local_handle_cleanup_confirmed"])
        self.assertFalse(closed["same_handle_remote_cleanup_acknowledged"])
        self.assertFalse(closed["same_handle_device_runtime_termination_proven"])
        self.assertEqual(closed["state"], "closed")
        self.assertEqual(closed["p0_call"], "NOT_RUN")
        self.assertFalse(driver.is_open)

    def test_m_early_stop_cleans_only_local_media_without_post_start_control(self) -> None:
        _LeaseEndpoint.block = True
        host, connector, driver, responder = self._make_host_with_phase_connector()
        host.open()
        host.start()
        endpoint = _LeaseEndpoint.instances[-1]
        self.assertTrue(endpoint.started.wait(1.0))

        stopped = host.stop()
        closed = host.close()

        self.assertEqual(responder.actions, ["prepare", "start"])
        self.assertEqual(stopped["media_termination_reason"], "operator_stop_requested")
        self.assertFalse(stopped["same_handle_device_runtime_termination_proven"])
        self.assertFalse(closed["same_handle_remote_cleanup_acknowledged"])
        self.assertTrue(closed["same_handle_local_handle_cleanup_confirmed"])
        self.assertFalse(driver.is_open)
        self.assertEqual(connector.phase_snapshot()["result_phase"], "DISABLED_NOT_RUN")

    def test_m_failure_after_transfer_returns_then_closes_exact_local_handle(self) -> None:
        _LeaseEndpoint.fail_after_transfer = True
        host, connector, driver, responder = self._make_host_with_phase_connector()

        with self.assertRaises(control.HostControlBlocked) as raised:
            host.open()

        self.assertEqual(
            raised.exception.reason_code, "pc_endpoint_composition_open_failed"
        )
        self.assertEqual(responder.actions, ["prepare", "start"])
        self.assertFalse(driver.is_open)
        self.assertEqual(connector.phase_snapshot()["state"], "LOCAL_CLOSED")
        self.assertTrue(host.audit()["same_handle_local_handle_cleanup_confirmed"])
        self.assertEqual(host.close()["state"], "closed")

    def test_m_unclaimed_disabled_connector_does_not_claim_driver_cleanup(self) -> None:
        host, connector, driver, responder = self._make_host_with_phase_connector(
            phase_enabled=False
        )
        with self.assertRaises(control.HostControlBlocked) as raised:
            host.open()

        self.assertEqual(raised.exception.reason_code, "wearable_prepare_failed")
        failed = host.audit()
        self.assertTrue(
            failed["same_handle_lease_never_acquired_caller_retains_handle"]
        )
        self.assertFalse(failed["same_handle_local_handle_cleanup_confirmed"])
        self.assertTrue(driver.is_open)
        self.assertEqual(responder.actions, [])

        closed = host.close()
        self.assertEqual(closed["state"], "closed")
        self.assertTrue(
            closed["same_handle_lease_never_acquired_caller_retains_handle"]
        )
        self.assertFalse(closed["same_handle_local_handle_cleanup_confirmed"])
        self.assertTrue(driver.is_open)
        self.assertEqual(connector.phase_snapshot()["state"], "dormant")

    def _make_host_with_phase_connector(
        self,
        *,
        phase_enabled: bool = True,
    ) -> tuple[
        control.HostControlSession,
        phase.SingleUsbPhaseConnector,
        _FakeOpenedDriver,
        _ControlResponder,
    ]:
        events: list[str] = []
        responder = _ControlResponder()

        def recorded(frame: bytes) -> bytes | None:
            _, payload = phase.decode_control_frame(frame)
            events.append(payload["action"])
            return responder(frame)

        driver = _FakeOpenedDriver(recorded)
        connector = phase.SingleUsbPhaseConnector(
            _config(enabled=phase_enabled),
            opened_driver=driver,
            registry=phase.SingleUsbLeaseRegistry(),
        )
        tls_connector = _FakeTlsConnector(events)
        host = control.HostControlSession(
            control.HostControlConfig(
                run_id=RUN_ID,
                exact_port=PORT,
                enabled=True,
                plan_only=False,
                frame_count=2,
                max_runtime_ms=1_000,
            ),
            run_registry=control.RunIdentityRegistry(),
            endpoint_factory=_LeaseEndpoint,
        )
        authorization = control.OneShotOperatorAuthorization(
            run_id=RUN_ID,
            token=bytearray(TOKEN),
            operator_authorized=True,
            expires_at_monotonic_ns=time.monotonic_ns() + 5_000_000_000,
        )
        host.prepare(authorization=authorization, verifier=_Verifier())
        host.preflight(
            wearable_control=connector,
            wearable_attestation=control.WearableControlAttestation(
                runner_version=control.WEARABLE_RUNNER_VERSION,
                runner_api_version=control.WEARABLE_RUNNER_API_VERSION,
                externally_attested=True,
                exact_prepare_start_cancel_join_close=True,
                out_of_band_from_media=False,
                finite_timeout_contract=True,
                runtime_telemetry_supported=True,
                max_operation_timeout_ms=1_000,
                logically_separate_and_not_interleaved_with_media=True,
            ),
            tls_connector=tls_connector,
            tls_connector_attestation=control.TlsConnectorAttestation(
                externally_attested=True,
                returns_connected_socket_only=True,
                verifies_chain_and_peer_identity=True,
                exact_session_binding=True,
                finite_timeout_contract=True,
                cleans_partial_open_before_raise=True,
                no_credential_or_media_result=True,
            ),
            serial_factory=connector,
        )
        _LeaseEndpoint.events = events
        return host, connector, driver, responder

    def test_source_has_no_real_opener_discovery_cli_or_audio_persistence(self) -> None:
        source = Path(
            "pc_simulator/ego_call_single_usb_phase_connector.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "import serial",
            "list_ports",
            "socket.",
            "argparse",
            "wave.",
            "open_explicit=Lazy",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn("CRC is framing", source)


if __name__ == "__main__":
    unittest.main()

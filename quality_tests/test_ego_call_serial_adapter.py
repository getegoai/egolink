from __future__ import annotations

import json
import threading
import unittest
import zlib
from collections import deque
from dataclasses import replace
from pathlib import Path

from pc_simulator import ego_call_concurrent_bridge as concurrent
from pc_simulator import ego_call_media_io as media_io
from pc_simulator import ego_call_serial_adapter as serial_adapter


IDENTITY = media_io.EndpointIdentity(
    session_id="call020h-session",
    device_id="call020h-device",
    guardian_id="call020h-guardian",
    uplink_clock_id="call020h-device-clock",
    downlink_clock_id="call020h-guardian-clock",
)


def _wire(
    direction: str,
    sequence: int = 0,
    *,
    session_id: str | None = None,
    source_clock_id: str | None = None,
) -> bytearray:
    config = media_io.MediaIoConfig(
        identity=IDENTITY,
        frame_count=max(1, sequence + 1),
        max_cycles=max(1, sequence + 1),
    )
    frame = media_io._make_frame(config, direction, sequence)
    if session_id is not None:
        frame.session_id = session_id
    if source_clock_id is not None:
        frame.source_clock_id = source_clock_id
    try:
        return media_io.FrameCodec.encode(frame)
    finally:
        frame.dispose()


def _recrc(wire: bytearray) -> None:
    wire[-media_io._CRC.size :] = media_io._CRC.pack(
        zlib.crc32(memoryview(wire)[: -media_io._CRC.size]) & 0xFFFFFFFF
    )


class _FakeInjectedSerial:
    """Caller-owned in-memory double for the injected callback contract."""

    def __init__(
        self,
        incoming: bytearray | None = None,
        *,
        read_actions: list[int | Exception] | None = None,
        write_actions: list[int | Exception] | None = None,
    ) -> None:
        self.incoming = incoming or bytearray()
        self.incoming_offset = 0
        self.read_actions = deque(read_actions or [])
        self.write_actions = deque(write_actions or [])
        self.outgoing = bytearray()
        self.read_calls = 0
        self.write_calls = 0
        self.cancel_calls = 0
        self.read_timeout_values: list[int] = []
        self.write_timeout_values: list[int] = []
        self.retained_read_buffers: list[bytearray] = []
        self.retained_write_buffers: list[bytearray] = []
        self._read_lock = threading.Lock()
        self._write_lock = threading.Lock()

    def readinto(self, target: memoryview, *, timeout_ms: int) -> int:
        with self._read_lock:
            self.read_calls += 1
            self.read_timeout_values.append(timeout_ms)
            self.retained_read_buffers.append(target.obj)
            action = self.read_actions.popleft() if self.read_actions else len(target)
            if isinstance(action, Exception):
                raise action
            if action == 0:
                return 0
            available = len(self.incoming) - self.incoming_offset
            count = min(action, len(target), available)
            if count == 0:
                return 0
            end = self.incoming_offset + count
            target[:count] = self.incoming[self.incoming_offset : end]
            self.incoming[self.incoming_offset : end] = b"\x00" * count
            self.incoming_offset = end
            return count

    def write(self, source: memoryview, *, timeout_ms: int) -> int:
        with self._write_lock:
            self.write_calls += 1
            self.write_timeout_values.append(timeout_ms)
            self.retained_write_buffers.append(source.obj)
            action = self.write_actions.popleft() if self.write_actions else len(source)
            if isinstance(action, Exception):
                raise action
            if action == 0:
                return 0
            count = min(action, len(source))
            self.outgoing.extend(source[:count])
            return count

    def cancel_pending_io(self) -> None:
        self.cancel_calls += 1

    def adapter_buffers_are_zero(self) -> bool:
        return all(
            all(value == 0 for value in item)
            for item in self.retained_read_buffers + self.retained_write_buffers
        )


class _RelayByteStream:
    def __init__(self, incoming: bytearray) -> None:
        self.incoming = incoming
        self.offset = 0
        self.closed = False
        self.retained_writes: list[bytearray] = []
        self._read_lock = threading.Lock()
        self._write_lock = threading.Lock()

    def read_exact(self, size: int, *, timeout_steps: int) -> bytearray:
        del timeout_steps
        with self._read_lock:
            end = self.offset + size
            if self.closed:
                raise media_io.MediaIoError("relay fixture closed")
            if end > len(self.incoming):
                raise media_io.MediaIoTimeout("relay fixture empty", retry_safe=True)
            result = bytearray(self.incoming[self.offset : end])
            self.incoming[self.offset : end] = b"\x00" * size
            self.offset = end
            return result

    def write_all(self, data: memoryview, *, timeout_steps: int) -> None:
        del timeout_steps
        with self._write_lock:
            if self.closed:
                raise media_io.MediaIoError("relay fixture closed")
            self.retained_writes.append(data.obj)

    def close(self) -> None:
        self.closed = True
        self.incoming[self.offset :] = b"\x00" * (len(self.incoming) - self.offset)


class EgoCallSerialAdapterTests(unittest.TestCase):
    def endpoint(
        self,
        fake: _FakeInjectedSerial,
        *,
        config: serial_adapter.HostSerialAdapterConfig | None = None,
    ) -> media_io.FramedEndpoint:
        return serial_adapter.make_wearable_serial_endpoint(
            fake, IDENTITY, config=config
        )

    def test_magic_split_across_chunks_and_rom_prefix_resynchronizes(self) -> None:
        valid = _wire("uplink")
        incoming = bytearray(b"ROM boot: ready\r\n")
        incoming.extend(valid)
        media_io._zero(valid)
        fake = _FakeInjectedSerial(incoming, read_actions=[1] * len(incoming))
        endpoint = self.endpoint(fake)

        frame, attempts = endpoint.receive(timeout_steps=50, attempts=1)
        try:
            self.assertEqual(frame.sequence, 0)
            self.assertEqual(frame.direction, "uplink")
            self.assertEqual(attempts, 1)
        finally:
            frame.dispose()
            endpoint.stream.close()

        audit = endpoint.stream.audit()
        self.assertEqual(audit["prefix_bytes_discarded"], len(b"ROM boot: ready\r\n"))
        self.assertEqual(audit["frames_admitted"], 1)
        self.assertTrue(fake.adapter_buffers_are_zero())
        self.assertEqual(fake.cancel_calls, 1)

    def test_false_magic_bad_length_and_bad_crc_then_true_frame(self) -> None:
        bad_length = bytearray(
            media_io._HEADER.pack(
                media_io.WIRE_MAGIC,
                media_io.WIRE_VERSION,
                1,
                1,
                2,
                0,
                0,
                1,
                1,
                1,
                1,
                media_io.FRAME_BYTES - 1,
            )
        )
        bad_crc = _wire("uplink")
        bad_crc[-1] ^= 0x5A
        valid = _wire("uplink")
        incoming = bytearray(b"prefix-")
        incoming.extend(bad_length)
        incoming.extend(bad_crc)
        incoming.extend(valid)
        for item in (bad_length, bad_crc, valid):
            media_io._zero(item)
        fake = _FakeInjectedSerial(incoming, read_actions=[2, 1, 3] * 2_000)
        endpoint = self.endpoint(fake)

        frame, _ = endpoint.receive(timeout_steps=50, attempts=1)
        frame.dispose()
        endpoint.stream.close()

        audit = endpoint.stream.audit()
        self.assertGreaterEqual(audit["invalid_candidates"], 2)
        self.assertEqual(audit["frames_admitted"], 1)
        self.assertTrue(fake.adapter_buffers_are_zero())

    def test_rom_prefix_at_limit_passes_and_one_byte_over_is_terminal(self) -> None:
        limit = 16
        config = serial_adapter.HostSerialAdapterConfig(
            max_resync_discard_bytes=limit,
            max_serial_calls_per_operation=limit + serial_adapter.MAX_WIRE_BYTES,
        )
        valid = _wire("uplink")
        exact_input = bytearray(b"R" * limit)
        exact_input.extend(valid)
        media_io._zero(valid)
        exact_fake = _FakeInjectedSerial(exact_input)
        exact_endpoint = self.endpoint(exact_fake, config=config)
        frame, _ = exact_endpoint.receive(timeout_steps=50, attempts=1)
        frame.dispose()
        exact_endpoint.stream.close()
        self.assertEqual(
            exact_endpoint.stream.audit()["prefix_bytes_discarded"], limit
        )

        over_wire = _wire("uplink")
        over_input = bytearray(b"R" * (limit + 1))
        over_input.extend(over_wire)
        media_io._zero(over_wire)
        over_fake = _FakeInjectedSerial(over_input)
        over_endpoint = self.endpoint(over_fake, config=config)
        with self.assertRaisesRegex(media_io.MediaIoProtocolError, "limit exceeded"):
            over_endpoint.receive(timeout_steps=50, attempts=1)
        self.assertTrue(over_endpoint.stream.audit()["terminal"])
        self.assertEqual(over_fake.cancel_calls, 1)
        over_endpoint.stream.close()

    def test_crc_valid_wrong_session_role_or_clock_is_immediately_terminal(self) -> None:
        wrong_session = _wire("uplink", session_id="other-session")
        wrong_clock = _wire("uplink", source_clock_id="other-device-clock")
        wrong_role = _wire("uplink")
        wrong_role[6] = 2  # source role becomes guardian for an uplink frame
        _recrc(wrong_role)

        for label, candidate in (
            ("session", wrong_session),
            ("role", wrong_role),
            ("clock", wrong_clock),
        ):
            with self.subTest(label=label):
                incoming = bytearray(candidate)
                fake = _FakeInjectedSerial(incoming)
                endpoint = self.endpoint(fake)
                with self.assertRaises(media_io.MediaIoProtocolError):
                    endpoint.receive(timeout_steps=50, attempts=3)
                audit = endpoint.stream.audit()
                self.assertTrue(audit["terminal"])
                self.assertEqual(audit["frames_admitted"], 0)
                self.assertEqual(fake.cancel_calls, 1)
                endpoint.stream.close()
            media_io._zero(candidate)

    def test_crc_valid_unknown_direction_is_terminal_not_resynchronized(self) -> None:
        candidate = _wire("uplink")
        candidate[5] = 9
        _recrc(candidate)
        fake = _FakeInjectedSerial(bytearray(candidate))
        media_io._zero(candidate)
        endpoint = self.endpoint(fake)

        with self.assertRaisesRegex(media_io.MediaIoProtocolError, "direction"):
            endpoint.receive(timeout_steps=50, attempts=2)

        self.assertTrue(endpoint.stream.audit()["terminal"])
        self.assertEqual(fake.cancel_calls, 1)
        endpoint.stream.close()

    def test_zero_progress_read_before_first_byte_is_retryable(self) -> None:
        valid = _wire("uplink")
        incoming = bytearray(valid)
        media_io._zero(valid)
        fake = _FakeInjectedSerial(incoming, read_actions=[0])
        endpoint = self.endpoint(fake)

        frame, attempts = endpoint.receive(timeout_steps=50, attempts=2)
        frame.dispose()
        endpoint.stream.close()

        self.assertEqual(attempts, 2)
        self.assertEqual(endpoint.stream.audit()["zero_progress_timeouts"], 1)
        self.assertTrue(fake.adapter_buffers_are_zero())

    def test_partial_and_unknown_progress_reads_are_terminal(self) -> None:
        valid = _wire("uplink")
        cases = (
            ("partial", [2, 0]),
            (
                "unknown",
                [serial_adapter.InjectedSerialTimeout("unknown", progress=None)],
            ),
            (
                "reported-partial",
                [serial_adapter.InjectedSerialTimeout("partial", progress=1)],
            ),
        )
        for label, actions in cases:
            with self.subTest(label=label):
                fake = _FakeInjectedSerial(bytearray(valid), read_actions=actions)
                endpoint = self.endpoint(fake)
                with self.assertRaises(media_io.MediaIoProtocolError):
                    endpoint.receive(timeout_steps=50, attempts=3)
                self.assertTrue(endpoint.stream.audit()["terminal"])
                self.assertEqual(fake.cancel_calls, 1)
                self.assertTrue(fake.adapter_buffers_are_zero())
                endpoint.stream.close()
        media_io._zero(valid)

    def test_fragmented_exact_write_is_lossless_bounded_and_zeroed(self) -> None:
        fake = _FakeInjectedSerial(write_actions=[1, 2, 3] * 1_000)
        endpoint = self.endpoint(fake)
        frame = media_io._make_frame(
            media_io.MediaIoConfig(identity=IDENTITY), "downlink", 0
        )
        expected = media_io.FrameCodec.encode(frame)
        media_ref = frame.media

        attempts = endpoint.send(frame, timeout_steps=50, attempts=1)

        self.assertEqual(attempts, 1)
        self.assertEqual(fake.outgoing, expected)
        self.assertTrue(all(value == 0 for value in media_ref))
        self.assertTrue(fake.adapter_buffers_are_zero())
        self.assertTrue(all(1 <= value <= 20 for value in fake.write_timeout_values))
        endpoint.stream.close()
        media_io._zero(expected)
        media_io._zero(fake.outgoing)

    def test_zero_progress_write_before_first_byte_retries(self) -> None:
        fake = _FakeInjectedSerial(write_actions=[0, 100_000])
        endpoint = self.endpoint(fake)
        frame = media_io._make_frame(
            media_io.MediaIoConfig(identity=IDENTITY), "downlink", 0
        )
        media_ref = frame.media

        attempts = endpoint.send(frame, timeout_steps=50, attempts=2)

        self.assertEqual(attempts, 2)
        self.assertEqual(endpoint.stream.audit()["zero_progress_timeouts"], 1)
        self.assertTrue(all(value == 0 for value in media_ref))
        self.assertTrue(fake.adapter_buffers_are_zero())
        endpoint.stream.close()
        media_io._zero(fake.outgoing)

    def test_close_cancels_and_quiesces_blocking_write_before_return(self) -> None:
        class BlockingCancelableSerial(_FakeInjectedSerial):
            def __init__(self) -> None:
                super().__init__()
                self.write_entered = threading.Event()
                self.cancelled = threading.Event()

            def write(self, source: memoryview, *, timeout_ms: int) -> int:
                self.write_calls += 1
                self.write_timeout_values.append(timeout_ms)
                self.retained_write_buffers.append(source.obj)
                self.write_entered.set()
                self.cancelled.wait(timeout_ms / 1_000)
                return 0

            def cancel_pending_io(self) -> None:
                self.cancel_calls += 1
                self.cancelled.set()

        fake = BlockingCancelableSerial()
        endpoint = self.endpoint(fake)
        frame = media_io._make_frame(
            media_io.MediaIoConfig(identity=IDENTITY), "downlink", 0
        )
        media_ref = frame.media
        failures: list[Exception] = []

        def writer() -> None:
            try:
                endpoint.send(frame, timeout_steps=50, attempts=1)
            except Exception as error:
                failures.append(error)

        thread = threading.Thread(target=writer)
        thread.start()
        self.assertTrue(fake.write_entered.wait(1.0))

        endpoint.stream.close()

        thread.join(1.0)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(failures), 1)
        self.assertIsInstance(failures[0], media_io.MediaIoTimeout)
        self.assertEqual(fake.cancel_calls, 1)
        self.assertTrue(fake.adapter_buffers_are_zero())
        self.assertTrue(all(value == 0 for value in media_ref))
        self.assertTrue(endpoint.stream.audit()["closed"])

    def test_partial_and_unknown_progress_writes_are_terminal(self) -> None:
        cases = (
            ("partial", [5, 0]),
            (
                "unknown",
                [serial_adapter.InjectedSerialTimeout("unknown", progress=None)],
            ),
            (
                "reported-partial",
                [serial_adapter.InjectedSerialTimeout("partial", progress=1)],
            ),
        )
        for label, actions in cases:
            with self.subTest(label=label):
                fake = _FakeInjectedSerial(write_actions=actions)
                endpoint = self.endpoint(fake)
                frame = media_io._make_frame(
                    media_io.MediaIoConfig(identity=IDENTITY), "downlink", 0
                )
                media_ref = frame.media
                with self.assertRaises(media_io.MediaIoProtocolError):
                    endpoint.send(frame, timeout_steps=50, attempts=3)
                self.assertTrue(endpoint.stream.audit()["terminal"])
                self.assertEqual(fake.cancel_calls, 1)
                self.assertTrue(all(value == 0 for value in media_ref))
                self.assertTrue(fake.adapter_buffers_are_zero())
                endpoint.stream.close()
                media_io._zero(fake.outgoing)

    def test_healthy_adapter_feeds_existing_concurrent_bridge_losslessly(self) -> None:
        frame_count = 2
        uplink = bytearray(b"ROM-prefix\r\n")
        downlink = bytearray()
        expected_downlink = bytearray()
        for sequence in range(frame_count):
            up_wire = _wire("uplink", sequence)
            down_wire = _wire("downlink", sequence)
            uplink.extend(up_wire)
            downlink.extend(down_wire)
            expected_downlink.extend(down_wire)
            media_io._zero(up_wire)
            media_io._zero(down_wire)
        fake = _FakeInjectedSerial(uplink)
        wearable = self.endpoint(fake)
        relay_stream = _RelayByteStream(downlink)
        relay = media_io.FramedEndpoint(
            relay_stream,
            IDENTITY,
            inbound_direction="downlink",
            outbound_direction="uplink",
        )
        config = concurrent.ConcurrentBridgeConfig(
            identity=IDENTITY,
            frame_count=frame_count,
            timeout_steps=50,
            receive_attempts=1,
            send_attempts=1,
            max_runtime_ms=2_000,
            join_timeout_ms=500,
            frame_deadline_ns=500_000_000,
        )

        result = concurrent.ConcurrentDuplexMediaBridge(config).run(
            wearable=wearable, relay=relay
        )

        self.assertEqual(result["result"], "PASS")
        self.assertEqual(result["direction_stats"]["uplink"]["frames_forwarded"], 2)
        self.assertEqual(result["direction_stats"]["downlink"]["frames_forwarded"], 2)
        self.assertEqual(fake.outgoing, expected_downlink)
        self.assertTrue(fake.adapter_buffers_are_zero())
        self.assertTrue(
            all(all(value == 0 for value in item) for item in relay_stream.retained_writes)
        )
        self.assertFalse(_contains_binary(result))
        media_io._zero(expected_downlink)
        media_io._zero(fake.outgoing)

    def test_audit_is_metadata_only_and_excludes_routing_identities(self) -> None:
        fake = _FakeInjectedSerial()
        endpoint = self.endpoint(fake)
        endpoint.stream.close()

        audit = endpoint.stream.audit()
        serialized = json.dumps(audit, sort_keys=True, allow_nan=False)

        self.assertFalse(_contains_binary(audit))
        for value in (
            IDENTITY.session_id,
            IDENTITY.device_id,
            IDENTITY.guardian_id,
            IDENTITY.uplink_clock_id,
            IDENTITY.downlink_clock_id,
        ):
            self.assertNotIn(value, serialized)
        self.assertFalse(audit["media_logged"])
        self.assertFalse(audit["media_persisted"])
        self.assertEqual(
            audit["control_plane"], "separate_unimplemented_no_in_band_control"
        )

    def test_module_has_no_port_enumeration_pyserial_cli_logging_or_storage(self) -> None:
        source = Path("pc_simulator/ego_call_serial_adapter.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("import serial", source)
        self.assertNotIn("list_ports", source)
        self.assertNotIn("serial.Serial(", source)
        self.assertNotIn("argparse", source)
        self.assertNotIn("logging", source)
        self.assertNotIn("print(", source)
        self.assertNotIn("write_bytes", source)
        self.assertNotIn("write_text", source)
        self.assertNotIn("def main(", source)
        self.assertIn("separate_unimplemented_no_in_band_control", source)

    def test_configuration_and_injected_shape_are_bounded_before_io(self) -> None:
        fake = _FakeInjectedSerial()
        with self.assertRaises(media_io.MediaIoError):
            self.endpoint(
                fake,
                config=replace(
                    serial_adapter.HostSerialAdapterConfig(),
                    max_serial_calls_per_operation=1,
                ),
            )
        with self.assertRaisesRegex(media_io.MediaIoError, "caller-injected"):
            serial_adapter.make_wearable_serial_endpoint(object(), IDENTITY)
        self.assertEqual((fake.read_calls, fake.write_calls), (0, 0))


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

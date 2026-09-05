from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest import mock

from pc_simulator import ego_call_media_io as media_io


class EgoCallMediaIoTests(unittest.TestCase):
    def config(self, **changes: object) -> media_io.MediaIoConfig:
        base = media_io.MediaIoConfig(frame_count=8, max_cycles=16)
        return replace(base, **changes)

    def test_healthy_fake_serial_duplex_reaches_both_sinks(self) -> None:
        result = media_io.run_fake_duplex(self.config())

        self.assertEqual(result["result"], "PASS")
        self.assertTrue(result["evaluation"]["full_duplex_observed"])
        self.assertEqual(result["profile"]["frame_bytes"], 640)
        self.assertEqual(result["profile"]["frame_duration_ms"], 20)
        self.assertEqual(result["end_to_end"]["sink_frames"], {"uplink": 8, "downlink": 8})
        self.assertTrue(result["buffer_lifecycle"]["all_runtime_media_buffers_zeroized"])
        self.assertTrue(result["buffer_lifecycle"]["all_fake_transport_buffers_zeroized"])
        self.assertFalse(result["bounded_run"]["network_serial_audio_hardware_used"])
        self.assertEqual(
            result["transport_boundary"]["control_plane"],
            "egolink.p0.v1_message_hub_separate_not_used",
        )
        self.assertEqual(
            result["transport_boundary"]["real_concurrent_20ms_pump"],
            "not_implemented",
        )
        self.assertFalse(result["claims"]["actual_io_ready"])

    def test_one_way_media_cannot_be_connected(self) -> None:
        result = media_io.run_fake_duplex(self.config(), scenario="one-way")

        self.assertEqual(result["result"], "FAIL")
        self.assertFalse(result["evaluation"]["full_duplex_observed"])
        self.assertEqual(result["end_to_end"]["sink_frames"]["downlink"], 0)
        self.assertEqual(result["claims"]["p0_call"], "NOT_RUN")

    def test_bounded_timeout_recovers_within_retry_budget(self) -> None:
        result = media_io.run_fake_duplex(
            self.config(receive_attempts=2), scenario="timeout-recovery"
        )

        self.assertEqual(result["result"], "PASS")
        self.assertEqual(result["direction_stats"]["downlink"]["receive_retry_count"], 1)
        self.assertEqual(
            result["direction_stats"]["downlink"]["receive_timeout_exhaustions"], 0
        )

    def test_bounded_timeout_exhaustion_fails_without_blocking(self) -> None:
        result = media_io.run_fake_duplex(
            self.config(receive_attempts=2), scenario="timeout-failure"
        )

        self.assertEqual(result["result"], "FAIL")
        self.assertEqual(result["bounded_run"]["executed_cycles"], 16)
        self.assertEqual(result["direction_stats"]["downlink"]["frames_forwarded"], 0)
        self.assertEqual(
            result["direction_stats"]["downlink"]["receive_timeout_exhaustions"],
            16,
        )
        self.assertTrue(result["buffer_lifecycle"]["all_runtime_media_buffers_zeroized"])

    def test_direction_queues_apply_backpressure_independently(self) -> None:
        result = media_io.run_fake_duplex(
            self.config(
                downlink_queue_capacity=1,
                downlink_service_interval_cycles=4,
            ),
            scenario="backpressure",
        )

        self.assertEqual(result["result"], "FAIL")
        self.assertEqual(result["direction_stats"]["downlink"]["backpressure_drops"], 1)
        self.assertEqual(result["direction_stats"]["uplink"]["backpressure_drops"], 0)
        self.assertEqual(result["direction_stats"]["uplink"]["frames_forwarded"], 8)
        self.assertTrue(result["buffer_lifecycle"]["all_runtime_media_buffers_zeroized"])

    def test_replay_is_deterministic(self) -> None:
        first = media_io.run_fake_duplex(self.config(), scenario="timeout-recovery")
        second = media_io.run_fake_duplex(self.config(), scenario="timeout-recovery")

        self.assertEqual(first, second)

    def test_strict_outbound_sequence_and_profile_zero_rejected_buffer(self) -> None:
        left, _ = media_io.memory_stream_pair()
        endpoint = media_io.FramedEndpoint(
            left,
            self.config().identity,
            inbound_direction="downlink",
            outbound_direction="uplink",
        )
        wrong_sequence = media_io._make_frame(self.config(), "uplink", 1)
        wrong_sequence_ref = wrong_sequence.media

        with self.assertRaisesRegex(media_io.MediaIoProtocolError, "sequence"):
            endpoint.send(wrong_sequence, timeout_steps=1, attempts=1)
        self.assertEqual(set(wrong_sequence_ref), {0})

        wrong_size = media_io._make_frame(self.config(), "uplink", 0)
        wrong_size.media.pop()
        wrong_size_ref = wrong_size.media
        with self.assertRaisesRegex(media_io.MediaIoProtocolError, "640-byte"):
            endpoint.send(wrong_size, timeout_steps=1, attempts=1)
        self.assertTrue(all(value == 0 for value in wrong_size_ref))

    def test_session_and_role_identity_fail_closed(self) -> None:
        left, _ = media_io.memory_stream_pair()
        endpoint = media_io.FramedEndpoint(
            left,
            self.config().identity,
            inbound_direction="downlink",
            outbound_direction="uplink",
        )
        frame = media_io._make_frame(self.config(), "uplink", 0)
        frame.session_id = "different-session"
        retained = frame.media
        with self.assertRaisesRegex(media_io.MediaIoProtocolError, "session"):
            endpoint.send(frame, timeout_steps=1, attempts=1)
        self.assertTrue(all(value == 0 for value in retained))

        duplicate_identity = replace(
            self.config().identity,
            guardian_id=self.config().identity.device_id,
        )
        with self.assertRaisesRegex(media_io.MediaIoProtocolError, "differ"):
            media_io.FramedEndpoint(
                left,
                duplicate_identity,
                inbound_direction="downlink",
                outbound_direction="uplink",
            )

    def test_crc_corruption_is_rejected_and_transport_copy_is_zeroed(self) -> None:
        sender, receiver = media_io.memory_stream_pair()
        frame = media_io._make_frame(self.config(), "uplink", 0)
        wire = media_io.FrameCodec.encode(frame)
        wire[-1] ^= 0xFF
        sender.write_all(memoryview(wire), timeout_steps=1)
        frame.dispose()
        media_io._zero(wire)

        with self.assertRaisesRegex(media_io.MediaIoProtocolError, "integrity"):
            media_io.FrameCodec.read(receiver, timeout_steps=1)
        sender.dispose_transport_buffers()
        self.assertTrue(sender.audit()["owned_buffers_zeroized"])
        self.assertEqual(sender.audit()["pending_bytes"], 0)

    def test_send_retries_and_zeroes_the_same_wire_and_media_objects(self) -> None:
        class RetainingStream:
            def __init__(self) -> None:
                self.calls = 0
                self.retained: bytearray | None = None

            def read_exact(self, size: int, *, timeout_steps: int) -> bytearray:
                raise AssertionError("read not expected")

            def write_all(self, data: memoryview, *, timeout_steps: int) -> None:
                self.calls += 1
                self.retained = data.obj
                if self.calls == 1:
                    raise media_io.MediaIoTimeout(
                        "fixture timeout", retry_safe=True
                    )

            def close(self) -> None:
                return None

        stream = RetainingStream()
        endpoint = media_io.FramedEndpoint(
            stream,
            self.config().identity,
            inbound_direction="downlink",
            outbound_direction="uplink",
        )
        frame = media_io._make_frame(self.config(), "uplink", 0)
        media_ref = frame.media

        attempts = endpoint.send(frame, timeout_steps=1, attempts=2)

        self.assertEqual(attempts, 2)
        self.assertEqual(stream.calls, 2)
        self.assertIsInstance(stream.retained, bytearray)
        self.assertTrue(all(value == 0 for value in stream.retained))
        self.assertTrue(all(value == 0 for value in media_ref))

    def test_unknown_progress_write_timeout_is_terminal_and_not_retried(self) -> None:
        class UnknownProgressStream:
            def __init__(self) -> None:
                self.calls = 0
                self.closed = False
                self.retained: bytearray | None = None

            def read_exact(self, size: int, *, timeout_steps: int) -> bytearray:
                raise AssertionError("read not expected")

            def write_all(self, data: memoryview, *, timeout_steps: int) -> None:
                self.calls += 1
                self.retained = data.obj
                raise media_io.MediaIoTimeout(
                    "unknown progress", retry_safe=False
                )

            def close(self) -> None:
                self.closed = True

        stream = UnknownProgressStream()
        endpoint = media_io.FramedEndpoint(
            stream,
            self.config().identity,
            inbound_direction="downlink",
            outbound_direction="uplink",
        )
        frame = media_io._make_frame(self.config(), "uplink", 0)
        retained_media = frame.media

        with self.assertRaisesRegex(media_io.MediaIoProtocolError, "unknown progress"):
            endpoint.send(frame, timeout_steps=1, attempts=3)

        self.assertEqual(stream.calls, 1)
        self.assertTrue(stream.closed)
        self.assertTrue(all(value == 0 for value in stream.retained))
        self.assertTrue(all(value == 0 for value in retained_media))

    def test_tail_timeout_after_consumed_header_is_terminal(self) -> None:
        sender, receiver = media_io.memory_stream_pair()
        receiver_endpoint = media_io.FramedEndpoint(
            receiver,
            self.config().identity,
            inbound_direction="uplink",
            outbound_direction="downlink",
        )
        frame = media_io._make_frame(self.config(), "uplink", 0)
        wire = media_io.FrameCodec.encode(frame)
        header_only = bytearray(wire[: media_io._HEADER.size])
        sender.write_all(memoryview(header_only), timeout_steps=1)
        frame.dispose()
        media_io._zero(wire)
        media_io._zero(header_only)

        with self.assertRaisesRegex(
            media_io.MediaIoProtocolError, "after header consumption"
        ):
            receiver_endpoint.receive(timeout_steps=1, attempts=3)
        with self.assertRaisesRegex(media_io.MediaIoError, "closed"):
            receiver.read_exact(1, timeout_steps=1)
        sender.dispose_transport_buffers()
        self.assertTrue(sender.audit()["owned_buffers_zeroized"])

    def test_bridge_rejects_mismatched_endpoint_identity_before_io(self) -> None:
        class CountingStream:
            def __init__(self) -> None:
                self.reads = 0
                self.writes = 0

            def read_exact(self, size: int, *, timeout_steps: int) -> bytearray:
                self.reads += 1
                raise AssertionError("identity gate must run before read")

            def write_all(self, data: memoryview, *, timeout_steps: int) -> None:
                self.writes += 1
                raise AssertionError("identity gate must run before write")

            def close(self) -> None:
                return None

        wearable_stream = CountingStream()
        relay_stream = CountingStream()
        config = self.config()
        wearable = media_io.FramedEndpoint(
            wearable_stream,
            config.identity,
            inbound_direction="uplink",
            outbound_direction="downlink",
        )
        other_identity = replace(
            config.identity, session_id="other-call020b-session"
        )
        relay = media_io.FramedEndpoint(
            relay_stream,
            other_identity,
            inbound_direction="downlink",
            outbound_direction="uplink",
        )

        with self.assertRaisesRegex(media_io.MediaIoProtocolError, "before I/O"):
            media_io.DuplexMediaBridge(config).run(wearable=wearable, relay=relay)

        self.assertEqual(
            (wearable_stream.reads, wearable_stream.writes), (0, 0)
        )
        self.assertEqual((relay_stream.reads, relay_stream.writes), (0, 0))

    def test_socket_stream_uses_recv_into_and_zeroes_partial_timeout_buffer(self) -> None:
        class FakeSocket:
            def __init__(self) -> None:
                self.calls = 0
                self.retained: bytearray | None = None

            def recv(self, size: int) -> bytes:
                raise AssertionError("recv would create an immutable media copy")

            def recv_into(self, target: memoryview, size: int) -> int:
                self.calls += 1
                self.retained = target.obj
                if self.calls == 1:
                    target[:2] = b"ab"
                    return 2
                raise media_io.socket.timeout()

            def sendall(self, data: memoryview) -> None:
                return None

            def close(self) -> None:
                return None

        fake_socket = FakeSocket()
        stream = media_io.SocketByteStream(fake_socket)

        with self.assertRaises(media_io.MediaIoTimeout) as raised:
            stream.read_exact(4, timeout_steps=1)

        self.assertFalse(raised.exception.retry_safe)
        self.assertIsNotNone(fake_socket.retained)
        self.assertTrue(all(value == 0 for value in fake_socket.retained))

    def test_tls_preflight_is_offline_source_bound_and_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ca_file = root / "ca.pem"
            token_file = root / "relay.token"
            ca_file.write_text("fixture-ca", encoding="utf-8")
            token_file.write_text("super-private-token\n", encoding="utf-8")
            config = media_io.TlsRelayConfig(
                relay_host="relay.private.example",
                relay_port=443,
                server_hostname="relay.private.example",
                source_ipv4="192.168.0.100",
                interface_name="rndis-fixture",
                ca_file=ca_file,
                token_file=token_file,
            )

            result = media_io.offline_tls_preflight(config)
            serialized = json.dumps(result, ensure_ascii=False)

        self.assertEqual(
            result["preflight_result"], "BLOCKED_PENDING_AUTHORIZED_EGRESS_PROBE"
        )
        self.assertEqual(result["source_binding"]["source_ipv4"], "192.168.0.100")
        self.assertEqual(result["source_binding"]["interface_name"], "rndis-fixture")
        self.assertEqual(
            result["source_binding"]["interface_name_to_ipv4_os_mapping"],
            "unverified_offline",
        )
        self.assertFalse(result["execution"]["socket_opened"])
        self.assertFalse(result["execution"]["outbound_traffic_sent"])
        self.assertEqual(
            result["data_plane"]["prior_explicit_source_bound_external_probe"],
            "timed_out",
        )
        for forbidden in (
            "super-private-token",
            "relay.private.example",
            str(ca_file),
            str(token_file),
        ):
            self.assertNotIn(forbidden, serialized)

    def test_tls_token_source_and_source_address_validation_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ca_file = Path(directory) / "ca.pem"
            ca_file.write_text("fixture-ca", encoding="utf-8")
            base = media_io.TlsRelayConfig(
                relay_host="relay.example",
                relay_port=443,
                server_hostname="relay.example",
                source_ipv4="192.168.0.100",
                interface_name="rndis-fixture",
                ca_file=ca_file,
                token_env_var="CALL020_TOKEN",
            )
            with self.assertRaisesRegex(media_io.MediaIoError, "unavailable"):
                media_io.offline_tls_preflight(base, environ={})
            with self.assertRaisesRegex(media_io.MediaIoError, "non-loopback"):
                media_io.offline_tls_preflight(
                    replace(base, source_ipv4="127.0.0.1"),
                    environ={"CALL020_TOKEN": "secret"},
                )
            with self.assertRaisesRegex(media_io.MediaIoError, "exactly one"):
                replace(base, token_env_var=None, token_file=None).validate()

    def test_oversized_token_file_is_bounded_zeroed_and_not_disclosed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ca_file = root / "ca.pem"
            token_file = root / "oversized.token"
            ca_file.write_text("fixture-ca", encoding="utf-8")
            secret = "Z" * (media_io.MAX_TOKEN_BYTES + 1)
            token_file.write_text(secret, encoding="ascii")
            config = media_io.TlsRelayConfig(
                relay_host="relay.example",
                relay_port=443,
                server_hostname="relay.example",
                source_ipv4="192.168.0.100",
                interface_name="rndis-fixture",
                ca_file=ca_file,
                token_file=token_file,
            )
            with mock.patch.object(
                media_io, "_zero", wraps=media_io._zero
            ) as zero:
                with self.assertRaises(media_io.MediaIoError) as raised:
                    media_io.offline_tls_preflight(config)

        rendered = str(raised.exception)
        self.assertNotIn(secret, rendered)
        self.assertNotIn(str(token_file), rendered)
        zero.assert_called()
        rejected_buffer = zero.call_args.args[0]
        self.assertLessEqual(len(rejected_buffer), media_io.MAX_TOKEN_BYTES + 1)
        self.assertTrue(all(value == 0 for value in rejected_buffer))

    def test_tls_connector_requires_authorization_before_socket_creation(self) -> None:
        config = media_io.TlsRelayConfig(
            relay_host="relay.example",
            relay_port=443,
            server_hostname="relay.example",
            source_ipv4="192.168.0.100",
            interface_name="rndis-fixture",
            ca_file=Path("not-read-before-authorization.pem"),
            token_env_var="CALL020_TOKEN",
        )
        with mock.patch.object(media_io.socket, "socket") as socket_factory:
            with self.assertRaisesRegex(media_io.MediaIoError, "authorization"):
                media_io.AuthorizedTlsRelayConnector.connect(config)
            socket_factory.assert_not_called()

    def test_authorized_connector_binds_source_before_connect_under_fakes(self) -> None:
        events: list[object] = []

        class FakeRawSocket:
            def settimeout(self, value: int) -> None:
                events.append(("timeout", value))

            def bind(self, address: tuple[str, int]) -> None:
                events.append(("bind", address))

            def connect(self, address: tuple[str, int]) -> None:
                events.append(("connect", address))

            def close(self) -> None:
                events.append("raw-close")

        class FakeTlsSocket:
            def __init__(self) -> None:
                self.auth_ref: bytearray | None = None

            def sendall(self, data: bytearray) -> None:
                events.append("auth")
                self.auth_ref = data

            def recv(self, size: int) -> bytes:
                return media_io.AUTH_ACK

            def close(self) -> None:
                events.append("tls-close")

        class FakeContext:
            minimum_version: object = None
            check_hostname = False
            verify_mode: object = None

            def load_cert_chain(self, *, certfile: str, keyfile: str) -> None:
                events.append("client-cert")

            def wrap_socket(self, raw: FakeRawSocket, *, server_hostname: str) -> FakeTlsSocket:
                events.append(("wrap", server_hostname))
                return tls_socket

        raw_socket = FakeRawSocket()
        tls_socket = FakeTlsSocket()
        context = FakeContext()
        with tempfile.TemporaryDirectory() as directory:
            ca_file = Path(directory) / "ca.pem"
            ca_file.write_text("fixture-ca", encoding="utf-8")
            config = media_io.TlsRelayConfig(
                relay_host="relay.example",
                relay_port=443,
                server_hostname="relay.example",
                source_ipv4="192.168.0.100",
                interface_name="rndis-fixture",
                ca_file=ca_file,
                token_env_var="CALL020_TOKEN",
            )
            with (
                mock.patch.object(media_io.socket, "socket", return_value=raw_socket),
                mock.patch.object(
                    media_io.ssl, "create_default_context", return_value=context
                ),
            ):
                stream = media_io.AuthorizedTlsRelayConnector.connect(
                    config,
                    operator_authorized=True,
                    environ={"CALL020_TOKEN": "private-token"},
                )

        self.assertLess(
            events.index(("bind", ("192.168.0.100", 0))),
            events.index(("connect", ("relay.example", 443))),
        )
        self.assertTrue(all(value == 0 for value in tls_socket.auth_ref))
        stream.close()

    def test_cli_is_metadata_only_and_exposes_no_packet_identity(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = media_io.main(["loopback", "--frames", "6"])
        rendered = output.getvalue()
        parsed = json.loads(rendered)

        self.assertEqual(exit_code, 0)
        self.assertEqual(parsed["result"], "PASS")
        self.assertNotIn("packet_id", rendered)
        self.assertNotIn("session_id", rendered)
        self.assertNotIn("call020b-local-session-001", rendered)
        self.assertNotIn('"records":', rendered)

    def test_media_module_does_not_import_message_hub_or_event_store(self) -> None:
        source = Path(media_io.__file__).read_text(encoding="utf-8")

        self.assertNotIn("import pc_simulator.board_bridge", source)
        self.assertNotIn("import pc_simulator.event_store", source)
        self.assertNotIn("from pc_simulator import board_bridge", source)
        self.assertNotIn("from pc_simulator import event_store", source)


if __name__ == "__main__":
    unittest.main()

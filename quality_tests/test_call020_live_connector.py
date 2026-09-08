from __future__ import annotations

import datetime
import hashlib
import json
import socket
import ssl
import struct
import sys
import tempfile
import threading
import time
import unittest
import contextlib
import io
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from pc_simulator import ego_call_live_connector as live
from pc_simulator import ego_call_operator_control as control
from pc_simulator import ego_call_live_endpoints as endpoints
from pc_simulator.ego_call_media_io import EndpointIdentity, FramedEndpoint, MediaFrame
from pc_simulator.ego_call_tls_stream_adapter import ConnectedTlsOrderedByteStream, ConnectedTlsStreamConfig, DEFAULT_ALPN


IDENTITY = EndpointIdentity("native-session", "native-device", "native-guardian", "native-up", "native-down")


class _ObservedWindowsSocket(socket.socket):
    """Real Winsock operations, with bounded preconnect fault injection."""

    def __init__(self, *args, fault=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fault = fault
        self.events = []

    def setsockopt(self, level, option, value):
        self.events.append(("set", level, option, value))
        if self.fault == "set_error":
            raise OSError("injected option rejection")
        return super().setsockopt(level, option, value)

    def getsockopt(self, level, option, *args):
        actual = super().getsockopt(level, option, *args)
        self.events.append(("get", level, option, actual))
        if self.fault == "get_error":
            raise OSError("injected readback failure")
        if self.fault == "wrong_index":
            return actual + 1
        if self.fault == "wrong_type":
            return True
        return actual

    def bind(self, address):
        self.events.append(("bind", address))
        return super().bind(address)

    def connect(self, address):
        self.events.append(("connect", address))
        return super().connect(address)


class LiveConnectorTests(unittest.TestCase):
    """Real OS loopback, real OpenSSL TLS, actual relay/threads; synthetic media."""

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="call020-tls-")
        cls.path = Path(cls.temp.name)
        key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Temporary CALL test CA")])
        now = datetime.datetime.now(datetime.timezone.utc)
        builder = x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(minutes=1)).not_valid_after(now + datetime.timedelta(days=1))
        ca = builder.add_extension(x509.BasicConstraints(ca=True, path_length=0), True).add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), True).sign(key, hashes.SHA256())
        cls.ca = str(cls.path / "ca.pem")
        Path(cls.ca).write_bytes(ca.public_bytes(serialization.Encoding.PEM))
        cls.certs = {}
        for role in ("server", "device", "guardian", "stranger"):
            leaf_key = ec.generate_private_key(ec.SECP256R1())
            leaf_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, role)])
            leaf = x509.CertificateBuilder().subject_name(leaf_name).issuer_name(name).public_key(leaf_key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(minutes=1)).not_valid_after(now + datetime.timedelta(days=1)).add_extension(x509.BasicConstraints(ca=False, path_length=None), True).add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH if role == "server" else ExtendedKeyUsageOID.CLIENT_AUTH]), False)
            if role == "server":
                leaf = leaf.add_extension(x509.SubjectAlternativeName([x509.DNSName("relay.test")]), False)
            certificate = leaf.sign(key, hashes.SHA256())
            cert_path, key_path = cls.path / (role + ".pem"), cls.path / (role + ".key")
            cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
            key_path.write_bytes(leaf_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
            cls.certs[role] = (str(cert_path), str(key_path), hashlib.sha256(certificate.public_bytes(serialization.Encoding.DER)).hexdigest())

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def config(self, **changes):
        return replace(live.RelayRunConfig(
            "loopback-run", "127.0.0.1", 0, self.ca,
            *self.certs["server"][:2], self.certs["device"][2], self.certs["guardian"][2],
            frame_count=12, max_runtime_ms=3000, setup_timeout_ms=3000, enabled=True,
        ), **changes)

    def route(self, port, **changes):
        return replace(control.HostTlsConnectorConfig(
            "127.0.0.1", port, "127.0.0.1", "relay.test", ca_file=self.ca,
            enabled=True, overall_timeout_ms=5000,
            tcp_connect_timeout_ms=1000, handshake_timeout_ms=1000, authentication_timeout_ms=3000,
        ), **changes)

    def start_relay(self, **changes):
        relay = live.LiveMtlsRelay(self.config(**changes))
        port = relay.listen()
        results = []
        def run():
            try:
                results.append(relay.run())
            except Exception as exc:
                results.append(exc)
        thread = threading.Thread(target=run)
        thread.start()
        return relay, port, thread, results

    def connect(self, port, role, identity=IDENTITY, certificate=None,
                route_changes=None, raw_factory=None):
        certificate = certificate or role
        route = self.route(port, **(route_changes or {}))
        if raw_factory is None:
            connector = live.make_connector(route, cert_file=self.certs[certificate][0], key_file=self.certs[certificate][1])
        else:
            connector = control.DefaultOffHostTlsConnector(
                route, authenticator=live.MtlsSessionAuthenticator(),
                socket_factory=raw_factory,
                ssl_context_factory=lambda: live.client_context(*self.certs[certificate][:2]),
            )
        bundle = connector.open_verified(control.TlsOpenRequest("loopback-run", identity, DEFAULT_ALPN, 5000, role))
        stream = ConnectedTlsOrderedByteStream(bundle.tls_socket, bundle.tls_attestation, bundle.authentication_decision, ConnectedTlsStreamConfig(identity, role, enabled=True))
        return stream, connector

    def test_real_tls_admission_duplex_media_and_guardian_descriptor(self):
        self.check_real_tls_duplex()

    @unittest.skipUnless(sys.platform == "win32", "IP_UNICAST_IF is a Windows IPv4 socket option")
    def test_windows_pinned_loopback_actual_options_tls_and_duplex(self):
        self.assertTrue(socket.if_indextoname(1))
        self.check_real_tls_duplex(interface_index=1)

    def check_real_tls_duplex(self, interface_index=None):
        relay, port, server_thread, results = self.start_relay()
        client_results = {}
        route_changes = {"windows_ipv4_interface_index": interface_index}
        observed = []
        def raw_factory(*args, **kwargs):
            raw = _ObservedWindowsSocket(*args, **kwargs)
            observed.append(raw)
            return raw
        def guardian_connect():
            try:
                # Patch only the module reference, not Python's global socket
                # module. Every underlying operation still uses real Winsock.
                proxy = SimpleNamespace(**{**vars(socket), "socket": raw_factory})
                observation = patch.object(live, "socket", proxy) if interface_index else contextlib.nullcontext()
                with observation:
                    client_results["guardian"] = live.guardian_join(self.route(port, **route_changes), run_id="loopback-run", cert_file=self.certs["guardian"][0], key_file=self.certs["guardian"][1])
            except Exception as exc:
                client_results["guardian"] = exc
        guardian_thread = threading.Thread(target=guardian_connect)
        guardian_thread.start()
        device, connector = self.connect(port, "device", route_changes=route_changes,
                                         raw_factory=raw_factory if interface_index else None)
        guardian_thread.join(5)
        self.assertFalse(guardian_thread.is_alive())
        self.assertIsInstance(client_results.get("guardian"), tuple)
        identity, guardian = client_results["guardian"]
        self.assertEqual(identity, IDENTITY)
        self.assertTrue(connector.audit()["connected_source_binding_verified"])
        self.assertTrue(connector.audit()["connected_numeric_peer_verified"])
        self.assertEqual(connector.audit()["windows_ipv4_interface_verified"], interface_index is not None)
        if interface_index is not None:
            self.assertEqual(len(observed), 2)
            for raw in observed:
                self.assertEqual(raw.events[:2], [
                    ("set", socket.IPPROTO_IP, 31, b"\x00\x00\x00\x01"),
                    ("get", socket.IPPROTO_IP, 31, 1),
                ])
                self.assertEqual(raw.events[2], ("bind", ("127.0.0.1", 0)))
                self.assertEqual(raw.events[3], ("connect", ("127.0.0.1", port)))
        endpoints = {
            "uplink": FramedEndpoint(device, IDENTITY, inbound_direction="downlink", outbound_direction="uplink"),
            "downlink": FramedEndpoint(guardian, IDENTITY, inbound_direction="uplink", outbound_direction="downlink"),
        }
        outcomes = []
        def send(direction):
            endpoint = endpoints[direction]
            try:
                start = time.monotonic()
                for sequence in range(12):
                    time.sleep(max(0, start + sequence * .02 - time.monotonic()))
                    source_role, source, target_role, target, clock = IDENTITY.values_for(direction)
                    frame = MediaFrame(IDENTITY.session_id, direction, source_role, source, target_role, target, sequence, clock, time.monotonic_ns(), bytearray([17 if direction == "uplink" else 31] * 640))
                    try:
                        endpoint.send(frame, timeout_steps=25, attempts=1)
                    finally:
                        frame.dispose()
                outcomes.append((direction, "sent", 12))
            except Exception as exc:
                outcomes.append(exc)
        def receive(direction):
            try:
                endpoint = endpoints[direction]
                for sequence in range(12):
                    frame, _ = endpoint.receive(timeout_steps=25, attempts=16)
                    try:
                        self.assertEqual(frame.sequence, sequence)
                        self.assertEqual(frame.media, bytearray([31 if direction == "uplink" else 17] * 640))
                    finally:
                        frame.dispose()
                outcomes.append((direction, "received", 12))
            except Exception as exc:
                outcomes.append(exc)
        workers = [threading.Thread(target=fn, args=(direction,)) for direction in endpoints for fn in (send, receive)]
        try:
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join(5)
            server_thread.join(5)
            self.assertFalse(any(worker.is_alive() for worker in workers))
            self.assertFalse(server_thread.is_alive())
            self.assertEqual(len(outcomes), 4)
            self.assertTrue(all(isinstance(outcome, tuple) for outcome in outcomes), (outcomes, [getattr(x, "metadata", str(x)) for x in results]))
            self.assertIsInstance(results[0], dict, repr(results[0]))
            self.assertEqual(results[0]["result"], "PASS")
            self.assertEqual(results[0]["p0_call"], "NOT_RUN")
            with self.assertRaises(live.LiveAdmissionError):
                relay.listen()  # terminal run cannot resurrect a finished call
        finally:
            device.close()
            guardian.close()

    @unittest.skipUnless(sys.platform == "win32", "IP_UNICAST_IF is a Windows IPv4 socket option")
    def test_windows_option_failures_stop_both_consumers_before_bind_or_connect(self):
        for consumer in ("device", "guardian"):
            for fault in ("set_error", "get_error", "wrong_index", "wrong_type", "kernel_reject"):
                with self.subTest(consumer=consumer, fault=fault):
                    index = 0xFFFFFF if fault == "kernel_reject" else 1
                    if fault == "kernel_reject":
                        self.assertNotIn(index, {item[0] for item in socket.if_nameindex()})
                    raw = _ObservedWindowsSocket(socket.AF_INET, socket.SOCK_STREAM, fault=fault)
                    route = self.route(1, windows_ipv4_interface_index=index)
                    if consumer == "device":
                        connector = control.DefaultOffHostTlsConnector(
                            route, authenticator=live.MtlsSessionAuthenticator(),
                            socket_factory=lambda *args: raw,
                            ssl_context_factory=lambda: live.client_context(*self.certs["device"][:2]),
                        )
                        with self.assertRaises(control.HostTlsConnectorBlocked) as raised:
                            connector.open_verified(control.TlsOpenRequest("loopback-run", IDENTITY, DEFAULT_ALPN, 5000))
                        self.assertEqual(raised.exception.reason_code, "windows_ipv4_interface_pin_failed")
                        self.assertFalse(raised.exception.metadata["network_attempted"])
                        self.assertFalse(connector.audit()["handshake_attempted"])
                        self.assertEqual(connector.audit()["authentication_callback_calls"], 0)
                    else:
                        proxy = SimpleNamespace(**{**vars(socket), "socket": lambda *args: raw})
                        with patch.object(live, "socket", proxy), self.assertRaises((control.HostControlError, OSError)):
                            live.guardian_join(route, run_id="loopback-run", cert_file=self.certs["guardian"][0], key_file=self.certs["guardian"][1])
                    self.assertEqual(raw.fileno(), -1)
                    self.assertFalse(any(event[0] in {"bind", "connect"} for event in raw.events))

    def test_guardian_rejects_windows_only_route_before_audio_import(self):
        values = {"tls": {"peer_ipv4": "127.0.0.1", "peer_port": 443,
                          "source_ipv4": "127.0.0.1", "tls_hostname": "relay.test",
                          "ca_file": self.ca, "windows_ipv4_interface_index": 1}}
        with patch.object(control.sys, "platform", "linux"), patch.dict(sys.modules, {"sounddevice": None}):
            with self.assertRaisesRegex(control.HostControlError, "requires Windows"):
                endpoints.run_guardian(values)

    def test_hostname_and_role_certificate_rejection_on_real_tls(self):
        for case in ("hostname", "role"):
            with self.subTest(case=case):
                _, port, worker, results = self.start_relay(setup_timeout_ms=1000)
                route = self.route(port, tls_hostname="wrong.test") if case == "hostname" else self.route(port)
                cert = "device" if case == "hostname" else "stranger"
                connector = live.make_connector(route, cert_file=self.certs[cert][0], key_file=self.certs[cert][1])
                with self.assertRaises(control.HostTlsConnectorBlocked):
                    connector.open_verified(control.TlsOpenRequest("loopback-run", IDENTITY, DEFAULT_ALPN, 5000))
                worker.join(4)
                self.assertFalse(worker.is_alive())
                self.assertIsInstance(results[0], Exception)

    def test_unknown_role_rejected_before_network(self):
        connector = live.make_connector(self.route(1), cert_file=self.certs["device"][0], key_file=self.certs["device"][1])
        with self.assertRaises(control.HostTlsConnectorBlocked):
            connector.open_verified(control.TlsOpenRequest("loopback-run", IDENTITY, DEFAULT_ALPN, 5000, "admin"))
        self.assertFalse(connector.audit()["socket_created"])

    def test_cross_session_pair_rejected_before_acknowledgement(self):
        _, port, server, results = self.start_relay(setup_timeout_ms=1000)
        failures = []
        def attempt(role, identity):
            try:
                stream, _ = self.connect(port, role, identity)
                stream.close()
                failures.append("unexpected admission")
            except control.HostTlsConnectorBlocked:
                failures.append(role)
        wrong = replace(IDENTITY, session_id="wrong-session")
        workers = [threading.Thread(target=attempt, args=("device", IDENTITY)),
                   threading.Thread(target=attempt, args=("guardian", wrong))]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(3)
        server.join(3)
        self.assertFalse(server.is_alive())
        self.assertCountEqual(failures, ["device", "guardian"])
        self.assertIsInstance(results[0], Exception)

    def test_real_tls_pending_read_cancellation_is_bounded(self):
        _, port, server, results = self.start_relay()
        connected = []
        guardian = threading.Thread(target=lambda: connected.append(self.connect(port, "guardian")[0]))
        guardian.start()
        device, _ = self.connect(port, "device")
        guardian.join(3)
        read_errors = []
        def read():
            try:
                device.read_exact(32, timeout_steps=50)
            except Exception as exc:
                read_errors.append(exc)
        reader = threading.Thread(target=read)
        reader.start()
        started = time.monotonic()
        device.request_cancel()
        reader.join(1)
        try:
            self.assertFalse(reader.is_alive())
            self.assertLess(time.monotonic() - started, 1)
            self.assertEqual(len(read_errors), 1)
        finally:
            device.close()
            for stream in connected:
                stream.close()
            server.join(3)
        self.assertFalse(server.is_alive())

    def test_cli_plan_does_not_open_audio_serial_or_network(self):
        path = self.path / "inert-plan.json"
        path.write_text("{}", encoding="utf-8")
        for role in ("guardian", "wearable"):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(endpoints.main([role, "--config", str(path)]), 0)
            self.assertFalse(json.loads(output.getvalue())["external_io_performed"])

    def test_cli_intent_is_one_shot_and_zeroes_its_token(self):
        token = bytearray(b"temporary-test-intent" * 2)
        verifier = endpoints._CliIntentVerifier("run", token)
        self.assertTrue(verifier.authorize_once(token=memoryview(token), run_id="run", action=control.AUTHORIZATION_ACTION, timeout_ms=10))
        self.assertFalse(any(verifier.token))
        self.assertFalse(verifier.authorize_once(token=memoryview(token), run_id="run", action=control.AUTHORIZATION_ACTION, timeout_ms=10))
        self.assertFalse(verifier.authorize_once(token=memoryview(bytearray(len(token))), run_id="run", action=control.AUTHORIZATION_ACTION, timeout_ms=10))

    def test_audio_names_must_match_exactly_and_unambiguously(self):
        api = SimpleNamespace(
            query_hostapis=lambda: [{"name": "WASAPI"}, {"name": "MME"}],
            query_devices=lambda: [
                {"name": "Headset", "hostapi": index, "max_input_channels": 1, "max_output_channels": 1}
                for index in (0, 1)],
        )
        with self.assertRaises(ValueError):
            endpoints._exact_audio_device(api, "Head", "input")
        with self.assertRaises(ValueError):
            endpoints._exact_audio_device(api, "Headset", "input")
        self.assertEqual(endpoints._exact_audio_device(api, "Headset", "input", "WASAPI"), 0)

    def test_admission_rejects_duplicate_json_oversize_and_truncation(self):
        packets = [struct.pack("!I", 4097), struct.pack("!I", 2) + b"{", struct.pack("!I", 13) + b'{"x":1,"x":2}']
        for packet in packets:
            with self.subTest(packet_size=len(packet)):
                left, right = socket.socketpair()
                try:
                    left.settimeout(.02)
                    right.sendall(packet)
                    right.shutdown(socket.SHUT_WR)
                    with self.assertRaises((ValueError, live.LiveAdmissionError)):
                        live._receive(left, time.monotonic() + .2)
                finally:
                    left.close()
                    right.close()

    def test_wrong_ack_is_rejected_by_exact_stream_authenticator(self):
        for mutation in ({"connection_id": "wrong-connection"}, {"accepted": 1}):
            with self.subTest(mutation=mutation):
                self.check_wrong_ack(mutation)

    def check_wrong_ack(self, mutation):
        left, right = socket.socketpair()
        left.settimeout(.02)
        right.settimeout(.02)
        def peer():
            value = live._receive(right, time.monotonic() + 1)
            live._send(right, {**value, "accepted": True, **mutation}, time.monotonic() + 1)
        worker = threading.Thread(target=peer)
        worker.start()
        evidence = control.HostTlsPeerEvidence("loopback-run", IDENTITY, "connection", "127.0.0.1", "relay.test", DEFAULT_ALPN, "TLSv1.3", "0" * 64, time.monotonic_ns())
        try:
            with self.assertRaises(live.LiveAdmissionError):
                live.MtlsSessionAuthenticator().authorize_tls_stream(evidence=evidence, tls_socket=left, timeout_ms=1000)
        finally:
            worker.join(1)
            left.close()
            right.close()


if __name__ == "__main__":
    unittest.main()

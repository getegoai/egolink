from __future__ import annotations

import json
import threading
import unittest
from array import array
from dataclasses import replace
from pathlib import Path
from unittest import mock

from pc_simulator import ego_call_media_io as media_io
from pc_simulator import ego_call_os_serial_wrapper as os_serial
from pc_simulator import ego_call_serial_adapter as serial_adapter


IDENTITY = media_io.EndpointIdentity(
    session_id="call020k-session",
    device_id="call020k-device",
    guardian_id="call020k-guardian",
    uplink_clock_id="call020k-device-clock",
    downlink_clock_id="call020k-guardian-clock",
)


class _FakeOpenedDriver:
    def __init__(
        self,
        *,
        port: str,
        baudrate: int = os_serial.DEFAULT_BAUDRATE,
        timeout: float = 0.02,
        write_timeout: float = 0.02,
        exclusive: bool = True,
        is_open: bool = True,
        incoming: bytearray | None = None,
        read_actions: list[object] | None = None,
        write_actions: list[object] | None = None,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.write_timeout = write_timeout
        self.exclusive = exclusive
        self.is_open = is_open
        self.incoming = incoming if incoming is not None else bytearray()
        self.outgoing = bytearray()
        self.read_actions = list(read_actions or [])
        self.write_actions = list(write_actions or [])
        self.read_calls = 0
        self.write_calls = 0
        self.open_calls = 0
        self.close_calls = 0
        self.cancel_read_calls = 0
        self.cancel_write_calls = 0
        self.read_entered = threading.Event()
        self.write_entered = threading.Event()
        self.read_cancelled = threading.Event()
        self.write_cancelled = threading.Event()
        self.read_timeout_values: list[float | None] = []
        self.write_timeout_values: list[float | None] = []
        self.retained_read_buffers: list[bytearray] = []
        self.retained_write_buffers: list[bytearray] = []

    @staticmethod
    def _next(actions: list[object], fallback: int) -> object:
        return actions.pop(0) if actions else fallback

    def open(self) -> None:
        self.open_calls += 1
        self.is_open = True

    def readinto(self, target: memoryview) -> int:
        self.read_calls += 1
        self.read_entered.set()
        self.read_timeout_values.append(self.timeout)
        self.retained_read_buffers.append(target.obj)
        action = self._next(self.read_actions, min(len(target), len(self.incoming)))
        if action == "block":
            self.read_cancelled.wait(1.0)
            raise os_serial.DriverIoTimeout("cancelled read", progress=None)
        if isinstance(action, BaseException):
            raise action
        if type(action) is not int:
            raise AssertionError("invalid read action")
        result = action
        if action > 0:
            copied = min(action, len(target), len(self.incoming))
            target[:copied] = self.incoming[:copied]
            self.incoming[:copied] = b"\x00" * copied
            del self.incoming[:copied]
            result = copied
        return result

    def write(self, source: memoryview) -> int:
        self.write_calls += 1
        self.write_entered.set()
        self.write_timeout_values.append(self.write_timeout)
        self.retained_write_buffers.append(source.obj)
        action = self._next(self.write_actions, len(source))
        if action == "block":
            self.write_cancelled.wait(1.0)
            raise os_serial.DriverIoTimeout("cancelled write", progress=None)
        if isinstance(action, BaseException):
            raise action
        if type(action) is not int:
            raise AssertionError("invalid write action")
        result = action
        if action > 0:
            written = min(action, len(source))
            self.outgoing.extend(source[:written])
            result = written
        return result

    def cancel_read(self) -> None:
        self.cancel_read_calls += 1
        self.read_cancelled.set()

    def cancel_write(self) -> None:
        self.cancel_write_calls += 1
        self.write_cancelled.set()

    def close(self) -> None:
        self.close_calls += 1
        self.is_open = False
        self.read_cancelled.set()
        self.write_cancelled.set()
        self.incoming[:] = b"\x00" * len(self.incoming)
        self.outgoing[:] = b"\x00" * len(self.outgoing)

    def retained_buffers_are_zero(self) -> bool:
        return all(
            all(value == 0 for value in item)
            for item in self.retained_read_buffers + self.retained_write_buffers
        )


class _FakeFactory:
    def __init__(
        self,
        driver: _FakeOpenedDriver | None = None,
        *,
        failure: Exception | None = None,
    ) -> None:
        self.driver = driver
        self.failure = failure
        self.calls: list[dict[str, object]] = []

    def open_explicit(self, **kwargs: object) -> _FakeOpenedDriver:
        self.calls.append(dict(kwargs))
        if self.failure is not None:
            raise self.failure
        if self.driver is None:
            raise AssertionError("fake factory has no driver")
        return self.driver

    def __bool__(self) -> bool:
        return True


class _FalseyFactory(_FakeFactory):
    def __bool__(self) -> bool:
        return False


class _FalseyRegistry(os_serial.OsSerialConnectionRegistry):
    def __bool__(self) -> bool:
        return False


class _FailingMarkOpenRegistry(os_serial.OsSerialConnectionRegistry):
    def mark_open(self, connection_id: str) -> None:
        del connection_id
        raise RuntimeError("raw registry detail for COM-PRIVATE")


class _ExplodingCancelLookupDriver(_FakeOpenedDriver):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.explode_cancel_lookup = False

    def __getattribute__(self, name: str) -> object:
        if name in {"cancel_read", "cancel_write"}:
            exploding = object.__getattribute__(self, "explode_cancel_lookup")
            if exploding:
                raise RuntimeError("raw cancel property detail for COM-PRIVATE")
        return super().__getattribute__(name)


def _config(
    connection_id: str = "call020k-connection-001",
    *,
    port_name: str = "COM-EXPLICIT-CALL020K",
    enabled: bool = True,
) -> os_serial.ExplicitOsSerialConfig:
    return os_serial.ExplicitOsSerialConfig(
        port_name=port_name,
        connection_id=connection_id,
        enabled=enabled,
    )


def _open(
    *,
    config: os_serial.ExplicitOsSerialConfig | None = None,
    driver: _FakeOpenedDriver | None = None,
    factory: _FakeFactory | None = None,
    registry: os_serial.OsSerialConnectionRegistry | None = None,
) -> tuple[
    os_serial.ExplicitOsSerialConnection,
    _FakeOpenedDriver,
    _FakeFactory,
    os_serial.OsSerialConnectionRegistry,
]:
    actual_config = config or _config()
    actual_driver = driver or _FakeOpenedDriver(port=actual_config.port_name)
    actual_factory = factory or _FakeFactory(actual_driver)
    actual_registry = registry or os_serial.OsSerialConnectionRegistry()
    wrapper = os_serial.ExplicitOsSerialConnection.open_explicit(
        actual_config,
        factory=actual_factory,
        registry=actual_registry,
    )
    return wrapper, actual_driver, actual_factory, actual_registry


def _wire(direction: str, sequence: int = 0) -> bytearray:
    config = media_io.MediaIoConfig(identity=IDENTITY, frame_count=2, max_cycles=2)
    frame = media_io._make_frame(config, direction, sequence)
    try:
        return media_io.FrameCodec.encode(frame)
    finally:
        frame.dispose()


def _contains_binary(value: object) -> bool:
    if isinstance(value, (bytes, bytearray, memoryview)):
        return True
    if isinstance(value, dict):
        return any(_contains_binary(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_binary(item) for item in value)
    return False


class EgoCallOsSerialWrapperTests(unittest.TestCase):
    def test_default_disabled_and_invalid_config_never_call_factory(self) -> None:
        cases = (
            (_config(enabled=False), "os_serial_wrapper_disabled"),
            (_config(port_name="COM*"), "explicit_os_serial_config_invalid"),
            (_config(port_name="loop://fake"), "explicit_os_serial_config_invalid"),
            (
                replace(_config(), exclusive=False),
                "explicit_os_serial_config_invalid",
            ),
        )
        for config, reason in cases:
            with self.subTest(reason=reason, port=config.port_name):
                factory = _FakeFactory(
                    _FakeOpenedDriver(port="should-never-open")
                )
                with self.assertRaises(os_serial.OsSerialAdmissionError) as raised:
                    os_serial.ExplicitOsSerialConnection.open_explicit(
                        config,
                        factory=factory,
                        registry=os_serial.OsSerialConnectionRegistry(),
                    )
                self.assertEqual(raised.exception.reason_code, reason)
                self.assertEqual(factory.calls, [])
                self.assertFalse(raised.exception.metadata["factory_called"])
                self.assertIsNone(raised.exception.__cause__)
                self.assertNotIn(config.port_name, repr(raised.exception))

    def test_falsey_injected_factory_and_registry_are_used_exactly(self) -> None:
        config = _config(connection_id="call020k-falsey-injected")
        driver = _FakeOpenedDriver(port=config.port_name)
        factory = _FalseyFactory(driver)
        registry = _FalseyRegistry()

        wrapper = os_serial.ExplicitOsSerialConnection.open_explicit(
            config,
            factory=factory,
            registry=registry,
        )

        self.assertEqual(len(factory.calls), 1)
        self.assertEqual(registry.audit()["state_counts"]["open"], 1)
        wrapper.close()

    def test_exact_port_baud_timeouts_and_exclusive_are_passed_to_factory(self) -> None:
        config = replace(
            _config(port_name="COM77", connection_id="call020k-exact-open"),
            baudrate=921_600,
            read_timeout_ms=17,
            write_timeout_ms=19,
        )
        driver = _FakeOpenedDriver(
            port=config.port_name,
            baudrate=config.baudrate,
            timeout=0.017,
            write_timeout=0.019,
        )
        wrapper, _, factory, registry = _open(config=config, driver=driver)

        self.assertEqual(
            factory.calls,
            [
                {
                    "port_name": "COM77",
                    "baudrate": 921_600,
                    "read_timeout_ms": 17,
                    "write_timeout_ms": 19,
                    "exclusive": True,
                }
            ],
        )
        self.assertEqual(wrapper.connection_id, "call020k-exact-open")
        self.assertEqual(registry.audit()["state_counts"]["open"], 1)
        self.assertEqual(driver.open_calls, 0)
        self.assertTrue(wrapper.audit()["driver_ownership_transferred"])
        self.assertFalse(wrapper.audit()["wrapper_reopens_driver"])
        wrapper.close()

    def test_lazy_pyserial_is_optional_and_dependency_failure_is_explicit(self) -> None:
        config = _config(connection_id="call020k-no-pyserial")
        registry = os_serial.OsSerialConnectionRegistry()
        with mock.patch(
            "pc_simulator.ego_call_os_serial_wrapper.importlib.import_module",
            side_effect=ModuleNotFoundError("serial"),
        ):
            with self.assertRaises(os_serial.OsSerialAdmissionError) as raised:
                os_serial.ExplicitOsSerialConnection.open_explicit(
                    config,
                    registry=registry,
                )
        self.assertEqual(
            raised.exception.reason_code, "pyserial_dependency_unavailable"
        )
        self.assertTrue(raised.exception.metadata["factory_called"])
        self.assertIsNone(raised.exception.__cause__)
        self.assertEqual(registry.audit()["state_counts"]["failed"], 1)

    def test_lazy_pyserial_factory_configures_then_explicitly_opens_fake_module(self) -> None:
        driver = _FakeOpenedDriver(port="", is_open=False)
        fake_module = type("FakeSerialModule", (), {"Serial": lambda self=None: driver})()
        factory = os_serial.LazyPySerialFactory()
        with mock.patch(
            "pc_simulator.ego_call_os_serial_wrapper.importlib.import_module",
            return_value=fake_module,
        ) as import_module:
            result = factory.open_explicit(
                port_name="COM88",
                baudrate=460_800,
                read_timeout_ms=11,
                write_timeout_ms=13,
                exclusive=True,
            )

        self.assertIs(result, driver)
        self.assertEqual(import_module.call_args.args, ("serial",))
        self.assertEqual(driver.port, "COM88")
        self.assertEqual(driver.baudrate, 460_800)
        self.assertEqual(driver.timeout, 0.011)
        self.assertEqual(driver.write_timeout, 0.013)
        self.assertTrue(driver.exclusive)
        self.assertTrue(driver.is_open)
        self.assertEqual(driver.open_calls, 1)
        driver.close()

    def test_lazy_pyserial_open_failure_closes_partial_driver_and_redacts_error(self) -> None:
        driver = _FakeOpenedDriver(port="", is_open=False)

        def fail_open() -> None:
            driver.open_calls += 1
            raise RuntimeError("raw open failure for COM-PRIVATE")

        driver.open = fail_open  # type: ignore[method-assign]
        fake_module = type("FakeSerialModule", (), {"Serial": lambda self=None: driver})()
        factory = os_serial.LazyPySerialFactory()
        with mock.patch(
            "pc_simulator.ego_call_os_serial_wrapper.importlib.import_module",
            return_value=fake_module,
        ):
            with self.assertRaises(os_serial.OsSerialFactoryError) as raised:
                factory.open_explicit(
                    port_name="COM98",
                    baudrate=115_200,
                    read_timeout_ms=20,
                    write_timeout_ms=20,
                    exclusive=True,
                )

        self.assertEqual((driver.open_calls, driver.close_calls), (1, 1))
        self.assertIsNone(raised.exception.__cause__)
        self.assertNotIn("raw open failure", repr(raised.exception))
        self.assertNotIn("COM-PRIVATE", repr(raised.exception))

    def test_invalid_returned_driver_is_cancelled_closed_and_registry_released(self) -> None:
        config = _config(connection_id="call020k-invalid-driver")
        invalid = _FakeOpenedDriver(port="WRONG-PORT")
        factory = _FakeFactory(invalid)
        registry = os_serial.OsSerialConnectionRegistry()

        with self.assertRaises(os_serial.OsSerialAdmissionError) as raised:
            os_serial.ExplicitOsSerialConnection.open_explicit(
                config, factory=factory, registry=registry
            )

        self.assertEqual(raised.exception.reason_code, "opened_serial_driver_invalid")
        self.assertEqual(
            (invalid.cancel_read_calls, invalid.cancel_write_calls, invalid.close_calls),
            (1, 1, 1),
        )
        audit = registry.audit()
        self.assertEqual(audit["active_port_count"], 0)
        self.assertEqual(audit["state_counts"]["failed"], 1)

    def test_factory_failure_releases_port_but_consumes_connection_identity(self) -> None:
        config = _config(connection_id="call020k-failed-open")
        registry = os_serial.OsSerialConnectionRegistry()
        failing = _FakeFactory(failure=RuntimeError("raw port detail"))
        with self.assertRaises(os_serial.OsSerialAdmissionError) as first:
            os_serial.ExplicitOsSerialConnection.open_explicit(
                config, factory=failing, registry=registry
            )
        self.assertEqual(first.exception.reason_code, "explicit_serial_open_failed")
        self.assertNotIn("raw port detail", str(first.exception))
        self.assertIsNone(first.exception.__cause__)
        self.assertNotIn("raw port detail", repr(first.exception))
        self.assertNotIn(config.port_name, repr(first.exception))
        self.assertEqual(registry.audit()["active_port_count"], 0)

        valid_factory = _FakeFactory(_FakeOpenedDriver(port=config.port_name))
        with self.assertRaises(os_serial.OsSerialAdmissionError) as reused:
            os_serial.ExplicitOsSerialConnection.open_explicit(
                config, factory=valid_factory, registry=registry
            )
        self.assertEqual(
            reused.exception.reason_code, "serial_connection_identity_reused"
        )
        self.assertEqual(valid_factory.calls, [])

    def test_mark_open_failure_closes_driver_releases_port_and_is_redacted(self) -> None:
        config = _config(connection_id="call020k-mark-open-failure")
        driver = _FakeOpenedDriver(port=config.port_name)
        registry = _FailingMarkOpenRegistry()

        with self.assertRaises(os_serial.OsSerialAdmissionError) as raised:
            os_serial.ExplicitOsSerialConnection.open_explicit(
                config,
                factory=_FakeFactory(driver),
                registry=registry,
            )

        self.assertEqual(
            raised.exception.reason_code, "serial_registry_open_transition_failed"
        )
        self.assertIsNone(raised.exception.__cause__)
        self.assertNotIn("raw registry detail", repr(raised.exception))
        self.assertNotIn(config.port_name, repr(raised.exception))
        self.assertEqual(
            (driver.cancel_read_calls, driver.cancel_write_calls, driver.close_calls),
            (1, 1, 1),
        )
        audit = registry.audit()
        self.assertEqual(audit["active_port_count"], 0)
        self.assertEqual(audit["state_counts"]["failed"], 1)

    def test_cancel_callback_property_failure_does_not_bypass_close_cleanup(self) -> None:
        config = _config(connection_id="call020k-cancel-lookup-failure")
        driver = _ExplodingCancelLookupDriver(port=config.port_name)
        wrapper, _, _, registry = _open(config=config, driver=driver)
        driver.explode_cancel_lookup = True

        wrapper.close()

        self.assertEqual(driver.close_calls, 1)
        self.assertEqual(wrapper.audit()["cancel_errors"], 2)
        self.assertTrue(wrapper.audit()["driver_reference_cleared"])
        self.assertEqual(registry.audit()["active_port_count"], 0)

    def test_one_process_port_owner_and_reconnect_requires_new_identity(self) -> None:
        registry = os_serial.OsSerialConnectionRegistry()
        first_config = _config(connection_id="call020k-owner-one", port_name="COM91")
        first, _, _, _ = _open(config=first_config, registry=registry)
        second_config = _config(connection_id="call020k-owner-two", port_name="COM91")
        blocked_factory = _FakeFactory(_FakeOpenedDriver(port="COM91"))
        with self.assertRaises(os_serial.OsSerialAdmissionError) as blocked:
            os_serial.ExplicitOsSerialConnection.open_explicit(
                second_config,
                factory=blocked_factory,
                registry=registry,
            )
        self.assertEqual(
            blocked.exception.reason_code, "serial_port_already_owned_in_process"
        )
        self.assertEqual(blocked_factory.calls, [])

        first.close()
        second, _, _, _ = _open(config=second_config, registry=registry)
        second.close()
        with self.assertRaises(os_serial.OsSerialAdmissionError) as old_identity:
            os_serial.ExplicitOsSerialConnection.open_explicit(
                first_config,
                factory=_FakeFactory(_FakeOpenedDriver(port="COM91")),
                registry=registry,
            )
        self.assertEqual(
            old_identity.exception.reason_code, "serial_connection_identity_reused"
        )

    def test_short_read_write_and_per_call_timeouts_pass_losslessly(self) -> None:
        driver = _FakeOpenedDriver(
            port="COM-EXPLICIT-CALL020K",
            incoming=bytearray(b"abcdef"),
            read_actions=[2],
            write_actions=[3],
        )
        wrapper, _, _, _ = _open(driver=driver)
        target = bytearray(6)
        source = bytearray(b"uvwxyz")

        read_count = wrapper.readinto(memoryview(target), timeout_ms=7)
        write_count = wrapper.write(memoryview(source), timeout_ms=9)

        self.assertEqual((read_count, write_count), (2, 3))
        self.assertEqual(target[:2], b"ab")
        self.assertEqual(driver.outgoing, bytearray(b"uvw"))
        self.assertEqual(driver.read_timeout_values, [0.007])
        self.assertEqual(driver.write_timeout_values, [0.009])
        media_io._zero(target)
        media_io._zero(source)
        wrapper.close()

    def test_timeout_progress_mapping_is_fail_closed(self) -> None:
        cases = (
            (
                "read-zero",
                "read",
                os_serial.DriverIoTimeout("zero", progress=0),
                0,
                False,
            ),
            (
                "read-unknown",
                "read",
                os_serial.DriverIoTimeout("unknown", progress=None),
                None,
                True,
            ),
            (
                "read-partial",
                "read",
                os_serial.DriverIoTimeout("partial", progress=2),
                2,
                True,
            ),
            (
                "read-plain-unknown",
                "read",
                TimeoutError("unknown"),
                None,
                True,
            ),
            (
                "write-zero",
                "write",
                os_serial.DriverIoTimeout("zero", progress=0),
                0,
                False,
            ),
            (
                "write-unknown",
                "write",
                TimeoutError("unknown"),
                None,
                True,
            ),
            (
                "write-partial",
                "write",
                os_serial.DriverIoTimeout("partial", progress=3),
                3,
                True,
            ),
        )
        for label, direction, action, progress, terminal in cases:
            with self.subTest(label=label):
                driver = _FakeOpenedDriver(
                    port="COM-EXPLICIT-CALL020K",
                    read_actions=[action] if direction == "read" else None,
                    write_actions=[action] if direction == "write" else None,
                )
                wrapper, _, _, _ = _open(
                    config=_config(connection_id=f"call020k-{label}"),
                    driver=driver,
                )
                buffer = bytearray(b"abcdef")
                with self.assertRaises(serial_adapter.InjectedSerialTimeout) as raised:
                    if direction == "read":
                        wrapper.readinto(memoryview(buffer), timeout_ms=5)
                    else:
                        wrapper.write(memoryview(buffer), timeout_ms=5)
                self.assertEqual(raised.exception.progress, progress)
                self.assertEqual(wrapper.audit()["state"], "terminal" if terminal else "open")
                media_io._zero(buffer)
                wrapper.close()

    def test_observable_driver_identity_or_configuration_change_is_terminal(self) -> None:
        mutations = (
            ("port", "COM-REPLACED"),
            ("is_open", False),
            ("baudrate", 9_600),
            ("exclusive", False),
        )
        for index, (attribute, value) in enumerate(mutations):
            with self.subTest(attribute=attribute):
                wrapper, driver, _, _ = _open(
                    config=_config(connection_id=f"call020k-mutation-{index}")
                )
                setattr(driver, attribute, value)
                target = bytearray(8)
                with self.assertRaises(media_io.MediaIoProtocolError):
                    wrapper.readinto(memoryview(target), timeout_ms=5)
                self.assertEqual(driver.read_calls, 0)
                self.assertEqual(wrapper.audit()["state"], "terminal")
                media_io._zero(target)
                wrapper.close()

    def test_multibyte_and_readonly_views_reject_before_driver_io(self) -> None:
        wrapper, driver, _, _ = _open(
            config=_config(connection_id="call020k-bad-view")
        )
        multibyte = memoryview(array("I", [1] * 2_000))
        readonly = memoryview(b"readonly")
        with self.assertRaises(media_io.MediaIoError):
            wrapper.write(multibyte, timeout_ms=5)
        with self.assertRaises(media_io.MediaIoError):
            wrapper.readinto(readonly, timeout_ms=5)
        self.assertEqual(driver.read_calls + driver.write_calls, 0)
        multibyte.release()
        readonly.release()
        wrapper.close()

    def test_close_cancels_blocking_directions_waits_and_clears_references(self) -> None:
        driver = _FakeOpenedDriver(
            port="COM-EXPLICIT-CALL020K",
            read_actions=["block"],
            write_actions=["block"],
        )
        wrapper, _, _, registry = _open(
            config=_config(connection_id="call020k-blocking-close"),
            driver=driver,
        )
        read_buffer = bytearray(16)
        write_buffer = bytearray(b"bounded-write")
        failures: list[Exception] = []

        def read() -> None:
            try:
                wrapper.readinto(memoryview(read_buffer), timeout_ms=20)
            except Exception as error:
                failures.append(error)

        def write() -> None:
            try:
                wrapper.write(memoryview(write_buffer), timeout_ms=20)
            except Exception as error:
                failures.append(error)

        read_thread = threading.Thread(target=read)
        write_thread = threading.Thread(target=write)
        read_thread.start()
        write_thread.start()
        self.assertTrue(driver.read_entered.wait(1.0))
        self.assertTrue(driver.write_entered.wait(1.0))

        wrapper.close()

        read_thread.join(1.0)
        write_thread.join(1.0)
        self.assertFalse(read_thread.is_alive())
        self.assertFalse(write_thread.is_alive())
        self.assertEqual(len(failures), 2)
        self.assertEqual(
            (
                driver.cancel_read_calls,
                driver.cancel_write_calls,
                driver.close_calls,
            ),
            (1, 1, 1),
        )
        audit = wrapper.audit()
        self.assertTrue(audit["driver_reference_cleared"])
        self.assertTrue(audit["config_and_connection_references_cleared"])
        self.assertEqual(registry.audit()["active_port_count"], 0)
        with self.assertRaises(media_io.MediaIoError):
            _ = wrapper.connection_id
        media_io._zero(read_buffer)
        media_io._zero(write_buffer)

    def test_h_resynchronizes_rom_prefix_over_explicit_wrapper(self) -> None:
        uplink = _wire("uplink")
        downlink = _wire("downlink")
        incoming = bytearray(b"ESP-ROM:boot\r\n")
        incoming.extend(uplink)
        media_io._zero(uplink)
        driver = _FakeOpenedDriver(
            port="COM-EXPLICIT-CALL020K",
            incoming=incoming,
            read_actions=[3, 2, 17],
            write_actions=[5, 11],
        )
        wrapper, _, _, _ = _open(
            config=_config(connection_id="call020k-h-resync"),
            driver=driver,
        )
        host_stream = serial_adapter.HostSerialOrderedByteStream(
            wrapper,
            IDENTITY,
            config=serial_adapter.HostSerialAdapterConfig(
                per_call_timeout_ms=20,
                max_operation_timeout_ms=1_000,
            ),
        )
        endpoint = media_io.FramedEndpoint(
            host_stream,
            IDENTITY,
            inbound_direction="uplink",
            outbound_direction="downlink",
        )

        received, _ = endpoint.receive(timeout_steps=50, attempts=1)
        self.assertEqual(received.direction, "uplink")
        received.dispose()
        outbound = media_io._make_frame(
            media_io.MediaIoConfig(identity=IDENTITY), "downlink", 0
        )
        endpoint.send(outbound, timeout_steps=50, attempts=1)
        self.assertEqual(driver.outgoing, downlink)
        media_io._zero(downlink)
        host_stream.close()
        wrapper.close()
        self.assertTrue(driver.retained_buffers_are_zero())

    def test_audit_registry_and_errors_are_metadata_only_and_redacted(self) -> None:
        config = _config(
            connection_id="call020k-private-connection",
            port_name="COM-PRIVATE-97",
        )
        wrapper, _, _, registry = _open(config=config)
        values = (wrapper.audit(), registry.audit())
        serialized = json.dumps(values, sort_keys=True, allow_nan=False)
        self.assertFalse(_contains_binary(values))
        self.assertNotIn(config.port_name, serialized)
        self.assertNotIn(config.connection_id, serialized)
        self.assertFalse(wrapper.audit()["media_logged"])
        self.assertFalse(wrapper.audit()["media_persisted"])
        self.assertFalse(wrapper.audit()["in_band_control_emitted"])
        wrapper.close()

    def test_module_has_no_enumeration_guess_autorun_required_import_or_media_log(self) -> None:
        source = Path("pc_simulator/ego_call_os_serial_wrapper.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("import serial", source)
        self.assertNotIn("serial.tools", source)
        self.assertNotIn("list_ports", source)
        self.assertNotIn("comports", source)
        self.assertNotIn("glob(", source)
        self.assertNotIn("wmic", source.lower())
        self.assertNotIn("def main(", source)
        self.assertNotIn("logging", source)
        self.assertNotIn("open(\"COM", source)
        self.assertIn("enabled: bool = False", source)
        self.assertIn('importlib.import_module("serial")', source)
        self.assertIn("port_enumerated_or_guessed", source)
        self.assertIn("rom_prefix_resynchronization_owner", source)


if __name__ == "__main__":
    unittest.main()

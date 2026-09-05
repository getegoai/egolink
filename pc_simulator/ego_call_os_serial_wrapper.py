"""CALL-020K explicit, default-off OS serial wrapper for CALL-020H.

The caller must provide one exact port name and connection identity.  This
module never enumerates, guesses, probes, or automatically opens a port.  A
caller-injected factory is preferred for tests.  The optional real factory
lazy-imports ``pyserial`` only after explicit enable/open; dependency absence is
a clear fail-closed result and never triggers installation or environment
changes.

On successful admission, ownership of the returned driver object transfers
fully to :class:`ExplicitOsSerialConnection`; the caller must not mutate,
close, or reopen it. A phase connector may deliberately return a borrowed
facade whose ``close`` gives the same underlying handle back to its lease
owner. K does not claim that its close physically closes such an underlying
OS handle. The wrapper itself never reopens a driver. One reader and one
writer may operate concurrently.  Close requests out-of-band read/write
cancellation, waits for both direction locks, closes the driver, releases the
process-local port owner, and clears adapter references.  It cannot preempt a
driver that violates its timeout/cancel contract.  A close/reopen performed
behind the wrapper between observations cannot be detected generically and is
therefore an explicit injected-driver trust boundary.  ROM-prefix/EGLM
resynchronization remains exclusively in CALL-020H; this layer never emits
in-band control, logs media, or persists media.
"""

from __future__ import annotations

import importlib
import math
import threading
from dataclasses import dataclass
from typing import Any, Protocol

from pc_simulator.ego_call_media_io import (
    MediaIoError,
    MediaIoProtocolError,
    _identifier,
)
from pc_simulator.ego_call_serial_adapter import InjectedSerialTimeout


OS_SERIAL_WRAPPER_VERSION = "egolink.ego_call_os_serial_wrapper.v0.1"
DEFAULT_BAUDRATE = 115_200
MAX_IO_BYTES = 4_096


class OpenedSerialDriver(Protocol):
    port: str
    baudrate: int
    timeout: float | None
    write_timeout: float | None
    exclusive: bool | None
    is_open: bool

    def readinto(self, target: memoryview) -> int: ...

    def write(self, source: memoryview) -> int: ...

    def cancel_read(self) -> None: ...

    def cancel_write(self) -> None: ...

    def close(self) -> None: ...


class ExplicitSerialFactory(Protocol):
    def open_explicit(
        self,
        *,
        port_name: str,
        baudrate: int,
        read_timeout_ms: int,
        write_timeout_ms: int,
        exclusive: bool,
    ) -> OpenedSerialDriver: ...


class OsSerialDependencyUnavailable(MediaIoError):
    """The optional pyserial module is not installed in this environment."""


class OsSerialFactoryError(MediaIoError):
    """The explicit serial factory failed without exposing its raw message."""


class DriverIoTimeout(TimeoutError):
    """Optional precise progress report from an injected serial driver."""

    def __init__(self, message: str, *, progress: int | None):
        super().__init__(message)
        if progress is not None and (type(progress) is not int or progress < 0):
            raise ValueError("driver timeout progress must be a non-negative int or None")
        self.progress = progress


@dataclass(frozen=True)
class ExplicitOsSerialConfig:
    """Exact caller choice and finite bounds; opening is disabled by default."""

    port_name: str
    connection_id: str
    enabled: bool = False
    baudrate: int = DEFAULT_BAUDRATE
    read_timeout_ms: int = 20
    write_timeout_ms: int = 20
    max_io_bytes: int = MAX_IO_BYTES
    exclusive: bool = True

    def validate(self) -> None:
        if type(self.enabled) is not bool:
            raise MediaIoError("enabled must be an explicit boolean")
        _exact_port_name(self.port_name)
        _identifier(self.connection_id, label="serial connection_id")
        _bounded_int(
            self.baudrate,
            label="baudrate",
            minimum=1_200,
            maximum=4_000_000,
        )
        _bounded_int(
            self.read_timeout_ms,
            label="read_timeout_ms",
            minimum=1,
            maximum=1_000,
        )
        _bounded_int(
            self.write_timeout_ms,
            label="write_timeout_ms",
            minimum=1,
            maximum=1_000,
        )
        _bounded_int(
            self.max_io_bytes,
            label="max_io_bytes",
            minimum=1,
            maximum=MAX_IO_BYTES,
        )
        if self.exclusive is not True:
            raise MediaIoError("exclusive serial ownership must be explicitly true")


class OsSerialAdmissionError(MediaIoProtocolError):
    """Redacted open/admission failure; never includes a port or connection ID."""

    def __init__(
        self,
        reason_code: str,
        *,
        factory_called: bool = False,
        cancel_errors: int = 0,
        close_errors: int = 0,
        registry_errors: int = 0,
    ):
        super().__init__("explicit OS serial admission rejected")
        self.reason_code = reason_code
        self.metadata = {
            "wrapper_version": OS_SERIAL_WRAPPER_VERSION,
            "result": "FAIL",
            "stage": "os_serial_admission",
            "reason_code": reason_code,
            "factory_called": factory_called,
            "port_enumerated_or_guessed": False,
            "port_or_connection_value_exposed": False,
            "media_io_started": False,
            "cancel_errors": cancel_errors,
            "close_errors": close_errors,
            "registry_errors": registry_errors,
            "media_logged_or_persisted": False,
        }


@dataclass(frozen=True)
class _ConnectionState:
    state: str


class OsSerialConnectionRegistry:
    """Bounded process owner: active ports release, connection IDs never reuse."""

    def __init__(self, *, max_connection_ids: int = 256):
        self.max_connection_ids = _bounded_int(
            max_connection_ids,
            label="max_connection_ids",
            minimum=1,
            maximum=4_096,
        )
        self._lock = threading.Lock()
        self._connections: dict[str, _ConnectionState] = {}
        self._active_ports: dict[str, str] = {}

    def reserve(self, *, port_name: str, connection_id: str) -> None:
        with self._lock:
            if connection_id in self._connections:
                raise OsSerialAdmissionError("serial_connection_identity_reused")
            if port_name in self._active_ports:
                raise OsSerialAdmissionError("serial_port_already_owned_in_process")
            if len(self._connections) >= self.max_connection_ids:
                raise OsSerialAdmissionError("serial_connection_registry_exhausted")
            self._connections[connection_id] = _ConnectionState("reserved")
            self._active_ports[port_name] = connection_id

    def mark_open(self, connection_id: str) -> None:
        with self._lock:
            if connection_id not in self._connections:
                raise MediaIoError("serial registry reservation is missing")
            self._connections[connection_id] = _ConnectionState("open")

    def mark_terminal(self, connection_id: str, state: str) -> None:
        if state not in {"closed", "failed"}:
            raise MediaIoError("serial registry terminal state is invalid")
        with self._lock:
            if connection_id not in self._connections:
                return
            self._connections[connection_id] = _ConnectionState(state)
            for port_name, owner in tuple(self._active_ports.items()):
                if owner == connection_id:
                    del self._active_ports[port_name]

    def audit(self) -> dict[str, Any]:
        with self._lock:
            states = {"reserved": 0, "open": 0, "closed": 0, "failed": 0}
            for value in self._connections.values():
                states[value.state] += 1
            return {
                "capacity": self.max_connection_ids,
                "connection_identity_count": len(self._connections),
                "active_port_count": len(self._active_ports),
                "state_counts": states,
                "raw_connection_ids_retained_for_nonreuse": True,
                "terminal_port_names_retained": False,
                "port_or_connection_values_exposed": False,
            }


class LazyPySerialFactory:
    """Optional real explicit opener; never imported or called automatically."""

    def open_explicit(
        self,
        *,
        port_name: str,
        baudrate: int,
        read_timeout_ms: int,
        write_timeout_ms: int,
        exclusive: bool,
    ) -> OpenedSerialDriver:
        try:
            serial_module = importlib.import_module("serial")
        except (ImportError, ModuleNotFoundError):
            raise OsSerialDependencyUnavailable(
                "optional pyserial dependency is unavailable"
            ) from None
        try:
            serial_class = getattr(serial_module, "Serial", None)
        except Exception:
            raise OsSerialDependencyUnavailable(
                "optional pyserial dependency shape is unavailable"
            ) from None
        if not callable(serial_class):
            raise OsSerialDependencyUnavailable(
                "optional pyserial dependency has no Serial implementation"
            )

        driver: Any | None = None
        try:
            driver = serial_class()
            if getattr(driver, "is_open", False):
                raise OsSerialFactoryError("new pyserial instance was unexpectedly open")
            driver.port = port_name
            driver.baudrate = baudrate
            driver.timeout = read_timeout_ms / 1_000
            driver.write_timeout = write_timeout_ms / 1_000
            driver.exclusive = exclusive
            driver.open()
            return driver
        except Exception as error:
            if driver is not None:
                try:
                    driver.close()
                except Exception:
                    pass
            if isinstance(error, OsSerialFactoryError):
                raise
            raise OsSerialFactoryError("explicit pyserial open failed") from None


def _bounded_int(value: object, *, label: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise MediaIoError(f"{label} must be an integer in [{minimum}, {maximum}]")
    return value


def _exact_port_name(value: object) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 260
        or value != value.strip()
        or any(ord(character) < 0x20 for character in value)
        or any(character in value for character in "*?")
        or "://" in value
    ):
        raise MediaIoProtocolError(
            "port_name must be one exact 1-260 character non-URL OS port name"
        )
    return value


def _driver_cleanup(driver: object) -> tuple[int, int]:
    cancel_errors = 0
    close_errors = 0
    for name in ("cancel_read", "cancel_write"):
        try:
            callback = getattr(driver, name, None)
        except Exception:
            cancel_errors += 1
            continue
        if callable(callback):
            try:
                callback()
            except Exception:
                cancel_errors += 1
        else:
            cancel_errors += 1
    close_lookup_failed = False
    try:
        close = getattr(driver, "close", None)
    except Exception:
        close_errors += 1
        close_lookup_failed = True
        close = None
    if callable(close):
        try:
            close()
        except Exception:
            close_errors += 1
    elif not close_lookup_failed:
        close_errors += 1
    return cancel_errors, close_errors


def _mark_registry_terminal_safely(
    registry: OsSerialConnectionRegistry,
    connection_id: str,
) -> int:
    try:
        registry.mark_terminal(connection_id, "failed")
    except Exception:
        return 1
    return 0


def _validate_open_driver(driver: object, config: ExplicitOsSerialConfig) -> None:
    for name in ("readinto", "write", "cancel_read", "cancel_write", "close"):
        if not callable(getattr(driver, name, None)):
            raise MediaIoProtocolError("opened serial driver shape is invalid")
    if getattr(driver, "is_open", None) is not True:
        raise MediaIoProtocolError("serial driver did not report an open handle")
    if getattr(driver, "port", None) != config.port_name:
        raise MediaIoProtocolError("serial driver port identity mismatch")
    if getattr(driver, "baudrate", None) != config.baudrate:
        raise MediaIoProtocolError("serial driver baudrate mismatch")
    if getattr(driver, "exclusive", None) is not True:
        raise MediaIoProtocolError("serial driver did not report exclusive ownership")
    for attribute, expected_ms in (
        ("timeout", config.read_timeout_ms),
        ("write_timeout", config.write_timeout_ms),
    ):
        actual = getattr(driver, attribute, None)
        if (
            isinstance(actual, bool)
            or not isinstance(actual, (int, float))
            or not math.isfinite(actual)
            or not math.isclose(actual, expected_ms / 1_000, rel_tol=0, abs_tol=1e-9)
        ):
            raise MediaIoProtocolError("serial driver timeout configuration mismatch")


def _timeout_matches(value: object, expected_ms: int) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
        and math.isclose(value, expected_ms / 1_000, rel_tol=0, abs_tol=1e-9)
    )


_DEFAULT_REGISTRY = OsSerialConnectionRegistry()


class ExplicitOsSerialConnection:
    """Single-open InjectedSerial implementation consumed by CALL-020H.

    A factory owns any partially created handle until ``open_explicit`` returns
    it. On successful driver validation, ownership of that returned object
    transfers to this wrapper and no caller may mutate, close, or reopen it.
    The object may be a caller-attested borrowed facade; K invokes ``close``
    exactly as normal but cannot infer physical OS-handle closure from it.
    """

    def __init__(
        self,
        driver: OpenedSerialDriver,
        config: ExplicitOsSerialConfig,
        registry: OsSerialConnectionRegistry,
    ):
        self._read_lock = threading.RLock()
        self._write_lock = threading.RLock()
        self._close_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._driver: OpenedSerialDriver | None = driver
        self._config: ExplicitOsSerialConfig | None = config
        self._registry: OsSerialConnectionRegistry | None = registry
        self._connection_id: str | None = config.connection_id
        self._closed = False
        self._terminal = False
        self._cancel_requested = False
        self._cancel_sent = False
        self._read_calls = 0
        self._write_calls = 0
        self._read_bytes = 0
        self._written_bytes = 0
        self._cancel_errors = 0
        self._close_errors = 0
        self._registry_errors = 0
        self._references_cleared = False

    @classmethod
    def open_explicit(
        cls,
        config: ExplicitOsSerialConfig,
        *,
        factory: ExplicitSerialFactory | None = None,
        registry: OsSerialConnectionRegistry | None = None,
    ) -> "ExplicitOsSerialConnection":
        if not isinstance(config, ExplicitOsSerialConfig):
            raise OsSerialAdmissionError("explicit_os_serial_config_required")
        try:
            config.validate()
        except Exception:
            raise OsSerialAdmissionError("explicit_os_serial_config_invalid") from None
        if config.enabled is not True:
            raise OsSerialAdmissionError("os_serial_wrapper_disabled")

        selected_registry = registry if registry is not None else _DEFAULT_REGISTRY
        if not isinstance(selected_registry, OsSerialConnectionRegistry):
            raise OsSerialAdmissionError("os_serial_registry_required")
        selected_factory = factory if factory is not None else LazyPySerialFactory()
        try:
            factory_open = getattr(selected_factory, "open_explicit", None)
        except Exception:
            raise OsSerialAdmissionError("explicit_serial_factory_invalid") from None
        if not callable(factory_open):
            raise OsSerialAdmissionError("explicit_serial_factory_invalid")

        try:
            selected_registry.reserve(
                port_name=config.port_name,
                connection_id=config.connection_id,
            )
        except OsSerialAdmissionError:
            raise
        except Exception:
            registry_errors = _mark_registry_terminal_safely(
                selected_registry, config.connection_id
            )
            raise OsSerialAdmissionError(
                "serial_registry_reservation_failed",
                registry_errors=registry_errors,
            ) from None
        driver: OpenedSerialDriver | None = None
        try:
            driver = factory_open(
                port_name=config.port_name,
                baudrate=config.baudrate,
                read_timeout_ms=config.read_timeout_ms,
                write_timeout_ms=config.write_timeout_ms,
                exclusive=config.exclusive,
            )
        except OsSerialDependencyUnavailable:
            registry_errors = _mark_registry_terminal_safely(
                selected_registry, config.connection_id
            )
            raise OsSerialAdmissionError(
                "pyserial_dependency_unavailable",
                factory_called=True,
                registry_errors=registry_errors,
            ) from None
        except Exception:
            registry_errors = _mark_registry_terminal_safely(
                selected_registry, config.connection_id
            )
            raise OsSerialAdmissionError(
                "explicit_serial_open_failed",
                factory_called=True,
                registry_errors=registry_errors,
            ) from None

        try:
            _validate_open_driver(driver, config)
        except Exception:
            cancel_errors, close_errors = _driver_cleanup(driver)
            registry_errors = _mark_registry_terminal_safely(
                selected_registry, config.connection_id
            )
            raise OsSerialAdmissionError(
                "opened_serial_driver_invalid",
                factory_called=True,
                cancel_errors=cancel_errors,
                close_errors=close_errors,
                registry_errors=registry_errors,
            ) from None
        try:
            selected_registry.mark_open(config.connection_id)
        except Exception:
            cancel_errors, close_errors = _driver_cleanup(driver)
            registry_errors = _mark_registry_terminal_safely(
                selected_registry, config.connection_id
            )
            raise OsSerialAdmissionError(
                "serial_registry_open_transition_failed",
                factory_called=True,
                cancel_errors=cancel_errors,
                close_errors=close_errors,
                registry_errors=registry_errors,
            ) from None
        return cls(driver, config, selected_registry)

    @property
    def connection_id(self) -> str:
        with self._state_lock:
            connection_id = self._connection_id
        if connection_id is None:
            raise MediaIoError("serial connection identity is unavailable")
        return connection_id

    def _fail_terminal(self) -> None:
        with self._state_lock:
            self._terminal = True
        self.cancel_pending_io()

    def _active(self) -> tuple[OpenedSerialDriver, ExplicitOsSerialConfig]:
        with self._state_lock:
            driver = self._driver
            config = self._config
            closed = self._closed
            cancelled = self._cancel_requested
        if closed or cancelled or driver is None or config is None:
            raise MediaIoError("explicit OS serial connection is closed or cancelled")
        try:
            is_open = driver.is_open
            port_name = driver.port
            baudrate = driver.baudrate
            exclusive = driver.exclusive
        except Exception:
            self._fail_terminal()
            raise MediaIoError("serial driver identity query failed") from None
        if (
            is_open is not True
            or port_name != config.port_name
            or baudrate != config.baudrate
            or exclusive is not True
        ):
            self._fail_terminal()
            raise MediaIoProtocolError(
                "serial driver identity or fixed configuration changed after open"
            )
        return driver, config

    @staticmethod
    def _validate_byte_view(
        value: memoryview,
        *,
        label: str,
        maximum: int,
        writable: bool,
    ) -> None:
        if not isinstance(value, memoryview):
            raise MediaIoError(f"{label} requires a memoryview")
        if (
            value.ndim != 1
            or not value.c_contiguous
            or value.itemsize != 1
            or value.nbytes != len(value)
            or not 1 <= len(value) <= maximum
            or (writable and value.readonly)
        ):
            raise MediaIoError(f"{label} requires a bounded contiguous byte view")

    def readinto(self, target: memoryview, *, timeout_ms: int) -> int:
        with self._read_lock:
            driver, config = self._active()
            self._validate_byte_view(
                target,
                label="serial read",
                maximum=config.max_io_bytes,
                writable=True,
            )
            requested_timeout = _bounded_int(
                timeout_ms,
                label="serial read timeout_ms",
                minimum=1,
                maximum=config.read_timeout_ms,
            )
            try:
                driver.timeout = requested_timeout / 1_000
                applied_timeout = driver.timeout
            except Exception:
                self._fail_terminal()
                raise MediaIoProtocolError("serial read timeout configuration failed") from None
            if not _timeout_matches(applied_timeout, requested_timeout):
                self._fail_terminal()
                raise MediaIoProtocolError("serial read timeout was not applied exactly")
            try:
                count = driver.readinto(target)
            except DriverIoTimeout as error:
                if error.progress != 0:
                    self._fail_terminal()
                raise InjectedSerialTimeout(
                    "OS serial read timed out", progress=error.progress
                ) from None
            except TimeoutError:
                self._fail_terminal()
                raise InjectedSerialTimeout(
                    "OS serial read timed out with unknown progress", progress=None
                ) from None
            except Exception:
                self._fail_terminal()
                raise InjectedSerialTimeout(
                    "OS serial read failed with unknown progress", progress=None
                ) from None
            if type(count) is not int or not 0 <= count <= len(target):
                self._fail_terminal()
                raise MediaIoProtocolError("serial driver returned an invalid read count")
            self._active()
            with self._state_lock:
                self._read_calls += 1
                self._read_bytes += count
            return count

    def write(self, source: memoryview, *, timeout_ms: int) -> int:
        with self._write_lock:
            driver, config = self._active()
            self._validate_byte_view(
                source,
                label="serial write",
                maximum=config.max_io_bytes,
                writable=False,
            )
            requested_timeout = _bounded_int(
                timeout_ms,
                label="serial write timeout_ms",
                minimum=1,
                maximum=config.write_timeout_ms,
            )
            try:
                driver.write_timeout = requested_timeout / 1_000
                applied_timeout = driver.write_timeout
            except Exception:
                self._fail_terminal()
                raise MediaIoProtocolError("serial write timeout configuration failed") from None
            if not _timeout_matches(applied_timeout, requested_timeout):
                self._fail_terminal()
                raise MediaIoProtocolError("serial write timeout was not applied exactly")
            try:
                count = driver.write(source)
            except DriverIoTimeout as error:
                if error.progress != 0:
                    self._fail_terminal()
                raise InjectedSerialTimeout(
                    "OS serial write timed out", progress=error.progress
                ) from None
            except TimeoutError:
                self._fail_terminal()
                raise InjectedSerialTimeout(
                    "OS serial write timed out with unknown progress", progress=None
                ) from None
            except Exception:
                self._fail_terminal()
                raise InjectedSerialTimeout(
                    "OS serial write failed with unknown progress", progress=None
                ) from None
            if type(count) is not int or not 0 <= count <= len(source):
                self._fail_terminal()
                raise MediaIoProtocolError("serial driver returned an invalid write count")
            self._active()
            with self._state_lock:
                self._write_calls += 1
                self._written_bytes += count
            return count

    def cancel_pending_io(self) -> None:
        with self._state_lock:
            self._cancel_requested = True
            if self._cancel_sent:
                return
            self._cancel_sent = True
            driver = self._driver
        if driver is None:
            return
        errors = 0
        for name in ("cancel_read", "cancel_write"):
            try:
                callback = getattr(driver, name, None)
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
        if errors:
            with self._state_lock:
                self._cancel_errors += errors

    def close(self) -> None:
        with self._close_lock:
            with self._state_lock:
                self._closed = True
            self.cancel_pending_io()
            with self._read_lock, self._write_lock:
                with self._state_lock:
                    driver = self._driver
                    registry = self._registry
                    connection_id = self._connection_id
                    terminal = self._terminal
                    self._driver = None
                    self._config = None
                    self._registry = None
                    self._connection_id = None
                    self._references_cleared = True
                if driver is not None:
                    try:
                        close_driver = getattr(driver, "close", None)
                        if not callable(close_driver):
                            raise MediaIoError("serial driver close callback is unavailable")
                        close_driver()
                    except Exception:
                        with self._state_lock:
                            self._close_errors += 1
                if registry is not None and connection_id is not None:
                    try:
                        registry.mark_terminal(
                            connection_id, "failed" if terminal else "closed"
                        )
                    except Exception:
                        with self._state_lock:
                            self._registry_errors += 1

    def audit(self) -> dict[str, Any]:
        with self._state_lock:
            return {
                "wrapper_version": OS_SERIAL_WRAPPER_VERSION,
                "state": (
                    "terminal"
                    if self._terminal
                    else "closed"
                    if self._closed
                    else "cancelled"
                    if self._cancel_requested
                    else "open"
                ),
                "explicit_port_required": True,
                "port_enumerated_or_guessed": False,
                "read_calls": self._read_calls,
                "write_calls": self._write_calls,
                "read_bytes": self._read_bytes,
                "written_bytes": self._written_bytes,
                "cancel_requested": self._cancel_requested,
                "cancel_errors": self._cancel_errors,
                "close_errors": self._close_errors,
                "registry_errors": self._registry_errors,
                "single_process_port_owner": True,
                "driver_reported_exclusive": True,
                "os_exclusivity_runtime_verified": False,
                "driver_ownership_transferred": True,
                "ownership_scope": "RETURNED_DRIVER_OBJECT",
                "borrowed_driver_facade_supported": True,
                "physical_os_handle_close_proven_by_wrapper": False,
                "wrapper_reopens_driver": False,
                "external_close_reopen_between_observations_detectable": False,
                "adapter_owned_media_or_wire_buffers": 0,
                "external_driver_buffer_copies_controlled": False,
                "driver_reference_cleared": self._driver is None,
                "config_and_connection_references_cleared": self._references_cleared,
                "port_or_connection_value_exposed": False,
                "in_band_control_emitted": False,
                "rom_prefix_resynchronization_owner": "CALL-020H",
                "media_logged": False,
                "media_persisted": False,
                "pyserial_import": "optional_lazy_only",
            }


__all__ = [
    "DEFAULT_BAUDRATE",
    "DriverIoTimeout",
    "ExplicitOsSerialConfig",
    "ExplicitOsSerialConnection",
    "ExplicitSerialFactory",
    "LazyPySerialFactory",
    "MAX_IO_BYTES",
    "OS_SERIAL_WRAPPER_VERSION",
    "OpenedSerialDriver",
    "OsSerialAdmissionError",
    "OsSerialConnectionRegistry",
    "OsSerialDependencyUnavailable",
    "OsSerialFactoryError",
]

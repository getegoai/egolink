"""Pure-standard-library Location Engine v0 admission and projection core.

This module is intentionally isolated from the live Message Hub.  It validates
accepted Location Engine states and the exact Sensor Policy configuration
identity before retaining an in-memory timeline.  Server receive time is kept
as transport evidence only; device current state is selected exclusively by
boot-scoped source-event ordering.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping

from pc_simulator.sensor_policy_v0 import (
    CONFIG_CONTRACT_VERSION,
    SEMANTIC_VALIDATION_VERSION,
    SensorPolicyConfig,
    SensorPolicyError,
    canonical_json_bytes,
    load_sensor_policy_config,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SENSOR_POLICY_CONFIG = (
    REPOSITORY_ROOT / "shared" / "config" / "sensor_policy_v0.json"
)

LOCATION_STATE_CONTRACT_VERSION = "egolink.location_engine.v0.1"
LOCATION_STATE_ENVELOPE_CONTRACT_VERSION = "egolink.location_state_envelope.v0.1"
UTC_EVENT_TIME_SOURCES = frozenset({"timestamp_utc_ns", "gnss_source_utc_ns"})
MONOTONIC_EVENT_TIME_SOURCE = "timestamp_monotonic_ns"
EVENT_TIME_SOURCES = UTC_EVENT_TIME_SOURCES | {MONOTONIC_EVENT_TIME_SOURCE}
OUTBOX_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$")


class LocationStateMirrorError(ValueError):
    """Base class for rejected mirror input."""


class LocationStateValidationError(LocationStateMirrorError):
    """Raised when an envelope, state, clock or policy identity is invalid."""


class LocationStateRegressionError(LocationStateMirrorError):
    """Raised when an older source event attempts to replace device current."""


class LocationStateConflictError(LocationStateMirrorError):
    """Raised when an immutable identity is reused for different content."""


@dataclass(frozen=True)
class LocationStateIdentity:
    """Immutable identity and ordering tuple for one device-derived state."""

    device_id: str
    boot_count: int
    session_id: str
    event_time_ms: int
    sequence_id: int
    observation_id: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "boot_count": self.boot_count,
            "session_id": self.session_id,
            "event_time_ms": self.event_time_ms,
            "sequence_id": self.sequence_id,
            "observation_id": self.observation_id,
        }


@dataclass(frozen=True)
class _ClockIdentity:
    source: str
    event_time_ns: int
    monotonic_clock_domain_id: str | None

    @property
    def comparison_domain(self) -> tuple[str, str | None]:
        if self.source in UTC_EVENT_TIME_SOURCES:
            return ("utc", None)
        return ("boot_monotonic", self.monotonic_clock_domain_id)

    def scoped_comparison_domain(
        self, boot_count: int
    ) -> tuple[str, int | None, str | None]:
        if self.source in UTC_EVENT_TIME_SOURCES:
            return ("utc", None, None)
        return ("boot_monotonic", boot_count, self.monotonic_clock_domain_id)

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_time_source": self.source,
            "event_time_ns": self.event_time_ns,
            "monotonic_clock_domain_id": self.monotonic_clock_domain_id,
        }


@dataclass
class _MirrorRecord:
    identity: LocationStateIdentity
    clock: _ClockIdentity
    policy_identity: dict[str, str]
    location_state: dict[str, Any]
    server_receive_time_ms: int | None
    content_hash: str

    def copy_for_inspection(self) -> dict[str, Any]:
        return {
            "identity": self.identity.as_dict(),
            "event_clock": self.clock.as_dict(),
            "policy_identity": deepcopy(self.policy_identity),
            "location_state": deepcopy(self.location_state),
            "server_receive_time_ms": self.server_receive_time_ms,
            "content_hash": self.content_hash,
        }


def _bounded_id(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 256:
        raise LocationStateValidationError(
            f"{name} must be a 1-256 character string"
        )
    return value


def _outbox_safe_id(value: Any, name: str) -> str:
    if not isinstance(value, str) or not OUTBOX_SAFE_ID.fullmatch(value):
        raise LocationStateValidationError(
            f"{name} must be a 1-128 character outbox-safe identifier"
        )
    return value


def _non_negative_integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise LocationStateValidationError(
            f"{name} must be a non-negative integer"
        )
    return value


def _positive_integer(value: Any, name: str) -> int:
    result = _non_negative_integer(value, name)
    if result == 0:
        raise LocationStateValidationError(f"{name} must be greater than zero")
    return result


def _exact_keys(
    value: Mapping[str, Any],
    *,
    required: set[str],
    optional: set[str] | None = None,
    name: str,
) -> None:
    allowed = required | (optional or set())
    missing = sorted(required - set(value))
    extra = sorted(set(value) - allowed)
    if missing or extra:
        raise LocationStateValidationError(
            f"{name} keys mismatch; missing={missing or []}, extra={extra or []}"
        )


def _clock_identity(
    value: Mapping[str, Any], *, event_time_ms: int, name: str
) -> _ClockIdentity:
    source = value.get("event_time_source")
    if source not in EVENT_TIME_SOURCES:
        raise LocationStateValidationError(f"{name}.event_time_source is unsupported")
    event_time_ns = _non_negative_integer(
        value.get("event_time_ns"), f"{name}.event_time_ns"
    )
    if event_time_ns // 1_000_000 != event_time_ms:
        raise LocationStateValidationError(
            f"{name}.event_time_ns does not bind to event_time_ms"
        )
    domain = value.get("monotonic_clock_domain_id")
    if source == MONOTONIC_EVENT_TIME_SOURCE:
        domain = _bounded_id(domain, f"{name}.monotonic_clock_domain_id")
    elif domain is not None:
        raise LocationStateValidationError(
            f"{name}.monotonic_clock_domain_id must be null for UTC time"
        )
    return _ClockIdentity(str(source), event_time_ns, domain)


class LocationStateRuntimeMirror:
    """Validate, order and project device Location Engine state.

    Persistence, live Message Hub wiring and authorization are deliberately
    outside this first LOC-021 slice.
    """

    _ENVELOPE_REQUIRED = {
        "envelope_contract_version",
        "device_id",
        "boot_count",
        "session_id",
        "event_time_ms",
        "event_time_source",
        "event_time_ns",
        "monotonic_clock_domain_id",
        "sequence_id",
        "observation_id",
        "policy_identity",
        "location_state",
    }
    _ENVELOPE_OPTIONAL = {"server_receive_time_ms"}
    _POLICY_IDENTITY_KEYS = {
        "contract_version",
        "semantic_validation",
        "config_id",
        "config_hash",
    }
    _STATE_REQUIRED = {
        "contract_version", "event_time_ms", "last_event_type",
        "mobility_state", "gnss_state", "lte_state", "last_trusted_location",
        "last_trusted_time_ms", "location_belief", "location_accuracy_m",
        "location_accuracy_status", "location_confidence",
        "location_confidence_basis", "location_confidence_calibrated",
        "location_source", "location_uncertainty_m",
        "location_uncertainty_basis", "battery_state", "battery_percent",
        "sensor_policy_state", "sos_active", "reason_codes",
    }

    def __init__(
        self,
        policy_config: SensorPolicyConfig | Mapping[str, Any] | str | Path | None = None,
    ) -> None:
        try:
            if policy_config is None:
                validated_config = load_sensor_policy_config(
                    DEFAULT_SENSOR_POLICY_CONFIG
                )
            elif isinstance(policy_config, SensorPolicyConfig):
                # Revalidate a defensive copy because the dataclass contains a
                # mutable mapping even though the wrapper itself is frozen.
                validated_config = SensorPolicyConfig.from_mapping(
                    policy_config.values
                )
            elif isinstance(policy_config, Mapping):
                validated_config = SensorPolicyConfig.from_mapping(policy_config)
            elif isinstance(policy_config, (str, Path)):
                validated_config = load_sensor_policy_config(policy_config)
            else:
                raise LocationStateValidationError(
                    "policy_config must be a validated config, mapping or path"
                )
        except SensorPolicyError as exc:
            raise LocationStateValidationError(
                "sensor policy configuration failed its named semantic validator"
            ) from exc

        self._policy_config = validated_config
        self._policy_identity = {
            "contract_version": CONFIG_CONTRACT_VERSION,
            "semantic_validation": SEMANTIC_VALIDATION_VERSION,
            "config_id": validated_config.config_id,
            "config_hash": validated_config.config_hash,
        }

        self._timeline: dict[str, list[_MirrorRecord]] = {}
        self._current: dict[str, _MirrorRecord] = {}
        self._identity_index: dict[tuple[Any, ...], tuple[str, _MirrorRecord]] = {}
        self._observation_index: dict[tuple[str, str], tuple[tuple[Any, ...], str]] = {}
        self._sequence_index: dict[
            tuple[str, int, str, int], tuple[tuple[Any, ...], str]
        ] = {}

    def _validate_envelope_contract(self, envelope: Mapping[str, Any]) -> None:
        """Validate the deployment-critical envelope shape without packages."""

        _exact_keys(
            envelope,
            required=self._ENVELOPE_REQUIRED,
            optional=self._ENVELOPE_OPTIONAL,
            name="location state envelope",
        )
        self._validate_canonical_json(envelope, "location state envelope")

    def _validate_state_contract(self, state: Mapping[str, Any]) -> None:
        """Validate the closed state shape and non-finite-number boundary."""

        _exact_keys(state, required=self._STATE_REQUIRED, name="location_state")
        self._validate_canonical_json(state, "location_state")
        if isinstance(state.get("event_time_ms"), bool) or not isinstance(
            state.get("event_time_ms"), int
        ):
            raise LocationStateValidationError(
                "location_state.event_time_ms must be an integer"
            )
        if not isinstance(state.get("sos_active"), bool):
            raise LocationStateValidationError("location_state.sos_active must be boolean")
        confidence = state.get("location_confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise LocationStateValidationError(
                "location_state.location_confidence must be numeric"
            )
        if not math.isfinite(float(confidence)) or not 0 <= confidence <= 1:
            raise LocationStateValidationError(
                "location_state.location_confidence must be finite and within 0..1"
            )
        self._validate_state_fields(state)

    @staticmethod
    def _validate_state_fields(state: Mapping[str, Any]) -> None:
        def enum(field: str, values: set[str]) -> None:
            if state.get(field) not in values:
                raise LocationStateValidationError(f"location_state.{field} is invalid")

        def number(value: Any, name: str, low: float, high: float | None = None, *, exclusive: bool = False) -> None:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise LocationStateValidationError(f"{name} must be a finite number")
            if (value <= low if exclusive else value < low) or (high is not None and value > high):
                raise LocationStateValidationError(f"{name} is outside its accepted range")

        if state.get("contract_version") != LOCATION_STATE_CONTRACT_VERSION:
            raise LocationStateValidationError("location_state contract version is unsupported")
        _non_negative_integer(state.get("event_time_ms"), "location_state.event_time_ms")
        confidence = state.get("location_confidence")
        enum("mobility_state", {"stable", "moving", "unknown"})
        enum("gnss_state", {"idle", "acquiring", "fix", "no_fix", "fix_rejected", "error", "unavailable"})
        enum("lte_state", {"offline", "online", "limited", "unavailable", "unknown"})
        enum("location_belief", {"Fine", "Coarse", "Predicted", "Unknown"})
        enum("location_accuracy_status", {"source_reported", "unavailable"})
        enum("location_source", {"gnss", "cell_reference", "wifi_reference", "known_place", "last_trusted", "none"})
        enum("location_uncertainty_basis", {"source_reported_accuracy", "hdop_rule_heuristic_v0", "reference_bound", "last_trusted_age_growth_rule_v0", "unavailable"})
        enum("battery_state", {"normal", "low", "critical", "charging", "unknown"})
        enum("sensor_policy_state", {"STABLE", "MOVING", "LOCATION_UNCERTAIN", "SOS", "LOW_BATTERY"})
        if state.get("location_confidence_basis") != "rule_heuristic_v0" or state.get("location_confidence_calibrated") is not False:
            raise LocationStateValidationError("location confidence metadata is invalid")
        last_event = state.get("last_event_type")
        if not isinstance(last_event, str) or not 1 <= len(last_event) <= 64:
            raise LocationStateValidationError("location_state.last_event_type is invalid")
        reasons = state.get("reason_codes")
        if not isinstance(reasons, list) or not reasons or len({repr(v) for v in reasons}) != len(reasons) or any(not isinstance(v, str) or not 1 <= len(v) <= 128 for v in reasons):
            raise LocationStateValidationError("location_state.reason_codes is invalid")
        for field, high in (("battery_percent", 100),):
            if state.get(field) is not None:
                number(state[field], f"location_state.{field}", 0, high)
        accuracy = state.get("location_accuracy_m")
        if accuracy is not None:
            number(accuracy, "location_state.location_accuracy_m", 0, exclusive=True)
        uncertainty = state.get("location_uncertainty_m")
        if uncertainty is not None:
            number(uncertainty, "location_state.location_uncertainty_m", 0)
        trusted = state.get("last_trusted_location")
        trusted_time = state.get("last_trusted_time_ms")
        if trusted is None:
            if trusted_time is not None:
                raise LocationStateValidationError("last_trusted_time_ms requires trusted location")
        else:
            if not isinstance(trusted, Mapping):
                raise LocationStateValidationError("last_trusted_location must be object or null")
            _exact_keys(trusted, required={"latitude_deg", "longitude_deg", "accuracy_m", "uncertainty_at_fix_m", "uncertainty_basis", "source", "evidence_ref"}, name="last_trusted_location")
            number(trusted.get("latitude_deg"), "last_trusted_location.latitude_deg", -90, 90)
            number(trusted.get("longitude_deg"), "last_trusted_location.longitude_deg", -180, 180)
            if trusted.get("accuracy_m") is not None:
                number(trusted["accuracy_m"], "last_trusted_location.accuracy_m", 0, exclusive=True)
            number(trusted.get("uncertainty_at_fix_m"), "last_trusted_location.uncertainty_at_fix_m", 0, exclusive=True)
            if trusted.get("uncertainty_basis") not in {"source_reported_accuracy", "hdop_rule_heuristic_v0", "reference_bound"} or trusted.get("source") not in {"gnss", "cell_reference", "wifi_reference", "known_place"}:
                raise LocationStateValidationError("last_trusted_location metadata is invalid")
            LocationStateRuntimeMirror._validate_evidence(trusted.get("evidence_ref"))
            _non_negative_integer(trusted_time, "last_trusted_time_ms")
        belief = state["location_belief"]
        if belief == "Unknown" and (accuracy is not None or state["location_accuracy_status"] != "unavailable" or confidence != 0 or state["location_source"] != "none" or uncertainty is not None or state["location_uncertainty_basis"] != "unavailable"):
            raise LocationStateValidationError("Unknown belief fields are inconsistent")
        if belief == "Predicted" and (accuracy is not None or state["location_accuracy_status"] != "unavailable" or state["location_source"] != "last_trusted" or uncertainty is None or uncertainty <= 0 or state["location_uncertainty_basis"] != "last_trusted_age_growth_rule_v0"):
            raise LocationStateValidationError("Predicted belief fields are inconsistent")
        if belief == "Fine" and (trusted is None or state["location_source"] != "gnss" or uncertainty is None or uncertainty <= 0):
            raise LocationStateValidationError("Fine belief fields are inconsistent")
        if belief == "Coarse" and (trusted is None or state["location_source"] not in {"cell_reference", "wifi_reference", "known_place"} or uncertainty is None or uncertainty <= 0):
            raise LocationStateValidationError("Coarse belief fields are inconsistent")
        if (state["location_accuracy_status"] == "source_reported") != (accuracy is not None):
            raise LocationStateValidationError("location accuracy status/value are inconsistent")

    @staticmethod
    def _validate_evidence(value: Any) -> None:
        if not isinstance(value, Mapping):
            raise LocationStateValidationError("evidence_ref must be an object")
        required = {"observation_id", "source_status", "stream_id", "sequence_id", "device_run_id", "boot_count", "event_time_ms", "event_time_source", "capture_time_ns", "monotonic_clock_domain_id"}
        _exact_keys(value, required=required, optional={"reference_id"}, name="evidence_ref")
        _bounded_id(value.get("observation_id"), "evidence_ref.observation_id")
        if value.get("source_status") not in {"observed", "verified"}:
            raise LocationStateValidationError("evidence_ref.source_status is invalid")
        for field in ("stream_id", "device_run_id"):
            if value.get(field) is not None:
                _bounded_id(value[field], f"evidence_ref.{field}")
        if "reference_id" in value:
            _bounded_id(value["reference_id"], "evidence_ref.reference_id")
        for field in ("sequence_id", "boot_count"):
            if value.get(field) is not None:
                _non_negative_integer(value[field], f"evidence_ref.{field}")
        _non_negative_integer(value.get("event_time_ms"), "evidence_ref.event_time_ms")
        _non_negative_integer(value.get("capture_time_ns"), "evidence_ref.capture_time_ns")
        source = value.get("event_time_source")
        domain = value.get("monotonic_clock_domain_id")
        if source not in EVENT_TIME_SOURCES:
            raise LocationStateValidationError("evidence_ref.event_time_source is invalid")
        if source == MONOTONIC_EVENT_TIME_SOURCE:
            _non_negative_integer(value.get("boot_count"), "evidence_ref.boot_count")
            _bounded_id(domain, "evidence_ref.monotonic_clock_domain_id")
        elif domain is not None:
            raise LocationStateValidationError("evidence_ref monotonic domain must be null for UTC")

    @staticmethod
    def _validate_canonical_json(value: Any, name: str) -> None:
        try:
            json.dumps(value, allow_nan=False, sort_keys=True)
        except (TypeError, ValueError) as exc:
            raise LocationStateValidationError(
                f"{name} must contain canonical JSON values"
            ) from exc

    @property
    def policy_identity(self) -> dict[str, str]:
        return dict(self._policy_identity)

    def ingest(self, envelope: Mapping[str, Any]) -> dict[str, Any]:
        """Atomically accept one state or report an idempotent duplicate."""

        if not isinstance(envelope, Mapping):
            raise LocationStateValidationError("location state envelope must be an object")
        self._validate_envelope_contract(envelope)
        _exact_keys(
            envelope,
            required=self._ENVELOPE_REQUIRED,
            optional=self._ENVELOPE_OPTIONAL,
            name="location state envelope",
        )
        if (
            envelope.get("envelope_contract_version")
            != LOCATION_STATE_ENVELOPE_CONTRACT_VERSION
        ):
            raise LocationStateValidationError(
                "location state envelope contract version is unsupported"
            )

        identity = LocationStateIdentity(
            device_id=_outbox_safe_id(envelope.get("device_id"), "device_id"),
            boot_count=_non_negative_integer(
                envelope.get("boot_count"), "boot_count"
            ),
            session_id=_outbox_safe_id(envelope.get("session_id"), "session_id"),
            event_time_ms=_non_negative_integer(
                envelope.get("event_time_ms"), "event_time_ms"
            ),
            sequence_id=_non_negative_integer(
                envelope.get("sequence_id"), "sequence_id"
            ),
            observation_id=_bounded_id(
                envelope.get("observation_id"), "observation_id"
            ),
        )
        clock = _clock_identity(
            envelope, event_time_ms=identity.event_time_ms, name="envelope"
        )
        receive_time = envelope.get("server_receive_time_ms")
        if "server_receive_time_ms" in envelope:
            receive_time = _non_negative_integer(
                receive_time, "server_receive_time_ms"
            )

        policy_identity = self._validate_policy_identity(
            envelope.get("policy_identity")
        )
        state = self._validate_location_state(
            envelope.get("location_state"), identity=identity, clock=clock
        )

        identity_key = self._identity_key(identity)
        content = {
            "identity": identity.as_dict(),
            "event_clock": clock.as_dict(),
            "policy_identity": policy_identity,
            "location_state": state,
        }
        try:
            content_hash = hashlib.sha256(canonical_json_bytes(content)).hexdigest()
        except (TypeError, ValueError) as exc:
            raise LocationStateValidationError(
                "location state envelope must contain canonical JSON values"
            ) from exc

        existing_identity = self._identity_index.get(identity_key)
        if existing_identity is not None:
            if existing_identity[0] == content_hash:
                return self._ingest_result("duplicate", existing_identity[1])
            raise LocationStateConflictError(
                "location state identity was reused with different content"
            )

        observation_key = (identity.device_id, identity.observation_id)
        existing_observation = self._observation_index.get(observation_key)
        if existing_observation is not None:
            raise LocationStateConflictError(
                "observation_id was reused with a different immutable identity"
            )

        sequence_key = (
            identity.device_id,
            identity.boot_count,
            identity.session_id,
            identity.sequence_id,
        )
        if sequence_key in self._sequence_index:
            raise LocationStateConflictError(
                "sequence_id was reused within one device boot/session"
            )

        current = self._current.get(identity.device_id)
        if current is not None:
            self._validate_forward_progress(current, identity, clock)

        record = _MirrorRecord(
            identity=identity,
            clock=clock,
            policy_identity=policy_identity,
            location_state=state,
            server_receive_time_ms=receive_time,
            content_hash=content_hash,
        )

        # All validation and conflict checks complete before any mutation.
        self._timeline.setdefault(identity.device_id, []).append(record)
        self._current[identity.device_id] = record
        self._identity_index[identity_key] = (content_hash, record)
        self._observation_index[observation_key] = (identity_key, content_hash)
        self._sequence_index[sequence_key] = (identity_key, content_hash)
        return self._ingest_result("accepted", record)

    def timeline(self, device_id: str) -> list[dict[str, Any]]:
        """Return a defensive copy of accepted evidence in source-event order."""

        device = _bounded_id(device_id, "device_id")
        return [record.copy_for_inspection() for record in self._timeline.get(device, [])]

    def current_record(self, device_id: str) -> dict[str, Any] | None:
        """Return derived current separately from the append-only timeline."""

        device = _bounded_id(device_id, "device_id")
        record = self._current.get(device)
        return record.copy_for_inspection() if record is not None else None

    def guardian_snapshot(
        self,
        device_id: str,
        *,
        view_event_time_ns: int,
        view_event_time_source: str,
        stale_after_ms: int,
        offline_after_ms: int,
        monotonic_clock_domain_id: str | None = None,
        location_access_authorized: bool = False,
    ) -> dict[str, Any]:
        """Build an honest Guardian projection using a comparable event clock.

        The caller must provide a current clock sample, not a server receive
        timestamp masquerading as device event time. Exact coordinates fail
        closed unless the future authenticated API adapter explicitly records
        that Guardian location access was authorized.
        """

        device = _bounded_id(device_id, "device_id")
        stale_limit = _positive_integer(stale_after_ms, "stale_after_ms")
        offline_limit = _positive_integer(offline_after_ms, "offline_after_ms")
        if offline_limit < stale_limit:
            raise LocationStateValidationError(
                "offline_after_ms must be greater than or equal to stale_after_ms"
            )
        if not isinstance(location_access_authorized, bool):
            raise LocationStateValidationError(
                "location_access_authorized must be boolean"
            )
        view_ns = _non_negative_integer(view_event_time_ns, "view_event_time_ns")
        view_ms = view_ns // 1_000_000
        view_clock = _clock_identity(
            {
                "event_time_source": view_event_time_source,
                "event_time_ns": view_ns,
                "monotonic_clock_domain_id": monotonic_clock_domain_id,
            },
            event_time_ms=view_ms,
            name="Guardian view clock",
        )

        record = self._current.get(device)
        if record is None:
            return self._empty_guardian_snapshot(device, self._policy_identity)
        if view_clock.comparison_domain != record.clock.comparison_domain:
            raise LocationStateValidationError(
                "Guardian view clock is not comparable with current source event time"
            )
        if view_ns < record.clock.event_time_ns:
            raise LocationStateRegressionError(
                "Guardian view event time precedes device current event time"
            )

        state = record.location_state
        state_age_ms = view_ms - record.identity.event_time_ms
        trusted = state.get("last_trusted_location")
        trusted_time = state.get("last_trusted_time_ms")
        location_age_ms: int | None = None
        location_age_status = "unavailable"
        if isinstance(trusted, Mapping) and isinstance(trusted_time, int):
            evidence = trusted["evidence_ref"]
            trusted_domain = self._evidence_comparison_domain(evidence)
            if trusted_domain == view_clock.scoped_comparison_domain(
                record.identity.boot_count
            ):
                location_age_ms = view_ms - trusted_time
                location_age_status = "event_time"
            else:
                location_age_status = "clock_incomparable"

        belief = str(state["location_belief"])
        position: dict[str, float] | None = None
        position_status = "unavailable"
        if (
            belief != "Unknown"
            and isinstance(trusted, Mapping)
            and location_access_authorized
        ):
            position = {
                "latitude_deg": float(trusted["latitude_deg"]),
                "longitude_deg": float(trusted["longitude_deg"]),
            }
            position_status = (
                "last_trusted_predicted"
                if belief == "Predicted"
                else "trusted_location"
            )
        elif belief != "Unknown" and isinstance(trusted, Mapping):
            position_status = "redacted_unauthorized"

        accuracy_applicable = (
            belief in {"Fine", "Coarse"}
            and state["location_accuracy_status"] == "source_reported"
            and state["location_accuracy_m"] is not None
        )
        uncertainty_applicable = (
            belief != "Unknown" and state["location_uncertainty_m"] is not None
        )
        stale = state_age_ms > stale_limit
        offline, offline_status, freshness_reasons = self._offline_projection(
            lte_state=str(state["lte_state"]),
            state_age_ms=state_age_ms,
            offline_after_ms=offline_limit,
            stale=stale,
        )

        return {
            "device_id": device,
            "available": True,
            "current_identity": record.identity.as_dict(),
            "policy_identity": deepcopy(record.policy_identity),
            "state_event_time_ms": record.identity.event_time_ms,
            "state_age_ms": state_age_ms,
            "location_age_ms": location_age_ms,
            "location_age_status": location_age_status,
            "location_belief": belief,
            "location_source": state["location_source"],
            "position": position,
            "position_status": position_status,
            "location_access_authorized": location_access_authorized,
            "accuracy": {
                "applicable": accuracy_applicable,
                "value_m": state["location_accuracy_m"] if accuracy_applicable else None,
                "status": state["location_accuracy_status"],
            },
            "confidence": {
                "value": state["location_confidence"],
                "basis": state["location_confidence_basis"],
                "calibrated": state["location_confidence_calibrated"],
            },
            "uncertainty": {
                "applicable": uncertainty_applicable,
                "value_m": (
                    state["location_uncertainty_m"]
                    if uncertainty_applicable
                    else None
                ),
                "basis": state["location_uncertainty_basis"],
            },
            "battery": {
                "state": state["battery_state"],
                "percent": state["battery_percent"],
            },
            "sensor_policy_state": state["sensor_policy_state"],
            "sos_active": state["sos_active"],
            "stale": stale,
            "offline": offline,
            "offline_status": offline_status,
            "freshness_reason_codes": freshness_reasons,
        }

    def _validate_policy_identity(self, value: Any) -> dict[str, str]:
        if not isinstance(value, Mapping):
            raise LocationStateValidationError("policy_identity must be an object")
        _exact_keys(
            value,
            required=self._POLICY_IDENTITY_KEYS,
            name="policy_identity",
        )
        for field, expected in self._policy_identity.items():
            if value.get(field) != expected:
                raise LocationStateValidationError(
                    f"policy_identity.{field} does not match the accepted configuration"
                )
        return dict(self._policy_identity)

    def _validate_location_state(
        self,
        value: Any,
        *,
        identity: LocationStateIdentity,
        clock: _ClockIdentity,
    ) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise LocationStateValidationError("location_state must be an object")
        state = deepcopy(dict(value))
        self._validate_state_contract(state)
        if state.get("contract_version") != LOCATION_STATE_CONTRACT_VERSION:
            raise LocationStateValidationError(
                "location_state contract version is unsupported"
            )
        if state["event_time_ms"] != identity.event_time_ms:
            raise LocationStateValidationError(
                "location_state.event_time_ms does not match envelope event time"
            )

        trusted = state.get("last_trusted_location")
        trusted_time = state.get("last_trusted_time_ms")
        if isinstance(trusted, Mapping):
            if trusted_time > state["event_time_ms"]:
                raise LocationStateValidationError(
                    "last trusted time exceeds current state event time"
                )
            evidence = trusted["evidence_ref"]
            if evidence["event_time_ms"] != trusted_time:
                raise LocationStateValidationError(
                    "last trusted time does not match its evidence event time"
                )
            if evidence["capture_time_ns"] // 1_000_000 != evidence["event_time_ms"]:
                raise LocationStateValidationError(
                    "last trusted capture time is not bound to its event time"
                )
            evidence_boot = evidence.get("boot_count")
            if isinstance(evidence_boot, int) and evidence_boot > identity.boot_count:
                raise LocationStateValidationError(
                    "last trusted evidence boot exceeds the enclosing device boot"
                )
            evidence_domain = self._evidence_comparison_domain(evidence)
            if state["location_belief"] != "Unknown" and (
                evidence_domain
                != clock.scoped_comparison_domain(identity.boot_count)
            ):
                raise LocationStateValidationError(
                    "active location belief uses an event clock incomparable with current state"
                )
            if (
                trusted_time == identity.event_time_ms
                and state["last_event_type"] in {"gnss_fix", "coarse_location"}
            ):
                if (
                    evidence["event_time_source"] != clock.source
                    or evidence["capture_time_ns"] != clock.event_time_ns
                ):
                    raise LocationStateValidationError(
                        "new trusted location evidence does not bind to the state event clock"
                    )
            belief = state["location_belief"]
            if belief in {"Fine", "Coarse"}:
                if state["location_source"] != trusted["source"]:
                    raise LocationStateValidationError(
                        "active location source does not match last trusted source"
                    )
                trusted_accuracy = trusted["accuracy_m"]
                if state["location_accuracy_status"] == "source_reported":
                    if state["location_accuracy_m"] != trusted_accuracy:
                        raise LocationStateValidationError(
                            "active reported accuracy does not match trusted evidence"
                        )
                elif trusted_accuracy is not None:
                    raise LocationStateValidationError(
                        "active trusted accuracy was suppressed without a belief transition"
                    )
                if (
                    state["location_uncertainty_m"]
                    != trusted["uncertainty_at_fix_m"]
                    or state["location_uncertainty_basis"]
                    != trusted["uncertainty_basis"]
                ):
                    raise LocationStateValidationError(
                        "active uncertainty does not match trusted evidence"
                    )
        return state

    @staticmethod
    def _evidence_comparison_domain(
        evidence: Mapping[str, Any]
    ) -> tuple[str, int | None, str | None]:
        source = evidence["event_time_source"]
        if source in UTC_EVENT_TIME_SOURCES:
            return ("utc", None, None)
        return (
            "boot_monotonic",
            evidence.get("boot_count"),
            evidence.get("monotonic_clock_domain_id"),
        )

    @staticmethod
    def _identity_key(identity: LocationStateIdentity) -> tuple[Any, ...]:
        return (
            identity.device_id,
            identity.boot_count,
            identity.session_id,
            identity.event_time_ms,
            identity.sequence_id,
            identity.observation_id,
        )

    @staticmethod
    def _validate_forward_progress(
        current: _MirrorRecord,
        incoming: LocationStateIdentity,
        clock: _ClockIdentity,
    ) -> None:
        prior = current.identity
        if incoming.boot_count < prior.boot_count:
            raise LocationStateRegressionError("device boot_count regression")
        if incoming.boot_count == prior.boot_count:
            if incoming.session_id != prior.session_id:
                raise LocationStateConflictError(
                    "session_id changed within one device boot without an ordering contract"
                )
            if clock.comparison_domain != current.clock.comparison_domain:
                raise LocationStateConflictError(
                    "event clock domain changed within one device boot/session"
                )
            if clock.event_time_ns < current.clock.event_time_ns:
                raise LocationStateRegressionError("source event time regression")
            if incoming.sequence_id <= prior.sequence_id:
                raise LocationStateRegressionError("source sequence_id did not advance")
        elif (
            clock.comparison_domain == ("utc", None)
            and current.clock.comparison_domain == ("utc", None)
            and clock.event_time_ns < current.clock.event_time_ns
        ):
            raise LocationStateRegressionError(
                "UTC source event time regressed across a newer device boot"
            )

    def _ingest_result(self, status: str, record: _MirrorRecord) -> dict[str, Any]:
        return {
            "status": status,
            "identity": record.identity.as_dict(),
            "timeline_length": len(
                self._timeline.get(record.identity.device_id, [])
            ),
            "current_event_time_ms": self._current.get(
                record.identity.device_id, record
            ).identity.event_time_ms,
        }

    @staticmethod
    def _offline_projection(
        *,
        lte_state: str,
        state_age_ms: int,
        offline_after_ms: int,
        stale: bool,
    ) -> tuple[bool | None, str, list[str]]:
        reasons: list[str] = []
        if stale:
            reasons.append("state_update_stale")
        if state_age_ms > offline_after_ms:
            reasons.append("device_event_silence_threshold_exceeded")
            return True, "offline", reasons
        if lte_state in {"offline", "unavailable"}:
            reasons.append("device_reported_lte_offline")
            return True, "offline", reasons
        if lte_state == "online":
            reasons.append("device_reported_lte_online")
            return False, "online", reasons
        if lte_state == "limited":
            reasons.append("device_reported_lte_limited")
            return False, "limited", reasons
        reasons.append("lte_state_unknown")
        return None, "unknown", reasons

    @staticmethod
    def _empty_guardian_snapshot(
        device_id: str, policy_identity: Mapping[str, str]
    ) -> dict[str, Any]:
        return {
            "device_id": device_id,
            "available": False,
            "current_identity": None,
            "policy_identity": dict(policy_identity),
            "state_event_time_ms": None,
            "state_age_ms": None,
            "location_age_ms": None,
            "location_age_status": "unavailable",
            "location_belief": "Unknown",
            "location_source": "none",
            "position": None,
            "position_status": "unavailable",
            "location_access_authorized": False,
            "accuracy": {
                "applicable": False,
                "value_m": None,
                "status": "unavailable",
            },
            "confidence": {
                "value": 0.0,
                "basis": "unavailable",
                "calibrated": False,
            },
            "uncertainty": {
                "applicable": False,
                "value_m": None,
                "basis": "unavailable",
            },
            "battery": {"state": "unknown", "percent": None},
            "sensor_policy_state": None,
            "sos_active": False,
            "stale": True,
            "offline": True,
            "offline_status": "offline",
            "freshness_reason_codes": ["no_accepted_device_state"],
        }

"""Deterministic rule-first Location Engine v0 reference implementation.

The reducer consumes normalized observations in event-time order. Coordinates
become trusted only when the observation carries capture-time lineage and an
observed/verified source status. Cell identifiers, IMU, battery, receive time,
and caller assertions can never manufacture a trusted point.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import math
from typing import Any, Mapping


CONTRACT_VERSION = "egolink.location_engine.v0.1"

MOBILITY_STATES = frozenset({"stable", "moving", "unknown"})
GNSS_STATES = frozenset(
    {"idle", "acquiring", "fix", "no_fix", "fix_rejected", "error", "unavailable"}
)
LTE_STATES = frozenset({"offline", "online", "limited", "unavailable", "unknown"})
BATTERY_STATES = frozenset({"normal", "low", "critical", "charging", "unknown"})
POLICY_STATES = frozenset(
    {"STABLE", "MOVING", "LOCATION_UNCERTAIN", "SOS", "LOW_BATTERY"}
)
COARSE_SOURCES = frozenset({"cell_reference", "wifi_reference", "known_place"})
TRUSTED_SOURCE_STATUSES = frozenset({"observed", "verified"})
RULE_DERIVED_SOURCE_STATUS = "rule_derived"
RULE_DERIVED_TIME_SOURCES = frozenset(
    {"policy_rule_v0", "policy_timer_v0", "policy_action_v0"}
)
GNSS_LINEAGE_EVENT_TYPES = frozenset(
    {"gnss_started", "gnss_stopped", "gnss_no_fix", "gnss_error"}
)
SUPPORTED_EVENT_TYPES = frozenset(
    {
        "tick",
        "imu_sample",
        "mobility",
        "gnss_started",
        "gnss_stopped",
        "gnss_no_fix",
        "gnss_error",
        "gnss_fix",
        "coarse_location",
        "lte_state",
        "cell_observation",
        "battery",
        "sos",
    }
)


class LocationEngineError(ValueError):
    """Raised when an observation violates the v0 structural contract."""


@dataclass(frozen=True)
class LocationEngineConfig:
    """Rule parameters supplied by configuration, not measured product truth."""

    fine_max_accuracy_m: float = 100.0
    fine_max_hdop: float = 5.0
    hdop_uncertainty_multiplier_m: float = 5.0
    coarse_max_uncertainty_m: float = 5_000.0
    fine_freshness_ms: int = 30_000
    coarse_freshness_ms: int = 120_000
    prediction_horizon_ms: int = 900_000
    uncertainty_growth_mps: float = 1.5
    fine_initial_confidence: float = 0.95
    coarse_initial_confidence: float = 0.65
    predicted_min_confidence: float = 0.10

    def __post_init__(self) -> None:
        for name in (
            "fine_max_accuracy_m",
            "fine_max_hdop",
            "hdop_uncertainty_multiplier_m",
            "coarse_max_uncertainty_m",
            "fine_freshness_ms",
            "coarse_freshness_ms",
            "prediction_horizon_ms",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or value <= 0
            ):
                raise LocationEngineError(f"{name} must be positive")
        if self.coarse_max_uncertainty_m < self.fine_max_accuracy_m:
            raise LocationEngineError(
                "coarse_max_uncertainty_m must be >= fine_max_accuracy_m"
            )
        if self.prediction_horizon_ms < max(
            self.fine_freshness_ms, self.coarse_freshness_ms
        ):
            raise LocationEngineError(
                "prediction_horizon_ms must cover both freshness windows"
            )
        if (
            isinstance(self.uncertainty_growth_mps, bool)
            or not isinstance(self.uncertainty_growth_mps, (int, float))
            or not math.isfinite(float(self.uncertainty_growth_mps))
            or self.uncertainty_growth_mps < 0
        ):
            raise LocationEngineError("uncertainty_growth_mps must be >= 0")
        for name in (
            "fine_initial_confidence",
            "coarse_initial_confidence",
            "predicted_min_confidence",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
            ):
                raise LocationEngineError(f"{name} must be numeric")
            if not 0.0 <= float(value) <= 1.0:
                raise LocationEngineError(f"{name} must be within [0, 1]")
        if self.predicted_min_confidence > min(
            self.fine_initial_confidence, self.coarse_initial_confidence
        ):
            raise LocationEngineError(
                "predicted_min_confidence cannot exceed an initial confidence"
            )


def _event_time_ms(observation: Mapping[str, Any]) -> int:
    value = observation.get("event_time_ms")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise LocationEngineError("event_time_ms must be a non-negative integer")
    return value


def _optional_finite(value: Any, name: str) -> float | None:
    if value is None:
        return None
    return _finite_number(value, name)


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LocationEngineError(f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise LocationEngineError(f"{name} must be finite")
    return number


def _enum_value(value: Any, allowed: frozenset[str], name: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        expected = ", ".join(sorted(allowed))
        raise LocationEngineError(f"{name} must be one of: {expected}")
    return value


def _lineage_mapping(observation: Mapping[str, Any]) -> Mapping[str, Any] | None:
    raw = observation.get("lineage")
    if not isinstance(raw, Mapping):
        raw = observation.get("evidence")
    if not isinstance(raw, Mapping):
        return None
    return raw


def _optional_lineage_string(
    raw: Mapping[str, Any], name: str, *, maximum: int = 256
) -> tuple[str | None, bool]:
    if name not in raw or raw.get(name) is None:
        return None, True
    value = raw.get(name)
    if not isinstance(value, str) or not value or len(value) > maximum:
        return None, False
    return value, True


def _optional_lineage_integer(
    raw: Mapping[str, Any], name: str
) -> tuple[int | None, bool]:
    if name not in raw or raw.get(name) is None:
        return None, True
    value = raw.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None, False
    return value, True


def _capture_time_binding(
    raw: Mapping[str, Any], event_time_ms: int
) -> tuple[str, int] | None:
    """Select a real capture timestamp whose millisecond lane equals the event time.

    UTC and GNSS-source UTC are globally meaningful. A monotonic timestamp is
    accepted only with an explicit boot and clock-domain scope.
    """

    for field in ("gnss_source_utc_ns", "timestamp_utc_ns"):
        if field not in raw or raw.get(field) is None:
            continue
        value = raw.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return None
        if value // 1_000_000 == event_time_ms:
            return field, value

    if "timestamp_monotonic_ns" not in raw or raw.get("timestamp_monotonic_ns") is None:
        return None
    monotonic_ns = raw.get("timestamp_monotonic_ns")
    boot_count = raw.get("boot_count")
    clock_domain = raw.get("monotonic_clock_domain_id")
    if (
        isinstance(monotonic_ns, bool)
        or not isinstance(monotonic_ns, int)
        or monotonic_ns < 0
        or isinstance(boot_count, bool)
        or not isinstance(boot_count, int)
        or boot_count < 0
        or not isinstance(clock_domain, str)
        or not clock_domain
        or len(clock_domain) > 256
    ):
        return None
    if monotonic_ns // 1_000_000 != event_time_ms:
        return None
    return "timestamp_monotonic_ns", monotonic_ns


def _evidence_ref(
    observation: Mapping[str, Any], event_time_ms: int
) -> dict[str, Any] | None:
    raw = _lineage_mapping(observation)
    if raw is None:
        return None
    observation_id = raw.get("observation_id")
    source_status = raw.get("source_status")
    if (
        not isinstance(observation_id, str)
        or not observation_id
        or len(observation_id) > 256
    ):
        return None
    if source_status not in TRUSTED_SOURCE_STATUSES:
        return None
    outer_evidence = observation.get("evidence")
    if (
        isinstance(outer_evidence, Mapping)
        and "source_status" in outer_evidence
        and outer_evidence.get("source_status") != source_status
    ):
        return None
    stream_id, stream_valid = _optional_lineage_string(raw, "stream_id")
    device_run_id, run_valid = _optional_lineage_string(raw, "device_run_id")
    sequence_id, sequence_valid = _optional_lineage_integer(raw, "sequence_id")
    boot_count, boot_valid = _optional_lineage_integer(raw, "boot_count")
    if not all((stream_valid, run_valid, sequence_valid, boot_valid)):
        return None
    binding = _capture_time_binding(raw, event_time_ms)
    if binding is None:
        return None
    event_time_source, capture_time_ns = binding
    return {
        "observation_id": observation_id,
        "source_status": source_status,
        "stream_id": stream_id,
        "sequence_id": sequence_id,
        "device_run_id": device_run_id,
        "boot_count": boot_count,
        "event_time_ms": event_time_ms,
        "event_time_source": event_time_source,
        "capture_time_ns": capture_time_ns,
        "monotonic_clock_domain_id": (
            raw.get("monotonic_clock_domain_id")
            if event_time_source == "timestamp_monotonic_ns"
            else None
        ),
    }


def _has_rule_derived_lineage(observation: Mapping[str, Any]) -> bool:
    """Require attributable input lineage for an internally derived mobility event."""

    raw = _lineage_mapping(observation)
    if raw is None:
        return False
    observation_id = raw.get("observation_id")
    basis_ids = raw.get("basis_observation_ids")
    valid_basis = (
        isinstance(basis_ids, list)
        and bool(basis_ids)
        and all(
            isinstance(item, str) and bool(item) and len(item) <= 256
            for item in basis_ids
        )
    )
    return (
        isinstance(observation_id, str)
        and bool(observation_id)
        and len(observation_id) <= 256
        and raw.get("source_status") == RULE_DERIVED_SOURCE_STATUS
        and raw.get("event_time_source") in RULE_DERIVED_TIME_SOURCES
        and valid_basis
        and len(set(basis_ids)) == len(basis_ids)
    )


def has_attributable_observation_lineage(
    observation: Mapping[str, Any],
    event_time_ms: int,
    *,
    allow_rule_derived: bool = True,
) -> bool:
    """Return whether an observation has capture-bound or derived lineage."""

    return _evidence_ref(observation, event_time_ms) is not None or (
        allow_rule_derived and _has_rule_derived_lineage(observation)
    )


class LocationEngineV0:
    """Small event-time reducer for the first P0 location slice."""

    def __init__(self, config: LocationEngineConfig | None = None) -> None:
        self.config = config or LocationEngineConfig()
        self._last_event_time_ms: int | None = None
        self._last_event_type = "initialized"
        self._last_reason_codes: list[str] = ["no_observation_yet"]
        self._mobility_state = "unknown"
        self._gnss_state = "idle"
        self._lte_state = "unknown"
        self._battery_state = "unknown"
        self._battery_percent: float | None = None
        self._sensor_policy_state = "STABLE"
        self._sos_active = False
        self._last_trusted_location: dict[str, Any] | None = None
        self._last_trusted_time_ms: int | None = None
        self._last_trusted_belief: str | None = None
        self._force_predicted = False

    @property
    def last_event_time_ms(self) -> int | None:
        return self._last_event_time_ms

    def set_policy_context(self, policy_state: str) -> None:
        self._sensor_policy_state = _enum_value(
            policy_state, POLICY_STATES, "sensor_policy_state"
        )

    def process(self, observation: Mapping[str, Any]) -> dict[str, Any]:
        """Apply one observation atomically.

        A rejected observation must not advance the reducer clock or leave a
        partially applied state behind.
        """

        prior_state = deepcopy(self.__dict__)
        try:
            return self._process_in_place(observation)
        except Exception:
            self.__dict__.clear()
            self.__dict__.update(prior_state)
            raise

    def _process_in_place(self, observation: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(observation, Mapping):
            raise LocationEngineError("observation must be an object")
        event_time_ms = _event_time_ms(observation)
        if self._last_event_time_ms is not None and event_time_ms < self._last_event_time_ms:
            raise LocationEngineError(
                "event_time_ms regression: receive/ingest time must not reorder evidence"
            )
        event_type = observation.get("event_type")
        if not isinstance(event_type, str) or not event_type or len(event_type) > 64:
            raise LocationEngineError("event_type must be a 1-64 character string")
        if event_type not in SUPPORTED_EVENT_TYPES:
            raise LocationEngineError(f"unsupported event_type: {event_type}")

        if event_type in GNSS_LINEAGE_EVENT_TYPES and not has_attributable_observation_lineage(
            observation, event_time_ms
        ):
            raise LocationEngineError(
                f"{event_type} lacks capture-bound or policy-action lineage"
            )

        self._last_event_time_ms = event_time_ms
        self._last_event_type = event_type
        self._last_reason_codes = []

        if event_type == "tick":
            self._last_reason_codes.append("policy_clock_advanced")
        elif event_type == "imu_sample":
            self._last_reason_codes.append("imu_observed_without_coordinate_derivation")
        elif event_type == "mobility":
            evidence = _evidence_ref(observation, event_time_ms)
            if evidence is None and not _has_rule_derived_lineage(observation):
                raise LocationEngineError("mobility observation lacks trusted lineage")
            self._mobility_state = _enum_value(
                observation.get("mobility_state"), MOBILITY_STATES, "mobility_state"
            )
            self._last_reason_codes.append(f"mobility_{self._mobility_state}")
        elif event_type == "gnss_started":
            self._gnss_state = "acquiring"
            self._force_predicted = self._last_trusted_location is not None
            self._last_reason_codes.append("gnss_acquisition_started")
        elif event_type == "gnss_stopped":
            self._gnss_state = "idle"
            self._last_reason_codes.append("gnss_acquisition_stopped")
        elif event_type == "gnss_no_fix":
            self._gnss_state = "no_fix"
            self._force_predicted = self._last_trusted_location is not None
            self._last_reason_codes.append("gnss_no_fix_preserved_last_trusted")
        elif event_type == "gnss_error":
            self._gnss_state = "error"
            self._force_predicted = self._last_trusted_location is not None
            self._last_reason_codes.append("gnss_error_preserved_last_trusted")
        elif event_type == "gnss_fix":
            self._apply_gnss_fix(observation, event_time_ms)
        elif event_type == "coarse_location":
            self._apply_coarse_location(observation, event_time_ms)
        elif event_type == "lte_state":
            self._lte_state = _enum_value(
                observation.get("lte_state"), LTE_STATES, "lte_state"
            )
            self._last_reason_codes.append(f"lte_{self._lte_state}")
        elif event_type == "cell_observation":
            self._lte_state = "online"
            self._last_reason_codes.append("cell_observed_without_coordinate_derivation")
        elif event_type == "battery":
            self._apply_battery(observation)
        elif event_type == "sos":
            active = observation.get("active")
            if not isinstance(active, bool):
                raise LocationEngineError("sos.active must be boolean")
            self._sos_active = active
            self._last_reason_codes.append("sos_active" if active else "sos_cleared")
        if not self._last_reason_codes:
            self._last_reason_codes.append("observation_applied")
        return self.snapshot(event_time_ms)

    def snapshot(self, event_time_ms: int | None = None) -> dict[str, Any]:
        if event_time_ms is None:
            event_time_ms = self._last_event_time_ms if self._last_event_time_ms is not None else 0
        if isinstance(event_time_ms, bool) or not isinstance(event_time_ms, int):
            raise LocationEngineError("snapshot event_time_ms must be an integer")
        if event_time_ms < 0:
            raise LocationEngineError("snapshot event_time_ms must be non-negative")
        if self._last_event_time_ms is not None and event_time_ms < self._last_event_time_ms:
            raise LocationEngineError("snapshot time cannot precede the latest event")

        belief = self._belief_at(event_time_ms)
        return {
            "contract_version": CONTRACT_VERSION,
            "event_time_ms": event_time_ms,
            "last_event_type": self._last_event_type,
            "mobility_state": self._mobility_state,
            "gnss_state": self._gnss_state,
            "lte_state": self._lte_state,
            "last_trusted_location": deepcopy_mapping(self._last_trusted_location),
            "last_trusted_time_ms": self._last_trusted_time_ms,
            "location_belief": belief["state"],
            "location_accuracy_m": belief["accuracy_m"],
            "location_accuracy_status": belief["accuracy_status"],
            "location_confidence": belief["confidence"],
            "location_confidence_basis": "rule_heuristic_v0",
            "location_confidence_calibrated": False,
            "location_source": belief["source"],
            "location_uncertainty_m": belief["uncertainty_m"],
            "location_uncertainty_basis": belief["uncertainty_basis"],
            "battery_state": self._battery_state,
            "battery_percent": self._battery_percent,
            "sensor_policy_state": self._sensor_policy_state,
            "sos_active": self._sos_active,
            "reason_codes": list(dict.fromkeys(self._last_reason_codes + belief["reasons"])),
        }

    def _apply_gnss_fix(
        self, observation: Mapping[str, Any], event_time_ms: int
    ) -> None:
        self._gnss_state = "fix_rejected"
        evidence = _evidence_ref(observation, event_time_ms)
        if evidence is None:
            self._reject_fix("gnss_fix_rejected_untrusted_lineage")
            return
        try:
            latitude = _finite_number(observation.get("latitude_deg"), "latitude_deg")
            longitude = _finite_number(observation.get("longitude_deg"), "longitude_deg")
            accuracy = _optional_finite(observation.get("accuracy_m"), "accuracy_m")
            hdop = _optional_finite(observation.get("hdop"), "hdop")
        except LocationEngineError as exc:
            self._reject_fix("gnss_fix_rejected_invalid_measurement", exc)
            return
        if not -90.0 <= latitude <= 90.0 or not -180.0 <= longitude <= 180.0:
            self._reject_fix("gnss_fix_rejected_coordinate_range")
            return

        measurement_accuracy: float | None = None
        if accuracy is not None:
            if not 0.0 < accuracy <= self.config.fine_max_accuracy_m:
                self._reject_fix("gnss_fix_rejected_reported_accuracy")
                return
            measurement_accuracy = accuracy
            initial_uncertainty = accuracy
            uncertainty_basis = "source_reported_accuracy"
        elif hdop is not None and 0.0 < hdop <= self.config.fine_max_hdop:
            initial_uncertainty = hdop * self.config.hdop_uncertainty_multiplier_m
            if not math.isfinite(initial_uncertainty) or initial_uncertainty <= 0.0:
                self._reject_fix("gnss_fix_rejected_hdop_uncertainty")
                return
            uncertainty_basis = "hdop_rule_heuristic_v0"
        else:
            self._reject_fix("gnss_fix_rejected_quality_gate")
            return

        self._gnss_state = "fix"
        self._store_trusted_location(
            latitude=latitude,
            longitude=longitude,
            measurement_accuracy_m=measurement_accuracy,
            initial_uncertainty_m=initial_uncertainty,
            uncertainty_basis=uncertainty_basis,
            source="gnss",
            belief="Fine",
            event_time_ms=event_time_ms,
            evidence=evidence,
        )
        self._last_reason_codes.append("gnss_fix_accepted")

    def _reject_fix(
        self, reason: str, error: LocationEngineError | None = None
    ) -> None:
        self._force_predicted = self._last_trusted_location is not None
        self._last_reason_codes.append(reason)
        if error is not None:
            self._last_reason_codes.append(str(error).replace(" ", "_")[:128])

    def _apply_coarse_location(
        self, observation: Mapping[str, Any], event_time_ms: int
    ) -> None:
        evidence = _evidence_ref(observation, event_time_ms)
        if evidence is None:
            raise LocationEngineError("coarse location lacks trusted lineage")
        reference_id = observation.get("reference_id")
        if (
            not isinstance(reference_id, str)
            or not reference_id
            or len(reference_id) > 256
        ):
            raise LocationEngineError(
                "coarse location requires a 1-256 character frozen reference_id"
            )
        source = _enum_value(
            observation.get("source"), COARSE_SOURCES, "coarse_location.source"
        )
        latitude = _finite_number(observation.get("latitude_deg"), "latitude_deg")
        longitude = _finite_number(observation.get("longitude_deg"), "longitude_deg")
        accuracy = _optional_finite(observation.get("accuracy_m"), "accuracy_m")
        uncertainty = _optional_finite(
            observation.get("uncertainty_m"), "uncertainty_m"
        )
        if not -90.0 <= latitude <= 90.0 or not -180.0 <= longitude <= 180.0:
            raise LocationEngineError("coarse location coordinate is out of range")
        initial_uncertainty = max(
            value for value in (uncertainty, accuracy) if value is not None
        ) if uncertainty is not None or accuracy is not None else None
        if (
            initial_uncertainty is None
            or initial_uncertainty <= 0.0
            or initial_uncertainty > self.config.coarse_max_uncertainty_m
        ):
            raise LocationEngineError(
                "coarse location uncertainty is outside the configured gate"
            )
        if accuracy is not None and accuracy <= 0.0:
            raise LocationEngineError("coarse location accuracy must be positive")
        evidence = {**evidence, "reference_id": reference_id}
        self._store_trusted_location(
            latitude=latitude,
            longitude=longitude,
            measurement_accuracy_m=accuracy,
            initial_uncertainty_m=initial_uncertainty,
            uncertainty_basis=(
                "source_reported_accuracy" if uncertainty is None else "reference_bound"
            ),
            source=source,
            belief="Coarse",
            event_time_ms=event_time_ms,
            evidence=evidence,
        )
        self._last_reason_codes.append("coarse_reference_accepted")

    def _store_trusted_location(
        self,
        *,
        latitude: float,
        longitude: float,
        measurement_accuracy_m: float | None,
        initial_uncertainty_m: float,
        uncertainty_basis: str,
        source: str,
        belief: str,
        event_time_ms: int,
        evidence: Mapping[str, Any],
    ) -> None:
        self._last_trusted_location = {
            "latitude_deg": latitude,
            "longitude_deg": longitude,
            "accuracy_m": measurement_accuracy_m,
            "uncertainty_at_fix_m": initial_uncertainty_m,
            "uncertainty_basis": uncertainty_basis,
            "source": source,
            "evidence_ref": dict(evidence),
        }
        self._last_trusted_time_ms = event_time_ms
        self._last_trusted_belief = belief
        self._force_predicted = False

    def _apply_battery(self, observation: Mapping[str, Any]) -> None:
        self._battery_state = _enum_value(
            observation.get("battery_state"), BATTERY_STATES, "battery_state"
        )
        value = observation.get("battery_percent")
        if value is None:
            self._battery_percent = None
        else:
            percent = _finite_number(value, "battery_percent")
            if not 0.0 <= percent <= 100.0:
                raise LocationEngineError("battery_percent must be within [0, 100]")
            self._battery_percent = percent
        self._last_reason_codes.append(f"battery_{self._battery_state}")

    def _belief_at(self, event_time_ms: int) -> dict[str, Any]:
        if self._last_trusted_location is None or self._last_trusted_time_ms is None:
            return _unknown_belief("no_trusted_location")

        age_ms = event_time_ms - self._last_trusted_time_ms
        if age_ms < 0:
            raise LocationEngineError("trusted location time exceeds snapshot time")
        source_accuracy = self._last_trusted_location["accuracy_m"]
        initial_uncertainty = float(
            self._last_trusted_location["uncertainty_at_fix_m"]
        )
        source = str(self._last_trusted_location["source"])
        initial_basis = str(self._last_trusted_location["uncertainty_basis"])
        initial_belief = self._last_trusted_belief or "Unknown"
        freshness_ms = (
            self.config.fine_freshness_ms
            if initial_belief == "Fine"
            else self.config.coarse_freshness_ms
        )
        initial_confidence = (
            self.config.fine_initial_confidence
            if initial_belief == "Fine"
            else self.config.coarse_initial_confidence
        )

        if age_ms <= freshness_ms and not self._force_predicted:
            return {
                "state": initial_belief,
                "accuracy_m": source_accuracy,
                "accuracy_status": (
                    "source_reported" if source_accuracy is not None else "unavailable"
                ),
                "confidence": round(float(initial_confidence), 6),
                "source": source,
                "uncertainty_m": initial_uncertainty,
                "uncertainty_basis": initial_basis,
                "reasons": ["trusted_location_fresh"],
            }

        if age_ms <= self.config.prediction_horizon_ms:
            age_s = age_ms / 1000.0
            uncertainty = initial_uncertainty + self.config.uncertainty_growth_mps * age_s
            if not math.isfinite(uncertainty):
                return _unknown_belief(
                    "uncertainty_growth_overflow",
                    "last_trusted_retained_as_memory_only",
                )
            denominator = max(1, self.config.prediction_horizon_ms - freshness_ms)
            decay_age = max(0, age_ms - freshness_ms)
            fraction = min(1.0, decay_age / denominator)
            confidence = initial_confidence - fraction * (
                initial_confidence - self.config.predicted_min_confidence
            )
            return {
                "state": "Predicted",
                "accuracy_m": None,
                "accuracy_status": "unavailable",
                "confidence": round(max(0.0, float(confidence)), 6),
                "source": "last_trusted",
                "uncertainty_m": round(uncertainty, 3),
                "uncertainty_basis": "last_trusted_age_growth_rule_v0",
                "reasons": [
                    "last_trusted_preserved",
                    "belief_forced_predicted" if self._force_predicted else "belief_aged",
                ],
            }

        return _unknown_belief(
            "prediction_horizon_exceeded", "last_trusted_retained_as_memory_only"
        )


def _unknown_belief(*reasons: str) -> dict[str, Any]:
    return {
        "state": "Unknown",
        "accuracy_m": None,
        "accuracy_status": "unavailable",
        "confidence": 0.0,
        "source": "none",
        "uncertainty_m": None,
        "uncertainty_basis": "unavailable",
        "reasons": list(reasons),
    }


def deepcopy_mapping(value: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        key: deepcopy_mapping(item) if isinstance(item, Mapping) else item
        for key, item in value.items()
    }

"""Configurable, deterministic Sensor Policy v0 for the sellable P0 path."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

from pc_simulator.location_engine_v0 import (
    BATTERY_STATES,
    GNSS_STATES,
    MOBILITY_STATES,
    SUPPORTED_EVENT_TYPES,
    LocationEngineConfig,
    has_attributable_observation_lineage,
)


CONFIG_CONTRACT_VERSION = "egolink.sensor_policy_config.v0.1"
SEMANTIC_VALIDATION_VERSION = "egolink.sensor_policy.semantic.v0.1"
DECISION_CONTRACT_VERSION = "egolink.sensor_policy_decision.v0.1"
POLICY_MODES = frozenset(
    {"STABLE", "MOVING", "LOCATION_UNCERTAIN", "SOS", "LOW_BATTERY"}
)


class SensorPolicyError(ValueError):
    """Raised when policy state or configuration violates the v0 contract."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _number(
    value: Any,
    name: str,
    *,
    minimum: float = 0.0,
    exclusive: bool = False,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SensorPolicyError(f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise SensorPolicyError(f"{name} must be finite")
    valid = number > minimum if exclusive else number >= minimum
    if not valid:
        operator = ">" if exclusive else ">="
        raise SensorPolicyError(f"{name} must be {operator} {minimum}")
    return number


def _duration_seconds(value: Any, name: str) -> float:
    number = _number(value, name, exclusive=True)
    if int(number * 1000) < 1:
        raise SensorPolicyError(f"{name} must round to at least one millisecond")
    return number


def _bounded_exponential_backoff(
    *, initial_s: float, multiplier: float, failure_count: int, maximum_s: float
) -> float:
    """Compute capped backoff without overflowing on a long failure run."""

    result = initial_s
    for _ in range(max(0, failure_count - 1)):
        if result >= maximum_s or result > maximum_s / multiplier:
            return maximum_s
        result *= multiplier
    return min(result, maximum_s)


def _integer(value: Any, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise SensorPolicyError(f"{name} must be an integer >= {minimum}")
    return value


def _object(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SensorPolicyError(f"{name} must be an object")
    return value


@dataclass(frozen=True)
class SensorPolicyConfig:
    """Validated immutable policy input plus its canonical identity."""

    values: dict[str, Any]
    config_hash: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "SensorPolicyConfig":
        copied = deepcopy(dict(value))
        _validate_config(copied)
        return cls(
            values=copied,
            config_hash=hashlib.sha256(canonical_json_bytes(copied)).hexdigest(),
        )

    @property
    def config_id(self) -> str:
        return str(self.values["config_id"])

    def location_engine_config(self) -> LocationEngineConfig:
        location = self.values["location"]
        return LocationEngineConfig(
            fine_max_accuracy_m=float(location["fine_max_accuracy_m"]),
            fine_max_hdop=float(location["fine_max_hdop"]),
            hdop_uncertainty_multiplier_m=float(
                location["hdop_uncertainty_multiplier_m"]
            ),
            coarse_max_uncertainty_m=float(location["coarse_max_uncertainty_m"]),
            fine_freshness_ms=int(float(location["fine_freshness_s"]) * 1000),
            coarse_freshness_ms=int(float(location["coarse_freshness_s"]) * 1000),
            prediction_horizon_ms=int(float(location["prediction_horizon_s"]) * 1000),
            uncertainty_growth_mps=float(location["uncertainty_growth_mps"]),
            fine_initial_confidence=float(location["fine_initial_confidence"]),
            coarse_initial_confidence=float(location["coarse_initial_confidence"]),
            predicted_min_confidence=float(location["predicted_min_confidence"]),
        )


def load_sensor_policy_config(path: str | Path) -> SensorPolicyConfig:
    config_path = Path(path)
    try:
        value = json.loads(
            config_path.read_text(encoding="utf-8"),
            parse_constant=lambda token: (_ for _ in ()).throw(
                SensorPolicyError(f"non-finite JSON constant is forbidden: {token}")
            ),
        )
    except (OSError, json.JSONDecodeError, SensorPolicyError) as exc:
        raise SensorPolicyError(f"unable to load sensor policy config: {exc}") from exc
    if not isinstance(value, Mapping):
        raise SensorPolicyError("sensor policy config root must be an object")
    return SensorPolicyConfig.from_mapping(value)


def _validate_exact_keys(
    value: Mapping[str, Any], required: set[str], name: str
) -> None:
    actual = set(value)
    missing = sorted(required - actual)
    extra = sorted(actual - required)
    if missing or extra:
        raise SensorPolicyError(
            f"{name} keys mismatch; missing={missing or []}, extra={extra or []}"
        )


def _validate_schedule(value: Any, name: str) -> None:
    schedule = _object(value, name)
    required = {
        "gnss_interval_s",
        "cell_interval_s",
        "imu_rate_hz",
        "lte_keep_connected",
    }
    _validate_exact_keys(schedule, required, name)
    _duration_seconds(schedule["gnss_interval_s"], f"{name}.gnss_interval_s")
    _duration_seconds(schedule["cell_interval_s"], f"{name}.cell_interval_s")
    _number(schedule["imu_rate_hz"], f"{name}.imu_rate_hz")
    if not isinstance(schedule["lte_keep_connected"], bool):
        raise SensorPolicyError(f"{name}.lte_keep_connected must be boolean")


def _validate_config(value: Mapping[str, Any]) -> None:
    required = {
        "contract_version",
        "semantic_validation",
        "config_id",
        "provenance",
        "stationary",
        "moving",
        "location_uncertain",
        "gnss",
        "cell",
        "movement",
        "location",
        "low_battery",
        "sos",
    }
    _validate_exact_keys(value, required, "config")
    if value["contract_version"] != CONFIG_CONTRACT_VERSION:
        raise SensorPolicyError(
            f"contract_version must be {CONFIG_CONTRACT_VERSION}"
        )
    if value["semantic_validation"] != SEMANTIC_VALIDATION_VERSION:
        raise SensorPolicyError(
            f"semantic_validation must be {SEMANTIC_VALIDATION_VERSION}"
        )
    if (
        not isinstance(value["config_id"], str)
        or not value["config_id"]
        or len(value["config_id"]) > 128
    ):
        raise SensorPolicyError("config_id must be a 1-128 character string")
    if value["provenance"] != "engineering_default_unverified":
        raise SensorPolicyError("provenance must remain engineering_default_unverified")

    for name in ("stationary", "moving", "location_uncertain"):
        _validate_schedule(value[name], name)

    gnss = _object(value["gnss"], "gnss")
    _validate_exact_keys(
        gnss,
        {
            "acquisition_timeout_s",
            "retry_backoff_s",
            "retry_backoff_multiplier",
            "max_retry_backoff_s",
        },
        "gnss",
    )
    _duration_seconds(gnss["acquisition_timeout_s"], "gnss.acquisition_timeout_s")
    initial_backoff = _duration_seconds(
        gnss["retry_backoff_s"], "gnss.retry_backoff_s"
    )
    _number(
        gnss["retry_backoff_multiplier"],
        "gnss.retry_backoff_multiplier",
        minimum=1.0,
    )
    max_backoff = _duration_seconds(
        gnss["max_retry_backoff_s"], "gnss.max_retry_backoff_s"
    )
    if max_backoff < initial_backoff:
        raise SensorPolicyError("gnss.max_retry_backoff_s must be >= retry_backoff_s")

    cell = _object(value["cell"], "cell")
    _validate_exact_keys(
        cell,
        {
            "request_timeout_s",
            "retry_backoff_s",
            "retry_backoff_multiplier",
            "max_retry_backoff_s",
        },
        "cell",
    )
    _duration_seconds(cell["request_timeout_s"], "cell.request_timeout_s")
    cell_initial_backoff = _duration_seconds(
        cell["retry_backoff_s"], "cell.retry_backoff_s"
    )
    _number(
        cell["retry_backoff_multiplier"],
        "cell.retry_backoff_multiplier",
        minimum=1.0,
    )
    cell_max_backoff = _duration_seconds(
        cell["max_retry_backoff_s"], "cell.max_retry_backoff_s"
    )
    if cell_max_backoff < cell_initial_backoff:
        raise SensorPolicyError("cell.max_retry_backoff_s must be >= retry_backoff_s")

    movement = _object(value["movement"], "movement")
    _validate_exact_keys(
        movement,
        {
            "window_s",
            "min_samples",
            "enter_rms_m_s2",
            "exit_rms_m_s2",
            "enter_windows",
            "exit_windows",
            "evidence_stale_after_s",
        },
        "movement",
    )
    _duration_seconds(movement["window_s"], "movement.window_s")
    _integer(movement["min_samples"], "movement.min_samples", minimum=2)
    enter_rms = _number(
        movement["enter_rms_m_s2"], "movement.enter_rms_m_s2", exclusive=True
    )
    exit_rms = _number(
        movement["exit_rms_m_s2"], "movement.exit_rms_m_s2"
    )
    if exit_rms >= enter_rms:
        raise SensorPolicyError(
            "movement.exit_rms_m_s2 must be < enter_rms_m_s2"
        )
    _integer(movement["enter_windows"], "movement.enter_windows", minimum=1)
    _integer(movement["exit_windows"], "movement.exit_windows", minimum=1)
    _duration_seconds(
        movement["evidence_stale_after_s"],
        "movement.evidence_stale_after_s",
    )

    location = _object(value["location"], "location")
    _validate_exact_keys(
        location,
        {
            "fine_max_accuracy_m",
            "fine_max_hdop",
            "hdop_uncertainty_multiplier_m",
            "coarse_max_uncertainty_m",
            "fine_freshness_s",
            "coarse_freshness_s",
            "prediction_horizon_s",
            "uncertainty_growth_mps",
            "uncertain_threshold_m",
            "fine_initial_confidence",
            "coarse_initial_confidence",
            "predicted_min_confidence",
        },
        "location",
    )
    fine_max = _number(
        location["fine_max_accuracy_m"], "location.fine_max_accuracy_m", exclusive=True
    )
    _number(location["fine_max_hdop"], "location.fine_max_hdop", exclusive=True)
    _number(
        location["hdop_uncertainty_multiplier_m"],
        "location.hdop_uncertainty_multiplier_m",
        exclusive=True,
    )
    coarse_max = _number(
        location["coarse_max_uncertainty_m"],
        "location.coarse_max_uncertainty_m",
        exclusive=True,
    )
    if coarse_max < fine_max:
        raise SensorPolicyError(
            "location.coarse_max_uncertainty_m must be >= fine_max_accuracy_m"
        )
    fine_freshness = _duration_seconds(
        location["fine_freshness_s"], "location.fine_freshness_s"
    )
    coarse_freshness = _duration_seconds(
        location["coarse_freshness_s"],
        "location.coarse_freshness_s",
    )
    horizon = _duration_seconds(
        location["prediction_horizon_s"],
        "location.prediction_horizon_s",
    )
    if horizon < max(fine_freshness, coarse_freshness):
        raise SensorPolicyError("location.prediction_horizon_s is shorter than freshness")
    _number(location["uncertainty_growth_mps"], "location.uncertainty_growth_mps")
    _number(
        location["uncertain_threshold_m"],
        "location.uncertain_threshold_m",
        exclusive=True,
    )
    for field in (
        "fine_initial_confidence",
        "coarse_initial_confidence",
        "predicted_min_confidence",
    ):
        confidence = _number(location[field], f"location.{field}")
        if confidence > 1.0:
            raise SensorPolicyError(f"location.{field} must be <= 1")
    if float(location["predicted_min_confidence"]) > min(
        float(location["fine_initial_confidence"]),
        float(location["coarse_initial_confidence"]),
    ):
        raise SensorPolicyError(
            "location.predicted_min_confidence cannot exceed initial confidence"
        )

    low_battery = _object(value["low_battery"], "low_battery")
    _validate_exact_keys(
        low_battery,
        {
            "enter_percent",
            "exit_percent",
            "critical_percent",
            "gnss_interval_s",
            "cell_interval_s",
            "imu_rate_hz",
            "lte_keep_connected",
        },
        "low_battery",
    )
    enter = _number(low_battery["enter_percent"], "low_battery.enter_percent")
    exit_value = _number(low_battery["exit_percent"], "low_battery.exit_percent")
    critical = _number(
        low_battery["critical_percent"], "low_battery.critical_percent"
    )
    if any(number > 100.0 for number in (enter, exit_value, critical)):
        raise SensorPolicyError("low_battery thresholds must be <= 100")
    if not critical <= enter < exit_value:
        raise SensorPolicyError(
            "low_battery thresholds must satisfy critical <= enter < exit"
        )
    _validate_schedule(
        {
            key: low_battery[key]
            for key in (
                "gnss_interval_s",
                "cell_interval_s",
                "imu_rate_hz",
                "lte_keep_connected",
            )
        },
        "low_battery.schedule",
    )

    sos = _object(value["sos"], "sos")
    _validate_exact_keys(
        sos,
        {
            "gnss_immediate",
            "gnss_retry_interval_s",
            "gnss_acquisition_timeout_s",
            "cell_interval_s",
            "imu_rate_hz",
            "lte_keep_connected",
            "upload_last_trusted",
            "start_ego_call",
        },
        "sos",
    )
    for field in (
        "gnss_immediate",
        "lte_keep_connected",
        "upload_last_trusted",
        "start_ego_call",
    ):
        if not isinstance(sos[field], bool):
            raise SensorPolicyError(f"sos.{field} must be boolean")
    for field in (
        "gnss_retry_interval_s",
        "gnss_acquisition_timeout_s",
        "cell_interval_s",
    ):
        _duration_seconds(sos[field], f"sos.{field}")
    _number(sos["imu_rate_hz"], "sos.imu_rate_hz")


def _validate_location_state(state: Mapping[str, Any]) -> None:
    if not isinstance(state, Mapping):
        raise SensorPolicyError("location_state must be an object")
    if state.get("contract_version") != "egolink.location_engine.v0.1":
        raise SensorPolicyError("location_state contract_version is unsupported")
    _integer(state.get("event_time_ms"), "location_state.event_time_ms")
    event_type = state.get("last_event_type")
    if not isinstance(event_type, str) or not event_type or len(event_type) > 64:
        raise SensorPolicyError("location_state.last_event_type is invalid")
    if state.get("mobility_state") not in MOBILITY_STATES:
        raise SensorPolicyError("location_state.mobility_state is invalid")
    if state.get("gnss_state") not in GNSS_STATES:
        raise SensorPolicyError("location_state.gnss_state is invalid")
    if state.get("battery_state") not in BATTERY_STATES:
        raise SensorPolicyError("location_state.battery_state is invalid")
    if state.get("location_belief") not in {"Fine", "Coarse", "Predicted", "Unknown"}:
        raise SensorPolicyError("location_state.location_belief is invalid")
    uncertainty = state.get("location_uncertainty_m")
    if uncertainty is not None:
        _number(uncertainty, "location_state.location_uncertainty_m")
    battery_percent = state.get("battery_percent")
    if battery_percent is not None:
        percent = _number(battery_percent, "location_state.battery_percent")
        if percent > 100.0:
            raise SensorPolicyError("location_state.battery_percent must be <= 100")
    if not isinstance(state.get("sos_active"), bool):
        raise SensorPolicyError("location_state.sos_active must be boolean")
    trusted_time = state.get("last_trusted_time_ms")
    if trusted_time is not None:
        trusted_time_value = _integer(
            trusted_time, "location_state.last_trusted_time_ms"
        )
        if trusted_time_value > int(state["event_time_ms"]):
            raise SensorPolicyError(
                "location_state.last_trusted_time_ms exceeds event time"
            )


@dataclass
class PolicyRuntimeState:
    mode: str = "STABLE"
    last_evaluation_ms: int | None = None
    low_battery_latched: bool = False
    rule_mobility_state: str = "unknown"
    last_imu_event_ms: int | None = None
    observed_mobility_state: str = "unknown"
    last_mobility_observation_ms: int | None = None
    movement_enter_windows: int = 0
    movement_exit_windows: int = 0
    last_gnss_attempt_ms: int | None = None
    gnss_acquisition_started_ms: int | None = None
    consecutive_no_fix: int = 0
    retry_not_before_ms: int | None = None
    last_cell_action_ms: int | None = None
    cell_request_started_ms: int | None = None
    consecutive_cell_timeouts: int = 0
    cell_retry_not_before_ms: int | None = None

    def snapshot(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "last_evaluation_ms": self.last_evaluation_ms,
            "low_battery_latched": self.low_battery_latched,
            "rule_mobility_state": self.rule_mobility_state,
            "last_imu_event_ms": self.last_imu_event_ms,
            "observed_mobility_state": self.observed_mobility_state,
            "last_mobility_observation_ms": self.last_mobility_observation_ms,
            "movement_enter_windows": self.movement_enter_windows,
            "movement_exit_windows": self.movement_exit_windows,
            "last_gnss_attempt_ms": self.last_gnss_attempt_ms,
            "gnss_acquisition_started_ms": self.gnss_acquisition_started_ms,
            "consecutive_no_fix": self.consecutive_no_fix,
            "retry_not_before_ms": self.retry_not_before_ms,
            "last_cell_action_ms": self.last_cell_action_ms,
            "cell_request_started_ms": self.cell_request_started_ms,
            "consecutive_cell_timeouts": self.consecutive_cell_timeouts,
            "cell_retry_not_before_ms": self.cell_retry_not_before_ms,
        }


class SensorPolicyV0:
    """Stateful scheduler whose history is exported on every decision."""

    def __init__(self, config: SensorPolicyConfig) -> None:
        self.config = config
        self.runtime = PolicyRuntimeState()
        self._imu_window: list[tuple[int, float]] = []

    def evaluate(
        self,
        location_state: Mapping[str, Any],
        *,
        event_type: str | None = None,
        observation: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        prior_runtime = deepcopy(self.runtime)
        prior_imu_window = list(self._imu_window)
        try:
            return self._evaluate_in_place(
                location_state, event_type=event_type, observation=observation
            )
        except Exception:
            self.runtime = prior_runtime
            self._imu_window = prior_imu_window
            raise

    def _evaluate_in_place(
        self,
        location_state: Mapping[str, Any],
        *,
        event_type: str | None,
        observation: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        _validate_location_state(location_state)
        event_time_ms = _integer(
            location_state.get("event_time_ms"), "location_state.event_time_ms"
        )
        if event_type is None:
            event_type = location_state.get("last_event_type", "tick")
        if not isinstance(event_type, str) or not event_type or len(event_type) > 64:
            raise SensorPolicyError("event_type must be a 1-64 character string")
        if event_type not in SUPPORTED_EVENT_TYPES:
            raise SensorPolicyError(f"unsupported event_type: {event_type}")
        if self.runtime.last_evaluation_ms is not None and event_time_ms < self.runtime.last_evaluation_ms:
            raise SensorPolicyError("policy event_time_ms regression")
        if observation is not None:
            observed_event_type = observation.get("event_type")
            if observed_event_type != event_type:
                raise SensorPolicyError("observation.event_type must match event_type")
            if observation.get("event_time_ms") != event_time_ms:
                raise SensorPolicyError(
                    "observation.event_time_ms must match location state event time"
                )
        if event_type in {"gnss_started", "gnss_stopped", "gnss_no_fix", "gnss_error"}:
            if observation is None or not has_attributable_observation_lineage(
                observation, event_time_ms
            ):
                raise SensorPolicyError(
                    f"{event_type} requires capture-bound or policy-action lineage"
                )
        self.runtime.last_evaluation_ms = event_time_ms
        self._apply_event_result(
            event_type, event_time_ms, location_state, observation=observation
        )
        if event_type == "imu_sample" and observation is not None:
            self._apply_imu_sample(observation, event_time_ms)
        self._update_low_battery_latch(location_state)

        conditions = self._conditions(location_state)
        previous_mode = self.runtime.mode
        mode = self._mode(conditions)
        sos_entry = mode == "SOS" and previous_mode != "SOS"
        reasons = self._transition_reasons(previous_mode, mode, conditions)
        schedule = self._schedule(mode)

        gnss = self._gnss_action(
            event_time_ms=event_time_ms,
            mode=mode,
            sos_entry=sos_entry,
            acquisition_timeout_s=float(schedule["gnss_acquisition_timeout_s"]),
            interval_s=float(schedule["gnss_interval_s"]),
        )
        cell = self._cell_action(
            event_time_ms=event_time_ms,
            interval_s=float(schedule["cell_interval_s"]),
            force=sos_entry,
        )

        accepted_location = (
            event_type == "gnss_fix" and location_state.get("gnss_state") == "fix"
        ) or (
            event_type == "coarse_location"
            and location_state.get("location_belief") == "Coarse"
        )
        upload_now = bool(accepted_location)
        if mode == "SOS" and (
            sos_entry or event_type in {"gnss_fix", "gnss_no_fix", "gnss_error"}
        ) and not accepted_location:
            upload_now = bool(self.config.values["sos"]["upload_last_trusted"])
        start_ego_call = sos_entry and bool(self.config.values["sos"]["start_ego_call"])

        self.runtime.mode = mode
        decision = {
            "contract_version": DECISION_CONTRACT_VERSION,
            "event_time_ms": event_time_ms,
            "config_id": self.config.config_id,
            "config_hash": self.config.config_hash,
            "policy_mode": mode,
            "derived_mobility_state": self._effective_mobility_state(
                location_state, event_time_ms
            ),
            "conditions": conditions,
            "transition": {
                "from": previous_mode,
                "to": mode,
                "changed": previous_mode != mode,
                "reason_codes": reasons,
            },
            "actions": {
                "imu": {"rate_hz": float(schedule["imu_rate_hz"])},
                "cell": cell,
                "gnss": gnss,
                "lte": {"keep_connected": bool(schedule["lte_keep_connected"])},
                "location": {"upload_now": upload_now},
                "ego_call": {"start_now": start_ego_call},
                "camera": {"requested": False, "action": "OFF"},
            },
            "next_evaluation_ms": self._next_evaluation_ms(
                event_time_ms,
                location_state=location_state,
                gnss=gnss,
                cell=cell,
                gnss_interval_s=float(schedule["gnss_interval_s"]),
                cell_interval_s=float(schedule["cell_interval_s"]),
            ),
            "runtime": self.runtime.snapshot(),
        }
        return decision

    def _apply_event_result(
        self,
        event_type: str,
        event_time_ms: int,
        location_state: Mapping[str, Any],
        *,
        observation: Mapping[str, Any] | None,
    ) -> None:
        if event_type == "gnss_started":
            self.runtime.last_gnss_attempt_ms = event_time_ms
            self.runtime.gnss_acquisition_started_ms = event_time_ms
        elif event_type == "gnss_fix" and location_state.get("gnss_state") == "fix":
            self.runtime.gnss_acquisition_started_ms = None
            self.runtime.consecutive_no_fix = 0
            self.runtime.retry_not_before_ms = None
            self.runtime.last_gnss_attempt_ms = event_time_ms
        elif event_type == "gnss_fix":
            self._record_gnss_failure(event_time_ms)
        elif event_type in {"gnss_no_fix", "gnss_error"}:
            self._record_gnss_failure(event_time_ms)
        elif event_type == "gnss_stopped":
            self.runtime.gnss_acquisition_started_ms = None
        elif event_type == "cell_observation":
            self.runtime.last_cell_action_ms = event_time_ms
            self.runtime.cell_request_started_ms = None
            self.runtime.consecutive_cell_timeouts = 0
            self.runtime.cell_retry_not_before_ms = None
        elif event_type == "mobility":
            if observation is None or not has_attributable_observation_lineage(
                observation, event_time_ms
            ):
                raise SensorPolicyError(
                    "mobility policy input requires attributable capture or rule lineage"
                )
            mobility = location_state.get("mobility_state")
            if mobility not in {"stable", "moving", "unknown"}:
                raise SensorPolicyError("location_state.mobility_state is invalid")
            self.runtime.observed_mobility_state = str(mobility)
            self.runtime.last_mobility_observation_ms = event_time_ms

    def _record_gnss_failure(
        self, event_time_ms: int, *, effective_mode: str | None = None
    ) -> None:
        self.runtime.gnss_acquisition_started_ms = None
        self.runtime.last_gnss_attempt_ms = event_time_ms
        self.runtime.consecutive_no_fix += 1
        gnss = self.config.values["gnss"]
        backoff_s = _bounded_exponential_backoff(
            initial_s=float(gnss["retry_backoff_s"]),
            multiplier=float(gnss["retry_backoff_multiplier"]),
            failure_count=self.runtime.consecutive_no_fix,
            maximum_s=float(gnss["max_retry_backoff_s"]),
        )
        if (effective_mode or self.runtime.mode) == "SOS":
            backoff_s = float(self.config.values["sos"]["gnss_retry_interval_s"])
        self.runtime.retry_not_before_ms = event_time_ms + int(backoff_s * 1000)

    def _apply_imu_sample(
        self, observation: Mapping[str, Any], event_time_ms: int
    ) -> None:
        value = observation.get("accel_m_s2")
        if (
            not isinstance(value, (list, tuple))
            or len(value) != 3
            or any(
                isinstance(component, bool)
                or not isinstance(component, (int, float))
                or not math.isfinite(float(component))
                for component in value
            )
        ):
            raise SensorPolicyError("imu_sample.accel_m_s2 must contain three finite numbers")
        magnitude = math.sqrt(sum(float(component) ** 2 for component in value))
        deviation = abs(magnitude - 9.80665)
        self.runtime.last_imu_event_ms = event_time_ms
        self._imu_window.append((event_time_ms, deviation))
        movement = self.config.values["movement"]
        window_ms = int(float(movement["window_s"]) * 1000)
        if self._imu_window[-1][0] - self._imu_window[0][0] < window_ms:
            return
        samples = self._imu_window
        self._imu_window = []
        if len(samples) < int(movement["min_samples"]):
            self.runtime.movement_enter_windows = 0
            self.runtime.movement_exit_windows = 0
            return
        rms = math.sqrt(sum(sample**2 for _, sample in samples) / len(samples))
        if rms >= float(movement["enter_rms_m_s2"]):
            self.runtime.movement_enter_windows += 1
            self.runtime.movement_exit_windows = 0
            if self.runtime.movement_enter_windows >= int(movement["enter_windows"]):
                self.runtime.rule_mobility_state = "moving"
        elif rms <= float(movement["exit_rms_m_s2"]):
            self.runtime.movement_exit_windows += 1
            self.runtime.movement_enter_windows = 0
            if self.runtime.movement_exit_windows >= int(movement["exit_windows"]):
                self.runtime.rule_mobility_state = "stable"
        else:
            self.runtime.movement_enter_windows = 0
            self.runtime.movement_exit_windows = 0

    def _effective_mobility_state(
        self, state: Mapping[str, Any], event_time_ms: int
    ) -> str:
        stale_after_ms = int(
            float(self.config.values["movement"]["evidence_stale_after_s"]) * 1000
        )
        if (
            self.runtime.last_imu_event_ms is not None
            and event_time_ms - self.runtime.last_imu_event_ms <= stale_after_ms
            and self.runtime.rule_mobility_state in {"stable", "moving"}
        ):
            return self.runtime.rule_mobility_state
        if (
            self.runtime.last_mobility_observation_ms is not None
            and event_time_ms - self.runtime.last_mobility_observation_ms
            <= stale_after_ms
            and self.runtime.observed_mobility_state in {"stable", "moving"}
        ):
            return self.runtime.observed_mobility_state
        return "unknown"

    def _update_low_battery_latch(self, state: Mapping[str, Any]) -> None:
        battery_state = state.get("battery_state")
        percent_value = state.get("battery_percent")
        thresholds = self.config.values["low_battery"]
        if battery_state in {"low", "critical"}:
            self.runtime.low_battery_latched = True
            return
        if isinstance(percent_value, (int, float)) and not isinstance(percent_value, bool):
            percent = float(percent_value)
            if percent <= float(thresholds["enter_percent"]):
                self.runtime.low_battery_latched = True
            elif percent >= float(thresholds["exit_percent"]) and battery_state in {
                "normal",
                "charging",
            }:
                self.runtime.low_battery_latched = False
        elif battery_state in {"normal", "charging"}:
            self.runtime.low_battery_latched = False

    def _conditions(self, state: Mapping[str, Any]) -> dict[str, bool]:
        uncertainty = state.get("location_uncertainty_m")
        threshold = float(self.config.values["location"]["uncertain_threshold_m"])
        uncertain = state.get("location_belief") in {"Unknown", "Predicted"}
        if isinstance(uncertainty, (int, float)) and not isinstance(uncertainty, bool):
            uncertain = uncertain or float(uncertainty) >= threshold
        mobility = self._effective_mobility_state(
            state, int(state.get("event_time_ms", 0))
        )
        return {
            "sos_active": state.get("sos_active") is True,
            "low_battery": self.runtime.low_battery_latched,
            "critical_battery": self._battery_is_critical(state),
            "location_uncertain": bool(uncertain),
            "moving": mobility == "moving",
        }

    def _battery_is_critical(self, state: Mapping[str, Any]) -> bool:
        if state.get("battery_state") == "critical":
            return True
        value = state.get("battery_percent")
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and float(value)
            <= float(self.config.values["low_battery"]["critical_percent"])
        )

    @staticmethod
    def _mode(conditions: Mapping[str, bool]) -> str:
        if conditions["sos_active"]:
            return "SOS"
        if conditions["low_battery"]:
            return "LOW_BATTERY"
        if conditions["location_uncertain"]:
            return "LOCATION_UNCERTAIN"
        if conditions["moving"]:
            return "MOVING"
        return "STABLE"

    @staticmethod
    def _transition_reasons(
        previous: str, current: str, conditions: Mapping[str, bool]
    ) -> list[str]:
        reasons = [f"effective_mode_{current.lower()}"]
        for name, active in conditions.items():
            if active:
                reasons.append(name)
        if previous != current:
            reasons.append(f"transition_{previous.lower()}_to_{current.lower()}")
        else:
            reasons.append("mode_unchanged")
        return reasons

    def _schedule(self, mode: str) -> dict[str, Any]:
        if mode == "SOS":
            sos = self.config.values["sos"]
            return {
                "gnss_interval_s": sos["gnss_retry_interval_s"],
                "gnss_acquisition_timeout_s": sos["gnss_acquisition_timeout_s"],
                "cell_interval_s": sos["cell_interval_s"],
                "imu_rate_hz": sos["imu_rate_hz"],
                "lte_keep_connected": sos["lte_keep_connected"],
            }
        if mode == "LOW_BATTERY":
            schedule = self.config.values["low_battery"]
        elif mode == "LOCATION_UNCERTAIN":
            schedule = self.config.values["location_uncertain"]
        elif mode == "MOVING":
            schedule = self.config.values["moving"]
        else:
            schedule = self.config.values["stationary"]
        return {
            **schedule,
            "gnss_acquisition_timeout_s": self.config.values["gnss"][
                "acquisition_timeout_s"
            ],
        }

    def _gnss_action(
        self,
        *,
        event_time_ms: int,
        mode: str,
        sos_entry: bool,
        acquisition_timeout_s: float,
        interval_s: float,
    ) -> dict[str, Any]:
        timeout_ms = int(acquisition_timeout_s * 1000)
        if self.runtime.gnss_acquisition_started_ms is not None:
            elapsed = event_time_ms - self.runtime.gnss_acquisition_started_ms
            if elapsed >= timeout_ms:
                self._record_gnss_failure(event_time_ms, effective_mode=mode)
                return {
                    "action": "stop_timeout",
                    "acquisition_timeout_s": acquisition_timeout_s,
                    "retry_not_before_ms": self.runtime.retry_not_before_ms,
                }
            return {
                "action": "continue",
                "acquisition_timeout_s": acquisition_timeout_s,
                "retry_not_before_ms": self.runtime.retry_not_before_ms,
            }

        sos_immediate = bool(self.config.values["sos"]["gnss_immediate"])
        if sos_entry and sos_immediate:
            self.runtime.retry_not_before_ms = None
            self.runtime.last_gnss_attempt_ms = event_time_ms
            self.runtime.gnss_acquisition_started_ms = event_time_ms
            return {
                "action": "start",
                "acquisition_timeout_s": acquisition_timeout_s,
                "retry_not_before_ms": None,
            }

        if (
            self.runtime.retry_not_before_ms is not None
            and event_time_ms < self.runtime.retry_not_before_ms
        ):
            return {
                "action": "wait_backoff",
                "acquisition_timeout_s": acquisition_timeout_s,
                "retry_not_before_ms": self.runtime.retry_not_before_ms,
            }
        if (
            self.runtime.retry_not_before_ms is not None
            and event_time_ms >= self.runtime.retry_not_before_ms
        ):
            self.runtime.retry_not_before_ms = None

        due = self.runtime.last_gnss_attempt_ms is None
        if self.runtime.last_gnss_attempt_ms is not None:
            due = event_time_ms - self.runtime.last_gnss_attempt_ms >= int(interval_s * 1000)
        if due:
            self.runtime.retry_not_before_ms = None
            self.runtime.last_gnss_attempt_ms = event_time_ms
            self.runtime.gnss_acquisition_started_ms = event_time_ms
            return {
                "action": "start",
                "acquisition_timeout_s": acquisition_timeout_s,
                "retry_not_before_ms": None,
            }
        return {
            "action": "wait_interval",
            "acquisition_timeout_s": acquisition_timeout_s,
            "retry_not_before_ms": self.runtime.retry_not_before_ms,
        }

    def _cell_action(
        self, *, event_time_ms: int, interval_s: float, force: bool
    ) -> dict[str, Any]:
        cell = self.config.values["cell"]
        timeout_s = float(cell["request_timeout_s"])
        timeout_ms = int(timeout_s * 1000)
        if self.runtime.cell_request_started_ms is not None:
            elapsed = event_time_ms - self.runtime.cell_request_started_ms
            if elapsed >= timeout_ms:
                self.runtime.cell_request_started_ms = None
                self.runtime.consecutive_cell_timeouts += 1
                backoff_s = _bounded_exponential_backoff(
                    initial_s=float(cell["retry_backoff_s"]),
                    multiplier=float(cell["retry_backoff_multiplier"]),
                    failure_count=self.runtime.consecutive_cell_timeouts,
                    maximum_s=float(cell["max_retry_backoff_s"]),
                )
                self.runtime.cell_retry_not_before_ms = event_time_ms + int(
                    backoff_s * 1000
                )
                return {
                    "action": "timeout",
                    "observe_now": False,
                    "interval_s": interval_s,
                    "request_timeout_s": timeout_s,
                    "retry_not_before_ms": self.runtime.cell_retry_not_before_ms,
                }
            return {
                "action": "continue",
                "observe_now": False,
                "interval_s": interval_s,
                "request_timeout_s": timeout_s,
                "retry_not_before_ms": self.runtime.cell_retry_not_before_ms,
            }
        if (
            self.runtime.cell_retry_not_before_ms is not None
            and event_time_ms >= self.runtime.cell_retry_not_before_ms
        ):
            self.runtime.cell_retry_not_before_ms = None
        if (
            self.runtime.cell_retry_not_before_ms is not None
            and event_time_ms < self.runtime.cell_retry_not_before_ms
            and not force
        ):
            return {
                "action": "wait_backoff",
                "observe_now": False,
                "interval_s": interval_s,
                "request_timeout_s": timeout_s,
                "retry_not_before_ms": self.runtime.cell_retry_not_before_ms,
            }
        due = force or self.runtime.last_cell_action_ms is None
        if self.runtime.last_cell_action_ms is not None:
            due = due or (
                event_time_ms - self.runtime.last_cell_action_ms >= int(interval_s * 1000)
            )
        if due:
            self.runtime.cell_retry_not_before_ms = None
            self.runtime.last_cell_action_ms = event_time_ms
            self.runtime.cell_request_started_ms = event_time_ms
            return {
                "action": "observe",
                "observe_now": True,
                "interval_s": interval_s,
                "request_timeout_s": timeout_s,
                "retry_not_before_ms": None,
            }
        return {
            "action": "wait_interval",
            "observe_now": False,
            "interval_s": interval_s,
            "request_timeout_s": timeout_s,
            "retry_not_before_ms": self.runtime.cell_retry_not_before_ms,
        }

    def _next_evaluation_ms(
        self,
        event_time_ms: int,
        *,
        location_state: Mapping[str, Any],
        gnss: Mapping[str, Any],
        cell: Mapping[str, Any],
        gnss_interval_s: float,
        cell_interval_s: float,
    ) -> int | None:
        candidates: list[int] = []

        def add_future(value: int | None) -> None:
            if value is not None and value > event_time_ms:
                candidates.append(value)

        if self.runtime.gnss_acquisition_started_ms is not None:
            add_future(
                self.runtime.gnss_acquisition_started_ms
                + int(float(gnss["acquisition_timeout_s"]) * 1000)
            )
        else:
            add_future(self.runtime.retry_not_before_ms)
            if self.runtime.last_gnss_attempt_ms is not None:
                add_future(
                    self.runtime.last_gnss_attempt_ms + int(gnss_interval_s * 1000)
                )
        if self.runtime.cell_request_started_ms is not None:
            add_future(
                self.runtime.cell_request_started_ms
                + int(float(cell["request_timeout_s"]) * 1000)
            )
        else:
            add_future(self.runtime.cell_retry_not_before_ms)
            if self.runtime.last_cell_action_ms is not None:
                add_future(
                    self.runtime.last_cell_action_ms + int(cell_interval_s * 1000)
                )

        last_trusted_time = location_state.get("last_trusted_time_ms")
        if isinstance(last_trusted_time, int) and not isinstance(last_trusted_time, bool):
            location = self.config.values["location"]
            belief = location_state.get("location_belief")
            if belief == "Fine":
                add_future(
                    last_trusted_time
                    + int(float(location["fine_freshness_s"]) * 1000)
                    + 1
                )
            elif belief == "Coarse":
                add_future(
                    last_trusted_time
                    + int(float(location["coarse_freshness_s"]) * 1000)
                    + 1
                )
            add_future(
                last_trusted_time
                + int(float(location["prediction_horizon_s"]) * 1000)
                + 1
            )

        stale_after_ms = int(
            float(self.config.values["movement"]["evidence_stale_after_s"]) * 1000
        )
        if self.runtime.rule_mobility_state in {"stable", "moving"}:
            add_future(
                self.runtime.last_imu_event_ms + stale_after_ms + 1
                if self.runtime.last_imu_event_ms is not None
                else None
            )
        if self.runtime.observed_mobility_state in {"stable", "moving"}:
            add_future(
                self.runtime.last_mobility_observation_ms + stale_after_ms + 1
                if self.runtime.last_mobility_observation_ms is not None
                else None
            )
        return min(candidates) if candidates else None

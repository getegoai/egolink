"""Replay Location Engine v0 and Sensor Policy v0 over accepted timelines.

The adapter reuses :mod:`pc_simulator.field_session_replay` for Field Session
loading, hash validation, timestamp lineage, and timeline construction.  It
does not use receive/ingest time as event time and does not synthesize missing
battery, connectivity, motion, or coordinates.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from pc_simulator import field_session_replay
from pc_simulator.location_engine_v0 import LocationEngineError, LocationEngineV0
from pc_simulator.sensor_policy_v0 import (
    SensorPolicyConfig,
    SensorPolicyError,
    SensorPolicyV0,
    canonical_json_bytes,
)


REPORT_CONTRACT_VERSION = "egolink.location_policy_replay.v0.1"
NORMALIZED_OBSERVATION_CONTRACT_VERSION = (
    "egolink.location_policy_observation.v0.1"
)
TRUSTED_FIELD_SOURCE_STATUSES = frozenset({"observed", "verified"})
LOCATION_EVIDENCE_EVENT_TYPES = frozenset(
    {"gnss_fix", "gnss_no_fix", "gnss_error", "coarse_location"}
)
MAX_DERIVED_TIMER_EVENTS = 10_000
PRIVATE_COORDINATE_KEYS = frozenset(
    {
        "lat",
        "lon",
        "latitude",
        "longitude",
        "latitude_deg",
        "longitude_deg",
        "coordinate",
        "coordinates",
        "position",
    }
)


class LocationPolicyReplayError(RuntimeError):
    """Raised when a replay input cannot be consumed without inventing truth."""


@dataclass(frozen=True)
class NormalizedTimeline:
    observations: list[dict[str, Any]]
    annotations: list[dict[str, Any]]
    input_record_count: int
    retained_evidence_count: int
    excluded_counts: dict[str, int]
    annotation_counts: dict[str, int]
    source_counts: dict[str, int]
    selected_policy_lane: str | None


@dataclass(frozen=True)
class LoadedNormalizedObservations:
    observations: list[dict[str, Any]]
    contract_version: str
    sha256: str
    record_count: int
    path: str


def stable_jsonl_bytes(rows: Iterable[Mapping[str, Any]]) -> bytes:
    return b"".join(canonical_json_bytes(dict(row)) + b"\n" for row in rows)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _first(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _bool_fix(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "fixed", "fix"}:
            return True
        if lowered in {"0", "false", "no", "no_fix", "nofix"}:
            return False
    return None


def _lineage(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "observation_id": row.get("observation_id"),
        "source": row.get("source"),
        "stream_id": row.get("stream_id"),
        "sequence_id": row.get("sequence_id"),
        "sample_index": row.get("sample_index"),
        "device_id": row.get("device_id"),
        "device_run_id": row.get("device_run_id"),
        "boot_count": row.get("boot_count"),
        "timestamp_monotonic_ns": row.get("timestamp_monotonic_ns"),
        "timestamp_utc_ns": row.get("timestamp_utc_ns"),
        "gnss_source_utc_ns": row.get("gnss_source_utc_ns"),
        "timestamp_utc_origin": row.get("timestamp_utc_origin"),
        "monotonic_clock_domain_id": row.get("monotonic_clock_domain_id"),
        "alignment_status": row.get("alignment_status"),
        "timestamp_uncertainty_ns": row.get("timestamp_uncertainty_ns"),
        "source_status": row.get("source_status"),
        "cross_source_order": row.get("cross_source_order"),
        "payload_artifact": deepcopy(row.get("payload_artifact")),
    }


def _event(
    row: Mapping[str, Any],
    event_type: str,
    event_time_ms: int,
    *,
    suffix: str,
    ordering_scope: str,
    event_time_basis: str,
    **values: Any,
) -> dict[str, Any]:
    lineage = _lineage(row)
    base_id = lineage.get("observation_id") or "unidentified"
    lineage["normalized_observation_id"] = f"{base_id}:{suffix}"
    lineage["event_time_source"] = "capture_event"
    return {
        "contract_version": NORMALIZED_OBSERVATION_CONTRACT_VERSION,
        "event_type": event_type,
        "event_time_ms": event_time_ms,
        **values,
        "lineage": lineage,
        "evidence": {
            "kind": "field_session_observation",
            "source_status": lineage.get("source_status"),
            "ordering_scope": ordering_scope,
            "event_time_basis": event_time_basis,
            "policy_eligible": True,
        },
    }


def _annotation(
    row: Mapping[str, Any],
    reason: str,
    *,
    event_time_ms: int | None,
    event_time_basis: str | None,
    annotation_type: str | None = None,
) -> dict[str, Any]:
    value = {
        "reason": reason,
        "annotation_type": annotation_type,
        "event_time_ms": event_time_ms,
        "event_time_basis": event_time_basis,
        "lineage": _lineage(row),
        "policy_eligible": False,
    }
    return {key: item for key, item in value.items() if item is not None}


def _integer_ns(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _policy_clock(
    row: Mapping[str, Any],
) -> tuple[str, int, str, str] | None:
    """Return a policy-safe lane and time without inventing cross-source order."""

    source = str(row.get("source") or "unknown")
    cross_source_order = row.get("cross_source_order")
    aligned_utc_ns = _integer_ns(row.get("timestamp_utc_ns"))
    if (
        aligned_utc_ns is not None
        and cross_source_order == "ordered_with_declared_uncertainty"
    ):
        return (
            "cross_source_utc",
            aligned_utc_ns,
            "cross_source",
            "aligned_utc",
        )

    # An unavailable cross-source relation does not invalidate GNSS's own
    # capture clock.  Keep it in a single-source lane and never interleave it
    # with another clock domain.
    if source != "gnss":
        return None
    direct_gnss_ns = _integer_ns(row.get("gnss_source_utc_ns"))
    if direct_gnss_ns is not None:
        return (
            "source:gnss:direct_utc",
            direct_gnss_ns,
            "same_source_only",
            "gnss_direct_source_utc",
        )
    if aligned_utc_ns is not None:
        run = str(row.get("device_run_id") or "unknown_run")
        return (
            f"source:gnss:{run}:aligned_utc",
            aligned_utc_ns,
            "same_source_only",
            "aligned_utc_same_source_only",
        )
    monotonic_ns = _integer_ns(row.get("timestamp_monotonic_ns"))
    if monotonic_ns is not None:
        domain = str(
            row.get("monotonic_clock_domain_id")
            or f"boot-{row.get('boot_count', 'unknown')}"
        )
        return (
            f"source:gnss:{domain}:monotonic",
            monotonic_ns,
            "same_source_only",
            "boot_monotonic_same_source_only",
        )
    return None


def _annotation_clock(row: Mapping[str, Any]) -> tuple[int | None, str | None]:
    for field, basis in (
        ("timestamp_utc_ns", "aligned_or_source_utc_annotation"),
        ("gnss_source_utc_ns", "gnss_source_utc_annotation"),
        ("timestamp_monotonic_ns", "source_monotonic_annotation"),
    ):
        value = _integer_ns(row.get(field))
        if value is not None:
            return value // 1_000_000, basis
    return None, None


def _normalized_events_from_row(
    row: Mapping[str, Any],
    event_time_ms: int,
    *,
    ordering_scope: str,
    event_time_basis: str,
) -> list[dict[str, Any]]:
    source = str(row.get("source") or "unknown")
    payload = _mapping(row.get("payload"))
    events: list[dict[str, Any]] = []

    gnss = _mapping(payload.get("gnss"))
    if source == "gnss" or gnss:
        source_payload = payload if source == "gnss" else gnss
        fix = _bool_fix(_first(source_payload.get("fix"), payload.get("fix")))
        if fix is True:
            events.append(
                _event(
                    row,
                    "gnss_fix",
                    event_time_ms,
                    suffix="gnss_fix",
                    ordering_scope=ordering_scope,
                    event_time_basis=event_time_basis,
                    latitude_deg=_first(
                        source_payload.get("latitude_deg"),
                        source_payload.get("latitude"),
                        source_payload.get("lat"),
                        payload.get("latitude_deg"),
                        payload.get("latitude"),
                        payload.get("lat"),
                    ),
                    longitude_deg=_first(
                        source_payload.get("longitude_deg"),
                        source_payload.get("longitude"),
                        source_payload.get("lon"),
                        payload.get("longitude_deg"),
                        payload.get("longitude"),
                        payload.get("lon"),
                    ),
                    accuracy_m=_first(
                        source_payload.get("accuracy_m"),
                        source_payload.get("horizontal_accuracy_m"),
                        payload.get("accuracy_m"),
                        payload.get("horizontal_accuracy_m"),
                    ),
                    hdop=_first(source_payload.get("hdop"), payload.get("hdop")),
                )
            )
        elif fix is False:
            events.append(
                _event(
                    row,
                    "gnss_no_fix",
                    event_time_ms,
                    suffix="gnss_no_fix",
                    ordering_scope=ordering_scope,
                    event_time_basis=event_time_basis,
                )
            )

    # Raw/calibrated IMU evidence is retained as an observation, but replay
    # does not promote an arbitrary payload label to mobility truth.  A future
    # movement rule must emit the engine's explicit rule_derived lineage.
    if source == "imu":
        calibrated = _mapping(payload.get("calibrated"))
        imu = _mapping(payload.get("imu"))
        accel_m_s2 = _first(
            calibrated.get("accel_m_s2"),
            imu.get("accel_m_s2"),
            payload.get("accel_m_s2"),
        )
        if isinstance(accel_m_s2, (list, tuple)) and len(accel_m_s2) == 3:
            events.append(
                _event(
                    row,
                    "imu_sample",
                    event_time_ms,
                    suffix=f"imu_sample_{row.get('sample_index', 'window')}",
                    ordering_scope=ordering_scope,
                    event_time_basis=event_time_basis,
                    sample_index=row.get("sample_index"),
                    accel_m_s2=list(accel_m_s2),
                )
            )

    power = _mapping(payload.get("power"))
    percent = _first(
        power.get("battery_percent"),
        power.get("soc_pct"),
        payload.get("battery_percent"),
        payload.get("soc_pct"),
    )
    battery_state = _first(power.get("state"), payload.get("battery_state"))
    if percent is not None or battery_state is not None:
        normalized_battery = (
            battery_state.strip().lower()
            if isinstance(battery_state, str)
            else "unknown"
        )
        if normalized_battery not in {"normal", "low", "critical", "charging", "unknown"}:
            normalized_battery = "unknown"
        events.append(
            _event(
                row,
                "battery",
                event_time_ms,
                suffix="battery",
                ordering_scope=ordering_scope,
                event_time_basis=event_time_basis,
                battery_state=normalized_battery,
                battery_percent=percent,
            )
        )

    cell = _mapping(payload.get("cell"))
    if source in {"lte", "cell"} and (cell or payload.get("cell_id") is not None):
        events.append(
            _event(
                row,
                "cell_observation",
                event_time_ms,
                suffix="cell",
                ordering_scope=ordering_scope,
                event_time_basis=event_time_basis,
            )
        )
    elif source == "lte" and payload.get("lte_state") is not None:
        events.append(
            _event(
                row,
                "lte_state",
                event_time_ms,
                suffix="lte_state",
                ordering_scope=ordering_scope,
                event_time_basis=event_time_basis,
                lte_state=str(payload["lte_state"]).lower(),
            )
        )

    sos = _mapping(payload.get("sos"))
    sos_active = _first(sos.get("active"), payload.get("sos_active"))
    if source == "sos" and isinstance(sos_active, bool):
        events.append(
            _event(
                row,
                "sos",
                event_time_ms,
                suffix="sos",
                ordering_scope=ordering_scope,
                event_time_basis=event_time_basis,
                active=sos_active,
            )
        )
    return events


def normalize_field_timeline(
    timeline: Sequence[Mapping[str, Any]],
) -> NormalizedTimeline:
    """Convert the accepted timeline without inventing cross-source order."""

    observations: list[dict[str, Any]] = []
    annotations: list[dict[str, Any]] = []
    excluded: Counter[str] = Counter()
    annotation_counts: Counter[str] = Counter()
    sources: Counter[str] = Counter()
    retained_evidence_count = 0
    candidates: dict[
        str, list[tuple[int, Mapping[str, Any], list[dict[str, Any]]]]
    ] = {}

    for ordinal, row in enumerate(timeline):
        source = str(row.get("source") or "unknown")
        sources[source] += 1
        if row.get("masked") is True or row.get("available_to_estimator") is False:
            excluded["masked_or_unavailable_to_estimator"] += 1
            continue
        source_status = row.get("source_status")
        event_time_ms, annotation_time_basis = _annotation_clock(row)

        if source == "manual_event" and source_status == "operator_weak_label":
            retained_evidence_count += 1
            manual_type = str(_mapping(row.get("payload")).get("event_type") or "OTHER")
            annotations.append(
                _annotation(
                    row,
                    "operator_weak_label_not_policy_input",
                    event_time_ms=event_time_ms,
                    event_time_basis=annotation_time_basis,
                    annotation_type=manual_type,
                )
            )
            annotation_counts["operator_weak_label_not_policy_input"] += 1
            continue
        if source == "camera":
            if source_status in TRUSTED_FIELD_SOURCE_STATUSES:
                retained_evidence_count += 1
            annotations.append(
                _annotation(
                    row,
                    "camera_experimental_not_policy_input",
                    event_time_ms=event_time_ms,
                    event_time_basis=annotation_time_basis,
                )
            )
            annotation_counts["camera_experimental_not_policy_input"] += 1
            continue
        if source_status not in TRUSTED_FIELD_SOURCE_STATUSES:
            excluded["source_not_trusted"] += 1
            continue
        retained_evidence_count += 1

        clock = _policy_clock(row)
        if clock is None:
            annotations.append(
                _annotation(
                    row,
                    "policy_event_time_or_order_unavailable",
                    event_time_ms=event_time_ms,
                    event_time_basis=annotation_time_basis,
                )
            )
            annotation_counts["policy_event_time_or_order_unavailable"] += 1
            continue
        lane, event_time_ns, ordering_scope, event_time_basis = clock
        normalized = _normalized_events_from_row(
            row,
            event_time_ns // 1_000_000,
            ordering_scope=ordering_scope,
            event_time_basis=event_time_basis,
        )
        if not normalized:
            annotations.append(
                _annotation(
                    row,
                    "source_payload_not_consumed_by_policy_v0",
                    event_time_ms=event_time_ns // 1_000_000,
                    event_time_basis=event_time_basis,
                )
            )
            annotation_counts["source_payload_not_consumed_by_policy_v0"] += 1
            continue
        candidates.setdefault(lane, []).append((ordinal, row, normalized))

    selected_policy_lane: str | None = None
    cross_source = candidates.get("cross_source_utc", [])
    cross_has_gnss = any(
        event.get("event_type", "").startswith("gnss_")
        for _ordinal, _row, events in cross_source
        for event in events
    )
    if cross_source and cross_has_gnss:
        selected_policy_lane = "cross_source_utc"
    else:
        gnss_lanes = sorted(
            (
                (lane, sum(len(events) for _ordinal, _row, events in rows))
                for lane, rows in candidates.items()
                if lane.startswith("source:gnss:")
            ),
            key=lambda item: (-item[1], item[0]),
        )
        if gnss_lanes:
            selected_policy_lane = gnss_lanes[0][0]
        elif cross_source:
            selected_policy_lane = "cross_source_utc"

    for lane, rows in candidates.items():
        if lane == selected_policy_lane:
            for ordinal, _row, events in rows:
                for event_ordinal, event in enumerate(events):
                    event["_normalization_order"] = [ordinal, event_ordinal]
                    observations.append(event)
            continue
        for _ordinal, row, _events in rows:
            event_time_ms, event_time_basis = _annotation_clock(row)
            annotations.append(
                _annotation(
                    row,
                    "policy_clock_lane_not_selected",
                    event_time_ms=event_time_ms,
                    event_time_basis=event_time_basis,
                )
            )
            annotation_counts["policy_clock_lane_not_selected"] += 1

    observations.sort(
        key=lambda event: (
            int(event["event_time_ms"]),
            event.get("_normalization_order", [0, 0]),
        )
    )
    last_event_time_ms: int | None = None
    for observation in observations:
        observation.pop("_normalization_order", None)
        current = int(observation["event_time_ms"])
        if last_event_time_ms is not None and current < last_event_time_ms:
            raise LocationPolicyReplayError(
                "selected policy clock lane regressed; receive time will not be substituted"
            )
        last_event_time_ms = current

    return NormalizedTimeline(
        observations=observations,
        annotations=annotations,
        input_record_count=len(timeline),
        retained_evidence_count=retained_evidence_count,
        excluded_counts=dict(sorted(excluded.items())),
        annotation_counts=dict(sorted(annotation_counts.items())),
        source_counts=dict(sorted(sources.items())),
        selected_policy_lane=selected_policy_lane,
    )


def _engine_observation(observation: Mapping[str, Any]) -> dict[str, Any]:
    return deepcopy(dict(observation))


def _effective_policy_event_type(
    source_event_type: str, location_state: Mapping[str, Any]
) -> str:
    # Policy v0 consumes the engine outcome alongside the original event type,
    # so a rejected fix remains attributable as a rejected fix rather than
    # being relabelled as another sensor result.
    del location_state
    return source_event_type


def _timer_observation(
    *,
    event_type: str,
    event_time_ms: int,
    timer_kind: str,
    ordinal: int,
    basis_observation_id: str,
) -> dict[str, Any]:
    observation_id = f"policy-timer:{timer_kind}:{event_time_ms}:{ordinal}"
    lineage = {
        "observation_id": observation_id,
        "normalized_observation_id": observation_id,
        "source": "policy_timer",
        "source_status": "rule_derived",
        "event_time_source": "policy_rule_v0",
        "basis_observation_ids": [basis_observation_id],
    }
    return {
        "contract_version": NORMALIZED_OBSERVATION_CONTRACT_VERSION,
        "event_type": event_type,
        "event_time_ms": event_time_ms,
        "lineage": lineage,
        "evidence": {
            "kind": "derived_policy_timer",
            "source_status": "rule_derived",
            "timer_kind": timer_kind,
            "basis_observation_ids": [basis_observation_id],
            "policy_eligible": True,
        },
    }


def _next_policy_timer_deadline(
    decision: Mapping[str, Any], after_ms: int
) -> tuple[str, int] | None:
    deadline = decision.get("next_evaluation_ms")
    if isinstance(deadline, int) and not isinstance(deadline, bool) and deadline > after_ms:
        return "policy_next_evaluation", deadline
    return None


def _location_reference(state: Mapping[str, Any], fallback: str | None) -> str | None:
    location = _mapping(state.get("last_trusted_location"))
    evidence = _mapping(location.get("evidence_ref"))
    observation_id = evidence.get("observation_id")
    if isinstance(observation_id, str) and observation_id:
        return observation_id
    return fallback


def _privacy_safe_location_state(
    state: Mapping[str, Any], fallback_reference: str | None
) -> dict[str, Any]:
    safe = deepcopy(dict(state))
    location = safe.pop("last_trusted_location", None)
    reference = _location_reference(state, fallback_reference)
    safe["last_trusted_location"] = None
    safe["last_trusted_location_ref"] = reference if location is not None else None
    return safe


def _strip_private_coordinates(value: Any) -> Any:
    if isinstance(value, Mapping):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if str(key).strip().lower() in PRIVATE_COORDINATE_KEYS:
                continue
            cleaned[str(key)] = _strip_private_coordinates(item)
        return cleaned
    if isinstance(value, list):
        return [_strip_private_coordinates(item) for item in value]
    return deepcopy(value)


def _time_weighted_location_metrics(
    trace: Sequence[Mapping[str, Any]],
) -> dict[str, int | float]:
    if not trace:
        return {
            "replayed_duration_ms": 0,
            "location_available_duration_ms": 0,
            "location_available_time_ratio": 0.0,
        }
    replayed_duration_ms = max(
        0,
        int(trace[-1]["input"]["event_time_ms"])
        - int(trace[0]["input"]["event_time_ms"]),
    )
    available_duration_ms = 0
    for current, following in zip(trace, trace[1:]):
        start = int(current["input"]["event_time_ms"])
        end = int(following["input"]["event_time_ms"])
        if _mapping(current.get("location_state")).get("location_belief") != "Unknown":
            available_duration_ms += max(0, end - start)
    ratio = (
        round(available_duration_ms / replayed_duration_ms, 6)
        if replayed_duration_ms
        else 0.0
    )
    return {
        "replayed_duration_ms": replayed_duration_ms,
        "location_available_duration_ms": available_duration_ms,
        "location_available_time_ratio": ratio,
    }


def _behavior_trace(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    result = deepcopy(list(report.get("trace") or []))
    for row in result:
        decision = _mapping(row.get("policy_decision"))
        if isinstance(decision, dict):
            decision.pop("config_id", None)
            decision.pop("config_hash", None)
    return result


def replay_observations(
    observations: Sequence[Mapping[str, Any]],
    config: SensorPolicyConfig,
    *,
    input_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    engine = LocationEngineV0(config.location_engine_config())
    policy = SensorPolicyV0(config)
    trace: list[dict[str, Any]] = []
    belief_counts: Counter[str] = Counter()
    policy_counts: Counter[str] = Counter()
    gnss_intents: Counter[str] = Counter()
    gnss_results: Counter[str] = Counter()
    cell_observation_count = 0
    maximum_uncertainty: float | None = None
    last_time_ms: int | None = None
    last_external_time_ms: int | None = None
    last_decision: dict[str, Any] | None = None
    last_basis_observation_id = "replay_start"
    trusted_location_reference: str | None = None
    derived_timer_event_count = 0
    external_observation_count = 0
    external_evidence_observation_count = 0
    external_location_evidence_observation_count = 0

    def append_step(
        observation: Mapping[str, Any],
        *,
        origin: str,
    ) -> dict[str, Any]:
        nonlocal last_time_ms
        nonlocal last_decision
        nonlocal last_basis_observation_id
        nonlocal trusted_location_reference
        nonlocal derived_timer_event_count
        nonlocal external_observation_count
        nonlocal external_evidence_observation_count
        nonlocal external_location_evidence_observation_count
        nonlocal cell_observation_count
        nonlocal maximum_uncertainty

        event_time_ms = observation.get("event_time_ms")
        if isinstance(event_time_ms, bool) or not isinstance(event_time_ms, int):
            raise LocationPolicyReplayError("policy observation has invalid event_time_ms")
        if last_time_ms is not None and event_time_ms < last_time_ms:
            raise LocationPolicyReplayError(
                "normalized observations must retain nondecreasing event time"
            )
        source_event_type = str(observation.get("event_type") or "")
        if not source_event_type:
            raise LocationPolicyReplayError("policy observation has no event_type")

        raw_state = engine.process(_engine_observation(observation))
        policy_event_type = _effective_policy_event_type(
            source_event_type, raw_state
        )
        decision = policy.evaluate(
            raw_state,
            event_type=policy_event_type,
            observation=observation,
        )
        engine.set_policy_context(decision["policy_mode"])
        raw_state = engine.snapshot(event_time_ms)
        lineage = deepcopy(_mapping(observation.get("lineage")))
        evidence = deepcopy(_mapping(observation.get("evidence")))
        normalized_id = _first(
            lineage.get("normalized_observation_id"),
            lineage.get("observation_id"),
        )
        if origin == "external" and isinstance(normalized_id, str) and normalized_id:
            last_basis_observation_id = normalized_id
        trusted_location_reference = _location_reference(
            raw_state, trusted_location_reference or last_basis_observation_id
        )
        safe_state = _privacy_safe_location_state(
            raw_state, trusted_location_reference
        )
        row = {
            "step": len(trace),
            "input": {
                "source_event_type": source_event_type,
                "policy_event_type": policy_event_type,
                "event_time_ms": event_time_ms,
                "origin": origin,
                "lineage": lineage,
                "evidence": evidence,
                "policy_observation": {
                    "contract_version": NORMALIZED_OBSERVATION_CONTRACT_VERSION,
                    "event_type": policy_event_type,
                    "event_time_ms": event_time_ms,
                    "derived_from_event_type": source_event_type,
                    "normalized_observation_id": normalized_id,
                },
            },
            "location_state": safe_state,
            "policy_decision": decision,
        }
        trace.append(row)
        belief_counts[str(safe_state["location_belief"])] += 1
        policy_counts[str(decision["policy_mode"])] += 1
        gnss_intents[str(decision["actions"]["gnss"]["action"])] += 1
        if source_event_type in {"gnss_fix", "gnss_no_fix", "gnss_error"}:
            result_key = (
                "gnss_fix_rejected"
                if source_event_type == "gnss_fix"
                and safe_state.get("gnss_state") != "fix"
                else source_event_type
            )
            gnss_results[result_key] += 1
        if origin == "external":
            external_observation_count += 1
            if source_event_type != "tick":
                external_evidence_observation_count += 1
            if source_event_type in LOCATION_EVIDENCE_EVENT_TYPES:
                external_location_evidence_observation_count += 1
            if source_event_type == "cell_observation":
                cell_observation_count += 1
        else:
            derived_timer_event_count += 1
        uncertainty = safe_state.get("location_uncertainty_m")
        if isinstance(uncertainty, (int, float)) and not isinstance(uncertainty, bool):
            maximum_uncertainty = max(
                float(uncertainty),
                maximum_uncertainty
                if maximum_uncertainty is not None
                else float(uncertainty),
            )
        last_time_ms = event_time_ms
        last_decision = decision
        return decision

    def drive_policy_timers_before(until_ms: int) -> None:
        while last_decision is not None and last_time_ms is not None:
            timer = _next_policy_timer_deadline(last_decision, last_time_ms)
            if timer is None:
                return
            timer_kind, deadline_ms = timer
            if deadline_ms >= until_ms:
                return
            if derived_timer_event_count >= MAX_DERIVED_TIMER_EVENTS:
                raise LocationPolicyReplayError("derived policy timer limit exceeded")
            append_step(
                _timer_observation(
                    event_type="tick",
                    event_time_ms=deadline_ms,
                    timer_kind=timer_kind,
                    ordinal=derived_timer_event_count,
                    basis_observation_id=last_basis_observation_id,
                ),
                origin="policy_timer",
            )

    try:
        for index, observation in enumerate(observations):
            event_time_ms = observation.get("event_time_ms")
            if isinstance(event_time_ms, bool) or not isinstance(event_time_ms, int):
                raise LocationPolicyReplayError(
                    f"normalized observation {index} has invalid event_time_ms"
                )
            if last_external_time_ms is not None and event_time_ms < last_external_time_ms:
                raise LocationPolicyReplayError(
                    "normalized observations must retain nondecreasing event time"
                )
            drive_policy_timers_before(event_time_ms)
            append_step(observation, origin="external")
            last_external_time_ms = event_time_ms
    except (LocationEngineError, SensorPolicyError) as exc:
        raise LocationPolicyReplayError(str(exc)) from exc

    run_status = (
        "completed"
        if external_location_evidence_observation_count > 0
        else "insufficient_evidence"
    )
    time_metrics = _time_weighted_location_metrics(trace)
    report = {
        "contract_version": REPORT_CONTRACT_VERSION,
        "run_status": run_status,
        "insufficient_evidence_reasons": (
            []
            if run_status == "completed"
            else ["no_external_location_evidence_observation"]
        ),
        "input": deepcopy(dict(input_metadata or {})),
        "config": {
            "config_id": config.config_id,
            "config_hash": config.config_hash,
            "provenance": config.values["provenance"],
        },
        "trace": trace,
        "metrics": {
            "external_observation_count": external_observation_count,
            "external_evidence_observation_count": external_evidence_observation_count,
            "external_location_evidence_observation_count": (
                external_location_evidence_observation_count
            ),
            "derived_policy_timer_event_count": derived_timer_event_count,
            "trace_step_count": len(trace),
            **time_metrics,
            "belief_counts": dict(sorted(belief_counts.items())),
            "policy_mode_counts": dict(sorted(policy_counts.items())),
            "gnss_intent_counts": dict(sorted(gnss_intents.items())),
            "gnss_result_counts": dict(sorted(gnss_results.items())),
            "cell_observation_count": cell_observation_count,
            "maximum_replayed_uncertainty_m": maximum_uncertainty,
            "camera_request_count": 0,
        },
        "final_state": (
            trace[-1]["location_state"]
            if trace
            else _privacy_safe_location_state(engine.snapshot(), None)
        ),
        "privacy": {
            "precise_coordinates_included": False,
            "location_representation": "evidence_reference_only",
        },
        "non_claims": [
            "no_measured_battery_savings_claim",
            "no_ground_truth_accuracy_claim_without_source_ground_truth",
            "no_hardware_acceptance_claim",
            "no_camera_or_ai_decision",
        ],
        "hardware_claim": "unverified",
    }
    safe_report = _strip_private_coordinates(report)
    safe_report["canonical_sha256"] = hashlib.sha256(
        canonical_json_bytes(safe_report)
    ).hexdigest()
    return safe_report


def replay_field_session(
    manifest_path: str | Path, config: SensorPolicyConfig
) -> dict[str, Any]:
    """Load and hash-check one sealed Session, then reuse its accepted timeline."""

    path = Path(manifest_path)
    package = field_session_replay.load_replay_package(path)
    timeline, timeline_summary = field_session_replay.build_replay_timeline(package)
    normalized = normalize_field_timeline(timeline)
    metadata = {
        "kind": "sealed_field_session",
        "manifest_path": str(path),
        "manifest_sha256": field_session_replay.sha256_file(path),
        "timeline_sha256": hashlib.sha256(stable_jsonl_bytes(timeline)).hexdigest(),
        "timeline_summary": timeline_summary,
        "input_record_count": normalized.input_record_count,
        "normalized_observation_count": len(normalized.observations),
        "retained_evidence_count": normalized.retained_evidence_count,
        "evidence_annotation_count": len(normalized.annotations),
        "evidence_annotations": normalized.annotations,
        "excluded_counts": normalized.excluded_counts,
        "annotation_counts": normalized.annotation_counts,
        "source_counts": normalized.source_counts,
        "selected_policy_lane": normalized.selected_policy_lane,
        "field_session_validation": deepcopy(package.validation),
    }
    return replay_observations(normalized.observations, config, input_metadata=metadata)


def compare_replay_reports(
    baseline: Mapping[str, Any], candidate: Mapping[str, Any]
) -> dict[str, Any]:
    """Compare simulated policy effects without translating them into savings."""

    left = _mapping(baseline.get("metrics"))
    right = _mapping(candidate.get("metrics"))
    numeric_fields = (
        "external_observation_count",
        "external_evidence_observation_count",
        "external_location_evidence_observation_count",
        "derived_policy_timer_event_count",
        "trace_step_count",
        "replayed_duration_ms",
        "location_available_duration_ms",
        "location_available_time_ratio",
        "cell_observation_count",
        "maximum_replayed_uncertainty_m",
        "camera_request_count",
    )
    deltas: dict[str, float | int | None] = {}
    for field in numeric_fields:
        left_value = left.get(field)
        right_value = right.get(field)
        if isinstance(left_value, (int, float)) and isinstance(right_value, (int, float)):
            deltas[field] = right_value - left_value
        else:
            deltas[field] = None
    left_config = _mapping(baseline.get("config"))
    right_config = _mapping(candidate.get("config"))
    left_behavior = _behavior_trace(baseline)
    right_behavior = _behavior_trace(candidate)
    left_behavior_hash = hashlib.sha256(canonical_json_bytes(left_behavior)).hexdigest()
    right_behavior_hash = hashlib.sha256(canonical_json_bytes(right_behavior)).hexdigest()
    evidence_sufficient = (
        baseline.get("run_status") == "completed"
        and candidate.get("run_status") == "completed"
    )
    behavior_equal = left_behavior == right_behavior
    return {
        "contract_version": "egolink.location_policy_replay_compare.v0.1",
        "status": (
            "insufficient_evidence"
            if not evidence_sufficient
            else ("equivalent_behavior" if behavior_equal else "different_behavior")
        ),
        "config_identity": {
            "baseline": {
                "config_id": left_config.get("config_id"),
                "config_hash": left_config.get("config_hash"),
            },
            "candidate": {
                "config_id": right_config.get("config_id"),
                "config_hash": right_config.get("config_hash"),
            },
            "config_id_equal": left_config.get("config_id")
            == right_config.get("config_id"),
            "config_hash_equal": left_config.get("config_hash")
            == right_config.get("config_hash"),
        },
        "full_trace_equal": baseline.get("trace") == candidate.get("trace"),
        "behavior_trace_equal": behavior_equal,
        "behavior_trace_sha256": {
            "baseline": left_behavior_hash,
            "candidate": right_behavior_hash,
        },
        "metric_deltas_candidate_minus_baseline": deltas,
        "gnss_intent_counts": {
            "baseline": deepcopy(left.get("gnss_intent_counts")),
            "candidate": deepcopy(right.get("gnss_intent_counts")),
        },
        "policy_mode_counts": {
            "baseline": deepcopy(left.get("policy_mode_counts")),
            "candidate": deepcopy(right.get("policy_mode_counts")),
        },
        "interpretation_boundary": (
            "replay outcomes only; no measured energy saving or real-world accuracy delta"
        ),
    }


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _validate_normalized_jsonl_row(
    value: Mapping[str, Any], line_number: int
) -> str:
    prefix = f"normalized JSONL line {line_number}"
    if value.get("contract_version") != NORMALIZED_OBSERVATION_CONTRACT_VERSION:
        raise LocationPolicyReplayError(
            f"{prefix} contract_version must be {NORMALIZED_OBSERVATION_CONTRACT_VERSION}"
        )
    event_type = value.get("event_type")
    if not isinstance(event_type, str) or not event_type or event_type == "tick":
        raise LocationPolicyReplayError(
            f"{prefix} requires a non-timer sensor event_type"
        )
    event_time_ms = value.get("event_time_ms")
    if (
        isinstance(event_time_ms, bool)
        or not isinstance(event_time_ms, int)
        or event_time_ms < 0
    ):
        raise LocationPolicyReplayError(
            f"{prefix} event_time_ms must be a non-negative integer"
        )
    lineage = value.get("lineage")
    evidence = value.get("evidence")
    if not isinstance(lineage, Mapping) or not isinstance(evidence, Mapping):
        raise LocationPolicyReplayError(
            f"{prefix} requires lineage and evidence objects"
        )
    observation_id = _first(
        lineage.get("normalized_observation_id"), lineage.get("observation_id")
    )
    if not isinstance(observation_id, str) or not observation_id:
        raise LocationPolicyReplayError(f"{prefix} has no stable observation id")
    source_status = lineage.get("source_status")
    if source_status not in {
        "observed",
        "verified",
        "rule_derived",
        "synthetic_fixture",
    }:
        raise LocationPolicyReplayError(f"{prefix} has unsupported source_status")
    if evidence.get("source_status") != source_status:
        raise LocationPolicyReplayError(
            f"{prefix} evidence source_status must match lineage"
        )
    if source_status in TRUSTED_FIELD_SOURCE_STATUSES:
        has_capture_time = (
            _integer_ns(lineage.get("timestamp_utc_ns")) is not None
            or _integer_ns(lineage.get("timestamp_monotonic_ns")) is not None
            or lineage.get("event_time_source") == "capture_event"
        )
        if not has_capture_time:
            raise LocationPolicyReplayError(
                f"{prefix} observed/verified evidence lacks capture event time"
            )
    if source_status == "rule_derived":
        basis = lineage.get("basis_observation_ids")
        if (
            lineage.get("event_time_source") != "policy_rule_v0"
            or not isinstance(basis, list)
            or not basis
            or not all(isinstance(item, str) and item for item in basis)
        ):
            raise LocationPolicyReplayError(
                f"{prefix} rule_derived evidence lacks attributable basis"
            )
    return observation_id


def load_normalized_observations_jsonl(
    path: str | Path,
) -> LoadedNormalizedObservations:
    rows: list[dict[str, Any]] = []
    observation_ids: set[str] = set()
    input_path = Path(path)
    try:
        raw_bytes = input_path.read_bytes()
        text = raw_bytes.decode("utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            value = json.loads(line, parse_constant=_reject_json_constant)
            if not isinstance(value, Mapping):
                raise LocationPolicyReplayError(
                    f"normalized JSONL line {line_number} is not an object"
                )
            observation_id = _validate_normalized_jsonl_row(value, line_number)
            if observation_id in observation_ids:
                raise LocationPolicyReplayError(
                    f"normalized JSONL duplicate observation id: {observation_id}"
                )
            observation_ids.add(observation_id)
            rows.append(dict(value))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise LocationPolicyReplayError(f"unable to load normalized JSONL: {exc}") from exc
    return LoadedNormalizedObservations(
        observations=rows,
        contract_version=NORMALIZED_OBSERVATION_CONTRACT_VERSION,
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
        record_count=len(rows),
        path=str(input_path),
    )

"""Credential-free CALL-020 media-metadata trace evaluator.

This module reconstructs a bounded, bidirectional packet trace captured by the
explicit PC development bridge.  It never reads or stores audio content, opens
a network connection, selects an RTC provider, or claims LTE/device-audio/P0
evidence.  Its output is only an offline engineering-fixture result.
"""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


TRACE_VERSION = "egolink.ego_call_media_trace.v0.1"
DIRECTIONS = ("uplink", "downlink")

_TRACE_KEYS = {
    "trace_version",
    "trace_id",
    "session_id",
    "trace_clock_id",
    "trace_start_time_ns",
    "trace_end_time_ns",
    "endpoints",
    "source_clock_ids",
    "config",
    "records",
}
_ENDPOINT_KEYS = {"device_id", "guardian_id"}
_DIRECTION_KEYS = set(DIRECTIONS)
_CONFIG_KEYS = {
    "expected_packet_count",
    "nominal_packet_interval_ns",
    "minimum_packets_per_direction_for_connected",
    "duplex_window_ns",
    "setup_timeout_ns",
    "max_loss_ratio",
    "max_jitter_ns",
    "max_gap_ns",
    "blackout_threshold_ns",
    "max_recovery_ns",
}
_RECORD_KEYS = {
    "observation_id",
    "packet_id",
    "session_id",
    "direction",
    "source_role",
    "source_id",
    "target_role",
    "target_id",
    "sequence",
    "source_clock_id",
    "source_time_ns",
    "trace_clock_id",
    "trace_time_ns",
    "encoded_size_bytes",
}


class MediaTraceError(ValueError):
    """Raised when a trace cannot be evaluated without inventing semantics."""


def _require_object(
    value: object,
    *,
    label: str,
    keys: set[str],
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise MediaTraceError(f"{label} must be an object")
    actual = set(value)
    if actual != keys:
        missing = sorted(keys - actual, key=repr)
        extra = sorted(actual - keys, key=repr)
        raise MediaTraceError(
            f"{label} fields must be exact; missing={missing}, extra={extra}"
        )
    return value


def _require_string(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MediaTraceError(f"{label} must be a non-empty string")
    if len(value) > 128:
        raise MediaTraceError(f"{label} must be at most 128 characters")
    return value


def _require_int(value: object, *, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise MediaTraceError(f"{label} must be an integer >= {minimum}")
    return value


def _require_ratio(value: object, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MediaTraceError(f"{label} must be a finite number in [0, 1]")
    result = float(value)
    if not math.isfinite(result) or result < 0.0 or result > 1.0:
        raise MediaTraceError(f"{label} must be a finite number in [0, 1]")
    return result


def _canonical(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise MediaTraceError("trace contains a non-JSON or non-finite value") from error


def _expected_roles(direction: str) -> tuple[str, str]:
    if direction == "uplink":
        return "device", "guardian"
    return "guardian", "device"


def _validate_trace(trace: object) -> dict[str, Any]:
    root = _require_object(trace, label="trace", keys=_TRACE_KEYS)
    if root["trace_version"] != TRACE_VERSION:
        raise MediaTraceError(f"trace_version must be {TRACE_VERSION!r}")

    trace_id = _require_string(root["trace_id"], label="trace_id")
    session_id = _require_string(root["session_id"], label="session_id")
    trace_clock_id = _require_string(root["trace_clock_id"], label="trace_clock_id")
    trace_start = _require_int(
        root["trace_start_time_ns"], label="trace_start_time_ns"
    )
    trace_end = _require_int(root["trace_end_time_ns"], label="trace_end_time_ns")
    if trace_end <= trace_start:
        raise MediaTraceError("trace_end_time_ns must be greater than trace_start_time_ns")

    endpoints = _require_object(
        root["endpoints"], label="endpoints", keys=_ENDPOINT_KEYS
    )
    endpoint_ids = {
        role: _require_string(endpoints[f"{role}_id"], label=f"endpoints.{role}_id")
        for role in ("device", "guardian")
    }
    if endpoint_ids["device"] == endpoint_ids["guardian"]:
        raise MediaTraceError("device_id and guardian_id must be distinct")

    source_clocks = _require_object(
        root["source_clock_ids"],
        label="source_clock_ids",
        keys=_DIRECTION_KEYS,
    )
    source_clock_ids = {
        direction: _require_string(
            source_clocks[direction], label=f"source_clock_ids.{direction}"
        )
        for direction in DIRECTIONS
    }

    raw_config = _require_object(root["config"], label="config", keys=_CONFIG_KEYS)
    raw_expected = _require_object(
        raw_config["expected_packet_count"],
        label="config.expected_packet_count",
        keys=_DIRECTION_KEYS,
    )
    expected = {
        direction: _require_int(
            raw_expected[direction],
            label=f"config.expected_packet_count.{direction}",
            minimum=1,
        )
        for direction in DIRECTIONS
    }
    config = {
        "expected_packet_count": expected,
        "nominal_packet_interval_ns": _require_int(
            raw_config["nominal_packet_interval_ns"],
            label="config.nominal_packet_interval_ns",
            minimum=1,
        ),
        "minimum_packets_per_direction_for_connected": _require_int(
            raw_config["minimum_packets_per_direction_for_connected"],
            label="config.minimum_packets_per_direction_for_connected",
            minimum=1,
        ),
        "duplex_window_ns": _require_int(
            raw_config["duplex_window_ns"],
            label="config.duplex_window_ns",
            minimum=1,
        ),
        "setup_timeout_ns": _require_int(
            raw_config["setup_timeout_ns"],
            label="config.setup_timeout_ns",
            minimum=1,
        ),
        "max_loss_ratio": _require_ratio(
            raw_config["max_loss_ratio"], label="config.max_loss_ratio"
        ),
        "max_jitter_ns": _require_int(
            raw_config["max_jitter_ns"], label="config.max_jitter_ns"
        ),
        "max_gap_ns": _require_int(
            raw_config["max_gap_ns"], label="config.max_gap_ns", minimum=1
        ),
        "blackout_threshold_ns": _require_int(
            raw_config["blackout_threshold_ns"],
            label="config.blackout_threshold_ns",
            minimum=1,
        ),
        "max_recovery_ns": _require_int(
            raw_config["max_recovery_ns"], label="config.max_recovery_ns"
        ),
    }
    minimum_packets = config["minimum_packets_per_direction_for_connected"]
    if any(expected[direction] < minimum_packets for direction in DIRECTIONS):
        raise MediaTraceError(
            "expected packet counts must cover the connected packet minimum"
        )
    if config["max_gap_ns"] < config["blackout_threshold_ns"]:
        raise MediaTraceError("max_gap_ns must be >= blackout_threshold_ns")
    if config["duplex_window_ns"] > config["blackout_threshold_ns"]:
        raise MediaTraceError(
            "duplex_window_ns must be <= blackout_threshold_ns so stale one-way "
            "media cannot establish connected"
        )

    raw_records = root["records"]
    if isinstance(raw_records, (str, bytes)) or not isinstance(raw_records, Sequence):
        raise MediaTraceError("records must be an array")

    observations: dict[str, str] = {}
    bridge_times: dict[int, str] = {}
    packet_identity: dict[str, tuple[Any, ...]] = {}
    sequence_identity: dict[tuple[str, int], tuple[Any, ...]] = {}
    records: list[dict[str, Any]] = []
    replay_duplicate_count = 0

    for index, raw_record in enumerate(raw_records):
        label = f"records[{index}]"
        record = dict(_require_object(raw_record, label=label, keys=_RECORD_KEYS))
        observation_id = _require_string(
            record["observation_id"], label=f"{label}.observation_id"
        )
        serialized = _canonical(record)
        if observation_id in observations:
            if observations[observation_id] != serialized:
                raise MediaTraceError(
                    f"observation_id {observation_id!r} was reused with conflicting data"
                )
            replay_duplicate_count += 1
            continue
        observations[observation_id] = serialized

        packet_id = _require_string(record["packet_id"], label=f"{label}.packet_id")
        if record["session_id"] != session_id:
            raise MediaTraceError(f"{label}.session_id does not match trace session")
        direction = record["direction"]
        if direction not in DIRECTIONS:
            raise MediaTraceError(f"{label}.direction must be uplink or downlink")
        source_role, target_role = _expected_roles(direction)
        if record["source_role"] != source_role or record["target_role"] != target_role:
            raise MediaTraceError(f"{label} endpoint roles conflict with direction")
        if record["source_id"] != endpoint_ids[source_role]:
            raise MediaTraceError(f"{label}.source_id does not match bound endpoint")
        if record["target_id"] != endpoint_ids[target_role]:
            raise MediaTraceError(f"{label}.target_id does not match bound endpoint")
        if record["source_clock_id"] != source_clock_ids[direction]:
            raise MediaTraceError(f"{label}.source_clock_id changed within direction")
        if record["trace_clock_id"] != trace_clock_id:
            raise MediaTraceError(f"{label}.trace_clock_id does not match trace")

        sequence = _require_int(record["sequence"], label=f"{label}.sequence")
        if sequence >= expected[direction]:
            raise MediaTraceError(f"{label}.sequence exceeds declared expected range")
        source_time = _require_int(
            record["source_time_ns"], label=f"{label}.source_time_ns"
        )
        trace_time = _require_int(record["trace_time_ns"], label=f"{label}.trace_time_ns")
        if trace_time < trace_start or trace_time > trace_end:
            raise MediaTraceError(f"{label}.trace_time_ns is outside trace bounds")
        if trace_time in bridge_times:
            raise MediaTraceError(
                f"trace clock collision between {bridge_times[trace_time]!r} and "
                f"{observation_id!r}"
            )
        bridge_times[trace_time] = observation_id
        encoded_size = _require_int(
            record["encoded_size_bytes"],
            label=f"{label}.encoded_size_bytes",
            minimum=1,
        )

        identity = (direction, sequence, source_time, encoded_size)
        prior_packet = packet_identity.get(packet_id)
        if prior_packet is not None and prior_packet != identity:
            raise MediaTraceError(f"packet_id {packet_id!r} has conflicting identity")
        packet_identity[packet_id] = identity
        sequence_key = (direction, sequence)
        prior_sequence = sequence_identity.get(sequence_key)
        sequence_value = (packet_id, source_time, encoded_size)
        if prior_sequence is not None and prior_sequence != sequence_value:
            raise MediaTraceError(
                f"{direction} sequence {sequence} has conflicting packet metadata"
            )
        sequence_identity[sequence_key] = sequence_value
        records.append(record)

    for direction in DIRECTIONS:
        by_sequence: dict[int, dict[str, Any]] = {}
        for record in records:
            if record["direction"] != direction:
                continue
            by_sequence.setdefault(record["sequence"], record)
        previous_time: int | None = None
        for sequence in sorted(by_sequence):
            source_time = by_sequence[sequence]["source_time_ns"]
            if previous_time is not None and source_time <= previous_time:
                raise MediaTraceError(
                    f"{direction} source_time_ns must increase with sequence"
                )
            previous_time = source_time

    return {
        "trace_id": trace_id,
        "session_id": session_id,
        "trace_clock_id": trace_clock_id,
        "trace_start_time_ns": trace_start,
        "trace_end_time_ns": trace_end,
        "config": config,
        "records": records,
        "replay_duplicate_count": replay_duplicate_count,
    }


def _direction_metrics(
    records: list[dict[str, Any]],
    *,
    direction: str,
    expected_count: int,
    nominal_packet_interval_ns: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    arrivals = sorted(
        (record for record in records if record["direction"] == direction),
        key=lambda record: record["trace_time_ns"],
    )
    first_by_sequence: dict[int, dict[str, Any]] = {}
    media_duplicate_count = 0
    reordered_count = 0
    highest_sequence = -1
    arrival_unique: list[dict[str, Any]] = []
    for record in arrivals:
        sequence = record["sequence"]
        if sequence in first_by_sequence:
            media_duplicate_count += 1
            continue
        first_by_sequence[sequence] = record
        arrival_unique.append(record)
        if sequence < highest_sequence:
            reordered_count += 1
        highest_sequence = max(highest_sequence, sequence)

    missing_sequences = sorted(set(range(expected_count)) - set(first_by_sequence))
    jitter_values: list[int] = []
    gaps: list[int] = []
    for previous, current in zip(arrival_unique, arrival_unique[1:]):
        arrival_delta = current["trace_time_ns"] - previous["trace_time_ns"]
        source_delta = current["source_time_ns"] - previous["source_time_ns"]
        jitter_values.append(abs(arrival_delta - source_delta))
        gaps.append(arrival_delta)

    source_cadence_errors: list[int] = []
    sequence_order = sorted(first_by_sequence.items())
    for (previous_sequence, previous), (current_sequence, current) in zip(
        sequence_order, sequence_order[1:]
    ):
        expected_source_delta = (
            current_sequence - previous_sequence
        ) * nominal_packet_interval_ns
        actual_source_delta = current["source_time_ns"] - previous["source_time_ns"]
        source_cadence_errors.append(abs(actual_source_delta - expected_source_delta))

    received_count = len(first_by_sequence)
    metrics = {
        "expected_packet_count": expected_count,
        "received_unique_packet_count": received_count,
        "lost_packet_count": len(missing_sequences),
        "loss_ratio": (len(missing_sequences) / expected_count),
        "missing_sequences": missing_sequences,
        "media_duplicate_packet_count": media_duplicate_count,
        "reordered_packet_count": reordered_count,
        "nominal_packet_interval_ns": nominal_packet_interval_ns,
        "max_source_cadence_error_ns": max(source_cadence_errors, default=0),
        "max_jitter_ns": max(jitter_values, default=0),
        "mean_jitter_ns": (
            sum(jitter_values) / len(jitter_values) if jitter_values else 0.0
        ),
        "max_gap_ns": max(gaps, default=0),
        "first_trace_time_ns": (
            arrival_unique[0]["trace_time_ns"] if arrival_unique else None
        ),
        "last_trace_time_ns": (
            arrival_unique[-1]["trace_time_ns"] if arrival_unique else None
        ),
    }
    return metrics, arrival_unique


def _connected_time(
    arrivals: dict[str, list[dict[str, Any]]],
    *,
    minimum_packets: int,
    duplex_window_ns: int,
) -> int | None:
    timeline = sorted(
        (
            (record["trace_time_ns"], direction)
            for direction in DIRECTIONS
            for record in arrivals[direction]
        ),
        key=lambda item: item[0],
    )
    counts = {direction: 0 for direction in DIRECTIONS}
    latest: dict[str, int | None] = {direction: None for direction in DIRECTIONS}
    for trace_time, direction in timeline:
        counts[direction] += 1
        latest[direction] = trace_time
        if any(counts[item] < minimum_packets for item in DIRECTIONS):
            continue
        if abs(int(latest["uplink"]) - int(latest["downlink"])) <= duplex_window_ns:
            return trace_time
    return None


def _blackouts(
    arrivals: list[dict[str, Any]],
    *,
    direction: str,
    connected_at_ns: int,
    trace_end_ns: int,
    threshold_ns: int,
) -> list[dict[str, Any]]:
    times = [record["trace_time_ns"] for record in arrivals]
    previous_candidates = [value for value in times if value <= connected_at_ns]
    previous = max(previous_candidates, default=connected_at_ns)
    result: list[dict[str, Any]] = []
    for current in (value for value in times if value > connected_at_ns):
        detection_time = previous + threshold_ns
        if current >= detection_time:
            result.append(
                {
                    "direction": direction,
                    "detected_at_ns": detection_time,
                    "recovered_at_ns": current,
                    "recovery_latency_ns": current - detection_time,
                    "recovered": True,
                }
            )
        previous = current
    detection_time = previous + threshold_ns
    if trace_end_ns >= detection_time:
        result.append(
            {
                "direction": direction,
                "detected_at_ns": detection_time,
                "recovered_at_ns": None,
                "recovery_latency_ns": None,
                "recovered": False,
            }
        )
    return result


def _state_trace(
    *,
    trace_start_ns: int,
    trace_end_ns: int,
    connected_at_ns: int | None,
    setup_timeout_ns: int,
    blackouts: list[dict[str, Any]],
    max_recovery_ns: int,
) -> tuple[list[dict[str, Any]], str, list[str]]:
    states = [
        {
            "trace_time_ns": trace_start_ns,
            "state": "probing",
            "reason": "offline_trace_started",
            "affected_directions": [],
        }
    ]
    failures: list[str] = []
    setup_deadline = trace_start_ns + setup_timeout_ns
    if connected_at_ns is None or connected_at_ns > setup_deadline:
        failure_time = min(trace_end_ns, setup_deadline)
        states.append(
            {
                "trace_time_ns": failure_time,
                "state": "failed",
                "reason": "full_duplex_not_observed",
                "affected_directions": list(DIRECTIONS),
            }
        )
        return states, "failed", ["full_duplex_not_observed"]

    states.append(
        {
            "trace_time_ns": connected_at_ns,
            "state": "connected",
            "reason": "bidirectional_media_metadata_observed",
            "affected_directions": [],
        }
    )
    boundary_events: list[tuple[int, int, str, dict[str, Any]]] = []
    for blackout in blackouts:
        if blackout["detected_at_ns"] < connected_at_ns:
            continue
        boundary_events.append(
            (blackout["detected_at_ns"], 0, "start", blackout)
        )
        if blackout["recovered_at_ns"] is not None:
            boundary_events.append(
                (blackout["recovered_at_ns"], 1, "end", blackout)
            )
    boundary_events.sort(key=lambda item: (item[0], item[1], item[3]["direction"]))

    active: set[str] = set()
    failed = False
    for event_time, _priority, kind, blackout in boundary_events:
        direction = blackout["direction"]
        if kind == "start":
            was_empty = not active
            active.add(direction)
            if was_empty:
                states.append(
                    {
                        "trace_time_ns": event_time,
                        "state": "reconnecting",
                        "reason": "media_blackout_detected",
                        "affected_directions": sorted(active),
                    }
                )
            continue

        active.discard(direction)
        recovery_latency = blackout["recovery_latency_ns"]
        if recovery_latency is not None and recovery_latency > max_recovery_ns:
            states.append(
                {
                    "trace_time_ns": event_time,
                    "state": "failed",
                    "reason": "recovery_budget_exceeded",
                    "affected_directions": [direction],
                }
            )
            failures.append(f"{direction}_recovery_budget_exceeded")
            failed = True
            break
        if not active:
            states.append(
                {
                    "trace_time_ns": event_time,
                    "state": "connected",
                    "reason": "bidirectional_media_recovered",
                    "affected_directions": [],
                }
            )

    if not failed:
        unrecovered = sorted(
            blackout["direction"] for blackout in blackouts if not blackout["recovered"]
        )
        if unrecovered:
            states.append(
                {
                    "trace_time_ns": trace_end_ns,
                    "state": "failed",
                    "reason": "media_blackout_unrecovered",
                    "affected_directions": unrecovered,
                }
            )
            failures.extend(f"{direction}_blackout_unrecovered" for direction in unrecovered)
            failed = True

    return states, ("failed" if failed else "connected"), failures


def evaluate_media_trace(trace: object) -> dict[str, Any]:
    """Validate and deterministically evaluate one metadata-only media trace."""

    normalized = _validate_trace(trace)
    config = normalized["config"]
    direction_metrics: dict[str, dict[str, Any]] = {}
    arrivals: dict[str, list[dict[str, Any]]] = {}
    for direction in DIRECTIONS:
        metrics, direction_arrivals = _direction_metrics(
            normalized["records"],
            direction=direction,
            expected_count=config["expected_packet_count"][direction],
            nominal_packet_interval_ns=config["nominal_packet_interval_ns"],
        )
        direction_metrics[direction] = metrics
        arrivals[direction] = direction_arrivals

    connected_at = _connected_time(
        arrivals,
        minimum_packets=config["minimum_packets_per_direction_for_connected"],
        duplex_window_ns=config["duplex_window_ns"],
    )
    blackouts: list[dict[str, Any]] = []
    if connected_at is not None:
        for direction in DIRECTIONS:
            blackouts.extend(
                _blackouts(
                    arrivals[direction],
                    direction=direction,
                    connected_at_ns=connected_at,
                    trace_end_ns=normalized["trace_end_time_ns"],
                    threshold_ns=config["blackout_threshold_ns"],
                )
            )
    blackouts.sort(key=lambda item: (item["detected_at_ns"], item["direction"]))

    states, final_state, failures = _state_trace(
        trace_start_ns=normalized["trace_start_time_ns"],
        trace_end_ns=normalized["trace_end_time_ns"],
        connected_at_ns=connected_at,
        setup_timeout_ns=config["setup_timeout_ns"],
        blackouts=blackouts,
        max_recovery_ns=config["max_recovery_ns"],
    )

    for direction in DIRECTIONS:
        metrics = direction_metrics[direction]
        if metrics["loss_ratio"] > config["max_loss_ratio"]:
            failures.append(f"{direction}_loss_budget_exceeded")
        if metrics["max_jitter_ns"] > config["max_jitter_ns"]:
            failures.append(f"{direction}_jitter_budget_exceeded")
        if metrics["max_gap_ns"] > config["max_gap_ns"]:
            failures.append(f"{direction}_gap_budget_exceeded")

    failures = sorted(set(failures))
    return {
        "evaluation_version": "egolink.ego_call_media_probe.v0.1",
        "trace_id": normalized["trace_id"],
        "session_id": normalized["session_id"],
        "trace_clock_id": normalized["trace_clock_id"],
        "trace_window": {
            "start_time_ns": normalized["trace_start_time_ns"],
            "end_time_ns": normalized["trace_end_time_ns"],
            "duration_ns": (
                normalized["trace_end_time_ns"]
                - normalized["trace_start_time_ns"]
            ),
        },
        "evaluation_config": config,
        "evaluation_result": "PASS" if not failures else "FAIL",
        "final_media_state": final_state,
        "full_duplex_observed": connected_at is not None,
        "connected_at_trace_time_ns": connected_at,
        "direction_metrics": direction_metrics,
        "blackouts": blackouts,
        "state_trace": states,
        "failure_reasons": failures,
        "replay_duplicate_observation_count": normalized["replay_duplicate_count"],
        "claims": {
            "offline_metadata_evaluator": "verified",
            "audio_content_retained": False,
            "device_audio": "unverified",
            "sim_lte_media": "unverified",
            "vps_rtc": "unverified",
            "production_rtc_provider": "not_selected",
            "p0_call": "NOT_RUN",
        },
    }


def load_and_evaluate(path: str | Path) -> dict[str, Any]:
    """Load a JSON trace and return its deterministic evaluation."""

    trace_path = Path(path)
    try:
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MediaTraceError(f"cannot load trace {trace_path}: {error}") from error
    return evaluate_media_trace(trace)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate a credential-free CALL-020 packet-metadata trace."
    )
    parser.add_argument("trace", help="Path to the JSON trace document")
    args = parser.parse_args(argv)
    try:
        result = load_and_evaluate(args.trace)
    except MediaTraceError as error:
        parser.exit(2, f"media trace rejected: {error}\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["evaluation_result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

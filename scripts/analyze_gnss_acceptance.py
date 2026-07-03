"""Analyze FIELD-003 outdoor GNSS acceptance evidence from a VPS export.

Offline evidence tool: reads a Message Hub test-run export plus an operator
field manifest, then writes JSON and Markdown reports for fix rate, TTFF,
position error, HDOP/error correlation, and the EALE-P0 max(25, hdop * 8)
radius comparison.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "reports" / "gnss"
GENERATOR_NAME = "FIELD-003.gnss_acceptance_analysis"
GENERATOR_VERSION = "0.1.0"
REPORT_JSON = "gnss_acceptance_report.json"
REPORT_MARKDOWN = "gnss_acceptance_report.md"
REQUIRED_POINT_TYPES = ("open_sky", "street_between_buildings", "tree_cover")
MIN_ATTEMPTS_PER_MODE = 5
ATTEMPT_MODES = ("cold", "warm")


class GnssAcceptanceError(RuntimeError):
    """Raised when input evidence cannot be analyzed."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def is_present(value: object) -> bool:
    return value is not None and value != ""


def normalize_key(value: object) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def numeric_or_none(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, str):
        text = value.strip()
        if not text or text.lower() in {"none", "null", "unknown", "unverified", "nan"}:
            return None
        try:
            number = float(text)
        except ValueError:
            return None
        return number if math.isfinite(number) else None
    return None


def int_or_none(value: object) -> int | None:
    number = numeric_or_none(value)
    if number is None or not number.is_integer():
        return None
    return int(number)


def bool_or_none(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        text = normalize_key(value)
        if text in {"true", "1", "yes", "y", "fixed", "fix"}:
            return True
        if text in {"false", "0", "no", "n", "no_fix", "not_fixed", "unfixed"}:
            return False
    return None


def parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def iso_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def nested_value(payload: object, dotted_path: str) -> object | None:
    value = payload
    for part in dotted_path.split("."):
        if isinstance(value, dict) and part in value:
            value = value[part]
        else:
            return None
    return value


def first_nested(payload: object, paths: Iterable[str]) -> object | None:
    for item_path in paths:
        value = nested_value(payload, item_path)
        if is_present(value):
            return value
    return None


def load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise GnssAcceptanceError(f"failed to read JSON: {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise GnssAcceptanceError(f"invalid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise GnssAcceptanceError(f"JSON document must be an object: {path}")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_m = 6371008.8
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    return radius_m * 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * pct
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[int(rank)]
    weight = rank - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def distribution(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "min": None, "p50": None, "p95": None, "max": None, "mean": None}
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "min": ordered[0],
        "p50": percentile(ordered, 0.50),
        "p95": percentile(ordered, 0.95),
        "max": ordered[-1],
        "mean": sum(ordered) / len(ordered),
    }


def pearson_correlation(pairs: list[tuple[float, float]]) -> float | None:
    if len(pairs) < 2:
        return None
    xs = [item[0] for item in pairs]
    ys = [item[1] for item in pairs]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    denom_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    denom_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if denom_x == 0.0 or denom_y == 0.0:
        return None
    return numerator / (denom_x * denom_y)


def eale_radius_m(hdop: float) -> float:
    return max(25.0, hdop * 8.0)


def iter_export_records(export: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
    for index, message in enumerate(as_list(export.get("messages"))):
        if isinstance(message, dict):
            yield f"messages[{index}]", message
    for key in ("location_reports", "location_observations", "events", "observations"):
        for index, record in enumerate(as_list(export.get(key))):
            if isinstance(record, dict):
                yield f"{key}[{index}]", record
    for index, raw_frame in enumerate(as_list(export.get("raw_frames"))):
        if not isinstance(raw_frame, dict):
            continue
        parse_result = as_dict(raw_frame.get("parse_result"))
        for derived_key in ("derived_message", "derived_event", "event"):
            derived = as_dict(parse_result.get(derived_key))
            if derived:
                yield f"raw_frames[{index}].parse_result.{derived_key}", derived


def normalize_observation(record: dict[str, Any], source_path: str) -> dict[str, Any] | None:
    event_type = str(first_nested(record, ("event_type", "type", "message_type", "gnss.event_type")) or "")
    state = str(first_nested(record, ("gnss_state", "gnss.state", "state")) or "").strip()
    fix = bool_or_none(first_nested(record, ("fix", "gnss.fix", "gnss_fix")))
    if fix is None:
        state_key = normalize_key(state)
        if state_key in {"fix", "fixed", "gnss_fix"}:
            fix = True
        elif state_key in {"no_fix", "not_fixed", "unfixed"}:
            fix = False
    lat = numeric_or_none(first_nested(record, ("lat", "latitude", "gnss.lat", "gnss.latitude", "location.lat")))
    lon = numeric_or_none(first_nested(record, ("lon", "longitude", "lng", "gnss.lon", "gnss.longitude", "location.lon")))
    hdop = numeric_or_none(first_nested(record, ("hdop", "gnss.hdop", "gnss_hdop")))
    satellites = int_or_none(first_nested(record, ("satellites", "gnss.satellites", "gnss_satellites", "sat_count")))
    ttff_ms = numeric_or_none(first_nested(record, (
        "ttff_ms",
        "time_to_first_fix_ms",
        "gnss.ttff_ms",
        "gnss.time_to_first_fix_ms",
        "gnss.attempt_ms",
        "gnss_attempt_ms",
        "gnss.attempt_duration_ms",
        "attempt_ms",
    )))
    command_id = first_nested(record, (
        "location_request_cmd_id",
        "cmd_id",
        "command.cmd_id",
        "command.last_cmd_id",
        "gnss.location_request_cmd_id",
    ))
    received_at = parse_timestamp(first_nested(record, ("server_received_at", "received_at", "ts", "timestamp")))
    source_status = first_nested(record, ("source_status", "gnss.source_status"))
    transport_type = first_nested(record, ("transport.type", "transport_type"))
    sequence = first_nested(record, ("seq", "message.seq", "gnss.seq"))

    location_like = normalize_key(event_type) in {"location_report", "location_observation", "gnss_observation"}
    has_gnss_value = any(value is not None for value in (fix, lat, lon, hdop, satellites, ttff_ms))
    if not location_like and not has_gnss_value:
        return None
    return {
        "source_path": source_path,
        "event_type": event_type or "unknown",
        "command_id": str(command_id) if is_present(command_id) else None,
        "server_received_at": iso_or_none(received_at),
        "timestamp_sort": received_at.timestamp() if received_at is not None else None,
        "seq": sequence,
        "fix": fix,
        "gnss_state": state or None,
        "lat": lat,
        "lon": lon,
        "hdop": hdop,
        "satellites": satellites,
        "ttff_s": (ttff_ms / 1000.0) if ttff_ms is not None else None,
        "source_status": str(source_status) if is_present(source_status) else None,
        "transport_type": str(transport_type) if is_present(transport_type) else None,
    }


def collect_observations(export: dict[str, Any]) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for source_path, record in iter_export_records(export):
        observation = normalize_observation(record, source_path)
        if observation is not None:
            observations.append(observation)
    return sorted(
        observations,
        key=lambda item: (
            item.get("timestamp_sort") is None,
            item.get("timestamp_sort") or 0.0,
            str(item.get("source_path") or ""),
        ),
    )


def normalize_reference_points(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    points: dict[str, dict[str, Any]] = {}
    raw_points = as_list(manifest.get("reference_points") or manifest.get("points"))
    for index, raw_point in enumerate(raw_points, start=1):
        if not isinstance(raw_point, dict):
            continue
        reference = as_dict(raw_point.get("reference"))
        point_id = str(raw_point.get("point_id") or raw_point.get("id") or f"point_{index:02d}")
        point_type = normalize_key(raw_point.get("point_type") or raw_point.get("type"))
        reference_lat = numeric_or_none(reference.get("lat") if "lat" in reference else raw_point.get("reference_lat"))
        reference_lon = numeric_or_none(reference.get("lon") if "lon" in reference else raw_point.get("reference_lon"))
        method = str(reference.get("method") or raw_point.get("reference_method") or raw_point.get("reference_source") or "").strip()
        points[point_id] = {
            "point_id": point_id,
            "name": str(raw_point.get("name") or point_id),
            "point_type": point_type,
            "reference_lat": reference_lat,
            "reference_lon": reference_lon,
            "reference_method": method,
            "reference_recorded_at": reference.get("recorded_at") or raw_point.get("reference_recorded_at"),
            "notes": raw_point.get("notes"),
        }
    return points


def normalize_attempts(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    for index, raw_attempt in enumerate(as_list(manifest.get("attempts")), start=1):
        if not isinstance(raw_attempt, dict):
            continue
        attempt_id = str(raw_attempt.get("attempt_id") or raw_attempt.get("id") or f"attempt_{index:03d}")
        command_id = raw_attempt.get("command_id") or raw_attempt.get("cmd_id")
        attempts.append({
            "attempt_id": attempt_id,
            "point_id": str(raw_attempt.get("point_id") or ""),
            "mode": normalize_key(raw_attempt.get("mode") or raw_attempt.get("attempt_mode")),
            "command_id": str(command_id) if is_present(command_id) else None,
            "started_at": raw_attempt.get("started_at"),
            "ended_at": raw_attempt.get("ended_at"),
            "started_at_dt": parse_timestamp(raw_attempt.get("started_at")),
            "ended_at_dt": parse_timestamp(raw_attempt.get("ended_at")),
            "operator_notes": raw_attempt.get("operator_notes") or raw_attempt.get("notes"),
        })
    return attempts


def protocol_checks(manifest: dict[str, Any], points: dict[str, dict[str, Any]], attempts: list[dict[str, Any]]) -> dict[str, Any]:
    point_types = sorted({str(point.get("point_type")) for point in points.values() if point.get("point_type")})
    missing_point_types = [point_type for point_type in REQUIRED_POINT_TYPES if point_type not in point_types]
    missing_reference_methods = [
        point_id
        for point_id, point in points.items()
        if not point.get("reference_method") or point.get("reference_lat") is None or point.get("reference_lon") is None
    ]
    attempt_counter: dict[str, Counter[str]] = defaultdict(Counter)
    for attempt in attempts:
        attempt_counter[str(attempt.get("point_id") or "")][str(attempt.get("mode") or "unknown")] += 1
    counts_by_point = {
        point_id: {mode: attempt_counter[point_id][mode] for mode in ATTEMPT_MODES}
        for point_id in sorted(points)
    }
    insufficient_attempts = [
        {"point_id": point_id, "mode": mode, "count": counts_by_point.get(point_id, {}).get(mode, 0), "required": MIN_ATTEMPTS_PER_MODE}
        for point_id in sorted(points)
        for mode in ATTEMPT_MODES
        if counts_by_point.get(point_id, {}).get(mode, 0) < MIN_ATTEMPTS_PER_MODE
    ]
    connection_text = str(manifest.get("connection_path") or manifest.get("runtime_connection") or "").strip().lower()
    runtime_usb_connected = bool_or_none(manifest.get("runtime_usb_connected"))
    vps_only = "vps" in connection_text and "message" in connection_text and "hub" in connection_text
    return {
        "required_point_types": list(REQUIRED_POINT_TYPES),
        "observed_point_types": point_types,
        "missing_point_types": missing_point_types,
        "reference_methods_recorded": not missing_reference_methods,
        "points_missing_reference": missing_reference_methods,
        "minimum_attempts_per_point_mode": MIN_ATTEMPTS_PER_MODE,
        "attempt_counts_by_point": counts_by_point,
        "insufficient_attempts": insufficient_attempts,
        "usb_free_vps_only_recorded": vps_only and runtime_usb_connected is False,
        "connection_path": connection_text or None,
        "runtime_usb_connected": runtime_usb_connected,
    }


def observation_in_attempt_window(observation: dict[str, Any], attempt: dict[str, Any]) -> bool:
    timestamp = observation.get("timestamp_sort")
    started_at = attempt.get("started_at_dt")
    ended_at = attempt.get("ended_at_dt")
    if timestamp is None or not isinstance(started_at, datetime):
        return False
    observed_at = datetime.fromtimestamp(float(timestamp), tz=timezone.utc)
    if observed_at < started_at:
        return False
    if isinstance(ended_at, datetime) and observed_at > ended_at:
        return False
    return True


def match_attempt_observations(attempt: dict[str, Any], observations: list[dict[str, Any]], by_command: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    command_id = attempt.get("command_id")
    if command_id:
        matches = list(by_command.get(str(command_id), []))
        if matches:
            return matches
    return [observation for observation in observations if observation_in_attempt_window(observation, attempt)]


def selected_attempt_observation(matches: list[dict[str, Any]]) -> dict[str, Any] | None:
    for observation in matches:
        if observation.get("fix") is True:
            return observation
    return matches[0] if matches else None


def attempt_ttff_s(attempt: dict[str, Any], observation: dict[str, Any]) -> float | None:
    if observation.get("fix") is not True:
        return None
    direct = numeric_or_none(observation.get("ttff_s"))
    if direct is not None:
        return direct
    started_at = attempt.get("started_at_dt")
    observed_sort = observation.get("timestamp_sort")
    if isinstance(started_at, datetime) and observed_sort is not None:
        return max(0.0, float(observed_sort) - started_at.timestamp())
    return None


def summarize_attempts(points: dict[str, dict[str, Any]], attempts: list[dict[str, Any]], observations: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    by_command: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for observation in observations:
        command_id = observation.get("command_id")
        if command_id:
            by_command[str(command_id)].append(observation)
    rows: list[dict[str, Any]] = []
    for attempt in attempts:
        point = points.get(str(attempt.get("point_id") or ""), {})
        matches = match_attempt_observations(attempt, observations, by_command)
        selected = selected_attempt_observation(matches)
        status = "missing_observation"
        error_m: float | None = None
        radius_m: float | None = None
        within_radius: bool | None = None
        ttff_s: float | None = None
        if selected is None:
            errors.append(f"attempt {attempt.get('attempt_id')} has no matched VPS GNSS observation")
        elif selected.get("fix") is True:
            status = "fix"
            ttff_s = attempt_ttff_s(attempt, selected)
            lat = numeric_or_none(selected.get("lat"))
            lon = numeric_or_none(selected.get("lon"))
            ref_lat = numeric_or_none(point.get("reference_lat"))
            ref_lon = numeric_or_none(point.get("reference_lon"))
            if lat is None or lon is None or ref_lat is None or ref_lon is None:
                errors.append(f"attempt {attempt.get('attempt_id')} fixed but lacks coordinates or reference")
            else:
                error_m = haversine_m(ref_lat, ref_lon, lat, lon)
            hdop = numeric_or_none(selected.get("hdop"))
            if hdop is None:
                warnings.append(f"attempt {attempt.get('attempt_id')} fixed but lacks HDOP")
            elif error_m is not None:
                radius_m = eale_radius_m(hdop)
                within_radius = error_m <= radius_m
        elif selected.get("fix") is False:
            status = "no_fix"
        else:
            status = "unknown_fix_state"
            warnings.append(f"attempt {attempt.get('attempt_id')} has unknown fix state")
        rows.append({
            "attempt_id": attempt.get("attempt_id"),
            "point_id": attempt.get("point_id"),
            "point_type": point.get("point_type"),
            "mode": attempt.get("mode"),
            "command_id": attempt.get("command_id"),
            "status": status,
            "observation_count": len(matches),
            "selected_observation": selected,
            "ttff_s": ttff_s,
            "error_m": error_m,
            "hdop": numeric_or_none(selected.get("hdop")) if selected else None,
            "eale_radius_m": radius_m,
            "within_eale_radius": within_radius,
        })
    return rows, errors, warnings


def summarize_point(point: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    attempts = len(rows)
    fix_rows = [row for row in rows if row.get("status") == "fix"]
    ttff_values = [float(row["ttff_s"]) for row in fix_rows if row.get("ttff_s") is not None]
    error_values = [float(row["error_m"]) for row in fix_rows if row.get("error_m") is not None]
    hdop_error_pairs = [(float(row["hdop"]), float(row["error_m"])) for row in fix_rows if row.get("hdop") is not None and row.get("error_m") is not None]
    eale_pairs = [row for row in fix_rows if row.get("eale_radius_m") is not None and row.get("error_m") is not None]
    outside = [row for row in eale_pairs if row.get("within_eale_radius") is False]
    return {
        "point_id": point.get("point_id"),
        "name": point.get("name"),
        "point_type": point.get("point_type"),
        "reference": {
            "lat": point.get("reference_lat"),
            "lon": point.get("reference_lon"),
            "method": point.get("reference_method"),
            "recorded_at": point.get("reference_recorded_at"),
        },
        "attempts": attempts,
        "cold_attempts": sum(1 for row in rows if row.get("mode") == "cold"),
        "warm_attempts": sum(1 for row in rows if row.get("mode") == "warm"),
        "fix_count": len(fix_rows),
        "fix_rate": (len(fix_rows) / attempts) if attempts else None,
        "ttff_s": distribution(ttff_values),
        "error_m": distribution(error_values),
        "hdop_error_correlation": pearson_correlation(hdop_error_pairs),
        "eale_radius_comparison": {
            "pairs": len(eale_pairs),
            "within_count": len(eale_pairs) - len(outside),
            "outside_count": len(outside),
            "outside_attempt_ids": [str(row.get("attempt_id")) for row in outside],
        },
    }


def build_eale_comparison(attempt_rows: list[dict[str, Any]]) -> dict[str, Any]:
    pairs = [row for row in attempt_rows if row.get("status") == "fix" and row.get("error_m") is not None and row.get("eale_radius_m") is not None]
    outside = [row for row in pairs if row.get("within_eale_radius") is False]
    ratios = [float(row["error_m"]) / float(row["eale_radius_m"]) for row in pairs if row.get("eale_radius_m")]
    if not pairs:
        assessment = "insufficient_fixed_hdop_error_pairs"
        needs_revision: bool | None = None
    elif outside:
        assessment = "revision_indicated"
        needs_revision = True
    else:
        assessment = "no_revision_indicated_by_this_run"
        needs_revision = False
    return {
        "assumption": "gnss_radius_m = max(25, hdop * 8)",
        "fixed_hdop_error_pairs": len(pairs),
        "outside_eale_radius_count": len(outside),
        "outside_eale_radius_attempt_ids": [str(row.get("attempt_id")) for row in outside],
        "max_error_to_eale_radius_ratio": max(ratios) if ratios else None,
        "revision_assessment": assessment,
        "needs_revision": needs_revision,
    }


def evaluate_gnss_acceptance(export: dict[str, Any], manifest: dict[str, Any], *, input_path: Path | None = None, manifest_path: Path | None = None, created_at: str | None = None) -> dict[str, Any]:
    created_at = created_at or utc_now()
    points = normalize_reference_points(manifest)
    attempts = normalize_attempts(manifest)
    observations = collect_observations(export)
    protocol = protocol_checks(manifest, points, attempts)
    attempt_rows, attempt_errors, attempt_warnings = summarize_attempts(points, attempts, observations)

    errors: list[str] = []
    warnings: list[str] = []
    if not points:
        errors.append("manifest has no reference_points")
    if not attempts:
        errors.append("manifest has no attempts")
    if protocol["missing_point_types"]:
        errors.append("manifest missing required reference point types: " + ", ".join(protocol["missing_point_types"]))
    if not protocol["reference_methods_recorded"]:
        errors.append("one or more reference points lack coordinates or reference method")
    if protocol["insufficient_attempts"]:
        errors.append("one or more points has fewer than five cold or five warm attempts")
    if not protocol["usb_free_vps_only_recorded"]:
        errors.append("manifest does not record runtime_usb_connected=false with VPS Message Hub connection")
    errors.extend(attempt_errors)
    warnings.extend(attempt_warnings)

    fixed_count = sum(1 for row in attempt_rows if row.get("status") == "fix")
    no_fix_count = sum(1 for row in attempt_rows if row.get("status") == "no_fix")
    missing_count = sum(1 for row in attempt_rows if row.get("status") == "missing_observation")
    if attempts and fixed_count == 0:
        warnings.append("no fixed attempts; error distance and EALE radius comparison are unavailable")
    if no_fix_count:
        warnings.append(f"{no_fix_count} attempts reported no fix")

    rows_by_point: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in attempt_rows:
        rows_by_point[str(row.get("point_id") or "")].append(row)
    per_point = [summarize_point(point, rows_by_point.get(point_id, [])) for point_id, point in sorted(points.items())]

    fixed_rows = [row for row in attempt_rows if row.get("status") == "fix"]
    ttff_values = [float(row["ttff_s"]) for row in fixed_rows if row.get("ttff_s") is not None]
    error_values = [float(row["error_m"]) for row in fixed_rows if row.get("error_m") is not None]
    hdop_error_pairs = [(float(row["hdop"]), float(row["error_m"])) for row in fixed_rows if row.get("hdop") is not None and row.get("error_m") is not None]
    if len(hdop_error_pairs) < 2:
        warnings.append("fewer than two fixed HDOP/error pairs; correlation is unavailable")
    eale_comparison = build_eale_comparison(attempt_rows)
    if eale_comparison["revision_assessment"] == "revision_indicated":
        warnings.append("one or more fixed attempts exceeded the EALE-P0 hdop*8 Fine-radius assumption")
    elif eale_comparison["revision_assessment"] == "insufficient_fixed_hdop_error_pairs":
        warnings.append("EALE-P0 radius comparison has insufficient fixed HDOP/error pairs")

    status = "FAIL" if errors else ("WARN" if warnings else "PASS")
    source = as_dict(manifest.get("source"))
    test_run_id = manifest.get("test_run_id") or source.get("test_run_id") or as_dict(export.get("test_run")).get("test_run_id") or as_dict(export.get("test_run")).get("id") or "unknown-test-run"
    return {
        "generator": {"name": GENERATOR_NAME, "version": GENERATOR_VERSION, "created_at": created_at},
        "result": {"status": status, "errors": errors, "warnings": warnings},
        "source": {
            "test_run_id": test_run_id,
            "input_path": str(input_path) if input_path else None,
            "manifest_path": str(manifest_path) if manifest_path else None,
            "board_id": manifest.get("board_id"),
            "device_id": manifest.get("device_id") or source.get("device_id"),
            "firmware_version": manifest.get("firmware_version") or source.get("firmware_version"),
            "firmware_commit_or_image": manifest.get("firmware_commit_or_image") or source.get("firmware_commit_or_image"),
            "connection_path": manifest.get("connection_path"),
        },
        "protocol": protocol,
        "counts": {
            "reference_points": len(points),
            "attempts": len(attempts),
            "observations": len(observations),
            "fixed_attempts": fixed_count,
            "no_fix_attempts": no_fix_count,
            "missing_observation_attempts": missing_count,
        },
        "overall": {
            "fix_rate": (fixed_count / len(attempt_rows)) if attempt_rows else None,
            "ttff_s": distribution(ttff_values),
            "error_m": distribution(error_values),
            "hdop_error_correlation": pearson_correlation(hdop_error_pairs),
        },
        "per_point": per_point,
        "attempts": attempt_rows,
        "eale_p0_comparison": eale_comparison,
        "boundaries": [
            "Offline analysis over an existing VPS Message Hub export and field manifest.",
            "No firmware, protocol, threshold, or hardware behavior is changed by this tool.",
            "Measured results are engineering acceptance records, not product accuracy claims.",
        ],
    }


def fmt_number(value: object, digits: int = 2) -> str:
    number = numeric_or_none(value)
    if number is None:
        return "n/a"
    return f"{number:.{digits}f}"


def fmt_rate(value: object) -> str:
    number = numeric_or_none(value)
    if number is None:
        return "n/a"
    return f"{number * 100.0:.1f}%"


def write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    result = as_dict(report.get("result"))
    source = as_dict(report.get("source"))
    counts = as_dict(report.get("counts"))
    overall = as_dict(report.get("overall"))
    eale = as_dict(report.get("eale_p0_comparison"))
    protocol = as_dict(report.get("protocol"))
    lines = [
        "# FIELD-003 GNSS Acceptance Report",
        "",
        f"- Result: {result.get('status', 'unknown')}",
        f"- Test run: {source.get('test_run_id', 'unknown')}",
        f"- Device: {source.get('device_id', 'unknown')}",
        f"- Board: {source.get('board_id', 'unknown')}",
        f"- Firmware: {source.get('firmware_version', 'unknown')}",
        f"- Firmware commit or image: {source.get('firmware_commit_or_image', 'unknown')}",
        f"- Connection path: {source.get('connection_path', 'unknown')}",
        f"- Input export: {source.get('input_path', 'unknown')}",
        f"- Field manifest: {source.get('manifest_path', 'unknown')}",
        "",
        "## Protocol Checks",
        "",
        f"- Required point types: {', '.join(as_list(protocol.get('required_point_types')))}",
        f"- Observed point types: {', '.join(as_list(protocol.get('observed_point_types'))) or 'none'}",
        f"- Missing point types: {', '.join(as_list(protocol.get('missing_point_types'))) or 'none'}",
        f"- Reference methods recorded: {protocol.get('reference_methods_recorded')}",
        f"- USB-Free VPS-only recorded: {protocol.get('usb_free_vps_only_recorded')}",
        f"- Minimum attempts per point/mode: {protocol.get('minimum_attempts_per_point_mode')}",
        "",
        "## Overall Metrics",
        "",
        f"- Attempts: {counts.get('attempts', 0)}",
        f"- Fixed attempts: {counts.get('fixed_attempts', 0)}",
        f"- No-fix attempts: {counts.get('no_fix_attempts', 0)}",
        f"- Fix rate: {fmt_rate(overall.get('fix_rate'))}",
        f"- TTFF p50/p95 s: {fmt_number(as_dict(overall.get('ttff_s')).get('p50'))} / {fmt_number(as_dict(overall.get('ttff_s')).get('p95'))}",
        f"- Error p50/p95 m: {fmt_number(as_dict(overall.get('error_m')).get('p50'))} / {fmt_number(as_dict(overall.get('error_m')).get('p95'))}",
        f"- HDOP/error correlation: {fmt_number(overall.get('hdop_error_correlation'), 3)}",
        "",
        "## Per-Point Summary",
        "",
        "| point_id | type | attempts | fix_rate | ttff_p50_s | error_p95_m | hdop_error_corr | outside_eale_radius |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for point in as_list(report.get("per_point")):
        if not isinstance(point, dict):
            continue
        point_eale = as_dict(point.get("eale_radius_comparison"))
        lines.append(
            "| "
            + " | ".join([
                str(point.get("point_id")),
                str(point.get("point_type")),
                str(point.get("attempts")),
                fmt_rate(point.get("fix_rate")),
                fmt_number(as_dict(point.get("ttff_s")).get("p50")),
                fmt_number(as_dict(point.get("error_m")).get("p95")),
                fmt_number(point.get("hdop_error_correlation"), 3),
                str(point_eale.get("outside_count", 0)),
            ])
            + " |"
        )
    lines.extend([
        "",
        "## EALE-P0 Fine Radius Check",
        "",
        f"- Assumption: {eale.get('assumption', 'unknown')}",
        f"- Fixed HDOP/error pairs: {eale.get('fixed_hdop_error_pairs', 0)}",
        f"- Outside assumed radius: {eale.get('outside_eale_radius_count', 0)}",
        f"- Max error/radius ratio: {fmt_number(eale.get('max_error_to_eale_radius_ratio'), 3)}",
        f"- Revision assessment: {eale.get('revision_assessment', 'unknown')}",
        "",
        "## Warnings",
        "",
    ])
    warnings = as_list(result.get("warnings"))
    lines.extend((f"- {warning}" for warning in warnings) if warnings else ["- none"])
    errors = as_list(result.get("errors"))
    if errors:
        lines.extend(["", "## Errors", ""])
        lines.extend(f"- {error}" for error in errors)
    lines.extend(["", "## Boundaries", ""])
    for boundary in as_list(report.get("boundaries")):
        lines.append(f"- {boundary}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def default_output_dir(report: dict[str, Any]) -> Path:
    test_run_id = str(as_dict(report.get("source")).get("test_run_id") or f"FIELD-003-{datetime.now(timezone.utc):%Y%m%d}")
    return DEFAULT_OUTPUT_ROOT / test_run_id


def analyze_gnss_acceptance(*, input_path: Path, manifest_path: Path, output_dir: Path | None = None, created_at: str | None = None) -> dict[str, Any]:
    export = load_json_object(input_path)
    manifest = load_json_object(manifest_path)
    report = evaluate_gnss_acceptance(export, manifest, input_path=input_path, manifest_path=manifest_path, created_at=created_at)
    target_dir = output_dir or default_output_dir(report)
    target_dir.mkdir(parents=True, exist_ok=True)
    report_path = target_dir / REPORT_JSON
    markdown_path = target_dir / REPORT_MARKDOWN
    report["report_path"] = str(report_path)
    report["markdown_report_path"] = str(markdown_path)
    write_json(report_path, report)
    write_markdown_report(markdown_path, report)
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", "--export", dest="input_path", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = analyze_gnss_acceptance(input_path=args.input_path, manifest_path=args.manifest, output_dir=args.output_dir)
    except GnssAcceptanceError as exc:
        print(f"FAIL FIELD-003 GNSS acceptance analysis: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        source = as_dict(report.get("source"))
        status = as_dict(report.get("result")).get("status")
        print(f"{status} FIELD-003 GNSS acceptance test_run={source.get('test_run_id')} report={report.get('markdown_report_path')}")
    return 1 if as_dict(report.get("result")).get("status") == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())

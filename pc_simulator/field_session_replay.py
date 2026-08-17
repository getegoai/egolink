"""Minimal, evidence-honest Field Session replay and GNSS blackout smoke.

This module consumes the existing A0-003 package and A0-002 time-lineage
contracts.  It deliberately does not define another input schema, mutate a
sealed session, or treat a structurally replayable package as an A-line Gate
PASS.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import html
import json
import math
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from pc_simulator import field_session
from pc_simulator.sensor_time_lineage import (
    SensorTimeLineageError,
    format_utc_ns,
    parse_utc_ns,
)


REPLAY_REPORT_VERSION = "egolink.field_session_replay_report.v0.1"
EXPERIMENT_REPORT_VERSION = "egolink.exp_a1_000_result.v0.1"
EXPERIMENT_ID = "EXP-A1-000"
SAFE_ALIGNMENT_STATUSES = {"estimated", "verified"}
TRUSTED_SOURCE_STATUSES = {"observed", "verified"}
SOURCE_ORDER = {
    "gnss": 0,
    "lte": 1,
    "imu": 2,
    "camera": 3,
    "manual_event": 4,
}
EARTH_RADIUS_M = 6_371_008.8
STANDARD_GRAVITY_M_S2 = 9.80665


class FieldSessionReplayError(RuntimeError):
    """Raised when replay would need to invent or ignore evidence."""


@dataclass(frozen=True)
class ReplayPackage:
    manifest_path: Path
    session_root: Path
    manifest: dict[str, Any]
    validation: dict[str, Any]
    artifacts: dict[str, dict[str, Any]]
    streams: dict[str, dict[str, Any]]
    stream_rows: dict[str, list[dict[str, Any]]]
    time_records: list[dict[str, Any]]


@dataclass(frozen=True)
class ExperimentConfig:
    blackout_start_utc: str
    blackout_duration_s: int = 60
    endpoint_tolerance_s: float = 0.0
    motion_window_s: float = 1.0
    motion_threshold_m_s2: float = 0.75
    motion_min_samples: int = 2
    imu_max_gap_s: float = 1.0

    def validate(self) -> None:
        try:
            parse_utc_ns(self.blackout_start_utc, "blackout_start_utc")
        except SensorTimeLineageError as error:
            raise FieldSessionReplayError(str(error)) from error
        if self.blackout_duration_s != 60:
            raise FieldSessionReplayError("EXP-A1-000 requires exactly one 60-second GNSS blackout")
        if not math.isfinite(self.endpoint_tolerance_s) or self.endpoint_tolerance_s < 0:
            raise FieldSessionReplayError("endpoint_tolerance_s must be finite and non-negative")
        if not math.isfinite(self.motion_window_s) or self.motion_window_s <= 0:
            raise FieldSessionReplayError("motion_window_s must be finite and positive")
        if not math.isfinite(self.motion_threshold_m_s2) or self.motion_threshold_m_s2 < 0:
            raise FieldSessionReplayError("motion_threshold_m_s2 must be finite and non-negative")
        if isinstance(self.motion_min_samples, bool) or self.motion_min_samples < 1:
            raise FieldSessionReplayError("motion_min_samples must be a positive integer")
        if not math.isfinite(self.imu_max_gap_s) or self.imu_max_gap_s <= 0:
            raise FieldSessionReplayError("imu_max_gap_s must be finite and positive")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def stable_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def stable_jsonl_bytes(rows: Iterable[Mapping[str, Any]]) -> bytes:
    return b"".join(
        json.dumps(
            dict(row),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
        for row in rows
    )


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_path(session_root: Path, artifact: Mapping[str, Any]) -> Path:
    target = (session_root / str(artifact["path"])).resolve()
    try:
        target.relative_to(session_root.resolve())
    except ValueError as error:
        raise FieldSessionReplayError(
            f"artifact escapes session root: {artifact.get('artifact_id')}"
        ) from error
    return target


def _is_inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def ensure_output_outside_session(output_dir: Path, session_root: Path) -> Path:
    output = output_dir.resolve()
    if output == session_root.resolve() or _is_inside(output, session_root):
        raise FieldSessionReplayError(
            "replay output must be outside the sealed Field Session root"
        )
    return output


def _load_artifact_rows(path: Path, format_name: str) -> list[dict[str, Any]]:
    if format_name == "jsonl":
        return field_session.load_jsonl(path)
    if format_name == "json":
        return [field_session.load_json(path)]
    return []


def load_replay_package(
    manifest_path: Path,
    *,
    generated_at: str | None = None,
) -> ReplayPackage:
    """Validate and load a complete sealed package.

    `field_eligible` is intentionally not a prerequisite.  It is a structural
    A-R0 review signal, whereas this loader only decides whether immutable
    evidence can be replayed without guessing.
    """

    manifest_file = manifest_path.resolve()
    session_root = manifest_file.parent
    manifest = field_session.load_json(manifest_file)
    validation = field_session.validate_field_session(
        manifest,
        session_root=session_root,
        manifest_path=manifest_file,
        generated_at=generated_at,
    )
    required_checks = {
        "valid": validation.get("valid") is True,
        "manifest_file_binding_verified": validation.get("manifest_file_binding_verified") is True,
        "artifact_integrity_verified": validation.get("artifact_integrity_verified") is True,
        "package_closure_verified": validation.get("package_closure_verified") is True,
        "session_complete": manifest.get("lifecycle_state") == "complete",
        "session_sealed": (
            isinstance(manifest.get("seal"), Mapping)
            and manifest["seal"].get("status") == "sealed"
        ),
    }
    failed = [name for name, passed in required_checks.items() if not passed]
    if failed:
        codes = [
            str(issue.get("code"))
            for issue in validation.get("errors", [])
            if isinstance(issue, Mapping) and issue.get("code")
        ]
        suffix = f"; validator errors={','.join(codes)}" if codes else ""
        raise FieldSessionReplayError(
            f"Field Session is not safely replayable: {','.join(failed)}{suffix}"
        )

    artifacts = {
        str(artifact["artifact_id"]): dict(artifact)
        for artifact in manifest.get("artifacts", [])
    }
    streams = {
        str(stream["stream_id"]): dict(stream)
        for stream in manifest.get("streams", [])
    }
    stream_rows: dict[str, list[dict[str, Any]]] = {}
    for stream_id, stream in streams.items():
        artifact_id = stream.get("artifact_id")
        if stream.get("status") != "captured" or not isinstance(artifact_id, str):
            continue
        artifact = artifacts.get(artifact_id)
        if artifact is None:
            raise FieldSessionReplayError(f"captured stream {stream_id} has no artifact")
        path = _artifact_path(session_root, artifact)
        stream_rows[stream_id] = _load_artifact_rows(path, str(artifact.get("format")))

    time_records: list[dict[str, Any]] = []
    time_lineage = manifest.get("time_lineage")
    if isinstance(time_lineage, Mapping):
        for artifact_id in time_lineage.get("record_artifact_ids", []):
            artifact = artifacts.get(str(artifact_id))
            if artifact is None:
                raise FieldSessionReplayError(
                    f"time-lineage record artifact is missing: {artifact_id}"
                )
            time_records.extend(
                field_session.load_jsonl(_artifact_path(session_root, artifact))
            )

    return ReplayPackage(
        manifest_path=manifest_file,
        session_root=session_root,
        manifest=manifest,
        validation=validation,
        artifacts=artifacts,
        streams=streams,
        stream_rows=stream_rows,
        time_records=time_records,
    )


def _int_value(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _float_value(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _sequence_value(row: Mapping[str, Any]) -> int | None:
    value = _int_value(row.get("sequence_id"))
    return value if value is not None else _int_value(row.get("seq"))


def _find_payload_row(
    record: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    *,
    artifact_format: str,
) -> dict[str, Any]:
    derivation = record.get("imu_sample_derivation")
    if isinstance(derivation, Mapping) and isinstance(derivation.get("window_id"), str):
        matches = [row for row in rows if row.get("window_id") == derivation["window_id"]]
    else:
        sequence_id = _int_value(record.get("sequence_id"))
        matches = [row for row in rows if _sequence_value(row) == sequence_id]

    if len(matches) == 1:
        return dict(matches[0])
    if not rows and artifact_format in {"jpeg", "binary"}:
        return {"media_artifact_only": True}
    reason = "missing" if not matches else "ambiguous"
    raise FieldSessionReplayError(
        f"{reason} stream payload for {record.get('stream_id')} sequence {record.get('sequence_id')}"
    )


def _base_timeline_item(
    record: Mapping[str, Any],
    stream: Mapping[str, Any],
    payload: Mapping[str, Any],
    artifact: Mapping[str, Any],
) -> dict[str, Any]:
    alignment = record.get("alignment") if isinstance(record.get("alignment"), Mapping) else {}
    timestamp_utc = record.get("timestamp_utc")
    utc_ns = None
    gnss_source_utc_ns = None
    if isinstance(timestamp_utc, str) and alignment.get("status") in SAFE_ALIGNMENT_STATUSES:
        try:
            utc_ns = parse_utc_ns(timestamp_utc, "observation timestamp_utc")
        except SensorTimeLineageError as error:
            raise FieldSessionReplayError(str(error)) from error
    elif (
        record.get("source") == "gnss"
        and isinstance(timestamp_utc, str)
        and alignment.get("status") == "unavailable"
        and alignment.get("timestamp_utc_origin") == "source_timestamp"
    ):
        try:
            gnss_source_utc_ns = parse_utc_ns(
                timestamp_utc, "GNSS direct source timestamp_utc"
            )
        except SensorTimeLineageError as error:
            raise FieldSessionReplayError(str(error)) from error
    uncertainty = _int_value(alignment.get("uncertainty_ns"))
    return {
        "observation_id": record.get("observation_id"),
        "source": record.get("source"),
        "stream_id": record.get("stream_id"),
        "sequence_id": record.get("sequence_id"),
        "sample_index": None,
        "device_id": record.get("device_id"),
        "device_run_id": stream.get("device_run_id"),
        "timestamp_monotonic_ns": record.get("timestamp_monotonic_ns"),
        "timestamp_utc": timestamp_utc,
        "timestamp_utc_ns": utc_ns,
        "gnss_source_utc_ns": gnss_source_utc_ns,
        "timestamp_utc_origin": alignment.get("timestamp_utc_origin"),
        "monotonic_clock_domain_id": record.get("monotonic_clock_domain_id"),
        "boot_count": record.get("boot_count"),
        "alignment_status": alignment.get("status"),
        "timestamp_uncertainty_ns": uncertainty,
        "source_status": (
            record.get("lineage", {}).get("source_status")
            if isinstance(record.get("lineage"), Mapping)
            else None
        ),
        "payload_artifact": {
            "artifact_id": artifact.get("artifact_id"),
            "path": artifact.get("path"),
            "sha256": artifact.get("sha256"),
        },
        "payload": deepcopy(dict(payload)),
        "available_to_estimator": True,
        "masked": False,
        "mask_reason": None,
        "timeline_group": None,
        "cross_source_order": "not_evaluated",
    }


def _calibrated_window_index(package: ReplayPackage) -> dict[tuple[str, str], dict[str, Any]]:
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for stream_id, stream in package.streams.items():
        if (
            stream.get("status") != "captured"
            or stream.get("source") != "imu"
            or stream.get("variant") != "calibrated"
            or not isinstance(stream.get("source_stream_id"), str)
        ):
            continue
        for row in package.stream_rows.get(stream_id, []):
            source_window = row.get("source_window")
            if isinstance(source_window, Mapping) and isinstance(source_window.get("window_id"), str):
                key = (str(stream["source_stream_id"]), str(source_window["window_id"]))
                if key in index:
                    raise FieldSessionReplayError(
                        f"duplicate calibrated IMU window: {source_window['window_id']}"
                    )
                index[key] = dict(row)
    return index


def _expand_imu_item(
    base: Mapping[str, Any],
    record: Mapping[str, Any],
    calibrated_window: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    if calibrated_window is None:
        return [dict(base)]
    samples = calibrated_window.get("samples")
    if not isinstance(samples, list):
        raise FieldSessionReplayError("calibrated IMU window has no samples")
    derivation = record.get("imu_sample_derivation")
    if not isinstance(derivation, Mapping):
        raise FieldSessionReplayError("calibrated IMU window has no sample-time derivation")
    capture_start_us = _int_value(derivation.get("capture_start_uptime_us"))
    if capture_start_us is None:
        raise FieldSessionReplayError("IMU capture_start_uptime_us is unavailable")
    base_monotonic_ns = _int_value(base.get("timestamp_monotonic_ns"))
    base_utc_ns = _int_value(base.get("timestamp_utc_ns"))
    expanded: list[dict[str, Any]] = []
    for ordinal, sample_value in enumerate(samples):
        if not isinstance(sample_value, Mapping):
            raise FieldSessionReplayError("calibrated IMU sample is not an object")
        offset_us = _int_value(sample_value.get("offset_us"))
        sample_index = _int_value(sample_value.get("index"))
        if offset_us is None or sample_index is None:
            raise FieldSessionReplayError("calibrated IMU sample index/offset is unavailable")
        monotonic_ns = (capture_start_us + offset_us) * 1000
        utc_ns = None
        if base_utc_ns is not None and base_monotonic_ns is not None:
            utc_ns = base_utc_ns + monotonic_ns - base_monotonic_ns
        item = deepcopy(dict(base))
        item.update(
            {
                "observation_id": f"{base.get('observation_id')}:sample-{sample_index}",
                "sample_index": sample_index,
                "timestamp_monotonic_ns": monotonic_ns,
                "timestamp_utc_ns": utc_ns,
                "timestamp_utc": format_utc_ns(utc_ns) if utc_ns is not None else None,
                "payload": {
                    "window_id": derivation.get("window_id"),
                    "calibration_id": calibrated_window.get("calibration_id"),
                    "calibration_identity_sha256": calibrated_window.get(
                        "calibration_identity_sha256"
                    ),
                    "uncalibrated": deepcopy(sample_value.get("uncalibrated")),
                    "calibrated": deepcopy(sample_value.get("calibrated")),
                    "offset_us": offset_us,
                    "sample_index": sample_index,
                },
            }
        )
        # The schema guarantees order, but retaining ordinal as the last
        # deterministic tie-breaker protects replay from equal offsets.
        item["_ordinal"] = ordinal
        expanded.append(item)
    return expanded


def _manual_event_items(package: ReplayPackage) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for stream_id, stream in package.streams.items():
        if stream.get("status") != "captured" or stream.get("source") != "manual_event":
            continue
        artifact = package.artifacts[str(stream["artifact_id"])]
        for ordinal, row in enumerate(package.stream_rows.get(stream_id, [])):
            timestamp_utc = row.get("timestamp_utc")
            utc_ns = None
            if (
                isinstance(timestamp_utc, str)
                and row.get("alignment_status") in SAFE_ALIGNMENT_STATUSES
            ):
                try:
                    utc_ns = parse_utc_ns(timestamp_utc, "manual event timestamp_utc")
                except SensorTimeLineageError as error:
                    raise FieldSessionReplayError(str(error)) from error
            result.append(
                {
                    "observation_id": row.get("event_id"),
                    "source": "manual_event",
                    "stream_id": stream_id,
                    "sequence_id": row.get("sequence_id"),
                    "sample_index": None,
                    "device_id": None,
                    "device_run_id": row.get("device_run_id"),
                    "timestamp_monotonic_ns": row.get("timestamp_monotonic_ns"),
                    "timestamp_utc": timestamp_utc,
                    "timestamp_utc_ns": utc_ns,
                    "monotonic_clock_domain_id": row.get("monotonic_clock_domain_id"),
                    "boot_count": row.get("boot_count"),
                    "alignment_status": row.get("alignment_status"),
                    "timestamp_uncertainty_ns": row.get("timestamp_uncertainty_ns"),
                    "source_status": "operator_weak_label",
                    "payload_artifact": {
                        "artifact_id": artifact.get("artifact_id"),
                        "path": artifact.get("path"),
                        "sha256": artifact.get("sha256"),
                    },
                    "payload": deepcopy(row),
                    "available_to_estimator": True,
                    "masked": False,
                    "mask_reason": None,
                    "timeline_group": None,
                    "cross_source_order": "not_evaluated",
                    "_ordinal": ordinal,
                }
            )
    return result


def _timeline_sort_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    source_rank = SOURCE_ORDER.get(str(row.get("source")), 99)
    sequence = _int_value(row.get("sequence_id"))
    sample_index = _int_value(row.get("sample_index"))
    ordinal = _int_value(row.get("_ordinal"))
    return (
        _int_value(row.get("timestamp_utc_ns")) or 0,
        source_rank,
        sequence if sequence is not None else 2**63 - 1,
        sample_index if sample_index is not None else 2**31 - 1,
        ordinal if ordinal is not None else 0,
        str(row.get("observation_id") or ""),
    )


def _uncertainty_interval(row: Mapping[str, Any]) -> tuple[int, int] | None:
    utc_ns = _int_value(row.get("timestamp_utc_ns"))
    uncertainty_ns = _int_value(row.get("timestamp_uncertainty_ns"))
    if utc_ns is None or uncertainty_ns is None:
        return None
    return utc_ns - uncertainty_ns, utc_ns + uncertainty_ns


def mark_ambiguous_cross_source_order(rows: list[dict[str, Any]]) -> int:
    ambiguous: set[int] = set()
    timed_indices = [
        index
        for index, row in enumerate(rows)
        if row.get("timeline_group") == "cross_source_utc"
    ]
    for left_position, left_index in enumerate(timed_indices):
        left = rows[left_index]
        left_interval = _uncertainty_interval(left)
        if left_interval is None:
            continue
        for right_index in timed_indices[left_position + 1 :]:
            right = rows[right_index]
            right_interval = _uncertainty_interval(right)
            if right_interval is None or right_interval[0] > left_interval[1]:
                break
            if (
                left.get("source") != right.get("source")
                or left.get("device_run_id") != right.get("device_run_id")
            ) and right_interval[0] <= left_interval[1]:
                ambiguous.update({left_index, right_index})
    for index in timed_indices:
        rows[index]["cross_source_order"] = (
            "ambiguous_uncertainty_overlap" if index in ambiguous else "ordered_with_declared_uncertainty"
        )
    return len(ambiguous)


def build_replay_timeline(package: ReplayPackage) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    calibrated = _calibrated_window_index(package)
    rows: list[dict[str, Any]] = []
    records_by_stream = Counter(str(record.get("stream_id")) for record in package.time_records)
    for record in package.time_records:
        stream_id = str(record.get("stream_id"))
        stream = package.streams.get(stream_id)
        if stream is None:
            raise FieldSessionReplayError(f"time record references unknown stream: {stream_id}")
        artifact = package.artifacts.get(str(stream.get("artifact_id")))
        if artifact is None:
            raise FieldSessionReplayError(f"stream artifact is unavailable: {stream_id}")
        payload = _find_payload_row(
            record,
            package.stream_rows.get(stream_id, []),
            artifact_format=str(artifact.get("format")),
        )
        base = _base_timeline_item(record, stream, payload, artifact)
        derivation = record.get("imu_sample_derivation")
        window_id = derivation.get("window_id") if isinstance(derivation, Mapping) else None
        calibrated_window = (
            calibrated.get((stream_id, str(window_id))) if window_id is not None else None
        )
        rows.extend(_expand_imu_item(base, record, calibrated_window))

    rows.extend(_manual_event_items(package))
    timed: list[dict[str, Any]] = []
    same_source_timed: list[dict[str, Any]] = []
    unordered: list[dict[str, Any]] = []
    for row in rows:
        if (
            _int_value(row.get("timestamp_utc_ns")) is not None
            and row.get("alignment_status") in SAFE_ALIGNMENT_STATUSES
            and _int_value(row.get("timestamp_uncertainty_ns")) is not None
        ):
            row["timeline_group"] = "cross_source_utc"
            timed.append(row)
        elif (
            row.get("source") == "gnss"
            and _int_value(row.get("gnss_source_utc_ns")) is not None
            and row.get("timestamp_utc_origin") == "source_timestamp"
        ):
            row["timeline_group"] = "gnss_source_utc_only"
            row["cross_source_order"] = "unavailable"
            same_source_timed.append(row)
        else:
            row["timeline_group"] = "clock_domain_local_or_unavailable"
            row["cross_source_order"] = "unavailable"
            unordered.append(row)
    timed.sort(key=_timeline_sort_key)
    same_source_timed.sort(
        key=lambda row: (
            _int_value(row.get("gnss_source_utc_ns")) or 0,
            _int_value(row.get("sequence_id")) or 0,
            str(row.get("observation_id") or ""),
        )
    )
    unordered.sort(
        key=lambda row: (
            str(row.get("monotonic_clock_domain_id") or "~unavailable"),
            _int_value(row.get("timestamp_monotonic_ns")) or 0,
            SOURCE_ORDER.get(str(row.get("source")), 99),
            _int_value(row.get("sequence_id")) or 0,
            _int_value(row.get("sample_index")) or 0,
        )
    )
    timeline = timed + same_source_timed + unordered
    ambiguous_count = mark_ambiguous_cross_source_order(timeline)
    for row in timeline:
        row.pop("_ordinal", None)
    summary = {
        "record_count": len(timeline),
        "cross_source_ordered_count": len(timed),
        "same_source_utc_only_count": len(same_source_timed),
        "unordered_count": len(unordered),
        "ambiguous_record_count": ambiguous_count,
        "source_counts": dict(sorted(Counter(str(row["source"]) for row in timeline).items())),
        "time_record_counts_by_stream": dict(sorted(records_by_stream.items())),
    }
    return timeline, summary


def _gnss_evaluation_time(row: Mapping[str, Any]) -> tuple[int | None, str | None]:
    """Return a GNSS-only clock without inventing cross-source alignment."""

    aligned = _int_value(row.get("timestamp_utc_ns"))
    if aligned is not None and row.get("alignment_status") in SAFE_ALIGNMENT_STATUSES:
        return aligned, "cross_source_aligned_utc"
    direct = _int_value(row.get("gnss_source_utc_ns"))
    if (
        direct is not None
        and row.get("source") == "gnss"
        and row.get("alignment_status") == "unavailable"
        and row.get("timestamp_utc_origin") == "source_timestamp"
    ):
        return direct, "gnss_direct_source_utc"
    return None, None


def apply_gnss_mask(
    timeline: Sequence[Mapping[str, Any]],
    *,
    start_utc: str,
    duration_s: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        start_ns = parse_utc_ns(start_utc, "GNSS mask start")
    except SensorTimeLineageError as error:
        raise FieldSessionReplayError(str(error)) from error
    if isinstance(duration_s, bool) or duration_s <= 0:
        raise FieldSessionReplayError("GNSS mask duration must be a positive integer")
    end_ns = start_ns + duration_s * 1_000_000_000
    output = deepcopy([dict(row) for row in timeline])
    masked_count = 0
    time_basis_counts: Counter[str] = Counter()
    for row in output:
        if row.get("source") != "gnss":
            continue
        timestamp_ns, time_basis = _gnss_evaluation_time(row)
        if timestamp_ns is None or time_basis is None:
            raise FieldSessionReplayError(
                "GNSS mask membership is indeterminate because source UTC alignment is unavailable"
            )
        time_basis_counts[time_basis] += 1
        if start_ns <= timestamp_ns < end_ns:
            row["available_to_estimator"] = False
            row["masked"] = True
            row["mask_reason"] = "gnss_blackout_interval"
            masked_count += 1
    return output, {
        "source": "gnss",
        "interval_semantics": "start_inclusive_end_exclusive",
        "start_utc": format_utc_ns(start_ns),
        "end_utc": format_utc_ns(end_ns),
        "duration_s": duration_s,
        "masked_observation_count": masked_count,
        "time_basis_counts": dict(sorted(time_basis_counts.items())),
        "cross_source_aligned": bool(time_basis_counts)
        and set(time_basis_counts) <= {"cross_source_aligned_utc"},
    }


def _manifest_sha256(package: ReplayPackage) -> str:
    return sha256_file(package.manifest_path)


def deterministic_generated_at(package: ReplayPackage, override: str | None = None) -> str:
    if override is not None:
        try:
            parse_utc_ns(override, "generated_at")
        except SensorTimeLineageError as error:
            raise FieldSessionReplayError(str(error)) from error
        return override
    seal = package.manifest.get("seal")
    sealed_at = seal.get("sealed_at_utc") if isinstance(seal, Mapping) else None
    if isinstance(sealed_at, str):
        return sealed_at
    return str(package.manifest.get("created_at_utc") or "1970-01-01T00:00:00Z")


def build_replay_report(
    package: ReplayPackage,
    timeline: Sequence[Mapping[str, Any]],
    timeline_summary: Mapping[str, Any],
    *,
    mask: Mapping[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    field_eligible = package.validation.get("field_eligible") is True
    return {
        "report_version": REPLAY_REPORT_VERSION,
        "generated_at_utc": deterministic_generated_at(package, generated_at),
        "session_id": package.manifest.get("session_id"),
        "source_manifest": {
            "file_name": package.manifest_path.name,
            "sha256": _manifest_sha256(package),
        },
        "input_validation": {
            "valid": True,
            "complete": True,
            "sealed": True,
            "manifest_file_binding_verified": True,
            "artifact_integrity_verified": True,
            "package_closure_verified": True,
            "field_eligible": field_eligible,
            "field_eligibility_scope": package.validation.get("field_eligibility_scope"),
            "field_eligibility_reasons": list(
                package.validation.get("field_eligibility_reasons", [])
            ),
        },
        "execution": {
            "status": "completed",
            "evidence_scope": (
                "structural_field_review_only" if field_eligible else "engineering_smoke_only"
            ),
            "timeline": dict(timeline_summary),
            "gnss_mask": dict(mask) if mask is not None else None,
        },
        "gate_status": "unverified",
        "non_claims": [
            "replay_completion_is_not_a0_006_or_a_r0_gate_pass",
            "field_eligibility_is_structural_review_only",
            "estimated_alignment_is_not_measured_four_source_synchronization",
            "gnss_direct_source_utc_is_same_source_only_not_cross_source_alignment",
        ],
        "privacy": {
            "timeline_contains_private_sensor_data": True,
            "outputs_must_not_be_committed": True,
        },
    }


def _nested_dict(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _coordinate(payload: Mapping[str, Any]) -> tuple[float, float] | None:
    candidates = [
        payload,
        _nested_dict(payload.get("gnss")),
        _nested_dict(payload.get("location")),
        _nested_dict(payload.get("position")),
    ]
    for candidate in candidates:
        lat = next(
            (
                _float_value(candidate.get(key))
                for key in ("lat", "latitude", "latitude_deg")
                if candidate.get(key) is not None
            ),
            None,
        )
        lon = next(
            (
                _float_value(candidate.get(key))
                for key in ("lon", "longitude", "longitude_deg")
                if candidate.get(key) is not None
            ),
            None,
        )
        if lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180:
            return lat, lon
    return None


def _bool_fix(payload: Mapping[str, Any]) -> bool:
    for candidate in (payload, _nested_dict(payload.get("gnss"))):
        value = candidate.get("fix")
        if value is True:
            return True
        if value is False:
            return False
    return False


def _trusted_gnss_point(row: Mapping[str, Any]) -> tuple[float, float] | None:
    if (
        row.get("source") != "gnss"
        or row.get("source_status") not in TRUSTED_SOURCE_STATUSES
        or _gnss_evaluation_time(row)[0] is None
    ):
        return None
    payload = _nested_dict(row.get("payload"))
    if not _bool_fix(payload):
        return None
    return _coordinate(payload)


def haversine_m(left: tuple[float, float], right: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, left)
    lat2, lon2 = map(math.radians, right)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    value = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(value)))


def _canonical_cell_component(value: Any) -> str | None:
    if value is None:
        return None
    rendered = str(value).strip().upper()
    return rendered or None


def _cell_fields(payload: Mapping[str, Any]) -> dict[str, str] | None:
    cell = _nested_dict(payload.get("cell"))
    values = {
        "rat": _canonical_cell_component(cell.get("rat") or cell.get("cell_rat") or payload.get("cell_rat")),
        "mcc": _canonical_cell_component(cell.get("mcc") or payload.get("cell_mcc")),
        "mnc": _canonical_cell_component(cell.get("mnc") or payload.get("cell_mnc")),
        "tac": _canonical_cell_component(cell.get("tac") or payload.get("cell_tac")),
        "cell_id": _canonical_cell_component(cell.get("cell_id") or payload.get("cell_id")),
    }
    if any(value is None for value in values.values()):
        return None
    return {key: str(value) for key, value in values.items()}


def canonical_cell_key(fields: Mapping[str, Any]) -> str | None:
    normalized = {
        key: _canonical_cell_component(fields.get(key))
        for key in ("rat", "mcc", "mnc", "tac", "cell_id")
    }
    if any(value is None for value in normalized.values()):
        return None
    return "|".join(str(normalized[key]) for key in ("rat", "mcc", "mnc", "tac", "cell_id"))


def load_lte_centroids(path: Path | None) -> tuple[dict[str, tuple[float, float]], dict[str, Any]]:
    if path is None:
        return {}, {
            "status": "unavailable",
            "reason_codes": ["lte_centroid_artifact_not_provided"],
            "sha256": None,
            "version": None,
        }
    resolved = path.resolve()
    try:
        payload = field_session.load_json(resolved)
    except (OSError, ValueError, field_session.FieldSessionError) as error:
        return {}, {
            "status": "unavailable",
            "reason_codes": ["lte_centroid_artifact_invalid"],
            "detail": str(error),
            "sha256": None,
            "version": None,
        }
    version = payload.get("version")
    provenance = payload.get("provenance")
    entries = payload.get("entries")
    if (
        not isinstance(version, str)
        or not version.strip()
        or not isinstance(provenance, (str, Mapping))
        or not provenance
        or not isinstance(entries, list)
        or not entries
    ):
        return {}, {
            "status": "unavailable",
            "reason_codes": ["lte_centroid_artifact_invalid"],
            "sha256": sha256_file(resolved),
            "version": version if isinstance(version, str) else None,
        }
    centroids: dict[str, tuple[float, float]] = {}
    for entry in entries:
        if not isinstance(entry, Mapping) or not isinstance(entry.get("cell"), Mapping):
            return {}, {
                "status": "unavailable",
                "reason_codes": ["lte_centroid_artifact_invalid"],
                "sha256": sha256_file(resolved),
                "version": version,
            }
        key = canonical_cell_key(entry["cell"])
        coordinate = _coordinate(entry)
        if key is None or coordinate is None or key in centroids:
            return {}, {
                "status": "unavailable",
                "reason_codes": ["lte_centroid_artifact_invalid"],
                "sha256": sha256_file(resolved),
                "version": version,
            }
        centroids[key] = coordinate
    return centroids, {
        "status": "available",
        "reason_codes": [],
        "sha256": sha256_file(resolved),
        "version": version,
        "entry_count": len(centroids),
        "provenance_recorded": True,
    }


def _lte_observations(timeline: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in timeline:
        if (
            row.get("source") != "lte"
            or row.get("source_status") not in TRUSTED_SOURCE_STATUSES
            or row.get("alignment_status") not in SAFE_ALIGNMENT_STATUSES
        ):
            continue
        timestamp_ns = _int_value(row.get("timestamp_utc_ns"))
        fields = _cell_fields(_nested_dict(row.get("payload")))
        if timestamp_ns is None:
            continue
        result.append(
            {
                "timestamp_ns": timestamp_ns,
                "cell_key": canonical_cell_key(fields) if fields is not None else None,
                "observation_id": row.get("observation_id"),
            }
        )
    return sorted(result, key=lambda value: (value["timestamp_ns"], str(value["observation_id"])))


def _calibrated_imu_samples(timeline: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for row in timeline:
        if (
            row.get("source") != "imu"
            or row.get("source_status") not in TRUSTED_SOURCE_STATUSES
            or row.get("alignment_status") not in SAFE_ALIGNMENT_STATUSES
        ):
            continue
        timestamp_ns = _int_value(row.get("timestamp_utc_ns"))
        payload = _nested_dict(row.get("payload"))
        calibrated = _nested_dict(payload.get("calibrated"))
        accel = calibrated.get("accel_m_s2")
        if (
            timestamp_ns is None
            or not isinstance(payload.get("calibration_id"), str)
            or not isinstance(accel, list)
            or len(accel) != 3
        ):
            continue
        vector = tuple(_float_value(value) for value in accel)
        if any(value is None for value in vector):
            continue
        samples.append(
            {
                "timestamp_ns": timestamp_ns,
                "accel_m_s2": tuple(float(value) for value in vector),
                "calibration_id": payload["calibration_id"],
            }
        )
    return sorted(samples, key=lambda value: value["timestamp_ns"])


def _imu_coverage_reason(
    samples: Sequence[Mapping[str, Any]],
    *,
    start_ns: int,
    end_ns: int,
    max_gap_s: float,
) -> str | None:
    inside = [
        _int_value(sample.get("timestamp_ns"))
        for sample in samples
        if _int_value(sample.get("timestamp_ns")) is not None
        and start_ns <= int(sample["timestamp_ns"]) <= end_ns
    ]
    if not inside:
        return "calibrated_imu_blackout_coverage_missing"
    max_gap_ns = int(max_gap_s * 1_000_000_000)
    boundaries = [start_ns, *inside, end_ns]
    if any(right - left > max_gap_ns for left, right in zip(boundaries, boundaries[1:])):
        return "calibrated_imu_blackout_gap_exceeded"
    return None


def _motion_state(
    samples: Sequence[Mapping[str, Any]],
    *,
    timestamp_ns: int,
    window_s: float,
    threshold_m_s2: float,
    min_samples: int,
) -> str:
    start_ns = timestamp_ns - int(window_s * 1_000_000_000)
    deviations: list[float] = []
    for sample in samples:
        sample_time = _int_value(sample.get("timestamp_ns"))
        if sample_time is None or not (start_ns <= sample_time <= timestamp_ns):
            continue
        accel = sample.get("accel_m_s2")
        if not isinstance(accel, tuple) or len(accel) != 3:
            continue
        magnitude = math.sqrt(sum(float(value) ** 2 for value in accel))
        deviations.append(magnitude - STANDARD_GRAVITY_M_S2)
    if len(deviations) < min_samples:
        return "unknown"
    rms = math.sqrt(sum(value * value for value in deviations) / len(deviations))
    return "moving" if rms >= threshold_m_s2 else "stationary"


def _latest_lte_position(
    observations: Sequence[Mapping[str, Any]],
    centroids: Mapping[str, tuple[float, float]],
    timestamp_ns: int,
) -> tuple[tuple[float, float] | None, str | None]:
    eligible = [row for row in observations if int(row["timestamp_ns"]) <= timestamp_ns]
    if not eligible:
        return None, "lte_observation_before_evaluation_missing"
    latest = eligible[-1]
    key = latest.get("cell_key")
    if not isinstance(key, str):
        return None, "lte_cell_key_incomplete"
    coordinate = centroids.get(key)
    if coordinate is None:
        return None, "lte_cell_coordinate_lookup_unavailable"
    return coordinate, None


def _motion_gated_lte_position(
    observations: Sequence[Mapping[str, Any]],
    centroids: Mapping[str, tuple[float, float]],
    imu_samples: Sequence[Mapping[str, Any]],
    *,
    timestamp_ns: int,
    blackout_start_ns: int,
    config: ExperimentConfig,
) -> tuple[tuple[float, float] | None, str | None]:
    eligible = [row for row in observations if int(row["timestamp_ns"]) <= timestamp_ns]
    if not eligible:
        return None, "lte_observation_before_evaluation_missing"
    current: tuple[float, float] | None = None
    current_key: str | None = None
    for observation in eligible:
        key = observation.get("cell_key")
        if not isinstance(key, str):
            return None, "lte_cell_key_incomplete"
        coordinate = centroids.get(key)
        if coordinate is None:
            return None, "lte_cell_coordinate_lookup_unavailable"
        event_time = int(observation["timestamp_ns"])
        if current is None or event_time < blackout_start_ns:
            current = coordinate
            current_key = key
            continue
        if key == current_key:
            continue
        state = _motion_state(
            imu_samples,
            timestamp_ns=event_time,
            window_s=config.motion_window_s,
            threshold_m_s2=config.motion_threshold_m_s2,
            min_samples=config.motion_min_samples,
        )
        if state == "unknown":
            return None, "imu_motion_state_unavailable_at_lte_update"
        if state == "moving":
            current = coordinate
            current_key = key
    return current, None


def _reference_points(
    timeline: Sequence[Mapping[str, Any]],
    *,
    start_ns: int,
    end_ns: int,
) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for row in timeline:
        timestamp_ns, time_basis = _gnss_evaluation_time(row)
        coordinate = _trusted_gnss_point(row)
        # The endpoint is evaluated separately.  A reference point belongs to
        # the blackout only when the estimator actually had it masked under
        # the public [start, end) interval semantics.
        if timestamp_ns is not None and coordinate is not None and start_ns <= timestamp_ns < end_ns:
            points.append(
                {
                    "timestamp_ns": timestamp_ns,
                    "coordinate": coordinate,
                    "observation_id": row.get("observation_id"),
                    "time_basis": time_basis,
                }
            )
    return sorted(points, key=lambda point: (point["timestamp_ns"], str(point["observation_id"])))


def _endpoint_reference(
    timeline: Sequence[Mapping[str, Any]],
    *,
    start_ns: int,
    end_ns: int,
    tolerance_s: float,
) -> dict[str, Any] | None:
    tolerance_ns = int(tolerance_s * 1_000_000_000)
    candidates: list[dict[str, Any]] = []
    for row in timeline:
        timestamp_ns, time_basis = _gnss_evaluation_time(row)
        coordinate = _trusted_gnss_point(row)
        if (
            timestamp_ns is not None
            and coordinate is not None
            and timestamp_ns >= start_ns
            and abs(timestamp_ns - end_ns) <= tolerance_ns
        ):
            candidates.append(
                {
                    "timestamp_ns": timestamp_ns,
                    "coordinate": coordinate,
                    "offset_s": round((timestamp_ns - end_ns) / 1_000_000_000, 9),
                    "observation_id": row.get("observation_id"),
                    "time_basis": time_basis,
                }
            )
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda point: (
            abs(point["timestamp_ns"] - end_ns),
            point["timestamp_ns"],
            str(point["observation_id"]),
        ),
    )


Prediction = Callable[[int], tuple[tuple[float, float] | None, str | None]]


def _evaluate_baseline(
    baseline_id: str,
    description: str,
    prediction: Prediction | None,
    references: Sequence[Mapping[str, Any]],
    endpoint_reference: Mapping[str, Any] | None,
    *,
    start_ns: int,
    end_ns: int,
    unavailable_reasons: Sequence[str] = (),
    notes: Sequence[str] = (),
) -> tuple[dict[str, Any], list[tuple[int, tuple[float, float]]]]:
    reasons = list(dict.fromkeys(str(reason) for reason in unavailable_reasons if reason))
    if prediction is None:
        return {
            "baseline_id": baseline_id,
            "description": description,
            "status": "unavailable",
            "reason_codes": reasons or ["baseline_prerequisites_unavailable"],
            "samples_evaluated": 0,
            "error_vs_time": [],
            "endpoint_error_m": None,
            "notes": list(notes),
        }, []

    series: list[dict[str, Any]] = []
    positions: list[tuple[int, tuple[float, float]]] = []
    prediction_reasons: list[str] = []
    for reference in references:
        timestamp_ns = int(reference["timestamp_ns"])
        coordinate, reason = prediction(timestamp_ns)
        if coordinate is None:
            if reason:
                prediction_reasons.append(reason)
            continue
        error_m = haversine_m(coordinate, tuple(reference["coordinate"]))
        series.append(
            {
                "time_offset_s": round((timestamp_ns - start_ns) / 1_000_000_000, 9),
                "error_m": round(error_m, 6),
            }
        )
        positions.append((timestamp_ns, coordinate))

    endpoint_error: float | None = None
    if endpoint_reference is None:
        prediction_reasons.append("endpoint_reference_unavailable")
    else:
        endpoint_position, endpoint_reason = prediction(end_ns)
        if endpoint_position is None:
            prediction_reasons.append(endpoint_reason or "endpoint_prediction_unavailable")
        else:
            endpoint_error = round(
                haversine_m(endpoint_position, tuple(endpoint_reference["coordinate"])),
                6,
            )
            positions.append((end_ns, endpoint_position))

    reasons.extend(prediction_reasons)
    reasons = list(dict.fromkeys(reasons))
    if not series and endpoint_error is None:
        status = "unavailable"
    elif endpoint_error is None or len(series) != len(references):
        status = "partial"
    else:
        status = "available"
    return {
        "baseline_id": baseline_id,
        "description": description,
        "status": status,
        "reason_codes": reasons,
        "samples_evaluated": len(series),
        "error_vs_time": series,
        "endpoint_error_m": endpoint_error,
        "notes": list(notes),
    }, positions


def evaluate_exp_a1_000(
    timeline: Sequence[Mapping[str, Any]],
    *,
    config: ExperimentConfig,
    lte_centroids: Mapping[str, tuple[float, float]],
    lte_centroid_artifact: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, list[tuple[int, tuple[float, float]]]]]:
    config.validate()
    start_ns = parse_utc_ns(config.blackout_start_utc, "blackout_start_utc")
    end_ns = start_ns + config.blackout_duration_s * 1_000_000_000
    references = _reference_points(timeline, start_ns=start_ns, end_ns=end_ns)
    endpoint = _endpoint_reference(
        timeline,
        start_ns=start_ns,
        end_ns=end_ns,
        tolerance_s=config.endpoint_tolerance_s,
    )
    pre_gnss: list[tuple[int, tuple[float, float], str]] = []
    for row in timeline:
        point = _trusted_gnss_point(row)
        timestamp_ns, time_basis = _gnss_evaluation_time(row)
        if (
            point is not None
            and timestamp_ns is not None
            and time_basis is not None
            and timestamp_ns < start_ns
        ):
            pre_gnss.append((timestamp_ns, point, time_basis))
    pre_gnss.sort(key=lambda value: value[0])
    common_reasons: list[str] = []
    if not references:
        common_reasons.extend(
            [
                "full_gnss_reference_unavailable",
                "gnss_blackout_masked_reference_missing",
            ]
        )

    lkp_prediction: Prediction | None = None
    lkp_reasons = list(common_reasons)
    if pre_gnss:
        last_position = pre_gnss[-1][1]
        lkp_prediction = lambda _timestamp_ns: (last_position, None)
    else:
        lkp_reasons.append("last_trusted_gnss_before_blackout_missing")

    lte_observations = _lte_observations(timeline)
    centroid_available = lte_centroid_artifact.get("status") == "available"
    lte_reasons = list(common_reasons)
    if not centroid_available:
        lte_reasons.extend(lte_centroid_artifact.get("reason_codes", []))
    if not lte_observations:
        lte_reasons.append("lte_source_time_or_observation_unavailable")
    references_cross_source_aligned = bool(references) and all(
        reference.get("time_basis") == "cross_source_aligned_utc"
        for reference in references
    ) and (
        endpoint is None or endpoint.get("time_basis") == "cross_source_aligned_utc"
    )
    if references and not references_cross_source_aligned:
        lte_reasons.append("gnss_reference_not_cross_source_aligned")
    lte_prediction: Prediction | None = None
    if centroid_available and lte_observations and references_cross_source_aligned:
        lte_prediction = lambda timestamp_ns: _latest_lte_position(
            lte_observations, lte_centroids, timestamp_ns
        )

    imu_samples = _calibrated_imu_samples(timeline)
    imu_reason = _imu_coverage_reason(
        imu_samples,
        start_ns=start_ns,
        end_ns=end_ns,
        max_gap_s=config.imu_max_gap_s,
    )
    motion_reasons = list(lte_reasons)
    if imu_reason:
        motion_reasons.append(imu_reason)
    motion_prediction: Prediction | None = None
    if (
        centroid_available
        and lte_observations
        and references_cross_source_aligned
        and imu_reason is None
    ):
        motion_prediction = lambda timestamp_ns: _motion_gated_lte_position(
            lte_observations,
            lte_centroids,
            imu_samples,
            timestamp_ns=timestamp_ns,
            blackout_start_ns=start_ns,
            config=config,
        )

    a_result, a_positions = _evaluate_baseline(
        "A",
        "last-known-position",
        lkp_prediction if references else None,
        references,
        endpoint,
        start_ns=start_ns,
        end_ns=end_ns,
        unavailable_reasons=lkp_reasons,
        notes=["same_gnss_source_clock_is_sufficient_for_baseline_a_only"],
    )
    b_result, b_positions = _evaluate_baseline(
        "B",
        "LTE coarse location from a frozen cell-centroid artifact",
        lte_prediction,
        references,
        endpoint,
        start_ns=start_ns,
        end_ns=end_ns,
        unavailable_reasons=lte_reasons,
        notes=["no_cell_coordinate_is_inferred_from_cell_id"],
    )
    c_result, c_positions = _evaluate_baseline(
        "C",
        "LTE centroid with calibrated-IMU motion gating",
        motion_prediction,
        references,
        endpoint,
        start_ns=start_ns,
        end_ns=end_ns,
        unavailable_reasons=motion_reasons,
        notes=[
            "moving_accepts_new_lte_centroid_stationary_holds_previous_centroid",
            "no_inertial_displacement_or_heading_estimate",
            "manual_events_are_not_detector_inputs",
        ],
    )
    baseline_results = [a_result, b_result, c_result]
    if all(result["status"] == "available" for result in baseline_results):
        run_status = "completed"
    elif any(result["samples_evaluated"] > 0 for result in baseline_results):
        run_status = "partial"
    else:
        run_status = "unavailable"

    reference_layer = [
        (int(point["timestamp_ns"]), tuple(point["coordinate"])) for point in references
    ]
    reference_time_basis_counts = Counter(
        str(point.get("time_basis") or "unavailable") for point in references
    )
    result = {
        "report_version": EXPERIMENT_REPORT_VERSION,
        "experiment_id": EXPERIMENT_ID,
        "run_status": run_status,
        "gate_status": "unverified",
        "blackout": {
            "source": "gnss",
            "interval_semantics": "start_inclusive_end_exclusive",
            "start_utc": format_utc_ns(start_ns),
            "end_utc": format_utc_ns(end_ns),
            "duration_s": config.blackout_duration_s,
        },
        "reference": {
            "type": "full_gnss_reference",
            "status": "available" if references else "unavailable",
            "point_count": len(references),
            "masked_reference_observation_count": len(references),
            "is_ground_truth": False,
            "endpoint_status": "available" if endpoint is not None else "unavailable",
            "endpoint_reference_offset_s": endpoint.get("offset_s") if endpoint else None,
            "endpoint_tolerance_s": config.endpoint_tolerance_s,
            "time_basis_counts": dict(sorted(reference_time_basis_counts.items())),
            "cross_source_aligned": references_cross_source_aligned,
            "reason_codes": [] if references else ["full_gnss_reference_unavailable"],
        },
        "configuration": {
            "motion_window_s": config.motion_window_s,
            "motion_threshold_m_s2": config.motion_threshold_m_s2,
            "motion_min_samples": config.motion_min_samples,
            "imu_max_gap_s": config.imu_max_gap_s,
        },
        "lte_centroid_artifact": dict(lte_centroid_artifact),
        "baselines": baseline_results,
        "non_claims": [
            "full_gnss_reference_is_not_ground_truth",
            "smoke_experiment_is_not_a_benchmark_pass",
            "no_learned_inertial_odometry_or_fusion",
            "no_uncertainty_calibration_claim",
            "gnss_direct_source_utc_is_not_cross_source_alignment",
        ],
        "privacy": {
            "raw_coordinates_exposed_in_result_json": False,
            "trajectory_render_is_private_field_evidence": True,
            "outputs_must_not_be_committed": True,
        },
    }
    return result, {
        "full_gnss_reference": reference_layer,
        "A_last_known": a_positions,
        "B_lte_coarse": b_positions,
        "C_lte_imu_motion": c_positions,
    }


def _svg_empty(title: str, message: str, *, width: int = 900, height: int = 520) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">\n'
        '<rect width="100%" height="100%" fill="#f8fafc"/>\n'
        f'<text x="32" y="48" font-family="sans-serif" font-size="22" fill="#0f172a">{html.escape(title)}</text>\n'
        f'<text x="32" y="88" font-family="sans-serif" font-size="14" fill="#64748b">{html.escape(message)}</text>\n'
        '</svg>\n'
    )


def render_trajectory_svg(
    layers: Mapping[str, Sequence[tuple[int, tuple[float, float]]]],
    *,
    title: str,
) -> str:
    width, height = 900, 520
    margin_left, margin_right, margin_top, margin_bottom = 70, 30, 70, 55
    points = [point for layer in layers.values() for _timestamp, point in layer]
    if not points:
        return _svg_empty(title, "No drawable WGS84 trajectory is available.")
    latitudes = [point[0] for point in points]
    longitudes = [point[1] for point in points]
    min_lat, max_lat = min(latitudes), max(latitudes)
    min_lon, max_lon = min(longitudes), max(longitudes)
    lat_span = max(max_lat - min_lat, 1e-7)
    lon_span = max(max_lon - min_lon, 1e-7)
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom

    def project(point: tuple[float, float]) -> tuple[float, float]:
        lat, lon = point
        x = margin_left + (lon - min_lon) / lon_span * plot_width
        y = margin_top + (max_lat - lat) / lat_span * plot_height
        return x, y

    colors = {
        "full_gnss_reference": "#0f766e",
        "A_last_known": "#dc2626",
        "B_lte_coarse": "#2563eb",
        "C_lte_imu_motion": "#7c3aed",
        "gnss": "#0f766e",
    }
    output = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#f8fafc"/>',
        f'<text x="{margin_left}" y="36" font-family="sans-serif" font-size="22" fill="#0f172a">{html.escape(title)}</text>',
        f'<rect x="{margin_left}" y="{margin_top}" width="{plot_width}" height="{plot_height}" fill="#ffffff" stroke="#cbd5e1"/>',
    ]
    legend_x = margin_left
    for index, (name, layer) in enumerate(layers.items()):
        color = colors.get(name, "#475569")
        projected = [project(point) for _timestamp, point in layer]
        if len(projected) >= 2:
            path = " ".join(
                ("M" if point_index == 0 else "L") + f" {x:.3f} {y:.3f}"
                for point_index, (x, y) in enumerate(projected)
            )
            output.append(
                f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2.5"/>'
            )
        for x, y in projected:
            output.append(f'<circle cx="{x:.3f}" cy="{y:.3f}" r="3" fill="{color}"/>')
        label_x = legend_x + index * 190
        output.extend(
            [
                f'<line x1="{label_x}" y1="{height - 22}" x2="{label_x + 24}" y2="{height - 22}" stroke="{color}" stroke-width="3"/>',
                f'<text x="{label_x + 30}" y="{height - 17}" font-family="sans-serif" font-size="12" fill="#334155">{html.escape(name)}</text>',
            ]
        )
    output.append(
        f'<text x="{margin_left}" y="{margin_top - 16}" font-family="sans-serif" font-size="12" fill="#64748b">Local WGS84 projection; no map tiles and no product accuracy claim.</text>'
    )
    output.append("</svg>")
    return "\n".join(output) + "\n"


def render_error_vs_time_svg(result: Mapping[str, Any]) -> str:
    width, height = 900, 520
    left, right, top, bottom = 70, 30, 65, 55
    series_by_name: dict[str, list[tuple[float, float]]] = {}
    for baseline in result.get("baselines", []):
        if not isinstance(baseline, Mapping):
            continue
        points = [
            (float(point["time_offset_s"]), float(point["error_m"]))
            for point in baseline.get("error_vs_time", [])
            if isinstance(point, Mapping)
        ]
        series_by_name[str(baseline.get("baseline_id"))] = points
    all_points = [point for series in series_by_name.values() for point in series]
    if not all_points:
        return _svg_empty("EXP-A1-000 error vs time", "No evaluable error series is available.")
    max_x = max(max(point[0] for point in all_points), 60.0)
    max_y = max(max(point[1] for point in all_points), 1.0)
    plot_width = width - left - right
    plot_height = height - top - bottom

    def project(point: tuple[float, float]) -> tuple[float, float]:
        return left + point[0] / max_x * plot_width, top + (max_y - point[1]) / max_y * plot_height

    colors = {"A": "#dc2626", "B": "#2563eb", "C": "#7c3aed"}
    output = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#f8fafc"/>',
        f'<text x="{left}" y="36" font-family="sans-serif" font-size="22" fill="#0f172a">EXP-A1-000 error vs time</text>',
        f'<rect x="{left}" y="{top}" width="{plot_width}" height="{plot_height}" fill="#fff" stroke="#cbd5e1"/>',
        f'<text x="{width / 2:.1f}" y="{height - 12}" text-anchor="middle" font-family="sans-serif" font-size="12" fill="#475569">seconds from first reference point</text>',
        f'<text x="18" y="{height / 2:.1f}" transform="rotate(-90 18 {height / 2:.1f})" text-anchor="middle" font-family="sans-serif" font-size="12" fill="#475569">position error (m)</text>',
    ]
    for index, (name, points) in enumerate(series_by_name.items()):
        color = colors.get(name, "#475569")
        projected = [project(point) for point in points]
        if len(projected) >= 2:
            path = " ".join(
                ("M" if point_index == 0 else "L") + f" {x:.3f} {y:.3f}"
                for point_index, (x, y) in enumerate(projected)
            )
            output.append(f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2.5"/>')
        for x, y in projected:
            output.append(f'<circle cx="{x:.3f}" cy="{y:.3f}" r="3" fill="{color}"/>')
        output.append(
            f'<text x="{left + index * 120}" y="{height - 32}" font-family="sans-serif" font-size="12" fill="{color}">Baseline {html.escape(name)}</text>'
        )
    output.append("</svg>")
    return "\n".join(output) + "\n"


def _gnss_layer(timeline: Sequence[Mapping[str, Any]]) -> list[tuple[int, tuple[float, float]]]:
    points: list[tuple[int, tuple[float, float]]] = []
    for row in timeline:
        timestamp_ns, _time_basis = _gnss_evaluation_time(row)
        coordinate = _trusted_gnss_point(row)
        if timestamp_ns is not None and coordinate is not None:
            points.append((timestamp_ns, coordinate))
    return sorted(points)


def write_replay_outputs(
    package: ReplayPackage,
    output_dir: Path,
    *,
    mask_start_utc: str | None = None,
    mask_duration_s: int | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    output = ensure_output_outside_session(output_dir, package.session_root)
    timeline, summary = build_replay_timeline(package)
    mask: dict[str, Any] | None = None
    if mask_start_utc is not None or mask_duration_s is not None:
        if mask_start_utc is None or mask_duration_s is None:
            raise FieldSessionReplayError("GNSS mask start and duration must be provided together")
        timeline, mask = apply_gnss_mask(
            timeline,
            start_utc=mask_start_utc,
            duration_s=mask_duration_s,
        )
    timeline_bytes = stable_jsonl_bytes(timeline)
    trajectory_svg = render_trajectory_svg(
        {"gnss": _gnss_layer(timeline)},
        title="Ego Link Field Session trajectory",
    )
    trajectory_bytes = trajectory_svg.encode("utf-8")
    report = build_replay_report(
        package,
        timeline,
        summary,
        mask=mask,
        generated_at=generated_at,
    )
    report["outputs"] = {
        "timeline": {
            "path": "timeline.jsonl",
            "sha256": sha256_bytes(timeline_bytes),
            "record_count": len(timeline),
        },
        "trajectory": {
            "path": "trajectory.svg",
            "sha256": sha256_bytes(trajectory_bytes),
        },
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "timeline.jsonl").write_bytes(timeline_bytes)
    (output / "trajectory.svg").write_bytes(trajectory_bytes)
    (output / "replay-summary.json").write_bytes(stable_json_bytes(report))
    return report


def write_exp_a1_000_outputs(
    package: ReplayPackage,
    output_dir: Path,
    *,
    config: ExperimentConfig,
    lte_centroid_path: Path | None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    output = ensure_output_outside_session(output_dir, package.session_root)
    timeline, timeline_summary = build_replay_timeline(package)
    masked_timeline, mask = apply_gnss_mask(
        timeline,
        start_utc=config.blackout_start_utc,
        duration_s=config.blackout_duration_s,
    )
    centroids, centroid_artifact = load_lte_centroids(lte_centroid_path)
    result, layers = evaluate_exp_a1_000(
        timeline,
        config=config,
        lte_centroids=centroids,
        lte_centroid_artifact=centroid_artifact,
    )
    result.update(
        {
            "generated_at_utc": deterministic_generated_at(package, generated_at),
            "session_id": package.manifest.get("session_id"),
            "source_manifest": {
                "file_name": package.manifest_path.name,
                "sha256": _manifest_sha256(package),
            },
            "input_validation": {
                "valid": True,
                "complete": True,
                "sealed": True,
                "artifact_integrity_verified": True,
                "package_closure_verified": True,
                "field_eligible": package.validation.get("field_eligible") is True,
                "field_eligibility_reasons": list(
                    package.validation.get("field_eligibility_reasons", [])
                ),
                "evidence_scope": (
                    "structural_field_review_only"
                    if package.validation.get("field_eligible") is True
                    else "engineering_smoke_only"
                ),
            },
            "mask_execution": mask,
            "timeline_summary": timeline_summary,
        }
    )
    trajectory_bytes = render_trajectory_svg(
        layers,
        title="EXP-A1-000 60-second GNSS blackout",
    ).encode("utf-8")
    error_bytes = render_error_vs_time_svg(result).encode("utf-8")
    result["outputs"] = {
        "trajectory": {
            "path": "trajectory.svg",
            "sha256": sha256_bytes(trajectory_bytes),
        },
        "error_vs_time": {
            "path": "error-vs-time.svg",
            "sha256": sha256_bytes(error_bytes),
        },
        "masked_gnss_observation_count": sum(
            1 for row in masked_timeline if row.get("masked") is True
        ),
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "trajectory.svg").write_bytes(trajectory_bytes)
    (output / "error-vs-time.svg").write_bytes(error_bytes)
    (output / "result.json").write_bytes(stable_json_bytes(result))
    return result

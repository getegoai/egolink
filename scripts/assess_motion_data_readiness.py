"""Assess whether bounded field evidence can support an IMU motion dataset.

The report is aggregate-only: it never writes raw messages, coordinates, cell
identifiers, or training rows. GNSS speed produces stationary/moving weak-label
coverage only; walking/vehicle labels always require later reviewed evidence.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "reports" / "motion_data_readiness"
REPORT_JSON = "motion_data_readiness_report.json"
REPORT_MARKDOWN = "motion_data_readiness_report.md"

if __package__ in (None, ""):
    sys.path.insert(0, str(REPO_ROOT))

from scripts import run_location_d2_d5_pipeline as pipeline  # noqa: E402


class MotionDataReadinessError(RuntimeError):
    """Raised when bounded evidence cannot be assessed safely."""


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def first_value(message: Mapping[str, Any], group: str, *keys: str) -> Any:
    nested = as_dict(message.get(group))
    for key in keys:
        if message.get(key) is not None:
            return message.get(key)
        if nested.get(key) is not None:
            return nested.get(key)
    return None


def bool_value(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


def number_value(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def timestamp_value(message: Mapping[str, Any]) -> datetime | None:
    raw = message.get("server_received_at") or message.get("received_at")
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * fraction) - 1))
    return ordered[index]


def safe_hash(value: object) -> str:
    return hashlib.sha256(str(value or "unknown").encode("utf-8")).hexdigest()[:16]


def relative_ref(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.name


def imu_metadata(message: Mapping[str, Any]) -> dict[str, Any] | None:
    nested = as_dict(message.get("imu"))
    has_top_level = any(str(key).startswith("imu_") for key in message)
    if not nested and not has_top_level:
        return None
    raw_mock = nested.get("data_is_mock")
    if raw_mock is None:
        raw_mock = message.get("imu_sample_mock")
    is_mock = bool_value(raw_mock)
    source_status = str(nested.get("source_status") or message.get("imu_source_status") or "unknown")
    evidence_status = str(nested.get("evidence_status") or message.get("imu_evidence_status") or "unknown")
    mock = is_mock is True or source_status == "mock" or evidence_status == "mock"
    return {
        "is_mock": is_mock,
        "observed": not mock and (is_mock is False or source_status == "observed" or evidence_status == "observed"),
        "mock": mock,
    }


def imu_sample(message: Mapping[str, Any]) -> dict[str, Any] | None:
    if message.get("message_type") != "event" or message.get("event_type") != "sensor_sample":
        return None
    timestamp = timestamp_value(message)
    axes = {
        name: number_value(first_value(message, "imu", f"imu_{name}", name))
        for name in (
            "accel_mg_x",
            "accel_mg_y",
            "accel_mg_z",
            "gyro_mdps_x",
            "gyro_mdps_y",
            "gyro_mdps_z",
        )
    }
    has_axes = all(value is not None for value in axes.values())
    is_mock = bool_value(first_value(message, "imu", "imu_sample_mock", "sample_mock", "data_is_mock"))
    hardware_present = bool_value(first_value(message, "imu", "imu_hardware_present", "hardware_present"))
    driver_enabled = bool_value(first_value(message, "imu", "imu_driver_enabled", "driver_enabled"))
    return {
        "timestamp": timestamp,
        "has_axes": has_axes,
        "is_mock": is_mock,
        "hardware_present": hardware_present,
        "driver_enabled": driver_enabled,
        "real": bool(timestamp and has_axes and is_mock is False and hardware_present is True and driver_enabled is True),
    }


def speed_observation(message: Mapping[str, Any], *, max_hdop: float) -> dict[str, Any] | None:
    if message.get("message_type") != "event" or message.get("event_type") != "location_report":
        return None
    if bool_value(first_value(message, "gnss", "fix")) is not True:
        return None
    timestamp = timestamp_value(message)
    speed = number_value(first_value(message, "gnss", "speed_mps", "speed"))
    hdop = number_value(first_value(message, "gnss", "hdop"))
    if timestamp is None or speed is None or speed < 0:
        return None
    if hdop is not None and hdop > max_hdop:
        return None
    return {"timestamp": timestamp, "speed_mps": speed, "hdop": hdop}


def classify_speed_window(
    sample_time: datetime,
    speed_observations: list[dict[str, Any]],
    *,
    label_window_sec: float,
    min_speed_samples: int,
    stationary_max_mps: float,
    moving_min_mps: float,
) -> str | None:
    nearby = [
        float(item["speed_mps"])
        for item in speed_observations
        if abs((item["timestamp"] - sample_time).total_seconds()) <= label_window_sec
    ]
    if len(nearby) < min_speed_samples:
        return None
    median_speed = statistics.median(nearby)
    if median_speed <= stationary_max_mps:
        return "stationary_candidate"
    if median_speed >= moving_min_mps:
        return "moving_candidate"
    return "ambiguous_speed"


def build_report(
    export: Mapping[str, Any],
    *,
    run_id: str,
    created_at: str,
    label_window_sec: float = 90.0,
    min_speed_samples: int = 2,
    stationary_max_mps: float = 0.3,
    moving_min_mps: float = 2.0,
    max_hdop: float = 5.0,
    max_model_interval_ms: float = 100.0,
    min_real_imu_samples: int = 100,
    min_joined_samples: int = 50,
) -> dict[str, Any]:
    window = as_dict(export.get("window"))
    if window and window.get("complete") is not True:
        raise MotionDataReadinessError("field export is incomplete or truncated")
    messages = [item for item in as_list(export.get("messages")) if isinstance(item, dict)]
    imu_metadata_events = [metadata for message in messages if (metadata := imu_metadata(message)) is not None]
    imu_samples = [sample for message in messages if (sample := imu_sample(message)) is not None]
    real_samples = [sample for sample in imu_samples if sample["real"]]
    mock_samples = [sample for sample in imu_samples if sample["is_mock"] is True]
    speed_samples = [
        sample
        for message in messages
        if (sample := speed_observation(message, max_hdop=max_hdop)) is not None
    ]

    real_times = sorted(sample["timestamp"] for sample in real_samples)
    intervals_ms = [
        (current - previous).total_seconds() * 1000.0
        for previous, current in zip(real_times, real_times[1:])
        if current > previous
    ]
    labels: dict[str, int] = {
        "stationary_candidate": 0,
        "moving_candidate": 0,
        "ambiguous_speed": 0,
        "unlabelled": 0,
    }
    for sample in real_samples:
        label = classify_speed_window(
            sample["timestamp"],
            speed_samples,
            label_window_sec=label_window_sec,
            min_speed_samples=min_speed_samples,
            stationary_max_mps=stationary_max_mps,
            moving_min_mps=moving_min_mps,
        )
        labels[label or "unlabelled"] += 1

    joined_count = len(real_samples) - labels["unlabelled"]
    median_interval_ms = statistics.median(intervals_ms) if intervals_ms else None
    p95_interval_ms = percentile(intervals_ms, 0.95)
    blockers: list[str] = []
    if len(real_samples) < min_real_imu_samples:
        blockers.append("insufficient_real_imu_samples")
    if median_interval_ms is None or median_interval_ms > max_model_interval_ms:
        blockers.append("imu_cadence_too_slow_or_unknown")
    if len(speed_samples) < min_speed_samples:
        blockers.append("insufficient_good_fix_speed_samples")
    if joined_count < min_joined_samples:
        blockers.append("insufficient_imu_gnss_join_coverage")
    if labels["stationary_candidate"] == 0:
        blockers.append("stationary_weak_label_missing")
    if labels["moving_candidate"] == 0:
        blockers.append("moving_weak_label_missing")

    device_ids = sorted({str(message.get("device_id")) for message in messages if message.get("device_id")})
    ready = not blockers
    return {
        "schema_version": "egolink.motion_data_readiness.v0.1",
        "run_id": run_id,
        "created_at": created_at,
        "status": "PASS" if ready else "WARN",
        "result": {
            "ready_for_motion_dataset_export": ready,
            "training_allowed": False,
            "three_class_labels_ready": False,
            "blockers": blockers,
        },
        "source": {
            "message_count": len(messages),
            "device_ref_hashes": [safe_hash(value) for value in device_ids],
            "bounded_export_complete": window.get("complete") if window else None,
        },
        "metrics": {
            "sensor_sample_event_count": len(imu_samples),
            "imu_metadata_event_count": len(imu_metadata_events),
            "observed_imu_metadata_count": sum(metadata["observed"] for metadata in imu_metadata_events),
            "mock_imu_metadata_count": sum(metadata["mock"] for metadata in imu_metadata_events),
            "real_imu_sample_count": len(real_samples),
            "mock_imu_sample_count": len(mock_samples),
            "imu_sample_without_axes_count": sum(not sample["has_axes"] for sample in imu_samples),
            "imu_interval_median_ms": round(median_interval_ms, 3) if median_interval_ms is not None else None,
            "imu_interval_p95_ms": round(p95_interval_ms, 3) if p95_interval_ms is not None else None,
            "good_fix_speed_sample_count": len(speed_samples),
            "imu_gnss_joined_sample_count": joined_count,
            "weak_label_counts": labels,
        },
        "thresholds": {
            "label_window_sec": label_window_sec,
            "min_speed_samples": min_speed_samples,
            "stationary_max_mps": stationary_max_mps,
            "moving_min_mps": moving_min_mps,
            "max_hdop": max_hdop,
            "max_model_interval_ms": max_model_interval_ms,
            "min_real_imu_samples": min_real_imu_samples,
            "min_joined_samples": min_joined_samples,
        },
        "label_boundary": {
            "generated_classes": ["stationary_candidate", "moving_candidate", "ambiguous_speed"],
            "walking_or_vehicle_generated": False,
            "reason": "GNSS speed is weak evidence for moving state, not reviewed walking/vehicle ground truth",
        },
        "scope": {
            "raw_messages_written": False,
            "raw_coordinates_written": False,
            "cell_identifiers_written": False,
            "training_rows_written": False,
            "model_training_started": False,
        },
        "next_step": (
            "Connect and validate QMI8658, then add an opt-in bounded high-rate IMU window capture if cadence remains above the model threshold."
        ),
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    metrics = as_dict(report.get("metrics"))
    result = as_dict(report.get("result"))
    labels = as_dict(metrics.get("weak_label_counts"))
    blockers = [str(item) for item in as_list(result.get("blockers"))]
    return "\n".join(
        [
            "# Motion Data Readiness",
            "",
            f"- Run: `{report.get('run_id')}`",
            f"- Result: **{report.get('status')}**",
            f"- Dataset export ready: **{result.get('ready_for_motion_dataset_export')}**",
            f"- Training allowed: **{result.get('training_allowed')}**",
            "",
            "## Evidence",
            "",
            f"- Sensor events: {metrics.get('sensor_sample_event_count')}",
            f"- IMU metadata events: {metrics.get('imu_metadata_event_count')} (observed {metrics.get('observed_imu_metadata_count')}, mock {metrics.get('mock_imu_metadata_count')})",
            f"- Real IMU samples: {metrics.get('real_imu_sample_count')}",
            f"- Mock IMU samples: {metrics.get('mock_imu_sample_count')}",
            f"- IMU interval median / p95: {metrics.get('imu_interval_median_ms')} / {metrics.get('imu_interval_p95_ms')} ms",
            f"- Good-fix speed samples: {metrics.get('good_fix_speed_sample_count')}",
            f"- IMU/GNSS joined samples: {metrics.get('imu_gnss_joined_sample_count')}",
            f"- Weak labels: stationary {labels.get('stationary_candidate', 0)}, moving {labels.get('moving_candidate', 0)}, ambiguous {labels.get('ambiguous_speed', 0)}",
            "",
            "## Decision",
            "",
            f"- Blockers: {', '.join(blockers) if blockers else 'none'}",
            "- GNSS speed does not generate walking or vehicle ground truth.",
            f"- Next: {report.get('next_step')}",
            "",
        ]
    )


def write_report(report: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / REPORT_JSON
    markdown_path = output_dir / REPORT_MARKDOWN
    payload = dict(report)
    payload["report_path"] = relative_ref(json_path)
    payload["markdown_report_path"] = relative_ref(markdown_path)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(payload), encoding="utf-8")
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input-export", type=Path)
    source.add_argument("--hub")
    parser.add_argument("--device-id")
    parser.add_argument("--started-at")
    parser.add_argument("--ended-at")
    parser.add_argument("--token-file", type=Path, default=pipeline.DEFAULT_TOKEN_FILE)
    parser.add_argument("--max-records", type=int, default=10000)
    parser.add_argument("--request-timeout-sec", type=float, default=180.0)
    parser.add_argument("--run-id", default="motion-data-readiness")
    parser.add_argument("--created-at")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def load_export(args: argparse.Namespace) -> Mapping[str, Any]:
    if args.input_export:
        try:
            payload = json.loads(args.input_export.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MotionDataReadinessError(f"cannot read input export: {type(exc).__name__}") from exc
        if not isinstance(payload, dict):
            raise MotionDataReadinessError("input export must be a JSON object")
        return payload
    if not args.device_id or not args.started_at or not args.ended_at:
        raise MotionDataReadinessError("--hub requires --device-id, --started-at, and --ended-at")
    return pipeline.fetch_device_window_export(
        hub_url=args.hub,
        device_id=args.device_id,
        started_at=args.started_at,
        ended_at=args.ended_at,
        max_records=args.max_records,
        token=pipeline.read_token(args.token_file),
        timeout_sec=args.request_timeout_sec,
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        export = load_export(args)
        report = build_report(
            export,
            run_id=args.run_id,
            created_at=args.created_at or datetime.now(timezone.utc).isoformat(),
        )
        written = write_report(report, args.output_dir or DEFAULT_OUTPUT_ROOT / args.run_id)
    except (MotionDataReadinessError, pipeline.LocationD2D5PipelineError) as exc:
        print(f"FAIL motion data readiness: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(written, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"{written['status']} motion data readiness report={written['markdown_report_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

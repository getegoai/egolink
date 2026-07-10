from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

from pc_simulator.imu_quality import load_jsonl


REPORT_SCHEMA_VERSION = "egolink.imu_pose_quality_report.v0.1"
AXES = ("x", "y", "z")


def _stats(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "min": None, "max": None, "mean": None, "stddev": None}
    return {
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "mean": mean(values),
        "stddev": pstdev(values) if len(values) > 1 else 0.0,
    }


def _gate(passed: bool, reason: str, **details: Any) -> dict[str, Any]:
    return {"passed": passed, "reason": reason, "details": details}


def _format_float(value: Any) -> str:
    return f"{float(value):.1f}" if isinstance(value, (int, float)) else "n/a"


def _parse_pose_label(label: str) -> dict[str, str] | None:
    normalized = label.strip().lower().replace("-", "_").replace("+", "_positive")
    normalized = normalized.replace("__", "_")
    aliases = {
        "x_pos": "x_positive",
        "x_positive": "x_positive",
        "x_neg": "x_negative",
        "x_negative": "x_negative",
        "y_pos": "y_positive",
        "y_positive": "y_positive",
        "y_neg": "y_negative",
        "y_negative": "y_negative",
        "z_pos": "z_positive",
        "z_positive": "z_positive",
        "z_neg": "z_negative",
        "z_negative": "z_negative",
    }
    canonical = aliases.get(normalized)
    if not canonical:
        return None
    axis, sign = canonical.split("_", 1)
    return {"axis": axis, "sign": sign}


def _dominant_axis(mean_axes_mg: list[float]) -> dict[str, Any]:
    dominant_index = max(range(3), key=lambda index: abs(mean_axes_mg[index]))
    value = mean_axes_mg[dominant_index]
    return {
        "axis": AXES[dominant_index],
        "sign": "positive" if value >= 0 else "negative",
        "mean_mg": value,
    }


def _ideal_vector(expected_pose: dict[str, str] | None) -> list[float] | None:
    if not expected_pose:
        return None
    vector = [0.0, 0.0, 0.0]
    axis_index = AXES.index(expected_pose["axis"])
    vector[axis_index] = 1000.0 if expected_pose["sign"] == "positive" else -1000.0
    return vector


def _extract_samples(messages: list[dict[str, Any]], warmup_discard: int) -> list[dict[str, Any]]:
    sample_events = [message for message in messages if message.get("type") == "imu_sample"]
    samples: list[dict[str, Any]] = []
    for event in sample_events[warmup_discard:]:
        payload = event.get("payload", {})
        accel = payload.get("accel_mg")
        gyro = payload.get("gyro_mdps")
        if isinstance(accel, list) and len(accel) == 3 and isinstance(gyro, list) and len(gyro) == 3:
            samples.append(
                {
                    "seq": event.get("seq"),
                    "device_monotonic_ms": event.get("device_monotonic_ms"),
                    "accel_mg": [float(value) for value in accel],
                    "gyro_mdps": [float(value) for value in gyro],
                    "source_availability": event.get("source_availability"),
                    "source_status": event.get("source_status"),
                }
            )
    return samples


def _source_values(messages_by_name: dict[str, list[dict[str, Any]]]) -> tuple[set[Any], set[Any]]:
    availability: set[Any] = set()
    status: set[Any] = set()
    for messages in messages_by_name.values():
        for event in messages:
            if event.get("type") == "imu_sample":
                availability.add(event.get("source_availability"))
                status.add(event.get("source_status"))
    return availability, status


def _analyze_pose(label: str, messages: list[dict[str, Any]], warmup_discard: int) -> dict[str, Any]:
    samples = _extract_samples(messages, warmup_discard)
    accel_vectors = [sample["accel_mg"] for sample in samples]
    gyro_vectors = [sample["gyro_mdps"] for sample in samples]
    mean_axes_mg = [
        mean([vector[index] for vector in accel_vectors]) if accel_vectors else 0.0
        for index in range(3)
    ]
    axis_stddev_mg = [
        pstdev([vector[index] for vector in accel_vectors]) if len(accel_vectors) > 1 else 0.0
        for index in range(3)
    ]
    accel_magnitudes = [
        math.sqrt(vector[0] * vector[0] + vector[1] * vector[1] + vector[2] * vector[2])
        for vector in accel_vectors
    ]
    gyro_abs_values = [abs(component) for vector in gyro_vectors for component in vector]
    dominant = _dominant_axis(mean_axes_mg)
    expected = _parse_pose_label(label)
    ideal = _ideal_vector(expected)
    offset = (
        [mean_axes_mg[index] - ideal[index] for index in range(3)]
        if ideal is not None
        else None
    )
    non_dominant_abs = [
        abs(value)
        for index, value in enumerate(mean_axes_mg)
        if AXES[index] != dominant["axis"]
    ]
    accel_mean_magnitude = mean(accel_magnitudes) if accel_magnitudes else None
    gyro_abs_mean = mean(gyro_abs_values) if gyro_abs_values else None
    static_passed = bool(
        accel_mean_magnitude is not None
        and 850.0 <= accel_mean_magnitude <= 1150.0
        and abs(float(dominant["mean_mg"])) >= 700.0
        and all(value <= 250.0 for value in non_dominant_abs)
        and max(axis_stddev_mg or [0.0]) <= 80.0
        and gyro_abs_mean is not None
        and gyro_abs_mean <= 5000.0
    )
    label_match = bool(
        expected is not None
        and dominant["axis"] == expected["axis"]
        and dominant["sign"] == expected["sign"]
    )
    calibration_offset_passed = bool(
        offset is not None
        and all(abs(value) <= 250.0 for value in offset)
        and abs(offset[AXES.index(expected["axis"])]) <= 200.0
    ) if expected else False

    return {
        "label": label,
        "expected_pose": expected,
        "sample_count": len(samples),
        "mean_axes_mg": mean_axes_mg,
        "axis_stddev_mg": axis_stddev_mg,
        "dominant_axis": dominant,
        "accel_magnitude_mg": _stats(accel_magnitudes),
        "gyro_abs_mdps": _stats(gyro_abs_values),
        "calibration_offset_mg": offset,
        "static_passed": static_passed,
        "label_match": label_match,
        "calibration_offset_passed": calibration_offset_passed,
    }


def _analyze_motion(messages: list[dict[str, Any]], warmup_discard: int) -> dict[str, Any]:
    samples = _extract_samples(messages, warmup_discard)
    accel_vectors = [sample["accel_mg"] for sample in samples]
    gyro_vectors = [sample["gyro_mdps"] for sample in samples]
    accel_magnitudes = [
        math.sqrt(vector[0] * vector[0] + vector[1] * vector[1] + vector[2] * vector[2])
        for vector in accel_vectors
    ]
    gyro_abs_values = [abs(component) for vector in gyro_vectors for component in vector]
    accel_range = max(accel_magnitudes) - min(accel_magnitudes) if accel_magnitudes else 0.0
    gyro_peak = max(gyro_abs_values) if gyro_abs_values else 0.0
    motion_passed = bool(len(samples) >= 20 and (accel_range >= 250.0 or gyro_peak >= 20000.0))
    return {
        "sample_count": len(samples),
        "accel_magnitude_mg": _stats(accel_magnitudes),
        "gyro_abs_mdps": _stats(gyro_abs_values),
        "accel_magnitude_range_mg": accel_range,
        "gyro_peak_mdps": gyro_peak,
        "motion_passed": motion_passed,
    }


def analyze_pose_quality(
    pose_messages: dict[str, list[dict[str, Any]]],
    *,
    motion_messages: list[dict[str, Any]] | None = None,
    min_static_poses: int = 3,
    min_samples_per_pose: int = 40,
    warmup_discard: int = 5,
) -> dict[str, Any]:
    pose_reports = {
        label: _analyze_pose(label, messages, warmup_discard)
        for label, messages in pose_messages.items()
    }
    expected_pose_keys = {
        f"{report['expected_pose']['axis']}_{report['expected_pose']['sign']}"
        for report in pose_reports.values()
        if report["expected_pose"] is not None
    }
    static_pose_reports = [
        report
        for report in pose_reports.values()
        if report["static_passed"] and report["sample_count"] >= min_samples_per_pose
    ]
    source_availability, source_status = _source_values(pose_messages)
    if motion_messages is not None:
        motion_availability, motion_status = _source_values({"motion": motion_messages})
        source_availability.update(motion_availability)
        source_status.update(motion_status)
    motion_report = _analyze_motion(motion_messages, warmup_discard) if motion_messages is not None else None

    pose_count_passed = len(static_pose_reports) >= min_static_poses
    axis_coverage_passed = len(expected_pose_keys) >= min_static_poses
    pose_label_match_passed = bool(pose_reports) and all(report["label_match"] for report in pose_reports.values())
    calibration_passed = bool(pose_reports) and all(
        report["calibration_offset_passed"] for report in pose_reports.values()
    )
    motion_passed = bool(motion_report and motion_report["motion_passed"])
    source_boundary_passed = source_availability == {"bridge_uplink"} and source_status == {"unverified"}
    pose_or_motion_passed = bool((pose_count_passed and axis_coverage_passed) or motion_passed)

    gates = {
        "pose_static_quality": _gate(
            bool(pose_reports) and all(report["static_passed"] for report in pose_reports.values()),
            "each supplied static pose is stable and plausibly near 1g",
        ),
        "pose_count": _gate(
            pose_count_passed,
            "at least the requested number of static pose windows passed",
            min_static_poses=min_static_poses,
            passed_static_poses=len(static_pose_reports),
        ),
        "axis_coverage": _gate(
            axis_coverage_passed,
            "static pose labels cover enough distinct axis/sign orientations",
            expected_pose_keys=sorted(expected_pose_keys),
            min_static_poses=min_static_poses,
        ),
        "pose_label_match": _gate(
            pose_label_match_passed,
            "dominant measured axis/sign matches each pose label",
        ),
        "calibration_offset": _gate(
            calibration_passed,
            "pose mean vectors stay within conservative offset bounds",
        ),
        "motion_sanity": _gate(
            motion_passed,
            "optional rotation/tap window shows measurable movement",
            motion_report=motion_report,
        ),
        "pose_or_motion_evidence": _gate(
            pose_or_motion_passed,
            "TIMU-004 has either multi-pose coverage or a motion sanity window",
        ),
        "source_boundary": _gate(
            source_boundary_passed,
            "source remains bridge_uplink/unverified until formal acceptance",
            source_availability_values=sorted(str(value) for value in source_availability),
            source_status_values=sorted(str(value) for value in source_status),
        ),
    }

    blocking_gate_names = set(gates) - {"motion_sanity"}
    gate_failures = [
        name
        for name, gate in gates.items()
        if name in blocking_gate_names and not gate["passed"]
    ]
    reasons = ["source_status_unverified"]
    if "pose_or_motion_evidence" in gate_failures:
        reasons.append("multi_pose_or_motion_evidence_missing")
    if "pose_count" in gate_failures:
        reasons.append("multi_pose_coverage_incomplete")
    if "axis_coverage" in gate_failures:
        reasons.append("axis_sign_coverage_incomplete")
    if not motion_passed and motion_messages is None and not (pose_count_passed and axis_coverage_passed):
        reasons.append("motion_window_missing")
    if gate_failures:
        reasons.append("quality_gates_not_all_passed")

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "pose_count": len(pose_reports),
        "pose_reports": pose_reports,
        "motion_report": motion_report,
        "gates": gates,
        "quality_gates_passed": not gate_failures,
        "formal_imu_acceptance": False,
        "formal_imu_acceptance_reasons": reasons,
    }


def format_pose_markdown(
    report: dict[str, Any],
    pose_sources: dict[str, Path],
    motion_source: Path | None = None,
    title: str = "# TIMU-004 QMI8658 Pose Quality Report",
) -> str:
    pose_rows = []
    for label, pose in report["pose_reports"].items():
        expected = pose["expected_pose"] or {"axis": "unknown", "sign": "unknown"}
        dominant = pose["dominant_axis"]
        offset = pose["calibration_offset_mg"]
        offset_text = (
            f"[{offset[0]:.1f}, {offset[1]:.1f}, {offset[2]:.1f}]"
            if offset is not None
            else "not_available"
        )
        pose_rows.append(
            "| "
            f"`{label}` | `{expected['axis']}` `{expected['sign']}` | "
            f"`{dominant['axis']}` `{dominant['sign']}` | "
            f"{pose['sample_count']} | {_format_float(pose['accel_magnitude_mg']['mean'])} | "
            f"{_format_float(pose['gyro_abs_mdps']['mean'])} | `{offset_text}` | "
            f"{'PASS' if pose['static_passed'] and pose['label_match'] else 'FAIL'} |"
        )

    gate_rows = [
        f"| `{name}` | {'PASS' if gate['passed'] else 'FAIL'} | {gate['reason']} |"
        for name, gate in report["gates"].items()
    ]

    source_lines = [f"- Pose `{label}`: `{path}`" for label, path in pose_sources.items()]
    if motion_source is not None:
        source_lines.append(f"- Motion: `{motion_source}`")
    if not source_lines:
        source_lines.append("- Source: not recorded")

    motion = report["motion_report"]
    motion_lines = [
        "## Motion Window",
        "",
    ]
    if motion is None:
        motion_lines.extend(["- Motion source: not supplied", "- Motion sanity: `False`"])
    else:
        motion_lines.extend(
            [
                f"- Motion samples: `{motion['sample_count']}`",
                f"- Accel magnitude range: `{motion['accel_magnitude_range_mg']}` mg",
                f"- Gyro peak: `{motion['gyro_peak_mdps']}` mdps",
                f"- Motion sanity: `{motion['motion_passed']}`",
            ]
        )

    lines = [
        title,
        "",
        *source_lines,
        f"- Pose windows: `{report['pose_count']}`",
        f"- Quality gates passed: `{report['quality_gates_passed']}`",
        f"- Formal IMU acceptance: `{report['formal_imu_acceptance']}`",
        f"- Formal acceptance reasons: `{', '.join(report['formal_imu_acceptance_reasons'])}`",
        "",
        "## Pose Windows",
        "",
        "| Pose | Expected | Measured | Samples | Mean | Gyro abs mean | Calibration offset mg | Result |",
        "|---|---|---|---:|---:|---:|---|---:|",
        *pose_rows,
        "",
        *motion_lines,
        "",
        "## Gates",
        "",
        "| Gate | Result | Meaning |",
        "|---|---:|---|",
        *gate_rows,
        "",
        "## Boundary",
        "",
        "This is a TIMU-004 pose/motion evidence gate, not product IMU acceptance.",
        "Formal acceptance stays false while the source is `bridge_uplink/unverified`",
        "and until mounting direction, calibration, FIFO/interrupt behavior, power",
        "behavior, and a real `platform_imu` backend pass separate hardware gates.",
        "",
    ]
    return "\n".join(lines)


def _parse_source(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("source must use LABEL=PATH")
    label, path = value.split("=", 1)
    if not label:
        raise argparse.ArgumentTypeError("source label must not be empty")
    return label, Path(path)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze QMI8658 pose and motion evidence.")
    parser.add_argument("--pose", action="append", type=_parse_source, default=[])
    parser.add_argument("--motion", type=Path, default=None)
    parser.add_argument("--json", action="store_true", help="Print the report as JSON.")
    parser.add_argument("--markdown", type=Path, default=None, help="Write a Markdown report.")
    parser.add_argument("--title", default="# TIMU-004 QMI8658 Pose Quality Report")
    parser.add_argument("--min-static-poses", type=int, default=3)
    parser.add_argument("--min-samples-per-pose", type=int, default=40)
    parser.add_argument("--warmup-discard", type=int, default=5)
    parser.add_argument("--fail-on-unusable", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    pose_sources = dict(args.pose)
    pose_messages = {label: load_jsonl(path) for label, path in pose_sources.items()}
    motion_messages = load_jsonl(args.motion) if args.motion else None
    report = analyze_pose_quality(
        pose_messages,
        motion_messages=motion_messages,
        min_static_poses=args.min_static_poses,
        min_samples_per_pose=args.min_samples_per_pose,
        warmup_discard=args.warmup_discard,
    )

    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(
            format_pose_markdown(report, pose_sources, args.motion, args.title),
            encoding="utf-8",
        )

    if args.json or not args.markdown:
        print(json.dumps(report, ensure_ascii=False, indent=2))

    if args.fail_on_unusable and not report["quality_gates_passed"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

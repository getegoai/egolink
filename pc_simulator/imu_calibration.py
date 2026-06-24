from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import mean
from typing import Any


PROFILE_SCHEMA_VERSION = "egolink.imu_calibration_profile.v0.1"
ENGINEERING_STAGE = "engineering"

RECALIBRATION_TRIGGERS = [
    "pcb_revision_change",
    "imu_part_or_lot_change",
    "imu_mounting_position_change",
    "enclosure_or_wearable_mechanics_change",
    "adhesive_or_fastener_change",
    "axis_orientation_change",
    "odr_filter_fifo_or_interrupt_policy_change",
    "power_rail_or_regulator_change",
    "firmware_backend_or_conversion_change",
    "production_fixture_change",
]

PRODUCTION_BLOCKERS = [
    "final_mounting_direction_not_frozen",
    "production_fixture_not_defined",
    "six_face_or_equivalent_accel_calibration_not_complete",
    "signed_gyro_bias_capture_not_complete",
    "temperature_drift_not_characterized",
    "fifo_drdy_interrupt_not_validated",
    "power_current_waveform_not_validated",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object")
    return value


def _float_list(values: Any, *, length: int, name: str) -> list[float]:
    if not isinstance(values, list) or len(values) != length:
        raise ValueError(f"{name} must be a {length}-element list")
    return [float(value) for value in values]


def _axis_map_from_pose_reports(pose_reports: dict[str, Any]) -> dict[str, Any]:
    axis_map: dict[str, Any] = {}
    for label, raw_report in pose_reports.items():
        report = _require_mapping(raw_report, f"pose_reports.{label}")
        expected = report.get("expected_pose")
        dominant = report.get("dominant_axis")
        if not isinstance(expected, dict) or not isinstance(dominant, dict):
            continue
        expected_axis = expected.get("axis")
        dominant_axis = dominant.get("axis")
        if expected_axis not in ("x", "y", "z") or dominant_axis not in ("x", "y", "z"):
            continue
        expected_sign = expected.get("sign")
        dominant_sign = dominant.get("sign")
        axis_map[str(expected_axis)] = {
            "measured_axis": str(dominant_axis),
            "sign": 1 if expected_sign == dominant_sign else -1,
            "pose_label": label,
        }
    return axis_map


def _offset_estimate_from_pose_reports(pose_reports: dict[str, Any]) -> dict[str, Any]:
    offsets: list[list[float]] = []
    per_pose: dict[str, list[float]] = {}
    for label, raw_report in pose_reports.items():
        report = _require_mapping(raw_report, f"pose_reports.{label}")
        raw_offset = report.get("calibration_offset_mg")
        if raw_offset is None:
            continue
        offset = _float_list(raw_offset, length=3, name=f"pose_reports.{label}.calibration_offset_mg")
        offsets.append(offset)
        per_pose[label] = offset

    mean_offset = [mean([offset[index] for offset in offsets]) for index in range(3)] if offsets else None
    max_abs_offset = max((abs(value) for offset in offsets for value in offset), default=None)
    return {
        "method": "mean_of_pose_mean_minus_ideal_vectors",
        "basis": "engineering_static_pose_quality_report",
        "offset_mg_xyz": mean_offset,
        "max_abs_pose_offset_mg": max_abs_offset,
        "per_pose_offset_mg": per_pose,
        "scale_matrix": None,
        "scale_matrix_status": "not_estimated_requires_six_face_or_fixture_calibration",
    }


def _static_quality_summary(pose_reports: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for label, raw_report in pose_reports.items():
        report = _require_mapping(raw_report, f"pose_reports.{label}")
        summary[label] = {
            "sample_count": int(report.get("sample_count", 0)),
            "mean_axes_mg": _float_list(report.get("mean_axes_mg", [0, 0, 0]), length=3, name="mean_axes_mg"),
            "axis_stddev_mg": _float_list(
                report.get("axis_stddev_mg", [0, 0, 0]),
                length=3,
                name="axis_stddev_mg",
            ),
            "static_passed": bool(report.get("static_passed")),
            "label_match": bool(report.get("label_match")),
            "calibration_offset_passed": bool(report.get("calibration_offset_passed")),
            "gyro_abs_mean_mdps": (
                report.get("gyro_abs_mdps", {}).get("mean")
                if isinstance(report.get("gyro_abs_mdps"), dict)
                else None
            ),
        }
    return summary


def build_engineering_calibration_profile(
    pose_quality_report: dict[str, Any],
    *,
    profile_id: str,
    hardware_profile: str,
    source_report: str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    report = _require_mapping(pose_quality_report, "pose_quality_report")
    pose_reports = _require_mapping(report.get("pose_reports"), "pose_quality_report.pose_reports")
    gates = _require_mapping(report.get("gates"), "pose_quality_report.gates")
    source_gate = _require_mapping(gates.get("source_boundary"), "pose_quality_report.gates.source_boundary")

    quality_gates_passed = bool(report.get("quality_gates_passed"))
    source_boundary_passed = bool(source_gate.get("passed"))
    usable_for_engineering = bool(quality_gates_passed and source_boundary_passed)

    return {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "profile_id": profile_id,
        "stage": ENGINEERING_STAGE,
        "generated_at": generated_at or utc_now(),
        "hardware_profile": hardware_profile,
        "source_report": source_report,
        "source_report_schema_version": report.get("schema_version"),
        "usable_for_engineering": usable_for_engineering,
        "production_ready": False,
        "formal_imu_acceptance": False,
        "recalibration_required_after": RECALIBRATION_TRIGGERS,
        "production_blockers": PRODUCTION_BLOCKERS,
        "axis_map": _axis_map_from_pose_reports(pose_reports),
        "accel_calibration": _offset_estimate_from_pose_reports(pose_reports),
        "gyro_calibration": {
            "bias_mdps_xyz": None,
            "status": "not_estimated_requires_signed_static_gyro_capture",
        },
        "quality_summary": {
            "pose_count": int(report.get("pose_count", 0)),
            "quality_gates_passed": quality_gates_passed,
            "source_boundary_passed": source_boundary_passed,
            "formal_imu_acceptance_reasons": report.get("formal_imu_acceptance_reasons", []),
            "static_poses": _static_quality_summary(pose_reports),
        },
        "boundary": {
            "can_use_for": [
                "engineering_axis_sanity",
                "temporary_mounting_experiments",
                "backend_regression_checks",
            ],
            "must_not_use_for": [
                "production_calibration",
                "motionnet_training",
                "fall_or_impact_product_claims",
                "battery_life_or_power_claims",
            ],
            "notes": (
                "This profile captures an engineering calibration estimate. "
                "It must be regenerated after hardware, mounting, enclosure, "
                "firmware sampling, FIFO/interrupt, or power-path changes."
            ),
        },
    }


def format_calibration_markdown(profile: dict[str, Any], title: str = "# TIMU-009A IMU Engineering Calibration Profile") -> str:
    accel = profile["accel_calibration"]
    offset = accel["offset_mg_xyz"]
    offset_text = (
        f"[{offset[0]:.1f}, {offset[1]:.1f}, {offset[2]:.1f}]"
        if isinstance(offset, list)
        else "not_available"
    )
    axis_rows = [
        f"| `{axis}` | `{entry['measured_axis']}` | `{entry['sign']}` | `{entry['pose_label']}` |"
        for axis, entry in sorted(profile["axis_map"].items())
    ]
    if not axis_rows:
        axis_rows = ["| n/a | n/a | n/a | n/a |"]

    pose_rows = []
    for label, pose in profile["quality_summary"]["static_poses"].items():
        mean_axes = pose["mean_axes_mg"]
        pose_rows.append(
            "| "
            f"`{label}` | {pose['sample_count']} | "
            f"[{mean_axes[0]:.1f}, {mean_axes[1]:.1f}, {mean_axes[2]:.1f}] | "
            f"`{pose['static_passed']}` | `{pose['label_match']}` | "
            f"`{pose['calibration_offset_passed']}` |"
        )
    if not pose_rows:
        pose_rows = ["| n/a | 0 | n/a | `False` | `False` | `False` |"]

    return "\n".join(
        [
            title,
            "",
            f"- Profile id: `{profile['profile_id']}`",
            f"- Stage: `{profile['stage']}`",
            f"- Hardware profile: `{profile['hardware_profile']}`",
            f"- Source report: `{profile['source_report']}`",
            f"- Usable for engineering: `{profile['usable_for_engineering']}`",
            f"- Production ready: `{profile['production_ready']}`",
            f"- Formal IMU acceptance: `{profile['formal_imu_acceptance']}`",
            f"- Estimated accel offset mg xyz: `{offset_text}`",
            f"- Gyro calibration: `{profile['gyro_calibration']['status']}`",
            "",
            "## Axis Map",
            "",
            "| Expected axis | Measured axis | Sign | Pose source |",
            "|---|---|---:|---|",
            *axis_rows,
            "",
            "## Static Pose Quality",
            "",
            "| Pose | Samples | Mean axes mg | Static | Label | Offset |",
            "|---|---:|---|---:|---:|---:|",
            *pose_rows,
            "",
            "## Recalibration Triggers",
            "",
            *[f"- `{trigger}`" for trigger in profile["recalibration_required_after"]],
            "",
            "## Production Blockers",
            "",
            *[f"- `{blocker}`" for blocker in profile["production_blockers"]],
            "",
            "## Boundary",
            "",
            profile["boundary"]["notes"],
            "",
            "This profile is for engineering bring-up only. It must be regenerated",
            "after the hardware and mechanical stack are frozen, and it is not valid",
            "as production calibration or model-training evidence.",
            "",
        ]
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate an engineering IMU calibration profile.")
    parser.add_argument("--pose-quality-json", type=Path, default=None)
    parser.add_argument(
        "--pose",
        action="append",
        default=[],
        help="Raw pose source as LABEL=PATH. May be repeated instead of --pose-quality-json.",
    )
    parser.add_argument("--min-static-poses", type=int, default=3)
    parser.add_argument("--min-samples-per-pose", type=int, default=40)
    parser.add_argument("--warmup-discard", type=int, default=5)
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--hardware-profile", required=True)
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument("--markdown", type=Path, default=None)
    parser.add_argument("--title", default="# TIMU-009A IMU Engineering Calibration Profile")
    parser.add_argument("--json", action="store_true", help="Print the profile as JSON.")
    return parser.parse_args(argv)


def _parse_pose_arg(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise ValueError("--pose must use LABEL=PATH")
    label, path = value.split("=", 1)
    if not label:
        raise ValueError("--pose label must not be empty")
    return label, Path(path)


def _load_or_analyze_pose_quality(args: argparse.Namespace) -> tuple[dict[str, Any], str]:
    if args.pose_quality_json is not None:
        return (
            json.loads(args.pose_quality_json.read_text(encoding="utf-8-sig")),
            str(args.pose_quality_json),
        )
    if not args.pose:
        raise ValueError("either --pose-quality-json or at least one --pose LABEL=PATH is required")

    from pc_simulator.imu_pose_quality import analyze_pose_quality
    from pc_simulator.imu_quality import load_jsonl

    pose_sources = dict(_parse_pose_arg(value) for value in args.pose)
    pose_messages = {label: load_jsonl(path) for label, path in pose_sources.items()}
    return (
        analyze_pose_quality(
            pose_messages,
            min_static_poses=args.min_static_poses,
            min_samples_per_pose=args.min_samples_per_pose,
            warmup_discard=args.warmup_discard,
        ),
        ";".join(f"{label}={path}" for label, path in pose_sources.items()),
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report, source_report = _load_or_analyze_pose_quality(args)
    profile = build_engineering_calibration_profile(
        report,
        profile_id=args.profile_id,
        hardware_profile=args.hardware_profile,
        source_report=source_report,
    )

    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(format_calibration_markdown(profile, args.title), encoding="utf-8")
    if args.json or not (args.output_json or args.markdown):
        print(json.dumps(profile, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

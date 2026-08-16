"""Compare two A0-001 calibration artifacts from independent six-face runs.

`repeatability_not_yet_established` is the largest gap left by a single calibration
run: one run is internally self-consistent by construction, which says nothing about
what a second run would produce. This tool reports the per-axis deltas between two
runs so that question becomes measurable.

It deliberately does not claim repeatability is characterized. Two runs yield one
delta, not a distribution; the declared bounds here are proposed engineering
observation limits, not a validated specification.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pc_simulator.imu_six_face_calibration import (
    ARTIFACT_SCHEMA_VERSION,
    AXES,
    ImuCalibrationError,
    stable_json_bytes,
)

COMPARISON_SCHEMA_VERSION = "egolink.imu_calibration_repeatability.v0.1"

# Proposed engineering observation bounds, not a validated specification. They exist so
# an obviously divergent second run is visible rather than silently averaged away.
PROPOSED_MAX_ACCEL_BIAS_DELTA_MG = 50.0
PROPOSED_MAX_SENSITIVITY_DELTA_MG_PER_G = 20.0
PROPOSED_MAX_GYRO_BIAS_DELTA_MDPS = 500.0

# Two runs give a single delta. A spread needs more, so nothing here may be presented
# as a characterized repeatability result.
MIN_RUNS_FOR_CHARACTERIZATION = 3


class CalibrationComparisonError(ValueError):
    """Raised when two artifacts cannot be honestly compared."""


def load_artifact(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CalibrationComparisonError(f"cannot read calibration artifact {path}: {error}") from error
    if not isinstance(payload, dict):
        raise CalibrationComparisonError(f"{path} is not a calibration artifact object")
    if payload.get("schema_version") != ARTIFACT_SCHEMA_VERSION:
        raise CalibrationComparisonError(f"{path} is not an {ARTIFACT_SCHEMA_VERSION} artifact")
    return payload


def _require_same(baseline: dict[str, Any], repeat: dict[str, Any], path: tuple[str, ...]) -> Any:
    left: Any = baseline
    right: Any = repeat
    for key in path:
        left = left.get(key) if isinstance(left, dict) else None
        right = right.get(key) if isinstance(right, dict) else None
    if left != right or left is None:
        label = ".".join(path)
        raise CalibrationComparisonError(
            f"{label} differs between the two runs ({left!r} vs {right!r}); "
            "this is not a repeatability comparison of the same configuration"
        )
    return left


def compare_calibrations(baseline: dict[str, Any], repeat: dict[str, Any]) -> dict[str, Any]:
    if baseline.get("calibration_id") == repeat.get("calibration_id"):
        raise CalibrationComparisonError(
            "both inputs are the same calibration; a repeatability comparison needs two independent runs"
        )

    device_id = _require_same(baseline, repeat, ("device", "device_id"))
    imu_model = _require_same(baseline, repeat, ("sensor", "imu_model"))
    _require_same(baseline, repeat, ("sensor", "sensor_i2c_address"))
    # Re-mounting changes the sensor-to-body relationship, so runs across different
    # mountings measure different things and must not be presented as repeatability.
    mounting = _require_same(baseline, repeat, ("mounting", "mounting_profile_id"))

    baseline_windows = {w["window_id"] for w in baseline.get("source_windows", [])}
    repeat_windows = {w["window_id"] for w in repeat.get("source_windows", [])}
    shared = sorted(baseline_windows & repeat_windows)
    if shared:
        raise CalibrationComparisonError(
            f"the two runs share source windows {shared}; independent captures are required"
        )

    def axis_deltas(section: str, field: str) -> list[dict[str, Any]]:
        left = baseline[section][field]
        right = repeat[section][field]
        return [
            {
                "axis": AXES[i],
                "baseline": left[i],
                "repeat": right[i],
                "delta": round(right[i] - left[i], 9),
                "abs_delta": round(abs(right[i] - left[i]), 9),
            }
            for i in range(3)
        ]

    accel_bias = axis_deltas("accelerometer", "bias_mg_xyz")
    sensitivity = axis_deltas("accelerometer", "sensitivity_mg_per_g_xyz")
    gyro_bias = axis_deltas("gyroscope", "bias_mdps_xyz")

    for entry, reference in zip(sensitivity, baseline["accelerometer"]["sensitivity_mg_per_g_xyz"]):
        entry["relative_delta_percent"] = round(entry["delta"] / reference * 100.0, 6) if reference else None

    checks = {
        "accel_bias_within_proposed_bound": max(e["abs_delta"] for e in accel_bias)
        <= PROPOSED_MAX_ACCEL_BIAS_DELTA_MG,
        "sensitivity_within_proposed_bound": max(e["abs_delta"] for e in sensitivity)
        <= PROPOSED_MAX_SENSITIVITY_DELTA_MG_PER_G,
        "gyro_bias_within_proposed_bound": max(e["abs_delta"] for e in gyro_bias)
        <= PROPOSED_MAX_GYRO_BIAS_DELTA_MDPS,
    }

    return {
        "schema_version": COMPARISON_SCHEMA_VERSION,
        "runs_compared": 2,
        "repeatability_characterized": False,
        "characterization_requires_runs": MIN_RUNS_FOR_CHARACTERIZATION,
        "device_id": device_id,
        "imu_model": imu_model,
        "mounting_profile_id": mounting,
        "baseline": {
            "calibration_id": baseline["calibration_id"],
            "calibration_run_id": baseline["calibration_run_id"],
            "calibration_time_utc": baseline["calibration_time_utc"],
            "payload_sha256": baseline["payload_sha256"],
        },
        "repeat": {
            "calibration_id": repeat["calibration_id"],
            "calibration_run_id": repeat["calibration_run_id"],
            "calibration_time_utc": repeat["calibration_time_utc"],
            "payload_sha256": repeat["payload_sha256"],
        },
        "firmware_identical": baseline["firmware"] == repeat["firmware"],
        "accel_bias_mg": accel_bias,
        "accel_sensitivity_mg_per_g": sensitivity,
        "gyro_bias_mdps": gyro_bias,
        "proposed_bounds": {
            "max_accel_bias_delta_mg": PROPOSED_MAX_ACCEL_BIAS_DELTA_MG,
            "max_sensitivity_delta_mg_per_g": PROPOSED_MAX_SENSITIVITY_DELTA_MG_PER_G,
            "max_gyro_bias_delta_mdps": PROPOSED_MAX_GYRO_BIAS_DELTA_MDPS,
            "status": "proposed_engineering_observation_bounds_not_validated",
        },
        "checks": checks,
        "within_all_proposed_bounds": all(checks.values()),
        "limitations": [
            "two_runs_give_one_delta_not_a_distribution",
            "bounds_are_proposed_not_validated",
            "same_mounting_and_device_only",
            "temperature_not_controlled_or_recorded",
            "does_not_establish_accuracy",
        ],
    }


def format_report(comparison: dict[str, Any]) -> str:
    def rows(entries: list[dict[str, Any]], unit: str) -> list[str]:
        out = []
        for e in entries:
            extra = ""
            if e.get("relative_delta_percent") is not None:
                extra = f" | {e['relative_delta_percent']:+.4f} %"
            out.append(
                f"| `{e['axis']}` | {e['baseline']} | {e['repeat']} | {e['delta']:+} {unit}{extra} |"
            )
        return out

    lines = [
        "# A0-001 IMU Calibration Repeatability Comparison",
        "",
        f"- Device: `{comparison['device_id']}`",
        f"- Sensor: `{comparison['imu_model']}`",
        f"- Mounting profile: `{comparison['mounting_profile_id']}`",
        f"- Baseline: `{comparison['baseline']['calibration_id']}` ({comparison['baseline']['calibration_time_utc']})",
        f"- Repeat:   `{comparison['repeat']['calibration_id']}` ({comparison['repeat']['calibration_time_utc']})",
        f"- Firmware identical: `{comparison['firmware_identical']}`",
        f"- Within all proposed bounds: `{comparison['within_all_proposed_bounds']}`",
        "",
        "## Accelerometer bias (mg)",
        "",
        "| Axis | Baseline | Repeat | Delta |",
        "|---|---|---|---|",
        *rows(comparison["accel_bias_mg"], "mg"),
        "",
        "## Accelerometer sensitivity (mg/g)",
        "",
        "| Axis | Baseline | Repeat | Delta |",
        "|---|---|---|---|",
        *rows(comparison["accel_sensitivity_mg_per_g"], "mg/g"),
        "",
        "## Gyroscope bias (mdps)",
        "",
        "| Axis | Baseline | Repeat | Delta |",
        "|---|---|---|---|",
        *rows(comparison["gyro_bias_mdps"], "mdps"),
        "",
        "## What this does and does not show",
        "",
        "This is a delta between two independent runs on the same device and mounting.",
        "Two runs produce one difference, not a spread, so repeatability is **not**",
        f"characterized here; that needs at least {comparison['characterization_requires_runs']} runs.",
        "The bounds are proposed engineering observation limits chosen so an obviously",
        "divergent second run is visible. They are not a validated specification, and",
        "staying inside them is not an accuracy result.",
        "",
        "## Limitations",
        "",
        *[f"- `{item}`" for item in comparison["limitations"]],
        "",
    ]
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--repeat", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        comparison = compare_calibrations(load_artifact(args.baseline), load_artifact(args.repeat))
        output_dir = args.output_dir.resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        summary_path = output_dir / "imu_calibration_repeatability.json"
        report_path = output_dir / "imu_calibration_repeatability.md"
        summary_path.write_bytes(stable_json_bytes(comparison) + b"\n")
        report_path.write_text(format_report(comparison), encoding="utf-8")
    except (OSError, CalibrationComparisonError, ImuCalibrationError, KeyError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 1

    result = {
        "ok": True,
        "within_all_proposed_bounds": comparison["within_all_proposed_bounds"],
        "repeatability_characterized": False,
        "runs_compared": 2,
        "outputs": {"summary": str(summary_path), "report": str(report_path)},
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print(f"compared {comparison['baseline']['calibration_id']} vs {comparison['repeat']['calibration_id']}")
        print("repeatability_characterized=false; two runs give one delta, not a distribution")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

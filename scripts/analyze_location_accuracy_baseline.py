"""Build a D2 location-accuracy baseline from FIELD-003 evidence.

This is an offline, no-hardware tool. It reads a Message Hub test-run export
and a FIELD-003 field manifest, reuses the GNSS acceptance analyzer for
attempt matching and distance math, then writes the bounded D2 report format
consumed by the Dashboard Field Test Results panel.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "reports" / "location_accuracy"
GENERATOR_NAME = "D2.location_accuracy_baseline"
GENERATOR_VERSION = "0.1.0"
REPORT_JSON = "location_accuracy_report.json"
REPORT_MARKDOWN = "location_accuracy_report.md"

if __package__ in (None, ""):
    sys.path.insert(0, str(REPO_ROOT))

from scripts import analyze_gnss_acceptance as gnss  # noqa: E402


class LocationAccuracyBaselineError(RuntimeError):
    """Raised when D2 baseline evidence cannot be analyzed."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def numeric_or_none(value: object) -> float | None:
    return gnss.numeric_or_none(value)


def rounded(value: object, digits: int = 3) -> float | None:
    number = numeric_or_none(value)
    return round(number, digits) if number is not None else None


def distribution_p50(values: list[float]) -> float | None:
    return rounded(gnss.percentile(values, 0.50))


def distribution_p90(values: list[float]) -> float | None:
    return rounded(gnss.percentile(values, 0.90))


def fmt_number(value: object, digits: int = 2) -> str:
    number = numeric_or_none(value)
    return "n/a" if number is None else f"{number:.{digits}f}"


def fmt_rate(value: object) -> str:
    number = numeric_or_none(value)
    return "n/a" if number is None else f"{number * 100.0:.1f}%"


def safe_path_ref(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve())).replace("\\", "/")
    except (OSError, ValueError):
        return path.name


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def errors_for_rows(rows: list[dict[str, Any]]) -> list[float]:
    return [
        float(row["error_m"])
        for row in rows
        if row.get("status") == "fix" and numeric_or_none(row.get("error_m")) is not None
    ]


def ttff_for_rows(rows: list[dict[str, Any]]) -> list[float]:
    return [
        float(row["ttff_s"])
        for row in rows
        if row.get("status") == "fix" and numeric_or_none(row.get("ttff_s")) is not None
    ]


def redacted_per_point(gnss_report: dict[str, Any]) -> list[dict[str, Any]]:
    rows_by_point: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in as_list(gnss_report.get("attempts")):
        if isinstance(row, dict):
            rows_by_point[str(row.get("point_id") or "unknown")].append(row)

    result: list[dict[str, Any]] = []
    for point in as_list(gnss_report.get("per_point")):
        if not isinstance(point, dict):
            continue
        point_id = str(point.get("point_id") or "unknown")
        rows = rows_by_point.get(point_id, [])
        errors = errors_for_rows(rows)
        ttff = ttff_for_rows(rows)
        eale = as_dict(point.get("eale_radius_comparison"))
        result.append(
            {
                "point_id": point_id,
                "point_type": point.get("point_type"),
                "attempts": point.get("attempts"),
                "cold_attempts": point.get("cold_attempts"),
                "warm_attempts": point.get("warm_attempts"),
                "fix_count": point.get("fix_count"),
                "fix_rate": rounded(point.get("fix_rate")),
                "ttff_median_s": distribution_p50(ttff),
                "ttff_p90_s": distribution_p90(ttff),
                "median_error_m": distribution_p50(errors),
                "p90_error_m": distribution_p90(errors),
                "hdop_error_correlation": rounded(point.get("hdop_error_correlation")),
                "outside_eale_radius_count": eale.get("outside_count"),
            }
        )
    return result


def build_metrics(gnss_report: dict[str, Any]) -> dict[str, Any]:
    rows = [row for row in as_list(gnss_report.get("attempts")) if isinstance(row, dict)]
    fixed_rows = [row for row in rows if row.get("status") == "fix"]
    errors = errors_for_rows(rows)
    ttff = ttff_for_rows(rows)
    counts = as_dict(gnss_report.get("counts"))
    overall = as_dict(gnss_report.get("overall"))
    return {
        "fix_rate": rounded(overall.get("fix_rate")),
        "ttff_median_s": distribution_p50(ttff),
        "ttff_p90_s": distribution_p90(ttff),
        "median_error_m": distribution_p50(errors),
        "p90_error_m": distribution_p90(errors),
        "hdop_error_correlation": rounded(overall.get("hdop_error_correlation")),
        "reference_point_count": counts.get("reference_points"),
        "attempt_count": counts.get("attempts"),
        "sample_count": counts.get("attempts"),
        "fixed_attempts": len(fixed_rows),
        "no_fix_attempts": counts.get("no_fix_attempts"),
        "missing_observation_attempts": counts.get("missing_observation_attempts"),
    }


def build_location_accuracy_report(
    export: dict[str, Any],
    manifest: dict[str, Any],
    *,
    input_path: Path | None = None,
    manifest_path: Path | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    created_at = created_at or utc_now()
    gnss_report = gnss.evaluate_gnss_acceptance(
        export,
        manifest,
        input_path=input_path,
        manifest_path=manifest_path,
        created_at=created_at,
    )
    gnss_result = as_dict(gnss_report.get("result"))
    source = as_dict(gnss_report.get("source"))
    metrics = build_metrics(gnss_report)
    per_point = redacted_per_point(gnss_report)
    eale = as_dict(gnss_report.get("eale_p0_comparison"))
    status = str(gnss_result.get("status") or "FAIL")

    return {
        "schema_version": "egolink.d2_location_accuracy_report.v0.1",
        "generator": {
            "name": GENERATOR_NAME,
            "version": GENERATOR_VERSION,
            "created_at": created_at,
            "source_generator": as_dict(gnss_report.get("generator")).get("name"),
            "source_generator_version": as_dict(gnss_report.get("generator")).get("version"),
        },
        "result": {
            "status": status,
            "errors": as_list(gnss_result.get("errors")),
            "warnings": as_list(gnss_result.get("warnings")),
            "field_gnss_status": status,
        },
        "run_id": source.get("test_run_id"),
        "created_at": created_at,
        "device_id": source.get("device_id"),
        "source": {
            "test_run_id": source.get("test_run_id"),
            "board_id": source.get("board_id"),
            "device_id": source.get("device_id"),
            "firmware_version": source.get("firmware_version"),
            "firmware_commit_or_image": source.get("firmware_commit_or_image"),
            "connection_path": source.get("connection_path"),
            "input_export": safe_path_ref(input_path),
            "field_manifest": safe_path_ref(manifest_path),
        },
        "metrics": metrics,
        "per_point": per_point,
        "eale_p0_comparison": {
            "assumption": eale.get("assumption"),
            "fixed_hdop_error_pairs": eale.get("fixed_hdop_error_pairs"),
            "outside_eale_radius_count": eale.get("outside_eale_radius_count"),
            "max_error_to_eale_radius_ratio": rounded(eale.get("max_error_to_eale_radius_ratio")),
            "revision_assessment": eale.get("revision_assessment"),
            "needs_revision": eale.get("needs_revision"),
        },
        "privacy": {
            "raw_coordinates_exposed": False,
            "exact_coordinates_copied": False,
            "raw_payload_copied": False,
            "static_report_policy": "bounded_summary_no_raw_coordinates",
        },
        "scope": {
            "hardware_contacted": False,
            "firmware_changed": False,
            "commands_sent": False,
            "location_accuracy_claimed": False,
            "engineering_baseline_only": True,
            "model_training_started": False,
            "model_artifact_written": False,
        },
        "non_claims": [
            "engineering_baseline_not_product_accuracy_claim",
            "no_learned_model_training_or_deployment",
            "no_raw_private_coordinates_in_dashboard_summary",
        ],
        "next_step": "sync this report to Field Test Results and compare the next D2 run against this baseline",
    }


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    result = as_dict(report.get("result"))
    source = as_dict(report.get("source"))
    metrics = as_dict(report.get("metrics"))
    eale = as_dict(report.get("eale_p0_comparison"))
    lines = [
        "# D2 Location Accuracy Baseline",
        "",
        f"- Result: {result.get('status', 'unknown')}",
        f"- Test run: {source.get('test_run_id', 'unknown')}",
        f"- Device: {source.get('device_id', 'unknown')}",
        f"- Board: {source.get('board_id', 'unknown')}",
        f"- Firmware: {source.get('firmware_version', 'unknown')}",
        f"- Connection path: {source.get('connection_path', 'unknown')}",
        "",
        "## Core Metrics",
        "",
        f"- Fix rate: {fmt_rate(metrics.get('fix_rate'))}",
        f"- TTFF median / p90: {fmt_number(metrics.get('ttff_median_s'))} s / {fmt_number(metrics.get('ttff_p90_s'))} s",
        f"- Error median / p90: {fmt_number(metrics.get('median_error_m'))} m / {fmt_number(metrics.get('p90_error_m'))} m",
        f"- Reference points: {metrics.get('reference_point_count', 0)}",
        f"- Attempts: {metrics.get('attempt_count', 0)}",
        f"- Fixed / no-fix / missing: {metrics.get('fixed_attempts', 0)} / {metrics.get('no_fix_attempts', 0)} / {metrics.get('missing_observation_attempts', 0)}",
        "",
        "## Per-Point Breakdown",
        "",
        "| point_id | type | attempts | fix_rate | ttff_p90_s | p90_error_m | outside_eale_radius |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for point in as_list(report.get("per_point")):
        if not isinstance(point, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    str(point.get("point_id")),
                    str(point.get("point_type")),
                    str(point.get("attempts")),
                    fmt_rate(point.get("fix_rate")),
                    fmt_number(point.get("ttff_p90_s")),
                    fmt_number(point.get("p90_error_m")),
                    str(point.get("outside_eale_radius_count", 0)),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## EALE-P0 Check",
            "",
            f"- Assumption: {eale.get('assumption', 'unknown')}",
            f"- Outside assumed radius: {eale.get('outside_eale_radius_count', 0)}",
            f"- Revision assessment: {eale.get('revision_assessment', 'unknown')}",
            "",
            "## Warnings",
            "",
        ]
    )
    warnings = as_list(result.get("warnings"))
    lines.extend((f"- {warning}" for warning in warnings) if warnings else ["- none"])
    errors = as_list(result.get("errors"))
    if errors:
        lines.extend(["", "## Errors", ""])
        lines.extend(f"- {error}" for error in errors)
    lines.extend(["", "## Non-Claims", ""])
    lines.extend(f"- {claim}" for claim in as_list(report.get("non_claims")))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def default_output_dir(report: dict[str, Any]) -> Path:
    run_id = str(report.get("run_id") or f"D2-001-{datetime.now(timezone.utc):%Y%m%d}")
    return DEFAULT_OUTPUT_ROOT / run_id


def analyze_location_accuracy_baseline(
    *,
    input_path: Path,
    manifest_path: Path,
    output_dir: Path | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    try:
        export = gnss.load_json_object(input_path)
        manifest = gnss.load_json_object(manifest_path)
    except gnss.GnssAcceptanceError as exc:
        raise LocationAccuracyBaselineError(str(exc)) from exc
    report = build_location_accuracy_report(
        export,
        manifest,
        input_path=input_path,
        manifest_path=manifest_path,
        created_at=created_at,
    )
    target_dir = output_dir or default_output_dir(report)
    target_dir.mkdir(parents=True, exist_ok=True)
    report_path = target_dir / REPORT_JSON
    markdown_path = target_dir / REPORT_MARKDOWN
    report["report_path"] = str(report_path)
    report["markdown_report_path"] = str(markdown_path)
    write_json(report_path, report)
    write_markdown(markdown_path, report)
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
        report = analyze_location_accuracy_baseline(
            input_path=args.input_path,
            manifest_path=args.manifest,
            output_dir=args.output_dir,
        )
    except LocationAccuracyBaselineError as exc:
        print(f"FAIL D2 location accuracy baseline: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        status = as_dict(report.get("result")).get("status")
        print(f"{status} D2 location accuracy baseline run_id={report.get('run_id')} report={report.get('markdown_report_path')}")
    return 1 if as_dict(report.get("result")).get("status") == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())

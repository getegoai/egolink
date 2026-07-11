"""Build a provisional D2 baseline from bounded historical VPS field windows.

The report separates measurable event-level GNSS fix rate from strict D2
metrics that require attempt timing and external reference coordinates. Raw
messages and private coordinates are never written to the report directory.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import statistics
import sys
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "reports" / "location_accuracy"
REPORT_JSON = "location_accuracy_report.json"
REPORT_MARKDOWN = "location_accuracy_report.md"
SCHEMA_VERSION = "egolink.d2_historical_baseline.v0.1"
GENERATOR_VERSION = "0.1.0"

if __package__ in (None, ""):
    sys.path.insert(0, str(REPO_ROOT))

from scripts import run_location_d2_d5_pipeline as pipeline  # noqa: E402


class D2HistoricalBaselineError(RuntimeError):
    """Raised when bounded historical evidence cannot be summarized safely."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def parse_utc(value: object, *, field: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise D2HistoricalBaselineError(f"observer report is missing {field}")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise D2HistoricalBaselineError(f"observer report has invalid {field}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def relative_ref(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.name


def load_observer_window(path: Path, *, margin_sec: int) -> dict[str, Any]:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise D2HistoricalBaselineError(f"cannot read observer report {path.name}: {type(exc).__name__}") from exc
    if not isinstance(report, dict):
        raise D2HistoricalBaselineError(f"observer report must be an object: {path.name}")
    summary = as_dict(report.get("summary"))
    start = parse_utc(
        summary.get("first_device_upload_at") or summary.get("first_location_upload_at"),
        field="first upload timestamp",
    ) - timedelta(seconds=margin_sec)
    end = parse_utc(
        summary.get("last_device_upload_at") or summary.get("last_location_upload_at"),
        field="last upload timestamp",
    ) + timedelta(seconds=margin_sec)
    if end < start:
        raise D2HistoricalBaselineError(f"observer report has reversed timestamps: {path.name}")
    return {
        "run_id": str(report.get("run_id") or path.parent.name),
        "device_id": str(report.get("device_id") or ""),
        "started_at": start.isoformat(),
        "ended_at": end.isoformat(),
        "observer_report": relative_ref(path),
    }


def first_value(message: Mapping[str, Any], *keys: str) -> Any:
    gnss = as_dict(message.get("gnss"))
    for key in keys:
        if message.get(key) is not None:
            return message.get(key)
        if gnss.get(key) is not None:
            return gnss.get(key)
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
    return parsed if math.isfinite(parsed) and parsed >= 0 else None


def location_reports(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for message in messages:
        if message.get("message_type") != "event" or message.get("event_type") != "location_report":
            continue
        key = (
            str(message.get("device_id") or ""),
            str(message.get("seq") or ""),
            str(message.get("server_received_at") or message.get("ts") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        reports.append(message)
    return reports


def summarize_window(window: Mapping[str, Any], export: Mapping[str, Any]) -> dict[str, Any]:
    reports = location_reports([item for item in as_list(export.get("messages")) if isinstance(item, dict)])
    fixes = [bool_value(first_value(message, "fix")) for message in reports]
    known_fixes = [value for value in fixes if value is not None]
    fix_count = sum(value is True for value in known_fixes)
    no_fix_count = sum(value is False for value in known_fixes)
    ttff_values = [
        value / 1000.0
        for message in reports
        if bool_value(first_value(message, "fix")) is True
        and (value := number_value(first_value(message, "attempt_ms"))) is not None
    ]
    speed_samples = sum(number_value(first_value(message, "speed_mps", "speed")) is not None for message in reports)
    imu_statuses: Counter[str] = Counter()
    for message in reports:
        imu = as_dict(message.get("imu"))
        status = str(
            imu.get("source_status")
            or imu.get("evidence_status")
            or message.get("imu_source_status")
            or message.get("imu_evidence_status")
            or "missing"
        )
        imu_statuses[status] += 1
    return {
        "run_id": window.get("run_id"),
        "observer_report": window.get("observer_report"),
        "started_at": window.get("started_at"),
        "ended_at": window.get("ended_at"),
        "export_complete": as_dict(export.get("window")).get("complete") is True,
        "location_report_count": len(reports),
        "known_fix_count": len(known_fixes),
        "fix_count": fix_count,
        "no_fix_count": no_fix_count,
        "event_fix_rate": round(fix_count / len(known_fixes), 6) if known_fixes else None,
        "ttff_sample_count": len(ttff_values),
        "ttff_median_s": round(statistics.median(ttff_values), 3) if ttff_values else None,
        "_ttff_values_s": ttff_values,
        "speed_sample_count": speed_samples,
        "imu_source_status_counts": dict(sorted(imu_statuses.items())),
    }


def build_report(
    *,
    run_id: str,
    generated_at: str,
    hub_url: str,
    device_id: str,
    windows: list[dict[str, Any]],
    token: str | None,
    request_timeout_sec: float,
    max_records: int,
) -> dict[str, Any]:
    window_summaries: list[dict[str, Any]] = []
    for window in windows:
        report_device = str(window.get("device_id") or device_id)
        if report_device and report_device != device_id:
            raise D2HistoricalBaselineError(
                f"observer device {report_device} does not match requested device {device_id}"
            )
        export = pipeline.fetch_device_window_export(
            hub_url=hub_url,
            device_id=device_id,
            started_at=str(window["started_at"]),
            ended_at=str(window["ended_at"]),
            max_records=max_records,
            token=token,
            timeout_sec=request_timeout_sec,
        )
        window_summaries.append(summarize_window(window, export))

    known_fix_count = sum(int(item["known_fix_count"]) for item in window_summaries)
    fix_count = sum(int(item["fix_count"]) for item in window_summaries)
    no_fix_count = sum(int(item["no_fix_count"]) for item in window_summaries)
    ttff_samples: list[float] = []
    for item in window_summaries:
        ttff_samples.extend(float(value) for value in as_list(item.pop("_ttff_values_s", [])))
    fix_rate = round(fix_count / known_fix_count, 6) if known_fix_count else None
    warnings = [
        "historical windows have no external reference coordinates; median and p90 position error are not measurable",
        "historical firmware messages have no explicit cold/warm attempt boundaries unless TTFF samples are reported",
        "event-level fix rate is provisional and is not the strict FIELD-003 per-attempt fix rate",
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "generator": {
            "name": "D2.historical_vps_baseline",
            "version": GENERATOR_VERSION,
            "created_at": generated_at,
        },
        "run_id": run_id,
        "created_at": generated_at,
        "device_id": device_id,
        "status": "WARN",
        "result": {
            "status": "WARN",
            "strict_d2_acceptance_ready": False,
            "reason": "historical_field_evidence_without_reference_truth_or_attempt_boundaries",
        },
        "metrics": {
            "fix_rate": fix_rate,
            "fix_rate_basis": "unique_location_report_events",
            "sample_count": known_fix_count,
            "fix_count": fix_count,
            "no_fix_count": no_fix_count,
            "ttff_median_s": round(statistics.median(ttff_samples), 3) if ttff_samples else None,
            "ttff_sample_count": len(ttff_samples),
            "median_error_m": None,
            "p90_error_m": None,
            "reference_point_count": 0,
        },
        "measurement_status": {
            "fix_rate": "provisional_event_level",
            "ttff": "measured" if ttff_samples else "not_measurable_missing_attempt_timing",
            "median_error": "not_measurable_missing_reference_truth",
            "p90_error": "not_measurable_missing_reference_truth",
        },
        "windows": window_summaries,
        "warnings": warnings,
        "errors": [],
        "next_step": "Run FIELD-003 with reference points and cold/warm attempt timestamps to replace this provisional baseline.",
        "scope": {
            "vps_read_only": True,
            "raw_exports_written": False,
            "raw_coordinates_written": False,
            "location_accuracy_claimed": False,
            "model_training_started": False,
        },
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    metrics = as_dict(report.get("metrics"))
    status = as_dict(report.get("measurement_status"))
    fix_rate = number_value(metrics.get("fix_rate"))
    fix_rate_text = f"{fix_rate * 100:.1f}%" if fix_rate is not None else "not measurable"
    lines = [
        "# D2 Historical VPS Baseline",
        "",
        f"- Run: `{report.get('run_id')}`",
        f"- Device: `{report.get('device_id')}`",
        f"- Result: **{report.get('status')} / provisional**",
        "",
        "## Baseline",
        "",
        f"- Event fix rate: **{fix_rate_text}** ({metrics.get('fix_count')} fix / {metrics.get('sample_count')} known reports)",
        f"- TTFF median: **{metrics.get('ttff_median_s') if metrics.get('ttff_median_s') is not None else 'not measurable'}** ({status.get('ttff')})",
        f"- Median position error: **not measurable** ({status.get('median_error')})",
        f"- P90 position error: **not measurable** ({status.get('p90_error')})",
        "",
        "## Field Windows",
        "",
        "| Window | Reports | Fix / No Fix | Event Fix Rate | TTFF Samples |",
        "|---|---:|---:|---:|---:|",
    ]
    for item in as_list(report.get("windows")):
        if not isinstance(item, dict):
            continue
        lines.append(
            f"| {item.get('run_id')} | {item.get('known_fix_count')} | {item.get('fix_count')} / {item.get('no_fix_count')} | {item.get('event_fix_rate')} | {item.get('ttff_sample_count')} |"
        )
    lines += [
        "",
        "## Decision",
        "",
        "This is the first evidence-backed historical field baseline, not strict D2 acceptance. It establishes an event-level fix-rate starting point but cannot support an accuracy or TTFF claim without reference truth and attempt boundaries.",
        "",
        f"Next: {report.get('next_step')}",
        "",
    ]
    return "\n".join(lines)


def write_report(report: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = dict(report)
    json_path = output_dir / REPORT_JSON
    markdown_path = output_dir / REPORT_MARKDOWN
    payload["report_path"] = relative_ref(json_path)
    payload["markdown_report_path"] = relative_ref(markdown_path)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(payload), encoding="utf-8")
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hub", required=True)
    parser.add_argument("--device-id", required=True)
    parser.add_argument("--observer-report", action="append", type=Path, required=True)
    parser.add_argument("--token-file", type=Path, default=pipeline.DEFAULT_TOKEN_FILE)
    parser.add_argument("--margin-sec", type=int, default=0)
    parser.add_argument("--max-records", type=int, default=10000)
    parser.add_argument("--request-timeout-sec", type=float, default=180.0)
    parser.add_argument("--run-id", default="D2-historical-vps-baseline")
    parser.add_argument("--generated-at")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.margin_sec < 0:
            raise D2HistoricalBaselineError("--margin-sec must be non-negative")
        windows = [load_observer_window(path, margin_sec=args.margin_sec) for path in args.observer_report]
        generated_at = args.generated_at or utc_now()
        report = build_report(
            run_id=args.run_id,
            generated_at=generated_at,
            hub_url=args.hub,
            device_id=args.device_id,
            windows=windows,
            token=pipeline.read_token(args.token_file),
            request_timeout_sec=args.request_timeout_sec,
            max_records=args.max_records,
        )
        output_dir = args.output_dir or DEFAULT_OUTPUT_ROOT / args.run_id
        written = write_report(report, output_dir)
    except (D2HistoricalBaselineError, pipeline.LocationD2D5PipelineError) as exc:
        print(f"FAIL D2 historical baseline: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(written, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"WARN D2 historical baseline report={written['markdown_report_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

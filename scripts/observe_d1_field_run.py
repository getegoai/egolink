"""Observe a D1 outdoor field run through the Message Hub Web/API.

This is a read-only long-run observer. It polls `/api/state`, records D1
freshness, LTE/location upload counters, map-coordinate availability, and power
sample progress, then writes JSON/Markdown reports plus JSONL samples. It does
not contact hardware directly, flash firmware, or send device commands.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import validate_d1_web_api as d1_web  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "reports" / "d1_field_observation"
OBSERVER_VERSION = "D1.field_observer.v2"
SAMPLES_JSONL = "d1_field_samples.jsonl"
STATUS_JSON = "d1_field_observation_status.json"
REPORT_JSON = "d1_field_observation_report.json"
REPORT_MARKDOWN = "d1_field_observation_report.md"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def number_or_none(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def int_or_none(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def summarize_sample(state: dict[str, Any], *, device_id: str | None, collected_at: str) -> dict[str, Any]:
    device = d1_web.select_d1_device(state, device_id=device_id)
    d1 = as_dict(device.get("d1_link"))
    estimate = as_dict(d1.get("location_estimate"))
    surface = as_dict(d1.get("map_surface"))
    freshness = as_dict(d1.get("upload_freshness"))
    uplink = as_dict(d1.get("uplink_metrics"))
    power_curve = as_dict(d1.get("power_curve"))
    components = as_dict(as_dict(d1.get("evidence")).get("components"))
    gnss = as_dict(components.get("gnss"))
    cell_lte = as_dict(components.get("cell_lte"))
    imu = as_dict(components.get("imu"))
    power = as_dict(components.get("power"))
    lat = number_or_none(surface.get("lat"))
    lon = number_or_none(surface.get("lon"))
    return {
        "collected_at": collected_at,
        "ok": bool(device),
        "device_id": device.get("device_id") or device_id,
        "d1_status": d1.get("status"),
        "location_state": estimate.get("state"),
        "location_reason": estimate.get("reason"),
        "location_updated_at": estimate.get("updated_at"),
        "last_device_upload_at": freshness.get("last_device_upload_at"),
        "last_location_upload_at": freshness.get("last_location_upload_at"),
        "last_location_event_type": freshness.get("last_location_event_type"),
        "freshness_s": number_or_none(freshness.get("freshness_s")),
        "last_seq": int_or_none(freshness.get("last_seq")),
        "map_mode": surface.get("mode"),
        "lat": lat,
        "lon": lon,
        "coordinate_seen": lat is not None and lon is not None,
        "raw_post_attempt_count": int_or_none(uplink.get("raw_post_attempt_count")),
        "raw_post_success_count": int_or_none(uplink.get("raw_post_success_count")),
        "raw_post_failure_count": int_or_none(uplink.get("raw_post_failure_count")),
        "raw_post_success_rate": number_or_none(uplink.get("raw_post_success_rate")),
        "location_event_count": int_or_none(uplink.get("location_event_count")),
        "power_sample_count": int_or_none(power_curve.get("sample_count")),
        "power_latest_sample_at": power_curve.get("latest_sample_at"),
        "battery_mv": int_or_none(power.get("battery_mv")),
        "soc_pct": number_or_none(power.get("soc_pct")),
        "power_evidence_status": power.get("evidence_status"),
        "gnss_seen": gnss.get("seen") is True,
        "gnss_fix": gnss.get("fix"),
        "gnss_state": gnss.get("state"),
        "gnss_reason_code": gnss.get("reason_code"),
        "cell_lte_seen": cell_lte.get("seen") is True,
        "cell_rat": cell_lte.get("rat"),
        "cell_id": cell_lte.get("cell_id"),
        "cell_registration_state": cell_lte.get("registration_state"),
        "cell_pdp_state": cell_lte.get("pdp_state"),
        "imu_seen": imu.get("seen") is True,
        "imu_evidence_status": imu.get("evidence_status"),
    }


def error_sample(*, device_id: str | None, collected_at: str, error: str) -> dict[str, Any]:
    return {
        "collected_at": collected_at,
        "ok": False,
        "device_id": device_id,
        "error": error,
    }


def metric_delta(samples: list[dict[str, Any]], key: str) -> int | float | None:
    values = [sample.get(key) for sample in samples if sample.get("ok") and isinstance(sample.get(key), (int, float))]
    if len(values) < 2:
        return None
    return values[-1] - values[0]


def first_value(samples: list[dict[str, Any]], key: str) -> Any:
    for sample in samples:
        if sample.get("ok") and sample.get(key) not in (None, ""):
            return sample.get(key)
    return None


def last_value(samples: list[dict[str, Any]], key: str) -> Any:
    for sample in reversed(samples):
        if sample.get("ok") and sample.get(key) not in (None, ""):
            return sample.get(key)
    return None


def unique_values(samples: list[dict[str, Any]], key: str) -> list[Any]:
    seen: list[Any] = []
    for sample in samples:
        value = sample.get(key)
        if sample.get("ok") and value not in (None, "") and value not in seen:
            seen.append(value)
    return seen


def value_advanced(samples: list[dict[str, Any]], key: str) -> bool:
    return len(unique_values(samples, key)) > 1


def evaluate_observation(
    *,
    samples: list[dict[str, Any]],
    run_id: str,
    hub_url: str,
    device_id: str | None,
    max_stale_sec: float,
    poll_interval_sec: float,
    duration_minutes: float,
) -> dict[str, Any]:
    ok_samples = [sample for sample in samples if sample.get("ok")]
    errors: list[str] = []
    warnings: list[str] = []
    if not ok_samples:
        errors.append("d1_no_successful_samples")

    fetch_error_count = sum(1 for sample in samples if not sample.get("ok"))
    stale_samples = [
        sample for sample in ok_samples if number_or_none(sample.get("freshness_s")) is not None and float(sample["freshness_s"]) > max_stale_sec
    ]
    missing_freshness = [sample for sample in ok_samples if sample.get("freshness_s") is None]
    coordinate_samples = [sample for sample in ok_samples if sample.get("coordinate_seen")]
    raw_failure_delta = metric_delta(ok_samples, "raw_post_failure_count")
    raw_success_delta = metric_delta(ok_samples, "raw_post_success_count")
    location_event_delta = metric_delta(ok_samples, "location_event_count")
    power_sample_delta = metric_delta(ok_samples, "power_sample_count")

    if fetch_error_count:
        warnings.append("d1_observer_fetch_errors_seen")
    if stale_samples:
        warnings.append("d1_upload_freshness_exceeded_threshold")
    if missing_freshness:
        warnings.append("d1_upload_freshness_missing")
    if not coordinate_samples:
        warnings.append("d1_coordinate_not_observed")
    if raw_failure_delta and raw_failure_delta > 0:
        warnings.append("d1_raw_post_failures_increased")
    location_advanced = (
        value_advanced(ok_samples, "last_location_upload_at")
        or value_advanced(ok_samples, "last_seq")
        or bool(raw_success_delta and raw_success_delta > 0)
        or bool(location_event_delta and location_event_delta > 0)
    )
    if len(ok_samples) > 1 and not location_advanced:
        warnings.append("d1_location_event_count_did_not_advance")
    power_observed = any(sample.get("battery_mv") is not None or sample.get("soc_pct") is not None for sample in ok_samples)
    power_advanced = value_advanced(ok_samples, "power_latest_sample_at") or bool(power_sample_delta and power_sample_delta > 0)
    if len(ok_samples) > 1 and not power_observed and not power_advanced:
        warnings.append("d1_power_sample_count_did_not_advance")

    result = "FAIL" if errors else ("WARN" if warnings else "PASS")
    freshness_values = [float(sample["freshness_s"]) for sample in ok_samples if sample.get("freshness_s") is not None]
    summary = {
        "sample_count": len(samples),
        "successful_sample_count": len(ok_samples),
        "fetch_error_count": fetch_error_count,
        "stale_sample_count": len(stale_samples),
        "coordinate_sample_count": len(coordinate_samples),
        "max_freshness_s": max(freshness_values) if freshness_values else None,
        "first_location_upload_at": first_value(ok_samples, "last_location_upload_at"),
        "last_location_upload_at": last_value(ok_samples, "last_location_upload_at"),
        "first_device_upload_at": first_value(ok_samples, "last_device_upload_at"),
        "last_device_upload_at": last_value(ok_samples, "last_device_upload_at"),
        "first_seq": first_value(ok_samples, "last_seq"),
        "last_seq": last_value(ok_samples, "last_seq"),
        "raw_post_success_start": first_value(ok_samples, "raw_post_success_count"),
        "raw_post_success_end": last_value(ok_samples, "raw_post_success_count"),
        "raw_post_success_delta": raw_success_delta,
        "raw_post_failure_start": first_value(ok_samples, "raw_post_failure_count"),
        "raw_post_failure_end": last_value(ok_samples, "raw_post_failure_count"),
        "raw_post_failure_delta": raw_failure_delta,
        "location_event_count_start": first_value(ok_samples, "location_event_count"),
        "location_event_count_end": last_value(ok_samples, "location_event_count"),
        "location_event_count_delta": location_event_delta,
        "power_sample_count_start": first_value(ok_samples, "power_sample_count"),
        "power_sample_count_end": last_value(ok_samples, "power_sample_count"),
        "power_sample_count_delta": power_sample_delta,
        "battery_mv_first": first_value(ok_samples, "battery_mv"),
        "battery_mv_last": last_value(ok_samples, "battery_mv"),
        "soc_pct_first": first_value(ok_samples, "soc_pct"),
        "soc_pct_last": last_value(ok_samples, "soc_pct"),
        "map_modes": unique_values(ok_samples, "map_mode"),
        "cell_ids": unique_values(ok_samples, "cell_id"),
        "cell_registration_states": unique_values(ok_samples, "cell_registration_state"),
        "cell_pdp_states": unique_values(ok_samples, "cell_pdp_state"),
        "gnss_states": unique_values(ok_samples, "gnss_state"),
        "imu_evidence_statuses": unique_values(ok_samples, "imu_evidence_status"),
        "power_evidence_statuses": unique_values(ok_samples, "power_evidence_status"),
    }
    return {
        "tool": "observe_d1_field_run",
        "observer_version": OBSERVER_VERSION,
        "result": result,
        "created_at": utc_now(),
        "run_id": run_id,
        "hub_url": hub_url.rstrip("/"),
        "device_id": last_value(ok_samples, "device_id") or device_id,
        "duration_minutes_requested": duration_minutes,
        "poll_interval_sec": poll_interval_sec,
        "max_stale_sec": max_stale_sec,
        "summary": summary,
        "errors": errors,
        "warnings": warnings,
        "scope": {
            "hardware_contacted_directly": False,
            "firmware_changed": False,
            "commands_sent": False,
            "gitlab_modified": False,
            "location_accuracy_claimed": False,
            "battery_life_claimed": False,
        },
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_samples(path: Path, samples: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(sample, ensure_ascii=False) + "\n" for sample in samples), encoding="utf-8")


def append_sample(path: Path, sample: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(sample, ensure_ascii=False) + "\n")


def latest_successful_sample(samples: list[dict[str, Any]]) -> dict[str, Any]:
    for sample in reversed(samples):
        if sample.get("ok"):
            return sample
    return {}


def write_status(
    path: Path,
    *,
    status: str,
    run_id: str,
    hub_url: str,
    device_id: str | None,
    planned_samples: int,
    samples: list[dict[str, Any]],
    samples_path: Path,
    report_json: Path,
    report_md: Path,
    result: str | None = None,
) -> None:
    latest = latest_successful_sample(samples)
    payload = {
        "tool": "observe_d1_field_run",
        "observer_version": OBSERVER_VERSION,
        "status": status,
        "result": result,
        "updated_at": utc_now(),
        "run_id": run_id,
        "hub_url": hub_url.rstrip("/"),
        "device_id": latest.get("device_id") or device_id,
        "planned_sample_count": planned_samples,
        "sample_count": len(samples),
        "successful_sample_count": sum(1 for sample in samples if sample.get("ok")),
        "fetch_error_count": sum(1 for sample in samples if not sample.get("ok")),
        "latest_sample_collected_at": latest.get("collected_at"),
        "latest_seq": latest.get("last_seq"),
        "latest_location_upload_at": latest.get("last_location_upload_at"),
        "latest_freshness_s": latest.get("freshness_s"),
        "latest_d1_status": latest.get("d1_status"),
        "samples_path": str(samples_path),
        "report_path": str(report_json),
        "markdown_report_path": str(report_md),
        "sample_write_mode": "incremental_jsonl",
        "scope": {
            "hardware_contacted_directly": False,
            "firmware_changed": False,
            "commands_sent": False,
            "gitlab_modified": False,
            "location_accuracy_claimed": False,
            "battery_life_claimed": False,
        },
    }
    write_json(path, payload)


def write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    summary = as_dict(report.get("summary"))
    lines = [
        "# D1 Field Observation Report",
        "",
        f"- Result: {report.get('result')}",
        f"- Observer version: {report.get('observer_version')}",
        f"- Run ID: {report.get('run_id')}",
        f"- Hub: {report.get('hub_url')}",
        f"- Device: {report.get('device_id')}",
        f"- Samples: {summary.get('successful_sample_count')} ok / {summary.get('sample_count')} total",
        f"- Freshness max: {summary.get('max_freshness_s')} s",
        f"- Location upload window: {summary.get('first_location_upload_at')} -> {summary.get('last_location_upload_at')}",
        f"- Raw POST delta: {summary.get('raw_post_success_delta')} ok / {summary.get('raw_post_failure_delta')} fail",
        f"- Location event delta: {summary.get('location_event_count_delta')}",
        f"- Power sample delta: {summary.get('power_sample_count_delta')}",
        f"- Battery: {summary.get('battery_mv_first')} mV -> {summary.get('battery_mv_last')} mV",
        f"- SoC: {summary.get('soc_pct_first')}% -> {summary.get('soc_pct_last')}%",
        f"- Map modes: {', '.join(str(item) for item in summary.get('map_modes') or [])}",
        f"- GNSS states: {', '.join(str(item) for item in summary.get('gnss_states') or [])}",
        "",
        "## Warnings",
        "",
    ]
    warnings = report.get("warnings") or []
    lines.extend(f"- {item}" for item in warnings) if warnings else lines.append("- none")
    lines.extend(["", "## Errors", ""])
    errors = report.get("errors") or []
    lines.extend(f"- {item}" for item in errors) if errors else lines.append("- none")
    lines.extend(
        [
            "",
            "## Boundaries",
            "",
            "- This observer reads the Message Hub Web/API only.",
            "- It does not directly contact hardware, flash firmware, send device commands, or modify GitLab.",
            "- It does not claim location accuracy, battery life, GNSS acceptance, or long LTE stability.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def observe_field_run(
    *,
    hub_url: str,
    token: str | None,
    output_dir: Path,
    run_id: str,
    device_id: str | None,
    duration_minutes: float,
    poll_interval_sec: float,
    max_stale_sec: float,
    timeout: float,
    sample_count: int | None = None,
) -> dict[str, Any]:
    if duration_minutes <= 0:
        raise ValueError("duration_minutes must be positive")
    if poll_interval_sec < 0:
        raise ValueError("poll_interval_sec must be non-negative")
    if max_stale_sec <= 0:
        raise ValueError("max_stale_sec must be positive")
    planned_samples = sample_count if sample_count is not None else max(1, int(duration_minutes * 60 // max(poll_interval_sec, 1)) + 1)
    if planned_samples <= 0:
        raise ValueError("sample_count must be positive")

    samples_path = output_dir / SAMPLES_JSONL
    status_path = output_dir / STATUS_JSON
    report_json = output_dir / REPORT_JSON
    report_md = output_dir / REPORT_MARKDOWN
    samples_path.parent.mkdir(parents=True, exist_ok=True)
    samples_path.write_text("", encoding="utf-8")
    samples: list[dict[str, Any]] = []
    write_status(
        status_path,
        status="running",
        run_id=run_id,
        hub_url=hub_url,
        device_id=device_id,
        planned_samples=planned_samples,
        samples=samples,
        samples_path=samples_path,
        report_json=report_json,
        report_md=report_md,
    )
    for index in range(planned_samples):
        collected_at = utc_now()
        try:
            state = d1_web.fetch_json(hub_url, "/api/state", token=token, timeout=timeout)
            sample = summarize_sample(state, device_id=device_id, collected_at=collected_at)
        except Exception as exc:  # noqa: BLE001 - report read-only observer failures, keep observing.
            sample = error_sample(device_id=device_id, collected_at=collected_at, error=str(exc))
        samples.append(sample)
        append_sample(samples_path, sample)
        write_status(
            status_path,
            status="running",
            run_id=run_id,
            hub_url=hub_url,
            device_id=device_id,
            planned_samples=planned_samples,
            samples=samples,
            samples_path=samples_path,
            report_json=report_json,
            report_md=report_md,
        )
        if index < planned_samples - 1 and poll_interval_sec > 0:
            time.sleep(poll_interval_sec)

    report = evaluate_observation(
        samples=samples,
        run_id=run_id,
        hub_url=hub_url,
        device_id=device_id,
        max_stale_sec=max_stale_sec,
        poll_interval_sec=poll_interval_sec,
        duration_minutes=duration_minutes,
    )
    report["samples_path"] = str(samples_path)
    report["status_path"] = str(status_path)
    report["report_path"] = str(report_json)
    report["markdown_report_path"] = str(report_md)
    report["sample_write_mode"] = "incremental_jsonl"
    write_json(report_json, report)
    write_markdown_report(report_md, report)
    write_status(
        status_path,
        status="completed",
        result=report.get("result"),
        run_id=run_id,
        hub_url=hub_url,
        device_id=device_id,
        planned_samples=planned_samples,
        samples=samples,
        samples_path=samples_path,
        report_json=report_json,
        report_md=report_md,
    )
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hub-url", default=d1_web.DEFAULT_HUB_URL)
    parser.add_argument("--token-file", type=Path, default=d1_web.DEFAULT_TOKEN_FILE)
    parser.add_argument("--run-id")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--device-id")
    parser.add_argument("--duration-minutes", type=float, default=240.0)
    parser.add_argument("--poll-interval-sec", type=float, default=60.0)
    parser.add_argument("--max-stale-sec", type=float, default=180.0)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--sample-count", type=int)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run_id = args.run_id or f"d1-field-observation-{d1_web.compact_utc_now()}"
    output_dir = args.output_dir or (DEFAULT_OUTPUT_ROOT / run_id)
    report = observe_field_run(
        hub_url=args.hub_url,
        token=d1_web.read_token(args.token_file),
        output_dir=output_dir,
        run_id=run_id,
        device_id=args.device_id,
        duration_minutes=args.duration_minutes,
        poll_interval_sec=args.poll_interval_sec,
        max_stale_sec=args.max_stale_sec,
        timeout=args.timeout,
        sample_count=args.sample_count,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"{report['result']} D1 field observation: {report['markdown_report_path']}")
    return 1 if report["result"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())

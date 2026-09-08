"""Observe server-side field readiness through the Message Hub Web/API.

This is a read-only D2/D5 preflight and long-run observer. It polls the
Message Hub health endpoint, `/api/state`, and `/engineering` Dashboard HTML, then writes a
bounded readiness report. It does not flash firmware, open serial ports,
enqueue commands, deploy services, train models, or claim location accuracy.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Iterable
from urllib import error, request

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.validate_fw001_hw_loop import (  # noqa: E402
    DEFAULT_HUB_URL,
    FieldValidationError,
    HubClient,
    compact_utc_now,
    parse_timestamp,
    utc_now,
    write_json,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TOKEN_FILE = REPO_ROOT / "server" / "runtime" / "vps_message_hub_token.txt"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "reports" / "field_readiness"
REPORT_JSON = "field_readiness_report.json"
REPORT_MARKDOWN = "field_readiness_report.md"
STATUS_JSON = "field_readiness_status.json"
SAMPLES_JSONL = "field_readiness_samples.jsonl"
ENGINEERING_DASHBOARD_PATH = "/engineering"
DASHBOARD_MARKERS = (
    "Ego Link Message Hub",
    "D1 Link Through",
    "Field Test Results",
    "Data Flywheel",
    "Latest Field State",
)


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def number_or_none(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def int_or_none(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def unique_text(values: Iterable[object]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in (None, ""):
            continue
        text = str(value)
        if text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def auth_headers(token: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token else {}


def read_token(token_env: str, token_file: Path | None) -> str | None:
    env_token = os.environ.get(token_env)
    if env_token:
        return env_token
    if token_file and token_file.exists():
        token = token_file.read_text(encoding="utf-8").strip()
        return token or None
    return None


def fetch_dashboard_html(base_url: str, *, token: str | None, timeout: float) -> str:
    req = request.Request(
        base_url.rstrip("/") + ENGINEERING_DASHBOARD_PATH,
        headers=auth_headers(token), method="GET",
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise FieldValidationError(f"GET {ENGINEERING_DASHBOARD_PATH} returned HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise FieldValidationError(f"GET {ENGINEERING_DASHBOARD_PATH} failed: {exc}") from exc


def dashboard_summary(html: str, markers: Iterable[str] = DASHBOARD_MARKERS) -> dict[str, Any]:
    missing = [marker for marker in markers if marker not in html]
    return {
        "reachable": bool(html),
        "html_bytes": len(html.encode("utf-8")),
        "required_markers": list(markers),
        "missing_markers": missing,
        "markers_present": not missing,
    }


def select_device(state: dict[str, Any], device_id: str | None) -> dict[str, Any]:
    devices = [item for item in as_list(state.get("devices")) if isinstance(item, dict)]
    if device_id:
        for device in devices:
            if device.get("device_id") == device_id:
                return device
        return {}
    for device in devices:
        if as_dict(device.get("d1_link")):
            return device
    return devices[0] if devices else {}


def seconds_since(timestamp_text: object, now_text: str) -> float | None:
    timestamp = parse_timestamp(timestamp_text)
    now = parse_timestamp(now_text)
    if timestamp is None or now is None:
        return None
    return max(0.0, (now - timestamp).total_seconds())


def compact_field_results(field_results: dict[str, Any]) -> dict[str, Any]:
    cards = as_list(field_results.get("cards"))
    return {
        "available": field_results.get("available"),
        "status": field_results.get("status"),
        "reason": field_results.get("reason"),
        "card_count": len(cards),
        "latest_kind": as_dict(cards[0]).get("kind") if cards else None,
        "latest_status": as_dict(cards[0]).get("status") if cards else None,
    }


def compact_data_flywheel(data_flywheel: dict[str, Any]) -> dict[str, Any]:
    counts = as_dict(data_flywheel.get("counts"))
    readiness = as_dict(data_flywheel.get("readiness"))
    paths = as_dict(data_flywheel.get("paths"))
    return {
        "available": data_flywheel.get("available"),
        "status": data_flywheel.get("status"),
        "pipeline_stage": data_flywheel.get("pipeline_stage"),
        "reason": data_flywheel.get("reason"),
        "records_total": counts.get("records_total"),
        "needs_review_records": counts.get("needs_review_records"),
        "dataset_manifest_ready": readiness.get("dataset_manifest_ready"),
        "model_training_ready": readiness.get("model_training_ready"),
        "readiness_reason": readiness.get("reason"),
        "review_packet_markdown": paths.get("location_review_packet_markdown"),
        "status_markdown": paths.get("data_flywheel_status_markdown"),
    }


def sample_state(
    *,
    hub_url: str,
    client: HubClient,
    token: str | None,
    device_id: str | None,
    request_timeout_sec: float,
) -> dict[str, Any]:
    collected_at = utc_now()
    sample: dict[str, Any] = {
        "collected_at": collected_at,
        "hub_url": hub_url,
        "ok": False,
        "errors": [],
        "warnings": [],
    }
    try:
        health = client.get("/health")
        state = client.get("/api/state")
        html = fetch_dashboard_html(hub_url, token=token, timeout=request_timeout_sec)
    except FieldValidationError as exc:
        sample["errors"] = [str(exc)]
        return sample

    device = select_device(state, device_id)
    d1 = as_dict(device.get("d1_link"))
    readiness = as_dict(d1.get("field_readiness"))
    acceptance = as_dict(d1.get("acceptance_gate"))
    estimate = as_dict(d1.get("location_estimate"))
    freshness = as_dict(d1.get("upload_freshness"))
    map_surface = as_dict(d1.get("map_surface"))
    trajectory = as_dict(map_surface.get("trajectory"))
    uplink = as_dict(d1.get("uplink_metrics"))
    power_curve = as_dict(d1.get("power_curve"))
    dashboard = dashboard_summary(html)
    field_results = compact_field_results(as_dict(state.get("field_results")))
    data_flywheel = compact_data_flywheel(as_dict(state.get("data_flywheel")))

    sample.update(
        {
            "ok": True,
            "health_ok": health.get("ok") is True,
            "service": health.get("service"),
            "dashboard": dashboard,
            "device_count": len([item for item in as_list(state.get("devices")) if isinstance(item, dict)]),
            "device_found": bool(device),
            "device_id": device.get("device_id") or device_id,
            "device_status": device.get("status"),
            "last_seen_at": device.get("last_seen_at"),
            "last_seen_age_sec": seconds_since(device.get("last_seen_at"), collected_at),
            "last_seq": device.get("last_seq"),
            "last_message_type": device.get("last_message_type"),
            "d1_status": d1.get("status"),
            "field_ready": readiness.get("ready") is True,
            "field_readiness": {
                "state": readiness.get("state"),
                "reason": readiness.get("reason"),
                "operator_action": readiness.get("operator_action"),
                "freshness_s": number_or_none(readiness.get("freshness_s")),
                "latest_upload_at": readiness.get("latest_upload_at"),
                "raw_post_health": readiness.get("raw_post_health"),
            },
            "acceptance_gate": {
                "status": acceptance.get("status"),
                "blockers": unique_text(as_list(acceptance.get("blockers"))),
                "warnings": unique_text(as_list(acceptance.get("warnings"))),
                "next_action": acceptance.get("next_action"),
            },
            "location_estimate": {
                "available": estimate.get("available"),
                "state": estimate.get("state"),
                "reason": estimate.get("reason"),
                "accuracy_claim": estimate.get("accuracy_claim"),
            },
            "map_surface": {
                "visible": map_surface.get("visible"),
                "mode": map_surface.get("mode"),
                "review_mode": map_surface.get("review_mode"),
                "trajectory_points": int_or_none(trajectory.get("point_count")),
                "reference_points": len(as_list(map_surface.get("reference_points"))),
                "accuracy_claim": map_surface.get("accuracy_claim"),
            },
            "upload_freshness": {
                "last_location_upload_at": freshness.get("last_location_upload_at"),
                "freshness_s": number_or_none(freshness.get("freshness_s")),
                "last_location_event_type": freshness.get("last_location_event_type"),
                "last_seq": freshness.get("last_seq"),
            },
            "uplink_metrics": {
                "location_event_count": uplink.get("location_event_count"),
                "raw_post_attempt_count": uplink.get("raw_post_attempt_count"),
                "raw_post_success_count": uplink.get("raw_post_success_count"),
                "raw_post_failure_count": uplink.get("raw_post_failure_count"),
                "raw_post_success_rate": uplink.get("raw_post_success_rate"),
            },
            "power_curve": {
                "sample_count": power_curve.get("sample_count"),
                "latest_sample_at": power_curve.get("latest_sample_at"),
                "battery_life_claim": power_curve.get("battery_life_claim"),
            },
            "field_results": field_results,
            "data_flywheel": data_flywheel,
        }
    )
    return sample


def sample_has_new_upload(samples: list[dict[str, Any]]) -> bool:
    ok_samples = [sample for sample in samples if sample.get("ok")]
    if len(ok_samples) < 2:
        return False
    first = ok_samples[0]
    latest = ok_samples[-1]
    first_seq = first.get("upload_freshness", {}).get("last_seq")
    latest_seq = latest.get("upload_freshness", {}).get("last_seq")
    if isinstance(first_seq, int) and isinstance(latest_seq, int) and latest_seq > first_seq:
        return True
    for key in ("last_location_upload_at",):
        if latest.get("upload_freshness", {}).get(key) not in (None, "", first.get("upload_freshness", {}).get(key)):
            return True
    first_success = first.get("uplink_metrics", {}).get("raw_post_success_count")
    latest_success = latest.get("uplink_metrics", {}).get("raw_post_success_count")
    if isinstance(first_success, int) and isinstance(latest_success, int) and latest_success > first_success:
        return True
    return False


def evaluate_samples(
    samples: list[dict[str, Any]],
    *,
    run_id: str,
    hub_url: str,
    device_id: str | None,
    require_fresh: bool,
    require_dashboard_markers: bool,
    min_success_samples: int,
) -> dict[str, Any]:
    ok_samples = [sample for sample in samples if sample.get("ok")]
    latest = ok_samples[-1] if ok_samples else {}
    errors: list[str] = []
    warnings: list[str] = []

    if len(ok_samples) < min_success_samples:
        errors.append(f"successful sample count {len(ok_samples)} below required {min_success_samples}")
    if any(sample.get("errors") for sample in samples):
        warnings.append("one_or_more_poll_errors")
    if not latest.get("health_ok"):
        errors.append("message_hub_health_not_ok")
    if not latest.get("device_found"):
        errors.append("target_device_not_found")
    dashboard = as_dict(latest.get("dashboard"))
    if require_dashboard_markers and not dashboard.get("markers_present"):
        errors.append("dashboard_required_markers_missing")
    if require_fresh and latest.get("field_ready") is not True:
        reason = as_dict(latest.get("field_readiness")).get("reason") or "unknown"
        errors.append(f"field_readiness_not_ready:{reason}")
    if as_dict(latest.get("location_estimate")).get("accuracy_claim") not in (None, "none"):
        errors.append("location_accuracy_claim_present")
    if as_dict(latest.get("map_surface")).get("accuracy_claim") not in (None, "none"):
        errors.append("map_accuracy_claim_present")
    if as_dict(latest.get("power_curve")).get("battery_life_claim") not in (None, "none"):
        errors.append("battery_life_claim_present")
    if ok_samples and not as_dict(latest.get("data_flywheel")).get("available"):
        warnings.append("data_flywheel_summary_not_available")
    if ok_samples and not as_dict(latest.get("field_results")).get("available"):
        warnings.append("field_results_summary_not_available")
    if len(ok_samples) > 1 and not sample_has_new_upload(ok_samples):
        warnings.append("no_new_upload_observed_during_window")

    result = "FAIL" if errors else ("WARN" if warnings else "PASS")
    return {
        "result": result,
        "run_id": run_id,
        "hub_url": hub_url,
        "device_id": latest.get("device_id") or device_id,
        "generated_at": utc_now(),
        "sample_count": len(samples),
        "successful_sample_count": len(ok_samples),
        "ready_sample_count": sum(1 for sample in ok_samples if sample.get("field_ready") is True),
        "new_upload_observed": sample_has_new_upload(ok_samples),
        "latest": latest,
        "errors": unique_text(errors),
        "warnings": unique_text(warnings),
        "non_claims": [
            "This report is server-side readiness and observability only.",
            "It does not claim product location accuracy, GNSS acceptance, LTE long-run acceptance, battery life, model performance, or product readiness.",
            "It does not send device commands, flash firmware, open serial ports, deploy services, train models, or expose raw private coordinates.",
        ],
    }


def write_status(path: Path, *, run_id: str, state: str, report: dict[str, Any] | None, latest_sample: dict[str, Any] | None) -> None:
    payload = {
        "run_id": run_id,
        "state": state,
        "updated_at": utc_now(),
        "result": report.get("result") if report else None,
        "sample_count": report.get("sample_count") if report else None,
        "ready_sample_count": report.get("ready_sample_count") if report else None,
        "latest_sample": latest_sample or {},
        "report_path": report.get("report_path") if report else None,
        "markdown_report_path": report.get("markdown_report_path") if report else None,
    }
    write_json(path, payload)


def append_sample_jsonl(path: Path, sample: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(sample, ensure_ascii=False, separators=(",", ":")) + "\n")


def render_markdown(report: dict[str, Any]) -> str:
    latest = as_dict(report.get("latest"))
    readiness = as_dict(latest.get("field_readiness"))
    acceptance = as_dict(latest.get("acceptance_gate"))
    map_surface = as_dict(latest.get("map_surface"))
    data_flywheel = as_dict(latest.get("data_flywheel"))
    field_results = as_dict(latest.get("field_results"))
    lines = [
        "# Field Readiness Observation",
        "",
        f"- Result: {report.get('result', 'unknown')}",
        f"- Run ID: {report.get('run_id', 'unknown')}",
        f"- Hub: {report.get('hub_url', 'unknown')}",
        f"- Device: {report.get('device_id', 'unknown')}",
        f"- Generated at: {report.get('generated_at', 'unknown')}",
        f"- Samples: {report.get('successful_sample_count', 0)} ok / {report.get('sample_count', 0)} total",
        f"- Ready samples: {report.get('ready_sample_count', 0)}",
        f"- New upload observed: {report.get('new_upload_observed', False)}",
        "",
        "## Latest Server State",
        "",
        f"- Health: {latest.get('health_ok', False)} / {latest.get('service', 'unknown')}",
        f"- Last seen age: {latest.get('last_seen_age_sec', 'unknown')} s",
        f"- Last seq: {latest.get('last_seq', 'unknown')}",
        f"- Field ready: {latest.get('field_ready', False)}",
        f"- Readiness: {readiness.get('state', 'unknown')} / {readiness.get('reason', 'unknown')}",
        f"- Operator action: {readiness.get('operator_action', 'unknown')}",
        f"- Upload freshness: {readiness.get('freshness_s', 'unknown')} s",
        f"- Raw POST health: {readiness.get('raw_post_health', 'unknown')}",
        f"- Acceptance gate: {acceptance.get('status', 'unknown')}",
        f"- Acceptance blockers: {acceptance.get('blockers', [])}",
        f"- Map mode: {map_surface.get('mode', 'unknown')} / track={map_surface.get('trajectory_points', 'unknown')} / refs={map_surface.get('reference_points', 'unknown')}",
        "",
        "## Evidence Summaries",
        "",
        f"- Field results: available={field_results.get('available')} cards={field_results.get('card_count')} latest={field_results.get('latest_kind')}:{field_results.get('latest_status')}",
        f"- Data flywheel: available={data_flywheel.get('available')} status={data_flywheel.get('status')} records={data_flywheel.get('records_total')} needs_review={data_flywheel.get('needs_review_records')}",
        f"- Dataset manifest ready: {data_flywheel.get('dataset_manifest_ready')}",
        f"- Model training ready: {data_flywheel.get('model_training_ready')}",
        "",
        "## Errors",
        "",
    ]
    if report.get("errors"):
        lines.extend(f"- {item}" for item in report["errors"])
    else:
        lines.append("- none")
    lines.extend(["", "## Warnings", ""])
    if report.get("warnings"):
        lines.extend(f"- {item}" for item in report["warnings"])
    else:
        lines.append("- none")
    lines.extend(["", "## Non-Claims", ""])
    lines.extend(f"- {item}" for item in report.get("non_claims", []))
    return "\n".join(lines) + "\n"


def observe_field_readiness(
    *,
    hub_url: str,
    device_id: str | None,
    token: str | None,
    run_id: str,
    output_dir: Path,
    duration_sec: float,
    poll_interval_sec: float,
    request_timeout_sec: float,
    require_fresh: bool = True,
    require_dashboard_markers: bool = True,
    min_success_samples: int = 1,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    samples_path = output_dir / SAMPLES_JSONL
    status_path = output_dir / STATUS_JSON
    report_path = output_dir / REPORT_JSON
    markdown_path = output_dir / REPORT_MARKDOWN
    if samples_path.exists():
        samples_path.unlink()

    client = HubClient(hub_url, token=token, timeout=request_timeout_sec)
    samples: list[dict[str, Any]] = []
    deadline = time.monotonic() + max(0.0, duration_sec)
    write_status(status_path, run_id=run_id, state="running", report=None, latest_sample=None)

    while True:
        sample = sample_state(
            hub_url=hub_url,
            client=client,
            token=token,
            device_id=device_id,
            request_timeout_sec=request_timeout_sec,
        )
        samples.append(sample)
        append_sample_jsonl(samples_path, sample)
        partial = evaluate_samples(
            samples,
            run_id=run_id,
            hub_url=hub_url,
            device_id=device_id,
            require_fresh=require_fresh,
            require_dashboard_markers=require_dashboard_markers,
            min_success_samples=min_success_samples,
        )
        write_status(status_path, run_id=run_id, state="running", report=partial, latest_sample=sample)
        if time.monotonic() >= deadline:
            break
        time.sleep(poll_interval_sec)

    report = evaluate_samples(
        samples,
        run_id=run_id,
        hub_url=hub_url,
        device_id=device_id,
        require_fresh=require_fresh,
        require_dashboard_markers=require_dashboard_markers,
        min_success_samples=min_success_samples,
    )
    report.update(
        {
            "started_at": samples[0]["collected_at"] if samples else None,
            "completed_at": utc_now(),
            "duration_sec": duration_sec,
            "poll_interval_sec": poll_interval_sec,
            "request_timeout_sec": request_timeout_sec,
            "require_fresh": require_fresh,
            "require_dashboard_markers": require_dashboard_markers,
            "report_path": str(report_path),
            "markdown_report_path": str(markdown_path),
            "samples_path": str(samples_path),
            "status_path": str(status_path),
        }
    )
    write_json(report_path, report)
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    write_status(status_path, run_id=run_id, state="completed", report=report, latest_sample=samples[-1] if samples else None)
    if report["result"] == "FAIL":
        raise FieldValidationError("; ".join(report["errors"]))
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hub", default=DEFAULT_HUB_URL)
    parser.add_argument("--device-id", default="ego-link-r1-connectivity-001")
    parser.add_argument("--token-env", default="EGOLINK_MESSAGE_HUB_TOKEN")
    parser.add_argument("--token-file", type=Path, default=DEFAULT_TOKEN_FILE)
    parser.add_argument("--run-id", default=f"field-readiness-{compact_utc_now()}")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--duration-sec", type=float, default=0.0)
    parser.add_argument("--poll-interval-sec", type=float, default=15.0)
    parser.add_argument("--request-timeout-sec", type=float, default=10.0)
    parser.add_argument("--min-success-samples", type=int, default=1)
    parser.add_argument("--allow-not-ready", action="store_true")
    parser.add_argument("--allow-missing-dashboard-markers", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = args.output_dir or DEFAULT_OUTPUT_ROOT / args.run_id
    try:
        report = observe_field_readiness(
            hub_url=args.hub,
            device_id=args.device_id,
            token=read_token(args.token_env, args.token_file),
            run_id=args.run_id,
            output_dir=output_dir,
            duration_sec=args.duration_sec,
            poll_interval_sec=args.poll_interval_sec,
            request_timeout_sec=args.request_timeout_sec,
            require_fresh=not args.allow_not_ready,
            require_dashboard_markers=not args.allow_missing_dashboard_markers,
            min_success_samples=args.min_success_samples,
        )
    except FieldValidationError as exc:
        print(f"FAIL field readiness observation: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        latest = as_dict(report.get("latest"))
        readiness = as_dict(latest.get("field_readiness"))
        print(
            "PASS field readiness observation "
            f"run_id={report['run_id']} device={report.get('device_id')} "
            f"ready={latest.get('field_ready')} reason={readiness.get('reason')}"
        )
        print(f"Report: {report['markdown_report_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

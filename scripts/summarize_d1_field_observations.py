"""Build a bounded local index for D1 field-observation runs.

This command scans local observer output directories and writes a compact
JSON/Markdown index. It does not contact hardware, call the Message Hub, send
commands, deploy code, or read `d1_field_samples.jsonl` contents.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Mapping

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import observe_d1_field_run


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = REPO_ROOT / "reports" / "d1_field_observation"
DEFAULT_OUTPUT_DIR = DEFAULT_ROOT / "index"
INDEX_JSON = "d1_field_observation_index.json"
INDEX_MARKDOWN = "d1_field_observation_index.md"
INDEX_VERSION = "D1.field_observation_index.v1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return payload


def relative_path(path: Path, *, root: Path) -> str:
    resolved = path.resolve()
    for base in (REPO_ROOT.resolve(), root.resolve().parent):
        try:
            return resolved.relative_to(base).as_posix()
        except ValueError:
            continue
    return path.name


def mtime_iso(path: Path | None) -> str | None:
    if path is None or not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


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


def summarize_completed_report(report: Mapping[str, Any], *, report_path: Path, root: Path) -> dict[str, Any]:
    summary = as_dict(report.get("summary"))
    markdown_path = report_path.with_name(observe_d1_field_run.REPORT_MARKDOWN)
    status_path = report_path.with_name(observe_d1_field_run.STATUS_JSON)
    return {
        "source": "report",
        "run_id": report.get("run_id") or report_path.parent.name,
        "status": "completed",
        "result": report.get("result"),
        "updated_at": mtime_iso(report_path),
        "created_at": report.get("created_at"),
        "device_id": report.get("device_id"),
        "sample_count": int_or_none(summary.get("sample_count")),
        "planned_sample_count": None,
        "successful_sample_count": int_or_none(summary.get("successful_sample_count")),
        "fetch_error_count": int_or_none(summary.get("fetch_error_count")),
        "latest_seq": int_or_none(summary.get("last_seq")),
        "latest_freshness_s": number_or_none(summary.get("max_freshness_s")),
        "latest_location_upload_at": summary.get("last_location_upload_at"),
        "latest_d1_status": None,
        "coordinate_sample_count": int_or_none(summary.get("coordinate_sample_count")),
        "raw_post_success_delta": int_or_none(summary.get("raw_post_success_delta")),
        "raw_post_failure_delta": int_or_none(summary.get("raw_post_failure_delta")),
        "location_event_count_delta": int_or_none(summary.get("location_event_count_delta")),
        "power_sample_count_delta": int_or_none(summary.get("power_sample_count_delta")),
        "report_path": relative_path(report_path, root=root),
        "markdown_report_path": relative_path(markdown_path, root=root) if markdown_path.exists() else None,
        "status_path": relative_path(status_path, root=root) if status_path.exists() else None,
        "warnings": list(as_list(report.get("warnings"))),
        "errors": list(as_list(report.get("errors"))),
    }


def summarize_live_status(status: Mapping[str, Any], *, status_path: Path, root: Path) -> dict[str, Any]:
    report_path = status_path.with_name(observe_d1_field_run.REPORT_JSON)
    markdown_path = status_path.with_name(observe_d1_field_run.REPORT_MARKDOWN)
    return {
        "source": "status",
        "run_id": status.get("run_id") or status_path.parent.name,
        "status": status.get("status") or "running",
        "result": status.get("result"),
        "updated_at": status.get("updated_at") or mtime_iso(status_path),
        "created_at": None,
        "device_id": status.get("device_id"),
        "sample_count": int_or_none(status.get("sample_count")),
        "planned_sample_count": int_or_none(status.get("planned_sample_count")),
        "successful_sample_count": int_or_none(status.get("successful_sample_count")),
        "fetch_error_count": int_or_none(status.get("fetch_error_count")),
        "latest_seq": int_or_none(status.get("latest_seq")),
        "latest_freshness_s": number_or_none(status.get("latest_freshness_s")),
        "latest_location_upload_at": status.get("latest_location_upload_at"),
        "latest_d1_status": status.get("latest_d1_status"),
        "coordinate_sample_count": None,
        "raw_post_success_delta": None,
        "raw_post_failure_delta": None,
        "location_event_count_delta": None,
        "power_sample_count_delta": None,
        "report_path": relative_path(report_path, root=root) if report_path.exists() else None,
        "markdown_report_path": relative_path(markdown_path, root=root) if markdown_path.exists() else None,
        "status_path": relative_path(status_path, root=root),
        "warnings": [],
        "errors": [],
    }


def summarize_run(run_dir: Path, *, root: Path) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    report_path = run_dir / observe_d1_field_run.REPORT_JSON
    status_path = run_dir / observe_d1_field_run.STATUS_JSON
    if not report_path.is_file() and not status_path.is_file():
        return None, None
    try:
        if status_path.is_file():
            status = read_json(status_path)
            if str(status.get("status") or "").lower() == "running" or not report_path.is_file():
                return summarize_live_status(status, status_path=status_path, root=root), None
        report = read_json(report_path)
        return summarize_completed_report(report, report_path=report_path, root=root), None
    except Exception as exc:  # noqa: BLE001 - keep a bounded index even when one run is malformed.
        error = {
            "run_id": run_dir.name,
            "status": "error",
            "reason": "field_observation_index_read_failed",
            "error_type": type(exc).__name__,
            "message": str(exc),
            "path": relative_path(run_dir, root=root),
        }
        return None, error


def sort_key(item: Mapping[str, Any]) -> str:
    return str(item.get("updated_at") or item.get("created_at") or item.get("run_id") or "")


def build_index(*, root: Path, limit: int | None = None, generated_at: str | None = None) -> dict[str, Any]:
    runs: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    if root.is_dir():
        for run_dir in sorted((item for item in root.iterdir() if item.is_dir()), key=lambda item: item.name):
            if run_dir.name == "index":
                continue
            run, error = summarize_run(run_dir, root=root)
            if run:
                runs.append(run)
            if error:
                errors.append(error)
    runs.sort(key=sort_key, reverse=True)
    if limit is not None:
        runs = runs[:limit]
    running = [item for item in runs if item.get("status") == "running"]
    completed = [item for item in runs if item.get("status") == "completed"]
    warn_or_fail = [item for item in runs if item.get("result") in {"WARN", "FAIL"}]
    latest = runs[0] if runs else None
    return {
        "tool": "summarize_d1_field_observations",
        "index_version": INDEX_VERSION,
        "generated_at": generated_at or utc_now(),
        "root": relative_path(root, root=root),
        "status": "available" if runs else "not_available",
        "summary": {
            "run_count": len(runs),
            "running_count": len(running),
            "completed_count": len(completed),
            "warn_or_fail_count": len(warn_or_fail),
            "error_count": len(errors),
            "latest_run_id": latest.get("run_id") if latest else None,
            "latest_status": latest.get("status") if latest else None,
            "latest_result": latest.get("result") if latest else None,
            "latest_seq": latest.get("latest_seq") if latest else None,
            "latest_freshness_s": latest.get("latest_freshness_s") if latest else None,
        },
        "runs": runs,
        "errors": errors,
        "scope": {
            "hardware_contacted_directly": False,
            "message_hub_called": False,
            "commands_sent": False,
            "firmware_changed": False,
            "gitlab_modified": False,
            "samples_jsonl_read": False,
            "location_accuracy_claimed": False,
            "battery_life_claimed": False,
        },
    }


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_markdown(path: Path, payload: Mapping[str, Any]) -> None:
    summary = as_dict(payload.get("summary"))
    runs = [as_dict(item) for item in as_list(payload.get("runs"))]
    lines = [
        "# D1 Field Observation Index",
        "",
        f"- Generated: {payload.get('generated_at')}",
        f"- Runs: {summary.get('run_count')}",
        f"- Running: {summary.get('running_count')}",
        f"- Completed: {summary.get('completed_count')}",
        f"- Warn or fail: {summary.get('warn_or_fail_count')}",
        f"- Latest: {summary.get('latest_run_id')} / {summary.get('latest_status')} / {summary.get('latest_result')}",
        "",
        "## Runs",
        "",
        "| Run | Status | Result | Samples | Latest Seq | Freshness | Updated |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    if runs:
        for run in runs:
            lines.append(
                "| {run_id} | {status} | {result} | {samples} | {seq} | {freshness} | {updated} |".format(
                    run_id=run.get("run_id") or "",
                    status=run.get("status") or "",
                    result=run.get("result") or "",
                    samples=run.get("sample_count") if run.get("sample_count") is not None else "",
                    seq=run.get("latest_seq") if run.get("latest_seq") is not None else "",
                    freshness=run.get("latest_freshness_s") if run.get("latest_freshness_s") is not None else "",
                    updated=run.get("updated_at") or "",
                )
            )
    else:
        lines.append("| none |  |  |  |  |  |  |")
    lines.extend(
        [
            "",
            "## Boundaries",
            "",
            "- This index reads local status/report summaries only.",
            "- It does not read sample JSONL contents, contact hardware, call the Message Hub, send commands, deploy code, or modify GitLab.",
            "- It does not claim location accuracy, battery life, GNSS acceptance, LTE long-run acceptance, model readiness, or product readiness.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_index(payload: Mapping[str, Any], *, output_dir: Path) -> tuple[Path, Path]:
    json_path = output_dir / INDEX_JSON
    md_path = output_dir / INDEX_MARKDOWN
    write_json(json_path, payload)
    write_markdown(md_path, payload)
    return json_path, md_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--generated-at")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.limit is not None and args.limit <= 0:
        raise ValueError("--limit must be positive")
    payload = build_index(root=args.root, limit=args.limit, generated_at=args.generated_at)
    json_path, md_path = write_index(payload, output_dir=args.output_dir)
    payload = dict(payload)
    payload["index_path"] = relative_path(json_path, root=args.root)
    payload["markdown_index_path"] = relative_path(md_path, root=args.root)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        summary = as_dict(payload.get("summary"))
        print(
            "D1 field observation index: "
            f"{summary.get('run_count')} runs, {summary.get('running_count')} running -> {payload['index_path']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

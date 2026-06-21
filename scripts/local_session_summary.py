"""Build a small health summary for a local Ego Link supervised session."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pc_simulator import event_store


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVENT_LOG = REPO_ROOT / "pc_simulator" / "runtime" / "events.jsonl"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def compact_event(event: dict[str, Any]) -> dict[str, Any]:
    fields = [
        "event_type",
        "device_id",
        "seq",
        "ts",
        "received_at",
        "source",
        "source_event_type",
        "source_event_key",
        "risk_type",
        "risk_score",
        "recommended_action",
        "wifi_rssi",
        "free_heap_bytes",
        "fix",
        "gnss_state",
        "cmd",
    ]
    return {field: event[field] for field in fields if field in event}


def summarize_events(
    events: list[dict[str, Any]],
    *,
    event_log: Path,
    dashboard_url: str | None = None,
    broker: str | None = None,
    session_dir: Path | None = None,
    dashboard_pid: int | None = None,
    worker_pid: int | None = None,
) -> dict[str, Any]:
    counts = Counter(str(event.get("event_type", "unknown")) for event in events)
    latest_by_type: dict[str, dict[str, Any]] = {}
    for event in events:
        event_type = str(event.get("event_type", "unknown"))
        latest_by_type.setdefault(event_type, compact_event(event))

    safety_evaluations = [
        event for event in events if event.get("event_type") == "safety_evaluation"
    ]
    safety_events = [event for event in events if event.get("event_type") == "safety_event"]
    commands = [event for event in events if event.get("event_type") == "command_sent"]

    return {
        "generated_at": utc_now(),
        "event_log": str(event_log),
        "event_count": len(events),
        "counts": dict(sorted(counts.items())),
        "latest_by_type": latest_by_type,
        "latest_events": [compact_event(event) for event in events[:8]],
        "safety": {
            "evaluations": len(safety_evaluations),
            "safety_events": len(safety_events),
            "commands": len(commands),
            "latest_risk_type": str(safety_evaluations[0].get("risk_type", "none"))
            if safety_evaluations
            else "none",
            "latest_action": str(safety_evaluations[0].get("recommended_action", "ignore"))
            if safety_evaluations
            else "ignore",
        },
        "processes": {
            "dashboard_pid": dashboard_pid,
            "worker_pid": worker_pid,
        },
        "endpoints": {
            "dashboard_url": dashboard_url,
            "broker": broker,
        },
        "session_dir": str(session_dir) if session_dir is not None else None,
    }


def render_markdown(report: dict[str, Any]) -> str:
    counts = report.get("counts", {})
    safety = report.get("safety", {})
    processes = report.get("processes", {})
    endpoints = report.get("endpoints", {})
    latest_events = report.get("latest_events", [])

    lines = [
        "# Ego Link Local Session Summary",
        "",
        f"- Generated: `{report.get('generated_at')}`",
        f"- Dashboard: `{endpoints.get('dashboard_url') or 'not configured'}`",
        f"- Broker: `{endpoints.get('broker') or 'not configured'}`",
        f"- Dashboard PID: `{processes.get('dashboard_pid') or 'unknown'}`",
        f"- MQTT Safety worker PID: `{processes.get('worker_pid') or 'unknown'}`",
        f"- Event log: `{report.get('event_log')}`",
        f"- Recent events scanned: `{report.get('event_count', 0)}`",
        "",
        "## Safety",
        "",
        f"- Evaluations: `{safety.get('evaluations', 0)}`",
        f"- Safety events: `{safety.get('safety_events', 0)}`",
        f"- Simulated commands: `{safety.get('commands', 0)}`",
        f"- Latest risk: `{safety.get('latest_risk_type', 'none')}`",
        f"- Latest action: `{safety.get('latest_action', 'ignore')}`",
        "",
        "## Event Counts",
        "",
    ]
    if counts:
        for event_type, count in sorted(counts.items()):
            lines.append(f"- `{event_type}`: `{count}`")
    else:
        lines.append("- No events found.")

    lines.extend(["", "## Latest Events", ""])
    if latest_events:
        for event in latest_events[:8]:
            event_type = event.get("event_type", "unknown")
            seq = event.get("seq", "unknown")
            risk = event.get("risk_type")
            action = event.get("recommended_action")
            detail = f"seq={seq}"
            if risk is not None:
                detail += f", risk={risk}"
            if action is not None:
                detail += f", action={action}"
            lines.append(f"- `{event_type}` ({detail})")
    else:
        lines.append("- No events found.")

    return "\n".join(lines) + "\n"


def write_report_files(report: dict[str, Any], session_dir: Path) -> tuple[Path, Path]:
    session_dir.mkdir(parents=True, exist_ok=True)
    json_path = session_dir / "session_summary.json"
    markdown_path = session_dir / "session_summary.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def build_report_from_log(
    event_log: Path,
    *,
    limit: int = 40,
    dashboard_url: str | None = None,
    broker: str | None = None,
    session_dir: Path | None = None,
    dashboard_pid: int | None = None,
    worker_pid: int | None = None,
) -> dict[str, Any]:
    events = event_store.load_recent(event_log, limit=limit)
    return summarize_events(
        events,
        event_log=event_log,
        dashboard_url=dashboard_url,
        broker=broker,
        session_dir=session_dir,
        dashboard_pid=dashboard_pid,
        worker_pid=worker_pid,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write a local Ego Link session summary.")
    parser.add_argument("--event-log", type=Path, default=DEFAULT_EVENT_LOG)
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--session-dir", type=Path, default=None)
    parser.add_argument("--dashboard-url", default=None)
    parser.add_argument("--broker", default=None)
    parser.add_argument("--dashboard-pid", type=int, default=None)
    parser.add_argument("--worker-pid", type=int, default=None)
    parser.add_argument("--json", action="store_true", help="Print JSON summary to stdout.")
    parser.add_argument("--markdown", action="store_true", help="Print Markdown summary to stdout.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report_from_log(
        args.event_log,
        limit=args.limit,
        dashboard_url=args.dashboard_url,
        broker=args.broker,
        session_dir=args.session_dir,
        dashboard_pid=args.dashboard_pid,
        worker_pid=args.worker_pid,
    )
    if args.session_dir is not None:
        write_report_files(report, args.session_dir)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.markdown:
        print(render_markdown(report), end="")
    if not args.json and not args.markdown and args.session_dir is None:
        print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

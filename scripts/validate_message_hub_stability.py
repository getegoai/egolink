"""Observe USB-Free Message Hub stability without sending device commands.

This script talks only to the HTTP Message Hub. It does not flash firmware,
open serial ports, erase flash, or enqueue downlink commands. It is intended
for R3 preflight observation: confirm that a device keeps reporting through the
VPS path while USB is disconnected.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.validate_fw001_hw_loop import (  # noqa: E402
    DEFAULT_HUB_URL,
    DEFAULT_OUTPUT_ROOT,
    FieldValidationError,
    HubClient,
    compact_utc_now,
    parse_timestamp,
    utc_now,
    write_json,
)


def message_key(message: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(message.get("server_received_at") or ""),
        str(message.get("message_type") or ""),
        str(message.get("event_type") or ""),
        str(message.get("seq") or ""),
    )


def message_received_at(message: dict[str, Any]) -> datetime | None:
    return parse_timestamp(message.get("server_received_at"))


def seconds_since(timestamp_text: object, now: datetime) -> float | None:
    timestamp = parse_timestamp(timestamp_text)
    if timestamp is None:
        return None
    return max(0.0, (now - timestamp).total_seconds())


def sorted_messages(messages: dict[tuple[str, str, str, str], dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        messages.values(),
        key=lambda item: message_received_at(item) or datetime.min.replace(tzinfo=timezone.utc),
    )


def count_seq_regressions(messages: list[dict[str, Any]]) -> int:
    regressions = 0
    previous: int | None = None
    for message in messages:
        seq = message.get("seq")
        if not isinstance(seq, int):
            continue
        if previous is not None and seq < previous:
            regressions += 1
        previous = seq
    return regressions


def max_message_gap_sec(messages: list[dict[str, Any]]) -> float | None:
    previous: datetime | None = None
    max_gap: float | None = None
    for message in messages:
        received_at = message_received_at(message)
        if received_at is None:
            continue
        if previous is not None:
            gap = max(0.0, (received_at - previous).total_seconds())
            max_gap = gap if max_gap is None else max(max_gap, gap)
        previous = received_at
    return max_gap


def summarize_messages(messages: list[dict[str, Any]]) -> dict[str, Any]:
    type_counts: Counter[str] = Counter()
    event_counts: Counter[str] = Counter()
    seqs: list[int] = []
    for message in messages:
        message_type = str(message.get("message_type") or "unknown")
        event_type = str(message.get("event_type") or "")
        type_counts[message_type] += 1
        if event_type:
            event_counts[event_type] += 1
        seq = message.get("seq")
        if isinstance(seq, int):
            seqs.append(seq)
    latest = messages[-1] if messages else {}
    latest_location = next((m for m in reversed(messages) if m.get("event_type") == "location_report"), {})
    return {
        "observed_message_count": len(messages),
        "message_type_counts": dict(sorted(type_counts.items())),
        "event_type_counts": dict(sorted(event_counts.items())),
        "first_seq": seqs[0] if seqs else None,
        "last_seq": seqs[-1] if seqs else None,
        "seq_regressions": count_seq_regressions(messages),
        "max_message_gap_sec": max_message_gap_sec(messages),
        "latest_message": latest,
        "latest_location": latest_location,
    }


def write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    summary = report.get("summary") or {}
    latest = summary.get("latest_message") or {}
    latest_location = summary.get("latest_location") or {}
    lines = [
        "# Message Hub Stability Observation Report",
        "",
        f"- Result: {report['result']}",
        f"- Observation ID: {report['observation_id']}",
        f"- Device ID: {report['device_id']}",
        f"- Board ID: {report['board_id']}",
        f"- Connection path: {report['connection_path']}",
        f"- Started at: {report['started_at']}",
        f"- Completed at: {report['completed_at']}",
        f"- Duration seconds: {report['duration_sec']}",
        f"- Hub: {report['hub_url']}",
        f"- Observed messages: {summary.get('observed_message_count', 0)}",
        f"- Message type counts: {summary.get('message_type_counts', {})}",
        f"- Event type counts: {summary.get('event_type_counts', {})}",
        f"- First seq: {summary.get('first_seq', 'unknown')}",
        f"- Last seq: {summary.get('last_seq', 'unknown')}",
        f"- Seq regressions: {summary.get('seq_regressions', 'unknown')}",
        f"- Max message gap sec: {summary.get('max_message_gap_sec', 'unknown')}",
        f"- Final last-seen age sec: {report.get('final_last_seen_age_sec', 'unknown')}",
        f"- Latest message: {latest.get('message_type', 'unknown')} / {latest.get('event_type', '')} seq={latest.get('seq', 'unknown')}",
        f"- Latest location: fix={latest_location.get('fix', 'unknown')} state={latest_location.get('gnss_state', 'unknown')}",
        "",
        "## Boundaries",
        "",
        "- This report is observation-only and does not enqueue device commands.",
        "- Passing this report does not prove outdoor GNSS fix, LTE data transport, battery accuracy, camera, audio, storage, or product power behavior.",
        "- USB-free runtime must be physically confirmed by the operator for the observed run.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def observe_stability(
    *,
    hub_url: str,
    device_id: str,
    token: str | None,
    output_dir: Path,
    observation_id: str,
    board_id: str,
    connection_path: str,
    duration_sec: float,
    poll_interval_sec: float,
    min_messages: int,
    max_last_seen_age_sec: float,
    max_message_gap_sec_value: float,
    expected_fw_version: str | None = None,
    expected_message_test_run_id: str | None = None,
    allow_seq_regression: bool = False,
) -> dict[str, Any]:
    client = HubClient(hub_url, token=token)
    started_at_text = utc_now()
    started_at = parse_timestamp(started_at_text)
    if started_at is None:
        raise FieldValidationError("failed to create observation start timestamp")

    health = client.get("/health")
    seen: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    device_snapshots: list[dict[str, Any]] = []
    deadline = time.monotonic() + duration_sec

    while True:
        try:
            device = client.get(f"/api/v1/devices/{device_id}").get("device") or {}
        except FieldValidationError:
            device = {}
        if isinstance(device, dict) and device:
            device_snapshots.append(device)
        try:
            history = client.get(f"/api/v1/devices/{device_id}/telemetry/history").get("telemetry") or []
        except FieldValidationError:
            history = []
        for item in history:
            if not isinstance(item, dict):
                continue
            received_at = message_received_at(item)
            if received_at is None or received_at < started_at:
                continue
            if expected_message_test_run_id and item.get("test_run_id") != expected_message_test_run_id:
                continue
            seen[message_key(item)] = item
        if time.monotonic() >= deadline:
            break
        time.sleep(poll_interval_sec)

    completed_at_text = utc_now()
    completed_at = parse_timestamp(completed_at_text)
    if completed_at is None:
        raise FieldValidationError("failed to create observation completion timestamp")
    final_device = device_snapshots[-1] if device_snapshots else {}
    messages = sorted_messages(seen)
    summary = summarize_messages(messages)
    final_last_seen_age = seconds_since(final_device.get("last_seen_at"), completed_at)

    errors: list[str] = []
    if summary["observed_message_count"] < min_messages:
        errors.append(f"observed {summary['observed_message_count']} messages; expected at least {min_messages}")
    if final_last_seen_age is None:
        errors.append("device last_seen_at was missing or invalid")
    elif final_last_seen_age > max_last_seen_age_sec:
        errors.append(
            f"final last_seen age {final_last_seen_age:.1f}s exceeded limit {max_last_seen_age_sec:.1f}s"
        )
    observed_max_gap = summary.get("max_message_gap_sec")
    if isinstance(observed_max_gap, (int, float)) and observed_max_gap > max_message_gap_sec_value:
        errors.append(f"max message gap {observed_max_gap:.1f}s exceeded limit {max_message_gap_sec_value:.1f}s")
    if summary.get("seq_regressions") and not allow_seq_regression:
        errors.append(f"observed {summary['seq_regressions']} sequence regression(s)")
    if expected_fw_version and final_device.get("fw_version") != expected_fw_version:
        errors.append(
            f"device fw_version={final_device.get('fw_version')} did not match expected {expected_fw_version}"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "stability_observation_report.json"
    markdown_path = output_dir / "stability_observation_report.md"
    messages_path = output_dir / "observed_messages.json"
    snapshots_path = output_dir / "device_snapshots.json"
    report = {
        "result": "PASS" if not errors else "FAIL",
        "hub_url": hub_url,
        "device_id": device_id,
        "board_id": board_id,
        "connection_path": connection_path,
        "observation_id": observation_id,
        "started_at": started_at_text,
        "completed_at": completed_at_text,
        "duration_sec": duration_sec,
        "poll_interval_sec": poll_interval_sec,
        "health": health,
        "final_device": final_device,
        "final_last_seen_age_sec": final_last_seen_age,
        "expected_fw_version": expected_fw_version,
        "expected_message_test_run_id": expected_message_test_run_id,
        "summary": summary,
        "errors": errors,
        "report_path": str(report_path),
        "markdown_report_path": str(markdown_path),
        "observed_messages_path": str(messages_path),
        "device_snapshots_path": str(snapshots_path),
    }
    write_json(messages_path, {"messages": messages})
    write_json(snapshots_path, {"devices": device_snapshots})
    write_json(report_path, report)
    write_markdown_report(markdown_path, report)

    if errors:
        raise FieldValidationError("; ".join(errors))
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hub", default=DEFAULT_HUB_URL)
    parser.add_argument("--device-id", default="ego-link-r1-connectivity-001")
    parser.add_argument("--token-env", default="EGOLINK_MESSAGE_HUB_TOKEN")
    parser.add_argument("--observation-id", default=f"stability-{compact_utc_now()}")
    parser.add_argument("--board-id", default="connectivity-node-001")
    parser.add_argument("--connection-path", default="independent_power_usb_disconnected")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--duration-sec", type=float, default=120.0)
    parser.add_argument("--poll-interval-sec", type=float, default=5.0)
    parser.add_argument("--min-messages", type=int, default=2)
    parser.add_argument("--max-last-seen-age-sec", type=float, default=60.0)
    parser.add_argument("--max-message-gap-sec", type=float, default=45.0)
    parser.add_argument("--expected-fw-version")
    parser.add_argument("--expected-message-test-run-id")
    parser.add_argument("--allow-seq-regression", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = args.output_dir or DEFAULT_OUTPUT_ROOT / args.observation_id
    try:
        report = observe_stability(
            hub_url=args.hub,
            device_id=args.device_id,
            token=os.environ.get(args.token_env) or None,
            output_dir=output_dir,
            observation_id=args.observation_id,
            board_id=args.board_id,
            connection_path=args.connection_path,
            duration_sec=args.duration_sec,
            poll_interval_sec=args.poll_interval_sec,
            min_messages=args.min_messages,
            max_last_seen_age_sec=args.max_last_seen_age_sec,
            max_message_gap_sec_value=args.max_message_gap_sec,
            expected_fw_version=args.expected_fw_version,
            expected_message_test_run_id=args.expected_message_test_run_id,
            allow_seq_regression=args.allow_seq_regression,
        )
    except FieldValidationError as exc:
        print(f"FAIL Message Hub stability observation: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        summary = report["summary"]
        print(
            "PASS Message Hub stability observation "
            f"device={report['device_id']} observation_id={report['observation_id']} "
            f"messages={summary['observed_message_count']}"
        )
        print(f"Report: {report['markdown_report_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

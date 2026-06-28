"""Validate the FW-002 request_location -> location_report Message Hub loop.

This script talks only to the HTTP Message Hub. It does not flash firmware,
open serial ports, erase flash, or send hardware control outside the normal
Message Hub command queue.
"""

from __future__ import annotations

import argparse
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
    wait_for_command_ack,
    wait_for_fresh_message,
    write_json,
)


LOCATION_SOURCE_STATUSES = {"verified", "observed", "pc_side_verified", "unverified"}


def is_fresh_location_report(
    message: dict[str, Any],
    started_at: datetime,
    *,
    test_run_id: str,
    cmd_id: str,
) -> bool:
    if message.get("message_type") != "event" or message.get("event_type") != "location_report":
        return False
    if message.get("test_run_id") != test_run_id:
        return False
    if str(message.get("location_request_cmd_id") or "") not in {"", cmd_id}:
        return False
    received_at = parse_timestamp(message.get("server_received_at"))
    return received_at is not None and received_at >= started_at


def validate_location_report(
    report: dict[str, Any],
    *,
    require_fix: bool,
) -> None:
    if "fix" not in report:
        raise FieldValidationError("location_report must explicitly include fix=true/false")
    fix = report.get("fix")
    if not isinstance(fix, bool):
        raise FieldValidationError("location_report fix field must be boolean")

    source_status = str(report.get("source_status") or "")
    if source_status not in LOCATION_SOURCE_STATUSES:
        raise FieldValidationError(
            "location_report source_status must be one of "
            + ", ".join(sorted(LOCATION_SOURCE_STATUSES))
        )

    gnss_state = str(report.get("gnss_state") or "")
    if not gnss_state:
        raise FieldValidationError("location_report must include gnss_state")

    if require_fix and not fix:
        raise FieldValidationError(f"location_report did not contain a real fix; gnss_state={gnss_state}")

    if fix:
        if report.get("lat") is None or report.get("lon") is None:
            raise FieldValidationError("fixed location_report must include lat and lon")
        if require_fix and source_status not in {"verified", "observed"}:
            raise FieldValidationError("fixed location_report must use verified or observed source_status")


def create_or_reuse_test_run(
    client: HubClient,
    *,
    test_run_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    try:
        return client.post("/api/v1/test-runs", payload)["test_run"]
    except FieldValidationError as exc:
        message = str(exc)
        if "UNIQUE constraint failed: test_runs.test_run_id" not in message:
            raise
    export = client.get(f"/api/v1/test-runs/{test_run_id}/export")
    test_run = export.get("test_run")
    if not isinstance(test_run, dict):
        raise FieldValidationError(f"existing test run {test_run_id} could not be loaded")
    reused = dict(test_run)
    reused["reused_existing"] = True
    return reused


def wait_for_location_report(
    client: HubClient,
    *,
    device_id: str,
    started_at: datetime,
    test_run_id: str,
    cmd_id: str,
    timeout_sec: float,
    poll_interval_sec: float,
    require_fix: bool,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_sec
    last_count = 0
    while True:
        history = client.get(f"/api/v1/devices/{device_id}/telemetry/history").get("telemetry") or []
        messages = [item for item in history if isinstance(item, dict)]
        last_count = len(messages)
        for message in messages:
            if is_fresh_location_report(message, started_at, test_run_id=test_run_id, cmd_id=cmd_id):
                validate_location_report(message, require_fix=False)
                return message
        if time.monotonic() >= deadline:
            raise FieldValidationError(
                f"timed out waiting for location_report from {device_id}; observed {last_count} recent messages"
            )
        time.sleep(poll_interval_sec)


def write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    location = report.get("location_report") or {}
    command = report.get("command") or {}
    heartbeat = report.get("fresh_heartbeat") or {}
    lines = [
        "# FW-002 GNSS Command/Telemetry Report",
        "",
        f"- Result: {report['result']}",
        f"- Test run ID: {report['test_run_id']}",
        f"- Device ID: {report['device_id']}",
        f"- Board ID: {report['board_id']}",
        f"- Connection path: {report['connection_path']}",
        f"- Started at: {report['started_at']}",
        f"- Completed at: {report['completed_at']}",
        f"- Hub: {report['hub_url']}",
        f"- Fresh heartbeat seq: {heartbeat.get('seq', 'unknown')}",
        f"- Command: {command.get('cmd', 'not sent')}",
        f"- Command ID: {command.get('cmd_id', 'not sent')}",
        f"- Command status: {command.get('status', 'not sent')}",
        f"- Location seq: {location.get('seq', 'unknown')}",
        f"- Location fix: {location.get('fix', 'unknown')}",
        f"- GNSS state: {location.get('gnss_state', 'unknown')}",
        f"- Source: {location.get('source', 'unknown')}",
        f"- Source status: {location.get('source_status', 'unknown')}",
        f"- GNSS source: {location.get('gnss_source', 'unknown')}",
        f"- GNSS driver: {location.get('gnss_driver', 'unknown')}",
        f"- GNSS query OK: {location.get('gnss_query_ok', 'unknown')}",
        f"- Errors: {', '.join(report.get('errors') or []) if report.get('errors') else 'none'}",
        f"- Test-run export path: {report.get('test_run_export_path', 'not written')}",
        "",
        "## Boundaries",
        "",
        "- This report proves the Message Hub command/telemetry observation path used by the script.",
        "- A no-fix report is acceptable for FW-002 prep and driver bring-up, but not for final R2 real-fix acceptance.",
        "- Use `--require-fix` only for an outdoor real-fix acceptance attempt.",
        "- Real GNSS fix, LTE module control, battery, camera, audio, storage, and product power behavior remain separate evidence gates.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_validation(
    *,
    hub_url: str,
    device_id: str,
    token: str | None,
    output_dir: Path,
    test_run_id: str,
    board_id: str,
    connection_path: str,
    timeout_sec: float,
    poll_interval_sec: float,
    require_fix: bool = False,
) -> dict[str, Any]:
    client = HubClient(hub_url, token=token)
    started_at_text = utc_now()
    started_at = parse_timestamp(started_at_text)
    if started_at is None:
        raise FieldValidationError("failed to create validation start timestamp")

    health = client.get("/health")
    test_run = create_or_reuse_test_run(
        client,
        test_run_id=test_run_id,
        payload={
            "test_run_id": test_run_id,
            "task_id": "FW-002",
            "board_id": board_id,
            "device_id": device_id,
            "connection_path": connection_path,
            "started_at": started_at_text,
            "status": "active",
            "goal": "request_location command produces explicit location_report over Message Hub",
        },
    )
    fresh_heartbeat = wait_for_fresh_message(
        client,
        device_id=device_id,
        started_at=started_at,
        message_type="status",
        timeout_sec=timeout_sec,
        poll_interval_sec=poll_interval_sec,
    )
    if fresh_heartbeat.get("test_run_id") != test_run_id:
        raise FieldValidationError(
            f"fresh heartbeat from {device_id} is missing expected test_run_id={test_run_id}; "
            "rebuild HTTP firmware with CONFIG_EGOLINK_TEST_RUN_ID set for this run"
        )

    created = client.post(
        f"/api/v1/devices/{device_id}/commands",
        {
            "cmd": "request_location",
            "test_run_id": test_run_id,
            "payload": {
                "reason": "fw002_location_validation",
                "test_run_id": test_run_id,
            },
        },
    )["command"]
    cmd_id = str(created["cmd_id"])
    location_report = wait_for_location_report(
        client,
        device_id=device_id,
        started_at=started_at,
        test_run_id=test_run_id,
        cmd_id=cmd_id,
        timeout_sec=timeout_sec,
        poll_interval_sec=poll_interval_sec,
        require_fix=require_fix,
    )
    command = wait_for_command_ack(
        client,
        device_id=device_id,
        cmd_id=cmd_id,
        timeout_sec=timeout_sec,
        poll_interval_sec=poll_interval_sec,
    )
    ack = command.get("ack") if isinstance(command.get("ack"), dict) else {}
    if ack.get("test_run_id") != test_run_id:
        raise FieldValidationError(f"ACK for command {cmd_id} is missing expected test_run_id={test_run_id}")

    errors: list[str] = []
    if require_fix:
        try:
            validate_location_report(location_report, require_fix=True)
        except FieldValidationError as exc:
            errors.append(str(exc))

    export = client.get(f"/api/v1/test-runs/{test_run_id}/export")
    output_dir.mkdir(parents=True, exist_ok=True)
    export_path = output_dir / "test_run_export.json"
    report_path = output_dir / "field_validation_report.json"
    markdown_path = output_dir / "field_validation_report.md"
    write_json(export_path, export)

    report = {
        "result": "FAIL" if errors else "PASS",
        "hub_url": hub_url,
        "device_id": device_id,
        "board_id": board_id,
        "connection_path": connection_path,
        "test_run_id": test_run_id,
        "started_at": started_at_text,
        "completed_at": utc_now(),
        "health": health,
        "test_run": test_run,
        "fresh_heartbeat": fresh_heartbeat,
        "command": command,
        "location_report": location_report,
        "require_fix": require_fix,
        "errors": errors,
        "test_run_export_path": str(export_path),
        "report_path": str(report_path),
        "markdown_report_path": str(markdown_path),
    }
    write_json(report_path, report)
    write_markdown_report(markdown_path, report)
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hub", default=DEFAULT_HUB_URL)
    parser.add_argument("--device-id", default="ego-link-r1-connectivity-001")
    parser.add_argument("--token-env", default="EGOLINK_MESSAGE_HUB_TOKEN")
    parser.add_argument("--test-run-id", default=f"fw002-location-{compact_utc_now()}")
    parser.add_argument("--board-id", default="connectivity-node-001")
    parser.add_argument("--connection-path", default="independent_power_usb_disconnected")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--timeout-sec", type=float, default=120.0)
    parser.add_argument("--poll-interval-sec", type=float, default=5.0)
    parser.add_argument("--require-fix", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = args.output_dir or DEFAULT_OUTPUT_ROOT / args.test_run_id
    try:
        report = run_validation(
            hub_url=args.hub,
            device_id=args.device_id,
            token=os.environ.get(args.token_env) or None,
            output_dir=output_dir,
            test_run_id=args.test_run_id,
            board_id=args.board_id,
            connection_path=args.connection_path,
            timeout_sec=args.timeout_sec,
            poll_interval_sec=args.poll_interval_sec,
            require_fix=args.require_fix,
        )
    except FieldValidationError as exc:
        print(f"FAIL FW-002 location validation: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        location = report["location_report"]
        print(
            f"{report['result']} FW-002 location validation "
            f"device={report['device_id']} test_run_id={report['test_run_id']} "
            f"fix={location.get('fix')} gnss_state={location.get('gnss_state')}"
        )
        print(f"Report: {report['markdown_report_path']}")
    return 0 if report.get("result") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Validate LTE-003 SIM7670G LTE HTTP command poll and ACK.

This script talks only to the HTTP Message Hub. It does not flash firmware,
open serial ports, erase flash, or use USB as a runtime data path. It enqueues
one harmless Message Hub command and waits for an LTE-marked ACK from the
device.
"""

from __future__ import annotations

import argparse
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
    utc_now,
    write_json,
)


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def is_2xx(value: object) -> bool:
    return isinstance(value, int) and 200 <= value < 300


def command_ack_summary(command: dict[str, Any]) -> dict[str, Any]:
    ack = as_dict(command.get("ack"))
    transport = as_dict(ack.get("transport"))
    lte_http = as_dict(ack.get("lte_http"))
    command_obs = as_dict(ack.get("command"))
    return {
        "cmd_id": command.get("cmd_id"),
        "cmd": command.get("cmd"),
        "command_status": command.get("status"),
        "ack_status": ack.get("status"),
        "ack_message": ack.get("message"),
        "ack_fw_version": ack.get("fw_version"),
        "ack_test_run_id": ack.get("test_run_id"),
        "transport_type": transport.get("type"),
        "transport_last_error": transport.get("last_error"),
        "poll_reason_code": lte_http.get("poll_reason_code"),
        "poll_status_code": lte_http.get("poll_status_code"),
        "poll_action_elapsed_ms": lte_http.get("poll_action_elapsed_ms"),
        "lte_http_phase": lte_http.get("phase"),
        "duplicate_local_execution_prevented": command_obs.get("duplicate_local_execution_prevented"),
    }


def ack_summary_errors(
    summary: dict[str, Any],
    *,
    expected_fw_version: str | None,
    expected_test_run_id: str,
) -> list[str]:
    errors: list[str] = []
    if summary.get("command_status") != "ok":
        errors.append(f"command status did not become ok; got {summary.get('command_status')}")
    if summary.get("ack_status") != "ok":
        errors.append(f"ACK status did not become ok; got {summary.get('ack_status')}")
    if expected_fw_version and summary.get("ack_fw_version") != expected_fw_version:
        errors.append(f"ACK fw_version={summary.get('ack_fw_version')} did not match expected {expected_fw_version}")
    if summary.get("ack_test_run_id") != expected_test_run_id:
        errors.append(
            f"ACK test_run_id={summary.get('ack_test_run_id')} did not match expected {expected_test_run_id}"
        )
    if summary.get("transport_type") != "lte":
        errors.append(f"ACK transport.type={summary.get('transport_type')} did not become lte")
    if summary.get("lte_http_phase") != "command_ack":
        errors.append(f"ACK lte_http.phase={summary.get('lte_http_phase')} did not become command_ack")
    if summary.get("poll_reason_code") != "LTE_HTTP_OK":
        errors.append(f"ACK poll_reason_code={summary.get('poll_reason_code')} did not become LTE_HTTP_OK")
    if not is_2xx(summary.get("poll_status_code")):
        errors.append(f"ACK poll_status_code={summary.get('poll_status_code')} was not 2xx")
    return errors


def find_command(commands: list[dict[str, Any]], cmd_id: str) -> dict[str, Any]:
    for command in commands:
        if command.get("cmd_id") == cmd_id:
            return command
    return {}


def write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    summary = report.get("ack_summary") or {}
    command = report.get("command") or {}
    lines = [
        "# LTE-003 LTE HTTP Command Loop Report",
        "",
        f"- Result: {report['result']}",
        f"- Test run ID: {report['test_run_id']}",
        f"- Device ID: {report['device_id']}",
        f"- Board ID: {report['board_id']}",
        f"- Connection path: {report['connection_path']}",
        f"- Started at: {report['started_at']}",
        f"- Completed at: {report['completed_at']}",
        f"- Hub: {report['hub_url']}",
        f"- Firmware: {summary.get('ack_fw_version', 'unknown')}",
        f"- Command: {command.get('cmd', 'not sent')}",
        f"- Command ID: {command.get('cmd_id', 'not sent')}",
        f"- Command status: {summary.get('command_status', 'unknown')}",
        f"- ACK status: {summary.get('ack_status', 'unknown')}",
        f"- ACK transport: {summary.get('transport_type', 'unknown')}",
        f"- Poll HTTP: {summary.get('poll_reason_code', 'unknown')} / {summary.get('poll_status_code', 'unknown')}",
        f"- Test-run export path: {report.get('test_run_export_path', 'not written')}",
        "",
        "## Errors",
        "",
    ]
    errors = report.get("errors") or []
    if errors:
        lines.extend(f"- {item}" for item in errors)
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Boundaries",
            "",
            "- This report validates only the LTE HTTP command poll and ACK thin-slice.",
            "- Passing this report does not validate reconnect, long-run LTE stability, battery, power, or GNSS-over-LTE behavior.",
            "- The command is intentionally harmless: set_report_interval.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def create_or_reuse_test_run(
    client: HubClient,
    *,
    test_run_id: str,
    board_id: str,
    device_id: str,
    connection_path: str,
    started_at: str,
) -> dict[str, Any]:
    payload = {
        "test_run_id": test_run_id,
        "task_id": "LTE-003",
        "board_id": board_id,
        "device_id": device_id,
        "connection_path": connection_path,
        "started_at": started_at,
        "status": "active",
        "goal": "USB-Free SIM7670G LTE HTTP command poll and ACK",
    }
    try:
        return client.post("/api/v1/test-runs", payload)["test_run"]
    except FieldValidationError as exc:
        if "UNIQUE constraint failed: test_runs.test_run_id" not in str(exc):
            raise
        return as_dict(client.get(f"/api/v1/test-runs/{test_run_id}/export").get("test_run"))


def validate_lte_command_loop(
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
    expected_fw_version: str | None,
    command_name: str,
    interval_ms: int,
    existing_command_id: str | None = None,
) -> dict[str, Any]:
    client = HubClient(hub_url, token=token)
    started_at_text = utc_now()
    health = client.get("/health")
    test_run = create_or_reuse_test_run(
        client,
        test_run_id=test_run_id,
        board_id=board_id,
        device_id=device_id,
        connection_path=connection_path,
        started_at=started_at_text,
    )
    if existing_command_id:
        commands = [
            item
            for item in (client.get(f"/api/v1/devices/{device_id}/commands").get("commands") or [])
            if isinstance(item, dict)
        ]
        created = find_command(commands, existing_command_id)
        if not created:
            raise FieldValidationError(f"existing command {existing_command_id} was not found for {device_id}")
    else:
        created = client.post(
            f"/api/v1/devices/{device_id}/commands",
            {
                "cmd": command_name,
                "test_run_id": test_run_id,
                "payload": {
                    "interval_ms": interval_ms,
                    "test_run_id": test_run_id,
                    "source": "lte003_command_validation",
                },
            },
        )["command"]
    cmd_id = str(created["cmd_id"])
    deadline = time.monotonic() + timeout_sec
    final_command: dict[str, Any] = created
    final_commands: list[dict[str, Any]] = []
    final_device: dict[str, Any] = {}
    summary: dict[str, Any] = command_ack_summary(created)
    errors: list[str] = [f"command {cmd_id} remained pending"]

    while True:
        try:
            final_device = as_dict(client.get(f"/api/v1/devices/{device_id}").get("device"))
        except FieldValidationError:
            final_device = {}
        final_commands = [
            item
            for item in (client.get(f"/api/v1/devices/{device_id}/commands").get("commands") or [])
            if isinstance(item, dict)
        ]
        final_command = find_command(final_commands, cmd_id) or final_command
        summary = command_ack_summary(final_command)
        status = str(final_command.get("status") or "")
        if status == "ok":
            errors = ack_summary_errors(
                summary,
                expected_fw_version=expected_fw_version,
                expected_test_run_id=test_run_id,
            )
            if not errors:
                break
        elif status not in {"pending", ""}:
            errors = [f"command {cmd_id} finished with non-ok status: {status}"]
            break
        if time.monotonic() >= deadline:
            errors = [f"timed out waiting for LTE ACK for command {cmd_id}", *ack_summary_errors(
                summary,
                expected_fw_version=expected_fw_version,
                expected_test_run_id=test_run_id,
            )]
            break
        time.sleep(poll_interval_sec)

    completed_at_text = utc_now()
    result = "PASS" if not errors else "FAIL"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "lte_command_loop_report.json"
    markdown_path = output_dir / "lte_command_loop_report.md"
    device_path = output_dir / "device_state.json"
    commands_path = output_dir / "commands.json"
    export_path = output_dir / "test_run_export.json"
    export = client.get(f"/api/v1/test-runs/{test_run_id}/export")
    report = {
        "result": result,
        "hub_url": hub_url,
        "device_id": device_id,
        "board_id": board_id,
        "connection_path": connection_path,
        "test_run_id": test_run_id,
        "started_at": started_at_text,
        "completed_at": completed_at_text,
        "expected_fw_version": expected_fw_version,
        "existing_command_id": existing_command_id,
        "health": health,
        "test_run": test_run,
        "command": final_command,
        "ack_summary": summary,
        "errors": errors,
        "device_state_path": str(device_path),
        "commands_path": str(commands_path),
        "test_run_export_path": str(export_path),
        "report_path": str(report_path),
        "markdown_report_path": str(markdown_path),
    }
    write_json(device_path, {"device": final_device})
    write_json(commands_path, {"commands": final_commands})
    write_json(export_path, export)
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
    parser.add_argument("--test-run-id", default=f"lte003-{compact_utc_now()}")
    parser.add_argument("--board-id", default="connectivity-node-001")
    parser.add_argument("--connection-path", default="independent_power_usb_disconnected")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--timeout-sec", type=float, default=240.0)
    parser.add_argument("--poll-interval-sec", type=float, default=5.0)
    parser.add_argument("--expected-fw-version", default="0.1.0-lte003-command-loop")
    parser.add_argument("--command", default="set_report_interval")
    parser.add_argument("--interval-ms", type=int, default=10000)
    parser.add_argument(
        "--existing-command-id",
        help="Wait for an already queued command instead of creating a new command.",
    )
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = args.output_dir or DEFAULT_OUTPUT_ROOT / args.test_run_id
    try:
        report = validate_lte_command_loop(
            hub_url=args.hub,
            device_id=args.device_id,
            token=os.environ.get(args.token_env) or None,
            output_dir=output_dir,
            test_run_id=args.test_run_id,
            board_id=args.board_id,
            connection_path=args.connection_path,
            timeout_sec=args.timeout_sec,
            poll_interval_sec=args.poll_interval_sec,
            expected_fw_version=args.expected_fw_version,
            command_name=args.command,
            interval_ms=args.interval_ms,
            existing_command_id=args.existing_command_id,
        )
    except FieldValidationError as exc:
        print(f"FAIL LTE-003 command loop validation: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            "PASS LTE-003 command loop validation "
            f"device={report['device_id']} cmd_id={report['ack_summary']['cmd_id']}"
        )
        print(f"Report: {report['markdown_report_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

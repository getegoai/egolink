"""Validate the FW-001 R1 USB-Free heartbeat and ACK loop.

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
from urllib import error, request


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HUB_URL = "http://127.0.0.1:8790"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "reports" / "field_validation"


class FieldValidationError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def compact_utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")


def parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


class HubClient:
    def __init__(self, base_url: str, *, token: str | None = None, timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def get(self, path: str) -> dict[str, Any]:
        req = request.Request(self.base_url + path, headers=self.headers(), method="GET")
        return self.open(req)

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = self.headers()
        headers["Content-Type"] = "application/json"
        req = request.Request(self.base_url + path, data=body, headers=headers, method="POST")
        return self.open(req)

    def open(self, req: request.Request) -> dict[str, Any]:
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise FieldValidationError(f"message hub returned HTTP {exc.code}: {detail}") from exc
        except error.URLError as exc:
            raise FieldValidationError(f"message hub request failed: {exc}") from exc
        if not isinstance(payload, dict):
            raise FieldValidationError("message hub response must be a JSON object")
        return payload


def is_fresh_message(message: dict[str, Any], started_at: datetime, *, message_type: str) -> bool:
    if message.get("message_type") != message_type:
        return False
    received_at = parse_timestamp(message.get("server_received_at"))
    return received_at is not None and received_at >= started_at


def wait_for_fresh_message(
    client: HubClient,
    *,
    device_id: str,
    started_at: datetime,
    message_type: str,
    timeout_sec: float,
    poll_interval_sec: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_sec
    last_count = 0
    while True:
        history = client.get(f"/api/v1/devices/{device_id}/telemetry/history").get("telemetry") or []
        messages = [item for item in history if isinstance(item, dict)]
        last_count = len(messages)
        for message in messages:
            if is_fresh_message(message, started_at, message_type=message_type):
                return message
        if time.monotonic() >= deadline:
            raise FieldValidationError(
                f"timed out waiting for fresh {message_type} from {device_id}; observed {last_count} recent messages"
            )
        time.sleep(poll_interval_sec)


def wait_for_command_ack(
    client: HubClient,
    *,
    device_id: str,
    cmd_id: str,
    timeout_sec: float,
    poll_interval_sec: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_sec
    while True:
        commands = client.get(f"/api/v1/devices/{device_id}/commands").get("commands") or []
        for command in commands:
            if isinstance(command, dict) and command.get("cmd_id") == cmd_id:
                status = str(command.get("status") or "")
                if status == "ok":
                    return command
                if status not in {"pending", ""}:
                    raise FieldValidationError(f"command {cmd_id} finished with non-ok status: {status}")
        if time.monotonic() >= deadline:
            raise FieldValidationError(f"timed out waiting for ACK for command {cmd_id}")
        time.sleep(poll_interval_sec)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    command = report.get("command") or {}
    heartbeat = report.get("fresh_heartbeat") or {}
    lines = [
        "# FW-001-HW R1 USB-Free Validation Report",
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
        f"- Test-run export path: {report.get('test_run_export_path', 'not written')}",
        "",
        "## Boundaries",
        "",
        "- This report proves only the Message Hub observation path used by the script.",
        "- USB-free runtime must be confirmed by the operator during the physical run.",
        "- GNSS, LTE module control, battery, camera, audio, and product power behavior are not proven by FW-001-HW.",
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
    command_name: str,
    interval_ms: int,
    create_command: bool = True,
) -> dict[str, Any]:
    client = HubClient(hub_url, token=token)
    started_at_text = utc_now()
    started_at = parse_timestamp(started_at_text)
    if started_at is None:
        raise FieldValidationError("failed to create validation start timestamp")

    health = client.get("/health")
    test_run = client.post(
        "/api/v1/test-runs",
        {
            "test_run_id": test_run_id,
            "task_id": "FW-001-HW",
            "board_id": board_id,
            "device_id": device_id,
            "connection_path": connection_path,
            "started_at": started_at_text,
            "status": "active",
            "goal": "R1 USB-Free heartbeat and command ACK over Message Hub",
        },
    )["test_run"]
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

    command: dict[str, Any] | None = None
    if create_command:
        created = client.post(
            f"/api/v1/devices/{device_id}/commands",
            {
                "cmd": command_name,
                "test_run_id": test_run_id,
                "payload": {
                    "interval_ms": interval_ms,
                    "test_run_id": test_run_id,
                    "source": "fw001_hw_validation",
                },
            },
        )["command"]
        command = wait_for_command_ack(
            client,
            device_id=device_id,
            cmd_id=str(created["cmd_id"]),
            timeout_sec=timeout_sec,
            poll_interval_sec=poll_interval_sec,
        )
        ack = command.get("ack") if isinstance(command.get("ack"), dict) else {}
        if ack.get("test_run_id") != test_run_id:
            raise FieldValidationError(
                f"ACK for command {command['cmd_id']} is missing expected test_run_id={test_run_id}"
            )

    export = client.get(f"/api/v1/test-runs/{test_run_id}/export")
    output_dir.mkdir(parents=True, exist_ok=True)
    export_path = output_dir / "test_run_export.json"
    report_path = output_dir / "field_validation_report.json"
    markdown_path = output_dir / "field_validation_report.md"
    write_json(export_path, export)

    report = {
        "result": "PASS",
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
    parser.add_argument("--test-run-id", default=f"fw001-hw-r1-{compact_utc_now()}")
    parser.add_argument("--board-id", default="connectivity-node-001")
    parser.add_argument("--connection-path", default="independent_power_usb_disconnected")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--timeout-sec", type=float, default=120.0)
    parser.add_argument("--poll-interval-sec", type=float, default=5.0)
    parser.add_argument("--command", default="set_report_interval")
    parser.add_argument("--interval-ms", type=int, default=10000)
    parser.add_argument("--no-command", action="store_true")
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
            command_name=args.command,
            interval_ms=args.interval_ms,
            create_command=not args.no_command,
        )
    except FieldValidationError as exc:
        print(f"FAIL FW-001-HW validation: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"PASS FW-001-HW validation device={report['device_id']} test_run_id={report['test_run_id']}")
        print(f"Report: {report['markdown_report_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

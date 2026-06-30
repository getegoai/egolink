"""Validate SIM7670G LTE HTTP command/report/ACK thin slices.

This script talks only to the HTTP Message Hub. It does not flash firmware,
open serial ports, erase flash, or use USB as a runtime data path. It enqueues
one Message Hub command and waits for LTE-marked evidence from the
device.
"""

from __future__ import annotations

import argparse
from datetime import datetime
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


LOCATION_SOURCE_STATUSES = {"verified", "observed", "pc_side_verified", "unverified"}


def is_fresh_location_report(
    message: dict[str, Any],
    started_at: datetime,
    *,
    expected_message_test_run_id: str,
    cmd_id: str,
) -> bool:
    if message.get("message_type") != "event" or message.get("event_type") != "location_report":
        return False
    if message.get("test_run_id") != expected_message_test_run_id:
        return False
    if str(message.get("location_request_cmd_id") or "") not in {"", cmd_id}:
        return False
    received_at = parse_timestamp(message.get("server_received_at"))
    return received_at is not None and received_at >= started_at


def is_fresh_location_observation(
    message: dict[str, Any],
    started_at: datetime,
    *,
    expected_message_test_run_id: str,
    cmd_id: str,
) -> bool:
    if message.get("message_type") != "event" or message.get("event_type") != "location_observation":
        return False
    if message.get("test_run_id") != expected_message_test_run_id:
        return False
    if str(message.get("location_request_cmd_id") or "") not in {"", cmd_id}:
        return False
    received_at = parse_timestamp(message.get("server_received_at"))
    return received_at is not None and received_at >= started_at


def validate_location_report(report: dict[str, Any], *, require_fix: bool) -> list[str]:
    errors: list[str] = []
    if "fix" not in report:
        errors.append("location_report must explicitly include fix=true/false")
    elif not isinstance(report.get("fix"), bool):
        errors.append("location_report fix field must be boolean")

    source_status = str(report.get("source_status") or "")
    if source_status not in LOCATION_SOURCE_STATUSES:
        errors.append(
            "location_report source_status must be one of " + ", ".join(sorted(LOCATION_SOURCE_STATUSES))
        )

    gnss_state = str(report.get("gnss_state") or "")
    if not gnss_state:
        errors.append("location_report must include gnss_state")

    if require_fix and report.get("fix") is not True:
        errors.append(f"location_report did not contain a real fix; gnss_state={gnss_state}")
    if report.get("fix") is True:
        if report.get("lat") is None or report.get("lon") is None:
            errors.append("fixed location_report must include lat and lon")
        if require_fix and source_status not in {"verified", "observed"}:
            errors.append("fixed location_report must use verified or observed source_status")

    transport = as_dict(report.get("transport"))
    if transport.get("type") != "lte":
        errors.append(f"location_report transport.type={transport.get('type')} did not become lte")
    return errors


def validate_location_observation(observation: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    source_status = str(observation.get("source_status") or "")
    if source_status not in LOCATION_SOURCE_STATUSES:
        errors.append(
            "location_observation source_status must be one of "
            + ", ".join(sorted(LOCATION_SOURCE_STATUSES))
        )

    cell = as_dict(observation.get("cell"))
    lte = as_dict(observation.get("lte"))
    if not cell:
        errors.append("location_observation must include a cell object")
    if not lte:
        errors.append("location_observation must include an lte object")
    if not cell.get("rat"):
        errors.append("location_observation.cell.rat is required")
    if not first_present(cell.get("cell_id"), cell.get("tac"), cell.get("registration_state")):
        errors.append("location_observation.cell must include cell_id, tac, or registration_state")
    if not first_present(lte.get("reason_code"), cell.get("reason_code")):
        errors.append("location_observation must include an LTE reason_code")

    transport = as_dict(observation.get("transport"))
    if transport.get("type") != "lte":
        errors.append(f"location_observation transport.type={transport.get('type')} did not become lte")
    lte_http = as_dict(observation.get("lte_http"))
    if lte_http.get("phase") != "location_observation":
        errors.append(f"location_observation lte_http.phase={lte_http.get('phase')} did not become location_observation")
    return errors


def first_present(*values: object) -> object | None:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def wait_for_location_report(
    client: HubClient,
    *,
    device_id: str,
    started_at: datetime,
    expected_message_test_run_id: str,
    cmd_id: str,
    timeout_sec: float,
    poll_interval_sec: float,
    require_fix: bool,
) -> tuple[dict[str, Any], list[str]]:
    deadline = time.monotonic() + timeout_sec
    last_count = 0
    while True:
        history = client.get(f"/api/v1/devices/{device_id}/telemetry/history").get("telemetry") or []
        messages = [item for item in history if isinstance(item, dict)]
        last_count = len(messages)
        for message in messages:
            if is_fresh_location_report(
                message,
                started_at,
                expected_message_test_run_id=expected_message_test_run_id,
                cmd_id=cmd_id,
            ):
                return message, validate_location_report(message, require_fix=require_fix)
        if time.monotonic() >= deadline:
            return {}, [f"timed out waiting for LTE location_report from {device_id}; observed {last_count} recent messages"]
        time.sleep(poll_interval_sec)


def wait_for_location_observation(
    client: HubClient,
    *,
    device_id: str,
    started_at: datetime,
    expected_message_test_run_id: str,
    cmd_id: str,
    timeout_sec: float,
    poll_interval_sec: float,
) -> tuple[dict[str, Any], list[str]]:
    deadline = time.monotonic() + timeout_sec
    last_count = 0
    while True:
        history = client.get(f"/api/v1/devices/{device_id}/telemetry/history").get("telemetry") or []
        messages = [item for item in history if isinstance(item, dict)]
        last_count = len(messages)
        for message in messages:
            if is_fresh_location_observation(
                message,
                started_at,
                expected_message_test_run_id=expected_message_test_run_id,
                cmd_id=cmd_id,
            ):
                return message, validate_location_observation(message)
        if time.monotonic() >= deadline:
            return {}, [
                f"timed out waiting for LTE location_observation from {device_id}; observed {last_count} recent messages"
            ]
        time.sleep(poll_interval_sec)


def ack_summary_errors(
    summary: dict[str, Any],
    *,
    expected_fw_version: str | None,
    expected_test_run_id: str,
    expected_ack_test_run_id: str | None = None,
) -> list[str]:
    errors: list[str] = []
    effective_ack_test_run_id = expected_ack_test_run_id or expected_test_run_id
    if summary.get("command_status") != "ok":
        errors.append(f"command status did not become ok; got {summary.get('command_status')}")
    if summary.get("ack_status") != "ok":
        errors.append(f"ACK status did not become ok; got {summary.get('ack_status')}")
    if expected_fw_version and summary.get("ack_fw_version") != expected_fw_version:
        errors.append(f"ACK fw_version={summary.get('ack_fw_version')} did not match expected {expected_fw_version}")
    if summary.get("ack_test_run_id") != effective_ack_test_run_id:
        errors.append(
            "ACK test_run_id="
            f"{summary.get('ack_test_run_id')} did not match expected ACK test_run_id {effective_ack_test_run_id}"
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


def resolve_evidence_start(
    *,
    evidence_since: str,
    validation_started_at: datetime,
    validation_started_at_text: str,
    command: dict[str, Any],
    test_run: dict[str, Any],
) -> tuple[datetime, str, str]:
    candidates = {
        "command_created": command.get("created_at"),
        "test_run_created": test_run.get("created_at") or test_run.get("started_at"),
        "validator_start": validation_started_at_text,
    }
    selected = candidates.get(evidence_since)
    parsed = parse_timestamp(selected)
    if parsed is not None:
        return parsed, str(selected), evidence_since
    return validation_started_at, validation_started_at_text, f"{evidence_since}_fallback_validator_start"


def get_device_state(client: HubClient, device_id: str) -> dict[str, Any]:
    try:
        return as_dict(client.get(f"/api/v1/devices/{device_id}").get("device"))
    except FieldValidationError:
        return {}


def list_device_commands(client: HubClient, device_id: str) -> list[dict[str, Any]]:
    return [
        item
        for item in (client.get(f"/api/v1/devices/{device_id}/commands").get("commands") or [])
        if isinstance(item, dict)
    ]


def write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    summary = report.get("ack_summary") or {}
    command = report.get("command") or {}
    location = report.get("location_report") or {}
    observation = report.get("location_observation") or {}
    observation_cell = as_dict(observation.get("cell"))
    observation_lte = as_dict(observation.get("lte"))
    command_name = str(command.get("cmd") or "unknown")
    lines = [
        "# LTE HTTP Command Loop Report",
        "",
        f"- Result: {report['result']}",
        f"- Test run ID: {report['test_run_id']}",
        f"- Device ID: {report['device_id']}",
        f"- Board ID: {report['board_id']}",
        f"- Connection path: {report['connection_path']}",
        f"- Started at: {report['started_at']}",
        f"- Completed at: {report['completed_at']}",
        f"- Evidence since: {report.get('evidence_started_at', 'unknown')} ({report.get('evidence_since_resolution', 'unknown')})",
        f"- Hub: {report['hub_url']}",
        f"- Firmware: {summary.get('ack_fw_version', 'unknown')}",
        f"- Expected ACK test run ID: {report.get('effective_expected_ack_test_run_id', 'unknown')}",
        f"- Expected message test run ID: {report.get('effective_expected_message_test_run_id', 'unknown')}",
        f"- Command: {command.get('cmd', 'not sent')}",
        f"- Command ID: {command.get('cmd_id', 'not sent')}",
        f"- Command status: {summary.get('command_status', 'unknown')}",
        f"- ACK status: {summary.get('ack_status', 'unknown')}",
        f"- ACK transport: {summary.get('transport_type', 'unknown')}",
        f"- Poll HTTP: {summary.get('poll_reason_code', 'unknown')} / {summary.get('poll_status_code', 'unknown')}",
        f"- Location seq: {location.get('seq', 'not required')}",
        f"- Location fix: {location.get('fix', 'not required')}",
        f"- GNSS state: {location.get('gnss_state', 'not required')}",
        f"- Location transport: {as_dict(location.get('transport')).get('type', 'not required')}",
        f"- Observation seq: {observation.get('seq', 'not required')}",
        f"- Observation cell: {observation_cell.get('rat', 'not required')} / {observation_cell.get('cell_id', 'unknown')}",
        f"- Observation LTE reason: {observation_lte.get('reason_code', 'not required')}",
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
            "- This report validates only the LTE HTTP command/report/ACK thin-slice.",
            "- Passing this report does not validate reconnect, long-run LTE stability, battery, power, or GNSS-over-LTE behavior.",
            f"- Command under validation: `{command_name}`.",
        ]
    )
    if command_name == "set_report_interval":
        lines.append("- The command is intentionally harmless: set_report_interval.")
    elif command_name == "request_location":
        lines.append(
            "- request_location validates command-scoped location_report transport only; GNSS fix requires --require-fix."
        )
        if report.get("require_location_observation"):
            lines.append("- location_observation validates command-scoped firmware-side cell/LTE evidence.")
    if report.get("arm_only"):
        lines.append("- Arm-only mode enqueued or selected the command but did not wait for runtime evidence.")
        lines.append("- Reconcile with the same command ID after the operator reboots the USB-disconnected device.")
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
    expected_ack_test_run_id: str | None = None,
    require_location_report: bool = False,
    require_location_observation: bool = False,
    require_fix: bool = False,
    expected_message_test_run_id: str | None = None,
    evidence_since: str = "command_created",
    arm_only: bool = False,
) -> dict[str, Any]:
    client = HubClient(hub_url, token=token)
    started_at_text = utc_now()
    started_at = parse_timestamp(started_at_text)
    if started_at is None:
        raise FieldValidationError("failed to create validation start timestamp")
    health = client.get("/health")
    effective_expected_message_test_run_id = expected_message_test_run_id or test_run_id
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
                    **({"interval_ms": interval_ms} if command_name == "set_report_interval" else {}),
                    **({"reason": "lte004_raw_lte_location_validation"} if command_name == "request_location" else {}),
                    "test_run_id": test_run_id,
                    "source": (
                        "lte004_raw_lte_location_validation"
                        if command_name == "request_location"
                        else "lte003_command_validation"
                    ),
                },
            },
        )["command"]
    cmd_id = str(created["cmd_id"])
    evidence_started_at, evidence_started_at_text, evidence_since_resolution = resolve_evidence_start(
        evidence_since=evidence_since,
        validation_started_at=started_at,
        validation_started_at_text=started_at_text,
        command=created,
        test_run=test_run,
    )
    deadline = time.monotonic() + timeout_sec
    final_command: dict[str, Any] = created
    final_commands: list[dict[str, Any]] = []
    final_device: dict[str, Any] = {}
    location_report: dict[str, Any] = {}
    location_observation: dict[str, Any] = {}
    summary: dict[str, Any] = command_ack_summary(created)
    errors: list[str] = []

    if arm_only:
        final_device = get_device_state(client, device_id)
        final_commands = list_device_commands(client, device_id)
        final_command = find_command(final_commands, cmd_id) or final_command
        summary = command_ack_summary(final_command)
    else:
        errors = [f"command {cmd_id} remained pending"]
        while True:
            final_device = get_device_state(client, device_id)
            final_commands = list_device_commands(client, device_id)
            final_command = find_command(final_commands, cmd_id) or final_command
            summary = command_ack_summary(final_command)
            status = str(final_command.get("status") or "")
            if status == "ok":
                errors = ack_summary_errors(
                    summary,
                    expected_fw_version=expected_fw_version,
                    expected_test_run_id=test_run_id,
                    expected_ack_test_run_id=expected_ack_test_run_id,
                )
                if not errors:
                    break
            elif status not in {"pending", ""}:
                errors = [f"command {cmd_id} finished with non-ok status: {status}"]
                break
            if time.monotonic() >= deadline:
                errors = [
                    f"timed out waiting for LTE ACK for command {cmd_id}",
                    *ack_summary_errors(
                        summary,
                        expected_fw_version=expected_fw_version,
                        expected_test_run_id=test_run_id,
                        expected_ack_test_run_id=expected_ack_test_run_id,
                    ),
                ]
                break
            time.sleep(poll_interval_sec)

    if not arm_only and not errors and require_location_report:
        location_report, location_errors = wait_for_location_report(
            client,
            device_id=device_id,
            started_at=evidence_started_at,
            expected_message_test_run_id=effective_expected_message_test_run_id,
            cmd_id=cmd_id,
            timeout_sec=timeout_sec,
            poll_interval_sec=poll_interval_sec,
            require_fix=require_fix,
        )
        errors.extend(location_errors)

    if not arm_only and not errors and require_location_observation:
        location_observation, observation_errors = wait_for_location_observation(
            client,
            device_id=device_id,
            started_at=evidence_started_at,
            expected_message_test_run_id=effective_expected_message_test_run_id,
            cmd_id=cmd_id,
            timeout_sec=timeout_sec,
            poll_interval_sec=poll_interval_sec,
        )
        errors.extend(observation_errors)

    completed_at_text = utc_now()
    result = "ARMED" if arm_only else ("PASS" if not errors else "FAIL")
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
        "evidence_since": evidence_since,
        "evidence_started_at": evidence_started_at_text,
        "evidence_since_resolution": evidence_since_resolution,
        "expected_fw_version": expected_fw_version,
        "expected_ack_test_run_id": expected_ack_test_run_id,
        "effective_expected_ack_test_run_id": expected_ack_test_run_id or test_run_id,
        "expected_message_test_run_id": expected_message_test_run_id,
        "effective_expected_message_test_run_id": effective_expected_message_test_run_id,
        "require_location_report": require_location_report,
        "require_location_observation": require_location_observation,
        "require_fix": require_fix,
        "arm_only": arm_only,
        "existing_command_id": existing_command_id,
        "health": health,
        "test_run": test_run,
        "command": final_command,
        "location_report": location_report,
        "location_observation": location_observation,
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
    parser.add_argument(
        "--expected-ack-test-run-id",
        help=(
            "Expected test_run_id inside the firmware ACK. Defaults to --test-run-id. "
            "Use this for repeat validations against an already-flashed image whose "
            "CONFIG_EGOLINK_TEST_RUN_ID is fixed at build time."
        ),
    )
    parser.add_argument(
        "--expected-message-test-run-id",
        help=(
            "Expected test_run_id inside required location_report/location_observation messages. "
            "Defaults to --test-run-id. Use this when command test-run identity differs from "
            "the firmware image CONFIG_EGOLINK_TEST_RUN_ID."
        ),
    )
    parser.add_argument("--command", default="set_report_interval")
    parser.add_argument("--interval-ms", type=int, default=10000)
    parser.add_argument(
        "--require-location-report",
        action="store_true",
        help="Require a fresh LTE-marked location_report for the command ID before passing.",
    )
    parser.add_argument(
        "--require-location-observation",
        action="store_true",
        help="Require a fresh LTE-marked location_observation with firmware-side cell/LTE evidence.",
    )
    parser.add_argument(
        "--require-fix",
        action="store_true",
        help="Require location_report fix=true with observed/verified coordinates.",
    )
    parser.add_argument(
        "--existing-command-id",
        help="Wait for an already queued command instead of creating a new command.",
    )
    parser.add_argument(
        "--evidence-since",
        choices=["command-created", "validator-start", "test-run-created"],
        default="command-created",
        help=(
            "Timestamp anchor for required location evidence. command-created lets "
            "reconciliation include frames uploaded during a manual USB-Free reboot "
            "before the validator was restarted."
        ),
    )
    parser.add_argument(
        "--arm-only",
        action="store_true",
        help="Create or select the command, write a report with its cmd_id, and exit without waiting for ACK.",
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
            expected_ack_test_run_id=args.expected_ack_test_run_id,
            expected_message_test_run_id=args.expected_message_test_run_id,
            command_name=args.command,
            interval_ms=args.interval_ms,
            existing_command_id=args.existing_command_id,
            require_location_report=args.require_location_report or args.require_fix,
            require_location_observation=args.require_location_observation,
            require_fix=args.require_fix,
            evidence_since=args.evidence_since.replace("-", "_"),
            arm_only=args.arm_only,
        )
    except FieldValidationError as exc:
        print(f"FAIL LTE-003 command loop validation: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        if report["result"] == "ARMED":
            print(
                "ARMED LTE command validation "
                f"device={report['device_id']} cmd_id={report['command']['cmd_id']}"
            )
        else:
            print(
                "PASS LTE-003 command loop validation "
                f"device={report['device_id']} cmd_id={report['ack_summary']['cmd_id']}"
            )
        print(f"Report: {report['markdown_report_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

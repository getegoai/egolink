"""Validate LTE-002 SIM7670G LTE HTTP uplink through the Message Hub.

This script talks only to the HTTP Message Hub. It does not flash firmware,
open serial ports, erase flash, enqueue commands, or control hardware. It is
intended for the USB-Free LTE-002 field step after the operator has flashed an
LTE HTTP probe image and disconnected USB runtime power.
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


KNOWN_LTE_HTTP_REASON_CODES = {
    "LTE_HTTP_OK",
    "LTE_HTTP_AT_UNREACHABLE",
    "LTE_HTTP_UART_INIT_FAILED",
    "LTE_HTTP_INIT_FAILED",
    "LTE_HTTP_CID_FAILED",
    "LTE_HTTP_URL_FAILED",
    "LTE_HTTP_CONTENT_FAILED",
    "LTE_HTTP_HEADER_FAILED",
    "LTE_HTTP_DATA_FAILED",
    "LTE_HTTP_ACTION_FAILED",
    "LTE_HTTP_STATUS_INVALID",
    "LTE_HTTP_CLIENT_ERROR",
    "LTE_HTTP_SERVER_ERROR",
    "LTE_HTTP_STATUS_ERROR",
}


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def latest_probe_message(
    messages: list[dict[str, Any]],
    *,
    started_at: datetime,
    expected_test_run_id: str | None,
    phase: str | None = None,
) -> dict[str, Any]:
    for message in messages:
        if message.get("message_type") != "event" or message.get("event_type") != "lte_http_probe":
            continue
        if phase and as_dict(message.get("lte_http")).get("phase") != phase:
            continue
        if expected_test_run_id and message.get("test_run_id") != expected_test_run_id:
            continue
        received_at = parse_timestamp(message.get("server_received_at"))
        if received_at is None or received_at < started_at:
            continue
        return message
    return {}


def lte_http_summary(message: dict[str, Any]) -> dict[str, Any]:
    lte_http = as_dict(message.get("lte_http"))
    transport = as_dict(message.get("transport"))
    lte = as_dict(message.get("lte"))
    cell = as_dict(message.get("cell"))
    return {
        "phase": lte_http.get("phase"),
        "reason_code": str(lte_http.get("reason_code") or "unknown"),
        "driver": lte_http.get("driver"),
        "status_code": lte_http.get("status_code"),
        "action_elapsed_ms": lte_http.get("action_elapsed_ms"),
        "transport_type": transport.get("type"),
        "transport_last_error": transport.get("last_error"),
        "lte_reason_code": lte.get("reason_code") or cell.get("reason_code"),
        "registration_state": lte.get("registration_state") or cell.get("registration_state"),
        "pdp_state": lte.get("pdp_state") or cell.get("pdp_state"),
        "assigned_ip": lte.get("assigned_ip"),
        "rat": cell.get("rat"),
        "cell_id": cell.get("cell_id"),
        "rssi": cell.get("rssi"),
        "rsrp": cell.get("rsrp"),
        "rsrq": cell.get("rsrq"),
        "sinr": cell.get("sinr"),
    }


def lte_http_summary_is_success(summary: dict[str, Any]) -> bool:
    status_code = summary.get("status_code")
    return (
        summary.get("phase") == "result"
        and summary.get("reason_code") == "LTE_HTTP_OK"
        and summary.get("transport_type") == "lte"
        and isinstance(status_code, int)
        and 200 <= status_code < 300
    )


def write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    lte_http = report.get("lte_http") or {}
    lines = [
        "# LTE-002 LTE HTTP Probe Report",
        "",
        f"- Result: {report['result']}",
        f"- Observation ID: {report['observation_id']}",
        f"- Device ID: {report['device_id']}",
        f"- Board ID: {report['board_id']}",
        f"- Connection path: {report['connection_path']}",
        f"- Started at: {report['started_at']}",
        f"- Completed at: {report['completed_at']}",
        f"- Hub: {report['hub_url']}",
        f"- Firmware: {report.get('fw_version', 'unknown')}",
        f"- Test run ID: {report.get('observed_test_run_id', 'unknown')}",
        f"- LTE HTTP reason: {lte_http.get('reason_code', 'unknown')}",
        f"- HTTP status: {lte_http.get('status_code', 'unknown')}",
        f"- Transport: {lte_http.get('transport_type', 'unknown')}",
        f"- LTE reason: {lte_http.get('lte_reason_code', 'unknown')}",
        f"- Registration/PDP: {lte_http.get('registration_state', 'unknown')} / {lte_http.get('pdp_state', 'unknown')}",
        f"- RAT/cell: {lte_http.get('rat', 'unknown')} / {lte_http.get('cell_id', 'unknown')}",
        f"- Signal: RSSI {lte_http.get('rssi', 'unknown')} RSRP {lte_http.get('rsrp', 'unknown')} RSRQ {lte_http.get('rsrq', 'unknown')} SINR {lte_http.get('sinr', 'unknown')}",
        "",
        "## Boundaries",
        "",
        "- This report validates only the LTE HTTP telemetry uplink thin-slice.",
        "- Passing this report does not validate LTE command polling, ACK, reconnect, battery, power, long-run stability, or enclosure GNSS behavior.",
        "- If no fresh LTE telemetry appears, the blocked stage is LTE HTTP/DNS/server reachability after the LTE-001B readiness gate.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_lte_http_probe(
    *,
    hub_url: str,
    device_id: str,
    token: str | None,
    output_dir: Path,
    observation_id: str,
    board_id: str,
    connection_path: str,
    timeout_sec: float,
    poll_interval_sec: float,
    expected_fw_version: str | None,
    expected_test_run_id: str | None,
) -> dict[str, Any]:
    client = HubClient(hub_url, token=token)
    started_at_text = utc_now()
    started_at = parse_timestamp(started_at_text)
    if started_at is None:
        raise FieldValidationError("failed to create LTE HTTP probe start timestamp")

    health = client.get("/health")
    test_run = client.post(
        "/api/v1/test-runs",
        {
            "test_run_id": observation_id,
            "task_id": "LTE-002",
            "board_id": board_id,
            "device_id": device_id,
            "connection_path": connection_path,
            "started_at": started_at_text,
            "status": "active",
            "goal": "USB-Free SIM7670G LTE HTTP telemetry uplink thin-slice",
        },
    )["test_run"]
    deadline = time.monotonic() + timeout_sec
    final_device: dict[str, Any] = {}
    final_probe: dict[str, Any] = {}
    final_attempt: dict[str, Any] = {}
    final_summary: dict[str, Any] = {}
    errors: list[str] = []

    while True:
        errors = []
        try:
            payload = client.get(f"/api/v1/devices/{device_id}")
            final_device = as_dict(payload.get("device"))
        except FieldValidationError as exc:
            final_device = {}
            errors.append(str(exc))
        history_payload = client.get(f"/api/v1/devices/{device_id}/telemetry/history")
        history = [item for item in history_payload.get("telemetry") or [] if isinstance(item, dict)]
        final_probe = latest_probe_message(
            history,
            started_at=started_at,
            expected_test_run_id=expected_test_run_id,
            phase="result",
        )
        final_attempt = latest_probe_message(
            history,
            started_at=started_at,
            expected_test_run_id=expected_test_run_id,
            phase="attempt",
        )
        if not final_probe:
            if final_attempt:
                errors.append("LTE HTTP attempt reached Message Hub, but no fresh result probe arrived")
            else:
                errors.append("no fresh LTE HTTP probe telemetry reached Message Hub")
        final_summary = lte_http_summary(final_probe)
        if expected_fw_version and final_probe.get("fw_version") != expected_fw_version:
            errors.append(f"fw_version={final_probe.get('fw_version')} did not match expected {expected_fw_version}")
        if expected_test_run_id and final_probe.get("test_run_id") != expected_test_run_id:
            errors.append(
                f"lte_http_probe test_run_id={final_probe.get('test_run_id')} did not match expected {expected_test_run_id}"
            )
        reason_code = final_summary.get("reason_code")
        if reason_code not in KNOWN_LTE_HTTP_REASON_CODES:
            errors.append(f"LTE HTTP reason_code was not recognized; got {reason_code}")
        if not lte_http_summary_is_success(final_summary):
            errors.append(f"LTE HTTP probe was not successful; summary={final_summary}")
        observability = as_dict(final_device.get("observability"))
        observed_transport = as_dict(observability.get("transport")).get("type")
        if observed_transport != "lte":
            errors.append(f"/api/state observability.transport.type={observed_transport} did not become lte")
        if not errors:
            break
        if time.monotonic() >= deadline:
            break
        time.sleep(poll_interval_sec)

    completed_at_text = utc_now()
    result = "PASS" if not errors else "FAIL"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "lte_http_probe_report.json"
    markdown_path = output_dir / "lte_http_probe_report.md"
    device_path = output_dir / "device_state.json"
    export_path = output_dir / "test_run_export.json"
    export = client.get(f"/api/v1/test-runs/{observation_id}/export")
    report = {
        "result": result,
        "hub_url": hub_url,
        "device_id": device_id,
        "board_id": board_id,
        "connection_path": connection_path,
        "observation_id": observation_id,
        "started_at": started_at_text,
        "completed_at": completed_at_text,
        "expected_fw_version": expected_fw_version,
        "expected_test_run_id": expected_test_run_id,
        "fw_version": final_probe.get("fw_version"),
        "observed_test_run_id": final_probe.get("test_run_id"),
        "health": health,
        "test_run": test_run,
        "lte_http": final_summary,
        "latest_probe": final_probe,
        "latest_attempt": final_attempt,
        "errors": errors,
        "device_state_path": str(device_path),
        "test_run_export_path": str(export_path),
        "report_path": str(report_path),
        "markdown_report_path": str(markdown_path),
    }
    write_json(device_path, {"device": final_device})
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
    parser.add_argument("--observation-id", default=f"lte002-{compact_utc_now()}")
    parser.add_argument("--board-id", default="connectivity-node-001")
    parser.add_argument("--connection-path", default="independent_power_usb_disconnected")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--timeout-sec", type=float, default=180.0)
    parser.add_argument("--poll-interval-sec", type=float, default=5.0)
    parser.add_argument("--expected-fw-version", default="0.1.0-lte002-lte-http-probe")
    parser.add_argument("--expected-test-run-id")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = args.output_dir or DEFAULT_OUTPUT_ROOT / args.observation_id
    try:
        report = validate_lte_http_probe(
            hub_url=args.hub,
            device_id=args.device_id,
            token=os.environ.get(args.token_env) or None,
            output_dir=output_dir,
            observation_id=args.observation_id,
            board_id=args.board_id,
            connection_path=args.connection_path,
            timeout_sec=args.timeout_sec,
            poll_interval_sec=args.poll_interval_sec,
            expected_fw_version=args.expected_fw_version,
            expected_test_run_id=args.expected_test_run_id,
        )
    except FieldValidationError as exc:
        print(f"FAIL LTE-002 HTTP probe validation: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            "PASS LTE-002 HTTP probe validation "
            f"device={report['device_id']} status={report['lte_http']['status_code']}"
        )
        print(f"Report: {report['markdown_report_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

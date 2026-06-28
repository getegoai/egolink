"""Validate LTE-001B SIM7670G LTE status observability through Message Hub.

This script talks only to the HTTP Message Hub. It does not flash firmware,
open serial ports, erase flash, enqueue commands, or control hardware. It is
intended for the USB-Free LTE-001B field step after the operator has flashed an
LTE-status image and disconnected USB runtime power.
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
    write_json,
)


KNOWN_LTE_REASON_CODES = {
    "LTE_AT_UNREACHABLE",
    "LTE_SIM_NOT_READY",
    "LTE_NOT_REGISTERED",
    "LTE_NOT_ATTACHED",
    "LTE_PDP_INACTIVE",
    "LTE_READY",
    "LTE_UART_INIT_FAILED",
}


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def first_known(*values: object) -> object:
    for value in values:
        if value not in (None, "", []):
            return value
    return None


def latest_status_test_run_id(device: dict[str, Any]) -> str | None:
    status = as_dict(device.get("last_status"))
    value = status.get("test_run_id")
    return str(value) if value not in (None, "") else None


def observed_lte_summary(device: dict[str, Any]) -> dict[str, Any]:
    observability = as_dict(device.get("observability"))
    lte = as_dict(observability.get("lte"))
    cell = as_dict(observability.get("cell"))
    reason_code = str(first_known(lte.get("reason_code"), cell.get("reason_code"), "unknown"))
    return {
        "reason_code": reason_code,
        "driver": first_known(lte.get("driver"), "unknown"),
        "query_ok": lte.get("query_ok"),
        "uart_ready": lte.get("uart_ready"),
        "at_ok": lte.get("at_ok"),
        "sim_state": first_known(lte.get("sim_state"), cell.get("sim_state"), "unknown"),
        "registration_state": first_known(lte.get("registration_state"), cell.get("registration_state"), "unknown"),
        "apn_state": first_known(lte.get("apn_state"), "unknown"),
        "pdp_state": first_known(lte.get("pdp_state"), cell.get("pdp_state"), "unknown"),
        "assigned_ip": first_known(lte.get("assigned_ip"), "unknown"),
        "rat": first_known(cell.get("rat"), "unknown"),
        "operator": first_known(cell.get("operator"), "unknown"),
        "mcc": first_known(cell.get("mcc"), "unknown"),
        "mnc": first_known(cell.get("mnc"), "unknown"),
        "tac": first_known(cell.get("tac"), "unknown"),
        "cell_id": first_known(cell.get("cell_id"), "unknown"),
        "rssi": cell.get("rssi"),
        "rsrp": cell.get("rsrp"),
        "rsrq": cell.get("rsrq"),
        "sinr": cell.get("sinr"),
    }


def lte_summary_is_observed(summary: dict[str, Any]) -> bool:
    reason_code = str(summary.get("reason_code") or "unknown")
    return reason_code in KNOWN_LTE_REASON_CODES


def write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    lte = report.get("lte") or {}
    lines = [
        "# LTE-001B LTE Observability Report",
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
        f"- LTE reason: {lte.get('reason_code', 'unknown')}",
        f"- SIM: {lte.get('sim_state', 'unknown')}",
        f"- Registration: {lte.get('registration_state', 'unknown')}",
        f"- APN/PDP: {lte.get('apn_state', 'unknown')} / {lte.get('pdp_state', 'unknown')}",
        f"- Assigned IP: {lte.get('assigned_ip', 'unknown')}",
        f"- RAT/cell: {lte.get('rat', 'unknown')} / {lte.get('cell_id', 'unknown')}",
        f"- Signal: RSSI {lte.get('rssi', 'unknown')} RSRP {lte.get('rsrp', 'unknown')} RSRQ {lte.get('rsrq', 'unknown')} SINR {lte.get('sinr', 'unknown')}",
        "",
        "## Boundaries",
        "",
        "- This report validates LTE state observability only.",
        "- `LTE_READY` means SIM/registration/attach/PDP appeared ready to the status query; it does not prove HTTP over LTE.",
        "- A non-ready `LTE_*` reason code can still be a valid LTE-001B observation because it explains the failing stage.",
        "- Passing this report does not flash hardware, disable Wi-Fi, set `transport.type=lte`, or prove LTE telemetry, command polling, ACK, DNS, battery, or power behavior.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_lte_observability(
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
    require_lte_ready: bool = False,
) -> dict[str, Any]:
    client = HubClient(hub_url, token=token)
    started_at_text = utc_now()
    started_at = parse_timestamp(started_at_text)
    if started_at is None:
        raise FieldValidationError("failed to create LTE observation start timestamp")

    health = client.get("/health")
    deadline = time.monotonic() + timeout_sec
    final_device: dict[str, Any] = {}
    final_lte: dict[str, Any] = {}
    errors: list[str] = []

    while True:
        errors = []
        try:
            payload = client.get(f"/api/v1/devices/{device_id}")
        except FieldValidationError as exc:
            payload = {}
            errors.append(str(exc))
        final_device = as_dict(payload.get("device"))
        if not final_device:
            errors.append(f"device {device_id} was not found")
        fw_version = final_device.get("fw_version")
        if expected_fw_version and fw_version != expected_fw_version:
            errors.append(f"fw_version={fw_version} did not match expected {expected_fw_version}")
        observed_test_run_id = latest_status_test_run_id(final_device)
        if expected_test_run_id and observed_test_run_id != expected_test_run_id:
            errors.append(
                f"last_status test_run_id={observed_test_run_id} did not match expected {expected_test_run_id}"
            )
        last_seen_at = parse_timestamp(final_device.get("last_seen_at"))
        if last_seen_at is None or last_seen_at < started_at:
            errors.append("device has not produced a fresh message since LTE observation started")
        final_lte = observed_lte_summary(final_device)
        if not lte_summary_is_observed(final_lte):
            errors.append(f"LTE reason_code was not observed; got {final_lte.get('reason_code')}")
        if require_lte_ready and final_lte.get("reason_code") != "LTE_READY":
            errors.append(f"LTE_READY was required; observed {final_lte.get('reason_code')}")
        if not errors:
            break
        if time.monotonic() >= deadline:
            break
        time.sleep(poll_interval_sec)

    completed_at_text = utc_now()
    result = "PASS" if not errors else "FAIL"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "lte_observability_report.json"
    markdown_path = output_dir / "lte_observability_report.md"
    device_path = output_dir / "device_state.json"
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
        "fw_version": final_device.get("fw_version"),
        "observed_test_run_id": latest_status_test_run_id(final_device),
        "health": health,
        "lte": final_lte,
        "errors": errors,
        "device_state_path": str(device_path),
        "report_path": str(report_path),
        "markdown_report_path": str(markdown_path),
    }
    write_json(device_path, {"device": final_device})
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
    parser.add_argument("--observation-id", default=f"lte001b-{compact_utc_now()}")
    parser.add_argument("--board-id", default="connectivity-node-001")
    parser.add_argument("--connection-path", default="independent_power_usb_disconnected")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--timeout-sec", type=float, default=180.0)
    parser.add_argument("--poll-interval-sec", type=float, default=5.0)
    parser.add_argument("--expected-fw-version", default="0.1.0-lte001b-observe")
    parser.add_argument("--expected-test-run-id")
    parser.add_argument("--require-lte-ready", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = args.output_dir or DEFAULT_OUTPUT_ROOT / args.observation_id
    try:
        report = validate_lte_observability(
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
            require_lte_ready=args.require_lte_ready,
        )
    except FieldValidationError as exc:
        print(f"FAIL LTE-001B observability validation: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            "PASS LTE-001B observability validation "
            f"device={report['device_id']} reason={report['lte']['reason_code']}"
        )
        print(f"Report: {report['markdown_report_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

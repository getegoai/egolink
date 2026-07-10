"""Prepare a Tiny Safety device-loop run plan without touching hardware.

The generated plan gives the operator exact commands for building the D1
periodic-location firmware image that contains the Tiny Safety CLI, optionally
flashing it, validating the serial CLI, and checking the USB-Free D1 Web path.
This script is offline-only: it does not read secrets, contact the Message Hub,
open serial ports, flash firmware, or run the generated commands.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any
from urllib.parse import urlparse


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "reports" / "tiny_safety_device_loop"
DEFAULT_HUB_URL = "http://203.0.113.10:8790"
DEFAULT_TOKEN_FILE = "server/runtime/vps_message_hub_token.txt"
DEFAULT_DEVICE_ID = "ego-link-r1-connectivity-001"
DEFAULT_BOARD_ID = "connectivity-node-001"
DEFAULT_FW_VERSION = "0.1.0-model-device-005-tiny-safety-cli"
DEFAULT_MODEL_ID = "MODEL-DEVICE-001-tiny-safety-v0-20260707"
DEFAULT_MODEL_VERSION = "0.1.0-synthetic-dry-run"
DEFAULT_BUILD_DIR = "build_model_device_005_tiny_safety"
DEFAULT_LOCATION_INTERVAL_SEC = 60
DEFAULT_OBSERVER_SAMPLE_COUNT = 3
DEFAULT_OBSERVER_POLL_INTERVAL_SEC = 10
DEFAULT_MAX17048_SDA_GPIO = 15
DEFAULT_MAX17048_SCL_GPIO = 16
PLAN_VERSION = "D5.tiny_safety_device_loop.v1"
PLAN_JSON = "tiny_safety_device_loop_plan.json"
RUNBOOK_MD = "TINY_SAFETY_DEVICE_LOOP_RUNBOOK.md"
NOTES_MD = "TINY_SAFETY_OPERATOR_NOTES.md"


class TinySafetyDeviceLoopError(RuntimeError):
    """Raised when device-loop planner inputs are inconsistent."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def compact_utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")


def git_short_commit() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return completed.stdout.strip() or "unknown"


def ps_quote(value: object) -> str:
    text = str(value)
    if text == "":
        return "''"
    safe_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_./:\\<>")
    if all(char in safe_chars for char in text):
        return text
    return "'" + text.replace("'", "''") + "'"


def format_ps_command(parts: list[str]) -> str:
    lines: list[str] = []
    for index, part in enumerate(parts):
        suffix = " `" if index < len(parts) - 1 else ""
        prefix = "" if index == 0 else "  "
        lines.append(f"{prefix}{ps_quote(part)}{suffix}")
    return "\n".join(lines)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def report_path(*parts: str) -> str:
    return str(Path("reports", *parts))


def resolve_hub(hub_url: str) -> dict[str, Any]:
    parsed = urlparse(hub_url)
    if not parsed.scheme or not parsed.hostname:
        raise TinySafetyDeviceLoopError("--hub-url must include scheme and host")
    return {
        "hub_url": hub_url.rstrip("/"),
        "host_name": parsed.hostname,
        "port": parsed.port or (443 if parsed.scheme == "https" else 80),
        "scheme": parsed.scheme,
    }


def command_record(
    *,
    description: str,
    argv: list[str],
    runs_build: bool = False,
    hardware_action: bool = False,
    opens_serial_port: bool = False,
    flashes_firmware: bool = False,
    contacts_message_hub: bool = False,
    sends_message_hub_command: bool = False,
    requires_operator_intent: bool = False,
) -> dict[str, Any]:
    return {
        "description": description,
        "argv": argv,
        "powershell": format_ps_command(argv),
        "runs_build": runs_build,
        "hardware_action": hardware_action,
        "opens_serial_port": opens_serial_port,
        "flashes_firmware": flashes_firmware,
        "contacts_message_hub": contacts_message_hub,
        "sends_message_hub_command": sends_message_hub_command,
        "requires_operator_intent": requires_operator_intent,
    }


def firmware_base_args(
    *,
    hub: dict[str, Any],
    device_id: str,
    fw_version: str,
    test_run_id: str,
    token_file: str,
    build_dir: str,
    location_interval_sec: int,
    max17048_sda_gpio: int,
    max17048_scl_gpio: int,
) -> list[str]:
    return [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        "scripts\\run_fw001_hw_r1.ps1",
        "-HostName",
        str(hub["host_name"]),
        "-Port",
        str(hub["port"]),
        "-Scheme",
        str(hub["scheme"]),
        "-DeviceId",
        device_id,
        "-FwVersion",
        fw_version,
        "-TestRunId",
        test_run_id,
        "-TokenFile",
        token_file,
        "-BuildDir",
        build_dir,
        "-EnableSim7670Gnss",
        "-EnableSim7670LteStatus",
        "-EnableSim7670LteHttpCommandLoop",
        "-EnableSim7670LocationObservation",
        "-EnableD1PeriodicLocation",
        "-D1PeriodicLocationIntervalSec",
        str(location_interval_sec),
        "-EnableMax17048Power",
        "-Max17048SdaGpio",
        str(max17048_sda_gpio),
        "-Max17048SclGpio",
        str(max17048_scl_gpio),
    ]


def build_commands(
    *,
    hub: dict[str, Any],
    run_id: str,
    device_id: str,
    fw_version: str,
    test_run_id: str,
    token_file: str,
    build_dir: str,
    location_interval_sec: int,
    observer_sample_count: int,
    observer_poll_interval_sec: int,
    max17048_sda_gpio: int,
    max17048_scl_gpio: int,
) -> dict[str, dict[str, Any]]:
    fw_base = firmware_base_args(
        hub=hub,
        device_id=device_id,
        fw_version=fw_version,
        test_run_id=test_run_id,
        token_file=token_file,
        build_dir=build_dir,
        location_interval_sec=location_interval_sec,
        max17048_sda_gpio=max17048_sda_gpio,
        max17048_scl_gpio=max17048_scl_gpio,
    )
    web_review_id = f"{run_id}-post-flash-web"
    observer_run_id = f"{run_id}-post-flash-observer"
    serial_run_id = f"{run_id}-serial-cli"
    return {
        "build_d1_tiny_cli_image": command_record(
            description=(
                "Build the D1 periodic-location firmware image that contains the "
                "MODEL-DEVICE-003 Tiny Safety CLI. No flash is run."
            ),
            argv=fw_base + ["-PrepareBuild", "-Json"],
            runs_build=True,
        ),
        "flash_explicit_operator_action": command_record(
            description=(
                "Flash the prepared Tiny Safety CLI firmware image only when the "
                "operator explicitly intends to overwrite device firmware."
            ),
            argv=fw_base
            + [
                "-PrepareBuild",
                "-Flash",
                "-FlashPort",
                "<COMx>",
                "-IUnderstandFlashWritesFirmware",
                "-Json",
            ],
            hardware_action=True,
            flashes_firmware=True,
            requires_operator_intent=True,
        ),
        "serial_tiny_safety_validation": command_record(
            description=(
                "Validate safety tiny status/selftest/demo marker lines on a flashed "
                "board through a bounded serial session."
            ),
            argv=[
                "python",
                "scripts\\validate_tiny_safety_firmware_cli.py",
                "--port",
                "<COMx>",
                "--i-understand-serial-hardware",
                "--run-id",
                serial_run_id,
                "--output-dir",
                report_path("tiny_safety_firmware_cli"),
            ],
            hardware_action=True,
            opens_serial_port=True,
            requires_operator_intent=True,
        ),
        "usb_free_d1_web_check_after_flash": command_record(
            description=(
                "Read-only Web/API check after flashing and rebooting on independent "
                "power. This validates D1 freshness without using serial runtime evidence."
            ),
            argv=[
                "python",
                "scripts\\validate_d1_web_api.py",
                "--hub-url",
                str(hub["hub_url"]),
                "--token-file",
                token_file,
                "--review-id",
                web_review_id,
                "--output-dir",
                report_path("d1_web_api", web_review_id),
                "--device-id",
                device_id,
                "--json",
            ],
            contacts_message_hub=True,
        ),
        "short_usb_free_observer_after_flash": command_record(
            description=(
                "Short read-only D1 observer after flashing. Use this only after the "
                "device is running independently and uploading through LTE."
            ),
            argv=[
                "python",
                "scripts\\observe_d1_field_run.py",
                "--hub-url",
                str(hub["hub_url"]),
                "--token-file",
                token_file,
                "--run-id",
                observer_run_id,
                "--output-dir",
                report_path("d1_field_observation", observer_run_id),
                "--device-id",
                device_id,
                "--sample-count",
                str(observer_sample_count),
                "--poll-interval-sec",
                str(observer_poll_interval_sec),
                "--max-stale-sec",
                str(max(location_interval_sec * 3, 180)),
                "--json",
            ],
            contacts_message_hub=True,
        ),
    }


def non_claims() -> list[str]:
    return [
        "default_plan_does_not_flash_firmware",
        "default_plan_does_not_open_serial_or_contact_hardware",
        "default_plan_does_not_read_or_persist_secret_values",
        "default_plan_does_not_contact_vps_or_send_device_commands",
        "tiny_safety_labels_are_synthetic_integration_evidence_only",
        "model_output_not_mapped_to_sms_calls_dispatch_or_external_escalation",
        "no_real_world_model_accuracy_claim",
        "no_latency_ram_flash_or_power_measurement_claim",
        "no_product_release_readiness_claim",
    ]


def build_expected_outputs(*, run_id: str, build_dir: str) -> dict[str, str]:
    web_review_id = f"{run_id}-post-flash-web"
    observer_run_id = f"{run_id}-post-flash-observer"
    serial_run_id = f"{run_id}-serial-cli"
    return {
        "firmware_build_dir": str(Path("firmware", "mqtt_heartbeat", build_dir)),
        "firmware_binary": str(Path("firmware", "mqtt_heartbeat", build_dir, "egolink_mqtt_heartbeat.bin")),
        "tiny_safety_cli_report": report_path(
            "tiny_safety_firmware_cli", serial_run_id, "tiny_safety_cli_report.json"
        ),
        "tiny_safety_cli_markdown": report_path(
            "tiny_safety_firmware_cli", serial_run_id, "tiny_safety_cli_report.md"
        ),
        "post_flash_web_api_report": report_path("d1_web_api", web_review_id, "d1_web_api_report.json"),
        "post_flash_observer_status": report_path(
            "d1_field_observation", observer_run_id, "d1_field_observation_status.json"
        ),
        "post_flash_observer_report": report_path(
            "d1_field_observation", observer_run_id, "d1_field_observation_report.json"
        ),
    }


def build_manifest(
    *,
    run_id: str,
    created_at: str,
    output_dir: Path,
    hub: dict[str, Any],
    device_id: str,
    board_id: str,
    fw_version: str,
    model_id: str,
    model_version: str,
    test_run_id: str,
    token_file: str,
    build_dir: str,
    location_interval_sec: int,
    observer_sample_count: int,
    observer_poll_interval_sec: int,
    max17048_sda_gpio: int,
    max17048_scl_gpio: int,
    git_commit: str,
) -> dict[str, Any]:
    plan_path = output_dir / PLAN_JSON
    runbook_path = output_dir / RUNBOOK_MD
    notes_path = output_dir / NOTES_MD
    commands = build_commands(
        hub=hub,
        run_id=run_id,
        device_id=device_id,
        fw_version=fw_version,
        test_run_id=test_run_id,
        token_file=token_file,
        build_dir=build_dir,
        location_interval_sec=location_interval_sec,
        observer_sample_count=observer_sample_count,
        observer_poll_interval_sec=observer_poll_interval_sec,
        max17048_sda_gpio=max17048_sda_gpio,
        max17048_scl_gpio=max17048_scl_gpio,
    )
    return {
        "tool": "prepare_tiny_safety_device_loop",
        "plan_version": PLAN_VERSION,
        "created_at": created_at,
        "task": "MODEL-DEVICE-005",
        "serves_demo": "D5",
        "run_id": run_id,
        "result": "READY_FOR_OPERATOR_PLAN",
        "git_commit": git_commit,
        "hub": hub,
        "device": {
            "board_id": board_id,
            "device_id": device_id,
            "fw_version": fw_version,
            "test_run_id": test_run_id,
        },
        "model": {
            "model_id": model_id,
            "model_version": model_version,
            "firmware_cli_commands": [
                "safety tiny status",
                "safety tiny selftest",
                "safety tiny demo normal",
                "safety tiny demo uncertain",
                "safety tiny demo needs_check",
                "safety tiny demo possible_risk",
                "safety tiny demo sos",
                "safety tiny demo cancel",
            ],
            "synthetic_only": True,
            "external_actions": False,
        },
        "firmware": {
            "source_path": "firmware/mqtt_heartbeat",
            "build_dir": build_dir,
            "features": [
                "sim7670_gnss",
                "sim7670_lte_status",
                "sim7670_lte_http_command_loop",
                "sim7670_location_observation",
                "d1_periodic_location",
                "max17048_power",
                "tiny_safety_cli",
            ],
            "d1_periodic_location_interval_sec": location_interval_sec,
            "max17048_sda_gpio": max17048_sda_gpio,
            "max17048_scl_gpio": max17048_scl_gpio,
        },
        "scope": {
            "offline_plan_generator": True,
            "commands_run": False,
            "build_ran": False,
            "hardware_contacted": False,
            "serial_ports_opened": False,
            "firmware_flashed": False,
            "message_hub_contacted": False,
            "message_hub_commands_sent": False,
            "secrets_read": False,
            "secrets_persisted": False,
            "gitlab_modified": False,
        },
        "commands": commands,
        "artifacts": {
            "plan": str(plan_path),
            "runbook": str(runbook_path),
            "operator_notes": str(notes_path),
        },
        "expected_outputs": build_expected_outputs(run_id=run_id, build_dir=build_dir),
        "hardware_evidence_requirements": [
            "board_id",
            "device_id",
            "firmware_commit_or_binary",
            "firmware_version",
            "test_run_id",
            "connection_path",
            "timestamp_utc",
            "command_list",
            "evidence_file_path",
        ],
        "boundaries": [
            "This planner writes local run-plan files only.",
            "Build, flash, serial validation, and Web checks are generated as commands but are not executed.",
            "Flashing remains an explicit operator hardware action and uses the existing firmware runner guard.",
            "Serial validation remains an explicit operator hardware action and uses the Tiny Safety validator guard.",
            "USB-Free D1 Web checks are read-only Message Hub checks and should be run after independent-power reboot.",
            "The plan preserves the current Safety Kernel boundary and does not route model output to real escalation.",
        ],
        "non_claims": non_claims(),
    }


def write_runbook(path: Path, manifest: dict[str, Any]) -> None:
    commands = manifest["commands"]
    lines = [
        "# Tiny Safety Device Loop Runbook",
        "",
        f"- Run ID: `{manifest['run_id']}`",
        f"- Task: `{manifest['task']}`",
        f"- Firmware version: `{manifest['device']['fw_version']}`",
        f"- Test run ID: `{manifest['device']['test_run_id']}`",
        f"- Model: `{manifest['model']['model_id']}` / `{manifest['model']['model_version']}`",
        f"- Git commit at plan time: `{manifest['git_commit']}`",
        "",
        "## 1. Build Image",
        "",
        "Build is allowed as a local static step. It does not flash the device.",
        "",
        "```powershell",
        commands["build_d1_tiny_cli_image"]["powershell"],
        "```",
        "",
        "## 2. Optional Flash",
        "",
        "Use only when the operator intends to overwrite firmware on the connectivity board.",
        "",
        "```powershell",
        commands["flash_explicit_operator_action"]["powershell"],
        "```",
        "",
        "## 3. Guarded Serial Tiny Safety CLI Validation",
        "",
        "Run after flashing if serial validation evidence is needed. Expected commands include `safety tiny status`, `safety tiny selftest`, and bounded `safety tiny demo ...` cases.",
        "",
        "```powershell",
        commands["serial_tiny_safety_validation"]["powershell"],
        "```",
        "",
        "## 4. USB-Free D1 Web Check",
        "",
        "Run after the board is rebooted on independent power and is uploading through LTE.",
        "",
        "```powershell",
        commands["usb_free_d1_web_check_after_flash"]["powershell"],
        "```",
        "",
        "## 5. Short USB-Free Observer",
        "",
        "This is a short smoke observer for post-flash freshness, not a long power baseline.",
        "",
        "```powershell",
        commands["short_usb_free_observer_after_flash"]["powershell"],
        "```",
        "",
        "## Expected Evidence",
        "",
    ]
    for name, value in manifest["expected_outputs"].items():
        lines.append(f"- `{name}`: `{value}`")
    lines.extend(["", "## Hardware Evidence Requirements", ""])
    for item in manifest["hardware_evidence_requirements"]:
        lines.append(f"- `{item}`")
    lines.extend(["", "## Boundaries", ""])
    for item in manifest["boundaries"]:
        lines.append(f"- {item}")
    lines.extend(["", "## Non-Claims", ""])
    for item in manifest["non_claims"]:
        lines.append(f"- `{item}`")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_notes(path: Path, manifest: dict[str, Any]) -> None:
    lines = [
        "# Tiny Safety Device Loop Operator Notes",
        "",
        f"- Run ID: `{manifest['run_id']}`",
        f"- Board ID: `{manifest['device']['board_id']}`",
        f"- Device ID: `{manifest['device']['device_id']}`",
        f"- Firmware version: `{manifest['device']['fw_version']}`",
        f"- Firmware binary: `{manifest['expected_outputs']['firmware_binary']}`",
        f"- Model ID: `{manifest['model']['model_id']}`",
        f"- Planned serial port: `<record COM port only when validating>`",
        f"- Independent-power reboot time UTC: `<record if flashed>`",
        "",
        "## Evidence",
        "",
        f"- Plan JSON: `{manifest['artifacts']['plan']}`",
        f"- Runbook: `{manifest['artifacts']['runbook']}`",
        f"- Tiny Safety CLI report: `{manifest['expected_outputs']['tiny_safety_cli_report']}`",
        f"- Post-flash Web/API report: `{manifest['expected_outputs']['post_flash_web_api_report']}`",
        f"- Post-flash observer report: `{manifest['expected_outputs']['post_flash_observer_report']}`",
        "",
        "## Observations",
        "",
        "| time UTC | action | result | evidence path |",
        "|---|---|---|---|",
        "| `<time>` | `<build/flash/serial/web>` | `<pass/fail/not-run>` | `<path>` |",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def prepare_device_loop(
    *,
    run_id: str,
    output_dir: Path,
    hub_url: str,
    device_id: str,
    board_id: str,
    fw_version: str,
    model_id: str,
    model_version: str,
    test_run_id: str,
    token_file: str,
    build_dir: str,
    location_interval_sec: int,
    observer_sample_count: int,
    observer_poll_interval_sec: int,
    max17048_sda_gpio: int,
    max17048_scl_gpio: int,
    created_at: str | None = None,
    git_commit: str | None = None,
) -> dict[str, Any]:
    if location_interval_sec < 15 or location_interval_sec > 3600:
        raise TinySafetyDeviceLoopError("--location-interval-sec must be between 15 and 3600")
    if observer_sample_count <= 0:
        raise TinySafetyDeviceLoopError("--observer-sample-count must be positive")
    if observer_poll_interval_sec < 1:
        raise TinySafetyDeviceLoopError("--observer-poll-interval-sec must be positive")
    if max17048_sda_gpio < 0 or max17048_scl_gpio < 0:
        raise TinySafetyDeviceLoopError("MAX17048 GPIO numbers must be non-negative")
    hub = resolve_hub(hub_url)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(
        run_id=run_id,
        created_at=created_at or utc_now(),
        output_dir=output_dir,
        hub=hub,
        device_id=device_id,
        board_id=board_id,
        fw_version=fw_version,
        model_id=model_id,
        model_version=model_version,
        test_run_id=test_run_id,
        token_file=token_file,
        build_dir=build_dir,
        location_interval_sec=location_interval_sec,
        observer_sample_count=observer_sample_count,
        observer_poll_interval_sec=observer_poll_interval_sec,
        max17048_sda_gpio=max17048_sda_gpio,
        max17048_scl_gpio=max17048_scl_gpio,
        git_commit=git_commit or git_short_commit(),
    )
    write_json(output_dir / PLAN_JSON, manifest)
    write_runbook(output_dir / RUNBOOK_MD, manifest)
    write_notes(output_dir / NOTES_MD, manifest)
    return manifest


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--hub-url", default=os.environ.get("EGOLINK_MESSAGE_HUB_URL") or DEFAULT_HUB_URL)
    parser.add_argument("--device-id", default=DEFAULT_DEVICE_ID)
    parser.add_argument("--board-id", default=DEFAULT_BOARD_ID)
    parser.add_argument("--fw-version", default=DEFAULT_FW_VERSION)
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument("--model-version", default=DEFAULT_MODEL_VERSION)
    parser.add_argument("--test-run-id")
    parser.add_argument("--token-file", default=DEFAULT_TOKEN_FILE)
    parser.add_argument("--build-dir", default=DEFAULT_BUILD_DIR)
    parser.add_argument("--location-interval-sec", type=int, default=DEFAULT_LOCATION_INTERVAL_SEC)
    parser.add_argument("--observer-sample-count", type=int, default=DEFAULT_OBSERVER_SAMPLE_COUNT)
    parser.add_argument("--observer-poll-interval-sec", type=int, default=DEFAULT_OBSERVER_POLL_INTERVAL_SEC)
    parser.add_argument("--max17048-sda-gpio", type=int, default=DEFAULT_MAX17048_SDA_GPIO)
    parser.add_argument("--max17048-scl-gpio", type=int, default=DEFAULT_MAX17048_SCL_GPIO)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run_id = args.run_id or f"MODEL-DEVICE-005-{compact_utc_now()}"
    test_run_id = args.test_run_id or f"{run_id}-d1"
    output_dir = args.output_dir or (DEFAULT_OUTPUT_ROOT / run_id)
    try:
        manifest = prepare_device_loop(
            run_id=run_id,
            output_dir=output_dir,
            hub_url=args.hub_url,
            device_id=args.device_id,
            board_id=args.board_id,
            fw_version=args.fw_version,
            model_id=args.model_id,
            model_version=args.model_version,
            test_run_id=test_run_id,
            token_file=args.token_file,
            build_dir=args.build_dir,
            location_interval_sec=args.location_interval_sec,
            observer_sample_count=args.observer_sample_count,
            observer_poll_interval_sec=args.observer_poll_interval_sec,
            max17048_sda_gpio=args.max17048_sda_gpio,
            max17048_scl_gpio=args.max17048_scl_gpio,
        )
    except TinySafetyDeviceLoopError as exc:
        print(f"FAIL Tiny Safety device loop plan: {exc}", file=sys.stderr)
        return 1
    summary = {
        "ok": True,
        "run_id": manifest["run_id"],
        "output_dir": str(output_dir),
        "plan_path": manifest["artifacts"]["plan"],
        "runbook_path": manifest["artifacts"]["runbook"],
        "scope": manifest["scope"],
    }
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"PASS Tiny Safety device loop plan: {manifest['artifacts']['runbook']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

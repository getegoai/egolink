"""Prepare a D1 outdoor field-test kit without touching hardware.

The generated kit gives the operator exact commands and checklists for a
multi-hour D1 field shakedown. This script is offline-only: it does not read
secrets, contact the Message Hub, open serial ports, flash firmware, or send
device commands.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any
from urllib.parse import urlparse


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "reports" / "d1_field"
DEFAULT_TOKEN_FILE = "server/runtime/vps_message_hub_token.txt"
DEFAULT_DEVICE_ID = "ego-link-r1-connectivity-001"
DEFAULT_FW_VERSION = "0.1.0-d1-periodic-location"
DEFAULT_BOARD_ID = "connectivity-node-001"
DEFAULT_DURATION_HOURS = 4.0
KIT_VERSION = "D1.field_kit.v4"
MANIFEST_JSON = "field_manifest.json"
RUNBOOK_MD = "FIELD_RUNBOOK.md"
CHECKLIST_MD = "FIELD_CHECKLIST.md"
NOTES_MD = "OPERATOR_NOTES.md"


class D1FieldKitError(RuntimeError):
    """Raised when field-kit inputs are inconsistent."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def compact_utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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


def command_record(
    *,
    description: str,
    argv: list[str],
    hardware_action: bool = False,
    opens_serial_port: bool = False,
    writes_amoled_serial: bool = False,
    sends_message_hub_command: bool = False,
    requires_operator_intent: bool = False,
) -> dict[str, Any]:
    return {
        "description": description,
        "argv": argv,
        "powershell": format_ps_command(argv),
        "hardware_action": hardware_action,
        "opens_serial_port": opens_serial_port,
        "writes_amoled_serial": writes_amoled_serial,
        "sends_message_hub_command": sends_message_hub_command,
        "requires_operator_intent": requires_operator_intent,
    }


def with_optional_amoled_port(argv: list[str], amoled_port: str) -> list[str]:
    if not amoled_port:
        return argv
    return argv + ["-AmoledPort", amoled_port]


def with_optional_sidecar_port(argv: list[str], amoled_port: str) -> list[str]:
    if not amoled_port:
        return argv
    return argv + ["-Port", amoled_port]


def resolve_hub(*, hub_url: str, host_name: str, port: int, scheme: str) -> dict[str, Any]:
    if hub_url:
        parsed = urlparse(hub_url)
        resolved_scheme = parsed.scheme or scheme
        resolved_host = parsed.hostname or host_name
        resolved_port = parsed.port or port
        normalized = hub_url.rstrip("/")
    else:
        resolved_scheme = scheme
        resolved_host = host_name
        resolved_port = port
        normalized = f"{resolved_scheme}://{resolved_host}:{resolved_port}"
    return {
        "hub_url": normalized,
        "host_name": resolved_host,
        "port": resolved_port,
        "scheme": resolved_scheme,
    }


def resolve_max17048_pins(
    *, board_revision: str, sda_gpio: int | None, scl_gpio: int | None
) -> tuple[int, int, list[str]]:
    warnings: list[str] = []
    if (sda_gpio is None) ^ (scl_gpio is None):
        raise D1FieldKitError("provide both --max17048-sda-gpio and --max17048-scl-gpio, or neither")
    if sda_gpio is not None and scl_gpio is not None:
        return sda_gpio, scl_gpio, warnings
    if board_revision == "V1":
        return 3, 2, warnings
    if board_revision == "unknown":
        warnings.append("board_revision_unknown_using_v2_default_pins_confirm_before_flash")
    return 15, 16, warnings


def report_path(*parts: str) -> str:
    return str(Path("reports", *parts))


def build_commands(
    *,
    hub: dict[str, Any],
    run_id: str,
    device_id: str,
    fw_version: str,
    token_file: str,
    amoled_port: str,
    sda_gpio: int,
    scl_gpio: int,
    duration_hours: float,
    location_interval_sec: int,
    battery_capacity_mah: float | None,
) -> dict[str, dict[str, Any]]:
    fw_base = [
        "powershell",
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
        run_id,
        "-TokenFile",
        token_file,
        "-EnableSim7670Gnss",
        "-EnableSim7670LteStatus",
        "-EnableSim7670LteHttpCommandLoop",
        "-EnableSim7670LocationObservation",
        "-EnableD1PeriodicLocation",
        "-D1PeriodicLocationIntervalSec",
        str(location_interval_sec),
        "-EnableMax17048Power",
        "-Max17048SdaGpio",
        str(sda_gpio),
        "-Max17048SclGpio",
        str(scl_gpio),
    ]
    battery_capacity_arg = f"{battery_capacity_mah:g}" if battery_capacity_mah is not None else "<rated-capacity-mah>"
    observer_max_stale_sec = max(location_interval_sec * 3, 180)
    duration_minutes = f"{duration_hours * 60:g}"
    preflight_amoled_argv = with_optional_sidecar_port(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            "scripts\\run_amoled_d1_status_sidecar.ps1",
            "-HubUrl",
            str(hub["hub_url"]),
            "-TokenFile",
            token_file,
            "-SampleCount",
            "1",
            "-PollIntervalSec",
            "0",
            "-ReadWindowSeconds",
            "10",
            "-SessionId",
            f"{run_id}-preflight-amoled",
            "-OutputDir",
            report_path("amoled_visible_status", run_id, "preflight"),
            "-Reset",
        ],
        amoled_port,
    )
    companion_argv = with_optional_amoled_port(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            "scripts\\run_d1_field_companion.ps1",
            "-HubUrl",
            str(hub["hub_url"]),
            "-TokenFile",
            token_file,
            "-RunId",
            run_id,
            "-DeviceId",
            device_id,
            "-DurationMinutes",
            duration_minutes,
            "-PollIntervalSec",
            str(location_interval_sec),
            "-AmoledReadWindowSeconds",
            "10",
            "-OutputRoot",
            report_path("d1_field_companion"),
        ],
        amoled_port,
    )
    return {
        "preflight_web_api_gate": command_record(
            description="Read-only preflight check of VPS D1 Web/API before leaving.",
            argv=[
                "python",
                "scripts\\validate_d1_web_api.py",
                "--hub-url",
                str(hub["hub_url"]),
                "--token-file",
                token_file,
                "--review-id",
                f"{run_id}-preflight",
                "--output-dir",
                report_path("d1_web_api", f"{run_id}-preflight"),
                "--device-id",
                device_id,
                "--json",
            ],
        ),
        "preflight_amoled_visible_status": command_record(
            description=(
                "Send one visible display_status page to the AMOLED sidecar before leaving. "
                "This writes only to the AMOLED USB Serial/JTAG sidecar."
            ),
            argv=preflight_amoled_argv,
            hardware_action=True,
            opens_serial_port=True,
            writes_amoled_serial=True,
            requires_operator_intent=True,
        ),
        "prepare_build": command_record(
            description="Create ignored local firmware config and build the D1 field image. No flash is run.",
            argv=fw_base + ["-PrepareBuild", "-Json"],
        ),
        "flash_explicit_operator_action": command_record(
            description="Flash the already prepared D1 field image only when the operator intends to write firmware.",
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
            requires_operator_intent=True,
        ),
        "short_usb_free_link_check": command_record(
            description=(
                "Optional 3-5 minute link check after the operator confirms independent power "
                "and USB disconnected. This may enqueue one request_location command."
            ),
            argv=fw_base
            + [
                "-Validate",
                "-OperatorConfirmedIndependentPower",
                "-OperatorConfirmedUsbDisconnected",
                "-LteCommandName",
                "request_location",
                "-RequireLteLocationObservation",
                "-ValidationTimeoutSec",
                "300",
                "-Json",
            ],
            sends_message_hub_command=True,
            requires_operator_intent=True,
        ),
        "live_field_observer": command_record(
            description="Read-only VPS observer to run during the outdoor field shakedown.",
            argv=[
                "python",
                "scripts\\observe_d1_field_run.py",
                "--hub-url",
                str(hub["hub_url"]),
                "--token-file",
                token_file,
                "--run-id",
                run_id,
                "--output-dir",
                report_path("d1_field_observation", run_id),
                "--device-id",
                device_id,
                "--duration-minutes",
                f"{duration_hours * 60:g}",
                "--poll-interval-sec",
                str(location_interval_sec),
                "--max-stale-sec",
                str(observer_max_stale_sec),
                "--json",
            ],
        ),
        "live_field_companion": command_record(
            description=(
                "Preferred D1 outdoor run command: starts the read-only observer and the visible AMOLED sidecar "
                "with the same run ID."
            ),
            argv=companion_argv,
            hardware_action=True,
            opens_serial_port=True,
            writes_amoled_serial=True,
            requires_operator_intent=True,
        ),
        "post_run_web_api_gate": command_record(
            description="Read-only D1 Web/API review after the field run.",
            argv=[
                "python",
                "scripts\\validate_d1_web_api.py",
                "--hub-url",
                str(hub["hub_url"]),
                "--token-file",
                token_file,
                "--review-id",
                f"{run_id}-web",
                "--output-dir",
                report_path("d1_web_api", run_id),
                "--device-id",
                device_id,
                "--json",
            ],
        ),
        "post_run_power_curve": command_record(
            description="Fetch the Message Hub test-run export and analyze measured MAX17048 power samples.",
            argv=[
                "python",
                "scripts\\analyze_power_curve.py",
                "--hub",
                str(hub["hub_url"]),
                "--test-run-id",
                run_id,
                "--token-file",
                token_file,
                "--output-dir",
                report_path("power", run_id),
                "--min-duration-hours",
                f"{duration_hours:g}",
                "--battery-capacity-mah",
                battery_capacity_arg,
                "--json",
            ],
        ),
        "post_run_d1_demo_report": command_record(
            description="Compose the D1 Web/API gate and power report into one D1 evidence report.",
            argv=[
                "python",
                "scripts\\build_d1_demo_report.py",
                "--web-api-report",
                report_path("d1_web_api", run_id, "d1_web_api_report.json"),
                "--power-curve-report",
                report_path("power", run_id, "power_curve_report.json"),
                "--report-id",
                run_id,
                "--output-dir",
                report_path("d1_demo", run_id),
                "--json",
            ],
        ),
        "post_run_data_flywheel_status": command_record(
            description=(
                "Run the local data-flywheel pipeline after the field run. "
                "This writes bounded pipeline/status/dataset/experiment manifests only, not raw candidate records."
            ),
            argv=[
                "python",
                "scripts\\run_data_flywheel_pipeline.py",
                "--run-id",
                f"{run_id}-data-pipeline",
                "--dataset-id",
                f"{run_id}-dataset",
                "--json",
            ],
        ),
        "post_run_sync_dashboard_summaries": command_record(
            description=(
                "Sync only curated Field Test Results, Data Flywheel, and Training Experiment summaries to the VPS Dashboard."
            ),
            argv=[
                "powershell",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                "scripts\\deploy_message_hub_vps.ps1",
                "-HostName",
                str(hub["host_name"]),
                "-SshKey",
                "$HOME\\.ssh\\egolink_vps_ed25519",
                "-Public",
                "-IncludeFieldReportSummaries",
                "-IncludeDataFlywheelSummaries",
                "-IncludeTrainingExperimentSummaries",
            ],
            requires_operator_intent=True,
        ),
    }


def build_checklists(*, duration_hours: float) -> dict[str, list[str]]:
    return {
        "before_leaving": [
            "Message Hub health endpoint and Dashboard are reachable from phone.",
            "Token is available via local token file or EGOLINK_MESSAGE_HUB_TOKEN, outside git.",
            "Run the read-only preflight Web/API gate and confirm D1 state is fresh.",
            "Run the AMOLED visible-status preflight and confirm the screen shows the D1 status page.",
            "Board revision and MAX17048 SDA/SCL pins are recorded.",
            "Firmware commit or binary path is recorded in OPERATOR_NOTES.md.",
            "D1 field image is built; flashing is complete only if explicitly intended by the operator.",
            "SIM/network path, GNSS antenna, battery, and cable strain relief are ready.",
            "Run ID, device ID, firmware version, and target evidence folders are copied to the phone or notes.",
            "Calling and SMS are not part of this run and must not be claimed.",
        ],
        "start_run": [
            "Confirm independent battery or power-bank supply.",
            "Disconnect USB before counting runtime evidence.",
            "Record local and UTC start time.",
            "Confirm Dashboard D1 panel becomes fresh before walking away.",
        ],
        "during_run": [
            f"Keep the device running outdoors for about {duration_hours:g} hours.",
            "Run the live field companion from this kit if a laptop or stable PC can stay online.",
            "Keep the AMOLED sidecar visible when practical; record if it becomes blank, stale, or disconnected.",
            "Check the Dashboard periodically from phone; do not use serial as the runtime evidence path.",
            "Record gaps, reboots, lost service, charging changes, or operator touches with timestamps.",
            "If USB must be reconnected, record the runtime stop first and treat later data as a new segment.",
        ],
        "after_run": [
            "Record local and UTC stop time plus visible Dashboard state.",
            "Run the Web/API gate, power-curve analysis, and D1 demo report commands from this kit.",
            "Run the data-flywheel pipeline command so post-run data state and dataset handoff readiness are recorded.",
            "Sync curated Field Test Results and Data Flywheel summaries to the VPS Dashboard.",
            "Keep raw Message Hub export, generated reports, and OPERATOR_NOTES.md together.",
            "Do not claim location accuracy, battery life, GNSS acceptance, or 24h PWR-001 pass from a short D1 run.",
        ],
    }


def non_claims() -> list[str]:
    return [
        "location_accuracy_not_claimed",
        "battery_life_not_claimed",
        "gnss_acceptance_not_claimed",
        "calling_not_claimed",
        "sms_not_claimed",
        "pwr001_24h_pass_not_claimed",
        "product_readiness_not_claimed",
    ]


def write_runbook(path: Path, manifest: dict[str, Any]) -> None:
    commands = manifest["commands"]
    checklist = manifest["checklists"]
    lines = [
        "# D1 Outdoor Field Runbook",
        "",
        "> Status: operator runbook and evidence manifest, not hardware evidence.",
        "",
        "## Purpose",
        "",
        "Serve D1 by running the 4G board on independent power for a multi-hour outdoor shakedown:",
        "GNSS/cell/IMU/power collection -> LTE upload -> server location estimate -> Dashboard map visible.",
        "Accuracy and battery life are explicitly out of scope for this run.",
        "",
        "## Identifiers",
        "",
        f"- Run ID: `{manifest['run_id']}`",
        f"- Kit version: `{manifest['kit_version']}`",
        f"- Hub URL: `{manifest['hub']['hub_url']}`",
        f"- Device ID: `{manifest['device']['device_id']}`",
        f"- Board ID: `{manifest['device']['board_id']}`",
        f"- Firmware version: `{manifest['device']['fw_version']}`",
        f"- Target duration: `{manifest['field_run']['duration_hours']} h`",
        f"- Location upload interval: `{manifest['field_run']['location_interval_sec']} s`",
        f"- AMOLED port: `{manifest['sidecar']['amoled_port'] or 'auto-detect'}`",
        f"- Board revision: `{manifest['power']['board_revision']}`",
        f"- MAX17048 pins: SDA GPIO{manifest['power']['max17048_sda_gpio']} / SCL GPIO{manifest['power']['max17048_scl_gpio']}",
        f"- Token file reference: `{manifest['secrets']['token_file']}`",
        "",
        "## Before Leaving",
        "",
    ]
    lines.extend(f"- [ ] {item}" for item in checklist["before_leaving"])
    lines.extend(
        [
        "",
        "### Preflight Web/API Gate",
        "",
        "Read-only check that the VPS D1 surface is reachable and current enough to review.",
        "",
        "```powershell",
        commands["preflight_web_api_gate"]["powershell"],
        "```",
        "",
        "### Preflight AMOLED Visible Status",
        "",
        "Confirm the sidecar screen visibly switches to the D1 status page before leaving.",
        "The sidecar runner sends the `display_status` command to force the full-screen status view.",
        "",
        "```powershell",
        commands["preflight_amoled_visible_status"]["powershell"],
        "```",
        "",
        "### Build Or Refresh Firmware Image",
        "",
        "This command does not flash firmware.",
        "",
            "```powershell",
            commands["prepare_build"]["powershell"],
            "```",
            "",
            "### Flash Only With Explicit Operator Intent",
            "",
            "Replace `<COMx>` with the observed ESP32-S3 console port only when you intend to write firmware.",
            "",
            "```powershell",
            commands["flash_explicit_operator_action"]["powershell"],
            "```",
            "",
            "## Start Run",
            "",
        ]
    )
    lines.extend(f"- [ ] {item}" for item in checklist["start_run"])
    lines.extend(
        [
            "",
            "Optional short check after USB is disconnected:",
            "",
            "```powershell",
            commands["short_usb_free_link_check"]["powershell"],
            "```",
            "",
            "## During Run",
            "",
            "Preferred one-command live run: starts the D1 observer and AMOLED display sidecar with the same run ID.",
            "",
            "```powershell",
            commands["live_field_companion"]["powershell"],
            "```",
            "",
            "Read-only live observer, if a laptop or stable PC can stay online during the field run:",
            "",
            "```powershell",
            commands["live_field_observer"]["powershell"],
            "```",
            "",
        ]
    )
    lines.extend(f"- [ ] {item}" for item in checklist["during_run"])
    lines.extend(
        [
            "",
            "## After Run",
            "",
        ]
    )
    lines.extend(f"- [ ] {item}" for item in checklist["after_run"])
    lines.extend(
        [
            "",
            "### Web/API Gate",
            "",
            "```powershell",
            commands["post_run_web_api_gate"]["powershell"],
            "```",
            "",
            "### Power Curve",
            "",
            "For a short field shakedown this uses the kit duration as the minimum duration. It is not a 24h PWR-001 pass.",
            "",
            "```powershell",
            commands["post_run_power_curve"]["powershell"],
            "```",
            "",
            "### D1 Evidence Report",
            "",
            "```powershell",
            commands["post_run_d1_demo_report"]["powershell"],
            "```",
            "",
            "### Data Flywheel Pipeline",
            "",
            "This writes bounded pipeline, status, dataset-manifest, and training-experiment reports. It does not export raw candidate records.",
            "",
            "```powershell",
            commands["post_run_data_flywheel_status"]["powershell"],
            "```",
            "",
            "### Sync Dashboard Summaries",
            "",
            "This syncs curated report summaries to the Web Dashboard. It does not copy candidate DBs, raw JSONL logs, or private payloads.",
            "",
            "```powershell",
            commands["post_run_sync_dashboard_summaries"]["powershell"],
            "```",
            "",
            "## Boundaries",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in manifest["boundaries"])
    lines.extend(["", "## Non-Claims", ""])
    lines.extend(f"- `{item}`" for item in manifest["non_claims"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_checklist(path: Path, manifest: dict[str, Any]) -> None:
    lines = ["# D1 Outdoor Field Checklist", "", f"- Run ID: `{manifest['run_id']}`", ""]
    for section, items in manifest["checklists"].items():
        lines.extend([f"## {section.replace('_', ' ').title()}", ""])
        lines.extend(f"- [ ] {item}" for item in items)
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_notes_template(path: Path, manifest: dict[str, Any]) -> None:
    lines = [
        "# D1 Field Operator Notes",
        "",
        f"- Run ID: `{manifest['run_id']}`",
        f"- Device ID: `{manifest['device']['device_id']}`",
        f"- Firmware version: `{manifest['device']['fw_version']}`",
        f"- Firmware commit or binary: `<record before leaving>`",
        f"- AMOLED port: `{manifest['sidecar']['amoled_port'] or 'auto-detect'}`",
        f"- Board revision: `{manifest['power']['board_revision']}`",
        f"- MAX17048 pins: SDA GPIO{manifest['power']['max17048_sda_gpio']} / SCL GPIO{manifest['power']['max17048_scl_gpio']}",
        f"- Battery capacity mAh: `{manifest['power']['battery_capacity_mah'] or '<record rated capacity>'}`",
        f"- Hub URL: `{manifest['hub']['hub_url']}`",
        "",
        "## Times",
        "",
        "- Local start: `<YYYY-MM-DD HH:MM timezone>`",
        "- UTC start: `<YYYY-MM-DDTHH:MM:SSZ>`",
        "- Local stop: `<YYYY-MM-DD HH:MM timezone>`",
        "- UTC stop: `<YYYY-MM-DDTHH:MM:SSZ>`",
        "",
        "## Observations",
        "",
        "| time | Dashboard state / field observation | operator action |",
        "|---|---|---|",
        "| `<time>` | `<fresh/stale, GNSS/cell/power notes>` | `<none/reboot/power change>` |",
        "",
        "## Evidence",
        "",
        f"- Kit manifest: `{manifest['artifacts']['manifest']}`",
        f"- Companion summary: `{manifest['expected_outputs']['companion_summary']}`",
        f"- Live field observation report: `{manifest['expected_outputs']['field_observation_report']}`",
        f"- AMOLED sidecar summary: `{manifest['expected_outputs']['amoled_sidecar_summary']}`",
        f"- Web/API report: `{manifest['expected_outputs']['web_api_report']}`",
        f"- Power report: `{manifest['expected_outputs']['power_report']}`",
        f"- D1 demo report: `{manifest['expected_outputs']['d1_demo_report']}`",
        f"- Training experiment plan: `{manifest['expected_outputs']['training_experiment_plan']}`",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_manifest(
    *,
    run_id: str,
    created_at: str,
    output_dir: Path,
    hub: dict[str, Any],
    device_id: str,
    board_id: str,
    fw_version: str,
    token_file: str,
    amoled_port: str,
    duration_hours: float,
    location_interval_sec: int,
    board_revision: str,
    sda_gpio: int,
    scl_gpio: int,
    battery_capacity_mah: float | None,
    warnings: list[str],
) -> dict[str, Any]:
    commands = build_commands(
        hub=hub,
        run_id=run_id,
        device_id=device_id,
        fw_version=fw_version,
        token_file=token_file,
        amoled_port=amoled_port,
        sda_gpio=sda_gpio,
        scl_gpio=scl_gpio,
        duration_hours=duration_hours,
        location_interval_sec=location_interval_sec,
        battery_capacity_mah=battery_capacity_mah,
    )
    manifest_path = output_dir / MANIFEST_JSON
    runbook_path = output_dir / RUNBOOK_MD
    checklist_path = output_dir / CHECKLIST_MD
    notes_path = output_dir / NOTES_MD
    return {
        "tool": "prepare_d1_field_kit",
        "kit_version": KIT_VERSION,
        "created_at": created_at,
        "demo": "D1",
        "run_id": run_id,
        "result": "READY_FOR_OPERATOR",
        "warnings": warnings,
        "hub": hub,
        "device": {
            "board_id": board_id,
            "device_id": device_id,
            "fw_version": fw_version,
        },
        "field_run": {
            "duration_hours": duration_hours,
            "location_interval_sec": location_interval_sec,
            "connection_path": "independent_power_usb_disconnected",
            "runtime_evidence_path": "device -> LTE/network -> VPS Message Hub -> Web Dashboard",
        },
        "sidecar": {
            "amoled_port": amoled_port,
            "mode": "pc_connected_visible_display",
            "status_command": "display_status",
            "product_dependency": False,
        },
        "communications": {
            "lte_data": "observed_for_d1_message_hub_uploads",
            "voice_calling": "unverified_not_implemented",
            "sms": "unverified_not_implemented",
            "live_call_or_sms_probe_included": False,
        },
        "power": {
            "backend": "MAX17048",
            "board_revision": board_revision,
            "max17048_sda_gpio": sda_gpio,
            "max17048_scl_gpio": scl_gpio,
            "battery_capacity_mah": battery_capacity_mah,
        },
        "secrets": {
            "token_file": token_file,
            "token_value_read": False,
            "token_value_persisted": False,
        },
        "scope": {
            "offline_kit_generator": True,
            "hardware_contacted": False,
            "serial_ports_opened": False,
            "message_hub_contacted": False,
            "commands_sent": False,
            "firmware_flashed": False,
            "gitlab_modified": False,
            "secrets_persisted": False,
        },
        "commands": commands,
        "checklists": build_checklists(duration_hours=duration_hours),
        "artifacts": {
            "manifest": str(manifest_path),
            "runbook": str(runbook_path),
            "checklist": str(checklist_path),
            "operator_notes": str(notes_path),
        },
        "expected_outputs": {
            "companion_summary": report_path("d1_field_companion", run_id, "d1_field_companion_summary.json"),
            "amoled_sidecar_summary": report_path("d1_field_companion", run_id, "amoled", f"{run_id}.summary.json"),
            "preflight_amoled_summary": report_path(
                "amoled_visible_status", run_id, "preflight", f"{run_id}-preflight-amoled.summary.json"
            ),
            "preflight_web_api_report": report_path(
                "d1_web_api", f"{run_id}-preflight", "d1_web_api_report.json"
            ),
            "field_observation_report": report_path("d1_field_observation", run_id, "d1_field_observation_report.json"),
            "field_observation_samples": report_path("d1_field_observation", run_id, "d1_field_samples.jsonl"),
            "web_api_report": report_path("d1_web_api", run_id, "d1_web_api_report.json"),
            "power_report": report_path("power", run_id, "power_curve_report.json"),
            "d1_demo_report": report_path("d1_demo", run_id, "d1_demo_report.json"),
            "message_hub_export": report_path("power", run_id, "test_run_export.json"),
            "data_flywheel_pipeline": report_path(
                "data_flywheel_pipeline", f"{run_id}-data-pipeline", "data_flywheel_pipeline_run.json"
            ),
            "data_flywheel_status": report_path(
                "data_flywheel", f"{run_id}-data-pipeline-data-flywheel", "data_flywheel_status.json"
            ),
            "training_dataset_manifest": report_path(
                "training_datasets", f"{run_id}-dataset", "training_dataset_manifest.json"
            ),
            "training_experiment_plan": report_path(
                "training_experiments",
                f"{run_id}-data-pipeline-experiment",
                "training_experiment_plan.json",
            ),
        },
        "boundaries": [
            "This generator only writes local kit files.",
            "It does not read or persist token values.",
            "It does not contact hardware, open serial ports, flash firmware, send Message Hub commands, deploy code, or modify GitLab.",
            "Operator commands that flash firmware or send commands are explicitly labeled and require operator intent.",
            "AMOLED sidecar commands are PC-connected display aids and are not USB-Free product acceptance evidence.",
            "Voice calling and SMS are unverified and not implemented in the current D1 run path.",
            "A multi-hour D1 shakedown is not a 24h PWR-001 pass or a product battery-life claim.",
        ],
        "non_claims": non_claims(),
    }


def prepare_field_kit(
    *,
    run_id: str,
    output_dir: Path,
    hub_url: str,
    host_name: str,
    port: int,
    scheme: str,
    device_id: str,
    board_id: str,
    fw_version: str,
    token_file: str,
    amoled_port: str,
    duration_hours: float,
    location_interval_sec: int,
    board_revision: str,
    max17048_sda_gpio: int | None,
    max17048_scl_gpio: int | None,
    battery_capacity_mah: float | None,
    created_at: str | None = None,
) -> dict[str, Any]:
    if duration_hours <= 0:
        raise D1FieldKitError("--duration-hours must be positive")
    if battery_capacity_mah is not None and battery_capacity_mah <= 0:
        raise D1FieldKitError("--battery-capacity-mah must be positive when provided")
    if location_interval_sec < 15 or location_interval_sec > 3600:
        raise D1FieldKitError("--location-interval-sec must be between 15 and 3600")
    hub = resolve_hub(hub_url=hub_url, host_name=host_name, port=port, scheme=scheme)
    sda_gpio, scl_gpio, warnings = resolve_max17048_pins(
        board_revision=board_revision,
        sda_gpio=max17048_sda_gpio,
        scl_gpio=max17048_scl_gpio,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(
        run_id=run_id,
        created_at=created_at or utc_now(),
        output_dir=output_dir,
        hub=hub,
        device_id=device_id,
        board_id=board_id,
        fw_version=fw_version,
        token_file=token_file,
        amoled_port=amoled_port,
        duration_hours=duration_hours,
        location_interval_sec=location_interval_sec,
        board_revision=board_revision,
        sda_gpio=sda_gpio,
        scl_gpio=scl_gpio,
        battery_capacity_mah=battery_capacity_mah,
        warnings=warnings,
    )
    write_json(output_dir / MANIFEST_JSON, manifest)
    write_runbook(output_dir / RUNBOOK_MD, manifest)
    write_checklist(output_dir / CHECKLIST_MD, manifest)
    write_notes_template(output_dir / NOTES_MD, manifest)
    return manifest


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--hub-url", default="")
    parser.add_argument("--host-name", default=os.environ.get("EGOLINK_VPS_HOST") or "<message-hub-host>")
    parser.add_argument("--port", type=int, default=8790)
    parser.add_argument("--scheme", choices=("http", "https"), default="http")
    parser.add_argument("--device-id", default=DEFAULT_DEVICE_ID)
    parser.add_argument("--board-id", default=DEFAULT_BOARD_ID)
    parser.add_argument("--fw-version", default=DEFAULT_FW_VERSION)
    parser.add_argument("--token-file", default=DEFAULT_TOKEN_FILE)
    parser.add_argument("--amoled-port", default="")
    parser.add_argument("--duration-hours", type=float, default=DEFAULT_DURATION_HOURS)
    parser.add_argument("--location-interval-sec", type=int, default=60)
    parser.add_argument("--board-revision", choices=("V2", "V1", "unknown"), default="V2")
    parser.add_argument("--max17048-sda-gpio", type=int)
    parser.add_argument("--max17048-scl-gpio", type=int)
    parser.add_argument("--battery-capacity-mah", type=float)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run_id = args.run_id or f"D1-FIELD-{compact_utc_now()}"
    output_dir = args.output_dir or (DEFAULT_OUTPUT_ROOT / run_id)
    try:
        manifest = prepare_field_kit(
            run_id=run_id,
            output_dir=output_dir,
            hub_url=args.hub_url,
            host_name=args.host_name,
            port=args.port,
            scheme=args.scheme,
            device_id=args.device_id,
            board_id=args.board_id,
            fw_version=args.fw_version,
            token_file=args.token_file,
            amoled_port=args.amoled_port,
            duration_hours=args.duration_hours,
            location_interval_sec=args.location_interval_sec,
            board_revision=args.board_revision,
            max17048_sda_gpio=args.max17048_sda_gpio,
            max17048_scl_gpio=args.max17048_scl_gpio,
            battery_capacity_mah=args.battery_capacity_mah,
        )
    except D1FieldKitError as exc:
        print(f"FAIL D1 field kit: {exc}", file=sys.stderr)
        return 1
    summary = {
        "ok": True,
        "run_id": manifest["run_id"],
        "output_dir": str(output_dir),
        "manifest_path": manifest["artifacts"]["manifest"],
        "runbook_path": manifest["artifacts"]["runbook"],
        "warnings": manifest["warnings"],
    }
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"PASS D1 field kit: {manifest['artifacts']['runbook']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

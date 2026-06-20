"""Non-destructive board validation for Ego Link P0.

The probe is intentionally conservative. It enumerates Windows USB/serial
devices, reads ESP32-S3 serial output if available, and sends only basic SIMCom
AT query commands to likely SIM7670G AT ports.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import re
import subprocess
import sys
from typing import Any, Iterable


SIM_AT_COMMANDS = ("AT", "ATI", "AT+CPIN?", "AT+CSQ", "AT+CEREG?", "AT+CGATT?")
DEFAULT_OUTPUT_DIR = Path("reports") / "board_validation"


@dataclass(frozen=True)
class SerialPortInfo:
    port: str
    name: str
    description: str
    pnp_device_id: str
    role: str
    usb_mi: str | None = None


@dataclass(frozen=True)
class CheckResult:
    check: str
    status: str
    detail: str


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = run_probe(
        esp_port=args.esp_port,
        sim_ports=args.sim_ports,
        esp_listen_seconds=args.esp_listen_seconds,
        output_dir=Path(args.output_dir),
        probe_all_sim_ports=args.probe_all_sim_ports,
        skip_esp_log=args.skip_esp_log,
    )
    print(report["markdown_path"])
    return 0 if not any(c["status"] == "FAIL" for c in report["checks"]) else 2


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory for timestamped JSON and Markdown reports.",
    )
    parser.add_argument(
        "--esp-port",
        default="auto",
        help="ESP32 serial port, or auto to use the CH343 port.",
    )
    parser.add_argument(
        "--sim-port",
        dest="sim_ports",
        action="append",
        default=[],
        help="SIM7670G AT port to probe. Can be repeated. Defaults to MI_02/MI_06.",
    )
    parser.add_argument(
        "--probe-all-sim-ports",
        action="store_true",
        help="Probe every VID_05C6 PID_9330 serial port, including diagnostic ports.",
    )
    parser.add_argument(
        "--esp-listen-seconds",
        type=float,
        default=5.0,
        help="Seconds to listen for ESP32 serial logs.",
    )
    parser.add_argument(
        "--skip-esp-log",
        action="store_true",
        help="Skip ESP32 log listening.",
    )
    return parser.parse_args(argv)


def run_probe(
    *,
    esp_port: str,
    sim_ports: list[str],
    esp_listen_seconds: float,
    output_dir: Path,
    probe_all_sim_ports: bool,
    skip_esp_log: bool,
) -> dict[str, Any]:
    started_at = utc_now()
    serial_ports = discover_serial_ports()
    net_adapters = discover_net_adapters()
    esp_candidate = choose_esp_port(serial_ports, esp_port)
    sim_candidates = choose_sim_ports(serial_ports, sim_ports, probe_all_sim_ports)

    esp_log = ""
    esp_error = None
    if esp_candidate and not skip_esp_log:
        esp_probe = read_serial_log(esp_candidate.port, esp_listen_seconds)
        esp_log = esp_probe.get("log", "")
        esp_error = esp_probe.get("error")

    sim_probe_results = []
    for port_info in sim_candidates:
        sim_probe_results.append(
            {
                "port_info": asdict(port_info),
                "probe": probe_sim_at_port(port_info.port, SIM_AT_COMMANDS),
            }
        )

    parsed_sim = [parse_sim_probe(item) for item in sim_probe_results]
    parsed_esp = parse_esp_log(esp_log)
    checks = evaluate_checks(
        serial_ports=serial_ports,
        net_adapters=net_adapters,
        esp_candidate=esp_candidate,
        esp_error=esp_error,
        esp_log=esp_log,
        parsed_esp=parsed_esp,
        parsed_sim=parsed_sim,
    )

    report_payload: dict[str, Any] = {
        "project": "Ego Link P0",
        "started_at": started_at,
        "host": {"platform": platform.platform(), "python": sys.version.split()[0]},
        "serial_ports": [asdict(item) for item in serial_ports],
        "net_adapters": net_adapters,
        "esp_probe": {
            "port": asdict(esp_candidate) if esp_candidate else None,
            "error": esp_error,
            "log_excerpt": truncate_text(esp_log, 4000),
            "parsed": parsed_esp,
        },
        "sim_probe_results": sim_probe_results,
        "parsed_sim": parsed_sim,
        "checks": [asdict(item) for item in checks],
    }

    stamp = timestamp_for_path()
    run_dir = output_dir / stamp
    run_dir.mkdir(parents=True, exist_ok=True)
    json_path = run_dir / "probe.json"
    markdown_path = run_dir / "probe.md"
    json_path.write_text(json.dumps(report_payload, indent=2, ensure_ascii=False), "utf-8")
    markdown_path.write_text(render_markdown_report(report_payload), "utf-8")
    report_payload["json_path"] = str(json_path)
    report_payload["markdown_path"] = str(markdown_path)
    return report_payload


def discover_serial_ports() -> list[SerialPortInfo]:
    if platform.system() != "Windows":
        return []
    script = r"""
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$ports = Get-CimInstance Win32_SerialPort |
  Select-Object DeviceID, Name, Description, PNPDeviceID
$ports | ConvertTo-Json -Depth 4
"""
    raw = run_powershell(script)
    rows = ensure_list(json.loads(raw)) if raw.strip() else []
    return [classify_serial_port(row) for row in rows]


def discover_net_adapters() -> list[dict[str, Any]]:
    if platform.system() != "Windows":
        return []
    script = r"""
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$adapters = Get-NetAdapter |
  Where-Object {
    $_.InterfaceDescription -match 'RNDIS|Remote NDIS|05C6|SIM|Qualcomm|USB' -or
    $_.Name -match 'RNDIS|USB|SIM'
  } |
  Select-Object Name, InterfaceDescription, Status, LinkSpeed, MacAddress
$adapters | ConvertTo-Json -Depth 4
"""
    raw = run_powershell(script)
    return ensure_list(json.loads(raw)) if raw.strip() else []


def classify_serial_port(row: dict[str, Any]) -> SerialPortInfo:
    port = str(row.get("DeviceID") or "")
    name = str(row.get("Name") or "")
    description = str(row.get("Description") or "")
    pnp = str(row.get("PNPDeviceID") or "")
    usb_mi = parse_usb_mi(pnp)
    role = "unknown"
    if "VID_1A86&PID_55D3" in pnp.upper() or "CH343" in name.upper():
        role = "esp32_s3_ch343"
    elif "VID_05C6&PID_9330" in pnp.upper():
        role = "sim7670_serial"
        if usb_mi in {"02", "06"}:
            role = "sim7670_at_candidate"
        elif usb_mi:
            role = f"sim7670_aux_mi_{usb_mi}"
    return SerialPortInfo(
        port=port,
        name=name,
        description=description,
        pnp_device_id=pnp,
        role=role,
        usb_mi=usb_mi,
    )


def choose_esp_port(
    serial_ports: Iterable[SerialPortInfo],
    requested: str,
) -> SerialPortInfo | None:
    if requested != "auto":
        return SerialPortInfo(requested, requested, "", "", "manual_esp")
    return next((item for item in serial_ports if item.role == "esp32_s3_ch343"), None)


def choose_sim_ports(
    serial_ports: Iterable[SerialPortInfo],
    requested: list[str],
    probe_all: bool,
) -> list[SerialPortInfo]:
    if requested:
        return [
            SerialPortInfo(port, port, "", "", "manual_sim_at")
            for port in requested
        ]
    if probe_all:
        return [item for item in serial_ports if item.role.startswith("sim7670")]
    return [item for item in serial_ports if item.role == "sim7670_at_candidate"]


def probe_sim_at_port(port: str, commands: Iterable[str]) -> dict[str, Any]:
    commands_literal = "@(" + ",".join(ps_quote(item) for item in commands) + ")"
    script = f"""
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$ErrorActionPreference = 'Stop'
$result = [ordered]@{{ port = {ps_quote(port)}; ok = $false; error = $null; responses = @() }}
$sp = $null
try {{
  $sp = [System.IO.Ports.SerialPort]::new({ps_quote(port)}, 115200, [System.IO.Ports.Parity]::None, 8, [System.IO.Ports.StopBits]::One)
  $sp.ReadTimeout = 800
  $sp.WriteTimeout = 800
  $sp.NewLine = "`r`n"
  $sp.DtrEnable = $false
  $sp.RtsEnable = $false
  $sp.Open()
  Start-Sleep -Milliseconds 120
  $sp.DiscardInBuffer()
  foreach ($cmd in {commands_literal}) {{
    $sp.Write("$cmd`r")
    Start-Sleep -Milliseconds 350
    $response = $sp.ReadExisting()
    if ($response.Length -gt 1600) {{
      $response = $response.Substring(0, 1600) + "...[truncated]"
    }}
    $result.responses += [ordered]@{{ command = $cmd; response = $response }}
  }}
  $result.ok = $true
}} catch {{
  $result.error = $_.Exception.Message
}} finally {{
  if ($sp -and $sp.IsOpen) {{ $sp.Close() }}
}}
$result | ConvertTo-Json -Depth 6
"""
    raw = run_powershell(script, timeout_seconds=8)
    return json.loads(raw)


def read_serial_log(port: str, seconds: float) -> dict[str, Any]:
    sleep_ms = max(0, int(seconds * 1000))
    script = f"""
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$ErrorActionPreference = 'Stop'
$result = [ordered]@{{ port = {ps_quote(port)}; ok = $false; error = $null; log = "" }}
$sp = $null
try {{
  $sp = [System.IO.Ports.SerialPort]::new({ps_quote(port)}, 115200, [System.IO.Ports.Parity]::None, 8, [System.IO.Ports.StopBits]::One)
  $sp.ReadTimeout = 500
  $sp.WriteTimeout = 500
  $sp.DtrEnable = $false
  $sp.RtsEnable = $false
  $sp.Open()
  Start-Sleep -Milliseconds {sleep_ms}
  $log = $sp.ReadExisting()
  if ($log.Length -gt 4000) {{
    $log = $log.Substring(0, 4000) + "...[truncated]"
  }}
  $result.log = $log
  $result.ok = $true
}} catch {{
  $result.error = $_.Exception.Message
}} finally {{
  if ($sp -and $sp.IsOpen) {{ $sp.Close() }}
}}
$result | ConvertTo-Json -Depth 5
"""
    raw = run_powershell(script, timeout_seconds=max(5, int(seconds) + 5))
    return json.loads(raw)


def parse_sim_probe(result: dict[str, Any]) -> dict[str, Any]:
    probe = result.get("probe", {})
    responses = probe.get("responses", [])
    combined = "\n".join(str(item.get("response") or "") for item in responses)
    model = match_text(r"Model:\s*([^\r\n]+)", combined)
    revision = match_text(r"Revision:\s*([^\r\n]+)", combined)
    imei = match_text(r"IMEI:\s*([0-9]+)", combined)
    csq = match_text(r"\+CSQ:\s*([0-9]+),([0-9]+)", combined)
    cpin_not_inserted = "SIM not inserted" in combined
    registered = bool(re.search(r"\+CEREG:\s*\d,([15])\b", combined))
    attached = bool(re.search(r"\+CGATT:\s*1\b", combined))
    return {
        "port": probe.get("port"),
        "ok": bool(probe.get("ok")),
        "error": probe.get("error"),
        "model": model,
        "revision": revision,
        "imei_present": bool(imei),
        "csq": csq,
        "sim_not_inserted": cpin_not_inserted,
        "registered": registered,
        "packet_attached": attached,
        "is_sim7670g": bool(model and "SIM7670G" in model.upper()),
    }


def parse_esp_log(log: str) -> dict[str, Any]:
    return {
        "has_log": bool(log.strip()),
        "boot_rom_seen": "ESP-ROM:esp32s3" in log,
        "sha256_warning": "SHA-256 comparison failed" in log,
        "camera_init_ok": "Camera init successful" in log,
        "sd_mount_failed": bool(re.search(r"Card Mount Failed|sdmmc_card_init failed|mount_to_vfs failed", log, re.I)),
        "sd_mount_ok": bool(re.search(r"Card Mount Successful|SD card mounted|card mounted", log, re.I)),
    }


def evaluate_checks(
    *,
    serial_ports: list[SerialPortInfo],
    net_adapters: list[dict[str, Any]],
    esp_candidate: SerialPortInfo | None,
    esp_error: str | None,
    esp_log: str,
    parsed_esp: dict[str, Any],
    parsed_sim: list[dict[str, Any]],
) -> list[CheckResult]:
    checks: list[CheckResult] = []
    checks.append(
        pass_fail(
            "esp32_ch343_serial_present",
            esp_candidate is not None,
            f"ESP32-S3 CH343 port: {esp_candidate.port if esp_candidate else 'not found'}",
        )
    )
    sim_ports = [item for item in serial_ports if item.role.startswith("sim7670")]
    checks.append(
        pass_fail(
            "sim7670_usb_serial_present",
            bool(sim_ports),
            f"SIM7670G serial ports: {', '.join(item.port for item in sim_ports) or 'not found'}",
        )
    )
    rndis = [item for item in net_adapters if "RNDIS" in str(item.get("InterfaceDescription", "")).upper()]
    checks.append(
        pass_fail(
            "sim7670_rndis_adapter_present",
            bool(rndis),
            f"RNDIS adapters: {', '.join(item.get('Name', '') for item in rndis) or 'not found'}",
        )
    )
    identity_ports = [item["port"] for item in parsed_sim if item.get("is_sim7670g")]
    checks.append(
        pass_fail(
            "sim7670_at_identity",
            bool(identity_ports),
            f"AT identity on: {', '.join(identity_ports) or 'none'}",
        )
    )
    sim_absent_ports = [item["port"] for item in parsed_sim if item.get("sim_not_inserted")]
    checks.append(
        CheckResult(
            "sim_card_absent_expected",
            "PASS" if sim_absent_ports else "WARN",
            (
                "SIM not inserted reported as expected on "
                + (", ".join(sim_absent_ports) if sim_absent_ports else "no AT port")
            ),
        )
    )
    if esp_error:
        checks.append(CheckResult("esp32_serial_log_read", "WARN", esp_error))
    elif parsed_esp["has_log"]:
        checks.append(CheckResult("esp32_serial_log_read", "PASS", "ESP32 log captured."))
    else:
        checks.append(
            CheckResult(
                "esp32_serial_log_read",
                "WARN",
                "No ESP32 log captured during listen window; press reset while probing to capture boot logs.",
            )
        )

    if parsed_esp["sd_mount_failed"]:
        checks.append(CheckResult("sd_card_mount", "FAIL", "ESP32 log reports SD card mount failure."))
    elif parsed_esp["sd_mount_ok"]:
        checks.append(CheckResult("sd_card_mount", "PASS", "ESP32 log reports SD card mounted."))
    else:
        checks.append(
            CheckResult(
                "sd_card_mount",
                "WARN",
                "SD mount status not observed in current ESP32 log window.",
            )
        )
    if parsed_esp["camera_init_ok"]:
        checks.append(CheckResult("camera_init_current_firmware", "PASS", "Current firmware reports camera init successful."))
    elif esp_log.strip():
        checks.append(CheckResult("camera_init_current_firmware", "WARN", "Camera init success not observed."))
    return checks


def render_markdown_report(report: dict[str, Any]) -> str:
    checks = report["checks"]
    lines = [
        "# Ego Link P0 Board Validation Report",
        "",
        f"- Generated: `{report['started_at']}`",
        f"- Platform: `{report['host']['platform']}`",
        f"- Python: `{report['host']['python']}`",
        "",
        "## Quality Gates",
        "",
        "| Check | Status | Detail |",
        "|---|---:|---|",
    ]
    for item in checks:
        lines.append(f"| `{item['check']}` | {item['status']} | {escape_table(item['detail'])} |")
    lines.extend(["", "## Serial Ports", "", "| Port | Role | Name | PNP |", "|---|---|---|---|"])
    for item in report["serial_ports"]:
        lines.append(
            f"| `{item['port']}` | `{item['role']}` | {escape_table(item['name'])} | `{escape_table(item['pnp_device_id'])}` |"
        )
    lines.extend(["", "## SIM7670G AT Summary", ""])
    for item in report["parsed_sim"]:
        lines.append(
            f"- `{item['port']}`: model=`{item.get('model')}`, "
            f"sim_not_inserted={item.get('sim_not_inserted')}, "
            f"csq=`{item.get('csq')}`, registered={item.get('registered')}, "
            f"attached={item.get('packet_attached')}"
        )
    lines.extend(["", "## ESP32 Log Summary", ""])
    esp = report["esp_probe"]["parsed"]
    lines.append(f"- has_log: `{esp['has_log']}`")
    lines.append(f"- boot_rom_seen: `{esp['boot_rom_seen']}`")
    lines.append(f"- camera_init_ok: `{esp['camera_init_ok']}`")
    lines.append(f"- sd_mount_failed: `{esp['sd_mount_failed']}`")
    lines.append(f"- sd_mount_ok: `{esp['sd_mount_ok']}`")
    if report["esp_probe"]["log_excerpt"]:
        lines.extend(["", "```text", report["esp_probe"]["log_excerpt"], "```"])
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- This probe is non-destructive. It does not dial, start PPP, place calls, or change modem settings.",
            "- If ESP32 SD status is not observed, rerun the probe and press the board reset button during the listen window.",
            "- P0 firmware should keep business logic behind LinkTransport, ModemDriver, GnssDriver, WakeDriver, and PowerDriver abstractions.",
            "",
        ]
    )
    return "\n".join(lines)


def pass_fail(check: str, condition: bool, detail: str) -> CheckResult:
    return CheckResult(check, "PASS" if condition else "FAIL", detail)


def run_powershell(script: str, timeout_seconds: int = 15) -> str:
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
    )
    return completed.stdout.strip()


def ensure_list(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def parse_usb_mi(pnp_device_id: str) -> str | None:
    match = re.search(r"&MI_([0-9A-Fa-f]{2})\\", pnp_device_id)
    return match.group(1).upper() if match else None


def match_text(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text)
    if not match:
        return None
    if len(match.groups()) == 1:
        return match.group(1).strip()
    return ",".join(group.strip() for group in match.groups())


def ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def truncate_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "...[truncated]"


def escape_table(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def timestamp_for_path() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


if __name__ == "__main__":
    raise SystemExit(main())

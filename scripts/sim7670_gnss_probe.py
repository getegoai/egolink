"""Probe SIM7670G GNSS over USB AT and write a PC Simulator event."""

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

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pc_simulator import event_store, protocol
from scripts.egolink_board_probe import (
    SerialPortInfo,
    choose_sim_ports,
    discover_serial_ports,
    ps_quote,
    truncate_text,
)


DEFAULT_OUTPUT_DIR = Path("reports") / "gnss_validation"
DEFAULT_EVENT_LOG = Path(__file__).resolve().parents[1] / "pc_simulator" / "runtime" / "events.jsonl"
GNSS_QUERY_COMMANDS = ("AT+CGNSSINFO", "AT+CGPSINFO")
KNOT_TO_MPS = 0.514444


@dataclass(frozen=True)
class AtCommand:
    command: str
    delay_ms: int


@dataclass(frozen=True)
class GnssFix:
    fix: bool
    source_command: str | None
    raw_line: str | None
    lat: float | None = None
    lon: float | None = None
    altitude_m: float | None = None
    speed_mps: float | None = None
    course_deg: float | None = None
    pdop: float | None = None
    hdop: float | None = None
    vdop: float | None = None
    satellites: int | None = None
    utc_date: str | None = None
    utc_time: str | None = None


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = run_probe(
        sim_ports=args.sim_ports,
        probe_all_sim_ports=args.probe_all_sim_ports,
        power_on=not args.no_power_on,
        warmup_seconds=args.warmup_seconds,
        poll_count=args.poll_count,
        poll_interval_seconds=args.poll_interval_seconds,
        output_dir=args.output_dir,
        event_log=args.event_log,
        write_event=not args.no_write_event,
        device_id=args.device_id,
    )
    print(report["markdown_path"])
    if report.get("event_path"):
        print(report["event_path"])
    return 0 if report["summary"]["at_ok"] else 2


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sim-port",
        dest="sim_ports",
        action="append",
        default=[],
        help="SIM7670G AT port to probe. Can be repeated. Defaults to auto-detected AT candidates.",
    )
    parser.add_argument(
        "--probe-all-sim-ports",
        action="store_true",
        help="Probe every VID_05C6 PID_9330 serial port instead of only AT candidates.",
    )
    parser.add_argument(
        "--no-power-on",
        action="store_true",
        help="Skip AT+CGNSSPWR=1 and only query the current GNSS state.",
    )
    parser.add_argument("--warmup-seconds", type=float, default=3.0)
    parser.add_argument("--poll-count", type=int, default=3)
    parser.add_argument("--poll-interval-seconds", type=float, default=2.0)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--event-log", type=Path, default=DEFAULT_EVENT_LOG)
    parser.add_argument("--no-write-event", action="store_true")
    parser.add_argument("--device-id", default=protocol.DEVICE_ID)
    return parser.parse_args(argv)


def run_probe(
    *,
    sim_ports: list[str],
    probe_all_sim_ports: bool,
    power_on: bool,
    warmup_seconds: float,
    poll_count: int,
    poll_interval_seconds: float,
    output_dir: Path,
    event_log: Path,
    write_event: bool,
    device_id: str,
) -> dict[str, Any]:
    started_at = utc_now()
    serial_ports = discover_serial_ports()
    candidates = choose_sim_ports(serial_ports, sim_ports, probe_all_sim_ports)
    port_results = []
    for port_info in candidates:
        probe = probe_gnss_at_port(
            port_info.port,
            power_on=power_on,
            warmup_seconds=warmup_seconds,
            poll_count=poll_count,
            poll_interval_seconds=poll_interval_seconds,
        )
        parsed = parse_gnss_probe(probe)
        port_results.append(
            {
                "port_info": asdict(port_info),
                "probe": probe,
                "parsed": parsed,
            }
        )

    best = select_best_result(port_results)
    event = None
    if best is not None and best["parsed"]["at_ok"]:
        seq = next_seq_from_event_log(event_log)
        event = location_event_from_parsed(best["parsed"], device_id=device_id, seq=seq)
        if write_event:
            event_store.append_jsonl(event_log, event)

    summary = {
        "at_ok": bool(best and best["parsed"]["at_ok"]),
        "fix": bool(best and best["parsed"]["fix"]["fix"]),
        "event_written": bool(write_event and event is not None),
        "candidate_ports": [item.port for item in candidates],
        "selected_port": best["parsed"]["port"] if best else None,
    }

    payload: dict[str, Any] = {
        "project": "Ego Link P0",
        "started_at": started_at,
        "host": {"platform": platform.platform(), "python": sys.version.split()[0]},
        "power_on": power_on,
        "warmup_seconds": warmup_seconds,
        "poll_count": poll_count,
        "poll_interval_seconds": poll_interval_seconds,
        "serial_ports": [asdict(item) for item in serial_ports],
        "port_results": port_results,
        "summary": summary,
        "event": event,
        "event_path": str(event_log) if event is not None and write_event else None,
    }
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = output_dir / stamp
    run_dir.mkdir(parents=True, exist_ok=True)
    json_path = run_dir / "gnss_probe.json"
    markdown_path = run_dir / "gnss_probe.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), "utf-8")
    markdown_path.write_text(render_markdown_report(payload), "utf-8")
    payload["json_path"] = str(json_path)
    payload["markdown_path"] = str(markdown_path)
    return payload


def probe_gnss_at_port(
    port: str,
    *,
    power_on: bool,
    warmup_seconds: float,
    poll_count: int,
    poll_interval_seconds: float,
) -> dict[str, Any]:
    commands = build_command_sequence(
        power_on=power_on,
        warmup_seconds=warmup_seconds,
        poll_count=poll_count,
        poll_interval_seconds=poll_interval_seconds,
    )
    command_rows = "@(" + ",".join(
        f"[pscustomobject]@{{ Command = {ps_quote(item.command)}; DelayMs = {item.delay_ms} }}"
        for item in commands
    ) + ")"
    script = f"""
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$ErrorActionPreference = 'Stop'
$result = [ordered]@{{ port = {ps_quote(port)}; ok = $false; error = $null; responses = @() }}
$sp = $null
try {{
  $sp = [System.IO.Ports.SerialPort]::new({ps_quote(port)}, 115200, [System.IO.Ports.Parity]::None, 8, [System.IO.Ports.StopBits]::One)
  $sp.ReadTimeout = 1000
  $sp.WriteTimeout = 1000
  $sp.NewLine = "`r`n"
  $sp.DtrEnable = $false
  $sp.RtsEnable = $false
  $sp.Open()
  Start-Sleep -Milliseconds 150
  $sp.DiscardInBuffer()
  foreach ($entry in {command_rows}) {{
    if ($entry.Command -eq '__sleep__') {{
      Start-Sleep -Milliseconds $entry.DelayMs
      continue
    }}
    $sp.Write("$($entry.Command)`r")
    Start-Sleep -Milliseconds $entry.DelayMs
    $response = $sp.ReadExisting()
    if ($response.Length -gt 2200) {{
      $response = $response.Substring(0, 2200) + "...[truncated]"
    }}
    $result.responses += [ordered]@{{ command = $entry.Command; response = $response }}
  }}
  $result.ok = $true
}} catch {{
  $result.error = $_.Exception.Message
}} finally {{
  if ($sp -and $sp.IsOpen) {{ $sp.Close() }}
}}
$result | ConvertTo-Json -Depth 7
"""
    timeout_seconds = max(12, int(warmup_seconds + poll_count * (2 + poll_interval_seconds)) + 10)
    raw = run_powershell(script, timeout_seconds=timeout_seconds)
    return json.loads(raw)


def build_command_sequence(
    *,
    power_on: bool,
    warmup_seconds: float,
    poll_count: int,
    poll_interval_seconds: float,
) -> list[AtCommand]:
    warmup_ms = max(0, int(warmup_seconds * 1000))
    poll_interval_ms = max(0, int(poll_interval_seconds * 1000))
    commands = [
        AtCommand("AT", 250),
        AtCommand("ATI", 500),
        AtCommand("AT+CGNSSPWR?", 500),
    ]
    if power_on:
        commands.append(AtCommand("AT+CGNSSPWR=1", max(1200, warmup_ms)))
    commands.append(AtCommand("AT+CGNSSPWR?", 500))
    for index in range(max(1, poll_count)):
        commands.extend(AtCommand(command, 800) for command in GNSS_QUERY_COMMANDS)
        if index < max(1, poll_count) - 1 and poll_interval_ms:
            commands.append(AtCommand("__sleep__", poll_interval_ms))
    return commands


def parse_gnss_probe(probe: dict[str, Any]) -> dict[str, Any]:
    responses = ensure_list(probe.get("responses"))
    combined = "\n".join(str(item.get("response") or "") for item in responses)
    fix = parse_gnss_responses(responses)
    model = match_text(r"Model:\s*([^\r\n]+)", combined)
    revision = match_text(r"Revision:\s*([^\r\n]+)", combined)
    power_state = match_last_text(r"\+CGNSSPWR:\s*([0-9]+)", combined)
    return {
        "port": probe.get("port"),
        "ok": bool(probe.get("ok")),
        "error": probe.get("error"),
        "at_ok": bool(probe.get("ok")) and ("OK" in combined or "SIMCOM" in combined.upper()),
        "model": model,
        "revision": revision,
        "is_sim7670g": bool(model and "SIM7670G" in model.upper()),
        "gnss_power_state": power_state,
        "fix": asdict(fix),
    }


def parse_gnss_responses(responses: Iterable[dict[str, Any]]) -> GnssFix:
    parsed: list[GnssFix] = []
    for item in responses:
        command = str(item.get("command") or "")
        response = str(item.get("response") or "")
        for line in response.splitlines():
            parsed_fix = parse_gnss_line(line, command)
            if parsed_fix is not None:
                parsed.append(parsed_fix)
    return next((item for item in parsed if item.fix), parsed[0] if parsed else GnssFix(False, None, None))


def parse_gnss_line(line: str, command: str) -> GnssFix | None:
    stripped = line.strip()
    if stripped.startswith("+CGNSSINFO:"):
        return parse_cgnssinfo(stripped, command)
    if stripped.startswith("+CGPSINFO:"):
        return parse_cgpsinfo(stripped, command)
    return None


def parse_cgpsinfo(line: str, command: str = "AT+CGPSINFO") -> GnssFix:
    fields = split_at_payload(line, "+CGPSINFO:")
    lat = parse_coordinate(get_field(fields, 0), get_field(fields, 1), kind="lat")
    lon = parse_coordinate(get_field(fields, 2), get_field(fields, 3), kind="lon")
    speed_knots = parse_float(get_field(fields, 7))
    return GnssFix(
        fix=lat is not None and lon is not None,
        source_command=command,
        raw_line=line,
        lat=lat,
        lon=lon,
        altitude_m=parse_float(get_field(fields, 6)),
        speed_mps=round(speed_knots * KNOT_TO_MPS, 3) if speed_knots is not None else None,
        course_deg=parse_float(get_field(fields, 8)),
        utc_date=empty_to_none(get_field(fields, 4)),
        utc_time=empty_to_none(get_field(fields, 5)),
    )


def parse_cgnssinfo(line: str, command: str = "AT+CGNSSINFO") -> GnssFix:
    fields = split_at_payload(line, "+CGNSSINFO:")
    lat_index, ns_index, lon_index, ew_index = choose_cgnss_coordinate_fields(fields)
    lat = parse_coordinate(get_field(fields, lat_index), get_field(fields, ns_index), kind="lat")
    lon = parse_coordinate(get_field(fields, lon_index), get_field(fields, ew_index), kind="lon")
    speed_knots = parse_float(get_field(fields, 12))
    return GnssFix(
        fix=lat is not None and lon is not None,
        source_command=command,
        raw_line=line,
        lat=lat,
        lon=lon,
        altitude_m=parse_float(get_field(fields, 11)),
        speed_mps=round(speed_knots * KNOT_TO_MPS, 3) if speed_knots is not None else None,
        course_deg=parse_float(get_field(fields, 13)),
        pdop=parse_float(get_field(fields, 14)),
        hdop=parse_float(get_field(fields, 15)),
        vdop=parse_float(get_field(fields, 16)),
        satellites=parse_int(get_field(fields, 17)),
        utc_date=empty_to_none(get_field(fields, 9)),
        utc_time=empty_to_none(get_field(fields, 10)),
    )


def choose_cgnss_coordinate_fields(fields: list[str]) -> tuple[int, int | None, int, int | None]:
    for candidate in ((5, 6, 7, 8), (4, 5, 6, 7)):
        if get_field(fields, candidate[1]).upper() in {"N", "S"} and get_field(fields, candidate[3]).upper() in {"E", "W"}:
            return candidate
    return (3, None, 4, None)


def split_at_payload(line: str, prefix: str) -> list[str]:
    _, _, payload = line.partition(prefix)
    return [field.strip() for field in payload.strip().split(",")]


def location_event_from_parsed(parsed: dict[str, Any], *, device_id: str, seq: int) -> dict[str, Any]:
    fix = parsed["fix"]
    payload: dict[str, Any] = {
        "source": "sim7670g_gnss",
        "fix": bool(fix.get("fix")),
        "gnss_state": "fix" if fix.get("fix") else "no_fix",
        "port": parsed.get("port"),
        "gnss_power_state": parsed.get("gnss_power_state"),
        "raw_command": fix.get("source_command"),
        "raw_response": truncate_text(str(fix.get("raw_line") or ""), 240),
    }
    for key in (
        "lat",
        "lon",
        "altitude_m",
        "speed_mps",
        "course_deg",
        "pdop",
        "hdop",
        "vdop",
        "satellites",
        "utc_date",
        "utc_time",
    ):
        if fix.get(key) is not None:
            payload[key] = fix[key]
    return protocol.event_message(
        device_id,
        utc_now(),
        seq,
        "location_report",
        "normal",
        **payload,
    )


def select_best_result(port_results: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not port_results:
        return None
    fixed = [item for item in port_results if item["parsed"]["fix"]["fix"]]
    if fixed:
        return fixed[0]
    at_ok = [item for item in port_results if item["parsed"]["at_ok"]]
    if at_ok:
        return at_ok[0]
    return port_results[0]


def render_markdown_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Ego Link P0 GNSS Probe Report",
        "",
        f"- Generated: `{report['started_at']}`",
        f"- Platform: `{report['host']['platform']}`",
        f"- Power on requested: `{report['power_on']}`",
        f"- Candidate ports: `{', '.join(summary['candidate_ports']) or 'none'}`",
        f"- Selected port: `{summary['selected_port']}`",
        f"- AT reachable: `{summary['at_ok']}`",
        f"- GNSS fix: `{summary['fix']}`",
        f"- Event written: `{summary['event_written']}`",
        "",
        "## Port Results",
        "",
    ]
    for item in report["port_results"]:
        parsed = item["parsed"]
        fix = parsed["fix"]
        lines.extend(
            [
                f"### `{parsed['port']}`",
                "",
                f"- at_ok: `{parsed['at_ok']}`",
                f"- model: `{parsed.get('model')}`",
                f"- gnss_power_state: `{parsed.get('gnss_power_state')}`",
                f"- fix: `{fix.get('fix')}`",
                f"- lat/lon: `{fix.get('lat')}`, `{fix.get('lon')}`",
                f"- raw: `{escape_inline(fix.get('raw_line'))}`",
                "",
            ]
        )
    if report.get("event"):
        lines.extend(["## Event", "", "```json", json.dumps(report["event"], indent=2, ensure_ascii=False), "```", ""])
    lines.extend(
        [
            "## Notes",
            "",
            "- This probe can turn GNSS on with `AT+CGNSSPWR=1` unless `--no-power-on` is used.",
            "- No fix is not a hard failure indoors; the script still writes a `location_report` event with `fix=false`.",
            "- Keep long cold-start fix tests as a hardware gate, not a unit-test requirement.",
            "",
        ]
    )
    return "\n".join(lines)


def next_seq_from_event_log(path: Path) -> int:
    if not path.exists():
        return 1
    max_seq = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
            max_seq = max(max_seq, int(event.get("seq", 0)))
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
    return max_seq + 1


def parse_coordinate(value: str | None, hemisphere: str | None = None, *, kind: str) -> float | None:
    if value is None or not value.strip():
        return None
    try:
        number = float(value)
    except ValueError:
        return None

    abs_number = abs(number)
    max_decimal = 90 if kind == "lat" else 180
    if abs_number > max_decimal:
        degrees = int(abs_number // 100)
        minutes = abs_number - degrees * 100
        coordinate = degrees + minutes / 60
        if number < 0:
            coordinate = -coordinate
    else:
        coordinate = number

    hemi = (hemisphere or "").upper()
    if hemi in {"S", "W"}:
        coordinate = -abs(coordinate)
    elif hemi in {"N", "E"}:
        coordinate = abs(coordinate)
    return round(coordinate, 6)


def run_powershell(script: str, timeout_seconds: int) -> str:
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


def get_field(fields: list[str], index: int | None) -> str:
    if index is None or index >= len(fields):
        return ""
    return fields[index].strip()


def empty_to_none(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    return value.strip()


def parse_float(value: str | None) -> float | None:
    if value is None or not value.strip():
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_int(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def match_text(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text)
    return match.group(1).strip() if match else None


def match_last_text(pattern: str, text: str) -> str | None:
    matches = list(re.finditer(pattern, text))
    return matches[-1].group(1).strip() if matches else None


def escape_inline(value: Any) -> str:
    return str(value or "").replace("`", "'").replace("\r", " ").replace("\n", " ")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())

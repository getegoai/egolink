"""Diagnose SIM7670G LTE HTTP AT reachability through the USB AT port.

This script is for LTE-002 failure triage after USB-Free validation reports no
fresh LTE HTTP telemetry. It opens bounded SIM7670G USB AT sessions only. It
does not flash firmware, erase flash, enqueue Message Hub commands, place
calls, or use bearer tokens. The default HTTP check is a public Message Hub
`/health` GET.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
from typing import Any, Iterable

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.egolink_board_probe import (  # noqa: E402
    SerialPortInfo,
    choose_sim_ports,
    discover_serial_ports,
    ps_quote,
    timestamp_for_path,
    truncate_text,
)


DEFAULT_HUB_BASE_URL = "http://203.0.113.10:8790"
DEFAULT_URL = f"{DEFAULT_HUB_BASE_URL}/health"
DEFAULT_DEVICE_ID = "ego-link-r1-connectivity-001"
DEFAULT_OUTPUT_DIR = Path("reports") / "field_validation" / "lte002-atdiag-http"


@dataclass(frozen=True)
class AtStep:
    command: str
    label: str
    wait_ms: int = 150
    read_window_ms: int = 1200
    stop_pattern: str = "OK|ERROR"
    optional: bool = False
    data: str | None = None
    log_command: str | None = None


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    bearer_token, token_source = load_bearer_token(args.token_env, args.token_file) if args.mode == "telemetry-post-auth" else (None, None)
    report = run_diagnostic(
        sim_ports=args.sim_ports,
        probe_all_sim_ports=args.probe_all_sim_ports,
        url=resolve_url(args.mode, args.url, args.device_id),
        mode=args.mode,
        device_id=args.device_id,
        bearer_token=bearer_token,
        token_source=token_source,
        include_cid=args.include_cid,
        payload_padding_bytes=args.payload_padding_bytes,
        output_dir=args.output_dir,
        action_timeout_sec=args.action_timeout_sec,
    )
    print(report["markdown_path"])
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["summary"]["result"] == "PASS" else 2


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
        "--url",
        help="HTTP URL for the SIM7670G AT check. Defaults depend on --mode.",
    )
    parser.add_argument(
        "--mode",
        choices=("health-get", "telemetry-post-unauth", "telemetry-post-auth"),
        default="health-get",
        help="Run a public /health GET, an unauthenticated telemetry POST, or a bearer-auth telemetry POST smoke.",
    )
    parser.add_argument(
        "--device-id",
        default=DEFAULT_DEVICE_ID,
        help="Device ID used to build the default unauthenticated telemetry POST URL.",
    )
    parser.add_argument(
        "--include-cid",
        action="store_true",
        help='Include AT+HTTPPARA="CID",1 before URL setup for comparison runs.',
    )
    parser.add_argument("--action-timeout-sec", type=float, default=60.0)
    parser.add_argument(
        "--payload-padding-bytes",
        type=int,
        default=0,
        help="Append a deterministic padding field to POST payloads to test larger HTTPDATA bodies.",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--token-env", default="EGOLINK_MESSAGE_HUB_TOKEN")
    parser.add_argument("--token-file", type=Path, default=Path("server") / "runtime" / "vps_message_hub_token.txt")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def run_diagnostic(
    *,
    sim_ports: list[str],
    probe_all_sim_ports: bool,
    url: str,
    mode: str,
    device_id: str,
    bearer_token: str | None,
    token_source: str | None,
    include_cid: bool,
    payload_padding_bytes: int,
    output_dir: Path,
    action_timeout_sec: float,
) -> dict[str, Any]:
    started_at = utc_now()
    serial_ports = discover_serial_ports()
    candidates = choose_sim_ports(serial_ports, sim_ports, probe_all_sim_ports)
    port_preflights: list[dict[str, Any]] = []
    for port_info in candidates:
        probe = run_at_sequence(port_info.port, build_status_steps(), timeout_seconds=18)
        parsed = parse_status_probe(probe)
        port_preflights.append(
            {
                "port_info": asdict(port_info),
                "probe": probe,
                "parsed": parsed,
            }
        )

    selected = select_http_port(port_preflights)
    http_probe: dict[str, Any] | None = None
    parsed_http: dict[str, Any] = {}
    if selected is not None:
        http_steps = build_http_steps(
            url,
            mode=mode,
            device_id=device_id,
            bearer_token=bearer_token,
            include_cid=include_cid,
            payload_padding_bytes=payload_padding_bytes,
            action_timeout_sec=action_timeout_sec,
        )
        timeout_seconds = sequence_timeout_seconds(http_steps, floor=25)
        http_probe = run_at_sequence(
            selected["parsed"]["port"],
            http_steps,
            timeout_seconds=timeout_seconds,
            auth_header=f"Authorization: Bearer {bearer_token}" if bearer_token else None,
        )
        parsed_http = parse_http_probe(http_probe, mode=mode)

    summary = summarize_run(
        candidates=candidates,
        port_preflights=port_preflights,
        selected=selected,
        parsed_http=parsed_http,
        url=url,
        mode=mode,
        include_cid=include_cid,
    )
    payload: dict[str, Any] = {
        "project": "Ego Link P0",
        "task_id": "LTE-002",
        "diagnostic": "sim7670g_lte_http_at",
        "started_at": started_at,
        "host": {"platform": platform.platform(), "python": sys.version.split()[0]},
        "url": url,
        "mode": mode,
        "device_id": device_id,
        "token_source": token_source,
        "auth_header_length": len(f"Authorization: Bearer {bearer_token}") if bearer_token else None,
        "include_cid": include_cid,
        "payload_padding_bytes": payload_padding_bytes,
        "action_timeout_sec": action_timeout_sec,
        "serial_ports": [asdict(item) for item in serial_ports],
        "candidate_ports": [asdict(item) for item in candidates],
        "port_preflights": port_preflights,
        "selected_port": selected["parsed"]["port"] if selected else None,
        "http_probe": http_probe,
        "parsed_http": parsed_http,
        "summary": summary,
    }
    stamp = timestamp_for_path()
    run_dir = output_dir / stamp
    run_dir.mkdir(parents=True, exist_ok=True)
    json_path = run_dir / "lte_http_at_diag.json"
    markdown_path = run_dir / "lte_http_at_diag.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    markdown_path.write_text(render_markdown_report(payload), encoding="utf-8")
    payload["json_path"] = str(json_path)
    payload["markdown_path"] = str(markdown_path)
    return payload


def build_status_steps() -> list[AtStep]:
    return [
        AtStep("AT", "AT", read_window_ms=900),
        AtStep("ATI", "ATI", read_window_ms=1400),
        AtStep("AT+CPIN?", "CPIN"),
        AtStep("AT+COPS?", "COPS"),
        AtStep("AT+CEREG?", "CEREG"),
        AtStep("AT+CGATT?", "CGATT"),
        AtStep("AT+CGDCONT?", "CGDCONT", read_window_ms=1500),
        AtStep("AT+CGACT?", "CGACT", read_window_ms=1500),
        AtStep("AT+CGPADDR=1", "CGPADDR", read_window_ms=1500),
        AtStep("AT+CSQ", "CSQ"),
        AtStep("AT+CPSI?", "CPSI", read_window_ms=1800),
        AtStep("AT+NETOPEN?", "NETOPEN", optional=True),
        AtStep("AT+CNACT?", "CNACT", optional=True),
    ]


def resolve_url(mode: str, url: str | None, device_id: str) -> str:
    if url:
        return url
    if mode in {"telemetry-post-unauth", "telemetry-post-auth"}:
        return f"{DEFAULT_HUB_BASE_URL}/api/v1/devices/{device_id}/telemetry"
    return DEFAULT_URL


def build_http_get_steps(url: str, *, include_cid: bool, action_timeout_sec: float) -> list[AtStep]:
    return build_http_steps(
        url,
        mode="health-get",
        device_id=DEFAULT_DEVICE_ID,
        bearer_token=None,
        include_cid=include_cid,
        payload_padding_bytes=0,
        action_timeout_sec=action_timeout_sec,
    )


def build_http_steps(
    url: str,
    *,
    mode: str,
    device_id: str,
    bearer_token: str | None,
    include_cid: bool,
    payload_padding_bytes: int,
    action_timeout_sec: float,
) -> list[AtStep]:
    steps = [
        AtStep("AT", "AT", read_window_ms=900),
        AtStep("AT+HTTPTERM", "HTTPTERM_PRE", read_window_ms=1200, optional=True),
        AtStep("AT+HTTPINIT", "HTTPINIT", read_window_ms=2500),
    ]
    if include_cid:
        steps.append(AtStep('AT+HTTPPARA="CID",1', "HTTPPARA_CID", read_window_ms=1800))
    steps.append(AtStep(f'AT+HTTPPARA="URL","{url}"', "HTTPPARA_URL", read_window_ms=2500))
    if mode in {"telemetry-post-unauth", "telemetry-post-auth"}:
        payload = telemetry_post_probe_payload(device_id, padding_bytes=payload_padding_bytes)
        steps.append(AtStep('AT+HTTPPARA="CONTENT","application/json"', "HTTPPARA_CONTENT", read_window_ms=1800))
        if mode == "telemetry-post-auth":
            if not bearer_token:
                raise ValueError("telemetry-post-auth requires a bearer token")
            steps.append(
                AtStep(
                    "__EGOLINK_AUTH_USERDATA__",
                    "HTTPPARA_USERDATA",
                    read_window_ms=1800,
                    log_command='AT+HTTPPARA="USERDATA","Authorization: Bearer [REDACTED_SECRET]"',
                )
            )
        steps.extend(
            [
                AtStep(
                    f"AT+HTTPDATA={len(payload)},10000",
                    "HTTPDATA",
                    wait_ms=150,
                    read_window_ms=10000,
                    stop_pattern="DOWNLOAD|ERROR",
                    data=payload,
                ),
                AtStep(
                    "AT+HTTPACTION=1",
                    "HTTPACTION_POST",
                    wait_ms=250,
                    read_window_ms=max(1000, int(action_timeout_sec * 1000)),
                    stop_pattern=r"\+HTTPACTION:",
                ),
                AtStep("AT+HTTPREAD", "HTTPREAD", read_window_ms=3500),
                AtStep("AT+HTTPTERM", "HTTPTERM_POST", read_window_ms=1200, optional=True),
            ]
        )
        return steps
    steps.extend(
        [
            AtStep(
                "AT+HTTPACTION=0",
                "HTTPACTION_GET",
                wait_ms=250,
                read_window_ms=max(1000, int(action_timeout_sec * 1000)),
                stop_pattern=r"\+HTTPACTION:",
            ),
            AtStep("AT+HTTPREAD", "HTTPREAD", read_window_ms=3500),
            AtStep("AT+HTTPTERM", "HTTPTERM_POST", read_window_ms=1200, optional=True),
        ]
    )
    return steps


def telemetry_post_probe_payload(device_id: str, *, padding_bytes: int = 0) -> str:
    payload = {
        "device_id": device_id,
        "schema_version": "egolink.p0.v1",
        "message_type": "event",
        "event_type": "lte_http_at_diag",
        "severity": "normal",
        "timestamp": "pc_at_diag",
        "seq": 0,
        "source": "pc_sim7670_usb_at",
    }
    if padding_bytes > 0:
        payload["padding"] = "x" * padding_bytes
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=True)


def sequence_timeout_seconds(steps: Iterable[AtStep], *, floor: int) -> int:
    total_ms = 0
    for step in steps:
        total_ms += max(0, step.wait_ms) + max(0, step.read_window_ms)
        if step.data:
            total_ms += max(0, step.read_window_ms)
    return max(floor, int(total_ms / 1000) + 12)


def run_at_sequence(
    port: str,
    steps: Iterable[AtStep],
    *,
    timeout_seconds: int,
    auth_header: str | None = None,
) -> dict[str, Any]:
    step_rows = "@(" + ",".join(ps_step_row(item) for item in steps) + ")"
    script = f"""
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$ErrorActionPreference = 'Stop'
$result = [ordered]@{{ port = {ps_quote(port)}; ok = $false; error = $null; responses = @() }}
$sp = $null
try {{
  $sp = [System.IO.Ports.SerialPort]::new({ps_quote(port)}, 115200, [System.IO.Ports.Parity]::None, 8, [System.IO.Ports.StopBits]::One)
  $sp.ReadTimeout = 250
  $sp.WriteTimeout = 1200
  $sp.NewLine = "`r`n"
  $sp.DtrEnable = $false
  $sp.RtsEnable = $false
  $sp.Open()
  Start-Sleep -Milliseconds 180
  $sp.DiscardInBuffer()
  foreach ($entry in {step_rows}) {{
    $response = ""
    $matched = $false
    $cmd = $entry.Command
    if ($cmd -eq "__EGOLINK_AUTH_USERDATA__") {{
      $cmd = "AT+HTTPPARA=`"USERDATA`",`"$env:EGOLINK_AT_AUTH_HEADER`""
    }}
    $logCommand = $entry.LogCommand
    if (-not $logCommand) {{
      $logCommand = $cmd
    }}
    $sp.Write("$cmd`r")
    if ($entry.WaitMs -gt 0) {{
      Start-Sleep -Milliseconds $entry.WaitMs
    }}
    $deadline = [DateTime]::UtcNow.AddMilliseconds($entry.ReadWindowMs)
    while ([DateTime]::UtcNow -lt $deadline) {{
      $chunk = $sp.ReadExisting()
      if ($chunk.Length -gt 0) {{
        $response += $chunk
      }}
      if ($entry.StopPattern -and $response -match $entry.StopPattern) {{
        $matched = $true
        break
      }}
      Start-Sleep -Milliseconds 100
    }}
    $chunk = $sp.ReadExisting()
    if ($chunk.Length -gt 0) {{
      $response += $chunk
    }}
    $data_sent = $false
    $data_length = 0
    if ($null -ne $entry.Data -and $entry.Data.Length -gt 0) {{
      $data_length = $entry.Data.Length
      if ($response -match "DOWNLOAD") {{
        $sp.Write($entry.Data)
        $data_sent = $true
        $dataDeadline = [DateTime]::UtcNow.AddMilliseconds($entry.ReadWindowMs)
        while ([DateTime]::UtcNow -lt $dataDeadline) {{
          $chunk = $sp.ReadExisting()
          if ($chunk.Length -gt 0) {{
            $response += $chunk
          }}
          if ($response -match "OK|ERROR") {{
            break
          }}
          Start-Sleep -Milliseconds 100
        }}
        $chunk = $sp.ReadExisting()
        if ($chunk.Length -gt 0) {{
          $response += $chunk
        }}
      }}
    }}
    if ($response.Length -gt 5000) {{
      $response = $response.Substring(0, 5000) + "...[truncated]"
    }}
    $response = $response -replace '(Authorization:\\s*Bearer\\s+)[^"`r`n]+', '$1[REDACTED_SECRET]'
    $response = $response -replace '(Bearer\\s+)[A-Za-z0-9._~+/=-]+', '$1[REDACTED_SECRET]'
    $result.responses += [ordered]@{{
      command = $logCommand
      label = $entry.Label
      response = $response
      matched = $matched
      optional = $entry.Optional
      data_sent = $data_sent
      data_length = $data_length
    }}
  }}
  $result.ok = $true
}} catch {{
  $result.error = $_.Exception.Message
}} finally {{
  if ($sp -and $sp.IsOpen) {{ $sp.Close() }}
}}
$result | ConvertTo-Json -Depth 8
"""
    extra_env = {"EGOLINK_AT_AUTH_HEADER": auth_header} if auth_header else None
    raw = run_powershell(script, timeout_seconds=timeout_seconds, extra_env=extra_env)
    return redact_payload(json.loads(raw))


def ps_step_row(step: AtStep) -> str:
    return (
        "[pscustomobject]@{"
        f"Command = {ps_quote(step.command)}; "
        f"Label = {ps_quote(step.label)}; "
        f"WaitMs = {step.wait_ms}; "
        f"ReadWindowMs = {step.read_window_ms}; "
        f"StopPattern = {ps_quote(step.stop_pattern)}; "
        f"Optional = {ps_bool(step.optional)}; "
        f"Data = {ps_null_or_quote(step.data)}; "
        f"LogCommand = {ps_null_or_quote(step.log_command)}"
        "}"
    )


def ps_bool(value: bool) -> str:
    return "$true" if value else "$false"


def ps_null_or_quote(value: str | None) -> str:
    return "$null" if value is None else ps_quote(value)


def parse_status_probe(probe: dict[str, Any]) -> dict[str, Any]:
    combined = combined_response_text(probe)
    model = match_text(r"Model:\s*([^\r\n]+)", combined)
    revision = match_text(r"Revision:\s*([^\r\n]+)", combined)
    cpin = match_text(r"\+CPIN:\s*([^\r\n]+)", combined)
    csq = match_text(r"\+CSQ:\s*([0-9]+),([0-9]+)", combined)
    assigned_ip = match_text(r"\+CGPADDR:\s*\d+,([^,\r\n]+)", combined)
    cpsi = match_text(r"(\+CPSI:[^\r\n]+)", combined)
    registered = bool(re.search(r"\+CEREG:\s*\d,([15])\b", combined))
    attached = bool(re.search(r"\+CGATT:\s*1\b", combined))
    pdp_active = bool(re.search(r"\+CGACT:\s*\d+,1\b", combined))
    sim_ready = bool(cpin and cpin.upper().startswith("READY"))
    return {
        "port": probe.get("port"),
        "ok": bool(probe.get("ok")),
        "error": probe.get("error"),
        "at_ok": response_ok(response_by_label(probe, "AT")) or "SIMCOM" in combined.upper(),
        "model": model,
        "revision": revision,
        "is_sim7670g": bool(model and "SIM7670G" in model.upper()),
        "sim_ready": sim_ready,
        "registered": registered,
        "attached": attached,
        "pdp_active": pdp_active,
        "assigned_ip": assigned_ip,
        "csq": csq,
        "cpsi": cpsi,
        "lte_ready": sim_ready and registered and attached and pdp_active and bool(assigned_ip),
    }


def parse_http_probe(probe: dict[str, Any] | None, *, mode: str = "health-get") -> dict[str, Any]:
    if probe is None:
        return {}
    responses = response_map(probe)
    action_label = "HTTPACTION_POST" if mode in {"telemetry-post-unauth", "telemetry-post-auth"} else "HTTPACTION_GET"
    action_response = responses.get(action_label, "")
    status = parse_httpaction(action_response)
    read_response = responses.get("HTTPREAD", "")
    health_ok = bool(re.search(r'"ok"\s*:\s*true', read_response, re.I))
    parsed = {
        "port": probe.get("port"),
        "ok": bool(probe.get("ok")),
        "error": probe.get("error"),
        "at_ok": response_ok(responses.get("AT", "")),
        "http_init_ok": response_ok(responses.get("HTTPINIT", "")),
        "http_cid_ok": response_ok(responses.get("HTTPPARA_CID", "")) if "HTTPPARA_CID" in responses else None,
        "http_url_ok": response_ok(responses.get("HTTPPARA_URL", "")),
        "http_content_ok": response_ok(responses.get("HTTPPARA_CONTENT", "")) if "HTTPPARA_CONTENT" in responses else None,
        "http_userdata_ok": response_ok(responses.get("HTTPPARA_USERDATA", "")) if "HTTPPARA_USERDATA" in responses else None,
        "http_data_ok": response_ok(responses.get("HTTPDATA", "")) if "HTTPDATA" in responses else None,
        "http_action_seen": status is not None,
        "http_read_ok": response_ok(read_response),
        "health_ok": health_ok,
        "http_action": status,
        "status_code": status["status_code"] if status else None,
        "data_len": status["data_len"] if status else None,
        "mode": mode,
        "reason_code": "unknown",
    }
    parsed["reason_code"] = classify_http_reason(parsed)
    return parsed


def parse_httpaction(text: str) -> dict[str, int] | None:
    match = re.search(r"\+HTTPACTION:\s*(\d+),\s*(-?\d+),\s*(-?\d+)", text)
    if not match:
        return None
    return {
        "method": int(match.group(1)),
        "status_code": int(match.group(2)),
        "data_len": int(match.group(3)),
    }


def classify_http_reason(parsed: dict[str, Any]) -> str:
    if not parsed.get("ok"):
        return "LTE_HTTP_SERIAL_FAILED"
    if not parsed.get("at_ok"):
        return "LTE_HTTP_AT_UNREACHABLE"
    if not parsed.get("http_init_ok"):
        return "LTE_HTTP_INIT_FAILED"
    if parsed.get("http_cid_ok") is False:
        return "LTE_HTTP_CID_FAILED"
    if not parsed.get("http_url_ok"):
        return "LTE_HTTP_URL_FAILED"
    if parsed.get("http_content_ok") is False:
        return "LTE_HTTP_CONTENT_FAILED"
    if parsed.get("http_userdata_ok") is False:
        return "LTE_HTTP_HEADER_FAILED"
    if parsed.get("http_data_ok") is False:
        return "LTE_HTTP_DATA_FAILED"
    if not parsed.get("http_action_seen"):
        return "LTE_HTTP_ACTION_FAILED"
    status_code = parsed.get("status_code")
    if parsed.get("mode") == "telemetry-post-unauth" and status_code in {401, 403}:
        return "LTE_HTTP_AUTH_GATE_REACHED"
    if isinstance(status_code, int) and 200 <= status_code < 300:
        return "LTE_HTTP_OK"
    if isinstance(status_code, int) and 400 <= status_code < 500:
        return "LTE_HTTP_CLIENT_ERROR"
    if isinstance(status_code, int) and 500 <= status_code < 600:
        return "LTE_HTTP_SERVER_ERROR"
    return "LTE_HTTP_STATUS_ERROR"


def select_http_port(port_preflights: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in port_preflights:
        parsed = item["parsed"]
        if parsed.get("is_sim7670g") and parsed.get("at_ok"):
            return item
    for item in port_preflights:
        if item["parsed"].get("at_ok"):
            return item
    return port_preflights[0] if port_preflights else None


def summarize_run(
    *,
    candidates: list[SerialPortInfo],
    port_preflights: list[dict[str, Any]],
    selected: dict[str, Any] | None,
    parsed_http: dict[str, Any],
    url: str,
    mode: str,
    include_cid: bool,
) -> dict[str, Any]:
    selected_status = selected["parsed"] if selected else {}
    http_ok = parsed_http.get("reason_code") in {"LTE_HTTP_OK", "LTE_HTTP_AUTH_GATE_REACHED"}
    return {
        "result": "PASS" if http_ok else "FAIL",
        "reason_code": parsed_http.get("reason_code") or "LTE_HTTP_NO_AT_PORT",
        "url": url,
        "mode": mode,
        "include_cid": include_cid,
        "candidate_ports": [item.port for item in candidates],
        "identity_ports": [item["parsed"]["port"] for item in port_preflights if item["parsed"].get("is_sim7670g")],
        "selected_port": selected_status.get("port"),
        "at_ok": bool(selected_status.get("at_ok")),
        "lte_ready": bool(selected_status.get("lte_ready")),
        "sim_ready": bool(selected_status.get("sim_ready")),
        "registered": bool(selected_status.get("registered")),
        "attached": bool(selected_status.get("attached")),
        "pdp_active": bool(selected_status.get("pdp_active")),
        "assigned_ip": selected_status.get("assigned_ip"),
        "http_status": parsed_http.get("status_code"),
        "http_data_len": parsed_http.get("data_len"),
        "health_ok": bool(parsed_http.get("health_ok")),
    }


def response_map(probe: dict[str, Any]) -> dict[str, str]:
    mapped: dict[str, str] = {}
    for item in ensure_response_list(probe):
        label = str(item.get("label") or item.get("command") or "")
        mapped[label] = str(item.get("response") or "")
    return mapped


def response_by_label(probe: dict[str, Any], label: str) -> str:
    return response_map(probe).get(label, "")


def combined_response_text(probe: dict[str, Any]) -> str:
    return "\n".join(str(item.get("response") or "") for item in ensure_response_list(probe))


def ensure_response_list(probe: dict[str, Any]) -> list[dict[str, Any]]:
    responses = probe.get("responses")
    if responses is None:
        return []
    if isinstance(responses, list):
        return responses
    return [responses]


def response_ok(text: str) -> bool:
    return bool(re.search(r"\bOK\b", text)) and not bool(re.search(r"\bERROR\b", text))


def match_text(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text)
    if not match:
        return None
    if len(match.groups()) == 1:
        return match.group(1).strip()
    return ",".join(group.strip() for group in match.groups())


def render_markdown_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# LTE-002 SIM7670G HTTP AT Diagnostic",
        "",
        f"- Generated: `{report['started_at']}`",
        f"- Result: `{summary['result']}`",
        f"- Reason: `{summary['reason_code']}`",
        f"- Mode: `{report['mode']}`",
        f"- URL: `{report['url']}`",
        f"- Token source: `{report.get('token_source') or 'none'}`",
        f"- Auth header length: `{report.get('auth_header_length') or 'none'}`",
        f"- Include CID: `{report['include_cid']}`",
        f"- Payload padding bytes: `{report.get('payload_padding_bytes', 0)}`",
        f"- Candidate ports: `{', '.join(summary['candidate_ports']) or 'none'}`",
        f"- Identity ports: `{', '.join(summary['identity_ports']) or 'none'}`",
        f"- Selected port: `{summary['selected_port']}`",
        f"- LTE ready: `{summary['lte_ready']}`",
        f"- SIM/registration/attach/PDP: `{summary['sim_ready']}` / `{summary['registered']}` / `{summary['attached']}` / `{summary['pdp_active']}`",
        f"- Assigned IP: `{summary['assigned_ip']}`",
        f"- HTTP status: `{summary['http_status']}`",
        f"- HTTP data length: `{summary['http_data_len']}`",
        f"- Health body ok: `{summary['health_ok']}`",
        "",
        "## Port Preflight",
        "",
        "| Port | Model | AT | LTE Ready | SIM | Reg | Attach | PDP | IP | CSQ |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for item in report["port_preflights"]:
        parsed = item["parsed"]
        lines.append(
            f"| `{parsed.get('port')}` | `{parsed.get('model')}` | {parsed.get('at_ok')} | "
            f"{parsed.get('lte_ready')} | {parsed.get('sim_ready')} | {parsed.get('registered')} | "
            f"{parsed.get('attached')} | {parsed.get('pdp_active')} | `{parsed.get('assigned_ip')}` | "
            f"`{parsed.get('csq')}` |"
        )
    lines.extend(["", "## HTTP AT Steps", ""])
    http_probe = report.get("http_probe") or {}
    if not http_probe:
        lines.append("- No HTTP probe was run because no AT candidate port was available.")
    else:
        lines.extend(["| Label | Matched | Optional | Response excerpt |", "|---|---:|---:|---|"])
        for item in ensure_response_list(http_probe):
            label = str(item.get("label") or item.get("command") or "")
            response = redact_sensitive(str(item.get("response") or ""))
            lines.append(
                f"| `{label}` | {item.get('matched')} | {item.get('optional')} | "
                f"`{escape_table(truncate_text(response, 180))}` |"
            )
    lines.extend(["", "## Boundary", ""])
    lines.append("- This is PC-side USB AT evidence, not USB-Free product runtime evidence.")
    if report["mode"] == "telemetry-post-auth":
        lines.append("- A bearer token is used only to set the SIM7670G HTTP USERDATA header; the token value is redacted from reports.")
        lines.append("- Passing this diagnostic proves the SIM7670G module can POST to the Message Hub over its AT HTTP stack.")
    else:
        lines.append("- Passing this diagnostic only proves the SIM7670G module can reach the public Message Hub health URL through its AT HTTP stack.")
        lines.append("- No bearer token is used or recorded by this diagnostic.")
    lines.append("")
    return "\n".join(lines)


def redact_sensitive(text: str) -> str:
    text = re.sub(r"(Authorization:\s*Bearer\s+)[^\r\n\"]+", r"\1[REDACTED_SECRET]", text, flags=re.I)
    text = re.sub(r"(Bearer\s+\[REDACTED_SECRET\])[^\r\n\"]*", r"\1", text, flags=re.I)
    return re.sub(r"(Bearer\s+)[A-Za-z0-9._~+/=-]+", r"\1[REDACTED_SECRET]", text, flags=re.I)


def redact_payload(value: Any) -> Any:
    if isinstance(value, str):
        return redact_sensitive(value)
    if isinstance(value, list):
        return [redact_payload(item) for item in value]
    if isinstance(value, dict):
        return {key: redact_payload(item) for key, item in value.items()}
    return value


def escape_table(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def load_bearer_token(token_env: str, token_file: Path) -> tuple[str, str]:
    token = (os.environ.get(token_env) or "").strip()
    if token:
        return token, f"env:{token_env}"
    if token_file.exists():
        token = token_file.read_text(encoding="utf-8").strip()
        if token:
            return token, "file"
    raise SystemExit(
        "telemetry-post-auth requires a bearer token; set "
        f"{token_env} or provide {token_file}"
    )


def run_powershell(script: str, timeout_seconds: int, extra_env: dict[str, str] | None = None) -> str:
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
        env=env,
    )
    return completed.stdout.strip()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())

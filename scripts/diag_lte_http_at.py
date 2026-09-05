"""Diagnose bounded SIM7670G LTE HTTPS behavior through the USB AT port.

This script is for LTE-002 failure triage after USB-Free validation reports no
fresh LTE HTTP telemetry. It opens bounded SIM7670G USB AT sessions only. It
does not flash firmware, erase flash, enqueue Message Hub commands, or place
calls. The default is the public HTTPS `/health` endpoint. A plaintext health
probe is available only as an explicit, expiring, credential-free engineering
fallback; it cannot POST or satisfy production TLS acceptance.

The ``tls-capability`` mode is a separate zero-traffic, read-only capability
probe. It sends only a fixed allowlist of identity, SSL command-discovery,
certificate-list, and clock queries. It never starts HTTP, changes SSL state,
uploads a certificate, reads a token, or sends a payload.
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
from urllib.parse import urlsplit

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


DEFAULT_HUB_BASE_URL = "https://ego.example.invalid"
DEFAULT_URL = f"{DEFAULT_HUB_BASE_URL}/health"
DEFAULT_EXPECTED_HOST = "ego.example.invalid"
DEFAULT_DEVICE_ID = "ego-link-r1-connectivity-001"
DEFAULT_OUTPUT_DIR = Path("reports") / "field_validation" / "lte002-atdiag-http"
MAX_BEARER_TOKEN_BYTES = 160
MAX_PLAINTEXT_FALLBACK_SECONDS = 3600
BEARER_TOKEN_RE = re.compile(r"[A-Za-z0-9._~+/=-]+")
TLS_CAPABILITY_COMMANDS = (
    "ATI",
    "AT+CGMR",
    "AT+CSSLCFG=?",
    "AT+CSSLCFG?",
    "AT+CCERTDOWN=?",
    "AT+CCERTLIST",
    "AT+CCLK?",
)
TLS_CAPABILITY_COMMAND_ALLOWLIST = frozenset(TLS_CAPABILITY_COMMANDS)
TLS_REQUIRED_CSSLCFG_OPTIONS = (
    "authmode",
    "cacert",
    "enablesni",
    "ignorecertcn",
    "ignorelocaltime",
)
SIMCOM_SIM76XX_SSL_MANUAL_URL = (
    "https://en.simcom.com/Uploads/file/20260622/20260622103004_43058.pdf"
)
SIMCOM_SIM76XX_SSL_APPLICATION_NOTE_URL = (
    "https://en.simcom.com/Uploads/file/20240611/20240611143858_59317.pdf"
)


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
    if args.mode == "tls-capability":
        report = run_tls_capability_diagnostic(
            sim_ports=args.sim_ports,
            probe_all_sim_ports=args.probe_all_sim_ports,
            output_dir=args.output_dir,
        )
        print(report["markdown_path"])
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["summary"]["capability"] == "present" else 2

    url = resolve_url(args.mode, args.url, args.device_id)
    try:
        transport = validate_ingress_url(
            url,
            mode=args.mode,
            expected_host=args.expected_host,
            allow_plaintext_engineering=args.allow_plaintext_engineering,
            plaintext_expires_at_utc=args.plaintext_expires_at_utc,
        )
    except ValueError as error:
        print(json.dumps({"ok": False, "error": str(error)}), file=sys.stderr)
        return 2
    bearer_token, token_source = (
        load_bearer_token(args.token_env, args.token_file)
        if args.mode == "telemetry-post-auth"
        else (None, None)
    )
    report = run_diagnostic(
        sim_ports=args.sim_ports,
        probe_all_sim_ports=args.probe_all_sim_ports,
        url=url,
        mode=args.mode,
        transport=transport,
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
    return 0 if str(report["summary"]["result"]).startswith("PASS") else 2


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
        help="HTTPS URL for the SIM7670G AT check. Defaults depend on --mode.",
    )
    parser.add_argument(
        "--mode",
        choices=("tls-capability", "health-get", "telemetry-post-unauth", "telemetry-post-auth"),
        default="health-get",
        help=(
            "Run the fixed read-only TLS capability query set, a public /health GET, "
            "an unauthenticated telemetry POST, or a bearer-auth telemetry POST smoke."
        ),
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
    parser.add_argument(
        "--expected-host",
        default=DEFAULT_EXPECTED_HOST,
        help="Exact TLS host expected in --url; defaults to the production Message Hub host.",
    )
    parser.add_argument(
        "--allow-plaintext-engineering",
        action="store_true",
        help="Allow only an unauthenticated /health HTTP probe within a bounded expiry window.",
    )
    parser.add_argument(
        "--plaintext-expires-at-utc",
        help="Required ISO-8601 UTC expiry for plaintext engineering health probes (maximum one hour).",
    )
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def run_diagnostic(
    *,
    sim_ports: list[str],
    probe_all_sim_ports: bool,
    url: str,
    mode: str,
    transport: dict[str, Any],
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
        transport=transport,
    )
    payload: dict[str, Any] = {
        "project": "Ego Link P0",
        "task_id": "LTE-002",
        "diagnostic": "sim7670g_lte_http_at",
        "started_at": started_at,
        "host": {"platform": platform.platform(), "python": sys.version.split()[0]},
        "url": url,
        "mode": mode,
        "transport": transport,
        "device_id": device_id,
        "token_source": token_source,
        "auth_configured": bearer_token is not None,
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


def run_tls_capability_diagnostic(
    *,
    sim_ports: list[str],
    probe_all_sim_ports: bool,
    output_dir: Path,
) -> dict[str, Any]:
    """Run only the fixed, read-only modem TLS capability query set."""

    started_at = utc_now()
    serial_ports = discover_serial_ports()
    candidates = choose_sim_ports(serial_ports, sim_ports, probe_all_sim_ports)
    steps = build_tls_capability_steps()
    probes: list[dict[str, Any]] = []
    for port_info in candidates:
        raw_probe = run_at_sequence(
            port_info.port,
            steps,
            timeout_seconds=sequence_timeout_seconds(steps, floor=20),
            command_allowlist=TLS_CAPABILITY_COMMAND_ALLOWLIST,
        )
        # Raw modem responses can contain local certificate filenames. Persist
        # only the bounded parser output, never the raw response text.
        probes.append(parse_tls_capability_probe(raw_probe))

    selected = select_tls_capability_probe(probes)
    capability = selected.get("capability") if selected else "unverified"
    summary = {
        "result": "INCOMPLETE" if capability == "present" else "FAIL",
        "reason_code": (
            "MODEM_TLS_CAPABILITY_PRESENT_EXACT_FIRMWARE_UNVERIFIED"
            if capability == "present"
            else "MODEM_TLS_CAPABILITY_MISSING"
            if capability == "missing"
            else "MODEM_TLS_CAPABILITY_NOT_PROBED"
        ),
        "capability": capability,
        "classification": f"capability-{capability}",
        "selected_port": selected.get("port") if selected else None,
        "candidate_ports": [item.port for item in candidates],
    }
    payload: dict[str, Any] = {
        "project": "Ego Link P0",
        "task_id": "OPS-004B",
        "diagnostic": "sim7670g_tls_capability_at",
        "mode": "tls-capability",
        "started_at": started_at,
        "host": {"platform": platform.platform(), "python": sys.version.split()[0]},
        "evidence_statement": (
            "documented capability / exact firmware + negative behavior unverified"
        ),
        "documented_capability": {
            "status": "documented",
            "scope": "SIMCom SIM76XX SSL AT command manual, software 2388_SIM76XX and later",
            "capabilities": [
                "CA certificate storage and SSL-context binding",
                "server authentication mode",
                "SNI enablement",
                "certificate common-name checking",
                "local-time certificate validation control",
            ],
            "official_sources": [
                SIMCOM_SIM76XX_SSL_MANUAL_URL,
                SIMCOM_SIM76XX_SSL_APPLICATION_NOTE_URL,
            ],
        },
        "exact_firmware": {
            "status": "unverified",
            "reason": "reported revision-to-2388_SIM76XX branch mapping is not established by this query-only probe",
            "model": selected.get("model") if selected else None,
            "revision": selected.get("revision") if selected else None,
        },
        "negative_behavior": {
            "status": "unverified",
            "reason": "zero-traffic probe does not attempt invalid CA, hostname, time, or SNI connections",
        },
        "probe_contract": {
            "read_only": True,
            "network_traffic": False,
            "state_writes": False,
            "certificate_upload": False,
            "token_or_payload_access": False,
            "allowed_commands": list(TLS_CAPABILITY_COMMANDS),
        },
        "candidate_ports": [item.port for item in candidates],
        "probes": probes,
        "summary": summary,
    }
    stamp = timestamp_for_path()
    run_dir = output_dir / stamp
    run_dir.mkdir(parents=True, exist_ok=True)
    json_path = run_dir / "tls_capability_at_diag.json"
    markdown_path = run_dir / "tls_capability_at_diag.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    markdown_path.write_text(render_tls_capability_markdown(payload), encoding="utf-8")
    payload["json_path"] = str(json_path)
    payload["markdown_path"] = str(markdown_path)
    return payload


def build_tls_capability_steps() -> list[AtStep]:
    steps = [
        AtStep("ATI", "ATI", read_window_ms=1400),
        AtStep("AT+CGMR", "CGMR", read_window_ms=1400),
        AtStep("AT+CSSLCFG=?", "CSSLCFG_TEST", read_window_ms=2400),
        AtStep("AT+CSSLCFG?", "CSSLCFG_READ", read_window_ms=2400),
        AtStep("AT+CCERTDOWN=?", "CCERTDOWN_TEST", read_window_ms=1800),
        AtStep("AT+CCERTLIST", "CCERTLIST", read_window_ms=2400),
        AtStep("AT+CCLK?", "CCLK_READ", read_window_ms=1400),
    ]
    return validate_tls_capability_steps(steps)


def validate_tls_capability_steps(steps: Iterable[AtStep]) -> list[AtStep]:
    """Fail closed if a TLS capability sequence departs from its exact contract."""

    checked = list(steps)
    commands = tuple(step.command for step in checked)
    if commands != TLS_CAPABILITY_COMMANDS:
        raise ValueError("tls-capability command sequence must match the fixed read-only allowlist")
    for step in checked:
        if step.command not in TLS_CAPABILITY_COMMAND_ALLOWLIST:
            raise ValueError(f"tls-capability command is not allowed: {step.command}")
        if step.data is not None or step.log_command not in (None, step.command):
            raise ValueError("tls-capability steps cannot send data or substitute commands")
    return checked


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


def validate_ingress_url(
    url: str,
    *,
    mode: str,
    expected_host: str = DEFAULT_EXPECTED_HOST,
    allow_plaintext_engineering: bool = False,
    plaintext_expires_at_utc: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Validate the non-secret transport target before opening a serial port."""

    parsed = urlsplit(url)
    if not expected_host or expected_host != expected_host.lower() or not re.fullmatch(r"[a-z0-9.-]+", expected_host):
        raise ValueError("expected-host must be a lowercase DNS name")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("ingress URL must not contain credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("ingress URL must not contain a query or fragment")
    if parsed.hostname != expected_host:
        raise ValueError("ingress URL host does not match expected-host")
    if parsed.scheme == "https":
        if parsed.port not in (None, 443):
            raise ValueError("production HTTPS ingress must use port 443")
        if mode == "telemetry-post-auth":
            raise ValueError(
                "authenticated modem POST is disabled until SIM7670 certificate-chain and hostname verification are implemented"
            )
        return {
            "scheme": "https",
            "expected_host": expected_host,
            "peer_verification": "modem_hardware_unverified",
            "production_acceptable": False,
            "plaintext_fallback": False,
            "plaintext_expires_at_utc": None,
        }
    if parsed.scheme != "http":
        raise ValueError("ingress URL scheme must be https")
    if not allow_plaintext_engineering:
        raise ValueError("plaintext ingress is disabled; use the HTTPS endpoint")
    if mode != "health-get" or parsed.path != "/health":
        raise ValueError("plaintext fallback is limited to credential-free GET /health")
    if not plaintext_expires_at_utc:
        raise ValueError("plaintext engineering fallback requires an explicit UTC expiry")
    try:
        expires = datetime.fromisoformat(plaintext_expires_at_utc.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("plaintext fallback expiry must be ISO-8601 UTC") from error
    if expires.tzinfo is None or expires.utcoffset() != timezone.utc.utcoffset(expires):
        raise ValueError("plaintext fallback expiry must include UTC timezone")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    remaining = (expires - current.astimezone(timezone.utc)).total_seconds()
    if remaining <= 0 or remaining > MAX_PLAINTEXT_FALLBACK_SECONDS:
        raise ValueError("plaintext fallback expiry must be within the next 3600 seconds")
    return {
        "scheme": "http",
        "expected_host": expected_host,
        "peer_verification": "not_applicable_plaintext_engineering_only",
        "production_acceptable": False,
        "plaintext_fallback": True,
        "plaintext_expires_at_utc": expires.astimezone(timezone.utc).isoformat(),
    }


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
    command_allowlist: frozenset[str] | None = None,
) -> dict[str, Any]:
    checked_steps = list(steps)
    if command_allowlist is not None:
        if auth_header is not None:
            raise ValueError("allowlisted AT query sequences cannot receive an auth header")
        for step in checked_steps:
            if step.command not in command_allowlist:
                raise ValueError(f"AT command is outside the supplied allowlist: {step.command}")
            if step.data is not None or step.log_command not in (None, step.command):
                raise ValueError("allowlisted AT query sequences cannot send data or substitute commands")
    step_rows = "@(" + ",".join(ps_step_row(item) for item in checked_steps) + ")"
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


def parse_tls_capability_probe(probe: dict[str, Any]) -> dict[str, Any]:
    """Reduce modem responses to non-secret capability facts."""

    responses = response_map(probe)
    csslcfg_test = responses.get("CSSLCFG_TEST", "")
    csslcfg_normalized = csslcfg_test.lower()
    options = {
        option: option in csslcfg_normalized
        for option in TLS_REQUIRED_CSSLCFG_OPTIONS
    }
    command_results = []
    labels = [
        ("ATI", "ATI"),
        ("AT+CGMR", "CGMR"),
        ("AT+CSSLCFG=?", "CSSLCFG_TEST"),
        ("AT+CSSLCFG?", "CSSLCFG_READ"),
        ("AT+CCERTDOWN=?", "CCERTDOWN_TEST"),
        ("AT+CCERTLIST", "CCERTLIST"),
        ("AT+CCLK?", "CCLK_READ"),
    ]
    for command, label in labels:
        response = responses.get(label, "")
        command_results.append(
            {
                "command": command,
                "supported": response_ok(response),
                "error_observed": bool(re.search(r"(?:\+CME\s+ERROR|\bERROR\b)", response, re.I)),
            }
        )

    required_api_labels = (
        "CSSLCFG_TEST",
        "CSSLCFG_READ",
        "CCERTDOWN_TEST",
        "CCERTLIST",
        "CCLK_READ",
    )
    missing = [label for label in required_api_labels if not response_ok(responses.get(label, ""))]
    missing.extend(option for option, present in options.items() if not present)
    capability = "present" if probe.get("ok") and not missing else "missing"
    ati = responses.get("ATI", "")
    model = match_text(r"Model:\s*([^\r\n]+)", ati)
    if model is None:
        model = match_text(r"\b(SIM7670[^\r\n]*)", ati)
    revision = match_text(r"Revision:\s*([^\r\n]+)", ati)
    if revision is None:
        revision = extract_cgmr_revision(responses.get("CGMR", ""))
    cert_list_response = responses.get("CCERTLIST", "")
    return {
        "port": safe_identity_field(str(probe.get("port") or "")),
        "probe_completed": bool(probe.get("ok")),
        "probe_error": safe_identity_field(str(probe.get("error") or "")) or None,
        "model": safe_identity_field(model),
        "revision": safe_identity_field(revision),
        "is_sim7670_family": bool(model and "SIM7670" in model.upper()),
        "capability": capability,
        "missing_or_unadvertised": sorted(set(missing)),
        "csslcfg_options": options,
        "certificate_list_response_present": "+CCERTLIST:" in cert_list_response.upper(),
        "clock_query_supported": response_ok(responses.get("CCLK_READ", "")),
        "clock_shape_recognized": bool(
            re.search(r'\+CCLK:\s*"\d{2}/\d{2}/\d{2},\d{2}:\d{2}:\d{2}[+-]\d{2}"', responses.get("CCLK_READ", ""))
        ),
        "command_results": command_results,
        "raw_responses_persisted": False,
    }


def extract_cgmr_revision(text: str) -> str | None:
    for line in text.splitlines():
        candidate = line.strip()
        if not candidate or candidate.upper() in {"AT+CGMR", "OK", "ERROR"}:
            continue
        if candidate.upper().startswith("+CME ERROR"):
            continue
        return re.sub(r"^\+CGMR:\s*", "", candidate, flags=re.I)
    return None


def safe_identity_field(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(redact_sensitive(value).split())
    cleaned = re.sub(r"\b\d{12,20}\b", "[REDACTED_IDENTIFIER]", cleaned)
    return truncate_text(cleaned, 120) if cleaned else None


def select_tls_capability_probe(probes: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in probes:
        if item.get("is_sim7670_family") and item.get("capability") == "present":
            return item
    for item in probes:
        if item.get("is_sim7670_family"):
            return item
    for item in probes:
        if item.get("capability") == "present":
            return item
    return probes[0] if probes else None


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
    transport: dict[str, Any],
) -> dict[str, Any]:
    selected_status = selected["parsed"] if selected else {}
    http_ok = parsed_http.get("reason_code") in {"LTE_HTTP_OK", "LTE_HTTP_AUTH_GATE_REACHED"}
    result = "FAIL"
    reason_code = parsed_http.get("reason_code") or "LTE_HTTP_NO_AT_PORT"
    if http_ok and transport.get("plaintext_fallback"):
        result = "PASS_ENGINEERING_FALLBACK"
        reason_code = "LTE_HTTP_ENGINEERING_HEALTH_OK"
    elif http_ok and transport.get("scheme") == "https":
        result = "INCOMPLETE"
        reason_code = "LTE_HTTPS_PEER_VERIFICATION_UNVERIFIED"
    return {
        "result": result,
        "reason_code": reason_code,
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


def render_tls_capability_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    exact_firmware = report["exact_firmware"]
    lines = [
        "# OPS-004B SIM7670G TLS Capability AT Probe",
        "",
        f"- Generated: `{report['started_at']}`",
        f"- Classification: `{summary['classification']}`",
        f"- Reason: `{summary['reason_code']}`",
        f"- Evidence statement: **{report['evidence_statement']}**",
        f"- Selected port: `{summary['selected_port']}`",
        f"- Model: `{exact_firmware.get('model')}`",
        f"- Firmware revision: `{exact_firmware.get('revision')}`",
        "",
        "## Safety Contract",
        "",
        "- The probe is query-only: no HTTP action, PDP/network activation, TLS setting write, certificate upload, token access, or payload body.",
        f"- Fixed AT allowlist: `{', '.join(report['probe_contract']['allowed_commands'])}`",
        "- Raw AT responses and certificate filenames are not persisted in this report.",
        "",
        "## Observations",
        "",
        "| Port | Model | Revision | Capability | Missing/unadvertised | Clock shape |",
        "|---|---|---|---|---|---:|",
    ]
    for item in report["probes"]:
        lines.append(
            f"| `{escape_table(item.get('port'))}` | `{escape_table(item.get('model'))}` | "
            f"`{escape_table(item.get('revision'))}` | `{item.get('capability')}` | "
            f"`{escape_table(', '.join(item.get('missing_or_unadvertised', [])) or 'none')}` | "
            f"{item.get('clock_shape_recognized')} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation Boundary",
            "",
            "- SIMCom's SIM76XX SSL AT command manual documents CA binding, server authentication, SNI, common-name checking, and local-time validation controls for software `2388_SIM76XX` and later.",
            "- An observed command surface is capability evidence only. It does not prove this exact firmware maps to that documented branch or correctly rejects an invalid CA, hostname, clock, or SNI case.",
            "- Any live probe requires new explicit operator authorization. Negative-path TLS testing is a separate, traffic-generating task.",
            "",
            "## Official Sources",
            "",
            f"- [SIMCom SIM76XX SSL AT Command Manual]({SIMCOM_SIM76XX_SSL_MANUAL_URL})",
            f"- [SIMCom SIM7600 Series SSL Application Note]({SIMCOM_SIM76XX_SSL_APPLICATION_NOTE_URL})",
            "",
        ]
    )
    return "\n".join(lines)


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
        f"- Auth configured: `{report.get('auth_configured', False)}`",
        f"- TLS peer verification: `{report.get('transport', {}).get('peer_verification', 'unavailable')}`",
        f"- Production acceptable: `{report.get('transport', {}).get('production_acceptable', False)}`",
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
        lines.append("- A response proves only AT-stack transport. This tool cannot prove SIM7670 certificate-chain or hostname verification.")
    elif report.get("transport", {}).get("plaintext_fallback"):
        lines.append("- This expiring fallback sends only GET /health, with no bearer token or location payload.")
        lines.append("- It is engineering reachability evidence and is rejected by production-style acceptance.")
    else:
        lines.append("- A response proves only that the SIM7670G AT stack reached the HTTPS URL; peer verification remains unverified.")
        lines.append("- No bearer token is used or recorded by this diagnostic.")
    lines.append("")
    return "\n".join(lines)


def redact_sensitive(text: str) -> str:
    text = re.sub(r"(Authorization:\s*Bearer\s+)[^\r\n\"]+", r"\1[REDACTED_SECRET]", text, flags=re.I)
    text = re.sub(r"(Bearer\s+\[REDACTED_SECRET\])[^\r\n\"]*", r"\1", text, flags=re.I)
    text = re.sub(r"(Bearer\s+)[A-Za-z0-9._~+/=-]+", r"\1[REDACTED_SECRET]", text, flags=re.I)
    text = re.sub(r"(https?://)[^/@\s\"']+@", r"\1[REDACTED_SECRET]@", text, flags=re.I)
    return re.sub(
        r"((?:access[_-]?token|token|api[_-]?key|password|secret)=)[^&\s\"']+",
        r"\1[REDACTED_SECRET]",
        text,
        flags=re.I,
    )


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
        return validate_bearer_token(token), f"env:{token_env}"
    if token_file.exists():
        with token_file.open("rb") as handle:
            raw = handle.read(MAX_BEARER_TOKEN_BYTES + 2)
        if len(raw) > MAX_BEARER_TOKEN_BYTES + 1:
            raise SystemExit("telemetry-post-auth token file exceeds the bounded token size")
        try:
            token = raw.decode("utf-8").strip()
        except UnicodeDecodeError as error:
            raise SystemExit("telemetry-post-auth token file must be UTF-8") from error
        if token:
            return validate_bearer_token(token), "file"
    raise SystemExit(
        "telemetry-post-auth requires a bearer token; set "
        f"{token_env} or provide {token_file}"
    )


def validate_bearer_token(token: str) -> str:
    if len(token.encode("utf-8")) > MAX_BEARER_TOKEN_BYTES or BEARER_TOKEN_RE.fullmatch(token) is None:
        raise SystemExit("telemetry-post-auth token has an invalid format or length")
    return token


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

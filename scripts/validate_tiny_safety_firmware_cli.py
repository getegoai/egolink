"""Validate Tiny Safety firmware CLI output.

Default mode is a no-hardware dry-run that writes the planned command evidence
shape. Fixture mode parses a saved log. Serial mode is bounded and requires an
explicit operator guard before opening a port.
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
from typing import Any


SCHEMA = "egolink.tiny_safety_firmware_cli_report.v0.1"
DEFAULT_OUTPUT_DIR = Path("reports") / "tiny_safety_firmware_cli"
EXPECTED_MODEL_ID = "MODEL-DEVICE-001-tiny-safety-v0-20260707"
EXPECTED_MODEL_VERSION = "0.1.0-synthetic-dry-run"
EXPECTED_HARNESS_VERSION = "tiny-safety-fw-harness-0.1.0"
EXPECTED_FEATURE_COUNT = "14"
EXPECTED_CLASS_COUNT = "4"
EXPECTED_SELFTEST_VECTORS = "4"
MARKER_RE = re.compile(
    r"\b(?P<marker>TINY_SAFETY_STATUS|TINY_SAFETY_SELFTEST|TINY_SAFETY_DEMO)\b(?P<body>.*)$"
)
TOKEN_RE = re.compile(r"(?P<key>[A-Za-z0-9_]+)=(?P<value>[^ \t\r\n]+)")


@dataclass(frozen=True)
class CommandSpec:
    name: str
    command: str
    expected_marker: str


@dataclass(frozen=True)
class CheckResult:
    check: str
    status: str
    detail: str


COMMANDS: tuple[CommandSpec, ...] = (
    CommandSpec("status", "safety tiny status", "TINY_SAFETY_STATUS"),
    CommandSpec("selftest", "safety tiny selftest", "TINY_SAFETY_SELFTEST"),
    CommandSpec("demo_normal", "safety tiny demo normal", "TINY_SAFETY_DEMO"),
    CommandSpec("demo_uncertain", "safety tiny demo uncertain", "TINY_SAFETY_DEMO"),
    CommandSpec("demo_needs_check", "safety tiny demo needs_check", "TINY_SAFETY_DEMO"),
    CommandSpec("demo_possible_risk", "safety tiny demo possible_risk", "TINY_SAFETY_DEMO"),
    CommandSpec("demo_sos", "safety tiny demo sos", "TINY_SAFETY_DEMO"),
    CommandSpec("demo_cancel", "safety tiny demo cancel", "TINY_SAFETY_DEMO"),
)

EXPECTED_DEMO_LABELS: dict[str, str] = {
    "normal": "normal",
    "uncertain": "uncertain",
    "needs_check": "needs_check",
    "possible_risk": "possible_risk",
    "sos": "safety_rule_required",
    "cancel": "safety_rule_required",
}

NON_CLAIMS = [
    "No firmware flash is performed by this validator.",
    "No real SMS, call, dispatch, or external escalation action is performed.",
    "Synthetic Tiny Safety labels are integration evidence, not field accuracy claims.",
    "No latency, RAM, flash, or power measurement is claimed from this report.",
]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.port and args.fixture_log:
        print("Use either --port or --fixture-log, not both.", file=sys.stderr)
        return 2
    if args.port and not args.i_understand_serial_hardware:
        print(
            "Refusing to open serial hardware without --i-understand-serial-hardware.",
            file=sys.stderr,
        )
        return 2

    run_id = args.run_id or f"tiny-safety-cli-{timestamp_for_path()}"
    output_root = Path(args.output_dir)
    if args.fixture_log:
        payload = run_fixture_validation(Path(args.fixture_log), output_root, run_id)
    elif args.port:
        payload = run_serial_validation(
            port=args.port,
            baud_rate=args.baud_rate,
            command_timeout_sec=args.command_timeout_sec,
            read_timeout_ms=args.read_timeout_ms,
            output_root=output_root,
            run_id=run_id,
        )
    else:
        payload = run_dry_run(output_root, run_id)

    print(payload["markdown_path"])
    return 0 if not has_failed_checks(payload) else 2


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory for timestamped JSON and Markdown reports.",
    )
    parser.add_argument("--run-id", help="Stable report directory name.")
    parser.add_argument("--fixture-log", help="Parse an existing Tiny Safety CLI log file.")
    parser.add_argument("--port", help="Serial port for bounded hardware validation.")
    parser.add_argument("--baud-rate", type=int, default=115200)
    parser.add_argument("--command-timeout-sec", type=float, default=4.0)
    parser.add_argument("--read-timeout-ms", type=int, default=250)
    parser.add_argument(
        "--i-understand-serial-hardware",
        action="store_true",
        help="Required guard before opening a serial port.",
    )
    return parser.parse_args(argv)


def run_dry_run(output_root: Path, run_id: str) -> dict[str, Any]:
    payload = base_payload(run_id=run_id, mode="dry_run")
    payload.update(
        {
            "hardware_contacted": False,
            "serial_port_opened": False,
            "firmware_flashed": False,
            "commands_planned": [asdict(command) for command in COMMANDS],
            "commands_sent": [],
            "observations": [],
            "checks": [
                asdict(
                    CheckResult(
                        "hardware_contact",
                        "PASS",
                        "default mode did not open serial hardware",
                    )
                ),
                asdict(
                    CheckResult(
                        "command_plan",
                        "PASS",
                        f"{len(COMMANDS)} Tiny Safety CLI commands planned",
                    )
                ),
                asdict(
                    CheckResult(
                        "runtime_validation",
                        "NOT_RUN",
                        "provide --fixture-log or guarded --port to validate firmware output",
                    )
                ),
            ],
            "result": "not_run",
        }
    )
    return write_report(payload, output_root, run_id)


def run_fixture_validation(fixture_log: Path, output_root: Path, run_id: str) -> dict[str, Any]:
    lines = fixture_log.read_text(encoding="utf-8").splitlines()
    observations = parse_marker_lines(lines)
    checks = evaluate_observations(observations)
    payload = base_payload(run_id=run_id, mode="fixture")
    payload.update(
        {
            "hardware_contacted": False,
            "serial_port_opened": False,
            "firmware_flashed": False,
            "source": {"fixture_log": str(fixture_log)},
            "commands_planned": [asdict(command) for command in COMMANDS],
            "commands_sent": [],
            "observations": observations,
            "raw_line_count": len(lines),
            "checks": [asdict(check) for check in checks],
            "result": result_from_checks(checks),
        }
    )
    return write_report(payload, output_root, run_id)


def run_serial_validation(
    *,
    port: str,
    baud_rate: int,
    command_timeout_sec: float,
    read_timeout_ms: int,
    output_root: Path,
    run_id: str,
) -> dict[str, Any]:
    serial_result = run_serial_commands(
        port=port,
        baud_rate=baud_rate,
        command_timeout_sec=command_timeout_sec,
        read_timeout_ms=read_timeout_ms,
    )
    records = ensure_list(serial_result.get("records"))
    lines: list[str] = []
    for record in records:
        lines.extend(str(line) for line in ensure_str_list(record.get("lines")))
    observations = parse_marker_lines(lines)
    checks = evaluate_observations(observations)
    checks.insert(
        0,
        CheckResult(
            "serial_session",
            "PASS" if serial_result.get("ok") else "FAIL",
            serial_result.get("error") or f"{len(records)} commands attempted on {port}",
        ),
    )
    payload = base_payload(run_id=run_id, mode="serial")
    payload.update(
        {
            "hardware_contacted": True,
            "serial_port_opened": bool(serial_result.get("serial_port_opened")),
            "firmware_flashed": False,
            "source": {
                "port": port,
                "baud_rate": baud_rate,
                "command_timeout_sec": command_timeout_sec,
                "read_timeout_ms": read_timeout_ms,
            },
            "commands_planned": [asdict(command) for command in COMMANDS],
            "commands_sent": records,
            "serial_result": serial_result,
            "observations": observations,
            "checks": [asdict(check) for check in checks],
            "result": result_from_checks(checks),
        }
    )
    return write_report(payload, output_root, run_id)


def parse_marker_lines(lines: list[str]) -> list[dict[str, Any]]:
    observations = []
    for line in lines:
        parsed = parse_marker_line(line)
        if parsed:
            observations.append(parsed)
    return observations


def parse_marker_line(line: str) -> dict[str, Any] | None:
    match = MARKER_RE.search(line)
    if not match:
        return None
    fields = {token.group("key"): token.group("value") for token in TOKEN_RE.finditer(match.group("body"))}
    return {"marker": match.group("marker"), "fields": fields, "line": line.strip()}


def evaluate_observations(observations: list[dict[str, Any]]) -> list[CheckResult]:
    status = first_record(observations, "TINY_SAFETY_STATUS")
    selftest = first_record(observations, "TINY_SAFETY_SELFTEST")
    demos = demo_records_by_name(observations)
    checks = [
        check(
            "marker_coverage",
            bool(status) and bool(selftest) and set(EXPECTED_DEMO_LABELS).issubset(demos),
            marker_coverage_detail(status, selftest, demos),
        ),
        check(
            "model_identity",
            all_model_identity_matches(observations),
            f"expected {EXPECTED_MODEL_ID} / {EXPECTED_MODEL_VERSION} / {EXPECTED_HARNESS_VERSION}",
        ),
        check(
            "dry_run_scope",
            all_dry_run_scope_matches(observations),
            "all observed Tiny Safety records must remain synthetic dry-run with no external actions",
        ),
        check(
            "status_shape",
            status_shape_matches(status),
            "status must report 14 features, 4 classes, dry_run=true, external_actions=false",
        ),
        check(
            "selftest_result",
            selftest_result_matches(selftest),
            "selftest must pass 4 exported synthetic vectors with 0 failures",
        ),
        check(
            "demo_labels",
            demo_labels_match(demos),
            demo_labels_detail(demos),
        ),
        check(
            "safety_rule_boundary",
            safety_rule_boundary_matches(demos),
            "SOS/cancel must be safety_rule_required=true; ordinary demos must not require safety rules",
        ),
    ]
    return checks


def first_record(observations: list[dict[str, Any]], marker: str) -> dict[str, Any] | None:
    return next((item for item in observations if item.get("marker") == marker), None)


def demo_records_by_name(observations: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    demos: dict[str, dict[str, Any]] = {}
    for item in observations:
        if item.get("marker") != "TINY_SAFETY_DEMO":
            continue
        name = item.get("fields", {}).get("name")
        if name:
            demos[str(name)] = item
    return demos


def marker_coverage_detail(
    status: dict[str, Any] | None,
    selftest: dict[str, Any] | None,
    demos: dict[str, dict[str, Any]],
) -> str:
    missing = []
    if not status:
        missing.append("status")
    if not selftest:
        missing.append("selftest")
    missing.extend(f"demo:{name}" for name in EXPECTED_DEMO_LABELS if name not in demos)
    return "all required markers observed" if not missing else "missing " + ", ".join(missing)


def all_model_identity_matches(observations: list[dict[str, Any]]) -> bool:
    if not observations:
        return False
    for item in observations:
        fields = item.get("fields", {})
        if fields.get("model_id") != EXPECTED_MODEL_ID:
            return False
        if fields.get("model_version") != EXPECTED_MODEL_VERSION:
            return False
        if fields.get("harness") != EXPECTED_HARNESS_VERSION:
            return False
    return True


def all_dry_run_scope_matches(observations: list[dict[str, Any]]) -> bool:
    if not observations:
        return False
    for item in observations:
        fields = item.get("fields", {})
        if fields.get("dry_run") != "true":
            return False
        if fields.get("synthetic_only") != "true":
            return False
        if fields.get("external_actions") not in (None, "false"):
            return False
    return True


def status_shape_matches(status: dict[str, Any] | None) -> bool:
    if not status:
        return False
    fields = status.get("fields", {})
    return (
        fields.get("features") == EXPECTED_FEATURE_COUNT
        and fields.get("classes") == EXPECTED_CLASS_COUNT
        and fields.get("dry_run") == "true"
        and fields.get("synthetic_only") == "true"
        and fields.get("external_actions") == "false"
    )


def selftest_result_matches(selftest: dict[str, Any] | None) -> bool:
    if not selftest:
        return False
    fields = selftest.get("fields", {})
    return (
        fields.get("result") == "pass"
        and fields.get("vectors") == EXPECTED_SELFTEST_VECTORS
        and fields.get("passed") == EXPECTED_SELFTEST_VECTORS
        and fields.get("failed") == "0"
    )


def demo_labels_match(demos: dict[str, dict[str, Any]]) -> bool:
    for name, expected_label in EXPECTED_DEMO_LABELS.items():
        fields = demos.get(name, {}).get("fields", {})
        if fields.get("label") != expected_label:
            return False
    return True


def demo_labels_detail(demos: dict[str, dict[str, Any]]) -> str:
    values = []
    for name, expected_label in EXPECTED_DEMO_LABELS.items():
        actual = demos.get(name, {}).get("fields", {}).get("label", "missing")
        values.append(f"{name}={actual}/{expected_label}")
    return "; ".join(values)


def safety_rule_boundary_matches(demos: dict[str, dict[str, Any]]) -> bool:
    for name in ("sos", "cancel"):
        if demos.get(name, {}).get("fields", {}).get("safety_rule_required") != "true":
            return False
    for name in ("normal", "uncertain", "needs_check", "possible_risk"):
        if demos.get(name, {}).get("fields", {}).get("safety_rule_required") != "false":
            return False
    return True


def run_serial_commands(
    *,
    port: str,
    baud_rate: int,
    command_timeout_sec: float,
    read_timeout_ms: int,
) -> dict[str, Any]:
    command_rows = [
        {
            "name": command.name,
            "command": command.command,
            "expected_marker": command.expected_marker,
        }
        for command in COMMANDS
    ]
    command_timeout_ms = max(1, int(command_timeout_sec * 1000))
    script = serial_powershell_script(
        port=port,
        baud_rate=baud_rate,
        command_rows=command_rows,
        command_timeout_ms=command_timeout_ms,
        read_timeout_ms=read_timeout_ms,
    )
    try:
        raw = run_powershell(script, timeout_seconds=max(20, int(command_timeout_sec * len(COMMANDS)) + 10))
        return json.loads(raw) if raw.strip() else {"ok": False, "error": "empty PowerShell output"}
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "serial_port_opened": False,
            "error": f"PowerShell serial validation timed out after {exc.timeout} seconds",
            "records": [],
        }
    except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "serial_port_opened": False,
            "error": str(exc),
            "records": [],
        }


def serial_powershell_script(
    *,
    port: str,
    baud_rate: int,
    command_rows: list[dict[str, str]],
    command_timeout_ms: int,
    read_timeout_ms: int,
) -> str:
    commands_json = json.dumps(command_rows, ensure_ascii=False)
    script = r"""
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$ErrorActionPreference = 'Stop'
$commandsJson = @'
__COMMANDS_JSON__
'@
$commands = @($commandsJson | ConvertFrom-Json)
$result = [ordered]@{
  port = __PORT__
  ok = $false
  error = $null
  serial_port_opened = $false
  records = @()
}
$sp = $null
try {
  $sp = [System.IO.Ports.SerialPort]::new(__PORT__, __BAUD_RATE__, [System.IO.Ports.Parity]::None, 8, [System.IO.Ports.StopBits]::One)
  $sp.ReadTimeout = __READ_TIMEOUT_MS__
  $sp.WriteTimeout = 500
  $sp.DtrEnable = $false
  $sp.RtsEnable = $false
  $sp.Open()
  $result.serial_port_opened = $true
  Start-Sleep -Milliseconds 300
  foreach ($cmd in $commands) {
    $record = [ordered]@{
      name = [string]$cmd.name
      command = [string]$cmd.command
      expected_marker = [string]$cmd.expected_marker
      ok = $false
      timeout = $false
      marker_line = $null
      lines = @()
      error = $null
    }
    try {
      $sp.DiscardInBuffer()
      $sp.WriteLine([string]$cmd.command)
      $deadline = [DateTime]::UtcNow.AddMilliseconds(__COMMAND_TIMEOUT_MS__)
      $text = ""
      $markerRegex = '\b' + [regex]::Escape([string]$cmd.expected_marker) + '\b'
      while ([DateTime]::UtcNow -lt $deadline) {
        $chunk = $sp.ReadExisting()
        if ($chunk) {
          $text += $chunk
          if ($text -match $markerRegex) {
            break
          }
        }
        Start-Sleep -Milliseconds 50
      }
      $lines = @($text -split "`r?`n" | Where-Object { $_ -ne "" })
      $record.lines = $lines
      foreach ($line in $lines) {
        if ($line -match $markerRegex) {
          $record.marker_line = $line
          $record.ok = $true
          break
        }
      }
      if (-not $record.ok) {
        $record.timeout = $true
      }
    } catch {
      $record.error = $_.Exception.Message
    }
    $result.records += $record
  }
  $allOk = $true
  foreach ($record in $result.records) {
    if (-not $record.ok) {
      $allOk = $false
    }
  }
  $result.ok = $allOk
} catch {
  $result.error = $_.Exception.Message
} finally {
  if ($sp -and $sp.IsOpen) { $sp.Close() }
}
$result | ConvertTo-Json -Depth 8
"""
    return (
        script.replace("__COMMANDS_JSON__", commands_json)
        .replace("__PORT__", ps_quote(port))
        .replace("__BAUD_RATE__", str(baud_rate))
        .replace("__READ_TIMEOUT_MS__", str(read_timeout_ms))
        .replace("__COMMAND_TIMEOUT_MS__", str(command_timeout_ms))
    )


def base_payload(*, run_id: str, mode: str) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "project": "Ego Link P0",
        "task": "MODEL-DEVICE-004",
        "serves_demo": "D5",
        "run_id": run_id,
        "mode": mode,
        "generated_at": utc_now(),
        "host": {"platform": platform.platform(), "python": sys.version.split()[0]},
        "non_claims": NON_CLAIMS,
    }


def write_report(payload: dict[str, Any], output_root: Path, run_id: str) -> dict[str, Any]:
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    json_path = run_dir / "tiny_safety_cli_report.json"
    markdown_path = run_dir / "tiny_safety_cli_report.md"
    payload["json_path"] = str(json_path)
    payload["markdown_path"] = str(markdown_path)
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    markdown_path.write_text(render_markdown_report(payload), encoding="utf-8")
    return payload


def render_markdown_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Tiny Safety Firmware CLI Validation",
        "",
        f"- Run ID: `{payload['run_id']}`",
        f"- Mode: `{payload['mode']}`",
        f"- Generated: `{payload['generated_at']}`",
        f"- Hardware contacted: `{payload.get('hardware_contacted')}`",
        f"- Serial port opened: `{payload.get('serial_port_opened')}`",
        f"- Firmware flashed: `{payload.get('firmware_flashed')}`",
        f"- Result: `{payload.get('result')}`",
        "",
        "## Checks",
        "",
        "| Check | Status | Detail |",
        "|---|---:|---|",
    ]
    for item in payload.get("checks", []):
        lines.append(f"| `{item['check']}` | {item['status']} | {escape_table(item['detail'])} |")

    lines.extend(["", "## Commands", "", "| Name | Command | Marker |", "|---|---|---|"])
    for command in payload.get("commands_planned", []):
        lines.append(
            f"| `{command['name']}` | `{command['command']}` | `{command['expected_marker']}` |"
        )

    observations = payload.get("observations", [])
    lines.extend(["", "## Observations", ""])
    if observations:
        for item in observations:
            fields = item.get("fields", {})
            label = fields.get("label") or fields.get("result") or fields.get("model_id")
            name = fields.get("name") or item.get("marker")
            lines.append(f"- `{item.get('marker')}` `{name}` `{label}`")
    else:
        lines.append("- No firmware marker lines parsed in this mode.")

    lines.extend(["", "## Non-Claims", ""])
    for claim in payload.get("non_claims", []):
        lines.append(f"- {claim}")
    lines.append("")
    return "\n".join(lines)


def check(name: str, condition: bool, detail: str) -> CheckResult:
    return CheckResult(name, "PASS" if condition else "FAIL", detail)


def result_from_checks(checks: list[CheckResult]) -> str:
    return "fail" if any(item.status == "FAIL" for item in checks) else "pass"


def has_failed_checks(payload: dict[str, Any]) -> bool:
    return any(item.get("status") == "FAIL" for item in payload.get("checks", []))


def ensure_list(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return [value]
    return []


def ensure_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


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


def ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def escape_table(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def timestamp_for_path() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


if __name__ == "__main__":
    raise SystemExit(main())

"""Validate the server-side location memory and active belief gate.

This gate talks only to the Message Hub. It does not flash firmware, open
serial ports, or require a USB runtime path. By default it seeds a synthetic
device with one fixed location report followed by one no-fix report, then
checks that the latest failure is visible without erasing the remembered
calibration.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pc_simulator import protocol  # noqa: E402
from scripts.validate_fw001_hw_loop import (  # noqa: E402
    DEFAULT_HUB_URL,
    FieldValidationError,
    HubClient,
    compact_utc_now,
    utc_now,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "reports" / "location_memory"
DEFAULT_TOKEN_FILE = REPO_ROOT / "server" / "runtime" / "vps_message_hub_token.txt"


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_token(token_file: Path | None) -> str | None:
    env_token = os.environ.get("EGOLINK_MESSAGE_HUB_TOKEN")
    if env_token:
        return env_token
    if token_file and token_file.exists():
        return token_file.read_text(encoding="utf-8").strip() or None
    return None


def find_device(state: dict[str, Any], device_id: str) -> dict[str, Any]:
    for device in state.get("devices") or []:
        if isinstance(device, dict) and device.get("device_id") == device_id:
            return device
    return {}


def redacted_location_memory(memory: dict[str, Any]) -> dict[str, Any]:
    redacted = json.loads(json.dumps(memory, ensure_ascii=False))
    last_known = redacted.pop("last_known_location", None)
    if isinstance(last_known, dict):
        redacted["last_known_location_present"] = last_known.get("lat") is not None and last_known.get("lon") is not None
        redacted["last_known_location_updated_at"] = last_known.get("updated_at")
    return redacted


def seed_synthetic_location_sequence(client: HubClient, *, device_id: str, test_run_id: str) -> None:
    client.post(
        "/api/v1/test-runs",
        {
            "test_run_id": test_run_id,
            "task_id": "LOC-003",
            "device_id": device_id,
            "status": "active",
            "source": "location_memory_gate",
        },
    )
    fixed = protocol.event_message(
        device_id,
        utc_now(),
        1,
        "location_report",
        "normal",
        fw_version="0.1.0-location-memory-gate",
        test_run_id=test_run_id,
        source="synthetic_gate_gnss",
        source_status="mock",
        fix=True,
        lat=0.0,
        lon=0.0,
        hdop=0.9,
        satellites=12,
        gnss_state="fix",
        transport={"type": "synthetic_gate"},
    )
    client.post(f"/api/v1/devices/{device_id}/telemetry", fixed)
    no_fix = protocol.event_message(
        device_id,
        utc_now(),
        2,
        "location_report",
        "normal",
        fw_version="0.1.0-location-memory-gate",
        test_run_id=test_run_id,
        source="synthetic_gate_gnss",
        source_status="mock",
        fix=False,
        lat=None,
        lon=None,
        gnss_state="no_fix",
        gnss_query_ok=True,
        location_request_cmd_id="cmd-location-memory-gate",
        transport={"type": "synthetic_gate"},
    )
    client.post(f"/api/v1/devices/{device_id}/telemetry", no_fix)


def evaluate_device_state(device: dict[str, Any], exported: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    latest_location = device.get("latest_location") if isinstance(device.get("latest_location"), dict) else {}
    location_memory = device.get("location_memory") if isinstance(device.get("location_memory"), dict) else {}
    observability = device.get("observability") if isinstance(device.get("observability"), dict) else {}
    belief = observability.get("location_belief") if isinstance(observability.get("location_belief"), dict) else {}
    memory_obs = observability.get("location_memory") if isinstance(observability.get("location_memory"), dict) else {}
    export_obs = (
        exported.get("observability_summary", {})
        .get("latest_observability", {})
        if isinstance(exported.get("observability_summary"), dict)
        else {}
    )
    export_belief = export_obs.get("location_belief") if isinstance(export_obs.get("location_belief"), dict) else {}
    export_memory = export_obs.get("location_memory") if isinstance(export_obs.get("location_memory"), dict) else {}

    if latest_location.get("event_type") != "location_report":
        errors.append("latest_location must remain a location_report")
    if latest_location.get("fix") is not False:
        errors.append("latest_location must expose the later no-fix report")
    if latest_location.get("gnss_state") != "no_fix":
        errors.append(f"latest_location.gnss_state={latest_location.get('gnss_state')} did not become no_fix")
    if location_memory.get("state") != "Fine":
        errors.append(f"location_memory.state={location_memory.get('state')} did not preserve Fine")
    if not isinstance(location_memory.get("last_no_fix"), dict):
        errors.append("location_memory.last_no_fix must preserve the failed GNSS attempt")
    if belief.get("state") != "Predicted":
        errors.append(f"observability.location_belief.state={belief.get('state')} did not become Predicted")
    if belief.get("reason") != "last_known_after_gnss_no_fix":
        errors.append(
            "observability.location_belief.reason="
            f"{belief.get('reason')} did not explain the memory-backed no-fix state"
        )
    if memory_obs.get("state") != "Fine":
        errors.append("observability.location_memory must expose the preserved Fine memory")
    if export_belief.get("state") != "Predicted":
        errors.append("test-run export observability_summary must include Predicted active belief")
    if export_memory.get("state") != "Fine":
        errors.append("test-run export observability_summary must include Fine location memory")
    return errors


def run_gate(
    *,
    hub_url: str,
    device_id: str,
    test_run_id: str,
    output_dir: Path,
    token: str | None,
    seed_synthetic: bool,
) -> dict[str, Any]:
    client = HubClient(hub_url, token=token)
    if seed_synthetic:
        seed_synthetic_location_sequence(client, device_id=device_id, test_run_id=test_run_id)
    state = client.get("/api/state")
    device = find_device(state, device_id)
    if not device:
        raise FieldValidationError(f"device {device_id} not found in /api/state")
    exported = client.get(f"/api/v1/test-runs/{test_run_id}/export")
    errors = evaluate_device_state(device, exported)
    observability = device.get("observability") if isinstance(device.get("observability"), dict) else {}
    report = {
        "result": "PASS" if not errors else "FAIL",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "hub_url": hub_url,
        "device_id": device_id,
        "test_run_id": test_run_id,
        "seed_synthetic": seed_synthetic,
        "errors": errors,
        "latest_location": {
            "event_type": (device.get("latest_location") or {}).get("event_type"),
            "fix": (device.get("latest_location") or {}).get("fix"),
            "gnss_state": (device.get("latest_location") or {}).get("gnss_state"),
            "server_received_at": (device.get("latest_location") or {}).get("server_received_at"),
        },
        "location_belief": observability.get("location_belief"),
        "location_memory": redacted_location_memory(device.get("location_memory") or {}),
        "export_observability": exported.get("observability_summary"),
    }
    write_json(output_dir / "location_memory_gate_report.json", report)
    write_markdown_report(output_dir / "location_memory_gate_report.md", report)
    return report


def write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    memory = report.get("location_memory") if isinstance(report.get("location_memory"), dict) else {}
    belief = report.get("location_belief") if isinstance(report.get("location_belief"), dict) else {}
    latest = report.get("latest_location") if isinstance(report.get("latest_location"), dict) else {}
    lines = [
        "# Location Memory Gate",
        "",
        f"- Result: {report['result']}",
        f"- Device: {report.get('device_id')}",
        f"- Test run: {report.get('test_run_id')}",
        f"- Seed synthetic: {report.get('seed_synthetic')}",
        f"- Latest location: fix={latest.get('fix')} gnss_state={latest.get('gnss_state')}",
        f"- Active belief: {belief.get('state')} / {belief.get('reason')}",
        f"- Location memory: {memory.get('state')} / {memory.get('reason')}",
        f"- Last known location present: {memory.get('last_known_location_present')}",
        "",
        "## Errors",
        "",
    ]
    if report.get("errors"):
        lines.extend(f"- {item}" for item in report["errors"])
    else:
        lines.append("- none")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hub-url", default=DEFAULT_HUB_URL)
    parser.add_argument("--device-id", default="ego-link-r0-location-memory-gate")
    parser.add_argument("--test-run-id")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--token-file", type=Path, default=DEFAULT_TOKEN_FILE)
    parser.add_argument("--no-seed-synthetic", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    test_run_id = args.test_run_id or f"location-memory-gate-{compact_utc_now()}"
    output_dir = args.output_dir or (DEFAULT_OUTPUT_ROOT / test_run_id)
    report = run_gate(
        hub_url=args.hub_url,
        device_id=args.device_id,
        test_run_id=test_run_id,
        output_dir=output_dir,
        token=read_token(args.token_file),
        seed_synthetic=not args.no_seed_synthetic,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"{report['result']} location memory gate: {output_dir / 'location_memory_gate_report.md'}")
    return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

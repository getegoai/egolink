"""Prepare a D2 reference-point field kit without contacting hardware.

The generated kit contains a strict FIELD-003 manifest template, a concise
operator runbook, a checklist, and read-only preflight/post-run commands. It
does not read tokens, contact the VPS, send device commands, open serial ports,
flash firmware, or expose coordinates outside the selected evidence directory.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "reports" / "d2_field"
DEFAULT_HUB_URL = "http://203.0.113.10:8790"
DEFAULT_DEVICE_ID = "ego-link-r1-connectivity-001"
DEFAULT_BOARD_ID = "connectivity-node-001"
DEFAULT_FW_VERSION = "0.1.0-model-device-006-tiny-safety-hw"
DEFAULT_MESSAGE_TEST_RUN_ID = "MODEL-DEVICE-006-hw-20260707-d1"
DEFAULT_FIRMWARE_REF = "app-commit:cf5b4a6"
DEFAULT_TOKEN_FILE = "server/runtime/vps_message_hub_token.txt"
KIT_VERSION = "D2.reference_field_kit.v1"
KIT_MANIFEST = "d2_field_kit.json"
FIELD_MANIFEST = "field_manifest.json"
RUNBOOK = "D2_FIELD_RUNBOOK.md"
CHECKLIST = "D2_FIELD_CHECKLIST.md"

POINTS = (
    ("open_sky_01", "open_sky", "Open sky reference point"),
    ("street_between_buildings_01", "street_between_buildings", "Street between buildings reference point"),
    ("tree_cover_01", "tree_cover", "Tree-cover reference point"),
)
MODES = ("cold", "warm")
ATTEMPTS_PER_MODE = 5


class D2FieldKitError(RuntimeError):
    """Raised when a field-kit input would produce an unsafe or invalid kit."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_run_id() -> str:
    return datetime.now(timezone.utc).strftime("D2-001-reference-%Y%m%d-%H%MZ")


def validate_run_id(run_id: str) -> str:
    value = run_id.strip()
    if not value or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{2,95}", value):
        raise D2FieldKitError("run ID must be 3-96 characters using letters, numbers, dot, dash, or underscore")
    return value


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def ps_quote(value: object) -> str:
    text = str(value)
    if re.fullmatch(r"[A-Za-z0-9._:/\\<>-]+", text):
        return text
    return "'" + text.replace("'", "''") + "'"


def ps_command(parts: list[object]) -> str:
    rendered = [ps_quote(item) for item in parts]
    return " `\n  ".join(rendered)


def reference_points() -> list[dict[str, Any]]:
    return [
        {
            "point_id": point_id,
            "name": name,
            "point_type": point_type,
            "reference": {
                "lat": "<fill-reference-latitude>",
                "lon": "<fill-reference-longitude>",
                "method": "<phone_gnss_5min_average|map_pick_satellite_view|survey_marker>",
                "recorded_at": "<fill-ISO-8601-UTC>",
                "phone_accuracy_m": "<optional-number>",
            },
            "notes": "<sky view, nearby structures, weather>",
        }
        for point_id, point_type, name in POINTS
    ]


def attempts() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for point_id, _point_type, _name in POINTS:
        for mode in MODES:
            for number in range(1, ATTEMPTS_PER_MODE + 1):
                rows.append(
                    {
                        "attempt_id": f"{point_id}-{mode}-{number:02d}",
                        "point_id": point_id,
                        "mode": mode,
                        "command_id": None,
                        "started_at": "<fill-ISO-8601-UTC>",
                        "ended_at": "<fill-ISO-8601-UTC>",
                        "operator_notes": "<stationary, obstruction, reset/power state, visible fix/no-fix>",
                    }
                )
    return rows


def build_field_manifest(
    *,
    run_id: str,
    board_id: str,
    device_id: str,
    fw_version: str,
    firmware_ref: str,
    message_test_run_id: str,
) -> dict[str, Any]:
    return {
        "schema_version": "egolink.field003_manifest.v0.2",
        "field_run_id": run_id,
        "test_run_id": message_test_run_id,
        "board_id": board_id,
        "device_id": device_id,
        "firmware_version": fw_version,
        "firmware_commit_or_image": firmware_ref,
        "connection_path": "vps_message_hub_usb_free",
        "runtime_usb_connected": False,
        "operator": "<fill-operator-initials>",
        "started_at": "<fill-ISO-8601-UTC>",
        "ended_at": "<fill-ISO-8601-UTC>",
        "reference_points": reference_points(),
        "attempts": attempts(),
        "notes": [
            "Exact coordinates stay only in this ignored reports directory.",
            "A partial run is useful evidence but cannot pass strict FIELD-003 acceptance.",
            "Cold means GNSS/device power-off for at least 10 minutes before the attempt.",
        ],
    }


def build_commands(
    *,
    run_id: str,
    hub_url: str,
    device_id: str,
    message_test_run_id: str,
    token_file: str,
    output_dir: Path,
) -> dict[str, dict[str, Any]]:
    manifest_path = output_dir / FIELD_MANIFEST
    preflight = [
        "python", "scripts\\observe_field_readiness.py", "--hub", hub_url,
        "--device-id", device_id, "--run-id", f"{run_id}-preflight",
        "--duration-sec", "0", "--json",
    ]
    observe = [
        "python", "scripts\\observe_field_readiness.py", "--hub", hub_url,
        "--device-id", device_id, "--run-id", f"{run_id}-observer",
        "--duration-sec", "14400", "--poll-interval-sec", "60",
    ]
    postrun = [
        "python", "scripts\\run_location_d2_d5_pipeline.py", "--hub", hub_url,
        "--test-run-id", message_test_run_id, "--manifest", str(manifest_path),
        "--run-id", run_id, "--token-file", token_file,
        "--request-timeout-sec", "120", "--json",
    ]
    return {
        "preflight": {"argv": preflight, "powershell": ps_command(preflight), "read_only": True},
        "long_observer": {"argv": observe, "powershell": ps_command(observe), "read_only": True},
        "postrun": {"argv": postrun, "powershell": ps_command(postrun), "read_only": True},
    }


def render_runbook(kit: dict[str, Any]) -> str:
    commands = kit["commands"]
    run_id = kit["run_id"]
    return f"""# D2 Reference-Point Field Run

- Run ID: `{run_id}`
- Device: `{kit['device_id']}`
- Message test run: `{kit['message_test_run_id']}`
- Evidence directory: `{kit['output_dir']}`

This task serves D2. It records reference-point evidence for fix rate, TTFF,
median error, and p90 error. It does not claim product accuracy.

## Before Leaving

1. Open the VPS Dashboard and confirm the device is fresh.
2. Run the read-only preflight:

```powershell
{commands['preflight']['powershell']}
```

3. Confirm the firmware version and Message Hub test-run ID match this kit.
4. Keep `field_manifest.json` private. Exact coordinates belong only in this
   ignored evidence directory.
5. On a phone, open `{kit['hub_url']}/d2-reference-capture`. The page stores
   reference coordinates and attempt timestamps only in that browser and can
   export a compatible `field_manifest.json`.

## At Each Reference Point

Use all three environments: open sky, a street between buildings, and tree
cover. Record a phone five-minute average, satellite map pick, or survey marker
as the reference coordinate.

For strict FIELD-003 acceptance, perform five cold and five warm attempts per
point. Cold means at least ten minutes powered off before the attempt. Warm
attempts keep the device powered and stationary. Record UTC start/end times in
`field_manifest.json`; `command_id` may remain null when periodic uploads are
matched by the time window.

A shorter run is still worth keeping: fill only completed attempts and remove
unused placeholder rows. It will produce an explainable partial/failed gate
for D5 review, but it cannot be reported as FIELD-003 acceptance.

Optional four-hour read-only observer:

```powershell
{commands['long_observer']['powershell']}
```

## After Returning

Finish the run timestamps and remove every unexecuted placeholder attempt.
The mobile capture page can provide the completed manifest instead of manual
JSON editing. Then fetch the bounded Message Hub export and run D2 -> D5 in one command:

```powershell
{commands['postrun']['powershell']}
```

Review:

- `reports/location_accuracy/{run_id}/location_accuracy_report.md`
- `reports/data_flywheel/{run_id}-data-flywheel/data_flywheel_status.md`
- `reports/location_pipeline/{run_id}/location_d2_d5_pipeline.md`

The raw export and exact reference coordinates remain under `reports/gnss/`
and `reports/d2_field/`; Dashboard summaries remain bounded and redacted.
"""


def render_checklist(kit: dict[str, Any]) -> str:
    rows = "\n".join(
        f"- [ ] `{point_id}`: reference recorded; 5 cold; 5 warm; stationary notes complete"
        for point_id, _point_type, _name in POINTS
    )
    return f"""# D2 Field Checklist

- [ ] Preflight reports `field_ready=true` and the Dashboard is reachable.
- [ ] Device ID is `{kit['device_id']}`.
- [ ] Firmware is `{kit['fw_version']}` or the manifest has been corrected.
- [ ] Runtime is battery/power-bank supplied with USB disconnected.
- [ ] GNSS antenna is attached and the device has outdoor sky exposure.
- [ ] Reference method and phone/map accuracy notes are recorded.
{rows}
- [ ] Unexecuted placeholder attempts were removed from `field_manifest.json`.
- [ ] Exact coordinates were not copied into docs, commits, or screenshots.
- [ ] Post-run D2 -> D5 command completed and reports were reviewed.
- [ ] Any incomplete run is labelled partial evidence, not acceptance.
"""


def prepare_kit(
    *,
    output_root: Path,
    run_id: str,
    hub_url: str,
    device_id: str,
    board_id: str,
    fw_version: str,
    firmware_ref: str,
    message_test_run_id: str,
    token_file: str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    run_id = validate_run_id(run_id)
    output_dir = output_root / run_id
    commands = build_commands(
        run_id=run_id,
        hub_url=hub_url,
        device_id=device_id,
        message_test_run_id=message_test_run_id,
        token_file=token_file,
        output_dir=output_dir,
    )
    kit = {
        "schema_version": KIT_VERSION,
        "generated_at": generated_at or utc_now(),
        "run_id": run_id,
        "hub_url": hub_url.rstrip("/"),
        "device_id": device_id,
        "board_id": board_id,
        "fw_version": fw_version,
        "firmware_ref": firmware_ref,
        "message_test_run_id": message_test_run_id,
        "output_dir": str(output_dir),
        "commands": commands,
        "strict_protocol": {"point_count": 3, "attempts_per_point_mode": 5, "attempt_count": 30},
        "scope": {
            "hardware_contacted": False,
            "vps_contacted": False,
            "commands_sent": False,
            "serial_opened": False,
            "firmware_flashed": False,
            "token_read": False,
            "product_accuracy_claimed": False,
        },
    }
    write_json(output_dir / FIELD_MANIFEST, build_field_manifest(
        run_id=run_id,
        board_id=board_id,
        device_id=device_id,
        fw_version=fw_version,
        firmware_ref=firmware_ref,
        message_test_run_id=message_test_run_id,
    ))
    write_json(output_dir / KIT_MANIFEST, kit)
    (output_dir / RUNBOOK).write_text(render_runbook(kit), encoding="utf-8")
    (output_dir / CHECKLIST).write_text(render_checklist(kit), encoding="utf-8")
    return kit


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default=default_run_id())
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--hub-url", default=DEFAULT_HUB_URL)
    parser.add_argument("--device-id", default=DEFAULT_DEVICE_ID)
    parser.add_argument("--board-id", default=DEFAULT_BOARD_ID)
    parser.add_argument("--fw-version", default=DEFAULT_FW_VERSION)
    parser.add_argument("--firmware-ref", default=DEFAULT_FIRMWARE_REF)
    parser.add_argument("--message-test-run-id", default=DEFAULT_MESSAGE_TEST_RUN_ID)
    parser.add_argument("--token-file", default=DEFAULT_TOKEN_FILE)
    parser.add_argument("--generated-at")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        kit = prepare_kit(
            output_root=args.output_root,
            run_id=args.run_id,
            hub_url=args.hub_url,
            device_id=args.device_id,
            board_id=args.board_id,
            fw_version=args.fw_version,
            firmware_ref=args.firmware_ref,
            message_test_run_id=args.message_test_run_id,
            token_file=args.token_file,
            generated_at=args.generated_at,
        )
    except D2FieldKitError as exc:
        print(f"FAIL D2 field kit: {exc}")
        return 1
    if args.json:
        print(json.dumps(kit, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"D2 field kit ready: {kit['output_dir']}")
        print(f"Runbook: {Path(kit['output_dir']) / RUNBOOK}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

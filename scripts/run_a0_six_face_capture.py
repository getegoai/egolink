"""Create exactly one operator-confirmed `capture_imu_window` command for one A0-001 pose.

Six-face calibration needs the device physically re-posed and re-settled between
windows, so this tool never loops: one invocation is one pose. It defaults to a
dry run, refuses to execute without an explicit per-pose stationary attestation,
and never overwrites an existing pose record.

`scripts/run_imu_capture_session.py` stays untouched: it requires exactly three
windows, creates its test run unconditionally, and labels evidence `D5-002` or
`FIELD-011`. None of that fits a seven-pose calibration run.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pc_simulator.imu_six_face_calibration import SOURCE_ROLES
from scripts.run_imu_capture_session import (
    INTERVAL_MS,
    SAMPLE_COUNT,
    TRANSPORT_TYPES,
    CaptureSessionError,
    HubClient,
    _object,
    _redact,
    _wait_for_ack,
    _wait_for_window,
    validate_hub_url,
)


RECORD_SCHEMA_VERSION = "egolink.a0_six_face_capture.v0.1"
TASK_ID = "A0-001"
# A face cannot always be named before it is measured: with the module fixed in an
# enclosure the operator rests it on an arbitrary side, and which sensor axis ends up
# vertical is only known from the samples. Recording "unidentified" is honest; forcing a
# guessed face label onto the record is not. The role binding happens later in the
# calibration metadata, where the tool re-checks it against the data.
UNIDENTIFIED_POSE = "unidentified"
CAPTURE_POSES = (*SOURCE_ROLES, UNIDENTIFIED_POSE)
CMD_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,16}$")
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,48}$")


class SixFaceCaptureError(RuntimeError):
    """A pose capture precondition or bounded execution failed."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe(value: str, name: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise SixFaceCaptureError(f"{name} has an invalid format: {value!r}")
    return value


def build_record(
    *,
    pose: str,
    cmd_id: str,
    device_id: str,
    test_run_id: str,
    transport_type: str,
    execute: bool,
    hub_url: str | None,
    now_fn: Callable[[], str] = utc_now,
) -> dict[str, Any]:
    return {
        "schema_version": RECORD_SCHEMA_VERSION,
        "task_id": TASK_ID,
        "pose": pose,
        "cmd_id": cmd_id,
        "device_id": device_id,
        "test_run_id": test_run_id,
        "transport_type": transport_type,
        "command": {
            "cmd": "capture_imu_window",
            "sample_count": SAMPLE_COUNT,
            "interval_ms": INTERVAL_MS,
        },
        "mode": "execute" if execute else "dry_run",
        "status": "running" if execute else "dry_run_ready",
        "started_at": now_fn(),
        "completed_at": None,
        "hub_url": hub_url if execute else None,
        "operator_confirmed_stationary": execute,
        "test_run_created": False,
        "test_run_reused": False,
        "external_actions": [],
        "ack": None,
        "window": None,
        "training_allowed": False,
        "production_ready": False,
        "hardware_gate_passed": False,
    }


def ensure_test_run(
    client: Any,
    record: dict[str, Any],
    *,
    test_run_id: str,
    device_id: str,
    create_missing: bool,
) -> None:
    """Reuse the calibration test run; all seven poses must share exactly one."""
    action = {"action": "resolve_test_run", "test_run_id": test_run_id, "state": "attempted"}
    record["external_actions"].append(action)
    response = client.get("/api/v1/test-runs")
    runs = _object(response, "test-runs response").get("test_runs")
    if not isinstance(runs, list):
        raise SixFaceCaptureError("Message Hub test-runs response must contain an array")
    existing = next(
        (run for run in runs if isinstance(run, dict) and run.get("test_run_id") == test_run_id),
        None,
    )
    if existing is not None:
        bound_device = existing.get("device_id")
        if bound_device is not None and bound_device != device_id:
            raise SixFaceCaptureError(
                f"test run {test_run_id} is bound to device {bound_device}, not {device_id}"
            )
        action["state"] = "reused"
        record["test_run_reused"] = True
        return
    if not create_missing:
        raise SixFaceCaptureError(
            f"test run {test_run_id} does not exist; pass --create-test-run for the first pose only"
        )
    response = client.post(
        "/api/v1/test-runs",
        {
            "test_run_id": test_run_id,
            "task_id": TASK_ID,
            "device_id": device_id,
            "status": "active",
            "goal": "A0-001 six-face IMU engineering calibration capture",
        },
    )
    created = _object(response, "test-run creation response").get("test_run")
    if not isinstance(created, dict) or created.get("test_run_id") != test_run_id:
        raise SixFaceCaptureError("Message Hub did not create the requested test run")
    action["state"] = "created"
    record["test_run_created"] = True


def capture_pose(
    *,
    pose: str,
    cmd_id: str,
    device_id: str,
    test_run_id: str,
    transport_type: str,
    execute: bool = False,
    create_test_run: bool = False,
    client: Any | None = None,
    hub_url: str | None = None,
    timeout_sec: float = 120.0,
    poll_interval_sec: float = 2.0,
    now_fn: Callable[[], str] = utc_now,
    monotonic_fn: Callable[[], float] = time.monotonic,
    sleep_fn: Callable[[float], None] = time.sleep,
    redaction_values: tuple[str, ...] = (),
) -> dict[str, Any]:
    if pose not in CAPTURE_POSES:
        raise SixFaceCaptureError(f"pose must be one of {list(CAPTURE_POSES)}")
    if transport_type not in TRANSPORT_TYPES:
        raise SixFaceCaptureError(f"transport type must be one of {sorted(TRANSPORT_TYPES)}")
    _safe(cmd_id, "cmd_id", CMD_ID_RE)
    _safe(device_id, "device_id", SAFE_ID_RE)
    _safe(test_run_id, "test_run_id", SAFE_ID_RE)
    if timeout_sec <= 0 or poll_interval_sec <= 0:
        raise SixFaceCaptureError("timeout and poll interval must be positive")

    record = build_record(
        pose=pose,
        cmd_id=cmd_id,
        device_id=device_id,
        test_run_id=test_run_id,
        transport_type=transport_type,
        execute=execute,
        hub_url=hub_url,
        now_fn=now_fn,
    )
    if not execute:
        record["completed_at"] = now_fn()
        return record
    if client is None:
        raise SixFaceCaptureError("execute mode requires a Message Hub client")

    try:
        ensure_test_run(
            client,
            record,
            test_run_id=test_run_id,
            device_id=device_id,
            create_missing=create_test_run,
        )
        action = {"action": "create_command", "cmd_id": cmd_id, "state": "attempted"}
        record["external_actions"].append(action)
        response = client.post(
            f"/api/v1/devices/{device_id}/commands",
            {
                "cmd": "capture_imu_window",
                "cmd_id": cmd_id,
                "test_run_id": test_run_id,
                "payload": {"sample_count": SAMPLE_COUNT, "interval_ms": INTERVAL_MS},
            },
        )
        created = _object(response, "command creation response").get("command")
        if not isinstance(created, dict) or created.get("cmd_id") != cmd_id or created.get("status") != "pending":
            raise SixFaceCaptureError(f"Message Hub did not create pending command {cmd_id}")
        action["state"] = "ok"

        deadline = monotonic_fn() + timeout_sec
        waiting = {
            "device_id": device_id,
            "cmd_id": cmd_id,
            "test_run_id": test_run_id,
            "transport_type": transport_type,
            "deadline": deadline,
            "monotonic_fn": monotonic_fn,
            "sleep_fn": sleep_fn,
            "poll_interval_sec": poll_interval_sec,
        }
        ack = _wait_for_ack(client, **waiting)
        window = _wait_for_window(client, **waiting)
    except Exception as error:  # Never let an unredacted token reach a traceback.
        record.update(
            {
                "status": "failed",
                "completed_at": now_fn(),
                "error": _redact(str(error), redaction_values),
            }
        )
        return record

    record.update(
        {
            "status": "completed",
            "completed_at": now_fn(),
            "ack": {"status": "ok", "test_run_id": ack["test_run_id"], "transport_type": transport_type},
            "window": window,
        }
    )
    return record


def write_record(path: Path, record: dict[str, Any]) -> None:
    if path.exists():
        raise SixFaceCaptureError(f"pose record already exists and will not be overwritten: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device-id", required=True)
    parser.add_argument("--test-run-id", required=True)
    parser.add_argument(
        "--pose",
        required=True,
        choices=list(CAPTURE_POSES),
        help="Use 'unidentified' when the face is only knowable from the samples",
    )
    parser.add_argument("--cmd-id", required=True, help="1-16 safe characters; window_id derives from it")
    parser.add_argument("--transport-type", required=True, choices=sorted(TRANSPORT_TYPES))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--hub", default="http://127.0.0.1:8790")
    parser.add_argument("--token-env", default="EGOLINK_MESSAGE_HUB_TOKEN")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually create the command; omitted means dry-run and no device contact",
    )
    parser.add_argument(
        "--operator-confirmed-stationary",
        action="store_true",
        help="Required with --execute: the operator placed this pose and confirmed it is still",
    )
    parser.add_argument(
        "--create-test-run",
        action="store_true",
        help="First pose only; later poses must reuse the same test run",
    )
    parser.add_argument("--timeout-sec", type=float, default=120.0)
    parser.add_argument("--poll-interval-sec", type=float, default=2.0)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    token: str | None = None
    try:
        if args.output.exists():
            raise SixFaceCaptureError(
                f"pose record already exists and will not be overwritten: {args.output}"
            )
        client = None
        hub_url = None
        if args.execute:
            if not args.operator_confirmed_stationary:
                raise SixFaceCaptureError(
                    "--execute requires --operator-confirmed-stationary for this specific pose"
                )
            hub_url = validate_hub_url(args.hub)
            token = os.environ.get(args.token_env) or None
            client = HubClient(hub_url, token=token)
        record = capture_pose(
            pose=args.pose,
            cmd_id=args.cmd_id,
            device_id=args.device_id,
            test_run_id=args.test_run_id,
            transport_type=args.transport_type,
            execute=args.execute,
            create_test_run=args.create_test_run,
            client=client,
            hub_url=hub_url,
            timeout_sec=args.timeout_sec,
            poll_interval_sec=args.poll_interval_sec,
            redaction_values=(token,) if token else (),
        )
        write_record(args.output, record)
    except Exception as error:  # Never let an unredacted token reach a traceback.
        message = _redact(str(error), (token,) if token else ())
        print(json.dumps({"ok": False, "error": message}, ensure_ascii=False))
        return 1

    ok = record["status"] in {"completed", "dry_run_ready"}
    summary = {
        "ok": ok,
        "pose": record["pose"],
        "cmd_id": record["cmd_id"],
        "mode": record["mode"],
        "status": record["status"],
        "hardware_gate_passed": False,
        "record": str(args.output),
    }
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    elif record["mode"] == "dry_run":
        print(f"dry run only: would request pose {record['pose']} as {record['cmd_id']}")
        print("no command was created and the device was not contacted")
    else:
        print(f"pose {record['pose']} -> {record['status']} (record: {args.output})")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())

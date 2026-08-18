"""FT-001B bounded IMU window burst runner.

Sequentially issues N bounded `capture_imu_window` commands (each
--sample-count samples x 50 ms; default 300 = 15 s) over the existing
Message Hub command queue and waits for each window's LTE ACK and
raw-frame evidence before continuing.

Windows are discrete captures; gaps between them are NOT hidden.  The
honest inter-window coverage must later be derived from each window's
`capture_start_uptime_us`/`capture_end_uptime_us` in the VPS export.

The runner creates exactly one test run and only `capture_imu_window`
commands.  It never flashes firmware, opens serial, or changes configuration.

Default mode is dry-run; pass --execute to send commands.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import re
import secrets
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_imu_capture_session import (  # noqa: E402
    CaptureSessionError,
    INTERVAL_MS,
    SAMPLE_COUNT,
    _object,
    _redact,
    _validate_ok_ack,
    _wait_for_ack,
    _wait_for_window,
    validate_hub_url,
)
from scripts.validate_fw001_hw_loop import HubClient  # noqa: E402

RECORD_SCHEMA_VERSION = "egolink.ft001b_imu_burst_execution.v0.1"
CMD_ID_RE = re.compile(r"^[a-z0-9]{1,16}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_field_session_id(now: datetime) -> str:
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    return f"FS-{stamp}-{secrets.token_hex(6)}"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device-id", default="ego-link-r1-connectivity-001")
    parser.add_argument("--test-run-id", required=True)
    parser.add_argument("--task-id", default="FT-001B")
    parser.add_argument("--cmd-prefix", default="ftb")
    parser.add_argument("--window-count", type=int, default=10)
    parser.add_argument("--sample-count", type=int, default=300,
                        help="IMU samples per window (firmware accepts 100-600, default 300 = 15s)")
    parser.add_argument("--hub", default="http://203.0.113.10:8790")
    parser.add_argument("--token-env", default="EGOLINK_MESSAGE_HUB_TOKEN")
    parser.add_argument("--token-file", default=str(REPO_ROOT / "server" / "runtime" / "vps_message_hub_token.txt"))
    parser.add_argument("--timeout-sec", type=float, default=180.0)
    parser.add_argument("--poll-interval-sec", type=float, default=3.0)
    parser.add_argument("--inter-window-delay-sec", type=float, default=5.0)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def load_token(args: argparse.Namespace) -> str | None:
    token = os.environ.get(args.token_env)
    if token:
        return token
    token_path = Path(args.token_file)
    if token_path.exists():
        value = token_path.read_text(encoding="utf-8").strip()
        return value or None
    return None


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.window_count < 1 or args.window_count > 60:
        print(json.dumps({"ok": False, "error": "window-count must be 1..60"}), file=sys.stderr)
        return 2
    if args.sample_count < 100 or args.sample_count > 600:
        print(json.dumps({"ok": False, "error": "sample-count must be 100..600"}), file=sys.stderr)
        return 2
    token = load_token(args)
    started = datetime.now(timezone.utc)
    field_session_id = make_field_session_id(started)
    record: dict[str, Any] = {
        "schema_version": RECORD_SCHEMA_VERSION,
        "device_id": args.device_id,
        "test_run_id": args.test_run_id,
        "field_session_id": field_session_id,
        "mode": "execute" if args.execute else "dry_run",
        "status": "running" if args.execute else "dry_run_ready",
        "started_at": started.isoformat(),
        "completed_at": None,
        "planned_window_count": args.window_count,
        "planned_sample_count_per_window": args.sample_count,
        "planned_total_samples": args.window_count * args.sample_count,
        "planned_capture_duration_s": args.window_count * args.sample_count * INTERVAL_MS / 1000,
        "completed_window_count": 0,
        "failed_window_count": 0,
        "commands_created": [],
        "training_allowed": False,
        "results": [],
        "honesty_note": (
            f"Windows are discrete {args.sample_count}-sample captures "
            f"({args.sample_count * INTERVAL_MS / 1000:.1f}s each) with real "
            "inter-window gaps. Coverage continuity must be derived from "
            "capture_start/end_uptime_us, never assumed continuous."
        ),
    }

    cmd_ids = []
    for index in range(args.window_count):
        cmd_id = f"{args.cmd_prefix}{index + 1:02d}".lower()
        if CMD_ID_RE.fullmatch(cmd_id) is None or len(cmd_id) > 16:
            print(json.dumps({"ok": False, "error": f"invalid cmd_id {cmd_id}"}), file=sys.stderr)
            return 2
        cmd_ids.append(cmd_id)

    if not args.execute:
        record["results"] = [
            {"cmd_id": cmd_id, "state": "planned", "training_allowed": False}
            for cmd_id in cmd_ids
        ]
        record["completed_at"] = utc_now()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if args.json:
            print(json.dumps(record, ensure_ascii=False, sort_keys=True))
        return 0

    hub_url = validate_hub_url(args.hub)
    client = HubClient(hub_url, token=token, timeout=30.0)
    record["hub_url"] = hub_url
    redaction = (token,) if token else ()

    def fail_record(message: str) -> int:
        record.update({"status": "failed", "completed_at": utc_now(), "error": _redact(message, redaction)})
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if args.json:
            print(json.dumps(record, ensure_ascii=False, sort_keys=True))
        return 2

    # Create the test run exactly once.
    try:
        response = client.post(
            "/api/v1/test-runs",
            {
                "test_run_id": args.test_run_id,
                "task_id": args.task_id,
                "device_id": args.device_id,
                "status": "active",
                "goal": f"FT-001B bounded {args.window_count}-window IMU burst over LTE",
            },
        )
        test_run = _object(response, "test-run creation response").get("test_run")
        if not isinstance(test_run, dict) or test_run.get("test_run_id") != args.test_run_id:
            raise CaptureSessionError("Message Hub did not create the requested test run")
    except Exception as error:  # noqa: BLE001
        return fail_record(f"test run creation failed: {error}")

    for index, cmd_id in enumerate(cmd_ids):
        result: dict[str, Any] = {
            "cmd_id": cmd_id,
            "window_index": index,
            "state": "creating",
            "created_at": utc_now(),
            "completed_at": None,
            "training_allowed": False,
        }
        record["results"].append(result)
        try:
            response = client.post(
                f"/api/v1/devices/{args.device_id}/commands",
                {
                    "cmd": "capture_imu_window",
                    "cmd_id": cmd_id,
                    "test_run_id": args.test_run_id,
                    "payload": {"sample_count": args.sample_count, "interval_ms": INTERVAL_MS},
                },
            )
            created = _object(response, "command creation response").get("command")
            if not isinstance(created, dict) or created.get("cmd_id") != cmd_id or created.get("status") != "pending":
                raise CaptureSessionError(f"Message Hub did not create pending command {cmd_id}")
            record["commands_created"].append(cmd_id)
            deadline = time.monotonic() + args.timeout_sec
            ack = _wait_for_ack(
                client,
                device_id=args.device_id,
                cmd_id=cmd_id,
                test_run_id=args.test_run_id,
                transport_type="lte",
                deadline=deadline,
                monotonic_fn=time.monotonic,
                sleep_fn=time.sleep,
                poll_interval_sec=args.poll_interval_sec,
            )
            evidence = _wait_for_window(
                client,
                device_id=args.device_id,
                cmd_id=cmd_id,
                test_run_id=args.test_run_id,
                transport_type="lte",
                deadline=deadline,
                monotonic_fn=time.monotonic,
                sleep_fn=time.sleep,
                poll_interval_sec=args.poll_interval_sec,
            )
            result.update(
                {
                    "state": "ok",
                    "completed_at": utc_now(),
                    "window_id": evidence["window_id"],
                    "cadence": evidence["cadence"],
                    "cadence_quality_status": evidence["cadence_quality_status"],
                    "samples_crc32": evidence["samples_crc32"],
                    "ack": {"status": "ok", "transport_type": "lte", "test_run_id": args.test_run_id},
                }
            )
            record["completed_window_count"] += 1
        except Exception as error:  # noqa: BLE001
            result.update({"state": "failed", "completed_at": utc_now(), "error": _redact(str(error), redaction)})
            record["failed_window_count"] += 1
            # A failed discrete window does not invalidate later independent windows;
            # the failure is preserved honestly and the burst continues.
        if index < len(cmd_ids) - 1 and args.inter_window_delay_sec > 0:
            time.sleep(args.inter_window_delay_sec)

    record["status"] = "completed" if record["completed_window_count"] > 0 else "failed"
    record["completed_at"] = utc_now()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(record, ensure_ascii=False, sort_keys=True))
    return 0 if record["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
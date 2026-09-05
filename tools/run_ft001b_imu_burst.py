"""Bounded discrete IMU-window preflight runner for FT-001B.

Sequentially issues N bounded `capture_imu_window` commands (each
100 samples x 50 ms) over the existing
Message Hub command queue and waits for each window's LTE ACK and
raw-frame evidence before continuing.

Windows are discrete captures; gaps between them are NOT hidden.  The
honest inter-window coverage is derived from each window's
`capture_start_uptime_us`/`capture_end_uptime_us` in the VPS export.
This tool can provide real IMU observations for an asynchronous Session, but
its output is never evidence of continuous IMU coverage.

The runner creates exactly one test run and only `capture_imu_window`
commands.  It never flashes firmware, opens serial, or changes configuration.

Default mode is dry-run; pass --execute to send commands.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import secrets
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

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
EXPECTED_MESSAGE_HUB_HOST = "ego.example.invalid"
CMD_ID_RE = re.compile(r"^[a-z0-9]{1,16}$")
CMD_PREFIX_RE = re.compile(r"^[a-z0-9]{1,4}$")
TEST_RUN_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,32}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_field_session_id(now: datetime) -> str:
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    return f"FS-{stamp}-{secrets.token_hex(6)}"


def _base36(value: int) -> str:
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    encoded = ""
    while value:
        value, remainder = divmod(value, 36)
        encoded = alphabet[remainder] + encoded
    return encoded or "0"


def make_command_ids(
    *,
    cmd_prefix: str,
    test_run_id: str,
    field_session_id: str,
    window_count: int,
) -> tuple[str, list[str]]:
    prefix = cmd_prefix.lower()
    if CMD_PREFIX_RE.fullmatch(prefix) is None:
        raise ValueError("cmd-prefix must be 1..4 lowercase alphanumeric characters")
    digest = hashlib.sha256(f"{test_run_id}\0{field_session_id}".encode("utf-8")).digest()
    namespace = _base36(int.from_bytes(digest[:6], "big")).rjust(10, "0")
    cmd_ids = [f"{prefix}{namespace}{index + 1:02d}" for index in range(window_count)]
    if any(CMD_ID_RE.fullmatch(cmd_id) is None for cmd_id in cmd_ids):
        raise ValueError("generated command ID is outside the 16-character contract")
    return namespace, cmd_ids


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device-id", default="ego-link-r1-connectivity-001")
    parser.add_argument("--test-run-id", required=True)
    parser.add_argument("--task-id", default="FT-001B")
    parser.add_argument(
        "--cmd-prefix",
        default="ftb",
        help="1..4 lowercase alphanumeric characters; a unique session namespace is appended",
    )
    parser.add_argument("--window-count", type=int, default=10)
    parser.add_argument("--sample-count", type=int, default=SAMPLE_COUNT,
                        help="IMU samples per bounded window (frozen contract: exactly 100)")
    parser.add_argument("--hub", default="https://ego.example.invalid")
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


def validate_production_hub_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "https":
        raise CaptureSessionError("FT-001B execute mode requires HTTPS Message Hub ingress")
    if parsed.hostname != EXPECTED_MESSAGE_HUB_HOST or parsed.port not in (None, 443):
        raise CaptureSessionError("FT-001B Message Hub host/port does not match the approved TLS endpoint")
    if parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment:
        raise CaptureSessionError("FT-001B Message Hub URL must not contain credentials, query, or fragment")
    if parsed.path not in ("", "/"):
        raise CaptureSessionError("FT-001B Message Hub URL must contain only the approved TLS origin")
    return validate_hub_url(value)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.window_count < 1 or args.window_count > 60:
        print(json.dumps({"ok": False, "error": "window-count must be 1..60"}), file=sys.stderr)
        return 2
    if args.sample_count != SAMPLE_COUNT:
        print(json.dumps({"ok": False, "error": "sample-count must be exactly 100"}), file=sys.stderr)
        return 2
    if TEST_RUN_ID_RE.fullmatch(args.test_run_id) is None:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "test-run-id must be 1..32 safe characters [A-Za-z0-9._:-]",
                }
            ),
            file=sys.stderr,
        )
        return 2
    if CMD_PREFIX_RE.fullmatch(args.cmd_prefix.lower()) is None:
        print(
            json.dumps(
                {"ok": False, "error": "cmd-prefix must be 1..4 lowercase alphanumeric characters"}
            ),
            file=sys.stderr,
        )
        return 2
    if args.timeout_sec <= 0 or args.poll_interval_sec <= 0 or args.inter_window_delay_sec < 0:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": (
                        "timeout-sec and poll-interval-sec must be positive; "
                        "inter-window-delay-sec must be non-negative"
                    ),
                }
            ),
            file=sys.stderr,
        )
        return 2
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
        "observed_boot_count": None,
        "boot_scope_consistent": True,
        "ft001b_minimum_imu_window_count": 3,
        "ft001b_imu_requirement_ready": False,
        "ft001b_acceptance": False,
        "ft001b_acceptance_reason": (
            "This runner covers only discrete IMU transport evidence; GNSS, Session packing, "
            "replay and field metrics remain required."
        ),
        "results": [],
        "honesty_note": (
            f"Windows are discrete {args.sample_count}-sample captures "
            f"({args.sample_count * INTERVAL_MS / 1000:.1f}s each) with real "
            "inter-window gaps. Coverage continuity must be derived from "
            "capture_start/end_uptime_us, never assumed continuous. This "
            "artifact is preflight/observation evidence, not continuous IMU acceptance."
        ),
    }

    try:
        command_namespace, cmd_ids = make_command_ids(
            cmd_prefix=args.cmd_prefix,
            test_run_id=args.test_run_id,
            field_session_id=field_session_id,
            window_count=args.window_count,
        )
    except ValueError as error:
        print(json.dumps({"ok": False, "error": str(error)}), file=sys.stderr)
        return 2
    record["command_id_namespace"] = command_namespace

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

    try:
        hub_url = validate_production_hub_url(args.hub)
    except CaptureSessionError as error:
        print(json.dumps({"ok": False, "error": str(error)}), file=sys.stderr)
        return 2
    token = load_token(args)
    record["hub_url"] = hub_url
    redaction = (token,) if token else ()

    def fail_record(message: str) -> int:
        record.update({"status": "failed", "completed_at": utc_now(), "error": _redact(message, redaction)})
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if args.json:
            print(json.dumps(record, ensure_ascii=False, sort_keys=True))
        return 2

    if not token:
        return fail_record("authenticated HTTPS execution requires a bearer token")
    client = HubClient(hub_url, token=token, timeout=30.0)

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
                    "boot_count": evidence["boot_count"],
                    "capture_start_uptime_us": evidence["capture_start_uptime_us"],
                    "capture_end_uptime_us": evidence["capture_end_uptime_us"],
                    "capture_span_us": evidence.get(
                        "capture_span_us",
                        evidence["capture_end_uptime_us"] - evidence["capture_start_uptime_us"],
                    ),
                    "ack": {"status": "ok", "transport_type": "lte", "test_run_id": args.test_run_id},
                }
            )
            if record["observed_boot_count"] is None:
                record["observed_boot_count"] = evidence["boot_count"]
            elif record["observed_boot_count"] != evidence["boot_count"]:
                record["boot_scope_consistent"] = False
                raise CaptureSessionError(
                    "IMU burst crossed device boots; FT-001B requires one boot scope"
                )
            record["completed_window_count"] += 1
        except Exception as error:  # noqa: BLE001
            result.update({"state": "failed", "completed_at": utc_now(), "error": _redact(str(error), redaction)})
            record["failed_window_count"] += 1
            # A failed discrete window does not invalidate later independent windows;
            # the failure is preserved honestly and the burst continues.
        if index < len(cmd_ids) - 1 and args.inter_window_delay_sec > 0:
            time.sleep(args.inter_window_delay_sec)

    if record["completed_window_count"] == record["planned_window_count"]:
        record["status"] = "burst_transport_completed"
    elif record["completed_window_count"] > 0:
        record["status"] = "partial"
    else:
        record["status"] = "failed"
    record["completion_ratio"] = (
        record["completed_window_count"] / record["planned_window_count"]
    )
    record["ft001b_imu_requirement_ready"] = (
        record["completed_window_count"] >= record["ft001b_minimum_imu_window_count"]
        and record["observed_boot_count"] is not None
        and record["boot_scope_consistent"]
    )
    record["completed_at"] = utc_now()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(record, ensure_ascii=False, sort_keys=True))
    return 0 if record["status"] == "burst_transport_completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())

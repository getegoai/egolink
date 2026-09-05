"""Plan and, only with --execute, run a bounded Wi-Fi or LTE IMU seed session.

The generated execution record contains lineage metadata only.  It never
contains the Message Hub token or raw IMU samples.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any, Callable
from urllib.parse import urlsplit


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.validate_fw001_hw_loop import HubClient


PLAN_SCHEMA_VERSION = "egolink.imu_capture_session_plan.v0.1"
EXECUTION_SCHEMA_VERSION = "egolink.imu_capture_session_execution.v0.1"
SAFE_PLANNED_ACTIVITIES = frozenset({"stationary", "walking", "transition_or_unknown"})
SPLIT_NAMES = frozenset({"train", "validation", "test", "unassigned"})
SAMPLE_COUNT = 100
INTERVAL_MS = 50
CHUNK_COUNT = 10
MAX_WINDOWS = 3
TRANSPORT_TYPES = frozenset({"wifi", "lte"})
ID_RE = re.compile(r"^[A-Za-z0-9._:-]+$")


class CaptureSessionError(RuntimeError):
    """A strict plan or bounded execution failed."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CaptureSessionError(f"{name} must be a JSON object")
    return value


def _exact_keys(value: dict[str, Any], required: set[str], optional: set[str], name: str) -> None:
    missing = required - set(value)
    extra = set(value) - required - optional
    if missing or extra:
        details = []
        if missing:
            details.append(f"missing {sorted(missing)}")
        if extra:
            details.append(f"unexpected {sorted(extra)}")
        raise CaptureSessionError(f"{name} has invalid fields: {', '.join(details)}")


def _safe_id(value: Any, name: str, maximum: int) -> str:
    if not isinstance(value, str) or not (1 <= len(value) <= maximum) or ID_RE.fullmatch(value) is None:
        raise CaptureSessionError(f"{name} must contain 1-{maximum} safe identifier characters")
    return value


def validate_plan(value: Any) -> dict[str, Any]:
    """Validate and return a plan without adding defaults or consent fields."""

    plan = _object(value, "plan")
    _exact_keys(
        plan,
        {"schema_version", "plan_id", "device_id", "test_run_id", "sample_count", "interval_ms", "sessions"},
        {"transport_type"},
        "plan",
    )
    if plan["schema_version"] != PLAN_SCHEMA_VERSION:
        raise CaptureSessionError(f"plan.schema_version must be {PLAN_SCHEMA_VERSION}")
    _safe_id(plan["plan_id"], "plan.plan_id", 48)
    _safe_id(plan["device_id"], "plan.device_id", 64)
    _safe_id(plan["test_run_id"], "plan.test_run_id", 32)
    if type(plan["sample_count"]) is not int or plan["sample_count"] != SAMPLE_COUNT:
        raise CaptureSessionError("plan.sample_count must be exactly 100")
    if type(plan["interval_ms"]) is not int or plan["interval_ms"] != INTERVAL_MS:
        raise CaptureSessionError("plan.interval_ms must be exactly 50")
    transport_type = plan.get("transport_type", "wifi")
    if not isinstance(transport_type, str) or transport_type not in TRANSPORT_TYPES:
        raise CaptureSessionError(f"plan.transport_type must be one of {sorted(TRANSPORT_TYPES)}")
    sessions = plan["sessions"]
    if not isinstance(sessions, list) or not sessions:
        raise CaptureSessionError("plan.sessions must be a non-empty array")

    session_ids: set[str] = set()
    cmd_ids: set[str] = set()
    window_total = 0
    for session_index, raw_session in enumerate(sessions):
        name = f"plan.sessions[{session_index}]"
        session = _object(raw_session, name)
        _exact_keys(session, {"session_id", "split_name", "windows"}, set(), name)
        session_id = _safe_id(session["session_id"], f"{name}.session_id", 48)
        if session_id in session_ids:
            raise CaptureSessionError(f"session_id is duplicated or crosses split groups: {session_id}")
        session_ids.add(session_id)
        if session["split_name"] not in SPLIT_NAMES:
            raise CaptureSessionError(f"{name}.split_name must be one of {sorted(SPLIT_NAMES)}")
        windows = session["windows"]
        if not isinstance(windows, list) or not windows:
            raise CaptureSessionError(f"{name}.windows must be a non-empty array")
        for window_index, raw_window in enumerate(windows):
            window_name = f"{name}.windows[{window_index}]"
            window = _object(raw_window, window_name)
            _exact_keys(window, {"cmd_id", "planned_activity"}, {"operator_instruction"}, window_name)
            cmd_id = _safe_id(window["cmd_id"], f"{window_name}.cmd_id", 16)
            if cmd_id in cmd_ids:
                raise CaptureSessionError(f"cmd_id is duplicated: {cmd_id}")
            cmd_ids.add(cmd_id)
            if window["planned_activity"] not in SAFE_PLANNED_ACTIVITIES:
                raise CaptureSessionError(
                    f"{window_name}.planned_activity is unsafe for this seed; allowed: {sorted(SAFE_PLANNED_ACTIVITIES)}"
                )
            if "operator_instruction" in window and (
                not isinstance(window["operator_instruction"], str)
                or not (1 <= len(window["operator_instruction"]) <= 240)
            ):
                raise CaptureSessionError(f"{window_name}.operator_instruction must contain 1-240 characters")
            window_total += 1
    if window_total != MAX_WINDOWS:
        raise CaptureSessionError(f"this bounded seed requires exactly {MAX_WINDOWS} windows")
    return plan


def load_plan(path: Path) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CaptureSessionError(f"cannot read plan {path.name}: {error}") from error
    return validate_plan(value), sha256_bytes(raw)


def iter_planned_windows(plan: dict[str, Any]):
    for session in plan["sessions"]:
        for window in session["windows"]:
            yield session, window


def plan_transport_type(plan: dict[str, Any]) -> str:
    return str(plan.get("transport_type", "wifi"))


def validate_hub_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise CaptureSessionError("hub URL must be an http(s) origin without credentials, query, or fragment")
    return value.rstrip("/")


def _redact(text: str, values: tuple[str, ...]) -> str:
    result = text
    for secret in values:
        if secret:
            result = result.replace(secret, "[REDACTED]")
    return result


def _find_command(commands: Any, cmd_id: str) -> dict[str, Any] | None:
    if not isinstance(commands, list):
        raise CaptureSessionError("Message Hub commands response must contain an array")
    for command in commands:
        if isinstance(command, dict) and command.get("cmd_id") == cmd_id:
            return command
    return None


def _validate_ok_ack(
    command: dict[str, Any], *, cmd_id: str, test_run_id: str, transport_type: str
) -> dict[str, Any]:
    status = command.get("status")
    if status != "ok":
        raise CaptureSessionError(f"command {cmd_id} ended with non-ok status: {status}")
    ack = command.get("ack")
    if not isinstance(ack, dict):
        raise CaptureSessionError(f"command {cmd_id} has no structured ACK")
    if ack.get("status") != "ok" or ack.get("cmd_id") not in {None, cmd_id}:
        raise CaptureSessionError(f"command {cmd_id} ACK is not ok or has mismatched lineage")
    if ack.get("test_run_id") != test_run_id:
        raise CaptureSessionError(f"command {cmd_id} ACK test_run_id mismatch")
    transport = ack.get("transport")
    if not isinstance(transport, dict) or transport.get("type") != transport_type:
        raise CaptureSessionError(f"command {cmd_id} ACK transport must be {transport_type}")
    observation = ack.get("command")
    if not isinstance(observation, dict) or observation.get("duplicate_local_execution_prevented") is not False:
        raise CaptureSessionError(f"command {cmd_id} duplicate/execution marker is not explicitly false")
    return ack


def _part_metadata(frame: Any) -> tuple[str, dict[str, Any], str] | None:
    if not isinstance(frame, dict):
        return None
    parse_result = frame.get("parse_result")
    if not isinstance(parse_result, dict) or parse_result.get("status") != "ok":
        return None
    message = parse_result.get("derived_message")
    if not isinstance(message, dict) or message.get("event_type") not in {"imu_window_chunk", "imu_window_manifest"}:
        return None
    imu = message.get("imu_window")
    if not isinstance(imu, dict):
        raise CaptureSessionError("accepted IMU raw frame is missing normalized metadata")
    return str(message["event_type"]), imu, str(frame.get("frame_id") or "")


def _window_evidence(
    raw_frames: Any, *, cmd_id: str, test_run_id: str, transport_type: str
) -> dict[str, Any] | None:
    if not isinstance(raw_frames, list):
        raise CaptureSessionError("Message Hub raw-frames response must contain an array")
    parts: list[tuple[str, dict[str, Any], str]] = []
    for frame in raw_frames:
        parsed = _part_metadata(frame)
        if parsed is not None and parsed[1].get("capture_cmd_id") == cmd_id:
            parts.append(parsed)
    if not parts:
        return None

    window_ids = {metadata.get("window_id") for _, metadata, _ in parts}
    if len(window_ids) != 1 or not next(iter(window_ids)):
        raise CaptureSessionError(f"command {cmd_id} has conflicting window IDs")
    window_id = str(next(iter(window_ids)))
    boot_count_values = [metadata.get("boot_count") for _, metadata, _ in parts]
    if any(type(value) is not int or value < 1 for value in boot_count_values):
        raise CaptureSessionError(f"command {cmd_id} has conflicting or invalid boot_count lineage")
    boot_counts = set(boot_count_values)
    if len(boot_counts) != 1:
        raise CaptureSessionError(f"command {cmd_id} has conflicting or invalid boot_count lineage")
    boot_count = next(iter(boot_counts))
    chunks: dict[int, tuple[dict[str, Any], str]] = {}
    manifests: list[tuple[dict[str, Any], str]] = []
    for event_type, metadata, frame_id in parts:
        common_ok = (
            metadata.get("contract_version") == "egolink.imu_window.v1"
            and metadata.get("window_id") == window_id
            and metadata.get("capture_cmd_id") == cmd_id
            and metadata.get("test_run_id") == test_run_id
            and metadata.get("transport_type") == transport_type
            and metadata.get("source") == "qmi8658_i2c"
            and metadata.get("source_status") == "observed"
            and metadata.get("training_allowed") is False
        )
        if not common_ok:
            raise CaptureSessionError(f"command {cmd_id} has invalid IMU source/transport/privacy lineage")
        if event_type == "imu_window_chunk":
            index = metadata.get("chunk_index")
            if type(index) is not int or not (0 <= index < CHUNK_COUNT) or index in chunks:
                raise CaptureSessionError(f"command {cmd_id} has duplicate or invalid chunk index")
            chunks[index] = (metadata, frame_id)
        else:
            manifests.append((metadata, frame_id))
    if len(manifests) > 1:
        raise CaptureSessionError(f"command {cmd_id} has duplicate manifests")
    if set(chunks) != set(range(CHUNK_COUNT)) or len(manifests) != 1:
        return None

    manifest, manifest_frame_id = manifests[0]
    fixed_ok = (
        manifest.get("sample_count") == SAMPLE_COUNT
        and manifest.get("requested_interval_us") == INTERVAL_MS * 1000
        and manifest.get("chunk_count") == CHUNK_COUNT
        and manifest.get("uploaded_chunk_count") == CHUNK_COUNT
        and manifest.get("read_failure_count") == 0
        and manifest.get("mock_sample_count") == 0
    )
    cadence_ok = (
        type(manifest.get("min_interval_us")) is int
        and 40_000 <= manifest["min_interval_us"]
        and type(manifest.get("mean_interval_us")) is int
        and 45_000 <= manifest["mean_interval_us"] <= 55_000
        and type(manifest.get("max_interval_us")) is int
        and manifest["max_interval_us"] <= 60_000
        and type(manifest.get("deadline_miss_count")) is int
        and manifest["deadline_miss_count"] <= 5
    )
    samples_crc32 = manifest.get("samples_crc32")
    capture_start_uptime_us = manifest.get("capture_start_uptime_us")
    capture_end_uptime_us = manifest.get("capture_end_uptime_us")
    capture_span_us = (
        capture_end_uptime_us - capture_start_uptime_us
        if isinstance(capture_start_uptime_us, int)
        and not isinstance(capture_start_uptime_us, bool)
        and isinstance(capture_end_uptime_us, int)
        and not isinstance(capture_end_uptime_us, bool)
        else None
    )
    interval_count = SAMPLE_COUNT - 1
    capture_bounds_ok = (
        not isinstance(capture_start_uptime_us, bool)
        and isinstance(capture_start_uptime_us, int)
        and capture_start_uptime_us >= 0
        and not isinstance(capture_end_uptime_us, bool)
        and isinstance(capture_end_uptime_us, int)
        and capture_end_uptime_us > capture_start_uptime_us
        and capture_span_us is not None
        and cadence_ok
        and capture_span_us >= manifest["min_interval_us"] * interval_count
        and capture_span_us <= manifest["max_interval_us"] * interval_count + 250_000
        and abs(capture_span_us - manifest["mean_interval_us"] * interval_count) <= 250_000
    )
    if (
        not fixed_ok
        or not cadence_ok
        or not capture_bounds_ok
        or not isinstance(samples_crc32, str)
        or re.fullmatch(r"[0-9A-F]{8}", samples_crc32) is None
    ):
        raise CaptureSessionError(f"command {cmd_id} manifest failed fixed capture/cadence quality checks")
    return {
        "window_id": window_id,
        "boot_count": boot_count,
        "capture_start_uptime_us": capture_start_uptime_us,
        "capture_end_uptime_us": capture_end_uptime_us,
        "capture_span_us": capture_span_us,
        "samples_crc32": samples_crc32,
        "chunk_count": CHUNK_COUNT,
        "chunk_frame_ids": [chunks[index][1] for index in range(CHUNK_COUNT)],
        "manifest_frame_id": manifest_frame_id,
        "cadence_quality_status": "qualified",
        "cadence": {
            "min_interval_us": manifest["min_interval_us"],
            "mean_interval_us": manifest["mean_interval_us"],
            "max_interval_us": manifest["max_interval_us"],
            "deadline_miss_count": manifest["deadline_miss_count"],
        },
        "source": "qmi8658_i2c",
        "source_status": "observed",
        "transport_type": transport_type,
        "training_allowed": False,
    }


def _wait_for_ack(
    client: Any,
    *,
    device_id: str,
    cmd_id: str,
    test_run_id: str,
    transport_type: str,
    deadline: float,
    monotonic_fn: Callable[[], float],
    sleep_fn: Callable[[float], None],
    poll_interval_sec: float,
) -> dict[str, Any]:
    while True:
        response = client.get(f"/api/v1/devices/{device_id}/commands")
        command = _find_command(_object(response, "commands response").get("commands"), cmd_id)
        if command is not None:
            status = command.get("status")
            if status == "ok":
                return _validate_ok_ack(
                    command,
                    cmd_id=cmd_id,
                    test_run_id=test_run_id,
                    transport_type=transport_type,
                )
            if status not in {None, "", "pending", "in_progress"}:
                raise CaptureSessionError(f"command {cmd_id} ended with non-ok status: {status}")
        if monotonic_fn() >= deadline:
            raise CaptureSessionError(f"timed out waiting for ACK for command {cmd_id}")
        sleep_fn(poll_interval_sec)


def _wait_for_window(
    client: Any,
    *,
    device_id: str,
    cmd_id: str,
    test_run_id: str,
    transport_type: str,
    deadline: float,
    monotonic_fn: Callable[[], float],
    sleep_fn: Callable[[float], None],
    poll_interval_sec: float,
) -> dict[str, Any]:
    while True:
        response = client.get(f"/api/v1/devices/{device_id}/raw-frames")
        evidence = _window_evidence(
            _object(response, "raw-frames response").get("raw_frames"),
            cmd_id=cmd_id,
            test_run_id=test_run_id,
            transport_type=transport_type,
        )
        if evidence is not None:
            return evidence
        if monotonic_fn() >= deadline:
            raise CaptureSessionError(f"timed out waiting for complete IMU window for command {cmd_id}")
        sleep_fn(poll_interval_sec)


def run_session(
    plan: dict[str, Any],
    *,
    plan_sha256: str,
    execute: bool = False,
    client: Any | None = None,
    hub_url: str | None = None,
    timeout_sec: float = 120.0,
    poll_interval_sec: float = 2.0,
    now_fn: Callable[[], str] = utc_now,
    monotonic_fn: Callable[[], float] = time.monotonic,
    sleep_fn: Callable[[float], None] = time.sleep,
    redaction_values: tuple[str, ...] = (),
) -> dict[str, Any]:
    plan = validate_plan(plan)
    if timeout_sec <= 0 or poll_interval_sec <= 0:
        raise CaptureSessionError("timeout and poll interval must be positive")
    flattened = list(iter_planned_windows(plan))
    transport_type = plan_transport_type(plan)
    record: dict[str, Any] = {
        "schema_version": EXECUTION_SCHEMA_VERSION,
        "plan_id": plan["plan_id"],
        "plan_sha256": plan_sha256,
        "device_id": plan["device_id"],
        "test_run_id": plan["test_run_id"],
        "transport_type": transport_type,
        "mode": "execute" if execute else "dry_run",
        "status": "running" if execute else "dry_run_ready",
        "started_at": now_fn(),
        "completed_at": None,
        "hub_url": hub_url if execute else None,
        "planned_window_count": len(flattened),
        "completed_window_count": 0,
        "test_run_created": False,
        "commands_created": [],
        "external_actions": [],
        "training_allowed": False,
        "results": [],
    }
    if not execute:
        record["results"] = [
            {
                "session_id": session["session_id"],
                "split_name": session["split_name"],
                "cmd_id": window["cmd_id"],
                "planned_activity": window["planned_activity"],
                "transport_type": transport_type,
                "state": "planned",
                "training_allowed": False,
            }
            for session, window in flattened
        ]
        record["completed_at"] = now_fn()
        return record
    if client is None:
        raise CaptureSessionError("execute mode requires a Message Hub client")

    test_run_action = {"action": "create_test_run", "test_run_id": plan["test_run_id"], "state": "attempted"}
    record["external_actions"].append(test_run_action)
    try:
        task_id = "FIELD-011" if transport_type == "lte" else "D5-002"
        goal = (
            "bounded three-window LTE QMI8658 pipeline seed"
            if transport_type == "lte"
            else "bounded three-window Wi-Fi QMI8658 pipeline seed"
        )
        response = client.post(
            "/api/v1/test-runs",
            {
                "test_run_id": plan["test_run_id"],
                "task_id": task_id,
                "device_id": plan["device_id"],
                "status": "active",
                "goal": goal,
            },
        )
        test_run = _object(response, "test-run creation response").get("test_run")
        if not isinstance(test_run, dict) or test_run.get("test_run_id") != plan["test_run_id"]:
            raise CaptureSessionError("Message Hub did not create the requested test run")
        test_run_action["state"] = "ok"
        record["test_run_created"] = True
    except Exception as error:
        test_run_action.update({"state": "failed", "error": _redact(str(error), redaction_values)})
        record.update({"status": "failed", "completed_at": now_fn()})
        return record

    for session, window in flattened:
        cmd_id = window["cmd_id"]
        result: dict[str, Any] = {
            "session_id": session["session_id"],
            "split_name": session["split_name"],
            "cmd_id": cmd_id,
            "planned_activity": window["planned_activity"],
            "transport_type": transport_type,
            "state": "creating",
            "created_at": now_fn(),
            "completed_at": None,
            "training_allowed": False,
        }
        record["results"].append(result)
        command_action = {"action": "create_command", "cmd_id": cmd_id, "state": "attempted"}
        record["external_actions"].append(command_action)
        try:
            response = client.post(
                f"/api/v1/devices/{plan['device_id']}/commands",
                {
                    "cmd": "capture_imu_window",
                    "cmd_id": cmd_id,
                    "test_run_id": plan["test_run_id"],
                    "payload": {"sample_count": SAMPLE_COUNT, "interval_ms": INTERVAL_MS},
                },
            )
            created = _object(response, "command creation response").get("command")
            if not isinstance(created, dict) or created.get("cmd_id") != cmd_id or created.get("status") != "pending":
                raise CaptureSessionError(f"Message Hub did not create pending command {cmd_id}")
            record["commands_created"].append(cmd_id)
            command_action["state"] = "ok"
            deadline = monotonic_fn() + timeout_sec
            ack = _wait_for_ack(
                client,
                device_id=plan["device_id"],
                cmd_id=cmd_id,
                test_run_id=plan["test_run_id"],
                transport_type=transport_type,
                deadline=deadline,
                monotonic_fn=monotonic_fn,
                sleep_fn=sleep_fn,
                poll_interval_sec=poll_interval_sec,
            )
            evidence = _wait_for_window(
                client,
                device_id=plan["device_id"],
                cmd_id=cmd_id,
                test_run_id=plan["test_run_id"],
                transport_type=transport_type,
                deadline=deadline,
                monotonic_fn=monotonic_fn,
                sleep_fn=sleep_fn,
                poll_interval_sec=poll_interval_sec,
            )
            result.update(
                {
                    "state": "ok",
                    "completed_at": now_fn(),
                    "ack": {
                        "status": "ok",
                        "test_run_id": ack["test_run_id"],
                        "transport_type": transport_type,
                        "duplicate_local_execution_prevented": False,
                    },
                    "window": evidence,
                }
            )
            record["completed_window_count"] += 1
        except Exception as error:
            if command_action["state"] == "attempted":
                command_action.update({"state": "failed", "error": _redact(str(error), redaction_values)})
            result.update({"state": "failed", "completed_at": now_fn(), "error": _redact(str(error), redaction_values)})
            record.update({"status": "failed", "completed_at": now_fn()})
            return record
    record.update({"status": "completed", "completed_at": now_fn()})
    return record


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--execute", action="store_true", help="Actually create commands; omitted means dry-run")
    parser.add_argument("--hub", default="http://127.0.0.1:8790")
    parser.add_argument("--token-env", default="EGOLINK_MESSAGE_HUB_TOKEN")
    parser.add_argument("--timeout-sec", type=float, default=120.0)
    parser.add_argument("--poll-interval-sec", type=float, default=2.0)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    token: str | None = None
    try:
        plan, plan_sha256 = load_plan(args.plan)
        client = None
        hub_url = None
        if args.execute:
            hub_url = validate_hub_url(args.hub)
            token = os.environ.get(args.token_env) or None
            client = HubClient(hub_url, token=token)
        record = run_session(
            plan,
            plan_sha256=plan_sha256,
            execute=args.execute,
            client=client,
            hub_url=hub_url,
            timeout_sec=args.timeout_sec,
            poll_interval_sec=args.poll_interval_sec,
            redaction_values=(token,) if token else (),
        )
    except Exception as error:
        print(json.dumps({"ok": False, "error": _redact(str(error), (token,) if token else ())}, ensure_ascii=False), file=sys.stderr)
        return 2
    _write_json(args.output, record)
    if args.json:
        print(json.dumps(record, ensure_ascii=False, sort_keys=True))
    return 0 if record["status"] in {"dry_run_ready", "completed"} else 2


if __name__ == "__main__":
    raise SystemExit(main())

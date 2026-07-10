"""Demo-first safety loop for Ego Link P0.

This module intentionally keeps the loop thin: it demonstrates the product
experience before all hardware paths are production-ready.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any, Callable, Iterable

from pc_simulator import board_bridge, event_store, protocol, session_inspector, session_recorder


DEMO_VERSION = "egolink.demo.safety_loop.v0.1"
DEMO_PROTOCOL_VERSION = "0.2"
PC_BRIDGE_ID = "pc-bridge"
WEARABLE_ID = "wearable-node-001"
CONNECTIVITY_ID = "connectivity-node-001"
VALID_RESPONSES = {"safe", "help", "no_response"}


@dataclass
class DemoPaths:
    event_log: Path
    recording_dir: Path
    quality_report_json: Path
    quality_report_markdown: Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DemoClock:
    def __init__(self, start: str | None = None) -> None:
        parsed = datetime.fromisoformat((start or "2026-06-24T00:00:00+00:00").replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        self._current = parsed

    def __call__(self) -> str:
        value = self._current
        self._current = self._current + timedelta(seconds=1)
        return value.isoformat()


def load_jsonl(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if isinstance(value, dict):
            rows.append(value)
    return rows


def normalize_source_messages(messages: Iterable[dict[str, Any]], *, now: Callable[[], str]) -> list[dict[str, Any]]:
    state = board_bridge.BridgeState()
    events: list[dict[str, Any]] = []
    for message in messages:
        try:
            event = board_bridge.normalize_message(
                message,
                received_at=now(),
                bridge_source="minimal_demo_source",
                state=state,
            )
        except board_bridge.BoardBridgeError:
            continue
        events.append(event)
    return events


def default_hello_events(*, now: Callable[[], str]) -> list[dict[str, Any]]:
    state = board_bridge.BridgeState()
    return [
        board_bridge.normalize_hello(
            {"type": "hello", "device_id": WEARABLE_ID, "role": "wearable_node", "protocol_version": DEMO_PROTOCOL_VERSION},
            received_at=now(),
            bridge_source="minimal_demo_default",
            state=state,
        ),
        board_bridge.normalize_hello(
            {
                "type": "hello",
                "device_id": CONNECTIVITY_ID,
                "role": "connectivity_node",
                "protocol_version": DEMO_PROTOCOL_VERSION,
            },
            received_at=now(),
            bridge_source="minimal_demo_default",
            state=state,
        ),
    ]


def event_seq(events: Iterable[dict[str, Any]]) -> int:
    values = [int(event["seq"]) for event in events if isinstance(event.get("seq"), int)]
    return max(values, default=0) + 1


def has_role(events: Iterable[dict[str, Any]], role: str) -> bool:
    return any(event.get("event_type") == "board_hello" and event.get("role") == role for event in events)


def source_event_key(event: dict[str, Any]) -> str:
    device_id = str(event.get("device_id") or event.get("source") or protocol.DEVICE_ID)
    event_type = str(event.get("event_type") or event.get("type") or "unknown")
    seq = event.get("seq")
    ts = str(event.get("received_at") or event.get("ts") or event.get("timestamp_ms") or "")
    return f"{device_id}:{event_type}:{seq}:{ts}" if seq not in (None, "") else f"{device_id}:{event_type}:{ts}"


def choose_motion_seed(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    motions = [event for event in events if event.get("event_type") in {"motion_event", "imu_motion"}]
    if motions:
        return motions[-1]
    samples = [event for event in events if event.get("event_type") == "imu_sample"]
    if samples:
        return max(samples, key=sample_energy)
    return None


def sample_energy(event: dict[str, Any]) -> float:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    accel = payload.get("accel_mg")
    gyro = payload.get("gyro_mdps")
    accel_peak = max((abs(float(value)) for value in accel), default=0.0) if isinstance(accel, list) else 0.0
    gyro_peak = max((abs(float(value)) for value in gyro), default=0.0) if isinstance(gyro, list) else 0.0
    return accel_peak + (gyro_peak / 100.0)


def build_motion_event(
    seed: dict[str, Any] | None,
    *,
    seq: int,
    session_id: str,
    now: Callable[[], str],
) -> dict[str, Any]:
    if seed is not None and seed.get("event_type") == "motion_event":
        event = dict(seed)
        payload = dict(event.get("payload") if isinstance(event.get("payload"), dict) else {})
        event.update(
            {
                "protocol_version": protocol.PROTOCOL_VERSION,
                "demo_protocol_version": DEMO_PROTOCOL_VERSION,
                "demo_version": DEMO_VERSION,
                "event_type": "motion_event",
                "message_type": "event",
                "priority": "high",
                "role": event.get("role") or "wearable_node",
                "session_id": session_id,
                "source_event_key": source_event_key(seed),
                "received_at": event.get("received_at") or now(),
            }
        )
        event["payload"] = payload
        return event

    payload: dict[str, Any] = {
        "impact_score": 0.92,
        "fall_score": 0.78,
        "stationary_seconds": 12,
        "demo_synthetic": seed is None,
    }
    if seed is not None:
        seed_payload = seed.get("payload") if isinstance(seed.get("payload"), dict) else {}
        payload.update(
            {
                "source_sample_event_key": source_event_key(seed),
                "accel_mg": seed_payload.get("accel_mg"),
                "gyro_mdps": seed_payload.get("gyro_mdps"),
                "demo_synthetic": True,
            }
        )

    return {
        "protocol_version": protocol.PROTOCOL_VERSION,
        "demo_protocol_version": DEMO_PROTOCOL_VERSION,
        "demo_version": DEMO_VERSION,
        "message_type": "event",
        "event_type": "motion_event",
        "priority": "high",
        "direction": "uplink",
        "device_id": str((seed or {}).get("device_id") or WEARABLE_ID),
        "role": "wearable_node",
        "seq": seq,
        "ts": now(),
        "received_at": now(),
        "session_id": session_id,
        "bridge_source": "minimal_demo",
        "sensor_model": "QMI8658",
        "imu_source": "qmi8658_i2c" if seed is not None else "demo_synthetic",
        "source_availability": "bridge_uplink",
        "source_status": "unverified",
        "sample_hz": 20,
        "payload": payload,
    }


def build_command(
    *,
    seq: int,
    session_id: str,
    target_device_id: str,
    target_role: str,
    command: str,
    command_payload: dict[str, Any],
    source_event: dict[str, Any],
    now: Callable[[], str],
) -> dict[str, Any]:
    command_id = f"demo-cmd-{seq:06d}"
    return {
        "protocol_version": protocol.PROTOCOL_VERSION,
        "demo_protocol_version": DEMO_PROTOCOL_VERSION,
        "demo_version": DEMO_VERSION,
        "message_type": "command",
        "event_type": "command_sent",
        "priority": "normal",
        "direction": "downlink",
        "device_id": PC_BRIDGE_ID,
        "target_device_id": target_device_id,
        "target_role": target_role,
        "seq": seq,
        "ts": now(),
        "received_at": now(),
        "session_id": session_id,
        "cmd_id": command_id,
        "cmd": command,
        "command_payload": command_payload,
        "source": "minimal_safety_demo",
        "source_event_key": source_event_key(source_event),
        "source_event_type": str(source_event.get("event_type") or "unknown"),
    }


def build_user_confirmation(
    *,
    seq: int,
    session_id: str,
    response: str,
    source_event: dict[str, Any],
    now: Callable[[], str],
) -> dict[str, Any]:
    return {
        "protocol_version": protocol.PROTOCOL_VERSION,
        "demo_protocol_version": DEMO_PROTOCOL_VERSION,
        "demo_version": DEMO_VERSION,
        "message_type": "event",
        "event_type": "user_confirmation",
        "priority": "high" if response == "help" else "normal",
        "direction": "uplink",
        "device_id": WEARABLE_ID,
        "role": "wearable_node",
        "seq": seq,
        "ts": now(),
        "received_at": now(),
        "session_id": session_id,
        "response": response,
        "source": "demo_cli",
        "source_event_key": source_event_key(source_event),
        "source_event_type": str(source_event.get("event_type") or "command_sent"),
    }


def build_command_ack(
    *,
    seq: int,
    session_id: str,
    command_event: dict[str, Any],
    now: Callable[[], str],
) -> dict[str, Any]:
    return {
        "protocol_version": protocol.PROTOCOL_VERSION,
        "demo_protocol_version": DEMO_PROTOCOL_VERSION,
        "demo_version": DEMO_VERSION,
        "message_type": "ack",
        "event_type": "command_ack",
        "priority": "normal",
        "direction": "uplink",
        "device_id": str(command_event.get("target_device_id") or CONNECTIVITY_ID),
        "role": str(command_event.get("target_role") or "connectivity_node"),
        "seq": seq,
        "ts": now(),
        "received_at": now(),
        "session_id": session_id,
        "cmd_id": command_event.get("cmd_id"),
        "cmd": command_event.get("cmd"),
        "ack_status": "mock_ok",
        "source": "minimal_safety_demo",
        "source_event_key": source_event_key(command_event),
        "source_event_type": "command_sent",
    }


def build_mock_location(
    *,
    seq: int,
    session_id: str,
    source_event: dict[str, Any],
    now: Callable[[], str],
) -> dict[str, Any]:
    return {
        "protocol_version": protocol.PROTOCOL_VERSION,
        "demo_protocol_version": DEMO_PROTOCOL_VERSION,
        "demo_version": DEMO_VERSION,
        "message_type": "event",
        "event_type": "location_report",
        "priority": "normal",
        "direction": "uplink",
        "device_id": CONNECTIVITY_ID,
        "role": "connectivity_node",
        "seq": seq,
        "ts": now(),
        "received_at": now(),
        "session_id": session_id,
        "source": "sim7670g_gnss",
        "fix": False,
        "gnss_power_state": 1,
        "gnss_state": "mock_refresh_no_fix",
        "satellites": 0,
        "source_event_key": source_event_key(source_event),
        "source_event_type": str(source_event.get("event_type") or "command_ack"),
    }


def build_safety_event(
    *,
    seq: int,
    session_id: str,
    response: str,
    motion_event: dict[str, Any],
    confirmation_event: dict[str, Any],
    location_event: dict[str, Any],
    now: Callable[[], str],
) -> dict[str, Any]:
    needs_help = response in {"help", "no_response"}
    return {
        "protocol_version": protocol.PROTOCOL_VERSION,
        "demo_protocol_version": DEMO_PROTOCOL_VERSION,
        "demo_version": DEMO_VERSION,
        "message_type": "event",
        "event_type": "safety_event",
        "priority": "critical" if needs_help else "normal",
        "direction": "local_record",
        "device_id": PC_BRIDGE_ID,
        "seq": seq,
        "ts": now(),
        "received_at": now(),
        "session_id": session_id,
        "source": "minimal_safety_demo",
        "risk_type": "fall_or_impact_candidate",
        "risk_score": 0.92,
        "confidence": 0.7,
        "recommended_action": "prepare_help" if needs_help else "close_as_safe",
        "response": response,
        "outcome": "needs_help" if needs_help else "confirmed_safe",
        "source_event_key": source_event_key(motion_event),
        "source_event_type": "motion_event",
        "evidence": {
            "motion_event_key": source_event_key(motion_event),
            "confirmation_event_key": source_event_key(confirmation_event),
            "location_event_key": source_event_key(location_event),
            "location_fix": location_event.get("fix"),
            "location_source": location_event.get("source"),
        },
    }


def build_demo_events(
    *,
    source_messages: Iterable[dict[str, Any]] = (),
    session_id: str,
    user_response: str,
    now: Callable[[], str] | None = None,
) -> list[dict[str, Any]]:
    if user_response not in VALID_RESPONSES:
        raise ValueError("user_response must be one of: " + ", ".join(sorted(VALID_RESPONSES)))

    clock = now or utc_now
    source_events = normalize_source_messages(source_messages, now=clock)
    events: list[dict[str, Any]] = []
    events.extend(event for event in source_events if event.get("event_type") == "board_hello")
    if not has_role(events, "wearable_node") or not has_role(events, "connectivity_node"):
        defaults = default_hello_events(now=clock)
        if not has_role(events, "wearable_node"):
            events.append(defaults[0])
        if not has_role(events, "connectivity_node"):
            events.append(defaults[1])

    next_seq = event_seq(events)
    motion = build_motion_event(choose_motion_seed(source_events), seq=next_seq, session_id=session_id, now=clock)
    events.append(motion)
    next_seq += 1

    ask_user = build_command(
        seq=next_seq,
        session_id=session_id,
        target_device_id=WEARABLE_ID,
        target_role="wearable_node",
        command="ask_user",
        command_payload={"text": "检测到异常，你现在安全吗？", "options": ["safe", "help"]},
        source_event=motion,
        now=clock,
    )
    events.append(ask_user)
    next_seq += 1

    confirmation = build_user_confirmation(
        seq=next_seq,
        session_id=session_id,
        response=user_response,
        source_event=ask_user,
        now=clock,
    )
    events.append(confirmation)
    next_seq += 1

    location_command = build_command(
        seq=next_seq,
        session_id=session_id,
        target_device_id=CONNECTIVITY_ID,
        target_role="connectivity_node",
        command="request_location",
        command_payload={"reason": "safety_event_confirmation"},
        source_event=confirmation,
        now=clock,
    )
    events.append(location_command)
    next_seq += 1

    ack = build_command_ack(seq=next_seq, session_id=session_id, command_event=location_command, now=clock)
    events.append(ack)
    next_seq += 1

    location = build_mock_location(seq=next_seq, session_id=session_id, source_event=ack, now=clock)
    events.append(location)
    next_seq += 1

    events.append(
        build_safety_event(
            seq=next_seq,
            session_id=session_id,
            response=user_response,
            motion_event=motion,
            confirmation_event=confirmation,
            location_event=location,
            now=clock,
        )
    )
    return events


def run_demo(
    *,
    event_log: Path,
    recording_dir: Path,
    session_id: str,
    user_response: str = "safe",
    source_path: Path | None = None,
    created_at: str | None = None,
    now: Callable[[], str] | None = None,
) -> dict[str, Any]:
    messages = load_jsonl(source_path)
    events = build_demo_events(
        source_messages=messages,
        session_id=session_id,
        user_response=user_response,
        now=now,
    )
    for event in events:
        event_store.append_jsonl(event_log, event)

    recording = session_recorder.build_recording(
        events,
        event_log=event_log,
        session_id=session_id,
        created_at=created_at,
    )
    paths = session_recorder.write_recording(recording, recording_dir)
    quality_report = session_inspector.inspect_recording(recording_dir)
    quality_json, quality_md = session_inspector.write_report(quality_report, recording_dir)

    return {
        "ok": quality_report["passed"],
        "demo_version": DEMO_VERSION,
        "session_id": session_id,
        "event_log": str(event_log),
        "recording_dir": str(recording_dir),
        "quality_report": {
            "path": str(quality_json),
            "markdown": str(quality_md),
            "passed": quality_report["passed"],
            "quality_score": quality_report["quality_score"],
        },
        "counts": {
            "events_written": len(events),
            **recording["manifest"]["record_counts"],
        },
        "response": user_response,
        "paths": {
            name: str(path)
            for name, path in {
                **paths,
                "quality_report_json": quality_json,
                "quality_report_markdown": quality_md,
            }.items()
        },
    }

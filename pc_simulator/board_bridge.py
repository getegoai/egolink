"""Dual-board PC bridge primitives for Ego Link P0.

The bridge keeps the two development boards decoupled. Board transports provide
newline-delimited JSON messages; this module normalizes them into the existing
PC Simulator event log and emits deterministic command events for early routing
tests. It intentionally avoids a Python serial dependency so the first PoC can
be verified with files/stdin and later wired to USB CDC or another transport.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, TextIO

from pc_simulator import event_store, protocol


BRIDGE_PROTOCOL_VERSION = "egolink.bridge.v0.1"
BOARD_PROTOCOL_VERSION = "0.2"
BRIDGE_INGEST_SOURCE = "pc_simulator.board_bridge"
KNOWN_ROLES = {"wearable_node", "connectivity_node"}
MOTION_EVENT_TYPES = {"motion_event", "imu_sample", "imu_motion"}
IMPACT_SCORE_TRIGGER = 0.8
FALL_SCORE_TRIGGER = 0.7


class BoardBridgeError(ValueError):
    """Raised when a bridge line or board payload cannot be ingested."""


@dataclass
class BridgeState:
    """Runtime state discovered from board hello messages."""

    role_to_device_id: dict[str, str] = field(default_factory=dict)
    device_id_to_role: dict[str, str] = field(default_factory=dict)
    next_command_seq: int = 1

    def bind(self, device_id: str, role: str) -> None:
        self.role_to_device_id[role] = device_id
        self.device_id_to_role[device_id] = role

    def role_for(self, device_id: str) -> str | None:
        return self.device_id_to_role.get(device_id)

    def device_for_role(self, role: str) -> str | None:
        return self.role_to_device_id.get(role)

    def command_id(self) -> str:
        value = f"bridge-cmd-{self.next_command_seq:06d}"
        self.next_command_seq += 1
        return value


@dataclass
class BridgeRunResult:
    stored_events: int = 0
    generated_commands: int = 0
    skipped_lines: int = 0
    devices: dict[str, str] = field(default_factory=dict)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_json_line(line: str) -> dict[str, Any]:
    stripped = line.strip().lstrip("\ufeff")
    if not stripped:
        raise BoardBridgeError("empty bridge line")
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise BoardBridgeError(f"invalid JSON payload: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise BoardBridgeError("bridge payload must be a JSON object")
    return payload


def normalize_message(
    message: dict[str, Any],
    *,
    received_at: str,
    bridge_source: str,
    state: BridgeState,
) -> dict[str, Any]:
    message_type = str(message.get("message_type") or message.get("type") or "")
    if message_type == "hello":
        return normalize_hello(message, received_at=received_at, bridge_source=bridge_source, state=state)
    return normalize_uplink_event(message, received_at=received_at, bridge_source=bridge_source, state=state)


def normalize_hello(
    message: dict[str, Any],
    *,
    received_at: str,
    bridge_source: str,
    state: BridgeState,
) -> dict[str, Any]:
    device_id = str(message.get("device_id") or "")
    role = str(message.get("role") or "")
    if not device_id:
        raise BoardBridgeError("hello message missing device_id")
    if role not in KNOWN_ROLES:
        raise BoardBridgeError(f"hello message has unsupported role: {role or '<missing>'}")

    state.bind(device_id, role)
    event = {
        "protocol_version": protocol.PROTOCOL_VERSION,
        "bridge_protocol_version": BRIDGE_PROTOCOL_VERSION,
        "board_protocol_version": str(message.get("protocol_version") or ""),
        "message_type": "event",
        "event_type": "board_hello",
        "priority": "normal",
        "direction": "uplink",
        "device_id": device_id,
        "role": role,
        "seq": message.get("seq"),
        "ts": str(message.get("ts") or message.get("timestamp_ms") or received_at),
        "received_at": received_at,
        "bridge_source": bridge_source,
        "ingest_source": BRIDGE_INGEST_SOURCE,
    }
    return drop_none(event)


def normalize_uplink_event(
    message: dict[str, Any],
    *,
    received_at: str,
    bridge_source: str,
    state: BridgeState,
) -> dict[str, Any]:
    event_type = str(message.get("event_type") or message.get("type") or "")
    device_id = str(message.get("device_id") or message.get("source") or "")
    if not device_id:
        raise BoardBridgeError("uplink message missing device_id/source")
    if not event_type:
        raise BoardBridgeError("uplink message missing event_type/type")
    if message.get("seq") in (None, ""):
        raise BoardBridgeError(f"{event_type} message missing seq")

    role = str(message.get("role") or state.role_for(device_id) or "")
    payload = message.get("payload")
    if payload is not None and not isinstance(payload, dict):
        raise BoardBridgeError("payload must be a JSON object when present")

    event = {
        "protocol_version": protocol.PROTOCOL_VERSION,
        "bridge_protocol_version": BRIDGE_PROTOCOL_VERSION,
        "message_type": "event",
        "event_type": event_type,
        "priority": str(message.get("priority") or priority_for_event(event_type)),
        "direction": "uplink",
        "device_id": device_id,
        "role": role or None,
        "seq": int(message["seq"]),
        "ts": ts_from_message(message, received_at),
        "received_at": received_at,
        "bridge_source": bridge_source,
        "ingest_source": BRIDGE_INGEST_SOURCE,
        "payload": payload,
    }

    for key in (
        "sensor_kind",
        "device_monotonic_ms",
        "timestamp_ms",
        "sample_hz",
        "imu_source",
        "sensor_model",
        "source_status",
        "source_availability",
    ):
        if key in message:
            event[key] = message[key]

    return drop_none(event)


def ts_from_message(message: dict[str, Any], received_at: str) -> str:
    if message.get("ts") not in (None, ""):
        return str(message["ts"])
    if message.get("device_monotonic_ms") not in (None, ""):
        return f"uptime_ms:{message['device_monotonic_ms']}"
    if message.get("timestamp_ms") not in (None, ""):
        return f"timestamp_ms:{message['timestamp_ms']}"
    return received_at


def priority_for_event(event_type: str) -> str:
    if event_type == "sos_pressed":
        return "critical"
    if event_type == "motion_event":
        return "high"
    return "normal"


def route_commands_for_event(event: dict[str, Any], state: BridgeState) -> list[dict[str, Any]]:
    if event.get("event_type") not in MOTION_EVENT_TYPES:
        return []

    payload = event.get("payload")
    if not isinstance(payload, dict):
        payload = {}
    impact_score = numeric(payload.get("impact_score"))
    fall_score = numeric(payload.get("fall_score"))
    should_route = (
        (impact_score is not None and impact_score >= IMPACT_SCORE_TRIGGER)
        or (fall_score is not None and fall_score >= FALL_SCORE_TRIGGER)
    )
    if not should_route:
        return []

    commands: list[dict[str, Any]] = []
    wearable_id = state.device_for_role("wearable_node")
    connectivity_id = state.device_for_role("connectivity_node")
    if wearable_id:
        commands.append(
            build_command_event(
                state,
                source_event=event,
                target_role="wearable_node",
                target_device_id=wearable_id,
                cmd="ask_user",
                payload={"text": "Impact detected. Are you safe?", "options": ["safe", "help"]},
            )
        )
    if connectivity_id:
        commands.append(
            build_command_event(
                state,
                source_event=event,
                target_role="connectivity_node",
                target_device_id=connectivity_id,
                cmd="request_location",
                payload={},
            )
        )
    return commands


def build_command_event(
    state: BridgeState,
    *,
    source_event: dict[str, Any],
    target_role: str,
    target_device_id: str,
    cmd: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    cmd_id = state.command_id()
    return {
        "protocol_version": protocol.PROTOCOL_VERSION,
        "bridge_protocol_version": BRIDGE_PROTOCOL_VERSION,
        "message_type": "command",
        "event_type": "command_sent",
        "priority": "normal",
        "direction": "downlink",
        "device_id": str(source_event.get("device_id") or protocol.DEVICE_ID),
        "target_device_id": target_device_id,
        "target_role": target_role,
        "seq": state.next_command_seq - 1,
        "ts": str(source_event.get("received_at") or utc_now()),
        "received_at": str(source_event.get("received_at") or utc_now()),
        "cmd_id": cmd_id,
        "cmd": cmd,
        "command_payload": payload,
        "source": BRIDGE_INGEST_SOURCE,
        "source_event_key": bridge_source_event_key(source_event),
        "source_event_type": str(source_event.get("event_type") or "unknown"),
    }


def build_downlink_message(command_event: dict[str, Any], *, session_id: str = "demo-v0-2") -> dict[str, Any]:
    """Render a bridge command event into the board-facing v0.2 JSON message."""

    cmd = str(command_event.get("cmd") or "")
    target_device_id = str(command_event.get("target_device_id") or "")
    cmd_id = str(command_event.get("cmd_id") or "")
    if not cmd:
        raise BoardBridgeError("command event missing cmd")
    if not target_device_id:
        raise BoardBridgeError("command event missing target_device_id")
    if not cmd_id:
        raise BoardBridgeError("command event missing cmd_id")

    payload = command_event.get("command_payload")
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise BoardBridgeError("command_payload must be a JSON object")

    rendered = {
        "protocol_version": BOARD_PROTOCOL_VERSION,
        "source": "pc-bridge",
        "target": target_device_id,
        "type": cmd,
        "cmd": cmd,
        "cmd_id": cmd_id,
        "seq": command_event.get("seq"),
        "timestamp_ms": timestamp_ms_from_bridge_event(command_event),
        "session_id": str(command_event.get("session_id") or session_id),
        "payload": payload,
    }
    return drop_none(rendered)


def timestamp_ms_from_bridge_event(event: dict[str, Any]) -> int | None:
    direct_value = event.get("timestamp_ms")
    if isinstance(direct_value, int):
        return direct_value
    if isinstance(direct_value, str) and direct_value.isdigit():
        return int(direct_value)

    value = str(event.get("received_at") or event.get("ts") or "")
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return int(parsed.timestamp() * 1000)


def bridge_source_event_key(event: dict[str, Any]) -> str:
    device_id = str(event.get("device_id") or protocol.DEVICE_ID)
    event_type = str(event.get("event_type") or "unknown")
    seq = event.get("seq")
    timestamp = str(event.get("received_at") or event.get("ts") or "")
    if seq not in (None, ""):
        return f"{device_id}:{event_type}:{seq}:{timestamp}" if timestamp else f"{device_id}:{event_type}:{seq}"
    return f"{device_id}:{event_type}:{timestamp}"


def consume_named_sources(
    sources: dict[str, Iterable[str]],
    event_log: Path,
    *,
    now: Callable[[], str] = utc_now,
    errors: TextIO | None = None,
) -> BridgeRunResult:
    state = BridgeState()
    result = BridgeRunResult()
    for bridge_source, lines in sources.items():
        for line in lines:
            try:
                message = parse_json_line(line)
                event = normalize_message(message, received_at=now(), bridge_source=bridge_source, state=state)
            except BoardBridgeError as exc:
                result.skipped_lines += 1
                if errors is not None:
                    print(f"board_bridge skipped line from {bridge_source}: {exc}", file=errors)
                continue
            event_store.append_jsonl(event_log, event)
            result.stored_events += 1
            commands = route_commands_for_event(event, state)
            for command in commands:
                event_store.append_jsonl(event_log, command)
                result.stored_events += 1
                result.generated_commands += 1
    result.devices = dict(sorted(state.role_to_device_id.items()))
    return result


def numeric(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def drop_none(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def read_source_lines(path: Path | str) -> list[str]:
    if str(path) == "-":
        return sys.stdin.read().splitlines()
    return Path(path).read_text(encoding="utf-8-sig").splitlines()

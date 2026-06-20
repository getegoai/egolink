"""Ego Link P0 message builders and validation helpers."""

from __future__ import annotations

from typing import Any

PROTOCOL_VERSION = "egolink.p0.v1"
DEVICE_ID = "ego-link-001"


def base_message(device_id: str, ts: str, seq: int) -> dict[str, Any]:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "device_id": device_id,
        "ts": ts,
        "seq": seq,
    }


def status_message(device_id: str, ts: str, seq: int, **fields: Any) -> dict[str, Any]:
    message = base_message(device_id, ts, seq)
    message.update({"message_type": "status"})
    message.update(fields)
    require_fields(message, ["battery", "link_type", "guard_mode", "queue_size"])
    return message


def event_message(device_id: str, ts: str, seq: int, event_type: str, priority: str, **fields: Any) -> dict[str, Any]:
    message = base_message(device_id, ts, seq)
    message.update({"message_type": "event", "event_type": event_type, "priority": priority})
    message.update(fields)
    require_fields(message, ["event_type", "priority"])
    return message


def command_message(cmd_id: str, cmd: str, **fields: Any) -> dict[str, Any]:
    message = {
        "protocol_version": PROTOCOL_VERSION,
        "message_type": "command",
        "cmd_id": cmd_id,
        "cmd": cmd,
    }
    message.update(fields)
    require_fields(message, ["cmd_id", "cmd"])
    return message


def ack_message(device_id: str, ts: str, seq: int, cmd_id: str, status: str) -> dict[str, Any]:
    message = base_message(device_id, ts, seq)
    message.update({"message_type": "ack", "cmd_id": cmd_id, "status": status})
    return message


def require_fields(message: dict[str, Any], fields: list[str]) -> None:
    missing = [field for field in fields if field not in message or message[field] in (None, "")]
    if missing:
        raise ValueError("missing required fields: " + ", ".join(missing))

"""Live Demo v0.3 safety loop built from AMOLED touch and SIM7670G GNSS evidence."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable, Iterable

from pc_simulator import (
    board_bridge,
    event_store,
    minimal_safety_demo,
    protocol,
    session_inspector,
    session_recorder,
    session_replay,
)


LIVE_DEMO_VERSION = "egolink.demo.live_safety_loop.v0.3"
DEMO_PROTOCOL_VERSION = "0.2"
PC_BRIDGE_ID = minimal_safety_demo.PC_BRIDGE_ID
WEARABLE_ID = minimal_safety_demo.WEARABLE_ID
CONNECTIVITY_ID = minimal_safety_demo.CONNECTIVITY_ID
VALID_RESPONSES = {"safe", "help"}


class LiveSafetyDemoError(ValueError):
    """Raised when the live demo evidence is missing a required loop step."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise LiveSafetyDemoError(f"Expected JSON object: {path}")
    return value


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if isinstance(value, dict):
            rows.append(value)
    return rows


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_amoled_messages(
    messages: Iterable[dict[str, Any]],
    *,
    session_id: str,
    now: Callable[[], str],
) -> list[dict[str, Any]]:
    state = board_bridge.BridgeState()
    events: list[dict[str, Any]] = []
    for message in messages:
        try:
            event = board_bridge.normalize_message(
                message,
                received_at=now(),
                bridge_source="amoled_live_demo",
                state=state,
            )
        except board_bridge.BoardBridgeError:
            continue
        event["demo_protocol_version"] = DEMO_PROTOCOL_VERSION
        event["demo_version"] = LIVE_DEMO_VERSION
        event["session_id"] = str(event.get("session_id") or session_id)
        if event.get("event_type") == "user_confirmation":
            event["priority"] = "high" if event.get("response") == "help" else "normal"
        events.append(event)
    return events


def require_user_confirmation(events: list[dict[str, Any]]) -> dict[str, Any]:
    confirmations = [event for event in events if event.get("event_type") == "user_confirmation"]
    if not confirmations:
        raise LiveSafetyDemoError("AMOLED evidence missing user_confirmation.")
    confirmation = confirmations[-1]
    response = str(confirmation.get("response") or "")
    if response not in VALID_RESPONSES:
        raise LiveSafetyDemoError(f"Unsupported user_confirmation response: {response or '<missing>'}")
    if not confirmation.get("cmd_id"):
        raise LiveSafetyDemoError("AMOLED user_confirmation missing cmd_id.")
    return confirmation


def require_ask_user_rendered(events: list[dict[str, Any]], cmd_id: str) -> dict[str, Any]:
    rendered = [
        event
        for event in events
        if event.get("event_type") == "ask_user_rendered" and str(event.get("cmd_id") or "") == cmd_id
    ]
    if not rendered:
        raise LiveSafetyDemoError("AMOLED evidence missing ask_user_rendered for the confirmation cmd_id.")
    return rendered[-1]


def mark_live(event: dict[str, Any]) -> dict[str, Any]:
    event["demo_protocol_version"] = DEMO_PROTOCOL_VERSION
    event["demo_version"] = LIVE_DEMO_VERSION
    return event


def build_location_command_ack(
    *,
    seq: int,
    session_id: str,
    command_event: dict[str, Any],
    at_ok: bool,
    selected_port: str | None,
    now: Callable[[], str],
) -> dict[str, Any]:
    return mark_live(
        {
            "protocol_version": protocol.PROTOCOL_VERSION,
            "message_type": "ack",
            "event_type": "command_ack",
            "priority": "normal",
            "direction": "uplink",
            "device_id": CONNECTIVITY_ID,
            "role": "connectivity_node",
            "seq": seq,
            "ts": now(),
            "received_at": now(),
            "session_id": session_id,
            "cmd_id": command_event.get("cmd_id"),
            "cmd": command_event.get("cmd"),
            "ack_status": "pc_at_probe_ok" if at_ok else "pc_at_probe_failed",
            "source": "sim7670g_gnss_probe",
            "port": selected_port,
            "source_event_key": minimal_safety_demo.source_event_key(command_event),
            "source_event_type": "command_sent",
        }
    )


def adapt_location_event(
    location_event: dict[str, Any],
    *,
    seq: int,
    session_id: str,
    source_event: dict[str, Any],
    now: Callable[[], str],
) -> dict[str, Any]:
    event = dict(location_event)
    event.update(
        {
            "protocol_version": protocol.PROTOCOL_VERSION,
            "message_type": "event",
            "event_type": "location_report",
            "priority": "normal",
            "direction": "uplink",
            "device_id": CONNECTIVITY_ID,
            "role": "connectivity_node",
            "seq": seq,
            "ts": event.get("ts") or now(),
            "received_at": event.get("received_at") or now(),
            "session_id": session_id,
            "source": event.get("source") or "sim7670g_gnss",
            "source_event_key": minimal_safety_demo.source_event_key(source_event),
            "source_event_type": "command_ack",
        }
    )
    return mark_live(drop_none(event))


def synthetic_location_failure(
    *,
    seq: int,
    session_id: str,
    source_event: dict[str, Any],
    now: Callable[[], str],
) -> dict[str, Any]:
    return adapt_location_event(
        {
            "fix": False,
            "gnss_state": "probe_failed",
            "gnss_power_state": None,
            "raw_response": "SIM7670G GNSS probe did not return an AT-ok result.",
            "source": "sim7670g_gnss",
        },
        seq=seq,
        session_id=session_id,
        source_event=source_event,
        now=now,
    )


def build_live_events(
    *,
    amoled_messages: Iterable[dict[str, Any]],
    location_event: dict[str, Any] | None,
    session_id: str,
    gnss_at_ok: bool = True,
    selected_gnss_port: str | None = None,
    allow_gnss_failure: bool = False,
    now: Callable[[], str] | None = None,
) -> list[dict[str, Any]]:
    clock = now or utc_now
    amoled_events = normalize_amoled_messages(amoled_messages, session_id=session_id, now=clock)
    confirmation = require_user_confirmation(amoled_events)
    cmd_id = str(confirmation["cmd_id"])
    require_ask_user_rendered(amoled_events, cmd_id)

    events = [mark_live(event) for event in minimal_safety_demo.default_hello_events(now=clock)]

    seq = minimal_safety_demo.event_seq(events)
    motion = mark_live(
        minimal_safety_demo.build_motion_event(
            None,
            seq=seq,
            session_id=session_id,
            now=clock,
        )
    )
    motion["source"] = "live_safety_demo"
    events.append(motion)

    seq = minimal_safety_demo.event_seq(events)
    ask_user = mark_live(
        minimal_safety_demo.build_command(
            seq=seq,
            session_id=session_id,
            target_device_id=WEARABLE_ID,
            target_role="wearable_node",
            command="ask_user",
            command_payload={"text": "Impact detected. Are you safe?", "options": ["safe", "help"]},
            source_event=motion,
            now=clock,
        )
    )
    ask_user["cmd_id"] = cmd_id
    ask_user["source"] = "live_safety_demo"
    events.append(ask_user)

    ask_key = minimal_safety_demo.source_event_key(ask_user)
    for event in amoled_events:
        if event.get("event_type") in {"command_ack", "ask_user_rendered", "user_confirmation"}:
            event["source_event_key"] = ask_key
            event["source_event_type"] = "command_sent"
        events.append(mark_live(event))

    seq = minimal_safety_demo.event_seq(events)
    request_location = mark_live(
        minimal_safety_demo.build_command(
            seq=seq,
            session_id=session_id,
            target_device_id=CONNECTIVITY_ID,
            target_role="connectivity_node",
            command="request_location",
            command_payload={"reason": "safety_event_confirmation", "user_response": confirmation["response"]},
            source_event=confirmation,
            now=clock,
        )
    )
    request_location["source"] = "live_safety_demo"
    events.append(request_location)

    seq = minimal_safety_demo.event_seq(events)
    location_ack = build_location_command_ack(
        seq=seq,
        session_id=session_id,
        command_event=request_location,
        at_ok=gnss_at_ok,
        selected_port=selected_gnss_port,
        now=clock,
    )
    events.append(location_ack)

    if location_event is None and not allow_gnss_failure:
        raise LiveSafetyDemoError("GNSS probe did not produce a location_report event.")

    seq = minimal_safety_demo.event_seq(events)
    location = (
        adapt_location_event(location_event, seq=seq, session_id=session_id, source_event=location_ack, now=clock)
        if location_event is not None
        else synthetic_location_failure(seq=seq, session_id=session_id, source_event=location_ack, now=clock)
    )
    events.append(location)

    seq = minimal_safety_demo.event_seq(events)
    safety = mark_live(
        minimal_safety_demo.build_safety_event(
            seq=seq,
            session_id=session_id,
            response=str(confirmation["response"]),
            motion_event=motion,
            confirmation_event=confirmation,
            location_event=location,
            now=clock,
        )
    )
    safety["source"] = "live_safety_demo"
    events.append(safety)
    return events


def run_live_demo(
    *,
    amoled_jsonl: Path,
    location_event: dict[str, Any] | None,
    event_log: Path,
    recording_dir: Path,
    session_id: str,
    gnss_at_ok: bool = True,
    selected_gnss_port: str | None = None,
    allow_gnss_failure: bool = False,
    created_at: str | None = None,
    now: Callable[[], str] | None = None,
) -> dict[str, Any]:
    events = build_live_events(
        amoled_messages=load_jsonl(amoled_jsonl),
        location_event=location_event,
        session_id=session_id,
        gnss_at_ok=gnss_at_ok,
        selected_gnss_port=selected_gnss_port,
        allow_gnss_failure=allow_gnss_failure,
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
    replay_report = session_replay.replay_recording(recording_dir)
    replay_json, replay_md = session_replay.write_report(replay_report, recording_dir)

    event_counts: dict[str, int] = {}
    for event in events:
        key = str(event.get("event_type") or event.get("message_type") or "unknown")
        event_counts[key] = event_counts.get(key, 0) + 1

    response_event = require_user_confirmation(events)
    result = {
        "ok": bool(quality_report["passed"] and replay_report["passed"]),
        "demo_version": LIVE_DEMO_VERSION,
        "session_id": session_id,
        "event_log": str(event_log),
        "recording_dir": str(recording_dir),
        "response": response_event["response"],
        "event_counts": dict(sorted(event_counts.items())),
        "quality_report": {
            "path": str(quality_json),
            "markdown": str(quality_md),
            "passed": quality_report["passed"],
            "quality_score": quality_report["quality_score"],
        },
        "replay_report": {
            "path": str(replay_json),
            "markdown": str(replay_md),
            "passed": replay_report["passed"],
            "summary": replay_report["summary"],
        },
        "paths": {
            name: str(path)
            for name, path in {
                **paths,
                "quality_report_json": quality_json,
                "quality_report_markdown": quality_md,
                "replay_report_json": replay_json,
                "replay_report_markdown": replay_md,
            }.items()
        },
    }
    return result


def drop_none(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}

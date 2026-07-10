"""Full Demo v0.5 orchestration for the Ego Link P0 safety loop."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable, Iterable

from pc_simulator import (
    event_store,
    live_safety_demo,
    minimal_safety_demo,
    protocol,
    session_inspector,
    session_recorder,
    session_replay,
)


FULL_DEMO_VERSION = "egolink.demo.full_safety_loop.v0.5"
AUDIO_MODE_MOCK = "mock"
AUDIO_MODE_DISABLED = "disabled"
VALID_AUDIO_MODES = {AUDIO_MODE_MOCK, AUDIO_MODE_DISABLED}


class FullSafetyDemoError(ValueError):
    """Raised when full demo evidence cannot satisfy the requested gate."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise FullSafetyDemoError(f"Expected JSON object: {path}")
    return value


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def mark_full(event: dict[str, Any]) -> dict[str, Any]:
    value = dict(event)
    value["full_demo_version"] = FULL_DEMO_VERSION
    return value


def build_capture_audio_command(
    *,
    seq: int,
    session_id: str,
    source_event: dict[str, Any],
    now: Callable[[], str],
) -> dict[str, Any]:
    command = minimal_safety_demo.build_command(
        seq=seq,
        session_id=session_id,
        target_device_id=live_safety_demo.WEARABLE_ID,
        target_role="wearable_node",
        command="capture_audio",
        command_payload={
            "mode": "structured_mock",
            "duration_ms": 1000,
            "raw_audio_allowed": False,
            "reason": "demo_v0_4_audio_chain_boundary",
        },
        source_event=source_event,
        now=now,
    )
    command["source"] = "full_safety_demo"
    return mark_full(command)


def build_mock_audio_ack(
    *,
    seq: int,
    session_id: str,
    command_event: dict[str, Any],
    now: Callable[[], str],
) -> dict[str, Any]:
    ack = minimal_safety_demo.build_command_ack(
        seq=seq,
        session_id=session_id,
        command_event=command_event,
        now=now,
    )
    ack.update(
        {
            "device_id": live_safety_demo.WEARABLE_ID,
            "role": "wearable_node",
            "ack_status": "mock_only",
            "source": "audio_chain_mock",
            "source_availability": "mock",
            "source_status": "mock_only",
        }
    )
    return mark_full(ack)


def build_mock_wake_detected(
    *,
    seq: int,
    session_id: str,
    source_event: dict[str, Any],
    now: Callable[[], str],
) -> dict[str, Any]:
    return mark_full(
        {
            "protocol_version": protocol.PROTOCOL_VERSION,
            "demo_protocol_version": live_safety_demo.DEMO_PROTOCOL_VERSION,
            "demo_version": FULL_DEMO_VERSION,
            "message_type": "event",
            "event_type": "wake_detected",
            "priority": "normal",
            "direction": "uplink",
            "device_id": live_safety_demo.WEARABLE_ID,
            "role": "wearable_node",
            "seq": seq,
            "ts": now(),
            "received_at": now(),
            "session_id": session_id,
            "source": "audio_chain_mock",
            "source_availability": "mock",
            "source_status": "mock_only",
            "confidence": 0.62,
            "speech_score": 0.62,
            "distress_score": 0.0,
            "impact_sound_score": 0.0,
            "unknown_loud_sound_score": 0.0,
            "audio_quality_score": 0.8,
            "audio_capture_mode": "structured_mock",
            "raw_audio_captured": False,
            "audio_clip_ref": None,
            "source_event_key": minimal_safety_demo.source_event_key(source_event),
            "source_event_type": "command_ack",
        }
    )


def append_mock_audio_chain(
    events: list[dict[str, Any]],
    *,
    session_id: str,
    now: Callable[[], str],
) -> list[dict[str, Any]]:
    motion = next((event for event in events if event.get("event_type") == "motion_event"), events[-1])
    seq = minimal_safety_demo.event_seq(events)
    command = build_capture_audio_command(seq=seq, session_id=session_id, source_event=motion, now=now)
    events.append(command)

    seq = minimal_safety_demo.event_seq(events)
    ack = build_mock_audio_ack(seq=seq, session_id=session_id, command_event=command, now=now)
    events.append(ack)

    seq = minimal_safety_demo.event_seq(events)
    events.append(build_mock_wake_detected(seq=seq, session_id=session_id, source_event=ack, now=now))
    return events


def build_full_events(
    *,
    amoled_messages: Iterable[dict[str, Any]],
    location_event: dict[str, Any] | None,
    session_id: str,
    gnss_at_ok: bool = True,
    selected_gnss_port: str | None = None,
    allow_gnss_failure: bool = False,
    audio_mode: str = AUDIO_MODE_MOCK,
    now: Callable[[], str] | None = None,
) -> list[dict[str, Any]]:
    if audio_mode not in VALID_AUDIO_MODES:
        raise FullSafetyDemoError("audio_mode must be one of: " + ", ".join(sorted(VALID_AUDIO_MODES)))

    clock = now or utc_now
    events = [
        mark_full(event)
        for event in live_safety_demo.build_live_events(
            amoled_messages=amoled_messages,
            location_event=location_event,
            session_id=session_id,
            gnss_at_ok=gnss_at_ok,
            selected_gnss_port=selected_gnss_port,
            allow_gnss_failure=allow_gnss_failure,
            now=clock,
        )
    ]
    if audio_mode == AUDIO_MODE_MOCK:
        append_mock_audio_chain(events, session_id=session_id, now=clock)
    return events


def patch_recording_manifest(recording: dict[str, Any], *, audio_mode: str) -> None:
    manifest = recording["manifest"]
    manifest["demo_version"] = FULL_DEMO_VERSION
    manifest["privacy"]["raw_audio_allowed"] = False
    manifest["privacy"]["raw_image_allowed"] = False
    manifest["privacy"]["notes"] = "Full demo stores structured events only; no raw audio or image files are captured."
    if audio_mode == AUDIO_MODE_MOCK:
        manifest["sensor_sources"]["microphone"] = {
            "availability": "mock",
            "status": "mock_only",
            "source": "pc_simulator/full_safety_demo.py",
            "records": ["wake_detected"],
            "note": "Structured audio wake evidence only; no real microphone samples or raw clips.",
        }
        manifest["sensor_sources"]["audio_wake_mock"] = {
            "availability": "mock",
            "status": "mock_only",
            "source": "pc_simulator/full_safety_demo.py",
            "records": ["wake_detected", "capture_audio command_ack"],
        }
    manifest.setdefault("limitations", []).append(
        "Full demo audio evidence is mock-only unless a later task supplies accepted microphone hardware evidence."
    )


def event_counts(events: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        key = str(event.get("event_type") or event.get("message_type") or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def has_command(events: list[dict[str, Any]], command: str) -> bool:
    return any(event.get("event_type") == "command_sent" and event.get("cmd") == command for event in events)


def has_command_ack(events: list[dict[str, Any]], command: str) -> bool:
    return any(event.get("event_type") == "command_ack" and event.get("cmd") == command for event in events)


def has_event(events: list[dict[str, Any]], event_type: str) -> bool:
    return any(event.get("event_type") == event_type for event in events)


def latest_event(events: list[dict[str, Any]], event_type: str) -> dict[str, Any] | None:
    return next((event for event in reversed(events) if event.get("event_type") == event_type), None)


def build_stage_gates(
    *,
    events: list[dict[str, Any]],
    quality_report: dict[str, Any],
    replay_report: dict[str, Any],
    audio_mode: str,
    gnss_at_ok: bool,
    require_real_gnss_fix: bool,
) -> dict[str, dict[str, Any]]:
    location = latest_event(events, "location_report") or {}
    gnss_fix = bool(location.get("fix"))
    audio_mock = latest_event(events, "wake_detected") or {}
    v03_passed = bool(has_event(events, "location_report") and gnss_at_ok)
    if require_real_gnss_fix:
        v03_passed = v03_passed and gnss_fix
    stages = {
        "demo_v0_1": {
            "passed": all(
                [
                    has_event(events, "motion_event"),
                    has_command(events, "ask_user"),
                    has_event(events, "ask_user_rendered"),
                    has_event(events, "user_confirmation"),
                    has_event(events, "safety_event"),
                ]
            ),
            "boundary": "real_amOLED_imu_touch_when_live_capture_is_used",
        },
        "demo_v0_2": {
            "passed": all(
                [
                    has_command(events, "request_location"),
                    has_command_ack(events, "request_location"),
                    has_event(events, "location_report"),
                ]
            ),
            "boundary": "SIM7670G ACK may be PC-side AT probe or explicit mock/no-fix evidence",
        },
        "demo_v0_3": {
            "passed": v03_passed,
            "gnss_at_ok": bool(gnss_at_ok),
            "real_fix": gnss_fix,
            "require_real_fix": require_real_gnss_fix,
            "boundary": "GNSS no-fix is acceptable unless --require-real-gnss-fix is set",
        },
        "demo_v0_4": {
            "passed": bool(audio_mode == AUDIO_MODE_MOCK and audio_mock),
            "audio_mode": audio_mode,
            "source_status": audio_mock.get("source_status") if audio_mock else "disabled",
            "raw_audio_captured": bool(audio_mock.get("raw_audio_captured")) if audio_mock else False,
            "boundary": "structured audio mock only; no raw microphone capture",
        },
        "demo_v0_5": {
            "passed": bool(quality_report["passed"] and replay_report["passed"]),
            "quality_score": quality_report["quality_score"],
            "replay_passed": replay_report["passed"],
            "boundary": "bounded runner, file integrity, quality gate, and replay are required",
        },
    }
    return stages


def run_full_demo(
    *,
    amoled_jsonl: Path,
    location_event: dict[str, Any] | None,
    event_log: Path,
    recording_dir: Path,
    session_id: str,
    gnss_at_ok: bool = True,
    selected_gnss_port: str | None = None,
    allow_gnss_failure: bool = False,
    require_real_gnss_fix: bool = False,
    audio_mode: str = AUDIO_MODE_MOCK,
    created_at: str | None = None,
    now: Callable[[], str] | None = None,
) -> dict[str, Any]:
    events = build_full_events(
        amoled_messages=live_safety_demo.load_jsonl(amoled_jsonl),
        location_event=location_event,
        session_id=session_id,
        gnss_at_ok=gnss_at_ok,
        selected_gnss_port=selected_gnss_port,
        allow_gnss_failure=allow_gnss_failure,
        audio_mode=audio_mode,
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
    patch_recording_manifest(recording, audio_mode=audio_mode)
    paths = session_recorder.write_recording(recording, recording_dir)
    quality_report = session_inspector.inspect_recording(recording_dir)
    quality_json, quality_md = session_inspector.write_report(quality_report, recording_dir)
    replay_report = session_replay.replay_recording(recording_dir)
    replay_json, replay_md = session_replay.write_report(replay_report, recording_dir)
    stages = build_stage_gates(
        events=events,
        quality_report=quality_report,
        replay_report=replay_report,
        audio_mode=audio_mode,
        gnss_at_ok=gnss_at_ok,
        require_real_gnss_fix=require_real_gnss_fix,
    )

    result = {
        "ok": all(stage["passed"] for stage in stages.values()),
        "demo_version": FULL_DEMO_VERSION,
        "session_id": session_id,
        "event_log": str(event_log),
        "recording_dir": str(recording_dir),
        "event_counts": event_counts(events),
        "stages": stages,
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
        "privacy": {
            "raw_audio_captured": False,
            "raw_image_captured": False,
            "recording_mode": recording["manifest"]["privacy"]["mode"],
        },
        "stability": {
            "bounded_capture": True,
            "event_log_created": event_log.is_file(),
            "recording_created": recording_dir.is_dir(),
            "file_integrity_checked": True,
            "replay_checked": True,
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

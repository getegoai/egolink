"""Write a bounded, browser-readable CALL-001 PC fixture artifact."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

from pc_simulator.ego_call import EgoCallFixture, replay_events


class _Ids:
    def __init__(self) -> None:
        self.value = 0

    def __call__(self) -> str:
        self.value += 1
        return f"{self.value:04d}"


class _Clock:
    def __init__(self) -> None:
        self.second = 0

    def __call__(self) -> str:
        value = f"2026-08-23T08:00:{self.second:02d}Z"
        self.second += 1
        return value


def run_fixture() -> tuple[list[dict], list[dict], dict]:
    fixture = EgoCallFixture(
        authorized_bindings={("device-demo", "guardian-demo")},
        clock=_Clock(),
        id_factory=_Ids(),
    )
    location_ref = {
        "belief_id": "belief-demo",
        "state": "Predicted",
        "observed_at_utc": "2026-08-23T07:59:50Z",
        "age_ms": 10000,
        "radius_m": 80.0,
    }
    sos = fixture.compose_manual_sos(
        device_id="device-demo",
        guardian_id="guardian-demo",
        sos_event_id="sos-demo",
        idempotency_key="demo-sos-request",
        location_belief_ref=location_ref,
    )
    session_id = sos["call_event"]["session_id"]
    for index, (state, reason) in enumerate(
        (
            ("ringing", "guardian_notified"),
            ("connected", "media_ready"),
            ("reconnecting", "media_lost"),
            ("connected", "media_recovered"),
            ("ended", "remote_hangup"),
        ),
        start=1,
    ):
        actor_role, actor_id = {
            "guardian_notified": ("call_control", "fixture-call-control"),
            "media_ready": ("rtc_adapter", "fixture-rtc-adapter"),
            "media_lost": ("rtc_adapter", "fixture-rtc-adapter"),
            "media_recovered": ("rtc_adapter", "fixture-rtc-adapter"),
            "remote_hangup": ("guardian", "guardian-demo"),
        }[reason]
        fixture.transition(
            session_id,
            to_state=state,
            reason_code=reason,
            idempotency_key=f"demo-happy-{index:02d}",
            actor_role=actor_role,
            actor_id=actor_id,
        )

    failed = fixture.request(
        device_id="device-demo",
        guardian_id="guardian-demo",
        idempotency_key="demo-failure-request",
        trigger_type="guardian_call",
        initiator="guardian",
        actor_role="guardian",
        actor_id="guardian-demo",
        location_belief_ref=None,
    )
    fixture.transition(
        failed["session_id"],
        to_state="failed",
        reason_code="network_unavailable",
        idempotency_key="demo-failure-final",
        actor_role="rtc_adapter",
        actor_id="fixture-rtc-adapter",
    )
    replay = replay_events(fixture.events)
    return fixture.events, fixture.local_sos_events, {
        "fixture_version": "egolink.ego_call_demo.v0.1",
        "sos": sos["local_event"],
        "replay": replay,
        "claims": {
            "state_contract": "pc_side_verified",
            "call_session_replay": "pc_side_verified",
            "local_sos_ordering": "in_memory_fixture_only",
            "local_sos_durability": "unverified",
            "sos_safety_contract": "unverified_reuse_existing_contract_in_followup",
            "rtc_media": "unverified",
            "device_audio": "unverified",
            "guardian_mobile_app": "unverified",
            "weak_network": "simulated_state_only",
        },
    }


def write_outputs(output_dir: Path) -> dict[str, str]:
    events, sos_events, summary = run_fixture()
    output_dir.mkdir(parents=True, exist_ok=True)
    events_path = output_dir / "ego_call_events.jsonl"
    sos_events_path = output_dir / "ego_call_sos_fixture_trace.jsonl"
    summary_path = output_dir / "ego_call_summary.json"
    browser_path = output_dir / "ego_call_fixture.html"

    events_path.write_text(
        "".join(json.dumps(event, sort_keys=True) + "\n" for event in events),
        encoding="utf-8",
    )
    sos_events_path.write_text(
        "".join(json.dumps(event, sort_keys=True) + "\n" for event in sos_events),
        encoding="utf-8",
    )
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    escaped_summary = html.escape(json.dumps(summary, indent=2, sort_keys=True))
    browser_path.write_text(
        "<!doctype html><html lang='zh-CN'><meta charset='utf-8'>"
        "<title>Ego Call CALL-001 PC Fixture</title>"
        "<main><h1>Ego Call CALL-001 PC Fixture</h1>"
        "<p>仅验证通话状态、权限、失败与回放；SOS 本地记录仅为内存顺序轨迹；"
        "不证明 RTC、设备音频、弱网能力或安全事件持久化。</p>"
        f"<pre>{escaped_summary}</pre></main></html>\n",
        encoding="utf-8",
    )
    return {
        "events": str(events_path),
        "sos_fixture_trace": str(sos_events_path),
        "summary": str(summary_path),
        "browser": str(browser_path),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    outputs = write_outputs(args.output_dir)
    print(json.dumps({"ok": True, "outputs": outputs}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Run Demo v0.3: AMOLED confirmation plus SIM7670G GNSS safety record."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pc_simulator import live_safety_demo
from scripts import sim7670_gnss_probe


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME = REPO_ROOT / "pc_simulator" / "runtime" / "demo_v0_3"


def default_session_id() -> str:
    return "demo-v0-3-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--event-log", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None, help="Recording output directory.")
    parser.add_argument("--runtime-dir", type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument("--json", action="store_true")

    parser.add_argument("--amoled-jsonl", type=Path, default=None, help="Use an existing AMOLED JSONL capture.")
    parser.add_argument("--amoled-port", default="", help="Optional AMOLED USB Serial/JTAG port.")
    parser.add_argument("--amoled-wait-seconds", type=int, default=60)
    parser.add_argument("--wait-for-motion", action="store_true", help="Wait for a physical motion event.")
    parser.add_argument("--reset-amoled", action="store_true")

    parser.add_argument("--location-event-json", type=Path, default=None, help="Use an existing location_report JSON object.")
    parser.add_argument("--sim-port", dest="sim_ports", action="append", default=[])
    parser.add_argument("--probe-all-sim-ports", action="store_true")
    parser.add_argument("--no-gnss-power-on", action="store_true")
    parser.add_argument("--gnss-warmup-seconds", type=float, default=3.0)
    parser.add_argument("--gnss-poll-count", type=int, default=3)
    parser.add_argument("--gnss-poll-interval-seconds", type=float, default=2.0)
    parser.add_argument("--allow-gnss-failure", action="store_true")
    return parser.parse_args(argv)


def run_amoled_capture(args: argparse.Namespace, *, session_id: str, amoled_dir: Path) -> tuple[Path, dict[str, object]]:
    if args.amoled_jsonl is not None:
        return args.amoled_jsonl, {"source": "provided", "jsonl_path": str(args.amoled_jsonl)}

    script = REPO_ROOT / "scripts" / "run_amoled_ask_user_demo.ps1"
    command = [
        "powershell",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-RequireConfirmation",
        "-WaitSeconds",
        str(args.amoled_wait_seconds),
        "-SessionId",
        session_id,
        "-OutputDir",
        str(amoled_dir),
    ]
    if args.amoled_port:
        command.extend(["-Port", args.amoled_port])
    if args.reset_amoled:
        command.append("-Reset")
    if args.wait_for_motion:
        command.append("-WaitForMotionEvent")

    completed = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True)
    summary_path = amoled_dir / f"{session_id}.summary.json"
    if completed.returncode != 0:
        raise live_safety_demo.LiveSafetyDemoError(
            "AMOLED ask_user capture failed.\n"
            + completed.stdout[-2000:]
            + completed.stderr[-2000:]
        )
    summary = live_safety_demo.load_json(summary_path)
    if not summary.get("ok"):
        raise live_safety_demo.LiveSafetyDemoError(f"AMOLED ask_user summary is not ok: {summary_path}")
    return Path(str(summary["jsonl_path"])), summary


def run_gnss_probe(args: argparse.Namespace, *, session_id: str, gnss_dir: Path, event_log: Path) -> tuple[dict[str, object] | None, dict[str, object]]:
    if args.location_event_json is not None:
        event = live_safety_demo.load_json(args.location_event_json)
        return event, {
            "source": "provided",
            "at_ok": True,
            "fix": bool(event.get("fix")),
            "selected_port": None,
        }

    report = sim7670_gnss_probe.run_probe(
        sim_ports=args.sim_ports,
        probe_all_sim_ports=args.probe_all_sim_ports,
        power_on=not args.no_gnss_power_on,
        warmup_seconds=args.gnss_warmup_seconds,
        poll_count=args.gnss_poll_count,
        poll_interval_seconds=args.gnss_poll_interval_seconds,
        output_dir=gnss_dir,
        event_log=event_log,
        write_event=False,
        device_id=live_safety_demo.CONNECTIVITY_ID,
    )
    summary = dict(report["summary"])
    summary["json_path"] = report["json_path"]
    summary["markdown_path"] = report["markdown_path"]
    if not summary.get("at_ok") and not args.allow_gnss_failure:
        raise live_safety_demo.LiveSafetyDemoError(f"SIM7670G GNSS probe failed AT gate: {report['markdown_path']}")
    return report.get("event"), summary


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    session_id = args.session_id or default_session_id()
    runtime_dir = args.runtime_dir
    event_log = args.event_log or (runtime_dir / f"{session_id}.events.jsonl")
    recording_dir = args.output_dir or (runtime_dir / "recordings" / session_id)
    amoled_dir = runtime_dir / "amoled"
    gnss_dir = runtime_dir / "gnss"

    try:
        if event_log.exists():
            raise live_safety_demo.LiveSafetyDemoError(f"Event log already exists: {event_log}")
        if recording_dir.exists():
            raise live_safety_demo.LiveSafetyDemoError(f"Recording directory already exists: {recording_dir}")

        amoled_jsonl, amoled_summary = run_amoled_capture(args, session_id=session_id, amoled_dir=amoled_dir)
        location_event, gnss_summary = run_gnss_probe(args, session_id=session_id, gnss_dir=gnss_dir, event_log=event_log)
        result = live_safety_demo.run_live_demo(
            amoled_jsonl=amoled_jsonl,
            location_event=location_event,
            event_log=event_log,
            recording_dir=recording_dir,
            session_id=session_id,
            gnss_at_ok=bool(gnss_summary.get("at_ok")),
            selected_gnss_port=str(gnss_summary.get("selected_port") or ""),
            allow_gnss_failure=args.allow_gnss_failure,
        )
    except live_safety_demo.LiveSafetyDemoError as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc), "session_id": session_id}, ensure_ascii=False, indent=2))
        else:
            print(f"FAIL demo v0.3 session={session_id}: {exc}", file=sys.stderr)
        return 2

    payload = {
        **result,
        "amoled": amoled_summary,
        "gnss": gnss_summary,
    }
    summary_path = runtime_dir / f"{session_id}.summary.json"
    payload["summary_path"] = str(summary_path)
    live_safety_demo.write_json(summary_path, payload)

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        status = "PASS" if payload["ok"] else "FAIL"
        print(f"{status} demo v0.3 live safety loop session={session_id}")
        print(f"Response: {payload['response']}")
        print(f"Event log: {payload['event_log']}")
        print(f"Recording: {payload['recording_dir']}")
        print(f"Quality: {payload['quality_report']['path']}")
        print(f"Replay: {payload['replay_report']['path']}")
        print(f"Summary: {summary_path}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

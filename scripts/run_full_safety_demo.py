"""Run the full Demo v0.5 Ego Link safety loop."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Callable, TypeVar

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pc_simulator import full_safety_demo, live_safety_demo
from scripts import run_demo_v0_3_live_safety_loop


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME = REPO_ROOT / "pc_simulator" / "runtime" / "demo_full"
T = TypeVar("T")


def default_session_id() -> str:
    return "demo-full-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--event-log", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None, help="Recording output directory.")
    parser.add_argument("--runtime-dir", type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument("--json", action="store_true")

    parser.add_argument("--amoled-jsonl", type=Path, default=None, help="Use an existing AMOLED JSONL capture.")
    parser.add_argument("--amoled-port", default="", help="Optional AMOLED USB Serial/JTAG port.")
    parser.add_argument("--amoled-wait-seconds", type=int, default=90)
    parser.add_argument("--amoled-retries", type=int, default=1)
    parser.add_argument("--wait-for-motion", action="store_true", help="Wait for a physical motion event.")
    parser.add_argument("--reset-amoled", action="store_true")

    parser.add_argument("--location-event-json", type=Path, default=None, help="Use an existing location_report JSON object.")
    parser.add_argument("--sim-port", dest="sim_ports", action="append", default=[])
    parser.add_argument("--probe-all-sim-ports", action="store_true")
    parser.add_argument("--no-gnss-power-on", action="store_true")
    parser.add_argument("--gnss-warmup-seconds", type=float, default=3.0)
    parser.add_argument("--gnss-poll-count", type=int, default=3)
    parser.add_argument("--gnss-poll-interval-seconds", type=float, default=2.0)
    parser.add_argument("--gnss-retries", type=int, default=1)
    parser.add_argument("--allow-gnss-failure", action="store_true")
    parser.add_argument("--require-real-gnss-fix", action="store_true")

    parser.add_argument(
        "--audio-mode",
        choices=sorted(full_safety_demo.VALID_AUDIO_MODES),
        default=full_safety_demo.AUDIO_MODE_MOCK,
        help="Use mock structured audio evidence or disable the v0.4 audio gate.",
    )
    return parser.parse_args(argv)


def run_with_retries(
    label: str,
    attempts: int,
    action: Callable[[], T],
) -> tuple[T, list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    total = max(1, attempts)
    for attempt in range(1, total + 1):
        try:
            value = action()
            records.append({"label": label, "attempt": attempt, "ok": True})
            return value, records
        except Exception as exc:
            records.append({"label": label, "attempt": attempt, "ok": False, "error": str(exc)})
            if attempt == total:
                raise full_safety_demo.FullSafetyDemoError(
                    f"{label} failed after {total} attempt(s): {exc}"
                ) from exc
    raise AssertionError("unreachable retry loop")


def run_amoled_step(args: argparse.Namespace, *, session_id: str, amoled_dir: Path) -> tuple[Path, dict[str, object]]:
    return run_demo_v0_3_live_safety_loop.run_amoled_capture(
        args,
        session_id=session_id,
        amoled_dir=amoled_dir,
    )


def run_gnss_step(
    args: argparse.Namespace,
    *,
    session_id: str,
    gnss_dir: Path,
    event_log: Path,
) -> tuple[dict[str, object] | None, dict[str, object]]:
    if args.location_event_json is not None:
        payload = full_safety_demo.load_json(args.location_event_json)
        embedded_event = payload.get("event")
        event = embedded_event if isinstance(embedded_event, dict) else payload
        report_summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        return event, {
            "source": "provided",
            "at_ok": bool(report_summary.get("at_ok", True)),
            "fix": bool(event.get("fix")),
            "selected_port": report_summary.get("selected_port") or event.get("port"),
            "json_path": str(args.location_event_json),
        }
    return run_demo_v0_3_live_safety_loop.run_gnss_probe(
        args,
        session_id=session_id,
        gnss_dir=gnss_dir,
        event_log=event_log,
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    session_id = args.session_id or default_session_id()
    runtime_dir = args.runtime_dir
    event_log = args.event_log or (runtime_dir / f"{session_id}.events.jsonl")
    recording_dir = args.output_dir or (runtime_dir / "recordings" / session_id)
    amoled_dir = runtime_dir / "amoled"
    gnss_dir = runtime_dir / "gnss"
    attempts: list[dict[str, Any]] = []

    try:
        if event_log.exists():
            raise full_safety_demo.FullSafetyDemoError(f"Event log already exists: {event_log}")
        if recording_dir.exists():
            raise full_safety_demo.FullSafetyDemoError(f"Recording directory already exists: {recording_dir}")

        (amoled_jsonl, amoled_summary), amoled_attempts = run_with_retries(
            "amoled_capture",
            args.amoled_retries,
            lambda: run_amoled_step(args, session_id=session_id, amoled_dir=amoled_dir),
        )
        attempts.extend(amoled_attempts)

        (location_event, gnss_summary), gnss_attempts = run_with_retries(
            "gnss_probe",
            args.gnss_retries,
            lambda: run_gnss_step(args, session_id=session_id, gnss_dir=gnss_dir, event_log=event_log),
        )
        attempts.extend(gnss_attempts)

        result = full_safety_demo.run_full_demo(
            amoled_jsonl=amoled_jsonl,
            location_event=location_event,
            event_log=event_log,
            recording_dir=recording_dir,
            session_id=session_id,
            gnss_at_ok=bool(gnss_summary.get("at_ok")),
            selected_gnss_port=str(gnss_summary.get("selected_port") or ""),
            allow_gnss_failure=args.allow_gnss_failure,
            require_real_gnss_fix=args.require_real_gnss_fix,
            audio_mode=args.audio_mode,
        )
    except (full_safety_demo.FullSafetyDemoError, live_safety_demo.LiveSafetyDemoError) as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc), "session_id": session_id, "attempts": attempts}, ensure_ascii=False, indent=2))
        else:
            print(f"FAIL full demo session={session_id}: {exc}", file=sys.stderr)
        return 2

    payload = {
        **result,
        "amoled": amoled_summary,
        "gnss": gnss_summary,
        "attempts": attempts,
    }
    summary_path = runtime_dir / f"{session_id}.summary.json"
    payload["summary_path"] = str(summary_path)
    full_safety_demo.write_json(summary_path, payload)

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        status = "PASS" if payload["ok"] else "FAIL"
        print(f"{status} full demo v0.5 session={session_id}")
        print(f"Event log: {payload['event_log']}")
        print(f"Recording: {payload['recording_dir']}")
        print(f"Quality: {payload['quality_report']['path']}")
        print(f"Replay: {payload['replay_report']['path']}")
        print(f"Summary: {summary_path}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

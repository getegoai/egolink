"""Generate bounded synthetic session recordings for data-flywheel dry-runs.

The generated data is intentionally marked synthetic-only. It can exercise the
recording, annotation, review, dataset-handoff, and experiment-plan plumbing,
but it is not field evidence and cannot support model performance claims.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import random
import re
import sys
from typing import Any, Mapping

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pc_simulator import session_annotations, session_recorder, training_candidate_store
from scripts import register_training_experiment, run_data_flywheel_pipeline


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "reports" / "synthetic_scenarios"
SYNTHETIC_SCHEMA_VERSION = "egolink.synthetic_scenario_run.v0.1"
SYNTHETIC_BUILDER_VERSION = "data-009.0"
SYNTHETIC_SOURCE_SCHEMA_VERSION = "egolink.synthetic_recording_source.v0.1"

SCENARIO_SPECS: dict[str, dict[str, Any]] = {
    "normal_walk": {
        "label": "safe",
        "risk_type": "none",
        "risk_score": 0.05,
        "confidence": 0.75,
        "impact_score": 0.04,
        "fall_score": 0.02,
        "stationary_seconds": 0.0,
        "recommended_action": "continue_monitoring",
    },
    "manual_sos": {
        "label": "needs_help",
        "risk_type": "manual_sos",
        "risk_score": 1.0,
        "confidence": 1.0,
        "impact_score": 0.08,
        "fall_score": 0.05,
        "stationary_seconds": 0.0,
        "recommended_action": "urgent_escalation",
    },
    "false_alarm": {
        "label": "false_alarm",
        "risk_type": "manual_sos",
        "risk_score": 0.45,
        "confidence": 0.65,
        "impact_score": 0.06,
        "fall_score": 0.03,
        "stationary_seconds": 0.0,
        "recommended_action": "ask_user",
    },
    "no_response": {
        "label": "no_response",
        "risk_type": "possible_fall",
        "risk_score": 0.82,
        "confidence": 0.7,
        "impact_score": 0.72,
        "fall_score": 0.78,
        "stationary_seconds": 45.0,
        "recommended_action": "ask_user",
    },
}
DEFAULT_SCENARIOS = tuple(SCENARIO_SPECS)
SPLIT_CYCLE = ("train", "validation", "test")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def iso_at(base: datetime, seconds: int) -> str:
    return (base + timedelta(seconds=seconds)).isoformat()


def epoch_ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def slug_id(value: object) -> str:
    text = str(value or "unknown").strip().lower()
    text = re.sub(r"[^a-z0-9_.-]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-._")
    return text or "unknown"


def timestamp_slug(value: str) -> str:
    return (
        value.replace("+00:00", "Z")
        .replace("+0000", "Z")
        .replace(":", "")
        .replace("-", "")
        .replace(".", "")
        .replace("T", "-")
    )


def default_run_id(generated_at: str) -> str:
    return f"synthetic-scenarios-{timestamp_slug(generated_at)[:16].rstrip('-')}"


def bounded_path(path: Path, *, base: Path | None = None) -> str:
    resolved = path.resolve()
    for root in [base, REPO_ROOT]:
        if root is None:
            continue
        try:
            return resolved.relative_to(root.resolve()).as_posix()
        except ValueError:
            continue
    return path.name


def event_base(
    *,
    device_id: str,
    event_type: str,
    seq: int,
    ts: datetime,
) -> dict[str, Any]:
    timestamp = ts.isoformat()
    return {
        "event_type": event_type,
        "device_id": device_id,
        "seq": seq,
        "ts": timestamp,
        "received_at": timestamp,
        "timestamp_ms": epoch_ms(ts),
    }


def jittered(value: float, rng: random.Random, *, spread: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return round(max(minimum, min(maximum, value + rng.uniform(-spread, spread))), 3)


def synthetic_motion_event(
    *,
    device_id: str,
    seq: int,
    ts: datetime,
    spec: Mapping[str, Any],
    rng: random.Random,
) -> dict[str, Any]:
    event = event_base(device_id=device_id, event_type="motion_event", seq=seq, ts=ts)
    event.update(
        {
            "role": "wearable_node",
            "bridge_source": "synthetic_scenario_generator",
            "source_availability": "bridge_uplink",
            "source_status": "synthetic_generated",
            "sensor_model": "synthetic_motion_v0",
            "payload": {
                "sensor_model": "synthetic_motion_v0",
                "imu_source": "synthetic_scenario_generator",
                "sample_hz": 25,
                "impact_score": jittered(float(spec["impact_score"]), rng, spread=0.025),
                "fall_score": jittered(float(spec["fall_score"]), rng, spread=0.025),
                "stationary_seconds": round(max(0.0, float(spec["stationary_seconds"]) + rng.uniform(-2.0, 2.0)), 2),
                "accel_mg": [
                    round(1000 + rng.uniform(-90, 90), 2),
                    round(rng.uniform(-70, 70), 2),
                    round(rng.uniform(-70, 70), 2),
                ],
                "gyro_mdps": [
                    round(rng.uniform(-1400, 1400), 2),
                    round(rng.uniform(-1400, 1400), 2),
                    round(rng.uniform(-1400, 1400), 2),
                ],
            },
        }
    )
    return event


def build_scenario_events(
    *,
    scenario: str,
    device_id: str,
    start_at: datetime,
    seq_base: int,
    rng: random.Random,
) -> list[dict[str, Any]]:
    spec = SCENARIO_SPECS[scenario]
    events = [
        synthetic_motion_event(
            device_id=device_id,
            seq=seq_base,
            ts=start_at,
            spec=spec,
            rng=rng,
        )
    ]
    motion_key = session_recorder.source_event_key(events[0])

    if scenario in {"manual_sos", "false_alarm"}:
        sos = event_base(device_id=device_id, event_type="sos_pressed", seq=seq_base + 1, ts=start_at + timedelta(seconds=1))
        sos.update({"source": "synthetic_button", "priority": "critical"})
        events.append(sos)
        safety_ref = session_recorder.source_event_key(sos)
    else:
        safety_ref = motion_key

    if scenario != "normal_walk":
        evaluation = event_base(
            device_id=device_id,
            event_type="safety_evaluation",
            seq=seq_base + 2,
            ts=start_at + timedelta(seconds=2),
        )
        evaluation.update(
            {
                "source": "synthetic_rule_router",
                "source_event_key": safety_ref,
                "source_event_type": "sos_pressed" if scenario in {"manual_sos", "false_alarm"} else "motion_event",
                "risk_type": spec["risk_type"],
                "risk_score": spec["risk_score"],
                "confidence": spec["confidence"],
                "recommended_action": spec["recommended_action"],
            }
        )
        events.append(evaluation)

        command = event_base(
            device_id=device_id,
            event_type="command_sent",
            seq=seq_base + 3,
            ts=start_at + timedelta(seconds=3),
        )
        command.update(
            {
                "source": "synthetic_rule_router",
                "cmd": "ask_user",
                "command_id": f"cmd-{seq_base + 3}",
            }
        )
        events.append(command)

    if scenario == "false_alarm":
        confirmation = event_base(
            device_id=device_id,
            event_type="user_confirmation",
            seq=seq_base + 4,
            ts=start_at + timedelta(seconds=4),
        )
        confirmation.update(
            {
                "source": "synthetic_user_response",
                "response": "safe",
                "outcome": "false_alarm",
            }
        )
        events.append(confirmation)

    return events


def add_synthetic_manifest_metadata(
    recording: dict[str, Any],
    *,
    run_id: str,
    scenario: str,
    sample_index: int,
    seed: int,
    training_requested: bool,
) -> None:
    manifest = recording["manifest"]
    manifest["firmware"] = {
        "name": "synthetic_scenario_generator",
        "version": SYNTHETIC_BUILDER_VERSION,
        "contract_version": session_recorder.DEFAULT_CONTRACT_VERSION,
    }
    manifest["synthetic"] = {
        "schema_version": SYNTHETIC_SOURCE_SCHEMA_VERSION,
        "builder_version": SYNTHETIC_BUILDER_VERSION,
        "synthetic_only": True,
        "run_id": run_id,
        "scenario": scenario,
        "sample_index": sample_index,
        "seed": seed,
        "training_requested": training_requested,
        "source": "scripts/generate_synthetic_scenarios.py",
        "allowed_use": "pipeline_dry_run_and_integration_testing",
        "not_allowed_use": [
            "field_evidence",
            "release_acceptance_metric",
            "model_accuracy_claim",
            "power_claim",
        ],
    }
    manifest.setdefault("sensor_sources", {})["synthetic_scenario_generator"] = {
        "availability": "synthetic",
        "status": "generated",
        "source": "scripts/generate_synthetic_scenarios.py",
        "note": "Synthetic source marker only; individual recording rows still use validator-supported availability values.",
    }
    manifest.setdefault("limitations", []).append(
        "Synthetic scenario recordings are for data-flywheel dry-runs only and are not hardware or field evidence."
    )


def annotate_generated_recording(
    recording_dir: Path,
    *,
    scenario: str,
    created_at: str,
    training_requested: bool,
) -> dict[str, Any]:
    targets = session_annotations.annotation_targets(recording_dir)
    motion_target = next((target for target in targets if target.get("frame_type") == "imu_motion"), None)
    target = motion_target or targets[0]
    return session_annotations.annotate_recording(
        recording_dir,
        source_event_key=target["source_event_key"],
        label=str(SCENARIO_SPECS[scenario]["label"]),
        annotator_type="rule",
        annotation_id=f"ann-{slug_id(scenario)}-{slug_id(recording_dir.name)}",
        created_at=created_at,
        training_allowed=training_requested,
        notes=(
            "Synthetic scenario label for pipeline dry-run only; explicit review is "
            "still required before dataset handoff."
        ),
    )


def generate_recordings(args: argparse.Namespace, *, run_dir: Path, generated_at: str) -> list[dict[str, Any]]:
    scenarios = list(args.scenario or DEFAULT_SCENARIOS)
    base_time = parse_utc(generated_at)
    recordings_root = run_dir / "recordings"
    rng = random.Random(args.seed)
    generated: list[dict[str, Any]] = []
    sample_counter = 0
    for scenario_index, scenario in enumerate(scenarios):
        for sample_index in range(1, args.samples_per_scenario + 1):
            sample_counter += 1
            session_id = f"{slug_id(args.run_id)}-{slug_id(scenario)}-{sample_index:03d}"
            start_at = base_time + timedelta(minutes=sample_counter)
            events = build_scenario_events(
                scenario=scenario,
                device_id=args.device_id,
                start_at=start_at,
                seq_base=1000 + scenario_index * 100 + sample_index * 10,
                rng=rng,
            )
            recording = session_recorder.build_recording(
                events,
                event_log=Path("synthetic_event_log.jsonl"),
                session_id=session_id,
                created_at=iso_at(start_at, 0),
            )
            add_synthetic_manifest_metadata(
                recording,
                run_id=args.run_id,
                scenario=scenario,
                sample_index=sample_index,
                seed=args.seed,
                training_requested=not args.no_training_request,
            )
            recording_dir = recordings_root / session_id
            session_recorder.write_recording(recording, recording_dir)
            annotation = annotate_generated_recording(
                recording_dir,
                scenario=scenario,
                created_at=iso_at(start_at, 5),
                training_requested=not args.no_training_request,
            )
            generated.append(
                {
                    "session_id": session_id,
                    "scenario": scenario,
                    "label": SCENARIO_SPECS[scenario]["label"],
                    "recording_ref": bounded_path(recording_dir, base=run_dir),
                    "annotation_id": annotation["annotation"]["annotation_id"],
                    "training_requested": not args.no_training_request,
                }
            )
    return generated


def pipeline_namespace(
    *,
    args: argparse.Namespace,
    run_dir: Path,
    db_path: Path,
    run_id: str,
    dataset_id: str,
    experiment_id: str,
    generated_at: str,
    recording_dirs: list[Path],
) -> argparse.Namespace:
    return argparse.Namespace(
        recording_dir=recording_dirs,
        db=db_path,
        run_id=run_id,
        dataset_id=dataset_id,
        generated_at=generated_at,
        output_root=run_dir / "data_flywheel_pipeline",
        data_flywheel_output_root=run_dir / "data_flywheel",
        dataset_output_root=run_dir / "training_datasets",
        experiment_output_root=run_dir / "training_experiments",
        experiment_id=experiment_id,
        model_track=args.model_track,
        candidate_model=args.candidate_model,
        baseline_model=args.baseline_model,
        require_ready=False,
        json=False,
    )


def run_pipeline(
    *,
    args: argparse.Namespace,
    run_dir: Path,
    db_path: Path,
    run_id: str,
    generated_at: str,
    recording_dirs: list[Path],
    suffix: str,
) -> dict[str, Any]:
    namespace = pipeline_namespace(
        args=args,
        run_dir=run_dir,
        db_path=db_path,
        run_id=f"{run_id}-{suffix}-pipeline",
        dataset_id=f"{run_id}-{suffix}-dataset",
        experiment_id=f"{run_id}-{suffix}-experiment",
        generated_at=generated_at,
        recording_dirs=recording_dirs,
    )
    return run_data_flywheel_pipeline.run_pipeline(namespace)


def review_generated_candidates(
    db_path: Path,
    *,
    session_ids: set[str],
    reviewed_at: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    queue = training_candidate_store.candidate_review_queue(
        db_path,
        limit=10000,
        generated_at=reviewed_at,
    )
    reviewed: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    split_index = 0
    for item in queue.get("records", []) or []:
        if not isinstance(item, dict) or item.get("session_id") not in session_ids:
            continue
        split_name = SPLIT_CYCLE[split_index % len(SPLIT_CYCLE)]
        split_index += 1
        try:
            action = training_candidate_store.review_candidate_record(
                db_path,
                record_id=str(item["record_id"]),
                decision="approve_for_training",
                reviewer="synthetic-generator",
                split_name=split_name,
                split_leakage_checked=True,
                privacy_reviewed=True,
                quality_reviewed=True,
                reviewed_at=reviewed_at,
                notes="Synthetic-only dry-run approval; not field evidence or release acceptance.",
            )
        except training_candidate_store.CandidateStoreError as exc:
            failed.append(
                {
                    "record_id": item.get("record_id"),
                    "session_id": item.get("session_id"),
                    "reason": str(exc),
                }
            )
        else:
            record = action["record"]
            reviewed.append(
                {
                    "record_id": record.get("record_id"),
                    "session_id": record.get("session_id"),
                    "state": record.get("state"),
                    "split_name": record.get("split_name"),
                    "training_allowed": bool(record.get("training_allowed")),
                }
            )
    return reviewed, failed


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def summarize_pipeline(payload: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not payload:
        return None
    data_flywheel = as_dict(payload.get("data_flywheel"))
    dataset = as_dict(payload.get("dataset_manifest"))
    experiment = as_dict(payload.get("training_experiment"))
    return {
        "run_id": payload.get("run_id"),
        "status": payload.get("status"),
        "recordings_requested": payload.get("recordings_requested"),
        "recordings_ingested": len(payload.get("recordings_ingested") or []),
        "records_total": as_dict(data_flywheel.get("counts")).get("records_total"),
        "pending_review": as_dict(data_flywheel.get("review_queue")).get("pending_records"),
        "dataset_status": dataset.get("status"),
        "eligible_records": as_dict(dataset.get("counts")).get("eligible_records"),
        "experiment_status": experiment.get("status"),
        "runner_ready": as_dict(experiment.get("runner")).get("ready_for_handoff"),
        "paths": as_dict(payload.get("paths")),
    }


def derive_status(
    *,
    initial_pipeline: Mapping[str, Any] | None,
    reviewed_pipeline: Mapping[str, Any] | None,
    review_failures: list[dict[str, Any]],
) -> str:
    if review_failures:
        return "review_failed"
    if reviewed_pipeline and reviewed_pipeline.get("status") == "ready_for_training_handoff":
        return "synthetic_ready_for_runner"
    if initial_pipeline:
        return str(initial_pipeline.get("status") or "generated")
    return "generated"


def render_markdown(payload: Mapping[str, Any]) -> str:
    counts = as_dict(payload.get("counts"))
    pipelines = as_dict(payload.get("pipelines"))
    review = as_dict(payload.get("synthetic_review"))
    paths = as_dict(payload.get("paths"))
    lines = [
        "# Ego Link Synthetic Scenario Run",
        "",
        f"- Run ID: {payload.get('run_id', 'unknown')}",
        f"- Generated at: {payload.get('generated_at', 'unknown')}",
        f"- Status: {payload.get('status', 'unknown')}",
        f"- Synthetic only: {payload.get('synthetic_only', True)}",
        f"- Scenarios: {', '.join(payload.get('scenarios', []) or [])}",
        f"- Recordings: {counts.get('recordings', 0)}",
        f"- Training requested: {counts.get('training_requested', 0)}",
        "",
        "## Pipeline",
        "",
    ]
    initial = as_dict(pipelines.get("initial"))
    if initial:
        lines.append(
            f"- Initial: {initial.get('status', 'unknown')} / records {initial.get('records_total', 0)} / "
            f"pending review {initial.get('pending_review', 0)}"
        )
    else:
        lines.append("- Initial: not run")
    reviewed = as_dict(pipelines.get("reviewed"))
    if reviewed:
        lines.append(
            f"- Reviewed: {reviewed.get('status', 'unknown')} / eligible {reviewed.get('eligible_records', 0)} / "
            f"experiment {reviewed.get('experiment_status', 'unknown')}"
        )
    else:
        lines.append("- Reviewed: not run")
    lines += [
        "",
        "## Synthetic Review",
        "",
        f"- Reviewed records: {len(review.get('reviewed_records') or [])}",
        f"- Failed reviews: {len(review.get('failed_reviews') or [])}",
        "",
        "## Artifacts",
        "",
        f"- Summary JSON: {paths.get('synthetic_scenario_run_json', 'unknown')}",
        f"- Summary Markdown: {paths.get('synthetic_scenario_run_markdown', 'unknown')}",
        "",
        "## Non-Claims",
        "",
    ]
    for item in payload.get("non_claims", []) or []:
        lines.append(f"- {item}")
    lines += [
        "",
        "This summary contains bounded synthetic run status only. It does not contain raw candidate records, candidate DB paths, private coordinates, runtime JSONL logs, model artifacts, or measured model/power results.",
        "",
    ]
    return "\n".join(lines)


def write_report(payload: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "synthetic_scenario_run.json"
    markdown_path = output_dir / "synthetic_scenario_run.md"
    written = dict(payload)
    written["paths"] = {
        "synthetic_scenario_run_json": bounded_path(json_path),
        "synthetic_scenario_run_markdown": bounded_path(markdown_path),
    }
    json_path.write_text(json.dumps(written, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(written), encoding="utf-8")
    return written


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate bounded synthetic scenarios for data-flywheel dry-runs.")
    parser.add_argument("--run-id", help="Stable synthetic run directory name.")
    parser.add_argument("--generated-at", help="UTC ISO timestamp for deterministic reports.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--db", type=Path, help="Synthetic candidate SQLite DB. Defaults inside the run directory.")
    parser.add_argument("--device-id", default="ego-link-synth-001")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--samples-per-scenario", type=int, default=1)
    parser.add_argument("--scenario", action="append", choices=tuple(SCENARIO_SPECS), help="Scenario to generate.")
    parser.add_argument("--no-training-request", action="store_true", help="Keep annotations collection-only.")
    parser.add_argument("--run-pipeline", action="store_true", help="Ingest generated recordings through DATA-006.")
    parser.add_argument(
        "--review-synthetic",
        action="store_true",
        help="Explicitly approve generated synthetic candidates for a dry-run handoff.",
    )
    parser.add_argument(
        "--model-track",
        default=register_training_experiment.DEFAULT_MODEL_TRACK,
        choices=("motionnet", "context_router", "audiogate", "visiongate"),
    )
    parser.add_argument("--candidate-model", default=register_training_experiment.DEFAULT_CANDIDATE_MODEL)
    parser.add_argument("--baseline-model", default=register_training_experiment.DEFAULT_BASELINE_MODEL)
    parser.add_argument("--json", action="store_true", help="Print the bounded synthetic run JSON.")
    args = parser.parse_args(argv)
    if args.samples_per_scenario < 1:
        parser.error("--samples-per-scenario must be >= 1")
    generated_at = args.generated_at or utc_now()
    args.generated_at = generated_at
    args.run_id = args.run_id or default_run_id(generated_at)
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run_dir = args.output_root / args.run_id
    db_path = args.db or (run_dir / "synthetic_candidates.db")
    recordings = generate_recordings(args, run_dir=run_dir, generated_at=args.generated_at)
    recording_dirs = [run_dir / item["recording_ref"] for item in recordings]

    initial_pipeline: dict[str, Any] | None = None
    reviewed_pipeline: dict[str, Any] | None = None
    reviewed_records: list[dict[str, Any]] = []
    failed_reviews: list[dict[str, Any]] = []

    if args.run_pipeline or args.review_synthetic:
        initial_pipeline = run_pipeline(
            args=args,
            run_dir=run_dir,
            db_path=db_path,
            run_id=args.run_id,
            generated_at=args.generated_at,
            recording_dirs=recording_dirs,
            suffix="initial",
        )

    if args.review_synthetic:
        reviewed_records, failed_reviews = review_generated_candidates(
            db_path,
            session_ids={str(item["session_id"]) for item in recordings},
            reviewed_at=args.generated_at,
        )
        if not failed_reviews:
            reviewed_pipeline = run_pipeline(
                args=args,
                run_dir=run_dir,
                db_path=db_path,
                run_id=args.run_id,
                generated_at=args.generated_at,
                recording_dirs=[],
                suffix="reviewed",
            )

    payload = {
        "schema_version": SYNTHETIC_SCHEMA_VERSION,
        "builder_version": SYNTHETIC_BUILDER_VERSION,
        "run_id": args.run_id,
        "generated_at": args.generated_at,
        "status": derive_status(
            initial_pipeline=initial_pipeline,
            reviewed_pipeline=reviewed_pipeline,
            review_failures=failed_reviews,
        ),
        "synthetic_only": True,
        "seed": args.seed,
        "scenarios": sorted({str(item["scenario"]) for item in recordings}),
        "counts": {
            "recordings": len(recordings),
            "training_requested": sum(1 for item in recordings if item.get("training_requested")),
            "reviewed_records": len(reviewed_records),
        },
        "recordings": recordings,
        "candidate_store": {
            "written": bool(initial_pipeline),
            "db_ref": db_path.name,
            "db_path_exported": False,
        },
        "pipelines": {
            "initial": summarize_pipeline(initial_pipeline),
            "reviewed": summarize_pipeline(reviewed_pipeline),
        },
        "synthetic_review": {
            "explicit_review_requested": bool(args.review_synthetic),
            "reviewed_records": reviewed_records,
            "failed_reviews": failed_reviews,
        },
        "non_claims": [
            "Synthetic scenarios are not hardware, field, or user evidence.",
            "Synthetic review is a dry-run gate exercise, not release acceptance.",
            "No model training has run.",
            "No model has been evaluated or deployed.",
            "No model accuracy, false-positive rate, latency, footprint, or power impact is claimed.",
            "No firmware, public protocol, Message Hub ingest, or on-device inference behavior changed.",
        ],
    }
    written = write_report(payload, run_dir)

    if args.json:
        print(json.dumps(written, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Synthetic scenarios: {written['status']}")
        print(f"Report: {run_dir / 'synthetic_scenario_run.md'}")
    return 1 if failed_reviews else 0


if __name__ == "__main__":
    raise SystemExit(main())

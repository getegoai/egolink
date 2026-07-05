"""Collect bounded D1 post-run evidence into one local summary.

This command is the normal "back from the field" entry point for D1. It reads
the Message Hub, builds existing Web/API, power, D1 demo, and data-flywheel
reports, and writes one summary that points at the artifacts. It does not
contact hardware, send device commands, deploy to the VPS, train a model, or
copy raw training data.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Mapping

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import analyze_power_curve
from scripts import build_d1_demo_report
from scripts import register_training_experiment
from scripts import run_data_flywheel_pipeline
from scripts import validate_d1_web_api


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "reports" / "d1_postrun"
DEFAULT_DEVICE_ID = "ego-link-r1-connectivity-001"
SCHEMA_VERSION = "egolink.d1_postrun_collection.v0.1"
BUILDER_VERSION = "data-008.0"
SUMMARY_JSON = "d1_postrun_collection_summary.json"
SUMMARY_MARKDOWN = "d1_postrun_collection_summary.md"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def compact_utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def bounded_error(reason: str, exc: BaseException) -> dict[str, Any]:
    return {
        "status": "error",
        "reason": reason,
        "error_type": type(exc).__name__,
        "message": str(exc),
    }


def web_api_summary(report: Mapping[str, Any] | None, error_summary: Mapping[str, Any] | None) -> dict[str, Any]:
    if error_summary:
        return dict(error_summary)
    if not report:
        return {"status": "skipped", "reason": "web_api_report_missing"}
    d1 = as_dict(report.get("d1"))
    return {
        "status": "completed",
        "result": report.get("result"),
        "device_id": report.get("device_id"),
        "d1_status": d1.get("status"),
        "report_path": report.get("report_path"),
        "markdown_report_path": report.get("markdown_report_path"),
        "warnings": list(report.get("warnings") or []),
        "errors": list(report.get("errors") or []),
    }


def power_summary(
    report: Mapping[str, Any] | None,
    status: Mapping[str, Any],
    *,
    export_path: Path | None,
    message_test_run_id: str | None,
) -> dict[str, Any]:
    if not report:
        summary = dict(status)
        summary["message_test_run_id"] = message_test_run_id
        summary["export_path"] = str(export_path) if export_path else None
        return summary
    result = as_dict(report.get("result"))
    return {
        "status": "completed",
        "result": result.get("status"),
        "message_test_run_id": message_test_run_id or as_dict(report.get("source")).get("test_run_id"),
        "export_path": str(export_path) if export_path else as_dict(report.get("source")).get("input_path"),
        "report_path": report.get("report_path"),
        "markdown_report_path": report.get("markdown_report_path"),
        "duration_hours": report.get("duration_hours"),
        "counts": as_dict(report.get("counts")),
        "warnings": list(result.get("warnings") or []),
        "errors": list(result.get("errors") or []),
    }


def d1_demo_summary(report: Mapping[str, Any] | None, error_summary: Mapping[str, Any] | None) -> dict[str, Any]:
    if error_summary:
        return dict(error_summary)
    if not report:
        return {"status": "skipped", "reason": "web_api_report_missing"}
    return {
        "status": "completed",
        "result": report.get("result"),
        "ready_for_founder_review": bool(report.get("ready_for_founder_review")),
        "report_path": report.get("report_path"),
        "markdown_report_path": report.get("markdown_report_path"),
    }


def data_pipeline_summary(report: Mapping[str, Any] | None, error_summary: Mapping[str, Any] | None) -> dict[str, Any]:
    if error_summary:
        return dict(error_summary)
    if not report:
        return {"status": "skipped", "reason": "data_flywheel_pipeline_skipped"}
    experiment = as_dict(report.get("training_experiment"))
    return {
        "status": report.get("status"),
        "run_id": report.get("run_id"),
        "recordings_requested": report.get("recordings_requested"),
        "recordings_ingested": len(as_list(report.get("recordings_ingested"))),
        "report_path": as_dict(report.get("paths")).get("data_flywheel_pipeline_json"),
        "markdown_report_path": as_dict(report.get("paths")).get("data_flywheel_pipeline_markdown"),
        "data_flywheel_status_path": as_dict(as_dict(report.get("data_flywheel")).get("paths")).get(
            "data_flywheel_status_json"
        ),
        "dataset_manifest_path": as_dict(as_dict(report.get("dataset_manifest")).get("paths")).get(
            "training_dataset_manifest_json"
        ),
        "training_experiment": {
            "status": experiment.get("status"),
            "reason": experiment.get("reason"),
            "experiment_id": experiment.get("experiment_id"),
            "report_path": as_dict(experiment.get("paths")).get("training_experiment_plan_json"),
        },
        "next_step": report.get("next_step"),
    }


def collect_web_api(
    *,
    hub_url: str,
    token: str | None,
    output_dir: Path,
    review_id: str,
    device_id: str,
    timeout: float,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    try:
        report = validate_d1_web_api.run_d1_web_api_gate(
            hub_url=hub_url,
            token=token,
            output_dir=output_dir,
            review_id=review_id,
            device_id=device_id,
            timeout=timeout,
        )
    except Exception as exc:  # Keep the post-run summary writeable when the hub is down.
        return None, bounded_error("d1_web_api_gate_failed", exc)
    return report, None


def collect_power_curve(
    args: argparse.Namespace,
    *,
    token: str | None,
    output_dir: Path,
    created_at: str,
) -> tuple[dict[str, Any] | None, dict[str, Any], Path | None]:
    if args.skip_power:
        return None, {"status": "skipped", "reason": "skip_power_requested"}, None
    if args.power_export and args.message_test_run_id:
        return (
            None,
            {"status": "error", "reason": "power_export_and_message_test_run_id_are_mutually_exclusive"},
            None,
        )
    if args.power_export:
        export_path = args.power_export
    elif args.message_test_run_id:
        output_dir.mkdir(parents=True, exist_ok=True)
        export_path = output_dir / "test_run_export.json"
        try:
            export = analyze_power_curve.fetch_message_hub_export(
                hub_url=args.hub_url,
                test_run_id=args.message_test_run_id,
                token=token,
                timeout=args.timeout,
            )
            analyze_power_curve.write_json(export_path, export)
        except analyze_power_curve.PowerCurveError as exc:
            return None, bounded_error("message_hub_test_run_export_failed", exc), export_path
    else:
        return (
            None,
            {"status": "skipped", "reason": "message_test_run_id_or_power_export_required"},
            None,
        )

    try:
        report = analyze_power_curve.analyze_power_curve(
            input_path=export_path,
            output_dir=output_dir,
            min_duration_hours=args.min_duration_hours,
            battery_capacity_mah=args.battery_capacity_mah,
            target_hours=args.target_hours,
            usable_capacity_factor=args.usable_capacity_factor,
            created_at=created_at,
        )
    except analyze_power_curve.PowerCurveError as exc:
        return None, bounded_error("power_curve_analysis_failed", exc), export_path
    return report, {"status": as_dict(report.get("result")).get("status") or "completed"}, export_path


def collect_d1_demo(
    *,
    web_report: Mapping[str, Any] | None,
    power_report: Mapping[str, Any] | None,
    output_dir: Path,
    run_id: str,
    created_at: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not web_report:
        return None, {"status": "skipped", "reason": "web_api_report_missing"}
    try:
        report = build_d1_demo_report.build_d1_demo_report(
            web_api_report_path=Path(str(web_report["report_path"])),
            power_curve_report_path=Path(str(power_report["report_path"])) if power_report else None,
            output_dir=output_dir,
            report_id=run_id,
            created_at=created_at,
        )
    except Exception as exc:
        return None, bounded_error("d1_demo_report_failed", exc)
    return report, None


def collect_data_pipeline(
    args: argparse.Namespace,
    *,
    run_id: str,
    created_at: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if args.skip_data_flywheel:
        return None, {"status": "skipped", "reason": "skip_data_flywheel_requested"}
    pipeline_run_id = args.data_pipeline_run_id or f"{run_id}-data-pipeline"
    namespace = argparse.Namespace(
        recording_dir=list(args.recording_dir or []),
        db=args.db,
        run_id=pipeline_run_id,
        dataset_id=args.dataset_id or f"{run_id}-dataset",
        generated_at=created_at,
        output_root=args.data_flywheel_pipeline_output_root,
        data_flywheel_output_root=args.data_flywheel_output_root,
        dataset_output_root=args.dataset_output_root,
        experiment_output_root=args.experiment_output_root,
        experiment_id=args.experiment_id,
        model_track=args.model_track,
        candidate_model=args.candidate_model,
        baseline_model=args.baseline_model,
        require_ready=False,
        json=False,
    )
    try:
        report = run_data_flywheel_pipeline.run_pipeline(namespace)
    except Exception as exc:
        return None, bounded_error("data_flywheel_pipeline_failed", exc)
    return report, None


def derive_result(components: Mapping[str, Mapping[str, Any]]) -> tuple[str, list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    web_api = as_dict(components.get("web_api"))
    web_result = str(web_api.get("result") or web_api.get("status") or "unknown")
    if web_api.get("status") == "error":
        errors.append(f"web_api:{web_api.get('reason', 'error')}")
    elif web_result == "FAIL":
        errors.append("web_api:result_fail")
    elif web_result != "PASS":
        warnings.append(f"web_api:{web_result}")

    power = as_dict(components.get("power_curve"))
    power_result = str(power.get("result") or power.get("status") or "unknown")
    if power_result != "PASS":
        warnings.append(f"power_curve:{power.get('reason') or power_result}")

    d1_demo = as_dict(components.get("d1_demo"))
    demo_result = str(d1_demo.get("result") or d1_demo.get("status") or "unknown")
    if demo_result != "PASS":
        warnings.append(f"d1_demo:{d1_demo.get('reason') or demo_result}")

    data_pipeline = as_dict(components.get("data_flywheel_pipeline"))
    data_status = str(data_pipeline.get("status") or "unknown")
    if data_status != "ready_for_training_handoff":
        warnings.append(f"data_flywheel_pipeline:{data_pipeline.get('reason') or data_status}")

    result = "FAIL" if errors else ("WARN" if warnings else "PASS")
    return result, errors, warnings


def derive_next_steps(components: Mapping[str, Mapping[str, Any]], result: str) -> list[str]:
    steps: list[str] = []
    web_api = as_dict(components.get("web_api"))
    if web_api.get("status") == "error" or web_api.get("result") == "FAIL":
        steps.append("Fix or wait for the D1 Web/API live surface before treating this run as reviewable.")

    power = as_dict(components.get("power_curve"))
    power_result = str(power.get("result") or power.get("status") or "")
    if power_result in {"skipped", ""}:
        steps.append("Rerun with --message-test-run-id or --power-export to bind a power curve report.")
    elif power_result != "PASS":
        steps.append("Inspect the power report; WARN/FAIL is allowed for a shakedown but must explain the gap.")

    data_pipeline = as_dict(components.get("data_flywheel_pipeline"))
    data_status = str(data_pipeline.get("status") or "")
    if data_status == "needs_recordings":
        steps.append("Attach explicit --recording-dir inputs when there are reviewed session recordings to ingest.")
    elif data_status == "needs_review":
        steps.append("Review pending candidates, then rerun the data-flywheel pipeline.")
    elif data_status and data_status != "ready_for_training_handoff":
        steps.append(str(data_pipeline.get("next_step") or "Continue the next DATA/TRAIN task."))

    if result != "FAIL":
        steps.append("Sync curated summaries to the VPS Dashboard when the run should be visible remotely.")
    return steps or ["No immediate follow-up is required for this collector result."]


def artifact_paths(components: Mapping[str, Mapping[str, Any]], summary_json: Path, summary_md: Path) -> dict[str, Any]:
    data_pipeline = as_dict(components.get("data_flywheel_pipeline"))
    training_experiment = as_dict(data_pipeline.get("training_experiment"))
    return {
        "postrun_summary_json": str(summary_json),
        "postrun_summary_markdown": str(summary_md),
        "web_api_report": as_dict(components.get("web_api")).get("report_path"),
        "power_curve_report": as_dict(components.get("power_curve")).get("report_path"),
        "message_hub_export": as_dict(components.get("power_curve")).get("export_path"),
        "d1_demo_report": as_dict(components.get("d1_demo")).get("report_path"),
        "data_flywheel_pipeline": data_pipeline.get("report_path"),
        "data_flywheel_status": data_pipeline.get("data_flywheel_status_path"),
        "training_dataset_manifest": data_pipeline.get("dataset_manifest_path"),
        "training_experiment_plan": training_experiment.get("report_path"),
    }


def render_markdown(summary: Mapping[str, Any]) -> str:
    components = as_dict(summary.get("components"))
    lines = [
        "# D1 Post-Run Collection",
        "",
        f"- Run ID: {summary.get('run_id', 'unknown')}",
        f"- Created at: {summary.get('created_at', 'unknown')}",
        f"- Result: {summary.get('result', 'unknown')}",
        f"- Device: {summary.get('device_id', 'unknown')}",
        f"- Hub: {summary.get('hub_url', 'unknown')}",
        f"- Message test run: {summary.get('message_test_run_id') or 'not provided'}",
        "",
        "## Components",
        "",
    ]
    for name in ("web_api", "power_curve", "d1_demo", "data_flywheel_pipeline"):
        component = as_dict(components.get(name))
        status = component.get("result") or component.get("status") or "unknown"
        reason = component.get("reason")
        suffix = f" ({reason})" if reason else ""
        lines.append(f"- {name}: {status}{suffix}")

    lines += ["", "## Artifacts", ""]
    for name, path in as_dict(summary.get("artifacts")).items():
        lines.append(f"- {name}: {path or 'not available'}")

    lines += ["", "## Next Steps", ""]
    lines.extend(f"- {step}" for step in as_list(summary.get("next_steps")))

    lines += ["", "## Boundaries", ""]
    lines.extend(f"- {item}" for item in as_list(summary.get("boundaries")))
    lines += ["", "## Non-Claims", ""]
    lines.extend(f"- {item}" for item in as_list(summary.get("non_claims")))
    lines.append("")
    return "\n".join(lines)


def collect_postrun(args: argparse.Namespace) -> dict[str, Any]:
    created_at = args.created_at or utc_now()
    run_id = args.run_id or f"D1-POSTRUN-{compact_utc_now()}"
    output_dir = args.output_root / run_id
    token = validate_d1_web_api.read_token(args.token_file)

    web_report, web_error = collect_web_api(
        hub_url=args.hub_url,
        token=token,
        output_dir=args.web_api_output_dir or (validate_d1_web_api.DEFAULT_OUTPUT_ROOT / run_id),
        review_id=args.web_review_id or f"{run_id}-web",
        device_id=args.device_id,
        timeout=args.timeout,
    )
    power_report, power_status, export_path = collect_power_curve(
        args,
        token=token,
        output_dir=args.power_output_dir or (analyze_power_curve.DEFAULT_OUTPUT_ROOT / run_id),
        created_at=created_at,
    )
    demo_report, demo_error = collect_d1_demo(
        web_report=web_report,
        power_report=power_report,
        output_dir=args.d1_demo_output_dir or (build_d1_demo_report.DEFAULT_OUTPUT_ROOT / run_id),
        run_id=run_id,
        created_at=created_at,
    )
    data_report, data_error = collect_data_pipeline(args, run_id=run_id, created_at=created_at)

    components = {
        "web_api": web_api_summary(web_report, web_error),
        "power_curve": power_summary(
            power_report,
            power_status,
            export_path=export_path,
            message_test_run_id=args.message_test_run_id,
        ),
        "d1_demo": d1_demo_summary(demo_report, demo_error),
        "data_flywheel_pipeline": data_pipeline_summary(data_report, data_error),
    }
    result, errors, warnings = derive_result(components)

    summary_json = output_dir / SUMMARY_JSON
    summary_md = output_dir / SUMMARY_MARKDOWN
    summary: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "builder_version": BUILDER_VERSION,
        "run_id": run_id,
        "created_at": created_at,
        "result": result,
        "errors": errors,
        "warnings": warnings,
        "hub_url": args.hub_url.rstrip("/"),
        "device_id": args.device_id,
        "message_test_run_id": args.message_test_run_id,
        "components": components,
        "scope": {
            "hardware_contacted": False,
            "firmware_changed": False,
            "serial_ports_opened": False,
            "commands_sent": False,
            "deploy_run": False,
            "gitlab_modified": False,
            "model_training_started": False,
            "model_deployed": False,
            "secrets_persisted": False,
        },
        "boundaries": [
            "Read-only Message Hub collection plus local report generation only.",
            "No hardware, serial port, firmware, Message Hub command, deployment, or GitLab mutation is performed.",
            "The data-flywheel step ingests only recording directories explicitly passed with --recording-dir.",
            "Dashboard state and curated summaries are not raw training data.",
        ],
        "non_claims": [
            "No location accuracy is claimed.",
            "No battery life or 24h PWR-001 pass is claimed.",
            "No GNSS acceptance, product readiness, calling, or SMS behavior is claimed.",
            "No model training, evaluation, deployment, accuracy, latency, footprint, or power impact is claimed.",
        ],
    }
    summary["next_steps"] = derive_next_steps(components, result)
    summary["artifacts"] = artifact_paths(components, summary_json, summary_md)
    write_json(summary_json, summary)
    summary_md.parent.mkdir(parents=True, exist_ok=True)
    summary_md.write_text(render_markdown(summary), encoding="utf-8")
    return summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", help="Local post-run collection ID.")
    parser.add_argument("--created-at", help="UTC ISO timestamp for deterministic reports.")
    parser.add_argument("--hub-url", default=validate_d1_web_api.DEFAULT_HUB_URL)
    parser.add_argument("--token-file", type=Path, default=validate_d1_web_api.DEFAULT_TOKEN_FILE)
    parser.add_argument("--device-id", default=DEFAULT_DEVICE_ID)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--web-review-id", help="Review ID for the D1 Web/API report.")
    parser.add_argument("--web-api-output-dir", type=Path)
    parser.add_argument("--message-test-run-id", help="Message Hub test_run_id to export for PWR-001 analysis.")
    parser.add_argument("--power-export", type=Path, help="Existing Message Hub test_run_export.json to analyze.")
    parser.add_argument("--power-output-dir", type=Path)
    parser.add_argument("--min-duration-hours", type=float, default=2.0)
    parser.add_argument("--battery-capacity-mah", type=float)
    parser.add_argument("--target-hours", type=float, default=analyze_power_curve.DEFAULT_TARGET_HOURS)
    parser.add_argument("--usable-capacity-factor", type=float, default=analyze_power_curve.DEFAULT_USABLE_CAPACITY_FACTOR)
    parser.add_argument("--skip-power", action="store_true")
    parser.add_argument("--d1-demo-output-dir", type=Path)
    parser.add_argument("--skip-data-flywheel", action="store_true")
    parser.add_argument("--recording-dir", action="append", type=Path)
    parser.add_argument("--db", type=Path, default=run_data_flywheel_pipeline.DEFAULT_DB)
    parser.add_argument("--data-pipeline-run-id")
    parser.add_argument("--dataset-id")
    parser.add_argument("--data-flywheel-pipeline-output-root", type=Path, default=run_data_flywheel_pipeline.DEFAULT_PIPELINE_ROOT)
    parser.add_argument("--data-flywheel-output-root", type=Path, default=run_data_flywheel_pipeline.DEFAULT_DATA_FLYWHEEL_ROOT)
    parser.add_argument("--dataset-output-root", type=Path, default=run_data_flywheel_pipeline.DEFAULT_DATASET_ROOT)
    parser.add_argument("--experiment-output-root", type=Path, default=run_data_flywheel_pipeline.DEFAULT_EXPERIMENT_ROOT)
    parser.add_argument("--experiment-id")
    parser.add_argument(
        "--model-track",
        default=register_training_experiment.DEFAULT_MODEL_TRACK,
        choices=("motionnet", "context_router", "audiogate", "visiongate"),
    )
    parser.add_argument("--candidate-model", default=register_training_experiment.DEFAULT_CANDIDATE_MODEL)
    parser.add_argument("--baseline-model", default=register_training_experiment.DEFAULT_BASELINE_MODEL)
    parser.add_argument("--require-pass", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    summary = collect_postrun(args)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"{summary['result']} D1 post-run collection: {summary['artifacts']['postrun_summary_markdown']}")
    if summary["result"] == "FAIL":
        return 1
    if args.require_pass and summary["result"] != "PASS":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

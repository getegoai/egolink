"""Collect bounded D1 post-run evidence into one local summary.

This command is the normal "back from the field" entry point for D1. It reads
the Message Hub, binds the local field-observation report/status when present,
builds existing Web/API, power, D1 demo, D1 training-readiness, D1 labeling
intake/queue/review-packet/decision-template, and data-flywheel reports, and
writes one summary that points at the artifacts. It does not contact hardware,
send device commands, deploy to the VPS, train a model, or copy raw training
data.
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
from scripts import assess_d1_training_readiness
from scripts import build_d1_labeling_intake
from scripts import build_training_handoff_bundle
from scripts import convert_d1_field_samples_to_power_export
from scripts import build_d1_demo_report
from scripts import build_d1_labeling_decision_template
from scripts import build_d1_labeling_review_packet
from scripts import create_training_job_plan
from scripts import export_training_feature_manifest
from scripts import observe_d1_field_run
from scripts import register_training_experiment
from scripts import run_data_flywheel_pipeline
from scripts import run_training_baseline_eval
from scripts import run_training_experiment_preflight
from scripts import run_training_runner_dry_run
from scripts import summarize_d1_labeling_queue
from scripts import validate_d1_web_api
from scripts import validate_d1_labeling_decision_template


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "reports" / "d1_postrun"
DEFAULT_DEVICE_ID = "ego-link-r1-connectivity-001"
SCHEMA_VERSION = "egolink.d1_postrun_collection.v0.12"
BUILDER_VERSION = "data-032.0"
SUMMARY_JSON = "d1_postrun_collection_summary.json"
SUMMARY_MARKDOWN = "d1_postrun_collection_summary.md"
READY_DATA_PIPELINE_STATUS = "ready_for_training_handoff"
READY_BASELINE_STATUSES = {"baseline_eval_complete", "synthetic_baseline_eval_complete"}
READY_HANDOFF_STATUS = "ready_for_training_server_handoff"
SYNTHETIC_HANDOFF_STATUS = "synthetic_handoff_dry_run_only"
READY_JOB_STATUS = create_training_job_plan.READY_JOB_STATUS
SYNTHETIC_JOB_STATUS = create_training_job_plan.SYNTHETIC_JOB_STATUS


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


def read_json_file(path: Path, *, label: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} JSON must be an object")
    return payload


def resolve_path_reference(value: object) -> Path | None:
    if value in (None, ""):
        return None
    path = Path(str(value))
    return path if path.is_absolute() else REPO_ROOT / path


def bounded_error(reason: str, exc: BaseException) -> dict[str, Any]:
    return {
        "status": "error",
        "reason": reason,
        "error_type": type(exc).__name__,
        "message": str(exc),
    }


def field_observation_summary(
    report: Mapping[str, Any] | None,
    status: Mapping[str, Any] | None,
    error_summary: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if error_summary:
        return dict(error_summary)
    if report:
        summary = as_dict(report.get("summary"))
        return {
            "status": "completed",
            "result": report.get("result"),
            "run_id": report.get("run_id"),
            "observer_version": report.get("observer_version"),
            "sample_count": summary.get("sample_count"),
            "successful_sample_count": summary.get("successful_sample_count"),
            "fetch_error_count": summary.get("fetch_error_count"),
            "last_seq": summary.get("last_seq"),
            "last_location_upload_at": summary.get("last_location_upload_at"),
            "max_freshness_s": summary.get("max_freshness_s"),
            "raw_post_success_delta": summary.get("raw_post_success_delta"),
            "location_event_count_delta": summary.get("location_event_count_delta"),
            "power_sample_count_delta": summary.get("power_sample_count_delta"),
            "report_path": report.get("report_path"),
            "markdown_report_path": report.get("markdown_report_path"),
            "samples_path": report.get("samples_path"),
            "status_path": report.get("status_path"),
            "warnings": list(report.get("warnings") or []),
            "errors": list(report.get("errors") or []),
        }
    if status:
        return {
            "status": status.get("status") or "running",
            "result": status.get("result"),
            "run_id": status.get("run_id"),
            "observer_version": status.get("observer_version"),
            "sample_count": status.get("sample_count"),
            "successful_sample_count": status.get("successful_sample_count"),
            "fetch_error_count": status.get("fetch_error_count"),
            "last_seq": status.get("latest_seq"),
            "last_location_upload_at": status.get("latest_location_upload_at"),
            "max_freshness_s": status.get("latest_freshness_s"),
            "report_path": status.get("report_path"),
            "markdown_report_path": status.get("markdown_report_path"),
            "samples_path": status.get("samples_path"),
            "status_path": status.get("status_path"),
        }
    return {"status": "skipped", "reason": "field_observation_report_missing"}


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


def training_readiness_summary(
    report: Mapping[str, Any] | None,
    error_summary: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if error_summary:
        return dict(error_summary)
    if not report:
        return {"status": "skipped", "reason": "training_readiness_not_run"}
    readiness = as_dict(report.get("readiness"))
    paths = as_dict(report.get("paths"))
    return {
        "status": report.get("status"),
        "reason": report.get("reason"),
        "run_id": report.get("run_id"),
        "ready_for_labeling_review": readiness.get("ready_for_labeling_review", False),
        "ready_for_training_handoff": readiness.get("ready_for_training_handoff", False),
        "training_allowed": readiness.get("training_allowed", False),
        "blockers": list(readiness.get("blockers") or []),
        "quality_gaps": list(readiness.get("quality_gaps") or []),
        "report_path": paths.get("d1_training_readiness_json"),
        "markdown_report_path": paths.get("d1_training_readiness_markdown"),
        "next_step": report.get("next_step"),
    }


def labeling_intake_summary(
    report: Mapping[str, Any] | None,
    error_summary: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if error_summary:
        return dict(error_summary)
    if not report:
        return {"status": "skipped", "reason": "labeling_intake_not_run"}
    queue = as_dict(report.get("intake_queue"))
    labeling = as_dict(report.get("labeling_request"))
    gates = as_dict(report.get("review_gates"))
    paths = as_dict(report.get("paths"))
    items = queue.get("items") if isinstance(queue.get("items"), list) else []
    first_item = as_dict(items[0]) if items else {}
    first_review = as_dict(first_item.get("review_state"))
    return {
        "status": report.get("status"),
        "reason": report.get("reason"),
        "run_id": report.get("run_id"),
        "pending_items": queue.get("pending_items", 0),
        "first_intake_id": first_item.get("intake_id"),
        "first_intake_status": first_item.get("status"),
        "operator_label": first_review.get("operator_label"),
        "privacy_review": first_review.get("privacy_review"),
        "training_consent": first_review.get("training_consent"),
        "split_plan": first_review.get("split_plan"),
        "requested_label_groups": list(labeling.get("requested_label_groups") or []),
        "candidate_store_gate": gates.get("candidate_store"),
        "model_training_gate": gates.get("model_training"),
        "blockers": list(report.get("blockers") or []),
        "report_path": paths.get("d1_labeling_intake_json"),
        "markdown_report_path": paths.get("d1_labeling_intake_markdown"),
        "next_step": report.get("next_step"),
    }


def labeling_queue_summary(
    report: Mapping[str, Any] | None,
    error_summary: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if error_summary:
        return dict(error_summary)
    if not report:
        return {"status": "skipped", "reason": "labeling_queue_not_run"}
    summary = as_dict(report.get("summary"))
    paths = as_dict(report.get("paths"))
    queue = as_dict(report.get("queue"))
    items = queue.get("items") if isinstance(queue.get("items"), list) else []
    first_item = as_dict(items[0]) if items else {}
    first_review = as_dict(first_item.get("review_state"))
    return {
        "status": report.get("status"),
        "run_id": report.get("run_id"),
        "intake_report_count": summary.get("intake_report_count", 0),
        "pending_item_count": summary.get("pending_item_count", 0),
        "not_ready_report_count": summary.get("not_ready_report_count", 0),
        "first_intake_id": first_item.get("intake_id"),
        "first_source_run_id": first_item.get("source_run_id"),
        "first_operator_label": first_review.get("operator_label"),
        "first_privacy_review": first_review.get("privacy_review"),
        "first_training_consent": first_review.get("training_consent"),
        "first_split_plan": first_review.get("split_plan"),
        "report_path": paths.get("d1_labeling_queue_json"),
        "markdown_report_path": paths.get("d1_labeling_queue_markdown"),
        "next_step": report.get("next_step"),
    }


def labeling_review_packet_summary(
    report: Mapping[str, Any] | None,
    error_summary: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if error_summary:
        return dict(error_summary)
    if not report:
        return {"status": "skipped", "reason": "labeling_review_packet_not_run"}
    summary = as_dict(report.get("summary"))
    paths = as_dict(report.get("paths"))
    review_packet = as_dict(report.get("review_packet"))
    items = review_packet.get("items") if isinstance(review_packet.get("items"), list) else []
    first_item = as_dict(items[0]) if items else {}
    first_state = as_dict(first_item.get("current_review_state"))
    return {
        "status": report.get("status"),
        "reason": report.get("reason"),
        "run_id": report.get("run_id"),
        "review_packet_items": summary.get("review_packet_items", 0),
        "queue_pending_items": summary.get("queue_pending_items", 0),
        "needs_operator_label": summary.get("needs_operator_label", 0),
        "needs_privacy_review": summary.get("needs_privacy_review", 0),
        "needs_training_consent": summary.get("needs_training_consent", 0),
        "needs_split_plan": summary.get("needs_split_plan", 0),
        "first_packet_item_id": first_item.get("packet_item_id"),
        "first_intake_id": first_item.get("intake_id"),
        "first_source_run_id": first_item.get("source_run_id"),
        "first_operator_label": first_state.get("operator_label"),
        "first_privacy_review": first_state.get("privacy_review"),
        "candidate_record_written_count": summary.get("candidate_record_written_count", 0),
        "training_allowed_count": summary.get("training_allowed_count", 0),
        "report_path": paths.get("d1_labeling_review_packet_json"),
        "markdown_report_path": paths.get("d1_labeling_review_packet_markdown"),
        "next_step": report.get("next_step"),
    }


def labeling_decision_template_summary(
    report: Mapping[str, Any] | None,
    error_summary: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if error_summary:
        return dict(error_summary)
    if not report:
        return {"status": "skipped", "reason": "labeling_decision_template_not_run"}
    summary = as_dict(report.get("summary"))
    paths = as_dict(report.get("paths"))
    template = as_dict(report.get("decision_template"))
    items = template.get("items") if isinstance(template.get("items"), list) else []
    first_item = as_dict(items[0]) if items else {}
    fields = as_dict(first_item.get("decision_fields"))
    operator_slot = as_dict(fields.get("operator_label"))
    privacy_slot = as_dict(fields.get("privacy_review"))
    candidate_slot = as_dict(fields.get("candidate_decision"))
    return {
        "status": report.get("status"),
        "reason": report.get("reason"),
        "run_id": report.get("run_id"),
        "template_items": summary.get("template_items", 0),
        "required_decision_fields": summary.get("required_decision_fields", 0),
        "selected_decision_fields": summary.get("selected_decision_fields", 0),
        "items_ready_for_validation": summary.get("items_ready_for_validation", 0),
        "ready_for_candidate_promotion": summary.get("ready_for_candidate_promotion", False),
        "first_packet_item_id": first_item.get("packet_item_id"),
        "first_intake_id": first_item.get("intake_id"),
        "first_source_run_id": first_item.get("source_run_id"),
        "first_operator_label_selected": operator_slot.get("selected"),
        "first_privacy_review_selected": privacy_slot.get("selected"),
        "first_candidate_decision_selected": candidate_slot.get("selected"),
        "candidate_record_written_count": summary.get("candidate_record_written_count", 0),
        "training_allowed_count": summary.get("training_allowed_count", 0),
        "report_path": paths.get("d1_labeling_decision_template_json"),
        "markdown_report_path": paths.get("d1_labeling_decision_template_markdown"),
        "next_step": report.get("next_step"),
    }


def labeling_decision_validation_summary(
    report: Mapping[str, Any] | None,
    error_summary: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if error_summary:
        return dict(error_summary)
    if not report:
        return {"status": "skipped", "reason": "labeling_decision_validation_not_run"}
    summary = as_dict(report.get("summary"))
    paths = as_dict(report.get("paths"))
    validation = as_dict(report.get("validation"))
    items = validation.get("items") if isinstance(validation.get("items"), list) else []
    first_item = as_dict(items[0]) if items else {}
    return {
        "status": report.get("status"),
        "reason": report.get("reason"),
        "run_id": report.get("run_id"),
        "validation_items": summary.get("validation_items", 0),
        "required_decision_fields": summary.get("required_decision_fields", 0),
        "selected_decision_fields": summary.get("selected_decision_fields", 0),
        "missing_decision_fields": summary.get("missing_decision_fields", 0),
        "invalid_decision_fields": summary.get("invalid_decision_fields", 0),
        "candidate_promotion_ready_items": summary.get("candidate_promotion_ready_items", 0),
        "ready_for_candidate_promotion": summary.get("ready_for_candidate_promotion", False),
        "first_packet_item_id": first_item.get("packet_item_id"),
        "first_source_run_id": first_item.get("source_run_id"),
        "first_decision_status": first_item.get("decision_status"),
        "candidate_record_written_count": summary.get("candidate_record_written_count", 0),
        "training_allowed_count": summary.get("training_allowed_count", 0),
        "report_path": paths.get("d1_labeling_decision_validation_json"),
        "markdown_report_path": paths.get("d1_labeling_decision_validation_markdown"),
        "next_step": report.get("next_step"),
    }


def nested_path(payload: Mapping[str, Any], *keys: str) -> Path | None:
    current: Any = payload
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    if current in (None, ""):
        return None
    return Path(str(current))


def training_chain_summary(report: Mapping[str, Any] | None, error_summary: Mapping[str, Any] | None) -> dict[str, Any]:
    if error_summary:
        return dict(error_summary)
    if not report:
        return {"status": "skipped", "reason": "training_chain_not_run"}
    preflight = as_dict(report.get("training_run_preflight"))
    feature = as_dict(report.get("training_feature_manifest"))
    runner = as_dict(report.get("training_runner_dry_run"))
    baseline = as_dict(report.get("training_baseline_eval"))
    handoff = as_dict(report.get("training_handoff_bundle"))
    job_plan = as_dict(report.get("training_job_plan"))
    return {
        "status": report.get("status"),
        "reason": report.get("reason"),
        "synthetic_allowed_for_dry_run": bool(report.get("synthetic_allowed_for_dry_run")),
        "preflight": {
            "status": preflight.get("status"),
            "reason": preflight.get("reason"),
            "run_id": preflight.get("run_id"),
            "report_path": str(nested_path(preflight, "paths", "training_run_preflight_json") or ""),
        },
        "feature_manifest": {
            "status": feature.get("status"),
            "reason": feature.get("reason"),
            "feature_set_id": feature.get("feature_set_id"),
            "row_count": as_dict(feature.get("feature_rows")).get("row_count"),
            "report_path": str(nested_path(feature, "paths", "training_feature_manifest_json") or ""),
        },
        "runner_dry_run": {
            "status": runner.get("status"),
            "reason": runner.get("reason"),
            "run_id": runner.get("run_id"),
            "report_path": str(nested_path(runner, "paths", "training_runner_dry_run_json") or ""),
        },
        "baseline_eval": {
            "status": baseline.get("status"),
            "reason": baseline.get("reason"),
            "eval_id": baseline.get("eval_id"),
            "metric_scope": as_dict(baseline.get("metrics")).get("scope"),
            "report_path": str(nested_path(baseline, "paths", "training_baseline_eval_json") or ""),
        },
        "handoff_bundle": {
            "status": handoff.get("status"),
            "reason": handoff.get("reason"),
            "handoff_id": handoff.get("handoff_id"),
            "training_server": as_dict(handoff.get("training_server")).get("integration"),
            "dry_run_only": as_dict(handoff.get("training_server")).get("dry_run_only", False),
            "report_path": str(nested_path(handoff, "paths", "training_handoff_bundle_json") or ""),
        },
        "job_plan": {
            "status": job_plan.get("status"),
            "reason": job_plan.get("reason"),
            "job_id": job_plan.get("job_id"),
            "runner_profile": as_dict(job_plan.get("runner_plan")).get("runner_profile"),
            "queue_state": as_dict(job_plan.get("runner_plan")).get("queue_state"),
            "dry_run_only": as_dict(job_plan.get("runner_plan")).get("dry_run_only", False),
            "report_path": str(nested_path(job_plan, "paths", "training_job_plan_json") or ""),
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


def field_power_samples_path(
    args: argparse.Namespace,
    *,
    field_report: Mapping[str, Any] | None,
    field_status: Mapping[str, Any] | None,
) -> Path | None:
    if args.field_power_samples:
        return args.field_power_samples
    for source in (field_report, field_status):
        path = resolve_path_reference(as_dict(source).get("samples_path"))
        if path:
            return path
    return None


def field_report_path_for_power_export(
    args: argparse.Namespace,
    *,
    field_report: Mapping[str, Any] | None,
) -> Path | None:
    explicit_report = args.field_observation_report
    if explicit_report and explicit_report.is_file():
        return explicit_report
    report_path = resolve_path_reference(as_dict(field_report).get("report_path"))
    return report_path if report_path and report_path.is_file() else None


def collect_power_curve(
    args: argparse.Namespace,
    *,
    token: str | None,
    output_dir: Path,
    created_at: str,
    field_report: Mapping[str, Any] | None = None,
    field_status: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any], Path | None]:
    if args.skip_power:
        return None, {"status": "skipped", "reason": "skip_power_requested"}, None
    if args.field_power_samples and (args.power_export or args.message_test_run_id):
        return (
            None,
            {"status": "error", "reason": "field_power_samples_is_mutually_exclusive_with_power_export_or_message_test_run_id"},
            None,
        )
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
        samples_path = field_power_samples_path(args, field_report=field_report, field_status=field_status)
        if samples_path and samples_path.is_file():
            output_dir.mkdir(parents=True, exist_ok=True)
            export_path = output_dir / convert_d1_field_samples_to_power_export.EXPORT_JSON
            try:
                export = convert_d1_field_samples_to_power_export.build_power_export(
                    samples_path=samples_path,
                    field_report_path=field_report_path_for_power_export(args, field_report=field_report),
                    run_id=args.run_id,
                    device_id=args.device_id,
                    created_at=created_at,
                )
                convert_d1_field_samples_to_power_export.write_power_export(export_path, export)
            except convert_d1_field_samples_to_power_export.FieldPowerExportError as exc:
                return None, bounded_error("field_power_export_failed", exc), export_path
        elif samples_path:
            return (
                None,
                {"status": "skipped", "reason": "field_power_samples_missing", "samples_path": str(samples_path)},
                None,
            )
        else:
            return (
                None,
                {"status": "skipped", "reason": "message_test_run_id_power_export_or_field_samples_required"},
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


def collect_field_observation(
    args: argparse.Namespace,
    *,
    run_id: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
    if args.skip_field_observation:
        return None, None, {"status": "skipped", "reason": "skip_field_observation_requested"}
    report_path = args.field_observation_report or (
        observe_d1_field_run.DEFAULT_OUTPUT_ROOT / run_id / observe_d1_field_run.REPORT_JSON
    )
    status_path = args.field_observation_status or (
        observe_d1_field_run.DEFAULT_OUTPUT_ROOT / run_id / observe_d1_field_run.STATUS_JSON
    )
    try:
        if report_path.is_file():
            return read_json_file(report_path, label="field observation report"), None, None
        if status_path.is_file():
            status = read_json_file(status_path, label="field observation status")
            status = dict(status)
            status.setdefault("status_path", str(status_path))
            return None, status, None
    except Exception as exc:
        return None, None, bounded_error("field_observation_report_failed", exc)
    return (
        None,
        None,
        {
            "status": "skipped",
            "reason": "field_observation_report_missing",
            "report_path": str(report_path),
            "status_path": str(status_path),
        },
    )


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


def collect_training_readiness(
    args: argparse.Namespace,
    *,
    field_report: Mapping[str, Any] | None,
    field_status: Mapping[str, Any] | None,
    field_error: Mapping[str, Any] | None,
    run_id: str,
    created_at: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if args.skip_training_readiness:
        return None, {"status": "skipped", "reason": "skip_training_readiness_requested"}
    if field_error:
        return None, {
            "status": "skipped",
            "reason": "field_observation_not_available_for_training_readiness",
            "field_observation_reason": field_error.get("reason"),
        }
    report_ref = args.field_observation_report
    if report_ref is None and field_report:
        report_path_text = field_report.get("report_path")
        report_ref = Path(str(report_path_text)) if report_path_text else None
    status_ref = args.field_observation_status
    if status_ref is None and field_status:
        status_path_text = field_status.get("status_path")
        status_ref = Path(str(status_path_text)) if status_path_text else None
    if report_ref is None and status_ref is None:
        return None, {"status": "skipped", "reason": "field_observation_report_missing"}

    readiness_run_id = args.training_readiness_run_id or f"{run_id}-training-readiness"
    namespace = argparse.Namespace(
        field_observation_report=report_ref,
        field_observation_status=status_ref,
        field_observation_root=assess_d1_training_readiness.DEFAULT_FIELD_OBSERVATION_ROOT,
        run_id=readiness_run_id,
        generated_at=created_at,
        output_root=args.training_readiness_output_root,
        output_dir=args.training_readiness_output_dir,
        json=False,
    )
    try:
        report = assess_d1_training_readiness.build_from_args(namespace)
    except Exception as exc:
        return None, bounded_error("training_readiness_assessment_failed", exc)
    return report, None


def collect_labeling_intake(
    args: argparse.Namespace,
    *,
    training_readiness_report: Mapping[str, Any] | None,
    training_readiness_error: Mapping[str, Any] | None,
    run_id: str,
    created_at: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if args.skip_labeling_intake:
        return None, {"status": "skipped", "reason": "skip_labeling_intake_requested"}
    if training_readiness_error:
        return None, {
            "status": "skipped",
            "reason": "training_readiness_not_available_for_labeling_intake",
            "training_readiness_reason": training_readiness_error.get("reason"),
        }
    readiness_ref = args.labeling_intake_training_readiness_report
    if readiness_ref is None and training_readiness_report:
        paths = as_dict(training_readiness_report.get("paths"))
        report_path_text = paths.get("d1_training_readiness_json")
        readiness_ref = Path(str(report_path_text)) if report_path_text else None
    expected_readiness_dir = args.training_readiness_output_dir or (
        args.training_readiness_output_root / (args.training_readiness_run_id or f"{run_id}-training-readiness")
    )
    if readiness_ref is None or (not readiness_ref.is_absolute() and not (REPO_ROOT / readiness_ref).is_file()):
        expected_readiness_ref = expected_readiness_dir / "d1_training_readiness.json"
        if expected_readiness_ref.is_file():
            readiness_ref = expected_readiness_ref
    if readiness_ref is None:
        return None, {"status": "skipped", "reason": "training_readiness_report_missing"}
    if not readiness_ref.is_absolute():
        readiness_ref = REPO_ROOT / readiness_ref

    intake_run_id = args.labeling_intake_run_id or f"{run_id}-labeling-intake"
    namespace = argparse.Namespace(
        training_readiness_report=readiness_ref,
        training_readiness_root=build_d1_labeling_intake.DEFAULT_READINESS_ROOT,
        run_id=intake_run_id,
        generated_at=created_at,
        output_root=args.labeling_intake_output_root,
        output_dir=args.labeling_intake_output_dir,
        json=False,
    )
    try:
        report = build_d1_labeling_intake.build_from_args(namespace)
    except Exception as exc:
        return None, bounded_error("labeling_intake_failed", exc)
    return report, None


def collect_labeling_queue(
    args: argparse.Namespace,
    *,
    labeling_intake_report: Mapping[str, Any] | None,
    labeling_intake_error: Mapping[str, Any] | None,
    run_id: str,
    created_at: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if args.skip_labeling_queue:
        return None, {"status": "skipped", "reason": "skip_labeling_queue_requested"}
    if labeling_intake_error:
        return None, {
            "status": "skipped",
            "reason": "labeling_intake_not_available_for_queue",
            "labeling_intake_reason": labeling_intake_error.get("reason"),
        }
    if not labeling_intake_report:
        return None, {"status": "skipped", "reason": "labeling_intake_report_missing"}

    queue_run_id = args.labeling_queue_run_id or f"{run_id}-labeling-queue"
    intake_root = args.labeling_intake_output_dir.parent if args.labeling_intake_output_dir else args.labeling_intake_output_root
    namespace = argparse.Namespace(
        intake_root=intake_root,
        run_id=queue_run_id,
        generated_at=created_at,
        output_root=args.labeling_queue_output_root,
        output_dir=args.labeling_queue_output_dir,
        limit=args.labeling_queue_limit,
        json=False,
    )
    try:
        report = summarize_d1_labeling_queue.build_from_args(namespace)
    except Exception as exc:
        return None, bounded_error("labeling_queue_failed", exc)
    return report, None


def collect_labeling_review_packet(
    args: argparse.Namespace,
    *,
    labeling_queue_report: Mapping[str, Any] | None,
    labeling_queue_error: Mapping[str, Any] | None,
    run_id: str,
    created_at: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if args.skip_labeling_review_packet:
        return None, {"status": "skipped", "reason": "skip_labeling_review_packet_requested"}
    if labeling_queue_error:
        return None, {
            "status": "skipped",
            "reason": "labeling_queue_not_available_for_review_packet",
            "labeling_queue_reason": labeling_queue_error.get("reason"),
        }
    if not labeling_queue_report:
        return None, {"status": "skipped", "reason": "labeling_queue_report_missing"}

    queue_ref = args.labeling_review_packet_queue_report
    if queue_ref is None:
        paths = as_dict(labeling_queue_report.get("paths"))
        report_path_text = paths.get("d1_labeling_queue_json")
        queue_ref = Path(str(report_path_text)) if report_path_text else None
    expected_queue_dir = args.labeling_queue_output_dir or (
        args.labeling_queue_output_root / (args.labeling_queue_run_id or f"{run_id}-labeling-queue")
    )
    if queue_ref is None or (not queue_ref.is_absolute() and not (REPO_ROOT / queue_ref).is_file()):
        expected_queue_ref = expected_queue_dir / "d1_labeling_queue.json"
        if expected_queue_ref.is_file():
            queue_ref = expected_queue_ref
    if queue_ref is None:
        return None, {"status": "skipped", "reason": "labeling_queue_report_missing"}
    if not queue_ref.is_absolute():
        queue_ref = REPO_ROOT / queue_ref

    review_run_id = args.labeling_review_packet_run_id or f"{run_id}-labeling-review"
    queue_root = args.labeling_queue_output_dir.parent if args.labeling_queue_output_dir else args.labeling_queue_output_root
    namespace = argparse.Namespace(
        labeling_queue_report=queue_ref,
        labeling_queue_root=queue_root,
        run_id=review_run_id,
        generated_at=created_at,
        output_root=args.labeling_review_packet_output_root,
        output_dir=args.labeling_review_packet_output_dir,
        limit=args.labeling_review_packet_limit,
        json=False,
    )
    try:
        report = build_d1_labeling_review_packet.build_from_args(namespace)
    except Exception as exc:
        return None, bounded_error("labeling_review_packet_failed", exc)
    return report, None


def collect_labeling_decision_template(
    args: argparse.Namespace,
    *,
    labeling_review_packet_report: Mapping[str, Any] | None,
    labeling_review_packet_error: Mapping[str, Any] | None,
    run_id: str,
    created_at: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if args.skip_labeling_decision_template:
        return None, {"status": "skipped", "reason": "skip_labeling_decision_template_requested"}
    if labeling_review_packet_error:
        return None, {
            "status": "skipped",
            "reason": "labeling_review_packet_not_available_for_decision_template",
            "labeling_review_packet_reason": labeling_review_packet_error.get("reason"),
        }
    if not labeling_review_packet_report:
        return None, {"status": "skipped", "reason": "labeling_review_packet_report_missing"}

    review_ref = args.labeling_decision_template_review_packet_report
    if review_ref is None:
        paths = as_dict(labeling_review_packet_report.get("paths"))
        report_path_text = paths.get("d1_labeling_review_packet_json")
        review_ref = Path(str(report_path_text)) if report_path_text else None
    expected_review_dir = args.labeling_review_packet_output_dir or (
        args.labeling_review_packet_output_root
        / (args.labeling_review_packet_run_id or f"{run_id}-labeling-review")
    )
    if review_ref is None or (not review_ref.is_absolute() and not (REPO_ROOT / review_ref).is_file()):
        expected_review_ref = expected_review_dir / "d1_labeling_review_packet.json"
        if expected_review_ref.is_file():
            review_ref = expected_review_ref
    if review_ref is None:
        return None, {"status": "skipped", "reason": "labeling_review_packet_report_missing"}
    if not review_ref.is_absolute():
        review_ref = REPO_ROOT / review_ref

    decision_run_id = args.labeling_decision_template_run_id or f"{run_id}-labeling-decisions"
    review_root = (
        args.labeling_review_packet_output_dir.parent
        if args.labeling_review_packet_output_dir
        else args.labeling_review_packet_output_root
    )
    namespace = argparse.Namespace(
        review_packet_report=review_ref,
        review_packet_root=review_root,
        run_id=decision_run_id,
        generated_at=created_at,
        output_root=args.labeling_decision_template_output_root,
        output_dir=args.labeling_decision_template_output_dir,
        limit=args.labeling_decision_template_limit,
        json=False,
    )
    try:
        report = build_d1_labeling_decision_template.build_from_args(namespace)
    except Exception as exc:
        return None, bounded_error("labeling_decision_template_failed", exc)
    return report, None


def collect_labeling_decision_validation(
    args: argparse.Namespace,
    *,
    labeling_decision_template_report: Mapping[str, Any] | None,
    labeling_decision_template_error: Mapping[str, Any] | None,
    run_id: str,
    created_at: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if args.skip_labeling_decision_validation:
        return None, {"status": "skipped", "reason": "skip_labeling_decision_validation_requested"}
    if labeling_decision_template_error:
        return None, {
            "status": "skipped",
            "reason": "labeling_decision_template_not_available_for_validation",
            "labeling_decision_template_reason": labeling_decision_template_error.get("reason"),
        }
    if not labeling_decision_template_report:
        return None, {"status": "skipped", "reason": "labeling_decision_template_report_missing"}

    decision_ref = args.labeling_decision_validation_template_report
    if decision_ref is None:
        paths = as_dict(labeling_decision_template_report.get("paths"))
        report_path_text = paths.get("d1_labeling_decision_template_json")
        decision_ref = Path(str(report_path_text)) if report_path_text else None
    expected_decision_dir = args.labeling_decision_template_output_dir or (
        args.labeling_decision_template_output_root
        / (args.labeling_decision_template_run_id or f"{run_id}-labeling-decisions")
    )
    if decision_ref is None or (not decision_ref.is_absolute() and not (REPO_ROOT / decision_ref).is_file()):
        expected_decision_ref = expected_decision_dir / "d1_labeling_decision_template.json"
        if expected_decision_ref.is_file():
            decision_ref = expected_decision_ref
    if decision_ref is None:
        return None, {"status": "skipped", "reason": "labeling_decision_template_report_missing"}
    if not decision_ref.is_absolute():
        decision_ref = REPO_ROOT / decision_ref

    validation_run_id = args.labeling_decision_validation_run_id or f"{run_id}-labeling-decision-validation"
    decision_root = (
        args.labeling_decision_template_output_dir.parent
        if args.labeling_decision_template_output_dir
        else args.labeling_decision_template_output_root
    )
    namespace = argparse.Namespace(
        decision_template_report=decision_ref,
        decision_template_root=decision_root,
        run_id=validation_run_id,
        generated_at=created_at,
        output_root=args.labeling_decision_validation_output_root,
        output_dir=args.labeling_decision_validation_output_dir,
        limit=args.labeling_decision_validation_limit,
        json=False,
    )
    try:
        report = validate_d1_labeling_decision_template.build_from_args(namespace)
    except Exception as exc:
        return None, bounded_error("labeling_decision_validation_failed", exc)
    return report, None


def collect_training_chain(
    args: argparse.Namespace,
    *,
    data_report: Mapping[str, Any] | None,
    run_id: str,
    created_at: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if args.skip_training_chain:
        return None, {"status": "skipped", "reason": "skip_training_chain_requested"}
    if not data_report:
        return None, {"status": "skipped", "reason": "data_flywheel_pipeline_missing"}
    if data_report.get("status") != READY_DATA_PIPELINE_STATUS:
        return None, {
            "status": "skipped",
            "reason": "data_flywheel_pipeline_not_ready",
            "data_flywheel_pipeline_status": data_report.get("status"),
            "next_step": data_report.get("next_step"),
        }

    dataset_manifest_path = nested_path(data_report, "dataset_manifest", "paths", "training_dataset_manifest_json")
    experiment_plan_path = nested_path(data_report, "training_experiment", "paths", "training_experiment_plan_json")
    if dataset_manifest_path is None or experiment_plan_path is None:
        return None, {
            "status": "error",
            "reason": "training_chain_inputs_missing",
            "dataset_manifest_path": str(dataset_manifest_path) if dataset_manifest_path else None,
            "experiment_plan_path": str(experiment_plan_path) if experiment_plan_path else None,
        }

    try:
        preflight_run_id = args.training_run_id or f"{run_id}-training-preflight"
        experiment = run_training_experiment_preflight.load_json(
            experiment_plan_path,
            label="experiment plan",
        )
        dataset = run_training_experiment_preflight.load_json(
            dataset_manifest_path,
            label="dataset manifest",
        )
        preflight_payload = run_training_experiment_preflight.build_preflight_report(
            experiment,
            dataset,
            experiment_plan_ref=experiment_plan_path.name,
            dataset_manifest_ref=dataset_manifest_path.name,
            run_id=preflight_run_id,
            created_at=created_at,
            allow_synthetic=args.allow_synthetic_training_chain,
        )
        preflight_written = run_training_experiment_preflight.write_preflight_report(
            preflight_payload,
            args.training_run_output_root / preflight_run_id,
        )
        preflight_path = args.training_run_output_root / preflight_run_id / "training_run_preflight.json"

        feature_set_id = args.feature_set_id or f"{run_id}-features"
        feature_dataset = export_training_feature_manifest.load_json(
            dataset_manifest_path,
            label="dataset manifest",
        )
        feature_preflight = export_training_feature_manifest.load_json(
            preflight_path,
            label="training run preflight",
        )
        feature_payload, feature_rows = export_training_feature_manifest.build_feature_manifest(
            feature_dataset,
            feature_preflight,
            dataset_manifest_ref=dataset_manifest_path.name,
            preflight_ref=preflight_path.name,
            feature_set_id=feature_set_id,
            generated_at=created_at,
            allow_synthetic=args.allow_synthetic_training_chain,
        )
        feature_written = export_training_feature_manifest.write_feature_manifest(
            feature_payload,
            feature_rows,
            args.training_feature_output_root / feature_set_id,
        )
        feature_manifest_path = args.training_feature_output_root / feature_set_id / "training_feature_manifest.json"
        feature_rows_path = args.training_feature_output_root / feature_set_id / "training_feature_rows.jsonl"

        runner_run_id = args.runner_dry_run_id or f"{run_id}-runner-dry-run"
        runner_manifest = run_training_runner_dry_run.load_json(
            feature_manifest_path,
            label="feature manifest",
        )
        runner_rows, runner_row_error = run_training_runner_dry_run.load_jsonl_rows(feature_rows_path)
        runner_payload = run_training_runner_dry_run.build_runner_dry_run_report(
            runner_manifest,
            runner_rows,
            row_error=runner_row_error,
            feature_manifest_ref=feature_manifest_path.name,
            feature_rows_ref=feature_rows_path.name,
            run_id=runner_run_id,
            created_at=created_at,
            allow_synthetic=args.allow_synthetic_training_chain,
        )
        runner_written = run_training_runner_dry_run.write_runner_dry_run_report(
            runner_payload,
            args.training_runner_dry_run_output_root / runner_run_id,
        )
        runner_path = args.training_runner_dry_run_output_root / runner_run_id / "training_runner_dry_run.json"

        baseline_eval_id = args.baseline_eval_id or f"{run_id}-baseline-eval"
        baseline_manifest = run_training_baseline_eval.load_json(
            feature_manifest_path,
            label="feature manifest",
        )
        baseline_runner = run_training_baseline_eval.load_json(
            runner_path,
            label="runner dry-run",
        )
        baseline_rows, baseline_row_error = run_training_baseline_eval.load_jsonl_rows(feature_rows_path)
        baseline_payload = run_training_baseline_eval.build_baseline_eval_report(
            baseline_manifest,
            baseline_runner,
            baseline_rows,
            row_error=baseline_row_error,
            feature_manifest_ref=feature_manifest_path.name,
            feature_rows_ref=feature_rows_path.name,
            runner_dry_run_ref=runner_path.name,
            eval_id=baseline_eval_id,
            created_at=created_at,
            allow_synthetic=args.allow_synthetic_training_chain,
        )
        baseline_written = run_training_baseline_eval.write_baseline_eval_report(
            baseline_payload,
            args.training_baseline_eval_output_root / baseline_eval_id,
        )
        baseline_path = args.training_baseline_eval_output_root / baseline_eval_id / "training_baseline_eval.json"

        handoff_id = args.training_handoff_id or f"{run_id}-training-handoff"
        handoff_dataset = build_training_handoff_bundle.load_json(
            dataset_manifest_path,
            label="dataset manifest",
        )
        handoff_preflight = build_training_handoff_bundle.load_json(
            preflight_path,
            label="training run preflight",
        )
        handoff_feature = build_training_handoff_bundle.load_json(
            feature_manifest_path,
            label="feature manifest",
        )
        handoff_runner = build_training_handoff_bundle.load_json(
            runner_path,
            label="runner dry-run",
        )
        handoff_baseline = build_training_handoff_bundle.load_json(
            baseline_path,
            label="baseline eval",
        )
        feature_row_count = build_training_handoff_bundle.count_jsonl_rows(feature_rows_path)
        handoff_payload = build_training_handoff_bundle.build_handoff_bundle(
            dataset=handoff_dataset,
            preflight=handoff_preflight,
            feature_manifest=handoff_feature,
            feature_row_count=feature_row_count,
            runner_dry_run=handoff_runner,
            baseline_eval=handoff_baseline,
            source_refs={
                "dataset_manifest": build_training_handoff_bundle.input_ref(dataset_manifest_path),
                "training_run_preflight": build_training_handoff_bundle.input_ref(preflight_path),
                "training_feature_manifest": build_training_handoff_bundle.input_ref(feature_manifest_path),
                "training_feature_rows": build_training_handoff_bundle.input_ref(feature_rows_path),
                "training_runner_dry_run": build_training_handoff_bundle.input_ref(runner_path),
                "training_baseline_eval": build_training_handoff_bundle.input_ref(baseline_path),
            },
            handoff_id=handoff_id,
            created_at=created_at,
            allow_synthetic=args.allow_synthetic_training_chain,
        )
        handoff_written = build_training_handoff_bundle.write_handoff_bundle(
            handoff_payload,
            args.training_handoff_output_root / handoff_id,
        )
        handoff_path = args.training_handoff_output_root / handoff_id / "training_handoff_bundle.json"

        job_id = args.training_job_id or f"{run_id}-training-job"
        job_payload = create_training_job_plan.build_job_plan(
            handoff_written,
            handoff_ref=create_training_job_plan.input_ref(handoff_path),
            job_id=job_id,
            created_at=created_at,
            allow_synthetic=args.allow_synthetic_training_chain,
            model_track=args.model_track,
            candidate_model=args.candidate_model,
            baseline_model=args.baseline_model,
            runner_profile=args.training_job_runner_profile,
        )
        job_written = create_training_job_plan.write_job_plan(
            job_payload,
            args.training_job_output_root / job_id,
        )
    except Exception as exc:
        return None, bounded_error("training_chain_failed", exc)

    return (
        {
            "status": job_written.get("status"),
            "reason": job_written.get("reason"),
            "synthetic_allowed_for_dry_run": bool(args.allow_synthetic_training_chain),
            "training_run_preflight": preflight_written,
            "training_feature_manifest": feature_written,
            "training_runner_dry_run": runner_written,
            "training_baseline_eval": baseline_written,
            "training_handoff_bundle": handoff_written,
            "training_job_plan": job_written,
            "next_step": job_written.get("next_step"),
        },
        None,
    )


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

    field_observation = as_dict(components.get("field_observation"))
    field_status = str(field_observation.get("result") or field_observation.get("status") or "")
    if field_observation.get("status") == "error":
        warnings.append(f"field_observation:{field_observation.get('reason') or field_status}")
    elif field_status == "FAIL":
        warnings.append("field_observation:result_fail")
    elif field_status and field_status not in {"PASS", "WARN", "completed", "skipped"}:
        warnings.append(f"field_observation:{field_observation.get('reason') or field_status}")

    data_pipeline = as_dict(components.get("data_flywheel_pipeline"))
    data_status = str(data_pipeline.get("status") or "unknown")
    if data_status != "ready_for_training_handoff":
        warnings.append(f"data_flywheel_pipeline:{data_pipeline.get('reason') or data_status}")

    training_readiness = as_dict(components.get("training_readiness"))
    readiness_status = str(training_readiness.get("status") or "unknown")
    if readiness_status not in {"ready_for_labeling_review", "skipped"}:
        warnings.append(f"training_readiness:{training_readiness.get('reason') or readiness_status}")

    labeling_intake = as_dict(components.get("labeling_intake"))
    labeling_status = str(labeling_intake.get("status") or "unknown")
    if labeling_status not in {"pending_human_review", "not_ready_for_labeling_intake", "skipped"}:
        warnings.append(f"labeling_intake:{labeling_intake.get('reason') or labeling_status}")

    labeling_queue = as_dict(components.get("labeling_queue"))
    labeling_queue_status = str(labeling_queue.get("status") or "unknown")
    if labeling_queue_status not in {"pending_human_review", "empty_or_not_ready", "no_intake_reports", "skipped"}:
        warnings.append(f"labeling_queue:{labeling_queue.get('reason') or labeling_queue_status}")

    labeling_review_packet = as_dict(components.get("labeling_review_packet"))
    labeling_review_status = str(labeling_review_packet.get("status") or "unknown")
    if labeling_review_status not in {"needs_human_review", "no_review_items", "no_labeling_queue", "skipped"}:
        warnings.append(f"labeling_review_packet:{labeling_review_packet.get('reason') or labeling_review_status}")

    labeling_decision_template = as_dict(components.get("labeling_decision_template"))
    labeling_decision_status = str(labeling_decision_template.get("status") or "unknown")
    if labeling_decision_status not in {
        "ready_for_human_input",
        "no_decision_items",
        "no_labeling_review_packet",
        "skipped",
    }:
        warnings.append(
            f"labeling_decision_template:{labeling_decision_template.get('reason') or labeling_decision_status}"
        )

    labeling_decision_validation = as_dict(components.get("labeling_decision_validation"))
    labeling_validation_status = str(labeling_decision_validation.get("status") or "unknown")
    if labeling_validation_status not in {
        "needs_decisions",
        "ready_for_candidate_promotion",
        "mixed_review_complete",
        "review_complete_not_promotable",
        "no_decision_items",
        "no_decision_template",
        "skipped",
    }:
        warnings.append(
            f"labeling_decision_validation:{labeling_decision_validation.get('reason') or labeling_validation_status}"
        )

    training_chain = as_dict(components.get("training_chain"))
    training_status = str(training_chain.get("status") or "unknown")
    if training_status == "error":
        warnings.append(f"training_chain:{training_chain.get('reason') or training_status}")
    elif training_status not in {READY_JOB_STATUS, SYNTHETIC_JOB_STATUS, "skipped"}:
        warnings.append(f"training_chain:{training_chain.get('reason') or training_status}")

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
        steps.append(
            "Rerun with --message-test-run-id, --power-export, or a field observer report/status "
            "with d1_field_samples.jsonl to bind a power curve report."
        )
    elif power_result != "PASS":
        steps.append("Inspect the power report; WARN/FAIL is allowed for a shakedown but must explain the gap.")

    d1_demo = as_dict(components.get("d1_demo"))
    if d1_demo and not d1_demo.get("ready_for_founder_review"):
        steps.append(
            "Keep work on D1 acceptance: rerun the 3-4h field session or PWR-001 evidence as needed, "
            "and keep DATA/TRAIN frozen until founder acceptance."
        )

    field_observation = as_dict(components.get("field_observation"))
    field_status = str(field_observation.get("result") or field_observation.get("status") or "")
    if field_status == "running":
        steps.append("Wait for the D1 field observer to finish, then rerun the post-run collector to bind the final observation report.")
    elif field_status == "FAIL":
        steps.append("Inspect the D1 field observation report before treating the run as reviewable.")

    data_pipeline = as_dict(components.get("data_flywheel_pipeline"))
    data_status = str(data_pipeline.get("status") or "")
    if data_status == "needs_recordings":
        steps.append("Attach explicit --recording-dir inputs when there are reviewed session recordings to ingest.")
    elif data_status == "needs_review":
        steps.append("Review pending candidates, then rerun the data-flywheel pipeline.")
    elif data_status and data_status not in {"ready_for_training_handoff", "skipped"}:
        steps.append(str(data_pipeline.get("next_step") or "Continue the next DATA/TRAIN task."))

    training_readiness = as_dict(components.get("training_readiness"))
    readiness_status = str(training_readiness.get("status") or "")
    if readiness_status == "ready_for_labeling_review":
        steps.append("Attach labels, privacy review, training consent, and split plan before training handoff.")
    elif readiness_status and readiness_status not in {"skipped", "ready_for_labeling_review"}:
        steps.append(str(training_readiness.get("next_step") or "Rerun D1 training readiness after a fresher field observation."))

    labeling_intake = as_dict(components.get("labeling_intake"))
    labeling_status = str(labeling_intake.get("status") or "")
    if labeling_status == "pending_human_review":
        steps.append(str(labeling_intake.get("next_step") or "Complete D1 labeling/privacy intake review before candidate-store writes."))
    elif labeling_status and labeling_status not in {"skipped", "not_ready_for_labeling_intake", "pending_human_review"}:
        steps.append(str(labeling_intake.get("next_step") or "Rerun D1 labeling intake after readiness is available."))

    labeling_queue = as_dict(components.get("labeling_queue"))
    labeling_queue_status = str(labeling_queue.get("status") or "")
    if labeling_queue_status == "pending_human_review":
        steps.append(str(labeling_queue.get("next_step") or "Review the D1 labeling queue before candidate-store writes."))
    elif labeling_queue_status and labeling_queue_status not in {
        "skipped",
        "empty_or_not_ready",
        "no_intake_reports",
        "pending_human_review",
    }:
        steps.append(str(labeling_queue.get("next_step") or "Rerun D1 labeling queue after intake is available."))

    labeling_review_packet = as_dict(components.get("labeling_review_packet"))
    labeling_review_status = str(labeling_review_packet.get("status") or "")
    if labeling_review_status == "needs_human_review":
        steps.append(
            str(
                labeling_review_packet.get("next_step")
                or "Fill the D1 labeling review packet before candidate-store promotion."
            )
        )
    elif labeling_review_status and labeling_review_status not in {
        "skipped",
        "no_review_items",
        "no_labeling_queue",
        "needs_human_review",
    }:
        steps.append(
            str(labeling_review_packet.get("next_step") or "Rerun D1 labeling review packet after queue generation.")
        )

    labeling_decision_template = as_dict(components.get("labeling_decision_template"))
    labeling_decision_status = str(labeling_decision_template.get("status") or "")
    if labeling_decision_status == "ready_for_human_input":
        steps.append(
            str(
                labeling_decision_template.get("next_step")
                or "Fill the D1 labeling decision template before candidate-store promotion."
            )
        )
    elif labeling_decision_status and labeling_decision_status not in {
        "skipped",
        "no_decision_items",
        "no_labeling_review_packet",
        "ready_for_human_input",
    }:
        steps.append(
            str(
                labeling_decision_template.get("next_step")
                or "Rerun D1 labeling decision template after review packet generation."
            )
        )

    labeling_decision_validation = as_dict(components.get("labeling_decision_validation"))
    labeling_validation_status = str(labeling_decision_validation.get("status") or "")
    if labeling_validation_status == "needs_decisions":
        steps.append(
            str(
                labeling_decision_validation.get("next_step")
                or "Fill missing selected values in the D1 labeling decision template, then rerun validation."
            )
        )
    elif labeling_validation_status == "invalid_decisions":
        steps.append(
            str(
                labeling_decision_validation.get("next_step")
                or "Fix invalid selected values in the D1 labeling decision template, then rerun validation."
            )
        )
    elif labeling_validation_status in {"ready_for_candidate_promotion", "mixed_review_complete"}:
        steps.append(
            str(
                labeling_decision_validation.get("next_step")
                or "Run a future explicit candidate-store promotion task; validation did not write records."
            )
        )
    elif labeling_validation_status and labeling_validation_status not in {
        "skipped",
        "no_decision_items",
        "no_decision_template",
        "review_complete_not_promotable",
    }:
        steps.append(
            str(labeling_decision_validation.get("next_step") or "Rerun D1 labeling decision validation.")
        )

    training_chain = as_dict(components.get("training_chain"))
    training_status = str(training_chain.get("status") or "")
    if training_status == "skipped" and training_chain.get("reason") == "data_flywheel_pipeline_not_ready":
        steps.append("After candidate review makes the dataset ready, rerun the post-run collector to create TRAIN-003..008 reports.")
    elif training_status == SYNTHETIC_JOB_STATUS:
        steps.append("Repeat the post-run collector with reviewed real rows before using the job plan for model training.")
    elif training_status and training_status not in {READY_JOB_STATUS, "skipped"}:
        steps.append(str(training_chain.get("next_step") or "Inspect the generated training-chain report and fix the first blocker."))

    if result != "FAIL":
        steps.append("Sync curated summaries to the VPS Dashboard when the run should be visible remotely.")
    return steps or ["No immediate follow-up is required for this collector result."]


def artifact_paths(components: Mapping[str, Mapping[str, Any]], summary_json: Path, summary_md: Path) -> dict[str, Any]:
    field_observation = as_dict(components.get("field_observation"))
    training_readiness = as_dict(components.get("training_readiness"))
    labeling_intake = as_dict(components.get("labeling_intake"))
    labeling_queue = as_dict(components.get("labeling_queue"))
    labeling_review_packet = as_dict(components.get("labeling_review_packet"))
    labeling_decision_template = as_dict(components.get("labeling_decision_template"))
    labeling_decision_validation = as_dict(components.get("labeling_decision_validation"))
    data_pipeline = as_dict(components.get("data_flywheel_pipeline"))
    training_experiment = as_dict(data_pipeline.get("training_experiment"))
    training_chain = as_dict(components.get("training_chain"))
    preflight = as_dict(training_chain.get("preflight"))
    feature_manifest = as_dict(training_chain.get("feature_manifest"))
    runner_dry_run = as_dict(training_chain.get("runner_dry_run"))
    baseline_eval = as_dict(training_chain.get("baseline_eval"))
    handoff_bundle = as_dict(training_chain.get("handoff_bundle"))
    job_plan = as_dict(training_chain.get("job_plan"))
    return {
        "postrun_summary_json": str(summary_json),
        "postrun_summary_markdown": str(summary_md),
        "field_observation_report": field_observation.get("report_path"),
        "field_observation_status": field_observation.get("status_path"),
        "field_observation_samples": field_observation.get("samples_path"),
        "d1_training_readiness": training_readiness.get("report_path"),
        "d1_labeling_intake": labeling_intake.get("report_path"),
        "d1_labeling_queue": labeling_queue.get("report_path"),
        "d1_labeling_review_packet": labeling_review_packet.get("report_path"),
        "d1_labeling_decision_template": labeling_decision_template.get("report_path"),
        "d1_labeling_decision_validation": labeling_decision_validation.get("report_path"),
        "web_api_report": as_dict(components.get("web_api")).get("report_path"),
        "power_curve_report": as_dict(components.get("power_curve")).get("report_path"),
        "message_hub_export": as_dict(components.get("power_curve")).get("export_path"),
        "d1_demo_report": as_dict(components.get("d1_demo")).get("report_path"),
        "data_flywheel_pipeline": data_pipeline.get("report_path"),
        "data_flywheel_status": data_pipeline.get("data_flywheel_status_path"),
        "training_dataset_manifest": data_pipeline.get("dataset_manifest_path"),
        "training_experiment_plan": training_experiment.get("report_path"),
        "training_run_preflight": preflight.get("report_path"),
        "training_feature_manifest": feature_manifest.get("report_path"),
        "training_runner_dry_run": runner_dry_run.get("report_path"),
        "training_baseline_eval": baseline_eval.get("report_path"),
        "training_handoff_bundle": handoff_bundle.get("report_path"),
        "training_job_plan": job_plan.get("report_path"),
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
    for name in (
        "field_observation",
        "training_readiness",
        "labeling_intake",
        "labeling_queue",
        "labeling_review_packet",
        "labeling_decision_template",
        "labeling_decision_validation",
        "web_api",
        "power_curve",
        "d1_demo",
        "data_flywheel_pipeline",
        "training_chain",
    ):
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
    field_report, field_status, field_error = collect_field_observation(args, run_id=run_id)
    training_readiness_report, training_readiness_error = collect_training_readiness(
        args,
        field_report=field_report,
        field_status=field_status,
        field_error=field_error,
        run_id=run_id,
        created_at=created_at,
    )
    labeling_intake_report, labeling_intake_error = collect_labeling_intake(
        args,
        training_readiness_report=training_readiness_report,
        training_readiness_error=training_readiness_error,
        run_id=run_id,
        created_at=created_at,
    )
    labeling_queue_report, labeling_queue_error = collect_labeling_queue(
        args,
        labeling_intake_report=labeling_intake_report,
        labeling_intake_error=labeling_intake_error,
        run_id=run_id,
        created_at=created_at,
    )
    labeling_review_packet_report, labeling_review_packet_error = collect_labeling_review_packet(
        args,
        labeling_queue_report=labeling_queue_report,
        labeling_queue_error=labeling_queue_error,
        run_id=run_id,
        created_at=created_at,
    )
    labeling_decision_template_report, labeling_decision_template_error = collect_labeling_decision_template(
        args,
        labeling_review_packet_report=labeling_review_packet_report,
        labeling_review_packet_error=labeling_review_packet_error,
        run_id=run_id,
        created_at=created_at,
    )
    labeling_decision_validation_report, labeling_decision_validation_error = collect_labeling_decision_validation(
        args,
        labeling_decision_template_report=labeling_decision_template_report,
        labeling_decision_template_error=labeling_decision_template_error,
        run_id=run_id,
        created_at=created_at,
    )
    power_report, power_status, export_path = collect_power_curve(
        args,
        token=token,
        output_dir=args.power_output_dir or (analyze_power_curve.DEFAULT_OUTPUT_ROOT / run_id),
        created_at=created_at,
        field_report=field_report,
        field_status=field_status,
    )
    demo_report, demo_error = collect_d1_demo(
        web_report=web_report,
        power_report=power_report,
        output_dir=args.d1_demo_output_dir or (build_d1_demo_report.DEFAULT_OUTPUT_ROOT / run_id),
        run_id=run_id,
        created_at=created_at,
    )
    data_report, data_error = collect_data_pipeline(args, run_id=run_id, created_at=created_at)
    training_report, training_error = collect_training_chain(
        args,
        data_report=data_report,
        run_id=run_id,
        created_at=created_at,
    )

    components = {
        "field_observation": field_observation_summary(field_report, field_status, field_error),
        "training_readiness": training_readiness_summary(training_readiness_report, training_readiness_error),
        "labeling_intake": labeling_intake_summary(labeling_intake_report, labeling_intake_error),
        "labeling_queue": labeling_queue_summary(labeling_queue_report, labeling_queue_error),
        "labeling_review_packet": labeling_review_packet_summary(
            labeling_review_packet_report,
            labeling_review_packet_error,
        ),
        "labeling_decision_template": labeling_decision_template_summary(
            labeling_decision_template_report,
            labeling_decision_template_error,
        ),
        "labeling_decision_validation": labeling_decision_validation_summary(
            labeling_decision_validation_report,
            labeling_decision_validation_error,
        ),
        "web_api": web_api_summary(web_report, web_error),
        "power_curve": power_summary(
            power_report,
            power_status,
            export_path=export_path,
            message_test_run_id=args.message_test_run_id,
        ),
        "d1_demo": d1_demo_summary(demo_report, demo_error),
        "data_flywheel_pipeline": data_pipeline_summary(data_report, data_error),
        "training_chain": training_chain_summary(training_report, training_error),
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
            "model_evaluation_started": False,
            "model_deployed": False,
            "model_artifact_written": False,
            "sample_jsonl_read_for_training_readiness": False,
            "sample_jsonl_read_for_labeling_intake": False,
            "sample_jsonl_read_for_labeling_queue": False,
            "sample_jsonl_read_for_labeling_review_packet": False,
            "sample_jsonl_read_for_labeling_decision_template": False,
            "sample_jsonl_read_for_labeling_decision_validation": False,
            "candidate_db_written_for_labeling_intake": False,
            "candidate_db_written_for_labeling_queue": False,
            "candidate_db_written_for_labeling_review_packet": False,
            "candidate_db_written_for_labeling_decision_template": False,
            "candidate_db_written_for_labeling_decision_validation": False,
            "secrets_persisted": False,
        },
        "boundaries": [
            "Read-only Message Hub collection plus local report generation only.",
            "No hardware, serial port, firmware, Message Hub command, deployment, or GitLab mutation is performed.",
            "The field-observation step reads only an explicit or same-run local observer report/status file.",
            "The training-readiness step reads only D1 field-observation report/status summaries, not sample JSONL contents.",
            "The labeling-intake step reads only the D1 training-readiness summary and writes no candidate DB.",
            "The labeling-queue step reads only D1 labeling-intake summaries and writes no candidate DB.",
            "The labeling-review packet step reads only the D1 labeling-queue summary and writes no candidate DB.",
            "The labeling-decision template step reads only the D1 labeling-review packet and writes no candidate DB.",
            "The labeling-decision validation step reads only the D1 labeling-decision template and writes no candidate DB.",
            "The data-flywheel step ingests only recording directories explicitly passed with --recording-dir.",
            "The training-chain step runs only bounded local preflight, feature export, runner dry-run, aggregate baseline-eval, handoff-bundle, and job-plan reports after a ready dataset handoff.",
            "Dashboard state and curated summaries are not raw training data.",
        ],
        "non_claims": [
            "No location accuracy is claimed.",
            "No battery life or 24h PWR-001 pass is claimed.",
            "No GNSS acceptance, product readiness, calling, or SMS behavior is claimed.",
            "No model training, deployment, model artifact, model card, real-world accuracy, latency, footprint, or power impact is claimed.",
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
    parser.add_argument("--skip-field-observation", action="store_true")
    parser.add_argument("--field-observation-report", type=Path)
    parser.add_argument("--field-observation-status", type=Path)
    parser.add_argument("--skip-training-readiness", action="store_true")
    parser.add_argument("--training-readiness-run-id")
    parser.add_argument("--training-readiness-output-root", type=Path, default=assess_d1_training_readiness.DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--training-readiness-output-dir", type=Path)
    parser.add_argument("--skip-labeling-intake", action="store_true")
    parser.add_argument("--labeling-intake-run-id")
    parser.add_argument("--labeling-intake-training-readiness-report", type=Path)
    parser.add_argument("--labeling-intake-output-root", type=Path, default=build_d1_labeling_intake.DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--labeling-intake-output-dir", type=Path)
    parser.add_argument("--skip-labeling-queue", action="store_true")
    parser.add_argument("--labeling-queue-run-id")
    parser.add_argument("--labeling-queue-output-root", type=Path, default=summarize_d1_labeling_queue.DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--labeling-queue-output-dir", type=Path)
    parser.add_argument("--labeling-queue-limit", type=int)
    parser.add_argument("--skip-labeling-review-packet", action="store_true")
    parser.add_argument("--labeling-review-packet-run-id")
    parser.add_argument("--labeling-review-packet-queue-report", type=Path)
    parser.add_argument(
        "--labeling-review-packet-output-root",
        type=Path,
        default=build_d1_labeling_review_packet.DEFAULT_OUTPUT_ROOT,
    )
    parser.add_argument("--labeling-review-packet-output-dir", type=Path)
    parser.add_argument("--labeling-review-packet-limit", type=int)
    parser.add_argument("--skip-labeling-decision-template", action="store_true")
    parser.add_argument("--labeling-decision-template-run-id")
    parser.add_argument("--labeling-decision-template-review-packet-report", type=Path)
    parser.add_argument(
        "--labeling-decision-template-output-root",
        type=Path,
        default=build_d1_labeling_decision_template.DEFAULT_OUTPUT_ROOT,
    )
    parser.add_argument("--labeling-decision-template-output-dir", type=Path)
    parser.add_argument("--labeling-decision-template-limit", type=int)
    parser.add_argument("--skip-labeling-decision-validation", action="store_true")
    parser.add_argument("--labeling-decision-validation-run-id")
    parser.add_argument("--labeling-decision-validation-template-report", type=Path)
    parser.add_argument(
        "--labeling-decision-validation-output-root",
        type=Path,
        default=validate_d1_labeling_decision_template.DEFAULT_OUTPUT_ROOT,
    )
    parser.add_argument("--labeling-decision-validation-output-dir", type=Path)
    parser.add_argument("--labeling-decision-validation-limit", type=int)
    parser.add_argument("--message-test-run-id", help="Message Hub test_run_id to export for PWR-001 analysis.")
    parser.add_argument("--power-export", type=Path, help="Existing Message Hub test_run_export.json to analyze.")
    parser.add_argument(
        "--field-power-samples",
        type=Path,
        help="Existing d1_field_samples.jsonl to convert into a PWR-001-compatible power export.",
    )
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
    parser.add_argument("--skip-training-chain", action="store_true")
    parser.add_argument(
        "--allow-synthetic-training-chain",
        action="store_true",
        help="Allow synthetic-only rows for TRAIN-003..008 dry-run integration reports.",
    )
    parser.add_argument("--training-run-output-root", type=Path, default=run_training_experiment_preflight.DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--training-run-id")
    parser.add_argument("--training-feature-output-root", type=Path, default=export_training_feature_manifest.DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--feature-set-id")
    parser.add_argument(
        "--training-runner-dry-run-output-root",
        type=Path,
        default=run_training_runner_dry_run.DEFAULT_OUTPUT_ROOT,
    )
    parser.add_argument("--runner-dry-run-id")
    parser.add_argument(
        "--training-baseline-eval-output-root",
        type=Path,
        default=run_training_baseline_eval.DEFAULT_OUTPUT_ROOT,
    )
    parser.add_argument("--baseline-eval-id")
    parser.add_argument(
        "--training-handoff-output-root",
        type=Path,
        default=build_training_handoff_bundle.DEFAULT_OUTPUT_ROOT,
    )
    parser.add_argument("--training-handoff-id")
    parser.add_argument(
        "--training-job-output-root",
        type=Path,
        default=create_training_job_plan.DEFAULT_OUTPUT_ROOT,
    )
    parser.add_argument("--training-job-id")
    parser.add_argument(
        "--training-job-runner-profile",
        default="local_runner_planned",
        choices=("local_runner_planned", "gpu_server_planned", "ci_dry_run"),
    )
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

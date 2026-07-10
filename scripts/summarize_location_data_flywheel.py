"""Build a D5 location-data flywheel status from D2 baseline evidence.

This is an offline, no-hardware control-plane tool. It consumes only the
bounded D2 `location_accuracy_report.json` summary, creates a location-specific
review packet, and writes a Dashboard-compatible `data_flywheel_status.json`.
It does not read raw field exports, copy private coordinates, train a model,
or create a training-ready dataset without explicit reviewed selections.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE_ROOT = REPO_ROOT / "reports" / "location_accuracy"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "reports" / "data_flywheel"
STATUS_JSON = "data_flywheel_status.json"
STATUS_MARKDOWN = "data_flywheel_status.md"
REVIEW_PACKET_JSON = "location_review_packet.json"
REVIEW_PACKET_MARKDOWN = "location_review_packet.md"
DATASET_MANIFEST_JSON = "location_dataset_manifest.json"
DATASET_MANIFEST_MARKDOWN = "location_dataset_manifest.md"
GENERATOR_NAME = "D5.location_data_flywheel"
GENERATOR_VERSION = "0.1.0"
STATUS_SCHEMA_VERSION = "egolink.data_flywheel_status.v0.1"
REVIEW_PACKET_SCHEMA_VERSION = "egolink.location_review_packet.v0.1"
DATASET_MANIFEST_SCHEMA_VERSION = "egolink.location_dataset_manifest.v0.1"
REVIEW_QUEUE_SCHEMA_VERSION = "egolink.location_review_queue.v0.1"
LOCATION_REVIEW_ACTIONS = ("mark_labelled", "exclude", "needs_more_capture")


class LocationDataFlywheelError(RuntimeError):
    """Raised when a location data-flywheel summary cannot be produced."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def int_or_zero(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def bool_flag(value: object) -> bool:
    return value is True or str(value).strip().lower() == "true"


def slugify(value: object) -> str:
    text = str(value or "unknown").strip().lower()
    text = re.sub(r"[^a-z0-9._-]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text[:96] or "unknown"


def stable_hash(value: str, length: int = 16) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:length]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_path_ref(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except (OSError, ValueError):
        return str(path)


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise LocationDataFlywheelError(f"Missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise LocationDataFlywheelError(f"Invalid JSON in {path}: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise LocationDataFlywheelError(f"Expected JSON object in {path}")
    return payload


def latest_baseline_report(root: Path) -> Path | None:
    candidates = [path for path in root.glob("**/location_accuracy_report.json") if path.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def default_run_id(baseline_report: Mapping[str, Any] | None, generated_at: str) -> str:
    if baseline_report:
        return "location-data-flywheel-" + slugify(baseline_report.get("run_id"))
    return "location-data-flywheel-" + slugify(generated_at.replace("+00:00", "Z"))


def source_report_ref(path: Path | None, report: Mapping[str, Any] | None) -> dict[str, Any]:
    if not path or not report:
        return {
            "type": "d2_location_accuracy_baseline",
            "available": False,
            "reason": "d2_location_accuracy_report_missing",
        }
    source = as_dict(report.get("source"))
    return {
        "type": "d2_location_accuracy_baseline",
        "available": True,
        "schema_version": report.get("schema_version"),
        "run_id": report.get("run_id"),
        "result_status": as_dict(report.get("result")).get("status"),
        "device_id": report.get("device_id") or source.get("device_id"),
        "firmware_version": source.get("firmware_version"),
        "report_path": safe_path_ref(path),
        "report_sha256": sha256_file(path),
    }


def review_record_id(run_id: str, candidate_type: str, key: str) -> str:
    return "locrev-" + stable_hash(f"{run_id}|{candidate_type}|{key}")


def base_review_record(
    *,
    report: Mapping[str, Any],
    source_ref: Mapping[str, Any],
    candidate_type: str,
    key: str,
    label: str,
    point: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    point = point or {}
    run_id = str(report.get("run_id") or "unknown")
    source = as_dict(report.get("source"))
    feature_groups = ["gnss", "ttff", "error_metrics", "field_reference"]
    if candidate_type == "location_no_fix":
        feature_groups = ["gnss", "transport", "failure_reason"]
    elif candidate_type == "location_bad_fix":
        feature_groups = ["gnss", "error_metrics", "eale_radius_comparison"]
    elif candidate_type == "location_known_place":
        feature_groups = ["gnss", "known_place", "field_reference"]
    return {
        "record_id": review_record_id(run_id, candidate_type, key),
        "session_id": run_id,
        "window_id": f"{slugify(key)}-summary",
        "state": "candidate",
        "candidate_type": candidate_type,
        "label": label,
        "label_review_state": "pending",
        "split_name": "unassigned",
        "split_leakage_checked": False,
        "privacy_class": "private_location_bounded_summary",
        "training_allowed": False,
        "quality_gate": "needs_review",
        "source_status": "d2_baseline_summary",
        "device_id": source.get("device_id"),
        "firmware_version": source.get("firmware_version"),
        "point_id": point.get("point_id"),
        "point_type": point.get("point_type"),
        "feature_groups": feature_groups,
        "source_report": {
            "type": source_ref.get("type"),
            "run_id": source_ref.get("run_id"),
            "report_sha256": source_ref.get("report_sha256"),
        },
        "available_actions": list(LOCATION_REVIEW_ACTIONS),
        "review_required": True,
        "review_reason": "location_sample_requires_label_privacy_quality_and_split_review",
    }


def location_review_records(report: Mapping[str, Any], source_ref: Mapping[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    run_id = str(report.get("run_id") or "unknown")
    metrics = as_dict(report.get("metrics"))
    per_point = [point for point in as_list(report.get("per_point")) if isinstance(point, dict)]
    for point in per_point:
        point_id = str(point.get("point_id") or "unknown")
        reference_record = base_review_record(
            report=report,
            source_ref=source_ref,
            candidate_type="location_reference_point",
            key=point_id,
            label="reference_point_quality",
            point=point,
        )
        reference_record["metrics_summary"] = {
            "attempts": point.get("attempts"),
            "fix_count": point.get("fix_count"),
            "fix_rate": point.get("fix_rate"),
            "ttff_p90_s": point.get("ttff_p90_s"),
            "p90_error_m": point.get("p90_error_m"),
            "outside_eale_radius_count": point.get("outside_eale_radius_count"),
        }
        records.append(reference_record)
        if "known" in str(point.get("point_type") or "").lower():
            records.append(
                base_review_record(
                    report=report,
                    source_ref=source_ref,
                    candidate_type="location_known_place",
                    key=f"{point_id}-known-place",
                    label="known_place_candidate",
                    point=point,
                )
            )
        if int_or_zero(point.get("outside_eale_radius_count")) > 0:
            bad_fix = base_review_record(
                report=report,
                source_ref=source_ref,
                candidate_type="location_bad_fix",
                key=f"{point_id}-bad-fix",
                label="bad_fix",
                point=point,
            )
            bad_fix["metrics_summary"] = {
                "p90_error_m": point.get("p90_error_m"),
                "outside_eale_radius_count": point.get("outside_eale_radius_count"),
            }
            records.append(bad_fix)

    if int_or_zero(metrics.get("no_fix_attempts")) > 0:
        no_fix = base_review_record(
            report=report,
            source_ref=source_ref,
            candidate_type="location_no_fix",
            key=f"{run_id}-no-fix",
            label="no_fix",
        )
        no_fix["metrics_summary"] = {
            "no_fix_attempts": metrics.get("no_fix_attempts"),
            "missing_observation_attempts": metrics.get("missing_observation_attempts"),
        }
        records.append(no_fix)

    if not records:
        records.append(
            base_review_record(
                report=report,
                source_ref=source_ref,
                candidate_type="location_baseline_review",
                key=f"{run_id}-baseline",
                label="baseline_needs_review",
            )
        )
    return records


def record_type_templates() -> dict[str, Any]:
    required_decisions = [
        "operator_label",
        "quality_reviewed",
        "privacy_reviewed",
        "training_allowed",
        "split_name",
        "split_leakage_checked",
        "candidate_decision",
    ]
    return {
        "location_reference_point": {
            "purpose": "review reference point quality and per-point metric usability",
            "required_decisions": required_decisions,
        },
        "location_known_place": {
            "purpose": "review whether a bounded sample can seed or verify a known-place memory",
            "required_decisions": required_decisions,
        },
        "location_no_fix": {
            "purpose": "label no-fix windows and failure reasons for robustness work",
            "required_decisions": required_decisions,
        },
        "location_bad_fix": {
            "purpose": "label high-error fixes that should drive rule/model correction",
            "required_decisions": required_decisions,
        },
        "location_field_session": {
            "purpose": "review a real field session summary before it can become D2/D5 evidence",
            "required_decisions": required_decisions,
        },
        "location_gnss_fix_window": {
            "purpose": "review GNSS fix windows that may seed D2 reference or quality work",
            "required_decisions": required_decisions,
        },
        "location_no_fix_window": {
            "purpose": "label no-fix field windows and likely failure context",
            "required_decisions": required_decisions,
        },
        "location_cell_transition_window": {
            "purpose": "review LTE/cell transition evidence with retention and privacy constraints",
            "required_decisions": required_decisions,
        },
        "location_power_window": {
            "purpose": "review field power windows before using them for product or model-power claims",
            "required_decisions": required_decisions,
        },
        "location_memory_coordinate_window": {
            "purpose": "review redacted coordinate-bearing windows before D2 reference or training use",
            "required_decisions": required_decisions,
        },
    }


def build_review_packet(
    *,
    generated_at: str,
    run_id: str,
    source_ref: Mapping[str, Any],
    review_records: list[dict[str, Any]],
) -> dict[str, Any]:
    type_counts = Counter(str(record.get("candidate_type") or "unknown") for record in review_records)
    return {
        "schema_version": REVIEW_PACKET_SCHEMA_VERSION,
        "generator": {"name": GENERATOR_NAME, "version": GENERATOR_VERSION},
        "run_id": run_id,
        "generated_at": generated_at,
        "source_reports": [dict(source_ref)],
        "status": "needs_review" if review_records else "needs_d2_baseline",
        "review_records": review_records,
        "record_type_counts": dict(sorted(type_counts.items())),
        "record_type_templates": record_type_templates(),
        "selection_policy": {
            "default_training_allowed": False,
            "manifest_requires_explicit_selection": True,
            "manifest_requires_privacy_review": True,
            "manifest_requires_split_leakage_review": True,
            "manifest_requires_quality_review": True,
        },
        "non_claims": [
            "No model training has run.",
            "No location model has been evaluated or deployed.",
            "No raw private coordinates are included in this review packet.",
            "No record is training-allowed until explicit consent, privacy, quality, and split review select it.",
        ],
    }


def load_selection(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    payload = load_json(path)
    records = payload.get("selected_records")
    if records is None:
        records = payload.get("records")
    if not isinstance(records, list):
        raise LocationDataFlywheelError("Selection file must contain selected_records or records list")
    return [record for record in records if isinstance(record, dict)]


def selection_blockers(selection: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    if not bool_flag(selection.get("training_allowed")):
        blockers.append("training_not_explicitly_allowed")
    if not bool_flag(selection.get("privacy_reviewed")):
        blockers.append("privacy_review_missing")
    if not bool_flag(selection.get("quality_reviewed")):
        blockers.append("quality_review_missing")
    if not bool_flag(selection.get("split_leakage_checked")):
        blockers.append("split_leakage_review_missing")
    split_name = str(selection.get("split_name") or "unassigned")
    if split_name in {"", "unassigned", "unknown"}:
        blockers.append("split_not_assigned")
    if str(selection.get("candidate_decision") or "") not in {"ready_for_dataset", "ready_for_candidate_store"}:
        blockers.append("candidate_decision_not_ready")
    return blockers


def build_dataset_manifest(
    *,
    generated_at: str,
    run_id: str,
    source_ref: Mapping[str, Any],
    review_records: list[dict[str, Any]],
    selections: list[dict[str, Any]],
) -> dict[str, Any]:
    records_by_id = {str(record.get("record_id")): record for record in review_records}
    selected_records: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for selection in selections:
        record_id = str(selection.get("record_id") or "")
        review_record = records_by_id.get(record_id)
        if review_record is None:
            rejected.append({"record_id": record_id or "unknown", "blockers": ["review_record_not_found"]})
            continue
        blockers = selection_blockers(selection)
        if blockers:
            rejected.append({"record_id": record_id, "blockers": blockers})
            continue
        selected_records.append(
            {
                "record_id": record_id,
                "session_id": review_record.get("session_id"),
                "window_id": review_record.get("window_id"),
                "candidate_type": review_record.get("candidate_type"),
                "label": selection.get("operator_label") or review_record.get("label"),
                "label_source": "operator_review_packet",
                "label_confidence": "reviewed",
                "split_name": selection.get("split_name"),
                "split_strategy": selection.get("split_strategy") or "session_place_time_blocked",
                "split_leakage_checked": True,
                "privacy_class": review_record.get("privacy_class"),
                "privacy_reviewed": True,
                "quality_reviewed": True,
                "training_allowed": True,
                "feature_groups": review_record.get("feature_groups") or [],
                "source_report_hash": as_dict(review_record.get("source_report")).get("report_sha256"),
            }
        )

    if selected_records:
        status = "ready_for_evaluation_handoff"
        reason = "explicit_selected_privacy_reviewed_samples_available"
    elif selections:
        status = "not_ready"
        reason = "selection_records_blocked"
    else:
        status = "not_ready"
        reason = "explicit_selection_missing"

    split_counts = Counter(str(record.get("split_name") or "unknown") for record in selected_records)
    return {
        "schema_version": DATASET_MANIFEST_SCHEMA_VERSION,
        "generator": {"name": GENERATOR_NAME, "version": GENERATOR_VERSION},
        "manifest_id": f"{run_id}-dataset-manifest",
        "generated_at": generated_at,
        "status": status,
        "reason": reason,
        "source_reports": [dict(source_ref)],
        "records": selected_records,
        "rejected_selections": rejected,
        "counts": {
            "review_records_total": len(review_records),
            "selection_records_total": len(selections),
            "eligible_records": len(selected_records),
            "rejected_selection_records": len(rejected),
        },
        "split_counts": dict(sorted(split_counts.items())),
        "training_server": {
            "ready_for_handoff": bool(selected_records),
            "runner_integration": "not_integrated",
            "experiment_id": None,
        },
        "readiness_gate": {
            "model_training_ready": False,
            "reason": "founder_model_task_approval_required" if selected_records else reason,
        },
        "privacy": {
            "raw_coordinates_exposed": False,
            "exact_coordinates_copied": False,
            "training_allowed_default": False,
        },
        "non_claims": [
            "This manifest is not a model-training run.",
            "No model weights, metrics, footprint, power, or device deployment evidence is produced.",
            "Records appear only after explicit review selections; raw private coordinates remain excluded.",
        ],
    }


def status_from_artifacts(
    *,
    generated_at: str,
    run_id: str,
    source_ref: Mapping[str, Any],
    review_records: list[dict[str, Any]],
    dataset_manifest: Mapping[str, Any],
    baseline_report: Mapping[str, Any] | None,
) -> dict[str, Any]:
    type_counts = Counter(str(record.get("candidate_type") or "unknown") for record in review_records)
    state_counts = Counter(str(record.get("state") or "unknown") for record in review_records)
    quality_gate_counts = Counter(str(record.get("quality_gate") or "unknown") for record in review_records)
    label_counts = Counter(str(record.get("label_review_state") or "unknown") for record in review_records)
    pending_records = len([record for record in review_records if record.get("label_review_state") == "pending"])
    dataset_ready = dataset_manifest.get("status") == "ready_for_evaluation_handoff"
    baseline_available = bool(source_ref.get("available"))
    result_status = as_dict(baseline_report.get("result") if baseline_report else {}).get("status")
    metrics = as_dict(baseline_report.get("metrics") if baseline_report else {})

    warnings: list[str] = []
    blockers: list[str] = []
    if not baseline_available:
        warnings.append("d2_baseline_report_missing")
        blockers.append("d2_baseline_report_missing")
    if result_status and result_status != "PASS":
        warnings.append("d2_baseline_result_not_pass")
    if pending_records:
        blockers.extend(["label_review_pending", "privacy_review_pending", "split_leakage_review_pending"])
    if not dataset_ready:
        blockers.append(str(dataset_manifest.get("reason") or "dataset_manifest_not_ready"))
    blockers.append("founder_model_task_approval_required")

    if not baseline_available:
        status = "needs_d2_baseline"
        pipeline_stage = "d2_baseline_missing"
        next_step = "Run a D2 location accuracy baseline report, then rerun this location data-flywheel summary."
    elif dataset_ready:
        status = "ready_for_evaluation_handoff"
        pipeline_stage = "location_dataset_manifest_ready"
        next_step = "Founder review is required before opening a model-training task from this manifest."
    else:
        status = "needs_review"
        pipeline_stage = "location_review_packet_pending"
        next_step = "Review the location review packet, then create an explicit selection file before dataset/model work."

    return {
        "schema_version": STATUS_SCHEMA_VERSION,
        "builder_version": "d5-location.0",
        "run_id": run_id,
        "generated_at": generated_at,
        "status": status,
        "pipeline_stage": pipeline_stage,
        "source_reports": [dict(source_ref)],
        "candidate_store": {
            "available": False,
            "reason": "location_file_review_packet_only",
            "schema_version": REVIEW_PACKET_SCHEMA_VERSION,
            "latest_updated_at": generated_at,
        },
        "counts": {
            "sessions_total": 1 if baseline_available else 0,
            "records_total": len(review_records),
            "needs_review_records": pending_records,
            "training_allowed_records": int_or_zero(as_dict(dataset_manifest.get("counts")).get("eligible_records")),
            "reviewed_training_candidate_records": int_or_zero(
                as_dict(dataset_manifest.get("counts")).get("eligible_records")
            ),
            "experiment_input_records": 0,
            "location_baseline_reports": 1 if baseline_available else 0,
            "reference_points": int_or_zero(metrics.get("reference_point_count")),
            "location_attempts": int_or_zero(metrics.get("attempt_count")),
            "fixed_attempts": int_or_zero(metrics.get("fixed_attempts")),
            "no_fix_attempts": int_or_zero(metrics.get("no_fix_attempts")),
        },
        "state_counts": dict(sorted(state_counts.items())),
        "candidate_type_counts": dict(sorted(type_counts.items())),
        "quality_gate_counts": dict(sorted(quality_gate_counts.items())),
        "label_review_state_counts": dict(sorted(label_counts.items())),
        "review": {
            "label_review_pending_records": pending_records,
            "split_leakage_unchecked_records": pending_records,
            "privacy_or_consent_blocked_records": pending_records,
            "quality_blocked_records": 0,
        },
        "review_queue": {
            "schema_version": REVIEW_QUEUE_SCHEMA_VERSION,
            "available": baseline_available,
            "pending_records": pending_records,
            "sample_records": review_records[:5],
            "available_actions": list(LOCATION_REVIEW_ACTIONS),
        },
        "readiness": {
            "model_training_ready": False,
            "reason": "founder_model_task_approval_required" if dataset_ready else "labelled_privacy_reviewed_d2_samples_missing",
            "dataset_manifest_ready": dataset_ready,
            "training_server_ready": False,
            "on_device_deployment_ready": False,
        },
        "warnings": sorted(set(warnings)),
        "blockers": sorted(set(blockers)),
        "next_step": next_step,
        "non_claims": [
            "No location model training has run.",
            "No on-device model has been deployed.",
            "No model accuracy, power, or product positioning claim is made.",
            "The Dashboard summary contains review state and counts only, not raw private coordinates.",
        ],
    }


def build_location_data_flywheel(
    *,
    baseline_report_path: Path | None,
    selection_path: Path | None = None,
    generated_at: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    generated = generated_at or utc_now()
    baseline_report = load_json(baseline_report_path) if baseline_report_path else None
    actual_run_id = run_id or default_run_id(baseline_report, generated)
    source_ref = source_report_ref(baseline_report_path, baseline_report)
    review_records = location_review_records(baseline_report, source_ref) if baseline_report else []
    selections = load_selection(selection_path)
    review_packet = build_review_packet(
        generated_at=generated,
        run_id=actual_run_id,
        source_ref=source_ref,
        review_records=review_records,
    )
    dataset_manifest = build_dataset_manifest(
        generated_at=generated,
        run_id=actual_run_id,
        source_ref=source_ref,
        review_records=review_records,
        selections=selections,
    )
    status = status_from_artifacts(
        generated_at=generated,
        run_id=actual_run_id,
        source_ref=source_ref,
        review_records=review_records,
        dataset_manifest=dataset_manifest,
        baseline_report=baseline_report,
    )
    return {
        "data_flywheel_status": status,
        "review_packet": review_packet,
        "dataset_manifest": dataset_manifest,
    }


def render_status_markdown(status: Mapping[str, Any]) -> str:
    counts = as_dict(status.get("counts"))
    review = as_dict(status.get("review"))
    readiness = as_dict(status.get("readiness"))
    review_queue = as_dict(status.get("review_queue"))
    lines = [
        "# D5 Location Data Flywheel Status",
        "",
        f"- Run ID: {status.get('run_id', 'unknown')}",
        f"- Generated at: {status.get('generated_at', 'unknown')}",
        f"- Status: {status.get('status', 'unknown')}",
        f"- Pipeline stage: {status.get('pipeline_stage', 'unknown')}",
        f"- Baseline reports: {counts.get('location_baseline_reports', 0)}",
        f"- Reference points: {counts.get('reference_points', 0)}",
        f"- Location attempts: {counts.get('location_attempts', 0)}",
        f"- Fixed / no-fix attempts: {counts.get('fixed_attempts', 0)} / {counts.get('no_fix_attempts', 0)}",
        f"- Field evidence: {counts.get('location_field_evidence_reports', 0)} reports / {counts.get('field_samples', 0)} samples",
        f"- Field GNSS: {counts.get('field_gnss_fix_samples', 0)} fix / {counts.get('field_gnss_no_fix_samples', 0)} no-fix / {counts.get('field_gnss_unknown_samples', 0)} unknown",
        f"- Review records: {counts.get('records_total', 0)}",
        f"- Model training ready: {readiness.get('model_training_ready', False)} ({readiness.get('reason', 'unknown')})",
        "",
        "## Review Queues",
        "",
        f"- Label review pending: {review.get('label_review_pending_records', 0)}",
        f"- Split leakage unchecked: {review.get('split_leakage_unchecked_records', 0)}",
        f"- Privacy/consent blocked: {review.get('privacy_or_consent_blocked_records', 0)}",
        f"- Bounded review queue: {review_queue.get('pending_records', 0)}",
        "",
        "## Counts",
        "",
        f"- Candidate types: {json.dumps(status.get('candidate_type_counts', {}), ensure_ascii=False, sort_keys=True)}",
        f"- Label states: {json.dumps(status.get('label_review_state_counts', {}), ensure_ascii=False, sort_keys=True)}",
        f"- Blockers: {', '.join(status.get('blockers', []) or []) or 'none'}",
        "",
        "## Next Step",
        "",
        str(status.get("next_step") or "Continue the next location data-flywheel task."),
        "",
        "## Review Queue Samples",
        "",
    ]
    for item in review_queue.get("sample_records", []) or []:
        lines.append(
            f"- {item.get('record_id', 'unknown')}: {item.get('candidate_type', 'unknown')} / "
            f"{item.get('label', 'unknown')} / split {item.get('split_name', 'unknown')} / "
            f"label_review {item.get('label_review_state', 'unknown')}"
        )
    if not review_queue.get("sample_records"):
        lines.append("- none")
    lines += ["", "## Non-Claims", ""]
    for item in status.get("non_claims", []) or []:
        lines.append(f"- {item}")
    lines += [
        "",
        "This report contains only bounded counts, review state, and artifact refs. It does not contain raw field exports, raw payload bytes, exact private coordinates, or model artifacts.",
        "",
    ]
    return "\n".join(lines)


def render_review_packet_markdown(packet: Mapping[str, Any]) -> str:
    lines = [
        "# D5 Location Review Packet",
        "",
        f"- Run ID: {packet.get('run_id', 'unknown')}",
        f"- Generated at: {packet.get('generated_at', 'unknown')}",
        f"- Status: {packet.get('status', 'unknown')}",
        f"- Review records: {len(packet.get('review_records', []) or [])}",
        f"- Record types: {json.dumps(packet.get('record_type_counts', {}), ensure_ascii=False, sort_keys=True)}",
        "",
        "## Review Records",
        "",
    ]
    for item in packet.get("review_records", []) or []:
        lines.append(
            f"- {item.get('record_id', 'unknown')}: {item.get('candidate_type', 'unknown')} / "
            f"{item.get('label', 'unknown')} / point {item.get('point_id') or 'aggregate'} / "
            f"{item.get('review_reason', 'needs_review')}"
        )
    if not packet.get("review_records"):
        lines.append("- none")
    lines += [
        "",
        "## Supported Record Types",
        "",
    ]
    for key, template in as_dict(packet.get("record_type_templates")).items():
        lines.append(f"- {key}: {as_dict(template).get('purpose', 'unknown')}")
    lines += ["", "## Non-Claims", ""]
    for item in packet.get("non_claims", []) or []:
        lines.append(f"- {item}")
    lines += [
        "",
        "This packet is a labeling/review worklist only. It excludes raw private coordinates and cannot be used as training input until explicit reviewed selections create a dataset manifest.",
        "",
    ]
    return "\n".join(lines)


def render_dataset_manifest_markdown(manifest: Mapping[str, Any]) -> str:
    counts = as_dict(manifest.get("counts"))
    lines = [
        "# D5 Location Dataset Manifest Gate",
        "",
        f"- Manifest ID: {manifest.get('manifest_id', 'unknown')}",
        f"- Generated at: {manifest.get('generated_at', 'unknown')}",
        f"- Status: {manifest.get('status', 'unknown')}",
        f"- Reason: {manifest.get('reason', 'unknown')}",
        f"- Review records: {counts.get('review_records_total', 0)}",
        f"- Selection records: {counts.get('selection_records_total', 0)}",
        f"- Eligible records: {counts.get('eligible_records', 0)}",
        f"- Rejected selections: {counts.get('rejected_selection_records', 0)}",
        "",
        "## Records",
        "",
    ]
    for item in manifest.get("records", []) or []:
        lines.append(
            f"- {item.get('record_id', 'unknown')}: {item.get('candidate_type', 'unknown')} / "
            f"{item.get('label', 'unknown')} / split {item.get('split_name', 'unknown')}"
        )
    if not manifest.get("records"):
        lines.append("- none")
    lines += [
        "",
        "## Training Server",
        "",
        f"- Ready for handoff: {as_dict(manifest.get('training_server')).get('ready_for_handoff', False)}",
        f"- Runner integration: {as_dict(manifest.get('training_server')).get('runner_integration', 'unknown')}",
        "",
        "## Non-Claims",
        "",
    ]
    for item in manifest.get("non_claims", []) or []:
        lines.append(f"- {item}")
    lines += [
        "",
        "This manifest gate contains selected bounded summaries only. It does not train a model, call a runner, expose raw coordinates, or deploy on-device inference.",
        "",
    ]
    return "\n".join(lines)


def write_location_data_flywheel_report(bundle: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    status_path = output_dir / STATUS_JSON
    status_markdown_path = output_dir / STATUS_MARKDOWN
    packet_path = output_dir / REVIEW_PACKET_JSON
    packet_markdown_path = output_dir / REVIEW_PACKET_MARKDOWN
    manifest_path = output_dir / DATASET_MANIFEST_JSON
    manifest_markdown_path = output_dir / DATASET_MANIFEST_MARKDOWN

    review_packet = dict(as_dict(bundle.get("review_packet")))
    dataset_manifest = dict(as_dict(bundle.get("dataset_manifest")))
    status = dict(as_dict(bundle.get("data_flywheel_status")))
    review_packet["paths"] = {
        "location_review_packet_json": safe_path_ref(packet_path),
        "location_review_packet_markdown": safe_path_ref(packet_markdown_path),
    }
    dataset_manifest["paths"] = {
        "location_dataset_manifest_json": safe_path_ref(manifest_path),
        "location_dataset_manifest_markdown": safe_path_ref(manifest_markdown_path),
    }
    status["paths"] = {
        "data_flywheel_status_json": safe_path_ref(status_path),
        "data_flywheel_status_markdown": safe_path_ref(status_markdown_path),
        "location_review_packet_json": safe_path_ref(packet_path),
        "location_review_packet_markdown": safe_path_ref(packet_markdown_path),
        "location_dataset_manifest_json": safe_path_ref(manifest_path),
        "location_dataset_manifest_markdown": safe_path_ref(manifest_markdown_path),
    }

    write_json(packet_path, review_packet)
    packet_markdown_path.write_text(render_review_packet_markdown(review_packet), encoding="utf-8")
    write_json(manifest_path, dataset_manifest)
    manifest_markdown_path.write_text(render_dataset_manifest_markdown(dataset_manifest), encoding="utf-8")
    write_json(status_path, status)
    status_markdown_path.write_text(render_status_markdown(status), encoding="utf-8")
    return {
        "data_flywheel_status": status,
        "review_packet": review_packet,
        "dataset_manifest": dataset_manifest,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-report", type=Path, help="D2 location_accuracy_report.json to summarize.")
    parser.add_argument(
        "--baseline-root",
        type=Path,
        default=DEFAULT_BASELINE_ROOT,
        help="Root searched for the latest D2 location_accuracy_report.json when --baseline-report is omitted.",
    )
    parser.add_argument(
        "--selection",
        type=Path,
        help="Optional explicit review selection JSON. Without it, the dataset manifest remains not_ready.",
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-id", help="Stable report directory name.")
    parser.add_argument("--generated-at", help="UTC ISO timestamp for deterministic reports.")
    parser.add_argument("--json", action="store_true", help="Print the Dashboard data_flywheel_status JSON.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    baseline_report_path = args.baseline_report
    if baseline_report_path is None:
        baseline_report_path = latest_baseline_report(args.baseline_root)
    try:
        generated = args.generated_at or utc_now()
        preview_report = load_json(baseline_report_path) if baseline_report_path else None
        run_id = args.run_id or default_run_id(preview_report, generated)
        bundle = build_location_data_flywheel(
            baseline_report_path=baseline_report_path,
            selection_path=args.selection,
            generated_at=generated,
            run_id=run_id,
        )
        written = write_location_data_flywheel_report(bundle, args.output_root / run_id)
    except LocationDataFlywheelError as exc:
        print(f"FAIL D5 location data flywheel: {exc}", file=sys.stderr)
        return 1

    status = as_dict(written.get("data_flywheel_status"))
    if args.json:
        print(json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        counts = as_dict(status.get("counts"))
        paths = as_dict(status.get("paths"))
        print(f"D5 location data flywheel: {status.get('status')} run_id={status.get('run_id')}")
        print(f"Report: {paths.get('data_flywheel_status_markdown')}")
        print(f"Review records: {counts.get('records_total', 0)}")
        print(f"Dataset manifest ready: {as_dict(status.get('readiness')).get('dataset_manifest_ready', False)}")
        print(f"Model training ready: {as_dict(status.get('readiness')).get('model_training_ready', False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

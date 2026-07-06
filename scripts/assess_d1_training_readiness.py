"""Assess whether a D1 field observation is ready for training-candidate review.

This command reads bounded D1 field-observation report/status summaries and
writes a compact readiness report for the DATA/D5 flywheel. It does not read
sample JSONL contents, contact hardware, call the Message Hub, generate
training samples, train/evaluate a model, or make location/power claims.
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


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIELD_OBSERVATION_ROOT = REPO_ROOT / "reports" / "d1_field_observation"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "reports" / "d1_training_readiness"
SCHEMA_VERSION = "egolink.d1_training_readiness.v0.1"
BUILDER_VERSION = "data-022.0"


class D1TrainingReadinessError(RuntimeError):
    """Raised when a bounded readiness report cannot be built."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def timestamp_slug(value: str) -> str:
    return (
        value.replace("+00:00", "Z")
        .replace("+0000", "Z")
        .replace(":", "")
        .replace("-", "")
        .replace(".", "")
        .replace("T", "-")
    )


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def int_or_zero(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return 0


def number_or_none(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def unique_text(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in (None, ""):
            continue
        text = str(value)
        if text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise D1TrainingReadinessError(f"{path} must contain a JSON object")
    return payload


def relative_path(path: Path | None, *, base: Path | None = None) -> str | None:
    if path is None:
        return None
    resolved = path.resolve()
    for root in (base, REPO_ROOT):
        if root is None:
            continue
        try:
            return resolved.relative_to(root.resolve()).as_posix()
        except (OSError, ValueError):
            continue
    return path.name


def latest_path(root: Path, pattern: str) -> Path | None:
    if not root.is_dir():
        return None
    candidates = [item for item in root.glob(pattern) if item.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda item: item.stat().st_mtime)


def default_run_id(observation_run_id: str | None, generated_at: str) -> str:
    if observation_run_id:
        return f"{observation_run_id}-training-readiness"
    return f"d1-training-readiness-{timestamp_slug(generated_at)[:16].rstrip('-')}"


def resolve_observation_paths(args: argparse.Namespace) -> tuple[Path | None, Path | None]:
    report_path = args.field_observation_report
    status_path = args.field_observation_status
    if report_path is None and status_path is None:
        report_path = latest_path(args.field_observation_root, "**/d1_field_observation_report.json")
    if status_path is None:
        status_path = latest_path(args.field_observation_root, "**/d1_field_observation_status.json")
    return report_path, status_path


def choose_source(report_path: Path | None, status_path: Path | None) -> tuple[str, Path, dict[str, Any]]:
    if report_path is not None and report_path.is_file():
        return "report", report_path, load_json(report_path)
    if status_path is not None and status_path.is_file():
        return "status", status_path, load_json(status_path)
    raise D1TrainingReadinessError("no D1 field-observation report or status summary found")


def observation_summary(source: str, payload: Mapping[str, Any], *, source_path: Path) -> dict[str, Any]:
    if source == "report":
        summary = as_dict(payload.get("summary"))
        return {
            "source": "field_observation_report",
            "run_id": payload.get("run_id"),
            "result": payload.get("result"),
            "status": "completed",
            "created_at": payload.get("created_at"),
            "device_id": payload.get("device_id"),
            "sample_count": int_or_zero(summary.get("sample_count")),
            "successful_sample_count": int_or_zero(summary.get("successful_sample_count")),
            "fetch_error_count": int_or_zero(summary.get("fetch_error_count")),
            "stale_sample_count": int_or_zero(summary.get("stale_sample_count")),
            "coordinate_sample_count": int_or_zero(summary.get("coordinate_sample_count")),
            "latest_seq": int_or_zero(summary.get("last_seq")),
            "max_freshness_s": number_or_none(summary.get("max_freshness_s")),
            "first_location_upload_at": summary.get("first_location_upload_at"),
            "last_location_upload_at": summary.get("last_location_upload_at"),
            "first_device_upload_at": summary.get("first_device_upload_at"),
            "last_device_upload_at": summary.get("last_device_upload_at"),
            "raw_post_success_delta": int_or_zero(summary.get("raw_post_success_delta")),
            "raw_post_failure_delta": int_or_zero(summary.get("raw_post_failure_delta")),
            "location_event_count_delta": int_or_zero(summary.get("location_event_count_delta")),
            "power_sample_count_delta": int_or_zero(summary.get("power_sample_count_delta")),
            "map_modes": unique_text(as_list(summary.get("map_modes"))),
            "cell_registration_states": unique_text(as_list(summary.get("cell_registration_states"))),
            "cell_pdp_states": unique_text(as_list(summary.get("cell_pdp_states"))),
            "gnss_states": unique_text(as_list(summary.get("gnss_states"))),
            "imu_evidence_statuses": unique_text(as_list(summary.get("imu_evidence_statuses"))),
            "power_evidence_statuses": unique_text(as_list(summary.get("power_evidence_statuses"))),
            "report_path": relative_path(source_path),
            "status_path": relative_path(source_path.with_name("d1_field_observation_status.json"))
            if source_path.with_name("d1_field_observation_status.json").exists()
            else None,
            "samples_jsonl_read": False,
        }

    return {
        "source": "field_observation_status",
        "run_id": payload.get("run_id"),
        "result": payload.get("result"),
        "status": payload.get("status") or "running",
        "created_at": None,
        "updated_at": payload.get("updated_at"),
        "device_id": payload.get("device_id"),
        "sample_count": int_or_zero(payload.get("sample_count")),
        "planned_sample_count": int_or_zero(payload.get("planned_sample_count")),
        "successful_sample_count": int_or_zero(payload.get("successful_sample_count")),
        "fetch_error_count": int_or_zero(payload.get("fetch_error_count")),
        "latest_seq": int_or_zero(payload.get("latest_seq")),
        "max_freshness_s": number_or_none(payload.get("latest_freshness_s")),
        "last_location_upload_at": payload.get("latest_location_upload_at"),
        "raw_post_success_delta": 0,
        "raw_post_failure_delta": 0,
        "location_event_count_delta": 0,
        "power_sample_count_delta": 0,
        "map_modes": [],
        "cell_registration_states": [],
        "cell_pdp_states": [],
        "gnss_states": [],
        "imu_evidence_statuses": [],
        "power_evidence_statuses": [],
        "report_path": relative_path(Path(str(payload.get("report_path") or ""))) if payload.get("report_path") else None,
        "status_path": relative_path(source_path),
        "samples_jsonl_read": False,
    }


def gate(status: str, reason: str, *, evidence: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {"status": status, "reason": reason, "evidence": dict(evidence or {})}


def build_readiness(
    observation: Mapping[str, Any],
    *,
    generated_at: str,
    run_id: str,
    output_dir: Path,
) -> dict[str, Any]:
    sample_count = int_or_zero(observation.get("sample_count"))
    successful_count = int_or_zero(observation.get("successful_sample_count"))
    fetch_errors = int_or_zero(observation.get("fetch_error_count"))
    stale_samples = int_or_zero(observation.get("stale_sample_count"))
    raw_ok = int_or_zero(observation.get("raw_post_success_delta"))
    raw_fail = int_or_zero(observation.get("raw_post_failure_delta"))
    coordinate_samples = int_or_zero(observation.get("coordinate_sample_count"))
    power_delta = int_or_zero(observation.get("power_sample_count_delta"))
    location_delta = int_or_zero(observation.get("location_event_count_delta"))
    max_freshness = number_or_none(observation.get("max_freshness_s"))
    map_modes = unique_text(as_list(observation.get("map_modes")))
    cell_registration = unique_text(as_list(observation.get("cell_registration_states")))
    cell_pdp = unique_text(as_list(observation.get("cell_pdp_states")))
    gnss_states = unique_text(as_list(observation.get("gnss_states")))
    imu_statuses = unique_text(as_list(observation.get("imu_evidence_statuses")))
    power_statuses = unique_text(as_list(observation.get("power_evidence_statuses")))

    capture_ok = successful_count > 0
    transport_ok = raw_fail == 0 and (
        raw_ok > 0 or str(observation.get("status")) == "running" or successful_count > 0
    )
    freshness_ok = max_freshness is None or max_freshness <= 180
    lte_seen = "registered_home" in cell_registration or bool(cell_registration)
    pdp_seen = "active" in cell_pdp or bool(cell_pdp)
    power_measured = "measured" in power_statuses or power_delta > 0
    imu_real = any(status not in {"mock", "unverified", "unknown"} for status in imu_statuses)
    gnss_fix_seen = any(state in {"fix", "fixed", "observed"} for state in gnss_states)
    ready_for_labeling = capture_ok and transport_ok and freshness_ok

    gates = {
        "field_observation": gate(
            "pass" if capture_ok else "blocked",
            "field_observation_summary_has_successful_samples" if capture_ok else "no_successful_observation_samples",
            evidence={"sample_count": sample_count, "successful_sample_count": successful_count, "fetch_error_count": fetch_errors},
        ),
        "transport": gate(
            "pass" if transport_ok else "blocked",
            "raw_post_failures_absent" if transport_ok else "raw_post_failures_or_no_transport_progress",
            evidence={
                "raw_post_success_delta": raw_ok,
                "raw_post_failure_delta": raw_fail,
                "cell_registration_states": cell_registration,
                "cell_pdp_states": cell_pdp,
            },
        ),
        "freshness": gate(
            "pass" if freshness_ok else "warn",
            "fresh_enough_for_review" if freshness_ok else "observation_freshness_exceeded_review_threshold",
            evidence={"max_freshness_s": max_freshness, "stale_sample_count": stale_samples},
        ),
        "location_evidence": gate(
            "warn" if not gnss_fix_seen else "pass",
            "gnss_fix_not_required_for_labeling_but_needed_for_accuracy_metrics"
            if not gnss_fix_seen
            else "gnss_fix_seen_in_observation_summary",
            evidence={
                "coordinate_sample_count": coordinate_samples,
                "location_event_count_delta": location_delta,
                "map_modes": map_modes,
                "gnss_states": gnss_states,
                "coordinate_values_copied": False,
            },
        ),
        "sensor_quality": gate(
            "warn" if not imu_real else "pass",
            "imu_mock_or_unverified_in_field_summary" if not imu_real else "imu_real_status_seen",
            evidence={"imu_evidence_statuses": imu_statuses, "power_evidence_statuses": power_statuses},
        ),
        "privacy": gate(
            "blocked",
            "privacy_review_required_before_training_use",
            evidence={"training_allowed": False, "private_coordinates_copied": False},
        ),
        "labels": gate(
            "blocked",
            "operator_or_user_labels_missing",
            evidence={"label_review_state": "missing"},
        ),
        "split_leakage": gate(
            "blocked",
            "split_plan_missing_for_real_field_data",
            evidence={"split_leakage_checked": False},
        ),
        "model_training": gate("not_run", "no_training_started"),
        "model_artifact": gate("not_produced", "no_model_artifact_written"),
        "release_claim": gate("not_allowed", "readiness_report_is_not_product_metric"),
    }

    blockers = [
        "privacy_review_required",
        "training_consent_not_granted",
        "operator_or_user_labels_missing",
        "split_plan_missing",
    ]
    quality_gaps: list[str] = []
    if not lte_seen:
        quality_gaps.append("lte_registration_summary_missing")
    if not pdp_seen:
        quality_gaps.append("pdp_state_summary_missing")
    if not power_measured:
        quality_gaps.append("measured_power_delta_or_status_missing")
    if not gnss_fix_seen:
        quality_gaps.append("gnss_fix_not_seen")
    if not imu_real:
        quality_gaps.append("imu_real_evidence_missing")
    if raw_fail:
        blockers.append("raw_post_failures_seen")
    if not capture_ok:
        blockers.append("field_observation_samples_missing")

    if not capture_ok or not transport_ok:
        status = "needs_capture"
        reason = "field_observation_not_ready_for_labeling_review"
    elif ready_for_labeling:
        status = "ready_for_labeling_review"
        reason = "field_observation_can_enter_human_review_but_not_training"
    else:
        status = "needs_capture"
        reason = "field_observation_needs_fresher_capture_before_review"

    report_path = output_dir / "d1_training_readiness.json"
    markdown_path = output_dir / "d1_training_readiness.md"
    return {
        "tool": "assess_d1_training_readiness",
        "schema_version": SCHEMA_VERSION,
        "builder_version": BUILDER_VERSION,
        "run_id": run_id,
        "generated_at": generated_at,
        "serves_demo": "D5",
        "status": status,
        "reason": reason,
        "source_observation": dict(observation),
        "evidence_coverage": {
            "capture": {
                "sample_count": sample_count,
                "successful_sample_count": successful_count,
                "fetch_error_count": fetch_errors,
                "ready_for_review": capture_ok,
            },
            "transport": {
                "raw_post_success_delta": raw_ok,
                "raw_post_failure_delta": raw_fail,
                "lte_registration_seen": lte_seen,
                "pdp_active_seen": pdp_seen,
            },
            "location": {
                "coordinate_sample_count": coordinate_samples,
                "location_event_count_delta": location_delta,
                "map_modes": map_modes,
                "gnss_states": gnss_states,
                "gnss_fix_seen": gnss_fix_seen,
                "coordinate_values_copied": False,
                "accuracy_claimed": False,
            },
            "sensors": {
                "imu_evidence_statuses": imu_statuses,
                "power_evidence_statuses": power_statuses,
                "power_measured_seen": power_measured,
                "real_imu_seen": imu_real,
            },
        },
        "readiness": {
            "ready_for_labeling_review": ready_for_labeling,
            "ready_for_training_handoff": False,
            "training_allowed": False,
            "consent_status": "not_reviewed",
            "privacy_review": "required",
            "label_review_state": "missing",
            "split_leakage_checked": False,
            "quality_gaps": quality_gaps,
            "blockers": blockers,
        },
        "gates": gates,
        "scope": {
            "sample_jsonl_read": False,
            "message_hub_contacted": False,
            "hardware_contacted": False,
            "firmware_changed": False,
            "commands_sent": False,
            "training_samples_written": False,
            "model_training_started": False,
            "model_artifact_written": False,
            "location_accuracy_claimed": False,
            "battery_life_claimed": False,
            "release_claim_allowed": False,
        },
        "next_step": (
            "Attach operator/user labels, privacy review, training consent, and a split plan before exporting "
            "real D1 records into the training-candidate handoff."
        ),
        "paths": {
            "d1_training_readiness_json": relative_path(report_path),
            "d1_training_readiness_markdown": relative_path(markdown_path),
        },
        "non_claims": [
            "This report does not contain raw sample JSONL, raw payload bytes, exact coordinate values, candidate DBs, feature rows, or model artifacts.",
            "It does not train or evaluate a model, measure model footprint or power, deploy to a device, or permit release claims.",
        ],
    }


def write_markdown(payload: Mapping[str, Any], path: Path) -> None:
    source = as_dict(payload.get("source_observation"))
    coverage = as_dict(payload.get("evidence_coverage"))
    transport = as_dict(coverage.get("transport"))
    location = as_dict(coverage.get("location"))
    readiness = as_dict(payload.get("readiness"))
    lines = [
        "# D1 Training Readiness",
        "",
        f"- Status: {payload.get('status')}",
        f"- Reason: {payload.get('reason')}",
        f"- Run ID: {payload.get('run_id')}",
        f"- Source observation: {source.get('run_id')} / {source.get('status')} / {source.get('result')}",
        f"- Samples: {source.get('successful_sample_count', 0)} ok / {source.get('sample_count', 0)} total",
        f"- Raw POST delta: {transport.get('raw_post_success_delta', 0)} ok / {transport.get('raw_post_failure_delta', 0)} fail",
        f"- Location summary: coordinates seen {location.get('coordinate_sample_count', 0)} / GNSS fix {location.get('gnss_fix_seen', False)} / map modes {', '.join(location.get('map_modes') or []) or 'none'}",
        f"- Ready for labeling review: {readiness.get('ready_for_labeling_review', False)}",
        f"- Ready for training handoff: {readiness.get('ready_for_training_handoff', False)}",
        f"- Training allowed: {readiness.get('training_allowed', False)}",
        "",
        "## Blockers",
        "",
    ]
    blockers = list(readiness.get("blockers") or [])
    lines.extend([f"- {item}" for item in blockers] or ["- none"])
    lines.extend(
        [
            "",
            "## Quality Gaps",
            "",
        ]
    )
    gaps = list(readiness.get("quality_gaps") or [])
    lines.extend([f"- {item}" for item in gaps] or ["- none"])
    lines.extend(
        [
            "",
            "## Boundaries",
            "",
            "- This report reads D1 field-observation summaries only.",
            "- It does not read sample JSONL contents, contact hardware, send commands, or change firmware.",
            "- It does not include exact coordinate values, train a model, produce model artifacts, or make location accuracy, battery-life, or release claims.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_report(payload: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "d1_training_readiness.json"
    markdown_path = output_dir / "d1_training_readiness.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_markdown(payload, markdown_path)
    payload["paths"] = {
        "d1_training_readiness_json": relative_path(json_path),
        "d1_training_readiness_markdown": relative_path(markdown_path),
    }
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def build_from_args(args: argparse.Namespace) -> dict[str, Any]:
    generated_at = args.generated_at or utc_now()
    report_path, status_path = resolve_observation_paths(args)
    source, source_path, source_payload = choose_source(report_path, status_path)
    observation = observation_summary(source, source_payload, source_path=source_path)
    run_id = args.run_id or default_run_id(str(observation.get("run_id") or ""), generated_at)
    output_dir = args.output_dir or (args.output_root / run_id)
    payload = build_readiness(observation, generated_at=generated_at, run_id=run_id, output_dir=output_dir)
    return write_report(payload, output_dir)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Assess D1 field-observation readiness for DATA/D5 review.")
    parser.add_argument("--field-observation-report", type=Path)
    parser.add_argument("--field-observation-status", type=Path)
    parser.add_argument("--field-observation-root", type=Path, default=DEFAULT_FIELD_OBSERVATION_ROOT)
    parser.add_argument("--run-id")
    parser.add_argument("--generated-at")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        payload = build_from_args(args)
    except D1TrainingReadinessError as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True))
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"{payload['status']} D1 training readiness: {as_dict(payload.get('paths')).get('d1_training_readiness_markdown')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

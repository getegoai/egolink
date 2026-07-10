"""Build a bounded D1 labeling/privacy review intake summary.

This DATA-024 helper turns a DATA-022 D1 training-readiness report into a
human-review intake item. It does not read sample JSONL contents, write the
candidate SQLite store, train/evaluate a model, or expose exact coordinates.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_READINESS_ROOT = REPO_ROOT / "reports" / "d1_training_readiness"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "reports" / "d1_labeling_intake"
SCHEMA_VERSION = "egolink.d1_labeling_intake.v0.1"
BUILDER_VERSION = "data-024.0"


class D1LabelingIntakeError(RuntimeError):
    """Raised when a D1 labeling intake report cannot be built safely."""


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


def stable_id(*parts: Any) -> str:
    text = "|".join(str(part or "") for part in parts)
    return "d1-intake-" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise D1LabelingIntakeError(f"readiness report not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise D1LabelingIntakeError(f"readiness report is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise D1LabelingIntakeError(f"readiness report must be a JSON object: {path}")
    return payload


def latest_path(root: Path, pattern: str) -> Path | None:
    if not root.is_dir():
        return None
    candidates = [item for item in root.glob(pattern) if item.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda item: item.stat().st_mtime)


def relative_path(path: Path | None) -> str | None:
    if path is None:
        return None
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO_ROOT.resolve()).as_posix()
    except (OSError, ValueError):
        return path.name


def default_run_id(readiness_run_id: str | None, generated_at: str) -> str:
    if readiness_run_id:
        return f"{readiness_run_id}-labeling-intake"
    slug = timestamp_slug(generated_at)[:16].rstrip("-")
    return f"d1-labeling-intake-{slug}"


def resolve_readiness_report(args: argparse.Namespace) -> Path:
    if args.training_readiness_report is not None:
        return args.training_readiness_report
    path = latest_path(args.training_readiness_root, "**/d1_training_readiness.json")
    if path is None:
        raise D1LabelingIntakeError("no d1_training_readiness.json report found")
    return path


def compact_source_observation(report: Mapping[str, Any]) -> dict[str, Any]:
    source = as_dict(report.get("source_observation"))
    return {
        "run_id": source.get("run_id"),
        "source": source.get("source"),
        "status": source.get("status"),
        "result": source.get("result"),
        "device_id": source.get("device_id"),
        "sample_count": int_or_zero(source.get("sample_count")),
        "successful_sample_count": int_or_zero(source.get("successful_sample_count")),
        "fetch_error_count": int_or_zero(source.get("fetch_error_count")),
        "latest_seq": source.get("latest_seq"),
        "max_freshness_s": number_or_none(source.get("max_freshness_s")),
        "last_location_upload_at": source.get("last_location_upload_at"),
        "samples_jsonl_read": bool(source.get("samples_jsonl_read", False)),
        "coordinate_values_copied": False,
    }


def compact_evidence_coverage(report: Mapping[str, Any]) -> dict[str, Any]:
    coverage = as_dict(report.get("evidence_coverage"))
    capture = as_dict(coverage.get("capture"))
    transport = as_dict(coverage.get("transport"))
    location = as_dict(coverage.get("location"))
    sensors = as_dict(coverage.get("sensors"))
    return {
        "capture": {
            "sample_count": int_or_zero(capture.get("sample_count")),
            "successful_sample_count": int_or_zero(capture.get("successful_sample_count")),
            "fetch_error_count": int_or_zero(capture.get("fetch_error_count")),
            "ready_for_review": bool(capture.get("ready_for_review", False)),
        },
        "transport": {
            "raw_post_success_delta": int_or_zero(transport.get("raw_post_success_delta")),
            "raw_post_failure_delta": int_or_zero(transport.get("raw_post_failure_delta")),
            "lte_registration_seen": bool(transport.get("lte_registration_seen", False)),
            "pdp_active_seen": bool(transport.get("pdp_active_seen", False)),
        },
        "location": {
            "coordinate_sample_count": int_or_zero(location.get("coordinate_sample_count")),
            "location_event_count_delta": int_or_zero(location.get("location_event_count_delta")),
            "map_modes": unique_text(as_list(location.get("map_modes"))),
            "gnss_states": unique_text(as_list(location.get("gnss_states"))),
            "gnss_fix_seen": bool(location.get("gnss_fix_seen", False)),
            "coordinate_values_copied": False,
            "accuracy_claimed": False,
        },
        "sensors": {
            "imu_evidence_statuses": unique_text(as_list(sensors.get("imu_evidence_statuses"))),
            "power_evidence_statuses": unique_text(as_list(sensors.get("power_evidence_statuses"))),
            "power_measured_seen": bool(sensors.get("power_measured_seen", False)),
            "real_imu_seen": bool(sensors.get("real_imu_seen", False)),
        },
    }


def readiness_blockers(report: Mapping[str, Any]) -> list[str]:
    readiness = as_dict(report.get("readiness"))
    return unique_text(as_list(readiness.get("blockers")))


def build_review_item(
    report: Mapping[str, Any],
    *,
    intake_id: str,
) -> dict[str, Any]:
    source = compact_source_observation(report)
    readiness = as_dict(report.get("readiness"))
    coverage = compact_evidence_coverage(report)
    sensors = as_dict(coverage.get("sensors"))
    location = as_dict(coverage.get("location"))
    return {
        "intake_id": intake_id,
        "source_run_id": source.get("run_id"),
        "readiness_run_id": report.get("run_id"),
        "device_id": source.get("device_id"),
        "status": "pending_label_privacy_split",
        "review_state": {
            "operator_label": "missing",
            "privacy_review": readiness.get("privacy_review") or "required",
            "training_consent": readiness.get("consent_status") or "not_reviewed",
            "split_plan": "missing",
            "quality_gaps": unique_text(as_list(readiness.get("quality_gaps"))),
        },
        "evidence_summary": {
            "samples": source.get("successful_sample_count", 0),
            "latest_seq": source.get("latest_seq"),
            "raw_post_success_delta": as_dict(coverage.get("transport")).get("raw_post_success_delta", 0),
            "raw_post_failure_delta": as_dict(coverage.get("transport")).get("raw_post_failure_delta", 0),
            "coordinate_sample_count": location.get("coordinate_sample_count", 0),
            "gnss_fix_seen": location.get("gnss_fix_seen", False),
            "imu_evidence_statuses": sensors.get("imu_evidence_statuses") or [],
            "power_evidence_statuses": sensors.get("power_evidence_statuses") or [],
        },
        "requested_actions": [
            "attach_operator_or_user_label",
            "complete_privacy_review",
            "record_training_consent_decision",
            "assign_session_split_and_check_leakage",
        ],
        "available_decisions": ["needs_more_capture", "reject_for_training", "ready_for_candidate_store"],
        "training_allowed": False,
        "candidate_record_written": False,
    }


def build_intake(
    report: Mapping[str, Any],
    *,
    generated_at: str,
    run_id: str,
    source_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    readiness = as_dict(report.get("readiness"))
    source = compact_source_observation(report)
    coverage = compact_evidence_coverage(report)
    is_ready = bool(readiness.get("ready_for_labeling_review")) and report.get("status") == "ready_for_labeling_review"
    intake_id = stable_id(report.get("run_id"), source.get("run_id"), generated_at)
    items = [build_review_item(report, intake_id=intake_id)] if is_ready else []
    status = "pending_human_review" if is_ready else "not_ready_for_labeling_intake"
    reason = (
        "d1_run_waiting_for_label_privacy_consent_and_split_review"
        if is_ready
        else "training_readiness_not_ready_for_labeling_intake"
    )
    report_path = output_dir / "d1_labeling_intake.json"
    markdown_path = output_dir / "d1_labeling_intake.md"
    return {
        "tool": "build_d1_labeling_intake",
        "schema_version": SCHEMA_VERSION,
        "builder_version": BUILDER_VERSION,
        "run_id": run_id,
        "generated_at": generated_at,
        "serves_demo": "D5",
        "status": status,
        "reason": reason,
        "source_readiness": {
            "run_id": report.get("run_id"),
            "status": report.get("status"),
            "reason": report.get("reason"),
            "report_path": relative_path(source_path),
        },
        "source_observation": source,
        "evidence_coverage": coverage,
        "intake_queue": {
            "available": is_ready,
            "pending_items": len(items),
            "items": items,
            "next_queue": "training_candidate_store_after_review",
        },
        "labeling_request": {
            "taxonomy_version": "d1_location_review.v0.1",
            "requested_label_groups": [
                "collection_context",
                "location_quality",
                "motion_context",
                "operator_outcome",
            ],
            "free_text_policy": "redacted_or_absent",
            "exact_coordinates_visible": False,
            "raw_sensor_payload_visible": False,
        },
        "review_gates": {
            "training_readiness": "pass" if is_ready else "blocked",
            "operator_label": "blocked",
            "privacy_review": "blocked",
            "training_consent": "blocked",
            "split_leakage": "blocked",
            "candidate_store": "not_written",
            "model_training": "not_run",
            "model_artifact": "not_produced",
            "release_claim": "not_allowed",
        },
        "blockers": unique_text(
            readiness_blockers(report)
            + [
                "operator_label_missing",
                "privacy_review_required",
                "training_consent_not_recorded",
                "split_plan_missing",
            ]
        ),
        "scope": {
            "training_readiness_report_read": True,
            "sample_jsonl_read": False,
            "message_hub_contacted": False,
            "hardware_contacted": False,
            "commands_sent": False,
            "firmware_changed": False,
            "candidate_db_written": False,
            "training_samples_written": False,
            "model_training_started": False,
            "model_artifact_written": False,
            "exact_coordinates_copied": False,
            "raw_sensor_payload_copied": False,
            "release_claim_allowed": False,
        },
        "paths": {
            "d1_labeling_intake_json": relative_path(report_path),
            "d1_labeling_intake_markdown": relative_path(markdown_path),
        },
        "next_step": (
            "Use this intake item to collect labels, privacy review, training consent, and split review; "
            "then write reviewed records through the candidate-store path."
            if is_ready
            else "Rerun D1 field observation and training-readiness assessment before labeling intake."
        ),
        "non_claims": [
            "This intake report is a human-review queue summary only.",
            "It does not contain raw sample JSONL, raw payload bytes, exact coordinates, candidate DBs, feature rows, targets, or model artifacts.",
            "It does not train or evaluate a model, deploy on-device inference, measure model footprint or power, or permit release claims.",
        ],
    }


def render_markdown(payload: Mapping[str, Any]) -> str:
    queue = as_dict(payload.get("intake_queue"))
    readiness = as_dict(payload.get("source_readiness"))
    source = as_dict(payload.get("source_observation"))
    coverage = as_dict(payload.get("evidence_coverage"))
    transport = as_dict(coverage.get("transport"))
    location = as_dict(coverage.get("location"))
    gates = as_dict(payload.get("review_gates"))
    lines = [
        "# D1 Labeling Intake",
        "",
        f"- Status: {payload.get('status')}",
        f"- Reason: {payload.get('reason')}",
        f"- Run ID: {payload.get('run_id')}",
        f"- Source readiness: {readiness.get('run_id')} / {readiness.get('status')}",
        f"- Source observation: {source.get('run_id')} / {source.get('status')} / {source.get('result')}",
        f"- Samples: {source.get('successful_sample_count', 0)} ok / {source.get('sample_count', 0)} total",
        f"- Raw POST delta: {transport.get('raw_post_success_delta', 0)} ok / {transport.get('raw_post_failure_delta', 0)} fail",
        f"- Location summary: coordinate samples {location.get('coordinate_sample_count', 0)} / GNSS fix {location.get('gnss_fix_seen', False)}",
        f"- Pending intake items: {queue.get('pending_items', 0)}",
        "",
        "## Review Gates",
        "",
    ]
    for name, status in gates.items():
        lines.append(f"- {name}: {status}")
    lines += [
        "",
        "## Intake Items",
        "",
    ]
    for item in queue.get("items", []) or []:
        state = as_dict(item.get("review_state"))
        lines.append(
            f"- {item.get('intake_id', 'unknown')}: label {state.get('operator_label', 'unknown')} / "
            f"privacy {state.get('privacy_review', 'unknown')} / consent {state.get('training_consent', 'unknown')} / "
            f"split {state.get('split_plan', 'unknown')}"
        )
    if not queue.get("items"):
        lines.append("- none")
    lines += [
        "",
        "## Boundaries",
        "",
        "- This report reads a D1 training-readiness summary only.",
        "- It does not read sample JSONL contents, contact hardware, send commands, or change firmware.",
        "- It does not include exact coordinates, raw payloads, feature rows, targets, candidate DBs, or model artifacts.",
        "- It does not train/evaluate a model, deploy on-device inference, or make release claims.",
        "",
    ]
    return "\n".join(lines)


def write_report(payload: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "d1_labeling_intake.json"
    markdown_path = output_dir / "d1_labeling_intake.md"
    payload["paths"] = {
        "d1_labeling_intake_json": relative_path(json_path),
        "d1_labeling_intake_markdown": relative_path(markdown_path),
    }
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(payload), encoding="utf-8")
    return payload


def build_from_args(args: argparse.Namespace) -> dict[str, Any]:
    generated_at = args.generated_at or utc_now()
    source_path = resolve_readiness_report(args)
    readiness_report = load_json(source_path)
    run_id = args.run_id or default_run_id(str(readiness_report.get("run_id") or ""), generated_at)
    output_dir = args.output_dir or (args.output_root / run_id)
    payload = build_intake(
        readiness_report,
        generated_at=generated_at,
        run_id=run_id,
        source_path=source_path,
        output_dir=output_dir,
    )
    return write_report(payload, output_dir)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a bounded D1 labeling/privacy review intake report.")
    parser.add_argument("--training-readiness-report", type=Path)
    parser.add_argument("--training-readiness-root", type=Path, default=DEFAULT_READINESS_ROOT)
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
    except D1LabelingIntakeError as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True))
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"{payload['status']} D1 labeling intake: {as_dict(payload.get('paths')).get('d1_labeling_intake_markdown')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

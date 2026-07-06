"""Build a bounded human-review packet from a D1 labeling queue.

The packet is a review worklist, not a reviewed dataset. It copies only compact
queue metadata and decision slots. It does not read sample JSONL contents,
write candidate DBs, train/evaluate a model, or expose exact coordinates.
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
DEFAULT_QUEUE_ROOT = REPO_ROOT / "reports" / "d1_labeling_queue"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "reports" / "d1_labeling_reviews"
SCHEMA_VERSION = "egolink.d1_labeling_review_packet.v0.1"
BUILDER_VERSION = "data-028.0"
SUMMARY_JSON = "d1_labeling_review_packet.json"
SUMMARY_MARKDOWN = "d1_labeling_review_packet.md"

OPERATOR_LABEL_VALUES = ["safe", "needs_help", "no_response", "uncertain", "not_training_relevant"]
PRIVACY_REVIEW_VALUES = ["approved_bounded_summary_only", "reject_private_data_risk", "needs_redaction_review"]
TRAINING_CONSENT_VALUES = ["approved_for_training", "not_approved_for_training", "defer"]
SPLIT_PLAN_VALUES = ["train", "validation", "test", "holdout", "exclude"]
CANDIDATE_DECISION_VALUES = ["ready_for_candidate_store", "needs_more_capture", "reject_for_training"]


class D1LabelingReviewPacketError(RuntimeError):
    """Raised when a D1 labeling review packet cannot be built safely."""


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


def int_or_zero(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return 0


def bool_value(value: Any) -> bool:
    return bool(value) if isinstance(value, bool) else False


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise D1LabelingReviewPacketError(f"D1 labeling queue report not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise D1LabelingReviewPacketError(f"D1 labeling queue report is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise D1LabelingReviewPacketError(f"D1 labeling queue report must be a JSON object: {path}")
    return payload


def relative_path(path: Path | None, *, root: Path | None = None) -> str | None:
    if path is None:
        return None
    resolved = path.resolve()
    for base in (REPO_ROOT.resolve(), root.resolve() if root else None):
        if base is None:
            continue
        try:
            return resolved.relative_to(base).as_posix()
        except (OSError, ValueError):
            continue
    return path.name


def default_run_id(generated_at: str) -> str:
    return f"d1-labeling-review-{timestamp_slug(generated_at)[:16].rstrip('-')}"


def find_queue_reports(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    reports = [path for path in root.glob("**/d1_labeling_queue.json") if path.is_file()]
    return sorted(reports, key=lambda path: path.stat().st_mtime, reverse=True)


def latest_queue_report(root: Path) -> Path | None:
    reports = find_queue_reports(root)
    return reports[0] if reports else None


def decision_slot(*, current: Any, allowed_values: list[str], required: bool = True) -> dict[str, Any]:
    return {
        "required": required,
        "current": current,
        "allowed_values": allowed_values,
        "selected": None,
        "reviewed_by": None,
        "reviewed_at": None,
    }


def packet_item_id(item: Mapping[str, Any]) -> str:
    basis = "|".join(
        str(item.get(key) or "")
        for key in ("intake_id", "source_run_id", "readiness_run_id", "device_id", "status")
    )
    return "d1-review-" + hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


def compact_review_item(item: Mapping[str, Any]) -> dict[str, Any]:
    review_state = as_dict(item.get("review_state"))
    evidence = as_dict(item.get("evidence_summary"))
    return {
        "packet_item_id": packet_item_id(item),
        "intake_id": item.get("intake_id"),
        "intake_run_id": item.get("intake_run_id"),
        "source_run_id": item.get("source_run_id"),
        "readiness_run_id": item.get("readiness_run_id"),
        "device_id": item.get("device_id"),
        "queue_status": item.get("status"),
        "current_review_state": {
            "operator_label": review_state.get("operator_label") or "missing",
            "privacy_review": review_state.get("privacy_review") or "required",
            "training_consent": review_state.get("training_consent") or "not_reviewed",
            "split_plan": review_state.get("split_plan") or "missing",
            "quality_gaps": unique_text(as_list(review_state.get("quality_gaps"))),
        },
        "evidence_summary": {
            "samples": int_or_zero(evidence.get("samples")),
            "latest_seq": evidence.get("latest_seq"),
            "raw_post_success_delta": int_or_zero(evidence.get("raw_post_success_delta")),
            "raw_post_failure_delta": int_or_zero(evidence.get("raw_post_failure_delta")),
            "coordinate_sample_count": int_or_zero(evidence.get("coordinate_sample_count")),
            "gnss_fix_seen": bool_value(evidence.get("gnss_fix_seen")),
            "imu_evidence_statuses": unique_text(as_list(evidence.get("imu_evidence_statuses"))),
            "power_evidence_statuses": unique_text(as_list(evidence.get("power_evidence_statuses"))),
        },
        "requested_actions": unique_text(as_list(item.get("requested_actions"))),
        "available_decisions": unique_text(as_list(item.get("available_decisions"))),
        "decision_slots": {
            "operator_label": decision_slot(
                current=review_state.get("operator_label") or "missing",
                allowed_values=OPERATOR_LABEL_VALUES,
            ),
            "privacy_review": decision_slot(
                current=review_state.get("privacy_review") or "required",
                allowed_values=PRIVACY_REVIEW_VALUES,
            ),
            "training_consent": decision_slot(
                current=review_state.get("training_consent") or "not_reviewed",
                allowed_values=TRAINING_CONSENT_VALUES,
            ),
            "split_plan": decision_slot(
                current=review_state.get("split_plan") or "missing",
                allowed_values=SPLIT_PLAN_VALUES,
            ),
            "candidate_decision": decision_slot(
                current="not_reviewed",
                allowed_values=CANDIDATE_DECISION_VALUES,
            ),
        },
        "candidate_record_written": False,
        "training_allowed": False,
        "candidate_write_gate": "blocked_until_review_packet_is_applied",
    }


def review_status(items: list[dict[str, Any]], source_status: str) -> str:
    if items:
        return "needs_human_review"
    if source_status in {"no_intake_reports", "empty_or_not_ready"}:
        return "no_review_items"
    return "no_review_items"


def build_review_packet(
    *,
    queue_report: Path | None,
    queue_root: Path,
    generated_at: str,
    run_id: str,
    limit: int | None = None,
) -> dict[str, Any]:
    if limit is not None and limit <= 0:
        raise D1LabelingReviewPacketError("--limit must be positive")
    if queue_report is None:
        queue_report = latest_queue_report(queue_root)
    if queue_report is None:
        return {
            "tool": "build_d1_labeling_review_packet",
            "schema_version": SCHEMA_VERSION,
            "builder_version": BUILDER_VERSION,
            "run_id": run_id,
            "generated_at": generated_at,
            "serves_demo": "D5",
            "status": "no_labeling_queue",
            "reason": "d1_labeling_queue_missing",
            "source_queue": {"available": False},
            "summary": {
                "queue_pending_items": 0,
                "review_packet_items": 0,
                "needs_operator_label": 0,
                "needs_privacy_review": 0,
                "needs_training_consent": 0,
                "needs_split_plan": 0,
                "candidate_record_written_count": 0,
                "training_allowed_count": 0,
            },
            "review_packet": {"items": [], "decision_schema": decision_schema()},
            "scope": safe_scope(False),
            "next_step": "Generate a D1 labeling queue before opening a review packet.",
            "non_claims": non_claims(),
        }

    payload = load_json(queue_report)
    queue = as_dict(payload.get("queue"))
    raw_items = [as_dict(item) for item in as_list(queue.get("items"))]
    if limit is not None:
        raw_items = raw_items[:limit]
    items = [compact_review_item(item) for item in raw_items if item]
    needs_operator_label = len(
        [item for item in items if as_dict(item.get("current_review_state")).get("operator_label") == "missing"]
    )
    needs_privacy_review = len(
        [item for item in items if as_dict(item.get("current_review_state")).get("privacy_review") == "required"]
    )
    needs_training_consent = len(
        [
            item
            for item in items
            if as_dict(item.get("current_review_state")).get("training_consent") == "not_reviewed"
        ]
    )
    needs_split_plan = len(
        [item for item in items if as_dict(item.get("current_review_state")).get("split_plan") == "missing"]
    )
    summary = as_dict(payload.get("summary"))
    source_status = str(payload.get("status") or "unknown")
    return {
        "tool": "build_d1_labeling_review_packet",
        "schema_version": SCHEMA_VERSION,
        "builder_version": BUILDER_VERSION,
        "run_id": run_id,
        "generated_at": generated_at,
        "serves_demo": "D5",
        "status": review_status(items, source_status),
        "source_queue": {
            "available": True,
            "run_id": payload.get("run_id"),
            "status": source_status,
            "report_path": relative_path(queue_report, root=queue_root),
            "pending_item_count": summary.get("pending_item_count", summary.get("pending_items", 0)),
            "intake_report_count": summary.get("intake_report_count", 0),
        },
        "summary": {
            "queue_pending_items": summary.get("pending_item_count", summary.get("pending_items", 0)),
            "review_packet_items": len(items),
            "needs_operator_label": needs_operator_label,
            "needs_privacy_review": needs_privacy_review,
            "needs_training_consent": needs_training_consent,
            "needs_split_plan": needs_split_plan,
            "candidate_record_written_count": 0,
            "training_allowed_count": 0,
        },
        "review_packet": {
            "status": "open" if items else "empty",
            "items": items,
            "decision_schema": decision_schema(),
            "apply_policy": "review_packet_must_be_applied_by_a_future_explicit_candidate_store_task",
        },
        "scope": safe_scope(True),
        "next_step": "Fill review decisions for each packet item, then run a future explicit candidate-store promotion task.",
        "non_claims": non_claims(),
    }


def decision_schema() -> dict[str, Any]:
    return {
        "operator_label": OPERATOR_LABEL_VALUES,
        "privacy_review": PRIVACY_REVIEW_VALUES,
        "training_consent": TRAINING_CONSENT_VALUES,
        "split_plan": SPLIT_PLAN_VALUES,
        "candidate_decision": CANDIDATE_DECISION_VALUES,
    }


def safe_scope(queue_summary_read: bool) -> dict[str, Any]:
    return {
        "labeling_queue_summary_read": queue_summary_read,
        "sample_jsonl_read": False,
        "payload_bytes_copied": False,
        "exact_coordinates_copied": False,
        "feature_rows_copied": False,
        "target_labels_written": False,
        "candidate_db_written": False,
        "training_samples_written": False,
        "model_training_started": False,
        "model_artifact_written": False,
        "release_claim_allowed": False,
    }


def non_claims() -> list[str]:
    return [
        "This review packet is a human-review worklist only.",
        "It does not read sample JSONL, raw payloads, exact coordinates, feature rows, targets, candidate DBs, or model artifacts.",
        "It does not mark items reviewed, write candidate records, train/evaluate a model, deploy inference, measure model footprint or power, or permit release claims.",
    ]


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = as_dict(payload.get("summary"))
    items = [as_dict(item) for item in as_list(as_dict(payload.get("review_packet")).get("items"))]
    lines = [
        "# D1 Labeling Review Packet",
        "",
        f"- Status: {payload.get('status')}",
        f"- Run ID: {payload.get('run_id')}",
        f"- Generated: {payload.get('generated_at')}",
        f"- Review items: {summary.get('review_packet_items', 0)}",
        f"- Queue pending items: {summary.get('queue_pending_items', 0)}",
        "",
        "## Review Items",
        "",
        "| Packet Item | Source Run | Intake | Samples | GNSS Fix | Operator Label | Privacy | Consent | Split | Candidate Decision |",
        "|---|---|---|---:|---|---|---|---|---|---|",
    ]
    if items:
        for item in items:
            evidence = as_dict(item.get("evidence_summary"))
            current = as_dict(item.get("current_review_state"))
            lines.append(
                "| {packet} | {source} | {intake} | {samples} | {gnss} | {label} | {privacy} | {consent} | {split} | not_reviewed |".format(
                    packet=item.get("packet_item_id") or "",
                    source=item.get("source_run_id") or "",
                    intake=item.get("intake_id") or "",
                    samples=evidence.get("samples", 0),
                    gnss=evidence.get("gnss_fix_seen", False),
                    label=current.get("operator_label") or "",
                    privacy=current.get("privacy_review") or "",
                    consent=current.get("training_consent") or "",
                    split=current.get("split_plan") or "",
                )
            )
    else:
        lines.append("| none |  |  | 0 |  |  |  |  |  |  |")

    lines += [
        "",
        "## Decision Values",
        "",
        f"- Operator label: {', '.join(OPERATOR_LABEL_VALUES)}",
        f"- Privacy review: {', '.join(PRIVACY_REVIEW_VALUES)}",
        f"- Training consent: {', '.join(TRAINING_CONSENT_VALUES)}",
        f"- Split plan: {', '.join(SPLIT_PLAN_VALUES)}",
        f"- Candidate decision: {', '.join(CANDIDATE_DECISION_VALUES)}",
        "",
        "## Next Step",
        "",
        f"- {payload.get('next_step')}",
        "",
        "## Boundaries",
        "",
    ]
    lines.extend(f"- {item}" for item in non_claims())
    lines.append("")
    return "\n".join(lines)


def write_report(payload: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / SUMMARY_JSON
    markdown_path = output_dir / SUMMARY_MARKDOWN
    payload["paths"] = {
        "d1_labeling_review_packet_json": relative_path(json_path),
        "d1_labeling_review_packet_markdown": relative_path(markdown_path),
    }
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(payload), encoding="utf-8")
    return payload


def build_from_args(args: argparse.Namespace) -> dict[str, Any]:
    generated_at = args.generated_at or utc_now()
    run_id = args.run_id or default_run_id(generated_at)
    output_dir = args.output_dir or (args.output_root / run_id)
    payload = build_review_packet(
        queue_report=args.labeling_queue_report,
        queue_root=args.labeling_queue_root,
        generated_at=generated_at,
        run_id=run_id,
        limit=args.limit,
    )
    return write_report(payload, output_dir)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a bounded D1 labeling review packet.")
    parser.add_argument("--labeling-queue-report", type=Path)
    parser.add_argument("--labeling-queue-root", type=Path, default=DEFAULT_QUEUE_ROOT)
    parser.add_argument("--run-id")
    parser.add_argument("--generated-at")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        payload = build_from_args(args)
    except D1LabelingReviewPacketError as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True))
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(
            f"{payload['status']} D1 labeling review packet: "
            f"{as_dict(payload.get('paths')).get('d1_labeling_review_packet_markdown')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

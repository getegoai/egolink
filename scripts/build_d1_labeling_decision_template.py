"""Build a fillable D1 labeling decision template from a review packet.

The template is an operator work aid. It copies compact review-packet metadata
and empty decision fields only. It does not mark items reviewed, write
candidate DBs, train/evaluate a model, or expose exact coordinates.
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
DEFAULT_REVIEW_ROOT = REPO_ROOT / "reports" / "d1_labeling_reviews"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "reports" / "d1_labeling_decisions"
SCHEMA_VERSION = "egolink.d1_labeling_decision_template.v0.1"
BUILDER_VERSION = "data-030.0"
SUMMARY_JSON = "d1_labeling_decision_template.json"
SUMMARY_MARKDOWN = "d1_labeling_decision_template.md"


class D1LabelingDecisionTemplateError(RuntimeError):
    """Raised when a D1 labeling decision template cannot be built safely."""


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
        raise D1LabelingDecisionTemplateError(f"D1 labeling review packet not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise D1LabelingDecisionTemplateError(f"D1 labeling review packet is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise D1LabelingDecisionTemplateError(f"D1 labeling review packet must be a JSON object: {path}")
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
    return f"d1-labeling-decisions-{timestamp_slug(generated_at)[:16].rstrip('-')}"


def find_review_packets(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    reports = [path for path in root.glob("**/d1_labeling_review_packet.json") if path.is_file()]
    return sorted(reports, key=lambda path: path.stat().st_mtime, reverse=True)


def latest_review_packet(root: Path) -> Path | None:
    reports = find_review_packets(root)
    return reports[0] if reports else None


def decision_template_slot(slot: Mapping[str, Any], fallback_values: list[str] | None = None) -> dict[str, Any]:
    return {
        "required": bool_value(slot.get("required")) if "required" in slot else True,
        "current": slot.get("current"),
        "allowed_values": unique_text(as_list(slot.get("allowed_values")) or list(fallback_values or [])),
        "selected": None,
        "operator_note": None,
    }


def compact_template_item(item: Mapping[str, Any], decision_schema: Mapping[str, Any]) -> dict[str, Any]:
    review_state = as_dict(item.get("current_review_state"))
    evidence = as_dict(item.get("evidence_summary"))
    source_slots = as_dict(item.get("decision_slots"))
    fields: dict[str, Any] = {}
    for field_name in ("operator_label", "privacy_review", "training_consent", "split_plan", "candidate_decision"):
        fields[field_name] = decision_template_slot(
            as_dict(source_slots.get(field_name)),
            fallback_values=as_list(decision_schema.get(field_name)),
        )
    return {
        "packet_item_id": item.get("packet_item_id"),
        "intake_id": item.get("intake_id"),
        "source_run_id": item.get("source_run_id"),
        "readiness_run_id": item.get("readiness_run_id"),
        "device_id": item.get("device_id"),
        "queue_status": item.get("queue_status"),
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
        "decision_fields": fields,
        "requested_actions": unique_text(as_list(item.get("requested_actions"))),
        "available_decisions": unique_text(as_list(item.get("available_decisions"))),
        "validation_state": "not_submitted",
        "candidate_record_written": False,
        "training_allowed": False,
    }


def build_template(
    *,
    review_packet_report: Path | None,
    review_packet_root: Path,
    generated_at: str,
    run_id: str,
    limit: int | None = None,
) -> dict[str, Any]:
    if limit is not None and limit <= 0:
        raise D1LabelingDecisionTemplateError("--limit must be positive")
    if review_packet_report is None:
        review_packet_report = latest_review_packet(review_packet_root)
    if review_packet_report is None:
        return {
            "tool": "build_d1_labeling_decision_template",
            "schema_version": SCHEMA_VERSION,
            "builder_version": BUILDER_VERSION,
            "run_id": run_id,
            "generated_at": generated_at,
            "serves_demo": "D5",
            "status": "no_labeling_review_packet",
            "reason": "d1_labeling_review_packet_missing",
            "source_review_packet": {"available": False},
            "summary": empty_summary(),
            "decision_template": {"items": [], "decision_schema": {}},
            "scope": safe_scope(False),
            "next_step": "Generate a D1 labeling review packet before opening a decision template.",
            "non_claims": non_claims(),
        }

    payload = load_json(review_packet_report)
    review_packet = as_dict(payload.get("review_packet"))
    decision_schema = as_dict(review_packet.get("decision_schema"))
    raw_items = [as_dict(item) for item in as_list(review_packet.get("items"))]
    if limit is not None:
        raw_items = raw_items[:limit]
    items = [compact_template_item(item, decision_schema) for item in raw_items if item]
    summary = template_summary(items, as_dict(payload.get("summary")))
    return {
        "tool": "build_d1_labeling_decision_template",
        "schema_version": SCHEMA_VERSION,
        "builder_version": BUILDER_VERSION,
        "run_id": run_id,
        "generated_at": generated_at,
        "serves_demo": "D5",
        "status": "ready_for_human_input" if items else "no_decision_items",
        "source_review_packet": {
            "available": True,
            "run_id": payload.get("run_id"),
            "status": payload.get("status"),
            "report_path": relative_path(review_packet_report, root=review_packet_root),
            "review_packet_items": summary.get("template_items", 0),
        },
        "summary": summary,
        "decision_template": {
            "status": "open" if items else "empty",
            "items": items,
            "decision_schema": decision_schema,
            "apply_policy": "template_must_be_validated_by_a_future_explicit_review_application_task",
        },
        "scope": safe_scope(True),
        "next_step": "Fill selected values in the decision template, then validate it before candidate-store promotion.",
        "non_claims": non_claims(),
    }


def empty_summary() -> dict[str, Any]:
    return {
        "template_items": 0,
        "required_decision_fields": 0,
        "selected_decision_fields": 0,
        "items_ready_for_validation": 0,
        "candidate_record_written_count": 0,
        "training_allowed_count": 0,
        "ready_for_candidate_promotion": False,
    }


def template_summary(items: list[dict[str, Any]], review_summary: Mapping[str, Any]) -> dict[str, Any]:
    required = 0
    selected = 0
    for item in items:
        for slot in as_dict(item.get("decision_fields")).values():
            slot_dict = as_dict(slot)
            if slot_dict.get("required", True):
                required += 1
            if slot_dict.get("selected") not in (None, ""):
                selected += 1
    summary = empty_summary()
    summary.update(
        {
            "template_items": len(items),
            "review_packet_items": review_summary.get("review_packet_items", len(items)),
            "queue_pending_items": review_summary.get("queue_pending_items", 0),
            "required_decision_fields": required,
            "selected_decision_fields": selected,
            "items_ready_for_validation": 0,
        }
    )
    return summary


def safe_scope(review_packet_summary_read: bool) -> dict[str, Any]:
    return {
        "review_packet_summary_read": review_packet_summary_read,
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
        "This decision template is a fillable work aid only.",
        "It does not read sample JSONL, raw payloads, exact coordinates, feature rows, targets, candidate DBs, or model artifacts.",
        "It does not mark items reviewed, apply decisions, write candidate records, train/evaluate a model, deploy inference, measure model footprint or power, or permit release claims.",
    ]


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = as_dict(payload.get("summary"))
    template = as_dict(payload.get("decision_template"))
    items = [as_dict(item) for item in as_list(template.get("items"))]
    lines = [
        "# D1 Labeling Decision Template",
        "",
        f"- Status: {payload.get('status')}",
        f"- Run ID: {payload.get('run_id')}",
        f"- Generated: {payload.get('generated_at')}",
        f"- Template items: {summary.get('template_items', 0)}",
        f"- Required fields: {summary.get('required_decision_fields', 0)}",
        f"- Selected fields: {summary.get('selected_decision_fields', 0)}",
        "",
        "## Fillable Items",
        "",
        "| Packet Item | Source Run | Intake | Samples | Operator Label | Privacy | Consent | Split | Candidate Decision |",
        "|---|---|---|---:|---|---|---|---|---|",
    ]
    if items:
        for item in items:
            evidence = as_dict(item.get("evidence_summary"))
            fields = as_dict(item.get("decision_fields"))
            lines.append(
                "| {packet} | {source} | {intake} | {samples} | {label} | {privacy} | {consent} | {split} | {candidate} |".format(
                    packet=item.get("packet_item_id") or "",
                    source=item.get("source_run_id") or "",
                    intake=item.get("intake_id") or "",
                    samples=evidence.get("samples", 0),
                    label=as_dict(fields.get("operator_label")).get("selected") or "TODO",
                    privacy=as_dict(fields.get("privacy_review")).get("selected") or "TODO",
                    consent=as_dict(fields.get("training_consent")).get("selected") or "TODO",
                    split=as_dict(fields.get("split_plan")).get("selected") or "TODO",
                    candidate=as_dict(fields.get("candidate_decision")).get("selected") or "TODO",
                )
            )
    else:
        lines.append("| none |  |  | 0 |  |  |  |  |  |")

    lines += [
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
        "d1_labeling_decision_template_json": relative_path(json_path),
        "d1_labeling_decision_template_markdown": relative_path(markdown_path),
    }
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(payload), encoding="utf-8")
    return payload


def build_from_args(args: argparse.Namespace) -> dict[str, Any]:
    generated_at = args.generated_at or utc_now()
    run_id = args.run_id or default_run_id(generated_at)
    output_dir = args.output_dir or (args.output_root / run_id)
    payload = build_template(
        review_packet_report=args.review_packet_report,
        review_packet_root=args.review_packet_root,
        generated_at=generated_at,
        run_id=run_id,
        limit=args.limit,
    )
    return write_report(payload, output_dir)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a bounded D1 labeling decision template.")
    parser.add_argument("--review-packet-report", type=Path)
    parser.add_argument("--review-packet-root", type=Path, default=DEFAULT_REVIEW_ROOT)
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
    except D1LabelingDecisionTemplateError as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True))
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(
            f"{payload['status']} D1 labeling decision template: "
            f"{as_dict(payload.get('paths')).get('d1_labeling_decision_template_markdown')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Validate a filled D1 labeling decision template.

The validation report checks selected decision values and candidate-promotion
gates only. It does not apply decisions, write candidate DBs, create training
samples, train/evaluate a model, or expose raw field samples.
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
DEFAULT_TEMPLATE_ROOT = REPO_ROOT / "reports" / "d1_labeling_decisions"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "reports" / "d1_labeling_decision_validations"
SCHEMA_VERSION = "egolink.d1_labeling_decision_validation.v0.1"
BUILDER_VERSION = "data-032.0"
SUMMARY_JSON = "d1_labeling_decision_validation.json"
SUMMARY_MARKDOWN = "d1_labeling_decision_validation.md"

REQUIRED_FIELDS = ("operator_label", "privacy_review", "training_consent", "split_plan", "candidate_decision")
PROMOTABLE_SPLITS = {"train", "validation", "test", "holdout"}
REJECTING_VALUES = {
    "operator_label": {"not_training_relevant"},
    "privacy_review": {"reject_private_data_risk", "needs_redaction_review"},
    "training_consent": {"not_approved_for_training", "defer"},
    "candidate_decision": {"reject_for_training", "needs_more_capture"},
}


class D1LabelingDecisionValidationError(RuntimeError):
    """Raised when a D1 labeling decision template cannot be validated safely."""


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


def bool_value(value: Any) -> bool:
    return bool(value) if isinstance(value, bool) else False


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise D1LabelingDecisionValidationError(f"D1 labeling decision template not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise D1LabelingDecisionValidationError(
            f"D1 labeling decision template is not valid JSON: {path}"
        ) from exc
    if not isinstance(payload, dict):
        raise D1LabelingDecisionValidationError(f"D1 labeling decision template must be a JSON object: {path}")
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
    return f"d1-labeling-decision-validation-{timestamp_slug(generated_at)[:16].rstrip('-')}"


def find_templates(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    reports = [path for path in root.glob("**/d1_labeling_decision_template.json") if path.is_file()]
    return sorted(reports, key=lambda path: path.stat().st_mtime, reverse=True)


def latest_template(root: Path) -> Path | None:
    reports = find_templates(root)
    return reports[0] if reports else None


def selected_value(slot: Mapping[str, Any]) -> str | None:
    selected = slot.get("selected")
    if selected in (None, ""):
        return None
    return str(selected)


def allowed_values(slot: Mapping[str, Any]) -> list[str]:
    return unique_text(as_list(slot.get("allowed_values")))


def validate_item(item: Mapping[str, Any]) -> dict[str, Any]:
    fields = as_dict(item.get("decision_fields"))
    selected: dict[str, str | None] = {}
    missing: list[str] = []
    invalid: list[dict[str, Any]] = []
    required_count = 0
    selected_count = 0

    for field_name in REQUIRED_FIELDS:
        slot = as_dict(fields.get(field_name))
        if bool_value(slot.get("required")) or slot.get("required", True) is True:
            required_count += 1
        value = selected_value(slot)
        selected[field_name] = value
        if value is not None:
            selected_count += 1
        if value is None and slot.get("required", True):
            missing.append(field_name)
            continue
        allowed = allowed_values(slot)
        if value is not None and allowed and value not in allowed:
            invalid.append({"field": field_name, "selected": value, "allowed_values": allowed})

    gates = {
        "operator_label_promotable": selected.get("operator_label") not in {None, "not_training_relevant"},
        "privacy_review_approved": selected.get("privacy_review") == "approved_bounded_summary_only",
        "training_consent_approved": selected.get("training_consent") == "approved_for_training",
        "split_promotable": selected.get("split_plan") in PROMOTABLE_SPLITS,
        "candidate_decision_ready": selected.get("candidate_decision") == "ready_for_candidate_store",
    }
    ready = not missing and not invalid and all(gates.values())
    rejected = any(selected.get(field) in values for field, values in REJECTING_VALUES.items())
    excluded = selected.get("split_plan") == "exclude"

    if invalid:
        status = "invalid_decisions"
    elif missing:
        status = "needs_decisions"
    elif ready:
        status = "ready_for_candidate_promotion"
    else:
        status = "review_complete_not_promotable"

    return {
        "packet_item_id": item.get("packet_item_id"),
        "intake_id": item.get("intake_id"),
        "source_run_id": item.get("source_run_id"),
        "readiness_run_id": item.get("readiness_run_id"),
        "device_id": item.get("device_id"),
        "decision_status": status,
        "required_decision_fields": required_count,
        "selected_decision_fields": selected_count,
        "missing_fields": missing,
        "invalid_fields": invalid,
        "selected_decisions": selected,
        "gates": gates,
        "ready_for_candidate_promotion": ready,
        "candidate_record_written": False,
        "training_allowed": False,
        "rejected_for_training": rejected,
        "excluded_from_training": excluded,
    }


def empty_summary() -> dict[str, Any]:
    return {
        "template_items": 0,
        "validation_items": 0,
        "required_decision_fields": 0,
        "selected_decision_fields": 0,
        "missing_decision_fields": 0,
        "invalid_decision_fields": 0,
        "items_needing_decisions": 0,
        "items_with_invalid_decisions": 0,
        "candidate_promotion_ready_items": 0,
        "review_complete_not_promotable_items": 0,
        "rejected_items": 0,
        "excluded_items": 0,
        "candidate_record_written_count": 0,
        "training_allowed_count": 0,
        "ready_for_candidate_promotion": False,
    }


def validation_status(items: list[dict[str, Any]]) -> str:
    if not items:
        return "no_decision_items"
    invalid = len([item for item in items if item.get("decision_status") == "invalid_decisions"])
    missing = len([item for item in items if item.get("decision_status") == "needs_decisions"])
    ready = len([item for item in items if item.get("decision_status") == "ready_for_candidate_promotion"])
    not_promotable = len([item for item in items if item.get("decision_status") == "review_complete_not_promotable"])
    if invalid:
        return "invalid_decisions"
    if missing:
        return "needs_decisions"
    if ready and not not_promotable:
        return "ready_for_candidate_promotion"
    if ready:
        return "mixed_review_complete"
    return "review_complete_not_promotable"


def summarize_items(items: list[dict[str, Any]], template_summary: Mapping[str, Any]) -> dict[str, Any]:
    summary = empty_summary()
    summary.update(
        {
            "template_items": template_summary.get("template_items", len(items)),
            "validation_items": len(items),
            "required_decision_fields": sum(int(item.get("required_decision_fields") or 0) for item in items),
            "selected_decision_fields": sum(int(item.get("selected_decision_fields") or 0) for item in items),
            "missing_decision_fields": sum(len(as_list(item.get("missing_fields"))) for item in items),
            "invalid_decision_fields": sum(len(as_list(item.get("invalid_fields"))) for item in items),
            "items_needing_decisions": len(
                [item for item in items if item.get("decision_status") == "needs_decisions"]
            ),
            "items_with_invalid_decisions": len(
                [item for item in items if item.get("decision_status") == "invalid_decisions"]
            ),
            "candidate_promotion_ready_items": len(
                [item for item in items if item.get("decision_status") == "ready_for_candidate_promotion"]
            ),
            "review_complete_not_promotable_items": len(
                [item for item in items if item.get("decision_status") == "review_complete_not_promotable"]
            ),
            "rejected_items": len([item for item in items if item.get("rejected_for_training")]),
            "excluded_items": len([item for item in items if item.get("excluded_from_training")]),
        }
    )
    summary["ready_for_candidate_promotion"] = (
        summary["candidate_promotion_ready_items"] > 0
        and summary["candidate_promotion_ready_items"] == summary["validation_items"]
    )
    return summary


def safe_scope(decision_template_summary_read: bool) -> dict[str, Any]:
    return {
        "decision_template_summary_read": decision_template_summary_read,
        "sample_jsonl_read": False,
        "payload_bytes_copied": False,
        "exact_coordinates_copied": False,
        "feature_rows_copied": False,
        "target_labels_written": False,
        "candidate_db_read": False,
        "candidate_db_written": False,
        "training_samples_written": False,
        "model_training_started": False,
        "model_evaluation_started": False,
        "model_artifact_written": False,
        "release_claim_allowed": False,
    }


def non_claims() -> list[str]:
    return [
        "This validation report checks a filled D1 labeling decision template only.",
        "It does not read sample JSONL, raw payloads, exact coordinates, feature rows, targets, candidate DBs, or model artifacts.",
        "It does not apply decisions, write candidate records, create training samples, train/evaluate a model, deploy inference, measure model footprint or power, or permit release claims.",
    ]


def next_step_for_status(status: str) -> str:
    if status == "no_decision_template":
        return "Generate a D1 labeling decision template before validation."
    if status == "no_decision_items":
        return "Regenerate the decision template after a review packet contains items."
    if status == "needs_decisions":
        return "Fill every required selected value in the D1 labeling decision template, then rerun validation."
    if status == "invalid_decisions":
        return "Fix selected values that are not in their allowed_values list, then rerun validation."
    if status in {"ready_for_candidate_promotion", "mixed_review_complete"}:
        return "Run a future explicit candidate-store promotion task after operator approval; this validation did not write records."
    return "Keep rejected/excluded items out of candidate promotion, or capture more D1 evidence and rerun the labeling flow."


def build_validation(
    *,
    decision_template_report: Path | None,
    decision_template_root: Path,
    generated_at: str,
    run_id: str,
    limit: int | None = None,
) -> dict[str, Any]:
    if limit is not None and limit <= 0:
        raise D1LabelingDecisionValidationError("--limit must be positive")
    if decision_template_report is None:
        decision_template_report = latest_template(decision_template_root)
    if decision_template_report is None:
        status = "no_decision_template"
        return {
            "tool": "validate_d1_labeling_decision_template",
            "schema_version": SCHEMA_VERSION,
            "builder_version": BUILDER_VERSION,
            "run_id": run_id,
            "generated_at": generated_at,
            "serves_demo": "D5",
            "status": status,
            "reason": "d1_labeling_decision_template_missing",
            "source_decision_template": {"available": False},
            "summary": empty_summary(),
            "validation": {"status": status, "items": [], "candidate_store_gate": "not_written"},
            "scope": safe_scope(False),
            "next_step": next_step_for_status(status),
            "non_claims": non_claims(),
        }

    payload = load_json(decision_template_report)
    template = as_dict(payload.get("decision_template"))
    raw_items = [as_dict(item) for item in as_list(template.get("items"))]
    if limit is not None:
        raw_items = raw_items[:limit]
    items = [validate_item(item) for item in raw_items if item]
    status = validation_status(items)
    summary = summarize_items(items, as_dict(payload.get("summary")))
    return {
        "tool": "validate_d1_labeling_decision_template",
        "schema_version": SCHEMA_VERSION,
        "builder_version": BUILDER_VERSION,
        "run_id": run_id,
        "generated_at": generated_at,
        "serves_demo": "D5",
        "status": status,
        "source_decision_template": {
            "available": True,
            "run_id": payload.get("run_id"),
            "status": payload.get("status"),
            "report_path": relative_path(decision_template_report, root=decision_template_root),
            "template_items": summary.get("template_items", 0),
        },
        "summary": summary,
        "validation": {
            "status": status,
            "items": items,
            "candidate_store_gate": "not_written",
            "apply_policy": "validation_report_must_be_consumed_by_a_future_explicit_candidate_store_task",
        },
        "scope": safe_scope(True),
        "next_step": next_step_for_status(status),
        "non_claims": non_claims(),
    }


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = as_dict(payload.get("summary"))
    validation = as_dict(payload.get("validation"))
    items = [as_dict(item) for item in as_list(validation.get("items"))]
    lines = [
        "# D1 Labeling Decision Validation",
        "",
        f"- Status: {payload.get('status')}",
        f"- Run ID: {payload.get('run_id')}",
        f"- Generated: {payload.get('generated_at')}",
        f"- Validation items: {summary.get('validation_items', 0)}",
        f"- Missing fields: {summary.get('missing_decision_fields', 0)}",
        f"- Invalid fields: {summary.get('invalid_decision_fields', 0)}",
        f"- Candidate-promotion ready items: {summary.get('candidate_promotion_ready_items', 0)}",
        "",
        "## Items",
        "",
        "| Packet Item | Source Run | Status | Missing Fields | Invalid Fields | Candidate Ready |",
        "|---|---|---|---|---|---|",
    ]
    if items:
        for item in items:
            invalid_fields = [as_dict(field).get("field") for field in as_list(item.get("invalid_fields"))]
            lines.append(
                "| {packet} | {source} | {status} | {missing} | {invalid} | {ready} |".format(
                    packet=item.get("packet_item_id") or "",
                    source=item.get("source_run_id") or "",
                    status=item.get("decision_status") or "",
                    missing=", ".join(str(value) for value in as_list(item.get("missing_fields"))) or "none",
                    invalid=", ".join(str(value) for value in invalid_fields if value) or "none",
                    ready="yes" if item.get("ready_for_candidate_promotion") else "no",
                )
            )
    else:
        lines.append("| none |  | no_decision_items | none | none | no |")

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
        "d1_labeling_decision_validation_json": relative_path(json_path),
        "d1_labeling_decision_validation_markdown": relative_path(markdown_path),
    }
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(payload), encoding="utf-8")
    return payload


def build_from_args(args: argparse.Namespace) -> dict[str, Any]:
    generated_at = args.generated_at or utc_now()
    run_id = args.run_id or default_run_id(generated_at)
    output_dir = args.output_dir or (args.output_root / run_id)
    payload = build_validation(
        decision_template_report=args.decision_template_report,
        decision_template_root=args.decision_template_root,
        generated_at=generated_at,
        run_id=run_id,
        limit=args.limit,
    )
    return write_report(payload, output_dir)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a bounded D1 labeling decision template.")
    parser.add_argument("--decision-template-report", type=Path)
    parser.add_argument("--decision-template-root", type=Path, default=DEFAULT_TEMPLATE_ROOT)
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
    except D1LabelingDecisionValidationError as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True))
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(
            f"{payload['status']} D1 labeling decision validation: "
            f"{as_dict(payload.get('paths')).get('d1_labeling_decision_validation_markdown')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

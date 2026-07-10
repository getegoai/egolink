"""Export Tiny Safety synthetic hard cases for human review.

This command consumes the MODEL-DEVICE-008 synthetic stress report and writes a
bounded review packet. The packet is for labeling workflow design only; records
remain synthetic, unreviewed, and training-disallowed until a human explicitly
reviews them in a later task.
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
from typing import Any, Mapping, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from model_lab.safety_companion.src import tiny_safety_model


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MODEL_DIR = (
    REPO_ROOT
    / "model_artifacts"
    / "tiny_safety_model"
    / "MODEL-DEVICE-001-tiny-safety-v0-20260707"
)
DEFAULT_STRESS_REPORT = DEFAULT_MODEL_DIR / "evaluation" / "tiny_safety_synthetic_stress.json"
DEFAULT_OUTPUT_DIR = DEFAULT_MODEL_DIR / "label_review"
MANIFEST_JSON = "tiny_safety_hard_case_review_manifest.json"
RECORDS_JSONL = "tiny_safety_hard_case_review_records.jsonl"
REPORT_MARKDOWN = "tiny_safety_hard_case_review.md"
SHA256 = "sha256.txt"
MANIFEST_SCHEMA_VERSION = "egolink.tiny_safety_hard_case_review_manifest.v0.1"
RECORD_SCHEMA_VERSION = "egolink.tiny_safety_hard_case_review_record.v0.1"
REVIEW_BUILDER_VERSION = "model-device-009.0"
REVIEW_LABELS = tuple(tiny_safety_model.STATE_LABELS) + ("exclude_from_training",)


class HardCaseReviewError(RuntimeError):
    """Raised when a hard-case review packet cannot be built safely."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def slug_id(value: object) -> str:
    text = str(value or "unknown").strip().lower()
    text = re.sub(r"[^a-z0-9_.-]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-._")
    return text or "unknown"


def bounded_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except (OSError, ValueError):
        return path.name


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise HardCaseReviewError(f"cannot read stress report: {path}") from exc
    except json.JSONDecodeError as exc:
        raise HardCaseReviewError(f"stress report is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise HardCaseReviewError("stress report JSON must be an object")
    return payload


def default_review_set_id(stress_report: Mapping[str, Any], generated_at: str) -> str:
    model_id = slug_id(stress_report.get("model_id") or "tiny-safety")
    stamp = slug_id(generated_at[:19])
    return f"{model_id}-hardcase-review-{stamp}"


def hard_case_reasons(case: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    if bool(case.get("disagreement")):
        reasons.append("synthetic_oracle_disagreement")
    if bool(case.get("low_confidence")):
        reasons.append("low_confidence")
    if bool(case.get("low_margin")):
        reasons.append("low_margin")
    return reasons or ["manual_spot_check"]


def priority_score(case: Mapping[str, Any]) -> float:
    confidence = as_float(case.get("confidence"))
    margin = as_float(case.get("score_margin"))
    score = 0.0
    if bool(case.get("disagreement")):
        score += 100.0
    if bool(case.get("low_confidence")):
        score += 20.0
    if bool(case.get("low_margin")):
        score += 10.0
    score += max(0.0, 1.0 - confidence)
    score += max(0.0, 0.08 - margin)
    return round(score, 6)


def sort_cases(cases: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return sorted(
        cases,
        key=lambda case: (
            -priority_score(case),
            as_float(case.get("confidence")),
            as_float(case.get("score_margin")),
            str(case.get("case_id") or ""),
        ),
    )


def select_cases(cases: Sequence[Mapping[str, Any]], max_records: int) -> list[Mapping[str, Any]]:
    sorted_cases = sort_cases(cases)
    if max_records <= 0:
        return sorted_cases
    return sorted_cases[:max_records]


def normalize_features(value: Any) -> dict[str, float]:
    features = as_dict(value)
    normalized: dict[str, float] = {}
    for name in tiny_safety_model.FEATURE_NAMES:
        if name in features:
            normalized[name] = round(as_float(features[name]), 6)
    for name in sorted(features):
        if name not in normalized:
            normalized[name] = round(as_float(features[name]), 6)
    return normalized


def build_review_record(
    *,
    review_set_id: str,
    rank: int,
    case: Mapping[str, Any],
    stress_report: Mapping[str, Any],
    stress_report_path: Path,
    stress_report_hash: str,
    generated_at: str,
) -> dict[str, Any]:
    case_id = str(case.get("case_id") or f"case-{rank:04d}")
    expected_label = str(case.get("expected_label") or "unknown")
    predicted_label = str(case.get("predicted_label") or "unknown")
    reasons = hard_case_reasons(case)
    return {
        "schema_version": RECORD_SCHEMA_VERSION,
        "review_record_id": f"{review_set_id}:{case_id}",
        "review_set_id": review_set_id,
        "rank": rank,
        "created_at": generated_at,
        "source": {
            "case_id": case_id,
            "source_report_path": bounded_path(stress_report_path),
            "source_report_hash": stress_report_hash,
            "synthetic_only": True,
            "source_type": "model-device-008-synthetic-hard-case",
        },
        "model": {
            "model_id": stress_report.get("model_id"),
            "model_version": stress_report.get("model_version"),
            "artifact_hash": stress_report.get("artifact_hash"),
            "predicted_label": predicted_label,
            "confidence": round(as_float(case.get("confidence")), 6),
            "score_margin": round(as_float(case.get("score_margin")), 6),
        },
        "synthetic_oracle": {
            "label": expected_label,
            "is_truth_source": False,
            "note": "Synthetic oracle label is for triage only, not a reviewed target.",
        },
        "priority": {
            "score": priority_score(case),
            "reasons": reasons,
            "disagreement": bool(case.get("disagreement")),
            "low_confidence": bool(case.get("low_confidence")),
            "low_margin": bool(case.get("low_margin")),
        },
        "features": normalize_features(case.get("features")),
        "review": {
            "state": "needs_human_review",
            "allowed_labels": list(REVIEW_LABELS),
            "reviewer_label": None,
            "reviewer_notes": None,
            "training_allowed_after_review": False,
        },
        "privacy": {
            "synthetic_only": True,
            "field_or_private_data": False,
            "raw_audio_or_image": False,
            "private_coordinates": False,
        },
    }


def count_values(records: Sequence[Mapping[str, Any]], dotted_path: tuple[str, ...]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for record in records:
        value: Any = record
        for key in dotted_path:
            value = as_dict(value).get(key)
        counter[str(value or "unknown")] += 1
    return dict(sorted(counter.items()))


def count_reasons(records: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for record in records:
        for reason in as_list(as_dict(record.get("priority")).get("reasons")):
            counter[str(reason or "unknown")] += 1
    return dict(sorted(counter.items()))


def build_packet(
    *,
    stress_report_path: Path,
    generated_at: str,
    review_set_id: str | None = None,
    max_records: int = 24,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    stress_report = read_json(stress_report_path)
    evaluation = as_dict(stress_report.get("evaluation"))
    hard_cases = [case for case in as_list(evaluation.get("hard_case_examples")) if isinstance(case, dict)]
    if not hard_cases:
        raise HardCaseReviewError("stress report has no hard_case_examples")
    stress_hash = file_sha256(stress_report_path)
    final_review_set_id = review_set_id or default_review_set_id(stress_report, generated_at)
    selected_cases = select_cases(hard_cases, max_records)
    records = [
        build_review_record(
            review_set_id=final_review_set_id,
            rank=index,
            case=case,
            stress_report=stress_report,
            stress_report_path=stress_report_path,
            stress_report_hash=stress_hash,
            generated_at=generated_at,
        )
        for index, case in enumerate(selected_cases, start=1)
    ]
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "builder_version": REVIEW_BUILDER_VERSION,
        "review_set_id": final_review_set_id,
        "generated_at": generated_at,
        "status": "ready_for_synthetic_review",
        "reason": "synthetic_hard_cases_exported_for_human_review",
        "source": {
            "stress_report_path": bounded_path(stress_report_path),
            "stress_report_hash": stress_hash,
            "stress_schema_version": stress_report.get("schema_version"),
            "model_id": stress_report.get("model_id"),
            "model_version": stress_report.get("model_version"),
            "artifact_hash": stress_report.get("artifact_hash"),
            "stress_case_count": evaluation.get("case_count"),
            "source_hard_case_examples": len(hard_cases),
        },
        "counts": {
            "records_exported": len(records),
            "records_available": len(hard_cases),
            "expected_labels": count_values(records, ("synthetic_oracle", "label")),
            "predicted_labels": count_values(records, ("model", "predicted_label")),
            "priority_reasons": count_reasons(records),
        },
        "review_policy": {
            "record_state": "needs_human_review",
            "allowed_labels": list(REVIEW_LABELS),
            "reviewer_label_required_before_training": True,
            "training_allowed": False,
            "synthetic_oracle_is_truth_source": False,
        },
        "gates": {
            "synthetic_only": True,
            "field_or_private_data_read": False,
            "human_review_completed": False,
            "training_dataset_manifest": "not_created",
            "model_training": "not_run",
            "model_behavior_changed": False,
            "hardware_contacted": False,
            "real_accuracy_claimed": False,
            "external_escalation_enabled": False,
        },
        "outputs": {
            "manifest": MANIFEST_JSON,
            "records_jsonl": RECORDS_JSONL,
            "markdown": REPORT_MARKDOWN,
            "sha256": SHA256,
        },
        "known_gaps": [
            "Records are synthetic stress cases only and are not reviewed labels.",
            "Synthetic oracle labels are triage hints, not training targets.",
            "No field samples, private data, candidate DBs, hardware, or firmware are contacted.",
            "No real-world accuracy, latency, RAM, flash, power, or release-readiness claim is made.",
        ],
        "next_step": (
            "Review these records as UI/workflow fixtures, then repeat the same review "
            "handoff with consented real field/session candidates before training."
        ),
    }
    return manifest, records


def render_markdown(manifest: Mapping[str, Any], records: Sequence[Mapping[str, Any]]) -> str:
    counts = as_dict(manifest.get("counts"))
    source = as_dict(manifest.get("source"))
    lines = [
        "# Tiny Safety Hard-Case Review Packet",
        "",
        f"- Review set: `{manifest.get('review_set_id')}`",
        f"- Status: `{manifest.get('status')}`",
        f"- Model: `{source.get('model_id')}` / `{source.get('model_version')}`",
        f"- Records exported: `{counts.get('records_exported')}`",
        f"- Source hard-case examples: `{source.get('source_hard_case_examples')}`",
        f"- Training allowed: `{as_dict(manifest.get('review_policy')).get('training_allowed')}`",
        "",
        "## Priority Reasons",
        "",
    ]
    reasons = as_dict(counts.get("priority_reasons"))
    if reasons:
        lines.extend(f"- `{reason}`: `{count}`" for reason, count in reasons.items())
    else:
        lines.append("- none")
    lines += ["", "## First Records", ""]
    for record in records[:10]:
        model = as_dict(record.get("model"))
        oracle = as_dict(record.get("synthetic_oracle"))
        priority = as_dict(record.get("priority"))
        source_record = as_dict(record.get("source"))
        lines.append(
            f"- `{source_record.get('case_id')}` oracle `{oracle.get('label')}` "
            f"predicted `{model.get('predicted_label')}` confidence `{model.get('confidence')}` "
            f"reasons `{', '.join(as_list(priority.get('reasons')))}`"
        )
    if not records:
        lines.append("- none")
    lines += ["", "## Known Gaps", ""]
    lines.extend(f"- {item}" for item in as_list(manifest.get("known_gaps")))
    lines.append("")
    return "\n".join(lines)


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_records(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    text = "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records)
    path.write_text(text, encoding="utf-8")


def write_sha(path: Path, files: Sequence[Path]) -> None:
    lines = [f"{file_sha256(file_path)}  {file_path.name}" for file_path in files]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_packet(manifest: Mapping[str, Any], records: Sequence[Mapping[str, Any]], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / MANIFEST_JSON
    records_path = output_dir / RECORDS_JSONL
    markdown_path = output_dir / REPORT_MARKDOWN
    sha_path = output_dir / SHA256
    write_json(manifest_path, manifest)
    write_records(records_path, records)
    markdown_path.write_text(render_markdown(manifest, records), encoding="utf-8")
    write_sha(sha_path, [manifest_path, records_path, markdown_path])
    return {
        "manifest": bounded_path(manifest_path),
        "records_jsonl": bounded_path(records_path),
        "markdown": bounded_path(markdown_path),
        "sha256": bounded_path(sha_path),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stress-report", type=Path, default=DEFAULT_STRESS_REPORT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--review-set-id", default="")
    parser.add_argument("--generated-at", default="")
    parser.add_argument("--max-records", type=int, default=24)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    generated_at = args.generated_at or utc_now()
    manifest, records = build_packet(
        stress_report_path=args.stress_report,
        generated_at=generated_at,
        review_set_id=args.review_set_id or None,
        max_records=args.max_records,
    )
    paths = write_packet(manifest, records, args.output_dir)
    output = {**manifest, "paths": paths}
    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"PASS tiny safety hard-case review packet: {paths['markdown']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

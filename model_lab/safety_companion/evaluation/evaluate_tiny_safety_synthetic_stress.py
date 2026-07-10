"""Run a synthetic stress evaluation for Tiny Safety v0.

The stress matrix is deterministic and synthetic-only. It is meant to expose
boundary cases for review, not to claim real-world safety accuracy.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
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
DEFAULT_ARTIFACT = DEFAULT_MODEL_DIR / "tiny_safety_model.json"
DEFAULT_OUTPUT_DIR = DEFAULT_MODEL_DIR / "evaluation"
REPORT_JSON = "tiny_safety_synthetic_stress.json"
REPORT_MARKDOWN = "tiny_safety_synthetic_stress.md"
SHA256 = "sha256.txt"
STATE_LABELS = tuple(tiny_safety_model.STATE_LABELS)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON must be an object: {path}")
    return payload


def relative_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except (OSError, ValueError):
        return path.as_posix()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def feature_row(
    *,
    row_id: str,
    impact: float,
    fall: float,
    stationary_norm: float,
    distress: float,
    unknown_loud: float,
) -> dict[str, Any]:
    lookup = {
        "motion_impact_score": impact,
        "motion_fall_score": fall,
        "motion_stationary_norm": stationary_norm,
        "motion_activity_confidence": 0.82,
        "motion_device_worn": 1.0,
        "audio_distress_score": distress,
        "audio_impact_sound_score": min(1.0, max(impact, fall) * 0.75),
        "audio_unknown_loud_sound_score": unknown_loud,
        "location_outside_safe_zone": 0.0,
        "location_dwell_norm": 0.05,
        "network_connectivity_score": 0.8,
        "network_offline_norm": 0.05,
        "device_battery_low": 0.18,
        "history_recent_risk_norm": 0.1,
    }
    return {
        "row_id": row_id,
        "features": [round(lookup[name], 6) for name in tiny_safety_model.FEATURE_NAMES],
        "synthetic_only": True,
        "source": "model-device-008-synthetic-boundary-matrix",
    }


def synthetic_oracle(row: Mapping[str, Any]) -> str:
    values = list(row.get("features") or [])
    feature = {name: float(values[index]) for index, name in enumerate(tiny_safety_model.FEATURE_NAMES)}
    impact = feature["motion_impact_score"]
    fall = feature["motion_fall_score"]
    stationary = feature["motion_stationary_norm"]
    distress = feature["audio_distress_score"]
    impact_sound = feature["audio_impact_sound_score"]
    unknown_loud = feature["audio_unknown_loud_sound_score"]
    risk_score = (
        0.34 * impact
        + 0.30 * fall
        + 0.18 * stationary
        + 0.12 * distress
        + 0.06 * impact_sound
    )
    if (impact >= 0.75 and fall >= 0.70 and stationary >= 0.45) or risk_score >= 0.72:
        return "possible_risk"
    if (impact >= 0.50 and fall >= 0.45 and stationary >= 0.20) or risk_score >= 0.46:
        return "needs_check"
    if impact >= 0.25 or fall >= 0.25 or distress >= 0.35 or unknown_loud >= 0.40 or risk_score >= 0.20:
        return "uncertain"
    return "normal"


def generate_cases() -> list[dict[str, Any]]:
    impacts = (0.0, 0.20, 0.40, 0.60, 0.80, 0.95)
    falls = (0.0, 0.20, 0.40, 0.60, 0.80, 0.95)
    stationary_values = (0.0, 0.20, 0.45, 0.70, 0.95)
    distress_values = (0.0, 0.35, 0.70)
    cases: list[dict[str, Any]] = []
    for impact in impacts:
        for fall in falls:
            for stationary in stationary_values:
                for distress in distress_values:
                    unknown_loud = 0.45 if distress == 0.35 and impact < 0.50 else 0.10
                    row_id = (
                        f"stress-i{int(impact * 100):03d}-f{int(fall * 100):03d}-"
                        f"s{int(stationary * 100):03d}-d{int(distress * 100):03d}"
                    )
                    row = feature_row(
                        row_id=row_id,
                        impact=impact,
                        fall=fall,
                        stationary_norm=stationary,
                        distress=distress,
                        unknown_loud=unknown_loud,
                    )
                    row["expected_label"] = synthetic_oracle(row)
                    cases.append(row)
    return cases


def score_margin(scores: Mapping[str, float]) -> float:
    values = sorted((float(value) for value in scores.values()), reverse=True)
    if len(values) < 2:
        return 0.0
    return round(values[0] - values[1], 6)


def evaluate_cases(
    artifact: Mapping[str, Any],
    cases: Sequence[Mapping[str, Any]],
    *,
    low_confidence_threshold: float,
    low_margin_threshold: float,
    max_examples: int,
) -> dict[str, Any]:
    confusion: dict[str, Counter[str]] = {label: Counter() for label in STATE_LABELS}
    by_expected: dict[str, dict[str, Any]] = {
        label: {"count": 0, "agree": 0, "low_confidence": 0, "low_margin": 0}
        for label in STATE_LABELS
    }
    examples: list[dict[str, Any]] = []
    agree = 0
    low_confidence_count = 0
    low_margin_count = 0

    for row in cases:
        expected = str(row["expected_label"])
        prediction = tiny_safety_model.predict(tiny_safety_model.model_input_from_feature_row(row), artifact)
        predicted = prediction.state_label
        margin = score_margin(prediction.scores)
        is_agree = predicted == expected
        is_low_confidence = prediction.confidence < low_confidence_threshold
        is_low_margin = margin < low_margin_threshold
        agree += int(is_agree)
        low_confidence_count += int(is_low_confidence)
        low_margin_count += int(is_low_margin)
        confusion.setdefault(expected, Counter())[predicted] += 1
        by_expected.setdefault(expected, {"count": 0, "agree": 0, "low_confidence": 0, "low_margin": 0})
        by_expected[expected]["count"] += 1
        by_expected[expected]["agree"] += int(is_agree)
        by_expected[expected]["low_confidence"] += int(is_low_confidence)
        by_expected[expected]["low_margin"] += int(is_low_margin)
        if (not is_agree) or is_low_confidence or is_low_margin:
            examples.append(
                {
                    "case_id": row["row_id"],
                    "expected_label": expected,
                    "predicted_label": predicted,
                    "confidence": prediction.confidence,
                    "score_margin": margin,
                    "disagreement": not is_agree,
                    "low_confidence": is_low_confidence,
                    "low_margin": is_low_margin,
                    "features": dict(zip(tiny_safety_model.FEATURE_NAMES, row["features"])),
                }
            )

    for stats in by_expected.values():
        count = int(stats["count"])
        stats["agreement_rate"] = round(float(stats["agree"]) / count, 6) if count else 0.0

    examples.sort(
        key=lambda item: (
            not bool(item["disagreement"]),
            float(item["confidence"]),
            float(item["score_margin"]),
            str(item["case_id"]),
        )
    )

    priority_labels = sorted(
        by_expected.items(),
        key=lambda item: (
            -(int(item[1]["count"]) - int(item[1]["agree"])),
            -int(item[1]["low_confidence"]),
            item[0],
        ),
    )
    return {
        "case_count": len(cases),
        "agreement_count": agree,
        "synthetic_agreement_rate": round(agree / len(cases), 6) if cases else 0.0,
        "low_confidence_threshold": low_confidence_threshold,
        "low_confidence_count": low_confidence_count,
        "low_margin_threshold": low_margin_threshold,
        "low_margin_count": low_margin_count,
        "confusion": {label: dict(counter) for label, counter in confusion.items()},
        "by_expected": by_expected,
        "hard_case_examples": examples[:max_examples],
        "labeling_priorities": [
            {
                "expected_label": label,
                "disagreement_count": int(stats["count"]) - int(stats["agree"]),
                "low_confidence_count": int(stats["low_confidence"]),
                "low_margin_count": int(stats["low_margin"]),
            }
            for label, stats in priority_labels
            if int(stats["count"]) - int(stats["agree"]) or int(stats["low_confidence"]) or int(stats["low_margin"])
        ],
    }


def build_report(
    *,
    artifact_path: Path,
    evaluated_at: str,
    low_confidence_threshold: float,
    low_margin_threshold: float,
    max_examples: int,
) -> dict[str, Any]:
    artifact = read_json(artifact_path)
    cases = generate_cases()
    evaluation = evaluate_cases(
        artifact,
        cases,
        low_confidence_threshold=low_confidence_threshold,
        low_margin_threshold=low_margin_threshold,
        max_examples=max_examples,
    )
    return {
        "schema_version": "egolink.tiny_safety_synthetic_stress.v0.1",
        "evaluated_at": evaluated_at,
        "serves_demo": "D4-D5",
        "model_id": artifact.get("model_id"),
        "model_version": artifact.get("model_version"),
        "artifact_path": relative_path(artifact_path),
        "artifact_hash": file_sha256(artifact_path),
        "oracle": {
            "name": "model-device-008-transparent-synthetic-boundary-oracle",
            "synthetic_only": True,
            "description": "Heuristic boundary matrix for review prioritization, not a truth source.",
        },
        "evaluation": evaluation,
        "scope": {
            "synthetic_only": True,
            "hardware_contacted": False,
            "firmware_changed": False,
            "model_behavior_changed": False,
            "model_training_started": False,
            "field_or_private_data_read": False,
            "real_accuracy_claimed": False,
        },
        "known_gaps": [
            "Synthetic oracle agreement is not real-world accuracy.",
            "No field samples, private data, or candidate DB records are read.",
            "Low-confidence cases need labeling review before training use.",
            "Runtime RAM, latency, power, and product readiness are not evaluated.",
        ],
        "non_claims": [
            "No real-world fall detection, distress detection, or proactive safety accuracy is claimed.",
            "No model behavior, thresholds, labels, contracts, or firmware are changed.",
            "No real SMS, call, dispatch, or external escalation action is enabled.",
        ],
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    evaluation = report["evaluation"]
    lines = [
        "# Tiny Safety Synthetic Stress Evaluation",
        "",
        f"- Model ID: `{report['model_id']}`",
        f"- Model version: `{report['model_version']}`",
        f"- Cases: `{evaluation['case_count']}`",
        f"- Synthetic agreement: `{evaluation['agreement_count']} / {evaluation['case_count']}`",
        f"- Synthetic agreement rate: `{evaluation['synthetic_agreement_rate']}`",
        f"- Low-confidence cases: `{evaluation['low_confidence_count']}`",
        f"- Low-margin cases: `{evaluation['low_margin_count']}`",
        "",
        "## Labeling Priorities",
        "",
    ]
    priorities = evaluation["labeling_priorities"]
    if priorities:
        lines.extend(
            f"- `{item['expected_label']}`: disagreements `{item['disagreement_count']}`, "
            f"low confidence `{item['low_confidence_count']}`, low margin `{item['low_margin_count']}`"
            for item in priorities
        )
    else:
        lines.append("- none")
    lines += ["", "## Hard Case Examples", ""]
    for item in evaluation["hard_case_examples"][:10]:
        lines.append(
            f"- `{item['case_id']}` expected `{item['expected_label']}` predicted "
            f"`{item['predicted_label']}` confidence `{item['confidence']}` margin `{item['score_margin']}`"
        )
    if not evaluation["hard_case_examples"]:
        lines.append("- none")
    lines += ["", "## Known Gaps", ""]
    lines.extend(f"- {item}" for item in report["known_gaps"])
    lines += ["", "## Non-Claims", ""]
    lines.extend(f"- {item}" for item in report["non_claims"])
    lines.append("")
    return "\n".join(lines)


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_sha256(path: Path, files: list[Path]) -> None:
    lines = [f"{file_sha256(file_path)}  {file_path.name}" for file_path in files]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_report(report: Mapping[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / REPORT_JSON
    markdown_path = output_dir / REPORT_MARKDOWN
    sha_path = output_dir / SHA256
    write_json(json_path, report)
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    write_sha256(sha_path, [json_path, markdown_path])
    return {
        "report_json": relative_path(json_path),
        "report_markdown": relative_path(markdown_path),
        "sha256": relative_path(sha_path),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-artifact", type=Path, default=DEFAULT_ARTIFACT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--evaluated-at", default="")
    parser.add_argument("--low-confidence-threshold", type=float, default=0.45)
    parser.add_argument("--low-margin-threshold", type=float, default=0.08)
    parser.add_argument("--max-examples", type=int, default=24)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(
        artifact_path=args.model_artifact,
        evaluated_at=args.evaluated_at or utc_now(),
        low_confidence_threshold=args.low_confidence_threshold,
        low_margin_threshold=args.low_margin_threshold,
        max_examples=args.max_examples,
    )
    paths = write_report(report, args.output_dir)
    output = {**report, "paths": paths}
    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"PASS tiny safety synthetic stress: {paths['report_markdown']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

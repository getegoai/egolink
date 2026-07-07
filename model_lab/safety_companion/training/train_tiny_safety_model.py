"""Train Tiny Safety Model v0 from deterministic synthetic integration data."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from model_lab.safety_companion.src import tiny_safety_model


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "model_artifacts" / "tiny_safety_model"
SUMMARY_JSON = "tiny_safety_model.json"
MODEL_CARD = "tiny_safety_model_card.md"
EVAL_JSONL = "tiny_safety_eval.jsonl"
SHA256 = "sha256.txt"


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


def default_model_id(generated_at: str) -> str:
    return f"tiny-safety-v0-{timestamp_slug(generated_at)[:16].rstrip('-')}"


def relative_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO_ROOT.resolve()).as_posix()
    except (OSError, ValueError):
        return path.name


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def write_sha256(path: Path, files: list[Path]) -> None:
    lines = []
    for file_path in files:
        digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {file_path.name}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def render_model_card(artifact: Mapping[str, Any]) -> str:
    metrics = artifact["metrics"]
    deployment = artifact["deployment"]
    safety = artifact["safety"]
    lines = [
        "# Tiny Safety Model v0",
        "",
        f"- Model ID: `{artifact['model_id']}`",
        f"- Version: `{artifact['model_version']}`",
        f"- Generated: `{artifact['generated_at']}`",
        f"- Scope: `{metrics['metric_scope']}`",
        f"- Training rows: `{artifact['training_data']['training_rows']}`",
        f"- Holdout rows: `{artifact['training_data']['holdout_rows']}`",
        f"- Holdout accuracy: `{metrics['holdout']['accuracy']}`",
        "",
        "## State Labels",
        "",
    ]
    lines.extend(f"- `{label}`" for label in artifact["output_state_labels"])
    lines += [
        "",
        "## Deployment Status",
        "",
        f"- Export format: `{deployment['export_format']}`",
        f"- Firmware integrated: `{deployment['firmware_integrated']}`",
        f"- Device deployed: `{deployment['device_deployed']}`",
        f"- Measured latency ms: `{deployment['measured_latency_ms']}`",
        f"- Measured power mW: `{deployment['measured_power_mw']}`",
        "",
        "## Safety Boundary",
        "",
        f"- SOS/cancel handled by Safety Kernel: `{safety['sos_cancel_handled_by_safety_kernel']}`",
        f"- Model controls external actions: `{safety['model_controls_external_actions']}`",
        f"- Release claim allowed: `{safety['release_claim_allowed']}`",
        "",
        "## Non-Claims",
        "",
    ]
    lines.extend(f"- {item}" for item in artifact["non_claims"])
    lines.append("")
    return "\n".join(lines)


def build_eval_rows(artifact: Mapping[str, Any], rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows:
        prediction = tiny_safety_model.predict(
            tiny_safety_model.model_input_from_feature_row(row),
            artifact,
        )
        output.append(
            {
                "row_id": row["row_id"],
                "label": row["label"],
                "predicted_label": prediction.state_label,
                "confidence": prediction.confidence,
                "scores": prediction.scores,
                "synthetic_only": True,
                "real_world_metric": False,
            }
        )
    return output


def train_and_write(
    *,
    model_id: str,
    generated_at: str,
    output_dir: Path,
    samples_per_class: int,
    seed: int,
) -> dict[str, Any]:
    rows = tiny_safety_model.synthetic_training_rows(samples_per_class=samples_per_class, seed=seed)
    training_rows, holdout_rows = tiny_safety_model.split_rows(rows)
    artifact = tiny_safety_model.build_artifact(
        model_id=model_id,
        generated_at=generated_at,
        training_rows=training_rows,
        holdout_rows=holdout_rows,
    )
    eval_rows = build_eval_rows(artifact, holdout_rows)
    json_path = output_dir / SUMMARY_JSON
    card_path = output_dir / MODEL_CARD
    eval_path = output_dir / EVAL_JSONL
    sha_path = output_dir / SHA256
    artifact["paths"] = {
        "model_artifact_json": relative_path(json_path),
        "model_card_markdown": relative_path(card_path),
        "synthetic_eval_jsonl": relative_path(eval_path),
        "sha256": relative_path(sha_path),
    }
    write_json(json_path, artifact)
    card_path.write_text(render_model_card(artifact), encoding="utf-8")
    write_jsonl(eval_path, eval_rows)
    write_sha256(sha_path, [json_path, card_path, eval_path])
    return artifact


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-id")
    parser.add_argument("--generated-at")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--samples-per-class", type=int, default=24)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    generated_at = args.generated_at or utc_now()
    model_id = args.model_id or default_model_id(generated_at)
    output_dir = args.output_dir or (args.output_root / model_id)
    artifact = train_and_write(
        model_id=model_id,
        generated_at=generated_at,
        output_dir=output_dir,
        samples_per_class=args.samples_per_class,
        seed=args.seed,
    )
    if args.json:
        print(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"PASS tiny safety model: {artifact['paths']['model_card_markdown']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

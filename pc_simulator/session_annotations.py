"""Annotation utilities for Ego Link M1 session recordings."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from pc_simulator import session_recorder


ANNOTATION_SCHEMA_VERSION = "egolink.session_annotation.v0.1"
ALLOWED_LABELS = {"safe", "needs_help", "false_alarm", "cancelled", "no_response"}
ALLOWED_ANNOTATOR_TYPES = {"human", "user_confirmation", "rule", "teacher_model"}

MODEL_LABELS_BY_LABEL: dict[str, dict[str, str]] = {
    "safe": {
        "risk_type": "none",
        "severity": "none",
        "user_state": "safe",
        "action_outcome": "confirmed_safe",
    },
    "needs_help": {
        "risk_type": "uncertain",
        "severity": "high",
        "user_state": "needs_help",
        "action_outcome": "help_requested",
    },
    "false_alarm": {
        "risk_type": "none",
        "severity": "none",
        "user_state": "safe",
        "action_outcome": "false_alarm",
    },
    "cancelled": {
        "risk_type": "none",
        "severity": "none",
        "user_state": "safe",
        "action_outcome": "dismissed",
    },
    "no_response": {
        "risk_type": "uncertain",
        "severity": "medium",
        "user_state": "unresponsive",
        "action_outcome": "not_executed",
    },
}


class AnnotationError(ValueError):
    """Raised when a session annotation cannot be applied safely."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def created_at_ms(value: str) -> int:
    text = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if isinstance(value, dict):
            rows.append(value)
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def annotation_targets(recording_dir: Path) -> list[dict[str, Any]]:
    recording_dir = recording_dir.resolve()
    targets: list[dict[str, Any]] = []
    for source_file, filename in (("sensor_frames", "sensor_frames.jsonl"), ("events", "events.jsonl")):
        for file_index, row in enumerate(load_jsonl(recording_dir / filename), start=1):
            key = row.get("source_event_key")
            if not key:
                continue
            targets.append(
                {
                    "index": len(targets) + 1,
                    "source_file": source_file,
                    "file_index": file_index,
                    "source_event_key": str(key),
                    "source_event_type": row.get("source_event_type"),
                    "record_type": row.get("record_type"),
                    "frame_type": row.get("frame_type"),
                    "event_type": row.get("event_type"),
                    "seq": row.get("seq"),
                    "ts": row.get("ts"),
                    "received_at": row.get("received_at"),
                }
            )
    return targets


def resolve_target(
    recording_dir: Path,
    *,
    source_event_key: str | None = None,
    target_index: int | None = None,
) -> dict[str, Any]:
    if bool(source_event_key) == (target_index is not None):
        raise AnnotationError("Provide exactly one of source_event_key or target_index.")
    targets = annotation_targets(recording_dir)
    if source_event_key:
        for target in targets:
            if target["source_event_key"] == source_event_key:
                return target
        raise AnnotationError(f"source_event_key not found: {source_event_key}")
    assert target_index is not None
    if target_index < 1 or target_index > len(targets):
        raise AnnotationError(f"target_index {target_index} is out of range 1..{len(targets)}.")
    return targets[target_index - 1]


def default_annotation_id(session_id: str, source_event_key: str, label: str, created_at: str) -> str:
    seed = f"{session_id}|{source_event_key}|{label}|{created_at}"
    return "ann-" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


def build_annotation(
    *,
    manifest: dict[str, Any],
    target: dict[str, Any],
    label: str,
    created_at: str | None = None,
    annotation_id: str | None = None,
    annotator_type: str = "human",
    notes: str | None = None,
    collection_allowed: bool = True,
    training_allowed: bool = False,
    raw_audio_allowed: bool = False,
    raw_image_allowed: bool = False,
) -> dict[str, Any]:
    if label not in ALLOWED_LABELS:
        raise AnnotationError(f"Unsupported label `{label}`. Allowed labels: {', '.join(sorted(ALLOWED_LABELS))}.")
    if annotator_type not in ALLOWED_ANNOTATOR_TYPES:
        raise AnnotationError(
            f"Unsupported annotator_type `{annotator_type}`. "
            f"Allowed types: {', '.join(sorted(ALLOWED_ANNOTATOR_TYPES))}."
        )
    session_id = str(manifest.get("session_id") or "")
    if not session_id:
        raise AnnotationError("session_manifest.json is missing session_id.")
    generated = created_at or utc_now()
    source_event_key = str(target["source_event_key"])
    return {
        "schema_version": ANNOTATION_SCHEMA_VERSION,
        "annotation_id": annotation_id or default_annotation_id(session_id, source_event_key, label, generated),
        "session_id": session_id,
        "source_event_key": source_event_key,
        "source_event_type": target.get("source_event_type"),
        "label": label,
        "created_at": generated,
        "annotator_type": annotator_type,
        "notes": notes,
        "consent": {
            "collection_allowed": bool(collection_allowed),
            "training_allowed": bool(training_allowed),
            "raw_audio_allowed": bool(raw_audio_allowed),
            "raw_image_allowed": bool(raw_image_allowed),
        },
        "model_labels": dict(MODEL_LABELS_BY_LABEL[label]),
    }


def summarize_annotations(annotations: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    outcomes: Counter[str] = Counter()
    for row in annotations:
        model_labels = row.get("model_labels")
        if isinstance(model_labels, dict):
            outcome = model_labels.get("action_outcome")
        else:
            outcome = row.get("outcome")
        outcomes[str(outcome or "unknown")] += 1
    return {
        "annotation_labels": dict(sorted(Counter(str(row.get("label") or "unknown") for row in annotations).items())),
        "annotation_outcomes": dict(sorted(outcomes.items())),
        "annotator_types": dict(sorted(Counter(str(row.get("annotator_type") or "unknown") for row in annotations).items())),
    }


def refresh_recording_metadata(
    recording_dir: Path,
    *,
    annotations: list[dict[str, Any]] | None = None,
) -> dict[str, Path]:
    recording_dir = recording_dir.resolve()
    paths = {
        "manifest": recording_dir / "session_manifest.json",
        "file_manifest": recording_dir / "file_manifest.json",
        "sensor_frames": recording_dir / "sensor_frames.jsonl",
        "events": recording_dir / "events.jsonl",
        "annotations": recording_dir / "annotations.jsonl",
        "summary": recording_dir / "session_recording.md",
    }
    manifest = load_json(paths["manifest"])
    sensor_frames = load_jsonl(paths["sensor_frames"])
    events = load_jsonl(paths["events"])
    annotation_rows = annotations if annotations is not None else load_jsonl(paths["annotations"])
    manifest.setdefault("record_counts", {})["annotations"] = len(annotation_rows)
    write_json(paths["manifest"], manifest)
    summary = session_recorder.render_markdown(
        {
            "manifest": manifest,
            "sensor_frames": sensor_frames,
            "events": events,
            "annotations": annotation_rows,
        }
    )
    paths["summary"].write_text(summary, encoding="utf-8")
    files_to_hash = {name: path for name, path in paths.items() if name != "file_manifest"}
    write_json(paths["file_manifest"], session_recorder.build_file_manifest(files_to_hash))
    return paths


def annotate_recording(
    recording_dir: Path,
    *,
    label: str,
    source_event_key: str | None = None,
    target_index: int | None = None,
    created_at: str | None = None,
    annotation_id: str | None = None,
    annotator_type: str = "human",
    notes: str | None = None,
    collection_allowed: bool = True,
    training_allowed: bool = False,
    raw_audio_allowed: bool = False,
    raw_image_allowed: bool = False,
) -> dict[str, Any]:
    recording_dir = recording_dir.resolve()
    manifest = load_json(recording_dir / "session_manifest.json")
    target = resolve_target(recording_dir, source_event_key=source_event_key, target_index=target_index)
    annotation = build_annotation(
        manifest=manifest,
        target=target,
        label=label,
        created_at=created_at,
        annotation_id=annotation_id,
        annotator_type=annotator_type,
        notes=notes,
        collection_allowed=collection_allowed,
        training_allowed=training_allowed,
        raw_audio_allowed=raw_audio_allowed,
        raw_image_allowed=raw_image_allowed,
    )
    annotations_path = recording_dir / "annotations.jsonl"
    annotations = load_jsonl(annotations_path)
    annotation_ids = {str(row.get("annotation_id")) for row in annotations if row.get("annotation_id")}
    if annotation["annotation_id"] in annotation_ids:
        raise AnnotationError(f"annotation_id already exists: {annotation['annotation_id']}")
    annotations.append(annotation)
    write_jsonl(annotations_path, annotations)
    paths = refresh_recording_metadata(recording_dir, annotations=annotations)
    return {
        "ok": True,
        "recording_dir": str(recording_dir),
        "annotation": annotation,
        "target": target,
        "paths": {name: str(path) for name, path in paths.items()},
        "record_counts": load_json(paths["manifest"]).get("record_counts", {}),
        "annotation_summary": summarize_annotations(annotations),
    }

"""Training-candidate store for Ego Link M1 data flywheel.

This module turns an inspected session recording plus annotations into bounded
candidate records. It does not train models, retain raw private payload bytes,
or mark records training-ready without a later review gate.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from pc_simulator import session_inspector


STORE_SCHEMA_VERSION = "egolink.training_candidate_store.v0.1"
RECORD_SCHEMA_VERSION = "egolink.training_candidate_record.v0.1"
STORE_BUILDER_VERSION = "data-003.0"


class CandidateStoreError(ValueError):
    """Raised when a candidate store cannot be built safely."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CandidateStoreError(f"Missing required file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CandidateStoreError(f"Invalid JSON in {path}: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise CandidateStoreError(f"Expected JSON object in {path}")
    return payload


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise CandidateStoreError(f"Missing required file: {path}")
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CandidateStoreError(f"Invalid JSONL in {path}:{line_number}: {exc.msg}") from exc
        if not isinstance(payload, dict):
            raise CandidateStoreError(f"Expected JSON object in {path}:{line_number}")
        rows.append(payload)
    return rows


def sha1_text(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def source_manifest_hash(recording_dir: Path, file_manifest: Mapping[str, Any]) -> str:
    files = file_manifest.get("files") if isinstance(file_manifest.get("files"), dict) else {}
    manifest_entry = files.get("manifest") if isinstance(files.get("manifest"), dict) else {}
    manifest_hash = manifest_entry.get("sha256")
    if manifest_hash:
        return str(manifest_hash)
    manifest_path = recording_dir / "session_manifest.json"
    digest = hashlib.sha256()
    with manifest_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def first_device_id(manifest: Mapping[str, Any]) -> str:
    device_ids = manifest.get("device_ids")
    if isinstance(device_ids, list) and device_ids:
        return str(device_ids[0])
    return "unknown"


def rows_by_source_key(recording_dir: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for filename in ("sensor_frames.jsonl", "events.jsonl"):
        for row in load_jsonl(recording_dir / filename):
            key = row.get("source_event_key")
            if key:
                rows[str(key)] = row
    return rows


def candidate_state(quality_report: Mapping[str, Any], consent: Mapping[str, Any]) -> str:
    if quality_report.get("passed") is not True:
        return "quality_blocked"
    if consent.get("collection_allowed") is False:
        return "consent_blocked"
    if consent.get("raw_audio_allowed") is True or consent.get("raw_image_allowed") is True:
        return "privacy_blocked"
    return "candidate"


def consent_status(consent: Mapping[str, Any]) -> str:
    if consent.get("collection_allowed") is False:
        return "collection_disallowed"
    if consent.get("training_allowed") is True:
        return "training_requested_pending_review"
    return "training_not_allowed"


def source_feature_group(source_row: Mapping[str, Any]) -> str:
    for key in ("frame_type", "event_type", "source_event_type"):
        value = source_row.get(key)
        if value:
            return str(value)
    return "unknown"


def build_candidate_record(
    *,
    recording_dir: Path,
    manifest: Mapping[str, Any],
    file_manifest: Mapping[str, Any],
    annotation: Mapping[str, Any],
    source_row: Mapping[str, Any],
    quality_report: Mapping[str, Any],
    generated_at: str,
) -> dict[str, Any]:
    session_id = str(manifest.get("session_id") or "")
    annotation_id = str(annotation.get("annotation_id") or "")
    source_key = str(annotation.get("source_event_key") or "")
    if not session_id or not annotation_id or not source_key:
        raise CandidateStoreError("Annotation is missing session_id, annotation_id, or source_event_key.")
    model_labels = annotation.get("model_labels") if isinstance(annotation.get("model_labels"), dict) else {}
    consent = annotation.get("consent") if isinstance(annotation.get("consent"), dict) else {}
    source_hash = source_manifest_hash(recording_dir, file_manifest)
    privacy_class = "structured_sensor_event"
    state = candidate_state(quality_report, consent)
    record_id = "cand-" + sha1_text(f"{session_id}|{annotation_id}|{source_key}")[:16]
    candidate_type = str(model_labels.get("risk_type") or annotation.get("label") or "unknown")
    feature_group = source_feature_group(source_row)
    device_id = str(source_row.get("device_id") or first_device_id(manifest))
    firmware = manifest.get("firmware") if isinstance(manifest.get("firmware"), dict) else {}
    return {
        "schema_version": RECORD_SCHEMA_VERSION,
        "record_id": record_id,
        "session_id": session_id,
        "window_id": source_key,
        "candidate_type": candidate_type,
        "created_at": annotation.get("created_at") or generated_at,
        "state": state,
        "training_allowed": False,
        "review_required": True,
        "review_reason": "DATA-003 stores candidates only; reviewed_training_candidate is a later gate.",
        "source_refs": {
            "recording_path": str(recording_dir),
            "source_event_key": source_key,
            "source_event_type": source_row.get("source_event_type") or source_row.get("event_type"),
            "annotation_id": annotation_id,
            "raw_frame_hashes": [],
        },
        "device_context": {
            "device_id": device_id,
            "device_role": "unknown",
            "firmware_version": firmware.get("version", "unknown"),
            "model_version": "none",
            "source_status": source_row.get("source_status") or source_row.get("source_availability") or "unknown",
            "transport_type": source_row.get("link_type") or "unknown",
        },
        "consent": {
            "consent_required": True,
            "consent_status": consent_status(consent),
            "consent_evidence_ref": annotation_id,
            "reviewed_by": "pending",
            "reviewed_at": None,
            "training_allowed": False,
            "annotation_training_requested": bool(consent.get("training_allowed")),
        },
        "privacy": {
            "privacy_class": privacy_class,
            "coordinate_redaction": "raw_coordinates_not_copied",
            "wifi_identifier_policy": "raw_identifier_not_copied",
            "guardian_data_state": "absent_or_redacted",
            "raw_audio_allowed": False,
            "raw_image_allowed": False,
        },
        "retention_and_deletion": {
            "retain_until": "review_required",
            "retention_basis": "engineering_candidate_review",
            "delete_request_id": None,
            "deletion_state": "not_requested",
        },
        "evidence": {
            "evidence_refs": [
                "session_manifest.json",
                "file_manifest.json",
                "sensor_frames.jsonl",
                "events.jsonl",
                "annotations.jsonl",
            ],
            "parser_status": "parsed",
            "parse_failure_reason": None,
            "redaction_state": "bounded_summary_only",
            "payload_bytes_retained": False,
        },
        "features": {
            "feature_groups": [feature_group],
            "feature_generator_version": "not_generated",
            "feature_quality": "not_generated",
            "missing_feature_reasons": ["DATA-003 does not generate model features."],
        },
        "labels": {
            "label_set": {
                "label": annotation.get("label"),
                "model_labels": model_labels,
            },
            "label_source": annotation.get("annotator_type") or "unknown",
            "label_confidence": "unreviewed",
            "label_review_state": "pending",
            "confirmation_outcome": model_labels.get("action_outcome"),
        },
        "quality": {
            "quality_gate": "pass" if quality_report.get("passed") is True else "fail",
            "quality_score": quality_report.get("quality_score"),
            "known_gaps": [issue.get("code") for issue in quality_report.get("warnings", []) if isinstance(issue, dict)],
            "excluded_evidence": ["raw_audio", "raw_image", "raw_dashboard_payload"],
            "blockers": [issue.get("code") for issue in quality_report.get("errors", []) if isinstance(issue, dict)],
        },
        "split": {
            "split_name": "unassigned",
            "split_strategy": "session_blocked",
            "split_group_key": session_id,
            "split_leakage_checked": False,
        },
        "lineage": {
            "schema_versions": {
                "record": RECORD_SCHEMA_VERSION,
                "session_recording": manifest.get("schema_version"),
                "file_manifest": file_manifest.get("schema_version"),
            },
            "generator_versions": {
                "store_builder": STORE_BUILDER_VERSION,
                "recorder": manifest.get("recorder_version"),
            },
            "source_manifest_hash": source_hash,
            "parent_dataset_id": None,
        },
        "release_review": {
            "experiment_id": None,
            "model_candidate_id": None,
            "release_gate_state": "not_started",
            "ota_update_state": "planned_not_implemented",
        },
    }


def candidate_records_from_recording(
    recording_dir: Path,
    *,
    generated_at: str | None = None,
) -> list[dict[str, Any]]:
    recording_dir = recording_dir.resolve()
    generated = generated_at or utc_now()
    manifest = load_json(recording_dir / "session_manifest.json")
    file_manifest = load_json(recording_dir / "file_manifest.json")
    annotations = load_jsonl(recording_dir / "annotations.jsonl")
    source_rows = rows_by_source_key(recording_dir)
    quality_report = session_inspector.inspect_recording(recording_dir, generated_at=generated)
    records: list[dict[str, Any]] = []
    for annotation in annotations:
        source_key = str(annotation.get("source_event_key") or "")
        source_row = source_rows.get(source_key)
        if source_row is None:
            source_row = {"source_event_key": source_key, "source_event_type": "unknown"}
        records.append(
            build_candidate_record(
                recording_dir=recording_dir,
                manifest=manifest,
                file_manifest=file_manifest,
                annotation=annotation,
                source_row=source_row,
                quality_report=quality_report,
                generated_at=generated,
            )
        )
    return records


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def initialize(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS training_candidate_sessions (
            session_id TEXT PRIMARY KEY,
            recording_dir TEXT NOT NULL,
            schema_version TEXT NOT NULL,
            quality_gate TEXT NOT NULL,
            quality_score REAL,
            annotations INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS training_candidate_records (
            record_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            window_id TEXT NOT NULL,
            candidate_type TEXT NOT NULL,
            state TEXT NOT NULL,
            training_allowed INTEGER NOT NULL,
            privacy_class TEXT NOT NULL,
            label_set TEXT NOT NULL,
            quality_gate TEXT NOT NULL,
            quality_score REAL,
            split_name TEXT NOT NULL,
            source_manifest_hash TEXT,
            record_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_training_candidate_session
            ON training_candidate_records(session_id);
        CREATE INDEX IF NOT EXISTS idx_training_candidate_state
            ON training_candidate_records(state);
        """
    )


def store_recording(
    recording_dir: Path,
    db_path: Path,
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    recording_dir = recording_dir.resolve()
    generated = generated_at or utc_now()
    manifest = load_json(recording_dir / "session_manifest.json")
    annotations = load_jsonl(recording_dir / "annotations.jsonl")
    quality_report = session_inspector.inspect_recording(recording_dir, generated_at=generated)
    records = candidate_records_from_recording(recording_dir, generated_at=generated)
    db = connect(db_path)
    try:
        initialize(db)
        db.execute(
            """
            INSERT INTO training_candidate_sessions (
                session_id, recording_dir, schema_version, quality_gate,
                quality_score, annotations, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                recording_dir=excluded.recording_dir,
                schema_version=excluded.schema_version,
                quality_gate=excluded.quality_gate,
                quality_score=excluded.quality_score,
                annotations=excluded.annotations,
                updated_at=excluded.updated_at
            """,
            (
                str(manifest.get("session_id") or ""),
                str(recording_dir),
                STORE_SCHEMA_VERSION,
                "pass" if quality_report.get("passed") is True else "fail",
                quality_report.get("quality_score"),
                len(annotations),
                generated,
            ),
        )
        for record in records:
            db.execute(
                """
                INSERT INTO training_candidate_records (
                    record_id, session_id, window_id, candidate_type, state,
                    training_allowed, privacy_class, label_set, quality_gate,
                    quality_score, split_name, source_manifest_hash, record_json,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(record_id) DO UPDATE SET
                    session_id=excluded.session_id,
                    window_id=excluded.window_id,
                    candidate_type=excluded.candidate_type,
                    state=excluded.state,
                    training_allowed=excluded.training_allowed,
                    privacy_class=excluded.privacy_class,
                    label_set=excluded.label_set,
                    quality_gate=excluded.quality_gate,
                    quality_score=excluded.quality_score,
                    split_name=excluded.split_name,
                    source_manifest_hash=excluded.source_manifest_hash,
                    record_json=excluded.record_json,
                    updated_at=excluded.updated_at
                """,
                (
                    record["record_id"],
                    record["session_id"],
                    record["window_id"],
                    record["candidate_type"],
                    record["state"],
                    int(bool(record["training_allowed"])),
                    record["privacy"]["privacy_class"],
                    json.dumps(record["labels"]["label_set"], ensure_ascii=False, sort_keys=True),
                    record["quality"]["quality_gate"],
                    record["quality"]["quality_score"],
                    record["split"]["split_name"],
                    record["lineage"]["source_manifest_hash"],
                    json.dumps(record, ensure_ascii=False, sort_keys=True),
                    record["created_at"],
                    generated,
                ),
            )
        db.commit()
    finally:
        db.close()
    state_counts = Counter(record["state"] for record in records)
    return {
        "ok": True,
        "schema_version": STORE_SCHEMA_VERSION,
        "db_path": str(db_path),
        "recording_dir": str(recording_dir),
        "session_id": manifest.get("session_id"),
        "quality_gate": "pass" if quality_report.get("passed") is True else "fail",
        "quality_score": quality_report.get("quality_score"),
        "annotations": len(annotations),
        "records_written": len(records),
        "state_counts": dict(sorted(state_counts.items())),
        "training_allowed_records": 0,
        "warnings": [] if annotations else ["no_annotations_no_candidate_records"],
    }

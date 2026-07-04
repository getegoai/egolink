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
DATA_FLYWHEEL_STATUS_SCHEMA_VERSION = "egolink.data_flywheel_status.v0.1"
DATA_FLYWHEEL_STATUS_BUILDER_VERSION = "data-005.0"
REVIEW_QUEUE_SCHEMA_VERSION = "egolink.training_candidate_review_queue.v0.1"
REVIEW_ACTION_SCHEMA_VERSION = "egolink.training_candidate_review_action.v0.1"
REVIEW_BUILDER_VERSION = "data-005.0"
REVIEW_ACTIONS = ("approve_for_training", "reject", "needs_changes")
DEFAULT_REVIEW_QUEUE_LIMIT = 25


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


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


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

        CREATE TABLE IF NOT EXISTS training_candidate_review_actions (
            review_id TEXT PRIMARY KEY,
            record_id TEXT NOT NULL,
            decision TEXT NOT NULL,
            reviewer TEXT NOT NULL,
            reviewed_at TEXT NOT NULL,
            action_json TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_training_candidate_review_record
            ON training_candidate_review_actions(record_id);
        """
    )


def table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def group_counts(connection: sqlite3.Connection, table_name: str, column_name: str) -> dict[str, int]:
    rows = connection.execute(
        f"SELECT {column_name} AS value, COUNT(*) AS count FROM {table_name} GROUP BY {column_name}"
    ).fetchall()
    return {
        str(row["value"] if row["value"] is not None else "unknown"): int(row["count"])
        for row in rows
    }


def build_store_unavailable_status(db_path: Path, *, generated_at: str, reason: str) -> dict[str, Any]:
    return {
        "schema_version": DATA_FLYWHEEL_STATUS_SCHEMA_VERSION,
        "builder_version": DATA_FLYWHEEL_STATUS_BUILDER_VERSION,
        "generated_at": generated_at,
        "status": "needs_capture",
        "pipeline_stage": reason,
        "candidate_store": {
            "available": False,
            "reason": reason,
            "db_path": str(db_path),
            "schema_version": STORE_SCHEMA_VERSION,
        },
        "counts": {
            "sessions_total": 0,
            "records_total": 0,
            "training_allowed_records": 0,
            "review_required_records": 0,
            "needs_review_records": 0,
            "reviewed_training_candidate_records": 0,
            "experiment_input_records": 0,
            "release_candidate_records": 0,
        },
        "state_counts": {},
        "candidate_type_counts": {},
        "quality_gate_counts": {},
        "privacy_class_counts": {},
        "label_review_state_counts": {},
        "split_counts": {},
        "review": {
            "label_review_pending_records": 0,
            "split_leakage_unchecked_records": 0,
            "privacy_or_consent_blocked_records": 0,
            "quality_blocked_records": 0,
        },
        "review_queue": {
            "schema_version": REVIEW_QUEUE_SCHEMA_VERSION,
            "available": False,
            "reason": reason,
            "pending_records": 0,
            "sample_records": [],
            "available_actions": list(REVIEW_ACTIONS),
        },
        "readiness": {
            "model_training_ready": False,
            "reason": reason,
            "dataset_manifest_ready": False,
            "training_server_ready": False,
            "on_device_deployment_ready": False,
        },
        "warnings": [reason],
        "blockers": [reason],
        "next_step": "Build the candidate store from reviewed session recordings before labeling or training.",
        "non_claims": [
            "No model training has run.",
            "No candidate record is training-ready from this status alone.",
            "No firmware or on-device inference behavior changes.",
        ],
    }


def load_candidate_record_jsons(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        "SELECT record_json FROM training_candidate_records ORDER BY record_id"
    ).fetchall()
    records: list[dict[str, Any]] = []
    for row in rows:
        try:
            record = json.loads(row["record_json"])
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def load_candidate_record_json(connection: sqlite3.Connection, record_id: str) -> dict[str, Any]:
    row = connection.execute(
        "SELECT record_json FROM training_candidate_records WHERE record_id = ?",
        (record_id,),
    ).fetchone()
    if row is None:
        raise CandidateStoreError(f"Candidate record not found: {record_id}")
    try:
        record = json.loads(row["record_json"])
    except (TypeError, json.JSONDecodeError) as exc:
        raise CandidateStoreError(f"Candidate record is not valid JSON: {record_id}") from exc
    if not isinstance(record, dict):
        raise CandidateStoreError(f"Candidate record is not a JSON object: {record_id}")
    return record


def label_review_state(record: Mapping[str, Any]) -> str:
    return str(as_dict(record.get("labels")).get("label_review_state") or "unknown")


def record_needs_review(record: Mapping[str, Any]) -> bool:
    state = str(record.get("state") or "unknown")
    if state in {"reviewed_training_candidate", "experiment_input", "release_candidate", "review_rejected"}:
        return False
    if record.get("review_required") is True:
        return True
    if label_review_state(record) in {"pending", "needs_revision"}:
        return True
    if as_dict(record.get("split")).get("split_leakage_checked") is not True:
        return True
    return state in {"candidate", "quality_blocked", "consent_blocked", "privacy_blocked"}


def bounded_review_queue_item(record: Mapping[str, Any]) -> dict[str, Any]:
    source_refs = as_dict(record.get("source_refs"))
    device_context = as_dict(record.get("device_context"))
    consent = as_dict(record.get("consent"))
    privacy = as_dict(record.get("privacy"))
    labels = as_dict(record.get("labels"))
    label_set = as_dict(labels.get("label_set"))
    quality = as_dict(record.get("quality"))
    split = as_dict(record.get("split"))
    features = as_dict(record.get("features"))
    return {
        "record_id": record.get("record_id"),
        "session_id": record.get("session_id"),
        "window_id": record.get("window_id"),
        "candidate_type": record.get("candidate_type"),
        "state": record.get("state"),
        "training_allowed": bool(record.get("training_allowed")),
        "review_required": bool(record.get("review_required")),
        "review_reason": record.get("review_reason"),
        "label": label_set.get("label"),
        "label_review_state": labels.get("label_review_state"),
        "label_confidence": labels.get("label_confidence"),
        "consent_status": consent.get("consent_status"),
        "annotation_training_requested": bool(consent.get("annotation_training_requested")),
        "consent_reviewed_by": consent.get("reviewed_by"),
        "privacy_class": privacy.get("privacy_class"),
        "quality_gate": quality.get("quality_gate"),
        "quality_score": quality.get("quality_score"),
        "quality_blockers": quality.get("blockers") or [],
        "split_name": split.get("split_name"),
        "split_leakage_checked": bool(split.get("split_leakage_checked")),
        "feature_groups": features.get("feature_groups") or [],
        "device_id": device_context.get("device_id"),
        "firmware_version": device_context.get("firmware_version"),
        "source_status": device_context.get("source_status"),
        "source_event_type": source_refs.get("source_event_type"),
        "annotation_id": source_refs.get("annotation_id"),
        "available_actions": list(REVIEW_ACTIONS),
    }


def bounded_review_queue_items(
    records: list[dict[str, Any]],
    *,
    limit: int | None = DEFAULT_REVIEW_QUEUE_LIMIT,
) -> list[dict[str, Any]]:
    items = [
        bounded_review_queue_item(record)
        for record in records
        if record_needs_review(record)
    ]
    items.sort(key=lambda item: (str(item.get("session_id") or ""), str(item.get("record_id") or "")))
    if limit is None:
        return items
    return items[: max(0, limit)]


def candidate_review_queue(
    db_path: Path,
    *,
    limit: int = DEFAULT_REVIEW_QUEUE_LIMIT,
    generated_at: str | None = None,
) -> dict[str, Any]:
    generated = generated_at or utc_now()
    db_path = db_path.resolve()
    if not db_path.exists():
        return {
            "schema_version": REVIEW_QUEUE_SCHEMA_VERSION,
            "generated_at": generated,
            "available": False,
            "reason": "candidate_store_missing",
            "pending_records": 0,
            "records": [],
            "available_actions": list(REVIEW_ACTIONS),
        }

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        required_tables = {"training_candidate_sessions", "training_candidate_records"}
        if not all(table_exists(connection, table) for table in required_tables):
            return {
                "schema_version": REVIEW_QUEUE_SCHEMA_VERSION,
                "generated_at": generated,
                "available": False,
                "reason": "candidate_store_uninitialized",
                "pending_records": 0,
                "records": [],
                "available_actions": list(REVIEW_ACTIONS),
            }
        records = load_candidate_record_jsons(connection)
    finally:
        connection.close()

    all_items = bounded_review_queue_items(records, limit=None)
    return {
        "schema_version": REVIEW_QUEUE_SCHEMA_VERSION,
        "generated_at": generated,
        "available": True,
        "pending_records": len(all_items),
        "records": all_items[: max(0, limit)],
        "available_actions": list(REVIEW_ACTIONS),
        "non_claims": [
            "Review queue records are bounded summaries only.",
            "No raw candidate record, raw payload, private coordinate, DB file, or runtime JSONL log is exported.",
        ],
    }


def review_id_for(record_id: str, decision: str, reviewer: str, reviewed_at: str) -> str:
    return "review-" + sha1_text(f"{record_id}|{decision}|{reviewer}|{reviewed_at}")[:16]


def require_approval_eligibility(
    record: Mapping[str, Any],
    *,
    split_name: str,
    split_leakage_checked: bool,
    privacy_reviewed: bool,
    quality_reviewed: bool,
) -> list[str]:
    blockers: list[str] = []
    consent = as_dict(record.get("consent"))
    privacy = as_dict(record.get("privacy"))
    quality = as_dict(record.get("quality"))
    if record.get("state") != "candidate":
        blockers.append("state_not_candidate")
    if quality.get("quality_gate") != "pass":
        blockers.append("quality_gate_not_pass")
    if consent.get("annotation_training_requested") is not True:
        blockers.append("training_not_requested_by_annotation")
    if consent.get("consent_status") != "training_requested_pending_review":
        blockers.append("consent_not_pending_training_review")
    if privacy.get("raw_audio_allowed") is True or privacy.get("raw_image_allowed") is True:
        blockers.append("raw_media_allowed")
    if not privacy_reviewed:
        blockers.append("privacy_review_not_confirmed")
    if not quality_reviewed:
        blockers.append("quality_review_not_confirmed")
    if not split_leakage_checked:
        blockers.append("split_leakage_not_checked")
    if split_name in {"", "unassigned"}:
        blockers.append("split_not_assigned")
    return blockers


def update_reviewed_record(
    record: dict[str, Any],
    *,
    decision: str,
    reviewer: str,
    reviewed_at: str,
    split_name: str,
    split_leakage_checked: bool,
    privacy_reviewed: bool,
    quality_reviewed: bool,
    notes: str | None,
) -> dict[str, Any]:
    updated = dict(record)
    labels = dict(as_dict(updated.get("labels")))
    consent = dict(as_dict(updated.get("consent")))
    split = dict(as_dict(updated.get("split")))
    review = {
        "schema_version": REVIEW_ACTION_SCHEMA_VERSION,
        "builder_version": REVIEW_BUILDER_VERSION,
        "decision": decision,
        "reviewer": reviewer,
        "reviewed_at": reviewed_at,
        "notes": notes or "",
        "privacy_reviewed": privacy_reviewed,
        "quality_reviewed": quality_reviewed,
        "split_leakage_checked": split_leakage_checked,
    }
    updated["review"] = review
    updated["updated_at"] = reviewed_at

    if decision == "approve_for_training":
        labels["label_review_state"] = "reviewed"
        labels["label_confidence"] = "reviewed"
        consent["reviewed_by"] = reviewer
        consent["reviewed_at"] = reviewed_at
        consent["training_allowed"] = True
        split["split_name"] = split_name
        split["split_leakage_checked"] = True
        updated["state"] = "reviewed_training_candidate"
        updated["training_allowed"] = True
        updated["review_required"] = False
        updated["review_reason"] = "DATA-005 approved after label, consent, privacy, quality, and split review."
    elif decision == "reject":
        labels["label_review_state"] = "rejected"
        labels["label_confidence"] = "reviewed"
        consent["reviewed_by"] = reviewer
        consent["reviewed_at"] = reviewed_at
        consent["training_allowed"] = False
        updated["state"] = "review_rejected"
        updated["training_allowed"] = False
        updated["review_required"] = False
        updated["review_reason"] = "DATA-005 rejected by review."
    elif decision == "needs_changes":
        labels["label_review_state"] = "needs_revision"
        labels["label_confidence"] = "needs_review"
        consent["training_allowed"] = False
        updated["training_allowed"] = False
        updated["review_required"] = True
        updated["review_reason"] = "DATA-005 review requested changes before any training use."
    else:
        raise CandidateStoreError(f"Unsupported review decision: {decision}")

    updated["labels"] = labels
    updated["consent"] = consent
    updated["split"] = split
    return updated


def save_candidate_record(connection: sqlite3.Connection, record: Mapping[str, Any], *, updated_at: str) -> None:
    labels = as_dict(record.get("labels"))
    quality = as_dict(record.get("quality"))
    split = as_dict(record.get("split"))
    privacy = as_dict(record.get("privacy"))
    lineage = as_dict(record.get("lineage"))
    connection.execute(
        """
        UPDATE training_candidate_records
        SET state = ?,
            training_allowed = ?,
            privacy_class = ?,
            label_set = ?,
            quality_gate = ?,
            quality_score = ?,
            split_name = ?,
            source_manifest_hash = ?,
            record_json = ?,
            updated_at = ?
        WHERE record_id = ?
        """,
        (
            record.get("state"),
            int(bool(record.get("training_allowed"))),
            as_dict(record.get("privacy")).get("privacy_class", "unknown"),
            json.dumps(as_dict(labels.get("label_set")), ensure_ascii=False, sort_keys=True),
            quality.get("quality_gate", "unknown"),
            quality.get("quality_score"),
            split.get("split_name", "unassigned"),
            lineage.get("source_manifest_hash"),
            json.dumps(record, ensure_ascii=False, sort_keys=True),
            updated_at,
            record.get("record_id"),
        ),
    )


def review_candidate_record(
    db_path: Path,
    *,
    record_id: str,
    decision: str,
    reviewer: str,
    split_name: str = "unassigned",
    split_leakage_checked: bool = False,
    privacy_reviewed: bool = False,
    quality_reviewed: bool = False,
    reviewed_at: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    if decision not in REVIEW_ACTIONS:
        raise CandidateStoreError(f"Unsupported review decision: {decision}")
    if not reviewer.strip():
        raise CandidateStoreError("Reviewer is required.")
    reviewed = reviewed_at or utc_now()
    db = connect(db_path)
    try:
        initialize(db)
        record = load_candidate_record_json(db, record_id)
        if decision == "approve_for_training":
            blockers = require_approval_eligibility(
                record,
                split_name=split_name,
                split_leakage_checked=split_leakage_checked,
                privacy_reviewed=privacy_reviewed,
                quality_reviewed=quality_reviewed,
            )
            if blockers:
                raise CandidateStoreError("Candidate cannot be approved for training: " + ", ".join(sorted(blockers)))
        updated = update_reviewed_record(
            record,
            decision=decision,
            reviewer=reviewer.strip(),
            reviewed_at=reviewed,
            split_name=split_name,
            split_leakage_checked=split_leakage_checked,
            privacy_reviewed=privacy_reviewed,
            quality_reviewed=quality_reviewed,
            notes=notes,
        )
        action = {
            "schema_version": REVIEW_ACTION_SCHEMA_VERSION,
            "builder_version": REVIEW_BUILDER_VERSION,
            "review_id": review_id_for(record_id, decision, reviewer.strip(), reviewed),
            "record_id": record_id,
            "decision": decision,
            "reviewer": reviewer.strip(),
            "reviewed_at": reviewed,
            "split_name": split_name,
            "split_leakage_checked": split_leakage_checked,
            "privacy_reviewed": privacy_reviewed,
            "quality_reviewed": quality_reviewed,
            "notes": notes or "",
        }
        save_candidate_record(db, updated, updated_at=reviewed)
        db.execute(
            """
            INSERT INTO training_candidate_review_actions (
                review_id, record_id, decision, reviewer, reviewed_at, action_json
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(review_id) DO UPDATE SET
                record_id=excluded.record_id,
                decision=excluded.decision,
                reviewer=excluded.reviewer,
                reviewed_at=excluded.reviewed_at,
                action_json=excluded.action_json
            """,
            (
                action["review_id"],
                record_id,
                decision,
                reviewer.strip(),
                reviewed,
                json.dumps(action, ensure_ascii=False, sort_keys=True),
            ),
        )
        db.commit()
    finally:
        db.close()
    return {
        "ok": True,
        "schema_version": REVIEW_ACTION_SCHEMA_VERSION,
        "decision": decision,
        "review_id": action["review_id"],
        "record": bounded_review_queue_item(updated),
        "non_claims": [
            "No model training has run.",
            "No dataset manifest has been exported.",
            "No on-device model behavior changed.",
        ],
    }


def readiness_reason(*, records_total: int, reviewed_training_candidate_records: int) -> str:
    if records_total == 0:
        return "no_candidate_records"
    if reviewed_training_candidate_records == 0:
        return "candidate_review_not_complete"
    return "reviewed_candidates_available"


def next_data_flywheel_step(status: str, blockers: list[str]) -> str:
    if status == "needs_labels":
        return "Add or review annotations, then rebuild the candidate store summary."
    if "consent_or_privacy_review_pending" in blockers:
        return "Run the consent/privacy review before any dataset export or training task."
    if "quality_review_pending" in blockers:
        return "Fix or exclude low-quality candidate records before dataset export."
    if "split_leakage_review_pending" in blockers:
        return "Run session/device/time-blocked split review before training."
    if status == "ready_for_experiment":
        return "Export a dataset manifest and hand it to the offline training runner."
    return "Create the labeling/review loop so candidate records can be promoted deliberately."


def summarize_candidate_store(db_path: Path, *, generated_at: str | None = None) -> dict[str, Any]:
    generated = generated_at or utc_now()
    db_path = db_path.resolve()
    if not db_path.exists():
        return build_store_unavailable_status(db_path, generated_at=generated, reason="candidate_store_missing")

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        required_tables = {"training_candidate_sessions", "training_candidate_records"}
        if not all(table_exists(connection, table) for table in required_tables):
            return build_store_unavailable_status(db_path, generated_at=generated, reason="candidate_store_uninitialized")

        sessions_total = int(connection.execute("SELECT COUNT(*) FROM training_candidate_sessions").fetchone()[0])
        records_total = int(connection.execute("SELECT COUNT(*) FROM training_candidate_records").fetchone()[0])
        training_allowed_records = int(
            connection.execute(
                "SELECT COALESCE(SUM(training_allowed), 0) FROM training_candidate_records"
            ).fetchone()[0]
            or 0
        )
        latest_updated_row = connection.execute(
            """
            SELECT MAX(updated_at) AS latest_updated_at FROM (
                SELECT updated_at FROM training_candidate_sessions
                UNION ALL
                SELECT updated_at FROM training_candidate_records
            )
            """
        ).fetchone()
        latest_updated_at = latest_updated_row["latest_updated_at"] if latest_updated_row else None
        state_counts = group_counts(connection, "training_candidate_records", "state")
        candidate_type_counts = group_counts(connection, "training_candidate_records", "candidate_type")
        quality_gate_counts = group_counts(connection, "training_candidate_records", "quality_gate")
        privacy_class_counts = group_counts(connection, "training_candidate_records", "privacy_class")
        split_counts = group_counts(connection, "training_candidate_records", "split_name")
        record_jsons = load_candidate_record_jsons(connection)
    finally:
        connection.close()

    label_review_state_counts = Counter(
        str(as_dict(record.get("labels")).get("label_review_state") or "unknown")
        for record in record_jsons
    )
    review_queue_items = bounded_review_queue_items(record_jsons, limit=None)
    review_scope_records = [
        record
        for record in record_jsons
        if str(record.get("state") or "unknown") not in {"review_rejected"}
    ]
    review_required_records = sum(1 for record in record_jsons if record.get("review_required") is True)
    label_review_pending_records = int(label_review_state_counts.get("pending", 0)) + int(
        label_review_state_counts.get("needs_revision", 0)
    )
    split_leakage_unchecked_records = sum(
        1 for record in review_scope_records if as_dict(record.get("split")).get("split_leakage_checked") is not True
    )
    privacy_or_consent_blocked_records = sum(
        state_counts.get(state, 0) for state in ("consent_blocked", "privacy_blocked")
    )
    quality_blocked_records = int(state_counts.get("quality_blocked", 0))
    reviewed_training_candidate_records = int(state_counts.get("reviewed_training_candidate", 0))
    experiment_input_records = int(state_counts.get("experiment_input", 0))
    release_candidate_records = int(state_counts.get("release_candidate", 0))
    needs_review_records = max(
        review_required_records,
        label_review_pending_records,
        split_leakage_unchecked_records,
        len(review_queue_items),
    )

    blockers: list[str] = []
    warnings: list[str] = []
    if records_total == 0:
        warnings.append("no_candidate_records")
    if privacy_or_consent_blocked_records:
        blockers.append("consent_or_privacy_review_pending")
    if quality_blocked_records:
        blockers.append("quality_review_pending")
    if split_leakage_unchecked_records:
        blockers.append("split_leakage_review_pending")
    if label_review_pending_records:
        blockers.append("label_review_pending")
    if training_allowed_records and reviewed_training_candidate_records == 0:
        blockers.append("training_allowed_without_reviewed_candidate")

    model_training_ready = bool(training_allowed_records and reviewed_training_candidate_records)
    if records_total == 0:
        status = "needs_labels"
        pipeline_stage = "candidate_store_empty"
    elif blockers:
        status = "needs_review"
        pipeline_stage = "candidate_review_pending"
    elif model_training_ready:
        status = "ready_for_experiment"
        pipeline_stage = "dataset_manifest_next"
    else:
        status = "needs_review"
        pipeline_stage = "candidate_review_pending"
        blockers.append("reviewed_training_candidate_missing")

    reason = readiness_reason(
        records_total=records_total,
        reviewed_training_candidate_records=reviewed_training_candidate_records,
    )
    return {
        "schema_version": DATA_FLYWHEEL_STATUS_SCHEMA_VERSION,
        "builder_version": DATA_FLYWHEEL_STATUS_BUILDER_VERSION,
        "generated_at": generated,
        "status": status,
        "pipeline_stage": pipeline_stage,
        "candidate_store": {
            "available": True,
            "db_path": str(db_path),
            "schema_version": STORE_SCHEMA_VERSION,
            "latest_updated_at": latest_updated_at,
        },
        "counts": {
            "sessions_total": sessions_total,
            "records_total": records_total,
            "training_allowed_records": training_allowed_records,
            "review_required_records": review_required_records,
            "needs_review_records": needs_review_records,
            "reviewed_training_candidate_records": reviewed_training_candidate_records,
            "experiment_input_records": experiment_input_records,
            "release_candidate_records": release_candidate_records,
        },
        "state_counts": dict(sorted(state_counts.items())),
        "candidate_type_counts": dict(sorted(candidate_type_counts.items())),
        "quality_gate_counts": dict(sorted(quality_gate_counts.items())),
        "privacy_class_counts": dict(sorted(privacy_class_counts.items())),
        "label_review_state_counts": dict(sorted(label_review_state_counts.items())),
        "split_counts": dict(sorted(split_counts.items())),
        "review": {
            "label_review_pending_records": label_review_pending_records,
            "split_leakage_unchecked_records": split_leakage_unchecked_records,
            "privacy_or_consent_blocked_records": privacy_or_consent_blocked_records,
            "quality_blocked_records": quality_blocked_records,
        },
        "review_queue": {
            "schema_version": REVIEW_QUEUE_SCHEMA_VERSION,
            "available": True,
            "pending_records": len(review_queue_items),
            "sample_records": review_queue_items[:5],
            "available_actions": list(REVIEW_ACTIONS),
        },
        "readiness": {
            "model_training_ready": model_training_ready,
            "reason": reason,
            "dataset_manifest_ready": model_training_ready,
            "training_server_ready": False,
            "on_device_deployment_ready": False,
        },
        "warnings": sorted(set(warnings)),
        "blockers": sorted(set(blockers)),
        "next_step": next_data_flywheel_step(status, blockers),
        "non_claims": [
            "No model training has run.",
            "No on-device model has been deployed.",
            "No model accuracy, false-positive rate, or battery impact is claimed.",
        ],
    }


def render_data_flywheel_status_markdown(summary: Mapping[str, Any]) -> str:
    counts = as_dict(summary.get("counts"))
    review = as_dict(summary.get("review"))
    review_queue = as_dict(summary.get("review_queue"))
    readiness = as_dict(summary.get("readiness"))
    candidate_store = as_dict(summary.get("candidate_store"))
    lines = [
        "# Ego Link Data Flywheel Status",
        "",
        f"- Generated at: {summary.get('generated_at', 'unknown')}",
        f"- Status: {summary.get('status', 'unknown')}",
        f"- Pipeline stage: {summary.get('pipeline_stage', 'unknown')}",
        f"- Candidate store available: {candidate_store.get('available', False)}",
        f"- Sessions: {counts.get('sessions_total', 0)}",
        f"- Candidate records: {counts.get('records_total', 0)}",
        f"- Needs review: {counts.get('needs_review_records', 0)}",
        f"- Training allowed records: {counts.get('training_allowed_records', 0)}",
        f"- Reviewed training candidates: {counts.get('reviewed_training_candidate_records', 0)}",
        f"- Model training ready: {readiness.get('model_training_ready', False)} ({readiness.get('reason', 'unknown')})",
        "",
        "## Review Queues",
        "",
        f"- Label review pending: {review.get('label_review_pending_records', 0)}",
        f"- Split leakage unchecked: {review.get('split_leakage_unchecked_records', 0)}",
        f"- Consent/privacy blocked: {review.get('privacy_or_consent_blocked_records', 0)}",
        f"- Quality blocked: {review.get('quality_blocked_records', 0)}",
        f"- Bounded review queue: {review_queue.get('pending_records', 0)}",
        "",
        "## Counts",
        "",
        f"- States: {json.dumps(summary.get('state_counts', {}), ensure_ascii=False, sort_keys=True)}",
        f"- Candidate types: {json.dumps(summary.get('candidate_type_counts', {}), ensure_ascii=False, sort_keys=True)}",
        f"- Quality gates: {json.dumps(summary.get('quality_gate_counts', {}), ensure_ascii=False, sort_keys=True)}",
        "",
        "## Next Step",
        "",
        str(summary.get("next_step") or "Create the next data flywheel task."),
        "",
        "## Review Queue Samples",
        "",
    ]
    for item in review_queue.get("sample_records", []) or []:
        lines.append(
            f"- {item.get('record_id', 'unknown')}: {item.get('state', 'unknown')} / "
            f"{item.get('label', 'unknown')} / split {item.get('split_name', 'unknown')} / "
            f"label_review {item.get('label_review_state', 'unknown')}"
        )
    if not review_queue.get("sample_records"):
        lines.append("- none")
    lines += [
        "",
        "## Non-Claims",
        "",
    ]
    for item in summary.get("non_claims", []) or []:
        lines.append(f"- {item}")
    lines += [
        "",
        "This report contains only bounded counts and review status. It does not contain raw candidate records, raw payload bytes, private coordinates, candidate DB files, or runtime JSONL logs.",
        "",
    ]
    return "\n".join(lines)


def write_data_flywheel_status_report(summary: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = dict(summary)
    json_path = output_dir / "data_flywheel_status.json"
    markdown_path = output_dir / "data_flywheel_status.md"
    payload["paths"] = {
        "data_flywheel_status_json": str(json_path),
        "data_flywheel_status_markdown": str(markdown_path),
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_data_flywheel_status_markdown(payload), encoding="utf-8")
    return payload


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

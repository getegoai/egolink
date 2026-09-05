"""Host reference semantics for the OUTBOX-010 persistent priority outbox.

This module deliberately uses two mirrored JSON files and atomic replacement
so crash/reopen behavior can be tested without hardware.  It is not an ESP32
NVS implementation and makes no flash-endurance or brownout-durability claim.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import threading
from typing import Any, Mapping


STORAGE_CONTRACT_VERSION = "egolink.persistent_priority_outbox.storage.v0.1"
RECORD_CONTRACT_VERSION = "egolink.persistent_priority_outbox.record.v0.1"
ACK_CONTRACT_VERSION = "egolink.persistent_priority_outbox.ack.v0.1"
SNAPSHOT_CONTRACT_VERSION = "egolink.persistent_priority_outbox.snapshot.v0.1"
PRIMARY_FILE_NAME = "persistent_priority_outbox.primary.json"
MIRROR_FILE_NAME = "persistent_priority_outbox.mirror.json"

PRIORITIES = ("info", "normal", "warning", "high", "critical")
_PRIORITY_RANK = {priority: rank for rank, priority in enumerate(PRIORITIES)}
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$")
_SAFE_ERROR = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

_PRIVATE_COORDINATE_KEYS = {
    "coordinate",
    "coordinates",
    "geojson",
    "gps_coordinate",
    "lat",
    "latitude",
    "latitude_deg",
    "lon",
    "long",
    "longitude",
    "longitude_deg",
    "raw_location",
}
_MEDIA_KEYS = {
    "audio",
    "audio_bytes",
    "audio_data",
    "blob",
    "data_uri",
    "image",
    "image_bytes",
    "jpeg",
    "media",
    "media_bytes",
    "opus",
    "pcm",
    "raw_audio",
    "recording",
    "video",
}


class OutboxError(RuntimeError):
    """Base class for explicit outbox failures."""


class OutboxValidationError(OutboxError):
    """Raised when an operation would create an invalid record."""


class OutboxPrivacyError(OutboxValidationError):
    """Raised when a payload contains precise coordinates or media."""


class OutboxIdentityConflictError(OutboxValidationError):
    """Raised when an event ID is reused with different immutable identity."""


class OutboxFullError(OutboxError):
    """Raised after a capacity rejection has been durably recorded."""


class OutboxOverflowError(OutboxFullError):
    """Raised after a payload-size rejection has been durably recorded."""


class OutboxCorruptionError(OutboxError):
    """Raised when neither persisted mirror can be trusted."""


class OutboxConfigurationError(OutboxError):
    """Raised when a persisted queue is opened with another configuration."""


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise OutboxValidationError(f"value is not finite canonical JSON: {exc}") from exc


def _sha256_hex(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _require_int(name: str, value: Any, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise OutboxValidationError(f"{name} must be an integer >= {minimum}")
    return value


def _require_id(name: str, value: Any) -> str:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise OutboxValidationError(f"{name} must be a nonempty safe identifier")
    return value


def _validate_payload_privacy(value: Any, path: str = "payload") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str) or not key:
                raise OutboxValidationError(f"{path} keys must be nonempty strings")
            normalized = key.casefold()
            if normalized in _PRIVATE_COORDINATE_KEYS:
                raise OutboxPrivacyError(
                    f"{path}.{key} is a precise-coordinate field and cannot be cached"
                )
            if normalized in _MEDIA_KEYS:
                raise OutboxPrivacyError(
                    f"{path}.{key} is a media field and cannot be cached"
                )
            _validate_payload_privacy(child, f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _validate_payload_privacy(child, f"{path}[{index}]")
        return
    if isinstance(value, (bytes, bytearray, memoryview)):
        raise OutboxPrivacyError(f"{path} contains binary media/blob data")
    if isinstance(value, str) and value.casefold().startswith(
        ("data:audio/", "data:image/", "data:video/")
    ):
        raise OutboxPrivacyError(f"{path} contains an embedded media data URI")
    if value is not None and not isinstance(value, (str, int, float, bool)):
        raise OutboxValidationError(f"{path} contains unsupported JSON value")
    if isinstance(value, float) and not math.isfinite(value):
        raise OutboxValidationError(f"{path} contains a non-finite number")


class PersistentPriorityOutbox:
    """Single-process, file-backed reference implementation.

    All time arguments are explicit integer milliseconds so retry and replay
    behavior remains deterministic.  Cross-process locking is intentionally
    outside this host reference slice.
    """

    def __init__(
        self,
        storage_dir: str | Path,
        *,
        device_id: str,
        max_records: int = 32,
        reserved_critical_records: int = 4,
        max_total_payload_bytes: int = 64 * 1024,
        max_payload_bytes: int = 4 * 1024,
        base_retry_ms: int = 1_000,
        max_retry_ms: int = 60_000,
        tombstone_capacity: int = 64,
    ) -> None:
        self._lock = threading.RLock()
        self.storage_dir = Path(storage_dir)
        self.primary_path = self.storage_dir / PRIMARY_FILE_NAME
        self.mirror_path = self.storage_dir / MIRROR_FILE_NAME
        self.device_id = _require_id("device_id", device_id)

        max_records = _require_int("max_records", max_records, minimum=1)
        reserved_critical_records = _require_int(
            "reserved_critical_records", reserved_critical_records
        )
        max_total_payload_bytes = _require_int(
            "max_total_payload_bytes", max_total_payload_bytes, minimum=1
        )
        max_payload_bytes = _require_int(
            "max_payload_bytes", max_payload_bytes, minimum=1
        )
        base_retry_ms = _require_int("base_retry_ms", base_retry_ms, minimum=1)
        max_retry_ms = _require_int("max_retry_ms", max_retry_ms, minimum=1)
        tombstone_capacity = _require_int(
            "tombstone_capacity", tombstone_capacity, minimum=1
        )
        if reserved_critical_records > max_records:
            raise OutboxConfigurationError(
                "reserved_critical_records cannot exceed max_records"
            )
        if max_payload_bytes > max_total_payload_bytes:
            raise OutboxConfigurationError(
                "max_payload_bytes cannot exceed max_total_payload_bytes"
            )
        if base_retry_ms > max_retry_ms:
            raise OutboxConfigurationError(
                "base_retry_ms cannot exceed max_retry_ms"
            )

        config_body = {
            "max_records": max_records,
            "reserved_critical_records": reserved_critical_records,
            "max_total_payload_bytes": max_total_payload_bytes,
            "max_payload_bytes": max_payload_bytes,
            "reserved_critical_payload_bytes": min(
                max_total_payload_bytes,
                reserved_critical_records * max_payload_bytes,
            ),
            "base_retry_ms": base_retry_ms,
            "max_retry_ms": max_retry_ms,
            "tombstone_capacity": tombstone_capacity,
        }
        self._configuration = {
            **config_body,
            "configuration_sha256": _sha256_hex(config_body),
        }
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._state = self._load_or_initialize()

    @property
    def configuration_sha256(self) -> str:
        return self._configuration["configuration_sha256"]

    def enqueue(
        self,
        *,
        event_id: str,
        event_type: str,
        priority: str,
        payload: Mapping[str, Any],
        source_event_time_ms: int,
        boot_count: int,
        session_id: str,
        source_sequence: int,
        now_ms: int,
    ) -> dict[str, Any]:
        """Persist an immutable record before it can be selected for send."""

        with self._lock:
            event_id = _require_id("event_id", event_id)
            event_type = _require_id("event_type", event_type)
            session_id = _require_id("session_id", session_id)
            if priority not in PRIORITIES:
                raise OutboxValidationError(f"unsupported priority: {priority!r}")
            if event_type in {"manual_sos", "sos"} and priority != "critical":
                raise OutboxValidationError("SOS events must use critical priority")
            source_event_time_ms = _require_int(
                "source_event_time_ms", source_event_time_ms
            )
            boot_count = _require_int("boot_count", boot_count)
            source_sequence = _require_int("source_sequence", source_sequence)
            now_ms = _require_int("now_ms", now_ms)
            if not isinstance(payload, Mapping):
                raise OutboxValidationError("payload must be a JSON object")
            payload_copy = copy.deepcopy(dict(payload))
            _validate_payload_privacy(payload_copy)
            payload_bytes = _canonical_json_bytes(payload_copy)
            payload_size_bytes = len(payload_bytes)
            payload_sha256 = hashlib.sha256(payload_bytes).hexdigest()
            identity_body = {
                "device_id": self.device_id,
                "event_id": event_id,
                "event_type": event_type,
                "priority": priority,
                "payload_sha256": payload_sha256,
                "source_event_time_ms": source_event_time_ms,
                "boot_count": boot_count,
                "session_id": session_id,
                "source_sequence": source_sequence,
            }
            identity_sha256 = _sha256_hex(identity_body)

            existing = self._find_record(event_id)
            if existing is not None:
                if existing["identity_sha256"] != identity_sha256:
                    raise OutboxIdentityConflictError(
                        "event_id is already bound to another immutable identity"
                    )
                candidate = copy.deepcopy(self._state)
                candidate["metrics"]["duplicate_enqueue_count"] += 1
                self._commit(candidate)
                return copy.deepcopy(existing)

            if self._find_tombstone(event_id) is not None:
                raise OutboxIdentityConflictError(
                    "event_id was already positively acknowledged and tombstoned"
                )

            if payload_size_bytes > self._configuration["max_payload_bytes"]:
                self._record_capacity_rejection(
                    event_id=event_id,
                    priority=priority,
                    now_ms=now_ms,
                    reason="payload_exceeds_record_limit",
                    payload_overflow=True,
                )
                raise OutboxOverflowError(
                    "payload exceeds configured per-record capacity"
                )

            records = self._state["records"]
            total_payload_bytes = sum(
                record["payload_size_bytes"] for record in records
            )
            noncritical_payload_bytes = sum(
                record["payload_size_bytes"]
                for record in records
                if record["priority"] != "critical"
            )
            noncritical_payload_limit = (
                self._configuration["max_total_payload_bytes"]
                - self._configuration["reserved_critical_payload_bytes"]
            )
            if (
                priority != "critical"
                and noncritical_payload_bytes + payload_size_bytes
                > noncritical_payload_limit
            ):
                self._record_capacity_rejection(
                    event_id=event_id,
                    priority=priority,
                    now_ms=now_ms,
                    reason="critical_payload_reserve_protected",
                    payload_overflow=True,
                )
                raise OutboxOverflowError(
                    "critical payload-byte reserve is protected"
                )
            if (
                total_payload_bytes + payload_size_bytes
                > self._configuration["max_total_payload_bytes"]
            ):
                self._record_capacity_rejection(
                    event_id=event_id,
                    priority=priority,
                    now_ms=now_ms,
                    reason="total_payload_capacity_exhausted",
                    payload_overflow=True,
                )
                raise OutboxOverflowError("total payload capacity is exhausted")

            noncritical_count = sum(
                record["priority"] != "critical" for record in records
            )
            noncritical_limit = (
                self._configuration["max_records"]
                - self._configuration["reserved_critical_records"]
            )
            if priority != "critical" and noncritical_count >= noncritical_limit:
                self._record_capacity_rejection(
                    event_id=event_id,
                    priority=priority,
                    now_ms=now_ms,
                    reason="critical_reserve_protected",
                )
                raise OutboxFullError("critical record reserve is protected")
            if len(records) >= self._configuration["max_records"]:
                reason = (
                    "critical_capacity_exhausted"
                    if priority == "critical"
                    else "record_capacity_exhausted"
                )
                self._record_capacity_rejection(
                    event_id=event_id,
                    priority=priority,
                    now_ms=now_ms,
                    reason=reason,
                )
                raise OutboxFullError("outbox record capacity is exhausted")

            record = {
                "contract_version": RECORD_CONTRACT_VERSION,
                "device_id": self.device_id,
                "event_id": event_id,
                "event_type": event_type,
                "priority": priority,
                "source_event_time_ms": source_event_time_ms,
                "boot_count": boot_count,
                "session_id": session_id,
                "source_sequence": source_sequence,
                "payload": payload_copy,
                "payload_sha256": payload_sha256,
                "payload_size_bytes": payload_size_bytes,
                "identity_sha256": identity_sha256,
                "enqueue_time_ms": now_ms,
                "attempt_count": 0,
                "last_attempt_time_ms": None,
                "next_retry_time_ms": now_ms,
                "last_attempt_token": None,
                "last_attempt_result": "not_attempted",
                "last_attempt_result_time_ms": None,
                "last_error_code": None,
                "send_state": "queued",
            }
            candidate = copy.deepcopy(self._state)
            candidate["records"].append(record)
            candidate["metrics"]["enqueue_count"] += 1
            candidate["metrics"]["last_drop_reason"] = None
            candidate["last_failure"] = None
            self._commit(candidate)
            return copy.deepcopy(record)

    def begin_send_attempt(self, *, now_ms: int) -> dict[str, Any] | None:
        """Persist attempt metadata, then return one due record to the caller."""

        with self._lock:
            now_ms = _require_int("now_ms", now_ms)
            due = [
                record
                for record in self._state["records"]
                if record["next_retry_time_ms"] <= now_ms
            ]
            if not due:
                return None
            selected = min(
                due,
                key=lambda record: (
                    -_PRIORITY_RANK[record["priority"]],
                    record["source_event_time_ms"],
                    record["enqueue_time_ms"],
                    record["event_id"],
                ),
            )
            candidate = copy.deepcopy(self._state)
            record = self._find_record_in(candidate, selected["event_id"])
            assert record is not None
            record["attempt_count"] += 1
            delay_ms = self._retry_delay_ms(record["attempt_count"])
            record["last_attempt_time_ms"] = now_ms
            record["next_retry_time_ms"] = now_ms + delay_ms
            record["last_attempt_token"] = self._attempt_token(record)
            record["last_attempt_result"] = "pending"
            record["last_attempt_result_time_ms"] = None
            record["last_error_code"] = None
            record["send_state"] = "attempt_started"
            candidate["metrics"]["send_attempt_count"] += 1
            self._commit(candidate)
            return copy.deepcopy(record)

    def record_transport_result(
        self,
        *,
        attempt_token: str,
        accepted_by_transport: bool,
        now_ms: int,
        error_code: str | None = None,
    ) -> str:
        """Record transport outcome without equating it to delivery."""

        with self._lock:
            attempt_token = _require_id("attempt_token", attempt_token)
            now_ms = _require_int("now_ms", now_ms)
            if error_code is not None and (
                not isinstance(error_code, str) or not _SAFE_ERROR.fullmatch(error_code)
            ):
                raise OutboxValidationError(
                    "error_code must be uppercase snake case when present"
                )
            if accepted_by_transport and error_code is not None:
                raise OutboxValidationError(
                    "accepted transport result cannot include error_code"
                )
            if not accepted_by_transport and error_code is None:
                raise OutboxValidationError(
                    "failed transport result requires an explicit error_code"
                )
            matching = next(
                (
                    record
                    for record in self._state["records"]
                    if record["last_attempt_token"] == attempt_token
                ),
                None,
            )
            if matching is None:
                raise OutboxValidationError("attempt_token is stale or unknown")
            desired = "transport_accepted" if accepted_by_transport else "failed"
            if matching["last_attempt_result"] == desired:
                return "duplicate"
            if matching["last_attempt_result"] != "pending":
                raise OutboxValidationError(
                    "attempt result already closed with a different outcome"
                )
            candidate = copy.deepcopy(self._state)
            record = next(
                item
                for item in candidate["records"]
                if item["last_attempt_token"] == attempt_token
            )
            record["last_attempt_result"] = desired
            record["last_attempt_result_time_ms"] = now_ms
            record["last_error_code"] = error_code
            if accepted_by_transport:
                record["send_state"] = "awaiting_positive_ack"
                candidate["metrics"]["transport_accept_count"] += 1
            else:
                record["send_state"] = "retry_wait"
                candidate["metrics"]["send_failure_count"] += 1
                candidate["last_failure"] = {
                    "reason": error_code,
                    "event_id": record["event_id"],
                    "priority": record["priority"],
                    "at_ms": now_ms,
                }
            self._commit(candidate)
            return "recorded"

    def handle_ack(self, ack: Mapping[str, Any]) -> str:
        """Delete only on a positive ACK matching device/event/payload identity."""

        with self._lock:
            normalized = self._validate_ack(ack)
            event_id = normalized["event_id"]
            record = self._find_record(event_id)
            tombstone = self._find_tombstone(event_id)

            if normalized["status"] != "accepted":
                self._record_ack_rejection(
                    normalized, "negative_ack", record=record
                )
                return "negative_ack"

            if record is not None:
                identity_matches = (
                    normalized["device_id"] == record["device_id"]
                    and normalized["payload_sha256"] == record["payload_sha256"]
                )
                if not identity_matches:
                    self._record_ack_rejection(
                        normalized, "identity_mismatch", record=record
                    )
                    return "identity_mismatch"

                candidate = copy.deepcopy(self._state)
                candidate["records"] = [
                    item for item in candidate["records"] if item["event_id"] != event_id
                ]
                candidate["ack_tombstones"].append(
                    {
                        "ack_id": normalized["ack_id"],
                        "device_id": normalized["device_id"],
                        "event_id": event_id,
                        "payload_sha256": normalized["payload_sha256"],
                        "acked_at_ms": normalized["ack_time_ms"],
                    }
                )
                capacity = self._configuration["tombstone_capacity"]
                if len(candidate["ack_tombstones"]) > capacity:
                    prune_count = len(candidate["ack_tombstones"]) - capacity
                    candidate["ack_tombstones"] = candidate["ack_tombstones"][
                        prune_count:
                    ]
                    candidate["metrics"]["tombstone_pruned_count"] += prune_count
                candidate["metrics"]["ack_delete_count"] += 1
                candidate["last_failure"] = None
                self._commit(candidate)
                return "deleted_after_positive_ack"

            if tombstone is not None:
                identity_matches = (
                    normalized["device_id"] == tombstone["device_id"]
                    and normalized["payload_sha256"] == tombstone["payload_sha256"]
                )
                if identity_matches:
                    candidate = copy.deepcopy(self._state)
                    candidate["metrics"]["duplicate_ack_count"] += 1
                    self._commit(candidate)
                    return "duplicate_positive_ack"

            self._record_ack_rejection(normalized, "stale_or_unknown", record=None)
            return "stale_or_unknown"

    def snapshot(self, *, now_ms: int) -> dict[str, Any]:
        """Return privacy-minimized queue and failure observability."""

        with self._lock:
            now_ms = _require_int("now_ms", now_ms)
            records = sorted(
                self._state["records"],
                key=lambda record: (
                    -_PRIORITY_RANK[record["priority"]],
                    record["source_event_time_ms"],
                    record["event_id"],
                ),
            )
            counts = {
                priority: sum(record["priority"] == priority for record in records)
                for priority in PRIORITIES
            }
            payload_bytes = sum(record["payload_size_bytes"] for record in records)
            oldest_age_ms = (
                max(0, now_ms - min(record["enqueue_time_ms"] for record in records))
                if records
                else None
            )
            next_retry_time_ms = (
                min(record["next_retry_time_ms"] for record in records)
                if records
                else None
            )
            noncritical_limit = (
                self._configuration["max_records"]
                - self._configuration["reserved_critical_records"]
            )
            if len(records) >= self._configuration["max_records"]:
                capacity_state = "full"
            elif sum(counts[p] for p in PRIORITIES if p != "critical") >= noncritical_limit:
                capacity_state = "critical_reserve_only"
            else:
                capacity_state = "available"
            return {
                "contract_version": SNAPSHOT_CONTRACT_VERSION,
                "storage_backend": "host_atomic_json_mirror_reference",
                "durability_claim": "host_reference_only_not_product_nvs",
                "device_id": self.device_id,
                "configuration_sha256": self.configuration_sha256,
                "generation": self._state["generation"],
                "capacity_state": capacity_state,
                "queued_count": len(records),
                "queued_by_priority": counts,
                "max_records": self._configuration["max_records"],
                "reserved_critical_records": self._configuration[
                    "reserved_critical_records"
                ],
                "reserved_critical_payload_bytes": self._configuration[
                    "reserved_critical_payload_bytes"
                ],
                "payload_bytes": payload_bytes,
                "max_total_payload_bytes": self._configuration[
                    "max_total_payload_bytes"
                ],
                "oldest_age_ms": oldest_age_ms,
                "next_retry_time_ms": next_retry_time_ms,
                "awaiting_positive_ack_count": sum(
                    record["send_state"] == "awaiting_positive_ack"
                    for record in records
                ),
                "ack_tombstone_count": len(self._state["ack_tombstones"]),
                "metrics": copy.deepcopy(self._state["metrics"]),
                "last_failure": copy.deepcopy(self._state["last_failure"]),
                "records": [self._record_observability(record) for record in records],
            }

    def export_storage_document(self) -> dict[str, Any]:
        """Return a copy for schema tests and offline inspection."""

        with self._lock:
            return copy.deepcopy(self._state)

    def _record_capacity_rejection(
        self,
        *,
        event_id: str,
        priority: str,
        now_ms: int,
        reason: str,
        payload_overflow: bool = False,
    ) -> None:
        candidate = copy.deepcopy(self._state)
        metrics = candidate["metrics"]
        metrics["rejected_enqueue_count"] += 1
        metrics["full_count"] += 1
        if payload_overflow:
            metrics["payload_overflow_count"] += 1
        if priority == "critical" or reason in {
            "critical_reserve_protected",
            "critical_payload_reserve_protected",
        }:
            metrics["priority_overflow_count"] += 1
        metrics["last_drop_reason"] = reason
        candidate["last_failure"] = {
            "reason": reason,
            "event_id": event_id,
            "priority": priority,
            "at_ms": now_ms,
        }
        self._commit(candidate)

    def _record_ack_rejection(
        self,
        ack: Mapping[str, Any],
        reason: str,
        *,
        record: Mapping[str, Any] | None,
    ) -> None:
        candidate = copy.deepcopy(self._state)
        candidate["metrics"]["ack_mismatch_count"] += 1
        candidate["last_failure"] = {
            "reason": reason,
            "event_id": ack["event_id"],
            "priority": record["priority"] if record is not None else "unknown",
            "at_ms": ack["ack_time_ms"],
        }
        self._commit(candidate)

    def _validate_ack(self, ack: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(ack, Mapping):
            raise OutboxValidationError("ack must be an object")
        expected = {
            "contract_version",
            "ack_id",
            "device_id",
            "event_id",
            "payload_sha256",
            "status",
            "ack_time_ms",
        }
        if set(ack) != expected:
            raise OutboxValidationError("ack fields must match the bounded ACK contract")
        if ack["contract_version"] != ACK_CONTRACT_VERSION:
            raise OutboxValidationError("unsupported ACK contract version")
        normalized = {
            "contract_version": ACK_CONTRACT_VERSION,
            "ack_id": _require_id("ack_id", ack["ack_id"]),
            "device_id": _require_id("device_id", ack["device_id"]),
            "event_id": _require_id("event_id", ack["event_id"]),
            "payload_sha256": ack["payload_sha256"],
            "status": ack["status"],
            "ack_time_ms": _require_int("ack_time_ms", ack["ack_time_ms"]),
        }
        if not isinstance(normalized["payload_sha256"], str) or not _SHA256.fullmatch(
            normalized["payload_sha256"]
        ):
            raise OutboxValidationError("payload_sha256 must be lowercase SHA-256")
        if normalized["status"] not in {"accepted", "rejected"}:
            raise OutboxValidationError("ACK status must be accepted or rejected")
        return normalized

    def _attempt_token(self, record: Mapping[str, Any]) -> str:
        body = {
            "device_id": record["device_id"],
            "event_id": record["event_id"],
            "payload_sha256": record["payload_sha256"],
            "attempt_count": record["attempt_count"],
        }
        return f"attempt:{_sha256_hex(body)[:32]}"

    def _retry_delay_ms(self, attempt_count: int) -> int:
        delay = self._configuration["base_retry_ms"]
        remaining_doublings = max(0, attempt_count - 1)
        maximum = self._configuration["max_retry_ms"]
        while remaining_doublings and delay < maximum:
            delay = min(delay * 2, maximum)
            remaining_doublings -= 1
        return delay

    @staticmethod
    def _record_observability(record: Mapping[str, Any]) -> dict[str, Any]:
        return {
            key: copy.deepcopy(record[key])
            for key in (
                "device_id",
                "event_id",
                "event_type",
                "priority",
                "source_event_time_ms",
                "boot_count",
                "session_id",
                "source_sequence",
                "payload_sha256",
                "payload_size_bytes",
                "identity_sha256",
                "enqueue_time_ms",
                "attempt_count",
                "last_attempt_time_ms",
                "next_retry_time_ms",
                "last_attempt_token",
                "last_attempt_result",
                "last_attempt_result_time_ms",
                "last_error_code",
                "send_state",
            )
        }

    def _find_record(self, event_id: str) -> dict[str, Any] | None:
        return self._find_record_in(self._state, event_id)

    @staticmethod
    def _find_record_in(
        state: Mapping[str, Any], event_id: str
    ) -> dict[str, Any] | None:
        return next(
            (record for record in state["records"] if record["event_id"] == event_id),
            None,
        )

    def _find_tombstone(self, event_id: str) -> dict[str, Any] | None:
        return next(
            (
                tombstone
                for tombstone in self._state["ack_tombstones"]
                if tombstone["event_id"] == event_id
            ),
            None,
        )

    def _load_or_initialize(self) -> dict[str, Any]:
        primary, primary_error = self._load_slot(self.primary_path)
        mirror, mirror_error = self._load_slot(self.mirror_path)
        valid = [state for state in (primary, mirror) if state is not None]
        existing_count = sum(path.exists() for path in (self.primary_path, self.mirror_path))

        config_errors = [
            error
            for error in (primary_error, mirror_error)
            if isinstance(error, OutboxConfigurationError)
        ]
        if config_errors:
            raise config_errors[0]

        if not valid:
            if existing_count:
                reasons = "; ".join(
                    str(error)
                    for error in (primary_error, mirror_error)
                    if error is not None
                )
                raise OutboxCorruptionError(
                    f"no trustworthy outbox mirror remains: {reasons}"
                )
            state = self._new_state()
            return self._persist_state(state)

        if len(valid) == 2 and valid[0]["generation"] == valid[1]["generation"]:
            if valid[0]["storage_sha256"] != valid[1]["storage_sha256"]:
                raise OutboxCorruptionError(
                    "mirrors have the same generation but different content"
                )
            return valid[0]

        chosen = max(valid, key=lambda state: state["generation"])
        recovered = copy.deepcopy(chosen)
        metrics = recovered["metrics"]
        metrics["recovery_count"] += 1
        invalid_errors = [
            error
            for error in (primary_error, mirror_error)
            if error is not None
        ]
        if invalid_errors:
            metrics["corruption_detected_count"] += len(invalid_errors)
            metrics["last_corruption_reason"] = "; ".join(
                str(error) for error in invalid_errors
            )[:512]
            metrics["last_recovery_reason"] = "invalid_mirror_repaired"
        elif len(valid) == 1:
            metrics["last_recovery_reason"] = "missing_mirror_repaired"
        else:
            metrics["last_recovery_reason"] = "generation_divergence_repaired"
        return self._persist_state(recovered)

    def _new_state(self) -> dict[str, Any]:
        return {
            "contract_version": STORAGE_CONTRACT_VERSION,
            "generation": 0,
            "device_id": self.device_id,
            "configuration": copy.deepcopy(self._configuration),
            "records": [],
            "ack_tombstones": [],
            "metrics": {
                "enqueue_count": 0,
                "duplicate_enqueue_count": 0,
                "rejected_enqueue_count": 0,
                "send_attempt_count": 0,
                "send_failure_count": 0,
                "transport_accept_count": 0,
                "ack_delete_count": 0,
                "duplicate_ack_count": 0,
                "ack_mismatch_count": 0,
                "full_count": 0,
                "priority_overflow_count": 0,
                "payload_overflow_count": 0,
                "tombstone_pruned_count": 0,
                "corruption_detected_count": 0,
                "recovery_count": 0,
                "last_drop_reason": None,
                "last_corruption_reason": None,
                "last_recovery_reason": None,
            },
            "last_failure": None,
            "storage_sha256": "",
        }

    def _commit(self, candidate: dict[str, Any]) -> None:
        persisted = self._persist_state(candidate)
        self._state = persisted

    def _persist_state(self, state: dict[str, Any]) -> dict[str, Any]:
        candidate = copy.deepcopy(state)
        candidate["generation"] += 1
        candidate["storage_sha256"] = self._calculate_storage_hash(candidate)
        self._validate_state(candidate)
        encoded = _canonical_json_bytes(candidate) + b"\n"
        # Mirror first: if the process dies before primary replacement, reopen
        # selects the higher valid generation and repairs the stale slot.
        self._write_slot_atomic(self.mirror_path, encoded)
        self._write_slot_atomic(self.primary_path, encoded)
        return candidate

    def _load_slot(
        self, path: Path
    ) -> tuple[dict[str, Any] | None, Exception | None]:
        if not path.exists():
            return None, None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            self._validate_state(value)
            return value, None
        except Exception as exc:  # surfaced or repaired by _load_or_initialize
            return None, exc

    def _validate_state(self, state: Any) -> None:
        if not isinstance(state, dict):
            raise OutboxCorruptionError("persisted root is not an object")
        required = {
            "contract_version",
            "generation",
            "device_id",
            "configuration",
            "records",
            "ack_tombstones",
            "metrics",
            "last_failure",
            "storage_sha256",
        }
        if set(state) != required:
            raise OutboxCorruptionError("persisted root fields do not match contract")
        if state["contract_version"] != STORAGE_CONTRACT_VERSION:
            raise OutboxCorruptionError("unsupported storage contract version")
        _require_int("generation", state["generation"], minimum=1)
        if state["device_id"] != self.device_id:
            raise OutboxConfigurationError("persisted device_id does not match opener")
        if state["configuration"] != self._configuration:
            raise OutboxConfigurationError(
                "persisted outbox configuration does not match opener"
            )
        if not isinstance(state["records"], list) or not isinstance(
            state["ack_tombstones"], list
        ):
            raise OutboxCorruptionError("records/tombstones must be arrays")
        if len(state["records"]) > self._configuration["max_records"]:
            raise OutboxCorruptionError("persisted record capacity is exceeded")
        if len(state["ack_tombstones"]) > self._configuration["tombstone_capacity"]:
            raise OutboxCorruptionError("persisted tombstone capacity is exceeded")
        event_ids: set[str] = set()
        payload_total = 0
        for record in state["records"]:
            self._validate_record(record)
            if record["event_id"] in event_ids:
                raise OutboxCorruptionError("duplicate persisted event_id")
            event_ids.add(record["event_id"])
            payload_total += record["payload_size_bytes"]
        if payload_total > self._configuration["max_total_payload_bytes"]:
            raise OutboxCorruptionError("persisted payload capacity is exceeded")
        for tombstone in state["ack_tombstones"]:
            self._validate_tombstone(tombstone)
        if not isinstance(state["metrics"], dict):
            raise OutboxCorruptionError("metrics must be an object")
        integer_metrics = {
            "enqueue_count",
            "duplicate_enqueue_count",
            "rejected_enqueue_count",
            "send_attempt_count",
            "send_failure_count",
            "transport_accept_count",
            "ack_delete_count",
            "duplicate_ack_count",
            "ack_mismatch_count",
            "full_count",
            "priority_overflow_count",
            "payload_overflow_count",
            "tombstone_pruned_count",
            "corruption_detected_count",
            "recovery_count",
        }
        nullable_metrics = {
            "last_drop_reason",
            "last_corruption_reason",
            "last_recovery_reason",
        }
        if set(state["metrics"]) != integer_metrics | nullable_metrics:
            raise OutboxCorruptionError("metric fields do not match contract")
        for key in integer_metrics:
            _require_int(key, state["metrics"][key])
        for key in nullable_metrics:
            value = state["metrics"][key]
            if value is not None and (not isinstance(value, str) or not value):
                raise OutboxCorruptionError(f"{key} must be null or nonempty")
        if state["last_failure"] is not None:
            failure = state["last_failure"]
            if not isinstance(failure, dict) or set(failure) != {
                "reason",
                "event_id",
                "priority",
                "at_ms",
            }:
                raise OutboxCorruptionError("last_failure does not match contract")
            if not isinstance(failure["reason"], str) or not failure["reason"]:
                raise OutboxCorruptionError("last_failure reason is invalid")
            _require_id("last_failure.event_id", failure["event_id"])
            if failure["priority"] not in {*PRIORITIES, "unknown"}:
                raise OutboxCorruptionError("last_failure priority is invalid")
            _require_int("last_failure.at_ms", failure["at_ms"])
        if not isinstance(state["storage_sha256"], str) or not _SHA256.fullmatch(
            state["storage_sha256"]
        ):
            raise OutboxCorruptionError("storage_sha256 is invalid")
        if state["storage_sha256"] != self._calculate_storage_hash(state):
            raise OutboxCorruptionError("storage_sha256 mismatch")

    def _validate_record(self, record: Any) -> None:
        if not isinstance(record, dict):
            raise OutboxCorruptionError("persisted record is not an object")
        required = {
            "contract_version",
            "device_id",
            "event_id",
            "event_type",
            "priority",
            "source_event_time_ms",
            "boot_count",
            "session_id",
            "source_sequence",
            "payload",
            "payload_sha256",
            "payload_size_bytes",
            "identity_sha256",
            "enqueue_time_ms",
            "attempt_count",
            "last_attempt_time_ms",
            "next_retry_time_ms",
            "last_attempt_token",
            "last_attempt_result",
            "last_attempt_result_time_ms",
            "last_error_code",
            "send_state",
        }
        if set(record) != required:
            raise OutboxCorruptionError("persisted record fields do not match contract")
        if record["contract_version"] != RECORD_CONTRACT_VERSION:
            raise OutboxCorruptionError("unsupported record contract version")
        if record["device_id"] != self.device_id:
            raise OutboxCorruptionError("record device_id mismatch")
        for field in ("event_id", "event_type", "session_id"):
            _require_id(field, record[field])
        if record["priority"] not in PRIORITIES:
            raise OutboxCorruptionError("invalid persisted priority")
        for field in (
            "source_event_time_ms",
            "boot_count",
            "source_sequence",
            "payload_size_bytes",
            "enqueue_time_ms",
            "attempt_count",
            "next_retry_time_ms",
        ):
            _require_int(field, record[field])
        if not isinstance(record["payload"], dict):
            raise OutboxCorruptionError("persisted payload must be an object")
        _validate_payload_privacy(record["payload"])
        payload_bytes = _canonical_json_bytes(record["payload"])
        if len(payload_bytes) != record["payload_size_bytes"]:
            raise OutboxCorruptionError("persisted payload size mismatch")
        payload_hash = hashlib.sha256(payload_bytes).hexdigest()
        if payload_hash != record["payload_sha256"]:
            raise OutboxCorruptionError("persisted payload hash mismatch")
        identity = {
            "device_id": record["device_id"],
            "event_id": record["event_id"],
            "event_type": record["event_type"],
            "priority": record["priority"],
            "payload_sha256": record["payload_sha256"],
            "source_event_time_ms": record["source_event_time_ms"],
            "boot_count": record["boot_count"],
            "session_id": record["session_id"],
            "source_sequence": record["source_sequence"],
        }
        if record["identity_sha256"] != _sha256_hex(identity):
            raise OutboxCorruptionError("persisted immutable identity hash mismatch")
        for nullable_time in (
            "last_attempt_time_ms",
            "last_attempt_result_time_ms",
        ):
            if record[nullable_time] is not None:
                _require_int(nullable_time, record[nullable_time])
        if record["last_attempt_token"] is not None:
            _require_id("last_attempt_token", record["last_attempt_token"])
        if record["last_attempt_result"] not in {
            "not_attempted",
            "pending",
            "failed",
            "transport_accepted",
        }:
            raise OutboxCorruptionError("invalid attempt result")
        if record["last_error_code"] is not None and not _SAFE_ERROR.fullmatch(
            record["last_error_code"]
        ):
            raise OutboxCorruptionError("invalid persisted error code")
        if record["send_state"] not in {
            "queued",
            "attempt_started",
            "retry_wait",
            "awaiting_positive_ack",
        }:
            raise OutboxCorruptionError("invalid persisted send state")
        if record["attempt_count"] == 0:
            if any(
                record[field] is not None
                for field in (
                    "last_attempt_time_ms",
                    "last_attempt_token",
                    "last_attempt_result_time_ms",
                    "last_error_code",
                )
            ) or record["last_attempt_result"] != "not_attempted" or record[
                "send_state"
            ] != "queued":
                raise OutboxCorruptionError("zero-attempt record state is inconsistent")
        else:
            if record["last_attempt_time_ms"] is None or record[
                "last_attempt_token"
            ] is None:
                raise OutboxCorruptionError("attempt lineage is incomplete")
            attempt_semantics = {
                "pending": ("attempt_started", False, False),
                "failed": ("retry_wait", True, True),
                "transport_accepted": (
                    "awaiting_positive_ack",
                    True,
                    False,
                ),
            }
            expected = attempt_semantics.get(record["last_attempt_result"])
            if expected is None:
                raise OutboxCorruptionError("attempted record has no result state")
            expected_send_state, needs_result_time, needs_error = expected
            if record["send_state"] != expected_send_state:
                raise OutboxCorruptionError("attempt result/send state mismatch")
            if (record["last_attempt_result_time_ms"] is not None) != needs_result_time:
                raise OutboxCorruptionError("attempt result-time state mismatch")
            if (record["last_error_code"] is not None) != needs_error:
                raise OutboxCorruptionError("attempt error state mismatch")

    @staticmethod
    def _validate_tombstone(tombstone: Any) -> None:
        if not isinstance(tombstone, dict) or set(tombstone) != {
            "ack_id",
            "device_id",
            "event_id",
            "payload_sha256",
            "acked_at_ms",
        }:
            raise OutboxCorruptionError("ACK tombstone fields do not match contract")
        for field in ("ack_id", "device_id", "event_id"):
            _require_id(field, tombstone[field])
        if not isinstance(tombstone["payload_sha256"], str) or not _SHA256.fullmatch(
            tombstone["payload_sha256"]
        ):
            raise OutboxCorruptionError("invalid tombstone payload hash")
        _require_int("acked_at_ms", tombstone["acked_at_ms"])

    @staticmethod
    def _calculate_storage_hash(state: Mapping[str, Any]) -> str:
        body = {key: value for key, value in state.items() if key != "storage_sha256"}
        return _sha256_hex(body)

    @staticmethod
    def _write_slot_atomic(path: Path, encoded: bytes) -> None:
        temporary_path: Path | None = None
        try:
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
            )
            temporary_path = Path(temporary_name)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
            temporary_path = None
            PersistentPriorityOutbox._fsync_directory(path.parent)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    @staticmethod
    def _fsync_directory(directory: Path) -> None:
        if os.name == "nt":
            return
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def positive_ack_for(
    record: Mapping[str, Any], *, ack_id: str, ack_time_ms: int
) -> dict[str, Any]:
    """Build the bounded unauthenticated ACK fixture for a record.

    Authentication is intentionally left to OPS-004/server integration.
    """

    return {
        "contract_version": ACK_CONTRACT_VERSION,
        "ack_id": ack_id,
        "device_id": record["device_id"],
        "event_id": record["event_id"],
        "payload_sha256": record["payload_sha256"],
        "status": "accepted",
        "ack_time_ms": ack_time_ms,
    }


__all__ = [
    "ACK_CONTRACT_VERSION",
    "MIRROR_FILE_NAME",
    "PRIMARY_FILE_NAME",
    "PersistentPriorityOutbox",
    "OutboxConfigurationError",
    "OutboxCorruptionError",
    "OutboxError",
    "OutboxFullError",
    "OutboxIdentityConflictError",
    "OutboxOverflowError",
    "OutboxPrivacyError",
    "OutboxValidationError",
    "positive_ack_for",
]

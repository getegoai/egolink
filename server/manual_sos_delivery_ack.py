"""Positive outbox ACK for a durably accepted manual-SOS request.

The digest is over the exact request bytes, without JSON normalization.  This
ACK proves only authenticated server durable ingest; Guardian visibility,
human acknowledgement and Ego Call state are separate facts.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping

from server.manual_sos_store import (
    ManualSosValidationError,
    validate_manual_sos_payload,
)


ACK_CONTRACT_VERSION = "egolink.persistent_priority_outbox.ack.v0.1"
DELIVERY_SCOPE = "server_durable_ingest_only"
_ACCEPTED_INGEST_RESULTS = frozenset({"accepted", "duplicate"})
_OUTBOX_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SQLITE_SIGNED_INT64_MAX = (1 << 63) - 1


class ManualSosDeliveryAckError(ValueError):
    """Raised when a non-durable or mismatched result requests an ACK."""


def _safe_id(value: Any, name: str) -> str:
    if not isinstance(value, str) or _OUTBOX_SAFE_ID.fullmatch(value) is None:
        raise ManualSosDeliveryAckError(
            f"{name} must be a 1-128 character outbox-safe identifier"
        )
    return value


def _non_negative_sqlite_integer(value: Any, name: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value > _SQLITE_SIGNED_INT64_MAX
    ):
        raise ManualSosDeliveryAckError(
            f"{name} must fit a non-negative SQLite signed integer"
        )
    return value


def exact_payload_sha256(payload_bytes: bytes) -> str:
    if not isinstance(payload_bytes, bytes) or not payload_bytes:
        raise ManualSosDeliveryAckError(
            "payload_bytes must be nonempty exact bytes"
        )
    return hashlib.sha256(payload_bytes).hexdigest()


def build_manual_sos_delivery_ack(
    payload_bytes: bytes,
    ingest_result: Mapping[str, Any],
    *,
    ack_time_ms: int,
) -> dict[str, Any]:
    """Return a positive ACK only for an exact durable accept/duplicate."""

    if not isinstance(ingest_result, Mapping):
        raise ManualSosDeliveryAckError("ingest_result must be an object")
    if ingest_result.get("status") not in _ACCEPTED_INGEST_RESULTS:
        raise ManualSosDeliveryAckError(
            "ingest result is not durably accepted"
        )
    identity = ingest_result.get("identity")
    if not isinstance(identity, Mapping):
        raise ManualSosDeliveryAckError("ingest result identity is missing")
    device_id = _safe_id(identity.get("device_id"), "identity.device_id")
    event_id = _safe_id(identity.get("event_id"), "identity.event_id")
    try:
        payload = validate_manual_sos_payload(payload_bytes)
    except ManualSosValidationError as error:
        raise ManualSosDeliveryAckError(
            "payload_bytes are not an accepted manual SOS"
        ) from error
    if payload.device_id != device_id or payload.event_id != event_id:
        raise ManualSosDeliveryAckError(
            "ingest result identity does not match the exact request bytes"
        )
    digest = exact_payload_sha256(payload_bytes)
    stored_digest = ingest_result.get("payload_sha256")
    if (
        not isinstance(stored_digest, str)
        or _SHA256.fullmatch(stored_digest) is None
        or stored_digest != digest
    ):
        raise ManualSosDeliveryAckError(
            "ingest result does not bind the exact request bytes"
        )
    return {
        "contract_version": ACK_CONTRACT_VERSION,
        "ack_id": "ack-" + digest,
        "device_id": device_id,
        "event_id": event_id,
        "payload_sha256": digest,
        "status": "accepted",
        "ack_time_ms": _non_negative_sqlite_integer(
            ack_time_ms, "ack_time_ms"
        ),
    }


__all__ = [
    "ACK_CONTRACT_VERSION",
    "DELIVERY_SCOPE",
    "ManualSosDeliveryAckError",
    "build_manual_sos_delivery_ack",
    "exact_payload_sha256",
]

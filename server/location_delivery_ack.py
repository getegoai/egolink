"""Transport-neutral positive ACK construction for accepted location state.

The ACK binds the exact request bytes that a device-side durable outbox sends.
It intentionally says only that the authenticated server durably accepted the
state; it does not claim Guardian display, human acknowledgement, or freshness.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping


ACK_CONTRACT_VERSION = "egolink.persistent_priority_outbox.ack.v0.1"
LOCATION_EVENT_PREFIX = "loc-"
LOCATION_ACK_PREFIX = "ack-"
_ACCEPTED_INGEST_RESULTS = frozenset({"accepted", "duplicate"})
_OUTBOX_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$")


class LocationDeliveryAckError(ValueError):
    """Raised when an ingest result cannot safely produce a positive ACK."""


def _non_negative_integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise LocationDeliveryAckError(f"{name} must be a non-negative integer")
    return value


def _bounded_identifier(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 256:
        raise LocationDeliveryAckError(f"{name} must be a 1-256 character string")
    return value


def _outbox_safe_identifier(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _OUTBOX_SAFE_ID.fullmatch(value):
        raise LocationDeliveryAckError(
            f"{name} must be a 1-128 character outbox-safe identifier"
        )
    return value


def exact_payload_sha256(payload_bytes: bytes) -> str:
    """Hash the exact persisted/transmitted bytes, without JSON re-encoding."""

    if not isinstance(payload_bytes, bytes) or not payload_bytes:
        raise LocationDeliveryAckError("payload_bytes must be nonempty bytes")
    return hashlib.sha256(payload_bytes).hexdigest()


def location_outbox_event_id(payload_sha256: str) -> str:
    """Return the bounded event ID shared by device and server adapters."""

    if (
        not isinstance(payload_sha256, str)
        or len(payload_sha256) != 64
        or any(character not in "0123456789abcdef" for character in payload_sha256)
    ):
        raise LocationDeliveryAckError("payload_sha256 must be 64 lowercase hex characters")
    return LOCATION_EVENT_PREFIX + payload_sha256


def build_location_state_delivery_ack(
    payload_bytes: bytes,
    envelope: Mapping[str, Any],
    ingest_result: Mapping[str, Any],
    *,
    ack_time_ms: int,
) -> dict[str, Any]:
    """Build a positive ACK only after accepted or idempotent durable ingest."""

    if not isinstance(envelope, Mapping) or not isinstance(ingest_result, Mapping):
        raise LocationDeliveryAckError("envelope and ingest_result must be objects")
    status = ingest_result.get("status")
    if status not in _ACCEPTED_INGEST_RESULTS:
        raise LocationDeliveryAckError("ingest result is not durably accepted")
    identity = ingest_result.get("identity")
    if not isinstance(identity, Mapping):
        raise LocationDeliveryAckError("ingest result identity is missing")

    device_id = _outbox_safe_identifier(envelope.get("device_id"), "device_id")
    observation_id = _bounded_identifier(
        envelope.get("observation_id"), "observation_id"
    )
    if device_id != _outbox_safe_identifier(
        identity.get("device_id"), "result.identity.device_id"
    ):
        raise LocationDeliveryAckError("ingest result device identity mismatch")
    if observation_id != _bounded_identifier(
        identity.get("observation_id"), "result.identity.observation_id"
    ):
        raise LocationDeliveryAckError("ingest result observation identity mismatch")

    for field in ("boot_count", "event_time_ms", "sequence_id"):
        if _non_negative_integer(envelope.get(field), field) != _non_negative_integer(
            identity.get(field), f"result.identity.{field}"
        ):
            raise LocationDeliveryAckError(f"ingest result {field} mismatch")
    session_id = _outbox_safe_identifier(envelope.get("session_id"), "session_id")
    if session_id != _outbox_safe_identifier(
        identity.get("session_id"), "result.identity.session_id"
    ):
        raise LocationDeliveryAckError("ingest result session identity mismatch")

    digest = exact_payload_sha256(payload_bytes)
    event_id = location_outbox_event_id(digest)
    return {
        "contract_version": ACK_CONTRACT_VERSION,
        "ack_id": LOCATION_ACK_PREFIX + digest,
        "device_id": device_id,
        "event_id": event_id,
        "payload_sha256": digest,
        "status": "accepted",
        "ack_time_ms": _non_negative_integer(ack_time_ms, "ack_time_ms"),
    }


__all__ = [
    "ACK_CONTRACT_VERSION",
    "LocationDeliveryAckError",
    "build_location_state_delivery_ack",
    "exact_payload_sha256",
    "location_outbox_event_id",
]

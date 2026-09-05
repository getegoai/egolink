"""Deterministic, credential-free Ego Call state fixture.

This module validates call transition records against the shared contract and
provides append/replay behavior for CALL-001. It does not carry RTC media,
contact an external provider, or claim product audio/network acceptance.
"""

from __future__ import annotations

import json
import math
import uuid
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker, validators


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "shared" / "contracts" / "ego_call_session.schema.json"
EGO_CALL_FORMAT_CHECKER = FormatChecker()
EGO_CALL_TYPE_CHECKER = Draft202012Validator.TYPE_CHECKER.redefine(
    "number",
    lambda _checker, value: (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
    ),
)
EgoCallValidator = validators.extend(
    Draft202012Validator,
    type_checker=EGO_CALL_TYPE_CHECKER,
)


@EGO_CALL_FORMAT_CHECKER.checks("date-time")
def _valid_datetime(value: object) -> bool:
    if not isinstance(value, str):
        return True
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


class EgoCallError(ValueError):
    """Base error for a rejected fixture operation."""


class EgoCallAuthorizationError(EgoCallError):
    """Raised when a device/guardian binding is not authorized."""


class EgoCallTransitionError(EgoCallError):
    """Raised when state history or a requested transition is invalid."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _new_id() -> str:
    return uuid.uuid4().hex


def load_validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return EgoCallValidator(schema, format_checker=EGO_CALL_FORMAT_CHECKER)


def _clone(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _transport_state(state: str) -> tuple[str, str]:
    return {
        "requested": ("pending", "not_started"),
        "ringing": ("ready", "connecting"),
        "connected": ("ready", "ready"),
        "reconnecting": ("ready", "interrupted"),
        "ended": ("closed", "closed"),
        "failed": ("failed", "failed"),
    }[state]


class EgoCallFixture:
    """In-memory call-control fixture with schema-validated append/replay."""

    def __init__(
        self,
        *,
        authorized_bindings: Iterable[tuple[str, str]],
        clock: Callable[[], str] = _utc_now,
        id_factory: Callable[[], str] = _new_id,
    ) -> None:
        self._authorized_bindings = set(authorized_bindings)
        self._clock = clock
        self._id_factory = id_factory
        self._validator = load_validator()
        self._events: list[dict[str, Any]] = []
        self._local_sos_events: list[dict[str, Any]] = []
        self._local_sos_results: dict[str, dict[str, Any]] = {}
        self._local_sos_inputs: dict[str, str] = {}
        self._sessions: dict[str, dict[str, Any]] = {}
        self._idempotent_results: dict[tuple[str, str, str], dict[str, Any]] = {}
        self._idempotent_inputs: dict[tuple[str, str, str], str] = {}

    @property
    def events(self) -> list[dict[str, Any]]:
        return _clone(self._events)

    @property
    def local_sos_events(self) -> list[dict[str, Any]]:
        """Return a non-contract, in-memory trace of local-first SOS ordering."""

        return _clone(self._local_sos_events)

    def revoke_binding(self, *, device_id: str, guardian_id: str) -> None:
        """Model endpoint revocation without disabling trusted session closure."""

        self._authorized_bindings.discard((device_id, guardian_id))

    def _authorize_actor(
        self,
        *,
        device_id: str,
        guardian_id: str,
        actor_role: str,
        actor_id: str,
    ) -> None:
        endpoint_role = actor_role in {"device", "guardian", "safety_kernel"}
        if endpoint_role and (device_id, guardian_id) not in self._authorized_bindings:
            raise EgoCallAuthorizationError("device/guardian binding is not authorized")
        expected_actor = {
            "device": device_id,
            "guardian": guardian_id,
            # CALL-001 models the safety kernel as a device-bound trusted actor.
            "safety_kernel": device_id,
            "call_control": "fixture-call-control",
            "rtc_adapter": "fixture-rtc-adapter",
        }.get(actor_role)
        if expected_actor is None or actor_id != expected_actor:
            raise EgoCallAuthorizationError("actor is not authorized for this call session")

    @staticmethod
    def _authorize_transition_role(*, actor_role: str, reason_code: str) -> None:
        allowed_roles = {
            "guardian_notified": {"call_control"},
            "media_ready": {"rtc_adapter"},
            "media_lost": {"rtc_adapter"},
            "media_recovered": {"rtc_adapter"},
            "local_hangup": {"device"},
            "remote_hangup": {"guardian"},
            "declined": {"guardian"},
            "no_answer": {"call_control"},
            "setup_timeout": {"call_control"},
            "reconnect_timeout": {"rtc_adapter"},
            "unauthorized": {"call_control"},
            "binding_revoked": {"call_control"},
            "provider_unavailable": {"rtc_adapter"},
            "network_unavailable": {"rtc_adapter"},
            "internal_error": {"call_control"},
        }.get(reason_code, set())
        if actor_role not in allowed_roles:
            raise EgoCallAuthorizationError(
                "authenticated actor role cannot assert this call transition reason"
            )

    @staticmethod
    def _validate_persisted_assertion(event: dict[str, Any]) -> None:
        assertion = event["asserted_by"]
        actor_role = assertion["role"]
        actor_id = assertion["subject_ref"]
        transition = event["transition"]
        if transition["from"] is None:
            if actor_role != event["trigger"]["initiator"]:
                raise EgoCallAuthorizationError(
                    "initial assertion role does not match call initiator"
                )
            if (
                event.get("location_belief_ref") is not None
                and actor_role not in {"device", "safety_kernel"}
            ):
                raise EgoCallAuthorizationError(
                    "persisted call initiator cannot assert a location belief"
                )
        else:
            EgoCallFixture._authorize_transition_role(
                actor_role=actor_role,
                reason_code=transition["reason_code"],
            )
        expected_subject = {
            "device": event["device_id"],
            "safety_kernel": event["device_id"],
            "guardian": event["guardian_id"],
            "call_control": "fixture-call-control",
            "rtc_adapter": "fixture-rtc-adapter",
        }.get(actor_role)
        if expected_subject is not None and actor_id != expected_subject:
            raise EgoCallAuthorizationError(
                "persisted endpoint assertion does not match session identity"
            )

    @staticmethod
    def _validate_location_snapshot(event: dict[str, Any]) -> None:
        location = event.get("location_belief_ref")
        if not isinstance(location, dict) or location.get("state") == "Unknown":
            return
        event_time = datetime.fromisoformat(event["event_time_utc"].replace("Z", "+00:00"))
        observed_time = datetime.fromisoformat(
            location["observed_at_utc"].replace("Z", "+00:00")
        )
        computed_age_ms = round((event_time - observed_time).total_seconds() * 1000)
        reported_age_ms = location["age_ms"]
        if computed_age_ms < -5_000 or abs(computed_age_ms - reported_age_ms) > 5_000:
            raise EgoCallTransitionError(
                "location belief age is inconsistent with the call-event snapshot"
            )

    @staticmethod
    def _location_belief_identity(location: Any) -> Any:
        """Compare belief content while allowing event-time age to advance."""

        if not isinstance(location, dict):
            return location
        return {
            key: location.get(key)
            for key in ("belief_id", "state", "observed_at_utc", "radius_m")
        }

    def request(
        self,
        *,
        device_id: str,
        guardian_id: str,
        idempotency_key: str,
        trigger_type: str,
        initiator: str,
        actor_role: str,
        actor_id: str,
        safety_event_ref: str | None = None,
        location_belief_ref: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._authorize_actor(
            device_id=device_id,
            guardian_id=guardian_id,
            actor_role=actor_role,
            actor_id=actor_id,
        )
        if initiator != actor_role:
            raise EgoCallAuthorizationError("request initiator does not match authenticated actor")
        if location_belief_ref is not None and actor_role not in {"device", "safety_kernel"}:
            raise EgoCallAuthorizationError(
                "authenticated actor cannot assert a location belief on call creation"
            )

        result_key = (device_id, guardian_id, idempotency_key)
        request_input = self._canonical_input(
            {
                "operation": "request",
                "trigger_type": trigger_type,
                "initiator": initiator,
                "actor_role": actor_role,
                "actor_id": actor_id,
                "safety_event_ref": safety_event_ref,
                "location_belief_ref": location_belief_ref,
            }
        )
        if result_key in self._idempotent_results:
            if self._idempotent_inputs[result_key] != request_input:
                raise EgoCallTransitionError("idempotency key was reused with conflicting request")
            return _clone(self._idempotent_results[result_key])

        session_id = f"call-{self._id_factory()}"
        event = self._build_event(
            session_id=session_id,
            sequence=0,
            from_state=None,
            to_state="requested",
            reason_code="created",
            idempotency_key=idempotency_key,
            device_id=device_id,
            guardian_id=guardian_id,
            actor_role=actor_role,
            actor_id=actor_id,
            trigger={
                "type": trigger_type,
                "initiator": initiator,
                "safety_event_ref": safety_event_ref,
            },
            location_belief_ref=location_belief_ref,
        )
        self._append(event)
        self._sessions[session_id] = event
        self._idempotent_results[result_key] = event
        self._idempotent_inputs[result_key] = request_input
        return _clone(event)

    def transition(
        self,
        session_id: str,
        *,
        to_state: str,
        reason_code: str,
        idempotency_key: str,
        actor_role: str,
        actor_id: str,
        location_belief_ref: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        previous = self._sessions.get(session_id)
        if previous is None:
            raise EgoCallTransitionError("unknown session")
        if to_state not in {
            "requested",
            "ringing",
            "connected",
            "reconnecting",
            "ended",
            "failed",
        }:
            raise EgoCallTransitionError("unknown target call state")
        self._authorize_actor(
            device_id=previous["device_id"],
            guardian_id=previous["guardian_id"],
            actor_role=actor_role,
            actor_id=actor_id,
        )
        self._authorize_transition_role(actor_role=actor_role, reason_code=reason_code)
        binding_active = (
            previous["device_id"], previous["guardian_id"]
        ) in self._authorized_bindings
        revoked_closeout = (
            actor_role == "call_control"
            and to_state == "failed"
            and reason_code == "binding_revoked"
        )
        if not binding_active and not revoked_closeout:
            raise EgoCallAuthorizationError(
                "revoked binding permits only trusted unauthorized closeout"
            )
        if (
            location_belief_ref is not None
            and location_belief_ref != previous["location_belief_ref"]
            and actor_role not in {"device", "safety_kernel"}
        ):
            raise EgoCallAuthorizationError(
                "authenticated transition actor cannot replace location belief"
            )
        result_key = (previous["device_id"], previous["guardian_id"], idempotency_key)
        transition_input = self._canonical_input(
            {
                "operation": "transition",
                "session_id": session_id,
                "to_state": to_state,
                "reason_code": reason_code,
                "actor_role": actor_role,
                "actor_id": actor_id,
                "location_belief_ref": location_belief_ref,
            }
        )
        if result_key in self._idempotent_results:
            if self._idempotent_inputs[result_key] != transition_input:
                raise EgoCallTransitionError("idempotency key was reused with conflicting transition")
            return _clone(self._idempotent_results[result_key])
        previous_state = previous["transition"]["to"]
        if previous_state in {"ended", "failed"}:
            raise EgoCallTransitionError("terminal session cannot transition")

        event = self._build_event(
            session_id=session_id,
            sequence=previous["sequence"] + 1,
            from_state=previous_state,
            to_state=to_state,
            reason_code=reason_code,
            idempotency_key=idempotency_key,
            device_id=previous["device_id"],
            guardian_id=previous["guardian_id"],
            actor_role=actor_role,
            actor_id=actor_id,
            trigger=previous["trigger"],
            location_belief_ref=(
                location_belief_ref
                if location_belief_ref is not None
                else previous["location_belief_ref"]
            ),
            refresh_location_age=location_belief_ref is None,
        )
        try:
            self._validator.validate(event)
        except Exception as exc:
            raise EgoCallTransitionError(
                f"transition {previous_state!r} -> {to_state!r} rejected"
            ) from exc
        self._append(event)
        self._sessions[session_id] = event
        self._idempotent_results[result_key] = event
        self._idempotent_inputs[result_key] = transition_input
        return _clone(event)

    @staticmethod
    def _canonical_input(value: dict[str, Any]) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"))

    def compose_manual_sos(
        self,
        *,
        device_id: str,
        guardian_id: str,
        sos_event_id: str,
        idempotency_key: str,
        location_belief_ref: dict[str, Any] | None,
    ) -> dict[str, Any]:
        sos_input = self._canonical_input(
            {
                "device_id": device_id,
                "guardian_id": guardian_id,
                "sos_event_id": sos_event_id,
                "idempotency_key": idempotency_key,
                "location_belief_ref": location_belief_ref,
            }
        )
        if sos_event_id in self._local_sos_results:
            if self._local_sos_inputs[sos_event_id] != sos_input:
                raise EgoCallTransitionError(
                    "SOS event ID was reused with conflicting local/remote input"
                )
            return _clone(self._local_sos_results[sos_event_id])

        local_event = {
            "event_id": sos_event_id,
            "event_type": "manual_sos",
            "local_state": "recorded_in_memory_fixture",
            "local_feedback": "started",
            "location_policy": "elevated",
            "remote_delivery_state": "pending",
            "fresh_gnss_required_before_call": False,
            "ai_veto_allowed": False,
        }
        # Model local-first ordering before any fallible remote operation. This
        # list is not a durable safety-event store or a second safety contract.
        self._local_sos_events.append(_clone(local_event))
        try:
            call_event = self.request(
                device_id=device_id,
                guardian_id=guardian_id,
                idempotency_key=idempotency_key,
                trigger_type="manual_sos",
                initiator="device",
                actor_role="device",
                actor_id=device_id,
                safety_event_ref=sos_event_id,
                location_belief_ref=location_belief_ref,
            )
        except EgoCallError as error:
            local_event.update(
                {
                    "remote_delivery_state": "failed",
                    "remote_failure_reason": (
                        "authorization_failed"
                        if isinstance(error, EgoCallAuthorizationError)
                        else "call_request_rejected"
                    ),
                }
            )
            self._local_sos_events[-1] = _clone(local_event)
            result = {
                "local_event": _clone(local_event),
                "call_event": None,
                "remote_call_state": "failed",
                "operation_order": [
                    "record_local_fixture_sos",
                    "start_parallel_remote_actions",
                ],
            }
            self._local_sos_inputs[sos_event_id] = sos_input
            self._local_sos_results[sos_event_id] = _clone(result)
            return _clone(result)
        local_event["remote_delivery_state"] = "requested"
        self._local_sos_events[-1] = _clone(local_event)
        result = {
            "local_event": _clone(local_event),
            "call_event": call_event,
            "remote_call_state": "requested",
            "operation_order": [
                "record_local_fixture_sos",
                "start_parallel_remote_actions",
            ],
        }
        self._local_sos_inputs[sos_event_id] = sos_input
        self._local_sos_results[sos_event_id] = _clone(result)
        return _clone(result)

    def _build_event(
        self,
        *,
        session_id: str,
        sequence: int,
        from_state: str | None,
        to_state: str,
        reason_code: str,
        idempotency_key: str,
        device_id: str,
        guardian_id: str,
        actor_role: str,
        actor_id: str,
        trigger: dict[str, Any],
        location_belief_ref: dict[str, Any] | None,
        refresh_location_age: bool = False,
    ) -> dict[str, Any]:
        event_time_utc = self._clock()
        location_snapshot = _clone(location_belief_ref)
        if (
            refresh_location_age
            and isinstance(location_snapshot, dict)
            and location_snapshot.get("state") != "Unknown"
        ):
            event_time = datetime.fromisoformat(event_time_utc.replace("Z", "+00:00"))
            observed_time = datetime.fromisoformat(
                location_snapshot["observed_at_utc"].replace("Z", "+00:00")
            )
            location_snapshot["age_ms"] = round(
                (event_time - observed_time).total_seconds() * 1000
            )
        signaling_status, media_status = _transport_state(to_state)
        provider_session_ref = (
            f"fixture-provider-{session_id}"
            if to_state in {"ringing", "connected", "reconnecting"}
            else None
        )
        return {
            "contract_version": "egolink.ego_call_session.v0.1",
            "session_id": session_id,
            "event_id": f"event-{self._id_factory()}",
            "idempotency_key": idempotency_key,
            "sequence": sequence,
            "event_time_utc": event_time_utc,
            "device_id": device_id,
            "guardian_id": guardian_id,
            "asserted_by": {
                "role": actor_role,
                "subject_ref": actor_id,
            },
            "trigger": trigger,
            "transition": {
                "from": from_state,
                "to": to_state,
                "reason_code": reason_code,
            },
            "location_belief_ref": location_snapshot,
            "signaling": {
                "mode": "managed_rtc",
                "status": signaling_status,
                "provider_session_ref": provider_session_ref,
            },
            "media": {
                "status": media_status,
                "direction": "full_duplex",
                "relay_mode": "managed_unknown",
            },
            "privacy": {
                "metadata_retention_seconds": 604800,
                "media_recording_allowed": False,
                "consent_ref": None,
            },
        }

    def _append(self, event: dict[str, Any]) -> None:
        try:
            self._validator.validate(event)
            self._validate_persisted_assertion(event)
            self._validate_location_snapshot(event)
            previous = self._sessions.get(event["session_id"])
            if previous is not None:
                event_time = datetime.fromisoformat(
                    event["event_time_utc"].replace("Z", "+00:00")
                )
                previous_time = datetime.fromisoformat(
                    previous["event_time_utc"].replace("Z", "+00:00")
                )
                if event_time < previous_time:
                    raise EgoCallTransitionError("session event time moved backwards")
        except Exception as exc:
            raise EgoCallTransitionError("call event was rejected by the session contract") from exc
        self._events.append(event)


def replay_events(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Validate append order and return bounded final state per session."""

    validator = load_validator()
    sessions: dict[str, dict[str, Any]] = {}
    seen_event_ids: dict[str, str] = {}
    seen_idempotency: dict[tuple[str, str, str], str] = {}
    accepted_count = 0

    for event in events:
        validator.validate(event)
        EgoCallFixture._validate_persisted_assertion(event)
        EgoCallFixture._validate_location_snapshot(event)
        canonical = json.dumps(event, sort_keys=True, separators=(",", ":"))
        event_id = event["event_id"]
        if event_id in seen_event_ids:
            if seen_event_ids[event_id] != canonical:
                raise EgoCallTransitionError("conflicting duplicate event_id")
            continue
        seen_event_ids[event_id] = canonical

        idempotency_scope = (
            event["device_id"],
            event["guardian_id"],
            event["idempotency_key"],
        )
        if idempotency_scope in seen_idempotency:
            raise EgoCallTransitionError("idempotency_key reused by a different event")
        seen_idempotency[idempotency_scope] = event_id

        session_id = event["session_id"]
        previous = sessions.get(session_id)
        if previous is None:
            if event["sequence"] != 0 or event["transition"]["from"] is not None:
                raise EgoCallTransitionError("session must start at sequence 0 requested")
        else:
            if event["sequence"] != previous["sequence"] + 1:
                raise EgoCallTransitionError("session sequence is not contiguous")
            if event["transition"]["from"] != previous["transition"]["to"]:
                raise EgoCallTransitionError("transition does not continue prior state")
            event_time = datetime.fromisoformat(
                event["event_time_utc"].replace("Z", "+00:00")
            )
            previous_time = datetime.fromisoformat(
                previous["event_time_utc"].replace("Z", "+00:00")
            )
            if event_time < previous_time:
                raise EgoCallTransitionError("session event time moved backwards")
            if event["device_id"] != previous["device_id"] or event["guardian_id"] != previous["guardian_id"]:
                raise EgoCallAuthorizationError("session identity changed during replay")
            if event["trigger"] != previous["trigger"]:
                raise EgoCallTransitionError("session trigger changed during replay")
            if (
                event["asserted_by"]["role"] not in {"device", "safety_kernel"}
                and EgoCallFixture._location_belief_identity(
                    event["location_belief_ref"]
                )
                != EgoCallFixture._location_belief_identity(
                    previous["location_belief_ref"]
                )
            ):
                raise EgoCallAuthorizationError(
                    "persisted transition actor cannot replace location belief"
                )
        sessions[session_id] = event
        accepted_count += 1

    return {
        "contract_version": "egolink.ego_call_fixture_replay.v0.1",
        "accepted_event_count": accepted_count,
        "session_count": len(sessions),
        "sessions": {
            session_id: {
                "final_state": event["transition"]["to"],
                "last_sequence": event["sequence"],
                "device_id": event["device_id"],
                "guardian_id": event["guardian_id"],
            }
            for session_id, event in sorted(sessions.items())
        },
        "scope": "pc_fixture_only_not_product_audio_or_network_evidence",
    }

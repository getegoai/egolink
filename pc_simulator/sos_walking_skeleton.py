"""Isolated host composition for the SOS-010 walking-skeleton seam.

This module composes existing host references only.  It does not read a real
button, control hardware, open a network connection, capture media, or claim
that the physical P0-SOS gate passes.
"""

from __future__ import annotations

import hashlib
import json
import math
import threading
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from jsonschema import Draft202012Validator

from pc_simulator.ego_call import (
    EgoCallAuthorizationError,
    EgoCallFixture,
    EgoCallTransitionError,
)
from pc_simulator.location_engine_v0 import LocationEngineV0
from pc_simulator.persistent_priority_outbox import (
    PersistentPriorityOutbox,
    positive_ack_for,
)
from pc_simulator.sensor_policy_v0 import SensorPolicyV0, load_sensor_policy_config


ROOT = Path(__file__).resolve().parents[1]
SAFETY_EVENT_SCHEMA_PATH = ROOT / "shared" / "contracts" / "safety_event.schema.json"
POLICY_DECISION_SCHEMA_PATH = (
    ROOT / "shared" / "contracts" / "sensor_policy_decision_v0.schema.json"
)
DEFAULT_POLICY_CONFIG_PATH = ROOT / "shared" / "config" / "sensor_policy_v0.json"
SAFETY_EVENT_SCHEMA = json.loads(SAFETY_EVENT_SCHEMA_PATH.read_text(encoding="utf-8"))
SAFETY_EVENT_VALIDATOR = Draft202012Validator(SAFETY_EVENT_SCHEMA)
POLICY_DECISION_VALIDATOR = Draft202012Validator(
    json.loads(POLICY_DECISION_SCHEMA_PATH.read_text(encoding="utf-8"))
)


class SosCompositionError(ValueError):
    """Base error for a rejected host SOS composition."""


class SosTriggerRejected(SosCompositionError):
    """Raised when the supplied button trace is not a qualified long press."""


class SosIdempotencyError(SosCompositionError):
    """Raised when an SOS event ID is reused with conflicting input."""


def _clone(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _integer(value: Any, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise SosCompositionError(f"{name} must be an integer >= {minimum}")
    return value


def _boolean(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise SosCompositionError(f"{name} must be boolean")
    return value


def _epoch_ms_to_utc(value: int) -> str:
    value = _integer(value, "event_time_ms")
    try:
        instant = datetime.fromtimestamp(value / 1000.0, tz=timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise SosCompositionError(
            "event_time_ms is outside the UTC date-time range"
        ) from exc
    return instant.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _serialized(method: Callable[..., Any]) -> Callable[..., Any]:
    """Serialize stateful host-composition calls without changing their API."""

    @wraps(method)
    def wrapped(self: "SosWalkingSkeleton", *args: Any, **kwargs: Any) -> Any:
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapped


def detect_qualified_long_press(
    samples: Sequence[Mapping[str, Any]],
    *,
    observed_until_ms: int,
    debounce_ms: int = 50,
    threshold_ms: int = 2_000,
) -> dict[str, Any]:
    """Validate a debounced long press without retaining the raw trace.

    ``samples`` must contain nondecreasing ``event_time_ms`` values and a
    boolean ``pressed`` value.  The threshold starts only after the press has
    remained stable for the debounce interval, which is deliberately
    conservative for a safety trigger.
    """

    if isinstance(samples, (str, bytes)) or not isinstance(samples, Sequence):
        raise SosCompositionError("samples must be a sequence of button observations")
    if not samples:
        raise SosTriggerRejected("button trace is empty")
    observed_until_ms = _integer(observed_until_ms, "observed_until_ms")
    debounce_ms = _integer(debounce_ms, "debounce_ms", minimum=1)
    threshold_ms = _integer(threshold_ms, "threshold_ms", minimum=1)

    raw_pressed = False
    stable_pressed = False
    raw_changed_at_ms: int | None = None
    stable_pressed_at_ms: int | None = None
    prior_time_ms: int | None = None
    raw_transition_count = 0

    def advance(target_ms: int) -> int | None:
        nonlocal stable_pressed, stable_pressed_at_ms, raw_changed_at_ms
        pending_at = (
            raw_changed_at_ms + debounce_ms
            if raw_changed_at_ms is not None and raw_pressed != stable_pressed
            else None
        )
        trigger_at = (
            stable_pressed_at_ms + threshold_ms
            if stable_pressed and stable_pressed_at_ms is not None
            else None
        )
        if (
            trigger_at is not None
            and trigger_at <= target_ms
            and (pending_at is None or trigger_at <= pending_at)
        ):
            return trigger_at
        if pending_at is not None and pending_at <= target_ms:
            stable_pressed = raw_pressed
            raw_changed_at_ms = None
            stable_pressed_at_ms = pending_at if stable_pressed else None
            trigger_at = (
                stable_pressed_at_ms + threshold_ms
                if stable_pressed_at_ms is not None
                else None
            )
            if trigger_at is not None and trigger_at <= target_ms:
                return trigger_at
        return None

    for sample in samples:
        if not isinstance(sample, Mapping):
            raise SosCompositionError("each button sample must be an object")
        event_time_ms = _integer(sample.get("event_time_ms"), "sample.event_time_ms")
        pressed = _boolean(sample.get("pressed"), "sample.pressed")
        if prior_time_ms is not None and event_time_ms < prior_time_ms:
            raise SosCompositionError("button sample event_time_ms must not regress")
        if event_time_ms > observed_until_ms:
            raise SosCompositionError("button sample exceeds observed_until_ms")
        triggered_at_ms = advance(event_time_ms)
        if triggered_at_ms is not None:
            return {
                "qualified": True,
                "stable_pressed_at_ms": stable_pressed_at_ms,
                "triggered_at_ms": triggered_at_ms,
                "debounce_ms": debounce_ms,
                "threshold_ms": threshold_ms,
                "raw_transition_count": raw_transition_count,
            }
        if pressed != raw_pressed:
            raw_pressed = pressed
            raw_changed_at_ms = event_time_ms
            raw_transition_count += 1
        prior_time_ms = event_time_ms

    triggered_at_ms = advance(observed_until_ms)
    if triggered_at_ms is None:
        raise SosTriggerRejected("button trace did not satisfy the debounced hold threshold")
    return {
        "qualified": True,
        "stable_pressed_at_ms": stable_pressed_at_ms,
        "triggered_at_ms": triggered_at_ms,
        "debounce_ms": debounce_ms,
        "threshold_ms": threshold_ms,
        "raw_transition_count": raw_transition_count,
    }


class SosWalkingSkeleton:
    """Local-first SOS composition over frozen host contracts and seams."""

    def __init__(
        self,
        storage_dir: str | Path,
        *,
        device_id: str,
        guardian_id: str,
        call_authorized: bool = True,
        policy_config_path: str | Path = DEFAULT_POLICY_CONFIG_PATH,
    ) -> None:
        self._lock = threading.RLock()
        self.device_id = device_id
        self.guardian_id = guardian_id
        config = load_sensor_policy_config(policy_config_path)
        self.config = config
        self.location_engine = LocationEngineV0(config.location_engine_config())
        self.sensor_policy = SensorPolicyV0(config)
        self.outbox = PersistentPriorityOutbox(storage_dir, device_id=device_id)
        self._call_time_utc = "1970-01-01T00:00:00.000Z"
        self._id_counter = 0
        bindings = {(device_id, guardian_id)} if call_authorized else set()
        self.call_fixture = EgoCallFixture(
            authorized_bindings=bindings,
            clock=lambda: self._call_time_utc,
            id_factory=self._next_id,
        )
        self._idempotent_inputs: dict[str, str] = {}
        self._idempotent_results: dict[str, dict[str, Any]] = {}

    def _next_id(self) -> str:
        self._id_counter += 1
        return f"sos-host-{self._id_counter:04d}"

    @_serialized
    def apply_observation(self, observation: Mapping[str, Any]) -> dict[str, Any]:
        """Seed location/policy state and return only a privacy-minimized view."""

        state = self.location_engine.process(observation)
        decision = self.sensor_policy.evaluate(
            state,
            event_type=observation.get("event_type"),
            observation=observation,
        )
        self.location_engine.set_policy_context(decision["policy_mode"])
        state = self.location_engine.snapshot(state["event_time_ms"])
        return {
            "event_time_ms": state["event_time_ms"],
            "location_belief": state["location_belief"],
            "last_trusted_available": state["last_trusted_location"] is not None,
            "battery_state": state["battery_state"],
            "battery_percent": state["battery_percent"],
            "policy_mode": decision["policy_mode"],
        }

    @_serialized
    def compose_manual_sos(
        self,
        *,
        event_id: str,
        button_samples: Sequence[Mapping[str, Any]],
        observed_until_ms: int,
        battery_percent: float | None,
        base_online: bool,
        upload_available: bool,
        source_sequence: int,
        boot_count: int = 1,
        session_id: str = "sos-host-session",
        debounce_ms: int = 50,
        long_press_threshold_ms: int = 2_000,
        guardian_transport_available: bool = True,
        server_delivery_ack: bool = False,
        call_outcome: str = "requested",
        ai_recommendation: str | None = None,
        camera_available: bool = False,
    ) -> dict[str, Any]:
        """Compose one qualified manual SOS with independent remote outcomes.

        Supported ``call_outcome`` values are ``requested``, ``declined``,
        ``network_unavailable`` and ``provider_unavailable``.  AI advice and
        camera availability are observed only as non-vetoable diagnostics.
        """

        if not isinstance(event_id, str) or not event_id or len(event_id) > 128:
            raise SosCompositionError("event_id must be a 1-128 character string")
        source_sequence = _integer(source_sequence, "source_sequence")
        boot_count = _integer(boot_count, "boot_count")
        if not isinstance(session_id, str) or not session_id:
            raise SosCompositionError("session_id must be a non-empty string")
        normalized_battery_percent: float | None = None
        if battery_percent is not None:
            if (
                isinstance(battery_percent, bool)
                or not isinstance(battery_percent, (int, float))
                or not math.isfinite(float(battery_percent))
                or not 0 <= float(battery_percent) <= 100
            ):
                raise SosCompositionError(
                    "battery_percent must be null or finite and within [0, 100]"
                )
            normalized_battery_percent = float(battery_percent)
        base_online = _boolean(base_online, "base_online")
        upload_available = _boolean(upload_available, "upload_available")
        guardian_transport_available = _boolean(
            guardian_transport_available, "guardian_transport_available"
        )
        server_delivery_ack = _boolean(
            server_delivery_ack, "server_delivery_ack"
        )
        camera_available = _boolean(camera_available, "camera_available")
        if server_delivery_ack and not guardian_transport_available:
            raise SosCompositionError(
                "server_delivery_ack requires transport acceptance"
            )
        allowed_call_outcomes = {
            "requested",
            "declined",
            "network_unavailable",
            "provider_unavailable",
        }
        if call_outcome not in allowed_call_outcomes:
            raise SosCompositionError("unsupported call_outcome")

        trigger = detect_qualified_long_press(
            button_samples,
            observed_until_ms=observed_until_ms,
            debounce_ms=debounce_ms,
            threshold_ms=long_press_threshold_ms,
        )
        triggered_at_ms = trigger["triggered_at_ms"]
        if (
            self.location_engine.last_event_time_ms is not None
            and triggered_at_ms < self.location_engine.last_event_time_ms
        ):
            raise SosCompositionError("SOS trigger predates current location state")

        composition_input = json.dumps(
            {
                "event_id": event_id,
                "trigger": trigger,
                "battery_percent": normalized_battery_percent,
                "base_online": base_online,
                "upload_available": upload_available,
                "source_sequence": source_sequence,
                "boot_count": boot_count,
                "session_id": session_id,
                "guardian_transport_available": guardian_transport_available,
                "server_delivery_ack": server_delivery_ack,
                "call_outcome": call_outcome,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        prior_input = self._idempotent_inputs.get(event_id)
        if prior_input is not None:
            if prior_input != composition_input:
                raise SosIdempotencyError(
                    "SOS event ID was reused with conflicting composition input"
                )
            replay = _clone(self._idempotent_results[event_id])
            replay["composition"]["idempotent_replay"] = True
            return replay

        stored_record = self._persisted_record(event_id)
        record_preexisted = stored_record is not None
        if stored_record is not None:
            self._validate_replayed_record(
                stored_record,
                trigger=trigger,
                battery_percent=normalized_battery_percent,
                base_online=base_online,
                upload_available=upload_available,
                source_sequence=source_sequence,
                boot_count=boot_count,
                session_id=session_id,
            )
            safety_event = _clone(stored_record["payload"])
            location_ref = _clone(
                safety_event["model_result"].get(
                    "location_belief_ref", self._unknown_location_ref(event_id)
                )
            )
            location_confidence = float(
                safety_event["model_result"].get("location_confidence", 0.0)
            )
            location_snapshot_status = _clone(
                safety_event["model_result"].get(
                    "location_snapshot",
                    {"state": "unavailable", "reason_code": "REOPEN_CONTEXT_UNAVAILABLE"},
                )
            )
        else:
            try:
                initial_location_state = self.location_engine.snapshot(triggered_at_ms)
                location_ref = self._location_belief_ref(
                    initial_location_state, event_id=event_id
                )
                location_confidence = float(
                    initial_location_state["location_confidence"]
                )
                location_snapshot_status = {
                    "state": "available",
                    "reason_code": "LOCATION_SNAPSHOT_AVAILABLE",
                }
            except Exception as exc:
                # Location is an independent post-trigger dependency. Persist an
                # honest coordinate-free Unknown reference instead of vetoing SOS.
                location_ref = self._unknown_location_ref(event_id)
                location_confidence = 0.0
                location_snapshot_status = {
                    "state": "unavailable",
                    "reason_code": "LOCATION_SNAPSHOT_ERROR",
                    "error_type": type(exc).__name__,
                }
            safety_event = {
                "contract_version": "1.0.0",
                "event_id": event_id,
                "device_id": self.device_id,
                "timestamp_ms": triggered_at_ms,
                "sequence": source_sequence,
                "event_type": "manual_sos",
                "priority": "critical",
                "source": "device_rule",
                "model_result": {
                    "manual_input": True,
                    "qualified_long_press": True,
                    "debounce_ms": trigger["debounce_ms"],
                    "hold_threshold_ms": trigger["threshold_ms"],
                    # Coordinate-free trigger context keeps call idempotency input
                    # stable if the host fixture is reopened without live location
                    # state. It is not an upload or a fresh-position claim.
                    "location_belief_ref": location_ref,
                    "location_confidence": location_confidence,
                    "location_snapshot": location_snapshot_status,
                },
                "context": {
                    "mode": "manual_sos",
                    "battery_percent": normalized_battery_percent,
                    "base_online": base_online,
                    "upload_available": upload_available,
                },
                "evidence": {
                    "audio_clip_ref": None,
                    "image_ref": None,
                    "imu_window_ref": None,
                    "location_fresh": location_ref["state"] in {"Fine", "Coarse"},
                },
                "privacy": {
                    "privacy_mode": True,
                    "raw_evidence_allowed": False,
                    "retention_seconds": 86_400,
                },
            }
        errors = sorted(
            SAFETY_EVENT_VALIDATOR.iter_errors(safety_event),
            key=lambda error: error.json_path,
        )
        if errors:
            message = "; ".join(
                f"{error.json_path}: {error.message}" for error in errors
            )
            raise SosCompositionError(f"manual_sos violates safety_event contract: {message}")

        operation_order: list[str] = []
        record = self.outbox.enqueue(
            event_id=event_id,
            event_type="manual_sos",
            priority="critical",
            payload=safety_event,
            source_event_time_ms=triggered_at_ms,
            boot_count=boot_count,
            session_id=session_id,
            source_sequence=source_sequence,
            now_ms=triggered_at_ms,
        )
        operation_order.append("safety_event_persisted")

        local_feedback = {"state": "started", "started_after_persist": True}
        operation_order.append("local_feedback_started")

        manual_actions = {
            "source": "manual_sos_event_edge",
            "location_upload_requested": True,
            "ego_call_requested": True,
        }
        battery_state = "unknown"
        try:
            if normalized_battery_percent is not None:
                battery_state = self._battery_state(normalized_battery_percent)
                battery_observation = {
                    "event_type": "battery",
                    "event_time_ms": triggered_at_ms,
                    "battery_state": battery_state,
                    "battery_percent": normalized_battery_percent,
                }
                battery_location_state = self.location_engine.process(
                    battery_observation
                )
                battery_policy = self.sensor_policy.evaluate(
                    battery_location_state,
                    event_type="battery",
                    observation=battery_observation,
                )
                self.location_engine.set_policy_context(
                    battery_policy["policy_mode"]
                )
                observed_battery_percent = battery_location_state[
                    "battery_percent"
                ]
                if (
                    observed_battery_percent != normalized_battery_percent
                    or battery_location_state["battery_state"] != battery_state
                ):
                    raise SosCompositionError(
                        "trigger battery observation was not applied"
                    )

            sos_observation = {
                "event_type": "sos",
                "event_time_ms": triggered_at_ms,
                "active": True,
            }
            location_state = self.location_engine.process(sos_observation)
            policy_decision = self.sensor_policy.evaluate(
                location_state,
                event_type="sos",
                observation=sos_observation,
            )
            self.location_engine.set_policy_context(policy_decision["policy_mode"])
            location_state = self.location_engine.snapshot(triggered_at_ms)
            policy_decision = self._manual_sos_policy_decision(policy_decision)
            operation_order.append("sensor_policy_sos_applied")
        except Exception as exc:
            # A local policy failure is visible but cannot veto the already
            # persisted manual event, Guardian alert attempt, or call request.
            policy_failure = {
                "state": "failed",
                "policy_mode": "unavailable",
                "error_code": "SENSOR_POLICY_BRANCH_ERROR",
                "error_type": type(exc).__name__,
                "manual_sos_actions": _clone(manual_actions),
            }
            policy_decision = policy_failure
            operation_order.append("sensor_policy_sos_failed")

        has_last_trusted = location_ref["state"] != "Unknown"
        location_branch = {
            "policy_requested": manual_actions["location_upload_requested"],
            "state": (
                "upload_requested_adapter_not_connected"
                if manual_actions["location_upload_requested"] and has_last_trusted
                else "upload_requested_no_trusted_belief"
                if manual_actions["location_upload_requested"]
                else "not_requested"
            ),
            "adapter_connected": False,
            "upload_executed": False,
            "upload_persisted": False,
            "belief_ref": location_ref,
            "belief_snapshot": location_snapshot_status,
        }

        try:
            guardian_alert = self._attempt_guardian_alert(
                record=record,
                event_time_ms=triggered_at_ms,
                transport_available=guardian_transport_available,
                server_delivery_ack=server_delivery_ack,
            )
        except Exception as exc:
            guardian_alert = {
                "state": "failed",
                "transport_accepted": False,
                "server_delivery_ack": None,
                "guardian_human_delivery": "unverified",
                "guardian_human_ack": "unverified",
                "current_event_attempted": False,
                "error_code": "GUARDIAN_ALERT_BRANCH_ERROR",
                "error_type": type(exc).__name__,
            }
        operation_order.append("guardian_alert_attempted")

        try:
            ego_call = self._request_ego_call(
                event_id=event_id,
                location_ref=location_ref,
                event_time_ms=triggered_at_ms,
                outcome=call_outcome,
                policy_requested=manual_actions["ego_call_requested"],
            )
        except Exception as exc:
            ego_call = {
                "state": "failed",
                "reason_code": "call_branch_error",
                "session_id": None,
                "policy_requested": manual_actions["ego_call_requested"],
                "request_attempted": manual_actions["ego_call_requested"],
                "request_created": False,
                "safety_event_ref": event_id,
                "location_belief_ref": dict(location_ref),
                "error_type": type(exc).__name__,
            }
        operation_order.append("ego_call_attempted")

        result = {
            "composition": {
                "mode": "isolated_host_reference",
                "idempotent_replay": False,
                "durable_outbox_replay": record_preexisted,
                "remote_session_durability_verified": False,
                "physical_p0_sos_verified": False,
                "operation_order": operation_order,
            },
            "trigger": trigger,
            "safety_event": safety_event,
            "local_event": {
                "state": "persisted",
                "event_id": event_id,
                "priority": "critical",
                "identity_sha256": record["identity_sha256"],
                "payload_sha256": record["payload_sha256"],
            },
            "local_feedback": local_feedback,
            "manual_sos_actions": manual_actions,
            "policy": policy_decision,
            "location": location_branch,
            "guardian_alert": guardian_alert,
            "ego_call": ego_call,
            "guardian_view": {
                "device_id": self.device_id,
                "safety_event_ref": event_id,
                "battery_state": battery_state,
                "battery_percent": normalized_battery_percent,
                "location": {
                    **location_ref,
                    "confidence": location_confidence,
                },
                "server_delivery_state": guardian_alert["state"],
                "guardian_human_delivery": "unverified",
                "guardian_human_ack": "unverified",
                "call_state": ego_call["state"],
            },
            "non_veto_guards": {
                "manual_sos_non_vetoable": True,
                "low_battery_vetoed": False,
                "ai_advice_present_but_non_authoritative": ai_recommendation is not None,
                "camera_available": camera_available,
                "camera_requested": bool(
                    policy_decision.get("actions", {})
                    .get("camera", {})
                    .get("requested", False)
                ),
            },
            "privacy": {
                "raw_button_trace_retained": False,
                "media_retained": False,
                "precise_coordinates_exported": False,
            },
        }
        self._idempotent_inputs[event_id] = composition_input
        self._idempotent_results[event_id] = _clone(result)
        return _clone(result)

    def _persisted_record(self, event_id: str) -> dict[str, Any] | None:
        document = self.outbox.export_storage_document()
        return next(
            (
                _clone(record)
                for record in document["records"]
                if record["event_id"] == event_id
            ),
            None,
        )

    def _validate_replayed_record(
        self,
        record: Mapping[str, Any],
        *,
        trigger: Mapping[str, Any],
        battery_percent: float | None,
        base_online: bool,
        upload_available: bool,
        source_sequence: int,
        boot_count: int,
        session_id: str,
    ) -> None:
        """Bind a reopen to the original durable SOS identity and payload.

        Location state is deliberately excluded from the comparison: it may be
        unavailable after a host reopen, so the already-persisted coordinate-
        free belief reference remains authoritative for this event.
        """

        payload = record["payload"]
        expected = {
            "record": {
                "source_event_time_ms": trigger["triggered_at_ms"],
                "boot_count": boot_count,
                "session_id": session_id,
                "source_sequence": source_sequence,
            },
            "event": {
                "event_id": record["event_id"],
                "device_id": self.device_id,
                "timestamp_ms": trigger["triggered_at_ms"],
                "sequence": source_sequence,
                "event_type": "manual_sos",
                "priority": "critical",
                "source": "device_rule",
            },
            "trigger": {
                "manual_input": True,
                "qualified_long_press": True,
                "debounce_ms": trigger["debounce_ms"],
                "hold_threshold_ms": trigger["threshold_ms"],
            },
            "context": {
                "mode": "manual_sos",
                "battery_percent": battery_percent,
                "base_online": base_online,
                "upload_available": upload_available,
            },
        }
        actual = {
            "record": {
                key: record[key]
                for key in (
                    "source_event_time_ms",
                    "boot_count",
                    "session_id",
                    "source_sequence",
                )
            },
            "event": {
                key: payload[key]
                for key in (
                    "event_id",
                    "device_id",
                    "timestamp_ms",
                    "sequence",
                    "event_type",
                    "priority",
                    "source",
                )
            },
            "trigger": {
                key: payload["model_result"][key]
                for key in (
                    "manual_input",
                    "qualified_long_press",
                    "debounce_ms",
                    "hold_threshold_ms",
                )
            },
            "context": payload["context"],
        }
        if actual != expected:
            raise SosIdempotencyError(
                "persisted SOS event conflicts with the replayed trigger identity"
            )

    @staticmethod
    def _manual_sos_policy_decision(
        policy_decision: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Apply the safety-contract edge actions to a valid policy decision.

        Sensor Policy keeps SOS active between evaluations, while every newly
        qualified physical event must independently request location upload and
        Ego Call. This adapter overlay makes that event-edge rule explicit.
        """

        composed = _clone(policy_decision)
        retrigger = not (
            composed["actions"]["location"]["upload_now"]
            and composed["actions"]["ego_call"]["start_now"]
        )
        composed["actions"]["location"]["upload_now"] = True
        composed["actions"]["ego_call"]["start_now"] = True
        reasons = composed["transition"]["reason_codes"]
        for reason in (
            "manual_sos_event_edge",
            "manual_sos_retrigger" if retrigger else None,
        ):
            if reason is not None and reason not in reasons:
                reasons.append(reason)
        errors = sorted(
            POLICY_DECISION_VALIDATOR.iter_errors(composed),
            key=lambda error: error.json_path,
        )
        if errors:
            raise SosCompositionError("manual SOS policy overlay violates its contract")
        return composed

    def _battery_state(self, battery_percent: float) -> str:
        thresholds = self.config.values["low_battery"]
        if battery_percent <= float(thresholds["critical_percent"]):
            return "critical"
        if battery_percent <= float(thresholds["enter_percent"]):
            return "low"
        if (
            self.sensor_policy.runtime.low_battery_latched
            and battery_percent < float(thresholds["exit_percent"])
        ):
            return "low"
        return "normal"

    @staticmethod
    def _unknown_location_ref(event_id: str) -> dict[str, Any]:
        return {
            "belief_id": (
                "sos-belief-"
                f"{hashlib.sha256(event_id.encode('utf-8')).hexdigest()[:24]}"
            ),
            "state": "Unknown",
            "observed_at_utc": None,
            "age_ms": None,
            "radius_m": None,
        }

    def _location_belief_ref(
        self, location_state: Mapping[str, Any], *, event_id: str
    ) -> dict[str, Any]:
        unknown = self._unknown_location_ref(event_id)
        belief_id = unknown["belief_id"]
        state = location_state["location_belief"]
        trusted_time_ms = location_state["last_trusted_time_ms"]
        radius_m = location_state["location_uncertainty_m"]
        if (
            state not in {"Fine", "Coarse", "Predicted"}
            or trusted_time_ms is None
            or radius_m is None
        ):
            return unknown
        return {
            "belief_id": belief_id,
            "state": state,
            "observed_at_utc": _epoch_ms_to_utc(trusted_time_ms),
            "age_ms": location_state["event_time_ms"] - trusted_time_ms,
            "radius_m": float(radius_m),
        }

    def _attempt_guardian_alert(
        self,
        *,
        record: Mapping[str, Any],
        event_time_ms: int,
        transport_available: bool,
        server_delivery_ack: bool,
    ) -> dict[str, Any]:
        attempt_time_ms = event_time_ms + 1
        result_time_ms = event_time_ms + 2
        prior_due_attempts_processed = 0
        scan_budget = self.outbox.snapshot(now_ms=attempt_time_ms)["queued_count"] + 1
        attempt: dict[str, Any] | None = None

        # The outbox owns global priority/FIFO selection and has no targeted
        # begin API. Drain each earlier due item through a truthful transport
        # result before selecting this event; never abandon another record in
        # ``attempt_started`` merely because it was not the current SOS.
        for _ in range(scan_budget):
            selected = self.outbox.begin_send_attempt(now_ms=attempt_time_ms)
            if selected is None:
                break
            if selected["event_id"] == record["event_id"]:
                attempt = selected
                break
            self.outbox.record_transport_result(
                attempt_token=selected["last_attempt_token"],
                accepted_by_transport=transport_available,
                now_ms=result_time_ms,
                error_code=None if transport_available else "NETWORK_UNAVAILABLE",
            )
            prior_due_attempts_processed += 1

        if attempt is None:
            current = next(
                (
                    item
                    for item in self.outbox.snapshot(now_ms=attempt_time_ms)["records"]
                    if item["event_id"] == record["event_id"]
                ),
                None,
            )
            current_state = current["send_state"] if current is not None else "not_queued"
            transport_accepted = current_state == "awaiting_positive_ack"
            if server_delivery_ack and transport_accepted:
                ack_result = self.outbox.handle_ack(
                    positive_ack_for(
                        record,
                        ack_id=(
                            "ack-"
                            f"{hashlib.sha256(record['event_id'].encode('utf-8')).hexdigest()[:20]}"
                        ),
                        ack_time_ms=event_time_ms + 3,
                    )
                )
                return {
                    "state": "server_acknowledged",
                    "transport_accepted": True,
                    "server_delivery_ack": ack_result,
                    "guardian_human_delivery": "unverified",
                    "guardian_human_ack": "unverified",
                    "current_event_attempted": False,
                    "prior_due_attempts_processed": prior_due_attempts_processed,
                }
            return {
                "state": current_state,
                "transport_accepted": transport_accepted,
                "server_delivery_ack": None,
                "guardian_human_delivery": "unverified",
                "guardian_human_ack": "unverified",
                "current_event_attempted": False,
                "prior_due_attempts_processed": prior_due_attempts_processed,
            }
        if not transport_available:
            self.outbox.record_transport_result(
                attempt_token=attempt["last_attempt_token"],
                accepted_by_transport=False,
                now_ms=result_time_ms,
                error_code="NETWORK_UNAVAILABLE",
            )
            return {
                "state": "retry_wait",
                "transport_accepted": False,
                "server_delivery_ack": None,
                "guardian_human_delivery": "unverified",
                "guardian_human_ack": "unverified",
                "current_event_attempted": True,
                "prior_due_attempts_processed": prior_due_attempts_processed,
                "error_code": "NETWORK_UNAVAILABLE",
            }
        self.outbox.record_transport_result(
            attempt_token=attempt["last_attempt_token"],
            accepted_by_transport=True,
            now_ms=result_time_ms,
        )
        if not server_delivery_ack:
            return {
                "state": "awaiting_positive_ack",
                "transport_accepted": True,
                "server_delivery_ack": None,
                "guardian_human_delivery": "unverified",
                "guardian_human_ack": "unverified",
                "current_event_attempted": True,
                "prior_due_attempts_processed": prior_due_attempts_processed,
            }
        ack = positive_ack_for(
            record,
            ack_id=f"ack-{hashlib.sha256(record['event_id'].encode('utf-8')).hexdigest()[:20]}",
            ack_time_ms=event_time_ms + 3,
        )
        ack_result = self.outbox.handle_ack(ack)
        return {
            "state": "server_acknowledged",
            "transport_accepted": True,
            "server_delivery_ack": ack_result,
            "guardian_human_delivery": "unverified",
            "guardian_human_ack": "unverified",
            "current_event_attempted": True,
            "prior_due_attempts_processed": prior_due_attempts_processed,
        }

    def _request_ego_call(
        self,
        *,
        event_id: str,
        location_ref: Mapping[str, Any],
        event_time_ms: int,
        outcome: str,
        policy_requested: bool,
    ) -> dict[str, Any]:
        if not policy_requested:
            return {
                "state": "not_requested",
                "reason_code": "policy_not_requested",
                "session_id": None,
                "policy_requested": False,
                "request_attempted": False,
                "request_created": False,
                "safety_event_ref": event_id,
                "location_belief_ref": dict(location_ref),
            }
        digest = hashlib.sha256(event_id.encode("utf-8")).hexdigest()[:24]
        self._call_time_utc = _epoch_ms_to_utc(event_time_ms)
        try:
            request = self.call_fixture.request(
                device_id=self.device_id,
                guardian_id=self.guardian_id,
                idempotency_key=f"sos-call-{digest}",
                trigger_type="manual_sos",
                initiator="device",
                actor_role="device",
                actor_id=self.device_id,
                safety_event_ref=event_id,
                location_belief_ref=dict(location_ref),
            )
            final = request
            if outcome == "declined":
                self._call_time_utc = _epoch_ms_to_utc(event_time_ms + 1)
                final = self.call_fixture.transition(
                    request["session_id"],
                    to_state="ended",
                    reason_code="declined",
                    idempotency_key=f"sos-declined-{digest}",
                    actor_role="guardian",
                    actor_id=self.guardian_id,
                )
            elif outcome in {"network_unavailable", "provider_unavailable"}:
                self._call_time_utc = _epoch_ms_to_utc(event_time_ms + 1)
                final = self.call_fixture.transition(
                    request["session_id"],
                    to_state="failed",
                    reason_code=outcome,
                    idempotency_key=f"sos-failed-{digest}",
                    actor_role="rtc_adapter",
                    actor_id="fixture-rtc-adapter",
                )
            return {
                "state": final["transition"]["to"],
                "reason_code": final["transition"]["reason_code"],
                "session_id": request["session_id"],
                "policy_requested": True,
                "request_attempted": True,
                "request_created": True,
                "safety_event_ref": event_id,
                "location_belief_ref": dict(location_ref),
            }
        except (EgoCallAuthorizationError, EgoCallTransitionError) as exc:
            return {
                "state": "rejected",
                "reason_code": "authorization_or_transition_rejected",
                "session_id": None,
                "policy_requested": True,
                "request_attempted": True,
                "request_created": False,
                "safety_event_ref": event_id,
                "location_belief_ref": dict(location_ref),
                "error_type": type(exc).__name__,
            }


__all__ = [
    "SosCompositionError",
    "SosIdempotencyError",
    "SosTriggerRejected",
    "SosWalkingSkeleton",
    "detect_qualified_long_press",
]

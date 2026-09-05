import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError

from pc_simulator.ego_call import load_validator


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "shared" / "contracts" / "ego_call_session.schema.json"


def _event(from_state, to_state):
    reason_by_transition = {
        (None, "requested"): "created",
        ("requested", "ringing"): "guardian_notified",
        ("requested", "failed"): "network_unavailable",
        ("requested", "ended"): "declined",
        ("ringing", "connected"): "media_ready",
        ("ringing", "failed"): "setup_timeout",
        ("ringing", "ended"): "declined",
        ("connected", "reconnecting"): "media_lost",
        ("connected", "failed"): "network_unavailable",
        ("connected", "ended"): "remote_hangup",
        ("reconnecting", "connected"): "media_recovered",
        ("reconnecting", "failed"): "reconnect_timeout",
        ("reconnecting", "ended"): "local_hangup",
    }
    signaling_status, media_status = {
        "requested": ("pending", "not_started"),
        "ringing": ("ready", "connecting"),
        "connected": ("ready", "ready"),
        "reconnecting": ("ready", "interrupted"),
        "ended": ("closed", "closed"),
        "failed": ("failed", "failed"),
    }[to_state]
    reason_code = reason_by_transition[(from_state, to_state)]
    actor_role = (
        "device"
        if from_state is None
        else {
            "guardian_notified": "call_control",
            "media_ready": "rtc_adapter",
            "media_lost": "rtc_adapter",
            "media_recovered": "rtc_adapter",
            "network_unavailable": "rtc_adapter",
            "reconnect_timeout": "rtc_adapter",
            "setup_timeout": "call_control",
            "remote_hangup": "guardian",
            "declined": "guardian",
            "local_hangup": "device",
        }[reason_code]
    )
    actor_id = {
        "device": "device-pseudonym-1",
        "guardian": "guardian-pseudonym-1",
        "call_control": "fixture-call-control",
        "rtc_adapter": "fixture-rtc-adapter",
    }[actor_role]
    return {
        "contract_version": "egolink.ego_call_session.v0.1",
        "session_id": "call-001",
        "event_id": f"call-001-1-{to_state}",
        "idempotency_key": "call-001-create-0001",
        "sequence": 0 if from_state is None else 1,
        "event_time_utc": "2026-08-23T08:00:00Z",
        "device_id": "device-pseudonym-1",
        "guardian_id": "guardian-pseudonym-1",
        "asserted_by": {"role": actor_role, "subject_ref": actor_id},
        "trigger": {
            "type": "manual_sos",
            "initiator": "device",
            "safety_event_ref": "sos-001",
        },
        "transition": {
            "from": from_state,
            "to": to_state,
            "reason_code": reason_code,
        },
        "location_belief_ref": {
            "belief_id": "belief-001",
            "state": "Predicted",
            "observed_at_utc": "2026-08-23T07:59:50Z",
            "age_ms": 10000,
            "radius_m": 80.0,
        },
        "signaling": {
            "mode": "managed_rtc",
            "status": signaling_status,
            "provider_session_ref": (
                "fixture-provider-call-001"
                if to_state in {"ringing", "connected", "reconnecting"}
                else None
            ),
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


class EgoCallContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(cls.schema)
        cls.validator = load_validator()

    def test_all_frozen_transitions_validate(self):
        allowed = [
            (None, "requested"),
            ("requested", "ringing"),
            ("requested", "failed"),
            ("requested", "ended"),
            ("ringing", "connected"),
            ("ringing", "failed"),
            ("ringing", "ended"),
            ("connected", "reconnecting"),
            ("connected", "failed"),
            ("connected", "ended"),
            ("reconnecting", "connected"),
            ("reconnecting", "failed"),
            ("reconnecting", "ended"),
        ]
        for pair in allowed:
            with self.subTest(pair=pair):
                self.validator.validate(_event(*pair))

    def test_invalid_transition_fails_closed(self):
        event = _event("requested", "ringing")
        event["transition"].update({"to": "reconnecting", "reason_code": "media_lost"})
        event["media"]["status"] = "interrupted"
        with self.assertRaises(ValidationError):
            self.validator.validate(event)

    def test_transition_reason_and_transport_state_must_agree(self):
        wrong_reason = _event("ringing", "connected")
        wrong_reason["transition"]["reason_code"] = "internal_error"
        with self.assertRaises(ValidationError):
            self.validator.validate(wrong_reason)

        false_connected = _event("ringing", "connected")
        false_connected["media"]["status"] = "not_started"
        with self.assertRaises(ValidationError):
            self.validator.validate(false_connected)

        missing_provider = _event("requested", "ringing")
        missing_provider["signaling"]["provider_session_ref"] = None
        with self.assertRaises(ValidationError):
            self.validator.validate(missing_provider)

        unanswered = _event("ringing", "ended")
        unanswered["transition"]["reason_code"] = "no_answer"
        unanswered["asserted_by"] = {
            "role": "call_control",
            "subject_ref": "fixture-call-control",
        }
        self.validator.validate(unanswered)

        ambiguous_timeout = _event("ringing", "ended")
        ambiguous_timeout["transition"]["reason_code"] = "setup_timeout"
        ambiguous_timeout["asserted_by"] = {
            "role": "call_control",
            "subject_ref": "fixture-call-control",
        }
        with self.assertRaises(ValidationError):
            self.validator.validate(ambiguous_timeout)

    def test_schema_binds_transition_reason_to_asserting_role(self):
        forged_media = _event("ringing", "connected")
        forged_media["asserted_by"] = {
            "role": "device",
            "subject_ref": "device-pseudonym-1",
        }
        with self.assertRaises(ValidationError):
            self.validator.validate(forged_media)

        forged_notification = _event("requested", "ringing")
        forged_notification["asserted_by"] = {
            "role": "guardian",
            "subject_ref": "guardian-pseudonym-1",
        }
        with self.assertRaises(ValidationError):
            self.validator.validate(forged_notification)

        forged_creation = _event(None, "requested")
        forged_creation["asserted_by"] = {
            "role": "guardian",
            "subject_ref": "guardian-pseudonym-1",
        }
        with self.assertRaises(ValidationError):
            self.validator.validate(forged_creation)

        guardian_with_location = _event(None, "requested")
        guardian_with_location["trigger"] = {
            "type": "guardian_call",
            "initiator": "guardian",
            "safety_event_ref": None,
        }
        guardian_with_location["asserted_by"] = {
            "role": "guardian",
            "subject_ref": "guardian-pseudonym-1",
        }
        with self.assertRaises(ValidationError):
            self.validator.validate(guardian_with_location)

        for from_state in ("requested", "ringing", "connected", "reconnecting"):
            with self.subTest(binding_revoked_from=from_state):
                revoked = _event(from_state, "failed")
                revoked["transition"]["reason_code"] = "binding_revoked"
                revoked["asserted_by"] = {
                    "role": "call_control",
                    "subject_ref": "fixture-call-control",
                }
                self.validator.validate(revoked)

    def test_timestamp_trigger_and_location_semantics_fail_closed(self):
        invalid_time = _event(None, "requested")
        invalid_time["event_time_utc"] = "not-a-time"
        with self.assertRaises(ValidationError):
            self.validator.validate(invalid_time)

        impossible_time = _event(None, "requested")
        impossible_time["event_time_utc"] = "2026-99-99T99:99:99Z"
        with self.assertRaises(ValidationError):
            self.validator.validate(impossible_time)

        impossible_location_time = _event(None, "requested")
        impossible_location_time["location_belief_ref"]["observed_at_utc"] = (
            "2026-02-30T08:00:00Z"
        )
        with self.assertRaises(ValidationError):
            self.validator.validate(impossible_location_time)

        invalid_trigger = _event(None, "requested")
        invalid_trigger["trigger"] = {
            "type": "guardian_call",
            "initiator": "device",
            "safety_event_ref": None,
        }
        with self.assertRaises(ValidationError):
            self.validator.validate(invalid_trigger)

        incomplete_fixed = _event(None, "requested")
        incomplete_fixed["location_belief_ref"].update(
            {"state": "Fine", "observed_at_utc": None, "age_ms": None, "radius_m": None}
        )
        with self.assertRaises(ValidationError):
            self.validator.validate(incomplete_fixed)

        nonfinite_radius = _event(None, "requested")
        nonfinite_radius["location_belief_ref"]["radius_m"] = float("nan")
        with self.assertRaises(ValidationError):
            self.validator.validate(nonfinite_radius)

        unknown_with_stale_fields = _event(None, "requested")
        unknown_with_stale_fields["location_belief_ref"]["state"] = "Unknown"
        with self.assertRaises(ValidationError):
            self.validator.validate(unknown_with_stale_fields)

    def test_sequence_semantics_match_replay_contract(self):
        initial = _event(None, "requested")
        initial["sequence"] = 1
        with self.assertRaises(ValidationError):
            self.validator.validate(initial)

        continuation = _event("requested", "ringing")
        continuation["sequence"] = 0
        with self.assertRaises(ValidationError):
            self.validator.validate(continuation)

    def test_precise_coordinates_and_signaling_secrets_are_not_contract_fields(self):
        coordinate_copy = _event(None, "requested")
        coordinate_copy["location_belief_ref"]["latitude_deg"] = 31.2
        with self.assertRaises(ValidationError):
            self.validator.validate(coordinate_copy)

        signaling_secret = _event(None, "requested")
        signaling_secret["signaling"]["rtc_token"] = "must-not-persist"
        with self.assertRaises(ValidationError):
            self.validator.validate(signaling_secret)

    def test_recording_requires_nonempty_consent_reference(self):
        event = _event(None, "requested")
        event["privacy"]["media_recording_allowed"] = True
        with self.assertRaises(ValidationError):
            self.validator.validate(event)

        consented = copy.deepcopy(event)
        consented["privacy"]["consent_ref"] = "consent-policy-record-001"
        self.validator.validate(consented)


if __name__ == "__main__":
    unittest.main()

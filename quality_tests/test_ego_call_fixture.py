import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import ValidationError

from pc_simulator.ego_call import (
    EgoCallAuthorizationError,
    EgoCallFixture,
    EgoCallTransitionError,
    replay_events,
)


ROOT = Path(__file__).resolve().parents[1]


class _Ids:
    def __init__(self):
        self.value = 0

    def __call__(self):
        self.value += 1
        return f"id-{self.value:04d}"


class EgoCallFixtureTests(unittest.TestCase):
    def fixture(self):
        return EgoCallFixture(
            authorized_bindings={("device-1", "guardian-1")},
            clock=lambda: "2026-08-23T08:00:00Z",
            id_factory=_Ids(),
        )

    def request(self, fixture, key="request-key-0001"):
        return fixture.request(
            device_id="device-1",
            guardian_id="guardian-1",
            idempotency_key=key,
            trigger_type="device_call",
            initiator="device",
            actor_role="device",
            actor_id="device-1",
        )

    def transition(self, fixture, session_id, **kwargs):
        default_role = {
            "guardian_notified": "call_control",
            "media_ready": "rtc_adapter",
            "media_lost": "rtc_adapter",
            "media_recovered": "rtc_adapter",
            "network_unavailable": "rtc_adapter",
            "reconnect_timeout": "rtc_adapter",
            "provider_unavailable": "rtc_adapter",
            "setup_timeout": "call_control",
            "internal_error": "call_control",
            "unauthorized": "call_control",
            "binding_revoked": "call_control",
            "remote_hangup": "guardian",
            "declined": "guardian",
            "no_answer": "call_control",
            "local_hangup": "device",
        }[kwargs["reason_code"]]
        actor_role = kwargs.pop("actor_role", default_role)
        default_actor_id = {
            "device": "device-1",
            "guardian": "guardian-1",
            "call_control": "fixture-call-control",
            "rtc_adapter": "fixture-rtc-adapter",
        }[actor_role]
        return fixture.transition(
            session_id,
            actor_role=actor_role,
            actor_id=kwargs.pop("actor_id", default_actor_id),
            **kwargs,
        )

    def test_authorized_happy_reconnect_and_replay_path(self):
        fixture = self.fixture()
        first = self.request(fixture)
        repeated = self.request(fixture)
        self.assertEqual(first, repeated)
        self.assertEqual(len(fixture.events), 1)

        path = (
            ("ringing", "guardian_notified"),
            ("connected", "media_ready"),
            ("reconnecting", "media_lost"),
            ("connected", "media_recovered"),
            ("ended", "remote_hangup"),
        )
        for index, (state, reason) in enumerate(path):
            self.transition(
                fixture,
                first["session_id"],
                to_state=state,
                reason_code=reason,
                idempotency_key=f"transition-key-{index:04d}",
            )
        replay = replay_events(fixture.events)
        self.assertEqual(replay["accepted_event_count"], 6)
        self.assertEqual(replay["sessions"][first["session_id"]]["final_state"], "ended")

    def test_unauthorized_invalid_and_terminal_transitions_fail_closed(self):
        fixture = self.fixture()
        with self.assertRaises(EgoCallAuthorizationError):
            fixture.request(
                device_id="device-1",
                guardian_id="guardian-other",
                idempotency_key="unauthorized-key",
                trigger_type="guardian_call",
                initiator="guardian",
                actor_role="guardian",
                actor_id="guardian-other",
            )
        first = self.request(fixture)
        with self.assertRaises(EgoCallAuthorizationError):
            self.transition(
                fixture,
                first["session_id"],
                to_state="ringing",
                reason_code="guardian_notified",
                idempotency_key="unauthorized-transition",
                actor_id="guardian-other",
            )
        with self.assertRaises(EgoCallTransitionError):
            self.transition(
                fixture,
                first["session_id"],
                to_state="reconnecting",
                reason_code="media_lost",
                idempotency_key="invalid-transition",
            )
        with self.assertRaises(EgoCallTransitionError):
            self.transition(
                fixture,
                first["session_id"],
                to_state="bogus",
                reason_code="internal_error",
                idempotency_key="unknown-target-state",
            )
        self.transition(
            fixture,
            first["session_id"],
            to_state="failed",
            reason_code="network_unavailable",
            idempotency_key="failure-transition",
        )
        with self.assertRaises(EgoCallTransitionError):
            self.transition(
                fixture,
                first["session_id"],
                to_state="ringing",
                reason_code="guardian_notified",
                idempotency_key="after-terminal",
            )

    def test_conflicting_idempotency_reuse_fails_closed(self):
        fixture = self.fixture()
        first = self.request(fixture, key="shared-idempotency-key")
        with self.assertRaises(EgoCallTransitionError):
            fixture.request(
                device_id="device-1",
                guardian_id="guardian-1",
                idempotency_key="shared-idempotency-key",
                trigger_type="guardian_call",
                initiator="guardian",
                actor_role="guardian",
                actor_id="guardian-1",
            )

        ringing = self.transition(
            fixture,
            first["session_id"],
            to_state="ringing",
            reason_code="guardian_notified",
            idempotency_key="transition-idempotency-key",
        )
        self.assertEqual(
            ringing,
            self.transition(
                fixture,
                first["session_id"],
                to_state="ringing",
                reason_code="guardian_notified",
                idempotency_key="transition-idempotency-key",
            ),
        )
        with self.assertRaises(EgoCallTransitionError):
            self.transition(
                fixture,
                first["session_id"],
                to_state="connected",
                reason_code="media_ready",
                idempotency_key="transition-idempotency-key",
            )

        duplicate_key = json.loads(json.dumps(ringing))
        duplicate_key["idempotency_key"] = first["idempotency_key"]
        with self.assertRaises(EgoCallTransitionError):
            replay_events([first, duplicate_key])

    def test_endpoint_cannot_forge_call_control_or_rtc_state(self):
        fixture = self.fixture()
        first = self.request(fixture)
        with self.assertRaises(EgoCallAuthorizationError):
            self.transition(
                fixture,
                first["session_id"],
                to_state="ringing",
                reason_code="guardian_notified",
                idempotency_key="forged-ringing",
                actor_role="device",
            )

        with self.assertRaises(EgoCallAuthorizationError):
            self.transition(
                fixture,
                first["session_id"],
                to_state="ringing",
                reason_code="guardian_notified",
                idempotency_key="forged-location-update",
                location_belief_ref={
                    "belief_id": "forged-belief",
                    "state": "Fine",
                    "observed_at_utc": "2026-08-23T08:00:00Z",
                    "age_ms": 0,
                    "radius_m": 0.0,
                },
            )

        ringing = self.transition(
            fixture,
            first["session_id"],
            to_state="ringing",
            reason_code="guardian_notified",
            idempotency_key="legit-ringing",
        )
        with self.assertRaises(EgoCallAuthorizationError):
            self.transition(
                fixture,
                ringing["session_id"],
                to_state="connected",
                reason_code="media_ready",
                idempotency_key="forged-connected",
                actor_role="guardian",
            )

        connected = self.transition(
            fixture,
            ringing["session_id"],
            to_state="connected",
            reason_code="media_ready",
            idempotency_key="legit-connected",
        )
        with self.assertRaises(EgoCallAuthorizationError):
            self.transition(
                fixture,
                connected["session_id"],
                to_state="ended",
                reason_code="remote_hangup",
                idempotency_key="forged-remote-hangup",
                actor_role="device",
            )

    def test_trusted_control_can_close_revoked_session_but_endpoint_cannot(self):
        fixture = self.fixture()
        first = self.request(fixture)
        fixture.revoke_binding(device_id="device-1", guardian_id="guardian-1")

        with self.assertRaises(EgoCallAuthorizationError):
            self.transition(
                fixture,
                first["session_id"],
                to_state="ended",
                reason_code="local_hangup",
                idempotency_key="revoked-endpoint",
                actor_role="device",
            )
        with self.assertRaises(EgoCallAuthorizationError):
            self.transition(
                fixture,
                first["session_id"],
                to_state="ringing",
                reason_code="guardian_notified",
                idempotency_key="revoked-ringing",
            )
        with self.assertRaises(EgoCallAuthorizationError):
            self.transition(
                fixture,
                first["session_id"],
                to_state="failed",
                reason_code="network_unavailable",
                idempotency_key="revoked-rtc-close",
            )
        closed = self.transition(
            fixture,
            first["session_id"],
            to_state="failed",
            reason_code="binding_revoked",
            idempotency_key="trusted-revocation-close",
        )
        self.assertEqual(closed["transition"]["to"], "failed")
        self.assertEqual(closed["asserted_by"]["role"], "call_control")

    def test_revocation_closeout_is_valid_from_every_nonterminal_active_state(self):
        paths = (
            (("ringing", "guardian_notified"),),
            (("ringing", "guardian_notified"), ("connected", "media_ready")),
            (
                ("ringing", "guardian_notified"),
                ("connected", "media_ready"),
                ("reconnecting", "media_lost"),
            ),
        )
        for path_index, path in enumerate(paths):
            with self.subTest(path=path):
                fixture = self.fixture()
                first = self.request(fixture, key=f"revoke-path-{path_index}-request")
                for step_index, (state, reason) in enumerate(path):
                    self.transition(
                        fixture,
                        first["session_id"],
                        to_state=state,
                        reason_code=reason,
                        idempotency_key=f"revoke-path-{path_index}-{step_index}",
                    )
                fixture.revoke_binding(device_id="device-1", guardian_id="guardian-1")
                closed = self.transition(
                    fixture,
                    first["session_id"],
                    to_state="failed",
                    reason_code="binding_revoked",
                    idempotency_key=f"revoke-path-{path_index}-close",
                )
                self.assertEqual(closed["transition"]["to"], "failed")

    def test_guardian_cannot_supply_a_location_belief_on_call_creation(self):
        fixture = self.fixture()
        with self.assertRaises(EgoCallAuthorizationError):
            fixture.request(
                device_id="device-1",
                guardian_id="guardian-1",
                idempotency_key="guardian-forged-location",
                trigger_type="guardian_call",
                initiator="guardian",
                actor_role="guardian",
                actor_id="guardian-1",
                location_belief_ref={
                    "belief_id": "forged-belief",
                    "state": "Fine",
                    "observed_at_utc": "2026-08-23T08:00:00Z",
                    "age_ms": 0,
                    "radius_m": 0.0,
                },
            )

    def test_manual_sos_records_local_first_order_without_waiting_for_gnss_or_ai(self):
        fixture = self.fixture()
        result = fixture.compose_manual_sos(
            device_id="device-1",
            guardian_id="guardian-1",
            sos_event_id="sos-001",
            idempotency_key="manual-sos-key",
            location_belief_ref=None,
        )
        self.assertEqual(result["operation_order"][0], "record_local_fixture_sos")
        self.assertEqual(
            result["local_event"]["local_state"], "recorded_in_memory_fixture"
        )
        self.assertFalse(result["local_event"]["fresh_gnss_required_before_call"])
        self.assertFalse(result["local_event"]["ai_veto_allowed"])
        self.assertEqual(result["call_event"]["transition"]["to"], "requested")
        self.assertEqual(result["remote_call_state"], "requested")
        self.assertEqual(fixture.local_sos_events, [result["local_event"]])

        repeated = fixture.compose_manual_sos(
            device_id="device-1",
            guardian_id="guardian-1",
            sos_event_id="sos-001",
            idempotency_key="manual-sos-key",
            location_belief_ref=None,
        )
        self.assertEqual(repeated, result)
        self.assertEqual(len(fixture.events), 1)
        self.assertEqual(len(fixture.local_sos_events), 1)

        with self.assertRaises(EgoCallTransitionError):
            fixture.compose_manual_sos(
                device_id="device-1",
                guardian_id="guardian-1",
                sos_event_id="sos-001",
                idempotency_key="manual-sos-key",
                location_belief_ref={
                    "belief_id": "different-belief",
                    "state": "Unknown",
                    "observed_at_utc": None,
                    "age_ms": None,
                    "radius_m": None,
                },
            )
        self.assertEqual(len(fixture.local_sos_events), 1)

    def test_manual_sos_remains_local_when_remote_authorization_fails(self):
        fixture = EgoCallFixture(
            authorized_bindings=set(),
            clock=lambda: "2026-08-23T08:00:00Z",
            id_factory=_Ids(),
        )
        result = fixture.compose_manual_sos(
            device_id="device-1",
            guardian_id="guardian-1",
            sos_event_id="sos-local-only",
            idempotency_key="manual-sos-local-only",
            location_belief_ref=None,
        )

        self.assertIsNone(result["call_event"])
        self.assertEqual(result["remote_call_state"], "failed")
        self.assertEqual(
            result["local_event"]["local_state"], "recorded_in_memory_fixture"
        )
        self.assertEqual(result["local_event"]["remote_delivery_state"], "failed")
        self.assertEqual(len(fixture.local_sos_events), 1)
        self.assertEqual(fixture.local_sos_events[0]["event_id"], "sos-local-only")
        self.assertFalse(fixture.local_sos_events[0]["fresh_gnss_required_before_call"])
        self.assertFalse(fixture.local_sos_events[0]["ai_veto_allowed"])

    def test_manual_sos_reports_contract_rejection_without_losing_local_event(self):
        fixture = self.fixture()
        result = fixture.compose_manual_sos(
            device_id="device-1",
            guardian_id="guardian-1",
            sos_event_id="sos-bad-location",
            idempotency_key="manual-sos-bad-location",
            location_belief_ref={
                "belief_id": "bad-belief",
                "state": "Fine",
                "observed_at_utc": "not-a-date",
                "age_ms": 0,
                "radius_m": 20,
            },
        )

        self.assertIsNone(result["call_event"])
        self.assertEqual(result["remote_call_state"], "failed")
        self.assertEqual(result["local_event"]["remote_failure_reason"], "call_request_rejected")
        self.assertEqual(fixture.local_sos_events[0]["remote_delivery_state"], "failed")

    def test_replay_rejects_gaps_conflicts_and_identity_changes(self):
        fixture = self.fixture()
        first = self.request(fixture)
        second = self.transition(
            fixture,
            first["session_id"],
            to_state="ringing",
            reason_code="guardian_notified",
            idempotency_key="ringing-key",
        )
        gap = json.loads(json.dumps(second))
        gap["event_id"] = "gap-event"
        gap["sequence"] = 2
        with self.assertRaises(EgoCallTransitionError):
            replay_events([first, gap])

        conflict = json.loads(json.dumps(first))
        conflict["guardian_id"] = "guardian-other"
        with self.assertRaises(EgoCallTransitionError):
            replay_events([first, conflict])

        changed_identity = json.loads(json.dumps(second))
        changed_identity["guardian_id"] = "guardian-other"
        with self.assertRaises(EgoCallAuthorizationError):
            replay_events([first, changed_identity])

        changed_trigger = json.loads(json.dumps(second))
        changed_trigger["trigger"] = {
            "type": "guardian_call",
            "initiator": "guardian",
            "safety_event_ref": None,
        }
        with self.assertRaises(EgoCallTransitionError):
            replay_events([first, changed_trigger])

        forged_actor = json.loads(json.dumps(second))
        forged_actor["asserted_by"] = {"role": "device", "subject_ref": "device-1"}
        with self.assertRaises(ValidationError):
            replay_events([first, forged_actor])

        forged_service_ref = json.loads(json.dumps(second))
        forged_service_ref["asserted_by"]["subject_ref"] = "attacker-control"
        with self.assertRaises(EgoCallAuthorizationError):
            replay_events([first, forged_service_ref])

        forged_location = json.loads(json.dumps(second))
        forged_location["location_belief_ref"] = {
            "belief_id": "forged-belief",
            "state": "Fine",
            "observed_at_utc": "2026-08-23T08:00:00Z",
            "age_ms": 0,
            "radius_m": 0.0,
        }
        with self.assertRaises(EgoCallAuthorizationError):
            replay_events([first, forged_location])

        backwards_time = json.loads(json.dumps(second))
        backwards_time["event_time_utc"] = "2026-08-22T08:00:00Z"
        with self.assertRaises(EgoCallTransitionError):
            replay_events([first, backwards_time])

        guardian_location = json.loads(json.dumps(first))
        guardian_location["trigger"] = {
            "type": "guardian_call",
            "initiator": "guardian",
            "safety_event_ref": None,
        }
        guardian_location["asserted_by"] = {
            "role": "guardian",
            "subject_ref": "guardian-1",
        }
        guardian_location["location_belief_ref"] = {
            "belief_id": "guardian-forged-belief",
            "state": "Fine",
            "observed_at_utc": "2026-08-23T08:00:00Z",
            "age_ms": 0,
            "radius_m": 0.0,
        }
        with self.assertRaises(ValidationError):
            replay_events([guardian_location])

    def test_live_transition_rejects_clock_rollback(self):
        times = iter(["2026-08-23T08:00:10Z", "2026-08-23T08:00:09Z"])
        fixture = EgoCallFixture(
            authorized_bindings={("device-1", "guardian-1")},
            clock=lambda: next(times),
            id_factory=_Ids(),
        )
        first = self.request(fixture)
        with self.assertRaises(EgoCallTransitionError):
            self.transition(
                fixture,
                first["session_id"],
                to_state="ringing",
                reason_code="guardian_notified",
                idempotency_key="clock-rollback",
            )
        self.assertEqual(fixture.events, [first])

    def test_carried_location_age_advances_with_call_event_time(self):
        times = iter(["2026-08-23T08:00:00Z", "2026-08-23T08:00:12Z"])
        fixture = EgoCallFixture(
            authorized_bindings={("device-1", "guardian-1")},
            clock=lambda: next(times),
            id_factory=_Ids(),
        )
        first = fixture.request(
            device_id="device-1",
            guardian_id="guardian-1",
            idempotency_key="location-age-request",
            trigger_type="device_call",
            initiator="device",
            actor_role="device",
            actor_id="device-1",
            location_belief_ref={
                "belief_id": "belief-1",
                "state": "Fine",
                "observed_at_utc": "2026-08-23T07:59:50Z",
                "age_ms": 10000,
                "radius_m": 20.0,
            },
        )
        ringing = self.transition(
            fixture,
            first["session_id"],
            to_state="ringing",
            reason_code="guardian_notified",
            idempotency_key="location-age-ringing",
        )
        self.assertEqual(ringing["location_belief_ref"]["belief_id"], "belief-1")
        self.assertEqual(ringing["location_belief_ref"]["age_ms"], 22000)
        self.assertEqual(replay_events(fixture.events)["accepted_event_count"], 2)

    def test_location_snapshot_age_must_match_event_time(self):
        fixture = self.fixture()
        with self.assertRaises(EgoCallTransitionError):
            fixture.request(
                device_id="device-1",
                guardian_id="guardian-1",
                idempotency_key="stale-location-age",
                trigger_type="device_call",
                initiator="device",
                actor_role="device",
                actor_id="device-1",
                location_belief_ref={
                    "belief_id": "stale-belief",
                    "state": "Fine",
                    "observed_at_utc": "2020-01-01T00:00:00Z",
                    "age_ms": 0,
                    "radius_m": 20.0,
                },
            )

    def test_schema_still_rejects_uncontracted_secret(self):
        fixture = self.fixture()
        event = self.request(fixture)
        event["signaling"]["rtc_token"] = "secret"
        with self.assertRaises(ValidationError):
            replay_events([event])

    def test_cli_writes_replayable_browser_fixture_without_product_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "pc_simulator.ego_call_demo",
                    "--output-dir",
                    tmp,
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            summary = json.loads((Path(tmp) / "ego_call_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["replay"]["session_count"], 2)
            self.assertEqual(summary["claims"]["state_contract"], "pc_side_verified")
            self.assertEqual(summary["claims"]["rtc_media"], "unverified")
            self.assertEqual(
                summary["claims"]["local_sos_durability"], "unverified"
            )
            sos_events = [
                json.loads(line)
                for line in (Path(tmp) / "ego_call_sos_fixture_trace.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(sos_events[0]["event_id"], "sos-demo")
            self.assertEqual(
                sos_events[0]["local_state"], "recorded_in_memory_fixture"
            )
            browser = (Path(tmp) / "ego_call_fixture.html").read_text(encoding="utf-8")
            self.assertIn("不证明 RTC、设备音频、弱网能力或安全事件持久化", browser)
            self.assertNotIn("rtc_token", browser)
            self.assertNotIn("latitude", browser)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from jsonschema import Draft202012Validator

from pc_simulator.sos_walking_skeleton import (
    SosIdempotencyError,
    SosTriggerRejected,
    SosWalkingSkeleton,
    detect_qualified_long_press,
)


ROOT = Path(__file__).resolve().parents[1]
SAFETY_SCHEMA = json.loads(
    (ROOT / "shared" / "contracts" / "safety_event.schema.json").read_text(
        encoding="utf-8"
    )
)
POLICY_DECISION_SCHEMA = json.loads(
    (ROOT / "shared" / "contracts" / "sensor_policy_decision_v0.schema.json").read_text(
        encoding="utf-8"
    )
)
FORBIDDEN_COORDINATE_KEYS = {
    "lat",
    "latitude",
    "latitude_deg",
    "lon",
    "lng",
    "longitude",
    "longitude_deg",
}


def observation_evidence(event_time_ms: int) -> dict:
    return {
        "observation_id": f"sos-test-{event_time_ms}",
        "source_status": "observed",
        "stream_id": "sos-test-stream",
        "sequence_id": event_time_ms,
        "device_run_id": "sos-test-run",
        "boot_count": 1,
        "timestamp_utc_ns": event_time_ms * 1_000_000,
        "event_time_source": "capture_event",
    }


def long_press(start_ms: int) -> tuple[list[dict], int]:
    samples = [
        {"event_time_ms": start_ms, "pressed": False},
        {"event_time_ms": start_ms + 10, "pressed": True},
        {"event_time_ms": start_ms + 30, "pressed": False},
        {"event_time_ms": start_ms + 60, "pressed": True},
    ]
    return samples, start_ms + 2_110


def assert_no_coordinate_keys(test: unittest.TestCase, value) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            test.assertNotIn(key.lower(), FORBIDDEN_COORDINATE_KEYS)
            assert_no_coordinate_keys(test, child)
    elif isinstance(value, list):
        for child in value:
            assert_no_coordinate_keys(test, child)


class SosWalkingSkeletonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base_time_ms = 1_800_000_000_000
        self.skeleton = SosWalkingSkeleton(
            Path(self.temp.name),
            device_id="wearable-1",
            guardian_id="guardian-1",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def seed_trusted_location(self, *, event_time_ms: int | None = None) -> None:
        event_time_ms = event_time_ms or self.base_time_ms
        self.skeleton.apply_observation(
            {
                "event_type": "gnss_fix",
                "event_time_ms": event_time_ms,
                "latitude_deg": 22.543096,
                "longitude_deg": 114.057865,
                "accuracy_m": 12.0,
                "evidence": observation_evidence(event_time_ms),
            }
        )

    def compose(self, event_id: str = "manual-sos-1", **overrides) -> dict:
        samples, observed_until_ms = long_press(self.base_time_ms + 100)
        values = {
            "event_id": event_id,
            "button_samples": samples,
            "observed_until_ms": observed_until_ms,
            "battery_percent": 72.0,
            "base_online": True,
            "upload_available": True,
            "source_sequence": 41,
        }
        values.update(overrides)
        return self.skeleton.compose_manual_sos(**values)

    def test_healthy_local_first_composition_validates_and_acks(self) -> None:
        self.seed_trusted_location()
        result = self.compose(server_delivery_ack=True)

        Draft202012Validator(SAFETY_SCHEMA).validate(result["safety_event"])
        Draft202012Validator(POLICY_DECISION_SCHEMA).validate(result["policy"])
        self.assertEqual(
            [
                "safety_event_persisted",
                "local_feedback_started",
                "sensor_policy_sos_applied",
                "guardian_alert_attempted",
                "ego_call_attempted",
            ],
            result["composition"]["operation_order"],
        )
        self.assertTrue(result["local_feedback"]["started_after_persist"])
        self.assertEqual("SOS", result["policy"]["policy_mode"])
        self.assertEqual("start", result["policy"]["actions"]["gnss"]["action"])
        self.assertTrue(result["policy"]["actions"]["lte"]["keep_connected"])
        self.assertTrue(result["policy"]["actions"]["location"]["upload_now"])
        self.assertTrue(result["policy"]["actions"]["ego_call"]["start_now"])
        self.assertTrue(result["location"]["policy_requested"])
        self.assertTrue(result["ego_call"]["policy_requested"])
        self.assertTrue(result["ego_call"]["request_attempted"])
        self.assertTrue(result["ego_call"]["request_created"])
        self.assertEqual("server_acknowledged", result["guardian_alert"]["state"])
        self.assertEqual(
            "unverified", result["guardian_alert"]["guardian_human_delivery"]
        )
        self.assertEqual("unverified", result["guardian_alert"]["guardian_human_ack"])
        self.assertEqual("requested", result["ego_call"]["state"])
        self.assertEqual(
            "upload_requested_adapter_not_connected", result["location"]["state"]
        )
        self.assertFalse(result["location"]["adapter_connected"])
        self.assertFalse(result["location"]["upload_executed"])
        self.assertFalse(result["location"]["upload_persisted"])
        snapshot = self.skeleton.outbox.snapshot(
            now_ms=result["trigger"]["triggered_at_ms"] + 4
        )
        self.assertEqual(0, snapshot["queued_count"])
        self.assertEqual(1, len(self.skeleton.call_fixture.events))
        self.assertFalse(result["composition"]["physical_p0_sos_verified"])
        self.assertFalse(result["privacy"]["raw_button_trace_retained"])
        self.assertFalse(result["privacy"]["media_retained"])
        assert_no_coordinate_keys(self, result)
        assert_no_coordinate_keys(self, self.skeleton.outbox.export_storage_document())
        assert_no_coordinate_keys(self, self.skeleton.call_fixture.events)

    def test_offline_branches_do_not_remove_local_event(self) -> None:
        self.seed_trusted_location()
        result = self.compose(
            base_online=False,
            upload_available=False,
            guardian_transport_available=False,
            call_outcome="network_unavailable",
        )

        snapshot = self.skeleton.outbox.snapshot(
            now_ms=result["trigger"]["triggered_at_ms"] + 3
        )
        self.assertEqual("persisted", result["local_event"]["state"])
        self.assertEqual("retry_wait", result["guardian_alert"]["state"])
        self.assertEqual("failed", result["ego_call"]["state"])
        self.assertEqual("network_unavailable", result["ego_call"]["reason_code"])
        self.assertEqual(1, snapshot["queued_count"])
        self.assertEqual("manual-sos-1", snapshot["records"][0]["event_id"])

    def test_guardian_call_decline_is_independent_from_alert_retention(self) -> None:
        self.seed_trusted_location()
        result = self.compose(
            guardian_transport_available=True,
            server_delivery_ack=False,
            call_outcome="declined",
        )

        self.assertEqual("awaiting_positive_ack", result["guardian_alert"]["state"])
        self.assertEqual("ended", result["ego_call"]["state"])
        self.assertEqual("declined", result["ego_call"]["reason_code"])
        snapshot = self.skeleton.outbox.snapshot(
            now_ms=result["trigger"]["triggered_at_ms"] + 3
        )
        self.assertEqual(1, snapshot["queued_count"])
        self.assertEqual(2, len(self.skeleton.call_fixture.events))

    def test_same_event_replay_is_idempotent_and_conflict_fails_closed(self) -> None:
        self.seed_trusted_location()
        first = self.compose(guardian_transport_available=False)
        repeated = self.compose(guardian_transport_available=False)

        self.assertFalse(first["composition"]["idempotent_replay"])
        self.assertTrue(repeated["composition"]["idempotent_replay"])
        self.assertEqual(first["local_event"], repeated["local_event"])
        self.assertEqual(1, len(self.skeleton.call_fixture.events))
        snapshot = self.skeleton.outbox.snapshot(
            now_ms=first["trigger"]["triggered_at_ms"] + 3
        )
        self.assertEqual(1, snapshot["queued_count"])
        self.assertEqual(1, snapshot["metrics"]["enqueue_count"])

        with self.assertRaises(SosIdempotencyError):
            self.compose(
                guardian_transport_available=False,
                battery_percent=71.0,
            )

    def test_outbox_identity_and_call_idempotency_key_survive_reopen(self) -> None:
        self.seed_trusted_location()
        first = self.compose(guardian_transport_available=False)
        first_call = self.skeleton.call_fixture.events[0]
        self.skeleton = SosWalkingSkeleton(
            Path(self.temp.name),
            device_id="wearable-1",
            guardian_id="guardian-1",
        )

        replayed = self.compose(guardian_transport_available=False)
        replayed_call = self.skeleton.call_fixture.events[0]

        self.assertTrue(replayed["composition"]["durable_outbox_replay"])
        self.assertEqual(first["local_event"], replayed["local_event"])
        self.assertEqual(first["safety_event"], replayed["safety_event"])
        self.assertEqual(first_call["idempotency_key"], replayed_call["idempotency_key"])
        self.assertEqual(
            first_call["location_belief_ref"], replayed_call["location_belief_ref"]
        )
        self.assertFalse(replayed["composition"]["remote_session_durability_verified"])
        self.assertEqual("retry_wait", replayed["guardian_alert"]["state"])
        self.assertFalse(replayed["guardian_alert"]["current_event_attempted"])
        snapshot = self.skeleton.outbox.snapshot(
            now_ms=replayed["trigger"]["triggered_at_ms"] + 3
        )
        self.assertEqual(1, snapshot["queued_count"])
        self.assertEqual(1, snapshot["metrics"]["enqueue_count"])
        self.assertEqual(1, snapshot["metrics"]["duplicate_enqueue_count"])

    def test_second_sos_retriggers_current_location_call_and_settles_prior_due(self) -> None:
        self.seed_trusted_location()
        self.compose(
            event_id="manual-sos-1",
            guardian_transport_available=False,
            call_outcome="network_unavailable",
        )
        samples, observed_until_ms = long_press(self.base_time_ms + 5_000)

        second = self.compose(
            event_id="manual-sos-2",
            button_samples=samples,
            observed_until_ms=observed_until_ms,
            source_sequence=42,
            guardian_transport_available=True,
            server_delivery_ack=True,
            call_outcome="requested",
        )

        Draft202012Validator(POLICY_DECISION_SCHEMA).validate(second["policy"])
        self.assertFalse(second["policy"]["transition"]["changed"])
        self.assertIn(
            "manual_sos_retrigger", second["policy"]["transition"]["reason_codes"]
        )
        self.assertTrue(second["policy"]["actions"]["location"]["upload_now"])
        self.assertTrue(second["policy"]["actions"]["ego_call"]["start_now"])
        self.assertTrue(second["location"]["policy_requested"])
        self.assertTrue(second["ego_call"]["policy_requested"])
        self.assertTrue(second["ego_call"]["request_attempted"])
        self.assertEqual("requested", second["ego_call"]["state"])
        self.assertEqual("server_acknowledged", second["guardian_alert"]["state"])
        self.assertTrue(second["guardian_alert"]["current_event_attempted"])
        self.assertEqual(1, second["guardian_alert"]["prior_due_attempts_processed"])
        records = {
            item["event_id"]: item
            for item in self.skeleton.outbox.snapshot(
                now_ms=observed_until_ms + 3
            )["records"]
        }
        self.assertEqual("awaiting_positive_ack", records["manual-sos-1"]["send_state"])
        self.assertNotIn("manual-sos-2", records)
        self.assertNotIn(
            "attempt_started", {item["send_state"] for item in records.values()}
        )

    def test_concurrent_duplicate_sos_is_serialized_and_idempotent(self) -> None:
        def invoke() -> dict:
            return self.compose(guardian_transport_available=False)

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: invoke(), range(2)))

        self.assertEqual(
            [False, True],
            sorted(
                (item["composition"]["idempotent_replay"] for item in results),
                reverse=False,
            ),
        )
        self.assertEqual(1, len(self.skeleton.call_fixture.events))
        snapshot = self.skeleton.outbox.snapshot(
            now_ms=results[0]["trigger"]["triggered_at_ms"] + 3
        )
        self.assertEqual(1, snapshot["queued_count"])
        self.assertEqual(1, snapshot["metrics"]["enqueue_count"])

    def test_location_snapshot_failure_cannot_veto_persist_alert_or_call(self) -> None:
        with mock.patch.object(
            self.skeleton.location_engine,
            "snapshot",
            side_effect=RuntimeError("injected location dependency failure"),
        ):
            result = self.compose()

        self.assertEqual("persisted", result["local_event"]["state"])
        self.assertEqual("started", result["local_feedback"]["state"])
        self.assertEqual("failed", result["policy"]["state"])
        self.assertEqual(
            "LOCATION_SNAPSHOT_ERROR",
            result["location"]["belief_snapshot"]["reason_code"],
        )
        self.assertEqual("Unknown", result["location"]["belief_ref"]["state"])
        self.assertEqual(0.0, result["guardian_view"]["location"]["confidence"])
        self.assertEqual("awaiting_positive_ack", result["guardian_alert"]["state"])
        self.assertEqual("requested", result["ego_call"]["state"])
        self.assertTrue(result["ego_call"]["request_attempted"])
        self.assertEqual(1, len(self.skeleton.call_fixture.events))
        self.assertEqual(
            1,
            self.skeleton.outbox.snapshot(
                now_ms=result["trigger"]["triggered_at_ms"] + 3
            )["queued_count"],
        )
        assert_no_coordinate_keys(self, result)

    def test_policy_and_guardian_branch_failures_are_isolated(self) -> None:
        original_evaluate = self.skeleton.sensor_policy.evaluate

        def fail_sos_policy(*args, **kwargs):
            if kwargs.get("event_type") == "sos":
                raise RuntimeError("injected policy failure")
            return original_evaluate(*args, **kwargs)

        with mock.patch.object(
            self.skeleton.sensor_policy, "evaluate", side_effect=fail_sos_policy
        ):
            policy_failed = self.compose(event_id="policy-failed")

        self.assertEqual("persisted", policy_failed["local_event"]["state"])
        self.assertEqual("failed", policy_failed["policy"]["state"])
        self.assertTrue(policy_failed["location"]["policy_requested"])
        self.assertEqual("awaiting_positive_ack", policy_failed["guardian_alert"]["state"])
        self.assertEqual("requested", policy_failed["ego_call"]["state"])

        samples, observed_until_ms = long_press(self.base_time_ms + 5_000)
        with mock.patch.object(
            self.skeleton,
            "_attempt_guardian_alert",
            side_effect=RuntimeError("injected Guardian branch failure"),
        ):
            guardian_failed = self.compose(
                event_id="guardian-failed",
                button_samples=samples,
                observed_until_ms=observed_until_ms,
                source_sequence=42,
            )

        self.assertEqual("persisted", guardian_failed["local_event"]["state"])
        self.assertEqual("failed", guardian_failed["guardian_alert"]["state"])
        self.assertEqual("GUARDIAN_ALERT_BRANCH_ERROR", guardian_failed["guardian_alert"]["error_code"])
        self.assertEqual("requested", guardian_failed["ego_call"]["state"])
        self.assertTrue(guardian_failed["ego_call"]["request_attempted"])

    def test_low_battery_ai_and_camera_cannot_veto_manual_sos(self) -> None:
        self.seed_trusted_location()
        result = self.compose(
            battery_percent=5.0,
            ai_recommendation="do_not_escalate",
            camera_available=False,
        )

        self.assertEqual("SOS", result["policy"]["policy_mode"])
        self.assertEqual("critical", result["guardian_view"]["battery_state"])
        self.assertEqual(5.0, result["guardian_view"]["battery_percent"])
        self.assertEqual(
            result["safety_event"]["context"]["battery_percent"],
            result["guardian_view"]["battery_percent"],
        )
        self.assertTrue(result["policy"]["conditions"]["low_battery"])
        self.assertTrue(result["policy"]["conditions"]["critical_battery"])
        self.assertTrue(result["policy"]["actions"]["lte"]["keep_connected"])
        self.assertTrue(result["policy"]["actions"]["ego_call"]["start_now"])
        self.assertFalse(result["policy"]["actions"]["camera"]["requested"])
        self.assertTrue(result["non_veto_guards"]["manual_sos_non_vetoable"])
        self.assertFalse(result["non_veto_guards"]["low_battery_vetoed"])
        self.assertTrue(
            result["non_veto_guards"]["ai_advice_present_but_non_authoritative"]
        )

    def test_unknown_battery_is_null_and_cannot_veto_manual_sos(self) -> None:
        result = self.compose(battery_percent=None)

        Draft202012Validator(SAFETY_SCHEMA).validate(result["safety_event"])
        self.assertIsNone(result["safety_event"]["context"]["battery_percent"])
        self.assertIsNone(result["guardian_view"]["battery_percent"])
        self.assertEqual("unknown", result["guardian_view"]["battery_state"])
        self.assertEqual("SOS", result["policy"]["policy_mode"])
        self.assertEqual("persisted", result["local_event"]["state"])
        self.assertEqual("started", result["local_feedback"]["state"])
        self.assertTrue(result["location"]["policy_requested"])
        self.assertTrue(result["ego_call"]["request_attempted"])

        schema_type = SAFETY_SCHEMA["properties"]["context"]["properties"][
            "battery_percent"
        ]["type"]
        self.assertEqual(["number", "null"], schema_type)

    def test_no_location_still_persists_alerts_and_requests_call(self) -> None:
        result = self.compose()

        self.assertEqual("Unknown", result["location"]["belief_ref"]["state"])
        self.assertIsNone(result["location"]["belief_ref"]["observed_at_utc"])
        self.assertIsNone(result["location"]["belief_ref"]["age_ms"])
        self.assertIsNone(result["location"]["belief_ref"]["radius_m"])
        self.assertEqual("upload_requested_no_trusted_belief", result["location"]["state"])
        self.assertFalse(result["location"]["adapter_connected"])
        self.assertFalse(result["location"]["upload_executed"])
        self.assertFalse(result["location"]["upload_persisted"])
        self.assertTrue(result["policy"]["actions"]["location"]["upload_now"])
        self.assertEqual("requested", result["ego_call"]["state"])
        snapshot = self.skeleton.outbox.snapshot(
            now_ms=result["trigger"]["triggered_at_ms"] + 3
        )
        self.assertEqual(1, snapshot["queued_count"])
        assert_no_coordinate_keys(self, result)

    def test_short_or_bouncing_press_is_rejected_before_persistence(self) -> None:
        samples = [
            {"event_time_ms": 10, "pressed": True},
            {"event_time_ms": 30, "pressed": False},
            {"event_time_ms": 60, "pressed": True},
            {"event_time_ms": 100, "pressed": False},
        ]
        with self.assertRaises(SosTriggerRejected):
            detect_qualified_long_press(samples, observed_until_ms=500)
        self.assertEqual(0, self.skeleton.outbox.snapshot(now_ms=500)["queued_count"])

    def test_long_press_debounce_boundary_is_explicit(self) -> None:
        start_ms = 100
        exact_boundary = [
            {"event_time_ms": start_ms, "pressed": False},
            {"event_time_ms": start_ms + 10, "pressed": True},
            # Stable press begins at 160; threshold and debounced release both
            # land at 2160, so the safety-biased equality qualifies.
            {"event_time_ms": 2_110, "pressed": False},
        ]
        qualified = detect_qualified_long_press(
            exact_boundary, observed_until_ms=2_160
        )
        self.assertEqual(2_160, qualified["triggered_at_ms"])

        released_before_boundary = [
            {"event_time_ms": start_ms, "pressed": False},
            {"event_time_ms": start_ms + 10, "pressed": True},
            {"event_time_ms": 2_109, "pressed": False},
        ]
        with self.assertRaises(SosTriggerRejected):
            detect_qualified_long_press(
                released_before_boundary, observed_until_ms=2_160
            )


if __name__ == "__main__":
    unittest.main()

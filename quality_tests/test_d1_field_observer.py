from __future__ import annotations

from contextlib import redirect_stdout
from http.server import ThreadingHTTPServer
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest

from pc_simulator import protocol
from scripts import observe_d1_field_run as observer
from server import message_hub


def sample(
    *,
    freshness_s: float = 5,
    seq: int = 10,
    success_count: int = 4,
    failure_count: int = 0,
    location_count: int = 8,
    power_count: int = 3,
    coordinate: bool = False,
) -> dict:
    return {
        "collected_at": "2026-07-04T08:00:00+00:00",
        "ok": True,
        "device_id": "ego-link-r1-connectivity-001",
        "d1_status": "estimate_visible",
        "d1_gate_status": "ready" if coordinate else "blocked",
        "d1_gate_next_action": "run_d1_field_kit_and_postrun_collector"
        if coordinate
        else "move_outdoors_until_two_coordinate_uploads_are_seen",
        "last_device_upload_at": "2026-07-04T08:00:00+00:00",
        "last_location_upload_at": "2026-07-04T08:00:00+00:00",
        "freshness_s": freshness_s,
        "last_seq": seq,
        "map_mode": "coordinate" if coordinate else "estimate_without_coordinate",
        "lat": 22.5 if coordinate else None,
        "lon": 113.9 if coordinate else None,
        "coordinate_seen": coordinate,
        "track_point_count": 2 if coordinate else 0,
        "required_track_points": 2,
        "coordinate_event_count": 2 if coordinate else 0,
        "coordinate_location_event_count": location_count,
        "missing_coordinate_event_count": max(0, location_count - (2 if coordinate else 0)),
        "latest_coordinate_seq": seq if coordinate else None,
        "latest_missing_coordinate_reason": None if coordinate else "gnss_no_fix",
        "coordinate_operator_hint": "enough_coordinate_uploads_for_d1_map_gate"
        if coordinate
        else "move_outdoors_until_two_coordinate_uploads_are_seen",
        "raw_post_attempt_count": success_count + failure_count,
        "raw_post_success_count": success_count,
        "raw_post_failure_count": failure_count,
        "location_event_count": location_count,
        "power_sample_count": power_count,
        "battery_mv": 4276,
        "soc_pct": 92,
        "power_evidence_status": "measured",
        "gnss_seen": True,
        "gnss_fix": None,
        "gnss_state": "unknown",
        "cell_lte_seen": True,
        "cell_rat": "LTE",
        "cell_id": "180571649",
        "cell_registration_state": "registered_home",
        "cell_pdp_state": "active",
        "imu_seen": True,
        "imu_evidence_status": "mock",
    }


def api_state(seq: int, *, success_count: int, location_count: int, power_count: int) -> dict:
    return {
        "devices": [
            {
                "device_id": "ego-link-r1-connectivity-001",
                "d1_link": {
                    "status": "estimate_visible",
                    "acceptance_gate": {
                        "status": "ready",
                        "track_points": 2,
                        "required_track_points": 2,
                        "next_action": "run_d1_field_kit_and_postrun_collector",
                    },
                    "location_estimate": {
                        "state": "Predicted",
                        "reason": "unit",
                        "updated_at": f"2026-07-04T08:00:{seq:02d}+00:00",
                    },
                    "map_surface": {
                        "mode": "memory_coordinate",
                        "lat": 22.5,
                        "lon": 113.9,
                        "coordinate_diagnostics": {
                            "coordinate_event_count": 2,
                            "location_event_count": location_count,
                            "missing_coordinate_event_count": max(0, location_count - 2),
                            "latest_coordinate_seq": seq,
                            "latest_missing_reason": "gnss_no_fix",
                            "operator_hint": "enough_coordinate_uploads_for_d1_map_gate",
                        },
                        "trajectory": {"point_count": 2},
                    },
                    "upload_freshness": {
                        "last_device_upload_at": f"2026-07-04T08:00:{seq:02d}+00:00",
                        "last_location_upload_at": f"2026-07-04T08:00:{seq:02d}+00:00",
                        "freshness_s": 5,
                        "last_seq": seq,
                    },
                    "uplink_metrics": {
                        "raw_post_attempt_count": success_count,
                        "raw_post_success_count": success_count,
                        "raw_post_failure_count": 0,
                        "location_event_count": location_count,
                    },
                    "power_curve": {
                        "sample_count": power_count,
                        "latest_sample_at": f"2026-07-04T08:00:{seq:02d}+00:00",
                    },
                    "evidence": {
                        "components": {
                            "power": {
                                "battery_mv": 4200 - seq,
                                "soc_pct": 90,
                                "evidence_status": "measured",
                            },
                            "gnss": {"seen": True, "fix": False, "state": "no_fix"},
                            "cell_lte": {
                                "seen": True,
                                "rat": "LTE",
                                "cell_id": "180571649",
                                "registration_state": "registered_home",
                                "pdp_state": "active",
                            },
                            "imu": {"seen": True, "evidence_status": "mock"},
                        }
                    },
                },
            }
        ]
    }


class D1FieldObserverTests(unittest.TestCase):
    def test_evaluate_observation_passes_fresh_periodic_upload_without_claims(self) -> None:
        samples = [
            sample(seq=20, success_count=7, location_count=12, power_count=5),
            sample(seq=41, success_count=9, location_count=13, power_count=6),
        ]

        report = observer.evaluate_observation(
            samples=samples,
            run_id="D1-FIELD-unit",
            hub_url="http://127.0.0.1:8790",
            device_id="ego-link-r1-connectivity-001",
            max_stale_sec=180,
            poll_interval_sec=60,
            duration_minutes=2,
        )

        self.assertEqual(report["result"], "WARN")
        self.assertIn("d1_coordinate_not_observed", report["warnings"])
        self.assertNotIn("d1_location_event_count_did_not_advance", report["warnings"])
        self.assertEqual(report["summary"]["raw_post_success_delta"], 2)
        self.assertEqual(report["summary"]["power_sample_count_delta"], 1)
        self.assertEqual(report["summary"]["coordinate_event_count_start"], 0)
        self.assertEqual(report["summary"]["coordinate_event_count_end"], 0)
        self.assertEqual(report["summary"]["track_point_count_end"], 0)
        self.assertFalse(report["scope"]["commands_sent"])
        self.assertFalse(report["scope"]["hardware_contacted_directly"])
        self.assertFalse(report["scope"]["location_accuracy_claimed"])

    def test_summarize_sample_records_coordinate_diagnostics(self) -> None:
        state = api_state(7, success_count=5, location_count=8, power_count=3)

        result = observer.summarize_sample(
            state,
            device_id="ego-link-r1-connectivity-001",
            collected_at="2026-07-04T08:00:07+00:00",
        )

        self.assertEqual(result["d1_gate_status"], "ready")
        self.assertEqual(result["track_point_count"], 2)
        self.assertEqual(result["coordinate_event_count"], 2)
        self.assertEqual(result["coordinate_location_event_count"], 8)
        self.assertEqual(result["missing_coordinate_event_count"], 6)
        self.assertEqual(result["latest_coordinate_seq"], 7)
        self.assertEqual(result["latest_missing_coordinate_reason"], "gnss_no_fix")
        self.assertEqual(result["coordinate_operator_hint"], "enough_coordinate_uploads_for_d1_map_gate")

    def test_evaluate_observation_fails_when_no_successful_samples(self) -> None:
        report = observer.evaluate_observation(
            samples=[{"ok": False, "error": "timeout"}],
            run_id="D1-FIELD-fail",
            hub_url="http://127.0.0.1:8790",
            device_id="ego-link-r1-connectivity-001",
            max_stale_sec=180,
            poll_interval_sec=60,
            duration_minutes=1,
        )

        self.assertEqual(report["result"], "FAIL")
        self.assertIn("d1_no_successful_samples", report["errors"])
        self.assertEqual(report["summary"]["fetch_error_count"], 1)

    def test_cli_writes_reports_against_token_protected_local_server(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            token_file = tmp_path / "token.txt"
            token_file.write_text("observer-secret-token\n", encoding="utf-8")
            output_dir = tmp_path / "observation"
            store = message_hub.MessageHubStore(tmp_path / "hub.db")
            store.ingest(
                "ego-link-r1-connectivity-001",
                "telemetry",
                protocol.event_message(
                    "ego-link-r1-connectivity-001",
                    "2026-07-04T08:00:01Z",
                    1,
                    "location_observation",
                    "normal",
                    source="d1_observer_fixture",
                    source_status="mock",
                    gnss={"fix": False, "state": "unknown"},
                    cell={"rat": "LTE", "cell_id": "mock-cell-d1", "registration_state": "registered_home"},
                    lte={"registered": True, "pdp_active": True, "reason_code": "LTE_READY"},
                    imu={"motion": None, "confidence": None, "evidence_status": "mock"},
                    power={"battery_mv": 4276, "soc_pct": 92, "evidence_status": "measured"},
                    transport={"type": "lte"},
                    reliability={
                        "network": {
                            "raw_post_attempt_count": 2,
                            "raw_post_success_count": 2,
                            "raw_post_failure_count": 0,
                        }
                    },
                    location_belief={
                        "state": "Unknown",
                        "source": ["cell", "lte", "imu", "power"],
                        "reason": "cell_observation_without_position_fix",
                    },
                ),
            )
            server = ThreadingHTTPServer(("127.0.0.1", 0), message_hub.make_handler(store, token="observer-secret-token"))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    exit_code = observer.main(
                        [
                            "--hub-url",
                            base_url,
                            "--token-file",
                            str(token_file),
                            "--output-dir",
                            str(output_dir),
                            "--run-id",
                            "D1-FIELD-observer-unit",
                            "--device-id",
                            "ego-link-r1-connectivity-001",
                            "--sample-count",
                            "1",
                            "--poll-interval-sec",
                            "0",
                            "--duration-minutes",
                            "1",
                            "--json",
                        ]
                    )
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertIn(payload["result"], {"PASS", "WARN"})
            self.assertNotIn("observer-secret-token", stdout.getvalue())
            self.assertTrue((output_dir / observer.REPORT_JSON).is_file())
            self.assertTrue((output_dir / observer.REPORT_MARKDOWN).is_file())
            self.assertTrue((output_dir / observer.SAMPLES_JSONL).is_file())
            self.assertTrue((output_dir / observer.STATUS_JSON).is_file())
            self.assertEqual(payload["summary"]["successful_sample_count"], 1)
            status = json.loads((output_dir / observer.STATUS_JSON).read_text(encoding="utf-8"))
            self.assertEqual(status["status"], "completed")
            self.assertEqual(status["result"], payload["result"])
            self.assertEqual(status["sample_count"], 1)
            self.assertFalse(status["scope"]["commands_sent"])

    def test_observer_writes_samples_incrementally_during_poll_loop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "observation"
            samples_path = output_dir / observer.SAMPLES_JSONL
            status_path = output_dir / observer.STATUS_JSON
            calls = 0
            original_fetch = observer.d1_web.fetch_json

            def fake_fetch_json(*args, **kwargs) -> dict:
                nonlocal calls
                if calls == 1:
                    self.assertTrue(samples_path.is_file())
                    lines = [line for line in samples_path.read_text(encoding="utf-8").splitlines() if line]
                    self.assertEqual(len(lines), 1)
                    self.assertIn('"last_seq": 1', lines[0])
                    self.assertTrue(status_path.is_file())
                    status = json.loads(status_path.read_text(encoding="utf-8"))
                    self.assertEqual(status["status"], "running")
                    self.assertEqual(status["sample_count"], 1)
                    self.assertEqual(status["latest_seq"], 1)
                calls += 1
                return api_state(calls, success_count=10 + calls, location_count=20 + calls, power_count=30 + calls)

            observer.d1_web.fetch_json = fake_fetch_json
            try:
                report = observer.observe_field_run(
                    hub_url="http://127.0.0.1:8790",
                    token=None,
                    output_dir=output_dir,
                    run_id="D1-FIELD-incremental",
                    device_id="ego-link-r1-connectivity-001",
                    duration_minutes=1,
                    poll_interval_sec=0,
                    max_stale_sec=180,
                    timeout=1,
                    sample_count=2,
                )
            finally:
                observer.d1_web.fetch_json = original_fetch

            lines = [json.loads(line) for line in samples_path.read_text(encoding="utf-8").splitlines() if line]
            final_status = json.loads(status_path.read_text(encoding="utf-8"))

        self.assertEqual(calls, 2)
        self.assertEqual(report["sample_write_mode"], "incremental_jsonl")
        self.assertEqual(report["status_path"], str(status_path))
        self.assertEqual(report["summary"]["successful_sample_count"], 2)
        self.assertEqual([line["last_seq"] for line in lines], [1, 2])
        self.assertEqual(final_status["status"], "completed")
        self.assertEqual(final_status["result"], report["result"])
        self.assertEqual(final_status["sample_count"], 2)
        self.assertEqual(final_status["latest_seq"], 2)


if __name__ == "__main__":
    unittest.main()

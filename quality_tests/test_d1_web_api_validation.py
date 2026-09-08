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
from scripts import validate_d1_web_api as d1_web
from server import message_hub


def d1_state() -> dict:
    return {
        "devices": [
            {
                "device_id": "ego-link-001",
                "d1_link": {
                    "status": "estimate_visible",
                    "acceptance_gate": {
                        "status": "ready",
                        "headline": "Ready for D1 field acceptance run",
                        "track_points": 2,
                        "required_track_points": 2,
                        "blockers": [],
                        "warnings": [],
                        "next_action": "run_d1_field_kit_and_postrun_collector",
                    },
                    "location_estimate": {
                        "available": True,
                        "state": "Coarse",
                        "accuracy_claim": "none",
                    },
                    "map_surface": {
                        "visible": True,
                        "mode": "coordinate",
                        "review_mode": "local_no_key",
                        "surface_role": "d2_d5_evidence_review",
                        "lat": 31.2,
                        "lon": 121.4,
                        "provider": {
                            "mode": "none",
                            "status": "not_configured",
                            "blocking_d1": False,
                        },
                        "layers": {
                            "current_point": True,
                            "trajectory": True,
                            "reference_points": False,
                            "provider_tiles": False,
                        },
                        "points": [
                            {"lat": 31.2, "lon": 121.4, "server_received_at": "2026-07-04T00:00:01Z", "seq": 1},
                            {"lat": 31.2005, "lon": 121.4006, "server_received_at": "2026-07-04T00:00:02Z", "seq": 2},
                        ],
                        "reference_points": [],
                        "privacy": {
                            "coordinate_visibility": "authenticated_runtime_only",
                            "static_report_policy": "bounded_summary_no_raw_coordinates",
                            "training_allowed": False,
                        },
                        "accuracy_claim": "none",
                        "trajectory": {"point_count": 2, "visible": True, "source": "recent_location_events"},
                    },
                    "upload_freshness": {"last_location_upload_at": "2026-07-04T00:00:01Z"},
                    "uplink_metrics": {
                        "basis": "device_raw_post_counters",
                        "location_event_count": 2,
                        "raw_post_attempt_count": 2,
                        "raw_post_success_count": 2,
                        "raw_post_failure_count": 0,
                        "raw_post_success_rate": 1.0,
                    },
                    "power_curve": {
                        "sample_count": 3,
                        "delta_battery_mv": -30,
                        "delta_soc_pct": -8.0,
                        "battery_life_claim": "none",
                    },
                    "evidence": {
                        "components": {
                            "gnss": {"seen": True},
                            "cell_lte": {"seen": True},
                            "imu": {"seen": True},
                            "power": {"seen": True},
                        }
                    },
                    "non_claims": ["location_accuracy_not_claimed", "battery_life_not_claimed"],
                },
            }
        ]
    }


def dashboard_html() -> str:
    return (
        "<html>D1 Link Through d1LinkPanel D1 Acceptance Gate d1AcceptanceBadge "
        "Upload Success Location Uploads Power Curve data-d1-map-mode data-map-review-mode "
        "data-map-provider-mode map-track Track points No-key Local Map Provider Status D2 Reference</html>"
    )


class D1WebApiValidationTests(unittest.TestCase):
    def test_evaluate_passes_d1_web_surface_without_product_claims(self) -> None:
        report = d1_web.evaluate_d1_web_api(
            health={"ok": True, "service": "egolink-message-hub"},
            state=d1_state(),
            dashboard_html=dashboard_html(),
            hub_url="http://127.0.0.1:8790",
            review_id="d1-unit",
        )

        self.assertEqual(report["result"], "PASS")
        self.assertFalse(report["scope"]["hardware_contacted"])
        self.assertFalse(report["scope"]["commands_sent"])
        self.assertFalse(report["scope"]["location_accuracy_claimed"])
        self.assertFalse(report["scope"]["battery_life_claimed"])
        self.assertEqual(report["d1"]["acceptance_gate"]["status"], "ready")
        self.assertTrue(all(item["status"] == "PASS" for item in report["gates"]))

    def test_missing_d1_metrics_fails_explainably(self) -> None:
        state = d1_state()
        state["devices"][0]["d1_link"]["uplink_metrics"]["location_event_count"] = 0
        state["devices"][0]["d1_link"]["power_curve"]["sample_count"] = 0

        report = d1_web.evaluate_d1_web_api(
            health={"ok": True},
            state=state,
            dashboard_html=dashboard_html(),
            hub_url="http://127.0.0.1:8790",
            review_id="d1-missing-metrics",
        )

        self.assertEqual(report["result"], "FAIL")
        self.assertIn("d1_location_upload_count_missing", report["errors"])
        self.assertIn("d1_power_sample_count_missing", report["errors"])

    def test_missing_map_trajectory_fails_d1_gate(self) -> None:
        state = d1_state()
        state["devices"][0]["d1_link"]["map_surface"]["points"] = []
        state["devices"][0]["d1_link"]["map_surface"]["trajectory"]["point_count"] = 0

        report = d1_web.evaluate_d1_web_api(
            health={"ok": True},
            state=state,
            dashboard_html=dashboard_html(),
            hub_url="http://127.0.0.1:8790",
            review_id="d1-missing-trajectory",
        )

        self.assertEqual(report["result"], "FAIL")
        self.assertIn("d1_map_trajectory_points_missing", report["errors"])
        self.assertIn("d1_map_trajectory_missing", report["errors"])

    def test_cli_writes_report_against_token_protected_local_server(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            token_file = tmp_path / "token.txt"
            token_file.write_text("secret-token\n", encoding="utf-8")
            output_dir = tmp_path / "review"
            store = message_hub.MessageHubStore(tmp_path / "hub.db")
            store.ingest(
                "ego-link-001",
                "heartbeat",
                protocol.status_message(
                    "ego-link-001",
                    "2026-07-04T00:00:00Z",
                    0,
                    battery=90,
                    battery_mv=3990,
                    link_type="lte",
                    guard_mode="child_safety",
                    queue_size=0,
                ),
            )
            store.ingest(
                "ego-link-001",
                "telemetry",
                protocol.event_message(
                    "ego-link-001",
                    "2026-07-04T00:00:01Z",
                    1,
                    "location_report",
                    "normal",
                    source="d1_cli_fixture",
                    source_status="mock",
                    fix=False,
                    gnss_state="no_fix",
                    power={"battery_mv": 3980, "soc_pct": 87, "evidence_status": "mock"},
                    transport={"type": "lte"},
                    reliability={"network": {"raw_post_attempt_count": 1, "raw_post_success_count": 1, "raw_post_failure_count": 0}},
                ),
            )
            store.ingest(
                "ego-link-001",
                "telemetry",
                protocol.event_message(
                    "ego-link-001",
                    "2026-07-04T00:00:01.500Z",
                    11,
                    "location_report",
                    "normal",
                    source="d1_cli_fixture",
                    source_status="mock",
                    fix=True,
                    lat=31.2,
                    lon=121.4,
                    gnss_state="fix",
                    power={"battery_mv": 3970, "soc_pct": 85, "evidence_status": "mock"},
                    transport={"type": "lte"},
                ),
            )
            store.ingest(
                "ego-link-001",
                "telemetry",
                protocol.event_message(
                    "ego-link-001",
                    "2026-07-04T00:00:02Z",
                    2,
                    "location_observation",
                    "normal",
                    source="d1_cli_fixture",
                    source_status="mock",
                    lat=31.2005,
                    lon=121.4006,
                    gnss={"fix": False, "state": "no_fix"},
                    cell={"rat": "LTE", "cell_id": "mock-cell-d1", "registration_state": "registered"},
                    lte={"registered": True, "pdp_active": True, "reason_code": "LTE_READY"},
                    imu={"motion": "stationary", "confidence": 0.9, "evidence_status": "mock"},
                    power={"battery_mv": 3960, "soc_pct": 82, "evidence_status": "mock"},
                    transport={"type": "lte"},
                    reliability={"network": {"raw_post_attempt_count": 2, "raw_post_success_count": 2, "raw_post_failure_count": 0}},
                    location_belief={
                        "state": "Coarse",
                        "radius_m": 250,
                        "confidence": 0.62,
                        "source": ["cell_lte"],
                        "reason": "d1_cli_fixture_estimate",
                    },
                ),
            )
            requested_paths: list[str] = []

            class RecordingHandler(message_hub.make_handler(store, token="secret-token")):
                def do_GET(self) -> None:
                    requested_paths.append(self.path)
                    super().do_GET()

            server = ThreadingHTTPServer(("127.0.0.1", 0), RecordingHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    exit_code = d1_web.main(
                        [
                            "--hub-url",
                            base_url,
                            "--token-file",
                            str(token_file),
                            "--output-dir",
                            str(output_dir),
                            "--review-id",
                            "d1-cli-unit",
                            "--json",
                        ]
                    )
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertIn("/engineering", requested_paths)
            self.assertNotIn("/", requested_paths)
            self.assertEqual(payload["result"], "PASS")
            self.assertNotIn("secret-token", stdout.getvalue())
            self.assertTrue((output_dir / "d1_web_api_report.json").is_file())
            self.assertTrue((output_dir / "d1_web_api_report.md").is_file())
            self.assertEqual(payload["d1"]["uplink_metrics"]["raw_post_success_rate"], 1.0)
            self.assertEqual(payload["d1"]["power_curve"]["sample_count"], 4)


if __name__ == "__main__":
    unittest.main()

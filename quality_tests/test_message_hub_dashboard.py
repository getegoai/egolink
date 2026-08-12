from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest

from server import message_hub


class MessageHubDashboardTests(unittest.TestCase):
    def test_progress_board_loader_allowlists_fields_and_removes_local_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "progress_board.json"
            path.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-07-11 15:00 UTC",
                        "git": {"branch": "main", "head": "abc123 test"},
                        "current_focus": "Probe QMI8658",
                        "milestones": [
                            {
                                "id": "D2",
                                "title": "Location Accuracy",
                                "done": 8,
                                "total": 10,
                                "tasks": [
                                    {
                                        "id": "D2-001",
                                        "label": "baseline",
                                        "state": "in_progress",
                                        "path": "D:/private/task.md",
                                    }
                                ],
                            }
                        ],
                        "operator_asks": ["Connect module"],
                        "active_tasks": [{"path": "D:/private/active.md"}],
                        "recent_done": [{"path": "D:/private/done.md"}],
                        "key_releases": [{"path": "D:/private/release.json"}],
                        "secret": "must-not-pass",
                    }
                ),
                encoding="utf-8",
            )

            progress = message_hub.load_progress_board(path)

        payload = json.dumps(progress)
        self.assertEqual(progress["status"], "available")
        self.assertEqual(progress["milestones"][0]["done"], 8)
        self.assertEqual(progress["operator_asks"], ["Connect module"])
        self.assertEqual(progress["summary"]["active_count"], 1)
        self.assertNotIn("D:/private", payload)
        self.assertNotIn("must-not-pass", payload)
        self.assertFalse(progress["privacy"]["local_paths_exposed"])

    def test_missing_progress_board_is_explainable(self) -> None:
        progress = message_hub.load_progress_board(Path("missing-progress-board-unit.json"))

        self.assertEqual(progress["status"], "unavailable")
        self.assertEqual(progress["reason"], "progress_board_missing_or_invalid")

    def test_dashboard_links_to_local_only_d2_reference_capture(self) -> None:
        html = message_hub.render_dashboard()

        self.assertIn('href="/d2-reference-capture"', html)
        self.assertIn("D2 Reference Capture", html)

    def test_dashboard_loads_d2_reference_manifest_locally_without_upload_api(self) -> None:
        html = message_hub.render_dashboard()

        self.assertIn('id="loadD2Manifest"', html)
        self.assertIn('id="clearD2References"', html)
        self.assertIn('id="d2ManifestFile"', html)
        self.assertIn('accept="application/json,.json"', html)
        self.assertIn("egolink.d2.map_review.v1", html)
        self.assertIn("egolink.d2.map_review.disabled.v1", html)
        self.assertIn("egolink.d2.reference_capture.v1", html)
        self.assertIn("D2_MANIFEST_MAX_BYTES = 262144", html)
        self.assertIn("D2_REFERENCE_POINT_LIMIT = 16", html)
        self.assertIn("manifest device does not match active device", html)
        self.assertIn("browser_local_manifest", html)
        self.assertIn("mapWithLocalReferences", html)
        self.assertIn("d1MapTrack(points, referencePoints)", html)
        self.assertNotIn("/api/v1/d2-reference", html)
        self.assertNotIn("method: 'POST'", html)

    def test_d2_reference_capture_is_mobile_local_only_and_manifest_compatible(self) -> None:
        html = message_hub.render_d2_reference_capture()

        self.assertIn('<meta name="viewport" content="width=device-width, initial-scale=1"', html)
        self.assertIn("Local only", html)
        self.assertIn("Reference coordinates are not uploaded", html)
        self.assertIn("egolink.field003_manifest.v0.2", html)
        self.assertIn("open_sky_01", html)
        self.assertIn("street_between_buildings_01", html)
        self.assertIn("tree_cover_01", html)
        self.assertIn("phone_browser_single_fix", html)
        self.assertIn("phone_gnss_5min_average", html)
        self.assertIn("5 cold + 5 warm per point", html)
        self.assertIn("navigator.geolocation", html)
        self.assertIn("localStorage", html)
        self.assertIn("field_manifest.json", html)
        self.assertIn("Partial evidence · not acceptance", html)
        self.assertNotIn("fetch(", html)
        self.assertNotIn("/api/v1/", html)

    def test_dashboard_uses_field_first_information_hierarchy(self) -> None:
        html = message_hub.render_dashboard()

        ordered_markers = (
            'id="d1Link"',
            'id="fieldOperations"',
            'id="fieldEvidence"',
            'id="fieldResults"',
            'id="dataFlywheel"',
            'id="progressBoard"',
            'id="modelDetails"',
            'id="diagnosticsDetails"',
        )
        positions = [html.index(marker) for marker in ordered_markers]

        self.assertEqual(positions, sorted(positions))
        self.assertIn("Field live view", html)
        self.assertIn("Field Test Results", html)
        self.assertIn("Data Flywheel", html)
        self.assertIn("Project Progress", html)

    def test_dashboard_disclosures_default_closed_and_preserve_existing_targets(self) -> None:
        html = message_hub.render_dashboard()

        operations_pos = html.index('id="fieldOperations"')
        operations_start = html.rfind("<section", 0, operations_pos)
        operations_end = html.index('id="fieldResults"', operations_pos)
        operations_body = html[operations_start:operations_end]
        for operations_target in ("deviceSelector", "commands", "fieldState"):
            self.assertIn(f'id="{operations_target}"', operations_body)

        disclosure_bodies: dict[str, str] = {}
        for details_id in ("modelDetails", "diagnosticsDetails"):
            id_pos = html.index(f'id="{details_id}"')
            tag_start = html.rfind("<details", 0, id_pos)
            tag_end = html.index(">", id_pos)
            close = html.index("</details>", tag_end)
            opening_tag = html[tag_start : tag_end + 1]
            disclosure_bodies[details_id] = html[tag_end + 1 : close]

            self.assertGreaterEqual(tag_start, 0)
            self.assertNotIn(" open", opening_tag)
            self.assertIn("dashboard-details", opening_tag)
            self.assertIn("<summary", disclosure_bodies[details_id])

        for target_id in (
            "d1Link",
            "progressBoard",
            "productDemo",
            "fieldResults",
            "dataFlywheel",
            "commands",
            "fieldState",
            "rawFrames",
            "messages",
        ):
            self.assertEqual(html.count(f'id="{target_id}"'), 1, target_id)

        for model_target in (
            "trainingExperiment",
            "d1TrainingReadiness",
            "d1LabelingDecisionTemplate",
        ):
            self.assertIn(f'id="{model_target}"', disclosure_bodies["modelDetails"])
        for diagnostic_target in ("rawFrames", "messages"):
            self.assertIn(f'id="{diagnostic_target}"', disclosure_bodies["diagnosticsDetails"])

    def test_dashboard_device_selector_prefers_current_run_then_newest_device(self) -> None:
        html = message_hub.render_dashboard()

        selector_pos = html.index('id="deviceSelector"')
        selector_start = html.rfind("<select", 0, selector_pos)
        selector_end = html.index(">", selector_pos)
        selector_tag = html[selector_start : selector_end + 1]
        self.assertGreaterEqual(selector_start, 0)
        self.assertIn('<label for="deviceSelector">', html)
        self.assertIn("aria-label=", selector_tag)
        self.assertIn("deviceSelector.addEventListener('change'", html)
        self.assertIn("DASHBOARD_DEVICE_KEY", html)
        self.assertIn("selectedDashboardDeviceId", html)
        self.assertIn("localStorage.setItem(DASHBOARD_DEVICE_KEY", html)

        function_start = html.index("function selectDashboardDevice")
        function_end = html.find("\n    function ", function_start + 1)
        selector_function = html[function_start : function_end if function_end >= 0 else None]
        current_run_marker = "current_run" if "current_run" in selector_function else "currentRun"
        self.assertIn(current_run_marker, selector_function)
        self.assertIn("device_id", selector_function)
        self.assertIn("last_seen_at", selector_function)
        self.assertIn("Date.parse", selector_function)
        self.assertLess(selector_function.index(current_run_marker), selector_function.index("last_seen_at"))
        self.assertIn("if (runDevice) return runDevice", selector_function)
        self.assertIn("return rightSeen - leftSeen", selector_function)

        render_start = html.index("function renderSelectedDevicePanels")
        render_end = html.find("\n    function ", render_start + 1)
        selected_render = html[render_start : render_end if render_end >= 0 else None]
        self.assertIn("selectDashboardDevice", selected_render)
        self.assertIn("d1LinkPanel", selected_render)
        self.assertIn("latestFieldState", selected_render)

    def test_dashboard_refresh_is_non_overlapping_and_retains_last_success(self) -> None:
        html = message_hub.render_dashboard()

        self.assertIn("let refreshInFlight = false", html)
        self.assertIn("let lastSuccessfulDashboardState = null", html)
        refresh_start = html.index("async function refresh")
        refresh_end = html.index("\n    refresh();", refresh_start)
        refresh_function = html[refresh_start:refresh_end]

        self.assertIn("if (refreshInFlight) return", refresh_function)
        self.assertIn("refreshInFlight = true", refresh_function)
        self.assertIn("try {", refresh_function)
        self.assertIn("catch", refresh_function)
        self.assertIn("finally", refresh_function)
        self.assertIn("refreshInFlight = false", refresh_function)
        self.assertIn("lastSuccessfulDashboardState = data", refresh_function)
        self.assertIn("setRefreshStatus", refresh_function)
        self.assertIn("refreshing", refresh_function.lower())
        self.assertIn("connected", refresh_function.lower())
        self.assertIn("failed", refresh_function.lower())
        self.assertNotIn("showStateMessage", refresh_function)

        status_start = html.index("function setRefreshStatus")
        status_end = html.find("\n    function ", status_start + 1)
        status_function = html[status_start : status_end if status_end >= 0 else None]
        self.assertIn("refreshStatus.textContent", status_function)

        catch_start = refresh_function.index("catch")
        finally_start = refresh_function.index("finally", catch_start)
        catch_block = refresh_function[catch_start:finally_start]
        self.assertIn("lastSuccessfulDashboardState", catch_block)
        self.assertIn("setInterval(refresh, 3000)", html)

    def test_dashboard_table_scroll_and_live_status_are_accessible(self) -> None:
        html = message_hub.render_dashboard()

        self.assertIn(".table-scroll", html)
        self.assertIn("overflow-x: auto", html)
        self.assertIn('.d1-summary-pane { order: 1; }', html)
        self.assertIn('.d1-map-pane { order: 2; }', html)
        self.assertIn('button, select { min-height: 44px; }', html)
        self.assertIn('<details class="d1-details">', html)
        self.assertIn('<summary>D1 evidence details</summary>', html)
        refresh_pos = html.index('id="refreshStatus"')
        refresh_start = html.rfind("<", 0, refresh_pos)
        refresh_end = html.index(">", refresh_pos)
        refresh_tag = html[refresh_start : refresh_end + 1]
        self.assertIn('role="status"', refresh_tag)
        self.assertIn('aria-live="polite"', refresh_tag)

        messages_pos = html.index('id="messages"')
        wrapper_start = html.rfind('<div class="table-scroll"', 0, messages_pos)
        wrapper_end = html.index(">", wrapper_start)
        wrapper_tag = html[wrapper_start : wrapper_end + 1]
        self.assertGreaterEqual(wrapper_start, 0)
        self.assertIn('role="region"', wrapper_tag)
        self.assertIn("aria-label=", wrapper_tag)
        self.assertIn('tabindex="0"', wrapper_tag)
        self.assertIn("<table", html[wrapper_end:messages_pos])

    def test_dashboard_exposes_field_state_and_command_panels(self) -> None:
        html = message_hub.render_dashboard()

        self.assertIn("Latest Field State", html)
        self.assertIn("Run Context", html)
        self.assertIn("Commands", html)
        self.assertIn("Raw Frames", html)
        self.assertIn("Product Demo", html)
        self.assertIn("Field Test Results", html)
        self.assertIn("Data Flywheel", html)
        self.assertIn("Project Progress", html)
        self.assertIn('id="progressBoard"', html)
        self.assertIn("progressBoardPanel", html)
        self.assertIn("Waiting For Founder", html)
        self.assertIn("Training Experiments", html)
        self.assertIn("Training Run Preflight", html)
        self.assertIn("Training Feature Manifest", html)
        self.assertIn("Training Runner Dry-Run", html)
        self.assertIn("Training Baseline Eval", html)
        self.assertIn("Training Handoff Bundle", html)
        self.assertIn("Training Job Plan", html)
        self.assertIn("Synthetic Training Chain", html)
        self.assertIn("D1 Training Readiness", html)
        self.assertIn("D1 Labeling Intake", html)
        self.assertIn("D1 Labeling Queue", html)
        self.assertIn("D1 Labeling Review Packet", html)
        self.assertIn("D1 Labeling Decision Template", html)
        self.assertIn("D1 Link Through", html)
        self.assertIn("dashboard-shell", html)
        self.assertIn("Field live view", html)
        self.assertIn("runContext", html)
        self.assertIn("rawFrames", html)
        self.assertIn("productDemo", html)
        self.assertIn("fieldResults", html)
        self.assertIn("dataFlywheel", html)
        self.assertIn("trainingExperiment", html)
        self.assertIn("trainingRunPreflight", html)
        self.assertIn("trainingFeatureManifest", html)
        self.assertIn("trainingRunnerDryRun", html)
        self.assertIn("trainingBaselineEval", html)
        self.assertIn("trainingHandoffBundle", html)
        self.assertIn("trainingJobPlan", html)
        self.assertIn("syntheticTrainingChain", html)
        self.assertIn("d1TrainingReadiness", html)
        self.assertIn("d1LabelingIntake", html)
        self.assertIn("d1LabelingQueue", html)
        self.assertIn("d1LabelingReviewPacket", html)
        self.assertIn("d1LabelingDecisionTemplate", html)
        self.assertIn("d1Link", html)
        self.assertIn("d1_link", html)
        self.assertIn("field_results", html)
        self.assertIn("data_flywheel", html)
        self.assertIn("dataFlywheelPanel", html)
        self.assertIn("training_experiment", html)
        self.assertIn("trainingExperimentPanel", html)
        self.assertIn("training_run_preflight", html)
        self.assertIn("trainingRunPreflightPanel", html)
        self.assertIn("training_feature_manifest", html)
        self.assertIn("trainingFeatureManifestPanel", html)
        self.assertIn("training_runner_dry_run", html)
        self.assertIn("trainingRunnerDryRunPanel", html)
        self.assertIn("training_baseline_eval", html)
        self.assertIn("trainingBaselineEvalPanel", html)
        self.assertIn("training_handoff_bundle", html)
        self.assertIn("trainingHandoffBundlePanel", html)
        self.assertIn("training_job_plan", html)
        self.assertIn("trainingJobPlanPanel", html)
        self.assertIn("synthetic_training_chain", html)
        self.assertIn("syntheticTrainingChainPanel", html)
        self.assertIn("d1_training_readiness", html)
        self.assertIn("d1TrainingReadinessPanel", html)
        self.assertIn("d1_labeling_intake", html)
        self.assertIn("d1LabelingIntakePanel", html)
        self.assertIn("d1_labeling_queue", html)
        self.assertIn("d1LabelingQueuePanel", html)
        self.assertIn("d1_labeling_review_packet", html)
        self.assertIn("d1LabelingReviewPacketPanel", html)
        self.assertIn("d1_labeling_decision_template", html)
        self.assertIn("d1LabelingDecisionTemplatePanel", html)
        self.assertIn("Runner Handoff", html)
        self.assertIn("Runner Ready", html)
        self.assertIn("Feature Rows", html)
        self.assertIn("Target Boundary", html)
        self.assertIn("Source Match", html)
        self.assertIn("Runner Input", html)
        self.assertIn("Target Guard", html)
        self.assertIn("Metric Scope", html)
        self.assertIn("Performance Claim", html)
        self.assertIn("Source Refs", html)
        self.assertIn("raw_rows_exposed", html)
        self.assertIn("Runner Queue", html)
        self.assertIn("Planned Metrics", html)
        self.assertIn("Synthetic Review", html)
        self.assertIn("Data Pipeline", html)
        self.assertIn("Review Ready", html)
        self.assertIn("First Intake", html)
        self.assertIn("Pending Items", html)
        self.assertIn("First Queue Item", html)
        self.assertIn("First Review Item", html)
        self.assertIn("Label Groups", html)
        self.assertIn("Decision Slots", html)
        self.assertIn("Needed Reviews", html)
        self.assertIn("Decision Progress", html)
        self.assertIn("First Template Item", html)
        self.assertIn("Selected Values", html)
        self.assertIn("Sensor Gaps", html)
        self.assertIn("Synthetic Gate", html)
        self.assertIn("Measured Metrics", html)
        self.assertIn("Classification Metrics", html)
        self.assertIn("Footprint Metrics", html)
        self.assertIn("Candidate Records", html)
        self.assertIn("D2 Baselines", html)
        self.assertIn("D2 Attempts", html)
        self.assertIn("Training Gate", html)
        self.assertIn("Review Queues", html)
        self.assertIn("Review Queue", html)
        self.assertIn("review_queue", html)
        self.assertIn("sample_records", html)
        self.assertIn("available_actions", html)
        self.assertIn("Training Server", html)
        self.assertIn("D5 Artifacts", html)
        self.assertIn("fieldResultsPanel", html)
        self.assertIn("fieldResultsCards", html)
        self.assertIn("d1FieldOverview", html)
        self.assertIn("d1StatusStrip", html)
        self.assertIn("d1FreshnessBadge", html)
        self.assertIn("d1FieldReadyBadge", html)
        self.assertIn("d1AcceptanceBadge", html)
        self.assertIn("field_readiness", html)
        self.assertIn("acceptance_gate", html)
        self.assertIn("Field Ready", html)
        self.assertIn("D1 Acceptance Gate", html)
        self.assertIn("acceptanceClass", html)
        self.assertIn("acceptanceLabel", html)
        self.assertIn("Coordinate data", html)
        self.assertIn("Latest missing reason", html)
        self.assertIn("Ready Reason", html)
        self.assertIn("Operator Action", html)
        self.assertIn("Freshness Gate", html)
        self.assertIn("readinessClass", html)
        self.assertIn("readinessHeadline", html)
        self.assertIn("status-chip", html)
        self.assertIn("d1-card", html)
        self.assertIn("D1 Status", html)
        self.assertIn("Map Surface", html)
        self.assertIn("map-surface", html)
        self.assertIn("map-track", html)
        self.assertIn("map-point-current", html)
        self.assertIn("map-point-reference", html)
        self.assertIn("normalizeMapPoints", html)
        self.assertIn("d1MapTrack", html)
        self.assertIn("data-d1-map-mode", html)
        self.assertIn("data-map-review-mode", html)
        self.assertIn("data-map-provider-mode", html)
        self.assertIn("No-key Local Map", html)
        self.assertIn("Provider Status", html)
        self.assertIn("D2 Reference", html)
        self.assertIn("fieldEvidenceLanes", html)
        self.assertIn("D2 Baseline", html)
        self.assertIn("D5 Flywheel", html)
        self.assertIn("Track points", html)
        self.assertIn("Accuracy Claim", html)
        self.assertIn("Upload Freshness", html)
        self.assertIn("Upload Success", html)
        self.assertIn("Location Uploads", html)
        self.assertIn("Power Curve", html)
        self.assertIn("Power Delta", html)
        self.assertIn("Battery Claim", html)
        self.assertIn("uplink_metrics", html)
        self.assertIn("power_curve", html)
        self.assertIn("raw_post_success_rate", html)
        self.assertIn("battery_life_claim", html)
        self.assertIn("GNSS Evidence", html)
        self.assertIn("Cell/LTE Evidence", html)
        self.assertIn("IMU Evidence", html)
        self.assertIn("Power Evidence", html)
        self.assertIn("product_demo", html)
        self.assertIn("KR-008", html)
        self.assertIn("DEMO-008", html)
        self.assertIn("Evidence Mode", html)
        self.assertIn("Web Review", html)
        self.assertIn("Release Ready", html)
        self.assertIn("raw_frames", html)
        self.assertIn("current_run", html)
        self.assertIn("Current Run", html)
        self.assertIn("Key Release", html)
        self.assertIn("Baseline", html)
        self.assertIn("Command Chain", html)
        self.assertIn("Raw Evidence", html)
        self.assertIn("Derived Location", html)
        self.assertIn("Failure State", html)
        self.assertIn("Failure Reason", html)
        self.assertIn("Network Reconnect", html)
        self.assertIn("Network Error", html)
        self.assertIn("Raw POST", html)
        self.assertIn("raw_post_attempt_count", html)
        self.assertIn("raw_post_success_count", html)
        self.assertIn("raw_post_failure_count", html)
        self.assertIn("Cache Queue", html)
        self.assertIn("Cache Retry", html)
        self.assertIn("retry_attempt_count", html)
        self.assertIn("retry_success_count", html)
        self.assertIn("retry_failure_count", html)
        self.assertIn("Cache Flush", html)
        self.assertIn("flush_attempt_count", html)
        self.assertIn("flush_success_count", html)
        self.assertIn("flush_failure_count", html)
        self.assertIn("Cache Drops", html)
        self.assertIn("EALE-P0", html)
        self.assertIn("EALE Reason", html)
        self.assertIn("EALE Failure", html)
        self.assertIn("Dataset Window", html)
        self.assertIn("Dataset Training", html)
        self.assertIn("Quality Flags", html)
        self.assertIn("rawFrameStatus", html)
        self.assertIn("Raw Frame ID", html)
        self.assertIn("Raw Derived", html)
        self.assertIn("onlineLabel", html)
        self.assertIn("GNSS State", html)
        self.assertIn("gnssField", html)
        self.assertIn("Fix", html)
        self.assertIn("Satellites", html)
        self.assertIn("HDOP", html)
        self.assertIn("Source Status", html)
        self.assertIn("Location Updated", html)
        self.assertIn("Field Message", html)
        self.assertIn("Location State", html)
        self.assertIn("Belief", html)
        self.assertIn("Belief Source", html)
        self.assertIn("Belief Reason", html)
        self.assertIn("Memory State", html)
        self.assertIn("Memory Updated", html)
        self.assertIn("Memory Reason", html)
        self.assertIn("Transport", html)
        self.assertIn("Runtime Reset", html)
        self.assertIn("obsReliability", html)
        self.assertIn("obsRelNetwork", html)
        self.assertIn("obsRelCache", html)
        self.assertIn("Command", html)
        self.assertIn("Power", html)
        self.assertIn("Cell", html)
        self.assertIn("LTE", html)
        self.assertIn("LTE Reason", html)
        self.assertIn("Wi-Fi", html)
        self.assertIn("IMU", html)
        self.assertIn("evidence_status", html)
        self.assertIn("source_status", html)
        self.assertIn("GNSS Reason", html)
        self.assertIn("Reason Codes", html)
        self.assertIn("observability", html)
        self.assertIn("latest_location", html)
        self.assertIn("location_memory", html)
        self.assertIn("API token required", html)
        self.assertIn("Last Error", html)
        self.assertIn("tokenInput", html)
        self.assertIn("Authorization: `Bearer ${token}`", html)

    def test_d1_link_summary_marks_fresh_periodic_upload_ready(self) -> None:
        now = message_hub.utc_now()
        location = {
            "message_type": "event",
            "event_type": "location_report",
            "seq": 42,
            "server_received_at": now,
            "fix": False,
            "gnss_state": "no_fix",
        }
        device = {
            "device_id": "ego-link-r1-connectivity-001",
            "last_seen_at": now,
            "last_seq": 42,
            "latest_location": location,
            "observability": {
                "location_belief": {
                    "state": "Predicted",
                    "reason": "unit_fresh_periodic_upload",
                    "updated_at": now,
                },
                "transport": {"type": "lte"},
                "gnss": {"fix": False, "state": "no_fix"},
                "cell": {"rat": "LTE", "cell_id": "unit-cell", "registration_state": "registered_home"},
                "imu": {"motion": "stationary", "evidence_status": "mock"},
                "power": {"battery_mv": 4070, "soc_pct": 90, "evidence_status": "measured"},
            },
        }
        messages = [
            {
                **location,
                "lat": 31.200001,
                "lon": 121.400001,
                "power": {"battery_mv": 4070, "soc_pct": 90, "evidence_status": "measured"},
                "reliability": {
                    "network": {
                        "raw_post_attempt_count": 4,
                        "raw_post_success_count": 4,
                        "raw_post_failure_count": 0,
                    }
                },
            }
        ]
        messages.append(
            {
                **location,
                "seq": 43,
                "server_received_at": now,
                "lat": 31.200501,
                "lon": 121.400601,
                "power": {"battery_mv": 4065, "soc_pct": 89, "evidence_status": "measured"},
            }
        )

        summary = message_hub.build_d1_link_summary(device, messages)

        readiness = summary["field_readiness"]
        map_surface = summary["map_surface"]
        self.assertTrue(readiness["ready"])
        self.assertEqual(readiness["state"], "ready")
        self.assertEqual(readiness["reason"], "fresh_periodic_upload")
        self.assertEqual(readiness["operator_action"], "go_test")
        self.assertLessEqual(readiness["freshness_s"], message_hub.D1_FIELD_READY_FRESHNESS_S)
        self.assertEqual(readiness["raw_post_health"], "ok")
        self.assertIn("location_accuracy_not_claimed", readiness["non_claims"])
        self.assertGreaterEqual(map_surface["trajectory"]["point_count"], 2)
        self.assertTrue(map_surface["trajectory"]["visible"])
        self.assertGreaterEqual(len(map_surface["points"]), 2)
        self.assertEqual(map_surface["points"][-1]["source"], "telemetry_history")
        self.assertEqual(map_surface["coordinate_diagnostics"]["coordinate_event_count"], 2)
        self.assertEqual(map_surface["coordinate_diagnostics"]["missing_coordinate_event_count"], 0)
        self.assertEqual(map_surface["review_mode"], "local_no_key")
        self.assertEqual(map_surface["surface_role"], "d2_d5_evidence_review")
        self.assertEqual(map_surface["provider"]["status"], "not_configured")
        self.assertFalse(map_surface["provider"]["blocking_d1"])
        self.assertFalse(map_surface["layers"]["provider_tiles"])
        self.assertEqual(map_surface["reference_points"], [])
        self.assertEqual(map_surface["privacy"]["static_report_policy"], "bounded_summary_no_raw_coordinates")
        self.assertEqual(map_surface["accuracy_claim"], "none")
        self.assertEqual(summary["acceptance_gate"]["status"], "ready")
        self.assertEqual(summary["acceptance_gate"]["track_points"], 2)
        self.assertEqual(summary["acceptance_gate"]["blockers"], [])
        self.assertEqual(summary["acceptance_gate"]["next_action"], "run_d1_field_kit_and_postrun_collector")

    def test_d1_link_summary_explains_location_uploads_without_coordinates(self) -> None:
        now = message_hub.utc_now()
        location = {
            "message_type": "event",
            "event_type": "location_observation",
            "seq": 77,
            "server_received_at": now,
            "cell": {"rat": "LTE", "cell_id": "unit-cell", "registration_state": "registered_home"},
            "imu": {"motion": "stationary", "evidence_status": "mock"},
            "location_belief": {
                "state": "Unknown",
                "reason": "cell_observation_without_position_fix",
                "source": ["cell", "lte", "imu", "power"],
            },
            "lte": {"registered": True, "pdp_active": True, "reason_code": "LTE_READY"},
            "power": {"battery_mv": 4070, "soc_pct": 90, "evidence_status": "measured"},
            "reliability": {
                "network": {
                    "raw_post_attempt_count": 7,
                    "raw_post_success_count": 7,
                    "raw_post_failure_count": 0,
                }
            },
        }
        device = {
            "device_id": "ego-link-r1-connectivity-001",
            "last_seen_at": now,
            "last_seq": 77,
            "latest_location": location,
            "observability": {
                "location_belief": location["location_belief"],
                "transport": {"type": "lte"},
                "gnss": {"fix": False, "state": "no_fix"},
                "cell": location["cell"],
                "lte": location["lte"],
                "imu": location["imu"],
                "power": location["power"],
            },
        }

        summary = message_hub.build_d1_link_summary(device, messages=[location])

        diagnostics = summary["map_surface"]["coordinate_diagnostics"]
        self.assertEqual(diagnostics["location_event_count"], 1)
        self.assertEqual(diagnostics["coordinate_event_count"], 0)
        self.assertEqual(diagnostics["missing_coordinate_event_count"], 1)
        self.assertEqual(diagnostics["latest_missing_reason"], "cell_observation_without_position_fix")
        self.assertEqual(diagnostics["operator_hint"], "move_outdoors_until_two_coordinate_uploads_are_seen")
        self.assertIn("d1_map_trajectory_needs_two_points", summary["acceptance_gate"]["blockers"])
        self.assertIn("d1_location_events_without_coordinate", summary["acceptance_gate"]["warnings"])
        self.assertEqual(
            summary["acceptance_gate"]["next_action"],
            "move_outdoors_until_two_coordinate_uploads_are_seen",
        )

    def test_d1_amap_fail_closed_filters_old_unknown_and_no_fix_coordinates(self) -> None:
        now = message_hub.utc_now()
        messages = [
            {
                "message_type": "event",
                "event_type": "location_report",
                "seq": 1,
                "server_received_at": now,
                "fw_version": "0.1.0-field011-gnss-imu",
                "fix": True,
                "lat": 22.5431,
                "lon": 114.0579,
            },
            {
                "message_type": "event",
                "event_type": "location_report",
                "seq": 2,
                "server_received_at": now,
                "fix": True,
                "lat": 22.5432,
                "lon": 114.0580,
            },
            {
                "message_type": "event",
                "event_type": "location_report",
                "seq": 3,
                "server_received_at": now,
                "fw_version": "0.1.0-fw005-gnss-correctness",
                "fix": False,
                "lat": 22.5433,
                "lon": 114.0581,
            },
        ]
        device = {
            "device_id": "ego-link-r1-connectivity-001",
            "latest_location": messages[-1],
            "last_seen_at": now,
            "observability": {"location_belief": {"state": "Predicted", "updated_at": now}},
        }

        surface = message_hub.build_d1_link_summary(device, list(reversed(messages)))["map_surface"]

        self.assertEqual(surface["amap_eligible_point_count"], 0)
        self.assertEqual(surface["amap_hidden_point_count"], 3)
        self.assertFalse(surface["layers"]["current_point"])
        self.assertFalse(surface["layers"]["trajectory"])
        self.assertEqual(surface["amap_trajectory"]["point_count"], 0)
        self.assertEqual(surface["amap_trajectory"]["hidden_point_count"], 3)
        self.assertEqual(
            [point["amap_exclusion_reason"] for point in surface["points"]],
            ["firmware_parser_not_allowlisted", "firmware_parser_not_allowlisted", "gnss_fix_not_true"],
        )
        self.assertTrue(all(point["coordinate_contract"] == "unknown" for point in surface["points"]))

    def test_d1_amap_mixed_history_only_allows_corrected_firmware_fix(self) -> None:
        now = message_hub.utc_now()
        old = {
            "message_type": "event",
            "event_type": "location_report",
            "seq": 10,
            "server_received_at": now,
            "fw_version": "0.1.0-field011-gnss-imu",
            "fix": True,
            "lat": 22.5431,
            "lon": 114.0579,
        }
        corrected = {
            **old,
            "seq": 11,
            "fw_version": "0.1.0-fw005-gnss-correctness",
            "lat": 22.5432,
            "lon": 114.0580,
        }
        device = {
            "device_id": "ego-link-r1-connectivity-001",
            "latest_location": corrected,
            "last_seen_at": now,
            "observability": {"location_belief": {"state": "Fine", "updated_at": now}},
        }

        surface = message_hub.build_d1_link_summary(device, [corrected, old])["map_surface"]

        self.assertEqual(surface["amap_eligible_point_count"], 1)
        self.assertEqual(surface["amap_hidden_point_count"], 1)
        self.assertTrue(surface["layers"]["current_point"])
        self.assertFalse(surface["layers"]["trajectory"])
        self.assertEqual(surface["amap_trajectory"]["point_count"], 1)
        self.assertEqual(surface["amap_trajectory"]["hidden_point_count"], 1)
        self.assertFalse(surface["points"][0]["amap_eligible"])
        self.assertTrue(surface["points"][1]["amap_eligible"])
        self.assertEqual(surface["points"][1]["coordinate_contract"], "wgs84")
        self.assertEqual(surface["points"][1]["fw_version"], "0.1.0-fw005-gnss-correctness")

    def test_d1_link_summary_waits_without_periodic_location_upload(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        device = {
            "device_id": "ego-link-r1-connectivity-001",
            "last_seen_at": now,
            "last_seq": 7,
            "observability": {"transport": {"type": "lte"}},
        }

        summary = message_hub.build_d1_link_summary(device, messages=[])

        readiness = summary["field_readiness"]
        self.assertFalse(readiness["ready"])
        self.assertEqual(readiness["state"], "waiting_for_data")
        self.assertEqual(readiness["reason"], "no_periodic_location_upload")
        self.assertEqual(readiness["operator_action"], "wait_for_new_dashboard_data")
        self.assertEqual(summary["acceptance_gate"]["status"], "blocked")
        self.assertIn("field_readiness_no_periodic_location_upload", summary["acceptance_gate"]["blockers"])
        self.assertIn("d1_map_trajectory_needs_two_points", summary["acceptance_gate"]["blockers"])

    def test_d1_link_summary_marks_old_periodic_upload_not_ready(self) -> None:
        old = (datetime.now(timezone.utc) - timedelta(seconds=message_hub.D1_FIELD_STALE_FRESHNESS_S + 60)).isoformat()
        location = {
            "message_type": "event",
            "event_type": "location_observation",
            "seq": 8,
            "server_received_at": old,
        }
        device = {
            "device_id": "ego-link-r1-connectivity-001",
            "last_seen_at": old,
            "last_seq": 8,
            "latest_location": location,
            "observability": {"location_belief": {"state": "Predicted", "updated_at": old}},
        }

        summary = message_hub.build_d1_link_summary(device, messages=[location])

        readiness = summary["field_readiness"]
        self.assertFalse(readiness["ready"])
        self.assertEqual(readiness["state"], "not_ready")
        self.assertEqual(readiness["reason"], "periodic_upload_too_old")
        self.assertEqual(readiness["operator_action"], "check_power_sim_lte_or_reboot")
        self.assertEqual(summary["acceptance_gate"]["status"], "blocked")
        self.assertIn("field_readiness_periodic_upload_too_old", summary["acceptance_gate"]["blockers"])

    def test_latest_field_results_summary_is_bounded_for_dashboard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            d1_dir = root / "d1_web_api" / "run-a"
            d1_dir.mkdir(parents=True)
            (d1_dir / "d1_web_api_report.json").write_text(
                json.dumps(
                    {
                        "result": "PASS",
                        "created_at": "2026-07-04T11:18:46+00:00",
                        "review_id": "ui001-web-vps-20260704",
                        "device_id": "ego-link-r1-connectivity-001",
                        "d1": {
                            "status": "estimate_visible",
                            "upload_freshness": {"freshness_s": 30},
                            "uplink_metrics": {
                                "raw_post_success_count": 45,
                                "raw_post_failure_count": 0,
                                "location_event_count": 22,
                            },
                            "power_curve": {"sample_count": 11, "window_s": 680},
                        },
                        "scope": {"commands_sent": False},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (d1_dir / "d1_web_api_report.md").write_text("# D1\n", encoding="utf-8")

            location_dir = root / "location_accuracy" / "run-d2"
            location_dir.mkdir(parents=True)
            (location_dir / "location_accuracy_report.json").write_text(
                json.dumps(
                    {
                        "status": "PASS",
                        "run_id": "d2-baseline-unit",
                        "created_at": "2026-07-04T11:45:00+00:00",
                        "device_id": "ego-link-r1-connectivity-001",
                        "metrics": {
                            "fix_rate": 0.8,
                            "ttff_median_s": 38,
                            "median_error_m": 12.5,
                            "p90_error_m": 31.0,
                            "reference_point_count": 3,
                            "sample_count": 15,
                        },
                        "raw_reference_points": [
                            {"lat": 31.123456, "lon": 121.654321, "label": "private-home"}
                        ],
                        "private_samples_path": "C:/private/location_accuracy_samples.jsonl",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (location_dir / "location_accuracy_report.md").write_text("# D2\n", encoding="utf-8")

            amoled_dir = root / "amoled_visible_status" / "run-b"
            amoled_dir.mkdir(parents=True)
            (amoled_dir / "run-b.summary.json").write_text(
                json.dumps(
                    {
                        "ok": True,
                        "session_id": "run-b",
                        "command_ack_count": 1,
                        "status_rendered_count": 1,
                        "last_status_payload": {
                            "summary": "LIVE fresh 58s",
                            "location": "Coord 0.37919,1.23713",
                            "battery": "88% / 4052mV",
                        },
                        "jsonl_path": "reports/amoled_visible_status/run-b/run-b.jsonl",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            companion_dir = root / "d1_field_companion" / "run-c"
            companion_dir.mkdir(parents=True)
            (companion_dir / "d1_field_companion_summary.json").write_text(
                json.dumps(
                    {
                        "result": "PASS",
                        "run_id": "run-c",
                        "created_at": "2026-07-04T11:30:00+00:00",
                        "children": [
                            {
                                "name": "d1_observer",
                                "summary": {
                                    "device_id": "ego-link-r1-connectivity-001",
                                    "summary": {
                                        "sample_count": 2,
                                        "successful_sample_count": 2,
                                        "coordinate_sample_count": 1,
                                        "max_freshness_s": 40,
                                    },
                                    "warnings": [],
                                    "errors": [],
                                },
                            },
                            {"name": "amoled_sidecar", "summary": {"status_rendered_count": 2}},
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            observation_dir = root / "d1_field_observation" / "run-d"
            observation_dir.mkdir(parents=True)
            (observation_dir / "d1_field_observation_status.json").write_text(
                json.dumps(
                    {
                        "status": "completed",
                        "result": "WARN",
                        "run_id": "run-d",
                        "sample_count": 4,
                        "successful_sample_count": 4,
                        "fetch_error_count": 0,
                        "latest_seq": 42,
                        "latest_freshness_s": 33,
                        "report_path": "C:/private/local/d1_field_observation_report.json",
                        "samples_path": "C:/private/local/d1_field_samples.jsonl",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (observation_dir / "d1_field_observation_report.json").write_text(
                json.dumps(
                    {
                        "result": "WARN",
                        "observer_version": "D1.field_observer.v2",
                        "run_id": "run-d",
                        "created_at": "2026-07-04T11:40:00+00:00",
                        "device_id": "ego-link-r1-connectivity-001",
                        "summary": {
                            "sample_count": 4,
                            "successful_sample_count": 4,
                            "fetch_error_count": 0,
                            "last_seq": 42,
                            "last_location_upload_at": "2026-07-04T11:39:00+00:00",
                            "max_freshness_s": 44,
                            "raw_post_success_delta": 3,
                            "location_event_count_delta": 2,
                            "power_sample_count_delta": 1,
                            "battery_mv_first": 4100,
                            "battery_mv_last": 4090,
                        },
                        "warnings": ["d1_coordinate_not_observed"],
                        "errors": [],
                        "samples_path": "C:/private/local/d1_field_samples.jsonl",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (observation_dir / "d1_field_observation_report.md").write_text("# Observation\n", encoding="utf-8")
            live_observation_dir = root / "d1_field_observation" / "run-e"
            live_observation_dir.mkdir(parents=True)
            live_status_path = live_observation_dir / "d1_field_observation_status.json"
            live_status_path.write_text(
                json.dumps(
                    {
                        "status": "running",
                        "run_id": "run-e",
                        "sample_count": 6,
                        "successful_sample_count": 6,
                        "fetch_error_count": 0,
                        "latest_seq": 100,
                        "latest_freshness_s": 12,
                        "report_path": "C:/private/local/live_report.json",
                        "samples_path": "C:/private/local/d1_field_samples.jsonl",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            os.utime(live_status_path, (2_000_000_000, 2_000_000_000))

            power_dir = root / "power" / "run-f"
            power_dir.mkdir(parents=True)
            (power_dir / "power_curve_report.json").write_text(
                json.dumps(
                    {
                        "generator": {"created_at": "2026-07-04T11:42:00+00:00"},
                        "result": {"status": "WARN", "warnings": ["duration below threshold"], "errors": []},
                        "source": {
                            "test_run_id": "run-f",
                            "input_path": "C:/private/local/field_observer_power_export.json",
                        },
                        "duration_hours": 2.19,
                        "counts": {
                            "samples": 132,
                            "measured_power_samples": 126,
                            "battery_mv_samples": 126,
                            "soc_pct_samples": 132,
                        },
                        "consumption_estimate": {"status": "not_estimated"},
                        "target_comparison": {"status": "not_estimated"},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (power_dir / "power_curve_report.md").write_text("# Power\n", encoding="utf-8")

            demo_dir = root / "d1_demo" / "run-g"
            demo_dir.mkdir(parents=True)
            (demo_dir / "d1_demo_report.json").write_text(
                json.dumps(
                    {
                        "result": "WARN",
                        "report_id": "run-g",
                        "created_at": "2026-07-04T11:43:00+00:00",
                        "ready_for_founder_review": False,
                        "d1": {"status": "estimate_visible"},
                        "power": {
                            "result": "WARN",
                            "duration_hours": 2.19,
                            "counts": {"measured_power_samples": 126},
                        },
                        "gates": [
                            {"id": "G1_D1_WEB_API", "status": "PASS", "summary": "D1 Web/API gate passed"},
                            {"id": "G2_PWR001_POWER_REPORT", "status": "WARN", "summary": "Power report warned"},
                        ],
                        "boundaries": {"battery_life_claimed": False},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (demo_dir / "d1_demo_report.md").write_text("# Demo\n", encoding="utf-8")

            postrun_dir = root / "d1_postrun" / "run-h"
            postrun_dir.mkdir(parents=True)
            (postrun_dir / "d1_postrun_collection_summary.json").write_text(
                json.dumps(
                    {
                        "result": "WARN",
                        "run_id": "run-h",
                        "created_at": "2026-07-04T11:44:00+00:00",
                        "components": {
                            "web_api": {"result": "PASS"},
                            "field_observation": {"result": "PASS"},
                            "power_curve": {"result": "WARN"},
                            "d1_demo": {"result": "WARN", "ready_for_founder_review": False},
                        },
                        "warnings": ["power_curve:WARN"],
                        "errors": [],
                        "next_steps": ["Keep work on D1 acceptance and keep DATA/TRAIN frozen."],
                        "artifacts": {"field_observation_samples": "C:/private/local/d1_field_samples.jsonl"},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (postrun_dir / "d1_postrun_collection_summary.md").write_text("# Postrun\n", encoding="utf-8")

            summary = message_hub.load_latest_field_results(root)

        self.assertTrue(summary["available"])
        self.assertEqual(summary["status"], "warn")
        self.assertEqual(summary["report_count"], 8)
        kinds = {item["kind"] for item in summary["reports"]}
        self.assertEqual(
            kinds,
            {
                "d2_location_accuracy",
                "d1_web_api",
                "d1_postrun",
                "d1_demo",
                "power_curve",
                "amoled_status",
                "d1_field_companion",
                "d1_field_observation",
            },
        )
        d2 = next(item for item in summary["reports"] if item["kind"] == "d2_location_accuracy")
        self.assertEqual(d2["metrics"]["median_error_m"], 12.5)
        self.assertEqual(d2["metrics"]["reference_point_count"], 3)
        d2_payload = json.dumps(d2)
        self.assertNotIn("31.123456", d2_payload)
        self.assertNotIn("121.654321", d2_payload)
        self.assertNotIn("location_accuracy_samples.jsonl", d2_payload)
        amoled = next(item for item in summary["reports"] if item["kind"] == "amoled_status")
        self.assertNotIn("jsonl_path", json.dumps(amoled))
        self.assertEqual(amoled["metrics"]["command_ack_count"], 1)
        observation = next(item for item in summary["reports"] if item["kind"] == "d1_field_observation")
        self.assertEqual(observation["status"], "running")
        self.assertEqual(observation["run_id"], "run-e")
        self.assertEqual(observation["metrics"]["sample_count"], 6)
        self.assertEqual(observation["metrics"]["latest_seq"], 100)
        observation_payload = json.dumps(observation)
        self.assertNotIn("d1_field_samples.jsonl", observation_payload)
        self.assertNotIn("C:/private", observation_payload)
        power = next(item for item in summary["reports"] if item["kind"] == "power_curve")
        self.assertEqual(power["metrics"]["measured_power_samples"], 126)
        demo = next(item for item in summary["reports"] if item["kind"] == "d1_demo")
        self.assertFalse(demo["metrics"]["ready_for_founder_review"])
        postrun = next(item for item in summary["reports"] if item["kind"] == "d1_postrun")
        self.assertEqual(postrun["metrics"]["power_curve"], "WARN")
        all_results = json.dumps(summary)
        self.assertNotIn("d1_field_samples.jsonl", all_results)
        self.assertNotIn("location_accuracy_samples.jsonl", all_results)
        self.assertNotIn("C:/private", all_results)

    def test_field_results_missing_returns_explainable_not_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary = message_hub.load_latest_field_results(Path(tmp))

        self.assertFalse(summary["available"])
        self.assertEqual(summary["status"], "not_available")
        self.assertEqual(summary["reason"], "no_field_result_reports")

    def test_latest_data_flywheel_status_summary_is_bounded_for_dashboard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_dir = root / "run-a"
            report_dir.mkdir(parents=True)
            (report_dir / "data_flywheel_status.json").write_text(
                json.dumps(
                    {
                        "schema_version": "egolink.data_flywheel_status.v0.1",
                        "run_id": "unit-data-flywheel",
                        "generated_at": "2026-07-04T12:04:00+00:00",
                        "status": "needs_review",
                        "pipeline_stage": "candidate_review_pending",
                        "candidate_store": {
                            "available": True,
                            "db_path": "C:/private/path/training_candidates.db",
                            "schema_version": "egolink.training_candidate_store.v0.1",
                            "latest_updated_at": "2026-07-04T12:03:00+00:00",
                        },
                        "counts": {
                            "sessions_total": 1,
                            "records_total": 3,
                            "needs_review_records": 3,
                            "training_allowed_records": 0,
                            "reviewed_training_candidate_records": 0,
                            "experiment_input_records": 0,
                            "location_baseline_reports": 1,
                            "reference_points": 3,
                            "location_attempts": 30,
                            "fixed_attempts": 27,
                            "no_fix_attempts": 3,
                        },
                        "source_reports": [
                            {
                                "type": "d2_location_accuracy_baseline",
                                "run_id": "FIELD-003-unit",
                                "result_status": "PASS",
                                "report_sha256": "abc123",
                            }
                        ],
                        "state_counts": {"candidate": 3},
                        "candidate_type_counts": {"needs_help": 3},
                        "quality_gate_counts": {"pass": 3},
                        "label_review_state_counts": {"pending": 3},
                        "review": {
                            "label_review_pending_records": 3,
                            "split_leakage_unchecked_records": 3,
                            "privacy_or_consent_blocked_records": 0,
                            "quality_blocked_records": 0,
                        },
                        "review_queue": {
                            "available": True,
                            "pending_records": 3,
                            "available_actions": ["approve_for_training", "reject", "needs_changes"],
                            "sample_records": [
                                {
                                    "record_id": "cand-unit",
                                    "session_id": "session-unit",
                                    "state": "candidate",
                                    "label": "needs_help",
                                    "split_name": "unassigned",
                                    "label_review_state": "pending",
                                }
                            ],
                        },
                        "readiness": {
                            "model_training_ready": False,
                            "reason": "candidate_review_not_complete",
                            "dataset_manifest_ready": False,
                            "training_server_ready": False,
                            "on_device_deployment_ready": False,
                        },
                        "blockers": ["label_review_pending", "split_leakage_review_pending"],
                        "warnings": [],
                        "next_step": "Create the labeling/review loop.",
                        "paths": {
                            "data_flywheel_status_markdown": "reports/data_flywheel/run-a/data_flywheel_status.md",
                            "location_review_packet_markdown": "reports/data_flywheel/run-a/location_review_packet.md",
                            "location_dataset_manifest_markdown": "reports/data_flywheel/run-a/location_dataset_manifest.md",
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            summary = message_hub.load_latest_data_flywheel_status(root)

        self.assertTrue(summary["available"])
        self.assertEqual(summary["status"], "needs_review")
        self.assertEqual(summary["counts"]["records_total"], 3)
        self.assertEqual(summary["counts"]["location_baseline_reports"], 1)
        self.assertEqual(summary["counts"]["reference_points"], 3)
        self.assertEqual(summary["counts"]["location_attempts"], 30)
        self.assertEqual(summary["source_reports"][0]["run_id"], "FIELD-003-unit")
        self.assertEqual(summary["review"]["label_review_pending_records"], 3)
        self.assertEqual(summary["review_queue"]["pending_records"], 3)
        self.assertEqual(summary["review_queue"]["sample_records"][0]["record_id"], "cand-unit")
        self.assertIn("approve_for_training", summary["review_queue"]["available_actions"])
        self.assertFalse(summary["readiness"]["model_training_ready"])
        self.assertEqual(summary["review_packet_path"], "reports/data_flywheel/run-a/location_review_packet.md")
        self.assertEqual(summary["dataset_manifest_path"], "reports/data_flywheel/run-a/location_dataset_manifest.md")
        payload = json.dumps(summary)
        self.assertNotIn("training_candidates.db", payload)
        self.assertNotIn("record_json", payload)

    def test_data_flywheel_missing_returns_explainable_not_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary = message_hub.load_latest_data_flywheel_status(Path(tmp))

        self.assertFalse(summary["available"])
        self.assertEqual(summary["status"], "not_available")
        self.assertEqual(summary["reason"], "no_data_flywheel_status_report")

    def test_latest_training_experiment_summary_is_bounded_for_dashboard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_dir = root / "unit-experiment"
            report_dir.mkdir(parents=True)
            (report_dir / "training_experiment_plan.json").write_text(
                json.dumps(
                    {
                        "schema_version": "egolink.training_experiment_plan.v0.1",
                        "builder_version": "train-002.0",
                        "experiment_id": "unit-experiment",
                        "created_at": "2026-07-05T06:20:00+00:00",
                        "status": "ready_for_runner",
                        "reason": "reviewed_dataset_manifest_available",
                        "dataset": {
                            "dataset_id": "unit-dataset",
                            "manifest_status": "ready_for_training_handoff",
                            "manifest_reason": "reviewed_candidates_available",
                            "records_total": 1,
                            "eligible_records": 1,
                            "reviewed_training_candidate_records": 1,
                            "split_counts": {"train": 1},
                            "record_sample": [
                                {
                                    "record_id": "cand-unit",
                                    "session_id": "session-unit",
                                    "candidate_type": "sos_confirmation",
                                    "label": "needs_help",
                                    "split_name": "train",
                                    "source_manifest_hash": "abc123",
                                    "recording_path": "C:/private/raw/session",
                                }
                            ],
                        },
                        "model_track": {
                            "track": "motionnet",
                            "candidate_model": "motionnet-v0.1-planned",
                            "baseline_model": "m0_rule_router",
                        },
                        "runner": {
                            "integration": "not_integrated",
                            "ready_for_handoff": True,
                            "training_server_endpoint": "https://private.example.invalid",
                            "next_command": "Integrate a runner task.",
                        },
                        "metrics_plan": {
                            "classification": {
                                "accuracy": "planned_not_measured",
                                "false_positive_rate": "planned_not_measured",
                            },
                            "operations": {
                                "latency_ms": "planned_not_measured",
                                "ram_bytes": "planned_not_measured",
                                "energy_per_inference": "planned_not_measured",
                            },
                        },
                        "gates": {
                            "dataset_ready": True,
                            "privacy_review": "inherited_from_dataset_manifest",
                            "consent_review": "inherited_from_dataset_manifest",
                            "split_leakage": "inherited_from_dataset_manifest",
                            "baseline_comparison": "planned_not_run",
                            "footprint": "planned_not_measured",
                            "power": "planned_not_measured",
                            "rollback_plan": "planned_not_written",
                        },
                        "non_claims": ["No model training has run."],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (report_dir / "training_experiment_plan.md").write_text("# Plan\n", encoding="utf-8")

            summary = message_hub.load_latest_training_experiment_plan(root)

        self.assertTrue(summary["available"])
        self.assertEqual(summary["status"], "ready_for_runner")
        self.assertEqual(summary["experiment_id"], "unit-experiment")
        self.assertEqual(summary["dataset"]["eligible_records"], 1)
        self.assertTrue(summary["runner"]["ready_for_handoff"])
        self.assertEqual(summary["runner"]["integration"], "not_integrated")
        self.assertEqual(summary["metrics_plan"]["operations"]["latency_ms"], "planned_not_measured")
        self.assertEqual(summary["gates"]["baseline_comparison"], "planned_not_run")
        self.assertEqual(summary["dataset"]["record_sample"][0]["record_id"], "cand-unit")
        payload = json.dumps(summary)
        self.assertNotIn("recording_path", payload)
        self.assertNotIn("C:/private", payload)
        self.assertNotIn("private.example.invalid", payload)
        self.assertNotIn("record_json", payload)

    def test_training_experiment_missing_returns_explainable_not_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary = message_hub.load_latest_training_experiment_plan(Path(tmp))

        self.assertFalse(summary["available"])
        self.assertEqual(summary["status"], "not_available")
        self.assertEqual(summary["reason"], "no_training_experiment_plan")

    def test_latest_training_run_preflight_summary_is_bounded_for_dashboard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_dir = root / "unit-preflight"
            report_dir.mkdir(parents=True)
            (report_dir / "training_run_preflight.json").write_text(
                json.dumps(
                    {
                        "schema_version": "egolink.training_run_preflight.v0.1",
                        "builder_version": "train-003.0",
                        "run_id": "unit-preflight",
                        "created_at": "2026-07-05T11:30:00+00:00",
                        "status": "ready_for_training_runner",
                        "reason": "bounded_dataset_and_experiment_handoff_ready",
                        "experiment": {
                            "experiment_id": "unit-experiment",
                            "status": "ready_for_runner",
                            "reason": "reviewed_dataset_manifest_available",
                            "model_track": {
                                "track": "motionnet",
                                "candidate_model": "motionnet-v0.1-planned",
                                "baseline_model": "m0_rule_router",
                            },
                            "plan_ref": "training_experiment_plan.json",
                            "private_plan_path": "C:/private/training_experiment_plan.json",
                        },
                        "dataset": {
                            "dataset_id": "unit-dataset",
                            "status": "ready_for_training_handoff",
                            "reason": "reviewed_candidates_available",
                            "manifest_ref": "training_dataset_manifest.json",
                            "private_manifest_path": "C:/private/training_dataset_manifest.json",
                            "records_total": 1,
                            "eligible_records": 1,
                            "reviewed_training_candidate_records": 1,
                            "experiment_records_total": 1,
                            "split_counts": {"train": 1},
                            "label_counts": {"needs_help": 1},
                            "source_status_counts": {"synthetic_generated": 1},
                            "synthetic_records": 1,
                            "synthetic_allowed_for_dry_run": True,
                            "record_sample": [
                                {
                                    "record_id": "cand-unit",
                                    "session_id": "session-unit",
                                    "candidate_type": "uncertain",
                                    "label": "needs_help",
                                    "split_name": "train",
                                    "source_status": "synthetic_generated",
                                    "source_manifest_hash": "abc123",
                                    "recording_path": "C:/private/raw/session",
                                }
                            ],
                        },
                        "checks": {
                            "experiment_ready": True,
                            "dataset_ready": True,
                            "has_eligible_records": True,
                            "required_record_fields": "pass",
                            "missing_record_fields": {},
                            "split_counts": {"train": 1},
                            "synthetic_record_policy": "acknowledged",
                        },
                        "runner": {
                            "integration": "local_preflight_only",
                            "ready_for_training_runner": True,
                            "training_server_endpoint": "https://private.example.invalid",
                            "next_step": "Connect a runner.",
                        },
                        "metrics_plan": {
                            "planned": {"classification": {"accuracy": "planned_not_measured"}},
                            "measured": {
                                "classification": "not_run",
                                "operations": "not_run",
                                "footprint": "not_run",
                                "power": "not_run",
                            },
                        },
                        "gates": {
                            "preflight_ready": True,
                            "dataset_gate": "ready_for_training_handoff",
                            "experiment_gate": "ready_for_runner",
                            "synthetic_gate": "acknowledged",
                            "model_training": "not_run",
                            "model_evaluation": "not_run",
                            "model_artifact": "not_produced",
                            "training_server": "not_integrated",
                            "device_deployment": "not_started",
                        },
                        "next_step": "Connect a runner.",
                        "non_claims": ["No model training has run."],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (report_dir / "training_run_preflight.md").write_text("# Preflight\n", encoding="utf-8")

            summary = message_hub.load_latest_training_run_preflight(root)

        self.assertTrue(summary["available"])
        self.assertEqual(summary["status"], "ready_for_training_runner")
        self.assertEqual(summary["run_id"], "unit-preflight")
        self.assertEqual(summary["dataset"]["eligible_records"], 1)
        self.assertEqual(summary["dataset"]["synthetic_records"], 1)
        self.assertTrue(summary["runner"]["ready_for_training_runner"])
        self.assertEqual(summary["checks"]["synthetic_record_policy"], "acknowledged")
        self.assertEqual(summary["metrics_plan"]["measured"]["classification"], "not_run")
        self.assertEqual(summary["gates"]["model_artifact"], "not_produced")
        self.assertEqual(summary["dataset"]["record_sample"][0]["record_id"], "cand-unit")
        payload = json.dumps(summary)
        self.assertNotIn("recording_path", payload)
        self.assertNotIn("private_manifest_path", payload)
        self.assertNotIn("C:/private", payload)
        self.assertNotIn("private.example.invalid", payload)
        self.assertNotIn("record_json", payload)

    def test_training_run_preflight_missing_returns_explainable_not_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary = message_hub.load_latest_training_run_preflight(Path(tmp))

        self.assertFalse(summary["available"])
        self.assertEqual(summary["status"], "not_available")
        self.assertEqual(summary["reason"], "no_training_run_preflight")

    def test_latest_training_feature_manifest_summary_is_bounded_for_dashboard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_dir = root / "unit-features"
            report_dir.mkdir(parents=True)
            (report_dir / "training_feature_manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": "egolink.training_feature_manifest.v0.1",
                        "builder_version": "train-004.0",
                        "feature_set_id": "unit-features",
                        "generated_at": "2026-07-05T12:00:00+00:00",
                        "status": "ready_for_synthetic_feature_dry_run",
                        "reason": "bounded_synthetic_feature_rows_ready_for_runner_dry_run",
                        "source_refs": {
                            "dataset_manifest_ref": "training_dataset_manifest.json",
                            "private_dataset_manifest_path": "C:/private/training_dataset_manifest.json",
                        },
                        "dataset": {
                            "dataset_id": "unit-dataset",
                            "status": "ready_for_training_handoff",
                            "reason": "reviewed_candidates_available",
                            "records_total": 1,
                            "eligible_records": 1,
                            "reviewed_training_candidate_records": 1,
                            "split_counts": {"train": 1},
                            "label_counts": {"needs_help": 1},
                            "source_status_counts": {"synthetic_generated": 1},
                            "synthetic_records": 1,
                            "synthetic_allowed_for_dry_run": True,
                            "recording_path": "C:/private/raw/session",
                        },
                        "preflight": {
                            "run_id": "unit-preflight",
                            "status": "ready_for_training_runner",
                            "reason": "bounded_dataset_and_experiment_handoff_ready",
                            "dataset_id": "unit-dataset",
                            "runner_ready": True,
                            "metrics_measured": {
                                "classification": "not_run",
                                "operations": "not_run",
                                "power": "not_run",
                            },
                            "training_server_endpoint": "https://private.example.invalid",
                        },
                        "feature_rows": {
                            "row_schema_version": "egolink.training_feature_row.v0.1",
                            "row_count": 1,
                            "rows_ref": "training_feature_rows.jsonl",
                            "feature_groups": ["imu_motion"],
                            "feature_scope": "manifest_summary_features",
                            "target_separated_from_features": True,
                            "row_sample": [{"raw_payload": "secret"}],
                        },
                        "checks": {
                            "dataset_ready": True,
                            "preflight_ready": True,
                            "source_match": True,
                            "has_records": True,
                            "required_record_fields": "pass",
                            "missing_record_fields": {},
                            "synthetic_record_policy": "acknowledged",
                            "label_leakage_guard": "target_separated_from_features",
                        },
                        "gates": {
                            "feature_export": "pass",
                            "training_runner": "not_integrated",
                            "model_training": "not_run",
                            "model_evaluation": "not_run",
                            "model_artifact": "not_produced",
                            "training_server": "not_integrated",
                            "device_deployment": "not_started",
                        },
                        "paths": {
                            "training_feature_manifest_json": "training_feature_manifest.json",
                            "training_feature_rows_jsonl": "C:/private/training_feature_rows.jsonl",
                        },
                        "next_step": "Dry-run only.",
                        "non_claims": ["No model training has run."],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (report_dir / "training_feature_manifest.md").write_text("# Feature Manifest\n", encoding="utf-8")

            summary = message_hub.load_latest_training_feature_manifest(root)

        self.assertTrue(summary["available"])
        self.assertEqual(summary["status"], "ready_for_synthetic_feature_dry_run")
        self.assertEqual(summary["feature_set_id"], "unit-features")
        self.assertEqual(summary["dataset"]["eligible_records"], 1)
        self.assertEqual(summary["preflight"]["run_id"], "unit-preflight")
        self.assertTrue(summary["preflight"]["runner_ready"])
        self.assertEqual(summary["feature_rows"]["row_count"], 1)
        self.assertEqual(summary["feature_rows"]["feature_scope"], "manifest_summary_features")
        self.assertTrue(summary["feature_rows"]["target_separated_from_features"])
        self.assertEqual(summary["checks"]["label_leakage_guard"], "target_separated_from_features")
        self.assertEqual(summary["gates"]["model_artifact"], "not_produced")
        payload = json.dumps(summary)
        self.assertNotIn("recording_path", payload)
        self.assertNotIn("private_dataset_manifest_path", payload)
        self.assertNotIn("row_sample", payload)
        self.assertNotIn("raw_payload", payload)
        self.assertNotIn("C:/private", payload)
        self.assertNotIn("private.example.invalid", payload)

    def test_training_feature_manifest_missing_returns_explainable_not_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary = message_hub.load_latest_training_feature_manifest(Path(tmp))

        self.assertFalse(summary["available"])
        self.assertEqual(summary["status"], "not_available")
        self.assertEqual(summary["reason"], "no_training_feature_manifest")

    def test_latest_training_runner_dry_run_summary_is_bounded_for_dashboard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_dir = root / "unit-runner"
            report_dir.mkdir(parents=True)
            (report_dir / "training_runner_dry_run.json").write_text(
                json.dumps(
                    {
                        "schema_version": "egolink.training_runner_dry_run.v0.1",
                        "builder_version": "train-005.0",
                        "run_id": "unit-runner",
                        "created_at": "2026-07-05T12:45:00+00:00",
                        "status": "synthetic_runner_dry_run_complete",
                        "reason": "runner_input_contract_validated_with_synthetic_dry_run_rows",
                        "feature_manifest": {
                            "feature_set_id": "unit-features",
                            "status": "ready_for_synthetic_feature_dry_run",
                            "reason": "bounded_synthetic_feature_rows_ready_for_runner_dry_run",
                            "feature_scope": "manifest_summary_features",
                            "target_separated_from_features": True,
                            "private_manifest_path": "C:/private/training_feature_manifest.json",
                        },
                        "dataset": {
                            "dataset_id": "unit-dataset",
                            "status": "ready_for_training_handoff",
                            "eligible_records": 1,
                            "synthetic_records": 1,
                            "recording_path": "C:/private/raw/session",
                        },
                        "preflight": {
                            "run_id": "unit-preflight",
                            "status": "ready_for_training_runner",
                            "runner_ready": True,
                            "metrics_measured": {
                                "classification": "not_run",
                                "operations": "not_run",
                                "power": "not_run",
                            },
                            "training_server_endpoint": "https://private.example.invalid",
                        },
                        "feature_rows": {
                            "expected_row_count": 1,
                            "actual_row_count": 1,
                            "row_count_matches": True,
                            "feature_set_mismatch_count": 0,
                            "split_counts": {"train": 1},
                            "label_counts": {"needs_help": 1},
                            "source_status_counts": {"synthetic_generated": 1},
                            "feature_group_counts": {"imu_motion": 1},
                            "synthetic_rows": 1,
                            "synthetic_allowed_for_dry_run": True,
                            "row_sample": [{"raw_payload": "secret"}],
                        },
                        "checks": {
                            "feature_manifest_ready": True,
                            "feature_rows_readable": True,
                            "row_count_matches": True,
                            "required_row_fields": "pass",
                            "missing_row_fields": {},
                            "target_leakage_guard": "pass",
                            "target_leakage_violations": {},
                            "synthetic_row_policy": "acknowledged",
                            "manifest_feature_export_gate": "pass",
                        },
                        "runner": {
                            "integration": "local_runner_dry_run",
                            "ready_for_real_runner": False,
                            "dry_run_only": True,
                            "training_server_endpoint": "https://private.example.invalid",
                            "next_step": "Dry-run only.",
                        },
                        "metrics_plan": {
                            "measured": {
                                "classification": "not_run",
                                "operations": "not_run",
                                "power": "not_run",
                            },
                            "dry_run_summary": {
                                "labels": {"needs_help": 1},
                                "splits": {"train": 1},
                                "feature_groups": {"imu_motion": 1},
                            },
                        },
                        "gates": {
                            "runner_input": "pass",
                            "model_training": "not_run",
                            "model_evaluation": "not_run",
                            "model_artifact": "not_produced",
                            "training_server": "not_integrated",
                            "device_deployment": "not_started",
                        },
                        "paths": {
                            "training_runner_dry_run_json": "training_runner_dry_run.json",
                            "private_artifact_path": "C:/private/model.bin",
                        },
                        "next_step": "Dry-run only.",
                        "non_claims": ["No model training has run."],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (report_dir / "training_runner_dry_run.md").write_text("# Runner Dry-Run\n", encoding="utf-8")

            summary = message_hub.load_latest_training_runner_dry_run(root)

        self.assertTrue(summary["available"])
        self.assertEqual(summary["status"], "synthetic_runner_dry_run_complete")
        self.assertEqual(summary["run_id"], "unit-runner")
        self.assertEqual(summary["feature_manifest"]["feature_set_id"], "unit-features")
        self.assertEqual(summary["feature_rows"]["actual_row_count"], 1)
        self.assertEqual(summary["feature_rows"]["label_counts"], {"needs_help": 1})
        self.assertTrue(summary["runner"]["dry_run_only"])
        self.assertEqual(summary["checks"]["target_leakage_guard"], "pass")
        self.assertEqual(summary["metrics_plan"]["measured"]["classification"], "not_run")
        self.assertEqual(summary["gates"]["model_artifact"], "not_produced")
        payload = json.dumps(summary)
        self.assertNotIn("recording_path", payload)
        self.assertNotIn("private_manifest_path", payload)
        self.assertNotIn("row_sample", payload)
        self.assertNotIn("raw_payload", payload)
        self.assertNotIn("private_artifact_path", payload)
        self.assertNotIn("C:/private", payload)
        self.assertNotIn("private.example.invalid", payload)

    def test_training_runner_dry_run_missing_returns_explainable_not_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary = message_hub.load_latest_training_runner_dry_run(Path(tmp))

        self.assertFalse(summary["available"])
        self.assertEqual(summary["status"], "not_available")
        self.assertEqual(summary["reason"], "no_training_runner_dry_run")

    def test_latest_training_baseline_eval_summary_is_bounded_for_dashboard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_dir = root / "unit-eval"
            report_dir.mkdir()
            (report_dir / "training_baseline_eval.json").write_text(
                json.dumps(
                    {
                        "schema_version": "egolink.training_baseline_eval.v0.1",
                        "eval_id": "unit-eval",
                        "created_at": "2026-07-06T00:30:00+00:00",
                        "status": "synthetic_baseline_eval_complete",
                        "reason": "synthetic_rows_evaluated_for_runner_integration_only",
                        "feature_manifest": {
                            "feature_set_id": "unit-features",
                            "status": "ready_for_synthetic_feature_dry_run",
                            "feature_scope": "manifest_summary_features",
                            "target_separated_from_features": True,
                        },
                        "runner_dry_run": {
                            "run_id": "unit-runner",
                            "status": "synthetic_runner_dry_run_complete",
                            "runner_input_gate": "pass",
                            "dry_run_only": True,
                        },
                        "dataset": {
                            "dataset_id": "unit-dataset",
                            "status": "ready_for_training_handoff",
                            "eligible_records": 1,
                            "synthetic_records": 1,
                        },
                        "feature_rows": {
                            "expected_row_count": 1,
                            "actual_row_count": 1,
                            "row_count_matches": True,
                            "runner_actual_row_count": 1,
                            "runner_row_count_matches": True,
                            "split_counts": {"test": 1},
                            "label_counts": {"needs_help": 1},
                            "risk_type_counts": {"uncertain": 1},
                            "candidate_type_counts": {"uncertain": 1},
                            "source_status_counts": {"synthetic_generated": 1},
                            "synthetic_rows": 1,
                            "synthetic_allowed_for_eval": True,
                            "row_sample": [{"private": "do-not-expose"}],
                        },
                        "checks": {
                            "feature_manifest_ready": True,
                            "runner_dry_run_ready": True,
                            "feature_rows_readable": True,
                            "row_count_matches": True,
                            "required_row_fields": "pass",
                            "missing_row_fields": {},
                            "target_leakage_guard": "pass",
                            "target_leakage_violations": {},
                            "synthetic_row_policy": "acknowledged",
                        },
                        "metrics": {
                            "scope": "synthetic_integration_only",
                            "measured_from_rows": True,
                            "classification": {
                                "baselines": [
                                    {
                                        "name": "candidate_type_risk_baseline",
                                        "overall": {"total": 1, "correct": 1, "accuracy": 1.0},
                                        "private_case_rows": [{"row_id": "secret"}],
                                    }
                                ],
                                "product_performance_claim": False,
                                "release_metric": False,
                            },
                            "operations": "not_run",
                            "footprint": "not_run",
                            "power": "not_run",
                        },
                        "gates": {
                            "baseline_evaluation": "pass",
                            "model_training": "not_run",
                            "model_artifact": "not_produced",
                            "model_card": "not_produced",
                            "training_server": "not_integrated",
                            "model_registry": "not_integrated",
                            "device_deployment": "not_started",
                            "release_claim": "not_allowed",
                        },
                        "source_refs": {
                            "feature_rows_ref": "training_feature_rows.jsonl",
                            "private_training_endpoint": "https://private.example.invalid",
                        },
                        "private_artifact_path": "C:/private/model.bin",
                        "non_claims": ["Synthetic baseline metrics are integration metrics only."],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (report_dir / "training_baseline_eval.md").write_text("# Baseline Eval\n", encoding="utf-8")

            summary = message_hub.load_latest_training_baseline_eval(root)

        self.assertTrue(summary["available"])
        self.assertEqual(summary["status"], "synthetic_baseline_eval_complete")
        self.assertEqual(summary["eval_id"], "unit-eval")
        self.assertEqual(summary["feature_rows"]["actual_row_count"], 1)
        self.assertEqual(summary["feature_rows"]["risk_type_counts"], {"uncertain": 1})
        self.assertEqual(summary["checks"]["synthetic_row_policy"], "acknowledged")
        self.assertEqual(summary["metrics"]["scope"], "synthetic_integration_only")
        self.assertEqual(summary["metrics"]["classification"]["baselines"][0]["overall"]["accuracy"], 1.0)
        self.assertFalse(summary["metrics"]["classification"]["product_performance_claim"])
        self.assertEqual(summary["gates"]["model_artifact"], "not_produced")
        self.assertEqual(summary["gates"]["release_claim"], "not_allowed")
        payload = json.dumps(summary)
        self.assertNotIn("row_sample", payload)
        self.assertNotIn("private_case_rows", payload)
        self.assertNotIn("private_artifact_path", payload)
        self.assertNotIn("C:/private", payload)
        self.assertNotIn("private.example.invalid", payload)

    def test_training_baseline_eval_missing_returns_explainable_not_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary = message_hub.load_latest_training_baseline_eval(Path(tmp))

        self.assertFalse(summary["available"])
        self.assertEqual(summary["status"], "not_available")
        self.assertEqual(summary["reason"], "no_training_baseline_eval")

    def test_latest_d1_labeling_intake_summary_is_bounded_for_dashboard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_dir = root / "unit-intake"
            report_dir.mkdir()
            (report_dir / "d1_labeling_intake.json").write_text(
                json.dumps(
                    {
                        "schema_version": "egolink.d1_labeling_intake.v0.1",
                        "run_id": "unit-intake",
                        "generated_at": "2026-07-06T11:35:00+00:00",
                        "serves_demo": "D5",
                        "status": "pending_human_review",
                        "reason": "d1_run_waiting_for_label_privacy_consent_and_split_review",
                        "source_readiness": {
                            "run_id": "unit-readiness",
                            "status": "ready_for_labeling_review",
                            "reason": "field_observation_can_enter_human_review_but_not_training",
                            "report_path": "reports/d1_training_readiness/unit/d1_training_readiness.json",
                        },
                        "source_observation": {
                            "run_id": "field-private",
                            "status": "completed",
                            "result": "PASS",
                            "device_id": "ego-link-r1-connectivity-001",
                            "sample_count": 5,
                            "successful_sample_count": 5,
                            "latest_seq": 52,
                            "max_freshness_s": 62,
                            "last_location_upload_at": "2026-07-06T11:20:18+00:00",
                            "samples_jsonl_read": False,
                            "coordinate_values_copied": False,
                            "lat": 31.123456,
                            "lon": 121.654321,
                        },
                        "evidence_coverage": {
                            "transport": {
                                "raw_post_success_delta": 2,
                                "raw_post_failure_delta": 0,
                                "lte_registration_seen": True,
                                "pdp_active_seen": True,
                            },
                            "location": {
                                "coordinate_sample_count": 5,
                                "location_event_count_delta": 3,
                                "map_modes": ["memory_coordinate"],
                                "gnss_states": ["unknown"],
                                "gnss_fix_seen": False,
                                "coordinate_values_copied": False,
                                "accuracy_claimed": False,
                                "raw_location": {"lat": 31.123456, "lon": 121.654321},
                            },
                            "sensors": {
                                "imu_evidence_statuses": ["mock"],
                                "power_evidence_statuses": ["measured"],
                                "power_measured_seen": True,
                                "real_imu_seen": False,
                            },
                        },
                        "intake_queue": {
                            "available": True,
                            "pending_items": 1,
                            "next_queue": "training_candidate_store_after_review",
                            "items": [
                                {
                                    "intake_id": "d1-intake-unit",
                                    "source_run_id": "field-private",
                                    "readiness_run_id": "unit-readiness",
                                    "device_id": "ego-link-r1-connectivity-001",
                                    "status": "pending_label_privacy_split",
                                    "training_allowed": False,
                                    "candidate_record_written": False,
                                    "review_state": {
                                        "operator_label": "missing",
                                        "privacy_review": "required",
                                        "training_consent": "not_reviewed",
                                        "split_plan": "missing",
                                        "quality_gaps": ["gnss_fix_not_seen"],
                                    },
                                    "evidence_summary": {
                                        "samples": 5,
                                        "latest_seq": 52,
                                        "raw_post_success_delta": 2,
                                        "raw_post_failure_delta": 0,
                                        "coordinate_sample_count": 5,
                                        "gnss_fix_seen": False,
                                        "imu_evidence_statuses": ["mock"],
                                        "power_evidence_statuses": ["measured"],
                                        "private_coordinates": [31.123456, 121.654321],
                                    },
                                    "requested_actions": ["attach_operator_or_user_label"],
                                    "available_decisions": ["needs_more_capture", "ready_for_candidate_store"],
                                    "raw_payload": {"secret": True},
                                }
                            ],
                        },
                        "labeling_request": {
                            "taxonomy_version": "d1_location_review.v0.1",
                            "requested_label_groups": ["collection_context", "location_quality"],
                            "free_text_policy": "redacted_or_absent",
                            "exact_coordinates_visible": False,
                            "raw_payload_visible": False,
                        },
                        "review_gates": {
                            "training_readiness": "pass",
                            "operator_label": "blocked",
                            "privacy_review": "blocked",
                            "candidate_store": "not_written",
                            "model_training": "not_run",
                        },
                        "blockers": ["operator_label_missing", "privacy_review_required"],
                        "scope": {
                            "training_readiness_report_read": True,
                            "sample_jsonl_read": False,
                            "hardware_contacted": False,
                            "candidate_db_written": False,
                            "model_training_started": False,
                            "model_artifact_written": False,
                            "exact_coordinates_copied": False,
                            "release_claim_allowed": False,
                        },
                        "paths": {
                            "d1_labeling_intake_json": "reports/d1_labeling_intake/unit/d1_labeling_intake.json",
                            "private_candidate_db": "C:/private/training_candidates.db",
                        },
                        "raw_payload": {"private": True},
                        "features": {"private": "do-not-expose"},
                        "target": {"private": "do-not-expose"},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (report_dir / "d1_labeling_intake.md").write_text("# D1 Intake\n", encoding="utf-8")

            summary = message_hub.load_latest_d1_labeling_intake(root)

        self.assertTrue(summary["available"])
        self.assertEqual(summary["status"], "pending_human_review")
        self.assertEqual(summary["run_id"], "unit-intake")
        self.assertEqual(summary["intake_queue"]["pending_items"], 1)
        self.assertEqual(summary["intake_queue"]["items"][0]["intake_id"], "d1-intake-unit")
        self.assertFalse(summary["intake_queue"]["items"][0]["training_allowed"])
        self.assertFalse(summary["intake_queue"]["items"][0]["candidate_record_written"])
        self.assertEqual(summary["review_gates"]["candidate_store"], "not_written")
        self.assertFalse(summary["scope"]["sample_jsonl_read"])
        self.assertFalse(summary["scope"]["candidate_db_written"])
        self.assertFalse(summary["scope"]["exact_coordinates_copied"])
        self.assertEqual(summary["labeling_request"]["requested_label_groups"], ["collection_context", "location_quality"])
        payload = json.dumps(summary)
        self.assertNotIn("31.123456", payload)
        self.assertNotIn("121.654321", payload)
        self.assertNotIn("raw_payload", payload)
        self.assertNotIn('"features"', payload)
        self.assertNotIn('"target"', payload)
        self.assertNotIn("private_candidate_db", payload)
        self.assertNotIn("C:/private", payload)

    def test_d1_labeling_intake_missing_returns_explainable_not_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary = message_hub.load_latest_d1_labeling_intake(Path(tmp))

        self.assertFalse(summary["available"])
        self.assertEqual(summary["status"], "not_available")
        self.assertEqual(summary["reason"], "no_d1_labeling_intake")

    def test_latest_d1_labeling_queue_summary_is_bounded_for_dashboard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_dir = root / "unit-queue"
            report_dir.mkdir()
            (report_dir / "d1_labeling_queue.json").write_text(
                json.dumps(
                    {
                        "schema_version": "egolink.d1_labeling_queue.v0.1",
                        "run_id": "unit-labeling-queue",
                        "generated_at": "2026-07-06T12:05:00+00:00",
                        "serves_demo": "D5",
                        "status": "pending_human_review",
                        "summary": {
                            "intake_report_count": 1,
                            "pending_item_count": 1,
                            "not_ready_report_count": 0,
                            "error_count": 0,
                            "training_allowed_count": 0,
                            "candidate_record_written_count": 0,
                        },
                        "queue": {
                            "next_queue": "training_candidate_store_after_review",
                            "items": [
                                {
                                    "intake_id": "d1-intake-unit",
                                    "intake_run_id": "unit-intake",
                                    "source_run_id": "field-private",
                                    "readiness_run_id": "unit-readiness",
                                    "device_id": "ego-link-r1-connectivity-001",
                                    "status": "pending_label_privacy_split",
                                    "review_state": {
                                        "operator_label": "missing",
                                        "privacy_review": "required",
                                        "training_consent": "not_reviewed",
                                        "split_plan": "missing",
                                        "quality_gaps": ["gnss_fix_not_seen"],
                                    },
                                    "evidence_summary": {
                                        "samples": 5,
                                        "latest_seq": 52,
                                        "raw_post_success_delta": 2,
                                        "raw_post_failure_delta": 0,
                                        "coordinate_sample_count": 5,
                                        "gnss_fix_seen": False,
                                        "imu_evidence_statuses": ["mock"],
                                        "power_evidence_statuses": ["measured"],
                                        "private_coordinates": [31.123456, 121.654321],
                                    },
                                    "requested_actions": ["attach_operator_or_user_label"],
                                    "available_decisions": ["needs_more_capture", "reject_for_training"],
                                    "training_allowed": True,
                                    "candidate_record_written": True,
                                    "intake_report_path": "ready/d1_labeling_intake.json",
                                    "raw_payload": {"secret": True},
                                }
                            ],
                        },
                        "intake_reports": [
                            {
                                "run_id": "unit-intake",
                                "status": "pending_human_review",
                                "pending_items": 1,
                                "report_path": "ready/d1_labeling_intake.json",
                                "markdown_report_path": "ready/d1_labeling_intake.md",
                                "training_allowed": True,
                                "candidate_record_written": True,
                                "private_candidate_db": "C:/private/training_candidates.db",
                            }
                        ],
                        "review_gates": {
                            "labeling_intake": "pass",
                            "operator_label": "blocked",
                            "privacy_review": "blocked",
                            "candidate_store": "not_written",
                            "model_training": "not_run",
                        },
                        "blockers": ["operator_label_missing", "privacy_review_required"],
                        "scope": {
                            "intake_summaries_read": True,
                            "sample_jsonl_read": False,
                            "hardware_contacted": False,
                            "candidate_db_written": False,
                            "training_samples_written": False,
                            "model_training_started": False,
                            "model_artifact_written": False,
                            "exact_coordinates_copied": False,
                            "release_claim_allowed": False,
                        },
                        "paths": {
                            "d1_labeling_queue_json": "reports/d1_labeling_queue/unit/d1_labeling_queue.json",
                            "private_candidate_db": "C:/private/training_candidates.db",
                            "sample_jsonl": "C:/private/d1_field_samples.jsonl",
                        },
                        "raw_payload": {"private": True},
                        "features": {"private": "do-not-expose"},
                        "target": {"private": "do-not-expose"},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (report_dir / "d1_labeling_queue.md").write_text("# D1 Labeling Queue\n", encoding="utf-8")

            summary = message_hub.load_latest_d1_labeling_queue(root)

        self.assertTrue(summary["available"])
        self.assertEqual(summary["status"], "pending_human_review")
        self.assertEqual(summary["run_id"], "unit-labeling-queue")
        self.assertEqual(summary["summary"]["pending_items"], 1)
        self.assertEqual(summary["summary"]["needs_operator_label"], 1)
        self.assertEqual(summary["summary"]["needs_privacy_review"], 1)
        self.assertEqual(summary["summary"]["needs_training_consent"], 1)
        self.assertEqual(summary["summary"]["needs_split_plan"], 1)
        self.assertEqual(summary["queue"]["pending_items"], 1)
        self.assertEqual(summary["queue"]["next_queue"], "training_candidate_store_after_review")
        self.assertEqual(summary["queue"]["items"][0]["intake_id"], "d1-intake-unit")
        self.assertFalse(summary["queue"]["items"][0]["training_allowed"])
        self.assertFalse(summary["queue"]["items"][0]["candidate_record_written"])
        self.assertFalse(summary["intake_reports"][0]["training_allowed"])
        self.assertFalse(summary["intake_reports"][0]["candidate_record_written"])
        self.assertFalse(summary["scope"]["sample_jsonl_read"])
        self.assertFalse(summary["scope"]["candidate_db_written"])
        self.assertFalse(summary["scope"]["exact_coordinates_copied"])
        payload = json.dumps(summary)
        self.assertNotIn("31.123456", payload)
        self.assertNotIn("121.654321", payload)
        self.assertNotIn("raw_payload", payload)
        self.assertNotIn('"features"', payload)
        self.assertNotIn('"target"', payload)
        self.assertNotIn("private_candidate_db", payload)
        self.assertNotIn("d1_field_samples.jsonl", payload)
        self.assertNotIn("C:/private", payload)

    def test_d1_labeling_queue_missing_returns_explainable_not_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary = message_hub.load_latest_d1_labeling_queue(Path(tmp))

        self.assertFalse(summary["available"])
        self.assertEqual(summary["status"], "not_available")
        self.assertEqual(summary["reason"], "no_d1_labeling_queue")

    def test_latest_d1_labeling_review_packet_summary_is_bounded_for_dashboard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_dir = root / "unit-review"
            report_dir.mkdir()
            (report_dir / "d1_labeling_review_packet.json").write_text(
                json.dumps(
                    {
                        "schema_version": "egolink.d1_labeling_review_packet.v0.1",
                        "run_id": "unit-labeling-review",
                        "generated_at": "2026-07-06T12:10:00+00:00",
                        "serves_demo": "D5",
                        "status": "needs_human_review",
                        "source_queue": {
                            "available": True,
                            "run_id": "unit-labeling-queue",
                            "status": "pending_human_review",
                            "report_path": "reports/d1_labeling_queue/unit/d1_labeling_queue.json",
                            "pending_item_count": 1,
                            "intake_report_count": 1,
                        },
                        "summary": {
                            "queue_pending_items": 1,
                            "review_packet_items": 1,
                            "needs_operator_label": 1,
                            "needs_privacy_review": 1,
                            "needs_training_consent": 1,
                            "needs_split_plan": 1,
                            "candidate_record_written_count": 0,
                            "training_allowed_count": 0,
                        },
                        "review_packet": {
                            "status": "open",
                            "items": [
                                {
                                    "packet_item_id": "d1-review-unit",
                                    "intake_id": "d1-intake-unit",
                                    "source_run_id": "field-private",
                                    "readiness_run_id": "unit-readiness",
                                    "device_id": "ego-link-r1-connectivity-001",
                                    "queue_status": "pending_label_privacy_split",
                                    "current_review_state": {
                                        "operator_label": "missing",
                                        "privacy_review": "required",
                                        "training_consent": "not_reviewed",
                                        "split_plan": "missing",
                                        "quality_gaps": ["gnss_fix_not_seen"],
                                    },
                                    "evidence_summary": {
                                        "samples": 5,
                                        "latest_seq": 52,
                                        "raw_post_success_delta": 2,
                                        "raw_post_failure_delta": 0,
                                        "coordinate_sample_count": 5,
                                        "gnss_fix_seen": False,
                                        "imu_evidence_statuses": ["mock"],
                                        "power_evidence_statuses": ["measured"],
                                        "private_coordinates": [31.123456, 121.654321],
                                    },
                                    "decision_slots": {
                                        "operator_label": {
                                            "required": True,
                                            "current": "missing",
                                            "selected": None,
                                            "allowed_values": ["safe", "needs_help"],
                                            "reviewed_by": "private-operator",
                                        },
                                        "privacy_review": {
                                            "required": True,
                                            "current": "required",
                                            "selected": None,
                                            "allowed_values": ["approved_bounded_summary_only"],
                                            "reviewed_at": "private-time",
                                        },
                                    },
                                    "requested_actions": ["attach_operator_or_user_label"],
                                    "available_decisions": ["needs_more_capture", "reject_for_training"],
                                    "training_allowed": True,
                                    "candidate_record_written": True,
                                    "raw_payload": {"secret": True},
                                }
                            ],
                            "decision_schema": {
                                "operator_label": ["safe", "needs_help"],
                                "candidate_decision": ["ready_for_candidate_store", "reject_for_training"],
                            },
                            "apply_policy": "review_packet_must_be_applied_by_a_future_explicit_candidate_store_task",
                        },
                        "scope": {
                            "labeling_queue_summary_read": True,
                            "sample_jsonl_read": False,
                            "payload_bytes_copied": False,
                            "exact_coordinates_copied": False,
                            "feature_rows_copied": False,
                            "target_labels_written": False,
                            "candidate_db_written": False,
                            "training_samples_written": False,
                            "model_training_started": False,
                            "model_artifact_written": False,
                            "release_claim_allowed": False,
                        },
                        "paths": {
                            "private_candidate_db": "C:/private/training_candidates.db",
                            "sample_jsonl": "C:/private/d1_field_samples.jsonl",
                        },
                        "raw_payload": {"private": True},
                        "features": {"private": "do-not-expose"},
                        "target": {"private": "do-not-expose"},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (report_dir / "d1_labeling_review_packet.md").write_text("# D1 Labeling Review\n", encoding="utf-8")

            summary = message_hub.load_latest_d1_labeling_review_packet(root)

        self.assertTrue(summary["available"])
        self.assertEqual(summary["status"], "needs_human_review")
        self.assertEqual(summary["run_id"], "unit-labeling-review")
        self.assertEqual(summary["summary"]["review_packet_items"], 1)
        self.assertEqual(summary["summary"]["needs_operator_label"], 1)
        self.assertEqual(summary["source_queue"]["run_id"], "unit-labeling-queue")
        item = summary["review_packet"]["items"][0]
        self.assertEqual(item["packet_item_id"], "d1-review-unit")
        self.assertEqual(item["decision_slots"]["operator_label"]["current"], "missing")
        self.assertIn("safe", item["decision_slots"]["operator_label"]["allowed_values"])
        self.assertFalse(item["training_allowed"])
        self.assertFalse(item["candidate_record_written"])
        self.assertFalse(summary["scope"]["sample_jsonl_read"])
        self.assertFalse(summary["scope"]["payload_bytes_copied"])
        self.assertFalse(summary["scope"]["candidate_db_written"])
        self.assertEqual(summary["review_gates"]["candidate_store"], "not_written")
        payload = json.dumps(summary)
        self.assertNotIn("31.123456", payload)
        self.assertNotIn("121.654321", payload)
        self.assertNotIn("raw_payload", payload)
        self.assertNotIn("private-operator", payload)
        self.assertNotIn("private-time", payload)
        self.assertNotIn('"features"', payload)
        self.assertNotIn('"target"', payload)
        self.assertNotIn("private_candidate_db", payload)
        self.assertNotIn("d1_field_samples.jsonl", payload)
        self.assertNotIn("C:/private", payload)

    def test_d1_labeling_review_packet_missing_returns_explainable_not_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary = message_hub.load_latest_d1_labeling_review_packet(Path(tmp))

        self.assertFalse(summary["available"])
        self.assertEqual(summary["status"], "not_available")
        self.assertEqual(summary["reason"], "no_d1_labeling_review_packet")

    def test_latest_d1_labeling_decision_template_summary_is_bounded_for_dashboard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_dir = root / "unit-decisions"
            report_dir.mkdir()
            (report_dir / "d1_labeling_decision_template.json").write_text(
                json.dumps(
                    {
                        "schema_version": "egolink.d1_labeling_decision_template.v0.1",
                        "run_id": "unit-labeling-decisions",
                        "generated_at": "2026-07-06T12:20:00+00:00",
                        "serves_demo": "D5",
                        "status": "ready_for_human_input",
                        "source_review_packet": {
                            "available": True,
                            "run_id": "unit-labeling-review",
                            "status": "needs_human_review",
                            "report_path": "reports/d1_labeling_reviews/unit/d1_labeling_review_packet.json",
                            "review_packet_items": 1,
                        },
                        "summary": {
                            "template_items": 1,
                            "review_packet_items": 1,
                            "queue_pending_items": 1,
                            "required_decision_fields": 5,
                            "selected_decision_fields": 0,
                            "items_ready_for_validation": 0,
                            "candidate_record_written_count": 0,
                            "training_allowed_count": 0,
                            "ready_for_candidate_promotion": False,
                        },
                        "decision_template": {
                            "status": "open",
                            "items": [
                                {
                                    "packet_item_id": "d1-review-unit",
                                    "intake_id": "d1-intake-unit",
                                    "source_run_id": "field-private",
                                    "readiness_run_id": "unit-readiness",
                                    "device_id": "ego-link-r1-connectivity-001",
                                    "queue_status": "pending_label_privacy_split",
                                    "current_review_state": {
                                        "operator_label": "missing",
                                        "privacy_review": "required",
                                        "training_consent": "not_reviewed",
                                        "split_plan": "missing",
                                        "quality_gaps": ["gnss_fix_not_seen"],
                                    },
                                    "evidence_summary": {
                                        "samples": 5,
                                        "latest_seq": 52,
                                        "raw_post_success_delta": 2,
                                        "raw_post_failure_delta": 0,
                                        "coordinate_sample_count": 5,
                                        "gnss_fix_seen": False,
                                        "imu_evidence_statuses": ["mock"],
                                        "power_evidence_statuses": ["measured"],
                                        "private_coordinates": [31.123456, 121.654321],
                                    },
                                    "decision_fields": {
                                        "operator_label": {
                                            "required": True,
                                            "current": "missing",
                                            "selected": None,
                                            "allowed_values": ["safe", "needs_help"],
                                            "operator_note": "private-note",
                                        },
                                        "privacy_review": {
                                            "required": True,
                                            "current": "required",
                                            "selected": None,
                                            "allowed_values": ["approved_bounded_summary_only"],
                                        },
                                        "candidate_decision": {
                                            "required": True,
                                            "current": "not_reviewed",
                                            "selected": None,
                                            "allowed_values": ["ready_for_candidate_store", "reject_for_training"],
                                        },
                                    },
                                    "requested_actions": ["attach_operator_or_user_label"],
                                    "available_decisions": ["needs_more_capture", "reject_for_training"],
                                    "validation_state": "not_submitted",
                                    "training_allowed": True,
                                    "candidate_record_written": True,
                                    "raw_payload": {"secret": True},
                                }
                            ],
                            "decision_schema": {
                                "operator_label": ["safe", "needs_help"],
                                "candidate_decision": ["ready_for_candidate_store", "reject_for_training"],
                            },
                            "apply_policy": "template_must_be_validated_by_a_future_explicit_review_application_task",
                        },
                        "scope": {
                            "review_packet_summary_read": True,
                            "sample_jsonl_read": False,
                            "payload_bytes_copied": False,
                            "exact_coordinates_copied": False,
                            "feature_rows_copied": False,
                            "target_labels_written": False,
                            "candidate_db_written": False,
                            "training_samples_written": False,
                            "model_training_started": False,
                            "model_artifact_written": False,
                            "release_claim_allowed": False,
                        },
                        "paths": {
                            "private_candidate_db": "C:/private/training_candidates.db",
                            "sample_jsonl": "C:/private/d1_field_samples.jsonl",
                        },
                        "raw_payload": {"private": True},
                        "features": {"private": "do-not-expose"},
                        "target": {"private": "do-not-expose"},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (report_dir / "d1_labeling_decision_template.md").write_text("# D1 Decisions\n", encoding="utf-8")

            summary = message_hub.load_latest_d1_labeling_decision_template(root)

        self.assertTrue(summary["available"])
        self.assertEqual(summary["status"], "ready_for_human_input")
        self.assertEqual(summary["run_id"], "unit-labeling-decisions")
        self.assertEqual(summary["summary"]["template_items"], 1)
        self.assertEqual(summary["summary"]["required_decision_fields"], 5)
        self.assertEqual(summary["summary"]["selected_decision_fields"], 0)
        self.assertFalse(summary["summary"]["ready_for_candidate_promotion"])
        self.assertEqual(summary["source_review_packet"]["run_id"], "unit-labeling-review")
        item = summary["decision_template"]["items"][0]
        self.assertEqual(item["packet_item_id"], "d1-review-unit")
        self.assertIn("safe", item["decision_fields"]["operator_label"]["allowed_values"])
        self.assertIsNone(item["decision_fields"]["operator_label"].get("selected"))
        self.assertFalse(item["training_allowed"])
        self.assertFalse(item["candidate_record_written"])
        self.assertFalse(summary["scope"]["sample_jsonl_read"])
        self.assertFalse(summary["scope"]["payload_bytes_copied"])
        self.assertFalse(summary["scope"]["candidate_db_written"])
        self.assertEqual(summary["review_gates"]["candidate_store"], "not_written")
        payload = json.dumps(summary)
        self.assertNotIn("31.123456", payload)
        self.assertNotIn("121.654321", payload)
        self.assertNotIn("raw_payload", payload)
        self.assertNotIn("private-note", payload)
        self.assertNotIn("d1_field_samples.jsonl", payload)
        self.assertNotIn('"features"', payload)
        self.assertNotIn('"target"', payload)
        self.assertNotIn("C:/private", payload)

    def test_d1_labeling_decision_template_missing_returns_explainable_not_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary = message_hub.load_latest_d1_labeling_decision_template(Path(tmp))

        self.assertFalse(summary["available"])
        self.assertEqual(summary["status"], "not_available")
        self.assertEqual(summary["reason"], "no_d1_labeling_decision_template")

    def test_deploy_script_can_include_curated_field_report_summaries(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        script = (repo_root / "scripts" / "deploy_message_hub_vps.ps1").read_text(encoding="utf-8")

        self.assertIn('Copy-RelativePath "docs\\generated\\progress_board.json"', script)
        self.assertIn("IncludeFieldReportSummaries", script)
        self.assertIn("IncludeDataFlywheelSummaries", script)
        self.assertIn("IncludeTrainingExperimentSummaries", script)
        self.assertIn("IncludeTrainingRunSummaries", script)
        self.assertIn("IncludeTrainingFeatureSummaries", script)
        self.assertIn("IncludeTrainingRunnerDryRunSummaries", script)
        self.assertIn("IncludeTrainingBaselineEvalSummaries", script)
        self.assertIn("IncludeTrainingHandoffSummaries", script)
        self.assertIn("IncludeTrainingJobSummaries", script)
        self.assertIn("IncludeSyntheticTrainingChainSummaries", script)
        self.assertIn("IncludeD1TrainingReadinessSummaries", script)
        self.assertIn("IncludeD1LabelingIntakeSummaries", script)
        self.assertIn("IncludeD1LabelingQueueSummaries", script)
        self.assertIn("IncludeD1LabelingReviewSummaries", script)
        self.assertIn("IncludeD1LabelingDecisionSummaries", script)
        self.assertIn("Copy-FieldReportSummaries", script)
        self.assertIn("Copy-DataFlywheelSummaries", script)
        self.assertIn("Copy-TrainingExperimentSummaries", script)
        self.assertIn("Copy-TrainingRunSummaries", script)
        self.assertIn("Copy-TrainingFeatureSummaries", script)
        self.assertIn("Copy-TrainingRunnerDryRunSummaries", script)
        self.assertIn("Copy-TrainingBaselineEvalSummaries", script)
        self.assertIn("Copy-TrainingHandoffSummaries", script)
        self.assertIn("Copy-TrainingJobSummaries", script)
        self.assertIn("Copy-SyntheticTrainingChainSummaries", script)
        self.assertIn("Copy-D1TrainingReadinessSummaries", script)
        self.assertIn("Copy-D1LabelingIntakeSummaries", script)
        self.assertIn("Copy-D1LabelingQueueSummaries", script)
        self.assertIn("Copy-D1LabelingReviewSummaries", script)
        self.assertIn("Copy-D1LabelingDecisionSummaries", script)
        self.assertIn("d1_web_api_report.json", script)
        self.assertIn("d1_field_companion_summary.json", script)
        self.assertIn("d1_field_observation_report.json", script)
        self.assertIn("d1_field_observation_report.md", script)
        self.assertIn("d1_field_observation_status.json", script)
        self.assertIn("location_accuracy_report.json", script)
        self.assertIn('"reports\\location_accuracy"', script)
        self.assertIn("power_curve_report.json", script)
        self.assertIn("d1_demo_report.json", script)
        self.assertIn("d1_postrun_collection_summary.json", script)
        self.assertIn("data_flywheel_status.json", script)
        self.assertIn("data_flywheel_status.md", script)
        self.assertIn("training_experiment_plan.json", script)
        self.assertIn("training_experiment_plan.md", script)
        self.assertIn("training_run_preflight.json", script)
        self.assertIn("training_run_preflight.md", script)
        self.assertIn("training_feature_manifest.json", script)
        self.assertIn("training_feature_manifest.md", script)
        self.assertNotIn("training_feature_rows.jsonl", script)
        self.assertIn("training_runner_dry_run.json", script)
        self.assertIn("training_runner_dry_run.md", script)
        self.assertIn("training_baseline_eval.json", script)
        self.assertIn("training_baseline_eval.md", script)
        self.assertIn("training_handoff_bundle.json", script)
        self.assertIn("training_handoff_bundle.md", script)
        self.assertIn("training_job_plan.json", script)
        self.assertIn("training_job_plan.md", script)
        self.assertIn("synthetic_training_chain.json", script)
        self.assertIn("synthetic_training_chain.md", script)
        self.assertIn("d1_training_readiness.json", script)
        self.assertIn("d1_training_readiness.md", script)
        self.assertIn("d1_labeling_intake.json", script)
        self.assertIn("d1_labeling_intake.md", script)
        self.assertIn("d1_labeling_queue.json", script)
        self.assertIn("d1_labeling_queue.md", script)
        self.assertIn("d1_labeling_review_packet.json", script)
        self.assertIn("d1_labeling_review_packet.md", script)
        self.assertIn("d1_labeling_decision_template.json", script)
        self.assertIn("d1_labeling_decision_template.md", script)
        self.assertIn("*.summary.json", script)
        self.assertNotIn("*.jsonl", script)
        self.assertNotIn("d1_field_samples.jsonl", script)
        self.assertNotIn("*.db", script)

    def test_latest_product_demo_report_summary_is_bounded_for_dashboard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_dir = root / "run-a"
            report_dir.mkdir()
            (report_dir / "product_demo_report.json").write_text(
                """
{
  "demo": {"candidate": "KR-008 / DEMO-008 Product Demo Closed Loop", "mode": "offline_evidence_composition", "product_ready": false},
  "source": {"test_run_id": "lte011-unit", "safety_session_id": "demo-unit", "evidence_mode": "composite_existing_evidence", "dataset_samples": 1},
  "result": {"status": "warn", "ready_for_kr008_release": false, "warnings": ["web_console_product_demo_review_pending"], "errors": [], "why_not_release_ready": ["web_console_product_demo_review_pending"]},
  "location": {"state": "Unknown", "gnss_fix": false, "gnss_state": "no_fix", "belief_reason": "cell_observation_without_position_fix"},
  "flow_order": ["report_export", "web_console_replay_review"],
  "flow": {
    "report_export": {"status": "pass", "summary": "report exported"},
    "web_console_replay_review": {"status": "not_run", "summary": "pending"}
  },
  "evidence_summary": {"flow_status_counts": {"pass": 7, "not_run": 1}, "feature_groups": ["gnss", "cell", "lte"], "raw_frame_refs": 3, "derived_event_refs": 2, "training_readiness": {"model_training_ready": false, "reason": "not_ready"}, "release_gate_usage": {"can_support_release_review": true}},
  "paths": {"product_demo_report_json": "reports/product_demo/run-a/product_demo_report.json", "product_demo_report_markdown": "reports/product_demo/run-a/product_demo_report.md"},
  "next_gates": ["Expose through Dashboard"],
  "non_claims": ["No product readiness claim."]
}
""".strip()
                + "\n",
                encoding="utf-8",
            )

            summary = message_hub.load_latest_product_demo_report(root)

        self.assertTrue(summary["available"])
        self.assertEqual(summary["status"], "warn")
        self.assertEqual(summary["candidate"], "KR-008 / DEMO-008 Product Demo Closed Loop")
        self.assertEqual(summary["evidence_mode"], "composite_existing_evidence")
        self.assertFalse(summary["ready_for_kr008_release"])
        self.assertEqual(summary["flow"]["web_console_replay_review"]["status"], "not_run")
        self.assertEqual(summary["location"]["state"], "Unknown")
        self.assertEqual(summary["raw_frame_refs"], 3)

    def test_product_demo_report_missing_returns_explainable_not_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary = message_hub.load_latest_product_demo_report(Path(tmp))

        self.assertFalse(summary["available"])
        self.assertEqual(summary["status"], "not_available")
        self.assertEqual(summary["reason"], "no_product_demo_report")

    def test_state_api_includes_recent_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            store.create_command("ego-link-001", {"cmd": "set_report_interval"})

            commands = store.recent_commands()

        self.assertEqual(commands[0]["cmd"], "set_report_interval")
        self.assertEqual(commands[0]["status"], "pending")

    def test_state_api_raw_frames_are_redacted_and_explainable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = message_hub.MessageHubStore(Path(tmp) / "hub.db")
            raw = message_hub.build_raw_frame("event", "raw-dashboard-test", b"event_type=dashboard_smoke\n")
            record = store.ingest_raw_frame("ego-link-001", raw)
            raw_frames = store.recent_raw_frames()

        self.assertEqual(record["parse_result"]["status"], "ok")
        self.assertEqual(raw_frames[0]["parse_result"]["status"], "ok")
        self.assertEqual(raw_frames[0]["parse_result"]["derived_message_type"], "event")
        self.assertTrue(raw_frames[0]["raw_payload"]["data_redacted"])
        self.assertNotIn("data", raw_frames[0]["raw_payload"])

    def test_amap_missing_config_falls_back_without_loader(self) -> None:
        html = message_hub.render_dashboard()

        self.assertIn('name="egolink-amap-status" content="not-configured"', html)
        self.assertNotIn('src="https://webapi.amap.com/loader.js"', html)
        self.assertIn("No-key Local Map", html)
        self.assertIn("local map fallback", html)

    def test_amap_dashboard_injects_only_public_js_key(self) -> None:
        public_key = "public_JS_key_1234"
        security_code = "server_only_security_1234"
        previous = os.environ.get(message_hub.AMAP_SECURITY_JS_CODE_ENV)
        os.environ[message_hub.AMAP_SECURITY_JS_CODE_ENV] = security_code
        try:
            html = message_hub.render_dashboard(amap_js_api_key=public_key)
        finally:
            if previous is None:
                os.environ.pop(message_hub.AMAP_SECURITY_JS_CODE_ENV, None)
            else:
                os.environ[message_hub.AMAP_SECURITY_JS_CODE_ENV] = previous

        self.assertIn(public_key, html)
        self.assertIn("window._AMapSecurityConfig", html)
        self.assertIn("window.location.origin+'/_AMapService'", html)
        self.assertNotIn(security_code, html)
        self.assertNotIn(message_hub.AMAP_SECURITY_JS_CODE_ENV, html)

    def test_amap_dashboard_preserves_instance_and_rejects_stale_async_render(self) -> None:
        html = message_hub.render_dashboard(amap_js_api_key="public_JS_key_1234")

        self.assertIn("let amapInstance = null", html)
        self.assertIn("let amapLoadPromise = null", html)
        self.assertIn("let amapRenderGeneration = 0", html)
        self.assertIn("if (generation !== amapRenderGeneration) return", html)
        self.assertIn("AMap.convertFrom(valid.map(point => [point.lon, point.lat]), 'gps'", html)
        self.assertIn(".filter(Boolean).slice(-40)", html)
        self.assertIn("kind: 'current'", html)
        self.assertIn("kind: 'last-known'", html)
        self.assertIn("kind: 'no-fix'", html)
        self.assertIn("kind: 'stale'", html)
        self.assertIn("kind: 'pre-correction-hidden'", html)
        self.assertIn("readiness.freshness_threshold_s ?? 180", html)
        self.assertIn("amap-stale-marker", html)
        self.assertIn("point.amap_eligible === true && point.coordinate_contract === 'wgs84'", html)
        self.assertIn("Pre-correction location hidden until new verified GNSS fix", html)
        self.assertIn("const fieldCoordinateText = latestTrustedPoint", html)
        self.assertNotIn("coordinateLabel(map.lat, map.lon)", html)
        self.assertIn("point.display_semantics === 'current_fix'", html)
        self.assertIn('id="amapLiveMap"', html)
        self.assertIn('id="d1Link"', html)


if __name__ == "__main__":
    unittest.main()

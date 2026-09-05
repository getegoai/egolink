from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from pc_simulator import location_policy_replay
from pc_simulator.sensor_policy_v0 import SensorPolicyConfig
from quality_tests.test_field_session_pack import _fixture
from quality_tests.test_ft001b_session_pack import _pack
from tools import run_location_policy_replay


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = json.loads(
    (ROOT / "shared" / "config" / "sensor_policy_v0.json").read_text(encoding="utf-8")
)


def timeline_row(
    source: str,
    event_time_ms: int,
    payload: dict,
    *,
    observation_id: str,
    order: str = "ordered_with_declared_uncertainty",
    source_status: str = "observed",
) -> dict:
    return {
        "observation_id": observation_id,
        "source": source,
        "stream_id": f"{source}-stream",
        "sequence_id": event_time_ms,
        "sample_index": None,
        "device_id": "ego-fixture",
        "device_run_id": "run-1",
        "boot_count": 1,
        "timestamp_monotonic_ns": event_time_ms * 1_000_000,
        "timestamp_utc_ns": event_time_ms * 1_000_000,
        "alignment_status": "verified",
        "timestamp_uncertainty_ns": 1_000,
        "source_status": source_status,
        "cross_source_order": order,
        "payload_artifact": {"path": f"streams/{source}.jsonl", "sha256": "a" * 64},
        "payload": deepcopy(payload),
        "available_to_estimator": True,
        "masked": False,
    }


def normalized_observation(
    event_type: str,
    event_time_ms: int,
    *,
    observation_id: str,
    source: str,
    source_status: str = "observed",
    **values: object,
) -> dict:
    return {
        "contract_version": (
            location_policy_replay.NORMALIZED_OBSERVATION_CONTRACT_VERSION
        ),
        "event_type": event_type,
        "event_time_ms": event_time_ms,
        **values,
        "lineage": {
            "observation_id": observation_id,
            "normalized_observation_id": observation_id,
            "source": source,
            "source_status": source_status,
            "event_time_source": "timestamp_monotonic_ns",
            "timestamp_monotonic_ns": event_time_ms * 1_000_000,
            "boot_count": 1,
            "monotonic_clock_domain_id": "fixture-boot-1",
            "device_run_id": "fixture-run-1",
        },
        "evidence": {
            "kind": "test_observation",
            "source_status": source_status,
            "policy_eligible": True,
        },
    }


def private_coordinate_paths(value: object, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}"
            if str(key).lower() in location_policy_replay.PRIVATE_COORDINATE_KEYS:
                found.append(child)
            found.extend(private_coordinate_paths(item, child))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(private_coordinate_paths(item, f"{path}[{index}]"))
    return found


class LocationPolicyReplayTests(unittest.TestCase):
    def config(self, **changes: object) -> SensorPolicyConfig:
        value = deepcopy(DEFAULT_CONFIG)
        for dotted, replacement in changes.items():
            section, field = dotted.split("__", 1)
            value[section][field] = replacement
        value["config_id"] = "fixture-" + str(len(changes))
        return SensorPolicyConfig.from_mapping(value)

    def test_normalizer_preserves_lineage_and_never_uses_receive_time(self) -> None:
        rows = [
            timeline_row(
                "gnss",
                1_000,
                {
                    "fix": True,
                    "lat": 22.5,
                    "lon": 114.0,
                    "accuracy_m": 10,
                    "server_received_at": "2099-01-01T00:00:00Z",
                },
                observation_id="gnss-1",
            ),
            {
                **timeline_row(
                    "lte", 2_000, {"cell": {"cell_id": "A"}}, observation_id="lte-1"
                ),
                "timestamp_utc_ns": None,
                "receive_timestamp_utc": "2026-08-23T00:00:02Z",
            },
        ]

        normalized = location_policy_replay.normalize_field_timeline(rows)

        self.assertEqual(1, len(normalized.observations))
        event = normalized.observations[0]
        self.assertEqual(1_000, event["event_time_ms"])
        self.assertEqual("gnss-1", event["lineage"]["observation_id"])
        self.assertEqual("capture_event", event["lineage"]["event_time_source"])
        self.assertEqual("observed", event["evidence"]["source_status"])
        self.assertEqual({}, normalized.excluded_counts)
        self.assertEqual(1, normalized.annotation_counts["policy_event_time_or_order_unavailable"])
        self.assertNotIn("server_received_at", json.dumps(event))

    def test_verified_and_same_source_gnss_are_retained_but_manual_is_annotation(self) -> None:
        rows = [
            timeline_row(
                "gnss",
                1,
                {"fix": False},
                observation_id="ambiguous",
                order="ambiguous_uncertainty_overlap",
                source_status="verified",
            ),
            timeline_row("camera", 2, {}, observation_id="camera"),
            timeline_row(
                "imu", 3, {"calibrated": {}}, observation_id="mock", source_status="mock"
            ),
            timeline_row(
                "manual_event",
                4,
                {"event_type": "START_WALKING"},
                observation_id="weak-walk",
                source_status="operator_weak_label",
            ),
            timeline_row(
                "lte",
                5,
                {"cell": {"cell_id": "verified-cell"}},
                observation_id="verified-cell",
                source_status="verified",
            ),
        ]

        normalized = location_policy_replay.normalize_field_timeline(rows)

        self.assertEqual(["gnss_no_fix"], [row["event_type"] for row in normalized.observations])
        self.assertEqual("verified", normalized.observations[0]["lineage"]["source_status"])
        self.assertEqual("same_source_only", normalized.observations[0]["evidence"]["ordering_scope"])
        self.assertEqual(1, normalized.excluded_counts["source_not_trusted"])
        reasons = [row["reason"] for row in normalized.annotations]
        self.assertIn("operator_weak_label_not_policy_input", reasons)
        self.assertIn("camera_experimental_not_policy_input", reasons)
        self.assertIn("policy_clock_lane_not_selected", reasons)
        self.assertNotIn("mobility", [row["event_type"] for row in normalized.observations])

    def test_replay_is_deterministic_and_never_requests_camera(self) -> None:
        rows = [
            timeline_row(
                "gnss",
                1_000,
                {"fix": True, "lat": 22.5, "lon": 114.0, "accuracy_m": 10},
                observation_id="gnss-fix",
            ),
            timeline_row(
                "manual_event",
                2_000,
                {"event_type": "START_WALKING"},
                observation_id="walk",
                source_status="operator_weak_label",
            ),
            timeline_row(
                "gnss", 3_000, {"fix": False}, observation_id="gnss-no-fix"
            ),
            timeline_row(
                "lte", 4_000, {"cell": {"cell_id": "B"}}, observation_id="cell"
            ),
        ]
        normalized = location_policy_replay.normalize_field_timeline(rows)
        config = self.config()

        first = location_policy_replay.replay_observations(normalized.observations, config)
        second = location_policy_replay.replay_observations(normalized.observations, config)

        self.assertEqual(first, second)
        self.assertEqual(0, first["metrics"]["camera_request_count"])
        self.assertEqual("Predicted", first["final_state"]["location_belief"])
        self.assertEqual("unknown", first["final_state"]["mobility_state"])
        self.assertEqual(
            "gnss-fix", first["final_state"]["last_trusted_location_ref"]
        )
        self.assertEqual("unverified", first["hardware_claim"])
        self.assertEqual([], private_coordinate_paths(first))
        self.assertFalse(first["privacy"]["precise_coordinates_included"])
        for row in first["trace"]:
            self.assertFalse(row["policy_decision"]["actions"]["camera"]["requested"])
            self.assertIn("lineage", row["input"])
            self.assertIn("evidence", row["input"])
            self.assertIn("policy_observation", row["input"])

    def test_config_comparison_reports_effects_not_measured_savings(self) -> None:
        observations = [
            {"event_type": "tick", "event_time_ms": 0, "lineage": {}},
            normalized_observation(
                "gnss_no_fix",
                45_000,
                observation_id="comparison-no-fix",
                source="gnss",
            ),
            {"event_type": "tick", "event_time_ms": 75_000, "lineage": {}},
            {"event_type": "tick", "event_time_ms": 105_000, "lineage": {}},
        ]
        baseline = location_policy_replay.replay_observations(
            observations, self.config(gnss__retry_backoff_s=60)
        )
        candidate = location_policy_replay.replay_observations(
            observations, self.config(gnss__retry_backoff_s=120)
        )
        comparison = location_policy_replay.compare_replay_reports(baseline, candidate)

        self.assertEqual("different_behavior", comparison["status"])
        self.assertFalse(comparison["behavior_trace_equal"])
        self.assertFalse(comparison["config_identity"]["config_hash_equal"])
        self.assertIn("replay outcomes only", comparison["interpretation_boundary"])
        self.assertNotIn("battery_savings", comparison)
        self.assertIn("no_measured_battery_savings_claim", candidate["non_claims"])

    def test_comparison_separates_config_identity_from_behavior(self) -> None:
        first = deepcopy(DEFAULT_CONFIG)
        second = deepcopy(DEFAULT_CONFIG)
        first["config_id"] = "identity-one"
        second["config_id"] = "identity-two"
        observations = [
            normalized_observation(
                "gnss_no_fix",
                0,
                observation_id="no-fix",
                source="gnss",
            )
        ]
        baseline = location_policy_replay.replay_observations(
            observations, SensorPolicyConfig.from_mapping(first)
        )
        candidate = location_policy_replay.replay_observations(
            observations, SensorPolicyConfig.from_mapping(second)
        )

        comparison = location_policy_replay.compare_replay_reports(
            baseline, candidate
        )

        self.assertFalse(comparison["config_identity"]["config_id_equal"])
        self.assertFalse(comparison["config_identity"]["config_hash_equal"])
        self.assertFalse(comparison["full_trace_equal"])
        self.assertTrue(comparison["behavior_trace_equal"])
        self.assertEqual("equivalent_behavior", comparison["status"])

    def test_replay_field_session_reuses_existing_loader_and_timeline(self) -> None:
        timeline = [
            timeline_row(
                "gnss",
                1_000,
                {"fix": True, "lat": 22.5, "lon": 114.0, "accuracy_m": 10},
                observation_id="gnss-fix",
            )
        ]
        package = mock.Mock()
        package.validation = {"valid": True, "field_eligible": False}
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            manifest.write_text("{}\n", encoding="utf-8")
            manifest_hash = hashlib.sha256(manifest.read_bytes()).hexdigest()
            with mock.patch.object(
                location_policy_replay.field_session_replay,
                "load_replay_package",
                return_value=package,
            ) as load, mock.patch.object(
                location_policy_replay.field_session_replay,
                "build_replay_timeline",
                return_value=(timeline, {"record_count": 1}),
            ) as build:
                report = location_policy_replay.replay_field_session(
                    manifest, self.config()
                )

        load.assert_called_once_with(manifest)
        build.assert_called_once_with(package)
        self.assertEqual(manifest_hash, report["input"]["manifest_sha256"])
        self.assertFalse(report["input"]["field_session_validation"]["field_eligible"])

    def test_cli_writes_two_reports_and_comparison(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            observations = root / "observations.jsonl"
            observation = normalized_observation(
                "gnss_no_fix",
                0,
                observation_id="cli-no-fix",
                source="gnss",
            )
            observations.write_text(
                json.dumps(observation, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            observations_sha256 = hashlib.sha256(observations.read_bytes()).hexdigest()
            first_config = root / "first.json"
            second_config = root / "second.json"
            first = deepcopy(DEFAULT_CONFIG)
            first["config_id"] = "first"
            second = deepcopy(DEFAULT_CONFIG)
            second["config_id"] = "second"
            second["gnss"]["retry_backoff_s"] = 120
            first_config.write_text(json.dumps(first), encoding="utf-8")
            second_config.write_text(json.dumps(second), encoding="utf-8")
            output = root / "output"

            code = run_location_policy_replay.main(
                [
                    "--normalized-jsonl",
                    str(observations),
                    "--config",
                    str(first_config),
                    "--config",
                    str(second_config),
                    "--output-dir",
                    str(output),
                ]
            )

            self.assertEqual(0, code)
            reports = sorted(output.glob("replay-*.json"))
            self.assertEqual(2, len(reports))
            first_report = next(
                json.loads(path.read_text(encoding="utf-8"))
                for path in reports
                if json.loads(path.read_text(encoding="utf-8"))["config"]["config_id"]
                == "first"
            )
            self.assertEqual(observations_sha256, first_report["input"]["sha256"])
            self.assertEqual(1, first_report["input"]["record_count"])
            self.assertEqual(
                location_policy_replay.NORMALIZED_OBSERVATION_CONTRACT_VERSION,
                first_report["input"]["contract_version"],
            )
            summary = json.loads((output / "comparison.json").read_text(encoding="utf-8"))
            self.assertEqual("completed", summary["status"])
            self.assertEqual(2, summary["report_count"])
            self.assertEqual(1, len(summary["comparisons"]))

    def test_real_ft001b_fixture_retains_evidence_and_never_passes_zero_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _fixture(root)
            _pack(paths)

            report = location_policy_replay.replay_field_session(
                root / "ft001b/manifest.json", self.config()
            )

        self.assertEqual(103, report["input"]["input_record_count"])
        self.assertGreater(report["input"]["normalized_observation_count"], 0)
        self.assertGreater(report["input"]["retained_evidence_count"], 0)
        self.assertGreater(report["input"]["evidence_annotation_count"], 0)
        self.assertEqual("completed", report["run_status"])
        self.assertEqual(2, report["metrics"]["external_evidence_observation_count"])
        self.assertEqual(
            2,
            report["metrics"]["external_location_evidence_observation_count"],
        )
        self.assertEqual(
            2, report["metrics"]["gnss_result_counts"]["gnss_fix_rejected"]
        )
        self.assertEqual([], private_coordinate_paths(report))

    def test_internal_policy_timer_drives_timeouts_and_backoff(self) -> None:
        observations = [
            normalized_observation(
                "cell_observation",
                0,
                observation_id="cell-start",
                source="lte",
            ),
            normalized_observation(
                "cell_observation",
                200_000,
                observation_id="cell-end",
                source="lte",
            ),
        ]

        report = location_policy_replay.replay_observations(
            observations, self.config()
        )

        timer_rows = [
            row for row in report["trace"] if row["input"]["origin"] == "policy_timer"
        ]
        self.assertGreater(len(timer_rows), 0)
        actions = [row["policy_decision"]["actions"]["gnss"]["action"] for row in timer_rows]
        self.assertIn("stop_timeout", actions)
        timeout_index = actions.index("stop_timeout")
        self.assertIn("start", actions[timeout_index + 1 :])
        self.assertEqual(
            len(timer_rows), report["metrics"]["derived_policy_timer_event_count"]
        )
        self.assertEqual(200_000, report["metrics"]["replayed_duration_ms"])

    def test_location_availability_is_time_weighted_not_row_weighted(self) -> None:
        fix = normalized_observation(
            "gnss_fix",
            0,
            observation_id="fix",
            source="gnss",
            latitude_deg=22.5,
            longitude_deg=114.0,
            accuracy_m=10,
        )
        end = normalized_observation(
            "cell_observation",
            10_000,
            observation_id="end",
            source="lte",
        )
        dense = [
            fix,
            normalized_observation(
                "imu_sample",
                1_000,
                observation_id="imu-1",
                source="imu",
                accel_m_s2=[0.0, 0.0, 9.80665],
            ),
            normalized_observation(
                "imu_sample",
                2_000,
                observation_id="imu-2",
                source="imu",
                accel_m_s2=[0.0, 0.0, 9.80665],
            ),
            end,
        ]

        sparse_report = location_policy_replay.replay_observations(
            [fix, end], self.config()
        )
        dense_report = location_policy_replay.replay_observations(
            dense, self.config()
        )

        self.assertNotEqual(
            sparse_report["metrics"]["external_observation_count"],
            dense_report["metrics"]["external_observation_count"],
        )
        for report in (sparse_report, dense_report):
            self.assertEqual(10_000, report["metrics"]["replayed_duration_ms"])
            self.assertEqual(
                10_000, report["metrics"]["location_available_duration_ms"]
            )
            self.assertEqual(1.0, report["metrics"]["location_available_time_ratio"])

    def test_empty_normalized_input_is_insufficient_and_cli_returns_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            observations = root / "empty.jsonl"
            observations.write_text("", encoding="utf-8")
            config_path = root / "config.json"
            config_path.write_text(json.dumps(DEFAULT_CONFIG), encoding="utf-8")
            output = root / "output"

            code = run_location_policy_replay.main(
                [
                    "--normalized-jsonl",
                    str(observations),
                    "--config",
                    str(config_path),
                    "--output-dir",
                    str(output),
                ]
            )
            summary = json.loads(
                (output / "comparison.json").read_text(encoding="utf-8")
            )

        self.assertEqual(1, code)
        self.assertEqual("insufficient_evidence", summary["status"])
        self.assertEqual(
            "insufficient_evidence", summary["reports"][0]["run_status"]
        )

    def test_non_location_observations_do_not_complete_location_replay(self) -> None:
        observations = [
            normalized_observation(
                "battery",
                0,
                observation_id="battery-only",
                source="power",
                battery_state="normal",
                battery_percent=80,
            ),
            normalized_observation(
                "imu_sample",
                1_000,
                observation_id="imu-only",
                source="imu",
                accel_m_s2=[0.0, 0.0, 9.80665],
            ),
        ]

        report = location_policy_replay.replay_observations(
            observations, self.config()
        )

        self.assertEqual("insufficient_evidence", report["run_status"])
        self.assertEqual(
            ["no_external_location_evidence_observation"],
            report["insufficient_evidence_reasons"],
        )
        self.assertEqual(2, report["metrics"]["external_evidence_observation_count"])
        self.assertEqual(
            0,
            report["metrics"]["external_location_evidence_observation_count"],
        )

    def test_cli_error_path_returns_two_and_sealed_output_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "config.json"
            config_path.write_text(json.dumps(DEFAULT_CONFIG), encoding="utf-8")
            missing_code = run_location_policy_replay.main(
                [
                    "--normalized-jsonl",
                    str(root / "missing.jsonl"),
                    "--config",
                    str(config_path),
                    "--output-dir",
                    str(root / "missing-output"),
                ]
            )
            manifest = root / "sealed" / "manifest.json"
            manifest.parent.mkdir()
            manifest.write_text("{}\n", encoding="utf-8")
            sealed_output = manifest.parent / "generated"
            sealed_code = run_location_policy_replay.main(
                [
                    "--manifest",
                    str(manifest),
                    "--config",
                    str(config_path),
                    "--output-dir",
                    str(sealed_output),
                ]
            )
            sealed_output_created = sealed_output.exists()

        self.assertEqual(2, missing_code)
        self.assertEqual(2, sealed_code)
        self.assertFalse(sealed_output_created)

    def test_normalized_jsonl_contract_rejects_missing_version_and_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            invalid = root / "invalid.jsonl"
            invalid.write_text(
                json.dumps({"event_type": "gnss_no_fix", "event_time_ms": 0})
                + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                location_policy_replay.LocationPolicyReplayError,
                "contract_version",
            ):
                location_policy_replay.load_normalized_observations_jsonl(invalid)

            duplicate = root / "duplicate.jsonl"
            row = normalized_observation(
                "gnss_no_fix",
                0,
                observation_id="duplicate",
                source="gnss",
            )
            duplicate.write_text(
                json.dumps(row) + "\n" + json.dumps(row) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                location_policy_replay.LocationPolicyReplayError,
                "duplicate observation id",
            ):
                location_policy_replay.load_normalized_observations_jsonl(duplicate)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from pc_simulator import field_session, field_session_replay
from pc_simulator.sensor_time_lineage import format_utc_ns, parse_utc_ns
from quality_tests.test_a0_field_session import _build_field_bundle
from scripts import replay_field_session


BASE_UTC = "2026-08-17T00:00:00Z"
BASE_NS = parse_utc_ns(BASE_UTC)


def timeline_row(
    source: str,
    offset_s: float,
    payload: dict,
    *,
    sequence_id: int = 1,
    alignment_status: str = "estimated",
    uncertainty_ns: int | None = 1_000_000,
    source_status: str = "observed",
    device_run_id: str = "primary-run",
) -> dict:
    timestamp_ns = BASE_NS + int(offset_s * 1_000_000_000)
    return {
        "observation_id": f"{source}-{sequence_id}-{offset_s}",
        "source": source,
        "stream_id": f"{source}-primary",
        "sequence_id": sequence_id,
        "sample_index": payload.get("sample_index"),
        "device_id": "ego-link-fixture-001",
        "device_run_id": device_run_id,
        "timestamp_monotonic_ns": max(0, int((offset_s + 10) * 1_000_000_000)),
        "timestamp_utc": format_utc_ns(timestamp_ns),
        "timestamp_utc_ns": timestamp_ns,
        "monotonic_clock_domain_id": f"{device_run_id}-clock",
        "boot_count": 1,
        "alignment_status": alignment_status,
        "timestamp_uncertainty_ns": uncertainty_ns,
        "source_status": source_status,
        "payload_artifact": {
            "artifact_id": f"{source}-artifact",
            "path": f"streams/{source}.jsonl",
            "sha256": "a" * 64,
        },
        "payload": copy.deepcopy(payload),
        "available_to_estimator": True,
        "masked": False,
        "mask_reason": None,
        "timeline_group": "cross_source_utc",
        "cross_source_order": "ordered_with_declared_uncertainty",
    }


def gnss_row(offset_s: float, lat: float, lon: float, *, sequence_id: int) -> dict:
    return timeline_row(
        "gnss",
        offset_s,
        {"fix": True, "lat": lat, "lon": lon},
        sequence_id=sequence_id,
    )


def direct_source_gnss_row(
    offset_s: float, lat: float, lon: float, *, sequence_id: int
) -> dict:
    row = gnss_row(offset_s, lat, lon, sequence_id=sequence_id)
    row["alignment_status"] = "unavailable"
    row["gnss_source_utc_ns"] = row["timestamp_utc_ns"]
    row["timestamp_utc_ns"] = None
    row["timestamp_utc_origin"] = "source_timestamp"
    row["timestamp_uncertainty_ns"] = None
    row["timeline_group"] = "gnss_source_utc_only"
    row["cross_source_order"] = "unavailable"
    return row


def lte_row(offset_s: float, cell_id: str, *, sequence_id: int) -> dict:
    return timeline_row(
        "lte",
        offset_s,
        {
            "cell": {
                "rat": "LTE",
                "mcc": "460",
                "mnc": "01",
                "tac": "1001",
                "cell_id": cell_id,
            }
        },
        sequence_id=sequence_id,
    )


def imu_row(offset_s: float, deviation_m_s2: float, *, sequence_id: int) -> dict:
    return timeline_row(
        "imu",
        offset_s,
        {
            "calibration_id": "imucal-0123456789abcdef01234567",
            "calibrated": {
                "accel_m_s2": [0.0, 0.0, field_session_replay.STANDARD_GRAVITY_M_S2 + deviation_m_s2]
            },
            "sample_index": sequence_id,
        },
        sequence_id=sequence_id,
    )


def centroid_key(cell_id: str) -> str:
    value = field_session_replay.canonical_cell_key(
        {"rat": "LTE", "mcc": "460", "mnc": "01", "tac": "1001", "cell_id": cell_id}
    )
    assert value is not None
    return value


def complete_experiment_timeline(*, moving_at_transition: bool = True) -> list[dict]:
    rows = [
        gnss_row(-1, 22.0, 114.0, sequence_id=1),
        gnss_row(0, 22.0, 114.0, sequence_id=2),
        gnss_row(30, 22.0, 114.0002, sequence_id=3),
        gnss_row(60, 22.0, 114.0004, sequence_id=4),
        lte_row(-1, "A", sequence_id=1),
        lte_row(30, "B", sequence_id=2),
    ]
    for index in range(61):
        deviation = 2.0 if moving_at_transition and index in {29, 30} else 0.0
        rows.append(imu_row(float(index), deviation, sequence_id=index + 1))
    return sorted(rows, key=lambda row: (row["timestamp_utc_ns"], row["source"], row["sequence_id"]))


def centroids() -> dict[str, tuple[float, float]]:
    return {
        centroid_key("A"): (22.0, 114.0),
        centroid_key("B"): (22.0, 114.0004),
    }


def centroid_artifact(status: str = "available") -> dict:
    return {
        "status": status,
        "reason_codes": [] if status == "available" else ["lte_centroid_artifact_not_provided"],
        "sha256": "b" * 64 if status == "available" else None,
        "version": "fixture-v1" if status == "available" else None,
        "entry_count": 2 if status == "available" else 0,
        "provenance_recorded": status == "available",
    }


def experiment_config(**changes: object) -> field_session_replay.ExperimentConfig:
    values = {
        "blackout_start_utc": BASE_UTC,
        "blackout_duration_s": 60,
        "endpoint_tolerance_s": 0.0,
        "motion_window_s": 1.0,
        "motion_threshold_m_s2": 0.75,
        "motion_min_samples": 2,
        "imu_max_gap_s": 1.0,
    }
    values.update(changes)
    return field_session_replay.ExperimentConfig(**values)


class FieldSessionReplayTests(unittest.TestCase):
    def _write_valid_field_ineligible_package(self, root: Path) -> Path:
        root.mkdir(parents=True)
        manifest = _build_field_bundle(root)
        manifest["session_type"] = "bench"
        manifest = field_session.seal_manifest(
            manifest,
            sealed_by="field-replay-unit-test",
            sealed_at_utc="2026-08-17T00:11:00Z",
        )
        path = root / "manifest.json"
        field_session.write_json(path, manifest)
        return path

    @staticmethod
    def _tree_hashes(root: Path) -> dict[str, str]:
        return {
            path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*"))
            if path.is_file()
        }

    def test_valid_complete_sealed_but_field_ineligible_package_replays_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            session_root = base / "session"
            manifest_path = self._write_valid_field_ineligible_package(session_root)
            before = self._tree_hashes(session_root)

            package = field_session_replay.load_replay_package(manifest_path)
            report = field_session_replay.write_replay_outputs(package, base / "output")
            after = self._tree_hashes(session_root)

            self.assertTrue(package.validation["valid"])
            self.assertFalse(package.validation["field_eligible"])
            self.assertEqual(before, after)
            self.assertEqual(report["execution"]["status"], "completed")
            self.assertEqual(report["execution"]["evidence_scope"], "engineering_smoke_only")
            self.assertIn(
                "session_type_not_field",
                report["input_validation"]["field_eligibility_reasons"],
            )
            self.assertEqual(report["gate_status"], "unverified")
            self.assertTrue((base / "output" / "timeline.jsonl").is_file())
            self.assertTrue((base / "output" / "trajectory.svg").is_file())
            self.assertTrue((base / "output" / "replay-summary.json").is_file())

    def test_invalid_artifact_hash_is_rejected_before_replay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "session"
            manifest_path = self._write_valid_field_ineligible_package(root)
            with (root / "streams" / "gnss.jsonl").open("ab") as handle:
                handle.write(b"{}\n")

            with self.assertRaisesRegex(
                field_session_replay.FieldSessionReplayError,
                "not safely replayable",
            ):
                field_session_replay.load_replay_package(manifest_path)

    def test_output_inside_sealed_package_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "session"
            root.mkdir()
            with self.assertRaisesRegex(
                field_session_replay.FieldSessionReplayError,
                "outside the sealed Field Session root",
            ):
                field_session_replay.ensure_output_outside_session(root / "generated", root)

    def test_mask_is_start_inclusive_end_exclusive_and_only_affects_gnss_copy(self) -> None:
        timeline = [
            gnss_row(-1, 22.0, 114.0, sequence_id=1),
            gnss_row(0, 22.0, 114.0, sequence_id=2),
            gnss_row(59.999999999, 22.0, 114.1, sequence_id=3),
            gnss_row(60, 22.0, 114.2, sequence_id=4),
            lte_row(30, "A", sequence_id=1),
        ]
        original = copy.deepcopy(timeline)

        masked, summary = field_session_replay.apply_gnss_mask(
            timeline,
            start_utc=BASE_UTC,
            duration_s=60,
        )

        self.assertEqual(timeline, original)
        self.assertEqual(summary["interval_semantics"], "start_inclusive_end_exclusive")
        self.assertEqual(summary["masked_observation_count"], 2)
        self.assertEqual(
            [row["sequence_id"] for row in masked if row["masked"]],
            [2, 3],
        )
        self.assertFalse(next(row for row in masked if row["source"] == "lte")["masked"])

    def test_receive_only_gnss_is_never_used_to_guess_mask_membership(self) -> None:
        row = gnss_row(10, 22.0, 114.0, sequence_id=1)
        row["alignment_status"] = "receive_only"
        row["timestamp_utc_ns"] = None
        row["timestamp_utc"] = None
        with self.assertRaisesRegex(
            field_session_replay.FieldSessionReplayError,
            "mask membership is indeterminate",
        ):
            field_session_replay.apply_gnss_mask([row], start_utc=BASE_UTC, duration_s=60)

    def test_estimated_sidecar_uncertainty_overlap_is_explicitly_ambiguous(self) -> None:
        camera = timeline_row(
            "camera",
            10.0,
            {"media_artifact_id": "camera-001"},
            sequence_id=1,
            uncertainty_ns=200_000_000,
            device_run_id="phone-sidecar",
        )
        manual = timeline_row(
            "manual_event",
            10.1,
            {"event_type": "ENTER_BUILDING"},
            sequence_id=2,
            uncertainty_ns=200_000_000,
            device_run_id="phone-sidecar",
        )
        ordered = [camera, manual]
        count = field_session_replay.mark_ambiguous_cross_source_order(ordered)
        self.assertEqual(count, 2)
        self.assertEqual(
            {row["cross_source_order"] for row in ordered},
            {"ambiguous_uncertainty_overlap"},
        )

    def test_calibrated_imu_window_expands_samples_and_retains_calibration_id(self) -> None:
        base = timeline_row(
            "imu",
            0,
            {"window_id": "window-1"},
            sequence_id=1,
        )
        base["timestamp_monotonic_ns"] = 1_000_000_000
        record = {
            "imu_sample_derivation": {
                "capture_start_uptime_us": 1_000_000,
                "window_id": "window-1",
            }
        }
        calibrated = {
            "calibration_id": "imucal-0123456789abcdef01234567",
            "calibration_identity_sha256": "c" * 64,
            "samples": [
                {
                    "index": 0,
                    "offset_us": 0,
                    "uncalibrated": {"accel_mg": [0, 0, 1000], "gyro_mdps": [0, 0, 0]},
                    "calibrated": {
                        "accel_mg": [0.0, 0.0, 1000.0],
                        "gyro_mdps": [0.0, 0.0, 0.0],
                        "accel_m_s2": [0.0, 0.0, field_session_replay.STANDARD_GRAVITY_M_S2],
                        "gyro_rad_s": [0.0, 0.0, 0.0],
                    },
                },
                {
                    "index": 1,
                    "offset_us": 50_000,
                    "uncalibrated": {"accel_mg": [1, 0, 1000], "gyro_mdps": [0, 0, 0]},
                    "calibrated": {
                        "accel_mg": [1.0, 0.0, 1000.0],
                        "gyro_mdps": [0.0, 0.0, 0.0],
                        "accel_m_s2": [0.00980665, 0.0, field_session_replay.STANDARD_GRAVITY_M_S2],
                        "gyro_rad_s": [0.0, 0.0, 0.0],
                    },
                },
            ],
        }

        expanded = field_session_replay._expand_imu_item(base, record, calibrated)

        self.assertEqual(len(expanded), 2)
        self.assertEqual(expanded[1]["timestamp_monotonic_ns"], 1_050_000_000)
        self.assertEqual(expanded[1]["timestamp_utc_ns"], BASE_NS + 50_000_000)
        self.assertEqual(expanded[1]["payload"]["calibration_id"], calibrated["calibration_id"])
        self.assertIn("uncalibrated", expanded[1]["payload"])
        self.assertIn("calibrated", expanded[1]["payload"])

    def test_three_baselines_complete_with_full_gnss_reference_and_no_coordinate_json(self) -> None:
        result, layers = field_session_replay.evaluate_exp_a1_000(
            complete_experiment_timeline(),
            config=experiment_config(),
            lte_centroids=centroids(),
            lte_centroid_artifact=centroid_artifact(),
        )

        self.assertEqual(result["run_status"], "completed")
        self.assertEqual(result["reference"]["type"], "full_gnss_reference")
        self.assertFalse(result["reference"]["is_ground_truth"])
        self.assertEqual(
            [baseline["status"] for baseline in result["baselines"]],
            ["available", "available", "available"],
        )
        self.assertTrue(all(baseline["endpoint_error_m"] is not None for baseline in result["baselines"]))
        serialized = json.dumps(result, sort_keys=True)
        self.assertNotIn("latitude", serialized)
        self.assertNotIn("longitude", serialized)
        self.assertNotIn("114.0004", serialized)
        self.assertGreater(len(layers["full_gnss_reference"]), 0)

    def test_motion_gated_lte_holds_new_centroid_while_stationary(self) -> None:
        result, _layers = field_session_replay.evaluate_exp_a1_000(
            complete_experiment_timeline(moving_at_transition=False),
            config=experiment_config(),
            lte_centroids=centroids(),
            lte_centroid_artifact=centroid_artifact(),
        )
        baseline_b = next(row for row in result["baselines"] if row["baseline_id"] == "B")
        baseline_c = next(row for row in result["baselines"] if row["baseline_id"] == "C")
        self.assertEqual(baseline_b["endpoint_error_m"], 0.0)
        self.assertGreater(baseline_c["endpoint_error_m"], 0.0)
        self.assertIn("no_inertial_displacement_or_heading_estimate", baseline_c["notes"])

    def test_missing_centroid_artifact_and_imu_do_not_silently_fallback(self) -> None:
        timeline = [row for row in complete_experiment_timeline() if row["source"] != "imu"]
        timeline.append(
            timeline_row(
                "manual_event",
                30,
                {"event_type": "START_WALKING"},
                sequence_id=1,
                source_status="operator_weak_label",
            )
        )
        result, _layers = field_session_replay.evaluate_exp_a1_000(
            timeline,
            config=experiment_config(),
            lte_centroids={},
            lte_centroid_artifact=centroid_artifact("unavailable"),
        )
        baseline_a, baseline_b, baseline_c = result["baselines"]
        self.assertEqual(baseline_a["status"], "available")
        self.assertEqual(baseline_b["status"], "unavailable")
        self.assertEqual(baseline_c["status"], "unavailable")
        self.assertIsNone(baseline_b["endpoint_error_m"])
        self.assertIsNone(baseline_c["endpoint_error_m"])
        self.assertIn("lte_centroid_artifact_not_provided", baseline_b["reason_codes"])
        self.assertIn("calibrated_imu_blackout_coverage_missing", baseline_c["reason_codes"])

    def test_missing_pre_blackout_fix_and_endpoint_reference_remain_null(self) -> None:
        timeline = [
            row
            for row in complete_experiment_timeline()
            if not (row["source"] == "gnss" and (row["timestamp_utc_ns"] < BASE_NS or row["timestamp_utc_ns"] == BASE_NS + 60_000_000_000))
        ]
        result, _layers = field_session_replay.evaluate_exp_a1_000(
            timeline,
            config=experiment_config(),
            lte_centroids=centroids(),
            lte_centroid_artifact=centroid_artifact(),
        )
        baseline_a = result["baselines"][0]
        self.assertEqual(baseline_a["status"], "unavailable")
        self.assertIn("last_trusted_gnss_before_blackout_missing", baseline_a["reason_codes"])
        self.assertIsNone(baseline_a["endpoint_error_m"])
        self.assertEqual(result["reference"]["endpoint_status"], "unavailable")

    def test_endpoint_alone_cannot_make_an_empty_blackout_complete(self) -> None:
        timeline = [
            gnss_row(-1, 22.0, 114.0, sequence_id=1),
            gnss_row(60, 22.0, 114.0004, sequence_id=2),
            lte_row(-1, "A", sequence_id=1),
        ]
        for index in range(61):
            timeline.append(imu_row(float(index), 0.0, sequence_id=index + 1))

        masked, mask = field_session_replay.apply_gnss_mask(
            timeline,
            start_utc=BASE_UTC,
            duration_s=60,
        )
        result, _layers = field_session_replay.evaluate_exp_a1_000(
            timeline,
            config=experiment_config(),
            lte_centroids=centroids(),
            lte_centroid_artifact=centroid_artifact(),
        )

        self.assertEqual(mask["masked_observation_count"], 0)
        self.assertFalse(any(row["masked"] for row in masked))
        self.assertEqual(result["run_status"], "unavailable")
        self.assertEqual(result["reference"]["masked_reference_observation_count"], 0)
        self.assertTrue(
            all(baseline["status"] == "unavailable" for baseline in result["baselines"])
        )
        self.assertTrue(
            all(
                "gnss_blackout_masked_reference_missing" in baseline["reason_codes"]
                for baseline in result["baselines"]
            )
        )

    def test_direct_gnss_source_utc_supports_only_same_source_baseline_a(self) -> None:
        timeline = [
            direct_source_gnss_row(-1, 22.0, 114.0, sequence_id=1),
            direct_source_gnss_row(0, 22.0, 114.0, sequence_id=2),
            direct_source_gnss_row(30, 22.0, 114.0002, sequence_id=3),
            direct_source_gnss_row(60, 22.0, 114.0004, sequence_id=4),
            lte_row(-1, "A", sequence_id=1),
            lte_row(30, "B", sequence_id=2),
        ]
        for index in range(61):
            timeline.append(imu_row(float(index), 0.0, sequence_id=index + 1))

        _masked, mask = field_session_replay.apply_gnss_mask(
            timeline,
            start_utc=BASE_UTC,
            duration_s=60,
        )
        result, _layers = field_session_replay.evaluate_exp_a1_000(
            timeline,
            config=experiment_config(),
            lte_centroids=centroids(),
            lte_centroid_artifact=centroid_artifact(),
        )

        self.assertEqual(mask["masked_observation_count"], 2)
        self.assertFalse(mask["cross_source_aligned"])
        self.assertEqual(result["run_status"], "partial")
        self.assertEqual(result["reference"]["cross_source_aligned"], False)
        baseline_a, baseline_b, baseline_c = result["baselines"]
        self.assertEqual(baseline_a["status"], "available")
        self.assertEqual(baseline_b["status"], "unavailable")
        self.assertEqual(baseline_c["status"], "unavailable")
        self.assertIn("gnss_reference_not_cross_source_aligned", baseline_b["reason_codes"])
        self.assertIn("gnss_reference_not_cross_source_aligned", baseline_c["reason_codes"])
    def test_exact_cell_lookup_is_required_and_receive_only_lte_is_ignored(self) -> None:
        row = lte_row(-1, "A", sequence_id=1)
        row["alignment_status"] = "receive_only"
        row["timestamp_utc_ns"] = None
        self.assertEqual(field_session_replay._lte_observations([row]), [])

        timeline = complete_experiment_timeline()
        result, _layers = field_session_replay.evaluate_exp_a1_000(
            timeline,
            config=experiment_config(),
            lte_centroids={centroid_key("A"): (22.0, 114.0)},
            lte_centroid_artifact=centroid_artifact(),
        )
        baseline_b = result["baselines"][1]
        self.assertNotEqual(baseline_b["status"], "available")
        self.assertIn("lte_cell_coordinate_lookup_unavailable", baseline_b["reason_codes"])

    def test_centroid_artifact_requires_version_provenance_and_unique_exact_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "centroids.json"
            path.write_text(
                json.dumps(
                    {
                        "version": "v1",
                        "provenance": "unit-test-only",
                        "entries": [
                            {
                                "cell": {
                                    "rat": "LTE",
                                    "mcc": "460",
                                    "mnc": "01",
                                    "tac": "1001",
                                    "cell_id": "A",
                                },
                                "latitude_deg": 22.0,
                                "longitude_deg": 114.0,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            values, artifact = field_session_replay.load_lte_centroids(path)
            self.assertEqual(artifact["status"], "available")
            self.assertEqual(values[centroid_key("A")], (22.0, 114.0))

            path.write_text(json.dumps({"version": "v1", "entries": []}), encoding="utf-8")
            values, artifact = field_session_replay.load_lte_centroids(path)
            self.assertEqual(values, {})
            self.assertEqual(artifact["status"], "unavailable")

    def test_haversine_and_svg_outputs_are_deterministic(self) -> None:
        self.assertEqual(field_session_replay.haversine_m((22.0, 114.0), (22.0, 114.0)), 0.0)
        result, layers = field_session_replay.evaluate_exp_a1_000(
            complete_experiment_timeline(),
            config=experiment_config(),
            lte_centroids=centroids(),
            lte_centroid_artifact=centroid_artifact(),
        )
        first_map = field_session_replay.render_trajectory_svg(layers, title="fixture")
        second_map = field_session_replay.render_trajectory_svg(layers, title="fixture")
        first_error = field_session_replay.render_error_vs_time_svg(result)
        second_error = field_session_replay.render_error_vs_time_svg(result)
        self.assertEqual(first_map, second_map)
        self.assertEqual(first_error, second_error)
        self.assertIn("<svg", first_map)
        self.assertIn("position error", first_error)

    def test_cli_exit_codes_distinguish_completed_partial_and_invalid(self) -> None:
        package = mock.sentinel.package
        with (
            mock.patch.object(field_session_replay, "load_replay_package", return_value=package),
            mock.patch.object(
                field_session_replay,
                "write_exp_a1_000_outputs",
                return_value={
                    "experiment_id": field_session_replay.EXPERIMENT_ID,
                    "run_status": "partial",
                    "gate_status": "unverified",
                    "baselines": [],
                },
            ),
            mock.patch("builtins.print"),
        ):
            self.assertEqual(
                replay_field_session.main(
                    [
                        "exp-a1-000",
                        "--manifest",
                        "manifest.json",
                        "--output-dir",
                        "output",
                        "--blackout-start",
                        BASE_UTC,
                    ]
                ),
                1,
            )

        with (
            mock.patch.object(
                field_session_replay,
                "load_replay_package",
                side_effect=field_session_replay.FieldSessionReplayError("invalid"),
            ),
            mock.patch("builtins.print"),
        ):
            self.assertEqual(
                replay_field_session.main(
                    [
                        "replay",
                        "--manifest",
                        "manifest.json",
                        "--output-dir",
                        "output",
                    ]
                ),
                2,
            )


if __name__ == "__main__":
    unittest.main()

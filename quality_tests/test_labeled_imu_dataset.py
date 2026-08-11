from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest

from scripts import build_labeled_imu_dataset as builder
from scripts import run_imu_capture_session as capture
from quality_tests.test_imu_capture_session import valid_plan


def stable_bytes(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def samples_for(seed: int) -> tuple[list[dict], str]:
    samples = []
    raw = bytearray()
    for index in range(100):
        offset = index * 50_000
        accel = [seed + index, seed - index, 1000 + seed]
        gyro = [index * 2, -index * 2, seed]
        samples.append({"index": index, "offset_us": offset, "accel_mg": accel, "gyro_mdps": gyro})
        raw.extend(struct.pack("<Iiiiiii", offset, *(accel + gyro)))
    return samples, hashlib.sha256(raw).hexdigest()


def source_row(plan: dict, cmd_id: str, seed: int) -> dict:
    samples, digest = samples_for(seed)
    return {
        "contract_version": "egolink.imu_window.v1",
        "window_id": f"imuw-{cmd_id}-b1",
        "capture_cmd_id": cmd_id,
        "boot_count": 1,
        "device_id": plan["device_id"],
        "fw_version": "0.1.0-d2-009-wifi-window",
        "test_run_id": plan["test_run_id"],
        "source": "qmi8658_i2c",
        "source_status": "observed",
        "transport_type": "wifi",
        "sensor": {"model": "QMI8658A", "i2c_address": 106, "accel_unit": "mg", "gyro_unit": "mdps"},
        "capture": {
            "sample_count": 100,
            "requested_interval_us": 50_000,
            "capture_start_uptime_us": 1_000_000,
            "capture_end_uptime_us": 5_951_000,
            "min_interval_us": 49_900,
            "mean_interval_us": 50_000,
            "max_interval_us": 50_100,
            "deadline_miss_count": 0,
            "read_failure_count": 0,
            "mock_sample_count": 0,
            "warmup_sample_count": 10,
            "warmup_interval_us": 50_000,
            "cadence_quality_status": "qualified",
        },
        "mounting_profile_id": "unrecorded",
        "axis_mapping_status": "unrecorded",
        "calibration_profile_id": "unrecorded",
        "activity_label": "unknown",
        "label_source": "none",
        "training_allowed": False,
        "samples_sha256": digest,
        "samples": samples,
    }


def execution_for(plan: dict, plan_sha256: str, rows: list[dict]) -> dict:
    by_cmd = {row["capture_cmd_id"]: row for row in rows}
    results = []
    for session, window in capture.iter_planned_windows(plan):
        source = by_cmd[window["cmd_id"]]
        results.append(
            {
                "session_id": session["session_id"],
                "split_name": session["split_name"],
                "cmd_id": window["cmd_id"],
                "planned_activity": window["planned_activity"],
                "state": "ok",
                "training_allowed": False,
                "ack": {
                    "status": "ok",
                    "test_run_id": plan["test_run_id"],
                    "transport_type": "wifi",
                    "duplicate_local_execution_prevented": False,
                },
                "window": {
                    "window_id": source["window_id"],
                    "source": "qmi8658_i2c",
                    "source_status": "observed",
                    "transport_type": "wifi",
                    "cadence_quality_status": "qualified",
                    "training_allowed": False,
                },
            }
        )
    return {
        "schema_version": capture.EXECUTION_SCHEMA_VERSION,
        "plan_id": plan["plan_id"],
        "plan_sha256": plan_sha256,
        "device_id": plan["device_id"],
        "test_run_id": plan["test_run_id"],
        "mode": "execute",
        "status": "completed",
        "planned_window_count": 3,
        "completed_window_count": 3,
        "test_run_created": True,
        "commands_created": [window["cmd_id"] for _, window in capture.iter_planned_windows(plan)],
        "external_actions": [
            {"action": "create_test_run", "test_run_id": plan["test_run_id"], "state": "ok"},
            *[
                {"action": "create_command", "cmd_id": window["cmd_id"], "state": "ok"}
                for _, window in capture.iter_planned_windows(plan)
            ],
        ],
        "training_allowed": False,
        "results": results,
    }


def create_fixture(root: Path, *, plan: dict | None = None) -> dict[str, Path | list[dict] | dict]:
    plan = copy.deepcopy(plan or valid_plan())
    plan_path = root / "capture_plan.json"
    plan_raw = stable_bytes(plan)
    plan_path.write_bytes(plan_raw)
    rows = [source_row(plan, window["cmd_id"], index + 1) for index, (_, window) in enumerate(capture.iter_planned_windows(plan))]
    source_path = root / "imu_windows.jsonl"
    source_raw = b"".join(stable_bytes(row) for row in rows)
    source_path.write_bytes(source_raw)
    export_manifest = {
        "schema_version": "egolink.imu_window_export.v1",
        "selectors": {"device_id": plan["device_id"], "test_run_id": plan["test_run_id"]},
        "privacy": {"training_allowed": False},
        "summary": {
            "truncated": False,
            "valid_windows": 3,
            "invalid_windows": 0,
            "cadence_qualified_windows": 3,
        },
        "invalid": [],
        "outputs": {
            "imu_windows_jsonl": source_path.name,
            "imu_windows_jsonl_sha256": hashlib.sha256(source_raw).hexdigest(),
        },
        "ok": True,
    }
    export_manifest_path = root / "imu_window_export_manifest.json"
    export_manifest_path.write_bytes(stable_bytes(export_manifest))
    execution = execution_for(plan, hashlib.sha256(plan_raw).hexdigest(), rows)
    execution_path = root / "execution.json"
    execution_raw = stable_bytes(execution)
    execution_path.write_bytes(execution_raw)
    labels = ["stationary", "walking", "transition_or_unknown"]
    annotations = {
        "schema_version": builder.ANNOTATIONS_SCHEMA_VERSION,
        "plan_id": plan["plan_id"],
        "plan_sha256": hashlib.sha256(plan_raw).hexdigest(),
        "execution_sha256": hashlib.sha256(execution_raw).hexdigest(),
        "annotations": [
            {
                "annotation_id": f"ann-{index + 1}",
                "session_id": plan["sessions"][index]["session_id"],
                "cmd_id": row["capture_cmd_id"],
                "window_id": row["window_id"],
                "samples_sha256": row["samples_sha256"],
                "activity_label": labels[index],
                "label_source": "operator_direct_observation",
                "label_confidence": "high",
                "review_state": "operator_confirmed",
                "created_at": f"2026-08-11T08:0{index}:00+00:00",
            }
            for index, row in enumerate(rows)
        ],
    }
    annotations_path = root / "annotations.json"
    annotations_path.write_bytes(stable_bytes(annotations))
    return {
        "plan": plan,
        "rows": rows,
        "export_manifest": export_manifest,
        "execution": execution,
        "annotations": annotations,
        "plan_path": plan_path,
        "source_path": source_path,
        "export_manifest_path": export_manifest_path,
        "execution_path": execution_path,
        "annotations_path": annotations_path,
        "output_dir": root / "dataset",
    }


def build(fixture: dict) -> dict:
    return builder.build_dataset(
        imu_windows_path=fixture["source_path"],
        export_manifest_path=fixture["export_manifest_path"],
        plan_path=fixture["plan_path"],
        execution_path=fixture["execution_path"],
        annotations_path=fixture["annotations_path"],
        output_dir=fixture["output_dir"],
    )


def write_annotations(fixture: dict) -> None:
    fixture["annotations_path"].write_bytes(stable_bytes(fixture["annotations"]))


def write_source(fixture: dict) -> None:
    source_raw = b"".join(stable_bytes(row) for row in fixture["rows"])
    fixture["source_path"].write_bytes(source_raw)
    fixture["export_manifest"]["outputs"]["imu_windows_jsonl_sha256"] = hashlib.sha256(source_raw).hexdigest()
    fixture["export_manifest_path"].write_bytes(stable_bytes(fixture["export_manifest"]))


class LabeledImuDatasetTests(unittest.TestCase):
    def test_build_requires_confirmed_three_key_join_and_preserves_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = create_fixture(Path(tmp))
            before = fixture["source_path"].read_bytes()
            manifest = build(fixture)
            after = fixture["source_path"].read_bytes()
            output_rows = [
                json.loads(line)
                for line in (fixture["output_dir"] / "labelled_imu_windows.jsonl").read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(before, after)
        self.assertEqual(manifest["status"], "pipeline_seed_ready")
        self.assertTrue(manifest["pipeline_seed_ready"])
        self.assertFalse(manifest["training_ready"])
        self.assertFalse(manifest["training_allowed"])
        self.assertEqual(manifest["summary"]["target_window_count"], 2)
        self.assertEqual(manifest["summary"]["exclusion_window_count"], 1)
        self.assertEqual({row["activity_label"] for row in output_rows}, {"stationary", "walking", "transition_or_unknown"})
        self.assertTrue(all(row["training_allowed"] is False and row["training_ready"] is False for row in output_rows))
        self.assertEqual({row["dataset_role"] for row in output_rows}, {"target", "exclusion"})

    def test_missing_extra_wrong_or_duplicate_annotation_is_rejected(self) -> None:
        mutations = {
            "missing": lambda annotations: annotations.pop(),
            "extra": lambda annotations: annotations.append(
                {
                    "annotation_id": "ann-extra",
                    "session_id": "session-still",
                    "cmd_id": "not-planned",
                    "window_id": "imuw-not-planned-b1",
                    "samples_sha256": "f" * 64,
                    "activity_label": "stationary",
                    "label_source": "operator_direct_observation",
                    "label_confidence": "high",
                    "review_state": "operator_confirmed",
                    "created_at": "2026-08-11T08:30:00+00:00",
                }
            ),
            "wrong_hash": lambda annotations: annotations[0].update(samples_sha256="e" * 64),
            "duplicate": lambda annotations: annotations.append(copy.deepcopy(annotations[0])),
        }
        for name, mutation in mutations.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                fixture = create_fixture(Path(tmp))
                mutation(fixture["annotations"]["annotations"])
                write_annotations(fixture)
                with self.assertRaises(builder.DatasetBuildError):
                    build(fixture)

    def test_annotation_is_post_capture_confirmation_not_plan_autolabel(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = create_fixture(Path(tmp))
            fixture["annotations"]["annotations"][0]["activity_label"] = "walking"
            fixture["annotations"]["annotations"][0]["review_state"] = "operator_confirmed"
            write_annotations(fixture)
            build(fixture)
            rows = [
                json.loads(line)
                for line in (fixture["output_dir"] / "labelled_imu_windows.jsonl").read_text(encoding="utf-8").splitlines()
            ]
        changed = next(row for row in rows if row["cmd_id"] == "d5002-still")
        self.assertEqual(changed["planned_activity"], "stationary")
        self.assertEqual(changed["activity_label"], "walking")
        self.assertEqual(changed["label_source"], "operator_confirmed_annotation_sidecar")

    def test_duplicate_sample_hash_and_bad_quality_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = create_fixture(Path(tmp))
            fixture["rows"][1]["samples"] = copy.deepcopy(fixture["rows"][0]["samples"])
            fixture["rows"][1]["samples_sha256"] = fixture["rows"][0]["samples_sha256"]
            write_source(fixture)
            with self.assertRaisesRegex(builder.DatasetBuildError, "duplicate window_id or samples_sha256"):
                build(fixture)

        with tempfile.TemporaryDirectory() as tmp:
            fixture = create_fixture(Path(tmp))
            fixture["rows"][0]["capture"]["cadence_quality_status"] = "needs_review"
            write_source(fixture)
            with self.assertRaisesRegex(builder.DatasetBuildError, "cadence"):
                build(fixture)

    def test_session_crossing_splits_is_rejected_before_artifact_reads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = valid_plan()
            plan["sessions"][1]["session_id"] = plan["sessions"][0]["session_id"]
            plan_path = root / "capture_plan.json"
            plan_path.write_bytes(stable_bytes(plan))
            for name in ("execution.json", "annotations.json", "imu_windows.jsonl"):
                (root / name).write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(builder.DatasetBuildError, "crosses split"):
                builder.build_dataset(
                    imu_windows_path=root / "imu_windows.jsonl",
                    export_manifest_path=root / "export_manifest.json",
                    plan_path=plan_path,
                    execution_path=root / "execution.json",
                    annotations_path=root / "annotations.json",
                    output_dir=root / "output",
                )

    def test_no_input_can_promote_training_or_skip_operator_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = create_fixture(Path(tmp))
            fixture["annotations"]["training_allowed"] = True
            write_annotations(fixture)
            with self.assertRaisesRegex(builder.DatasetBuildError, "fields mismatch"):
                build(fixture)

        with tempfile.TemporaryDirectory() as tmp:
            fixture = create_fixture(Path(tmp))
            fixture["annotations"]["annotations"][0]["review_state"] = "planned"
            write_annotations(fixture)
            with self.assertRaisesRegex(builder.DatasetBuildError, "operator_confirmed"):
                build(fixture)

        with tempfile.TemporaryDirectory() as tmp:
            fixture = create_fixture(Path(tmp))
            fixture["rows"][0]["training_allowed"] = True
            write_source(fixture)
            with self.assertRaisesRegex(builder.DatasetBuildError, "privacy"):
                build(fixture)


if __name__ == "__main__":
    unittest.main()

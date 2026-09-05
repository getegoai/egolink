import copy
import json
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from pc_simulator.ego_call_media_probe import (
    MediaTraceError,
    TRACE_VERSION,
    evaluate_media_trace,
)


ROOT = Path(__file__).resolve().parents[1]
MS = 1_000_000


def _record(direction, sequence, trace_time_ms, *, observation_suffix="0"):
    source_role, target_role = (
        ("device", "guardian")
        if direction == "uplink"
        else ("guardian", "device")
    )
    return {
        "observation_id": f"obs-{direction}-{sequence}-{observation_suffix}",
        "packet_id": f"packet-{direction}-{sequence}",
        "session_id": "call020-offline-001",
        "direction": direction,
        "source_role": source_role,
        "source_id": f"{source_role}-fixture-001",
        "target_role": target_role,
        "target_id": f"{target_role}-fixture-001",
        "sequence": sequence,
        "source_clock_id": f"{source_role}-clock-boot-001",
        "source_time_ns": sequence * 20 * MS,
        "trace_clock_id": "pc-bridge-clock-boot-001",
        "trace_time_ns": trace_time_ms * MS,
        "encoded_size_bytes": 40,
    }


def _trace(*, count=5, trace_end_ms=130):
    records = []
    for sequence in range(count):
        records.append(_record("uplink", sequence, 5 + sequence * 20))
        records.append(_record("downlink", sequence, 10 + sequence * 20))
    return {
        "trace_version": TRACE_VERSION,
        "trace_id": "call020-media-trace-001",
        "session_id": "call020-offline-001",
        "trace_clock_id": "pc-bridge-clock-boot-001",
        "trace_start_time_ns": 0,
        "trace_end_time_ns": trace_end_ms * MS,
        "endpoints": {
            "device_id": "device-fixture-001",
            "guardian_id": "guardian-fixture-001",
        },
        "source_clock_ids": {
            "uplink": "device-clock-boot-001",
            "downlink": "guardian-clock-boot-001",
        },
        "config": {
            "expected_packet_count": {"uplink": count, "downlink": count},
            "nominal_packet_interval_ns": 20 * MS,
            "minimum_packets_per_direction_for_connected": 2,
            "duplex_window_ns": 50 * MS,
            "setup_timeout_ns": 100 * MS,
            "max_loss_ratio": 0.0,
            "max_jitter_ns": 10 * MS,
            "max_gap_ns": 80 * MS,
            "blackout_threshold_ns": 60 * MS,
            "max_recovery_ns": 60 * MS,
        },
        "records": records,
    }


class EgoCallMediaProbeTests(unittest.TestCase):
    def test_healthy_bidirectional_trace_connects_without_product_claim(self):
        result = evaluate_media_trace(_trace())

        self.assertEqual(result["evaluation_result"], "PASS")
        self.assertEqual(result["final_media_state"], "connected")
        self.assertTrue(result["full_duplex_observed"])
        self.assertEqual(
            [event["state"] for event in result["state_trace"]],
            ["probing", "connected"],
        )
        self.assertEqual(result["direction_metrics"]["uplink"]["lost_packet_count"], 0)
        self.assertEqual(result["direction_metrics"]["downlink"]["lost_packet_count"], 0)
        self.assertEqual(
            result["direction_metrics"]["uplink"]["max_source_cadence_error_ns"],
            0,
        )
        self.assertEqual(result["evaluation_config"], _trace()["config"])
        self.assertEqual(result["trace_window"]["duration_ns"], 130 * MS)
        self.assertFalse(result["claims"]["audio_content_retained"])
        self.assertEqual(result["claims"]["sim_lte_media"], "unverified")
        self.assertEqual(result["claims"]["production_rtc_provider"], "not_selected")
        self.assertEqual(result["claims"]["p0_call"], "NOT_RUN")

    def test_one_way_media_never_forges_connected(self):
        trace = _trace()
        trace["records"] = [
            record for record in trace["records"] if record["direction"] == "uplink"
        ]

        result = evaluate_media_trace(trace)

        self.assertEqual(result["evaluation_result"], "FAIL")
        self.assertEqual(result["final_media_state"], "failed")
        self.assertFalse(result["full_duplex_observed"])
        self.assertNotIn("connected", [event["state"] for event in result["state_trace"]])
        self.assertIn("full_duplex_not_observed", result["failure_reasons"])
        self.assertEqual(result["direction_metrics"]["downlink"]["loss_ratio"], 1.0)

    def test_loss_reorder_media_duplicate_and_replay_duplicate_are_independent(self):
        trace = _trace(trace_end_ms=120)
        trace["config"]["max_loss_ratio"] = 0.25
        trace["config"]["max_jitter_ns"] = 50 * MS
        trace["records"] = [
            _record("uplink", 0, 5),
            _record("uplink", 2, 25),
            _record("uplink", 1, 45),
            _record("uplink", 1, 52, observation_suffix="duplicate"),
            _record("uplink", 3, 65),
        ] + [
            _record("downlink", sequence, 10 + sequence * 20)
            for sequence in range(5)
        ]
        trace["records"].append(copy.deepcopy(trace["records"][0]))

        result = evaluate_media_trace(trace)
        uplink = result["direction_metrics"]["uplink"]

        self.assertEqual(result["evaluation_result"], "PASS")
        self.assertEqual(uplink["missing_sequences"], [4])
        self.assertEqual(uplink["lost_packet_count"], 1)
        self.assertEqual(uplink["reordered_packet_count"], 1)
        self.assertEqual(uplink["media_duplicate_packet_count"], 1)
        self.assertEqual(result["replay_duplicate_observation_count"], 1)
        self.assertEqual(result["direction_metrics"]["downlink"]["lost_packet_count"], 0)

    def test_internal_blackout_recovery_builds_reconnecting_timeline(self):
        trace = _trace(count=6, trace_end_ms=220)
        trace["config"].update(
            {
                "max_jitter_ns": 100 * MS,
                "max_gap_ns": 120 * MS,
                "max_recovery_ns": 60 * MS,
            }
        )
        trace["records"] = [
            _record("uplink", sequence, arrival)
            for sequence, arrival in enumerate([5, 25, 45, 155, 175, 195])
        ] + [
            _record("downlink", sequence, arrival)
            for sequence, arrival in enumerate([10, 30, 50, 70, 180, 200])
        ]

        result = evaluate_media_trace(trace)

        self.assertEqual(result["evaluation_result"], "PASS")
        self.assertEqual(result["final_media_state"], "connected")
        self.assertEqual(
            [event["state"] for event in result["state_trace"]],
            ["probing", "connected", "reconnecting", "connected"],
        )
        self.assertEqual(len(result["blackouts"]), 2)
        self.assertTrue(all(item["recovered"] for item in result["blackouts"]))
        self.assertEqual(
            {item["recovery_latency_ns"] for item in result["blackouts"]},
            {50 * MS},
        )

    def test_blackout_over_budget_or_unrecovered_terminates_failed(self):
        over_budget = _trace(count=6, trace_end_ms=220)
        over_budget["config"].update(
            {"max_jitter_ns": 100 * MS, "max_gap_ns": 120 * MS, "max_recovery_ns": 40 * MS}
        )
        over_budget["records"] = [
            _record("uplink", sequence, arrival)
            for sequence, arrival in enumerate([5, 25, 45, 155, 175, 195])
        ] + [
            _record("downlink", sequence, arrival)
            for sequence, arrival in enumerate([10, 30, 50, 70, 180, 200])
        ]
        result = evaluate_media_trace(over_budget)
        self.assertEqual(result["final_media_state"], "failed")
        self.assertIn("uplink_recovery_budget_exceeded", result["failure_reasons"])

        unrecovered = _trace(count=6, trace_end_ms=220)
        unrecovered["config"].update(
            {"max_loss_ratio": 0.5, "max_jitter_ns": 100 * MS, "max_gap_ns": 120 * MS}
        )
        unrecovered["records"] = [
            _record("uplink", sequence, arrival)
            for sequence, arrival in enumerate([5, 25, 45])
        ] + [
            _record("downlink", sequence, arrival)
            for sequence, arrival in enumerate([10, 30, 50, 70, 90, 200])
        ]
        result = evaluate_media_trace(unrecovered)
        self.assertEqual(result["final_media_state"], "failed")
        self.assertIn("uplink_blackout_unrecovered", result["failure_reasons"])
        self.assertTrue(any(not item["recovered"] for item in result["blackouts"]))

    def test_replay_is_order_independent_but_observation_reuse_fails_closed(self):
        trace = _trace()
        shuffled = copy.deepcopy(trace)
        random.Random(7).shuffle(shuffled["records"])
        self.assertEqual(evaluate_media_trace(trace), evaluate_media_trace(shuffled))

        exact_replay = copy.deepcopy(trace)
        exact_replay["records"].append(copy.deepcopy(exact_replay["records"][0]))
        result = evaluate_media_trace(exact_replay)
        self.assertEqual(result["replay_duplicate_observation_count"], 1)

        conflict = copy.deepcopy(exact_replay)
        conflict["records"][-1]["encoded_size_bytes"] += 1
        with self.assertRaisesRegex(MediaTraceError, "observation_id"):
            evaluate_media_trace(conflict)

    def test_identity_clock_sequence_and_time_lineage_fail_closed(self):
        mutations = []

        wrong_session = _trace()
        wrong_session["records"][0]["session_id"] = "other-session"
        mutations.append(wrong_session)

        wrong_source = _trace()
        wrong_source["records"][0]["source_id"] = "guardian-fixture-001"
        mutations.append(wrong_source)

        wrong_clock = _trace()
        wrong_clock["records"][0]["source_clock_id"] = "changed-clock"
        mutations.append(wrong_clock)

        out_of_range = _trace()
        out_of_range["records"][0]["sequence"] = 5
        mutations.append(out_of_range)

        source_regression = _trace()
        uplink_two = next(
            record
            for record in source_regression["records"]
            if record["direction"] == "uplink" and record["sequence"] == 2
        )
        uplink_two["source_time_ns"] = 10 * MS
        mutations.append(source_regression)

        trace_collision = _trace()
        trace_collision["records"][1]["trace_time_ns"] = trace_collision["records"][0][
            "trace_time_ns"
        ]
        mutations.append(trace_collision)

        outside_trace = _trace()
        outside_trace["records"][0]["trace_time_ns"] = outside_trace[
            "trace_end_time_ns"
        ] + 1
        mutations.append(outside_trace)

        for index, mutation in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(MediaTraceError):
                evaluate_media_trace(mutation)

    def test_trace_rejects_media_content_unknown_fields_and_nonfinite_budget(self):
        content = _trace()
        content["records"][0]["payload"] = "base64-audio-is-forbidden"
        with self.assertRaisesRegex(MediaTraceError, "fields must be exact"):
            evaluate_media_trace(content)

        provider = _trace()
        provider["config"]["rtc_provider"] = "premature-choice"
        with self.assertRaisesRegex(MediaTraceError, "fields must be exact"):
            evaluate_media_trace(provider)

        nonfinite = _trace()
        nonfinite["config"]["max_loss_ratio"] = float("nan")
        with self.assertRaises(MediaTraceError):
            evaluate_media_trace(nonfinite)

        boolean_time = _trace()
        boolean_time["records"][0]["trace_time_ns"] = True
        with self.assertRaises(MediaTraceError):
            evaluate_media_trace(boolean_time)

        stale_duplex_window = _trace()
        stale_duplex_window["config"]["duplex_window_ns"] = 61 * MS
        with self.assertRaisesRegex(MediaTraceError, "stale one-way"):
            evaluate_media_trace(stale_duplex_window)

    def test_cli_replays_json_and_preserves_nonclaims(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            trace_path = Path(temporary_directory) / "trace.json"
            trace_path.write_text(json.dumps(_trace()), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "pc_simulator.ego_call_media_probe",
                    str(trace_path),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["evaluation_result"], "PASS")
        self.assertEqual(result["claims"]["device_audio"], "unverified")
        self.assertEqual(result["claims"]["sim_lte_media"], "unverified")
        self.assertNotIn("packet_id", completed.stdout)
        self.assertNotIn("payload", completed.stdout)


if __name__ == "__main__":
    unittest.main()

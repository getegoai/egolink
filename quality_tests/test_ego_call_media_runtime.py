import copy
import json
import subprocess
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from pc_simulator.ego_call_media_probe import evaluate_media_trace
from pc_simulator.ego_call_media_runtime import (
    BlackoutFault,
    DelayFault,
    DeterministicFaultPlan,
    DirectionQueueConfig,
    EvaluationBudget,
    MediaRuntimeConfig,
    MediaRuntimeError,
    Pcm16EngineeringProfile,
    ProcessLocalBoundary,
    run_media_runtime,
)


ROOT = Path(__file__).resolve().parents[1]


def _assert_no_binary(test: unittest.TestCase, value):
    test.assertNotIsInstance(value, (bytes, bytearray, memoryview))
    if isinstance(value, dict):
        for item in value.values():
            _assert_no_binary(test, item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _assert_no_binary(test, item)


class EgoCallMediaRuntimeTests(unittest.TestCase):
    def test_healthy_duplex_uses_exact_profile_and_metadata_evaluator(self):
        captured = {}

        def inspect(trace):
            captured["trace"] = copy.deepcopy(trace)
            return evaluate_media_trace(trace)

        with mock.patch(
            "pc_simulator.ego_call_media_runtime.evaluate_media_trace",
            side_effect=inspect,
        ):
            result = run_media_runtime(MediaRuntimeConfig(frame_count=12))

        self.assertEqual(result["runtime_result"], "PASS")
        self.assertTrue(result["evaluation"]["full_duplex_observed"])
        self.assertEqual(result["evaluation"]["final_media_state"], "connected")
        self.assertEqual(
            result["profile"],
            {
                "encoding": "PCM_S16LE",
                "sample_rate_hz": 16000,
                "channels": 1,
                "sample_width_bytes": 2,
                "frame_duration_ms": 20,
                "samples_per_frame": 320,
                "frame_bytes": 640,
            },
        )
        self.assertEqual(result["boundary"]["transport"], "in_process_memory_datagram")
        self.assertEqual(result["boundary"]["signaling"], "in_process_fixture")
        self.assertEqual(
            result["boundary"]["encryption"], "not_applicable_process_local"
        )
        self.assertFalse(result["boundary"]["network_io"])
        self.assertEqual(
            result["boundary"]["external_adapter_copy_control"],
            "not_enforced_by_runtime",
        )
        self.assertTrue(
            result["clock_lineage"]["bridge_timestamps_strictly_monotonic"]
        )
        self.assertEqual(len(captured["trace"]["records"]), 24)
        for record in captured["trace"]["records"]:
            self.assertEqual(
                set(record),
                {
                    "observation_id",
                    "packet_id",
                    "session_id",
                    "direction",
                    "source_role",
                    "source_id",
                    "target_role",
                    "target_id",
                    "sequence",
                    "source_clock_id",
                    "source_time_ns",
                    "trace_clock_id",
                    "trace_time_ns",
                    "encoded_size_bytes",
                },
            )
            self.assertEqual(record["encoded_size_bytes"], 640)
            _assert_no_binary(self, record)

    def test_one_way_fault_never_connects(self):
        frame_count = 12
        result = run_media_runtime(
            MediaRuntimeConfig(
                frame_count=frame_count,
                faults=DeterministicFaultPlan(
                    blackouts=(BlackoutFault("downlink", 0, frame_count - 1),)
                ),
            )
        )

        self.assertEqual(result["runtime_result"], "FAIL")
        self.assertFalse(result["evaluation"]["full_duplex_observed"])
        self.assertEqual(result["evaluation"]["final_media_state"], "failed")
        self.assertNotIn(
            "connected",
            [event["state"] for event in result["evaluation"]["state_trace"]],
        )
        self.assertEqual(
            result["direction_runtime_stats"]["downlink"]["frames_delivered"], 0
        )

    def test_blackout_has_deterministic_bounded_recovery(self):
        config = MediaRuntimeConfig(
            frame_count=12,
            evaluation=EvaluationBudget(max_loss_ratio=0.5, max_recovery_ns=40_000_000),
            faults=DeterministicFaultPlan(
                blackouts=(BlackoutFault("uplink", 4, 7),)
            ),
        )

        result = run_media_runtime(config)

        self.assertEqual(result["runtime_result"], "PASS")
        self.assertEqual(
            [event["state"] for event in result["evaluation"]["state_trace"]],
            ["probing", "connected", "reconnecting", "connected"],
        )
        self.assertEqual(len(result["evaluation"]["blackouts"]), 1)
        blackout = result["evaluation"]["blackouts"][0]
        self.assertEqual(blackout["direction"], "uplink")
        self.assertTrue(blackout["recovered"])
        self.assertEqual(blackout["recovery_latency_ns"], 40_000_000)
        self.assertEqual(
            result["direction_runtime_stats"]["uplink"]["frames_dropped_blackout"],
            4,
        )

    def test_blackout_over_recovery_budget_fails_honestly(self):
        result = run_media_runtime(
            MediaRuntimeConfig(
                frame_count=12,
                evaluation=EvaluationBudget(
                    max_loss_ratio=0.5, max_recovery_ns=20_000_000
                ),
                faults=DeterministicFaultPlan(
                    blackouts=(BlackoutFault("uplink", 4, 7),)
                ),
            )
        )

        self.assertEqual(result["runtime_result"], "FAIL")
        self.assertEqual(result["evaluation"]["final_media_state"], "failed")
        self.assertIn(
            "uplink_recovery_budget_exceeded",
            result["evaluation"]["failure_reasons"],
        )

    def test_independent_queue_backpressure_is_bounded_and_visible(self):
        result = run_media_runtime(
            MediaRuntimeConfig(
                frame_count=12,
                downlink_queue=DirectionQueueConfig(
                    capacity_frames=2,
                    service_interval_frames=4,
                    service_batch_frames=1,
                ),
            )
        )

        uplink = result["direction_runtime_stats"]["uplink"]
        downlink = result["direction_runtime_stats"]["downlink"]
        self.assertEqual(uplink["frames_dropped_backpressure"], 0)
        self.assertGreater(downlink["frames_dropped_backpressure"], 0)
        self.assertLessEqual(downlink["peak_queue_depth"], 2)
        self.assertEqual(downlink["final_queue_depth"], 0)
        self.assertEqual(result["runtime_result"], "FAIL")
        self.assertIn(
            "downlink_loss_budget_exceeded",
            result["evaluation"]["failure_reasons"],
        )

    def test_delay_can_reorder_one_direction_without_mixing_the_other(self):
        result = run_media_runtime(
            MediaRuntimeConfig(
                frame_count=8,
                faults=DeterministicFaultPlan(
                    delays=(DelayFault("uplink", 0, 2),)
                ),
            )
        )

        uplink = result["direction_runtime_stats"]["uplink"]
        downlink = result["direction_runtime_stats"]["downlink"]
        self.assertEqual(result["runtime_result"], "PASS")
        self.assertEqual(uplink["configured_delayed_frames"], 1)
        self.assertEqual(uplink["reordered_delivery_count"], 1)
        self.assertEqual(
            result["evaluation"]["direction_metrics"]["uplink"][
                "reordered_packet_count"
            ],
            1,
        )
        self.assertEqual(downlink["reordered_delivery_count"], 0)

    def test_identity_profile_boundary_and_fault_config_fail_closed(self):
        invalid = [
            replace(MediaRuntimeConfig(), guardian_id="device-fixture-001"),
            replace(MediaRuntimeConfig(), bridge_clock_id="device-clock-boot-001"),
            replace(MediaRuntimeConfig(), session_id="newline\nis_forbidden"),
            replace(
                MediaRuntimeConfig(),
                profile=Pcm16EngineeringProfile(sample_rate_hz=8_000),
            ),
            replace(
                MediaRuntimeConfig(),
                profile=Pcm16EngineeringProfile(channels=True),
            ),
            replace(
                MediaRuntimeConfig(),
                boundary=ProcessLocalBoundary(network_io=True),
            ),
            replace(
                MediaRuntimeConfig(),
                boundary=ProcessLocalBoundary(network_io=0),
            ),
            replace(
                MediaRuntimeConfig(),
                downlink_queue=DirectionQueueConfig(
                    capacity_frames=1, service_batch_frames=2
                ),
            ),
            replace(
                MediaRuntimeConfig(),
                faults=DeterministicFaultPlan(
                    blackouts=(
                        BlackoutFault("uplink", 2, 4),
                        BlackoutFault("uplink", 4, 5),
                    )
                ),
            ),
        ]

        for index, config in enumerate(invalid):
            with self.subTest(index=index), self.assertRaises(MediaRuntimeError):
                run_media_runtime(config)

    def test_replay_is_exactly_deterministic(self):
        config = MediaRuntimeConfig(
            frame_count=12,
            evaluation=EvaluationBudget(max_loss_ratio=0.5),
            faults=DeterministicFaultPlan(
                blackouts=(BlackoutFault("downlink", 5, 6),),
                delays=(DelayFault("uplink", 1, 2),),
            ),
        )

        self.assertEqual(run_media_runtime(config), run_media_runtime(config))

    def test_delivered_and_dropped_buffers_are_zeroed_and_results_are_metadata_only(self):
        buffers = []
        borrowed_by_sink = []

        def factory(_direction, sequence, frame_bytes):
            marker = (sequence + 1) & 0xFF
            buffer = bytearray([marker]) * frame_bytes
            buffers.append(buffer)
            return buffer

        def sink(_direction, _sequence, payload):
            self.assertTrue(any(payload))
            borrowed_by_sink.append(payload)

        result = run_media_runtime(
            MediaRuntimeConfig(
                frame_count=8,
                faults=DeterministicFaultPlan(
                    blackouts=(BlackoutFault("downlink", 2, 3),)
                ),
                evaluation=EvaluationBudget(max_loss_ratio=0.25),
            ),
            frame_factory=factory,
            frame_sink=sink,
        )

        self.assertEqual(len(buffers), 16)
        self.assertEqual(len(borrowed_by_sink), 14)
        self.assertTrue(all(not any(buffer) for buffer in buffers))
        self.assertEqual(
            result["buffer_lifecycle"]["created_mutable_buffers"],
            result["buffer_lifecycle"]["zeroized_after_delivery"]
            + result["buffer_lifecycle"]["zeroized_after_drop"]
            + result["buffer_lifecycle"]["zeroized_during_cleanup"],
        )
        self.assertEqual(result["buffer_lifecycle"]["outstanding_mutable_buffers"], 0)
        self.assertEqual(
            result["boundary"]["external_adapter_copy_control"],
            "not_enforced_by_runtime",
        )
        _assert_no_binary(self, result)
        serialized = json.dumps(result, sort_keys=True)
        self.assertNotIn("payload", serialized)
        self.assertNotIn("packet_id", serialized)

    def test_invalid_mutable_frame_is_zeroed_before_rejection(self):
        retained = []

        def invalid_factory(_direction, _sequence, _frame_bytes):
            buffer = bytearray(b"not-640-bytes")
            retained.append(buffer)
            return buffer

        with self.assertRaisesRegex(MediaRuntimeError, "wrong byte length"):
            run_media_runtime(MediaRuntimeConfig(), frame_factory=invalid_factory)
        self.assertEqual(len(retained), 1)
        self.assertFalse(any(retained[0]))

    def test_cli_emits_only_metadata_summary(self):
        completed = subprocess.run(
            [
                sys.executable,
                "-B",
                "-m",
                "pc_simulator.ego_call_media_runtime",
                "--frames",
                "12",
                "--scenario",
                "healthy",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        output = json.loads(completed.stdout)
        self.assertEqual(output["runtime_result"], "PASS")
        self.assertFalse(output["bounded_run"]["raw_audio_persisted"])
        self.assertFalse(output["bounded_run"]["socket_network_hardware_used"])
        self.assertNotIn("packet_id", completed.stdout)
        self.assertNotIn("observation_id", completed.stdout)
        self.assertNotIn("payload", completed.stdout)


if __name__ == "__main__":
    unittest.main()

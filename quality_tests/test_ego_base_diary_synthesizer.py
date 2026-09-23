from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from pc_simulator.ego_base_diary_synthesizer import EgoBaseDiarySynthesizer, ActivityEpisode
from scripts.generate_daily_semantic_diary import generate_representative_full_day_timeline


class TestEgoBaseDiarySynthesizer(unittest.TestCase):
    def setUp(self):
        self.synthesizer = EgoBaseDiarySynthesizer()

    def test_state_to_activity_mapping(self):
        m = self.synthesizer.map_state_to_activity_type
        self.assertEqual(m("stationary"), "stationary_work")
        self.assertEqual(m("stationary", is_charging=True), "charging_rest")
        self.assertEqual(m("stationary_charging"), "charging_rest")
        self.assertEqual(m("walking"), "outdoor_walk")
        self.assertEqual(m("running"), "running_workout")
        self.assertEqual(m("cycling"), "cycling_trip")
        self.assertEqual(m("in_vehicle"), "commute_transit")
        self.assertEqual(m("manual_sos"), "emergency_incident")
        self.assertEqual(m("fall_suspected"), "emergency_incident")

    def test_episodic_segmentation(self):
        # 10 walking windows, followed by 5 vehicle windows
        windows = []
        t = 0.0
        for _ in range(10):
            windows.append({
                "time_offset_s": t,
                "arbitrated_state": "walking",
                "confidence": 0.92,
                "speed_mps": 1.4,
            })
            t += 5.0
        for _ in range(5):
            windows.append({
                "time_offset_s": t,
                "arbitrated_state": "in_vehicle",
                "confidence": 0.98,
                "speed_mps": 10.0,
            })
            t += 5.0

        episodes = self.synthesizer.segment_timeline_into_episodes(windows)
        self.assertEqual(len(episodes), 2)

        ep1 = episodes[0]
        self.assertEqual(ep1.activity_type, "outdoor_walk")
        self.assertEqual(ep1.window_count, 10)
        self.assertEqual(ep1.duration_seconds, 50.0)
        self.assertAlmostEqual(ep1.mean_speed_mps, 1.4, places=2)

        ep2 = episodes[1]
        self.assertEqual(ep2.activity_type, "commute_transit")
        self.assertEqual(ep2.window_count, 5)
        self.assertEqual(ep2.duration_seconds, 25.0)
        self.assertAlmostEqual(ep2.mean_speed_mps, 10.0, places=2)

    def test_daily_statistics_safe_day(self):
        windows = generate_representative_full_day_timeline()
        episodes = self.synthesizer.segment_timeline_into_episodes(windows)
        stats = self.synthesizer.compute_daily_statistics(episodes)

        self.assertTrue(stats["is_day_completely_safe"])
        self.assertEqual(stats["safety_incident_count"], 0)
        self.assertGreater(stats["active_minutes"], 0)
        self.assertGreater(stats["sedentary_minutes"], 0)
        self.assertGreater(stats["transit_minutes"], 0)
        self.assertGreater(stats["rest_minutes"], 0)

    def test_daily_statistics_with_safety_incident(self):
        windows = generate_representative_full_day_timeline()
        # Inject an emergency SOS window
        windows.append({
            "time_offset_s": 5000.0,
            "arbitrated_state": "manual_sos",
            "confidence": 1.0,
            "is_safety_override": True,
            "arbitration_reason": "Physical SOS button pressed",
        })

        episodes = self.synthesizer.segment_timeline_into_episodes(windows)
        stats = self.synthesizer.compute_daily_statistics(episodes)

        self.assertFalse(stats["is_day_completely_safe"])
        self.assertGreaterEqual(stats["safety_incident_count"], 1)

    def test_generate_diary_markdown(self):
        windows = generate_representative_full_day_timeline()
        episodes = self.synthesizer.segment_timeline_into_episodes(windows)
        stats = self.synthesizer.compute_daily_statistics(episodes)

        md = self.synthesizer.generate_semantic_diary_markdown(episodes, stats, "2026-09-23")
        self.assertIn("Ego Link Daily Life Journal", md)
        self.assertIn("Guardian Peace-of-Mind Summary", md)
        self.assertIn("Activity Time Allocation", md)
        self.assertIn("Episodic Timeline Narrative", md)
        self.assertIn("ALL NORMAL", md)


if __name__ == "__main__":
    unittest.main()

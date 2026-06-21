from __future__ import annotations

import unittest

from model_lab.safety_companion.src.feature_extractor import build_model_input
from model_lab.safety_companion.src.scenario_generator import sample_sensor_frames


class FeatureExtractorTests(unittest.TestCase):
    def test_sos_frame_maps_user_input(self) -> None:
        frame = next(item for item in sample_sensor_frames() if item["frame_id"] == "frame-sos-001")
        value = build_model_input(frame)
        self.assertTrue(value["features"]["user"]["sos_pressed"])
        self.assertTrue(value["evidence_available"]["fresh_gnss"])


if __name__ == "__main__":
    unittest.main()

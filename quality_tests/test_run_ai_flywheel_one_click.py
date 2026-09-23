"""Unit tests for One-Click AI Flywheel Pipeline (AI-050).

Validates end-to-end execution of:
1. Slicing/Ingestion
2. Shadow evaluation & gold sample mining
3. Continuous fine-tuning
4. Safety regression gate & binary packaging
5. Ego Base semantic diary synthesis
"""

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts.run_ai_flywheel_one_click import run_one_click_flywheel


class TestRunAiFlywheelOneClick(unittest.TestCase):

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="test_one_click_flywheel_"))

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_run_one_click_flywheel_end_to_end(self):
        res = run_one_click_flywheel(
            output_root=self.temp_dir,
            model_version=3,
            date_str="2026-09-23",
        )

        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["model_version"], 3)
        self.assertGreater(res["windows_count"], 0)
        self.assertGreater(res["gold_samples_count"], 0)
        self.assertLess(res["binary_size_kb"], 30.0)
        self.assertTrue(len(res["sha256"]) == 64)

        # Check generated files
        harvester_manifest = self.temp_dir / "harvester" / "dataset_manifest.json"
        shadow_summary = self.temp_dir / "shadow_v1" / "shadow_evaluation_summary.json"
        flywheel_report = self.temp_dir / "flywheel_v3" / "retraining_report.json"
        ota_bin = self.temp_dir / "flywheel_v3" / "ego_model_v3.bin"
        diary_md = self.temp_dir / "ego_base" / "daily_life_diary_20260923.md"
        guardian_card = self.temp_dir / "ego_base" / "daily_guardian_summary_20260923.json"

        self.assertTrue(shadow_summary.is_file())
        self.assertTrue(flywheel_report.is_file())
        self.assertTrue(ota_bin.is_file())
        self.assertTrue(diary_md.is_file())
        self.assertTrue(guardian_card.is_file())

        with open(guardian_card, "r", encoding="utf-8") as f:
            card_data = json.load(f)
            self.assertEqual(card_data["date"], "2026-09-23")
            self.assertEqual(card_data["model_version_active"], 3)
            self.assertIn("active_minutes", card_data["statistics"])


if __name__ == "__main__":
    unittest.main()

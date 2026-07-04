import unittest
from pathlib import Path


class DataFlywheelPipelineDocTests(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[1]
        self.spec = (
            self.repo_root / "docs" / "development" / "DATA_FLYWHEEL_PIPELINE.md"
        ).read_text(encoding="utf-8")
        self.spec_flat = " ".join(self.spec.split())
        self.task = (
            self.repo_root
            / "docs"
            / "tasks"
            / "done"
            / "DATA-002_DATA_FLYWHEEL_PIPELINE_SPEC.md"
        ).read_text(encoding="utf-8")

    def test_default_training_and_raw_media_rules_are_locked(self):
        for token in (
            "training_allowed=false",
            "raw_audio_allowed=false",
            "raw_image_allowed=false",
            "raw_wifi_bssid_retention=false",
        ):
            self.assertIn(token, self.spec)

    def test_candidate_records_require_privacy_consent_and_deletion_controls(self):
        for token in (
            "consent_status",
            "privacy_class",
            "delete_request_id",
            "deletion_state",
            "split_leakage_checked",
            "source_manifest_hash",
            "session_blocked",
            "split_leakage_blocked",
        ):
            self.assertIn(token, self.spec)

    def test_spec_references_privacy_boundary_and_blocks_dashboard_training(self):
        self.assertIn("../product/PRODUCT_DEMO_PRIVACY_BOUNDARY.md", self.spec)
        self.assertIn("A Dashboard view is not a training source by itself", self.spec_flat)
        self.assertIn("Product-demo and V1 field-test records remain non-training", self.task)

    def test_model_training_and_ota_remain_future_work(self):
        for token in (
            "it does not perform model training",
            "planned_not_implemented",
            "No firmware, device protocol, Message Hub deployment, or OTA update behavior changes",
        ):
            self.assertIn(token, self.spec_flat)


if __name__ == "__main__":
    unittest.main()

import unittest
from pathlib import Path


class ModelFootprintAssessmentDocTests(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[1]
        self.doc = (
            self.repo_root / "docs" / "modeling" / "MODEL_FOOTPRINT_ASSESSMENT.md"
        ).read_text(encoding="utf-8")
        self.doc_flat = " ".join(self.doc.split())
        self.task = (
            self.repo_root
            / "docs"
            / "tasks"
            / "active"
            / "MODEL-001_MODEL_FOOTPRINT_ASSESSMENT.md"
        ).read_text(encoding="utf-8")
        self.plan = (
            self.repo_root / "docs" / "roadmap" / "V1_PRODUCT_PLAN.md"
        ).read_text(encoding="utf-8")

    def test_no_budget_is_verified_without_measured_evidence(self):
        for token in (
            "No model-footprint value is verified until",
            "`TBD(MODEL-001)` values in production requirements",
            "Estimates are useful for planning",
            "must remain marked `estimated`",
        ):
            self.assertIn(token, self.doc)

    def test_protocol_tracks_evidence_levels_and_measurement_axes(self):
        for token in (
            "protocol_defined",
            "artifact_estimated",
            "build_verified",
            "runtime_measured",
            "power_measured",
            "candidate_compared",
            "Static firmware footprint",
            "Runtime RAM",
            "Latency",
            "Power",
        ):
            self.assertIn(token, self.doc)

    def test_minimum_report_manifest_covers_prod_001_budget_fields(self):
        for token in (
            "ram_peak_bytes",
            "flash_total_bytes",
            "latency_p50_ms",
            "latency_p95_ms",
            "energy_per_inference_mj",
            "source_status",
            "known_gaps",
            "evidence_paths",
        ):
            self.assertIn(token, self.doc)

    def test_model_001_remains_active_until_measurements_exist(self):
        self.assertIn("status: paused", self.task)
        self.assertIn("MODEL-001 remains open but paused for D1", self.task)
        self.assertIn("Paused by NORTH_STAR alignment", self.task)
        self.assertIn("measurements pending", self.plan)
        self.assertIn("A passing build is not runtime RAM, latency, or power evidence", self.doc_flat)


if __name__ == "__main__":
    unittest.main()

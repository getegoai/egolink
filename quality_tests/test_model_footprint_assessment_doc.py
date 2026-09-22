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
        self.plan_flat = " ".join(self.plan.split())

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

    def test_model_001_rebase_keeps_measurements_honest_without_blocking_launch(self):
        self.assertIn("status: paused", self.task)
        self.assertIn("ADR-0011", self.task)
        self.assertIn("Deterministic Safety Kernel resource fit remains a hardware selection gate", self.task)
        self.assertIn("do not block the first", self.task)
        self.assertIn("not globally blocked", self.task)
        self.assertIn("ADR-0016", self.plan)
        for token in (
            "MODEL-001 measurements remain pending",
            "runtime RAM/latency, inference energy and comparable MCU evidence",
            "cannot be inferred from static footprint or builds",
            "Measured deterministic Safety Kernel resource/power fit remains a hardware selection gate",
            "advanced-model benchmarks do not block the three P0 capability Gates",
            "Current rule-state truth still requires the engineering acceptance above",
        ):
            self.assertIn(token, self.plan_flat)
        self.assertIn("A passing build is not runtime RAM, latency, or power evidence", self.doc_flat)


if __name__ == "__main__":
    unittest.main()

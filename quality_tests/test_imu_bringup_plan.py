from __future__ import annotations

from pathlib import Path
import unittest


class ImuBringupPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.plan_path = self.repo_root / "docs" / "hardware" / "TIMU_001_REAL_IMU_BRINGUP_PLAN.md"
        self.matrix_path = self.repo_root / "docs" / "modeling" / "HARDWARE_SENSOR_MATRIX.md"
        self.status_path = self.repo_root / "docs" / "STATUS.md"
        self.plan = self.plan_path.read_text(encoding="utf-8")
        self.matrix = self.matrix_path.read_text(encoding="utf-8")
        self.status = self.status_path.read_text(encoding="utf-8")

    def test_plan_records_current_real_imu_boundary(self) -> None:
        self.assertTrue(self.plan_path.is_file())
        for token in [
            "no repo-backed evidence",
            "imu_source=mock_stationary",
            "imu_hardware_present=false",
            "imu_driver_enabled=false",
            "imu_sample_mock=true",
            "not real motion data",
        ]:
            with self.subTest(token=token):
                self.assertIn(token, self.plan)

    def test_plan_names_candidates_without_freezing_product_part(self) -> None:
        for token in [
            "ST STEVAL-MKI227KA",
            "LSM6DSV16X",
            "SensorTile.box PRO",
            "Candidate hardware only",
            "not a frozen product part",
        ]:
            with self.subTest(token=token):
                self.assertIn(token, self.plan)

    def test_real_driver_gates_require_identity_and_live_capture(self) -> None:
        for token in [
            "WHOAMI",
            "imu_hardware_present=true",
            "imu_driver_enabled=true",
            "imu_sample_mock=false",
            "Sample-rate report",
            "Quality gate",
            "Replay",
        ]:
            with self.subTest(token=token):
                self.assertIn(token, self.plan)

    def test_status_and_matrix_keep_timu_boundary_visible(self) -> None:
        self.assertIn("TIMU-001", self.status)
        self.assertIn("TIMU_001_REAL_IMU_BRINGUP_PLAN.md", self.status)
        self.assertIn("TIMU-001", self.matrix)
        self.assertIn("TIMU_001_REAL_IMU_BRINGUP_PLAN.md", self.matrix)


if __name__ == "__main__":
    unittest.main()

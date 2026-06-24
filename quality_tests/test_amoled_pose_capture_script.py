from __future__ import annotations

from pathlib import Path
import unittest


class AmoledPoseCaptureScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.script_path = self.repo_root / "scripts" / "capture_amoled_qmi8658_pose_set.ps1"
        self.script = self.script_path.read_text(encoding="utf-8")

    def test_script_uses_bounded_serial_capture_without_pyserial_dependency(self) -> None:
        required_terms = [
            "System.IO.Ports.SerialPort",
            "TimeoutSeconds",
            "ReadTimeoutMs",
            "amoled_bridge_done",
            "RTS reset pulse",
            "UTF8Encoding]::new($false)",
            "skipped_non_json_lines",
            "Write-Utf8NoBomLines -Path $LogPath",
        ]

        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, self.script)

        self.assertNotIn("pyserial", self.script.lower())
        self.assertNotIn("pip install", self.script.lower())
        self.assertNotIn("*> $LogPath", self.script)

    def test_script_preserves_pose_labels_and_unverified_source_boundary(self) -> None:
        required_terms = [
            "z_negative",
            "x_positive",
            "y_positive",
            "source_boundary",
            "bridge_uplink/unverified",
            "formal_imu_acceptance = $false",
        ]

        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, self.script)

    def test_script_can_run_pose_analysis_and_m1_loop(self) -> None:
        required_terms = [
            "scripts\\analyze_imu_pose_quality.py",
            "scripts\\board_bridge.py",
            "scripts\\session_recorder.py",
            "scripts\\inspect_session_recording.py",
            "scripts\\replay_session_recording.py",
            "$SessionId.pose_quality.md",
            "TIMU_004B_QMI8658_MANUAL_CAPTURE_20260623.md",
        ]

        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, self.script)

    def test_script_supports_motion_only_with_existing_pose_sources(self) -> None:
        required_terms = [
            "[string[]]$ExistingPose",
            "[switch]$MotionOnly",
            "Convert-ExistingPoseSource",
            "ExistingPose must use LABEL=PATH",
            "$PoseLabels = @()",
            "$CaptureMotion = $true",
            "No captures selected",
        ]

        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, self.script)


if __name__ == "__main__":
    unittest.main()

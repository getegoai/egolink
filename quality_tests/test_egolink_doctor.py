from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import egolink_doctor


class EgoLinkDoctorTests(unittest.TestCase):
    def test_passing_structure_report_contains_required_json_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.create_required_structure(root)

            with mock.patch.object(egolink_doctor, "check_git_work_tree") as git_check:
                git_check.return_value = egolink_doctor.DoctorCheck(
                    "git_work_tree",
                    True,
                    "Root is inside a Git work tree.",
                )
                with mock.patch.object(egolink_doctor, "check_required_commands") as command_checks:
                    command_checks.return_value = [
                        egolink_doctor.DoctorCheck("command:python", True, "Found python"),
                        egolink_doctor.DoctorCheck("command:git", True, "Found git"),
                        egolink_doctor.DoctorCheck("command:codex", True, "Found codex"),
                    ]

                    report = egolink_doctor.run_doctor(root)

            self.assertTrue(report["ok"])
            self.assertEqual(report["root"], str(root.resolve()))
            self.assertIn("checks", report)
            self.assertIn("summary", report)
            self.assertEqual(report["summary"]["failed"], 0)
            for check in report["checks"]:
                self.assertIn("name", check)
                self.assertIn("ok", check)
                self.assertIn("detail", check)

            json.dumps(report)

    def test_failing_structure_reports_missing_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "firmware").mkdir()

            with mock.patch.object(egolink_doctor, "check_git_work_tree") as git_check:
                git_check.return_value = egolink_doctor.DoctorCheck(
                    "git_work_tree",
                    True,
                    "Root is inside a Git work tree.",
                )
                with mock.patch.object(egolink_doctor, "check_required_commands") as command_checks:
                    command_checks.return_value = [
                        egolink_doctor.DoctorCheck("command:python", True, "Found python"),
                        egolink_doctor.DoctorCheck("command:git", True, "Found git"),
                        egolink_doctor.DoctorCheck("command:codex", True, "Found codex"),
                    ]

                    report = egolink_doctor.run_doctor(root)

            self.assertFalse(report["ok"])
            failed_names = {check["name"] for check in report["checks"] if not check["ok"]}
            self.assertIn("directory:pc_simulator", failed_names)
            self.assertIn("directory:quality_tests", failed_names)
            self.assertIn("directory:docs", failed_names)
            self.assertIn("directory:scripts", failed_names)
            self.assertIn("file:README.md", failed_names)

    def test_main_returns_nonzero_when_required_check_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            with mock.patch.object(egolink_doctor, "check_git_work_tree") as git_check:
                git_check.return_value = egolink_doctor.DoctorCheck(
                    "git_work_tree",
                    True,
                    "Root is inside a Git work tree.",
                )
                with mock.patch.object(egolink_doctor, "check_required_commands") as command_checks:
                    command_checks.return_value = [
                        egolink_doctor.DoctorCheck("command:python", True, "Found python"),
                        egolink_doctor.DoctorCheck("command:git", True, "Found git"),
                        egolink_doctor.DoctorCheck("command:codex", True, "Found codex"),
                    ]

                    with mock.patch("builtins.print"):
                        exit_code = egolink_doctor.main(["--root", str(root), "--json"])

            self.assertNotEqual(exit_code, 0)

    def create_required_structure(self, root: Path) -> None:
        for directory_name in egolink_doctor.REQUIRED_TOP_LEVEL_DIRECTORIES:
            (root / directory_name).mkdir()
        (root / "README.md").write_text("# Ego Link P0\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()

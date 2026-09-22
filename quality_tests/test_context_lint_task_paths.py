"""Task paths distinguish required context from ignored, not-yet-made outputs."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import context_lint


class ContextLintTaskPathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        subprocess.run(["git", "init", "--quiet", str(self.repo)], check=True)
        (self.repo / "docs/tasks/active").mkdir(parents=True)
        (self.repo / "input.md").write_text("Required input\n", encoding="utf-8")
        (self.repo / ".gitignore").write_text(
            "/reports/\n/firmware/**/build_*/\n"
            "/firmware/**/sdkconfig.*.local\n*.log\n"
            "/exports/*\n!/exports/required.json\n",
            encoding="utf-8",
        )

    def lint_paths(self, *, context: list[str], allowed: list[str]) -> list[str]:
        (self.repo / "docs/tasks/active/TEST.json").write_text(
            json.dumps({"context": context, "allowed_paths": allowed}),
            encoding="utf-8",
        )
        errors: list[str] = []
        with patch.object(context_lint, "ROOT", self.repo):
            context_lint.check_active_tasks(errors)
        return errors

    def assert_single_error(self, errors: list[str], category: str) -> None:
        self.assertEqual(len(errors), 1, errors)
        self.assertIn(category, errors[0])

    def test_existing_input_and_output_paths_are_valid(self) -> None:
        self.assertEqual(
            self.lint_paths(context=["./input.md"], allowed=["input.md"]), []
        )

    def test_context_must_exist_even_when_git_ignored(self) -> None:
        for missing in ["absent.md", "reports/not-created.json"]:
            with self.subTest(missing=missing):
                self.assert_single_error(
                    self.lint_paths(context=[missing], allowed=[]), "missing context path"
                )

    def test_missing_unignored_output_is_an_error(self) -> None:
        self.assert_single_error(
            self.lint_paths(context=["input.md"], allowed=["src/typo.py"]),
            "missing allowed_paths path",
        )
        self.assertFalse((self.repo / "src").exists())

    def test_missing_tracked_output_is_an_error(self) -> None:
        subprocess.run(["git", "add", "input.md"], cwd=self.repo, check=True)
        (self.repo / "input.md").unlink()
        self.assert_single_error(
            self.lint_paths(context=[], allowed=["input.md"]), "missing allowed_paths path"
        )

    def test_missing_git_ignored_output_is_allowed_without_creation(self) -> None:
        for output in [
            "reports/gnss/",
            r"reports\capture.json",
            "./reports/board_validation/CALL-020-20260902-001/",
            "firmware/mqtt_heartbeat/build_*",
            "firmware/mqtt_heartbeat/sdkconfig.*.local",
        ]:
            with self.subTest(output=output):
                self.assertEqual(self.lint_paths(context=["input.md"], allowed=[output]), [])
                self.assertFalse((self.repo / "reports").exists())
                self.assertFalse((self.repo / "firmware").exists())

    def test_force_tracked_ignored_file_cannot_be_silently_missing(self) -> None:
        path = self.repo / "reports/required.json"
        path.parent.mkdir()
        path.write_text("{}", encoding="utf-8")
        subprocess.run(["git", "add", "-f", "reports/required.json"], cwd=self.repo, check=True)
        path.unlink()
        self.assert_single_error(
            self.lint_paths(context=[], allowed=["reports/required.json"]),
            "missing allowed_paths path",
        )

    def test_git_ignore_negation_does_not_allow_missing_output(self) -> None:
        self.assert_single_error(
            self.lint_paths(context=[], allowed=["exports/required.json"]),
            "missing allowed_paths path",
        )

    def test_escaping_paths_rejected_before_ignore_check(self) -> None:
        for key in ["context", "allowed"]:
            for unsafe in [
                "../outside.log",
                "reports/../../outside.log",
                r"..\outside.log",
                "/outside.log",
                "C:/outside.log",
                "C:outside.log",
                r"\\server\share\outside.log",
            ]:
                with self.subTest(key=key, unsafe=unsafe):
                    paths: dict[str, list[str]] = {"context": [], "allowed": []}
                    paths[key] = [unsafe]
                    self.assert_single_error(self.lint_paths(**paths), "invalid ")

    def test_existing_context_glob_and_missing_context_glob(self) -> None:
        self.assertEqual(self.lint_paths(context=["*.md"], allowed=[]), [])
        self.assert_single_error(
            self.lint_paths(context=["firmware/**/build_*"], allowed=[]), "missing context path"
        )


if __name__ == "__main__":
    unittest.main()

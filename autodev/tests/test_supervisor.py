from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "autodev.py"
SPEC = importlib.util.spec_from_file_location("egolink_autodev", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
AUTODEV = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = AUTODEV
SPEC.loader.exec_module(AUTODEV)


class PathBoundaryTests(unittest.TestCase):
    def test_normalize_windows_path(self) -> None:
        self.assertEqual(AUTODEV.normalize_relpath(r"docs\file.md"), "docs/file.md")

    def test_allowed_exact_path(self) -> None:
        task = {"allowed_paths": ["docs/file.md"], "forbidden_paths": []}
        self.assertEqual(AUTODEV.validate_changed_paths(task, ["docs/file.md"]), [])

    def test_outside_allowed_path_is_rejected(self) -> None:
        task = {"allowed_paths": ["docs/**"], "forbidden_paths": ["docs/private/**"]}
        violations = AUTODEV.validate_changed_paths(task, ["firmware/main.c"])
        self.assertTrue(any("outside allowed_paths" in item for item in violations))

    def test_forbidden_path_is_rejected(self) -> None:
        task = {"allowed_paths": ["docs/**"], "forbidden_paths": ["docs/private/**"]}
        violations = AUTODEV.validate_changed_paths(task, ["docs/private/secret.md"])
        self.assertTrue(any("matches forbidden_paths" in item for item in violations))


class BacklogSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.backlog = {
            "tasks": [
                {"id": "A", "depends_on": []},
                {"id": "B", "depends_on": ["A"]},
                {"id": "C", "depends_on": ["B"], "human_gate": True},
            ]
        }

    def test_first_task_is_ready(self) -> None:
        task = AUTODEV.select_next_task(self.backlog, AUTODEV.default_state())
        self.assertEqual(task["id"], "A")

    def test_dependency_unlocks_next_task(self) -> None:
        state = AUTODEV.default_state()
        state["completed"] = ["A"]
        task = AUTODEV.select_next_task(self.backlog, state)
        self.assertEqual(task["id"], "B")

    def test_human_gate_is_detected(self) -> None:
        state = AUTODEV.default_state()
        state["completed"] = ["A", "B"]
        task = AUTODEV.pending_human_gate(self.backlog, state)
        self.assertEqual(task["id"], "C")


class ResultSchemaTests(unittest.TestCase):
    def test_packaged_backlog_and_schema_are_valid_json(self) -> None:
        root = Path(__file__).resolve().parents[2]
        backlog = json.loads((root / "autodev" / "backlog.json").read_text(encoding="utf-8"))
        schema = json.loads((root / "autodev" / "result.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(len(backlog["tasks"]), 3)
        self.assertEqual(schema["type"], "object")


if __name__ == "__main__":
    unittest.main(verbosity=2)

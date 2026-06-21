from __future__ import annotations

import importlib.util
import datetime as dt
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


class MonitoringTests(unittest.TestCase):
    def test_duration_format(self) -> None:
        self.assertEqual(AUTODEV.format_duration(65), "01:05")
        self.assertEqual(AUTODEV.format_duration(3661), "01:01:01")

    def test_git_warning_lines_are_filtered_from_monitor_output(self) -> None:
        output = "\n".join(
            [
                "warning: in the working copy of 'scripts/run_autodev.ps1', LF will be replaced by CRLF the next time Git touches it",
                "scripts/autodev.py",
                "docs/AUTODEV_GUIDE.md",
            ]
        )
        self.assertEqual(
            AUTODEV.clean_git_output(output).splitlines(),
            ["scripts/autodev.py", "docs/AUTODEV_GUIDE.md"],
        )

    def test_seconds_since_iso_timestamp_handles_utc_values(self) -> None:
        old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=5)).isoformat()
        age = AUTODEV.seconds_since_iso_timestamp(old)
        self.assertIsNotNone(age)
        self.assertGreaterEqual(age, 0)

    def test_mcp_tool_event_includes_available_operation(self) -> None:
        event = {
            "type": "item.started",
            "item": {
                "type": "mcp_tool_call",
                "server": "sandbox",
                "name": "read_file",
                "arguments": {"path": "README.md"},
            },
        }
        formatted = AUTODEV.format_codex_event(event)
        self.assertIsNotNone(formatted)
        tag, message = formatted
        self.assertEqual(tag, "TOOL")
        self.assertIn("sandbox/read_file", message)
        self.assertIn("README.md", message)

    def test_reasoning_event_does_not_render_reasoning_text(self) -> None:
        event = {
            "type": "item.completed",
            "item": {"type": "reasoning", "text": "private details"},
        }
        formatted = AUTODEV.format_codex_event(event)
        self.assertEqual(formatted, ("THINK", "Analysis step completed"))

    def test_read_local_session_summary_from_explicit_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary_path = Path(tmp) / "session_summary.json"
            summary_path.write_text(
                json.dumps(
                    {
                        "event_count": 2,
                        "counts": {"safety_evaluation": 1},
                        "safety": {"latest_risk_type": "manual_sos"},
                    }
                ),
                encoding="utf-8",
            )

            summary = AUTODEV.read_local_session_summary(
                summary_path=summary_path,
                allow_event_log_fallback=False,
            )

        self.assertIsNotNone(summary)
        assert summary is not None
        self.assertEqual(summary["source"], "session_summary")
        self.assertEqual(summary["event_count"], 2)
        self.assertEqual(summary["safety"]["latest_risk_type"], "manual_sos")

    def test_build_local_session_summary_from_event_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            event_log = Path(tmp) / "events.jsonl"
            event_log.write_text(
                "\n".join(
                    [
                        json.dumps({"event_type": "sensor_sample", "seq": 1}),
                        json.dumps(
                            {
                                "event_type": "safety_evaluation",
                                "seq": 2,
                                "risk_type": "none",
                                "recommended_action": "ignore",
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            summary = AUTODEV.build_local_session_summary_from_events(event_log, limit=10)

        self.assertIsNotNone(summary)
        assert summary is not None
        self.assertEqual(summary["source"], "event_log_fallback")
        self.assertEqual(summary["counts"]["sensor_sample"], 1)
        self.assertEqual(summary["safety"]["evaluations"], 1)
        self.assertEqual(summary["safety"]["latest_action"], "ignore")


if __name__ == "__main__":
    unittest.main(verbosity=2)

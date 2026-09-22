import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "build_progress_board.py"

spec = importlib.util.spec_from_file_location("build_progress_board", MODULE_PATH)
board_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(board_mod)


def make_repo(root: Path) -> None:
    (root / "docs" / "tasks" / "active").mkdir(parents=True)
    (root / "docs" / "tasks" / "done").mkdir(parents=True)
    (root / "docs" / "current" / "key_releases").mkdir(parents=True)
    (root / "docs" / "tasks" / "active" / "AAA-001_X.md").write_text(
        "---\nid: AAA-001\ntitle: Active thing\nstatus: active\n"
        "execution_state: in_progress\nowner: codex\npriority: high\ncreated: 2026-07-01\n---\n# Body\n",
        encoding="utf-8",
    )
    (root / "docs" / "tasks" / "active" / "BBB-001_Y.md").write_text(
        "---\nid: BBB-001\ntitle: Paused thing\nstatus: paused\n"
        "created: 2026-07-01\n---\n# Body\n",
        encoding="utf-8",
    )
    (root / "docs" / "tasks" / "done" / "CCC-001_Z.md").write_text(
        "---\ntask_id: CCC-001\ntitle: Done thing\nstatus: superseded\n"
        "last_verified: 2026-07-02\n---\n# Body\n",
        encoding="utf-8",
    )
    (root / "docs" / "current" / "key_releases" / "KR-001_TEST.json").write_text(
        json.dumps({"id": "KR-001", "status": "released", "title": "First"}),
        encoding="utf-8",
    )
    (root / "docs" / "current" / "progress_board_config.json").write_text(
        json.dumps({
            "current_focus": "test focus",
            "milestones": [
                {"id": "M1", "title": "one", "tasks": [
                    "AAA-001", "CCC-001", {"id": "DDD-001", "label": "planned thing"},
                ]},
            ],
            "assignees": {"AAA-001": "codex"},
            "operator_asks": ["do a thing"],
        }, ensure_ascii=False),
        encoding="utf-8",
    )


class ProgressBoardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        make_repo(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_frontmatter_parsing_handles_both_id_keys(self):
        packets = board_mod.scan_packets(self.root / "docs" / "tasks")
        self.assertEqual(packets["AAA-001"]["state"], "in_progress")
        self.assertEqual(packets["BBB-001"]["state"], "paused")
        self.assertEqual(packets["CCC-001"]["state"], "done")
        self.assertEqual(packets["CCC-001"]["packet_status"], "superseded")

    def test_milestone_progress_counts_done_and_planned(self):
        board = board_mod.build_board(self.root)
        ms = board["milestones"][0]
        self.assertEqual(ms["done"], 1)
        self.assertEqual(ms["total"], 3)
        states = {t["id"]: t["state"] for t in ms["tasks"]}
        self.assertEqual(states["AAA-001"], "in_progress")
        self.assertEqual(states["CCC-001"], "done")
        self.assertEqual(states["DDD-001"], "planned")

    def test_task_paths_are_stable_repo_relative_posix_paths(self):
        board = board_mod.build_board(self.root)
        active_by_id = {task["id"]: task for task in board["active_tasks"]}

        self.assertEqual(
            active_by_id["AAA-001"]["path"],
            "docs/tasks/active/AAA-001_X.md",
        )
        self.assertEqual(
            active_by_id["BBB-001"]["path"],
            "docs/tasks/active/BBB-001_Y.md",
        )
        self.assertEqual(
            board["recent_done"][0]["path"],
            "docs/tasks/done/CCC-001_Z.md",
        )
        serialized = json.dumps(board)
        self.assertNotIn(self.root.name, serialized)

    def test_markdown_render_contains_key_sections(self):
        board = board_mod.build_board(self.root)
        md = board_mod.render_markdown(board)
        self.assertEqual(board["counts"]["active"], 1)
        self.assertEqual(board["counts"]["paused"], 1)
        self.assertEqual(board["counts"]["open_total"], 2)
        for expected in ("里程碑", "开放任务（只有实施中计入 WIP）", "最近完成",
                         "等待创始人处理", "KR-001", "do a thing",
                         "planned thing"):
            self.assertIn(expected, md)

    def test_open_inventory_does_not_inflate_implementation_wip(self):
        entries = {
            "QUEUED": ("active", "queued", "planned"),
            "REVIEW": ("active", "acceptance_review", "acceptance_review"),
            "PARKED": ("active", "parked", "parked"),
            "REGRESSION": ("continuous_regression", "continuous_regression", "continuous_regression"),
            "LEGACY": ("active", "", "planned"),
            "BLOCKED": ("blocked", "in_progress", "paused"),
        }
        for task_id, (status, execution, _) in entries.items():
            (self.root / "docs/tasks/active" / f"{task_id}.md").write_text(
                f"---\nid: {task_id}\nstatus: {status}\nexecution_state: {execution}\n---\n",
                encoding="utf-8",
            )
        board = board_mod.build_board(self.root)
        by_id = {p["id"]: p for p in board["active_tasks"]}
        for task_id, (_, _, expected) in entries.items():
            self.assertEqual(by_id[task_id]["state"], expected)
        self.assertEqual(board["counts"]["active"], 1)
        self.assertEqual(board["counts"]["open_total"], 8)
        self.assertEqual(board["counts"]["acceptance_review"], 1)
        self.assertEqual(board["counts"]["continuous_regression"], 1)
        self.assertEqual(board["counts"]["planned"], 2)
        self.assertEqual(by_id["AAA-001"]["owner"], "codex")
        self.assertIn("待验收: 1", board_mod.render_markdown(board))

    def test_key_release_scan_is_defensive(self):
        (self.root / "docs" / "current" / "key_releases" / "broken.json").write_text(
            "{not json", encoding="utf-8"
        )
        releases = board_mod.scan_key_releases(
            self.root / "docs" / "current" / "key_releases"
        )
        self.assertEqual(len(releases), 1)
        self.assertEqual(releases[0]["id"], "KR-001")

    def test_server_summary_distinguishes_wip_from_open_inventory(self):
        from server.message_hub import load_progress_board

        path = self.root / "board.json"
        value = {"active_tasks": [{}, {}, {}], "counts": {"active": 1}}
        path.write_text(json.dumps(value), encoding="utf-8")
        summary = load_progress_board(path)["summary"]
        self.assertEqual(summary["active_count"], 1)
        self.assertEqual(summary["open_count"], 3)
        for invalid in (None, True, -1, "1"):
            value["counts"]["active"] = invalid
            path.write_text(json.dumps(value), encoding="utf-8")
            self.assertEqual(load_progress_board(path)["summary"]["active_count"], 3)


if __name__ == "__main__":
    unittest.main()

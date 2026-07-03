"""Build the one-page EgoLink project progress board.

Scans task packets under docs/tasks/active and docs/tasks/done, merges them
with the director-maintained milestone map in
docs/current/progress_board_config.json and the key-release manifests under
docs/current/key_releases/, then writes docs/generated/PROGRESS_BOARD.md and
docs/generated/progress_board.json.

The generated board is a read surface for the founder; it never edits task
packets or STATUS.md. Regenerate it at every packet open/close/fix per
docs/development/DIRECTOR_WORKFLOW.md.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

STATE_GLYPH = {
    "done": "✅",          # check mark
    "in_progress": "⏳",   # hourglass
    "paused": "⏸",        # pause
    "planned": "\U0001f4cb",   # clipboard
}


def parse_frontmatter(text: str) -> dict:
    """Parse top-level scalar keys from a leading YAML frontmatter block."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fields: dict = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if not line or line.startswith((" ", "\t", "-", "#")):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        value = value.strip().strip('"').strip("'")
        if value:
            fields[key.strip()] = value
    return fields


def scan_packets(tasks_dir: Path) -> dict:
    """Return {task_id: packet_info} for active/ and done/ packets."""
    packets: dict = {}
    for state_dir, default_state in (("active", "in_progress"), ("done", "done")):
        folder = tasks_dir / state_dir
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.md")):
            fields = parse_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
            task_id = fields.get("id") or fields.get("task_id")
            if not task_id:
                continue
            status = (fields.get("status") or "").lower()
            if state_dir == "done":
                state = "done"
            elif status in ("paused", "blocked"):
                state = "paused"
            else:
                state = default_state
            packets[task_id] = {
                "id": task_id,
                "title": fields.get("title", path.stem),
                "state": state,
                "packet_status": status or default_state,
                "priority": fields.get("priority", ""),
                "date": fields.get("completed")
                or fields.get("last_updated")
                or fields.get("last_verified")
                or fields.get("created")
                or "",
                "path": path.as_posix(),
            }
    return packets


def scan_key_releases(kr_dir: Path) -> list:
    releases = []
    if not kr_dir.is_dir():
        return releases
    for path in sorted(kr_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        kr_id = (
            data.get("id")
            or data.get("key_release_id")
            or data.get("kr_id")
            or path.stem.split("_")[0]
        )
        status = data.get("status") or data.get("release_status") or "unknown"
        title = data.get("title") or data.get("name") or ""
        releases.append({"id": str(kr_id), "status": str(status), "title": str(title)})
    return releases


def git_summary(repo_root: Path) -> dict:
    def run(args):
        try:
            out = subprocess.run(
                ["git", *args], cwd=repo_root, capture_output=True,
                text=True, timeout=10, check=False,
            )
            return out.stdout.strip()
        except OSError:
            return ""

    return {
        "branch": run(["rev-parse", "--abbrev-ref", "HEAD"]),
        "head": run(["log", "-1", "--format=%h %s"]),
    }


def resolve_milestones(config: dict, packets: dict) -> list:
    milestones = []
    for entry in config.get("milestones", []):
        tasks = []
        done_count = 0
        for item in entry.get("tasks", []):
            task_id = item["id"] if isinstance(item, dict) else item
            label = item.get("label", task_id) if isinstance(item, dict) else task_id
            packet = packets.get(task_id)
            state = packet["state"] if packet else "planned"
            if state == "done":
                done_count += 1
            tasks.append({"id": task_id, "label": label, "state": state})
        milestones.append({
            "id": entry.get("id", ""),
            "title": entry.get("title", ""),
            "done": done_count,
            "total": len(tasks),
            "tasks": tasks,
        })
    return milestones


def build_board(repo_root: Path) -> dict:
    config_path = repo_root / "docs" / "current" / "progress_board_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    packets = scan_packets(repo_root / "docs" / "tasks")
    active = sorted(
        (p for p in packets.values() if p["state"] in ("in_progress", "paused")),
        key=lambda p: p["id"],
    )
    recent_done = sorted(
        (p for p in packets.values() if p["state"] == "done"),
        key=lambda p: p["date"],
        reverse=True,
    )[: config.get("recent_done_limit", 8)]
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "git": git_summary(repo_root),
        "current_focus": config.get("current_focus", ""),
        "milestones": resolve_milestones(config, packets),
        "active_tasks": active,
        "recent_done": recent_done,
        "operator_asks": config.get("operator_asks", []),
        "assignees": config.get("assignees", {}),
        "key_releases": scan_key_releases(
            repo_root / "docs" / "current" / "key_releases"
        ),
        "counts": {
            "active": len(active),
            "done_total": sum(1 for p in packets.values() if p["state"] == "done"),
        },
    }


def render_markdown(board: dict) -> str:
    lines = [
        "# EgoLink 项目进度看板",
        "",
        f"- 生成时间: {board['generated_at']}",
        f"- 分支: `{board['git'].get('branch', '')}` @ {board['git'].get('head', '')}",
        f"- 当前焦点: {board['current_focus']}",
        f"- 已完成任务总数: {board['counts']['done_total']}"
        f"，进行中: {board['counts']['active']}",
        "",
        "## 里程碑",
        "",
        "| 里程碑 | 进度 | 任务 |",
        "|---|---|---|",
    ]
    for ms in board["milestones"]:
        items = " ".join(
            f"{STATE_GLYPH[t['state']]}{t['label']}" for t in ms["tasks"]
        )
        lines.append(f"| {ms['id']} {ms['title']} | {ms['done']}/{ms['total']} | {items} |")
    lines += [
        "",
        "图例: ✅完成 ⏳进行中 ⏸暂停 \U0001f4cb计划中",
        "",
        "## 进行中的任务",
        "",
        "| 任务 | 标题 | 状态 | 优先级 | 执行者 |",
        "|---|---|---|---|---|",
    ]
    assignees = board["assignees"]
    for task in board["active_tasks"]:
        lines.append(
            f"| {task['id']} | {task['title']} | {task['packet_status']} "
            f"| {task['priority']} | {assignees.get(task['id'], '-')} |"
        )
    lines += ["", "## 最近完成", "", "| 任务 | 标题 | 日期 |", "|---|---|---|"]
    for task in board["recent_done"]:
        lines.append(f"| {task['id']} | {task['title']} | {task['date']} |")
    lines += ["", "## 等待创始人处理", ""]
    for ask in board["operator_asks"]:
        lines.append(f"- [ ] {ask}")
    lines += ["", "## 关键版本 (KR)", "", "| KR | 状态 | 标题 |", "|---|---|---|"]
    for kr in board["key_releases"]:
        lines.append(f"| {kr['id']} | {kr['status']} | {kr['title']} |")
    lines += [
        "",
        "---",
        "",
        "本文件由 `python scripts/build_progress_board.py` 生成，请勿手工编辑。",
        "数据来源: docs/tasks/ 任务包 frontmatter、docs/current/progress_board_config.json、",
        "docs/current/key_releases/。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="repository root")
    parser.add_argument(
        "--out-dir", default=None,
        help="output directory (default: <repo-root>/docs/generated)",
    )
    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()
    out_dir = Path(args.out_dir) if args.out_dir else repo_root / "docs" / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)

    board = build_board(repo_root)
    (out_dir / "progress_board.json").write_text(
        json.dumps(board, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "PROGRESS_BOARD.md").write_text(render_markdown(board), encoding="utf-8")
    print(
        "progress board written: "
        f"{(out_dir / 'PROGRESS_BOARD.md').as_posix()} "
        f"(active={board['counts']['active']}, done={board['counts']['done_total']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

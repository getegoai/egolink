#!/usr/bin/env python3
"""Local diagnostic CLI for the Ego Link P0 repository."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any


REQUIRED_TOP_LEVEL_DIRECTORIES = (
    "firmware",
    "pc_simulator",
    "quality_tests",
    "docs",
    "scripts",
)
REQUIRED_COMMANDS = ("python", "git", "codex")


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    ok: bool
    detail: str


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_doctor(Path(args.root))
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(render_human_report(report))
    return 0 if report["ok"] else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default=".",
        help="Repository root to inspect. Defaults to the current directory.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the diagnostic report as JSON.",
    )
    return parser


def run_doctor(root: Path) -> dict[str, Any]:
    resolved_root = root.expanduser().resolve()
    checks = collect_checks(resolved_root)
    failed = [check for check in checks if not check.ok]
    return {
        "ok": not failed,
        "root": str(resolved_root),
        "checks": [asdict(check) for check in checks],
        "summary": {
            "total": len(checks),
            "passed": len(checks) - len(failed),
            "failed": len(failed),
        },
    }


def collect_checks(root: Path) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    checks.extend(check_required_directories(root))
    checks.append(check_readme(root))
    checks.append(check_git_work_tree(root))
    checks.extend(check_required_commands())
    return checks


def check_required_directories(root: Path) -> list[DoctorCheck]:
    return [
        DoctorCheck(
            name=f"directory:{directory_name}",
            ok=(root / directory_name).is_dir(),
            detail=(
                f"Found required directory: {directory_name}"
                if (root / directory_name).is_dir()
                else f"Missing required directory: {directory_name}"
            ),
        )
        for directory_name in REQUIRED_TOP_LEVEL_DIRECTORIES
    ]


def check_readme(root: Path) -> DoctorCheck:
    readme = root / "README.md"
    return DoctorCheck(
        name="file:README.md",
        ok=readme.is_file(),
        detail="Found README.md" if readme.is_file() else "Missing README.md",
    )


def check_git_work_tree(root: Path) -> DoctorCheck:
    git = shutil.which("git")
    if not git:
        return DoctorCheck(
            name="git_work_tree",
            ok=False,
            detail="Cannot check Git work tree because git is not available.",
        )
    completed = subprocess.run(
        [git, "-C", str(root), "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        check=False,
    )
    inside = completed.returncode == 0 and completed.stdout.strip().lower() == "true"
    detail = "Root is inside a Git work tree." if inside else "Root is not inside a Git work tree."
    if completed.stderr.strip() and not inside:
        detail = f"{detail} {completed.stderr.strip()}"
    return DoctorCheck(name="git_work_tree", ok=inside, detail=detail)


def check_required_commands() -> list[DoctorCheck]:
    return [check_command(command) for command in REQUIRED_COMMANDS]


def check_command(command: str) -> DoctorCheck:
    path = shutil.which(command)
    return DoctorCheck(
        name=f"command:{command}",
        ok=path is not None,
        detail=f"Found {command}: {path}" if path else f"Missing command on PATH: {command}",
    )


def render_human_report(report: dict[str, Any]) -> str:
    lines = [
        "Ego Link Project Doctor",
        f"Root: {report['root']}",
        f"Status: {'OK' if report['ok'] else 'FAIL'}",
        "",
        "Checks:",
    ]
    for check in report["checks"]:
        status = "PASS" if check["ok"] else "FAIL"
        lines.append(f"- {status} {check['name']}: {check['detail']}")
    summary = report["summary"]
    lines.extend(
        [
            "",
            f"Summary: {summary['passed']}/{summary['total']} passed, {summary['failed']} failed.",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())

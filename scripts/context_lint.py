from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]

SKIP_PARTS_FOR_LINKS = {
    ".git",
    "__pycache__",
    "docs/archive",
    "model_artifacts",
    "reports",
}

SKIP_DIR_NAMES = {
    ".git",
    "__pycache__",
    "build",
    "runtime",
    "runs",
}

LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def repo_path(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def should_skip_dir(path: Path) -> bool:
    rel = repo_path(path) if path != ROOT else ""
    if path.name in SKIP_DIR_NAMES:
        return True
    return any(rel == part or rel.startswith(part + "/") for part in SKIP_PARTS_FOR_LINKS)


def iter_files(patterns: tuple[str, ...]) -> list[Path]:
    files: list[Path] = []
    stack = [ROOT]
    while stack:
        current = stack.pop()
        for child in current.iterdir():
            if child.is_dir():
                if not should_skip_dir(child):
                    stack.append(child)
                continue
            if any(child.match(pattern) for pattern in patterns):
                files.append(child)
    return sorted(files)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def frontmatter(text: str) -> dict[str, str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip().strip("'\"")
    return fields


def normalize_link(raw_link: str) -> str | None:
    link = raw_link.strip()
    if not link or link.startswith("#"):
        return None
    if link.startswith("<") and link.endswith(">"):
        link = link[1:-1].strip()
    parsed = urlparse(link)
    if parsed.scheme in {"http", "https", "mailto", "tel"}:
        return None
    path = parsed.path
    if not path:
        return None
    return unquote(path)


def link_target_exists(source: Path, link: str) -> bool:
    link_path = normalize_link(link)
    if link_path is None:
        return True
    if link_path.startswith("/"):
        target = ROOT / link_path.lstrip("/")
    else:
        target = source.parent / link_path
    return target.exists()


def check_markdown_links(errors: list[str]) -> None:
    for path in iter_files(("*.md",)):
        text = read_text(path)
        for link in LINK_RE.findall(text):
            if not link_target_exists(path, link):
                errors.append(f"missing markdown link target: {repo_path(path)} -> {link}")


def strip_scalar(value: str) -> str:
    return value.strip().strip("'\"").rstrip(",")


def parse_simple_lists(text: str) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {"context": [], "allowed_paths": []}
    current: str | None = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        key_match = re.match(r"^(context|allowed_paths)\s*:\s*(.*)$", stripped)
        if key_match:
            current = key_match.group(1)
            value = key_match.group(2).strip()
            if value.startswith("[") and value.endswith("]"):
                items = [strip_scalar(item) for item in value[1:-1].split(",")]
                result[current].extend(item for item in items if item)
            elif value:
                result[current].append(strip_scalar(value))
            continue

        if current and stripped.startswith("- "):
            value = strip_scalar(stripped[2:])
            if value:
                result[current].append(value)
            continue

        if not raw_line.startswith((" ", "\t")):
            current = None

    return result


def load_task_paths(path: Path) -> dict[str, list[str]]:
    if path.suffix == ".json":
        payload = json.loads(read_text(path))
        return {
            "context": list(payload.get("context", [])),
            "allowed_paths": list(payload.get("allowed_paths", [])),
        }
    text = read_text(path)
    match = FRONTMATTER_RE.match(text)
    parse_text = match.group(1) if match else text
    return parse_simple_lists(parse_text)


def path_or_glob_exists(value: str) -> bool:
    cleaned = value.split("#", 1)[0].strip().strip("'\"")
    if not cleaned:
        return True
    if any(char in cleaned for char in "*?["):
        return any(ROOT.glob(cleaned))
    return (ROOT / cleaned).exists()


def check_active_tasks(errors: list[str]) -> None:
    task_dir = ROOT / "docs" / "tasks" / "active"
    if not task_dir.exists():
        errors.append("missing active task directory: docs/tasks/active")
        return

    for task in sorted(task_dir.glob("*")):
        if task.suffix.lower() not in {".md", ".json", ".yml", ".yaml"}:
            continue
        try:
            paths = load_task_paths(task)
        except Exception as exc:  # noqa: BLE001 - lint should report malformed task files.
            errors.append(f"could not parse active task packet: {repo_path(task)}: {exc}")
            continue
        for key in ("context", "allowed_paths"):
            for value in paths.get(key, []):
                if not path_or_glob_exists(value):
                    errors.append(f"missing {key} path in {repo_path(task)}: {value}")


def check_authoritative_metadata(errors: list[str]) -> None:
    for path in iter_files(("*.md",)):
        fields = frontmatter(read_text(path))
        if fields.get("document_status") == "authoritative" and not fields.get("last_verified"):
            errors.append(f"authoritative document missing last_verified: {repo_path(path)}")


def check_archive_authority(errors: list[str]) -> None:
    archive_dir = ROOT / "docs" / "archive"
    if not archive_dir.exists():
        return
    for path in sorted(archive_dir.rglob("*.md")):
        fields = frontmatter(read_text(path))
        if fields.get("document_status") == "authoritative":
            errors.append(f"archive document must not be authoritative: {repo_path(path)}")


def main() -> int:
    errors: list[str] = []
    check_markdown_links(errors)
    check_active_tasks(errors)
    check_authoritative_metadata(errors)
    check_archive_authority(errors)

    if errors:
        print("context_lint: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1

    print("context_lint: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())

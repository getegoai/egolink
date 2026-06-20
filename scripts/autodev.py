#!/usr/bin/env python3
"""Small, visible Codex supervisor for sequential Ego Link development tasks.

The supervisor intentionally uses only the Python standard library.  It binds
Codex to the repository that contains this script, streams JSONL execution
progress, independently verifies each task, commits successful work, and stops
on the first unresolved failure or human gate.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import fnmatch
import json
import os
import queue
import shlex
import shutil
import signal
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path
from typing import Any, Iterable, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
AUTODEV_DIR = REPO_ROOT / "autodev"
BACKLOG_PATH = AUTODEV_DIR / "backlog.json"
RESULT_SCHEMA_PATH = AUTODEV_DIR / "result.schema.json"
RUNTIME_DIR = AUTODEV_DIR / "runtime"
RUNS_DIR = AUTODEV_DIR / "runs"
STATE_PATH = RUNTIME_DIR / "state.json"
REQUIRED_DIRS = ("docs", "firmware", "pc_simulator", "quality_tests", "scripts")
REQUIRED_FILES = ("README.md", "AGENTS.md", "autodev/backlog.json", "autodev/result.schema.json")
DEFAULT_BRANCH = "autodev/egolink-p0"
DEFAULT_TASK_TIMEOUT_SECONDS = 90 * 60
HEARTBEAT_SECONDS = 30


class AutoDevError(RuntimeError):
    """Expected supervisor error with a concise user-facing message."""


class Console:
    COLORS = {
        "reset": "\033[0m",
        "bold": "\033[1m",
        "dim": "\033[2m",
        "blue": "\033[34m",
        "green": "\033[32m",
        "yellow": "\033[33m",
        "red": "\033[31m",
        "cyan": "\033[36m",
        "magenta": "\033[35m",
    }

    def __init__(self) -> None:
        self.use_color = bool(sys.stdout.isatty() and not os.environ.get("NO_COLOR"))

    def _paint(self, text: str, *styles: str) -> str:
        if not self.use_color:
            return text
        prefix = "".join(self.COLORS[s] for s in styles)
        return f"{prefix}{text}{self.COLORS['reset']}"

    @staticmethod
    def timestamp() -> str:
        return dt.datetime.now().strftime("%H:%M:%S")

    def line(self, tag: str, message: str, color: str = "blue") -> None:
        tag_text = self._paint(f"[{tag:<7}]", "bold", color)
        print(f"{self._paint(self.timestamp(), 'dim')} {tag_text} {message}", flush=True)

    def header(self, title: str) -> None:
        rule = "=" * 78
        print(f"\n{self._paint(rule, 'cyan')}\n{self._paint(title, 'bold', 'cyan')}\n{self._paint(rule, 'cyan')}", flush=True)

    def info(self, message: str) -> None:
        self.line("INFO", message, "blue")

    def task(self, message: str) -> None:
        self.line("TASK", message, "magenta")

    def success(self, message: str) -> None:
        self.line("OK", message, "green")

    def warning(self, message: str) -> None:
        self.line("WARN", message, "yellow")

    def error(self, message: str) -> None:
        self.line("ERROR", message, "red")


CONSOLE = Console()


@dataclasses.dataclass
class ProcessResult:
    returncode: int
    output: str
    timed_out: bool = False


@dataclasses.dataclass
class CodexRunResult:
    returncode: int
    structured_result: dict[str, Any] | None
    run_dir: Path
    timed_out: bool
    thread_id: str | None


@dataclasses.dataclass
class VerificationResult:
    ok: bool
    output: str
    failed_command: list[str] | None = None


def iso_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def normalize_relpath(path: str | Path) -> str:
    return str(path).replace("\\", "/").lstrip("./")


def display_command(command: Sequence[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(list(command))
    return shlex.join(command)


def prepare_command(command: Sequence[str]) -> list[str]:
    """Make Windows .cmd/.bat launchers executable without enabling a shell globally."""
    prepared = list(command)
    if os.name == "nt" and prepared:
        suffix = Path(prepared[0]).suffix.lower()
        if suffix in {".cmd", ".bat"}:
            comspec = os.environ.get("COMSPEC", "cmd.exe")
            return [comspec, "/d", "/c", *prepared]
    return prepared


def run_capture(
    command: Sequence[str],
    *,
    cwd: Path = REPO_ROOT,
    check: bool = False,
    timeout: int = 60,
) -> ProcessResult:
    try:
        completed = subprocess.run(
            prepare_command(command),
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        result = ProcessResult(127, str(exc))
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        result = ProcessResult(124, str(output), timed_out=True)
    else:
        result = ProcessResult(completed.returncode, completed.stdout or "")

    if check and result.returncode != 0:
        raise AutoDevError(
            f"Command failed ({result.returncode}): {display_command(command)}\n{result.output.strip()}"
        )
    return result


def git(*args: str, check: bool = True, timeout: int = 60) -> ProcessResult:
    return run_capture(("git", *args), check=check, timeout=timeout)


def actual_git_root() -> Path:
    result = git("rev-parse", "--show-toplevel", check=True)
    raw = result.output.strip()
    if not raw:
        raise AutoDevError("Git did not return a repository root.")
    return Path(raw).resolve()


def ensure_correct_workspace() -> None:
    actual = actual_git_root()
    expected = REPO_ROOT.resolve()
    if actual != expected:
        raise AutoDevError(
            "Workspace mismatch detected.\n"
            f"Expected repository: {expected}\n"
            f"Git repository:      {actual}\n"
            "Open the EGOLINK folder as the VS Code workspace and run the script again."
        )


def worktree_status() -> str:
    return git("status", "--porcelain=v1", "--untracked-files=all", check=True).output


def assert_clean_worktree() -> None:
    status = worktree_status().strip()
    if status:
        raise AutoDevError(
            "The Git working tree is not clean. Commit or stash the following changes before AutoDev runs:\n"
            + status
        )


def get_changed_paths() -> list[str]:
    tracked = git("diff", "--name-only", "HEAD", check=True).output.splitlines()
    untracked = git("ls-files", "--others", "--exclude-standard", check=True).output.splitlines()
    paths = {normalize_relpath(p.strip()) for p in (*tracked, *untracked) if p.strip()}
    return sorted(paths)


def path_matches(path: str, pattern: str) -> bool:
    path_n = normalize_relpath(path)
    pattern_n = normalize_relpath(pattern)
    return fnmatch.fnmatchcase(path_n, pattern_n)


def validate_changed_paths(task: dict[str, Any], changed_paths: Sequence[str]) -> list[str]:
    allowed = [normalize_relpath(p) for p in task.get("allowed_paths", [])]
    forbidden = [normalize_relpath(p) for p in task.get("forbidden_paths", [])]
    violations: list[str] = []

    for path in changed_paths:
        if not any(path_matches(path, pattern) for pattern in allowed):
            violations.append(f"outside allowed_paths: {path}")
        if any(path_matches(path, pattern) for pattern in forbidden):
            violations.append(f"matches forbidden_paths: {path}")
    return violations


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AutoDevError(f"Required file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise AutoDevError(f"Invalid JSON in {path}: {exc}") from exc


def load_backlog() -> dict[str, Any]:
    backlog = load_json(BACKLOG_PATH)
    if not isinstance(backlog, dict) or not isinstance(backlog.get("tasks"), list):
        raise AutoDevError("autodev/backlog.json must contain a top-level tasks array.")

    seen: set[str] = set()
    tasks_by_id: dict[str, dict[str, Any]] = {}
    for index, task in enumerate(backlog["tasks"]):
        if not isinstance(task, dict):
            raise AutoDevError(f"Backlog task #{index + 1} is not an object.")
        task_id = task.get("id")
        if not isinstance(task_id, str) or not task_id.strip():
            raise AutoDevError(f"Backlog task #{index + 1} has no valid id.")
        if task_id in seen:
            raise AutoDevError(f"Duplicate backlog task id: {task_id}")
        seen.add(task_id)
        tasks_by_id[task_id] = task
        if not task.get("allowed_paths"):
            raise AutoDevError(f"Task {task_id} has no allowed_paths.")
        if not task.get("verification"):
            raise AutoDevError(f"Task {task_id} has no verification commands.")

    for task in backlog["tasks"]:
        for dependency in task.get("depends_on", []):
            if dependency not in tasks_by_id:
                raise AutoDevError(f"Task {task['id']} depends on unknown task {dependency}.")

    # Detect dependency cycles with a small DFS.
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visited:
            return
        if task_id in visiting:
            raise AutoDevError(f"Dependency cycle detected at task {task_id}.")
        visiting.add(task_id)
        for dep in tasks_by_id[task_id].get("depends_on", []):
            visit(dep)
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in tasks_by_id:
        visit(task_id)
    return backlog


def default_state() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "completed": [],
        "blocked": {},
        "commits": {},
        "last_updated": None,
    }


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return default_state()
    state = load_json(STATE_PATH)
    if not isinstance(state, dict):
        raise AutoDevError(f"Invalid state file: {STATE_PATH}")
    base = default_state()
    base.update(state)
    return base


def save_state(state: dict[str, Any]) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    state["last_updated"] = iso_now()
    temp = STATE_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(STATE_PATH)


def select_next_task(backlog: dict[str, Any], state: dict[str, Any]) -> dict[str, Any] | None:
    completed = set(state.get("completed", []))
    blocked = set(state.get("blocked", {}).keys())
    for task in backlog["tasks"]:
        task_id = task["id"]
        if task_id in completed or task_id in blocked:
            continue
        dependencies = set(task.get("depends_on", []))
        if dependencies.issubset(completed):
            return task
    return None


def pending_human_gate(backlog: dict[str, Any], state: dict[str, Any]) -> dict[str, Any] | None:
    completed = set(state.get("completed", []))
    blocked = set(state.get("blocked", {}).keys())
    for task in backlog["tasks"]:
        if task["id"] in completed or task["id"] in blocked:
            continue
        if set(task.get("depends_on", [])).issubset(completed) and task.get("human_gate"):
            return task
    return None


def ensure_branch(branch: str) -> None:
    current = git("branch", "--show-current", check=True).output.strip()
    if not current:
        raise AutoDevError("AutoDev does not run from a detached HEAD.")
    if current == branch:
        CONSOLE.info(f"Using existing AutoDev branch: {branch}")
        return

    exists = git("show-ref", "--verify", "--quiet", f"refs/heads/{branch}", check=False).returncode == 0
    if exists:
        CONSOLE.info(f"Switching from {current} to existing branch {branch}")
        git("switch", branch, check=True)
    else:
        CONSOLE.info(f"Creating AutoDev branch {branch} from {current}")
        git("switch", "-c", branch, check=True)


def format_codex_event(event: dict[str, Any], verbose: bool = False) -> tuple[str, str] | None:
    event_type = str(event.get("type", ""))
    if event_type == "thread.started":
        return "CODEX", f"Thread started: {event.get('thread_id', 'unknown')}"
    if event_type == "turn.started":
        return "CODEX", "Turn started"
    if event_type == "turn.completed":
        usage = event.get("usage") or {}
        if isinstance(usage, dict) and usage:
            return (
                "CODEX",
                "Turn completed — input {input_tokens}, output {output_tokens}, reasoning {reasoning_output_tokens}".format(
                    input_tokens=usage.get("input_tokens", "?"),
                    output_tokens=usage.get("output_tokens", "?"),
                    reasoning_output_tokens=usage.get("reasoning_output_tokens", "?"),
                ),
            )
        return "CODEX", "Turn completed"
    if event_type in {"turn.failed", "error"}:
        detail = event.get("message") or event.get("error") or json.dumps(event, ensure_ascii=False)
        return "ERROR", str(detail)
    if event_type not in {"item.started", "item.completed", "item.updated"}:
        return ("EVENT", event_type) if verbose and event_type else None

    item = event.get("item") or {}
    if not isinstance(item, dict):
        return None
    item_type = str(item.get("type", "unknown"))
    phase = event_type.split(".")[-1]

    if item_type == "reasoning":
        # Operational visibility only; do not print private chain-of-thought text.
        return "THINK", "Analysis step started" if phase == "started" else "Analysis step completed"

    if item_type == "command_execution":
        command = item.get("command") or item.get("cmd") or "<command>"
        status = item.get("status") or phase
        exit_code = item.get("exit_code")
        if phase == "started":
            return "CMD", str(command)
        suffix = f"status={status}"
        if exit_code is not None:
            suffix += f", exit={exit_code}"
        output = item.get("aggregated_output") or item.get("output") or ""
        if output:
            compact = str(output).strip()
            if len(compact) > 1200:
                compact = compact[:1200] + " …"
            suffix += f"\n{compact}"
        return "CMD", f"{command} — {suffix}"

    if item_type in {"file_change", "file_changes"}:
        changes = item.get("changes") or item.get("files") or item.get("path") or "file changes"
        return "FILES", f"{phase}: {changes}"

    if item_type in {"plan", "plan_update"}:
        text = item.get("text") or item.get("plan") or item.get("content") or phase
        return "PLAN", str(text)

    if item_type == "agent_message":
        text = item.get("text") or item.get("message") or ""
        if text:
            return "AGENT", str(text)
        return None

    if item_type in {"mcp_tool_call", "web_search"}:
        name = item.get("name") or item.get("query") or item_type
        return "TOOL", f"{phase}: {name}"

    if verbose:
        return "ITEM", f"{phase}: {item_type}"
    return None


def terminate_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            process.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
        else:
            os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=8)
    except Exception:
        try:
            process.terminate()
            process.wait(timeout=5)
        except Exception:
            process.kill()


def stream_process(
    process: subprocess.Popen[str],
    *,
    raw_log_path: Path,
    timeout_seconds: int,
    event_mode: bool,
    verbose_events: bool = False,
) -> ProcessResult:
    line_queue: queue.Queue[str | None] = queue.Queue()
    started = time.monotonic()
    output_parts: list[str] = []
    timed_out = False

    def reader() -> None:
        assert process.stdout is not None
        try:
            for line in process.stdout:
                line_queue.put(line)
        finally:
            line_queue.put(None)

    thread = threading.Thread(target=reader, name="autodev-process-reader", daemon=True)
    thread.start()
    raw_log_path.parent.mkdir(parents=True, exist_ok=True)

    with raw_log_path.open("w", encoding="utf-8", newline="") as raw_log:
        reader_done = False
        last_heartbeat = started
        while not reader_done or process.poll() is None:
            elapsed = time.monotonic() - started
            if elapsed > timeout_seconds:
                timed_out = True
                CONSOLE.error(f"Process exceeded timeout of {timeout_seconds} seconds; terminating it.")
                terminate_process(process)
                break

            try:
                line = line_queue.get(timeout=0.5)
            except queue.Empty:
                line = ""

            if line is None:
                reader_done = True
            elif line:
                raw_log.write(line)
                raw_log.flush()
                output_parts.append(line)
                stripped = line.rstrip("\r\n")
                if event_mode:
                    try:
                        event = json.loads(stripped)
                    except json.JSONDecodeError:
                        CONSOLE.line("CODEX", stripped, "blue")
                    else:
                        formatted = format_codex_event(event, verbose=verbose_events)
                        if formatted:
                            tag, message = formatted
                            color = {
                                "ERROR": "red",
                                "CMD": "cyan",
                                "FILES": "green",
                                "PLAN": "magenta",
                                "AGENT": "blue",
                                "THINK": "yellow",
                            }.get(tag, "blue")
                            CONSOLE.line(tag, message, color)
                else:
                    CONSOLE.line("OUTPUT", stripped, "blue")

            now = time.monotonic()
            if now - last_heartbeat >= HEARTBEAT_SECONDS and process.poll() is None:
                minutes = int((now - started) // 60)
                seconds = int((now - started) % 60)
                CONSOLE.line("ACTIVE", f"Still running — elapsed {minutes:02d}:{seconds:02d}", "yellow")
                last_heartbeat = now

    if process.poll() is None:
        process.wait(timeout=10)
    thread.join(timeout=2)
    return ProcessResult(process.returncode or 0, "".join(output_parts), timed_out=timed_out)


def create_process(command: Sequence[str], *, stdin_pipe: bool = False) -> subprocess.Popen[str]:
    kwargs: dict[str, Any] = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(
        prepare_command(command),
        cwd=str(REPO_ROOT),
        stdin=subprocess.PIPE if stdin_pipe else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        **kwargs,
    )


def build_task_prompt(task: dict[str, Any], repair_context: str | None = None) -> str:
    task_json = json.dumps(task, ensure_ascii=False, indent=2)
    repair_section = ""
    if repair_context:
        trimmed = repair_context[-12000:]
        repair_section = f"""

## Repair context

The previous implementation did not pass external verification. Fix only the current task. The supervisor reported:

```text
{trimmed}
```
"""

    return textwrap.dedent(
        f"""
        You are the autonomous Builder for the Ego Link P0 repository.

        The supervisor has hard-bound the workspace to:
        {REPO_ROOT}

        Before editing, read:
        1. AGENTS.md
        2. README.md
        3. relevant existing files for this task
        4. docs/EGO_LINK_P0_CONTEXT.md if it exists

        Complete exactly one task: {task['id']} — {task['title']}.

        Non-negotiable rules:
        - Modify only files matching allowed_paths in the task object.
        - Do not modify autodev/, AGENTS.md, Git metadata, or unrelated files.
        - Do not run Git commit, push, checkout, switch, reset, clean, merge, or rebase.
        - Do not access the network or install dependencies.
        - Do not implement later backlog tasks.
        - Do not start persistent servers, monitors, watchers, or interactive processes.
        - Inspect existing code and preserve its conventions.
        - Run the task's verification commands when possible.
        - If the task cannot be completed within its boundaries, return status=blocked and explain the concrete blocker.
        - Your final response must conform exactly to the provided JSON schema.

        Current task contract:
        ```json
        {task_json}
        ```
        {repair_section}
        """
    ).strip() + "\n"


def locate_codex() -> str:
    candidate = shutil.which("codex")
    if not candidate:
        raise AutoDevError(
            "Codex CLI was not found on PATH. Open a new PowerShell terminal after installing/signing in to Codex, then run 'codex --version'."
        )
    return candidate


def run_codex_task(
    task: dict[str, Any],
    *,
    attempt: int,
    timeout_seconds: int,
    repair_context: str | None,
    model: str | None,
    reasoning_effort: str | None,
    verbose_events: bool,
) -> CodexRunResult:
    codex = locate_codex()
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = RUNS_DIR / f"{stamp}_{task['id']}_attempt-{attempt}"
    run_dir.mkdir(parents=True, exist_ok=False)
    prompt_path = run_dir / "prompt.txt"
    events_path = run_dir / "events.jsonl"
    result_path = run_dir / "result.json"
    metadata_path = run_dir / "metadata.json"

    prompt = build_task_prompt(task, repair_context=repair_context)
    prompt_path.write_text(prompt, encoding="utf-8")

    command: list[str] = [
        codex,
        "--ask-for-approval",
        "never",
        "exec",
        "--cd",
        str(REPO_ROOT),
        "--sandbox",
        "workspace-write",
        "--json",
        "--ephemeral",
        "--color",
        "never",
        "--output-schema",
        str(RESULT_SCHEMA_PATH),
        "--output-last-message",
        str(result_path),
    ]
    if model:
        command.extend(("--model", model))
    if reasoning_effort:
        command.extend(("--config", f'model_reasoning_effort="{reasoning_effort}"'))
    command.append("-")

    metadata_path.write_text(
        json.dumps(
            {
                "task_id": task["id"],
                "attempt": attempt,
                "started_at": iso_now(),
                "workspace": str(REPO_ROOT),
                "command": command[:-1] + ["<prompt from stdin>"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    CONSOLE.line("LAUNCH", f"Codex attempt {attempt}; logs: {run_dir.relative_to(REPO_ROOT)}", "magenta")
    process = create_process(command, stdin_pipe=True)
    assert process.stdin is not None
    process.stdin.write(prompt)
    process.stdin.close()

    process_result = stream_process(
        process,
        raw_log_path=events_path,
        timeout_seconds=timeout_seconds,
        event_mode=True,
        verbose_events=verbose_events,
    )

    structured: dict[str, Any] | None = None
    if result_path.exists():
        try:
            parsed = json.loads(result_path.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                structured = parsed
        except json.JSONDecodeError:
            structured = None

    thread_id: str | None = None
    if events_path.exists():
        for line in events_path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "thread.started":
                thread_id = event.get("thread_id")
                break

    return CodexRunResult(
        returncode=process_result.returncode,
        structured_result=structured,
        run_dir=run_dir,
        timed_out=process_result.timed_out,
        thread_id=thread_id,
    )


def expand_verification_command(command: Sequence[str]) -> list[str]:
    expanded: list[str] = []
    for item in command:
        if item == "{python}":
            expanded.append(sys.executable)
        else:
            expanded.append(str(item))
    return expanded


def run_command_live(command: Sequence[str], *, timeout_seconds: int, log_path: Path) -> ProcessResult:
    CONSOLE.line("VERIFY", display_command(command), "cyan")
    process = create_process(command, stdin_pipe=False)
    return stream_process(
        process,
        raw_log_path=log_path,
        timeout_seconds=timeout_seconds,
        event_mode=False,
    )


def verify_task(task: dict[str, Any], run_dir: Path) -> VerificationResult:
    all_output: list[str] = []
    diff_check = run_capture(("git", "diff", "--check"), check=False, timeout=60)
    all_output.append(f"$ git diff --check\n{diff_check.output}")
    if diff_check.returncode != 0:
        return VerificationResult(False, "\n".join(all_output), ["git", "diff", "--check"])

    timeout_seconds = int(task.get("verification_timeout_seconds", 300))
    for index, raw_command in enumerate(task.get("verification", []), start=1):
        if not isinstance(raw_command, list) or not all(isinstance(part, str) for part in raw_command):
            return VerificationResult(
                False,
                f"Invalid verification command in task {task['id']}: {raw_command!r}",
                None,
            )
        command = expand_verification_command(raw_command)
        log_path = run_dir / f"verification-{index}.log"
        result = run_command_live(command, timeout_seconds=timeout_seconds, log_path=log_path)
        all_output.append(f"$ {display_command(command)}\n{result.output}")
        if result.returncode != 0 or result.timed_out:
            return VerificationResult(False, "\n".join(all_output), command)

    return VerificationResult(True, "\n".join(all_output), None)


def save_failure_patch(run_dir: Path) -> Path:
    patch_path = run_dir / "failed.patch"
    # Intent-to-add makes untracked files appear in a normal Git diff without staging their content.
    git("add", "-N", ".", check=False)
    patch = git("diff", "--binary", "HEAD", check=False, timeout=120).output
    patch_path.write_text(patch, encoding="utf-8", errors="replace")
    git("reset", check=False)
    return patch_path


def rollback_to_head() -> None:
    git("reset", "--hard", "HEAD", check=True, timeout=120)
    git("clean", "-fd", check=True, timeout=120)


def commit_task(task: dict[str, Any], changed_paths: Sequence[str]) -> str:
    if not changed_paths:
        return ""
    git("add", "-A", "--", *changed_paths, check=True, timeout=120)
    message = str(task.get("commit_message") or f"autodev({task['id']}): {task['title']}")
    result = git("commit", "-m", message, check=True, timeout=180)
    CONSOLE.line("GIT", result.output.strip(), "green")
    commit_hash = git("rev-parse", "--short", "HEAD", check=True).output.strip()
    return commit_hash


def mark_blocked(state: dict[str, Any], task: dict[str, Any], reason: str, run_dir: Path | None) -> None:
    state.setdefault("blocked", {})[task["id"]] = {
        "reason": reason,
        "run_dir": normalize_relpath(run_dir.relative_to(REPO_ROOT)) if run_dir else None,
        "at": iso_now(),
    }
    save_state(state)


def mark_completed(state: dict[str, Any], task: dict[str, Any], commit_hash: str) -> None:
    completed = state.setdefault("completed", [])
    if task["id"] not in completed:
        completed.append(task["id"])
    state.setdefault("blocked", {}).pop(task["id"], None)
    if commit_hash:
        state.setdefault("commits", {})[task["id"]] = commit_hash
    save_state(state)


def execute_task(
    task: dict[str, Any],
    state: dict[str, Any],
    *,
    task_timeout_seconds: int,
    model: str | None,
    reasoning_effort: str | None,
    keep_failed_changes: bool,
    verbose_events: bool,
) -> bool:
    CONSOLE.header(f"{task['id']} — {task['title']}")
    CONSOLE.task(task.get("description", ""))
    CONSOLE.info("Allowed paths: " + ", ".join(task.get("allowed_paths", [])))

    max_repairs = int(task.get("max_repair_attempts", 1))
    verification_failure: str | None = None
    last_run: CodexRunResult | None = None

    for attempt in range(1, max_repairs + 2):
        last_run = run_codex_task(
            task,
            attempt=attempt,
            timeout_seconds=task_timeout_seconds,
            repair_context=verification_failure,
            model=model,
            reasoning_effort=reasoning_effort,
            verbose_events=verbose_events,
        )

        result = last_run.structured_result
        if last_run.timed_out:
            reason = f"Codex timed out after {task_timeout_seconds} seconds."
        elif last_run.returncode != 0:
            reason = f"Codex exited with code {last_run.returncode}."
        elif result is None:
            reason = "Codex did not produce a valid structured result."
        elif result.get("task_id") != task["id"]:
            reason = f"Codex returned task_id={result.get('task_id')!r}, expected {task['id']!r}."
        elif result.get("status") == "blocked":
            blockers = result.get("blockers") or [result.get("summary", "Unknown blocker")]
            reason = "Codex reported a blocker: " + "; ".join(map(str, blockers))
        else:
            reason = ""

        changed_paths = get_changed_paths()
        violations = validate_changed_paths(task, changed_paths)
        if violations:
            reason = "Path boundary violation: " + "; ".join(violations)

        if reason:
            CONSOLE.error(reason)
            patch = save_failure_patch(last_run.run_dir)
            if not keep_failed_changes:
                rollback_to_head()
                CONSOLE.warning(f"Failed changes rolled back. Patch saved at {patch.relative_to(REPO_ROOT)}")
            else:
                CONSOLE.warning("Failed changes kept in the working tree for inspection.")
            mark_blocked(state, task, reason, last_run.run_dir)
            return False

        CONSOLE.info("Changed files: " + (", ".join(changed_paths) if changed_paths else "none"))
        verification = verify_task(task, last_run.run_dir)
        if verification.ok:
            CONSOLE.success("External verification passed.")
            if changed_paths:
                stat = git("diff", "--stat", "HEAD", check=True).output.strip()
                if stat:
                    CONSOLE.line("DIFF", stat, "green")
                commit_hash = commit_task(task, changed_paths)
                CONSOLE.success(f"Committed {task['id']} as {commit_hash}")
            else:
                commit_hash = ""
                CONSOLE.warning("Task already satisfied; no repository change was required.")
            mark_completed(state, task, commit_hash)
            return True

        verification_failure = verification.output
        CONSOLE.error(
            "External verification failed"
            + (f": {display_command(verification.failed_command)}" if verification.failed_command else ".")
        )
        if attempt <= max_repairs:
            CONSOLE.warning(f"Starting repair attempt {attempt + 1} of {max_repairs + 1}.")
            continue

        reason = "Verification failed after all permitted repair attempts."
        patch = save_failure_patch(last_run.run_dir)
        if not keep_failed_changes:
            rollback_to_head()
            CONSOLE.warning(f"Failed changes rolled back. Patch saved at {patch.relative_to(REPO_ROOT)}")
        else:
            CONSOLE.warning("Failed changes kept in the working tree for inspection.")
        mark_blocked(state, task, reason, last_run.run_dir)
        return False

    return False


def doctor() -> int:
    CONSOLE.header("Ego Link AutoDev Doctor")
    checks: list[tuple[str, bool, str]] = []

    checks.append(("Python", sys.version_info >= (3, 10), sys.version.split()[0]))

    git_path = shutil.which("git")
    checks.append(("Git command", bool(git_path), git_path or "not found"))
    codex_path = shutil.which("codex")
    checks.append(("Codex command", bool(codex_path), codex_path or "not found"))

    if git_path:
        try:
            actual = actual_git_root()
            checks.append(("Workspace root", actual == REPO_ROOT.resolve(), f"expected={REPO_ROOT.resolve()} actual={actual}"))
        except AutoDevError as exc:
            checks.append(("Workspace root", False, str(exc)))

        name = git("config", "user.name", check=False).output.strip()
        email = git("config", "user.email", check=False).output.strip()
        checks.append(("Git identity", bool(name and email), f"{name or '<missing name>'} <{email or 'missing email'}>"))

    for directory in REQUIRED_DIRS:
        path = REPO_ROOT / directory
        checks.append((f"Directory {directory}", path.is_dir(), str(path)))
    for filename in REQUIRED_FILES:
        path = REPO_ROOT / filename
        checks.append((f"File {filename}", path.is_file(), str(path)))

    try:
        backlog = load_backlog()
        checks.append(("Backlog", True, f"{len(backlog['tasks'])} tasks"))
    except AutoDevError as exc:
        checks.append(("Backlog", False, str(exc)))

    try:
        schema = load_json(RESULT_SCHEMA_PATH)
        checks.append(("Result schema", isinstance(schema, dict), str(RESULT_SCHEMA_PATH)))
    except AutoDevError as exc:
        checks.append(("Result schema", False, str(exc)))

    if codex_path:
        version = run_capture((codex_path, "--version"), check=False, timeout=30)
        checks.append(("Codex version", version.returncode == 0, version.output.strip() or f"exit={version.returncode}"))

    dirty = worktree_status().strip() if git_path else ""
    checks.append(("Clean working tree", not bool(dirty), dirty or "clean"))

    failed = 0
    for name, ok, detail in checks:
        if ok:
            CONSOLE.success(f"{name}: {detail}")
        else:
            failed += 1
            CONSOLE.error(f"{name}: {detail}")

    if failed:
        CONSOLE.error(f"Doctor found {failed} blocking issue(s).")
        return 1
    CONSOLE.success("Environment is ready for autonomous execution.")
    return 0


def show_status() -> int:
    backlog = load_backlog()
    state = load_state()
    completed = set(state.get("completed", []))
    blocked = state.get("blocked", {})
    CONSOLE.header("Ego Link AutoDev Status")
    for task in backlog["tasks"]:
        task_id = task["id"]
        if task_id in completed:
            commit = state.get("commits", {}).get(task_id, "no-change")
            CONSOLE.success(f"{task_id}: done ({commit}) — {task['title']}")
        elif task_id in blocked:
            CONSOLE.error(f"{task_id}: blocked — {blocked[task_id].get('reason', 'unknown')}")
        elif task.get("human_gate"):
            CONSOLE.warning(f"{task_id}: human gate — {task['title']}")
        else:
            deps = task.get("depends_on", [])
            waiting = [dep for dep in deps if dep not in completed]
            if waiting:
                CONSOLE.info(f"{task_id}: waiting for {', '.join(waiting)} — {task['title']}")
            else:
                CONSOLE.task(f"{task_id}: ready — {task['title']}")
    if state.get("last_updated"):
        CONSOLE.info(f"State last updated: {state['last_updated']}")
    return 0


def reset_state(yes: bool) -> int:
    if not yes:
        CONSOLE.error("Reset requires --yes. This resets task state only; it does not change Git history.")
        return 2
    if STATE_PATH.exists():
        STATE_PATH.unlink()
    CONSOLE.success("AutoDev runtime state reset. Git commits were not changed.")
    return 0


def run_loop(args: argparse.Namespace) -> int:
    ensure_correct_workspace()
    assert_clean_worktree()
    backlog = load_backlog()
    branch = args.branch or backlog.get("default_branch") or DEFAULT_BRANCH

    if not args.dry_run and not args.no_branch_switch:
        ensure_branch(branch)
        assert_clean_worktree()

    state = load_state()
    max_tasks = args.max_tasks
    if args.until_blocked:
        max_tasks = 10_000

    completed_this_run = 0
    while completed_this_run < max_tasks:
        human_task = pending_human_gate(backlog, state)
        next_task = select_next_task(backlog, state)

        # select_next_task may return a human-gated task; stop instead of invoking Codex.
        if next_task and next_task.get("human_gate"):
            human_task = next_task
            next_task = None

        if next_task is None:
            if human_task:
                CONSOLE.warning(
                    f"Stopped at human/hardware gate {human_task['id']}: {human_task['title']}"
                )
            else:
                CONSOLE.success("No ready automated tasks remain.")
            break

        if args.dry_run:
            CONSOLE.task(f"Would run {next_task['id']}: {next_task['title']}")
            # Simulate dependency progress only for previewing the sequence.
            state.setdefault("completed", []).append(next_task["id"])
            completed_this_run += 1
            continue

        ok = execute_task(
            next_task,
            state,
            task_timeout_seconds=args.task_timeout,
            model=args.model,
            reasoning_effort=args.reasoning_effort,
            keep_failed_changes=args.keep_failed_changes,
            verbose_events=args.verbose_events,
        )
        if not ok:
            CONSOLE.error(f"AutoDev stopped at {next_task['id']}.")
            return 1
        completed_this_run += 1

    CONSOLE.header("AutoDev Run Summary")
    CONSOLE.success(f"Completed {completed_this_run} task(s) in this run.")
    if not args.dry_run:
        CONSOLE.info(f"Current branch: {git('branch', '--show-current', check=True).output.strip()}")
        CONSOLE.info(f"Current commit: {git('rev-parse', '--short', 'HEAD', check=True).output.strip()}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Visible, sequential Codex supervisor for the Ego Link repository."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("doctor", help="Validate workspace, tools, Git identity, and control files.")
    subparsers.add_parser("status", help="Show backlog and runtime task state.")

    reset_parser = subparsers.add_parser("reset", help="Reset ignored AutoDev runtime state only.")
    reset_parser.add_argument("--yes", action="store_true", help="Confirm state reset.")

    run_parser = subparsers.add_parser("run", help="Run ready backlog tasks sequentially.")
    run_parser.add_argument("--max-tasks", type=int, default=1, help="Maximum tasks to complete (default: 1).")
    run_parser.add_argument("--until-blocked", action="store_true", help="Continue until no task is ready or a task blocks.")
    run_parser.add_argument("--branch", default=None, help=f"AutoDev branch (default: backlog or {DEFAULT_BRANCH}).")
    run_parser.add_argument("--no-branch-switch", action="store_true", help="Stay on the current branch.")
    run_parser.add_argument("--dry-run", action="store_true", help="Preview task order without invoking Codex or changing Git.")
    run_parser.add_argument("--model", default=None, help="Optional Codex model override.")
    run_parser.add_argument(
        "--reasoning-effort",
        choices=("low", "medium", "high", "xhigh"),
        default="medium",
        help="Codex reasoning effort override (default: medium).",
    )
    run_parser.add_argument(
        "--task-timeout",
        type=int,
        default=DEFAULT_TASK_TIMEOUT_SECONDS,
        help=f"Per-Codex-attempt timeout in seconds (default: {DEFAULT_TASK_TIMEOUT_SECONDS}).",
    )
    run_parser.add_argument(
        "--keep-failed-changes",
        action="store_true",
        help="Keep failed uncommitted changes instead of saving a patch and rolling back.",
    )
    run_parser.add_argument(
        "--verbose-events",
        action="store_true",
        help="Print otherwise-unclassified Codex JSONL events.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            return doctor()
        if args.command == "status":
            return show_status()
        if args.command == "reset":
            return reset_state(args.yes)
        if args.command == "run":
            if args.max_tasks < 1:
                raise AutoDevError("--max-tasks must be at least 1.")
            if args.task_timeout < 60:
                raise AutoDevError("--task-timeout must be at least 60 seconds.")
            return run_loop(args)
        parser.error(f"Unknown command: {args.command}")
        return 2
    except KeyboardInterrupt:
        CONSOLE.error("Interrupted by user. Inspect the working tree before the next run.")
        return 130
    except AutoDevError as exc:
        CONSOLE.error(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

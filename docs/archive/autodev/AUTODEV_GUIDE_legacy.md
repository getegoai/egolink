# Ego Link AutoDev v0.2

This package adds a small, local supervisor around `codex exec`. It runs backlog tasks sequentially, streams the execution process in the VS Code terminal, verifies each task independently, commits successful work on a dedicated Git branch, and stops on failure or a human/hardware gate.

No multi-agent framework, MCP server, Agents SDK, or cloud orchestration layer is required.

## 1. Files added

```text
AGENTS.md
autodev/
  backlog.json
  result.schema.json
  .gitignore
  tests/test_supervisor.py
scripts/
  autodev.py
  autodev_bootstrap_check.py
  run_autodev.ps1
  watch_autodev.ps1
docs/
  AUTODEV_GUIDE.md
```

Runtime logs are created under `autodev/runs/` and state under `autodev/runtime/`. Both are ignored by Git.

## 2. Preconditions

Open the **EGOLINK repository root** in VS Code, then open an integrated PowerShell terminal.

Required tools:

- Python 3.10 or newer
- Git
- Codex CLI available as `codex`
- Codex CLI already signed in

## 3. Commit the supervisor package before the first run

After extracting this package into the repository root:

```powershell
git add AGENTS.md autodev docs/AUTODEV_GUIDE.md scripts/autodev.py scripts/autodev_bootstrap_check.py scripts/run_autodev.ps1
git commit -m "chore: add Ego Link AutoDev supervisor"
```

The working tree must be clean before autonomous execution starts.

Now check the environment:

```powershell
python scripts/autodev.py doctor
```

The supervisor derives the expected repository root from its own file path and compares it with `git rev-parse --show-toplevel`. It refuses to run when the workspace is wrong.

## 4. Run the three-task smoke test

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_autodev.ps1 -MaxTasks 3
```

Equivalent direct command:

```powershell
python scripts/autodev.py run --max-tasks 3 --branch autodev/egolink-p0
```

The first run creates or switches to the branch `autodev/egolink-p0`.

## 5. What is visible during execution

The terminal shows:

- selected task and dependency state;
- Codex thread start;
- command execution start/completion;
- file-change events;
- agent status messages;
- periodic heartbeat when Codex is quiet;
- each external verification command and its output;
- Git diff summary;
- commit hash;
- stop/block reason.

A second terminal can show the live dashboard with `python scripts/autodev.py watch`. The supervisor also maintains `autodev/runtime/LIVE_STATUS.md`.

The complete raw JSONL event stream and readable logs remain in:

```text
autodev/runs/<timestamp>_<task-id>_attempt-<n>/
```

Detailed private model reasoning is not printed. The console shows operational progress, commands, file changes, messages, and verification results.

## 6. Included first three tasks

The initial backlog is intentionally low-risk. It validates the automatic loop before the agent touches firmware behavior.

1. Create an evidence-based repository baseline document.
2. Add a standard-library repository contract test.
3. Add a tested `egolink_doctor.py` command-line diagnostic.

Each successful task receives its own Git commit.

## 7. Useful commands

Show task state:

```powershell
python scripts/autodev.py status
```

Preview ready tasks without invoking Codex:

```powershell
python scripts/autodev.py run --max-tasks 3 --dry-run
```

Run one task only:

```powershell
python scripts/autodev.py run --max-tasks 1
```

Use a specific Codex model:

```powershell
python scripts/autodev.py run --max-tasks 3 --model gpt-5.5
```

Reset only the local AutoDev task state:

```powershell
python scripts/autodev.py reset --yes
```

Run supervisor unit tests:

```powershell
python -m unittest discover -s autodev/tests -v
```

## 8. Failure behavior

By default, when a task fails after its allowed repair attempt:

1. the supervisor saves a binary Git patch in the task run directory;
2. it rolls the working tree back to the last successful commit;
3. it records the task as blocked;
4. it stops before starting another task.

Use `--keep-failed-changes` only when you intentionally want to inspect an uncommitted failed attempt in the working tree.

## 9. Expanding beyond three tasks

Edit `autodev/backlog.json` and add narrowly scoped tasks with:

- unique `id`;
- dependencies;
- explicit `allowed_paths`;
- concrete requirements;
- deterministic verification commands;
- a commit message;
- `human_gate: true` for physical-device steps.

Increase gradually:

```powershell
python scripts/autodev.py run --max-tasks 5
python scripts/autodev.py run --until-blocked
```

Keep real SIM7670G registration, GNSS fix, calling, firmware flashing, serial observation, and power measurement behind human/hardware gates.


## 10. Live monitoring

See `docs/AUTODEV_MONITORING.md` for the dual-terminal workflow, live status files, idle detection, raw event tailing, and interpretation of observable progress.

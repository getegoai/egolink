---
id: OPS-001
title: VPS Message Hub production hardening baseline
status: done
priority: high
requires_hardware: false
created: 2026-07-03
last_updated: 2026-07-03

context:
  - docs/development/VPS_MESSAGE_HUB.md
  - docs/development/PROTOCOL.md
  - docs/current/ACTIVE_BUILD.md
  - server/

allowed_paths:
  - server/
  - scripts/
  - docs/development/VPS_MESSAGE_HUB.md
  - docs/operations/

out_of_scope:
  - protocol/envelope changes (egolink.p0.v1 stays frozen)
  - firmware changes
  - Dashboard feature changes
  - changing the public endpoint address or port
---

# Problem

The VPS Message Hub (203.0.113.10:8790) is already operated as a real
production service during development (founder statement 2026-07-03), but it
has no documented monitoring, backup/restore, log rotation, disk-usage
control, or token rotation procedure. A disk-full event, process crash, or
token leak would silently break the walking skeleton and could lose evidence
data.

# Expected Result

A minimal but real production-operations baseline: the hub restarts on
failure, its data is backed up and restorably tested, disk growth is bounded,
basic liveness monitoring exists, and operational procedures are written in a
runbook.

# Acceptance Criteria

- [ ] Service supervision: hub runs under systemd (or equivalent) with
      restart-on-failure; unit file or config committed under `docs/operations/`
      or `scripts/`.
- [ ] Backup: a scheduled job archives the hub's event/report stores; a
      documented restore procedure is executed once against a scratch
      directory and its output recorded as evidence.
- [ ] Log/disk bounds: log rotation or size-capped logging configured; report
      store growth policy documented (what gets pruned, when).
- [ ] Liveness monitoring: a cron-based check hits `/health` and records
      failures somewhere the operator will actually see (file + optional
      notification); one simulated failure demonstrates detection.
- [ ] Token handling: runbook section describing where the runtime token
      lives, how to rotate it, and confirming no secret is committed to git.
- [ ] Runbook `docs/operations/VPS_RUNBOOK.md` covers: deploy, restart,
      backup/restore, rotation, health-check interpretation, and disk
      recovery.
- [ ] `python scripts/context_lint.py` and `scripts/verify.ps1` pass.

# Validation Commands

```powershell
python scripts/context_lint.py
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
```

# Hardware Validation

- Not applicable (server-side task). VPS access is performed by the operator;
  the builder prepares scripts/configs and the operator applies them on the
  VPS and captures command output as evidence.

# Decisions

- Keep HTTP+token as-is for now; TLS termination is a follow-up decision
  (record it in the runbook's risk section, do not implement here).

# Completion Evidence

- Completed: 2026-07-03 by claude (director executed directly over SSH with
  founder authorization; key auth `egolink_vps_ed25519`, no password used).
- Changed files: `scripts/ops/egolink_backup.sh`,
  `scripts/ops/egolink_healthcheck.sh`, `docs/operations/VPS_RUNBOOK.md`,
  `reports/ops/OPS-001-20260703-001/ops_evidence.md`; VPS-side:
  `/usr/local/bin/egolink-backup.sh`, `/usr/local/bin/egolink-healthcheck.sh`,
  `/etc/systemd/journald.conf.d/egolink.conf`, root crontab (2 entries).
- Test result: first backup ok (985KB); restore test integrity `ok` with all
  8 tables; healthcheck success + simulated-failure detection both verified;
  journald vacuumed to 496M under 500M cap; `context_lint` + `verify.ps1`
  run after doc changes.
- Restore-test evidence path: reports/ops/OPS-001-20260703-001/ops_evidence.md
- Monitoring-detection evidence path: same file (FAIL line captured).
- Remaining risks: no off-host backup copy, no outbound alerting, no TLS;
  root password rotation + PasswordAuthentication off are recommended
  operator actions (runbook section 1 and 8; OPS-002 candidates).

# Builder Prompt

```text
Read docs/tasks/active/OPS-001_VPS_PRODUCTION_HARDENING.md in
D:\pywork\egolink. Load only AGENTS.md, docs/CONTEXT_INDEX.md, and the files
in this packet's `context`. Do only this task; obey `allowed_paths` and
`out_of_scope`. Prepare all scripts/configs so the operator can apply them on
the VPS; clearly mark every step that requires operator execution. Run the
validation commands before finishing. If any acceptance criterion cannot be
met, stop and report the blocker. Return: changed files, validation output,
evidence paths. Do not update docs/current/STATUS.md and do not move this
packet to done/.
```

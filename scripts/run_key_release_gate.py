"""Validate and report an Ego Link key-release manifest.

The gate is intentionally evidence-first. It does not flash firmware, contact
hardware, deploy services, or rerun long field tests. A release manifest binds a
version to already captured build, deploy, flash, runtime, validation, and
non-claim evidence so later releases can be checked the same way.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


DEFAULT_MANIFEST = Path("docs/current/key_releases/KR-001_USB_FREE_RAW_LTE_LOCATION.json")
DEFAULT_OUTPUT_ROOT = Path("reports/key_releases")
VALID_STATUSES = {"release_candidate", "released"}
VALID_GATE_STATUSES = {"PASS", "WARN", "FAIL", "NOT_RUN"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def repo_path(repo_root: Path, relative_path: str) -> Path:
    return repo_root / relative_path.replace("/", "\\")


def git_commit_exists(repo_root: Path, commit: str) -> bool:
    if not commit:
        return False
    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"{commit}^{{commit}}"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def evaluate_release_gate(
    manifest: dict[str, Any],
    *,
    repo_root: Path,
    allow_missing_local_evidence: bool = False,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    release_id = str(manifest.get("release_id") or "")
    status = str(manifest.get("status") or "")
    if not release_id:
        errors.append("manifest.release_id is required")
    if status not in VALID_STATUSES:
        errors.append(f"manifest.status must be one of {sorted(VALID_STATUSES)}")

    gates = as_list(manifest.get("gates"))
    if not gates:
        errors.append("manifest.gates must include at least one gate")
    for gate in gates:
        if not isinstance(gate, dict):
            errors.append("each gate must be an object")
            continue
        gate_id = str(gate.get("id") or "unknown")
        gate_status = str(gate.get("status") or "")
        if gate_status not in VALID_GATE_STATUSES:
            errors.append(f"gate {gate_id} has invalid status {gate_status!r}")
        if gate_status == "FAIL":
            errors.append(f"gate {gate_id} is FAIL")
        if gate_status == "NOT_RUN":
            warnings.append(f"gate {gate_id} is NOT_RUN")

    evidence_results: list[dict[str, Any]] = []
    for item in as_list(manifest.get("evidence")):
        if not isinstance(item, dict):
            errors.append("each evidence item must be an object")
            continue
        evidence_path = str(item.get("path") or "")
        if not evidence_path:
            errors.append("evidence.path is required")
            continue
        required = bool(item.get("required", True))
        local_only = bool(item.get("local_only", False))
        exists = repo_path(repo_root, evidence_path).exists()
        evidence_results.append(
            {
                "path": evidence_path,
                "kind": item.get("kind", "unknown"),
                "required": required,
                "local_only": local_only,
                "exists": exists,
            }
        )
        if required and not exists:
            if local_only and allow_missing_local_evidence:
                warnings.append(f"local evidence missing but allowed: {evidence_path}")
            else:
                errors.append(f"required evidence missing: {evidence_path}")

    commit_results: list[dict[str, Any]] = []
    for item in as_list(manifest.get("commits")):
        if not isinstance(item, dict):
            errors.append("each commit item must be an object")
            continue
        commit = str(item.get("commit") or "")
        exists = git_commit_exists(repo_root, commit)
        commit_results.append({"commit": commit, "label": item.get("label", ""), "exists": exists})
        if not exists:
            errors.append(f"required commit missing: {commit}")

    non_claims = as_list(manifest.get("non_claims"))
    if not non_claims:
        warnings.append("manifest.non_claims is empty")

    result = "PASS" if not errors else "FAIL"
    return {
        "result": result,
        "generated_at": utc_now(),
        "release_id": release_id,
        "release_name": manifest.get("release_name", ""),
        "release_version": manifest.get("release_version", ""),
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "gate_count": len(gates),
        "evidence": evidence_results,
        "commits": commit_results,
        "non_claim_count": len(non_claims),
    }


def write_markdown_report(path: Path, manifest: dict[str, Any], report: dict[str, Any]) -> None:
    lines = [
        f"# {report.get('release_id', 'unknown')} Key Release Gate",
        "",
        f"- Result: {report['result']}",
        f"- Release: {report.get('release_name', '')}",
        f"- Version: {report.get('release_version', '')}",
        f"- Status: {report.get('status', '')}",
        f"- Generated at: {report.get('generated_at', '')}",
        "",
        "## Gates",
        "",
    ]
    for gate in as_list(manifest.get("gates")):
        if isinstance(gate, dict):
            lines.append(f"- {gate.get('id', 'unknown')}: {gate.get('status', 'unknown')} - {gate.get('summary', '')}")
    lines.extend(["", "## Evidence", ""])
    for item in report.get("evidence", []):
        marker = "ok" if item.get("exists") else "missing"
        lines.append(f"- {marker}: {item.get('path')} ({item.get('kind')})")
    lines.extend(["", "## Non-Claims", ""])
    for item in as_list(manifest.get("non_claims")):
        lines.append(f"- {item}")
    lines.extend(["", "## Errors", ""])
    if report.get("errors"):
        lines.extend(f"- {item}" for item in report["errors"])
    else:
        lines.append("- none")
    lines.extend(["", "## Warnings", ""])
    if report.get("warnings"):
        lines.extend(f"- {item}" for item in report["warnings"])
    else:
        lines.append("- none")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--allow-missing-local-evidence", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = args.repo_root.resolve()
    manifest_path = args.manifest if args.manifest.is_absolute() else repo_root / args.manifest
    manifest = load_json(manifest_path)
    report = evaluate_release_gate(
        manifest,
        repo_root=repo_root,
        allow_missing_local_evidence=args.allow_missing_local_evidence,
    )
    output_dir = args.output_dir or (repo_root / DEFAULT_OUTPUT_ROOT / str(report.get("release_id") or "unknown"))
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "release_gate_report.json"
    markdown_path = output_dir / "release_gate_report.md"
    report["report_path"] = str(report_path)
    report["markdown_report_path"] = str(markdown_path)
    write_json(report_path, report)
    write_markdown_report(markdown_path, manifest, report)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"{report['result']} key release gate {report.get('release_id')}: {markdown_path}")
    return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

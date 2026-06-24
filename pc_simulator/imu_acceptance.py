from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


ACCEPTANCE_SCHEMA_VERSION = "egolink.imu_acceptance_preflight.v0.1"
EVIDENCE_SCHEMA_VERSION = "egolink.imu_acceptance_evidence.v0.1"

REQUIRED_GATES = [
    {
        "id": "product_mounting_direction_frozen",
        "label": "Product mounting direction frozen",
        "missing_action": "Freeze the IMU board orientation in the target enclosure or wearable fixture.",
    },
    {
        "id": "production_fixture_defined",
        "label": "Production fixture defined",
        "missing_action": "Define the production or lab fixture used for repeatable IMU calibration.",
    },
    {
        "id": "six_face_or_equivalent_accel_calibration_complete",
        "label": "Six-face or equivalent accel calibration complete",
        "missing_action": "Capture the final accel calibration after the mechanical stack is frozen.",
    },
    {
        "id": "signed_static_gyro_bias_complete",
        "label": "Signed static gyro bias complete",
        "missing_action": "Capture signed static gyro bias with the final mounting orientation.",
    },
    {
        "id": "temperature_drift_characterized",
        "label": "Temperature drift characterized",
        "missing_action": "Characterize accel/gyro drift across the expected operating temperature range.",
    },
    {
        "id": "fifo_drdy_interrupt_validated",
        "label": "FIFO/DRDY interrupt validated",
        "missing_action": "Validate the selected FIFO or DRDY interrupt path on hardware.",
    },
    {
        "id": "power_current_waveform_validated",
        "label": "Power/current waveform validated",
        "missing_action": "Align firmware power markers with PPK2/Otii or equivalent current waveforms.",
    },
    {
        "id": "backend_quality_gate_passed",
        "label": "Backend quality gate passed",
        "missing_action": "Repeat backend live capture, quality gate, and replay with the final configuration.",
    },
    {
        "id": "m1_recording_replay_passed",
        "label": "M1 recording and replay passed",
        "missing_action": "Record and replay an M1 session using the accepted IMU backend evidence.",
    },
    {
        "id": "recalibration_triggers_reviewed",
        "label": "Recalibration triggers reviewed",
        "missing_action": "Review hardware, mounting, firmware, power, and fixture changes against recalibration triggers.",
    },
]

EXPECTED_ARTIFACTS = {
    "product_mounting_direction_frozen": (
        "Mounting-direction note with board/enclosure photos or fixture drawing, "
        "axis convention, and operator confirmation."
    ),
    "production_fixture_defined": (
        "Fixture description with repeatable board placement, orientation marks, "
        "and calibration operator steps."
    ),
    "six_face_or_equivalent_accel_calibration_complete": (
        "Final six-face or equivalent accel calibration JSON/Markdown generated "
        "after the mounting stack is frozen."
    ),
    "signed_static_gyro_bias_complete": (
        "Static gyro bias capture from the final mounting orientation, with signed "
        "x/y/z bias values and capture duration."
    ),
    "temperature_drift_characterized": (
        "Temperature sweep or bounded engineering drift note covering the expected "
        "operating range and recalibration limits."
    ),
    "fifo_drdy_interrupt_validated": (
        "Hardware log/report proving the selected FIFO or DRDY interrupt path "
        "fires and is consumed by firmware."
    ),
    "power_current_waveform_validated": (
        "PPK2/Otii or equivalent current waveform aligned to firmware "
        "POWER_MARKER records."
    ),
    "backend_quality_gate_passed": (
        "Final backend live capture, quality report, and source-boundary report "
        "from the accepted configuration."
    ),
    "m1_recording_replay_passed": (
        "M1 recording directory plus quality and replay reports generated from "
        "accepted backend evidence."
    ),
    "recalibration_triggers_reviewed": (
        "Review note covering PCB, IMU lot, mounting, enclosure, ODR/filter/FIFO, "
        "power rail, firmware conversion, and fixture changes."
    ),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object")
    return value


def _load_json(path: Path) -> dict[str, Any]:
    return _require_mapping(json.loads(path.read_text(encoding="utf-8-sig")), str(path))


def _evidence_by_gate(evidence_manifest: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if evidence_manifest is None:
        return {}
    manifest = _require_mapping(evidence_manifest, "evidence_manifest")
    evidence = _require_mapping(manifest.get("evidence", {}), "evidence_manifest.evidence")
    return {str(gate_id): _require_mapping(value, f"evidence.{gate_id}") for gate_id, value in evidence.items()}


def _evaluate_gate(gate: dict[str, str], evidence: dict[str, Any] | None) -> dict[str, Any]:
    gate_id = gate["id"]
    if evidence is None:
        return {
            "id": gate_id,
            "label": gate["label"],
            "passed": False,
            "status": "missing",
            "artifact": None,
            "observed_on_hardware": False,
            "reason": "evidence_missing",
            "next_action": gate["missing_action"],
        }

    status = str(evidence.get("status", "missing"))
    artifact = evidence.get("artifact")
    observed_on_hardware = bool(evidence.get("observed_on_hardware"))
    passed = bool(status == "pass" and artifact and observed_on_hardware)
    reason = "ok" if passed else "evidence_not_hardware_validated"
    if status != "pass":
        reason = f"status_{status}"
    elif not artifact:
        reason = "artifact_missing"
    elif not observed_on_hardware:
        reason = "hardware_observation_missing"

    return {
        "id": gate_id,
        "label": gate["label"],
        "passed": passed,
        "status": status,
        "artifact": str(artifact) if artifact else None,
        "observed_on_hardware": observed_on_hardware,
        "reason": reason,
        "next_action": None if passed else gate["missing_action"],
    }


def build_acceptance_preflight_report(
    calibration_profile: dict[str, Any],
    *,
    evidence_manifest: dict[str, Any] | None = None,
    report_id: str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    profile = _require_mapping(calibration_profile, "calibration_profile")
    evidence = _evidence_by_gate(evidence_manifest)
    gate_results = [_evaluate_gate(gate, evidence.get(gate["id"])) for gate in REQUIRED_GATES]

    profile_stage = str(profile.get("stage", "unknown"))
    profile_production_ready = bool(profile.get("production_ready"))
    profile_formal_acceptance = bool(profile.get("formal_imu_acceptance"))
    all_gates_passed = all(gate["passed"] for gate in gate_results)
    profile_ready = bool(profile_stage == "production" and profile_production_ready and profile_formal_acceptance)
    formal_imu_acceptance = bool(all_gates_passed and profile_ready)

    profile_blockers: list[str] = []
    if profile_stage != "production":
        profile_blockers.append("calibration_profile_not_production_stage")
    if not profile_production_ready:
        profile_blockers.append("calibration_profile_production_ready_false")
    if not profile_formal_acceptance:
        profile_blockers.append("calibration_profile_formal_imu_acceptance_false")

    failed_gates = [gate["id"] for gate in gate_results if not gate["passed"]]
    next_actions = [
        gate["next_action"]
        for gate in gate_results
        if gate["next_action"]
    ]
    next_actions.extend(profile_blockers)

    return {
        "schema_version": ACCEPTANCE_SCHEMA_VERSION,
        "report_id": report_id,
        "generated_at": generated_at or utc_now(),
        "calibration_profile_id": profile.get("profile_id"),
        "hardware_profile": profile.get("hardware_profile"),
        "calibration_profile_stage": profile_stage,
        "calibration_profile_production_ready": profile_production_ready,
        "calibration_profile_formal_imu_acceptance": profile_formal_acceptance,
        "required_evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
        "gate_results": gate_results,
        "all_evidence_gates_passed": all_gates_passed,
        "profile_blockers": profile_blockers,
        "failed_gates": failed_gates,
        "formal_imu_acceptance": formal_imu_acceptance,
        "motionnet_training_enabled": False,
        "boundary": {
            "can_use_for": [
                "product_acceptance_preflight",
                "operator_checklist_generation",
                "missing_evidence_tracking",
            ],
            "must_not_use_for": [
                "claiming_product_imu_acceptance_without_hardware_evidence",
                "motionnet_training_enablement",
                "fall_or_impact_product_claims",
            ],
            "notes": (
                "This preflight report is a gate ledger. It does not create "
                "hardware evidence; each pass requires a hardware-observed "
                "artifact for the final mechanical and firmware configuration."
            ),
        },
        "next_actions": next_actions,
    }


def build_evidence_manifest_template(
    *,
    manifest_id: str,
    hardware_profile: str,
    calibration_profile_id: str | None = None,
    target_mounting_direction: str | None = None,
    reference_artifacts: list[str] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "manifest_id": manifest_id,
        "generated_at": generated_at or utc_now(),
        "hardware_profile": hardware_profile,
        "calibration_profile_id": calibration_profile_id,
        "target_mounting_direction": target_mounting_direction or "pending",
        "reference_artifacts": reference_artifacts or [],
        "evidence": {
            gate["id"]: {
                "status": "pending",
                "artifact": None,
                "observed_on_hardware": False,
                "expected_artifact": EXPECTED_ARTIFACTS[gate["id"]],
                "operator_action": gate["missing_action"],
                "acceptance_rule": (
                    "Set status to pass only when artifact names a durable file "
                    "or report from the final hardware configuration and "
                    "observed_on_hardware is true."
                ),
            }
            for gate in REQUIRED_GATES
        },
        "boundary": {
            "formal_imu_acceptance": False,
            "motionnet_training_enabled": False,
            "notes": (
                "This is an operator evidence template. It does not validate "
                "hardware by itself; it becomes acceptance evidence only after "
                "each gate points to hardware-observed artifacts."
            ),
        },
    }


def format_acceptance_markdown(
    report: dict[str, Any],
    title: str = "# TIMU-009B IMU Product Acceptance Preflight",
) -> str:
    rows = []
    for gate in report["gate_results"]:
        artifact = gate["artifact"] or "missing"
        rows.append(
            "| "
            f"`{gate['id']}` | `{gate['status']}` | `{gate['passed']}` | "
            f"`{gate['observed_on_hardware']}` | `{artifact}` | `{gate['reason']}` |"
        )

    blockers = report["profile_blockers"] or ["none"]
    failed_gates = report["failed_gates"] or ["none"]
    actions = report["next_actions"] or ["none"]

    return "\n".join(
        [
            title,
            "",
            f"- Report id: `{report['report_id']}`",
            f"- Calibration profile id: `{report['calibration_profile_id']}`",
            f"- Hardware profile: `{report['hardware_profile']}`",
            f"- Calibration profile stage: `{report['calibration_profile_stage']}`",
            f"- Calibration profile production ready: `{report['calibration_profile_production_ready']}`",
            f"- Calibration profile formal IMU acceptance: `{report['calibration_profile_formal_imu_acceptance']}`",
            f"- All evidence gates passed: `{report['all_evidence_gates_passed']}`",
            f"- Formal IMU acceptance: `{report['formal_imu_acceptance']}`",
            f"- MotionNet training enabled: `{report['motionnet_training_enabled']}`",
            "",
            "## Gate Results",
            "",
            "| Gate | Status | Passed | Hardware observed | Artifact | Reason |",
            "|---|---|---:|---:|---|---|",
            *rows,
            "",
            "## Profile Blockers",
            "",
            *[f"- `{blocker}`" for blocker in blockers],
            "",
            "## Failed Gates",
            "",
            *[f"- `{gate}`" for gate in failed_gates],
            "",
            "## Next Actions",
            "",
            *[f"- {action}" for action in actions],
            "",
            "## Boundary",
            "",
            report["boundary"]["notes"],
            "",
        ]
    )


def format_evidence_manifest_markdown(
    manifest: dict[str, Any],
    title: str = "# TIMU-009C-B0 IMU Product Mounting Evidence Template",
) -> str:
    rows = []
    for gate in REQUIRED_GATES:
        evidence = _require_mapping(manifest["evidence"][gate["id"]], f"evidence.{gate['id']}")
        rows.append(
            "| "
            f"`{gate['id']}` | `{evidence['status']}` | "
            f"`{evidence['observed_on_hardware']}` | {evidence['expected_artifact']} | "
            f"{evidence['operator_action']} |"
        )

    references = manifest.get("reference_artifacts") or ["none"]

    return "\n".join(
        [
            title,
            "",
            f"- Manifest id: `{manifest['manifest_id']}`",
            f"- Hardware profile: `{manifest['hardware_profile']}`",
            f"- Calibration profile id: `{manifest.get('calibration_profile_id')}`",
            f"- Target mounting direction: `{manifest['target_mounting_direction']}`",
            f"- Formal IMU acceptance: `{manifest['boundary']['formal_imu_acceptance']}`",
            f"- MotionNet training enabled: `{manifest['boundary']['motionnet_training_enabled']}`",
            "",
            "## Operator Rule",
            "",
            manifest["boundary"]["notes"],
            "",
            "Do not set a gate to `pass` until the artifact is a durable report or"
            " file from the final hardware configuration and `observed_on_hardware`"
            " is `true`.",
            "",
            "## Evidence Gates",
            "",
            "| Gate | Status | Hardware observed | Expected artifact | Operator action |",
            "|---|---|---:|---|---|",
            *rows,
            "",
            "## Reference Artifacts",
            "",
            *[f"- `{artifact}`" for artifact in references],
            "",
            "## Next Hardware Step",
            "",
            "Fix the QMI8658 board in the target wearable orientation or a repeatable"
            " temporary fixture, then capture the final mounting/static calibration"
            " evidence before promoting any gate to `pass`.",
            "",
        ]
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an IMU product acceptance preflight report.")
    parser.add_argument("--calibration-profile", required=True, type=Path)
    parser.add_argument("--evidence-manifest", type=Path, default=None)
    parser.add_argument("--report-id", required=True)
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument("--markdown", type=Path, default=None)
    parser.add_argument("--title", default="# TIMU-009B IMU Product Acceptance Preflight")
    parser.add_argument("--evidence-template-json", type=Path, default=None)
    parser.add_argument("--evidence-template-markdown", type=Path, default=None)
    parser.add_argument("--manifest-id", default=None)
    parser.add_argument("--target-mounting-direction", default=None)
    parser.add_argument("--reference-artifact", action="append", default=[])
    parser.add_argument("--json", action="store_true", help="Print the report as JSON.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    profile = _load_json(args.calibration_profile)
    evidence_manifest = _load_json(args.evidence_manifest) if args.evidence_manifest else None
    report = build_acceptance_preflight_report(
        profile,
        evidence_manifest=evidence_manifest,
        report_id=args.report_id,
    )

    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(format_acceptance_markdown(report, args.title), encoding="utf-8")
    if args.evidence_template_json or args.evidence_template_markdown:
        manifest = build_evidence_manifest_template(
            manifest_id=args.manifest_id or f"{args.report_id}-evidence-template",
            hardware_profile=str(profile.get("hardware_profile", "unknown")),
            calibration_profile_id=str(profile.get("profile_id")) if profile.get("profile_id") else None,
            target_mounting_direction=args.target_mounting_direction,
            reference_artifacts=args.reference_artifact,
        )
        if args.evidence_template_json:
            args.evidence_template_json.parent.mkdir(parents=True, exist_ok=True)
            args.evidence_template_json.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        if args.evidence_template_markdown:
            args.evidence_template_markdown.parent.mkdir(parents=True, exist_ok=True)
            args.evidence_template_markdown.write_text(format_evidence_manifest_markdown(manifest), encoding="utf-8")
    if args.json or not (args.output_json or args.markdown or args.evidence_template_json or args.evidence_template_markdown):
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

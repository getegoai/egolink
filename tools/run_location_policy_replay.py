"""Run Location Engine/Sensor Policy v0 over a Field Session or normalized JSONL."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pc_simulator import field_session_replay  # noqa: E402
from pc_simulator.location_policy_replay import (  # noqa: E402
    LocationPolicyReplayError,
    compare_replay_reports,
    load_normalized_observations_jsonl,
    replay_field_session,
    replay_observations,
)
from pc_simulator.sensor_policy_v0 import (  # noqa: E402
    SensorPolicyError,
    load_sensor_policy_config,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--manifest", type=Path, help="Sealed A0 Field Session manifest.")
    source.add_argument(
        "--normalized-jsonl",
        type=Path,
        help="Already-normalized Location Engine observation JSONL.",
    )
    parser.add_argument(
        "--config",
        action="append",
        required=True,
        type=Path,
        help="Sensor Policy JSON; repeat to compare configurations.",
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--json", action="store_true", help="Print the summary JSON.")
    return parser.parse_args(argv)


def _safe_name(value: str) -> str:
    return "".join(character if character.isalnum() or character in "-_." else "_" for character in value)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        configs = [load_sensor_policy_config(path) for path in args.config]
        loaded_observations = (
            load_normalized_observations_jsonl(args.normalized_jsonl)
            if args.normalized_jsonl is not None
            else None
        )
        if args.manifest is not None:
            field_session_replay.ensure_output_outside_session(
                args.output_dir, args.manifest.parent
            )
        reports = []
        for config in configs:
            if args.manifest is not None:
                report = replay_field_session(args.manifest, config)
            else:
                report = replay_observations(
                    loaded_observations.observations if loaded_observations else [],
                    config,
                    input_metadata={
                        "kind": "normalized_jsonl",
                        "path": loaded_observations.path if loaded_observations else None,
                        "contract_version": (
                            loaded_observations.contract_version
                            if loaded_observations
                            else None
                        ),
                        "sha256": loaded_observations.sha256
                        if loaded_observations
                        else None,
                        "record_count": loaded_observations.record_count
                        if loaded_observations
                        else 0,
                    },
                )
            reports.append(report)
        comparisons = [
            compare_replay_reports(reports[0], candidate) for candidate in reports[1:]
        ]
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for report in reports:
            config_id = str(report["config"]["config_id"])
            config_hash = str(report["config"]["config_hash"])
            output = args.output_dir / (
                f"replay-{_safe_name(config_id)}-{config_hash[:12]}.json"
            )
            output.write_text(
                json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        run_status = (
            "insufficient_evidence"
            if any(report.get("run_status") != "completed" for report in reports)
            else "completed"
        )
        summary = {
            "status": run_status,
            "report_count": len(reports),
            "reports": [
                {
                    "config_id": report["config"]["config_id"],
                    "config_hash": report["config"]["config_hash"],
                    "canonical_sha256": report["canonical_sha256"],
                    "run_status": report["run_status"],
                    "metrics": report["metrics"],
                }
                for report in reports
            ],
            "comparisons": comparisons,
        }
        (args.output_dir / "comparison.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            label = "PASS" if run_status == "completed" else "INSUFFICIENT"
            print(
                f"{label} location-policy replay "
                f"configs={len(reports)} "
                "location_observations="
                f"{reports[0]['metrics']['external_location_evidence_observation_count']}"
            )
        return 0 if run_status == "completed" else 1
    except (
        LocationPolicyReplayError,
        SensorPolicyError,
        field_session_replay.FieldSessionReplayError,
        OSError,
        ValueError,
    ) as exc:
        print(f"FAIL location-policy replay: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

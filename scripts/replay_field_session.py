"""Replay one sealed A0-003 Field Session or run EXP-A1-000."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pc_simulator import field_session_replay  # noqa: E402


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--generated-at",
        help="Optional deterministic UTC report timestamp; defaults to the package seal time.",
    )
    parser.add_argument("--json", action="store_true", help="Print the machine report to stdout.")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    replay = subparsers.add_parser(
        "replay",
        help="Replay synchronized package streams and regenerate a private trajectory.",
    )
    _add_common_arguments(replay)
    replay.add_argument("--mask-gnss-start", help="Optional UTC start of a GNSS-only mask.")
    replay.add_argument("--mask-gnss-duration-s", type=int)

    experiment = subparsers.add_parser(
        "exp-a1-000",
        help="Run the bounded 60-second GNSS blackout smoke experiment.",
    )
    _add_common_arguments(experiment)
    experiment.add_argument("--blackout-start", required=True)
    experiment.add_argument("--blackout-duration-s", type=int, default=60)
    experiment.add_argument("--lte-centroids", type=Path)
    experiment.add_argument("--endpoint-tolerance-s", type=float, default=0.0)
    experiment.add_argument("--motion-window-s", type=float, default=1.0)
    experiment.add_argument("--motion-threshold-m-s2", type=float, default=0.75)
    experiment.add_argument("--motion-min-samples", type=int, default=2)
    experiment.add_argument("--imu-max-gap-s", type=float, default=1.0)
    return parser.parse_args(argv)


def _print_report(report: dict[str, object], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return
    if report.get("experiment_id") == field_session_replay.EXPERIMENT_ID:
        baselines = report.get("baselines")
        statuses = ",".join(
            f"{row.get('baseline_id')}={row.get('status')}"
            for row in baselines
            if isinstance(row, dict)
        ) if isinstance(baselines, list) else "none"
        print(
            f"{report.get('run_status', 'unavailable').upper()} "
            f"{field_session_replay.EXPERIMENT_ID} baselines={statuses} "
            f"gate={report.get('gate_status')}"
        )
        return
    execution = report.get("execution")
    timeline = execution.get("timeline", {}) if isinstance(execution, dict) else {}
    validation = report.get("input_validation")
    field_eligible = validation.get("field_eligible") if isinstance(validation, dict) else None
    print(
        "PASS field-session replay "
        f"records={timeline.get('record_count', 0)} "
        f"field_eligible={str(field_eligible).lower()} gate={report.get('gate_status')}"
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        package = field_session_replay.load_replay_package(
            args.manifest,
            generated_at=args.generated_at,
        )
        if args.command == "replay":
            report = field_session_replay.write_replay_outputs(
                package,
                args.output_dir,
                mask_start_utc=args.mask_gnss_start,
                mask_duration_s=args.mask_gnss_duration_s,
                generated_at=args.generated_at,
            )
            exit_code = 0
        else:
            config = field_session_replay.ExperimentConfig(
                blackout_start_utc=args.blackout_start,
                blackout_duration_s=args.blackout_duration_s,
                endpoint_tolerance_s=args.endpoint_tolerance_s,
                motion_window_s=args.motion_window_s,
                motion_threshold_m_s2=args.motion_threshold_m_s2,
                motion_min_samples=args.motion_min_samples,
                imu_max_gap_s=args.imu_max_gap_s,
            )
            report = field_session_replay.write_exp_a1_000_outputs(
                package,
                args.output_dir,
                config=config,
                lte_centroid_path=args.lte_centroids,
                generated_at=args.generated_at,
            )
            exit_code = 0 if report.get("run_status") == "completed" else 1
    except field_session_replay.FieldSessionReplayError as error:
        print(f"FAIL field-session replay: {error}", file=sys.stderr)
        return 2
    except (OSError, ValueError) as error:
        print(f"FAIL field-session replay: {error}", file=sys.stderr)
        return 2

    _print_report(report, as_json=args.json)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

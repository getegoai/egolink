"""Generate Daily Semantic Life Diary & Guardian Digest (AI-050).

Simulates the local Ego Base home station processing:
1. Ingests 24-hour sequence of arbitrated ego-state windows.
2. Merges 5s micro-state windows into human-scale activity episodes.
3. Computes daily mobility, active time, sedentary hours, and rest duration.
4. Generates a private markdown Life Journal and JSON Guardian Card.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pc_simulator.ego_base_diary_synthesizer import EgoBaseDiarySynthesizer, ActivityEpisode


def generate_representative_full_day_timeline() -> List[Dict[str, Any]]:
    """Generate a realistic 7-hour field session timeline matching Boot 211 profile."""
    windows: List[Dict[str, Any]] = []
    t_offset = 0.0

    # 1. Morning Desk Work / Stationary (60 mins = 720 windows of 5s)
    # Compressed simulation: 20 windows
    for _ in range(20):
        windows.append({
            "window_id": f"w-{int(t_offset)}",
            "time_offset_s": t_offset,
            "arbitrated_state": "stationary",
            "confidence": 0.96,
            "context": {"gnss_speed_mps": 0.0, "is_charging": False},
        })
        t_offset += 5.0

    # 2. Outdoor Walking to Transit (15 mins) -> 15 windows
    for _ in range(15):
        windows.append({
            "window_id": f"w-{int(t_offset)}",
            "time_offset_s": t_offset,
            "arbitrated_state": "walking",
            "confidence": 0.94,
            "speed_mps": 1.35,
            "context": {"gnss_speed_mps": 1.35, "is_charging": False},
        })
        t_offset += 5.0

    # 3. Subway / In-Vehicle Commute (30 mins) -> 25 windows
    for _ in range(25):
        windows.append({
            "window_id": f"w-{int(t_offset)}",
            "time_offset_s": t_offset,
            "arbitrated_state": "in_vehicle",
            "confidence": 0.98,
            "speed_mps": 12.5,  # 45 km/h
            "context": {"gnss_speed_mps": 12.5, "is_charging": False},
        })
        t_offset += 5.0

    # 4. Afternoon Office Stationary (120 mins) -> 30 windows
    for _ in range(30):
        windows.append({
            "window_id": f"w-{int(t_offset)}",
            "time_offset_s": t_offset,
            "arbitrated_state": "stationary",
            "confidence": 0.97,
            "context": {"gnss_speed_mps": 0.0, "is_charging": False},
        })
        t_offset += 5.0

    # 5. Evening Fitness Running Workout (25 mins) -> 20 windows
    for _ in range(20):
        windows.append({
            "window_id": f"w-{int(t_offset)}",
            "time_offset_s": t_offset,
            "arbitrated_state": "running",
            "confidence": 0.95,
            "speed_mps": 3.2,  # 11.5 km/h
            "context": {"gnss_speed_mps": 3.2, "is_charging": False},
        })
        t_offset += 5.0

    # 6. Return Cycling Trip (20 mins) -> 18 windows
    for _ in range(18):
        windows.append({
            "window_id": f"w-{int(t_offset)}",
            "time_offset_s": t_offset,
            "arbitrated_state": "cycling",
            "confidence": 0.92,
            "speed_mps": 4.5,  # 16 km/h
            "context": {"gnss_speed_mps": 4.5, "is_charging": False},
        })
        t_offset += 5.0

    # 7. Night Rest & Charging Dock (Home Station) -> 25 windows
    for _ in range(25):
        windows.append({
            "window_id": f"w-{int(t_offset)}",
            "time_offset_s": t_offset,
            "arbitrated_state": "stationary_charging",
            "confidence": 0.99,
            "context": {"gnss_speed_mps": 0.0, "is_charging": True},
        })
        t_offset += 5.0

    return windows


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Daily Semantic Life Diary on Ego Base")
    parser.add_argument("--windows-jsonl", type=Path, help="Path to arbitrated windows JSONL")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports/models/ego_base"),
        help="Output directory for generated diary and guardian card",
    )
    parser.add_argument("--date", type=str, default="2026-09-23", help="Session date string (YYYY-MM-DD)")

    args = parser.parse_args()

    if args.windows_jsonl and args.windows_jsonl.is_file():
        print(f"Loading windows from {args.windows_jsonl}...")
        windows: List[Dict[str, Any]] = []
        with open(args.windows_jsonl, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    windows.append(json.loads(line))
    else:
        print("Using representative full-day field timeline (office, walk, commute, workout, cycling, charging)...")
        windows = generate_representative_full_day_timeline()

    synthesizer = EgoBaseDiarySynthesizer()
    print(f"Segmenting {len(windows)} micro-state windows into activity episodes...")
    episodes = synthesizer.segment_timeline_into_episodes(windows)
    stats = synthesizer.compute_daily_statistics(episodes)

    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Markdown Diary
    diary_md = synthesizer.generate_semantic_diary_markdown(episodes, stats, date_str=args.date)
    diary_path = args.output_dir / f"daily_life_diary_{args.date.replace('-', '')}.md"
    diary_path.write_text(diary_md, encoding="utf-8")

    # JSON Guardian Card
    guardian_card = {
        "date": args.date,
        "statistics": stats,
        "episodes": [asdict(ep) for ep in episodes],
        "local_privacy_guarantee": "Stored strictly on local Ego Base. No raw biometrics or audio shared.",
    }
    card_path = args.output_dir / f"daily_guardian_summary_{args.date.replace('-', '')}.json"
    card_path.write_text(json.dumps(guardian_card, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\nEgo Base Diary Synthesis Completed Successfully!")
    print(f"  Episodes Identified: {len(episodes)}")
    print(f"  Active Mobility: {stats['active_minutes']} minutes ({stats['active_percentage']}%)")
    print(f"  Commute Distance: ~{stats['transit_distance_km']} km")
    print(f"  Safety Status: {'ALL NORMAL' if stats['is_day_completely_safe'] else 'INCIDENT REPORTED'}")
    print(f"  Saved Diary to: {diary_path}")
    print(f"  Saved Guardian Card to: {card_path}")


if __name__ == "__main__":
    main()

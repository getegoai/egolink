"""Ego Base Local Station Timeline Ingester & Semantic Diary Synthesizer (AI-050).

Implements the L3 narrative and guardian digest layer defined in ADR-0016,
ADR-0017, and AI_NATIVE_EGO_STATE_FLYWHEEL.md:
1. Episodic Segmentation: Merges high-frequency 5.0s micro-state windows
   into coherent human activity bouts (commute, walk, workout, sedentary work, rest).
2. Daily Health & Mobility Statistics: Computes active duration, sedentary ratio,
   transit distance, and rest quality.
3. Local-First Semantic Synthesis: Generates private daily life journals and
   guardian reassurance cards without exposing raw private telemetry to public clouds.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np


@dataclass
class ActivityEpisode:
    """A cohesive temporal activity episode merged from contiguous windows."""
    episode_id: str
    activity_type: str
    start_time_s: float
    end_time_s: float
    duration_seconds: float
    start_iso: str
    end_iso: str
    mean_confidence: float
    window_count: int
    mean_speed_mps: Optional[float] = None
    estimated_distance_meters: Optional[float] = None
    is_safety_event: bool = False
    safety_details: Optional[str] = None


class EgoBaseDiarySynthesizer:
    """Processes daily ego-state timeline and synthesizes L3 life diaries."""

    def __init__(self, min_episode_duration_s: float = 15.0):
        self.min_episode_duration_s = min_episode_duration_s

    @staticmethod
    def map_state_to_activity_type(state: str, is_charging: bool = False) -> str:
        """Map micro-states to human-scale semantic activity types."""
        if state in ("manual_sos", "fall_suspected", "abnormal_shock"):
            return "emergency_incident"
        if is_charging or state == "stationary_charging":
            return "charging_rest"
        if state == "stationary":
            return "stationary_work"
        if state == "walking":
            return "outdoor_walk"
        if state == "running":
            return "running_workout"
        if state == "cycling":
            return "cycling_trip"
        if state == "in_vehicle":
            return "commute_transit"
        return "general_activity"

    def segment_timeline_into_episodes(
        self,
        timeline_windows: List[Dict[str, Any]],
        *,
        base_epoch_s: float = 1774346400.0,  # 2026-09-23 10:00:00 UTC default
    ) -> List[ActivityEpisode]:
        """Aggregate 5s micro-state windows into contiguous activity episodes."""
        if not timeline_windows:
            return []

        episodes: List[ActivityEpisode] = []
        current_type: Optional[str] = None
        current_windows: List[Dict[str, Any]] = []

        def flush_episode(ep_idx: int) -> None:
            nonlocal current_windows, current_type
            if not current_windows or not current_type:
                return

            t_start = current_windows[0].get("time_offset_s", 0.0)
            t_end = current_windows[-1].get("time_offset_s", 0.0) + 5.0
            duration = max(5.0, t_end - t_start)

            confs = [w.get("confidence", 0.9) for w in current_windows]
            speeds = [w.get("speed_mps") for w in current_windows if w.get("speed_mps") is not None]

            mean_spd = float(np.mean(speeds)) if speeds else None
            est_dist = float(mean_spd * duration) if mean_spd is not None else None

            is_safety = any(w.get("is_safety_override", False) for w in current_windows)
            safety_reason = next((w.get("arbitration_reason") for w in current_windows if w.get("is_safety_override")), None)

            start_dt = datetime.fromtimestamp(base_epoch_s + t_start, tz=timezone.utc)
            end_dt = datetime.fromtimestamp(base_epoch_s + t_end, tz=timezone.utc)

            ep = ActivityEpisode(
                episode_id=f"ep-{ep_idx:04d}",
                activity_type=current_type,
                start_time_s=t_start,
                end_time_s=t_end,
                duration_seconds=duration,
                start_iso=start_dt.strftime("%H:%M:%S"),
                end_iso=end_dt.strftime("%H:%M:%S"),
                mean_confidence=round(float(np.mean(confs)), 3),
                window_count=len(current_windows),
                mean_speed_mps=round(mean_spd, 2) if mean_spd is not None else None,
                estimated_distance_meters=round(est_dist, 1) if est_dist is not None else None,
                is_safety_event=is_safety,
                safety_details=safety_reason,
            )
            episodes.append(ep)
            current_windows = []

        ep_counter = 1
        for w in timeline_windows:
            state = w.get("arbitrated_state", "stationary")
            is_chg = w.get("context", {}).get("is_charging", False)
            act_type = self.map_state_to_activity_type(state, is_chg)

            if current_type is None:
                current_type = act_type
                current_windows.append(w)
            elif act_type == current_type:
                current_windows.append(w)
            else:
                # Type changed -> flush previous episode
                flush_episode(ep_counter)
                ep_counter += 1
                current_type = act_type
                current_windows.append(w)

        if current_windows:
            flush_episode(ep_counter)

        return episodes

    def compute_daily_statistics(self, episodes: List[ActivityEpisode]) -> Dict[str, Any]:
        """Calculate overall mobility, active minutes, and safety metrics."""
        total_time_s = sum(ep.duration_seconds for ep in episodes)
        active_time_s = sum(
            ep.duration_seconds for ep in episodes
            if ep.activity_type in ("outdoor_walk", "running_workout", "cycling_trip")
        )
        sedentary_time_s = sum(
            ep.duration_seconds for ep in episodes
            if ep.activity_type == "stationary_work"
        )
        rest_time_s = sum(
            ep.duration_seconds for ep in episodes
            if ep.activity_type == "charging_rest"
        )
        transit_time_s = sum(
            ep.duration_seconds for ep in episodes
            if ep.activity_type == "commute_transit"
        )
        transit_dist_m = sum(
            ep.estimated_distance_meters or 0.0 for ep in episodes
            if ep.activity_type in ("commute_transit", "cycling_trip")
        )

        safety_episodes = [ep for ep in episodes if ep.is_safety_event]

        return {
            "total_monitored_hours": round(total_time_s / 3600.0, 2),
            "total_monitored_minutes": round(total_time_s / 60.0, 1),
            "active_minutes": round(active_time_s / 60.0, 1),
            "sedentary_minutes": round(sedentary_time_s / 60.0, 1),
            "rest_minutes": round(rest_time_s / 60.0, 1),
            "transit_minutes": round(transit_time_s / 60.0, 1),
            "transit_distance_km": round(transit_dist_m / 1000.0, 2),
            "active_percentage": round((active_time_s / total_time_s * 100.0), 1) if total_time_s > 0 else 0.0,
            "safety_incident_count": len(safety_episodes),
            "is_day_completely_safe": len(safety_episodes) == 0,
        }

    def generate_semantic_diary_markdown(
        self,
        episodes: List[ActivityEpisode],
        stats: Dict[str, Any],
        date_str: str = "2026-09-23",
    ) -> str:
        """Synthesize human-readable daily life journal and guardian card."""
        lines: List[str] = [
            f"# Ego Link Daily Life Journal — {date_str}",
            "",
            "> [!NOTE]",
            "> Generated locally on Ego Base. Zero raw audio, video, or exact coordinates were uploaded to external clouds.",
            "",
            "## 1. Guardian Peace-of-Mind Summary",
            "",
        ]

        if stats["is_day_completely_safe"]:
            lines.extend([
                "- **Safety Status**: :white_check_mark: **ALL NORMAL** (0 emergency alerts, 0 falls, 0 SOS calls)",
                f"- **Active Mobility**: {stats['active_minutes']} minutes active locomotion ({stats['active_percentage']}% of monitored day)",
                f"- **Transit & Commute**: {stats['transit_minutes']} mins (~{stats['transit_distance_km']} km)",
                f"- **Rest & Docking**: {stats['rest_minutes']} mins resting/charging",
            ])
        else:
            lines.extend([
                f"- **Safety Status**: :warning: **{stats['safety_incident_count']} SAFETY INCIDENT(S) RECORDED**",
                f"- **Active Mobility**: {stats['active_minutes']} minutes active locomotion",
            ])

        lines.extend([
            "",
            "## 2. Activity Time Allocation",
            "",
            "| Category | Duration (mins) | Ratio |",
            "|---|---|---|",
            f"| Active Exercise (Walk / Run / Bike) | {stats['active_minutes']} min | {stats['active_percentage']}% |",
            f"| Desk Work & Stationary | {stats['sedentary_minutes']} min | {round(stats['sedentary_minutes'] / max(1, stats['total_monitored_minutes']) * 100, 1)}% |",
            f"| Commute & In-Vehicle | {stats['transit_minutes']} min | {round(stats['transit_minutes'] / max(1, stats['total_monitored_minutes']) * 100, 1)}% |",
            f"| Rest & Charging Dock | {stats['rest_minutes']} min | {round(stats['rest_minutes'] / max(1, stats['total_monitored_minutes']) * 100, 1)}% |",
            "",
            "## 3. Episodic Timeline Narrative",
            "",
        ])

        for ep in episodes:
            icon = ":runner:" if ep.activity_type == "running_workout" else \
                   ":walking:" if ep.activity_type == "outdoor_walk" else \
                   ":car:" if ep.activity_type == "commute_transit" else \
                   ":bike:" if ep.activity_type == "cycling_trip" else \
                   ":battery:" if ep.activity_type == "charging_rest" else \
                   ":rotating_light:" if ep.is_safety_event else ":coffee:"

            dur_str = f"{int(ep.duration_seconds // 60)}m {int(ep.duration_seconds % 60)}s"
            dist_str = f" (~{ep.estimated_distance_meters:.0f}m)" if ep.estimated_distance_meters else ""

            if ep.is_safety_event:
                lines.append(f"### {icon} `{ep.start_iso} - {ep.end_iso}`: **SAFETY ALERT** ({ep.safety_details})")
            else:
                act_title = ep.activity_type.replace("_", " ").title()
                lines.append(f"### {icon} `{ep.start_iso} - {ep.end_iso}`: {act_title} ({dur_str}{dist_str})")

            lines.append(f"- State Confidence: {ep.mean_confidence * 100:.1f}%, Windows: {ep.window_count}")
            lines.append("")

        return "\n".join(lines)

"""Append a human/user annotation to an Ego Link M1 session recording."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pc_simulator import session_annotations


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Append an annotation to an Ego Link M1 session recording.")
    parser.add_argument("recording_dir", type=Path)
    parser.add_argument("--source-event-key", default=None)
    parser.add_argument("--target-index", type=int, default=None)
    parser.add_argument("--label", choices=sorted(session_annotations.ALLOWED_LABELS), default=None)
    parser.add_argument(
        "--annotator-type",
        choices=sorted(session_annotations.ALLOWED_ANNOTATOR_TYPES),
        default="human",
    )
    parser.add_argument("--notes", default=None)
    parser.add_argument("--created-at", default=None)
    parser.add_argument("--annotation-id", default=None)
    parser.add_argument("--training-allowed", action="store_true")
    parser.add_argument("--collection-disallowed", action="store_true")
    parser.add_argument("--raw-audio-allowed", action="store_true")
    parser.add_argument("--raw-image-allowed", action="store_true")
    parser.add_argument("--list-targets", action="store_true", help="List annotatable source_event_key targets.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.list_targets:
        targets = session_annotations.annotation_targets(args.recording_dir)
        if args.json:
            print(json.dumps({"recording_dir": str(args.recording_dir), "targets": targets}, ensure_ascii=False, indent=2))
        else:
            for target in targets:
                label = target.get("event_type") or target.get("frame_type") or target.get("source_event_type")
                print(f"{target['index']:>3} {label} seq={target.get('seq')} key={target['source_event_key']}")
        return 0
    if args.label is None:
        print("ERROR: --label is required unless --list-targets is used.", file=sys.stderr)
        return 2
    try:
        result = session_annotations.annotate_recording(
            args.recording_dir,
            source_event_key=args.source_event_key,
            target_index=args.target_index,
            label=args.label,
            created_at=args.created_at,
            annotation_id=args.annotation_id,
            annotator_type=args.annotator_type,
            notes=args.notes,
            collection_allowed=not args.collection_disallowed,
            training_allowed=args.training_allowed,
            raw_audio_allowed=args.raw_audio_allowed,
            raw_image_allowed=args.raw_image_allowed,
        )
    except session_annotations.AnnotationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        annotation = result["annotation"]
        print(
            f"Annotation {annotation['annotation_id']} label={annotation['label']} "
            f"source_event_key={annotation['source_event_key']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

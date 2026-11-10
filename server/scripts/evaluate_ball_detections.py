"""Evaluate detector JSONL candidates against reviewed labels-v1 JSONL."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from strikezone.ball.evaluation import evaluate_ball_detections


def read_jsonl(path):
    rows = []
    with path.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{number}: invalid JSON: {exc.msg}") from exc
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--detections", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--video-id", help="Default video ID for detection rows that omit video_id")
    parser.add_argument("--iou-threshold", type=float, default=0.5)
    parser.add_argument("--center-threshold-px", type=float, default=8.0)
    parser.add_argument("--include-draft", action="store_true")
    args = parser.parse_args()
    for path in (args.labels, args.detections):
        if not path.is_file():
            parser.error(f"file not found: {path}")
    if args.output.exists():
        parser.error(f"output already exists: {args.output}")
    try:
        result = evaluate_ball_detections(
            read_jsonl(args.labels), read_jsonl(args.detections),
            iou_threshold=args.iou_threshold,
            center_threshold_px=args.center_threshold_px,
            include_draft=args.include_draft,
            default_video_id=args.video_id,
        )
    except ValueError as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["metrics"], ensure_ascii=False))


if __name__ == "__main__":
    main()

"""Metrics for comparing frame-level ball labels with detector candidates."""

from __future__ import annotations

import math
from statistics import mean, median


REVIEWED_STATUSES = {"reviewed", "approved", "verified", "final"}


def _point(value, name):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{name} must contain two coordinates")
    point = tuple(float(v) for v in value)
    if not all(math.isfinite(v) for v in point):
        raise ValueError(f"{name} must contain finite coordinates")
    return point


def _box(value, name):
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError(f"{name} must contain four coordinates")
    box = tuple(float(v) for v in value)
    if not all(math.isfinite(v) for v in box) or box[0] >= box[2] or box[1] >= box[3]:
        raise ValueError(f"{name} must be a finite non-degenerate box")
    return box


def box_iou(first, second):
    first = _box(first, "first box")
    second = _box(second, "second box")
    left, top = max(first[0], second[0]), max(first[1], second[1])
    right, bottom = min(first[2], second[2]), min(first[3], second[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    first_area = (first[2] - first[0]) * (first[3] - first[1])
    second_area = (second[2] - second[0]) * (second[3] - second[1])
    union = first_area + second_area - intersection
    return intersection / union if union else 0.0


def _percentile(values, percentile):
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _key(row, default_video_id):
    frame = row.get("frame_index")
    if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
        raise ValueError("frame_index must be a nonnegative integer")
    video_id = row.get("video_id", default_video_id)
    if not isinstance(video_id, str) or not video_id:
        raise ValueError("video_id is required when no default is supplied")
    return video_id, frame


def evaluate_ball_detections(
    labels,
    detections,
    *,
    iou_threshold=0.5,
    center_threshold_px=8.0,
    include_draft=False,
    default_video_id=None,
):
    """Evaluate one annotated ball per frame against zero or more candidates.

    A candidate matches when its IoU reaches ``iou_threshold`` or its center is
    within ``center_threshold_px``. Unannotated/uncertain frames are skipped;
    reviewed ``out_of_frame`` rows are explicit negative frames.
    """
    if not 0 <= iou_threshold <= 1:
        raise ValueError("iou_threshold must be between zero and one")
    if not math.isfinite(center_threshold_px) or center_threshold_px < 0:
        raise ValueError("center_threshold_px must be a nonnegative finite number")

    detection_by_key = {}
    for row in detections:
        key = _key(row, default_video_id)
        if key in detection_by_key:
            raise ValueError(f"duplicate detection row for {key[0]} frame {key[1]}")
        candidates = row.get("candidates")
        if not isinstance(candidates, list):
            raise ValueError("detection candidates must be a list")
        detection_by_key[key] = candidates

    seen_labels = set()
    frame_results = []
    center_errors = []
    matched_ious = []
    tp = fp = fn = positives = negatives = skipped = 0

    for label in labels:
        key = _key(label, default_video_id)
        if key in seen_labels:
            raise ValueError(f"duplicate label row for {key[0]} frame {key[1]}")
        seen_labels.add(key)
        if not include_draft and label.get("review_status") not in REVIEWED_STATUSES:
            skipped += 1
            continue

        ball = label.get("ball")
        if not isinstance(ball, dict):
            raise ValueError("label ball must be an object")
        visibility = ball.get("visibility")
        candidates = detection_by_key.get(key, [])

        if visibility == "out_of_frame":
            negatives += 1
            fp += len(candidates)
            frame_results.append({
                "video_id": key[0], "frame_index": key[1], "status": "negative",
                "candidate_count": len(candidates), "false_positives": len(candidates),
            })
            continue

        if visibility not in {"visible", "occluded"}:
            skipped += 1
            continue
        if ball.get("center_xy") is None and ball.get("bbox_xyxy") is None:
            skipped += 1
            continue

        positives += 1
        truth_center = _point(ball["center_xy"], "label center_xy") if ball.get("center_xy") is not None else None
        truth_box = _box(ball.get("bbox_xyxy"), "label bbox_xyxy")
        scored = []
        for index, candidate in enumerate(candidates):
            if not isinstance(candidate, dict):
                raise ValueError("each candidate must be an object")
            candidate_center = _point(candidate["center_xy"], "candidate center_xy") if candidate.get("center_xy") is not None else None
            candidate_box = _box(candidate.get("bbox_xyxy"), "candidate bbox_xyxy")
            distance = math.dist(truth_center, candidate_center) if truth_center is not None and candidate_center is not None else None
            iou = box_iou(truth_box, candidate_box) if truth_box is not None and candidate_box is not None else None
            matched = (iou is not None and iou >= iou_threshold) or (distance is not None and distance <= center_threshold_px)
            scored.append((matched, iou if iou is not None else -1.0, -(distance if distance is not None else math.inf), index, distance, iou))

        matches = [item for item in scored if item[0]]
        if matches:
            selected = max(matches)
            selected_index, distance, iou = selected[3], selected[4], selected[5]
            tp += 1
            fp += len(candidates) - 1
            if distance is not None:
                center_errors.append(distance)
            if iou is not None:
                matched_ious.append(iou)
            status = "true_positive"
        else:
            selected_index = distance = iou = None
            fn += 1
            fp += len(candidates)
            status = "false_negative"
        frame_results.append({
            "video_id": key[0], "frame_index": key[1], "status": status,
            "candidate_count": len(candidates), "matched_candidate_index": selected_index,
            "center_error_px": distance, "iou": iou,
            "false_positives": len(candidates) - 1 if matches else len(candidates),
        })

    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else None
    return {
        "schema_version": "ball-detection-evaluation-v1",
        "thresholds": {"iou": iou_threshold, "center_distance_px": center_threshold_px},
        "counts": {
            "annotated_positive_frames": positives, "annotated_negative_frames": negatives,
            "skipped_label_frames": skipped, "true_positives": tp,
            "false_positives": fp, "false_negatives": fn,
        },
        "metrics": {
            "precision": precision, "recall": recall, "f1": f1,
            "center_error_px_mean": mean(center_errors) if center_errors else None,
            "center_error_px_median": median(center_errors) if center_errors else None,
            "center_error_px_p95": _percentile(center_errors, 0.95),
            "matched_iou_mean": mean(matched_ious) if matched_ious else None,
        },
        "frames": frame_results,
    }

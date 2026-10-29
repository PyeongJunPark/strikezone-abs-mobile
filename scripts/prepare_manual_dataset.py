"""Build analysis PNGs from explicitly reviewed frame labels and cursor positions.

No object detector, label interpolation, or automatic cursor search is used.
Run from the repository root; real annotations and generated files stay ignored.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def save_png(path: Path, pixels: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, encoded = cv2.imencode(".png", pixels)
    if not ok:
        raise ValueError(f"PNG encode failed: {path}")
    path.write_bytes(encoded.tobytes())


def read_png(path: str | Path) -> np.ndarray:
    result = cv2.imdecode(np.frombuffer(Path(path).read_bytes(), np.uint8), cv2.IMREAD_UNCHANGED)
    if result is None:
        raise ValueError(f"Cannot decode {path}")
    return result


def cursor_mask(shape: tuple, tip: list[int] | None) -> np.ndarray:
    mask = np.zeros(shape[:2], np.uint8)
    if tip is not None:
        # Arrow silhouette includes its stem; dilation covers outline/compression fringe.
        arrow = np.array([[0, 0], [0, 36], [8, 28], [14, 42],
                          [21, 39], [15, 27], [30, 27]], np.int32)
        cv2.fillPoly(mask, [arrow + np.array(tip)], 255)
        mask = cv2.dilate(mask, np.ones((7, 7), np.uint8))
    return mask


def ui_mask(shape: tuple, video: int, frame: int) -> np.ndarray:
    """Reviewed overlays for this specific selection, not a general UI detector."""
    h, w = shape[:2]
    mask = np.zeros((h, w), np.uint8)
    rectangles = {
        1: [(0, 0, w, 95)],
        2: [(808, 0, w, 105), (838, 207, w, 282), (0, 676, w, h)],
        3: [(763, 0, w, 108), (0, 677, w, h)],
        4: [(183, 0, 747, 390)],
        5: [(0, 0, 228, 170), (562, 736, 736, h), (0, 921, w, h)],
        6: [],
    }
    for x0, y0, x1, y1 in rectangles[video]:
        mask[y0:y1, x0:x1] = 255
    if video == 2 and frame in (24, 26, 28):
        cv2.circle(mask, (469, 385), 81, 255, -1)
    if video == 6:
        cv2.circle(mask, (493, 364), 81, 255, -1)
    return mask


def iter_analysis_frames(manifest_path: str | Path):
    """Yield cleaned BGR pixels, exclusion mask, and labels. Never fall back to raw.

    Coordinates retain source dimensions. Consumers must reject detections whose
    support overlaps the exclusion mask, not treat synthetic pixels as evidence.
    Paths in the manifest are repository-relative; run from the repository root.
    """
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    if manifest["default_analysis_input"] != "cursor_cleaned_png":
        raise ValueError("Expected a cursor-cleaned analysis dataset")
    for entry in manifest["frames"]:
        yield read_png(entry["image_path"]), read_png(entry["ignore_mask_path"]), entry


def build(source_manifest: Path, annotations: Path, version: str) -> Path:
    if not version or Path(version).name != version or version in (".", ".."):
        raise ValueError("Version must be a single directory name")
    source = json.loads(source_manifest.read_text(encoding="utf-8"))
    review = json.loads(annotations.read_text(encoding="utf-8"))
    if review["annotation_method"] != "assistant_visual_manual":
        raise ValueError("Explicit visual annotations required")
    samples = {s["video_id"]: s for s in source["samples"]}
    out = Path("data/derived") / version
    manifest_path = Path("data/releases") / version / "manifest.json"
    # Published/local prior versions are immutable; use a new name to rebuild.
    if manifest_path.exists():
        raise FileExistsError(f"Dataset already exists: {manifest_path}")
    for sample in samples.values():
        if digest(Path(sample["source_path"])) != sample["source_sha256"]:
            raise ValueError(f"Source hash mismatch: {sample['video_id']}")
    frames, label_files, seen = [], [], set()
    for video_id, sample in samples.items():
        selected = sorted((r for r in review["records"] if r["video_id"] == video_id),
                          key=lambda r: r["frame_index"])
        cap = cv2.VideoCapture(sample["source_path"])
        try:
            for record in selected:
                frame = record["frame_index"]
                if (video_id, frame) in seen:
                    raise ValueError("Duplicate manual frame")
                seen.add((video_id, frame))
                if frame < 0 or frame >= cap.get(cv2.CAP_PROP_FRAME_COUNT):
                    raise ValueError("Frame outside video")
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame)
                ok, raw = cap.read()
                if not ok:
                    raise ValueError(f"Decode failed: {video_id} / {frame}")
                h, w = raw.shape[:2]
                video = int(video_id[-3:])
                mask = cursor_mask(raw.shape, record["cursor_tip_xy"])
                ignored = cv2.bitwise_or(mask, ui_mask(raw.shape, video, frame))
                # OpenCV only fills the reviewed mask. Outside it is copied verbatim.
                filled = cv2.inpaint(raw, mask, 3, cv2.INPAINT_TELEA) if mask.any() else raw
                cleaned = raw.copy()
                cleaned[mask != 0] = filled[mask != 0]
                assert np.array_equal(raw[mask == 0], cleaned[mask == 0])
                paths = {key: out / video_id / folder / f"f{frame:06d}.png" for key, folder in
                         [("original_image_path", "original"), ("image_path", "analysis"),
                          ("cursor_mask_path", "cursor-mask"), ("ignore_mask_path", "ignore-mask")]}
                for key, pixels in zip(paths, [raw, cleaned, mask, ignored]):
                    save_png(paths[key], pixels)
                ball = record["ball_center_xy"]
                points = [ball] if ball else []
                points += [p["xy"] for p in record["batter_keypoints"].values() if p["xy"]]
                for x, y in points:
                    if not (0 <= x < w and 0 <= y < h):
                        raise ValueError("Point outside image")
                    if ignored[round(y), round(x)]:
                        raise ValueError("Label overlaps an exclusion mask")
                x0, y0, x1, y1 = record["batter_bbox_xyxy"]
                if not (0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h):
                    raise ValueError("Invalid batter box")
                if mask[y0:y1, x0:x1].any():
                    raise ValueError("Cursor overlaps batter: exclude/review before building")
                if ball:
                    x, y = ball
                    r = record["ball_localization_tolerance_px"]
                    if mask[max(0,y-r):y+r+1,max(0,x-r):x+r+1].any():
                        raise ValueError("Cursor overlaps ball support")
                entry = {
                    "schema_version": "labels-v1", "example_only": False,
                    "video_id": video_id, "pitch_id": video_id + "_p001",
                    "frame_index": frame, "pts_ms": cap.get(cv2.CAP_PROP_POS_MSEC),
                    "time_source": "container_pts", "image_width": w, "image_height": h,
                    "coordinate_space": "upright_unmirrored_pixels", "review_status": "draft",
                    "ball": {"visibility": record["ball_visibility"], "center_xy": ball,
                             "bbox_xyxy": None, "note": record["ball_note"]},
                    "batter": {"bbox_xyxy": record["batter_bbox_xyxy"],
                               "bbox_extent": record["batter_bbox_extent"],
                               "keypoints": record["batter_keypoints"],
                               "side_assignment": record["batter_side_note"]},
                    "plate": {"front_edge_xy": None, "status": "uncertain"},
                    "zone": {"bbox_xyxy": None, "reference_frame_index": None, "basis": None},
                    "swing": "unknown", "judgment": "unknown", "judgment_evidence": None,
                    "annotation": {"method": "assistant_visual_manual", "independent_review": False,
                                   "coverage": "selected_frames_only", "pose_quality": record["pose_quality"],
                                   "estimated_ball_tolerance_px": record["ball_localization_tolerance_px"],
                                   "estimated_pose_tolerance_px": record["pose_localization_tolerance_px"],
                                   "tolerances_are_measured_accuracy": False},
                    "cursor_cleanup": {"method": "opencv_telea_mask_only", "radius_px": 3,
                                       "cursor_present": record["cursor_tip_xy"] is not None,
                                       "modified_mask_pixels": int(np.count_nonzero(mask)),
                                       "outside_mask_identical": True, "synthetic_region_excluded": True},
                    "split": "development_only", "split_group_id": sample["split_group_id"],
                    **{key: path.as_posix() for key, path in paths.items()},
                }
                frames.append(entry)
        finally:
            cap.release()
        label_path = Path("data/labels") / version / f"{video_id}.jsonl"
        label_path.parent.mkdir(parents=True, exist_ok=True)
        label_path.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in frames
                                      if e["video_id"] == video_id), encoding="utf-8")
        label_files.append(label_path)
    if len(frames) != len(review["records"]):
        raise ValueError("Unknown source video in annotations")
    files = [annotations, *label_files]
    files += [Path(e[key]) for e in frames for key in
              ("original_image_path", "image_path", "cursor_mask_path", "ignore_mask_path")]
    manifest = {
        "schema_version": "manual-analysis-v1", "dataset_version": version,
        "parent_manifest": source_manifest.as_posix(), "source_count": len(samples),
        "status": "local_draft", "shared_location": None,
        "default_analysis_input": "cursor_cleaned_png", "labels_reference": "original_pixels",
        "not_for_training_or_final_evaluation": True,
        "frames_are_sparse_not_constant_fps_video": True,
        "source_videos": list(samples.values()), "frames": frames,
        "files": [{"path": p.as_posix(), "sha256": digest(p), "bytes": p.stat().st_size} for p in files],
    }
    write_json(manifest_path, manifest)
    return manifest_path


def validate(manifest_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for item in manifest["files"]:
        if digest(Path(item["path"])) != item["sha256"]:
            raise ValueError(f"Hash mismatch: {item['path']}")
    for sample in manifest["source_videos"]:
        if digest(Path(sample["source_path"])) != sample["source_sha256"]:
            raise ValueError("Original source modified")
    for clean, ignored, entry in iter_analysis_frames(manifest_path):
        raw = read_png(entry["original_image_path"])
        mask = read_png(entry["cursor_mask_path"])
        if not np.array_equal(raw[mask == 0], clean[mask == 0]):
            raise ValueError("Pixels outside cursor mask changed")
        if np.any((mask != 0) & (ignored == 0)):
            raise ValueError("Reconstructed pixels must be excluded")
    return {"frames": len(manifest["frames"]), "files_verified": len(manifest["files"]),
            "cursor_cleaned_frames": sum(e["cursor_cleanup"]["cursor_present"] for e in manifest["frames"]),
            "visible_ball_centers": sum(e["ball"]["center_xy"] is not None for e in manifest["frames"]),
            "visible_keypoints": sum(p["xy"] is not None for e in manifest["frames"] for p in e["batter"]["keypoints"].values()),
            "outside_cursor_masks_identical": True, "original_video_hashes_verified": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-manifest", type=Path, default=Path("data/releases/testset-v002/manifest.json"))
    parser.add_argument("--annotations", type=Path, default=Path("data/labels/testset-v003/manual-review.json"))
    parser.add_argument("--version", default="testset-v003")
    parser.add_argument("--validate", type=Path)
    args = parser.parse_args()
    result = args.validate or build(args.source_manifest, args.annotations, args.version)
    print(json.dumps(validate(result), indent=2))

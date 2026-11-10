import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from strikezone.ball.evaluation import box_iou, evaluate_ball_detections


def label(frame, visibility="visible", center=None, box=None, review="reviewed"):
    return {
        "video_id": "video-1", "frame_index": frame, "review_status": review,
        "ball": {"visibility": visibility, "center_xy": center, "bbox_xyxy": box},
    }


def detection(frame, candidates):
    return {"video_id": "video-1", "frame_index": frame, "candidates": candidates}


class BallEvaluationTests(unittest.TestCase):
    def test_iou(self):
        self.assertAlmostEqual(box_iou([0, 0, 10, 10], [5, 5, 15, 15]), 25 / 175)

    def test_counts_matches_misses_extra_candidates_and_negatives(self):
        labels = [
            label(1, center=[10, 10], box=[5, 5, 15, 15]),
            label(2, center=[30, 30], box=[25, 25, 35, 35]),
            label(3, visibility="out_of_frame"),
            label(4, center=[40, 40], review="draft"),
        ]
        detections = [
            detection(1, [
                {"center_xy": [11, 10], "bbox_xyxy": [6, 5, 16, 15]},
                {"center_xy": [100, 100], "bbox_xyxy": [95, 95, 105, 105]},
            ]),
            detection(2, []),
            detection(3, [{"center_xy": [2, 2], "bbox_xyxy": [0, 0, 4, 4]}]),
        ]
        result = evaluate_ball_detections(labels, detections)
        self.assertEqual(result["counts"], {
            "annotated_positive_frames": 2, "annotated_negative_frames": 1,
            "skipped_label_frames": 1, "true_positives": 1,
            "false_positives": 2, "false_negatives": 1,
        })
        self.assertAlmostEqual(result["metrics"]["precision"], 1 / 3)
        self.assertAlmostEqual(result["metrics"]["recall"], 1 / 2)
        self.assertEqual(result["metrics"]["center_error_px_mean"], 1.0)

    def test_center_only_match_and_include_draft(self):
        result = evaluate_ball_detections(
            [label(1, center=[5, 5], review="draft")],
            [detection(1, [{"center_xy": [8, 9]}])], include_draft=True,
        )
        self.assertEqual(result["counts"]["true_positives"], 1)
        self.assertEqual(result["metrics"]["center_error_px_mean"], 5.0)

    def test_unannotated_visibility_is_not_a_negative(self):
        result = evaluate_ball_detections(
            [label(1, visibility="uncertain", review="reviewed")],
            [detection(1, [{"center_xy": [5, 5]}])],
        )
        self.assertEqual(result["counts"]["skipped_label_frames"], 1)
        self.assertEqual(result["counts"]["false_positives"], 0)

    def test_duplicate_rows_are_rejected(self):
        row = detection(1, [])
        with self.assertRaises(ValueError):
            evaluate_ball_detections([], [row, row])

    def test_cli_writes_report(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            folder = Path(folder)
            labels_path, detections_path, output = folder / "labels.jsonl", folder / "detections.jsonl", folder / "report.json"
            labels_path.write_text(json.dumps(label(1, center=[10, 10])) + "\n", encoding="utf-8")
            detections_path.write_text(json.dumps(detection(1, [{"center_xy": [10, 10]}])) + "\n", encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(root / "scripts" / "evaluate_ball_detections.py"),
                 "--labels", str(labels_path), "--detections", str(detections_path), "--output", str(output)],
                capture_output=True, text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["counts"]["true_positives"], 1)


if __name__ == "__main__":
    unittest.main()

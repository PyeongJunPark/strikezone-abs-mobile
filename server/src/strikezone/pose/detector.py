"""Adapter for Ultralytics COCO 17-joint Pose output."""
from .zone import JOINTS

ALL_JOINTS = dict(JOINTS, left_elbow=7, right_elbow=8, left_wrist=9,
                 right_wrist=10, left_ankle=15, right_ankle=16, nose=0)


class PoseDetector:
    def __init__(self, model, device='cpu', imgsz=640):
        from ultralytics import YOLO
        self.model = YOLO(str(model))
        if self.model.task != 'pose':
            raise ValueError('A Pose model is required')
        self.device, self.imgsz = device, imgsz

    def predict(self, frame):
        result = self.model.predict(frame, device=self.device, imgsz=self.imgsz,
                                    verbose=False, save=False)[0]
        if result.keypoints is None or result.keypoints.conf is None:
            return []
        boxes = result.boxes.xyxy.cpu().tolist()
        xy = result.keypoints.xy.cpu().tolist()
        confidence = result.keypoints.conf.cpu().tolist()
        # Ultralytics returns boxes/keypoints restored to the input frame size.
        return [dict(bbox_xyxy=box, keypoints={name: dict(xy=points[index],
                    confidence=scores[index]) for name, index in ALL_JOINTS.items()})
                for box, points, scores in zip(boxes, xy, confidence)]

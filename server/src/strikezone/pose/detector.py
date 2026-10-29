"""Adapter for Ultralytics COCO 17-joint Pose output."""
from .zone import JOINTS


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
                    confidence=scores[index]) for name, index in JOINTS.items()})
                for box, points, scores in zip(boxes, xy, confidence)]

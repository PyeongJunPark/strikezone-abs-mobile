"""Pure pose selection and height calculation in original image coordinates."""
from copy import deepcopy
from math import isfinite

JOINTS = {"left_shoulder": 5, "right_shoulder": 6, "left_hip": 11,
          "right_hip": 12, "left_knee": 13, "right_knee": 14}


def valid_box(box, width, height):
    return (len(box) == 4 and all(isfinite(v) for v in box)
            and 0 <= box[0] < box[2] <= width
            and 0 <= box[1] < box[3] <= height)


def overlap(a, b):
    intersection = max(0, min(a[2], b[2])-max(a[0], b[0])) * max(
        0, min(a[3], b[3])-max(a[1], b[1]))
    union = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1])-intersection
    return intersection / union if union > 0 else 0.0


def analyze(candidates, roi, width, height, threshold=0.5, min_iou=0.2):
    """Select only an unambiguous ROI match; never substitute another joint."""
    if not 0 <= threshold <= 1 or not 0 < min_iou <= 1:
        raise ValueError('Invalid confidence or IoU threshold')
    out = dict(status='missing', confidence=None, reason='no_detection',
               batter_id=None, bbox_xyxy=None, keypoints={}, top_y=None, bottom_y=None)
    if not valid_box(roi, width, height):
        return dict(out, status='invalid', reason='invalid_roi')
    ranked = sorted([(overlap(c['bbox_xyxy'], roi), c) for c in candidates
                     if valid_box(c['bbox_xyxy'], width, height)],
                    key=lambda x: x[0], reverse=True)
    if not ranked or ranked[0][0] < min_iou:
        return out
    if len(ranked) > 1 and ranked[1][0] >= min_iou and ranked[0][0]-ranked[1][0] < 0.1:
        return dict(out, reason='ambiguous_selection')
    candidate = ranked[0][1]
    out.update(batter_id='manual-roi', bbox_xyxy=candidate['bbox_xyxy'])
    for name in JOINTS:
        point = candidate.get('keypoints', {}).get(name)
        if point is None:
            continue
        xy, conf = point['xy'], point['confidence']
        if (len(xy) == 2 and all(isfinite(v) for v in xy)
                and isfinite(conf) and 0 <= conf <= 1
                and 0 <= xy[0] < width and 0 <= xy[1] < height):
            out['keypoints'][name] = deepcopy(point)
    if len(out['keypoints']) != 6:
        return dict(out, reason='missing_keypoints')
    confidence = min(p['confidence'] for p in out['keypoints'].values())
    out['confidence'] = confidence
    if confidence < threshold:
        return dict(out, reason='low_confidence')
    ys = [sum(out['keypoints'][side+'_'+joint]['xy'][1] for side in ('left', 'right'))/2
          for joint in ('shoulder', 'hip', 'knee')]
    if not ys[0] < ys[1] < ys[2]:
        return dict(out, status='invalid', reason='invalid_geometry')
    return dict(out, status='ok', reason=None, top_y=(ys[0]+ys[1])/2, bottom_y=ys[2])


class HeightLock:
    """Height only, not a complete plate-aligned zone or pitch state machine."""
    def __init__(self):
        self.value = None

    def reset(self):
        self.value = None

    def lock(self, pose, frame_index, threshold):
        if pose['status'] != 'ok':
            return False
        if self.value is None:
            self.value = dict(top_y=pose['top_y'], bottom_y=pose['bottom_y'],
                              reference_frame_index=frame_index, method='pose-midpoint-v1',
                              keypoint_threshold=threshold)
        return True

    def snapshot(self):
        return deepcopy(self.value)

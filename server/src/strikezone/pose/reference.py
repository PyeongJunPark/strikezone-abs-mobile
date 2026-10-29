"""Reference-frame candidates from observed pose quality, not release detection."""
from copy import deepcopy
from math import isfinite


def exclude_masked_joints(candidates, mask, margin=4):
    """Reject pose evidence on reconstructed pixels or known screen overlays."""
    clean = deepcopy(candidates)
    h, w = mask.shape
    for person in clean:
        for name, point in list(person.get('keypoints', {}).items()):
            xy = point.get('xy', [])
            if len(xy) != 2 or not all(isfinite(v) for v in xy):
                del person['keypoints'][name]
                continue
            x, y = (round(v) for v in point['xy'])
            if not (0 <= x < w and 0 <= y < h) or mask[
                max(0,y-margin):min(h,y+margin+1), max(0,x-margin):min(w,x+margin+1)
            ].any():
                del person['keypoints'][name]
    return clean


def rank_references(frames, release_frame):
    """Rank valid frames strictly before a manually supplied release boundary.

    Stability is assessed only against the previous consecutive source frame.
    A repeated image is retained for scrubbing but not recommended as new evidence.
    """
    results = []
    previous = None
    for frame in sorted(frames, key=lambda f: f['frame_index']):
        pose = frame['pose']
        if frame['frame_index'] >= release_frame:
            break
        if pose['status'] == 'ok' and not frame.get('duplicate_of_previous', False):
            shift = None
            if (previous and previous['frame_index']+1 == frame['frame_index']
                    and previous['pose']['status'] == 'ok'):
                shift = max(abs(pose[k]-previous['pose'][k]) for k in ('top_y','bottom_y'))
            penalty = min(0.4, shift/frame['image_height']*5) if shift is not None else 0.15
            results.append(dict(frame_index=frame['frame_index'],
                                score=round(pose['confidence']-penalty, 6),
                                confidence=pose['confidence'], height_change_px=shift,
                                reason='valid_pose_stable_height' if shift is not None else 'valid_pose_no_neighbor',
                                release_boundary_source='manual', release_verified=False))
        previous = frame
    return sorted(results, key=lambda x: (-x['score'], x['frame_index']))

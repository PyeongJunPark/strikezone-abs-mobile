"""Conservative offline isolated-spike filter; never modifies input observations.

Requires two supporting observations on each side. Sustained turns, endpoints,
long gaps and size-only anomalies are deliberately retained for review.
"""
import math
import numpy as np


def filter_track(track, fps=30):
    points = sorted(track, key=lambda p: p['frame_index'])
    rejected = []
    removed = set()
    max_gap = max(2, round(fps * .1))
    for i in range(2, len(points)-2):
        window = points[i-2:i+3]
        if any(p.get('observed') is False or p.get('source_frame_repeated') for p in window):
            continue
        frames = np.array([p['frame_index'] for p in window], dtype=float)
        xy = np.array([p.get('center_xy', [math.nan, math.nan]) for p in window], dtype=float)
        gaps = np.diff(frames)
        if not np.isfinite(xy).all() or min(gaps) <= 0 or max(gaps) > max_gap:
            continue
        left = (xy[1]-xy[0])/gaps[0]
        right = (xy[4]-xy[3])/gaps[3]
        speed = max(np.linalg.norm(left), np.linalg.norm(right), .5)
        # The motion before and after the suspect must agree, including bridging.
        bridge = (xy[3]-xy[1])/(frames[3]-frames[1])
        if max(np.linalg.norm(left-right), np.linalg.norm(left-bridge), np.linalg.norm(right-bridge)) > .65*speed:
            continue
        predicted = xy[1]+bridge*(frames[2]-frames[1])
        residual = float(np.linalg.norm(xy[2]-predicted))
        boxes = [p.get('bbox_xyxy') for p in (window[1], window[3])]
        diameters = [max(b[2]-b[0], b[3]-b[1]) for b in boxes if b]
        threshold = max(6., 1.5*float(np.median(diameters)) if diameters else 6., 1.5*speed*max(gaps[1:3]))
        if residual <= threshold or any(j in removed for j in range(i-2, i+3)):
            continue
        removed.add(i)
        rejected.append(dict(observation=points[i], reason='isolated_position_spike', residual_px=residual,
                             threshold_px=threshold, expected_xy=predicted.tolist()))
    return dict(track=[p for i,p in enumerate(points) if i not in removed], rejected=rejected,
                input_count=len(points), removed_count=len(removed), method='isolated_spike_v1')

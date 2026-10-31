"""Size across motion, without counting the streak along motion as diameter."""
import numpy as np


def perpendicular_width(mask, motion_xy):
    direction = np.asarray(motion_xy, dtype=float)
    if direction.shape != (2,) or not np.isfinite(direction).all():
        return dict(width_px=None, reason='invalid_motion')
    speed = float(np.linalg.norm(direction))
    if speed < 1e-6:
        return dict(width_px=None, reason='unknown_motion_direction')
    ys,xs = np.where(mask>0)
    if len(xs)<3:
        return dict(width_px=None, reason='insufficient_mask')
    n = np.array([-direction[1], direction[0]])/speed
    points = np.column_stack([xs,ys]).astype(float)
    # Project all pixel corners. Do not shrink the observed mask.
    corners = np.concatenate([points+o for o in [[-.5,-.5],[-.5,.5],[.5,-.5],[.5,.5]]])
    projection = corners@n; low,high = float(projection.min()),float(projection.max())
    center = points.mean(axis=0); along = center-n*(center@n)
    return dict(width_px=high-low, normal_xy=n.tolist(),
                endpoints_xy=[(along+n*low).tolist(),(along+n*high).tolist()],
                reason='measured_perpendicular_silhouette')

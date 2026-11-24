"""Home-plate ground-plane homography from manually marked or detected corners.

Plate coordinates are centimetres on the ground plane. The origin is the
midpoint of the front edge (pitcher side); +x runs toward the front corner that
appears on the image right, and +y runs toward the catcher. The mapping is only
valid for points lying on the ground plane. It must not be used to read a 3D
position of a ball in the air (see docs/coordinates.md).
"""
import math
import numpy as np

PLATE_WIDTH_CM = 43.18                      # 17 in front edge
PLATE_SIDE_CM = 21.59                       # 8.5 in side edges
PLATE_BACK_EDGE_CM = 30.48                  # 12 in edges meeting at the tip
BALL_DIAMETER_CM = 7.33                     # official 7.29~7.48 cm, midpoint
BALL_RADIUS_CM = BALL_DIAMETER_CM / 2
_HALF = PLATE_WIDTH_CM / 2
PLATE_TIP_DEPTH_CM = PLATE_SIDE_CM + math.sqrt(PLATE_BACK_EDGE_CM**2 - _HALF**2)

# Marking order: front-left, front-right, right shoulder, back tip, left shoulder.
PLATE_CORNERS_CM = [(-_HALF, 0.0), (_HALF, 0.0), (_HALF, PLATE_SIDE_CM),
                    (0.0, PLATE_TIP_DEPTH_CM), (-_HALF, PLATE_SIDE_CM)]
FOUR_POINT_INDICES = [0, 1, 2, 4]           # pentagon without the back tip

# Reprojection limits: a ratio of the front-edge length, with a pixel floor so a
# one-pixel click error on a small, distant plate is not rejected.
WARN_ERROR_RATIO, WARN_ERROR_FLOOR_PX = .03, 1.5
MAX_ERROR_RATIO, MAX_ERROR_FLOOR_PX = .06, 3.0
MIN_FRONT_EDGE_PX = 5.0
MAX_VALID_DEPTH_CM = 150.0                  # catcher region must stay in front of the camera


def _normalise(points):
    points = np.asarray(points, float)
    centre = points.mean(axis=0)
    scale = math.sqrt(2) / max(np.sqrt(((points - centre) ** 2).sum(axis=1)).mean(), 1e-12)
    t = np.array([[scale, 0, -scale * centre[0]], [0, scale, -scale * centre[1]], [0, 0, 1]])
    return np.c_[points, np.ones(len(points))] @ t.T, t


def solve_homography(source, target):
    """Normalised DLT. Returns the 3x3 matrix mapping source -> target."""
    if len(source) != len(target) or len(source) < 4:
        raise ValueError('At least four point pairs are required')
    a, ta = _normalise(source)
    b, tb = _normalise(target)
    rows = []
    for (x, y, _), (u, v, _) in zip(a, b):
        rows.append([-x, -y, -1, 0, 0, 0, u * x, u * y, u])
        rows.append([0, 0, 0, -x, -y, -1, v * x, v * y, v])
    _, singular, vt = np.linalg.svd(np.asarray(rows))
    if singular[-2] < 1e-10:
        raise ValueError('Degenerate point configuration')
    h = np.linalg.inv(tb) @ vt[-1].reshape(3, 3) @ ta
    if abs(h[2, 2]) < 1e-12:
        raise ValueError('Degenerate homography')
    return h / h[2, 2]


def apply_homography(matrix, points):
    """Map Nx2 points; returns (mapped Nx2, homogeneous w)."""
    points = np.asarray(points, float).reshape(-1, 2)
    mapped = np.c_[points, np.ones(len(points))] @ np.asarray(matrix, float).T
    w = mapped[:, 2]
    with np.errstate(divide='ignore', invalid='ignore'):
        return mapped[:, :2] / w[:, None], w


def _signed_area(polygon):
    x, y = np.asarray(polygon, float).T
    return .5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def _is_convex(polygon):
    p = np.asarray(polygon, float)
    edges = np.roll(p, -1, axis=0) - p
    cross = edges[:, 0] * np.roll(edges[:, 1], -1) - edges[:, 1] * np.roll(edges[:, 0], -1)
    return bool(np.all(cross > 0) or np.all(cross < 0))


def _missing(reason, **extra):
    return dict(status='invalid', reason=reason, method='plate_homography_v1', matrix=None,
                inverse=None, corners_xy=None, front_edge_xy=None, px_per_cm_front=None,
                reprojection_error_px=None, warnings=[], **extra)


def fit_plate(image_points, image_size=None):
    """Fit the plate homography from 4 or 5 ordered image corners.

    Order: front-left, front-right, right shoulder, [back tip], left shoulder,
    where left/right refer to the front corners as seen in the image. With four
    points the fit is exact, so the reprojection error carries no evidence; with
    five points it measures how plate-like the marked shape is.
    """
    try:
        points = [[float(v) for v in p] for p in image_points]
    except (TypeError, ValueError):
        return _missing('invalid_points')
    if len(points) not in (4, 5) or any(len(p) != 2 or not all(math.isfinite(v) for v in p) for p in points):
        return _missing('invalid_points')
    if image_size is not None:
        w, h = image_size
        if any(not (0 <= x < w and 0 <= y < h) for x, y in points):
            return _missing('point_outside_image')
    if points[0][0] > points[1][0]:
        return _missing('front_corners_reversed')
    front = math.dist(points[0], points[1])
    if front < MIN_FRONT_EDGE_PX:
        return _missing('front_edge_too_small')
    if not _is_convex(points):
        return _missing('not_convex_or_wrong_order')
    plate = [PLATE_CORNERS_CM[i] for i in (range(5) if len(points) == 5 else FOUR_POINT_INDICES)]
    # Plate is counter-clockwise in its own frame; a consistent marking keeps one orientation.
    try:
        matrix = solve_homography(plate, points)
        inverse = np.linalg.inv(matrix)
    except (ValueError, np.linalg.LinAlgError):
        return _missing('degenerate_geometry')
    projected, w = apply_homography(matrix, PLATE_CORNERS_CM)
    depth_check, depth_w = apply_homography(matrix, [(-_HALF, MAX_VALID_DEPTH_CM), (_HALF, MAX_VALID_DEPTH_CM)])
    if np.any(w <= 0) or np.any(depth_w <= 0) or not np.all(np.isfinite(depth_check)):
        return _missing('plate_plane_crosses_horizon')
    used = projected if len(points) == 5 else projected[FOUR_POINT_INDICES]
    errors = np.linalg.norm(used - np.asarray(points), axis=1)
    max_error = float(errors.max())
    warnings = []
    if len(points) == 4:
        warnings.append('four_points_exact_fit_unverified')
    elif max_error > max(MAX_ERROR_FLOOR_PX, MAX_ERROR_RATIO * front):
        return dict(_missing('shape_not_plate_like'), reprojection_error_px=max_error)
    elif max_error > max(WARN_ERROR_FLOOR_PX, WARN_ERROR_RATIO * front):
        warnings.append('high_reprojection_error')
    return dict(status='ok', reason=None, method='plate_homography_v1',
                matrix=matrix.tolist(), inverse=inverse.tolist(),
                corners_xy=projected.tolist(), front_edge_xy=[points[0], points[1]],
                px_per_cm_front=front / PLATE_WIDTH_CM,
                reprojection_error_px=max_error, mean_error_px=float(errors.mean()),
                points_used=len(points), warnings=warnings)


def plate_to_image(calibration, points_cm):
    mapped, _ = apply_homography(calibration['matrix'], points_cm)
    return mapped.tolist()


def image_to_plate(calibration, points_xy):
    """Ground-plane lookup only (e.g. a shoe or a mark on the dirt)."""
    mapped, _ = apply_homography(calibration['inverse'], points_xy)
    return mapped.tolist()


def zone_edges(calibration, depth_cm=0.0, include_ball=True):
    """Image points where the zone side planes meet the ground at a plate depth.

    The rulebook zone is the plate width; a pitch is a strike when any part of
    the ball touches it, so the ball radius is added on both sides by default.
    """
    half = _HALF + (BALL_RADIUS_CM if include_ball else 0.0)
    left, right = plate_to_image(calibration, [(-half, depth_cm), (half, depth_cm)])
    return dict(left_xy=left, right_xy=right, half_width_cm=half, depth_cm=depth_cm,
                include_ball_radius=include_ball)


def summary(calibration):
    """JSON-friendly record for result files (matrix kept for reproducibility)."""
    keys = ('status', 'reason', 'method', 'matrix', 'corners_xy', 'front_edge_xy', 'px_per_cm_front',
            'reprojection_error_px', 'mean_error_px', 'points_used', 'warnings')
    return {k: calibration.get(k) for k in keys}

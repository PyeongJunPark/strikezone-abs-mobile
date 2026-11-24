import math
import unittest
import numpy as np
from strikezone.plate.homography import (BALL_RADIUS_CM, FOUR_POINT_INDICES, PLATE_CORNERS_CM,
                                         PLATE_TIP_DEPTH_CM, PLATE_WIDTH_CM, fit_plate,
                                         image_to_plate, plate_to_image, zone_edges)


def camera(position=(80., -1800., 160.), target=(0., 20., 0.), focal=2400., size=(1920, 1080)):
    """Pinhole camera behind the pitcher looking at the plate (plate frame, cm, z up)."""
    c = np.array(position);forward = np.array(target)-c;forward /= np.linalg.norm(forward)
    right = np.cross(forward, [0, 0, 1.]);right /= np.linalg.norm(right)
    down = np.cross(forward, right)
    rotation = np.stack([right, down, forward])
    def project(points):
        out = []
        for p in points:
            x, y, z = rotation @ (np.array([p[0], p[1], p[2] if len(p) > 2 else 0.])-c)
            out.append([focal*x/z+size[0]/2, focal*y/z+size[1]/2])
        return out
    return project


class PlateHomographyTests(unittest.TestCase):
    def setUp(self):
        self.project = camera()
        self.corners = self.project(PLATE_CORNERS_CM)

    def test_tip_depth_matches_rulebook_shape(self):
        self.assertAlmostEqual(PLATE_TIP_DEPTH_CM, 43.1, delta=.1)

    def test_five_points_from_real_projection_fit_exactly(self):
        r = fit_plate(self.corners, (1920, 1080))
        self.assertEqual(r['status'], 'ok')
        self.assertLess(r['reprojection_error_px'], 1e-6)
        self.assertEqual(r['warnings'], [])
        expected = math.dist(self.corners[0], self.corners[1])/PLATE_WIDTH_CM
        self.assertAlmostEqual(r['px_per_cm_front'], expected)

    def test_ground_points_round_trip(self):
        r = fit_plate(self.corners)
        ground = [(0, 0), (10, 30), (-25, 80), (30, -40)]
        image = plate_to_image(r, ground)
        np.testing.assert_allclose(image, self.project(ground), atol=1e-6)
        np.testing.assert_allclose(image_to_plate(r, image), ground, atol=1e-6)

    def test_zone_edges_include_ball_radius(self):
        r = fit_plate(self.corners)
        edges = zone_edges(r)
        half = PLATE_WIDTH_CM/2+BALL_RADIUS_CM
        np.testing.assert_allclose([edges['left_xy'], edges['right_xy']], self.project([(-half, 0), (half, 0)]), atol=1e-6)
        plain = zone_edges(r, include_ball=False)
        self.assertLess(plain['right_xy'][0]-plain['left_xy'][0], edges['right_xy'][0]-edges['left_xy'][0])

    def test_four_points_fit_but_are_flagged_unverified(self):
        r = fit_plate([self.corners[i] for i in FOUR_POINT_INDICES])
        self.assertEqual(r['status'], 'ok')
        self.assertIn('four_points_exact_fit_unverified', r['warnings'])
        np.testing.assert_allclose(r['corners_xy'][3], self.corners[3], atol=1e-6)

    def test_small_marking_noise_is_accepted(self):
        noisy = [[x+dx, y+dy] for (x, y), (dx, dy) in zip(self.corners, [(1, -1), (-1, 0), (0, 1), (1, 1), (-1, -1)])]
        r = fit_plate(noisy)
        self.assertEqual(r['status'], 'ok')
        self.assertGreater(r['reprojection_error_px'], 0)

    def test_non_plate_pentagon_is_rejected(self):
        # A tip shifted sideways keeps the shape convex but no plate projects to it.
        project = camera(position=(0., -400., 300.), focal=1200.)
        bad = [list(p) for p in project(PLATE_CORNERS_CM)]
        bad[3][0] += math.dist(bad[0], bad[1])*.4
        r = fit_plate(bad)
        self.assertEqual(r['status'], 'invalid')
        self.assertEqual(r['reason'], 'shape_not_plate_like')

    def test_wrong_order_is_rejected(self):
        swapped = [self.corners[i] for i in (0, 1, 4, 3, 2)]
        self.assertEqual(fit_plate(swapped)['reason'], 'not_convex_or_wrong_order')
        reversed_front = [self.corners[i] for i in (1, 0, 2, 3, 4)]
        self.assertEqual(fit_plate(reversed_front)['reason'], 'front_corners_reversed')

    def test_invalid_inputs(self):
        self.assertEqual(fit_plate([[0, 0], [1, 1]])['reason'], 'invalid_points')
        self.assertEqual(fit_plate([[0, 0], [float('nan'), 1], [2, 2], [3, 3]])['reason'], 'invalid_points')
        self.assertEqual(fit_plate(self.corners, (100, 100))['reason'], 'point_outside_image')
        tiny = [[100, 100], [102, 100], [102, 99], [101, 98], [100, 99]]
        self.assertEqual(fit_plate(tiny)['reason'], 'front_edge_too_small')

    def test_off_axis_camera_still_fits(self):
        project = camera(position=(-350., -1500., 220.))
        r = fit_plate(project(PLATE_CORNERS_CM))
        self.assertEqual(r['status'], 'ok')
        self.assertLess(r['reprojection_error_px'], 1e-6)


if __name__ == '__main__':
    unittest.main()

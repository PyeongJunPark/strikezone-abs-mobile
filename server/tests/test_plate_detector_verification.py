import unittest
import cv2
import numpy as np
from strikezone.plate.detector import locate, verify_polygon
from strikezone.plate.homography import PLATE_CORNERS_CM
from test_plate_homography import camera


def batter(x=200):
    return dict(bbox_xyxy=[x, 100, x+100, 400], keypoints={})


def projected_plate(offset=(-700, -110)):
    corners = camera(position=(0., -400., 300.), focal=1200.)(PLATE_CORNERS_CM)
    return [[x+offset[0], y+offset[1]] for x, y in corners]


class PlateVerificationTests(unittest.TestCase):
    def test_projected_plate_polygon_is_verified_in_any_vertex_order(self):
        plate = projected_plate()
        for start in range(5):
            for sequence in (plate, plate[::-1]):
                polygon = sequence[start:]+sequence[:start]
                r = verify_polygon(polygon, (800, 600))
                self.assertEqual(r['status'], 'ok')
                np.testing.assert_allclose(r['ordered_xy'], plate, atol=1e-6)

    def test_lopsided_tall_pentagon_is_not_plate(self):
        r = verify_polygon([[100, 200], [200, 200], [200, 180], [120, 100], [100, 180]])
        self.assertEqual(r['status'], 'invalid')
        self.assertEqual(verify_polygon([[0, 0], [1, 0], [1, 1], [0, 1]])['reason'], 'needs_five_vertices')

    def test_detected_plate_is_suggested_but_not_confirmed(self):
        im = np.zeros((600, 800, 3), np.uint8);mask = np.zeros((600, 800), np.uint8)
        cv2.fillConvexPoly(im, np.round(projected_plate()).astype(np.int32), (255, 255, 255))
        plate = locate(im, mask, batter())
        self.assertNotEqual(plate['status'], 'ok')
        self.assertIsNone(plate['front_edge_xy'])
        self.assertEqual(plate['reason'], 'verified_candidate_needs_confirmation')
        np.testing.assert_allclose(plate['suggested_corners_xy'], projected_plate(), atol=3)

    def test_white_bar_is_not_suggested(self):
        im = np.zeros((600, 800, 3), np.uint8);mask = np.zeros((600, 800), np.uint8)
        cv2.rectangle(im, (200, 420), (300, 435), (255, 255, 255), -1)
        plate = locate(im, mask, batter())
        self.assertIsNone(plate['suggested_corners_xy'])


if __name__ == '__main__':
    unittest.main()

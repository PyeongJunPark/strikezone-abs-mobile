import unittest
from strikezone.judgment.video_pipeline import resolve_plate, validate_config
from strikezone.plate.homography import PLATE_CORNERS_CM
from test_plate_homography import camera


class PipelinePlateCornerTests(unittest.TestCase):
    def setUp(self):
        self.meta=dict(width=1920,height=1080,frames=300,fps=30)
        self.corners=camera(position=(0.,-400.,300.),focal=1200.)(PLATE_CORNERS_CM)

    def test_without_corners_keeps_two_point_flow(self):
        config=dict(plate_points=[[900,800],[1000,800]],trigger_frame=100)
        self.assertIsNone(resolve_plate(config,self.meta))
        self.assertEqual(config['plate_points'],[[900,800],[1000,800]])

    def test_corners_replace_front_edge(self):
        config=dict(plate_corners=self.corners,trigger_frame=100)
        calibration=resolve_plate(config,self.meta)
        self.assertEqual(calibration['status'],'ok')
        self.assertEqual(config['plate_points'],[self.corners[0],self.corners[1]])
        validate_config(config,self.meta)

    def test_bad_corner_order_reports_korean_message(self):
        config=dict(plate_corners=[self.corners[i] for i in (0,1,4,3,2)],trigger_frame=100)
        with self.assertRaisesRegex(ValueError,'꼭짓점 순서'):resolve_plate(config,self.meta)

    def test_non_list_corners_rejected(self):
        with self.assertRaises(ValueError):resolve_plate(dict(plate_corners='x'),self.meta)


if __name__ == '__main__':
    unittest.main()

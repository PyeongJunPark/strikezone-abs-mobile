import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('track_ball', Path(__file__).resolve().parents[1]/'scripts/track_ball.py')
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)

class BallCliTests(unittest.TestCase):
    def test_crop_restores_source_coordinates(self):
        candidate = cli.restore_candidate([10,20,16,28], .8, [450,350,1250,900])
        self.assertEqual(candidate['bbox_xyxy'], [460,370,466,378])
        self.assertEqual(candidate['center_xy'], [463,374])

    def test_invalid_calibration_rejected(self):
        base = dict(trigger_frame=0, pitcher_box=[0,0,30,30], plate_region=[40,40,60,60])
        cli.validate_config(base, 100, 100)
        for patch in ({'trigger_frame': -1}, {'trigger_frame': True},
                      {'crop': [0,0,101,100]}, {'pitcher_box': [0,0,float('nan'),30]},
                      {'crop': [0.5,0,10,10]}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                cli.validate_config(dict(base, **patch), 100, 100)

if __name__ == '__main__':
    unittest.main()

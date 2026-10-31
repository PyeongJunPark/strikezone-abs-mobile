import unittest
from strikezone.judgment.video_pipeline import validate_config


class VideoConfigTests(unittest.TestCase):
    def setUp(self):
        self.meta=dict(width=1920,height=1080,frames=300,fps=30)
        self.config=dict(plate_points=[[900,800],[1000,800]],trigger_frame=100)
    def test_valid_config(self):validate_config(self.config,self.meta)
    def test_outside_frame_rejected(self):
        self.config['trigger_frame']=300
        with self.assertRaises(ValueError):validate_config(self.config,self.meta)
    def test_tiny_plate_rejected(self):
        self.config['plate_points']=[[900,800],[901,800]]
        with self.assertRaises(ValueError):validate_config(self.config,self.meta)
    def test_invalid_manual_height_rejected(self):
        self.config['manual_height']=[800,700]
        with self.assertRaises(ValueError):validate_config(self.config,self.meta)
    def test_nonfinite_rejected(self):
        self.config['plate_points'][0][0]=float('nan')
        with self.assertRaises(ValueError):validate_config(self.config,self.meta)
    def test_fallback_height_validated(self):
        self.config['fallback_height']=[400,700];validate_config(self.config,self.meta)
        self.config['fallback_height']=[700,400]
        with self.assertRaises(ValueError):validate_config(self.config,self.meta)
    def test_fallback_height_outside_image_rejected(self):
        self.config['fallback_height']=[400,1200]
        with self.assertRaises(ValueError):validate_config(self.config,self.meta)

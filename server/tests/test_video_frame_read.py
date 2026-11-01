import unittest
from unittest.mock import patch
from strikezone.judgment.video_pipeline import read_video_frames, selected_overlay_frame

class Capture:
    def __init__(self, count=8):self.index=-1;self.count=count;self.released=False
    def set(self,*args):raise AssertionError('Random frame seek is not allowed')
    def grab(self):self.index+=1;return self.index<self.count
    def retrieve(self):return True,self.index
    def release(self):self.released=True

class FrameReadTests(unittest.TestCase):
    def test_selected_marker_never_appears_a_frame_early(self):
        self.assertEqual(selected_overlay_frame({'frame_index':2969,'source':'observed'}),2969)
        self.assertEqual(selected_overlay_frame({'frame_index':2972.59,'source':'predicted'}),2973)
        self.assertIsNone(selected_overlay_frame(None))

    def test_original_indices_are_preserved_without_random_seek(self):
        cap=Capture()
        with patch('strikezone.judgment.video_pipeline.cv2.VideoCapture',return_value=cap):
            self.assertEqual(read_video_frames('phone.mp4',4,7),{4:4,5:5,6:6})
        self.assertTrue(cap.released)

    def test_early_end_fails_and_releases_capture(self):
        cap=Capture(3)
        with patch('strikezone.judgment.video_pipeline.cv2.VideoCapture',return_value=cap):
            with self.assertRaises(ValueError):read_video_frames('phone.mp4',4,7)
        self.assertTrue(cap.released)

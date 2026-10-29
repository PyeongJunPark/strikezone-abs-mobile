import unittest
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from strikezone.pose.pitch_start import PitchStartDetector,auto_reference


class StartTests(unittest.TestCase):
    def setUp(self):
        self.base=np.zeros((100,120,3),np.uint8)
        self.mask=np.zeros((100,120),np.uint8)
        self.detector=PitchStartDetector([10,10,60,90],[80,10,110,90])

    def arm(self):
        for i in range(4):self.detector.update(self.base,self.mask,i)

    def moving(self,x):
        im=self.base.copy();im[20:60,x:x+20]=255;return im

    def test_still_video_never_fires(self):
        for i in range(20):self.assertIsNone(self.detector.update(self.base,self.mask,i)['event'])

    def test_confirmation_is_causal_once_and_not_release(self):
        self.arm();r=self.detector.update(self.moving(15),self.mask,4);self.assertIsNone(r['event'])
        r=self.detector.update(self.moving(30),self.mask,5)
        self.assertEqual(r['event']['onset_frame_index'],4)
        self.assertEqual(r['event']['confirmed_frame_index'],5)
        self.assertFalse(r['event']['ball_release_confirmed'])
        self.assertIsNone(self.detector.update(self.moving(20),self.mask,6)['event'])

    def test_single_flash_is_rejected(self):
        self.arm();self.detector.update(self.moving(15),self.mask,4)
        self.assertIsNone(self.detector.update(self.base,self.mask,5)['event'])
        self.assertIsNone(self.detector.event)

    def test_background_change_and_gap_interrupt(self):
        self.arm();r=self.detector.update(np.full_like(self.base,255),self.mask,4)
        self.assertEqual(r['state'],'interrupted');self.assertIsNone(r['event'])
        self.setUp();self.arm();r=self.detector.update(self.moving(15),self.mask,8)
        self.assertEqual(r['reason'],'frame_gap_or_size_change')

    def test_hidden_motion_cannot_trigger(self):
        self.mask[10:90,10:60]=255;self.arm()
        self.assertEqual(self.detector.state,'interrupted')

    def test_reference_is_valid_recent_and_strictly_before_onset(self):
        frames=[dict(frame_index=i,pose={'status':'ok'}) for i in (1,3,4,5)]
        event={'onset_frame_index':4,'confirmed_frame_index':5}
        self.assertEqual(auto_reference(frames,event)['reference_frame_index'],3)
        self.assertEqual(auto_reference(frames,{'onset_frame_index':30})['reason'],'no_valid_pre_start_pose')
        self.assertEqual(auto_reference([],None)['reason'],'no_pitch_start_candidate')


if __name__=='__main__':unittest.main()

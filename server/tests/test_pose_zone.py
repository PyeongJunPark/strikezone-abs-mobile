import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from strikezone.pose.zone import analyze, HeightLock


class PoseTests(unittest.TestCase):
    def setUp(self):
        self.person = {'bbox_xyxy':[100,100,300,600], 'keypoints':{
            side+'_'+joint:{'xy':[x,y], 'confidence':0.9}
            for side,x in [('left',150),('right',250)]
            for joint,y in [('shoulder',200),('hip',400),('knee',550)]}}

    def run_pose(self, people=None):
        return analyze(people if people is not None else [self.person],
                       [100,100,300,600],800,800)

    def test_formula_and_distractor(self):
        other=copy.deepcopy(self.person); other['bbox_xyxy']=[400,100,700,700]
        p=self.run_pose([other,self.person])
        self.assertEqual((p['top_y'],p['bottom_y']),(300,550))

    def test_missing_and_low_confidence(self):
        self.person['keypoints']['left_knee']['confidence']=0.49
        self.assertIsNone(self.run_pose()['top_y'])
        del self.person['keypoints']['left_knee']
        self.assertEqual(self.run_pose()['reason'],'missing_keypoints')

    def test_invalid_geometry(self):
        self.person['keypoints']['left_knee']['xy'][1]=100
        self.assertEqual(self.run_pose()['status'],'invalid')

    def test_nan_and_outside(self):
        for value in [float('nan'),float('inf'),-1,800]:
            self.person['keypoints']['left_knee']['xy'][0]=value
            self.assertEqual(self.run_pose()['reason'],'missing_keypoints')

    def test_ambiguity_and_missing(self):
        self.assertEqual(self.run_pose([self.person,self.person])['reason'],'ambiguous_selection')
        self.assertEqual(self.run_pose([])['status'],'missing')

    def test_lock_reset(self):
        lock=HeightLock()
        self.assertFalse(lock.lock(self.run_pose([]),0,0.5))
        pose=self.run_pose(); self.assertTrue(lock.lock(pose,3,0.5))
        pose['top_y']=50
        lock.lock(pose,4,0.5)
        self.assertEqual(lock.snapshot()['top_y'],300)
        snapshot=lock.snapshot(); snapshot['top_y']=1
        self.assertEqual(lock.snapshot()['reference_frame_index'],3)
        lock.reset(); self.assertIsNone(lock.snapshot())


if __name__=='__main__':
    unittest.main()

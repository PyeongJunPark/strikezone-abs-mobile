import unittest
from strikezone.judgment.pose_session import PoseZoneSession

class PoseSessionTests(unittest.TestCase):
 def pose(self,lift=0,offset=0):
  ys={'left_shoulder':20,'right_shoulder':20,'left_hip':40,'right_hip':40,'left_knee':80-lift,'right_knee':80}
  return dict(status='ok',top_y=30+offset,bottom_y=80-lift/2+offset,keypoints={n:dict(xy=[20,y+offset],confidence=.9) for n,y in ys.items()})
 def ready(self,s):
  for f in [0,3,6,9]:s.update(f,self.pose(),'a')
 def test_requires_stable_duration(self):
  s=PoseZoneSession([10,30],30);s.update(0,self.pose(),'a');self.assertIsNone(s.zone)
  for f in [3,6,9]:s.update(f,self.pose(),'a')
  self.assertEqual(s.snapshot()['phase'],'stable_ready')
 def test_leg_lift_locks_pre_motion_height(self):
  s=PoseZoneSession([10,30],30);self.ready(s);s.update(12,self.pose(20),'a')
  self.assertEqual(s.snapshot()['phase'],'motion_pending');self.assertEqual(s.zone,[10,30,30,80])
  s.update(15,self.pose(25),'a');self.assertEqual(s.snapshot()['lock_reason'],'sustained_pose_motion')
  s.freeze(20);s.update(21,self.pose(35),'a');self.assertEqual(s.zone,[10,30,30,80])
 def test_single_bad_pose_does_not_lock(self):
  s=PoseZoneSession([10,30],30);self.ready(s);s.update(12,self.pose(20),'a');s.update(15,self.pose(),'a')
  self.assertIsNone(s.lock_frame)
 def test_identity_change_reacquires(self):
  s=PoseZoneSession([10,30],30);self.ready(s);s.update(12,self.pose(offset=10),'b');self.assertIsNone(s.zone)
 def test_stale_unlocked_pose_invalid(self):
  s=PoseZoneSession([10,30],30);self.ready(s);self.assertIsNone(s.freeze(30)['zone'])
 def test_missing_stance_not_invented(self):
  s=PoseZoneSession([10,30],30);s.update(0,{'status':'missing'},None);self.assertIsNone(s.freeze(1)['zone'])
 def test_gap_breaks_stability(self):
  s=PoseZoneSession([10,30],30)
  for f in [0,3,6,20]:s.update(f,self.pose(),'a')
  self.assertIsNone(s.zone)
 def test_scale_invariant_motion(self):
  s=PoseZoneSession([10,30],30)
  for f,lift in [(0,0),(3,0),(6,0),(9,0),(12,20),(15,20)]:
   p=self.pose(lift);p['top_y']*=3;p['bottom_y']*=3
   for k in p['keypoints'].values():k['xy']=[x*3 for x in k['xy']]
   s.update(f,p,'a')
  self.assertEqual(s.lock_reason,'sustained_pose_motion')
 def test_explicit_reference(self):
  s=PoseZoneSession([10,30],30);s.update(0,self.pose(),'a',explicit_reference=True)
  self.assertEqual(s.freeze(100)['zone'],[10,30,30,80])
 def test_manual_height(self):
  s=PoseZoneSession([10,30],30,[20,80]);s.update(0,{},None);self.assertEqual(s.freeze(1)['height_source'],'manual')
 def test_frame_order(self):
  s=PoseZoneSession([10,30],30);s.update(5,{},None)
  with self.assertRaises(ValueError):s.update(4,{},None)

 def test_explicit_reference_overrides_earlier_motion_lock(self):
  s=PoseZoneSession([10,30],30);self.ready(s);s.update(12,self.pose(20),'a');s.update(15,self.pose(20),'a')
  s.update(18,self.pose(offset=2),'a',explicit_reference=True)
  self.assertEqual(s.zone,[10,32,30,82]);self.assertEqual(s.lock_reason,'manual_reference_frame')
 def test_invalid_explicit_reference_does_not_use_old_zone(self):
  s=PoseZoneSession([10,30],30);self.ready(s);s.update(12,{'status':'missing'},None,explicit_reference=True)
  self.assertIsNone(s.freeze(14)['zone'])

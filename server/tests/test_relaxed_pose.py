import unittest
from strikezone.judgment.pose_session import PoseZoneSession
from strikezone.pose.selector import plate_role_rejection,BatterSelector

def pose():
    ys={'left_shoulder':20,'right_shoulder':20,'left_hip':40,'right_hip':40,'left_knee':80,'right_knee':80}
    return dict(status='ok',top_y=30,bottom_y=80,keypoints={n:dict(xy=[20,y],confidence=.9) for n,y in ys.items()})

class RelaxedTests(unittest.TestCase):
    def test_sparse_same_batter_survives_missing_frames(self):
        s=PoseZoneSession([10,30],30,relaxed=True,fallback_height=[10,90])
        s.update(0,pose(),'a');s.update(3,{},None);s.update(20,pose(),'a')
        self.assertEqual(s.freeze(25)['height_source'],'pose_median')
        self.assertEqual(s.zone,[10,30,30,80])
    def test_no_batter_uses_only_supplied_fallback(self):
        s=PoseZoneSession([10,30],30,relaxed=True,fallback_height=[20,90])
        self.assertEqual(s.freeze(10)['height_source'],'manual_fallback')
        self.assertIsNone(PoseZoneSession([10,30],30,relaxed=True).freeze(10)['zone'])
    def test_median_never_mixes_identities(self):
        s=PoseZoneSession([10,30],30,relaxed=True,fallback_height=[20,90])
        s.update(0,pose(),'a');s.update(3,pose(),'b')
        self.assertEqual(s.freeze(4)['height_source'],'manual_fallback')
    def test_stable_zone_retained_despite_short_dropout(self):
        s=PoseZoneSession([10,30],30,relaxed=True)
        for f in [0,3,6]:s.update(f,pose(),'a')
        s.update(25,{},None);self.assertEqual(s.freeze(30)['zone'],[10,30,30,80])
    def test_invalid_explicit_reference_stays_invalid(self):
        s=PoseZoneSession([10,30],30,relaxed=True,fallback_height=[20,90])
        s.update(1,{},None,explicit_reference=True);self.assertIsNone(s.freeze(3)['zone'])
    def test_foreground_pitcher_and_center_umpire_rejected(self):
        plate=[100,120,200]
        pitcher=dict(bbox_xyxy=[130,0,180,195],keypoints={})
        umpire=dict(bbox_xyxy=[95,100,125,200],keypoints={})
        batter=dict(bbox_xyxy=[135,100,165,200],keypoints={})
        self.assertEqual(plate_role_rejection(pitcher,plate),'foreground_scale')
        self.assertEqual(plate_role_rejection(umpire,plate),'receiver_center_lane')
        self.assertIsNone(plate_role_rejection(batter,plate))
    def test_continuity_cannot_override_role_rejection(self):
        s=BatterSelector();s.previous=[95,100,125,200]
        r=s.select([dict(bbox_xyxy=s.previous,keypoints={})],1,300,300,plate=[100,120,200])
        self.assertIsNone(r['candidate']);self.assertEqual(r['rejected_candidates'][0]['reason'],'receiver_center_lane')
    def test_wide_batting_stance_is_not_foreground_pitcher(self):
        batter=dict(bbox_xyxy=[340,1330,409,1488],keypoints={})
        self.assertIsNone(plate_role_rejection(batter,[474.5,508,1500]))

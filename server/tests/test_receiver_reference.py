import unittest
from strikezone.judgment.receiver_reference import reference_call

def pts(coords):return [dict(frame_index=f,center_xy=[x,y],observed=True) for f,x,y in coords]
class ReceiverTests(unittest.TestCase):
 def test_first_exit_precedes_later_rebound(self):
  tr=pts([(0,0,50),(1,50,50),(2,95,50),(3,125,50),(4,145,50),(5,160,60),(6,175,70),(7,160,80),(8,145,90)])
  r=reference_call(tr,[90,40,110,70]);self.assertEqual(r['reason'],'first_receiver_passage_end');self.assertEqual(r['position']['frame_index'],3);self.assertFalse(r['confirmed_plate_crossing'])
 def test_gap_turn_precedes_later_bounce(self):
  tr=pts([(0,100,10),(1,101,20),(2,102,30),(8,104,45),(9,105,40),(10,106,35),(11,107,40),(12,108,50),(13,109,60),(14,110,50),(15,111,40)])
  r=reference_call(tr,[90,40,110,70]);self.assertEqual(r['reason'],'direction_change_across_gap');self.assertEqual(r['position']['frame_index'],2);self.assertEqual(r['event']['uncertainty_interval'],[2,8])
 def test_disappearance_uses_last_observed_not_forecast(self):
  tr=pts([(0,10,15),(1,30,20),(2,50,30),(3,70,40),(4,95,50)]);ds=[dict(frame_index=f,candidates=[]) for f in range(5,8)]
  r=reference_call(tr,[90,40,110,70],detections=ds,end_frame=10)
  self.assertEqual(r['preview'],'STRIKE_ESTIMATE');self.assertEqual(r['position']['frame_index'],4);self.assertEqual(r['reason'],'disappearance_near_receiver');self.assertFalse(r['confirmed_catch'])
 def test_no_event_falls_back_with_low_confidence(self):
  r=reference_call(pts([(0,0,0),(1,30,30),(2,50,50)]),[90,40,110,70])
  self.assertEqual(r['preview'],'BALL_ESTIMATE');self.assertEqual(r['confidence'],'low');self.assertEqual(r['reason'],'closest_observation_to_receiver')
 def test_boundary_counts_as_strike(self):
  r=reference_call(pts([(0,89,50)]),[90,40,110,70]);self.assertEqual(r['preview'],'STRIKE_ESTIMATE');self.assertTrue(r['boundary_hit'])
 def test_empty_observations(self):
  self.assertEqual(reference_call([],[90,40,110,70])['preview'],'UNJUDGEABLE')
 def test_direction_change_interpolates_one_frame_before(self):
  tr=pts([(0,50,10),(1,65,20),(3,95,40),(4,80,50),(5,65,60)])
  r=reference_call(tr,[90,30,110,70]);self.assertEqual(r['reason'],'sustained_trajectory_change');self.assertEqual(r['position']['frame_index'],2);self.assertEqual(r['position']['source'],'interpolated');self.assertIn('bounce_or_deflection_possible',r['warnings'])
 def test_disconnected_stationary_tail_cannot_select_zone_point(self):
  tr=pts([(0,80,60),(1,85,68),(2,90,76),(6,45,84),(8,45,85),(9,45,85)])
  r=reference_call(tr,[40,70,60,95]);self.assertEqual(r['reason'],'flight_track_discontinuity');self.assertEqual(r['position']['frame_index'],2);self.assertEqual(r['preview'],'BALL_ESTIMATE');self.assertFalse(r['event']['confirmed_contact'])
 def test_turn_outside_receiver_is_used_before_nearest(self):
  tr=pts([(0,0,0),(1,10,10),(2,20,20),(3,30,10),(4,40,0)])
  r=reference_call(tr,[100,100,120,140]);self.assertEqual(r['reason'],'sustained_trajectory_change');self.assertEqual(r['position']['frame_index'],1)
 def test_smooth_flight_has_no_turn(self):
  r=reference_call(pts([(i,10*i,i*i) for i in range(7)]),[100,100,120,140]);self.assertIsNone(r['event'])
 def test_unobserved_points_not_treated_as_evidence(self):
  r=reference_call([dict(frame_index=1,center_xy=[100,50],observed=False)],[90,40,110,70]);self.assertEqual(r['preview'],'UNJUDGEABLE')
if __name__=='__main__':unittest.main()

import unittest
from unittest.mock import patch
from strikezone.judgment.receiver_reference import prioritized_reference_call
class PriorityTests(unittest.TestCase):
 def call(self,track,rows=None):return prioritized_reference_call(track,[90,40,110,70],size_rows=rows,image_size=(200,150))
 def track(self,coords):return [dict(frame_index=i,center_xy=p,observed=True) for i,p in enumerate(coords)]
 def test_observation_precedes_bad_prediction(self):
  with patch('strikezone.ball.size_forecast.forecast',side_effect=AssertionError('must not forecast')):
   r=self.call(self.track([[10,10],[40,20],[70,30],[100,50]]));self.assertEqual(r['decision_source'],'observed_receiver_proximity');self.assertEqual(r['preview'],'STRIKE_ESTIMATE')
 def test_offscreen_prediction_is_low_confidence_ball(self):
  model=dict(status='unstable_forecast',candidate=dict(frame=10,center_xy=[250,300]),flags=['unstable'])
  with patch('strikezone.ball.size_forecast.forecast',return_value=model):
   r=self.call(self.track([[0,0],[5,5],[10,10]]));self.assertEqual(r['reason'],'offscreen_prediction');self.assertEqual(r['preview'],'BALL_ESTIMATE');self.assertEqual(r['confidence'],'low');self.assertFalse(r['confirmed_plate_crossing'])
 def test_prediction_failure_falls_back(self):
  r=self.call(self.track([[0,0],[5,5],[10,10]]));self.assertEqual(r['decision_source'],'nearest_observation');self.assertEqual(r['position']['source'],'observed')
 def test_no_points_no_prediction(self):
  self.assertEqual(self.call([])['decision_source'],'unavailable')
if __name__=='__main__':unittest.main()

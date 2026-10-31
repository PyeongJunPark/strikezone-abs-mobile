import unittest
from strikezone.ball.size_forecast import forecast_width_updates,predict

def rows(n):
 return [dict(frame=i,horizontal_width_px=1/(.05+.1*i/30),diameter_px=999,center_xy=[(20+5*i/30)/(.05+.1*i/30),(10+2*i/30+3*(i/30)**2)/(.05+.1*i/30)]) for i in range(n)]

class WidthForecastTests(unittest.TestCase):
 def test_distant_candidate_withheld_not_clamped(self):
  m=forecast_width_updates(rows(5),50)[-1]
  self.assertIsNone(m['candidate']);self.assertIn('outside_supported_prediction_window',m['rejection_reasons'])
  self.assertGreater(m['rejected_candidate']['frame'],m['prediction_frame_bounds'][1]);self.assertIsNone(predict(m,m['rejected_candidate']['frame']))
 def test_new_observations_allow_supported_estimate(self):
  m=forecast_width_updates(rows(40),50,image_size=(1920,1080))[-1]
  self.assertIsNotNone(m['candidate']);self.assertEqual(m['size_metric'],'mask_horizontal_width_px')
  changed=rows(40)
  for r in changed:r['diameter_px']=1
  self.assertEqual(m,forecast_width_updates(changed,50,image_size=(1920,1080))[-1])
 def test_missing_width_never_falls_back_to_circle(self):
  r=rows(5)
  for x in r:x['horizontal_width_px']=None
  self.assertEqual(forecast_width_updates(r,50),[])
 def test_offscreen_candidate_is_diagnostic_only(self):
  m=forecast_width_updates(rows(40),50,image_size=(10,10))[-1]
  self.assertIsNone(m['candidate']);self.assertIn('predicted_position_outside_image',m['rejection_reasons'])

if __name__=='__main__':unittest.main()

import unittest
from strikezone.ball.track_filter import filter_track
class FilterTests(unittest.TestCase):
 def points(self,xy):return [dict(frame_index=i,center_xy=p,bbox_xyxy=[p[0]-2,p[1]-2,p[0]+2,p[1]+2]) for i,p in enumerate(xy)]
 def test_spike_removed_without_mutation(self):
  p=self.points([[0,0],[10,0],[20,50],[30,0],[40,0]])
  r=filter_track(p);self.assertEqual(r['removed_count'],1);self.assertEqual(len(p),5);self.assertEqual(r['rejected'][0]['observation']['frame_index'],2)
 def test_sustained_turn_preserved(self):
  self.assertEqual(filter_track(self.points([[0,0],[10,0],[20,0],[20,10],[20,20]]))['removed_count'],0)
 def test_smooth_curve_preserved(self):
  self.assertEqual(filter_track(self.points([[i*10,i*i] for i in range(10)]))['removed_count'],0)
 def test_gap_preserved(self):
  p=self.points([[0,0],[10,0],[20,50],[30,0],[40,0]]);p[3]['frame_index']=30;p[4]['frame_index']=31
  self.assertEqual(filter_track(p)['removed_count'],0)
 def test_endpoint_preserved(self):
  self.assertEqual(filter_track(self.points([[0,90],[10,0],[20,0],[30,0],[40,0]]))['removed_count'],0)

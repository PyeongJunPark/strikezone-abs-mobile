import unittest
from strikezone.ball.track_filter import filter_track
from strikezone.ball.learned_trajectory import link,Config

def points(xy):return [dict(frame_index=i,center_xy=list(p),bbox_xyxy=[p[0]-3,p[1]-3,p[0]+3,p[1]+3],confidence=.9) for i,p in enumerate(xy)]

class StationaryTests(unittest.TestCase):
    def test_static_jitter_rejected_without_mutation(self):
        p=points([(100+i%2,100) for i in range(12)])
        self.assertEqual(filter_track(p)['removed_count'],12);self.assertEqual(len(p),12)
    def test_slow_continuous_motion_not_stationary(self):
        p=points([(100+i,100) for i in range(20)])
        self.assertEqual(filter_track(p)['removed_count'],0)
    def test_catch_slowdown_is_preserved(self):
        p=points([(i*10,100) for i in range(6)]+[(60,100)]*12)
        self.assertEqual(filter_track(p)['removed_count'],0)
    def test_backward_jump_to_static_object_detaches(self):
        p=points([(i*10,100) for i in range(6)]+[(20,100)]*12)
        r=filter_track(p);self.assertEqual(r['removed_count'],12);self.assertEqual(r['track'][-1]['frame_index'],5)
    def test_prefix_does_not_seed_flight(self):
        p=points([(0,100)]*10+[(i*10,100) for i in range(1,8)])
        self.assertEqual(filter_track(p)['track'][0]['frame_index'],10)
    def test_missing_or_repeated_frames_not_static_evidence(self):
        p=points([(100,100)]*8)
        for q in p:q['source_frame_repeated']=True
        self.assertEqual(filter_track(p)['removed_count'],0)
    def test_link_near_static_object_does_not_inherit_id(self):
        p=points([(100,100)]*8+[(110,100),(120,100),(130,100)])
        tracks=link([dict(frame_index=q['frame_index'],candidates=[q]) for q in p],Config())
        self.assertEqual(len(tracks),1);self.assertEqual(tracks[0][0]['frame_index'],8)

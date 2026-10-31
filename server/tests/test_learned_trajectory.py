import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from strikezone.ball.learned_trajectory import Config, analyze, endpoint, estimate_position, compare_zone


def point(i,x,y=100):
    return dict(frame_index=i,center_xy=[x,y],bbox_xyxy=[x-3,y-3,x+3,y+3],confidence=.9)


class TrajectoryTests(unittest.TestCase):
    def test_static_ball_does_not_start(self):
        rows=[dict(frame_index=i,candidates=[point(i,50)]) for i in range(20)]
        self.assertEqual(analyze(rows)['status'],'no_moving_ball_track')

    def test_bounce_without_pitch_start(self):
        track=[point(i,50+12*i,100) for i in range(10)]
        track += [point(i,158-10*(i-9),100+6*(i-9)) for i in range(10,15)]
        e=endpoint(track,Config())
        self.assertEqual(e['status'],'candidate')
        self.assertEqual(e['frame_index'],9)
        self.assertFalse(e['confirmed_catch'])

    def test_stop(self):
        track=[point(i,50+12*i) for i in range(10)]+[point(i,158) for i in range(10,14)]
        self.assertEqual(endpoint(track,Config())['reason'],'abrupt_deceleration')

    def test_loss_alone_not_catch(self):
        self.assertEqual(endpoint([point(i,50+12*i) for i in range(10)],Config())['status'],'missing')

    def test_duplicate_video_frames_not_a_stop(self):
        track=[point(i,50+12*i) for i in range(10)]
        track += [dict(point(i,158),source_frame_repeated=True) for i in range(10,13)]
        track += [point(i,158+12*(i-12)) for i in range(13,17)]
        self.assertEqual(endpoint(track,Config())['status'],'missing')

    def test_occlusion_uses_both_sides(self):
        track=[point(i,10*i) for i in [0,1,2,3,7,8,9]]
        p=estimate_position(track,5)
        self.assertEqual(p['center_xy'],[50.,100.])
        self.assertEqual(p['source'],'interpolated')
        self.assertFalse(p['observed'])
        self.assertEqual(p['support_frames'],[3,7])

    def test_extrapolation_short_only(self):
        track=[point(i,10*i) for i in range(6)]
        self.assertEqual(estimate_position(track,7)['source'],'extrapolated')
        self.assertIsNone(estimate_position(track,10)['center_xy'])

    def test_long_gap_not_fabricated(self):
        self.assertIsNone(estimate_position([point(0,0),point(20,200)],10)['center_xy'])

    def test_estimate_near_zone_edge_held(self):
        p=dict(center_xy=[50,100],source='interpolated',uncertainty_px=10)
        self.assertEqual(compare_zone(p,[49,80,100,120])['preview'],'UNJUDGEABLE')
        self.assertEqual(compare_zone(p,[20,60,100,140])['preview'],'STRIKE')

    def test_isolated_big_jump_not_motion_track(self):
        rows=[dict(frame_index=i,candidates=[point(i,50 if i<6 else 800)]) for i in range(12)]
        self.assertEqual(analyze(rows)['status'],'no_moving_ball_track')

if __name__=='__main__':unittest.main()

import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from strikezone.ball.manual_pitch import track_manual_pitch

def rows(points,end=25):
    return [dict(frame_index=f,candidates=[dict(center_xy=[x,100],confidence=.9,bbox_xyxy=[x-3,97,x+3,103]) for ff,x in points if ff==f]) for f in range(end)]

class ManualPitchTests(unittest.TestCase):
    def test_deferred_endpoint_keeps_track_without_catch(self):
        r=track_manual_pitch(rows([(i,20+i*20) for i in range(10)]),0,[0,0,100,200],[180,50,230,150],defer_endpoint=True)
        self.assertEqual(len(r['track']),10)
        self.assertIsNone(r['endpoint']['frame_index'])
        self.assertEqual(r['status'],'ball_track_candidate')
    def test_no_people_needed_and_near_plate_missing_is_candidate(self):
        r=track_manual_pitch(rows([(i,20+i*20) for i in range(10)]),0,[0,0,100,200],[180,50,230,150])
        self.assertEqual(r['endpoint']['frame_index'],9)
        self.assertFalse(r['endpoint']['confirmed_catch'])
    def test_manual_arm_excludes_previous_pitch(self):
        r=track_manual_pitch(rows([(i,20+i*20) for i in range(10)]),12,[0,0,100,200],[180,50,230,150])
        self.assertEqual(r['status'],'no_ball_track')
    def test_stationary_false_detection_is_not_flight(self):
        r=track_manual_pitch(rows([(i,40) for i in range(20)]),0,[0,0,100,200],[180,50,230,150])
        self.assertEqual(r['status'],'no_ball_track')
    def test_end_of_video_is_not_disappearance(self):
        r=track_manual_pitch(rows([(i,20+i*20) for i in range(10)],10),0,[0,0,100,200],[180,50,230,150])
        self.assertIsNone(r['endpoint']['frame_index'])
    def test_missing_outside_plate_not_catch(self):
        r=track_manual_pitch(rows([(i,20+i*20) for i in range(7)]),0,[0,0,100,200],[180,50,230,150])
        self.assertIsNone(r['endpoint']['frame_index'])
    def test_interpolation_at_pre_endpoint(self):
        r=track_manual_pitch(rows([(i,20+i*20) for i in range(10) if i!=8]),0,[0,0,100,200],[180,50,230,150])
        self.assertEqual(r['position']['source'],'interpolated')

if __name__=='__main__':unittest.main()

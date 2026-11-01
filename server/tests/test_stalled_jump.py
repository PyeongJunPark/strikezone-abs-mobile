import copy
import unittest
from strikezone.ball.track_filter import filter_track
from strikezone.judgment.receiver_reference import prioritized_reference_call

def points(coords):
    return [dict(frame_index=f,center_xy=[x,y],bbox_xyxy=[x-3,y-3,x+3,y+3],observed=True) for f,x,y in coords]

class StalledJumpTests(unittest.TestCase):
    def flight(self):return [(i,10*i,50) for i in range(6)]

    def test_forward_jump_and_two_stalled_points_are_quarantined(self):
        p=points(self.flight()+[(6,90,50),(7,90.5,50),(10,110,80)])
        original=copy.deepcopy(p);r=filter_track(p)
        self.assertEqual([q['frame_index'] for q in r['track']],list(range(6)))
        self.assertEqual(r['continuity_loss']['last_valid_frame'],5)
        self.assertEqual(p,original)

    def test_missing_time_is_used_in_jump_test(self):
        # Thirty pixels over three frames is normal progress, followed by a stop.
        p=points(self.flight()+[(8,80,50),(9,80,50)])
        self.assertEqual(filter_track(p)['removed_count'],0)

    def test_real_moving_rebound_is_preserved(self):
        p=points(self.flight()+[(6,40,45),(7,30,40),(8,20,35)])
        self.assertEqual(filter_track(p)['removed_count'],0)

    def test_normal_catch_stop_is_preserved(self):
        p=points(self.flight()+[(6,60,50),(7,60,50),(8,60,50)])
        self.assertEqual(filter_track(p)['removed_count'],0)

    def test_short_reacquisition_keeps_later_flight(self):
        p=points(self.flight()+[(6,90,80),(7,90,80),(8,80,50),(9,90,50)])
        r=filter_track(p)
        self.assertEqual([q['frame_index'] for q in r['track']],[0,1,2,3,4,5,8,9])
        self.assertIsNone(r['continuity_loss'])

    def test_exclusion_cannot_manufacture_catch_or_nearest_strike(self):
        p=points(self.flight()+[(6,90,50),(7,90,50)])
        ds=[dict(frame_index=i,candidates=[]) for i in range(6,12)]
        r=prioritized_reference_call(p,[40,30,100,70],detections=ds,end_frame=15)
        self.assertIsNone(r['event']);self.assertIsNone(r['position'])
        self.assertEqual(r['preview'],'UNJUDGEABLE')
        self.assertEqual(r['reason'],'tracking_discontinuity_prediction_unavailable')

    def test_forecast_only_uses_retained_observations(self):
        p=points(self.flight()+[(6,90,50),(7,90,50)])
        rows=[dict(frame=i,perpendicular_px=1/(.08+.01*i)) for i in range(8)]
        r=prioritized_reference_call(p,[60,30,100,70],size_rows=rows,image_size=(200,200))
        self.assertEqual(r['position']['source'],'predicted')
        self.assertEqual(r['forecast']['training_frames'],list(range(6)))
        self.assertFalse(r['confirmed_catch'])

import unittest
from strikezone.judgment.receiver_reference import arrival_after_rejected_tail,prioritized_reference_call

def track():
    return [dict(frame_index=i,center_xy=[i*10,50],bbox_xyxy=[i*10-3,47,i*10+3,53],observed=True) for i in range(6)]

def detections():return [dict(frame_index=i,candidates=[]) for i in range(6,12)]

class FilteredArrivalTests(unittest.TestCase):
    def test_independent_raw_disappearance_accepts_last_observation(self):
        p=track()+[dict(frame_index=i,center_xy=[90,80]) for i in (6,7)]
        ds=detections();ds[0]['candidates']=[p[-2]];ds[1]['candidates']=[p[-1]]
        r=prioritized_reference_call(p,[45,40,65,70],detections=ds,end_frame=15)
        self.assertEqual(r['reason'],'receiver_disappearance_after_rejected_tail')
        self.assertEqual(r['position']['frame_index'],5)
        self.assertEqual(r['position']['source'],'observed')
        self.assertEqual(r['event']['confirmed_at'],11)
        self.assertFalse(r['confirmed_catch'])

    def test_far_early_loss_does_not_become_catch(self):
        self.assertIsNone(arrival_after_rejected_tail(track(),[100,40,120,70],30,detections(),15))

    def test_incomplete_raw_coverage_is_not_disappearance(self):
        self.assertIsNone(arrival_after_rejected_tail(track(),[45,40,65,70],30,detections()[:-1],15))

    def test_forward_continuation_overrides_filter_rejection(self):
        ds=detections();ds[3]['candidates']=[dict(center_xy=[90,50],confidence=.9)]
        self.assertIsNone(arrival_after_rejected_tail(track(),[45,40,65,70],30,ds,15))

    def test_already_stationary_or_inside_region_is_not_arrival(self):
        self.assertIsNone(arrival_after_rejected_tail(track(),[0,0,200,200],30,detections(),15))

    def test_video_end_is_not_confirmed_disappearance(self):
        self.assertIsNone(arrival_after_rejected_tail(track(),[45,40,65,70],30,detections(),10))

import copy
from pathlib import Path
import sys
import unittest
import numpy as np
import cv2
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from strikezone.pose.selector import BatterSelector, exclude_masked
from strikezone.plate.detector import locate, zone_candidate
from strikezone.plate.calibration import PlateCalibration


def batter(x=200):
    return dict(bbox_xyxy=[x,100,x+100,400],keypoints={
        'left_shoulder':dict(xy=[x+30,150],confidence=.9),
        'right_shoulder':dict(xy=[x+70,150],confidence=.9),
        'left_hip':dict(xy=[x+30,260],confidence=.9),
        'right_hip':dict(xy=[x+70,260],confidence=.9),
        'left_wrist':dict(xy=[x+55,145],confidence=.9),
        'right_wrist':dict(xy=[x+60,145],confidence=.9)})


class SceneTests(unittest.TestCase):
    def test_calibration_persistence_replace_reset(self):
        im=np.zeros((600,800,3),np.uint8);mask=np.zeros((600,800),np.uint8)
        c=PlateCalibration();edge=[[200,450],[300,450]]
        c.update(im,mask,'a',24,{'front_edge_xy':edge})
        for i in [26,28,100]:
            r=c.update(im,mask,'a',i,{})
            self.assertEqual(r['front_edge_xy'],edge)
            self.assertEqual(r['reference_frame_index'],24)
            self.assertTrue(r['reused'])
        new=[[210,460],[310,460]]
        self.assertEqual(c.update(im,mask,'a',101,{'front_edge_xy':new})['front_edge_xy'],new)
        self.assertIsNone(c.update(im,mask,'a',102,{'reset_plate':True})['front_edge_xy'])
        self.assertIsNone(c.update(im,mask,'a',103,{})['front_edge_xy'])

    def test_calibration_video_size_mask_invalid(self):
        im=np.zeros((600,800,3),np.uint8);mask=np.zeros((600,800),np.uint8)
        c=PlateCalibration();event={'front_edge_xy':[[200,450],[300,450]]}
        c.update(im,mask,'a',0,event)
        mask[450,250]=255
        self.assertEqual(c.update(im,mask,'a',1,{})['reason'],'masked_edge')
        mask[:]=0
        self.assertEqual(c.update(im,mask,'a',2,{})['status'],'ok')
        self.assertIsNone(c.update(im,mask,'b',0,{})['front_edge_xy'])
        c.update(im,mask,'b',1,event)
        self.assertIsNone(c.update(im[:500],mask[:500],'b',2,{})['front_edge_xy'])
        c.update(im,mask,'b',3,event)
        c.update(im,mask,'b',4,{'front_edge_xy':[[0,0],[0,1]]})
        self.assertIsNone(c.update(im,mask,'b',5,{})['front_edge_xy'])

    def test_auto_and_continuity(self):
        s=BatterSelector();a=s.select([batter()],0,800,600)
        self.assertEqual(a['status'],'ok')
        changed=batter(210);changed['keypoints']['left_wrist']['confidence']=.1
        b=s.select([changed],1,800,600)
        self.assertEqual(a['batter_id'],b['batter_id'])
        self.assertIsNone(s.select([],2,800,600)['candidate'])
        s.select([],3,800,600);s.select([],4,800,600)
        self.assertIsNone(s.previous)

    def test_ambiguous_and_manual(self):
        s=BatterSelector();people=[batter(),batter(500)]
        self.assertEqual(s.select(people,0,800,600)['reason'],'ambiguous_selection')
        a=s.select(people,1,800,600,manual_roi=[500,100,600,400])
        self.assertEqual(a['candidate']['bbox_xyxy'][0],500)
        self.assertIsNone(a['confidence'])

    def test_reset_and_time_order(self):
        s=BatterSelector();s.select([batter()],1,800,600)
        with self.assertRaises(ValueError):s.select([],1,800,600)
        s.reset();self.assertIsNone(s.select([],0,800,600)['candidate'])

    def test_mask_exclusion(self):
        mask=np.zeros((600,800),np.uint8);mask[200,250]=255
        self.assertEqual(exclude_masked([batter()],mask),[])

    def test_plate_candidate_not_confirmed(self):
        im=np.zeros((600,800,3),np.uint8);mask=np.zeros((600,800),np.uint8)
        cv2.fillConvexPoly(im,np.array([[160,410],[205,410],[205,425],[183,440],[160,425]]), (255,255,255))
        plate=locate(im,mask,batter())
        self.assertTrue(plate['candidates'])
        self.assertIsNone(plate['front_edge_xy'])
        self.assertNotEqual(plate['status'],'ok')

    def test_manual_zone_and_mask(self):
        im=np.zeros((600,800,3),np.uint8);mask=np.zeros((600,800),np.uint8)
        edge=[[300,450],[200,450]]
        plate=locate(im,mask,None,edge)
        zone=zone_candidate(dict(status='ok',top_y=200,bottom_y=350),plate,12)
        self.assertEqual(zone['bbox_xyxy'],[200,200,300,350])
        mask[450,250]=255
        self.assertEqual(locate(im,mask,None,edge)['reason'],'masked_edge')
        self.assertEqual(locate(im,mask,None,[[1,1],[1,3]])['status'],'invalid')
        self.assertEqual(locate(im,mask,None,[[float('nan'),1],[3,3]])['status'],'invalid')


if __name__=='__main__':unittest.main()

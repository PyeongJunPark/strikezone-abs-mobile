import unittest
import cv2
import numpy as np
from strikezone.ball.masking import measure_ball_mask

class MaskTests(unittest.TestCase):
 def test_silhouette_preserved(self):
  bg=np.full((64,64,3),30,np.uint8);im=bg.copy();cv2.circle(im,(32,32),9,(180,180,180),-1);cv2.circle(im,(35,34),3,(65,65,65),-1)
  r=measure_ball_mask(im,bg,(20,20));self.assertIsNotNone(r['diameter_px']);self.assertGreaterEqual(r['horizontal_width_px'],19)
  ys,xs=np.where(r['mask']);points=np.column_stack([xs,ys]);corners=np.concatenate([points+off for off in [[-.5,-.5],[-.5,.5],[.5,-.5],[.5,.5]]]);self.assertLessEqual(np.linalg.norm(corners-r['circle_center'],axis=1).max(),r['diameter_px']/2+1e-4)
 def test_stationary_bright_background_rejected(self):
  bg=np.full((64,64,3),20,np.uint8);cv2.circle(bg,(32,32),9,(255,255,255),-1)
  self.assertIsNone(measure_ball_mask(bg,bg,(20,20))['diameter_px'])
 def test_merged_foreground_rejected(self):
  bg=np.zeros((64,64,3),np.uint8);im=bg.copy();im[20:45,20:64]=255
  self.assertIsNone(measure_ball_mask(im,bg,(20,20))['diameter_px'])
if __name__=='__main__':unittest.main()

import unittest
import cv2,numpy as np
from strikezone.ball.blur_size import perpendicular_width

class PerpendicularTests(unittest.TestCase):
 def test_streak_length_does_not_change_width(self):
  vals=[]
  for length in [0,10,30]:
   m=np.zeros((96,128),np.uint8)
   for x in range(40,41+length):cv2.circle(m,(x,48),10,255,-1)
   vals.append(perpendicular_width(m,[1,0])['width_px'])
  self.assertEqual(vals,[21,21,21])
 def test_rotation_and_pixel_corners(self):
  m=np.zeros((96,96),np.uint8)
  for d in range(20):cv2.circle(m,(30+d,30+d),10,255,-1)
  r=perpendicular_width(m,[1,1]);self.assertLess(abs(r['width_px']-21),1)
 def test_no_direction_or_mask(self):
  self.assertIsNone(perpendicular_width(np.ones((3,3)),[0,0])['width_px'])
  self.assertIsNone(perpendicular_width(np.zeros((3,3)),[1,0])['width_px'])
if __name__=='__main__':unittest.main()

import sys
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from strikezone.pose.reference import exclude_masked_joints, rank_references


class ReferenceTests(unittest.TestCase):
    def frame(self,index,top=100,duplicate=False,status='ok'):
        return dict(frame_index=index,image_height=800,duplicate_of_previous=duplicate,
                    pose=dict(status=status,confidence=.9,top_y=top,bottom_y=500))

    def test_only_valid_unique_pre_release_and_stability(self):
        frames=[self.frame(0),self.frame(1,101),self.frame(2,200),
                self.frame(3,duplicate=True),self.frame(4,status='missing'),self.frame(5)]
        ranked=rank_references(frames,5)
        self.assertEqual(ranked[0]['frame_index'],1)
        self.assertEqual({x['frame_index'] for x in ranked},{0,1,2})

    def test_sparse_frames_do_not_claim_consecutive_stability(self):
        result=rank_references([self.frame(0),self.frame(10)],11)
        self.assertTrue(all(x['height_change_px'] is None for x in result))

    def test_mask_neighborhood_excludes_inpainted_evidence_without_mutation(self):
        people=[dict(keypoints={'left_knee':dict(xy=[10,10],confidence=.9),
                               'right_knee':dict(xy=[30,30],confidence=.9)})]
        mask=np.zeros((50,50),np.uint8);mask[12,12]=255
        result=exclude_masked_joints(people,mask)
        self.assertNotIn('left_knee',result[0]['keypoints'])
        self.assertIn('right_knee',result[0]['keypoints'])
        self.assertIn('left_knee',people[0]['keypoints'])

    def test_invalid_point_is_discarded_before_rounding(self):
        people=[dict(keypoints={'left_knee':dict(xy=[float('nan'),10],confidence=.9)})]
        self.assertEqual(exclude_masked_joints(people,np.zeros((20,20),np.uint8))[0]['keypoints'],{})


if __name__=='__main__':unittest.main()

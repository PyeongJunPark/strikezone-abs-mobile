"""Manual fixed-camera calibration events, isolated by video and image size."""
from copy import deepcopy
from .detector import locate


class PlateCalibration:
    def __init__(self):
        self.context=None
        self.value=None

    def update(self, frame, mask, video_id, frame_index, correction):
        context=(video_id,frame.shape[1],frame.shape[0])
        if context!=self.context or correction.get('reset_plate',False):
            self.value=None
        self.context=context
        if 'front_edge_xy' in correction:
            self.value=None
            candidate=locate(frame,mask,None,correction['front_edge_xy'])
            if correction['front_edge_xy'] is None:
                candidate=dict(status='missing',confidence=None,reason='not_configured',
                               source='manual',front_edge_xy=None,corners_xy=None,candidates=[])
            if candidate['status']=='ok':
                self.value=dict(edge=deepcopy(candidate['front_edge_xy']),reference=frame_index)
            else:
                return candidate
        if self.value is None:
            return dict(status='missing',confidence=None,reason='not_configured',source='manual',
                        front_edge_xy=None,corners_xy=None,candidates=[],reference_frame_index=None)
        result=locate(frame,mask,None,self.value['edge'])
        result.update(reference_frame_index=self.value['reference'],
                      calibration_mode='fixed_camera_manual',
                      reused=frame_index!=self.value['reference'])
        return result

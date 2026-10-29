"""Causal, conservative pitcher-motion onset candidate; never ball release proof."""
import cv2
import numpy as np


class PitchStartDetector:
    def __init__(self, pitcher_roi, batter_roi, stable_frames=3, confirm_frames=2,
                 motion_threshold=.08, background_threshold=.15):
        self.roi, self.batter_roi = pitcher_roi, batter_roi
        self.stable_frames, self.confirm_frames = stable_frames, confirm_frames
        self.motion_threshold, self.background_threshold = motion_threshold, background_threshold
        self.previous = self.previous_mask = self.baseline = self.baseline_mask = None
        self.last_index = None
        self.stable = self.pending = 0
        self.onset = self.event = None
        self.state = 'awaiting_ready'

    def update(self, image, ignore_mask, index):
        gray = cv2.GaussianBlur(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), (5,5), 0)
        valid = ignore_mask == 0
        region = np.zeros(gray.shape, bool)
        x1,y1,x2,y2 = map(int,self.roi); region[y1:y2,x1:x2] = True
        background = ~region
        a,b,c,d = map(int,self.batter_roi); background[b:d,a:c] = False
        out = dict(state=self.state, reason=None, event=None, motion_fraction=None,
                   background_fraction=None, ball_release_confirmed=False)
        if self.last_index is not None and (index != self.last_index+1 or gray.shape != self.previous.shape):
            self.state = 'interrupted'; out['reason'] = 'frame_gap_or_size_change'
        elif self.previous is not None and self.state != 'interrupted':
            usable = valid & self.previous_mask
            foreground = region & usable
            bg = background & usable
            if foreground.sum() < max(100, region.sum()*.5) or bg.sum() < 100:
                self.state = 'interrupted'; out['reason'] = 'insufficient_unmasked_area'
            else:
                delta = cv2.absdiff(gray,self.previous)
                motion = float((delta[foreground] > 20).mean())
                bg_motion = float((delta[bg] > 20).mean())
                out.update(motion_fraction=motion, background_fraction=bg_motion)
                if bg_motion > self.background_threshold:
                    self.state = 'interrupted'; out['reason'] = 'background_change'
                elif self.state == 'awaiting_ready':
                    self.stable = self.stable+1 if motion < .015 else 0
                    if self.stable >= self.stable_frames:
                        self.baseline = gray.copy(); self.baseline_mask = valid.copy(); self.state = 'armed'
                elif self.state in ('armed','candidate'):
                    baseline_region = foreground & self.baseline_mask
                    if baseline_region.sum() < max(100,region.sum()*.5):
                        self.state = 'interrupted'; out['reason'] = 'insufficient_baseline_area'
                        self.previous,self.previous_mask,self.last_index = gray,valid,index
                        return dict(out,state=self.state)
                    displacement = float((cv2.absdiff(gray,self.baseline)[baseline_region] > 20).mean())
                    out['baseline_displacement'] = displacement
                    if displacement >= self.motion_threshold and motion >= .01:
                        if not self.pending: self.onset = index
                        self.pending += 1; self.state = 'candidate'
                        if self.pending >= self.confirm_frames:
                            self.state = 'triggered'
                            self.event = dict(onset_frame_index=self.onset, confirmed_frame_index=index,
                                              method='pitcher_roi_motion_v1', validated=False,
                                              ball_release_confirmed=False)
                            out['event'] = self.event.copy()
                    else:
                        self.pending = 0; self.onset = None; self.state = 'armed'
        self.previous, self.previous_mask, self.last_index = gray, valid, index
        out['state'] = self.state
        return out


def auto_reference(frames, event, max_age=15):
    if event is None:
        return dict(status='missing', reason='no_pitch_start_candidate', event=None, reference_frame_index=None)
    before = [f for f in frames if event['onset_frame_index']-max_age <= f['frame_index'] < event['onset_frame_index']
              and f['pose']['status']=='ok']
    if not before:
        return dict(status='missing', reason='no_valid_pre_start_pose', event=event, reference_frame_index=None)
    return dict(status='ok', reason=None, event=event, reference_frame_index=before[-1]['frame_index'])

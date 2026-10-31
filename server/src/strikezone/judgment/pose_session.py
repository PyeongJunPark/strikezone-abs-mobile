"""Acquire a stable stance, then retain it through the start of batting motion."""
from copy import deepcopy
import math
import statistics


class PoseZoneSession:
    STABLE_SECONDS = .3
    MAX_SAMPLE_GAP = .25
    STABLE_SPREAD = .14
    MOTION_SHIFT = .30

    def __init__(self, plate_x, fps, manual_height=None, *, relaxed=False, fallback_height=None):
        if len(plate_x)!=2 or not all(math.isfinite(x) for x in plate_x) or plate_x[0]>=plate_x[1] or not math.isfinite(fps) or fps<=0:
            raise ValueError('Invalid plate width or FPS')
        if manual_height is not None and (len(manual_height)!=2 or not all(math.isfinite(x) for x in manual_height) or manual_height[0]>=manual_height[1]):
            raise ValueError('Invalid manual height')
        self.plate_x=list(plate_x);self.fps=fps;self.manual_height=manual_height
        if fallback_height is not None and (len(fallback_height)!=2 or not all(math.isfinite(v) for v in fallback_height) or fallback_height[0]>=fallback_height[1]):
            raise ValueError('Invalid fallback height')
        self.relaxed=relaxed;self.fallback_height=fallback_height
        self.history=[];self.height_source='manual' if manual_height is not None else 'batter_pose'
        self.last_frame=None;self.identity=None;self.frozen=False
        self._reset()

    def _reset(self):
        self.samples=[];self.zone=None;self.reference=None;self.baseline=None
        self.last_valid=None;self.motion_start=None;self.motion_count=0
        self.lock_frame=None;self.lock_reason=None;self.stable_range=None

    @staticmethod
    def features(pose):
        if pose.get('status')!='ok':return None
        keys=pose.get('motion_keypoints',pose.get('keypoints',{}))
        names=['left_shoulder','right_shoulder','left_hip','right_hip','left_knee','right_knee']
        if any(n not in keys or keys[n]['confidence']<.4 for n in names):return None
        ys={n:keys[n]['xy'][1] for n in names}
        shoulder=(ys[names[0]]+ys[names[1]])/2;hip=(ys[names[2]]+ys[names[3]])/2
        scale=hip-shoulder
        if not math.isfinite(scale) or scale<=2:return None
        values={n:ys[n] for n in names}
        # Relative knee heights detect leg lift even when the torso also moves.
        values.update(left_relative=ys['left_knee']-hip,right_relative=ys['right_knee']-hip)
        for n in ['left_wrist','right_wrist','left_ankle','right_ankle']:
            if n in keys and keys[n]['confidence']>=.4:values[n]=keys[n]['xy'][1]
        if not all(math.isfinite(v) for v in values.values()):return None
        return dict(values=values,scale=scale,top=pose['top_y'],bottom=pose['bottom_y'])

    def update(self, frame, pose, batter_id, explicit_reference=False):
        if self.last_frame is not None and frame<=self.last_frame:raise ValueError('Frames must increase')
        self.last_frame=frame
        if self.frozen:return self.snapshot()
        if self.manual_height is not None:
            self.zone=[self.plate_x[0],self.manual_height[0],self.plate_x[1],self.manual_height[1]]
            self.reference=frame;return self.snapshot()
        if batter_id and batter_id!=self.identity:
            self._reset();self.history=[];self.identity=batter_id
        feature=self.features(pose)
        if explicit_reference and feature is None:
            self.zone=None;self.reference=frame;self.lock_frame=frame;self.lock_reason='invalid_reference_pose'
            return self.snapshot()
        if self.lock_frame is not None and not explicit_reference:return self.snapshot()
        if self.last_valid is not None and frame-self.last_valid>round(self.MAX_SAMPLE_GAP*self.fps):
            self.motion_count=0;self.motion_start=None
        if not self.relaxed and self.last_valid is not None and frame-self.last_valid>round(.5*self.fps):self._reset()
        if feature is None:
            self.samples=[];self.motion_count=0;self.motion_start=None
            return self.snapshot()
        self.last_valid=frame
        if explicit_reference:
            self.zone=[self.plate_x[0],feature['top'],self.plate_x[1],feature['bottom']]
            self.reference=frame;self.lock_frame=frame;self.lock_reason='manual_reference_frame';self.stable_range=[frame,frame]
            return self.snapshot()
        if self.baseline is not None:
            base=self.baseline;shared=set(base['values'])&set(feature['values'])
            shift=max(abs(feature['values'][n]-base['values'][n]) for n in shared)/base['scale']
            if shift>self.MOTION_SHIFT:
                if self.motion_start is None:self.motion_start=frame
                self.motion_count+=1;self.samples=[]
                if self.motion_count>=2:
                    self.lock_frame=frame;self.lock_reason='sustained_pose_motion'
                return self.snapshot()
        self.motion_count=0;self.motion_start=None
        self.history.append(dict(feature,frame=frame))
        if self.samples and frame-self.samples[-1]['frame']>round(self.MAX_SAMPLE_GAP*self.fps):self.samples=[]
        self.samples.append(dict(feature,frame=frame))
        while len(self.samples)>1 and frame-self.samples[1]['frame']>=self.STABLE_SECONDS*self.fps:self.samples.pop(0)
        duration=.2 if self.relaxed else self.STABLE_SECONDS
        if len(self.samples)<(3 if self.relaxed else 4) or frame-self.samples[0]['frame']<duration*self.fps:return self.snapshot()
        scale=statistics.median(s['scale'] for s in self.samples)
        shared=set.intersection(*(set(s['values']) for s in self.samples))
        spread=max(max(s['values'][n] for s in self.samples)-min(s['values'][n] for s in self.samples) for n in shared)/scale
        if spread>(.25 if self.relaxed else self.STABLE_SPREAD):return self.snapshot()
        self.baseline=dict(scale=scale,values={n:statistics.median(s['values'][n] for s in self.samples) for n in shared})
        self.zone=[self.plate_x[0],statistics.median(s['top'] for s in self.samples),self.plate_x[1],statistics.median(s['bottom'] for s in self.samples)]
        self.reference=frame;self.stable_range=[self.samples[0]['frame'],frame]
        return self.snapshot()

    def freeze(self, frame):
        if self.manual_height is None:
            age_limit=5*self.fps if self.lock_reason=='manual_reference_frame' else (3*self.fps if self.relaxed else (2*self.fps if self.lock_frame is not None else .5*self.fps))
            if self.reference is None or frame-self.reference>age_limit:self.zone=None
        if self.relaxed and self.zone is None and self.lock_reason!='invalid_reference_pose':
            rows=[r for r in self.history if 0<=frame-r['frame']<=3*self.fps]
            if len(rows)>=2:
                scale=statistics.median(r['scale'] for r in rows)
                top=statistics.median(r['top'] for r in rows);bottom=statistics.median(r['bottom'] for r in rows)
                # Reject large leg-lift/swing excursions; missing frames need not be consecutive.
                rows=[r for r in rows if abs(r['top']-top)<=.5*scale and abs(r['bottom']-bottom)<=.5*scale]
                if len(rows)>=2:
                    self.zone=[self.plate_x[0],statistics.median(r['top'] for r in rows),self.plate_x[1],statistics.median(r['bottom'] for r in rows)]
                    self.reference=rows[-1]['frame'];self.height_source='pose_median';self.lock_reason='sparse_pre_pitch_median'
            if self.zone is None and self.fallback_height is not None:
                self.zone=[self.plate_x[0],self.fallback_height[0],self.plate_x[1],self.fallback_height[1]]
                self.height_source='manual_fallback';self.lock_reason='saved_zone_fallback';self.reference=None
        self.frozen=True
        if self.lock_reason is None:self.lock_reason='pitch_start' if self.zone else 'no_stable_stance'
        return self.snapshot()

    def snapshot(self):
        phase='locked' if self.frozen or self.lock_frame is not None else ('motion_pending' if self.motion_count else ('stable_ready' if self.zone else 'searching_stance'))
        return deepcopy(dict(zone=self.zone,phase=phase,height_source=self.height_source,reference_frame=self.reference,batter_id=self.identity,
                             status='ok' if self.zone else 'missing_stable_stance',stable_frame_range=self.stable_range,lock_frame=self.lock_frame,
                             lock_reason=self.lock_reason,motion_start_frame=self.motion_start))

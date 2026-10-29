"""Conservative batting-stance heuristic, not a trained role classifier."""
from copy import deepcopy
from math import hypot
from .zone import overlap, valid_box


def exclude_masked(candidates, mask):
    """A masked detection box is not evidence, including reconstructed pixels."""
    h, w = mask.shape
    return [deepcopy(c) for c in candidates if valid_box(c['bbox_xyxy'], w, h)
            and not mask[int(c['bbox_xyxy'][1]):int(c['bbox_xyxy'][3])+1,
                         int(c['bbox_xyxy'][0]):int(c['bbox_xyxy'][2])+1].any()]


def stance_score(candidate, people):
    box = candidate['bbox_xyxy']; height=box[3]-box[1]
    k = candidate['keypoints']
    names=['left_shoulder','right_shoulder','left_hip','right_hip','left_wrist','right_wrist']
    if any(n not in k or k[n]['confidence']<0.4 for n in names):
        return 0.0
    s=sum(k[n]['xy'][1] for n in names[:2])/2
    hip=sum(k[n]['xy'][1] for n in names[2:4])/2
    if hip<=s or height<=0:
        return 0.0
    a,b=(k[n]['xy'] for n in names[4:])
    close=max(0,1-hypot(a[0]-b[0],a[1]-b[1])/(height*0.45))
    raised=max(0,min(1,(hip-(a[1]+b[1])/2)/(hip-s)))
    # A smaller nearby player at similar foot height supports the batter hypothesis.
    support=0.0
    cx=(box[0]+box[2])/2
    for other in people:
        if other is candidate:
            continue
        q=other['bbox_xyxy']; oh=q[3]-q[1]
        if (0.25*height<oh<0.85*height and
                abs(q[3]-box[3])<height*0.25 and
                0.15*height<abs((q[0]+q[2])/2-cx)<height*1.1):
            support=1.0
    return round(0.5*close+0.3*raised+0.2*support,4)


class BatterSelector:
    def __init__(self):
        self.previous=None
        self.last_index=None
        self.generation=0
        self.misses=0

    def reset(self):
        self.previous=None
        self.last_index=None
        self.misses=0

    def select(self, people, frame_index, width, height, manual_roi=None):
        if self.last_index is not None and frame_index<=self.last_index:
            raise ValueError('Frames must be strictly increasing; reset on new video')
        if self.last_index is not None and frame_index-self.last_index>15:
            self.reset()
        self.last_index=frame_index
        source='manual' if manual_roi is not None else 'auto'
        if manual_roi is not None and not valid_box(manual_roi,width,height):
            raise ValueError('Invalid manual ROI')
        ranked=[]
        for c in people:
            if not valid_box(c['bbox_xyxy'],width,height):
                continue
            base=stance_score(c,people)
            continuity=overlap(c['bbox_xyxy'],self.previous) if self.previous else 0
            score=overlap(c['bbox_xyxy'],manual_roi) if manual_roi is not None else base
            if manual_roi is None and continuity>=0.4:
                score=max(score,0.65+0.25*continuity)
            ranked.append((score,c,base,continuity))
        ranked.sort(key=lambda x:x[0],reverse=True)
        threshold=0.2 if source=='manual' else 0.75
        reason='no_detection' if not ranked else 'low_role_score'
        selected=None
        if ranked and ranked[0][0]>=threshold:
            if len(ranked)>1 and ranked[0][0]-ranked[1][0]<0.12:
                reason='ambiguous_selection'
            else:
                selected=deepcopy(ranked[0][1]);reason=None
        if selected is None:
            self.misses+=1
            if self.misses>=3:self.previous=None
        else:
            if self.previous is None or overlap(selected['bbox_xyxy'],self.previous)<0.4:
                self.generation+=1
            self.previous=selected['bbox_xyxy'];self.misses=0
        return dict(status='ok' if selected else 'missing',reason=reason,
                    confidence=None,source=source,heuristic_score=ranked[0][0] if ranked else None,
                    batter_id=f'b{self.generation}' if selected else None,candidate=selected,
                    candidates=[dict(bbox_xyxy=c['bbox_xyxy'],score=s,stance_score=b)
                                for s,c,b,_ in ranked])

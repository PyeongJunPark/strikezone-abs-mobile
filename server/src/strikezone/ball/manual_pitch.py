"""Manually armed, fixed-camera ball tracking. No per-frame player dependencies."""
import math
import numpy as np
from .learned_trajectory import Config, link, endpoint, estimate_position, velocity


def inside(xy, box):
    return box[0] <= xy[0] <= box[2] and box[1] <= xy[1] <= box[3]


def track_manual_pitch(rows, trigger_frame, pitcher_box, plate_region, fps=30, width=1080, acquisition_seconds=2, defer_endpoint=False):
    """Offline experiment: one manual arm, fixed origin, observed ball flight.

    Player poses are deliberately absent from this API. A missing endpoint stays
    missing; disappearance in a plate region is not proof of glove contact.
    Input rows must include the full confirmation horizon, even empty frames.
    """
    if fps <= 0 or len(pitcher_box)!=4 or len(plate_region)!=4:
        raise ValueError('Invalid calibration')
    if any(b[0]>=b[2] or b[1]>=b[3] for b in (pitcher_box,plate_region)):
        raise ValueError('Degenerate calibration')
    rows=[r for r in rows if trigger_frame<=r['frame_index']<trigger_frame+round(4*fps)]
    cfg=Config(min_speed=2*width/1080*30/fps,min_travel=max(15,20*width/1080))
    tracks=link(rows,cfg); eligible=[]
    target=np.array([(plate_region[0]+plate_region[2])/2,(plate_region[1]+plate_region[3])/2])
    for tid,t in enumerate(tracks):
        for i in range(len(t)-3):
            q=t[i:i+4]
            if q[0]['frame_index']>trigger_frame+round(acquisition_seconds*fps):continue
            if q[-1]['frame_index']-q[0]['frame_index']>max(8,round(.4*fps)):continue
            if not inside(q[0]['center_xy'],pitcher_box):continue
            speed,error=velocity(q);travel=math.dist(q[0]['center_xy'],q[-1]['center_xy'])
            if np.linalg.norm(speed)<cfg.min_speed or travel<cfg.min_travel or error>max(15,width*.025):continue
            flight=t[i:]; best_gain=max(math.dist(q[0]['center_xy'],target)-math.dist(p['center_xy'],target) for p in flight)
            # No narrow torso corridor or monotonic-distance requirement: an
            # arcing flight may initially travel away from the ground anchor.
            score=travel+min(150,best_gain)+min(20,len(flight))*4-error*2
            eligible.append((score,tid,i,flight));break
    if not eligible:
        return dict(status='no_ball_track',track=[],endpoint=dict(frame_index=None,reason='no_ball_track'),position=None,alternative_count=0)
    eligible.sort(key=lambda a:a[0],reverse=True)
    _,tid,start,track=eligible[0]
    # Only the first 1.5 seconds after acquired flight belong to this pitch.
    track=[p for p in track if p['frame_index']<=track[0]['frame_index']+round(1.5*fps)]
    by_frame={r['frame_index']:r for r in rows}
    for p in track:p['source_frame_repeated']=by_frame[p['frame_index']].get('source_frame_repeated',False)
    if defer_endpoint:
        return dict(status='ball_track_candidate',track=track,endpoint=dict(frame_index=None,reason='deferred_to_contact_analysis'),position=None,
                    selected_track_id=tid,alternative_count=len(eligible)-1,selection='manual_window_fixed_origin_motion_score',trigger_frame=trigger_frame)
    end=endpoint(track,cfg)
    if end['frame_index'] is not None:
        point=next(p for p in track if p['frame_index']==end['frame_index'])
        if not inside(point['center_xy'],plate_region):
            end=dict(frame_index=None,reason='motion_change_outside_plate_region')
    horizon=max(3,round(.20*fps)); required=max(2,round(.067*fps))
    for i,p in enumerate(track):
        if i<3 or not inside(p['center_xy'],plate_region):continue
        if math.dist(track[0]['center_xy'],p['center_xy'])<cfg.min_travel:continue
        f=p['frame_index']; future=range(f+1,f+horizon+1)
        if not all(j in by_frame for j in future):continue
        if any(f<q['frame_index']<=f+horizon for q in track):continue
        effective=[j for j in future if not by_frame[j].get('source_frame_repeated',False)]
        if len(effective)<required:continue
        # An unassigned moving detection near the last observation prevents a
        # false disappearance from a simple track split. Static clutter does not.
        escape=False
        for j in effective:
            for c in by_frame[j]['candidates']:
                if c['confidence']<.3 or math.dist(c['center_xy'],p['center_xy'])>max(25,width*.025)*(j-f):continue
                prev=by_frame.get(j-1,{}).get('candidates',[])
                if not any(math.dist(c['center_xy'],old['center_xy'])<3 for old in prev):escape=True
        if escape:continue
        candidate=dict(frame_index=f,confirmed_frame_index=effective[required-1],reason='plate_region_disappearance',
                       status='candidate',confirmed_catch=False,timing_uncertainty_frames=1)
        if end['frame_index'] is None or f<end['frame_index']:end=candidate
        break
    if end['frame_index'] is not None:track=[p for p in track if p['frame_index']<=end['frame_index']+2]
    position=estimate_position(track,end['frame_index']-1,cfg) if end['frame_index'] is not None else None
    return dict(status='ball_track_candidate',track=track,endpoint=end,position=position,selected_track_id=tid,
                alternative_count=len(eligible)-1,selection='manual_window_fixed_origin_motion_score',
                trigger_frame=trigger_frame,pitcher_box=list(pitcher_box),plate_region=list(plate_region))

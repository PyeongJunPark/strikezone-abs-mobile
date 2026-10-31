"""Offline learned-ball trajectories and explicitly labelled position estimates.

No pose/start trigger. Endpoint means a motion change, not a confirmed catch.
Coordinates are source pixels; defaults target 1080-wide, 30 fps recordings.
"""
from dataclasses import dataclass, asdict
import math
import numpy as np


@dataclass
class Config:
    confidence: float = .12
    max_gap: int = 8
    max_speed: float = 95.
    association_margin: float = 20.
    min_speed: float = 4.
    min_travel: float = 60.
    turn_degrees: float = 65.
    stop_ratio: float = .28
    interpolation_gap: int = 8
    extrapolation_frames: int = 3


def velocity(points):
    times=np.array([p['frame_index'] for p in points],float)
    xy=np.array([p['center_xy'] for p in points],float)
    if len(points)<2 or times[-1]==times[0]:return np.zeros(2),0.
    times-=times[-1]
    coeff=np.polyfit(times,xy,1)
    residual=float(np.sqrt(np.mean((np.polyval(coeff[:,0],times)-xy[:,0])**2+(np.polyval(coeff[:,1],times)-xy[:,1])**2)))
    return coeff[0],residual


def link(rows, cfg):
    """Multiple tracks prevent a stationary false positive from owning the ball ID."""
    tracks=[]
    for row in rows:
        frame=row['frame_index']
        candidates=[dict(c,frame_index=frame,observed=True) for c in row['candidates'] if c['confidence']>=cfg.confidence]
        active=[t for t in tracks if frame-t[-1]['frame_index']<=cfg.max_gap]
        cost=np.full((len(active),len(candidates)),1e6)
        for i,t in enumerate(active):
            last=t[-1];gap=frame-last['frame_index'];v,_=velocity(t[-4:]);speed=float(np.linalg.norm(v))
            prediction=np.array(last['center_xy'])+v*gap
            for j,c in enumerate(candidates):
                distance=math.dist(last['center_xy'],c['center_xy'])
                error=float(np.linalg.norm(np.array(c['center_xy'])-prediction))
                gate=cfg.association_margin+min(55.,speed*1.6)*gap
                if len(t)==1:gate=cfg.max_speed*gap
                if distance<=cfg.max_speed*gap and error<=gate:
                    cost[i,j]=error+5*(1-c['confidence'])
        assigned=set();used_tracks=set()
        if cost.size:
            for value,i,j in sorted((cost[i,j],i,j) for i in range(len(active)) for j in range(len(candidates)) if cost[i,j]<1e6):
                if i not in used_tracks and j not in assigned:
                    active[i].append(candidates[j]);assigned.add(j);used_tracks.add(i)
        tracks.extend([[c] for j,c in enumerate(candidates) if j not in assigned])
    return tracks


def flight_run(track,cfg):
    """Find sustained, approximately smooth displacement instead of a single jump."""
    best=None
    for i in range(len(track)-5):
        window=track[i:i+6];v,residual=velocity(window)
        travel=math.dist(window[0]['center_xy'],window[-1]['center_xy'])
        if np.linalg.norm(v)<cfg.min_speed or travel<cfg.min_travel or residual>12:continue
        score=travel/(window[-1]['frame_index']-window[0]['frame_index'])+sum(p['confidence'] for p in window)*3
        if best is None or score>best[0]:best=(float(score),i)
    return best


def endpoint(track,cfg):
    track=[p for p in track if not p.get('source_frame_repeated',False)]
    for k in range(5,len(track)-2):
        pre=track[k-5:k+1];post=track[k:k+3]
        vin,errin=velocity(pre);vout,errout=velocity(post)
        speed=float(np.linalg.norm(vin));after=float(np.linalg.norm(vout))
        if speed<cfg.min_speed or errin>12 or errout>12:continue
        if math.dist(pre[0]['center_xy'],pre[-1]['center_xy'])<cfg.min_travel:continue
        if pre[-1]['frame_index']-pre[0]['frame_index']>12 or post[-1]['frame_index']-post[0]['frame_index']>5:continue
        angle=math.degrees(math.acos(float(np.clip(np.dot(vin,vout)/max(1e-9,speed*after),-1,1))))
        first=(np.array(post[1]['center_xy'])-post[0]['center_xy'])/(post[1]['frame_index']-post[0]['frame_index'])
        first_speed=float(np.linalg.norm(first))
        first_angle=math.degrees(math.acos(float(np.clip(np.dot(vin,first)/max(1e-9,speed*first_speed),-1,1))))
        stopped=after<speed*cfg.stop_ratio and first_speed<speed*cfg.stop_ratio
        if not stopped and not (angle>=cfg.turn_degrees and first_angle>=cfg.turn_degrees and after>=cfg.min_speed*.5):continue
        return dict(status='candidate',frame_index=track[k]['frame_index'],confirmed_frame_index=post[-1]['frame_index'],
                    reason='abrupt_deceleration' if stopped else 'trajectory_turn_or_bounce',
                    turn_degrees=angle,speed_before=speed,speed_after=after,confirmed_catch=False,
                    timing_uncertainty_frames=max(track[k]['frame_index']-track[k-1]['frame_index'],track[k+1]['frame_index']-track[k]['frame_index'])-1)
    return dict(status='missing',reason='no_supported_motion_endpoint',frame_index=None,confirmed_catch=False)


def estimate_position(track,frame,cfg=None):
    cfg=cfg or Config()
    missing=dict(frame_index=frame,center_xy=None,observed=False,source='missing',uncertainty_px=None)
    exact=next((p for p in track if p['frame_index']==frame),None)
    if exact:
        box=exact.get('bbox_xyxy',[0,0,6,6]);radius=max(3.,min(box[2]-box[0],box[3]-box[1])/2)
        return dict(missing,center_xy=list(exact['center_xy']),observed=True,source='detected',uncertainty_px=radius)
    before=[p for p in track if p['frame_index']<frame];after=[p for p in track if p['frame_index']>frame]
    if before and after:
        a,b=before[-1],after[0];gap=b['frame_index']-a['frame_index']
        if gap>cfg.interpolation_gap:return dict(missing,reason='gap_too_long')
        ratio=(frame-a['frame_index'])/gap
        xy=np.array(a['center_xy'])*(1-ratio)+np.array(b['center_xy'])*ratio
        va,ea=velocity(before[-4:]);vb,eb=velocity(after[:4])
        uncertainty=3.+max(ea,eb)+gap*.5*float(np.linalg.norm(va-vb))
        return dict(missing,center_xy=xy.tolist(),source='interpolated',uncertainty_px=uncertainty,
                    support_frames=[a['frame_index'],b['frame_index']])
    if len(before)>=4 and not after:
        gap=frame-before[-1]['frame_index'];v,error=velocity(before[-5:])
        if gap<=cfg.extrapolation_frames and error<=12:
            xy=np.array(before[-1]['center_xy'])+v*gap
            return dict(missing,center_xy=xy.tolist(),source='extrapolated',uncertainty_px=5+error+gap*5,
                        support_frames=[p['frame_index'] for p in before[-5:]])
    return dict(missing,reason='insufficient_support')


def compare_zone(position,zone):
    result=dict(preview='UNJUDGEABLE',reason='position_missing',geometry='screen_point_center',validated=False)
    if position['center_xy'] is None:return result
    if zone is None:return dict(result,reason='zone_missing')
    if len(zone)!=4 or not all(math.isfinite(x) for x in zone) or zone[0]>=zone[2] or zone[1]>=zone[3]:return dict(result,reason='invalid_zone')
    x,y=position['center_xy'];l,t,r,b=zone
    inside=l<=x<=r and t<=y<=b
    distance=min(x-l,r-x,y-t,b-y) if inside else math.hypot(max(l-x,0,x-r),max(t-y,0,y-b))
    uncertain=position['source']!='detected' and distance<=position['uncertainty_px']
    return dict(result,preview='UNJUDGEABLE' if uncertain else 'STRIKE' if inside else 'BALL',
                raw_point_preview='STRIKE' if inside else 'BALL',reason='estimate_crosses_zone_boundary' if uncertain else 'point_inside_zone' if inside else 'point_outside_zone',position_source=position['source'])


def analyze(rows,zone=None,cfg=None):
    cfg=cfg or Config();tracks=link(rows,cfg);eligible=[]
    for t in tracks:
        run=flight_run(t,cfg)
        if run:
            # Rank coherent flight evidence, not detector confidence alone.
            eligible.append((run[0]+min(40,len(t))*.5,t,run[1]))
    if not eligible:return dict(status='no_moving_ball_track',tracks=[],endpoint=dict(status='missing',frame_index=None),position=None,comparison=dict(preview='UNJUDGEABLE',reason='no_track'),config=asdict(cfg))
    eligible.sort(key=lambda x:x[0],reverse=True);_,track,start=eligible[0]
    end=endpoint(track[start:],cfg)
    position=estimate_position(track,end['frame_index']-1,cfg) if end['frame_index'] is not None else None
    comparison=compare_zone(position,zone) if position else dict(preview='UNJUDGEABLE',reason='endpoint_missing')
    if end.get('timing_uncertainty_frames',0)>1:
        comparison=dict(comparison,preview='UNJUDGEABLE',reason='endpoint_timing_uncertain')
    return dict(status='motion_track',track=track,flight_start_frame=track[start]['frame_index'],endpoint=end,
                position=position,comparison=comparison,alternative_track_count=len(eligible)-1,config=asdict(cfg),
                selection='highest_scoring_smooth_moving_track',offline=True)

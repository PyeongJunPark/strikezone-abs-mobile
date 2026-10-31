"""Single-camera, receiver-proximity reference call, not a plate-depth judgment."""
import math
import numpy as np


def distance_box(point, box):
    x,y=point;l,t,r,b=box
    return math.hypot(max(l-x,0,x-r),max(t-y,0,y-b))


def reference_call(track, zone, fps=30, receiver=None, detections=None, end_frame=None):
    if len(zone)!=4 or not all(math.isfinite(v) for v in zone) or zone[0]>=zone[2] or zone[1]>=zone[3] or fps<=0:
        raise ValueError('Invalid zone or FPS')
    l,t,r,b=zone;w=r-l;h=b-t
    derived=receiver is None
    receiver=receiver or [l-1.5*w,t-.35*h,r+1.5*w,b+.8*h]
    points=[];seen=set()
    for p in sorted(track,key=lambda p:p['frame_index']):
        f=p['frame_index'];xy=p.get('center_xy')
        if f in seen or p.get('observed') is False or p.get('source_frame_repeated') or xy is None or len(xy)!=2 or not all(math.isfinite(v) for v in xy):continue
        points.append(p);seen.add(f)
    result=dict(method='receiver_prearrival_reference_v1',receiver_region=receiver,receiver_source='zone_derived' if derived else 'manual',zone=zone,validated=False,confirmed_catch=False,confirmed_plate_crossing=False,confidence='low')
    if not points:return dict(result,preview='UNJUDGEABLE',reason='no_ball_observations',position=None)
    def velocity(a,z):return (np.array(z['center_xy'])-a['center_xy'])/(z['frame_index']-a['frame_index'])
    max_gap=max(1,round(.1*fps));event=None
    # End the judgment window at the first sustained exit from the receiver
    # search area. Keep tracking elsewhere, but do not use a later rebound.
    passage_event=None
    for i in range(1,len(points)-2):
        p,z,q=points[i:i+3]
        if distance_box(p['center_xy'],receiver)!=0:continue
        d1=distance_box(z['center_xy'],receiver);d2=distance_box(q['center_xy'],receiver)
        if d1<=0 or d2<=d1 or q['frame_index']-p['frame_index']>max_gap*3:continue
        if not any(distance_box(a['center_xy'],receiver)>0 for a in points[:i]):continue
        passage_event=dict(frame=p['frame_index']+1,reason='first_receiver_passage_end',confirmed_at=q['frame_index'],
                           uncertainty_interval=[p['frame_index'],z['frame_index']],confirmed_contact=False,
                           excluded_tail_frames=[a['frame_index'] for a in points[i+1:]])
        points=points[:i+1];break
    # A short occlusion can hide the first turn. Do not interpolate across it
    # and then prefer a later, fully visible bounce.
    for i in range(2,len(points)-2):
        pre,a,p,z,q=points[i-2:i+3]
        gap=z['frame_index']-p['frame_index']
        if not(max_gap<gap<=max_gap*3):continue
        # A gap alone far from the receiver is not an arrival/contact cue.
        if distance_box(p['center_xy'],receiver)>max(8.,w*.3):continue
        if max(a['frame_index']-pre['frame_index'],p['frame_index']-a['frame_index'],q['frame_index']-z['frame_index'])>max_gap:continue
        v0=velocity(pre,a);v1=velocity(a,p);v2=velocity(z,q);speed=np.linalg.norm(v1)
        if speed<max(1.,w*.03) or np.linalg.norm(v2)<speed*.2:continue
        if np.dot(v0,v1)<=0:continue
        cosine=float(np.dot(v1,v2)/(speed*np.linalg.norm(v2)))
        if cosine<math.cos(math.radians(65)):
            event=dict(frame=p['frame_index']+1,reason='direction_change_across_gap',confirmed_at=q['frame_index'],
                       uncertainty_interval=[p['frame_index'],z['frame_index']],confirmed_contact=False,
                       excluded_tail_frames=[a['frame_index'] for a in points[i+1:]])
            points=points[:i+1];break
    # Separate moving flight from a spatially disconnected, stationary tail.
    # This is a tracking discontinuity, not evidence of a catch or bounce.
    for i in range(2,len(points)-3):
        if event is not None:break
        pre,a,p=points[i-2:i+1];tail=points[i+1:i+4]
        gap=tail[0]['frame_index']-p['frame_index']
        v0=velocity(pre,a);v1=velocity(a,p);speed=np.linalg.norm(v1)
        if not (1<=gap<=max_gap*3) or speed<max(1.,w*.03):continue
        if max(a['frame_index']-pre['frame_index'],p['frame_index']-a['frame_index'])>max_gap:continue
        if np.linalg.norm(v0-v1)>speed*.6:continue
        tail_spread=max(math.dist(tail[0]['center_xy'],q['center_xy']) for q in tail[1:])
        jump=np.array(tail[0]['center_xy'])-p['center_xy']
        residual=np.linalg.norm(jump-v1*gap)
        if tail_spread<=max(2.,w*.08) and np.dot(jump,v1)<0 and residual>max(w*.5,speed*gap*1.5):
            event=dict(frame=p['frame_index']+1,reason='flight_track_discontinuity',confirmed_at=tail[-1]['frame_index'],
                       uncertainty_interval=[p['frame_index'],tail[0]['frame_index']],excluded_tail_frames=[q['frame_index'] for q in points[i+1:]],confirmed_contact=False)
            points=points[:i+1];break
    # A sustained sharp turn can happen outside the receiver ROI as well.
    if event is None:
        for i in range(2,len(points)-2):
            pre,a,p,z,q=points[i-2:i+3]
            if max(y['frame_index']-x['frame_index'] for x,y in zip([pre,a,p,z],[a,p,z,q]))>max_gap:continue
            v0=velocity(pre,a);v1=velocity(a,p);v2=velocity(p,z);v3=velocity(z,q)
            speed=np.linalg.norm(v1)
            if speed<max(1.,w*.03) or min(np.linalg.norm(v2),np.linalg.norm(v3))<speed*.2:continue
            if np.linalg.norm(v0-v1)>speed*.6:continue
            cosine=float(np.dot(v1,v2)/(speed*np.linalg.norm(v2)))
            continuity=float(np.dot(v2,v3)/(np.linalg.norm(v2)*np.linalg.norm(v3)))
            if cosine<math.cos(math.radians(65)) and continuity>math.cos(math.radians(40)):
                event=dict(frame=p['frame_index'],reason='sustained_trajectory_change',confirmed_at=q['frame_index'],confirmed_contact=False);break
    for i in range(2,len(points)-1):
        if event is not None:break
        a,p,z=points[i-1:i+2]
        if distance_box(p['center_xy'],receiver)>0 or max(p['frame_index']-a['frame_index'],z['frame_index']-p['frame_index'])>max_gap:continue
        before=velocity(points[i-2],p);after=velocity(p,z);s0=np.linalg.norm(before);s1=np.linalg.norm(after)
        if s0<max(.5,w*.015):continue
        angle=math.degrees(math.acos(float(np.clip(np.dot(before,after)/(s0*s1),-1,1)))) if s1>1e-6 else 0
        if angle>=65 and i+2<len(points):
            confirmation=points[i+2]
            if confirmation['frame_index']-z['frame_index']<=max_gap and np.dot(after,velocity(z,confirmation))>0:
                event=dict(frame=p['frame_index'],reason='direction_change_near_receiver',confirmed_at=confirmation['frame_index']);break
        if s1<s0*.25 and i+2<len(points):
            q=points[i+2]
            if q['frame_index']-z['frame_index']<=max_gap and np.linalg.norm(velocity(z,q))<s0*.3:
                event=dict(frame=z['frame_index'],reason='slowdown_near_receiver',confirmed_at=q['frame_index']);break
    # A track ending is not by itself proof of disappearance: examine detections.
    if event is None and len(points)>=3 and detections is not None:
        p=points[-1];f=p['frame_index'];by={r['frame_index']:r for r in detections}
        if distance_box(p['center_xy'],receiver)==0 and end_frame is not None and f+3<end_frame and all(k in by for k in range(f+1,f+4)):
            vel=velocity(points[-3],p);missing=0
            for k in range(f+1,f+4):
                pred=np.array(p['center_xy'])+vel*(k-f)
                local=any(math.dist(q['center_xy'],pred)<=max(w*.35,np.linalg.norm(vel)*2) for q in by[k].get('candidates',[]) if q.get('confidence',1)>=.08)
                missing+=not local
            if missing>=2 and np.linalg.norm(vel)>=max(.5,w*.015):event=dict(frame=f+1,reason='disappearance_near_receiver',confirmed_at=f+3)
    if event is None and passage_event is not None:event=passage_event
    position=None
    if event:
        target=event['frame']-1
        exact=next((p for p in points if p['frame_index']==target),None)
        if exact:position=dict(frame_index=target,center_xy=exact['center_xy'],source='observed')
        else:
            pre=[p for p in points if p['frame_index']<target];post=[p for p in points if p['frame_index']>target]
            if pre and post and post[0]['frame_index']-pre[-1]['frame_index']<=max_gap:
                a,z=pre[-1],post[0];fraction=(target-a['frame_index'])/(z['frame_index']-a['frame_index']);xy=np.array(a['center_xy'])+fraction*(np.array(z['center_xy'])-a['center_xy']);position=dict(frame_index=target,center_xy=xy.tolist(),source='interpolated')
            elif len(pre)>=2 and target-pre[-1]['frame_index']<=min(2,max_gap):
                xy=np.array(pre[-1]['center_xy'])+velocity(pre[-2],pre[-1])*(target-pre[-1]['frame_index']);position=dict(frame_index=target,center_xy=xy.tolist(),source='short_extrapolation')
    if position is None:
        anchor=[(l+r)/2,b];chosen=min(points,key=lambda p:(distance_box(p['center_xy'],receiver),math.dist(p['center_xy'],anchor)))
        position=dict(frame_index=chosen['frame_index'],center_xy=chosen['center_xy'],source='observed');reason='closest_observation_to_receiver';event=None
    else:reason=event['reason']
    x,y=position['center_xy'];inside=l<=x<=r and t<=y<=b
    margin=min(x-l,r-x,y-t,b-y) if inside else -distance_box([x,y],zone)
    tolerance=max(3.,w*.08)
    preview='STRIKE_ESTIMATE' if inside or abs(margin)<=tolerance else 'BALL_ESTIMATE'
    warnings=['screen_position_proxy_not_plate_crossing']
    if derived:warnings.append('receiver_region_derived_from_zone')
    if event is None:warnings.append('arrival_not_found_fallback')
    if reason in ('direction_change_near_receiver','sustained_trajectory_change'):warnings.append('bounce_or_deflection_possible')
    if reason=='flight_track_discontinuity':warnings.append('contact_time_unknown_last_flight_observation')
    if position['source']!='observed':warnings.append('position_estimated')
    if len(points)<4:warnings.append('few_observations')
    if distance_box(position['center_xy'],receiver)>0:warnings.append('selected_position_outside_receiver')
    confidence='medium' if event and reason=='disappearance_near_receiver' and position['source']=='observed' and len(points)>=5 else 'low'
    return dict(result,preview=preview,reason=reason,position=position,event=event,confidence=confidence,confidence_kind='heuristic_not_probability',edge_margin_px=margin,boundary_hit=abs(margin)<=tolerance,boundary_policy='strike',boundary_tolerance_px=tolerance,warnings=warnings,observations=len(points))


def prioritized_reference_call(track, zone, fps=30, receiver=None, detections=None,
                               end_frame=None, size_rows=None, image_size=None):
    """Observed arrival > size/trajectory forecast > nearest observation.

    An offscreen *computed* endpoint gives a low-confidence BALL_ESTIMATE by
    product policy. It is never marked as a physical crossing or confirmed ball.
    """
    from strikezone.ball.size_forecast import forecast
    from strikezone.ball.track_filter import filter_track
    filtering = filter_track(track, fps)
    track = filtering['track']
    base = reference_call(track, zone, fps, receiver, detections, end_frame)
    base['track_filter'] = {k:v for k,v in filtering.items() if k != 'track'}
    base.update(method='observed_then_prediction_reference_v2',decision_source='nearest_observation')
    if base['position'] is None:
        base['decision_source']='unavailable'
        return base
    l,t,r,b=zone;w=r-l;h=b-t
    # Narrower than the search ROI: disappearance in the wide search area alone
    # must not turn an early tracking loss into a credible arrival.
    arrival_region=[l-.65*w,t-.2*h,r+.65*w,b+.4*h]
    base['arrival_acceptance_region']=arrival_region
    valid=[p for p in track if p.get('observed',True) and not p.get('source_frame_repeated',False) and p.get('center_xy') is not None and all(math.isfinite(v) for v in p['center_xy'])]
    valid.sort(key=lambda p:p['frame_index'])
    if base.get('event'):
        base['decision_source']='observed_flight_end' if base['reason'] in ('flight_track_discontinuity','direction_change_across_gap','first_receiver_passage_end') else 'observed_arrival'
        return base
    if valid and distance_box(base['position']['center_xy'],arrival_region)<=max(8.,w*.2):
        base['decision_source']='observed_receiver_proximity'
        base['confidence']='low'
        return base
    base['early_loss_suspected']=True
    base['reason']='closest_observation_to_receiver'
    base['event']=None
    base['confidence']='low'
    by={p['frame_index']:p for p in valid}
    rows=[]
    for row in size_rows or []:
        f=row['frame'];width=row.get('perpendicular_px')
        if f not in by or row.get('repeated') or width is None or not math.isfinite(width) or width<=0:continue
        rows.append(dict(frame=f,diameter_px=width,center_xy=by[f]['center_xy']))
    model=forecast(rows,w,fps,observations=None,allow_past=True)
    c=model.get('candidate')
    base['forecast_status']=model['status']
    if c is None or not all(math.isfinite(v) for v in [c['frame'],*c['center_xy']]):
        base['prediction_unavailable_reason']=model['status']
        return base
    # No claiming a pre-observation crossing as an arrival prediction.
    if c['frame']<min(by):
        base['prediction_unavailable_reason']='before_first_observation'
        return base
    x,y=c['center_xy'];outside=image_size is not None and not (0<=x<image_size[0] and 0<=y<image_size[1])
    inside=l<=x<=r and t<=y<=b
    margin=min(x-l,r-x,y-t,b-y) if inside else -distance_box([x,y],zone)
    tolerance=max(3.,w*.08)
    preview='BALL_ESTIMATE' if outside else ('STRIKE_ESTIMATE' if inside or abs(margin)<=tolerance else 'BALL_ESTIMATE')
    warnings=list(base.get('warnings',[]))+['early_tracking_loss','unvalidated_trajectory_forecast']+model.get('flags',[])
    if outside:warnings.append('offscreen_forecast_is_not_physical_ball_proof')
    return dict(base,preview=preview,reason='offscreen_prediction' if outside else 'trajectory_prediction_after_early_loss',
                decision_source='predicted_arrival',position=dict(frame_index=c['frame'],center_xy=c['center_xy'],source='predicted'),
                event=None,confidence='low',edge_margin_px=margin,boundary_hit=abs(margin)<=tolerance,boundary_policy='strike',warnings=warnings,forecast=model,
                observed_fallback=base['position'],offscreen_prediction=outside)

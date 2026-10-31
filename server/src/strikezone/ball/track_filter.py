"""Offline stationary-clutter and isolated-spike filter; input stays intact.

Requires two supporting observations on each side. Sustained turns, endpoints,
long gaps and size-only anomalies are deliberately retained for review.
Persistent static prefixes and spatially disconnected static tails are excluded;
continuous flight ending in a stop remains available as arrival evidence.
"""
import math
import numpy as np


def stationary_radius(points):
    diameters=[min(b[2]-b[0],b[3]-b[1]) for p in points if (b:=p.get('bbox_xyxy'))]
    return max(2.,min(6.,.35*float(np.median(diameters)))) if diameters else 2.


def stationary(points, fps=30):
    """Require elapsed time and distinct real observations, not just proximity."""
    if len(points)<4 or points[-1]['frame_index']-points[0]['frame_index']<.2*fps:return False
    if any(p.get('observed') is False or p.get('source_frame_repeated') for p in points):return False
    xy=np.array([p['center_xy'] for p in points],float);frames=np.array([p['frame_index'] for p in points])
    return bool(np.isfinite(xy).all() and np.all(np.diff(frames)>0) and max(np.diff(frames))<=max(2,round(.15*fps)) and np.max(np.linalg.norm(xy-xy[0],axis=1))<=stationary_radius(points))


def stationary_rejections(points,fps):
    removed=set();records=[];i=0
    while i<len(points)-3:
        end=i+4
        while end<=len(points) and points[end-1]['frame_index']-points[i]['frame_index']<.2*fps:end+=1
        if end>len(points) or not stationary(points[i:end],fps):i+=1;continue
        radius=stationary_radius(points[i:end]);anchor=np.array(points[i]['center_xy'],float)
        while end<len(points) and 0<points[end]['frame_index']-points[end-1]['frame_index']<=max(2,round(.15*fps)) and math.dist(points[end]['center_xy'],anchor)<=radius:end+=1
        reason=None
        if i==0:reason='stationary_prefix_or_entire_track'
        elif i>=2:
            a,b=points[i-2:i];dt=b['frame_index']-a['frame_index'];gap=points[i]['frame_index']-b['frame_index']
            if dt>0 and gap>0:
                v=(np.array(b['center_xy'])-a['center_xy'])/dt;jump=anchor-b['center_xy'];speed=np.linalg.norm(v)
                residual=np.linalg.norm(jump-v*gap)
                # A normal arrival can stop. Only detach a stationary tail when
                # its connection contradicts the incoming flight.
                if speed>=1 and ((np.dot(jump,v)<0 and np.linalg.norm(jump)>3*radius) or residual>max(4*radius,2*speed*gap)):
                    reason='disconnected_stationary_tail'
        if reason:
            for j in range(i,end):
                removed.add(j);records.append(dict(observation=points[j],reason=reason,radius_px=radius))
        i=end
    return removed,records


def filter_track(track, fps=30):
    points = sorted(track, key=lambda p: p['frame_index'])
    removed,rejected=stationary_rejections(points,fps)
    max_gap = max(2, round(fps * .1))
    for i in range(2, len(points)-2):
        window = points[i-2:i+3]
        if any(p.get('observed') is False or p.get('source_frame_repeated') for p in window):
            continue
        frames = np.array([p['frame_index'] for p in window], dtype=float)
        xy = np.array([p.get('center_xy', [math.nan, math.nan]) for p in window], dtype=float)
        gaps = np.diff(frames)
        if not np.isfinite(xy).all() or min(gaps) <= 0 or max(gaps) > max_gap:
            continue
        left = (xy[1]-xy[0])/gaps[0]
        right = (xy[4]-xy[3])/gaps[3]
        speed = max(np.linalg.norm(left), np.linalg.norm(right), .5)
        # The motion before and after the suspect must agree, including bridging.
        bridge = (xy[3]-xy[1])/(frames[3]-frames[1])
        if max(np.linalg.norm(left-right), np.linalg.norm(left-bridge), np.linalg.norm(right-bridge)) > .65*speed:
            continue
        predicted = xy[1]+bridge*(frames[2]-frames[1])
        residual = float(np.linalg.norm(xy[2]-predicted))
        boxes = [p.get('bbox_xyxy') for p in (window[1], window[3])]
        diameters = [max(b[2]-b[0], b[3]-b[1]) for b in boxes if b]
        threshold = max(6., 1.5*float(np.median(diameters)) if diameters else 6., 1.5*speed*max(gaps[1:3]))
        if residual <= threshold or any(j in removed for j in range(i-2, i+3)):
            continue
        removed.add(i)
        rejected.append(dict(observation=points[i], reason='isolated_position_spike', residual_px=residual,
                             threshold_px=threshold, expected_xy=predicted.tolist()))
    return dict(track=[p for i,p in enumerate(points) if i not in removed], rejected=rejected,
                input_count=len(points), removed_count=len(removed), method='stationary_and_isolated_spike_v2')

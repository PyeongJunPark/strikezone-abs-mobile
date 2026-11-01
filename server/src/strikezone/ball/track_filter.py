"""Offline stationary-clutter and isolated-spike filter; input stays intact.

Isolated spikes require two supporting observations on each side. Stalled jumps
require four smooth incoming observations and two stalled observations.
Sustained moving turns, long gaps and size-only anomalies remain for review.
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


def stalled_jump_rejections(points, fps):
    """Quarantine an implausible jump followed by a stop, not a moving rebound.

    Four smooth incoming observations and two stalled observations are required.
    A later point may rejoin only within a short prediction window. Otherwise
    the rest is unverified after tracking loss, not necessarily a false ball.
    """
    max_gap = max(2, round(.1 * fps))
    for i in range(4, len(points)-1):
        window = points[i-4:i+2]
        if any(p.get('observed') is False or p.get('source_frame_repeated') for p in window):
            continue
        frames = np.array([p['frame_index'] for p in window], float)
        xy = np.array([p['center_xy'] for p in window], float)
        gaps = np.diff(frames)
        if not np.isfinite(xy).all() or min(gaps) <= 0 or max(gaps) > max_gap:
            continue
        velocities = np.diff(xy[:4], axis=0) / gaps[:3, None]
        v = velocities[-1]; speed = np.linalg.norm(v)
        if speed < 1 or max(np.linalg.norm(velocities-v, axis=1)) > .35*speed:
            continue
        expected = xy[3] + v*gaps[3]
        residual = float(np.linalg.norm(xy[4]-expected))
        boxes = [p.get('bbox_xyxy') for p in window[:4]]
        diameters = [min(b[2]-b[0], b[3]-b[1]) for b in boxes if b]
        diameter = float(np.median(diameters)) if diameters else 4.
        threshold = max(8., 2*diameter, 1.5*speed*gaps[3])
        if residual <= threshold or np.linalg.norm(xy[4]-xy[3]) <= 2*speed*gaps[3]:
            continue
        if np.linalg.norm(xy[5]-xy[4])/gaps[4] > .25*speed:
            continue
        # Require two moving observations to rejoin the original flight.
        rejoin = len(points)
        for j in range(i+2, len(points)-1):
            a,b = points[j:j+2]
            dt = a['frame_index']-frames[3]
            gap = b['frame_index']-a['frame_index']
            if dt > max(3, round(.15*fps)):break
            if gap <= 0 or gap > max_gap:continue
            if any(p.get('observed') is False or p.get('source_frame_repeated') for p in (a,b)):continue
            va = (np.array(b['center_xy'])-a['center_xy'])/gap
            if math.dist(a['center_xy'], xy[3]+v*dt) <= max(2*diameter, .6*speed) and np.linalg.norm(va-v) <= .5*speed:
                rejoin=j;break
        records = [dict(observation=points[j], reason='disconnected_stalled_segment' if j<i+2 else 'unverified_after_discontinuity',
                        residual_px=residual, threshold_px=threshold, expected_xy=expected.tolist()) for j in range(i,rejoin)]
        loss = None if rejoin<len(points) else dict(last_valid_frame=points[i-1]['frame_index'], first_rejected_frame=points[i]['frame_index'], confirmed_at=points[i+1]['frame_index'])
        return set(range(i,rejoin)), records, loss
    return set(), [], None


def filter_track(track, fps=30):
    points = sorted(track, key=lambda p: p['frame_index'])
    removed,rejected,loss=stalled_jump_rejections(points,fps)
    static_removed,static_rejected=stationary_rejections(points,fps)
    rejected.extend(r for r in static_rejected if points.index(r['observation']) not in removed)
    removed.update(static_removed)
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
                input_count=len(points), removed_count=len(removed), continuity_loss=loss, method='stationary_spike_and_stalled_jump_v3')

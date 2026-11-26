"""White contour proposals; uncertain automatic geometry requires confirmation."""
import math
import cv2
import numpy as np


def locate(frame, mask, batter, manual_edge=None):
    h,w=frame.shape[:2]
    out=dict(status='missing',confidence=None,reason='no_detection',source='auto',
             front_edge_xy=None,corners_xy=None,candidates=[],
             suggested_corners_xy=None,suggested_front_edge_xy=None)
    if manual_edge is not None:
        if (len(manual_edge)!=2 or any(len(p)!=2 for p in manual_edge) or
                any(not math.isfinite(v) for p in manual_edge for v in p) or
                any(not (0<=x<w and 0<=y<h) for x,y in manual_edge)):
            return dict(out,status='invalid',reason='invalid_manual_edge',source='manual')
        edge=sorted(manual_edge,key=lambda p:p[0])
        if edge[1][0]-edge[0][0]<2:
            return dict(out,status='invalid',reason='invalid_manual_edge',source='manual')
        # Reject evidence anywhere along the marked segment, not just its endpoints.
        line=np.zeros((h,w),np.uint8)
        cv2.line(line,tuple(map(round,edge[0])),tuple(map(round,edge[1])),255,3)
        if np.any((line>0)&(mask>0)):
            return dict(out,status='invalid',reason='masked_edge',source='manual')
        return dict(out,status='ok',reason=None,source='manual',front_edge_xy=edge)
    if batter is None:
        return dict(out,reason='batter_missing')
    x1,y1,x2,y2=batter['bbox_xyxy'];bh=y2-y1
    left=max(0,int(x1-bh));right=min(w,int(x2+bh))
    top=max(0,int(y2-bh*0.3));bottom=min(h,int(y2+bh*0.25))
    hsv=cv2.cvtColor(frame,cv2.COLOR_BGR2HSV)
    binary=cv2.inRange(hsv,np.array([0,0,150]),np.array([179,80,255]))
    region=np.zeros_like(binary);region[top:bottom,left:right]=255
    binary=cv2.bitwise_and(binary,region)
    binary=cv2.morphologyEx(binary,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
    for contour in cv2.findContours(binary,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]:
        area=cv2.contourArea(contour)
        if not max(8,bh*bh*0.0003)<=area<=bh*bh*0.15:continue
        x,y,bw,bh2=cv2.boundingRect(contour)
        if bw<5 or bh2<2 or not 0.4<bw/bh2<12:continue
        if mask[y:y+bh2,x:x+bw].any():continue
        polygon=cv2.approxPolyDP(contour,0.035*cv2.arcLength(contour,True),True)
        if not 4<=len(polygon)<=6 or not cv2.isContourConvex(polygon):continue
        out['candidates'].append(dict(polygon_xy=polygon[:,0,:].tolist(),
                                      bbox_xyxy=[x,y,x+bw,y+bh2],confidence=None,
                                      reason='front_edge_unverified'))
    if out['candidates']:out['reason']='manual_confirmation_required'
    # White shoes, lines and partial plate contours cannot establish a front edge.
    # A pentagon that fits the plate shape is only a suggestion for one-click
    # confirmation; the status stays unconfirmed.
    for candidate in out['candidates']:
        candidate['verification']=verify_polygon(candidate['polygon_xy'],(w,h))
    verified=[c for c in out['candidates'] if c['verification']['status']=='ok']
    if len(verified)==1:
        best=verified[0]['verification']
        out.update(reason='verified_candidate_needs_confirmation',suggested_corners_xy=best['ordered_xy'],
                   suggested_front_edge_xy=best['front_edge_xy'])
    elif len(verified)>1:
        out['reason']='ambiguous_verified_candidates'
    return out


def verify_polygon(polygon, image_size=None):
    """Try every corner order of a 5-vertex contour against the plate shape.

    Returns the best plate-homography fit (lowest reprojection error) with the
    corners in marking order, or an invalid record. Only five vertices carry a
    shape check: any four points fit a homography exactly.
    """
    from .homography import fit_plate
    points=[[float(x),float(y)] for x,y in polygon]
    if len(points)!=5:
        return dict(status='invalid',reason='needs_five_vertices',ordered_xy=None,front_edge_xy=None,
                    reprojection_error_px=None)
    best=None
    for sequence in (points,points[::-1]):
        for i in range(5):
            ordered=sequence[i:]+sequence[:i]
            if ordered[0][0]>ordered[1][0]:continue
            fit=fit_plate(ordered,image_size)
            if fit['status']!='ok':continue
            # The front edge is the longest side of the pentagon in practice.
            sides=[np.hypot(*np.subtract(ordered[k],ordered[(k+1)%5])) for k in range(5)]
            if sides[0]<max(sides)*.999:continue
            if best is None or fit['reprojection_error_px']<best['reprojection_error_px']:
                best=dict(fit,ordered_xy=ordered)
    if best is None:
        return dict(status='invalid',reason='shape_not_plate_like',ordered_xy=None,front_edge_xy=None,
                    reprojection_error_px=None)
    return {k:best[k] for k in ('status','reason','ordered_xy','front_edge_xy','reprojection_error_px','px_per_cm_front','warnings')}


def zone_candidate(pose,plate,frame_index):
    out=dict(status='missing',confidence=None,reason='incomplete_geometry',bbox_xyxy=None,
             reference_frame_index=frame_index,method='pose-midpoint-v1',
             geometry='image_rect_approx_v1',locked=False)
    if pose['status']!='ok' or plate['status']!='ok':return out
    edge=plate['front_edge_xy'];left=min(p[0] for p in edge);right=max(p[0] for p in edge)
    return dict(out,status='ok',reason=None,bbox_xyxy=[left,pose['top_y'],right,pose['bottom_y']])

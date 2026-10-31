"""Offline ball masks from a detection and temporally estimated background.

Diameters describe visible silhouettes, not calibrated physical sphere sizes.
The enclosing circle preserves every selected pixel corner, including blur.
"""
import cv2
import numpy as np


def measure_ball_mask(patch, background, box_size):
    h, w = patch.shape[:2]
    empty = np.zeros((h, w), np.uint8)
    result = dict(mask=empty, diameter_px=None, horizontal_width_px=None,
                  circle_center=None, reason='no_foreground', blur_ratio=None)
    if background.shape != patch.shape:
        result['reason'] = 'background_shape_mismatch'
        return result
    # Colour difference includes dark seams/shadows, unlike brightness-only masks.
    delta = np.max(np.abs(patch.astype(np.float32)-background.astype(np.float32)), axis=2)
    yy, xx = np.indices((h, w)); cx, cy = w//2, h//2
    bw, bh = box_size
    rx, ry = max(4, bw*.7+2), max(4, bh*.7+2)
    support = (abs(xx-cx)<=rx) & (abs(yy-cy)<=ry)
    core = (abs(xx-cx)<=max(2,bw*.3)) & (abs(yy-cy)<=max(2,bh*.3))
    outer = ~support
    noise = delta[outer]
    noise_level = float(np.median(noise)) if noise.size else 0
    mad = float(np.median(np.abs(noise-noise_level))) if noise.size else 0
    peak = float(np.percentile(delta[core],90))
    threshold = max(8., noise_level+3*max(1.,mad), peak*.22)
    result.update(contrast=peak, threshold=threshold)
    if peak < threshold*1.25:
        result['reason']='weak_temporal_contrast'; return result
    binary = ((delta>=threshold)&support).astype(np.uint8)
    # Close tiny holes before filling interior seams. No erosion/shrink operation.
    binary = cv2.morphologyEx(binary,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
    n, labels, stats, centers = cv2.connectedComponentsWithStats(binary,8)
    options=[]
    for k in range(1,n):
        x,y,sw,sh,area=stats[k]
        dist=np.linalg.norm((centers[k]-[cx,cy])/[max(bw/2,2),max(bh/2,2)])
        if area>=3 and dist<=1.:
            options.append((dist,k))
    if not options:return result
    _,k=min(options); selected=(labels==k).astype(np.uint8)*255
    contours,_=cv2.findContours(selected,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(selected,contours,-1,255,cv2.FILLED)
    ys,xs=np.where(selected)
    result['mask']=selected
    # A boundary touch means that a glove/body/background may be merged, or
    # the crop is insufficient. Do not silently turn a clipped mask into size.
    if xs.min()==0 or ys.min()==0 or xs.max()==w-1 or ys.max()==h-1 or np.any(selected[~support]):
        result['reason']='mask_touches_search_boundary';return result
    if np.any((abs(xs-cx)>=rx-1)|(abs(ys-cy)>=ry-1)):
        result['reason']='mask_touches_search_boundary';return result
    points=np.column_stack([xs,ys]).astype(np.float32)
    corners=np.concatenate([points+offset for offset in np.array([[-.5,-.5],[-.5,.5],[.5,-.5],[.5,.5]],np.float32)])
    center,radius=cv2.minEnclosingCircle(corners)
    width=float(xs.max()-xs.min()+1);height=float(ys.max()-ys.min()+1)
    result.update(diameter_px=2*float(radius),horizontal_width_px=width,
                  circle_center=list(center),blur_ratio=max(width,height)/min(width,height),reason='measured_silhouette')
    return result

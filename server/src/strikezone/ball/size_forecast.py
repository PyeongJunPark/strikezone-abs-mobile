"""Five-observation weak-perspective flight forecast; not calibrated 3D physics.

q=1/diameter=a+b*t approximates constant optical-depth speed.
x*q and y*q are quadratic in time, approximating constant transverse
acceleration under pinhole projection. Acceleration is fitted, not fixed to g.
"""
import math
import numpy as np


def forecast(rows, plate_width, fps=30, observations=5, allow_past=False):
    if not math.isfinite(plate_width) or plate_width<=0 or not math.isfinite(fps) or fps<=0 or (observations is not None and observations<3):
        raise ValueError('Invalid scale, FPS or observation count')
    usable=[];seen=set()
    for r in sorted(rows,key=lambda r:r['frame']):
        d=r.get('diameter_px');xy=r.get('center_xy')
        if r.get('repeated') or r['frame'] in seen or d is None or not math.isfinite(d) or d<=0:continue
        if xy is None or len(xy)!=2 or not all(math.isfinite(v) for v in xy):continue
        seen.add(r['frame']);usable.append(r)
    observations = len(usable) if observations is None else observations
    if observations<3 or len(usable)<observations:return dict(status='insufficient_observations',observations=len(usable),candidate=None)
    train=usable[:observations];base=train[0]['frame'];t=np.array([(r['frame']-base)/fps for r in train]);d=np.array([r['diameter_px'] for r in train]);q=1/d;xy=np.array([r['center_xy'] for r in train]);coeff=np.polyfit(t,q,1)
    result=dict(status='fitted',training_frames=[r['frame'] for r in train],training_end=train[-1]['frame'],base_frame=base,fps=fps,inverse_diameter_coefficients=coeff.tolist(),candidate=None,flags=[],model='linear_inverse_diameter_quadratic_projected_position',calibrated_3d=False)
    qfit=np.polyval(coeff,t)
    if np.any(qfit<=0):return dict(result,status='invalid_size_fit')
    # Fit numerator using the fitted depth curve, so noisy diameter samples do
    # not directly multiply noise into the observed screen coordinates.
    numerator=np.column_stack([np.polyfit(t,xy[:,i]*qfit,2) for i in range(2)])
    posfit=np.column_stack([np.polyval(numerator[:,i],t)/qfit for i in range(2)])
    result.update(position_numerator_coefficients=numerator.tolist(),size_training_rmse_px=float(np.sqrt(np.mean((1/qfit-d)**2))),position_training_rmse_px=float(np.sqrt(np.mean(np.sum((posfit-xy)**2,axis=1)))))
    target=[plate_width*9/math.pi/17,plate_width*9.25/math.pi/17];result['target_diameter_px']=target
    if coeff[0]<=1e-10:return dict(result,status='not_shrinking')
    times=[(1/v-coeff[1])/coeff[0] for v in target];tc=(1/np.mean(target)-coeff[1])/coeff[0]
    if tc<t[-1] and not allow_past:return dict(result,status='crossing_before_model_ready',retrospective_frame=float(base+tc*fps))
    frame=float(base+tc*fps);qt=np.polyval(coeff,tc);position=[float(np.polyval(numerator[:,i],tc)/qt) for i in range(2)]
    result['candidate']=dict(frame=frame,frame_range_from_ball_spec=sorted(float(base+x*fps) for x in times),center_xy=position,diameter_px=float(np.mean(target)),source='forecast_from_first_observations')
    result['candidate']['temporal_relation']='past_estimate' if tc<t[-1] else 'future_prediction'
    if tc<0:result['flags'].append('crossing_before_first_observation')
    if len(train)<5:result['flags'].append('provisional_fewer_than_five_observations')
    if tc-t[-1]>1:result['flags'].append('beyond_one_second_horizon')
    if tc-t[-1]>3*(t[-1]-t[0]):result['flags'].append('extrapolation_over_three_training_spans')
    if result['size_training_rmse_px']>1:result['flags'].append('size_fit_rmse_over_1px')
    if result['position_training_rmse_px']>5:result['flags'].append('position_fit_rmse_over_5px')
    sensitivity=[]
    for i in range(len(t)):
        a,b=np.polyfit(np.delete(t,i),np.delete(q,i),1)
        if a<=1e-10:continue
        sensitivity.append(float(base+((1/np.mean(target)-b)/a)*fps))
    result['leave_one_out_candidate_frames']=sensitivity
    if len(sensitivity)<len(t) or max(sensitivity,default=frame)-min(sensitivity,default=frame)>10:result['flags'].append('unstable_leave_one_out_timing')
    result['status']='forecast_candidate' if not result['flags'] else 'unstable_forecast'
    return result


def forecast_updates(rows, plate_width, fps=30):
    """Replay causally: every new valid detection refits all observations so far.

    Three observations permit the quadratic fit; fewer than five are provisional.
    Predicted points never enter the observation history. Past crossing estimates
    remain estimates, not a confirmed crossing or catch event.
    """
    history=[];updates=[];seen=set()
    for row in sorted(rows,key=lambda r:r['frame']):
        d=row.get('diameter_px');xy=row.get('center_xy')
        if row.get('repeated') or row['frame'] in seen or d is None or not math.isfinite(d) or d<=0:continue
        if xy is None or len(xy)!=2 or not all(math.isfinite(v) for v in xy):continue
        seen.add(row['frame']);history.append(row)
        model=forecast(history,plate_width,fps,observations=None,allow_past=True)
        model.update(update_frame=row['frame'],observation_count=len(history))
        if model['candidate']:model['candidate']['source']='cumulative_observations'
        updates.append(model)
    return updates


def predict(model,frame):
    bounds=model.get('prediction_frame_bounds')
    if bounds is not None and not bounds[0]<=frame<=bounds[1]:return None
    t=(frame-model['base_frame'])/model['fps'];q=float(np.polyval(model['inverse_diameter_coefficients'],t))
    if q<=0:return None
    numerator=np.array(model['position_numerator_coefficients'])
    return dict(frame=frame,diameter_px=1/q,center_xy=[float(np.polyval(numerator[:,i],t)/q) for i in range(2)],source='predicted')


def forecast_width_updates(rows, plate_width, fps=30, image_size=None):
    """Use measured horizontal widths; suppress unsupported arrival estimates.

    Future extrapolation is limited to one observed time span and 0.25 seconds,
    whichever is shorter. This is an engineering bound, not an accuracy claim.
    Rejected candidates are diagnostic only and never become observations.
    """
    measured = [dict(r, diameter_px=r.get('horizontal_width_px')) for r in rows]
    updates = forecast_updates(measured, plate_width, fps)
    for model in updates:
        model['size_metric'] = 'mask_horizontal_width_px'
        frames = model.get('training_frames', [])
        if not frames:
            continue
        horizon = min(0.25*fps, frames[-1]-frames[0])
        model['prediction_frame_bounds'] = [frames[0], frames[-1]+horizon]
        model['max_extrapolation_frames'] = horizon
        candidate = model.get('candidate')
        if not candidate:
            continue
        reasons = list(model.get('flags', []))
        frame = candidate['frame']
        if not frames[0] <= frame <= frames[-1]+horizon:
            reasons.append('outside_supported_prediction_window')
        if image_size is not None:
            x,y = candidate['center_xy'];w,h = image_size
            if not (0<=x<w and 0<=y<h):
                reasons.append('predicted_position_outside_image')
        if reasons:
            model['rejected_candidate'] = candidate
            model['candidate'] = None
            model['rejection_reasons'] = reasons
            model['status'] = 'arrival_withheld'
    return updates

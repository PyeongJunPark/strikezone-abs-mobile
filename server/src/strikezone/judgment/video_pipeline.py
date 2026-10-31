"""Local offline video pipeline. Model paths and annotations are caller supplied."""
import json
import math
import subprocess
from pathlib import Path
import cv2
import numpy as np
from strikezone.pose.detector import PoseDetector
from strikezone.pose.selector import BatterSelector
from strikezone.pose.zone import analyze, valid_box
from strikezone.ball.manual_pitch import track_manual_pitch
from strikezone.ball.masking import measure_ball_mask
from strikezone.ball.blur_size import perpendicular_width
from strikezone.ball.track_filter import filter_track
from strikezone.judgment.receiver_reference import prioritized_reference_call
from strikezone.judgment.pose_session import PoseZoneSession


def metadata(path):
    cap=cv2.VideoCapture(str(path))
    result=dict(width=int(cap.get(3)),height=int(cap.get(4)),fps=cap.get(5),frames=int(cap.get(7)))
    cap.release()
    if min(result.values())<=0 or not all(math.isfinite(v) for v in result.values()):
        raise ValueError('영상을 읽을 수 없습니다.')
    return result


def validate_config(config, meta):
    w,h,n=meta['width'],meta['height'],meta['frames']
    points=config.get('plate_points')
    if not isinstance(points,list) or len(points)!=2 or any(len(p)!=2 or not all(type(x) in (int,float) and math.isfinite(x) for x in p) or not(0<=p[0]<w and 0<=p[1]<h) for p in points):
        raise ValueError('홈플레이트 좌우 두 점을 지정하세요.')
    if abs(points[0][0]-points[1][0])<5:raise ValueError('홈플레이트 폭이 너무 작습니다.')
    f=config.get('trigger_frame')
    if type(f) is not int or not 1<=f<n-2:raise ValueError('영상 안의 투구 시작 프레임을 선택하세요.')
    ref=config.get('reference_frame')
    if ref is not None and (type(ref) is not int or not max(0,f-round(5*meta['fps']))<=ref<f):raise ValueError('준비 자세 기준은 투구 시작 전 5초 이내 프레임으로 선택하세요.')
    for key in ('batter_roi','pitcher_roi'):
        if config.get(key) is not None and not valid_box(config[key],w,h):raise ValueError(f'{key} 범위 오류')
    height=config.get('manual_height')
    if height is not None and (len(height)!=2 or not all(type(v) in (int,float) and math.isfinite(v) for v in height) or not 0<=height[0]<height[1]<h):raise ValueError('수동 존 높이 범위 오류')
    fallback=config.get('fallback_height')
    if fallback is not None and (len(fallback)!=2 or not all(type(v) in (int,float) and math.isfinite(v) for v in fallback) or not 0<=fallback[0]<fallback[1]<h):raise ValueError('대체 존 높이 범위 오류')


class VideoPipeline:
    def __init__(self, pose_model, ball_model, ffmpeg, device='cpu'):
        from ultralytics import YOLO
        self.pose=PoseDetector(pose_model,device,960)
        self.ball=YOLO(str(ball_model));self.device=device;self.ffmpeg=str(ffmpeg)

    def run(self, source, config, output, progress=lambda value:None, cached_track=None, cached_detections=None):
        source=Path(source);output=Path(output);output.mkdir(parents=True,exist_ok=True)
        meta=metadata(source);validate_config(config,meta)
        (output/'config.json').write_text(json.dumps(config,indent=2),encoding='utf8')
        w,h,fps=meta['width'],meta['height'],meta['fps'];trigger=config['trigger_frame']
        start=max(0,trigger-round(2*fps));stop=min(meta['frames'],trigger+round(4*fps))
        if config.get('reference_frame') is not None:start=min(start,config['reference_frame'])
        cap=cv2.VideoCapture(str(source));cap.set(1,start);images={}
        for f in range(start,stop):
            ok,im=cap.read()
            if not ok:raise ValueError(f'프레임 {f} 읽기 실패')
            images[f]=im
        cap.release()
        points=sorted(config['plate_points'],key=lambda p:p[0]);left,right=points[0][0],points[1][0];pw=right-left;py=sum(p[1] for p in points)/2
        crop=[max(0,int(left-5*pw)),max(0,int(py-12*pw)),min(w,int(right+5*pw)),min(h,int(py+2*pw))]
        selector=BatterSelector();session=PoseZoneSession([left,right],fps,config.get('manual_height'),relaxed=True,fallback_height=config.get('fallback_height'))
        poses={};states={};sample_every=max(1,round(fps/10))
        for f in range(start,stop):
            if f==trigger:session.freeze(f)
            if f<trigger and ((f-start)%sample_every==0 or f==config.get('reference_frame')) and config.get('manual_height') is None:
                x,y,r,b=crop;people=self.pose.predict(images[f][y:b,x:r])
                restored=[]
                for person in people:
                    bb=person['bbox_xyxy'];person['bbox_xyxy']=[bb[0]+x,bb[1]+y,bb[2]+x,bb[3]+y]
                    for k in person['keypoints'].values():k['xy']=[k['xy'][0]+x,k['xy'][1]+y]
                    bb=person['bbox_xyxy']
                    if abs((bb[0]+bb[2])/2-(left+right)/2)<=4*pw and abs(bb[3]-py)<=3*pw:
                        restored.append(person)
                selected=selector.select(restored,f,w,h,config.get('batter_roi'),plate=[left,right,py],pitcher_roi=config.get('pitcher_roi'));candidate=selected['candidate']
                pose=analyze([candidate],candidate['bbox_xyxy'],w,h,threshold=.4) if candidate else dict(status='missing',reason=selected['reason'],keypoints={})
                if candidate:pose['motion_keypoints']=candidate['keypoints']
                poses[f]=dict(pose=pose,selection=selected)
                session.update(f,pose,selected['batter_id'],explicit_reference=f==config.get('reference_frame'))
            elif f<trigger and config.get('manual_height') is not None:
                session.update(f,{},None)
            states[f]=session.snapshot()
            if (f-start)%max(1,round(fps))==0:progress(f'타자 자세 분석 {f-start}/{stop-start}')
        zone=session.snapshot()['zone'];detections=[];track=[];sizes=[]
        if zone is None:
            result=dict(preview='UNJUDGEABLE',reason='missing_stable_stance',position=None,decision_source='unavailable',zone=None,confidence='low',confirmed_plate_crossing=False)
        else:
            if cached_track is None:
                # Remove mostly empty sky in portrait clips without narrowing
                # the horizontal flight corridor. Restore original coordinates.
                ball_top=max(0,int(py-16*pw)) if h>w else 0
                for begin in range(trigger,stop,8):
                    inds=list(range(begin,min(stop,begin+8)))
                    predictions=self.ball.predict([images[f][ball_top:] for f in inds],imgsz=1280,conf=.08,classes=[2],device=self.device,verbose=False)
                    for f,pred in zip(inds,predictions):
                        candidates=[]
                        for box,conf in zip(pred.boxes.xyxy.cpu().tolist(),pred.boxes.conf.cpu().tolist()):
                            l,t,r,b=box
                            t+=ball_top;b+=ball_top;box=[l,t,r,b]
                            if max(r-l,b-t)<=max(w,h)*.08:candidates.append(dict(center_xy=[(l+r)/2,(t+b)/2],bbox_xyxy=box,confidence=conf))
                        detections.append(dict(frame_index=f,candidates=candidates))
                    progress(f'공 검출 {min(stop,begin+8)-trigger}/{stop-trigger}')
                pitcher=config.get('pitcher_roi') or [0,0,w,h]
                region=[left-pw,zone[1]-pw,right+pw,py+pw]
                track=track_manual_pitch(detections,trigger,pitcher,region,fps,w,acquisition_seconds=3,defer_endpoint=True)['track']
            else:
                track=[p for p in cached_track if trigger<=p['frame_index']<stop]
                detections=cached_detections or []
            original_track=track
            for i,p in enumerate(track):
                f=p['frame_index'];x,y=map(round,p['center_xy']);patch=images[f][y-32:y+32,x-32:x+32];size=None
                if patch.shape==(64,64,3) and p.get('bbox_xyxy'):
                    ns=[images[k][y-32:y+32,x-32:x+32] for k in (f-6,f-3,f+3,f+6) if k in images]
                    if len(ns)>=2:
                        l,t,r,b=p['bbox_xyxy'];m=measure_ball_mask(patch,np.median(ns,axis=0).astype(np.uint8),(r-l,b-t))
                        motion=np.array(track[min(i+1,len(track)-1)]['center_xy'])-track[max(0,i-1)]['center_xy']
                        if m['diameter_px'] is not None:size=perpendicular_width(m['mask'],motion)['width_px']
                sizes.append(dict(frame=f,perpendicular_px=size,repeated=p.get('source_frame_repeated',False)))
            result=prioritized_reference_call(track,zone,fps,detections=detections or None,end_frame=stop,size_rows=sizes,image_size=(w,h))
            track=filter_track(original_track,fps)['track']
            result['input_track']=original_track
        result.update(zone_session=session.snapshot(),metadata=meta,trigger_frame=trigger,clip_start_frame=start,clip_end_frame=stop,
                      track=track,pose_frames=poses,zone_frames=states,track_source='cached_reviewed_track' if cached_track is not None else 'fresh_model_detection',
                      manual_pitch_start=True,selection_mode='manual_batter_roi' if config.get('batter_roi') else 'auto_heuristic',size_measurements=sizes)
        (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
        (output/'detections.json').write_text(json.dumps(detections),encoding='utf8')
        self.render(images,poses,states,track,result,points,output,progress)
        return result

    def render(self,images,poses,states,track,result,plate,output,progress):
        fps=result['metadata']['fps'];writer=cv2.VideoWriter(str(output/'render-temp.mp4'),cv2.VideoWriter_fourcc(*'mp4v'),fps,(1280,800))
        by={p['frame_index']:p for p in track};trail=[];last_pose=None;pose_frame=None
        excluded=set((result.get('event') or {}).get('excluded_tail_frames',[]))
        selected=result['position'];poster_done=False
        for f,raw in images.items():
            im=raw.copy();state=states[f];zone=state['zone']
            cv2.line(im,tuple(map(round,plate[0])),tuple(map(round,plate[1])),(255,200,0),3)
            if zone:cv2.rectangle(im,tuple(map(round,zone[:2])),tuple(map(round,zone[2:])),(0,255,255),2)
            if f in poses:last_pose=poses[f]['pose'];pose_frame=f
            # Never display a frozen historical skeleton as a current observation.
            if last_pose and pose_frame is not None and f-pose_frame<=max(1,round(fps/10)):
                for point in last_pose.get('keypoints',{}).values():
                    if point['confidence']>=.4:cv2.circle(im,tuple(map(round,point['xy'])),3,(255,0,255),-1)
                bb=last_pose.get('bbox_xyxy')
                if bb:cv2.rectangle(im,tuple(map(round,bb[:2])),tuple(map(round,bb[2:])),(255,0,255),2)
            if f in by:trail.append((by[f]['center_xy'],f in excluded))
            for xy,skip in trail:cv2.circle(im,tuple(map(round,xy)),3,(140,140,140) if skip else (0,255,0),-1)
            if selected and abs(f-selected['frame_index'])<=1:
                xy=selected['center_xy']
                if 0<=xy[0]<im.shape[1] and 0<=xy[1]<im.shape[0]:cv2.circle(im,tuple(map(round,xy)),10,(0,165,255),3)
            canvas=np.zeros((800,1280,3),np.uint8);h,w=im.shape[:2]
            if h>w:
                scale=min(460/w,680/h);sw,sh=round(w*scale),round(h*scale);canvas[:sh,:sw]=cv2.resize(im,(sw,sh))
                l=min(p[0] for p in plate);r=max(p[0] for p in plate);pw=r-l;py=sum(p[1] for p in plate)/2
                x0=max(0,int(l-4*pw));x1=min(w,int(r+4*pw));y0=max(0,int(py-10*pw));y1=min(h,int(py+2*pw));crop=im[y0:y1,x0:x1]
                sc=min(780/crop.shape[1],680/crop.shape[0]);cw,ch=round(crop.shape[1]*sc),round(crop.shape[0]*sc);canvas[:ch,480:480+cw]=cv2.resize(crop,(cw,ch))
            else:canvas[:680]=cv2.resize(im,(1280,680))
            labels=[f'f{f} / {f/fps:.3f}s | zone {state["phase"]} / {state["height_source"]}',
                    f'OFFLINE REFERENCE: {result["preview"]} | {result["reason"]}',
                    f'selected: {selected["frame_index"] if selected else "none"} ({selected["source"] if selected else "none"}) | GREEN ball / PURPLE pose / YELLOW zone / GRAY excluded',
                    f'zone ref {state["reference_frame"]} | lock {state.get("lock_reason")} | Stable stance then motion/pitch lock. Not ABS.']
            for i,label in enumerate(labels):cv2.putText(canvas,label,(10,707+i*25),0,.52,(255,255,255),1)
            if not poster_done and ((selected and f==round(selected['frame_index'])) or (not selected and f==result['trigger_frame'])):
                cv2.imencode('.jpg',canvas)[1].tofile(str(output/'poster.jpg'));poster_done=True
            writer.write(canvas)
        writer.release();progress('결과 영상 인코딩')
        subprocess.run([self.ffmpeg,'-y','-loglevel','error','-i',str(output/'render-temp.mp4'),'-an','-c:v','libx264','-preset','veryfast','-crf','22','-pix_fmt','yuv420p','-movflags','+faststart',str(output/'analysis.mp4')],check=True)
        cap=cv2.VideoCapture(str(output/'analysis.mp4'));count=0
        while cap.read()[0]:count+=1
        cap.release()
        if count!=len(images):raise RuntimeError('Output frame count mismatch')
        (output/'validation.json').write_text(json.dumps(dict(decoded_frames=count,expected_frames=len(images))),encoding='utf8')

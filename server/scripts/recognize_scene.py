"""Recognize the six-source manifest without using annotation boxes as input."""
import argparse
from collections import defaultdict, Counter
import hashlib
import html
import json
from pathlib import Path
import sys
import time

import cv2
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from strikezone.pose.detector import PoseDetector
from strikezone.pose.zone import analyze, overlap
from strikezone.pose.selector import BatterSelector, exclude_masked
from strikezone.plate.detector import locate, zone_candidate
from strikezone.plate.calibration import PlateCalibration


def read_image(path,gray=False):
    data=cv2.imdecode(np.fromfile(path,dtype=np.uint8),0 if gray else 1)
    if data is None:raise ValueError(f'Unreadable image: {path}')
    return data


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root',type=Path,required=True)
    parser.add_argument('--manifest',default='data/releases/testset-v003/manifest.json')
    parser.add_argument('--model',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--device',default='cpu')
    parser.add_argument('--imgsz',type=int,default=960)
    parser.add_argument('--overrides',type=Path)
    args=parser.parse_args()
    manifest_path=args.data_root/args.manifest
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    overrides=json.loads(args.overrides.read_text(encoding='utf-8')) if args.overrides else {}
    if not args.model.is_file():parser.error('Model must be a local file')
    detector=PoseDetector(args.model,args.device,args.imgsz)
    args.output.mkdir(parents=True,exist_ok=False)
    tracker=BatterSelector();previous_video=None
    calibration=PlateCalibration()
    applied=set()
    stats=defaultdict(Counter);records=[];gallery=[]
    for e in sorted(manifest['frames'],key=lambda e:(e['video_id'],e['frame_index'])):
        vid,idx=e['video_id'],e['frame_index'];key=f'{vid}:{idx}'
        if vid!=previous_video:tracker.reset();previous_video=vid
        image=read_image(args.data_root/e['image_path'])
        mask=read_image(args.data_root/e['ignore_mask_path'],True)
        h,w=image.shape[:2]
        if mask.shape!=(h,w) or [w,h]!=[e['image_width'],e['image_height']]:
            raise ValueError('Manifest/image/mask dimension mismatch')
        begin=time.perf_counter()
        # Masked synthetic/UI evidence is removed before inference and box validation.
        model_input=image.copy();model_input[mask>0]=0
        people=detector.predict(model_input)
        usable=exclude_masked(people,mask)
        correction=overrides.get(key,{})
        # Apply calibration events even when their frame is absent from this sparse manifest.
        pending=[]
        for event_key,event in overrides.items():
            event_video,event_frame=event_key.rsplit(':',1)
            if event_video==vid and int(event_frame)<=idx and event_key not in applied:
                pending.append((int(event_frame),event_key,event))
        for event_frame,event_key,event in sorted(pending):
            if 'front_edge_xy' in event or event.get('reset_plate',False):
                calibration.update(image,mask,vid,event_frame,event)
            applied.add(event_key)
        if correction.get('reset',False):tracker.reset()
        selection=tracker.select(usable,idx,w,h,correction.get('roi'))
        person=selection['candidate']
        roi=person['bbox_xyxy'] if person else [0,0,w,h]
        pose=analyze([person] if person else [],roi,w,h)
        pose['batter_id']=selection['batter_id']
        plate=calibration.update(image,mask,vid,idx,{})
        zone=zone_candidate(pose,plate,idx)
        elapsed=(time.perf_counter()-begin)*1000
        record=dict(schema_version='analysis-v1',video_id=vid,pitch_id=e['pitch_id'],
                    frame_index=idx,pts_ms=e.get('pts_ms'),time_source=e.get('time_source','unknown'),
                    coordinate_space='upright_unmirrored_pixels',image_width=w,image_height=h,
                    selection=selection,pose=pose,plate=plate,zone=zone,
                    rejected_masked_boxes=len(people)-len(usable),elapsed_ms=elapsed)
        # Annotations are used ONLY after selection, for draft-box comparison.
        reference=e['batter'].get('bbox_xyxy')
        iou=overlap(person['bbox_xyxy'],reference) if person and reference else None
        record['draft_comparison']=dict(batter_iou=iou,not_accuracy_benchmark=True)
        stats[vid]['frames']+=1
        stats[vid]['selected']+=person is not None
        stats[vid]['draft_iou_ge_0.5']+=iou is not None and iou>=0.5
        stats[vid]['pose_ok']+=pose['status']=='ok'
        stats[vid]['plate_candidate_frames']+=bool(plate['candidates'])
        stats[vid]['zone_ok']+=zone['status']=='ok'
        stats[vid][selection['reason'] or 'selection_ok']+=1
        records.append(record)
        view=image.copy();view[mask>0]=(view[mask>0]*0.3).astype(np.uint8)
        for c in selection['candidates']:
            x1,y1,x2,y2=map(int,c['bbox_xyxy'])
            cv2.rectangle(view,(x1,y1),(x2,y2),(150,150,150),1)
            cv2.putText(view,f"{c['score']:.2f}",(x1,y1),0,0.5,(0,200,255),1)
        if person:
            x1,y1,x2,y2=map(int,person['bbox_xyxy']);cv2.rectangle(view,(x1,y1),(x2,y2),(0,255,0),2)
            for point in pose['keypoints'].values():
                cv2.circle(view,tuple(map(round,point['xy'])),3,(0,255,255),-1)
        for c in plate['candidates']:
            cv2.polylines(view,[np.array(c['polygon_xy'],np.int32)],True,(0,165,255),2)
        if plate['front_edge_xy']:
            a,b=plate['front_edge_xy']
            cv2.line(view,tuple(map(round,a)),tuple(map(round,b)),(255,255,0),3)
        if zone['bbox_xyxy']:
            a,b,c,d=map(round,zone['bbox_xyxy']);cv2.rectangle(view,(a,b),(c,d),(255,255,0),2)
        cv2.putText(view,f"{vid[-4:]} f{idx} batter:{selection['reason'] or selection['source']}",
                    (10,22),0,0.5,(0,255,255),1)
        cv2.putText(view,f"plate:{plate['reason'] or plate['source']} ref:{plate.get('reference_frame_index')} | PREVIEW ONLY",(10,44),0,0.45,(0,255,255),1)
        name=f'{vid}-{idx}.jpg';cv2.imencode('.jpg',view)[1].tofile(str(args.output/name))
        gallery.append(f'<figure><img src="{name}"><figcaption>{html.escape(key)}<br>selection: {selection["reason"] or "ok"}; pose: {pose["reason"] or "ok"}; plate: {plate["reason"] or "ok"}</figcaption></figure>')
    (args.output/'results.jsonl').write_text(''.join(json.dumps(r,allow_nan=False)+'\n' for r in records),encoding='utf-8')
    report=dict(model_sha256=hashlib.sha256(args.model.read_bytes()).hexdigest(),
                manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                device=args.device,imgsz=args.imgsz,by_video=dict(stats),
                note='Sparse development frames, draft labels. No final ABS or real-time accuracy claim.')
    (args.output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    (args.output/'review.html').write_text('<meta charset="utf-8"><title>Issue 19 review</title><style>body{background:#18202a;color:white;font:16px sans-serif}main{display:grid;grid-template-columns:repeat(3,1fr)}figure{margin:10px}img{width:100%}</style><h1>Automatic recognition / draft review</h1><p>Green: selected batter. Orange: unconfirmed plate proposal. Cyan: manually confirmed 2D zone. Dark: ignored pixels.</p><main>'+''.join(gallery)+'</main>',encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()

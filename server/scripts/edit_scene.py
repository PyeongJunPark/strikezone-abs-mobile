"""Click a manual batter ROI and optional visible plate front edge on one frame."""
import argparse
import json
from pathlib import Path
import cv2
import numpy as np


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-root',type=Path,required=True)
    p.add_argument('--manifest',default='data/releases/testset-v003/manifest.json')
    p.add_argument('--frame',required=True,help='video_id:frame_index')
    p.add_argument('--output',type=Path,required=True,help='Correction JSON; other frames preserved')
    p.add_argument('--plate-only',action='store_true',help='Two clicks for plate edge; keep automatic batter selection')
    args=p.parse_args()
    manifest=json.loads((args.data_root/args.manifest).read_text(encoding='utf-8'))
    entry=next(e for e in manifest['frames'] if f"{e['video_id']}:{e['frame_index']}"==args.frame)
    image=cv2.imdecode(np.fromfile(args.data_root/entry['image_path'],np.uint8),1)
    mask=cv2.imdecode(np.fromfile(args.data_root/entry['ignore_mask_path'],np.uint8),0)
    if image is None or mask is None:raise ValueError('Missing image/mask')
    scale=min(1,1000/image.shape[1],700/image.shape[0])
    shown=image.copy();shown[mask>0]=(shown[mask>0]*0.3).astype(np.uint8)
    shown=cv2.resize(shown,None,fx=scale,fy=scale)
    sx=shown.shape[1]/image.shape[1];sy=shown.shape[0]/image.shape[0]
    points=[]
    def mouse(event,x,y,flags,param):
        if event==cv2.EVENT_LBUTTONDOWN and len(points)<(2 if args.plate_only else 4):points.append((x,y))
    title='Plate: 2 endpoints; S save; R redraw; D reset calibration; Esc cancel' if args.plate_only else 'Batter: 2 corners; Plate: 2 endpoints; S save; R redraw; D reset plate'
    cv2.namedWindow(title);cv2.setMouseCallback(title,mouse)
    try:
        while True:
            canvas=shown.copy()
            for pt in points:cv2.circle(canvas,pt,5,(0,255,255),-1)
            if len(points)>=2:
                if args.plate_only:cv2.line(canvas,points[0],points[1],(255,255,0),2)
                else:cv2.rectangle(canvas,points[0],points[1],(0,255,0),2)
            if len(points)==4:cv2.line(canvas,points[2],points[3],(255,255,0),2)
            cv2.imshow(title,canvas);key=cv2.waitKey(20)&255
            if key==27 or cv2.getWindowProperty(title,cv2.WND_PROP_AUTOSIZE)<0:return
            if key in (ord('r'),ord('R')):points=[]
            if key in (ord('d'),ord('D')):
                overrides=json.loads(args.output.read_text(encoding='utf-8')) if args.output.exists() else {}
                event=overrides.setdefault(args.frame,{})
                event.pop('front_edge_xy',None);event['reset_plate']=True
                args.output.parent.mkdir(parents=True,exist_ok=True)
                args.output.write_text(json.dumps(overrides,indent=2),encoding='utf-8')
                return
            if key not in (ord('s'),ord('S')) or len(points) not in (2,4):continue
            original=[[x/sx,y/sy] for x,y in points]
            if args.plate_only:
                import sys
                sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
                from strikezone.plate.detector import locate
                if locate(image,mask,None,original)['status']!='ok':
                    print('Invalid/masked edge; redraw with R',flush=True)
                    continue
                overrides=json.loads(args.output.read_text(encoding='utf-8')) if args.output.exists() else {}
                event=overrides.setdefault(args.frame,{})
                event['front_edge_xy']=original;event.pop('reset_plate',None)
                args.output.parent.mkdir(parents=True,exist_ok=True)
                args.output.write_text(json.dumps(overrides,indent=2),encoding='utf-8')
                return
            a,b=original[:2];roi=[min(a[0],b[0]),min(a[1],b[1]),max(a[0],b[0]),max(a[1],b[1])]
            if roi[2]-roi[0]<2 or roi[3]-roi[1]<2:continue
            overrides=json.loads(args.output.read_text(encoding='utf-8')) if args.output.exists() else {}
            overrides[args.frame]=dict(roi=roi,reset=True)
            if len(points)==4:overrides[args.frame]['front_edge_xy']=original[2:]
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(overrides,indent=2),encoding='utf-8')
            return
    finally:cv2.destroyAllWindows()


if __name__=='__main__':main()

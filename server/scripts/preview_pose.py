"""Offline Pose height preview. No plate geometry or strike/ball decision."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from strikezone.pose.zone import analyze, HeightLock, valid_box
from strikezone.pose.detector import PoseDetector


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--video', type=Path, required=True)
    p.add_argument('--model', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True, help='New output directory')
    p.add_argument('--video-id', required=True)
    p.add_argument('--pitch-id', default=None)
    p.add_argument('--roi', nargs=4, type=float, required=True, metavar=('X1','Y1','X2','Y2'))
    p.add_argument('--start', type=int, default=0)
    p.add_argument('--end', type=int, required=True, help='Inclusive original frame index')
    p.add_argument('--lock-frame', type=int)
    p.add_argument('--reset-frame', type=int, action='append', default=[])
    p.add_argument('--threshold', type=float, default=0.5)
    p.add_argument('--device', default='cpu')
    p.add_argument('--imgsz', type=int, default=640)
    args = p.parse_args()
    if args.start < 0 or args.end < args.start or not 0 <= args.threshold <= 1:
        p.error('Invalid frame range or threshold')
    events = args.reset_frame + ([args.lock_frame] if args.lock_frame is not None else [])
    if any(not args.start <= f <= args.end for f in events):
        p.error('Lock/reset frame must lie within the selected range')
    if not args.video.is_file() or not args.model.is_file():
        p.error('Local video and model files are required')
    import cv2
    cap = cv2.VideoCapture(str(args.video))
    if not cap.isOpened():
        raise RuntimeError('Cannot open input video')
    if args.end >= int(cap.get(cv2.CAP_PROP_FRAME_COUNT)):
        cap.release()
        p.error('End frame exceeds video length')
    detector = PoseDetector(args.model, args.device, args.imgsz)
    args.output.mkdir(parents=True, exist_ok=False)
    lock, counts, durations = HeightLock(), Counter(), []
    writer = None
    try:
        with (args.output/'frames.jsonl').open('w', encoding='utf-8') as stream:
            # Decode sequentially to preserve original frame indices.
            for index in range(args.end+1):
                ok, frame = cap.read()
                if not ok:
                    raise RuntimeError(f'Decode failed at frame {index}')
                if index < args.start:
                    continue
                h, w = frame.shape[:2]
                if not valid_box(args.roi, w, h):
                    raise ValueError('ROI outside decoded upright image')
                if writer is None:
                    # Fixed-rate visualization only. Never a measurement of capture time.
                    writer = cv2.VideoWriter(str(args.output/'preview.mp4'),
                                             cv2.VideoWriter_fourcc(*'mp4v'), 30, (w,h))
                    if not writer.isOpened():
                        raise RuntimeError('Video writer unavailable')
                begin = time.perf_counter()
                candidates = detector.predict(frame)
                pose = analyze(candidates, args.roi, w, h, args.threshold)
                durations.append((time.perf_counter()-begin)*1000)
                counts[pose['reason'] or 'ok'] += 1
                if index in args.reset_frame:
                    lock.reset()
                lock_event = None
                if index == args.lock_frame:
                    lock_event = 'locked' if lock.lock(pose,index,args.threshold) else 'rejected'
                fixed = lock.snapshot()
                record = dict(schema_version='analysis-v1', video_id=args.video_id,
                              pitch_id=args.pitch_id, frame_index=index, pts_ms=None,
                              time_source='unknown', image_width=w, image_height=h,
                              coordinate_space='upright_unmirrored_pixels', pose=pose,
                              pose_height_lock=fixed, lock_event=lock_event)
                stream.write(json.dumps(record, allow_nan=False)+'\n')
                x1,y1,x2,y2 = map(int,args.roi)
                cv2.rectangle(frame,(x1,y1),(x2,y2),(120,120,120),1)
                if pose['bbox_xyxy']:
                    a,b,c,d=map(int,pose['bbox_xyxy'])
                    cv2.rectangle(frame,(a,b),(c,d),(255,180,0),2)
                for joint in pose['keypoints'].values():
                    color=(0,255,0) if joint['confidence']>=args.threshold else (0,0,255)
                    cv2.circle(frame,tuple(map(int,joint['xy'])),4,color,-1)
                height = fixed or (pose if pose['status']=='ok' else None)
                if height:
                    for name in ('top_y','bottom_y'):
                        y=round(height[name]); cv2.line(frame,(x1,y),(x2,y),(0,255,255),2)
                text=f"frame {index} | {pose['reason'] or 'ok'} | {'LOCKED' if fixed else 'LIVE'}"
                cv2.putText(frame,text,(12,25),cv2.FONT_HERSHEY_SIMPLEX,0.55,(0,255,255),2)
                cv2.putText(frame,'HEIGHT PREVIEW ONLY - ROI IS NOT PLATE WIDTH',(12,50),
                            cv2.FONT_HERSHEY_SIMPLEX,0.45,(0,255,255),1)
                writer.write(frame)
                if index==args.start or index==args.lock_frame:
                    cv2.imwrite(str(args.output/f'frame-{index}.jpg'),frame)
    finally:
        cap.release()
        if writer is not None:
            writer.release()
    report=dict(video_sha256=hashlib.sha256(args.video.read_bytes()).hexdigest(),
                model_sha256=hashlib.sha256(args.model.read_bytes()).hexdigest(),
                config={k:str(v) if isinstance(v,Path) else v for k,v in vars(args).items()},
                statuses=dict(counts), frames=len(durations), first_frame_ms=durations[0],
                mean_after_first_ms=sum(durations[1:])/len(durations[1:]) if len(durations)>1 else None,
                note='Offline inference only; no accuracy or real-time claim. Output video is fixed 30fps.')
    (args.output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()

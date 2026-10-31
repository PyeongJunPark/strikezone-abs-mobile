"""Portable offline manual-start ball tracker. Coordinates are source pixels."""
import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from strikezone.ball.manual_pitch import track_manual_pitch
from strikezone.ball.learned_trajectory import estimate_position


def validate_config(config, width, height):
    trigger = config['trigger_frame']
    if isinstance(trigger, bool) or not isinstance(trigger, int) or trigger < 0:
        raise ValueError('trigger_frame must be a nonnegative integer')
    for name in ('pitcher_box', 'plate_region', 'crop'):
        box = config.get(name, [0, 0, width, height])
        if len(box) != 4 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in box):
            raise ValueError(f'Invalid {name}')
        l, t, r, b = box
        if not (0 <= l < r <= width and 0 <= t < b <= height):
            raise ValueError(f'{name} must fit the source image')
        if name == 'crop' and any(int(v) != v for v in box):
            raise ValueError('crop coordinates must be integers')
    for name in ('pitcher_box', 'plate_region'):
        if name not in config:
            raise ValueError(f'Missing {name}')


def restore_candidate(box, confidence, crop):
    l, t, r, b = map(float, box)
    l += crop[0]
    r += crop[0]
    t += crop[1]
    b += crop[1]
    return dict(center_xy=[(l+r)/2, (t+b)/2], bbox_xyxy=[l,t,r,b], confidence=float(confidence))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('video', 'weights', 'config', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--device', default='cpu')
    args = parser.parse_args()
    if not args.video.is_file() or not args.weights.is_file():
        parser.error('video and weights must be existing local files')
    config = json.loads(args.config.read_text(encoding='utf-8'))
    import cv2
    import numpy as np
    from ultralytics import YOLO
    cap = cv2.VideoCapture(str(args.video))
    try:
        width, height = (int(cap.get(p)) for p in (cv2.CAP_PROP_FRAME_WIDTH, cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        if not cap.isOpened() or not math.isfinite(fps) or fps <= 0:
            raise ValueError('Unreadable video or invalid FPS')
        validate_config(config, width, height)
        crop = list(map(int, config.get('crop', [0,0,width,height])))
        model = YOLO(str(args.weights))
        ball_class = config.get('ball_class', 2)
        if ball_class not in model.names:
            raise ValueError('ball_class is absent from model.names')
        args.output.mkdir(parents=True, exist_ok=False)
        start = config['trigger_frame']
        stop = start + round(4 * fps)
        rows, previous = [], None
        with (args.output / 'detections.jsonl').open('w', encoding='utf-8') as stream:
            for index in range(stop):
                ok, frame = cap.read()
                if not ok:
                    break
                if index < start:
                    continue
                l,t,r,b = crop
                prediction = model.predict(frame[t:b,l:r], imgsz=1280, conf=.08,
                                           classes=[ball_class], device=args.device, verbose=False)[0]
                candidates = [restore_candidate(box, confidence, crop)
                              for box, confidence in zip(prediction.boxes.xyxy.cpu().tolist(), prediction.boxes.conf.cpu().tolist())
                              if max(box[2]-box[0], box[3]-box[1]) <= 100]
                row = dict(frame_index=index, timestamp_ms=index/fps*1000,
                           source_frame_repeated=previous is not None and bool(np.array_equal(previous, frame)),
                           candidates=candidates)
                previous = frame
                rows.append(row)
                stream.write(json.dumps(row) + '\n')
        if not rows:
            raise ValueError('No frames at or after trigger_frame')
        result = track_manual_pitch(rows, start, config['pitcher_box'], config['plate_region'],
                                    fps=fps, width=width, defer_endpoint=True)
        track = result['track']
        positions = [estimate_position(track, f) for f in range(track[0]['frame_index'], min(rows[-1]['frame_index'], track[-1]['frame_index']+3)+1)] if track else []
        result.update(schema='offline-ball-track-v1', offline=True, validated_judgment=False,
                      positions=positions, config=config, width=width, height=height, fps=fps,
                      video_name=args.video.name, weights_name=args.weights.name,
                      ball_class_name=model.names[ball_class], processed_frames=len(rows),
                      time_basis='nominal_video_fps_not_capture_speed')
        (args.output/'track.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(dict(status=result['status'], observed_points=len(track), processed_frames=len(rows))))
    finally:
        cap.release()


if __name__ == '__main__':
    main()

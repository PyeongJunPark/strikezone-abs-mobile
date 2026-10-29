"""Prepare a self-contained fixed-zone review page from cleaned analysis frames."""
import argparse
import base64
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'server/src'))
from strikezone.pose.detector import PoseDetector
from strikezone.pose.reference import exclude_masked_joints, rank_references
from strikezone.pose.zone import analyze, valid_box
from strikezone.pose.pitch_start import PitchStartDetector, auto_reference


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--video-id', required=True)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--roi', nargs=4, type=float, required=True)
    parser.add_argument('--zone-x', nargs=2, type=float, required=True)
    parser.add_argument('--release-frame', type=int,
                        help='Manually reviewed boundary, not an automatic release detection')
    parser.add_argument('--pitcher-roi', nargs=4, type=float,
                        help='Pitcher-only region for automatic motion onset; omit for manual mode')
    parser.add_argument('--threshold', type=float, default=0.5)
    parser.add_argument('--device', default='cpu')
    parser.add_argument('--imgsz', type=int, default=640)
    parser.add_argument('--output', type=Path, required=True, help='New output directory')
    args = parser.parse_args()
    if not 0 <= args.threshold <= 1 or args.imgsz <= 0:
        parser.error('Invalid model settings')
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    if manifest.get('default_analysis_input') != 'cursor_cleaned_png':
        parser.error('A cleaned-image manifest is required; raw fallback is disabled')
    entries = sorted([e for e in manifest['frames'] if e['video_id'] == args.video_id],
                     key=lambda e: e['frame_index'])
    if not entries or len({e['frame_index'] for e in entries}) != len(entries):
        parser.error('Empty selection or duplicate frame index')
    if any(type(e['frame_index']) is not int or e['frame_index'] < 0 for e in entries):
        parser.error('Source frame indices must be nonnegative integers')
    if args.release_frame is None and args.pitcher_roi is None:
        parser.error('Specify --pitcher-roi for automatic mode or --release-frame for manual mode')
    if args.release_frame is not None and not entries[0]['frame_index'] < args.release_frame <= entries[-1]['frame_index']:
        parser.error('Release boundary must lie inside the selected sequence')
    hashes = {e['path']: e['sha256'] for e in manifest['files']}
    for entry in entries:
        for key in ('image_path', 'ignore_mask_path'):
            path = ROOT / entry[key]
            if entry[key] not in hashes or sha(path) != hashes[entry[key]]:
                parser.error(f'Missing or changed analysis input: {path}')
    if not args.model.is_file():
        parser.error('A local Pose model is required')
    args.output.mkdir(parents=True, exist_ok=False)
    import cv2
    import numpy as np
    detector = PoseDetector(args.model, args.device, args.imgsz)
    start_detector = PitchStartDetector(args.pitcher_roi,args.roi) if args.pitcher_roi else None
    frames = []
    previous_hash = None
    for entry in entries:
        image = cv2.imdecode(np.frombuffer((ROOT/entry['image_path']).read_bytes(), np.uint8), cv2.IMREAD_COLOR)
        mask = cv2.imdecode(np.frombuffer((ROOT/entry['ignore_mask_path']).read_bytes(), np.uint8), cv2.IMREAD_GRAYSCALE)
        if image is None or mask is None or mask.shape != image.shape[:2]:
            raise ValueError('Invalid image or mask dimensions')
        h, w = image.shape[:2]
        if not valid_box(args.roi, w, h) or not (0 <= args.zone_x[0] < args.zone_x[1] <= w):
            raise ValueError('Invalid ROI or manual horizontal range')
        if args.pitcher_roi and not valid_box(args.pitcher_roi,w,h):
            raise ValueError('Invalid pitcher ROI')
        onset = start_detector.update(image,mask,entry['frame_index']) if start_detector else None
        inference = image.copy()
        inference[mask != 0] = 0
        candidates = exclude_masked_joints(detector.predict(inference), mask)
        pose = analyze(candidates, args.roi, w, h, args.threshold)
        image_hash = hashlib.sha256(image.tobytes()).hexdigest()
        # JPEG is for display only; inference uses the verified lossless PNG above.
        ok, jpg = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ok:
            raise RuntimeError('Preview encode failed')
        frames.append(dict(frame_index=entry['frame_index'], image_width=w, image_height=h,
                           pts_ms=entry.get('pts_ms'), time_source=entry.get('time_source', 'unknown'),
                           pose=pose, pitch_start=onset, image_path=entry['image_path'], ignore_mask_path=entry['ignore_mask_path'],
                           image_sha256=hashes[entry['image_path']],
                           duplicate_of_previous=image_hash == previous_hash,
                           preview='data:image/jpeg;base64,' + base64.b64encode(jpg).decode('ascii')))
        previous_hash = image_hash
    automatic = auto_reference(frames,start_detector.event) if start_detector else None
    boundary = automatic['event']['onset_frame_index'] if automatic and automatic['event'] else args.release_frame
    config = dict(roi=args.roi, zone_x=args.zone_x, release_frame=boundary, pitcher_roi=args.pitcher_roi,
                  threshold=args.threshold, device=args.device, imgsz=args.imgsz,
                  release_source='pitcher_motion_candidate' if args.pitcher_roi else 'manual_visual_boundary', mask_policy='blackout_and_reject_joint_neighborhood',
                  formula='pose-midpoint-v1', model_path=str(args.model))
    data = dict(video_id=args.video_id, frames=frames, config=config, automatic=automatic,
                input_manifest_sha256=sha(args.manifest), model_sha256=sha(args.model))
    source = ROOT/'server/ui'
    page = (source/'fixed-zone.html').read_text(encoding='utf-8')
    page = page.replace('/*__STATE__*/', (source/'fixed-zone.js').read_text(encoding='utf-8'))
    page = page.replace('/*__DATA__*/', json.dumps(data, allow_nan=False).replace('<', '\\u003c'))
    (args.output/'review.html').write_text(page, encoding='utf-8')
    report = dict(video_id=args.video_id, input_manifest=str(args.manifest),
                  input_manifest_sha256=data['input_manifest_sha256'], model_sha256=data['model_sha256'],
                  config=config, frame_count=len(frames),
                  statuses=dict(Counter(f['pose']['reason'] or 'ok' for f in frames)),
                  candidates=rank_references(frames,boundary) if boundary is not None else [], automatic=automatic,
                  sparse=any(b['frame_index'] != a['frame_index']+1 for a,b in zip(frames,frames[1:])),
                  note='Motion onset is an unvalidated candidate, not ball release. Manual pitcher ROI and zone width; single-pitch run; background-change guard is heuristic.')
    (args.output/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    with (args.output/'frames.jsonl').open('w',encoding='utf-8') as stream:
        for f in frames:
            stream.write(json.dumps({k:v for k,v in f.items() if k != 'preview'}, allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k != 'candidates'}, indent=2))


if __name__ == '__main__':
    main()

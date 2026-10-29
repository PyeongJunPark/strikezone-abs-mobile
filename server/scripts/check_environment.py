"""Check video decoding, model inference and CPU/CUDA forward/backward execution."""
import argparse
import hashlib
import importlib.metadata
import json
import platform
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def resolve(value):
    path = Path(value).expanduser()
    return path if path.is_absolute() else ROOT / path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8-sig'))
    video, model = resolve(config['video']), resolve(config['model'])
    for path in (video, model):
        if not path.is_file():
            raise FileNotFoundError(f'Missing local input: {path}')
    frames, size = int(config.get('frames', 3)), int(config.get('imgsz', 640))
    if frames < 1 or size < 32:
        raise ValueError('frames must be positive and imgsz must be >= 32')
    output = resolve(config.get('output', 'outputs/environment-check.json'))
    if output.resolve() in (video.resolve(), model.resolve(), args.config.resolve()):
        raise ValueError('Output must not overwrite an input')
    import cv2
    import torch
    from ultralytics import YOLO

    device = str(config.get('device', 'cpu'))
    if device != 'cpu' and not torch.cuda.is_available():
        raise RuntimeError('CUDA unavailable; install CUDA wheels or select cpu')
    tensor_device = 'cpu' if device == 'cpu' else (f'cuda:{device}' if device.isdigit() else device)
    layer = torch.nn.Conv2d(3, 8, 3).to(tensor_device)
    layer(torch.randn(1, 3, 32, 32, device=tensor_device)).square().mean().backward()
    if device != 'cpu':
        torch.cuda.synchronize()
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f'Cannot open video: {video}')
    report = {
        'python': platform.python_version(), 'platform': platform.platform(),
        'packages': {name: importlib.metadata.version(name) for name in
                     ('torch', 'torchvision', 'ultralytics', 'opencv-python', 'numpy')},
        'cuda_available': torch.cuda.is_available(), 'torch_cuda': torch.version.cuda,
        'gpu': torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        'device': device, 'forward_backward': 'passed',
        'video_name': video.name, 'model_name': model.name,
        'model_sha256': hashlib.sha256(model.read_bytes()).hexdigest(),
        'file_fps': cap.get(cv2.CAP_PROP_FPS),
        'video_frames': int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
        'resolution': [int(cap.get(3)), int(cap.get(4))],
        'results': [], 'note': 'Environment smoke check, not accuracy or real-time validation',
    }
    try:
        detector = YOLO(str(model))
        for index in range(frames):
            ok, frame = cap.read()
            if not ok:
                break
            start = time.perf_counter()
            result = detector.predict(frame, device=device, imgsz=size, verbose=False, save=False)[0]
            if device != 'cpu':
                torch.cuda.synchronize()
            report['results'].append({'frame': index,
                'elapsed_ms': round((time.perf_counter() - start) * 1000, 2),
                'detections': len(result.boxes) if result.boxes is not None else 0,
                'keypoint_shape': list(result.keypoints.shape) if result.keypoints is not None else None})
    finally:
        cap.release()
    if not report['results']:
        raise RuntimeError('No decodable frames')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

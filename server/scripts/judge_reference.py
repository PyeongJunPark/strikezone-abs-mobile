"""Run the offline reference policy on previously detected observations."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from strikezone.judgment.receiver_reference import prioritized_reference_call


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error('Input observations must not be overwritten')
    data = json.loads(args.input.read_text(encoding='utf-8-sig'))
    result = prioritized_reference_call(
        data['track'], data['zone'], fps=data.get('fps', 30),
        receiver=data.get('receiver'), detections=data.get('detections'),
        end_frame=data.get('end_frame'), size_rows=data.get('size_rows'),
        image_size=data.get('image_size'),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    print(f"{result['preview']}: {result['reason']}")


if __name__ == '__main__':
    main()

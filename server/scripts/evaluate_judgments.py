"""Compare pipeline ball/strike calls with human labels and write a report."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from strikezone.judgment.evaluation import evaluate, load_labels, load_predictions, markdown, read_jsonl


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--labels', type=Path, required=True, help='정답 라벨 JSONL')
    parser.add_argument('--predictions', type=Path, required=True,
                        help='판정 결과 JSONL (preview 또는 result_json 경로)')
    parser.add_argument('--output', type=Path, help='report.json·report.md를 저장할 폴더')
    args = parser.parse_args()
    try:
        labels = load_labels(read_jsonl(args.labels))
        predictions = load_predictions(read_jsonl(args.predictions), base=args.predictions.parent)
    except (OSError, ValueError) as exc:
        parser.exit(2, f'오류: {exc}\n')
    report = evaluate(labels, predictions)
    text = markdown(report)
    if args.output:
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
        (args.output / 'report.md').write_text(text, encoding='utf8')
    sys.stdout.reconfigure(encoding='utf-8')
    print(text)


if __name__ == '__main__':
    main()

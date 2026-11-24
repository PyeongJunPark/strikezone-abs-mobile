"""Ball/strike accuracy against human labels (proposal target: >=80% on >=100 pitches).

Labels (one JSON object per line):
  {"pitch_id": "...", "truth": "STRIKE" | "BALL" | "SWING" | "UNKNOWN", ...}
SWING pitches are outside the judgment scope (only taken pitches are called)
and UNKNOWN means the labelers could not agree or could not see the ball.
Both are reported but excluded from accuracy.

Predictions (one JSON object per line):
  {"pitch_id": "...", "preview": "STRIKE_ESTIMATE" | "BALL_ESTIMATE" | "UNJUDGEABLE", ...}
or {"pitch_id": "...", "result_json": "path/to/result.json"} written by the pipeline.
"""
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

TRUTHS = ('STRIKE', 'BALL', 'SWING', 'UNKNOWN')
CALLS = {'STRIKE_ESTIMATE': 'STRIKE', 'BALL_ESTIMATE': 'BALL', 'UNJUDGEABLE': 'UNJUDGEABLE',
         'STRIKE': 'STRIKE', 'BALL': 'BALL'}
TARGET_ACCURACY = .80
TARGET_PITCHES = 100


def read_jsonl(path):
    rows = []
    for number, line in enumerate(Path(path).read_text(encoding='utf8').splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f'{path}:{number}: JSON 형식 오류 ({exc.msg})') from None
    return rows


def load_labels(rows):
    labels = {}
    for row in rows:
        pitch, truth = row.get('pitch_id'), str(row.get('truth', '')).upper()
        if not pitch:
            raise ValueError('pitch_id가 없는 라벨이 있습니다.')
        if truth not in TRUTHS:
            raise ValueError(f'{pitch}: truth는 {"/".join(TRUTHS)} 중 하나여야 합니다.')
        if pitch in labels:
            raise ValueError(f'{pitch}: 라벨이 중복되었습니다.')
        labels[pitch] = dict(row, truth=truth)
    return labels


def load_predictions(rows, base=None):
    predictions = {}
    for row in rows:
        pitch = row.get('pitch_id')
        if not pitch:
            raise ValueError('pitch_id가 없는 예측이 있습니다.')
        if pitch in predictions:
            raise ValueError(f'{pitch}: 예측이 중복되었습니다.')
        record = dict(row)
        if 'result_json' in row:
            path = Path(row['result_json'])
            if base is not None and not path.is_absolute():
                path = Path(base) / path
            result = json.loads(path.read_text(encoding='utf8'))
            for key in ('preview', 'reason', 'decision_source', 'confidence', 'boundary_hit', 'edge_margin_px'):
                record.setdefault(key, result.get(key))
        call = CALLS.get(str(record.get('preview', '')).upper())
        if call is None:
            raise ValueError(f'{pitch}: 알 수 없는 판정 값 {record.get("preview")!r}')
        predictions[pitch] = dict(record, call=call)
    return predictions


def wilson_interval(successes, total, z=1.96):
    """95% Wilson score interval; small samples are the norm here."""
    if total == 0:
        return None
    p = successes / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return [max(0.0, centre - half), min(1.0, centre + half)]


def _rate(correct, total):
    return dict(correct=correct, total=total, accuracy=correct / total if total else None,
                ci95=wilson_interval(correct, total))


def evaluate(labels, predictions):
    truth_counts = Counter(label['truth'] for label in labels.values())
    eligible = [p for p, label in labels.items() if label['truth'] in ('STRIKE', 'BALL')]
    missing = sorted(p for p in eligible if p not in predictions)
    unlabeled = sorted(p for p in predictions if p not in labels)
    confusion = {t: Counter() for t in ('STRIKE', 'BALL')}
    groups = defaultdict(lambda: [0, 0])
    errors = []
    unjudged = []
    judged = correct_judged = 0
    for pitch in eligible:
        truth = labels[pitch]['truth']
        prediction = predictions.get(pitch)
        call = prediction['call'] if prediction else 'MISSING'
        confusion[truth][call] += 1
        if call == 'UNJUDGEABLE':
            unjudged.append(dict(pitch_id=pitch, truth=truth, reason=prediction.get('reason')))
        if call in ('STRIKE', 'BALL'):
            judged += 1
            hit = call == truth
            correct_judged += hit
            for key in ('decision_source', 'confidence', 'boundary_hit'):
                bucket = groups[(key, str(prediction.get(key)))]
                bucket[0] += hit
                bucket[1] += 1
            if not hit:
                errors.append(dict(pitch_id=pitch, truth=truth, call=call,
                                   reason=prediction.get('reason'),
                                   decision_source=prediction.get('decision_source'),
                                   boundary_hit=prediction.get('boundary_hit'),
                                   edge_margin_px=prediction.get('edge_margin_px'),
                                   note=labels[pitch].get('note')))
    strict = _rate(correct_judged, len(eligible))
    by_group = defaultdict(dict)
    for (key, value), (hit, total) in sorted(groups.items()):
        by_group[key][value] = _rate(hit, total)
    strike_total = sum(confusion['STRIKE'].values())
    ball_total = sum(confusion['BALL'].values())
    report = dict(
        labeled=len(labels), truth_counts=dict(truth_counts), eligible=len(eligible),
        excluded=dict(swing=truth_counts.get('SWING', 0), unknown=truth_counts.get('UNKNOWN', 0)),
        judged=judged, coverage=judged / len(eligible) if eligible else None,
        accuracy_strict=strict, accuracy_judged=_rate(correct_judged, judged),
        strike_recall=_rate(confusion['STRIKE']['STRIKE'], strike_total),
        ball_recall=_rate(confusion['BALL']['BALL'], ball_total),
        confusion={t: dict(c) for t, c in confusion.items()},
        by_group=dict(by_group), errors=errors, unjudged=unjudged, missing_predictions=missing,
        predictions_without_label=unlabeled,
        target=dict(accuracy=TARGET_ACCURACY, pitches=TARGET_PITCHES,
                    enough_pitches=len(eligible) >= TARGET_PITCHES,
                    met=bool(eligible) and len(eligible) >= TARGET_PITCHES
                        and strict['accuracy'] >= TARGET_ACCURACY))
    return report


def _pct(rate):
    if rate['accuracy'] is None:
        return '-'
    low, high = rate['ci95']
    return f"{rate['accuracy']*100:.1f}% ({rate['correct']}/{rate['total']}, 95% CI {low*100:.1f}~{high*100:.1f}%)"


def markdown(report):
    target = report['target']
    status = '달성' if target['met'] else ('미달' if target['enough_pitches'] else f"표본 부족({report['eligible']}/{target['pitches']}구)")
    lines = ['# 볼·스트라이크 판정 정확도', '',
             f"- 라벨 {report['labeled']}구 중 평가 대상 {report['eligible']}구 (스윙 {report['excluded']['swing']}, 판단 불가 라벨 {report['excluded']['unknown']} 제외)",
             f"- **엄격 정확도 (판정 불가·누락도 오답 처리): {_pct(report['accuracy_strict'])}**",
             f"- 판정한 투구만의 정확도: {_pct(report['accuracy_judged'])}",
             f"- 판정률(coverage): {report['coverage']*100:.1f}%" if report['coverage'] is not None else '- 판정률: -',
             f"- 스트라이크 재현율: {_pct(report['strike_recall'])}",
             f"- 볼 재현율: {_pct(report['ball_recall'])}",
             f"- 목표(엄격 정확도 {target['accuracy']*100:.0f}% 이상, {target['pitches']}구 이상): **{status}**", '',
             '## 혼동 행렬 (행: 정답, 열: 판정)', '',
             '| 정답 \\ 판정 | STRIKE | BALL | UNJUDGEABLE | MISSING |', '|---|---:|---:|---:|---:|']
    for truth in ('STRIKE', 'BALL'):
        row = report['confusion'][truth]
        lines.append(f"| {truth} | " + ' | '.join(str(row.get(c, 0)) for c in ('STRIKE', 'BALL', 'UNJUDGEABLE', 'MISSING')) + ' |')
    for key, title in (('decision_source', '판정 근거별'), ('confidence', '신뢰도별'), ('boundary_hit', '경계 근처 여부별')):
        if report['by_group'].get(key):
            lines += ['', f'## {title} 정확도 (판정한 투구)', '']
            lines += [f"- {value}: {_pct(rate)}" for value, rate in report['by_group'][key].items()]
    if report['errors']:
        lines += ['', '## 오답 목록', '', '| pitch_id | 정답 | 판정 | 판정 근거 | 경계 | 메모 |', '|---|---|---|---|---|---|']
        lines += [f"| {e['pitch_id']} | {e['truth']} | {e['call']} | {e['decision_source'] or '-'} | {e['boundary_hit']} | {e['note'] or ''} |" for e in report['errors']]
    if report['unjudged']:
        lines += ['', f"판정 불가 {len(report['unjudged'])}구: " + ', '.join(f"{u['pitch_id']}({u['reason']})" for u in report['unjudged'])]
    if report['missing_predictions']:
        lines += ['', f"예측 없음 {len(report['missing_predictions'])}구: " + ', '.join(report['missing_predictions'])]
    if report['predictions_without_label']:
        lines += ['', f"라벨 없는 예측 {len(report['predictions_without_label'])}구(무시): " + ', '.join(report['predictions_without_label'])]
    return '\n'.join(lines) + '\n'

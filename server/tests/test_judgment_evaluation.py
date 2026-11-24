import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from strikezone.judgment.evaluation import evaluate, load_labels, load_predictions, markdown, wilson_interval

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'evaluate_judgments.py'


def labels(*rows):return load_labels([dict(pitch_id=p, truth=t) for p, t in rows])
def preds(*rows):return load_predictions([dict(pitch_id=p, preview=c, decision_source='observed_arrival', confidence='low', boundary_hit=False) for p, c in rows])


class EvaluationTests(unittest.TestCase):
    def test_strict_accuracy_counts_unjudgeable_and_missing_as_wrong(self):
        r = evaluate(labels(('a', 'STRIKE'), ('b', 'BALL'), ('c', 'BALL'), ('d', 'STRIKE')),
                     preds(('a', 'STRIKE_ESTIMATE'), ('b', 'STRIKE_ESTIMATE'), ('c', 'UNJUDGEABLE')))
        self.assertEqual(r['accuracy_strict']['correct'], 1)
        self.assertEqual(r['accuracy_strict']['total'], 4)
        self.assertEqual(r['accuracy_judged']['total'], 2)
        self.assertEqual(r['coverage'], .5)
        self.assertEqual(r['missing_predictions'], ['d'])
        self.assertEqual(r['confusion']['BALL'], {'STRIKE': 1, 'UNJUDGEABLE': 1})
        self.assertEqual([e['pitch_id'] for e in r['errors']], ['b'])
        self.assertEqual([u['pitch_id'] for u in r['unjudged']], ['c'])

    def test_swing_and_unknown_are_excluded(self):
        r = evaluate(labels(('a', 'STRIKE'), ('b', 'SWING'), ('c', 'unknown')),
                     preds(('a', 'STRIKE_ESTIMATE'), ('b', 'BALL_ESTIMATE'), ('x', 'BALL_ESTIMATE')))
        self.assertEqual(r['eligible'], 1)
        self.assertEqual(r['accuracy_strict']['accuracy'], 1.0)
        self.assertEqual(r['excluded'], dict(swing=1, unknown=1))
        self.assertEqual(r['predictions_without_label'], ['x'])

    def test_target_requires_100_pitches_and_80_percent(self):
        rows = [(f'p{i}', 'STRIKE' if i % 2 else 'BALL') for i in range(100)]
        calls = [(p, ('STRIKE_ESTIMATE' if t == 'STRIKE' else 'BALL_ESTIMATE') if i < 80 else 'UNJUDGEABLE') for i, (p, t) in enumerate(rows)]
        self.assertTrue(evaluate(labels(*rows), preds(*calls))['target']['met'])
        calls[0] = (calls[0][0], 'UNJUDGEABLE')
        self.assertFalse(evaluate(labels(*rows), preds(*calls))['target']['met'])
        small = evaluate(labels(*rows[:10]), preds(*calls[1:10]))
        self.assertFalse(small['target']['enough_pitches'])
        self.assertIn('표본 부족', markdown(small))

    def test_wilson_interval(self):
        low, high = wilson_interval(80, 100)
        self.assertAlmostEqual(low, .711, places=2);self.assertAlmostEqual(high, .867, places=2)
        self.assertIsNone(wilson_interval(0, 0))

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):load_labels([dict(pitch_id='a', truth='MAYBE')])
        with self.assertRaises(ValueError):load_labels([dict(pitch_id='a', truth='BALL'), dict(pitch_id='a', truth='BALL')])
        with self.assertRaises(ValueError):load_predictions([dict(pitch_id='a', preview='FOUL')])

    def test_cli_reads_result_json_and_writes_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / 'run1').mkdir()
            (tmp / 'run1' / 'result.json').write_text(json.dumps(dict(preview='BALL_ESTIMATE', reason='x', decision_source='observed_arrival', confidence='low', boundary_hit=True)), encoding='utf8')
            (tmp / 'labels.jsonl').write_text('# 주석\n{"pitch_id":"p1","truth":"BALL"}\n{"pitch_id":"p2","truth":"STRIKE"}\n', encoding='utf8')
            (tmp / 'preds.jsonl').write_text('{"pitch_id":"p1","result_json":"run1/result.json"}\n{"pitch_id":"p2","preview":"BALL_ESTIMATE"}\n', encoding='utf8')
            out = subprocess.run([sys.executable, str(SCRIPT), '--labels', str(tmp / 'labels.jsonl'), '--predictions', str(tmp / 'preds.jsonl'), '--output', str(tmp / 'report')],
                                 capture_output=True, text=True, encoding='utf8')
            self.assertEqual(out.returncode, 0, out.stderr)
            report = json.loads((tmp / 'report' / 'report.json').read_text(encoding='utf8'))
            self.assertEqual(report['accuracy_strict']['correct'], 1)
            self.assertEqual(report['by_group']['boundary_hit']['True']['correct'], 1)
            self.assertIn('혼동 행렬', (tmp / 'report' / 'report.md').read_text(encoding='utf8'))


if __name__ == '__main__':
    unittest.main()

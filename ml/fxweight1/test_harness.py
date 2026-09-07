"""MT5を起動せず、実測の取り違えと円建て判定の境界を検証する。"""
import ast
import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import adjudicate
import attribution
import measure
from generate_proposals import ROOT, generate, parameters


class HarnessTests(unittest.TestCase):
    def test_proposals_and_inherited_guards(self):
        rows, duplicates = generate()
        self.assertEqual((len(rows), duplicates), (45, 0))
        self.assertEqual([sum(r['family'] == f for r in rows) for f in 'ABCDEF'],
                         [4, 15, 6, 8, 8, 4])
        self.assertTrue(all(v > 0 for r in rows for v in parameters(r['parameter_json']).values()))
        old = ast.parse((ROOT.parent / 'fxmult1' / 'measure.py').read_text(encoding='utf-8'))
        new = ast.parse((ROOT / 'measure.py').read_text(encoding='utf-8'))
        book = next(n.value for n in old.body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == 'BOOK' for t in n.targets))
        self.assertEqual(measure.BASE, ast.literal_eval(book))
        for name in ('ea_sha', 'kill'):
            self.assertEqual(ast.dump(next(n for n in old.body if isinstance(n, ast.FunctionDef) and n.name == name)),
                             ast.dump(next(n for n in new.body if isinstance(n, ast.FunctionDef) and n.name == name)))
        old_run = next(n for n in old.body if isinstance(n, ast.FunctionDef) and n.name == 'run')
        new_run = next(n for n in new.body if isinstance(n, ast.FunctionDef) and n.name == 'run')
        self.assertEqual(ast.dump(old_run.body[0]), ast.dump(new_run.body[1]))

    def test_curve_and_attribution_edges(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'deals.csv'
            for profits in ([-10, -20, 50, -5], [50, -10, -20, 5], [0, 0], [10, 20]):
                with path.open('w', encoding='utf-8', newline='') as fh:
                    w = csv.writer(fh, lineterminator='\n')
                    w.writerow(['time', 'magic', 'profit'])
                    for p in profits:
                        w.writerow([100, 20261001, p])
                net, dd, span, rows = adjudicate.curve(path)
                self.assertEqual(net, sum(profits))
                stats = attribution.segment(rows)
                self.assertAlmostEqual(sum(v[0] for v in stats.values()), -dd)

    def test_budget_and_ties(self):
        by = {(pid, 'IS'): dict(proposal_id=pid, monthly_pct=mo, dd_yen=dd)
              for pid, mo, dd in [('W001', 1, 100000), ('W002', 2, 100001),
                                  ('W003', 1, 50000), ('W004', 3, 125000)]}
        self.assertEqual([(rank, r['proposal_id']) for rank, r in adjudicate.rankings(by, 'IS', 20)],
                         [(1, 'W001'), (1, 'W003')])
        self.assertEqual(adjudicate.rankings(by, 'IS', 25)[0][1]['proposal_id'], 'W004')

    def test_resume_and_metadata(self):
        props, _ = generate()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            deal = root / 'deal.csv'
            deal.write_text('time,magic,profit\n100,20261001,-10\n200,20261001,20\n', encoding='utf-8')
            out = root / 'results.csv'
            with patch.object(measure, 'OUT', out):
                measure.append_result(dict(props[0], window='IS', status='OK', deals=str(deal)))
                measure.append_result(dict(props[0], window='OOS', status='FAILED'))
                self.assertEqual(measure.load_done(props), {('W001', 'IS')})
                by = adjudicate.collect(out, props)
                self.assertEqual(by['W001', 'IS']['net'], 10)
                self.assertEqual(by['W001', 'IS']['gain_pp'], 0)
                self.assertNotIn(('W001', 'OOS'), by)
                self.assertNotIn(b'\r', out.read_bytes())
                changed = [dict(props[0])]
                p = parameters(changed[0]['parameter_json'])
                p['GlobalLotMult'] = 2
                changed[0]['parameter_json'] = json.dumps(p)
                with self.assertRaises(ValueError):
                    measure.load_done(changed)
                deal.unlink()
                self.assertEqual(measure.load_done(props), set())


if __name__ == '__main__':
    unittest.main()

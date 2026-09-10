"""初回到達、期間打切り、連続性と高速版の同値性を独立な逐次計算で確認する。"""
import math
import unittest
from statistics import median

from common import ROOT
from extract import select_rows
from simulate import PathRandom, fast_simulate, simulate


def reference(profits, k, initial, ruin, length, horizon, paths, seed):
    wins, losses, times = [], [], []
    for path in range(paths):
        rng = PathRandom(seed, path)
        equity = initial
        for t in range(math.floor(len(profits) * horizon)):
            if t % length == 0:
                start = rng.randrange(len(profits) - length + 1)
            equity += profits[start + t % length] * (equity / initial) * k
            if equity >= initial * 2:
                wins.append(equity); times.append(t + 1); break
            if equity <= initial * ruin:
                losses.append(equity); break
    return [len(wins), len(losses), paths - len(wins) - len(losses),
            median(times) if times else '', median(wins) if wins else '', median(losses) if losses else '']


class SimulationTests(unittest.TestCase):
    def test_run_selection(self):
        rows = [dict(window='OOS', mult='1', proposal_id='G001', status='OK'),
                dict(window='OOS', mult='2', proposal_id='G001', status='OK'),
                dict(window='OOS', mult='1', proposal_id='G002', status='OK')]
        self.assertEqual(select_rows(rows, 'gold', 'OOS'), rows[:1])
        self.assertEqual(select_rows(rows, 'gold', 'IS'), [])
        with self.assertRaises(ValueError):
            select_rows(rows, 'fx', 'OOS')

    def test_known_outcomes(self):
        self.assertEqual(simulate([50], 1, 100, length=1, n_paths=5)['median_trades_double'], 2)
        self.assertEqual(simulate([-80], 1, 100, length=1, n_paths=5)['p_ruin'], 1)
        self.assertEqual(simulate([1], 1, 100, length=1, n_paths=5)['p_unresolved'], 1)
        self.assertEqual(simulate([-200, -200], 1, 100, length=2, n_paths=5)['median_final_ruin'], -100)

    def test_reference_and_backend(self):
        fields = ['n_double', 'n_ruin', 'n_unresolved', 'median_trades_double',
                  'median_final_double', 'median_final_ruin']
        for length in [1, 3, 7]:
            for ruin in [.1, .2, .3]:
                args = ([20, -40, -10, 30, 50, -160, 80], 1, 100, ruin, length, 2.5, 100, 42)
                expected = reference(*args)
                implementations = [simulate(*args)]
                if (ROOT / '_engine.exe').exists():
                    implementations.append(fast_simulate(ROOT / '_engine.exe', *args))
                for actual in implementations:
                    for name, value in zip(fields, expected):
                        if value == '':
                            self.assertEqual(actual[name], value)
                        else:
                            self.assertAlmostEqual(actual[name], value, places=9)

    def test_invalid_input(self):
        for profits, k, kwargs in [([], 1, {}), ([1], -1, {}),
                                   ([float('nan')], 1, {}), ([1], 1, {'length': 2}),
                                   ([1], 1, {'length': 1, 'ruin_frac': 1})]:
            with self.assertRaises(ValueError):
                simulate(profits, k, **kwargs)

    def test_repeatability(self):
        args = ([100, -20, 50, -80], 3)
        self.assertEqual(simulate(*args, length=2, n_paths=30), simulate(*args, length=2, n_paths=30))


if __name__ == '__main__':
    unittest.main()

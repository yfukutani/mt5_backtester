"""V014の主結果（期限2ヶ月・OOS・動的B(3) vs constant k=3）が乱数seedに依存しないか確認する。"""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import correct_ceiling as cc
import dynamic_k as dk

books = cc.load()
t_oos = [p for _, p in books[("both", "OOS")]]
n = len(t_oos)
rate = n / dk.MONTHS["OOS"]
H = int(round(rate * 2))

const_fn = dk.policy_constant(3)
dyn_fn = dk.policy_B(3)

print(f"OOS期限2ヶ月・H={H}steps・複数seedでの再現性確認")
print(f"{'seed':>10}{'constant P(2倍)':>18}{'動的B P(2倍)':>14}{'差':>9}")
diffs = []
for seed in (30271, 11111, 22222, 33333, 44444, 55555):
    paths = dk.generate_paths(t_oos, H, dk.N_PATHS, dk.L, seed=seed)
    rc = dk.run_policy(paths, const_fn, H)
    rd = dk.run_policy(paths, dyn_fn, H)
    diff = rd["p_hit"] - rc["p_hit"]
    diffs.append(diff)
    print(f"{seed:>10}{100*rc['p_hit']:>17.1f}%{100*rd['p_hit']:>13.1f}%{100*diff:>8.2f}pt")

print(f"\n差の平均: {100*sum(diffs)/len(diffs):+.2f}pt / 最小: {100*min(diffs):+.2f}pt / 最大: {100*max(diffs):+.2f}pt")

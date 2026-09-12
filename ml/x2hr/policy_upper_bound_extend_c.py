"""V035の追試：C族が格子端(c=3.0)で最大だったため、cを伸ばして飽和を確認する。"""
import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, r'C:\Users\f\source\repos\mt5_backtester\ml\x2hr')
import correct_ceiling as cc
import dynamic_k as dk
import dynamic_k_lag as dkl

N_PATHS = 10000
books = dkl.build_books()
pr_is, lg_is, _ = books["IS"]
pr_o, lg_o, _ = books["OOS"]
s_is = float(pr_is.std(ddof=1)) / cc.CAPITAL
rate_is = len(pr_is) / cc.MONTHS["IS"]

print("V035追試：C族のcを伸ばして飽和を確認（先読み・OOS窓で最良を選ぶ）")
print(f"{'期限':>6}{'c':>7}{'OOS到達':>9}{'破綻':>8}{'期限切れ':>10}")
for lim in (5.0, 6.0, 12.0):
    H = int(round(rate_is * lim))
    pp, pl = dkl.generate_paths_lag(pr_o, lg_o, H, N_PATHS, seed=710000 + int(lim * 100))
    best = None
    for c in (2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 12.0, 16.0):
        r = dkl.run_policy_lag(pp, pl, dk.policy_C(c, s_is), entry_sizing=True)
        mark = ""
        if best is None or r["p_hit"] > best[1]:
            best = (c, r["p_hit"]); mark = " ★"
        print(f"{lim:>5.0f}月{c:>7.1f}{100*r['p_hit']:>8.1f}%{100*r['p_ruin']:>7.1f}%"
              f"{100*r['p_exp']:>9.1f}%{mark}")
    print(f"  → 最良 c={best[0]} / {100*best[1]:.1f}%"
          f"{'  ✅85%到達' if best[1] >= 0.85 else '  ❌85%未達'}\n")

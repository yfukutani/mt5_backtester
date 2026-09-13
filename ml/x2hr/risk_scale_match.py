"""V096：**実装のリスク水準がHJBの前提と合っているか**（2026-09-13）。

【Codexの指摘②】
> V086はHJBの「形」を移植した方策であり、**HJBの絶対的な総リスク水準と一致する
> 保証がない。** 基準ブックの年率ボラを σ₀、期限をT年とすると、理想化した比例運用でも
> 対応には **`k·σ₀·√T = u_ref`** が必要。

つまり「HJBの形を使っている」だけでは足りず、**kがHJBの想定するリスク水準に
合っていなければ、そもそも別の方策を走らせている**ことになる。

【本スクリプトで測ること】
実履歴から、倍率 k=1 のときの**期限ボラ** `u(k=1) = (σ_profit/資金) × √(期限内取引数)`
を求め、HJBが想定する `u_ref = u*(0, τ=1)` と一致する k を逆算する。

    k_match = u_ref / u(k=1)

**k_match より大きい k を使っていれば、HJBの想定より過大なリスクを取っている。**
V086/V087 は 6ヶ月で k=4、12ヶ月で k=2 を使った。**これが妥当だったかを確認する。**

【限界】
- σ_profit は1取引の損益の標準偏差。**建玉が重なる効果を無視している**
  （重なりがあれば実際の期間ボラはこれより大きい）
- 最小ロットの床を無視した理想化
- 弱局面の取引数・分散は推定値。期間が約38ヶ月しかない
- **段階2の簡易検証である。採用の根拠にはしない**
"""
from __future__ import annotations

import csv
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dynamic_k_lag as dkl
import hjb_validate as hv

CAPITAL = 100000.0
QUIET_END = datetime(2020, 1, 1, tzinfo=timezone.utc)


def load(window):
    fx, gold = dkl.resolve_runs()
    rec = []
    for src in (fx.get(window), gold.get(window)):
        if src is None:
            continue
        rows = []
        for r in csv.DictReader(open(src, encoding="utf-8")):
            if int(r["magic"]) == 0:
                continue
            rows.append((int(r["time"]), int(r["entry"]),
                         int(r["position_id"]), float(r["profit"]),
                         float(r["volume"])))
        rows.sort()
        opened = {}
        for t, entry, pid, profit, vol in rows:
            if entry == 0:
                opened[pid] = (t, vol)
            else:
                o = opened.pop(pid, None)
                if o is None or profit == 0.0 or o[1] <= 0:
                    continue
                rec.append((o[0], profit))
    rec.sort()
    return rec


def main():
    print("=" * 110)
    print("V096：実装のリスク水準がHJBの前提と合っているか")
    print("=" * 110)
    print("★ Codexの指摘②：**HJBの形を使うだけでは足りない。**")
    print("  `k·σ₀·√T = u_ref` を満たすkでなければ、別の方策を走らせている。\n")

    # HJBの基準 u_ref
    xs, taus, tab, val = hv.policy_table(0.48)
    u_ref = float(np.interp(0.0, xs, tab[len(taus) - 1]))
    print(f"  HJB（H=0.48）の基準 u_ref = u*(0, τ=1) = **{u_ref:.4f}**")
    print(f"  HJBの値（到達確率の理論値）= {100*val:.1f}%\n")

    data = {"IS": load("IS"), "OOS": load("OOS")}
    quiet = [x for x in data["OOS"]
             if datetime.fromtimestamp(x[0], tz=timezone.utc) < QUIET_END]
    t0 = datetime.fromtimestamp(data["OOS"][0][0], tz=timezone.utc)
    span_q = (QUIET_END - t0).days / 30.44

    sets = [("IS窓（2021-06〜2026-06）", data["IS"], 60.0),
            ("OOS窓 全体", data["OOS"], 55.0),
            ("**OOS 弱局面のみ**", quiet, span_q)]

    print("=" * 110)
    print("【1. k=1 のときの期限ボラと、HJBに合うk】")
    print("=" * 110)
    print(f"{'窓':<26}{'期限':>6}{'取引数':>8}{'σ_profit':>11}"
          f"{'u(k=1)':>10}{'**k_match**':>13}{'実際に使ったk':>14}")
    used = {("**OOS 弱局面のみ**", 6): 4.0, ("**OOS 弱局面のみ**", 12): 2.0}
    for name, rec, span in sets:
        p = np.array([x[1] for x in rec], dtype=float)
        sd = float(p.std(ddof=1))
        per_month = len(rec) / span
        for months in (6, 12):
            n = per_month * months
            u1 = (sd / CAPITAL) * math.sqrt(n)
            km = u_ref / u1 if u1 > 0 else float("nan")
            uk = used.get((name, months))
            print(f"{name:<26}{months:>5}月{n:>8.0f}{sd:>11,.0f}"
                  f"{u1:>10.4f}{km:>13.2f}"
                  f"{('—' if uk is None else f'{uk:.1f}'):>14}")

    # ---------- 2. 使ったkに対応する到達率 ----------
    print("\n" + "=" * 110)
    print("【2. 実際に使ったkに対応する、拡散近似での到達率】")
    print("=" * 110)
    print("  k を変えると期限ボラが `u = (k/k_match)·u_ref` の水準にスケールする。")
    print("  HJBの形をそのまま使いつつ、全体を `k/k_match` 倍したときの到達率を測る。\n")
    p = np.array([x[1] for x in quiet], dtype=float)
    sd = float(p.std(ddof=1))
    per_month = len(quiet) / span_q

    print(f"{'期限':>5}{'真のH':>8}{'k_match':>10}{'使ったk':>9}{'倍率':>8}"
          f"{'到達':>9}{'破綻':>9}")
    Hs = {}
    for months, k_used in ((6, 4.0), (12, 2.0)):
        n = per_month * months
        u1 = (sd / CAPITAL) * math.sqrt(n)
        km = u_ref / u1
        scale = k_used / km
        s_trade = float(p.mean() / p.std(ddof=1))
        H_true = s_trade * math.sqrt(n)
        Hs[months] = H_true
        xs2, taus2, tab2, _ = hv.policy_table(round(H_true, 2))
        tab_scaled = tab2 * scale
        pr, ru, se = hv.forward(xs2, taus2, tab_scaled, H_true)
        print(f"{months:>4}月{H_true:>8.3f}{km:>10.2f}{k_used:>9.1f}"
              f"{scale:>8.2f}{100*pr:>8.1f}%{100*ru:>8.1f}%")

    print("\n  → **倍率が1.0から大きく離れていれば、HJBの想定と違うリスク水準で走っている**")

    print("\n" + "=" * 110)
    print("【限界】")
    print("=" * 110)
    print("  ・σ_profit は1取引の損益の標準偏差。**建玉の重なりを無視している**")
    print("    （重なりがあれば実際の期間ボラはこれより大きく、k_match は小さくなる）")
    print("  ・最小ロットの床を無視した理想化")
    print("  ・弱局面は約38ヶ月しかなく、分散・取引数とも推定値")
    print("  ・**段階2の簡易検証である。採用の根拠にはしない**")
    print("\n完了。")


if __name__ == "__main__":
    main()

"""V087：**入手可能な独立標本を最大化した対比較**（簡易検証・2026-09-13）。

【V086で分かったこと】

OOS弱局面・重なりのある138起点（7日刻み）では——

| 方策 | k=4 到達 | 破綻 |
|---|---:|---:|
| P 比例（基準） | 13.8% | 0.0% |
| T 時間のみ 1/√τ | 34.1% | 3.6% |
| **H HJB方策そのもの** | **50.7%** | 8.7% |
| X HJBの時間方向のみ | 33.3% | 4.3% |
| V083の式（誤り） | 52.2% | 14.5% |

**Codexの指摘を反映した正しいHJB方策（H）でも改善は残る。**
**しかも V083 の誤った式より破綻が低い（8.7% vs 14.5%）。**
**x依存は効いている**（H 50.7% vs X 33.3% ＝ +17.4pt）。

**ところが非重複起点（6本）では改善が消える**（k=4 で 33.3% vs 33.3%、k=8 では悪化）。

【問題の本質】
弱局面は約38ヶ月しかなく、非重複6ヶ月窓は6本、12ヶ月窓は3本。
**検出力がない。** 138起点は138回の独立試行ではない。

【本スクリプトの方針】
**入手可能な独立標本を最大化する。**
弱局面に限らず、**全期間（2016-11〜2026-06・115ヶ月）の非重複窓**を使う。

- 6ヶ月窓：**19本**（うち弱局面6本）
- 12ヶ月窓：**9本**

**好転局面を含むので保守評価ではない。** 弱局面限定の数字と必ず併記する。
**これは「実力値」ではなく「方策の差が一貫しているか」を見るための集合である。**

さらに、**起点を重ねた集合に対して移動ブロック・ブートストラップ**で
対応差の区間を出す（暦時間の依存を残す）。ブロック長への感度も見る。

【限界（Codexの指摘を反映）】
- 全期間を使うと**2020-2021の金の大相場**が入り、保守評価ではなくなる
- 19本・9本でも少ない。**115ヶ月しかないという事実は変わらない**
- ブートストラップは情報量を増やさない。区間の見積もりを直すだけ
- 履歴再生は**含み損益・期限時の残存建玉・証拠金不足を扱っていない**
- H=0.48 を弱局面OOSから推定した以上、**この方策について未使用OOSではない**
- **段階2の簡易検証である。採用の根拠にはしない**
"""
from __future__ import annotations

import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calendar_origins as co
import common_origin_deadline as cod
import deadline_aware_sizing as das
import deadline_committed as dc
import policy_decomposition as pd
import target_policy_gap as tpg

QUIET_END = tpg.QUIET_END
K_SHOW = [2.0, 4.0, 8.0]
CAP = 3.0
H_POL = 0.48
BOOT = 4000
SEED = 20260913


def load_all():
    """OOS窓とIS窓をつないで、全期間の取引列を作る。"""
    a, b = co.load_events("OOS")[0], co.load_events("IS")[0]
    rec = sorted(list(a) + list(b))
    return rec


def nonoverlap(start, end_cap, months):
    out, d = [], start
    while cod.add_months(d, months) <= end_cap:
        out.append(d)
        d = cod.add_months(d, months)
    return out


def pairs_at(rec, origins, k, pol, cap, months):
    ti = [x[0] for x in rec]
    out = []
    for d in origins:
        t_end = cod.add_months(d, months)
        t0, t1 = int(d.timestamp()), int(t_end.timestamp())
        hb, rb = dc.simulate(rec, ti, t0, t1, k, None, 0.0)
        hp, rp = dc.simulate(rec, ti, t0, t1, k, pol, cap)
        out.append((d, hb, hp, rb, rp))
    return out


def sign_test(pairs):
    b = sum(1 for _, hb, hp, _, _ in pairs if hb and not hp)
    c = sum(1 for _, hb, hp, _, _ in pairs if hp and not hb)
    n = b + c
    if n == 0:
        return b, c, 1.0
    lo = min(b, c)
    tail = sum(math.comb(n, i) for i in range(lo + 1)) / (2.0 ** n)
    return b, c, min(1.0, 2.0 * tail)


def block_boot(diffs, L, rng, reps=BOOT):
    """移動ブロック・ブートストラップで対応差の平均の区間を出す。"""
    n = len(diffs)
    if n < L:
        return (float("nan"), float("nan"))
    nb = int(math.ceil(n / L))
    starts_max = n - L
    means = np.empty(reps)
    for r in range(reps):
        idx = []
        for _ in range(nb):
            s = int(rng.integers(0, starts_max + 1))
            idx.extend(range(s, s + L))
        means[r] = float(np.mean([diffs[i] for i in idx[:n]]))
    return (float(np.percentile(means, 2.5)),
            float(np.percentile(means, 97.5)))


def main():
    print("=" * 116)
    print("V087：入手可能な独立標本を最大化した対比較（簡易検証）")
    print("=" * 116)
    print("★ V086で、Codexの指摘を反映した**正しいHJB方策でも改善は残った**。")
    print("  しかし非重複起点は弱局面で6本・3本しかなく、検出力がない。")
    print("  ここでは**全期間（115ヶ月）の非重複窓**を使い、独立標本を最大化する。")
    print("  **好転局面を含むので保守評価ではない。弱局面の数字と必ず併記する。**\n")

    rec_all = load_all()
    rec_oos = co.load_events("OOS")[0]
    a_oos, b_oos = co.WINDOW_RANGE["OOS"]
    a_is, b_is = co.WINDOW_RANGE["IS"]
    t_all0 = datetime.fromtimestamp(rec_all[0][0], tz=timezone.utc)
    print(f"  全期間：{t_all0:%Y-%m-%d} 〜 {b_is:%Y-%m-%d}"
          f"（{len(rec_all)}建玉）")
    base = das.Policy(H=H_POL)
    hjb = pd.HJB(base)

    rng = np.random.default_rng(SEED)

    for D in (6, 12):
        print("\n" + "=" * 116)
        print(f"【期限 {D}ヶ月】HJB方策そのもの（上限{CAP:.0f}倍・H={H_POL}）"
              f" vs 比例方策")
        print("=" * 116)
        sets = [
            ("**全期間・非重複**", rec_all, nonoverlap(a_oos, b_is, D)),
            ("弱局面・非重複", rec_oos, nonoverlap(a_oos, QUIET_END, D)),
        ]
        for sname, rec, og in sets:
            print(f"\n--- {sname}（{len(og)}本）---")
            print(f"{'k':>4}{'比例':>8}{'HJB':>8}{'差':>8}"
                  f"{'比例だけ':>9}{'HJBだけ':>9}{'符号検定p':>11}"
                  f"{'比例破綻':>9}{'HJB破綻':>9}")
            for k in K_SHOW:
                pr = pairs_at(rec, og, k, hjb, CAP, D)
                n = len(pr)
                rb = sum(x[1] for x in pr) / n
                rp = sum(x[2] for x in pr) / n
                ru_b = sum(x[3] for x in pr) / n
                ru_p = sum(x[4] for x in pr) / n
                b, c, p = sign_test(pr)
                print(f"{k:>4.0f}{100*rb:>7.1f}%{100*rp:>7.1f}%"
                      f"{100*(rp-rb):>7.1f}{b:>9}{c:>9}{p:>11.3f}"
                      f"{100*ru_b:>8.1f}%{100*ru_p:>8.1f}%")

        # ---- 重なりのある起点＋移動ブロック・ブートストラップ ----
        print(f"\n--- 重なりのある起点（7日刻み）＋移動ブロック・ブートストラップ ---")
        print("  ブロック長は「暦時間で何本の起点をまとめるか」。"
              f"{D}ヶ月期限なら約{int(D*30/7)}本で1窓ぶん")
        og7 = pd.all_origins(a_oos, QUIET_END, D, 7)
        print(f"{'k':>4}{'弱局面 比例':>12}{'HJB':>8}{'差':>8}"
              + "".join(f"{f'L={L} の95%区間':>22}"
                        for L in (int(D * 30 / 7), int(D * 30 / 7) * 2)))
        for k in K_SHOW:
            pr = pairs_at(rec_oos, og7, k, hjb, CAP, D)
            diffs = [float(x[2]) - float(x[1]) for x in pr]
            rb = sum(x[1] for x in pr) / len(pr)
            rp = sum(x[2] for x in pr) / len(pr)
            cells = ""
            for L in (int(D * 30 / 7), int(D * 30 / 7) * 2):
                lo, hi = block_boot(diffs, L, rng)
                cells += f"{f'[{100*lo:+.1f}, {100*hi:+.1f}]pt':>22}"
            print(f"{k:>4.0f}{100*rb:>11.1f}%{100*rp:>7.1f}%"
                  f"{100*(rp-rb):>7.1f}{cells}")

    print("\n" + "=" * 116)
    print("【限界】Codexの指摘を反映")
    print("=" * 116)
    print("  ・全期間を使うと**2020-2021の金の大相場**が入り、保守評価ではなくなる")
    print("  ・19本・9本でも少ない。**115ヶ月しかないという事実は変わらない**")
    print("  ・ブートストラップは情報量を増やさない。区間の見積もりを直すだけ")
    print("  ・履歴再生は**含み損益・期限時の残存建玉・証拠金不足を扱っていない**")
    print("  ・H=0.48 を弱局面OOSから推定した以上、**未使用OOSではない**")
    print("  ・**段階2の簡易検証である。採用の根拠にはしない**")
    print("\n完了。")


if __name__ == "__main__":
    main()

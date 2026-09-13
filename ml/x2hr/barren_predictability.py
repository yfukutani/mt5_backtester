"""V104：**不毛月は事前に予測できるか**（簡易検証・2026-09-14）。

【V102で分かった天井】
弱局面の不毛月18ヶ月でブック全体は −77,869円。**うち SCA GBPJPY だけで −66,697円（86%）。**
理想的に識別できれば **純益 58,541 → 191,935円（3.3倍）／12ヶ月マイナス窓 7/27 → 0/27。**

**問題は「相場の性質」ではなく「識別可能性」に還元された。**

【本スクリプトで測ること】
**最も安く・最も直接的な識別可能性の検証**＝「**前月までの情報で今月が読めるか**」。

| 検証 | 内容 |
|---|---|
| **A. 月次損益の自己相関** | ラグ1〜3。正なら「悪い月は続く」＝切り替えが効く |
| **B. 前月の符号で今月を予測** | 前月マイナス→今月もマイナスか（分割表） |
| **C. 建玉時のレンジ幅** | `\|price − sl\|/price` の月平均が翌月の損益を予測するか |
| **D. 切り替えルールの効果** | 「前月が負けたらSCA GBPJPYを止める」を実際に適用して移動窓を測る |

**Dが本命。** A〜Cで予測力が無ければ、月次の切り替えは効かず、
**日中の特徴量（ボラ・レンジ状態）に降りるしかない**と分かる。

【なぜV077と違うか】
V077は**ブック全体・取引単位**で入口フィルタを5種試して全滅した。
本スクリプトは**SCA GBPJPY 1枠・月単位**で、しかも**時間方向の予測**を見る。
（V077の「ストップ距離」はブック全体の取引単位での分位分割であり、別物。）

【限界】
- 弱局面は38ヶ月・IS窓は61ヶ月。**月次の標本が少なく、自己相関の推定は粗い**
- 切り替えルールは損益の線形な足し引き。**最小ロット制約を無視している**
- 「前月が負けたら止める」は**当月の途中で判定しない**（月初に決める）
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

SCA_GJ = 20261001
WEAK = (datetime(2016, 11, 9, tzinfo=timezone.utc),
        datetime(2020, 1, 1, tzinfo=timezone.utc))
IS_W = (datetime(2021, 6, 21, tzinfo=timezone.utc),
        datetime(2026, 6, 21, tzinfo=timezone.utc))


def load():
    """(t_in, profit, magic, rel_sl) を返す。rel_sl は建玉時のストップ距離の相対値。"""
    fx, gold = dkl.resolve_runs()
    rec = []
    for window in ("OOS", "IS"):
        for src in (fx.get(window), gold.get(window)):
            if src is None:
                continue
            rows = []
            for r in csv.DictReader(open(src, encoding="utf-8")):
                m = int(r["magic"])
                if m == 0:
                    continue
                rows.append((int(r["time"]), int(r["entry"]),
                             int(r["position_id"]), float(r["profit"]), m,
                             float(r["price"]), float(r["sl"])))
            rows.sort()
            opened = {}
            for t, entry, pid, profit, m, price, sl in rows:
                if entry == 0:
                    rel = (abs(price - sl) / price
                           if sl > 0 and price > 0 else 0.0)
                    opened[pid] = (t, m, rel)
                else:
                    o = opened.pop(pid, None)
                    if o is None or profit == 0.0:
                        continue
                    rec.append((o[0], profit, o[1], o[2]))
    rec.sort()
    return rec


def months_of(a, b):
    out, d = [], datetime(a.year, a.month, 1, tzinfo=timezone.utc)
    while d < b:
        out.append((d.year, d.month))
        d = (datetime(d.year + 1, 1, 1, tzinfo=timezone.utc) if d.month == 12
             else datetime(d.year, d.month + 1, 1, tzinfo=timezone.utc))
    return out


def monthly(rec, a, b, magic=None):
    ms = months_of(a, b)
    idx = {k: i for i, k in enumerate(ms)}
    pnl = np.zeros(len(ms))
    rel = [[] for _ in ms]
    for t, prof, m, r in rec:
        if magic is not None and m != magic:
            continue
        d = datetime.fromtimestamp(t, tz=timezone.utc)
        if not (a <= d < b):
            continue
        i = idx[(d.year, d.month)]
        pnl[i] += prof
        if r > 0:
            rel[i].append(r)
    relm = np.array([np.mean(x) if x else np.nan for x in rel])
    return ms, pnl, relm


def rolling(v, w):
    if len(v) < w:
        return np.array([])
    return np.array([v[i:i + w].sum() for i in range(len(v) - w + 1)])


def acf(v, lag):
    if len(v) <= lag + 2:
        return float("nan")
    a, b = v[:-lag], v[lag:]
    if a.std() == 0 or b.std() == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def main():
    print("=" * 108)
    print("V104：不毛月は事前に予測できるか（簡易検証）")
    print("=" * 108)
    print("★ V102より、不毛月の損失の86%は SCA GBPJPY 1枠。")
    print("  理想的に識別できれば純益3.3倍・12ヶ月マイナス窓ゼロ。")
    print("  **最も安い識別可能性の検証＝「前月までの情報で今月が読めるか」。**\n")

    rec = load()

    for label, (a, b) in (("OOS 弱局面（2016-11〜2019-12）", WEAK),
                          ("IS窓（2021-06〜2026-06）", IS_W)):
        ms, book, _ = monthly(rec, a, b)
        _, sca, sca_rel = monthly(rec, a, b, SCA_GJ)
        print("=" * 108)
        print(f"【{label}】{len(ms)}ヶ月")
        print("=" * 108)
        print(f"  ブック純益 {book.sum():+,.0f}円 / SCA GBPJPY {sca.sum():+,.0f}円")
        sign = "".join("+" if v > 0 else ("-" if v < 0 else "0") for v in sca)
        print(f"  SCA GBPJPY 月次の符号: {sign}")
        pos = int((sca > 0).sum())
        print(f"  プラスの月 {pos}/{len(sca)} ({100*pos/len(sca):.0f}%)\n")

        # --- A. 自己相関 ---
        print("  【A. 月次損益の自己相関】正なら『悪い月は続く』")
        cells = "".join(f"  ラグ{L}: {acf(sca, L):+.3f}" for L in (1, 2, 3))
        print(f"    SCA GBPJPY{cells}")
        cells = "".join(f"  ラグ{L}: {acf(book, L):+.3f}" for L in (1, 2, 3))
        print(f"    ブック全体{cells}")

        # --- B. 前月の符号で予測 ---
        print("\n  【B. 前月の符号で今月を予測】")
        prev_neg = sca[:-1] <= 0
        cur_neg = sca[1:] <= 0
        n = len(prev_neg)
        a11 = int((prev_neg & cur_neg).sum())
        a10 = int((prev_neg & ~cur_neg).sum())
        a01 = int((~prev_neg & cur_neg).sum())
        a00 = int((~prev_neg & ~cur_neg).sum())
        p_neg_given_neg = a11 / max(a11 + a10, 1)
        p_neg_given_pos = a01 / max(a01 + a00, 1)
        base = int(cur_neg.sum()) / max(n, 1)
        print(f"    前月マイナス → 今月マイナス: {a11}/{a11+a10} "
              f"({100*p_neg_given_neg:.0f}%)")
        print(f"    前月プラス   → 今月マイナス: {a01}/{a01+a00} "
              f"({100*p_neg_given_pos:.0f}%)")
        print(f"    無条件の今月マイナス率: {100*base:.0f}%")
        lift = p_neg_given_neg - base
        print(f"    **予測力（差）: {100*lift:+.1f}pt**"
              f"{'  ← 予測力なし' if abs(lift) < 0.10 else ''}")

        # --- C. レンジ幅 ---
        print("\n  【C. 建玉時のレンジ幅（|price−sl|/price の月平均）】")
        ok = ~np.isnan(sca_rel)
        if ok.sum() > 5:
            r_prev = sca_rel[:-1]
            p_next = sca[1:]
            m2 = ~np.isnan(r_prev)
            if m2.sum() > 5 and np.nanstd(r_prev[m2]) > 0:
                c = float(np.corrcoef(r_prev[m2], p_next[m2])[0, 1])
                print(f"    前月のレンジ幅 vs 今月の損益: 相関 {c:+.3f}"
                      f"{'  ← 予測力なし' if abs(c) < 0.3 else ''}")
            c2 = float(np.corrcoef(sca_rel[ok], sca[ok])[0, 1])
            print(f"    同月のレンジ幅 vs 同月の損益: 相関 {c2:+.3f}"
                  f"（**同月は事前に使えない。参考値**）")
        else:
            print("    レンジ幅のデータが不足")

        # --- D. 切り替えルール ---
        print("\n  【D. 切り替えルール】『前月が負けたら翌月はSCA GBPJPYを止める』")
        others = book - sca
        on = np.ones(len(sca), dtype=bool)
        for i in range(1, len(sca)):
            on[i] = sca[i - 1] > 0
        switched = others + np.where(on, sca, 0.0)
        print(f"{'':>6}{'純益':>13}{'12月移動 最小':>16}{'12月マイナス窓':>16}"
              f"{'6月マイナス窓':>15}")
        for name, v in (("現状", book), ("**切替**", switched),
                        ("常時OFF", others)):
            r12, r6 = rolling(v, 12), rolling(v, 6)
            print(f"{name:>6}{v.sum():>13,.0f}{r12.min():>16,.0f}"
                  f"{f'{int((r12 <= 0).sum())}/{len(r12)}':>16}"
                  f"{f'{int((r6 <= 0).sum())}/{len(r6)}':>15}")
        print(f"    （切替でOFFになった月: {int((~on).sum())}/{len(on)}）")
        print()

    print("=" * 108)
    print("【読み方】")
    print("=" * 108)
    print("  ・A・Bで予測力が無ければ、**月次の切り替えは効かない**")
    print("  ・その場合、識別は**日中の特徴量（ボラ・レンジ状態）**に降りるしかなく、")
    print("    決済ログでは検証できない＝**EAに実装してMT5で回す**必要がある")
    print("  ・Dで12ヶ月マイナス窓が減らなければ、この方向は閉じる")

    print("\n" + "=" * 108)
    print("【限界】")
    print("=" * 108)
    print("  ・弱局面38ヶ月・IS窓61ヶ月。**月次の標本が少なく推定は粗い**")
    print("  ・切り替えは損益の線形な足し引き。最小ロット制約を無視")
    print("  ・**段階2の簡易検証である。採用の根拠にはしない**")
    print("\n完了。")


if __name__ == "__main__":
    main()

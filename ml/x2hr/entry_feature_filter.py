"""V077：**建玉時点で分かる特徴量による取引の取捨選択**（2026-09-13）。

【なぜこれを試すか】
V056の枠組みでは、到達確率の天井 `Φ(期限シャープ)` を上げる手段は2つだけ。
- ① **1取引あたりのシャープを上げる**
- ② 期限内の取引数を増やす（√で効く）

②はV074・V075で測り切った（方針Aに6倍・方針Bに16倍の頻度が必要）。
**①は「新規戦略類型の提案」（C6）としては0件だったが、
「既存の取引を建玉時点の情報で取捨選択する」形ではまだ一度も試していない。**

【最初に確認すべき算術（これがこの案の厳しさ）】

取引の割合 q を残すと、期限内の取引数は q 倍になる。
期限シャープは `S_q × sqrt(q*N)`。元は `S * sqrt(N)`。改善の条件は——

    S_q / S  >  1/sqrt(q)

| 残す割合 q | 必要なシャープ改善 |
|---:|---:|
| 80% | **+11.8%** |
| 50% | **+41.4%** |
| 30% | **+82.6%** |
| 20% | **+123.6%** |

**取引を半分捨てるなら、1取引あたりの質が41%良くならないと損になる。**
これは非常に厳しい条件であり、**成立しない可能性のほうが高い。**

【建玉時点で利用できる特徴量（決済情報は一切使わない）】

| 特徴量 | 列 | 備考 |
|---|---|---|
| 時間帯（UTC時） | `time` | 東京/ロンドン/NY セッション |
| 曜日 | `time` | 月曜ギャップ・金曜手仕舞い |
| 方向 | `type` | 買い/売り |
| 相対ストップ距離 | `abs(price-sl)/price` | EA自身のリスク見積もり |
| 建玉サイズ | `volume` | EA自身の確信度 |

【手続き（事前登録）】
1. **IS窓だけ**で各特徴量の水準別に平均損益を見て、閾値・保持集合を決める
2. **OOS窓（弱局面の実履歴・86起点）**で期限シャープと到達率を測る
3. **全フィルタの結果を報告する**（IS/OOSとも）。ISで良くOOSで悪いものも隠さない

【限界】
- 特徴量は5つだけ。多重比較の補正はしていない（**ISで最良のものを選ぶ時点で
  選択バイアスがある**。だからOOSの数字だけを結論に使う）
- スプレッド・スリッページは元の記録のまま
- 弱局面の起点は86個。起点が重なるため独立ではない
- 取引を捨てても**EAの内部状態（ナンピン・両建て等）は変わらない前提**。
  実際には取引を止めると後続の建玉も変わるため、**これは上限側の見積もり**
"""
from __future__ import annotations

import csv
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calendar_origins as co
import dynamic_k_lag as dkl
import target_policy_gap as tpg

MULT = 2.0
QUIET_END = tpg.QUIET_END
K_GRID = tpg.K_GRID
CHECK = [3, 6, 12]


def load_feat(window):
    """(t_in, t_out, profit, volume, hour, wday, side, rel_sl) を返す。
    hour/wday/side/rel_sl はすべて**建玉時点**の情報。"""
    fx, gold = dkl.resolve_runs()
    rec = []
    for src in (fx.get(window), gold.get(window)):
        if src is None:
            continue
        rows = []
        for r in csv.DictReader(open(src, encoding="utf-8")):
            if int(r["magic"]) == 0:
                continue
            rows.append((int(r["time"]), int(r["entry"]), int(r["position_id"]),
                         float(r["profit"]), float(r["volume"]),
                         int(r["type"]), float(r["price"]), float(r["sl"])))
        rows.sort()
        opened = {}
        for t, entry, pid, profit, vol, typ, price, sl in rows:
            if entry == 0:
                rel = abs(price - sl) / price if (sl > 0 and price > 0) else 0.0
                opened[pid] = (t, vol, typ, rel)
            else:
                o = opened.pop(pid, None)
                if o is None or profit == 0.0 or o[1] <= 0:
                    continue
                d = datetime.fromtimestamp(o[0], tz=timezone.utc)
                rec.append((o[0], t, profit, o[1],
                            d.hour, d.weekday(), o[2], o[3]))
    rec.sort()
    return rec


def sharpe(vals):
    a = np.asarray(vals, dtype=float)
    if len(a) < 3 or a.std(ddof=1) == 0:
        return 0.0
    return float(a.mean() / a.std(ddof=1))


def horizon_sharpe(rec, months=12.0, span_months=55.0):
    """期限シャープ ＝ 1取引シャープ × sqrt(期限内の取引数)。"""
    s = sharpe([x[2] for x in rec])
    n = len(rec) * months / span_months
    return s, n, s * math.sqrt(max(n, 0.0))


def make_filters(is_rec):
    """**IS窓だけ**を見て保持集合を決める。"""
    out = {}

    by_h = {}
    for x in is_rec:
        by_h.setdefault(x[4], []).append(x[2])
    good_h = {h for h, v in by_h.items() if np.mean(v) > 0}
    out["時間帯（IS平均が正の時のみ）"] = (lambda x, s=good_h: x[4] in s)

    ranked = sorted(by_h.items(), key=lambda kv: -float(np.mean(kv[1])))
    top_h = {h for h, _ in ranked[:max(1, len(ranked) // 2)]}
    out["時間帯（IS上位半分）"] = (lambda x, s=top_h: x[4] in s)

    by_w = {}
    for x in is_rec:
        by_w.setdefault(x[5], []).append(x[2])
    good_w = {w for w, v in by_w.items() if np.mean(v) > 0}
    out["曜日（IS平均が正の曜日のみ）"] = (lambda x, s=good_w: x[5] in s)

    by_s = {}
    for x in is_rec:
        by_s.setdefault(x[6], []).append(x[2])
    best_s = max(by_s.items(), key=lambda kv: float(np.mean(kv[1])))[0]
    lab = "買い" if best_s == 0 else "売り"
    out["方向（IS優位側＝" + lab + "のみ）"] = (lambda x, s=best_s: x[6] == s)

    rels = np.array([x[7] for x in is_rec if x[7] > 0])
    if len(rels) > 10:
        med = float(np.median(rels))
        by_r = {"近": [], "遠": []}
        for x in is_rec:
            by_r["近" if x[7] <= med else "遠"].append(x[2])
        best_r = max(by_r.items(), key=lambda kv: float(np.mean(kv[1])))[0]
        if best_r == "近":
            out["ストップ距離（IS優位側＝近い半分）"] = (lambda x, m=med: x[7] <= m)
        else:
            out["ストップ距離（IS優位側＝遠い半分）"] = (lambda x, m=med: x[7] > m)

    mv = float(np.median([x[3] for x in is_rec]))
    by_v = {"小": [], "大": []}
    for x in is_rec:
        by_v["小" if x[3] <= mv else "大"].append(x[2])
    best_v = max(by_v.items(), key=lambda kv: float(np.mean(kv[1])))[0]
    if best_v == "小":
        out["建玉サイズ（IS優位側＝小さい半分）"] = (lambda x, m=mv: x[3] <= m)
    else:
        out["建玉サイズ（IS優位側＝大きい半分）"] = (lambda x, m=mv: x[3] > m)

    return out


def to_rec4(rec):
    return [(a, b, c, d) for a, b, c, d, *_ in rec]


def phi(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def main():
    print("=" * 122)
    print("V077：建玉時点で分かる特徴量による取引の取捨選択（倍率2倍固定）")
    print("=" * 122)
    print("★ V056の①「1取引あたりのシャープを上げる」を、既存取引の取捨選択で試す。\n")
    print("【最初に：この案が成立するための算術】")
    print("  割合 q を残すと 期限シャープ＝S_q×sqrt(q*N)。改善の条件は S_q/S > 1/sqrt(q)。")
    print(f"{'残す割合q':>10}{'必要なシャープ改善':>20}")
    for q in (0.8, 0.5, 0.3, 0.2):
        print(f"{100*q:>9.0f}%{100*(1/math.sqrt(q)-1):>19.1f}%")
    print("  → **半分捨てるなら質が41%良くならないと損になる。厳しい条件である。**\n")

    raw = {w: load_feat(w) for w in ("IS", "OOS")}
    a_oos, _ = co.WINDOW_RANGE["OOS"]
    a_is, b_is = co.WINDOW_RANGE["IS"]
    SPAN = {"IS": 60.0, "OOS": 55.0}

    filters = make_filters(raw["IS"])

    print("=" * 122)
    print("【1. 期限シャープ（12ヶ月）で見た効果】S_q*sqrt(q*N)。**これが天井を決める**")
    print("=" * 122)
    print(f"{'フィルタ':<32}│{'IS残':>7}{'IS 1取引S':>11}{'IS 期限S':>10}"
          f"│{'OOS残':>7}{'OOS 1取引S':>12}{'OOS 期限S':>11}{'OOS天井':>9}{'判定':>6}")
    base = {w: horizon_sharpe(raw[w], 12.0, SPAN[w]) for w in ("IS", "OOS")}
    print(f"{'（基準：全取引）':<32}│{len(raw['IS']):>7}{base['IS'][0]:>11.4f}"
          f"{base['IS'][2]:>10.3f}│{len(raw['OOS']):>7}{base['OOS'][0]:>12.4f}"
          f"{base['OOS'][2]:>11.3f}{100*phi(base['OOS'][2]):>8.1f}%{'—':>6}")
    keep = {}
    for name, fn in filters.items():
        row = []
        for w in ("IS", "OOS"):
            sub = [x for x in raw[w] if fn(x)]
            keep[(name, w)] = sub
            row.append((len(sub), horizon_sharpe(sub, 12.0, SPAN[w])))
        ok = row[1][1][2] > base["OOS"][2]
        print(f"{name:<32}│{row[0][0]:>7}{row[0][1][0]:>11.4f}{row[0][1][2]:>10.3f}"
              f"│{row[1][0]:>7}{row[1][1][0]:>12.4f}{row[1][1][2]:>11.3f}"
              f"{100*phi(row[1][1][2]):>8.1f}%{'OK' if ok else 'NG':>6}")

    print("\n" + "=" * 122)
    print("【2. 実際の到達率】弱局面の実履歴（起点＋18暦月 ≤ 2020-01-01・86起点）")
    print("=" * 122)
    print("  kはIS窓の6ヶ月基準で選ぶ（OOSを見ない）。方針A＝6ヶ月65%、方針B＝12ヶ月90%")
    print(f"{'フィルタ':<32}│{'k':>5}{'IS 6月':>9}{'IS 12月':>9}"
          f"│{'OOS 3月':>9}{'OOS 6月':>9}{'OOS 12月':>10}{'12月破綻':>10}"
          f"│{'方針A':>7}{'方針B':>7}")

    def run(rec_is, rec_oos, label):
        best, bp = None, -1.0
        for k in K_GRID:
            o = tpg.evaluate_quiet(rec_is, k, [6], a_is, b_is)
            if o[6][0] > bp:
                best, bp = k, o[6][0]
        oi = tpg.evaluate_quiet(rec_is, best, CHECK, a_is, b_is)
        oo = tpg.evaluate_quiet(rec_oos, best, CHECK, a_oos, QUIET_END)
        okA = oo[6][0] >= 0.65
        okB = oo[12][0] >= 0.90
        print(f"{label:<32}│{best:>5.0f}{100*oi[6][0]:>8.1f}%{100*oi[12][0]:>8.1f}%"
              f"│{100*oo[3][0]:>8.1f}%{100*oo[6][0]:>8.1f}%{100*oo[12][0]:>9.1f}%"
              f"{100*oo[12][1]:>9.1f}%│{'OK' if okA else 'NG':>7}{'OK' if okB else 'NG':>7}")

    run(to_rec4(raw["IS"]), to_rec4(raw["OOS"]), "（基準：全取引）")
    for name in filters:
        run(to_rec4(keep[(name, "IS")]), to_rec4(keep[(name, "OOS")]), name)

    print("\n" + "=" * 122)
    print("【限界】")
    print("=" * 122)
    print("  ・特徴量は5つのみ。多重比較の補正なし（ISで最良を選ぶ時点で選択バイアス）")
    print("  ・取引を捨ててもEAの内部状態は変わらない前提＝**上限側の見積もり**")
    print("  ・スプレッド・スリッページは元の記録のまま")
    print("  ・弱局面の起点は86個。起点が重なるため独立ではない")
    print("\n完了。")


if __name__ == "__main__":
    main()

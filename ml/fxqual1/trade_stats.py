"""枠ごとの「シグナル品質」を、ロットサイズを消した形で測る（段階2の土台）。

【なぜ R倍率で見るのか】
2026-09-08〜09-17 の掃引は、すべて **ロットの大小**の話だった（倍率・複利・risk%・
証拠金cap・枠の重み）。今回の主題は **枠そのものの質**である。円建て純益で見ると
枠の質と枠のロットが混ざるので、**1取引を「SL距離の何倍取れたか」= R倍率**に
正規化して見る。R倍率はロットにも口座残高にも依存しない。

    R = (決済価格 - 建値) / |建値 - SL|   （売りは符号反転）

【使う取引ログ】
`ml/fxcomp1/run_deals/fc_full_C001_*_deals.csv`
= 本番現行（RefCap=78,000固定・倍率1・重み全1.0）の FULL窓（2016.11-2026.06・115か月）。
固定サイジングなので、**取引の採否がロットで変わらない**＝シグナル品質を見るのに最も素直。

【この道具で測れないもの】
- **Pair と Carry は SL を持たない**（sl=0）ので R倍率が定義できない。別の指標で見る。
- 含み損益の経路（MFE/MAE）はログに無い。**「TPまで伸びたか」は分かるが
  「どこまで逆行したか」は分からない。**
- `profit_jpy` 列は `profit * usdjpy` になっており、**円口座では二重換算**である。
  results.csv の枠別純益と1円まで一致するのは `profit` 列のほう。ここでは `profit` を使う。
- ここで出る数字は **採用の根拠にはならない**（プロジェクト規律・段階2）。
  ふるい分けにのみ使う。
"""
from __future__ import annotations

import csv
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEALS = REPO / "ml" / "fxcomp1" / "run_deals"

MAGICS = {
    20260622: "PB_UJ", 20260627: "PB_GJ", 20260610: "RSI_UJ",
    20260605: "RSI_EU", 20260774: "RSI_GU", 20260629: "PAIR",
    20260650: "CARRY", 20261000: "SCA_UJ", 20261001: "SCA_GJ",
}
# 窓の境界（fxmargin3/measure.py と同じ定義）
OOS_FROM = datetime(2016, 11, 9, tzinfo=timezone.utc).timestamp()
IS_FROM = datetime(2021, 6, 20, tzinfo=timezone.utc).timestamp()
FULL_TO = datetime(2026, 6, 20, tzinfo=timezone.utc).timestamp()


def find_base_deals() -> Path:
    cands = sorted(DEALS.glob("fc_full_C001_*_deals.csv"))
    if not cands:
        raise SystemExit("C001 の FULL取引ログが見つからない")
    return cands[-1]


def load_trades(path: Path):
    """position_id で建て玉を組み、1取引 = (in, out) にまとめる。"""
    rows = []
    with open(path, encoding="utf-8") as f:
        for d in csv.DictReader(f):
            rows.append(d)
    opens, trades = {}, []
    for d in rows:
        pid = d["position_id"]
        if d["entry"] == "0":                      # 建玉
            opens[pid] = d
        else:                                       # 決済
            o = opens.pop(pid, None)
            if o is None:
                continue
            magic = int(o["magic"] or d["magic"] or 0)
            name = MAGICS.get(magic)
            if name is None:
                continue
            t_in, t_out = int(o["time"]), int(d["time"])
            ep, xp = float(o["price"]), float(d["price"])
            sl = float(o["sl"])
            is_buy = (o["type"] == "0")
            r = None
            if sl > 0:
                risk = abs(ep - sl)
                if risk > 0:
                    r = (xp - ep) / risk if is_buy else (ep - xp) / risk
            trades.append(dict(
                sleeve=name, t_in=t_in, t_out=t_out, is_buy=is_buy,
                entry=ep, exit=xp, sl=sl, r=r,
                pnl=float(d["profit"] or 0.0),
                vol=float(o["volume"] or 0.0),
                hold_h=(t_out - t_in) / 3600.0,
            ))
    return trades


def window_of(t: float) -> str | None:
    if OOS_FROM <= t < IS_FROM:
        return "OOS"
    if IS_FROM <= t < FULL_TO:
        return "IS"
    return None


def summarize(ts, key):
    """R倍率のある枠の要約。R が無い枠（Pair/Carry）は円建てで出す。"""
    out = {}
    for win in ("OOS", "IS"):
        sub = [t for t in ts if window_of(t["t_in"]) == win]
        if not sub:
            continue
        rs = [t["r"] for t in sub if t["r"] is not None]
        pnl = [t["pnl"] for t in sub]
        wins = [p for p in pnl if p > 0]
        row = dict(n=len(sub), win_rate=100.0 * len(wins) / max(1, len(pnl)),
                   pnl=sum(pnl), hold_h_med=median([t["hold_h"] for t in sub]))
        if rs:
            row.update(r_n=len(rs), r_sum=sum(rs), r_mean=sum(rs) / len(rs),
                       r_med=median(rs))
        out[win] = row
    return out


def median(xs):
    xs = sorted(xs)
    if not xs:
        return float("nan")
    m = len(xs) // 2
    return xs[m] if len(xs) % 2 else 0.5 * (xs[m - 1] + xs[m])


def main():
    p = find_base_deals()
    print(f"取引ログ: {p.name}")
    trades = load_trades(p)
    by = defaultdict(list)
    for t in trades:
        by[t["sleeve"]].append(t)

    print("\n=== 枠ごとの素の成績（本番現行サイジング・FULL窓を OOS/IS に分割）===")
    hdr = (f"{'枠':<8}{'窓':<5}{'取引':>6}{'勝率%':>8}{'純益(円)':>12}"
           f"{'ΣR':>9}{'平均R':>8}{'中央R':>8}{'保有h中央':>10}")
    print(hdr)
    for name in ("PB_UJ", "PB_GJ", "RSI_UJ", "RSI_EU", "RSI_GU",
                 "PAIR", "CARRY", "SCA_UJ", "SCA_GJ"):
        s = summarize(by.get(name, []), name)
        for win in ("OOS", "IS"):
            if win not in s:
                continue
            r = s[win]
            rs = (f"{r.get('r_sum', float('nan')):>9.1f}"
                  f"{r.get('r_mean', float('nan')):>8.3f}"
                  f"{r.get('r_med', float('nan')):>8.3f}"
                  if "r_sum" in r else f"{'—':>9}{'—':>8}{'—':>8}")
            print(f"{name:<8}{win:<5}{r['n']:>6}{r['win_rate']:>8.1f}"
                  f"{r['pnl']:>12,.0f}{rs}{r['hold_h_med']:>10.1f}")
    return trades, by


if __name__ == "__main__":
    main()

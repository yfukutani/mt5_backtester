# -*- coding: utf-8 -*-
"""枠別の証拠金効率を測る。

cap の応答曲線（第8報）は 60→100% で単調増加だった。
折り返しが無いということは、証拠金が律速しているということである。
証拠金が律速なら、判断基準は「純益」ではなく
「証拠金をどれだけ長く占有して、いくら稼いだか」でなければならない。

1建玉が占有する証拠金（JPY） = volume * 100,000 * 基軸→JPYレート / 25
これを保有時間で積分したものを 証拠金日（margin-yen-day）と呼ぶ。

    効率 = 純益 / 証拠金日

判断は IS窓（W7/W8/W9）だけで行い、OOS窓（W1/W2/W3）で評価する。
IS で決めて IS で測れば必ず良く見えるので、それでは何も分からない。
"""
import csv
import sys
from collections import defaultdict
from pathlib import Path

CONTRACT = 100_000
LEVERAGE = 25

KIND = {
    20260622: "price", 20260627: "price", 20260610: "price",
    20260605: "price*usdjpy", 20260774: "price*usdjpy",
    20260629: "price*usdjpy", 20260650: "price",
    20261000: "price", 20261001: "price",
}
NAME = {
    20260622: "PB UJ", 20260627: "PB GJ", 20260610: "RSI UJ",
    20260605: "RSI EU", 20260774: "RSI GU", 20260629: "Pair",
    20260650: "Carry", 20261000: "SCA UJ", 20261001: "SCA GJ",
}


def jpy_rate(row):
    kind = KIND.get(int(row["magic"]))
    if kind is None:
        return None
    price = float(row["price"])
    if kind == "price":
        return price
    usdjpy = float(row["usdjpy"])
    return price * usdjpy if usdjpy > 0 else None


def positions(path):
    """(magic, margin_jpy, hold_sec, profit_jpy, t_in, t_out) を返す。"""
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    rows.sort(key=lambda r: int(r["time"]))
    opened = {}
    out = []
    for r in rows:
        pid = r["position_id"]
        magic = int(r["magic"])
        if magic not in KIND:
            continue
        if int(r["entry"]) == 0:
            rate = jpy_rate(r)
            if rate is None:
                continue
            margin = float(r["volume"]) * CONTRACT * rate / LEVERAGE
            opened[pid] = (magic, margin, int(r["time"]))
        else:
            if pid not in opened:
                continue
            m, margin, t_in = opened.pop(pid)
            t_out = int(r["time"])
            out.append((m, margin, max(t_out - t_in, 0), float(r["profit"]), t_in, t_out))
    # 期末に残った建玉は決済損益に含まれないので、占有だけ計上しない（対称にするため捨てる）
    return out


def summarise(path):
    pos = positions(path)
    agg = defaultdict(lambda: {"n": 0, "profit": 0.0, "mdays": 0.0, "hold": 0.0, "margin": 0.0})
    for magic, margin, hold, profit, _ti, _to in pos:
        a = agg[magic]
        a["n"] += 1
        a["profit"] += profit
        a["mdays"] += margin * hold / 86400.0
        a["hold"] += hold / 86400.0
        a["margin"] += margin
    return agg


def peak_share(path):
    """総使用証拠金がピークの瞬間に、どの枠が何%占めていたか。"""
    pos = positions(path)
    ev = []
    for magic, margin, _hold, _p, t_in, t_out in pos:
        ev.append((t_in, +margin, magic))
        ev.append((t_out, -margin, magic))
    ev.sort()
    cur = defaultdict(float)
    total = 0.0
    best = (0.0, None, 0)
    for t, d, magic in ev:
        cur[magic] += d
        total += d
        if total > best[0]:
            best = (total, dict(cur), t)
    return best


def fmt(agg, title):
    print("")
    print("### " + title)
    print("| 枠 | 件数 | 純益 | 証拠金日 | 効率(円/証拠金日) | 平均保有(日) | 平均証拠金 |")
    print("|---|---:|---:|---:|---:|---:|---:|")
    rows = []
    for magic, a in agg.items():
        eff = a["profit"] / a["mdays"] if a["mdays"] > 0 else 0.0
        rows.append((eff, magic, a))
    rows.sort(reverse=True)
    tot_p = tot_m = 0.0
    for eff, magic, a in rows:
        tot_p += a["profit"]
        tot_m += a["mdays"]
        n = max(a["n"], 1)
        print("| {} | {} | {:,.0f} | {:,.0f} | **{:+.4f}** | {:.1f} | {:,.0f} |".format(
            NAME[magic], a["n"], a["profit"], a["mdays"], eff, a["hold"] / n, a["margin"] / n))
    print("| **合計** | | {:,.0f} | {:,.0f} | **{:+.4f}** | | |".format(
        tot_p, tot_m, tot_p / tot_m if tot_m else 0))
    return {m: (a["profit"] / a["mdays"] if a["mdays"] > 0 else 0.0) for _e, m, a in rows}


def main():
    base = Path(__file__).resolve().parents[1] / "fxwin1" / "run_deals"
    runs = {}
    for p in base.glob("mc_w*_X005_*_deals.csv"):
        w = p.name.split("_")[1]
        runs[w] = p
    if not runs:
        print("X005 の窓別 deals が見つからない", file=sys.stderr)
        return 1

    IS_W = ["w7", "w8", "w9"]     # 完全にISに収まる窓
    OOS_W = ["w1", "w2", "w3"]    # 完全にOOSに収まる窓

    def merged(ws):
        agg = defaultdict(lambda: {"n": 0, "profit": 0.0, "mdays": 0.0, "hold": 0.0, "margin": 0.0})
        for w in ws:
            if w not in runs:
                continue
            for magic, a in summarise(runs[w]).items():
                for k in a:
                    agg[magic][k] += a[k]
        return agg

    print("# 枠別 証拠金効率（X005・レバレッジ1:25・24か月窓を新規50万円で開始）")
    print("")
    print("各窓を合算している。効率 = 純益 / 証拠金日。")
    is_eff = fmt(merged(IS_W), "IS窓 W7+W8+W9（2022-11〜2026-06）— ここで判断する")
    oos_eff = fmt(merged(OOS_W), "OOS窓 W1+W2+W3（2016-11〜2020-11）— ここで評価する")

    print("")
    print("### 順位が期間をまたいで再現するか")
    print("| 枠 | IS効率 | IS順位 | OOS効率 | OOS順位 | 符号一致 |")
    print("|---|---:|---:|---:|---:|---|")
    is_rank = {m: i + 1 for i, m in enumerate(sorted(is_eff, key=lambda m: -is_eff[m]))}
    oos_rank = {m: i + 1 for i, m in enumerate(sorted(oos_eff, key=lambda m: -oos_eff[m]))}
    for m in sorted(is_eff, key=lambda m: -is_eff[m]):
        same = "○" if (is_eff[m] >= 0) == (oos_eff.get(m, 0) >= 0) else "**×**"
        print("| {} | {:+.4f} | {} | {:+.4f} | {} | {} |".format(
            NAME[m], is_eff[m], is_rank[m], oos_eff.get(m, 0), oos_rank.get(m, "-"), same))

    print("")
    print("### 使用証拠金がピークの瞬間の内訳（窓ごと）")
    print("| 窓 | ピーク使用証拠金 | 上位の占有 |")
    print("|---|---:|---|")
    for w in ["w1", "w2", "w3", "w7", "w8", "w9"]:
        if w not in runs:
            continue
        total, cur, _t = peak_share(runs[w])
        if not cur:
            continue
        top = sorted(((v, k) for k, v in cur.items() if v > 1), reverse=True)[:4]
        s = " / ".join("{} {:.0f}%".format(NAME[k], v / total * 100) for v, k in top)
        print("| {} | {:,.0f} | {} |".format(w.upper(), total, s))
    return 0


if __name__ == "__main__":
    sys.exit(main())

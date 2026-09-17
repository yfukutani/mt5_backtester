# -*- coding: utf-8 -*-
"""MT5を回さずに測れる3つ — A5(同時保有) / D1(RSI3枠の相関) / C9(最小ロット張り付き)。

第9報の50案のうち、deal ログだけで厳密に測れるものを先に潰す。

A5  枠ごとの同時保有本数の分布と、その枠が占有する証拠金のピーク。
    「本数の上限」が「占有の上限」になるかを見る。
D1  RSI 3枠（UJ/EU/GU）の月次損益の相関。W4 は3枠が同時に負けて作られた。
    3枠が独立でないなら、3枠あることは分散になっていない。
C9  `Clamp()` は最小ロット 0.01 に切り上げる。張り付いている取引は
    「サイジングされていない」＝リスク管理の外にある。
"""
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from margin_efficiency import NAME, positions  # noqa: E402

BASE = ROOT.parent / "fxwin1" / "run_deals"
IS_W = ["w7", "w8", "w9"]
OOS_W = ["w1", "w2", "w3"]
RSI = [20260610, 20260605, 20260774]


def find(win, pid="X005"):
    hits = sorted(BASE.glob(f"mc_{win}_{pid}_*_deals.csv"))
    return hits[0] if hits else None


def concurrency(paths):
    """枠ごとの同時保有本数の分布（イベント走査）。"""
    stat = defaultdict(lambda: {"max_n": 0, "max_margin": 0.0, "n_hist": defaultdict(float)})
    for path in paths:
        ev = []
        for magic, margin, _h, _p, t_in, t_out in positions(path):
            ev.append((t_in, +1, +margin, magic))
            ev.append((t_out, -1, -margin, magic))
        ev.sort()
        cnt = defaultdict(int)
        mar = defaultdict(float)
        prev_t = None
        for t, dn, dm, magic in ev:
            if prev_t is not None and t > prev_t:
                dt = (t - prev_t) / 86400.0
                for m, c in cnt.items():
                    if c > 0:
                        stat[m]["n_hist"][c] += dt
            cnt[magic] += dn
            mar[magic] += dm
            s = stat[magic]
            s["max_n"] = max(s["max_n"], cnt[magic])
            s["max_margin"] = max(s["max_margin"], mar[magic])
            prev_t = t
    return stat


def monthly_pnl(paths):
    out = defaultdict(lambda: defaultdict(float))
    for path in paths:
        for magic, _m, _h, profit, _ti, t_out in positions(path):
            d = datetime.fromtimestamp(t_out, tz=timezone.utc)
            out[magic][f"{d.year}-{d.month:02d}"] += profit
    return out


def corr(a, b):
    keys = sorted(set(a) | set(b))
    xs = [a.get(k, 0.0) for k in keys]
    ys = [b.get(k, 0.0) for k in keys]
    if len(keys) < 3:
        return float("nan")
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    return num / (dx * dy) if dx > 0 and dy > 0 else float("nan")


def minlot(paths):
    import csv
    agg = defaultdict(lambda: {"n": 0, "at_min": 0})
    for path in paths:
        for r in csv.DictReader(open(path, encoding="utf-8")):
            if int(r["entry"]) != 0:
                continue
            magic = int(r["magic"])
            if magic not in NAME:
                continue
            agg[magic]["n"] += 1
            if abs(float(r["volume"]) - 0.01) < 1e-9:
                agg[magic]["at_min"] += 1
    return agg


def section(title, wins):
    paths = [p for p in (find(w) for w in wins) if p]
    print("")
    print("## " + title)

    print("")
    print("### A5 同時保有（本数と、その枠の使用証拠金のピーク）")
    print("| 枠 | 最大同時本数 | 1本の時間% | 2本 | 3本 | 4本以上 | 枠の証拠金ピーク |")
    print("|---|---:|---:|---:|---:|---:|---:|")
    st = concurrency(paths)
    for m in sorted(st, key=lambda m: -st[m]["max_margin"]):
        s = st[m]
        tot = sum(s["n_hist"].values()) or 1.0
        p1 = s["n_hist"].get(1, 0) / tot * 100
        p2 = s["n_hist"].get(2, 0) / tot * 100
        p3 = s["n_hist"].get(3, 0) / tot * 100
        p4 = sum(v for k, v in s["n_hist"].items() if k >= 4) / tot * 100
        print("| {} | {} | {:.0f}% | {:.0f}% | {:.0f}% | {:.0f}% | {:,.0f} |".format(
            NAME[m], s["max_n"], p1, p2, p3, p4, s["max_margin"]))

    print("")
    print("### D1 月次損益の相関（RSI 3枠と、比較のため他枠）")
    mp = monthly_pnl(paths)
    order = [m for m in NAME if m in mp]
    print("| | " + " | ".join(NAME[m] for m in order) + " |")
    print("|---|" + "---:|" * len(order))
    for a in order:
        cells = []
        for b in order:
            c = corr(mp[a], mp[b])
            cells.append("—" if a == b else ("{:+.2f}".format(c) if c == c else "—"))
        print("| **{}** | ".format(NAME[a]) + " | ".join(cells) + " |")

    print("")
    print("### C9 最小ロット(0.01)に張り付いている割合")
    print("| 枠 | 発注数 | 0.01 | 割合 |")
    print("|---|---:|---:|---:|")
    ml = minlot(paths)
    for m in sorted(ml, key=lambda m: -ml[m]["at_min"] / max(ml[m]["n"], 1)):
        a = ml[m]
        print("| {} | {} | {} | {:.0f}% |".format(
            NAME[m], a["n"], a["at_min"], a["at_min"] / max(a["n"], 1) * 100))


def main():
    print("# 同時保有・相関・最小ロット張り付き（X005・1:25）")
    print("")
    print("deal ログだけで厳密に測れるもの。MT5 は1回も回していない。")
    section("IS窓 W7+W8+W9（2022-11〜2026-06）", IS_W)
    section("OOS窓 W1+W2+W3（2016-11〜2020-11）", OOS_W)
    return 0


if __name__ == "__main__":
    sys.exit(main())

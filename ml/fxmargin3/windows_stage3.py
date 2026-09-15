"""段階3の MT5 deal ログを 24か月窓に切り、各窓を新規50万円口座として測り直す。

【何に答えるか】
U011（保守版の枠別重み）が OOS 55か月で 11.33%/月 を出した。
だがこれは**1本の経路の標本1件**であり、
`docs/oanda_fx_cap_pathdep_20260915.md` が cap に対してやったのと同じ疑いが要る——
**期間を切っても同じ符号か。**

【なぜ切る必要があるか（U011 固有の理由）】
U011 は OOS の55か月で **50万円 → 1億8,282万円**まで増える。
- 最初の14か月で 500,000 → 23,981,861円（48倍）。この局面が幾何平均を作っている。
- 口座が大きくなると **ロットが銘柄上限 `SYMBOL_VOLUME_MAX`=50 に張り付く**
  （新規建玉に占める割合が 2017年 15.1% → 2021年 34.3%）。
- **張り付いた時点でサイジング規則は働いていない。**成績はブローカーの上限値が決めている。
「50万円の口座で月利6%」という問いに答えるなら、**毎回50万円から始めて測る**しかない。

【やること】
`subperiod.py` の窓シミュレーションをそのまま使う（cap=None＝logged の再現）。
複利枠のロットは `k = sim_eq / log_eq` で比例追従させ、固定ロット枠は追従させない。

【限界・必ず読むこと】
- equity は決済損益ベース＝含み損益を含まない。
- ⚠️ **ロットが50に張り付いた区間では比例追従が保守側にずれる。**
  logged のロットは上限で切られているので、k倍した sim ロットは
  「切られていないロット × k」より**小さい**。窓の成績は**下振れ側に出る**。
- 同じ1本の履歴から切り出した窓であり、独立標本ではない。符号の数え上げは目安。
"""
from __future__ import annotations

import argparse
import csv
import glob
import importlib.util
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]

_spec = importlib.util.spec_from_file_location("subperiod", ROOT / "subperiod.py")
sp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sp)
mcs = sp.mcs
DEPOSIT = sp.DEPOSIT


def load(pid, win):
    hits = sorted(glob.glob(str(ROOT / "run_deals" / f"mc_{win}_{pid}_*_deals.csv")))
    if not hits:
        return None
    rows = list(csv.DictReader(open(hits[-1], encoding="utf-8")))
    rows.sort(key=lambda r: int(r["time"]))
    return rows


def params_of(pid):
    for r in csv.DictReader(open(ROOT / "results.csv", encoding="utf-8")):
        if r["proposal_id"] == pid:
            return json.loads(r["parameter_json"]), r["description"]
    return {}, ""


def lot_ceiling_share(rows, t0, t1):
    """窓内の新規建玉のうち、**元の run で**銘柄上限50ロットに張り付いていた割合。

    ⚠️ これは窓シミュレーション側の値ではない。窓側は50万円から始めるので
    `k = sim_eq/log_eq` が小さくなり、sim のロットが上限に達することはまず無い。
    この列が意味するのは「**その期間の logged ロットが上限で切られていたか**」＝
    **比例追従の分母がどれだけ壊れているか**である。値が大きい窓ほど、
    `logged × k` は「切られていないロット × k」を下回り、窓の月利は下振れして出る。
    """
    n = hit = 0
    for r in rows:
        if r["entry"] != "0":
            continue
        ts = int(r["time"])
        if not (t0 <= ts < t1):
            continue
        n += 1
        if float(r["volume"]) >= 49.99:
            hit += 1
    return hit, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*", default=None)
    ap.add_argument("--win", default="oos")
    ap.add_argument("--span", type=int, default=24)
    ap.add_argument("--step", type=int, default=12)
    args = ap.parse_args()
    ids = args.ids or ["U000", "U001", "U011"]

    print(f"段階3の窓別再測定（{args.span}か月窓・進め幅{args.step}か月・"
          f"各窓を新規{DEPOSIT:,}円口座として計算）")
    print("元は MT5 の実測 deal ログ。窓への切り直しは決済損益ベースの再構成。\n")

    for pid in ids:
        rows = load(pid, args.win)
        if not rows:
            print(f"■ {pid}: deal ログ無し\n")
            continue
        params, desc = params_of(pid)
        comp = mcs.compounding_magics(params)
        edges = sp.month_edges(rows, args.step, args.span)

        print(f"■ {pid}  {desc}")
        hdr = "  %-18s %8s %14s %8s %8s %10s" % (
            "期間", "建玉", "純益", "月利", "最大DD", "元run上限")
        print(hdr)
        print("  " + "-" * (len(hdr) - 2))
        geos = []
        for t0, t1, label in edges:
            s = sp.simulate_window(rows, comp, None, t0, t1)
            if s["opened"] == 0:
                continue
            g = sp.geo(s["monthly"])
            geos.append(g)
            hit, n = lot_ceiling_share(rows, t0, t1)
            share = f"{100 * hit / n:.0f}%" if n else "-"
            print("  %-18s %8d %14s %7.2f%% %7.1f%% %10s" % (
                label, s["opened"], format(round(s["net"]), ","),
                g, 100 * s["dd"], share))
        if geos:
            print("  " + "-" * (len(hdr) - 2))
            print("  %-18s %8s %14s %7.2f%%  (平均 %.2f%% / 最悪 %.2f%% / 6%%以上 %d/%d)"
                  % ("中央値", "", "", statistics.median(geos),
                     statistics.fmean(geos), min(geos),
                     sum(1 for g in geos if g >= 6.0), len(geos)))
        print()

    print("注: 「元run上限」は、**元の55か月/115か月の run** でその期間の新規建玉のロットが")
    print("    銘柄上限50に達していた割合。窓シミュレーション側の値ではない。")
    print("    ここが大きい期間では logged ロットが上限で切られているので、")
    print("    `logged × k` は本来のロットを下回り、**窓の月利は下振れして出る**。")
    print("    したがってこの表は U011 に対して保守側の推定であり、実測で確かめる必要がある。")


if __name__ == "__main__":
    main()

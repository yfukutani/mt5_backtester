"""Claude A10「証拠金維持率でロットを制限する」を deal ログから再構成する（段階2）。

【何に答えるか】
docs/oanda_fx_scagj_weight_20260915.md の §4 は、このブックを止めているのが
**DDでもリスク許容度でもなく「レバレッジ25の証拠金」**だと結論した。
T039（SCA_GJ重み1.0）は OOS 3.23%/月だが使用証拠金 215.4% で実行できない。

しかし **215.4% は「ピーク」であって「常時」ではない**——100%を超えたのは
2,750時点中 76時点（2.8%）だけである。
ならば「収まる範囲までロットを削る」だけで、残り97%の時間の成績は保てるのではないか。
これが A10 であり、同ドキュメントが
「制約として最後まで残った唯一の軸」と書いたものである。

【どう測るか — なぜ deal ログだけで測れるか】
ロットを k 倍に削っても建玉の値動きは変わらない。約定価格も決済価格も同じである。
したがって **その建玉の損益はちょうど k 倍**になる。これは近似ではなく厳密である。

厳密でないのは1点だけ: 削った結果 equity が変わると、その後のロットも変わる。
複利枠のロットは equity に比例するので、
    sim_lot = logged_lot * (sim_equity / logged_equity)
で追従させる。この比例は EA の LotRisk() / RefCap=0 の定義そのものなので、
cap 無しで走らせれば logged の純益を厳密に再現するはずである（自己検証に使う）。

【限界・必ず読むこと】
- equity は**決済損益ベース**（含み損益を含まない）。実際の証拠金維持率はこれより悪い。
- **拒否された注文は deal ログに無い。** logged 側が既に壁に当たっていた可能性は消せない。
- 固定ロット枠（Pair・mask外のSCA）は equity に連動しないので scale=1 で扱う。
- ロットは 0.01 刻みに切り下げる。丸めて 0 になる注文は発注しない扱い。
- **段階2の簡易検証。採用の最終判断は MT5 バックテストで行う。**
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

DEPOSIT = 500_000
LEVERAGE = 25
CONTRACT = 100_000
LOT_STEP = 0.01
MIN_LOT = 0.01

KIND = {
    20260622: "price", 20260627: "price", 20260610: "price",
    20260605: "price*usdjpy", 20260774: "price*usdjpy", 20260629: "price*usdjpy",
    20260650: "price", 20261000: "price", 20261001: "price",
}
SLEEVE_NAME = {
    20260622: "PB UJ", 20260627: "PB GJ", 20260610: "RSI UJ",
    20260605: "RSI EU", 20260774: "RSI GU", 20260629: "Pair",
    20260650: "Carry", 20261000: "SCA UJ", 20261001: "SCA GJ",
}
# FxRiskMask の bit -> magic（EA: bit0=RSI_UJ bit1=RSI_EU bit2=RSI_GU bit3=SCA_UJ bit4=SCA_GJ）
MASK_BIT_MAGIC = {0: 20260610, 1: 20260605, 2: 20260774, 3: 20261000, 4: 20261001}
# RefCap_* を持つ枠（0 なら equity 連動＝複利）
REFCAP_MAGIC = {"RefCap_PB_USDJPY": 20260622, "RefCap_PB_GBPJPY": 20260627,
                "RefCap_CARRY": 20260650}


def jpy_rate(row):
    kind = KIND.get(int(row["magic"]))
    if kind is None:
        return None
    price = float(row["price"])
    if kind == "price":
        return price
    usdjpy = float(row["usdjpy"])
    return price * usdjpy if usdjpy > 0 else None


def compounding_magics(params):
    """この構成で equity に連動してロットが動く枠の magic 集合。"""
    out = set()
    mask = int(params.get("FxRiskMask", 0))
    if float(params.get("FxRiskRefCap", 0)) == 0 and mask:
        for bit, magic in MASK_BIT_MAGIC.items():
            if mask & (1 << bit):
                out.add(magic)
    for key, magic in REFCAP_MAGIC.items():
        if float(params.get(key, 0)) == 0:
            out.add(magic)
    return out


def simulate(rows, comp_magics, cap):
    """cap = 使用証拠金/equity の上限（None で無制限＝logged の再現）。"""
    log_eq = sim_eq = float(DEPOSIT)
    sim_eq_min = float(DEPOSIT)
    sim_eq_peak = float(DEPOSIT)
    sim_dd = 0.0
    used = 0.0                    # 現在の使用証拠金（sim側・JPY）
    pos = {}                      # pid -> dict(k, need_unit, vol_left, magic)
    skipped = trimmed = opened = 0
    worst_ratio = 0.0
    monthly = defaultdict(float)
    cut_by_sleeve = defaultdict(float)
    lots = []                     # 実際に発注したロット（実行可能性の点検用）
    max_margin = 0.0

    for r in rows:
        magic = int(r["magic"])
        pid = r["position_id"]
        if r["entry"] == "0":                                 # IN
            rate = jpy_rate(r)
            vol = float(r["volume"])
            if rate is None or rate <= 0 or vol <= 0:
                continue
            opened += 1
            need_unit = vol * CONTRACT * rate / LEVERAGE      # logged ロットの必要証拠金
            k = (sim_eq / log_eq) if (magic in comp_magics and log_eq > 0) else 1.0
            if k < 0:
                k = 0.0
            if cap is not None and sim_eq > 0:
                avail = cap * sim_eq - used
                if need_unit * k > avail:
                    k = max(0.0, avail / need_unit) if need_unit > 0 else 0.0
                    trimmed += 1
            lot = math.floor(vol * k / LOT_STEP) * LOT_STEP   # 0.01刻みへ切り下げ
            if lot < MIN_LOT - 1e-12:
                skipped += 1
                pos[pid] = {"k": 0.0, "need_unit": need_unit,
                            "vol_left": vol, "magic": magic}
                continue
            k = lot / vol
            lots.append(lot)
            pos[pid] = {"k": k, "need_unit": need_unit, "vol_left": vol, "magic": magic}
            used += need_unit * k
            max_margin = max(max_margin, used)
        else:                                                 # OUT
            p = pos.get(pid)
            profit = float(r["profit"])
            vol = float(r["volume"])
            log_eq += profit
            if p is None:
                sim_eq += profit                              # 対応するINが窓の外
                k_applied = 1.0
            else:
                k_applied = p["k"]
                sim_eq += profit * k_applied
                cut_by_sleeve[p["magic"]] += profit * (1.0 - k_applied)
                frac = min(1.0, vol / p["vol_left"]) if p["vol_left"] > 0 else 1.0
                used -= p["need_unit"] * k_applied * frac
                p["vol_left"] -= vol
                if p["vol_left"] <= 1e-9:
                    pos.pop(pid, None)
            used = max(0.0, used)
            month = datetime.fromtimestamp(int(r["time"]), timezone.utc).strftime("%Y-%m")
            monthly[month] += profit * k_applied
            sim_eq_min = min(sim_eq_min, sim_eq)
            sim_eq_peak = max(sim_eq_peak, sim_eq)
            if sim_eq_peak > 0:
                sim_dd = max(sim_dd, (sim_eq_peak - sim_eq) / sim_eq_peak)
        if sim_eq > 0:
            worst_ratio = max(worst_ratio, used / sim_eq)

    lots.sort()
    return {"net": sim_eq - DEPOSIT, "final": sim_eq, "min_eq": sim_eq_min,
            "dd": sim_dd, "worst_ratio": worst_ratio, "opened": opened,
            "trimmed": trimmed, "skipped": skipped, "max_margin": max_margin,
            "max_lot": lots[-1] if lots else 0.0,
            "p99_lot": lots[int(len(lots) * 0.99)] if lots else 0.0,
            "med_lot": lots[len(lots) // 2] if lots else 0.0,
            "monthly": dict(monthly), "cut": dict(cut_by_sleeve)}


def geo_monthly(monthly):
    """月次損益列から複利の幾何平均月利・中央値・上位3か月除外値を出す。"""
    eq = float(DEPOSIT)
    rets = []
    for m in sorted(monthly):
        if eq <= 0:
            break
        rets.append(monthly[m] / eq)
        eq += monthly[m]
    if not rets:
        return 0.0, 0.0, 0.0

    def geo(xs):
        acc = 1.0
        for x in xs:
            acc *= max(1e-9, 1.0 + x)
        return acc ** (1.0 / len(xs)) - 1.0

    med = sorted(rets)[len(rets) // 2]
    drop3 = sorted(rets)[:-3] if len(rets) > 3 else rets
    return geo(rets) * 100, med * 100, geo(drop3) * 100


def load(repo, pid, win):
    hits = sorted(repo.glob("ml/fxrisk3/run_deals/ft_%s_%s_*_deals.csv" % (win, pid)))
    if not hits:
        return None
    rows = list(csv.DictReader(open(hits[-1], encoding="utf-8")))
    rows.sort(key=lambda r: int(r["time"]))
    return rows


def params_of(repo, pid):
    for r in csv.DictReader(open(repo / "ml/fxrisk3/results.csv", encoding="utf-8")):
        if r["proposal_id"] == pid:
            return json.loads(r["parameter_json"]), r["description"]
    return {}, ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--caps", default="none,1.0,0.7,0.5,0.3")
    args = ap.parse_args()
    ids = args.ids or ["T039", "T043", "T045", "T035"]
    repo = Path(__file__).resolve().parents[2]
    caps = [None if c == "none" else float(c) for c in args.caps.split(",")]

    print("A10 証拠金上限サイジング（レバレッジ%d・入金%s円）" % (LEVERAGE, format(DEPOSIT, ",")))
    print("equityは決済損益ベース＝含み損を含まない。段階2の簡易検証。\n")
    for pid in ids:
        params, desc = params_of(repo, pid)
        comp = compounding_magics(params)
        print("■ %s  %s" % (pid, desc))
        print("  複利枠: %s" % ", ".join(SLEEVE_NAME.get(m, str(m)) for m in sorted(comp)))
        for win in ("full", "oos"):
            rows = load(repo, pid, win)
            if not rows:
                continue
            print("  --- %s ---" % win.upper())
            print("  %6s %14s %8s %8s %9s %7s %11s %10s %11s %9s %9s"
                  % ("cap", "純益", "月利", "中央値", "上位3除外",
                     "最大DD", "最低資産", "証拠金最大", "削った注文",
                     "最大ロット", "証拠金実額"))
            for cap in caps:
                s = simulate(rows, comp, cap)
                g, med, d3 = geo_monthly(s["monthly"])
                label = "無制限" if cap is None else "%.0f%%" % (cap * 100)
                print("  %6s %14s %7.2f%% %7.2f%% %8.2f%% %6.1f%% %11s %9.1f%% %5d/%-5d %9.2f %13s"
                      % (label, format(round(s["net"]), ","), g, med, d3,
                         s["dd"] * 100, format(round(s["min_eq"]), ","),
                         s["worst_ratio"] * 100, s["trimmed"], s["opened"],
                         s["max_lot"], format(round(s["max_margin"]), ",")))
        print()
    print("注: 拒否された注文は deal ログに無い。ロット削減の損益は k 倍で厳密だが、")
    print("    equity 経路が変わる分の再帰は比例近似である。MT5 で確認するまで採用しない。")


if __name__ == "__main__":
    main()

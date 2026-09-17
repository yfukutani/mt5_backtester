"""cap の効果が「たまたまその経路だっただけ」でないかを、期間を切って確かめる（段階2）。

【何に答えるか】
`docs/oanda_fx_margin_cap_20260915.md` §5 は、自分の結果のいちばん弱いところを
こう書いている。

  > この結果でいちばん疑うべきは「cap を掛けたほうが純益が増える」という点である。
  > OOS の cap無し 6,431,404円 に対し cap80% は 7,229,106円——削ったのに 12% 増えている。
  > 機構としては説明がつく（ボラティリティ・ドラッグの低減）。
  > だがこれは**経路依存**であり、**別の期間で同じ符号になる保証はない。**

この「保証はない」を、測れる形にする。**115か月を独立した部分期間に切り、
各期間を入金50万から開始し直して、cap の符号が期間ごとに変わるかを数える。**
1本の長い経路では「cap が勝った」は標本1件でしかない。切れば標本が増える。

Codex案 #45（時系列ウォークフォワード）・#47（期間を区切った再標本化）に対応する。

【なぜ MT5 なしで測れるか】
`ml/fxmargin2/margin_cap_sim.py` と同じ理屈——ロットを k 倍にすればその建玉の損益は
ちょうど k 倍であり、これは近似ではない。厳密でないのは
「削った結果 equity が変わると、その後の複利枠のロットも変わる」ぶんの比例追従だけである。

ただし部分期間では1点だけ注意が要る。**logged 側の equity は窓の途中から始まらない。**
複利枠の logged ロットは「その時点の logged equity」に比例して決まっていたので、
k = sim_eq / log_eq を出すには log_eq を**ログの先頭から**正しく持ち回る必要がある。
そこで窓の前の行も読み飛ばさず、log_eq だけは更新し続ける。

【限界・必ず読むこと】
- equity は決済損益ベース＝**含み損を含まない**。実際の最大DDはこれより深い。
- 部分期間は互いに重なりのない連続区間だが、**同じ1本の履歴から切り出した**ものであり、
  独立標本ではない。符号の数え上げは目安であって検定ではない。
- 窓をまたぐ建玉は「**建てた時刻が窓の中にある**」もののみ採用し、決済は窓外でも処理する。
  窓端で強制決済すると、勝ち逃げ・損切り回避の両方向にバイアスが出るため。
- **段階2の簡易検証。採用の最終判断は MT5 バックテストで行う。**
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "mcs", REPO / "ml" / "fxmargin2" / "margin_cap_sim.py")
mcs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mcs)

DEPOSIT = mcs.DEPOSIT
CONTRACT = mcs.CONTRACT
LEVERAGE = mcs.LEVERAGE
LOT_STEP = mcs.LOT_STEP
MIN_LOT = mcs.MIN_LOT


def simulate_window(rows, comp_magics, cap, t0, t1):
    """[t0, t1) に**建てた**取引だけで、入金50万から始める口座を再構成する。

    log_eq はログの先頭から通して更新する（複利枠の logged ロットの基準だから）。
    """
    log_eq = float(DEPOSIT)
    sim_eq = float(DEPOSIT)
    sim_eq_min = sim_eq_peak = float(DEPOSIT)
    sim_dd = 0.0
    used = 0.0
    pos = {}
    opened = trimmed = skipped = 0
    monthly = defaultdict(float)
    worst_ratio = 0.0

    for r in rows:
        ts = int(r["time"])
        pid = r["position_id"]
        if r["entry"] == "0":                                  # IN
            if not (t0 <= ts < t1):
                continue                                       # 窓外の建玉は採らない
            magic = int(r["magic"])
            rate = mcs.jpy_rate(r)
            vol = float(r["volume"])
            if rate is None or rate <= 0 or vol <= 0:
                continue
            opened += 1
            need_unit = vol * CONTRACT * rate / LEVERAGE
            k = (sim_eq / log_eq) if (magic in comp_magics and log_eq > 0) else 1.0
            if k < 0:
                k = 0.0
            if cap is not None and sim_eq > 0:
                avail = cap * sim_eq - used
                if need_unit * k > avail:
                    k = max(0.0, avail / need_unit) if need_unit > 0 else 0.0
                    trimmed += 1
            lot = math.floor(vol * k / LOT_STEP) * LOT_STEP
            if lot < MIN_LOT - 1e-12:
                skipped += 1
                pos[pid] = {"k": 0.0, "need_unit": need_unit, "vol_left": vol}
                continue
            k = lot / vol
            pos[pid] = {"k": k, "need_unit": need_unit, "vol_left": vol}
            used += need_unit * k
        else:                                                  # OUT
            profit = float(r["profit"])
            log_eq += profit                                   # 窓の内外を問わず常に更新
            p = pos.get(pid)
            if p is None:
                continue                                       # 窓外で建てた玉は sim に無い
            vol = float(r["volume"])
            k_applied = p["k"]
            sim_eq += profit * k_applied
            frac = min(1.0, vol / p["vol_left"]) if p["vol_left"] > 0 else 1.0
            used = max(0.0, used - p["need_unit"] * k_applied * frac)
            p["vol_left"] -= vol
            if p["vol_left"] <= 1e-9:
                pos.pop(pid, None)
            month = datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m")
            monthly[month] += profit * k_applied
            sim_eq_min = min(sim_eq_min, sim_eq)
            sim_eq_peak = max(sim_eq_peak, sim_eq)
            if sim_eq_peak > 0:
                sim_dd = max(sim_dd, (sim_eq_peak - sim_eq) / sim_eq_peak)
        if sim_eq > 0:
            worst_ratio = max(worst_ratio, used / sim_eq)

    return {"net": sim_eq - DEPOSIT, "min_eq": sim_eq_min, "dd": sim_dd,
            "opened": opened, "trimmed": trimmed, "skipped": skipped,
            "worst_ratio": worst_ratio, "monthly": dict(monthly)}


def geo(monthly):
    eq = float(DEPOSIT)
    rets = []
    for mth in sorted(monthly):
        if eq <= 0:
            break
        rets.append(monthly[mth] / eq)
        eq += monthly[mth]
    if not rets:
        return 0.0
    acc = 1.0
    for x in rets:
        acc *= max(1e-9, 1.0 + x)
    return (acc ** (1.0 / len(rets)) - 1.0) * 100


def month_edges(rows, step_months, span_months):
    """ログの期間を月境界で刻み、(t0, t1, ラベル) の列を返す。"""
    times = [int(r["time"]) for r in rows]
    first = datetime.fromtimestamp(min(times), timezone.utc)
    last = datetime.fromtimestamp(max(times), timezone.utc)
    start = datetime(first.year, first.month, 1, tzinfo=timezone.utc)
    out = []
    y, mo = start.year, start.month
    while True:
        a = datetime(y, mo, 1, tzinfo=timezone.utc)
        ny, nmo = y + (mo - 1 + span_months) // 12, (mo - 1 + span_months) % 12 + 1
        b = datetime(ny, nmo, 1, tzinfo=timezone.utc)
        if a >= last:
            break
        out.append((int(a.timestamp()), int(b.timestamp()),
                    f"{a:%Y-%m}〜{b:%Y-%m}"))
        y, mo = y + (mo - 1 + step_months) // 12, (mo - 1 + step_months) % 12 + 1
        if b > last:
            break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", default="T036")
    ap.add_argument("--win", default="full")
    ap.add_argument("--caps", default="none,0.85,0.80,0.75,0.70")
    ap.add_argument("--span", type=int, default=23, help="部分期間の長さ（月）")
    ap.add_argument("--step", type=int, default=23, help="窓の進め幅（月）。span未満で重なる")
    args = ap.parse_args()

    rows = mcs.load(REPO, args.id, args.win)
    if not rows:
        raise SystemExit(f"deal ログが見つかりません: {args.id} {args.win}")
    params, desc = mcs.params_of(REPO, args.id)
    comp = mcs.compounding_magics(params)
    caps = [None if c == "none" else float(c) for c in args.caps.split(",")]

    print(f"■ {args.id}  {desc}")
    print(f"  窓: {args.win.upper()} を {args.span}か月ごと"
          f"（進め幅 {args.step}か月）に切り、各期間を入金{DEPOSIT:,}円から開始し直す")
    print("  equity は決済損益ベース＝含み損を含まない。段階2の簡易検証。\n")

    edges = month_edges(rows, args.step, args.span)
    base_cap = None
    table = {}
    for t0, t1, label in edges:
        table[label] = {}
        for cap in caps:
            s = simulate_window(rows, comp, cap, t0, t1)
            table[label][cap] = (s, geo(s["monthly"]))

    hdr = "  %-18s %8s" % ("期間", "建玉")
    for cap in caps:
        hdr += " %16s" % ("無制限" if cap is None else "cap%.0f%%" % (cap * 100))
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for _, _, label in edges:
        row = table[label]
        line = "  %-18s %8d" % (label, row[caps[0]][0]["opened"])
        for cap in caps:
            s, g = row[cap]
            line += " %10s/%4.1f%%" % (format(round(s["net"]), ","), g)
        print(line)
    print("\n  （各セルは 純益円 / 月利%。月利は幾何平均の複利）\n")

    print("  最大DD（決済損益ベース）")
    for _, _, label in edges:
        line = "  %-18s        " % label
        for cap in caps:
            line += " %15.1f%%" % (table[label][cap][0]["dd"] * 100)
        print(line)

    # 【信頼性の点検】後半の窓ほど logged equity が大きいので k=sim_eq/log_eq が小さくなり、
    # 0.01 刻みへの切り下げで発注そのものが消える。消えた割合が大きい窓の数字は読めない。
    print("\n  丸めで消えた建玉 / 全建玉（この割合が大きい窓の数字は信用できない）")
    for _, _, label in edges:
        line = "  %-18s        " % label
        for cap in caps:
            s = table[label][cap][0]
            r = 100.0 * s["skipped"] / s["opened"] if s["opened"] else 0.0
            line += " %11d/%-4d" % (s["skipped"], s["opened"])
        print(line)

    print("\n  cap の符号（無制限を基準にした純益の差）")
    counts = {cap: [0, 0] for cap in caps if cap is not None}
    for _, _, label in edges:
        base = table[label][base_cap][0]["net"]
        line = "  %-18s        " % label
        for cap in caps:
            if cap is None:
                line += " %15s" % "—"
                continue
            d = table[label][cap][0]["net"] - base
            counts[cap][0 if d > 0 else 1] += 1
            line += " %+15s" % format(round(d), ",")
        print(line)
    print()
    for cap in caps:
        if cap is None:
            continue
        w, l = counts[cap]
        print("  cap%.0f%%: 勝ち %d期間 / 負け %d期間" % (cap * 100, w, l))

    # 【目標判定】「月利6%」に対する現在地は、1本の長期経路の幾何平均ではなく
    # 「新規50万円口座がその期間に得た月利」の分布で見るほうが実務に近い。
    print("\n  月利の分布（各窓を新規50万円口座として計算・%/月）")
    print("  %8s %8s %8s %8s %8s %10s %10s"
          % ("cap", "中央値", "平均", "最悪", "最良", "6%以上", "マイナス"))
    for cap in caps:
        xs = sorted(table[label][cap][1] for _, _, label in edges)
        n = len(xs)
        med = xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2
        label_cap = "無制限" if cap is None else "%.0f%%" % (cap * 100)
        print("  %8s %7.2f%% %7.2f%% %7.2f%% %7.2f%% %6d/%-3d %6d/%-3d"
              % (label_cap, med, sum(xs) / n, xs[0], xs[-1],
                 sum(1 for x in xs if x >= 6.0), n,
                 sum(1 for x in xs if x < 0.0), n))

    print("\n注: 部分期間は同じ1本の履歴からの切り出しであり独立標本ではない。")
    print("    符号の数え上げは目安であって検定ではない。採用の判断は MT5 で行う。")


if __name__ == "__main__":
    main()

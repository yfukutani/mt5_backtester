"""基準dealログから建玉単位の成績を組み立て、SL決済の実態を定量化する。

含み益の経路（MFE）はdealログには無いため、ここで分かるのは
「初期リスクRに対して最終的にどこで死んだか」までである。
MFEは別途 analyze_mfe.py で価格データを当てて算出する。
"""
import csv
import sys
from collections import defaultdict

MAGIC_NAME = {20260640: "PB GOLD", 20261002: "SCA GOLD"}


def load(path):
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    ins, outs = {}, defaultdict(list)
    for r in rows:
        pid = int(r["position_id"])
        rec = {
            "time": int(r["time"]),
            "profit": float(r["profit"]),
            "profit_jpy": float(r["profit_jpy"]),
            "magic": int(r["magic"]),
            "type": int(r["type"]),
            "volume": float(r["volume"]),
            "price": float(r["price"]),
            "sl": float(r["sl"]),
        }
        if r["entry"] == "0":
            ins[pid] = rec
        else:
            outs[pid].append(rec)

    trades = []
    for pid, i in ins.items():
        o = outs.get(pid)
        if not o:
            continue
        exit_price = sum(x["price"] * x["volume"] for x in o) / sum(x["volume"] for x in o)
        profit_jpy = sum(x["profit_jpy"] for x in o)
        is_buy = i["type"] == 0
        risk = abs(i["price"] - i["sl"])
        if risk <= 0:
            continue
        realized = (exit_price - i["price"]) if is_buy else (i["price"] - exit_price)
        trades.append({
            "pid": pid,
            "magic": i["magic"],
            "name": MAGIC_NAME.get(i["magic"], str(i["magic"])),
            "is_buy": is_buy,
            "entry_time": i["time"],
            "exit_time": max(x["time"] for x in o),
            "entry": i["price"],
            "sl": i["sl"],
            "exit": exit_price,
            "risk": risk,
            "r_mult": realized / risk,
            "profit_jpy": profit_jpy,
            "hold_h": (max(x["time"] for x in o) - i["time"]) / 3600.0,
        })
    return trades


def report(trades, label):
    print(f"\n{'='*70}\n{label}   建玉数 {len(trades)}\n{'='*70}")
    for name in sorted({t["name"] for t in trades}):
        g = [t for t in trades if t["name"] == name]
        wins = [t for t in g if t["profit_jpy"] > 0]
        losses = [t for t in g if t["profit_jpy"] <= 0]
        # 当初SLで死んだ＝実現Rが -0.95R 以下（スリッページ込み）
        at_sl = [t for t in losses if t["r_mult"] <= -0.95]
        print(f"\n--- {name} ---")
        print(f"  取引 {len(g)}  勝ち {len(wins)}  負け {len(losses)}  "
              f"純益 {sum(t['profit_jpy'] for t in g):>12,.0f} 円")
        print(f"  当初SL到達で決済: {len(at_sl)} 件 "
              f"({100*len(at_sl)/max(1,len(g)):.1f}%)  "
              f"損失合計 {sum(t['profit_jpy'] for t in at_sl):>12,.0f} 円")
        if losses:
            print(f"  負け取引の実現R分布: "
                  f"min {min(t['r_mult'] for t in losses):.2f} / "
                  f"中央 {sorted(t['r_mult'] for t in losses)[len(losses)//2]:.2f} / "
                  f"max {max(t['r_mult'] for t in losses):.2f}")
        if wins:
            rs = sorted(t["r_mult"] for t in wins)
            print(f"  勝ち取引の実現R分布: "
                  f"min {rs[0]:.2f} / 中央 {rs[len(rs)//2]:.2f} / max {rs[-1]:.2f}")
            print(f"  勝ちの利益合計 {sum(t['profit_jpy'] for t in wins):>12,.0f} 円"
                  f"  / 上位5件が占める割合 "
                  f"{100*sum(sorted((t['profit_jpy'] for t in wins), reverse=True)[:5])/sum(t['profit_jpy'] for t in wins):.1f}%")
        hs = sorted(t["hold_h"] for t in g)
        print(f"  保有時間(h): 中央 {hs[len(hs)//2]:.1f} / 90%点 {hs[int(len(hs)*0.9)]:.1f} / max {hs[-1]:.1f}")
        print(f"  初期リスク幅(USD): 中央 {sorted(t['risk'] for t in g)[len(g)//2]:.2f}")


if __name__ == "__main__":
    for path, label in [(sys.argv[1], sys.argv[2])] if len(sys.argv) > 2 else []:
        report(load(path), label)

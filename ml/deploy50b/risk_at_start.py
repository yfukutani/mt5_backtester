"""「50万円で始めた直後」の危険度を実額で出す。

【なぜ必要か】MT5テスターの最大相対DD%は、利益が積み上がって膨らんだ残高に対する
比率である。10年で純利益が入金の7倍になるブックでは、後半のDDは%が小さく出る。
入金50万でこれから始める人にとっての危険度は、その%ではなく
「1取引でいくら失いうるか」「最悪の月にいくら減るか」を入金50万に対して見た値である。

倍率xNのときの損失はロットに比例するので、x1の実測値をN倍して示す。
"""
import csv
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

DEPOSIT = 500000
MAGIC = {20260640: "PB GOLD", 20261002: "SCA GOLD"}


def trades(path):
    ins, outs = {}, defaultdict(list)
    for r in csv.DictReader(open(path, encoding="utf-8")):
        m = int(r["magic"])
        if m not in MAGIC:
            continue
        pid = int(r["position_id"])
        if r["entry"] == "0":
            ins[pid] = r
        else:
            outs[pid].append(r)
    out = []
    for pid, i in ins.items():
        o = outs.get(pid)
        if not o:
            continue
        t = max(int(x["time"]) for x in o)
        out.append({
            "magic": int(i["magic"]),
            "name": MAGIC[int(i["magic"])],
            "t": datetime.fromtimestamp(t, timezone.utc),
            "profit": sum(float(x["profit_jpy"]) for x in o),
            "volume": float(i["volume"]),
        })
    return out


def main(path, label, mults):
    tr = trades(path)
    tr.sort(key=lambda x: x["t"])
    worst = sorted(tr, key=lambda x: x["profit"])[:5]

    months = defaultdict(float)
    for t in tr:
        months[(t["t"].year, t["t"].month)] += t["profit"]
    worst_m = sorted(months.items(), key=lambda kv: kv[1])[:3]

    # 連続する下落の最大（取引順の累積損益の高値からの落ち込み）
    peak = cum = 0.0
    max_dd = 0.0
    for t in tr:
        cum += t["profit"]
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)

    print(f"\n{'='*74}\n{label}   GOLD 2枠 x1 の実測（{len(tr)}取引）\n{'='*74}")
    print("最悪の単一取引 上位5件:")
    for t in worst:
        print(f"  {t['t']:%Y-%m-%d}  {t['name']:<9} {t['volume']:.2f}lot  {t['profit']:>10,.0f} 円")
    print("\n最悪の月 上位3件:")
    for (y, m), v in worst_m:
        print(f"  {y}-{m:02d}  {v:>10,.0f} 円")
    print(f"\n累積損益ベースの最大落ち込み: {max_dd:,.0f} 円")

    print(f"\n--- 倍率別に入金 {DEPOSIT:,} 円へ換算 ---")
    print(f"{'倍率':>5}{'最悪1取引':>14}{'対入金':>9}{'最悪の月':>14}{'対入金':>9}{'最大落ち込み':>14}{'対入金':>9}")
    w1 = worst[0]["profit"]
    wm = worst_m[0][1]
    for n in mults:
        print(f"x{n:<4}{w1*n:>14,.0f}{100*abs(w1*n)/DEPOSIT:>8.1f}%"
              f"{wm*n:>14,.0f}{100*abs(wm*n)/DEPOSIT:>8.1f}%"
              f"{-max_dd*n:>14,.0f}{100*max_dd*n/DEPOSIT:>8.1f}%")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], [1, 3, 5, 6, 8, 10, 12, 15])

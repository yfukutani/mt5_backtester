"""改善が少数の取引に依存していないかを検査する。

大きな改善率が「たまたま数件の大勝ち」で作られている場合、それは採用根拠にならない。
基準と候補の SCA GOLD 建玉を突き合わせ、
  - 損益が変わった建玉が何件か
  - 改善額の上位N件が全体の何%を占めるか
  - 悪化した建玉はどれだけあるか
を出す。
"""
import csv
import sys
from collections import defaultdict
from pathlib import Path

SCA_GOLD = 20261002


def positions(path, magic=SCA_GOLD):
    ins, outs = {}, defaultdict(list)
    for r in csv.DictReader(open(path, encoding="utf-8")):
        if int(r["magic"]) != magic:
            continue
        pid = int(r["position_id"])
        if r["entry"] == "0":
            ins[pid] = r
        else:
            outs[pid].append(r)
    out = {}
    for pid, i in ins.items():
        o = outs.get(pid)
        if not o:
            continue
        out[pid] = {
            "entry_t": int(i["time"]),
            "exit_t": max(int(x["time"]) for x in o),
            "profit": sum(float(x["profit_jpy"]) for x in o),
        }
    return out


def main(base_path, cand_path, label):
    b, c = positions(base_path), positions(cand_path)
    common = sorted(set(b) & set(c))
    print(f"\n{'='*72}\n{label}\n{'='*72}")
    print(f"SCA GOLD 建玉  基準 {len(b)} / 候補 {len(c)} / 共通 {len(common)}")
    print(f"  基準のみ {len(set(b)-set(c))} / 候補のみ {len(set(c)-set(b))}")

    deltas = [(pid, c[pid]["profit"] - b[pid]["profit"]) for pid in common]
    changed = [d for d in deltas if abs(d[1]) > 0.5]
    gain = [d for d in deltas if d[1] > 0.5]
    loss = [d for d in deltas if d[1] < -0.5]
    total = sum(d[1] for d in deltas)
    print(f"\n損益が変わった建玉: {len(changed)} / {len(common)} "
          f"({100*len(changed)/max(1,len(common)):.1f}%)")
    print(f"  改善 {len(gain)} 件 計 {sum(d[1] for d in gain):>+12,.0f} 円")
    print(f"  悪化 {len(loss)} 件 計 {sum(d[1] for d in loss):>+12,.0f} 円")
    print(f"  正味 {total:>+12,.0f} 円")

    gain.sort(key=lambda d: -d[1])
    if gain and total > 0:
        for n in (1, 3, 5, 10):
            if len(gain) >= n:
                top = sum(d[1] for d in gain[:n])
                print(f"  改善額の上位{n:>2}件が正味に占める割合: {100*top/total:>5.1f}%")

    # 保有時間の変化
    hold_b = sum((b[p]["exit_t"] - b[p]["entry_t"]) for p in common) / max(1, len(common)) / 3600
    hold_c = sum((c[p]["exit_t"] - c[p]["entry_t"]) for p in common) / max(1, len(common)) / 3600
    print(f"\n平均保有時間: 基準 {hold_b:.2f}h → 候補 {hold_c:.2f}h ({hold_c-hold_b:+.2f}h)")
    longer = sum(1 for p in common if c[p]["exit_t"] > b[p]["exit_t"])
    print(f"  決済が後ろにずれた建玉: {longer} / {len(common)}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])

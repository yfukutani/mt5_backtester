"""SCA GOLD の改善が年次で一貫しているかを検査する。

TP側の施策が触れるのは「TPに到達する取引」だけで、ISでは242件中15件しかない。
少数に効く施策は、たまたま当たった年が1つあるだけで全体の数字が動く。
年ごとに符号が揃っているか（＝面か点か）を見る。
"""
import csv
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

SCA_GOLD = 20261002


def positions(path):
    ins, outs = {}, defaultdict(list)
    for r in csv.DictReader(open(path, encoding="utf-8")):
        if int(r["magic"]) != SCA_GOLD:
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
            "year": datetime.fromtimestamp(int(i["time"]), timezone.utc).year,
            "profit": sum(float(x["profit_jpy"]) for x in o),
        }
    return out


def main(base_path, cand_path, label):
    b, c = positions(base_path), positions(cand_path)
    common = sorted(set(b) & set(c))
    years = defaultdict(lambda: [0.0, 0.0, 0, 0])   # base, cand, n, changed
    for pid in common:
        y = b[pid]["year"]
        years[y][0] += b[pid]["profit"]
        years[y][1] += c[pid]["profit"]
        years[y][2] += 1
        if abs(c[pid]["profit"] - b[pid]["profit"]) > 0.5:
            years[y][3] += 1

    print(f"\n{'='*76}\n{label}\n{'='*76}")
    print(f"{'年':<6}{'取引':>6}{'変化':>6}{'基準':>12}{'候補':>12}{'差':>12}{'差%':>9}")
    pos = neg = 0
    for y in sorted(years):
        bb, cc, n, ch = years[y]
        d = cc - bb
        pct = (100 * d / abs(bb)) if bb else 0.0
        if ch:
            if d > 0:
                pos += 1
            elif d < 0:
                neg += 1
        print(f"{y:<6}{n:>6}{ch:>6}{bb:>12,.0f}{cc:>12,.0f}{d:>+12,.0f}{pct:>+8.1f}%")
    tb = sum(v[0] for v in years.values())
    tc = sum(v[1] for v in years.values())
    print(f"{'合計':<6}{sum(v[2] for v in years.values()):>6}{sum(v[3] for v in years.values()):>6}"
          f"{tb:>12,.0f}{tc:>12,.0f}{tc-tb:>+12,.0f}{100*(tc-tb)/abs(tb):>+8.1f}%")
    print()
    print(f"効果が出た年のうち  改善 {pos} 年 / 悪化 {neg} 年")
    if pos + neg:
        print(f"→ {'年をまたいで一貫' if neg == 0 else '年によって符号が反転（少数年に依存の疑い）'}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])

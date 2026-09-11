"""14枠の全部分集合（16,384通り）を総当たりし、2倍到達が最速の組み合わせを探す。

【なぜ「速度」で探すのか】V007 で、到達期間の下限が
    最短取引数 = 2·ln(2)/(m/s)²      （ケリー基準で運用したとき）
で決まることが分かった。月あたりの到達回数に直すと

    速度 [倍化/月] = (m/s)² × 月あたり取引数 / (2·ln2)

**シャープが高くても取引機会が少なければ遅い。** 逆に取引が多くてもシャープが
低ければ遅い。**この積を最大化する枠の組み合わせ**を探すのが正しい問い。

【計算量】部分集合ごとに取引列をマージし直すと重いが、枠の取引は互いに素なので
  n = Σn_i,  Σx = Σ(Σx)_i,  Σx² = Σ(Σx²)_i
から平均と分散が O(1) で出せる。16,384通りを総当たりできる。

【注意】この最適化は「どの枠を使うか」を過去データで選ぶ行為そのものであり、
**選択による過学習が入る**。IS で選んだ組み合わせが OOS で通用するかを
必ず突き合わせること。本スクリプトは3窓すべてで独立に最適化し、
「窓をまたいで同じ組み合わせが選ばれるか」を見る。
"""
from __future__ import annotations

import csv
import math
from collections import defaultdict
from itertools import combinations
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FX = REPO / "ml" / "fxmult1"
GOLD = REPO / "ml" / "goldcomp1"
MONTHS = {"IS": 60.0, "OOS": 55.0, "FULL": 115.0}

NAMES = {
    20260622: "PB_UJ", 20260627: "PB_GJ", 20260610: "RSI_UJ",
    20260605: "RSI_EU", 20260774: "RSI_GU", 20260629: "PAIR",
    20260650: "CARRY", 20261000: "SCA_UJ", 20261001: "SCA_GJ",
    20260640: "PB_GOLD", 20261002: "SCA_G1", 20261003: "SCA_G2",
    20260710: "ETH", 20260720: "FUND", 20260724: "BFX",
}


def by_sleeve(path):
    out = defaultdict(list)
    for r in csv.DictReader(open(path, encoding="utf-8")):
        p = float(r["profit"])
        m = int(r["magic"])
        if p == 0.0 or m == 0:      # magic=0 は期間終了時の強制決済
            continue
        out[m].append(p)
    return out


def load():
    src = defaultdict(dict)
    runs = {}
    for f in ("results.csv", "results_grid.csv"):
        p = FX / f
        if not p.exists():
            continue
        for r in csv.DictReader(open(p, encoding="utf-8")):
            if r["status"] == "OK" and int(r["mult"]) == 1 and r.get("deals"):
                runs[r["window"]] = FX / "run_deals" / r["deals"]
    for w, p in runs.items():
        for m, t in by_sleeve(p).items():
            src[w][m] = t
    for r in csv.DictReader(open(GOLD / "results.csv", encoding="utf-8")):
        if r["status"] == "OK" and r["proposal_id"] == "G001" and r.get("deals"):
            for m, t in by_sleeve(GOLD / "run_deals" / r["deals"]).items():
                src[r["window"]][m] = t
    return src


def agg(t):
    n = len(t)
    return n, sum(t), sum(x * x for x in t)


def speed_of(n, s1, s2, months):
    """倍化/月。n<30 は統計として扱えないので除外。"""
    if n < 30:
        return None
    m = s1 / n
    var = (s2 - n * m * m) / (n - 1)
    if var <= 0 or m <= 0:
        return None
    sd = math.sqrt(var)
    sh = m / sd
    rate = n / months
    return (sh ** 2) * rate / (2 * math.log(2)), sh, rate, n


def search(win, sleeves):
    stats = {m: agg(t) for m, t in sleeves.items()}
    keys = sorted(stats)
    best = []
    for r in range(1, len(keys) + 1):
        for combo in combinations(keys, r):
            n = s1 = s2 = 0
            for m in combo:
                a, b, c = stats[m]
                n += a; s1 += b; s2 += c
            v = speed_of(n, s1, s2, MONTHS[win])
            if v:
                best.append((v[0], combo, v[1], v[2], v[3]))
    best.sort(reverse=True)
    return best


def main():
    src = load()
    results = {}
    for win in ("IS", "OOS", "FULL"):
        if win not in src or not src[win]:
            print(f"\n=== {win}窓: データなし ===")
            continue
        sl = src[win]
        best = search(win, sl)
        results[win] = best
        full = tuple(sorted(sl))
        fv = next((b for b in best if b[1] == full), None)
        print(f"\n{'='*96}")
        print(f"{win}窓 — 2倍到達が最速の組み合わせ（全{2**len(sl)-1:,}通りを総当たり）")
        print(f"{'='*96}")
        print(f"  {'順':>3}{'倍化/月':>9}{'到達月数':>10}{'m/s':>9}"
              f"{'月取引':>8}{'取引数':>8}  枠")
        for i, (sp, combo, sh, rate, n) in enumerate(best[:8], 1):
            names = "+".join(NAMES.get(m, str(m)) for m in combo)
            print(f"  {i:>3}{sp:>9.3f}{1/sp:>10.1f}{sh:>9.4f}"
                  f"{rate:>8.1f}{n:>8}  {names[:58]}")
        if fv:
            sp, combo, sh, rate, n = fv
            print(f"  {'全枠':>3}{sp:>9.3f}{1/sp:>10.1f}{sh:>9.4f}"
                  f"{rate:>8.1f}{n:>8}  （全{len(combo)}枠）")

    # 窓をまたいだ一致を見る＝選択の過学習の度合い
    if len(results) >= 2:
        print(f"\n{'='*96}\n窓をまたいで同じ組み合わせが選ばれるか（選択の過学習の検査）\n{'='*96}")
        tops = {w: set(b[1]) for w, b in
                ((w, r[0]) for w, r in results.items() if r)}
        for w, s in tops.items():
            print(f"  {w:>5} 最速: " + "+".join(NAMES.get(m, str(m)) for m in sorted(s)))
        wins = list(tops)
        for a, b in combinations(wins, 2):
            inter = tops[a] & tops[b]
            union = tops[a] | tops[b]
            print(f"  {a}∩{b}: {len(inter)}/{len(union)}枠 一致 — "
                  + ("+".join(NAMES.get(m, str(m)) for m in sorted(inter)) or "なし"))

        # ISで選んだ組み合わせをOOSで評価する（正しい検証の向き）
        if "IS" in results and "OOS" in src:
            print(f"\n  ISで選んだ最速の組み合わせを OOS で評価:")
            for rank in range(3):
                combo = results["IS"][rank][1]
                sl = src["OOS"]
                if not all(m in sl for m in combo):
                    print(f"    {rank+1}位: OOSに存在しない枠を含む（GOLD側のIS未測定）")
                    continue
                n = s1 = s2 = 0
                for m in combo:
                    a, b2, c = agg(sl[m]); n += a; s1 += b2; s2 += c
                v = speed_of(n, s1, s2, MONTHS["OOS"])
                names = "+".join(NAMES.get(m, str(m)) for m in combo)
                if v:
                    print(f"    {rank+1}位 {names[:44]}: "
                          f"IS {results['IS'][rank][0]:.3f} → OOS {v[0]:.3f} 倍化/月"
                          f"（{1/v[0]:.1f}か月）")
                else:
                    print(f"    {rank+1}位 {names[:44]}: OOSでは評価不能")


if __name__ == "__main__":
    main()

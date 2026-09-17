"""枠別のリスク特性を deal ログから出す（段階2の簡易検証・採用の根拠にはしない）。

【何に答えるか】100案のうち、サイジングを枠ごとに変える案の下ごしらえ。

- Claude A3「枠ごとに riskPct を変える（リスクパリティ）」
- Claude D8「枠別のDD寄与を測り、DDの主因枠だけ倍率を下げる」
- Claude D9「相関の高い枠を同時に持たない（USDJPY系が3枠ある）」
- Codex #7「相関込みの静的な枠配分」

【何を出すか】基準run（S001＝mask=0・RefCap=250,000・倍率1）の deal ログから、
枠ごとに 純益・取引数・1取引の平均と標準偏差・単独の最大DD（ピーク比）・
月次損益の相関行列を出す。

【限界・必ず読むこと】
- **決済損益だけ**で作るので建玉中の含み損を含まない。DDは下限値。
- 単独DDの合計はブック全体のDDと一致しない（分散効果があるため）。
  「DDの主因枠」は**単独DD**と**ブックDD日への寄与**の2通りで見る必要があり、
  ここで出すのは前者だけである。
- **これは段階2（ふるい分け）であって、採用の根拠にはならない。**
  採用の判断は必ずMT5バックテストで行う（CLAUDE.md）。
"""
from __future__ import annotations

import csv
import math
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEPOSIT = 500000

SLEEVES = {
    20260622: "PB USDJPY", 20260627: "PB GBPJPY", 20260610: "RSI USDJPY",
    20260605: "RSI EURUSD", 20260774: "RSI GBPUSD", 20260629: "PairTrade",
    20260650: "Carry AUDJPY", 20261000: "SCA USDJPY", 20261001: "SCA GBPJPY",
}
# 同じ通貨に賭けている枠を見分けるため
EXPOSURE = {
    "PB USDJPY": "USDJPY", "RSI USDJPY": "USDJPY", "SCA USDJPY": "USDJPY",
    "PB GBPJPY": "GBPJPY", "SCA GBPJPY": "GBPJPY",
    "RSI EURUSD": "EURUSD", "RSI GBPUSD": "GBPUSD",
    "PairTrade": "EURUSD/GBPUSD", "Carry AUDJPY": "AUDJPY",
}


def latest_deals(pattern):
    hits = sorted((ROOT / "run_deals").glob(pattern))
    if not hits:
        raise SystemExit(f"deal ログが見つかりません: {pattern}")
    return hits[-1]


def load(path):
    per = defaultdict(list)
    for r in csv.DictReader(open(path, encoding="utf-8")):
        p = float(r["profit"])
        if p == 0.0:
            continue          # IN約定は損益0
        name = SLEEVES.get(int(r["magic"]))
        if name is None:
            continue          # テスト終了時の強制決済（magic=0）は枠に帰属できない
        per[name].append((int(r["time"]), p))
    for v in per.values():
        v.sort()
    return per


def max_dd(series):
    """単独で走らせたときのピーク比最大DD（入金を元手とする）。"""
    eq = peak = DEPOSIT
    worst = 0.0
    for _, p in series:
        eq += p
        peak = max(peak, eq)
        worst = max(worst, (peak - eq) / peak)
    return worst * 100


def monthly(series):
    m = defaultdict(float)
    for t, p in series:
        import datetime as _dt
        d = _dt.datetime.fromtimestamp(t, _dt.timezone.utc)
        m[(d.year, d.month)] += p
    return m


def corr(a, b):
    keys = sorted(set(a) | set(b))
    xs = [a.get(k, 0.0) for k in keys]
    ys = [b.get(k, 0.0) for k in keys]
    n = len(keys)
    if n < 2:
        return float("nan")
    mx, my = sum(xs) / n, sum(ys) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return float("nan")
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def main():
    path = latest_deals("fs_full_S001_*_deals.csv")
    print(f"基準run: {path.name}")
    print("S001 = マスク0（risk%化なし）/ RefCap=250,000 / 倍率1 / 入金 500,000円")
    print("FULL窓 2016.11.09〜2026.06.20（115か月）。決済損益のみ＝含み損を含まない。\n")

    per = load(path)
    rows = []
    for name, series in per.items():
        ps = [p for _, p in series]
        n = len(ps)
        mean = sum(ps) / n
        sd = math.sqrt(sum((p - mean) ** 2 for p in ps) / (n - 1)) if n > 1 else 0.0
        net = sum(ps)
        dd = max_dd(series)
        rows.append({
            "name": name, "net": net, "n": n, "mean": mean, "sd": sd,
            "dd": dd, "rdd": net / (dd / 100 * DEPOSIT) if dd > 0 else float("inf"),
            "monthly": monthly(series),
        })
    rows.sort(key=lambda r: -r["net"])

    total = sum(r["net"] for r in rows)
    print(f"{'枠':<14}{'エクスポージャ':<14}{'純益':>10}{'比率':>7}{'取引':>6}"
          f"{'1取引平均':>10}{'1取引SD':>9}{'単独DD':>8}{'純益/DD額':>10}")
    for r in rows:
        print(f"{r['name']:<14}{EXPOSURE[r['name']]:<14}{r['net']:>10,.0f}"
              f"{100 * r['net'] / total:>6.1f}%{r['n']:>6}{r['mean']:>10,.0f}"
              f"{r['sd']:>9,.0f}{r['dd']:>7.1f}%{r['rdd']:>10.2f}")
    print(f"{'合計':<28}{total:>10,.0f}{100.0:>6.1f}%"
          f"{sum(r['n'] for r in rows):>6}")

    print("\n【A3 枠ごとに riskPct を変えるなら、何を基準にするか】")
    print("1取引SDそのものは基準にならない——SDは現在のロットの大きさを映しているだけで、")
    print("risk%化すれば定義上どの枠も同じリスクに揃う（uniform risk% がすでにリスクパリティ）。")
    print("A3が問うのは『パリティからどちらへ傾けるか』なので、**規模に依らない質**で見る。\n")
    print(f"{'枠':<14}{'1取引S':>9}{'年間取引':>9}{'年率換算S':>10}"
          f"{'純益/DD額':>10}  パリティからの傾け方")
    yrs = 115.0 / 12.0
    prof = []
    for r in rows:
        s1 = r["mean"] / r["sd"] if r["sd"] > 0 else 0.0
        per_year = r["n"] / yrs
        sann = s1 * math.sqrt(per_year)
        prof.append((sann, r, s1, per_year))
    for sann, r, s1, per_year in sorted(prof, key=lambda x: -x[0]):
        tilt = "厚く" if sann >= 0.5 else ("薄く" if sann < 0.3 else "中立")
        print(f"{r['name']:<14}{s1:>9.3f}{per_year:>9.1f}{sann:>10.2f}"
              f"{r['rdd']:>10.2f}  {tilt}")
    print("\n  年率換算S = 1取引S × √(年間取引数)。枠どうしがほぼ無相関（下の【D9】）なので、")
    print("  同じDD予算で最大の利益を取る配分は、おおむね**年率換算Sに比例**する。")

    print("\n【D9 枠の相関】月次損益のピアソン相関（|r|>=0.3 のみ表示）")
    hits = []
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            c = corr(a["monthly"], b["monthly"])
            if not math.isnan(c) and abs(c) >= 0.3:
                hits.append((c, a["name"], b["name"]))
    if hits:
        for c, x, y in sorted(hits, key=lambda h: -abs(h[0])):
            same = "  ← 同一通貨" if EXPOSURE[x] == EXPOSURE[y] else ""
            print(f"  {c:+.3f}  {x} × {y}{same}")
    else:
        print("  |r|>=0.3 の組み合わせなし＝枠どうしはほぼ無相関")

    print("\n注: これは段階2の簡易検証であり、採用の根拠にはしない。")
    print("    単独DDの合計はブック全体のDDと一致しない（分散効果があるため）。")
    print("    DDは決済損益ベースの下限値で、建玉中の含み損を含まない。")


if __name__ == "__main__":
    main()

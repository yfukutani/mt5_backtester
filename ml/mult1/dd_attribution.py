"""最悪ドローダウンを作っているのがどの枠かを分解する。

【なぜ見るか】ml/mult1 で、踏める倍率を決めているのは「入金に対する円建ての
最悪落ち込み」だと確定した。利益を足すより落ち込みを削るほうが倍率に直結する
（DDを2割削れば倍率を2割上げられ、利益はそのぶん丸ごと増える）。

そこで、最悪落ち込みの期間に**どの枠がいくら損しているか**を出す。特定の枠に
偏っていればそこを削るのが最短で、散らばっていればDD削減の余地は小さい。

枠別に見るため magic 列が要る。deal ログは全枠ぶんを持っている。
"""
from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEAL_DIR = ROOT / "run_deals"
DEPOSIT = 500000

NAMES = {
    20260640: "PB GOLD", 20261002: "SCA GOLD第1", 20261003: "SCA GOLD第2",
    20261004: "SCA GOLD第3", 20260710: "ETH キャリー",
    20260720: "BTC funding逆張り", 20260724: "BfxRev リバウンド",
}


def deals(path):
    out = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        p = float(r["profit"])
        if p == 0.0:
            continue          # IN約定は損益0
        out.append((datetime.fromtimestamp(int(r["time"]), timezone.utc),
                    int(r["magic"]), p))
    out.sort()
    return out


def worst_window(rows):
    """最大落ち込みの開始（ピーク）と底の時刻を返す。"""
    peak = cum = 0.0
    peak_at = rows[0][0]
    worst = 0.0
    span = None
    for t, _, p in rows:
        cum += p
        if cum > peak:
            peak, peak_at = cum, t
        if peak - cum > worst:
            worst, span = peak - cum, (peak_at, t)
    return worst, span


def main():
    import sys
    label = sys.argv[1] if len(sys.argv) > 1 else "SCA2ONLY"
    win = sys.argv[2] if len(sys.argv) > 2 else "FULL"

    runs = {}
    for f in ("results.csv", "results_sca2only.csv"):
        p = ROOT / f
        if not p.exists():
            continue
        for r in csv.DictReader(open(p, encoding="utf-8")):
            if r["status"] == "OK" and int(r["mult"]) == 1 and r["deals"]:
                runs[(r["label"], r["window"])] = r["deals"]

    key = (label, win)
    if key not in runs:
        print(f"該当なし: {key} / 持っているのは {sorted(runs)}")
        return
    rows = deals(DEAL_DIR / runs[key])
    worst, span = worst_window(rows)
    a, b = span
    print(f"{label} / {win}窓 / x1・入金{DEPOSIT:,}円")
    print(f"最大落ち込み {worst:,.0f}円（入金の {100*worst/DEPOSIT:.1f}%）")
    print(f"期間 {a:%Y-%m-%d} 〜 {b:%Y-%m-%d}（{(b-a).days}日）\n")

    # 落ち込み期間中の枠別損益。ここが偏っていれば削る先が決まる。
    seg = defaultdict(lambda: [0.0, 0])
    for t, m, p in rows:
        if a < t <= b:
            seg[m][0] += p
            seg[m][1] += 1
    print(f"{'枠':<20}{'落ち込み期間の損益':>18}{'決済数':>8}{'寄与率':>8}")
    total_loss = sum(v[0] for v in seg.values() if v[0] < 0)
    for m, (net, n) in sorted(seg.items(), key=lambda kv: kv[1][0]):
        share = 100 * net / total_loss if net < 0 and total_loss else 0.0
        print(f"{NAMES.get(m, str(m)):<20}{net:>18,.0f}{n:>8}"
              f"{(f'{share:.0f}%' if net < 0 else '—'):>8}")

    # 通期の枠別も併記。DDへの寄与と利益への寄与は別物なので両方見る。
    tot = defaultdict(lambda: [0.0, 0])
    for _, m, p in rows:
        tot[m][0] += p
        tot[m][1] += 1
    print(f"\n{'枠':<20}{'通期の純益':>14}{'決済数':>8}")
    for m, (net, n) in sorted(tot.items(), key=lambda kv: -kv[1][0]):
        print(f"{NAMES.get(m, str(m)):<20}{net:>14,.0f}{n:>8}")

    # 各枠を1つ抜いたら最悪落ち込みがどうなるか（他枠は不変なので引き算でよい）
    print(f"\n{'抜く枠':<20}{'残りの最悪落ち込み':>18}{'変化':>10}{'失う純益':>12}")
    for m in sorted(tot, key=lambda k: -tot[k][0]):
        rest = [(t, mm, p) for t, mm, p in rows if mm != m]
        if not rest:
            continue
        w2, _ = worst_window(rest)
        print(f"{NAMES.get(m, str(m)):<20}{w2:>18,.0f}"
              f"{100*(w2/worst-1):>9.1f}%{tot[m][0]:>12,.0f}")

    # 【本題】倍率はDD予算で決まるので、月利は「純益 ÷ 円建てDD」に比例する。
    # 利益が小さくてもDDへの寄与がそれ以上に大きい枠は、抜いたほうが月利が上がる。
    # 全部分集合を総当たりして、この比が最大になる組み合わせを探す。
    from itertools import combinations
    magics = sorted(tot, key=lambda k: -tot[k][0])
    base_ratio = sum(v[0] for v in tot.values()) / worst
    print(f"\n【純益÷最悪落ち込み】倍率はDD予算で決まるので、月利はこの比に比例する")
    print(f"現行6枠: 純益 {sum(v[0] for v in tot.values()):,.0f} / DD {worst:,.0f} "
          f"= {base_ratio:.2f}")
    cands = []
    for k in range(0, len(magics)):
        for drop in combinations(magics, k):
            rest = [(t, m, p) for t, m, p in rows if m not in drop]
            if not rest:
                continue
            w2, _ = worst_window(rest)
            p2 = sum(p for _, _, p in rest)
            if w2 <= 0 or p2 <= 0:
                continue
            cands.append((p2 / w2, p2, w2, drop))
    cands.sort(reverse=True)
    print(f"\n  {'比':>7}{'対現行':>8}{'純益':>11}{'最悪落ち込み':>13}  抜く枠")
    for ratio, p2, w2, drop in cands[:10]:
        names = "、".join(NAMES.get(m, str(m)) for m in drop) or "（現行のまま）"
        print(f"  {ratio:>7.2f}{100*(ratio/base_ratio-1):>+7.1f}%"
              f"{p2:>11,.0f}{w2:>13,.0f}  {names}")


if __name__ == "__main__":
    main()

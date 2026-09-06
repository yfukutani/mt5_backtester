"""x1 の deal ログから倍率曲線を出し、DD予算の中で踏める倍率を両構成で比べる。

【見方】MT5の最大相対DD%は「その時点の残高」に対する比率なので、固定ロットで
残高が増えるブックでは後半の落ち込みほど%が小さく出る。新規に入金50万で始める人の
危険度は「入金額に対する円建ての落ち込み」で見る（docs/deploy50_recheck_20260905.md）。

【DD予算】入金の30%（＝150,000円）を上限とする。これは運用方針として置いた値であり
理論的な裏付けは無い。25%と35%も併記して感度を見る。

【線形性】全枠が固定ロットなので円建て損益は倍率に正比例する。x4/x8 の実測と
x1×n の予測を突き合わせて、証拠金の影響で線形性が崩れていないかを確認する。
"""
from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEAL_DIR = ROOT / "run_deals"
DEPOSIT = 500000
BUDGETS = (0.25, 0.30, 0.35)
MULTS = list(range(1, 13))


def closed_trades(path):
    """決済損益を時刻順に。IN約定は損益0で記録されるので落とす。"""
    rows = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        p = float(r["profit"])          # profit_jpy はJPY建てでは使えない
        if p == 0.0:
            continue
        rows.append((datetime.fromtimestamp(int(r["time"]), timezone.utc), p))
    rows.sort()
    return rows


def curve(rows, n):
    """倍率 n のときの円建て最大落ち込みと最終純益。"""
    peak = cum = worst = 0.0
    worst_at = None
    for t, p in rows:
        cum += p * n
        peak = max(peak, cum)
        if peak - cum > worst:
            worst, worst_at = peak - cum, t
    return worst, cum, worst_at


CONFIGS = [("OFF", "現行（第2も第3もなし）"),
           ("SCA2ONLY", "第2セッションのみ"),
           ("ON", "第2＋第3セッション")]


def main():
    res = {}
    for f in ("results.csv", "results_sca2only.csv"):
        p = ROOT / f
        if not p.exists():
            continue
        for r in csv.DictReader(open(p, encoding="utf-8")):
            if r["status"] == "OK":
                res[r["run_id"]] = r
    x1 = {}
    for r in res.values():
        if int(r["mult"]) == 1 and r["deals"]:
            x1[(r["label"], r["window"])] = DEAL_DIR / r["deals"]

    months = {"IS": 60.0, "OOS": 55.0, "FULL": 115.0}

    for win in ("IS", "OOS", "FULL"):
        keys = [k for k, _ in CONFIGS if (k, win) in x1]
        if len(keys) < 2:
            continue
        print(f"\n{'='*92}")
        print(f"{win}窓  入金{DEPOSIT:,}円・非複利・XM本番構成（GOLD2枠＋暗号3枠）")
        print(f"{'='*92}")
        data = {k: closed_trades(x1[(k, win)]) for k in keys}
        for k, name in CONFIGS:
            if k not in data:
                continue
            w1, n1, _ = curve(data[k], 1)
            print(f"  {name:<22} 決済{len(data[k]):>5}件 / x1 純益 {n1:>9,.0f}円 / "
                  f"x1 最大落ち込み {w1:>8,.0f}円")

        head = "".join(f"{dict(CONFIGS)[k][:12]:^28}｜" for k in keys)
        print(f"\n  {'倍率':>4}｜" + head)
        print(f"  {'':>4}｜" + "".join(f"{'落ち込み':>10}{'入金比':>7}{'月利':>9}｜"
                                      for _ in keys))
        best = {}
        for n in MULTS:
            line = f"  x{n:<3}｜"
            for k in keys:
                w, net, _ = curve(data[k], n)
                ratio = w / DEPOSIT
                mo = 100 * net / DEPOSIT / months[win]
                for b in BUDGETS:
                    if ratio <= b and (k, b) not in best or \
                       (ratio <= b and best[(k, b)][0] < n):
                        best[(k, b)] = (n, ratio, mo)
                line += f"{w:>10,.0f}{100*ratio:>6.1f}%{mo:>8.2f}%｜"
            print(line)

        print(f"\n  DD予算ごとに踏める最大倍率と、そのときの月利")
        print(f"  {'予算':>6}｜" + "".join(f"{dict(CONFIGS)[k][:10]:^24}｜" for k in keys))
        for b in BUDGETS:
            line = f"  {100*b:>5.0f}%｜"
            for k in keys:
                v = best.get((k, b))
                line += (f"{'x'+str(v[0]):>7}{100*v[1]:>7.1f}%{v[2]:>8.2f}%｜"
                         if v else f"{'—':^24}｜")
            print(line)

        # 月利6%に必要な倍率と、そのとき入金の何%を落とすか
        print(f"\n  月利6%に必要な倍率と、そのときの入金比")
        for k in keys:
            w1, n1, _ = curve(data[k], 1)
            need = 0.06 * DEPOSIT * months[win] / n1
            print(f"    {dict(CONFIGS)[k]:<22} x{need:.2f} / "
                  f"落ち込み {w1*need:>9,.0f}円 = 入金の {100*w1*need/DEPOSIT:>5.1f}%")

    # 線形性の検証：実測 x4 / x8 と x1×n の予測がどれだけ合うか
    print(f"\n{'='*86}\n線形性の検証（IS窓・実測 vs x1のスケーリング）\n{'='*86}")
    print(f"  {'構成':>4}{'倍率':>5}{'実測純益':>12}{'予測純益':>12}{'ずれ':>8}"
          f"{'実測DD%':>9}{'予測DD%':>9}")
    for r in res.values():
        m = int(r["mult"])
        if m == 1 or r["window"] != "IS":
            continue
        base = x1.get((r["label"], "IS"))
        if not base:
            continue
        rows = closed_trades(base)
        w, net, _ = curve(rows, m)
        actual_net = float(r["net"])
        # MT5の相対DD%は残高基準なので、円建てDDから逆算した近似と突き合わせる
        print(f"  {r['label']:>4}{'x'+str(m):>5}{actual_net:>12,.0f}{net:>12,.0f}"
              f"{100*(actual_net/net-1):>7.1f}%{float(r['dd_pct']):>8.2f}%"
              f"{100*w/(DEPOSIT+net):>8.2f}%")


if __name__ == "__main__":
    main()

"""S01：**枠ごとの健康診断**（簡易検証・2026-09-17）。

【ユーザー指示（2026-09-17）】
> 次は**現状の戦略の精度向上**を目指してください。
> **一個一個の戦略に改良点がないか**CodexとClaudeで両方で案を出し合い、
> 有効な手立てを探してください。

【本スクリプトの位置づけ】
改良案を出す前に、**どの枠のどこが弱いのかを数字で押さえる**。
`CLAUDE.md` の段階2（簡易検証）。**採用の根拠にはしない。**

【測ること】
基準R001（本番現行設定）の決済ログから、枠ごとに——

| 指標 | なぜ見るか |
|---|---|
| 1取引あたり純益 | **小さいとコストに埋もれる**（RSI EURUSDは22円/取引） |
| 勝率・平均勝ち・平均負け | 分布の形。ペイオフ比 |
| 1取引シャープ・t値 | **統計的に有意か。件数が少ない枠は当てにならない** |
| 純益の集中度（上位5取引が占める割合） | **ランピーさ。Carryは13取引しかない** |
| 年別の符号 | **時期依存**。IS窓だけ効く枠を見抜く |
| 保有時間の中央値 | コスト（スワップ）の効き方 |

【限界】
- 決済ログの `profit` はスプレッド込み。**スワップ・手数料の扱いはログの定義に従う**
- IS窓の測定が無い（FULL/OOSのみ）ので、IS = FULL − OOS で近似する箇所がある
- 1取引シャープは取引単位。**建玉の重なりを無視している**
- **段階2の簡易検証である。採用の根拠にはしない**
"""
from __future__ import annotations

import csv
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
DEAL_DIR = ROOT / "run_deals"
RESULTS = ROOT / "results.csv"
BASE_ID = "R001"
MAGICS = {
    20260622: "PB USDJPY", 20260627: "PB GBPJPY", 20260610: "RSI USDJPY",
    20260605: "RSI EURUSD", 20260774: "RSI GBPUSD", 20260629: "PairTrade",
    20260650: "Carry AUDJPY", 20261000: "SCA USDJPY", 20261001: "SCA GBPJPY",
}
OOS_END = datetime(2021, 6, 21, tzinfo=timezone.utc)


def load_deals(path):
    """(t_in, t_out, profit, magic) を返す。"""
    rows = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        m = int(r["magic"])
        if m not in MAGICS:
            continue
        rows.append((int(r["time"]), int(r["entry"]), int(r["position_id"]),
                     float(r["profit"]), m))
    rows.sort()
    rec, opened = [], {}
    for t, entry, pid, profit, m in rows:
        if entry == 0:
            opened[pid] = t
        else:
            t_in = opened.pop(pid, None)
            if t_in is None or profit == 0.0:
                continue
            rec.append((t_in, t, profit, m))
    rec.sort()
    return rec


def stat(p):
    a = np.asarray(p, dtype=float)
    if len(a) < 3 or a.std(ddof=1) == 0:
        return 0.0, 0.0
    return (float(a.mean() / a.std(ddof=1)),
            float(a.mean() / (a.std(ddof=1) / math.sqrt(len(a)))))


def main():
    res = [r for r in csv.DictReader(open(RESULTS, encoding="utf-8"))
           if r["proposal_id"] == BASE_ID and r["window"] == "FULL"]
    if not res or not res[0].get("deals"):
        print("基準R001のFULL決済ログが見つからない")
        return
    path = DEAL_DIR / res[0]["deals"]
    if not path.exists():
        print(f"決済ログがない: {path}")
        return
    rec = load_deals(path)

    print("=" * 122)
    print("S01：枠ごとの健康診断（簡易検証・基準R001＝本番現行設定）")
    print("=" * 122)
    print("★ 改良案を出す前に、**どの枠のどこが弱いのか**を数字で押さえる。")
    print("  `CLAUDE.md` の段階2。**採用の根拠にはしない。**\n")
    print(f"  全期間 {len(rec)}建玉（2016-11〜2026-06）\n")

    by = defaultdict(list)
    for t_in, t_out, prof, m in rec:
        by[m].append((t_in, t_out, prof))

    # ---------- 1. 基本 ----------
    print("=" * 122)
    print("【1. 枠ごとの基本指標（全期間）】")
    print("=" * 122)
    print(f"{'枠':<14}{'件数':>6}{'純益':>11}{'1取引':>8}{'勝率':>7}"
          f"{'平均勝ち':>10}{'平均負け':>10}{'PF':>7}{'1取引S':>9}{'t値':>7}"
          f"{'保有h中央':>11}")
    rows = []
    for m, v in by.items():
        p = np.array([x[2] for x in v])
        hold = np.array([(x[1] - x[0]) / 3600.0 for x in v])
        win, los = p[p > 0], p[p < 0]
        pf = (win.sum() / abs(los.sum())) if len(los) and los.sum() != 0 else float("inf")
        s, t = stat(p)
        rows.append((p.sum(), m, len(v), p.sum(), p.mean(),
                     len(win) / len(p), win.mean() if len(win) else 0,
                     los.mean() if len(los) else 0, pf, s, t,
                     float(np.median(hold))))
    rows.sort(key=lambda r: -r[0])
    for _, m, n, tot, avg, wr, aw, al, pf, s, t, hm in rows:
        print(f"{MAGICS[m]:<14}{n:>6}{tot:>11,.0f}{avg:>8,.0f}{100*wr:>6.0f}%"
              f"{aw:>10,.0f}{al:>10,.0f}{pf:>7.2f}{s:>9.4f}{t:>7.2f}{hm:>11.1f}")

    # ---------- 2. 集中度 ----------
    print("\n" + "=" * 122)
    print("【2. 純益の集中度】**上位数取引が占める割合。高いほどランピー＝再現性が低い**")
    print("=" * 122)
    print(f"{'枠':<14}{'件数':>6}{'純益':>11}"
          f"{'上位1件':>10}{'上位5件':>10}{'上位10%':>10}{'最大の1件':>12}")
    for _, m, n, tot, *_ in rows:
        p = np.sort(np.array([x[2] for x in by[m]]))[::-1]
        if tot <= 0:
            print(f"{MAGICS[m]:<14}{n:>6}{tot:>11,.0f}{'—':>10}{'—':>10}"
                  f"{'—':>10}{p[0]:>12,.0f}")
            continue
        k10 = max(1, n // 10)
        print(f"{MAGICS[m]:<14}{n:>6}{tot:>11,.0f}"
              f"{100*p[0]/tot:>9.0f}%{100*p[:5].sum()/tot:>9.0f}%"
              f"{100*p[:k10].sum()/tot:>9.0f}%{p[0]:>12,.0f}")

    # ---------- 3. 年別の符号 ----------
    print("\n" + "=" * 122)
    print("【3. 年別の純益】**時期依存を見る。OOS=2016-2021前半 / IS=2021後半-2026**")
    print("=" * 122)
    years = list(range(2016, 2027))
    print(f"{'枠':<14}" + "".join(f"{y:>9}" for y in years))
    for _, m, *_ in rows:
        cells = ""
        for y in years:
            s = sum(x[2] for x in by[m]
                    if datetime.fromtimestamp(x[0], tz=timezone.utc).year == y)
            cells += f"{s:>9,.0f}" if s else f"{'—':>9}"
        print(f"{MAGICS[m]:<14}{cells}")

    # ---------- 4. OOS / IS 分割 ----------
    print("\n" + "=" * 122)
    print("【4. OOS窓 と IS窓の対比】**両方プラスが運用ルール**")
    print("=" * 122)
    print(f"{'枠':<14}{'OOS件数':>9}{'OOS純益':>11}{'OOS 1取引':>11}{'OOS t値':>9}"
          f"│{'IS件数':>8}{'IS純益':>11}{'IS 1取引':>11}{'IS t値':>8}{'判定':>6}")
    for _, m, *_ in rows:
        o = [x[2] for x in by[m]
             if datetime.fromtimestamp(x[0], tz=timezone.utc) < OOS_END]
        i = [x[2] for x in by[m]
             if datetime.fromtimestamp(x[0], tz=timezone.utc) >= OOS_END]
        so, to = stat(o)
        si, ti = stat(i)
        ok = (sum(o) > 0 and sum(i) > 0)
        print(f"{MAGICS[m]:<14}{len(o):>9}{sum(o):>11,.0f}"
              f"{(sum(o)/len(o) if o else 0):>11,.0f}{to:>9.2f}"
              f"│{len(i):>8}{sum(i):>11,.0f}"
              f"{(sum(i)/len(i) if i else 0):>11,.0f}{ti:>8.2f}"
              f"{'OK' if ok else 'NG':>6}")

    print("\n" + "=" * 122)
    print("【限界】")
    print("=" * 122)
    print("  ・決済ログの profit はスプレッド込み。スワップ・手数料はログの定義に従う")
    print("  ・1取引シャープは取引単位。**建玉の重なりを無視している**")
    print("  ・**段階2の簡易検証である。採用の根拠にはしない**")
    print("\n完了。")


if __name__ == "__main__":
    main()

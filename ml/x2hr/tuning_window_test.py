"""V051：GOLD枠の優位性は**相場環境**か**近年データへの調整（過学習）**か。

【V050で分離できなかった論点】
GOLD枠のシャープは 2016-2019年 0.0159（実質ゼロ）→ 2024-2026年 0.2241。
「2020年以降に優位性が現れた」ことは分かったが、原因が

1. **相場環境が戦略に合った**（金の大相場・ボラの上昇）
2. **近年データへの調整＝過学習**

のどちらかを分離できていなかった。

【分離の考え方：調整に使った期間の外を見る】
本プロジェクトのGOLD枠は **IS窓（2021.06.21〜2026.06.20）** を使って開発・調整された。
したがって次のように期間を切れば分離できる。

| 期間 | 調整に使ったか | 金の相場 |
|---|---|---|
| **A: 2016-01 〜 2019-12** | ❌ 使っていない | 静か |
| **B: 2020-01 〜 2021-06** | ❌ **使っていない** | **大相場（2020年に急騰）** |
| **C: 2021-06 〜 2026-06** | ✅ 調整に使った | 大相場 |

- **B ≈ C なら**：調整に使っていない期間でも同じ優位性が出ている
  → **相場環境が原因**（過学習ではない）
- **B ≪ C なら**：調整に使った期間でしか優位性が出ていない → **過学習**

**Bは「金の大相場でありながら調整に使っていない」という、分離に最適な期間である。**

【FX枠にも同じ検査をする】
V042でFX枠のシャープは 2022-2023の0.1442 → 2024-2026の0.0362 と急落した。
**両方ともIS窓（調整に使った期間）の中である。** 調整した期間の中で劣化しているなら、
それは過学習では説明しにくい。

【限界】
- 「IS窓で調整した」は本プロジェクトの記録に基づく理解であり、
  枠によっては別の期間で調整された可能性がある
- 期間Bは18ヶ月・GOLD枠で約120取引しかなく、シャープの推定誤差は大きい
"""
from __future__ import annotations

import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dynamic_k_lag as dkl
from sleeve_ablation import MAGIC_NAME
from sleeve_time_trend import SYMBOL_OF, CRYPTO

CONTRACT = 100.0
PERIODS = [
    ("A: 2016-01〜2019-12（未調整・静か）", datetime(2016, 1, 1), datetime(2020, 1, 1)),
    ("B: 2020-01〜2021-06（未調整・大相場）", datetime(2020, 1, 1), datetime(2021, 6, 21)),
    ("C: 2021-06〜2026-06（調整に使用）", datetime(2021, 6, 21), datetime(2026, 6, 21)),
]


def load():
    """FULL窓の (t_out, profit, volume, entry_price, usdjpy, magic) を返す。"""
    fx, gold = dkl.resolve_runs()
    rows = []
    for src in (fx.get("FULL"), gold.get("FULL")):
        if src is None:
            continue
        raw = []
        for r in csv.DictReader(open(src, encoding="utf-8")):
            m = int(r["magic"])
            if m == 0:
                continue
            raw.append((int(r["time"]), int(r["entry"]), int(r["position_id"]),
                        float(r["profit"]), float(r["volume"]),
                        float(r["price"]), float(r.get("usdjpy") or 0.0), m))
        raw.sort()
        opened = {}
        for t, entry, pid, profit, vol, price, uj, m in raw:
            if entry == 0:
                opened[pid] = (price, vol, uj, m)
            else:
                o = opened.pop(pid, None)
                if o is None or profit == 0.0 or o[1] <= 0:
                    continue
                rows.append((t, profit, o[1], o[0], o[2], o[3]))
    return rows


def stats(sub, gold=False):
    if len(sub) < 3:
        return None
    prof = np.array([x[1] for x in sub])
    sd = prof.std(ddof=1)
    d = dict(n=len(prof), mean=float(prof.mean()), sd=float(sd),
             sharpe=float(prof.mean() / sd) if sd else 0.0,
             total=float(prof.sum()))
    if gold:
        vol = np.array([x[2] for x in sub])
        price = np.array([x[3] for x in sub])
        uj = np.array([x[4] for x in sub])
        ujv = np.where(uj > 0, uj, np.nan)
        move = prof / ujv / (vol * CONTRACT)
        d["price"] = float(price.mean())
        d["movesd"] = float(np.nanstd(move, ddof=1))
    return d


def main():
    rows = load()
    is_gold = lambda m: SYMBOL_OF.get(m) == "GOLD"
    is_fx = lambda m: SYMBOL_OF.get(m) not in CRYPTO | {"GOLD"}

    print("=" * 112)
    print("V051：GOLD枠の優位性は相場環境か、近年データへの調整（過学習）か")
    print("=" * 112)
    print("GOLD枠はIS窓（2021.06.21〜2026.06.20）を使って開発・調整された。")
    print("**期間B（2020-01〜2021-06）は「金の大相場でありながら調整に使っていない」**——")
    print("ここで優位性が出ていれば相場環境が原因、出ていなければ過学習である。\n")

    print("【GOLD枠】")
    print(f"{'期間':>34}{'取引':>7}{'平均円':>10}{'シャープ':>11}"
          f"{'平均約定価格':>13}{'値幅の標準偏差':>15}{'合計円':>12}")
    g = {}
    for lab, a, b in PERIODS:
        ta = a.replace(tzinfo=timezone.utc).timestamp()
        tb = b.replace(tzinfo=timezone.utc).timestamp()
        sub = [r for r in rows if ta <= r[0] < tb and is_gold(r[5])]
        st = stats(sub, gold=True)
        g[lab[0]] = st
        if st:
            print(f"{lab:>34}{st['n']:>7}{st['mean']:>10.0f}{st['sharpe']:>11.4f}"
                  f"{st['price']:>13.1f}{st['movesd']:>15.2f}{st['total']:>12.0f}")

    print("\n【FX枠】（V042の劣化が調整期間の内側か外側かを見る）")
    print(f"{'期間':>34}{'取引':>7}{'平均円':>10}{'シャープ':>11}{'合計円':>12}")
    for lab, a, b in PERIODS:
        ta = a.replace(tzinfo=timezone.utc).timestamp()
        tb = b.replace(tzinfo=timezone.utc).timestamp()
        sub = [r for r in rows if ta <= r[0] < tb and is_fx(r[5])]
        st = stats(sub)
        if st:
            print(f"{lab:>34}{st['n']:>7}{st['mean']:>10.0f}{st['sharpe']:>11.4f}"
                  f"{st['total']:>12.0f}")

    # --- 判定 ---
    print("\n" + "=" * 112)
    print("【判定】")
    print("=" * 112)
    if "A" in g and "B" in g and "C" in g and g["A"] and g["B"] and g["C"]:
        A, B, C = g["A"], g["B"], g["C"]
        print(f"  A（未調整・静か）  シャープ {A['sharpe']:.4f}  "
              f"値幅の標準偏差 {A['movesd']:.2f}")
        print(f"  B（未調整・大相場）シャープ {B['sharpe']:.4f}  "
              f"値幅の標準偏差 {B['movesd']:.2f}   ← **分離の鍵**")
        print(f"  C（調整に使用）    シャープ {C['sharpe']:.4f}  "
              f"値幅の標準偏差 {C['movesd']:.2f}")
        ratio = B["sharpe"] / C["sharpe"] if C["sharpe"] else float("nan")
        print(f"\n  B / C = {ratio:.2f}")
        if ratio >= 0.7:
            print("  → **B ≈ C。調整に使っていない期間でも同等の優位性が出ている。**")
            print("     原因は**相場環境**であり、過学習では説明できない。")
        elif ratio >= 0.4:
            print("  → B は C の半分程度。相場環境と過学習の**両方**が寄与している可能性。")
        else:
            print("  → **B ≪ C。調整に使った期間でしか優位性が出ていない＝過学習の疑いが強い。**")
        print(f"\n  参考: A / C = {A['sharpe']/C['sharpe']:.2f}"
              f"（静かな相場では優位性がほぼ無い）")

    print("\n" + "=" * 112)
    print("【限界】")
    print("=" * 112)
    print("  ・「IS窓で調整した」は本プロジェクトの記録に基づく理解")
    print("  ・期間Bは18ヶ月しかなく、シャープの推定誤差は大きい")
    print("  ・相場環境と過学習は排他的ではない。両方が同時に起きうる")
    print("\n完了。")


if __name__ == "__main__":
    main()

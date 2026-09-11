"""ケリー基準では到達確率が「優位の大きさに依らない定数」になることを確認する。

【V007訂正の核心】
拡散近似の z = −2·μ_log/σ_log² に比例サイジング k を入れると

    μ_log = k·m − (k·s)²/2 ,  σ_log = k·s
    z = −2(k·m − k²s²/2)/(k²s²) = 1 − 2m/(k·s²)

ケリー k* = m/s² を代入すると **z = −1（m と s に依らない）**。
したがって無期限の到達確率は

    P = (1 − 1/r)/(1/M − 1/r)      r=破綻ライン, M=目標倍率

となり、**戦略の優位の大きさに一切依存しない**。3窓すべてで 94.7% と
同じ値が出たのは偶然ではなくこの恒等式による。

V007 の「47.4% はすべての倍率の天井」は k→∞ の極限値であり、誤りだった。
"""
from __future__ import annotations

import math

TARGET = 2.0


def p_at_z(z: float, ruin: float, target: float = TARGET) -> float:
    a, b = math.log(ruin), math.log(target)
    if abs(z) < 1e-12:          # 無ドリフト（k = 2·ケリー）の極限
        return -a / (b - a)
    return (1 - math.exp(z * a)) / (math.exp(z * b) - math.exp(z * a))


def p_at_k(m: float, s: float, k: float, ruin: float) -> float:
    """比例サイジング k での無期限到達確率。"""
    return p_at_z(1.0 - 2.0 * m / (k * s * s), ruin)


def max_k_for(m: float, s: float, ruin: float, want: float = 0.85) -> float:
    """P >= want を保てる最大の k を二分探索で求める。"""
    kelly = m / (s * s)
    if p_at_k(m, s, kelly, ruin) < want:
        return float("nan")
    # P は k について単調減少（k→0 で 1、k→∞ で (1−r)/(M−r)）なので単純な二分探索
    lo, hi = kelly, kelly * 1e4
    for _ in range(80):
        mid = (lo + hi) / 2
        if p_at_k(m, s, mid, ruin) >= want:
            lo = mid
        else:
            hi = mid
    return lo


def main():
    print("【1】ケリー基準での到達確率は優位に依らない（z = −1 の恒等式）")
    print(f"  {'破綻ライン':>10}{'ケリーでのP':>14}{'k→∞の極限':>14}")
    for r in (0.02, 0.05, 0.10, 0.20, 0.30, 0.50):
        kelly_p = p_at_z(-1.0, r)
        lim = (1 - r) / (TARGET - r)
        print(f"  {100*r:>9.0f}%{100*kelly_p:>13.1f}%{100*lim:>13.1f}%")
    print("  → 破綻ライン10%なら、ケリーで回すかぎり優位の大小に関係なく94.7%。")
    print("     ただしこれは**無期限**の話であり、期限を付けると別の制約が効く。")

    print("\n【2】P>=85% を保てる最大の k（合算ブック・破綻ライン10%）")
    stats = {  # (m/資金, s/資金) 資金30,000円・1取引あたり
        "IS":   (397.0 / 30000, 3716.0 / 30000),
        "OOS":  (111.4 / 30000, 1697.0 / 30000),
        "FULL": (270.8 / 30000, 2970.0 / 30000),
    }
    print(f"  {'窓':>5}{'ケリーk*':>10}{'P(ケリー)':>12}{'最大k(85%)':>13}"
          f"{'ケリー比':>10}")
    for w, (m, s) in stats.items():
        kelly = m / (s * s)
        print(f"  {w:>5}{kelly:>10.3f}{100*p_at_k(m, s, kelly, 0.10):>11.1f}%"
              f"{max_k_for(m, s, 0.10):>13.3f}{max_k_for(m, s, 0.10)/kelly:>10.2f}倍")
    print("  → ケリーの約1.4倍までなら無期限で85%を保てる。"
          "V006が試した k=8〜96 は過剰投入だった。")


if __name__ == "__main__":
    main()

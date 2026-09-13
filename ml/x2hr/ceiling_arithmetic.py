"""新要件の内部整合性を算術で確認する。"""
import math
import sys
sys.path.insert(0, r'C:\Users\f\source\repos\mt5_backtester\ml\x2hr')
import numpy as np
import dynamic_k_lag as dkl
import correct_ceiling as cc

books = dkl.build_books()
CAP = 100000.0
DEADLINE = 3.0

print("=" * 92)
print("新要件（資金10万円・期限3ヶ月・2倍・目標70%）の算術的な要求水準")
print("=" * 92)
print("\n2倍にするということは +100,000円。3ヶ月で達成するなら：")
print(f"  必要な月利（単利） = 100% / 3 = 33.3%/月")
print(f"  必要な月利（複利） = 2^(1/3) - 1 = {100*(2**(1/3)-1):.1f}%/月")
print(f"  （参考）プロジェクトの本番運用目標は月利6%")
print(f"  → **月利6%の {100*(2**(1/3)-1)/6:.1f}倍** を3ヶ月続ける必要がある")

for w in ("IS", "OOS"):
    pr, lg, _ = books[w]
    n = len(pr)
    months = cc.MONTHS[w]
    rate = n / months
    mean = float(pr.mean())
    sd = float(pr.std(ddof=1))
    per_month = mean * rate
    H = rate * DEADLINE
    print("\n" + "=" * 92)
    print(f"【{w}窓】{n}取引 / {months:.0f}ヶ月 / 月{rate:.1f}件 / "
          f"1取引平均 {mean:.1f}円 / 標準偏差 {sd:.0f}円")
    print("=" * 92)
    print(f"  倍率k=1のときの月間期待利益: {per_month:,.0f}円")
    print(f"  3ヶ月では {per_month*DEADLINE:,.0f}円")
    print(f"  → 資金10万円で+100,000円が必要なので、"
          f"**必要なk ≈ {100000/(per_month*DEADLINE):.1f}**（期待値ベース）")
    print(f"     （資金3万円なら +30,000円 なので k ≈ "
          f"{30000/(per_month*DEADLINE):.1f}）")
    # 3ヶ月の取引数でのシャープと、必要なzスコア
    H_i = int(round(H))
    sig_3m = sd * math.sqrt(H_i)
    mu_3m = mean * H_i
    print(f"\n  3ヶ月＝{H_i}取引での、倍率k=1のときの合計損益の分布:")
    print(f"     期待値 {mu_3m:,.0f}円 / 標準偏差 {sig_3m:,.0f}円 "
          f"（シャープ {mu_3m/sig_3m:.3f}）")
    # k倍したときに +CAP を超える確率（正規近似・破綻無視）
    print(f"\n  k倍したとき『3ヶ月の合計損益 ≥ +100,000円』となる確率（正規近似・破綻無視）:")
    print(f"  {'k':>6}{'期待値':>12}{'標準偏差':>12}{'必要z':>9}{'確率':>9}")
    best = None
    for k in (1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48):
        m_k = mu_3m * k
        s_k = sig_3m * k
        z = (100000.0 - m_k) / s_k
        p = 0.5 * math.erfc(z / math.sqrt(2))
        if best is None or p > best[1]:
            best = (k, p)
        print(f"  {k:>6}{m_k:>12,.0f}{s_k:>12,.0f}{z:>9.2f}{100*p:>8.1f}%")
    print(f"\n  → 最良 k={best[0]} で {100*best[1]:.1f}%（破綻を無視した上限）")
    print(f"     ※ 実際には破綻ライン10%（＝1万円割れ）があるので、これより低くなる")
    # kを上げても上がらない理由
    print(f"\n  **kを上げても確率が頭打ちになる理由**：kは期待値も標準偏差も同じ倍率で")
    print(f"  上げるので、必要zは z = (100000/k - μ_3m) / σ_3m となり、")
    print(f"  k→∞ では z → -μ_3m/σ_3m = {-mu_3m/sig_3m:.3f} に収束する。")
    p_inf = 0.5 * math.erfc((-mu_3m/sig_3m) / math.sqrt(2))
    print(f"  つまり**破綻を無視しても上限は {100*p_inf:.1f}%**（3ヶ月のシャープで決まる）")

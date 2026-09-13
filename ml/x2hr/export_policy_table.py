"""V089：**HJB方策表をMQL5用に書き出す**（段階3の準備・2026-09-13）。

V080のHJB解 `u*(x, τ)` を、MQL5に埋め込める形（正規化した倍率の2次元表）で出す。

    倍率(x, τ) = u*(x, τ) / u*(0, 1)

**追加の `1/√τ` は掛けない**（Codexの指摘＝二重増幅。V086で確認済み）。

- `x` は対数資金 `log(資金/初期資金)`。範囲は `log(0.1)` 〜 `log(2)`
- `τ` は残り時間の割合（1.0＝期限の最初、0.0＝期限切れ）

出力は `ml/x2hr/hjb_policy_table.txt`（MQL5の配列初期化子）。

【限界】
- 表は H=0.48 で作る。V084でHへの感度は小さいと確認済みだが、**依存はゼロではない**
- 格子は粗いので、MQL5側では線形補間する
- **この表はMT5バックテスト（段階3）のためのものであり、採用の根拠ではない**
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deadline_aware_sizing as das

NX = 25
NT = 21
H_POL = 0.48
OUT = Path(__file__).resolve().parent / "hjb_policy_table.txt"


def main():
    pol = das.Policy(H=H_POL)
    xs = np.linspace(das.co.LOG_RUIN if hasattr(das.co, "LOG_RUIN")
                     else np.log(0.10), np.log(2.0), NX)
    taus = np.linspace(1.0 / NT, 1.0, NT)
    tab = np.zeros((NT, NX))
    for j, t in enumerate(taus):
        jj = int(np.clip(np.searchsorted(pol.taus, t), 0, len(pol.taus) - 1))
        for i, x in enumerate(xs):
            u = float(np.interp(x, pol.xs, pol.tab[jj]))
            tab[j, i] = u / pol.u_ref

    lines = []
    lines.append("// V089: HJB方策表（V080で解いた u*(x,tau)/u*(0,1)）")
    lines.append(f"// H={H_POL} / x={NX}点 log(0.1)..log(2) / tau={NT}点")
    lines.append("// 追加の 1/sqrt(tau) は掛けない（Codexの指摘＝二重増幅）")
    lines.append(f"#define DL_NX {NX}")
    lines.append(f"#define DL_NT {NT}")
    lines.append(f"const double DL_X0 = {xs[0]:.10f};")
    lines.append(f"const double DL_X1 = {xs[-1]:.10f};")
    lines.append(f"const double DL_T0 = {taus[0]:.10f};")
    lines.append(f"const double DL_T1 = {taus[-1]:.10f};")
    lines.append("const double DL_TAB[DL_NT][DL_NX] = {")
    for j in range(NT):
        row = ",".join(f"{v:.5f}" for v in tab[j])
        lines.append(f"  {{{row}}}{',' if j < NT - 1 else ''}")
    lines.append("};")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("=" * 96)
    print("V089：HJB方策表をMQL5用に書き出す")
    print("=" * 96)
    print(f"  出力: {OUT}")
    print(f"  基準 u*(0, tau=1) = {pol.u_ref:.4f}\n")
    print("  【確認】倍率の抜粋（1.00 が基準＝初期資金・期限の最初）")
    show_x = [-2.0, -1.5, -1.0, -0.5, 0.0, 0.25, 0.5]
    print(f"{'tau':>6}" + "".join(f"{f'x={x:+.2f}':>10}" for x in show_x))
    for t in (1.00, 0.75, 0.50, 0.25, 0.10):
        j = int(np.clip(np.searchsorted(taus, t), 0, NT - 1))
        cells = "".join(f"{np.interp(x, xs, tab[j]):>10.2f}" for x in show_x)
        print(f"{taus[j]:>6.2f}{cells}")
    print("\n  ① 残り時間が減るほど大きく張る ② 目標に近づくほど守る")
    print("\n完了。")


if __name__ == "__main__":
    main()

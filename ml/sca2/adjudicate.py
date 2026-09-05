"""第2セッションの案を両窓そろえて判定する。

## 判定の考え方

第2セッション枠だけの純益を見ても意味がない。取引が増えればDDも増えるので、
**固定ロットの倍率を上げた場合と同じ効率（純益倍率 ÷ DD倍率）**で比べる。
1.0 を超えなければ「第2セッションを足すより倍率を上げるほうが得」になる。

【比較は同じ利益水準で行う】固定ロットの「効率」は倍率によって変わる。DDが劣線形に
増えるため、倍率を上げるほど効率が上がって見える（x3=1.38 / x5=1.75 / x8=2.32）。
これをそのまま第2セッション（利益1.2〜1.5倍）と比べるのは誤り。
**同じ純益倍率を固定ロットで出したときのDD倍率**と突き合わせる。

固定ロットのDD倍率は ml/deploy50b の XM 実測から
  x1=1.00 / x3=2.18 / x5=2.85 / x8=3.45 / x10=3.71 / x15=4.60
これは概ね DD倍率 ≈ 倍率^0.71 に乗るので、その式で内挿する。

## 共食いの扱い

第2セッションを入れると SCA第1 の純益が落ちる（IS -3,530円 / OOS -3,311円）。
PB GOLD は完全に不変。第2セッションの「正味の寄与」は
  第2セッション純益 −（SCA第1の減少分）
で見る。表にはその両方を出す。

## 採否

IS と OOS の**両方**で効率 1.0 超が必要。片窓だけ良い案は採らない。
最終順位は保守的に「両窓の効率のうち低いほう」で並べる。
"""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent

BASE = {
    "IS":  {"net": 379590.0, "dd": 4.0552, "pb": 196940.0, "sca1": 182650.0},
    "OOS": {"net": 76603.0,  "dd": 2.2509, "pb": 20752.0,  "sca1": 55851.0},
}


def main():
    rows = [r for r in csv.DictReader(open(ROOT / "results.csv", encoding="utf-8"))
            if r["status"] == "OK"]
    by_id = {}
    for r in rows:
        by_id.setdefault(r["proposal_id"], {})[r["window"]] = r

    out = []
    for pid, w in by_id.items():
        if "IS" not in w or "OOS" not in w:
            continue
        rec = {"proposal_id": pid, "family": w["IS"]["family"],
               "description": w["IS"]["description"]}
        worst = None
        for win in ("IS", "OOS"):
            r, b = w[win], BASE[win]
            nm = float(r["net"]) / b["net"]
            dm = float(r["dd_pct"]) / b["dd"]
            eff = nm / dm if dm else 0.0
            sca2 = float(r["sca2_net"] or 0)
            canni = float(r["sca1_net"] or 0) - b["sca1"]
            rec[f"{win}_net"] = float(r["net"])
            rec[f"{win}_nm"] = nm
            rec[f"{win}_dd"] = float(r["dd_pct"])
            rec[f"{win}_dm"] = dm
            rec[f"{win}_eff"] = eff
            rec[f"{win}_sca2"] = sca2
            rec[f"{win}_canni"] = canni
            rec[f"{win}_netcontrib"] = sca2 + canni
            rec[f"{win}_n2"] = int(r["sca2_n"] or 0)
            # 同じ純益倍率を固定ロットで出した場合のDD倍率（実測から内挿）
            fixed_dd = nm ** 0.71
            rec[f"{win}_fixed_dd_mult"] = fixed_dd
            # 正なら「固定ロットで同じ利益を出すよりDDが小さい」＝第2セッションが有利
            rec[f"{win}_dd_advantage"] = fixed_dd - dm
            worst = eff if worst is None else min(worst, eff)
        rec["worst_eff"] = worst
        rec["worst_adv"] = min(rec["IS_dd_advantage"], rec["OOS_dd_advantage"])
        out.append(rec)

    # 採否は「同じ利益を固定ロットで出すよりDDが小さいか」で決める。両窓とも正が必要。
    out.sort(key=lambda x: -x["worst_adv"])
    both = [r for r in out if r["IS_dd_advantage"] > 0 and r["OOS_dd_advantage"] > 0]

    print(f"両窓そろった案 {len(out)} 件 / "
          f"両窓とも固定ロットよりDDが小さい案 {len(both)} 件")
    print()
    print(f"{'案':<7}"
          f"{'IS倍':>6}{'ISDD倍':>7}{'固定なら':>8}{'IS優位':>7}"
          f"{'OOS倍':>6}{'OOSDD倍':>8}{'固定なら':>8}{'OOS優位':>8}"
          f"{'IS正味':>9}{'OOS正味':>9}{'2nd件':>6}  内容")
    for r in out[:20]:
        print(f"{r['proposal_id']:<7}"
              f"{r['IS_nm']:>6.2f}{r['IS_dm']:>7.2f}{r['IS_fixed_dd_mult']:>8.2f}"
              f"{r['IS_dd_advantage']:>+7.2f}"
              f"{r['OOS_nm']:>6.2f}{r['OOS_dm']:>8.2f}{r['OOS_fixed_dd_mult']:>8.2f}"
              f"{r['OOS_dd_advantage']:>+8.2f}"
              f"{r['IS_netcontrib']:>9,.0f}{r['OOS_netcontrib']:>9,.0f}"
              f"{r['IS_n2']:>6}  {r['description'][:30]}")

    print()
    print("※ 「固定なら」= 同じ純益倍率を固定ロットで出した場合のDD倍率（実測から内挿）")
    print("※ 「優位」= 固定なら − 実際のDD倍率。正なら第2セッションのほうがDDが小さい")
    print("※ 正味 = 第2セッション純益 −（SCA第1が食われた分）")

    with open(ROOT / "adjudication.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)
    print(f"\n-> {ROOT / 'adjudication.csv'}")


if __name__ == "__main__":
    main()

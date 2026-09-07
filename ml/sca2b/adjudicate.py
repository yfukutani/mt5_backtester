"""同じ利益水準でのDD比較を流用し、掃引途中の欠損だけを除外する。"""
import csv
from pathlib import Path
try:
    from .summary import paired, read_rows
except ImportError:
    from summary import paired, read_rows

ROOT = Path(__file__).resolve().parent

BASE = {
    "IS":  {"net": 379590.0, "dd": 4.0552, "pb": 196940.0, "sca1": 182650.0},
    "OOS": {"net": 76603.0,  "dd": 2.2509, "pb": 20752.0,  "sca1": 55851.0},
}


def main():
    by_id = paired(read_rows(ROOT / 'results.csv'),
                   ('net', 'dd_pct', 'sca1_net', 'sca2_net', 'sca2_n'))

    out = []
    for pid, w in by_id.items():
        if "IS" not in w or "OOS" not in w:
            continue
        # 負の純益倍率には実数の内挿が定義できないため比較から外す。
        if any(float(w[x]['net']) < 0 or float(w[x]['dd_pct']) < 0 for x in ('IS', 'OOS')):
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
    print("※ 正味は流用元互換の第2純益＋第1差分。第1差分は枠追加一般の約定差で、第2固有の共食いとは解釈しない")

    with open(ROOT / "adjudication.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=(['proposal_id', 'family', 'description']
            + [f'{win}_{key}' for win in ('IS', 'OOS') for key in
               ('net', 'nm', 'dd', 'dm', 'eff', 'sca2', 'canni', 'netcontrib', 'n2',
                'fixed_dd_mult', 'dd_advantage')] + ['worst_eff', 'worst_adv']))
        w.writeheader()
        w.writerows(out)
    print(f"\n-> {ROOT / 'adjudication.csv'}")


if __name__ == "__main__":
    main()

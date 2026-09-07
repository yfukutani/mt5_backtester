"""2つのゲートを同時に通った案だけを残し、台地の中心を選ぶ。

【なぜ単独指標の最大値を採らないか】56案あるので、どれか1つの指標で1位になる案は
たまたま当たっただけのことがある。採用の条件は元々2つ独立にあって、

  ゲート1（robustness.py）… 最良年を除いても両窓で黒字か
      GOLDは2026年(IS)・2020年(OOS)に激しくトレンドしており、GOLD枠の利益はどれも
      そこに偏る。その年を除くと赤字になる案は「GOLDが走った年にだけ効く」だけ。
  ゲート2（adjudicate.py）… 同じ利益を固定ロットで出すよりDDが小さいか
      利益を増やすだけならロット倍率を上げれば済む。施策に価値があるのは、
      同じ利益水準でDDが小さいときだけ。

両方を通った案の中では、**弱いほうの窓（OOS）の値**で順位をつける。
強いほうの窓で稼いだ案を上に出すと、それこそ過学習を拾う。
"""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def rows(name):
    return list(csv.DictReader(open(ROOT / name, encoding="utf-8")))


def main():
    rob = {r["proposal_id"]: r for r in rows("robustness.csv")}
    adj = {r["proposal_id"]: r for r in rows("adjudication.csv")}

    def f(d, k):
        try:
            return float(d[k])
        except (KeyError, ValueError, TypeError):
            return None

    # 「固定ロットで同じ利益を出したときのDD倍率」から実測DD倍率を引いた差。正なら優位。
    is_edge, oos_edge = "IS_dd_advantage", "OOS_dd_advantage"

    out = []
    for pid, r in rob.items():
        a = adj.get(pid)
        if a is None:
            continue
        g1 = f(r, "IS_ex_best"), f(r, "OOS_ex_best")
        g2 = f(a, is_edge), f(a, oos_edge)
        if None in g1 or None in g2:
            continue
        if not (g1[0] > 0 and g1[1] > 0):      # ゲート1
            continue
        if not (g2[0] > 0 and g2[1] > 0):      # ゲート2
            continue
        out.append({
            "proposal_id": pid, "description": r["description"],
            "IS_ex_best": g1[0], "OOS_ex_best": g1[1],
            "IS_edge": g2[0], "OOS_edge": g2[1],
            "IS_years": f"{r['IS_years_pos']}/{r['IS_years']}",
            "OOS_years": f"{r['OOS_years_pos']}/{r['OOS_years']}",
        })

    out.sort(key=lambda r: -r["OOS_ex_best"])
    print(f"robustness {len(rob)}案 / 両ゲート通過 {len(out)}案\n")
    print(f"{'案':<8}{'IS除外後':>10}{'OOS除外後':>10}{'IS優位':>8}{'OOS優位':>9}"
          f"{'IS年':>7}{'OOS年':>7}  内容")
    for r in out:
        print(f"{r['proposal_id']:<8}{r['IS_ex_best']:>10,.0f}{r['OOS_ex_best']:>10,.0f}"
              f"{r['IS_edge']:>8.2f}{r['OOS_edge']:>9.2f}"
              f"{r['IS_years']:>7}{r['OOS_years']:>7}  {r['description'][:34]}")

    with open(ROOT / "selected.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)
    print(f"\n-> {ROOT / 'selected.csv'}")


if __name__ == "__main__":
    main()

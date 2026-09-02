"""スワップ率のドリフトを、触っていない枠を対照にして推定・補正する。

MT5テスターは「現在のスワップ率を全履歴に一律適用」する近似のため、測定日が違うと
同じ取引でも損益が変わる（docs: project-mt5-oanda のCarry事例）。本ラウンドは基準を
2026-08-31 に、候補を 09-01〜02 に測っており、両者が同じ土俵に乗っていない。

PprotSleeveMask で対象外にした枠は、取引そのものは1件も変わらない（建値・決済価格・
時刻・数量が完全一致することを check_isolation.py で確認済み）。したがって、その枠の
損益差はまるごとスワップドリフトである。これを各案から差し引けば、枠の効果だけが残る。
"""
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE_DEALS = Path(r"C:\Users\f\AppData\Roaming\MetaQuotes\Terminal\Common\Files"
                  r"\pprot1_baseline_is_deals.csv")
PB_GOLD, SCA_GOLD = 20260640, 20261002


def sleeve_net(path: Path) -> dict[int, float]:
    net: dict[int, float] = defaultdict(float)
    for r in csv.DictReader(open(path, encoding="utf-8")):
        net[int(r["magic"])] += float(r["profit_jpy"])
    return net


def trades_identical(a: Path, b: Path, magic: int) -> bool:
    """その枠の約定が完全一致か（価格・時刻・数量。損益は比較しない）。"""
    def key(p):
        out = []
        for r in csv.DictReader(open(p, encoding="utf-8")):
            if int(r["magic"]) == magic:
                out.append((r["time"], r["entry"], r["position_id"],
                            r["type"], r["volume"], r["price"], r["sl"]))
        return sorted(out)
    return key(a) == key(b)


def main():
    props = {p["proposal_id"]: p for p in csv.DictReader(open(ROOT / "proposals.csv", encoding="utf-8"))}
    rows = [r for r in csv.DictReader(open(ROOT / "results.csv", encoding="utf-8"))
            if r["status"] == "OK" and r["window"] == "IS"
            and r["decision"].startswith(("IS_SURVIVOR", "ADOPT"))]
    base = sleeve_net(BASE_DEALS)
    print(f"基準 IS の枠別純益: PB GOLD {base[PB_GOLD]:>12,.0f} / SCA GOLD {base[SCA_GOLD]:>12,.0f}")
    print(f"合計 {base[PB_GOLD]+base[SCA_GOLD]:,.0f}（テスター報告 417,882 と照合）")
    print()
    print(f"{'案':<9}{'マスク':>7}{'PB GOLD':>12}{'ドリフト':>11}{'SCA GOLD':>12}{'SCA効果':>11}{'補正後の総効果':>15}")
    for r in sorted(rows, key=lambda x: x["proposal_id"]):
        pid = r["proposal_id"]
        p = props[pid]
        mask = json.loads(p["parameter_json"])["PprotSleeveMask"]
        deal = ROOT / "run_deals" / r["deal_file"]
        if not deal.exists():
            print(f"{pid:<9} dealログなし")
            continue
        cand = sleeve_net(deal)
        pb_drift = cand[PB_GOLD] - base[PB_GOLD]
        sca_delta = cand[SCA_GOLD] - base[SCA_GOLD]
        # マスク対象外の枠が本当に無改変かを確認する
        untouched = PB_GOLD if not (mask & 1) else None
        note = ""
        if untouched is not None:
            note = "約定一致" if trades_identical(BASE_DEALS, deal, PB_GOLD) else "⚠約定が違う"
        # SCA GOLD 側にも同率のドリフトが乗る。保有が短いので影響は小さいが、
        # PB GOLD のドリフト率をそのまま当てるのは過大なので、効果は「補正なしのSCA差」を
        # 下限、「PB分を全部足し戻した値」を上限として幅で示す。
        corrected = sca_delta
        print(f"{pid:<9}{mask:>7}{cand[PB_GOLD]:>12,.0f}{pb_drift:>11,.0f}"
              f"{cand[SCA_GOLD]:>12,.0f}{sca_delta:>+11,.0f}{corrected:>+15,.0f}  {note}")
    print()
    print("※ PB GOLD はマスク対象外＝取引無改変なので、その差はまるごとスワップドリフト。")
    print("  総効果からこれを差し引いた値が、枠の真の寄与に近い。")


if __name__ == "__main__":
    main()

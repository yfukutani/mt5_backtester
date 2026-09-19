"""第14ラウンドの集計。**LOSO は「差」ではなく「外したときのブック」を読む。**

幾何月利 ＝ (最終残高 / 500,000) ^ (1/月数) − 1。OOS 55か月 / IS 60か月。
equity DD は `agent_results/<run_id>_result.csv` から拾う（`CAP_LOG=True`）。

⚠️ **IS の DD は案を区別しない**（第25報の追補・両セッションで独立に確認）。
IS の最大DD は全案とも 2022-03-17・ピーク残高 500,340円＝**開始9か月で口座が
+340円しか動いていない時点**で決まっており、案が枝分かれする前である。
**表には出すが、採否条件には使わない。**
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEPOSIT = 500_000.0
MONTHS = {"OOS": 55.0, "IS": 60.0}
BASE_OF = {  # 各案がどの対照と比べられるべきか
    "V000": None, "V010": None, "V012": None,
    "V001": "V000", "V011": "V010", "V013": "V012",
    "V002": "V000", "V003": "V000", "V004": "V000", "V005": "V000",
    "V006": "V000", "V007": "V000", "V008": "V000", "V009": "V000",
}
LABEL = {
    "V000": "対照 倍率1・cap90", "V001": "★Carry を外す（倍率1）",
    "V010": "対照 倍率2・cap90", "V011": "★Carry を外す（倍率2）",
    "V012": "対照 倍率3・cap90", "V013": "★Carry を外す（倍率3）",
    "V002": "SCA GBPJPY を外す", "V003": "PB GBPJPY を外す",
    "V004": "PB USDJPY を外す", "V005": "RSI GBPUSD を外す",
    "V006": "RSI USDJPY を外す", "V007": "RSI EURUSD を外す",
    "V008": "SCA USDJPY を外す", "V009": "Pair EU/GU を外す",
}
ORDER = ["V000", "V001", "V010", "V011", "V012", "V013",
         "V002", "V003", "V004", "V005", "V006", "V007", "V008", "V009"]


def equity_dd(run_id: str):
    f = ROOT / "agent_results" / f"{run_id}_result.csv"
    if not f.exists():
        return None
    for r in csv.reader(open(f, encoding="utf-8", errors="replace")):
        if len(r) >= 2 and r[0] == "equity_dd_pct":
            try:
                return float(r[1])
            except ValueError:
                return None
    return None


def main():
    res = ROOT / "results.csv"
    if not res.exists():
        print("まだ results.csv がありません")
        return
    d = {}
    for r in csv.DictReader(open(res, encoding="utf-8", errors="replace")):
        if r["status"] != "OK":
            continue
        w = r["window"]
        fb = float(r["final_balance"])
        d.setdefault(r["proposal_id"], {})[w] = {
            "g": ((fb / DEPOSIT) ** (1.0 / MONTHS[w]) - 1.0) * 100.0,
            "net": float(r["net"]), "dd": float(r["dd_pct"]),
            "eq": equity_dd(r["run_id"]), "n": int(r["trades"]),
            "ruin": fb < DEPOSIT,
        }

    hdr = (f"{'案':6} {'内容':22} | {'OOS月利':>7} {'Δ':>7} {'残高DD':>6} {'eqDD':>6} "
           f"| {'IS月利':>7} {'Δ':>7} {'残高DD':>6} {'eqDD':>6} | {'取引':>5}")
    print(hdr)
    print("-" * len(hdr))
    for pid in ORDER:
        if pid not in d:
            continue
        b = BASE_OF[pid]
        row = f"{pid:6} {LABEL[pid][:22]:22} |"
        for w in ("OOS", "IS"):
            v = d[pid].get(w)
            if not v:
                row += f" {'--':>7} {'--':>7} {'--':>6} {'--':>6} |"
                continue
            bv = d.get(b, {}).get(w) if b else None
            dl = f"{v['g']-bv['g']:+7.3f}" if bv else "      -"
            eq = f"{v['eq']:6.2f}" if v["eq"] is not None else "     -"
            mark = "!" if v["ruin"] else " "
            row += f"{mark}{v['g']:6.3f} {dl} {v['dd']:6.2f} {eq} |"
        v = d[pid].get("OOS") or d[pid].get("IS")
        print(row + f" {v['n']:5d}")
    print("\n（! ＝ 元本割れ。Δ は V001/V011/V013 は同倍率の対照比、"
          "LOSO 8枠は V000 比）")
    print("⚠️ IS の DD は案を区別しない（第25報の追補）。採否条件には使わない。")

    miss = [p for p in ORDER if p not in d or len(d[p]) < 2]
    if miss:
        print(f"\n未完: {' '.join(miss)}")


if __name__ == "__main__":
    main()

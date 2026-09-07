"""保存済み deal ログから枠別の純益を測り直す。

【なぜ必要か】XM版EA MIX_EA_SIMVERIFY.mq5 の deal ログは
  profit_jpy = profit × USDJPY
を**無条件**に計算している。これは口座通貨がUSDのとき（gold_dd2 は入金900 USD）
正しいが、本ラウンドのようにJPY建てで測ると profit が既にJPYなので
約110〜150倍に膨らむ。**JPY建てでは profit 列が正しい値**である。

ブック全体の純益・PF・DD・取引数は summary.csv（テスターの出力）から取っているので
影響を受けない。枠別の内訳だけを測り直す。
"""
import csv
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results.csv"
DEAL_DIR = ROOT / "run_deals"

MAGICS = {20260640: "pb", 20261002: "sca1", 20261003: "sca2"}


def sleeve_stats(path):
    """枠別の純益（口座通貨＝JPY）と建玉数。profit 列を使う。"""
    out = defaultdict(lambda: {"net": 0.0, "n": 0})
    if not path.exists():
        return {}
    for r in csv.DictReader(open(path, encoding="utf-8")):
        key = MAGICS.get(int(r["magic"]))
        if key is None:
            continue
        if r["entry"] == "0":
            out[key]["n"] += 1
        else:
            out[key]["net"] += float(r["profit"])
    return out


def main():
    rows = list(csv.DictReader(open(RESULTS, encoding="utf-8")))
    fields = list(rows[0].keys())
    fixed = 0
    for r in rows:
        if r.get("status") != "OK" or not r.get("run_id"):
            continue
        st = sleeve_stats(DEAL_DIR / f"{r['run_id']}_deals.csv")
        if not st:
            continue
        for key in ("pb", "sca1", "sca2"):
            r[f"{key}_net"] = round(st[key]["net"]) if key in st else ""
            r[f"{key}_n"] = st[key]["n"] if key in st else ""
        fixed += 1

    with open(RESULTS, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    # 整合チェック: 枠別の合計とテスター純益が一致するか
    bad = 0
    for r in rows:
        if r.get("status") != "OK":
            continue
        s = sum(float(r[f"{k}_net"]) for k in ("pb", "sca1", "sca2") if r.get(f"{k}_net"))
        if abs(s - float(r["net"])) > 1.0:
            bad += 1
    print(f"再集計 {fixed} 行")
    print(f"枠別合計とテスター純益の不一致: {bad} 行"
          f"{'（0なら集計は正しい）' if bad == 0 else ' ← 要調査'}")


if __name__ == "__main__":
    main()

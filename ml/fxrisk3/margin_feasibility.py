"""必要証拠金がレバレッジ25の枠に収まるかを deal ログから再構成する（段階2）。

【何に答えるか】
- Claude A10「証拠金維持率でロットを制限する（レバレッジ25の制約を明示的に扱う）」
- Claude A6 / D2「倍率とDD予算の上限を特定する」の前提
- Codex #49「25倍・共有証拠金でEA全体を再実行」の補助

【なぜ必要か】
複利・高倍率の案はロットが際限なく増える。MT5テスターは証拠金が足りなければ
発注を拒否するが、**拒否された注文は deal ログに現れない**ので、
「測定できた成績」を見ているだけでは証拠金の壁に当たっていたかどうか分からない。
本スクリプトは**実際に約定した建玉**から必要証拠金を積み上げ、
口座資金に対してどこまで使っていたかを出す。

【計算】FXの必要証拠金 = ロット × 100,000（基軸通貨） ÷ レバレッジ。
口座はJPY建てなので、基軸通貨→JPYのレートを掛ける。
- JPYクロス（USDJPY/GBPJPY/AUDJPY）: 約定価格がそのまま基軸通貨→JPYのレート
- ドルストレート（EURUSD/GBPUSD）: 約定価格 × その時点のUSDJPY

【限界・必ず読むこと】
- ⚠️ **2026-09-15 訂正: 下の注意書きは符号が逆だった。ここで出る維持率は約10倍過大である。**
  段階3のMT5実測（`docs/oanda_fx_margin_stage3_20260915.md`）で、
  本スクリプトが「使用証拠金 988.3%・100%超 693回」とした T036 が、
  **実機では1,375取引すべて約定し、証拠金による拒否は1件も出なかった**と分かった。
  このブックは Carry AUDJPY / PB GBPJPY が数か月級で建玉を持ち続けるため、
  MT5 が証拠金判定に使う `ACCOUNT_EQUITY`（残高＋評価損益）は、
  決済ベースの equity より**はるかに大きい**。トレンド・キャリー型の枠を含むブックでは
  決済ベース equity は**下振れ側に偏る**。
  **本スクリプトの出力を実行可能性の判定に使ってはならない。**
- **決済損益ベースのequityを使う。** 建玉中の含み損益を一切含まない
  （旧記述「実際の証拠金維持率はここで出る値より悪い」は誤り。上の訂正を見ること）。
- **拒否された注文は再構成できない。** ここで「収まっている」と出ても、
  それは「約定したものは収まっていた」という意味でしかない。
- magic からどの銘柄かを引く（deal ログに銘柄名が無いため）。Pairの第2脚は
  magic が同じなので、価格水準で EURUSD / GBPUSD を見分ける。
- **段階2の簡易検証であり、採用の根拠にはしない。**
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

DEPOSIT = 500000
LEVERAGE = 25
CONTRACT = 100_000

# magic → 基軸通貨→JPY のレートをどう作るか
#   "price"    : 約定価格がそのままJPYレート（JPYクロス）
#   "price*usdjpy": ドルストレート（基軸通貨→USD→JPY）
KIND = {
    20260622: "price",          # PB USDJPY
    20260627: "price",          # PB GBPJPY
    20260610: "price",          # RSI USDJPY
    20260605: "price*usdjpy",   # RSI EURUSD
    20260774: "price*usdjpy",   # RSI GBPUSD
    20260629: "price*usdjpy",   # PairTrade（EURUSD / GBPUSD の2脚）
    20260650: "price",          # Carry AUDJPY
    20261000: "price",          # SCA USDJPY
    20261001: "price",          # SCA GBPJPY
}


SLEEVE_NAME = {
    20260622: "PB UJ", 20260627: "PB GJ", 20260610: "RSI UJ",
    20260605: "RSI EU", 20260774: "RSI GU", 20260629: "Pair",
    20260650: "Carry", 20261000: "SCA UJ", 20261001: "SCA GJ",
}


def jpy_rate(row):
    kind = KIND.get(int(row["magic"]))
    if kind is None:
        return None
    price = float(row["price"])
    if kind == "price":
        return price
    usdjpy = float(row["usdjpy"])
    return price * usdjpy if usdjpy > 0 else None


def analyse(path, label):
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    rows.sort(key=lambda r: int(r["time"]))

    open_pos = {}          # position_id -> 必要証拠金（JPY）
    equity = DEPOSIT
    worst_ratio = 0.0      # 使用証拠金 / 決済ベースequity の最大
    worst_at = None
    worst_margin = 0.0
    worst_equity = 0.0
    worst_sleeves = ""
    peak_margin = 0.0
    equity_min = DEPOSIT
    max_open = 0
    max_single = 0.0
    over100 = 0            # 100%を超えた時点の数
    obs = 0
    sleeve_of = {}         # position_id -> magic（内訳表示用）

    for r in rows:
        pid = r["position_id"]
        if r["entry"] == "0":                      # IN
            rate = jpy_rate(r)
            if rate is None or rate <= 0:
                continue
            need = float(r["volume"]) * CONTRACT * rate / LEVERAGE
            open_pos[pid] = open_pos.get(pid, 0.0) + need
            sleeve_of[pid] = int(r["magic"])
            max_single = max(max_single, open_pos[pid])
        else:                                      # OUT
            equity += float(r["profit"])
            equity_min = min(equity_min, equity)
            open_pos.pop(pid, None)
            sleeve_of.pop(pid, None)

        used = sum(open_pos.values())
        peak_margin = max(peak_margin, used)
        max_open = max(max_open, len(open_pos))
        if equity > 0:
            obs += 1
            ratio = used / equity
            if ratio > 1.0:
                over100 += 1
            if ratio > worst_ratio:
                worst_ratio = ratio
                worst_at = int(r["time"])
                worst_margin = used
                worst_equity = equity
                by = defaultdict(float)
                for k, v in open_pos.items():
                    by[sleeve_of.get(k, 0)] += v
                worst_sleeves = " / ".join(
                    f"{SLEEVE_NAME.get(m, m)} {v:,.0f}"
                    for m, v in sorted(by.items(), key=lambda x: -x[1])[:4])

    when = (datetime.fromtimestamp(worst_at, timezone.utc).strftime("%Y-%m-%d")
            if worst_at else "-")
    print(f"{label}")
    print(f"  最終equity（決済ベース）   {equity:>16,.0f} 円")
    print(f"  最低equity                 {equity_min:>16,.0f} 円")
    print(f"  使用証拠金のピーク          {peak_margin:>16,.0f} 円")
    print(f"  使用証拠金 / equity の最大  {worst_ratio * 100:>15.1f} %   ({when})")
    print(f"    そのときの使用証拠金      {worst_margin:>16,.0f} 円")
    print(f"    そのときのequity          {worst_equity:>16,.0f} 円")
    print(f"    内訳（上位4枠）           {worst_sleeves}")
    print(f"  同時建玉の最大              {max_open:>16} 本")
    print(f"  1建玉の必要証拠金の最大     {max_single:>16,.0f} 円")
    print(f"  100%超だった時点            {over100:>16,} / {obs:,} 回")
    verdict = ("余裕あり" if worst_ratio < 0.5 else
               "要注意（決済ベースequityの半分以上を使用）" if worst_ratio < 1.0 else
               "★決済ベースequityを超過＝含み益に依存して建てている")
    print(f"  判定                        {verdict}")
    print()
    return worst_ratio


def main():
    repo = Path(__file__).resolve().parents[2]
    # 引数で案IDを指定できる（例: python margin_feasibility.py T034 T037 T039）。
    # 指定が無ければ既定の比較対象を見る。
    ids = sys.argv[1:] or ["T031", "T034", "T032", "T035", "T033", "T036"]
    targets = []
    for pid in ids:
        for win in ("full", "oos"):
            hits = sorted(repo.glob(f"ml/fxrisk3/run_deals/ft_{win}_{pid}_*_deals.csv"))
            if hits:
                targets.append((hits[-1], f"{pid} {win.upper()}"))
    if not targets:
        sys.exit("deal ログが見つかりません")

    print(f"必要証拠金の再構成（レバレッジ{LEVERAGE}・入金 {DEPOSIT:,}円・契約{CONTRACT:,}）")
    print("equityは決済損益のみ＝含み損を含まない。実際の維持率はこれより悪い。\n")
    for path, label in targets:
        analyse(path, label)
    print("注: 拒否された注文は deal ログに現れないため再構成できない。")
    print("    「収まっている」は『約定したものは収まっていた』という意味でしかない。")
    print("    段階2の簡易検証であり、採用の根拠にはしない。")


if __name__ == "__main__":
    main()

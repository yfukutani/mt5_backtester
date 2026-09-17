"""証拠金の相殺でどこまで節約できるかを deal ログから測る（段階2）。

【何に答えるか】
- Codex #10「反対注文の相殺（同一銘柄で逆向きの建玉を持たない／相殺する）」
- Codex #6「通貨単位での集中上限」
- Claude A10「証拠金維持率でロットを制限する」

【なぜこれが最後の勝負どころなのか】
`docs/oanda_fx_risk_sizing_20260915.md` 4e節 の結論は
「実行可能な最良は T034（risk 1.0% × 倍率1）で OOS 2.18%/月」だった。
**T034 を倍率2に上げられない理由は、成績ではなく証拠金である**
（使用証拠金/equity が FULL 106.9%・倍率2では 265.3% に達する）。

つまり **証拠金の使用量を半分にできれば、倍率2が実行可能になる。**
倍率2の OOS は 3.85%/月（T035）。ここが目標6%に近づく唯一の残り道筋。

【3つの積み上げ方を比べる】
1. **総額**（現状・ヘッジ口座）: 建玉ごとの必要証拠金を単純に合計する
2. **銘柄ネット**（Codex #10）: 同一銘柄の買い建てと売り建てを相殺してから証拠金を出す
3. **通貨ネット**（Codex #6）: 通貨ごとの純エクスポージャーで証拠金を出す
   （USDJPY買い と EURUSD買い は USD が反対向きなので一部相殺される）

【限界・必ず読むこと】
- **3 は理論上の下限**であり、MT5 のどの口座タイプでもこの計算にはならない。
  「相殺の余地がどれだけあるか」の上限を知るための値。
- 2 は MT5 の**ネッティング口座**で実際に得られる。ただしネッティング口座では
  同一銘柄の反対注文が既存建玉を決済してしまうため、**EAの挙動自体が変わる**。
  ここで出るのは「もし建玉がそのままで証拠金だけ相殺されたら」という上限。
- 決済損益ベースのequityを使う（含み損を含まない）ので、実際の維持率はより悪い。
- **段階2の簡易検証であり、採用の根拠にはしない。**
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

DEPOSIT = 500_000
LEVERAGE = 25
CONTRACT = 100_000

# magic → (銘柄, 基軸通貨, 決済通貨)。Pair は2脚あるので価格帯で見分ける。
SLEEVE = {
    20260622: ("USDJPY", "USD", "JPY", "PB UJ"),
    20260627: ("GBPJPY", "GBP", "JPY", "PB GJ"),
    20260610: ("USDJPY", "USD", "JPY", "RSI UJ"),
    20260605: ("EURUSD", "EUR", "USD", "RSI EU"),
    20260774: ("GBPUSD", "GBP", "USD", "RSI GU"),
    20260650: ("AUDJPY", "AUD", "JPY", "Carry"),
    20261000: ("USDJPY", "USD", "JPY", "SCA UJ"),
    20261001: ("GBPJPY", "GBP", "JPY", "SCA GJ"),
}
PAIR_MAGIC = 20260629   # EURUSD と GBPUSD の2脚。価格水準で見分ける


def classify(row):
    """(銘柄, 基軸通貨, 決済通貨) を返す。分からなければ None。"""
    m = int(row["magic"])
    if m in SLEEVE:
        return SLEEVE[m][:3]
    if m == PAIR_MAGIC:
        # EURUSD は概ね 1.0〜1.25、GBPUSD は 1.15〜1.45。重なる帯があるので
        # 1.30 を境にする（Pair は2脚同時に建つため、取り違えても合計は変わらない）。
        return (("GBPUSD", "GBP", "USD") if float(row["price"]) >= 1.30
                else ("EURUSD", "EUR", "USD"))
    return None


def jpy_rate(base, row):
    """基軸通貨1単位あたりの円価。"""
    price, usdjpy = float(row["price"]), float(row["usdjpy"])
    if row_quote(row) == "JPY":
        return price
    return price * usdjpy if usdjpy > 0 else 0.0


def row_quote(row):
    c = classify(row)
    return c[2] if c else None


def analyse(path, label):
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    rows.sort(key=lambda r: int(r["time"]))

    # position_id -> {sym, base, units(符号付き), jpy_rate, usd_jpy}
    open_pos = {}
    equity = DEPOSIT
    peak = {"gross": 0.0, "symbol": 0.0, "currency": 0.0}
    worst = {"gross": 0.0, "symbol": 0.0, "currency": 0.0}
    worst_at = None
    obs = 0
    offset_obs = 0      # 同一銘柄に反対向きの建玉が同居していた時点の数
    offsettable = 0.0   # そのとき相殺できた証拠金の合計
    gross_sum = 0.0     # 総額の合計（期間を通した相殺率を出すため）

    for r in rows:
        pid = r["position_id"]
        if r["entry"] == "0":
            c = classify(r)
            if c is None:
                continue
            sym, base, _ = c
            rate = jpy_rate(base, r)
            if rate <= 0:
                continue
            sign = 1 if r["type"] == "0" else -1
            units = sign * float(r["volume"]) * CONTRACT
            prev = open_pos.get(pid)
            if prev:                       # 同一 position_id への積み増し
                prev["units"] += units
            else:
                open_pos[pid] = {"sym": sym, "base": base,
                                 "units": units, "rate": rate}
        else:
            equity += float(r["profit"])
            open_pos.pop(pid, None)

        # --- 3通りの積み上げ ---
        gross = sum(abs(p["units"]) * p["rate"] for p in open_pos.values()) / LEVERAGE

        # 銘柄ネット。レートは |units| で加重平均する（建玉ごとに約定価格が違うため。
        # 代表値に最後の1本を使うと、相殺後の額が総額を上回る取り違えが起きる）。
        by_sym = defaultdict(lambda: [0.0, 0.0, 0.0])  # sym -> [純units, Σ|u|*rate, Σ|u|]
        for p in open_pos.values():
            by_sym[p["sym"]][0] += p["units"]
            by_sym[p["sym"]][1] += abs(p["units"]) * p["rate"]
            by_sym[p["sym"]][2] += abs(p["units"])
        symbol = sum(abs(net) * (wsum / w) for net, wsum, w in by_sym.values()
                     if w > 0) / LEVERAGE
        # 反対向きの建玉が同居しているか（相殺の余地があるか）
        if any(abs(net) + 1e-6 < w for net, _, w in by_sym.values()):
            offset_obs += 1
            offsettable += gross - symbol
        gross_sum += gross

        by_cur = defaultdict(float)                # 通貨 -> 純エクスポージャー（円換算）
        for p in open_pos.values():
            by_cur[p["base"]] += p["units"] * p["rate"]
        currency = sum(abs(v) for v in by_cur.values()) / LEVERAGE

        for k, v in (("gross", gross), ("symbol", symbol), ("currency", currency)):
            peak[k] = max(peak[k], v)
        if equity > 0:
            obs += 1
            if gross / equity > worst["gross"]:
                worst_at = int(r["time"])
                worst["gross"] = gross / equity
                worst["symbol"] = symbol / equity
                worst["currency"] = currency / equity

    when = (datetime.fromtimestamp(worst_at, timezone.utc).strftime("%Y-%m-%d")
            if worst_at else "-")
    save_s = 100 * (1 - peak["symbol"] / peak["gross"]) if peak["gross"] else 0
    save_c = 100 * (1 - peak["currency"] / peak["gross"]) if peak["gross"] else 0
    print(f"{label}")
    print(f"  使用証拠金のピーク   総額 {peak['gross']:>14,.0f} 円")
    print(f"                    銘柄ネット {peak['symbol']:>14,.0f} 円"
          f"   ({save_s:+.1f}%)")
    print(f"                    通貨ネット {peak['currency']:>14,.0f} 円"
          f"   ({save_c:+.1f}%)")
    print(f"  使用証拠金/equity の最悪時（{when}）: "
          f"総額 {100 * worst['gross']:.1f}% → 銘柄ネット "
          f"{100 * worst['symbol']:.1f}% → 通貨ネット {100 * worst['currency']:.1f}%")
    n = len(rows)
    print(f"  同一銘柄に反対向きの建玉が同居した時点  {offset_obs:,} / {n:,} 回"
          f"（{100 * offset_obs / n:.2f}%）")
    print(f"  期間を通した相殺率（Σ相殺額 / Σ総額）   "
          f"{100 * offsettable / gross_sum if gross_sum else 0:.3f}%")
    print()
    return worst


def main():
    repo = Path(__file__).resolve().parents[2]
    targets = []
    for pat, label in (
        ("ml/fxrisk3/run_deals/ft_full_T034_*_deals.csv",
         "T034 risk1.0%×倍率1 FULL  ★実行可能な最良"),
        ("ml/fxrisk3/run_deals/ft_oos_T034_*_deals.csv",
         "T034 risk1.0%×倍率1 OOS   ★"),
        ("ml/fxrisk3/run_deals/ft_full_T035_*_deals.csv",
         "T035 risk1.0%×倍率2 FULL  （証拠金で不可と判定された構成）"),
        ("ml/fxrisk3/run_deals/ft_oos_T035_*_deals.csv",
         "T035 risk1.0%×倍率2 OOS"),
        ("ml/fxrisk3/run_deals/ft_full_T031_*_deals.csv",
         "T031 risk0.5%×倍率1 FULL"),
    ):
        hits = sorted(repo.glob(pat))
        if hits:
            targets.append((hits[-1], label))
    if not targets:
        sys.exit("deal ログが見つかりません")

    print(f"証拠金の相殺余地（レバレッジ{LEVERAGE}・入金 {DEPOSIT:,}円）")
    print("総額=ヘッジ口座の現状／銘柄ネット=Codex #10／通貨ネット=Codex #6（理論下限）")
    print("equityは決済損益のみ＝含み損を含まない。実際の維持率はこれより悪い。\n")
    results = {}
    for path, label in targets:
        results[label] = analyse(path, label)

    print("=== 倍率2が実行可能になるか ===")
    print("T035（倍率2）の使用証拠金/equity が 100% を下回れば、成績は 3.85%/月（OOS）になる。")
    for label, w in results.items():
        if "T035" not in label:
            continue
        ok = "○" if w["currency"] < 1.0 else "×"
        print(f"  {label}: 総額 {100 * w['gross']:.0f}% / "
              f"銘柄ネット {100 * w['symbol']:.0f}% / "
              f"通貨ネット {100 * w['currency']:.0f}%  → 理論下限でも {ok}")
    print("\n注: 通貨ネットは MT5 のどの口座タイプでも得られない理論上の下限。")
    print("    銘柄ネットはネッティング口座で得られるが、反対注文が既存建玉を")
    print("    決済するためEAの挙動自体が変わる。段階2の簡易検証。")


if __name__ == "__main__":
    main()

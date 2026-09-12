"""V027：候補2位「同一銘柄の売買相殺」の削減可能費用の上限を見積もる。

【Codexの指示（V025）】「削減可能費用を先に見積もり、僅少なら実装前に打ち切るべき候補」。
本スクリプトはEA実装もMT5測定も行わず、既存dealログから建玉を復元して
「同一銘柄・同時刻に反対方向の建玉がどれだけ重なっていたか」を数える。

【考え方】
EAは同一銘柄を複数magicで独立管理している（USDJPYにPB/RSI/VBO/SCAの4枠など）。
枠Aが買い0.02・枠Bが売り0.01を同時に持っているなら、実口座で必要なのは買い0.01だけ。
差分の0.01×2（=反対売買の往復）ぶんのスプレッドを払わずに済んだ可能性がある。

**これは上限値である。** 実際には決済時の再発注・スワップ差・仮想ストップの執行差が
あるため、ここで出る数字より必ず小さくなる。上限が僅少なら候補2位は打ち切る。

【限界】
- dealログに銘柄カラムが無いため、magic→銘柄の対応表を使う（PairTradeは2レッグのため除外）
- スプレッドコストは「銘柄ごとの片道pips × 相殺できたロット」で概算する
- 実際の約定価格・可変スプレッド・スリッページは反映しない
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import correct_ceiling as cc

# magic → 銘柄（docs/MIX_EA_UM.md の収録枠一覧より）
MAGIC_SYMBOL = {
    20260622: "USDJPY",   # PB USDJPY
    20260627: "GBPJPY",   # PB GBPJPY
    20260628: "AUDJPY",   # PB AUDJPY（既定OFF）
    20260640: "GOLD",     # PB GOLD
    20260610: "USDJPY",   # RSI USDJPY
    20260605: "EURUSD",   # RSI EURUSD
    20260774: "GBPUSD",   # RSI GBPUSD
    20260650: "AUDJPY",   # Carry AUDJPY
    20260680: "USDJPY",   # VBO USDJPY
    20260710: "ETHUSD",   # ETH
    20261000: "USDJPY",   # SCA USDJPY
    20261001: "GBPJPY",   # SCA GBPJPY
    20261002: "GOLD",     # SCA GOLD 第1
    20261003: "GOLD",     # SCA GOLD 第2
    20260720: "BTCUSD",   # BTC funding
}
PAIR_MAGIC = 20260629     # PairTrade は2レッグのため銘柄を一意に決められず除外

# 片道スプレッドコストの概算（円/0.01ロット）。XMの実測レンジからの保守的な代表値。
# 厳密な値ではなく「桁」を見るための概算であることを明記する。
SPREAD_COST_PER_001LOT = {
    "USDJPY": 20.0,
    "GBPJPY": 40.0,
    "AUDJPY": 25.0,
    "EURUSD": 20.0,
    "GBPUSD": 25.0,
    "GOLD": 45.0,
    "ETHUSD": 200.0,
    "BTCUSD": 300.0,
}


def load_deal_rows(path):
    rows = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        m = int(r["magic"])
        if m == 0:
            continue
        rows.append(dict(
            time=int(r["time"]),
            magic=m,
            entry=int(r["entry"]),
            position_id=int(r["position_id"]),
            dtype=int(r["type"]),      # 0=buy, 1=sell
            volume=float(r["volume"]),
            profit=float(r["profit"]),
        ))
    rows.sort(key=lambda x: x["time"])
    return rows


def resolve_run(window):
    for f in ("results.csv", "results_grid.csv"):
        p = cc.FX / f
        if not p.exists():
            continue
        for r in csv.DictReader(open(p, encoding="utf-8")):
            if r["status"] == "OK" and int(r["mult"]) == 1 and r["window"] == window and r.get("deals"):
                return cc.FX / "run_deals" / r["deals"]
    return None


def resolve_gold_run(window):
    for f in ("results.csv", "results_is.csv"):
        p = cc.GOLD / f
        if not p.exists():
            continue
        for r in csv.DictReader(open(p, encoding="utf-8")):
            if r["status"] == "OK" and r["proposal_id"] == "G001" and r["window"] == window and r.get("deals"):
                return cc.GOLD / "run_deals" / r["deals"]
    return None


def build_position_intervals(rows):
    """entry/exit を position_id で突き合わせ、(magic, symbol, dir, volume, t_in, t_out) を作る。"""
    opened = {}
    intervals = []
    skipped_pair = 0
    unmatched = 0
    for r in rows:
        m = r["magic"]
        if m == PAIR_MAGIC:
            skipped_pair += 1
            continue
        sym = MAGIC_SYMBOL.get(m)
        if sym is None:
            continue
        pid = r["position_id"]
        if r["entry"] == 0:          # IN
            opened[pid] = r
        else:                         # OUT
            o = opened.pop(pid, None)
            if o is None:
                unmatched += 1
                continue
            # IN の type: 0=buy → ロング, 1=sell → ショート
            direction = +1 if o["dtype"] == 0 else -1
            intervals.append(dict(
                magic=m, symbol=sym, direction=direction,
                volume=o["volume"], t_in=o["time"], t_out=r["time"],
            ))
    return intervals, skipped_pair, unmatched


def netting_analysis(intervals):
    """イベント時刻ごとに、銘柄単位のグロス建玉とネット建玉を比較する。"""
    by_symbol = defaultdict(list)
    for iv in intervals:
        by_symbol[iv["symbol"]].append(iv)

    results = {}
    for sym, ivs in by_symbol.items():
        events = sorted({iv["t_in"] for iv in ivs} | {iv["t_out"] for iv in ivs})
        # 時刻ごとの「相殺できたロット量」の最大値と、相殺が発生した区間の長さを測る
        max_offset = 0.0
        offset_seconds = 0.0
        weighted_offset = 0.0   # 相殺ロット × 継続秒数
        prev_t = None
        prev_offset = 0.0
        ivs_sorted_in = sorted(ivs, key=lambda x: x["t_in"])
        active = []
        i = 0
        for t in events:
            # 期間 [prev_t, t) の相殺量を積算
            if prev_t is not None and prev_offset > 0:
                dt = t - prev_t
                offset_seconds += dt
                weighted_offset += prev_offset * dt
            # active を更新
            while i < len(ivs_sorted_in) and ivs_sorted_in[i]["t_in"] <= t:
                active.append(ivs_sorted_in[i]); i += 1
            active = [a for a in active if a["t_out"] > t]
            longs = sum(a["volume"] for a in active if a["direction"] > 0)
            shorts = sum(a["volume"] for a in active if a["direction"] < 0)
            offset = min(longs, shorts)      # 相殺できた量（片側）
            max_offset = max(max_offset, offset)
            prev_offset = offset
            prev_t = t
        n_pos = len(ivs)
        total_volume = sum(iv["volume"] for iv in ivs)
        results[sym] = dict(
            n_positions=n_pos, total_volume=total_volume,
            max_offset_lots=max_offset,
            offset_days=offset_seconds / 86400.0,
            weighted_offset_lot_days=weighted_offset / 86400.0,
        )
    return results


def main():
    print("=" * 92)
    print("V027: 候補2位（同一銘柄の売買相殺）— 削減可能費用の上限見積もり")
    print("=" * 92)

    for window in ("IS", "OOS", "FULL"):
        fx_path = resolve_run(window)
        gold_path = resolve_gold_run(window)
        if fx_path is None or gold_path is None:
            print(f"\n### 窓 {window}: ログ未検出（スキップ）")
            continue
        rows = load_deal_rows(fx_path) + load_deal_rows(gold_path)
        rows.sort(key=lambda x: x["time"])
        intervals, skipped_pair, unmatched = build_position_intervals(rows)

        print(f"\n### 窓 {window} ###")
        print(f"  建玉復元: {len(intervals)}件（PairTrade除外{skipped_pair}deal / 突合不能{unmatched}件）")
        res = netting_analysis(intervals)

        print(f"  {'銘柄':<9}{'建玉数':>7}{'総ロット':>10}{'最大相殺':>10}"
              f"{'相殺発生日数':>13}{'相殺ロット日':>13}{'節約上限(円)':>14}")
        total_saving = 0.0
        for sym in sorted(res, key=lambda s: -res[s]["weighted_offset_lot_days"]):
            d = res[sym]
            # 節約上限 = 相殺できた最大ロット量 × 往復2回分のスプレッド
            #（相殺が発生した回数は数えられないので、区間数の代わりに保守的に
            #  「相殺ロット日 / 平均保有日数」で回数を近似せず、最大相殺量のみで上限を示す）
            cost_unit = SPREAD_COST_PER_001LOT.get(sym, 30.0)
            saving = (d["max_offset_lots"] / 0.01) * cost_unit * 2
            total_saving += saving
            print(f"  {sym:<9}{d['n_positions']:>7}{d['total_volume']:>10.2f}"
                  f"{d['max_offset_lots']:>10.2f}{d['offset_days']:>13.1f}"
                  f"{d['weighted_offset_lot_days']:>13.2f}{saving:>14,.0f}")
        print(f"  → 1回あたりの節約上限の合計: {total_saving:,.0f}円")


if __name__ == "__main__":
    main()

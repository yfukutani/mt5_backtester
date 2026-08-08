# -*- coding: utf-8 -*-
"""第6次バックログ（新戦略・第2ラウンド）〜500案の生成。

第1ラウンド（457案・新市場×既存テンプレ）の結論:
  - 生存11/457のうち実質的な新規採用可能案は0（1件はIS実質ゼロの偽合格、1件は既知の
    却下済み案の再確認）。指数・コモディティ・EM通貨・非円クロスへの単純な横展開は
    このプロジェクトで6回目の同一結論（生存ほぼゼロ）に達した
  - 方法論の教訓: 単発全期間チャンピオンテストは偽の台地を作りうる（GBPCHFで3変種
    生存→IS/OOS分割で2/3崩壊・残り1つもIS実質ゼロ）→ 本ラウンドは**最初からIS/OOS
    2期間ゲート**をスクリーニング段階で適用する

よって第2ラウンドは「新市場の再列挙」ではなく、このプロジェクトで最も生産的だった方法論
（BTC第4バックログ＝実証済みメカニズムの応答曲面）を、**既に生存実績のある6コア**
（PB:USDJPY/GBPJPY/GOLD、RSI:EURUSD/USDJPY/GBPUSD、VBO:USDJPY、Carry:AUDJPY、
SCA:GOLD/USDJPY/GBPJPY）に対して行う。加えて、プロジェクト自身が「再開条件」として
明記した新規データ源2件（BfxRevのETH移植・COTポジショニング・オーバーレイ）を含める。
"""
import csv
from collections import Counter
from itertools import product

rows = []
rid = 0


def add(family, template, symbol, period, params, priority, note, lot="0.01"):
    global rid
    rid += 1
    rows.append({"id": "M%03d" % rid, "family": family, "template": template,
                 "symbol": symbol, "period": period, "params": repr(params),
                 "priority": priority, "lot": lot, "note": note})


# ============ 1. PB応答曲面（3コア: USDJPY/GBPJPY/GOLD） ============
PB_CORES = {"USDJPY": "0.01", "GBPJPY": "0.01", "GOLD": "0.01"}
for sym, lot in PB_CORES.items():
    # ADX閾値 × RR比
    for adx, rr in product([15, 18, 25, 30], [1.5, 2.5, 3.0]):
        add("PB応答曲面_ADXxRR", "PullbackTrend", sym, "H4",
            {"ADX_Threshold": adx, "RR_Ratio": rr}, "S", "ADX閾値×RR比の格子", lot)
    # 環境フィルター傾き × ATR_SL_Mult
    for slope, atrm in product([0.8, 1.5, 2.0], [1.5, 2.5]):
        add("PB応答曲面_傾きxSL", "PullbackTrend", sym, "H4",
            {"MA_Slope_Min_ATR": slope, "ATR_SL_Mult": atrm}, "S", "環境フィルター強度×SL幅の格子", lot)
    # MTF合流（新軸: 上位足MAを変える）
    for htf, hma in product(["16408", "20"], [100, 200, 300]):  # 16408=D1
        add("PB_MTF合流変種", "PullbackTrend", sym, "H4",
            {"UseHigherTFFilter": True, "HigherTF": htf, "HigherTF_MA": hma},
            "A", "MTF合流フィルターのMA期間変種（既存採用の周辺探索）", lot)

# ============ 2. RSI応答曲面（3コア: EURUSD/USDJPY/GBPUSD） ============
RSI_CORES = {"EURUSD": "H1", "USDJPY": "H4", "GBPUSD": "H4"}
for sym, per in RSI_CORES.items():
    for ob, os_ in product([70, 75, 80], [20, 25, 30]):
        add("RSI応答曲面_OBxOS", "RSI_Reversal", sym, per,
            {"RSI_Overbought": ob, "RSI_Oversold": os_}, "S", "RSI閾値の格子")
    for rng in [0.10, 0.15, 0.25, 0.30, 0.40]:
        add("RSI応答曲面_レンジ閾値", "RSI_Reversal", sym, per,
            {"Range_Slope_Max_ATR": rng}, "S", "レンジフィルター閾値の細密格子")
    for bb in [2.0, 3.0, 3.5]:
        add("RSI応答曲面_BB", "RSI_Reversal", sym, per,
            {"BB_Deviation": bb}, "A", "BB偏差の格子")
    for sl, rr in product([40, 55], [90, 120]):
        add("RSI応答曲面_SLxTP", "RSI_Reversal", sym, per,
            {"StopLoss_Pips": sl, "TakeProfit_Pips": rr}, "A", "固定pips SL/TPの格子")

# ============ 3. VBO応答曲面（USDJPY） ============
for ch, sf in product([10, 15, 25, 30], [0.7, 0.8, 1.2, 1.5]):
    add("VBO応答曲面_チャネルxスクイーズ", "VolBreakout", "USDJPY", "H4",
        {"Channel_Period": ch, "Squeeze_Factor": sf}, "S", "チャネル期間×スクイーズ閾値の格子")
for tm in [1.5, 2.0, 2.5, 4.0]:
    add("VBO応答曲面_トレール", "VolBreakout", "USDJPY", "H4",
        {"Trail_Mult": tm}, "A", "トレール幅の格子")

# ============ 4. Carry応答曲面（AUDJPY） ============
for hm, tm in product([0.25, 0.5, 1.0, 1.25, 1.5], [100, 150, 250, 300]):
    add("Carry応答曲面_帯xMA", "Carry", "AUDJPY", "D1",
        {"Hyst_ATR_Mult": hm, "TrendMA_Period": tm}, "S", "ヒステリシス帯×トレンドMA期間の格子")

# ============ 5. SCA応答曲面（GOLD/USDJPY/GBPJPY） ============
SCA_CORES = {"GOLD": "0.01", "USDJPY": "0.01", "GBPJPY": "0.01"}
for sym, lot in SCA_CORES.items():
    for re_, te in product([6, 9, 12], [12, 15, 18]):
        if re_ >= te:
            continue
        add("SCA応答曲面_セッション窓", "SCA_EA", sym, "M15",
            {"RangeEndHour": re_, "TradeEndHour": te}, "S", "レンジ確定/取引終了時刻の格子", lot)
    for mnr, mxr in product([0.15, 0.30, 0.45], [0.8, 1.2, 1.5]):
        add("SCA応答曲面_レンジ幅", "SCA_EA", sym, "M15",
            {"MinRange_ATRd": mnr, "MaxRange_ATRd": mxr}, "S", "レンジ幅フィルターの格子", lot)
    for bm in [1.5, 2.5, 3.0]:
        add("SCA応答曲面_Boost倍率", "SCA_EA", sym, "M15",
            {"Boost_Mult": bm}, "A", "リバーサルBoost倍率の格子", lot)
    for fc in [18, 20]:
        add("SCA応答曲面_強制決済", "SCA_EA", sym, "M15",
            {"ForceCloseHour": fc}, "B", "強制決済時刻の格子", lot)

# ============ 6. 追加軸（既存6コアの残り応答曲面・新軸で総数を拡張） ============
for sym, lot in PB_CORES.items():
    for tma in [100, 150, 250, 300]:
        add("PB応答曲面_トレンドMA", "PullbackTrend", sym, "H4",
            {"TrendMA_Period": tma}, "A", "大局トレンドMA期間の格子", lot)
    for fe, se in product([10, 15], [40, 60]):
        add("PB応答曲面_EMA組", "PullbackTrend", sym, "H4",
            {"FastEMA_Period": fe, "SlowEMA_Period": se}, "B", "押し目EMA組の格子", lot)

for sym, per in RSI_CORES.items():
    for adx_on, adxth in product([True], [20, 25, 30]):
        add("RSI応答曲面_ADX追加", "RSI_Reversal", sym, per,
            {"UseADXFilter": adx_on, "ADX_Period": 14}, "B",
            "ADXフィルターを追加した変種（閾値はEA既定22.5固定・追加要否のみ検証）")
    for sw, db in product([2, 4, 5], [50, 80, 120]):
        add("RSI応答曲面_DP", "RSI_Reversal", sym, per,
            {"UseDoublePattern": True, "Swing_Lookback": sw, "DP_Pattern_Bars": db},
            "B", "ダブルパターン検出のパラメータ格子")

for sl, sf in product([30, 40, 70], [0.9, 1.0, 1.1]):
    add("VBO応答曲面_スクイーズ参照", "VolBreakout", "USDJPY", "H4",
        {"Squeeze_Lookback": sl, "Squeeze_Factor": sf}, "A", "スクイーズ参照期間×閾値の格子")
for atrm in [1.5, 2.5, 3.0]:
    add("VBO応答曲面_初期SL", "VolBreakout", "USDJPY", "H4",
        {"ATR_SL_Mult": atrm}, "B", "初期ストップ幅の格子")

for cd, em in product([0, 3, 5, 10], [0, 20, 40]):
    add("Carry応答曲面_退出クールダウン", "Carry", "AUDJPY", "D1",
        {"ReentryCooldown": cd, "ExitMA_Period": em}, "A",
        "退出後クールダウン×デュアルMA退出の格子（BTC/ETHで採用済み機構のAUDJPY移植）")

for sym, lot in SCA_CORES.items():
    for bb, sl_mode in product([0.0, 0.05, 0.10], [0, 1]):
        add("SCA応答曲面_バッファxSL方式", "SCA_EA", sym, "M15",
            {"Break_Buffer_ATRd": bb, "SL_Mode": sl_mode}, "B",
            "ブレイクバッファ×SL方式(レンジ反対端/ATR)の格子", lot)

# ============ 6b. さらに残り軸（総数を500案規模へ） ============
for sym, lot in PB_CORES.items():
    for slope, rr in product([0.8, 1.5, 2.0], [1.5, 2.5, 3.0, 3.5]):
        add("PB応答曲面_傾きxRR", "PullbackTrend", sym, "H4",
            {"MA_Slope_Min_ATR": slope, "RR_Ratio": rr}, "A", "環境フィルター強度×RR比の格子", lot)
    for flag in ["RequireBullishCandle", "UseMomentumConfirm", "UsePullbackQuality"]:
        add("PB_単一条件解除", "PullbackTrend", sym, "H4", {flag: False}, "B",
            "条件を1つだけ外した感度確認(%s)" % flag, lot)

for sym, per in RSI_CORES.items():
    for lb in [10, 30, 40]:
        add("RSI応答曲面_傾き参照期間", "RSI_Reversal", sym, per,
            {"Range_Slope_Lookback": lb}, "B", "レンジ判定の傾き参照期間の格子")
    add("RSI_ダブルパターン単独", "RSI_Reversal", sym, per, {"UseDoublePattern": True}, "B",
        "ダブルパターンのみ追加（既定値のまま）")

for sym, lot in SCA_CORES.items():
    for d1ma in [100, 200]:
        add("SCA_D1トレンドフィルター", "SCA_EA", sym, "M15",
            {"UseD1TrendFilter": True, "D1Trend_MA": d1ma}, "B",
            "D1トレンド方向フィルターを追加した変種", lot)
    add("SCA_複数回エントリー許可", "SCA_EA", sym, "M15", {"OneShotPerDir": False}, "B",
        "1日1方向1回の制約を外した変種", lot)
    add("SCA_逆指値事前設置", "SCA_EA", sym, "M15", {"UseStopOrders": True}, "B",
        "レンジ確定時に両端へ逆指値を事前設置する変種", lot)

for ap in [10, 20, 28]:
    add("Carry応答曲面_ATR期間", "Carry", "AUDJPY", "D1", {"ATR_Period": ap}, "B",
        "ヒステリシス帯計算に使うATR期間の格子")
for only in ["long", "short"]:
    add("VBO_単方向のみ", "VolBreakout", "USDJPY", "H4",
        {"AllowLong": only == "long", "AllowShort": only == "short"}, "B",
        "ロング/ショートいずれか一方のみ許可（%s限定）" % only)

# ============ 7. 新規データ源2件（プロジェクト自身が明記した「再開条件」） ============
add("新データ_BfxRevのETH移植", "BfxRev_EA", "ETHUSD", "D1", {},
    "S", "Bitfinexマージン(long建玉急減リバウンド)機構のBTC→ETH移植。"
        "btc_backlog4.mdで『ETHはデータ取得後』として保留されたまま未着手の項目。"
        "ETHUSD Bitfinexマージンロング建玉データを新規取得しBTC版と同一シグナル定義で検証。")
add("新データ_COTオーバーレイ_GOLD", "PullbackTrend", "GOLD", "H4", {"__cot_overlay__": "extreme_long"},
    "A", "CFTC COT(商品先物委員会建玉明細)のヘッジファンド買い越しが極端なときのみPB_GOLDのエントリーを許可"
        "するオーバーレイ。過去(btc_backlog4.md教訓)『COT週次n不足』は標準的シグナルとして使った際の反証で、"
        "既存エッジへのフィルターとしての利用は未検証。週次データのため対象はD1以上の低頻度戦略に限定")
add("新データ_COTオーバーレイ_AUDJPY", "Carry", "AUDJPY", "D1", {"__cot_overlay__": "extreme_long"},
    "A", "AUDのCOT建玉極端値をCarry_AUDJPYのエントリー許可条件に追加するオーバーレイ")
add("新データ_COTオーバーレイ_EURUSD", "RSI_Reversal", "EURUSD", "H1", {"__cot_overlay__": "extreme_short"},
    "B", "EURのCOT建玉極端値をRSI_EURUSDのオーバーレイに追加")

with open("ml/backlog5/candidates6.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=["id", "family", "template", "symbol", "period",
                                       "params", "priority", "lot", "note"])
    w.writeheader()
    w.writerows(rows)

print("total candidates (round2 response-surface):", len(rows))
for k, v in Counter(r["family"] for r in rows).most_common():
    print("  %-30s %d" % (k, v))
print("priority:", dict(Counter(r["priority"] for r in rows)))

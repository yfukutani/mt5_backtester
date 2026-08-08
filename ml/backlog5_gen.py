# -*- coding: utf-8 -*-
"""第5次バックログ: 新戦略候補〜500案の生成。

背景（本ファイル冒頭に記録・重複検証を避けるため）:
既存ドキュメント(rejected_strategies.md / new_plan_backlog.md / btc_backlog4.md 等)により
以下が既に大規模検証済みで再検証しない:
  - PB/VBO/RSIの他資産横展開個別ケース多数（SILVER/JP225/US100/OIL/USDCHF/NZDUSD/USDCAD等）
  - crypto alt(ADA/XRP/SOL/DOGE/LTC/BNB)のtrend-hold(824格子)・funding逆張り(FX72格子)・
    マルチソース合成(BK16格子) → 生存はBTC/ETHのみ確定
  - W1/MN長期軸、通貨強弱ローテ、ボラレジーム切替、カレンダー効果、ML/メタラベリング等
    （NEW_PLAN 1,020案で生存ゼロ確定）

本バックログは「未踏の(既存テンプレ×新市場)組合せ」+「新規メカニズム」に絞って構成する。
生存実績のあるテンプレ（PB=USDJPY/GBPJPY/GOLD、RSI=EURUSD/USDJPY/GBPUSD、
VBO=USDJPY(GBPJPYは弱含み)、SCA=GOLD/USDJPY/GBPJPY、CARRY=AUDJPY）を、
まだ試していない銘柄へ単発チャンピオンテスト（open_prices・全期間）で一次スクリーニングする。
"""
import csv
from collections import Counter

FX_CROSSES_REST = [
    "EURJPY", "CHFJPY", "CADJPY", "NZDJPY",              # 円クロス残り
    "AUDCAD", "AUDCHF", "AUDNZD", "NZDCAD", "NZDCHF", "CADCHF",
    "EURCAD", "EURCHF", "EURNZD", "EURAUD",
    "GBPAUD", "GBPCAD", "GBPCHF", "GBPNZD",
]
JPY_CROSSES = FX_CROSSES_REST[:4]
NON_JPY_CROSSES = FX_CROSSES_REST[4:]
EM_EXOTIC = ["USDMXN", "USDZAR", "USDTRY", "EURTRY", "EURZAR"]
METALS_OTHER = ["SILVER", "PLAT-OCT26", "PALL-SEP26", "HGCOP-SEP26"]
SOFTS = ["COCOA-SEP26", "COFFE-SEP26", "CORN-SEP26", "COTTO-DEC26", "SUGAR-OCT26", "WHEAT-SEP26"]
ENERGY = ["OILCash", "NGASCash"]
INDICES = ["US30Cash", "US500Cash", "US100Cash", "UK100Cash", "GER40Cash",
           "EU50Cash", "HK50Cash", "AUS200Cash", "FRA40Cash", "JP225Cash"]

rows = []
rid = 0


def add(family, template, symbol, period, tag, priority, note, lot="0.01"):
    global rid
    rid += 1
    rows.append({"id": "N%03d" % rid, "family": family, "template": template,
                 "symbol": symbol, "period": period, "tag": tag,
                 "priority": priority, "lot": lot, "note": note})


# --- 1. PB(PullbackTrend) 未踏市場 champion ---
for s in JPY_CROSSES:
    add("PB_未踏円クロス", "PullbackTrend", s, "H4", "std", "A", "円クロス残り4本")
for s in NON_JPY_CROSSES:
    add("PB_未踏クロス", "PullbackTrend", s, "H4", "std", "B", "非円クロス14本")
for s in METALS_OTHER:
    add("PB_他貴金属", "PullbackTrend", s, "H4", "std", "B", "SILVER以外の貴金属/銅")
for s in SOFTS + ENERGY:
    add("PB_ソフト/エネルギー", "PullbackTrend", s, "H4", "std", "C", "未踏コモディティ", lot="1.0")
for s in INDICES:
    add("PB_未踏指数", "PullbackTrend", s, "H4", "std", "C", "US100/JP225/OIL以外の指数", lot="1.0")

# --- 2. RSI(RSI_Reversal) 未踏市場 champion（実績3ペアの一般化テンプレ・最優先の一つ） ---
for s in JPY_CROSSES + ["AUDJPY"]:
    add("RSI_未踏円クロス", "RSI_Reversal", s, "H4", "std", "A", "円クロス（RSIは未検証）")
for s in NON_JPY_CROSSES:
    add("RSI_未踏クロス", "RSI_Reversal", s, "H4", "std", "A", "非円クロス14本")
for s in ["EURUSD", "USDJPY", "GBPUSD"]:
    add("RSI_D1変種", "RSI_Reversal", s, "D1", "std", "B", "既存採用ペアのD1版")
for s in EM_EXOTIC:
    add("RSI_EM逆張り", "RSI_Reversal", s, "H4", "std", "A", "新興国通貨レンジ回帰（新市場）")

# --- 3. VBO(VolBreakout) 未踏市場 champion ---
for s in JPY_CROSSES:
    add("VBO_未踏円クロス", "VolBreakout", s, "H4", "std", "A", "円クロス残り4本")
for s in NON_JPY_CROSSES:
    add("VBO_未踏クロス", "VolBreakout", s, "H4", "std", "B", "非円クロス14本")
for s in METALS_OTHER:
    add("VBO_他貴金属", "VolBreakout", s, "H4", "std", "B", "スクイーズ→拡大は貴金属と相性未検証")
for s in SOFTS + ENERGY:
    add("VBO_ソフト/エネルギー", "VolBreakout", s, "H4", "std", "C", "未踏コモディティ", lot="1.0")
for s in INDICES:
    add("VBO_未踏指数", "VolBreakout", s, "H4", "std", "C", "未踏指数", lot="1.0")

# --- 4. SCA(セッションORB) 未踏市場 — 唯一3ペア一般化実績のあるテンプレ・最優先 ---
sca_targets = (["EURJPY", "AUDJPY", "NZDJPY", "CHFJPY", "CADJPY",
                "EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDCAD", "USDCHF"]
               + NON_JPY_CROSSES + EM_EXOTIC)
for s in sca_targets:
    pr = "S" if s in ("EURJPY", "AUDJPY", "NZDJPY", "EURUSD", "GBPUSD") else "A"
    add("SCA_未踏市場", "SCA_EA", s, "M15", "std", pr, "セッションORB横展開（実績テンプレ）")

# --- 5. Carry(ヒステリシス) 高スワップ未踏市場（新市場） ---
for s in ["NZDJPY", "GBPNZD", "NZDUSD", "AUDUSD", "AUDNZD", "GBPAUD"]:
    add("Carry_FX高スワップ", "Carry", s, "D1", "std", "A", "AUDJPY以外の高スワップFX")
for s in EM_EXOTIC:
    add("Carry_EM高スワップ", "Carry", s, "D1", "std", "S", "新興国通貨キャリー（新市場・高スワップ）")
for s in ["SILVER", "PLAT-OCT26", "PALL-SEP26"]:
    add("Carry_貴金属", "Carry", s, "D1", "std", "C", "貴金属の長期トレンド保有")

# --- 6a. PB: H1時間軸変種（円クロス+非円クロスA/B優先） ---
for s in JPY_CROSSES + NON_JPY_CROSSES:
    add("PB_H1変種", "PullbackTrend", s, "H1", "std", "C", "H4がダメでも短TFで機能するか")
# --- 6b. RSI: ATR固定ストップ変種（全RSI未踏クロス対象） ---
for s in JPY_CROSSES + ["AUDJPY"] + NON_JPY_CROSSES + EM_EXOTIC:
    add("RSI_ATR固定SL", "RSI_Reversal", s, "H4", "atrstop", "C", "ATRベースSL/TP版（固定pipsの代替）")
# --- 6c. VBO: トレール幅変種（Trail_Mult 2.0） ---
for s in JPY_CROSSES + NON_JPY_CROSSES:
    add("VBO_トレール短縮", "VolBreakout", s, "H4", "trail20", "C", "Trail_Mult=2.0（利伸ばし短縮）")
# --- 6d. SCA: レンジ幅フィルター緩和変種（S/A対象） ---
for s in sca_targets:
    add("SCA_レンジ緩和", "SCA_EA", s, "M15", "range_wide", "B", "MinRange/MaxRangeを緩和した変種")
# --- 6e. Carry: ヒステリシス幅変種（新市場のみ） ---
for s in EM_EXOTIC + ["NZDJPY", "GBPNZD", "NZDUSD", "AUDUSD", "AUDNZD", "GBPAUD"]:
    add("Carry_ヒステリシス変種", "Carry", s, "D1", "hyst15", "B", "Hyst_ATR_Mult=1.5（帯を広げた変種）")

# --- 6f. SCA: リバーサルBoost OFF変種（純ブレイク版） ---
for s in sca_targets:
    add("SCA_Boost無し", "SCA_EA", s, "M15", "noboost", "B", "リバーサルBoostを外した純ブレイク版")
# --- 6g. PB: RR比変種（RR2.5・より伸ばす版） ---
for s in JPY_CROSSES + NON_JPY_CROSSES:
    add("PB_RR2.5", "PullbackTrend", s, "H4", "rr25", "C", "RR_Ratio=2.5（利大きめ）")
# --- 6h. VBO: チャネル短縮変種（Channel10） ---
for s in JPY_CROSSES + NON_JPY_CROSSES:
    add("VBO_チャネル短縮", "VolBreakout", s, "H4", "ch10", "C", "Channel_Period=10（短期ブレイク）")
# --- 6i. RSI: D1変種を全EM+円クロスへ拡張 ---
for s in JPY_CROSSES + EM_EXOTIC:
    add("RSI_D1拡張", "RSI_Reversal", s, "D1", "std", "C", "D1版の追加銘柄")

# --- 6j. PB: ADX緩和を非円クロスにも拡張 ---
for s in NON_JPY_CROSSES:
    add("PB_ADX緩和", "PullbackTrend", s, "H4", "noadx", "C", "ADXフィルター無し（非円）")
# --- 6k. RSI: BB偏差3.0の緩和版（全RSI未踏対象） ---
for s in JPY_CROSSES + ["AUDJPY"] + NON_JPY_CROSSES + EM_EXOTIC:
    add("RSI_BB緩和", "RSI_Reversal", s, "H4", "bb30", "C", "BB_Deviation=3.0（バンド拡張）")
# --- 6l. PB/VBOをEM通貨にも拡張（未踏メカニズム×新市場の組合せを増やす） ---
for s in EM_EXOTIC:
    add("PB_EM", "PullbackTrend", s, "H4", "std", "B", "新興国通貨への押し目買い横展開")
for s in EM_EXOTIC:
    add("VBO_EM", "VolBreakout", s, "H4", "std", "B", "新興国通貨へのボラブレイク横展開")
# --- 6m. RSIを貴金属/ソフト/エネルギーにも拡張 ---
for s in METALS_OTHER + SOFTS + ENERGY:
    add("RSI_コモディティ", "RSI_Reversal", s, "H4", "atrstop", "C", "コモディティのレンジ回帰", lot="1.0")

# --- 6n. RSI: 未踏クロスのH1変種（PBのH1変種と対の軸） ---
for s in JPY_CROSSES + ["AUDJPY"] + NON_JPY_CROSSES:
    add("RSI_H1変種", "RSI_Reversal", s, "H1", "std", "C", "H1版（RSIのネイティブ時間軸候補）")
# --- 6o. Carry: 負スワップでも保有する逆張りキャリー（EM通貨、仮説=スワップ以外の平均回帰） ---
for s in EM_EXOTIC:
    add("Carry_逆スワップ", "Carry", s, "D1", "negswap", "C", "スワップ条件を外した純トレンド保有版")

# --- 7. パラメータ変種（S/A優先候補のロバスト性追加確認・水増しでなく実質的な追加軸） ---
# RSI: レンジフィルター閾値を2水準（現行0.2/緩和0.35）で全A優先クロスに追加
rsi_a_targets = JPY_CROSSES + ["AUDJPY"] + NON_JPY_CROSSES + EM_EXOTIC
for s in rsi_a_targets:
    add("RSI_フィルター緩和", "RSI_Reversal", s, "H4", "range035", "B", "レンジフィルターを緩和した変種")
# VBO: スクイーズOFF版（純ブレイクアウト）を全候補で追加
vbo_targets = JPY_CROSSES + NON_JPY_CROSSES
for s in vbo_targets:
    add("VBO_スクイーズOFF", "VolBreakout", s, "H4", "nosqueeze", "B", "スクイーズ条件を外した純粋ブレイク")
# PB: ADX無しの緩和版を円クロスのみ追加確認
for s in JPY_CROSSES:
    add("PB_ADX緩和", "PullbackTrend", s, "H4", "noadx", "B", "ADXフィルターを外した緩和版")

with open("ml/backlog5/candidates.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=["id", "family", "template", "symbol", "period",
                                       "tag", "priority", "lot", "note"])
    w.writeheader()
    w.writerows(rows)

print("total candidates:", len(rows))
print("by family:")
for k, v in Counter(r["family"] for r in rows).most_common():
    print("  %-22s %d" % (k, v))
print("by priority:", dict(Counter(r["priority"] for r in rows)))

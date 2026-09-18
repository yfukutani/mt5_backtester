"""第17報ラウンド `ml/fxqual5` — SCA の発注時間帯フィルタを、初めて MT5 で測る。

【なぜこのラウンドがあるか — 「結論だけ出てバックテストが無い」案を見つけた】
`docs/oanda_fx_last_axes_20260915.md` §1 は、**取引ログを発注時刻で切り直して**
次を得ている（SCA GBPJPY・単位は円）:

| 発注時刻（サーバー時刻） | IS純益 | OOS純益 |
|---:|---:|---:|
| **09時** | **−7,646** | **−13,093** |
| 10時 | +27,652 | +22,144 |
| 11時 | +53,767 | +33,168 |

**09時のブレイクは両窓とも赤字。** IS だけを見て「09時を切る」と決め、それを OOS に
当てて枠純益 +31.0%（+13,093円）になる、という筋である。当時の記述は
「fxrisk3 の測定が終わり次第、MT5 の確認runを1本取る」だった。

**その確認runは1本も取られていない。**
全ラウンドの `results.csv` を調べたところ `ScaFilHourFrom` は **44run すべて −1（無効）**
であり、この案が MT5 上で走ったことは一度も無い。
**プロジェクトのルール（採用の最終判断は必ずバックテスト）を満たしていない。**

【取引ログの切り直しは、バックテストの代わりにならない】
切り直しは「**その注文が実際に出なかったら何が起きたか**」を教えない。SCA は
1日1発（`scaDone`）の設計で、`RevBoost`（GBPJPY は 6.0 倍）もある。
09時の発注を止めた日に、同じ日の10時・11時の挙動が変わりうる。
だから **X002 を「反証試験」として置く**（下記）。

【事前の予想（後付けを避けるため先に書く）】
- **X001（SCA GBPJPY の09時除外）**: 切り直しの見積もりどおりなら
  枠純益 **OOS +13,093 / IS +7,646** 前後。ブック全体で **単利月利 +0.02〜0.05pt**。
  **ただし一致しない可能性のほうが興味深い**（下記 X002 と合わせて読む）。
- **X002（SCA 2枠に同じ時間帯フィルタ）**: `ml/fxqual5/sca_hours.py` で V000 の取引ログを
  配賦修正後に切り直した結果、**SCA USDJPY の09時は両窓とも黒字**である
  （OOS **+634** / IS **+6,431**）。つまり 10-11時の窓を USDJPY にも当てると
  **その分だけ損をするはず**である。
  **X002 − X001 の SCA USDJPY 枠の差が −634（OOS）/ −6,431（IS）にならなければ、
  切り直しは実測と一致しない。** これがこのラウンドの本当の検算である。

  > `oanda_fx_last_axes_20260915.md` は「B2 はこの枠では何も切らない（±0）」と書いているが、
  > それは B2 を**枠ごとに「IS で黒字の時間帯」と定義**したからで、
  > **GBPJPY 由来の 10-11時 をそのまま USDJPY に当てた場合ではない。**
  > X002 は後者である。混同しないこと。
- **X003（11時のみ）**: 両窓で最も強い時間帯だけを残す形。**深い後付けであり、
  両窓で良くなっても採らない。** 勾配を見るためだけに置く。効き幅は X001 より大きく出るはず。
- **X004（V001 ＋ X001 の合成）**: 両窓で符号が揃った改善だけを重ねた構成。
  素朴な足し算なら **OOS +15,000 / IS +11,000** 前後だが、
  枠が違うので相互作用は無いはず（枠ゲートは枠内で閉じている）。**足し算が当たると予想する。**

【効き幅の見積もり】
最良でも **単利月利 +0.05pt**。対照は OOS 0.428% であり、目標6%には **桁が2つ足りない。**
これは測る前に書いている。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROOT = Path(__file__).resolve().parent

_spec = importlib.util.spec_from_file_location(
    "_m3", REPO / "ml" / "fxmargin3" / "measure.py")
m3 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m3)

ROOT.mkdir(parents=True, exist_ok=True)
m3.RUN_DIR = ROOT / "runs"
m3.CONFIG_DIR = ROOT / "configs"
m3.DEAL_DIR = ROOT / "run_deals"
m3.OUT = ROOT / "results.csv"
m3.LOG = ROOT / "measure.log"
m3.CAP_LOG = True

# fxqual1〜4 と同一の窓。ここを変えると前ラウンドと並べられない。
m3.WINDOWS = {
    "OOS": ("2016.11.09", "2021.06.20", 55.0),
    "IS":  ("2021.06.20", "2026.06.20", 60.0),
}
WINS = ("OOS", "IS")

PARAMS = {
    "GlobalLotMult": 1,
    "MarginCapPct": 0,
    "BrokerMaxLot": 0,
    "FxRiskMask": 0, "FxRiskPct": 0.5, "FxRiskRefCap": 0,
    "RefCap_PB_USDJPY": 78000, "RefCap_PB_GBPJPY": 78000, "RefCap_CARRY": 78000,
    "TagDealTriggers": True,
    "PairSkipAtStop": False, "PairEqualNotional": False,
    "PairMaxHoldBars": 0, "PairEntryZOv": 0.0,
    "RsiMechMask_UJ": 0, "RsiMechMask_EU": 0, "RsiMechMask_GU": 0,
    "PbDiagCounters": True,
    "PbAdxThr_UJ": 0.0, "PbSlopeATR_UJ": 0.0,
    "PbAdxThr_GJ": 0.0, "PbSlopeATR_GJ": 0.0,
    # SCA の入口フィルタ（第14報で入っている）。**全案で明示的に書く。**
    "ScaFilMask": 0, "ScaFilRangeMin": 0.0,
    "ScaFilHourFrom": -1, "ScaFilHourTo": -1, "ScaFilBuyOnly": False,
}
for _k in ("BFXREV", "BTC_FUND", "CARRY", "ETH", "PAIR", "PB_GBPJPY", "PB_GOLD",
           "PB_USDJPY", "RSI_EURUSD", "RSI_GBPUSD", "RSI_USDJPY", "SCA_GBPJPY",
           "SCA_GOLD", "SCA_USDJPY", "VBO"):
    PARAMS[f"Mult_{_k}"] = 1.0


def t(**over):
    p = dict(PARAMS)
    for k, v in over.items():
        p[k] = v
    return p


# RSI USDJPY の機構ゲート: R=1 / B=2 / D=4 の OR に対する許可マスク。
# 124 ＝ R単独(1)・B単独(2)を落とす（fxqual3 V001・両窓＋の唯一の採用候補）。
NO_SINGLE_RB = 124

PROPOSALS = [
    ("X000", "fxqual3/V000",
     "対照: SCA フィルタ全部無効。V000/W000 と1円まで一致すること", PARAMS),

    # --- 本命: 一度も MT5 で走っていない案 -----------------------------------
    ("X001", "X000",
     "SCA GBPJPY: 09時の発注を除外（10-11時のみ）。切り直しでは枠 +31.0%",
     t(ScaFilMask=2, ScaFilHourFrom=10, ScaFilHourTo=11)),

    # --- 反証試験: 切り直しは「SCA USDJPY では何も切らない」と言っている ------
    # X002 と X001 の SCA USDJPY 枠の差が 0 でなければ、切り直しは実測と一致しない。
    ("X002", "X001",
     "SCA 2枠に同じ時間帯フィルタ。切り直しなら USDJPY 枠は −634(OOS)/−6,431(IS) のはず（検算）",
     t(ScaFilMask=3, ScaFilHourFrom=10, ScaFilHourTo=11)),

    # --- 勾配だけ見る。両窓で良くても採らない（深い後付けだから）--------------
    ("X003", "X000",
     "SCA GBPJPY: 11時のみ（両窓で最強の時間帯だけ残す・深い後付けなので採らない）",
     t(ScaFilMask=2, ScaFilHourFrom=11, ScaFilHourTo=11)),

    # --- 合成: 両窓で符号が揃った改善だけを重ねる ----------------------------
    ("X004", "X001",
     "合成: RSI USDJPY 機構ゲート(V001) ＋ SCA GBPJPY 09時除外",
     t(RsiMechMask_UJ=NO_SINGLE_RB, ScaFilMask=2, ScaFilHourFrom=10, ScaFilHourTo=11)),
]

ORDER = ["X000", "X001", "X002", "X004", "X003"]


def main():
    for d in (m3.RUN_DIR, m3.CONFIG_DIR, m3.DEAL_DIR):
        d.mkdir(parents=True, exist_ok=True)
    if not m3.acquire_lock():
        return
    done = m3.load_done()
    idx = {p: i for i, p in enumerate(ORDER)}
    props = sorted(PROPOSALS, key=lambda x: idx.get(x[0], 99))
    jobs = [(pid, base, desc, params, w)
            for (pid, base, desc, params) in props
            for w in WINS if (pid, w) not in done]
    if not jobs:
        print("完了済みです")
        return
    import ctypes
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    try:
        m3.log(f"FXQUAL5_START jobs={len(jobs)} SCA 発注時間帯フィルタ4案＋対照")
        for pid, base, desc, params, window in jobs:
            row = m3.run(pid, base, desc, params, window)
            m3.append_result(row)
            if pid == "X000" and row.get("status") != "OK":
                m3.log("FXQUAL5_ABORT 対照が失敗した。回帰試験が取れないので中止")
                return
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        (m3.ROOT / "measure.lock").unlink(missing_ok=True)
    m3.log(f"FXQUAL5_END -> {m3.OUT}")


if __name__ == "__main__":
    main()

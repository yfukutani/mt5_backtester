"""第17報ラウンド `ml/fxqual4` — PullbackTrend 入口の「締める」側を初めて測る。

【このラウンドの出発点】
第16報（`ml/fxqual3`）で `PbDiagCounters` を初めて回し、PB 入口8条件 AND の
**leave-one-out**（その条件以外の7つが全部成立していたバー数 − 全条件成立バー数
＝ その条件だけで落ちたバー数）を両窓で取った。

| 枠 | 窓 | ALL | 0 up | 1 armed | 2 >fastEMA | 3 陽線 | 4 >高値[2] | 5 ADX | 6 slope | 7 D1MA200 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| PB USDJPY | OOS | 37 | 0 | 53 | 7 | 0 | 36 | 67 | **239** | 12 |
| PB USDJPY | IS | 104 | 0 | 170 | 20 | 1 | 89 | 172 | **262** | 10 |
| PB GBPJPY | OOS | 65 | 0 | 36 | 9 | 0 | 41 | 53 | **228** | 1 |
| PB GBPJPY | IS | 37 | 0 | 58 | 8 | 1 | 30 | 39 | **239** | 0 |

**律速は条件6（trendMA の傾き ≥ k×ATR）である。** 次点の ADX の 3〜4倍強い。
第14報で ADX を 30→22.5 に緩めても取引が5件しか増えなかったのはこれで説明がつく。
**推測ではなく計測でこの結論が出たのは今回が初めて。**

【では緩めればよいのか — 逆である。第14報が既に測っている】
| 案 | 変更 | 枠純益 OOS | 枠純益 IS |
|---|---|---:|---:|
| Q013 | PB GBPJPY slope 1.5→1.2 | 22,738→21,698 | 22,291→**13,210** |
| Q016 | PB USDJPY slope 1.2→0.9 | −1,812→**−9,125** | 22,267→**12,372** |

**緩めると両窓で悪化する。** つまり slope は「絞りすぎている無駄な条件」ではなく、
**効いている条件**である。勾配は反対を向いている。

> **このラウンドで測るのは、その反対側＝「締める」方向である。**
> 第14報・第15報・第16報を通して、PB の slope を**上げた**実測は1件も無い。

【事前の予想（後付けを避けるため先に書く）】
- PB USDJPY は **OOS で唯一マイナスの FX 枠**（−1,812円 / 18deal）である。
  取引が少ないのは分かっていたが、第16報まで「頻度が律速」と読んでいた。
  LOO と Q016 を合わせると、**頻度ではなく質**の問題と読むほうが整合する。
  slope を 1.2→1.5 にすると **OOS の負けが浅くなる可能性がある**が、
  18deal が 10deal 台前半に落ちるので、**統計的にはほぼ何も言えない**。
- PB GBPJPY は両窓とも +22,000円台で既に黒字。締めれば **取引がさらに減るだけ**で
  金額は横ばいか微減と予想する。
- ADX を締める側（UJ 27.5→32.5・GJ 30→35）は、LOO では slope の 1/3 の強さなので
  **効き幅も小さい**と予想する。
- **効き幅の桁の見積もり: 単利月利 ±0.02pt。** PB 2枠の合計は OOS +20,926円で
  ブック全体（+117,843円）の 18% しかなく、その中の入口閾値をひと刻み動かしただけで
  動く額は数千円である。**月利6%に対しては無に等しい。**

【このラウンドが安い理由】
**新しい input を1つも使わない。** `PbSlopeATR_UJ/_GJ`・`PbAdxThr_UJ/_GJ` は
第14報で既に EA に入っており、走行中の `.ex5` がそのまま受け付ける。
**EA の変更もコンパイルも不要**で、回帰リスクがゼロである。
（W000 が fxqual3 の V000 と1円まで一致することで、それを実測で示す。）
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
# PB の律速カウンタは CapLogFile に相乗りして出る。cap 自体は MarginCapPct=0 で無効。
# 締めた構成でも LOO を取り直せるので、閾値を動かしたとき律速が入れ替わるかが見える。
m3.CAP_LOG = True

# fxqual1 / fxqual2 / fxqual3 と同一の窓。ここを変えると前ラウンドと並べられない。
m3.WINDOWS = {
    "OOS": ("2016.11.09", "2021.06.20", 55.0),
    "IS":  ("2021.06.20", "2026.06.20", 60.0),
}
WINS = ("OOS", "IS")

# fxqual3 の V000 と同一（本番現行サイジング＋計装ON）。差は PB の入口閾値だけ。
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
    # 第14報で入った PB 入口の上書き（0=現行）。**全案で明示的に書く。**
    "PbAdxThr_UJ": 0.0, "PbSlopeATR_UJ": 0.0,
    "PbAdxThr_GJ": 0.0, "PbSlopeATR_GJ": 0.0,
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


PROPOSALS = [
    ("W000", "fxqual3/V000",
     "対照: PB 入口の上書きを全部0（現行）。V000/T000/Q000 と1円まで一致すること",
     PARAMS),

    # --- 本命: slope を締める（この軸は一度も測っていない）------------------
    ("W001", "W000", "PB USDJPY: slope下限 1.2 -> 1.5ATR（律速を1刻み締める）",
     t(PbSlopeATR_UJ=1.5)),
    ("W002", "W000", "PB USDJPY: slope下限 1.2 -> 1.8ATR（2刻み。取引は半減するはず）",
     t(PbSlopeATR_UJ=1.8)),
    ("W003", "W000", "PB GBPJPY: slope下限 1.5 -> 1.8ATR",
     t(PbSlopeATR_GJ=1.8)),
    ("W004", "W000", "PB GBPJPY: slope下限 1.5 -> 2.1ATR",
     t(PbSlopeATR_GJ=2.1)),

    # --- 次点: ADX を締める（LOO では slope の 1/3 の強さ。効き幅も小さいと予想）---
    ("W005", "W000", "PB USDJPY: ADX閾値 27.5 -> 32.5（緩める側 Q015 は両窓で割れた）",
     t(PbAdxThr_UJ=32.5)),
    ("W006", "W000", "PB GBPJPY: ADX閾値 30 -> 35（緩める側 Q011/Q012 は無風だった）",
     t(PbAdxThr_GJ=35.0)),

    # --- 合成: 2枠とも1刻み締める -------------------------------------------
    ("W007", "W001", "合成: PB 2枠とも slope を1刻み締める（UJ 1.5 ＋ GJ 1.8）",
     t(PbSlopeATR_UJ=1.5, PbSlopeATR_GJ=1.8)),
]

# 対照が最初。次に本命の slope 4件、それから ADX、最後に合成。
# 途中で止まっても判断に効く数字から埋まる並びにする。
ORDER = ["W000", "W001", "W003", "W002", "W004", "W007", "W005", "W006"]


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
        m3.log(f"FXQUAL4_START jobs={len(jobs)} PB入口を締める7案＋対照")
        for pid, base, desc, params, window in jobs:
            row = m3.run(pid, base, desc, params, window)
            m3.append_result(row)
            if pid == "W000" and row.get("status") != "OK":
                m3.log("FXQUAL4_ABORT 対照が失敗した。回帰試験が取れないので中止")
                return
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        (m3.ROOT / "measure.lock").unlink(missing_ok=True)
    m3.log(f"FXQUAL4_END -> {m3.OUT}")


if __name__ == "__main__":
    main()

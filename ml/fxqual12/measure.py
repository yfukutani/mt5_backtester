"""第23報 第12ラウンド `ml/fxqual12` — SCA の退出(TP)・入口(overshoot)・重み。

【このラウンドが何を閉じるか】
Codex の棚卸し（`docs/codex_oafx_inventory_20260919.md`）が「未実装・未測定」として
残した軸は3つだった。うち SCA の2つ（**TP の R倍率** と **入口 overshoot 上限**）を
EA に実装して測る。残る1つ（RSI の機構別退出）は改修が大きいので次ラウンド。

そこに、**本ラウンドで新しく見つけた軸**を1つ足す（下記 Group C）。

【測る前に分かったこと — `ml/fxqualexec` の E000 deal ログを読んだ】

(1) **SCA の TP(2R) はほとんど発火しない。**

| 窓 | 枠 | 強制決済(22時) | SL | **TP** |
|---|---|---:|---:|---:|
| OOS | SCA UJ | 90.3% | 8.7% | **1.0%** |
| OOS | SCA GJ | 60.1% | 32.9% | **7.1%** |
| IS  | SCA UJ | 82.7% | 15.0% | **2.3%** |
| IS  | SCA GJ | 66.9% | 27.1% | **6.0%** |

**実現 R倍率の最大値は TP の 2.000R ちょうどで、2R を超えた取引は 4窓×枠で1件も無い。**
→ **rr を上げる方向は 93〜99% の取引に対して no-op。** 効くのは「いま 2R で
利確している 1〜7%」だけで、その先が伸びるか萎むかは測らないと分からない。
→ **rr を下げる方向**は、実現 R倍率を k で頭打ちにした下界が両窓ともマイナス
（OOS GJ 426,099 → −304,632 @1R / IS GJ −719,706 → −1,767,783 @1R）。
この下界は「ピークで切れば拾えたはずの分」を無視しているので過小評価だが、
**第17報（`ml/fxqual7`・建値ストップ）で「利益を出している当の取引の伸びを切っていた」
と同じ機構**なので、事前期待はマイナスに置く。

(2) **SL の滑りは無い。** SL 退出の実現 R倍率は平均 −1.001〜−1.005R（最悪 −1.035R）。
「損失が想定より大きい」という漏れは存在しない。**この仮説はここで閉じる。**

(3) 🔴 **SCA GBPJPY は1取引あたりの期待値がほぼゼロである。**
`R = FxRiskPct × equity` なので、全複利では **1取引の質は実現 R倍率**で測るのが正しい
（円建てでは「いつ勝ったか」が混ざる）。9枠を R倍率で並べると:

| 枠 | n(OOS) | 平均R(OOS) | ΣR(OOS) | n(IS) | 平均R(IS) | ΣR(IS) |
|---|---:|---:|---:|---:|---:|---:|
| pb_gj | 15 | **+1.117** | +16.8 | 13 | **+1.724** | +22.4 |
| pb_uj | 13 | +0.339 | +4.4 | 49 | +0.524 | +25.7 |
| rsi_gu | 62 | +0.493 | +30.6 | 65 | +0.286 | +18.6 |
| rsi_uj | 68 | +0.295 | +20.1 | 90 | +0.238 | +21.4 |
| rsi_eu | 269 | +0.047 | +12.6 | 275 | +0.066 | +18.1 |
| sca_uj | 103 | +0.007 | +0.7 | 214 | +0.061 | +13.1 |
| **sca_gj** | **621** | **−0.016** | **−10.2** | **683** | **+0.018** | **+12.5** |

**SCA GBPJPY は全 deal の 48% を出しながら、1取引の期待値が ±0.02R しかない。**
それでも円建てでは OOS **+426,099**（ブックの30%）を計上している。
**つまりこの枠の円建て損益は「勝ちが equity の大きい時期に来たか」でほぼ決まっている。**
IS では同じ枠が **−719,706** になる。**符号が窓で割れるのは、これが理由である。**

→ **Group C: この枠の重みを下げたらブックはどうなるか。**
`Mult_SCA_GBPJPY` は `LotRisk()` の中で risk% ベースロットに掛かるので
（EA `return Clamp(..., base*GlobalLotMult*S[i].lotMult*factor, i)`）、**EA 改修は要らない。**
⚠️ 第22報の発見「複利では枠別損益はブックの分解ではない」があるので、
**「−426,099 になるはず」とは予測しない。** 実測する。

【事前の予想 — 外れたら記録する】
- **Q001〜Q003（重みを下げる）**: OOS は**悪化**、IS は**改善**、DD は**両窓で低下**と予想。
  OOS が判定窓なので、**単体では棄却になる**と予想する。
- **Q004（重みを下げて倍率で買い戻す）**: ここが本命。DD を同じにしたときに
  月利が上がるかどうか。**五分五分**と予想する。
- **Q005/Q007（rr を上げる）**: **ほぼ 0**（no-op が 93〜99%）。
- **Q006/Q008（rr を下げる）**: **両窓マイナス**と予想。
- **Q009〜Q012（overshoot 上限）**: **ほぼ 0**と予想。
  overshoot が大きい取引は `dist` が大きく、risk% では**ロットが小さい**。
  つまりこの上限は「重みの軽い取引」を落とす。`ScaFilRangeMin`（重い取引を落とす）とは
  **逆向き**なので、ブックへの効きは一桁小さいはずである。
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

m3.WINDOWS = {
    "OOS":  ("2016.11.09", "2021.06.20", 55.0),
    "IS":   ("2021.06.20", "2026.06.20", 60.0),
    "FULL": ("2016.11.09", "2026.06.20", 115.0),
}
WINS = ("OOS", "IS")

BASE = {
    "BrokerMaxLot": 0,
    "TagDealTriggers": True,
    "PairSkipAtStop": False, "PairEqualNotional": False,
    "PairMaxHoldBars": 0, "PairEntryZOv": 0.0,
    "RsiMechMask_UJ": 0, "RsiMechMask_EU": 0, "RsiMechMask_GU": 0,
    "PbDiagCounters": True,
    "PbAdxThr_UJ": 0.0, "PbSlopeATR_UJ": 0.0,
    "PbAdxThr_GJ": 0.0, "PbSlopeATR_GJ": 0.0,
    "ScaFilMask": 0, "ScaFilRangeMin": 0.0,
    "ScaFilHourFrom": -1, "ScaFilHourTo": -1, "ScaFilBuyOnly": False,
    "ScaBETriggerR": 0.0, "ScaBELockR": 0.0, "ScaBEMask": 0,
    "ScaRevOnlyMask": 0, "ScaRevDropMask": 0,
    "PbArmMaxBars_UJ": 0, "PbArmMaxBars_GJ": 0, "PairRequireZTurning": False,
    "MarginCapPct": 0,
    # 第23報の新 input（既定 0 で現行と完全同値でなければならない）
    "ScaRR_UJ": 0.0, "ScaRR_GJ": 0.0,
    "ScaOvsATR_UJ": 0.0, "ScaOvsATR_GJ": 0.0,
}
for _k in ("BFXREV", "BTC_FUND", "CARRY", "ETH", "PAIR", "PB_GBPJPY", "PB_GOLD",
           "PB_USDJPY", "RSI_EURUSD", "RSI_GBPUSD", "RSI_USDJPY", "SCA_GBPJPY",
           "SCA_GOLD", "SCA_USDJPY", "VBO"):
    BASE[f"Mult_{_k}"] = 1.0

# 採用候補3件（第22報）。
CAND = {
    "RsiMechMask_UJ": 124,
    "PbSlopeATR_UJ": 1.40,
    "ScaFilMask": 1, "ScaFilRangeMin": 0.0048,
}

# 全複利・倍率1・候補3件 ＝ `ml/fxqual10` の G005 ＝ `ml/fxqualexec` の E000。
COMP1 = dict(BASE, FxRiskMask=31, FxRiskPct=0.5, FxRiskRefCap=0, GlobalLotMult=1,
             RefCap_PB_USDJPY=0, RefCap_PB_GBPJPY=0, RefCap_CARRY=0, **CAND)


def t(**over):
    p = dict(COMP1)
    p.update(over)
    return p


PROPOSALS = [
    # ⚠️ 回帰試験。新 input 4本が既定で inert であることの唯一の確認。
    #    **OOS +1,431,459 / IS +4,845,523 と1円まで一致しなければならない。**
    #    ずれたら以降の12案はすべて解釈不能なので、その場で止めて原因を書く。
    ("Q000", "fxqualexec/E000",
     "対照＝回帰試験: 新 input 4本が既定0で inert か（E000 と1円まで一致すること）",
     COMP1),

    # --- Group C: SCA GBPJPY の重み（既存 input・EA 改修不要）---
    ("Q001", "Q000", "SCA GBPJPY の重み 0.5（1取引の期待値が ±0.02R しかない枠）",
     t(Mult_SCA_GBPJPY=0.5)),
    ("Q002", "Q000", "同 0.25", t(Mult_SCA_GBPJPY=0.25)),
    ("Q003", "Q000", "同 0.0（枠を実質止める。ブックの分解になっているかの反証点）",
     t(Mult_SCA_GBPJPY=0.0)),
    ("Q004", "Q002", "**本命**: 重み 0.25 ＋ 倍率2（下がったDDを倍率で買い戻す）",
     t(Mult_SCA_GBPJPY=0.25, GlobalLotMult=2)),

    # --- Group A: TP の R倍率（新 input）---
    ("Q005", "Q000", "SCA GBPJPY の TP を 3.0R（上げる方向・93%は no-op のはず）",
     t(ScaRR_GJ=3.0)),
    ("Q006", "Q000", "同 1.5R（下げる方向・下界はマイナス）", t(ScaRR_GJ=1.5)),
    ("Q007", "Q000", "SCA USDJPY の TP を 3.0R（99%は no-op のはず）", t(ScaRR_UJ=3.0)),
    ("Q008", "Q000", "同 1.5R", t(ScaRR_UJ=1.5)),

    # --- Group B: 入口 overshoot 上限（新 input）---
    # GBPJPY は buffer=0 なので下限の制約が無い。USDJPY は buffer=0.10×ATR。
    ("Q009", "Q000", "SCA GBPJPY の overshoot 上限 0.15×ATR", t(ScaOvsATR_GJ=0.15)),
    ("Q010", "Q000", "同 0.35×ATR（緩い側・ほぼ no-op の錨）", t(ScaOvsATR_GJ=0.35)),
    ("Q011", "Q000", "SCA USDJPY の overshoot 上限 0.20×ATR（buffer 0.10 の直上）",
     t(ScaOvsATR_UJ=0.20)),
    ("Q012", "Q000", "同 0.45×ATR（緩い側の錨）", t(ScaOvsATR_UJ=0.45)),
]

# 回帰試験 → Group C（EA 非依存で情報量が一番大きい）→ TP → overshoot の順。
# 途中で止まっても「価値の高い側」から埋まる。
ORDER = ["Q000", "Q001", "Q002", "Q003", "Q004",
         "Q005", "Q006", "Q007", "Q008",
         "Q009", "Q010", "Q011", "Q012"]


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
        m3.log(f"FXQUAL12_START jobs={len(jobs)} SCAのTP・overshoot・重み")
        for pid, base, desc, params, window in jobs:
            row = m3.run(pid, base, desc, params, window)
            m3.append_result(row)
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        (m3.ROOT / "measure.lock").unlink(missing_ok=True)
    m3.log(f"FXQUAL12_END -> {m3.OUT}")


if __name__ == "__main__":
    main()

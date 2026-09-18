"""第17報ラウンド `ml/fxqual6` — W001 は本物か、それとも4取引のまぐれか。

【何が起きたか】
`ml/fxqual4` の **W001（PB USDJPY の slope 下限 1.2 → 1.5ATR）**が、
このテーマ全体で最大の効果を出した:

| 窓 | ブック純益 | Δ | 単利月利 | 残高DD | equity DD |
|---|---:|---:|---:|---:|---:|
| OOS | +125,077 | **+7,234** | 0.428% → **0.455%** | 5.27% → **4.65%** | 7.04% → **6.23%** |
| IS | +258,290 | **+2,845** | 0.852% → **0.861%** | 7.35% → 7.55% | 7.51% → 7.66% |

**枠内で閉じている**（PB USDJPY 以外の枠の差は ±52円）。
**PB USDJPY は OOS で唯一マイナスだった枠が黒字になった**（−1,812 → **+5,422**）。
しかも **OOS では DD も下がっている**。緩める側（1.2→0.9）は第14報で両窓悪化、
締めすぎ（1.8）も両窓悪化なので、**1.5 は両側を測った上での内点**である。

【しかし、採用してはいけない】
**OOS の PB USDJPY は 8 deal ＝ 4往復である。** 対照の 18 deal（9往復）から
5往復を落として、残り4往復が +5,422円 を出した、というのがこの数字の中身である。

> Codex（2026-09-19）:「PBの正の結果は、少なくとも合計30〜60件級の再検証が
> ない限り採用しないのが安全です。」

**4取引の改善は、両窓で符号が揃っていても採用根拠にならない。**
IS 側は 22往復で +2,816（基準 +22,267 の +12.6%）と、ずっと控えめである。

【このラウンドで何を決めるか — 台地か、尖りか】
**1.5 の周りを細かく刻む。**

- **台地**（1.35〜1.65 のどこを取っても PB USDJPY の OOS が黒字）なら、
  閾値の位置ではなく**「もっと締める」という方向**が効いている。採用を検討できる。
- **尖り**（1.5 だけ黒字で 1.45 や 1.55 は赤字）なら、**4取引のまぐれ**である。棄却する。

**この判定は「良い値を探す」ためではない。** むしろ**棄却するための試験**である。
グリッドを細かくして最良点を選ぶのは、まさに第16報で V007 が示した失敗の形なので、
**「最良の刻みを採る」ことは最初からしない。**

【事前の予想】
**尖りだと予想する。** 4往復の損益が、ひと刻み動かすだけで符号を変えないほうが不自然である。
外れて台地になれば、それは W001 を採用候補に上げる根拠になる。
**予想を先に書いておくのは、外れたときに後付けできなくするためである。**

【合成（W008）について】
`V001`（RSI USDJPY の機構ゲート）と `W001`（PB USDJPY の slope）は**別の枠**である。
`ml/fxqual4` の W007 が **W001 と W003 の枠別Δを完全に足し算で再現した**ので
（OOS +7,234 − 19,966 = −12,732・1円まで一致）、**枠が違えば相互作用は無い**と考えてよい。
W008 は素朴な足し算（OOS +9,371 / IS +6,088）になると予想する。
**当たっても、W001 の4取引という弱点はそのまま残る。**
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


NO_SINGLE_RB = 124   # fxqual3 V001: RSI USDJPY の R単独・B単独を落とす

PROPOSALS = [
    ("Y000", "fxqual4/W000",
     "対照: 上書き全部0。W000/V000 と1円まで一致すること", PARAMS),

    # --- 1.5 の周りを刻む（台地か尖りかを見る。最良点を選ぶためではない）------
    ("Y001", "Y000", "PB USDJPY slope 1.35ATR（W001 の手前）", t(PbSlopeATR_UJ=1.35)),
    ("Y002", "Y000", "PB USDJPY slope 1.40ATR", t(PbSlopeATR_UJ=1.40)),
    ("Y003", "Y000", "PB USDJPY slope 1.45ATR（W001 のすぐ手前）", t(PbSlopeATR_UJ=1.45)),
    ("Y004", "Y000", "PB USDJPY slope 1.55ATR（W001 のすぐ先）", t(PbSlopeATR_UJ=1.55)),
    ("Y005", "Y000", "PB USDJPY slope 1.65ATR", t(PbSlopeATR_UJ=1.65)),
    ("Y006", "Y000", "PB USDJPY slope 1.30ATR（緩める側 1.2 との中間）",
     t(PbSlopeATR_UJ=1.30)),

    # --- 合成: 両窓で符号が揃った2件を重ねる（枠が違うので足し算になるはず）----
    ("Y007", "fxqual4/W001",
     "合成: RSI USDJPY 機構ゲート(V001) ＋ PB USDJPY slope 1.5(W001)",
     t(RsiMechMask_UJ=NO_SINGLE_RB, PbSlopeATR_UJ=1.5)),
]

# 対照 → 1.5 のすぐ両隣（尖りかどうかが最速で分かる）→ 外側 → 合成。
ORDER = ["Y000", "Y003", "Y004", "Y002", "Y005", "Y001", "Y006", "Y007"]


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
        m3.log(f"FXQUAL6_START jobs={len(jobs)} W001 の頑健性（slope の細刻み）＋合成")
        for pid, base, desc, params, window in jobs:
            row = m3.run(pid, base, desc, params, window)
            m3.append_result(row)
            if pid == "Y000" and row.get("status") != "OK":
                m3.log("FXQUAL6_ABORT 対照が失敗した。回帰試験が取れないので中止")
                return
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        (m3.ROOT / "measure.lock").unlink(missing_ok=True)
    m3.log(f"FXQUAL6_END -> {m3.OUT}")


if __name__ == "__main__":
    main()

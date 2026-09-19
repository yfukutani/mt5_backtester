"""第27報 第15ラウンド `ml/fxqual15` — `T001` を採るか捨てるかを決める（台地・合成・FULL）。

【EA は触らない】
`RsiTpMask_*` / `RsiTpMult_*` は第13ラウンドで実装・デプロイ済み（`e8fcfbd`・`.ex5` は 20:09:25）。
**このラウンドはコンパイルしない。** 並行セッションの `ml/fxqual14` と衝突しないよう、
ロックとテスターが空くのを待つだけにする。

【何を決めるか】
第13ラウンドで `T001`（`RsiTpMask_UJ=120` ＋ `RsiTpMult_UJ=1.5`）が採用候補になった。
**ただし第25報の追補で評価を2段下げてある:**

- **IS の DD は案を区別しない**（最大DD は全案とも 2022-03-17・ピーク 500,340円＝
  窓開始から9か月で +340円しか動いていない地点で決まる）。**IS の DD は採否条件から外す。**
- **反証点が効いていない**——`T002`（同じ D群 ×0.7）の IS は +0.036pt で `T001`（+0.015pt）より良い。
  **縮めても伸ばしても IS が上がる＝ IS 側はノイズ。**

**したがって `T001` の根拠は OOS 側だけである**（×1.5 で +0.011pt / ×0.7 で −0.038pt と
方向が出ており、OOS の残高DD −0.64pt・equity DD −1.04pt も同時に改善）。
**このラウンドは「その OOS の方向が、台地なのか 1.5 の1点だけの尖りなのか」を決める。**

【採否の条件（先に書いておく）】
1. **OOS の倍率応答が単調か台地であること。** 1.25 と 1.75 が 1.5 と同符号なら台地。
   **1.5 だけが突出していたら尖りとして棄却する**（第20報で `ScaFilRangeMin=0.0060` が
   IS のスパイクと分かって 0.0048 に下げた前例に従う）。
2. **FULL 窓でも OOS と同符号であること。**
3. **IS は「悪化していないこと」だけを見る。** IS の改善は根拠に使わない（上記の理由）。
4. **OOS の equity DD が悪化しないこと。**

【事前の予想】
- **台地はあると予想する。** 機構は「D を含む群には伸びしろがある」であって閾値の当てものではない。
- **×2.0 は落ちると予想する。** RSI は SCA の22時のような強制決済を持たないので、
  TP を遠ざけるほど**建玉が長居して次のシグナルを潰す**
  （第13ラウンドで取引数が 1188→1184 / 1452→1437 と減っているのがその兆候）。
- **合成（`T001`＋`T008`）は劣加算と予想する。** 両方とも「TP を伸ばして建玉を長持ちさせる」
  方向なので、**同じ資金と同じ建玉スロットを取り合う。**
  ⚠️ **第22報「複利では加算性の符号すら窓で変わる」があるので、
  +0.011 と +0.039 を足して +0.05pt と見積もってはいけない。合成そのものを測る。**
- **FULL は OOS 寄りに出ると予想する**（FULL の 115か月のうち 55か月が OOS）。

【規模について正直に】
**`T001` は +0.011pt である。** 台地が確認できても、**目標6%までの +3.5pt/月 に対しては 0.3%。**
**このラウンドの価値は「採ってよいかを確定させること」であって、目標への前進ではない。**
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
    "OOS":  ("2016.11.09", "2021.06.20", 55.0),
    "IS":   ("2021.06.20", "2026.06.20", 60.0),
    "FULL": ("2016.11.09", "2026.06.20", 115.0),
}

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
    "ScaRR_UJ": 0.0, "ScaRR_GJ": 0.0,
    "ScaOvsATR_UJ": 0.0, "ScaOvsATR_GJ": 0.0,
    "RsiTpMask_UJ": 0, "RsiTpMult_UJ": 1.0,
    "RsiTpMask_EU": 0, "RsiTpMult_EU": 1.0,
    "RsiTpMask_GU": 0, "RsiTpMult_GU": 1.0,
}
for _k in ("BFXREV", "BTC_FUND", "CARRY", "ETH", "PAIR", "PB_GBPJPY", "PB_GOLD",
           "PB_USDJPY", "RSI_EURUSD", "RSI_GBPUSD", "RSI_USDJPY", "SCA_GBPJPY",
           "SCA_GOLD", "SCA_USDJPY", "VBO"):
    BASE[f"Mult_{_k}"] = 1.0

CAND = {
    "RsiMechMask_UJ": 124,
    "PbSlopeATR_UJ": 1.40,
    "ScaFilMask": 1, "ScaFilRangeMin": 0.0048,
}

# 全複利・倍率1・候補3件 ＝ fxqual10 G005 ＝ fxqualexec E000 ＝ fxqual12 Q000 ＝ fxqual13 T000。
COMP1 = dict(BASE, FxRiskMask=31, FxRiskPct=0.5, FxRiskRefCap=0, GlobalLotMult=1,
             RefCap_PB_USDJPY=0, RefCap_PB_GBPJPY=0, RefCap_CARRY=0, **CAND)

M_D_ANY = 120    # D を含む全コード(4,5,6,7)
M_B_ONLY = 2     # B 単独


def t(**over):
    p = dict(COMP1)
    p.update(over)
    return p


# (id, base, desc, params, 測る窓)
PROPOSALS = [
    # 回帰試験 ＋ FULL の基準。OOS +1,431,459 / IS +4,845,523 と一致すること。
    ("W000", "fxqual13/T000", "対照＝回帰試験（FULL も取る）", COMP1, ("OOS", "IS", "FULL")),

    # T001 の再現と FULL。OOS +1,442,852 / IS +4,890,581 と一致すること。
    ("W001", "W000", "**T001 の再現＋FULL**: UJ・D を含む群 ×1.5",
     t(RsiTpMask_UJ=M_D_ANY, RsiTpMult_UJ=1.5), ("OOS", "IS", "FULL")),

    # 倍率の内点。**OOS が台地か尖りか**を決める。ここがこのラウンドの本体。
    ("W002", "W001", "UJ・D を含む群 **×1.25**",
     t(RsiTpMask_UJ=M_D_ANY, RsiTpMult_UJ=1.25), ("OOS", "IS")),
    ("W003", "W001", "UJ・D を含む群 **×1.75**",
     t(RsiTpMask_UJ=M_D_ANY, RsiTpMult_UJ=1.75), ("OOS", "IS")),
    ("W004", "W001", "UJ・D を含む群 **×2.0**（落ちると予想）",
     t(RsiTpMask_UJ=M_D_ANY, RsiTpMult_UJ=2.0), ("OOS", "IS")),

    # 合成。⚠️ 足し算で見積もらない。
    ("W005", "W001", "**合成**: T001 ＋ T008（EU・B 単独 ×1.5）",
     t(RsiTpMask_UJ=M_D_ANY, RsiTpMult_UJ=1.5,
       RsiTpMask_EU=M_B_ONLY, RsiTpMult_EU=1.5), ("OOS", "IS", "FULL")),

    # T008 単独の FULL。合成を分解するのに要る（OOS/IS は第13ラウンドで測定済み）。
    ("W006", "W000", "T008 単独（EU・B 単独 ×1.5）の FULL",
     t(RsiTpMask_EU=M_B_ONLY, RsiTpMult_EU=1.5), ("FULL",)),
]

ORDER = ["W000", "W001", "W002", "W003", "W004", "W005", "W006"]


def main():
    for d in (m3.RUN_DIR, m3.CONFIG_DIR, m3.DEAL_DIR):
        d.mkdir(parents=True, exist_ok=True)
    if not m3.acquire_lock():
        return
    done = m3.load_done()
    idx = {p: i for i, p in enumerate(ORDER)}
    props = sorted(PROPOSALS, key=lambda x: idx.get(x[0], 99))
    # OOS → IS → FULL の順に全案を埋める。FULL は約2倍かかるので、
    # 途中で止まっても判定に要る両窓がそろう。
    jobs = [(pid, base, desc, params, w)
            for w_order in ("OOS", "IS", "FULL")
            for (pid, base, desc, params, wins) in props
            for w in wins if w == w_order and (pid, w) not in done]
    if not jobs:
        print("完了済みです")
        return
    import ctypes
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    try:
        m3.log(f"FXQUAL15_START jobs={len(jobs)} T001 の台地・合成・FULL")
        for pid, base, desc, params, window in jobs:
            row = m3.run(pid, base, desc, params, window)
            m3.append_result(row)
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        (m3.ROOT / "measure.lock").unlink(missing_ok=True)
    m3.log(f"FXQUAL15_END -> {m3.OUT}")


if __name__ == "__main__":
    main()

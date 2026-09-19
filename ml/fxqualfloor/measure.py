"""第17報の追加ラウンド `ml/fxqualfloor` — レンジ幅下限の内点を挟む。

【出発点】
`ml/fxqual10` が SCA USDJPY のレンジ幅下限を**全複利の上で** 0.0026〜0.0060 まで掃いた。
**6点すべて両窓プラス・ほぼ単調・両窓とも DD も下がる。**

| floor | OOS Δ | IS Δ | OOS sca_uj_n | IS sca_uj_n |
|---:|---:|---:|---:|---:|
| 0（対照） | — | — | 266 | 328 |
| 0.0042 | +142,023 | +413,234 | 140 | 245 |
| 0.0048 | **+150,369** | +409,131 | 103 | 214 |
| **0.0060** | +149,736 | **+525,131** | **49** | **167** |
| **∞（枠を外す）** | +149,604 | **−48,828** | 0 | 0 |

**OOS は floor 0.0042 以降 +150,000 で頭打ちで、枠を丸ごと外した値（+149,604）と同じ。**
**IS は 0.0060 でまだ上昇中で、∞ では −48,828 に落ちる。**

> **したがって内点の最適は 0.0060 と ∞ のあいだにある。両端で挟まれて確定している。**
> **だが 0.0060 が掃引範囲の端なので、そこが頂上かどうかは分かっていない。**

【このラウンドで決めること】
**IS の頂上がどこにあるか。** 0.0070 / 0.0080 / 0.0100 / 0.0120 / 0.0150 を刻む。

【事前の予想】
- **OOS は 0.0070 以降もほぼ +150,000 で動かない**と予想する。
  すでに「枠を外したのと同じ」水準に達しており、**残っている取引を削っても
  ブックはそれ以上良くならない**はずである。
- **IS は 0.0080〜0.0100 のどこかで頂上を打つ**と予想する。
  0.0060 で +525,131、∞ で −48,828 なので、**どこかで折り返す。**
  0.0060 での IS 取引数が 167 なので、0.0100 では 60〜80 程度まで落ちるはずで、
  **そのあたりで標本が薄くなって折り返す**と見る。
- **⚠️ 頂上を採ってはいけない。** `ml/fxqual6` の slope と同じで、**採るのは台地の内側**である。
  グリッドの最良点を採るのは第16報 V007 の失敗の形。**両窓プラスが続く帯の内側**を採る。

【効き幅の見積もり】
**新しい改善は出ない。** `ml/fxqual10` が既に +0.151pt / +0.175pt を出しており、
**本ラウンドはその値を確定させるだけ**である。頂上が 0.0060 より上にあっても、
**IS がもう少し伸びるだけで OOS は動かない**と見る。

【窓】
**OOS / IS のみ。** FULL（1本 590秒）は、閾値が決まってから対照と一緒に測る。

【素朴予測を書かない理由】
`ml/fxqual10` は deal ログから外挿した「素朴予測」を各案に書いたが、
**4件とも外れた**（複利では枠別損益がブックの分解にならないため。
[oanda_fx_compounding_attribution_20260919.md](../../docs/oanda_fx_compounding_attribution_20260919.md)）。
**本ラウンドで書けるのは「どちらへ動くか」だけ**である。
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
WINS = ("OOS", "IS")   # FULL は閾値が決まってから別ラウンドで測る

BASE = {
    "MarginCapPct": 0,
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
}
for _k in ("BFXREV", "BTC_FUND", "CARRY", "ETH", "PAIR", "PB_GBPJPY", "PB_GOLD",
           "PB_USDJPY", "RSI_EURUSD", "RSI_GBPUSD", "RSI_USDJPY", "SCA_GBPJPY",
           "SCA_GOLD", "SCA_USDJPY", "VBO"):
    BASE[f"Mult_{_k}"] = 1.0

# R036 = 全複利・倍率1。CAND = 採用済みの2件。F003 = その合成（fxqualcfm / fxqual10 と同一）。
R036 = dict(BASE, FxRiskMask=31, FxRiskPct=0.5, FxRiskRefCap=0, GlobalLotMult=1,
            RefCap_PB_USDJPY=0, RefCap_PB_GBPJPY=0, RefCap_CARRY=0)
CAND = {"RsiMechMask_UJ": 124, "PbSlopeATR_UJ": 1.40}
F003 = dict(R036, **CAND)


def t(base, **over):
    p = dict(base)
    for k, v in over.items():
        p[k] = v
    return p


def floor_(x):
    """SCA USDJPY だけにレンジ幅下限を掛ける（bit0 = magic 20261000）。"""
    return {"ScaFilMask": 1, "ScaFilRangeMin": x}


PROPOSALS = [
    ("H000", "fxqual10/G000",
     "対照: F003（全複利・倍率1 ＋ 採用候補2件）。G000 と1円まで一致すること",
     F003),

    ("H001", "H000", "SCA UJ レンジ幅下限 0.0070（0.0060 の1つ上）", t(F003, **floor_(0.0070))),
    ("H002", "H000", "SCA UJ レンジ幅下限 0.0080", t(F003, **floor_(0.0080))),
    ("H003", "H000", "SCA UJ レンジ幅下限 0.0100", t(F003, **floor_(0.0100))),
    ("H004", "H000", "SCA UJ レンジ幅下限 0.0120", t(F003, **floor_(0.0120))),
    ("H005", "H000", "SCA UJ レンジ幅下限 0.0150（∞ に近い側。取引はごく少数になるはず）",
     t(F003, **floor_(0.0150))),
]

# 対照 → 0.0060 のすぐ上 → 上へ。折り返しが早く見える並びにする。
ORDER = ["H000", "H001", "H002", "H003", "H004", "H005"]


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
        m3.log(f"FXQUALFLOOR_START jobs={len(jobs)} レンジ幅下限の内点を挟む")
        for pid, base, desc, params, window in jobs:
            row = m3.run(pid, base, desc, params, window)
            m3.append_result(row)
            if pid == "H000" and window == "OOS" and row.get("status") != "OK":
                m3.log("FXQUALFLOOR_ABORT 対照が失敗した。中止")
                return
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        (m3.ROOT / "measure.lock").unlink(missing_ok=True)
    m3.log(f"FXQUALFLOOR_END -> {m3.OUT}")


if __name__ == "__main__":
    main()

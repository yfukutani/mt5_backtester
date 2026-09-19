"""第17報の確認ラウンド `ml/fxqualcfm` — 採用候補は本番のサイジングでも残るか。

【なぜ要るか】
第3〜7ラウンドは**すべて本番現行のサイジング**（`RefCap_*=78,000`・`GlobalLotMult=1`・
`FxRiskMask=0` ＝ `ml/fxrisk1` の **R001** と同一）で測った。そこで残った採用候補は2件:

| 候補 | 内容 | OOS Δ | IS Δ |
|---|---|---:|---:|
| `V001` | `RsiMechMask_UJ=124`（RSI USDJPY の R単独・B単独を落とす） | +2,137 | +3,243 |
| `slope` | `PbSlopeATR_UJ=1.40`（PB USDJPY の slope 下限・台地の内側） | +7,429 | +6,266 |

**だが本番で目指しているのは複利の構成である。**
`docs/oanda_fx_risk_sizing_20260915.md` の

- **R036**（`FxRiskMask=31` / `FxRiskPct=0.5` / `FxRiskRefCap=0` / `RefCap_*=0` / 倍率1）
  ＝ **含み益なしで成立する最良**（OOS 1.69% / 最大DD 23.1%）
- **R037**（同上・**倍率2**）＝ 数字上の最良（OOS 3.02% / 最大DD 41.8%）

では、**枠のロットが equity に連動して増える**。固定 0.01 ロットの世界で +7,429円だった改善が、
複利の世界で同じ比率で残るとは限らない——**枠ごとの寄与率が違うからである。**
実際 `oanda_fx_last_axes_20260915.md` は
「**複利・risk% を効かせるほど SCA GBPJPY の寄与率は下がる**（T034 では純益の3.7%）」
と記録している。**PB USDJPY と RSI USDJPY についても同じことが起きうる。**

【このラウンドで決めること】
1. **FULL 窓（115か月）を初めて測る。** 第3〜7ラウンドは OOS/IS の2窓しか無い。
   採用の前に**3窓目**を見る。
2. **R036 / R037 のサイジングで、2件の採用候補が残るか。**
   残らなければ「**固定ロットでだけ効く改善**」であり、本番への価値は無い。
3. **幾何月利で報告する。** 目標（月利6%）は幾何・複利で定義されている。
   第3〜7ラウンドの単利月利とは並べられない。

【事前の予想】
- **FULL 窓では両方とも残ると予想する**（OOS/IS の両方で同符号なので、その和である
  FULL で符号が変わるほうが不自然）。
- **R036 / R037 では効き幅の比率が下がると予想する。** 複利で伸びるのは
  「早い時期に勝った枠」で、PB USDJPY は OOS で元々マイナスの枠である。
  **金額は増えるが、月利のポイント換算では小さくなる**と見る。
- **口座破綻（元本割れ）の有無を最優先で見る。** R037 は最大DD 41.8% で、
  改善が DD を悪化させる方向に出たら、金額が増えても採らない。

【注意】
`ml/fxrisk1` の R001 は OOS +119,537 で、本ラウンド群の対照（+117,843）と **1,694円ずれる。**
9月15日から18日のあいだに EA が変わっているためで、**両者を直接は並べられない。**
だから本ラウンドは **R036 / R037 の対照も自分で測り直す**（F002 / F004）。
比較はすべてラウンド内で閉じる。
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

# OOS/IS は第3〜7ラウンドと同一。**FULL を足す**（115か月・本ラウンドが初めて）。
m3.WINDOWS = {
    "OOS":  ("2016.11.09", "2021.06.20", 55.0),
    "IS":   ("2021.06.20", "2026.06.20", 60.0),
    "FULL": ("2016.11.09", "2026.06.20", 115.0),
}
WINS = ("OOS", "IS", "FULL")

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
}
for _k in ("BFXREV", "BTC_FUND", "CARRY", "ETH", "PAIR", "PB_GBPJPY", "PB_GOLD",
           "PB_USDJPY", "RSI_EURUSD", "RSI_GBPUSD", "RSI_USDJPY", "SCA_GBPJPY",
           "SCA_GOLD", "SCA_USDJPY", "VBO"):
    BASE[f"Mult_{_k}"] = 1.0

# --- サイジングの3構成（ml/fxrisk1 と同じ値）------------------------------
PROD = dict(BASE, FxRiskMask=0, FxRiskPct=0.5, FxRiskRefCap=0, GlobalLotMult=1,
            RefCap_PB_USDJPY=78000, RefCap_PB_GBPJPY=78000, RefCap_CARRY=78000)
R036 = dict(BASE, FxRiskMask=31, FxRiskPct=0.5, FxRiskRefCap=0, GlobalLotMult=1,
            RefCap_PB_USDJPY=0, RefCap_PB_GBPJPY=0, RefCap_CARRY=0)
R037 = dict(BASE, FxRiskMask=31, FxRiskPct=0.5, FxRiskRefCap=0, GlobalLotMult=2,
            RefCap_PB_USDJPY=0, RefCap_PB_GBPJPY=0, RefCap_CARRY=0)

# --- 採用候補（枠が違うので足し算になることは3例で確認済み）----------------
CAND = {"RsiMechMask_UJ": 124, "PbSlopeATR_UJ": 1.40}


def t(base, **over):
    p = dict(base)
    for k, v in over.items():
        p[k] = v
    return p


PROPOSALS = [
    ("F000", "fxqual7/Z000", "対照: 本番現行サイジング（R001相当）。OOS/IS は Z000 と一致すること",
     PROD),
    ("F001", "F000", "採用候補: V001(RsiMechMask_UJ=124) ＋ PB slope 1.40。本番現行サイジング",
     t(PROD, **CAND)),

    ("F002", "fxrisk1/R036", "対照: R036（全複利・倍率1・含み益なしで成立する最良）", R036),
    ("F003", "F002", "R036 ＋ 採用候補2件", t(R036, **CAND)),

    ("F004", "fxrisk1/R037", "対照: R037（全複利・倍率2・数字上の最良）", R037),
    ("F005", "F004", "R037 ＋ 採用候補2件", t(R037, **CAND)),
]

# 本番現行 → R036 → R037 の順。窓は OOS/IS/FULL。
# 途中で止まっても「本番現行で残るか」から埋まる並びにする。
ORDER = ["F000", "F001", "F002", "F003", "F004", "F005"]


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
        m3.log(f"FXQUALCFM_START jobs={len(jobs)} 採用候補2件を FULL窓と複利サイジングで確認")
        for pid, base, desc, params, window in jobs:
            row = m3.run(pid, base, desc, params, window)
            m3.append_result(row)
            if pid == "F000" and window == "OOS" and row.get("status") != "OK":
                m3.log("FXQUALCFM_ABORT 対照が失敗した。回帰試験が取れないので中止")
                return
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        (m3.ROOT / "measure.lock").unlink(missing_ok=True)
    m3.log(f"FXQUALCFM_END -> {m3.OUT}")


if __name__ == "__main__":
    main()

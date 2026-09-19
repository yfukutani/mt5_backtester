"""第17報の追加ラウンド `ml/fxqualexec` — その複利構成は、本当に建てられるのか。

【なぜこれが要るか】
本日の実測で、採用候補3件を全複利に載せると

| 構成 | OOS 幾何月利 | IS | 最大DD(OOS) |
|---|---:|---:|---:|
| 全複利・倍率1 ＋ 候補3件 | **2.490%** | 4.065% | 24.34% |
| 全複利・倍率2 ＋ 候補2件 | **3.340%** | 7.216% | 51.47% |

まで出た。**だが「建てられるか」を一度も測っていない。**

`oanda_fx_risk_sizing_20260915.md` は `R037` について
**「確定利益だけでは必要証拠金に届かず、時間の 3.5〜5.2% を含み益に依存して建てている」
＝ 実行不可**と判定している。**本ラウンドの構成は R037 より強い**
（`FxRiskMask=31` で SCA 2枠にも risk% が掛かる）ので、**同じかそれ以上に苦しいはず**である。

【測り方 — 既存 input だけで足りる】
`MarginCapPct` は **使用証拠金 / 口座equity の上限（%）**である（EA 1702行）。
`MarginCapLot()` が `eq*MarginCapPct/100 - ACCOUNT_MARGIN` を空き枠として、
それを超えるロットを削る。**0 で無効。**

したがって:

- **`MarginCapPct=100` を入れて結果が cap=0 と1円まで一致すれば、
  この構成は「使用証拠金が equity を超えたことが一度も無い」**＝ **実行可能**である。
- **一致しなければ、その差が「含み益に依存して建てていた分」**である。
  `CapLogFile` の `cut` / `deny` / `lot_want` / `lot_got` に、
  **どの枠で何回・どれだけ削られたか**が出る（第10報の計装）。

**OANDA は維持率100%で切る**（`oanda_broker_specs_20260915.md`）。
実用域として **90%** も測る。

【事前の予想】
- **倍率1（E001）は cap=100 でほぼ一致する**と予想する。
  `R036`（倍率1）は「含み益なしで成立する最良」と判定されており、
  本構成はそれに枠の質の改善を足しただけである。**改善は equity を増やすので、
  証拠金の余裕はむしろ広がる。**
- **倍率2（E004）は cap=100 で大きく削られる**と予想する。
  `R037` が実行不可と判定された理由そのものである。
- **cap=90（E002 / E005）はどちらも削られる**と予想する。
  第13報で cap の応答曲線が 60→100% で単調増加だったので、
  **90% は 100% より必ず苦しい。**

【このラウンドで決めること】
**「採用候補を載せた複利構成のうち、どれが本番に持っていけるか。」**
月利が高くても**建てられない構成は採らない**。これは `CLAUDE.md` の
「最優先の合否は口座破綻の有無」と同じ性質の、実行可能性のゲートである。
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
m3.CAP_LOG = True     # cap の cut/deny/lot_want/lot_got を記録する（本ラウンドの主役）

m3.WINDOWS = {
    "OOS":  ("2016.11.09", "2021.06.20", 55.0),
    "IS":   ("2021.06.20", "2026.06.20", 60.0),
    "FULL": ("2016.11.09", "2026.06.20", 115.0),
}
WINS = ("OOS", "IS")   # FULL は実行可能な構成が絞れてから測る

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
}
for _k in ("BFXREV", "BTC_FUND", "CARRY", "ETH", "PAIR", "PB_GBPJPY", "PB_GOLD",
           "PB_USDJPY", "RSI_EURUSD", "RSI_GBPUSD", "RSI_USDJPY", "SCA_GBPJPY",
           "SCA_GOLD", "SCA_USDJPY", "VBO"):
    BASE[f"Mult_{_k}"] = 1.0

# 採用候補3件。SCA のレンジ幅下限は **0.0048**（`ml/fxqualfloor` で 0.0060 が
# IS のスパイクと判明したため、台地の内側を採る）。
CAND = {
    "RsiMechMask_UJ": 124,
    "PbSlopeATR_UJ": 1.40,
    "ScaFilMask": 1, "ScaFilRangeMin": 0.0048,
}

COMP1 = dict(BASE, FxRiskMask=31, FxRiskPct=0.5, FxRiskRefCap=0, GlobalLotMult=1,
             RefCap_PB_USDJPY=0, RefCap_PB_GBPJPY=0, RefCap_CARRY=0,
             MarginCapPct=0, **CAND)
COMP2 = dict(COMP1, GlobalLotMult=2)


def t(base, **over):
    p = dict(base)
    for k, v in over.items():
        p[k] = v
    return p


PROPOSALS = [
    # ⚠️ E000 は `ml/fxqual10` の **G005**（F003 ＋ floor 0.0048）と**同一構成**である。
    #    したがって **OOS +1,431,459 / IS +4,845,523 と1円まで一致しなければならない。**
    #    これが本ラウンドの回帰試験になる——並行セッションが `LotFloorMask` を足した
    #    新しいバイナリで走る可能性があるので、**既定で inert かどうかがここで実測される。**
    ("E000", "fxqual10/G005",
     "対照: 倍率1・候補3件・cap無効。G005（OOS +1,431,459 / IS +4,845,523）と一致すること",
     COMP1),
    ("E001", "E000", "倍率1 ＋ **MarginCapPct=100**（一致すれば実行可能）",
     t(COMP1, MarginCapPct=100)),
    ("E002", "E000", "倍率1 ＋ MarginCapPct=90（OANDA の実用域）",
     t(COMP1, MarginCapPct=90)),

    ("E003", "E000", "対照: 倍率2・候補3件・cap無効", COMP2),
    ("E004", "E003", "倍率2 ＋ **MarginCapPct=100**（R037 は実行不可と判定された水準）",
     t(COMP2, MarginCapPct=100)),
    ("E005", "E003", "倍率2 ＋ MarginCapPct=90", t(COMP2, MarginCapPct=90)),
]

# 倍率1 の実行可能性 → 倍率2 の実行可能性、の順。
# 途中で止まっても「本番に持っていける側」から先に埋まる。
ORDER = ["E000", "E001", "E002", "E003", "E004", "E005"]


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
        m3.log(f"FXQUALEXEC_START jobs={len(jobs)} 複利構成は建てられるのか（証拠金cap）")
        for pid, base, desc, params, window in jobs:
            row = m3.run(pid, base, desc, params, window)
            m3.append_result(row)
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        (m3.ROOT / "measure.lock").unlink(missing_ok=True)
    m3.log(f"FXQUALEXEC_END -> {m3.OUT}")


if __name__ == "__main__":
    main()

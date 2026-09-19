"""第17報の追加ラウンド `ml/fxqualamp` — 複利の増幅は、どの候補から来ているのか。

【なぜ要るか】
確認ラウンド `ml/fxqualcfm` で、採用候補2件の効き幅がサイジングで大きく変わることが分かった:

| サイジング（OOS） | 対照 | 候補2件 | 効き幅 |
|---|---:|---:|---:|
| 本番現行（`RefCap=78,000`・倍率1） | 0.386% | 0.414% | +0.028pt |
| 全複利・倍率1（`FxRiskMask=31`・`RefCap_*=0`） | 2.004% | 2.337% | **+0.332pt** |

**だが「2件まとめて」しか測っていない。** 固定ロットでの内訳は
**V001（RSI UJ の機構ゲート）が +2,137円・slope 1.40 が +7,429円**で、
比でいえば **22% : 78%** である。**複利でも同じ比とはかぎらない。**

理由: 全複利構成では枠ごとに複利の効き方が違う。
- **PB USDJPY** は `RefCap_PB_USDJPY=0` で **equity 連動**（`useRisk=true`・`riskPct=2.0`）
- **RSI USDJPY** は `FxRiskMask` bit0 で **equity 連動**（`riskPct=0.5`）
- **SCA USDJPY** は bit3 で equity 連動（09-15 の修正で初めて有効になった）

**risk% が 2.0 と 0.5 で4倍違う**ので、**同じ「1取引あたりの改善」でも複利で乗る量が違う。**

【このラウンドで決めること】
**+0.332pt のうち、どれがどれだけ運んでいるか。**
それが分かると、**次にどの枠を触ると複利で報われるか**が決まる。

【事前の予想】
**PB USDJPY（slope）が大半を運ぶ**と予想する。固定ロットでの寄与が78%で、
かつ **risk% が 2.0 と最大**だからである。
**ただし比が 78% を大きく超える**と予想する——risk% の差（2.0 対 0.5）が
複利でさらに開くはずである。**具体的には 85〜95% と予想する。**

**加算性は複利では成り立たないと予想する。** 固定ロットでは7例すべて1円まで足し算だったが、
**複利では枠どうしが同じ equity を共有する**ので、片方が増やした equity が
もう片方のロットを大きくする。**G004 は G001+G002+G003 の和より大きくなるはず**である。
**これが外れて足し算になったら、そのほうが驚きであり、記録する価値がある。**

【効き幅の見積もり】
このラウンドは**新しい改善を探さない。** 既に測った +0.332pt の内訳を割るだけである。
**月利は1ptも増えない。**
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
    # 第18報（並行セッション）の新入力。**全案で明示的に既定値を書く。**
    "PbArmMaxBars_UJ": 0, "PbArmMaxBars_GJ": 0, "PairRequireZTurning": False,
}
for _k in ("BFXREV", "BTC_FUND", "CARRY", "ETH", "PAIR", "PB_GBPJPY", "PB_GOLD",
           "PB_USDJPY", "RSI_EURUSD", "RSI_GBPUSD", "RSI_USDJPY", "SCA_GBPJPY",
           "SCA_GOLD", "SCA_USDJPY", "VBO"):
    BASE[f"Mult_{_k}"] = 1.0

# 全複利・倍率1（`ml/fxqualcfm` の F002 と同一）。ここを土台にする。
R036 = dict(BASE, FxRiskMask=31, FxRiskPct=0.5, FxRiskRefCap=0, GlobalLotMult=1,
            RefCap_PB_USDJPY=0, RefCap_PB_GBPJPY=0, RefCap_CARRY=0)

RSI_GATE = {"RsiMechMask_UJ": 124}                                  # V001
PB_SLOPE = {"PbSlopeATR_UJ": 1.40}                                  # 第6ラウンド台地の内側
SCA_RANGE = {"ScaFilMask": 1, "ScaFilRangeMin": 0.00595}            # 第8ラウンドの副産物


def t(base, *dicts):
    p = dict(base)
    for d in dicts:
        p.update(d)
    return p


PROPOSALS = [
    ("G000", "fxqualcfm/F002",
     "対照: 全複利・倍率1。F002 と一致すること（EA が差し替わっているので回帰試験）",
     R036),

    # --- 候補を1件ずつ ---------------------------------------------------
    ("G001", "G000", "全複利 ＋ RSI USDJPY の機構ゲートだけ（V001）",
     t(R036, RSI_GATE)),
    ("G002", "G000", "全複利 ＋ PB USDJPY の slope 1.40 だけ",
     t(R036, PB_SLOPE)),
    ("G003", "G000", "全複利 ＋ SCA USDJPY のレンジ幅下限だけ",
     t(R036, SCA_RANGE)),

    # --- 全部（加算性が複利でも成り立つかの検算）--------------------------
    ("G004", "G000", "全複利 ＋ 候補3件（G001+G002+G003 の和より大きくなると予想）",
     t(R036, RSI_GATE, PB_SLOPE, SCA_RANGE)),
]

ORDER = ["G000", "G002", "G001", "G003", "G004"]


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
        m3.log(f"FXQUALAMP_START jobs={len(jobs)} 複利の増幅の内訳を割る")
        for pid, base, desc, params, window in jobs:
            row = m3.run(pid, base, desc, params, window)
            m3.append_result(row)
            if pid == "G000" and window == "OOS" and row.get("status") != "OK":
                m3.log("FXQUALAMP_ABORT 対照が失敗した。中止")
                return
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        (m3.ROOT / "measure.lock").unlink(missing_ok=True)
    m3.log(f"FXQUALAMP_END -> {m3.OUT}")


if __name__ == "__main__":
    main()

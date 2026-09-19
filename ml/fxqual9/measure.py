"""第19報ラウンド `ml/fxqual9` — 状態機械に残っていた最後の入口2軸。

【なぜここか — Codex の棚卸しで名指しされた2つだけが残った】
`docs/codex_oafx_inventory_20260919.md` で、第1〜7ラウンドの実測を全部渡したうえで
「残っている合理的な作業」として挙がったのは**この2軸だけ**である。
どちらも **EA に実装が無いので、既存 input では表現できない**。

### A. `PbArmMaxBars_UJ` / `_GJ`（PullbackTrend の armed の寿命）

第17報（`ml/fxqual3`）の leave-one-out で、PB 入口の律速は
**slope → ADX → armed** の順だった（PB USDJPY・IS で armed が 126〜170バー）。
ところが `armedBuy`/`armedSell` は `up`/`dn` が崩れるまで**無期限に残る**実装で、
**100本前に付けた押し目でも生きている。**
「押し目を付けてから N バー以内でしか入らない」という寿命は**一度も測っていない。**

### B. `PairRequireZTurning`（乖離が縮小へ転じた足でしか入らない）

`ProcPair()` は `|z|>=entryZ` になった足でその場で両脚を建てる。
**乖離がまだ拡大している途中でも建つ。** 「前バーより |z| が縮んでいること」は未測定。

【⚠️ 第5ラウンドの教訓がここにも効く可能性が高い】
`ml/fxqual5` で、SCA の時間帯ゲートは「止めた発注が消える」のではなく
**「後ろの足へずれる」**ことが分かり、切り直しの予測（+13,093）が実測（−6,817）と
符号ごと逆になった。**判定条件は「そのゲートが日内で解除されるか」**だった。

**この2軸はどちらも『ずれる』側である。**
- PB: armed が期限切れになっても、その後 `lp<=fastema` が再成立すれば**また arm される**。
  トレンドが続いていれば押し目は何度も来るので、**入口が消えるのではなく後ろへずれる。**
- Pair: 今日 turning しなくても、|z|>=entryZ が続いていれば**明日 turning した足で入る。**

つまり **どちらも「取引を減らす」より「取引をずらす」効果のほうが大きい**と予想する。
**両窓プラスになる確率は高くないと見る。**

【事前の予想（測る前に書く）】
- 効き幅の見積もりは **月利 ±0.02pt**（Codex は PB ±0.014pt / Pair ±0.03pt）。
- PB USDJPY の OOS は **8 deal ＝ 4往復**しかない。**正の一点が出ても採用根拠にならない。**
  `ml/fxqual6` の slope が「5点連続の台地」だったので候補になったのと同じ基準で見る。
  **勾配（1/2/3/5/8）が単調か台地でなければ棄却する。**
- Pair は OOS 30脚 / IS 56脚しかなく、`ml/fxqual2` の T001〜T007 が全部ほぼゼロだった。
  **turning も同じくほぼゼロだと予想する。**

**測る価値があるのは、この2軸が「枠の質」というテーマで最後の未測定軸だからであって、
月利が上がると思っているからではない。**

【回帰試験】
`A000`（新入力を全部既定値）は `ml/fxqual4` の W000（= fxqual7 Z000 = fxqual8 RV00）と
**純益・DD・取引数が1円まで一致**しなければならない。
**このラウンドは EA を差し替えて再コンパイルする**ので、合わなければそこで止める。

  OOS +117,843 / DD 5.2719% / 1375 trades
  IS  +255,445 / DD 7.3544% / 1595 trades
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
    # 他セッションが足した入力。**全案で明示的に既定値を書く**（Codex の査読より）。
    "ScaBETriggerR": 0.0, "ScaBELockR": 0.0, "ScaBEMask": 0,
    "ScaRevOnlyMask": 0, "ScaRevDropMask": 0,
    # 第19報（このラウンド）で足した入力。0 と false が現行。
    "PbArmMaxBars_UJ": 0, "PbArmMaxBars_GJ": 0,
    "PairRequireZTurning": False,
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
    ("A000", "fxqual4/W000",
     "対照: 新入力を全部既定値。W000/Z000/RV00 と1円まで一致すること（再コンパイル後の回帰試験）",
     PARAMS),

    # --- PB USDJPY の armed の寿命（勾配・台地かどうかで判定する）--------------
    # LOO で armed が最も強く効いていた枠。H4 なので 1バー=4時間・12バー=2日。
    ("A001", "A000", "PB USDJPY: armed の寿命 1バー（セット足＋次の1足のみ）",
     t(PbArmMaxBars_UJ=1)),
    ("A002", "A000", "PB USDJPY: armed の寿命 2バー", t(PbArmMaxBars_UJ=2)),
    ("A003", "A000", "PB USDJPY: armed の寿命 3バー", t(PbArmMaxBars_UJ=3)),
    ("A004", "A000", "PB USDJPY: armed の寿命 5バー", t(PbArmMaxBars_UJ=5)),
    ("A005", "A000", "PB USDJPY: armed の寿命 8バー（約1.3日）", t(PbArmMaxBars_UJ=8)),

    # --- PB GBPJPY（LOO では 36〜58バーと弱い。中央の1点だけ当てる）------------
    ("A006", "A000", "PB GBPJPY: armed の寿命 3バー（UJ で効くなら同方向に出るはず）",
     t(PbArmMaxBars_GJ=3)),

    # --- Pair の Z 転換 -------------------------------------------------------
    ("A007", "A000", "Pair: 乖離が縮小へ転じた足でしか建てない", t(PairRequireZTurning=True)),
]

# 対照 → UJ の勾配（形が最速で分かる）→ GJ → Pair。
ORDER = ["A000", "A001", "A002", "A003", "A004", "A005", "A006", "A007"]


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
        m3.log(f"FXQUAL9_START jobs={len(jobs)} PB armed の寿命6案＋Pair Z転換1案＋対照")
        for pid, base, desc, params, window in jobs:
            row = m3.run(pid, base, desc, params, window)
            m3.append_result(row)
            if pid == "A000" and row.get("status") != "OK":
                m3.log("FXQUAL9_ABORT 対照が失敗した。回帰試験が取れないので中止")
                return
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        (m3.ROOT / "measure.lock").unlink(missing_ok=True)
    m3.log(f"FXQUAL9_END -> {m3.OUT}")


if __name__ == "__main__":
    main()

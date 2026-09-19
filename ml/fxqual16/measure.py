"""第16ラウンド `ml/fxqual16` — 倍率3 で cap を作っているのは誰か（6run）。

【経緯 — 2セッションで2回まちがえた軸である】
`V012`（倍率3・cap90）の OOS は 4.608%（eqDD 73.62%）で、
2点フィットの予測 4.373% を上回った。局所指数が 0.746 → 1.055 に上がる
＝ **DD に対して収穫逓増**に見える。

並行セッションの説明: **倍率を上げるほど cap が左の尾を切っている。**
cap の cut/deny は 0 → 459/342 → 2,191/1,705 と増える。
したがって `V012` は「同じブックを倍率で伸ばした点」ではなく**別の系**で、
**ここから先へ外挿すると戦略ではなく cap の挙動を外挿することになる。**

🔴 **こちらはこの cap ログを枠別に割って「主犯は Pair（cut の 89%）」と書いた。誤りだった。**
**`ProcPair()` は毎評価バーで無条件に `Clamp()` を2回呼ぶ**（EA 2905-2906行。
発注の判定は 2935行）。**Pair の cut/deny は「評価の回数」であって「潰された発注」ではない**
（`calls` が 57,152 に対し OOS 取引数は 30）。

**Pair を除くと、実際の発注に対する cap 圧力はこうなる:**

| 構成（OOS） | Pair 以外の cut / deny | うち `sca_gj` |
|---|---:|---:|
| 倍率1（`V000`） | **0 / 0** | — |
| 倍率2（`V010`） | 69 / 3 | **53（77%）** |
| **倍率3（`V012`）** | **232 / 27** | **167（72%）** |

**主犯は `sca_gj` で 6〜7割。** 機構も明確で、**`scaBoostMult=6.0` の反転日だけ
通常の6倍のロットを要求する**ので、cap に当たるのはその日の注文である。
これは `docs/oanda_fx_sca_boost_under_risk_20260919.md` と同じ根に当たっている
（boost 群は sca_gj の損益の符号を決めてもおり、**cap 圧力の主因でもある**）。

【このラウンドで測ること】
**比較指標は「Pair 以外の cut/deny」である。総件数ではない。**
総件数は Pair を外せば定義上ほぼゼロになるので、何も検証できない。

| 案 | 内容 | 見どころ |
|---|---|---|
| （対照） | `V012`（`ml/fxqual14` で既測） | Pair 以外 232/27・OOS 4.608% |
| **X001** | **Pair 抜き・倍率3** | **Pair 以外の cut が 232 から減れば「Pair の建玉が他枠の空きを奪っていた」が実在** |
| **X002** | **`Mult_SCA_GBPJPY=0.25`・倍率3** | cap 圧力の7割を直接外す |
| X003 | X001 ＋ X002 | 加算性（⚠️ 足し算で見積もらない） |

【事前予想（並行セッションと共同）】
- **`X002` > `X001`。** cap 圧力の主因は `sca_gj` なので。
- **`X001` で「Pair 以外の cut」がほとんど減らなければ、Pair は証拠金を占有していなかった**
  ことになり、`V009`（Pair 抜き・倍率1）の元の見積もり（±0.03pt）が正しかったことになる。
- **`X002` は月利を下げるはず。** 第12ラウンド C群で `Mult_SCA_GBPJPY=0.25` は
  倍率1 で両窓マイナス（OOS −0.482pt / IS −0.205pt）だった。
  **本ラウンドの問いは「倍率3 では cap を空けるぶん符号が変わるか」である。**
  第23報の `Q004`（重み0.25 ＋ 倍率2）が OOS +0.197pt だったので、
  **倍率が上がるほどこの軸は有利になる傾向が既に見えている。**
  **倍率3 でそれが続くかどうか。**
- **曲率の検証**: cap 圧力が減った構成で局所指数が 1.055 から 0.75 付近へ戻れば、
  「収穫逓増は cap のせい」が支持される。**戻らなければ否定される。**

⚠️ **EA は触らない。** `Mult_*` / `En_*` は既存 input。
`scaBoostMult` を input 化する案（第17ラウンド候補）は、
**並行セッションの `ml/fxqual15` が走り終わってから**でないと、
あちらのデプロイ検査（リポジトリの .mq5 と一致するか）を落としてしまう。
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
m3.CAP_LOG = True          # このラウンドの主指標が cap ログなので必須

m3.WINDOWS = {
    "OOS":  ("2016.11.09", "2021.06.20", 55.0),
    "IS":   ("2021.06.20", "2026.06.20", 60.0),
    "FULL": ("2016.11.09", "2026.06.20", 115.0),
}
WINS = ("OOS", "IS")

# ml/fxqual14 の BASE と1文字も変えない（比較可能性のため）。
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

# 倍率3・cap90 ＝ ml/fxqual14 の V012（OOS 5,457,672 / eqDD 73.62%）。
COMP3 = dict(BASE, FxRiskMask=31, FxRiskPct=0.5, FxRiskRefCap=0, GlobalLotMult=3,
             RefCap_PB_USDJPY=0, RefCap_PB_GBPJPY=0, RefCap_CARRY=0,
             MarginCapPct=90, **CAND)


def t(**over):
    p = dict(COMP3)
    p.update(over)
    return p


PROPOSALS = [
    ("X000", "fxqual14/V012",
     "対照＝回帰試験: 倍率3・cap90。V012 の OOS 5,457,672 と一致すること", COMP3),
    ("X001", "X000", "**Pair を外す**（倍率3）。Pair 以外の cut が 232 から減るか",
     t(En_PAIR=False)),
    ("X002", "X000", "**Mult_SCA_GBPJPY=0.25**（倍率3）。cap 圧力の7割を直接外す",
     t(Mult_SCA_GBPJPY=0.25)),
    ("X003", "X001", "X001 ＋ X002（⚠️ 加算性は測る。足し算で見積もらない）",
     t(En_PAIR=False, Mult_SCA_GBPJPY=0.25)),
]

# 対照 → 予想が強い X002 → X001 → 合成。途中で止まっても価値の高い側から埋まる。
ORDER = ["X000", "X002", "X001", "X003"]

EXPECT = {"X000": {"OOS": 5457672.0}}


def check(row):
    pid, win = row["proposal_id"], row["window"]
    if row.get("status") != "OK":
        raise RuntimeError(f"{pid}({win}) が FAILED です。中止します。")
    if pid not in EXPECT or win not in EXPECT[pid]:
        return
    exp = EXPECT[pid][win]
    got = float(row["net"])
    rel = abs(got - exp) / abs(exp)
    m3.log(f"REGRESSION {pid} {win} expected={exp} got={got} -> "
           f"{'EXACT' if abs(got-exp) < 1.0 else f'DRIFT rel={rel:.5%}'}")
    # Carry のスワップ・ドリフトがあるので 0.5% までは許す（fxqual14 と同じ規約）。
    if rel > 0.005:
        raise RuntimeError(
            f"{pid}({win}) が V012 を再現しませんでした（期待 {exp} / 実測 {got}）。")


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
        m3.log(f"FXQUAL16_START jobs={len(jobs)} 倍率3 で cap を作っているのは誰か")
        for pid, base, desc, params, window in jobs:
            row = m3.run(pid, base, desc, params, window)
            m3.append_result(row)
            check(row)
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        (m3.ROOT / "measure.lock").unlink(missing_ok=True)
    m3.log(f"FXQUAL16_END -> {m3.OUT}")


if __name__ == "__main__":
    main()

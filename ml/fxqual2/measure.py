"""第15報ラウンド `ml/fxqual2` — 発火理由を記録するためだけの対照2run。

【なぜこのラウンドが要るか】
`ml/fxqual1`（第14報）で測れない案が2家族ある。どちらも「案が悪い」のではなく
**取引ログに必要なものが記録されていない**ために測れない。

1. **RSI の3機構が分離できない**（Claude #18/#20・Codex #19〜#21）
   `ProcRSI()` の入口は `eb = range_ok && up && (rbuy||bbuy||dpb)` という OR で、
   RSI反転 / ボリンジャー回帰 / ダブルボトム の3つが同居している。
   退出は共通の固定SL/TPひとつ。**機構別の成績を一度も見ていない**ので
   「勝つ機構だけ残す」も「機構ごとに退出を変える」も、案として測れない。

2. **Pair の参入時 z が分からない**（Codex #23）
   現行は `|z| >= entryZ(4.0)` で建てるが、退出は `|z| >= stopZ(5.0)` でも起きる。
   **建てた瞬間に退出条件も成立している領域**があり、そこを避ける案が出ている。
   z が記録されていないので件数すら数えられない。

【このラウンドがやること】
`TagDealTriggers=true`（第15報でEAに追加・既定false）を入れた対照を、
fxqual1 の Q000 と**完全に同じ構成**で OOS/IS の2窓だけ走らせる。
変わるのは注文コメントの文字列と deals ダンプの1列（`comment`）だけで、
**売買判断は1ビットも変わらない。**

【このラウンド自身が回帰試験である】
したがって T000 の 純益・DD・取引数は **fxqual1 の Q000 と1円まで一致しなければならない。**
一致しなければ、タグ付けが売買に影響しているということであり、
`analyze.py` の結果も信用できない。**一致の確認を判定の前に置くこと。**

【このラウンドは収益を改善しない】
測るのは「内訳」だけである。改善案は、内訳を見てから次のラウンドで出す。
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
m3.CAP_LOG = False

# fxqual1 と同一の窓。数字を並べられるようにするため、ここを変えてはいけない。
m3.WINDOWS = {
    "OOS": ("2016.11.09", "2021.06.20", 55.0),
    "IS":  ("2021.06.20", "2026.06.20", 60.0),
}
WINS = ("OOS", "IS")

# fxqual1 の Q000 と同一（本番現行サイジング）。差は TagDealTriggers だけ。
PARAMS = {
    "GlobalLotMult": 1,
    "MarginCapPct": 0,
    "BrokerMaxLot": 0,
    "FxRiskMask": 0, "FxRiskPct": 0.5, "FxRiskRefCap": 0,
    "RefCap_PB_USDJPY": 78000, "RefCap_PB_GBPJPY": 78000, "RefCap_CARRY": 78000,
    "TagDealTriggers": True,
}
for _k in ("BFXREV", "BTC_FUND", "CARRY", "ETH", "PAIR", "PB_GBPJPY", "PB_GOLD",
           "PB_USDJPY", "RSI_EURUSD", "RSI_GBPUSD", "RSI_USDJPY", "SCA_GBPJPY",
           "SCA_GOLD", "SCA_USDJPY", "VBO"):
    PARAMS[f"Mult_{_k}"] = 1.0

PROPOSALS = [
    ("T000", "fxqual1/Q000", "計装ON対照: 発火理由タグ＋Pairのz記録。"
                             "売買はQ000と同一でなければならない", PARAMS),
]


def main():
    for d in (m3.RUN_DIR, m3.CONFIG_DIR, m3.DEAL_DIR):
        d.mkdir(parents=True, exist_ok=True)
    if not m3.acquire_lock():
        return
    done = m3.load_done()
    jobs = [(pid, base, desc, params, w)
            for (pid, base, desc, params) in PROPOSALS
            for w in WINS if (pid, w) not in done]
    if not jobs:
        print("完了済みです")
        return
    import ctypes
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    try:
        m3.log(f"FXQUAL2_START jobs={len(jobs)} 発火理由の計装（売買は不変のはず）")
        for pid, base, desc, params, window in jobs:
            row = m3.run(pid, base, desc, params, window)
            m3.append_result(row)
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        (m3.ROOT / "measure.lock").unlink(missing_ok=True)
    m3.log(f"FXQUAL2_END -> {m3.OUT}")


if __name__ == "__main__":
    main()

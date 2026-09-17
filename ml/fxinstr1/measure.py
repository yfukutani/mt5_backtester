"""cap が実際にどれだけ削っているかを測る（第10報）。

【なぜこれを先に測るのか】
第9報は「cap の応答曲線が単調＝証拠金が律速している」と診断した。
Codex の50案の A群（#1 退出を先に処理する／#2 発注順を効率順にする／
#4 枠ごとの建玉証拠金予算／#7 不足量の後追い補充）は、すべて
**「cap に削られている良い注文がそれなりの量ある」**という前提の上に立っている。

**その量を、まだ一度も測っていない。**

削られている量が小さければ、A群は**まとめて価値が無い**。
大きければ、A群が本命になる。**どちらでも次にやることが決まる。**

【計装の中身】
EA の `Clamp()` に枠インデックスを渡し、枠別に数えるだけ（受動的）。

    calls     cap有効時の Clamp 呼び出し回数
    cut       cap がロットを削った回数（発注はできた）
    deny      cap が 0 にした回数＝**発注を見送った**
    lot_want  cap を掛ける前の希望ロットの合計
    lot_got   実際に返したロットの合計

**lot_got / lot_want が「cap を通過した量の割合」**である。
これが 0.95 なら、配分をどう賢くしても取り返せるのは残り5%しかない。

【ついでに直したもの — 含み損込みDD】
`OnTester()` は `equity_dd_pct`（STAT_EQUITY_DDREL_PERCENT）を
`ResultFileName` に書いていたが、**そのファイルは `FILE_COMMON` 無しで開かれており**
テスターエージェントのサンドボックスに落ちて**誰も読んでいなかった**。
そのため報告してきた最大DDは、ずっと残高ベース（含み損を含まない下限値）のままだった。
計装ログは `FILE_COMMON` で開くので、ここから両方を回収する。

【最初に対照を回す】
EA を再コンパイルするので、**I000 = X005＋cap90 が fxcap25 の Y090 を厳密に再現すること**
を最初に確認する。再現しなければ以降は比較できないので、そこで止める。

    Y090 実測: W1 6,094,303 / W2 1,133,625 / W3 1,155,866 / OOS 45,221,926
               OOS DD 68.2165% / 1,309取引
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
m3.CAP_LOG = True                    # ← このラウンドだけ計装を有効にする

WINDOWS = {
    "W1": ("2016.11.09", "2018.11.09", 24.0),
    "W2": ("2017.11.09", "2019.11.09", 24.0),
    "W3": ("2018.11.09", "2020.11.09", 24.0),
    "OOS": ("2016.11.09", "2021.06.20", 55.0),
}
m3.WINDOWS = WINDOWS
WINS = ("OOS", "W1", "W2", "W3")     # 対照の再現確認は OOS が最も厳しい

cfg = m3.cfg
W = dict(PB_USDJPY=0.5, RSI_USDJPY=2.0, RSI_EURUSD=4.0, RSI_GBPUSD=4.0,
         PAIR=4.0, CARRY=0.75, SCA_USDJPY=4.0, SCA_GBPJPY=4.0)

# 再現を確認する既測値（ml/fxcap25/results.csv より）。
EXPECT = {
    "I000": {"OOS": (45221926.0, 1309), "W1": (6094303.0, 579),
             "W2": (1133625.0, 527), "W3": (1155866.0, 508)},
}

PROPOSALS = [
    ("I000", "Y090", "対照: X005＋cap90。再コンパイルEAが Y090 を厳密に再現すること",
     cfg(7, 1.0, 3, 90, **W)),
    ("I001", "Y100", "X005＋cap100（capが最も効く側）", cfg(7, 1.0, 3, 100, **W)),
    ("I002", "X005", "X005＋cap80（本番候補側）", cfg(7, 1.0, 3, 80, **W)),
]
ORDER = ["I000", "I001", "I002"]


def main():
    for d in (m3.RUN_DIR, m3.CONFIG_DIR, m3.DEAL_DIR):
        d.mkdir(parents=True, exist_ok=True)
    if not m3.acquire_lock():
        return
    done = m3.load_done()
    idx = {p: i for i, p in enumerate(ORDER)}
    props = sorted(PROPOSALS, key=lambda t: idx.get(t[0], 99))
    jobs = [(pid, base, desc, params, w)
            for (pid, base, desc, params) in props
            for w in WINS if (pid, w) not in done]
    if not jobs:
        print("全案・全窓が完了済みです")
        return
    import ctypes
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    try:
        m3.log(f"FXINSTR1_START jobs={len(jobs)} cap計装=ON")
        for pid, base, desc, params, window in jobs:
            row = m3.run(pid, base, desc, params, window)
            m3.append_result(row)
            exp = EXPECT.get(pid, {}).get(window)
            if exp and row.get("status") == "OK":
                ok = (abs(float(row["net"]) - exp[0]) < 1.0
                      and int(row["trades"]) == exp[1])
                m3.log(f"I000_CHECK {window} expected net={exp[0]} trades={exp[1]} "
                       f"got net={row['net']} trades={row['trades']} "
                       f"-> {'OK' if ok else 'MISMATCH'}")
                if not ok:
                    m3.log("FXINSTR1_ABORT 再現しなかった。以降は比較できないので止める")
                    return
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        (m3.ROOT / "measure.lock").unlink(missing_ok=True)
    m3.log(f"FXINSTR1_END -> {m3.OUT}")


if __name__ == "__main__":
    main()

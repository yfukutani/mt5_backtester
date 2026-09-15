"""入金額を変えて月利が動くかを見る（1:25・cap100%・X005の重み）。

【何に答えるか】
`docs/oanda_fx_fxrisk3_final_20260915.md` §5 が「**入金を増やせば月利は上がるはず**」と
未測定のまま残していた論点。第8報の cap 応答曲線で、これを測る理由がはっきりした。

**cap を 100%（証拠金の物理的な天井）まで開けても、約定は 1,310件で頭打ちになる。**
無制約なら 1,375件なので、**65件はどう頑張っても建たない。**
理由は下側の制約——証拠金予算に収まるロットが**最小ロット 0.01 を下回る**と、
`Clamp()` は cap を突き破らないために **0 を返して発注を見送る**。

【予想と、それが外れたら何を意味するか】
理屈の上では、月利（%）は入金額に対して**不変**のはずである——

    lot    = risk% × equity / SL距離        → lot ∝ equity
    必要証拠金 = lot × 契約 × 価格 / レバレッジ → 証拠金 ∝ equity
    よって 証拠金/equity は入金額によらず一定

**つまり入金を増やしても証拠金の天井は緩まない。** 緩むのは最小ロットの粒度だけで、
効くのは上の65件ぶんに限られるはず。

**もし入金を増やして月利が大きく伸びたら、この理解が間違っている**ことになる。
そのときは「50万円という資金量が本質的な制約」という結論に変わり、
打ち手が「戦略を良くする」から「資金を増やす」に移る。**どちらでも意思決定に効く。**

【測り方】
X005 の重み ＋ cap100%（＝Y100）を、入金だけ変えて OOS 55か月で回す。
Y100（入金50万円）は `ml/fxcap25/` に既測: 純益 51,320,738円・月利 8.80%・
最大DD 64.48%・1,310取引。**取引数が 1,375 に近づくかを見る。**

月利は幾何平均なので入金額が違っても直接比べられる。
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
m3.WINDOWS = {"OOS": ("2016.11.09", "2021.06.20", 55.0)}

cfg = m3.cfg
W = dict(PB_USDJPY=0.5, RSI_USDJPY=2.0, RSI_EURUSD=4.0, RSI_GBPUSD=4.0,
         PAIR=4.0, CARRY=0.75, SCA_USDJPY=4.0, SCA_GBPJPY=4.0)
PARAMS = cfg(7, 1.0, 3, 100, **W)

# (案ID, 入金額)。50万円は fxcap25 の Y100 に既測なので測り直さない。
DEPOSITS = [("D02M", 2_000_000), ("D05M", 5_000_000), ("D20M", 20_000_000)]


def main():
    for d in (m3.RUN_DIR, m3.CONFIG_DIR, m3.DEAL_DIR):
        d.mkdir(parents=True, exist_ok=True)
    if not m3.acquire_lock():
        return
    done = m3.load_done()
    jobs = [(pid, dep) for pid, dep in DEPOSITS if (pid, "OOS") not in done]
    if not jobs:
        print("全案が完了済みです")
        return
    import ctypes
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    try:
        m3.log(f"FXDEP25_START jobs={len(jobs)} leverage=1:25 cap=100")
        for pid, dep in jobs:
            # run() は m3.DEPOSIT を yaml の deposit と monthly_pct に使う。
            # 案ごとに差し替える。
            m3.DEPOSIT = dep
            row = m3.run(pid, "Y100", f"入金 {dep:,}円（Y100と同一構成・cap100%）",
                         PARAMS, "OOS")
            row["description"] = f"入金 {dep:,}円（Y100と同一構成・cap100%）"
            m3.append_result(row)
    finally:
        m3.DEPOSIT = 500000
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        (m3.ROOT / "measure.lock").unlink(missing_ok=True)
    m3.log(f"FXDEP25_END -> {m3.OUT}")


if __name__ == "__main__":
    main()

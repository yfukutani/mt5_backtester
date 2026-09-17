"""レバレッジ 1:25 で測り直す。**これまでの全 run は 1:100 で走っていた。**

【なぜこのラウンドが要るか】
2026-09-15、テスターのジャーナルに

    initial deposit 500000 JPY, leverage 1:100

と出ていることが分かった（当日の109 run すべて）。`mt5bt/runner.py` が ini に
`Leverage=25` と書いていたが、MT5 の `[Tester]` セクションは **"1:25" 形式**でないと
解釈せず、**黙って既定の 1:100 にフォールバック**していた。エラーも警告も出ない。

したがって——
- OANDA証券の実口座は**個人FXで25倍が上限**（規制）。**1:100 の結果は実口座で再現しない。**
- 「証拠金の壁は存在しなかった」（`docs/oanda_fx_margin_stage3_20260915.md`）は
  **1:100 での話**であり、1:25 では未確認。
- A10（`MarginCapPct`）が no-op だったのも 1:100 での話。**1:25 では効く可能性がある。**
- 証拠金に依存しない結論（純益の枠別内訳・上限50への張り付き・
  重みを変えても結果がほぼ同じこと）は 1:100 でも 1:25 でも成り立つとは限らない。
  ロットが証拠金で削られれば内訳も変わる。

`runner.py` は修正済みで、`verify_leverage()` が毎 run ジャーナルと突き合わせる
（短い検証 run で `レバレッジ確認: 1:25` を確認済み）。

【測る順】
証拠金が効くかどうかは**倍率の高い構成ほど早く出る**ので、
V001（T036・cap無し）を最初に回す。ここで 1:100 と結果が変われば、
「壁は無かった」は 1:25 では成り立たないと即座に分かる。

【比較の相手】同じ構成の 1:100 実測は `ml/fxmargin3/results.csv` にある。
  U000(T043)  OOS 1,213,378 / DD 29.54 / 1375取引
  U001(T036)  OOS 6,431,197 / DD 85.39 / 1375取引
  U011(重み)  OOS 182,319,948 / DD 70.48 / 1375取引
  U010(IS最適) OOS 186,665,092 / DD 69.06 / 1375取引
**取引数が 1375 を下回ったら、それが証拠金で弾かれた注文の数である。**
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
# ロック（m3.ROOT/measure.lock）は共有のまま。端末は1台しか使えない。

cfg = m3.cfg
W = {"OOS": ("2016.11.09", "2021.06.20", 55.0),
     "FULL": ("2016.11.09", "2026.06.20", 115.0)}
m3.WINDOWS = W

U011_W = dict(PB_USDJPY=0.5, RSI_USDJPY=2.0, RSI_EURUSD=4.0, RSI_GBPUSD=4.0,
              PAIR=4.0, CARRY=0.75, SCA_USDJPY=4.0, SCA_GBPJPY=4.0)

PROPOSALS = [
    ("V001", "T036", "本命: T036（mask=7/risk1%/倍率3）・cap無し。"
                     "1:100 では OOS 6,431,197円/1375取引。1:25 で何が変わるか",
     cfg(7, 1.0, 3, 0)),
    ("V004", "T036", "U011の重み・cap無し。1:100 では OOS 182,319,948円/1375取引。"
                     "口座が1億超まで育つ構成が 1:25 の証拠金に収まるはずがない、の検証",
     cfg(7, 1.0, 3, 0, **U011_W)),
    ("V000", "T043", "基準: T043（mask=23/倍率1/SCA_GJ 0.15）・cap無し。"
                     "1:100 では OOS 1,213,378円。倍率1なら 1:25 でも変わらないはず",
     cfg(23, 1.0, 1, 0, 0.15)),
    ("V002", "T036", "T036 ＋ cap80%。1:100 では完全な no-op だった。"
                     "1:25 で効くなら A10 は生き返る", cfg(7, 1.0, 3, 80)),
    ("V005", "T036", "U011の重み ＋ cap80%。A10 が重み構成を実行可能にするか",
     cfg(7, 1.0, 3, 80, **U011_W)),
    ("V006", "T036", "切り分け: RSI 3枠だけ一律4倍・cap無し。"
                     "U011 の効果が『配分』か『RSIの増レバ』かを 1:25 の土俵で決める",
     cfg(7, 1.0, 3, 0, RSI_USDJPY=4.0, RSI_EURUSD=4.0, RSI_GBPUSD=4.0)),
    ("V003", "T036", "T036 ＋ cap75%（台地の下端）", cfg(7, 1.0, 3, 75)),
]

ORDER = ["V001", "V004", "V000", "V002", "V005", "V006", "V003"]


def main():
    for d in (m3.RUN_DIR, m3.CONFIG_DIR, m3.DEAL_DIR):
        d.mkdir(parents=True, exist_ok=True)
    if not m3.acquire_lock():
        return
    done = m3.load_done()
    idx = {p: i for i, p in enumerate(ORDER)}
    props = sorted(PROPOSALS, key=lambda t: idx.get(t[0], 99))
    # OOS を全案ぶん先に回してから FULL に入る。証拠金で弾かれるかどうかは
    # OOS だけで分かるので、判断に効く数字から埋める。
    jobs = ([(p[0], p[1], p[2], p[3], "OOS") for p in props
             if (p[0], "OOS") not in done]
            + [(p[0], p[1], p[2], p[3], "FULL") for p in props
               if (p[0], "FULL") not in done])
    if not jobs:
        print("全案・両窓が完了済みです")
        return
    import ctypes
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    try:
        m3.log(f"FXLEV25_START jobs={len(jobs)} done={len(done)} leverage=1:25")
        for pid, base, desc, params, window in jobs:
            row = m3.run(pid, base, desc, params, window)
            m3.append_result(row)
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        (m3.ROOT / "measure.lock").unlink(missing_ok=True)
    m3.log(f"FXLEV25_END -> {m3.OUT}")


if __name__ == "__main__":
    main()

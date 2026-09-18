"""第16報ラウンド `ml/fxqual3` — RSI の発火機構ゲート ＋ PB 入口の律速計装。

【このラウンドの出発点】
`ml/fxqual2` の T000（計装ON対照・**Q000 と1円まで一致**＝回帰試験合格）で、
RSI 3枠の3機構（R=RSI反転 / B=BB回帰 / D=ダブルボトム）を**初めて分離できた**。
`ProcRSI()` の入口は `(rbuy||bbuy||dpb)` の OR で、退出は共通の固定SL/TPひとつしかない。

内訳（純益・円）:

| 枠 | 機構 | OOS | IS | 両窓の符号 |
|---|---|---:|---:|---|
| RSI_UJ | D 単独 | +3,833 | +6,933 | **両窓＋** |
| RSI_UJ | B 単独 | −2,357 | −1,191 | **両窓−** |
| RSI_UJ | R 単独 | −499 | −491 | 両窓−（各1件・ノイズ） |
| RSI_UJ | RBD | +4,582 | +1,817 | 両窓＋ |
| RSI_UJ | BD | +2,616 | −1,492 | 割れる |
| RSI_UJ | RB | −305 | +1,443 | 割れる |
| RSI_GU | B 単独 | +11,991 | +13,453 | **両窓＋** |
| RSI_GU | RB | +5,199 | −167 | 割れる |
| RSI_EU | B 単独 | −4,214 | +10,492 | **反転** |
| RSI_EU | RB | +9,734 | −3,787 | **反転** |
| RSI_EU | R 単独 | −1,715 | +1,325 | 反転（6件/3件・ノイズ） |

【読み】
- **USDJPY は「ダブルボトム(D)を含む足」で勝ち、「BB回帰(B)単独」で負ける。両窓で同じ符号。**
- **GBPUSD は B 単独が主戦力。両窓で同じ符号。落とすものが無い。**
- **EURUSD は勝つ機構が窓で入れ替わる。**B と RB が両方とも符号反転している。
  これは「どちらを残すか」の問題ではなく、**この枠の入口が窓に対して不安定**という意味である。
  したがって **EURUSD に機構ゲートを当てるのは、窓に合わせた後付けにしかならない。**
  測りはするが（V003）、**両窓で良くなることは期待していない。**

【効き幅の見積もり — 先に書いておく】
両窓で符号が揃っているものだけを落とす案（V001）の素朴な足し算は
**OOS +2,856円 / IS +1,682円**。月利に直すと **+0.010pt / +0.006pt** である。
目標（月利6%）に対しては**無に等しい。** それでもやるのは、
第14報の21案が**1件も両窓改善しなかった**ので、まず「両窓で改善する案が存在するのか」を
1件でも作ることに意味があるからである。**収益目標への前進としては期待していない。**

（素朴な足し算が当たる保証も無い。ゲートで落とした足ではフラグを消費しないので、
  「単独では建てず合流を待つ」動きになり、**落とした取引の分だけ減る**のではなく
  **別の足で別の取引が生まれる**。だから実測する。）

【PB 入口の律速（同時に測る）】
第14報で PB GBPJPY の ADX を 30→22.5 にしても 115か月で取引が5件しか増えなかった。
**律速は ADX ではない。** 何が律速かを推測で潰すのはもう止めて、数える。
`PbDiagCounters=true` で、入口8条件それぞれについて
「**その条件以外の7つが全部成立していたバー数**」を数える（leave-one-out）。
差し引きが「その条件だけで落ちたバー数」＝律速の強さになる。
**カウンタを回すだけで売買には触れない**ので、V000 は T000 と一致しなければならない。

【回帰試験を先に置く】
V000 は fxqual2 の T000（＝fxqual1 の Q000）と **純益・DD・取引数が1円まで一致**しなければ
ならない。新しい input（`RsiMechMask_*` / `PbDiagCounters`）は既定で挙動を変えない**はず**
だが、「はず」で済ませると以降の数字が前ラウンドと並べられない。
一致しなければそこで止める。
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
# PB の律速カウンタは CapLogFile に相乗りして出る。cap 自体は MarginCapPct=0 で無効。
m3.CAP_LOG = True

# fxqual1 / fxqual2 と同一の窓。ここを変えると前ラウンドと並べられない。
m3.WINDOWS = {
    "OOS": ("2016.11.09", "2021.06.20", 55.0),
    "IS":  ("2021.06.20", "2026.06.20", 60.0),
}
WINS = ("OOS", "IS")

# fxqual2 の T000 と同一（本番現行サイジング＋計装ON）。差は機構ゲートだけ。
PARAMS = {
    "GlobalLotMult": 1,
    "MarginCapPct": 0,
    "BrokerMaxLot": 0,
    "FxRiskMask": 0, "FxRiskPct": 0.5, "FxRiskRefCap": 0,
    "RefCap_PB_USDJPY": 78000, "RefCap_PB_GBPJPY": 78000, "RefCap_CARRY": 78000,
    "TagDealTriggers": True,
    "PairSkipAtStop": False, "PairEqualNotional": False,
    "PairMaxHoldBars": 0, "PairEntryZOv": 0.0,
    # 第16報の新入力は**全案で明示的に既定値を書く**（Codex の査読より）。
    "RsiMechMask_UJ": 0, "RsiMechMask_EU": 0, "RsiMechMask_GU": 0,
    "PbDiagCounters": True,
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


# 組み合わせコード: R=1 / B=2 / D=4 の OR。マスクは 1<<(コード-1) の OR。
R, B, D = 1, 2, 4
def mask(*codes):
    m = 0
    for c in codes:
        m |= 1 << (c - 1)
    return m


ALL7 = mask(1, 2, 3, 4, 5, 6, 7)          # 127 ＝ 全許可（0 と同義だが明示用）
NO_SINGLE_RB = mask(3, 4, 5, 6, 7)        # 124 ＝ R単独・B単独を落とす
D_ONLY = mask(4, 5, 6, 7)                 # 120 ＝ D を含む足だけ
NO_SINGLE_R = mask(2, 3, 4, 5, 6, 7)      # 126 ＝ R単独だけ落とす
B_ONLY = mask(2)                          #   2 ＝ B 単独だけ

PROPOSALS = [
    ("V000", "fxqual2/T000",
     "対照: 機構ゲート全部OFF＋PB律速カウンタON。T000/Q000 と1円まで一致すること", PARAMS),

    # --- 両窓で符号が揃っているものだけを落とす（本命・とはいえ効き幅は月利+0.01pt）---
    ("V001", "V000", "RSI USDJPY: R単独・B単独を落とす（両窓とも負けている機構）",
     t(RsiMechMask_UJ=NO_SINGLE_RB)),
    ("V002", "V000", "RSI USDJPY: ダブルボトムを含む足だけ（D/DB/DR/DRB）",
     t(RsiMechMask_UJ=D_ONLY)),

    # --- 窓で符号が割れる枠。期待していないが、割れていることを数字で残す ---------
    ("V003", "V000", "RSI EURUSD: R単独を落とす（両窓で符号が反転する枠・期待薄）",
     t(RsiMechMask_EU=NO_SINGLE_R)),
    ("V004", "V000", "RSI GBPUSD: B単独だけ（RB を落とす。OOS −5,199 なので期待薄）",
     t(RsiMechMask_GU=B_ONLY)),

    # --- Codex の第1推奨（反証試験として測る）---------------------------------
    # Codex に意見を求めた時点では OOS の内訳しか渡せていなかったため、
    # 「EURUSD は RB のみが唯一の強い候補」が第1推奨として返ってきた。
    # その後に出た IS の内訳では **RB が −3,787 で B単独が +10,492 と符号が逆**である。
    # つまりこれは「OOS で選んで IS で落ちる」典型のはずで、私は**外れると予想する**。
    # それでも測るのは、予想を先に書いた反証試験が安いからである（2run）。
    ("V007", "V000",
     "RSI EURUSD: RB 同時発火のみ（Codex 第1推奨・OOSで選んだ形。ISで落ちると予想）",
     t(RsiMechMask_EU=mask(3))),

    # --- 合成 -----------------------------------------------------------------
    ("V005", "V001", "合成: UJ(R単独B単独を落とす) ＋ EU(R単独を落とす)",
     t(RsiMechMask_UJ=NO_SINGLE_RB, RsiMechMask_EU=NO_SINGLE_R)),
    ("V006", "V002", "合成: UJ(Dを含む足だけ) ＋ EU(R単独を落とす)",
     t(RsiMechMask_UJ=D_ONLY, RsiMechMask_EU=NO_SINGLE_R)),
]

# 対照が最初。次に両窓の根拠がある2件。それから期待薄の対照群、最後に合成。
# 途中で止まっても判断に効く数字から埋まる並びにする。
ORDER = ["V000", "V001", "V002", "V007", "V005", "V006", "V003", "V004"]


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
        m3.log(f"FXQUAL3_START jobs={len(jobs)} RSI機構ゲート7案＋対照")
        for pid, base, desc, params, window in jobs:
            row = m3.run(pid, base, desc, params, window)
            m3.append_result(row)
            if pid == "V000" and row.get("status") != "OK":
                m3.log("FXQUAL3_ABORT 対照が失敗した。回帰試験が取れないので中止")
                return
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        (m3.ROOT / "measure.lock").unlink(missing_ok=True)
    m3.log(f"FXQUAL3_END -> {m3.OUT}")


if __name__ == "__main__":
    main()

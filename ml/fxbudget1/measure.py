"""枠ごとの証拠金予算を刻む（第13報・Codex #4）。

【なぜこれを測るのか】
第10報の cap 計装で3つ分かった。

    ① 注文だけで数えた通過率は **30.2%**（通期OOS・cap90）。RSI EURUSD は **23.8%** しか通らない。
    ② cap を 80→100 に 20pt 開けても通過率は 5.6pt しか動かないのに、OOS窓中央値は 0.78pt 動く。
       **効いているのは総量ではなく「通る取引の顔ぶれ」。**
    ③ `Mult_*` は cap を上回る領域では**何も変えない**（希望を変えても cap が先に決める）。

③ のため、顔ぶれを変えるには「希望を下げる」のではなく
**「その枠が取れる上限を下げる」**必要がある。EA に `Bud_*`
（1注文の所要証拠金が equity の何%までか・既定0で無効）を足した。
`Mult_*` と違い **cap と同じ側（上限）に効くので、cap の下でも必ず通る。**

【空白がどこにあるか】
fxeff1 が RSI EURUSD について測ったのは2点だけである。

    全停止（E03）      OOS窓中央値 **2.44%**   ← 証拠金を空けても置く先が無かった
    重み 4.0→2.0（E12） 対照と1円まで同一        ← cap の上なので効かなかった

**「止める」と「効かない」の間**、つまり「止めずに小さくした場合」は一度も測っていない。

【土俵 — ここが前ラウンドと違う】
`ml/fxvmax1`（第12報）で **業者の1注文上限を OANDA 実機の 10ロット**にした結果が出ているので、
本ラウンドは**最初からその土俵で測る**。

    BrokerMaxLot = 10   （OANDA証券の実機値。XM は 50）
    MarginCapPct = 90   （cap100 は証拠金維持率100%＝追証ラインで実運用できない）
    X005 の重み・FxRiskMask=7・risk 1.0%・RefCap=0・倍率3

対照 B000 は `ml/fxvmax1` の **O003（cap90＋上限10）と1円まで一致**しなければならない。
一致しなければ `Bud_*` の追加が既定挙動を壊しているので、そこで止める。

【予想 — 外すと恥ずかしいので先に書く】
RSI EURUSD は希望の 76% を cap に捨てられている。予算で上限を切ると、
**捨てられる量は減らないが、捨てられる「場所」が変わる**（大きい注文が削られ、
小さい注文が通るようになる）。第10報 ② から、これは中央値を動かすはずである。
**向きは分からない。** 上がる根拠と同じだけ下がる根拠がある（E03 は下がった）。

【留保】
- OOS窓は3本しかなく、cap も重みも W1〜W3 を見て選んでいる。**完全な holdout ではない。**
- ここで良い予算が見つかっても、それは **W1〜W3 に当てた値**である。
- フィード・スプレッド・スワップは **XM のもの**。OANDA端末での確認は別途必要。
"""
from __future__ import annotations

import csv
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
m3.CAP_LOG = True          # 予算が何をどれだけ削ったかを枠別に残す

WINDOWS = {
    "W1": ("2016.11.09", "2018.11.09", 24.0),
    "W2": ("2017.11.09", "2019.11.09", 24.0),
    "W3": ("2018.11.09", "2020.11.09", 24.0),
    "OOS": ("2016.11.09", "2021.06.20", 55.0),
}
m3.WINDOWS = WINDOWS
WINS = ("W1", "W2", "W3", "OOS")

cfg = m3.cfg
W = dict(PB_USDJPY=0.5, RSI_USDJPY=2.0, RSI_EURUSD=4.0, RSI_GBPUSD=4.0,
         PAIR=4.0, CARRY=0.75, SCA_USDJPY=4.0, SCA_GBPJPY=4.0)

BUD_KEYS = ("Bud_PB_USDJPY", "Bud_PB_GBPJPY", "Bud_RSI_USDJPY", "Bud_RSI_EURUSD",
            "Bud_RSI_GBPUSD", "Bud_PAIR", "Bud_CARRY", "Bud_SCA_USDJPY",
            "Bud_SCA_GBPJPY")


def bud(cap=90, mult=3, maxlot=10, **budgets):
    """X005＋上限10＋cap90 をベースに、枠ごとの証拠金予算だけ動かす。"""
    p = cfg(7, 1.0, mult, cap, **W)
    p["BrokerMaxLot"] = maxlot
    for k, v in budgets.items():
        if k not in BUD_KEYS:
            raise KeyError(f"未知の予算入力: {k}（綴りを確認）")
        p[k] = v
    return p


PROPOSALS = [
    # --- 対照: 予算を掛けない。fxvmax1 の O003 を1円まで再現しなければ以降は無効 ---
    ("B000", "O003", "対照: Bud_* 全て0（＝O003 と同一挙動のはず）", bud()),

    # --- 本題: RSI EURUSD の予算を刻む（「全停止」と「効かない」の間）-----------
    ("B001", "B000", "RSI EU の1注文を equity の 10% までに制限", bud(Bud_RSI_EURUSD=10.0)),
    ("B002", "B000", "RSI EU を 20% まで", bud(Bud_RSI_EURUSD=20.0)),
    ("B003", "B000", "RSI EU を 30% まで", bud(Bud_RSI_EURUSD=30.0)),
    ("B004", "B000", "RSI EU を 40% まで", bud(Bud_RSI_EURUSD=40.0)),

    # --- PairTrade は「通過量」の 48.9% を占める最大の消費者（第10報 §3）--------
    #     Pair は1回の希望が小さく通過率 88.1%＝**cap の恩恵を最も受けている枠**。
    #     RSI EU から証拠金を奪っているのは Pair ではないか、を測る。
    ("B005", "B000", "Pair の1注文を equity の 10% までに制限", bud(Bud_PAIR=10.0)),
    ("B006", "B000", "Pair を 20% まで", bud(Bud_PAIR=20.0)),

    # --- risk%枠をまとめて絞る（一律版・#9）------------------------------------
    ("B007", "B000", "RSI 3枠を一律 20% まで",
     bud(Bud_RSI_EURUSD=20.0, Bud_RSI_GBPUSD=20.0, Bud_RSI_USDJPY=20.0)),
    ("B008", "B000", "全9枠を一律 20% まで",
     bud(**{k: 20.0 for k in BUD_KEYS})),

    # --- 勝ち残った1本と Carry 停止（fxeff1 E01）の組み合わせ -------------------
    #     Carry は W2/W3/通期のすべてで負けている（第10報 §4b）。
    ("B009", "B000", "RSI EU 20% ＋ Carry の予算を 2%（ほぼ止めるが分散は残す）",
     bud(Bud_RSI_EURUSD=20.0, Bud_CARRY=2.0)),
]

# 対照 → RSI EU の刻み → Pair → 一律 の順。途中で止まっても判断に効く順に並べる。
ORDER = ["B000", "B002", "B003", "B001", "B004", "B005", "B009",
         "B007", "B006", "B008"]


def expect_from_vmax():
    """fxvmax1 の O003 を「対照が一致すべき値」として読む。

    自分で数字を書き写すと転記ミスが入るので、results.csv から引く。
    O003 がまだ無ければ空を返し、対照チェックはスキップする（その旨をログに残す）。
    """
    path = REPO / "ml" / "fxvmax1" / "results.csv"
    if not path.exists():
        return {}
    out = {}
    for r in csv.DictReader(open(path, encoding="utf-8")):
        if r.get("proposal_id") == "O003" and r.get("status") == "OK":
            out[r["window"]] = (float(r["net"]), int(r["trades"]))
    return out


def main():
    for d in (m3.RUN_DIR, m3.CONFIG_DIR, m3.DEAL_DIR):
        d.mkdir(parents=True, exist_ok=True)
    if not m3.acquire_lock():
        return
    expect = expect_from_vmax()
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
        m3.log(f"FXBUDGET1_START jobs={len(jobs)} 枠ごとの証拠金予算 "
               f"BrokerMaxLot=10 cap=90 leverage=1:25")
        if not expect:
            m3.log("FXBUDGET1_WARN fxvmax1 の O003 が見つからない。"
                   "対照の一致確認をスキップする（比較の土台が弱くなる）")
        for pid, base, desc, params, window in jobs:
            row = m3.run(pid, base, desc, params, window)
            m3.append_result(row)
            if pid == "B000" and window in expect and row.get("status") == "OK":
                en, et = expect[window]
                ok = (abs(float(row["net"]) - en) < 1.0
                      and int(row["trades"]) == et)
                m3.log(f"B000_CHECK {window} expected net={en} trades={et} "
                       f"got net={row['net']} trades={row['trades']} "
                       f"-> {'OK' if ok else 'MISMATCH'}")
                if not ok:
                    m3.log("FXBUDGET1_ABORT Bud_* 既定0 が O003 と一致しない。"
                           "EAの変更が既定挙動を壊している。以降は比較できない")
                    return
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        (m3.ROOT / "measure.lock").unlink(missing_ok=True)
    m3.log(f"FXBUDGET1_END -> {m3.OUT}")


if __name__ == "__main__":
    main()

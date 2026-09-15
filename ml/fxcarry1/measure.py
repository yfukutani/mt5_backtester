"""Carry を「止めるか残すか」の二択ではなく、間を測る（第11報）。

【なぜ Carry だけを掘るのか】
fxeff1（16案・64run）で切り分けたところ、**効いていたのは Carry 1枠だけ**だった。

    Y100 対照              中央値 5.60% / 平均 7.44% / 最悪 4.96%
    E01  Carry のみ止める   中央値 8.17% / 平均 8.19% / 最悪 3.54%
    E05  3枠とも止める      中央値 7.19% / 平均 7.75% / 最悪 3.50%
    E03  RSI EU のみ止める  中央値 2.44% / 平均 5.84% / 最悪 1.71%

**Carry だけを外すほうが、3枠とも外すより良い。** PB UJ と RSI EU を外したのは差し引きマイナス。
そして E01 は**これまでで唯一、中央値だけでなく平均も動いた案**である（+0.75pt）。
他の案は中央値が平均の5倍動く＝再配分でしかなかった。

【ただし止めると分散を失う】
第9報 §4・§5b で事前に書いた2つの留保が、実測でそのまま出た。

    - W4（全構成が負ける唯一の窓）で2番目に稼いだのは Carry（+199,810円）
    - Carry は IS で PB UJ と −0.61・Pair と −0.57 の逆相関

E01 は**最悪窓が 4.96% → 3.54% に落ちている**（−1.42pt）。分散を失ったぶんである。

**だから二択で決めない。** Carry の「何が悪いのか」を分けて測る:

    サイズ    重みを下げる（`Mult_CARRY`）
    複利      口座とともに大きくなるのを止める（`RefCap_CARRY` を固定額に）
    保有期間  平均 184.8日 を切る（`CarryHoldBars`・第9報 A10）
    退出条件  ヒステリシス帯の代わりに退出SMA（`CarryExitPeriod`・Codex #21）

どれか1つが Carry の毒であって、残りは分散源として残せるかもしれない。
**残せるなら、最悪窓を落とさずに中央値・平均を取れる。**

【土俵】
すべて X005 の重み・`FxRiskMask=7`・risk 1.0%・`RefCap=0`・倍率3・**cap100**。
E01 と直接比べるための土俵である。cap100 は追証ラインで実運用できないので、
勝ち残った構成は最後に cap90（実用域）でも測る。
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


# 第11報で EA に足した入力（既定はどちらも 0＝現行と同一挙動）。
NEW_INPUTS = ("CarryHoldBars", "CarryExitPeriod")


def carry(cap=100, mult=3, off=False, **over):
    """X005 をベースに Carry まわりだけ動かす。

    `over` に置ける鍵: Mult_CARRY / RefCap_CARRY / CarryHoldBars / CarryExitPeriod
    """
    w = dict(W)
    if "Mult_CARRY" in over:
        w["CARRY"] = over.pop("Mult_CARRY")
    p = cfg(7, 1.0, mult, cap, **w)
    for k, v in over.items():
        # BASE は fxrisk3 の雛形なので、第11報で足した入力はまだ載っていない。
        # 綴り間違いを拾うために、新設分は明示的に許可する。
        if k not in m3.BASE and k not in p and k not in NEW_INPUTS:
            raise KeyError(f"未知の入力: {k}")
        p[k] = v
    if off:
        p["En_CARRY"] = False
    return p


PROPOSALS = [
    # --- 対照 -------------------------------------------------------------
    ("C00", "Y100", "対照: X005＋cap100（Carry そのまま・既測 Y100 の再現確認）",
     carry()),
    ("C09", "E01", "対照: Carry を止める（fxeff1 E01 の再現確認）", carry(off=True)),

    # --- サイズを下げる（止めずに小さくする）------------------------------
    ("C01", "Y100", "Carry の重みを 0.75→0.375（半分）", carry(Mult_CARRY=0.375)),
    ("C02", "Y100", "Carry の重みを 0.75→0.15（ほぼ消す・残すのは分散だけ）",
     carry(Mult_CARRY=0.15)),

    # --- 複利を止める（口座とともに大きくなるのを止める）------------------
    ("C03", "Y100", "Carry の複利を止める（RefCap=500,000＝入金額で固定）",
     carry(RefCap_CARRY=500000)),
    ("C04", "Y100", "Carry の複利を 2,000,000 で頭打ちにする",
     carry(RefCap_CARRY=2000000)),

    # --- 保有期間を切る（平均184.8日）------------------------------------
    ("C05", "Y100", "Carry の保有上限 60日（第9報 A10）", carry(CarryHoldBars=60)),
    ("C06", "Y100", "Carry の保有上限 30日", carry(CarryHoldBars=30)),
    ("C07", "Y100", "Carry の保有上限 120日", carry(CarryHoldBars=120)),

    # --- 退出条件を変える（Codex #21）-------------------------------------
    ("C10", "Y100", "Carry の退出をSMA40割れに（ヒステリシス帯の代わり）",
     carry(CarryExitPeriod=40)),
    ("C11", "Y100", "Carry の退出をSMA20割れに（より早く切る）",
     carry(CarryExitPeriod=20)),
]

# 効きの大きそうな順。C00 の再現確認を最初に置く（EAを再コンパイルしているため）。
ORDER = ["C00", "C09", "C03", "C05", "C02", "C10", "C01", "C06", "C04", "C11", "C07"]

# 再コンパイル後に一致しなければならない既測値。
# C00 = Y100（ml/fxcap25）, C09 = E01（ml/fxeff1）
EXPECT = {
    "C00": {"W1": (6725965.0, 579), "W2": (1348701.0, 529),
            "W3": (1097587.0, 508), "OOS": (51320738.0, 1310)},
}


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
        m3.log(f"FXCARRY1_START jobs={len(jobs)} done={len(done)}")
        for pid, base, desc, params, window in jobs:
            row = m3.run(pid, base, desc, params, window)
            m3.append_result(row)
            exp = EXPECT.get(pid, {}).get(window)
            if exp and row.get("status") == "OK":
                ok = (abs(float(row["net"]) - exp[0]) < 1.0
                      and int(row["trades"]) == exp[1])
                m3.log(f"C00_CHECK {window} expected net={exp[0]} trades={exp[1]} "
                       f"got net={row['net']} trades={row['trades']} "
                       f"-> {'OK' if ok else 'MISMATCH'}")
                if not ok:
                    m3.log("FXCARRY1_ABORT 再現しなかった。比較できないので止める")
                    return
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        (m3.ROOT / "measure.lock").unlink(missing_ok=True)
    m3.log(f"FXCARRY1_END -> {m3.OUT}")


if __name__ == "__main__":
    main()

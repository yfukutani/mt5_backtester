"""risk% を「最小ロットの壁」を越える水準に校正し直した比較条件。

【fxrisk2 が失敗した理由】
SCAのrisk%化バグを直した直後のラウンド（fxrisk2）で、risk% を 0.05 / 0.1 / 0.25 と
低く振った。SCA GBPJPY の Revブースト×6 で実効リスクが risk%×6 になるのを恐れたためである。

**その水準ではロットが 0.01 に丸め戻され、固定ロットと完全に同じ結果になった。**
実測: S003（mask=8・risk 0.05%）の FULL は S001（mask=0）と
純益 911,736円・最大DD 10.8347%・取引数 2,969 まで完全一致した。

deal ログからSL距離を取って逆算すると、基準資金25万で 0.02 ロット以上になる取引の割合は:

    risk%    SCA USDJPY   SCA GBPJPY   RSI USDJPY   RSI EURUSD   RSI GBPUSD
    0.05          0.0%         0.0%         0.0%         0.0%         0.0%
    0.10          0.0%         0.0%         0.0%         0.0%         0.0%
    0.25         11.1%         0.4%         0.0%        58.3%         0.0%
    0.50         57.1%        37.7%       100.0%       100.0%        57.5%
    0.75         79.6%        74.9%       100.0%       100.0%       100.0%
    1.00         93.9%        91.0%       100.0%       100.0%       100.0%
    2.00        100.0%        99.8%       100.0%       100.0%       100.0%

**基準資金25万・最小ロット0.01では、risk% が 0.5% を下回ると意味を持たない。**
1ロットのSL損失は SCA USDJPY で中央値 56,800円、SCA GBPJPY で 70,500円。
0.01ロットでも 568円 / 705円のリスクがあり、これは 25万の 0.23% / 0.28% に相当する。
**口座が小さいほど risk% の刻みは粗くなる**（Codex #5「最小ロットへの強制切上げ」）。

【本ラウンドの水準】
- 非複利（`FxRiskRefCap=250,000`）: **0.5 / 1.0 / 2.0**
- equity連動（`FxRiskRefCap=0`）: 開始equityが50万＝基準の2倍なので **0.25 / 0.5 / 1.0**

SCA GBPJPY の risk 2.0% はブースト時に実効12%となり破綻side に振れるはずだが、
**どこで壊れるかを知ること自体が目的**（Claude案 A6 / D2）なので意図的に含める。

【A群は fxrisk2 から結果を流用する】
T001 / T002 は fxrisk2 の S001 / S002 とパラメータが完全に同一。
測定済みなので results.csv に転記して再測定を省く（deal ログは fxrisk2 のものを参照）。
"""
from __future__ import annotations

import csv
import json
import math
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FIELDS = ["proposal_id", "family", "description", "parameter_json"]
MULTS = tuple("Mult_" + s for s in (
    "PB_USDJPY", "PB_GBPJPY", "PB_GOLD", "RSI_USDJPY", "RSI_EURUSD",
    "RSI_GBPUSD", "PAIR", "CARRY", "VBO", "ETH", "BTC_FUND", "BFXREV",
    "SCA_GOLD", "SCA_USDJPY", "SCA_GBPJPY"))
REFCAPS = ("RefCap_PB_USDJPY", "RefCap_PB_GBPJPY", "RefCap_CARRY")
LAB = ("FxRiskMask", "FxRiskPct", "FxRiskRefCap")


def parameters(raw):
    p = json.loads(raw)
    if not isinstance(p, dict) or set(p) != {*MULTS, *REFCAPS, *LAB, "GlobalLotMult"}:
        raise ValueError("比較軸以外の変更、またはパラメータの指定漏れがあります")
    if any(isinstance(v, bool) or not isinstance(v, (int, float))
           or not math.isfinite(v) for v in p.values()):
        raise ValueError("パラメータは有限の数値にしてください")
    if not isinstance(p["FxRiskMask"], int) or not 0 <= p["FxRiskMask"] <= 31:
        raise ValueError("FxRiskMaskは0〜31の整数にしてください")
    if p["FxRiskPct"] <= 0 or p["FxRiskRefCap"] < 0:
        raise ValueError("FxRiskPctは正、FxRiskRefCapは非負にしてください")
    # fxrisk2 の失敗を繰り返さないための歯止め。
    # 基準資金25万・最小ロット0.01では 0.25% 未満はロットが動かず、測定が無意味になる。
    if p["FxRiskMask"] != 0 and p["FxRiskPct"] < 0.25:
        raise ValueError("FxRiskPctが0.25%未満では最小ロットに丸められ、測定の意味がありません")
    if len({p[k] for k in REFCAPS}) != 1 or p[REFCAPS[0]] < 0:
        raise ValueError("3枠のRefCapは同一の非負値にしてください")
    if p["GlobalLotMult"] not in (1, 2, 3):
        raise ValueError("倍率は1・2・3のいずれかにしてください")
    # 枠別重みは原則1.0に固定してサイジング軸の効果を分離する。
    # 例外は Mult_SCA_GBPJPY だけ——J群で「SCA GBPJPYのロットだけ絞る」ことを測るため。
    # SCA GBPJPY の scaBoostMult=6.0 は固定ロット0.01の前提で調整された値で、
    # risk%化するとリスク調整済みのロットをさらに6倍するため、実効リスクが risk%×6 になる。
    # T039 の証拠金ピークは FULL で 87%・OOS で 70% がこの1枠の1建玉だった。
    for k in MULTS:
        if k == "Mult_SCA_GBPJPY":
            if not 0.0 < p[k] <= 1.0:
                raise ValueError("Mult_SCA_GBPJPYは0より大きく1.0以下にしてください")
            continue
        if p[k] != 1.0:
            raise ValueError("サイジング軸の効果を分離するため、枠別重みは1.0に固定してください")
    return p


def generate():
    rows = []
    seen = set()

    def add(family, mask, risk, fxref, refcap, mult, scagj=1.0):
        p = dict.fromkeys(MULTS, 1.0)
        p["Mult_SCA_GBPJPY"] = scagj
        p.update(dict.fromkeys(REFCAPS, refcap))
        p.update(FxRiskMask=mask, FxRiskPct=risk, FxRiskRefCap=fxref, GlobalLotMult=mult)
        raw = json.dumps(p, sort_keys=True, separators=(",", ":"))
        parameters(raw)
        if raw in seen:
            return
        seen.add(raw)
        desc = (f"マスク={mask} / risk%={risk:g} / FxRiskRefCap={fxref} "
                f"/ RefCap={refcap} / 倍率={mult}")
        if scagj != 1.0:
            desc += f" / SCA_GJ重み={scagj:g}"
        rows.append(dict(proposal_id=f"T{len(rows) + 1:03d}", family=family,
                         description=desc, parameter_json=raw))

    # A: 対照。fxrisk2 の S001 / S002 と同一パラメータで、結果を流用する。
    add("A", 0, 0.5, 0, 250000, 1)
    add("A", 7, 0.5, 0, 250000, 1)

    # B: SCAを1枠ずつ。どちらの枠がどれだけ効くかを分離する。
    for mask in (8, 16):
        for risk in (0.5, 1.0, 2.0):
            add("B", mask, risk, 250000, 250000, 1)

    # C: SCA 2枠。fxref で「単なる増量」と「複利」を分ける。
    for risk in (0.5, 1.0, 2.0):
        add("C", 24, risk, 250000, 250000, 1)
    for risk in (0.25, 0.5, 1.0):
        add("C", 24, risk, 0, 250000, 1)

    # D: RSI3枠＋SCA2枠。非複利で増量効果だけを見る。
    for risk in (0.5, 1.0, 2.0):
        add("D", 31, risk, 250000, 250000, 1)

    # E: 5枠を equity 連動に。既存3枠は RefCap=250,000 のまま。
    for risk in (0.25, 0.5, 1.0):
        add("E", 31, risk, 0, 250000, 1)

    # F: 9枠中8枠が equity 連動（Pairのみ固定）＝最大複利。
    for risk in (0.25, 0.5, 1.0, 2.0):
        add("F", 31, risk, 0, 0, 1)

    # G: 最大複利に全体倍率を重ねる。どこで証拠金・DDが壊れるかを特定する（A6/D2）。
    for risk in (0.25, 0.5, 1.0):
        for mult in (2, 3):
            add("G", 31, risk, 0, 0, mult)

    # H: RSI 3枠だけを risk% 化した最大複利のフロンティア。
    #    T003 で SCA の risk%化が逆効果（黒字→赤字）と判明したため、
    #    **SCAを固定ロットのまま残した mask=7 が実務上の本命**になった。
    #    fxrisk1 の G群（実質 mask=7）は risk 0.1/0.25/0.5 × 倍率1/2 までしか測っておらず、
    #    **risk 1.0% と 倍率3 は未測定**。そこを埋める。
    for risk in (0.5, 1.0):
        for mult in (1, 2, 3):
            add("H", 7, risk, 0, 0, mult)

    # I: **RSI 3枠 ＋ SCA GBPJPY** を risk%化（mask = 1+2+4+16 = 23）。
    #    T003〜T006 の実測で、risk%化の符号が枠ごとに逆だと判明した。
    #      SCA USDJPY  16,339 → −5,881 → −16,315 → −31,385（risk 0.5/1.0/2.0・単調に破壊）
    #      SCA GBPJPY 115,992 → 172,652（risk 0.5・+48.9%。OOSでも +21.6%）
    #    狭いレンジ層が USDJPY は赤字・GBPJPY は黒字だったことと整合する（§4d）。
    #    **有害な SCA USDJPY だけを外し、有益な SCA GBPJPY を入れた構成**が
    #    当初の案に無かったので追加する。H群の最良条件（最大複利）に揃える。
    for risk in (0.5, 1.0):
        for mult in (1, 2):
            add("I", 23, risk, 0, 0, mult)

    # J: I群の証拠金問題を **SCA GBPJPY のロットだけ絞って** 解く。EA改修は不要。
    #    T039（mask=23・risk1.0・倍率1）は「上位3か月を除いた成長率 1.33%」で
    #    mask=7 の最良（0.97%）を大きく上回ったが、証拠金が OOS 215% で実行できない。
    #    その証拠金ピークの **FULL 87% / OOS 70% が SCA GBPJPY の1建玉**だった。
    #    原因は scaBoostMult=6.0——固定ロット0.01の前提で調整された値なので、
    #    risk%化するとリスク調整済みのロットをさらに6倍してしまう。
    #    Mult_SCA_GBPJPY で打ち消せば、複利の恩恵を残したまま証拠金を下げられるはず。
    for scagj in (0.2, 0.1, 0.15, 0.35, 0.5):
        add("J", 23, 1.0, 0, 0, 1, scagj)
    add("J", 23, 0.5, 0, 0, 1, 0.35)

    return rows


def load_proposals(path=ROOT / "proposals.csv"):
    with open(path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != FIELDS:
            raise ValueError("proposals.csvのヘッダーが一致しません")
        rows = list(reader)
    expected = {r["proposal_id"]: r for r in generate()}
    if len(rows) != len(expected) or {r["proposal_id"] for r in rows} != set(expected):
        raise ValueError(f"T001〜T{len(expected):03d}の{len(expected)}案すべてが必要です")
    for r in rows:
        e = expected[r["proposal_id"]]
        if (parameters(r["parameter_json"]) != parameters(e["parameter_json"])
                or any(r[k] != e[k] for k in ("family", "description"))):
            raise ValueError(f"{r['proposal_id']}の設定または説明が設計と異なります")
    return rows


def main():
    rows = generate()
    ROOT.mkdir(parents=True, exist_ok=True)
    with open(ROOT / "proposals.csv", "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    duplicates = len(rows) - len({r["parameter_json"] for r in rows})
    print(f"総数={len(rows)} / 内訳={dict(Counter(r['family'] for r in rows))} / 重複={duplicates}")


if __name__ == "__main__":
    main()

"""第10ラウンドの判定表（幾何月利・最大DD・枠別）を出す。

使い方: `python ml\fxqual10\report.py`

**判定に必要なものを1枚にまとめる**のが目的である:
- ブックの**幾何月利**（目標6%はこれで定義されている）と**最大DD**、**口座破綻の有無**
- **SCA 2枠の枠別純益**（`G008`/`G009` が何をしたかは、ここを見ないと分からない）
- **測る前に書いた予測との差**

⚠️ **ラウンドをまたいで枠別 CSV を引き算してはいけない**（第16報より前は配賦の版が違い、
Carry はスワップでドリフトする）。本スクリプトは**ラウンド内で閉じて**比較する。
"""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEPOSIT = 500_000.0
MONTHS = {"OOS": 55.0, "IS": 60.0, "FULL": 115.0}

# 測る前に書いた予測（`docs/oanda_fx_sleeve_quality_round10_20260919.md` §4）。
# **素朴な差分であって実測の予言ではない。** 複利では equity 経路が変わるので一致しない。
NAIVE = {
    ("G008", "OOS"): -264_788, ("G008", "IS"): +695_109,
    ("G009", "OOS"): -207_217, ("G009", "IS"): +543_569,
    ("G001", "OOS"): +17_379,  ("G001", "IS"): +78_447,
    ("G002", "OOS"): +52_840,  ("G002", "IS"): +55_539,
    ("G003", "OOS"): +29_228,  ("G003", "IS"): +21_102,
    ("G004", "OOS"): +98_008,  ("G004", "IS"): +35_831,
    ("G005", "OOS"): +74_431,  ("G005", "IS"): -24_875,
    ("G007", "OOS"): +64_172,  ("G007", "IS"): -119_159,
    ("G006", "OOS"): +59_795,  ("G006", "IS"): -170_103,
}

DESC = {
    "G000": "対照（F003: 全複利・倍率1＋採用候補2件）",
    "G008": "SCA GBPJPY を risk% から外す（mask=15）",
    "G009": "SCA 2枠を risk% から外す（mask=7）",
    "G006": "SCA USDJPY を丸ごと外す（基準線）",
    "G001": "SCA UJ レンジ幅下限 0.0026",
    "G002": "SCA UJ レンジ幅下限 0.0030",
    "G003": "SCA UJ レンジ幅下限 0.0036",
    "G004": "SCA UJ レンジ幅下限 0.0042",
    "G005": "SCA UJ レンジ幅下限 0.0048",
    "G007": "SCA UJ レンジ幅下限 0.0060",
}
ORDER = ["G000", "G008", "G009", "G006", "G001", "G002", "G003", "G004", "G005", "G007"]


def geo_monthly(net: float, months: float) -> float:
    """幾何月利。**単利ではない**（目標6%は幾何で定義されている）。"""
    final = DEPOSIT + net
    if final <= 0:
        return float("nan")     # 元本割れ。幾何平均が定義できない
    return ((final / DEPOSIT) ** (1.0 / months) - 1.0) * 100.0


def main() -> None:
    path = ROOT / "results.csv"
    if not path.exists():
        print("results.csv がまだありません")
        return
    rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    idx = {(r["proposal_id"], r["window"]): r for r in rows if r["status"] == "OK"}

    print(f"## 実測（{len(idx)} run 完了）\n")
    print("| 案 | 内容 | 窓 | 純益 | **幾何月利** | 残高DD | equityDD | 取引 | 口座破綻 |")
    print("|---|---|---|---:|---:|---:|---:|---:|---|")
    for pid in ORDER:
        for w in ("OOS", "IS", "FULL"):
            r = idx.get((pid, w))
            if not r:
                continue
            net = float(r["net"])
            gm = geo_monthly(net, MONTHS[w])
            eq = r.get("equity_dd_pct") or r.get("dd_equity_pct") or ""
            bust = "**あり**" if DEPOSIT + net <= 0 else "なし"
            print(f"| {pid} | {DESC.get(pid,'')} | {w} | {net:+,.0f} | **{gm:.3f}%** | "
                  f"{float(r['dd_pct']):.2f}% | {eq} | {r['trades']} | {bust} |")

    ctl = {w: idx.get(("G000", w)) for w in ("OOS", "IS", "FULL")}
    if not ctl["OOS"]:
        return

    print("\n## 対照との差（幾何月利のポイント）と、予測との照合\n")
    print("| 案 | 窓 | 対照 | 案 | **Δpt** | DD | 素朴な予測(円) | **実測Δ(円)** | 予測は |")
    print("|---|---|---:|---:|---:|---|---:|---:|---|")
    for pid in ORDER[1:]:
        for w in ("OOS", "IS", "FULL"):
            r, c = idx.get((pid, w)), ctl.get(w)
            if not (r and c):
                continue
            cn, rn = float(c["net"]), float(r["net"])
            gc, gr = geo_monthly(cn, MONTHS[w]), geo_monthly(rn, MONTHS[w])
            d_yen = rn - cn
            naive = NAIVE.get((pid, w))
            if naive is None:
                verdict = "—"
            elif (naive > 0) == (d_yen > 0):
                verdict = f"符号一致（{naive:+,.0f}）"
            else:
                verdict = f"**符号が逆**（{naive:+,.0f}）"
            print(f"| {pid} | {w} | {gc:.3f}% | {gr:.3f}% | **{gr-gc:+.3f}pt** | "
                  f"{float(c['dd_pct']):.2f}%→{float(r['dd_pct']):.2f}% | "
                  f"{'' if naive is None else f'{naive:+,.0f}'} | {d_yen:+,.0f} | {verdict} |")

    print("\n## SCA 2枠の枠別純益（**機構の確認用**）\n")
    print("> ⚠️ 複利では枠別Δの引き算が成立しない（触っていない枠も equity 経路で動く）。")
    print("> **採否はブックの幾何月利で、機構の確認だけこの表で**行うこと。\n")
    print("| 案 | 窓 | SCA USDJPY | 件数 | SCA GBPJPY | 件数 | 他7枠の和 |")
    print("|---|---|---:|---:|---:|---:|---:|")
    others = ["pb_uj", "pb_gj", "rsi_uj", "rsi_eu", "rsi_gu", "pair", "carry"]
    for pid in ORDER:
        for w in ("OOS", "IS", "FULL"):
            r = idx.get((pid, w))
            if not r:
                continue
            o = sum(float(r.get(f"{k}_net") or 0) for k in others)
            print(f"| {pid} | {w} | {float(r.get('sca_uj_net') or 0):+,.0f} | {r.get('sca_uj_n','')} | "
                  f"{float(r.get('sca_gj_net') or 0):+,.0f} | {r.get('sca_gj_n','')} | {o:+,.0f} |")

    # --- 判定のための要約 ---
    print("\n## 判定\n")
    g000 = {w: float(ctl[w]["net"]) for w in ctl if ctl[w]}
    band = []
    for pid in ["G001", "G002", "G003", "G004", "G005", "G007"]:
        o, i = idx.get((pid, "OOS")), idx.get((pid, "IS"))
        if o and i:
            do = float(o["net"]) - g000.get("OOS", 0)
            di = float(i["net"]) - g000.get("IS", 0)
            band.append((pid, do, di, do > 0 and di > 0))
    if band:
        pos = [b[0] for b in band if b[3]]
        print(f"- **両窓プラスの掃引点:** {pos if pos else 'なし'}")
        print("  - 採用基準は「**両窓プラスが3点以上連続**」。1点だけなら採らない。")
        print("  - 採るなら**帯の中央**。ピークを採らない。")
    g6 = idx.get(("G006", "OOS"))
    if g6 and band:
        d6 = float(g6["net"]) - g000.get("OOS", 0)
        best = max(band, key=lambda b: b[1])
        print(f"- **基準線 G006（枠外し）の OOS Δ:** {d6:+,.0f}／"
              f"**掃引の最良 {best[0]}:** {best[1]:+,.0f}")
        print("  - 掃引が G006 を超えなければ、**SCA USDJPY を複利構成から外すのが正解**。")
    print("- ⚠️ **G008/G009 は両窓で符号が割れると予測している。** 割れた場合、"
          "**目標定義（OOS）と一般方針（IS優先）が衝突する**ので、"
          "**両窓を並べてユーザーに判定を仰ぐ**こと。こちらで決めない。")


if __name__ == "__main__":
    main()

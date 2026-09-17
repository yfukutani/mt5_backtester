"""第14報ラウンド `ml/fxqual1` の採否判定。

【このラウンドの土俵】
本番現行サイジング（RefCap=78,000 固定・倍率1・重み全1.0・cap無し・leverage 1:25）。
**全案でロット規則が同一**なので、差はすべて「枠の入口と出口の規則」から来る。

【月利の定義】
固定サイジング＝複利が効かないので **単利**（純益 ÷ 50万円 ÷ 月数）。
複利前提の過去ラウンド（幾何月利）の数字とは並べられない。

【判定規則】
CLAUDE.md の報告規律に従い、**IS窓と OOS窓の両方**で 損益・月利・最大DD を併記する。
採否は以下で機械的に出す。人が読んで覆すのは構わないが、既定はこれ。

    両窓とも Q000 を上回る           -> 候補（次ラウンドで確認）
    片窓だけ上回る                   -> 相場観の賭け（単独では採らない）
    両窓とも下回る                   -> 棄却
    取引数が Q000 と1件も変わらない  -> 無効（入力が効いていない＝実装を疑う）

最後の1行が要る。第14報では `CarryExitPeriod` が
「退出だけ」を変えていなかった（入口も変わっていた）という交絡が見つかっている。
**入力が効いていないことと、効いた結果が同じことは、区別できなければならない。**
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RES = ROOT / "results.csv"
WINS = ("OOS", "IS")
MONTHS = {"OOS": 55.0, "IS": 60.0}

# 枠ごとの列名（results.csv の後半）と、その枠を狙っている案の見分け
SLEEVES = ["pb_uj", "pb_gj", "rsi_uj", "rsi_eu", "rsi_gu",
           "pair", "carry", "sca_uj", "sca_gj"]
SLEEVE_LABEL = {
    "pb_uj": "PB UJ", "pb_gj": "PB GJ",
    "rsi_uj": "RSI UJ", "rsi_eu": "RSI EU", "rsi_gu": "RSI GU",
    "pair": "Pair", "carry": "Carry",
    "sca_uj": "SCA UJ", "sca_gj": "SCA GJ",
}
# 案がどの枠を触るか（狙い撃ちの枠だけを見れば、他枠のノイズに紛れない）
TARGET = {
    "Q001": ["rsi_uj", "rsi_eu", "rsi_gu"], "Q002": ["rsi_uj", "rsi_eu", "rsi_gu"],
    "Q003": ["rsi_eu"], "Q004": ["rsi_uj", "rsi_gu"],
    "Q005": ["sca_uj", "sca_gj"], "Q006": ["sca_uj", "sca_gj"],
    "Q007": ["sca_uj", "sca_gj"], "Q008": ["sca_gj"],
    "Q009": ["sca_uj", "sca_gj"], "Q010": ["sca_uj", "sca_gj"],
    "Q011": ["pb_gj"], "Q012": ["pb_gj"], "Q013": ["pb_gj"], "Q014": ["pb_gj"],
    "Q015": ["pb_uj"], "Q016": ["pb_uj"],
    "Q017": ["sca_gj"], "Q018": ["sca_uj", "sca_gj"],
    "Q019": ["carry"], "Q020": ["carry"], "Q021": ["carry"],
}


def f(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def load():
    if not RES.exists():
        sys.exit("results.csv がまだ無い。ラウンドが1本も完走していない。")
    rows = {}
    for r in csv.DictReader(open(RES, encoding="utf-8")):
        if r.get("status") != "OK":
            continue
        rows[(r["proposal_id"], r["window"])] = r
    return rows


def main():
    rows = load()
    pids = sorted({p for (p, _) in rows})
    if not pids:
        sys.exit("OK の行が無い。")

    base = {w: rows.get(("Q000", w)) for w in WINS}
    have_base = all(base[w] for w in WINS)

    print(f"# fxqual1 判定 — {len(rows)}run / 44run 完了 "
          f"({len(pids)}構成・対照={'あり' if have_base else '**まだ無い**'})\n")

    # --- 全体表（損益・想定月利・最大DD を IS/OOS 併記）---
    print("## 1. ブック全体（単利月利・DDは残高ベース）\n")
    print("| 案 | 説明 | OOS 純益 | OOS 月利% | OOS DD% | OOS 取引 "
          "| IS 純益 | IS 月利% | IS DD% | IS 取引 |")
    print("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for p in pids:
        desc = ""
        cells = []
        for w in WINS:
            r = rows.get((p, w))
            if not r:
                cells += ["—"] * 4
                continue
            desc = desc or r["description"][:44]
            cells += [f"{f(r['net']):+,.0f}", f"{f(r['monthly_pct']):.3f}",
                      f"{f(r['dd_pct']):.1f}", f"{int(f(r['trades']))}"]
        print(f"| {p} | {desc} | " + " | ".join(cells) + " |")

    if not have_base:
        print("\n> 対照 Q000 の両窓が揃うまで差分は出せない。")
        return

    # --- 差分と判定 ---
    print("\n## 2. 対照 Q000 との差（ブック全体）と判定\n")
    print("| 案 | OOS Δ純益 | OOS Δ月利pt | IS Δ純益 | IS Δ月利pt "
          "| Δ取引(OOS/IS) | 判定 |")
    print("|---|---:|---:|---:|---:|---:|---|")
    verdicts = {}
    for p in pids:
        if p == "Q000":
            continue
        if not all(rows.get((p, w)) for w in WINS):
            continue
        d_net, d_mon, d_tr = {}, {}, {}
        for w in WINS:
            r, b = rows[(p, w)], base[w]
            d_net[w] = f(r["net"]) - f(b["net"])
            d_mon[w] = f(r["monthly_pct"]) - f(b["monthly_pct"])
            d_tr[w] = int(f(r["trades"])) - int(f(b["trades"]))
        if d_tr["OOS"] == 0 and d_tr["IS"] == 0 and \
                abs(d_net["OOS"]) < 1 and abs(d_net["IS"]) < 1:
            v = "**無効**（1円も動いていない＝入力が効いていない）"
        elif d_net["OOS"] > 0 and d_net["IS"] > 0:
            v = "**候補**（両窓で改善）"
        elif d_net["OOS"] > 0 or d_net["IS"] > 0:
            w_ok = "OOS" if d_net["OOS"] > 0 else "IS"
            v = f"相場観の賭け（{w_ok}のみ）"
        else:
            v = "棄却（両窓で悪化）"
        verdicts[p] = v
        print(f"| {p} | {d_net['OOS']:+,.0f} | {d_mon['OOS']:+.3f} "
              f"| {d_net['IS']:+,.0f} | {d_mon['IS']:+.3f} "
              f"| {d_tr['OOS']:+d}/{d_tr['IS']:+d} | {v} |")

    # --- 狙った枠だけの差（他枠のノイズを外す）---
    print("\n## 3. 狙い撃ちした枠だけの差（他枠のノイズを除く）\n")
    print("> ブック全体の差には、触っていない枠の分も乗る（固定サイジングなので"
          "本来は乗らないはずだが、証拠金の取り合いで順序が変わりうる）。"
          "**案が狙った枠の純益だけ**を抜くと、効き目の向きがはっきりする。\n")
    print("| 案 | 枠 | OOS 枠純益(対照) | OOS Δ | OOS Δ取引 "
          "| IS 枠純益(対照) | IS Δ | IS Δ取引 |")
    print("|---|---|---:|---:|---:|---:|---:|---:|")
    for p in pids:
        if p == "Q000" or p not in TARGET:
            continue
        if not all(rows.get((p, w)) for w in WINS):
            continue
        for s in TARGET[p]:
            cells = []
            for w in WINS:
                r, b = rows[(p, w)], base[w]
                bn, rn = f(b[f"{s}_net"]), f(r[f"{s}_net"])
                bt, rt = f(b[f"{s}_n"]), f(r[f"{s}_n"])
                cells += [f"{bn:+,.0f}", f"{rn - bn:+,.0f}", f"{int(rt - bt):+d}"]
            print(f"| {p} | {SLEEVE_LABEL[s]} | " + " | ".join(cells) + " |")

    # --- 目標に対する現在地 ---
    print("\n## 4. 目標（月利6%）に対する現在地\n")
    b_oos, b_is = base["OOS"], base["IS"]
    print(f"- 対照 Q000（本番現行・固定サイジング）: "
          f"OOS 単利月利 **{f(b_oos['monthly_pct']):.3f}%** "
          f"(純益 {f(b_oos['net']):+,.0f}円 / DD {f(b_oos['dd_pct']):.1f}%) ／ "
          f"IS 単利月利 **{f(b_is['monthly_pct']):.3f}%** "
          f"(純益 {f(b_is['net']):+,.0f}円 / DD {f(b_is['dd_pct']):.1f}%)")
    best = None
    for p, v in verdicts.items():
        if not v.startswith("**候補**"):
            continue
        m = min(f(rows[(p, w)]["monthly_pct"]) for w in WINS)
        if best is None or m > best[1]:
            best = (p, m)
    if best:
        print(f"- 両窓で改善した案の最良: **{best[0]}**（両窓の低いほうで "
              f"月利 {best[1]:.3f}%）")
    else:
        print("- **両窓で改善した案は無い。**")
    print("\n> このラウンドは固定サイジングなので、月利の絶対値は目標6%と直接は比べられない"
          "（本番は複利・倍率を乗せる）。**ここで見るのは枠の改良の向きと大きさだけ**であり、"
          "良い改良が見つかればサイジングは後から掛け直す。")


if __name__ == "__main__":
    main()

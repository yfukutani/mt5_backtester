"""`ml/fxqual3` の判定 — 回帰試験 → ゲートが効いたかの確認 → 枠別の差 → PB の律速。

【順番を変えないこと】
1. **回帰試験**: V000 が fxqual2 の T000（＝fxqual1 の Q000）と
   純益・DD・取引数で1円まで一致するか。新 input（`RsiMechMask_*` / `PbDiagCounters`）は
   既定で挙動を変えない**はず**だが、一致しなければ以降の比較は前ラウンドと並べられない。
2. **ゲートが効いたかの確認**: V001〜V006 が V000 と**完全に同じ数字なら、それは
   「効かなかった」ではなく「入力が届いていない」**（旧 .ex5 のまま走った等。MT5 は
   知らない入力を黙って無視する）。ここを飛ばすと偽の実測を採用してしまう。
3. 枠別の差（`ml/fxqual1/reattribute.py` と同じ、**建玉時 magic への引き直し**込み）。
4. PB 入口の律速（`*_cap.csv` の `pbdiag` 行）。

【PB の律速の読み方】
各条件 k について「その条件以外の7つが全部成立していたバー数」を LOO[k] とし、
全条件成立を ALL とすると、**LOO[k] − ALL が「その条件だけで落ちたバー数」**である。
これが大きい条件ほど強く絞っている。素朴な漏斗（順に絞る）は順序で答えが変わるので使わない。
"""
from __future__ import annotations

import csv
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROOT = Path(__file__).resolve().parent

_spec = importlib.util.spec_from_file_location(
    "_reattr", REPO / "ml" / "fxqual1" / "reattribute.py")
ra = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ra)

PB_COND = ["0 up(終値>trendMA & fastEMA>slowEMA)", "1 armed(押し目待ち)",
           "2 終値>fastEMA", "3 陽線/陰線", "4 終値>2本前の高値(安値)",
           "5 ADX", "6 slope(trendMA傾き)", "7 上位足(D1 MA200)"]
PB_MAGIC = {20260622: "PB USDJPY", 20260627: "PB GBPJPY",
            20260628: "PB AUDJPY", 20260640: "PB GOLD"}
DEPOSIT = 500000
MONTHS = {"OOS": 55.0, "IS": 60.0}


def load(path):
    if not path.exists():
        return {}
    return {(r["proposal_id"], r["window"]): r
            for r in csv.DictReader(open(path, encoding="utf-8"))
            if r.get("status") == "OK"}


def regression(v, t):
    print("## 0. 回帰試験（新 input が既定で挙動を変えていないこと）\n")
    print("| 窓 | fxqual2 T000 純益 | fxqual3 V000 純益 | 差 | T000 取引 | V000 取引 | 判定 |")
    print("|---|---:|---:|---:|---:|---:|---|")
    ok = True
    for w in ("OOS", "IS"):
        a, b = t.get(("T000", w)), v.get(("V000", w))
        if not a or not b:
            print(f"| {w} | — | — | — | — | — | 片方が未完了 |")
            ok = False
            continue
        dn = float(b["net"]) - float(a["net"])
        dt = int(float(b["trades"])) - int(float(a["trades"]))
        good = abs(dn) < 1 and dt == 0
        ok = ok and good
        print(f"| {w} | {float(a['net']):+,.0f} | {float(b['net']):+,.0f} | {dn:+,.0f} "
              f"| {int(float(a['trades']))} | {int(float(b['trades']))} "
              f"| {'一致' if good else '**不一致（以降を読んではいけない）**'} |")
    print()
    return ok


def gate_effective(v):
    """V001〜が V000 と完全一致していないか。一致＝入力が届いていない疑い。"""
    print("## 1. ゲートが本当に届いているか\n")
    print("> V001〜V006 が V000 と**完全に同じ数字**なら、それは「効かなかった」ではなく")
    print("> **「入力が EA に届いていない」**（旧 .ex5 のまま走った等）。")
    print("> MT5 は知らない入力を黙って無視するので、ここを見ないと偽の実測を採ってしまう。\n")
    print("| 案 | 窓 | Δ純益 | Δ取引 | 判定 |")
    print("|---|---|---:|---:|---|")
    bad = []
    for (pid, w), r in sorted(v.items()):
        if pid == "V000":
            continue
        b = v.get(("V000", w))
        if not b:
            continue
        dn = float(r["net"]) - float(b["net"])
        dt = int(float(r["trades"])) - int(float(b["trades"]))
        same = dn == 0 and dt == 0
        if same:
            bad.append((pid, w))
        print(f"| {pid} | {w} | {dn:+,.0f} | {dt:+d} "
              f"| {'**V000と同一＝入力が届いていない疑い**' if same else '差が出ている'} |")
    print()
    if bad:
        print(f"> [!warning] **{len(bad)}件が V000 と同一である。** "
              "EA のバイナリと入力名を確認すること。\n")
    return not bad


def sleeve_diff(results_path):
    print("## 2. 枠別の差（建玉時 magic への引き直し込み・第16報の修正）\n")
    out = ra.main(results_path)
    out.sort(key=lambda x: (x["id"], x["window"]))
    ra.table(out, base_id="V000")
    print()


def equity_dd(run_id):
    """含み損込みDD。EA は `ResultFileName` をテスターのサンドボックスに書くので、
    run の直後に `agent_results/` へ退避されたものを読む（第15報の回収経路）。
    results.csv には列を足さない（走行中のラウンドがヘッダ不一致で壊れるため）。"""
    f = ROOT / "agent_results" / f"{run_id}_result.csv"
    if not f.exists():
        return None
    for row in csv.reader(open(f, encoding="utf-8")):
        if len(row) == 2 and row[0] == "equity_dd_pct":
            try:
                return float(row[1])
            except ValueError:
                return None
    return None


def monthly(v):
    print("## 3. 損益・想定月利・最大DD（IS窓とOOS窓の両方）\n")
    print("> 固定サイジングなので月利は**単利**（純益 ÷ 50万 ÷ 月数）。"
          "複利前提の幾何月利とは並べられない。DD は残高ベースと含み損込み(equity)の両方。\n")
    print("| 案 | 窓 | 純益 | 単利月利 | 残高DD | equity DD | 取引 | 口座破綻 |")
    print("|---|---|---:|---:|---:|---:|---:|---|")
    for (pid, w), r in sorted(v.items()):
        net = float(r["net"])
        eq = equity_dd(r["run_id"])
        fb = float(r.get("final_balance") or 0)
        print(f"| {pid} | {w} | {net:+,.0f} | {100*net/DEPOSIT/MONTHS[w]:.3f}% "
              f"| {float(r['dd_pct']):.2f}% | {'—' if eq is None else f'{eq:.2f}%'} "
              f"| {int(float(r['trades']))} | {'**あり**' if fb <= 0 else 'なし'} |")
    print()


def pb_funnel(v):
    print("## 4. PB 入口の律速（leave-one-out）\n")
    print("> LOO[k] = 「条件 k 以外の7つが全部成立していたバー数」。"
          "**LOO[k] − ALL がその条件だけで落ちたバー数**＝絞りの強さ。\n")
    any_row = False
    for (pid, w), r in sorted(v.items()):
        if pid != "V000":
            continue
        cap = ROOT / "run_deals" / f"{r['run_id']}_cap.csv"
        if not cap.exists():
            continue
        for row in csv.reader(open(cap, encoding="utf-8")):
            if not row or row[0] != "pbdiag":
                continue
            any_row = True
            magic = int(row[1])
            bars, allc = int(row[2]), int(row[3])
            loo = [int(x) for x in row[4].split("|")]
            print(f"\n### {PB_MAGIC.get(magic, magic)} — {w}窓"
                  f"（評価バー {bars:,} / 全条件成立 {allc}）\n")
            print("| 条件 | LOO | その条件だけで落ちたバー | 絞りの順位 |")
            print("|---|---:|---:|---:|")
            solo = [(k, loo[k] - allc) for k in range(8)]
            rank = {k: i + 1 for i, (k, _) in
                    enumerate(sorted(solo, key=lambda x: -x[1]))}
            for k in range(8):
                print(f"| {PB_COND[k]} | {loo[k]:,} | {solo[k][1]:,} | {rank[k]} |")
    if not any_row:
        print("> pbdiag 行がまだ無い（V000 が未完了か、CapLogFile が渡っていない）。")
    print()


def main():
    v = load(ROOT / "results.csv")
    t = load(REPO / "ml" / "fxqual2" / "results.csv")
    if not v:
        raise SystemExit("fxqual3 の results.csv がまだ無い。")
    print("# fxqual3 — RSI 発火機構ゲート（第16報）\n")
    ok = regression(v, t)
    if not ok:
        print("> **回帰試験が通っていないので、以下は参考値である。**\n")
    gate_effective(v)
    monthly(v)
    sleeve_diff(ROOT / "results.csv")
    pb_funnel(v)


if __name__ == "__main__":
    main()

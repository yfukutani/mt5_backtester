r"""含み損込みDD（equity DD）を、消える前に拾い続ける常駐スクリプト。

【なぜ要るか】
報告してきた `dd_pct` は **残高ベース**（`STAT_BALANCE_DDREL_PERCENT`）である。
決済して初めて残高が動くので、**含み損は1円も乗っていない**。
Pair（保有中央値 229〜311時間）や Carry（同 1,152〜4,164時間）のように長く持つ枠では、
これは risk を**過小表示する**。2026-09-18 に Codex の査読で改めて突かれた。

EA は `equity_dd_pct`（`STAT_EQUITY_DDREL_PERCENT`）も書いている。ただし
`ResultFileName` は `FILE_COMMON` を付けずに開かれているため、
**テスターエージェントのサンドボックス**に落ちる:

    ...\Tester\<端末ID>\Agent-127.0.0.1-<port>\MQL5\Files\<run_id>_result.csv

そして **エージェントは次のrunを始めるときにこのフォルダを空にする。**
だから「あとでまとめて集める」ができない。**走っている最中に拾うしかない。**

【やること】
数秒おきにエージェントのサンドボックスを覗き、`*_result.csv` を見つけたら
ラウンド配下の `agent_results/` に複製する。読むだけなのでテスターには触らない。

【使い方】
    python ml/fxqual1/collect_equity_dd.py            # 常駐（Ctrl-C で止める）
    python ml/fxqual1/collect_equity_dd.py --report   # 集めた分を results.csv と突き合わせて表に出す

【恒久対策（このスクリプトは本来要らない）】
`ml/fxmargin3/measure.py` の `run()` が、runの直後に同じ回収をすればよい。
**ただし走行中のラウンドがその module を読み込んでいる間は書き換えない**
（`FIELDS` を増やすと、再開時に既存 results.csv のヘッダと列数が食い違う）。
fxqual1 が終わってから直すこと。
"""
from __future__ import annotations

import csv
import shutil
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROOT = Path(__file__).resolve().parent
OUT = ROOT / "agent_results"
TESTER = Path(r"C:\Users\f\AppData\Roaming\MetaQuotes\Tester")
POLL_SEC = 5.0


def sandboxes():
    if not TESTER.exists():
        return []
    return [p for p in TESTER.glob("*/Agent-*/MQL5/Files") if p.is_dir()]


def watch():
    OUT.mkdir(parents=True, exist_ok=True)
    seen = {p.name for p in OUT.glob("*_result.csv")}
    # **起動時に既にあるファイルは拾わない。** サンドボックスには別ラウンドの
    # 食べ残しが何十件も残っており、全部さらうとこのラウンドの結果に混ざる。
    t0 = time.time() - 600.0        # 直前に終わったrunの取りこぼしだけは拾う
    print(f"監視開始: {len(sandboxes())}個のエージェントサンドボックス "
          f"-> {OUT}（既に {len(seen)}件・10分より古いものは無視）")
    while True:
        for box in sandboxes():
            for src in box.glob("*_result.csv"):
                if src.name in seen:
                    continue
                try:
                    if src.stat().st_mtime < t0:
                        seen.add(src.name)      # 古い食べ残し。二度と見ない
                        continue
                except OSError:
                    continue
                try:
                    shutil.copy2(src, OUT / src.name)
                except OSError:
                    continue          # 書き込み中なら次の周回で拾う
                seen.add(src.name)
                print(f"回収 {src.name}", flush=True)
        time.sleep(POLL_SEC)


def report():
    res = ROOT / "results.csv"
    if not res.exists():
        sys.exit("results.csv がまだ無い。")
    eq = {}
    for p in OUT.glob("*_result.csv"):
        d = {r[0]: r[1] for r in csv.reader(open(p, encoding="utf-8")) if len(r) >= 2}
        eq[p.name[:-len("_result.csv")]] = d
    rows = [r for r in csv.DictReader(open(res, encoding="utf-8"))
            if r.get("status") == "OK"]
    print("# 含み損込みDD（equity DD）と残高ベースDDの差\n")
    print("> `dd_pct`（これまで報告してきた数字）は残高ベースで、**含み損を含まない**。")
    print("> 口座破綻の判定に効くのは equity 側である。\n")
    print("| 案 | 窓 | 純益 | 月利% | 残高DD% | **equity DD%** | 差 | 取引 |")
    print("|---|---|---:|---:|---:|---:|---:|---:|")
    miss = 0
    for r in rows:
        d = eq.get(r["run_id"])
        if not d:
            miss += 1
            continue
        b = float(r["dd_pct"])
        e = float(d.get("equity_dd_pct", "nan"))
        print(f"| {r['proposal_id']} | {r['window']} | {float(r['net']):+,.0f} "
              f"| {float(r['monthly_pct']):.3f} | {b:.1f} | **{e:.1f}** "
              f"| {e-b:+.1f} | {int(float(r['trades']))} |")
    if miss:
        print(f"\n> {miss}run 分は回収前に消されている"
              "（ウォッチャーを立てる前に走った分）。")


if __name__ == "__main__":
    if "--report" in sys.argv:
        report()
    else:
        watch()

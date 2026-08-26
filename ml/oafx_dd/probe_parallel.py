# -*- coding: utf-8 -*-
"""BT1/BT2端末で並列バックテストが安全に行えるかを検証する。

【なぜ慎重に確かめるか】
本プロジェクトでは「mt5btを絶対に並列実行しない」を厳守してきた。過去に並列実行で
結果が壊れ、誤ったFAIL判定を生んだためである。ただしあの事故は *同一端末* を2つの
プロセスが奪い合った結果だった。端末が物理的に分かれていれば話は別になる。

【並列が安全な条件】
1. 端末ごとにデータディレクトリ(MQL5\\Profiles\\Tester\\*.set の置き場)が分離している
   → 分離していないとSETファイルを互いに上書きし、片方が別のパラメータで走る
2. dealログのファイル名がrunごとに一意
   → 本ドライバはrun_id基準で一意。ただしFILE_COMMONの出力先は全端末で共有される
3. results/<run_name> がrunごとに一意

1が満たされないなら並列は不可。ここを実測で確かめる。
"""
import json
import subprocess
import sys
import time
from pathlib import Path

TERMINALS = {
    "BT1": Path(r"C:\Program Files\OANDA MetaTrader 5_BT1\terminal64.exe"),
    "BT2": Path(r"C:\Program Files\OANDA MetaTrader 5_BT2\terminal64.exe"),
}
APPDATA_TERM = Path(r"C:\Users\f\AppData\Roaming\MetaQuotes\Terminal")


def data_dir_of(exe: Path):
    """端末の実データディレクトリを特定する。

    ポータブル運用なら exe と同じ場所、通常運用なら APPDATA 配下のハッシュ名。
    origin.txt にインストール元パスが書かれているのでそれで突き合わせる。
    """
    portable = exe.parent / "MQL5"
    if portable.is_dir():
        return exe.parent, "portable"
    hits = []
    for d in APPDATA_TERM.iterdir():
        if not d.is_dir():
            continue
        origin = d / "origin.txt"
        if not origin.is_file():
            continue
        try:
            text = origin.read_text(encoding="utf-16", errors="ignore")
        except OSError:
            continue
        if str(exe.parent).lower() in text.lower():
            hits.append(d)
    if len(hits) == 1:
        return hits[0], "appdata"
    return None, "unknown(%d候補)" % len(hits)


def main():
    print("=== 端末とデータディレクトリの対応 ===")
    dirs = {}
    for name, exe in TERMINALS.items():
        if not exe.is_file():
            print("%-4s 実行ファイルが見つかりません: %s" % (name, exe))
            continue
        d, kind = data_dir_of(exe)
        dirs[name] = d
        print("%-4s exe=%s" % (name, exe))
        print("     data=%s  (%s)" % (d, kind))
        if d:
            tester = d / "MQL5" / "Profiles" / "Tester"
            experts = d / "MQL5" / "Experts"
            print("     Tester profiles: %s / Experts: %s"
                  % ("あり" if tester.is_dir() else "なし",
                     "あり" if experts.is_dir() else "なし"))

    print("\n=== 判定 ===")
    vals = [v for v in dirs.values() if v]
    if len(vals) < 2:
        print("データディレクトリを特定できませんでした。並列は許可できません。")
        return 1
    if len(set(str(v).lower() for v in vals)) != len(vals):
        print("⚠️データディレクトリが共有されています。SETファイルを奪い合うため並列は不可。")
        return 1
    print("データディレクトリは分離されています（条件1を満たす）。")
    print("→ ただし FILE_COMMON のdeal出力先は全端末で共有される点に注意。")
    print("  runごとに一意なEquityLogFile名なら衝突しない。")
    json.dump({k: str(v) for k, v in dirs.items()},
              open(Path(__file__).resolve().parent / "parallel_terminals.json", "w",
                   encoding="utf-8"), ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())

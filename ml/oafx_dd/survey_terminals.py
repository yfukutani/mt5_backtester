# -*- coding: utf-8 -*-
"""バックテスト用5端末の状態を調べる。

並列実行の前提:
  1. データディレクトリが端末ごとに分離している（SETファイルの奪い合いを防ぐ）
  2. 口座・サーバーが本番と同一（銘柄仕様が揃わないと基準値と比較できない）
  3. 必要銘柄の履歴がある
  4. 検証EAが配置・コンパイル済み
"""
import re
import sys
from pathlib import Path

APPDATA = Path(r"C:\Users\f\AppData\Roaming\MetaQuotes\Terminal")
PROGRAMS = Path(r"C:\Program Files")
TARGETS = ["OANDA MetaTrader 5", "OANDA MetaTrader 5_BT1", "OANDA MetaTrader 5_BT2",
           "OANDA MetaTrader 5_BT3", "OANDA MetaTrader 5_BT4"]
WANT = ["USDJPY", "GBPJPY", "EURUSD", "GBPUSD", "AUDJPY"]
EA = "MIX_EA_OANDA_SIMVERIFY"


def data_dir(install: Path):
    for d in APPDATA.iterdir():
        if not d.is_dir():
            continue
        origin = d / "origin.txt"
        if not origin.is_file():
            continue
        try:
            text = origin.read_text(encoding="utf-16", errors="ignore")
        except OSError:
            continue
        # 末尾一致で厳密に見る（_BT1 が "OANDA MetaTrader 5" に誤マッチするのを防ぐ）
        for line in text.splitlines():
            if line.strip().lower() == str(install).lower():
                return d
    return None


def last_auth(base: Path):
    logs = sorted((base / "logs").glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    for lg in logs[:3]:
        try:
            txt = lg.read_text(encoding="utf-16", errors="ignore")
        except OSError:
            continue
        hits = re.findall(r"'(\d+)': authorized on ([^\s(]+(?: [^\s(]+)*?) through", txt)
        if hits:
            return hits[-1]
    return None


def main():
    rows = []
    for name in TARGETS:
        install = PROGRAMS / name
        exe = install / "terminal64.exe"
        if not exe.is_file():
            print("%-28s 実行ファイルなし" % name)
            continue
        base = data_dir(install)
        if base is None:
            print("%-28s データディレクトリ不明" % name)
            continue
        auth = last_auth(base)
        syms = {}
        for server in base.glob("bases/OANDA*"):
            h = server / "history"
            if h.is_dir():
                syms[server.name] = sorted(d.name for d in h.iterdir() if d.is_dir())
        ea_ex5 = (base / "MQL5" / "Experts" / (EA + ".ex5")).is_file()
        rows.append({"name": name, "base": base, "auth": auth, "syms": syms, "ea": ea_ex5})

    print("=== 端末の状態 ===")
    for r in rows:
        acct, server = r["auth"] if r["auth"] else ("?", "?")
        print("\n%-28s" % r["name"])
        print("  data   : %s" % r["base"].name)
        print("  口座   : %s @ %s" % (acct, server))
        print("  検証EA : %s" % ("配置済み" if r["ea"] else "⚠️未配置"))
        for srv, sl in r["syms"].items():
            miss = [w for w in WANT if w not in sl]
            print("  %s: %s%s" % (srv, ", ".join(sl) if sl else "(なし)",
                                  "  ⚠️不足=" + ",".join(miss) if miss else "  ✓必要銘柄あり"))

    print("\n=== 並列の前提1: データディレクトリの分離 ===")
    dirs = [str(r["base"]).lower() for r in rows]
    if len(set(dirs)) == len(dirs):
        print("すべて分離されています ✓")
    else:
        print("⚠️共有があります。並列は不可。")

    print("\n=== 並列の前提2: 口座・サーバーの一致 ===")
    auths = {r["name"]: r["auth"] for r in rows}
    base_auth = auths.get("OANDA MetaTrader 5")
    for n, a in auths.items():
        mark = "✓" if a == base_auth else "⚠️本番と不一致"
        print("  %-28s %s  %s" % (n, a, mark))
    return 0


if __name__ == "__main__":
    sys.exit(main())

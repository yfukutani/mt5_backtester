# -*- coding: utf-8 -*-
"""BT1/BT2端末に必要な銘柄を気配値登録する（チャート起動方式）。

MT5は /config:<ini> の [StartUp] Symbol= でチャートを開くと、その銘柄が
気配値に選択され履歴フォルダが生成される。GUI操作なしで登録できる。

【注意】デモ口座はライブと銘柄名が異なる。実測でGBPJPYは "GBPJPY.cl" だった。
そこで素の名前とサフィックス付きの両方を試し、実際に生成された名前を記録する。
EA側は Sym_* 入力で銘柄名を差し替えられるので、判明した名前をそこへ渡す。
"""
import subprocess
import sys
import time
from pathlib import Path

TERMS = {
    "BT1": (r"C:\Program Files\OANDA MetaTrader 5_BT1\terminal64.exe",
            r"C:\Users\f\AppData\Roaming\MetaQuotes\Terminal\6142D304BFF2E6AB353977162D6F452C"),
    "BT2": (r"C:\Program Files\OANDA MetaTrader 5_BT2\terminal64.exe",
            r"C:\Users\f\AppData\Roaming\MetaQuotes\Terminal\06EBB62A36630B6356B2240C609DE508"),
}
SCRATCH = Path(r"C:\Users\f\AppData\Local\Temp\claude\C--project"
               r"\861ddb77-6585-42d0-b5ea-e82fa9407308\scratchpad")

# OANDA FXの9枠が必要とする銘柄。素の名前と .cl 付きの両方を試す。
WANTED = ["USDJPY", "GBPJPY", "EURUSD", "GBPUSD", "AUDJPY", "XAUUSD"]
SUFFIXES = ["", ".cl"]


def kill_terminals():
    subprocess.run(["taskkill", "/F", "/IM", "terminal64.exe"],
                   capture_output=True, text=True)
    time.sleep(3)


def history_dirs(base: Path):
    out = set()
    for server in base.glob("bases/OANDA*"):
        h = server / "history"
        if h.is_dir():
            out |= {d.name for d in h.iterdir() if d.is_dir()}
    return out


def open_chart(exe: str, symbol: str, wait: int = 26):
    ini = SCRATCH / ("reg_%s.ini" % symbol.replace(".", "_"))
    ini.parent.mkdir(parents=True, exist_ok=True)
    ini.write_text("[StartUp]\r\nSymbol=%s\r\nPeriod=M15\r\n" % symbol, encoding="ascii")
    subprocess.Popen([exe, "/config:%s" % ini])
    time.sleep(wait)
    kill_terminals()


def main():
    resolved = {}
    for name, (exe, data) in TERMS.items():
        base = Path(data)
        print("\n######## %s ########" % name)
        before = history_dirs(base)
        print("登録前: %s" % ", ".join(sorted(before)))
        found = {}
        for want in WANTED:
            hit = next((s for s in before if s == want or s.startswith(want + ".")), None)
            if hit:
                found[want] = hit
                print("  %-8s 既に存在: %s" % (want, hit))
                continue
            for suf in SUFFIXES:
                cand = want + suf
                open_chart(exe, cand)
                now = history_dirs(base)
                new = now - before
                hit2 = next((s for s in now if s == cand), None)
                if hit2:
                    found[want] = hit2
                    before = now
                    print("  %-8s 登録成功: %s" % (want, hit2))
                    break
                if new:
                    before = now
            else:
                print("  %-8s ⚠️登録できず（この口座には無い可能性）" % want)
        resolved[name] = found
        print("登録後: %s" % ", ".join(sorted(history_dirs(base))))

    print("\n######## 解決した銘柄名 ########")
    for name, found in resolved.items():
        print("%-4s %s" % (name, found))
        missing = [w for w in WANTED if w not in found]
        if missing:
            print("     ⚠️不足: %s" % ", ".join(missing))
    return 0


if __name__ == "__main__":
    sys.exit(main())

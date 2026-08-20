# -*- coding: utf-8 -*-
"""OANDA GOLDの2枠がどちらも実際に動いているかを、枠を分けて実測で確認する。

MIX_EA_OANDA のdealログは magic列を持たない(time,profitのみ)ため、
XM側で使っていたmagic出現ゲートが使えない。代わりに
  PB単独 / SCA単独 / 両方
を走らせ、取引数が整合するかで枠の生存を確かめる。
片方が無音で脱落していれば、単独runの取引数が0になるか、
両方runの取引数が単独の合計と大きく食い違う。
"""
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from measure_books import (  # noqa: E402
    MT5BT, REPO, WORK, OANDA_PATH, wait_mt5, summary,
)

FRM, TO = "2016.11.09", "2026.06.20"
BASE = {
    "En_PB_USDJPY": False, "En_PB_GBPJPY": False, "En_PB_AUDJPY": False,
    "En_RSI_USDJPY": False, "En_RSI_EURUSD": False, "En_RSI_GBPUSD": False,
    "En_PAIR": False, "En_CARRY": False, "En_VBO": False, "En_ETH": False,
    "En_SCA_USDJPY": False, "En_SCA_GBPJPY": False,
    "Mult_PB_GOLD": 1.0, "Mult_SCA_GOLD": 1.0,
}
CASES = [
    ("PBのみ",  {"En_PB_GOLD": True,  "En_SCA_GOLD": False}),
    ("SCAのみ", {"En_PB_GOLD": False, "En_SCA_GOLD": True}),
    ("両方",    {"En_PB_GOLD": True,  "En_SCA_GOLD": True}),
]


def main():
    res = {}
    for label, ov in CASES:
        run = "oagold_split_%s" % ("pb" if "PB" in label else ("sca" if "SCA" in label else "both"))
        r = summary(run)
        if r is None:
            cfg = {
                "mt5_path": OANDA_PATH, "expert": "MIX_EA_OANDA",
                "symbol": "XAUUSD", "period": "M15",
                "from_date": FRM, "to_date": TO,
                "deposit": 500000, "currency": "JPY", "leverage": 25,
                "model": "every_tick",
                "parameters": dict(BASE, **ov, **{"ResultFileName": run + "_r.csv"}),
                "report_dir": "results", "report_name": run,
            }
            path = WORK / (run + ".yaml")
            yaml.safe_dump(cfg, open(path, "w", encoding="utf-8"),
                           allow_unicode=True, sort_keys=False)
            wait_mt5()
            subprocess.run([str(MT5BT), "run", str(path)], cwd=str(REPO), timeout=7200,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            r = summary(run)
        if r is None:
            print("%-7s 実行失敗" % label, flush=True)
            continue
        res[label] = r
        print("%-7s 純利益%+11.0f PF%.4f DD%6.2f%% n=%d"
              % (label, r["net"], r["pf"], r["ddpct"], r["n"]), flush=True)

    if len(res) == 3:
        s = res["PBのみ"]["n"] + res["SCAのみ"]["n"]
        b = res["両方"]["n"]
        print("\n単独の合計 n=%d / 両方 n=%d （差 %+d）" % (s, b, b - s))
        if res["PBのみ"]["n"] == 0:
            print("→ ⚠️PB GOLDが1件も取引していない。枠が死んでいる。")
        elif res["SCAのみ"]["n"] == 0:
            print("→ ⚠️SCA GOLDが1件も取引していない。枠が死んでいる。")
        elif abs(b - s) > max(10, s * 0.05):
            print("→ ⚠️差が大きい。枠の相互作用か、どちらかが部分的に脱落している可能性。")
        else:
            print("→ 両枠とも正常に稼働している。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

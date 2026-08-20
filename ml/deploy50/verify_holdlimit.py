# -*- coding: utf-8 -*-
"""本番EAに実装した保有上限64バーが、検証EAの結果を再現するかを確かめる。

検証EA(MIX_EA_SIMVERIFY)は GoldLabMode=24 + GoldLabPBHoldBars で機構を与えたが、
本番EA(MIX_EA)には GoldPBHoldBars として直接埋め込んだ。移植ミスがあれば
数値がずれるため、実測で突き合わせる。

期待値（検証EA・GOLD2枠のみ・USD建て900・時間帯ゲートON）:
  ON (64バー) IS 2510.12 / OOS 720.00
  OFF (0)     IS 2429.34 / OOS 647.28
"""
import copy
import csv
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from measure_books import MT5BT, REPO, WORK, wait_mt5, summary  # noqa: E402

BASE = REPO / "ml" / "gold_dd" / "configs" / "gdda_xm5_gdd06_01_20260814100657_ab9000.yaml"
EXPECT = {("ON", "IS"): 2510.12, ("ON", "OOS"): 720.00,
          ("OFF", "IS"): 2429.34, ("OFF", "OOS"): 647.28}
WINDOWS = {"IS": ("2021.06.21", "2026.06.20"), "OOS": ("2016.06.21", "2021.06.20")}


def main():
    ok = True
    for case in ("ON", "OFF"):
        for win, (frm, to) in WINDOWS.items():
            run = "hl_prod_%s_%s" % (case, win)
            r = summary(run)
            if r is None:
                cfg = copy.deepcopy(yaml.safe_load(open(BASE, encoding="utf-8")))
                cfg["expert"] = "MIX_EA"          # 本番EAで測る
                p = cfg["parameters"]
                for k in list(p):
                    if k.startswith(("R6", "GoldDD", "SimVerify", "GoldHour", "GoldLab")):
                        del p[k]
                p["GoldPBHoldBars"] = 64 if case == "ON" else 0
                p["UseGoldHourGate"] = True       # 採用済みの時間帯ゲートは有効のまま
                for k in ("En_ETH", "En_BTC_FUND", "En_BFXREV"):
                    p[k] = False
                p["ResultFileName"] = run + "_r.csv"
                cfg["from_date"], cfg["to_date"] = frm, to
                cfg["report_name"] = run
                path = WORK / (run + ".yaml")
                yaml.safe_dump(cfg, open(path, "w", encoding="utf-8"),
                               allow_unicode=True, sort_keys=False)
                wait_mt5()
                subprocess.run([str(MT5BT), "run", str(path)], cwd=str(REPO), timeout=5400,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                r = summary(run)
            exp = EXPECT[(case, win)]
            if r is None:
                print("%-4s %-4s FAIL（結果なし）" % (case, win))
                ok = False
                continue
            diff = r["net"] - exp
            hit = abs(diff) < 1.0
            ok = ok and hit
            print("%-4s %-4s net=%9.2f (期待 %9.2f 差 %+7.2f) pf=%.4f dd=%7.4f%% n=%d %s"
                  % (case, win, r["net"], exp, diff, r["pf"], r["ddpct"], r["n"],
                     "一致" if hit else "← 不一致"))
    print("\n判定: %s" % ("本番EAは検証EAを再現している" if ok else "移植にズレあり。要調査"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

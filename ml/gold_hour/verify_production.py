# -*- coding: utf-8 -*-
"""本番EAに入れた時間帯ゲートが検証EAの結果を再現するかを確認する。

検証EA(MIX_EA_SIMVERIFY)は入力でゲートを与えたが、本番EA(MIX_EA)には
ルールを直接埋め込んだ。移植ミスがあれば数値がずれるため実測で突き合わせる。

期待値（検証EA・GOLD2枠のみ・USD建て900）:
  IS  net=2429.3  OOS net=647.3
ゲートOFF(UseGoldHourGate=false)なら採用前の基準に戻るはず:
  IS  net=2394.57 OOS net=579.46
"""
import copy
import csv
import subprocess
import sys
import time
from pathlib import Path

import yaml

MT5BT = Path(r"C:\Users\f\AppData\Local\Python\pythoncore-3.14-64\Scripts\mt5bt.exe")
REPO = Path(__file__).resolve().parents[2]
WORK = REPO / "ml" / "gold_hour" / "configs"
BASE = REPO / "ml" / "gold_dd" / "configs" / "gdda_xm5_gdd06_01_20260814100657_ab9000.yaml"

EXPECT = {
    ("ON", "IS"): 2429.3, ("ON", "OOS"): 647.3,
    ("OFF", "IS"): 2394.57, ("OFF", "OOS"): 579.46,
}
WINDOWS = {"IS": ("2021.06.21", "2026.06.20"), "OOS": ("2016.06.21", "2021.06.20")}


def wait_mt5():
    while True:
        r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq terminal64.exe"],
                           capture_output=True, text=True)
        if "terminal64.exe" not in r.stdout:
            return
        time.sleep(15)


def summary(run):
    f = REPO / "results" / run / "summary.csv"
    if not f.exists():
        return None
    d = {}
    for row in csv.reader(open(f, newline="", encoding="utf-8-sig")):
        if len(row) >= 2:
            d[row[0]] = row[1]
    try:
        return {"net": float(d["純利益"]), "pf": float(d["プロフィットファクター"]),
                "dd": float(d["最大相対DD%"]), "n": int(d["総取引数"])}
    except (KeyError, ValueError):
        return None


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    ok = True
    for gate in ("ON", "OFF"):
        for win, (frm, to) in WINDOWS.items():
            run = "prodgate_%s_%s" % (gate, win)
            r = summary(run)
            if r is None:
                cfg = copy.deepcopy(yaml.safe_load(open(BASE, encoding="utf-8")))
                cfg["expert"] = "MIX_EA"          # 本番EAで測る
                p = cfg["parameters"]
                # 検証EA専用の入力は本番EAに存在しないので落とす
                for k in list(p):
                    if k.startswith(("R6", "GoldDD", "SimVerify", "GoldHour")):
                        del p[k]
                p["UseGoldHourGate"] = (gate == "ON")
                # GOLD2枠のみ（暗号は無効）
                for k in ("En_ETH", "En_BTC_FUND", "En_BFXREV"):
                    p[k] = False
                p["ResultFileName"] = run + "_r.csv"
                p["EquityLogFile"] = run + "_deals.csv"
                cfg["from_date"], cfg["to_date"] = frm, to
                cfg["report_name"] = run
                path = WORK / (run + ".yaml")
                yaml.safe_dump(cfg, open(path, "w", encoding="utf-8"),
                               allow_unicode=True, sort_keys=False)
                wait_mt5()
                subprocess.run([str(MT5BT), "run", str(path)], cwd=str(REPO), timeout=5400,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                r = summary(run)
            exp = EXPECT[(gate, win)]
            if r is None:
                print("%-4s %-4s FAIL（結果なし）" % (gate, win))
                ok = False
                continue
            diff = r["net"] - exp
            hit = abs(diff) < 1.0
            ok = ok and hit
            print("%-4s %-4s net=%9.2f (期待 %9.2f 差 %+7.2f) pf=%.4f dd=%7.4f%% n=%d %s"
                  % (gate, win, r["net"], exp, diff, r["pf"], r["dd"], r["n"],
                     "一致" if hit else "← 不一致"))
    print("\n判定: %s" % ("本番EAは検証EAを再現している" if ok else "移植にズレあり。要調査"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

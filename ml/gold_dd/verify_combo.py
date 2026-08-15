# -*- coding: utf-8 -*-
"""採用2案(GDD07_14 + GDD24_13)の同時適用を実測する。

2案は個別に測定されたもので、組合せは未測定。過去のラウンドで枠間の
相互作用が確認されているため、合算が単純な足し算になる保証はない。

OFF / PBのみ / SCAのみ / 両方 の4条件を、GOLD2(IS/OOS)とXM5 FULLで測る。
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
WORK = REPO / "ml" / "gold_dd" / "configs"
COMMON = Path(r"C:\Users\f\AppData\Roaming\MetaQuotes\Terminal\Common\Files")
OUT = REPO / "ml" / "gold_dd" / "combo_verify.csv"

BASE = WORK / "gdda_xm5_gdd06_01_20260814100657_ab9000.yaml"

# 既定値: PB GOLD rr=2.0 / SCA GOLD rr=1.5
CASES = [
    ("OFF",   {"GoldDDPBRR": 2.0, "GoldDDSCARR": 1.5}),
    ("PB18",  {"GoldDDPBRR": 1.8, "GoldDDSCARR": 1.5}),
    ("SCA17", {"GoldDDPBRR": 2.0, "GoldDDSCARR": 1.7}),
    ("BOTH",  {"GoldDDPBRR": 1.8, "GoldDDSCARR": 1.7}),
]

# XM5はETH履歴の都合で2016.11.09開始。GOLD2は暗号を含まないので従来日付。
SCOPES = {
    "GOLD2_IS":  dict(crypto=False, frm="2021.06.21", to="2026.06.20"),
    "GOLD2_OOS": dict(crypto=False, frm="2016.06.21", to="2021.06.20"),
    "XM5_FULL":  dict(crypto=True,  frm="2016.11.09", to="2026.06.20"),
}
CRYPTO_MAGICS = {"ETH": 20260710, "FUNDING": 20260720, "BFXREV": 20260724}


def wait_mt5():
    import subprocess as sp
    while True:
        r = sp.run(["tasklist", "/FI", "IMAGENAME eq terminal64.exe"],
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


def magics(run):
    """dealに暗号3枠のmagicが実際に現れたか。ETH無音欠落の再発防止。"""
    f = COMMON / (run + "_deals.csv")
    if not f.exists():
        return "dealsファイル不在"
    seen = set()
    for row in csv.reader(open(f, encoding="utf-8-sig", errors="replace")):
        for cell in row:
            try:
                seen.add(int(float(cell)))
            except (TypeError, ValueError):
                pass
    miss = [n for n, m in CRYPTO_MAGICS.items() if m not in seen]
    return "欠落=" + ",".join(miss) if miss else "全枠OK"


def main():
    rows = []
    for scope, s in SCOPES.items():
        for name, ov in CASES:
            run = "combo_%s_%s" % (name, scope)
            r = summary(run)
            if r is None:
                cfg = copy.deepcopy(yaml.safe_load(open(BASE, encoding="utf-8")))
                p = cfg["parameters"]
                p.pop("GoldDDPBATRSL", None)
                p["GoldDDMode"] = 2
                p.update(ov)
                for k in ("En_ETH", "En_BTC_FUND", "En_BFXREV"):
                    p[k] = s["crypto"]
                p["ResultFileName"] = run + "_r.csv"
                p["EquityLogFile"] = run + "_deals.csv"
                cfg["from_date"], cfg["to_date"] = s["frm"], s["to"]
                cfg["report_name"] = run
                path = WORK / (run + ".yaml")
                yaml.safe_dump(cfg, open(path, "w", encoding="utf-8"),
                               allow_unicode=True, sort_keys=False)
                wait_mt5()
                subprocess.run([str(MT5BT), "run", str(path)], cwd=str(REPO),
                               capture_output=False, timeout=5400,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                r = summary(run)
            note = magics(run) if s["crypto"] else "-"
            rows.append({"scope": scope, "case": name,
                         "net": r["net"] if r else "", "pf": r["pf"] if r else "",
                         "dd": r["dd"] if r else "", "n": r["n"] if r else "",
                         "magic": note})
            print("%-10s %-6s %s | %s"
                  % (scope, name,
                     ("net=%+10.0f pf=%.4f dd=%8.4f%% n=%d"
                      % (r["net"], r["pf"], r["dd"], r["n"])) if r else "FAIL",
                     note), flush=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("\n→ %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())

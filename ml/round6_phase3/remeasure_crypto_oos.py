# -*- coding: utf-8 -*-
"""暗号系厳格改善2件のOOSを、ETHを含めて再測定する。

【背景】docs/eth_history_investigation_20260813.md
round6_phase2の48 OOS構成はすべて開始日2016.06.21で、ブローカーのETHUSD履歴開始
(2016.11.08)より前だったためETH枠のhandle生成が失敗し、無音で欠落していた。
つまり従来の「暗号3枠」OOS値は実質 BTC funding + BfxRev の2枠のみだった。

【本スクリプト】開始日を2016.11.09に変更してOOSを測り直す。
検出漏れを防ぐため、生成されたdealに各枠のmagicが実際に現れることをassertする
(従来のrun_decomposition.pyはファイル存在しか見ておらず、これが最終報告まで通った原因)。
"""
import copy
import csv
import subprocess
import sys
from pathlib import Path

import yaml

MT5BT = r"C:\Users\f\AppData\Local\Python\pythoncore-3.14-64\Scripts\mt5bt.exe"
REPO = Path(__file__).resolve().parents[2]
WORK = REPO / "ml" / "round6_phase3" / "configs"
WORK.mkdir(parents=True, exist_ok=True)
OUT = REPO / "ml" / "round6_phase3" / "crypto_oos_remeasure.csv"
COMMON_FILES = Path(r"C:\Users\f\AppData\Roaming\MetaQuotes\Terminal\Common\Files")

# ETHUSD履歴開始は2016.11.08。OnInit時点でバーが存在するよう翌日から開始する。
WINDOWS = {
    "OOS_FIXED": ("2016.11.09", "2021.06.20"),   # ETHを含む正しいOOS
    "IS":        ("2021.06.21", "2026.06.20"),   # 参照用（元から正常）
}

# 暗号3枠のmagic（欠落検出用）
CRYPTO_MAGICS = {"ETH": 20260710, "FUNDING": 20260720, "BFXREV": 20260724}

# input名は experts/MIX_EA_SIMVERIFY.mq5 の実装に合わせる（R6CryptoMode=1がcause機構）
CASES = [
    ("OFF",  {"R6CryptoMode": 0}),
    ("D5",   {"R6CryptoMode": 1, "R6CryptoLookbackDays": 1,
              "R6CryptoCooldownDays": 3, "R6CryptoShockPct": 5.0}),
    ("D10",  {"R6CryptoMode": 1, "R6CryptoLookbackDays": 1,
              "R6CryptoCooldownDays": 3, "R6CryptoShockPct": 10.0}),
]

# 既存の暗号3枠構成をベースに使う（枠のON/OFFとUSD建て設定がそのまま流用できる）
BASE_CFG = REPO / "ml" / "round6_phase3" / "configs" / "r6p3_decomp_full_crypto3_off.yaml"


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


def assert_magics_present(run, expected):
    """dealに期待するmagicが実際に現れたか検査する。欠落は静かに通さない。"""
    # EA側は FileOpen(..., FILE_COMMON) で書くため共通Filesフォルダに出る。
    # results/配下ではない点に注意（ここを取り違えて検査が空振りした）。
    f = COMMON_FILES / (run + "_deals.csv")
    if not f.exists():
        return None, "dealsファイル不在: %s" % f.name
    seen = set()
    try:
        for row in csv.DictReader(open(f, encoding="utf-8-sig")):
            for k in row:
                if k and "magic" in k.lower() and row[k]:
                    try:
                        seen.add(int(float(row[k])))
                    except ValueError:
                        pass
    except Exception as e:
        return None, "deals読取失敗: %s" % e
    missing = [n for n, m in expected.items() if m not in seen]
    return (len(missing) == 0), ("欠落=" + ",".join(missing) if missing else "全枠OK")


def main():
    if not BASE_CFG.exists():
        print("ベースconfigがありません: %s" % BASE_CFG)
        print("round6_phase3のconfigs/から暗号3枠構成のyamlを指定してください。")
        return 1
    rows = []
    for win, (frm, to) in WINDOWS.items():
        for name, ov in CASES:
            run = "cryptoRM_%s_%s" % (name, win)
            r = summary(run)
            if r is None:
                cfg = copy.deepcopy(yaml.safe_load(open(BASE_CFG, encoding="utf-8")))
                cfg["from_date"], cfg["to_date"] = frm, to
                cfg["parameters"].update(ov)
                cfg["parameters"]["ResultFileName"] = run + "_r.csv"
                # ランごとに一意にする。従来は全ランで同名だったためdealが上書きされ、
                # 枠の欠落を検査できなかった（ETH無音欠落を見逃した原因のひとつ）
                cfg["parameters"]["EquityLogFile"] = run + "_deals.csv"
                cfg["parameters"]["OpsLogPrefix"] = run + "_ops"
                cfg["report_dir"] = "results"
                cfg["report_name"] = run
                p = WORK / (run + ".yaml")
                yaml.safe_dump(cfg, open(p, "w", encoding="utf-8"),
                               allow_unicode=True, sort_keys=False)
                subprocess.run([MT5BT, "run", str(p)], cwd=str(REPO),
                               capture_output=True, text=True, timeout=3600)
                r = summary(run)
            ok, note = assert_magics_present(run, CRYPTO_MAGICS)
            rows.append({"window": win, "case": name,
                         "net": r["net"] if r else "", "pf": r["pf"] if r else "",
                         "dd": r["dd"] if r else "", "n": r["n"] if r else "",
                         "magics_ok": ok, "note": note})
            print("%-10s %-4s %s | magic検査: %s"
                  % (win, name,
                     ("net=%+9.0f pf=%.4f dd=%7.4f%% n=%d" % (r["net"], r["pf"], r["dd"], r["n"]))
                     if r else "FAIL",
                     note), flush=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("\n→ %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())

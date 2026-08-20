# -*- coding: utf-8 -*-
"""フォワード実資金に合わせた設定で、3口座の想定成績を実測する。

【設定の根拠】2026-08-15時点の実測残高
  OANDA FX  900282956: balance = equity = 77,954（クレジットなし）
  OANDA CFD 900282957: balance = equity = 102,183
  XM        370406351: balance 52,366 / credit 65,000 / equity 117,366

RefCapはユーザー判断により XM=117,000（クレジット込みequity基準）、
OANDA=78,000（FX口座の実額）で固定した。

倍率はすべてx1（現行フォワードと同じ）。バックテストで確認した高倍率は
適用していない。フォワードの結果を見てから判断する方針のため。
"""
import csv
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from measure_books import MT5BT, REPO, WORK, OANDA_PATH, XM_PATH, wait_mt5, summary  # noqa: E402

OUT = REPO / "ml" / "deploy50" / "forward_settings.csv"
WINDOWS = {"IS": ("2021.06.21", "2026.06.20", 60.0),
           "FULL": ("2016.11.09", "2026.06.20", 115.0)}

COMMON_ON = {
    "UseGoldHourGate": True, "GoldPBHoldBars": 64,
}

ACCOUNTS = {
    "OANDA_FX": {
        "path": OANDA_PATH, "expert": "MIX_EA_OANDA", "symbol": "USDJPY",
        "deposit": 77954,
        "params": {
            "En_PB_USDJPY": True, "En_PB_GBPJPY": True, "En_PB_AUDJPY": False,
            "En_PB_GOLD": False, "En_RSI_USDJPY": True, "En_RSI_EURUSD": True,
            "En_RSI_GBPUSD": True, "En_PAIR": True, "En_CARRY": True, "En_VBO": False,
            "En_ETH": False, "En_SCA_GOLD": False,
            "En_SCA_USDJPY": True, "En_SCA_GBPJPY": True,
            "RefCap_PB_USDJPY": 78000, "RefCap_PB_GBPJPY": 78000, "RefCap_CARRY": 78000,
        },
    },
    "OANDA_CFD": {
        "path": OANDA_PATH, "expert": "MIX_EA_OANDA", "symbol": "XAUUSD",
        "deposit": 102183,
        "params": {
            "En_PB_USDJPY": False, "En_PB_GBPJPY": False, "En_PB_AUDJPY": False,
            "En_PB_GOLD": True, "En_RSI_USDJPY": False, "En_RSI_EURUSD": False,
            "En_RSI_GBPUSD": False, "En_PAIR": False, "En_CARRY": False, "En_VBO": False,
            "En_ETH": False, "En_SCA_GOLD": True,
            "En_SCA_USDJPY": False, "En_SCA_GBPJPY": False,
        },
    },
    "XM": {
        "path": XM_PATH, "expert": "MIX_EA", "symbol": "USDJPY",
        "deposit": 117366,
        "params": {
            "En_PB_USDJPY": True, "En_PB_GBPJPY": True, "En_PB_AUDJPY": False,
            "En_PB_GOLD": True, "En_RSI_USDJPY": True, "En_RSI_EURUSD": True,
            "En_RSI_GBPUSD": True, "En_PAIR": True, "En_CARRY": True, "En_VBO": False,
            "En_ETH": True, "En_BTC_FUND": True, "En_BFXREV": True,
            "En_SCA_GOLD": True, "En_SCA_USDJPY": True, "En_SCA_GBPJPY": True,
            "FundUseWebRequest": False, "BfxUseWebRequest": False,
            "RefCap_PB_USDJPY": 117000, "RefCap_PB_GBPJPY": 117000, "RefCap_CARRY": 117000,
        },
    },
}


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, spec in ACCOUNTS.items():
        for win, (frm, to, months) in WINDOWS.items():
            run = "fwdset_%s_%s" % (name.lower(), win.lower())
            r = summary(run)
            if r is None:
                cfg = {
                    "mt5_path": spec["path"], "expert": spec["expert"],
                    "symbol": spec["symbol"], "period": "M15",
                    "from_date": frm, "to_date": to,
                    "deposit": spec["deposit"], "currency": "JPY", "leverage": 25,
                    "model": "every_tick",
                    "parameters": dict(spec["params"], **COMMON_ON,
                                       **{"ResultFileName": run + "_r.csv"}),
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
                print("%-10s %-4s FAIL" % (name, win), flush=True)
                continue
            dep = spec["deposit"]
            monthly = r["net"] / months / dep * 100
            rf = r["net"] / (r["ddpct"] / 100.0 * dep) if r["ddpct"] > 0 else 0
            over = " ←DD30%超" if r["ddpct"] > 30.0 else ""
            rows.append({"account": name, "deposit": dep, "window": win,
                         "net": r["net"], "pf": r["pf"], "dd_pct": r["ddpct"],
                         "monthly_pct": monthly, "rf": rf, "n": r["n"]})
            print("%-10s %-4s 入金%7d 純利益%+10.0f PF%.4f DD%6.2f%% 月利%6.2f%% RF%5.1f n=%d%s"
                  % (name, win, dep, r["net"], r["pf"], r["ddpct"], monthly, rf,
                     r["n"], over), flush=True)
            with open(OUT, "w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)
    print("\n→ %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())

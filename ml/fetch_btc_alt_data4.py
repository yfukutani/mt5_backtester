# -*- coding: utf-8 -*-
"""
第4バックログ用: 多銘柄funding+perp日足の取得（Binance・無料/認証不要）。
G1メカニズム（funding悲観極端→踏み上げ）の多銘柄移植（FX系ファミリー）用。
出力: funding_<sym>.csv / perp_<sym>.csv（ml/*.csvはgitignore）
"""
import csv
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).parent
UA = {"User-Agent": "Mozilla/5.0 (research; mt5-backtester)"}

SYMBOLS = ["LTCUSDT", "XRPUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT", "ADAUSDT"]


def get_json(url, retries=3, timeout=30):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            if i == retries - 1:
                raise
            print(f"  retry {i+1}: {e}", flush=True)
            time.sleep(3)


def save(rows, header, fname):
    with open(OUT / fname, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    if rows:
        t0 = datetime.fromtimestamp(rows[0][0], timezone.utc)
        t1 = datetime.fromtimestamp(rows[-1][0], timezone.utc)
        print(f"  {len(rows)}件 {t0.date()}..{t1.date()} -> {fname}", flush=True)


def fetch_funding(sym):
    rows = []
    start = int(datetime(2019, 9, 1, tzinfo=timezone.utc).timestamp() * 1000)
    while True:
        url = (f"https://fapi.binance.com/fapi/v1/fundingRate"
               f"?symbol={sym}&startTime={start}&limit=1000")
        data = get_json(url)
        if not data:
            break
        for d in data:
            rows.append((int(d["fundingTime"]) // 1000, float(d["fundingRate"])))
        if len(data) < 1000:
            break
        start = int(data[-1]["fundingTime"]) + 1
        time.sleep(0.3)
    save(rows, ["time", "funding_rate"], f"funding_{sym.replace('USDT','').lower()}.csv")


def fetch_klines(sym):
    rows = []
    start = int(datetime(2019, 9, 1, tzinfo=timezone.utc).timestamp() * 1000)
    while True:
        url = (f"https://fapi.binance.com/fapi/v1/klines"
               f"?symbol={sym}&interval=1d&startTime={start}&limit=1000")
        data = get_json(url)
        if not data:
            break
        for k in data:
            rows.append((int(k[0]) // 1000, float(k[1]), float(k[2]), float(k[3]), float(k[4])))
        if len(data) < 1000:
            break
        start = int(data[-1][0]) + 86400000
        time.sleep(0.3)
    save(rows, ["time", "open", "high", "low", "close"], f"perp_{sym.replace('USDT','').lower()}.csv")


if __name__ == "__main__":
    ok, ng = [], []
    for sym in SYMBOLS:
        try:
            print(f"{sym}...", flush=True)
            fetch_funding(sym)
            fetch_klines(sym)
            ok.append(sym)
        except Exception as e:
            print(f"  {sym} 失敗: {e}", flush=True)
            ng.append(sym)
    print(f"完了: {ok} / 失敗: {ng}")

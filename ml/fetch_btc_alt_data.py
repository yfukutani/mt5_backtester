# -*- coding: utf-8 -*-
"""
BTC外部データ取得基盤（バックログG系の解放・無料API/認証不要）。
- G1: Binance永久先物 Funding Rate（BTCUSDT・8時間毎・2019.09〜）
- G3: Fear & Greed Index（alternative.me・日次・2018.02〜）
- G6: ネットワークハッシュレート（blockchain.info・全期間）
出力: このスクリプトと同じ場所に funding_btc.csv / fng.csv / hashrate.csv
再実行すると全量を取り直す（冪等）。
"""
import csv
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).parent
UA = {"User-Agent": "Mozilla/5.0 (research; mt5-backtester)"}


def get_json(url, retries=3):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            if i == retries - 1:
                raise
            print(f"  retry {i+1}: {e}")
            time.sleep(2)


def fetch_funding():
    print("G1 Funding Rate (Binance BTCUSDT perp)...")
    rows = []
    start = int(datetime(2019, 9, 1, tzinfo=timezone.utc).timestamp() * 1000)
    while True:
        url = (f"https://fapi.binance.com/fapi/v1/fundingRate"
               f"?symbol=BTCUSDT&startTime={start}&limit=1000")
        data = get_json(url)
        if not data:
            break
        for d in data:
            rows.append((int(d["fundingTime"]) // 1000, float(d["fundingRate"])))
        if len(data) < 1000:
            break
        start = int(data[-1]["fundingTime"]) + 1
        time.sleep(0.3)
    with open(OUT / "funding_btc.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["time", "funding_rate"])
        w.writerows(rows)
    t0 = datetime.fromtimestamp(rows[0][0], timezone.utc)
    t1 = datetime.fromtimestamp(rows[-1][0], timezone.utc)
    print(f"  {len(rows)}件 {t0.date()}..{t1.date()} -> funding_btc.csv")


def fetch_fng():
    print("G3 Fear & Greed Index (alternative.me)...")
    data = get_json("https://api.alternative.me/fng/?limit=0&format=json")
    rows = [(int(d["timestamp"]), int(d["value"]), d["value_classification"])
            for d in data["data"]]
    rows.sort()
    with open(OUT / "fng.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["time", "value", "label"])
        w.writerows(rows)
    t0 = datetime.fromtimestamp(rows[0][0], timezone.utc)
    t1 = datetime.fromtimestamp(rows[-1][0], timezone.utc)
    print(f"  {len(rows)}件 {t0.date()}..{t1.date()} -> fng.csv")


def fetch_hashrate():
    print("G6 Hash Rate (blockchain.info)...")
    data = get_json("https://api.blockchain.info/charts/hash-rate"
                    "?timespan=all&format=json&sampled=false")
    rows = [(int(p["x"]), float(p["y"])) for p in data["values"]]
    with open(OUT / "hashrate.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["time", "hashrate_ths"])
        w.writerows(rows)
    t0 = datetime.fromtimestamp(rows[0][0], timezone.utc)
    t1 = datetime.fromtimestamp(rows[-1][0], timezone.utc)
    print(f"  {len(rows)}件 {t0.date()}..{t1.date()} -> hashrate.csv")


if __name__ == "__main__":
    ok = []
    for name, fn in (("funding", fetch_funding), ("fng", fetch_fng),
                     ("hashrate", fetch_hashrate)):
        try:
            fn()
            ok.append(name)
        except Exception as e:
            print(f"  {name} 取得失敗: {e}")
    print(f"完了: {ok}")

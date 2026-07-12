# -*- coding: utf-8 -*-
"""
BTC外部データ取得基盤 第2弾（第2バックログP/V/X系用・無料API/認証不要）。
第1弾（fetch_btc_alt_data.py: funding/F&G/hashrate）に続き、
「唯一の生存戦略G1が新情報源由来」の教訓からポジショニング・バリュエーション・
クロス市場プレミアム系のデータを揃える。

- P5: Binance ETHUSDT永久先物 Funding Rate（8時間毎・2019.11〜）
- P11-13: CFTC COT（TFF・CME Bitcoin先物・週次・2017.12〜、socrata公開API）
- V系: blockchain.info チャート群（difficulty / miners-revenue / transaction-fees-usd /
        n-transactions / estimated-transaction-volume-usd / market-cap）
- X系: Binance現物 BTCUSDT 日足（2017.08〜） + Coinbase BTC-USD 日足（2015〜）
        → Coinbaseプレミアム・spot/perp乖離の材料

出力: このスクリプトと同じ場所に *.csv（ml/*.csvはgitignore済み）。再実行で全量取り直し（冪等）。
"""
import csv
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).parent
UA = {"User-Agent": "Mozilla/5.0 (research; mt5-backtester)"}


def get_json(url, retries=3, timeout=30):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            if i == retries - 1:
                raise
            print(f"  retry {i+1}: {e}")
            time.sleep(2)


def save(rows, header, fname):
    with open(OUT / fname, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    if rows:
        t0 = datetime.fromtimestamp(rows[0][0], timezone.utc)
        t1 = datetime.fromtimestamp(rows[-1][0], timezone.utc)
        print(f"  {len(rows)}件 {t0.date()}..{t1.date()} -> {fname}")
    else:
        print(f"  0件 -> {fname} (要調査)")


def fetch_funding_eth():
    print("P5 ETH Funding Rate (Binance ETHUSDT perp)...")
    rows = []
    start = int(datetime(2019, 11, 1, tzinfo=timezone.utc).timestamp() * 1000)
    while True:
        url = (f"https://fapi.binance.com/fapi/v1/fundingRate"
               f"?symbol=ETHUSDT&startTime={start}&limit=1000")
        data = get_json(url)
        if not data:
            break
        for d in data:
            rows.append((int(d["fundingTime"]) // 1000, float(d["fundingRate"])))
        if len(data) < 1000:
            break
        start = int(data[-1]["fundingTime"]) + 1
        time.sleep(0.3)
    save(rows, ["time", "funding_rate"], "funding_eth.csv")


def fetch_cot():
    print("P11-13 CFTC COT TFF - CME Bitcoin (socrata)...")
    # TFF Futures Only データセット。列名はAPIで揺れるため防御的に解決する。
    base = "https://publicreporting.cftc.gov/resource/gpe5-46if.json"
    q = urllib.parse.urlencode({
        "$where": "upper(contract_market_name) like 'BITCOIN%'",
        "$limit": "5000",
        "$order": "report_date_as_yyyy_mm_dd",
    })
    data = get_json(f"{base}?{q}", timeout=60)
    if not data:
        print("  0件 — データセットID/列名要確認")
        return
    keys = data[0].keys()
    print(f"  生{len(data)}件 市場名例: {sorted(set(d.get('contract_market_name','?') for d in data))[:4]}")

    def find_key(*subs):
        for k in keys:
            kl = k.lower()
            if all(s in kl for s in subs):
                return k
        return None

    k_date = find_key("report_date")
    k_ll = find_key("lev_money", "long")
    k_ls = find_key("lev_money", "short")
    k_al = find_key("asset_mgr", "long") or find_key("asset", "long")
    k_as = find_key("asset_mgr", "short") or find_key("asset", "short")
    k_oi = find_key("open_interest")
    print(f"  解決列: date={k_date} lev_long={k_ll} lev_short={k_ls} am_long={k_al} am_short={k_as} oi={k_oi}")
    rows = []
    for d in data:
        # 本体契約のみ（MICRO等の派生は除外）
        if d.get("contract_market_name", "").strip().upper() != "BITCOIN":
            continue
        try:
            ts = int(datetime.fromisoformat(d[k_date].replace("T", " ").split(".")[0])
                     .replace(tzinfo=timezone.utc).timestamp())
            rows.append((ts,
                         float(d.get(k_ll) or 0), float(d.get(k_ls) or 0),
                         float(d.get(k_al) or 0), float(d.get(k_as) or 0),
                         float(d.get(k_oi) or 0)))
        except Exception:
            continue
    rows.sort()
    save(rows, ["time", "lev_long", "lev_short", "am_long", "am_short", "oi"], "cot_btc.csv")


def fetch_chain(name, fname, col):
    print(f"V系 {name} (blockchain.info)...")
    data = get_json(f"https://api.blockchain.info/charts/{name}"
                    "?timespan=all&format=json&sampled=false", timeout=60)
    rows = [(int(p["x"]), float(p["y"])) for p in data["values"]]
    save(rows, ["time", col], fname)


def fetch_binance_spot():
    print("X系 Binance現物 BTCUSDT 日足...")
    rows = []
    start = int(datetime(2017, 8, 1, tzinfo=timezone.utc).timestamp() * 1000)
    while True:
        url = (f"https://api.binance.com/api/v3/klines"
               f"?symbol=BTCUSDT&interval=1d&startTime={start}&limit=1000")
        data = get_json(url)
        if not data:
            break
        for k in data:
            rows.append((int(k[0]) // 1000, float(k[1]), float(k[2]),
                         float(k[3]), float(k[4]), float(k[5])))
        if len(data) < 1000:
            break
        start = int(data[-1][0]) + 86400000
        time.sleep(0.3)
    save(rows, ["time", "open", "high", "low", "close", "volume"], "spot_btcusdt.csv")


def fetch_coinbase():
    print("X1 Coinbase BTC-USD 日足（300本/リクエスト制限）...")
    rows = []
    t0 = datetime(2015, 1, 1, tzinfo=timezone.utc)
    end = datetime.now(timezone.utc)
    step = 300 * 86400
    start = int(t0.timestamp())
    while start < int(end.timestamp()):
        stop = min(start + step, int(end.timestamp()))
        url = ("https://api.exchange.coinbase.com/products/BTC-USD/candles"
               f"?granularity=86400&start={datetime.fromtimestamp(start, timezone.utc).isoformat()}"
               f"&end={datetime.fromtimestamp(stop, timezone.utc).isoformat()}")
        data = get_json(url)
        # 形式: [time, low, high, open, close, volume] 降順
        for k in (data or []):
            rows.append((int(k[0]), float(k[3]), float(k[2]), float(k[1]), float(k[4]), float(k[5])))
        start = stop
        time.sleep(0.4)
    rows = sorted(set(rows))
    save(rows, ["time", "open", "high", "low", "close", "volume"], "coinbase_btcusd.csv")


if __name__ == "__main__":
    import sys
    jobs = [
        ("funding_eth", fetch_funding_eth),
        ("cot", fetch_cot),
        ("difficulty", lambda: fetch_chain("difficulty", "chain_difficulty.csv", "difficulty")),
        ("miners_rev", lambda: fetch_chain("miners-revenue", "chain_miners_revenue.csv", "usd")),
        ("fees", lambda: fetch_chain("transaction-fees-usd", "chain_fees_usd.csv", "usd")),
        ("ntx", lambda: fetch_chain("n-transactions", "chain_ntx.csv", "count")),
        ("txvol", lambda: fetch_chain("estimated-transaction-volume-usd", "chain_txvol_usd.csv", "usd")),
        ("mcap", lambda: fetch_chain("market-cap", "chain_mcap.csv", "usd")),
        ("spot", fetch_binance_spot),
        ("coinbase", fetch_coinbase),
    ]
    ok, ng = [], []
    for name, fn in jobs:
        try:
            fn()
            ok.append(name)
        except Exception as e:
            print(f"  {name} 取得失敗: {e}")
            ng.append(name)
    print(f"完了: {ok}")
    if ng:
        print(f"失敗: {ng}")
    sys.exit(0 if not ng else 1)

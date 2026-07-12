# -*- coding: utf-8 -*-
"""
BTC外部データ取得基盤 第3弾（第3バックログQ/W/Y/M系用・無料API/認証不要）。
- Q1-Q5: Bitfinexマージン建玉 long/short（tBTCUSD/tETHUSD・日次サンプル・2013〜）
- W1-W3: CME Bitcoin先物 日足（Yahoo chart API・BTC=F・2017.12〜）
- Y1-Y3: ステーブルコイン総供給（DefiLlama・日次）
- M4/Q3: Bybit funding履歴（BTCUSDT・8h毎）— Binance源の二重化・取引所間乖離
- W4-W5: Deribit DVOL 日足（2021.03〜）
出力: ml/*.csv（gitignore済み）。再実行で全量取り直し（冪等）。
Bitfinexは1分粒度APIを日次サンプリング（各日00:00±30分の平均）で取得するため時間がかかる
（約600リクエスト・7分前後）。
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


def get_json(url, retries=5, timeout=30):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            if i == retries - 1:
                raise
            wait = 120 if "429" in str(e) else 3   # レート制限は120秒バックオフ
            print(f"  retry {i+1}: {e} (wait {wait}s)", flush=True)
            time.sleep(wait)


def save(rows, header, fname, t_idx=0):
    with open(OUT / fname, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    if rows:
        t0 = datetime.fromtimestamp(rows[0][t_idx], timezone.utc)
        t1 = datetime.fromtimestamp(rows[-1][t_idx], timezone.utc)
        print(f"  {len(rows)}件 {t0.date()}..{t1.date()} -> {fname}")
    else:
        print(f"  0件 -> {fname} (要調査)")


def fetch_bitfinex_side(symbol, side, out_file):
    """pos.size 1分足を10000件ずつ辿り、日次(UTC日末)にサンプリング。
    既存CSVがあれば末尾からレジューム（429長期規制対策・低速10秒間隔）"""
    rows = {}
    start = int(datetime(2016, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    if (OUT / out_file).exists():
        with open(OUT / out_file, encoding="utf-8") as f:
            for line in f.readlines()[1:]:
                try:
                    ts, val = line.strip().split(",")
                    rows[int(ts) // 86400] = (int(ts), float(val))
                except Exception:
                    continue
        if rows:
            start = (max(rows.keys()) + 1) * 86400000
            print(f"    resume: {len(rows)}日分あり {datetime.fromtimestamp(start/1000, timezone.utc).date()}から", flush=True)
    end_goal = int(datetime.now(timezone.utc).timestamp() * 1000)
    calls = 0
    while start < end_goal:
        url = (f"https://api-pub.bitfinex.com/v2/stats1/"
               f"pos.size:1m:{symbol}:{side}/hist?limit=10000&sort=1&start={start}")
        data = get_json(url, timeout=60)
        calls += 1
        if not data:
            break
        for ts, val in data:
            day = int(ts) // 86400000
            rows[day] = (int(ts) // 1000, float(val))   # 同日内は最後の値で上書き=日末値
        last_ts = int(data[-1][0])
        if last_ts <= start:
            break
        start = last_ts + 60000
        if calls % 20 == 0:
            print(f"    {symbol}:{side} {calls}calls {datetime.fromtimestamp(last_ts/1000, timezone.utc).date()}", flush=True)
            out = [(v[0], v[1]) for k, v in sorted(rows.items())]
            save(out, ["time", "size"], out_file)   # 途中保存（レジューム用）
        time.sleep(5)   # stats1はIPレベルの長期429あり（バースト厳禁・12req/分なら安定）
    out = [(v[0], v[1]) for k, v in sorted(rows.items())]
    return out


def fetch_bitfinex():
    # ETH系列はレート制限のコスト対効果で当面見送り（Q5は後日）
    for sym, tag in (("tBTCUSD", "btc"),):
        for side in ("long", "short"):
            print(f"Q系 Bitfinexマージン {sym} {side}...", flush=True)
            rows = fetch_bitfinex_side(sym, side, f"bfx_{tag}_{side}.csv")
            save(rows, ["time", "size"], f"bfx_{tag}_{side}.csv")


def fetch_cme():
    print("W系 CME Bitcoin先物 日足 (Yahoo BTC=F)...")
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           + urllib.parse.quote("BTC=F") + "?range=max&interval=1d")
    data = get_json(url, timeout=60)
    res = data["chart"]["result"][0]
    ts = res["timestamp"]
    q = res["indicators"]["quote"][0]
    rows = []
    for i in range(len(ts)):
        c = q["close"][i]
        if c is None:
            continue
        rows.append((int(ts[i]), float(q["open"][i] or c), float(c)))
    save(rows, ["time", "open", "close"], "cme_btc.csv")


def fetch_stablecoins():
    print("Y系 ステーブルコイン総供給 (DefiLlama)...")
    data = get_json("https://stablecoins.llama.fi/stablecoincharts/all", timeout=60)
    rows = []
    for d in data:
        try:
            ts = int(d["date"])
            v = d.get("totalCirculatingUSD", {})
            usd = float(v.get("peggedUSD", 0)) if isinstance(v, dict) else float(v)
            if usd > 0:
                rows.append((ts, usd))
        except Exception:
            continue
    rows.sort()
    save(rows, ["time", "usd"], "stablecoins.csv")


def fetch_bybit_funding():
    print("M4/Q3 Bybit funding履歴 (BTCUSDT)...")
    rows = []
    end = int(datetime.now(timezone.utc).timestamp() * 1000)
    while True:
        url = ("https://api.bybit.com/v5/market/funding/history"
               f"?category=linear&symbol=BTCUSDT&limit=200&endTime={end}")
        data = get_json(url)
        lst = data.get("result", {}).get("list", [])
        if not lst:
            break
        for d in lst:
            rows.append((int(d["fundingRateTimestamp"]) // 1000, float(d["fundingRate"])))
        oldest = min(int(d["fundingRateTimestamp"]) for d in lst)
        if oldest >= end:
            break
        end = oldest - 1
        if len(rows) % 2000 == 0:
            print(f"    {len(rows)}件 {datetime.fromtimestamp(oldest/1000, timezone.utc).date()}")
        time.sleep(0.3)
    rows = sorted(set(rows))
    save(rows, ["time", "funding_rate"], "funding_bybit.csv")


def fetch_dvol():
    print("W4-W5 Deribit DVOL 日足...")
    rows = []
    start = int(datetime(2021, 3, 1, tzinfo=timezone.utc).timestamp() * 1000)
    end_goal = int(datetime.now(timezone.utc).timestamp() * 1000)
    while start < end_goal:
        stop = min(start + 700 * 86400000, end_goal)
        url = ("https://www.deribit.com/api/v2/public/get_volatility_index_data"
               f"?currency=BTC&start_timestamp={start}&end_timestamp={stop}&resolution=1D")
        data = get_json(url, timeout=60)
        for rec in data.get("result", {}).get("data", []):
            # [timestamp_ms, open, high, low, close]
            rows.append((int(rec[0]) // 1000, float(rec[4])))
        start = stop + 86400000
        time.sleep(0.5)
    rows = sorted(set(rows))
    save(rows, ["time", "dvol"], "dvol_btc.csv")


if __name__ == "__main__":
    import sys
    only = sys.argv[1] if len(sys.argv) > 1 else None
    jobs = [
        ("cme", fetch_cme),
        ("stable", fetch_stablecoins),
        ("bybit", fetch_bybit_funding),
        ("dvol", fetch_dvol),
        ("bitfinex", fetch_bitfinex),   # 最後（長い）
    ]
    ok, ng = [], []
    for name, fn in jobs:
        if only and name != only:
            continue
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

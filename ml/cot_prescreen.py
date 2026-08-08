# -*- coding: utf-8 -*-
"""COT(米国商品先物取引委員会 建玉明細)オーバーレイの事前分析(Python統計・EA実装前のスクリーニング)。

NEW_PLAN_EAバックログのF13/F15/F16/F17等と同じ方法論: 本格的なEA実装の前に、
仮説が統計的に成立するかを軽量なPython分析で確認する。|t|<2ならEA実装せず即棄却。

データ源: CFTC Legacy Futures Only Report（Socrata公開API・認証不要・週次・1986〜）+
stooq.com日足CSV（無料・認証不要）をCOT報告日（火曜）非重複の週次リターンにリサンプル。

【重要】初版はYahoo Financeのinterval=1wkが実際には月次データ(dataGranularity=1mo)を
返す既知の挙動により、COTの週次イベントを重複カウントし t値が異常に膨張していた
（GOLD売越極端でt=-13.72という非現実的な値）。本版はstooq日足→週次非重複リサンプルに
差し替えて再計算する。
"""
import csv
import io
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import numpy as np

UA = {"User-Agent": "Mozilla/5.0 (research; mt5-backtester)"}
BASE = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"

MARKETS = {
    # stooq.comはボット判定でCSV取得不可。Yahooはinterval=1wkが実際には月次を返す既知の
    # 挙動があるためinterval=1d(日足・全期間)を取得し、こちら側で正しく週次に整合させる。
    "GOLD": ("GOLD - COMMODITY EXCHANGE INC.", "GC=F"),
    "EURFX": ("EURO FX - CHICAGO MERCANTILE EXCHANGE", "EURUSD=X"),
    "AUD": ("AUSTRALIAN DOLLAR - CHICAGO MERCANTILE EXCHANGE", "AUDUSD=X"),
}


def fetch_cot(market_name):
    q = ("$where=" + urllib.parse.quote("market_and_exchange_names='%s'" % market_name)
         + "&$select=report_date_as_yyyy_mm_dd,noncomm_positions_long_all,noncomm_positions_short_all"
         + "&$order=report_date_as_yyyy_mm_dd&$limit=3000")
    url = BASE + "?" + q
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read().decode())
    rows = []
    for d in data:
        try:
            t = datetime.strptime(d["report_date_as_yyyy_mm_dd"][:10], "%Y-%m-%d").date()
            net = int(d["noncomm_positions_long_all"]) - int(d["noncomm_positions_short_all"])
            rows.append((t, net))
        except (KeyError, ValueError):
            continue
    return rows


def fetch_yahoo_daily(symbol):
    # range=max はサーバー側でinterval指定を無視し月次に強制ダウンサンプルする既知の挙動があるため、
    # period1/period2を明示指定して真の日足を取得する（実測: range=maxはmeta.dataGranularity=1moを返す）。
    px = {}
    end = datetime.now(tz=timezone.utc)
    start = datetime(1999, 1, 1, tzinfo=timezone.utc)
    cur_end = end
    while cur_end > start:
        cur_start = max(start, cur_end - timedelta(days=365 * 3))
        url = ("https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(symbol)
               + "?period1=%d&period2=%d&interval=1d" % (int(cur_start.timestamp()), int(cur_end.timestamp())))
        req = urllib.request.Request(url, headers=UA)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read().decode())
            res = data["chart"]["result"][0]
            ts = res.get("timestamp") or []
            closes = res["indicators"]["quote"][0]["close"]
            for t, c in zip(ts, closes):
                if c is None:
                    continue
                d = datetime.fromtimestamp(t, tz=timezone.utc).date()
                px[d] = float(c)
        except urllib.error.HTTPError as e:
            print("    (chunk %s-%s failed: %s)" % (cur_start.date(), cur_end.date(), e))
        cur_end = cur_start - timedelta(days=1)
    return px


print("=" * 96)
print("COT事前分析(訂正版・stooq日足→COT報告日ちょうどの非重複週次リターン)")
print("仮説: 非商業ネットポジションの週次変化(前週比)が極端 → 翌週(次のCOT報告日まで)の価格方向")
for name, (market, stq) in MARKETS.items():
    try:
        cot = fetch_cot(market)
    except Exception as e:
        print("%-8s COT取得失敗: %s" % (name, e))
        continue
    try:
        px = fetch_yahoo_daily(stq)
    except Exception as e:
        print("%-8s 価格取得失敗: %s" % (name, e))
        continue
    if len(cot) < 100 or len(px) < 500:
        print("%-8s データ不足 COTn=%d 価格n=%d" % (name, len(cot), len(px)))
        continue

    px_dates = sorted(px.keys())

    def price_on_or_after(d0, start_idx=0):
        # px_dates は昇順なのでstart_idxから前進探索（毎回全探索を避ける）。
        # 戻り値は (価格, その日付のpx_datesインデックス) — 次回探索の開始位置に使う。
        i = start_idx
        n = len(px_dates)
        while i < n and px_dates[i] < d0:
            i += 1
        if i >= n:
            return None, None, i
        d = px_dates[i]
        return px[d], d, i

    # COTは1行=1週(火曜報告)。非重複で「この火曜の価格→次の火曜の価格」のリターンのみを使う
    # （前版のバグ=Yahoo週足が実際は月足を返し、多数の週が同一月足に重複マップされ
    #   疑似的に有意になっていた点を解消。今回は日足から週次を正しく1対1で対応させる）
    rets, nets = [], []
    idx = 0
    for i in range(len(cot) - 1):
        d0, net = cot[i]
        d1, _ = cot[i + 1]
        p0, dd0, idx = price_on_or_after(d0, idx)
        if p0 is None:
            break
        p1, dd1, idx2 = price_on_or_after(d1, idx)
        if p1 is None:
            break
        if dd0 == dd1:
            continue   # 同一日にしかマッチしない場合(データ欠損)はスキップ
        rets.append(p1 / p0 - 1.0)
        nets.append(net)
    nets = np.array(nets, dtype=float)
    rets = np.array(rets, dtype=float)
    n_total = len(rets)
    q_hi, q_lo = np.percentile(nets, 90), np.percentile(nets, 10)

    def tstat(mask):
        a = rets[mask]
        if len(a) < 10:
            return None, len(a), None
        return a.mean() / (a.std(ddof=1) / np.sqrt(len(a))), len(a), a.mean()

    t_hi, n_hi, m_hi = tstat(nets >= q_hi)
    t_lo, n_lo, m_lo = tstat(nets <= q_lo)
    fmt = lambda t, m: ("t=%+.2f mean=%+.4f" % (t, m)) if t is not None else "n不足"
    print("%-8s COT週n=%4d 価格n=%5d 対応n=%4d | 買越90%%tile(n=%3d): %s | 売越10%%tile(n=%3d): %s"
          % (name, len(cot), len(px), n_total, n_hi, fmt(t_hi, m_hi), n_lo, fmt(t_lo, m_lo)))

print()
print("判定基準: |t|>=2.0 で初めてEA実装を検討（NEW_PLAN_EAバックログF13-F17と同一基準）。")

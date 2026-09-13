"""V102：**不毛月の損失の86%を占める SCA GBPJPY をどうするか**（簡易検証・2026-09-13）。

【V099の数字を読み直す】
弱局面（38ヶ月）の不毛月18ヶ月で、ブック全体は **−77,869円**。
そのうち **SCA GBPJPY だけで −66,697円（86%）**。

| 枠 | 弱局面 純益 | 不毛月の損益 | 良い月の損益（差分） |
|---|---:|---:|---:|
| **SCA GBPJPY** | **+23,412** | **−66,697** | **+90,109** |

**SCA GBPJPY は良い月に+90,109円を稼ぎ、不毛月に−66,697円を失っている。**
IS窓でも同じ形（不毛月 −67,793円）。

**つまり「不毛月」とは、ほぼ「SCA GBPJPY が負ける月」のことである。**
SCA＝セッションORBブレイクなので、**ブレイクが失敗する（往って来い）相場**。

【試すこと（3つ）】
1. **SCA GBPJPY の重みを下げる** — 0倍〜1.5倍で12ヶ月移動合計のマイナス窓を測る
2. **SCA GBPJPY を「不毛月だけ」止める** — 実際には事前に分からないが、
   **上限（どこまで良くなりうるか）を知る**ために測る
3. **SCA GBPJPY の逆を張る枠を足す** — 「ブレイク失敗の逆張り」の理想化。
   実際にはコストとタイミングで劣化するが、**上限を知る**

**2と3は将来を知っている前提なので採用候補ではない。**
**「直せばどこまで良くなるか」の上限を測るためだけに使う。**

【限界】
- 損益の線形な足し算・引き算。最小ロット制約を無視している
- 2と3は**未来の情報を使う理想化**。実現可能性は別問題
- 弱局面は38ヶ月。12ヶ月窓は27個
- **段階2の簡易検証である。採用の根拠にはしない**
"""
from __future__ import annotations

import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dynamic_k_lag as dkl
import sleeve_ablation as sab

WEAK = (datetime(2016, 11, 9, tzinfo=timezone.utc),
        datetime(2020, 1, 1, tzinfo=timezone.utc))
IS_W = (datetime(2021, 6, 21, tzinfo=timezone.utc),
        datetime(2026, 6, 21, tzinfo=timezone.utc))
TARGET = 20261001          # SCA GBPJPY
WEIGHTS = [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5]


def months_of(a, b):
    out, d = [], datetime(a.year, a.month, 1, tzinfo=timezone.utc)
    while d < b:
        out.append((d.year, d.month))
        d = (datetime(d.year + 1, 1, 1, tzinfo=timezone.utc) if d.month == 12
             else datetime(d.year, d.month + 1, 1, tzinfo=timezone.utc))
    return out


def monthly_by_magic(a, b):
    fx, gold = dkl.resolve_runs()
    ms = months_of(a, b)
    idx = {k: i for i, k in enumerate(ms)}
    out = {}
    for window in ("OOS", "IS"):
        for src in (fx.get(window), gold.get(window)):
            if src is None:
                continue
            rows = []
            for r in csv.DictReader(open(src, encoding="utf-8")):
                m = int(r["magic"])
                if m == 0:
                    continue
                rows.append((int(r["time"]), int(r["entry"]),
                             int(r["position_id"]), float(r["profit"]), m))
            rows.sort()
            opened = {}
            for t, entry, pid, profit, m in rows:
                if entry == 0:
                    opened[pid] = (t, m)
                else:
                    o = opened.pop(pid, None)
                    if o is None or profit == 0.0:
                        continue
                    d = datetime.fromtimestamp(o[0], tz=timezone.utc)
                    if a <= d < b:
                        out.setdefault(m, np.zeros(len(ms)))[idx[(d.year,
                                                                 d.month)]] += profit
    return ms, out


def rolling(v, w):
    if len(v) < w:
        return np.array([])
    return np.array([v[i:i + w].sum() for i in range(len(v) - w + 1)])


def line(label, v):
    r12, r6 = rolling(v, 12), rolling(v, 6)
    return (f"{label:<28}{v.sum():>12,.0f}{r12.min():>14,.0f}"
            f"{f'{int((r12 <= 0).sum())}/{len(r12)}':>13}"
            f"{r6.min():>13,.0f}"
            f"{f'{int((r6 <= 0).sum())}/{len(r6)}':>12}")


def main():
    print("=" * 100)
    print("V102：不毛月の損失の86%を占める SCA GBPJPY をどうするか")
    print("=" * 100)
    print("★ 弱局面の不毛月18ヶ月でブック全体は −77,869円。")
    print("  そのうち **SCA GBPJPY だけで −66,697円（86%）**。")
    print("  **『不毛月』とはほぼ『SCA GBPJPY が負ける月』のことである。**\n")

    for label, (a, b) in (("OOS 弱局面（2016-11〜2019-12）", WEAK),
                          ("IS窓（2021-06〜2026-06）", IS_W)):
        ms, mm = monthly_by_magic(a, b)
        book = np.sum(list(mm.values()), axis=0)
        sca = mm.get(TARGET, np.zeros(len(ms)))
        others = book - sca
        barren = book <= 0
        print("=" * 100)
        print(f"【{label}】{len(ms)}ヶ月 / ブック {book.sum():+,.0f}円 / "
              f"SCA GBPJPY {sca.sum():+,.0f}円 / 不毛月 {int(barren.sum())}ヶ月")
        print("=" * 100)
        print(f"{'条件':<28}{'純益':>12}{'12月移動 最小':>14}{'12月マイナス窓':>13}"
              f"{'6月移動 最小':>13}{'6月マイナス窓':>12}")

        # 1. 重みを振る
        for w in WEIGHTS:
            tag = "**現状**" if w == 1.0 else f"SCA GBPJPY {w:.2f}倍"
            print(line(tag, others + w * sca))

        # 2. 不毛月だけ止める（未来を知っている前提・上限の把握）
        s2 = sca.copy()
        s2[barren] = 0.0
        print(line("〔上限〕不毛月だけ止める", others + s2))

        # 3. 不毛月だけ逆を張る（同上）
        s3 = sca.copy()
        s3[barren] = -s3[barren]
        print(line("〔上限〕不毛月だけ逆を張る", others + s3))

        # 4. SCA GBPJPY の負けた月だけ止める（同上）
        s4 = sca.copy()
        s4[sca < 0] = 0.0
        print(line("〔上限〕SCAが負ける月を止める", others + s4))
        print()

    print("=" * 100)
    print("【読み方】")
    print("=" * 100)
    print("  ・**重みを下げてマイナス窓が減るなら、配分の見直しに意味がある**")
    print("  ・〔上限〕の行は**未来を知っている前提**。採用候補ではない。")
    print("    ただし『完璧に直せてもここまで』という天井を示す。")
    print("  ・上限でもマイナス窓が0にならないなら、**SCA GBPJPYは主因ではない**")

    print("\n" + "=" * 100)
    print("【限界】")
    print("=" * 100)
    print("  ・損益の線形な足し算・引き算。最小ロット制約を無視している")
    print("  ・〔上限〕は未来の情報を使う理想化。実現可能性は別問題")
    print("  ・弱局面は38ヶ月。12ヶ月窓は27個")
    print("  ・**段階2の簡易検証である。採用の根拠にはしない**")
    print("\n完了。")


if __name__ == "__main__":
    main()

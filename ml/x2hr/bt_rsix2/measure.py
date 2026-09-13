"""V100：**RSI横展開4枠の単独バックテスト**（段階3・2026-09-13）。

【なぜこの4枠か】
V099より、ブックが**不毛な月**に稼げるのは RSI GBPUSD と RSI USDJPY の2枠だけ。
1取引シャープの高い PB GOLD・SCA GOLD2 は不毛月にはマイナスで役に立たない。
→ **増やすべきは RSI型（逆張り）。**

【既存の棄却記録を踏まえて候補を絞った】

| 既存記録 | 内容 |
|---|---|
| `project_status.md` | **RSI14 をクロスペアへ展開 → 全滅（ドルストレート限定と判明）** |
| `rejected_strategies.md` §0e | **USDCHF RSI → 棄却**（全期間 −20,635 / PF0.66 / 130取引） |
| `project_status.md` | RSI14 を GBPUSD へ横展開 → **採用**（唯一の成功） |

**したがってクロスペア（EURJPY/AUDJPY/EURGBP等）とUSDCHFは候補から外した。**

残る未検証は——

| 銘柄 | 理由 |
|---|---|
| **GOLD** | 既存3枠（PB GOLD・SCA GOLD1/2）はすべて順張り／ブレイク。**逆張りは一度も試していない。** ブック純益の56%を占める銘柄に逆方向の機構を足す |
| AUDUSD | コモディティ通貨のドルストレート。未検証 |
| NZDUSD | 同上（PullbackTrend版は §0f で棄却済みだが、RSIは別戦略） |
| USDCAD | 同上 |

設定は**採用実績のある RSI GBPUSD のテンプレートを共通で流用**する
（Codexの「銘柄別の大量最適化を避ける」に従う）。
GOLDのみ pips が使えないので ATRストップ（PB GOLDと同じ方式）。

【測り方】
**4枠だけを有効にした単独バックテスト**を IS窓・OOS窓・全期間で回す。
既存ブックと混ぜないのは、**枠単独の性質（特に不毛月の損益）を見たいから。**

判定は2段階。
1. **従来の基準**：IS窓・OOS窓とも純益がプラスか（運用ルール）
2. **V099の新基準**：**既存ブックが不毛な月に稼げるか**

**1を満たさなくても2を満たせば価値がある可能性はあるが、
PF0.66のような明確な赤字枠は救えない。**

【限界】
- 4枠を同時に有効にしているので、枠間の相殺は見えるが個別の寄与は決済ログで分ける
- 設定はGBPUSDのテンプレート流用。**銘柄ごとの最適化はしていない**（意図的）
- GOLDはATRストップなのでGBPUSDと厳密には同一設定ではない
"""
from __future__ import annotations

import csv
import hashlib
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
ROOT = Path(__file__).resolve().parent
RUN_DIR = ROOT / "runs"
CONFIG_DIR = ROOT / "configs"
DEAL_DIR = ROOT / "run_deals"
OUT = ROOT / "results.csv"
LOG = ROOT / "measure.log"
MT5BT = REPO / "mt5bt.bat"
COMMON = Path(r"C:\Users\f\AppData\Roaming\MetaQuotes\Terminal\Common\Files")
EXE = r"C:\Users\f\AppData\Roaming\XMTrading MT5\terminal64.exe"
EA_EX5 = Path(r"C:\Users\f\AppData\Roaming\MetaQuotes\Terminal"
              r"\BAC624F09E3C5D5AFDD21CE91C0B879D\MQL5\Experts\MIX_EA_X2HR.ex5")

DEPOSIT = 500000          # 元の取引ログと同じ入金額（枠単独の素の成績を見る）
RUN_TIMEOUT = 7200

WINDOWS = {
    "FULL": ("2016.11.09", "2026.06.20"),
    "OOS": ("2016.11.09", "2021.06.20"),
    "IS": ("2021.06.21", "2026.06.20"),
}

# RSI横展開4枠だけを有効にする（既存枠はすべてOFF）
BOOK = {
    "En_PB_USDJPY": False, "En_PB_GBPJPY": False, "En_PB_AUDJPY": False,
    "En_PB_GOLD": False, "En_RSI_USDJPY": False, "En_RSI_EURUSD": False,
    "En_RSI_GBPUSD": False, "En_PAIR": False, "En_CARRY": False,
    "En_VBO": False, "En_ETH": False, "En_BTC_FUND": False,
    "En_BFXREV": False, "En_SCA_GOLD": False, "En_SCA_USDJPY": False,
    "En_SCA_GBPJPY": False,
    "En_RSI_X2": True, "Mult_RSI_X2": 1.0,
    "SimVerifyMode": 0, "R6GoldMode": 0, "R6CryptoMode": 0,
    "GoldDDMode": 0, "GoldLabMode": 0, "GoldLabMode2": 0,
    "GszMode": 0, "GszSleeveMask": 0,
    "Sca2Enable": False, "Sca3Enable": False, "Sca4Enable": False,
    "Sca5Enable": False, "Sca6Enable": False, "Pb2Enable": False,
    "FundUseWebRequest": False, "BfxUseWebRequest": False,
    "GlobalLotMult": 1, "DlMode": 0,
    "RefCap_PB_USDJPY": 78000, "RefCap_PB_GBPJPY": 78000,
    "RefCap_CARRY": 78000,
}

MAGICS = {20260790: "RSI GOLD", 20260791: "RSI AUDUSD",
          20260792: "RSI NZDUSD", 20260793: "RSI USDCAD"}

_ea_sha = None


def log(msg):
    line = f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def ea_sha():
    return hashlib.sha256(EA_EX5.read_bytes()).hexdigest()


def kill():
    folder = str(Path(EXE).parent).replace("'", "''")
    ps = ("Get-Process terminal64,metatester64 -ErrorAction SilentlyContinue | "
          f"Where-Object {{ $_.Path -like '{folder}\\*' }} | "
          "Stop-Process -Force -ErrorAction SilentlyContinue")
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                   timeout=120, capture_output=True)


def run_one(window):
    if ea_sha() != _ea_sha:
        raise RuntimeError("EAバイナリが測定中に入れ替わった")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    run_id = f"rsix2_{window.lower()}_{stamp}_{uuid.uuid4().hex[:4]}"
    p = dict(BOOK)
    p["ResultFileName"] = f"{run_id}_result.csv"
    p["EquityLogFile"] = f"{run_id}_deals.csv"
    frm, to = WINDOWS[window]
    lines = [f"mt5_path: {EXE}", "expert: MIX_EA_X2HR", "symbol: USDJPY",
             "period: M15", f"from_date: {frm}", f"to_date: {to}",
             f"deposit: {DEPOSIT}", "currency: JPY", "leverage: 25",
             "model: every_tick", "parameters:"]
    for k, v in p.items():
        lines.append(f"  {k}: "
                     f"{'true' if v is True else 'false' if v is False else v}")
    lines += [f"report_dir: {RUN_DIR}", f"report_name: {run_id}", ""]
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    cfg = CONFIG_DIR / f"{run_id}.yaml"
    cfg.write_text("\n".join(lines), encoding="utf-8")

    log(f"RUN_START {window}")
    t0 = time.time()
    status = "OK"
    try:
        subprocess.run([str(MT5BT), "run", str(cfg), "--no-charts"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=RUN_TIMEOUT, cwd=str(REPO))
    except subprocess.TimeoutExpired:
        kill()
        status = "TIMEOUT"

    row = {"window": window, "run_id": run_id, "status": status,
           "secs": round(time.time() - t0, 1)}
    sp = RUN_DIR / run_id / "summary.csv"
    if sp.exists():
        d = {r[0]: r[1] for r in csv.reader(open(sp, encoding="utf-8"))
             if len(r) >= 2}
        for key, col in (("純利益", "net"), ("最大相対DD%", "dd_pct"),
                         ("総取引数", "trades"),
                         ("プロフィットファクター", "pf")):
            try:
                row[col] = float(d[key])
            except (KeyError, ValueError):
                row[col] = ""

    src = COMMON / f"{run_id}_deals.csv"
    DEAL_DIR.mkdir(parents=True, exist_ok=True)
    if src.exists():
        try:
            src.replace(DEAL_DIR / f"{run_id}_deals.csv")
            row["deals"] = f"{run_id}_deals.csv"
        except OSError:
            row["deals"] = ""
        # 枠別の内訳
        dp = DEAL_DIR / f"{run_id}_deals.csv"
        if dp.exists():
            st = {}
            for r in csv.DictReader(open(dp, encoding="utf-8")):
                name = MAGICS.get(int(r["magic"]))
                if name is None:
                    continue
                a = st.setdefault(name, {"net": 0.0, "n": 0})
                if r["entry"] == "0":
                    a["n"] += 1
                else:
                    a["net"] += float(r["profit"])
            for name, a in st.items():
                key = name.replace("RSI ", "").lower()
                row[f"{key}_net"] = round(a["net"], 0)
                row[f"{key}_n"] = a["n"]
    kill()
    log(f"RUN_END   {window} net={row.get('net','')} pf={row.get('pf','')} "
        f"trades={row.get('trades','')} ({row['secs']}s)")
    return row


def main():
    global _ea_sha
    if not EA_EX5.exists():
        print(f"EAが見つかりません: {EA_EX5}")
        sys.exit(1)
    _ea_sha = ea_sha()
    log(f"START ea_sha={_ea_sha[:12]} deposit={DEPOSIT} (RSI横展開4枠のみ)")
    cols = ["window", "net", "pf", "dd_pct", "trades",
            "gold_net", "gold_n", "audusd_net", "audusd_n",
            "nzdusd_net", "nzdusd_n", "usdcad_net", "usdcad_n",
            "status", "secs", "run_id", "deals"]
    rows = []
    for w in ("OOS", "IS", "FULL"):
        rows.append(run_one(w))
        with open(OUT, "w", encoding="utf-8", newline="") as fh:
            wr = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            wr.writeheader()
            wr.writerows(rows)
    log(f"DONE -> {OUT}")


if __name__ == "__main__":
    main()

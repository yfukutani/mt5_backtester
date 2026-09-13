"""V091：**段階3 — 期限意識サイジングのMT5バックテスト**（2026-09-13）。

【位置づけ】
`CLAUDE.md`「戦略検証の進め方」の**段階3**。
> **採用の最終判断は、必ずMT5バックテストで行う。**
> 取引ログの再サンプリング・数値シミュレーション・解析近似は、
> 段階2（ふるい分け）までの道具であって、採用の根拠にはならない。

【何を測るか】
簡易検証（V083・V086）で「期限意識サイジングが比例方策より到達率を上げる」と出た。
**しかしログ再生は含み損益・証拠金不足による強制決済を扱っていない。**
V088ではIS窓で**資金がマイナスまで突き抜けた経路が4本**出ており、
Codexも「期限が近づくと増額する方策では特に重大」と指摘している。

**MT5なら証拠金・強制決済・銘柄別のロット刻みが正しく効く。** そこを測る。

【設計（Codexの推奨に従う）】
- **起点は成績を見ずに固定する。** 弱局面の**非重複**窓のみ。
  - 6ヶ月：2016-11-09 から6本（〜2019-11-09）
  - 12ヶ月：2016-11-09 から3本（〜2019-11-09）
- 各窓で **DlMode=1（比例のみ）** と **DlMode=2（HJB期限意識）** を回す
- 合計 6×2 + 3×2 = **18実行**
- 資金10万円・破綻ライン10%・目標2倍・倍率2倍固定
- k と 上限は**簡易検証で事前に固定**（6ヶ月 k=4 / 12ヶ月 k=2、上限3倍）

【Codexの但し書き（重く受け止める）】
> 同じ過去期間をMT5で測り直すことは**実行精度の検証**であり、
> **新しいOOSの獲得ではない。** 約6本・約3本では 65%・90% を精密に検証できない。

**したがって本検証の目的は「到達率の精密な推定」ではなく、**
**「含み損益・証拠金を入れても簡易検証の向きが保たれるか」の確認である。**

【ブック】15枠すべて（FX側10枠＋GOLD側5枠）。
RefCap_* は既定の固定値のまま（0にすると資金比例が二重に効く）。

【限界】
- 非重複窓は6本・3本しかない。**到達率の推定には足りない**
- 同じ弱局面を再度使っている。**新しいOOSではない**
- XM端末・XM銘柄で測る。本番ブローカーが違えば結果も違う
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

DEPOSIT = 100000          # 資金10万円（ユーザー指示）
RUN_TIMEOUT = 5400

# --- 起点は成績を見ずに固定（弱局面の非重複窓） ---
ORIGINS_6 = ["2016.11.09", "2017.05.09", "2017.11.09",
             "2018.05.09", "2018.11.09", "2019.05.09"]
ORIGINS_12 = ["2016.11.09", "2017.11.09", "2018.11.09"]
# k と 上限は簡易検証で事前に固定する（OOSを見て選び直さない）
PLAN = [(6, ORIGINS_6, 4.0, 3.0), (12, ORIGINS_12, 2.0, 3.0)]

# 15枠すべて（FX側10枠＋GOLD側5枠）
BOOK = {
    "En_PB_USDJPY": True, "En_PB_GBPJPY": True, "En_PB_AUDJPY": False,
    "En_PB_GOLD": True, "En_RSI_USDJPY": True, "En_RSI_EURUSD": True,
    "En_RSI_GBPUSD": True, "En_PAIR": True, "En_CARRY": True, "En_VBO": False,
    "En_ETH": True, "En_BTC_FUND": True, "En_BFXREV": True,
    "En_SCA_GOLD": True, "En_SCA_USDJPY": True, "En_SCA_GBPJPY": True,
    "SimVerifyMode": 0, "R6GoldMode": 0, "R6CryptoMode": 0,
    "GoldDDMode": 0, "GoldLabMode": 0, "GoldLabMode2": 0,
    "GoldPBHoldBars": 64, "GoldHourGateMode": 1,
    "GoldHourPBWeekMask1": 2, "GoldHourPBStart1": 0, "GoldHourPBEnd1": 7,
    "GoldHourPBWeekMask2": 32, "GoldHourPBStart2": 12, "GoldHourPBEnd2": 16,
    "GszMode": 0, "GszSleeveMask": 0,
    "Sca2Enable": False, "Sca3Enable": False, "Sca4Enable": False,
    "Sca5Enable": False, "Sca6Enable": False, "Pb2Enable": False,
    "FundUseWebRequest": False, "BfxUseWebRequest": False,
    "GlobalLotMult": 1,
    # 【必須】EAの既定は 0（＝口座equity連動）。**指定しないと別物を測る。**
    # 元の取引ログを作った fxmult1 の実行は 78000（固定＝非複利）だった。
    # 落としたまま最初の試験実行をしたところ、Carry AUDJPY が 0.05→0.19ロットになり、
    # 2016-11-09（米大統領選の急落）の1取引で −90,003円＝破綻した。
    # さらに RefCap=0 のままだと枠側でも資金比例が効き、DlMult() の ratio と
    # **二重に効く**（Codexが事前に指摘していた落とし穴）。
    # 資金連動なのはこの3枠だけで、他は固定ロット。ここを固定にすれば
    # 全枠が入金額に依存せず、元のログのロットを再現できる。
    "RefCap_PB_USDJPY": 78000, "RefCap_PB_GBPJPY": 78000, "RefCap_CARRY": 78000,
}

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


def add_months(d: str, months: int) -> str:
    y, m, day = (int(x) for x in d.split("."))
    mm = m - 1 + months
    y += mm // 12
    m = mm % 12 + 1
    dim = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    md = dim[m - 1]
    if m == 2 and ((y % 4 == 0 and y % 100 != 0) or y % 400 == 0):
        md = 29
    return f"{y:04d}.{m:02d}.{min(day, md):02d}"


def run_one(months, origin, mode, k, cap):
    if ea_sha() != _ea_sha:
        raise RuntimeError("EAバイナリが測定中に入れ替わった")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    tag = origin.replace(".", "")
    run_id = f"dl_{months}m_{tag}_mode{mode}_{stamp}_{uuid.uuid4().hex[:4]}"
    p = dict(BOOK)
    p["DlMode"] = mode
    # .set ファイルの datetime は "YYYY.MM.DD HH:MM:SS" 形式。
    # MQL5ソースの D'...' 記法を書くと 1970 と解釈され、即座に期限切れになる
    # （最初の試験実行で 0取引になった原因）。
    p["DlStart"] = f"{origin} 00:00:00"
    p["DlMonths"] = months
    p["DlK"] = k
    p["DlCap"] = cap
    p["DlRefCap"] = DEPOSIT
    p["DlTargetX"] = 2.0
    p["DlRuinPct"] = 10.0
    p["DlCloseOnEnd"] = True
    p["DlResultFile"] = f"{run_id}_dl.csv"
    p["ResultFileName"] = f"{run_id}_result.csv"
    p["EquityLogFile"] = f"{run_id}_deals.csv"
    # 期限より少し後ろまで走らせる（到達/破綻/期限切れはEA側が判定して停止する）
    to = add_months(origin, months)
    lines = [f"mt5_path: {EXE}", "expert: MIX_EA_X2HR", "symbol: USDJPY",
             "period: M15", f"from_date: {origin}", f"to_date: {to}",
             f"deposit: {DEPOSIT}", "currency: JPY", "leverage: 25",
             "model: every_tick", "parameters:"]
    for kk, vv in p.items():
        lines.append(f"  {kk}: "
                     f"{'true' if vv is True else 'false' if vv is False else vv}")
    lines += [f"report_dir: {RUN_DIR}", f"report_name: {run_id}", ""]
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    cfg = CONFIG_DIR / f"{run_id}.yaml"
    cfg.write_text("\n".join(lines), encoding="utf-8")

    log(f"RUN_START {months}m {origin} mode={mode} k={k} cap={cap}")
    t0 = time.time()
    status = "OK"
    try:
        subprocess.run([str(MT5BT), "run", str(cfg), "--no-charts"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=RUN_TIMEOUT, cwd=str(REPO))
    except subprocess.TimeoutExpired:
        kill()
        status = "TIMEOUT"

    row = {"months": months, "origin": origin, "mode": mode, "k": k, "cap": cap,
           "run_id": run_id, "status": status,
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

    dlp = COMMON / f"{run_id}_dl.csv"
    if dlp.exists():
        rr = list(csv.DictReader(open(dlp, encoding="utf-8")))
        if rr:
            row["why"] = rr[0].get("why", "")
            row["end_equity"] = rr[0].get("end_equity", "")
            row["ea_max_dd_pct"] = rr[0].get("max_dd_pct", "")
        dlp.unlink(missing_ok=True)
    else:
        row["why"] = "NO_RESULT"

    src = COMMON / f"{run_id}_deals.csv"
    DEAL_DIR.mkdir(parents=True, exist_ok=True)
    if src.exists():
        try:
            src.replace(DEAL_DIR / f"{run_id}_deals.csv")
            row["deals"] = f"{run_id}_deals.csv"
        except OSError:
            row["deals"] = ""
    kill()

    log(f"RUN_END   {months}m {origin} mode={mode} -> {row.get('why','')} "
        f"net={row.get('net','')} dd={row.get('dd_pct','')} "
        f"({row['secs']}s)")
    return row


def main():
    global _ea_sha
    if not EA_EX5.exists():
        print(f"EAが見つかりません: {EA_EX5}")
        sys.exit(1)
    _ea_sha = ea_sha()
    log(f"START ea_sha={_ea_sha[:12]} deposit={DEPOSIT}")

    cols = ["months", "origin", "mode", "k", "cap", "why", "end_equity",
            "net", "dd_pct", "ea_max_dd_pct", "trades", "pf",
            "status", "secs", "run_id", "deals"]
    rows = []
    for months, origins, k, cap in PLAN:
        for origin in origins:
            for mode in (1, 2):
                rows.append(run_one(months, origin, mode, k, cap))
                OUT.parent.mkdir(parents=True, exist_ok=True)
                with open(OUT, "w", encoding="utf-8", newline="") as fh:
                    w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
                    w.writeheader()
                    w.writerows(rows)
    log(f"DONE {len(rows)} runs -> {OUT}")


if __name__ == "__main__":
    main()

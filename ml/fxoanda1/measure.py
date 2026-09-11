"""FX推奨設定を OANDA フィードで測り直す（本番投入可否の最終関門）。

【なぜ必要か】ラウンド9〜14の測定はすべて XM端末・XM銘柄で行った。本番は OANDA で、
フィードもスプレッドも違う。特に SCA はM15のレンジブレイクなのでスプレッド差が
そのまま成績に効く。XMで出た OOS 3.02%/月 が OANDA でどこまで残るかが投入可否を決める。

【端末が使えるようになった経緯】OANDA端末は長く「LiveUpdateで起動不能」と記録して
いたが、実際は `Terminal exit with code 0` が更新適用のための正常な再起動であり、
元のPIDだけを見て落ちたと誤判定していた。3台が 6180/6182 に更新済みで、
起動・接続・67銘柄の同期を確認した。

【EAの同一性】OANDA端末に配備した .ex5 は XM側と同一SHA（98d735cabbc58164）。
ビルドも XM 6182 / OANDA BT1 6182 で揃っている。したがって差はフィードのみ。

【比較する設定】fxrisk1 の結果から、現行と上位3案。
  R001  現行（RefCap=78000 / 倍率1 / 固定ロット）
  R031  5枠risk%化・固定基準25万・倍率3   OOS 1.88%/月・最大DD 25.9%
  R035  5枠risk%化・複利・risk 0.25%      OOS 2.47%/月・最大DD 40.0%
  R037  5枠risk%化・複利・risk 0.5%       OOS 3.02%/月・最大DD 41.8%

【履歴の制約】OANDA の履歴が OOS窓（2016.11〜2021.06）まで遡れるかは未確認。
遡れなければ run が "no history data" で落ちるので、その事実自体が結果になる。
"""
from __future__ import annotations

import csv
import json
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROOT = Path(__file__).resolve().parent
RUN_DIR = ROOT / "runs"
CONFIG_DIR = ROOT / "configs"
DEAL_DIR = ROOT / "run_deals"
OUT = ROOT / "results.csv"
LOG = ROOT / "measure.log"
MT5BT = REPO / "mt5bt.bat"
COMMON = Path(r"C:\Users\f\AppData\Roaming\MetaQuotes\Terminal\Common\Files")

# OANDA BT1（build 6182・XMと同ビルド）
EXE = r"C:\Program Files\OANDA MetaTrader 5_BT1\terminal64.exe"
EA_EX5 = Path(r"C:\Users\f\AppData\Roaming\MetaQuotes\Terminal"
              r"\6142D304BFF2E6AB353977162D6F452C\MQL5\Experts\MIX_EA_SIMVERIFY.ex5")

DEPOSIT = 500000
RUN_TIMEOUT = 5400

WINDOWS = {
    "FULL": ("2016.11.09", "2026.06.20", 115.0),
    "OOS":  ("2016.11.09", "2021.06.20", 55.0),
    # ユーザー指示（2026-09-11）により IS も必ず併記する。
    "IS":   ("2021.06.21", "2026.06.20", 60.0),
}

SRC = REPO / "ml" / "fxrisk1" / "proposals.csv"
TARGETS = ["R001", "R031", "R035", "R037"]

MAGICS = {
    20260622: "pb_uj", 20260627: "pb_gj", 20260610: "rsi_uj",
    20260605: "rsi_eu", 20260774: "rsi_gu", 20260629: "pair",
    20260650: "carry", 20261000: "sca_uj", 20261001: "sca_gj",
}

FIELDS = (["proposal_id", "window", "status", "net", "pf", "dd_pct", "trades",
           "deals", "elapsed", "run_id", "description", "parameter_json"]
          + [f"{k}_{s}" for k in MAGICS.values() for s in ("net", "n")])

_ea_sha = None


def ea_sha() -> str:
    import hashlib
    return hashlib.sha256(EA_EX5.read_bytes()).hexdigest()


def log(msg):
    line = f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def kill():
    folder = str(Path(EXE).parent).replace("'", "''")
    ps = ("Get-Process terminal64,metatester64 -ErrorAction SilentlyContinue | "
          f"Where-Object {{ $_.Path -like '{folder}\\*' }} | "
          "Stop-Process -Force -ErrorAction SilentlyContinue")
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                   timeout=120, capture_output=True)


def load_done():
    done = set()
    if OUT.exists():
        for r in csv.DictReader(open(OUT, encoding="utf-8")):
            if r.get("status") == "OK":
                done.add((r["proposal_id"], r["window"]))
    return done


def append_result(row):
    exists = OUT.exists()
    with open(OUT, "a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        if not exists:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in FIELDS})
        fh.flush()


def run(prop, window):
    if ea_sha() != _ea_sha:
        raise RuntimeError("EAバイナリが測定中に入れ替わった")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    run_id = f"oa_{window.lower()}_{prop['proposal_id']}_{stamp}_{uuid.uuid4().hex[:4]}"
    p = json.loads(prop["parameter_json"])
    p["ResultFileName"] = f"{run_id}_result.csv"
    p["EquityLogFile"] = f"{run_id}_deals.csv"
    frm, to, months = WINDOWS[window]
    lines = [f"mt5_path: {EXE}", "expert: MIX_EA_SIMVERIFY", "symbol: USDJPY",
             "period: M15", f"from_date: {frm}", f"to_date: {to}",
             f"deposit: {DEPOSIT}", "currency: JPY", "leverage: 25",
             "model: every_tick", "parameters:"]
    for k, v in p.items():
        lines.append(f"  {k}: {'true' if v is True else 'false' if v is False else v}")
    lines += [f"report_dir: {RUN_DIR}", f"report_name: {run_id}", ""]
    cfg = CONFIG_DIR / f"{run_id}.yaml"
    cfg.write_text("\n".join(lines), encoding="utf-8")

    log(f"RUN_START {prop['proposal_id']} {window}")
    t0 = time.time()
    try:
        subprocess.run([str(MT5BT), "run", str(cfg), "--no-charts"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=RUN_TIMEOUT, cwd=str(REPO))
    except subprocess.TimeoutExpired:
        kill()
        return {"proposal_id": prop["proposal_id"], "window": window,
                "status": "FAILED", "description": prop["description"]}

    sp = RUN_DIR / run_id / "summary.csv"
    v = None
    if sp.exists():
        d = {r[0]: r[1] for r in csv.reader(open(sp, encoding="utf-8")) if len(r) >= 2}
        try:
            v = {"net": float(d["純利益"]), "pf": float(d["プロフィットファクター"]),
                 "dd_pct": float(d["最大相対DD%"]), "trades": int(float(d["総取引数"]))}
        except (KeyError, ValueError):
            v = None

    src = COMMON / f"{run_id}_deals.csv"
    dst = DEAL_DIR / f"{run_id}_deals.csv"
    if src.exists():
        try:
            src.replace(dst)
        except OSError:
            dst = src
    st = {}
    if dst.exists():
        for r in csv.DictReader(open(dst, encoding="utf-8")):
            k = MAGICS.get(int(r["magic"]))
            if k is None:
                continue
            a = st.setdefault(k, {"net": 0.0, "n": 0})
            if r["entry"] == "0":
                a["n"] += 1
            else:
                a["net"] += float(r["profit"])   # profit_jpy はJPY建てでは使えない
    kill()

    row = {"proposal_id": prop["proposal_id"], "window": window, "run_id": run_id,
           "deals": dst.name if dst.exists() else "",
           "description": prop["description"], "parameter_json": prop["parameter_json"],
           "status": "OK" if v else "FAILED", "elapsed": round(time.time() - t0, 1)}
    if v:
        row.update(v)
    for k in MAGICS.values():
        row[f"{k}_net"] = round(st[k]["net"]) if k in st else ""
        row[f"{k}_n"] = st[k]["n"] if k in st else ""
    log(f"RUN_END {prop['proposal_id']} {window} net={row.get('net')} "
        f"trades={row.get('trades')} {row['elapsed']}s")
    return row


def main():
    global _ea_sha
    for d in (RUN_DIR, CONFIG_DIR, DEAL_DIR):
        d.mkdir(parents=True, exist_ok=True)
    _ea_sha = ea_sha()
    log(f"OANDA_START EA_SHA {_ea_sha[:16]} exe={EXE}")

    props = {r["proposal_id"]: r for r in
             csv.DictReader(open(SRC, encoding="utf-8"))}
    done = load_done()
    jobs = [(props[pid], w) for w in WINDOWS for pid in TARGETS
            if (pid, w) not in done]
    log(f"jobs={len(jobs)} done={len(done)}")

    import ctypes
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    try:
        for prop, window in jobs:
            append_result(run(prop, window))
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
    log("OANDA_END")


if __name__ == "__main__":
    main()

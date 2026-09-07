"""OANDA FX 9枠の重み再配分をIS/OOSで測る、直列・再開可能な掃引。ロット丸めのため実測点だけを扱う。端末と測定ガードはfxmult1を継承する。"""
from __future__ import annotations

import csv
import os
from generate_proposals import load_proposals, parameters
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
EXE = r"C:\Users\f\AppData\Roaming\XMTrading MT5\terminal64.exe"

DEPOSIT = 500000
RUN_TIMEOUT = 3600

WINDOWS = {
    "IS":   ("2021.06.21", "2026.06.20", 60.0),
    "OOS":  ("2016.11.09", "2021.06.20", 55.0),

}

# OANDA FX口座の9枠（MIX_EA_OANDA.mq5 の既定ON。GOLD系はCFD口座、暗号は取扱なし）
BASE = {
    "En_PB_USDJPY": True, "En_PB_GBPJPY": True, "En_PB_AUDJPY": False,
    "En_PB_GOLD": False, "En_RSI_USDJPY": True, "En_RSI_EURUSD": True,
    "En_RSI_GBPUSD": True, "En_PAIR": True, "En_CARRY": True, "En_VBO": False,
    "En_ETH": False, "En_BTC_FUND": False, "En_BFXREV": False,
    "En_SCA_GOLD": False, "En_SCA_USDJPY": True, "En_SCA_GBPJPY": True,
    "SimVerifyMode": 0, "R6GoldMode": 0, "R6CryptoMode": 0,
    "GoldDDMode": 0, "GoldLabMode": 0, "GoldLabMode2": 0,
    "GoldPBHoldBars": 64, "GoldHourGateMode": 1,
    "GoldHourPBWeekMask1": 2, "GoldHourPBStart1": 0, "GoldHourPBEnd1": 7,
    "GoldHourPBWeekMask2": 32, "GoldHourPBStart2": 12, "GoldHourPBEnd2": 16,
    "GszMode": 0, "GszSleeveMask": 0,
    "Sca2Enable": False, "Sca3Enable": False, "Sca4Enable": False,
    "Sca5Enable": False, "Sca6Enable": False, "Pb2Enable": False,
    "FundUseWebRequest": False, "BfxUseWebRequest": False,
    # 【必須】検証EAの既定は 0（＝口座equity基準で複利が効く）だが、本番の
    # MIX_EA_OANDA.mq5 は 78000（＝固定配分で非複利）。指定しないと本番と別物を測る。
    # 最初これを落とし、x1のISが9.3%/月・x4が16倍・x8が24取引で口座破綻という
    # 明らかに異常な結果になった（線形性検証で検出）。
    "RefCap_PB_USDJPY": 78000, "RefCap_PB_GBPJPY": 78000, "RefCap_CARRY": 78000,
}

MAGICS = {
    20260622: "pb_uj", 20260627: "pb_gj", 20260610: "rsi_uj",
    20260605: "rsi_eu", 20260774: "rsi_gu", 20260629: "pair",
    20260650: "carry", 20261000: "sca_uj", 20261001: "sca_gj",
}

EA_EX5 = Path(r"C:\Users\f\AppData\Roaming\MetaQuotes\Terminal"
              r"\BAC624F09E3C5D5AFDD21CE91C0B879D\MQL5\Experts\MIX_EA_SIMVERIFY.ex5")
_ea_sha = None


def ea_sha() -> str:
    import hashlib
    return hashlib.sha256(EA_EX5.read_bytes()).hexdigest()


def log(msg):
    line = f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8", newline="") as fh:
        fh.write(line + "\n")


def kill():
    folder = str(Path(EXE).parent).replace("'", "''")
    ps = ("Get-Process terminal64,metatester64 -ErrorAction SilentlyContinue | "
          f"Where-Object {{ $_.Path -like '{folder}\\*' }} | "
          "Stop-Process -Force -ErrorAction SilentlyContinue")
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                   timeout=120, capture_output=True)


def run(prop, window):
    mult = parameters(prop["parameter_json"])["GlobalLotMult"]
    if ea_sha() != _ea_sha:
        raise RuntimeError("EAバイナリが測定中に入れ替わった")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    run_id = f"fw_{window.lower()}_{prop['proposal_id']}_{stamp}_{uuid.uuid4().hex[:4]}"
    p = dict(BASE)
    p.update(parameters(prop["parameter_json"]))
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
    cfg.write_bytes("\n".join(lines).encode("utf-8"))

    log(f"RUN_START x{mult} {window}")
    t0 = time.time()
    try:
        subprocess.run([str(MT5BT), "run", str(cfg), "--no-charts"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=RUN_TIMEOUT, cwd=str(REPO))
    except subprocess.TimeoutExpired:
        kill()
        return {**prop, "mult": mult, "window": window, "run_id": run_id, "status": "FAILED"}

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

    # 枠別も残す。倍率余力が特定の枠のDDに縛られていないかを後で見るため。
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

    row = {**prop, "mult": mult, "window": window, "run_id": run_id,
           "deals": str(dst) if dst.exists() else "",
           "status": "OK" if v else "FAILED", "elapsed": round(time.time() - t0, 1)}
    if v:
        row.update(v)
        row["monthly_pct"] = round(100 * v["net"] / DEPOSIT / months, 4)
    for k in MAGICS.values():
        row[f"{k}_net"] = round(st[k]["net"]) if k in st else ""
        row[f"{k}_n"] = st[k]["n"] if k in st else ""
    log(f"RUN_END x{mult} {window} net={row.get('net')} dd%={row.get('dd_pct')} "
        f"trades={row.get('trades')} {row['elapsed']}s")
    return row


FIELDS = (["proposal_id", "family", "description", "parameter_json",
           "mult", "window", "status", "net", "pf", "dd_pct", "monthly_pct",
           "trades", "deals", "elapsed", "run_id"]
          + [f"{k}_{s}" for k in MAGICS.values() for s in ("net", "n")])


def append_result(row):
    exists = OUT.exists() and OUT.stat().st_size > 0
    with open(OUT, "a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        if not exists:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in FIELDS})
        # 強制終了後にも完了済みrunを再利用できるよう、毎回ディスクまで保存する。
        fh.flush()
        os.fsync(fh.fileno())


def load_done(props):
    done = set()
    expected = {p["proposal_id"]: parameters(p["parameter_json"]) for p in props}
    if OUT.exists() and OUT.stat().st_size:
        with open(OUT, encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames != FIELDS:
                raise ValueError("results.csvのヘッダーが一致しません")
            for r in reader:
                if r.get("proposal_id") in expected:
                    if parameters(r["parameter_json"]) != expected[r["proposal_id"]]:
                        raise ValueError("既存結果と案のパラメータが異なります")
                    path = Path(r.get("deals") or "__missing__")
                    if not path.is_absolute():
                        path = DEAL_DIR / path
                    if r.get("status") == "OK" and path.is_file():
                        done.add((r["proposal_id"], r["window"]))
    return done


def main():
    global _ea_sha
    props = load_proposals()
    done = load_done(props)
    jobs = [(p, w) for w in WINDOWS for p in props if (p["proposal_id"], w) not in done]
    if not jobs:
        print("全案・両窓が完了済みです")
        return
    for d in (RUN_DIR, CONFIG_DIR, DEAL_DIR):
        d.mkdir(parents=True, exist_ok=True)
    _ea_sha = ea_sha()
    log(f"EA_SHA {_ea_sha[:16]}")
    import ctypes
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    try:
        log(f"FXWEIGHT_START jobs={len(jobs)} done={len(done)}")
        for prop, window in jobs:
            append_result(run(prop, window))
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
    log(f"FXWEIGHT_END -> {OUT}")


if __name__ == "__main__":
    main()

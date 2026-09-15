"""段階3 — A10「証拠金維持率でロットを制限する」を MT5 バックテストで確認する。

【位置づけ】
`docs/oanda_fx_margin_cap_20260915.md` は dealログからの再構成（段階2）で
**T036 ＋ cap80% が OOS 5.01%/月**（純益 7,229,106円・最大DD 56.1%・元本割れなし）
という結果を得たが、`CLAUDE.md` の絶対のルールにより
**採用の最終判断は MT5 バックテストで行う**ことになっている。本ラボがその段階3である。

段階2でいちばん疑わしいのは「**cap を掛けたほうが純益が12%増える**」という結果そのもの
（同doc §5）。比例近似の外挿であり、別の経路で同じ符号になる保証はない。

【EAバイナリが入れ替わることへの対処 — U000 を必ず最初に回す】
本ラウンドのために `MIX_EA_SIMVERIFY.mq5` を再コンパイルする。追加した入力は
`MarginCapPct`（既定0）と `ScaFil*`（既定OFF）で、**どちらも既定値では旧挙動と同一**の
はずだが、「はず」で済ませると fxrisk3 の既存結果と本ラウンドを並べられない。

そこで **U000 = T043 ＋ MarginCapPct=0** を最初に回し、
fxrisk3 の T043 の純益・DD・取引数を**厳密に再現すること**を確認する。
再現しなければ以降の結果は fxrisk3 と比較できないので、そこで止める。

  fxrisk3 T043 実測: FULL 純益 17,072,185 / DD 40.0584% / 2969取引
                     OOS  純益  1,213,378 / DD 29.5%    / 1375取引

【測定順】OOS を先に回す。OOSが判断窓であり、FULL（10分）より短い（4分）ため、
途中で中断しても判断に効く数字から埋まる。
"""
from __future__ import annotations

import csv
import importlib.util
import json
import math
import os
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
EA_EX5 = Path(r"C:\Users\f\AppData\Roaming\MetaQuotes\Terminal"
              r"\BAC624F09E3C5D5AFDD21CE91C0B879D\MQL5\Experts\MIX_EA_SIMVERIFY.ex5")

DEPOSIT = 500000
RUN_TIMEOUT = 5400

WINDOWS = {
    "OOS":  ("2016.11.09", "2021.06.20", 55.0),
    "FULL": ("2016.11.09", "2026.06.20", 115.0),
}

MAGICS = {
    20260622: "pb_uj", 20260627: "pb_gj", 20260610: "rsi_uj",
    20260605: "rsi_eu", 20260774: "rsi_gu", 20260629: "pair",
    20260650: "carry", 20261000: "sca_uj", 20261001: "sca_gj",
}

# fxrisk3 と同一の BASE を使う。手写しの差で結果が比較不能になるのを防ぐため、
# fxrisk3/measure.py から直接読み込んで一致を強制する。
_spec = importlib.util.spec_from_file_location(
    "_fxrisk3_measure", REPO / "ml" / "fxrisk3" / "measure.py")
_fx3 = importlib.util.module_from_spec(_spec)
import sys as _sys
_sys.path.insert(0, str(REPO / "ml" / "fxrisk3"))
_spec.loader.exec_module(_fx3)
BASE = dict(_fx3.BASE)
assert _fx3.WINDOWS["OOS"] == WINDOWS["OOS"], "OOS窓が fxrisk3 と違う"
assert _fx3.WINDOWS["FULL"] == WINDOWS["FULL"], "FULL窓が fxrisk3 と違う"
assert _fx3.DEPOSIT == DEPOSIT and _fx3.MAGICS == MAGICS

# --- 段階3で回す構成 -------------------------------------------------------
# risk% 3枠（mask=7＝RSI×3）と 5枠（mask=23＝RSI×3＋SCA_GJ）の2系統に cap を掛ける。
# MarginCapPct 以外は fxrisk3 の対応案と1文字も変えない（parameter_json をそのまま使う）。


def cfg(mask, pct, mult, cap, sca_gj=1.0, **weights):
    p = {"FxRiskMask": mask, "FxRiskPct": pct, "FxRiskRefCap": 0,
         "GlobalLotMult": mult, "RefCap_CARRY": 0, "RefCap_PB_GBPJPY": 0,
         "RefCap_PB_USDJPY": 0, "MarginCapPct": cap}
    for k in ("BFXREV", "BTC_FUND", "CARRY", "ETH", "PAIR", "PB_GBPJPY", "PB_GOLD",
              "PB_USDJPY", "RSI_EURUSD", "RSI_GBPUSD", "RSI_USDJPY", "SCA_GBPJPY",
              "SCA_GOLD", "SCA_USDJPY", "VBO"):
        p[f"Mult_{k}"] = 1.0
    p["Mult_SCA_GBPJPY"] = sca_gj
    for k, v in weights.items():                     # 枠別の重み（A3/A7）
        key = f"Mult_{k}"
        if key not in p:
            raise KeyError(f"未知の枠: {key}")
        p[key] = v
    return p


PROPOSALS = [
    # id,     base,   説明,                                              params
    ("U000", "T043", "対照: T043 ＋ cap無効。再コンパイルEAが旧挙動と一致することの証明",
     cfg(23, 1.0, 1, 0, 0.15)),
    ("U001", "T036", "本命: T036（mask=7/risk1%/倍率3）＋ cap80%。段階2で OOS 5.01%/月",
     cfg(7, 1.0, 3, 80)),
    ("U002", "T036", "T036 ＋ cap85%（台地の上端）", cfg(7, 1.0, 3, 85)),
    ("U003", "T036", "T036 ＋ cap75%（台地の下端・段階2のOOS最良 5.13%）", cfg(7, 1.0, 3, 75)),
    ("U006", "T043", "合成: mask=23 / 倍率3 / SCA_GJ重み0.15 ＋ cap80%（未測定）",
     cfg(23, 1.0, 3, 80, 0.15)),
    ("U007", "T043", "U006 から cap を外したもの。cap の効果だけを分離する",
     cfg(23, 1.0, 3, 0, 0.15)),
    ("U008", "T035", "T035（倍率2）＋ cap80%。倍率3が本当に要るのか", cfg(7, 1.0, 2, 80)),
    ("U004", "T034", "対照: T034 ＋ cap80%。段階2では 7/1375 しか削られない＝ほぼ無影響のはず",
     cfg(7, 1.0, 1, 80)),
    ("U005", "T043", "対照: T043 ＋ cap80%。段階2では 10/1375＝ほぼ無影響のはず",
     cfg(23, 1.0, 1, 80, 0.15)),

    # --- 枠別の重み（A3/A7・Codex #7）— ml/fxmargin3/weights.py の座標降下 ------
    # 重みは IS(60か月)だけで決め、OOS では評価しかしていない。
    # 55か月まとめた OOS では 4.67% -> 7.90%（IS最適）/ 7.67%（保守版）。
    #
    # **ただし OOS を窓に切ると評価が分かれる**（weights_windows.py）。
    # OOSに収まる24か月窓3本の月利中央値は 基準 4.73% / IS最適 3.45% / 保守版 6.16%。
    # **IS最適重みは基準を下回る＝過学習の疑いが濃い。保守版だけが持ちこたえている。**
    # したがって **U011（保守版）を先に回す。**
    ("U011", "T036", "本命（重み）: 固定・小口枠を一律4倍まで。"
                     "PB_UJ 0.5 / RSI_UJ 2 / RSI_EU 4 / RSI_GU 4 / Pair 4 / "
                     "Carry 0.75 / SCA×2 4 ＋ cap80%",
     cfg(7, 1.0, 3, 80, PB_USDJPY=0.5, RSI_USDJPY=2.0, RSI_EURUSD=4.0,
         RSI_GBPUSD=4.0, PAIR=4.0, CARRY=0.75, SCA_USDJPY=4.0, SCA_GBPJPY=4.0)),
    ("U010", "T036", "対照（過学習の疑い）: IS最適重み。PB_UJ 0.3 / Pair 8 / SCA×2 12 ＋ cap80%。"
                     "OOS窓では基準を下回るので、MT5でも保守版に負けるはず",
     cfg(7, 1.0, 3, 80, PB_USDJPY=0.3, RSI_USDJPY=2.0, RSI_EURUSD=4.0,
         RSI_GBPUSD=4.0, PAIR=8.0, CARRY=0.75, SCA_USDJPY=12.0, SCA_GBPJPY=12.0)),
]

# --- 測定順の差し替え（2026-09-15 15:20 JST・U002 FULL の途中で判断） ------------
# U001（T036 ＋ cap80%）と U002 OOS（cap85%）が、cap を掛けない fxrisk3 の T036 と
# **純益・DD・取引数まで完全に一致した**（net=6,431,197 / dd=85.3875 / trades=1375）。
# テスターのジャーナルにも、この時間帯の [No money] は**1件も無い**
# （当日の22件はすべて 01:29-01:38 UTC＝T030 の run のもの）。
# つまり **cap は発注時に一度も効いていない＝段階2の再構成が約10倍過大だった**。
# 原因は再構成が equity を「決済損益のみ」で作っていたこと。このブックは
# Carry AUDJPY と PB GBPJPY が数か月級の**含み益**を抱えたまま持ち続けるので、
# 実際の equity は再構成値よりはるかに大きい。doc の「実際の維持率はこれより悪い」
# という注意書きは、**符号が逆だった**。
#
# したがって cap 違いの run（U002 FULL / U003 / U004 / U005 / U006 / U008）は
# ほぼ確実に no-op で、先に回す価値が無い。**未知が残っているのは重みの U011 / U010 と、
# 未測定の構成である U007 だけ**なので、そこから回す。
# cap の否定を確定させるための最小限として、台地の下端 U003（cap75%）は残す。
MEASURE_ORDER = ["U011", "U010", "U007", "U003", "U008", "U005", "U004", "U006", "U002"]

# U000 が再現しなければならない fxrisk3 T043 の実測値（results.csv より）。
U000_EXPECT = {"FULL": {"net": 17072185.0, "trades": 2969, "dd_pct": 40.0584},
               "OOS":  {"net": 1213378.0,  "trades": 1375, "dd_pct": 29.4954}}

FIELDS = (["proposal_id", "base", "description", "parameter_json", "cap", "window",
           "status", "net", "pf", "dd_pct", "monthly_pct", "trades", "final_balance",
           "balance_source", "deals", "elapsed", "run_id"]
          + [f"{k}_{s}" for k in MAGICS.values() for s in ("net", "n")])


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


def final_balance(summary, deal_profit):
    for key in ("最終残高", "残高", "Final Balance", "Balance", "final_balance", "balance"):
        try:
            value = float(str(summary[key]).replace(",", "").replace(" ", ""))
        except (KeyError, ValueError):
            continue
        if math.isfinite(value):
            return value, f"summary:{key}"
    if deal_profit is not None:
        return round(DEPOSIT + deal_profit, 2), "deposit_plus_deal_profit"
    return "", "unavailable"


def run(pid, base, desc, params, window):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    run_id = f"mc_{window.lower()}_{pid}_{stamp}_{uuid.uuid4().hex[:4]}"
    p = dict(BASE)
    p.update(params)
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
    cfg_path = CONFIG_DIR / f"{run_id}.yaml"
    cfg_path.write_bytes("\n".join(lines).encode("utf-8"))

    log(f"RUN_START {pid} {window} cap={params['MarginCapPct']}")
    t0 = time.time()
    try:
        subprocess.run([str(MT5BT), "run", str(cfg_path), "--no-charts"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=RUN_TIMEOUT, cwd=str(REPO))
    except subprocess.TimeoutExpired:
        kill()
        return {"proposal_id": pid, "base": base, "description": desc,
                "parameter_json": json.dumps(params, sort_keys=True),
                "cap": params["MarginCapPct"], "window": window,
                "run_id": run_id, "status": "FAILED"}

    sp = RUN_DIR / run_id / "summary.csv"
    v, d = None, {}
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

    st, deal_profit = {}, 0.0
    if dst.exists():
        for r in csv.DictReader(open(dst, encoding="utf-8")):
            deal_profit += float(r["profit"])
            k = MAGICS.get(int(r["magic"]))
            if k is None:
                continue
            a = st.setdefault(k, {"net": 0.0, "n": 0})
            if r["entry"] == "0":
                a["n"] += 1
            else:
                a["net"] += float(r["profit"])
    kill()

    row = {"proposal_id": pid, "base": base, "description": desc,
           "parameter_json": json.dumps(params, sort_keys=True),
           "cap": params["MarginCapPct"], "window": window, "run_id": run_id,
           "deals": str(dst) if dst.exists() else "",
           "status": "OK" if v else "FAILED", "elapsed": round(time.time() - t0, 1)}
    row["final_balance"], row["balance_source"] = final_balance(
        d, deal_profit if dst.exists() else None)
    try:
        row["trades"] = int(float(d["総取引数"]))
    except (KeyError, ValueError):
        pass
    if v:
        row.update(v)
        row["monthly_pct"] = round(100 * v["net"] / DEPOSIT / months, 4)
    for k in MAGICS.values():
        row[f"{k}_net"] = round(st[k]["net"]) if k in st else ""
        row[f"{k}_n"] = st[k]["n"] if k in st else ""
    log(f"RUN_END {pid} {window} net={row.get('net')} dd%={row.get('dd_pct')} "
        f"trades={row.get('trades')} {row['elapsed']}s")
    return row


def append_result(row):
    exists = OUT.exists() and OUT.stat().st_size > 0
    with open(OUT, "a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        if not exists:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in FIELDS})
        fh.flush()
        os.fsync(fh.fileno())


def load_done():
    done = set()
    if OUT.exists() and OUT.stat().st_size:
        for r in csv.DictReader(open(OUT, encoding="utf-8")):
            if r.get("status") == "OK":
                done.add((r["proposal_id"], r["window"]))
    return done


def check_u000(row):
    """再コンパイルしたEAが fxrisk3 の T043 を厳密に再現するか。

    再現しなければ、以降の結果は fxrisk3 の既存結果と並べられない。
    その場合は**測定を止める**——比較できない数字を積み上げても判断に使えない。
    """
    exp = U000_EXPECT[row["window"]]
    got = (row.get("net"), row.get("trades"))
    ok = (row.get("status") == "OK"
          and abs(float(row["net"]) - exp["net"]) < 1.0
          and int(row["trades"]) == exp["trades"])
    log(f"U000_CHECK {row['window']} expected net={exp['net']} trades={exp['trades']} "
        f"got net={got[0]} trades={got[1]} -> {'OK' if ok else 'MISMATCH'}")
    if not ok:
        raise RuntimeError(
            f"U000({row['window']})が fxrisk3 の T043 を再現しませんでした。"
            f"期待 net={exp['net']} trades={exp['trades']} / 実測 net={got[0]} trades={got[1]}。"
            "EAの再コンパイルで既定挙動が変わっています。段階3を中止します。")


def acquire_lock():
    """二重起動を防ぐ。

    MT5テスターは1端末しか使えず、driver の kill() は同一インストールの
    **全**テスターを落とす。measure.py が2本走ると互いの走行中runを殺し合い、
    results.csv には中断された run が FAILED として積まれる。
    ロックが取れなければ**黙って降りる**（後から起動したほうが降りる）。
    """
    lock = ROOT / "measure.lock"
    if lock.exists():
        try:
            pid = int(lock.read_text().strip())
        except (ValueError, OSError):
            pid = -1
        if pid > 0:
            out = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                 f"if (Get-Process -Id {pid} -ErrorAction SilentlyContinue) {{'ALIVE'}}"],
                capture_output=True, text=True, timeout=60).stdout
            if "ALIVE" in out:
                log(f"LOCK_BUSY pid={pid} が測定中のため起動しない")
                return False
        log("LOCK_STALE 前回のロックを破棄する")
    lock.write_text(str(os.getpid()), encoding="ascii")
    return True


def main():
    for d in (RUN_DIR, CONFIG_DIR, DEAL_DIR):
        d.mkdir(parents=True, exist_ok=True)
    if not acquire_lock():
        return
    done = load_done()
    order = {pid: i for i, pid in enumerate(MEASURE_ORDER)}
    props = sorted(PROPOSALS, key=lambda t: order.get(t[0], -1))
    jobs = [(pid, base, desc, params, w)
            for (pid, base, desc, params) in props
            for w in ("OOS", "FULL") if (pid, w) not in done]
    if not jobs:
        print("全案・両窓が完了済みです")
        return
    import hashlib
    sha = hashlib.sha256(EA_EX5.read_bytes()).hexdigest()
    log(f"EA_SHA {sha[:16]}  mtime={datetime.fromtimestamp(EA_EX5.stat().st_mtime)}")
    import ctypes
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    try:
        log(f"FXMARGIN3_START jobs={len(jobs)} done={len(done)}")
        for pid, base, desc, params, window in jobs:
            row = run(pid, base, desc, params, window)
            append_result(row)
            if pid == "U000":
                check_u000(row)
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        (ROOT / "measure.lock").unlink(missing_ok=True)
    log(f"FXMARGIN3_END -> {OUT}")


if __name__ == "__main__":
    main()

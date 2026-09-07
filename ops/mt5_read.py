#!/usr/bin/env python3
"""MT5 terminal state reader / post-update guard (A-3, corrected scope).

Correction, 2026-08-02
----------------------
The 2026-08-02 improvements report first blamed this routine's own MT5 Python
read (``initialize(path=...)`` for three terminals in one process) for detaching
MIX_EA from all three terminals at 17:08.  **That attribution was wrong.**  The
terminal journals show the real cause on every terminal::

    17:07:04  LiveUpdate  new version build 6090 ... is available
    17:07:10  LiveUpdate  downloaded successfully
    17:08:10  LiveUpdate  start ...\\liveupdate\\terminal64.exe /update /path:...
    17:08:11  Experts     expert MIX_EA_OANDA (USDJPY,M15) removed
    17:08:15  Terminal    stopped with 0
    17:08:45  Terminal    OANDA MetaTrader 5 x64 build 6090 started

MT5 updated itself (OANDA 5836 -> 6090, XM 6061 -> 6090) and restarted.  The
Python read merely happened to be running at the same minute, because the
watchdog had just relaunched all three terminals at 17:06 after the 54-hour
outage, which made them check for updates immediately.  A follow-up measurement
at 17:39 -- ``initialize(path=...)`` + ``shutdown()`` against a single terminal
-- produced no ``removed`` event at all.

The real failure mode this guards against
-----------------------------------------
**An MT5 LiveUpdate silently restarts the terminal WITHOUT re-attaching the EA.**
Even though the updater is invoked with ``/config:claude_startup_*.ini``, the
terminals came back on build 6090 with no expert loaded and stayed that way
until the watchdog's next 30-minute cycle noticed (17:35:59 -> fully restored
17:37:15).  That is a ~28-minute unprotected window; on a weekday it would be
28 minutes of missed signals.  Auto-updates are not schedulable, so the terminal
state has to be *checked*, not assumed.

What this module does
---------------------
* ``verify_attachment()`` - journal-only, zero side effects: how many EA charts
  each terminal currently has loaded (last-event-wins, so a later ``removed``
  correctly overrides an earlier ``loaded``).
* per-terminal reads in a short-lived **subprocess each** - still the right
  shape for a live rig even though the API turned out not to be the culprit:
  it bounds any future misbehaviour to one terminal.
* reports ``trade_allowed`` and the terminal ``build``, so "EA attached but algo
  trading switched off" and "the build changed under us" are both visible.

This module never calls an order function.  It only reads.

Usage
-----
    python ops/mt5_read.py                     # read all three, print JSON
    python ops/mt5_read.py --from 2026-07-25   # deal history window
    python ops/mt5_read.py --terminal XM
    python ops/mt5_read.py --verify-only       # journal-only attachment check
    python ops/mt5_read.py --recover-if-detached
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

APPDATA = os.environ.get("APPDATA", "")

# name -> (terminal exe, terminal data dir, expected EA name in the journal)
#
# OANDA_CFD is intentionally absent since 2026-08-31: the account balance was moved
# to 0 and the user asked to halt this terminal entirely. mt5.initialize(path=...)
# below launches the terminal at that path if it is not already running, so leaving
# a stopped terminal in this dict would make every no-argument read (e.g. the watchdog's
# S-8 AutoTrading check, which calls this script with no --terminal filter every 30
# minutes) silently relaunch it. Do not re-add without an explicit user request.
TERMINALS = {
    "OANDA_FX": (
        r"C:\Program Files\OANDA MetaTrader 5_SET1\terminal64.exe",
        Path(APPDATA) / "MetaQuotes" / "Terminal" / "1416E208B6517B13F4031221752BCFBD",
        "MIX_EA_OANDA",
    ),
    "XM": (
        r"C:\Program Files\XM Trading MT5\terminal64.exe",
        Path(APPDATA) / "MetaQuotes" / "Terminal" / "C4171FD2B38378D6406D5C84412B5F20",
        "MIX_EA",
    ),
}

WATCHDOG = r"C:\AI\claud\project\forward_test\check_and_recover.ps1"


# --------------------------------------------------------------------------
# EA attachment check (journal based, same last-event-wins rule as watchdog_lib)
# --------------------------------------------------------------------------

def read_journal_lines(data_dir: Path, day: dt.date) -> list[str]:
    """MT5 terminal journals are UTF-16LE, tab separated, logs/<yyyyMMdd>.log."""
    path = data_dir / "logs" / f"{day:%Y%m%d}.log"
    if not path.exists():
        return []
    try:
        return path.read_text(encoding="utf-16", errors="replace").splitlines()
    except (OSError, UnicodeError):
        try:
            return path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return []


def ea_chart_state(data_dir: Path, ea_name: str, days_back: int = 3,
                   now: dt.datetime | None = None) -> dict[str, str]:
    """Last EA event per chart -> 'loaded' or 'removed'.

    Last-event-wins, so a `removed` later in the day correctly overrides an
    earlier `loaded`.  Scanning several days back is the S-3 fix: just after
    midnight today's journal may not exist yet on a perfectly healthy terminal.
    """
    now = now or dt.datetime.now()
    state: dict[str, str] = {}
    for back in range(days_back, -1, -1):
        day = (now - dt.timedelta(days=back)).date()
        for line in read_journal_lines(data_dir, day):
            parts = line.split("\t")
            if len(parts) < 5:
                continue
            msg = parts[4]
            if not msg.startswith(f"expert {ea_name} ("):
                continue
            chart = msg[len(f"expert {ea_name} ("):].split(")")[0]
            if msg.endswith("loaded successfully"):
                state[chart] = "loaded"
            elif msg.endswith("removed"):
                state[chart] = "removed"
    return state


def verify_attachment(now: dt.datetime | None = None) -> dict:
    """Report, per terminal, how many EA charts are currently 'loaded'."""
    out = {}
    for name, (_exe, data_dir, ea) in TERMINALS.items():
        state = ea_chart_state(data_dir, ea, now=now)
        loaded = sorted(c for c, v in state.items() if v == "loaded")
        out[name] = {
            "loaded_charts": loaded,
            "count": len(loaded),
            "ok": len(loaded) == 1,
        }
    return out


# --------------------------------------------------------------------------
# The actual read - executed in a CHILD process, one terminal only
# --------------------------------------------------------------------------

_CHILD = r'''
import json, sys, datetime as dt
import MetaTrader5 as mt5

path, frm, to = sys.argv[1], sys.argv[2], sys.argv[3]
out = {"ok": False}
if not mt5.initialize(path=path):
    out["error"] = "initialize failed: %s" % (mt5.last_error(),)
    print(json.dumps(out)); raise SystemExit(0)
try:
    ti = mt5.terminal_info()
    # trade_allowed is the "AutoTrading" toggle. After the 2026-08-02 LiveUpdate the
    # terminals came back with no EA at all; an update that leaves the EA attached but
    # this flag off would trade nothing while looking perfectly healthy in the journal.
    out["terminal"] = {
        "build": ti.build, "connected": ti.connected,
        "trade_allowed": ti.trade_allowed, "path": ti.path,
    }
    ai = mt5.account_info()
    out["account"] = {
        "login": ai.login, "currency": ai.currency, "balance": ai.balance,
        "equity": ai.equity, "credit": ai.credit, "margin": ai.margin,
        "margin_free": ai.margin_free, "margin_level": ai.margin_level,
        "profit": ai.profit,
    }
    out["positions"] = [{
        "ticket": p.ticket, "symbol": p.symbol, "magic": p.magic, "type": p.type,
        "volume": p.volume, "price_open": p.price_open, "sl": p.sl, "tp": p.tp,
        "profit": p.profit, "swap": p.swap,
        "time": dt.datetime.utcfromtimestamp(p.time).isoformat(),
    } for p in (mt5.positions_get() or [])]
    d0 = dt.datetime.strptime(frm, "%Y-%m-%d")
    d1 = dt.datetime.strptime(to, "%Y-%m-%d")
    out["deals"] = [{
        "ticket": d.ticket, "order": d.order, "symbol": d.symbol, "magic": d.magic,
        "entry": d.entry, "type": d.type, "volume": d.volume, "price": d.price,
        "profit": d.profit, "swap": d.swap, "commission": d.commission,
        "time": dt.datetime.utcfromtimestamp(d.time).isoformat(),
    } for d in (mt5.history_deals_get(d0, d1) or [])]
    out["ok"] = True
finally:
    mt5.shutdown()
print(json.dumps(out))
'''


def read_terminal(name: str, frm: str, to: str, timeout: int = 120) -> dict:
    """Read one terminal in its own short-lived process.

    Isolation is the whole point: never let two terminals share a process, which
    is the pattern that tore down all three on 2026-08-02.
    """
    exe = TERMINALS[name][0]
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD, exe, frm, to],
        capture_output=True, text=True, timeout=timeout,
    )
    if proc.returncode != 0:
        return {"ok": False, "error": f"child exited {proc.returncode}: {proc.stderr.strip()[:400]}"}
    line = (proc.stdout or "").strip().splitlines()
    if not line:
        return {"ok": False, "error": "child produced no output"}
    try:
        return json.loads(line[-1])
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"unparsable child output: {exc}"}


def run_watchdog() -> str:
    if not Path(WATCHDOG).exists():
        return f"watchdog script not found: {WATCHDOG}"
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", WATCHDOG],
        capture_output=True, text=True, timeout=900,
    )
    return (proc.stdout or "").strip()[-2000:]


def main() -> int:
    ap = argparse.ArgumentParser(description="Non-destructive MT5 reader (A-3)")
    default_from = (dt.date.today() - dt.timedelta(days=14)).isoformat()
    ap.add_argument("--from", dest="frm", default=default_from)
    ap.add_argument("--to", dest="to",
                    default=(dt.date.today() + dt.timedelta(days=1)).isoformat())
    ap.add_argument("--terminal", choices=sorted(TERMINALS), action="append")
    ap.add_argument("--verify-only", action="store_true",
                    help="only check EA attachment, do not touch the API at all")
    ap.add_argument("--recover-if-detached", action="store_true",
                    help="run the watchdog immediately if an EA came loose")
    args = ap.parse_args()

    result = {"read_at": dt.datetime.now().isoformat(timespec="seconds")}

    before = verify_attachment()
    result["attachment_before"] = before

    if not args.verify_only:
        names = args.terminal or sorted(TERMINALS)
        result["terminals"] = {n: read_terminal(n, args.frm, args.to) for n in names}
        after = verify_attachment()
        result["attachment_after"] = after
        no_algo = [n for n, r in result["terminals"].items()
                   if r.get("ok") and not r.get("terminal", {}).get("trade_allowed", True)]
        if no_algo:
            result["ALGO_DISABLED"] = (
                "AutoTrading is OFF on: " + ", ".join(no_algo)
                + " -- EA is loaded but will not place orders."
            )
        detached = [n for n, v in after.items() if not v["ok"]]
        result["detached_after_read"] = detached
        if detached:
            result["WARNING"] = (
                "EA detached during the read on: " + ", ".join(detached)
                + " -- this is the F-3 failure mode; do not leave it to the 30-min watchdog cycle."
            )
            if args.recover_if_detached:
                result["watchdog_output"] = run_watchdog()
                result["attachment_after_recovery"] = verify_attachment()

    json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")

    if result.get("detached_after_read") and not args.recover_if_detached:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

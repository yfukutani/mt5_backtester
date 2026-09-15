#!/usr/bin/env bash
# fxmargin3 の「まだ分かっていない案」が終わったら、fxmargin3 を止めて fxwin1 を始める。
#
# fxmargin3 に残っているのは
#   U011 / U010 / U007 / U003  … 未知が残る（回す価値がある）
#   U008 / U005 / U004 / U006 / U002FULL … cap 違いだけ＝no-op と分かっている
# なので **U003 FULL が終わった時点で打ち切り**、価値の高い fxwin1（24か月窓の実測）へ移す。
# 打ち切った分は measure.py の resume（results.csv 基準）で後から拾える。
#
# 端末は1台しか使えないので、**必ず fxmargin3 を落としてから** fxwin1 を起動する。
# ロックは fxmargin3 の measure.lock を共有しているため、二重起動にはならない。
set -u

REPO="C:/Users/f/source/repos/mt5_backtester"
PY="C:/Users/f/AppData/Local/Programs/Python/Python314/python.exe"
M3LOG="$REPO/ml/fxmargin3/measure.log"
LOG="$REPO/ml/fxwin1/chain.log"

say() { echo "$(date -u +%FT%TZ) $*" | tee -a "$LOG"; }

LOCKF="$REPO/ml/fxwin1/chain.lock"
if [ -f "$LOCKF" ] && kill -0 "$(cat "$LOCKF" 2>/dev/null)" 2>/dev/null; then
  say "CHAIN_BUSY 既に別のchainが待機中。起動しない"
  exit 0
fi
echo $$ > "$LOCKF"
trap 'rm -f "$LOCKF"' EXIT

say "CHAIN_START fxmargin3 の U003 FULL の完了を待つ"

# 最大3時間待つ（U011FULL+U010x2+U007x2+U003x2 で約1時間の見込み）。
deadline=$(( $(date +%s) + 10800 ))
while [ "$(date +%s)" -lt "$deadline" ]; do
  if grep -q "RUN_END U003 FULL" "$M3LOG" 2>/dev/null; then
    say "U003 FULL の完了を検出"
    break
  fi
  if grep -q "FXMARGIN3_END" "$M3LOG" 2>/dev/null; then
    say "fxmargin3 が自力で完了した"
    break
  fi
  sleep 30
done

if ! grep -qE "RUN_END U003 FULL|FXMARGIN3_END" "$M3LOG" 2>/dev/null; then
  say "CHAIN_ABORT 3時間待っても U003 FULL に到達しなかった"
  exit 1
fi

# fxmargin3 を止める。measure.lock に書かれている pid を落とし、
# 走っているテスターも落としてから解放する。
LOCK="$REPO/ml/fxmargin3/measure.lock"
if [ -f "$LOCK" ]; then
  pid=$(cat "$LOCK" 2>/dev/null)
  say "fxmargin3 (pid=$pid) を停止する"
  powershell -NoProfile -NonInteractive -Command \
    "Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue" || true
fi
powershell -NoProfile -NonInteractive -Command \
  "Get-Process terminal64,metatester64 -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue" || true
sleep 10
rm -f "$LOCK"

say "FXWIN1 を開始する"
cd "$REPO" && "$PY" ml/fxwin1/measure.py >> "$LOG" 2>&1
say "CHAIN_END exit=$?"

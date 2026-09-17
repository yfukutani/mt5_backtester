#!/usr/bin/env bash
# fxlev25 の OOS が全案ぶん終わったら、fxlev25 を止めて fxwin1（24か月窓の実測）へ移す。
#
# fxlev25 は OOS 7本 → FULL 7本 の順。**判断に効くのは OOS のほうで**、
# FULL（115か月・各10分）は口座が数千万〜億に育った領域の数字なので
# 「50万円で月利6%」という問いには答えない。
# 一方 fxwin1 は**毎回50万円から始める24か月窓**で、まさにその問いに答える。
# よって **V003 OOS（OOSの最後）で打ち切り**、fxwin1 を先に回す。
# 打ち切った FULL は measure.py の resume（results.csv 基準）で後から拾える。
#
# 端末は1台しか使えないので、**必ず fxlev25 を落としてから** fxwin1 を起動する。
set -u

REPO="C:/Users/f/source/repos/mt5_backtester"
PY="C:/Users/f/AppData/Local/Programs/Python/Python314/python.exe"
SRCLOG="$REPO/ml/fxlev25/measure.log"
LOG="$REPO/ml/fxwin1/chain.log"

say() { echo "$(date -u +%FT%TZ) $*" | tee -a "$LOG"; }

LOCKF="$REPO/ml/fxwin1/chain.lock"
if [ -f "$LOCKF" ] && kill -0 "$(cat "$LOCKF" 2>/dev/null)" 2>/dev/null; then
  say "CHAIN_BUSY 既に別のchainが待機中。起動しない"
  exit 0
fi
echo $$ > "$LOCKF"
trap 'rm -f "$LOCKF"' EXIT

say "CHAIN_START fxlev25 の V003 OOS の完了を待つ"

deadline=$(( $(date +%s) + 10800 ))
while [ "$(date +%s)" -lt "$deadline" ]; do
  if grep -q "RUN_END V003 OOS" "$SRCLOG" 2>/dev/null; then
    say "V003 OOS の完了を検出"
    break
  fi
  if grep -q "FXLEV25_END" "$SRCLOG" 2>/dev/null; then
    say "fxlev25 が自力で完了した"
    break
  fi
  sleep 30
done

if ! grep -qE "RUN_END V003 OOS|FXLEV25_END" "$SRCLOG" 2>/dev/null; then
  say "CHAIN_ABORT 3時間待っても V003 OOS に到達しなかった"
  exit 1
fi

LOCK="$REPO/ml/fxmargin3/measure.lock"
if [ -f "$LOCK" ]; then
  pid=$(cat "$LOCK" 2>/dev/null)
  say "fxlev25 (pid=$pid) を停止する"
  powershell -NoProfile -NonInteractive -Command \
    "Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue" || true
fi
powershell -NoProfile -NonInteractive -Command \
  "Get-Process terminal64,metatester64 -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue" || true
sleep 10
rm -f "$LOCK"

say "FXWIN1 を開始する（24か月窓・45run・1:25）"
cd "$REPO" && "$PY" ml/fxwin1/measure.py >> "$LOG" 2>&1
say "CHAIN_END exit=$?"

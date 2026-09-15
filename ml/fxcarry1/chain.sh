#!/usr/bin/env bash
# fxinstr1（cap計装）の終了を待って Carry ラウンドを始める。
#
# EA は fxinstr1 の chain が再コンパイルする（CarryExitPeriod / CarryHoldBars も
# そこで一緒に入る。どちらも既定 0 で現行と同一挙動）。**ここでは再コンパイルしない。**
set -u

REPO="C:/Users/f/source/repos/mt5_backtester"
PY="C:/Users/f/AppData/Local/Programs/Python/Python314/python.exe"
LOCK="$REPO/ml/fxmargin3/measure.lock"
LOG="$REPO/ml/fxcarry1/chain.log"

say() { echo "$(date -u +%FT%TZ) $*" | tee -a "$LOG"; }

LOCKF="$REPO/ml/fxcarry1/chain.lock"
if [ -f "$LOCKF" ] && kill -0 "$(cat "$LOCKF" 2>/dev/null)" 2>/dev/null; then
  say "CHAIN_BUSY 既に別のchainが待機中。起動しない"
  exit 0
fi
echo $$ > "$LOCKF"
trap 'rm -f "$LOCKF"' EXIT

lock_alive() {
  [ -f "$LOCK" ] || return 1
  local pid
  pid=$(tr -d '\r\n ' < "$LOCK" 2>/dev/null)
  [ -n "$pid" ] || return 1
  powershell -NoProfile -NonInteractive -Command \
    "if (Get-Process -Id $pid -ErrorAction SilentlyContinue) {'ALIVE'}" 2>/dev/null \
    | grep -q ALIVE
}

say "CHAIN_START fxinstr1 の完了を待つ"

deadline=$(( $(date +%s) + 36000 ))          # 最大10時間
while [ "$(date +%s)" -lt "$deadline" ]; do
  if grep -qE "FXINSTR1_END|FXINSTR1_ABORT" "$REPO/ml/fxinstr1/measure.log" 2>/dev/null; then
    say "fxinstr1 の終了を検出"
    break
  fi
  sleep 60
done

if ! grep -qE "FXINSTR1_END|FXINSTR1_ABORT" "$REPO/ml/fxinstr1/measure.log" 2>/dev/null; then
  say "CHAIN_ABORT 10時間待っても fxinstr1 が終わらなかった"
  exit 1
fi

if grep -q "FXINSTR1_ABORT" "$REPO/ml/fxinstr1/measure.log" 2>/dev/null; then
  say "CHAIN_ABORT fxinstr1 が再現確認で止まっている。EAが変わった可能性があるので進まない"
  exit 1
fi

while lock_alive; do sleep 60; done
sleep 30

say "FXCARRY1 を開始する"
cd "$REPO" && "$PY" ml/fxcarry1/measure.py >> "$LOG" 2>&1
say "CHAIN_END exit=$?"

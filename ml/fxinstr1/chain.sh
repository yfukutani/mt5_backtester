#!/usr/bin/env bash
# fxeff1（証拠金効率16案）の終了を待ち、EA を再コンパイルして cap 計装ラウンドを始める。
#
# 本ラウンドは **EA を差し替える**（Clamp に枠インデックスを渡し、CapLogFile を足す）。
# 走行中に EA バイナリを差し替えると measure.py が
# 「EAバイナリが測定中に入れ替わった」で落ちるので、**必ず待ってから**触る。
#
# fxeff1 の完了は measure.log の FXEFF1_END で判定する。
# ロックが空くだけでは足りない（別のラウンドが割り込むと誤って進む）。
set -u

REPO="C:/Users/f/source/repos/mt5_backtester"
EXPERTS="C:/Users/f/AppData/Roaming/MetaQuotes/Terminal/BAC624F09E3C5D5AFDD21CE91C0B879D/MQL5/Experts"
EXPERTS_WIN='C:\Users\f\AppData\Roaming\MetaQuotes\Terminal\BAC624F09E3C5D5AFDD21CE91C0B879D\MQL5\Experts'
MED="C:/Users/f/AppData/Roaming/XMTrading MT5/MetaEditor64.exe"
PY="C:/Users/f/AppData/Local/Programs/Python/Python314/python.exe"
LOCK="$REPO/ml/fxmargin3/measure.lock"
LOG="$REPO/ml/fxinstr1/chain.log"

say() { echo "$(date -u +%FT%TZ) $*" | tee -a "$LOG"; }

LOCKF="$REPO/ml/fxinstr1/chain.lock"
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

say "CHAIN_START fxeff1 の完了を待つ"

deadline=$(( $(date +%s) + 28800 ))          # 最大8時間（16案×4窓＝約2.5時間の見込み）
while [ "$(date +%s)" -lt "$deadline" ]; do
  if grep -q "FXEFF1_END" "$REPO/ml/fxeff1/measure.log" 2>/dev/null; then
    say "FXEFF1_END を検出"
    break
  fi
  sleep 60
done

if ! grep -q "FXEFF1_END" "$REPO/ml/fxeff1/measure.log" 2>/dev/null; then
  say "CHAIN_ABORT 8時間待っても fxeff1 が終わらなかった"
  exit 1
fi

# 他のラウンドが走っていないことを確かめてから EA を触る。
while lock_alive; do
  say "LOCK_BUSY 別の測定が走っている。空くまで待つ"
  sleep 60
done
sleep 30

say "EA をデプロイして再コンパイルする"
cp "$REPO/experts/MIX_EA_SIMVERIFY.mq5" "$EXPERTS/MIX_EA_SIMVERIFY.mq5" \
  || { say "CHAIN_ABORT copy失敗"; exit 1; }
"$MED" /compile:"$EXPERTS_WIN\\MIX_EA_SIMVERIFY.mq5" /log:"$EXPERTS_WIN\\c_simverify_capinstr.log"
sleep 3
result=$(iconv -f UTF-16LE -t UTF-8 "$EXPERTS/c_simverify_capinstr.log" 2>/dev/null | grep -a "^Result:")
say "COMPILE $result"
case "$result" in
  *"0 errors"*) ;;
  *) say "CHAIN_ABORT コンパイルにエラー"; exit 1 ;;
esac

say "FXINSTR1 を開始する"
cd "$REPO" && "$PY" ml/fxinstr1/measure.py >> "$LOG" 2>&1
say "CHAIN_END exit=$?"

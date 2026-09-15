#!/usr/bin/env bash
# cap の応答曲線（fxcap25）が終わるのを待って、証拠金効率ラウンド（fxeff1）を始める。
#
# 端末は1台しか使えず、driver の kill() が同一インストールの全テスターを落とすため
# 並走できない。EA は再コンパイルしない（本ラウンドは既存の入力しか触らない）ので、
# 待つだけでよい。
set -u

REPO="C:/Users/f/source/repos/mt5_backtester"
PY="C:/Users/f/AppData/Local/Programs/Python/Python314/python.exe"
LOG="$REPO/ml/fxeff1/chain.log"

say() { echo "$(date -u +%FT%TZ) $*" | tee -a "$LOG"; }

LOCKF="$REPO/ml/fxeff1/chain.lock"
if [ -f "$LOCKF" ] && kill -0 "$(cat "$LOCKF" 2>/dev/null)" 2>/dev/null; then
  say "CHAIN_BUSY 既に別のchainが待機中。起動しない"
  exit 0
fi
echo $$ > "$LOCKF"
trap 'rm -f "$LOCKF"' EXIT

say "CHAIN_START fxcap25 の終了を待つ"

# 残り Y095 OOS ＋ Y085 4窓 ＝ 約13分の見込み。余裕をみて2時間待つ。
deadline=$(( $(date +%s) + 7200 ))
while [ "$(date +%s)" -lt "$deadline" ]; do
  if grep -q "FXCAP25_END" "$REPO/ml/fxcap25/measure.log" 2>/dev/null; then
    say "FXCAP25_END を検出"
    break
  fi
  sleep 30
done

if ! grep -q "FXCAP25_END" "$REPO/ml/fxcap25/measure.log" 2>/dev/null; then
  say "CHAIN_ABORT 2時間待っても cap ラウンドが終わらなかった"
  exit 1
fi

# 端末の後始末を待ってから触る。
sleep 30

say "FXEFF1 を開始する"
cd "$REPO" && "$PY" ml/fxeff1/measure.py >> "$LOG" 2>&1
say "CHAIN_END exit=$?"

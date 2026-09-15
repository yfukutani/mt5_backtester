#!/usr/bin/env bash
# fxrisk3 の掃引が終わるのを待ち、EA を再コンパイルして段階3（fxmargin3）を始める。
#
# 掃引中に EA バイナリを差し替えると measure.py が
# 「EAバイナリが測定中に入れ替わった」で落ちる（走行中の案が無効になる）。
# 端末は1台しか使えず、driver の kill() が同一インストールの全テスターを落とすため、
# 並走もできない。よって「待ってから繋ぐ」のがこの環境で取れる唯一の順序である。
set -u

REPO="C:/Users/f/source/repos/mt5_backtester"
EXPERTS="C:/Users/f/AppData/Roaming/MetaQuotes/Terminal/BAC624F09E3C5D5AFDD21CE91C0B879D/MQL5/Experts"
EXPERTS_WIN='C:\Users\f\AppData\Roaming\MetaQuotes\Terminal\BAC624F09E3C5D5AFDD21CE91C0B879D\MQL5\Experts'
MED="C:/Users/f/AppData/Roaming/XMTrading MT5/MetaEditor64.exe"
PY="C:/Users/f/AppData/Local/Programs/Python/Python314/python.exe"
LOG="$REPO/ml/fxmargin3/chain.log"

say() { echo "$(date -u +%FT%TZ) $*" | tee -a "$LOG"; }

# 二重起動を防ぐ。chain が2本走ると MetaEditor が同じ .ex5 を同時に書きに行き、
# その後 measure.py も2本立ち上がって互いのテスターを殺し合う
# （measure.py 側にもロックはあるが、コンパイルの競合はそこでは防げない）。
LOCKF="$REPO/ml/fxmargin3/chain.lock"
if [ -f "$LOCKF" ] && kill -0 "$(cat "$LOCKF" 2>/dev/null)" 2>/dev/null; then
  say "CHAIN_BUSY 既に別のchainが待機中。起動しない"
  exit 0
fi
echo $$ > "$LOCKF"
trap 'rm -f "$LOCKF"' EXIT

say "CHAIN_START 掃引の終了を待つ"

# 最大6時間待つ。残り10案 x 約14分 = 約2.3時間の見込み。
deadline=$(( $(date +%s) + 21600 ))
while [ "$(date +%s)" -lt "$deadline" ]; do
  if grep -q "FXRISK3_END" "$REPO/ml/fxrisk3/measure.log" 2>/dev/null; then
    say "FXRISK3_END を検出"
    break
  fi
  sleep 60
done

if ! grep -q "FXRISK3_END" "$REPO/ml/fxrisk3/measure.log" 2>/dev/null; then
  say "CHAIN_ABORT 6時間待っても掃引が終わらなかった"
  exit 1
fi

# 掃引の後始末（端末の終了）を待ってから触る。
sleep 30

say "EA をデプロイして再コンパイルする"
cp "$REPO/experts/MIX_EA_SIMVERIFY.mq5" "$EXPERTS/MIX_EA_SIMVERIFY.mq5" || { say "CHAIN_ABORT copy失敗"; exit 1; }
"$MED" /compile:"$EXPERTS_WIN\\MIX_EA_SIMVERIFY.mq5" /log:"$EXPERTS_WIN\\c_simverify_margincap.log"
sleep 3
result=$(iconv -f UTF-16LE -t UTF-8 "$EXPERTS/c_simverify_margincap.log" 2>/dev/null | grep -a "^Result:")
say "COMPILE $result"
case "$result" in
  *"0 errors"*) ;;
  *) say "CHAIN_ABORT コンパイルにエラー"; exit 1 ;;
esac

say "FXMARGIN3 を開始する"
cd "$REPO" && "$PY" ml/fxmargin3/measure.py >> "$LOG" 2>&1
say "CHAIN_END exit=$?"

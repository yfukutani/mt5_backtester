#!/usr/bin/env bash
# 共有ロックが空くのを待って、証拠金効率ラウンド（fxeff1）を始める。
#
# 端末は1台しか使えず、driver の kill() が同一インストールの全テスターを落とすため
# 並走できない。EA は再コンパイルしない（本ラウンドは既存の入力しか触らない）。
#
# 【なぜ「特定のラウンドの終了」ではなくロックを見るのか】
# 最初は `FXCAP25_END` を待つ実装にしていたが、cap ラウンドの終了と同時に
# **別のセッションが仕掛けていた fxdep25 が3秒先にロックを取り**、
# こちらは LOCK_BUSY で静かに降りた（measure.py の設計どおり）。
# 「どのラウンドが次に走るか」を chain 側で知ることはできないので、
# **ロックが空くまで待つ**に変える。キューに何本積まれていても順に消化される。
set -u

REPO="C:/Users/f/source/repos/mt5_backtester"
PY="C:/Users/f/AppData/Local/Programs/Python/Python314/python.exe"
LOCK="$REPO/ml/fxmargin3/measure.lock"      # 全ラウンド共通のロック
LOG="$REPO/ml/fxeff1/chain.log"

say() { echo "$(date -u +%FT%TZ) $*" | tee -a "$LOG"; }

LOCKF="$REPO/ml/fxeff1/chain.lock"
if [ -f "$LOCKF" ] && kill -0 "$(cat "$LOCKF" 2>/dev/null)" 2>/dev/null; then
  say "CHAIN_BUSY 既に別のchainが待機中。起動しない"
  exit 0
fi
echo $$ > "$LOCKF"
trap 'rm -f "$LOCKF"' EXIT

# 走っている測定のPIDが生きている間は待つ。
lock_alive() {
  [ -f "$LOCK" ] || return 1
  local pid
  pid=$(tr -d '\r\n ' < "$LOCK" 2>/dev/null)
  [ -n "$pid" ] || return 1
  powershell -NoProfile -NonInteractive -Command \
    "if (Get-Process -Id $pid -ErrorAction SilentlyContinue) {'ALIVE'}" 2>/dev/null \
    | grep -q ALIVE
}

say "CHAIN_START 共有ロックが空くのを待つ"

deadline=$(( $(date +%s) + 21600 ))          # 最大6時間
while [ "$(date +%s)" -lt "$deadline" ]; do
  if ! lock_alive; then
    say "LOCK_FREE 空きを検出"
    break
  fi
  sleep 30
done

if lock_alive; then
  say "CHAIN_ABORT 6時間待ってもロックが空かなかった"
  exit 1
fi

# 端末の後始末を待ってから触る。
sleep 20

# ここでもう一度取られている可能性がある（他の chain との競争）。
# measure.py 側のロックで安全に降りるので、降りたら待ち直す。
for attempt in 1 2 3 4 5 6 7 8 9 10; do
  say "FXEFF1 を開始する（試行 $attempt）"
  cd "$REPO" && "$PY" ml/fxeff1/measure.py >> "$LOG" 2>&1
  if grep -q "FXEFF1_END" "$REPO/ml/fxeff1/measure.log" 2>/dev/null; then
    say "CHAIN_END 完了"
    exit 0
  fi
  if ! tail -1 "$REPO/ml/fxeff1/measure.log" 2>/dev/null | grep -q "LOCK_BUSY"; then
    say "CHAIN_END 測定が終了（未完了の可能性あり）"
    exit 0
  fi
  say "LOCK_BUSY に阻まれた。空くのを待ち直す"
  while lock_alive; do sleep 30; done
  sleep 20
done
say "CHAIN_ABORT 10回試しても開始できなかった"
exit 1

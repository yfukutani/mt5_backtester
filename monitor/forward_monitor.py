# -*- coding: utf-8 -*-
"""
forward_monitor.py — フォワードテスト監視（改善案S-1: EA脱落・端末停止の当日検知）

■ 何を検知するか（各端末ごと）
  1. EA生存: mixlogのハートビート（当日サーバー日付のDAILY行 / 鮮度=最終レコード経過時間）
  2. セッション窓の稼働: サーバー9:30以降なら当日のSCA_RANGE行が所定銘柄分あるか
     （2026.07.06のXM脱落事件はこの判定で当日検知できた）
  3. 端末・口座状態（MetaTrader5パッケージがある場合のみ）:
     接続(connected) / 自動売買許可(trade_allowed) / equity / 保有ポジション数
     ※ mt5.initialize は端末未起動なら起動を試みる＝落ちていた端末の自動復旧も兼ねる。
       ただしEAのチャート復帰までは保証しないため、復旧後は次回実行のmixlogで確認する。

■ 何をしないか
  発注・決済・注文変更などの取引系APIは一切呼ばない（完全読み取り専用）。
  EA本体は無改修（運用ツール＝戦略検証ゲートの対象外）。

■ 出力
  - コンソール: 端末ごとに OK / WARN / ALERT と詳細
  - monitor_log.csv: 実行履歴（追記）
  - ALERT_YYYYMMDD_HHMM.txt: ALERTが1件でもあれば alert_dir に生成
  - 終了コード: 0=全OK / 1=ALERTあり / 2=WARNのみ

■ 使い方
  python forward_monitor.py [config.json]   （省略時: 同ディレクトリの monitor_config.json）
  セットアップとタスクスケジューラ登録は README.md 参照。
"""
import csv
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent
CONFIG_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "monitor_config.json"

OK, WARN, ALERT = "OK", "WARN", "ALERT"
SEV = {OK: 0, WARN: 1, ALERT: 2}


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def server_now(cfg):
    """サーバー時刻の近似（UTC + server_utc_offset時間）。DSTはconfigで管理。"""
    return datetime.now(timezone.utc) + timedelta(hours=cfg.get("server_utc_offset", 3))


def read_mixlog(files_dir, prefix, snow):
    """当月+前月のmixlogを読み、レコード（サーバーepoch）リストを返す"""
    rows = []
    for dt in (snow, snow - timedelta(days=28)):
        p = Path(files_dir) / f"{prefix}_{dt:%Y%m}.csv"
        if not p.exists():
            continue
        try:
            with open(p, encoding="utf-8-sig", errors="replace") as f:
                for r in csv.DictReader(f):
                    try:
                        rows.append({"t": int(r["time"]), "type": r["type"],
                                     "symbol": r.get("symbol", ""), "note": r.get("note", "")})
                    except (ValueError, KeyError):
                        continue
        except OSError:
            continue
    rows.sort(key=lambda x: x["t"])
    return rows


def check_terminal(t, cfg):
    """1端末分のチェック。(status, details:list[str], metrics:dict) を返す"""
    details = []
    status = OK
    snow = server_now(cfg)
    sdate = snow.date()
    wd = snow.weekday()  # 0=Mon .. 6=Sun（サーバー時刻基準）

    def worse(s):
        nonlocal status
        if SEV[s] > SEV[status]:
            status = s

    # ---- 1) mixlogハートビート ----
    files_dir = t["files_dir"]
    rows = read_mixlog(files_dir, t.get("prefix", "mixlog"), snow)
    metrics = {"records": len(rows)}
    if not rows:
        worse(ALERT)
        details.append(f"mixlogが見つからない/空: {files_dir}\\{t.get('prefix')}_{snow:%Y%m}.csv")
    else:
        last = rows[-1]
        last_dt = datetime.fromtimestamp(last["t"], timezone.utc)  # サーバーepochをそのまま比較軸に
        now_srv_naive = snow.replace(tzinfo=timezone.utc)
        age_h = (now_srv_naive - last_dt).total_seconds() / 3600
        metrics["last_record_age_h"] = round(age_h, 1)
        # 鮮度: 平日26h / 月曜は週末を挟むため80h まで許容
        limit = 80 if wd == 0 else 26
        if wd in (5, 6):
            details.append(f"週末のため鮮度チェックをスキップ（最終レコード {age_h:.1f}h前）")
        elif age_h > limit:
            worse(ALERT)
            details.append(f"最終レコードが{age_h:.1f}h前（許容{limit}h）＝EA停止/端末停止の疑い")
        else:
            details.append(f"最終レコード {age_h:.1f}h前 ✓")

        # 当日サーバー日付のDAILY行
        daily_today = [r for r in rows if r["type"] == "DAILY"
                       and datetime.fromtimestamp(r["t"], timezone.utc).date() == sdate]
        if wd < 5:
            if daily_today:
                details.append("当日DAILYハートビート ✓")
            else:
                worse(WARN)
                details.append("当日DAILY行なし（未初回tickの早朝なら正常・日中ならEA脱落疑い）")

        # SCA_RANGE窓チェック（サーバー9:30以降の平日）
        rng_hour = t.get("range_check_hour", 9)
        if wd < 5 and (snow.hour > rng_hour or (snow.hour == rng_hour and snow.minute >= 30)):
            expect = set(t.get("sca_symbols", []))
            got = {r["symbol"] for r in rows if r["type"] == "SCA_RANGE"
                   and datetime.fromtimestamp(r["t"], timezone.utc).date() == sdate}
            missing = expect - got
            if expect and missing:
                worse(ALERT)
                details.append(f"当日SCA_RANGE欠落: {sorted(missing)}（9時窓にEA不在＝取りこぼし進行中の疑い）")
            elif expect:
                details.append(f"当日SCA_RANGE {len(got)}/{len(expect)}銘柄 ✓")

    # ---- 2) MT5 API死活（任意・パッケージがあれば） ----
    if cfg.get("use_mt5_api", True):
        try:
            import MetaTrader5 as mt5
            was_up = _terminal_running(t.get("exe_name", "terminal64.exe"))
            if mt5.initialize(path=t["terminal_path"]):
                ti = mt5.terminal_info()
                ai = mt5.account_info()
                if ti is not None:
                    metrics["connected"] = ti.connected
                    metrics["trade_allowed"] = ti.trade_allowed
                    if not ti.connected:
                        worse(ALERT)
                        details.append("端末がサーバー未接続")
                    if not ti.trade_allowed:
                        worse(ALERT)
                        details.append("自動売買がOFF（アルゴリズム取引ボタン）")
                    if ti.connected and ti.trade_allowed:
                        details.append("接続・自動売買許可 ✓")
                if ai is not None:
                    metrics["equity"] = ai.equity
                    metrics["positions"] = len(mt5.positions_get() or [])
                    details.append(f"equity={ai.equity:,.0f} 保有={metrics['positions']}")
                if not was_up:
                    worse(WARN)
                    details.append("端末が停止していたためinitializeで起動（EAのチャート復帰は次回実行のmixlogで要確認）")
                mt5.shutdown()
            else:
                worse(ALERT)
                details.append(f"mt5.initialize失敗: {mt5.last_error()}")
        except ImportError:
            details.append("MetaTrader5パッケージ無し→mixlogチェックのみ（degraded）")
        except Exception as e:  # APIチェック失敗はWARN止まり（mixlog判定が主）
            worse(WARN)
            details.append(f"MT5 APIチェック例外: {e}")

    return status, details, metrics


def _terminal_running(exe_name):
    try:
        import subprocess
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {exe_name}"],
                             capture_output=True, text=True, timeout=30)
        return exe_name.lower() in out.stdout.lower()
    except Exception:
        return True  # 不明時は起動扱い（誤WARN回避）


def main():
    cfg = load_config()
    snow = server_now(cfg)
    print(f"===== forward_monitor {datetime.now():%Y-%m-%d %H:%M} "
          f"(サーバー時刻近似 {snow:%Y-%m-%d %H:%M}) =====")
    results = []
    for t in cfg["terminals"]:
        status, details, metrics = check_terminal(t, cfg)
        results.append((t["name"], status, details, metrics))
        icon = {"OK": "[OK]   ", "WARN": "[WARN] ", "ALERT": "[ALERT]"}[status]
        print(f"\n{icon} {t['name']}")
        for d in details:
            print(f"    - {d}")

    # ログCSV追記
    log_path = HERE / cfg.get("log_csv", "monitor_log.csv")
    new = not log_path.exists()
    with open(log_path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["run_time", "terminal", "status", "detail"])
        for name, status, details, _ in results:
            w.writerow([datetime.now().isoformat(timespec="seconds"), name, status,
                        " | ".join(details)])

    # ALERTファイル
    worst = max((SEV[s] for _, s, _, _ in results), default=0)
    if worst >= SEV[ALERT]:
        alert_dir = Path(cfg.get("alert_dir", str(HERE)))
        alert_dir.mkdir(parents=True, exist_ok=True)
        ap = alert_dir / f"ALERT_{datetime.now():%Y%m%d_%H%M}.txt"
        with open(ap, "w", encoding="utf-8") as f:
            f.write(f"フォワード監視 ALERT {datetime.now():%Y-%m-%d %H:%M}\n\n")
            for name, status, details, _ in results:
                if status == ALERT:
                    f.write(f"[{status}] {name}\n")
                    for d in details:
                        f.write(f"  - {d}\n")
            f.write("\n対応: 該当端末の起動・EAチャート搭載・自動売買ONを確認し、"
                    "mixlogに当日行が出ることを確認する。\n")
        print(f"\n!! ALERTファイル生成: {ap}")
    print(f"\n結果ログ: {log_path}")
    sys.exit(0 if worst == 0 else (1 if worst >= SEV[ALERT] else 2))


if __name__ == "__main__":
    main()

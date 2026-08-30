from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# 50 independent mechanism families x 20 pre-declared variants = exactly 1,000 ideas.
# The grid values are hypotheses, not post-hoc deal deletion rules; every executable case
# must be run in MT5 with the setting active at decision time.
FAMILIES = [
 ("overlap_mutex","PBとSCAの新規を相互排他にし同時損失を抑える","2枠DDが各単独DDを上回り損失重複がある","同一EAで相手Magic保有中の発注を拒否","(2)軽微なコード変更"),
 ("overlap_priority_pb","競合時にPBを優先","PBとSCAの期待値・保有長が異なる","競合時SCAのみ見送り","(2)軽微なコード変更"),
 ("overlap_priority_sca","競合時にSCAを優先","短期SCAで資金拘束時間を短縮し得る","競合時PBのみ見送り","(2)軽微なコード変更"),
 ("overlap_direction","同方向だけ同時保有禁止","同方向GOLDベータの重複だけ除く","方向別Magic保有判定","(2)軽微なコード変更"),
 ("overlap_opposite","逆方向だけ同時保有禁止","逆方向の往復損を避ける","方向別Magic保有判定","(2)軽微なコード変更"),
 ("pb_atr_sl","PBの初期SLをATR倍率で再設計","2026-03最大DDのPB損失幅を直接制御","ATR SLと連動TPをEA内設定","(2)軽微なコード変更"),
 ("pb_rr","PBの利確RRを変更","損失幅を変えず回復速度を変える","RRをEA内input化","(2)軽微なコード変更"),
 ("pb_adx","PBのADX最低値を変更","弱いトレンドのPBを選別","ADX閾値inputを実バックテスト","(2)軽微なコード変更"),
 ("pb_slope","PBのMA傾き閾値を変更","トレンド質で悪い押し目を除く","傾きATR閾値を実バックテスト","(2)軽微なコード変更"),
 ("pb_ema_pair","PBのEMA組を再設計","急変局面の追随速度を変える","Fast/Slowの組合せ実測","(2)軽微なコード変更"),
 ("pb_trend_ma","PB長期MA期間を変更","GOLDの構造変化への追随性を調整","TrendMA期間実測","(2)軽微なコード変更"),
 ("pb_adx_period","PB ADX期間を変更","短期的なトレンド崩壊検知を調整","ADX period実測","(2)軽微なコード変更"),
 ("pb_candle_body","PB確認足の実体率を要求","ヒゲ主体の偽反発を避ける","実体/レンジ閾値を追加","(2)軽微なコード変更"),
 ("pb_close_location","PB確認足終値位置を要求","反発の質を終値位置で測る","CLV閾値を追加","(2)軽微なコード変更"),
 ("pb_pullback_depth","EMA帯への押し深さを制限","深すぎる崩れ・浅すぎる追随を除く","ATR正規化深さ帯を追加","(2)軽微なコード変更"),
 ("pb_extension_cap","長期MAからの乖離上限","過熱域での遅い参入を抑える","MA乖離/ATR上限を追加","(2)軽微なコード変更"),
 ("pb_higher_tf","D1方向合流を要求","H4と上位トレンド不一致を避ける","D1 MA期間別ゲート","(2)軽微なコード変更"),
 ("pb_hold_limit","PB最大保有H4本数","長期停滞からの尾損失を限定","バー経過で時間退出","(2)軽微なコード変更"),
 ("pb_breakeven","PB建値移動構造","勝ちを損失へ戻す取引を減らす","MFE ATR到達後SL変更","(2)軽微なコード変更"),
 ("pb_trailing","PBトレーリング構造","利益の吐き出しを抑える","ATR追随SLをtick内実装","(2)軽微なコード変更"),
 ("sca_min_range","SCA最小アジアレンジを変更","狭すぎるノイズ日を除く","既存レンジ計算の閾値input","(2)軽微なコード変更"),
 ("sca_max_range","SCA最大アジアレンジを変更","既に動いた日の追随損を除く","最大ATR比input","(2)軽微なコード変更"),
 ("sca_buffer","SCAブレイクbufferを変更","偽ブレイク頻度を制御","ATRd buffer実測","(2)軽微なコード変更"),
 ("sca_rr","SCA RRを変更","勝率と損益比のDD効率を探索","RR input実測","(2)軽微なコード変更"),
 ("sca_boost","SCA reversal boost倍率を変更","0.01整数ロット段階で尾損失を制御","実効lotをログ確認","(2)軽微なコード変更"),
 ("sca_trade_end","SCA新規終了時刻を前倒し","NY前後の質の低い追随を除く","終了時刻input実測","(2)軽微なコード変更"),
 ("sca_force_close","SCA強制決済時刻を変更","保有時間と夕刻反転リスクを制御","決済時刻input実測","(2)軽微なコード変更"),
 ("sca_range_start","SCAレンジ開始時刻を変更","薄商いノイズの混入を調整","開始時刻input実測","(2)軽微なコード変更"),
 ("sca_range_end","SCAレンジ終了時刻を変更","欧州前レンジ定義を調整","終了時刻input実測","(2)軽微なコード変更"),
 ("sca_weekday","SCA曜日を選択","曜日別損失集中を事前ゲート化","曜日maskをEA内判定","(2)軽微なコード変更"),
 ("pb_weekday","PB曜日を選択","週内の流動性・イベント差を利用","曜日maskをEA内判定","(2)軽微なコード変更"),
 ("sca_one_direction","SCA日次方向を片側に限定","両方向往復損を抑える","日次first signal後反対側禁止","(2)軽微なコード変更"),
 ("sca_failed_break","初回偽抜け後その日停止","レンジ往復の損失連鎖を抑える","SL後日次ロック","(2)軽微なコード変更"),
 ("sca_retest","SCAを抜け後リテスト参入へ変更","初動のスリッページと偽抜けを抑える","状態機械で再接触確認","(3)大規模開発"),
 ("portfolio_loss_cooldown","GOLD損失後に両枠を一定バー休止","損失クラスターを切る","決済時点状態をEAで更新","(2)軽微なコード変更"),
 ("sleeve_loss_cooldown","各枠の損失後だけ休止","相互の機会を温存し連敗を抑える","Magic別決済状態","(2)軽微なコード変更"),
 ("daily_loss_cap","GOLD日次確定損失上限","同日損失の積み上がりを抑える","当日HistoryDeal集計後発注停止","(2)軽微なコード変更"),
 ("weekly_loss_cap","GOLD週次確定損失上限","荒れた週の連敗を抑える","週初からの確定損益ゲート","(2)軽微なコード変更"),
 ("equity_overlap_cap","GOLD含み損時に他枠新規を抑制","同時含み損の深掘りを防ぐ","GOLD Magicの含み損率判定","(2)軽微なコード変更"),
 ("vol_regime_atr","ATRレジーム別に挙動変更","固定閾値の期間依存を下げる","過去分位をpoint-in-time算出","(3)大規模開発"),
 ("vol_regime_rvol","実現ボラ分位で選別","急変・低ボラ双方を分離","rolling RV分位をEA内計算","(3)大規模開発"),
 ("trend_regime","ADX×MA傾きレジームで役割分担","PBとORBの得意環境を分ける","2次元regimeゲート","(3)大規模開発"),
 ("range_regime","日足レンジ/ATRで役割分担","日中拡張余地を測る","前日range比ゲート","(2)軽微なコード変更"),
 ("gap_regime","週明けgap時の役割分担","流動性断絶日の尾損失を抑える","金曜終値比gapゲート","(2)軽微なコード変更"),
 ("event_calendar","主要米指標前後の新規・保有を制御","GOLD固有イベントリスクを分離","point-in-timeカレンダー統合","(3)大規模開発"),
 ("spread_gate","スプレッド上限を動的制御","薄商い・ニュース時の約定悪化を避ける","tick spread分位ゲート","(2)軽微なコード変更"),
 ("slippage_guard","許容価格逸脱で発注取消","急変時の悪い約定を減らす","指値/stop-limit状態機械","(3)大規模開発"),
 ("tail_hedge","損失重複時だけ小口逆方向ヘッジ","尾部だけ凸性を持たせる","別Magic・実効0.01以上で実測","(3)大規模開発"),
 ("role_switch","trend時PB/range拡張時SCAへ切替","2枠を独立でなく補完役にする","point-in-time regime selector","(3)大規模開発"),
 ("walkforward_selector","過去窓成績で片枠を選択","環境変化に応じ役割を更新","固定ルールwalk-forwardをEA内再現","(3)大規模開発"),
]


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    rows=[]
    for fi,(family,overview,rationale,test,label) in enumerate(FAMILIES,1):
        for v in range(1,21):
            rows.append({"id":f"GDD{fi:02d}_{v:02d}","family":family,"overview":overview,
                         "rationale":rationale,"test_method":test,"variation":f"family固有水準{v:02d}/20",
                         "classification":label,"status":"UNTESTED"})
    assert len(rows)==1000 and len({r['id'] for r in rows})==1000
    with (ROOT/"proposals.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=rows[0]); w.writeheader(); w.writerows(rows)
    print(f"wrote {len(rows)} proposals across {len(FAMILIES)} families")


if __name__=="__main__": main()

//+------------------------------------------------------------------+
//|  PullbackTrend.mq5                                               |
//|  押し目買い / 戻り売り トレンドフォローEA v1.2                  |
//|  目標プロファイル: 勝率60% / RR1.5                              |
//|  v1.2: MA200傾きによる環境フィルター（強トレンド限定）を追加    |
//+------------------------------------------------------------------+
#property copyright "2026"
#property version   "1.20"
#property strict

#include <Trade\Trade.mqh>

//--- 入力パラメータ
input group "=== トレンド判定 ==="
input int            TrendMA_Period = 200;  // 大局トレンドMA（この上下で方向を限定）
input ENUM_MA_METHOD TrendMA_Method = MODE_SMA;
input int            FastEMA_Period = 20;   // 押し目の基準となる短期EMA
input int            SlowEMA_Period = 50;   // 中期トレンド確認用EMA
// 判定に使う時間足。既定PERIOD_CURRENT＝チャートTF（既存動作と完全一致）。
// 新バー検出/執行はチャートTF（PERIOD_CURRENT）のまま行うため、判定W1・執行D1のように分離できる
// （ブローカーによっては週足の新バー切替タイミングが市場休止時間と重なり market closed になるため）。
input ENUM_TIMEFRAMES SignalTimeframe = PERIOD_CURRENT;

input group "=== 押し目/戻り検出 ==="
input bool   RequireBullishCandle = true;  // エントリー足に陽線/陰線を要求する
input bool   UsePullbackQuality   = true;  // 押し目をSlowEMAを割らない健全な押しに限定（深さフィルター）
input bool   UseMomentumConfirm   = true;  // エントリー足が2本前の高値/安値をブレイクすることを要求

input group "=== トレンド強度フィルター（ADX） ==="
input bool   UseADXFilter  = true;  // ADXによる強トレンドフィルターを使用する
input int    ADX_Period    = 14;
input double ADX_Threshold = 25.0;  // ADXがこの値以上の強トレンドのみエントリー

input group "=== 環境フィルター（MA200傾き） ==="
input bool   UseTrendStrength  = false; // MA200の傾きで強トレンド環境のみに限定する
input int    MA_Slope_Lookback = 20;    // MA200の傾きを測るバー数
input double MA_Slope_Min_ATR  = 0.5;   // この傾き（lookback本でATR×係数）以上で強トレンドと判断

input group "=== マルチタイムフレーム合流フィルター ==="
input bool            UseHigherTFFilter = false;      // 上位足のトレンド方向が一致する場合のみエントリー
input ENUM_TIMEFRAMES HigherTF          = PERIOD_D1;  // 合流を確認する上位足
input int             HigherTF_MA       = 200;        // 上位足の大局トレンドMA期間

input group "=== ストップ（ATRベース） ==="
input bool   UseATRStops    = true;  // ATRベースのSL/TPを使用する
input int    ATR_Period     = 14;
input double ATR_SL_Mult    = 1.5;   // SL距離 = ATR × この倍率
input double RR_Ratio       = 1.5;   // TP距離 = SL距離 × このRR比（目標RR）

input group "=== ストップ（固定pips・UseATRStops=false時） ==="
input int    StopLoss_Pips   = 30;
input int    TakeProfit_Pips = 45;

input group "=== トレード設定 ==="
input double LotSize     = 0.01;
input int    MagicNumber = 20260622;

input group "=== ポジションサイジング（リスクベース） ==="
input bool   UseRiskSizing = false; // ON: 資産のRiskPercent%をSL距離でリスクするロットを動的計算（複利）
input double RiskPercent   = 1.0;   // 1取引あたりのリスク（口座資産に対する%）

input group "=== 出力設定 ==="
input string ResultFileName = "";
input string EquityLogFile  = ""; // 全dealのtime,profitを書き出す（mt5bt portfolioでDD合算）

//--- グローバル変数
CTrade trade;
int    trendma_handle;
int    fastema_handle;
int    slowema_handle;
int    atr_handle;
int    adx_handle;
int    higher_trendma_handle;
double pip_value;

bool armed_buy  = false; // 上昇トレンド中に押し目（FastEMAタッチ）を確認済み
bool armed_sell = false; // 下降トレンド中に戻り（FastEMAタッチ）を確認済み

//+------------------------------------------------------------------+
int OnInit()
{
    pip_value = (_Digits == 3 || _Digits == 5) ? 10 * _Point : _Point;

    trendma_handle = iMA(_Symbol, SignalTimeframe, TrendMA_Period, 0, TrendMA_Method, PRICE_CLOSE);
    fastema_handle = iMA(_Symbol, SignalTimeframe, FastEMA_Period, 0, MODE_EMA, PRICE_CLOSE);
    slowema_handle = iMA(_Symbol, SignalTimeframe, SlowEMA_Period, 0, MODE_EMA, PRICE_CLOSE);
    atr_handle     = iATR(_Symbol, SignalTimeframe, ATR_Period);
    adx_handle     = iADX(_Symbol, SignalTimeframe, ADX_Period);
    higher_trendma_handle = UseHigherTFFilter
        ? iMA(_Symbol, HigherTF, HigherTF_MA, 0, TrendMA_Method, PRICE_CLOSE)
        : INVALID_HANDLE;

    if(trendma_handle == INVALID_HANDLE || fastema_handle == INVALID_HANDLE ||
       slowema_handle == INVALID_HANDLE || atr_handle == INVALID_HANDLE ||
       adx_handle == INVALID_HANDLE ||
       (UseHigherTFFilter && higher_trendma_handle == INVALID_HANDLE))
    {
        Print("インジケーターハンドルの作成に失敗しました");
        return INIT_FAILED;
    }

    trade.SetExpertMagicNumber(MagicNumber);
    trade.SetDeviationInPoints(10);
    Print("PullbackTrend v1.1 起動 | TrendMA=", TrendMA_Period,
          " FastEMA=", FastEMA_Period, " SlowEMA=", SlowEMA_Period,
          " | Quality=", UsePullbackQuality ? "ON" : "OFF",
          " | Momentum=", UseMomentumConfirm ? "ON" : "OFF",
          " | ADX=", UseADXFilter ? StringFormat("ON(>=%.0f)", ADX_Threshold) : "OFF",
          " | Stops=", UseATRStops ? StringFormat("ATR(x%.1f RR%.1f)", ATR_SL_Mult, RR_Ratio)
                                   : StringFormat("Fixed(SL%d TP%d)", StopLoss_Pips, TakeProfit_Pips));
    return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
    IndicatorRelease(trendma_handle);
    IndicatorRelease(fastema_handle);
    IndicatorRelease(slowema_handle);
    IndicatorRelease(atr_handle);
    IndicatorRelease(adx_handle);
    if(higher_trendma_handle != INVALID_HANDLE) IndicatorRelease(higher_trendma_handle);
}

//+------------------------------------------------------------------+
void OnTick()
{
    static datetime last_bar_time = 0;
    datetime current_bar_time = iTime(_Symbol, PERIOD_CURRENT, 0);
    if(current_bar_time == last_bar_time) return;
    last_bar_time = current_bar_time;

    // インジケーター値（前確定足 shift=1）
    double trendma_buf[], fastema_buf[], slowema_buf[], atr_buf[];
    ArraySetAsSeries(trendma_buf, true);
    ArraySetAsSeries(fastema_buf, true);
    ArraySetAsSeries(slowema_buf, true);
    ArraySetAsSeries(atr_buf,     true);

    int trendma_need = UseTrendStrength ? (MA_Slope_Lookback + 2) : 1;
    if(CopyBuffer(trendma_handle, 0, 1, trendma_need, trendma_buf) < trendma_need) return;
    if(CopyBuffer(fastema_handle, 0, 1, 1, fastema_buf) < 1) return;
    if(CopyBuffer(slowema_handle, 0, 1, 1, slowema_buf) < 1) return;
    if(CopyBuffer(atr_handle,     0, 1, 1, atr_buf)     < 1) return;

    double trendma = trendma_buf[0];
    double fastema = fastema_buf[0];
    double slowema = slowema_buf[0];
    double atr     = atr_buf[0];

    // 環境フィルター: MA200の傾き（lookback本での変化量）をATRで正規化
    bool env_up = true, env_down = true;
    if(UseTrendStrength)
    {
        double ma_slope = trendma - trendma_buf[MA_Slope_Lookback];
        double thresh   = MA_Slope_Min_ATR * atr;
        env_up   = (ma_slope >=  thresh);  // MA200が明確に上昇 → 買い許可
        env_down = (ma_slope <= -thresh);  // MA200が明確に下降 → 売り許可
    }

    double close_prev = iClose(_Symbol, SignalTimeframe, 1);
    double open_prev  = iOpen(_Symbol,  SignalTimeframe, 1);
    double high_prev  = iHigh(_Symbol,  SignalTimeframe, 1);
    double low_prev   = iLow(_Symbol,   SignalTimeframe, 1);
    double high_2     = iHigh(_Symbol,  SignalTimeframe, 2);
    double low_2      = iLow(_Symbol,   SignalTimeframe, 2);

    // --- トレンド判定 ---
    bool uptrend   = (close_prev > trendma) && (fastema > slowema);
    bool downtrend = (close_prev < trendma) && (fastema < slowema);

    // トレンドが崩れたらアームを解除
    if(!uptrend)   armed_buy  = false;
    if(!downtrend) armed_sell = false;

    // --- 押し目/戻りアーム判定 ---
    // 改善1: 押し目の質。FastEMAは割るがSlowEMAは割らない健全な押しに限定
    bool quality_buy  = !UsePullbackQuality || (low_prev  >= slowema);
    bool quality_sell = !UsePullbackQuality || (high_prev <= slowema);

    // 上昇トレンド中に安値がFastEMAまで押した → 押し目アーム
    if(uptrend && low_prev <= fastema && quality_buy)
        armed_buy = true;
    // 下降トレンド中に高値がFastEMAまで戻した → 戻りアーム
    if(downtrend && high_prev >= fastema && quality_sell)
        armed_sell = true;

    // --- エントリーシグナル ---
    // アーム後、終値がFastEMA上へ回復（押し目からの反発）でエントリー
    bool bullish = !RequireBullishCandle || (close_prev > open_prev);
    bool bearish = !RequireBullishCandle || (close_prev < open_prev);

    // 改善3: モメンタム確認。エントリー足が2本前の高値/安値をブレイク
    bool momentum_buy  = !UseMomentumConfirm || (close_prev > high_2);
    bool momentum_sell = !UseMomentumConfirm || (close_prev < low_2);

    // 改善2: トレンド強度フィルター（ADX）
    bool adx_ok = true;
    if(UseADXFilter)
    {
        double adx_buf[];
        ArraySetAsSeries(adx_buf, true);
        if(CopyBuffer(adx_handle, 0, 1, 1, adx_buf) < 1) return;
        adx_ok = (adx_buf[0] >= ADX_Threshold);
    }

    // マルチタイムフレーム合流: 上位足のトレンド方向がH4の方向と一致する場合のみ許可
    bool higher_ok_buy = true, higher_ok_sell = true;
    if(UseHigherTFFilter)
    {
        double higher_ma_buf[];
        ArraySetAsSeries(higher_ma_buf, true);
        if(CopyBuffer(higher_trendma_handle, 0, 1, 1, higher_ma_buf) < 1) return;
        double higher_close = iClose(_Symbol, HigherTF, 1);
        higher_ok_buy  = (higher_close > higher_ma_buf[0]);
        higher_ok_sell = (higher_close < higher_ma_buf[0]);
    }

    bool entry_buy  = armed_buy  && uptrend   && (close_prev > fastema) && bullish && momentum_buy  && adx_ok && env_up   && higher_ok_buy;
    bool entry_sell = armed_sell && downtrend && (close_prev < fastema) && bearish && momentum_sell && adx_ok && env_down && higher_ok_sell;

    bool has_buy  = HasPosition(POSITION_TYPE_BUY);
    bool has_sell = HasPosition(POSITION_TYPE_SELL);

    double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
    double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);

    double sl_dist, tp_dist;
    if(UseATRStops)
    {
        sl_dist = atr * ATR_SL_Mult;
        tp_dist = sl_dist * RR_Ratio;
    }
    else
    {
        sl_dist = StopLoss_Pips   * pip_value;
        tp_dist = TakeProfit_Pips * pip_value;
    }

    // 買いエントリー
    if(entry_buy && !has_buy)
    {
        if(has_sell) ClosePositions(POSITION_TYPE_SELL);
        double sl = NormalizeDouble(ask - sl_dist, _Digits);
        double tp = NormalizeDouble(ask + tp_dist, _Digits);
        if(trade.Buy(CalcLot(sl_dist), _Symbol, ask, sl, tp, "PullbackBuy"))
            Print("[BUY] close=", close_prev, " fastEMA=", DoubleToString(fastema, _Digits),
                  " atr=", DoubleToString(atr, _Digits));
        armed_buy = false; // 1回のアームで1エントリー
    }

    // 売りエントリー
    if(entry_sell && !has_sell)
    {
        if(has_buy) ClosePositions(POSITION_TYPE_BUY);
        double sl = NormalizeDouble(bid + sl_dist, _Digits);
        double tp = NormalizeDouble(bid - tp_dist, _Digits);
        if(trade.Sell(CalcLot(sl_dist), _Symbol, bid, sl, tp, "PullbackSell"))
            Print("[SELL] close=", close_prev, " fastEMA=", DoubleToString(fastema, _Digits),
                  " atr=", DoubleToString(atr, _Digits));
        armed_sell = false;
    }
}

//+------------------------------------------------------------------+
bool HasPosition(ENUM_POSITION_TYPE type)
{
    for(int i = PositionsTotal() - 1; i >= 0; i--)
        if(PositionGetSymbol(i) == _Symbol &&
           PositionGetInteger(POSITION_MAGIC) == MagicNumber &&
           PositionGetInteger(POSITION_TYPE)  == type)
            return true;
    return false;
}

//+------------------------------------------------------------------+
void ClosePositions(ENUM_POSITION_TYPE type)
{
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        ulong ticket = PositionGetTicket(i);
        if(PositionGetSymbol(i) == _Symbol &&
           PositionGetInteger(POSITION_MAGIC) == MagicNumber &&
           PositionGetInteger(POSITION_TYPE)  == type)
            trade.PositionClose(ticket);
    }
}

//+------------------------------------------------------------------+
// リスクベースのロット計算: 資産のRiskPercent%をSL距離でリスクする。
// UseRiskSizing=false なら固定LotSizeを返す（既存挙動と完全一致）。
double CalcLot(double sl_dist_price)
{
    if(!UseRiskSizing || sl_dist_price <= 0.0)
        return LotSize;

    double equity    = AccountInfoDouble(ACCOUNT_EQUITY);
    double riskMoney = equity * RiskPercent / 100.0;

    double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
    double tickSize  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
    if(tickValue <= 0.0 || tickSize <= 0.0)
        return LotSize;

    // SL距離（価格）あたり1ロットの損失額
    double moneyPerLot = (sl_dist_price / tickSize) * tickValue;
    if(moneyPerLot <= 0.0)
        return LotSize;

    double lot = riskMoney / moneyPerLot;

    // ブローカーのロット制約（最小/最大/刻み）に丸める
    double minLot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
    double maxLot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
    double stepLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
    if(stepLot > 0.0)
        lot = MathFloor(lot / stepLot) * stepLot;
    lot = MathMax(minLot, MathMin(maxLot, lot));
    return lot;
}

//+------------------------------------------------------------------+
double OnTester()
{
    double pf = TesterStatistics(STAT_PROFIT_FACTOR);

    // ポートフォリオDD算出用: 全dealの time,profit を書き出す（mt5bt portfolio が合算）
    if(EquityLogFile != "")
    {
        int eqh = FileOpen(EquityLogFile, FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
        if(eqh != INVALID_HANDLE)
        {
            FileWrite(eqh, "time", "profit");
            HistorySelect(0, TimeCurrent());
            int eqTotal = HistoryDealsTotal();
            for(int eqi = 0; eqi < eqTotal; eqi++)
            {
                ulong eqtk = HistoryDealGetTicket(eqi);
                if(eqtk == 0) continue;
                long eqtype = HistoryDealGetInteger(eqtk, DEAL_TYPE);
                if(eqtype != DEAL_TYPE_BUY && eqtype != DEAL_TYPE_SELL) continue; // 残高操作(入金)等を除外
                double eqp = HistoryDealGetDouble(eqtk, DEAL_PROFIT)
                           + HistoryDealGetDouble(eqtk, DEAL_SWAP)
                           + HistoryDealGetDouble(eqtk, DEAL_COMMISSION);
                long eqt = (long)HistoryDealGetInteger(eqtk, DEAL_TIME);
                FileWrite(eqh, eqt, DoubleToString(eqp, 2));
            }
            FileClose(eqh);
        }
    }

    if(ResultFileName == "") return pf;

    int fh = FileOpen(ResultFileName, FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
    if(fh == INVALID_HANDLE)
    {
        Print("結果ファイルを開けません: ", ResultFileName, " Error=", GetLastError());
        return pf;
    }
    FileWrite(fh, "key", "value");
    FileWrite(fh, "net_profit",      DoubleToString(TesterStatistics(STAT_PROFIT), 2));
    FileWrite(fh, "gross_profit",    DoubleToString(TesterStatistics(STAT_GROSS_PROFIT), 2));
    FileWrite(fh, "gross_loss",      DoubleToString(TesterStatistics(STAT_GROSS_LOSS), 2));
    FileWrite(fh, "profit_factor",   DoubleToString(TesterStatistics(STAT_PROFIT_FACTOR), 4));
    FileWrite(fh, "expected_payoff", DoubleToString(TesterStatistics(STAT_EXPECTED_PAYOFF), 2));
    FileWrite(fh, "sharpe_ratio",    DoubleToString(TesterStatistics(STAT_SHARPE_RATIO), 4));
    FileWrite(fh, "max_dd_abs",      DoubleToString(TesterStatistics(STAT_BALANCE_DD), 2));
    FileWrite(fh, "max_dd_pct",      DoubleToString(TesterStatistics(STAT_BALANCE_DDREL_PERCENT), 4));
    FileWrite(fh, "recovery_factor", DoubleToString(TesterStatistics(STAT_RECOVERY_FACTOR), 4));
    FileWrite(fh, "total_trades",    IntegerToString((int)TesterStatistics(STAT_TRADES)));
    FileWrite(fh, "win_trades",      IntegerToString((int)TesterStatistics(STAT_PROFIT_TRADES)));
    FileWrite(fh, "loss_trades",     IntegerToString((int)TesterStatistics(STAT_LOSS_TRADES)));
    FileWrite(fh, "max_profit",      DoubleToString(TesterStatistics(STAT_MAX_PROFITTRADE), 2));
    FileWrite(fh, "max_loss",        DoubleToString(TesterStatistics(STAT_MAX_LOSSTRADE), 2));
    FileWrite(fh, "max_consec_wins", IntegerToString((int)TesterStatistics(STAT_MAX_CONWINS)));
    FileWrite(fh, "max_consec_loss", IntegerToString((int)TesterStatistics(STAT_MAX_CONLOSSES)));
    FileWrite(fh, "initial_deposit", DoubleToString(TesterStatistics(STAT_INITIAL_DEPOSIT), 2));
    FileWrite(fh, "final_balance",   DoubleToString(TesterStatistics(STAT_INITIAL_DEPOSIT) + TesterStatistics(STAT_PROFIT), 2));
    FileClose(fh);
    Print("バックテスト結果を書き出しました: MQL5\\Files\\", ResultFileName);
    return pf;
}
//+------------------------------------------------------------------+

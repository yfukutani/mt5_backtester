//+------------------------------------------------------------------+
//|  KeltnerBreakout.mq5                                             |
//|  ケルトナーチャネル・ブレイク トレンドフォローEA v1.0          |
//|  EMA±ATR チャネルのブレイクで順張り（戦略#11）                  |
//+------------------------------------------------------------------+
#property copyright "2026"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>

//--- 入力パラメータ
input group "=== ケルトナーチャネル ==="
input int    EMA_Period     = 20;   // チャネル中心のEMA期間
input int    ATR_Period     = 14;   // チャネル幅のATR期間
input double ChannelMult    = 2.0;  // チャネル幅 = ATR × この倍率

input group "=== トレンドフィルター ==="
input int            TrendMA_Period = 200;  // 大局トレンドMA（この方向のみエントリー）
input ENUM_MA_METHOD TrendMA_Method = MODE_SMA;
input bool   UseADXFilter  = true;  // ADX強トレンドフィルターを使用する
input int    ADX_Period    = 14;
input double ADX_Threshold = 22.5;  // ADXがこの値以上の強トレンドのみ

input group "=== ストップ（ATRベース） ==="
input bool   UseATRStops   = true;  // ATRベースのSL/TPを使用する
input double ATR_SL_Mult   = 2.0;   // SL距離 = ATR × この倍率
input double RR_Ratio      = 2.0;   // TP距離 = SL距離 × このRR比

input group "=== ストップ（固定pips・UseATRStops=false時） ==="
input int    StopLoss_Pips   = 40;
input int    TakeProfit_Pips = 80;

input group "=== トレード設定 ==="
input double LotSize     = 0.01;
input int    MagicNumber = 20260625;

input group "=== 出力設定 ==="
input string ResultFileName = "";

//--- グローバル変数
CTrade trade;
int    ema_handle;
int    atr_handle;
int    trendma_handle;
int    adx_handle;
double pip_value;

//+------------------------------------------------------------------+
int OnInit()
{
    pip_value = (_Digits == 3 || _Digits == 5) ? 10 * _Point : _Point;

    ema_handle     = iMA(_Symbol, PERIOD_CURRENT, EMA_Period, 0, MODE_EMA, PRICE_CLOSE);
    atr_handle     = iATR(_Symbol, PERIOD_CURRENT, ATR_Period);
    trendma_handle = iMA(_Symbol, PERIOD_CURRENT, TrendMA_Period, 0, TrendMA_Method, PRICE_CLOSE);
    adx_handle     = iADX(_Symbol, PERIOD_CURRENT, ADX_Period);

    if(ema_handle == INVALID_HANDLE || atr_handle == INVALID_HANDLE ||
       trendma_handle == INVALID_HANDLE || adx_handle == INVALID_HANDLE)
    {
        Print("インジケーターハンドルの作成に失敗しました");
        return INIT_FAILED;
    }

    trade.SetExpertMagicNumber(MagicNumber);
    trade.SetDeviationInPoints(10);
    Print("KeltnerBreakout v1.0 起動 | EMA=", EMA_Period, " ATR=", ATR_Period,
          " ChMult=", DoubleToString(ChannelMult, 1), " TrendMA=", TrendMA_Period,
          " | ADX=", UseADXFilter ? StringFormat("ON(>=%.1f)", ADX_Threshold) : "OFF",
          " | Stops=", UseATRStops ? StringFormat("ATR(x%.1f RR%.1f)", ATR_SL_Mult, RR_Ratio)
                                   : StringFormat("Fixed(SL%d TP%d)", StopLoss_Pips, TakeProfit_Pips));
    return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
    IndicatorRelease(ema_handle);
    IndicatorRelease(atr_handle);
    IndicatorRelease(trendma_handle);
    IndicatorRelease(adx_handle);
}

//+------------------------------------------------------------------+
void OnTick()
{
    static datetime last_bar_time = 0;
    datetime current_bar_time = iTime(_Symbol, PERIOD_CURRENT, 0);
    if(current_bar_time == last_bar_time) return;
    last_bar_time = current_bar_time;

    // インジケーター値（前確定足 shift=1 と その1本前 shift=2）
    double ema_buf[], atr_buf[], trendma_buf[];
    ArraySetAsSeries(ema_buf,     true);
    ArraySetAsSeries(atr_buf,     true);
    ArraySetAsSeries(trendma_buf, true);

    if(CopyBuffer(ema_handle,     0, 1, 2, ema_buf)     < 2) return;
    if(CopyBuffer(atr_handle,     0, 1, 2, atr_buf)     < 2) return;
    if(CopyBuffer(trendma_handle, 0, 1, 1, trendma_buf) < 1) return;

    double ema_prev  = ema_buf[0];   // shift=1
    double atr_prev  = atr_buf[0];
    double ema_prev2 = ema_buf[1];   // shift=2
    double atr_prev2 = atr_buf[1];
    double trendma   = trendma_buf[0];

    double close_prev  = iClose(_Symbol, PERIOD_CURRENT, 1);
    double close_prev2 = iClose(_Symbol, PERIOD_CURRENT, 2);

    // ケルトナーチャネル境界
    double upper_prev  = ema_prev  + atr_prev  * ChannelMult;
    double lower_prev  = ema_prev  - atr_prev  * ChannelMult;
    double upper_prev2 = ema_prev2 + atr_prev2 * ChannelMult;
    double lower_prev2 = ema_prev2 - atr_prev2 * ChannelMult;

    // トレンド判定
    bool uptrend   = (close_prev > trendma);
    bool downtrend = (close_prev < trendma);

    // ブレイク判定: 直前足はチャネル内、前確定足で上限/下限を終値ブレイク
    bool break_up   = (close_prev2 <= upper_prev2) && (close_prev > upper_prev);
    bool break_down = (close_prev2 >= lower_prev2) && (close_prev < lower_prev);

    // ADXフィルター
    bool adx_ok = true;
    if(UseADXFilter)
    {
        double adx_buf[];
        ArraySetAsSeries(adx_buf, true);
        if(CopyBuffer(adx_handle, 0, 1, 1, adx_buf) < 1) return;
        adx_ok = (adx_buf[0] >= ADX_Threshold);
    }

    bool entry_buy  = uptrend   && break_up   && adx_ok;
    bool entry_sell = downtrend && break_down && adx_ok;

    bool has_buy  = HasPosition(POSITION_TYPE_BUY);
    bool has_sell = HasPosition(POSITION_TYPE_SELL);

    double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
    double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);

    double sl_dist, tp_dist;
    if(UseATRStops)
    {
        sl_dist = atr_prev * ATR_SL_Mult;
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
        if(trade.Buy(LotSize, _Symbol, ask, sl, tp, "KeltnerBuy"))
            Print("[BUY] close=", close_prev, " upper=", DoubleToString(upper_prev, _Digits),
                  " atr=", DoubleToString(atr_prev, _Digits));
    }

    // 売りエントリー
    if(entry_sell && !has_sell)
    {
        if(has_buy) ClosePositions(POSITION_TYPE_BUY);
        double sl = NormalizeDouble(bid + sl_dist, _Digits);
        double tp = NormalizeDouble(bid - tp_dist, _Digits);
        if(trade.Sell(LotSize, _Symbol, bid, sl, tp, "KeltnerSell"))
            Print("[SELL] close=", close_prev, " lower=", DoubleToString(lower_prev, _Digits),
                  " atr=", DoubleToString(atr_prev, _Digits));
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
double OnTester()
{
    double pf = TesterStatistics(STAT_PROFIT_FACTOR);
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

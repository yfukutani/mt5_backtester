//+------------------------------------------------------------------+
//|  DMI_Cross.mq5                                                   |
//|  ADX強トレンド + DIクロス 順張りEA v1.1                         |
//|  +DI/-DIのクロスをトレンド方向に取る（戦略#15）                 |
//|  v1.1: ADX傾き・DI乖離幅フィルターを追加                        |
//+------------------------------------------------------------------+
#property copyright "2026"
#property version   "1.10"
#property strict

#include <Trade\Trade.mqh>

//--- 入力パラメータ
input group "=== DMI/ADX設定 ==="
input int    ADX_Period    = 14;    // ADX/DMI期間
input double ADX_Threshold = 22.5;  // ADXがこの値以上の強トレンドのみ

input group "=== クロス品質フィルター ==="
input bool   UseADXSlope   = false; // ADX上昇中（トレンド加速）のクロスのみ（検証で取引激減のためOFF）
input bool   UseDISpread   = false; // +DI/-DIの乖離が閾値以上のクロスのみ（検証で純利益減のためOFF）
input double DI_Min_Spread = 3.0;   // クロス時に必要な+DI/-DI乖離幅

input group "=== トレンドフィルター ==="
input int            TrendMA_Period = 200;  // 大局トレンドMA（この方向のみエントリー）
input ENUM_MA_METHOD TrendMA_Method = MODE_SMA;
input bool           UseMAFilter    = true; // MA200トレンドフィルターを使用する

input group "=== ストップ（ATRベース） ==="
input bool   UseATRStops   = true;  // ATRベースのSL/TPを使用する
input int    ATR_Period    = 14;
input double ATR_SL_Mult   = 2.0;   // SL距離 = ATR × この倍率
input double RR_Ratio      = 2.0;   // TP距離 = SL距離 × このRR比

input group "=== ストップ（固定pips・UseATRStops=false時） ==="
input int    StopLoss_Pips   = 40;
input int    TakeProfit_Pips = 80;

input group "=== トレード設定 ==="
input double LotSize     = 0.01;
input int    MagicNumber = 20260626;

input group "=== 出力設定 ==="
input string ResultFileName = "";

//--- グローバル変数
CTrade trade;
int    adx_handle;
int    atr_handle;
int    trendma_handle;
double pip_value;

//+------------------------------------------------------------------+
int OnInit()
{
    pip_value = (_Digits == 3 || _Digits == 5) ? 10 * _Point : _Point;

    adx_handle     = iADX(_Symbol, PERIOD_CURRENT, ADX_Period);
    atr_handle     = iATR(_Symbol, PERIOD_CURRENT, ATR_Period);
    trendma_handle = iMA(_Symbol, PERIOD_CURRENT, TrendMA_Period, 0, TrendMA_Method, PRICE_CLOSE);

    if(adx_handle == INVALID_HANDLE || atr_handle == INVALID_HANDLE ||
       trendma_handle == INVALID_HANDLE)
    {
        Print("インジケーターハンドルの作成に失敗しました");
        return INIT_FAILED;
    }

    trade.SetExpertMagicNumber(MagicNumber);
    trade.SetDeviationInPoints(10);
    Print("DMI_Cross v1.1 起動 | ADX=", ADX_Period, " 閾値=", DoubleToString(ADX_Threshold, 1),
          " | ADX傾き=", UseADXSlope ? "ON" : "OFF",
          " | DI乖離=", UseDISpread ? StringFormat("ON(>=%.1f)", DI_Min_Spread) : "OFF",
          " | MAフィルター=", UseMAFilter ? StringFormat("ON(%d)", TrendMA_Period) : "OFF",
          " | Stops=", UseATRStops ? StringFormat("ATR(x%.1f RR%.1f)", ATR_SL_Mult, RR_Ratio)
                                   : StringFormat("Fixed(SL%d TP%d)", StopLoss_Pips, TakeProfit_Pips));
    return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
    IndicatorRelease(adx_handle);
    IndicatorRelease(atr_handle);
    IndicatorRelease(trendma_handle);
}

//+------------------------------------------------------------------+
void OnTick()
{
    static datetime last_bar_time = 0;
    datetime current_bar_time = iTime(_Symbol, PERIOD_CURRENT, 0);
    if(current_bar_time == last_bar_time) return;
    last_bar_time = current_bar_time;

    // DMI値: バッファ0=ADX, 1=+DI, 2=-DI（shift=1とshift=2を取得）
    double adx_buf[], plus_buf[], minus_buf[], atr_buf[], trendma_buf[];
    ArraySetAsSeries(adx_buf,     true);
    ArraySetAsSeries(plus_buf,    true);
    ArraySetAsSeries(minus_buf,   true);
    ArraySetAsSeries(atr_buf,     true);
    ArraySetAsSeries(trendma_buf, true);

    if(CopyBuffer(adx_handle, 0, 1, 2, adx_buf)   < 2) return;
    if(CopyBuffer(adx_handle, 1, 1, 2, plus_buf)  < 2) return;
    if(CopyBuffer(adx_handle, 2, 1, 2, minus_buf) < 2) return;
    if(CopyBuffer(atr_handle, 0, 1, 1, atr_buf)   < 1) return;
    if(CopyBuffer(trendma_handle, 0, 1, 1, trendma_buf) < 1) return;

    double adx        = adx_buf[0];      // shift=1
    double adx_prev2  = adx_buf[1];      // ADX shift=2（傾き判定用）
    double plus_prev  = plus_buf[0];     // +DI shift=1
    double minus_prev = minus_buf[0];    // -DI shift=1
    double plus_prev2 = plus_buf[1];     // +DI shift=2
    double minus_prev2= minus_buf[1];    // -DI shift=2
    double atr        = atr_buf[0];
    double trendma    = trendma_buf[0];

    double close_prev = iClose(_Symbol, PERIOD_CURRENT, 1);

    // DIクロス検出: 前足で +DI<-DI、前確定足で +DI>-DI → 強気クロス
    bool cross_up   = (plus_prev2 <= minus_prev2) && (plus_prev > minus_prev);
    bool cross_down = (plus_prev2 >= minus_prev2) && (plus_prev < minus_prev);

    // ADX強トレンド条件
    bool strong = (adx >= ADX_Threshold);

    // MA200トレンドフィルター
    bool uptrend   = !UseMAFilter || (close_prev > trendma);
    bool downtrend = !UseMAFilter || (close_prev < trendma);

    // ADX傾きフィルター（トレンド加速中のクロスのみ）
    bool adx_rising = !UseADXSlope || (adx > adx_prev2);

    // DI乖離幅フィルター（拮抗した弱いクロスを除外）
    bool spread_buy  = !UseDISpread || ((plus_prev  - minus_prev) >= DI_Min_Spread);
    bool spread_sell = !UseDISpread || ((minus_prev - plus_prev)  >= DI_Min_Spread);

    bool entry_buy  = cross_up   && strong && uptrend   && adx_rising && spread_buy;
    bool entry_sell = cross_down && strong && downtrend && adx_rising && spread_sell;

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
        if(trade.Buy(LotSize, _Symbol, ask, sl, tp, "DMI_Buy"))
            Print("[BUY] +DI=", DoubleToString(plus_prev,1), " -DI=", DoubleToString(minus_prev,1),
                  " ADX=", DoubleToString(adx,1));
    }

    // 売りエントリー
    if(entry_sell && !has_sell)
    {
        if(has_buy) ClosePositions(POSITION_TYPE_BUY);
        double sl = NormalizeDouble(bid + sl_dist, _Digits);
        double tp = NormalizeDouble(bid - tp_dist, _Digits);
        if(trade.Sell(LotSize, _Symbol, bid, sl, tp, "DMI_Sell"))
            Print("[SELL] +DI=", DoubleToString(plus_prev,1), " -DI=", DoubleToString(minus_prev,1),
                  " ADX=", DoubleToString(adx,1));
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

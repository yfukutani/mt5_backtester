//+------------------------------------------------------------------+
//|  RSIDivergence.mq5                                               |
//|  RSIダイバージェンス逆張りEA v1.0（新規戦略候補#10）             |
//|  価格が新高値/新安値を更新する一方、RSIが追随しない               |
//|  （レギュラーダイバージェンス）を検出し、トレンド転換を逆張りで取る|
//+------------------------------------------------------------------+
#property copyright "2026"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>

input group "=== RSI設定 ==="
input int RSI_Period = 14;

input group "=== ダイバージェンス検出 ==="
input int    Swing_Lookback  = 3;    // スイング判定の前後本数
input int    Pattern_Bars    = 60;   // パターン検索範囲（本数）

input group "=== ストップ（ATRベース） ==="
input int    ATR_Period  = 14;
input double ATR_SL_Mult = 1.5;   // SL距離 = ATR × この倍率
input double RR_Ratio    = 2.0;   // TP距離 = SL距離 × このRR比

input group "=== トレード設定 ==="
input double LotSize     = 0.01;
input int    MagicNumber = 20260900;

input group "=== 出力設定 ==="
input string ResultFileName = "";
input string EquityLogFile  = "";

CTrade trade;
int    rsi_handle;
int    atr_handle;

//+------------------------------------------------------------------+
int OnInit()
{
    rsi_handle = iRSI(_Symbol, PERIOD_CURRENT, RSI_Period, PRICE_CLOSE);
    atr_handle = iATR(_Symbol, PERIOD_CURRENT, ATR_Period);
    if(rsi_handle == INVALID_HANDLE || atr_handle == INVALID_HANDLE)
    {
        Print("インジケーターハンドルの作成に失敗しました");
        return INIT_FAILED;
    }
    trade.SetExpertMagicNumber(MagicNumber);
    trade.SetDeviationInPoints(10);
    Print("RSIDivergence v1.0 起動 | RSI=", RSI_Period, " SwingLB=", Swing_Lookback, " PatternBars=", Pattern_Bars);
    return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
    IndicatorRelease(rsi_handle);
    IndicatorRelease(atr_handle);
}

//+------------------------------------------------------------------+
bool IsSwingHigh(const double &arr[], int idx, int lb, int sz)
{
    if(idx < lb || idx + lb >= sz) return false;
    double v = arr[idx];
    for(int k = 1; k <= lb; k++)
        if(arr[idx - k] >= v || arr[idx + k] >= v) return false;
    return true;
}

bool IsSwingLow(const double &arr[], int idx, int lb, int sz)
{
    if(idx < lb || idx + lb >= sz) return false;
    double v = arr[idx];
    for(int k = 1; k <= lb; k++)
        if(arr[idx - k] <= v || arr[idx + k] <= v) return false;
    return true;
}

// 弱気ダイバージェンス: 価格の高値切り上げ + RSIの高値切り下げ → ネックライン(直近安値)を返す
bool DetectBearishDivergence(const double &high[], const double &low[], const double &rsi[],
                              int pb, int lb, double &neck_out)
{
    int sz = ArraySize(high);
    int h1 = -1;
    for(int i = lb; i < pb - lb; i++)
        if(IsSwingHigh(high, i, lb, sz)) { h1 = i; break; }
    if(h1 < 0) return false;

    int h2 = -1;
    for(int i = h1 + lb + 1; i < pb; i++)
        if(IsSwingHigh(high, i, lb, sz)) { h2 = i; break; }
    if(h2 < 0) return false;

    bool price_higher_high = high[h1] > high[h2];
    bool rsi_lower_high    = rsi[h1] < rsi[h2];
    if(!price_higher_high || !rsi_lower_high) return false;

    double neck = DBL_MAX;
    for(int i = h1 + 1; i < h2; i++)
        if(IsSwingLow(low, i, lb, sz) && low[i] < neck) neck = low[i];
    if(neck == DBL_MAX) return false;

    neck_out = neck;
    return true;
}

// 強気ダイバージェンス: 価格の安値切り下げ + RSIの安値切り上げ → ネックライン(直近高値)を返す
bool DetectBullishDivergence(const double &high[], const double &low[], const double &rsi[],
                             int pb, int lb, double &neck_out)
{
    int sz = ArraySize(low);
    int l1 = -1;
    for(int i = lb; i < pb - lb; i++)
        if(IsSwingLow(low, i, lb, sz)) { l1 = i; break; }
    if(l1 < 0) return false;

    int l2 = -1;
    for(int i = l1 + lb + 1; i < pb; i++)
        if(IsSwingLow(low, i, lb, sz)) { l2 = i; break; }
    if(l2 < 0) return false;

    bool price_lower_low = low[l1] < low[l2];
    bool rsi_higher_low  = rsi[l1] > rsi[l2];
    if(!price_lower_low || !rsi_higher_low) return false;

    double neck = 0;
    for(int i = l1 + 1; i < l2; i++)
        if(IsSwingHigh(high, i, lb, sz) && high[i] > neck) neck = high[i];
    if(neck <= 0) return false;

    neck_out = neck;
    return true;
}

//+------------------------------------------------------------------+
void OnTick()
{
    static datetime last_bar_time = 0;
    datetime current_bar_time = iTime(_Symbol, PERIOD_CURRENT, 0);
    if(current_bar_time == last_bar_time) return;
    last_bar_time = current_bar_time;

    double atr_buf[];
    ArraySetAsSeries(atr_buf, true);
    if(CopyBuffer(atr_handle, 0, 1, 1, atr_buf) < 1) return;
    double atr = atr_buf[0];

    int bs = Pattern_Bars + Swing_Lookback + 5;
    double high_buf[], low_buf[], rsi_buf[];
    ArraySetAsSeries(high_buf, true);
    ArraySetAsSeries(low_buf,  true);
    ArraySetAsSeries(rsi_buf,  true);
    if(CopyHigh(_Symbol, PERIOD_CURRENT, 1, bs, high_buf) < bs) return;
    if(CopyLow(_Symbol,  PERIOD_CURRENT, 1, bs, low_buf)  < bs) return;
    if(CopyBuffer(rsi_handle, 0, 1, bs, rsi_buf) < bs) return;

    double close_prev = iClose(_Symbol, PERIOD_CURRENT, 1);

    bool bear_div = false, bull_div = false;
    double neck_sell = 0, neck_buy = 0;
    if(DetectBearishDivergence(high_buf, low_buf, rsi_buf, Pattern_Bars, Swing_Lookback, neck_sell))
        bear_div = (close_prev <= neck_sell);
    if(DetectBullishDivergence(high_buf, low_buf, rsi_buf, Pattern_Bars, Swing_Lookback, neck_buy))
        bull_div = (close_prev >= neck_buy);

    bool has_buy  = HasPosition(POSITION_TYPE_BUY);
    bool has_sell = HasPosition(POSITION_TYPE_SELL);

    double sl_dist = atr * ATR_SL_Mult;
    double tp_dist = sl_dist * RR_Ratio;
    double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
    double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);

    if(bull_div && !has_buy)
    {
        if(has_sell) ClosePositions(POSITION_TYPE_SELL);
        double sl = NormalizeDouble(ask - sl_dist, _Digits);
        double tp = NormalizeDouble(ask + tp_dist, _Digits);
        if(trade.Buy(LotSize, _Symbol, ask, sl, tp, "BullDiv"))
            Print("[BUY] BullishDivergence close=", close_prev, " neck=", DoubleToString(neck_buy, _Digits));
    }
    if(bear_div && !has_sell)
    {
        if(has_buy) ClosePositions(POSITION_TYPE_BUY);
        double sl = NormalizeDouble(bid + sl_dist, _Digits);
        double tp = NormalizeDouble(bid - tp_dist, _Digits);
        if(trade.Sell(LotSize, _Symbol, bid, sl, tp, "BearDiv"))
            Print("[SELL] BearishDivergence close=", close_prev, " neck=", DoubleToString(neck_sell, _Digits));
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
                if(eqtype != DEAL_TYPE_BUY && eqtype != DEAL_TYPE_SELL) continue;
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
    if(fh == INVALID_HANDLE) return pf;
    FileWrite(fh, "key", "value");
    FileWrite(fh, "net_profit",      DoubleToString(TesterStatistics(STAT_PROFIT), 2));
    FileWrite(fh, "profit_factor",   DoubleToString(TesterStatistics(STAT_PROFIT_FACTOR), 4));
    FileWrite(fh, "max_dd_abs",      DoubleToString(TesterStatistics(STAT_BALANCE_DD), 2));
    FileWrite(fh, "max_dd_pct",      DoubleToString(TesterStatistics(STAT_BALANCE_DDREL_PERCENT), 4));
    FileWrite(fh, "recovery_factor", DoubleToString(TesterStatistics(STAT_RECOVERY_FACTOR), 4));
    FileWrite(fh, "total_trades",    IntegerToString((int)TesterStatistics(STAT_TRADES)));
    FileWrite(fh, "win_trades",      IntegerToString((int)TesterStatistics(STAT_PROFIT_TRADES)));
    FileWrite(fh, "loss_trades",     IntegerToString((int)TesterStatistics(STAT_LOSS_TRADES)));
    FileWrite(fh, "initial_deposit", DoubleToString(TesterStatistics(STAT_INITIAL_DEPOSIT), 2));
    FileWrite(fh, "final_balance",   DoubleToString(TesterStatistics(STAT_INITIAL_DEPOSIT) + TesterStatistics(STAT_PROFIT), 2));
    FileClose(fh);
    return pf;
}
//+------------------------------------------------------------------+

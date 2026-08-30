//+------------------------------------------------------------------+
//|  SCA_DL_EA.mq5                                                   |
//|  デイリーレベル・スキャルパー v1.0（バックログE1/E2）              |
//|  前日高値(PDH)/前日安値(PDL)をキーレベルとして:                    |
//|   Mode=0 (E1 Breakout): 実体ブレイクで順張り                       |
//|   Mode=1 (E2 Sweep):    ヒゲで一瞬抜けて実体が戻る「流動性スイープ」|
//|                         を検出して逆張り（ストップ狩りフェード）    |
//|  ORB(SCA_EA)とは別レベル体系＝相補の追加収益源候補。M15チャート。   |
//|  ※検証は必ず every_tick（スプレッド実費込み）で行うこと。          |
//+------------------------------------------------------------------+
#property copyright "2026"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>

input group "=== モード ==="
input int Mode = 0;   // 0=E1ブレイク順張り / 1=E2スイープ逆張り

input group "=== 時間帯（サーバー時間・XM=GMT+2/+3） ==="
input int TradeStartHour = 9;    // 監視開始（欧州時間）
input int TradeEndHour   = 18;   // 新規最終
input int ForceCloseHour = 22;   // 全決済

input group "=== エントリー/エグジット ==="
input double SL_ATRd_Mult   = 0.30;  // SL距離 = D1ATR×この値（Mode0）
input double RR_Ratio       = 1.5;   // TP = SL距離×RR
input double Sweep_SL_ATRd  = 0.20;  // Mode1: SL=スイープ髭の先+D1ATR×この値
input bool   OneShotPerDir  = true;

input group "=== スプレッドガード ==="
input int MaxSpreadPoints = 0;

input group "=== トレード設定 ==="
input double LotSize     = 0.01;
input int    MagicNumber = 20261030;

input group "=== 出力設定 ==="
input string ResultFileName = "";
input string EquityLogFile  = "";

CTrade trade;
int    atr_d1_handle;

datetime g_day        = 0;
double   g_pdh = 0.0, g_pdl = 0.0;
bool     g_tradedLong = false;
bool     g_tradedShort= false;

//+------------------------------------------------------------------+
int OnInit()
{
    atr_d1_handle = iATR(_Symbol, PERIOD_D1, 14);
    if(atr_d1_handle == INVALID_HANDLE) return INIT_FAILED;
    trade.SetExpertMagicNumber(MagicNumber);
    trade.SetDeviationInPoints(20);
    Print("SCA_DL v1.0 起動 | ", _Symbol, " | Mode=", Mode,
          " | ", TradeStartHour, "-", TradeEndHour, "h / Close ", ForceCloseHour, "h");
    return INIT_SUCCEEDED;
}

void OnDeinit(const int reason) { IndicatorRelease(atr_d1_handle); }

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

void CloseAll()
{
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        ulong ticket = PositionGetTicket(i);
        if(PositionGetSymbol(i) == _Symbol &&
           PositionGetInteger(POSITION_MAGIC) == MagicNumber)
            trade.PositionClose(ticket);
    }
}

//+------------------------------------------------------------------+
void OnTick()
{
    static datetime last_bar_time = 0;
    datetime bar_time = iTime(_Symbol, PERIOD_CURRENT, 0);
    if(bar_time == last_bar_time) return;
    last_bar_time = bar_time;

    MqlDateTime dt;
    TimeToStruct(bar_time, dt);
    datetime day_start = bar_time - (dt.hour * 3600 + dt.min * 60 + dt.sec);

    if(day_start != g_day)
    {
        g_day = day_start;
        g_pdh = iHigh(_Symbol, PERIOD_D1, 1);   // 前日高安（D1バー確定値）
        g_pdl = iLow(_Symbol, PERIOD_D1, 1);
        g_tradedLong = false;
        g_tradedShort= false;
    }

    if(dt.hour >= ForceCloseHour)
    {
        CloseAll();
        return;
    }
    if(dt.hour < TradeStartHour || dt.hour >= TradeEndHour) return;
    if(g_pdh <= 0 || g_pdl <= 0 || g_pdh <= g_pdl) return;

    double atrd_buf[];
    ArraySetAsSeries(atrd_buf, true);
    if(CopyBuffer(atr_d1_handle, 0, 1, 1, atrd_buf) < 1) return;
    double atrd = atrd_buf[0];
    if(atrd <= 0.0) return;

    if(MaxSpreadPoints > 0 &&
       SymbolInfoInteger(_Symbol, SYMBOL_SPREAD) > MaxSpreadPoints) return;

    double close1 = iClose(_Symbol, PERIOD_CURRENT, 1);
    double high1  = iHigh(_Symbol, PERIOD_CURRENT, 1);
    double low1   = iLow(_Symbol, PERIOD_CURRENT, 1);
    bool has_buy  = HasPosition(POSITION_TYPE_BUY);
    bool has_sell = HasPosition(POSITION_TYPE_SELL);

    if(Mode == 0)
    {
        // E1: 前日高値の実体ブレイク → 買い / 前日安値割れ → 売り
        if(close1 > g_pdh && !has_buy && !(OneShotPerDir && g_tradedLong))
        {
            double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
            double sl  = NormalizeDouble(ask - SL_ATRd_Mult * atrd, _Digits);
            double tp  = NormalizeDouble(ask + RR_Ratio * SL_ATRd_Mult * atrd, _Digits);
            if(trade.Buy(LotSize, _Symbol, ask, sl, tp, "DL-B-L")) g_tradedLong = true;
        }
        if(close1 < g_pdl && !has_sell && !(OneShotPerDir && g_tradedShort))
        {
            double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
            double sl  = NormalizeDouble(bid + SL_ATRd_Mult * atrd, _Digits);
            double tp  = NormalizeDouble(bid - RR_Ratio * SL_ATRd_Mult * atrd, _Digits);
            if(trade.Sell(LotSize, _Symbol, bid, sl, tp, "DL-B-S")) g_tradedShort = true;
        }
    }
    else
    {
        // E2: スイープ（ヒゲが前日高値を抜き実体は戻る）→ 売り / 対称で買い
        if(high1 > g_pdh && close1 < g_pdh && !has_sell && !(OneShotPerDir && g_tradedShort))
        {
            double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
            double sl  = NormalizeDouble(high1 + Sweep_SL_ATRd * atrd, _Digits);
            double dist = sl - bid;
            if(dist > 0)
            {
                double tp = NormalizeDouble(bid - RR_Ratio * dist, _Digits);
                if(trade.Sell(LotSize, _Symbol, bid, sl, tp, "DL-SW-S")) g_tradedShort = true;
            }
        }
        if(low1 < g_pdl && close1 > g_pdl && !has_buy && !(OneShotPerDir && g_tradedLong))
        {
            double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
            double sl  = NormalizeDouble(low1 - Sweep_SL_ATRd * atrd, _Digits);
            double dist = ask - sl;
            if(dist > 0)
            {
                double tp = NormalizeDouble(ask + RR_Ratio * dist, _Digits);
                if(trade.Buy(LotSize, _Symbol, ask, sl, tp, "DL-SW-L")) g_tradedLong = true;
            }
        }
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
                FileWrite(eqh, (long)HistoryDealGetInteger(eqtk, DEAL_TIME),
                          DoubleToString(eqp, 2));
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

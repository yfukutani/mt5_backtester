//+------------------------------------------------------------------+
//|  SCA_BOX_EA.mq5                                                  |
//|  ボックス往復スキャルパー v1.0（バックログE12）                    |
//|  SCA_EA(ORB)が MinRange フィルターで捨てている「狭レンジ日」を     |
//|  レンジ端タッチの逆張り（中央/反対端回帰）で収益化する相補戦略。    |
//|  レンジ定義はORBと同一（アジア0-9hサーバー時間）。                  |
//|  レンジをブレイクした日は逆張り停止（ブレイク日はORBの領分）。      |
//|  ※検証は必ず every_tick（スプレッド実費込み）で行うこと。          |
//+------------------------------------------------------------------+
#property copyright "2026"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>

input group "=== セッション定義（サーバー時間・XM=GMT+2/+3） ==="
input int RangeStartHour = 0;   // レンジ計測開始時
input int RangeEndHour   = 9;   // レンジ確定時。この時刻以降タッチ監視
input int TradeEndHour   = 20;  // 新規エントリー最終時
input int ForceCloseHour = 22;  // 全決済時

input group "=== ボックス条件（D1 ATR正規化・ORBのMinRangeと相補） ==="
input double BoxMin_ATRd = 0.15;  // レンジ幅がこれ未満はスキップ（スプレッド負け回避）
input double BoxMax_ATRd = 0.45;  // レンジ幅がこれ超はスキップ（=ORB対象日）

input group "=== エントリー/エグジット ==="
input int    TP_Mode        = 0;    // 0=レンジ中央 / 1=反対端
input double SL_Width_Mult  = 0.5;  // SL=レンジ端の外側×レンジ幅×この値
input bool   OneShotPerDir  = true; // 1日1方向1回まで
input bool   StopAfterBreak = true; // 実体ブレイク発生後は当日停止

input group "=== スプレッドガード ==="
input int MaxSpreadPoints = 0;

input group "=== トレード設定 ==="
input double LotSize     = 0.01;
input int    MagicNumber = 20261020;

input group "=== 出力設定 ==="
input string ResultFileName = "";
input string EquityLogFile  = "";

CTrade trade;
int    atr_d1_handle;

datetime g_day        = 0;
double   g_rangeHigh  = 0.0;
double   g_rangeLow   = 0.0;
bool     g_rangeReady = false;
bool     g_rangeSkip  = false;
bool     g_dead       = false;   // ブレイク後の当日停止
bool     g_tradedLong = false;
bool     g_tradedShort= false;

//+------------------------------------------------------------------+
int OnInit()
{
    atr_d1_handle = iATR(_Symbol, PERIOD_D1, 14);
    if(atr_d1_handle == INVALID_HANDLE) return INIT_FAILED;
    trade.SetExpertMagicNumber(MagicNumber);
    trade.SetDeviationInPoints(20);
    Print("SCA_BOX v1.0 起動 | ", _Symbol, " | Box ", BoxMin_ATRd, "-", BoxMax_ATRd,
          "×ATRd | TP_Mode=", TP_Mode, " SLw=", SL_Width_Mult);
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
bool ComputeRange(datetime day_start)
{
    datetime t_from = day_start + RangeStartHour * 3600;
    datetime t_to   = day_start + RangeEndHour   * 3600;
    double hi = -DBL_MAX, lo = DBL_MAX;
    int bars = Bars(_Symbol, PERIOD_CURRENT);
    for(int sft = 1; sft < 200; sft++)
    {
        if(sft >= bars) break;
        datetime bt = iTime(_Symbol, PERIOD_CURRENT, sft);
        if(bt < t_from) break;
        if(bt >= t_to) continue;
        double h = iHigh(_Symbol, PERIOD_CURRENT, sft);
        double l = iLow(_Symbol, PERIOD_CURRENT, sft);
        if(h > hi) hi = h;
        if(l < lo) lo = l;
    }
    if(hi <= -DBL_MAX || lo >= DBL_MAX) return false;
    g_rangeHigh = hi;
    g_rangeLow  = lo;
    return true;
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
        g_rangeReady = false;
        g_rangeSkip  = false;
        g_dead       = false;
        g_tradedLong = false;
        g_tradedShort= false;
    }

    if(dt.hour >= ForceCloseHour)
    {
        CloseAll();
        return;
    }

    if(!g_rangeReady && dt.hour >= RangeEndHour)
    {
        if(!ComputeRange(day_start)) return;
        g_rangeReady = true;
        double atrd_buf[];
        ArraySetAsSeries(atrd_buf, true);
        if(CopyBuffer(atr_d1_handle, 0, 1, 1, atrd_buf) < 1) return;
        double atrd = atrd_buf[0];
        double width = g_rangeHigh - g_rangeLow;
        if(atrd <= 0.0 || width < BoxMin_ATRd * atrd || width > BoxMax_ATRd * atrd)
            g_rangeSkip = true;
    }
    if(!g_rangeReady || g_rangeSkip || g_dead) return;
    if(dt.hour < RangeEndHour || dt.hour >= TradeEndHour) return;

    double close1 = iClose(_Symbol, PERIOD_CURRENT, 1);
    double high1  = iHigh(_Symbol, PERIOD_CURRENT, 1);
    double low1   = iLow(_Symbol, PERIOD_CURRENT, 1);
    double width  = g_rangeHigh - g_rangeLow;
    double mid    = g_rangeLow + width / 2.0;

    // 実体ブレイクが起きた日は逆張り停止（ORBの領分）
    if(StopAfterBreak && (close1 > g_rangeHigh || close1 < g_rangeLow))
    {
        g_dead = true;
        return;
    }

    if(MaxSpreadPoints > 0 &&
       SymbolInfoInteger(_Symbol, SYMBOL_SPREAD) > MaxSpreadPoints) return;

    bool has_buy  = HasPosition(POSITION_TYPE_BUY);
    bool has_sell = HasPosition(POSITION_TYPE_SELL);

    // 上端タッチ（ヒゲ到達・実体はレンジ内）→ 売り
    if(high1 >= g_rangeHigh && close1 < g_rangeHigh && !has_sell &&
       !(OneShotPerDir && g_tradedShort))
    {
        double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
        double sl  = NormalizeDouble(g_rangeHigh + SL_Width_Mult * width, _Digits);
        double tp  = NormalizeDouble(TP_Mode == 0 ? mid : g_rangeLow, _Digits);
        if(bid > tp && sl > bid)
            if(trade.Sell(LotSize, _Symbol, bid, sl, tp, "BOX-S"))
                g_tradedShort = true;
    }
    // 下端タッチ → 買い
    if(low1 <= g_rangeLow && close1 > g_rangeLow && !has_buy &&
       !(OneShotPerDir && g_tradedLong))
    {
        double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
        double sl  = NormalizeDouble(g_rangeLow - SL_Width_Mult * width, _Digits);
        double tp  = NormalizeDouble(TP_Mode == 0 ? mid : g_rangeHigh, _Digits);
        if(ask < tp && sl < ask)
            if(trade.Buy(LotSize, _Symbol, ask, sl, tp, "BOX-L"))
                g_tradedLong = true;
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

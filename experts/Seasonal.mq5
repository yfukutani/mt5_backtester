//+------------------------------------------------------------------+
//|  Seasonal.mq5                                                    |
//|  季節性（ターン・オブ・マンス）EA v1.0                            |
//|  月末の最終N営業日にロング→新月の第M営業日で決済。               |
//|  機関リバランス/年金フローによるカレンダー・アノマリーを取る。   |
//|  価格パターンに依存しない別軸収益源（既存EAと機構的に無相関）。  |
//|  営業日はカレンダーから決定的に算出（先読みなし、祝日は無視＝近似）|
//+------------------------------------------------------------------+
#property copyright "2026"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>

input group "=== ターン・オブ・マンス窓 ==="
input int    DaysBeforeEnd  = 1;   // 月末の最終N営業日でエントリー（1=最終営業日のみ）
input int    DaysAfterStart = 3;   // 新月の第M営業日で決済

input group "=== トレンドフィルター（任意・既定OFFで純粋カレンダー） ==="
input bool            UseTrendFilter = false;     // ON: 大局MA上のときのみロング（弱気相場回避）
input int             TrendMA_Period = 200;
input ENUM_MA_METHOD  TrendMA_Method = MODE_SMA;

input group "=== トレード設定 ==="
input double LotSize     = 0.1;    // 指数は最小ロット0.1
input int    MagicNumber = 20260670;

input group "=== ポジションサイジング（資産連動・複利） ==="
input bool   UseRiskSizing = false;    // ON: 資産連動でロットをスケール（複利）
input double RefDeposit    = 100000.0; // 基準資金

input group "=== 出力設定 ==="
input string ResultFileName = "";
input string EquityLogFile  = ""; // 全dealのtime,profitを書き出す（mt5bt portfolioでDD合算）

CTrade trade;
int    trendma_handle = INVALID_HANDLE;
int    entry_month    = -1;

//+------------------------------------------------------------------+
int OnInit()
{
    if(UseTrendFilter)
    {
        trendma_handle = iMA(_Symbol, PERIOD_CURRENT, TrendMA_Period, 0, TrendMA_Method, PRICE_CLOSE);
        if(trendma_handle == INVALID_HANDLE)
        {
            Print("MAハンドルの作成に失敗");
            return INIT_FAILED;
        }
    }
    trade.SetExpertMagicNumber(MagicNumber);
    trade.SetDeviationInPoints(20);
    Print("Seasonal(TOM) v1.0 起動 | ", _Symbol,
          " | 窓: 月末", DaysBeforeEnd, "営業日前〜新月第", DaysAfterStart, "営業日",
          " | TrendFilter=", UseTrendFilter ? "ON" : "OFF");
    return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
    if(trendma_handle != INVALID_HANDLE) IndicatorRelease(trendma_handle);
}

//+------------------------------------------------------------------+
//| 月の最終日（28/29/30/31）                                        |
//+------------------------------------------------------------------+
int LastDayOfMonth(int year, int mon)
{
    int days[] = {31,28,31,30,31,30,31,31,30,31,30,31};
    int d = days[mon-1];
    if(mon == 2 && ((year%4==0 && year%100!=0) || year%400==0)) d = 29;
    return d;
}

//+------------------------------------------------------------------+
//| 指定日付がその月で何営業日目か（Mon-Fri、1始まり）               |
//+------------------------------------------------------------------+
int BusinessDayOfMonth(int year, int mon, int day)
{
    int count = 0;
    for(int d = 1; d <= day; d++)
    {
        MqlDateTime x;
        x.year=year; x.mon=mon; x.day=d; x.hour=0; x.min=0; x.sec=0;
        datetime dt = StructToTime(x);
        MqlDateTime y; TimeToStruct(dt, y);
        if(y.day_of_week >= 1 && y.day_of_week <= 5) count++;
    }
    return count;
}

//+------------------------------------------------------------------+
//| 指定日付より後、月末までの営業日数（Mon-Fri）                    |
//+------------------------------------------------------------------+
int BusinessDaysToMonthEnd(int year, int mon, int day)
{
    int last = LastDayOfMonth(year, mon);
    int count = 0;
    for(int d = day+1; d <= last; d++)
    {
        MqlDateTime x;
        x.year=year; x.mon=mon; x.day=d; x.hour=0; x.min=0; x.sec=0;
        datetime dt = StructToTime(x);
        MqlDateTime y; TimeToStruct(dt, y);
        if(y.day_of_week >= 1 && y.day_of_week <= 5) count++;
    }
    return count;
}

//+------------------------------------------------------------------+
void OnTick()
{
    static datetime last_bar_time = 0;
    datetime current_bar_time = iTime(_Symbol, PERIOD_CURRENT, 0);
    if(current_bar_time == last_bar_time) return;
    last_bar_time = current_bar_time;

    MqlDateTime t;
    TimeToStruct(current_bar_time, t);
    if(t.day_of_week < 1 || t.day_of_week > 5) return; // 週末はスキップ

    int days_to_end  = BusinessDaysToMonthEnd(t.year, t.mon, t.day);
    int bday_of_mon  = BusinessDayOfMonth(t.year, t.mon, t.day);
    bool has_pos     = HasPosition();

    // トレンドフィルター（任意）
    bool trend_ok = true;
    if(UseTrendFilter)
    {
        double ma_buf[];
        ArraySetAsSeries(ma_buf, true);
        if(CopyBuffer(trendma_handle, 0, 1, 1, ma_buf) < 1) return;
        trend_ok = (iClose(_Symbol, PERIOD_CURRENT, 1) > ma_buf[0]);
    }

    // 決済: 新月（エントリー月と異なる）かつ第DaysAfterStart営業日に到達
    if(has_pos && t.mon != entry_month && bday_of_mon >= DaysAfterStart)
    {
        ClosePosition();
        entry_month = -1;
        return;
    }

    // エントリー: 月末の最終DaysBeforeEnd営業日（ロング限定）
    if(!has_pos && days_to_end <= (DaysBeforeEnd - 1) && trend_ok)
    {
        double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
        if(trade.Buy(CalcLot(), _Symbol, ask, 0, 0, "TOM"))
            entry_month = t.mon;
    }
}

//+------------------------------------------------------------------+
double CalcLot()
{
    double lot = LotSize;
    if(UseRiskSizing)
    {
        double equity = AccountInfoDouble(ACCOUNT_EQUITY);
        double refDep = (RefDeposit > 0.0) ? RefDeposit : 100000.0;
        lot = LotSize * (equity / refDep);
    }
    double minLot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
    double maxLot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
    double stepLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
    if(stepLot > 0.0) lot = MathFloor(lot / stepLot) * stepLot;
    lot = MathMax(minLot, MathMin(maxLot, lot));
    return lot;
}

//+------------------------------------------------------------------+
bool HasPosition()
{
    for(int i = PositionsTotal() - 1; i >= 0; i--)
        if(PositionGetSymbol(i) == _Symbol &&
           PositionGetInteger(POSITION_MAGIC) == MagicNumber)
            return true;
    return false;
}

//+------------------------------------------------------------------+
void ClosePosition()
{
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        ulong ticket = PositionGetTicket(i);
        if(PositionGetInteger(POSITION_MAGIC) == MagicNumber &&
           PositionGetString(POSITION_SYMBOL) == _Symbol)
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
    return pf;
}
//+------------------------------------------------------------------+

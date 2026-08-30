//+------------------------------------------------------------------+
//|  GoldSeason.mq5                                                  |
//|  GOLD 月別シーズナリティ EA v1.0                                  |
//|  金の実物需要サイクル(インド婚礼/祭礼9-11月・春節1-2月・年末     |
//|  ジュエリー需要)で季節的に強い月だけロング。価格パターンに依存   |
//|  しないカレンダー駆動=既存トレンド戦略と無相関を狙う別軸。       |
//|  documented窓: 8月ロング→3月決済(8-2月が強・3-7月が弱)。         |
//|  破綻回避にワイドATRストップ。                                    |
//+------------------------------------------------------------------+
#property copyright "2026"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>

input group "=== 季節窓（強い月にロング）==="
input int    EnterMonth = 8;   // この月の最初の足でロング（既定8月）
input int    ExitMonth  = 3;   // この月の最初の足で決済（既定3月）＝8-2月保有

input group "=== ストップ（破綻回避のワイドATR）==="
input bool   UseATRStop  = true;
input int    ATR_Period  = 14;
input double ATR_SL_Mult = 4.0;

input group "=== トレード設定 ==="
input double LotSize     = 0.01;
input int    MagicNumber = 20260750;

input group "=== ポジションサイジング ==="
input bool   UseRiskSizing = false;
input double RiskPercent   = 2.0;

input group "=== 出力設定 ==="
input string ResultFileName = "";
input string EquityLogFile  = "";

CTrade trade;
int    atr_handle = INVALID_HANDLE;

//+------------------------------------------------------------------+
int OnInit()
{
    atr_handle = iATR(_Symbol, PERIOD_CURRENT, ATR_Period);
    if(atr_handle == INVALID_HANDLE) { Print("ATRハンドル作成失敗"); return INIT_FAILED; }
    trade.SetExpertMagicNumber(MagicNumber);
    trade.SetDeviationInPoints(20);
    Print("GoldSeason v1.0 起動 | ", _Symbol, " | ロング窓: ", EnterMonth, "月→", ExitMonth, "月",
          " | ATRストップ=", UseATRStop ? StringFormat("ON(x%.1f)", ATR_SL_Mult) : "OFF");
    return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason) { if(atr_handle != INVALID_HANDLE) IndicatorRelease(atr_handle); }

//+------------------------------------------------------------------+
// 月mが季節窓内か（EnterMonth..ExitMonthの手前まで、年跨ぎ対応）
bool InSeason(int m)
{
    if(EnterMonth <= ExitMonth) return (m >= EnterMonth && m < ExitMonth);
    return (m >= EnterMonth || m < ExitMonth); // 年跨ぎ（例8→3）
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
    bool in_season = InSeason(t.mon);
    bool has_pos   = HasPosition();

    double atr_buf[];
    ArraySetAsSeries(atr_buf, true);
    if(CopyBuffer(atr_handle, 0, 1, 1, atr_buf) < 1) return;
    double atr1 = atr_buf[0];

    // エントリー: 季節窓入り かつ 未保有 → GOLDロング
    if(in_season && !has_pos)
    {
        double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
        double sl  = (UseATRStop && atr1 > 0.0) ? ask - ATR_SL_Mult * atr1 : 0.0;
        double risk = (sl > 0.0) ? ask - sl : 0.0;
        trade.Buy(CalcLot(risk), _Symbol, ask,
                  (sl > 0.0 ? NormalizeDouble(sl, _Digits) : 0.0), 0, "GoldSeason");
    }
    // 決済: 季節窓終了
    else if(!in_season && has_pos)
    {
        ClosePosition();
    }
}

//+------------------------------------------------------------------+
double CalcLot(double risk_dist)
{
    if(!UseRiskSizing || risk_dist <= 0.0) return LotSize;
    double equity   = AccountInfoDouble(ACCOUNT_EQUITY);
    double risk_amt = equity * RiskPercent / 100.0;
    double tick_val = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
    double tick_sz  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
    if(tick_val <= 0.0 || tick_sz <= 0.0) return LotSize;
    double loss_per_lot = (risk_dist / tick_sz) * tick_val;
    if(loss_per_lot <= 0.0) return LotSize;
    double lot = risk_amt / loss_per_lot;
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

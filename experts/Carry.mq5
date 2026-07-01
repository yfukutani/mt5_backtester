//+------------------------------------------------------------------+
//|  Carry.mq5                                                       |
//|  キャリートレード（スワップ収集）EA v1.0                         |
//|  D1のMA200上で買い長期保有、割れで決済。スワップ＋順張りを取る。 |
//|  ⚠️ MT5テスターは現在スワップ率を全履歴に適用するため、スワップ  |
//|     収益のバックテストは近似。スポットP&Lは正確。               |
//+------------------------------------------------------------------+
#property copyright "2026"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>

input group "=== トレンド判定 ==="
input int            TrendMA_Period = 200;       // 大局トレンドMA（この上で買い保有）
input ENUM_MA_METHOD TrendMA_Method = MODE_SMA;
// トレンド判定の時間足。既定 PERIOD_CURRENT＝チャートTF（XM検証はD1チャートで不変）。
// 執行はチャートTFの新バーで行うため、判定D1・執行H1のように分離できる。
// OANDA-Japanサーバーは D1始値(00:00) の成行が "market closed" で失敗するため、
// チャートをH1にし SignalTimeframe=D1(PERIOD_D1) にすると市場開場中の時刻で約定できる。
input ENUM_TIMEFRAMES SignalTimeframe = PERIOD_CURRENT;

input group "=== キャリー条件 ==="
input bool   RequirePositiveSwap = true;  // ロングスワップが正（キャリー有利）のときのみ保有

input group "=== トレード設定 ==="
input double LotSize     = 0.01;
input int    MagicNumber = 20260650;

input group "=== ポジションサイジング（資産連動・複利） ==="
input bool   UseRiskSizing = false;    // ON: 資産連動でロットをスケール（複利）
input double RefDeposit    = 100000.0; // 基準資金

input group "=== 出力設定 ==="
input string ResultFileName = "";
input string EquityLogFile  = ""; // 全dealのtime,profitを書き出す（mt5bt portfolioでDD合算）

CTrade trade;
int    trendma_handle;

//+------------------------------------------------------------------+
int OnInit()
{
    trendma_handle = iMA(_Symbol, SignalTimeframe, TrendMA_Period, 0, TrendMA_Method, PRICE_CLOSE);
    if(trendma_handle == INVALID_HANDLE)
    {
        Print("MAハンドルの作成に失敗");
        return INIT_FAILED;
    }
    trade.SetExpertMagicNumber(MagicNumber);
    trade.SetDeviationInPoints(20);
    Print("Carry v1.0 起動 | ", _Symbol, " MA", TrendMA_Period,
          " | PositiveSwapOnly=", RequirePositiveSwap ? "ON" : "OFF");
    return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason) { IndicatorRelease(trendma_handle); }

//+------------------------------------------------------------------+
void OnTick()
{
    static datetime last_bar_time = 0;
    datetime current_bar_time = iTime(_Symbol, PERIOD_CURRENT, 0);
    if(current_bar_time == last_bar_time) return;
    last_bar_time = current_bar_time;

    double ma_buf[];
    ArraySetAsSeries(ma_buf, true);
    if(CopyBuffer(trendma_handle, 0, 1, 1, ma_buf) < 1) return;
    double ma200 = ma_buf[0];
    double close_prev = iClose(_Symbol, SignalTimeframe, 1);

    bool has_pos = HasPosition();

    // スワップ条件（現在のロングスワップが正か）
    bool swap_ok = !RequirePositiveSwap || (SymbolInfoDouble(_Symbol, SYMBOL_SWAP_LONG) > 0.0);

    // エントリー: MA200上 + キャリー有利 → 買い長期保有（SL/TPなし、MA割れで決済）
    if(close_prev > ma200 && swap_ok && !has_pos)
    {
        double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
        if(trade.Buy(CalcLot(), _Symbol, ask, 0, 0, "Carry"))
            Print("[CARRY BUY] close=", close_prev, " ma200=", DoubleToString(ma200, _Digits),
                  " swapLong=", DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_SWAP_LONG), 2));
    }
    // 決済: MA200割れ（トレンド崩れ＝リスクオフ回避）
    else if(close_prev < ma200 && has_pos)
    {
        ClosePosition();
        Print("[CARRY EXIT] close=", close_prev, " ma200=", DoubleToString(ma200, _Digits));
    }
}

//+------------------------------------------------------------------+
double CalcLot()
{
    if(!UseRiskSizing) return LotSize;
    double equity = AccountInfoDouble(ACCOUNT_EQUITY);
    double refDep = (RefDeposit > 0.0) ? RefDeposit : 100000.0;
    double lot    = LotSize * (equity / refDep);
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

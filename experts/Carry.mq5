//+------------------------------------------------------------------+
//|  Carry.mq5                                                       |
//|  キャリートレード（スワップ収集）EA v1.0                         |
//|  D1のMA200上で買い長期保有、割れで決済。スワップ＋順張りを取る。 |
//|  ⚠️ MT5テスターは現在スワップ率を全履歴に適用するため、スワップ  |
//|     収益のバックテストは近似。スポットP&Lは正確。               |
//+------------------------------------------------------------------+
#property copyright "2026"
#property version   "1.20"
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

input group "=== MAクロス・ヒステリシス帯（往復ビンタ削減） ==="
// entry: close > MA+b×ATR / exit: close < MA−b×ATR に非対称化し、MA200付近のチョップによる
// 「高値で買い→浅い割れで損切り」の往復損失を削減する。AUDJPYで採用(b=0.75)、ETHは不採用（既定OFF）。
// 検証: 全期間 +177,524→+209,966 / DD30.49%→24.17% / every_tick +149,032→+238,486（docs/carry.md）。
input bool   UseHysteresis  = false;
input int    ATR_Period     = 14;
input double Hyst_ATR_Mult  = 0.75;  // 帯の半幅（×ATR）

input group "=== デュアルMA退出（BTC v1.2・A2） ==="
// >0で退出線を分離: entry=TrendMA上かつExitMA上 / exit=ExitMA割れ（TrendMA割れを待たない）。
// 2018年型の深い暴落を早期退出で回避する狙い（BTC検証用・ヒステリシスとは併用不可）。
input int    ExitMA_Period  = 0;

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
int    atr_handle = INVALID_HANDLE;
int    exitma_handle = INVALID_HANDLE;

//+------------------------------------------------------------------+
int OnInit()
{
    trendma_handle = iMA(_Symbol, SignalTimeframe, TrendMA_Period, 0, TrendMA_Method, PRICE_CLOSE);
    if(trendma_handle == INVALID_HANDLE)
    {
        Print("MAハンドルの作成に失敗");
        return INIT_FAILED;
    }
    if(UseHysteresis)
    {
        atr_handle = iATR(_Symbol, SignalTimeframe, ATR_Period);
        if(atr_handle == INVALID_HANDLE) { Print("ATRハンドルの作成に失敗"); return INIT_FAILED; }
    }
    if(ExitMA_Period > 0)
    {
        exitma_handle = iMA(_Symbol, SignalTimeframe, ExitMA_Period, 0, TrendMA_Method, PRICE_CLOSE);
        if(exitma_handle == INVALID_HANDLE) { Print("ExitMAハンドルの作成に失敗"); return INIT_FAILED; }
    }
    trade.SetExpertMagicNumber(MagicNumber);
    trade.SetDeviationInPoints(20);
    Print("Carry v1.2 起動 | ", _Symbol, " MA", TrendMA_Period,
          " | PositiveSwapOnly=", RequirePositiveSwap ? "ON" : "OFF",
          " | Hyst=", UseHysteresis ? StringFormat("ON(±%.2fATR)", Hyst_ATR_Mult) : "OFF",
          " | ExitMA=", ExitMA_Period > 0 ? IntegerToString(ExitMA_Period) : "OFF");
    return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
    IndicatorRelease(trendma_handle);
    if(atr_handle != INVALID_HANDLE) IndicatorRelease(atr_handle);
    if(exitma_handle != INVALID_HANDLE) IndicatorRelease(exitma_handle);
}

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

    // ヒステリシス帯: entry閾値=MA+b×ATR / exit閾値=MA−b×ATR（OFF時は両方MA200のまま）
    double entry_th = ma200, exit_th = ma200;
    if(UseHysteresis)
    {
        double atr_buf[];
        ArraySetAsSeries(atr_buf, true);
        if(CopyBuffer(atr_handle, 0, 1, 1, atr_buf) < 1) return;
        entry_th = ma200 + Hyst_ATR_Mult * atr_buf[0];
        exit_th  = ma200 - Hyst_ATR_Mult * atr_buf[0];
    }
    // A2デュアルMA: entry=TrendMA上かつExitMA上 / exit=ExitMA割れ（早期退出）
    if(ExitMA_Period > 0)
    {
        double ex_buf[];
        ArraySetAsSeries(ex_buf, true);
        if(CopyBuffer(exitma_handle, 0, 1, 1, ex_buf) < 1) return;
        entry_th = MathMax(ma200, ex_buf[0]);
        exit_th  = ex_buf[0];
    }

    // エントリー: 帯の上抜け + キャリー有利 → 買い長期保有（SL/TPなし、帯の下割れで決済）
    if(close_prev > entry_th && swap_ok && !has_pos)
    {
        double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
        if(trade.Buy(CalcLot(), _Symbol, ask, 0, 0, "Carry"))
            Print("[CARRY BUY] close=", close_prev, " ma200=", DoubleToString(ma200, _Digits),
                  " swapLong=", DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_SWAP_LONG), 2));
    }
    // 決済: 帯の下割れ（トレンド崩れ＝リスクオフ回避）
    else if(close_prev < exit_th && has_pos)
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

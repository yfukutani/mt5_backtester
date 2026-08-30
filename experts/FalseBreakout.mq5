//+------------------------------------------------------------------+
//|  FalseBreakout.mq5                                               |
//|  偽ブレイク・フェード EA v1.0（レンジ反転・別軸）                |
//|  Donchianレンジを一旦ブレイクしたが定着せず内側に戻った(=偽    |
//|  ブレイク)バーを検出し、逆方向にフェードする。VolBreakoutが      |
//|  「取る」ブレイクの失敗側を取る＝構造的に負相関を狙う収益源。   |
//|  ストップは偽ブレイクの極値の外側(構造ベース)、TPはRR比。       |
//+------------------------------------------------------------------+
#property copyright "2026"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>

input group "=== レンジ・偽ブレイク判定 ==="
input int    Channel_Period = 20;     // Donchianレンジ本数（直近高安）
input double Pierce_Min_ATR = 0.5;    // ブレイク深度がこの×ATR以上で「意味ある偽ブレイク」（ノイズ除去）
input bool   AllowLong      = true;   // 偽ブレイクダウン→買い
input bool   AllowShort     = true;   // 偽ブレイクアップ→売り

input group "=== ストップ／利確 ==="
input int    ATR_Period     = 14;
input double SL_Buffer_ATR  = 0.2;    // 偽ブレイク極値の外側に置くバッファ（×ATR）
input double RR_Ratio       = 1.5;    // TP = リスク × RR

input group "=== トレード設定 ==="
input double LotSize     = 0.01;
input int    MagicNumber = 20260690;

input group "=== ポジションサイジング ==="
input bool   UseRiskSizing = false;
input double RiskPercent   = 2.0;

input group "=== 出力設定 ==="
input string ResultFileName = "";
input string EquityLogFile  = "";

CTrade trade;
int    atr_handle;

//+------------------------------------------------------------------+
int OnInit()
{
    atr_handle = iATR(_Symbol, PERIOD_CURRENT, ATR_Period);
    if(atr_handle == INVALID_HANDLE) { Print("ATRハンドル作成失敗"); return INIT_FAILED; }
    trade.SetExpertMagicNumber(MagicNumber);
    trade.SetDeviationInPoints(20);
    Print("FalseBreakout v1.0 起動 | ", _Symbol, " ch=", Channel_Period,
          " SLbuf=", SL_Buffer_ATR, "ATR RR=", RR_Ratio);
    return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason) { IndicatorRelease(atr_handle); }

//+------------------------------------------------------------------+
void OnTick()
{
    static datetime last_bar_time = 0;
    datetime current_bar_time = iTime(_Symbol, PERIOD_CURRENT, 0);
    if(current_bar_time == last_bar_time) return;
    last_bar_time = current_bar_time;

    if(HasPosition()) return;

    double atr_buf[];
    ArraySetAsSeries(atr_buf, true);
    if(CopyBuffer(atr_handle, 0, 1, 1, atr_buf) < 1) return;
    double atr1 = atr_buf[0];
    if(atr1 <= 0.0) return;

    // Donchian高安（確定足 shift=2..Channel_Period+1、判定足shift=1は除外）
    double hh = -DBL_MAX, ll = DBL_MAX;
    for(int s = 2; s <= Channel_Period + 1; s++)
    {
        double h = iHigh(_Symbol, PERIOD_CURRENT, s);
        double l = iLow(_Symbol, PERIOD_CURRENT, s);
        if(h > hh) hh = h;
        if(l < ll) ll = l;
    }

    double high1  = iHigh(_Symbol, PERIOD_CURRENT, 1);
    double low1   = iLow(_Symbol, PERIOD_CURRENT, 1);
    double close1 = iClose(_Symbol, PERIOD_CURRENT, 1);

    // 偽ブレイクダウン: 安値がレンジ下限を「意味ある深さ」割ったが終値は内側に戻った → 買い
    bool failed_down = ((ll - low1) >= Pierce_Min_ATR * atr1) && (close1 > ll);
    // 偽ブレイクアップ: 高値がレンジ上限を「意味ある深さ」超えたが終値は内側に戻った → 売り
    bool failed_up   = ((high1 - hh) >= Pierce_Min_ATR * atr1) && (close1 < hh);

    if(AllowLong && failed_down)
    {
        double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
        double sl  = low1 - SL_Buffer_ATR * atr1;
        double risk = ask - sl;
        if(risk <= 0.0) return;
        double tp  = ask + RR_Ratio * risk;
        trade.Buy(CalcLot(risk), _Symbol, ask,
                  NormalizeDouble(sl, _Digits), NormalizeDouble(tp, _Digits), "FBO-L");
    }
    else if(AllowShort && failed_up)
    {
        double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
        double sl  = high1 + SL_Buffer_ATR * atr1;
        double risk = sl - bid;
        if(risk <= 0.0) return;
        double tp  = bid - RR_Ratio * risk;
        trade.Sell(CalcLot(risk), _Symbol, bid,
                   NormalizeDouble(sl, _Digits), NormalizeDouble(tp, _Digits), "FBO-S");
    }
}

//+------------------------------------------------------------------+
double CalcLot(double risk_dist)
{
    if(!UseRiskSizing) return LotSize;
    double equity   = AccountInfoDouble(ACCOUNT_EQUITY);
    double risk_amt = equity * RiskPercent / 100.0;
    double tick_val = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
    double tick_sz  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
    if(risk_dist <= 0.0 || tick_val <= 0.0 || tick_sz <= 0.0) return LotSize;
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

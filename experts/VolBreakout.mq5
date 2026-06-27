//+------------------------------------------------------------------+
//|  VolBreakout.mq5                                                 |
//|  ボラ・スクイーズ・ブレイクアウト EA v1.0（クライシスアルファ）  |
//|  ボラ圧縮(スクイーズ)後のDonchianブレイクを両方向で取り、ATR     |
//|  チャンデリア・トレーリングで利を伸ばす。多数の小損＋稀な大勝＝  |
//|  正スキュー。危機/レジーム転換のボラ膨張で大きく取る別軸収益源。 |
//|  既存の負スキュー群(RSI/Pair/Carry)が出血する局面のテールヘッジ。|
//+------------------------------------------------------------------+
#property copyright "2026"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>

input group "=== ブレイクアウト ==="
input int    Channel_Period  = 20;     // Donchianチャネル本数（直近高安）
input bool   AllowLong       = true;
input bool   AllowShort      = true;

input group "=== スクイーズ・フィルター ==="
input bool   UseSqueezeFilter = true;  // ON: ボラ圧縮後のブレイクのみ
input int    Squeeze_Lookback = 50;    // ATR平均の参照本数
input double Squeeze_Factor   = 1.0;   // ATR[1] < Factor×平均ATR で圧縮と判定

input group "=== ストップ ==="
input int    ATR_Period   = 14;
input double ATR_SL_Mult  = 2.0;       // 初期ストップ距離（×ATR）
input double Trail_Mult    = 3.0;      // トレーリング距離（×ATR、利を伸ばす）

input group "=== トレード設定 ==="
input double LotSize     = 0.01;
input int    MagicNumber = 20260680;

input group "=== ポジションサイジング（リスク%・正スキューはレバレッジ耐性あり） ==="
input bool   UseRiskSizing = false;    // ON: 1取引リスク=equity×RiskPercent%
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
    Print("VolBreakout v1.0 起動 | ", _Symbol, " ch=", Channel_Period,
          " squeeze=", UseSqueezeFilter ? StringFormat("ON(<%.1f×avg)", Squeeze_Factor) : "OFF",
          " SL=", ATR_SL_Mult, "ATR trail=", Trail_Mult, "ATR");
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

    int need = Squeeze_Lookback + 2;
    double atr_buf[];
    ArraySetAsSeries(atr_buf, true);
    if(CopyBuffer(atr_handle, 0, 1, need, atr_buf) < need) return;
    double atr1 = atr_buf[0];
    if(atr1 <= 0.0) return;

    // スクイーズ判定: 直近ATRがその平均より低い＝ボラ圧縮
    double avg_atr = 0.0;
    for(int i = 0; i < Squeeze_Lookback; i++) avg_atr += atr_buf[i];
    avg_atr /= Squeeze_Lookback;
    bool squeeze_ok = !UseSqueezeFilter || (atr1 < Squeeze_Factor * avg_atr);

    double close1 = iClose(_Symbol, PERIOD_CURRENT, 1);

    if(!HasPosition())
    {
        // Donchian高安（直近Channel_Period本の確定足 shift=2..Channel_Period+1、ブレイク足shift=1は除外）
        double hh = -DBL_MAX, ll = DBL_MAX;
        for(int s = 2; s <= Channel_Period + 1; s++)
        {
            double h = iHigh(_Symbol, PERIOD_CURRENT, s);
            double l = iLow(_Symbol, PERIOD_CURRENT, s);
            if(h > hh) hh = h;
            if(l < ll) ll = l;
        }

        if(squeeze_ok && AllowLong && close1 > hh)
        {
            double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
            double sl  = ask - ATR_SL_Mult * atr1;
            trade.Buy(CalcLot(atr1), _Symbol, ask, sl, 0, "VBO-L");
        }
        else if(squeeze_ok && AllowShort && close1 < ll)
        {
            double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
            double sl  = bid + ATR_SL_Mult * atr1;
            trade.Sell(CalcLot(atr1), _Symbol, bid, sl, 0, "VBO-S");
        }
    }
    else
    {
        // チャンデリア・トレーリング（利を伸ばす＝正スキュー）
        TrailStop(close1, atr1);
    }
}

//+------------------------------------------------------------------+
void TrailStop(double close1, double atr1)
{
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        ulong ticket = PositionGetTicket(i);
        if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
        if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;

        long   type = PositionGetInteger(POSITION_TYPE);
        double cur_sl = PositionGetDouble(POSITION_SL);
        double open_p = PositionGetDouble(POSITION_PRICE_OPEN);

        if(type == POSITION_TYPE_BUY)
        {
            double new_sl = close1 - Trail_Mult * atr1;
            if(new_sl > cur_sl && new_sl < close1)
                trade.PositionModify(ticket, NormalizeDouble(new_sl, _Digits), 0);
        }
        else if(type == POSITION_TYPE_SELL)
        {
            double new_sl = close1 + Trail_Mult * atr1;
            if((cur_sl == 0.0 || new_sl < cur_sl) && new_sl > close1)
                trade.PositionModify(ticket, NormalizeDouble(new_sl, _Digits), 0);
        }
    }
}

//+------------------------------------------------------------------+
double CalcLot(double atr1)
{
    if(!UseRiskSizing) return LotSize;
    double equity   = AccountInfoDouble(ACCOUNT_EQUITY);
    double risk_amt = equity * RiskPercent / 100.0;
    double sl_dist  = ATR_SL_Mult * atr1;
    double tick_val = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
    double tick_sz  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
    if(sl_dist <= 0.0 || tick_val <= 0.0 || tick_sz <= 0.0) return LotSize;
    double loss_per_lot = (sl_dist / tick_sz) * tick_val;
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

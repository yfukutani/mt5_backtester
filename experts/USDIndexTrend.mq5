//+------------------------------------------------------------------+
//|  USDIndexTrend.mq5                                               |
//|  USD Index合成トレンドEA v1.0（新規戦略候補#19）                 |
//|  複数USDペア(EURUSD/GBPUSD/USDCHF/USDJPY)のATR正規化モメンタムを |
//|  USD視点で符号を揃えて合成し、合成USD強弱のトレンドでUSDJPYを取る|
//|  （単一ペアのノイズより合成指数の方が頑健という仮説の検証）。    |
//+------------------------------------------------------------------+
#property copyright "2026"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>

input group "=== 合成USD指数 ==="
input int    Momentum_Period = 20;   // モメンタム測定期間（バー数）
input int    ATR_Period      = 14;
input double USD_Min_Strength = 1.0; // 合成USD強弱の最小閾値（ATR単位平均）

input group "=== 取引銘柄 ==="
input string TradeSymbol = "USDJPY"; // 実際にポジションを取る銘柄

input group "=== ストップ ==="
input double ATR_SL_Mult = 2.0;
input double RR_Ratio    = 2.0;

input group "=== トレード設定 ==="
input double LotSize     = 0.01;
input int    MagicNumber = 20260970;

input group "=== 出力設定 ==="
input string ResultFileName = "";
input string EquityLogFile  = "";

CTrade trade;
int hATR_EUR, hATR_GBP, hATR_CHF, hATR_JPY;
datetime g_lastBar = 0;

//+------------------------------------------------------------------+
int OnInit()
{
    SymbolSelect("EURUSD", true);
    SymbolSelect("GBPUSD", true);
    SymbolSelect("USDCHF", true);
    SymbolSelect("USDJPY", true);
    hATR_EUR = iATR("EURUSD", PERIOD_CURRENT, ATR_Period);
    hATR_GBP = iATR("GBPUSD", PERIOD_CURRENT, ATR_Period);
    hATR_CHF = iATR("USDCHF", PERIOD_CURRENT, ATR_Period);
    hATR_JPY = iATR("USDJPY", PERIOD_CURRENT, ATR_Period);
    if(hATR_EUR==INVALID_HANDLE||hATR_GBP==INVALID_HANDLE||hATR_CHF==INVALID_HANDLE||hATR_JPY==INVALID_HANDLE)
    {
        Print("ATRハンドル作成失敗");
        return INIT_FAILED;
    }
    trade.SetExpertMagicNumber(MagicNumber);
    trade.SetDeviationInPoints(10);
    Print("USDIndexTrend v1.0 起動 | TradeSymbol=", TradeSymbol, " MomPeriod=", Momentum_Period);
    return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
    IndicatorRelease(hATR_EUR); IndicatorRelease(hATR_GBP);
    IndicatorRelease(hATR_CHF); IndicatorRelease(hATR_JPY);
}

//+------------------------------------------------------------------+
double NormMomentum(string sym, int hATR)
{
    double atrBuf[];
    ArraySetAsSeries(atrBuf, true);
    if(CopyBuffer(hATR, 0, 1, 1, atrBuf) < 1) return 0;
    double atr = atrBuf[0];
    if(atr <= 0) return 0;
    double closeNow  = iClose(sym, PERIOD_CURRENT, 1);
    double closePast = iClose(sym, PERIOD_CURRENT, Momentum_Period + 1);
    if(closeNow == 0 || closePast == 0) return 0;
    return (closeNow - closePast) / atr;
}

//+------------------------------------------------------------------+
bool HasPosition(ENUM_POSITION_TYPE type)
{
    for(int i = PositionsTotal() - 1; i >= 0; i--)
        if(PositionGetSymbol(i) == TradeSymbol &&
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
        if(PositionGetSymbol(i) == TradeSymbol &&
           PositionGetInteger(POSITION_MAGIC) == MagicNumber &&
           PositionGetInteger(POSITION_TYPE)  == type)
            trade.PositionClose(ticket);
    }
}

//+------------------------------------------------------------------+
void OnTick()
{
    datetime bt = iTime(TradeSymbol, PERIOD_CURRENT, 0);
    if(bt == 0 || bt == g_lastBar) return;
    g_lastBar = bt;

    // USD視点で符号を揃えて合成: EUR/GBPはUSDがクオート通貨→USD高で下落(符号反転)
    // USDCHF/USDJPYはUSDがベース通貨→USD高で上昇(符号そのまま)
    double momEUR = NormMomentum("EURUSD", hATR_EUR);
    double momGBP = NormMomentum("GBPUSD", hATR_GBP);
    double momCHF = NormMomentum("USDCHF", hATR_CHF);
    double momJPY = NormMomentum("USDJPY", hATR_JPY);
    double usdStrength = (-momEUR - momGBP + momCHF + momJPY) / 4.0;

    bool longUSD  = (usdStrength >=  USD_Min_Strength);
    bool shortUSD = (usdStrength <= -USD_Min_Strength);

    double atrBuf[];
    ArraySetAsSeries(atrBuf, true);
    if(CopyBuffer(hATR_JPY, 0, 1, 1, atrBuf) < 1) return;
    double atr = atrBuf[0];
    if(atr <= 0) return;
    double sl_dist = atr * ATR_SL_Mult;
    double tp_dist = sl_dist * RR_Ratio;
    int digits = (int)SymbolInfoInteger(TradeSymbol, SYMBOL_DIGITS);

    bool hasBuy  = HasPosition(POSITION_TYPE_BUY);
    bool hasSell = HasPosition(POSITION_TYPE_SELL);

    trade.SetExpertMagicNumber(MagicNumber);
    if(longUSD && !hasBuy)
    {
        if(hasSell) ClosePositions(POSITION_TYPE_SELL);
        double ask = SymbolInfoDouble(TradeSymbol, SYMBOL_ASK);
        double sl = NormalizeDouble(ask - sl_dist, digits);
        double tp = NormalizeDouble(ask + tp_dist, digits);
        trade.Buy(LotSize, TradeSymbol, ask, sl, tp, "USDIdx-L");
    }
    else if(shortUSD && !hasSell)
    {
        if(hasBuy) ClosePositions(POSITION_TYPE_BUY);
        double bid = SymbolInfoDouble(TradeSymbol, SYMBOL_BID);
        double sl = NormalizeDouble(bid + sl_dist, digits);
        double tp = NormalizeDouble(bid - tp_dist, digits);
        trade.Sell(LotSize, TradeSymbol, bid, sl, tp, "USDIdx-S");
    }
    else if(!longUSD && !shortUSD)
    {
        if(hasBuy)  ClosePositions(POSITION_TYPE_BUY);
        if(hasSell) ClosePositions(POSITION_TYPE_SELL);
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

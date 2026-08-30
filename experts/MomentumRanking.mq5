//+------------------------------------------------------------------+
//|  MomentumRanking.mq5                                             |
//|  モメンタム・ランキング バスケットEA v1.0（新規戦略候補#13）     |
//|  複数FXペアのモメンタムを比較し、最も強いペアのみ順張りで取る。  |
//|  銘柄選択自体をアルファ源とする発想（既存は固定銘柄決め打ち）。  |
//+------------------------------------------------------------------+
#property copyright "2026"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>

input group "=== 対象バスケット ==="
input string Symbols        = "USDJPY,EURUSD,GBPUSD,AUDJPY,EURJPY,GBPJPY"; // カンマ区切り銘柄リスト
input int    Momentum_Period = 20;  // モメンタム測定期間（バー数）
input int    ATR_Period      = 14;

input group "=== エントリー ==="
input double Momentum_Min_ATR = 1.0;  // 最小モメンタム閾値（ATR倍率）。これ未満なら不稼働
input double ATR_SL_Mult      = 2.0;
input double RR_Ratio         = 2.0;

input group "=== トレード設定 ==="
input double LotSize     = 0.01;
input int    MagicNumber = 20260910;

input group "=== 出力設定 ==="
input string ResultFileName = "";
input string EquityLogFile  = "";

CTrade trade;
string  g_symbols[];
int     g_n = 0;
int     g_hATR[];
datetime g_lastBar = 0;
string   g_curSymbol = "";

//+------------------------------------------------------------------+
int OnInit()
{
    g_n = StringSplit(Symbols, ',', g_symbols);
    ArrayResize(g_hATR, g_n);
    for(int i = 0; i < g_n; i++)
    {
        SymbolSelect(g_symbols[i], true);
        g_hATR[i] = iATR(g_symbols[i], PERIOD_CURRENT, ATR_Period);
        if(g_hATR[i] == INVALID_HANDLE)
        {
            Print("ATRハンドル作成失敗: ", g_symbols[i]);
            return INIT_FAILED;
        }
    }
    trade.SetExpertMagicNumber(MagicNumber);
    trade.SetDeviationInPoints(10);
    Print("MomentumRanking v1.0 起動 | 銘柄数=", g_n, " | MomentumPeriod=", Momentum_Period);
    return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
    for(int i = 0; i < g_n; i++)
        if(g_hATR[i] != INVALID_HANDLE) IndicatorRelease(g_hATR[i]);
}

//+------------------------------------------------------------------+
bool HasPosition(string sym, ENUM_POSITION_TYPE type)
{
    for(int i = PositionsTotal() - 1; i >= 0; i--)
        if(PositionGetSymbol(i) == sym &&
           PositionGetInteger(POSITION_MAGIC) == MagicNumber &&
           PositionGetInteger(POSITION_TYPE)  == type)
            return true;
    return false;
}

void CloseAllPositions()
{
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        ulong ticket = PositionGetTicket(i);
        if(PositionGetInteger(POSITION_MAGIC) == MagicNumber)
            trade.PositionClose(ticket);
    }
}

//+------------------------------------------------------------------+
void OnTick()
{
    // 新バー検出（先頭銘柄のチャートTFを基準に判定。全銘柄同一TF前提）
    datetime bt = iTime(g_symbols[0], PERIOD_CURRENT, 0);
    if(bt == 0 || bt == g_lastBar) return;
    g_lastBar = bt;

    // 各銘柄のモメンタムスコア（ATR正規化リターン）を計算
    double bestScore = 0;
    string bestSym = "";
    int    bestDir = 0; // 1=買い, -1=売り

    for(int i = 0; i < g_n; i++)
    {
        string sym = g_symbols[i];
        double atrBuf[];
        ArraySetAsSeries(atrBuf, true);
        if(CopyBuffer(g_hATR[i], 0, 1, 1, atrBuf) < 1) continue;
        double atr = atrBuf[0];
        if(atr <= 0) continue;

        double closeNow  = iClose(sym, PERIOD_CURRENT, 1);
        double closePast = iClose(sym, PERIOD_CURRENT, Momentum_Period + 1);
        if(closeNow == 0 || closePast == 0) continue;

        double momentum = (closeNow - closePast) / atr; // ATR単位の変化量
        double score = MathAbs(momentum);
        if(score > bestScore)
        {
            bestScore = score;
            bestSym   = sym;
            bestDir   = (momentum > 0) ? 1 : -1;
        }
    }

    bool qualifies = (bestScore >= Momentum_Min_ATR) && (bestSym != "");

    // 現在保有中のポジションが「今回のベスト銘柄・方向」と違えば入れ替え
    bool needSwitch = false;
    if(g_curSymbol != "" && (!qualifies || g_curSymbol != bestSym))
        needSwitch = true;
    if(!qualifies)
    {
        if(g_curSymbol != "") { CloseAllPositions(); g_curSymbol = ""; }
        return;
    }
    if(needSwitch)
    {
        CloseAllPositions();
        g_curSymbol = "";
    }

    bool hasBuy  = HasPosition(bestSym, POSITION_TYPE_BUY);
    bool hasSell = HasPosition(bestSym, POSITION_TYPE_SELL);
    if((bestDir == 1 && hasBuy) || (bestDir == -1 && hasSell))
    {
        g_curSymbol = bestSym;
        return; // 既にベスト銘柄・方向で保有中
    }

    // 新規エントリー
    double atrBuf2[];
    ArraySetAsSeries(atrBuf2, true);
    int idx = -1;
    for(int i = 0; i < g_n; i++) if(g_symbols[i] == bestSym) { idx = i; break; }
    if(idx < 0 || CopyBuffer(g_hATR[idx], 0, 1, 1, atrBuf2) < 1) return;
    double atr = atrBuf2[0];
    double sl_dist = atr * ATR_SL_Mult;
    double tp_dist = sl_dist * RR_Ratio;
    int digits = (int)SymbolInfoInteger(bestSym, SYMBOL_DIGITS);

    trade.SetExpertMagicNumber(MagicNumber);
    if(bestDir == 1)
    {
        double ask = SymbolInfoDouble(bestSym, SYMBOL_ASK);
        double sl = NormalizeDouble(ask - sl_dist, digits);
        double tp = NormalizeDouble(ask + tp_dist, digits);
        if(trade.Buy(LotSize, bestSym, ask, sl, tp, "MomRank"))
            Print("[BUY] ", bestSym, " momentum=", DoubleToString(bestScore, 2));
    }
    else
    {
        double bid = SymbolInfoDouble(bestSym, SYMBOL_BID);
        double sl = NormalizeDouble(bid + sl_dist, digits);
        double tp = NormalizeDouble(bid - tp_dist, digits);
        if(trade.Sell(LotSize, bestSym, bid, sl, tp, "MomRank"))
            Print("[SELL] ", bestSym, " momentum=", DoubleToString(bestScore, 2));
    }
    g_curSymbol = bestSym;
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

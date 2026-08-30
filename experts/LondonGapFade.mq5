//+------------------------------------------------------------------+
//|  LondonGapFade.mq5                                               |
//|  ロンドンオープン・ギャップフェードEA v1.0（新規戦略候補#18）    |
//|  ロンドンオープン時刻の始値と直前バー終値のギャップを検出し、     |
//|  ギャップが一定以上ならギャップ方向と逆にエントリー（埋め狙い）。 |
//+------------------------------------------------------------------+
#property copyright "2026"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>

input group "=== セッション設定（GMT基準）==="
input int London_Open_Hour = 7;   // ロンドンオープン時刻（GMT）。この時刻のH1バーでギャップ判定

input group "=== ギャップ検出 ==="
input int    ATR_Period       = 14;
input double Gap_Min_ATR      = 0.5;  // ギャップ幅 >= この倍率×ATR で検出

input group "=== ストップ ==="
input double ATR_SL_Mult = 1.5;   // SL距離 = ATR × この倍率
input double RR_Ratio    = 1.0;   // TP距離 = SL距離 × このRR比

input group "=== トレード設定 ==="
input double LotSize     = 0.01;
input int    MagicNumber = 20260960;

input group "=== 出力設定 ==="
input string ResultFileName = "";
input string EquityLogFile  = "";

CTrade trade;
int    atr_handle;

//+------------------------------------------------------------------+
int OnInit()
{
    atr_handle = iATR(_Symbol, PERIOD_H1, ATR_Period);
    if(atr_handle == INVALID_HANDLE) { Print("ATRハンドル作成失敗"); return INIT_FAILED; }
    trade.SetExpertMagicNumber(MagicNumber);
    trade.SetDeviationInPoints(10);
    Print("LondonGapFade v1.0 起動 | OpenHour=", London_Open_Hour, " GapMinATR=", Gap_Min_ATR);
    return INIT_SUCCEEDED;
}

void OnDeinit(const int reason) { IndicatorRelease(atr_handle); }

//+------------------------------------------------------------------+
void OnTick()
{
    static datetime last_bar_time = 0;
    datetime current_bar_time = iTime(_Symbol, PERIOD_H1, 0);
    if(current_bar_time == last_bar_time) return;
    last_bar_time = current_bar_time;

    // 直前に確定したH1バー（shift=1）がロンドンオープン時刻かを判定
    MqlDateTime dt;
    TimeToStruct(iTime(_Symbol, PERIOD_H1, 1), dt);
    if(dt.hour != London_Open_Hour) return;

    double atr_buf[];
    ArraySetAsSeries(atr_buf, true);
    if(CopyBuffer(atr_handle, 0, 2, 1, atr_buf) < 1) return; // 判定バー確定前のATR
    double atr = atr_buf[0];
    if(atr <= 0) return;

    double open1  = iOpen(_Symbol, PERIOD_H1, 1);  // ロンドンオープンバーの始値
    double close2 = iClose(_Symbol, PERIOD_H1, 2); // 直前バー（アジア時間）の終値
    double gap = open1 - close2;
    if(MathAbs(gap) < Gap_Min_ATR * atr) return;

    if(HasPosition()) return; // 1本のみ、既存ポジションがあれば新規なし

    double sl_dist = atr * ATR_SL_Mult;
    double tp_dist = sl_dist * RR_Ratio;
    int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);

    if(gap > 0)
    {
        // 上ギャップ → 下落(埋め)方向を狙って売り
        double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
        double sl = NormalizeDouble(bid + sl_dist, digits);
        double tp = NormalizeDouble(bid - tp_dist, digits);
        if(trade.Sell(LotSize, _Symbol, bid, sl, tp, "GapFadeS"))
            Print("[SELL] gap=", DoubleToString(gap, digits), " atr=", DoubleToString(atr, digits));
    }
    else
    {
        // 下ギャップ → 上昇(埋め)方向を狙って買い
        double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
        double sl = NormalizeDouble(ask - sl_dist, digits);
        double tp = NormalizeDouble(ask + tp_dist, digits);
        if(trade.Buy(LotSize, _Symbol, ask, sl, tp, "GapFadeB"))
            Print("[BUY] gap=", DoubleToString(gap, digits), " atr=", DoubleToString(atr, digits));
    }
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

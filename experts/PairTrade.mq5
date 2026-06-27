//+------------------------------------------------------------------+
//|  PairTrade.mq5                                                   |
//|  統計的平均回帰ペアトレード（マーケットニュートラル）v1.0      |
//|  2通貨ペアのスプレッドのz-score回帰を取る（戦略: リスト外）    |
//|  アタッチ先=主シンボル(例EURUSD)、SecondSymbol=従シンボル(GBPUSD)|
//+------------------------------------------------------------------+
#property copyright "2026"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>

//--- 入力パラメータ
input group "=== ペア設定 ==="
input string SecondSymbol = "GBPUSD"; // 従シンボル（主シンボルはアタッチ先）
input int    Lookback     = 100;      // スプレッド統計の期間（バー数）

input group "=== エントリー/決済（z-score） ==="
input double Entry_Z = 2.0;  // |z|がこの値以上で乖離エントリー
input double Exit_Z  = 0.5;  // |z|がこの値以下で回帰決済
input double Stop_Z  = 4.0;  // |z|がこの値以上で損切り（乖離拡大）

input group "=== トレード設定 ==="
input double LotSize     = 0.01;
input int    MagicNumber = 20260629;

input group "=== ポジションサイジング（資産連動・複利） ==="
input bool   UseRiskSizing = false;    // ON: 資産連動でロットをスケール（複利）。価格SLが無いため資産比例方式。
input double RefDeposit    = 100000.0; // 基準資金。LotSizeはこの資金額での基準ロット。

input group "=== 出力設定 ==="
input string ResultFileName = "";
input string EquityLogFile  = ""; // 全dealのtime,profitを書き出す（mt5bt portfolioでDD合算）

//--- グローバル変数
CTrade trade;

//+------------------------------------------------------------------+
int OnInit()
{
    if(!SymbolSelect(SecondSymbol, true))
    {
        Print("従シンボルの選択に失敗: ", SecondSymbol);
        return INIT_FAILED;
    }
    trade.SetExpertMagicNumber(MagicNumber);
    trade.SetDeviationInPoints(20);
    Print("PairTrade v1.0 起動 | 主=", _Symbol, " 従=", SecondSymbol,
          " | Lookback=", Lookback, " EntryZ=", DoubleToString(Entry_Z,1),
          " ExitZ=", DoubleToString(Exit_Z,1), " StopZ=", DoubleToString(Stop_Z,1));
    return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void OnTick()
{
    static datetime last_bar_time = 0;
    datetime current_bar_time = iTime(_Symbol, PERIOD_CURRENT, 0);
    if(current_bar_time == last_bar_time) return;
    last_bar_time = current_bar_time;

    // 両シンボルの終値（前確定足からLookback本）
    double mainC[], secondC[];
    ArraySetAsSeries(mainC,   true);
    ArraySetAsSeries(secondC, true);
    if(CopyClose(_Symbol,      PERIOD_CURRENT, 1, Lookback, mainC)   < Lookback) return;
    if(CopyClose(SecondSymbol, PERIOD_CURRENT, 1, Lookback, secondC) < Lookback) return;

    // スプレッド配列と統計
    double mean = 0.0;
    double spread0 = mainC[0] - secondC[0];
    for(int i = 0; i < Lookback; i++)
        mean += (mainC[i] - secondC[i]);
    mean /= Lookback;

    double var = 0.0;
    for(int i = 0; i < Lookback; i++)
    {
        double s = mainC[i] - secondC[i];
        var += (s - mean) * (s - mean);
    }
    var /= Lookback;
    double sd = MathSqrt(var);
    if(sd <= 0.0) return;

    double z = (spread0 - mean) / sd;

    // ポジション状態（主シンボルの方向で判定）
    bool main_long  = HasPos(_Symbol, POSITION_TYPE_BUY);
    bool main_short = HasPos(_Symbol, POSITION_TYPE_SELL);
    int state = main_long ? 1 : (main_short ? -1 : 0);

    if(state == 0)
    {
        // エントリー: スプレッドが平均から乖離 → 回帰方向に張る
        if(z >= Entry_Z)
        {
            // 主が割高 → 主売り・従買い（スプレッド縮小に賭ける）
            OpenPair(false);
            Print("[ENTRY short-spread] z=", DoubleToString(z,2), " spread=", DoubleToString(spread0,5));
        }
        else if(z <= -Entry_Z)
        {
            // 主が割安 → 主買い・従売り
            OpenPair(true);
            Print("[ENTRY long-spread] z=", DoubleToString(z,2), " spread=", DoubleToString(spread0,5));
        }
    }
    else if(state == 1)
    {
        // long-spread（主買い・従売り）: zが0付近に戻る or 拡大しすぎ
        if(z >= -Exit_Z || z <= -Stop_Z)
        {
            CloseAll();
            Print("[EXIT long-spread] z=", DoubleToString(z,2));
        }
    }
    else if(state == -1)
    {
        // short-spread（主売り・従買い）
        if(z <= Exit_Z || z >= Stop_Z)
        {
            CloseAll();
            Print("[EXIT short-spread] z=", DoubleToString(z,2));
        }
    }
}

//+------------------------------------------------------------------+
// long_spread=true: 主買い・従売り / false: 主売り・従買い
void OpenPair(bool long_spread)
{
    double mainAsk = SymbolInfoDouble(_Symbol,      SYMBOL_ASK);
    double mainBid = SymbolInfoDouble(_Symbol,      SYMBOL_BID);
    double secAsk  = SymbolInfoDouble(SecondSymbol, SYMBOL_ASK);
    double secBid  = SymbolInfoDouble(SecondSymbol, SYMBOL_BID);

    double lot = CalcLotPair();
    if(long_spread)
    {
        trade.Buy(lot, _Symbol, mainAsk, 0, 0, "PairMain");
        trade.Sell(lot, SecondSymbol, secBid, 0, 0, "PairSecond");
    }
    else
    {
        trade.Sell(lot, _Symbol, mainBid, 0, 0, "PairMain");
        trade.Buy(lot, SecondSymbol, secAsk, 0, 0, "PairSecond");
    }
}

//+------------------------------------------------------------------+
bool HasPos(string sym, ENUM_POSITION_TYPE type)
{
    for(int i = PositionsTotal() - 1; i >= 0; i--)
        if(PositionGetSymbol(i) == sym &&
           PositionGetInteger(POSITION_MAGIC) == MagicNumber &&
           PositionGetInteger(POSITION_TYPE)  == type)
            return true;
    return false;
}

//+------------------------------------------------------------------+
void CloseAll()
{
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        ulong ticket = PositionGetTicket(i);
        if(PositionGetInteger(POSITION_MAGIC) == MagicNumber)
        {
            string sym = PositionGetString(POSITION_SYMBOL);
            if(sym == _Symbol || sym == SecondSymbol)
                trade.PositionClose(ticket);
        }
    }
}

//+------------------------------------------------------------------+
// 資産連動の複利ロット計算: lot = LotSize × (equity / RefDeposit)。
// UseRiskSizing=false なら固定LotSizeを返す（既存挙動と完全一致）。
double CalcLotPair()
{
    if(!UseRiskSizing)
        return LotSize;

    double equity = AccountInfoDouble(ACCOUNT_EQUITY);
    double refDep = (RefDeposit > 0.0) ? RefDeposit : 100000.0;
    double lot    = LotSize * (equity / refDep);

    double minLot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
    double maxLot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
    double stepLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
    if(stepLot > 0.0)
        lot = MathFloor(lot / stepLot) * stepLot;
    lot = MathMax(minLot, MathMin(maxLot, lot));
    return lot;
}

//+------------------------------------------------------------------+
double OnTester()
{
    double pf = TesterStatistics(STAT_PROFIT_FACTOR);

    // ポートフォリオDD算出用: 全dealの time,profit を書き出す（mt5bt portfolio が合算）
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
                if(eqtype != DEAL_TYPE_BUY && eqtype != DEAL_TYPE_SELL) continue; // 残高操作(入金)等を除外
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
    if(fh == INVALID_HANDLE)
    {
        Print("結果ファイルを開けません: ", ResultFileName, " Error=", GetLastError());
        return pf;
    }
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
    Print("バックテスト結果を書き出しました: MQL5\\Files\\", ResultFileName);
    return pf;
}
//+------------------------------------------------------------------+

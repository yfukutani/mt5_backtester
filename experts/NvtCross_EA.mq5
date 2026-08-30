//+------------------------------------------------------------------+
//|  NvtCross_EA.mq5                                                 |
//|  NVT移動平均クロスの割安化ロング v1.0（第2バックログV7）           |
//|  仮説: NVT（時価総額/オンチェーン取引額）はBTCの利用実態に対する    |
//|  価格の割高度。NVTのMA30がMA90を下抜け＝「価格に対して利用が       |
//|  伸びている（割安化）」の転換点で、その後20日のリターンが対照の     |
//|  3倍超（スクリーニング: n=30/t=2.03/前半+17.3/後半+5.9/           |
//|  独立エピソード21個・隣接9セル全て両半プラス）。                    |
//|  データ: Common\Files\nvt_btc.csv（ml/gen_nvt.pyで生成・日次）。   |
//|  候補段階のためCSV参照のみ（採用時はFundingRev v1.1同様の          |
//|  blockchain.info自動更新を実装する）。                             |
//+------------------------------------------------------------------+
#property copyright "2026"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>

input group "=== シグナル ==="
input string NvtFile   = "nvt_btc.csv";  // Common\Files内（time,nvt 日次）
input int    FastMA    = 30;             // NVT短期MA
input int    SlowMA    = 90;             // NVT長期MA
input int    HoldDays  = 20;             // 保有日数（D1バー）

input group "=== トレード設定 ==="
input double LotSize     = 0.01;
input int    MagicNumber = 20260722;

input group "=== 出力設定 ==="
input string ResultFileName = "";
input string EquityLogFile  = "";

CTrade trade;
long     n_day[];    // UTC日番号
double   n_val[];
int      n_n = 0;
datetime lastBar = 0;

//+------------------------------------------------------------------+
int OnInit()
{
    trade.SetExpertMagicNumber(MagicNumber);
    int fh = FileOpen(NvtFile, FILE_READ | FILE_CSV | FILE_ANSI | FILE_COMMON, ',');
    if(fh == INVALID_HANDLE)
    {
        Print("NVT CSVが開けない（Common\\Files\\", NvtFile, "）err=", GetLastError());
        return INIT_FAILED;
    }
    ArrayResize(n_day, 8000);
    ArrayResize(n_val, 8000);
    FileReadString(fh);
    FileReadString(fh);
    while(!FileIsEnding(fh) && n_n < 8000)
    {
        string ts = FileReadString(fh);
        string vs = FileReadString(fh);
        if(ts == "") break;
        n_day[n_n] = StringToInteger(ts) / 86400;
        n_val[n_n] = StringToDouble(vs);
        n_n++;
    }
    FileClose(fh);
    if(n_n < SlowMA + 10)
    {
        Print("NVTデータ不足: ", n_n, "件");
        return INIT_FAILED;
    }
    if(n_day[n_n - 1] < 10000)   // 日番号の健全性（1997年以前=時刻列の生成バグ検知）
    {
        Print("NVT CSVの時刻列が不正: day[last]=", n_day[n_n - 1]);
        return INIT_FAILED;
    }
    Print("NvtCross v1.0 起動 | NVT ", n_n, "件 | MA", FastMA, "/", SlowMA, " | 保有", HoldDays, "日");
    return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| day（UTC日番号）以前で最後のNVTインデックス。無ければ-1            |
//+------------------------------------------------------------------+
int IdxBefore(long day)
{
    for(int i = n_n - 1; i >= 0; i--)
        if(n_day[i] <= day) return i;
    return -1;
}

double MaAt(int idx, int period)
{
    if(idx - period + 1 < 0) return EMPTY_VALUE;
    double s = 0;
    for(int i = idx - period + 1; i <= idx; i++) s += n_val[i];
    return s / period;
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

int BarsHeldD1()
{
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        if(PositionGetSymbol(i) == _Symbol &&
           PositionGetInteger(POSITION_MAGIC) == MagicNumber)
        {
            datetime opened = (datetime)PositionGetInteger(POSITION_TIME);
            return iBarShift(_Symbol, PERIOD_D1, opened, false);
        }
    }
    return 0;
}

void CloseAll()
{
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        ulong tk = PositionGetTicket(i);
        if(PositionGetString(POSITION_SYMBOL) == _Symbol &&
           PositionGetInteger(POSITION_MAGIC) == MagicNumber)
            trade.PositionClose(tk);
    }
}

//+------------------------------------------------------------------+
void OnTick()
{
    datetime bt = iTime(_Symbol, PERIOD_D1, 0);
    if(bt == lastBar) return;
    lastBar = bt;

    if(HasPosition())
    {
        if(BarsHeldD1() >= HoldDays) CloseAll();
        return;   // 1ポジション制
    }

    // 前日までのNVTでMAクロス判定（当日データは使わない）
    long yday = (long)bt / 86400 - 1;
    int idx = IdxBefore(yday);
    if(idx < 1) return;
    double f0 = MaAt(idx, FastMA);
    double s0 = MaAt(idx, SlowMA);
    double f1 = MaAt(idx - 1, FastMA);
    double s1 = MaAt(idx - 1, SlowMA);
    if(f0 == EMPTY_VALUE || s0 == EMPTY_VALUE || f1 == EMPTY_VALUE || s1 == EMPTY_VALUE) return;

    if(f0 < s0 && f1 >= s1)
    {
        double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
        if(trade.Buy(LotSize, _Symbol, ask, 0, 0, "NvtX"))
            Print("[NVTX BUY] fast=", DoubleToString(f0, 1), " slow=", DoubleToString(s0, 1));
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
            int tot = HistoryDealsTotal();
            for(int i = 0; i < tot; i++)
            {
                ulong tk = HistoryDealGetTicket(i);
                if(tk == 0) continue;
                long dtype = HistoryDealGetInteger(tk, DEAL_TYPE);
                if(dtype != DEAL_TYPE_BUY && dtype != DEAL_TYPE_SELL) continue;
                double p = HistoryDealGetDouble(tk, DEAL_PROFIT)
                         + HistoryDealGetDouble(tk, DEAL_SWAP)
                         + HistoryDealGetDouble(tk, DEAL_COMMISSION);
                FileWrite(eqh, (long)HistoryDealGetInteger(tk, DEAL_TIME), DoubleToString(p, 2));
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

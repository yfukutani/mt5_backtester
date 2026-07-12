//+------------------------------------------------------------------+
//|  FundingRev_EA.mq5                                               |
//|  BTC funding rate 悲観極端の逆張りロング v1.0（バックログG1）      |
//|  仮説: 永久先物の資金調達率が極端なマイナス＝ショート過密の状態は  |
//|  踏み上げが起きやすく、翌5日のリターンが対照の6倍（事前分析:      |
//|  +4.18%/t=5.13/前後半両プラス）。                                  |
//|  データ: Common\Files\funding_btc.csv（ml/fetch_btc_alt_data.pyで  |
//|  取得・8時間毎）。テスターのAgentワイプ対策としてFILE_COMMON参照。 |
//|  ロジック: 新D1バーで前日のfunding日平均を計算し、閾値未満なら     |
//|  ロング→HoldDays日後に成行クローズ（SL/TPなし＝分析準拠）。        |
//+------------------------------------------------------------------+
#property copyright "2026"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>

input group "=== シグナル ==="
input string FundingFile     = "funding_btc.csv"; // Common\Files内
input double Threshold_Pct8h = -0.004;  // 日平均funding閾値（%/8h・5%分位）
input int    HoldDays        = 5;       // 保有日数（D1バー）

input group "=== トレード設定 ==="
input double LotSize     = 0.01;
input double DisasterSL_Pct = 0.0;      // 災害SL（エントリー比%・0=無効＝分析準拠）
input int    MagicNumber = 20260720;

input group "=== 出力設定 ==="
input string ResultFileName = "";
input string EquityLogFile  = "";

CTrade trade;
long   f_time[];
double f_rate[];
int    f_n = 0;
datetime lastBar = 0;
int    barsHeld = 0;

//+------------------------------------------------------------------+
int OnInit()
{
    trade.SetExpertMagicNumber(MagicNumber);
    // funding CSVをCommonから読み込み（time,funding_rate）
    int fh = FileOpen(FundingFile, FILE_READ | FILE_CSV | FILE_ANSI | FILE_COMMON, ',');
    if(fh == INVALID_HANDLE)
    {
        Print("funding CSVが開けない（Common\\Files\\", FundingFile, "）err=", GetLastError());
        return INIT_FAILED;
    }
    ArrayResize(f_time, 20000);
    ArrayResize(f_rate, 20000);
    // ヘッダをスキップ
    FileReadString(fh);
    FileReadString(fh);
    while(!FileIsEnding(fh) && f_n < 20000)
    {
        string ts = FileReadString(fh);
        string rs = FileReadString(fh);
        if(ts == "") break;
        f_time[f_n] = StringToInteger(ts);
        f_rate[f_n] = StringToDouble(rs);
        f_n++;
    }
    FileClose(fh);
    if(f_n < 100)
    {
        Print("fundingデータ不足: ", f_n, "件");
        return INIT_FAILED;
    }
    Print("FundingRev v1.0 起動 | funding ", f_n, "件 ",
          TimeToString((datetime)f_time[0], TIME_DATE), "..",
          TimeToString((datetime)f_time[f_n - 1], TIME_DATE),
          " | 閾値 ", DoubleToString(Threshold_Pct8h, 4), "%/8h | 保有", HoldDays, "日");
    return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| [t0, t1) のfunding平均（%/8h）。データ無しはEMPTY_VALUE           |
//+------------------------------------------------------------------+
double FundingAvg(datetime t0, datetime t1)
{
    double sum = 0;
    int cnt = 0;
    for(int i = 0; i < f_n; i++)
    {
        if(f_time[i] >= (long)t0 && f_time[i] < (long)t1)
        {
            sum += f_rate[i] * 100.0;   // 率→%
            cnt++;
        }
        else if(f_time[i] >= (long)t1)
            break;
    }
    return (cnt > 0 ? sum / cnt : EMPTY_VALUE);
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
        barsHeld++;
        if(barsHeld >= HoldDays)
        {
            CloseAll();
            barsHeld = 0;
        }
        return;   // 1ポジション制
    }
    barsHeld = 0;

    // 前日 [bt-1日, bt) のfunding日平均
    double avg = FundingAvg(bt - 86400, bt);
    if(avg == EMPTY_VALUE) return;   // データ範囲外（2019.09以前など）

    if(avg < Threshold_Pct8h)
    {
        double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
        double sl = (DisasterSL_Pct > 0 ? NormalizeDouble(ask * (1 - DisasterSL_Pct / 100), _Digits) : 0);
        if(trade.Buy(LotSize, _Symbol, ask, sl, 0, "FundRev"))
            Print("[FUNDREV BUY] avg_funding=", DoubleToString(avg, 4), "%/8h");
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

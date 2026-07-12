//+------------------------------------------------------------------+
//|  ETH_EA.mq5                                                      |
//|  ETH専用EA v1.0 — A2デュアルMA＋ETH実証済み機構の統合             |
//|                                                                  |
//|  コア戦略（A2・2026-07-12ユーザー採用）:                          |
//|    D1でclose>MA200かつclose>MA40で買い保有 / close<MA40で退出     |
//|    （早期退出で2018/2022型の深押しを回避）＋退出後5日は再entry禁止 |
//|    （whipsaw削減・クールダウン、市場横断で実証）。                 |
//|  検証成績（0.02lot・スワップ実費込み・XMテスター）:               |
//|    full(2016.11-2026.06) +7,576円/PF1.81/DD3.7%/50取引            |
//|    IS(2021.06-) +4,165円/PF1.50/DD3.8%                            |
//|    プラトー: ExitMA30/40/50×cd3/5/7の全点プラス                   |
//|  組み込み済みの実証済み機構:                                      |
//|    - 災害SL 45%（全50取引のMAE最悪-29.2%×1.5・歴史上不発火＝      |
//|      期待値不変のテール保護、Z3方式で校正）                        |
//|    - 運用ログ（mixlog形式・ライブのみ・ethlog_YYYYMM.csv）         |
//|  組み込まない（ETHで検証済み無効のため）:                          |
//|    funding系（352格子で死亡）/ボラターゲット（ETHで効率-43%）/     |
//|    ヒステリシス帯（ETH不採用・v1.1検証）/複利サイジング（固定優位） |
//|  ⚠️ 本EAはMIX_EAのETH trend-holdスリーブの「置換」。併走させると   |
//|     ETHエクスポージャーが二重になる（docs/ETH_EA_UM.md参照）。     |
//+------------------------------------------------------------------+
#property copyright "2026"
#property version   "1.10"
#property strict

#include <Trade\Trade.mqh>

input group "=== A2デュアルMA ==="
input int             TrendMA_Period  = 200;   // 大局トレンドMA（この上でのみ買い）
input int             ExitMA_Period   = 40;    // 退出MA（割れで手仕舞い・0=MA200単独の旧スリーブ互換）
input ENUM_MA_METHOD  MA_Method       = MODE_SMA;
input ENUM_TIMEFRAMES SignalTimeframe = PERIOD_CURRENT;  // 判定TF（D1チャート想定）
input int             ReentryCooldown = 5;     // 退出後の再entry禁止バー数（S9・実証済み）

input group "=== トレード設定 ==="
input double LotSize        = 0.02;   // 固定ロット（複利はETHで劣後の実証あり）
input double DisasterSL_Pct = 45.0;   // 災害SL（entry比%・歴史上不発火の校正値・0=無効）
input int    MagicNumber    = 20260723;
// v1.1: 暗号グループ同時ポジション上限（口座横断・MIX_EA v1.3と同一ルール）。
// テスター実測で効率劣化のため既定0。1=保有中は新規見送り
input int    MaxCryptoConcurrent = 0;

input group "=== 運用ログ（ライブのみ） ==="
input bool   EnableOpsLog = true;     // ethlog_YYYYMM.csv へDEAL/DAILY出力

input group "=== 出力設定 ==="
input string ResultFileName = "";
input string EquityLogFile  = "";

CTrade   trade;
int      trendma_handle = INVALID_HANDLE;
int      exitma_handle = INVALID_HANDLE;
datetime g_last_exit = 0;
datetime g_last_daily = 0;

//+------------------------------------------------------------------+
int OnInit()
{
    trendma_handle = iMA(_Symbol, SignalTimeframe, TrendMA_Period, 0, MA_Method, PRICE_CLOSE);
    if(trendma_handle == INVALID_HANDLE)
    {
        Print("TrendMAハンドルの作成に失敗");
        return INIT_FAILED;
    }
    if(ExitMA_Period > 0)
    {
        exitma_handle = iMA(_Symbol, SignalTimeframe, ExitMA_Period, 0, MA_Method, PRICE_CLOSE);
        if(exitma_handle == INVALID_HANDLE)
        {
            Print("ExitMAハンドルの作成に失敗");
            return INIT_FAILED;
        }
    }
    trade.SetExpertMagicNumber(MagicNumber);
    trade.SetDeviationInPoints(20);
    Print("ETH_EA v1.0 起動 | ", _Symbol,
          " | A2 MA", TrendMA_Period, "/", ExitMA_Period > 0 ? IntegerToString(ExitMA_Period) : "OFF(単独)",
          " | Cooldown=", ReentryCooldown,
          " | 災害SL=", DisasterSL_Pct > 0 ? StringFormat("%.0f%%", DisasterSL_Pct) : "OFF",
          " | OpsLog=", EnableOpsLog ? "ON" : "OFF");
    return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
    if(trendma_handle != INVALID_HANDLE) IndicatorRelease(trendma_handle);
    if(exitma_handle != INVALID_HANDLE) IndicatorRelease(exitma_handle);
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

// v1.1: 暗号グループ同時上限（口座横断）
bool CryptoGuardOK()
{
    if(MaxCryptoConcurrent <= 0) return true;
    int cnt = 0;
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        long m = PositionGetInteger(POSITION_MAGIC);
        if(PositionGetSymbol(i) == "") continue;
        if(m == 20260710 || m == 20260720 || m == 20260723 || m == 20260724) cnt++;
    }
    if(cnt >= MaxCryptoConcurrent)
    {
        Print("[CRYPTO-CAP] エントリー見送り（暗号同時", cnt, "/上限", MaxCryptoConcurrent, "）");
        return false;
    }
    return true;
}

void ClosePosition()
{
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        ulong tk = PositionGetTicket(i);
        if(PositionGetInteger(POSITION_MAGIC) == MagicNumber &&
           PositionGetString(POSITION_SYMBOL) == _Symbol)
            trade.PositionClose(tk);
    }
}

//+------------------------------------------------------------------+
//| 運用ログ（ライブのみ・月次ローテーション・追記）                  |
//+------------------------------------------------------------------+
void OpsWrite(const string kind, const string detail)
{
    if(!EnableOpsLog || MQLInfoInteger(MQL_TESTER)) return;
    MqlDateTime dt;
    TimeToStruct(TimeCurrent(), dt);
    string fname = StringFormat("ethlog_%04d%02d.csv", dt.year, dt.mon);
    int fh = FileOpen(fname, FILE_READ | FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
    if(fh == INVALID_HANDLE) return;
    FileSeek(fh, 0, SEEK_END);
    if(FileTell(fh) == 0)
        FileWrite(fh, "time", "kind", "detail", "equity", "balance");
    FileWrite(fh, TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS), kind, detail,
              DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY), 2),
              DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2));
    FileClose(fh);
}

void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
{
    if(trans.type != TRADE_TRANSACTION_DEAL_ADD) return;
    if(!HistoryDealSelect(trans.deal)) return;
    if(HistoryDealGetInteger(trans.deal, DEAL_MAGIC) != MagicNumber) return;
    long   dtype = HistoryDealGetInteger(trans.deal, DEAL_TYPE);
    if(dtype != DEAL_TYPE_BUY && dtype != DEAL_TYPE_SELL) return;
    double p = HistoryDealGetDouble(trans.deal, DEAL_PROFIT)
             + HistoryDealGetDouble(trans.deal, DEAL_SWAP)
             + HistoryDealGetDouble(trans.deal, DEAL_COMMISSION);
    OpsWrite("DEAL", StringFormat("%s|%s|%.2f@%.2f|pnl=%.2f",
             dtype == DEAL_TYPE_BUY ? "BUY" : "SELL",
             HistoryDealGetString(trans.deal, DEAL_SYMBOL),
             HistoryDealGetDouble(trans.deal, DEAL_VOLUME),
             HistoryDealGetDouble(trans.deal, DEAL_PRICE), p));
}

//+------------------------------------------------------------------+
void OnTick()
{
    static datetime last_bar_time = 0;
    datetime current_bar_time = iTime(_Symbol, PERIOD_CURRENT, 0);
    if(current_bar_time == last_bar_time) return;
    last_bar_time = current_bar_time;

    // 日次ハートビート（生存確認・ライブのみ）
    datetime d1bar = iTime(_Symbol, PERIOD_D1, 0);
    if(d1bar != g_last_daily)
    {
        g_last_daily = d1bar;
        OpsWrite("DAILY", StringFormat("pos=%s", HasPosition() ? "LONG" : "FLAT"));
    }

    double ma_buf[];
    ArraySetAsSeries(ma_buf, true);
    if(CopyBuffer(trendma_handle, 0, 1, 1, ma_buf) < 1) return;
    double ma200 = ma_buf[0];
    double close_prev = iClose(_Symbol, SignalTimeframe, 1);

    double entry_th = ma200, exit_th = ma200;
    if(ExitMA_Period > 0)
    {
        double ex_buf[];
        ArraySetAsSeries(ex_buf, true);
        if(CopyBuffer(exitma_handle, 0, 1, 1, ex_buf) < 1) return;
        entry_th = MathMax(ma200, ex_buf[0]);
        exit_th  = ex_buf[0];
    }

    bool has_pos = HasPosition();

    // クールダウン（S9）: 退出から所定バー数は再entry禁止
    bool cooldown_ok = true;
    if(ReentryCooldown > 0 && g_last_exit > 0)
        cooldown_ok = (iBarShift(_Symbol, SignalTimeframe, g_last_exit, false) >= ReentryCooldown);

    if(close_prev > entry_th && !has_pos && cooldown_ok && CryptoGuardOK())
    {
        double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
        double sl = (DisasterSL_Pct > 0
                     ? NormalizeDouble(ask * (1 - DisasterSL_Pct / 100), _Digits) : 0);
        if(trade.Buy(LotSize, _Symbol, ask, sl, 0, "ETH_A2"))
            Print("[ETH_A2 BUY] close=", close_prev, " entryTh=", DoubleToString(entry_th, _Digits));
    }
    else if(close_prev < exit_th && has_pos)
    {
        ClosePosition();
        g_last_exit = current_bar_time;
        Print("[ETH_A2 EXIT] close=", close_prev, " exitTh=", DoubleToString(exit_th, _Digits));
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

//+------------------------------------------------------------------+
//|  DAY_RELAY.mq5                                                   |
//|  セッションリレー・デイトレEA v1.0（DAY_EAバックログ A5/A10）      |
//|  「欧州時間に強く動いた方向へ、NYセッションで追随する」            |
//|  期待値マップ実測: GOLD強シグナル +182.9円/回（IS+207/OOS+140、    |
//|  コスト52円を両期間で超過）に基づく。                              |
//|  判定: JudgeHour時に窓(StartHour→EndHour)のリターンを測り、       |
//|  |リターン| >= MinMove_ADR × D1ATR14 なら方向へ成行。              |
//|  決済: CloseHour強制（既定20時=NY午後を持たない・SCA知見）。       |
//|  SL: SL_ADR×ATRd（0=なし・時間決済のみ）。1日1回。                |
//|  ※検証はevery_tick推奨。H1チャートにアタッチ。                    |
//+------------------------------------------------------------------+
#property copyright "2026"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>

input group "=== セッション窓（サーバー時間・GMT+2/+3） ==="
input int StartHour = 9;    // 判定窓の開始（欧州オープン）
input int EndHour   = 15;   // 判定窓の終了（この時のcloseまで＝15時close）
input int JudgeHour = 16;   // 判定・エントリー時
input int CloseHour = 20;   // 全決済時

input group "=== シグナル ==="
input double MinMove_ADR = 0.30;  // 窓リターンの下限（D1ATR14倍・強シグナルのみ）
input double SL_ADR      = 0.0;   // SL距離（ATRd倍・0=SLなし時間決済のみ）

input group "=== トレード設定 ==="
input double LotSize     = 0.01;
input int    MagicNumber = 20262001;

input group "=== 出力設定 ==="
input string ResultFileName = "";
input string EquityLogFile  = "";
input string TradeLogFile   = "";

CTrade trade;
int    atr_d1_handle;
datetime g_day    = 0;
bool     g_traded = false;

//+------------------------------------------------------------------+
int OnInit()
{
    atr_d1_handle = iATR(_Symbol, PERIOD_D1, 14);
    if(atr_d1_handle == INVALID_HANDLE) return INIT_FAILED;
    trade.SetExpertMagicNumber(MagicNumber);
    trade.SetDeviationInPoints(20);
    Print("DAY_RELAY v1.0 起動 | ", _Symbol, " | 窓", StartHour, "-", EndHour,
          "h 判定", JudgeHour, "h 決済", CloseHour, "h | MinMove=", MinMove_ADR, "×ATRd");
    return INIT_SUCCEEDED;
}

void OnDeinit(const int reason) { IndicatorRelease(atr_d1_handle); }

//+------------------------------------------------------------------+
bool HasPosition()
{
    for(int i = PositionsTotal() - 1; i >= 0; i--)
        if(PositionGetSymbol(i) == _Symbol &&
           PositionGetInteger(POSITION_MAGIC) == MagicNumber) return true;
    return false;
}

void CloseAll()
{
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        ulong tk = PositionGetTicket(i);
        if(PositionGetSymbol(i) == _Symbol &&
           PositionGetInteger(POSITION_MAGIC) == MagicNumber)
            trade.PositionClose(tk);
    }
}

//+------------------------------------------------------------------+
void OnTick()
{
    static datetime last_bar = 0;
    datetime bt = iTime(_Symbol, PERIOD_H1, 0);
    if(bt == last_bar) return;
    last_bar = bt;

    MqlDateTime dt;
    TimeToStruct(bt, dt);
    datetime day_start = bt - (dt.hour * 3600 + dt.min * 60 + dt.sec);

    if(day_start != g_day)
    {
        g_day = day_start;
        g_traded = false;
    }

    // 決済時刻
    if(dt.hour >= CloseHour)
    {
        CloseAll();
        return;
    }

    // 判定・エントリー（JudgeHourのH1バー開始時に一度だけ）
    if(dt.hour != JudgeHour || g_traded || HasPosition()) return;
    g_traded = true;   // 1日1回の判定（発注可否に関わらず消費）

    // 窓リターン: StartHourのopen → EndHourバーのclose（=EndHour+1時のopen直前）
    int shOpen = iBarShift(_Symbol, PERIOD_H1, day_start + StartHour * 3600, true);
    int shClose = iBarShift(_Symbol, PERIOD_H1, day_start + EndHour * 3600, true);
    if(shOpen < 0 || shClose < 0) return;
    double wOpen = iOpen(_Symbol, PERIOD_H1, shOpen);
    double wClose = iClose(_Symbol, PERIOD_H1, shClose);
    double move = wClose - wOpen;

    double ab[];
    ArraySetAsSeries(ab, true);
    if(CopyBuffer(atr_d1_handle, 0, 1, 1, ab) < 1) return;
    double atrd = ab[0];
    if(atrd <= 0) return;

    if(MathAbs(move) < MinMove_ADR * atrd) return;   // 強シグナルのみ

    if(move > 0)
    {
        double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
        double sl = (SL_ADR > 0 ? NormalizeDouble(ask - SL_ADR * atrd, _Digits) : 0.0);
        trade.Buy(LotSize, _Symbol, ask, sl, 0.0, "RELAY-L");
    }
    else
    {
        double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
        double sl = (SL_ADR > 0 ? NormalizeDouble(bid + SL_ADR * atrd, _Digits) : 0.0);
        trade.Sell(LotSize, _Symbol, bid, sl, 0.0, "RELAY-S");
    }
}

//+------------------------------------------------------------------+
double OnTester()
{
    double pf = TesterStatistics(STAT_PROFIT_FACTOR);
    if(TradeLogFile != "")
    {
        int th = FileOpen(TradeLogFile, FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
        if(th != INVALID_HANDLE)
        {
            FileWrite(th, "pos_id", "entry_time", "dir", "lots", "entry_price", "exit_time", "profit");
            HistorySelect(0, TimeCurrent());
            int total = HistoryDealsTotal();
            long op_id[8]; long op_et[8]; int op_dir[8];
            double op_lot[8]; double op_px[8]; double op_pnl[8];
            int nOpen = 0;
            for(int i = 0; i < total; i++)
            {
                ulong tk = HistoryDealGetTicket(i);
                if(tk == 0) continue;
                long dtype = HistoryDealGetInteger(tk, DEAL_TYPE);
                if(dtype != DEAL_TYPE_BUY && dtype != DEAL_TYPE_SELL) continue;
                long entry = HistoryDealGetInteger(tk, DEAL_ENTRY);
                long pid = (long)HistoryDealGetInteger(tk, DEAL_POSITION_ID);
                double pnl = HistoryDealGetDouble(tk, DEAL_PROFIT)
                           + HistoryDealGetDouble(tk, DEAL_SWAP)
                           + HistoryDealGetDouble(tk, DEAL_COMMISSION);
                if(entry == DEAL_ENTRY_IN)
                {
                    if(nOpen < 8)
                    {
                        op_id[nOpen] = pid;
                        op_et[nOpen] = (long)HistoryDealGetInteger(tk, DEAL_TIME);
                        op_dir[nOpen] = (dtype == DEAL_TYPE_BUY ? 1 : -1);
                        op_lot[nOpen] = HistoryDealGetDouble(tk, DEAL_VOLUME);
                        op_px[nOpen] = HistoryDealGetDouble(tk, DEAL_PRICE);
                        op_pnl[nOpen] = pnl;
                        nOpen++;
                    }
                }
                else
                {
                    for(int k = 0; k < nOpen; k++)
                    {
                        if(op_id[k] != pid) continue;
                        FileWrite(th, op_id[k], op_et[k], op_dir[k],
                                  DoubleToString(op_lot[k], 2), DoubleToString(op_px[k], _Digits),
                                  (long)HistoryDealGetInteger(tk, DEAL_TIME),
                                  DoubleToString(op_pnl[k] + pnl, 2));
                        for(int m = k; m < nOpen - 1; m++)
                        {
                            op_id[m] = op_id[m+1]; op_et[m] = op_et[m+1]; op_dir[m] = op_dir[m+1];
                            op_lot[m] = op_lot[m+1]; op_px[m] = op_px[m+1]; op_pnl[m] = op_pnl[m+1];
                        }
                        nOpen--;
                        break;
                    }
                }
            }
            FileClose(th);
        }
    }
    if(EquityLogFile != "")
    {
        int eqh = FileOpen(EquityLogFile, FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
        if(eqh != INVALID_HANDLE)
        {
            FileWrite(eqh, "time", "profit");
            HistorySelect(0, TimeCurrent());
            int n = HistoryDealsTotal();
            for(int e = 0; e < n; e++)
            {
                ulong tk = HistoryDealGetTicket(e);
                if(tk == 0) continue;
                long ty = HistoryDealGetInteger(tk, DEAL_TYPE);
                if(ty != DEAL_TYPE_BUY && ty != DEAL_TYPE_SELL) continue;
                double p = HistoryDealGetDouble(tk, DEAL_PROFIT) + HistoryDealGetDouble(tk, DEAL_SWAP)
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
    FileWrite(fh, "max_dd_pct",      DoubleToString(TesterStatistics(STAT_BALANCE_DDREL_PERCENT), 4));
    FileWrite(fh, "total_trades",    IntegerToString((int)TesterStatistics(STAT_TRADES)));
    FileWrite(fh, "win_trades",      IntegerToString((int)TesterStatistics(STAT_PROFIT_TRADES)));
    FileWrite(fh, "initial_deposit", DoubleToString(TesterStatistics(STAT_INITIAL_DEPOSIT), 2));
    FileClose(fh);
    return pf;
}
//+------------------------------------------------------------------+

//+------------------------------------------------------------------+
//|  BfxRev_EA.mq5                                                   |
//|  Bitfinexデレバレッジ・リバウンド v1.0（第3/4バックログBF・Q2）    |
//|  仮説: Bitfinexマージンのロング建玉が5日で10%超急減＝強制投げ      |
//|  （デレバレッジ）の完了直後は反発しやすい。fundingの悲観極端       |
//|  （G1）とは別のデレバレッジ現象を捕捉（イベント重複7%・相関+0.156・|
//|  G1との合算で効率+39%）。                                          |
//|  スクリーニング: n=78/t=3.25（fix5）・n=62/t=3.35（fix10）・        |
//|  後半(+6.9〜9.5%)が前半より強い・隣接drop20も同方向＝領域あり。     |
//|  データ供給（FundingRev v1.1と同型）:                              |
//|  - テスター: Common\Files\bfx_btc_long.csv                         |
//|    （ml/fetch_btc_alt_data3.py bitfinex で取得・日次）              |
//|  - ライブ: Bitfinex公開APIをWebRequestで直接取得（要URL許可:       |
//|    https://api-pub.bitfinex.com）。失敗時キャッシュ→手動CSV。      |
//|    データ欠損時は新規停止・決済はデータ非依存で必ず実行。          |
//+------------------------------------------------------------------+
#property copyright "2026"
#property version   "1.10"
#property strict

#include <Trade\Trade.mqh>

input group "=== シグナル ==="
input string BfxFile      = "bfx_btc_long.csv"; // Common\Files内（テスター/フォールバック）
input double DropPct      = 10.0;   // ロング建玉の急減閾値（%・5日変化）
input int    LookbackDays = 5;      // 変化率の測定日数
input int    HoldDays     = 10;     // 保有日数（D1バー）

input group "=== データ供給（ライブ） ==="
input bool   UseWebRequest = true;  // ライブ時Bitfinex APIから直接取得（テスターは常にCSV）
input string ApiUrl = "https://api-pub.bitfinex.com/v2/stats1/pos.size:1m:tBTCUSD:long/hist?limit=10000&sort=-1";
input bool   UpdateCsvCache = true;
input string CacheFile = "bfx_btc_long_cache.csv";

input group "=== トレード設定 ==="
input double LotSize        = 0.01;
input double DisasterSL_Pct = 75.0; // 災害SL（MAE最悪-47.5%×1.5・歴史上不発火・0=無効）
input int    MagicNumber    = 20260724;
// v1.1: 暗号グループ同時ポジション上限（口座全体のMagic 20260710/20260720/20260723/20260724を
// 横断カウント）。テスター実測で効率劣化のため既定0（MIX_EA_UM§9）。1=保有中は新規見送り
input int    MaxCryptoConcurrent = 0;

input group "=== 出力設定 ==="
input string ResultFileName = "";
input string EquityLogFile  = "";

CTrade   trade;
long     b_day[];    // UTC日番号
double   b_val[];    // ロング建玉サイズ（日末値）
int      b_n = 0;
datetime evaluatedBar = 0;
datetime lastFetchAttempt = 0;

//+------------------------------------------------------------------+
int LoadCsvInto(const string fname, long &t[], double &v[])
{
    int fh = FileOpen(fname, FILE_READ | FILE_CSV | FILE_ANSI | FILE_COMMON, ',');
    if(fh == INVALID_HANDLE) return 0;
    int n = 0;
    ArrayResize(t, 5000);
    ArrayResize(v, 5000);
    FileReadString(fh);
    FileReadString(fh);
    while(!FileIsEnding(fh))
    {
        string ts = FileReadString(fh);
        string vs = FileReadString(fh);
        if(ts == "") break;
        if(n >= ArraySize(t)) { ArrayResize(t, n + 2000); ArrayResize(v, n + 2000); }
        t[n] = StringToInteger(ts) / 86400;   // 日番号化
        v[n] = StringToDouble(vs);
        n++;
    }
    FileClose(fh);
    return n;
}

//+------------------------------------------------------------------+
//| APIレスポンス [[ms,val],...]（降順）→日末値へ集約して一時配列に    |
//+------------------------------------------------------------------+
int ParseBfx(const string body, long &t[], double &v[])
{
    // 形式: [[1752278400000,45123.4],[...]] — 数値ペアの単純パース
    int n = 0;
    ArrayResize(t, 5000);
    ArrayResize(v, 5000);
    int pos = 0;
    long lastday = -1;
    while(true)
    {
        int i0 = StringFind(body, "[", pos);
        if(i0 < 0) break;
        int ic = StringFind(body, ",", i0);
        int i1 = StringFind(body, "]", i0);
        if(ic < 0 || i1 < 0 || ic > i1) { pos = i0 + 1; continue; }
        long tms = StringToInteger(StringSubstr(body, i0 + 1, ic - i0 - 1));
        double val = StringToDouble(StringSubstr(body, ic + 1, i1 - ic - 1));
        if(tms > 1000000000000)   // ミリ秒epochのみ採用（外側の"["を除外）
        {
            long dy = tms / 86400000;
            if(dy != lastday)      // sort=-1（降順）→ 各日の最初=その日の最新値
            {
                if(n >= ArraySize(t)) { ArrayResize(t, n + 2000); ArrayResize(v, n + 2000); }
                t[n] = dy;
                v[n] = val;
                n++;
                lastday = dy;
            }
        }
        pos = i1 + 1;
    }
    return n;   // 降順のまま返す（CommitDataで昇順化）
}

//+------------------------------------------------------------------+
void CommitData(long &t[], double &v[], const int n, const bool merge)
{
    if(!merge || b_n == 0)
    {
        ArrayResize(b_day, n);
        ArrayResize(b_val, n);
        if(n > 1 && t[0] > t[n - 1])
            for(int i = 0; i < n; i++) { b_day[i] = t[n - 1 - i]; b_val[i] = v[n - 1 - i]; }
        else
            for(int i = 0; i < n; i++) { b_day[i] = t[i]; b_val[i] = v[i]; }
        b_n = n;
        return;
    }
    // マージ: 既存より新しい日だけ追加/更新（APIは直近7日分しか持たないため）
    for(int i = n - 1; i >= 0; i--)   // 降順→古い順に処理
    {
        long dy = t[i];
        if(b_n > 0 && dy == b_day[b_n - 1]) { b_val[b_n - 1] = v[i]; continue; }
        if(b_n == 0 || dy > b_day[b_n - 1])
        {
            ArrayResize(b_day, b_n + 1);
            ArrayResize(b_val, b_n + 1);
            b_day[b_n] = dy;
            b_val[b_n] = v[i];
            b_n++;
        }
    }
}

//+------------------------------------------------------------------+
bool FetchBfx()
{
    char req[], res[];
    string rh;
    ResetLastError();
    int code = WebRequest("GET", ApiUrl, "", 5000, req, res, rh);
    if(code != 200)
    {
        int err = GetLastError();
        Print("Bitfinex API失敗 http=", code, " err=", err,
              err == 4014 ? " →オプション→EA→WebRequest許可URLに https://api-pub.bitfinex.com を追加" : "");
        return false;
    }
    string body = CharArrayToString(res, 0, WHOLE_ARRAY, CP_UTF8);
    long   tt[];
    double tv[];
    int n = ParseBfx(body, tt, tv);
    if(n < 3)
    {
        Print("Bitfinexパース失敗 n=", n, " body先頭: ", StringSubstr(body, 0, 100));
        return false;
    }
    CommitData(tt, tv, n, true);
    Print("Bitfinex API取得: ", n, "日分マージ（総", b_n, "日）");
    if(UpdateCsvCache)
    {
        int fh = FileOpen(CacheFile, FILE_WRITE | FILE_CSV | FILE_ANSI | FILE_COMMON, ',');
        if(fh != INVALID_HANDLE)
        {
            FileWrite(fh, "time", "size");
            for(int i = 0; i < b_n; i++)
                FileWrite(fh, (string)(b_day[i] * 86400), DoubleToString(b_val[i], 2));
            FileClose(fh);
        }
    }
    return true;
}

//+------------------------------------------------------------------+
int OnInit()
{
    trade.SetExpertMagicNumber(MagicNumber);
    long   tt[];
    double tv[];
    if(MQLInfoInteger(MQL_TESTER) || !UseWebRequest)
    {
        int n = LoadCsvInto(BfxFile, tt, tv);
        if(n < 100 && MQLInfoInteger(MQL_TESTER))
        {
            Print("bfx CSV不足（Common\\Files\\", BfxFile, "）: ", n, "件");
            return INIT_FAILED;
        }
        if(n > 0) CommitData(tt, tv, n, false);
    }
    else
    {
        int n = LoadCsvInto(CacheFile, tt, tv);
        if(n < 100) n = LoadCsvInto(BfxFile, tt, tv);
        if(n > 0) CommitData(tt, tv, n, false);
        lastFetchAttempt = TimeCurrent();
        if(!FetchBfx())
            Print("起動時API失敗→CSV代替 ", b_n, "日（エントリー評価時に再試行）");
    }
    if(b_n > 0 && b_day[b_n - 1] < 10000)
    {
        Print("bfx CSVの時刻列が不正: day[last]=", b_day[b_n - 1]);
        return INIT_FAILED;
    }
    Print("BfxRev v1.0 起動 | データ", b_n, "日 | 急減閾値-", DoubleToString(DropPct, 0),
          "%/", LookbackDays, "日 | 保有", HoldDays, "日 | 災害SL",
          DisasterSL_Pct > 0 ? DoubleToString(DisasterSL_Pct, 0) + "%" : "OFF",
          " | ", MQLInfoInteger(MQL_TESTER) ? "テスター(CSV)" : (UseWebRequest ? "ライブ(API自動更新)" : "ライブ(CSV外部更新)"));
    return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| day（UTC日番号）ちょうど、無ければ3日以内の直近前値。無ければ-1   |
//+------------------------------------------------------------------+
double ValAt(long day)
{
    for(int i = b_n - 1; i >= 0; i--)
    {
        if(b_day[i] <= day)
        {
            if(day - b_day[i] <= 3) return b_val[i];
            return -1;
        }
    }
    return -1;
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
bool EnsureData(const datetime bt)
{
    if(MQLInfoInteger(MQL_TESTER)) return (b_n > 0);
    long yday = (long)bt / 86400 - 1;
    if(b_n > 0 && b_day[b_n - 1] >= yday) return true;
    if(!UseWebRequest)
    {
        long   tt[];
        double tv[];
        int n = LoadCsvInto(BfxFile, tt, tv);
        if(n > 0) CommitData(tt, tv, n, false);
        return (b_n > 0 && b_day[b_n - 1] >= yday);
    }
    if(TimeCurrent() - lastFetchAttempt < 3600) return false;
    lastFetchAttempt = TimeCurrent();
    if(FetchBfx()) return (b_day[b_n - 1] >= yday);
    return (b_n > 0 && b_day[b_n - 1] >= yday);
}

//+------------------------------------------------------------------+
void OnTick()
{
    datetime bt = iTime(_Symbol, PERIOD_D1, 0);

    // 決済はデータ非依存・毎tick（フェイルセーフ）
    if(HasPosition())
    {
        if(BarsHeldD1() >= HoldDays) CloseAll();
        evaluatedBar = bt;
        return;
    }
    if(evaluatedBar == bt) return;
    if(!EnsureData(bt)) return;

    long yday = (long)bt / 86400 - 1;
    double v1 = ValAt(yday);
    double v0 = ValAt(yday - LookbackDays);
    evaluatedBar = bt;
    if(v1 <= 0 || v0 <= 0) return;
    double chg = (v1 / v0 - 1) * 100;
    if(chg < -DropPct && CryptoGuardOK())
    {
        double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
        double sl = (DisasterSL_Pct > 0 ? NormalizeDouble(ask * (1 - DisasterSL_Pct / 100), _Digits) : 0);
        if(trade.Buy(LotSize, _Symbol, ask, sl, 0, "BfxRev"))
            Print("[BFXREV BUY] long建玉", DoubleToString(chg, 1), "%/", LookbackDays, "日");
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

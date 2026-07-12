//+------------------------------------------------------------------+
//|  FundingRev_EA.mq5                                               |
//|  BTC funding rate 悲観極端の逆張りロング v1.1（バックログG1）      |
//|  仮説: 永久先物の資金調達率が極端なマイナス＝ショート過密の状態は  |
//|  踏み上げが起きやすく、翌5日のリターンが対照の6倍（事前分析:      |
//|  +4.18%/t=5.13/前後半両プラス）。                                  |
//|  ロジック: 新D1バーで前日のfunding日平均を計算し、閾値未満なら     |
//|  ロング→HoldDays日後に成行クローズ（SL/TPなし＝分析準拠）。        |
//|                                                                  |
//|  データ供給（v1.1でライブ自動更新を内蔵）:                        |
//|  - テスター: Common\Files\funding_btc.csv（ml/fetch_btc_alt_data  |
//|    .pyで生成・Agentワイプ対策でFILE_COMMON）                       |
//|  - ライブ: Binance APIからWebRequestで直接取得（日次・要URL許可:   |
//|    ツール→オプション→EA→WebRequest許可URLに                       |
//|    https://fapi.binance.com を追加）。成功時はキャッシュCSVを      |
//|    更新し、失敗時はキャッシュ→手動CSVへフォールバック。            |
//|    データ欠損時は新規エントリー停止（フェイルセーフ）。決済は      |
//|    データ非依存で必ず実行。                                       |
//+------------------------------------------------------------------+
#property copyright "2026"
#property version   "1.10"
#property strict

#include <Trade\Trade.mqh>

input group "=== シグナル ==="
input string FundingFile     = "funding_btc.csv"; // Common\Files内（バックテスト/手動更新用）
input double Threshold_Pct8h = -0.004;  // 日平均funding閾値（%/8h・5%分位）
input int    HoldDays        = 5;       // 保有日数（D1バー）

input group "=== データ供給（ライブ） ==="
input bool   UseWebRequest = true;      // ライブ時Binance APIから直接取得（テスターは常にCSV）
input string ApiUrl        = "https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&limit=1000";
input bool   UpdateCsvCache = true;     // API取得成功時にキャッシュCSVを更新
input string CacheFile     = "funding_btc_cache.csv"; // Common\Files内（マスターは上書きしない）

input group "=== トレード設定 ==="
input double LotSize     = 0.01;
input double DisasterSL_Pct = 0.0;      // 災害SL（エントリー比%・0=無効＝分析準拠）
input int    MagicNumber = 20260720;

input group "=== 出力設定 ==="
input string ResultFileName = "";
input string EquityLogFile  = "";

CTrade trade;
long     f_time[];
double   f_rate[];
int      f_n = 0;
datetime evaluatedBar = 0;      // このD1バーのシグナル評価済みフラグ
datetime lastFetchAttempt = 0;  // APIリトライ間隔制御（1時間）

//+------------------------------------------------------------------+
//| CSV(time,funding_rate)を一時配列へ読み込み。読めた件数を返す      |
//+------------------------------------------------------------------+
int LoadCsvInto(const string fname, long &t[], double &r[])
{
    int fh = FileOpen(fname, FILE_READ | FILE_CSV | FILE_ANSI | FILE_COMMON, ',');
    if(fh == INVALID_HANDLE) return 0;
    int n = 0;
    ArrayResize(t, 8000);
    ArrayResize(r, 8000);
    FileReadString(fh);   // ヘッダ2フィールドをスキップ
    FileReadString(fh);
    while(!FileIsEnding(fh))
    {
        string ts = FileReadString(fh);
        string rs = FileReadString(fh);
        if(ts == "") break;
        if(n >= ArraySize(t)) { ArrayResize(t, n + 4000); ArrayResize(r, n + 4000); }
        t[n] = StringToInteger(ts);
        r[n] = StringToDouble(rs);
        n++;
    }
    FileClose(fh);
    return n;
}

//+------------------------------------------------------------------+
//| APIレスポンスを一時配列へパース。件数を返す                       |
//| 形式: [{"symbol":"BTCUSDT","fundingTime":1783756800000,           |
//|        "fundingRate":"0.00000942","markPrice":"..."},...]（昇順） |
//+------------------------------------------------------------------+
int ParseFunding(const string body, long &t[], double &r[])
{
    int n = 0;
    ArrayResize(t, 1100);
    ArrayResize(r, 1100);
    int pos = 0;
    while(true)
    {
        int it = StringFind(body, "\"fundingTime\":", pos);
        if(it < 0) break;
        it += 14;
        int ir = StringFind(body, "\"fundingRate\":\"", it);
        if(ir < 0) break;
        ir += 15;
        int ire = StringFind(body, "\"", ir);
        if(ire < 0) break;
        long tms = StringToInteger(StringSubstr(body, it, 20));    // 数字以外で変換停止
        double rate = StringToDouble(StringSubstr(body, ir, ire - ir));
        if(tms > 0)
        {
            if(n >= ArraySize(t)) { ArrayResize(t, n + 500); ArrayResize(r, n + 500); }
            t[n] = tms / 1000;   // ms→s
            r[n] = rate;
            n++;
        }
        pos = ire;
    }
    return n;
}

//+------------------------------------------------------------------+
//| 一時配列を本体へ反映（昇順を保証）                                |
//+------------------------------------------------------------------+
void CommitData(long &t[], double &r[], const int n)
{
    ArrayResize(f_time, n);
    ArrayResize(f_rate, n);
    if(n > 1 && t[0] > t[n - 1])   // 降順で来たら反転
    {
        for(int i = 0; i < n; i++) { f_time[i] = t[n - 1 - i]; f_rate[i] = r[n - 1 - i]; }
    }
    else
    {
        for(int i = 0; i < n; i++) { f_time[i] = t[i]; f_rate[i] = r[i]; }
    }
    f_n = n;
}

//+------------------------------------------------------------------+
bool FetchFunding()
{
    char req[], res[];
    string rh;
    ResetLastError();
    int code = WebRequest("GET", ApiUrl, "", 5000, req, res, rh);
    if(code != 200)
    {
        int err = GetLastError();
        Print("funding API取得失敗 http=", code, " err=", err,
              err == 4014 ? " →ツール→オプション→EA→WebRequest許可URLに https://fapi.binance.com を追加" : "");
        return false;
    }
    string body = CharArrayToString(res, 0, WHOLE_ARRAY, CP_UTF8);
    long   tt[];
    double tr[];
    int n = ParseFunding(body, tt, tr);
    if(n < 3)
    {
        Print("funding APIパース失敗（件数", n, "）: ", StringSubstr(body, 0, 120));
        return false;
    }
    CommitData(tt, tr, n);
    Print("funding API取得: ", n, "件 ",
          TimeToString((datetime)f_time[0], TIME_DATE), "..",
          TimeToString((datetime)f_time[f_n - 1], TIME_DATE | TIME_MINUTES));
    if(UpdateCsvCache)
    {
        int fh = FileOpen(CacheFile, FILE_WRITE | FILE_CSV | FILE_ANSI | FILE_COMMON, ',');
        if(fh != INVALID_HANDLE)
        {
            FileWrite(fh, "time", "funding_rate");
            for(int i = 0; i < f_n; i++)
                FileWrite(fh, (string)f_time[i], DoubleToString(f_rate[i], 8));
            FileClose(fh);
        }
    }
    return true;
}

//+------------------------------------------------------------------+
//| シグナル評価前のデータ確保。テスター=CSV必須、ライブ=API→CSV代替  |
//| falseなら評価を保留（次tickで再試行・リトライは1時間間隔）        |
//+------------------------------------------------------------------+
bool EnsureData(const datetime bt)
{
    if(MQLInfoInteger(MQL_TESTER)) return (f_n > 0);
    long newest = (f_n > 0 ? f_time[f_n - 1] : 0);
    // 前日分が概ね揃っていれば十分（3枠中2枠以上=バー起点-12h以内）
    if(newest >= (long)bt - 12 * 3600) return true;
    if(!UseWebRequest)
    {
        // 外部更新モード: 毎バー、CSVを再読込（日次スクリプトが更新する想定）
        long   tt[];
        double tr[];
        int n = LoadCsvInto(FundingFile, tt, tr);
        if(n > 0) CommitData(tt, tr, n);
        return (f_n > 0 && f_time[f_n - 1] >= (long)bt - 12 * 3600);
    }
    if(TimeCurrent() - lastFetchAttempt < 3600) return false;   // リトライ待ち
    lastFetchAttempt = TimeCurrent();
    if(FetchFunding()) return true;
    // API失敗→キャッシュ→マスターCSVの順で救済
    long   tt[];
    double tr[];
    int n = LoadCsvInto(CacheFile, tt, tr);
    if(n < 3) n = LoadCsvInto(FundingFile, tt, tr);
    if(n > 0 && (f_n == 0 || tt[n - 1] > f_time[f_n - 1])) CommitData(tt, tr, n);
    return (f_n > 0 && f_time[f_n - 1] >= (long)bt - 12 * 3600);
}

//+------------------------------------------------------------------+
int OnInit()
{
    trade.SetExpertMagicNumber(MagicNumber);
    if(MQLInfoInteger(MQL_TESTER) || !UseWebRequest)
    {
        long   tt[];
        double tr[];
        int n = LoadCsvInto(FundingFile, tt, tr);
        if(n < 100 && MQLInfoInteger(MQL_TESTER))
        {
            Print("funding CSVが開けない/不足（Common\\Files\\", FundingFile, "）件数=", n);
            return INIT_FAILED;
        }
        if(n > 0) CommitData(tt, tr, n);
    }
    else
    {
        lastFetchAttempt = TimeCurrent();
        if(!FetchFunding())
        {
            // 起動直後はネットワーク未確立もあり得る→CSVで代替し、以後新バーでAPI再試行
            long   tt[];
            double tr[];
            int n = LoadCsvInto(CacheFile, tt, tr);
            if(n < 3) n = LoadCsvInto(FundingFile, tt, tr);
            if(n > 0) CommitData(tt, tr, n);
            Print("起動時API失敗→CSV代替 ", f_n, "件（エントリー評価時に再試行）");
        }
    }
    if(f_n > 0)
        Print("FundingRev v1.1 起動 | funding ", f_n, "件 ",
              TimeToString((datetime)f_time[0], TIME_DATE), "..",
              TimeToString((datetime)f_time[f_n - 1], TIME_DATE),
              " | 閾値 ", DoubleToString(Threshold_Pct8h, 4), "%/8h | 保有", HoldDays, "日",
              " | ", MQLInfoInteger(MQL_TESTER) ? "テスター(CSV)" : (UseWebRequest ? "ライブ(API自動更新)" : "ライブ(CSV外部更新)"));
    else
        Print("FundingRev v1.1 起動 | fundingデータ未取得（決済は機能・新規はデータ取得後）");
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

//+------------------------------------------------------------------+
//| 保有D1バー数（ポジションのオープン時刻から算出＝再起動に頑健）    |
//+------------------------------------------------------------------+
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

    // 決済はデータ非依存・毎tick判定（フェイルセーフ）
    if(HasPosition())
    {
        if(BarsHeldD1() >= HoldDays) CloseAll();
        evaluatedBar = bt;   // 保有中のバーは新規評価しない（1ポジション制）
        return;
    }

    if(evaluatedBar == bt) return;   // 本日評価済み

    if(!EnsureData(bt)) return;      // データ未達→評価保留（次tick/1時間後に再試行）

    // 前日 [bt-1日, bt) のfunding日平均
    double avg = FundingAvg(bt - 86400, bt);
    evaluatedBar = bt;               // データはあったので本日の評価を確定
    if(avg == EMPTY_VALUE) return;   // 窓内データ無し（2019.09以前など）

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

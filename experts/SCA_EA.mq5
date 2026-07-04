//+------------------------------------------------------------------+
//|  SCA_EA.mq5                                                      |
//|  セッションORB（オープニングレンジ・ブレイクアウト）スキャルパー v1.1 |
//|  アジア時間のレンジを定義し、ロンドン序盤のブレイクを日中完結で取る。|
//|  対象: GOLD / USDJPY / GBPJPY（M15チャート推奨）                  |
//|  既存ブック（H4トレンド/レンジ/キャリー等）と別メカニズム＝       |
//|  セッション構造のボラ拡大を収益源とする。                         |
//|  v1.1: ML確率フィルター（M1×30本の18特徴量ロジスティック回帰で     |
//|  ブレイク方向への2×ATR継続確率を推定し、閾値未満なら見送る）。      |
//|  係数は ml/train.py の自動生成ヘッダ(ml_model_*.mqh)を埋め込み。   |
//|  ※検証は必ず every_tick（スプレッド実費込み）で行うこと。          |
//+------------------------------------------------------------------+
#property copyright "2026"
#property version   "1.10"
#property strict

#include <Trade\Trade.mqh>
#include "ml_model_gold.mqh"
#include "ml_model_usdjpy.mqh"
#include "ml_model_gbpjpy.mqh"

#define ML_NFEAT 18

input group "=== セッション定義（サーバー時間・XM=GMT+2/+3） ==="
input int RangeStartHour = 0;   // レンジ計測開始時（アジア序盤）
input int RangeEndHour   = 9;   // レンジ確定時（ロンドン前）。この時刻以降ブレイク監視
input int TradeEndHour   = 15;  // 新規エントリー最終時（これ以降は新規なし）
input int ForceCloseHour = 22;  // 全決済時（ロールオーバー・スプレッド拡大前）

input group "=== レンジ・フィルター（D1 ATR正規化） ==="
input double MinRange_ATRd = 0.15;  // レンジ幅がD1ATR×この値未満はスキップ（ノイズ日）
input double MaxRange_ATRd = 1.00;  // レンジ幅がD1ATR×この値超はスキップ（既に動いた日）

input group "=== エントリー/エグジット ==="
input double Break_Buffer_ATRd = 0.0;  // ブレイク判定バッファ（D1ATR倍率、0=レンジ端そのまま）
input int    SL_Mode           = 0;    // 0=レンジ反対端 / 1=ATRベース
input double SL_ATRd_Mult      = 0.5;  // SL_Mode=1時: SL距離=D1ATR×この値
input double RR_Ratio          = 1.5;  // TP距離 = SL距離×このRR
input bool   OneShotPerDir     = true; // 1日1方向1回まで（true推奨）

input group "=== D1トレンド方向フィルター（MTF合流のORB適用） ==="
// ブレイク方向がD1のMA200トレンド方向と一致する場合のみエントリー。
// 本ブックで最も成功した改善パターン（PB USDJPY +53%）のセッションORB版。
input bool UseD1TrendFilter = false;
input int  D1Trend_MA       = 200;

input group "=== ML確率フィルター（M1×30本→2×ATR継続確率） ==="
// ブレイク検出時にML確率（ブレイク方向にM1 ATR14×2が10本以内に到達する較正済み確率）
// が閾値未満ならエントリーを見送る。確率が後続バーで閾値を超えれば通常通り入る。
input bool   UseMLFilter  = false;
input double ML_Threshold = 0.40;   // ベース率33-35%に対し「平均より明確に高い」水準

input group "=== スプレッドガード ==="
input int MaxSpreadPoints = 0;  // エントリー時スプレッド上限（points、0=無効）

input group "=== トレード設定 ==="
input double LotSize     = 0.01;
input int    MagicNumber = 20261000;

input group "=== ポジションサイジング（リスク%） ==="
input bool   UseRiskSizing = false;
input double RiskPercent   = 1.0;

input group "=== 出力設定 ==="
input string ResultFileName = "";
input string EquityLogFile  = "";

CTrade trade;
int    atr_d1_handle;
int    ma_d1_handle = INVALID_HANDLE;
double pip_value;
int    ml_atr_handle = INVALID_HANDLE;   // M1 ATR14（ML特徴量用）
double ml_w[ML_NFEAT];
double ml_b = 0.0;

// 日次状態
datetime g_day        = 0;     // 現在の日（00:00）
double   g_rangeHigh  = 0.0;
double   g_rangeLow   = 0.0;
bool     g_rangeReady = false;
bool     g_rangeSkip  = false; // 幅フィルターで当日スキップ
bool     g_tradedLong = false;
bool     g_tradedShort= false;

//+------------------------------------------------------------------+
int OnInit()
{
    pip_value = (_Digits == 3 || _Digits == 5) ? 10 * _Point : _Point;
    atr_d1_handle = iATR(_Symbol, PERIOD_D1, 14);
    if(atr_d1_handle == INVALID_HANDLE)
    {
        Print("D1 ATRハンドルの作成に失敗");
        return INIT_FAILED;
    }
    if(UseD1TrendFilter)
    {
        ma_d1_handle = iMA(_Symbol, PERIOD_D1, D1Trend_MA, 0, MODE_SMA, PRICE_CLOSE);
        if(ma_d1_handle == INVALID_HANDLE) { Print("D1 MAハンドルの作成に失敗"); return INIT_FAILED; }
    }
    if(UseMLFilter)
    {
        ml_atr_handle = iATR(_Symbol, PERIOD_M1, 14);
        if(ml_atr_handle == INVALID_HANDLE) { Print("M1 ATRハンドルの作成に失敗"); return INIT_FAILED; }
        if(StringFind(_Symbol, "GOLD") >= 0 || StringFind(_Symbol, "XAU") >= 0)
            { ArrayCopy(ml_w, ML_W_GOLD);   ml_b = ML_B_GOLD; }
        else if(StringFind(_Symbol, "USDJPY") >= 0)
            { ArrayCopy(ml_w, ML_W_USDJPY); ml_b = ML_B_USDJPY; }
        else if(StringFind(_Symbol, "GBPJPY") >= 0)
            { ArrayCopy(ml_w, ML_W_GBPJPY); ml_b = ML_B_GBPJPY; }
        else { Print("MLフィルター: 未対応銘柄 ", _Symbol); return INIT_FAILED; }
    }
    trade.SetExpertMagicNumber(MagicNumber);
    trade.SetDeviationInPoints(20);
    Print("SCA_EA v1.0 起動 | ", _Symbol,
          " | Range ", RangeStartHour, "-", RangeEndHour, "h / TradeEnd ", TradeEndHour,
          "h / Close ", ForceCloseHour, "h | RangeFilter ", MinRange_ATRd, "-", MaxRange_ATRd, "×ATRd",
          " | SL_Mode=", SL_Mode, " RR=", RR_Ratio);
    return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
    IndicatorRelease(atr_d1_handle);
    if(ma_d1_handle != INVALID_HANDLE) IndicatorRelease(ma_d1_handle);
    if(ml_atr_handle != INVALID_HANDLE) IndicatorRelease(ml_atr_handle);
}

//+------------------------------------------------------------------+
//| ML特徴量（train.py build_features()と厳密一致・ロング基準・M1）    |
//| バーt = 確定した最新M1バー（shift 1）                              |
//+------------------------------------------------------------------+
double MLSampleStd(const double &v[], int start, int count)
{
    if(count < 2) return 0.0;
    double mean = 0.0;
    for(int i = start; i < start + count; i++) mean += v[i];
    mean /= count;
    double ss = 0.0;
    for(int i = start; i < start + count; i++) ss += (v[i] - mean) * (v[i] - mean);
    return MathSqrt(ss / (count - 1));
}

bool ComputeMLFeatures(double &x[])
{
    double c[], o[], h[], l[];
    long   tv[];
    double atrBuf[];
    ArraySetAsSeries(c, true);  ArraySetAsSeries(o, true);
    ArraySetAsSeries(h, true);  ArraySetAsSeries(l, true);
    ArraySetAsSeries(tv, true); ArraySetAsSeries(atrBuf, true);
    int need = 31;   // c[0]=shift1(バーt) .. c[30]=shift31
    if(CopyClose(_Symbol, PERIOD_M1, 1, need, c) != need) return false;
    if(CopyOpen(_Symbol, PERIOD_M1, 1, need, o)  != need) return false;
    if(CopyHigh(_Symbol, PERIOD_M1, 1, need, h)  != need) return false;
    if(CopyLow(_Symbol, PERIOD_M1, 1, need, l)   != need) return false;
    if(CopyTickVolume(_Symbol, PERIOD_M1, 1, need, tv) != need) return false;
    if(CopyBuffer(ml_atr_handle, 0, 1, 3, atrBuf) != 3) return false;

    double atr = atrBuf[0];
    if(atr <= 0 || atrBuf[1] <= 0 || atrBuf[2] <= 0) return false;

    x[0] = (c[0] - c[1])  / atr;                             // mom1
    x[1] = (c[0] - c[3])  / atr;                             // mom3
    x[2] = (c[0] - c[5])  / atr;                             // mom5
    x[3] = (c[0] - c[10]) / atr;                             // mom10
    x[4] = (c[0] - c[30]) / atr;                             // mom30
    x[5] = (c[0] - o[0]) / atr;                              // body0
    x[6] = (h[0] - MathMax(c[0], o[0])) / atr;               // upw0
    x[7] = (MathMin(c[0], o[0]) - l[0]) / atr;               // dnw0
    x[8] = (c[1] - o[1]) / atrBuf[1];                        // body1
    x[9] = (c[2] - o[2]) / atrBuf[2];                        // body2
    double hh = h[0], ll = l[0];
    for(int i = 1; i < 30; i++)
    {
        if(h[i] > hh) hh = h[i];
        if(l[i] < ll) ll = l[i];
    }
    double rng = hh - ll;
    x[10] = (rng > 0 ? (c[0] - ll) / rng : 0.5);             // rangepos
    x[11] = rng / atr / 30.0 * 10.0;                         // rangew
    double ret1[30];
    for(int i = 0; i < 30; i++) ret1[i] = c[i] - c[i + 1];
    double rv10 = MLSampleStd(ret1, 0, 10);
    double rv30 = MLSampleStd(ret1, 0, 30);
    x[12] = (rv30 > 0 ? rv10 / rv30 : 1.0);                  // volratio
    int up10 = 0, up30 = 0;
    for(int i = 0; i < 30; i++)
    {
        if(c[i] > o[i]) { up30++; if(i < 10) up10++; }
    }
    x[13] = up10 / 10.0;                                     // upshare10
    x[14] = up30 / 30.0;                                     // upshare30
    double tvm = 0.0;
    for(int i = 0; i < 30; i++) tvm += (double)tv[i];
    tvm /= 30.0;
    x[15] = (tvm > 0 ? (double)tv[0] / tvm : 1.0);           // tvr
    MqlDateTime st;
    TimeToStruct(iTime(_Symbol, PERIOD_M1, 1), st);
    double hr = st.hour + st.min / 60.0;
    x[16] = MathSin(2.0 * M_PI * hr / 24.0);                 // hsin
    x[17] = MathCos(2.0 * M_PI * hr / 24.0);                 // hcos
    return true;
}

//+------------------------------------------------------------------+
//| ブレイク方向のML確率（ショートは対称化: train.pyと一致）           |
//+------------------------------------------------------------------+
double GetMLProb(bool isLong)
{
    double x[ML_NFEAT];
    if(!ComputeMLFeatures(x)) return -1.0;   // 計算不能（フィルター判定不可＝見送り）
    if(!isLong)
    {
        // 符号反転: mom*, body0/1/2
        x[0] = -x[0]; x[1] = -x[1]; x[2] = -x[2]; x[3] = -x[3]; x[4] = -x[4];
        x[5] = -x[5]; x[8] = -x[8]; x[9] = -x[9];
        double tmp = x[6]; x[6] = x[7]; x[7] = tmp;          // upw0 <-> dnw0
        x[10] = 1.0 - x[10]; x[13] = 1.0 - x[13]; x[14] = 1.0 - x[14];
    }
    double z = ml_b;
    for(int i = 0; i < ML_NFEAT; i++) z += ml_w[i] * x[i];
    return 1.0 / (1.0 + MathExp(-z));
}

//+------------------------------------------------------------------+
bool HasPosition(ENUM_POSITION_TYPE type)
{
    for(int i = PositionsTotal() - 1; i >= 0; i--)
        if(PositionGetSymbol(i) == _Symbol &&
           PositionGetInteger(POSITION_MAGIC) == MagicNumber &&
           PositionGetInteger(POSITION_TYPE)  == type)
            return true;
    return false;
}

void CloseAll()
{
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        ulong ticket = PositionGetTicket(i);
        if(PositionGetSymbol(i) == _Symbol &&
           PositionGetInteger(POSITION_MAGIC) == MagicNumber)
            trade.PositionClose(ticket);
    }
}

//+------------------------------------------------------------------+
double CalcLot(double sl_dist_price)
{
    if(!UseRiskSizing || sl_dist_price <= 0.0)
        return LotSize;
    double equity    = AccountInfoDouble(ACCOUNT_EQUITY);
    double riskMoney = equity * RiskPercent / 100.0;
    double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
    double tickSize  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
    if(tickValue <= 0.0 || tickSize <= 0.0) return LotSize;
    double moneyPerLot = (sl_dist_price / tickSize) * tickValue;
    if(moneyPerLot <= 0.0) return LotSize;
    double lot = riskMoney / moneyPerLot;
    double minLot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
    double maxLot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
    double stepLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
    if(stepLot > 0.0) lot = MathFloor(lot / stepLot) * stepLot;
    lot = MathMax(minLot, MathMin(maxLot, lot));
    return lot;
}

//+------------------------------------------------------------------+
// 当日 RangeStartHour〜RangeEndHour のレンジをM15バーから計算
bool ComputeRange(datetime day_start)
{
    datetime t_from = day_start + RangeStartHour * 3600;
    datetime t_to   = day_start + RangeEndHour   * 3600;   // 排他（この時刻のバーは含めない）
    double hi = -DBL_MAX, lo = DBL_MAX;
    int bars = Bars(_Symbol, PERIOD_CURRENT);
    for(int sft = 1; sft < 200; sft++)   // 直近200本以内に当日分は収まる（M15×9h=36本）
    {
        if(sft >= bars) break;
        datetime bt = iTime(_Symbol, PERIOD_CURRENT, sft);
        if(bt < t_from) break;           // 窓より過去に出たら終了
        if(bt >= t_to) continue;         // 窓より未来（レンジ後）はスキップ
        double h = iHigh(_Symbol, PERIOD_CURRENT, sft);
        double l = iLow(_Symbol, PERIOD_CURRENT, sft);
        if(h > hi) hi = h;
        if(l < lo) lo = l;
    }
    if(hi <= -DBL_MAX || lo >= DBL_MAX) return false;
    g_rangeHigh = hi;
    g_rangeLow  = lo;
    return true;
}

//+------------------------------------------------------------------+
void OnTick()
{
    static datetime last_bar_time = 0;
    datetime bar_time = iTime(_Symbol, PERIOD_CURRENT, 0);
    if(bar_time == last_bar_time) return;
    last_bar_time = bar_time;

    MqlDateTime dt;
    TimeToStruct(bar_time, dt);
    datetime day_start = bar_time - (dt.hour * 3600 + dt.min * 60 + dt.sec);

    // 日付が変わったら状態リセット
    if(day_start != g_day)
    {
        g_day = day_start;
        g_rangeReady = false;
        g_rangeSkip  = false;
        g_tradedLong = false;
        g_tradedShort= false;
    }

    // 強制クローズ時刻
    if(dt.hour >= ForceCloseHour)
    {
        CloseAll();
        return;
    }

    // レンジ確定（RangeEndHour以降に一度だけ計算）
    if(!g_rangeReady && dt.hour >= RangeEndHour)
    {
        if(!ComputeRange(day_start)) return;
        g_rangeReady = true;

        // 幅フィルター（D1 ATR正規化）
        double atrd_buf[];
        ArraySetAsSeries(atrd_buf, true);
        if(CopyBuffer(atr_d1_handle, 0, 1, 1, atrd_buf) < 1) return;
        double atrd = atrd_buf[0];
        double width = g_rangeHigh - g_rangeLow;
        if(atrd <= 0.0 || width < MinRange_ATRd * atrd || width > MaxRange_ATRd * atrd)
            g_rangeSkip = true;
    }
    if(!g_rangeReady || g_rangeSkip) return;

    // エントリー時間帯チェック
    if(dt.hour < RangeEndHour || dt.hour >= TradeEndHour) return;

    // D1 ATR（バッファ/SL用）
    double atrd_buf2[];
    ArraySetAsSeries(atrd_buf2, true);
    if(CopyBuffer(atr_d1_handle, 0, 1, 1, atrd_buf2) < 1) return;
    double atrd = atrd_buf2[0];
    if(atrd <= 0.0) return;

    double buffer  = Break_Buffer_ATRd * atrd;
    double close1  = iClose(_Symbol, PERIOD_CURRENT, 1);

    // スプレッドガード
    if(MaxSpreadPoints > 0)
    {
        long spr = SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
        if(spr > MaxSpreadPoints) return;
    }

    bool has_buy  = HasPosition(POSITION_TYPE_BUY);
    bool has_sell = HasPosition(POSITION_TYPE_SELL);

    // D1トレンド方向フィルター
    bool d1_ok_buy = true, d1_ok_sell = true;
    if(UseD1TrendFilter)
    {
        double ma_buf[];
        ArraySetAsSeries(ma_buf, true);
        if(CopyBuffer(ma_d1_handle, 0, 1, 1, ma_buf) < 1) return;
        double d1_close = iClose(_Symbol, PERIOD_D1, 1);
        d1_ok_buy  = (d1_close > ma_buf[0]);
        d1_ok_sell = (d1_close < ma_buf[0]);
    }

    // 上抜けブレイク → 買い（MLフィルター有効時はブレイク方向の継続確率が閾値以上の場合のみ）
    if(d1_ok_buy && close1 > g_rangeHigh + buffer && !has_buy && !(OneShotPerDir && g_tradedLong)
       && (!UseMLFilter || GetMLProb(true) >= ML_Threshold))
    {
        double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
        double sl  = (SL_Mode == 0) ? g_rangeLow : ask - SL_ATRd_Mult * atrd;
        double sl_dist = ask - sl;
        if(sl_dist > 0)
        {
            double tp = NormalizeDouble(ask + RR_Ratio * sl_dist, _Digits);
            if(trade.Buy(CalcLot(sl_dist), _Symbol, ask, NormalizeDouble(sl, _Digits), tp, "SCA-L"))
            {
                g_tradedLong = true;
                Print("[SCA BUY] range=", DoubleToString(g_rangeLow,_Digits), "-",
                      DoubleToString(g_rangeHigh,_Digits), " close=", close1);
            }
        }
    }
    // 下抜けブレイク → 売り（MLフィルター有効時はブレイク方向の継続確率が閾値以上の場合のみ）
    if(d1_ok_sell && close1 < g_rangeLow - buffer && !has_sell && !(OneShotPerDir && g_tradedShort)
       && (!UseMLFilter || GetMLProb(false) >= ML_Threshold))
    {
        double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
        double sl  = (SL_Mode == 0) ? g_rangeHigh : bid + SL_ATRd_Mult * atrd;
        double sl_dist = sl - bid;
        if(sl_dist > 0)
        {
            double tp = NormalizeDouble(bid - RR_Ratio * sl_dist, _Digits);
            if(trade.Sell(CalcLot(sl_dist), _Symbol, bid, NormalizeDouble(sl, _Digits), tp, "SCA-S"))
            {
                g_tradedShort = true;
                Print("[SCA SELL] range=", DoubleToString(g_rangeLow,_Digits), "-",
                      DoubleToString(g_rangeHigh,_Digits), " close=", close1);
            }
        }
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

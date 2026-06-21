//+------------------------------------------------------------------+
//|  RSI_Reversal.mq5                                                |
//|  RSI逆張り + BB2.5σ OR + ダブルトップ/ボトム v2.5               |
//+------------------------------------------------------------------+
#property copyright "2026"
#property version   "2.50"
#property strict

#include <Trade\Trade.mqh>

//--- 入力パラメータ
input group "=== トレンドフィルター（MA） ==="
input int            MA_Period = 200;
input ENUM_MA_METHOD MA_Method = MODE_SMA;

input group "=== ボリンジャーバンド設定 ==="
input int    BB_Period    = 20;
input double BB_Deviation = 2.5;

input group "=== RSI設定 ==="
input int    RSI_Period            = 14;
input double RSI_OverboughtExtreme = 75.0;
input double RSI_Overbought        = 72.5;
input double RSI_OversoldExtreme   = 27.5;
input double RSI_Oversold          = 30.0;

input group "=== ダブルトップ/ボトム設定 ==="
input bool   UseDoublePattern = true; // ダブルパターン戦略を使用する
input int    Swing_Lookback   = 3;    // スウィング判定の前後本数
input int    DP_Pattern_Bars  = 60;   // パターン検索範囲（本数）
input double DP_Tolerance_ATR = 1.0; // 同レベル許容幅（ATR倍率）

input group "=== トレード設定 ==="
input double LotSize         = 0.01;
input int    StopLoss_Pips   = 50;
input int    TakeProfit_Pips = 100;
input int    MagicNumber     = 20260603;

input group "=== ATRベース動的SL/TP ==="
input bool   UseATRStopLoss    = false; // ATRベースの動的SLを使用する（trueで固定SL/TPを無視）
input double ATR_SL_Multiplier = 1.5;  // SL距離 = ATR × この倍率
input double ATR_RR_Ratio      = 2.0;  // TP距離 = SL距離 × このRR比

input group "=== ADXフィルター ==="
input bool   UseADXFilter  = false; // ADXフィルターを使用する（強トレンド時エントリー禁止）
input int    ADX_Period     = 14;   // ADX期間
input double ADX_Threshold = 25.0;  // この値以上は強トレンドと判断してスキップ

input group "=== 時間帯フィルター（GMT基準） ==="
input bool UseTimeFilter   = false; // 時間帯フィルターを使用する
input int  FilterStartHour = 8;     // エントリー許可開始時刻（GMT時）
input int  FilterEndHour   = 20;    // エントリー許可終了時刻（GMT時）

input group "=== 出力設定 ==="
input string ResultFileName = "";

//--- グローバル変数
CTrade trade;
int    rsi_handle;
int    ma_handle;
int    bb_handle;
int    atr_handle;
int    adx_handle;
double pip_value;

bool rsi_was_overbought = false;
bool rsi_was_oversold   = false;
bool price_above_bb     = false;
bool price_below_bb     = false;

//+------------------------------------------------------------------+
int OnInit()
{
    pip_value  = (_Digits == 3 || _Digits == 5) ? 10 * _Point : _Point;
    rsi_handle = iRSI(_Symbol, PERIOD_CURRENT, RSI_Period, PRICE_CLOSE);
    ma_handle  = iMA(_Symbol, PERIOD_CURRENT, MA_Period, 0, MA_Method, PRICE_CLOSE);
    bb_handle  = iBands(_Symbol, PERIOD_CURRENT, BB_Period, 0, BB_Deviation, PRICE_CLOSE);
    atr_handle = iATR(_Symbol, PERIOD_CURRENT, 14);
    adx_handle = iADX(_Symbol, PERIOD_CURRENT, ADX_Period);

    if(rsi_handle == INVALID_HANDLE || ma_handle == INVALID_HANDLE ||
       bb_handle  == INVALID_HANDLE || atr_handle == INVALID_HANDLE ||
       adx_handle == INVALID_HANDLE)
    {
        Print("インジケーターハンドルの作成に失敗しました");
        return INIT_FAILED;
    }
    trade.SetExpertMagicNumber(MagicNumber);
    trade.SetDeviationInPoints(10);
    Print("RSI_Reversal v2.5 起動 | DoublePattern=", UseDoublePattern ? "ON" : "OFF",
          " | ATR-SL=", UseATRStopLoss ? StringFormat("ON(x%.1f RR%.1f)", ATR_SL_Multiplier, ATR_RR_Ratio) : "OFF",
          " | ADX=", UseADXFilter ? StringFormat("ON(<%g)", ADX_Threshold) : "OFF",
          " | TimeFilter=", UseTimeFilter ? StringFormat("ON(%d-%d GMT)", FilterStartHour, FilterEndHour) : "OFF");
    return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
    IndicatorRelease(rsi_handle);
    IndicatorRelease(ma_handle);
    IndicatorRelease(bb_handle);
    IndicatorRelease(atr_handle);
    IndicatorRelease(adx_handle);
}

//+------------------------------------------------------------------+
// スウィングハイ判定（ArraySetAsSeries=true: インデックス小=新しい）
bool IsSwingHigh(const double &arr[], int idx, int lb, int sz)
{
    if(idx < lb || idx + lb >= sz) return false;
    double v = arr[idx];
    for(int k = 1; k <= lb; k++)
        if(arr[idx - k] >= v || arr[idx + k] >= v) return false;
    return true;
}

// スウィングロー判定
bool IsSwingLow(const double &arr[], int idx, int lb, int sz)
{
    if(idx < lb || idx + lb >= sz) return false;
    double v = arr[idx];
    for(int k = 1; k <= lb; k++)
        if(arr[idx - k] <= v || arr[idx + k] <= v) return false;
    return true;
}

// ダブルボトム検出 → ネックライン価格を返す
bool DetectDoubleBottom(const double &high[], const double &low[],
                        int pb, int lb, double atr_val, double tol,
                        double &neck_out)
{
    int sz = ArraySize(low);

    // L1: 最新のスウィングロー（インデックスが小さい方）
    int l1 = -1;
    for(int i = lb; i < pb - lb; i++)
        if(IsSwingLow(low, i, lb, sz)) { l1 = i; break; }
    if(l1 < 0) return false;

    // L2: L1より古いスウィングロー
    int l2 = -1;
    for(int i = l1 + lb + 1; i < pb; i++)
        if(IsSwingLow(low, i, lb, sz)) { l2 = i; break; }
    if(l2 < 0) return false;

    // 2つの安値が同レベルか
    if(MathAbs(low[l1] - low[l2]) > atr_val * tol) return false;

    // L1とL2の間の最高スウィングハイ = ネックライン
    double neck = 0;
    for(int i = l1 + 1; i < l2; i++)
        if(IsSwingHigh(high, i, lb, sz) && high[i] > neck)
            neck = high[i];
    if(neck <= 0) return false;

    neck_out = neck;
    return true;
}

// ダブルトップ検出 → ネックライン価格を返す
bool DetectDoubleTop(const double &high[], const double &low[],
                     int pb, int lb, double atr_val, double tol,
                     double &neck_out)
{
    int sz = ArraySize(high);

    // H1: 最新のスウィングハイ
    int h1 = -1;
    for(int i = lb; i < pb - lb; i++)
        if(IsSwingHigh(high, i, lb, sz)) { h1 = i; break; }
    if(h1 < 0) return false;

    // H2: H1より古いスウィングハイ
    int h2 = -1;
    for(int i = h1 + lb + 1; i < pb; i++)
        if(IsSwingHigh(high, i, lb, sz)) { h2 = i; break; }
    if(h2 < 0) return false;

    // 2つの高値が同レベルか
    if(MathAbs(high[h1] - high[h2]) > atr_val * tol) return false;

    // H1とH2の間の最低スウィングロー = ネックライン
    double neck = DBL_MAX;
    for(int i = h1 + 1; i < h2; i++)
        if(IsSwingLow(low, i, lb, sz) && low[i] < neck)
            neck = low[i];
    if(neck == DBL_MAX) return false;

    neck_out = neck;
    return true;
}

//+------------------------------------------------------------------+
void OnTick()
{
    static datetime last_bar_time = 0;
    datetime current_bar_time = iTime(_Symbol, PERIOD_CURRENT, 0);
    if(current_bar_time == last_bar_time) return;
    last_bar_time = current_bar_time;

    // インジケーター値（前確定足）
    double rsi_buf[], ma_buf[], bb_upper[], bb_lower[], atr_buf[];
    ArraySetAsSeries(rsi_buf,  true);
    ArraySetAsSeries(ma_buf,   true);
    ArraySetAsSeries(bb_upper, true);
    ArraySetAsSeries(bb_lower, true);
    ArraySetAsSeries(atr_buf,  true);

    if(CopyBuffer(rsi_handle, 0, 1, 1, rsi_buf)  < 1) return;
    if(CopyBuffer(ma_handle,  0, 1, 1, ma_buf)   < 1) return;
    if(CopyBuffer(bb_handle,  1, 1, 1, bb_upper) < 1) return;
    if(CopyBuffer(bb_handle,  2, 1, 1, bb_lower) < 1) return;
    if(CopyBuffer(atr_handle, 0, 1, 1, atr_buf)  < 1) return;

    double rsi        = rsi_buf[0];
    double ma         = ma_buf[0];
    double atr        = atr_buf[0];
    double close_prev = iClose(_Symbol, PERIOD_CURRENT, 1);

    // High/Low配列（ダブルパターン用）
    int    buf_size = DP_Pattern_Bars + Swing_Lookback + 5;
    double high_buf[], low_buf[];
    ArraySetAsSeries(high_buf, true);
    ArraySetAsSeries(low_buf,  true);
    if(CopyHigh(_Symbol, PERIOD_CURRENT, 1, buf_size, high_buf) < buf_size) return;
    if(CopyLow( _Symbol, PERIOD_CURRENT, 1, buf_size, low_buf)  < buf_size) return;

    // トレンド判断（RSI/BBシグナル用）
    bool uptrend   = (close_prev > ma);
    bool downtrend = (close_prev < ma);

    // RSIフラグ更新
    if(rsi >= RSI_OverboughtExtreme) rsi_was_overbought = true;
    if(rsi <= RSI_OversoldExtreme)   rsi_was_oversold   = true;

    // BBフラグ更新
    if(close_prev >= bb_upper[0]) price_above_bb = true;
    if(close_prev <= bb_lower[0]) price_below_bb = true;

    // --- シグナル判定 ---

    // RSIシグナル（MA200フィルターあり）
    bool rsi_buy  = rsi_was_oversold   && (rsi >= RSI_Oversold);
    bool rsi_sell = rsi_was_overbought && (rsi <= RSI_Overbought);

    // BBシグナル（MA200フィルターあり）
    bool bb_buy  = price_below_bb && (close_prev > bb_lower[0]);
    bool bb_sell = price_above_bb && (close_prev < bb_upper[0]);

    // ダブルパターンシグナル（MA200フィルターなし）
    bool dp_buy = false, dp_sell = false;
    double neck_buy = 0, neck_sell = 0;
    if(UseDoublePattern)
    {
        if(DetectDoubleBottom(high_buf, low_buf, DP_Pattern_Bars, Swing_Lookback, atr, DP_Tolerance_ATR, neck_buy))
            dp_buy = (close_prev >= neck_buy);

        if(DetectDoubleTop(high_buf, low_buf, DP_Pattern_Bars, Swing_Lookback, atr, DP_Tolerance_ATR, neck_sell))
            dp_sell = (close_prev <= neck_sell);
    }

    // ADXフィルター（強トレンド時はエントリー禁止）
    bool adx_ok = true;
    if(UseADXFilter)
    {
        double adx_buf[];
        ArraySetAsSeries(adx_buf, true);
        if(CopyBuffer(adx_handle, 0, 1, 1, adx_buf) < 1) return;
        adx_ok = (adx_buf[0] < ADX_Threshold);
    }

    // 時間帯フィルター（GMT基準）
    bool in_time = true;
    if(UseTimeFilter)
    {
        MqlDateTime gmt;
        TimeGMT(gmt);
        in_time = (gmt.hour >= FilterStartHour && gmt.hour < FilterEndHour);
    }

    // 最終エントリー条件（RSI/BB はMA200フィルター付き、DPは単独）
    // RSI/BB/DoublePattern 全てMA200フィルター適用
    bool entry_buy  = adx_ok && in_time && uptrend   && (rsi_buy  || bb_buy  || dp_buy);
    bool entry_sell = adx_ok && in_time && downtrend && (rsi_sell || bb_sell || dp_sell);

    bool has_buy  = HasPosition(POSITION_TYPE_BUY);
    bool has_sell = HasPosition(POSITION_TYPE_SELL);

    double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
    double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
    double sl_dist, tp_dist;
    if(UseATRStopLoss)
    {
        sl_dist = atr * ATR_SL_Multiplier;
        tp_dist = sl_dist * ATR_RR_Ratio;
    }
    else
    {
        sl_dist = StopLoss_Pips   * pip_value;
        tp_dist = TakeProfit_Pips * pip_value;
    }

    // 買いエントリー
    if(entry_buy && !has_buy)
    {
        if(has_sell) ClosePositions(POSITION_TYPE_SELL);
        double sl = NormalizeDouble(ask - sl_dist, _Digits);
        double tp = NormalizeDouble(ask + tp_dist, _Digits);
        string reason = dp_buy ? (rsi_buy || bb_buy ? "RSI/BB+DP" : "DoubleBottom")
                                : (rsi_buy ? (bb_buy ? "RSI+BB" : "RSI") : "BB");
        if(trade.Buy(LotSize, _Symbol, ask, sl, tp, reason))
            Print("[BUY] reason=", reason, " RSI=", DoubleToString(rsi,1),
                  " close=", close_prev, " neck=", DoubleToString(neck_buy, _Digits));
        if(rsi_buy) rsi_was_oversold = false;
        if(bb_buy)  price_below_bb   = false;
    }

    // 売りエントリー
    if(entry_sell && !has_sell)
    {
        if(has_buy) ClosePositions(POSITION_TYPE_BUY);
        double sl = NormalizeDouble(bid + sl_dist, _Digits);
        double tp = NormalizeDouble(bid - tp_dist, _Digits);
        string reason = dp_sell ? (rsi_sell || bb_sell ? "RSI/BB+DP" : "DoubleTop")
                                 : (rsi_sell ? (bb_sell ? "RSI+BB" : "RSI") : "BB");
        if(trade.Sell(LotSize, _Symbol, bid, sl, tp, reason))
            Print("[SELL] reason=", reason, " RSI=", DoubleToString(rsi,1),
                  " close=", close_prev, " neck=", DoubleToString(neck_sell, _Digits));
        if(rsi_sell) rsi_was_overbought = false;
        if(bb_sell)  price_above_bb     = false;
    }
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

//+------------------------------------------------------------------+
void ClosePositions(ENUM_POSITION_TYPE type)
{
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        ulong ticket = PositionGetTicket(i);
        if(PositionGetSymbol(i) == _Symbol &&
           PositionGetInteger(POSITION_MAGIC) == MagicNumber &&
           PositionGetInteger(POSITION_TYPE)  == type)
            trade.PositionClose(ticket);
    }
}

//+------------------------------------------------------------------+
double OnTester()
{
    double pf = TesterStatistics(STAT_PROFIT_FACTOR);
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

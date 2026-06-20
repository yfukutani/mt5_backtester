//+------------------------------------------------------------------+
//|  RSI_Reversal.mq5                                                |
//|  RSI逆張り + BBバンド再入り（OR条件）v2.1                         |
//|  買い: (RSIゾーン脱出) OR (BB下限割れ→回復) + MA200上             |
//|  売り: (RSIゾーン脱出) OR (BB上限超え→回復) + MA200下             |
//+------------------------------------------------------------------+
#property copyright "2026"
#property version   "2.10"
#property strict

#include <Trade\Trade.mqh>

//--- 入力パラメータ
input group "=== トレンドフィルター（MA） ==="
input int              MA_Period   = 200;
input ENUM_MA_METHOD   MA_Method   = MODE_SMA;

input group "=== ボリンジャーバンド設定 ==="
input int    BB_Period    = 20;
input double BB_Deviation = 2.0;

input group "=== RSI設定 ==="
input int    RSI_Period            = 14;
input double RSI_OverboughtExtreme = 75.0;
input double RSI_Overbought        = 72.5;
input double RSI_OversoldExtreme   = 27.5;
input double RSI_Oversold          = 30.0;

input group "=== トレード設定 ==="
input double LotSize         = 0.01;
input int    StopLoss_Pips   = 50;
input int    TakeProfit_Pips = 100;
input int    MagicNumber     = 20260603;

input group "=== 出力設定 ==="
input string ResultFileName  = "";

//--- グローバル変数
CTrade trade;
int    rsi_handle;
int    ma_handle;
int    bb_handle;
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

    if(rsi_handle == INVALID_HANDLE || ma_handle == INVALID_HANDLE || bb_handle == INVALID_HANDLE)
    {
        Print("インジケーターハンドルの作成に失敗しました");
        return INIT_FAILED;
    }

    trade.SetExpertMagicNumber(MagicNumber);
    trade.SetDeviationInPoints(10);

    Print("RSI_Reversal v2.1 起動",
          " | MA(", MA_Period, ")",
          " | BB(", BB_Period, ",", BB_Deviation, "σ)",
          " | RSI(", RSI_Period, ") OBE=", RSI_OverboughtExtreme,
          " OB=", RSI_Overbought, " OSE=", RSI_OversoldExtreme, " OS=", RSI_Oversold,
          " | SL=", StopLoss_Pips, " TP=", TakeProfit_Pips);
    return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
    if(rsi_handle != INVALID_HANDLE) IndicatorRelease(rsi_handle);
    if(ma_handle  != INVALID_HANDLE) IndicatorRelease(ma_handle);
    if(bb_handle  != INVALID_HANDLE) IndicatorRelease(bb_handle);
}

//+------------------------------------------------------------------+
void OnTick()
{
    static datetime last_bar_time = 0;
    datetime current_bar_time = iTime(_Symbol, PERIOD_CURRENT, 0);
    if(current_bar_time == last_bar_time) return;
    last_bar_time = current_bar_time;

    // インジケーター値を取得（前確定足）
    double rsi_buf[], ma_buf[], bb_upper[], bb_lower[];
    ArraySetAsSeries(rsi_buf,  true);
    ArraySetAsSeries(ma_buf,   true);
    ArraySetAsSeries(bb_upper, true);
    ArraySetAsSeries(bb_lower, true);

    if(CopyBuffer(rsi_handle, 0, 1, 1, rsi_buf)  < 1) return;
    if(CopyBuffer(ma_handle,  0, 1, 1, ma_buf)   < 1) return;
    if(CopyBuffer(bb_handle,  1, 1, 1, bb_upper) < 1) return;
    if(CopyBuffer(bb_handle,  2, 1, 1, bb_lower) < 1) return;

    double rsi        = rsi_buf[0];
    double ma         = ma_buf[0];
    double close_prev = iClose(_Symbol, PERIOD_CURRENT, 1);

    // トレンド判断
    bool uptrend   = (close_prev > ma);
    bool downtrend = (close_prev < ma);

    // --- フラグ更新（エントリー判定より先に実行）---

    // RSI極端ゾーン到達を記録
    if(rsi >= RSI_OverboughtExtreme) rsi_was_overbought = true;
    if(rsi <= RSI_OversoldExtreme)   rsi_was_oversold   = true;

    // BB超過を記録（前確定足終値がバンド外に出た時点）
    if(close_prev >= bb_upper[0]) price_above_bb = true;
    if(close_prev <= bb_lower[0]) price_below_bb = true;

    // --- シグナル判定 ---

    // RSIシグナル（ゾーン脱出）
    bool rsi_buy_signal  = rsi_was_oversold   && (rsi >= RSI_Oversold);
    bool rsi_sell_signal = rsi_was_overbought && (rsi <= RSI_Overbought);

    // BBシグナル（バンド外→バンド内への回復）
    // close_prevがBB外に出た実績あり かつ 現在足でバンド内に戻っている
    bool bb_buy_signal  = price_below_bb && (close_prev > bb_lower[0]);
    bool bb_sell_signal = price_above_bb && (close_prev < bb_upper[0]);

    bool has_buy  = HasPosition(POSITION_TYPE_BUY);
    bool has_sell = HasPosition(POSITION_TYPE_SELL);

    double ask     = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
    double bid     = SymbolInfoDouble(_Symbol, SYMBOL_BID);
    double sl_dist = StopLoss_Pips   * pip_value;
    double tp_dist = TakeProfit_Pips * pip_value;

    // 買いエントリー（RSI OR BB、MA200上昇トレンドのみ）
    if(uptrend && (rsi_buy_signal || bb_buy_signal) && !has_buy)
    {
        if(has_sell) ClosePositions(POSITION_TYPE_SELL);
        double sl = NormalizeDouble(ask - sl_dist, _Digits);
        double tp = NormalizeDouble(ask + tp_dist, _Digits);
        string reason = rsi_buy_signal ? (bb_buy_signal ? "RSI+BB" : "RSI") : "BB";
        if(trade.Buy(LotSize, _Symbol, ask, sl, tp, reason))
            Print("[BUY] reason=", reason,
                  " RSI=", DoubleToString(rsi, 1),
                  " close=", close_prev,
                  " BB_lower=", DoubleToString(bb_lower[0], 3));
        if(rsi_buy_signal) rsi_was_oversold = false;
        if(bb_buy_signal)  price_below_bb   = false;
    }

    // 売りエントリー（RSI OR BB、MA200下降トレンドのみ）
    if(downtrend && (rsi_sell_signal || bb_sell_signal) && !has_sell)
    {
        if(has_buy) ClosePositions(POSITION_TYPE_BUY);
        double sl = NormalizeDouble(bid + sl_dist, _Digits);
        double tp = NormalizeDouble(bid - tp_dist, _Digits);
        string reason = rsi_sell_signal ? (bb_sell_signal ? "RSI+BB" : "RSI") : "BB";
        if(trade.Sell(LotSize, _Symbol, bid, sl, tp, reason))
            Print("[SELL] reason=", reason,
                  " RSI=", DoubleToString(rsi, 1),
                  " close=", close_prev,
                  " BB_upper=", DoubleToString(bb_upper[0], 3));
        if(rsi_sell_signal) rsi_was_overbought = false;
        if(bb_sell_signal)  price_above_bb     = false;
    }
}

//+------------------------------------------------------------------+
bool HasPosition(ENUM_POSITION_TYPE type)
{
    for(int i = PositionsTotal() - 1; i >= 0; i--)
        if(PositionGetSymbol(i) == _Symbol &&
           PositionGetInteger(POSITION_MAGIC) == MagicNumber &&
           PositionGetInteger(POSITION_TYPE) == type)
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
           PositionGetInteger(POSITION_TYPE) == type)
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

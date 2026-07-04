//+------------------------------------------------------------------+
//|  SCA_ML_EA.mq5                                                   |
//|  ML確率スキャルパー（M1・GOLD/USDJPY/GBPJPY）                      |
//|  直近30本のM1ローソク足から18特徴量を計算し、ロジスティック回帰で   |
//|  「次の10本以内にTPライン(TP_ATR_Mult×ATR14)到達」の確率を推定。   |
//|  確率が閾値以上でエントリーし、TP到達 or 10本タイムアウトで決済     |
//|  （タイムアウト＝学習ラベルの先読み期間と一致）。                   |
//|  係数は ml/train.py の自動生成ヘッダ(ml_model_*.mqh)を埋め込み。   |
//|  特徴量定義は train.py と厳密に一致させること（変更時は要再学習）。 |
//+------------------------------------------------------------------+
#property copyright "2026"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>
#include "ml_model_gold.mqh"
#include "ml_model_usdjpy.mqh"
#include "ml_model_gbpjpy.mqh"

#define NFEAT 18

//--- 入力
input double EntryThreshold  = 0.55;  // エントリー確率閾値
input double TP_ATR_Mult     = 2.0;   // TP幅（×ATR14 M1）＝学習ラベルと一致させる
input int    ATR_Period      = 14;    // ATR期間（学習と一致）
input int    TimeoutBars     = 10;    // タイムアウト決済本数（ラベルの先読みと一致）
input double DisasterSL_ATR  = 4.0;   // 災害SL幅（×ATR）＝ラベル外の保険
input int    MaxSpreadPoints = 0;     // スプレッド上限（points, 0=無効）
input double LotSize         = 0.01;
input long   MagicNumber     = 20261100;
input string ResultFileName  = "sca_ml_result.csv";
input string EquityLogFile   = "";

CTrade   trade;
int      atrHandle   = INVALID_HANDLE;
double   W[NFEAT];
double   B           = 0.0;
datetime lastBarTime = 0;
int      barsHeld    = 0;

//+------------------------------------------------------------------+
int OnInit()
{
    trade.SetExpertMagicNumber(MagicNumber);
    atrHandle = iATR(_Symbol, PERIOD_M1, ATR_Period);
    if(atrHandle == INVALID_HANDLE) return INIT_FAILED;

    // 銘柄に対応する学習済み係数を選択
    if(StringFind(_Symbol, "GOLD") >= 0 || StringFind(_Symbol, "XAU") >= 0)
        { ArrayCopy(W, ML_W_GOLD);   B = ML_B_GOLD; }
    else if(StringFind(_Symbol, "USDJPY") >= 0)
        { ArrayCopy(W, ML_W_USDJPY); B = ML_B_USDJPY; }
    else if(StringFind(_Symbol, "GBPJPY") >= 0)
        { ArrayCopy(W, ML_W_GBPJPY); B = ML_B_GBPJPY; }
    else
    {
        Print("SCA_ML: 未対応銘柄 ", _Symbol);
        return INIT_FAILED;
    }
    return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
    if(atrHandle != INVALID_HANDLE) IndicatorRelease(atrHandle);
}

//+------------------------------------------------------------------+
//| 標本標準偏差（ddof=1, pandasの.std()と一致）                       |
//+------------------------------------------------------------------+
double SampleStd(const double &v[], int start, int count)
{
    if(count < 2) return 0.0;
    double mean = 0.0;
    for(int i = start; i < start + count; i++) mean += v[i];
    mean /= count;
    double ss = 0.0;
    for(int i = start; i < start + count; i++) ss += (v[i] - mean) * (v[i] - mean);
    return MathSqrt(ss / (count - 1));
}

//+------------------------------------------------------------------+
//| 18特徴量を計算（train.py build_features()と厳密一致・ロング基準）  |
//| 格納順: mom1,mom3,mom5,mom10,mom30,body0,upw0,dnw0,body1,body2,   |
//|   rangepos,rangew,volratio,upshare10,upshare30,tvr,hsin,hcos      |
//| バーt = 確定した最新バー（shift 1）                                |
//+------------------------------------------------------------------+
bool ComputeFeatures(double &x[], double &atrOut)
{
    double c[], o[], h[], l[];
    long   tv[];
    double atrBuf[];
    ArraySetAsSeries(c, true);  ArraySetAsSeries(o, true);
    ArraySetAsSeries(h, true);  ArraySetAsSeries(l, true);
    ArraySetAsSeries(tv, true); ArraySetAsSeries(atrBuf, true);
    int need = 31;   // c[0]=shift1(バーt) .. c[30]=shift31（mom30/ret1[29]用）
    if(CopyClose(_Symbol, PERIOD_M1, 1, need, c) != need) return false;
    if(CopyOpen(_Symbol, PERIOD_M1, 1, need, o)  != need) return false;
    if(CopyHigh(_Symbol, PERIOD_M1, 1, need, h)  != need) return false;
    if(CopyLow(_Symbol, PERIOD_M1, 1, need, l)   != need) return false;
    if(CopyTickVolume(_Symbol, PERIOD_M1, 1, need, tv) != need) return false;
    if(CopyBuffer(atrHandle, 0, 1, 3, atrBuf) != 3) return false;

    double atr = atrBuf[0];
    if(atr <= 0 || atrBuf[1] <= 0 || atrBuf[2] <= 0) return false;
    atrOut = atr;

    // モメンタム（k本前比・ATR正規化）
    x[0] = (c[0] - c[1])  / atr;                             // mom1
    x[1] = (c[0] - c[3])  / atr;                             // mom3
    x[2] = (c[0] - c[5])  / atr;                             // mom5
    x[3] = (c[0] - c[10]) / atr;                             // mom10
    x[4] = (c[0] - c[30]) / atr;                             // mom30
    // ローソク形状（各バー自身のATRで正規化）
    x[5] = (c[0] - o[0]) / atr;                              // body0
    x[6] = (h[0] - MathMax(c[0], o[0])) / atr;               // upw0
    x[7] = (MathMin(c[0], o[0]) - l[0]) / atr;               // dnw0
    x[8] = (c[1] - o[1]) / atrBuf[1];                        // body1
    x[9] = (c[2] - o[2]) / atrBuf[2];                        // body2
    // 直近30本レンジ内位置・正規化幅
    double hh = h[0], ll = l[0];
    for(int i = 1; i < 30; i++)
    {
        if(h[i] > hh) hh = h[i];
        if(l[i] < ll) ll = l[i];
    }
    double rng = hh - ll;
    x[10] = (rng > 0 ? (c[0] - ll) / rng : 0.5);             // rangepos
    x[11] = rng / atr / 30.0 * 10.0;                         // rangew
    // 実現ボラ比（1本リターンの標本std, 直近10 vs 30）
    double ret1[30];
    for(int i = 0; i < 30; i++) ret1[i] = c[i] - c[i + 1];
    double rv10 = SampleStd(ret1, 0, 10);
    double rv30 = SampleStd(ret1, 0, 30);
    x[12] = (rv30 > 0 ? rv10 / rv30 : 1.0);                  // volratio
    // 陽線比率
    int up10 = 0, up30 = 0;
    for(int i = 0; i < 30; i++)
    {
        if(c[i] > o[i]) { up30++; if(i < 10) up10++; }
    }
    x[13] = up10 / 10.0;                                     // upshare10
    x[14] = up30 / 30.0;                                     // upshare30
    // tickvol比（バーt / 直近30本平均）
    double tvm = 0.0;
    for(int i = 0; i < 30; i++) tvm += (double)tv[i];
    tvm /= 30.0;
    x[15] = (tvm > 0 ? (double)tv[0] / tvm : 1.0);           // tvr
    // 時刻周期エンコード（サーバー時・バーt開始時刻）
    MqlDateTime st;
    TimeToStruct(iTime(_Symbol, PERIOD_M1, 1), st);
    double hr = st.hour + st.min / 60.0;
    x[16] = MathSin(2.0 * M_PI * hr / 24.0);                 // hsin
    x[17] = MathCos(2.0 * M_PI * hr / 24.0);                 // hcos
    return true;
}

//+------------------------------------------------------------------+
//| ショート用の方向対称化（train.pyのSIGN_FLIP/SWAP/INVERT01と一致）  |
//+------------------------------------------------------------------+
void Symmetrize(const double &x[], double &xs[])
{
    for(int i = 0; i < NFEAT; i++) xs[i] = x[i];
    // 符号反転: mom1,mom3,mom5,mom10,mom30,body0,body1,body2
    xs[0] = -xs[0]; xs[1] = -xs[1]; xs[2] = -xs[2]; xs[3] = -xs[3]; xs[4] = -xs[4];
    xs[5] = -xs[5]; xs[8] = -xs[8]; xs[9] = -xs[9];
    // 入替: upw0 <-> dnw0
    double tmp = xs[6]; xs[6] = xs[7]; xs[7] = tmp;
    // 1-x: rangepos, upshare10, upshare30
    xs[10] = 1.0 - xs[10]; xs[13] = 1.0 - xs[13]; xs[14] = 1.0 - xs[14];
}

double Predict(const double &x[])
{
    double z = B;
    for(int i = 0; i < NFEAT; i++) z += W[i] * x[i];
    return 1.0 / (1.0 + MathExp(-z));
}

//+------------------------------------------------------------------+
bool HasPosition()
{
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        ulong tk = PositionGetTicket(i);
        if(tk == 0) continue;
        if(PositionGetString(POSITION_SYMBOL) == _Symbol &&
           PositionGetInteger(POSITION_MAGIC) == MagicNumber) return true;
    }
    return false;
}

void CloseAll()
{
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        ulong tk = PositionGetTicket(i);
        if(tk == 0) continue;
        if(PositionGetString(POSITION_SYMBOL) == _Symbol &&
           PositionGetInteger(POSITION_MAGIC) == MagicNumber)
            trade.PositionClose(tk);
    }
}

//+------------------------------------------------------------------+
void OnTick()
{
    datetime bt = iTime(_Symbol, PERIOD_M1, 0);
    if(bt == lastBarTime) return;      // 新バー確定時のみ処理
    lastBarTime = bt;

    // 保有中: バー数を数え、タイムアウトで成行クローズ
    if(HasPosition())
    {
        barsHeld++;
        if(barsHeld >= TimeoutBars) CloseAll();
        if(HasPosition()) return;      // 1ポジション制
    }
    barsHeld = 0;

    // スプレッドガード
    if(MaxSpreadPoints > 0 &&
       SymbolInfoInteger(_Symbol, SYMBOL_SPREAD) > MaxSpreadPoints) return;

    double x[NFEAT], atr = 0.0;
    if(!ComputeFeatures(x, atr)) return;

    double pL = Predict(x);
    double xs[NFEAT];
    Symmetrize(x, xs);
    double pS = Predict(xs);
    if(pL < EntryThreshold && pS < EntryThreshold) return;

    // TPは学習ラベルと同じ「バーtの終値 + k×ATR(t)」に置く
    double closeT = iClose(_Symbol, PERIOD_M1, 1);
    int    digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);

    if(pL >= pS)
    {
        double tp = NormalizeDouble(closeT + TP_ATR_Mult   * atr, digits);
        double sl = NormalizeDouble(closeT - DisasterSL_ATR * atr, digits);
        trade.Buy(LotSize, _Symbol, 0.0, sl, tp);
    }
    else
    {
        double tp = NormalizeDouble(closeT - TP_ATR_Mult   * atr, digits);
        double sl = NormalizeDouble(closeT + DisasterSL_ATR * atr, digits);
        trade.Sell(LotSize, _Symbol, 0.0, sl, tp);
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

//+------------------------------------------------------------------+
//|  RSI2Reversal.mq5                                               |
//|  RSI(2) ディープ逆張り EA v1.0（Connors流・レンジ強化）        |
//|  超短期RSI(期間2)が深い行き過ぎ(OS<10 / OB>90)で逆張り、       |
//|  短期MA(5)への回帰で決済する高勝率・短保有の平均回帰。         |
//|  既存RSI_Reversal(RSI14+BB+DP)とは別周期で低相関を狙う。       |
//|  レンジ局面限定(MA200傾き≤閾値)＋破綻回避のワイドATRストップ。 |
//+------------------------------------------------------------------+
#property copyright "2026"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>

input group "=== RSI(2) 逆張り ==="
input int    RSI_Period = 2;     // 超短期RSI
input double OS_Level   = 10.0;  // これ未満で買い（深い売られすぎ）
input double OB_Level   = 90.0;  // これ超で売り（深い買われすぎ）
input int    MA_Exit_Period = 5; // 終値がこのMAを回帰方向に抜けたら決済
input bool   AllowLong  = true;
input bool   AllowShort = true;

input group "=== レンジ環境フィルター（MA200傾き） ==="
input bool   UseRangeFilter      = true;
input int    Trend_MA_Period      = 200;
input int    Range_Slope_Lookback = 20;
input double Range_Slope_Max_ATR  = 0.2;  // 傾きがこれ以下＝レンジ

input group "=== 破綻回避ストップ ==="
input bool   UseATRStop  = true;
input int    ATR_Period  = 14;
input double ATR_SL_Mult = 3.0;  // ワイド（回帰を待つが大損は限定）

input group "=== トレード設定 ==="
input double LotSize     = 0.01;
input int    MagicNumber = 20260780;

input group "=== ポジションサイジング ==="
input bool   UseRiskSizing = false;
input double RiskPercent   = 2.0;

input group "=== 出力設定 ==="
input string ResultFileName = "";
input string EquityLogFile  = "";

CTrade trade;
int    rsi_handle, maexit_handle, trend_handle, atr_handle;
double pip_value;

//+------------------------------------------------------------------+
int OnInit()
{
   pip_value = (_Digits==3||_Digits==5) ? 10*_Point : _Point;
   rsi_handle    = iRSI(_Symbol, PERIOD_CURRENT, RSI_Period, PRICE_CLOSE);
   maexit_handle = iMA(_Symbol, PERIOD_CURRENT, MA_Exit_Period, 0, MODE_SMA, PRICE_CLOSE);
   trend_handle  = iMA(_Symbol, PERIOD_CURRENT, Trend_MA_Period, 0, MODE_SMA, PRICE_CLOSE);
   atr_handle    = iATR(_Symbol, PERIOD_CURRENT, ATR_Period);
   if(rsi_handle==INVALID_HANDLE||maexit_handle==INVALID_HANDLE||
      trend_handle==INVALID_HANDLE||atr_handle==INVALID_HANDLE)
   { Print("ハンドル作成失敗"); return INIT_FAILED; }
   trade.SetExpertMagicNumber(MagicNumber);
   trade.SetDeviationInPoints(10);
   Print("RSI2Reversal v1.0 起動 | ", _Symbol, " RSI", RSI_Period,
         " OS<", OS_Level, " OB>", OB_Level, " exitMA", MA_Exit_Period,
         " | Range=", UseRangeFilter?StringFormat("ON(<=%.1f)",Range_Slope_Max_ATR):"OFF");
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   IndicatorRelease(rsi_handle); IndicatorRelease(maexit_handle);
   IndicatorRelease(trend_handle); IndicatorRelease(atr_handle);
}

//+------------------------------------------------------------------+
void OnTick()
{
   static datetime last_bar=0;
   datetime bt=iTime(_Symbol,PERIOD_CURRENT,0);
   if(bt==last_bar) return;
   last_bar=bt;

   double rb[],eb[],tb[],ab[];
   ArraySetAsSeries(rb,true);ArraySetAsSeries(eb,true);ArraySetAsSeries(tb,true);ArraySetAsSeries(ab,true);
   if(CopyBuffer(rsi_handle,0,1,1,rb)<1) return;
   if(CopyBuffer(maexit_handle,0,1,1,eb)<1) return;
   if(CopyBuffer(atr_handle,0,1,1,ab)<1) return;
   double rsi=rb[0], maexit=eb[0], atr=ab[0];
   double cp=iClose(_Symbol,PERIOD_CURRENT,1);

   bool range_ok=true;
   if(UseRangeFilter){
      int need=Range_Slope_Lookback+2;
      if(CopyBuffer(trend_handle,0,1,need,tb)<need) return;
      double slope=MathAbs(tb[0]-tb[Range_Slope_Lookback]);
      range_ok=(slope<=Range_Slope_Max_ATR*atr);
   }

   bool hb=HasPos(POSITION_TYPE_BUY), hs=HasPos(POSITION_TYPE_SELL);

   // --- 決済: 終値が短期MAを回帰方向に抜けた ---
   if(hb && cp>maexit){ CloseType(POSITION_TYPE_BUY); hb=false; }
   if(hs && cp<maexit){ CloseType(POSITION_TYPE_SELL); hs=false; }

   // --- エントリー: 深い行き過ぎ＋レンジ ---
   double sld = (UseATRStop && atr>0) ? ATR_SL_Mult*atr : 0.0;
   if(AllowLong && !hb && range_ok && rsi<OS_Level){
      double ask=SymbolInfoDouble(_Symbol,SYMBOL_ASK);
      double sl=(sld>0)?ask-sld:0.0;
      trade.Buy(CalcLot(sld),_Symbol,ask,(sl>0?NormalizeDouble(sl,_Digits):0.0),0,"RSI2-L");
   }
   if(AllowShort && !hs && range_ok && rsi>OB_Level){
      double bid=SymbolInfoDouble(_Symbol,SYMBOL_BID);
      double sl=(sld>0)?bid+sld:0.0;
      trade.Sell(CalcLot(sld),_Symbol,bid,(sl>0?NormalizeDouble(sl,_Digits):0.0),0,"RSI2-S");
   }
}

//+------------------------------------------------------------------+
double CalcLot(double slDist)
{
   if(!UseRiskSizing || slDist<=0) return LotSize;
   double eq=AccountInfoDouble(ACCOUNT_EQUITY), rm=eq*RiskPercent/100.0;
   double tv=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_VALUE), ts=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE);
   if(tv<=0||ts<=0) return LotSize;
   double mpl=(slDist/ts)*tv; if(mpl<=0) return LotSize;
   double lot=rm/mpl;
   double mn=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN),mx=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MAX),st=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP);
   if(st>0) lot=MathFloor(lot/st)*st;
   return MathMax(mn,MathMin(mx,lot));
}

//+------------------------------------------------------------------+
bool HasPos(ENUM_POSITION_TYPE type)
{
   for(int k=PositionsTotal()-1;k>=0;k--)
      if(PositionGetSymbol(k)==_Symbol && PositionGetInteger(POSITION_MAGIC)==MagicNumber &&
         PositionGetInteger(POSITION_TYPE)==type) return true;
   return false;
}
void CloseType(ENUM_POSITION_TYPE type)
{
   for(int k=PositionsTotal()-1;k>=0;k--){
      ulong tk=PositionGetTicket(k);
      if(PositionGetSymbol(k)==_Symbol && PositionGetInteger(POSITION_MAGIC)==MagicNumber &&
         PositionGetInteger(POSITION_TYPE)==type) trade.PositionClose(tk);
   }
}

//+------------------------------------------------------------------+
double OnTester()
{
   double pf=TesterStatistics(STAT_PROFIT_FACTOR);
   if(EquityLogFile!=""){
      int eqh=FileOpen(EquityLogFile,FILE_WRITE|FILE_CSV|FILE_ANSI,',');
      if(eqh!=INVALID_HANDLE){
         FileWrite(eqh,"time","profit"); HistorySelect(0,TimeCurrent());
         int n=HistoryDealsTotal();
         for(int e=0;e<n;e++){ ulong tk=HistoryDealGetTicket(e); if(tk==0) continue;
            long ty=HistoryDealGetInteger(tk,DEAL_TYPE); if(ty!=DEAL_TYPE_BUY&&ty!=DEAL_TYPE_SELL) continue;
            double p=HistoryDealGetDouble(tk,DEAL_PROFIT)+HistoryDealGetDouble(tk,DEAL_SWAP)+HistoryDealGetDouble(tk,DEAL_COMMISSION);
            FileWrite(eqh,(long)HistoryDealGetInteger(tk,DEAL_TIME),DoubleToString(p,2)); }
         FileClose(eqh);
      }
   }
   if(ResultFileName=="") return pf;
   int fh=FileOpen(ResultFileName,FILE_WRITE|FILE_CSV|FILE_ANSI,',');
   if(fh==INVALID_HANDLE) return pf;
   FileWrite(fh,"key","value");
   FileWrite(fh,"net_profit",DoubleToString(TesterStatistics(STAT_PROFIT),2));
   FileWrite(fh,"profit_factor",DoubleToString(TesterStatistics(STAT_PROFIT_FACTOR),4));
   FileWrite(fh,"max_dd_pct",DoubleToString(TesterStatistics(STAT_BALANCE_DDREL_PERCENT),4));
   FileWrite(fh,"total_trades",IntegerToString((int)TesterStatistics(STAT_TRADES)));
   FileWrite(fh,"win_trades",IntegerToString((int)TesterStatistics(STAT_PROFIT_TRADES)));
   FileWrite(fh,"loss_trades",IntegerToString((int)TesterStatistics(STAT_LOSS_TRADES)));
   FileWrite(fh,"initial_deposit",DoubleToString(TesterStatistics(STAT_INITIAL_DEPOSIT),2));
   FileWrite(fh,"final_balance",DoubleToString(TesterStatistics(STAT_INITIAL_DEPOSIT)+TesterStatistics(STAT_PROFIT),2));
   FileClose(fh);
   return pf;
}
//+------------------------------------------------------------------+

//+------------------------------------------------------------------+
//|  PortfolioEA.mq5                                                 |
//|  統合ポートフォリオEA v1.0（1チャートで全枠を稼働）             |
//|  本番ブックの全枠（PullbackTrend/RSI_Reversal/PairTrade/Carry/  |
//|  VolBreakout/暗号トレンド）を内部の枠リストで反復処理する。     |
//|  1チャートにアタッチするだけで、各枠の銘柄・時間足で新バーを    |
//|  検出し該当戦略を実行。MagicNumberで枠ごとに独立。              |
//|  ※ライブ運用専用。各戦略の検証は個別EA(mt5bt)を使うこと。      |
//|  各枠の挙動は対応する個別EAと一致するよう移植（本番OFF機能は    |
//|  非実装＝OFF相当）。                                            |
//+------------------------------------------------------------------+
#property copyright "2026"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>

//=== 枠ON/OFF（運用時に個別に止められる）===
input group "=== 枠の有効/無効 ==="
input bool En_PB_USDJPY  = true;
input bool En_PB_GBPJPY  = true;
input bool En_PB_AUDJPY  = false;  // 死に枠（デプロイ除外）。既定OFF
input bool En_PB_GOLD    = true;
input bool En_RSI_USDJPY = true;
input bool En_RSI_EURUSD = true;
input bool En_RSI_GBPUSD = true;   // レンジ枠強化（横展開で採用）
input bool En_PAIR       = true;
input bool En_CARRY      = true;
input bool En_VBO        = true;
input bool En_ETH        = true;

input group "=== 全体設定 ==="
input bool   MasterEnable  = true;   // 全枠の発注を一括停止できる安全スイッチ
input double GlobalLotMult = 1.0;    // 全枠のロットに掛ける倍率（資金規模調整用）

input group "=== per-sleeve ロット倍率（増レバ配分用・既定1.0で不変） ==="
input double Mult_PB_USDJPY  = 1.0;
input double Mult_PB_GBPJPY  = 1.0;
input double Mult_PB_GOLD    = 1.0;
input double Mult_RSI_USDJPY = 1.0;
input double Mult_RSI_EURUSD = 1.0;
input double Mult_RSI_GBPUSD = 1.0;
input double Mult_PAIR       = 1.0;
input double Mult_CARRY      = 1.0;
input double Mult_VBO        = 1.0;
input double Mult_ETH        = 1.0;

input group "=== risk%/複利枠の基準資金（0=口座equity・>0で配分資金固定） ==="
input double RefCap_PB_USDJPY = 0;   // PB USDJPY risk%の基準資金（配分額）
input double RefCap_PB_GBPJPY = 0;   // PB GBPJPY risk%の基準資金
input double RefCap_CARRY      = 0;  // Carry複利の基準資金

input group "=== 出力（検証用・ライブでは空でOK）==="
input string ResultFileName = "";
input string EquityLogFile  = "";

//=== 戦略種別 ===
enum ESTRAT { ST_PULLBACK, ST_RSI, ST_PAIR, ST_CARRY, ST_VBO };

//=== 枠定義＋状態 ===
struct SLEEVE
{
   bool            enabled;
   ESTRAT          strat;
   string          symbol;
   ENUM_TIMEFRAMES tf;
   long            magic;
   double          lot;          // 固定ロット（useRisk=falseで使用）
   bool            useRisk;      // PB=risk%、Carry/Pair=資産連動複利
   double          riskPct;      // PB risk%
   double          refDeposit;   // Carry/Pair 複利基準
   // 共通
   double          pip;
   int             digits;
   double          point;
   datetime        lastBar;
   // ハンドル
   int             hTrend, hFast, hSlow, hATR, hADX, hRSI, hBB;
   // PB/RSI/VBO 共通ストップ
   bool            useATRstops;
   double          atrSLmult, rr;
   double          slPips, tpPips;
   // PB 環境フィルター・ADX
   bool            useTrend; double slopeMinATR; int slopeLB;
   bool            useADX;   double adxThr;
   // PB マルチタイムフレーム合流フィルター
   bool            useHigherTF; ENUM_TIMEFRAMES higherTF; int higherTFMA; int hHigherTrend;
   // PB 状態
   bool            armedBuy, armedSell;
   // RSI
   double          bbDev, rsiOBX, rsiOB, rsiOSX, rsiOS;
   bool            useDP; int swingLB, dpBars; double dpTolATR;
   bool            useRange; double rangeMaxATR; int rangeLB;
   bool            wasOB, wasOS, aboveBB, belowBB;
   // PAIR
   string          second; int lookback; double entryZ, exitZ, stopZ;
   // CARRY
   int             trendPeriod; bool reqPosSwap;
   // VBO
   int             channel; bool useSqueeze; int sqLB; double sqFactor; double trailMult;
   // 増レバ配分（deploy）
   double          lotMult;   // per-sleeve ロット倍率
   double          refCap;    // risk%/複利の基準資金（0=口座equity）
};

SLEEVE S[32];
int    NS = 0;
CTrade trade;

//+------------------------------------------------------------------+
void AddSleeve(SLEEVE &x){ S[NS] = x; NS++; }

//+------------------------------------------------------------------+
int OnInit()
{
   NS = 0;
   SLEEVE z; // ゼロ初期化テンプレ
   ZeroSleeve(z);

   //--- PullbackTrend 共通プリセット ---
   SLEEVE pb = z;
   pb.strat=ST_PULLBACK; pb.tf=PERIOD_H4;
   pb.useATRstops=true; pb.atrSLmult=2.0; pb.rr=2.0;
   pb.useTrend=true; pb.slopeMinATR=1.2; pb.slopeLB=20;
   pb.useADX=true; pb.adxThr=22.5;

   // 1. PB USDJPY (risk2%) — MTF合流フィルター採用（D1トレンド一致必須）
   { SLEEVE x=pb; x.enabled=En_PB_USDJPY; x.symbol="USDJPY"; x.magic=20260622;
     x.useRisk=true; x.riskPct=2.0; x.lot=0.01; x.lotMult=Mult_PB_USDJPY; x.refCap=RefCap_PB_USDJPY;
     x.useHigherTF=true; x.higherTF=PERIOD_D1; x.higherTFMA=200; AddSleeve(x); }
   // 2. PB GBPJPY (risk2%) — MTF合流フィルター採用（D1トレンド一致必須）
   { SLEEVE x=pb; x.enabled=En_PB_GBPJPY; x.symbol="GBPJPY"; x.magic=20260627;
     x.useRisk=true; x.riskPct=2.0; x.lot=0.01; x.lotMult=Mult_PB_GBPJPY; x.refCap=RefCap_PB_GBPJPY;
     x.useHigherTF=true; x.higherTF=PERIOD_D1; x.higherTFMA=200; AddSleeve(x); }
   // 3. PB AUDJPY (固定・除外枠)
   { SLEEVE x=pb; x.enabled=En_PB_AUDJPY; x.symbol="AUDJPY"; x.magic=20260628;
     x.useRisk=false; x.lot=0.01; AddSleeve(x); }
   // 4. PB GOLD (固定)
   { SLEEVE x=pb; x.enabled=En_PB_GOLD; x.symbol="GOLD"; x.magic=20260640;
     x.useRisk=false; x.lot=0.01; x.lotMult=Mult_PB_GOLD; AddSleeve(x); }

   //--- RSI_Reversal 共通プリセット ---
   SLEEVE rs = z;
   rs.strat=ST_RSI; rs.bbDev=2.5; rs.rsiOBX=75.0; rs.rsiOB=72.5; rs.rsiOSX=27.5; rs.rsiOS=30.0;
   rs.useRange=true; rs.rangeMaxATR=0.2; rs.rangeLB=20; rs.useATRstops=false;
   rs.swingLB=3; rs.dpTolATR=0.5; rs.useRisk=false; rs.lot=0.01;

   // 5. RSI USDJPY H4 (DP ON, SL50/TP110)
   { SLEEVE x=rs; x.enabled=En_RSI_USDJPY; x.symbol="USDJPY"; x.tf=PERIOD_H4; x.magic=20260610;
     x.useDP=true; x.dpBars=100; x.slPips=50; x.tpPips=110; x.lotMult=Mult_RSI_USDJPY; AddSleeve(x); }
   // 6. RSI EURUSD H1 (DP OFF, SL45/TP105)
   { SLEEVE x=rs; x.enabled=En_RSI_EURUSD; x.symbol="EURUSD"; x.tf=PERIOD_H1; x.magic=20260605;
     x.useDP=false; x.dpBars=60; x.slPips=45; x.tpPips=105; x.lotMult=Mult_RSI_EURUSD; AddSleeve(x); }
   // 6b. RSI GBPUSD H4 (DP OFF, SL50/TP110) — レンジ枠強化
   { SLEEVE x=rs; x.enabled=En_RSI_GBPUSD; x.symbol="GBPUSD"; x.tf=PERIOD_H4; x.magic=20260774;
     x.useDP=false; x.dpBars=100; x.slPips=50; x.tpPips=110; x.lotMult=Mult_RSI_GBPUSD; AddSleeve(x); }

   // 7. PairTrade EURUSD/GBPUSD H1
   { SLEEVE x=z; x.enabled=En_PAIR; x.strat=ST_PAIR; x.symbol="EURUSD"; x.second="GBPUSD";
     x.tf=PERIOD_H1; x.magic=20260629; x.lot=0.01; x.useRisk=false; x.refDeposit=100000;
     x.lookback=200; x.entryZ=4.0; x.exitZ=-1.0; x.stopZ=5.0; x.lotMult=Mult_PAIR; AddSleeve(x); }

   // 8. Carry AUDJPY D1 (複利0.05, スワップ条件ON)
   { SLEEVE x=z; x.enabled=En_CARRY; x.strat=ST_CARRY; x.symbol="AUDJPY"; x.tf=PERIOD_D1;
     x.magic=20260650; x.trendPeriod=200; x.reqPosSwap=true;
     x.useRisk=true; x.lot=0.05; x.refDeposit=100000; x.lotMult=Mult_CARRY; x.refCap=RefCap_CARRY; AddSleeve(x); }

   // 9. VolBreakout USDJPY H4 (固定)
   { SLEEVE x=z; x.enabled=En_VBO; x.strat=ST_VBO; x.symbol="USDJPY"; x.tf=PERIOD_H4;
     x.magic=20260680; x.lot=0.01; x.useRisk=false; x.channel=20;
     x.useSqueeze=true; x.sqLB=50; x.sqFactor=1.0; x.atrSLmult=2.0; x.trailMult=3.0; x.lotMult=Mult_VBO; AddSleeve(x); }

   // 10. 暗号トレンド ETHUSD D1 (Carryロジック, スワップ条件OFF, 固定0.05)
   { SLEEVE x=z; x.enabled=En_ETH; x.strat=ST_CARRY; x.symbol="ETHUSD"; x.tf=PERIOD_D1;
     x.magic=20260710; x.trendPeriod=200; x.reqPosSwap=false;
     x.useRisk=false; x.lot=0.05; x.refDeposit=100000; x.lotMult=Mult_ETH; AddSleeve(x); }

   // ハンドル生成・銘柄メタ
   for(int i=0;i<NS;i++)
   {
      if(!S[i].enabled) continue;
      SymbolSelect(S[i].symbol, true);
      if(S[i].second!="") SymbolSelect(S[i].second, true);
      S[i].digits = (int)SymbolInfoInteger(S[i].symbol, SYMBOL_DIGITS);
      S[i].point  = SymbolInfoDouble(S[i].symbol, SYMBOL_POINT);
      S[i].pip    = (S[i].digits==3 || S[i].digits==5) ? 10*S[i].point : S[i].point;
      S[i].lastBar = 0;
      if(S[i].strat==ST_PULLBACK){
         S[i].hTrend=iMA(S[i].symbol,S[i].tf,200,0,MODE_SMA,PRICE_CLOSE);
         S[i].hFast =iMA(S[i].symbol,S[i].tf,20,0,MODE_EMA,PRICE_CLOSE);
         S[i].hSlow =iMA(S[i].symbol,S[i].tf,50,0,MODE_EMA,PRICE_CLOSE);
         S[i].hATR  =iATR(S[i].symbol,S[i].tf,14);
         S[i].hADX  =iADX(S[i].symbol,S[i].tf,14);
         if(S[i].useHigherTF)
            S[i].hHigherTrend=iMA(S[i].symbol,S[i].higherTF,S[i].higherTFMA,0,MODE_SMA,PRICE_CLOSE);
      } else if(S[i].strat==ST_RSI){
         S[i].hRSI =iRSI(S[i].symbol,S[i].tf,14,PRICE_CLOSE);
         S[i].hTrend=iMA(S[i].symbol,S[i].tf,200,0,MODE_SMA,PRICE_CLOSE);
         S[i].hBB  =iBands(S[i].symbol,S[i].tf,20,0,S[i].bbDev,PRICE_CLOSE);
         S[i].hATR =iATR(S[i].symbol,S[i].tf,14);
      } else if(S[i].strat==ST_CARRY){
         S[i].hTrend=iMA(S[i].symbol,S[i].tf,S[i].trendPeriod,0,MODE_SMA,PRICE_CLOSE);
      } else if(S[i].strat==ST_VBO){
         S[i].hATR =iATR(S[i].symbol,S[i].tf,14);
      }
   }
   Print("PortfolioEA v1.0 起動 | 有効枠数=", CountEnabled(), "/", NS,
         " | Master=", MasterEnable?"ON":"OFF", " | LotMult=", GlobalLotMult);
   return INIT_SUCCEEDED;
}

void ZeroSleeve(SLEEVE &x)
{
   x.enabled=false; x.strat=ST_PULLBACK; x.symbol=""; x.tf=PERIOD_H4; x.magic=0;
   x.lot=0.01; x.useRisk=false; x.riskPct=0; x.refDeposit=100000;
   x.pip=0; x.digits=5; x.point=0; x.lastBar=0;
   x.hTrend=INVALID_HANDLE; x.hFast=INVALID_HANDLE; x.hSlow=INVALID_HANDLE;
   x.hATR=INVALID_HANDLE; x.hADX=INVALID_HANDLE; x.hRSI=INVALID_HANDLE; x.hBB=INVALID_HANDLE;
   x.useATRstops=false; x.atrSLmult=0; x.rr=0; x.slPips=0; x.tpPips=0;
   x.useTrend=false; x.slopeMinATR=0; x.slopeLB=20; x.useADX=false; x.adxThr=0;
   x.useHigherTF=false; x.higherTF=PERIOD_D1; x.higherTFMA=200; x.hHigherTrend=INVALID_HANDLE;
   x.armedBuy=false; x.armedSell=false;
   x.bbDev=2.0; x.rsiOBX=0; x.rsiOB=0; x.rsiOSX=0; x.rsiOS=0;
   x.useDP=false; x.swingLB=3; x.dpBars=100; x.dpTolATR=0.5;
   x.useRange=false; x.rangeMaxATR=0; x.rangeLB=20;
   x.wasOB=false; x.wasOS=false; x.aboveBB=false; x.belowBB=false;
   x.second=""; x.lookback=200; x.entryZ=0; x.exitZ=0; x.stopZ=0;
   x.trendPeriod=200; x.reqPosSwap=false;
   x.channel=20; x.useSqueeze=false; x.sqLB=50; x.sqFactor=1.0; x.trailMult=0;
   x.lotMult=1.0; x.refCap=0.0;
}

int CountEnabled(){ int c=0; for(int i=0;i<NS;i++) if(S[i].enabled) c++; return c; }

//+------------------------------------------------------------------+
void OnTick()
{
   if(!MasterEnable) return;
   for(int i=0;i<NS;i++)
   {
      if(!S[i].enabled) continue;
      datetime bt = iTime(S[i].symbol, S[i].tf, 0);
      if(bt==0 || bt==S[i].lastBar) continue;   // 新バーのみ
      // VBOはバー内トレーリングのため毎バー評価。他もバー確定で処理。
      S[i].lastBar = bt;
      switch(S[i].strat){
         case ST_PULLBACK: ProcPullback(i); break;
         case ST_RSI:      ProcRSI(i);      break;
         case ST_PAIR:     ProcPair(i);     break;
         case ST_CARRY:    ProcCarry(i);    break;
         case ST_VBO:      ProcVBO(i);      break;
      }
   }
}

//============================ 共通ヘルパ ============================
bool HasPos(int i, ENUM_POSITION_TYPE type)
{
   for(int k=PositionsTotal()-1;k>=0;k--)
      if(PositionGetSymbol(k)==S[i].symbol &&
         PositionGetInteger(POSITION_MAGIC)==S[i].magic &&
         PositionGetInteger(POSITION_TYPE)==type) return true;
   return false;
}
bool HasAny(int i)
{
   for(int k=PositionsTotal()-1;k>=0;k--)
      if(PositionGetSymbol(k)==S[i].symbol &&
         PositionGetInteger(POSITION_MAGIC)==S[i].magic) return true;
   return false;
}
void CloseType(int i, ENUM_POSITION_TYPE type)
{
   for(int k=PositionsTotal()-1;k>=0;k--){
      ulong tk=PositionGetTicket(k);
      if(PositionGetSymbol(k)==S[i].symbol &&
         PositionGetInteger(POSITION_MAGIC)==S[i].magic &&
         PositionGetInteger(POSITION_TYPE)==type) trade.PositionClose(tk);
   }
}
void CloseSleeveAll(int i)
{
   for(int k=PositionsTotal()-1;k>=0;k--){
      ulong tk=PositionGetTicket(k);
      if(PositionGetInteger(POSITION_MAGIC)==S[i].magic){
         string sym=PositionGetString(POSITION_SYMBOL);
         if(sym==S[i].symbol || sym==S[i].second) trade.PositionClose(tk);
      }
   }
}
double Clamp(string sym, double lot)
{
   double mn=SymbolInfoDouble(sym,SYMBOL_VOLUME_MIN);
   double mx=SymbolInfoDouble(sym,SYMBOL_VOLUME_MAX);
   double st=SymbolInfoDouble(sym,SYMBOL_VOLUME_STEP);
   if(st>0) lot=MathFloor(lot/st)*st;
   return MathMax(mn,MathMin(mx,lot));
}
double LotRisk(int i, double slDistPrice)
{
   double base;
   if(!S[i].useRisk || slDistPrice<=0) base=S[i].lot;
   else{
      // refCap>0なら配分資金固定でサイズ（口座共有時の過大化を防ぐ）、0なら口座equity
      double eq=(S[i].refCap>0.0) ? S[i].refCap : AccountInfoDouble(ACCOUNT_EQUITY);
      double rm=eq*S[i].riskPct/100.0;
      double tv=SymbolInfoDouble(S[i].symbol,SYMBOL_TRADE_TICK_VALUE);
      double ts=SymbolInfoDouble(S[i].symbol,SYMBOL_TRADE_TICK_SIZE);
      if(tv<=0||ts<=0){ base=S[i].lot; }
      else{ double mpl=(slDistPrice/ts)*tv; base=(mpl>0)?rm/mpl:S[i].lot; }
   }
   return Clamp(S[i].symbol, base*GlobalLotMult*S[i].lotMult);
}
double LotComplex(int i, string sym)  // Carry/Pair 資産連動複利
{
   double base=S[i].lot;
   if(S[i].useRisk){
      double eq=(S[i].refCap>0.0) ? S[i].refCap : AccountInfoDouble(ACCOUNT_EQUITY);
      double rd=(S[i].refDeposit>0)?S[i].refDeposit:100000.0;
      base=S[i].lot*(eq/rd);
   }
   return Clamp(sym, base*GlobalLotMult*S[i].lotMult);
}
double GetBuf(int h,int idx)
{
   double b[]; ArraySetAsSeries(b,true);
   if(CopyBuffer(h,0,1,idx+1,b)<idx+1) return EMPTY_VALUE;
   return b[idx];
}

//============================ PullbackTrend ============================
void ProcPullback(int i)
{
   string sym=S[i].symbol; ENUM_TIMEFRAMES tf=S[i].tf;
   int need = S[i].useTrend ? (S[i].slopeLB+2) : 1;
   double tb[],fb[],sb[],ab[];
   ArraySetAsSeries(tb,true);ArraySetAsSeries(fb,true);ArraySetAsSeries(sb,true);ArraySetAsSeries(ab,true);
   if(CopyBuffer(S[i].hTrend,0,1,need,tb)<need) return;
   if(CopyBuffer(S[i].hFast,0,1,1,fb)<1) return;
   if(CopyBuffer(S[i].hSlow,0,1,1,sb)<1) return;
   if(CopyBuffer(S[i].hATR,0,1,1,ab)<1) return;
   double trendma=tb[0],fastema=fb[0],slowema=sb[0],atr=ab[0];

   bool env_up=true, env_down=true;
   if(S[i].useTrend){
      double slope=trendma-tb[S[i].slopeLB]; double th=S[i].slopeMinATR*atr;
      env_up=(slope>=th); env_down=(slope<=-th);
   }
   double cp=iClose(sym,tf,1), op=iOpen(sym,tf,1);
   double h2=iHigh(sym,tf,2), l2=iLow(sym,tf,2);
   double lp=iLow(sym,tf,1), hp=iHigh(sym,tf,1);

   bool up=(cp>trendma)&&(fastema>slowema);
   bool dn=(cp<trendma)&&(fastema<slowema);
   if(!up) S[i].armedBuy=false;
   if(!dn) S[i].armedSell=false;
   bool qb=(lp>=slowema), qs=(hp<=slowema);
   if(up && lp<=fastema && qb) S[i].armedBuy=true;
   if(dn && hp>=fastema && qs) S[i].armedSell=true;

   bool bull=(cp>op), bear=(cp<op);
   bool mb=(cp>h2), ms=(cp<l2);
   bool adx_ok=true;
   if(S[i].useADX){ double a=GetBuf(S[i].hADX,0); if(a==EMPTY_VALUE) return; adx_ok=(a>=S[i].adxThr); }

   // マルチタイムフレーム合流: 上位足のトレンド方向がH4の方向と一致する場合のみ許可
   bool higher_ok_buy=true, higher_ok_sell=true;
   if(S[i].useHigherTF){
      double hb2=GetBuf(S[i].hHigherTrend,0); if(hb2==EMPTY_VALUE) return;
      double higher_close=iClose(sym,S[i].higherTF,1);
      higher_ok_buy  = (higher_close > hb2);
      higher_ok_sell = (higher_close < hb2);
   }

   bool eb=S[i].armedBuy&&up&&(cp>fastema)&&bull&&mb&&adx_ok&&env_up  &&higher_ok_buy;
   bool es=S[i].armedSell&&dn&&(cp<fastema)&&bear&&ms&&adx_ok&&env_down&&higher_ok_sell;
   bool hb=HasPos(i,POSITION_TYPE_BUY), hs=HasPos(i,POSITION_TYPE_SELL);

   double sld = S[i].useATRstops ? atr*S[i].atrSLmult : S[i].slPips*S[i].pip;
   double tpd = S[i].useATRstops ? sld*S[i].rr        : S[i].tpPips*S[i].pip;
   trade.SetExpertMagicNumber(S[i].magic);
   if(eb && !hb){
      if(hs) CloseType(i,POSITION_TYPE_SELL);
      double ask=SymbolInfoDouble(sym,SYMBOL_ASK);
      trade.Buy(LotRisk(i,sld),sym,ask,
                NormalizeDouble(ask-sld,S[i].digits),NormalizeDouble(ask+tpd,S[i].digits),"PB");
      S[i].armedBuy=false;
   }
   if(es && !hs){
      if(hb) CloseType(i,POSITION_TYPE_BUY);
      double bid=SymbolInfoDouble(sym,SYMBOL_BID);
      trade.Sell(LotRisk(i,sld),sym,bid,
                 NormalizeDouble(bid+sld,S[i].digits),NormalizeDouble(bid-tpd,S[i].digits),"PB");
      S[i].armedSell=false;
   }
}

//============================ RSI_Reversal ============================
bool SwingHi(const double &a[],int idx,int lb,int sz){ if(idx<lb||idx+lb>=sz) return false;
   double v=a[idx]; for(int k=1;k<=lb;k++) if(a[idx-k]>=v||a[idx+k]>=v) return false; return true; }
bool SwingLo(const double &a[],int idx,int lb,int sz){ if(idx<lb||idx+lb>=sz) return false;
   double v=a[idx]; for(int k=1;k<=lb;k++) if(a[idx-k]<=v||a[idx+k]<=v) return false; return true; }
bool DblBottom(const double &hi[],const double &lo[],int pb,int lb,double atr,double tol,double &neck){
   int sz=ArraySize(lo); int l1=-1;
   for(int i=lb;i<pb-lb;i++) if(SwingLo(lo,i,lb,sz)){l1=i;break;} if(l1<0) return false;
   int l2=-1; for(int i=l1+lb+1;i<pb;i++) if(SwingLo(lo,i,lb,sz)){l2=i;break;} if(l2<0) return false;
   if(MathAbs(lo[l1]-lo[l2])>atr*tol) return false;
   double nk=0; for(int i=l1+1;i<l2;i++) if(SwingHi(hi,i,lb,sz)&&hi[i]>nk) nk=hi[i];
   if(nk<=0) return false; neck=nk; return true; }
bool DblTop(const double &hi[],const double &lo[],int pb,int lb,double atr,double tol,double &neck){
   int sz=ArraySize(hi); int h1=-1;
   for(int i=lb;i<pb-lb;i++) if(SwingHi(hi,i,lb,sz)){h1=i;break;} if(h1<0) return false;
   int h2=-1; for(int i=h1+lb+1;i<pb;i++) if(SwingHi(hi,i,lb,sz)){h2=i;break;} if(h2<0) return false;
   if(MathAbs(hi[h1]-hi[h2])>atr*tol) return false;
   double nk=DBL_MAX; for(int i=h1+1;i<h2;i++) if(SwingLo(lo,i,lb,sz)&&lo[i]<nk) nk=lo[i];
   if(nk==DBL_MAX) return false; neck=nk; return true; }

void ProcRSI(int i)
{
   string sym=S[i].symbol; ENUM_TIMEFRAMES tf=S[i].tf;
   int maneed=S[i].useRange?(S[i].rangeLB+2):1;
   double rb[],mb[],bu[],bl[],ab[];
   ArraySetAsSeries(rb,true);ArraySetAsSeries(mb,true);ArraySetAsSeries(bu,true);ArraySetAsSeries(bl,true);ArraySetAsSeries(ab,true);
   if(CopyBuffer(S[i].hRSI,0,1,1,rb)<1) return;
   if(CopyBuffer(S[i].hTrend,0,1,maneed,mb)<maneed) return;
   if(CopyBuffer(S[i].hBB,1,1,1,bu)<1) return;
   if(CopyBuffer(S[i].hBB,2,1,1,bl)<1) return;
   if(CopyBuffer(S[i].hATR,0,1,1,ab)<1) return;
   double rsi=rb[0],ma=mb[0],atr=ab[0],cp=iClose(sym,tf,1);

   bool range_ok=true;
   if(S[i].useRange){ double sl=MathAbs(ma-mb[S[i].rangeLB]); range_ok=(sl<=S[i].rangeMaxATR*atr); }

   int bs=S[i].dpBars+S[i].swingLB+5;
   double hib[],lob[]; ArraySetAsSeries(hib,true); ArraySetAsSeries(lob,true);
   if(CopyHigh(sym,tf,1,bs,hib)<bs) return;
   if(CopyLow(sym,tf,1,bs,lob)<bs) return;

   bool up=(cp>ma), dn=(cp<ma);
   if(rsi>=S[i].rsiOBX) S[i].wasOB=true;
   if(rsi<=S[i].rsiOSX) S[i].wasOS=true;
   if(cp>=bu[0]) S[i].aboveBB=true;
   if(cp<=bl[0]) S[i].belowBB=true;

   bool rbuy=S[i].wasOS&&(rsi>=S[i].rsiOS);
   bool rsell=S[i].wasOB&&(rsi<=S[i].rsiOB);
   bool bbuy=S[i].belowBB&&(cp>bl[0]);
   bool bsell=S[i].aboveBB&&(cp<bu[0]);
   bool dpb=false,dps=false; double nb=0,nsk=0;
   if(S[i].useDP){
      if(DblBottom(hib,lob,S[i].dpBars,S[i].swingLB,atr,S[i].dpTolATR,nb)) dpb=(cp>=nb);
      if(DblTop(hib,lob,S[i].dpBars,S[i].swingLB,atr,S[i].dpTolATR,nsk)) dps=(cp<=nsk);
   }
   bool eb=range_ok&&up&&(rbuy||bbuy||dpb);
   bool es=range_ok&&dn&&(rsell||bsell||dps);
   bool hb=HasPos(i,POSITION_TYPE_BUY), hs=HasPos(i,POSITION_TYPE_SELL);

   double sld=S[i].useATRstops?atr*S[i].atrSLmult:S[i].slPips*S[i].pip;
   double tpd=S[i].useATRstops?sld*S[i].rr:S[i].tpPips*S[i].pip;
   trade.SetExpertMagicNumber(S[i].magic);
   if(eb && !hb){
      if(hs) CloseType(i,POSITION_TYPE_SELL);
      double ask=SymbolInfoDouble(sym,SYMBOL_ASK);
      trade.Buy(LotRisk(i,sld),sym,ask,NormalizeDouble(ask-sld,S[i].digits),NormalizeDouble(ask+tpd,S[i].digits),"RSI");
      if(rbuy) S[i].wasOS=false; if(bbuy) S[i].belowBB=false;
   }
   if(es && !hs){
      if(hb) CloseType(i,POSITION_TYPE_BUY);
      double bid=SymbolInfoDouble(sym,SYMBOL_BID);
      trade.Sell(LotRisk(i,sld),sym,bid,NormalizeDouble(bid+sld,S[i].digits),NormalizeDouble(bid-tpd,S[i].digits),"RSI");
      if(rsell) S[i].wasOB=false; if(bsell) S[i].aboveBB=false;
   }
}

//============================ PairTrade ============================
void ProcPair(int i)
{
   string sym=S[i].symbol, sec=S[i].second; ENUM_TIMEFRAMES tf=S[i].tf; int LB=S[i].lookback;
   double mc[],sc[]; ArraySetAsSeries(mc,true); ArraySetAsSeries(sc,true);
   if(CopyClose(sym,tf,1,LB,mc)<LB) return;
   if(CopyClose(sec,tf,1,LB,sc)<LB) return;
   double sp0=mc[0]-sc[0], mean=0;
   for(int k=0;k<LB;k++) mean+=(mc[k]-sc[k]); mean/=LB;
   double var=0; for(int k=0;k<LB;k++){ double s=mc[k]-sc[k]; var+=(s-mean)*(s-mean);} var/=LB;
   double sd=MathSqrt(var); if(sd<=0) return;
   double z=(sp0-mean)/sd;
   bool ml=HasPos(i,POSITION_TYPE_BUY), msh=HasPos(i,POSITION_TYPE_SELL);
   int st=ml?1:(msh?-1:0);
   trade.SetExpertMagicNumber(S[i].magic);
   double lot=LotComplex(i,sym);
   if(st==0){
      if(z>=S[i].entryZ){ // 主売り・従買い
         trade.Sell(lot,sym,SymbolInfoDouble(sym,SYMBOL_BID),0,0,"PairMain");
         trade.Buy(LotComplex(i,sec),sec,SymbolInfoDouble(sec,SYMBOL_ASK),0,0,"PairSecond");
      } else if(z<=-S[i].entryZ){ // 主買い・従売り
         trade.Buy(lot,sym,SymbolInfoDouble(sym,SYMBOL_ASK),0,0,"PairMain");
         trade.Sell(LotComplex(i,sec),sec,SymbolInfoDouble(sec,SYMBOL_BID),0,0,"PairSecond");
      }
   } else if(st==1){
      if(z>=-S[i].exitZ || z<=-S[i].stopZ) CloseSleeveAll(i);
   } else if(st==-1){
      if(z<=S[i].exitZ || z>=S[i].stopZ) CloseSleeveAll(i);
   }
}

//============================ Carry / 暗号トレンド ============================
void ProcCarry(int i)
{
   string sym=S[i].symbol; ENUM_TIMEFRAMES tf=S[i].tf;
   double mb[]; ArraySetAsSeries(mb,true);
   if(CopyBuffer(S[i].hTrend,0,1,1,mb)<1) return;
   double ma=mb[0], cp=iClose(sym,tf,1);
   bool swap_ok = !S[i].reqPosSwap || (SymbolInfoDouble(sym,SYMBOL_SWAP_LONG)>0.0);
   bool has=HasAny(i);
   trade.SetExpertMagicNumber(S[i].magic);
   if(cp>ma && swap_ok && !has){
      trade.Buy(LotComplex(i,sym),sym,SymbolInfoDouble(sym,SYMBOL_ASK),0,0,"Carry");
   } else if(cp<ma && has){
      CloseSleeveAll(i);
   }
}

//============================ VolBreakout ============================
void ProcVBO(int i)
{
   string sym=S[i].symbol; ENUM_TIMEFRAMES tf=S[i].tf;
   int need=S[i].sqLB+2;
   double ab[]; ArraySetAsSeries(ab,true);
   if(CopyBuffer(S[i].hATR,0,1,need,ab)<need) return;
   double atr1=ab[0]; if(atr1<=0) return;
   double avg=0; for(int k=0;k<S[i].sqLB;k++) avg+=ab[k]; avg/=S[i].sqLB;
   bool sq = !S[i].useSqueeze || (atr1<S[i].sqFactor*avg);
   double cp=iClose(sym,tf,1);
   trade.SetExpertMagicNumber(S[i].magic);
   if(!HasAny(i)){
      double hh=-DBL_MAX, ll=DBL_MAX;
      for(int sft=2; sft<=S[i].channel+1; sft++){
         double h=iHigh(sym,tf,sft), l=iLow(sym,tf,sft);
         if(h>hh) hh=h; if(l<ll) ll=l;
      }
      if(sq && cp>hh){
         double ask=SymbolInfoDouble(sym,SYMBOL_ASK); double sl=ask-S[i].atrSLmult*atr1;
         trade.Buy(LotRisk(i,ask-sl),sym,ask,NormalizeDouble(sl,S[i].digits),0,"VBO-L");
      } else if(sq && cp<ll){
         double bid=SymbolInfoDouble(sym,SYMBOL_BID); double sl=bid+S[i].atrSLmult*atr1;
         trade.Sell(LotRisk(i,sl-bid),sym,bid,NormalizeDouble(sl,S[i].digits),0,"VBO-S");
      }
   } else {
      // チャンデリア・トレーリング
      for(int k=PositionsTotal()-1;k>=0;k--){
         ulong tk=PositionGetTicket(k);
         if(PositionGetInteger(POSITION_MAGIC)!=S[i].magic) continue;
         if(PositionGetString(POSITION_SYMBOL)!=sym) continue;
         long ty=PositionGetInteger(POSITION_TYPE);
         double cur=PositionGetDouble(POSITION_SL);
         if(ty==POSITION_TYPE_BUY){
            double nsl=cp-S[i].trailMult*atr1;
            if(nsl>cur && nsl<cp) trade.PositionModify(tk,NormalizeDouble(nsl,S[i].digits),0);
         } else if(ty==POSITION_TYPE_SELL){
            double nsl=cp+S[i].trailMult*atr1;
            if((cur==0.0||nsl<cur) && nsl>cp) trade.PositionModify(tk,NormalizeDouble(nsl,S[i].digits),0);
         }
      }
   }
}

//============================ 出力（検証用）============================
double OnTester()
{
   double pf = TesterStatistics(STAT_PROFIT_FACTOR);
   if(EquityLogFile != ""){
      int eqh=FileOpen(EquityLogFile,FILE_WRITE|FILE_CSV|FILE_ANSI,',');
      if(eqh!=INVALID_HANDLE){
         FileWrite(eqh,"time","profit");
         HistorySelect(0,TimeCurrent());
         int n=HistoryDealsTotal();
         for(int e=0;e<n;e++){ ulong tk=HistoryDealGetTicket(e); if(tk==0) continue;
            long ty=HistoryDealGetInteger(tk,DEAL_TYPE);
            if(ty!=DEAL_TYPE_BUY&&ty!=DEAL_TYPE_SELL) continue;
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

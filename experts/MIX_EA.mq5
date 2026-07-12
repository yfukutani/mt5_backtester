//+------------------------------------------------------------------+
//|  MIX_EA.mq5（XM版）                                              |
//|  統合ポートフォリオEA v1.0 = PortfolioEA（既存ブック11枠）+      |
//|  SCA（セッションORBスキャルパー3枠・第1/第2バックログ最終形）。   |
//|  1チャートにアタッチするだけで全14枠を稼働。MagicNumberで独立。   |
//|  SCA枠: GOLD(Range1-9h/TE15/FC20/MinR0.40/金曜スキップ/Revブースト)|
//|         USDJPY/GBPJPY(Range0-9h/TE12/FC22/MinR0.30/Revブースト)   |
//|  ※ライブ運用専用。各戦略の検証は個別EA(mt5bt)を使うこと。        |
//|  ※XMサーバー時刻(GMT+2/+3)前提。使い方: docs/MIX_EA_UM.md        |
//+------------------------------------------------------------------+
#property copyright "2026"
#property version   "1.20"
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
input bool En_ETH        = true;   // v1.2: A2デュアルMA(200/40+cd5+SL45)に更新（ETH_EA同等）
input bool En_BTC_FUND   = true;   // v1.2新設: BTC funding逆張り（FundingRev v1.2同等・採用形）
input bool En_BFXREV     = true;   // v1.3新設: Bitfinexデレバレッジ・リバウンド（BfxRev v1.0採用形）
input bool En_SCA_GOLD   = true;   // SCAセッションORB（最終形・Revブースト込み）
input bool En_SCA_USDJPY = true;
input bool En_SCA_GBPJPY = true;

input group "=== BTC funding枠の設定（FundingRev v1.2の採用形） ==="
input string FundingFile      = "funding_btc.csv"; // Common\Files内（テスター/フォールバック）
input bool   FundUseWebRequest = true;             // ライブ: Binance API自動取得（要URL許可）
input double FundThreshold    = -0.004;            // 日平均funding閾値（%/8h）
input int    FundMaxHold      = 20;                // 退出上限日数（med90退出のフェイルセーフ）

input group "=== BfxRev枠の設定（BfxRev v1.0の採用形） ==="
input string BfxFile          = "bfx_btc_long.csv"; // Common\Files内
input bool   BfxUseWebRequest = true;   // ライブ: Bitfinex API自動取得（要URL許可 api-pub.bitfinex.com）
input double BfxDropPct       = 10.0;   // ロング建玉急減閾値（%/5日）
input int    BfxHoldDays      = 10;     // 保有日数

input group "=== 暗号グループ同時ポジション上限（v1.3） ==="
// 暗号3枠（ETH/BTC funding/BfxRev）の同時保有は約11%の日のみ。cap=1はDD-26%だが利益-36%＝
// 効率劣化がテスター実測で判明（MIX_EA_UM§9）。よって既定OFF。ロット増はGlobalLotMult/Mult_*で
// 行う（2x=DD26.1%/3x=DD31.5%実測）。有効化する場合は口座全体の暗号Magic
// （20260710/20260720/20260723/20260724）を横断カウント＝単独EA併用時も機能。
input int MaxCryptoConcurrent = 0;   // 0=無効（推奨・実測根拠） / 1=保有中は他の暗号新規を控える

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
input double Mult_BTC_FUND   = 1.0;
input double Mult_BFXREV     = 1.0;
input double Mult_SCA_GOLD   = 1.0;   // 例: ミックスB相当なら3.0（0.01→0.03）
input double Mult_SCA_USDJPY = 1.0;
input double Mult_SCA_GBPJPY = 1.0;

input group "=== risk%/複利枠の基準資金（0=口座equity・>0で配分資金固定） ==="
input double RefCap_PB_USDJPY = 0;   // PB USDJPY risk%の基準資金（配分額）
input double RefCap_PB_GBPJPY = 0;   // PB GBPJPY risk%の基準資金
input double RefCap_CARRY      = 0;  // Carry複利の基準資金

input group "=== 出力（検証用・ライブでは空でOK）==="
input string ResultFileName = "";
input string EquityLogFile  = "";

input group "=== 運用ログ（フォワード分析用・ライブで有効化） ==="
// MQL5\Files\<prefix>_YYYYMM.csv に月次追記。3種のレコードを出力:
//  DEAL      = 全約定（IN/OUT・枠Magic・ロット・価格・SL/TP・損益）
//  SCA_RANGE = SCA枠の日次レンジ確定情報（高安・幅・ATRd・ドリフト・スキップ有無）
//  DAILY     = 日次スナップショット（equity/balance/証拠金/保有数）
input bool   EnableOpsLog = false;
input string OpsLogPrefix = "mixlog";

//=== 戦略種別 ===
enum ESTRAT { ST_PULLBACK, ST_RSI, ST_PAIR, ST_CARRY, ST_VBO, ST_SCA, ST_FUNDING, ST_BFXREV };

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
   bool            useHyst; double hystMult;   // MAクロス・ヒステリシス帯（AUDJPYのみ採用）
   // CARRY v1.2: デュアルMA退出+クールダウン+災害SL（ETH枠=A2形で採用）
   int             exitPeriod; int hExit; int cdBars; datetime cdExitBar; double disasterSL;
   // v1.3: 暗号グループ（同時ポジション上限ガードの対象）
   bool            cryptoGroup;
   // VBO
   int             channel; bool useSqueeze; int sqLB; double sqFactor; double trailMult;
   // 増レバ配分（deploy）
   double          lotMult;   // per-sleeve ロット倍率
   double          refCap;    // risk%/複利の基準資金（0=口座equity）
   // SCA（セッションORB）
   int             scaRangeStart, scaRangeEnd, scaTradeEnd, scaForceClose;
   double          scaMinRange, scaMaxRange, scaBuf;
   bool            scaSkipFriday, scaRevBoost;
   double          scaBoostMult;
   datetime        scaDay;
   double          scaRangeHigh, scaRangeLow, scaDrift;
   bool            scaReady, scaSkip, scaTradedL, scaTradedS;
};

SLEEVE S[32];
int    NS = 0;
CTrade trade;
datetime g_opsDay = 0;   // 運用ログの日次スナップショット管理

//============================ 運用ログ ============================
string OpsLogFile()
{
   MqlDateTime t;
   TimeToStruct(TimeCurrent(), t);
   return StringFormat("%s_%04d%02d.csv", OpsLogPrefix, t.year, t.mon);
}

void OpsWrite(string type, long magic, string sym,
              double f1, double f2, double f3, double f4, double f5, double f6,
              string note)
{
   if(!EnableOpsLog) return;
   int fh = FileOpen(OpsLogFile(), FILE_READ | FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
   if(fh == INVALID_HANDLE) return;
   bool empty = (FileSize(fh) == 0);
   FileSeek(fh, 0, SEEK_END);
   if(empty)
      FileWrite(fh, "time", "type", "magic", "symbol", "f1", "f2", "f3", "f4", "f5", "f6", "note");
   FileWrite(fh, (long)TimeCurrent(), type, magic, sym,
             DoubleToString(f1, 5), DoubleToString(f2, 5), DoubleToString(f3, 5),
             DoubleToString(f4, 5), DoubleToString(f5, 5), DoubleToString(f6, 5), note);
   FileClose(fh);
}

// 全約定を記録（DEAL: f1=方向 f2=ロット f3=価格 f4=SL f5=TP f6=損益, note=IN/OUT）
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
{
   if(!EnableOpsLog) return;
   if(trans.type != TRADE_TRANSACTION_DEAL_ADD) return;
   if(!HistoryDealSelect(trans.deal)) return;
   long magic = HistoryDealGetInteger(trans.deal, DEAL_MAGIC);
   if(magic < 20260000 || magic >= 20270000) return;   // 本EAの枠のみ
   long dtype = HistoryDealGetInteger(trans.deal, DEAL_TYPE);
   if(dtype != DEAL_TYPE_BUY && dtype != DEAL_TYPE_SELL) return;
   long entry = HistoryDealGetInteger(trans.deal, DEAL_ENTRY);
   double pnl = HistoryDealGetDouble(trans.deal, DEAL_PROFIT)
              + HistoryDealGetDouble(trans.deal, DEAL_SWAP)
              + HistoryDealGetDouble(trans.deal, DEAL_COMMISSION);
   OpsWrite("DEAL", magic, HistoryDealGetString(trans.deal, DEAL_SYMBOL),
            (dtype == DEAL_TYPE_BUY ? 1 : -1),
            HistoryDealGetDouble(trans.deal, DEAL_VOLUME),
            HistoryDealGetDouble(trans.deal, DEAL_PRICE),
            HistoryDealGetDouble(trans.deal, DEAL_SL),
            HistoryDealGetDouble(trans.deal, DEAL_TP),
            pnl,
            (entry == DEAL_ENTRY_IN ? "IN" : "OUT"));
}

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

   // 8. Carry AUDJPY D1 (複利0.05, スワップ条件ON, ヒステリシス帯±0.75ATR採用)
   { SLEEVE x=z; x.enabled=En_CARRY; x.strat=ST_CARRY; x.symbol="AUDJPY"; x.tf=PERIOD_D1;
     x.magic=20260650; x.trendPeriod=200; x.reqPosSwap=true;
     x.useHyst=true; x.hystMult=0.75;
     x.useRisk=true; x.lot=0.05; x.refDeposit=100000; x.lotMult=Mult_CARRY; x.refCap=RefCap_CARRY; AddSleeve(x); }

   // 9. VolBreakout USDJPY H4 (固定)
   { SLEEVE x=z; x.enabled=En_VBO; x.strat=ST_VBO; x.symbol="USDJPY"; x.tf=PERIOD_H4;
     x.magic=20260680; x.lot=0.01; x.useRisk=false; x.channel=20;
     x.useSqueeze=true; x.sqLB=50; x.sqFactor=1.0; x.atrSLmult=2.0; x.trailMult=3.0; x.lotMult=Mult_VBO; AddSleeve(x); }

   // 10. 暗号 ETHUSD D1 — v1.2でA2デュアルMAに更新（ETH_EA v1.0同等: 200/40+cd5+災害SL45）
   //     旧: MA200単独ホールド。検証: full+7,576/PF1.81(0.02lot)→0.05でも線形（ES面で実証）
   { SLEEVE x=z; x.enabled=En_ETH; x.strat=ST_CARRY; x.symbol="ETHUSD"; x.tf=PERIOD_D1;
     x.magic=20260710; x.trendPeriod=200; x.reqPosSwap=false;
     x.exitPeriod=40; x.cdBars=5; x.disasterSL=45.0;
     x.useRisk=false; x.lot=0.05; x.refDeposit=100000; x.lotMult=Mult_ETH; AddSleeve(x); }

   // 10b. BTC funding逆張り BTCUSD D1 — v1.2新設（FundingRev v1.2採用形と同一・Magic継続）
   //      閾値-0.004/退出=funding>90日中央値/上限20日/災害SL40。full+39,036/PF2.17/DD9.4%(0.01lot)
   //      ⚠️ 単独チャートのFundingRev_EAとは排他（同Magic・併走で二重発注になる）
   { SLEEVE x=z; x.enabled=En_BTC_FUND; x.strat=ST_FUNDING; x.symbol="BTCUSD"; x.tf=PERIOD_D1;
     x.magic=20260720; x.lot=0.01; x.useRisk=false; x.disasterSL=40.0; x.cryptoGroup=true;
     x.lotMult=Mult_BTC_FUND; AddSleeve(x); }

   // 10c. BfxRevデレバレッジ・リバウンド BTCUSD D1 — v1.3新設（BfxRev v1.0採用形と同一・Magic継続）
   //      long建玉5日-10%超→10日保有/災害SL75。full+57,812/PF1.98(0.01lot)
   //      ⚠️ 単独チャートのBfxRev_EAとは排他（同Magic・併走で二重発注になる）
   { SLEEVE x=z; x.enabled=En_BFXREV; x.strat=ST_BFXREV; x.symbol="BTCUSD"; x.tf=PERIOD_D1;
     x.magic=20260724; x.lot=0.01; x.useRisk=false; x.disasterSL=75.0; x.cryptoGroup=true;
     x.lotMult=Mult_BFXREV; AddSleeve(x); }

   //--- SCA セッションORB（第1/第2バックログ最終形・検証: docs/sca_ea.md）---
   // 11. SCA GOLD M15（Range1-9h/TE15/FC20/MinR0.40/buf0.05/RR1.5/金曜スキップ/Revブースト）
   { SLEEVE x=z; x.enabled=En_SCA_GOLD; x.strat=ST_SCA; x.symbol="GOLD"; x.tf=PERIOD_M15;
     x.magic=20261002; x.lot=0.01; x.useRisk=false; x.rr=1.5; x.lotMult=Mult_SCA_GOLD;
     x.scaRangeStart=1; x.scaRangeEnd=9; x.scaTradeEnd=15; x.scaForceClose=20;
     x.scaMinRange=0.40; x.scaMaxRange=1.00; x.scaBuf=0.05;
     x.scaSkipFriday=true; x.scaRevBoost=true; x.scaBoostMult=2.0; AddSleeve(x); }
   // 12. SCA USDJPY M15（初版形: Range0-9h/TE12/FC22/MinR0.30/buf0.05/RR2.0/Revブースト）
   { SLEEVE x=z; x.enabled=En_SCA_USDJPY; x.strat=ST_SCA; x.symbol="USDJPY"; x.tf=PERIOD_M15;
     x.magic=20261000; x.lot=0.01; x.useRisk=false; x.rr=2.0; x.lotMult=Mult_SCA_USDJPY;
     x.scaRangeStart=0; x.scaRangeEnd=9; x.scaTradeEnd=12; x.scaForceClose=22;
     x.scaMinRange=0.30; x.scaMaxRange=1.00; x.scaBuf=0.05;
     x.scaSkipFriday=false; x.scaRevBoost=true; x.scaBoostMult=2.0; AddSleeve(x); }
   // 13. SCA GBPJPY M15（初版形: buf0）
   { SLEEVE x=z; x.enabled=En_SCA_GBPJPY; x.strat=ST_SCA; x.symbol="GBPJPY"; x.tf=PERIOD_M15;
     x.magic=20261001; x.lot=0.01; x.useRisk=false; x.rr=2.0; x.lotMult=Mult_SCA_GBPJPY;
     x.scaRangeStart=0; x.scaRangeEnd=9; x.scaTradeEnd=12; x.scaForceClose=22;
     x.scaMinRange=0.30; x.scaMaxRange=1.00; x.scaBuf=0.0;
     x.scaSkipFriday=false; x.scaRevBoost=true; x.scaBoostMult=2.0; AddSleeve(x); }

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
         if(S[i].useHyst) S[i].hATR=iATR(S[i].symbol,S[i].tf,14);
         if(S[i].exitPeriod>0)
            S[i].hExit=iMA(S[i].symbol,S[i].tf,S[i].exitPeriod,0,MODE_SMA,PRICE_CLOSE);
      } else if(S[i].strat==ST_FUNDING){
         if(!FundingInit())
         {
            S[i].enabled=false;
            Print("BTC funding枠: データ初期化失敗のため無効化（決済のみ有効・他枠は正常）");
         }
      } else if(S[i].strat==ST_BFXREV){
         if(!BfxInit())
         {
            S[i].enabled=false;
            Print("BfxRev枠: データ初期化失敗のため無効化（決済のみ有効・他枠は正常）");
         }
      } else if(S[i].strat==ST_VBO){
         S[i].hATR =iATR(S[i].symbol,S[i].tf,14);
      } else if(S[i].strat==ST_SCA){
         S[i].hATR =iATR(S[i].symbol,PERIOD_D1,14);   // レンジ幅正規化用のD1 ATR
      }
   }
   Print("MIX_EA v1.3 (XM) 起動 | 有効枠数=", CountEnabled(), "/", NS,
         " | Master=", MasterEnable?"ON":"OFF", " | LotMult=", GlobalLotMult,
         " | CryptoCap=", MaxCryptoConcurrent>0 ? IntegerToString(MaxCryptoConcurrent) : "OFF");
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
   x.useHyst=false; x.hystMult=0.75;
   x.exitPeriod=0; x.hExit=INVALID_HANDLE; x.cdBars=0; x.cdExitBar=0; x.disasterSL=0;
   x.cryptoGroup=false;
   x.channel=20; x.useSqueeze=false; x.sqLB=50; x.sqFactor=1.0; x.trailMult=0;
   x.lotMult=1.0; x.refCap=0.0;
   x.scaRangeStart=0; x.scaRangeEnd=9; x.scaTradeEnd=15; x.scaForceClose=22;
   x.scaMinRange=0.30; x.scaMaxRange=1.00; x.scaBuf=0.0;
   x.scaSkipFriday=false; x.scaRevBoost=false; x.scaBoostMult=2.0;
   x.scaDay=0; x.scaRangeHigh=0; x.scaRangeLow=0; x.scaDrift=0;
   x.scaReady=false; x.scaSkip=false; x.scaTradedL=false; x.scaTradedS=false;
}

int CountEnabled(){ int c=0; for(int i=0;i<NS;i++) if(S[i].enabled) c++; return c; }

//+------------------------------------------------------------------+
void OnTick()
{
   if(!MasterEnable) return;
   // 日次スナップショット（DAILY: f1=equity f2=balance f3=証拠金 f4=保有数）
   if(EnableOpsLog)
   {
      datetime d = TimeCurrent() - (TimeCurrent() % 86400);
      if(d != g_opsDay)
      {
         g_opsDay = d;
         OpsWrite("DAILY", 0, "",
                  AccountInfoDouble(ACCOUNT_EQUITY), AccountInfoDouble(ACCOUNT_BALANCE),
                  AccountInfoDouble(ACCOUNT_MARGIN), PositionsTotal(), 0, 0, "");
      }
   }
   for(int i=0;i<NS;i++)
   {
      if(!S[i].enabled) continue;
      if(S[i].strat==ST_FUNDING){ ProcFunding(i); continue; }   // 自前でバー/リトライ管理
      if(S[i].strat==ST_BFXREV){ ProcBfx(i); continue; }        // 同上
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
         case ST_SCA:      ProcSCA(i);      break;
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
//=== v1.3: 暗号グループ同時ポジション上限ガード ===
// 口座全体の暗号Magic（MIXスリーブ+単独EA）を横断カウント。上限到達なら新規を見送る。
bool CryptoGuardOK(int i)
{
   if(MaxCryptoConcurrent<=0 || !S[i].cryptoGroup) return true;
   int cnt=0;
   for(int k=PositionsTotal()-1;k>=0;k--){
      long m=PositionGetInteger(POSITION_MAGIC);
      if(PositionGetSymbol(k)=="" ) continue;
      if(m==20260710 || m==20260720 || m==20260723 || m==20260724) cnt++;
   }
   if(cnt>=MaxCryptoConcurrent){
      Print("[CRYPTO-CAP] 枠", S[i].magic, " のエントリー見送り（暗号同時", cnt, "/上限", MaxCryptoConcurrent, "）");
      OpsWrite("SKIP", S[i].magic, S[i].symbol, cnt, MaxCryptoConcurrent, 0, 0, 0, 0, "crypto-cap");
      return false;
   }
   return true;
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
   // ヒステリシス帯: entry=MA+b×ATR / exit=MA−b×ATR（AUDJPYのみ採用、ETHはOFF）
   double entry_th=ma, exit_th=ma;
   if(S[i].useHyst){
      double ab[]; ArraySetAsSeries(ab,true);
      if(CopyBuffer(S[i].hATR,0,1,1,ab)<1) return;
      entry_th=ma+S[i].hystMult*ab[0]; exit_th=ma-S[i].hystMult*ab[0];
   }
   // v1.2 A2デュアルMA: entry=TrendMA上かつExitMA上 / exit=ExitMA割れ（ETH枠で採用・ヒステリシスと排他）
   if(S[i].exitPeriod>0){
      double eb[]; ArraySetAsSeries(eb,true);
      if(CopyBuffer(S[i].hExit,0,1,1,eb)<1) return;
      entry_th=MathMax(ma,eb[0]); exit_th=eb[0];
   }
   // v1.2 クールダウン（S9）: 退出後cdBarsは再entry禁止
   bool cd_ok=true;
   if(S[i].cdBars>0 && S[i].cdExitBar>0)
      cd_ok=(iBarShift(sym,tf,S[i].cdExitBar,false)>=S[i].cdBars);
   trade.SetExpertMagicNumber(S[i].magic);
   if(cp>entry_th && swap_ok && !has && cd_ok && CryptoGuardOK(i)){
      double ask=SymbolInfoDouble(sym,SYMBOL_ASK);
      double sl=(S[i].disasterSL>0 ? NormalizeDouble(ask*(1-S[i].disasterSL/100),S[i].digits) : 0);
      trade.Buy(LotComplex(i,sym),sym,ask,sl,0,"Carry");
   } else if(cp<exit_th && has){
      CloseSleeveAll(i);
      S[i].cdExitBar=iTime(sym,tf,0);
   }
}

//============================ BTC funding逆張り（FundingRev v1.2移植） ============================
long     f_time[];  double f_rate[];  int f_n=0;
long     g_fday[];  double g_fdayavg[]; int g_fdn=0;
datetime g_fundEvalBar=0, g_fundFetchAt=0;

int FundLoadCsvInto(const string fname, long &t[], double &r[])
{
   int fh=FileOpen(fname, FILE_READ|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
   if(fh==INVALID_HANDLE) return 0;
   int n=0; ArrayResize(t,8000); ArrayResize(r,8000);
   FileReadString(fh); FileReadString(fh);   // ヘッダ
   while(!FileIsEnding(fh)){
      string ts=FileReadString(fh), rs=FileReadString(fh);
      if(ts=="") break;
      if(n>=ArraySize(t)){ ArrayResize(t,n+4000); ArrayResize(r,n+4000); }
      t[n]=StringToInteger(ts); r[n]=StringToDouble(rs); n++;
   }
   FileClose(fh);
   return n;
}

void FundCommit(long &t[], double &r[], const int n)
{
   ArrayResize(f_time,n); ArrayResize(f_rate,n);
   if(n>1 && t[0]>t[n-1]) for(int i=0;i<n;i++){ f_time[i]=t[n-1-i]; f_rate[i]=r[n-1-i]; }
   else                   for(int i=0;i<n;i++){ f_time[i]=t[i];     f_rate[i]=r[i]; }
   f_n=n;
   ArrayResize(g_fday,f_n); ArrayResize(g_fdayavg,f_n);
   g_fdn=0; long cur=-1; double sum=0; int cnt=0;
   for(int i=0;i<f_n;i++){
      long dy=f_time[i]/86400;
      if(dy!=cur){ if(cnt>0){ g_fday[g_fdn]=cur; g_fdayavg[g_fdn]=sum/cnt*100.0; g_fdn++; } cur=dy; sum=0; cnt=0; }
      sum+=f_rate[i]; cnt++;
   }
   if(cnt>0){ g_fday[g_fdn]=cur; g_fdayavg[g_fdn]=sum/cnt*100.0; g_fdn++; }
}

int FundParse(const string body, long &t[], double &r[])
{
   int n=0; ArrayResize(t,1100); ArrayResize(r,1100);
   int pos=0;
   while(true){
      int it=StringFind(body,"\"fundingTime\":",pos); if(it<0) break; it+=14;
      int ir=StringFind(body,"\"fundingRate\":\"",it); if(ir<0) break; ir+=15;
      int ire=StringFind(body,"\"",ir); if(ire<0) break;
      long tms=StringToInteger(StringSubstr(body,it,20));
      double rate=StringToDouble(StringSubstr(body,ir,ire-ir));
      if(tms>0){
         if(n>=ArraySize(t)){ ArrayResize(t,n+500); ArrayResize(r,n+500); }
         t[n]=tms/1000; r[n]=rate; n++;
      }
      pos=ire;
   }
   return n;
}

bool FundFetch()
{
   char req[],res[]; string rh;
   ResetLastError();
   int code=WebRequest("GET","https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&limit=1000","",5000,req,res,rh);
   if(code!=200){
      int err=GetLastError();
      Print("funding API失敗 http=",code," err=",err,
            err==4014?" →オプション→EA→WebRequest許可URLに https://fapi.binance.com を追加":"");
      return false;
   }
   string body=CharArrayToString(res,0,WHOLE_ARRAY,CP_UTF8);
   long tt[]; double tr[];
   int n=FundParse(body,tt,tr);
   if(n<3){ Print("funding APIパース失敗 n=",n); return false; }
   FundCommit(tt,tr,n);
   Print("funding API取得: ",n,"件");
   return true;
}

bool FundingInit()
{
   if(MQLInfoInteger(MQL_TESTER) || !FundUseWebRequest){
      long tt[]; double tr[];
      int n=FundLoadCsvInto(FundingFile,tt,tr);
      if(n<100 && MQLInfoInteger(MQL_TESTER)){ Print("funding CSV不足: ",n,"件"); return false; }
      if(n>0) FundCommit(tt,tr,n);
   } else {
      g_fundFetchAt=TimeCurrent();
      if(!FundFetch()){
         long tt[]; double tr[];
         int n=FundLoadCsvInto(FundingFile,tt,tr);
         if(n>0) FundCommit(tt,tr,n);
         Print("起動時API失敗→CSV代替 ",f_n,"件（以後リトライ）");
      }
   }
   Print("BTC funding枠: ",f_n,"件ロード | 閾値",DoubleToString(FundThreshold,4),
         "%/8h | 退出=med90(上限",FundMaxHold,"日)");
   return true;   // ライブは0件でも枠は維持（決済独立・fetch再試行）
}

double FundAvg(datetime t0, datetime t1)
{
   double sum=0; int cnt=0;
   for(int i=0;i<f_n;i++){
      if(f_time[i]>=(long)t0 && f_time[i]<(long)t1){ sum+=f_rate[i]*100.0; cnt++; }
      else if(f_time[i]>=(long)t1) break;
   }
   return (cnt>0 ? sum/cnt : EMPTY_VALUE);
}

double FundMed90(datetime bt)
{
   long d1=(long)bt/86400, d0=d1-91;
   double win[]; ArrayResize(win,100); int m=0;
   for(int i=0;i<g_fdn;i++){
      if(g_fday[i]>=d0 && g_fday[i]<d1) win[m++]=g_fdayavg[i];
      else if(g_fday[i]>=d1) break;
   }
   if(m<30) return EMPTY_VALUE;
   ArrayResize(win,m); ArraySort(win);
   return (m%2==1 ? win[m/2] : (win[m/2-1]+win[m/2])/2);
}

bool FundEnsure(datetime bt)
{
   if(MQLInfoInteger(MQL_TESTER)) return (f_n>0);
   long newest=(f_n>0 ? f_time[f_n-1] : 0);
   if(newest>=(long)bt-12*3600) return true;
   if(!FundUseWebRequest){
      long tt[]; double tr[];
      int n=FundLoadCsvInto(FundingFile,tt,tr);
      if(n>0) FundCommit(tt,tr,n);
      return (f_n>0 && f_time[f_n-1]>=(long)bt-12*3600);
   }
   if(TimeCurrent()-g_fundFetchAt<3600) return false;   // 1時間リトライ間隔
   g_fundFetchAt=TimeCurrent();
   if(FundFetch()) return true;
   return (f_n>0 && f_time[f_n-1]>=(long)bt-12*3600);
}

int FundBarsHeld(int i)
{
   for(int k=PositionsTotal()-1;k>=0;k--){
      if(PositionGetSymbol(k)==S[i].symbol && PositionGetInteger(POSITION_MAGIC)==S[i].magic){
         datetime opened=(datetime)PositionGetInteger(POSITION_TIME);
         return iBarShift(S[i].symbol,PERIOD_D1,opened,false);
      }
   }
   return 0;
}

void ProcFunding(int i)
{
   datetime bt=iTime(S[i].symbol,PERIOD_D1,0);
   if(bt==0) return;
   trade.SetExpertMagicNumber(S[i].magic);

   // 決済（データ依存はmed90のみ・上限FundMaxHoldは無条件で必ず執行）
   if(HasAny(i)){
      int held=FundBarsHeld(i);
      bool timeup=(held>=FundMaxHold);
      bool normalized=false;
      if(held>=1){
         double avg=FundAvg(bt-86400,bt);
         if(avg!=EMPTY_VALUE){
            double med=FundMed90(bt);
            normalized=(med!=EMPTY_VALUE && avg>med);
         }
      }
      if((timeup||normalized) && bt!=g_fundEvalBar){   // 新バーで判定（標準形と同一）
         CloseSleeveAll(i);
      }
      g_fundEvalBar=bt;
      return;
   }
   if(g_fundEvalBar==bt) return;   // 本日評価済み
   if(!FundEnsure(bt)) return;     // データ未達→tickで再試行（1時間間隔）
   double avg=FundAvg(bt-86400,bt);
   g_fundEvalBar=bt;
   if(avg==EMPTY_VALUE) return;
   if(avg<FundThreshold && CryptoGuardOK(i)){
      double ask=SymbolInfoDouble(S[i].symbol,SYMBOL_ASK);
      double sl=(S[i].disasterSL>0 ? NormalizeDouble(ask*(1-S[i].disasterSL/100),S[i].digits) : 0);
      if(trade.Buy(Clamp(S[i].symbol,S[i].lot*S[i].lotMult*GlobalLotMult),S[i].symbol,ask,sl,0,"FundRev"))
         Print("[FUNDREV BUY] avg=",DoubleToString(avg,4),"%/8h");
   }
}

//============================ BfxRevデレバレッジ・リバウンド（BfxRev v1.0移植） ============================
long     bx_day[];  double bx_val[];  int bx_n=0;
datetime g_bfxEvalBar=0, g_bfxFetchAt=0;

int BfxLoadCsv(const string fname, long &t[], double &v[])
{
   int fh=FileOpen(fname, FILE_READ|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
   if(fh==INVALID_HANDLE) return 0;
   int n=0; ArrayResize(t,5000); ArrayResize(v,5000);
   FileReadString(fh); FileReadString(fh);
   while(!FileIsEnding(fh)){
      string ts=FileReadString(fh), vs=FileReadString(fh);
      if(ts=="") break;
      if(n>=ArraySize(t)){ ArrayResize(t,n+2000); ArrayResize(v,n+2000); }
      t[n]=StringToInteger(ts)/86400; v[n]=StringToDouble(vs); n++;
   }
   FileClose(fh);
   return n;
}

void BfxCommit(long &t[], double &v[], const int n, const bool merge)
{
   if(!merge || bx_n==0){
      ArrayResize(bx_day,n); ArrayResize(bx_val,n);
      if(n>1 && t[0]>t[n-1]) for(int i=0;i<n;i++){ bx_day[i]=t[n-1-i]; bx_val[i]=v[n-1-i]; }
      else                   for(int i=0;i<n;i++){ bx_day[i]=t[i];     bx_val[i]=v[i]; }
      bx_n=n;
      return;
   }
   for(int i=n-1;i>=0;i--){
      long dy=t[i];
      if(bx_n>0 && dy==bx_day[bx_n-1]){ bx_val[bx_n-1]=v[i]; continue; }
      if(bx_n==0 || dy>bx_day[bx_n-1]){
         ArrayResize(bx_day,bx_n+1); ArrayResize(bx_val,bx_n+1);
         bx_day[bx_n]=dy; bx_val[bx_n]=v[i]; bx_n++;
      }
   }
}

int BfxParse(const string body, long &t[], double &v[])
{
   int n=0; ArrayResize(t,5000); ArrayResize(v,5000);
   int pos=0; long lastday=-1;
   while(true){
      int i0=StringFind(body,"[",pos); if(i0<0) break;
      int ic=StringFind(body,",",i0);
      int i1=StringFind(body,"]",i0);
      if(ic<0 || i1<0 || ic>i1){ pos=i0+1; continue; }
      long tms=StringToInteger(StringSubstr(body,i0+1,ic-i0-1));
      double val=StringToDouble(StringSubstr(body,ic+1,i1-ic-1));
      if(tms>1000000000000){
         long dy=tms/86400000;
         if(dy!=lastday){
            if(n>=ArraySize(t)){ ArrayResize(t,n+2000); ArrayResize(v,n+2000); }
            t[n]=dy; v[n]=val; n++; lastday=dy;
         }
      }
      pos=i1+1;
   }
   return n;
}

bool BfxFetch()
{
   char req[],res[]; string rh;
   ResetLastError();
   int code=WebRequest("GET","https://api-pub.bitfinex.com/v2/stats1/pos.size:1m:tBTCUSD:long/hist?limit=10000&sort=-1","",5000,req,res,rh);
   if(code!=200){
      int err=GetLastError();
      Print("Bitfinex API失敗 http=",code," err=",err,
            err==4014?" →WebRequest許可URLに https://api-pub.bitfinex.com を追加":"");
      return false;
   }
   string body=CharArrayToString(res,0,WHOLE_ARRAY,CP_UTF8);
   long tt[]; double tv[];
   int n=BfxParse(body,tt,tv);
   if(n<3){ Print("Bitfinexパース失敗 n=",n); return false; }
   BfxCommit(tt,tv,n,true);
   Print("Bitfinex API取得: ",n,"日分マージ（総",bx_n,"日）");
   return true;
}

bool BfxInit()
{
   long tt[]; double tv[];
   if(MQLInfoInteger(MQL_TESTER) || !BfxUseWebRequest){
      int n=BfxLoadCsv(BfxFile,tt,tv);
      if(n<100 && MQLInfoInteger(MQL_TESTER)){ Print("bfx CSV不足: ",n,"件"); return false; }
      if(n>0) BfxCommit(tt,tv,n,false);
   } else {
      int n=BfxLoadCsv(BfxFile,tt,tv);
      if(n>0) BfxCommit(tt,tv,n,false);
      g_bfxFetchAt=TimeCurrent();
      if(!BfxFetch())
         Print("起動時Bitfinex API失敗→CSV代替 ",bx_n,"日（以後リトライ）");
   }
   Print("BfxRev枠: ",bx_n,"日ロード | 急減-",DoubleToString(BfxDropPct,0),"%/5日 | 保有",BfxHoldDays,"日");
   return true;   // ライブは0件でも枠維持（決済独立・fetch再試行）
}

double BfxValAt(long day)
{
   for(int i=bx_n-1;i>=0;i--){
      if(bx_day[i]<=day){
         if(day-bx_day[i]<=3) return bx_val[i];
         return -1;
      }
   }
   return -1;
}

bool BfxEnsure(datetime bt)
{
   if(MQLInfoInteger(MQL_TESTER)) return (bx_n>0);
   long yday=(long)bt/86400-1;
   if(bx_n>0 && bx_day[bx_n-1]>=yday) return true;
   if(!BfxUseWebRequest){
      long tt[]; double tv[];
      int n=BfxLoadCsv(BfxFile,tt,tv);
      if(n>0) BfxCommit(tt,tv,n,false);
      return (bx_n>0 && bx_day[bx_n-1]>=yday);
   }
   if(TimeCurrent()-g_bfxFetchAt<3600) return false;
   g_bfxFetchAt=TimeCurrent();
   if(BfxFetch()) return (bx_day[bx_n-1]>=yday);
   return (bx_n>0 && bx_day[bx_n-1]>=yday);
}

int BfxBarsHeld(int i)
{
   for(int k=PositionsTotal()-1;k>=0;k--){
      if(PositionGetSymbol(k)==S[i].symbol && PositionGetInteger(POSITION_MAGIC)==S[i].magic){
         datetime opened=(datetime)PositionGetInteger(POSITION_TIME);
         return iBarShift(S[i].symbol,PERIOD_D1,opened,false);
      }
   }
   return 0;
}

void ProcBfx(int i)
{
   datetime bt=iTime(S[i].symbol,PERIOD_D1,0);
   if(bt==0) return;
   trade.SetExpertMagicNumber(S[i].magic);

   // 決済はデータ非依存（保有日数のみ）
   if(HasAny(i)){
      if(BfxBarsHeld(i)>=BfxHoldDays) CloseSleeveAll(i);
      g_bfxEvalBar=bt;
      return;
   }
   if(g_bfxEvalBar==bt) return;
   if(!BfxEnsure(bt)) return;
   long yday=(long)bt/86400-1;
   double v1=BfxValAt(yday), v0=BfxValAt(yday-5);
   g_bfxEvalBar=bt;
   if(v1<=0 || v0<=0) return;
   double chg=(v1/v0-1)*100;
   if(chg<-BfxDropPct && CryptoGuardOK(i)){
      double ask=SymbolInfoDouble(S[i].symbol,SYMBOL_ASK);
      double sl=(S[i].disasterSL>0 ? NormalizeDouble(ask*(1-S[i].disasterSL/100),S[i].digits) : 0);
      if(trade.Buy(Clamp(S[i].symbol,S[i].lot*S[i].lotMult*GlobalLotMult),S[i].symbol,ask,sl,0,"BfxRev"))
         Print("[BFXREV BUY] long建玉",DoubleToString(chg,1),"%/5日");
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

//============================ SCA（セッションORB）============================
// SCA_EA v1.5の本番採用機能のみ移植: セッション時刻/MinRangeフィルタ/金曜スキップ/
// リバーサル型増しロット。検証用オプション（Partial/Retest/StopOrders/ML等）は非搭載。
bool SCARange(int i, datetime day_start)
{
   string sym=S[i].symbol; ENUM_TIMEFRAMES tf=S[i].tf;
   datetime t_from=day_start+S[i].scaRangeStart*3600;
   datetime t_to  =day_start+S[i].scaRangeEnd*3600;
   double hi=-DBL_MAX, lo=DBL_MAX, openF=0, closeL=0;
   bool haveL=false;
   int bars=Bars(sym,tf);
   for(int sft=1; sft<200; sft++){
      if(sft>=bars) break;
      datetime bt2=iTime(sym,tf,sft);
      if(bt2<t_from) break;
      if(bt2>=t_to) continue;
      double h=iHigh(sym,tf,sft), l=iLow(sym,tf,sft);
      if(h>hi) hi=h;
      if(l<lo) lo=l;
      if(!haveL){ closeL=iClose(sym,tf,sft); haveL=true; }
      openF=iOpen(sym,tf,sft);
   }
   if(hi<=-DBL_MAX || lo>=DBL_MAX) return false;
   S[i].scaRangeHigh=hi;
   S[i].scaRangeLow=lo;
   S[i].scaDrift=closeL-openF;   // リバーサル判定用（窓内ドリフト）
   return true;
}

void ProcSCA(int i)
{
   string sym=S[i].symbol; ENUM_TIMEFRAMES tf=S[i].tf;
   datetime bt=iTime(sym,tf,0);
   MqlDateTime dt; TimeToStruct(bt,dt);
   datetime day_start=bt-(dt.hour*3600+dt.min*60+dt.sec);

   if(day_start!=S[i].scaDay){
      S[i].scaDay=day_start;
      S[i].scaReady=false; S[i].scaSkip=false;
      S[i].scaTradedL=false; S[i].scaTradedS=false;
   }
   trade.SetExpertMagicNumber(S[i].magic);

   if(dt.hour>=S[i].scaForceClose){ CloseSleeveAll(i); return; }

   if(!S[i].scaReady && dt.hour>=S[i].scaRangeEnd){
      if(!SCARange(i, day_start)) return;
      S[i].scaReady=true;
      double ab[]; ArraySetAsSeries(ab,true);
      if(CopyBuffer(S[i].hATR,0,1,1,ab)<1) return;
      double atrd=ab[0], w=S[i].scaRangeHigh-S[i].scaRangeLow;
      if(atrd<=0 || w<S[i].scaMinRange*atrd || w>S[i].scaMaxRange*atrd)
         S[i].scaSkip=true;
      // レンジ確定の意思決定コンテキストを記録（バックテストとの乖離分析用）
      OpsWrite("SCA_RANGE", S[i].magic, sym,
               S[i].scaRangeHigh, S[i].scaRangeLow, w, atrd, S[i].scaDrift,
               S[i].scaSkip ? 1 : 0, S[i].scaSkip ? "SKIP" : "ACTIVE");
   }
   if(!S[i].scaReady || S[i].scaSkip) return;
   if(dt.hour<S[i].scaRangeEnd || dt.hour>=S[i].scaTradeEnd) return;
   if(S[i].scaSkipFriday && dt.day_of_week==5) return;

   double ab2[]; ArraySetAsSeries(ab2,true);
   if(CopyBuffer(S[i].hATR,0,1,1,ab2)<1) return;
   double atrd=ab2[0]; if(atrd<=0) return;
   double buffer=S[i].scaBuf*atrd;
   double close1=iClose(sym,tf,1);
   bool hasB=HasPos(i,POSITION_TYPE_BUY), hasS=HasPos(i,POSITION_TYPE_SELL);

   // 上抜けブレイク → 買い
   if(close1>S[i].scaRangeHigh+buffer && !hasB && !S[i].scaTradedL){
      double ask=SymbolInfoDouble(sym,SYMBOL_ASK);
      double sl=S[i].scaRangeLow, dist=ask-sl;
      if(dist>0){
         double lot=S[i].lot*GlobalLotMult*S[i].lotMult;
         if(S[i].scaRevBoost && S[i].scaDrift<0) lot*=S[i].scaBoostMult;   // リバーサル型
         double tp=NormalizeDouble(ask+S[i].rr*dist,S[i].digits);
         if(trade.Buy(Clamp(sym,lot),sym,ask,NormalizeDouble(sl,S[i].digits),tp,"SCA-L"))
            S[i].scaTradedL=true;
      }
   }
   // 下抜けブレイク → 売り
   if(close1<S[i].scaRangeLow-buffer && !hasS && !S[i].scaTradedS){
      double bid=SymbolInfoDouble(sym,SYMBOL_BID);
      double sl=S[i].scaRangeHigh, dist=sl-bid;
      if(dist>0){
         double lot=S[i].lot*GlobalLotMult*S[i].lotMult;
         if(S[i].scaRevBoost && S[i].scaDrift>0) lot*=S[i].scaBoostMult;
         double tp=NormalizeDouble(bid-S[i].rr*dist,S[i].digits);
         if(trade.Sell(Clamp(sym,lot),sym,bid,NormalizeDouble(sl,S[i].digits),tp,"SCA-S"))
            S[i].scaTradedS=true;
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

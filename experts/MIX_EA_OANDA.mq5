//+------------------------------------------------------------------+
//|  MIX_EA_OANDA.mq5（OANDA証券・国内版）                            |
//|  統合ポートフォリオEA v1.0 = PortfolioEA_OANDA（既存ブック10枠）+ |
//|  SCA（セッションORBスキャルパー3枠・第1/第2バックログ最終形）。   |
//|  OANDA仕様差の吸収（PortfolioEA_OANDAから継承）:                  |
//|   (1) 全枠の銘柄名を input 化（サフィックス差・GOLD→XAUUSD）。    |
//|   (2) ETHUSD枠は OANDA に暗号資産CFDが無いため既定OFF（取扱不可）。|
//|   (3) XAUUSD は実機OANDA本番端末でFX枠と同一端末稼働を確認済み。  |
//|       ※口座にCFDアクセスが無い場合は En_PB_GOLD/En_SCA_GOLD=false |
//|  SCA枠: XAUUSD(Range1-9h/TE15/FC20/MinR0.40/金曜スキップ/Revブースト)|
//|         USDJPY/GBPJPY(Range0-9h/TE12/FC22/MinR0.30/Revブースト)   |
//|  ※OANDAのサーバー時刻はXMと同一のGMT+2/+3系と検証済み（時刻     |
//|    パラメータ変更不要）。JPYペアのSCAはOANDAのタイトなスプレッド  |
//|    でXM比+64〜139%の検証実績（docs/sca_ea.md）。                  |
//|  ※ライブ運用専用。各戦略の検証は個別EA(mt5bt)を使うこと。        |
//|  使い方: docs/MIX_EA_UM.md                                        |
//|  【2026-07-12 XM v1.3統合レビュー】BTC funding逆張り/BfxRev/       |
//|  ETH A2デュアルMAの暗号3戦略は、OANDA証券が暗号資産CFD非対応の    |
//|  ため本EAには追加不可（XM版MIX_EA v1.3専用）。本EAは13枠のまま。  |
//+------------------------------------------------------------------+
// v1.2: 利益トレール（含み益が残高比%刻みでSLを段階的に引き上げ・既定OFF）
// v1.1: アーム状態のGlobalVariable永続化（再起動でPB armed/RSI wasOB等/
//       SCA日次状態を失わない。テスターでは無効・挙動不変）
#property copyright "2026"
#property version   "1.20"
#property strict

#include <Trade\Trade.mqh>

//=== 枠ON/OFF（運用時に個別に止められる）===
input group "=== 枠の有効/無効 ==="
input bool En_PB_USDJPY  = true;
input bool En_PB_GBPJPY  = true;
input bool En_PB_AUDJPY  = false;  // 死に枠（デプロイ除外）。既定OFF
input bool En_PB_GOLD    = true;   // XAUUSD。実機OANDA本番端末でFX枠と同一端末稼働を確認済（CFDアクセス前提・無ければfalse）
input bool En_RSI_USDJPY = true;
input bool En_RSI_EURUSD = true;
input bool En_RSI_GBPUSD = true;   // レンジ枠強化（横展開で採用）
input bool En_PAIR       = true;
input bool En_CARRY      = true;
input bool En_VBO        = false;  // 2026-08-08: every_tick実費検証でOOS一貫マイナス判明のため除外
                                    // （docs/codex_verification_20260808.md）
input bool En_ETH        = false;  // ETHUSD＝OANDAは暗号資産CFD取扱なし。既定OFF（取扱不可）
input bool En_SCA_GOLD   = true;   // SCA XAUUSD（CFDアクセス前提・無ければfalse）
input bool En_SCA_USDJPY = true;   // SCA USDJPY（OANDAスプレッドでXM比+139%の検証実績）
input bool En_SCA_GBPJPY = true;   // SCA GBPJPY（同+64%）

input group "=== 銘柄名（OANDA仕様・ブローカーのサフィックス差を吸収）==="
input string Sym_USDJPY = "USDJPY";   // FX
input string Sym_GBPJPY = "GBPJPY";   // FX
input string Sym_AUDJPY = "AUDJPY";   // FX（PB死に枠＋Carry）
input string Sym_EURUSD = "EURUSD";   // FX（RSI＋Pairの主）
input string Sym_GBPUSD = "GBPUSD";   // FX（RSI＋Pairの従）
input string Sym_GOLD   = "XAUUSD";   // 商品CFD専用口座（OANDAは XAUUSD）
input string Sym_ETHUSD = "ETHUSD";   // 暗号資産＝OANDA取扱なし（En_ETH=false既定）

input group "=== 利益トレール（v1.2・既定OFF） ==="
// 含み益が口座残高のStep%に達したらSLを「残高のLock%の利益を確保する価格」へ移動し、
// 以後はStep%増えるごとに同じ幅だけSLを引き上げる（追従幅は Step-Lock で一定）。
// 例（Step=0.5 / Lock=0.1・残高10万円）: +500円→SL=+100円 / +1,000円→+600円 / +1,500円→+1,100円
// SLは改善方向にのみ動かし、現値やストップレベルを跨ぐ位置には置かない。
// 対象は本EAが建てた全ポジション（PairTrade/Carryなど本来SLを持たない枠にもSLが付く点に注意）。
input bool   UseProfitTrail    = false;  // 利益トレールを使用する
input double ProfitTrail_Step  = 0.5;    // 発動・引き上げの刻み（口座残高に対する%）
input double ProfitTrail_Lock  = 0.1;    // 初回発動時に確保する利益（口座残高に対する%）

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
input double Mult_SCA_GOLD   = 1.0;   // 例: ミックスB相当なら3.0（0.01→0.03）
input double Mult_SCA_USDJPY = 1.0;
input double Mult_SCA_GBPJPY = 1.0;

input group "=== risk%/複利枠の基準資金（0=口座equity・>0で配分資金固定） ==="
input double RefCap_PB_USDJPY = 0;   // PB USDJPY risk%の基準資金（配分額）
input double RefCap_PB_GBPJPY = 0;   // PB GBPJPY risk%の基準資金
input double RefCap_CARRY      = 0;  // Carry複利の基準資金

input group "=== Carry執行TF（OANDA: D1始値の market closed 回避） ==="
// Carry枠の新バー検出/執行TF。判定（MA200・終値）はD1のまま。
// OANDA-JapanはD1始値(00:00)の成行が market closed で失敗するため既定H1（開場中のH1始値で約定）。
// XM等で従来どおりD1執行に戻すなら PERIOD_D1 を指定。
input ENUM_TIMEFRAMES Carry_ExecTF = PERIOD_H1;

input group "=== 出力（検証用・ライブでは空でOK）==="
input string ResultFileName = "";
input string EquityLogFile  = "";

input group "=== 運用ログ（フォワード分析用・ライブで有効化） ==="
// MQL5\Files\<prefix>_YYYYMM.csv に月次追記。3種のレコードを出力:
//  DEAL      = 全約定（IN/OUT・枠Magic・ロット・価格・SL/TP・損益）
//  SCA_RANGE = SCA枠の日次レンジ確定情報（高安・幅・ATRd・ドリフト・スキップ有無）
//  DAILY     = 日次スナップショット（equity/balance/証拠金/保有数）
input bool   EnableOpsLog = false;
input string OpsLogPrefix = "mixlog_oa";

//=== 戦略種別 ===
enum ESTRAT { ST_PULLBACK, ST_RSI, ST_PAIR, ST_CARRY, ST_VBO, ST_SCA };

//=== 枠定義＋状態 ===
struct SLEEVE
{
   bool            enabled;
   ESTRAT          strat;
   string          symbol;
   ENUM_TIMEFRAMES tf;
   ENUM_TIMEFRAMES execTf;       // 新バー検出/執行TF（PERIOD_CURRENT=tfと同一）。判定はtfのまま
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
   bool            useADX;   double adxThr; int adxPeriod;
   // PB EMA組（スリーブ別）
   int             fastEMA, slowEMA;
   // PB 構造TP（B10: 直近スイング高安をTP上限に使う）
   bool            useStructTP; int structLB; double structMinRR;
   // PB マルチタイムフレーム合流フィルター
   bool            useHigherTF; ENUM_TIMEFRAMES higherTF; int higherTFMA; int hHigherTrend;
   // PB 状態
   bool            armedBuy, armedSell;
   // RSI
   double          bbDev, rsiOBX, rsiOB, rsiOSX, rsiOS; int bbPeriod;
   bool            useDP; int swingLB, dpBars; double dpTolATR;
   bool            useRange; double rangeMaxATR; int rangeLB;
   bool            wasOB, wasOS, aboveBB, belowBB;
   // PAIR
   string          second; int lookback; double entryZ, exitZ, stopZ;
   // CARRY
   int             trendPeriod; bool reqPosSwap;
   bool            useHyst; double hystMult;   // MAクロス・ヒステリシス帯（AUDJPYのみ採用）
   int             cdBars; datetime cdExitBar; // 退出後クールダウン（XM版から移植・S9）
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
   //    v1.9: ADX_Threshold 22.5→27.5（トレードオフ8案の組合せ検証#3。
   //    docs/tradeoff8_combined_20260812.md）
   { SLEEVE x=pb; x.enabled=En_PB_USDJPY; x.symbol=Sym_USDJPY; x.magic=20260622;
     x.useRisk=true; x.riskPct=2.0; x.lot=0.01; x.lotMult=Mult_PB_USDJPY; x.refCap=RefCap_PB_USDJPY;
     x.useHigherTF=true; x.higherTF=PERIOD_D1; x.higherTFMA=200;
     x.adxThr=27.5; AddSleeve(x); }
   // 2. PB GBPJPY (risk2%) — MTF合流フィルター採用（D1トレンド一致必須）
   //    v1.3: MA_Slope_Min_ATR 1.2→1.5, RR_Ratio 2.0→3.5（応答曲面M366・本番同一条件tier2確認:
   //    IS-90→+18,665／OOS+13,254→+4,641。現状市場(IS)の利益を優先しユーザー承認、
   //    OOS低下は許容。docs/new_strategies_round2_20260805.md）
   //    v1.4: RR_Ratio 3.5→4.0（Codex提案11の近傍応答曲面・本番同一条件tier2確認:
   //    IS+18,665→+29,315／OOS+4,641→+10,197。トレードオフなしの純改善。
   //    docs/codex_verification_20260808.md）
   //    v1.5: ADX_Period 14→10（Codex 500案応答曲面C・IS+29,315→+31,611／OOS+10,197→+14,670。
   //    トレードオフなしの純改善。docs/codex500_verification_20260810.md）
   //    v1.6: EMA組 20/50→25/60（Codex 500案残余F5・IS+31,611→+33,133/OOS+14,670→+20,763・
   //    DD 18.13→14.68%＝トレードオフなしの純改善。docs/codex500_verification2_20260810.md）
   //    ⚠️構造TP(B10)はEMA25/60採用後にON/OFFで結果が完全一致＝発火せず無効と実測判明。
   //      MinRR0.5まで下げると発火するが激しく悪化するため既定OFFのまま温存（XM版と同一判断）。
   { SLEEVE x=pb; x.enabled=En_PB_GBPJPY; x.symbol=Sym_GBPJPY; x.magic=20260627;
     x.useRisk=true; x.riskPct=2.0; x.lot=0.01; x.lotMult=Mult_PB_GBPJPY; x.refCap=RefCap_PB_GBPJPY;
     x.useHigherTF=true; x.higherTF=PERIOD_D1; x.higherTFMA=200;
     x.slopeMinATR=1.5; x.rr=4.0; x.adxPeriod=10; x.adxThr=30.0;   // v1.8: ADX閾値22.5→30
     x.fastEMA=25; x.slowEMA=35; AddSleeve(x); }   // v1.9: SlowEMA 60→35（組合せ検証#4）
   // 3. PB AUDJPY (固定・除外枠)
   //    v1.9: RR_Ratio 2.0→5.0（組合せ検証#5・両期間で明確に黒字化）
   { SLEEVE x=pb; x.enabled=En_PB_AUDJPY; x.symbol=Sym_AUDJPY; x.magic=20260628;
     x.useRisk=false; x.lot=0.01; x.rr=5.0; AddSleeve(x); }
   // 4. PB GOLD→XAUUSD (固定) ※商品CFD専用口座
   { SLEEVE x=pb; x.enabled=En_PB_GOLD; x.symbol=Sym_GOLD; x.magic=20260640;
     x.useRisk=false; x.lot=0.01; x.lotMult=Mult_PB_GOLD; AddSleeve(x); }

   //--- RSI_Reversal 共通プリセット ---
   SLEEVE rs = z;
   rs.strat=ST_RSI; rs.bbDev=2.5; rs.rsiOBX=75.0; rs.rsiOB=72.5; rs.rsiOSX=27.5; rs.rsiOS=30.0;
   rs.useRange=true; rs.rangeMaxATR=0.2; rs.rangeLB=20; rs.useATRstops=false;
   rs.swingLB=3; rs.dpTolATR=0.5; rs.useRisk=false; rs.lot=0.01;

   // 5. RSI USDJPY H4 (DP ON, SL50/TP110)
   //    v1.9: DP_Tolerance_ATR 0.5→1.5（組合せ検証#6・両期間が均等に高い構成）
   { SLEEVE x=rs; x.enabled=En_RSI_USDJPY; x.symbol=Sym_USDJPY; x.tf=PERIOD_H4; x.magic=20260610;
     x.useDP=true; x.dpBars=100; x.dpTolATR=1.5; x.slPips=50; x.tpPips=110;
     x.lotMult=Mult_RSI_USDJPY; AddSleeve(x); }
   // 6. RSI EURUSD H1 (DP OFF, SL25/TP105)
   //    v1.8: StopLoss_Pips 45→25（全パラメータ再最適化・OOS赤字-1,867→+2,582へ黒字転換。
   //    docs/param_reopt_20260811.md）
   { SLEEVE x=rs; x.enabled=En_RSI_EURUSD; x.symbol=Sym_EURUSD; x.tf=PERIOD_H1; x.magic=20260605;
     x.useDP=false; x.dpBars=60; x.slPips=25; x.tpPips=105; x.lotMult=Mult_RSI_EURUSD; AddSleeve(x); }
   // 6b. RSI GBPUSD H4 (DP OFF, SL50/TP110) — レンジ枠強化
   //     v1.3: BB_Deviation 2.5→2.0（応答曲面M129・本番同一条件tier2確認: IS+5,241→+12,442/
   //     OOS+11,464→+16,020、docs/new_strategies_round2_20260805.md）
   //     v1.4: BB_Period 20→30（Codex 500案応答曲面B・IS+12,442→+13,398／OOS+16,045→+18,922。
   //     トレードオフなしの純改善。docs/codex500_verification_20260810.md）
   { SLEEVE x=rs; x.enabled=En_RSI_GBPUSD; x.symbol=Sym_GBPUSD; x.tf=PERIOD_H4; x.magic=20260774;
     x.useDP=false; x.dpBars=100; x.slPips=50; x.tpPips=110; x.bbDev=2.0; x.bbPeriod=30;
     x.lotMult=Mult_RSI_GBPUSD; AddSleeve(x); }

   // 7. PairTrade EURUSD/GBPUSD H1
   { SLEEVE x=z; x.enabled=En_PAIR; x.strat=ST_PAIR; x.symbol=Sym_EURUSD; x.second=Sym_GBPUSD;
     x.tf=PERIOD_H1; x.magic=20260629; x.lot=0.01; x.useRisk=false; x.refDeposit=100000;
     x.lookback=200; x.entryZ=4.0; x.exitZ=-1.0; x.stopZ=5.0; x.lotMult=Mult_PAIR; AddSleeve(x); }

   // 8. Carry AUDJPY 判定D1・執行Carry_ExecTF(既定H1) (複利0.05, スワップ条件ON, ヒステリシス帯±0.75ATR採用)
   { SLEEVE x=z; x.enabled=En_CARRY; x.strat=ST_CARRY; x.symbol=Sym_AUDJPY; x.tf=PERIOD_D1;
     x.execTf=Carry_ExecTF;
     x.magic=20260650; x.trendPeriod=200; x.reqPosSwap=true;
     x.useHyst=true; x.hystMult=0.75; x.cdBars=10;   // v1.9: cooldown 0→10（組合せ検証#7）
     x.useRisk=true; x.lot=0.05; x.refDeposit=100000; x.lotMult=Mult_CARRY; x.refCap=RefCap_CARRY; AddSleeve(x); }

   // 9. VolBreakout USDJPY H4 (固定)
   { SLEEVE x=z; x.enabled=En_VBO; x.strat=ST_VBO; x.symbol=Sym_USDJPY; x.tf=PERIOD_H4;
     x.magic=20260680; x.lot=0.01; x.useRisk=false; x.channel=20;
     x.useSqueeze=true; x.sqLB=50; x.sqFactor=1.0; x.atrSLmult=2.0; x.trailMult=3.0; x.lotMult=Mult_VBO; AddSleeve(x); }

   // 10. 暗号トレンド ETHUSD D1 (Carryロジック, スワップ条件OFF, 固定0.05) ※OANDA取扱なし→既定OFF
   //     v1.8: TrendMA_Period 200→150（全パラメータ再最適化・両期間で利益/PF/DD改善。
   //     docs/param_reopt_20260811.md。※OANDA取扱なしで既定OFFのため実運用への影響なし）
   { SLEEVE x=z; x.enabled=En_ETH; x.strat=ST_CARRY; x.symbol=Sym_ETHUSD; x.tf=PERIOD_D1;
     x.magic=20260710; x.trendPeriod=150; x.reqPosSwap=false;
     x.useRisk=false; x.lot=0.05; x.refDeposit=100000; x.lotMult=Mult_ETH; AddSleeve(x); }

   //--- SCA セッションORB（第1/第2バックログ最終形・検証: docs/sca_ea.md）---
   // 11. SCA XAUUSD M15（Range1-9h/TE15/FC20/MinR0.40/buf0.05/RR1.5/金曜スキップ/Revブースト）
   { SLEEVE x=z; x.enabled=En_SCA_GOLD; x.strat=ST_SCA; x.symbol=Sym_GOLD; x.tf=PERIOD_M15;
     x.magic=20261002; x.lot=0.01; x.useRisk=false; x.rr=1.5; x.lotMult=Mult_SCA_GOLD;
     x.scaRangeStart=1; x.scaRangeEnd=9; x.scaTradeEnd=15; x.scaForceClose=20;
     x.scaMinRange=0.40; x.scaMaxRange=1.00; x.scaBuf=0.05;
     x.scaSkipFriday=true; x.scaRevBoost=true; x.scaBoostMult=2.0; AddSleeve(x); }
   // 12. SCA USDJPY M15（Range0-9h/TE12/FC22/MinR0.30/buf0.10/RR2.0/Revブースト）
   //     v1.8: Break_Buffer_ATRd 0.05→0.10（全パラメータ再最適化・OOS赤字-4,875→+110へ黒字転換。
   //     ⚠️ただしOOS+110円/PF1.0024と経済的には極薄。docs/param_reopt_20260811.md）
   { SLEEVE x=z; x.enabled=En_SCA_USDJPY; x.strat=ST_SCA; x.symbol=Sym_USDJPY; x.tf=PERIOD_M15;
     x.magic=20261000; x.lot=0.01; x.useRisk=false; x.rr=2.0; x.lotMult=Mult_SCA_USDJPY;
     x.scaRangeStart=0; x.scaRangeEnd=9; x.scaTradeEnd=12; x.scaForceClose=22;
     x.scaMinRange=0.30; x.scaMaxRange=1.00; x.scaBuf=0.10;
     x.scaSkipFriday=false; x.scaRevBoost=true; x.scaBoostMult=2.0; AddSleeve(x); }
   // 13. SCA GBPJPY M15（初版形: buf0）
   //     v1.3: Boost_Mult 2.0→3.0（応答曲面M239・本番同一条件tier2確認: IS+27,445→+39,027/
   //     OOS+11,127→+23,451、docs/new_strategies_round2_20260805.md）
   //     v1.6: Boost_Mult 3.0→4.0（Codex 500案残余F21・IS+39,027→+50,609/OOS+23,451→+35,775。
   //     ⚠️利益+30〜53%と引き換えにDDも悪化(IS 24.01→26.45%・OOS 17.37→19.32%)＝
   //     利益とリスクのトレードオフをユーザー承認のうえ採用。
   //     docs/codex500_verification2_20260810.md）
   //     v1.7: Boost_Mult 4.0→6.0（Codex 500案ラウンド3 R3F09・IS+50,609→+73,773/
   //     OOS+35,775→+60,423＝利益+46〜69%。⚠️DDも悪化(IS 26.45→30.03%・OOS 19.32→22.95%)だが
   //     利益/DD比は単調改善。⚠️Boost4.5はロット丸めで4.0と同値＝整数倍のみ有効。
   //     docs/codex500_round3_20260811.md）
   { SLEEVE x=z; x.enabled=En_SCA_GBPJPY; x.strat=ST_SCA; x.symbol=Sym_GBPJPY; x.tf=PERIOD_M15;
     x.magic=20261001; x.lot=0.01; x.useRisk=false; x.rr=2.0; x.lotMult=Mult_SCA_GBPJPY;
     x.scaRangeStart=0; x.scaRangeEnd=9; x.scaTradeEnd=12; x.scaForceClose=22;
     x.scaMinRange=0.30; x.scaMaxRange=1.00; x.scaBuf=0.0;
     x.scaSkipFriday=false; x.scaRevBoost=true; x.scaBoostMult=6.0; AddSleeve(x); }

   // ハンドル生成・銘柄メタ
   for(int i=0;i<NS;i++)
   {
      if(S[i].execTf==PERIOD_CURRENT) S[i].execTf=S[i].tf;  // 既定: 執行TF=判定TF（Carryのみ別TF）
      if(!S[i].enabled) continue;
      if(!SymbolSelect(S[i].symbol, true))
         Print("⚠ 銘柄が見つかりません（名前/サフィックス要確認）: ", S[i].symbol, " (magic=", S[i].magic, ")");
      if(S[i].second!="") SymbolSelect(S[i].second, true);
      S[i].digits = (int)SymbolInfoInteger(S[i].symbol, SYMBOL_DIGITS);
      S[i].point  = SymbolInfoDouble(S[i].symbol, SYMBOL_POINT);
      S[i].pip    = (S[i].digits==3 || S[i].digits==5) ? 10*S[i].point : S[i].point;
      S[i].lastBar = 0;
      if(S[i].strat==ST_PULLBACK){
         S[i].hTrend=iMA(S[i].symbol,S[i].tf,200,0,MODE_SMA,PRICE_CLOSE);
         S[i].hFast =iMA(S[i].symbol,S[i].tf,S[i].fastEMA,0,MODE_EMA,PRICE_CLOSE);
         S[i].hSlow =iMA(S[i].symbol,S[i].tf,S[i].slowEMA,0,MODE_EMA,PRICE_CLOSE);
         S[i].hATR  =iATR(S[i].symbol,S[i].tf,14);
         S[i].hADX  =iADX(S[i].symbol,S[i].tf,S[i].adxPeriod);
         if(S[i].useHigherTF)
            S[i].hHigherTrend=iMA(S[i].symbol,S[i].higherTF,S[i].higherTFMA,0,MODE_SMA,PRICE_CLOSE);
      } else if(S[i].strat==ST_RSI){
         S[i].hRSI =iRSI(S[i].symbol,S[i].tf,14,PRICE_CLOSE);
         S[i].hTrend=iMA(S[i].symbol,S[i].tf,200,0,MODE_SMA,PRICE_CLOSE);
         S[i].hBB  =iBands(S[i].symbol,S[i].tf,S[i].bbPeriod,0,S[i].bbDev,PRICE_CLOSE);
         S[i].hATR =iATR(S[i].symbol,S[i].tf,14);
      } else if(S[i].strat==ST_CARRY){
         S[i].hTrend=iMA(S[i].symbol,S[i].tf,S[i].trendPeriod,0,MODE_SMA,PRICE_CLOSE);
         if(S[i].useHyst) S[i].hATR=iATR(S[i].symbol,S[i].tf,14);
      } else if(S[i].strat==ST_VBO){
         S[i].hATR =iATR(S[i].symbol,S[i].tf,14);
      } else if(S[i].strat==ST_SCA){
         S[i].hATR =iATR(S[i].symbol,PERIOD_D1,14);   // レンジ幅正規化用のD1 ATR
      }
   }
   // v1.1: アーム状態の復元（ライブのみ。テスターでは何もしない）
   int restored = StRestore();
   if(StLive())
      Print("状態永続化: ", restored>0 ? IntegerToString(restored)+"枠のアーム状態を復元"
                                       : "保存済み状態なし（初回起動または期限切れ）");
   if(UseProfitTrail)
      PrintFormat("利益トレール: ON | 刻み%.2f%% / 初回確保%.2f%%（追従幅%.2f%%）",
                  ProfitTrail_Step, ProfitTrail_Lock, ProfitTrail_Step - ProfitTrail_Lock);
   Print("MIX_EA_OANDA v1.2 起動 | 有効枠数=", CountEnabled(), "/", NS,
         " | Master=", MasterEnable?"ON":"OFF", " | LotMult=", GlobalLotMult);
   return INIT_SUCCEEDED;
}

void ZeroSleeve(SLEEVE &x)
{
   x.enabled=false; x.strat=ST_PULLBACK; x.symbol=""; x.tf=PERIOD_H4; x.execTf=PERIOD_CURRENT; x.magic=0;
   x.lot=0.01; x.useRisk=false; x.riskPct=0; x.refDeposit=100000;
   x.pip=0; x.digits=5; x.point=0; x.lastBar=0;
   x.hTrend=INVALID_HANDLE; x.hFast=INVALID_HANDLE; x.hSlow=INVALID_HANDLE;
   x.hATR=INVALID_HANDLE; x.hADX=INVALID_HANDLE; x.hRSI=INVALID_HANDLE; x.hBB=INVALID_HANDLE;
   x.useATRstops=false; x.atrSLmult=0; x.rr=0; x.slPips=0; x.tpPips=0;
   x.useTrend=false; x.slopeMinATR=0; x.slopeLB=20; x.useADX=false; x.adxThr=0; x.adxPeriod=14;
   x.fastEMA=20; x.slowEMA=50;
   x.useStructTP=false; x.structLB=50; x.structMinRR=0.5;
   x.useHigherTF=false; x.higherTF=PERIOD_D1; x.higherTFMA=200; x.hHigherTrend=INVALID_HANDLE;
   x.armedBuy=false; x.armedSell=false;
   x.bbDev=2.0; x.bbPeriod=20; x.rsiOBX=0; x.rsiOB=0; x.rsiOSX=0; x.rsiOS=0;
   x.useDP=false; x.swingLB=3; x.dpBars=100; x.dpTolATR=0.5;
   x.useRange=false; x.rangeMaxATR=0; x.rangeLB=20;
   x.wasOB=false; x.wasOS=false; x.aboveBB=false; x.belowBB=false;
   x.second=""; x.lookback=200; x.entryZ=0; x.exitZ=0; x.stopZ=0;
   x.trendPeriod=200; x.reqPosSwap=false;
   x.useHyst=false; x.hystMult=0.75;
   x.cdBars=0; x.cdExitBar=0;
   x.channel=20; x.useSqueeze=false; x.sqLB=50; x.sqFactor=1.0; x.trailMult=0;
   x.lotMult=1.0; x.refCap=0.0;
   x.scaRangeStart=0; x.scaRangeEnd=9; x.scaTradeEnd=15; x.scaForceClose=22;
   x.scaMinRange=0.30; x.scaMaxRange=1.00; x.scaBuf=0.0;
   x.scaSkipFriday=false; x.scaRevBoost=false; x.scaBoostMult=2.0;
   x.scaDay=0; x.scaRangeHigh=0; x.scaRangeLow=0; x.scaDrift=0;
   x.scaReady=false; x.scaSkip=false; x.scaTradedL=false; x.scaTradedS=false;
}

int CountEnabled(){ int c=0; for(int i=0;i<NS;i++) if(S[i].enabled) c++; return c; }

//============================ アーム状態の永続化（v1.1） ============================
// PB armed / RSI wasOB・wasOS・aboveBB・belowBB / SCA日次状態はメモリのみに存在し、
// EA再起動で消えるとアーム済みシグナルをライブだけ取り損ねる
// （2026-08-02 フォワードvsBT照合で実証: docs/forward_vs_backtest_20260802.md 原因B）。
// ライブのみGlobalVariableへ保存しOnInitで復元する。テスター/最適化では完全無効＝挙動不変。
// lastBarは意図的に対象外（再起動直後の1回即時再評価は決済取り逃しの回収に働くため維持）。
// GlobalVariableは4週間無アクセスで自動削除されるため、日次で全枠を再保存してタッチする。
bool StLive(){ return !MQLInfoInteger(MQL_TESTER) && !MQLInfoInteger(MQL_OPTIMIZATION); }
string StKey(const int i, const string f){ return "MIXST_"+(string)S[i].magic+"_"+f; }

// 保存対象フィールドのスナップショット（変更検知用）
string StSnap(const int i)
{
   return StringFormat("%d%d%d%d%d%d|%I64d|%.8f|%.8f|%.8f|%d%d%d%d",
      (int)S[i].armedBuy,(int)S[i].armedSell,(int)S[i].wasOB,(int)S[i].wasOS,
      (int)S[i].aboveBB,(int)S[i].belowBB,
      (long)S[i].scaDay,
      S[i].scaRangeHigh,S[i].scaRangeLow,S[i].scaDrift,
      (int)S[i].scaReady,(int)S[i].scaSkip,(int)S[i].scaTradedL,(int)S[i].scaTradedS);
}

void StSave(const int i)
{
   if(!StLive()) return;
   GlobalVariableSet(StKey(i,"aB"), S[i].armedBuy  ? 1 : 0);
   GlobalVariableSet(StKey(i,"aS"), S[i].armedSell ? 1 : 0);
   GlobalVariableSet(StKey(i,"oB"), S[i].wasOB     ? 1 : 0);
   GlobalVariableSet(StKey(i,"oS"), S[i].wasOS     ? 1 : 0);
   GlobalVariableSet(StKey(i,"bU"), S[i].aboveBB   ? 1 : 0);
   GlobalVariableSet(StKey(i,"bL"), S[i].belowBB   ? 1 : 0);
   GlobalVariableSet(StKey(i,"sD"), (double)(long)S[i].scaDay);
   GlobalVariableSet(StKey(i,"sH"), S[i].scaRangeHigh);
   GlobalVariableSet(StKey(i,"sL"), S[i].scaRangeLow);
   GlobalVariableSet(StKey(i,"sF"), S[i].scaDrift);
   GlobalVariableSet(StKey(i,"s1"),
      (S[i].scaReady?1:0)+(S[i].scaSkip?2:0)+(S[i].scaTradedL?4:0)+(S[i].scaTradedS?8:0));
}

int StRestore()   // OnInit末尾から呼ぶ。復元できた枠数を返す
{
   if(!StLive()) return 0;
   int n=0;
   for(int i=0;i<NS;i++){
      if(!S[i].enabled) continue;
      if(!GlobalVariableCheck(StKey(i,"s1")) && !GlobalVariableCheck(StKey(i,"aB"))) continue;
      S[i].armedBuy  = (GlobalVariableGet(StKey(i,"aB"))!=0);
      S[i].armedSell = (GlobalVariableGet(StKey(i,"aS"))!=0);
      S[i].wasOB     = (GlobalVariableGet(StKey(i,"oB"))!=0);
      S[i].wasOS     = (GlobalVariableGet(StKey(i,"oS"))!=0);
      S[i].aboveBB   = (GlobalVariableGet(StKey(i,"bU"))!=0);
      S[i].belowBB   = (GlobalVariableGet(StKey(i,"bL"))!=0);
      S[i].scaDay    = (datetime)(long)GlobalVariableGet(StKey(i,"sD"));
      S[i].scaRangeHigh = GlobalVariableGet(StKey(i,"sH"));
      S[i].scaRangeLow  = GlobalVariableGet(StKey(i,"sL"));
      S[i].scaDrift     = GlobalVariableGet(StKey(i,"sF"));
      int f=(int)GlobalVariableGet(StKey(i,"s1"));
      S[i].scaReady=((f&1)!=0); S[i].scaSkip=((f&2)!=0);
      S[i].scaTradedL=((f&4)!=0); S[i].scaTradedS=((f&8)!=0);
      n++;
   }
   return n;
}

//============================ 利益トレール（v1.2） ============================
// 仕様: 含み益が「口座残高 × ProfitTrail_Step%」に達するごとに段階を1つ上げ、
//       第n段では「口座残高 × (Lock% + (n-1)×Step%)」の利益を確保する価格へSLを移動する。
//       Step=0.5 / Lock=0.1 なら 0.5%→+0.1% / 1.0%→+0.6% / 1.5%→+1.1%（追従幅0.4%固定）。
// 既定OFF。ONでも「改善方向のみ・現値/ストップレベルを跨がない」ため約定拒否は起きない。
int SleeveByMagic(const long m)
{
   for(int i=0;i<NS;i++) if(S[i].magic==m) return i;
   return -1;
}

// 利益トレールの対象枠: **FXのみ**（XAUUSDは対象外）かつ PairTrade / Carry を除外。
// 除外理由（2026-08-05 実測・docs/profit_trail_20260805.md）:
//  - GOLD（PB 20260640 / SCA 20261002）は利益が44%失われた（トレンド追随の大勝ちを刈る）
//  - PairTrade は2レグ同時決済のサヤ取りで、片脚だけSLに掛かるとヘッジが崩れる
//  - Carry は「SLを置かない」ことが設計思想（docs/carry.md）。ETH枠も ST_CARRY で同扱い
bool PtrailEligible(const int i)
{
   if(i < 0) return false;
   if(S[i].strat==ST_PAIR || S[i].strat==ST_CARRY)  return false;  // PairTrade / Carry / ETH
   if(S[i].magic==20260640 || S[i].magic==20261002) return false;  // PB GOLD / SCA GOLD
   return true;
}

void ProfitTrail()
{
   if(!UseProfitTrail) return;
   double bal = AccountInfoDouble(ACCOUNT_BALANCE);
   double step_money = bal * ProfitTrail_Step / 100.0;
   if(bal <= 0.0 || step_money <= 0.0) return;

   for(int k=PositionsTotal()-1;k>=0;k--)
   {
      ulong tk = PositionGetTicket(k);
      if(tk==0) continue;
      long mg = PositionGetInteger(POSITION_MAGIC);
      if(!PtrailEligible(SleeveByMagic(mg))) continue;   // FX枠のみ（Pair/Carry/GOLDは除外）

      string sym = PositionGetString(POSITION_SYMBOL);
      // 判定は実含み益（スワップ込み）
      double profit = PositionGetDouble(POSITION_PROFIT) + PositionGetDouble(POSITION_SWAP);
      int n = (int)MathFloor(profit / step_money);
      if(n < 1) continue;

      double lock_money = bal * ProfitTrail_Lock / 100.0 + (n - 1) * step_money;
      bool   is_buy = (PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY);
      double open_p = PositionGetDouble(POSITION_PRICE_OPEN);
      double cur_sl = PositionGetDouble(POSITION_SL);
      double tp     = PositionGetDouble(POSITION_TP);
      int    dg     = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
      double px     = is_buy ? SymbolInfoDouble(sym, SYMBOL_BID) : SymbolInfoDouble(sym, SYMBOL_ASK);

      // 値幅→金額の換算はポジション自身の損益から求める。
      // SYMBOL_TRADE_TICK_VALUE は建値通貨で返るブローカーがあり（XMのGOLD/ETH/BTCで実測）、
      // 口座通貨(JPY)前提で計算するとUSD建て銘柄でSL距離が約164倍になり一度も発動しない。
      double moved   = is_buy ? (px - open_p) : (open_p - px);
      double pprofit = PositionGetDouble(POSITION_PROFIT);
      if(moved <= 0.0 || pprofit <= 0.0) continue;
      double money_per_price = pprofit / moved;
      if(money_per_price <= 0.0) continue;
      double dist = lock_money / money_per_price;
      if(dist <= 0.0) continue;

      double newsl = NormalizeDouble(is_buy ? open_p + dist : open_p - dist, dg);

      if(is_buy  && !(newsl > cur_sl)) continue;
      if(!is_buy && !(cur_sl==0.0 || newsl < cur_sl)) continue;
      if((is_buy && newsl >= px) || (!is_buy && newsl <= px)) continue;

      long   stops = SymbolInfoInteger(sym, SYMBOL_TRADE_STOPS_LEVEL);
      double pt    = SymbolInfoDouble(sym, SYMBOL_POINT);
      if(stops > 0 && MathAbs(px - newsl) < stops * pt) continue;

      if(trade.PositionModify(tk, newsl, tp))
         OpsWrite("PTRAIL", mg, sym, n, profit, lock_money, newsl, px,
                  PositionGetDouble(POSITION_VOLUME), "STEP");
   }
}

//+------------------------------------------------------------------+
void OnTick()
{
   if(!MasterEnable) return;
   ProfitTrail();   // v1.2（既定OFF）。毎ティック評価してピークを取り逃さない
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
   // v1.1: 状態GVの日次タッチ（4週間無アクセス失効の回避・ライブのみ・EnableOpsLog非依存）
   if(StLive())
   {
      static datetime st_day = 0;
      datetime d2 = TimeCurrent() - (TimeCurrent() % 86400);
      if(d2 != st_day){ st_day = d2; for(int i=0;i<NS;i++) if(S[i].enabled) StSave(i); }
   }
   for(int i=0;i<NS;i++)
   {
      if(!S[i].enabled) continue;
      datetime bt = iTime(S[i].symbol, S[i].execTf, 0);  // 執行TFの新バーで評価（Carryは判定D1/執行H1）
      if(bt==0 || bt==S[i].lastBar) continue;   // 新バーのみ
      // VBOはバー内トレーリングのため毎バー評価。他もバー確定で処理。
      S[i].lastBar = bt;
      // v1.1: アーム状態が変化したバーだけ保存（ライブのみ。テスターではsnap生成もしない）
      string snap = StLive() ? StSnap(i) : "";
      switch(S[i].strat){
         case ST_PULLBACK: ProcPullback(i); break;
         case ST_RSI:      ProcRSI(i);      break;
         case ST_PAIR:     ProcPair(i);     break;
         case ST_CARRY:    ProcCarry(i);    break;
         case ST_VBO:      ProcVBO(i);      break;
         case ST_SCA:      ProcSCA(i);      break;
      }
      if(StLive() && StSnap(i)!=snap) StSave(i);
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
// B10構造TP: 直近スイング高安とRR由来TPの「近い方」の距離を返す。
// 構造が無い/近すぎる場合は従来RR距離のまま（＝エントリーは削らない）。
// 単体EA PullbackTrend.mq5 の StructureTP() と同一ロジック。
double StructTPDist(int i,const bool is_buy,const double entry,const double sl_dist,const double rr_tp)
{
   if(!S[i].useStructTP) return rr_tp;
   double h[],l[];
   ArraySetAsSeries(h,true); ArraySetAsSeries(l,true);
   if(CopyHigh(S[i].symbol,S[i].tf,1,S[i].structLB,h)<S[i].structLB) return rr_tp;
   if(CopyLow (S[i].symbol,S[i].tf,1,S[i].structLB,l)<S[i].structLB) return rr_tp;
   double lvl  = is_buy ? h[ArrayMaximum(h,0,S[i].structLB)]
                        : l[ArrayMinimum(l,0,S[i].structLB)];
   double dist = is_buy ? (lvl-entry) : (entry-lvl);
   if(dist<=0.0 || dist < S[i].structMinRR*sl_dist) return rr_tp;
   return MathMin(dist,rr_tp);
}

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
      double tpb=StructTPDist(i,true,ask,sld,tpd);   // B10
      trade.Buy(LotRisk(i,sld),sym,ask,
                NormalizeDouble(ask-sld,S[i].digits),NormalizeDouble(ask+tpb,S[i].digits),"PB");
      S[i].armedBuy=false;
   }
   if(es && !hs){
      if(hb) CloseType(i,POSITION_TYPE_BUY);
      double bid=SymbolInfoDouble(sym,SYMBOL_BID);
      double tps=StructTPDist(i,false,bid,sld,tpd);  // B10
      trade.Sell(LotRisk(i,sld),sym,bid,
                 NormalizeDouble(bid+sld,S[i].digits),NormalizeDouble(bid-tps,S[i].digits),"PB");
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
   // ヒステリシス帯: entry=MA+b×ATR / exit=MA−b×ATR（AUDJPYのみ採用、ETHはOFF＝従来どおり）
   double entry_th=ma, exit_th=ma;
   if(S[i].useHyst){
      double ab[]; ArraySetAsSeries(ab,true);
      if(CopyBuffer(S[i].hATR,0,1,1,ab)<1) return;
      entry_th=ma+S[i].hystMult*ab[0]; exit_th=ma-S[i].hystMult*ab[0];
   }
   // クールダウン（S9・XM版から移植）: 退出後cdBarsは再entry禁止
   bool cd_ok=true;
   if(S[i].cdBars>0 && S[i].cdExitBar>0)
      cd_ok=(iBarShift(sym,tf,S[i].cdExitBar,false)>=S[i].cdBars);
   trade.SetExpertMagicNumber(S[i].magic);
   if(cp>entry_th && swap_ok && !has && cd_ok){
      trade.Buy(LotComplex(i,sym),sym,SymbolInfoDouble(sym,SYMBOL_ASK),0,0,"Carry");
   } else if(cp<exit_th && has){
      CloseSleeveAll(i);
      S[i].cdExitBar=iTime(sym,tf,0);
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

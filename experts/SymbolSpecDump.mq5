//+------------------------------------------------------------------+
//| SymbolSpecDump.mq5                                               |
//| 銘柄仕様と口座条件を書き出すだけの診断EA（発注しない）            |
//+------------------------------------------------------------------+
// 【なぜ要るか】
// 2026-09-15、OANDA FX の検証で「複利を止めているのは 1注文あたり 50ロットという
// 銘柄上限」と分かった（docs/oanda_fx_cap_curve_deposit_20260915.md）。
// ところが**その 50 という値は XM の端末で測ったもの**である。本番は OANDA証券。
// 天井を決めているパラメータが違うブローカーのものなら、結論ごと動く。
//
// 同じ日に「ini の Leverage=25 が無視されて 1:100 で走っていた」も見つかっている。
// **「そうなっているはず」を測らずに書かない。**
//
// 【使い方】
// 各端末にコピーしてコンパイルし、短いバックテストを1本回す。
// 結果は Common\Files\symbol_specs_<broker>.csv に出る（両端末から同じ場所に出せる）。
//
//   mt5_path を XM / OANDA それぞれに向けた yaml で1日ぶん回すだけでよい。
//   OnInit で書き出して OnTick は何もしないので、期間は最短でよい。

input string OutTag = "unknown";   // 出力ファイル名につけるブローカー名

string SYMS[] = {"USDJPY", "EURUSD", "GBPUSD", "GBPJPY", "AUDJPY", "XAUUSD"};

int OnInit()
{
   string path = StringFormat("symbol_specs_%s.csv", OutTag);
   int fh = FileOpen(path, FILE_WRITE | FILE_CSV | FILE_ANSI | FILE_COMMON, ',');
   if(fh == INVALID_HANDLE)
   {
      Print("FileOpen 失敗: ", path, " err=", GetLastError());
      return INIT_FAILED;
   }

   FileWrite(fh, "broker", OutTag);
   FileWrite(fh, "server", AccountInfoString(ACCOUNT_SERVER));
   FileWrite(fh, "company", AccountInfoString(ACCOUNT_COMPANY));
   FileWrite(fh, "currency", AccountInfoString(ACCOUNT_CURRENCY));
   FileWrite(fh, "account_leverage", (long)AccountInfoInteger(ACCOUNT_LEVERAGE));
   FileWrite(fh, "margin_mode", (long)AccountInfoInteger(ACCOUNT_MARGIN_MODE));
   FileWrite(fh, "balance", AccountInfoDouble(ACCOUNT_BALANCE));
   FileWrite(fh, "");
   FileWrite(fh, "symbol", "vol_min", "vol_max", "vol_step", "contract_size",
             "margin_initial", "margin_maintenance", "margin_1lot_buy",
             "digits", "point", "spread", "trade_mode");

   for(int i = 0; i < ArraySize(SYMS); i++)
   {
      string s = SYMS[i];
      if(!SymbolSelect(s, true))
      {
         FileWrite(fh, s, "NOT_AVAILABLE");
         continue;
      }
      double ask = SymbolInfoDouble(s, SYMBOL_ASK);
      if(ask <= 0.0)
         ask = SymbolInfoDouble(s, SYMBOL_BID);
      double m1 = 0.0;
      // 1ロットの必要証拠金。OrderCalcMargin は口座レバレッジと銘柄設定の両方を見る。
      if(!OrderCalcMargin(ORDER_TYPE_BUY, s, 1.0, ask, m1))
         m1 = -1.0;

      FileWrite(fh, s,
                SymbolInfoDouble(s, SYMBOL_VOLUME_MIN),
                SymbolInfoDouble(s, SYMBOL_VOLUME_MAX),
                SymbolInfoDouble(s, SYMBOL_VOLUME_STEP),
                SymbolInfoDouble(s, SYMBOL_TRADE_CONTRACT_SIZE),
                SymbolInfoDouble(s, SYMBOL_MARGIN_INITIAL),
                SymbolInfoDouble(s, SYMBOL_MARGIN_MAINTENANCE),
                m1,
                (long)SymbolInfoInteger(s, SYMBOL_DIGITS),
                SymbolInfoDouble(s, SYMBOL_POINT),
                (long)SymbolInfoInteger(s, SYMBOL_SPREAD),
                (long)SymbolInfoInteger(s, SYMBOL_TRADE_MODE));
   }
   FileClose(fh);
   Print("SymbolSpecDump -> Common\\Files\\", path);
   return INIT_SUCCEEDED;
}

void OnTick() {}
double OnTester() { return 0.0; }

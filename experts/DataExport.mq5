//+------------------------------------------------------------------+
//|  DataExport.mq5                                                  |
//|  ML学習用データ輸出EA（テスター経由でM1履歴をCSV化）              |
//|  使い方: mt5btでチャート銘柄・期間を指定して実行すると、OnTesterで |
//|  ExportSymbols（カンマ区切り・空=チャート銘柄）の全M1バーを        |
//|  MQL5\Files\m1_<銘柄小文字>[_<ExportTag>].csv に書き出す。         |
//|  取引は一切しない。                                               |
//|  注意:                                                           |
//|   - チャート時間枠はH1推奨（テスト進行が軽い。M1出力はTFに無関係） |
//|   - チャート銘柄以外のヒストリーは「テスト開始の約1年前以降」しか   |
//|     ロードされない（フル期間が必要なら期間を分割して結合する）      |
//|   - チャート銘柄GOLDの単独テストは異常終了する既知問題があるため    |
//|     チャートはUSDJPY等の安定銘柄で実行すること                     |
//+------------------------------------------------------------------+
#property copyright "2026"
#property version   "1.10"
#property strict

input string ExportSymbols  = "";   // カンマ区切りの出力対象銘柄（空=チャート銘柄）
input string ExportTag      = "";
input int    ExportTFMin    = 1;    // 出力時間足（分: 1=M1, 60=H1, 1440=D1）   // 出力ファイル名タグ: m1_<sym>_<tag>.csv
input string ResultFileName = "";   // mt5bt互換（完了検出用のダミー結果も書く）

string symbols[];
ENUM_TIMEFRAMES ExportTF() { return (ExportTFMin >= 1440 ? PERIOD_D1 : (ExportTFMin >= 60 ? PERIOD_H1 : PERIOD_M1)); }
bool   warmed = false;

int OnInit()
{
    string src = (ExportSymbols == "" ? _Symbol : ExportSymbols);
    int cnt = StringSplit(src, ',', symbols);
    for(int s = 0; s < cnt; s++)
    {
        StringTrimLeft(symbols[s]);
        StringTrimRight(symbols[s]);
    }
    return INIT_SUCCEEDED;
}

void OnTick()
{
    // テスト序盤に対象銘柄を一度参照してヒストリー同期をトリガーしておく
    if(!warmed)
    {
        for(int s = 0; s < ArraySize(symbols); s++)
        {
            MqlRates r[];
            CopyRates(symbols[s], ExportTF(), 0, 10, r);
        }
        warmed = true;
    }
}

double OnTester()
{
    long totalExported = 0;
    for(int s = 0; s < ArraySize(symbols); s++)
    {
        string sym = symbols[s];
        MqlRates rates[];
        ArraySetAsSeries(rates, false);
        int total  = Bars(sym, ExportTF());
        int copied = CopyRates(sym, ExportTF(), 0, total, rates);
        string lower = sym;
        StringToLower(lower);
        string fname = (ExportTFMin == 1 ? "m1_" : (ExportTFMin >= 1440 ? "d1_" : "h1_")) + lower + (ExportTag != "" ? "_" + ExportTag : "") + ".csv";
        int digits = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
        Print("DataExport: symbol=", sym, " Bars=", total, " copied=", copied, " -> ", fname);
        int fh = FileOpen(fname, FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
        if(fh != INVALID_HANDLE)
        {
            FileWrite(fh, "time", "open", "high", "low", "close", "tickvol", "spread");
            for(int i = 0; i < copied; i++)
                FileWrite(fh, (long)rates[i].time,
                          DoubleToString(rates[i].open, digits),
                          DoubleToString(rates[i].high, digits),
                          DoubleToString(rates[i].low, digits),
                          DoubleToString(rates[i].close, digits),
                          (long)rates[i].tick_volume,
                          (long)rates[i].spread);
            FileClose(fh);
            totalExported += copied;
        }
    }
    // mt5btの完了検出用ダミー結果
    if(ResultFileName != "")
    {
        int rh = FileOpen(ResultFileName, FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
        if(rh != INVALID_HANDLE)
        {
            FileWrite(rh, "key", "value");
            FileWrite(rh, "net_profit", "0");
            FileWrite(rh, "exported_bars", IntegerToString((int)totalExported));
            FileClose(rh);
        }
    }
    return 0.0;
}
//+------------------------------------------------------------------+

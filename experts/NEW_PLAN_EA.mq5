//+------------------------------------------------------------------+
//|  NEW_PLAN_EA.mq5                                                 |
//|  低相関新戦略のスロット式シェル v1.0（2026.07.07）                 |
//|                                                                  |
//|  ■ 位置づけ                                                      |
//|  既存ブック（MIX_EA）と相関の少ない新収益源を組み込むための器。    |
//|  docs/new_plan_backlog.md の1,020案探索（チャンピオン13実検証+     |
//|  層別クローズ）の結果、**現時点の生存戦略はゼロ**のため、          |
//|  本EAは意図的に「空のシェル」である（取引しない）。                |
//|                                                                  |
//|  ■ 戦略追加の手順（バックログの採用ゲート4条件を通過した戦略のみ）  |
//|   1. ST_* 定数を追加し、SLEEVE構造体に必要フィールドを足す         |
//|   2. AddSleeve()で枠登録（Magic 20263000番台・既存と重複禁止）      |
//|   3. Proc<Strategy>()を実装し OnTick のディスパッチに追加           |
//|   4. every_tick検証→既存dealログとの月次相関<+0.3を確認→採用       |
//|                                                                  |
//|  ■ 採用ゲート（docs/new_plan_backlog.md）                         |
//|   ①IS/OOS両プラス ②パラメタプラトー ③既存ブックと相関<+0.3        |
//|   ④ブック合算のリターン/DD効率が改善                              |
//+------------------------------------------------------------------+
#property copyright "2026"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>

input group "=== マスター ==="
input bool   MasterEnable  = true;
input double GlobalLotMult = 1.0;

input group "=== 運用ログ（フォワード分析用） ==="
input bool   EnableOpsLog = false;
input string OpsLogPrefix = "newplan";

//--- 戦略種別（採用戦略が現れたらここに追加）
enum STRATEGY_TYPE
{
    ST_NONE = 0
    // ST_XXX = 1, ...  ← 採用ゲート通過後に追加
};

struct SLEEVE
{
    STRATEGY_TYPE type;
    string        symbol;
    ENUM_TIMEFRAMES tf;
    long          magic;
    double        lots;
    bool          enabled;
    datetime      lastBar;
};

SLEEVE S[16];
int    NS = 0;
CTrade trade;

//+------------------------------------------------------------------+
void AddSleeve(STRATEGY_TYPE t, string sym, ENUM_TIMEFRAMES tf, long magic,
               double lots, bool en)
{
    if(NS >= 16) return;
    S[NS].type = t;
    S[NS].symbol = sym;
    S[NS].tf = tf;
    S[NS].magic = magic;
    S[NS].lots = lots;
    S[NS].enabled = en;
    S[NS].lastBar = 0;
    if(en) SymbolSelect(sym, true);
    NS++;
}

//+------------------------------------------------------------------+
int OnInit()
{
    NS = 0;
    // ---- 枠登録（現在ゼロ: 1,020案探索で生存戦略なし＝docs/new_plan_backlog.md）----
    // 例: AddSleeve(ST_XXX, "USDJPY", PERIOD_H4, 20263000, 0.01, En_XXX);

    int active = 0;
    for(int i = 0; i < NS; i++) if(S[i].enabled) active++;
    Print("NEW_PLAN_EA v1.0 起動 | 登録枠=", NS, " 有効枠=", active,
          NS == 0 ? "（探索完了・生存戦略ゼロ＝待機シェル。取引しません）" : "");
    return INIT_SUCCEEDED;
}

void OnDeinit(const int reason) {}

//+------------------------------------------------------------------+
void OnTick()
{
    if(!MasterEnable || NS == 0) return;
    for(int i = 0; i < NS; i++)
    {
        if(!S[i].enabled) continue;
        datetime bt = iTime(S[i].symbol, S[i].tf, 0);
        if(bt == 0 || bt == S[i].lastBar) continue;
        S[i].lastBar = bt;
        switch(S[i].type)
        {
            // case ST_XXX: ProcXXX(i); break;   ← 採用戦略のディスパッチ
            default: break;
        }
    }
}
//+------------------------------------------------------------------+

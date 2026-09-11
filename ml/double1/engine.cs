// 外部パッケージを導入せず、Windows標準ランタイムで感度全組合せを計算するための補助実装。
// 金融上の仮定・制限はsimulate.pyと共通であり、MT5や測定プログラムには接続しない。
using System;
using System.Collections.Generic;
using System.Globalization;

class Engine {
    static uint Next(ref uint x) {
        x ^= x << 13; x ^= x >> 17; x ^= x << 5; return x;
    }
    static int Draw(ref uint x, int n) {
        uint limit = uint.MaxValue - uint.MaxValue % (uint)n;
        uint v;
        do { v = Next(ref x); } while (v > limit);
        return (int)((v - 1) % (uint)n);
    }
    static string Median(List<double> a) {
        if (a.Count == 0) return "";
        a.Sort(); int m = a.Count / 2;
        return (a.Count % 2 == 1 ? a[m] : (a[m-1] + a[m]) / 2).ToString("R", CultureInfo.InvariantCulture);
    }
    static void Main() {
        CultureInfo.CurrentCulture = CultureInfo.InvariantCulture;
        string[] a = Console.ReadLine().Split(',');
        double k = double.Parse(a[0]), initial = double.Parse(a[1]), ruin = double.Parse(a[2]);
        int length = int.Parse(a[3]), paths = int.Parse(a[5]);
        uint seed = unchecked((uint)long.Parse(a[6]));
        double[] profits = Array.ConvertAll(Console.ReadLine().Split(','), double.Parse);
        int steps = (int)Math.Floor(profits.Length * double.Parse(a[4]));
        int n = profits.Length - length + 1;
        double[][] blocks = new double[n][];
        double[] low = new double[n], high = new double[n];
        for (int s = 0; s < n; s++) {
            List<double> v = new List<double>(); double e = 1;
            low[s] = double.PositiveInfinity; high[s] = double.NegativeInfinity;
            for (int j = 0; j < length; j++) {
                e *= 1 + profits[s+j] * k / initial; v.Add(e);
                low[s] = Math.Min(low[s], e); high[s] = Math.Max(high[s], e);
                // 非正資産に到達したら必ず破綻するため、その後の符号反転は作らない。
                if (e <= 0) break;
            }
            blocks[s] = v.ToArray();
        }
        List<double> wins = new List<double>(), losses = new List<double>(), times = new List<double>();
        for (int path = 0; path < paths; path++) {
            uint state = unchecked(seed + (uint)(path + 1) * 2654435769U);
            if (state == 0) state = 1;
            double equity = 1; int used = 0;
            while (used < steps) {
                int s = Draw(ref state, n), take = Math.Min(length, steps - used);
                double[] v = blocks[s];
                // 内部極値でも閾値に触れないブロックだけを省略し、初回到達を保存する。
                if (take == length && equity * low[s] > ruin && equity * high[s] < 2) {
                    equity *= v[v.Length - 1]; used += length; continue;
                }
                double before = equity;
                for (int j = 0; j < Math.Min(take, v.Length); j++) {
                    equity = before * v[j]; used++;
                    if (equity >= 2 || equity <= ruin) break;
                }
                if (equity >= 2 || equity <= ruin) break;
            }
            if (equity >= 2) { wins.Add(equity * initial); times.Add(used); }
            else if (equity <= ruin) losses.Add(equity * initial);
        }
        Console.WriteLine(string.Join(",", new string[] {
            wins.Count.ToString(), losses.Count.ToString(), (paths - wins.Count - losses.Count).ToString(),
            steps.ToString(), Median(times), Median(wins), Median(losses)}));
    }
}

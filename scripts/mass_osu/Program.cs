using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text;
using Newtonsoft.Json;
using PerformanceCalculator;
using osu.Framework.Logging;
using osu.Game.Beatmaps;
using osu.Game.Beatmaps.Formats;
using osu.Game.Rulesets;
using osu.Game.Rulesets.Mods;
using osu.Game.Rulesets.Osu;
using osu.Game.Rulesets.Osu.Difficulty;
using osu.Game.Rulesets.Osu.Objects;
using osu.Game.Rulesets.Scoring;
using osu.Game.Scoring;

// One persistent process avoids starting .NET for every map/mod combination.
Console.InputEncoding = new UTF8Encoding(false);
Console.OutputEncoding = new UTF8Encoding(false);
Logger.Enabled = false;
LegacyDifficultyCalculatorBeatmapDecoder.Register();
var ruleset = new OsuRuleset();
string? line;
while ((line = Console.ReadLine()) != null)
{
    try
    {
        var input = line.Split('\t');
        string path = input[0];
        uint bits = uint.Parse(input[1]);
        bool classic = input[2] == "1";
        var acronyms = new List<string>();
        foreach (var (bit, acronym) in new (uint, string)[] { (2, "EZ"), (8, "HD"), (16, "HR"), (64, "DT"), (256, "HT"), (1024, "FL") })
            if ((bits & bit) != 0) acronyms.Add(acronym);
        if (classic) acronyms.Add("CL");
        var mods = ProcessorCommand.ParseMods(ruleset, acronyms.ToArray(), []);
        var working = new SingleCalculationWorkingBeatmap(path);
        // Large edited maps can exceed the UI-oriented 10-second loading timeout.
        using var cancellation = new System.Threading.CancellationTokenSource();
        var map = working.GetPlayableBeatmap(ruleset.RulesetInfo, mods, cancellation.Token);
        var difficulty = (OsuDifficultyAttributes)ruleset.CreateDifficultyCalculator(working).Calculate(mods, cancellation.Token);
        int count = map.HitObjects.Count;
        int sliders = map.HitObjects.Count(x => x is Slider);
        int ticks = map.HitObjects.Sum(x => x.NestedHitObjects.Count(n => n is SliderTick or SliderRepeat));
        var cases = new List<object>();
        foreach (bool imperfect in new[] { false, true })
        {
            int good = imperfect ? Math.Min(count / 3, Math.Max(1, count / 25)) : 0;
            int meh = imperfect ? Math.Min(count / 3, Math.Max(1, count / 50)) : 0;
            int miss = imperfect ? Math.Min(count - good - meh, Math.Max(1, count / 50)) : 0;
            int great = count - good - meh - miss;
            int tailMiss = imperfect && sliders > 0 ? Math.Max(1, sliders / 25) : 0;
            int tickMiss = imperfect && ticks > 0 ? Math.Max(1, ticks / 25) : 0;
            int combo = imperfect ? (map.GetMaxCombo() - miss) / 2 : map.GetMaxCombo();
            var statistics = new Dictionary<HitResult, int> { [HitResult.Great] = great, [HitResult.Ok] = good, [HitResult.Meh] = meh, [HitResult.Miss] = miss };
            double total = 6 * great + 2 * good + meh;
            double maximum = 6 * count;
            if (!classic)
            {
                statistics[HitResult.SliderTailHit] = sliders - tailMiss;
                statistics[HitResult.LargeTickMiss] = tickMiss;
                total += 3 * (sliders - tailMiss);
                maximum += 3 * sliders;
                total += 0.6 * (ticks - tickMiss);
                maximum += 0.6 * ticks;
            }
            var score = new ScoreInfo(map.BeatmapInfo, ruleset.RulesetInfo) { Mods = mods, Statistics = statistics, Accuracy = total / maximum, MaxCombo = combo };
            // Empty-map pp is undefined upstream; FL additionally triggers a debug assertion.
            var performance = count == 0 ? new Dictionary<string, string?>()
                : NumericBits(ruleset.CreatePerformanceCalculator()!.Calculate(score, difficulty)!);
            cases.Add(new { state = new[] { great, good, meh, miss, combo, sliders - tailMiss, ticks - tickMiss }, performance });
        }
        var diff = NumericBits(difficulty);
        diff["n_large_ticks"] = BitConverter.DoubleToUInt64Bits(ticks).ToString("x16");
        Console.WriteLine(JsonConvert.SerializeObject(new { difficulty = diff, cases }));
    }
    catch (Exception e)
    {
        Console.WriteLine(JsonConvert.SerializeObject(new { error = e.ToString() }));
    }
}

static Dictionary<string, string?> NumericBits(object attributes)
{
    var result = new Dictionary<string, string?>();
    foreach (var property in attributes.GetType().GetProperties())
    {
        var json = property.GetCustomAttribute<JsonPropertyAttribute>();
        string name = json?.PropertyName ?? property.Name;
        object? value = property.GetValue(attributes);
        if (property.PropertyType == typeof(double) || property.PropertyType == typeof(int) || property.PropertyType == typeof(double?))
            result[name] = value == null ? null : BitConverter.DoubleToUInt64Bits(Convert.ToDouble(value)).ToString("x16");
    }
    return result;
}

// Every instance serves one map/mod request. Both callers use identical mods,
// so reuse the fully processed beatmap instead of allocating its nested objects twice.
sealed class SingleCalculationWorkingBeatmap(string path) : ProcessorWorkingBeatmap(path)
{
    private IBeatmap? playable;

    public override IBeatmap GetPlayableBeatmap(IRulesetInfo ruleset, IReadOnlyList<Mod> mods, System.Threading.CancellationToken token)
        => playable ??= base.GetPlayableBeatmap(ruleset, mods, token);
}

# osu!standard parity

Standard difficulty and performance were compared with `ppy/osu` master at
`adfbb1ca25f7836f0f3577faac334469e6e9e8ae` (2026-10-09). The C# difficulty
calculator reports version `20260706`. The reference CLI is `ppy/osu-tools` at
`8ce45b33c61e977b577fa1579c169371ed7b6c76` (2026-09-12), built against the pinned
osu! source, rather than its older NuGet ruleset packages.

The `pp-update` branch already contained the 2026 Q2 aim, speed, reading, and
flashlight rework. This update brings its remaining calculations into line with
the pinned source:

- Aim and speed note counts use the shared logistic function, with the same
  floating-point operation order as C#.
- The final variable-length aim section is included without another stored-length
  eviction. Rust evaluates a copy of the peak list, so repeated and gradual
  calculations do not need C#'s mutable final-peak bookkeeping.
- Hidden sliders retain their default fade-in duration when calculating opacity.
- A zero legacy score uses combo-based miss estimation. Positive legacy scores
  still use the score-based calculator, except with ScoreV2.
- Reading pp accounts for estimated aim slider breaks on classic plays.
- ScoreV2 accuracy pp counts slider heads even with classic slider accuracy.
- Relax's 100-judgment miss multiplier is 0.75 at OD <= 0.
- Empty difficulty calculations return zero skill and legacy-score attributes.

The Rust flashlight attribute continues to use `0.0` when Flashlight is absent.
C# now represents that absence with a nullable attribute; this does not change
the numerical calculations. Zero-judgment performance keeps Rust's existing
zero result, while the C# calculator currently produces NaN for empty maps.

## Reference coverage

All numerical comparisons use `to_bits()` equality:

- 18 maps x 7 fixed mod combinations for Standard difficulty and full-combo SS pp.
- The same 126 combinations for non-full-combo lazer scores, with exact judgment,
  tick, slider-tail, and combo counts.
- 10 additional difficulty cases and 9 non-empty performance cases covering
  classic scores, absent/zero/positive legacy totals, Flashlight, ScoreV2, OD0
  Relax, short maps with low difficult-note counts, and all misses.
- The empty-map performance case checks Rust's zero-result behavior separately.

The existing Mania, Catch, Taiko, decoding, unit, and gradual tests remain part
of the regression suite. Their algorithms and reference snapshots were not
updated in this Standard pass.

Validation on Windows: all 217 tests pass with `cargo nextest run --all-features`.
All Standard gates also pass with `--release`. The full release suite has two
existing Mania failures on `resources/1002277.osu`: star rating differs by one
bit increment, and difficulty pp differs by four. Both were reproduced from the
unmodified `pp-update` base. The Mania reference values were kept unchanged.

## Building the reference calculator

Use dedicated upstream checkouts if `../osu` or `../osu-tools` already contain
other work. Check out the exact revisions above before building. Change
`PerformanceCalculator/PerformanceCalculator.csproj` to replace all five
`ppy.osu.Game*` package references with project references to the local
`osu.Game`, `osu.Game.Rulesets.Osu`, `osu.Game.Rulesets.Taiko`,
`osu.Game.Rulesets.Catch`, and `osu.Game.Rulesets.Mania` projects. The upstream
`UseLocalOsu.ps1` script performs this conversion when the checkouts have their
usual `osu` and `osu-tools` sibling names.

This osu-tools revision also needs `using osu.Game.Scoring;` in
`PerformanceCalculator/Leaderboard/LeaderboardCommand.cs` and
`PerformanceCalculator/Profile/ProfileCommand.cs` because `APIMod.ToMod` moved
to an extension method in the newer osu! source. These are CLI build adaptations;
the C# calculator algorithms must remain unmodified.

For the separate checkouts used for this update:

```powershell
dotnet build ../osu-tools-upstream/PerformanceCalculator/PerformanceCalculator.csproj -p:RunAnalyzers=false -p:NuGetAudit=false

$env:OSU_TOOLS_DIR = (Resolve-Path ../osu-tools-upstream).Path
$env:OSU_SOURCE_DIR = (Resolve-Path ../osu-upstream).Path

python scripts/gen_ext_refs.py osu scripts/manifest.txt tests/data/ext_refs.rs
python scripts/gen_ext_acc_refs.py scripts/manifest.txt tests/data/ext_acc_refs.rs
python scripts/gen_ext_edge_refs.py tests/data/ext_edge_refs.rs

cargo nextest run --all-features
cargo test --doc --all-features
```

The environment variables select the checkout paths and record their Git
revisions in the generated files. Without them, the scripts use the conventional
`../osu` and `../osu-tools` locations. They do not rebuild the CLI. Verify its
source references and inspect a representative CLI result before regenerating
snapshots. Generators run rustfmt and write LF line endings.

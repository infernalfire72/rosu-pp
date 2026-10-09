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

## Generated references

All six generated Rust snapshots in `tests/data/` are local, ignored files.
Git retains the generators, manifests, and beatmap inputs. A clean checkout
builds and runs the ordinary tests without requiring C# tooling. The build
script detects each available snapshot and enables its corresponding parity
gates. Missing gates remain visible as ignored tests with generation
instructions; a build warning lists missing snapshots. Explicitly running an
ignored gate without its snapshot fails with those instructions.

Generate snapshots with the commands below after building and verifying the
reference CLI. The mass snapshot has its own generation command in the mass
validation section. Cargo detects snapshot creation, changes, and removal
automatically, including when running with `--all-features`. The full bit-exact
suite requires all six local snapshots; a clean checkout alone does not verify
C# parity.

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

Validation on Windows: all 219 tests pass with `cargo nextest run --all-features`.
All 76 Standard and decoding tests selected with
`--release -E 'test(osu) | binary(decode)'` also pass. All 15 executable
documentation tests pass. The full release suite passes 217 of 219 tests,
with two
existing Mania failures on `resources/1002277.osu`: star rating differs by one
bit increment, and difficulty pp differs by four. Both were reproduced from the
unmodified `pp-update` base. The Mania reference values were kept unchanged.

## Mass validation

The read-only scan of `F:\backup3\AppData\osu\Songs` found 17,123 `.osu`
files. Twenty zero-byte files cannot be decoded by C# and were excluded.
The remaining 15,601 Standard files contain 15,407 distinct maps. The mass
runner attempts every Standard file with these 16 mod combinations:

NM, EZ, HR, DT, HT, HD, FL, HD+EZ, HD+FL, HD+DT, HR+DT, HD+HR+DT, EZ+DT,
EZ+FL, HR+FL, DT+FL.

Each combination is tested with lazer and classic scoring, both full-combo SS and
an imperfect score with misses, 100s, 50s, reduced combo, and dropped slider
ends/ticks. The score states come from the C# worker. Every numeric difficulty
and performance attribute is compared as raw IEEE-754 bits. Nullable absent
Flashlight difficulty is normalised to Rust's zero; other nullable fields are
compared directly. Empty-map difficulty and Rust's zero pp are checked, but
undefined C# empty-map pp is excluded.

The completed comparisons cover **15,598 files**, **499,136 map/mod/scoring
combinations**, and **22,449,152 numeric field checks**, with **zero numerical
mismatches**. Seventeen valid maps have no judgments; their 1,088 performance
cases check Rust's zero pp rather than undefined upstream pp.

Three extreme maps remain **unverified** because C# could not complete the
reference calculation within its loading limits:

- Culprate - Yin (sometimes) [test3]
- Camellia - M1LLI0N PP (sometimes) [1E23pp]
- Frums (unknown "lambda") - 19ZZ (osu!team) [Aspire]

Longer attempts with both Debug and Release C# builds consumed several
GB of memory without producing references. These 96 combinations remain
reported as reference failures; they are not counted as matching. The mass
runner therefore returns a failure status on this full library until those
references can be obtained. All numerical mismatches from completed
comparisons have been fixed.

Mass testing found and fixed:

- Stack threshold multiplication at float precision and integral time comparisons.
- Spinner position and stack offsets.
- Clamping hitobject coordinates to the official bounds; preserving fractional
  head and control-point coordinates in format version 128 and later.
- Resetting repeats on zero-length slider paths during decoding.
- Float subtraction in the snap aim overlap bonus.
- Equal strain peak insertion order, matching `List<T>.BinarySearch`.
- Fused interpolation rounding used by .NET 10 on FMA-capable hardware.
- Flashlight power rounding, preventing LLVM from substituting a square root.

Eleven maps in `tests/data/mass_osu/` retain these failures as permanent
regressions. Their new snapshots cover 352 map/mod/scoring combinations and
704 performance states. Existing seven-mod snapshots are unchanged. Shared
decoding fixes also run through the other modes' existing regression gates.

Run the mass comparison after building the pinned source-based CLI:

```powershell
python scripts/mass_osu.py "F:\backup3\AppData\osu\Songs" --tools ../osu-tools-upstream --classic
```

The runner builds persistent C# and Rust workers, writes resumable references
and reports under `target/`, and exits unsuccessfully on any mismatch or
calculator error. `--reference-timeout N` bounds each C# response to N seconds
(default 120); a timeout is an explicit reference failure. `--limit N` selects a deterministic content-hash sample;
`--debug` checks an unoptimised Rust build. `--classic` adds classic scoring to
the default lazer cases. Comparisons use the current machine's .NET and Rust
math implementations; the library run was performed on Windows.

After confirming representative results against the official `simulate osu`
CLI, regenerate only the new regression snapshot with:

```powershell
python scripts/gen_mass_osu_refs.py target/mass-osu/bin/Debug/net10.0/MassOsu.dll
```

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
python scripts/gen_ext_refs.py mania scripts/manifest_mania.txt tests/data/ext_refs_mania.rs
python scripts/gen_ext_refs.py catch scripts/manifest_catch.txt tests/data/ext_refs_catch.rs

cargo nextest run --all-features
cargo test --doc --all-features
```

The environment variables select the checkout paths and record their Git
revisions in the generated files. Without them, the scripts use the conventional
`../osu` and `../osu-tools` locations. They do not rebuild the CLI. Verify its
source references and inspect a representative CLI result before regenerating
snapshots. Generators run rustfmt and write LF line endings.

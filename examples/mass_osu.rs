//! Line-based worker for scripts/mass_osu.py. Output uses raw IEEE-754 bits.
use std::io::{self, BufRead, Write};

use rosu_pp::{Beatmap, Difficulty, osu::Osu};

fn main() {
    let stdout = io::stdout();
    let mut out = io::BufWriter::new(stdout.lock());
    for line in io::stdin().lock().lines() {
        let line = line.unwrap();
        let parts: Vec<_> = line.split('\t').collect();
        let result = std::panic::catch_unwind(|| calculate(&parts));
        match result {
            Ok(Ok(json)) => writeln!(out, "{json}").unwrap(),
            Ok(Err(_)) | Err(_) => {
                writeln!(out, "{{\"error\":\"Rust calculation failed\"}}").unwrap()
            }
        }
        out.flush().unwrap();
    }
}

fn calculate(parts: &[&str]) -> Result<String, Box<dyn std::error::Error>> {
    let map = Beatmap::from_path(parts[0])?;
    let mods: u32 = parts[1].parse()?;
    let lazer = parts[2] == "0";
    let a = Difficulty::new()
        .mods(mods)
        .lazer(lazer)
        .calculate_for_mode::<Osu>(&map)?;
    let mut difficulty = Vec::new();
    macro_rules! diff {
        ($($name:literal => $value:expr),* $(,)?) => { $(difficulty.push(format!("\"{}\":\"{:016x}\"", $name, ($value as f64).to_bits()));)* };
    }
    diff! {
        "star_rating" => a.stars, "max_combo" => a.max_combo,
        "aim_difficulty" => a.aim, "aim_difficult_slider_count" => a.aim_difficult_slider_count,
        "speed_difficulty" => a.speed, "speed_note_count" => a.speed_note_count,
        "flashlight_difficulty" => a.flashlight, "reading_difficulty" => a.reading,
        "slider_factor" => a.slider_factor, "aim_top_weighted_slider_factor" => a.aim_top_weighted_slider_factor,
        "speed_top_weighted_slider_factor" => a.speed_top_weighted_slider_factor,
        "aim_difficult_strain_count" => a.aim_difficult_strain_count,
        "speed_difficult_strain_count" => a.speed_difficult_strain_count,
        "reading_difficult_note_count" => a.reading_difficult_note_count,
        "nested_score_per_object" => a.nested_score_per_object,
        "legacy_score_base_multiplier" => a.legacy_score_base_multiplier,
        "maximum_legacy_combo_score" => a.maximum_legacy_combo_score,
        "HitCircleCount" => a.n_circles, "SliderCount" => a.n_sliders,
        "SpinnerCount" => a.n_spinners, "n_large_ticks" => a.n_large_ticks,
    }
    let mut cases = Vec::new();
    for state in &parts[3..] {
        let s: Vec<u32> = state.split(',').map(str::parse).collect::<Result<_, _>>()?;
        let p = a
            .clone()
            .performance()
            .mods(mods)
            .lazer(lazer)
            .n300(s[0])
            .n100(s[1])
            .n50(s[2])
            .misses(s[3])
            .combo(s[4])
            .slider_end_hits(s[5])
            .large_tick_hits(s[6])
            .calculate()?;
        let mut performance = Vec::new();
        macro_rules! perf {
            ($($name:literal => $value:expr),* $(,)?) => { $(performance.push(format!("\"{}\":\"{:016x}\"", $name, ($value).to_bits()));)* };
        }
        perf! {
            "pp" => p.pp, "aim" => p.pp_aim, "speed" => p.pp_speed,
            "accuracy" => p.pp_acc, "flashlight" => p.pp_flashlight, "reading" => p.pp_reading,
            "effective_miss_count" => p.effective_miss_count,
            "combo_based_estimated_miss_count" => p.combo_based_estimated_miss_count,
            "aim_estimated_slider_breaks" => p.aim_estimated_slider_breaks,
            "speed_estimated_slider_breaks" => p.speed_estimated_slider_breaks,
        }
        for (name, value) in [
            ("speed_deviation", p.speed_deviation),
            (
                "score_based_estimated_miss_count",
                p.score_based_estimated_miss_count,
            ),
        ] {
            performance.push(format!(
                "\"{name}\":{}",
                value.map_or_else(
                    || "null".to_owned(),
                    |v| format!("\"{:016x}\"", v.to_bits())
                )
            ));
        }
        cases.push(format!("{{\"performance\":{{{}}}}}", performance.join(",")));
    }
    Ok(format!(
        "{{\"difficulty\":{{{}}},\"cases\":[{}]}}",
        difficulty.join(","),
        cases.join(",")
    ))
}

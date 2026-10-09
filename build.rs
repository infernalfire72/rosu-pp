use std::{env, path::PathBuf};

fn main() {
    let root = PathBuf::from(env::var_os("CARGO_MANIFEST_DIR").unwrap());
    let references = [
        ("has_ext_osu_refs", "ext_refs.rs"),
        ("has_ext_acc_osu_refs", "ext_acc_refs.rs"),
        ("has_ext_edge_osu_refs", "ext_edge_refs.rs"),
        ("has_ext_mania_refs", "ext_refs_mania.rs"),
        ("has_ext_catch_refs", "ext_refs_catch.rs"),
        ("has_mass_osu_refs", "mass_osu_refs.rs"),
    ];
    let mut missing = Vec::new();

    // Watching the directory also detects creation of previously absent snapshots.
    println!("cargo:rerun-if-changed=tests/data");

    for (cfg, name) in references {
        println!("cargo:rustc-check-cfg=cfg({cfg})");
        let relative = format!("tests/data/{name}");

        if root.join(&relative).is_file() {
            println!("cargo:rerun-if-changed={relative}");
            println!("cargo:rustc-cfg={cfg}");
        } else {
            missing.push(name);
        }
    }

    if !missing.is_empty() {
        println!(
            "cargo:warning=Missing generated C# references ({}); corresponding parity tests are ignored. See docs/standard-parity.md to generate them.",
            missing.join(", ")
        );
    }
}

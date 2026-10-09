"""Compare a recursive Standard beatmap library with source-built osu-tools.

Run: python scripts/mass_osu.py SONGS --tools ../osu-tools-upstream
Build osu-tools against the desired osu! source revision first (see
docs/standard-parity.md). Reports and resumable C# caches stay under target/.
No beatmaps are modified. Comparisons use IEEE-754 bits, with no tolerance.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import gzip
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
MODS = [0, 2, 16, 64, 256, 8, 1024, 10, 1032, 72, 80, 88, 66, 1026, 1040, 1088]


def worker(command, timeout=120):
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, text=True, encoding="utf-8", bufsize=1)
    process.response_queue = queue.Queue()
    process.response_timeout = timeout

    def read_responses():
        try:
            for output in process.stdout:
                if output.startswith("{"):
                    process.response_queue.put(json.loads(output))
            process.response_queue.put({"error": f"Worker exited: {process.wait()}"})
        except (OSError, ValueError) as error:
            process.response_queue.put({"error": f"Invalid worker response: {error}"})

    threading.Thread(target=read_responses, daemon=True).start()
    return process


def query(process, line):
    try:
        process.stdin.write(line + "\n")
        process.stdin.flush()
    except (OSError, BrokenPipeError):
        return {"error": f"Worker pipe failed (exit {process.poll()})"}
    try:
        return process.response_queue.get(timeout=process.response_timeout)
    except queue.Empty:
        process.kill()
        process.wait(timeout=10)
        return {"error": f"Worker exceeded {process.response_timeout}s response timeout"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("songs", type=Path)
    parser.add_argument("--tools", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=0, help="0 tests every Standard map")
    parser.add_argument("--manifest", type=Path, help="JSON list of paths, instead of rescanning")
    parser.add_argument("--classic", action="store_true", help="Also test classic scoring")
    parser.add_argument("--debug", action="store_true", help="Use unoptimised Rust worker")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--no-build", action="store_true")
    parser.add_argument("--rust-worker", type=Path)
    parser.add_argument("--reference-worker", type=Path)
    parser.add_argument("--reference-timeout", type=float, default=120, help="Seconds per C# response; timeout is reported as a reference failure")
    parser.add_argument("--reference-cache", type=Path, help="Reuse a cache with identical official calculator assemblies and score protocol")
    parser.add_argument("--report", type=Path, default=ROOT / "target/mass-osu-report.jsonl")
    args = parser.parse_args()
    if args.jobs < 1 or args.limit < 0 or args.reference_timeout <= 0:
        parser.error("--jobs and --reference-timeout must be positive and --limit cannot be negative")
    target = ROOT / "target/mass-osu"
    target.mkdir(parents=True, exist_ok=True)
    tools_project = args.tools.resolve() / "PerformanceCalculator/PerformanceCalculator.csproj"
    # The worker references the same source-built calculator as the official CLI.
    project = target / "MassOsu.csproj"
    from xml.sax.saxutils import escape
    project.write_text(f'''<Project Sdk="Microsoft.NET.Sdk">
<PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><Nullable>enable</Nullable><EnableDefaultCompileItems>false</EnableDefaultCompileItems></PropertyGroup>
<ItemGroup><ProjectReference Include="{escape(str(tools_project))}" /><Compile Include="{escape(str(ROOT / 'scripts/mass_osu/Program.cs'))}" /></ItemGroup>
</Project>
''', encoding="utf-8", newline="\n")
    if not args.no_build:
        subprocess.run(["dotnet", "build", str(project), "-v", "quiet", "-p:RunAnalyzers=false", "-p:NuGetAudit=false"], check=True)
    command = ["cargo", "build", "--example", "mass_osu"]
    if not args.debug:
        command.append("--release")
    if not args.no_build:
        subprocess.run(command, cwd=ROOT, check=True)
    assembly = args.reference_worker or target / "bin/Debug/net10.0/MassOsu.dll"
    # Hash the actual reference assemblies; invalidate caches when source/build changes.
    fingerprint = hashlib.sha256()
    fingerprint.update(assembly.read_bytes())
    for name in ["PerformanceCalculator.dll", "osu.Game.dll", "osu.Game.Rulesets.Osu.dll", "osu.Framework.dll"]:
        fingerprint.update((assembly.parent / name).read_bytes())
    calculator_hash = hashlib.sha256(b"mass-osu-score-protocol-1")
    for name in ["PerformanceCalculator.dll", "osu.Game.dll", "osu.Game.Rulesets.Osu.dll", "osu.Framework.dll"]:
        calculator_hash.update((assembly.parent / name).read_bytes())
    cache = args.reference_cache or target / fingerprint.hexdigest()[:16]
    cache.mkdir(exist_ok=True)
    metadata_path = cache / "metadata.json"
    metadata = {"calculator_hash": calculator_hash.hexdigest(), "score_protocol": 1}
    if args.reference_cache:
        if not metadata_path.exists() or json.loads(metadata_path.read_text()) != metadata:
            raise RuntimeError("Reference cache calculator assemblies or score protocol do not match")
    else:
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    if args.manifest:
        paths = [Path(p) for p in json.loads(args.manifest.read_text(encoding="utf-8"))]
    else:
        paths = [Path(d) / f for d, _, files in os.walk(args.songs) for f in files if f.lower().endswith(".osu")]
    inventory_file = target / (hashlib.sha256("\n".join(map(str, paths)).encode()).hexdigest()[:16] + "-inventory.json")
    inventory = json.loads(inventory_file.read_text(encoding="utf-8")) if inventory_file.exists() else {}
    standard = []
    empty_files = []
    for index, path in enumerate(paths):
        try:
            stat = path.stat()
            entry = inventory.get(str(path))
            if stat.st_size == 0:
                entry = [0, stat.st_mtime_ns, "empty-file", hashlib.sha256(b"").hexdigest()]
                inventory[str(path)] = entry
            elif entry is None or entry[0:2] != [stat.st_size, stat.st_mtime_ns]:
                data = path.read_bytes()
                header = data.split(b"[HitObjects]", 1)[0].decode("utf-8-sig", errors="replace")
                mode = next((line.split(":", 1)[1].strip() for line in header.splitlines() if line.strip().startswith("Mode:")), "0")
                entry = [stat.st_size, stat.st_mtime_ns, mode, hashlib.sha256(data).hexdigest()]
                inventory[str(path)] = entry
            mode = entry[2]
            if mode == "empty-file":
                empty_files.append(str(path))
            elif mode == "0":
                standard.append((entry[3], path))
        except OSError as e:
            print(f"Cannot read {ascii(str(path))}: {e}", flush=True)
        if (index + 1) % 500 == 0:
            inventory_file.write_text(json.dumps(inventory, ensure_ascii=False), encoding="utf-8")
            print(f"Scanned {index + 1}/{len(paths)} files", flush=True)
    inventory_file.write_text(json.dumps(inventory, ensure_ascii=False), encoding="utf-8")
    # Hash order gives a reproducible sample spanning the whole library.
    standard.sort(key=lambda item: (item[0], str(item[1])))
    if args.limit:
        standard = standard[:args.limit]
    print(f"Selected {len(standard)} Standard maps from {len(paths)} files; {len(MODS)} mods; classic={args.classic}", flush=True)
    local = threading.local()
    processes = []
    rust_worker = args.rust_worker or ROOT / "target" / ("debug" if args.debug else "release") / "examples" / ("mass_osu.exe" if os.name == "nt" else "mass_osu")

    def compare_map(item):
        if not hasattr(local, "cs"):
            local.cs = worker(["dotnet", str(assembly)], args.reference_timeout)
            local.rs = worker([str(rust_worker)])
            processes.extend([local.cs, local.rs])
            local.maps = 0
        if local.maps >= 50 or local.cs.poll() is not None:
            if local.cs.poll() is None:
                local.cs.stdin.close()
                local.cs.wait(timeout=30)
            local.cs = worker(["dotnet", str(assembly)], args.reference_timeout)
            processes.append(local.cs)
            local.maps = 0
        local.maps += 1
        digest, path = item
        cs, rs = local.cs, local.rs
        counts = Counter()
        failures = []
        packed = cache / f"{digest}.json.gz"
        references = json.loads(gzip.decompress(packed.read_bytes())) if packed.exists() else {}
        changed = False
        for classic in ([False, True] if args.classic else [False]):
            for mods in MODS:
                request = f"{path}\t{mods}\t{int(classic)}"
                key = f"{mods}-{int(classic)}"
                cached = cache / f"{digest}-{key}.json"
                if key in references:
                    reference = references[key]
                elif cached.exists():
                    reference = json.loads(cached.read_text(encoding="utf-8"))
                    references[key] = reference
                    changed = True
                else:
                    reference = query(cs, request)
                    if "error" not in reference:
                        references[key] = reference
                        changed = True
                counts["combinations"] += 1
                differences = []
                if "error" in reference:
                    differences.append({"reference_error": reference["error"]})
                    counts["reference_errors"] += 1
                else:
                    states = [",".join(map(str, case["state"])) for case in reference["cases"]]
                    actual = query(rs, request + "\t" + "\t".join(states))
                    if "error" in actual:
                        differences.append({"rust_error": actual["error"]})
                    else:
                        groups = [("difficulty", reference["difficulty"], actual["difficulty"])]
                        groups += [(f"performance_{i}", c["performance"], a["performance"]) for i, (c, a) in enumerate(zip(reference["cases"], actual["cases"]))]
                        for group, expected, result in groups:
                            # Documented upstream NaN on zero-judgment performance.
                            if group.startswith("performance") and sum(reference["cases"][0]["state"][:4]) == 0:
                                counts["empty_performance_cases"] += 1
                                counts["fields"] += 1
                                if result["pp"] != "0000000000000000":
                                    differences.append({"group": group, "field": "pp", "expected_empty_pp": "0000000000000000", "rs": result["pp"]})
                                continue
                            for field, value in expected.items():
                                if field not in result:
                                    raise RuntimeError(f"Unmapped C# numeric field: {group}/{field}")
                                if field == "flashlight_difficulty" and value is None:
                                    value = "0000000000000000"
                                counts["fields"] += 1
                                if value != result[field]:
                                    differences.append({"group": group, "field": field, "cs": value, "rs": result[field]})
                                    counts[f"mismatch:{group}/{field}"] += 1
                if differences:
                    counts["failed_combinations"] += 1
                    failures.append({"path": str(path), "sha256": digest, "mods": mods, "classic": classic, "differences": differences})
        if changed:
            # Atomically publish complete map caches, including duplicate files.
            temporary = packed.with_suffix(f".{threading.get_ident()}.tmp")
            temporary.write_bytes(gzip.compress(json.dumps(references).encode(), mtime=0))
            temporary.replace(packed)
        counts["maps"] = 1
        return counts, failures

    counts = Counter()
    start = time.monotonic()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    try:
        with args.report.open("w", encoding="utf-8", newline="\n") as report, ThreadPoolExecutor(max_workers=args.jobs) as pool:
            futures = [pool.submit(compare_map, item) for item in standard]
            for index, future in enumerate(as_completed(futures)):
                map_counts, failures = future.result()
                counts.update(map_counts)
                for failure in failures:
                    report.write(json.dumps(failure, ensure_ascii=False) + "\n")
                report.flush()
                if (index + 1) % 10 == 0 or index + 1 == len(standard):
                    print(f"{index + 1}/{len(standard)} maps; {counts['failed_combinations']} failures; {time.monotonic() - start:.1f}s", flush=True)
    finally:
        for process in processes:
            try:
                process.stdin.close()
            except OSError:
                pass
            process.wait(timeout=30)
    summary = {"input_files": len(paths), "excluded_empty_files": empty_files, "distinct_maps": len({digest for digest, _ in standard}), "counts": dict(counts), "seconds": time.monotonic() - start, "reference_hash": fingerprint.hexdigest(), "mods": MODS, "classic": args.classic}
    args.report.with_suffix(".summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8", newline="\n")
    print(json.dumps(summary, indent=2), flush=True)
    if counts["failed_combinations"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

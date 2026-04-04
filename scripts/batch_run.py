#!/usr/bin/env python3
"""
Batch runner: process a directory of PPTX files through the SlideSherlock pipeline.

Usage:
    python scripts/batch_run.py /path/to/pptx_dir --preset draft --workers 3
    python scripts/batch_run.py /path/to/pptx_dir --preset draft --workers 3 --output /path/to/results

Produces:
    <output_dir>/
    ├── <file1>/run_log.json, metrics.json, final.mp4
    ├── <file2>/run_log.json, metrics.json, final.mp4
    ├── ...
    ├── batch_summary.json        # aggregated stats across all runs
    └── batch_summary.csv         # one row per file, ready for pandas/LaTeX
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_one(pptx_path: str, output_dir: str, preset: str, idx: int, total: int) -> dict:
    """Run the CLI on a single PPTX. Returns a summary dict."""
    basename = Path(pptx_path).stem
    file_output = os.path.join(output_dir, basename)

    t0 = time.time()
    result = {
        "file": os.path.basename(pptx_path),
        "basename": basename,
        "input_bytes": os.path.getsize(pptx_path),
        "status": "unknown",
        "pipeline_duration_s": 0,
        "slide_count": 0,
        "output_bytes": 0,
        "error": None,
    }

    try:
        env = {**os.environ, "PYTHONPATH": f"{repo_root}:{repo_root}/packages/core"}
        proc = subprocess.run(
            [
                os.path.join(repo_root, "venv", "bin", "python"),
                os.path.join(repo_root, "scripts", "slidesherlock_cli.py"),
                "run",
                pptx_path,
                "--preset",
                preset,
                "--output",
                file_output,
            ],
            capture_output=True,
            text=True,
            timeout=900,  # 15 min max per file
            env=env,
            cwd=repo_root,
        )

        elapsed = time.time() - t0
        result["pipeline_duration_s"] = round(elapsed, 1)

        # Read run_log.json if it exists
        log_path = os.path.join(file_output, "run_log.json")
        if os.path.exists(log_path):
            with open(log_path) as f:
                run_log = json.load(f)
            result["status"] = "ok"
            result["slide_count"] = run_log.get("slide_count", 0)
            result["pipeline_duration_s"] = run_log.get("pipeline_duration_s", elapsed)
            result["stages"] = run_log.get("stages", {})
            result["variant"] = run_log.get("variant")

            # Check for output video
            video_path = os.path.join(file_output, "final.mp4")
            if os.path.exists(video_path):
                result["output_bytes"] = os.path.getsize(video_path)
            else:
                result["status"] = "no_video"
        else:
            result["status"] = "failed"
            result["error"] = proc.stderr[-500:] if proc.stderr else "no run_log.json"

        if proc.returncode != 0 and result["status"] != "ok":
            result["status"] = "failed"
            result["error"] = proc.stderr[-500:] if proc.stderr else f"exit code {proc.returncode}"

    except subprocess.TimeoutExpired:
        result["status"] = "timeout"
        result["error"] = "exceeded 900s timeout"
        result["pipeline_duration_s"] = 900
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        result["pipeline_duration_s"] = round(time.time() - t0, 1)

    status_icon = "OK" if result["status"] == "ok" else result["status"].upper()
    print(
        f"  [{idx:>3}/{total}] {status_icon:<10} {result['pipeline_duration_s']:>6.1f}s  {result.get('slide_count', '?'):>3} slides  {result['file'][:60]}"
    )
    return result


def aggregate(results: list[dict], output_dir: str):
    """Write batch_summary.json and batch_summary.csv."""
    ok = [r for r in results if r["status"] == "ok"]
    failed = [r for r in results if r["status"] != "ok"]

    # Stage timing aggregation
    stage_totals: dict[str, list[float]] = {}
    for r in ok:
        for sname, sdata in r.get("stages", {}).items():
            base = sname.split("_")[0]  # normalize verify_en → verify
            stage_totals.setdefault(base, []).append(sdata.get("duration_s", 0))

    stage_stats = {}
    for sname, durations in sorted(stage_totals.items()):
        if durations:
            stage_stats[sname] = {
                "mean_s": round(sum(durations) / len(durations), 2),
                "min_s": round(min(durations), 2),
                "max_s": round(max(durations), 2),
                "total_s": round(sum(durations), 2),
                "count": len(durations),
            }

    summary = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "total_files": len(results),
        "successful": len(ok),
        "failed": len(failed),
        "success_rate": round(len(ok) / len(results) * 100, 1) if results else 0,
        "total_slides": sum(r.get("slide_count", 0) for r in ok),
        "total_pipeline_s": round(sum(r["pipeline_duration_s"] for r in ok), 1),
        "mean_pipeline_s": round(sum(r["pipeline_duration_s"] for r in ok) / len(ok), 1)
        if ok
        else 0,
        "mean_slides": round(sum(r.get("slide_count", 0) for r in ok) / len(ok), 1) if ok else 0,
        "total_input_mb": round(sum(r["input_bytes"] for r in results) / 1e6, 1),
        "total_output_mb": round(sum(r.get("output_bytes", 0) for r in ok) / 1e6, 1),
        "stage_stats": stage_stats,
        "failures": [{"file": r["file"], "error": r.get("error", "")[:200]} for r in failed],
    }

    # Write JSON
    summary_path = os.path.join(output_dir, "batch_summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    # Write CSV (one row per file)
    csv_path = os.path.join(output_dir, "batch_summary.csv")
    fieldnames = [
        "file",
        "status",
        "slide_count",
        "pipeline_duration_s",
        "input_bytes",
        "output_bytes",
        "error",
    ]
    # Add per-stage duration columns
    stage_names = [
        "ingest",
        "evidence",
        "render",
        "graph",
        "script",
        "verify",
        "translate",
        "audio",
        "video",
    ]
    for sn in stage_names:
        fieldnames.append(f"{sn}_s")

    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in results:
            row = {
                "file": r["file"],
                "status": r["status"],
                "slide_count": r.get("slide_count", 0),
                "pipeline_duration_s": r["pipeline_duration_s"],
                "input_bytes": r["input_bytes"],
                "output_bytes": r.get("output_bytes", 0),
                "error": (r.get("error") or "")[:100],
            }
            for sn in stage_names:
                # Check both "sn" and "sn_en" variants
                stages = r.get("stages", {})
                d = stages.get(sn, stages.get(f"{sn}_en", {}))
                row[f"{sn}_s"] = d.get("duration_s", "") if d else ""
            writer.writerow(row)

    # Print summary
    print()
    print("=" * 64)
    print("  BATCH SUMMARY")
    print("=" * 64)
    print(f"  Files processed:  {len(results)}")
    print(f"  Successful:       {len(ok)} ({summary['success_rate']}%)")
    print(f"  Failed:           {len(failed)}")
    print(f"  Total slides:     {summary['total_slides']}")
    print(f"  Mean pipeline:    {summary['mean_pipeline_s']}s")
    print(f"  Mean slides:      {summary['mean_slides']}")
    print(f"  Total input:      {summary['total_input_mb']} MB")
    print(f"  Total output:     {summary['total_output_mb']} MB")
    print()

    if stage_stats:
        print("  Stage Timing (mean across successful runs):")
        for sname, stats in stage_stats.items():
            print(
                f"    {sname:<12} {stats['mean_s']:>7.1f}s mean  ({stats['min_s']:.1f}–{stats['max_s']:.1f}s)"
            )
        print()

    if failed:
        print(f"  Failed files ({len(failed)}):")
        for r in failed[:10]:
            print(f"    {r['file'][:50]}: {r.get('error', '')[:80]}")
        if len(failed) > 10:
            print(f"    ... and {len(failed) - 10} more")
        print()

    print(f"  JSON:  {summary_path}")
    print(f"  CSV:   {csv_path}")
    print("=" * 64)

    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Batch run SlideSherlock on a directory of PPTX files"
    )
    parser.add_argument("pptx_dir", help="Directory containing .pptx files")
    parser.add_argument("--preset", "-p", default="draft", help="Quality preset (default: draft)")
    parser.add_argument(
        "--output", "-o", default=None, help="Output directory (default: ./output/batch)"
    )
    parser.add_argument(
        "--workers", "-w", type=int, default=3, help="Parallel workers (default: 3)"
    )
    parser.add_argument("--limit", "-n", type=int, default=None, help="Process only first N files")
    args = parser.parse_args()

    pptx_dir = os.path.abspath(args.pptx_dir)
    if not os.path.isdir(pptx_dir):
        print(f"Error: {pptx_dir} is not a directory", file=sys.stderr)
        return 1

    pptx_files = sorted(
        [
            os.path.join(pptx_dir, f)
            for f in os.listdir(pptx_dir)
            if f.lower().endswith(".pptx") and not f.startswith("~$")
        ]
    )

    if args.limit:
        pptx_files = pptx_files[: args.limit]

    if not pptx_files:
        print(f"No .pptx files found in {pptx_dir}", file=sys.stderr)
        return 1

    output_dir = os.path.abspath(args.output or os.path.join(repo_root, "output", "batch"))
    os.makedirs(output_dir, exist_ok=True)

    total = len(pptx_files)
    workers = min(args.workers, total)

    print(f"\n  SlideSherlock Batch Run")
    print(f"  Files:   {total}")
    print(f"  Preset:  {args.preset}")
    print(f"  Workers: {workers}")
    print(f"  Output:  {output_dir}")
    print()

    t0 = time.time()
    results = []

    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {}
        for i, pptx in enumerate(pptx_files, 1):
            future = pool.submit(run_one, pptx, output_dir, args.preset, i, total)
            futures[future] = pptx

        for future in as_completed(futures):
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                pptx = futures[future]
                results.append(
                    {
                        "file": os.path.basename(pptx),
                        "status": "error",
                        "pipeline_duration_s": 0,
                        "input_bytes": 0,
                        "error": str(e),
                    }
                )

    # Sort results by filename for consistent output
    results.sort(key=lambda r: r["file"])

    wall_time = time.time() - t0
    print(f"\n  Wall time: {wall_time:.0f}s ({wall_time/60:.1f} min)")

    summary = aggregate(results, output_dir)

    return 0


if __name__ == "__main__":
    sys.exit(main())

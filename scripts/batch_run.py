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
        cmd = [
            os.path.join(repo_root, "venv", "bin", "python"),
            os.path.join(repo_root, "scripts", "slidesherlock_cli.py"),
            "run",
            pptx_path,
            "--preset",
            preset,
            "--output",
            file_output,
        ]
        # Pass --ai-narration if LLM_PROVIDER is set to openai
        if os.environ.get("LLM_PROVIDER", "").strip().lower() == "openai":
            cmd.append("--ai-narration")
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=1800,  # 30 min max per file
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

            # Extract paper-relevant metrics from run_log
            cov = run_log.get("coverage", {})
            result["total_claims"] = cov.get("total_claims", 0)
            result["claims_with_evidence"] = cov.get("claims_with_evidence", 0)
            result["pct_evidence_coverage"] = cov.get("pct_claims_with_evidence", 0)
            result["verifier_pass"] = cov.get("pass", 0)
            result["verifier_rewrite"] = cov.get("rewrite", 0)
            result["verifier_remove"] = cov.get("remove", 0)

            ev = run_log.get("evidence", {})
            result["evidence_items"] = ev.get("total_items", 0)
            result["evidence_kinds"] = ev.get("kinds", {})

            vr = run_log.get("verify", {})
            result["verify_decisions"] = vr.get("total_decisions", 0)
            result["verify_verdicts"] = vr.get("verdicts", {})
            result["verify_iterations"] = vr.get("iterations", 0)

            ai = run_log.get("ai_narration", {})
            result["ai_slides_rewritten"] = ai.get("slides_rewritten", 0)

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

    # Aggregate evidence/verifier metrics for paper tables
    total_evidence = sum(r.get("evidence_items", 0) for r in ok)
    total_claims = sum(r.get("total_claims", 0) for r in ok)
    total_claims_with_ev = sum(r.get("claims_with_evidence", 0) for r in ok)
    total_pass = sum(r.get("verifier_pass", 0) for r in ok)
    total_rewrite = sum(r.get("verifier_rewrite", 0) for r in ok)
    total_remove = sum(r.get("verifier_remove", 0) for r in ok)
    total_verdicts = total_pass + total_rewrite + total_remove

    # Aggregate evidence kind distribution
    kind_totals: dict[str, int] = {}
    for r in ok:
        for k, v in r.get("evidence_kinds", {}).items():
            kind_totals[k] = kind_totals.get(k, 0) + v

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
        # Paper-relevant aggregates (EMNLP + AAAI)
        "evidence": {
            "total_items": total_evidence,
            "mean_per_file": round(total_evidence / len(ok), 1) if ok else 0,
            "kind_distribution": kind_totals,
        },
        "verification": {
            "total_claims": total_claims,
            "claims_with_evidence": total_claims_with_ev,
            "pct_evidence_coverage": round(total_claims_with_ev / total_claims * 100, 1)
            if total_claims
            else 0,
            "total_verdicts": total_verdicts,
            "pass": total_pass,
            "rewrite": total_rewrite,
            "remove": total_remove,
            "pass_rate": round(total_pass / total_verdicts * 100, 1) if total_verdicts else 0,
            "rewrite_rate": round(total_rewrite / total_verdicts * 100, 1) if total_verdicts else 0,
            "remove_rate": round(total_remove / total_verdicts * 100, 1) if total_verdicts else 0,
        },
        "ai_narration": {
            "files_with_ai": sum(1 for r in ok if r.get("ai_slides_rewritten", 0) > 0),
            "total_slides_rewritten": sum(r.get("ai_slides_rewritten", 0) for r in ok),
        },
        "failures": [{"file": r["file"], "error": (r.get("error") or "")[:200]} for r in failed],
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
        # Evidence metrics (EMNLP + AAAI)
        "evidence_items",
        "total_claims",
        "claims_with_evidence",
        "pct_evidence_coverage",
        # Verifier metrics (EMNLP + AAAI)
        "verifier_pass",
        "verifier_rewrite",
        "verifier_remove",
        "verify_iterations",
        # AI narration metrics
        "ai_slides_rewritten",
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
        "narrate",
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
                "evidence_items": r.get("evidence_items", 0),
                "total_claims": r.get("total_claims", 0),
                "claims_with_evidence": r.get("claims_with_evidence", 0),
                "pct_evidence_coverage": r.get("pct_evidence_coverage", 0),
                "verifier_pass": r.get("verifier_pass", 0),
                "verifier_rewrite": r.get("verifier_rewrite", 0),
                "verifier_remove": r.get("verifier_remove", 0),
                "verify_iterations": r.get("verify_iterations", 0),
                "ai_slides_rewritten": r.get("ai_slides_rewritten", 0),
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

    # Paper-relevant metrics
    ev = summary.get("evidence", {})
    vf = summary.get("verification", {})
    if ev.get("total_items"):
        print("  Evidence Metrics:")
        print(f"    Total evidence items: {ev['total_items']} ({ev['mean_per_file']} mean/file)")
        for k, v in sorted(ev.get("kind_distribution", {}).items(), key=lambda x: -x[1])[:8]:
            print(f"      {k}: {v}")
        print()
    if vf.get("total_verdicts"):
        print("  Verification Metrics:")
        print(f"    Claims: {vf['total_claims']} total, {vf['claims_with_evidence']} grounded ({vf['pct_evidence_coverage']}%)")
        print(f"    Verdicts: {vf['pass']} PASS ({vf['pass_rate']}%) | {vf['rewrite']} REWRITE ({vf['rewrite_rate']}%) | {vf['remove']} REMOVE ({vf['remove_rate']}%)")
        print()

    if failed:
        print(f"  Failed files ({len(failed)}):")
        for r in failed[:10]:
            print(f"    {r['file'][:50]}: {(r.get('error') or '')[:80]}")
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

    print("\n  SlideSherlock Batch Run")
    print(f"  Files:   {total}")
    print(f"  Preset:  {args.preset}")
    print(f"  Workers: {workers}")
    print(f"  Output:  {output_dir}")
    print()

    t0 = time.time()
    results = []
    completed = 0
    ok_count = 0
    total_file_time = 0.0

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
                result = {
                    "file": os.path.basename(pptx),
                    "status": "error",
                    "pipeline_duration_s": 0,
                    "input_bytes": 0,
                    "error": str(e),
                }
                results.append(result)

            # Progress logging with ETA
            completed += 1
            if result.get("status") == "ok":
                ok_count += 1
                total_file_time += result.get("pipeline_duration_s", 0)
            elapsed = time.time() - t0
            avg_per_file = elapsed / completed if completed else 0
            remaining = (total - completed) * avg_per_file / max(workers, 1)
            eta_min = remaining / 60
            avg_file_time = total_file_time / ok_count if ok_count else 0
            print(
                f"  Progress: {completed}/{total} done ({ok_count} OK) | "
                f"Elapsed: {elapsed/60:.1f}m | ETA: {eta_min:.1f}m | "
                f"Avg: {avg_file_time:.0f}s/file"
            )

    # Sort results by filename for consistent output
    results.sort(key=lambda r: r["file"])

    wall_time = time.time() - t0
    print(f"\n  Wall time: {wall_time:.0f}s ({wall_time/60:.1f} min)")

    aggregate(results, output_dir)

    return 0


if __name__ == "__main__":
    sys.exit(main())

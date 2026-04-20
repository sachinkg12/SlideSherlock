#!/usr/bin/env python3
"""
Hallucination Baseline Experiment (E1-E3).

Three conditions on N LoC PPTX files:
  A) Raw GPT: SKIP_VERIFY=1 NARRATE_NO_EVIDENCE=1 (no evidence in prompt, no verifier)
  B) Grounded: SKIP_VERIFY=1 (evidence in prompt, no verifier loop)
  C) Full:     default pipeline (evidence + verifier + AI narration)

Usage:
    python scripts/hallucination_experiment.py /path/to/pptx_dir \
        --limit 30 --output /path/to/results

Produces:
    <output>/
    ├── condition_a/   (per-file run_log.json, metrics.json, ai_narration.json)
    ├── condition_b/
    ├── condition_c/
    └── experiment_results.json   (aggregated comparison table)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Load .env file if present (for OPENAI_API_KEY etc.)
env_path = os.path.join(repo_root, ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

# Condition definitions: env vars to set for each
CONDITIONS = {
    "condition_a": {
        "label": "Raw GPT (no evidence, no verifier)",
        "env": {"SKIP_VERIFY": "1", "NARRATE_NO_EVIDENCE": "1"},
    },
    "condition_b": {
        "label": "Grounded prompt (evidence, no verifier)",
        "env": {"SKIP_VERIFY": "1", "NARRATE_NO_EVIDENCE": "0"},
    },
    "condition_c": {
        "label": "Full pipeline (evidence + verifier)",
        "env": {"SKIP_VERIFY": "0", "NARRATE_NO_EVIDENCE": "0"},
    },
}


def run_one(pptx_path: str, output_dir: str, condition_env: dict, idx: int, total: int) -> dict:
    """Run one PPTX under one condition."""
    basename = Path(pptx_path).stem
    file_output = os.path.join(output_dir, basename)

    t0 = time.time()
    result = {
        "file": os.path.basename(pptx_path),
        "basename": basename,
        "status": "unknown",
        "pipeline_duration_s": 0,
        "slide_count": 0,
    }

    try:
        env = {
            **os.environ,
            "PYTHONPATH": f"{repo_root}:{repo_root}/packages/core",
            "LLM_PROVIDER": "openai",
            "SKIP_STAGE_CACHE": "1",  # Don't reuse cached stages across conditions
            **condition_env,
        }
        cmd = [
            os.path.join(repo_root, "venv", "bin", "python"),
            os.path.join(repo_root, "scripts", "slidesherlock_cli.py"),
            "run",
            pptx_path,
            "--preset",
            "draft",
            "--output",
            file_output,
            "--ai-narration",
            "--skip-av",  # Skip audio+video — we only need narration text
        ]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=1800,
            env=env,
            cwd=repo_root,
        )

        elapsed = time.time() - t0
        result["pipeline_duration_s"] = round(elapsed, 1)

        log_path = os.path.join(file_output, "run_log.json")
        if os.path.exists(log_path):
            with open(log_path) as f:
                run_log = json.load(f)
            result["status"] = "ok"
            result["slide_count"] = run_log.get("slide_count", 0)
            result["pipeline_duration_s"] = run_log.get("pipeline_duration_s", elapsed)

            cov = run_log.get("coverage", {})
            result["total_claims"] = cov.get("total_claims", 0)
            result["claims_with_evidence"] = cov.get("claims_with_evidence", 0)
            result["pct_evidence_coverage"] = cov.get("pct_claims_with_evidence", 0)
            result["verifier_pass"] = cov.get("pass", 0)
            result["verifier_rewrite"] = cov.get("rewrite", 0)
            result["verifier_remove"] = cov.get("remove", 0)

            ai = run_log.get("ai_narration", {})
            result["ai_slides_rewritten"] = ai.get("slides_rewritten", 0)

            # Read AI narration output for hallucination analysis
            narration_path = os.path.join(file_output, "ai_narration.json")
            if os.path.exists(narration_path):
                with open(narration_path) as f:
                    result["narration_entries"] = json.load(f)
        else:
            result["status"] = "failed"
            result["error"] = proc.stderr[-500:] if proc.stderr else "no run_log.json"

        if proc.returncode != 0 and result["status"] != "ok":
            result["status"] = "failed"
            result["error"] = proc.stderr[-500:] if proc.stderr else f"exit {proc.returncode}"

    except subprocess.TimeoutExpired:
        result["status"] = "timeout"
        result["pipeline_duration_s"] = 1800
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        result["pipeline_duration_s"] = round(time.time() - t0, 1)

    icon = "OK" if result["status"] == "ok" else result["status"].upper()
    print(
        f"  [{idx:>3}/{total}] {icon:<8} {result['pipeline_duration_s']:>6.1f}s  {result['file'][:50]}"
    )
    return result


def aggregate_condition(results: list[dict]) -> dict:
    """Aggregate metrics for one condition."""
    ok = [r for r in results if r["status"] == "ok"]
    total_claims = sum(r.get("total_claims", 0) for r in ok)
    total_pass = sum(r.get("verifier_pass", 0) for r in ok)
    total_rewrite = sum(r.get("verifier_rewrite", 0) for r in ok)
    total_remove = sum(r.get("verifier_remove", 0) for r in ok)
    total_verdicts = total_pass + total_rewrite + total_remove
    total_claims_with_ev = sum(r.get("claims_with_evidence", 0) for r in ok)

    return {
        "files_processed": len(ok),
        "files_failed": len(results) - len(ok),
        "total_slides": sum(r.get("slide_count", 0) for r in ok),
        "total_claims": total_claims,
        "claims_with_evidence": total_claims_with_ev,
        "pct_evidence_coverage": round(total_claims_with_ev / total_claims * 100, 1)
        if total_claims
        else 0,
        "verifier_pass": total_pass,
        "verifier_rewrite": total_rewrite,
        "verifier_remove": total_remove,
        "pass_rate": round(total_pass / total_verdicts * 100, 1) if total_verdicts else 0,
        "rewrite_rate": round(total_rewrite / total_verdicts * 100, 1) if total_verdicts else 0,
        "remove_rate": round(total_remove / total_verdicts * 100, 1) if total_verdicts else 0,
        "ai_slides_rewritten": sum(r.get("ai_slides_rewritten", 0) for r in ok),
        "mean_pipeline_s": round(sum(r["pipeline_duration_s"] for r in ok) / len(ok), 1)
        if ok
        else 0,
    }


def main():
    parser = argparse.ArgumentParser(description="Hallucination baseline experiment (E1-E3)")
    parser.add_argument("pptx_dir", help="Directory containing PPTX files")
    parser.add_argument(
        "--output", "-o", default="./hallucination_results", help="Output directory"
    )
    parser.add_argument("--limit", "-n", type=int, default=30, help="Number of files to process")
    parser.add_argument(
        "--conditions",
        "-c",
        nargs="+",
        default=["condition_a", "condition_b", "condition_c"],
        choices=list(CONDITIONS.keys()),
        help="Which conditions to run (default: all three)",
    )
    args = parser.parse_args()

    # Discover PPTX files
    pptx_dir = os.path.abspath(args.pptx_dir)
    pptx_files = sorted(
        [
            os.path.join(pptx_dir, f)
            for f in os.listdir(pptx_dir)
            if f.endswith(".pptx") and not f.startswith("~$")
        ]
    )

    if args.limit and args.limit < len(pptx_files):
        pptx_files = pptx_files[: args.limit]

    print(f"\n{'='*60}")
    print(f"Hallucination Baseline Experiment")
    print(f"Files: {len(pptx_files)} | Conditions: {', '.join(args.conditions)}")
    print(f"Output: {args.output}")
    print(f"{'='*60}\n")

    os.makedirs(args.output, exist_ok=True)
    all_results = {}

    for cond_name in args.conditions:
        cond = CONDITIONS[cond_name]
        cond_output = os.path.join(args.output, cond_name)
        os.makedirs(cond_output, exist_ok=True)

        print(f"\n--- {cond_name}: {cond['label']} ---")
        print(f"    Env: {cond['env']}")
        print()

        results = []
        for i, pptx_path in enumerate(pptx_files, 1):
            r = run_one(pptx_path, cond_output, cond["env"], i, len(pptx_files))
            results.append(r)

        agg = aggregate_condition(results)
        all_results[cond_name] = {
            "label": cond["label"],
            "env": cond["env"],
            "aggregate": agg,
            "per_file": [{k: v for k, v in r.items() if k != "narration_entries"} for r in results],
        }

        print(
            f"\n  Summary: {agg['files_processed']}/{len(pptx_files)} ok, "
            f"claims={agg['total_claims']}, "
            f"pass={agg['pass_rate']}%, rewrite={agg['rewrite_rate']}%, "
            f"coverage={agg['pct_evidence_coverage']}%"
        )

    # Write combined results
    experiment = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "pptx_dir": pptx_dir,
        "num_files": len(pptx_files),
        "conditions": all_results,
    }

    results_path = os.path.join(args.output, "experiment_results.json")
    with open(results_path, "w") as f:
        json.dump(experiment, f, indent=2)
    print(f"\nResults written to {results_path}")

    # Print comparison table
    print(f"\n{'='*60}")
    print(f"COMPARISON TABLE")
    print(f"{'='*60}")
    print(f"{'Condition':<35} {'Claims':>7} {'Pass%':>7} {'Rewrite%':>9} {'Coverage%':>10}")
    print("-" * 70)
    for cond_name in args.conditions:
        agg = all_results[cond_name]["aggregate"]
        label = CONDITIONS[cond_name]["label"]
        print(
            f"{label:<35} {agg['total_claims']:>7} {agg['pass_rate']:>6.1f}% {agg['rewrite_rate']:>8.1f}% {agg['pct_evidence_coverage']:>9.1f}%"
        )
    print()


if __name__ == "__main__":
    main()

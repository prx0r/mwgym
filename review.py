"""MWGym Experiment Review Routine.

Reads experiment logs, analyzes results, and recommends next steps.
Run: python3 /root/mwgym/review.py [--log-dir /root/mwgym/logs] [--out /root/mwgym/logs/REVIEW.md]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def load_experiments(log_dir: Path) -> list[dict]:
    """Load all JSON experiment logs from the log directory."""
    experiments = []
    for p in sorted(log_dir.glob("*.json")):
        if p.name == "REVIEW.md" or p.name.startswith("."):
            continue
        try:
            data = json.loads(p.read_text())
            data["_file"] = p.name
            experiments.append(data)
        except (json.JSONDecodeError, KeyError) as e:
            print(f"WARN: skipping {p.name}: {e}", file=sys.stderr)
    return experiments


def analyze_experiment(exp: dict) -> dict:
    """Produce a structured analysis of one experiment."""
    results = exp.get("results", [])
    summary = exp.get("summary", {})

    # Group by genome
    by_genome: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        by_genome[r.get("genome", r.get("genome_id", "unknown"))].append(r)

    genome_stats = {}
    for genome, runs in by_genome.items():
        n = len(runs)
        successes = sum(1 for r in runs if r.get("success", False))
        failures = [r for r in runs if not r.get("success", False)]
        total_tokens = sum(r.get("tokens", r.get("total_tokens", 0)) for r in runs)
        total_ms = sum(r.get("ms", r.get("duration_ms", 0)) for r in runs)
        total_artifacts = sum(len(r.get("artifacts", [])) for r in runs)

        # Failure analysis
        failure_reasons = []
        for f in failures:
            preview = f.get("output_preview", "")
            if "timed out" in preview.lower():
                failure_reasons.append("timeout")
            elif "error" in preview.lower():
                failure_reasons.append("error")
            else:
                failure_reasons.append("wrong_output")

        genome_stats[genome] = {
            "n": n,
            "successes": successes,
            "failures": len(failures),
            "pass_rate": round(successes / max(1, n), 3),
            "total_tokens": total_tokens,
            "avg_tokens": round(total_tokens / max(1, n)),
            "total_ms": total_ms,
            "avg_ms": round(total_ms / max(1, n)),
            "total_artifacts": total_artifacts,
            "failure_tasks": [{"task_id": f.get("task_id"), "reason": failure_reasons[i] if i < len(failure_reasons) else "unknown", "preview": f.get("output_preview", "")[:80]} for i, f in enumerate(failures)],
        }

    # Cross-genome comparison
    genomes = list(genome_stats.keys())
    winner = None
    if genomes:
        # Winner = highest pass_rate, then lowest avg_tokens as tiebreak
        winner = min(genomes, key=lambda g: (-genome_stats[g]["pass_rate"], genome_stats[g]["avg_tokens"]))

    return {
        "experiment": exp.get("experiment", exp.get("_file", "unknown")),
        "run_id": exp.get("run_id", ""),
        "timestamp": exp.get("timestamp", ""),
        "tasks": exp.get("tasks", len(results)),
        "genome_stats": genome_stats,
        "winner": winner,
        "total_results": len(results),
    }


def generate_recommendations(analyses: list[dict]) -> list[str]:
    """Generate next-step recommendations based on all experiment analyses."""
    recs = []

    for a in analyses:
        stats = a["genome_stats"]

        # Check for timeout failures
        for genome, s in stats.items():
            for f in s.get("failure_tasks", []):
                if f["reason"] == "timeout":
                    recs.append(
                        f"FIX: {genome} timed out on {f['task_id']} — increase max_wall_seconds "
                        f"or reduce context_pack size for fast-bundle genome"
                    )

        # Check token efficiency
        genomes = list(stats.keys())
        if len(genomes) >= 2:
            sorted_by_tokens = sorted(genomes, key=lambda g: stats[g]["avg_tokens"])
            most_efficient = sorted_by_tokens[0]
            least_efficient = sorted_by_tokens[-1]
            ratio = stats[least_efficient]["avg_tokens"] / max(1, stats[most_efficient]["avg_tokens"])
            if ratio > 2.0:
                recs.append(
                    f"OPTIMIZE: {least_efficient} uses {ratio:.1f}x more tokens than {most_efficient} — "
                    f"consider shorter system prompts or fewer output fields"
                )

        # Check pass rates
        for genome, s in stats.items():
            if s["pass_rate"] < 1.0:
                recs.append(
                    f"RELIABILITY: {genome} at {s['pass_rate']*100:.0f}% pass rate — "
                    f"investigate {s['failures']} failure(s)"
                )

    # Strategic recs based on overall progress
    all_genomes = set()
    for a in analyses:
        all_genomes.update(a["genome_stats"].keys())

    if "direct-fast" in all_genomes and "fast-bundle" in all_genomes:
        recs.append(
            "NEXT STEP: Both baseline genomes validated. Build the dynamic router (Arm D) "
            "that picks direct-fast for simple tasks and fast-bundle for multi-file tasks"
        )

    if not any("ygo" in a["experiment"].lower() for a in analyses):
        recs.append(
            "YGO WORLD: No YGO experiments yet. Build YGO→genome adapter to test "
            "resource allocation in a closed deterministic world"
        )

    if not any("letta" in a["experiment"].lower() for a in analyses):
        recs.append(
            "LETTA HARNESS: Not yet benchmarked. Need letta-stateless and letta-stateful "
            "arms to complete the 4-arm crossover from MWGYM-V2-SPEC"
        )

    return recs


def format_review(analyses: list[dict], recommendations: list[str]) -> str:
    """Format the full review as markdown."""
    lines = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines.append(f"# MWGym Experiment Review")
    lines.append(f"")
    lines.append(f"Generated: {now}")
    lines.append(f"Experiments reviewed: {len(analyses)}")
    lines.append(f"")

    for a in analyses:
        lines.append(f"---")
        lines.append(f"")
        lines.append(f"## {a['experiment']}")
        lines.append(f"")
        lines.append(f"- Run ID: `{a['run_id']}`")
        lines.append(f"- Timestamp: {a['timestamp']}")
        lines.append(f"- Tasks: {a['tasks']}")
        lines.append(f"- Winner: **{a['winner']}**")
        lines.append(f"")

        # Per-genome table
        lines.append(f"### Genome Performance")
        lines.append(f"")
        lines.append(f"| Genome | Pass | Tokens (avg) | Latency (avg) | Artifacts | Failures |")
        lines.append(f"|--------|------|-------------|---------------|-----------|----------|")
        for genome, s in sorted(a["genome_stats"].items()):
            lines.append(
                f"| {genome} | {s['successes']}/{s['n']} ({s['pass_rate']*100:.0f}%) "
                f"| {s['avg_tokens']} "
                f"| {s['avg_ms']}ms "
                f"| {s['total_artifacts']} "
                f"| {s['failures']} |"
            )
        lines.append(f"")

        # Failure details
        for genome, s in a["genome_stats"].items():
            if s.get("failure_tasks"):
                lines.append(f"### Failures: {genome}")
                lines.append(f"")
                for f in s["failure_tasks"]:
                    lines.append(f"- `{f['task_id']}`: {f['reason']} — {f['preview']}")
                lines.append(f"")

    # Recommendations
    lines.append(f"---")
    lines.append(f"")
    lines.append(f"## Recommendations")
    lines.append(f"")
    for i, rec in enumerate(recommendations, 1):
        lines.append(f"{i}. {rec}")
    lines.append(f"")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="MWGym experiment review")
    parser.add_argument("--log-dir", default="/root/mwgym/logs", help="Directory with experiment JSON logs")
    parser.add_argument("--out", default=None, help="Output review markdown file (default: log-dir/REVIEW.md)")
    parser.add_argument("--json", action="store_true", help="Output analysis as JSON instead of markdown")
    args = parser.parse_args()

    log_dir = Path(args.log_dir)
    out_path = Path(args.out) if args.out else log_dir / "REVIEW.md"

    experiments = load_experiments(log_dir)
    if not experiments:
        print(f"No experiment logs found in {log_dir}")
        sys.exit(1)

    print(f"Found {len(experiments)} experiment log(s)")

    analyses = [analyze_experiment(e) for e in experiments]
    recommendations = generate_recommendations(analyses)

    if args.json:
        output = json.dumps({"analyses": analyses, "recommendations": recommendations}, indent=2)
    else:
        output = format_review(analyses, recommendations)

    out_path.write_text(output)
    print(f"Review written to {out_path}")

    # Also print summary to stdout
    print(f"\n{'='*60}")
    for a in analyses:
        print(f"\n{a['experiment']}:")
        print(f"  Winner: {a['winner']}")
        for genome, s in a["genome_stats"].items():
            print(f"  {genome}: {s['pass_rate']*100:.0f}% pass, {s['avg_tokens']} tok, {s['avg_ms']}ms")
    print(f"\nRecommendations ({len(recommendations)}):")
    for i, rec in enumerate(recommendations, 1):
        print(f"  {i}. {rec}")


if __name__ == "__main__":
    main()

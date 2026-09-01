"""LabBrief — empirical memory for workers.

Queries Hydra for prior runs on a family, returns structured brief.
Worker receives this BEFORE execution. Brief is recorded as input artifact.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field


@dataclass
class LabBrief:
    """Structured brief from Hydra empirical data."""
    family_id: str = ""
    worker_genome_id: str = ""

    # Stats from prior runs
    total_runs: int = 0
    mean_quality: float = 0.0
    mean_cost_usd: float = 0.0
    mean_duration_ms: float = 0.0

    # Model economics
    model_stats: dict = field(default_factory=dict)
    # e.g. {"mimo-v2.5": {"n": 15, "quality": 0.85, "cost": 0.0}, "groq/...": {...}}

    # Capability evidence
    capabilities: dict = field(default_factory=dict)
    # e.g. {"model.select": {"score": 0.7, "n": 10}, "budget.allocate": {...}}

    # Failure patterns
    top_failures: list[dict] = field(default_factory=list)
    # e.g. [{"mode": "budget_exceeded", "freq": 0.3}, ...]

    # Successful patterns
    successful_patterns: list[str] = field(default_factory=list)

    # Similar runs
    similar_runs: list[dict] = field(default_factory=list)

    # What worked before
    recommendations: list[str] = field(default_factory=list)

    def to_context(self) -> str:
        """Format as text context for the worker."""
        lines = [f"## Lab Brief: {self.family_id}"]
        lines.append(f"Prior runs: {self.total_runs}")
        if self.total_runs > 0:
            lines.append(f"Mean quality: {self.mean_quality:.2f}")
            lines.append(f"Mean cost: ${self.mean_cost_usd:.4f}")

        if self.model_stats:
            lines.append("\n### Model Economics")
            for model, stats in self.model_stats.items():
                lines.append(f"- {model}: n={stats['n']}, quality={stats['quality']:.2f}, cost=${stats['cost']:.4f}")

        if self.capabilities:
            lines.append("\n### Capability Evidence")
            for cap, stats in self.capabilities.items():
                lines.append(f"- {cap}: score={stats['score']:.2f} (n={stats['n']})")

        if self.top_failures:
            lines.append("\n### Common Failures")
            for f in self.top_failures[:5]:
                lines.append(f"- {f['mode']}: {f['freq']*100:.0f}% of runs")

        if self.recommendations:
            lines.append("\n### Recommendations")
            for r in self.recommendations:
                lines.append(f"- {r}")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


def generate_brief(hydra, family_id: str, worker_genome_id: str = "") -> LabBrief:
    """Generate a LabBrief from Hydra data."""
    brief = LabBrief(family_id=family_id, worker_genome_id=worker_genome_id)

    # Get family stats
    stats = hydra.family_stats(family_id)
    brief.total_runs = stats.get("total_runs", 0) or 0
    brief.mean_quality = stats.get("mean_quality", 0) or 0.0
    brief.mean_cost_usd = stats.get("mean_cost_usd", 0) or 0.0

    # Get top failures
    failures = hydra.get_failure_modes(family_id, min_frequency=0.1)
    brief.top_failures = [{"mode": f["failure_mode"], "freq": f["frequency"]}
                          for f in failures[:5]]

    # Get capability evidence
    if worker_genome_id:
        caps = hydra.get_capabilities(worker_genome_id, family_id)
        brief.capabilities = {c["capability"]: {"score": c["mean_score"], "n": c["n_samples"]}
                              for c in caps}

    # Get model stats from runs
    runs = hydra.get_runs(family_id=family_id, limit=50)
    model_stats = {}
    for run in runs:
        model = run.get("model", "")
        if not model:
            continue
        if model not in model_stats:
            model_stats[model] = {"n": 0, "quality_sum": 0.0, "cost_sum": 0.0}
        model_stats[model]["n"] += 1
        model_stats[model]["quality_sum"] += run.get("quality_score", 0)
        model_stats[model]["cost_sum"] += run.get("cost_usd", 0)

    brief.model_stats = {
        m: {"n": s["n"],
            "quality": s["quality_sum"] / s["n"],
            "cost": s["cost_sum"] / s["n"]}
        for m, s in model_stats.items()
    }

    # Generate recommendations
    if brief.total_runs > 0:
        if brief.mean_quality > 0.8:
            brief.recommendations.append("Worker performs well on this family — maintain current approach")
        elif brief.mean_quality > 0.5:
            brief.recommendations.append("Worker has moderate success — focus on failure modes")
        else:
            brief.recommendations.append("Worker struggles — consider different strategy")

        if brief.top_failures:
            top = brief.top_failures[0]["mode"]
            if "budget" in top:
                brief.recommendations.append("Budget is limiting — prioritize cheaper model calls")
            elif "timeout" in top or "slow" in top:
                brief.recommendations.append("Speed matters — use faster model or reduce steps")
            elif "quality" in top or "incorrect" in top:
                brief.recommendations.append("Quality is low — use stronger model or verify more")

    return brief

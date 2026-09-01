"""FamilyWorldSpec — maps Oracle task families to CGE world generators.

Oracle defines what work exists. FamilyWorldSpec defines how to generate
synthetic training worlds for each task family.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class FamilyWorldSpec:
    """Binding between an Oracle task family and CGE world generation.

    One spec per family. The adversary mutates WorldGenomes within a family.
    """
    family_id: str = ""             # e.g. "software.bug_fix"
    task_family: str = ""           # Oracle taxonomy path
    submission_type: str = ""       # hackathon, api_integration, etc.

    # What capabilities this family tests
    capabilities: tuple[str, ...] = ()
    # e.g. ("code.understand", "code.write", "code.debug", "process.verify")

    # Hard gates for this family
    gates: tuple[str, ...] = ()
    # e.g. ("builds", "tests_pass", "required_files_exist")

    # Generator: creates WorldGenome instances
    generator: str = ""             # e.g. "software.bug_fix.v1"

    # Verifier: evaluates worker output
    verifier: str = ""              # e.g. "software.bug_fix.verifier.v1"

    # Mutator families: which perturbation classes apply
    mutator_families: tuple[str, ...] = ()
    # e.g. ("repo", "temporal", "information", "tool_failure")

    # Difficulty range
    min_difficulty: int = 1
    max_difficulty: int = 10

    # Resource defaults
    default_resources: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items()}
        d["capabilities"] = list(d["capabilities"])
        d["gates"] = list(d["gates"])
        d["mutator_families"] = list(d["mutator_families"])
        return d

    @classmethod
    def from_dict(cls, d: dict) -> FamilyWorldSpec:
        d = dict(d)
        for key in ("capabilities", "gates", "mutator_families"):
            if key in d and isinstance(d[key], list):
                d[key] = tuple(d[key])
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ─── Registry ────────────────────────────────────────────────────────

_REGISTRY: dict[str, FamilyWorldSpec] = {}


def register_family(spec: FamilyWorldSpec):
    """Register a family world spec."""
    _REGISTRY[spec.family_id] = spec


def get_family(family_id: str) -> FamilyWorldSpec | None:
    return _REGISTRY.get(family_id)


def list_families() -> list[str]:
    return list(_REGISTRY.keys())


def _seed_families():
    """Register the canonical 11 families from the Oracle taxonomy."""

    register_family(FamilyWorldSpec(
        family_id="software.implementation",
        task_family="software.implementation",
        submission_type="hackathon",
        capabilities=("code.understand", "code.write", "code.test", "process.verify",
                       "architecture.decide", "docs.write"),
        gates=("builds", "tests_pass", "required_files_exist", "no_secrets"),
        generator="software.implementation.v1",
        verifier="software.implementation.verifier.v1",
        mutator_families=("repo", "information", "temporal", "tool_failure"),
    ))

    register_family(FamilyWorldSpec(
        family_id="software.maintenance",
        task_family="software.maintenance",
        submission_type="bug_fix",
        capabilities=("code.understand", "code.debug", "code.write", "process.verify",
                       "regression.detect"),
        gates=("builds", "tests_pass", "no_regression", "fix_matches_description"),
        generator="software.maintenance.v1",
        verifier="software.maintenance.verifier.v1",
        mutator_families=("repo", "temporal", "information"),
    ))

    register_family(FamilyWorldSpec(
        family_id="research.analysis",
        task_family="research.analysis",
        submission_type="research_report",
        capabilities=("source.verify", "source.independently",
                       "claim.support", "reason.causal", "text.write"),
        gates=("claims_supported", "no_unsupported_claims", "sources_cited",
               "coverage_adequate"),
        generator="research.analysis.v1",
        verifier="research.analysis.verifier.v1",
        mutator_families=("information", "source", "temporal"),
    ))

    register_family(FamilyWorldSpec(
        family_id="research.verification",
        task_family="research.verification",
        submission_type="fact_check",
        capabilities=("source.verify", "claim.correct", "evidence.evaluate",
                       "reason.formal"),
        gates=("all_claims_verified", "no_false_negatives", "no_false_positives"),
        generator="research.verification.v1",
        verifier="research.verification.verifier.v1",
        mutator_families=("information", "source", "entity"),
    ))

    register_family(FamilyWorldSpec(
        family_id="ideation.technical",
        task_family="ideation.technical",
        submission_type="hackathon_idea",
        capabilities=("feasibility.assess", "constraint.satisfy",
                       "novelty.evaluate", "plan.create"),
        gates=("api_compatible", "budget_feasible", "deadline_feasible",
               "stack_compatible"),
        generator="ideation.technical.v1",
        verifier="ideation.technical.verifier.v1",
        mutator_families=("economic", "information", "temporal"),
    ))

    register_family(FamilyWorldSpec(
        family_id="content.writing",
        task_family="content.writing",
        submission_type="content_piece",
        capabilities=("source.integrate", "text.write", "audience.adapt",
                       "citation.verify"),
        gates=("truth_accurate", "required_coverage", "citations_valid",
               "length_adequate"),
        generator="content.writing.v1",
        verifier="content.writing.verifier.v1",
        mutator_families=("information", "source", "temporal"),
    ))

    register_family(FamilyWorldSpec(
        family_id="support.customer_service",
        task_family="support.customer_service",
        submission_type="support_response",
        capabilities=("policy.retrieve", "policy.apply", "process.escalate",
                       "text.respond", "state.lookup"),
        gates=("correct_action", "policy_compliant", "no_unauthorized_action"),
        generator="support.customer_service.v1",
        verifier="support.customer_service.verifier.v1",
        mutator_families=("policy", "temporal", "information"),
    ))

    register_family(FamilyWorldSpec(
        family_id="data.processing",
        task_family="data.processing",
        submission_type="data_pipeline",
        capabilities=("schema.understand", "transform.apply",
                       "error.handle", "output.validate"),
        gates=("exact_output_match", "records_retained", "no_data_loss",
               "reproducible"),
        generator="data.processing.v1",
        verifier="data.processing.verifier.v1",
        mutator_families=("information", "temporal", "tool_failure"),
    ))

    register_family(FamilyWorldSpec(
        family_id="business.decision",
        task_family="business.decision",
        submission_type="decision_memo",
        capabilities=("data.analyze", "risk.assess", "option.compare",
                       "recommend.justify"),
        gates=("decision_justified", "risk_acknowledged", "option_exhaustive"),
        generator="business.decision.v1",
        verifier="business.decision.verifier.v1",
        mutator_families=("economic", "information", "temporal"),
    ))

    register_family(FamilyWorldSpec(
        family_id="venue.autonomy",
        task_family="venue.autonomy",
        submission_type="gig_execution",
        capabilities=("platform.navigate", "auth.manage", "submit.execute",
                       "error.handle", "budget.manage"),
        gates=("submitted", "auth_valid", "no_budget_overrun"),
        generator="venue.autonomy.v1",
        verifier="venue.autonomy.verifier.v1",
        mutator_families=("economic", "tool_failure", "temporal", "policy"),
    ))

    register_family(FamilyWorldSpec(
        family_id="compute.routing",
        task_family="compute.routing",
        submission_type="resource_allocation",
        capabilities=("model.select", "budget.allocate", "quality.estimate",
                       "latency.predict", "escalation.decide"),
        gates=("budget_respected", "quality_threshold_met",
               "latency_satisfied"),
        generator="compute.routing.v1",
        verifier="compute.routing.verifier.v1",
        mutator_families=("economic", "tool_failure", "temporal"),
    ))

    # ─── Metaculus Forecasting ──────────────────────────────────────
    register_family(FamilyWorldSpec(
        family_id="forecasting.binary",
        task_family="forecasting.binary",
        submission_type="probability_forecast",
        capabilities=("evidence.gather", "base_rate.establish",
                       "calibration.apply", "uncertainty.quantify",
                       "update.incorporate"),
        gates=("probability_valid", "reasoning_documented",
               "calibration_better_than_baseline"),
        generator="forecasting.binary.v1",
        verifier="forecasting.binary.verifier.v1",
        mutator_families=("information", "temporal", "source"),
    ))

    register_family(FamilyWorldSpec(
        family_id="forecasting.numeric",
        task_family="forecasting.numeric",
        submission_type="cdf_forecast",
        capabilities=("evidence.gather", "distribution.estimate",
                       "bounds.establish", "calibration.apply",
                       "update.incorporate"),
        gates=("cdf_valid", "reasoning_documented",
               "calibration_better_than_baseline"),
        generator="forecasting.numeric.v1",
        verifier="forecasting.numeric.verifier.v1",
        mutator_families=("information", "temporal", "source"),
    ))

    register_family(FamilyWorldSpec(
        family_id="forecasting.multiple_choice",
        task_family="forecasting.multiple_choice",
        submission_type="probability_distribution",
        capabilities=("evidence.gather", "options.enumerate",
                       "probability.allocate", "calibration.apply",
                       "update.incorporate"),
        gates=("probabilities_sum_to_one", "reasoning_documented",
               "calibration_better_than_baseline"),
        generator="forecasting.multiple_choice.v1",
        verifier="forecasting.multiple_choice.verifier.v1",
        mutator_families=("information", "temporal", "source"),
    ))


_seed_families()

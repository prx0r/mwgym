"""MWGym Worlds — CGE-based adversarial world evolution.

Architecture:
  Oracle → FamilyWorldSpec → WorldGenome → CGE Compiler → Executable World
                                        ↕ (co-evolve)
                                   Adversary (failure-guided mutation)
                                        ↕
                                   Curriculum (MAP-Elites selection)
                                        ↕
                                   Worker (harness execution)
                                        ↕
                                   FailureVector → back to Adversary
"""
from .schema import FamilyWorldSpec, get_family, list_families, register_family
from .cge_adapter import (
    BaseWorld, ComputeRoutingWorld, ResearchVerificationWorld,
    SoftwareBugFixWorld, compile_world, register_world_class,
)
from .adversary import Adversary, MutationStrategy, STRATEGIES
from .curriculum import Curriculum, CurriculumConfig

__all__ = [
    "FamilyWorldSpec",
    "get_family",
    "list_families",
    "register_family",
    "BaseWorld",
    "compile_world",
    "register_world_class",
    "SoftwareBugFixWorld",
    "ResearchVerificationWorld",
    "ComputeRoutingWorld",
    "Adversary",
    "MutationStrategy",
    "STRATEGIES",
    "Curriculum",
    "CurriculumConfig",
]

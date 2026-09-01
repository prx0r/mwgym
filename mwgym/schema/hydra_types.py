"""HydraDB Schema — clean graph database design for the learning loop.

This module defines the canonical node types and relationships for storing
learning loop data in HydraDB. All data flows through this schema.

Design Principles (from HydraDB docs):
1. All node creation via MERGE with integer id
2. All properties are scalars (serialize complex data as JSON strings)
3. All relationships are directed and typed
4. Time as unix timestamps (integers)
5. String IDs stored as separate properties
6. One write per request, no transactions
7. Content-hash everything for Git lineage

Node Types:
- Run: one worker execution attempt
- World: CGE world configuration
- Worker: worker identity and version
- Capability: per-worker capability score
- Failure: what went wrong
- Curriculum: archived world for replay
- Experiment: controlled comparison
- Insight: reflection and learning
- Forecast: Metaculus prediction
- Question: Metaculus question

Relationship Types:
- EXECUTED_BY: Run → Worker
- IN_WORLD: Run → World
- PRODUCED: Run → Capability
- CAUSED: Run → Failure
- RESPONDS_TO: World → Failure
- EVOLVED_FROM: World → World
- SELECTED: Curriculum → World
- PART_OF: Experiment → Run
- DERIVED_FROM: Insight → Experiment
- AFFECTS: Insight → Capability
- APPLIED_TO: Insight → World
- FORECASTS: Forecast → Question
- MADE_BY: Forecast → Worker
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any


# ─── ID Generation ────────────────────────────────────────────────────

# Structured ID ranges to avoid collisions
ID_RUN = 10_000_000
ID_WORLD = 20_000_000
ID_WORKER = 30_000_000
ID_CAPABILITY = 40_000_000
ID_FAILURE = 50_000_000
ID_CURRICULUM = 60_000_000
ID_EXPERIMENT = 70_000_000
ID_INSIGHT = 80_000_000
ID_FORECAST = 90_000_000
ID_QUESTION = 100_000_000


def _to_int_id(string_id: str, base: int = 0) -> int:
    """Convert string ID to integer for HydraDB."""
    hash_hex = hashlib.md5(string_id.encode()).hexdigest()[:8]
    return base + int(hash_hex, 16) % 1_000_000


# ─── Node Types ───────────────────────────────────────────────────────

@dataclass
class RunNode:
    """One worker execution attempt."""
    run_id: str
    worker_id: str
    world_id: str
    status: str  # success, failure, timeout
    quality: float
    cost_usd: float
    duration_ms: int
    model: str
    content_hash: str = ""
    started_at: float = 0.0
    ended_at: float = 0.0
    
    def to_int_id(self) -> int:
        return _to_int_id(self.run_id, ID_RUN)
    
    def to_properties(self) -> dict:
        return {
            "id": self.to_int_id(),
            "run_id": self.run_id,
            "worker_id": self.worker_id,
            "world_id": self.world_id,
            "status": self.status,
            "quality": self.quality,
            "cost_usd": self.cost_usd,
            "duration_ms": self.duration_ms,
            "model": self.model,
            "content_hash": self.content_hash,
            "started_at": int(self.started_at),
            "ended_at": int(self.ended_at),
        }


@dataclass
class WorldNode:
    """CGE world configuration."""
    world_id: str
    family: str
    difficulty: int
    seed: int
    parent_id: str = ""
    params_json: str = ""
    created_at: float = 0.0
    
    def to_int_id(self) -> int:
        return _to_int_id(self.world_id, ID_WORLD)
    
    def to_properties(self) -> dict:
        return {
            "id": self.to_int_id(),
            "world_id": self.world_id,
            "family": self.family,
            "difficulty": self.difficulty,
            "seed": self.seed,
            "parent_id": self.parent_id,
            "params_json": self.params_json,
            "created_at": int(self.created_at),
        }


@dataclass
class WorkerNode:
    """Worker identity and version."""
    worker_id: str
    harness: str
    model: str
    version: int = 1
    
    def to_int_id(self) -> int:
        return _to_int_id(self.worker_id, ID_WORKER)
    
    def to_properties(self) -> dict:
        return {
            "id": self.to_int_id(),
            "worker_id": self.worker_id,
            "harness": self.harness,
            "model": self.model,
            "version": self.version,
        }


@dataclass
class CapabilityNode:
    """Per-worker capability score."""
    capability_id: str
    worker_id: str
    capability: str
    family: str
    score: float
    n_samples: int
    confidence: float = 0.5
    
    def to_int_id(self) -> int:
        return _to_int_id(self.capability_id, ID_CAPABILITY)
    
    def to_properties(self) -> dict:
        return {
            "id": self.to_int_id(),
            "capability_id": self.capability_id,
            "worker_id": self.worker_id,
            "capability": self.capability,
            "family": self.family,
            "score": self.score,
            "n_samples": self.n_samples,
            "confidence": self.confidence,
        }


@dataclass
class FailureNode:
    """What went wrong in a run."""
    failure_id: str
    run_id: str
    failure_type: str
    severity: float
    description: str = ""
    
    def to_int_id(self) -> int:
        return _to_int_id(self.failure_id, ID_FAILURE)
    
    def to_properties(self) -> dict:
        return {
            "id": self.to_int_id(),
            "failure_id": self.failure_id,
            "run_id": self.run_id,
            "failure_type": self.failure_type,
            "severity": self.severity,
            "description": self.description,
        }


@dataclass
class CurriculumNode:
    """Archived world for replay."""
    entry_id: str
    world_id: str
    family: str
    difficulty: int
    fitness: float
    niche: str
    replay_count: int = 0
    
    def to_int_id(self) -> int:
        return _to_int_id(self.entry_id, ID_CURRICULUM)
    
    def to_properties(self) -> dict:
        return {
            "id": self.to_int_id(),
            "entry_id": self.entry_id,
            "world_id": self.world_id,
            "family": self.family,
            "difficulty": self.difficulty,
            "fitness": self.fitness,
            "niche": self.niche,
            "replay_count": self.replay_count,
        }


@dataclass
class ExperimentNode:
    """Controlled comparison."""
    experiment_id: str
    hypothesis: str
    family: str
    status: str  # running, completed
    n_rounds: int = 0
    
    def to_int_id(self) -> int:
        return _to_int_id(self.experiment_id, ID_EXPERIMENT)
    
    def to_properties(self) -> dict:
        return {
            "id": self.to_int_id(),
            "experiment_id": self.experiment_id,
            "hypothesis": self.hypothesis,
            "family": self.family,
            "status": self.status,
            "n_rounds": self.n_rounds,
        }


@dataclass
class InsightNode:
    """Reflection and learning."""
    insight_id: str
    kind: str  # weakness_detected, adversary_stuck, etc.
    title: str
    body: str
    confidence: float
    experiment_id: str = ""
    
    def to_int_id(self) -> int:
        return _to_int_id(self.insight_id, ID_INSIGHT)
    
    def to_properties(self) -> dict:
        return {
            "id": self.to_int_id(),
            "insight_id": self.insight_id,
            "kind": self.kind,
            "title": self.title,
            "body": self.body,
            "confidence": self.confidence,
            "experiment_id": self.experiment_id,
        }


@dataclass
class ForecastNode:
    """Metaculus prediction."""
    forecast_id: str
    question_id: str
    worker_id: str
    prediction: float
    submitted_at: float
    brier_score: float = 0.0
    log_score: float = 0.0
    status: str = "pending"
    
    def to_int_id(self) -> int:
        return _to_int_id(self.forecast_id, ID_FORECAST)
    
    def to_properties(self) -> dict:
        return {
            "id": self.to_int_id(),
            "forecast_id": self.forecast_id,
            "question_id": self.question_id,
            "worker_id": self.worker_id,
            "prediction": self.prediction,
            "submitted_at": int(self.submitted_at),
            "brier_score": self.brier_score,
            "log_score": self.log_score,
            "status": self.status,
        }


@dataclass
class QuestionNode:
    """Metaculus question."""
    question_id: str
    metaculus_id: int
    title: str
    family: str
    close_time: float
    resolution: str = ""
    community_prediction: float = 0.5
    
    def to_int_id(self) -> int:
        return _to_int_id(self.question_id, ID_QUESTION)
    
    def to_properties(self) -> dict:
        return {
            "id": self.to_int_id(),
            "question_id": self.question_id,
            "metaculus_id": self.metaculus_id,
            "title": self.title,
            "family": self.family,
            "close_time": int(self.close_time),
            "resolution": self.resolution,
            "community_prediction": self.community_prediction,
        }


# ─── Relationship Types ───────────────────────────────────────────────

@dataclass
class Edge:
    """A relationship between two nodes."""
    src_label: str
    src_id: int
    dst_label: str
    dst_id: int
    edge_type: str
    properties: dict = field(default_factory=dict)
    
    def to_cypher(self) -> tuple[str, dict]:
        """Generate Cypher MERGE statement."""
        prop_str = ""
        if self.properties:
            parts = []
            for k, v in self.properties.items():
                if isinstance(v, str):
                    parts.append(f"{k}: \"{v}\"")
                elif isinstance(v, (int, float, bool)):
                    parts.append(f"{k}: {v}")
            prop_str = " {" + ", ".join(parts) + "}"
        
        query = f'''
            MERGE (a:{self.src_label} {{id: $src_id}})-[:{self.edge_type}{prop_str}]->(b:{self.dst_label} {{id: $dst_id}})
        '''
        return query, {"src_id": self.src_id, "dst_id": self.dst_id}

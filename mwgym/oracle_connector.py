"""Oracle Connector — fetch opportunities from Oracle, normalize to MWGym tasks.

The Oracle is the single source of truth for opportunities.
MWGym fetches from Oracle, not from external APIs directly.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from oracle.sdk import Oracle


@dataclass
class Opportunity:
    """Normalized opportunity from Oracle."""
    id: str = ""
    title: str = ""
    description: str = ""
    source: str = ""
    url: str = ""
    category: str = ""
    skills: list[str] = field(default_factory=list)
    reward_usd: float = 0.0
    currency: str = "USD"
    status: str = "open"
    posted_at: str = ""
    extra: dict = field(default_factory=dict)
    fetched_at: float = field(default_factory=time.time)

    def to_task(self) -> str:
        """Convert to MWGym task instruction based on category."""
        if self.category.startswith("forecasting"):
            return self._forecasting_task()
        return self._coding_task()

    def _forecasting_task(self) -> str:
        """Task instruction for forecasting questions."""
        task = f"Forecast: {self.title}\n\n"
        task += f"Source: {self.source} ({self.url})\n"
        task += f"Type: {self.category}\n"
        if self.extra.get("community_prediction") is not None:
            task += f"Community prediction: {self.extra['community_prediction']}\n"
        if self.extra.get("nr_forecasters"):
            task += f"Other forecasters: {self.extra['nr_forecasters']}\n"
        if self.extra.get("close_time"):
            task += f"Close: {self.extra['close_time']}\n"
        task += f"\nDescription:\n{self.description[:1000]}\n\n"
        task += "Instructions:\n"
        task += "1. Research the question thoroughly\n"
        task += "2. Consider base rates, recent evidence, and counterarguments\n"
        task += "3. Produce a probability estimate (0.01 to 0.99)\n"
        task += "4. Write your reasoning to reasoning.md\n"
        task += "5. Return JSON: {\"status\": \"complete\", \"probability\": 0.XX, \"notes\": \"...\"}\n"
        return task

    def _coding_task(self) -> str:
        """Task instruction for coding/bounty tasks."""
        task = f"Task: {self.title}\n\n"
        task += f"Description: {self.description[:1000]}\n\n"
        if self.skills:
            task += f"Required skills: {', '.join(self.skills)}\n\n"
        task += "Requirements:\n"
        task += "- Implement the solution in Python\n"
        task += "- Write code to a .py file\n"
        task += "- Code must be runnable (no syntax errors)\n\n"
        task += "Return JSON: {\"status\": \"complete\", \"writes\": [{\"path\": \"solution.py\", \"content\": \"...\"}], \"notes\": \"...\"}\n"
        return task

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


def fetch_from_oracle(oracle_url: str = "http://localhost:8788",
                       source: str = "", skill: str = "",
                       min_reward: float = 0, limit: int = 50) -> list[Opportunity]:
    """Fetch opportunities from the Oracle API."""
    o = Oracle(oracle_url)
    data = o.work(src=source, skill=skill, min_reward=min_reward, limit=limit)

    opps = []
    for item in data.get("work", []):
        extra = item.get("extra", {})
        if isinstance(extra, str):
            try: extra = json.loads(extra)
            except: extra = {}

        opps.append(Opportunity(
            id=item.get("id", ""),
            title=item.get("title", ""),
            description=item.get("desc", ""),
            source=item.get("src", ""),
            url=item.get("url", ""),
            category=item.get("cat", ""),
            skills=item.get("skills", []),
            reward_usd=float(item.get("reward", 0) or 0),
            currency=item.get("currency", "USD"),
            status=item.get("status", "open"),
            posted_at=item.get("posted", ""),
            extra=extra,
        ))
    return opps


def fetch_forecasting(limit: int = 20) -> list[Opportunity]:
    """Fetch Metaculus forecasting opportunities."""
    return fetch_from_oracle(source="metaculus", limit=limit)


def fetch_coding(limit: int = 20) -> list[Opportunity]:
    """Fetch coding/bounty opportunities."""
    opps = []
    for src in ["github", "bountybook"]:
        opps.extend(fetch_from_oracle(source=src, limit=limit))
    return opps


def fetch_all(limit_per_source: int = 10) -> list[Opportunity]:
    """Fetch from all Oracle sources."""
    all_opps = []
    all_opps.extend(fetch_from_oracle(limit=limit_per_source))
    return all_opps


def save_opportunities(opps: list[Opportunity], path: str = "/root/mwgym/data/opportunities.json"):
    from pathlib import Path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    data = [o.to_dict() for o in opps]
    Path(path).write_text(json.dumps(data, indent=2, default=str))
    return path


def load_opportunities(path: str = "/root/mwgym/data/opportunities.json") -> list[Opportunity]:
    from pathlib import Path
    p = Path(path)
    if not p.exists():
        return []
    data = json.loads(p.read_text())
    return [Opportunity(**{k: v for k, v in d.items() if k in Opportunity.__dataclass_fields__}) for d in data]

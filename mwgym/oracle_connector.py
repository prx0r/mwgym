"""Oracle Connector — fetch real opportunities, normalize to MWGym tasks.

Sources: bountybook, github bounties, manual entries
Output: task instruction + metadata for MWGym execution
"""
from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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
    fetched_at: float = field(default_factory=time.time)

    def to_task(self) -> str:
        """Convert to MWGym task instruction."""
        task = f"Task: {self.title}\n\n"
        task += f"Description: {self.description}\n\n"
        if self.skills:
            task += f"Required skills: {', '.join(self.skills)}\n\n"
        task += "Requirements:\n"
        task += "- Implement the solution in Python\n"
        task += "- Write code to a .py file\n"
        task += "- Code must be runnable (no syntax errors)\n"
        task += "- Include necessary imports\n\n"
        task += "Return a JSON ActionBundle:\n"
        task += '{"status": "complete", "writes": [{"path": "solution.py", "content": "..."}], "notes": "..."}'
        return task

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


def _get(url: str, timeout: int = 15) -> Any:
    try:
        req = urllib.request.Request(url, headers={
            "Accept": "application/json",
            "User-Agent": "MWGym/1.0",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"  Fetch error: {e}")
        return None


def fetch_bountybook(limit: int = 20) -> list[Opportunity]:
    """Fetch from bountybook API."""
    data = _get(f"https://api.bountybook.ai/jobs?limit={limit}")
    if not data:
        return []

    opps = []
    for j in data.get("jobs", []):
        opps.append(Opportunity(
            id=f"bountybook:{j.get('id', '')}",
            title=j.get("title", ""),
            description=j.get("description", "")[:500],
            source="bountybook",
            url=j.get("url", ""),
            category=j.get("category", "development"),
            skills=j.get("skills", []),
            reward_usd=float(j.get("reward", 0) or 0),
            currency=j.get("currency", "USD"),
            status=j.get("status", "open"),
            posted_at=j.get("posted_at", ""),
        ))
    return opps


def fetch_github_bounties(limit: int = 20) -> list[Opportunity]:
    """Fetch from GitHub bounty issues."""
    data = _get(f"https://api.github.com/search/issues?q=label:bounty+is:open+is:issue&per_page={limit}")
    if not data:
        return []

    opps = []
    for item in data.get("items", [])[:limit]:
        labels = [l.get("name", "") for l in item.get("labels", [])]
        reward = 0.0
        for l in labels:
            if "$" in l:
                try:
                    reward = float(l.replace("$", "").replace(",", ""))
                except: pass

        opps.append(Opportunity(
            id=f"github:{item.get('number', '')}",
            title=item.get("title", ""),
            description=item.get("body", "")[:500] or "",
            source="github",
            url=item.get("html_url", ""),
            category="development",
            skills=[l for l in labels if l not in ["bounty", "enhancement", "bug"]],
            reward_usd=reward,
            currency="USD",
            status="open",
            posted_at=item.get("created_at", ""),
        ))
    return opps


def fetch_local_tasks() -> list[Opportunity]:
    """Load local submission tasks as opportunities."""
    tasks_dir = Path("/root/mwgym/datasets/submissions-v1")
    opps = []
    if not tasks_dir.exists():
        return opps

    for task_dir in sorted(tasks_dir.iterdir()):
        if not task_dir.is_dir():
            continue
        instruction_file = task_dir / "instruction.md"
        if instruction_file.exists():
            instruction = instruction_file.read_text()
            title = instruction.split("\n")[0][:80]
            opps.append(Opportunity(
                id=f"local:{task_dir.name}",
                title=title,
                description=instruction,
                source="local",
                category="development",
                skills=["python"],
                reward_usd=0.0,
                status="open",
            ))
    return opps


def fetch_all(limit_per_source: int = 10) -> list[Opportunity]:
    """Fetch from all sources, deduplicate."""
    all_opps = []

    # Local tasks first (always available)
    local = fetch_local_tasks()
    all_opps.extend(local)
    print(f"  Local: {len(local)} tasks")

    # Bountybook
    try:
        bb = fetch_bountybook(limit_per_source)
        all_opps.extend(bb)
        print(f"  Bountybook: {len(bb)} opportunities")
    except: pass

    # GitHub
    try:
        gh = fetch_github_bounties(limit_per_source)
        all_opps.extend(gh)
        print(f"  GitHub: {len(gh)} bounties")
    except: pass

    # Deduplicate by title similarity
    seen = set()
    unique = []
    for opp in all_opps:
        key = opp.title.lower().strip()[:50]
        if key not in seen:
            seen.add(key)
            unique.append(opp)

    return unique


def save_opportunities(opps: list[Opportunity], path: str = "/root/mwgym/data/opportunities.json"):
    """Save fetched opportunities."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    data = [o.to_dict() for o in opps]
    Path(path).write_text(json.dumps(data, indent=2, default=str))
    return path


def load_opportunities(path: str = "/root/mwgym/data/opportunities.json") -> list[Opportunity]:
    """Load saved opportunities."""
    p = Path(path)
    if not p.exists():
        return []
    data = json.loads(p.read_text())
    return [Opportunity(**{k: v for k, v in d.items() if k in Opportunity.__dataclass_fields__}) for d in data]

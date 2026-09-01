"""Metaculus Adapter — forecasting opportunities for MWGym campaigns.

Connects Oracle (which has Metaculus data) → MWGym → Metaculus API.
"""
from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from typing import Any


METACULUS_API = "https://www.metaculus.com/api2"
METACULUS_API_V1 = "https://www.metaculus.com/api"


@dataclass
class ForecastQuestion:
    """A Metaculus question ready for forecasting."""
    question_id: int
    title: str
    question_type: str  # binary, numeric, multiple_choice
    status: str
    description: str = ""
    community_prediction: float | None = None
    nr_forecasters: int = 0
    close_time: str = ""
    resolve_time: str = ""
    url: str = ""
    tournaments: list[str] = None

    def __post_init__(self):
        if self.tournaments is None:
            self.tournaments = []


class MetaculusClient:
    """Thin client for Metaculus API."""

    def __init__(self, token: str = ""):
        self.token = token or os.environ.get("METACULUS_API_KEY", "")
        self._headers = {
            "Authorization": f"Token {self.token}",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        }

    def _get(self, path: str, params: dict = None) -> dict | None:
        url = f"{METACULUS_API}{path}"
        if params:
            query = "&".join(f"{k}={v}" for k, v in params.items() if v)
            if query:
                url += f"?{query}"
        try:
            req = urllib.request.Request(url, headers=self._headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read())
        except Exception as e:
            return {"error": str(e)}

    def _post(self, path: str, data: dict) -> dict | None:
        url = f"{METACULUS_API}{path}"
        body = json.dumps(data).encode()
        try:
            req = urllib.request.Request(url, data=body, headers={
                **self._headers, "Content-Type": "application/json"
            }, method="POST")
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read())
        except Exception as e:
            return {"error": str(e)}

    def list_questions(self, status: str = "open", qtype: str = "binary",
                       limit: int = 50) -> list[ForecastQuestion]:
        """List questions from Metaculus."""
        data = self._get("/questions/", {"status": status, "type": qtype, "limit": limit})
        if not data or "results" not in data:
            return []

        questions = []
        for q in data["results"]:
            qdata = q.get("question", {})
            projects = q.get("projects", {})
            tournaments = []
            for ptype in ("leaderboard_tag", "site_main"):
                for p in projects.get(ptype, []):
                    tournaments.append(p.get("name", ""))

            questions.append(ForecastQuestion(
                question_id=q["id"],
                title=q.get("title", ""),
                question_type=qdata.get("type", "binary"),
                status=q.get("status", ""),
                description=(q.get("description", "") or "")[:500],
                nr_forecasters=q.get("nr_forecasters", 0),
                close_time=q.get("actual_close_time") or q.get("scheduled_close_time") or "",
                resolve_time=q.get("actual_resolve_time") or q.get("scheduled_resolve_time") or "",
                url=f"https://www.metaculus.com/questions/{q['id']}/",
                tournaments=tournaments,
            ))
        return questions

    def get_question(self, question_id: int) -> dict | None:
        """Get full question detail."""
        return self._get(f"/questions/{question_id}/")

    def submit_forecast(self, question_id: int, probability: float) -> dict | None:
        """Submit a binary forecast."""
        return self._post(f"/questions/{question_id}/forecast/", {
            "probability": max(0.01, min(0.99, probability)),
        })

    def submit_numeric_forecast(self, question_id: int, cdf_201: list[float]) -> dict | None:
        """Submit a numeric CDF forecast (201 points)."""
        return self._post(f"/questions/{question_id}/forecast/", {
            "continuous_cdf": cdf_201,
        })

    def get_my_forecasts(self, question_id: int) -> dict | None:
        """Get my previous forecasts on a question."""
        return self._get(f"/questions/{question_id}/forecasts/")


def get_forecasting_opportunities(oracle_url: str = "http://localhost:8788",
                                   limit: int = 20) -> list[dict]:
    """Get Metaculus opportunities from the Oracle."""
    try:
        url = f"{oracle_url}/work?src=metaculus&limit={limit}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return data.get("work", [])
    except:
        return []

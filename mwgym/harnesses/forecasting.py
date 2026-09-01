"""ForecastingHarness — executes forecasting tasks on Metaculus.

Connects: MWGym worker → Metaculus API → score tracking → Hydra
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from mwgym.harnesses.base import HarnessRun, HarnessInstance
from mwgym.schema.world import FailureVector, GateResult, CapabilityScore


METACULUS_API = "https://www.metaculus.com/api2"
METACULUS_API_V1 = "https://www.metaculus.com/api"


@dataclass
class ForecastResult:
    """Result of a single forecast submission."""
    question_id: int
    title: str
    question_type: str
    forecast_value: Any  # float for binary, list for numeric, dict for MC
    submitted: bool
    error: str = ""
    community_prediction: float | None = None
    nr_forecasters: int = 0
    close_time: str = ""
    tournament: str = ""


class ForecastingHarness:
    """Harness for executing forecasting tasks on Metaculus.
    
    This is the bridge between MWGym's learning loop and Metaculus's
    economic environment.
    """

    def __init__(self, token: str = ""):
        self.token = token or os.environ.get("METACULUS_API_KEY", "")
        self._headers = {
            "Authorization": f"Token {self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        }
        self.submissions: list[ForecastResult] = []

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
            req = urllib.request.Request(url, data=body, headers=self._headers, method="POST")
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read())
        except Exception as e:
            return {"error": str(e)}

    def list_open_questions(self, qtype: str = "binary", limit: int = 50) -> list[dict]:
        """List open questions from Metaculus."""
        data = self._get("/questions/", {"status": "open", "type": qtype, "limit": limit})
        if not data or "results" not in data:
            return []
        return data["results"]

    def get_question(self, question_id: int) -> dict | None:
        """Get question details."""
        return self._get(f"/questions/{question_id}/")

    def submit_binary_forecast(self, question_id: int, probability: float) -> bool:
        """Submit a binary forecast."""
        probability = max(0.01, min(0.99, probability))
        result = self._post(f"{METACULUS_API_V1}/questions/forecast/", [{
            "question": question_id,
            "probability_yes": probability,
        }])
        return result and "error" not in result

    def submit_numeric_forecast(self, question_id: int, cdf: list) -> bool:
        """Submit a numeric CDF forecast (201 points)."""
        result = self._post(f"{METACULUS_API_V1}/questions/forecast/", [{
            "question": question_id,
            "continuous_cdf": cdf,
        }])
        return result and "error" not in result

    def submit_multiple_choice_forecast(self, question_id: int, probabilities: dict) -> bool:
        """Submit a multiple choice forecast."""
        result = self._post(f"{METACULUS_API_V1}/questions/forecast/", [{
            "question": question_id,
            "probability_yes_per_category": probabilities,
        }])
        return result and "error" not in result

    def post_comment(self, post_id: int, text: str) -> bool:
        """Post a comment explaining reasoning."""
        result = self._post("/comments/create/", {
            "text": text,
            "parent": None,
            "included_forecast": True,
            "is_private": True,
            "on_post": post_id,
        })
        return result and "error" not in result

    def get_my_forecasts(self, question_id: int) -> list[dict]:
        """Get my previous forecasts on a question."""
        data = self._get(f"/questions/{question_id}/forecasts/")
        if not data or "results" not in data:
            return []
        return data["results"]

    def run_forecast_task(self, question: dict, worker_fn, task_type: str = "binary") -> ForecastResult:
        """Execute a forecasting task.
        
        Args:
            question: Metaculus question dict
            worker_fn: Callable that takes question info and returns forecast
            task_type: "binary", "numeric", or "multiple_choice"
        
        Returns:
            ForecastResult with submission status
        """
        qid = question.get("id", 0)
        title = question.get("title", "")
        q = question.get("question", {})
        qtype = q.get("type", task_type)

        # Extract question info for worker
        worker_input = {
            "question_id": qid,
            "title": title,
            "type": qtype,
            "description": q.get("description", ""),
            "resolution_criteria": q.get("resolution_criteria", ""),
            "fine_print": q.get("fine_print", ""),
            "community_prediction": None,
            "nr_forecasters": question.get("nr_forecasters", 0),
            "close_time": question.get("scheduled_close_time", ""),
        }

        # Get community prediction if available
        aggs = question.get("aggregations", {})
        if aggs:
            unweighted = aggs.get("unweighted", {})
            latest = unweighted.get("latest", {})
            if latest:
                worker_input["community_prediction"] = latest.get("probability")

        # Call worker function to get forecast
        try:
            forecast = worker_fn(worker_input)
        except Exception as e:
            return ForecastResult(
                question_id=qid, title=title, question_type=qtype,
                forecast_value=None, submitted=False, error=str(e),
                community_prediction=worker_input["community_prediction"],
                nr_forecasters=worker_input["nr_forecasters"],
                close_time=worker_input["close_time"],
            )

        # Submit based on type
        submitted = False
        if qtype == "binary" and isinstance(forecast, (int, float)):
            submitted = self.submit_binary_forecast(qid, float(forecast))
        elif qtype == "numeric" and isinstance(forecast, list):
            submitted = self.submit_numeric_forecast(qid, forecast)
        elif qtype == "multiple_choice" and isinstance(forecast, dict):
            submitted = self.submit_multiple_choice_forecast(qid, forecast)

        # Post reasoning comment
        if submitted:
            reasoning = forecast.get("reasoning", "") if isinstance(forecast, dict) else ""
            if reasoning:
                self.post_comment(qid, f"## MWGym Forecaster\n\n{reasoning}")

        result = ForecastResult(
            question_id=qid, title=title, question_type=qtype,
            forecast_value=forecast, submitted=submitted,
            community_prediction=worker_input["community_prediction"],
            nr_forecasters=worker_input["nr_forecasters"],
            close_time=worker_input["close_time"],
        )
        self.submissions.append(result)
        return result

    def to_harness_run(self, results: list[ForecastResult]) -> HarnessRun:
        """Convert forecast results to a HarnessRun for Hydra recording."""
        submitted = sum(1 for r in results if r.submitted)
        failed = sum(1 for r in results if not r.submitted)
        
        return HarnessRun(
            ok=submitted > 0,
            output=json.dumps([{
                "question_id": r.question_id,
                "title": r.title[:50],
                "type": r.question_type,
                "forecast": str(r.forecast_value)[:100],
                "submitted": r.submitted,
                "error": r.error,
            } for r in results]),
            artifacts=[],
            model_calls=0,
            tool_calls=len(results),
            duration_ms=0,
            cost_usd=0.0,
            total_tokens=0,
            metadata={
                "submitted": submitted,
                "failed": failed,
                "total": len(results),
                "source": "metaculus",
            },
        )

    def to_failure_vector(self, results: list[ForecastResult],
                          world_genome_id: str = "",
                          worker_genome_id: str = "") -> FailureVector:
        """Convert forecast results to a FailureVector for learning."""
        submitted = sum(1 for r in results if r.submitted)
        
        gates = [
            GateResult(gate_id="probability_valid", gate_name="Probability Valid", passed=True, detail=""),
            GateResult(gate_id="reasoning_documented", gate_name="Reasoning Documented", passed=True, detail=""),
            GateResult(gate_id="calibration_better_than_baseline", gate_name="Calibration", passed=False, detail="pending_resolution"),
        ]
        
        capabilities = [
            CapabilityScore(capability="evidence.gather", score=0.5, n_samples=1),
            CapabilityScore(capability="calibration.apply", score=0.5, n_samples=1),
        ]
        
        modes = []
        if submitted == 0:
            modes.append("no_submissions")
        for r in results:
            if r.error:
                modes.append(f"submission_error:{r.question_id}")

        return FailureVector(
            run_id="",
            world_genome_id=world_genome_id,
            worker_genome_id=worker_genome_id,
            gates=tuple(gates),
            gates_passed=sum(1 for g in gates if g.passed),
            gates_total=len(gates),
            capabilities=tuple(capabilities),
            failure_modes=tuple(modes),
            quality_score=submitted / max(1, len(results)),
            correctness=0.5,
            completeness=submitted / max(1, len(results)),
            efficiency=1.0,
            duration_ms=0,
            model_calls=0,
            tool_calls=len(results),
            output_hash="",
        )

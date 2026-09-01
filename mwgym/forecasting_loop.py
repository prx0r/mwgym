"""ForecastingLoop — the Metaculus learning loop.

Connects: Oracle → MWGym worker → Metaculus → Hydra → learn → repeat

This is the bridge between "we can submit forecasts" and "we learn from
what works and get better over time."
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from mwgym.metaculus import MetaculusClient, ForecastQuestion
from mwgym.harnesses.forecasting import ForecastingHarness, ForecastResult


@dataclass
class ForecastingLoop:
    """The Metaculus learning loop.
    
    Flow:
    1. Fetch questions from Metaculus
    2. Generate forecasts using worker function
    3. Submit to Metaculus
    4. Record in Hydra
    5. When questions resolve, record outcomes
    6. Extract lessons
    7. Feed lessons back to worker
    8. Repeat
    """
    
    client: MetaculusClient
    harness: ForecastingHarness
    hydra: object  # TODO: Wire real HydraDB client
    worker_fn: Callable[[dict], Any] = None  # question -> forecast
    worker_genome_id: str = "metaculus-v1"
    
    def __post_init__(self):
        if not self.client.token:
            self.client = MetaculusClient(os.environ.get("METACULUS_API_KEY", ""))
        if not self.harness.token:
            self.harness = ForecastingHarness(os.environ.get("METACULUS_API_KEY", ""))
    
    def run_batch(self, questions: list = None, limit: int = 20,
                  qtype: str = "binary") -> dict:
        """Run a batch of forecasts.
        
        Args:
            questions: Optional list of question dicts or ForecastQuestion objects
            limit: Max questions to forecast
            qtype: Question type filter
        
        Returns:
            Summary of batch run
        """
        # Fetch questions if not provided
        if not questions:
            questions = self.client.list_questions(status="open", qtype=qtype, limit=limit)
        
        if not questions:
            return {"error": "no questions available"}
        
        session_id = str(uuid.uuid4())[:8]
        run_id = f"forecast-{session_id}"
        
        print(f"🎯 Forecasting session {session_id}: {len(questions)} questions")
        
        # Record session start
        self.hydra.record_forecast_session(
            session_id=session_id,
            worker_genome_id=self.worker_genome_id,
            run_id=run_id,
            n_questions=len(questions),
        )
        
        results = []
        for q in questions:
            # Handle both dict and ForecastQuestion objects
            if hasattr(q, 'question_id'):
                qid = q.question_id
                title = q.title[:50] if q.title else ""
                q_dict = {
                    "id": q.question_id,
                    "title": q.title,
                    "question": {"type": q.question_type},
                    "nr_forecasters": q.nr_forecasters,
                    "scheduled_close_time": q.close_time,
                    "aggregations": {},
                }
            else:
                qid = q.get("id", 0)
                title = q.get("title", "")[:50]
                q_dict = q
            
            # Skip if already forecasted
            existing = self.hydra.get_unresolved_forecasts()
            if any(f["question_id"] == qid for f in existing):
                print(f"  ⏭️  [{qid}] {title} (already forecasted)")
                continue
            
            # Run forecast
            result = self.harness.run_forecast_task(q_dict, self.worker_fn, qtype)
            results.append(result)
            
            # Record in Hydra
            self.hydra.record_forecast(
                question_id=qid,
                question_title=title,
                question_type=qtype,
                forecast_value=result.forecast_value,
                submitted=result.submitted,
                community_prediction=result.community_prediction,
                nr_forecasters=result.nr_forecasters,
                close_time=result.close_time,
                worker_genome_id=self.worker_genome_id,
                run_id=run_id,
            )
            
            status = "✅" if result.submitted else "❌"
            forecast_str = str(result.forecast_value)[:20]
            print(f"  {status} [{qid}] {title} → {forecast_str}")
            
            # Rate limit
            time.sleep(0.5)
        
        # Update session
        submitted = sum(1 for r in results if r.submitted)
        self.hydra.update_forecast_session(
            session_id=session_id,
            n_submitted=submitted,
        )
        
        # Record run in Hydra
        harness_run = self.harness.to_harness_run(results)
        fv = self.harness.to_failure_vector(results, worker_genome_id=self.worker_genome_id)
        self.hydra.record_run(
            run_id=run_id,
            worker_genome_id=self.worker_genome_id,
            family_id="forecasting.binary",
            harness="forecasting",
            model="metaculus-worker",
            success=submitted > 0,
            quality_score=submitted / max(1, len(results)),
            failure_vector=fv,
        )
        
        summary = {
            "session_id": session_id,
            "total": len(questions),
            "forecasted": len(results),
            "submitted": submitted,
            "failed": len(results) - submitted,
        }
        
        print(f"\n📊 Summary: {summary}")
        return summary
    
    def check_resolutions(self) -> dict:
        """Check for resolved questions and record outcomes.
        
        This is the learning part — when questions resolve, we compare
        our forecasts to the actual outcome and extract lessons.
        """
        unresolved = self.hydra.get_unresolved_forecasts(limit=100)
        
        if not unresolved:
            return {"message": "no unresolved forecasts"}
        
        resolved_count = 0
        beat_count = 0
        lessons = []
        
        for f in unresolved:
            qid = f["question_id"]
            
            # Check if question resolved
            question = self.client.get_question(qid)
            if not question or not question.get("resolved"):
                continue
            
            resolution = question.get("resolution")
            if resolution is None:
                continue
            
            # Get our forecast and community forecast
            our_forecast = json.loads(f["forecast_value"]) if f["forecast_value"] else 0.5
            community_forecast = f["community_prediction"] or 0.5
            
            # Record resolution
            result = self.hydra.record_forecast_resolution(
                question_id=qid,
                resolution_value=str(resolution),
                our_forecast=float(our_forecast) if isinstance(our_forecast, (int, float)) else 0.5,
                community_forecast=float(community_forecast),
            )
            
            resolved_count += 1
            if result["beat_community"]:
                beat_count += 1
            
            # Extract lesson
            lesson = self._extract_lesson(f, result)
            if lesson:
                lessons.append(lesson)
                self.hydra.record_forecast_lesson(
                    question_id=qid,
                    lesson_type=lesson["type"],
                    lesson=lesson["lesson"],
                    evidence=lesson["evidence"],
                    worker_genome_id=self.worker_genome_id,
                    confidence=lesson["confidence"],
                )
            
            print(f"  {'✅' if result['beat_community'] else '❌'} [{qid}] "
                  f"resolved={resolution} our={our_forecast} comm={community_forecast}")
        
        stats = self.hydra.get_forecast_stats(self.worker_genome_id)
        
        summary = {
            "checked": len(unresolved),
            "newly_resolved": resolved_count,
            "beat_community": beat_count,
            "lessons_extracted": len(lessons),
            "stats": stats,
        }
        
        print(f"\n📊 Resolution check: {summary}")
        return summary
    
    def _extract_lesson(self, forecast: dict, resolution: dict) -> dict | None:
        """Extract a learning lesson from a resolved forecast."""
        our = json.loads(forecast["forecast_value"]) if forecast["forecast_value"] else 0.5
        community = forecast["community_prediction"] or 0.5
        resolved_value = resolution.get("resolution", "")
        
        if not resolved_value:
            return None
        
        # Binary resolution
        actual = 1.0 if resolved_value in ("Yes", "1", "True", "yes", "true") else 0.0
        
        our_err = abs(float(our) - actual) if isinstance(our, (int, float)) else 0.5
        comm_err = abs(community - actual)
        
        if our_err < comm_err:
            # We beat community — what did we do right?
            return {
                "type": "calibration_success",
                "lesson": f"Beat community by {comm_err - our_err:.3f}. "
                         f"Our forecast {our} was closer to {actual} than community {community}.",
                "evidence": {"our": our, "community": community, "actual": actual},
                "confidence": 0.6,
            }
        elif our_err > comm_err + 0.1:
            # We did significantly worse
            if abs(our - community) < 0.1:
                return {
                    "type": "calibration_weak",
                    "lesson": f"Forecast {our} close to community {community} but both wrong. "
                             f"Need better domain knowledge for this question type.",
                    "evidence": {"our": our, "community": community, "actual": actual},
                    "confidence": 0.7,
                }
            else:
                return {
                    "type": "overconfidence",
                    "lesson": f"Forecast {our} significantly off from {actual}. "
                             f"Community was {community}. Update too aggressive?",
                    "evidence": {"our": our, "community": community, "actual": actual},
                    "confidence": 0.8,
                }
        
        return None
    
    def get_recommended_strategy(self) -> dict:
        """Get recommended forecasting strategy based on learned lessons."""
        lessons = self.hydra.get_forecast_lessons(limit=50)
        stats = self.hydra.get_forecast_stats(self.worker_genome_id)
        
        if not lessons:
            return {
                "strategy": "coverage_first",
                "reason": "no lessons yet — focus on forecasting all questions",
                "stats": stats,
            }
        
        # Analyze lesson patterns
        lesson_types = {}
        for l in lessons:
            t = l["lesson_type"]
            lesson_types[t] = lesson_types.get(t, 0) + 1
        
        recommendations = []
        
        if lesson_types.get("overconfidence", 0) > 3:
            recommendations.append("Reduce forecast extremity — stay within 0.1-0.9")
        
        if lesson_types.get("calibration_weak", 0) > 5:
            recommendations.append("Improve domain research — community is beating us consistently")
        
        if stats.get("beat_rate", 0) > 0.5:
            recommendations.append("Good calibration — maintain strategy, increase coverage")
        
        if stats.get("pending", 0) > 20:
            recommendations.append("Many pending forecasts — check for new resolutions")
        
        return {
            "strategy": "refinement" if stats.get("beat_rate", 0) > 0.4 else "coverage_first",
            "recommendations": recommendations,
            "lesson_breakdown": lesson_types,
            "stats": stats,
        }

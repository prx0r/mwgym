#!/usr/bin/env python3
"""Metaculus Loop — simple end-to-end: discover → forecast → submit → record.

Usage:
    python3 metaculus_loop.py --dry-run --limit 5
    python3 metaculus_loop.py --limit 10
    python3 metaculus_loop.py --check-scores
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/root/workerkit")

from mwgym.metaculus import MetaculusClient
from mwgym.worlds.cge_adapter import ForecastingWorld, compile_world
from mwgym.schema.world import WorldGenome

# Rate limit: 2 seconds between submissions
RATE_LIMIT_DELAY = 2.0


TOURNAMENT = int(os.environ.get("METACULUS_TOURNAMENT", "0"))  # 0 = all open questions


def simple_forecast(question: dict) -> dict:
    """Baseline forecast: use community_prediction if available, else 50%."""
    qid = question.get("id", 0)
    title = question.get("title", "")
    qdata = question.get("question", {})
    qtype = qdata.get("type", "binary")

    # Extract community prediction
    cp = 0.5
    aggs = question.get("aggregations", {})
    if aggs:
        unweighted = aggs.get("unweighted", {})
        latest = unweighted.get("latest", {})
        if latest and latest.get("probability") is not None:
            cp = latest["probability"]

    if qtype == "binary":
        return {"question_type": "binary", "probability": cp, "reasoning": f"Baseline: community prediction = {cp:.2f}"}
    elif qtype == "numeric":
        center = cp * 1000 if cp else 500
        cdf = [1.0 / (1.0 + math.exp(-(x - center) / 100)) for x in range(201)]
        return {"question_type": "numeric", "cdf_201": cdf, "reasoning": f"Baseline: centered on {center:.0f}"}
    else:
        return {"question_type": "multiple_choice", "probabilities": {}, "reasoning": "Baseline: equal probability"}


def run_batch(client: MetaculusClient, limit: int = 10, dry_run: bool = False) -> list[dict]:
    """Discover questions, forecast, optionally submit."""
    # Discover
    print(f"Fetching up to {limit} open questions from tournament {TOURNAMENT}...")
    questions = []
    offset = 0
    while len(questions) < limit:
        params = {
            "status": "open",
            "limit": min(50, limit - len(questions)),
            "offset": offset,
        }
        if TOURNAMENT:
            params["project"] = TOURNAMENT
        data = client._get("/questions/", params)
        if not data or "results" not in data:
            break
        questions.extend(data["results"])
        if not data.get("next"):
            break
        offset += 50

    print(f"Found {len(questions)} questions")

    results = []
    for q in questions:
        qid = q.get("id", 0)
        title = q.get("title", "")[:60]
        qtype = q.get("question", {}).get("type", "binary")

        # Generate forecast
        forecast = simple_forecast(q)

        # Determine actual question type
        qtype_actual = qtype

        # Create CGE world
        cp = 0.5
        aggs = q.get("aggregations", {})
        if aggs:
            unweighted = aggs.get("unweighted", {})
            latest = unweighted.get("latest", {})
            if latest and latest.get("probability") is not None:
                cp = latest["probability"]

        genome = WorldGenome(
            id=f"forecast-q{qid}",
            family_id=f"forecasting.{qtype_actual}",
            structure={"question_type": qtype_actual, "question_id": qid},
            information={
                "community_prediction": cp,
                "question_text": title,
                "nr_forecasters": q.get("nr_forecasters", 0),
            },
            resources={"budget_usd": 0.01},
        )
        world = compile_world(genome)
        state = world.reset(seed=qid)
        score = world.score(state)

        # Submit
        if dry_run:
            status = "DRY_RUN"
            print(f"  [DRY] q{qid} ({qtype_actual}): {forecast.get('probability', '?')} — {title}")
        else:
            _headers = {
                "Authorization": f"Token {client.token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            }
            if qtype_actual == "binary":
                p = max(0.01, min(0.99, forecast.get("probability", 0.5)))
                payload = [{"question": qid, "probability_yes": p, "confidence": None}]
            elif qtype_actual == "numeric":
                # Generate a simple CDF centered on 500
                import math
                cdf = [1.0 / (1.0 + math.exp(-(x - 500) / 100)) for x in range(201)]
                payload = [{"question": qid, "continuous_cdf": cdf}]
            elif qtype_actual == "multiple_choice":
                payload = [{"question": qid, "probability_yes_per_category": {}}]
            else:
                payload = [{"question": qid, "probability_yes": 0.5, "confidence": None}]
            body = json.dumps(payload).encode()
            import urllib.request as _urllib
            req = _urllib.Request(
                "https://www.metaculus.com/api/questions/forecast/",
                data=body, headers=_headers, method="POST"
            )
            try:
                with _urllib.urlopen(req, timeout=15) as resp:
                    result = json.loads(resp.read())
                    status = "submitted" if isinstance(result, dict) and "error" not in result else "failed"
                    if status == "failed":
                        err = result.get("error", str(result))
                        print(f"  ERROR: {err}")
                        if "not scheduled" in str(err).lower() or "already closed" in str(err).lower():
                            status = "skipped"
            except Exception as e:
                body_err = ""
                if hasattr(e, 'read'):
                    body_err = e.read().decode()[:200]
                status = "failed"
                if "429" in str(e) or "Too Many Requests" in body_err:
                    print(f"  RATE LIMITED, waiting 10s...")
                    time.sleep(10)
                elif "not scheduled" in body_err.lower() or "already closed" in body_err.lower():
                    status = "skipped"
                elif "continuous_cdf" in body_err.lower() or "probability_yes_per_category" in body_err.lower():
                    # Wrong question type - try to get correct type from detail
                    try:
                        detail = client._get(f"/questions/{qid}/")
                        if detail and "question" in detail:
                            real_type = detail["question"].get("type", "binary")
                            if real_type == "numeric":
                                import math as _math
                                cdf = [1.0 / (1.0 + _math.exp(-(x - 500) / 100)) for x in range(201)]
                                payload = [{"question": qid, "continuous_cdf": cdf}]
                            elif real_type == "multiple_choice":
                                payload = [{"question": qid, "probability_yes_per_category": {}}]
                            body = json.dumps(payload).encode()
                            req2 = _urllib.Request(
                                "https://www.metaculus.com/api/questions/forecast/",
                                data=body, headers=_headers, method="POST"
                            )
                            with _urllib.urlopen(req2, timeout=15) as resp2:
                                result2 = json.loads(resp2.read())
                                status = "submitted" if isinstance(result2, dict) and "error" not in result2 else "failed"
                                if status == "submitted":
                                    print(f"  RETRY OK as {real_type}")
                    except Exception:
                        pass
                print(f"  ERROR: {e} {body_err}")
            time.sleep(RATE_LIMIT_DELAY)
            print(f"  [{status.upper()}] q{qid} ({qtype}): {forecast.get('probability', '?')} — {title}")
            time.sleep(1)  # rate limit

        results.append({
            "question_id": qid,
            "title": title,
            "type": qtype,
            "forecast": forecast.get("probability") if qtype == "binary" else forecast.get("question_type"),
            "community_prediction": cp,
            "status": status,
            "world_score": score.get("log_score") if score else None,
        })

    return results


def check_scores(client: MetaculusClient) -> list[dict]:
    """Check scores on previously forecasted questions."""
    # Get my forecasts
    data = client._get("/questions/", {"status": "resolved", "limit": 20})
    if not data or "results" not in data:
        print("No resolved questions found")
        return []

    results = []
    for q in data["results"]:
        qid = q.get("id", 0)
        title = q.get("title", "")[:60]
        resolution = q.get("resolution")
        print(f"  q{qid}: resolution={resolution} — {title}")
        results.append({"question_id": qid, "resolution": resolution, "title": title})
    return results


def main():
    parser = argparse.ArgumentParser(description="Metaculus forecasting loop")
    parser.add_argument("--limit", type=int, default=10, help="Max questions to process")
    parser.add_argument("--dry-run", action="store_true", help="Don't submit, just print")
    parser.add_argument("--check-scores", action="store_true", help="Check resolved questions")
    parser.add_argument("--token", default="", help="Metaculus API token")
    args = parser.parse_args()

    token = args.token or os.environ.get("METACULUS_API_KEY", "")
    if not token:
        print("ERROR: Set METACULUS_API_KEY or pass --token")
        sys.exit(1)

    client = MetaculusClient(token=token)

    if args.check_scores:
        check_scores(client)
    else:
        results = run_batch(client, limit=args.limit, dry_run=args.dry_run)
        print(f"\nDone. {len(results)} questions processed.")
        submitted = sum(1 for r in results if r["status"] in ("submitted", "DRY_RUN"))
        print(f"  Submitted: {submitted}")
        print(f"  Failed: {len(results) - submitted}")


if __name__ == "__main__":
    main()

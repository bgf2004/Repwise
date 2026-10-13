"""Transparent observational rest guidance, without claiming a causal optimum."""

from collections import defaultdict
import math
from statistics import median

from .models import SetCreate


MIN_BUCKET_SAMPLES = 6
MIN_BUCKET_SESSIONS = 3
SUCCESS_RATE = 0.8
MIN_REST_SECONDS = 30
MAX_REST_SECONDS = 600
BUCKET_SECONDS = 30


def kilograms(weight: float, unit: str) -> float:
    return weight * 0.45359237 if unit == "lb" else weight


def recommend(history, *, exercise, weight, unit, target_reps, set_number, tempo, baseline_seconds):
    comparable = []
    excluded = 0
    for item in history:
        try:
            # Revalidate stored measurements so corrupted/imported timing never drives advice.
            SetCreate.model_validate({key: item[key] for key in SetCreate.model_fields if key in item})
            rest = item["rest_before_seconds"]
            matches = (
                isinstance(item.get("workout_id"), str) and bool(item["workout_id"])
                and set_number > 1
                and item["set_number"] == set_number
                and item["exercise"] == exercise
                and abs(kilograms(item["weight"], item["unit"]) - kilograms(weight, unit)) <= 0.03
                and item["target_reps"] == target_reps
                and item["tempo"] == tempo
                and isinstance(rest, (int, float)) and math.isfinite(rest)
                and MIN_REST_SECONDS <= rest <= MAX_REST_SECONDS
            )
        except (KeyError, TypeError, ValueError):
            matches = False
        if matches:
            comparable.append(item)
        else:
            excluded += 1

    groups = defaultdict(list)
    for item in comparable:
        bucket = int((item["rest_before_seconds"] + BUCKET_SECONDS / 2) // BUCKET_SECONDS) * BUCKET_SECONDS
        groups[bucket].append(item)
    buckets = []
    eligible = []
    for rest, items in sorted(groups.items()):
        successes = sum(item["reps"] >= item["target_reps"] for item in items)
        rate = successes / len(items)
        buckets.append({
            "rest_seconds": rest,
            "samples": len(items),
            "success_rate": round(rate, 4),
            "median_reps": median(item["reps"] for item in items),
        })
        sessions = len({item["workout_id"] for item in items})
        if len(items) >= MIN_BUCKET_SAMPLES and sessions >= MIN_BUCKET_SESSIONS and rate >= SUCCESS_RATE:
            eligible.append(rest)

    sample_count = len(comparable)
    session_count = len({item["workout_id"] for item in comparable})
    if eligible:
        chosen = min(eligible)
        low = max(MIN_REST_SECONDS, chosen - BUCKET_SECONDS // 2)
        high = min(MAX_REST_SECONDS, chosen + BUCKET_SECONDS // 2)
        status = "personalized"
        explanation = (
            f"Your shortest observed rest bucket meeting the rep target at least {SUCCESS_RATE:.0%} of the time "
            f"with at least {MIN_BUCKET_SAMPLES} sets across {MIN_BUCKET_SESSIONS} workouts is around {chosen} seconds. "
            "Compared exercise, external load, target reps, set number, and intended tempo. "
            "This is an association in your history, not proof of an optimal rest time; effort and workout order may differ."
        )
    else:
        chosen = baseline_seconds
        low = high = baseline_seconds
        status = "learning" if sample_count else "baseline"
        explanation = (
            f"Using your chosen {baseline_seconds}-second timer. "
            f"A suggestion needs at least {MIN_BUCKET_SAMPLES} comparable sets in a 30-second rest bucket "
            f"across {MIN_BUCKET_SESSIONS} workouts, with at least {SUCCESS_RATE:.0%} meeting the rep target. "
            "Only the same exercise, external load, target reps, set number, and intended tempo are compared."
        )
        if set_number == 1:
            explanation = "First sets have no comparable between-set rest history. " + explanation
    return {
        "recommended_seconds": chosen,
        "range_low": low,
        "range_high": high,
        "status": status,
        "sample_count": sample_count,
        "session_count": session_count,
        "explanation": explanation,
        "buckets": buckets,
        "excluded_count": excluded,
    }

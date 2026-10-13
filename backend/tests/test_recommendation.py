from datetime import datetime, timedelta, timezone
import unittest
from uuid import uuid4

from backend.recommendation import recommend


class RecommendationTests(unittest.TestCase):
    def item(self, **changes):
        start = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
        item = {
            "id": str(uuid4()), "workout_id": str(uuid4()), "exercise": "squat",
            "weight": 100, "unit": "lb", "target_reps": 10, "reps": 10, "set_number": 2,
            "started_at": start.isoformat(), "ended_at": (start + timedelta(seconds=40)).isoformat(),
            "rest_before_seconds": 120, "tempo": "natural", "effort_rir": None,
            "source": "manual", "rep_details": [], "notes": "",
        }
        item.update(changes)
        return item

    def result(self, history, **changes):
        query = dict(exercise="squat", weight=100, unit="lb", target_reps=10,
                     set_number=2, tempo="natural", baseline_seconds=150)
        query.update(changes)
        return recommend(history, **query)

    def test_no_history_uses_chosen_baseline(self):
        result = self.result([])
        self.assertEqual(result["status"], "baseline")
        self.assertEqual(result["recommended_seconds"], 150)
        self.assertEqual(result["buckets"], [])

    def test_small_sample_does_not_claim_personalization(self):
        result = self.result([self.item() for _ in range(5)])
        self.assertEqual(result["status"], "learning")
        self.assertEqual(result["recommended_seconds"], 150)
        self.assertEqual(result["sample_count"], 5)

    def test_successes_from_one_session_are_not_sufficient(self):
        result = self.result([self.item(workout_id="same-workout") for _ in range(10)])
        self.assertEqual(result["status"], "learning")
        self.assertEqual(result["session_count"], 1)

    def test_equivalent_units_match_with_rounding_tolerance(self):
        result = self.result([self.item(weight=45.36, unit="kg") for _ in range(6)])
        self.assertEqual(result["status"], "personalized")
        self.assertEqual(result["sample_count"], 6)

    def test_irrelevant_sets_do_not_leak_into_evidence(self):
        changes = [
            {"exercise": "curl"}, {"weight": 101}, {"target_reps": 8}, {"set_number": 3},
            {"tempo": "controlled"}, {"rest_before_seconds": None}, {"rest_before_seconds": 10},
            {"rest_before_seconds": 700}, {"set_number": 1}, {"ended_at": "not-a-date"},
        ]
        good = [self.item(rest_before_seconds=120) for _ in range(6)]
        result = self.result(good + [self.item(**change) for change in changes])
        self.assertEqual(result["sample_count"], 6)
        self.assertEqual(result["excluded_count"], len(changes))
        self.assertEqual(len(result["buckets"]), 1)

    def test_selects_shortest_successful_observed_bucket(self):
        history = [self.item(rest_before_seconds=60, reps=6) for _ in range(6)]
        history += [self.item(rest_before_seconds=90) for _ in range(5)]
        history += [self.item(rest_before_seconds=90, reps=9)]
        history += [self.item(rest_before_seconds=150) for _ in range(6)]
        result = self.result(history)
        self.assertEqual(result["recommended_seconds"], 90)
        self.assertEqual((result["range_low"], result["range_high"]), (75, 105))
        self.assertIn("association", result["explanation"])
        self.assertAlmostEqual(result["buckets"][1]["success_rate"], 5 / 6, places=4)

    def test_many_unsuccessful_sets_preserve_baseline(self):
        result = self.result([self.item(reps=8) for _ in range(20)])
        self.assertEqual(result["status"], "learning")
        self.assertEqual(result["recommended_seconds"], 150)

    def test_first_set_never_gets_between_set_recommendation(self):
        result = self.result([self.item(set_number=1) for _ in range(8)], set_number=1)
        self.assertEqual(result["status"], "baseline")
        self.assertEqual(result["sample_count"], 0)
        self.assertIn("First sets", result["explanation"])

    def test_invalid_timing_and_missing_session_excluded(self):
        bad = self.item(source="camera", reps=1, rep_details=[{
            "index": 1, "down_seconds": 30, "up_seconds": 30,
            "total_seconds": 60, "range_degrees": 80,
        }])
        missing = self.item()
        del missing["workout_id"]
        result = self.result([bad, missing])
        self.assertEqual(result["excluded_count"], 2)
        self.assertEqual(result["status"], "baseline")


if __name__ == "__main__":
    unittest.main()

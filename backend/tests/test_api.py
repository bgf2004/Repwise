"""API integration tests use temporary SQLite files, never the user's history."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app import create_app


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database = Path(self.directory.name) / "workouts.sqlite3"
        self.client = TestClient(create_app(self.database, Path(self.directory.name) / "no-frontend"))
        self.client.__enter__()
        self.workout = self.client.post("/api/workouts", json={}).json()
        self.start = datetime.fromisoformat(self.workout["started_at"]) + timedelta(seconds=1)

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.directory.cleanup()

    def payload(self, **changes):
        value = {
            "id": str(uuid4()), "exercise": "squat", "weight": 20, "unit": "kg",
            "target_reps": 10, "reps": 10, "set_number": 1,
            "started_at": self.start.isoformat(),
            "ended_at": (self.start + timedelta(seconds=40)).isoformat(),
            "rest_before_seconds": None, "tempo": "natural", "effort_rir": None,
            "source": "manual", "rep_details": [], "notes": "",
        }
        value.update(changes)
        return value

    def save(self, payload=None):
        return self.client.post(f"/api/workouts/{self.workout['id']}/sets", json=payload or self.payload())

    def test_real_file_survives_app_restart(self):
        value = self.payload()
        self.assertEqual(self.save(value).status_code, 201)
        with TestClient(create_app(self.database)) as restarted:
            workouts = restarted.get("/api/workouts").json()
            self.assertEqual(len(workouts), 1)
            self.assertEqual(workouts[0]["sets"][0]["id"], value["id"])
            self.assertEqual(workouts[0]["sets"][0]["weight"], 20)
        self.assertTrue(self.database.is_file())

    def test_empty_database_has_no_seeded_workouts_or_recommendations(self):
        workouts = self.client.get("/api/workouts").json()
        self.assertEqual(workouts[0]["sets"], [])
        result = self.client.get("/api/recommendation", params={"exercise": "squat", "weight": 0}).json()
        self.assertEqual(result["status"], "baseline")
        self.assertEqual(result["sample_count"], 0)

    def test_retry_is_idempotent_even_after_workout_ends(self):
        value = self.payload()
        first = self.save(value).json()
        close = self.client.patch(f"/api/workouts/{self.workout['id']}", json={"ended_at": value["ended_at"]})
        self.assertEqual(close.status_code, 200)
        self.assertEqual(self.save(value).json(), first)
        self.assertEqual(len(self.client.get("/api/workouts").json()[0]["sets"]), 1)

    def test_reused_id_with_changed_payload_conflicts(self):
        value = self.payload()
        self.save(value)
        value["weight"] = 25
        response = self.save(value)
        self.assertEqual(response.status_code, 409)
        self.assertIn("different save request", response.json()["detail"])

    def test_reused_id_in_other_workout_conflicts(self):
        value = self.payload()
        self.save(value)
        other = self.client.post("/api/workouts", json={}).json()
        response = self.client.post(f"/api/workouts/{other['id']}/sets", json=value)
        self.assertEqual(response.status_code, 409)

    def test_duplicate_ordinal_conflicts(self):
        self.save()
        response = self.save(self.payload(
            started_at=(self.start + timedelta(minutes=3)).isoformat(),
            ended_at=(self.start + timedelta(minutes=4)).isoformat(),
        ))
        self.assertEqual(response.status_code, 409)

    def test_ordinal_is_per_exercise(self):
        self.save()
        response = self.save(self.payload(
            exercise="curl", started_at=(self.start + timedelta(minutes=3)).isoformat(),
            ended_at=(self.start + timedelta(minutes=4)).isoformat(),
        ))
        self.assertEqual(response.status_code, 201)

    def test_overlapping_and_out_of_order_sets_rejected(self):
        self.save(self.payload(set_number=2))
        overlap = self.payload(set_number=3, started_at=(self.start + timedelta(seconds=10)).isoformat())
        self.assertEqual(self.save(overlap).status_code, 422)
        backwards = self.payload(
            set_number=1, started_at=(self.start + timedelta(minutes=3)).isoformat(),
            ended_at=(self.start + timedelta(minutes=4)).isoformat(),
        )
        self.assertEqual(self.save(backwards).status_code, 422)

    def test_invalid_timestamps_and_negative_values_rejected(self):
        examples = [
            {"started_at": "2026-09-24T10:00:00"},
            {"started_at": (self.start - timedelta(minutes=2)).isoformat()},
            {"ended_at": (self.start - timedelta(seconds=1)).isoformat()},
            {"weight": -1}, {"weight": 2001}, {"target_reps": 0}, {"reps": -1},
            {"rest_before_seconds": -1}, {"effort_rir": 11}, {"exercise": "deadlift"},
            {"weight": "Infinity"}, {"weight": "NaN"}, {"source": "invented"},
        ]
        for change in examples:
            with self.subTest(change=change):
                self.assertEqual(self.save(self.payload(**change)).status_code, 422)

    def test_rep_timing_cannot_exceed_set_time(self):
        detail = {"index": 1, "down_seconds": 30, "up_seconds": 30, "total_seconds": 60, "range_degrees": 80}
        self.assertEqual(self.save(self.payload(source="camera", reps=1, rep_details=[detail])).status_code, 422)

    def test_nonfinite_json_numbers_report_validation_error(self):
        for value in [float("nan"), float("inf"), float("-inf")]:
            response = self.client.post(
                f"/api/workouts/{self.workout['id']}/sets",
                content=json.dumps(self.payload(weight=value)),
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(response.status_code, 422)

    def test_manual_record_cannot_claim_pose_measurements(self):
        detail = {"index": 1, "down_seconds": 1, "up_seconds": 1, "total_seconds": 2, "range_degrees": 80}
        self.assertEqual(self.save(self.payload(rep_details=[detail])).status_code, 422)

    def test_correction_preserves_camera_measurements_and_retry_returns_correction(self):
        detail = {"index": 1, "down_seconds": 1.3, "up_seconds": 0.8, "total_seconds": 2.4, "range_degrees": 90}
        value = self.payload(source="camera", reps=1, rep_details=[detail])
        self.assertEqual(self.save(value).status_code, 201)
        edited = self.client.patch(f"/api/sets/{value['id']}", json={"reps": 2, "effort_rir": 2}).json()
        self.assertEqual(edited["reps"], 2)
        self.assertEqual(edited["tracked_reps"], 1)
        self.assertTrue(edited["reps_corrected"])
        self.assertEqual(edited["rep_details"], [detail])
        self.assertEqual(self.save(value).json()["reps"], 2)
        cleared = self.client.patch(f"/api/sets/{value['id']}", json={"effort_rir": None}).json()
        self.assertIsNone(cleared["effort_rir"])

    def test_patch_rejects_null_and_immutable_fields(self):
        saved = self.save().json()
        for patch in [{"reps": None}, {"reps": -1}, {"id": str(uuid4())}, {"rep_details": []}, {}]:
            with self.subTest(patch=patch):
                self.assertEqual(self.client.patch(f"/api/sets/{saved['id']}", json=patch).status_code, 422)

    def test_ending_workout_cannot_truncate_set_and_closed_workout_rejects_new_set(self):
        value = self.payload()
        self.save(value)
        url = f"/api/workouts/{self.workout['id']}"
        self.assertEqual(self.client.patch(url, json={"ended_at": self.start.isoformat()}).status_code, 422)
        self.assertEqual(self.client.patch(url, json={"ended_at": value["ended_at"]}).status_code, 200)
        next_set = self.payload(
            set_number=2, started_at=(self.start + timedelta(minutes=3)).isoformat(),
            ended_at=(self.start + timedelta(minutes=4)).isoformat(),
        )
        self.assertEqual(self.save(next_set).status_code, 409)
        self.assertEqual(self.client.patch(url, json={"ended_at": None}).status_code, 200)
        self.assertEqual(self.save(next_set).status_code, 201)

    def test_unknown_ids_return_404(self):
        missing = str(uuid4())
        self.assertEqual(self.client.patch(f"/api/sets/{missing}", json={"reps": 1}).status_code, 404)
        self.assertEqual(self.client.patch(f"/api/workouts/{missing}", json={"ended_at": None}).status_code, 404)

    def test_query_validation_and_local_only_origin(self):
        self.assertEqual(self.client.get("/api/recommendation", params={"exercise": "squat", "weight": "nan"}).status_code, 422)
        self.assertEqual(self.client.get("/api/recommendation", params={"exercise": "squat", "weight": 0, "baseline_seconds": 10}).status_code, 422)
        response = self.client.get("/api/health", headers={"Origin": "https://example.org"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("access-control-allow-origin", response.headers)


if __name__ == "__main__":
    unittest.main()

"""SQLite storage. Each mutation is atomic; retries cannot double-count a set."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from .models import SetCreate, SetUpdate


class DomainError(Exception):
    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.status_code = status_code


def timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def encode(data) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False)


class Repository:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS workouts (
                    id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    ended_at TEXT
                );
                CREATE TABLE IF NOT EXISTS sets (
                    id TEXT PRIMARY KEY,
                    workout_id TEXT NOT NULL REFERENCES workouts(id),
                    exercise TEXT NOT NULL,
                    set_number INTEGER NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    UNIQUE(workout_id, exercise, set_number)
                );
                CREATE INDEX IF NOT EXISTS sets_workout ON sets(workout_id, started_at);
                PRAGMA user_version = 1;
            """)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _workout(connection, workout_id):
        row = connection.execute("SELECT * FROM workouts WHERE id=?", (workout_id,)).fetchone()
        if row is None:
            raise DomainError("Workout not found.", 404)
        data = dict(row)
        data["sets"] = [json.loads(item[0]) for item in connection.execute(
            "SELECT data_json FROM sets WHERE workout_id=? ORDER BY started_at, set_number",
            (workout_id,),
        )]
        return data

    def list_workouts(self):
        with self.connect() as connection:
            ids = connection.execute("SELECT id FROM workouts ORDER BY started_at DESC").fetchall()
            return [self._workout(connection, row[0]) for row in ids]

    def create_workout(self):
        workout_id = str(uuid4())
        started_at = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            connection.execute("INSERT INTO workouts(id, started_at) VALUES (?,?)", (workout_id, started_at))
            return self._workout(connection, workout_id)

    def update_workout(self, workout_id: str, ended_at: datetime | None):
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            workout = self._workout(connection, workout_id)
            if ended_at is not None:
                if ended_at < timestamp(workout["started_at"]):
                    raise DomainError("Workout end must be at or after its start.", 422)
                if any(ended_at < timestamp(item["ended_at"]) for item in workout["sets"]):
                    raise DomainError("Workout end cannot precede a saved set.", 422)
            connection.execute("UPDATE workouts SET ended_at=? WHERE id=?", (
                ended_at.isoformat() if ended_at else None, workout_id,
            ))
            return self._workout(connection, workout_id)

    def create_set(self, workout_id: str, value: SetCreate):
        request = value.model_dump(mode="json")
        request_json = encode(request)
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            previous = connection.execute("SELECT * FROM sets WHERE id=?", (str(value.id),)).fetchone()
            if previous is not None:
                if previous["workout_id"] != workout_id or previous["request_json"] != request_json:
                    raise DomainError("This set ID already belongs to a different save request.")
                return json.loads(previous["data_json"])
            workout = self._workout(connection, workout_id)
            if workout["ended_at"] is not None:
                raise DomainError("This workout has ended. Start or resume a workout before adding sets.")
            if value.started_at < timestamp(workout["started_at"]):
                raise DomainError("Set start cannot precede workout start.", 422)
            for existing in workout["sets"]:
                if existing["exercise"] == value.exercise and existing["set_number"] == value.set_number:
                    raise DomainError("That set number already exists for this exercise in this workout.")
                if value.started_at < timestamp(existing["ended_at"]) and value.ended_at > timestamp(existing["started_at"]):
                    raise DomainError("Set time overlaps an existing set.", 422)
                if existing["exercise"] == value.exercise:
                    if (value.set_number > existing["set_number"]) != (value.started_at >= timestamp(existing["ended_at"])):
                        raise DomainError("Set numbers must follow time order for each exercise.", 422)
            data = {
                **request,
                "workout_id": workout_id,
                "original_reps": value.reps,
                "tracked_reps": len(value.rep_details) if value.source == "camera" else None,
                "reps_corrected": value.source == "camera" and value.reps != len(value.rep_details),
            }
            try:
                connection.execute(
                    "INSERT INTO sets VALUES (?,?,?,?,?,?,?,?)",
                    (str(value.id), workout_id, value.exercise, value.set_number,
                     request["started_at"], request["ended_at"], request_json, encode(data)),
                )
            except sqlite3.IntegrityError as error:
                raise DomainError("A conflicting set has already been saved.") from error
            return data

    def update_set(self, set_id: str, value: SetUpdate):
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT data_json FROM sets WHERE id=?", (set_id,)).fetchone()
            if row is None:
                raise DomainError("Set not found.", 404)
            data = json.loads(row[0])
            data.update(value.model_dump(exclude_unset=True))
            reference = data["tracked_reps"] if data["source"] == "camera" else data["original_reps"]
            data["reps_corrected"] = data["reps"] != reference
            connection.execute("UPDATE sets SET data_json=? WHERE id=?", (encode(data), set_id))
            return data

    def all_sets(self):
        with self.connect() as connection:
            return [json.loads(row[0]) for row in connection.execute("SELECT data_json FROM sets ORDER BY started_at")]

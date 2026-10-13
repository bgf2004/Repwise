"""Run from the project root: python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000."""

from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .models import SetCreate, SetUpdate, WorkoutCreate, WorkoutUpdate
from .recommendation import recommend
from .repository import DomainError, Repository


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def create_app(db_path: str | Path | None = None, static_dir: str | Path | None = None):
    database = Path(db_path or os.environ.get("REPWISE_DB", PROJECT_ROOT / "data" / "workouts.sqlite3"))

    @asynccontextmanager
    async def lifespan(application):
        application.state.repository = Repository(database)
        yield

    application = FastAPI(title="Repwise local workout API", version="0.1.0", lifespan=lifespan)

    @application.exception_handler(DomainError)
    async def handle_domain_error(request, error):
        return JSONResponse(status_code=error.status_code, content={"detail": str(error)})

    @application.exception_handler(RequestValidationError)
    async def handle_validation_error(request, error):
        # Non-standard JSON NaN/Infinity still receive a useful 422 rather than
        # breaking JSON serialization while reporting the rejected input.
        safe_errors = json.loads(json.dumps(error.errors(), default=str), parse_constant=str)
        return JSONResponse(status_code=422, content={"detail": safe_errors})

    # No permissive CORS: Vite proxies /api; production UI and API share one origin.
    @application.get("/api/health")
    def health():
        return {"status": "ok", "storage": "sqlite", "version": "0.1.0"}

    @application.get("/api/workouts")
    def workouts(request: Request):
        return request.app.state.repository.list_workouts()

    @application.post("/api/workouts", status_code=201)
    def create_workout(value: WorkoutCreate, request: Request):
        return request.app.state.repository.create_workout()

    @application.patch("/api/workouts/{workout_id}")
    def update_workout(workout_id: str, value: WorkoutUpdate, request: Request):
        return request.app.state.repository.update_workout(workout_id, value.ended_at)

    @application.post("/api/workouts/{workout_id}/sets", status_code=201)
    def create_set(workout_id: str, value: SetCreate, request: Request):
        return request.app.state.repository.create_set(workout_id, value)

    @application.patch("/api/sets/{set_id}")
    def update_set(set_id: str, value: SetUpdate, request: Request):
        return request.app.state.repository.update_set(set_id, value)

    @application.get("/api/recommendation")
    def recommendation(
        request: Request,
        exercise: Literal["squat", "curl"],
        weight: float = Query(ge=0, le=2000, allow_inf_nan=False),
        unit: Literal["lb", "kg"] = "lb",
        target_reps: int = Query(default=10, ge=1, le=200),
        set_number: int = Query(default=2, ge=1, le=100),
        tempo: Literal["natural", "controlled"] = "natural",
        baseline_seconds: int = Query(default=120, ge=30, le=600),
    ):
        return recommend(
            request.app.state.repository.all_sets(), exercise=exercise, weight=weight, unit=unit,
            target_reps=target_reps, set_number=set_number, tempo=tempo, baseline_seconds=baseline_seconds,
        )

    frontend = Path(static_dir) if static_dir else PROJECT_ROOT / "frontend" / "dist"
    if frontend.is_dir():
        application.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    return application


app = create_app()

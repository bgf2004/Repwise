"""Repeatable local HTTP benchmark, using isolated, synthetic SQLite databases.

Run with the project virtual environment from any working directory:
  .venv/Scripts/python.exe scripts/benchmark_api.py

No production data is read or changed. HTTP round trips exclude browser/camera
inference and are sequential, warm-cache timings, not concurrent capacity tests.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import socket
import sqlite3
import statistics
import subprocess
import sys
import time
from uuid import NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx

from backend.models import SetCreate
from backend.repository import Repository, encode


def identifier(value: str) -> str:
    return str(uuid5(NAMESPACE_URL, "repwise-synthetic-benchmark:" + value))


def payload(key, started, exercise, number, rest, *, weight, reps=10):
    return SetCreate(
        id=identifier(key), exercise=exercise, weight=weight, unit="kg",
        target_reps=10, reps=reps, set_number=number,
        started_at=started, ended_at=started + timedelta(seconds=40),
        rest_before_seconds=rest, tempo="natural", effort_rir=2,
        source="camera", notes="Synthetic benchmark fixture; not an observed workout.",
        rep_details=[dict(index=index + 1, down_seconds=1.8, up_seconds=1.2,
                          total_seconds=3.0, range_degrees=90.0) for index in range(reps)],
    )


def seed(database: Path, count: int):
    """Bulk fixture load with the exact repository encoding/schema, then audit."""
    if count % 10 or count < 300:
        raise ValueError("Use at least 300 sets, in multiples of 10.")
    repository = Repository(database)
    workouts, records = [], []
    for workout_index in range(count // 10):
        workout_id = identifier(f"seed-workout-{workout_index}")
        started = datetime(2020, 1, 1, tzinfo=timezone.utc) + timedelta(days=workout_index)
        rest = (90, 120, 150)[workout_index % 3]
        next_start = started
        for position in range(10):
            exercise = "squat" if position < 5 else "curl"
            number = position % 5 + 1
            value = payload(f"seed-set-{workout_index}-{position}", next_start,
                            exercise, number, None if position == 0 else rest,
                            weight=50 if exercise == "squat" else 20,
                            reps=8 if rest == 90 else 10)
            request = value.model_dump(mode="json")
            data = {**request, "workout_id": workout_id, "original_reps": value.reps,
                    "tracked_reps": len(value.rep_details), "reps_corrected": False}
            records.append((str(value.id), workout_id, exercise, number,
                            request["started_at"], request["ended_at"], encode(request), encode(data)))
            next_start = value.ended_at + timedelta(seconds=rest)
        workouts.append((workout_id, started.isoformat(), value.ended_at.isoformat()))
    with repository.connect() as connection:
        connection.executemany("INSERT INTO workouts VALUES (?,?,?)", workouts)
        connection.executemany("INSERT INTO sets VALUES (?,?,?,?,?,?,?,?)", records)
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not connection.execute("PRAGMA foreign_key_check").fetchall()
        assert connection.execute("SELECT COUNT(*) FROM sets").fetchone()[0] == count
    saved = repository.list_workouts()
    assert len(saved) == count // 10
    for workout in saved:
        assert len(workout["sets"]) == 10
        last_end = workout["started_at"]
        seen = set()
        for item in workout["sets"]:
            valid = SetCreate.model_validate({key: item[key] for key in SetCreate.model_fields})
            assert valid.started_at >= datetime.fromisoformat(last_end.replace("Z", "+00:00"))
            assert item["workout_id"] == workout["id"]
            assert item["original_reps"] == item["tracked_reps"] == item["reps"]
            assert (item["exercise"], item["set_number"]) not in seen
            seen.add((item["exercise"], item["set_number"]))
            last_end = item["ended_at"]
    return {"sets": count, "workouts": count // 10,
            "fixture_validation_passed": count, "sqlite_integrity": "ok",
            "foreign_key_violations": 0, "seed_method": "parameterized bulk INSERT, Pydantic validation and repository audit"}


def summarize(records):
    result = {}
    for operation in sorted({row["operation"] for row in records}):
        selected = [row for row in records if row["operation"] == operation and not row["warmup"]]
        values = sorted(row["elapsed_ms"] for row in selected)
        result[operation] = {
            "requests": len(values), "passed_checks": sum(row["passed"] for row in selected),
            "median_ms": statistics.median(values),
            "p95_ms": values[math.ceil(0.95 * len(values)) - 1],
            "min_ms": min(values), "max_ms": max(values),
            "median_response_bytes": statistics.median(row["response_bytes"] for row in selected),
        }
    return result


def run_scenario(directory: Path, count: int, port: int, read_repeats: int, repeats: int):
    directory.mkdir()
    database = directory / "synthetic.sqlite3"
    fixture = seed(database, count)
    (directory / "fixtures.json").write_text(json.dumps(fixture, indent=2), encoding="utf-8")
    rows, idempotency_checks = [], 0
    environment = {**os.environ, "REPWISE_DB": str(database), "PYTHONDONTWRITEBYTECODE": "1"}
    with (directory / "server.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.app:app", "--host", "127.0.0.1",
                                    "--port", str(port), "--no-access-log"], cwd=ROOT, env=environment,
                                   stdout=log, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=60) as client:
                ready = False
                for _ in range(100):
                    if process.poll() is not None:
                        raise RuntimeError("Benchmark API failed to start; see server.log.")
                    try:
                        ready = client.get("/api/health").status_code == 200
                    except httpx.TransportError:
                        pass
                    if ready:
                        break
                    time.sleep(0.1)
                if not ready:
                    raise TimeoutError("Benchmark server did not become ready.")

                def measured(operation, warmup, method, path, expected_status=200, **kwargs):
                    start = time.perf_counter_ns()
                    response = client.request(method, path, **kwargs)
                    elapsed = (time.perf_counter_ns() - start) / 1e6
                    # Response body is fully buffered before timing ends; client JSON parsing/checks are excluded.
                    row = dict(operation=operation, warmup=warmup, elapsed_ms=elapsed,
                               status=response.status_code, response_bytes=len(response.content), passed=False)
                    rows.append(row)
                    assert response.status_code == expected_status, response.text[:200]
                    return response.json(), row

                print(f"{count:,} sets: measuring full history reads", flush=True)
                for index in range(read_repeats + 3):
                    data, row = measured("history_get", index < 3, "GET", "/api/workouts")
                    assert len(data) == count // 10
                    assert sum(len(workout["sets"]) for workout in data) == count
                    row["passed"] = True

                print(f"{count:,} sets: measuring rest suggestions", flush=True)
                params = dict(exercise="squat", weight=50, unit="kg", target_reps=10,
                              set_number=2, tempo="natural", baseline_seconds=180)
                for index in range(repeats + 10):
                    data, row = measured("recommendation_get", index < 10, "GET", "/api/recommendation", params=params)
                    assert data["status"] == "personalized" and data["recommended_seconds"] == 120
                    assert data["sample_count"] == count // 10 and data["session_count"] == count // 10
                    assert data["excluded_count"] == count - count // 10
                    row["passed"] = True

                print(f"{count:,} sets: measuring set saves", flush=True)
                for index in range(repeats + 10):
                    if index % 10 == 0:
                        created = client.post("/api/workouts", json={})
                        assert created.status_code == 201
                        workout = created.json()
                        next_start = datetime.fromisoformat(workout["started_at"])
                    value = payload(f"post-{count}-{index}", next_start, "squat", index % 10 + 1,
                                    None if index % 10 == 0 else 120, weight=75)
                    request = value.model_dump(mode="json")
                    path = f"/api/workouts/{workout['id']}/sets"
                    data, row = measured("set_post", index < 10, "POST", path, expected_status=201, json=request)
                    assert data["id"] == str(value.id) and data["reps"] == data["tracked_reps"] == 10
                    assert data["original_reps"] == 10 and not data["reps_corrected"]
                    row["passed"] = True
                    # Retry every tenth save outside latency samples; verify exact stable response.
                    if index % 10 == 9:
                        retry = client.post(path, json=request)
                        assert retry.status_code == 201 and retry.json() == data
                        idempotency_checks += 1
                    next_start = value.ended_at + timedelta(seconds=120)
                final = client.get("/api/workouts").json()
                assert sum(len(item["sets"]) for item in final) == count + repeats + 10
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            with (directory / "raw-http.jsonl").open("w", encoding="utf-8") as file:
                for row in rows:
                    file.write(json.dumps(row) + "\n")
    # Re-read on disk to derive final results, independent of in-memory timing accumulation.
    stored = [json.loads(line) for line in (directory / "raw-http.jsonl").read_text().splitlines()]
    summary = dict(seed=fixture, metrics=summarize(stored),
                   invariants={"idempotent_retries_passed": idempotency_checks,
                               "final_sets": count + repeats + 10,
                               "recommendation_fixture_expected_seconds": 120})
    (directory / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sets", nargs="+", type=int, default=[1000, 10000])
    parser.add_argument("--repeats", type=int, default=100)
    parser.add_argument("--read-repeats", type=int, default=30)
    parser.add_argument("--port", type=int, default=8767)
    args = parser.parse_args()
    if args.repeats < 10 or args.repeats % 10 or args.read_repeats < 10:
        parser.error("repeats must be a positive multiple of 10; at least 10 reads.")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", args.port))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = ROOT / "output" / "benchmarks" / ("api-" + stamp)
    output.mkdir(parents=True)
    source = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sorted((ROOT / "backend").glob("*.py"))}
    source["scripts/benchmark_api.py"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    metadata = dict(started_utc=stamp, python=sys.version, platform=platform.platform(),
                    processor=platform.processor(), logical_cpu_count=os.cpu_count(), sqlite=sqlite3.sqlite_version,
                    libraries={name: importlib.metadata.version(name) for name in ("fastapi", "uvicorn", "httpx", "pydantic")},
                    source_sha256=source, options=vars(args),
                    scope="Single persistent HTTP client, sequential loopback requests, warm OS/database cache; no concurrent users, camera inference, rendering, or real workout validation.",
                    timer="perf_counter_ns around fully buffered httpx request; includes server validation/SQLite/serialization/HTTP; excludes client JSON parsing and correctness checks",
                    p95_definition="nearest rank: sorted measurements[ceil(0.95*n)-1]",
                    warmups={"history_get": 3, "recommendation_get": 10, "set_post": 10},
                    order="Read and recommendation timings precede save measurements, keeping initial record counts exact.")
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    results = {}
    for count in args.sets:
        results[str(count)] = run_scenario(output / str(count), count, args.port, args.read_repeats, args.repeats)
    for relative, digest in source.items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == digest, f"Source changed during run: {relative}"
    (output / "summary.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "results": results}, indent=2), flush=True)


if __name__ == "__main__":
    main()

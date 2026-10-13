# Repwise measured results — September 24, 2026

The current laptop version passed **48 automated tests**. A separate real-HTTP benchmark exercised histories of **1,000 and 10,000 synthetic workout sets**. All **460 measured requests** passed their response checks; another **22 duplicate-submit retries** returned the original saved result without creating duplicate sets.

These are local backend measurements. They do not measure camera inference, real-person exercise recognition, browser rendering, iPhone performance, or concurrent-user capacity.

## Latency results

| Starting history | Operation | Measured requests | Median | 95th percentile |
|---|---|---:|---:|---:|
| 1,000 sets / 100 workouts | Save a set | 100 | 9.12 ms | 10.79 ms |
| 1,000 sets / 100 workouts | Calculate rest suggestion | 100 | 45.84 ms | 64.67 ms |
| 1,000 sets / 100 workouts | Retrieve complete history | 30 | 129.39 ms | 160.81 ms |
| 10,000 sets / 1,000 workouts | Save a set | 100 | 10.97 ms | 15.80 ms |
| 10,000 sets / 1,000 workouts | Calculate rest suggestion | 100 | 563.22 ms | 710.23 ms |
| 10,000 sets / 1,000 workouts | Retrieve complete history | 30 | 1,332.66 ms | 1,390.22 ms |

The 95th percentile is the duration at or below which 95% of the recorded requests completed. The report uses the nearest-rank calculation, with warmups excluded. Results represent one run and may vary with machine load.

## How the benchmark ran

- Windows 11, AMD64 processor with 16 logical CPUs; Python 3.12.14, SQLite 3.53.1, FastAPI 0.141.1, Uvicorn 0.53.0, HTTPX 0.28.1, and Pydantic 2.13.5. Exact platform details and source SHA-256 hashes are in [metadata.json](metadata.json).
- One HTTP client issued sequential requests to an isolated Uvicorn server at `127.0.0.1:8767`, with a reused connection and warm caches. This was not a load test with multiple users or a cloud/network benchmark.
- Separate synthetic SQLite databases were created for the two history sizes. The running user application and its workout database were not used by the benchmark.
- Each initial workout contains ten sets split between squats and curls. Seeded sets contain eight or ten synthetic rep-detail records; saves contain ten. These records were generated, not captured from a camera.
- Seed data were bulk inserted using the repository schema and encoding, then checked through Pydantic validation, a repository read, SQLite integrity checks, and foreign-key checks. Bulk seeding time is not a reported performance result.
- History and recommendation requests ran before new-set writes, so their history sizes are exact. Saves followed ten excluded warmup writes, then added 100 measured sets. Final sizes were 1,110 and 10,110 sets.
- The stopwatch includes HTTP transfer, server validation, database work, response serialization, and receiving the full response body. Client-side JSON parsing, response assertions, browser work, and camera inference are outside the timing.
- Per history size, warmups comprised three history reads, ten suggestions, and ten saves. Retry checks were outside the latency samples.
- Correctness checks included expected record counts and the fixture's expected 120-second rest suggestion. This verifies the programmed rule against known synthetic data, not that 120 seconds is physiologically optimal.
- An independent recalculation from raw measurements matched all medians and percentiles; source hashes remained unchanged. See [independent-verification.json](independent-verification.json).

Raw samples are in [1,000-set measurements](1000/raw-http.jsonl) and [10,000-set measurements](10000/raw-http.jsonl). [summary.json](summary.json) contains unrounded results.

## Automated tests

Rerun after the timed benchmark finished to avoid competition for CPU during measurement:

- **26 backend tests passed:** persistence, input validation, duplicate submissions, edits preserving measurements, chronological checks, unit conversion, and rest-suggestion rules/fallbacks.
- **22 frontend tests passed:** 13 synthetic-landmark counter tests, five mocked camera-lifecycle tests, and four timing-feedback tests.

The frontend test runner initially encountered a sandbox file-access restriction; the authorized rerun passed. No failing application test was suppressed. The camera lifecycle tests use mocks and do not turn on the webcam.

## What the results suggest improving

Set saving remains fast at the larger history size. The current history endpoint returns every workout, including rep details: its response grows from approximately 1.32 MB to 13.17 MB. Pagination and loading rep details only when needed would reduce the history screen's workload. Rest suggestions currently read and validate the entire set history; filtering comparable records in the database and avoiding repeated full-history validation are useful next optimization targets. These are recommendations, not changes included in this baseline.

## Resume wording

- Built a React/TypeScript and FastAPI workout tracker with browser-based pose estimation for squats and curls, rep-phase timing, SQLite workout history, and rest suggestions based on comparable sets.
- Validated 48 automated tests and benchmarked a 10,000-set synthetic history, measuring 15.8 ms p95 set-save latency across 100 sequential local HTTP requests.

Do not replace “synthetic history” with real users/workouts, or describe the latency as camera/AI inference speed. Counting accuracy, phase-timing error, real-camera processing rate, and the effectiveness of rest suggestions still need evaluation on separately labeled, consented exercise recordings and actual workout sessions.

## Repeat the measurement

From the Repwise project folder, with dependencies installed:

```powershell
.\.venv\Scripts\python.exe scripts\benchmark_api.py
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
```

Run the frontend checks from `frontend` with `pnpm run test`. Keep other heavy work stopped during timing. Each benchmark run writes a new timestamped directory and its own synthetic databases; port 8767 must be available.

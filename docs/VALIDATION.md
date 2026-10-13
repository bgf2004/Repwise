# Repwise validation

Checked locally on September 24, 2026. These results establish software behavior, not exercise-recognition accuracy.

## Publication checks — October 13, 2026

- Reran all **26 backend tests** and **22 frontend tests** successfully.
- TypeScript checks and the Vite production build passed.
- The initial backend run stalled in the restricted execution environment; rerunning outside that environment passed. The September 24 benchmark numbers below remain historical results and were not remeasured for publication.

## Automated checks

- **26 backend tests passed:** SQLite persistence across restart, input validation, isolated synthetic data, duplicate-submit idempotency, edits preserving camera timing, chronological consistency, rest bucket selection, unit conversion, irrelevant-data exclusion, and baseline fallback.
- **22 frontend tests passed:** 13 synthetic-landmark movement tests, 5 mocked camera lifecycle tests, and 4 tempo-summary tests.
- TypeScript checks and the Vite production build passed.

The 26 backend and 22 frontend tests were rerun successfully after the September 24 API benchmark. See the [measured benchmark report](../output/benchmarks/api-20260924T084714Z/REPORT.md) for 1,000- and 10,000-set synthetic histories, request counts, median/p95 latencies, and raw data. These HTTP timings exclude camera inference and browser rendering.

## Browser workflow

Used a separate SQLite test database, with deliberately synthetic manually entered sets. No real workout records or camera footage were used.

- Entered 45 lb, started a workout, counted 10 manual reps, recorded effort and a test note, and saved the first set.
- Reloaded the app and verified the saved set and continuing rest timer.
- Logged a second set; verified that its rest-before value captured the interval from the prior set.
- Corrected reps from 8 to 9 and later changed the second set's weight to 50 lb.
- Finished the workout and verified history showed two sets and 19 reps.
- Verified the rest-insights screen and comparison set-position selector.
- Inspected desktop and mobile layouts; no page-width overflow at the checked mobile viewport.
- No browser console errors appeared during these workflows.

## Assets

The actual MediaPipe Pose Landmarker Lite model and the matching package's WASM runtime are downloaded locally. Their source, version, size, and SHA-256 are recorded in `frontend/public/models/assets-manifest.json` by the asset preparation script.

## Limits of this validation

The camera tests mock device and model lifecycle boundaries. Rep-counter tests use synthetic joint trajectories. Live workout tracking, camera latency/FPS, rep-count accuracy, phase-timing error, and suitability of rest suggestions have **not** been measured on a representative dataset or on people exercising. The interface states this limitation. Camera permissions remain off until the user enables the camera.

Rest suggestions are transparent associations in recorded sets, not validated causal or medical recommendations. Suggested minimum evidence thresholds are product heuristics.

See the README evaluation plan before using performance or accuracy numbers on a resume.

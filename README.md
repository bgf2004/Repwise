# Repwise

A local workout companion that connects camera-based rep timing with a useful training log. Enter your external load and target reps, record a set, and track the rest interval before your next set. As your history grows, Repwise can suggest a rest interval based on comparable sets you actually completed.

This is a working, single-user prototype for development and evaluation. It has no public account system or cloud deployment. Camera-derived rep counts and timings have **not** been validated on a labeled exercise dataset yet; the app does not claim a measured counting accuracy or a medically optimal rest duration.

## What it does

- Logs exercises, entered weight, weight unit, target reps, actual reps, and set order.
- Tracks the time between sets and retains the measured interval with the following set.
- Runs MediaPipe Pose Landmarker locally in the browser for side-view squats and curls, using movement rules to count reps and estimate movement-phase duration.
- Summarizes rep timing and consistency; supports manual set logging when tracking is unavailable.
- Saves workout history in SQLite and uses comparable historical sets to produce an explainable rest suggestion.
- Keeps manual corrections separate from the original measured rep details.

“Weight” means the external load you enter; the camera does not estimate kilograms or pounds. Enter a consistent load convention for an exercise: for example, the combined weight of two dumbbells each time. Rep speed means **time per movement phase**, not measured bar velocity in meters per second.

The first release saves set metrics, not video recordings. There is no injury-risk classifier, medical advice, or claim that a particular movement pattern is universally correct.

## Windows setup

**After setup:** double-click `Start Repwise.cmd`, keep its window open, and open **http://127.0.0.1:8765**. If that address is already working, use the existing running instance. Follow the setup steps below for first installation or rebuilding after changes.

Install Python 3.10 or later, Node.js 20.19 or later, and pnpm. A recent desktop Chrome or Edge is recommended for camera access and WebAssembly. Setup needs internet access to install dependencies and download the pose model; the finished app serves its model and runtime files locally.

Clone the repository and open the project directory in PowerShell:

```powershell
git clone https://github.com/bgf2004/Repwise.git
Set-Location Repwise
```

Then run:

```powershell
.\setup.ps1
.\start.ps1
```

Then open **http://127.0.0.1:8765**. Stop the server with Ctrl+C. The start script stays in the foreground and does not register a background service.

If PowerShell blocks a local script under your execution policy, invoke it for this process only:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
```

Custom executable paths can be supplied when Python or pnpm is not on your PATH:

```powershell
.\setup.ps1 -PythonExe "C:\path\to\python.exe" -PnpmExe "C:\path\to\pnpm.cmd"
```

The setup script creates `.venv`, installs the backend and frontend dependencies, prepares local vision assets, and builds the frontend. If a pnpm lockfile exists, installation uses that lockfile. Rerun setup after updating the app.

Optional launch arguments:

```powershell
.\start.ps1 -Port 8766
.\start.ps1 -OpenBrowser
```

If you opt to open a browser automatically and it loads before the server is ready, refresh the page. No camera access starts merely from launching the server; start it explicitly in the app and approve the browser's camera prompt.

## First workout

1. Choose an exercise, weight, unit, target reps, and intended tempo. Choose your starting rest timer.
2. Position the camera so the relevant joints stay visible. Use a stable side view for the squat; leave room for the whole movement. Inspect the tracking preview before starting.
3. Start a set and complete the movement. Low-confidence or missing landmarks can interrupt tracking; correct an incorrect total or use manual logging.
4. End and save the set. Rest timing connects the end of that set to the start of the next one.
5. Review the saved reps, weight, timing, and rest periods in workout history. Future suggestions show whether there is enough comparable history to use.

The person controls set boundaries. The app does not reliably infer when a workout is over from someone standing still. Good lighting, an unobstructed view, stable camera placement, and one person in the frame make tracking easier. Test carefully before treating the recorded measurements as reliable.

## How rest suggestions work

The initial suggestion uses your chosen baseline timer. Historical suggestions require evidence, and the app reports the sample size rather than presenting a guess as personalization.

Comparable history must match the exercise, entered external load, target rep count, set number within that exercise, and intended tempo. Pounds and kilograms are normalized, with a 0.03 kg comparison tolerance. First sets and rest intervals outside 30–600 seconds do not contribute.

The current rule groups rest durations into 30-second buckets. A bucket needs at least **six comparable sets across three workouts** and a target-rep completion rate of **80% or greater**. The app chooses the shortest observed bucket that meets those rules. With insufficient qualifying evidence, it keeps the baseline you chose.

These thresholds are prototype engineering rules, not established physiological recommendations. Meeting a target after a rest interval demonstrates an association, not that the rest caused the result. Sleep, exercise order, fatigue, and effort can affect performance. Deliberately slow reps are not automatically scored as poor performance. The intended goal is a useful, reviewable suggestion; “best” and “optimal” are not validated claims.

## Local data and privacy

- Camera frames are processed in the browser. They are not uploaded to the backend, sent to an AI API, or written as video files.
- The backend receives workout fields and measured rep/set details. It stores them at `data/workouts.sqlite3` by default.
- There is no login or separation between multiple people using the same app data. Treat a running local instance as accessible to other users and programs on that computer.
- The server binds to `127.0.0.1`. Do not expose it publicly without adding authentication, authorization, and deployment controls.
- `REPWISE_DB` can override the SQLite path. For example, set `$env:REPWISE_DB` before launching the server.
- Back up the database while the server is stopped. Dependency installation and the initial model download use internet access; ordinary workout tracking does not require an external AI service.

No API key is required. The model is downloaded from Google's official MediaPipe model distribution. `frontend/public/models/assets-manifest.json` records the URL, model hash, package version, and local runtime files used by this installation.

## Development

The project uses React, TypeScript, Vite, and MediaPipe in the frontend, plus FastAPI and SQLite in the backend. The production backend serves `frontend/dist` and `/api` on one origin. Build the frontend **before** starting the production backend because the frontend mount is configured on startup.

Start the backend from the project root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8765 --reload
```

In a second terminal, run the frontend development server:

```powershell
Set-Location frontend
pnpm dev
```

The Vite configuration forwards API requests to the local backend. Keep the development backend on port 8765 unless you also update that proxy configuration. Camera APIs need a secure context; localhost and `127.0.0.1` work for local development, while plain HTTP over a LAN address may not.

After installing frontend dependencies, prepare assets separately if needed:

```powershell
.\.venv\Scripts\python.exe scripts/prepare_assets.py
```

Use `--force-download` to replace the model from the official source or `--skip-download` to verify that the model is already available while copying runtime assets. Failed downloads return a nonzero exit status and do not replace a working model with a partial file. Run the frontend build again after changing public assets.

## Verification

The [September 24 benchmark report](output/benchmarks/api-20260924T084714Z/REPORT.md) includes actual laptop API measurements, raw samples, and resume wording. Reproduce it with `.\.venv\Scripts\python.exe scripts\benchmark_api.py`; it creates separate synthetic databases and does not use your workout history.

Run the backend checks from the project root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
```

Run frontend tests and compile the production frontend:

```powershell
Set-Location frontend
pnpm test
pnpm build
```

The automated checks cover program behavior, including synthetic movement sequences and recommendation boundaries. They do not establish accuracy on real camera footage, injury detection, or the effectiveness of a rest prescription.

Before adding performance numbers to a resume, evaluate a frozen app version on held-out recordings from people and sessions not used to tune the movement thresholds:

1. Collect consented, side-view clips covering lighting, clothing, camera placement, partial visibility, and interrupted sets. Keep evaluation recordings separate from ordinary app use.
2. Manually label each completed rep and the beginning/end of each movement phase. Record disagreements between reviewers.
3. Report rep-count mean absolute error, exact-count rate per set, movement-phase timestamp error, and tracking coverage. Count failed tracking sessions instead of omitting them.
4. Measure processing frame rate and latency on a named device and browser, including warm-up separately. Do not equate rendering frame rate with pose-inference speed.
5. Evaluate rest suggestions against the user's baseline timer on later workouts. Report sample sizes, target-rep completion rate, rest time, and uncertainty; historical associations alone do not prove causation.

No measured CV accuracy, latency, or health outcome is claimed by this repository before that evaluation has been performed.

## References

- [Apple App Store release plan and laptop launch instructions](docs/APPLE_RELEASE.md)
- [MediaPipe Pose Landmarker for Web](https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker/web_js)
- [MediaPipe Pose Landmarker overview and model information](https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker)
- [FastAPI documentation](https://fastapi.tiangolo.com/)
- [Vite documentation](https://vite.dev/guide/)

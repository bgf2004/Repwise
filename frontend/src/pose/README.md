# Camera tracking

`PoseCamera.start()` is called by an explicit user action. It loads locally hosted MediaPipe Pose Landmarker Lite and its matching WASM runtime, tries GPU inference with CPU fallback, then requests video-only camera permission. It returns the original camera coordinates; no mirroring or recording is applied. Call `stop()` on navigation/unmount. Stop also invalidates any pending initialization so a late permission response cannot leave the camera running.

`RepCounter` accepts normalized MediaPipe landmarks plus the source frame dimensions. It calculates **2D image-plane angles in pixel coordinates**, smooths them with an 80 ms exponential filter, and locks the most visible side until `reset()`. It requires a stable extended starting position and a complete bend/extend cycle with distinct thresholds, minimum phase durations, and no tracking gap over 500 ms. Frames with low visibility or joints outside the image are excluded.

The squat thresholds are 158° extension / 105° flexion; curl thresholds are 150° extension / 60° flexion. These are prototype detection rules, not prescribed exercise depth or clinical standards. Repetitions outside these thresholds can be missed. Do not force a movement to satisfy the counter. Counts must remain manually correctable. Range is an estimated change in the selected 2D joint angle, not anatomical range of motion.

The down/up fields mean lowering/rising the movement. Squat flexion is down and extension is up; curl flexion is up and extension is down. Duration begins near departure from the extended position and ends upon return to its threshold. Bottom pauses are included in these phase estimates; they are not separately measured. Timing is affected by the smoothing delay and 15 FPS inference ceiling. There is no calibrated linear velocity in meters per second and no injury-risk assessment.

Designed for one person with a fixed, unobstructed side view. Perspective, loose clothing, occlusion, assisted or partial repetitions, and moving cameras affect reliability. Synthetic tests establish algorithmic behavior only. Rep counting accuracy and phase timing accuracy on human recordings remain unvalidated.

MediaPipe's browser detector runs synchronously; the 15 FPS cap limits load, but moving inference into a worker is a future performance improvement for low-powered devices.

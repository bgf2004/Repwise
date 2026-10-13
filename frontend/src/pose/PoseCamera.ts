import { FilesetResolver, PoseLandmarker } from '@mediapipe/tasks-vision';
import type { Landmark } from './RepCounter';

type FrameCallback = (landmarks: Landmark[], timestampMs: number, width: number, height: number) => void;

/** Owns only the live video stream and pose detector; no recording, uploading, or persistence. */
export class PoseCamera {
  private detector: PoseLandmarker | null = null;
  private stream: MediaStream | null = null;
  private video: HTMLVideoElement | null = null;
  private animationFrame: number | null = null;
  private generation = 0;

  /** Call only in response to the user's explicit camera button. */
  async start(video: HTMLVideoElement, onFrame: FrameCallback, onError: (message: string) => void): Promise<void> {
    this.stop();
    const generation = this.generation;
    let pendingDetector: PoseLandmarker | null = null;
    let pendingStream: MediaStream | null = null;
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error('Camera access requires localhost or a secure HTTPS connection.');
      const vision = await FilesetResolver.forVisionTasks('/wasm');
      if (generation !== this.generation) return;
      const options = {
        runningMode: 'VIDEO' as const,
        numPoses: 1,
        minPoseDetectionConfidence: 0.6,
        minPosePresenceConfidence: 0.6,
        minTrackingConfidence: 0.6,
        outputSegmentationMasks: false,
      };
      try {
        pendingDetector = await PoseLandmarker.createFromOptions(vision, {
          ...options, baseOptions: { modelAssetPath: '/models/pose_landmarker_lite.task', delegate: 'GPU' },
        });
      } catch {
        if (generation !== this.generation) return;
        pendingDetector = await PoseLandmarker.createFromOptions(vision, {
          ...options, baseOptions: { modelAssetPath: '/models/pose_landmarker_lite.task', delegate: 'CPU' },
        });
      }
      if (generation !== this.generation) { pendingDetector.close(); return; }
      pendingStream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 720 }, frameRate: { ideal: 30 } },
        audio: false,
      });
      if (generation !== this.generation) {
        pendingStream.getTracks().forEach(track => track.stop());
        pendingDetector.close();
        return;
      }
      this.detector = pendingDetector;
      this.stream = pendingStream;
      this.video = video;
      video.srcObject = pendingStream;
      // Ownership moves to stop(); stale async completions must not close a newer session.
      pendingDetector = null;
      pendingStream = null;
      video.muted = true;
      video.playsInline = true;
      await video.play();
      if (generation !== this.generation) return;
      let lastFrameTime = -Infinity;
      let lastVideoTime = -1;
      const tick = (timestampMs: number) => {
        if (generation !== this.generation || !this.detector) return;
        if (video.readyState >= 2 && video.videoWidth > 0 && video.videoHeight > 0
          && timestampMs - lastFrameTime >= 1000 / 15 && video.currentTime !== lastVideoTime) {
          lastFrameTime = timestampMs;
          lastVideoTime = video.currentTime;
          try {
            const result = this.detector.detectForVideo(video, timestampMs);
            try {
              onFrame(result.landmarks[0] ?? [], timestampMs, video.videoWidth, video.videoHeight);
            } finally {
              result.close();
            }
          } catch (error) {
            this.stop();
            onError(error instanceof Error ? error.message : 'Pose tracking stopped. Try starting the camera again.');
            return;
          }
        }
        this.animationFrame = requestAnimationFrame(tick);
      };
      this.animationFrame = requestAnimationFrame(tick);
    } catch (error) {
      if (generation !== this.generation) {
        pendingStream?.getTracks().forEach(track => track.stop());
        if (pendingDetector && pendingDetector !== this.detector) pendingDetector.close();
        return;
      }
      if (!this.detector) pendingDetector?.close();
      if (!this.stream) pendingStream?.getTracks().forEach(track => track.stop());
      this.stop();
      const name = error instanceof Error ? error.name : '';
      const message = name === 'NotAllowedError' ? 'Camera permission was not granted. You can still log sets manually.'
        : name === 'NotFoundError' ? 'No camera was found. You can still log sets manually.'
          : error instanceof Error ? error.message : 'Camera could not start. Check permission and model files.';
      onError(message);
    }
  }

  stop(): void {
    this.generation += 1;
    if (this.animationFrame !== null) cancelAnimationFrame(this.animationFrame);
    this.animationFrame = null;
    this.stream?.getTracks().forEach(track => track.stop());
    this.stream = null;
    if (this.video) {
      this.video.pause();
      this.video.srcObject = null;
      this.video = null;
    }
    this.detector?.close();
    this.detector = null;
  }
}

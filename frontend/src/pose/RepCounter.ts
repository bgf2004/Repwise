export type Exercise = 'squat' | 'curl';

export interface Landmark {
  x: number;
  y: number;
  z?: number;
  visibility?: number;
}

export interface RepDetail {
  index: number;
  down_seconds: number;
  up_seconds: number;
  total_seconds: number;
  range_degrees: number;
}

export interface TrackingSnapshot {
  count: number;
  phase: 'ready' | 'lowering' | 'rising' | 'find-position' | 'tracking-lost';
  angle: number | null;
  confidence: number;
  /** Only the update completing a repetition contains a rep. */
  rep: RepDetail | null;
  feedback: string;
}

const MIN_VISIBILITY = 0.65;
const MAX_GAP_MS = 500;
const MIN_PHASE_MS = 250;
const MIN_REP_MS = 700;
const MAX_REP_MS = 30_000;
const SMOOTHING_MS = 80;
const JOINTS = {
  squat: { left: [23, 25, 27], right: [24, 26, 28] },
  curl: { left: [11, 13, 15], right: [12, 14, 16] },
} as const;
type Side = 'left' | 'right';
type Stage = 'seeking' | 'ready' | 'flexing' | 'extending';

/** Interior 2D joint angle, correcting normalized x/y for the frame's aspect ratio. */
export function jointAngle(a: Landmark, b: Landmark, c: Landmark, width: number, height: number): number | null {
  if (![a.x, a.y, b.x, b.y, c.x, c.y, width, height].every(Number.isFinite) || width <= 0 || height <= 0) return null;
  const ux = (a.x - b.x) * width;
  const uy = (a.y - b.y) * height;
  const vx = (c.x - b.x) * width;
  const vy = (c.y - b.y) * height;
  const lengths = Math.hypot(ux, uy) * Math.hypot(vx, vy);
  if (lengths < 1e-6) return null;
  const cosine = Math.max(-1, Math.min(1, (ux * vx + uy * vy) / lengths));
  return Math.acos(cosine) * 180 / Math.PI;
}

/** One person, fixed side view. Timing and angles are estimates, not clinical form assessments. */
export class RepCounter {
  private count = 0;
  private side: Side | null = null;
  private stage: Stage = 'seeking';
  private angle: number | null = null;
  private lastUpdate: number | null = null;
  private lastVisible: number | null = null;
  private topSince: number | null = null;
  private lastTopAt = 0;
  private peakAngle = 0;
  private cycleStart = 0;
  private lowestAngle = 180;
  private lowestAt = 0;
  private reachedBottom = false;

  constructor(private readonly exercise: Exercise) {}

  reset(): void {
    this.count = 0;
    this.side = null;
    this.lastUpdate = null;
    this.lastVisible = null;
    this.discardPartial();
  }

  private discardPartial(): void {
    this.stage = 'seeking';
    this.angle = null;
    this.topSince = null;
    this.peakAngle = 0;
    this.reachedBottom = false;
  }

  private confidence(landmarks: Landmark[], side: Side): number {
    return Math.min(...JOINTS[this.exercise][side].map(index => {
      const point = landmarks[index];
      if (!point || !Number.isFinite(point.x) || !Number.isFinite(point.y) || point.x < 0 || point.x > 1 || point.y < 0 || point.y > 1) return 0;
      const visibility = point.visibility ?? 1;
      return Number.isFinite(visibility) ? Math.max(0, Math.min(1, visibility)) : 0;
    }));
  }

  private result(confidence: number, feedback: string, rep: RepDetail | null = null): TrackingSnapshot {
    let phase: TrackingSnapshot['phase'] = 'find-position';
    if (this.stage === 'ready') phase = 'ready';
    if (this.stage === 'flexing') phase = this.exercise === 'squat' ? 'lowering' : 'rising';
    if (this.stage === 'extending') phase = this.exercise === 'squat' ? 'rising' : 'lowering';
    return { count: this.count, phase, angle: this.angle, confidence, rep, feedback };
  }

  update(landmarks: Landmark[], timestampMs: number, width: number, height: number): TrackingSnapshot {
    if (!Number.isFinite(timestampMs) || (this.lastUpdate !== null && timestampMs <= this.lastUpdate)) {
      return this.result(0, 'Waiting for the next camera frame.');
    }
    this.lastUpdate = timestampMs;
    const gap = this.lastVisible === null ? 0 : timestampMs - this.lastVisible;
    if (gap > MAX_GAP_MS) this.discardPartial();

    if (!this.side) {
      const left = this.confidence(landmarks, 'left');
      const right = this.confidence(landmarks, 'right');
      if (Math.max(left, right) >= MIN_VISIBILITY) this.side = left >= right ? 'left' : 'right';
    }
    const confidence = this.side ? this.confidence(landmarks, this.side) : 0;
    const indices = this.side ? JOINTS[this.exercise][this.side] : null;
    const raw = indices && confidence >= MIN_VISIBILITY
      ? jointAngle(landmarks[indices[0]], landmarks[indices[1]], landmarks[indices[2]], width, height)
      : null;
    if (raw === null) {
      return { count: this.count, phase: 'tracking-lost', angle: null, confidence, rep: null,
        feedback: this.exercise === 'squat'
          ? 'Keep the same side of your hip, knee, and ankle in view.'
          : 'Keep the same side of your shoulder, elbow, and wrist in view.' };
    }

    const elapsed = this.lastVisible === null ? SMOOTHING_MS : timestampMs - this.lastVisible;
    this.lastVisible = timestampMs;
    this.angle = this.angle === null ? raw : this.angle + (raw - this.angle) * (1 - Math.exp(-elapsed / SMOOTHING_MS));
    const angle = this.angle;
    const topThreshold = this.exercise === 'squat' ? 158 : 150;
    const bottomThreshold = this.exercise === 'squat' ? 105 : 60;
    const readyMessage = this.exercise === 'squat' ? 'Ready. Lower into your next squat.' : 'Ready. Curl up for your next rep.';

    if (this.stage === 'seeking') {
      if (angle >= topThreshold) {
        this.topSince ??= timestampMs;
        this.peakAngle = Math.max(this.peakAngle, angle);
        if (timestampMs - this.topSince >= 150) {
          this.stage = 'ready';
          this.lastTopAt = timestampMs;
          return this.result(confidence, readyMessage);
        }
      } else {
        this.topSince = null;
        this.peakAngle = 0;
      }
      return this.result(confidence, this.exercise === 'squat'
        ? 'Stand tall in a side view to begin counting.' : 'Start with your arm extended at your side.');
    }

    if (this.stage === 'ready') {
      this.peakAngle = Math.max(this.peakAngle, angle);
      if (angle >= topThreshold) this.lastTopAt = timestampMs;
      if (angle < topThreshold - 8) {
        this.stage = 'flexing';
        this.cycleStart = this.lastTopAt;
        this.lowestAngle = angle;
        this.lowestAt = timestampMs;
        this.reachedBottom = angle <= bottomThreshold;
      }
      return this.result(confidence, readyMessage);
    }

    if (timestampMs - this.cycleStart > MAX_REP_MS) {
      this.discardPartial();
      return this.result(confidence, 'Movement paused. Return to the starting position to count again.');
    }

    this.peakAngle = Math.max(this.peakAngle, angle);
    if (angle < this.lowestAngle) {
      this.lowestAngle = angle;
      this.lowestAt = timestampMs;
    }
    if (angle <= bottomThreshold) this.reachedBottom = true;
    if (this.reachedBottom && angle > this.lowestAngle + 6) this.stage = 'extending';

    if (angle >= topThreshold) {
      const flexMs = this.lowestAt - this.cycleStart;
      const extendMs = timestampMs - this.lowestAt;
      const totalMs = timestampMs - this.cycleStart;
      const accepted = this.reachedBottom && flexMs >= MIN_PHASE_MS && extendMs >= MIN_PHASE_MS && totalMs >= MIN_REP_MS;
      const rep = accepted ? {
        index: ++this.count,
        down_seconds: (this.exercise === 'squat' ? flexMs : extendMs) / 1000,
        up_seconds: (this.exercise === 'squat' ? extendMs : flexMs) / 1000,
        total_seconds: totalMs / 1000,
        range_degrees: this.peakAngle - this.lowestAngle,
      } : null;
      this.stage = 'ready';
      this.lastTopAt = timestampMs;
      this.peakAngle = angle;
      this.reachedBottom = false;
      return this.result(confidence, accepted ? `Rep ${this.count} recorded. Keep a steady tempo.` : 'Partial or very brief movement skipped.', rep);
    }

    return this.result(confidence, this.stage === 'flexing'
      ? (this.exercise === 'squat' ? 'Lowering. Keep your movement controlled.' : 'Rising. Keep your movement controlled.')
      : (this.exercise === 'squat' ? 'Rising. Return to your starting position.' : 'Lowering. Return to your starting position.'));
  }
}

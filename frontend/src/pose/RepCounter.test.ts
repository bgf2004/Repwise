import { describe, expect, it } from 'vitest';
import { jointAngle, RepCounter, type Exercise, type Landmark, type RepDetail, type TrackingSnapshot } from './RepCounter';

function pose(angle: number, exercise: Exercise = 'squat', width = 960, height = 720, leftVisibility = 0.99, rightVisibility = 0.4): Landmark[] {
  const points: Landmark[] = Array.from({ length: 33 }, () => ({ x: 0.5, y: 0.5, visibility: 0.1 }));
  const indices = exercise === 'squat' ? [[23, 25, 27], [24, 26, 28]] : [[11, 13, 15], [12, 14, 16]];
  const radians = angle * Math.PI / 180;
  for (const [side, [a, b, c]] of indices.entries()) {
    const cx = side === 0 ? 300 : 400;
    const cy = 300;
    const visibility = side === 0 ? leftVisibility : rightVisibility;
    points[a] = { x: cx / width, y: (cy - 120) / height, visibility };
    points[b] = { x: cx / width, y: cy / height, visibility };
    points[c] = { x: (cx + 120 * Math.sin(radians)) / width, y: (cy - 120 * Math.cos(radians)) / height, visibility };
  }
  return points;
}

class Movement {
  time = 0;
  reps: RepDetail[] = [];
  last: TrackingSnapshot | null = null;
  angle = 176;
  constructor(readonly counter: RepCounter, readonly exercise: Exercise = 'squat', readonly width = 960, readonly height = 720) {}
  sample(angle: number, leftVisibility = 0.99, rightVisibility = 0.4): void {
    this.time += 50;
    this.angle = angle;
    this.last = this.counter.update(pose(angle, this.exercise, this.width, this.height, leftVisibility, rightVisibility), this.time, this.width, this.height);
    if (this.last.rep) this.reps.push(this.last.rep);
  }
  hold(angle: number, duration = 350): void {
    for (let n = 0; n < duration / 50; n++) this.sample(angle);
  }
  move(to: number, duration: number): void {
    const from = this.angle;
    const steps = Math.round(duration / 50);
    for (let n = 1; n <= steps; n++) this.sample(from + (to - from) * n / steps);
  }
  rep(flexMs = 1200, extendMs = 700): void {
    this.move(this.exercise === 'squat' ? 82 : 35, flexMs);
    this.move(176, extendMs);
    this.hold(176, 200);
  }
}

describe('joint geometry', () => {
  it('converts normalized coordinates to the actual rectangular image before computing angles', () => {
    const a = { x: 0.2, y: 0.2 };
    const b = { x: 0.5, y: 0.5 };
    const c = { x: 0.8, y: 0.2 };
    expect(jointAngle(a, b, c, 100, 100)).toBeCloseTo(90);
    expect(jointAngle(a, b, c, 200, 100)).toBeCloseTo(126.86989765);
  });

  it('rejects invalid dimensions, coordinates and zero-length limbs', () => {
    const a = { x: 0.2, y: 0.2 };
    const b = { x: 0.5, y: 0.5 };
    expect(jointAngle(a, b, b, 960, 720)).toBeNull();
    expect(jointAngle(a, b, a, 0, 720)).toBeNull();
    expect(jointAngle({ x: NaN, y: 0.2 }, b, a, 960, 720)).toBeNull();
  });
});

describe('RepCounter full-cycle detection', () => {
  it('counts complete squat cycles once and preserves directional phase timings', () => {
    const motion = new Movement(new RepCounter('squat'));
    motion.hold(176);
    motion.rep();
    motion.rep();
    expect(motion.last?.count).toBe(2);
    expect(motion.reps.map(rep => rep.index)).toEqual([1, 2]);
    for (const rep of motion.reps) {
      expect(rep.down_seconds).toBeGreaterThan(rep.up_seconds);
      expect(rep.down_seconds + rep.up_seconds).toBeCloseTo(rep.total_seconds);
      expect(rep.range_degrees).toBeGreaterThan(70);
      expect(rep.total_seconds).toBeGreaterThan(1.4);
      expect(rep.total_seconds).toBeLessThan(2.2);
    }
    expect(motion.last?.rep).toBeNull();
  });

  it('labels curl flexion as rising and extension as lowering', () => {
    const motion = new Movement(new RepCounter('curl'), 'curl');
    motion.hold(176);
    motion.move(70, 950);
    expect(motion.last?.phase).toBe('rising');
    motion.move(35, 350);
    motion.move(110, 400);
    expect(motion.last?.phase).toBe('lowering');
    motion.move(176, 350);
    motion.hold(176);
    expect(motion.reps).toHaveLength(1);
    expect(motion.reps[0].up_seconds).toBeGreaterThan(motion.reps[0].down_seconds);
    expect(motion.reps[0].up_seconds + motion.reps[0].down_seconds).toBeCloseTo(motion.reps[0].total_seconds);
  });

  it('gives the same count and timing for equivalent pixel trajectories at different aspect ratios', () => {
    const landscape = new Movement(new RepCounter('squat'), 'squat', 960, 720);
    const portrait = new Movement(new RepCounter('squat'), 'squat', 720, 1280);
    for (const motion of [landscape, portrait]) { motion.hold(176); motion.rep(); }
    expect(portrait.reps[0].total_seconds).toBe(landscape.reps[0].total_seconds);
    expect(portrait.reps[0].range_degrees).toBeCloseTo(landscape.reps[0].range_degrees);
  });

  it('does not count an initial partial movement before finding the extended starting position', () => {
    const motion = new Movement(new RepCounter('squat'));
    motion.hold(85);
    motion.move(176, 800);
    motion.hold(176);
    expect(motion.last?.count).toBe(0);
    motion.rep();
    expect(motion.last?.count).toBe(1);
  });

  it('does not count threshold jitter or incomplete movement', () => {
    const motion = new Movement(new RepCounter('squat'));
    motion.hold(176);
    for (let n = 0; n < 100; n++) motion.sample(160 + Math.sin(n) * 16);
    motion.move(130, 700);
    motion.move(176, 700);
    motion.hold(176);
    expect(motion.last?.count).toBe(0);
  });

  it('rejects implausibly brief cycles', () => {
    const motion = new Movement(new RepCounter('squat'));
    motion.hold(176);
    motion.move(75, 100);
    motion.move(176, 100);
    motion.hold(176, 250);
    expect(motion.last?.count).toBe(0);
  });
});

describe('tracking continuity', () => {
  it('discards a partial repetition after more than 500 ms with low visibility', () => {
    const motion = new Movement(new RepCounter('squat'));
    motion.hold(176);
    motion.move(82, 1000);
    for (let n = 0; n < 14; n++) motion.sample(82, 0.2, 0.2);
    expect(motion.last?.phase).toBe('tracking-lost');
    motion.move(176, 800);
    motion.hold(176);
    expect(motion.last?.count).toBe(0);
    motion.rep();
    expect(motion.last?.count).toBe(1);
  });

  it('discards a partial repetition if the camera stops producing frames', () => {
    const motion = new Movement(new RepCounter('squat'));
    motion.hold(176);
    motion.move(82, 1000);
    motion.time += 1500;
    motion.move(176, 800);
    motion.hold(176);
    expect(motion.last?.count).toBe(0);
  });

  it('does not switch to the other side during a set when the chosen side disappears', () => {
    const motion = new Movement(new RepCounter('squat'));
    motion.hold(176);
    for (let n = 0; n < 30; n++) motion.sample(n < 15 ? 80 : 176, 0.1, 0.99);
    expect(motion.last?.count).toBe(0);
    expect(motion.last?.phase).toBe('tracking-lost');
    motion.counter.reset();
    for (let n = 0; n < 8; n++) motion.sample(176, 0.1, 0.99);
    expect(motion.last?.phase).toBe('ready');
  });

  it('handles empty frames and resets count and side for a new set', () => {
    const motion = new Movement(new RepCounter('squat'));
    motion.hold(176);
    motion.rep();
    motion.counter.reset();
    expect(motion.counter.update([], 0, 960, 720)).toMatchObject({ count: 0, angle: null, rep: null, phase: 'tracking-lost' });
  });

  it('ignores duplicate or reversed timestamps', () => {
    const counter = new RepCounter('squat');
    counter.update(pose(176), 100, 960, 720);
    counter.update(pose(176), 300, 960, 720);
    for (const timestamp of [300, 200]) {
      const result = counter.update(pose(82), timestamp, 960, 720);
      expect(result.count).toBe(0);
      expect(result.angle).toBeCloseTo(176);
    }
  });
});

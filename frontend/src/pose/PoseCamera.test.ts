import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PoseCamera } from './PoseCamera';

const mediapipe = vi.hoisted(() => ({ resolve: vi.fn(), create: vi.fn() }));
vi.mock('@mediapipe/tasks-vision', () => ({
  FilesetResolver: { forVisionTasks: mediapipe.resolve },
  PoseLandmarker: { createFromOptions: mediapipe.create },
}));

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((ok, fail) => { resolve = ok; reject = fail; });
  return { promise, resolve, reject };
}

describe('PoseCamera lifecycle', () => {
  let getUserMedia: ReturnType<typeof vi.fn>;
  let stopTrack: ReturnType<typeof vi.fn>;
  let detector: { close: ReturnType<typeof vi.fn>; detectForVideo: ReturnType<typeof vi.fn> };
  let stream: MediaStream;
  let video: HTMLVideoElement;
  let camera: PoseCamera;

  beforeEach(() => {
    vi.clearAllMocks();
    stopTrack = vi.fn();
    stream = { getTracks: () => [{ stop: stopTrack }] } as unknown as MediaStream;
    getUserMedia = vi.fn().mockResolvedValue(stream);
    vi.stubGlobal('navigator', { mediaDevices: { getUserMedia } });
    vi.stubGlobal('requestAnimationFrame', vi.fn().mockReturnValue(123));
    vi.stubGlobal('cancelAnimationFrame', vi.fn());
    detector = { close: vi.fn(), detectForVideo: vi.fn() };
    mediapipe.resolve.mockResolvedValue({});
    mediapipe.create.mockResolvedValue(detector);
    video = { srcObject: null, muted: false, playsInline: false, play: vi.fn().mockResolvedValue(undefined), pause: vi.fn() } as unknown as HTMLVideoElement;
    camera = new PoseCamera();
  });

  afterEach(() => {
    camera.stop();
    vi.unstubAllGlobals();
  });

  it('requests video without audio and releases the stream and detector on stop', async () => {
    const onError = vi.fn();
    expect(getUserMedia).not.toHaveBeenCalled();
    await camera.start(video, vi.fn(), onError);
    expect(getUserMedia).toHaveBeenCalledWith(expect.objectContaining({ audio: false }));
    expect(video.srcObject).toBe(stream);
    expect(video.muted).toBe(true);
    camera.stop();
    expect(stopTrack).toHaveBeenCalledTimes(1);
    expect(detector.close).toHaveBeenCalledTimes(1);
    expect(video.srcObject).toBeNull();
    expect(onError).not.toHaveBeenCalled();
  });

  it('falls back to CPU if GPU model initialization fails', async () => {
    mediapipe.create.mockRejectedValueOnce(new Error('WebGL unavailable')).mockResolvedValueOnce(detector);
    await camera.start(video, vi.fn(), vi.fn());
    expect(mediapipe.create.mock.calls[0][1].baseOptions.delegate).toBe('GPU');
    expect(mediapipe.create.mock.calls[1][1].baseOptions.delegate).toBe('CPU');
    expect(getUserMedia).toHaveBeenCalledTimes(1);
  });

  it('closes a late model result without requesting permission after cancellation', async () => {
    const pending = deferred<typeof detector>();
    mediapipe.create.mockReturnValue(pending.promise);
    const start = camera.start(video, vi.fn(), vi.fn());
    await vi.waitFor(() => expect(mediapipe.create).toHaveBeenCalled());
    camera.stop();
    pending.resolve(detector);
    await start;
    expect(detector.close).toHaveBeenCalledTimes(1);
    expect(getUserMedia).not.toHaveBeenCalled();
  });

  it('releases a stream returned after the user cancels the permission request', async () => {
    const pending = deferred<MediaStream>();
    getUserMedia.mockReturnValue(pending.promise);
    const start = camera.start(video, vi.fn(), vi.fn());
    await vi.waitFor(() => expect(getUserMedia).toHaveBeenCalled());
    camera.stop();
    pending.resolve(stream);
    await start;
    expect(stopTrack).toHaveBeenCalledTimes(1);
    expect(detector.close).toHaveBeenCalledTimes(1);
    expect(video.srcObject).toBeNull();
  });

  it('cleans up on permission denial and reports a useful fallback', async () => {
    const denied = new Error('Permission denied');
    denied.name = 'NotAllowedError';
    getUserMedia.mockRejectedValue(denied);
    const onError = vi.fn();
    await camera.start(video, vi.fn(), onError);
    expect(detector.close).toHaveBeenCalledTimes(1);
    expect(onError).toHaveBeenCalledWith(expect.stringContaining('log sets manually'));
  });
});

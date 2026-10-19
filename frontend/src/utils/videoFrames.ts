export function frameAtTime(time: number, fps: number, frameCount: number): number {
  if (!Number.isFinite(time) || fps <= 0 || frameCount <= 0) return 0;
  const position = time * fps;
  const arithmeticTolerance = Number.EPSILON * Math.max(1, Math.abs(position));
  return Math.min(frameCount - 1, Math.max(0, Math.floor(position + arithmeticTolerance)));
}

export function selectVideoFrame(frameIndex: number, fps: number, frameCount: number): { frame: number; time: number } {
  const frame = Math.min(frameCount - 1, Math.max(0, Math.trunc(frameIndex)));
  return { frame, time: (frame + 0.5) / fps };
}

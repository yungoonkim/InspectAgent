import type { RoiRect } from '../types/roi';

interface Source { video_id: string; source_revision: string; width: number; height: number }

export function sourceKey(source: Source | null): string {
  return source ? JSON.stringify([source.video_id, source.source_revision, source.width, source.height]) : '';
}

export function sameSource(first: Source | null, second: Source | null): boolean {
  return !!first && !!second && sourceKey(first) === sourceKey(second);
}

export function roiFits(roi: RoiRect, source: Source | null): boolean {
  return !!source && Object.values(roi).every(value => Number.isSafeInteger(value))
    && roi.x >= 0 && roi.y >= 0 && roi.width >= 16 && roi.height >= 16
    && roi.x + roi.width <= source.width && roi.y + roi.height <= source.height;
}

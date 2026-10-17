/**
 * VisionInsight Client-Side Image Crop Utility
 * Pure 1:1 pixel extraction from server-generated Grab PNG buffers
 */

import type { RoiRect } from '../types/roi';

/**
 * Loads an HTMLImageElement asynchronously from an image URL or Blob URL
 */
export function loadImageFromUrl(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => resolve(img);
    img.onerror = (err) => reject(new Error(`Failed to load image from URL: ${err}`));
    img.src = url;
  });
}

/**
 * Extracts exact 1:1 unscaled pixels corresponding to roi [x, y, width, height]
 * from the source image.
 * Returns both a visual Data URL (PNG) and the raw ImageData pixel array.
 */
export function cropExactPixels(
  sourceImage: HTMLImageElement,
  roi: RoiRect
): { cropBlobUrl: string; imageData: ImageData } {
  const canvas = document.createElement('canvas');
  canvas.width = roi.width;
  canvas.height = roi.height;

  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  if (!ctx) {
    throw new Error('Could not obtain 2D rendering context for image crop');
  }

  // Draw exactly the sub-rectangle with 1:1 mapping
  ctx.drawImage(
    sourceImage,
    roi.x,
    roi.y,
    roi.width,
    roi.height,
    0,
    0,
    roi.width,
    roi.height
  );

  const imageData = ctx.getImageData(0, 0, roi.width, roi.height);
  const cropBlobUrl = canvas.toDataURL('image/png');

  return {
    cropBlobUrl,
    imageData,
  };
}

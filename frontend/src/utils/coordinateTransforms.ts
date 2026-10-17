/**
 * VisionInsight Coordinate Transformation & Math Utilities
 * Precision mappings between screen display viewports and 1920×480 native frame coordinates
 */

import type { RoiRect, ViewportMapping } from '../types/roi';

/**
 * Calculates display area and scale factor for object-fit: contain
 */
export function calculateViewportMapping(
  containerWidth: number,
  containerHeight: number,
  imageWidth = 1920,
  imageHeight = 480
): ViewportMapping {
  if (containerWidth <= 0 || containerHeight <= 0) {
    return {
      offsetX: 0,
      offsetY: 0,
      displayWidth: imageWidth,
      displayHeight: imageHeight,
      scaleX: 1,
      scaleY: 1,
    };
  }

  const containerAspect = containerWidth / containerHeight;
  const imageAspect = imageWidth / imageHeight;

  let displayWidth: number;
  let displayHeight: number;
  let offsetX: number;
  let offsetY: number;

  if (containerAspect > imageAspect) {
    // Container is wider than image aspect ratio (pillarboxed)
    displayHeight = containerHeight;
    displayWidth = containerHeight * imageAspect;
    offsetX = (containerWidth - displayWidth) / 2;
    offsetY = 0;
  } else {
    // Container is taller than image aspect ratio (letterboxed)
    displayWidth = containerWidth;
    displayHeight = containerWidth / imageAspect;
    offsetX = 0;
    offsetY = (containerHeight - displayHeight) / 2;
  }

  const scaleX = displayWidth / imageWidth;
  const scaleY = displayHeight / imageHeight;

  return {
    offsetX,
    offsetY,
    displayWidth,
    displayHeight,
    scaleX,
    scaleY,
  };
}

/**
 * Converts screen pointer coordinates (relative to container) to native image pixel coordinates
 */
export function screenToImageCoords(
  screenX: number,
  screenY: number,
  mapping: ViewportMapping,
  imageWidth = 1920,
  imageHeight = 480
): { x: number; y: number } {
  const rawX = (screenX - mapping.offsetX) / mapping.scaleX;
  const rawY = (screenY - mapping.offsetY) / mapping.scaleY;

  const clampedX = Math.min(Math.max(0, Math.round(rawX)), imageWidth);
  const clampedY = Math.min(Math.max(0, Math.round(rawY)), imageHeight);

  return { x: clampedX, y: clampedY };
}

/**
 * Converts native image ROI to screen coordinates for rendering the overlay box
 */
export function imageToScreenRect(
  roi: RoiRect,
  mapping: ViewportMapping
): { left: number; top: number; width: number; height: number } {
  return {
    left: mapping.offsetX + roi.x * mapping.scaleX,
    top: mapping.offsetY + roi.y * mapping.scaleY,
    width: roi.width * mapping.scaleX,
    height: roi.height * mapping.scaleY,
  };
}

/**
 * Clamps ROI rectangle to stay strictly within image bounds with integer coordinates
 */
export function clampRoiRect(
  rect: RoiRect,
  imageWidth = 1920,
  imageHeight = 480,
  minSize = 30
): RoiRect {
  let width = Math.round(Math.max(minSize, Math.min(rect.width, imageWidth)));
  let height = Math.round(Math.max(minSize, Math.min(rect.height, imageHeight)));

  let x = Math.round(Math.max(0, Math.min(rect.x, imageWidth - width)));
  let y = Math.round(Math.max(0, Math.min(rect.y, imageHeight - height)));

  if (x + width > imageWidth) {
    x = imageWidth - width;
  }
  if (y + height > imageHeight) {
    y = imageHeight - height;
  }

  return {
    x: Math.max(0, x),
    y: Math.max(0, y),
    width,
    height,
  };
}

/**
 * Computes Gray Value (GV) from RGB using standard machine vision / OpenCV weighting:
 * Gray = round(0.299*R + 0.587*G + 0.114*B)
 */
export function computeGrayValue(r: number, g: number, b: number): number {
  const gv = Math.round(0.299 * r + 0.587 * g + 0.114 * b);
  return Math.min(255, Math.max(0, gv));
}

/**
 * Computes ROI Center coordinates (centerX = x + width / 2, centerY = y + height / 2)
 * Keeps .5 decimals without integer rounding as per specification
 */
export function computeRoiCenter(roi: RoiRect): { centerX: number; centerY: number } {
  return {
    centerX: roi.x + roi.width / 2,
    centerY: roi.y + roi.height / 2,
  };
}

/**
 * Formats ROI coordinates as Center representation:
 * e.g. "CENTER (830, 259.5) · 286×289 px"
 */
export function formatRoiCenter(roi: RoiRect): string {
  const { centerX, centerY } = computeRoiCenter(roi);
  return `CENTER (${centerX}, ${centerY}) · ${roi.width}×${roi.height} px`;
}

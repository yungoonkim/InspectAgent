/**
 * Image transformation and coordinate math utilities for 600x600 precision vision viewport.
 * Supports:
 * 1. Cursor Anchored Zoom In (Wheel Up)
 * 2. Center Directed Zoom Out (Wheel Down)
 * 3. Viewport Center Button Zoom (+, -, presets)
 * 4. Pixel Inspector forward & inverse coordinate transformations
 */

export const WORKSPACE_SIZE = 600;
export const MIN_ZOOM = 1.0;
export const MAX_ZOOM = 40.0;
export const ZOOM_PRESETS = [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 40.0] as const;

export interface Point {
  x: number;
  y: number;
}

export interface ViewTransform {
  zoom: number;
  pan: Point;
}

/**
 * Clamp zoom to [MIN_ZOOM, MAX_ZOOM] with 2 decimal precision.
 */
export function clampZoom(val: number): number {
  return Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, Math.round(val * 100) / 100));
}

/**
 * Find next/previous zoom level in standard inspection presets.
 * If currentZoom is exactly on a preset, steps to next/prev.
 * If between presets, steps to next higher/lower preset.
 */
export function getStepZoom(currentZoom: number, isZoomIn: boolean): number {
  const EPS = 0.005;
  if (isZoomIn) {
    for (const preset of ZOOM_PRESETS) {
      if (preset > currentZoom + EPS) {
        return preset;
      }
    }
    return MAX_ZOOM;
  } else {
    for (let i = ZOOM_PRESETS.length - 1; i >= 0; i--) {
      const preset = ZOOM_PRESETS[i];
      if (preset < currentZoom - EPS) {
        return preset;
      }
    }
    return MIN_ZOOM;
  }
}

/**
 * Calculate origin (top-left) of unrotated image in 600x600 canvas coordinate space.
 */
export function calculateOrigin(
  targetW: number,
  targetH: number,
  zoom: number,
  pan: Point
): Point {
  return {
    x: (WORKSPACE_SIZE - targetW * zoom) / 2 + pan.x,
    y: (WORKSPACE_SIZE - targetH * zoom) / 2 + pan.y,
  };
}

/**
 * Convert canvas viewport coordinate (0..600) to image pixel coordinate.
 */
export function viewportToImagePixel(
  canvasX: number,
  canvasY: number,
  targetW: number,
  targetH: number,
  zoom: number,
  pan: Point
): { imgX: number; imgY: number; isOverImage: boolean } {
  const origin = calculateOrigin(targetW, targetH, zoom, pan);
  const imgX = (canvasX - origin.x) / zoom;
  const imgY = (canvasY - origin.y) / zoom;
  const isOverImage = imgX >= 0 && imgX < targetW && imgY >= 0 && imgY < targetH;
  return { imgX, imgY, isOverImage };
}

/**
 * Convert image pixel coordinate to canvas viewport coordinate (0..600).
 */
export function imagePixelToViewport(
  imgX: number,
  imgY: number,
  targetW: number,
  targetH: number,
  zoom: number,
  pan: Point
): Point {
  const origin = calculateOrigin(targetW, targetH, zoom, pan);
  return {
    x: origin.x + imgX * zoom,
    y: origin.y + imgY * zoom,
  };
}

/**
 * Compute next transform when mouse wheel event occurs.
 *
 * Requirements:
 * - Wheel Up (isZoomIn = true):
 *   - If pointer is over real image pixel: Cursor Anchored Zoom In.
 *     The exact image pixel under pointerX, pointerY remains at pointerX, pointerY.
 *   - If pointer is over black padding: Viewport Center Zoom In.
 * - Wheel Down (isZoomIn = false):
 *   - Center Directed Zoom Out.
 *     Reference point is viewport center (300, 300).
 *     Pan scales proportionally by nextZoom / currentZoom.
 *     When nextZoom reaches 1.0 (100%), pan resets to (0, 0), naturally restoring center alignment.
 */
export function computeWheelTransform({
  currentTransform,
  deltaY,
  pointerX,
  pointerY,
  targetW,
  targetH,
}: {
  currentTransform: ViewTransform;
  deltaY: number;
  pointerX: number;
  pointerY: number;
  targetW: number;
  targetH: number;
}): ViewTransform {
  if (targetW <= 0 || targetH <= 0) return currentTransform;

  const { zoom: currentZoom, pan } = currentTransform;
  const isZoomIn = deltaY < 0;
  const nextZoom = getStepZoom(currentZoom, isZoomIn);

  // Boundary check: already at min or max
  if (Math.abs(nextZoom - currentZoom) < 0.001) {
    return currentTransform;
  }

  const ratio = nextZoom / currentZoom;
  const viewportCenterX = WORKSPACE_SIZE / 2; // 300
  const viewportCenterY = WORKSPACE_SIZE / 2; // 300

  if (isZoomIn) {
    // Check if pointer is over image or padding
    const { isOverImage } = viewportToImagePixel(
      pointerX,
      pointerY,
      targetW,
      targetH,
      currentZoom,
      pan
    );

    if (isOverImage) {
      // Cursor Anchored Zoom In:
      // nextPan = pan + (pointer - viewportCenter - pan) * (1 - ratio)
      const nextPanX = pan.x + (pointerX - viewportCenterX - pan.x) * (1 - ratio);
      const nextPanY = pan.y + (pointerY - viewportCenterY - pan.y) * (1 - ratio);
      return {
        zoom: nextZoom,
        pan: {
          x: Math.round(nextPanX * 100) / 100,
          y: Math.round(nextPanY * 100) / 100,
        },
      };
    } else {
      // Fallback: Pointer is over black padding -> Viewport Center Zoom
      const nextPanX = pan.x * ratio;
      const nextPanY = pan.y * ratio;
      return {
        zoom: nextZoom,
        pan: {
          x: Math.round(nextPanX * 100) / 100,
          y: Math.round(nextPanY * 100) / 100,
        },
      };
    }
  } else {
    // Center Directed Zoom Out:
    // When returning to 1.0 (100%), restore center alignment (pan = 0, 0)
    if (nextZoom <= 1.0 || Math.abs(nextZoom - 1.0) < 0.001) {
      return {
        zoom: 1.0,
        pan: { x: 0, y: 0 },
      };
    }

    // Proportionally shrink pan offset towards center
    const nextPanX = pan.x * ratio;
    const nextPanY = pan.y * ratio;
    return {
      zoom: nextZoom,
      pan: {
        x: Math.round(nextPanX * 100) / 100,
        y: Math.round(nextPanY * 100) / 100,
      },
    };
  }
}

/**
 * Compute next transform for toolbar buttons (+, -, presets).
 * Always zooms around viewport center (300, 300) without depending on pointer position.
 */
export function computeButtonTransform({
  currentTransform,
  targetZoom,
}: {
  currentTransform: ViewTransform;
  targetZoom: number;
}): ViewTransform {
  const { zoom: currentZoom, pan } = currentTransform;
  const nextZoom = clampZoom(targetZoom);

  if (Math.abs(nextZoom - currentZoom) < 0.001) {
    return currentTransform;
  }

  if (nextZoom <= 1.0) {
    return {
      zoom: 1.0,
      pan: { x: 0, y: 0 },
    };
  }

  const ratio = nextZoom / currentZoom;
  return {
    zoom: nextZoom,
    pan: {
      x: Math.round(pan.x * ratio * 100) / 100,
      y: Math.round(pan.y * ratio * 100) / 100,
    },
  };
}

/**
 * VisionInsight ROI & Crop Data Types
 * Machine Vision Inspection Specification
 */

export interface RoiRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export type RoiState = 'NO_ROI' | 'EDITING' | 'APPLIED';

export interface RoiCenter {
  centerX: number;
  centerY: number;
}

export interface ViewportMapping {
  offsetX: number;
  offsetY: number;
  displayWidth: number;
  displayHeight: number;
  scaleX: number;
  scaleY: number;
}

export interface CropData {
  cropBlobUrl: string;
  imageData: ImageData;
  roi: RoiRect;
  width: number;
  height: number;
  captureId: string;
  videoId: string;
  sourceRevision: string;
  frameIndex: number;
  createdAt: string;
}

export interface PixelInspectionInfo {
  grabX: number | null;
  grabY: number | null;
  localX: number | null;
  localY: number | null;
  r: number;
  g: number;
  b: number;
  gv: number;
  isPadding: boolean;
}

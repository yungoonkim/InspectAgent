import React, { useRef, useState, useEffect } from 'react';
import {
  Image as ImageIcon,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  Crosshair,
  Grid,
  Layers,
  Tag,
  Info,
  Flame,
} from 'lucide-react';
import type { CaptureMetadata } from '../types/video';
import type { CropData, PixelInspectionInfo } from '../types/roi';
import type { InspectionResponse } from '../types/inspection';
import { computeGrayValue } from '../utils/coordinateTransforms';
import {
  getInspectionImageUrl,
  getGrabInspectionImageUrl,
  getInspectionAnomalyMap,
  getInspectionAnomalyMapOverlayUrl,
  type AnomalyMapMetadata,
} from '../api/inspection';
import {
  WORKSPACE_SIZE,
  MIN_ZOOM,
  MAX_ZOOM,
  ZOOM_PRESETS,
  type ViewTransform,
  calculateOrigin,
  computeWheelTransform,
  computeButtonTransform,
  getStepZoom,
} from '../utils/imageTransform';
import {
  isAnomalyMapCompatible,
  isFixtureInspection,
  isInspectionImageCurrent,
  startInspectionHeatmapLoad,
  type InspectionImageIdentity,
} from '../utils/step4ImageState';

interface ImageViewProps {
  capture: CaptureMetadata | null;
  imageBlobUrl: string | null;
  cropData: CropData | null;
  isLoading: boolean;
  error: string | null;
  currentInspection?: InspectionResponse | null;
}

interface LoadedStaticImage {
  imageId: string;
  inspectionId: string;
  imageElement: HTMLImageElement;
  imageData: ImageData;
  width: number;
  height: number;
}

export const ImageView: React.FC<ImageViewProps> = ({
  capture,
  imageBlobUrl,
  cropData,
  isLoading,
  error,
  currentInspection,
}) => {
  // Source Mode: 'CAPTURE' (LiveView Grab ROI crop) vs 'REGISTERED' (Actual static inspection image)
  const [activeSource, setActiveSource] = useState<'CAPTURE' | 'REGISTERED'>('REGISTERED');

  // Sub-view mode for CAPTURE: 'focus' (600x600 precision crop) or 'overview' (full 1920x480 frame)
  const [userCaptureViewMode, setUserCaptureViewMode] = useState<'focus' | 'overview'>('focus');
  const captureViewMode = cropData ? userCaptureViewMode : 'overview';

  // Zoom & Pan atomic transform state for 600x600 workspace (default 100% / zoom = 1.0)
  const [transform, setTransform] = useState<ViewTransform>({
    zoom: 1.0,
    pan: { x: 0, y: 0 },
  });
  const { zoom, pan } = transform;

  // Synchronous ref to prevent stale closures and lag during rapid wheel events
  const transformRef = useRef<ViewTransform>({
    zoom: 1.0,
    pan: { x: 0, y: 0 },
  });

  const updateTransform = (next: ViewTransform) => {
    transformRef.current = next;
    setTransform(next);
    setInspector(null);
  };

  const [showGrid, setShowGrid] = useState<boolean>(true);
  const [isPanning, setIsPanning] = useState<boolean>(false);
  const panStartRef = useRef<{ x: number; y: number; initialPan: { x: number; y: number } }>({
    x: 0,
    y: 0,
    initialPan: { x: 0, y: 0 },
  });

  // Pixel Inspector state
  const [inspectorState, setInspectorState] = useState<{
    source: LoadedStaticImage | CropData | null;
    value: PixelInspectionInfo;
  } | null>(null);

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const canvasWrapperRef = useRef<HTMLDivElement | null>(null);
  const [cropImgElement, setCropImgElement] = useState<HTMLImageElement | null>(null);

  // Registered Static Image state
  const [loadedStaticImg, setStaticImg] = useState<LoadedStaticImage | null>(null);
  const [staticLoading, setStaticLoading] = useState<boolean>(false);
  const [staticError, setStaticError] = useState<string | null>(null);
  const staticImg = isInspectionImageCurrent(currentInspection, loadedStaticImg)
    ? loadedStaticImg : null;
  const inspectorSource = activeSource === 'REGISTERED' ? staticImg : cropData;
  const inspector = inspectorState?.source === inspectorSource ? inspectorState.value : null;
  const setInspector = (value: PixelInspectionInfo | null) => {
    setInspectorState(value ? { source: inspectorSource, value } : null);
  };

  // Day 7 Step 4: PatchCore Anomaly Map state for REGISTERED inspection images
  const [heatmapState, setHeatmapState] = useState<(InspectionImageIdentity & {
    status: 'LOADING' | 'AVAILABLE' | 'NOT_AVAILABLE';
    metadata: AnomalyMapMetadata | null;
    imageElement: HTMLImageElement | null;
  }) | null>(null);
  const [heatmapSelection, setHeatmapSelection] = useState<InspectionImageIdentity | null>(null);
  const [heatmapOpacity, setHeatmapOpacity] = useState<number>(0.6);
  const isMockFixture = isFixtureInspection(currentInspection);
  const isHeatmapCurrent = isInspectionImageCurrent(currentInspection, heatmapState);
  const isHeatmapReady = !!staticImg && isHeatmapCurrent && !!heatmapState?.imageElement &&
    isAnomalyMapCompatible(currentInspection, heatmapState.metadata, staticImg, {
      width: heatmapState.imageElement.naturalWidth,
      height: heatmapState.imageElement.naturalHeight,
    });
  const anomalyMapMeta = isHeatmapReady ? heatmapState?.metadata : null;
  const overlayImgElement = isHeatmapReady ? heatmapState?.imageElement : null;
  const showHeatmap = isHeatmapReady && isInspectionImageCurrent(currentInspection, heatmapSelection);
  const anomalyMapStatus = !currentInspection ? 'IDLE' : isMockFixture ? 'NOT_AVAILABLE' :
    !isHeatmapCurrent ? 'LOADING' : heatmapState?.status === 'AVAILABLE' && !isHeatmapReady
      ? staticImg ? 'NOT_AVAILABLE' : 'LOADING' : heatmapState?.status;

  // 1. Load LiveView Crop Image element when cropData changes and reset to 100% center
  useEffect(() => {
    if (!cropData) return;
    let isCurrent = true;
    const img = new Image();
    img.src = cropData.cropBlobUrl;
    img.onload = () => {
      if (isCurrent) {
        setCropImgElement(img);
        setUserCaptureViewMode('focus');
        setActiveSource('CAPTURE');
        updateTransform({ zoom: 1.0, pan: { x: 0, y: 0 } });
      }
    };
    return () => {
      isCurrent = false;
    };
  }, [cropData]);

  // 2. Load Registered Static Image when currentInspection changes
  useEffect(() => {
    if (!currentInspection || !currentInspection.image_id) {
      setStaticImg(null);
      setStaticLoading(false);
      setStaticError(null);
      return;
    }

    const targetImageId = currentInspection.image_id;
    const targetInspectionId = currentInspection.inspection_id;
    let isCurrent = true;

    setStaticLoading(true);
    setStaticImg(null);
    setStaticError(null);

    const url = currentInspection.metrics?.input_source === 'LIVEVIEW_GRAB'
      ? getGrabInspectionImageUrl(targetInspectionId) : getInspectionImageUrl(targetImageId);
    const img = new Image();
    img.crossOrigin = currentInspection.metrics?.input_source === 'LIVEVIEW_GRAB' ? 'use-credentials' : 'anonymous';

    img.onload = () => {
      if (!isCurrent) return;
      try {
        const offscreen = document.createElement('canvas');
        const w = img.naturalWidth || img.width;
        const h = img.naturalHeight || img.height;
        offscreen.width = w;
        offscreen.height = h;
        const ctx = offscreen.getContext('2d', { willReadFrequently: true });
        if (ctx) {
          ctx.drawImage(img, 0, 0);
          const imageData = ctx.getImageData(0, 0, w, h);
          setStaticImg({
            imageId: targetImageId,
            inspectionId: targetInspectionId,
            imageElement: img,
            imageData,
            width: w,
            height: h,
          });
          setStaticLoading(false);
          setActiveSource('REGISTERED');
          updateTransform({ zoom: 1.0, pan: { x: 0, y: 0 } });
        } else {
          setStaticError('픽셀 데이터를 읽을 Canvas 2D 컨텍스트를 생성할 수 없습니다.');
          setStaticLoading(false);
        }
      } catch (err: any) {
        if (isCurrent) {
          setStaticError(`픽셀 데이터 추출 실패: ${err.message}`);
          setStaticLoading(false);
        }
      }
    };

    img.onerror = () => {
      if (!isCurrent) return;
      setStaticError(`정적 이미지 로드 실패: ${targetImageId}`);
      setStaticLoading(false);
    };

    img.src = url;

    return () => {
      isCurrent = false;
    };
  }, [currentInspection]);

  // 3. Load Anomaly Map sidecar when currentInspection changes (Day 7 Step 4)
  useEffect(() => {
    setHeatmapSelection(null);
    if (!currentInspection || !currentInspection.inspection_id) {
      setHeatmapState(null);
      return;
    }

    const identity = {
      inspectionId: currentInspection.inspection_id,
      imageId: currentInspection.image_id,
    };
    setHeatmapState({ ...identity, status: 'LOADING', metadata: null, imageElement: null });
    return startInspectionHeatmapLoad(currentInspection, {
      getMetadata: getInspectionAnomalyMap,
      getOverlayUrl: getInspectionAnomalyMapOverlayUrl,
      createImage: () => new Image(),
      onAvailable: (metadata, imageElement) => {
        setHeatmapState({ ...identity, status: 'AVAILABLE', metadata, imageElement });
      },
      onUnavailable: () => {
        setHeatmapState({ ...identity, status: 'NOT_AVAILABLE', metadata: null, imageElement: null });
      },
    });
  }, [currentInspection]);

  // Prevent browser page scroll when wheeling inside the 600x600 workspace
  useEffect(() => {
    const el = canvasWrapperRef.current;
    if (!el) return;

    const handleNativeWheel = (e: WheelEvent) => {
      e.preventDefault();
      const isPrecisionMode =
        (activeSource === 'CAPTURE' && captureViewMode === 'focus' && !!cropData) ||
        (activeSource === 'REGISTERED' && !!staticImg);

      if (!isPrecisionMode) return;

      const canvas = canvasRef.current;
      if (!canvas) return;

      const rect = canvas.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) return;

      const scaleX = WORKSPACE_SIZE / rect.width;
      const scaleY = WORKSPACE_SIZE / rect.height;
      const pointerX = Math.max(0, Math.min(WORKSPACE_SIZE, (e.clientX - rect.left) * scaleX));
      const pointerY = Math.max(0, Math.min(WORKSPACE_SIZE, (e.clientY - rect.top) * scaleY));

      let targetW = 0;
      let targetH = 0;
      let targetImageData: ImageData | null = null;
      let grabRoiX: number | null = null;
      let grabRoiY: number | null = null;

      if (activeSource === 'REGISTERED' && staticImg) {
        targetW = staticImg.width;
        targetH = staticImg.height;
        targetImageData = staticImg.imageData;
      } else if (activeSource === 'CAPTURE' && cropData) {
        targetW = cropData.width;
        targetH = cropData.height;
        targetImageData = cropData.imageData;
        grabRoiX = cropData.roi.x;
        grabRoiY = cropData.roi.y;
      }

      if (targetW <= 0 || targetH <= 0) return;

      const nextTransform = computeWheelTransform({
        currentTransform: transformRef.current,
        deltaY: e.deltaY,
        pointerX,
        pointerY,
        targetW,
        targetH,
      });

      updateTransform(nextTransform);

      // Instantly refresh pixel inspector under pointer at the new zoom/pan
      if (targetImageData) {
        const origin = calculateOrigin(targetW, targetH, nextTransform.zoom, nextTransform.pan);
        const localX = Math.floor((pointerX - origin.x) / nextTransform.zoom);
        const localY = Math.floor((pointerY - origin.y) / nextTransform.zoom);

        if (localX >= 0 && localX < targetW && localY >= 0 && localY < targetH) {
          const pixelIdx = (localY * targetW + localX) * 4;
          const r = targetImageData.data[pixelIdx];
          const g = targetImageData.data[pixelIdx + 1];
          const b = targetImageData.data[pixelIdx + 2];
          const gv = computeGrayValue(r, g, b);

          setInspector({
            grabX: grabRoiX !== null ? grabRoiX + localX : null,
            grabY: grabRoiY !== null ? grabRoiY + localY : null,
            localX,
            localY,
            r,
            g,
            b,
            gv,
            isPadding: false,
          });
        } else {
          setInspector({
            grabX: null,
            grabY: null,
            localX: null,
            localY: null,
            r: 0,
            g: 0,
            b: 0,
            gv: 0,
            isPadding: true,
          });
        }
      }
    };

    el.addEventListener('wheel', handleNativeWheel, { passive: false });
    return () => {
      el.removeEventListener('wheel', handleNativeWheel);
    };
  }, [activeSource, captureViewMode, cropData, staticImg, isLoading, staticLoading]);

  // Render 600x600 precision inspection canvas (Shared by both Product Focus Crop and Registered Static Image)
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const WORKSPACE_SIZE = 600;
    canvas.width = WORKSPACE_SIZE;
    canvas.height = WORKSPACE_SIZE;

    // Fill entire 600x600 workspace with strict RGB(0, 0, 0)
    ctx.fillStyle = '#000000';
    ctx.fillRect(0, 0, WORKSPACE_SIZE, WORKSPACE_SIZE);

    // Determine active target image
    let targetElement: HTMLImageElement | null = null;
    let targetImageData: ImageData | null = null;
    let targetW = 0;
    let targetH = 0;

    if (activeSource === 'REGISTERED') {
      if (staticImg) {
        targetElement = staticImg.imageElement;
        targetImageData = staticImg.imageData;
        targetW = staticImg.width;
        targetH = staticImg.height;
      }
    } else {
      if (cropData && cropImgElement) {
        targetElement = cropImgElement;
        targetImageData = cropData.imageData;
        targetW = cropData.width;
        targetH = cropData.height;
      }
    }

    if (!targetElement || !targetImageData || targetW <= 0 || targetH <= 0) {
      return;
    }

    // Nearest-neighbor rendering for crisp machine vision inspection
    ctx.imageSmoothingEnabled = false;

    // Calculate unscaled center offset at 100% (zoom = 1) plus pan
    const origin = calculateOrigin(targetW, targetH, zoom, pan);
    const originX = origin.x;
    const originY = origin.y;

    // Draw Source Image 1:1 unscaled
    ctx.drawImage(targetElement, originX, originY, targetW * zoom, targetH * zoom);

    // Day 7 Step 4: Draw PatchCore Anomaly Heatmap Overlay (REGISTERED mode only)
    if (activeSource === 'REGISTERED' && showHeatmap && overlayImgElement) {
      ctx.save();
      ctx.globalAlpha = Math.max(0.1, Math.min(1.0, heatmapOpacity));
      ctx.drawImage(overlayImgElement, originX, originY, targetW * zoom, targetH * zoom);
      ctx.restore();
    }

    // Subtle crop / image boundary outline
    ctx.strokeStyle = '#38bdf8';
    ctx.lineWidth = 1;
    ctx.strokeRect(originX, originY, targetW * zoom, targetH * zoom);

    // Visible pixel range calculation for viewport culling
    const startX = Math.max(0, Math.floor(-originX / zoom));
    const endX = Math.min(targetW - 1, Math.ceil((WORKSPACE_SIZE - originX) / zoom));
    const startY = Math.max(0, Math.floor(-originY / zoom));
    const endY = Math.min(targetH - 1, Math.ceil((WORKSPACE_SIZE - originY) / zoom));

    // 2. Draw pixel grid if zoomed in >= 400% (4x)
    if (showGrid && zoom >= 4.0) {
      ctx.strokeStyle = zoom >= 32.0 ? 'rgba(255, 255, 255, 0.28)' : 'rgba(255, 255, 255, 0.15)';
      ctx.lineWidth = 0.5;

      // Vertical lines for visible columns
      for (let x = startX; x <= endX + 1; x++) {
        const lineX = originX + x * zoom;
        if (lineX >= 0 && lineX <= WORKSPACE_SIZE) {
          ctx.beginPath();
          ctx.moveTo(lineX, Math.max(0, originY));
          ctx.lineTo(lineX, Math.min(WORKSPACE_SIZE, originY + targetH * zoom));
          ctx.stroke();
        }
      }

      // Horizontal lines for visible rows
      for (let y = startY; y <= endY + 1; y++) {
        const lineY = originY + y * zoom;
        if (lineY >= 0 && lineY <= WORKSPACE_SIZE) {
          ctx.beginPath();
          ctx.moveTo(Math.max(0, originX), lineY);
          ctx.lineTo(Math.min(WORKSPACE_SIZE, originX + targetW * zoom), lineY);
          ctx.stroke();
        }
      }
    }

    // 3. High-Zoom: Render actual Gray Value (0~255) numbers inside each visible pixel cell at 3200%~4000%
    if (showGrid && zoom >= 32.0) {
      ctx.font = zoom >= 36 ? 'bold 11px monospace' : 'bold 10px monospace';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';

      for (let y = startY; y <= endY; y++) {
        for (let x = startX; x <= endX; x++) {
          const pixelIdx = (y * targetW + x) * 4;
          const r = targetImageData.data[pixelIdx];
          const g = targetImageData.data[pixelIdx + 1];
          const b = targetImageData.data[pixelIdx + 2];
          const gv = computeGrayValue(r, g, b);

          const cx = originX + x * zoom + zoom / 2;
          const cy = originY + y * zoom + zoom / 2;

          ctx.fillStyle = gv > 128 ? '#0a0f1d' : '#f8fafc';
          ctx.fillText(String(gv), cx, cy);
        }
      }
    }

    // 4. Highlight hovered pixel if zoomed >= 1600%
    if (
      zoom >= 16.0 &&
      inspector &&
      inspector.localX !== null &&
      inspector.localY !== null &&
      !inspector.isPadding
    ) {
      const hx = originX + inspector.localX * zoom;
      const hy = originY + inspector.localY * zoom;
      ctx.strokeStyle = '#fbbf24'; // Amber highlight
      ctx.lineWidth = 2;
      ctx.strokeRect(hx, hy, zoom, zoom);

      // Floating GV tag above hovered cell
      if (zoom < 32.0) {
        const tagText = `GV ${inspector.gv}`;
        ctx.font = 'bold 10px monospace';
        const textWidth = ctx.measureText(tagText).width;
        const tagX = Math.max(4, Math.min(WORKSPACE_SIZE - textWidth - 10, hx + zoom / 2 - (textWidth + 10) / 2));
        const tagY = hy > 20 ? hy - 4 : hy + zoom + 12;

        ctx.fillStyle = 'rgba(15, 23, 42, 0.9)';
        ctx.fillRect(tagX - 4, tagY - 10, textWidth + 8, 14);
        ctx.strokeStyle = '#fbbf24';
        ctx.lineWidth = 1;
        ctx.strokeRect(tagX - 4, tagY - 10, textWidth + 8, 14);

        ctx.fillStyle = '#fbbf24';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'middle';
        ctx.fillText(tagText, tagX, tagY - 3);
      }
    }
  }, [
    activeSource,
    captureViewMode,
    isLoading,
    staticLoading,
    cropData,
    cropImgElement,
    staticImg,
    zoom,
    pan,
    showGrid,
    inspector,
    showHeatmap,
    overlayImgElement,
    heatmapOpacity,
  ]);

  // Zoom handlers with strict [1.0, 40.0] bounds and viewport-center scaling
  const handleZoomChange = (newZoom: number) => {
    const next = computeButtonTransform({
      currentTransform: transformRef.current,
      targetZoom: newZoom,
    });
    updateTransform(next);
  };

  const handleZoomStep = (factor: number) => {
    const isZoomIn = factor > 1;
    const targetZoom = getStepZoom(transformRef.current.zoom, isZoomIn);
    const next = computeButtonTransform({
      currentTransform: transformRef.current,
      targetZoom,
    });
    updateTransform(next);
  };

  const handleResetZoomPan = () => {
    updateTransform({ zoom: 1.0, pan: { x: 0, y: 0 } });
  };

  const handleResetPan = () => {
    updateTransform({ zoom: transformRef.current.zoom, pan: { x: 0, y: 0 } });
  };

  // Mouse Down for Pan
  const handlePointerDown = (e: React.PointerEvent) => {
    const isPrecisionMode =
      (activeSource === 'CAPTURE' && captureViewMode === 'focus') ||
      (activeSource === 'REGISTERED' && !!staticImg);

    if (!isPrecisionMode) return;

    setIsPanning(true);
    panStartRef.current = {
      x: e.clientX,
      y: e.clientY,
      initialPan: { ...transformRef.current.pan },
    };
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  };

  // Mouse Move for Pan & Pixel Inspector
  const handlePointerMove = (e: React.PointerEvent) => {
    if (!canvasRef.current) return;

    const isPrecisionMode =
      (activeSource === 'CAPTURE' && captureViewMode === 'focus' && !!cropData) ||
      (activeSource === 'REGISTERED' && !!staticImg);

    if (!isPrecisionMode) return;

    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return;

    // Pan motion
    if (isPanning) {
      const deltaX = (e.clientX - panStartRef.current.x) * WORKSPACE_SIZE / rect.width;
      const deltaY = (e.clientY - panStartRef.current.y) * WORKSPACE_SIZE / rect.height;
      updateTransform({
        zoom: transformRef.current.zoom,
        pan: {
          x: panStartRef.current.initialPan.x + deltaX,
          y: panStartRef.current.initialPan.y + deltaY,
        },
      });
      return;
    }

    // Determine dimensions and image data
    let targetW = 0;
    let targetH = 0;
    let targetImageData: ImageData | null = null;
    let grabRoiX: number | null = null;
    let grabRoiY: number | null = null;

    if (activeSource === 'REGISTERED') {
      if (staticImg) {
        targetW = staticImg.width;
        targetH = staticImg.height;
        targetImageData = staticImg.imageData;
      }
    } else {
      if (cropData) {
        targetW = cropData.width;
        targetH = cropData.height;
        targetImageData = cropData.imageData;
        grabRoiX = cropData.roi.x;
        grabRoiY = cropData.roi.y;
      }
    }

    if (!targetImageData || targetW <= 0 || targetH <= 0) return;

    // Canvas coordinates (0 to 600)
    const scaleX = WORKSPACE_SIZE / rect.width;
    const scaleY = WORKSPACE_SIZE / rect.height;
    const canvasX = (e.clientX - rect.left) * scaleX;
    const canvasY = (e.clientY - rect.top) * scaleY;

    const origin = calculateOrigin(targetW, targetH, zoom, pan);
    const originX = origin.x;
    const originY = origin.y;

    const localX = Math.floor((canvasX - originX) / zoom);
    const localY = Math.floor((canvasY - originY) / zoom);

    if (localX >= 0 && localX < targetW && localY >= 0 && localY < targetH) {
      const pixelIdx = (localY * targetW + localX) * 4;
      const r = targetImageData.data[pixelIdx];
      const g = targetImageData.data[pixelIdx + 1];
      const b = targetImageData.data[pixelIdx + 2];
      const gv = computeGrayValue(r, g, b);

      setInspector({
        grabX: grabRoiX !== null ? grabRoiX + localX : null,
        grabY: grabRoiY !== null ? grabRoiY + localY : null,
        localX,
        localY,
        r,
        g,
        b,
        gv,
        isPadding: false,
      });
    } else {
      setInspector({
        grabX: null,
        grabY: null,
        localX: null,
        localY: null,
        r: 0,
        g: 0,
        b: 0,
        gv: 0,
        isPadding: true,
      });
    }
  };

  const handlePointerUp = (e: React.PointerEvent) => {
    if (isPanning) {
      try {
        (e.target as HTMLElement).releasePointerCapture(e.pointerId);
      } catch {
        // ignore
      }
      setIsPanning(false);
    }
  };

  const handlePointerLeave = () => {
    setIsPanning(false);
    setInspector(null);
  };

  // Check if active inspection matches loaded static image
  const isInspectionSynced = isInspectionImageCurrent(currentInspection, staticImg);

  return (
    <div className="panel-card precision-inspector-card">
      {/* Header with Source & Mode Toggles */}
      <div className="panel-header">
        <div className="panel-title-area">
          <ImageIcon size={16} className="text-cyan" />
          <h2 className="panel-title">정밀 검사 뷰어 (600×600 Precision View)</h2>

          {/* Dynamic Title Badges */}
          {activeSource === 'REGISTERED' && currentInspection ? (
            <span className="phase-badge active font-mono flex items-center gap-1.5">
              <Tag size={12} className="text-cyan" />
              <span>
                {currentInspection.metrics?.input_source === 'LIVEVIEW_GRAB' ? 'LIVEVIEW GRAB CROP' : 'REGISTERED IMAGE'} — {currentInspection.image_id} (검사: {currentInspection.inspection_id})
              </span>
            </span>
          ) : activeSource === 'CAPTURE' && cropData ? (
            <span className="phase-badge active font-mono">
              Product Focus ({cropData.width}×{cropData.height}px)
            </span>
          ) : activeSource === 'CAPTURE' && capture ? (
            <span className="phase-badge font-mono">Overview (1920×480)</span>
          ) : null}
        </div>

        {/* Source Mode Toggles (LiveView Grab vs Registered Static Image) */}
        <div className="flex items-center gap-2">
          <div className="source-mode-selector">
            <button
              type="button"
              className={`source-tab-btn ${activeSource === 'REGISTERED' ? 'active' : ''}`}
              onClick={() => setActiveSource('REGISTERED')}
              disabled={!currentInspection}
              title={
                currentInspection
                  ? `정적 검사 이미지 (${currentInspection.image_id}) 표시`
                  : '검사를 먼저 선택하거나 실행하세요.'
              }
            >
              <Tag size={13} />
              <span>{currentInspection?.metrics?.input_source === 'LIVEVIEW_GRAB' ? 'Grab 검사 이미지' : '정적 검사 이미지'}</span>
              {currentInspection && (
                <span className="text-[10px] bg-cyan-500/20 text-cyan px-1.5 py-0.2 rounded font-mono">
                  {currentInspection.inspection_id}
                </span>
              )}
            </button>

            <button
              type="button"
              className={`source-tab-btn ${activeSource === 'CAPTURE' ? 'active' : ''}`}
              onClick={() => setActiveSource('CAPTURE')}
              disabled={!capture && !cropData}
              title={
                cropData
                  ? 'LiveView Grab ROI Crop 이미지 표시'
                  : capture
                  ? 'LiveView Grab 전체 프레임 표시'
                  : 'LiveView에서 Grab 또는 ROI 선택을 수행하세요.'
              }
            >
              <Crosshair size={13} />
              <span>LiveView Grab</span>
              {cropData && (
                <span className="text-[10px] bg-emerald-500/20 text-emerald px-1.5 py-0.2 rounded font-mono">
                  Crop
                </span>
              )}
            </button>
          </div>

          {/* Sub-view mode toggles for CAPTURE only */}
          {activeSource === 'CAPTURE' && cropData && (
            <div className="view-mode-tabs">
              <button
                type="button"
                className={`tab-btn ${captureViewMode === 'focus' ? 'active' : ''}`}
                onClick={() => setUserCaptureViewMode('focus')}
              >
                <Crosshair size={12} />
                <span>Product Focus</span>
              </button>
              <button
                type="button"
                className={`tab-btn ${captureViewMode === 'overview' ? 'active' : ''}`}
                onClick={() => setUserCaptureViewMode('overview')}
              >
                <Layers size={12} />
                <span>Overview</span>
              </button>
            </div>
          )}
        </div>
      </div>

      <div className="panel-body">
        {/* Error States */}
        {error && (
          <div className="alert-banner alert-error">
            <AlertTriangle size={16} />
            <span>{error}</span>
          </div>
        )}

        {activeSource === 'REGISTERED' && staticError && (
          <div className="alert-banner alert-error">
            <AlertTriangle size={16} />
            <span>{staticError}</span>
          </div>
        )}

        {/* Loading Spinner */}
        {(isLoading || (activeSource === 'REGISTERED' && staticLoading)) && (
          <div className="image-empty-placeholder">
            <div className="spinner text-cyan" style={{ width: 28, height: 28 }} />
            <div className="text-sm font-medium text-slate-300 mt-2">
              {activeSource === 'REGISTERED'
                ? `서버에서 정적 검사 이미지(${currentInspection?.image_id}) 1:1 디코딩 중...`
                : 'FastAPI 서버에서 정확한 프레임을 캡처 및 디코딩 중...'}
            </div>
            <div className="text-xs text-slate-500 font-mono">
              {activeSource === 'REGISTERED'
                ? 'Safe ImageRegistry reading PNG / 0 ML inference'
                : 'OpenCV decoders running / saving to CaptureStore'}
            </div>
          </div>
        )}

        {/* Empty State for CAPTURE */}
        {!isLoading && !staticLoading && activeSource === 'CAPTURE' && !capture && (
          <div className="image-empty-placeholder">
            <ImageIcon className="placeholder-icon" />
            <div className="text-sm font-medium text-slate-300">
              아직 캡처된 프레임이 없습니다.
            </div>
            <div className="text-xs text-slate-500 max-w-sm">
              상단 라이브 뷰어에서 원하는 시점으로 이동한 후{' '}
              <strong className="text-cyan">[Grab]</strong> 또는{' '}
              <strong className="text-cyan">[ROI 선택]</strong>을 누르면 서버가 생성한
              무손실 PNG가 이곳에 로드됩니다.
            </div>
          </div>
        )}

        {/* Empty State for REGISTERED */}
        {!isLoading && !staticLoading && activeSource === 'REGISTERED' && !currentInspection && (
          <div className="image-empty-placeholder">
            <Tag className="placeholder-icon text-cyan" />
            <div className="text-sm font-medium text-slate-300">
              선택된 정적 검사 기록이 없습니다.
            </div>
            <div className="text-xs text-slate-500 max-w-sm">
              우측 검사 패널에서 기존 검사 ID를 조회하거나 새 검사를 실행하면,
              해당 검사에 사용된 실제 원본 이미지와 서버의 최종 판정 오버레이가 표시됩니다.
            </div>
          </div>
        )}

        {/* 1. PRECISION WORKSPACE (600x600 Canvas for both Focus Crop and Registered Static Image) */}
        {!isLoading &&
          !staticLoading &&
          ((activeSource === 'REGISTERED' && !!staticImg) ||
            (activeSource === 'CAPTURE' && capture && captureViewMode === 'focus')) && (
            <div className="precision-workspace-container">
              {/* Toolbar for Zoom & Pan Controls */}
              <div className="workspace-toolbar">
                <div className="toolbar-group">
                  <span className="toolbar-label">Zoom</span>
                  <button
                    type="button"
                    className="btn-tool"
                    onClick={() => handleZoomStep(0.8)}
                    disabled={zoom <= MIN_ZOOM}
                    title="축소 (Zoom Out, 최소 100%)"
                  >
                    <ZoomOut size={14} />
                  </button>
                  <div className="zoom-presets">
                    {ZOOM_PRESETS.map((level) => (
                      <button
                        key={level}
                        type="button"
                        className={`preset-btn ${zoom === level ? 'active' : ''}`}
                        onClick={() => handleZoomChange(level)}
                      >
                        {level * 100}%
                      </button>
                    ))}
                  </div>
                  <button
                    type="button"
                    className="btn-tool"
                    onClick={() => handleZoomStep(1.25)}
                    disabled={zoom >= MAX_ZOOM}
                    title="확대 (Zoom In, 최대 4000%)"
                  >
                    <ZoomIn size={14} />
                  </button>
                </div>

                <div className="toolbar-group">
                  <button
                    type="button"
                    className="btn-tool"
                    onClick={handleResetZoomPan}
                    title="100% 원본 배율 및 위치 복원"
                  >
                    <RotateCcw size={13} />
                    <span>100% Reset</span>
                  </button>
                  <button
                    type="button"
                    className="btn-tool"
                    onClick={handleResetPan}
                    title="Pan 위치 초기화"
                  >
                    <span>Pan Reset</span>
                  </button>
                  <button
                    type="button"
                    className={`btn-tool ${showGrid ? 'active-tool' : ''}`}
                    onClick={() => setShowGrid(!showGrid)}
                    title="픽셀 경계 격자 표시 토글 (400% 이상)"
                  >
                    <Grid size={14} />
                    <span>Grid</span>
                  </button>
                </div>

                {/* Day 7 Step 4: Heatmap Controls for REGISTERED inspection images */}
                {activeSource === 'REGISTERED' && isInspectionSynced && (
                  <div className="toolbar-group heatmap-toolbar-group">
                    <button
                      type="button"
                      className={`btn-tool heatmap-toggle-btn ${showHeatmap ? 'active-heatmap' : ''}`}
                      onClick={() => setHeatmapSelection(showHeatmap || !currentInspection ? null : {
                        inspectionId: currentInspection.inspection_id,
                        imageId: currentInspection.image_id,
                      })}
                      disabled={anomalyMapStatus !== 'AVAILABLE' || !overlayImgElement}
                      title={
                        anomalyMapStatus === 'AVAILABLE'
                          ? showHeatmap
                            ? '이상 반응 Heatmap 끄기'
                            : '이상 반응 Heatmap 켜기'
                          : anomalyMapStatus === 'LOADING'
                          ? '이상지도 가용성 확인 중...'
                          : '이 검사 기록에는 저장된 이상지도 데이터가 없습니다.'
                      }
                    >
                      <Flame size={13} className={showHeatmap ? 'text-amber' : ''} />
                      <span>Heatmap {showHeatmap ? 'ON' : 'OFF'}</span>
                    </button>

                    {showHeatmap && overlayImgElement && (
                      <div className="heatmap-opacity-container flex items-center gap-1.5 px-2 py-0.5 bg-slate-900/60 rounded border border-slate-700/60 text-xs">
                        <span className="text-[11px] text-slate-400">투명도</span>
                        <input
                          type="range"
                          min="0.1"
                          max="1.0"
                          step="0.05"
                          value={heatmapOpacity}
                          onChange={(e) => setHeatmapOpacity(parseFloat(e.target.value))}
                          className="w-16 h-1.5 accent-cyan cursor-pointer"
                          title={`Heatmap 투명도: ${Math.round(heatmapOpacity * 100)}%`}
                        />
                        <span className="text-[10px] font-mono text-cyan w-7 text-right">
                          {Math.round(heatmapOpacity * 100)}%
                        </span>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* 600x600 Fixed Viewport with non-passive wheel prevention */}
              <div ref={canvasWrapperRef} className="canvas-scroll-wrapper">
                <div className="canvas-frame-600">
                  <canvas
                    ref={canvasRef}
                    className={`precision-canvas ${isPanning ? 'cursor-grabbing' : 'cursor-crosshair'}`}
                    onPointerDown={handlePointerDown}
                    onPointerMove={handlePointerMove}
                    onPointerUp={handlePointerUp}
                    onPointerCancel={handlePointerUp}
                    onPointerLeave={handlePointerLeave}
                  />

                  {/* Day 7 Step 3: Fixed Floating Verdict Overlay on Registered Static Image */}
                  {activeSource === 'REGISTERED' && isInspectionSynced && currentInspection && (
                    <div
                      className={`verdict-overlay-card verdict-${(currentInspection.final_result || 'not_run').toLowerCase()}`}
                    >
                      {/* Top Header Row with Verdict Badge */}
                      <div className="verdict-header-row">
                        <div className={`verdict-badge-lg ${(currentInspection.final_result || 'not_run').toLowerCase()}`}>
                          {currentInspection.final_result === 'OK' && <CheckCircle2 size={16} />}
                          {currentInspection.final_result === 'NG' && <XCircle size={16} />}
                          {currentInspection.final_result === 'REINSPECT' && <AlertTriangle size={16} />}
                          {currentInspection.final_result === 'ERROR' && <AlertTriangle size={16} />}
                          {!currentInspection.final_result && <Info size={16} />}
                          <span>{currentInspection.final_result || 'NOT RUN'}</span>
                        </div>

                        {/* Provenance Tag */}
                        <div className="text-[11px] font-mono text-slate-300">
                          {isMockFixture ? (
                            <span className="text-amber font-semibold">테스트 Fixture</span>
                          ) : currentInspection.metrics?.input_source === 'LIVEVIEW_GRAB' ? (
                            <span className="text-amber font-semibold">실험적 Grab 검사</span>
                          ) : currentInspection.provenance === 'LIVE_INSPECTION' ? (
                            <span className="text-emerald font-semibold">실시간 검사</span>
                          ) : (
                            <span className="text-cyan font-semibold">저장 검사 조회</span>
                          )}
                        </div>
                      </div>

                      {/* Mock Fixture Notice (Section 7) */}
                      {isMockFixture && (
                        <div className="verdict-mock-banner">
                          <AlertTriangle size={13} />
                          <span>MOCK / TEST FIXTURE — 저장된 테스트 판정이며 실제 결함 위치의 증거가 아닙니다.</span>
                        </div>
                      )}

                      {/* Key Inspection Metrics */}
                      <div className="verdict-meta-grid">
                        <div className="verdict-meta-item">
                          <span className="verdict-meta-label">검사 ID</span>
                          <span className="verdict-meta-value text-cyan">
                            {currentInspection.inspection_id}
                          </span>
                        </div>
                        <div className="verdict-meta-item">
                          <span className="verdict-meta-label">이미지 ID</span>
                          <span className="verdict-meta-value">
                            {currentInspection.image_id}
                          </span>
                        </div>
                        <div className="verdict-meta-item">
                          <span className="verdict-meta-label">Anomaly Score</span>
                          <span
                            className={`verdict-meta-value ${
                              currentInspection.anomaly_score !== null &&
                              currentInspection.decision_threshold !== null &&
                              currentInspection.anomaly_score > currentInspection.decision_threshold
                                ? 'text-coral'
                                : 'text-emerald'
                            }`}
                          >
                            {currentInspection.anomaly_score !== null
                              ? currentInspection.anomaly_score.toFixed(4)
                              : 'N/A'}
                          </span>
                        </div>
                        <div className="verdict-meta-item">
                          <span className="verdict-meta-label">Decision Threshold</span>
                          <span className="verdict-meta-value text-slate-300">
                            {currentInspection.decision_threshold !== null &&
                            currentInspection.decision_threshold !== undefined
                              ? currentInspection.decision_threshold.toFixed(4)
                              : 'N/A'}
                          </span>
                        </div>
                      </div>

                      {/* Defect Location Notice (Day 7 Step 4) */}
                      {anomalyMapStatus === 'AVAILABLE' && overlayImgElement ? (
                        showHeatmap ? (
                          <div className="verdict-location-notice active-map">
                            🔥 PatchCore 모델의 상대적 이상 반응 분포입니다. 실제 결함 위치가 검증된 결과는 아닙니다.
                          </div>
                        ) : (
                          <div className="verdict-location-notice map-available">
                            🗺️ 이상지도(Anomaly Map) 저장됨 — 상단 툴바의 [Heatmap ON]으로 상대적 이상 반응 분포를 확인할 수 있습니다.
                          </div>
                        )
                      ) : anomalyMapStatus === 'LOADING' ? (
                        <div className="verdict-location-notice">
                          ⏳ 이상지도 가용성 확인 중...
                        </div>
                      ) : (
                        <div className="verdict-location-notice">
                          📍 이 검사 기록에는 저장된 이상지도 데이터가 없습니다. (추측 위치 표시 금지)
                        </div>
                      )}

                      {/* Viewport Hint (Section 4) */}
                      {staticImg && (staticImg.width > 600 || staticImg.height > 600) && (
                        <div className="verdict-viewport-hint">
                          <Info size={11} />
                          <span>
                            원본 {staticImg.width}×{staticImg.height}px 중 600×600px 뷰포트 표시 (Pan으로 1:1 탐색)
                          </span>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>

              {/* Real-time Pixel Inspector Bar */}
              <div className="pixel-inspector-bar">
                <div className="inspector-left">
                  <Crosshair size={14} className="text-cyan" />
                  <span className="font-semibold text-slate-300">Pixel Inspector</span>
                  {inspector?.isPadding ? (
                    <span className="inspector-status-badge padding">PADDING (RGB 0,0,0)</span>
                  ) : inspector ? (
                    <span className="inspector-status-badge product">
                      {activeSource === 'REGISTERED' ? 'STATIC IMAGE PIXEL' : 'PRODUCT PIXEL'}
                    </span>
                  ) : (
                    <span className="inspector-status-badge idle">마우스를 이미지 위에 올리세요</span>
                  )}
                </div>

                <div className="inspector-values-row font-mono">
                  {/* Coordinates */}
                  {activeSource === 'CAPTURE' && (
                    <div className="coord-group">
                      <span className="coord-label">Grab Coord:</span>
                      <span className="coord-val text-cyan">
                        {inspector && inspector.grabX !== null && inspector.grabY !== null
                          ? `(${inspector.grabX}, ${inspector.grabY})`
                          : '—'}
                      </span>
                    </div>
                  )}

                  <div className="coord-group">
                    <span className="coord-label">
                      {activeSource === 'REGISTERED' ? 'Image Local:' : 'Crop Local:'}
                    </span>
                    <span className="coord-val">
                      {inspector && inspector.localX !== null && inspector.localY !== null
                        ? `(${inspector.localX}, ${inspector.localY})`
                        : '—'}
                    </span>
                  </div>

                  {/* Color Swatch */}
                  <div className="swatch-group">
                    <div
                      className="pixel-color-swatch"
                      style={{
                        backgroundColor: inspector
                          ? `rgb(${inspector.r}, ${inspector.g}, ${inspector.b})`
                          : '#000000',
                      }}
                    />
                    <span className="rgb-val">
                      {inspector
                        ? `RGB(${inspector.r}, ${inspector.g}, ${inspector.b})`
                        : 'RGB(—, —, —)'}
                    </span>
                  </div>

                  {/* Gray Value */}
                  <div className="gv-group">
                    <span className="gv-label">Gray Value (GV):</span>
                    <span className="gv-val text-emerald font-bold">
                      {inspector ? inspector.gv : '—'}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          )}

        {/* 2. OVERVIEW MODE for CAPTURE (Full 1920x480 frame) */}
        {!isLoading &&
          activeSource === 'CAPTURE' &&
          capture &&
          captureViewMode === 'overview' && (
            <div className="image-viewport">
              {imageBlobUrl ? (
                <img
                  src={imageBlobUrl}
                  alt={`Captured frame ${capture.frame_index}`}
                  className="captured-image"
                />
              ) : null}
            </div>
          )}

        {/* Bottom Provenance Meta Pill Grid */}
        {activeSource === 'CAPTURE' && capture && (
          <div className="metadata-grid">
            <div className="meta-pill">
              <span className="meta-pill-label">Capture ID</span>
              <span className="meta-pill-value font-mono text-cyan truncate" title={capture.capture_id}>
                {capture.capture_id}
              </span>
            </div>
            <div className="meta-pill">
              <span className="meta-pill-label">프레임 번호</span>
              <span className="meta-pill-value font-mono">Index #{capture.frame_index}</span>
            </div>
            <div className="meta-pill">
              <span className="meta-pill-label">원천 해상도</span>
              <span className="meta-pill-value font-mono">
                {capture.width}×{capture.height} PNG
              </span>
            </div>
            <div className="meta-pill">
              <span className="meta-pill-label">ROI 크기</span>
              <span className="meta-pill-value font-mono text-cyan">
                {cropData ? `${cropData.width}×${cropData.height}px (Crop 완료)` : '전체 (미선택)'}
              </span>
            </div>
            <div className="meta-pill">
              <span className="meta-pill-label">검사 소스</span>
              <span className="meta-pill-value font-mono text-amber text-xs">
                {cropData ? 'LIVEVIEW ROI CROP' : 'LIVEVIEW GRAB'}
              </span>
            </div>
          </div>
        )}

        {activeSource === 'REGISTERED' && currentInspection && staticImg && (
          <div className="metadata-grid">
            <div className="meta-pill">
              <span className="meta-pill-label">검사 ID</span>
              <span className="meta-pill-value font-mono text-cyan">
                {currentInspection.inspection_id}
              </span>
            </div>
            <div className="meta-pill">
              <span className="meta-pill-label">등록 이미지</span>
              <span className="meta-pill-value font-mono">{currentInspection.image_id}</span>
            </div>
            <div className="meta-pill">
              <span className="meta-pill-label">원천 해상도</span>
              <span className="meta-pill-value font-mono">
                {staticImg.width}×{staticImg.height} PNG
              </span>
            </div>
            <div className="meta-pill">
              <span className="meta-pill-label">최종 판정</span>
              <span
                className={`meta-pill-value font-mono font-bold ${
                  currentInspection.final_result === 'OK'
                    ? 'text-emerald'
                    : currentInspection.final_result === 'NG'
                    ? 'text-coral'
                    : 'text-amber'
                }`}
              >
                {currentInspection.final_result}
              </span>
            </div>
            <div className="meta-pill">
              <span className="meta-pill-label">검사 소스</span>
              <span className="meta-pill-value font-mono text-cyan text-xs">
                {currentInspection.provenance || 'STORED_RESULT'}
              </span>
            </div>
            {anomalyMapMeta && (
              <div className="meta-pill">
                <span className="meta-pill-label">이상지도 (Map)</span>
                <span className="meta-pill-value font-mono text-amber text-xs">
                  {anomalyMapMeta.anomaly_map_width}×{anomalyMapMeta.anomaly_map_height} (Jet Overlay)
                </span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

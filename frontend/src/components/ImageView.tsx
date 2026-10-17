import React, { useRef, useState, useEffect } from 'react';
import {
  Image as ImageIcon,
  CheckCircle2,
  AlertTriangle,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  Crosshair,
  Grid,
  Layers,
} from 'lucide-react';
import type { CaptureMetadata } from '../types/video';
import type { CropData, PixelInspectionInfo } from '../types/roi';
import { computeGrayValue } from '../utils/coordinateTransforms';

interface ImageViewProps {
  capture: CaptureMetadata | null;
  imageBlobUrl: string | null;
  cropData: CropData | null;
  isLoading: boolean;
  error: string | null;
}

const MIN_ZOOM = 1.0; // Minimum 100% (1x)
const MAX_ZOOM = 40.0; // Maximum 4000% (40x)
const ZOOM_PRESETS = [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 40.0];

const clampZoom = (val: number): number => {
  return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, Math.round(val * 100) / 100));
};

export const ImageView: React.FC<ImageViewProps> = ({
  capture,
  imageBlobUrl,
  cropData,
  isLoading,
  error,
}) => {
  // View mode: 'focus' (600x600 precision crop) or 'overview' (full 1920x480 frame)
  const [userViewMode, setUserViewMode] = useState<'focus' | 'overview'>('focus');
  const viewMode = cropData ? userViewMode : 'overview';

  // Zoom & Pan state for 600x600 workspace (default 100% / zoom = 1.0)
  const [zoom, setZoom] = useState<number>(1.0);
  const [pan, setPan] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [showGrid, setShowGrid] = useState<boolean>(true);
  const [isPanning, setIsPanning] = useState<boolean>(false);
  const panStartRef = useRef<{ x: number; y: number; initialPan: { x: number; y: number } }>({
    x: 0,
    y: 0,
    initialPan: { x: 0, y: 0 },
  });

  // Pixel Inspector state
  const [inspector, setInspector] = useState<PixelInspectionInfo | null>(null);

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const canvasWrapperRef = useRef<HTMLDivElement | null>(null);
  const [cropImgElement, setCropImgElement] = useState<HTMLImageElement | null>(null);

  // Load crop Image element when cropData changes and reset to 100% center
  useEffect(() => {
    if (!cropData) return;
    let isCurrent = true;
    const img = new Image();
    img.src = cropData.cropBlobUrl;
    img.onload = () => {
      if (isCurrent) {
        setCropImgElement(img);
        setUserViewMode('focus');
        setZoom(1.0);
        setPan({ x: 0, y: 0 });
      }
    };
    return () => {
      isCurrent = false;
    };
  }, [cropData]);

  // Requirement 4: Prevent browser page scroll when wheeling inside the 600x600 workspace
  // Uses non-passive native wheel listener with e.preventDefault()
  useEffect(() => {
    const el = canvasWrapperRef.current;
    if (!el) return;

    const handleNativeWheel = (e: WheelEvent) => {
      e.preventDefault();
      if (viewMode !== 'focus' || !cropData) return;

      const delta = e.deltaY < 0 ? 1.25 : 0.8;
      setZoom((prevZoom) => clampZoom(prevZoom * delta));
    };

    el.addEventListener('wheel', handleNativeWheel, { passive: false });
    return () => {
      el.removeEventListener('wheel', handleNativeWheel);
    };
  }, [viewMode, cropData]);

  // Render 600x600 precision inspection canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const WORKSPACE_SIZE = 600;
    canvas.width = WORKSPACE_SIZE;
    canvas.height = WORKSPACE_SIZE;

    // 1. Fill entire 600x600 workspace with strict RGB(0, 0, 0)
    ctx.fillStyle = '#000000';
    ctx.fillRect(0, 0, WORKSPACE_SIZE, WORKSPACE_SIZE);

    if (!cropData || !cropImgElement) {
      return;
    }

    const cropW = cropData.width;
    const cropH = cropData.height;

    // Nearest-neighbor rendering for crisp machine vision inspection
    ctx.imageSmoothingEnabled = false;

    // Calculate unscaled center offset at 100% (zoom = 1) plus pan
    const originX = (WORKSPACE_SIZE - cropW * zoom) / 2 + pan.x;
    const originY = (WORKSPACE_SIZE - cropH * zoom) / 2 + pan.y;

    // Draw Crop Image
    ctx.drawImage(cropImgElement, originX, originY, cropW * zoom, cropH * zoom);

    // Subtle crop boundary outline
    ctx.strokeStyle = '#38bdf8';
    ctx.lineWidth = 1;
    ctx.strokeRect(originX, originY, cropW * zoom, cropH * zoom);

    // Visible pixel range calculation for viewport culling
    const startX = Math.max(0, Math.floor(-originX / zoom));
    const endX = Math.min(cropW - 1, Math.ceil((WORKSPACE_SIZE - originX) / zoom));
    const startY = Math.max(0, Math.floor(-originY / zoom));
    const endY = Math.min(cropH - 1, Math.ceil((WORKSPACE_SIZE - originY) / zoom));

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
          ctx.lineTo(lineX, Math.min(WORKSPACE_SIZE, originY + cropH * zoom));
          ctx.stroke();
        }
      }

      // Horizontal lines for visible rows
      for (let y = startY; y <= endY + 1; y++) {
        const lineY = originY + y * zoom;
        if (lineY >= 0 && lineY <= WORKSPACE_SIZE) {
          ctx.beginPath();
          ctx.moveTo(Math.max(0, originX), lineY);
          ctx.lineTo(Math.min(WORKSPACE_SIZE, originX + cropW * zoom), lineY);
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
          const pixelIdx = (y * cropW + x) * 4;
          const r = cropData.imageData.data[pixelIdx];
          const g = cropData.imageData.data[pixelIdx + 1];
          const b = cropData.imageData.data[pixelIdx + 2];
          const gv = computeGrayValue(r, g, b);

          const cx = originX + x * zoom + zoom / 2;
          const cy = originY + y * zoom + zoom / 2;

          // Contrast coloring: dark text on bright pixel, white text on dark pixel
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

      // At 1600% (zoom < 32), display floating GV tag above the hovered cell
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
  }, [cropData, cropImgElement, zoom, pan, showGrid, inspector]);

  // Zoom handlers with strict [1.0, 40.0] bounds
  const handleZoomChange = (newZoom: number) => {
    setZoom(clampZoom(newZoom));
  };

  const handleZoomStep = (factor: number) => {
    setZoom((prev) => clampZoom(prev * factor));
  };

  const handleResetZoomPan = () => {
    setZoom(1.0);
    setPan({ x: 0, y: 0 });
  };

  const handleResetPan = () => {
    setPan({ x: 0, y: 0 });
  };

  // Mouse Down for Pan
  const handlePointerDown = (e: React.PointerEvent) => {
    if (viewMode !== 'focus') return;
    setIsPanning(true);
    panStartRef.current = {
      x: e.clientX,
      y: e.clientY,
      initialPan: { ...pan },
    };
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  };

  // Mouse Move for Pan & Pixel Inspector
  const handlePointerMove = (e: React.PointerEvent) => {
    if (viewMode !== 'focus' || !canvasRef.current) return;

    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();

    // Pan motion
    if (isPanning) {
      const deltaX = e.clientX - panStartRef.current.x;
      const deltaY = e.clientY - panStartRef.current.y;
      setPan({
        x: panStartRef.current.initialPan.x + deltaX,
        y: panStartRef.current.initialPan.y + deltaY,
      });
      return;
    }

    // Pixel Inspector calculation
    if (!cropData) return;

    // Canvas coordinates (0 to 600)
    const scaleX = 600 / rect.width;
    const scaleY = 600 / rect.height;
    const canvasX = (e.clientX - rect.left) * scaleX;
    const canvasY = (e.clientY - rect.top) * scaleY;

    const cropW = cropData.width;
    const cropH = cropData.height;
    const originX = (600 - cropW * zoom) / 2 + pan.x;
    const originY = (600 - cropH * zoom) / 2 + pan.y;

    const localX = Math.floor((canvasX - originX) / zoom);
    const localY = Math.floor((canvasY - originY) / zoom);

    if (localX >= 0 && localX < cropW && localY >= 0 && localY < cropH) {
      // Inside product crop: read unscaled raw ImageData
      const pixelIdx = (localY * cropW + localX) * 4;
      const r = cropData.imageData.data[pixelIdx];
      const g = cropData.imageData.data[pixelIdx + 1];
      const b = cropData.imageData.data[pixelIdx + 2];
      const gv = computeGrayValue(r, g, b);

      setInspector({
        grabX: cropData.roi.x + localX,
        grabY: cropData.roi.y + localY,
        localX,
        localY,
        r,
        g,
        b,
        gv,
        isPadding: false,
      });
    } else {
      // Outside crop: black padding
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

  return (
    <div className="panel-card precision-inspector-card">
      {/* Header with Mode Toggles */}
      <div className="panel-header">
        <div className="panel-title-area">
          <ImageIcon size={16} className="text-cyan" />
          <h2 className="panel-title">정밀 검사 뷰어 (600×600 Precision View)</h2>
          {cropData ? (
            <span className="phase-badge active font-mono">
              Product Focus ({cropData.width}×{cropData.height}px)
            </span>
          ) : capture ? (
            <span className="phase-badge font-mono">Overview (1920×480)</span>
          ) : null}
        </div>

        {/* View Mode Switching Tabs */}
        <div className="flex items-center gap-2">
          {cropData && (
            <div className="view-mode-tabs">
              <button
                type="button"
                className={`tab-btn ${viewMode === 'focus' ? 'active' : ''}`}
                onClick={() => setUserViewMode('focus')}
              >
                <Crosshair size={13} />
                <span>Product Focus (600×600)</span>
              </button>
              <button
                type="button"
                className={`tab-btn ${viewMode === 'overview' ? 'active' : ''}`}
                onClick={() => setUserViewMode('overview')}
              >
                <Layers size={13} />
                <span>Overview (전체)</span>
              </button>
            </div>
          )}

          {capture && (
            <span className="text-xs bg-emerald-500/10 text-emerald border border-emerald-500/30 px-2.5 py-0.5 rounded-full font-mono flex items-center gap-1.5">
              <CheckCircle2 size={12} />
              <span>SERVER PNG READY</span>
            </span>
          )}
        </div>
      </div>

      <div className="panel-body">
        {/* Error State */}
        {error && (
          <div className="alert-banner alert-error">
            <AlertTriangle size={16} />
            <span>{error}</span>
          </div>
        )}

        {/* Loading Spinner */}
        {isLoading && (
          <div className="image-empty-placeholder">
            <div className="spinner text-cyan" style={{ width: 28, height: 28 }} />
            <div className="text-sm font-medium text-slate-300 mt-2">
              FastAPI 서버에서 정확한 프레임을 캡처 및 디코딩 중...
            </div>
            <div className="text-xs text-slate-500 font-mono">
              OpenCV decoders running / saving to CaptureStore
            </div>
          </div>
        )}

        {/* Empty State */}
        {!isLoading && !capture && (
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

        {/* 1. PRODUCT FOCUS MODE (600x600 Canvas) */}
        {!isLoading && capture && viewMode === 'focus' && (
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
            </div>

            {/* 600x600 Fixed Viewport with non-passive wheel prevention */}
            <div
              ref={canvasWrapperRef}
              className="canvas-scroll-wrapper"
            >
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
                  <span className="inspector-status-badge product">PRODUCT PIXEL</span>
                ) : (
                  <span className="inspector-status-badge idle">마우스를 이미지 위에 올리세요</span>
                )}
              </div>

              <div className="inspector-values-row font-mono">
                {/* Coordinates */}
                <div className="coord-group">
                  <span className="coord-label">Grab Coord:</span>
                  <span className="coord-val text-cyan">
                    {inspector && inspector.grabX !== null && inspector.grabY !== null
                      ? `(${inspector.grabX}, ${inspector.grabY})`
                      : '—'}
                  </span>
                </div>

                <div className="coord-group">
                  <span className="coord-label">Crop Local:</span>
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

        {/* 2. OVERVIEW MODE (Full 1920x480 frame) */}
        {!isLoading && capture && viewMode === 'overview' && (
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

        {/* Capture & Crop Provenance Grid */}
        {capture && (
          <div className="metadata-grid">
            <div className="meta-pill">
              <span className="meta-pill-label">Capture ID</span>
              <span className="meta-pill-value font-mono text-cyan truncate" title={capture.capture_id}>
                {capture.capture_id}
              </span>
            </div>
            <div className="meta-pill">
              <span className="meta-pill-label">프레임 번호</span>
              <span className="meta-pill-value font-mono">
                Index #{capture.frame_index}
              </span>
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
                {cropData
                  ? `${cropData.width}×${cropData.height}px (Crop 완료)`
                  : '전체 (미선택)'}
              </span>
            </div>
            <div className="meta-pill">
              <span className="meta-pill-label">검사 상태</span>
              <span className="meta-pill-value font-mono text-amber text-xs">
                {cropData ? 'MANUAL CROP READY' : 'GRAB READY'}
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

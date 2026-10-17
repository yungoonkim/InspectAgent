import React, { useRef, useState, useEffect, useCallback } from 'react';
import type { RoiRect, RoiState } from '../types/roi';
import {
  calculateViewportMapping,
  screenToImageCoords,
  imageToScreenRect,
  clampRoiRect,
  formatRoiCenter,
} from '../utils/coordinateTransforms';

interface RoiOverlayProps {
  roi: RoiRect;
  roiState: RoiState;
  onChangeRoi: (roi: RoiRect) => void;
  frozenImageUrl: string | null;
  imageWidth?: number;
  imageHeight?: number;
}

type DragMode =
  | 'none'
  | 'moving'
  | 'drawing'
  | 'nw'
  | 'ne'
  | 'se'
  | 'sw'
  | 'n'
  | 's'
  | 'e'
  | 'w';

export const RoiOverlay: React.FC<RoiOverlayProps> = ({
  roi,
  roiState,
  onChangeRoi,
  frozenImageUrl,
  imageWidth = 1920,
  imageHeight = 480,
}) => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [containerSize, setContainerSize] = useState<{ width: number; height: number }>({
    width: 0,
    height: 0,
  });

  const [dragMode, setDragMode] = useState<DragMode>('none');
  const dragStartRef = useRef<{
    pointerX: number;
    pointerY: number;
    initialRoi: RoiRect;
  }>({
    pointerX: 0,
    pointerY: 0,
    initialRoi: roi,
  });

  // Track container dimensions using ResizeObserver
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const updateSize = () => {
      const rect = el.getBoundingClientRect();
      setContainerSize({ width: rect.width, height: rect.height });
    };

    updateSize();

    const observer = new ResizeObserver(() => {
      updateSize();
    });
    observer.observe(el);

    return () => observer.disconnect();
  }, []);

  const mapping = calculateViewportMapping(
    containerSize.width,
    containerSize.height,
    imageWidth,
    imageHeight
  );

  const screenRect = imageToScreenRect(roi, mapping);

  // Pointer Down on Handle or Box
  const handlePointerDown = (e: React.PointerEvent, mode: DragMode) => {
    e.stopPropagation();
    e.preventDefault();

    if (!containerRef.current) return;
    const containerRect = containerRef.current.getBoundingClientRect();
    const relX = e.clientX - containerRect.left;
    const relY = e.clientY - containerRect.top;

    setDragMode(mode);
    dragStartRef.current = {
      pointerX: relX,
      pointerY: relY,
      initialRoi: { ...roi },
    };

    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  };

  // Background pointer down: start drawing new rectangle (only in EDITING mode)
  const handleBackgroundPointerDown = (e: React.PointerEvent) => {
    e.preventDefault();
    if (roiState !== 'EDITING' || !containerRef.current) return;

    const containerRect = containerRef.current.getBoundingClientRect();
    const relX = e.clientX - containerRect.left;
    const relY = e.clientY - containerRect.top;

    const imgCoord = screenToImageCoords(relX, relY, mapping, imageWidth, imageHeight);

    const initialRect: RoiRect = {
      x: imgCoord.x,
      y: imgCoord.y,
      width: 1,
      height: 1,
    };

    setDragMode('drawing');
    dragStartRef.current = {
      pointerX: relX,
      pointerY: relY,
      initialRoi: initialRect,
    };

    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  };

  // Pointer Move
  const handlePointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (dragMode === 'none' || !containerRef.current) return;

      const containerRect = containerRef.current.getBoundingClientRect();
      const currentRelX = e.clientX - containerRect.left;
      const currentRelY = e.clientY - containerRect.top;

      const startCoord = screenToImageCoords(
        dragStartRef.current.pointerX,
        dragStartRef.current.pointerY,
        mapping,
        imageWidth,
        imageHeight
      );

      const currentCoord = screenToImageCoords(
        currentRelX,
        currentRelY,
        mapping,
        imageWidth,
        imageHeight
      );

      const deltaX = currentCoord.x - startCoord.x;
      const deltaY = currentCoord.y - startCoord.y;

      const init = dragStartRef.current.initialRoi;
      let nextRoi: RoiRect = { ...init };

      if (dragMode === 'moving') {
        nextRoi = {
          x: init.x + deltaX,
          y: init.y + deltaY,
          width: init.width,
          height: init.height,
        };
      } else if (dragMode === 'drawing') {
        const x1 = Math.min(startCoord.x, currentCoord.x);
        const y1 = Math.min(startCoord.y, currentCoord.y);
        const x2 = Math.max(startCoord.x, currentCoord.x);
        const y2 = Math.max(startCoord.y, currentCoord.y);

        nextRoi = {
          x: x1,
          y: y1,
          width: Math.max(30, x2 - x1),
          height: Math.max(30, y2 - y1),
        };
      } else {
        // Resizing via 8 handles
        let newX = init.x;
        let newY = init.y;
        let newW = init.width;
        let newH = init.height;

        if (dragMode.includes('w')) {
          newX = init.x + deltaX;
          newW = init.width - deltaX;
        }
        if (dragMode.includes('e')) {
          newW = init.width + deltaX;
        }
        if (dragMode.includes('n')) {
          newY = init.y + deltaY;
          newH = init.height - deltaY;
        }
        if (dragMode.includes('s')) {
          newH = init.height + deltaY;
        }

        // Handle negative inversion
        if (newW < 30) {
          newW = 30;
          if (dragMode.includes('w')) newX = init.x + init.width - 30;
        }
        if (newH < 30) {
          newH = 30;
          if (dragMode.includes('n')) newY = init.y + init.height - 30;
        }

        nextRoi = {
          x: newX,
          y: newY,
          width: newW,
          height: newH,
        };
      }

      onChangeRoi(clampRoiRect(nextRoi, imageWidth, imageHeight));
    },
    [dragMode, mapping, imageWidth, imageHeight, onChangeRoi]
  );

  const handlePointerUp = (e: React.PointerEvent) => {
    if (dragMode !== 'none') {
      try {
        (e.target as HTMLElement).releasePointerCapture(e.pointerId);
      } catch {
        // ignore
      }
      setDragMode('none');
    }
  };

  return (
    <div
      ref={containerRef}
      className="roi-overlay-container"
      onPointerDown={handleBackgroundPointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerUp}
    >
      {/* 1. Underlying frozen server PNG for 100% pixel-perfect alignment */}
      {frozenImageUrl && (
        <img
          src={frozenImageUrl}
          alt="Frozen inspection frame"
          className="frozen-frame-layer"
          draggable={false}
        />
      )}

      {/* 2. Interactive ROI Box */}
      {containerSize.width > 0 && (
        <div
          className={`roi-bounding-box ${roiState === 'APPLIED' ? 'applied' : 'editing'}`}
          style={{
            left: `${screenRect.left}px`,
            top: `${screenRect.top}px`,
            width: `${screenRect.width}px`,
            height: `${screenRect.height}px`,
          }}
          onPointerDown={roiState === 'EDITING' ? (e) => handlePointerDown(e, 'moving') : undefined}
        >
          {/* Top Label Badge */}
          <div className={`roi-label-badge font-mono ${roiState === 'APPLIED' ? 'applied' : 'editing'}`}>
            <span className="roi-state-tag">
              {roiState === 'APPLIED' ? 'ROI APPLIED' : 'ROI EDITING'}
            </span>
            <span className="roi-label-center">{formatRoiCenter(roi)}</span>
          </div>

          {/* Crosshair guide lines */}
          <div className="roi-crosshair roi-crosshair-h" />
          <div className="roi-crosshair roi-crosshair-v" />

          {/* 8 Resize Handles (Only interactive during EDITING mode) */}
          {roiState === 'EDITING' && (
            <>
              <div
                className="roi-handle roi-handle-nw"
                onPointerDown={(e) => handlePointerDown(e, 'nw')}
              />
              <div
                className="roi-handle roi-handle-ne"
                onPointerDown={(e) => handlePointerDown(e, 'ne')}
              />
              <div
                className="roi-handle roi-handle-se"
                onPointerDown={(e) => handlePointerDown(e, 'se')}
              />
              <div
                className="roi-handle roi-handle-sw"
                onPointerDown={(e) => handlePointerDown(e, 'sw')}
              />
              <div
                className="roi-handle roi-handle-n"
                onPointerDown={(e) => handlePointerDown(e, 'n')}
              />
              <div
                className="roi-handle roi-handle-s"
                onPointerDown={(e) => handlePointerDown(e, 's')}
              />
              <div
                className="roi-handle roi-handle-w"
                onPointerDown={(e) => handlePointerDown(e, 'w')}
              />
              <div
                className="roi-handle roi-handle-e"
                onPointerDown={(e) => handlePointerDown(e, 'e')}
              />
            </>
          )}
        </div>
      )}
    </div>
  );
};

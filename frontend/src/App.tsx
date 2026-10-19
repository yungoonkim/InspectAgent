import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Header } from './components/Header';
import { WorkflowStepper } from './components/WorkflowStepper';
import { LiveView } from './components/LiveView';
import { ImageView } from './components/ImageView';
import { InspectionPanel } from './components/InspectionPanel';
import { GrabInspectionPanel } from './components/GrabInspectionPanel';
import { InspectionTabs } from './components/InspectionTabs';
import { AgentPanel } from './components/AgentPanel';
import { VisionReviewPanel } from './components/VisionReviewPanel';
import {
  checkHealth,
  getVideos,
  getVideoStreamUrl,
  ensureCaptureSession,
  grabFrame,
  fetchCaptureImageBlob,
} from './api/video';
import type { VideoMetadata, CaptureMetadata } from './types/video';
import type { RoiRect, CropData, RoiState } from './types/roi';
import type { InspectionResponse } from './types/inspection';
import type { ReinspectionGroup } from './types/reinspection';
import { loadImageFromUrl, cropExactPixels } from './utils/imageCropper';
import { computeRoiCenter } from './utils/coordinateTransforms';
import { roiFits, sameSource, sourceKey } from './utils/roiLifetime';

const DEFAULT_ROI: RoiRect = {
  x: 800,
  y: 80,
  width: 320,
  height: 320,
};

export const App: React.FC = () => {
  const [mode, setMode] = useState<'MANUAL' | 'AUTO'>('MANUAL');
  const [apiConnected, setApiConnected] = useState<boolean>(false);
  const [video, setVideo] = useState<VideoMetadata | null>(null);
  const [videos, setVideos] = useState<VideoMetadata[]>([]);
  const [streamUrl, setStreamUrl] = useState<string>('');
  const [isGrabbing, setIsGrabbing] = useState<boolean>(false);
  const [capture, setCapture] = useState<CaptureMetadata | null>(null);
  const [imageBlobUrl, setImageBlobUrl] = useState<string | null>(null);
  const [grabError, setGrabError] = useState<string | null>(null);
  const [generalError, setGeneralError] = useState<string | null>(null);

  // Phase F-3.1: ROI State Machine (NO_ROI -> EDITING -> APPLIED)
  const [roi, setRoi] = useState<RoiRect>(DEFAULT_ROI);
  const [roiState, setRoiState] = useState<RoiState>('NO_ROI');
  const [cropData, setCropData] = useState<CropData | null>(null);
  const [cropMessage, setCropMessage] = useState<string | null>(null);

  // Phase F-2: Static Image Inspection & Agent state
  const [currentInspection, setCurrentInspection] = useState<InspectionResponse | null>(null);
  const [reinspectionGroup, setReinspectionGroup] = useState<ReinspectionGroup | null>(null);
  const selectionVersionRef = useRef(0);
  const getSelectionVersion = useCallback(() => selectionVersionRef.current, []);
  const startSelection = useCallback(() => {
    selectionVersionRef.current += 1;
    setCurrentInspection(null);
    return selectionVersionRef.current;
  }, []);
  const handleInspectionChange = useCallback((inspection: InspectionResponse | null, version?: number) => {
    if (version !== undefined && version !== selectionVersionRef.current) return;
    setCurrentInspection(inspection);
  }, []);

  // Keep ref to revoke previous Blob URLs to prevent memory leaks
  const prevBlobUrlRef = useRef<string | null>(null);
  const prevCropBlobUrlRef = useRef<string | null>(null);
  const videoKeyRef = useRef('');
  const grabEpochRef = useRef(0);
  const grabBusyRef = useRef(false);
  const acquiredFramesRef = useRef(new Set<string>());

  const applyVideo = useCallback((nextVideo: VideoMetadata) => {
    if (grabBusyRef.current) return;
    const nextKey = sourceKey(nextVideo);
    if (videoKeyRef.current !== nextKey) {
      videoKeyRef.current = nextKey;
      grabEpochRef.current++;
      acquiredFramesRef.current.clear();
      setRoiState('NO_ROI');
      setRoi(DEFAULT_ROI);
      setCapture(null);
      setCropData(null);
      setImageBlobUrl(null);
      setCurrentInspection(null);
      setGrabError(null);
      setCropMessage(null);
      selectionVersionRef.current++;
    }
    setVideo(nextVideo);
    setStreamUrl(getVideoStreamUrl(nextVideo.video_id));
    setGeneralError(null);
  }, []);

  // Check API, bootstrap session, and load initial video metadata
  const loadInitialData = useCallback(async () => {
    try {
      const isHealthy = await checkHealth();
      setApiConnected(isHealthy);

      // Pre-bootstrap capture session so session cookie and CSRF token are ready
      try {
        await ensureCaptureSession();
      } catch (sessionErr) {
        console.warn('Initial session bootstrap warning (will retry on grab):', sessionErr);
      }

      const videoList = await getVideos();
      setVideos(videoList.videos ?? []);
      if (videoList.videos && videoList.videos.length > 0) {
        applyVideo(videoList.videos[0]);
      } else {
        setGeneralError('등록된 비디오 소스가 없습니다. (data/outputs/videos 확인 필요)');
      }
    } catch (err: any) {
      setApiConnected(false);
      setGeneralError('FastAPI 서버에 연결할 수 없습니다. (백엔드 서버 및 프록시 상태 확인)');
      console.warn('API Connection error:', err);
    }
  }, [applyVideo]);

  useEffect(() => {
    let isMounted = true;

    void (async () => {
      if (!isMounted) return;
      await loadInitialData();
    })();

    // Periodic connectivity probe every 5 seconds
    const interval = setInterval(async () => {
      const isHealthy = await checkHealth();
      if (isMounted) {
        setApiConnected(isHealthy);
      }
    }, 5000);

    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [loadInitialData]);

  // Cleanup Blob URLs on unmount
  useEffect(() => {
    return () => {
      if (prevBlobUrlRef.current) {
        URL.revokeObjectURL(prevBlobUrlRef.current);
      }
      if (prevCropBlobUrlRef.current) {
        URL.revokeObjectURL(prevCropBlobUrlRef.current);
      }
    };
  }, []);

  // Handle Grab Trigger from LiveView
  const handleGrab = async (frameIndex: number): Promise<void> => {
    if (grabBusyRef.current) return;
    if (!video) {
      setGrabError('비디오 메타데이터가 로드되지 않았습니다.');
      return;
    }

    if (mode === 'AUTO') {
      setGrabError('AUTO 모드는 현재 준비 중입니다. MANUAL 모드로 전환하여 프레임을 캡처하세요.');
      return;
    }

    // CASE B: ROI is EDITING -> perform client-side Crop using existing frozen Capture PNG (DO NOT call server Grab API!)
    if (roiState === 'EDITING' && sameSource(capture, video) && capture?.frame_index === frameIndex) {
      startSelection();
      // Validate ROI bounds & existing capture
      if (!capture || !imageBlobUrl) {
        setGrabError('기준 캡처 프레임이 유효하지 않습니다. 먼저 영상을 일시정지 후 다시 시도하세요.');
        return;
      }
      if (roi.width <= 0 || roi.height <= 0) {
        setGrabError('ROI의 너비와 높이는 0보다 커야 합니다.');
        return;
      }
      if (
        roi.x < 0 ||
        roi.y < 0 ||
        roi.x + roi.width > (video.width || 1920) ||
        roi.y + roi.height > (video.height || 480)
      ) {
        setGrabError('ROI 영역이 원본 영상 해상도 범위를 벗어났습니다.');
        return;
      }

      setIsGrabbing(true);
      grabBusyRef.current = true;
      const epoch = ++grabEpochRef.current;
      setGrabError(null);

      try {
        const sourceImg = await loadImageFromUrl(imageBlobUrl);
        const { cropBlobUrl, imageData } = cropExactPixels(sourceImg, roi);
        if (epoch !== grabEpochRef.current) { URL.revokeObjectURL(cropBlobUrl); return; }

        if (prevCropBlobUrlRef.current) {
          URL.revokeObjectURL(prevCropBlobUrlRef.current);
        }
        prevCropBlobUrlRef.current = cropBlobUrl;

        const newCrop: CropData = {
          cropBlobUrl,
          imageData,
          roi: { ...roi },
          width: roi.width,
          height: roi.height,
          captureId: capture.capture_id,
          videoId: capture.video_id,
          sourceRevision: capture.source_revision,
          frameIndex: capture.frame_index,
          createdAt: new Date().toISOString(),
        };

        setCropData(newCrop);
        setRoiState('APPLIED');
        const center = computeRoiCenter(roi);
        setCropMessage(
          `ROI Crop 적용 완료 [Center: (${center.centerX}, ${center.centerY}) · ${roi.width}×${roi.height}px] → 600×600 Product Focus 반영`
        );
      } catch (err: any) {
        console.error('Crop application error:', err);
        setGrabError(`Crop 적용 실패: ${err.message}`);
        // Maintain EDITING state on error
      } finally {
        grabBusyRef.current = false;
        setIsGrabbing(false);
      }
      return;
    }

    // CASE C: ROI is APPLIED -> Same frame re-confirmation without redundant server calls
    if (roiState === 'APPLIED') {
      if (capture && capture.frame_index === frameIndex && cropData) {
        setCropMessage(
          `현재 녹화 프레임 #${frameIndex} 유지: 같은 프레임은 새 광학 정보가 아닙니다. 새 이미지 재검사는 다른 프레임을 선택하세요.`
        );
        return;
      }
    }

    const frameKey = `${sourceKey(video)}:${frameIndex}`;
    if (acquiredFramesRef.current.has(frameKey)) {
      setGrabError('이미 획득한 녹화 프레임입니다. 새 Capture ID만 바꿔 재검사하지 않습니다. 다른 프레임을 선택하세요.');
      return;
    }
    if (roiState !== 'NO_ROI' && !roiFits(roi, video)) {
      setRoiState('NO_ROI');
      setCropData(null);
      setGrabError('ROI 좌표가 현재 원본 영상에 유효하지 않습니다. ROI를 다시 지정하세요.');
      return;
    }
    startSelection();
    setCropData(null);
    setCropMessage(null);
    setIsGrabbing(true);
    grabBusyRef.current = true;
    const epoch = ++grabEpochRef.current;
    setGrabError(null);
    let pendingBlobUrl: string | null = null;

    try {
      // 1. Call FastAPI Grab API with exact frame index and source revision
      const captureResult = await grabFrame(
        video.video_id,
        frameIndex,
        video.source_revision
      );

      if (!sameSource(captureResult, video) || captureResult.frame_index !== frameIndex) throw new Error('GRAB_SOURCE_MISMATCH');

      // 2. Fetch binary PNG image blob from CaptureStore
      const imageBlob = await fetchCaptureImageBlob(captureResult.capture_id);
      if (epoch !== grabEpochRef.current) return;

      const newBlobUrl = URL.createObjectURL(imageBlob);
      pendingBlobUrl = newBlobUrl;
      if (roiState !== 'NO_ROI') {
        const sourceImage = await loadImageFromUrl(newBlobUrl);
        const nextCrop = cropExactPixels(sourceImage, roi);
        if (epoch !== grabEpochRef.current) {
          URL.revokeObjectURL(nextCrop.cropBlobUrl); return;
        }
        if (prevCropBlobUrlRef.current) URL.revokeObjectURL(prevCropBlobUrlRef.current);
        prevCropBlobUrlRef.current = nextCrop.cropBlobUrl;
        setCropData({ ...nextCrop, roi: { ...roi }, width: roi.width, height: roi.height,
          captureId: captureResult.capture_id, videoId: captureResult.video_id,
          sourceRevision: captureResult.source_revision, frameIndex, createdAt: new Date().toISOString() });
        setRoiState('APPLIED');
        setCropMessage(`새 Capture #${frameIndex}에 기존 ROI ${roi.width}×${roi.height}px 적용. 병 전체 포함 여부를 확인하세요.`);
      }
      acquiredFramesRef.current.add(frameKey);
      setCapture(captureResult);
      if (prevBlobUrlRef.current) URL.revokeObjectURL(prevBlobUrlRef.current);
      prevBlobUrlRef.current = newBlobUrl;
      setImageBlobUrl(newBlobUrl);
      pendingBlobUrl = null;

      // When grabbing full frame without applied ROI, clear previous cropData so ImageView shows Overview
      if (roiState === 'NO_ROI') {
        setCropData(null);
        setCropMessage(null);
      }
    } catch (err: any) {
      console.error('Frame Grab error:', err);
      const errorCode = err?.data?.detail?.error_code || err?.message || 'UNKNOWN_ERROR';
      let userFriendlyMsg = '프레임 캡처 중 오류가 발생했습니다.';

      if (errorCode === 'CAPTURE_ORIGIN_FORBIDDEN' || err?.status === 403) {
        userFriendlyMsg = '요청 Origin이 서버 보안 정책에 의해 거부되었습니다. (CORS Origin 확인 필요)';
      } else if (errorCode === 'FRAME_INDEX_OUT_OF_RANGE') {
        userFriendlyMsg = '지정한 프레임 번호가 영상 범위를 벗어났습니다.';
      } else if (errorCode === 'SOURCE_REVISION_MISMATCH') {
        userFriendlyMsg = '영상 소스 버전이 일치하지 않습니다. 메타데이터를 새로고침하세요.';
      } else if (errorCode === 'CAPTURE_RATE_LIMIT_EXCEEDED') {
        userFriendlyMsg = '캡처 요청이 너무 빠릅니다. 잠시 후 다시 시도하세요.';
      } else if (err?.message) {
        userFriendlyMsg = `Grab 실패: ${err.message}`;
      }

      setGrabError(userFriendlyMsg);
    } finally {
      if (pendingBlobUrl) URL.revokeObjectURL(pendingBlobUrl);
      grabBusyRef.current = false;
      setIsGrabbing(false);
    }
  };

  // Handle ROI Selection Toggle
  const handleToggleRoi = async (currentFrame: number, isPaused: boolean) => {
    if (!isPaused) {
      setGrabError('ROI를 선택하려면 먼저 영상을 일시정지하세요.');
      return;
    }

    if (roiState === 'EDITING') {
      setRoiState('APPLIED');
      return;
    }

    if (roiState === 'APPLIED') {
      startSelection();
      setCropData(null);
      setRoiState('EDITING');
      return;
    }

    // Turning on ROI editing from NO_ROI:
    // If we don't have a capture yet, or if current capture frame differs from paused frame, grab once
    if (!capture || capture.frame_index !== currentFrame) {
      await handleGrab(currentFrame);
    }

    setRoiState('EDITING');
    setGrabError(null);
  };

  // Handle ROI modification (moving/resizing shifts APPLIED -> EDITING)
  const handleChangeRoi = (newRoi: RoiRect) => {
    grabEpochRef.current++;
    startSelection();
    setRoi(newRoi);
    if (roiState === 'APPLIED') {
      setRoiState('EDITING');
    }
  };

  // Reset ROI to default centered rectangle & reset state to NO_ROI
  const handleResetRoi = () => {
    grabEpochRef.current++;
    startSelection();
    setRoi(DEFAULT_ROI);
    setRoiState('NO_ROI');
    setCropData(null);
    setCropMessage(null);
    setGrabError(null);
  };

  const handleModeChange = (newMode: 'MANUAL' | 'AUTO') => {
    setMode(newMode);
    if (newMode === 'AUTO') {
      setGrabError('AUTO 검사 연결 준비 중 — 현재는 MANUAL Grab 및 ROI 선택만 지원됩니다.');
      setRoiState('NO_ROI');
    } else {
      setGrabError(null);
    }
  };

  const handleRunAgent = (_inspectionId: string) => {
    const el = document.getElementById('agent-diagnostic-panel');
    if (el) {
      el.scrollIntoView({ behavior: 'smooth' });
    }
  };

  // Determine current workflow step
  let currentStep = 1;
  if (currentInspection) {
    currentStep = 4;
  } else if (cropData) {
    currentStep = 3;
  } else if (capture) {
    currentStep = 2;
  }

  return (
    <div className="min-h-screen flex flex-col bg-slate-950">
      {/* Top Application Header */}
      <Header
        mode={mode}
        onModeChange={handleModeChange}
        apiConnected={apiConnected}
        activeVideoId={video?.video_id}
      />

      {/* Main Workspace Body */}
      <main className="main-content">
        <div className="app-container">
          {/* Stepper Strip */}
          <WorkflowStepper currentStep={currentStep} />

          {/* General connection alert if offline */}
          {generalError && (
            <div className="alert-banner alert-warning">
              <span>{generalError}</span>
            </div>
          )}

          {/* 1. Primary Live View Section with Integrated ROI Tools */}
          <div className="live-video-selection">
            <label htmlFor="live-video-source">LiveView 영상 선택</label>
            <select id="live-video-source" value={video?.video_id ?? ''} disabled={isGrabbing || !videos.length}
              onChange={event => {
                const selected = videos.find(item => item.video_id === event.target.value);
                if (selected) applyVideo(selected);
              }}>
              {!videos.length && <option value="">영상 목록 대기</option>}
              {videos.map(item => <option key={item.video_id} value={item.video_id}>
                {item.video_id} · {item.duration_seconds}초 · {item.frame_count}프레임{item.video_id === 'VID-000003' ? ' · 양품/불량 원본 혼합 데모' : ''}
              </option>)}
            </select>
            <span>원본 분류를 섞은 합성 데모이며 PatchCore OK/NG 판정을 보장하지 않습니다. 영상 변경 시 ROI를 다시 지정하세요.</span>
          </div>
          <LiveView
            key={video ? sourceKey(video) : 'no-video'}
            video={video}
            streamUrl={streamUrl}
            isGrabbing={isGrabbing}
            onGrab={handleGrab}
            mode={mode}
            error={grabError}
            capture={capture}
            imageBlobUrl={imageBlobUrl}
            roi={roi}
            onChangeRoi={handleChangeRoi}
            roiState={roiState}
            onToggleRoi={handleToggleRoi}
            onResetRoi={handleResetRoi}
            cropMessage={cropMessage}
          />

          {/* 2. Middle Grid: 600×600 Precision ImageView & Inspection Panel */}
          <div className="middle-grid">
            <ImageView
              capture={capture}
              imageBlobUrl={imageBlobUrl}
              cropData={cropData}
              isLoading={isGrabbing}
              error={grabError}
              currentInspection={currentInspection}
            />

            <div className="flex flex-col gap-4">
              <InspectionTabs
                grabPanel={<GrabInspectionPanel crop={cropData} enabled={mode === 'MANUAL' && roiState === 'APPLIED' && !isGrabbing} manualMode={mode === 'MANUAL'}
                  currentInspection={currentInspection}
                  onSelectionStart={startSelection} onInspectionChange={handleInspectionChange} onGroupChange={setReinspectionGroup} />}
                judgePanel={<VisionReviewPanel inspection={currentInspection} reinspectionGroup={reinspectionGroup} />}
                staticImagePanel={<InspectionPanel
                  currentInspection={currentInspection}
                  onInspectionChange={handleInspectionChange}
                  onSelectionStart={startSelection}
                  getSelectionVersion={getSelectionVersion}
                  onRunAgent={handleRunAgent}
                />}
              />
            </div>
          </div>

          {/* 3. Bottom Full Width: AI Agent Diagnostic Panel */}
          <AgentPanel inspectionId={currentInspection?.inspection_id || null} />
        </div>
      </main>
    </div>
  );
};

export default App;

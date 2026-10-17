import React, { useRef, useState } from 'react';
import {
  Play,
  Pause,
  Camera,
  RotateCcw,
  SkipBack,
  SkipForward,
  AlertCircle,
  Activity,
  Square,
  CheckCircle2,
} from 'lucide-react';
import type { VideoMetadata, CaptureMetadata } from '../types/video';
import type { RoiRect, RoiState } from '../types/roi';
import { formatRoiCenter } from '../utils/coordinateTransforms';
import { RoiOverlay } from './RoiOverlay';

interface LiveViewProps {
  video: VideoMetadata | null;
  streamUrl: string;
  isGrabbing: boolean;
  onGrab: (frameIndex: number) => Promise<void> | void;
  mode: 'MANUAL' | 'AUTO';
  error: string | null;
  capture: CaptureMetadata | null;
  imageBlobUrl: string | null;
  roi: RoiRect;
  onChangeRoi: (roi: RoiRect) => void;
  roiState: RoiState;
  onToggleRoi: (currentFrame: number, isPaused: boolean) => void;
  onResetRoi: () => void;
  cropMessage: string | null;
}

export const LiveView: React.FC<LiveViewProps> = ({
  video,
  streamUrl,
  isGrabbing,
  onGrab,
  mode,
  error,
  capture,
  imageBlobUrl,
  roi,
  onChangeRoi,
  roiState,
  onToggleRoi,
  onResetRoi,
  cropMessage,
}) => {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [isPlaying, setIsPlaying] = useState<boolean>(true);
  const [currentTime, setCurrentTime] = useState<number>(0);
  const duration = video?.duration_seconds || 8.0;
  const [currentFrame, setCurrentFrame] = useState<number>(0);
  const [videoLoaded, setVideoLoaded] = useState<boolean>(false);
  const [videoError, setVideoError] = useState<string | null>(null);

  const fps = video?.fps || 30.0;
  const maxFrames = video?.frame_count ? video.frame_count - 1 : 239;

  // Invalidate ROI editing when playback state or timeline changes
  const invalidateRoiIfActive = () => {
    if (roiState !== 'NO_ROI') {
      onToggleRoi(currentFrame, false);
    }
  };

  // Video time update handler
  const handleTimeUpdate = () => {
    if (videoRef.current) {
      const time = videoRef.current.currentTime;
      setCurrentTime(time);
      const calculatedFrame = Math.min(
        Math.max(0, Math.floor(time * fps)),
        maxFrames
      );
      if (calculatedFrame !== currentFrame) {
        setCurrentFrame(calculatedFrame);
        if (roiState !== 'NO_ROI') {
          invalidateRoiIfActive();
        }
      }
    }
  };

  const handlePlayPause = () => {
    if (!videoRef.current) return;
    if (videoRef.current.paused) {
      invalidateRoiIfActive();
      videoRef.current
        .play()
        .then(() => setIsPlaying(true))
        .catch((err) => {
          console.warn('Playback error:', err);
          setIsPlaying(false);
        });
    } else {
      videoRef.current.pause();
      setIsPlaying(false);
    }
  };

  const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    invalidateRoiIfActive();
    const targetTime = parseFloat(e.target.value);
    if (videoRef.current) {
      videoRef.current.currentTime = targetTime;
      setCurrentTime(targetTime);
      const calculatedFrame = Math.min(
        Math.max(0, Math.floor(targetTime * fps)),
        maxFrames
      );
      setCurrentFrame(calculatedFrame);
    }
  };

  const stepFrame = (delta: number) => {
    if (!videoRef.current) return;
    if (!videoRef.current.paused) {
      videoRef.current.pause();
      setIsPlaying(false);
    }
    invalidateRoiIfActive();

    const frameDuration = 1 / fps;
    const newTime = Math.min(
      Math.max(0, videoRef.current.currentTime + delta * frameDuration),
      duration
    );
    videoRef.current.currentTime = newTime;
    setCurrentTime(newTime);
    const calculatedFrame = Math.min(
      Math.max(0, Math.floor(newTime * fps)),
      maxFrames
    );
    setCurrentFrame(calculatedFrame);
  };

  const handleRestart = () => {
    invalidateRoiIfActive();
    if (videoRef.current) {
      videoRef.current.currentTime = 0;
      setCurrentTime(0);
      setCurrentFrame(0);
      videoRef.current.play().then(() => setIsPlaying(true));
    }
  };

  const handleGrabClick = () => {
    if (isGrabbing) return;
    // Auto-pause upon manual grab for precision, if playing
    if (videoRef.current && !videoRef.current.paused) {
      videoRef.current.pause();
      setIsPlaying(false);
    }
    onGrab(currentFrame);
  };

  const handleRoiToggleClick = () => {
    const isPaused = videoRef.current ? videoRef.current.paused : !isPlaying;
    onToggleRoi(currentFrame, isPaused);
  };

  // Format seconds to mm:ss.SSS
  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    const ms = Math.floor((seconds % 1) * 1000);
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}.${ms.toString().padStart(3, '0')}`;
  };

  const isPaused = !isPlaying;

  return (
    <div className="panel-card">
      <div className="panel-header">
        <div className="panel-title-area">
          <Activity size={16} className="text-cyan" />
          <h2 className="panel-title">H.264 컨베이어 라이브 뷰어 (Live View)</h2>
          <span className="phase-badge active font-mono">1920×480 CFR</span>
          {roiState === 'EDITING' && (
            <span className="text-xs bg-cyan-500/10 text-cyan border border-cyan-500/30 px-2 py-0.5 rounded font-mono flex items-center gap-1">
              <Square size={11} />
              <span>ROI EDITING</span>
            </span>
          )}
          {roiState === 'APPLIED' && (
            <span className="text-xs bg-emerald-500/10 text-emerald border border-emerald-500/30 px-2 py-0.5 rounded font-mono flex items-center gap-1">
              <CheckCircle2 size={11} />
              <span>ROI APPLIED</span>
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {mode === 'AUTO' && (
            <span className="text-xs bg-amber-500/10 text-amber border border-amber-500/30 px-2.5 py-0.5 rounded-full font-medium">
              AUTO 검사 연결 준비 중 (현재는 MANUAL Grab만 지원)
            </span>
          )}
          <span className="panel-meta">Line 1 · Bottle Conveyor Stream</span>
        </div>
      </div>

      <div className="panel-body">
        {/* Error notification if any */}
        {(error || videoError) && (
          <div className="alert-banner alert-error">
            <AlertCircle size={16} />
            <span>{error || videoError}</span>
          </div>
        )}

        {/* Informative message for ROI Crop */}
        {cropMessage && (
          <div className="alert-banner alert-success">
            <CheckCircle2 size={16} />
            <span>{cropMessage}</span>
          </div>
        )}

        {/* Video Canvas Container */}
        <div className="video-wrapper">
          {/* Overlays */}
          <div className="video-overlay-badge">
            <div className={`live-indicator-dot ${isPaused ? 'paused' : ''}`} />
            <span>
              {roiState === 'EDITING'
                ? `FROZEN FRAME (ROI EDITING${capture ? ` #${capture.frame_index}` : ''})`
                : roiState === 'APPLIED'
                ? `FROZEN FRAME (ROI APPLIED${capture ? ` #${capture.frame_index}` : ''})`
                : isPlaying
                ? videoLoaded
                  ? 'STREAM PLAYING'
                  : 'CONNECTING STREAM...'
                : 'STREAM PAUSED'}
            </span>
          </div>

          <div className="video-overlay-fps">
            <span>
              {fps.toFixed(2)} FPS · {video?.width || 1920}×{video?.height || 480}
            </span>
          </div>

          {/* HTML5 Video Element */}
          {streamUrl ? (
            <video
              ref={videoRef}
              src={streamUrl}
              className="video-element"
              loop
              playsInline
              autoPlay
              muted
              crossOrigin="anonymous"
              onTimeUpdate={handleTimeUpdate}
              onLoadedMetadata={() => {
                setVideoLoaded(true);
              }}
              onError={(e) => {
                console.error('Video loading error:', e);
                setVideoError('영상 스트림을 로드할 수 없습니다. FastAPI 서버 상태를 확인하세요.');
              }}
            />
          ) : (
            <div className="text-dim font-mono text-sm">
              비디오 스트림 URL 연결 대기 중...
            </div>
          )}

          {/* Interactive ROI Overlay when active */}
          {roiState !== 'NO_ROI' && (
            <RoiOverlay
              roi={roi}
              roiState={roiState}
              onChangeRoi={onChangeRoi}
              frozenImageUrl={imageBlobUrl}
              imageWidth={video?.width || 1920}
              imageHeight={video?.height || 480}
            />
          )}
        </div>

        {/* Control and Scrubber Bar */}
        <div className="video-controls-bar">
          {/* Progress / Seek bar */}
          <div className="scrubber-row">
            <span className="time-counter">{formatTime(currentTime)}</span>
            <input
              type="range"
              min={0}
              max={duration || 8.0}
              step={0.001}
              value={currentTime}
              onChange={handleSeek}
              className="scrubber-slider"
              title="비디오 위치 탐색 (Seek)"
            />
            <span className="time-counter">
              {formatTime(duration)}
              <span className="text-cyan ml-2 font-mono">
                [Frame {currentFrame} / {maxFrames}]
              </span>
            </span>
          </div>

          {/* Action Buttons Row */}
          <div className="controls-actions-row">
            {/* Playback Controls Group */}
            <div className="playback-buttons">
              <button
                type="button"
                className="btn btn-outline"
                onClick={handlePlayPause}
                title={isPlaying ? '일시정지 (Pause)' : '재생 (Play)'}
              >
                {isPlaying ? <Pause size={16} /> : <Play size={16} fill="currentColor" />}
                <span>{isPlaying ? 'Pause' : 'Play'}</span>
              </button>

              <button
                type="button"
                className="btn btn-outline"
                onClick={() => stepFrame(-1)}
                title="1프레임 뒤로 (-1 Frame)"
              >
                <SkipBack size={15} />
                <span className="hidden sm:inline">-1 Frame</span>
              </button>

              <button
                type="button"
                className="btn btn-outline"
                onClick={() => stepFrame(1)}
                title="1프레임 앞으로 (+1 Frame)"
              >
                <SkipForward size={15} />
                <span className="hidden sm:inline">+1 Frame</span>
              </button>

              <button
                type="button"
                className="btn btn-outline"
                onClick={handleRestart}
                title="처음부터 재생"
              >
                <RotateCcw size={15} />
              </button>
            </div>

            {/* Vision Inspection & ROI Action Group (Crop button integrated into Grab) */}
            <div className="roi-actions-group">
              {/* 1. Grab Button (handles both full frame grab and ROI crop grab) */}
              <button
                type="button"
                className={`btn grab-cta-button ${
                  roiState === 'EDITING'
                    ? 'btn-grab-editing'
                    : roiState === 'APPLIED'
                    ? 'btn-grab-applied'
                    : 'btn-primary'
                }`}
                onClick={handleGrabClick}
                disabled={isGrabbing || !streamUrl}
                title={
                  roiState === 'EDITING'
                    ? '선택된 ROI 영역을 600×600 ImageView로 Crop 반영합니다'
                    : roiState === 'APPLIED'
                    ? '현재 적용된 Crop 결과를 유지/재확인합니다'
                    : '서버에서 정확한 현재 프레임을 전체 캡처합니다'
                }
              >
                {isGrabbing ? (
                  <>
                    <div className="spinner" />
                    <span>처리 중...</span>
                  </>
                ) : (
                  <>
                    <Camera size={16} />
                    <span>
                      {roiState === 'EDITING'
                        ? 'Grab (Crop 반영)'
                        : roiState === 'APPLIED'
                        ? 'Grab (적용됨)'
                        : 'Grab'}
                    </span>
                  </>
                )}
              </button>

              {/* 2. ROI Select Toggle Button */}
              <button
                type="button"
                className={`btn ${
                  roiState === 'EDITING'
                    ? 'btn-active-cyan'
                    : roiState === 'APPLIED'
                    ? 'btn-active-green'
                    : 'btn-outline'
                }`}
                onClick={handleRoiToggleClick}
                disabled={isPlaying}
                title={
                  isPlaying
                    ? 'ROI를 선택하려면 먼저 영상을 일시정지하세요.'
                    : roiState === 'EDITING'
                    ? 'ROI 편집 모드 닫기'
                    : roiState === 'APPLIED'
                    ? 'ROI 재수정 모드로 전환'
                    : '영상 위에서 검사할 병의 ROI 사각형을 선택합니다.'
                }
              >
                <Square size={16} />
                <span>
                  {roiState === 'EDITING'
                    ? 'ROI 닫기'
                    : roiState === 'APPLIED'
                    ? 'ROI 재수정'
                    : 'ROI 선택'}
                </span>
              </button>

              {/* 3. ROI Reset Button */}
              <button
                type="button"
                className="btn btn-outline text-dim"
                onClick={onResetRoi}
                disabled={roiState === 'NO_ROI'}
                title="ROI 사각형을 초기화하고 일반 뷰 모드로 복귀합니다"
              >
                <span>ROI 초기화</span>
              </button>
            </div>
          </div>

          {/* User Workflow Guidance */}
          <div className="text-xs text-slate-400 font-mono mt-2 flex items-center gap-1">
            <span>안내: 1. Pause → 2. ROI 선택 → 3. 영역 조정 → 4. Grab</span>
          </div>
        </div>

        {/* Stream Metadata Grid */}
        <div className="metadata-grid">
          <div className="meta-pill">
            <span className="meta-pill-label">비디오 ID</span>
            <span className="meta-pill-value text-cyan">{video?.video_id || 'VID-000001'}</span>
          </div>
          <div className="meta-pill">
            <span className="meta-pill-label">해상도 / 비율</span>
            <span className="meta-pill-value">
              {video ? `${video.width}×${video.height}` : '1920×480'}
            </span>
          </div>
          <div className="meta-pill">
            <span className="meta-pill-label">프레임률 (FPS)</span>
            <span className="meta-pill-value">{fps.toFixed(2)} CFR</span>
          </div>
          <div className="meta-pill">
            <span className="meta-pill-label">현재 프레임</span>
            <span className="meta-pill-value font-mono text-cyan">
              #{currentFrame} / {maxFrames}
            </span>
          </div>
          <div className="meta-pill">
            <span className="meta-pill-label">ROI 중심 좌표</span>
            <span className="meta-pill-value font-mono text-xs truncate" title={roiState !== 'NO_ROI' ? formatRoiCenter(roi) : '비활성'}>
              {roiState !== 'NO_ROI' ? formatRoiCenter(roi) : '비활성 (미선택)'}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};

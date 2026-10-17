import React, { useState, useEffect, useRef } from 'react';
import {
  Cpu,
  Search,
  Play,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Sparkles,
} from 'lucide-react';
import type { InspectionResponse } from '../types/inspection';
import {
  getInspectionImages,
  getRecentInspections,
  getInspection,
  createInspection,
} from '../api/inspection';

interface InspectionPanelProps {
  currentInspection: InspectionResponse | null;
  onInspectionChange: (inspection: InspectionResponse | null) => void;
  onRunAgent: (inspectionId: string) => void;
}

export const InspectionPanel: React.FC<InspectionPanelProps> = ({
  currentInspection,
  onInspectionChange,
  onRunAgent,
}) => {
  const [imageIds, setImageIds] = useState<string[]>([]);
  const [selectedImageId, setSelectedImageId] = useState<string>('IMG-BOTTLE-0001');
  const [productId, setProductId] = useState<string>('ABCD1541');
  const [inputInspectionId, setInputInspectionId] = useState<string>('INSP-001396');
  const [recentInspections, setRecentInspections] = useState<InspectionResponse[]>([]);

  const [isLoadingImages, setIsLoadingImages] = useState<boolean>(false);
  const [isQuerying, setIsQuerying] = useState<boolean>(false);
  const [isInspecting, setIsInspecting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const initialLoadedRef = useRef<boolean>(false);

  // Load available registered image IDs and recent inspections on mount
  useEffect(() => {
    let isMounted = true;

    void (async () => {
      try {
        setIsLoadingImages(true);
        const imagesRes = await getInspectionImages();
        if (isMounted && imagesRes.image_ids && imagesRes.image_ids.length > 0) {
          setImageIds(imagesRes.image_ids);
          setSelectedImageId((prev) => (prev ? prev : imagesRes.image_ids[0]));
        }
      } catch (err: any) {
        console.warn('Failed to load registered image IDs:', err);
      } finally {
        if (isMounted) setIsLoadingImages(false);
      }

      try {
        const listRes = await getRecentInspections(20);
        if (isMounted && listRes.inspections && listRes.inspections.length > 0) {
          setRecentInspections(listRes.inspections);
          // Set initial inspection to a verified one if none selected yet
          if (!initialLoadedRef.current) {
            initialLoadedRef.current = true;
            const initial =
              listRes.inspections.find((i) => i.inspection_id === 'INSP-001396') ||
              listRes.inspections[0];
            onInspectionChange({
              ...initial,
              provenance: 'STORED_RESULT',
            });
            setInputInspectionId(initial.inspection_id);
          }
        }
      } catch (err: any) {
        console.warn('Failed to load recent inspections:', err);
      }
    })();

    return () => {
      isMounted = false;
    };
  }, [onInspectionChange]);

  // Handle Query Stored Inspection by ID (Zero ML call)
  const handleQueryInspection = async (
    targetId?: string,
    customProvenance?: 'STORED_RESULT' | 'RECORDED_TEST_FIXTURE'
  ) => {
    const idToFetch = (targetId || inputInspectionId).trim();
    if (!idToFetch) {
      setError('검사 ID를 입력하거나 목록에서 선택하세요.');
      return;
    }

    setIsQuerying(true);
    setError(null);

    try {
      const res = await getInspection(idToFetch);
      const prov =
        customProvenance || (idToFetch === 'INSP-001391' ? 'RECORDED_TEST_FIXTURE' : 'STORED_RESULT');
      onInspectionChange({
        ...res,
        provenance: prov,
      });
      setInputInspectionId(idToFetch);
    } catch (err: any) {
      console.error('Inspection query error:', err);
      setError(`검사 조회 실패: ${err.message || '해당 ID의 검사 기록을 찾을 수 없습니다.'}`);
    } finally {
      setIsQuerying(false);
    }
  };

  // Handle New Live Inspection Execution
  const handleExecuteInspection = async () => {
    if (!selectedImageId) {
      setError('검사할 등록 이미지를 선택하세요.');
      return;
    }

    setIsInspecting(true);
    setError(null);

    try {
      const res = await createInspection(productId, selectedImageId);
      onInspectionChange({
        ...res,
        provenance: 'LIVE_INSPECTION',
      });
      setInputInspectionId(res.inspection_id);
    } catch (err: any) {
      console.error('Live inspection execution error:', err);
      setError(`검사 실행 실패: ${err.message || 'PatchCore 검사 중 오류가 발생했습니다.'}`);
    } finally {
      setIsInspecting(false);
    }
  };

  // Quick Preset Scenario Selection
  const handleSelectPresetScenario = (
    id: string,
    imgId: string,
    customProvenance?: 'STORED_RESULT' | 'RECORDED_TEST_FIXTURE'
  ) => {
    setSelectedImageId(imgId);
    setInputInspectionId(id);
    void handleQueryInspection(id, customProvenance);
  };

  return (
    <div className="panel-card inspection-panel-card">
      {/* Header */}
      <div className="panel-header">
        <div className="panel-title-area">
          <Cpu size={16} className="text-amber" />
          <h2 className="panel-title">정적 이미지 결함 검사 (Inspection Panel)</h2>
        </div>
        <div className="flex items-center gap-2">
          {currentInspection?.provenance === 'LIVE_INSPECTION' ? (
            <span className="text-xs bg-emerald-500/15 text-emerald border border-emerald-500/30 px-2.5 py-0.5 rounded-full font-mono font-medium">
              LIVE INSPECTION
            </span>
          ) : currentInspection?.provenance === 'RECORDED_TEST_FIXTURE' ? (
            <span className="text-xs bg-amber-500/15 text-amber border border-amber-500/30 px-2.5 py-0.5 rounded-full font-mono font-medium">
              RECORDED TEST FIXTURE
            </span>
          ) : currentInspection ? (
            <span className="text-xs bg-sky-500/15 text-sky-400 border border-sky-500/30 px-2.5 py-0.5 rounded-full font-mono font-medium">
              STORED RESULT
            </span>
          ) : (
            <span className="phase-badge deferred font-mono">NOT ANALYZED</span>
          )}
        </div>
      </div>

      <div className="panel-body flex flex-col justify-between gap-4">
        {/* Source Provenance Guide Alert */}
        <div className="text-[11px] text-slate-400 bg-slate-900/60 border border-slate-800 p-2.5 rounded-lg flex items-center justify-between">
          <span>
            <strong className="text-cyan">SOURCE: REGISTERED STATIC IMAGE</strong> — MVTec AD 병 데이터셋 기반
          </span>
          <span className="text-slate-500 font-mono text-[10px]">Threshold: 34.1442</span>
        </div>

        {/* Error notification if any */}
        {error && (
          <div className="alert-banner alert-error">
            <AlertTriangle size={15} />
            <span>{error}</span>
          </div>
        )}

        {/* 1. Static Image & Inspection Selection Controls */}
        <div className="bg-slate-900/80 border border-slate-800/80 p-3 rounded-xl space-y-3">
          <div className="text-xs font-semibold text-slate-300 flex items-center justify-between">
            <span>검사 대상 및 이력 선택</span>
            <div className="flex items-center gap-1.5 text-[11px]">
              <span className="text-slate-400">발표 시연 숏컷:</span>
              <button
                type="button"
                className="text-cyan hover:underline font-mono"
                onClick={() => handleSelectPresetScenario('INSP-001387', 'IMG-BOTTLE-0084')}
                title="T01 정상 병 검사 (OK)"
              >
                [T01:OK]
              </button>
              <button
                type="button"
                className="text-amber hover:underline font-mono"
                onClick={() => handleSelectPresetScenario('INSP-001388', 'IMG-BOTTLE-INJ-0001')}
                title="T03 저조도 경고 검사 (REINSPECT)"
              >
                [T03:Warn]
              </button>
              <button
                type="button"
                className="text-emerald hover:underline font-mono"
                onClick={() => handleSelectPresetScenario('INSP-001390', 'IMG-BOTTLE-0001')}
                title="T06 결함 미검출 한계 사례 (기존 판정 유지 OK)"
              >
                [T06:한계OK]
              </button>
              <button
                type="button"
                className="text-rose-400 hover:underline font-mono"
                onClick={() =>
                  handleSelectPresetScenario('INSP-001391', 'IMG-BOTTLE-0001', 'RECORDED_TEST_FIXTURE')
                }
                title="Rule 4 Mock 불량 탐지 (NG Fixture)"
              >
                [Mock:NG]
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {/* Image ID Dropdown */}
            <div>
              <label className="text-[11px] text-slate-400 font-medium block mb-1">
                등록 이미지 (Image ID)
              </label>
              <select
                value={selectedImageId}
                onChange={(e) => setSelectedImageId(e.target.value)}
                disabled={isLoadingImages || isInspecting}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 font-mono focus:border-cyan focus:outline-none"
              >
                {imageIds.map((id) => (
                  <option key={id} value={id}>
                    {id}
                  </option>
                ))}
              </select>
            </div>

            {/* Product ID Input */}
            <div>
              <label className="text-[11px] text-slate-400 font-medium block mb-1">
                제품 ID (Product ID)
              </label>
              <input
                type="text"
                value={productId}
                onChange={(e) => setProductId(e.target.value)}
                disabled={isInspecting}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 font-mono focus:border-cyan focus:outline-none"
                placeholder="예: ABCD1541"
              />
            </div>
          </div>

          {/* Inspection ID Input & Action Buttons */}
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 pt-1">
            <div className="flex-1 flex items-center gap-1.5">
              <input
                type="text"
                list="recent-inspections-list"
                value={inputInspectionId}
                onChange={(e) => setInputInspectionId(e.target.value)}
                disabled={isQuerying || isInspecting}
                placeholder="검사 ID (예: INSP-001387)"
                className="flex-1 bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 font-mono focus:border-cyan focus:outline-none"
              />
              <datalist id="recent-inspections-list">
                {recentInspections.map((insp) => (
                  <option
                    key={insp.inspection_id}
                    value={insp.inspection_id}
                    label={`${insp.final_result} (Score: ${insp.anomaly_score?.toFixed(2) ?? '—'})`}
                  />
                ))}
              </datalist>
              <button
                type="button"
                onClick={() => handleQueryInspection()}
                disabled={isQuerying || !inputInspectionId.trim()}
                className="btn btn-outline text-xs px-3 py-1.5 flex items-center gap-1.5"
                title="기존 저장된 검사 결과 조회"
              >
                {isQuerying ? <div className="spinner" /> : <Search size={13} />}
                <span>조회</span>
              </button>
            </div>

            <button
              type="button"
              onClick={handleExecuteInspection}
              disabled={isInspecting || !selectedImageId}
              className="btn btn-primary text-xs px-4 py-1.5 flex items-center justify-center gap-1.5 bg-gradient-to-r from-cyan-600 to-sky-500 text-white font-semibold"
              title="선택한 등록 이미지로 FastAPI PatchCore 신규 검사 실행"
            >
              {isInspecting ? (
                <>
                  <div className="spinner" />
                  <span>검사 중...</span>
                </>
              ) : (
                <>
                  <Play size={13} fill="currentColor" />
                  <span>Inspect 실행</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* 2. Inspection Result Metric Tiles */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
          {/* Final Verdict */}
          <div className="meta-pill">
            <span className="meta-pill-label">종합 판정 (Verdict)</span>
            <div className="flex items-center gap-1.5 mt-1">
              {currentInspection?.final_result === 'OK' && (
                <CheckCircle2 size={16} className="text-emerald" />
              )}
              {currentInspection?.final_result === 'NG' && (
                <XCircle size={16} className="text-rose-400" />
              )}
              {currentInspection?.final_result === 'REINSPECT' && (
                <AlertTriangle size={16} className="text-amber" />
              )}
              {currentInspection?.final_result === 'ERROR' && (
                <AlertTriangle size={16} className="text-red-500" />
              )}
              <span
                className={`meta-pill-value font-mono font-bold text-sm ${
                  currentInspection?.final_result === 'OK'
                    ? 'text-emerald'
                    : currentInspection?.final_result === 'NG'
                    ? 'text-rose-400'
                    : currentInspection?.final_result === 'REINSPECT'
                    ? 'text-amber'
                    : currentInspection?.final_result === 'ERROR'
                    ? 'text-red-500'
                    : 'text-dim'
                }`}
              >
                {currentInspection?.final_result || 'NOT RUN'}
              </span>
            </div>
          </div>

          {/* Anomaly Score */}
          <div className="meta-pill">
            <span className="meta-pill-label">이상 점수 (Score)</span>
            <span
              className={`meta-pill-value font-mono text-sm font-semibold ${
                currentInspection?.anomaly_score !== null &&
                currentInspection?.anomaly_score !== undefined &&
                currentInspection.anomaly_score >= 34.1442
                  ? 'text-rose-400'
                  : currentInspection?.anomaly_score
                  ? 'text-emerald'
                  : 'text-dim'
              }`}
            >
              {currentInspection?.anomaly_score !== null &&
              currentInspection?.anomaly_score !== undefined
                ? currentInspection.anomaly_score.toFixed(4)
                : '—'}
            </span>
          </div>

          {/* Image Quality Status */}
          <div className="meta-pill">
            <span className="meta-pill-label">영상 품질 (Quality)</span>
            <span
              className={`meta-pill-value font-mono text-xs font-semibold ${
                currentInspection?.image_quality_status === 'NORMAL'
                  ? 'text-emerald'
                  : currentInspection?.image_quality_status === 'WARNING_LOW_BRIGHTNESS'
                  ? 'text-amber'
                  : currentInspection?.image_quality_status === 'ERROR'
                  ? 'text-rose-400'
                  : 'text-dim'
              }`}
            >
              {currentInspection?.image_quality_status || '—'}
            </span>
          </div>

          {/* Reason Code */}
          <div className="meta-pill">
            <span className="meta-pill-label">사유 코드 (Reason)</span>
            <span
              className="meta-pill-value font-mono text-xs truncate text-cyan"
              title={currentInspection?.final_reason_code || '—'}
            >
              {currentInspection?.final_reason_code || '—'}
            </span>
          </div>
        </div>

        {/* 3. Detailed Metadata Summary Row */}
        {currentInspection && (
          <div className="bg-slate-900/60 border border-slate-800 p-2.5 rounded-lg text-xs font-mono text-slate-400 flex flex-wrap items-center justify-between gap-2">
            <div>
              <span className="text-slate-500">ID: </span>
              <span className="text-slate-200 font-bold">{currentInspection.inspection_id}</span>
              <span className="text-slate-500 ml-2">Image: </span>
              <span className="text-cyan">{currentInspection.image_id}</span>
              <span className="text-slate-500 ml-2">Inference: </span>
              <span className="text-slate-300">
                {currentInspection.inference_time_ms ? `${currentInspection.inference_time_ms.toFixed(1)} ms` : '—'}
              </span>
            </div>

            {/* Quick Trigger to Agent Diagnosis */}
            <button
              type="button"
              onClick={() => onRunAgent(currentInspection.inspection_id)}
              className="text-[11px] text-indigo-400 hover:text-indigo-300 flex items-center gap-1 font-sans font-medium"
            >
              <Sparkles size={12} />
              <span>하단 AI 진단 보고서로 이동</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

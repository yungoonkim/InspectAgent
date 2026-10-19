import React, { useState, useEffect, useCallback, useRef, useLayoutEffect } from 'react';
import {
  Bot,
  Sparkles,
  Shield,
  Search,
  AlertTriangle,
  CheckCircle2,
  ListFilter,
  FileText,
} from 'lucide-react';
import type { AgentReport } from '../types/agent';
import { getStoredAgentReport, runAgentAnalysis } from '../api/inspection';
import { agentFailureMessage, liveAnalysisLabel, type LiveAnalysisStatus } from '../utils/agentAnalysisState';

interface AgentPanelProps {
  inspectionId: string | null;
}

export const AgentPanel: React.FC<AgentPanelProps> = ({ inspectionId }) => {
  const [prevPropId, setPrevPropId] = useState<string | null>(inspectionId);
  const [activeInspectionId, setActiveInspectionId] = useState<string>(inspectionId || '');
  const [loadedReport, setReport] = useState<AgentReport | null>(null);
  const [reportOrigin, setReportOrigin] = useState<'STORED' | 'LIVE'>('STORED');
  const [liveState, setLiveState] = useState<{id:string; status:LiveAnalysisStatus} | null>(null);
  const requestVersion = useRef(0);
  const livePending = useRef(false);
  const activeId = useRef(activeInspectionId.trim());
  const currentTarget = activeInspectionId.trim();
  useLayoutEffect(() => { activeId.current = currentTarget; }, [currentTarget]);
  const report = loadedReport?.inspection_id === currentTarget ? loadedReport : null;
  const liveStatus = liveState?.id === currentTarget ? liveState.status : 'NOT_VERIFIED';

  const [isLoadingStored, setIsLoadingStored] = useState<boolean>(false);
  const [isAnalyzingLive, setIsAnalyzingLive] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Sync state if inspectionId prop changed
  if (inspectionId !== prevPropId) {
    setPrevPropId(inspectionId);
    setActiveInspectionId(inspectionId || '');
  }

  // Confirmation Modal state
  const [showConfirmModal, setShowConfirmModal] = useState<boolean>(false);

  const fetchStoredReport = useCallback(async (targetId: string) => {
    if (!targetId.trim()) return;
    const target = targetId.trim();
    const version = ++requestVersion.current;
    const isCurrent = () => version === requestVersion.current && activeId.current === target;
    setIsLoadingStored(true);
    setError(null);
    setReport(null);
    setLiveState({id:target, status:'NOT_VERIFIED'});

    try {
      const data = await getStoredAgentReport(target);
      if (!isCurrent()) return;
      if (data.inspection_id !== target) throw new Error('Stored report identity mismatch');
      setReport(data);
      setReportOrigin('STORED');
    } catch (err: any) {
      if (!isCurrent()) return;
      // If 404, it means no stored report exists yet
      setReport(null);
      const detailMsg = err?.data?.detail?.message || err?.message || '사전 저장된 보고서가 없습니다.';
      if (err?.status === 404) {
        setError(detailMsg);
      } else {
        setError(`보고서 조회 중 오류: ${detailMsg}`);
      }
    } finally {
      if (isCurrent()) setIsLoadingStored(false);
    }
  }, []);

  // Fetch report on mount or when inspectionId prop changes
  useEffect(() => {
    if (inspectionId) void fetchStoredReport(inspectionId);
    else {
      requestVersion.current += 1;
      setReport(null);
      setError(null);
      setIsLoadingStored(false);
    }
  }, [inspectionId, fetchStoredReport]);

  // Handle Escape key to close modal
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && showConfirmModal) {
        setShowConfirmModal(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [showConfirmModal]);

  const handleConfirmLiveAnalysis = async () => {
    if (livePending.current) return;
    setShowConfirmModal(false);
    if (!activeInspectionId.trim()) return;
    const target = activeInspectionId.trim();
    const version = ++requestVersion.current;
    const isCurrent = () => version === requestVersion.current && activeId.current === target;
    livePending.current = true;

    setIsAnalyzingLive(true);
    setError(null);
    setIsLoadingStored(false);
    setReport(null);
    setLiveState({id:target, status:'RUNNING'});

    try {
      const res = await runAgentAnalysis(target);
      if (!isCurrent()) return;
      if (res.inspection_id !== target || res.analysis_status !== 'COMPLETED'
        || !['LIVE_AGENT_ANALYSIS', 'FAKE_TEST'].includes(res.provenance ?? '')) throw new Error('AGENT_RESPONSE_INVALID');
      setReport(res);
      setReportOrigin('LIVE');
      setLiveState({id:target, status:'COMPLETED'});
    } catch (err: any) {
      if (!isCurrent()) return;
      setLiveState({id:target, status:'FAILED'});
      const errCode = err?.data?.detail?.error_code || err?.message || 'UNKNOWN_ERROR';
      setError(agentFailureMessage(errCode, err?.status));
    } finally {
      livePending.current = false;
      setIsAnalyzingLive(false);
    }
  };

  return (
    <div className="panel-card mt-6 agent-panel-card" id="agent-diagnostic-panel">
      {/* Header */}
      <div className="panel-header">
        <div className="panel-title-area">
          <Bot size={16} className="text-indigo-400" />
          <h2 className="panel-title">AI Agent 근거 기반 이상 진단 (Gemini Diagnostic Agent)</h2>
        </div>

        <div className="flex items-center gap-2">
          <span className="phase-badge font-mono" data-agent-live-status={liveStatus}>{report?.provenance === 'FAKE_TEST' ? 'FAKE_TEST · LIVE 미검증' : liveAnalysisLabel(liveStatus)}</span>
          {report?.provenance === 'FAKE_TEST' ? <span>FAKE_TEST · 실제 Gemini 분석 아님</span> : report?.provenance === 'RECORDED_TEST_FIXTURE' ? (
            <span className="text-xs bg-amber-500/15 text-amber border border-amber-500/30 px-2.5 py-0.5 rounded-full font-mono font-medium">
              RECORDED TEST FIXTURE (검증된 근거)
            </span>
          ) : report?.provenance === 'LIVE_AGENT_ANALYSIS' ? (
            <span className="text-xs bg-indigo-500/15 text-indigo-300 border border-indigo-500/30 px-2.5 py-0.5 rounded-full font-mono font-medium">
              {reportOrigin === 'LIVE' ? 'LIVE ANALYSIS' : 'STORED LIVE REPORT'}
            </span>
          ) : report ? (
            <span className="text-xs bg-sky-500/15 text-sky-400 border border-sky-500/30 px-2.5 py-0.5 rounded-full font-mono font-medium">
              STORED REPORT
            </span>
          ) : (
            <span className="phase-badge deferred font-mono">NOT ANALYZED</span>
          )}
          {currentTarget === 'INSP-001391' && <span className="phase-badge font-mono">RECORDED TEST FIXTURE INPUT</span>}

          <div className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-slate-900 border border-slate-700/80 text-[11px] text-slate-300">
            <Shield size={12} className="text-emerald" />
            <span>판정 불변 가드레일</span>
          </div>
        </div>
      </div>

      <div className="panel-body space-y-4">
        {/* Top Control Bar: Target Inspection Selection & Action Buttons */}
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 bg-slate-900/80 border border-slate-800 p-3 rounded-xl">
          <div className="flex items-center gap-2 flex-1">
            <span className="text-xs font-semibold text-slate-300 whitespace-nowrap">
              진단 대상 ID:
            </span>
            <input
              type="text"
              value={activeInspectionId}
              readOnly={!!inspectionId}
              onChange={(e) => setActiveInspectionId(e.target.value)}
              placeholder="INSP-001396"
              className="bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 font-mono focus:border-indigo-400 focus:outline-none w-44"
            />
            <button
              type="button"
              onClick={() => fetchStoredReport(activeInspectionId)}
              disabled={isLoadingStored || isAnalyzingLive || !activeInspectionId.trim()}
              className="btn btn-outline text-xs px-3 py-1.5 flex items-center gap-1.5"
              title="사전 저장된 Gemini 진단 보고서 즉시 조회 (API 호출 0회)"
            >
              {isLoadingStored ? <div className="spinner" /> : <Search size={13} />}
              <span>기존 보고서 조회</span>
            </button>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setShowConfirmModal(true)}
              disabled={isAnalyzingLive || !!report || !activeInspectionId.trim()}
              className="btn text-xs px-3.5 py-1.5 flex items-center gap-1.5 bg-gradient-to-r from-indigo-600 to-indigo-500 hover:from-indigo-500 hover:to-indigo-400 text-white font-medium rounded-lg shadow-lg shadow-indigo-500/20"
              title="현재 검사에 대해 Gemini AI Function Calling 진단을 새로 실행합니다"
            >
              {isAnalyzingLive ? (
                <>
                  <div className="spinner" />
                  <span>진단 분석 중...</span>
                </>
              ) : (
                <>
                  <Sparkles size={13} />
                  <span>Gemini AI 진단 실행</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Live Analysis Progress Notice */}
        {isAnalyzingLive && (
          <div className="p-4 rounded-xl bg-indigo-950/30 border border-indigo-500/30 flex items-center gap-3">
            <div className="spinner text-indigo-400" style={{ width: 20, height: 20 }} />
            <div className="text-xs text-indigo-200">
              <span className="font-semibold block">Gemini 3.8 Flash가 검사 근거를 수집 및 분석 중입니다...</span>
              <span className="text-indigo-300/80 font-mono text-[11px]">
                서버 도구 호출(Inspection Result, Image Quality, Logs) 및 엄격한 증거 1:1 검증 진행 중 (약 20~30초 소요 가능)
              </span>
            </div>
          </div>
        )}

        {/* Error notification */}
        {error && !isAnalyzingLive && (
          <div className="alert-banner alert-warning">
            <AlertTriangle size={15} />
            <span className="text-xs">{error}</span>
          </div>
        )}

        {/* 1. Overall Summary Card */}
        {report?.overall_summary && (
          <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-bold uppercase tracking-wider text-indigo-400 flex items-center gap-1.5">
                <FileText size={13} />
                <span>진단 총평 (Overall Summary)</span>
              </span>
              <span className="text-[10px] font-mono text-slate-500">
                Analysis ID: {report.analysis_id || 'ANALYSIS-MOCK'}
              </span>
            </div>
            <p className="text-sm font-medium text-slate-100 leading-relaxed bg-slate-950/60 p-3 rounded-lg border border-slate-800/80">
              {report.overall_summary}
            </p>
          </div>
        )}

        {/* 2. Observed Facts & Evidence Table */}
        {report && report.observed_facts && report.observed_facts.length > 0 && (
          <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-3.5 space-y-2.5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-slate-300 flex items-center gap-1.5">
                <ListFilter size={14} className="text-cyan" />
                <span>관측 근거 (Observed Facts & Evidence)</span>
              </span>
              <span className="text-[11px] font-mono text-cyan bg-cyan-500/10 border border-cyan-500/20 px-2 py-0.5 rounded">
                총 {report.observed_facts.length}개 사실 수집됨
              </span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead>
                  <tr className="border-b border-slate-800 text-slate-500 text-[10px] uppercase">
                    <th className="py-2 px-2.5">Fact ID</th>
                    <th className="py-2 px-2.5">Evidence ID</th>
                    <th className="py-2 px-2.5">Source Tool</th>
                    <th className="py-2 px-2.5">Field Pointer</th>
                    <th className="py-2 px-2.5">Observed Value</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {report.observed_facts.map((fact) => (
                    <tr key={fact.fact_id} className="hover:bg-slate-800/40">
                      <td className="py-2 px-2.5 font-bold text-indigo-300">{fact.fact_id}</td>
                      <td className="py-2 px-2.5 text-cyan">{fact.evidence_id}</td>
                      <td className="py-2 px-2.5 text-slate-300">{fact.source_tool}</td>
                      <td className="py-2 px-2.5 text-slate-400">{fact.source_field}</td>
                      <td className="py-2 px-2.5 font-semibold text-emerald">
                        {String(fact.observed_value)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* 3. Hypotheses & Recommended Checks Grid */}
        {report && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {/* Possible Causes / Hypotheses */}
            <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-3.5 space-y-2">
              <span className="text-xs font-bold text-slate-300 flex items-center gap-1.5">
                <AlertTriangle size={13} className="text-amber" />
                <span>추정 원인 가설 (Possible Causes)</span>
              </span>
              {report.possible_causes && report.possible_causes.length > 0 ? (
                <div className="space-y-2">
                  {report.possible_causes.map((cause, idx) => (
                    <div key={idx} className="p-2.5 rounded-lg bg-slate-950 border border-slate-800 text-xs">
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-bold text-amber">{cause.cause_code}</span>
                        <div className="flex gap-1">
                          {cause.evidence_refs.map((ref) => (
                            <span key={ref} className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-indigo-950 text-indigo-300 border border-indigo-800">
                              {ref}
                            </span>
                          ))}
                        </div>
                      </div>
                      <p className="text-slate-300 text-[11px] leading-relaxed">{cause.statement}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-xs text-slate-500 py-2">
                  검사 결과가 정상이거나 특이 고장 가설이 식별되지 않았습니다.
                </div>
              )}
            </div>

            {/* Recommended Checks */}
            <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-3.5 space-y-2">
              <span className="text-xs font-bold text-slate-300 flex items-center gap-1.5">
                <CheckCircle2 size={13} className="text-emerald" />
                <span>권고 조치 사항 (Action Plan)</span>
              </span>
              {report.recommended_checks && report.recommended_checks.length > 0 ? (
                <div className="space-y-2">
                  {report.recommended_checks.map((chk, idx) => (
                    <div key={idx} className="p-2.5 rounded-lg bg-slate-950 border border-slate-800 text-xs">
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-bold text-emerald">{chk.check_code}</span>
                        <div className="flex gap-1">
                          {chk.evidence_refs.map((ref) => (
                            <span key={ref} className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-indigo-950 text-indigo-300 border border-indigo-800">
                              {ref}
                            </span>
                          ))}
                        </div>
                      </div>
                      <p className="text-slate-300 text-[11px] leading-relaxed">{chk.instruction}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-xs text-slate-500 py-2">
                  특이 권고 사항이 없습니다.
                </div>
              )}
            </div>
          </div>
        )}

        {/* 4. Limitations Disclaimer Strip */}
        {report && report.limitations && report.limitations.length > 0 && (
          <div className="p-3 rounded-lg bg-slate-900/50 border border-slate-800 text-[11px] text-slate-400 space-y-1">
            <span className="font-semibold text-slate-300 block">진단 한계 및 법적 고지 (Limitations):</span>
            <ul className="list-disc list-inside space-y-0.5 text-slate-400">
              {report.limitations.map((lim, idx) => (
                <li key={idx}>{lim}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Empty State when no report */}
        {!report && !isLoadingStored && !isAnalyzingLive && (
          <div className="p-8 text-center bg-slate-900/40 border border-dashed border-slate-800 rounded-xl space-y-2">
            <Bot size={28} className="mx-auto text-slate-600" />
            <div className="text-xs font-medium text-slate-400">
              해당 검사에 대한 진단 보고서가 아직 로드되지 않았습니다.
            </div>
            <p className="text-[11px] text-slate-500 max-w-sm mx-auto">
              상단의 <strong className="text-cyan">[기존 보고서 조회]</strong>를 눌러 검증된 T01/T03
              사전 저장 보고서를 확인하거나, <strong className="text-indigo-400">[Gemini AI 진단 실행]</strong>을 통해 새로 분석하세요.
            </p>
          </div>
        )}
      </div>

      {/* Confirmation Modal for Live Gemini API Call */}
      {showConfirmModal && (
        <div
          className="modal-overlay"
          role="dialog"
          aria-modal="true"
          aria-labelledby="gemini-confirm-modal-title"
          onClick={(e) => {
            if (e.target === e.currentTarget) {
              setShowConfirmModal(false);
            }
          }}
        >
          <div className="modal-dialog">
            <div className="modal-header">
              <div className="modal-title-area">
                <div className="modal-icon-badge">
                  <Sparkles size={18} />
                </div>
                <div>
                  <h3 id="gemini-confirm-modal-title" className="modal-title">
                    Gemini AI 자율 진단 실행 확인
                  </h3>
                  <span className="text-[11px] text-slate-400 font-mono">
                    Target: {activeInspectionId}
                  </span>
                </div>
              </div>
              <button
                type="button"
                className="btn-tool text-slate-400 hover:text-white"
                onClick={() => setShowConfirmModal(false)}
                title="닫기 (Esc)"
              >
                ✕
              </button>
            </div>

            <div className="modal-body">
              <div className="modal-info-box">
                <p>
                  현재 검사 <strong className="text-cyan font-mono">[{activeInspectionId}]</strong>에 대해
                  Google Gemini AI Function Calling Agent를 실행합니다.
                </p>
                <p className="text-slate-400 text-xs mt-2">
                  Gemini는 서버 도구(<span className="font-mono text-slate-300">get_inspection_result, analyze_image_quality, get_execution_logs</span>)를 자율 호출하여 근거를 수집한 후 종합 진단 리포트를 작성합니다.
                </p>
              </div>

              <div className="modal-warning-box">
                <AlertTriangle size={18} className="shrink-0 mt-0.5" />
                <div>
                  <strong className="block font-semibold">실제 외부 AI API 호출 발생 안내</strong>
                  <span>
                    실제 Gemini API 호출이 발생하며, 네트워크 상태 및 LLM 추론에 따라 약 20~30초의 소요 시간이 발생할 수 있습니다. 계속 진행하시겠습니까?
                  </span>
                </div>
              </div>
            </div>

            <div className="modal-footer">
              <button
                type="button"
                onClick={() => setShowConfirmModal(false)}
                className="btn btn-outline text-xs px-4 py-2"
              >
                취소 (돌아가기)
              </button>
              <button
                type="button"
                disabled={isAnalyzingLive}
                onClick={handleConfirmLiveAnalysis}
                className="btn text-xs px-5 py-2 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold rounded-lg shadow-lg shadow-indigo-500/25"
              >
                {isAnalyzingLive ? '진단 시작 중...' : '확인 후 AI 진단 실행'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

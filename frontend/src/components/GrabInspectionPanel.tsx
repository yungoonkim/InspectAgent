import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { CropData } from '../types/roi';
import type { InspectionResponse } from '../types/inspection';
import type { ManualOutcome, ReinspectionGroup } from '../types/reinspection';
import { createGrabInspection, getCaptureReinspectionGroup, getInspection, getReinspectionGroup, saveManualReview } from '../api/inspection';
import { cropIdentity, isGrabInspectionMatching, GRAB_LIMITATION } from '../utils/grabInspectionState';
import { inspectionQualitySummary } from '../utils/inspectionQualitySummary';
import { canUseCapture, grabInspectionDisabled, inspectionProgress, isJudgeAssisted, MANUAL_DEFAULT } from '../utils/reinspectionState';
import { getCaptureMetadata } from '../api/video';
import {
  canPrepareNewProduct, clearWorkflowHints, GROUP_HINT_KEY, PENDING_CAPTURE_HINT_KEY,
  prepareNewProductCapture, restoreCurrentCaptureWorkflow, recoveryProblem, type RecoveryProblem
} from '../utils/reinspectionRecovery';

interface Props {
  crop: CropData | null;
  enabled: boolean;
  manualMode?: boolean;
  currentInspection?: InspectionResponse | null;
  onSelectionStart: () => number;
  onInspectionChange: (inspection: InspectionResponse, version?: number) => void;
  onGroupChange?: (group: ReinspectionGroup | null) => void;
  onRequestJudge?: () => void;
}

const storageKey = GROUP_HINT_KEY;
const pendingKey = PENDING_CAPTURE_HINT_KEY;
const requestId = () => crypto.randomUUID().replaceAll('-', '');

export function GrabInspectionPanel({ crop, enabled, manualMode = enabled, currentInspection = null, onSelectionStart, onInspectionChange, onGroupChange, onRequestJudge }: Props) {
  const [productId, setProductId] = useState('ABCD1541');
  const [group, setGroup] = useState<ReinspectionGroup | null>(null);
  useEffect(() => { onGroupChange?.(group); }, [group, onGroupChange]);
  const [restoring, setRestoring] = useState(true);
  const [blocked, setBlocked] = useState(false);
  const [lookupProblem, setLookupProblem] = useState<RecoveryProblem | null>(null);
  const [sameProduct, setSameProduct] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [outcome, setOutcome] = useState<{ key: string; message: string; completed: boolean } | null>(null);
  const [manualResult, setManualResult] = useState<ManualOutcome>(MANUAL_DEFAULT);
  const [operator, setOperator] = useState('');
  const [reason, setReason] = useState('');
  const busyRef = useRef(false);
  const epochRef = useRef(0);
  const mounted = useRef(true);
  const currentKey = cropIdentity(crop);
  const currentKeyRef = useRef(currentKey);
  useLayoutEffect(() => { currentKeyRef.current = currentKey; epochRef.current++; }, [currentKey]);
  const visibleOutcome = outcome?.key === currentKey ? outcome : null;
  const matchingInspection = currentInspection && crop && isGrabInspectionMatching(currentInspection, crop)
    ? currentInspection : null;
  const qualitySummary = inspectionQualitySummary(matchingInspection);
  const captureAllowed = canUseCapture(group, crop?.captureId, sameProduct);
  const inspectDisabled = grabInspectionDisabled({
    enabled, hasCrop: !!crop, busy, restoring, blocked,
    captureAllowed, completed: !!visibleOutcome?.completed, productId
  });

  useEffect(() => {
    mounted.current = true;
    let active = true;
    void (async () => {
      let target = '저장 그룹';
      try {
        const identifier = localStorage.getItem(storageKey);
        const pending = localStorage.getItem(pendingKey);
        target = pending ? `이전 대기 Capture ${pending}` : `저장 그룹 ${identifier ?? '없음'}`;
        if (identifier || pending) {
          const restored = pending ? await getCaptureReinspectionGroup(pending) : await getReinspectionGroup(identifier!);
          if (active) {
            localStorage.setItem(storageKey, restored.group_id);
            localStorage.removeItem(pendingKey);
            setGroup(restored); setProductId(restored.product_id); setBlocked(false); setLookupProblem(null);
          }
        }
      } catch (error) {
        if (active) {
          const problem = recoveryProblem(error);
          setBlocked(true); setLookupProblem(problem); setMessage(`${target} 복원 실패: ${problem.message} 새 Grab이 있다면 [저장 그룹 새로 조회]로 현재 Capture부터 확인하세요.`);
        }
      } finally {
        if (active) setRestoring(false);
      }
    })();
    return () => { active = false; mounted.current = false; };
  }, []);

  const remember = (value: ReinspectionGroup) => {
    localStorage.setItem(storageKey, value.group_id);
    localStorage.removeItem(pendingKey);
    setGroup(value);
  };

  const inspect = async () => {
    if (!crop || busyRef.current || inspectDisabled) return;
    busyRef.current = true;
    setBusy(true);
    setOutcome(null);
    setMessage('');
    const version = onSelectionStart();
    const key = currentKey;
    try {
      localStorage.setItem(pendingKey, crop.captureId);
      const result = await createGrabInspection(crop, productId,
        { group, sameProductConfirmed: sameProduct, requestId: requestId() });
      if (!isGrabInspectionMatching(result, crop)) throw new Error('GRAB_RESULT_SOURCE_MISMATCH');
      const identifier = result.metrics?.reinspection?.group_id;
      if (!identifier) throw new Error('REINSPECTION_GROUP_MISSING');
      localStorage.setItem(storageKey, identifier);
      const updated = await getReinspectionGroup(identifier);
      if (!mounted.current) return;
      remember(updated);
      setSameProduct(false);
      if (currentKeyRef.current !== key) return;
      onInspectionChange({ ...result, provenance: 'LIVEVIEW_GRAB' }, version);
      setOutcome({ key, completed: true, message: `${result.inspection_id} · ${result.final_result} · ${result.final_reason_code} · ${result.image_quality_status} · Score ${result.anomaly_score?.toFixed(4) ?? '—'} / ${result.decision_threshold ?? '—'}${result.metrics?.anomaly_map_available === false ? ' · Heatmap 미생성' : ''}` });
    } catch (error) {
      if (mounted.current) {
        setBlocked(true);
        setLookupProblem(null);
        setMessage(`Grab 검사 실패: ${error instanceof Error ? error.message : 'UNKNOWN_ERROR'} — 결과 조회 전 재실행하지 않습니다.`);
      }
    } finally {
      busyRef.current = false;
      if (mounted.current) setBusy(false);
    }
  };

  const refresh = async () => {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setBlocked(true);
    const key = currentKey;
    try {
      const identifier = group?.group_id ?? localStorage.getItem(storageKey);
      const pending = localStorage.getItem(pendingKey);
      const recovery = crop ? await restoreCurrentCaptureWorkflow(crop, group,
        { groupId: identifier, pendingCaptureId: pending },
        { capture: getCaptureMetadata, group: getCaptureReinspectionGroup, savedGroup: getReinspectionGroup }) : null;
      const restored = recovery ? recovery.group : pending ? await getCaptureReinspectionGroup(pending)
        : identifier ? await getReinspectionGroup(identifier) : null;
      if (!mounted.current) return;
      if (currentKeyRef.current !== key) {
        setLookupProblem(null); setMessage('Capture가 변경되어 조회 결과를 적용하지 않았습니다. 저장 그룹을 다시 조회하세요.'); return;
      }
      if (recovery?.needsNewProductConfirmation) {
        const problem: RecoveryProblem = { kind: 'GROUP_NOT_FOUND',
          message: `현재 Capture ${crop!.captureId}의 소유권·출처와 미사용 상태는 확인했습니다. 이전 그룹/대기 Capture는 복원되지 않았습니다. 같은 제품이면 기존 그룹 접근을 복구하고, 실제 새 제품이면 [새 제품 검사 시작]에서 명시적으로 확인하세요. 기존 기록과 검사 횟수는 초기화하지 않습니다.` };
        setLookupProblem(problem); setMessage(problem.message);
        return;
      }
      if (restored) { remember(restored); setProductId(restored.product_id); }
      else setGroup(null);
      setBlocked(false);
      setLookupProblem(null);
      setMessage('저장 그룹 조회 완료. 신규 검사는 실행하지 않았습니다.');
    } catch (error) {
      if (mounted.current && currentKeyRef.current === key) {
        const problem = recoveryProblem(error);
        setLookupProblem(problem);
        setMessage(error instanceof Error && error.message === 'PENDING_CAPTURE_RESULT_UNRESOLVED'
          ? '현재 Capture의 이전 검사 완료 여부가 미확정입니다. 재실행하지 말고 저장 그룹을 다시 조회하세요.'
          : `현재 Capture ${crop?.captureId ?? '없음'} 상태 조회 실패: ${problem.message}`);
      }
    }
    finally { busyRef.current = false; if (mounted.current) setBusy(false); }
  };

  const startNewProduct = async () => {
    if (!crop || !manualMode || busyRef.current || restoring || !canPrepareNewProduct(blocked, lookupProblem)) return;
    if (!window.confirm('새 제품의 최초 검사를 시작합니까? 기존 그룹·검사·수동 확인 기록과 레거시 정책은 그대로 보존됩니다. 현재 Capture를 서버에서 확인하며 검사는 아직 실행하지 않습니다.')) return;
    const key = currentKey;
    busyRef.current = true;
    setBusy(true);
    setBlocked(true);
    try {
      const restored = await prepareNewProductCapture(crop, true, { capture: getCaptureMetadata, group: getCaptureReinspectionGroup });
      if (!mounted.current) return;
      if (currentKeyRef.current !== key) {
        setLookupProblem(null); setMessage('Capture가 변경되어 이전 확인 결과를 적용하지 않았습니다. 현재 Capture를 다시 확인하세요.'); return;
      }
      if (restored) {
        remember(restored); setProductId(restored.product_id);
        setMessage('현재 Capture에 연결된 기존 그룹을 복원했습니다. 같은 Capture는 다시 검사하지 않습니다.');
      } else {
        clearWorkflowHints(localStorage);
        setGroup(null); setOutcome(null);
        setMessage('새 제품 전환 확인 완료 · 현재 Capture의 접근 권한·출처와 미사용 상태를 확인했습니다. [Grab 이미지 검사]로 최초 검사를 시작하세요. 기존 서버 기록은 보존됩니다.');
        epochRef.current++; onSelectionStart();
      }
      setSameProduct(false); setBlocked(false); setLookupProblem(null);
    } catch (error) {
      if (mounted.current) { const problem = recoveryProblem(error); setLookupProblem(problem); setMessage(problem.message); }
    } finally { busyRef.current = false; if (mounted.current) setBusy(false); }
  };

  const review = async () => {
    if (!manualMode || !group || busyRef.current || !operator.trim() || !reason.trim()) return;
    busyRef.current = true;
    setBusy(true);
    try {
      remember(await saveManualReview(group, manualResult, operator, reason, requestId()));
      setMessage('개발용 수동 확인 저장 완료 — 원본 PatchCore 판정은 변경되지 않았습니다.');
      setManualResult('HOLD');
    } catch (error) { setMessage(String(error)); }
    finally { busyRef.current = false; setBusy(false); }
  };

  const viewAttempt = async (identifier: string) => {
    if (busyRef.current) return;
    const epoch = ++epochRef.current;
    const version = onSelectionStart();
    try {
      const result = await getInspection(identifier);
      const expected = group && [...group.attempts, ...group.failed_attempts].find(attempt => attempt.inspection_id === identifier);
      if (!expected || result.metrics?.input_provenance?.capture_id !== expected.input_provenance.capture_id
        || result.metrics?.reinspection?.group_id !== group?.group_id) throw new Error('GRAB_HISTORY_SOURCE_MISMATCH');
      if (mounted.current && epoch === epochRef.current) {
        onInspectionChange({ ...result, provenance: 'STORED_RESULT' }, version);
      }
    } catch (error) { if (mounted.current && epoch === epochRef.current) setMessage(String(error)); }
  };

  return <section className="panel-card grab-inspection-panel" aria-label="Grab 이미지 검사">
    <div className="panel-header">
      <h2 className="panel-title">MANUAL · Grab 이미지 검사</h2>
      <span className="panel-meta">EXPERIMENTAL</span>
    </div>
    <div className="panel-body">
      <div className="grab-panel-source">SOURCE: LIVEVIEW_GRAB{!crop && ' · ROI Crop 대기'}</div>
      {crop && <details className="grab-panel-details">
        <summary>상세 정보 · 현재 Grab Crop</summary>
        <div>Capture ID: {crop.captureId}</div>
        <div>{crop.videoId} · Frame {crop.frameIndex}</div>
        <div>ROI ({crop.roi.x}, {crop.roi.y}, {crop.width}, {crop.height}) · {crop.width}×{crop.height}</div>
      </details>}
      <p className="grab-panel-note grab-panel-warning">{GRAB_LIMITATION}</p>
      <label className="grab-panel-field">제품 ID
        <input aria-label="Grab 제품 ID" value={productId} disabled={busy || !!group || restoring} onChange={event => setProductId(event.target.value)} />
      </label>
      <div role="status" className="grab-panel-status">{inspectionProgress({ group, restoring, blocked, hasCrop: !!crop, ready: !inspectDisabled })}</div>
      {!isJudgeAssisted(group) && group?.status === 'RETRY_ALLOWED' && <label className="grab-panel-checkbox">
        <input aria-label="동일 제품 재검사 확인" type="checkbox" checked={sameProduct} onChange={event => setSameProduct(event.target.checked)} disabled={busy} />
        <span>동일한 실제 제품의 재검사임을 확인합니다. 기존 ROI를 유지하고 다른 영상 프레임을 새로 Grab하세요. 같은 Crop의 Gemini 2차 분석은 재검사 횟수에 포함하지 않습니다.</span>
      </label>}
      <button type="button" className="btn btn-primary" onClick={() => void inspect()} disabled={inspectDisabled}>
        {busy ? 'Grab 검사 중...' : visibleOutcome?.completed ? '현재 Crop 검사 완료' : 'Grab 이미지 검사'}
      </button>
      <div className="grab-panel-actions">
        <button type="button" className="btn btn-outline" disabled={busy || restoring} onClick={() => void refresh()}>저장 그룹 새로 조회</button>
        <button type="button" className="btn btn-outline" disabled={!manualMode || !crop || busy || restoring || !canPrepareNewProduct(blocked, lookupProblem)} onClick={() => void startNewProduct()}>새 제품 검사 시작</button>
      </div>
      {visibleOutcome && <div role="status" className="grab-panel-status">{visibleOutcome.message}</div>}
      {matchingInspection && <div aria-label="현재 Grab 검사 상세" className="grab-panel-result">
        <div className="grab-panel-result-heading">검사 ID: <strong>{matchingInspection.inspection_id}</strong></div>
        <div className="grab-panel-metrics">
          <div className="meta-pill" data-verdict={matchingInspection.final_result}>
            <span className="meta-pill-label">서버 최종 판정:</span>
            <span className="meta-pill-value"><strong>{matchingInspection.final_result ?? '—'}</strong></span>
            <span className="grab-panel-caption">{matchingInspection.final_reason_code ?? '—'}</span>
          </div>
          <div className="meta-pill">
            <span className="meta-pill-label">PatchCore 모델 판정:</span>
            <span
              className="meta-pill-value"
              data-verdict={qualitySummary.modelVerdict}
            >
              <strong>{qualitySummary.modelVerdict}</strong>
            </span>
            <span className="grab-panel-caption">Score {matchingInspection.anomaly_score?.toFixed(4) ?? '—'} / {matchingInspection.decision_threshold ?? '—'}</span>
          </div>
          <div className="meta-pill">
            <span className="meta-pill-label">평균 GV (ROI 전체):</span>
            <span className="meta-pill-value"><strong>{qualitySummary.meanLabel}</strong></span>
            <span className="grab-panel-caption">밝기 기준: {qualitySummary.criteria}</span>
          </div>
          <div className="meta-pill">
            <span className="meta-pill-label">영상 품질:</span>
            <span className="meta-pill-value"><strong>{matchingInspection.image_quality_status}</strong></span>
            <span className="grab-panel-caption">품질 사유: {qualitySummary.reason}</span>
          </div>
        </div>
        {matchingInspection.final_result === 'REINSPECT' && matchingInspection.final_reason_code === 'IMAGE_QUALITY_WARNING'
          && <p className="grab-panel-note grab-panel-warning">영상 품질 경고가 모델 OK/NG보다 우선 적용되었습니다. 원본 모델 판정은 변경되지 않습니다.</p>}
        {matchingInspection.final_result === 'REINSPECT' && onRequestJudge && <>
          <p className="grab-panel-note">2차 Gemini Judge는 선택 사항입니다. 비활성·실패·미실행이어도 신규 정책의 3차 작업자 확인을 진행할 수 있습니다.</p>
          <button type="button" className="btn btn-outline" disabled={busy} onClick={onRequestJudge}>2차 Gemini Judge 보기 (선택)</button>
        </>}
      </div>}
      {message && <div role="status" className="grab-panel-note grab-panel-warning">{message}</div>}
      {group && <div className="grab-panel-history">
        <h3>검사 이력</h3>
        <details className="grab-panel-details"><summary>상세 정보 · 검사 그룹</summary>{group.group_id}</details>
        <ul>{[...group.attempts, ...group.failed_attempts].map(attempt => <li key={attempt.inspection_id} className="grab-panel-attempt">
          <div><strong>{attempt.attempt_number ?? '실패(횟수 제외)'} · {attempt.inspection_id}</strong></div>
          <div>Model {attempt.result} / Server {attempt.final_result}</div>
          <div className="grab-panel-caption">{attempt.image_quality_status} · {attempt.anomaly_score ?? '—'} / {attempt.decision_threshold ?? '—'} · {attempt.final_reason_code}</div>
          <details className="grab-panel-details"><summary>상세 정보 · 검사 입력</summary>{attempt.input_provenance.capture_id} · Frame {attempt.input_provenance.frame_index}</details>
          <button type="button" className="btn btn-outline" disabled={busy} onClick={() => void viewAttempt(attempt.inspection_id)}>이미지/Heatmap 조회</button>
        </li>)}</ul>
      </div>}
      {group?.status === 'MANUAL_REVIEW_REQUIRED' && <fieldset className="grab-panel-manual" disabled={busy || !manualMode}>
        <legend>{isJudgeAssisted(group) ? '3차 작업자 최종 확인 · Gemini 실행 불필수' : '레거시 재검사 한도 도달 · 작업자 확인 필요'}</legend>
        <p className="grab-panel-caption">대상 검사: {group.current_inspection_id} · 서버 원판정 REINSPECT는 유지됩니다.</p>
        <p className="grab-panel-caption">개발용 자기신고 수동 확인입니다. 인증된 공장 품질 승인이나 설비 제어가 아닙니다.</p>
        <label className="grab-panel-field">수동 결과 <select aria-label="수동 결과" value={manualResult} onChange={event => setManualResult(event.target.value as ManualOutcome)}><option value="HOLD">HOLD</option><option value="MANUAL_OK">MANUAL_OK</option><option value="MANUAL_NG">MANUAL_NG</option></select></label>
        <label className="grab-panel-field">작업자 표시명 <input aria-label="작업자 표시명" maxLength={64} value={operator} onChange={event => setOperator(event.target.value)} /></label>
        <label className="grab-panel-field">수동 판단 사유 <textarea aria-label="수동 판단 사유" maxLength={1000} value={reason} onChange={event => setReason(event.target.value)} /></label>
        <button type="button" className="btn btn-outline" disabled={!operator.trim() || !reason.trim()} onClick={() => void review()}>수동 확인 저장</button>
      </fieldset>}
      {group?.manual_reviews.map(entry => <div key={entry.review_id} className="grab-panel-note">개발용 수동 확인 · {entry.result} · {entry.operator_id} · {entry.timestamp} · {entry.reason} · 원본 판정 불변</div>)}
    </div>
  </section>;
}

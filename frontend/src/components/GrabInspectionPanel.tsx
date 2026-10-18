import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { CropData } from '../types/roi';
import type { InspectionResponse } from '../types/inspection';
import type { ManualOutcome, ReinspectionGroup } from '../types/reinspection';
import { createGrabInspection, getCaptureReinspectionGroup, getInspection, getReinspectionGroup, saveManualReview } from '../api/inspection';
import { cropIdentity, isGrabInspectionMatching, GRAB_LIMITATION } from '../utils/grabInspectionState';
import { canUseCapture, MANUAL_DEFAULT } from '../utils/reinspectionState';

interface Props {
  crop: CropData | null;
  enabled: boolean;
  manualMode?: boolean;
  onSelectionStart: () => number;
  onInspectionChange: (inspection: InspectionResponse, version?: number) => void;
}

const storageKey = 'visioninsight.manual-reinspection-group';
const pendingKey = 'visioninsight.manual-reinspection-pending-capture';
const requestId = () => crypto.randomUUID().replaceAll('-', '');

export function GrabInspectionPanel({ crop, enabled, manualMode = enabled, onSelectionStart, onInspectionChange }: Props) {
  const [productId, setProductId] = useState('ABCD1541');
  const [group, setGroup] = useState<ReinspectionGroup | null>(null);
  const [restoring, setRestoring] = useState(true);
  const [blocked, setBlocked] = useState(false);
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
  const captureAllowed = canUseCapture(group, crop?.captureId, sameProduct);

  useEffect(() => {
    mounted.current = true;
    let active = true;
    void (async () => {
      try {
        const identifier = localStorage.getItem(storageKey);
        const pending = localStorage.getItem(pendingKey);
        if (identifier || pending) {
          const restored = pending ? await getCaptureReinspectionGroup(pending) : await getReinspectionGroup(identifier!);
          localStorage.setItem(storageKey, restored.group_id);
          localStorage.removeItem(pendingKey);
          if (active) { setGroup(restored); setProductId(restored.product_id); }
        }
      } catch {
        if (active) { setBlocked(true); setMessage('그룹 복원 실패: 세션 만료 또는 서버 오류. 자동으로 새 그룹을 만들지 않습니다.'); }
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
    if (!crop || !enabled || busyRef.current || restoring || blocked || !captureAllowed || visibleOutcome?.completed) return;
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
    try {
      const identifier = group?.group_id ?? localStorage.getItem(storageKey);
      const pending = localStorage.getItem(pendingKey);
      if (!identifier && !pending) throw new Error('서버에 확정된 그룹 ID가 없습니다.');
      remember(pending ? await getCaptureReinspectionGroup(pending) : await getReinspectionGroup(identifier!));
      setBlocked(false);
      setMessage('저장 그룹 조회 완료. 신규 검사는 실행하지 않았습니다.');
    } catch (error) { setMessage(String(error)); }
    finally { busyRef.current = false; setBusy(false); }
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

  return <section className="panel-card p-3 space-y-2" aria-label="Grab 이미지 검사">
    <h2 className="text-sm font-semibold text-cyan">MANUAL · Grab 이미지 검사</h2>
    <div className="text-xs font-mono break-all">SOURCE: LIVEVIEW_GRAB · {crop?.captureId ?? 'ROI Crop 대기'}</div>
    {crop && <div className="text-xs font-mono">{crop.videoId} · Frame {crop.frameIndex} · ROI ({crop.roi.x}, {crop.roi.y}, {crop.width}, {crop.height}) · {crop.width}×{crop.height}</div>}
    <p className="text-xs text-amber-300">{GRAB_LIMITATION}</p>
    <label className="text-xs">제품 ID <input aria-label="Grab 제품 ID" value={productId} disabled={busy || !!group || restoring} onChange={event => setProductId(event.target.value)} className="bg-slate-900 border rounded px-2" /></label>
    <div role="status" className="text-xs break-all">{group ? `${group.group_id} · 검사 ${group.attempt_count} / 3 · 남은 ${group.remaining_attempts}회 · ${group.status}` : '최초 검사 1 / 3 준비'}</div>
    {group?.status === 'RETRY_ALLOWED' && <label className="text-xs block"><input aria-label="동일 제품 재검사 확인" type="checkbox" checked={sameProduct} onChange={event => setSameProduct(event.target.checked)} disabled={busy} /> 동일한 실제 제품의 재검사임을 확인합니다. 기존 ROI를 유지하고 다른 영상 프레임을 새로 Grab하세요. 같은 Crop의 Gemini 2차 분석은 재검사 횟수에 포함하지 않습니다.</label>}
    <button type="button" className="btn btn-primary" onClick={() => void inspect()} disabled={!enabled || !crop || busy || restoring || blocked || !captureAllowed || !!visibleOutcome?.completed}>
      {busy ? 'Grab 검사 중...' : visibleOutcome?.completed ? '현재 Crop 검사 완료' : 'Grab 이미지 검사'}
    </button>
    <button type="button" className="btn" disabled={busy || restoring} onClick={() => void refresh()}>저장 그룹 새로 조회</button>
    <button type="button" className="btn" disabled={!manualMode || busy || restoring} onClick={() => {
      epochRef.current++; localStorage.removeItem(storageKey); localStorage.removeItem(pendingKey); setGroup(null); setBlocked(false); setSameProduct(false); setOutcome(null); setMessage('새 제품 그룹입니다. 이전 Capture를 재사용할 수 없습니다.'); onSelectionStart();
    }}>새 제품 검사 시작</button>
    {visibleOutcome && <div role="status" className="text-xs break-all">{visibleOutcome.message}</div>}
    {message && <div role="status" className="text-xs text-amber-300">{message}</div>}
    {group && <ul className="text-xs space-y-2">{[...group.attempts, ...group.failed_attempts].map(attempt => <li key={attempt.inspection_id} className="break-all">
      {attempt.attempt_number ?? '실패(횟수 제외)'} · {attempt.inspection_id} · {attempt.input_provenance.capture_id} · Frame {attempt.input_provenance.frame_index} · Model {attempt.result} / Server {attempt.final_result} · {attempt.image_quality_status} · {attempt.anomaly_score ?? '—'} / {attempt.decision_threshold ?? '—'} · {attempt.final_reason_code}
      <button type="button" className="btn" disabled={busy} onClick={() => void viewAttempt(attempt.inspection_id)}>이미지/Heatmap 조회</button>
    </li>)}</ul>}
    {group?.status === 'MANUAL_REVIEW_REQUIRED' && <fieldset className="border border-amber-700 p-2 text-xs space-y-2" disabled={busy || !manualMode}>
      <legend>자동 재검사 한도 도달 · 작업자 확인 필요</legend>
      <p>개발용 자기신고 수동 확인입니다. 인증된 공장 품질 승인이나 설비 제어가 아닙니다.</p>
      <label>수동 결과 <select aria-label="수동 결과" value={manualResult} onChange={event => setManualResult(event.target.value as ManualOutcome)}><option value="HOLD">HOLD</option><option value="MANUAL_OK">MANUAL_OK</option><option value="MANUAL_NG">MANUAL_NG</option></select></label>
      <label className="block">작업자 표시명 <input aria-label="작업자 표시명" maxLength={64} value={operator} onChange={event => setOperator(event.target.value)} /></label>
      <label className="block">수동 판단 사유 <textarea aria-label="수동 판단 사유" maxLength={1000} value={reason} onChange={event => setReason(event.target.value)} /></label>
      <button type="button" className="btn" disabled={!operator.trim() || !reason.trim()} onClick={() => void review()}>수동 확인 저장</button>
    </fieldset>}
    {group?.manual_reviews.map(entry => <div key={entry.review_id} className="text-xs break-all">개발용 수동 확인 · {entry.result} · {entry.operator_id} · {entry.timestamp} · {entry.reason} · 원본 판정 불변</div>)}
  </section>;
}

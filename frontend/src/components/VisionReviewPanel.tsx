import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { InspectionResponse } from '../types/inspection';
import type { VisionReview, VisionReviewResponse } from '../types/visionReview';
import type { ReinspectionGroup } from '../types/reinspection';
import { createVisionReview, getVisionReview } from '../api/visionReview';
import { getInspection } from '../api/inspection';
import { canRequestVisionReview, judgeOutcome, manualReviewLabel, matchesVisionInput, visionInputKey } from '../utils/visionReviewState';

export function VisionReviewPanel({ inspection, reinspectionGroup = null, onRequestManualReview }: {
  inspection: InspectionResponse | null; reinspectionGroup?: ReinspectionGroup | null;
  onRequestManualReview?: () => void;
}) {
  const key = visionInputKey(inspection);
  const currentKey = useRef(key);
  const busyRef = useRef(false);
  const [busyKey, setBusyKey] = useState('');
  const [consentKey, setConsentKey] = useState('');
  const [state, setState] = useState<{ key: string; response?: VisionReviewResponse; error?: string; origin?: 'STORED' | 'NEW_REQUEST' } | null>(null);
  const [historyRequestKey, setHistoryRequestKey] = useState('');
  const [history, setHistory] = useState<{ key: string; entries: { identifier: string; attempt: number | null; review?: VisionReview | null; error?: string }[] } | null>(null);
  useLayoutEffect(() => { currentKey.current = key; }, [key]);
  const current = state?.key === key ? state : null;
  const identifier = inspection?.inspection_id;
  const captureId = inspection?.metrics?.input_provenance?.capture_id;
  const digest = inspection?.metrics?.input_provenance?.crop_sha256;
  const groupId = inspection?.metrics?.reinspection?.group_id ?? null;
  const imageId = inspection?.image_id;
  const groupMatches = !!key && !!reinspectionGroup && reinspectionGroup.group_id === groupId;
  const attemptIndex = groupMatches ? reinspectionGroup.attempts.findIndex(attempt =>
    attempt.inspection_id === identifier && attempt.input_provenance.capture_id === captureId) : -1;
  const previousAttempts = attemptIndex > 0 ? reinspectionGroup!.attempts.slice(0, attemptIndex)
    .filter(attempt => attempt.final_result === 'REINSPECT') : [];
  const historyKey = JSON.stringify([key, groupId, previousAttempts.map(attempt =>
    [attempt.inspection_id, attempt.input_provenance.capture_id, attempt.attempt_number])]);
  const previousSources = JSON.stringify(previousAttempts.map(attempt => ({ identifier: attempt.inspection_id,
    capture: attempt.input_provenance.capture_id, attempt: attempt.attempt_number })));

  useEffect(() => {
    let active = true;
    if (historyRequestKey === historyKey) {
      const sources: { identifier: string; capture: string; attempt: number | null }[] = JSON.parse(previousSources);
      void Promise.all(sources.map(async source => {
        try {
          const stored = await getInspection(source.identifier);
          if (stored.inspection_id !== source.identifier || stored.metrics?.reinspection?.group_id !== groupId
            || stored.metrics?.input_provenance?.capture_id !== source.capture || !visionInputKey(stored)) {
            throw new Error('VISION_HISTORY_SOURCE_MISMATCH');
          }
          const response = await getVisionReview(source.identifier);
          if (response.available !== !!response.review || (response.review && !matchesVisionInput(response.review, stored))) {
            throw new Error('VISION_HISTORY_SOURCE_MISMATCH');
          }
          return { identifier: source.identifier, attempt: source.attempt, review: response.review };
        } catch {
          return { identifier: source.identifier, attempt: source.attempt,
            error: '이전 회차 기록 조회 실패: 세션·접근 권한 또는 이미지 출처를 확인하세요. 미실행으로 간주하지 않습니다.' };
        }
      })).then(entries => { if (active) setHistory({ key: historyKey, entries }); });
    }
    return () => { active = false; };
  }, [historyRequestKey, historyKey, previousSources, groupId]);

  useEffect(() => {
    let active = true;
    if (key && identifier) {
      void getVisionReview(identifier).then(response => {
        if (!active) return;
        const review = response.review;
        if (review && (review.inspection_id !== identifier || review.capture_id !== captureId
          || review.image_sha256 !== digest || review.reinspection_group_id !== groupId
          || !['LIVE', 'FAKE_TEST'].includes(review.analysis_mode) || judgeOutcome(review) === 'INVALID'
          || (review.prompt_version === 'bottle-vision-judge-a-v1' && review.image_id !== imageId))) {
          setState({ key, error: 'VISION_REVIEW_SOURCE_MISMATCH' });
        } else setState({ key, response, origin: 'STORED' });
      }).catch(() => { if (active) setState({ key, error: 'Vision 기록 조회 실패: 세션·Crop 접근 권한을 확인하세요.' }); });
    }
    return () => { active = false; };
  }, [key, identifier, captureId, digest, groupId, imageId]);

  const requestReview = async () => {
    if (!inspection || !key || busyRef.current || !canRequestVisionReview(current?.response, consentKey === key)) return;
    busyRef.current = true;
    setBusyKey(key);
    try {
      const response = await createVisionReview(inspection.inspection_id, crypto.randomUUID().replaceAll('-', ''),
        !current?.response?.capabilities.live_enabled || consentKey === key);
      if (currentKey.current !== key) return;
      if (!response.review || (response.review.analysis_mode === 'LIVE' && !response.capabilities.live_enabled)
        || !matchesVisionInput(response.review, inspection)) throw new Error('VISION_REVIEW_SOURCE_MISMATCH');
      setState({ key, response, origin: 'NEW_REQUEST' });
    } catch {
      if (currentKey.current === key) setState({ key, error: 'VISION_ANALYSIS_FAILED: 자동 재호출하지 않습니다. 저장 결과를 새로고침으로 확인하세요.' });
    } finally { busyRef.current = false; setBusyKey(''); }
  };

  if (!key || !inspection) return <section aria-label="Gemini Vision Judge 2차 이미지 판정" className="panel-card vision-judge-panel">
    <div className="panel-header"><h2 className="panel-title">Gemini Vision Judge · 2차 이미지 판정</h2></div>
    <div className="panel-body"><p className="judge-note">저장된 원본 Crop이 연결된 LIVEVIEW_GRAB REINSPECT 검사를 선택하세요. 탭 전환은 검사나 Google 요청을 실행하지 않습니다.</p></div>
  </section>;
  const response = current?.response;
  const review = response?.review;
  const outcome = review ? judgeOutcome(review) : null;
  return <section aria-label="Gemini Vision Judge 2차 이미지 판정" className="panel-card vision-judge-panel">
    <div className="panel-header">
      <h2 className="panel-title">Gemini Vision Judge · 2차 이미지 판정</h2>
      <span className="panel-meta">INDEPENDENT JUDGE</span>
    </div>
    <div className="panel-body">
      <div className="judge-inspection-id">검사 ID: <strong>{inspection.inspection_id}</strong> · LIVEVIEW_GRAB</div>
      <p className="judge-caption">현재 Crop의 독립적인 이미지 기반 2차 판정입니다. 1차 서버 판정·작업자 기록·재검사 횟수를 변경하지 않습니다. 실제 정상 보증이나 운영 최종 NG 확정이 아닙니다.</p>
      <div className="judge-verdict-card" data-verdict={outcome ?? 'NOT_ANALYZED'}>
        <h3>Gemini Judge 2차 판정</h3>
        <strong className="judge-verdict">{outcome === 'LEGACY_OPINION' ? '미실행 · 과거 관찰 의견만 존재'
          : outcome === 'ANALYSIS_FAILED' ? '실패 · 판정 없음' : outcome ?? (current?.error ? '현재 회차 조회 실패'
            : response ? '현재 회차 Gemini Judge 미실행' : '현재 회차 저장 결과 조회 중')}</strong>
        {review?.analysis_mode === 'FAKE_TEST' && <span className="judge-warning">FAKE_TEST · 실제 Google 판정 아님</span>}
      </div>
      <div className="judge-status" aria-label="Gemini Judge 실행 상태">
        {review ? review.analysis_mode === 'FAKE_TEST' ? 'FAKE_TEST · 실제 분석 아님'
          : outcome === 'ANALYSIS_FAILED' ? 'LIVE ANALYSIS FAILED'
            : current?.origin === 'NEW_REQUEST' ? '신규 LIVE 응답' : '저장 LIVE 응답 조회'
          : busyKey === key ? '보조 분석 요청 중 · 자동 재시도 없음' : current?.error ? 'ANALYSIS FAILED · 판정 없음' : '미실행'}
        {review && 'analysis_status' in review && ` · ${review.analysis_status}`}
        <div>요청 모델: {review?.model_requested ?? response?.capabilities.model_requested ?? '미확인'}</div>
        {review && <div>응답 모델: {review.model_resolved || '미확인'} · 분석 시각: {review.created_at}</div>}
      </div>
      <div className="judge-summary-grid">
        <div className="meta-pill"><span className="meta-pill-label">1차 서버 판정</span><strong className="meta-pill-value">{inspection.final_result}</strong><span className="judge-caption">원본 판정 불변</span></div>
        <div className="meta-pill"><span className="meta-pill-label">작업자 수동 확인</span><span className="meta-pill-value">{manualReviewLabel(reinspectionGroup, inspection)}</span></div>
      </div>
      <details className="judge-details">
        <summary>상세 정보 · 이미지 및 응답 출처</summary>
        <div>Image ID: {imageId}</div><div>Capture ID: {captureId}</div><div>RIG: {groupId ?? '미연결'}</div>
        <div>SHA256: {digest}</div>
        {review && <><div>Vision Review ID: {review.vision_review_id}</div><div>Prompt: {review.prompt_version}</div>
          <div>이 분석의 HTTP 전송 시도: {review.http_attempts ?? '미계측'} · 응답 상태: {review.provider_http_status ?? '미확인'}</div></>}
      </details>
      <p className="judge-note judge-warning">{!response ? 'API 허용 상태 미확인 · 요청 차단' : response.capabilities.live_enabled ? '현재 Crop만 명시적 동의 후 1회 전송 · Google 외부 전송 및 과금 가능' : '실제 API 호출 DISABLED'} · {response?.capabilities.reason ?? (current?.error ?? '저장 기록 조회 중...')}</p>
      {response && (response.capabilities.result_contract !== 'VISION_JUDGE_A_V1' || response.capabilities.consent_policy !== 'PER_REQUEST_CROP_V1') && <p role="status" className="judge-note judge-warning">현재 서버는 동적 Judge 동의 계약 미지원 · 신규 요청 차단 · 승인된 코드 적용 및 재시작 필요</p>}
      {response?.capabilities.live_enabled && !response.available && <label className="judge-consent">
        <input aria-label="현재 Crop Google 전송 동의" type="checkbox" checked={consentKey === key} onChange={event => setConsentKey(event.target.checked ? key : '')} />
        <span>이 검사 Crop PNG를 Google에 1회 전송하는 데 동의합니다. 실패해도 자동 재호출하지 않습니다.</span>
      </label>}
      <button type="button" className="btn btn-primary" disabled={!!busyKey || !canRequestVisionReview(response, consentKey === key)}
        onClick={() => void requestReview()}>현재 Crop Gemini Judge 2차 판정</button>
      {reinspectionGroup?.workflow_policy === 'judge-assisted-v1' && groupMatches
        && reinspectionGroup.status === 'MANUAL_REVIEW_REQUIRED' && onRequestManualReview && <>
        <p className="judge-note">Gemini는 선택적 참고 의견입니다. 미실행·비활성·분석 실패여도 원본 REINSPECT를 유지하며 작업자가 MANUAL_OK / MANUAL_NG / HOLD를 저장할 수 있습니다.</p>
        <button type="button" className="btn" onClick={onRequestManualReview}>3차 작업자 확인으로 이동</button>
      </>}
      {response?.capabilities.analysis_mode === 'FAKE_TEST' && <strong className="judge-note judge-warning">FAKE_TEST · MOCK TEST ONLY · 실제 Gemini 분석 아님</strong>}
      {busyKey === key && <div role="status" className="judge-status">보조 분석 요청 중 · 자동 재시도 없음</div>}
      {current?.error && <div role="alert" className="judge-note judge-error">{current.error}</div>}
      {review && <div className="judge-review" data-testid="vision-review-result">
        {'classification' in review && <p className="judge-note">과거 관찰 의견: {review.classification} · Judge 판정으로 변환하지 않음</p>}
        <div className="judge-evidence-card">
          <h3>시각적 근거 · 모델 관찰 의견(미검증)</h3>
          {'judge_rationale' in review && <><p>2차 판정 근거: {review.judge_rationale}</p>
            <ul>{review.defect_locations.map((value, index) => <li key={index}>관측 위치(미검증): {value}</li>)}</ul></>}
          <ul>{review.visible_observations.map((value, index) => <li key={index}>{value}</li>)}</ul>
        </div>
        <div className="judge-evidence-card"><h3>분석 한계</h3><ul>{review.limitations.map((value, index) => <li key={index}>{value}</li>)}</ul></div>
        <div className="judge-evidence-card"><h3>작업자 권고</h3><p>{review.recommended_operator_action}</p></div>
        <p className="judge-note">{review.failure_code ?? '보조 응답 스키마 검증 완료'} · 운영 최종 판정·작업자 승인 아님 · 원본 판정 불변</p>
      </div>}
      {previousAttempts.length > 0 && <section className="judge-evidence-card" aria-label="이전 회차 Gemini Judge 저장 결과">
        <h3>동일 제품 그룹 · 이전 회차 Gemini 결과</h3>
        <p className="judge-caption">현재 회차 판정이 아닙니다. 저장 결과만 조회하며 Google 재호출·전송 동의 승계·검사 횟수 변경은 없습니다.</p>
        <button type="button" className="btn" disabled={historyRequestKey === historyKey}
          onClick={() => setHistoryRequestKey(historyKey)}>이전 회차 Gemini 결과 보기</button>
        {historyRequestKey === historyKey && history?.key !== historyKey && <p role="status">이전 회차 저장 결과 조회 중...</p>}
        {history?.key === historyKey && history.entries.map(entry => <div className="judge-review" key={entry.identifier}
          data-testid="vision-history-result">
          <strong>검사 {entry.attempt}회차 · {entry.identifier}</strong>
          {entry.error ? <p role="alert" className="judge-error">{entry.error}</p> : entry.review ? <>
            <div className="judge-verdict-card" data-verdict={judgeOutcome(entry.review)}>
              <h3>이전 회차 Gemini 독립 판정</h3>
              <strong className="judge-verdict">{judgeOutcome(entry.review) === 'LEGACY_OPINION' ? '과거 관찰 의견 · Judge 판정 아님'
                : judgeOutcome(entry.review) === 'ANALYSIS_FAILED' ? '실패 · 판정 없음' : judgeOutcome(entry.review)}</strong>
            </div>
            <p className="judge-note">{entry.review.analysis_mode === 'FAKE_TEST' ? 'FAKE_TEST · 실제 Google 판정 아님' : '저장 LIVE 응답 조회'}
              {'analysis_status' in entry.review && ` · ${entry.review.analysis_status}`}</p>
            <div>요청 모델: {entry.review.model_requested} · 응답 모델: {entry.review.model_resolved || '미확인'}</div>
            <div>분석 시각: {entry.review.created_at}</div>
            <details className="judge-details"><summary>이전 회차 근거 및 이미지 출처</summary>
              <div>원래 검사 ID: {entry.review.inspection_id}</div>
              {'image_id' in entry.review && <div>Image ID: {entry.review.image_id}</div>}
              <div>Capture ID: {entry.review.capture_id}</div><div>SHA256: {entry.review.image_sha256}</div>
              {'classification' in entry.review && <p>과거 관찰 의견: {entry.review.classification} · Judge 판정으로 변환하지 않음</p>}
              {'judge_rationale' in entry.review && <><p>판정 근거: {entry.review.judge_rationale}</p>
                <ul>{entry.review.defect_locations.map((value, index) => <li key={index}>관측 위치(미검증): {value}</li>)}</ul></>}
              <h3>시각적 관찰 의견(미검증)</h3><ul>{entry.review.visible_observations.map((value, index) => <li key={index}>{value}</li>)}</ul>
              <h3>분석 한계</h3><ul>{entry.review.limitations.map((value, index) => <li key={index}>{value}</li>)}</ul>
              <p>작업자 권고: {entry.review.recommended_operator_action}</p>
              {entry.review.failure_code && <p className="judge-error">{entry.review.failure_code}</p>}
            </details>
          </> : <p>이전 회차에 저장된 Gemini Judge 결과 없음</p>}
        </div>)}
      </section>}
    </div>
  </section>;
}

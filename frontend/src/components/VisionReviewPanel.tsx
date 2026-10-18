import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { InspectionResponse } from '../types/inspection';
import type { VisionReviewResponse } from '../types/visionReview';
import { createVisionReview, getVisionReview } from '../api/visionReview';
import { matchesVisionInput, visionInputKey } from '../utils/visionReviewState';

export function VisionReviewPanel({ inspection }: { inspection: InspectionResponse | null }) {
  const key = visionInputKey(inspection);
  const currentKey = useRef(key);
  const busyRef = useRef(false);
  const [busyKey, setBusyKey] = useState('');
  const [state, setState] = useState<{ key: string; response?: VisionReviewResponse; error?: string } | null>(null);
  useLayoutEffect(() => { currentKey.current = key; }, [key]);
  const current = state?.key === key ? state : null;
  const identifier = inspection?.inspection_id;
  const captureId = inspection?.metrics?.input_provenance?.capture_id;
  const digest = inspection?.metrics?.input_provenance?.crop_sha256;
  const groupId = inspection?.metrics?.reinspection?.group_id ?? null;

  useEffect(() => {
    let active = true;
    if (key && identifier) {
      void getVisionReview(identifier).then(response => {
        if (!active) return;
        const review = response.review;
        if (review && ((!['LIVE', 'FAKE_TEST'].includes(review.analysis_mode) || (review.analysis_mode === 'LIVE' && !response.capabilities.live_enabled)) || review.inspection_id !== identifier || review.capture_id !== captureId
          || review.image_sha256 !== digest || review.reinspection_group_id !== groupId)) {
          setState({ key, error: 'VISION_REVIEW_SOURCE_MISMATCH' });
        } else setState({ key, response });
      }).catch(() => { if (active) setState({ key, error: 'Vision 기록 조회 실패: 세션·Crop 접근 권한을 확인하세요.' }); });
    }
    return () => { active = false; };
  }, [key, identifier, captureId, digest, groupId]);

  const requestReview = async () => {
    if (!inspection || !key || busyRef.current || !current?.response?.capabilities.enabled || current.response.available) return;
    busyRef.current = true;
    setBusyKey(key);
    try {
      const response = await createVisionReview(inspection.inspection_id, crypto.randomUUID().replaceAll('-', ''));
      if (currentKey.current !== key) return;
      if (!response.review || (response.review.analysis_mode === 'LIVE' && !response.capabilities.live_enabled)
        || !matchesVisionInput(response.review, inspection)) throw new Error('VISION_REVIEW_SOURCE_MISMATCH');
      setState({ key, response });
    } catch {
      if (currentKey.current === key) setState({ key, error: 'VISION_ANALYSIS_FAILED: 자동 재호출하지 않습니다. 저장 결과를 새로고침으로 확인하세요.' });
    } finally { busyRef.current = false; setBusyKey(''); }
  };

  if (!key || !inspection) return null;
  const response = current?.response;
  const review = response?.review;
  return <section aria-label="Gemini Vision 이미지 2차 분석" className="panel-card p-3 space-y-2 text-xs">
    <h2 className="font-semibold">Gemini Vision · 이미지 2차 분석</h2>
    <p>현재 검사 Crop 이미지를 별도 Vision 모델이 분석합니다. 원본 PatchCore 판정 및 작업자 확인 결과는 변경되지 않습니다. 새 Grab·재검사 횟수 증가는 없습니다.</p>
    <div className="font-mono break-all">{inspection.inspection_id} · LIVEVIEW_GRAB · {captureId} · SHA256 {digest}</div>
    <p className="text-amber-300">실제 API 호출 DISABLED · 후보 {response?.capabilities.model_requested ?? 'gemini-4-argon'} API/이미지 지원 UNKNOWN. {response?.capabilities.reason ?? (current?.error ?? '저장 기록 조회 중...')}</p>
    <button type="button" className="btn" disabled={!!busyKey || !response?.capabilities.enabled || response.available}
      onClick={() => void requestReview()}>현재 Crop Gemini 2차 분석</button>
    {response?.capabilities.analysis_mode === 'FAKE_TEST' && <strong>FAKE_TEST · MOCK TEST ONLY · 실제 Gemini 분석 아님</strong>}
    {busyKey === key && <div role="status">보조 분석 요청 중 · 자동 재시도 없음</div>}
    {current?.error && <div role="alert">{current.error}</div>}
    {review && <div className="space-y-1" data-testid="vision-review-result">
      <strong>{review.analysis_mode === 'FAKE_TEST' ? 'FAKE_TEST · 실제 분석 아님' : '저장 LIVE 보조 의견'} · {review.classification}</strong>
      <p>NG/OK 확정 아님 · 원본 판정 불변</p>
      <div>{review.visible_observations.map((value, index) => <p key={index}>모델 관찰 의견(미검증): {value}</p>)}</div>
      <div>{review.limitations.map((value, index) => <p key={index}>한계: {value}</p>)}</div>
      <p>작업자 권고: {review.recommended_operator_action}</p>
      <p>{review.failure_code ?? '보조 응답 스키마 검증 완료'} · 요청 모델 {review.model_requested} · 응답 모델 {review.model_resolved} · {review.created_at}</p>
    </div>}
  </section>;
}

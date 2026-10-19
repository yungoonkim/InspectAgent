import type { BottleEdges } from '../utils/bottleEdges';

const statusLabels = { SUCCESS: '성공 (기하 조건)', UNCERTAIN: '불확실', FAILED: '실패' };
const numberLabel = (value: number | null) => value === null ? '계산 불가' : value.toFixed(2);

export function BottleEdgeDetails({ edges }: { edges: BottleEdges }) {
  return <details className="bottle-edge-information">
    <summary>병 테두리 · 외곽: {statusLabels[edges.assessment.outer.status]} / 내부 림 후보: {statusLabels[edges.assessment.rim.status]}</summary>
    <p>원본 Crop 픽셀 실측 · 초록: 외곽 / 노랑: 내부 림 후보. 원·누락 구간을 보완하지 않습니다.
      반사 경계와 실제 림의 구분 정확도는 미검증이며, 성공은 제품 정상이나 검출 정확도를 보증하지 않습니다.</p>
    <p>검출 제한: {edges.reasons.join(', ') || '기존 검출 조건 충족'}</p>
    {(['outer', 'rim'] as const).map(name => {
      const assessment = edges.assessment[name];
      return <div key={name} className="edge-measurement-card">
        <strong>{name === 'outer' ? '병 외곽' : '내부 림 후보'}: {statusLabels[assessment.status]}</strong>
        <p>폐곡선: {assessment.closed ? '확인' : '아님'} · 연결 성분 {assessment.components}개 · 관측 선분 {edges[name].length}개
          {name === 'rim' && <> · 연결 각도 구간 {(assessment.coverage * 100).toFixed(1)}% · 표본 최대 미검출 각도 {numberLabel(assessment.largestGapDegrees)}°</>}</p>
        <p>원형도 4πA/P²: {numberLabel(assessment.circularity)} · 기준 반경 √(A/π): {numberLabel(assessment.referenceRadius)} px
          · 반경 편차 RMS / 최대: {numberLabel(assessment.radialRms)} / {numberLabel(assessment.radialMax)} px</p>
        <p>근거: {assessment.reasons.join(', ') || '관측 경계의 단일 폐곡선 확인'}</p>
      </div>;
    })}
    <p>기준 원은 관측 면적의 등가 원(중심은 분할 영역 무게중심)이며 화면에 추가로 그리지 않습니다.
      외곽 둘레는 픽셀 격자 길이라 원형도에 계단 오차가 있습니다. 각도는 5° 간격 표본이며 신뢰 확률·합격 기준이 아닙니다.</p>
    <div className="edge-region-statistics" aria-label="영역별 밝기 비교">
      {([['roi', 'A · 전체 ROI'], ['body', 'B · 외곽 내부 후보'],
        ['rim', 'C · 닫힌 림 후보 내부'], ['background', 'D · 외곽 바깥 후보']] as const).map(([name, label]) => {
        const region = edges.regions[name];
        return <div key={name} className="edge-measurement-card">
          <strong>{label}</strong>
          {region ? <>
            <p>평균 / 중앙값 / 표준편차 GV: {region.mean.toFixed(2)} / {region.median.toFixed(2)} / {region.std.toFixed(2)}</p>
            <p>{region.pixels.toLocaleString()} px · ROI 면적의 {(region.areaRatio * 100).toFixed(2)}%</p>
          </> : <p>계산 불가 — 외곽 분할이 불확실하거나 해당 경계가 완전히 닫히지 않았습니다. 추정값을 채우지 않습니다.</p>}
        </div>;
      })}
    </div>
    <p>GV는 OpenCV 8-bit RGB→GRAY 정수 변환 기준의 원본 픽셀 통계입니다. B/D는 외곽 분할 조건 충족 시에만,
      C는 모든 관측 림 구간이 연결된 폐곡선일 때만 계산합니다. 내부 영역은 겹치므로 네 영역을 합산하지 않습니다.
      서버는 기존 전체 ROI 평균과 밝기 하한 125.0을 그대로 사용합니다. 영역별 GV에는 125.0을 적용하지 않으며 서버 품질·최종 판정에 반영하지 않습니다.</p>
  </details>;
}

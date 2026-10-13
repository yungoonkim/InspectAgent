# VisionInsight — 프로젝트 Agent 개발 지침

## 프로젝트
- **이름:** VisionInsight
- **목표:** MVTec AD Bottle 기반 산업용 Vision 검사 이상 진단 AI Agent
- **우선순위:** AI Agent 70% / Vision 30%
- **기술 스택:** Python 3.11(Miniconda `vision-insight`), FastAPI, OpenCV/NumPy, Gemini, React/TypeScript, Google Cloud Run

## 작업 방법
1. 작업 전에 현재 저장소와 기존 구현/문서를 읽고, 변경 범위와 테스트 계획을 간단히 설명한다.
2. 한 번에 하나의 기능 단위만 구현한다. 기존 동작을 무단 삭제하거나 전면 재작성하지 않는다.
3. 변경 후 관련 테스트를 실제 실행하고 성공/실패 및 미실행 이유를 명시한다.
4. 완료 보고는 한국어로 작성하며 변경 파일, 실행 명령, 검증 근거, 남은 작업을 포함한다.
5. 중요한 구조 변경과 외부 서비스 생성/권한 변경/과금 작업은 사전에 사용자에게 확인한다.

## 데이터 및 안전 규칙
1. MVTec AD 원본 이미지를 수정하지 않는다.
2. `ground_truth` 마스크와 주입 정답은 프로젝트 외부의 평가 전용 환경에 보관하고, 운영 코드와 Agent 도구에서 읽지 않는다.
3. `broken_large`, `contamination`처럼 정답이 포함된 원본 경로를 Agent에게 전달하지 않는다. 중립적 `image_id`를 사용한다.
4. `product_id`와 `inspection_id`를 분리하고, 검사 ID 중복을 방지한다.
5. 제품 판정(`OK/NG/UNKNOWN`)과 영상 품질(`NORMAL/WARNING/ERROR`)을 별도로 저장한다.
6. 원본 정답 라벨을 Vision 예측 결과로 둔갑시키지 않는다. 계산하지 않은 점수나 실제 발생하지 않은 로그를 생성하지 않는다.
7. 입력 이미지 밝기 저하는 조명 장치 고장이 확정되었다는 뜻이 아니다. Agent는 관측·가설·한계를 분리한다.
8. 합성 설비 로그가 있다면 합성임을 명확하게 기록하고 실제 물리적 원인의 증거로 단정하지 않는다.
9. API 키, 인증 정보, 평가 정답, 대용량 데이터셋, 실행 로그는 Git에 노출하지 않는다.

## 개발 구조
1. 환경은 Miniconda `vision-insight`(Python 3.11)를 사용한다. 별도 venv를 추가하지 않는다.
2. 서버 API/영상 처리/저장소/Agent 도구/UI를 느슨하게 결합한다.
3. 로컬 JSONL 저장은 개발용이다. Cloud Run에서 영구 저장이 필요하면 Cloud Storage 등 별도 저장 계층을 사용한다.
4. 컨테이너는 `0.0.0.0`과 `PORT` 환경변수에 바인딩한다.
5. API와 도구의 입력/출력 형식은 `docs/inspection-data-schema.md`에 유지한다.
6. 사용자 제공 임의의 파일 경로를 그대로 읽지 않고 서버가 관리하는 `image_id`를 사용한다.
7. 실제 Gemini tool call 결과를 확인하며, 모델이 도구를 호출하지 않았을 때 호출했다고 보고하지 않는다.

## 일정 및 완료 기준
- Day 1: Bottle 이미지 로드 + `POST /inspections` 검사 ID 반환
- Day 2: Vision 지표 계산 + 검사/이벤트 로그 자동 저장
- Day 3: T01/T03/T05/T06 반복 재현 + 정답 분리
- Day 4: Gemini Agent 실제 도구 호출 + 구조화 보고서
- Day 5: 상황별 추가 조사 + 반례 평가
- Day 6: React E2E + Cloud Run 준비
- Day 7: Cloud Run HTTPS API/Agent 분석 검증 + 문서화

> 이 문서는 프로젝트의 Agent 지침 초안이다. **Antigravity IDE에서 자동 인식되는 규칙 파일 위치와 형식은 실제 사용 중인 버전에 따라 확인하고 필요하면 IDE의 Rules 기능에 등록한다.**

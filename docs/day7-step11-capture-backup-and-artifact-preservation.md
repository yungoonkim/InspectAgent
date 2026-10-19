# Step 11 — Capture 백업 및 검사 산출물 보존 확인

## A–C. 승인된 Capture 4개 백업: PASS

백업 폴더: `C:\Users\USER\VisionInsight_GrabBackup_Step11_20261019\`

manifest: `C:\Users\USER\VisionInsight_GrabBackup_Step11_20261019\backup_manifest.json`

검증 시각: **2026-10-19T02:11:43.2763926Z (KST 11:11:43)**.

| Capture ID | bytes | 원본 복사 전 = 원본 복사 후 = 백업 SHA256 |
|---|---:|---|
| `CAP-0e821e45b4d04984ad7f56f3dd3decf8` | 775553 | `4bbff87d5eae08d9b9b31e873bfc6275b10a4b2b6149cbb6804d9632f775955f` |
| `CAP-14543e2caf6d4ee58ad1fdd91bd6ff14` | 777166 | `bda88e853d4a28093441317eebf6ec8393652e7125957599a1e41bcd53310d09` |
| `CAP-411dbfc718be42ef91885ca243ecb465` | 784387 | `cf948eebae9fe8c865a3e25fb19570fcb2ab4faf03d9d9bdfd570c59b78bc363` |
| `CAP-db609379922a4b4e883cd894931923e1` | 780672 | `e5a0d231486bae29eb5c660e45acbddb78c99e6e5f87c0c5f13e57945b9db044` |

원본 디렉터리는 `C:\Users\USER\AI-NativeAgent\Project\InspectAgent\data\outputs\captures\`, 파일명은 Capture ID + `.png`다. 백업에는 PNG 4개와 manifest 1개만 생성했다. 복사 중 PNG 변경 이벤트는 0, 원본 집합/해시도 동일했다. 원본 스트림은 읽기 전용으로 열었고 복사 동안 쓰기·삭제 공유를 허용하지 않았다. 새 파일 생성 모드만 사용했으며 원본 삭제·이동·수정 명령은 없었다.

기존 두 백업의 PNG 9개/manifest 2개 및 운영 검사·로그 JSONL 2개의 총 **13개** SHA256은 백업 전후와 마지막 확인 때 동일했다. 기존 백업 폴더는 변경하지 않았다.

승인된 4개의 연결 Inspection ID는 저장 검사 기록에서 발견되지 않았다. Frame Index/ROI 및 이 4개에 대응하는 Crop/Heatmap은 **UNKNOWN**으로 유지한다.

## 중요한 상태 변화 — 승인 범위 밖 새 Capture

백업 종료 이후 산출물 조사 시점에 승인된 4개는 원본 Capture 폴더에서 사라져 있었고, 아래 새 파일 1개를 확인했다. 승인된 4개 백업 파일은 다시 해시 검증하여 manifest와 모두 일치함을 확인했다.

- 새 파일: `C:\Users\USER\AI-NativeAgent\Project\InspectAgent\data\outputs\captures\CAP-c6a86173515b4005b0c7c485df30f49a.png`
- 크기: 777388 bytes
- 파일 수정 시각: `2026-10-19T02:13:53.5403308Z` (KST 11:13:53)
- SHA256: `f1332dcec2ffd1e06822385a31897f4fd2aaee69bb86d766243aa668f2f565e9`
- 연결 Inspection ID: 저장 JSONL에서 발견되지 않음. Crop/Heatmap 연계는 UNKNOWN.
- 이 파일은 이번 승인된 4개에 포함되지 않아 **복사하지 않았다**. 추가 백업에는 별도 승인이 필요하다.

Codex가 실행한 백업 및 감사 스크립트에는 원본 PNG 삭제·수정이나 서버 요청/종료 동작이 없다. 원본 변경은 백업 검증 구간 이후 관찰됐다. 현재 서버는 계속 PID 25328에서 LISTENING이다. 기존 CaptureStore에는 TTL cleanup과 디렉터리 초기화 시 파일 제거 경로가 있으나, 이번 변화가 어느 경로/요청에서 일어났는지는 서버 로그·runtime 메모리 확인이 없어 **UNKNOWN**이다. 파일 수정 시각만으로 사용자의 조작이나 reload 원인을 확정하지 않는다.

## D. ROI Crop 저장과 연결

프로젝트 루트: `C:\Users\USER\AI-NativeAgent\Project\InspectAgent\`

- 영속 Crop: `data/outputs/grab_inspection_inputs/{image_id}.png`
- 대응 metadata: 같은 디렉터리의 `{image_id}.json`. image ID와 Crop SHA256, 소유권 바인딩을 저장한다. 소유권 값/세션 토큰은 보고서에 노출하지 않았다.
- 실제 Grab 검사 **12건**에서 PNG와 metadata가 모두 존재하고, record provenance의 Crop SHA256/해상도 및 metadata ID/해시가 일치했다.

| Inspection ID | Capture ID | Frame | ROI (x, y, width, height) | image_id |
|---|---|---:|---|---|
| INSP-001652 | CAP-3c483952db514e27832d9a69f573672f | 59 | 700,122,284,272 | IMG-GRAB-315b2ea9070c475c850d9c1160b0483d |
| INSP-001653 | CAP-3c483952db514e27832d9a69f573672f | 59 | 1403,124,284,272 | IMG-GRAB-7a7208ea157647c9bb07933a3291941d |
| INSP-001655 | CAP-9ece61bcc44945499b8d604b0f842f0f | 132 | 271,121,277,274 | IMG-GRAB-07bd539a1bb94a9fa637841a0855cb60 |
| INSP-001656 | CAP-467f14aff28242679062d6cd744c73d5 | 140 | 333,117,285,284 | IMG-GRAB-c58ef4eb5e1b41d4be8af09cddce14c7 |
| INSP-001657 | CAP-6923ec6a277049a081141c201547f4f2 | 64 | 751,124,278,272 | IMG-GRAB-b46dc76e52d84cfcb6812766eba5c1fd |
| INSP-001658 | CAP-8f92698205f044738fe3e6eb4c9d453c | 52 | 646,124,293,274 | IMG-GRAB-cf7945be12f745ce8b2781ee7abc25e8 |
| INSP-001660 | CAP-ac74f8548ed442e48eaa6f6bec8a01fa | 82 | 895,120,282,280 | IMG-GRAB-15c0c322b0384d8a818604b6d5c64ce0 |
| INSP-001661 | CAP-07ffc3e9811145e885686e77fdbe48ba | 93 | 986,115,294,284 | IMG-GRAB-fed9f6ebff4b41818a943cf79609cb03 |
| INSP-001662 | CAP-5bffd678a52d401bb87c71be75299862 | 101 | 1058,121,287,276 | IMG-GRAB-5699c22c805f4e268684f25bd071510a |
| INSP-001664 | CAP-9b437523902c440ab7a83667e902f754 | 42 | 907,123,291,274 | IMG-GRAB-98b2f8f61af64544998b45b94a8d5611 |
| INSP-001665 | CAP-42ab6204e99d4016beaedfc4335c460f | 54 | 1011,120,291,274 | IMG-GRAB-802b755acf314404a2b3169a5c07416e |
| INSP-001666 | CAP-c070061f5b33496d8ff00c2f8a07aea1 | 67 | 1113,118,291,274 | IMG-GRAB-1b9ab4741aa44de89b956e4a574ffba1 |

위 12건의 video_id는 모두 `VID-000001`, 저장 final_result는 모두 `REINSPECT`다. 기존 기록을 읽은 값이며 신규 검사를 실행하지 않았다.

Crop은 검사 시 `frame[y:y+height, x:x+width]`를 PNG로 별도 저장한다 (`backend/grab_inspection.py:188-211`). 임시 Capture 종료 cleanup과 다른 디렉터리이며, shutdown 시 Crop을 삭제하는 경로는 확인되지 않았다. 새 Crop 저장 실패 시에는 해당 작업이 새로 만든 파일만 rollback 삭제한다 (`:212-219`). 이 모듈에는 기존 Crop을 시작 시 일괄 삭제하는 처리가 없다.

## E. Heatmap / Anomaly Map

저장 위치: `data/outputs/inspection_anomaly_maps/`

- `{inspection_id}.npz`: 수치 이상지도
- `{inspection_id}.json`: image ID, 원본 이미지 크기, map 크기, transform, artifact SHA256
- `{inspection_id}_overlay.png`: 표시용 overlay

**14개 bundle / 파일 42개**가 존재한다. 위 Grab 12건과 등록 이미지 검사 INSP-001650/001651의 2건에서 record/image ID, 원본 크기, overlay PNG 크기, NPZ/overlay metadata SHA256이 일치했다. NPZ는 `allow_pickle=False`로 읽어 float32, 256×256, 유한한 수치임을 확인했다. PatchCore/checkpoint는 로드하지 않았다.

연결 예: INSP-001652 → IMG-GRAB-315b2ea9070c475c850d9c1160b0483d.png (284×272) → INSP-001652.json/.npz/_overlay.png. 코드의 생성 계약과 저장된 ID·크기·해시를 확인한 범위이며, 모델 재추론이나 검출 성능 재평가를 수행하지 않았다.

Map의 shutdown cleanup은 확인되지 않았다. `backend/anomaly_map_store.py`의 삭제 처리는 신규 bundle 저장 실패 시 rollback과 쓰기 lock 해제에 사용된다. 기존 bundle은 변경하지 않았다.

## F. 검사 JSONL / 실행 로그 / 재검사 상태

- 결과: `data/inspections.jsonl` — 1621행
- 실행 이벤트: `data/inspection_logs.jsonl` — 8087행
- 두 기록은 inspection_id로 연결된다. 위 Grab 12건에는 각각 이벤트 6개가 연결돼 있다. 이벤트 message 원문은 출력하지 않았다.
- 재검사/수동 확인: `data/outputs/reinspection_history/state.json` 존재 확인.

이들은 파일 기반 영속 저장이며, 확인한 서버 shutdown 처리에 삭제·초기화 경로가 없다. 디스크 장애에 대비한 별도 매체 백업까지 확보됐다는 의미는 아니다.

기존 JSONL의 과거 ID 중복도 확인됐다. INSP-000001은 4행, 000002/000003/000004/000005는 각 3행, 000006/000007은 각 2행이다. 중복 초과 행은 13개다. 작업 전후 JSONL 해시는 동일하며 이번에 생성·수정한 기록이 아니다. 중복 ID의 과거 이력을 유일하게 연결할 수 있다고 주장하지 않는다. 수정·정리는 이번 범위에 포함하지 않았다.

## G. AI 보고서 저장과 연결

Diagnostic Agent: `data/outputs/agent_reports/{inspection_id}.json`. 파일 5개의 이름과 본문 inspection_id가 일치하고, 해당 검사 ID가 JSONL에 존재한다.

| 저장 보고서 | 본문 provenance | 주의점 |
|---|---|---|
| INSP-000001.json | LIVE_AGENT_ANALYSIS | JSONL 동일 ID 4행. 어느 과거 행과 정확히 연결되는지는 UNKNOWN |
| INSP-000002.json | LIVE_AGENT_ANALYSIS | JSONL 동일 ID 3행. 어느 과거 행과 정확히 연결되는지는 UNKNOWN |
| INSP-001396.json | RECORDED_TEST_FIXTURE | 저장 Fixture로 취급 |
| INSP-001398.json | RECORDED_TEST_FIXTURE | 저장 Fixture로 취급 |
| INSP-001406.json | LIVE_AGENT_ANALYSIS | 본문에 저장된 provenance. 이번에 실제 호출을 검증했다는 의미는 아님 |

5건 모두 analysis_id와 COMPLETED 상태가 저장돼 있었다. 저장 파일 구조를 확인한 것이며 이번 작업에서 실제 Gemini 호출이 성공했다는 의미가 아니다. INSP-001652의 Agent report는 이 저장 위치에 존재하지 않는다.

Agent report는 shutdown에서 삭제하지 않는다. 다만 현재 저장 코드는 동일 inspection_id 경로를 `w` 모드로 열어 향후 재분석 시 덮어쓸 수 있다 (`backend/agent/api.py:286-291`). 이번에는 해당 API를 호출하거나 코드를 수정하지 않았다.

독립 Gemini Vision은 `data/outputs/vision_reviews/state.json`을 사용하는 설계이나 현재 이 state 파일은 없다. Vision 결과가 생성돼 있다고 주장하지 않는다.

## H. 종료 판단과 남은 위험

1. **승인된 PNG 4개 보존은 완료**. 원본이 사라져도 백업으로 바이트 복구가 가능하다. 운영 Capture로 재등록하지 않는다.
2. **현재 새 Capture 1개는 미백업**. 보존이 필요하면 별도 승인 후 백업 검증이 필요하다. 그 전에 서버 종료를 권고하지 않는다.
3. 임시 Capture는 TTL cleanup에서 삭제되며, shutdown뿐 아니라 다음 Capture 디렉터리 초기화 때에도 기존 PNG를 삭제한다 (`backend/capture_store.py:69-80, 101-107, 224-228`).
4. 저장 Crop/Map/JSONL/report/재검사 state는 파일로 남는 설계이나 CaptureStore 세션은 메모리에만 있다. 서버 재시작 후 기존 소유권 인증이 복원되지 않아 과거 Crop이나 group을 UI/API에서 조회하지 못할 가능성이 있다 (`backend/grab_inspection.py:132-146`, `backend/vision_review_api.py:20-36`). **파일 영속성과 UI 접근 복원은 별도**이며 후자는 보장하지 않는다.
5. 영속 자료 일체의 별도 매체 snapshot이 필요하다면 Crop 파일 24개, Map 파일 42개, 검사/로그 JSONL, 재검사 state, Agent report 5개를 대상으로 추가 백업을 별도 계획한다. 이번에는 이들을 외부로 복사하지 않았다.

읽기 전용 감사 내 대상 파일 76개의 시작/중간/종료 해시는 모두 동일했다. 이 76개는 해당 시점의 자료·현재 Capture·marker를 포함한 선택 범위이며, 모델·DB까지 포함한 전체 자산 검증이 아니다.

실행 파일: `scripts/backup_step11_captures.ps1` (백업·검증), `scripts/audit_step11_inspection_artifacts.py` (backend import 없는 읽기 전용 감사). backend 코드 변경, 서버 조작, PatchCore 로드·추론, Gemini 호출, 이미지 외부 전송은 0회다. 추가 구현·실제 검사·자동 재실행 없이 사용자에게 보고한 뒤 대기한다.

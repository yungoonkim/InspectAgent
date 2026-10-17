# Day5 Step 3 Phase B-2B-R — Synthetic Input A/B Diagnostic

작성일: 2026-10-17. **최종 상태: PARTIAL**.

## 1. 결론과 상태 구분

합성3종의 A/B 추론과 Tensor·Normalize·score 관측은 확보했다. 공식 모델은1회 로딩했고, **총7회 추론**했다. 그러나 실행기 최종 보호 검사에서 차단된 socket 시도1건을 검출하여 exit1 / `STOPPED`로 종료했다. 원본 결과를 COMPLETE로 바꾸지 않았고 추가 추론하지 않았다.

- **OBSERVED:** Path A Normalize2회, Path B1회. 모든 합성 입력에서 backbone 입력과 score가 달라졌다.
- **OBSERVED:** SYN-003만 고정34.1442 기준의 수학적 위치가 교차했다. 제품 OK/NG나 서버 최종 판정은 만들지 않았다.
- **OBSERVED:** SYN-001의 추가 기존 wrapper 호출과 계측된 Path A의 입력 Tensor·score·anomaly_map이 정확히 일치했다.
- **CONFIRMED:** 모델 state_dict 전후 fingerprint 및 공식 checkpoint·운영 자산 무결성 보존.
- **PARTIAL:** 최종 실행기 보호 검사 정상 종료까지 입증한 것은 아니다. 차단 사건의 원래 call stack이 저장되지 않은 한계를 남긴다.
- **UNRESOLVED:** 운영 전처리 문제, threshold provenance 및 정식 교체 판단. 실험 완료 여부와 별개다.

## 2. 승인 및 확인한 문서

직전 B-2B는 독립 정상 개발 이미지를 확보하지 못해 중단됐다. 이번에는 사용자가 **메모리 생성 중립 합성3종**으로 제한적 CPU 추론을 별도 승인했다. 실제 정상 이미지 선정 게이트를 통과했다고 해석하지 않는다.

AGENTS.md와 AUTO/MANUAL 명세, B-2A 감사, B-2B 중단 보고서, PostgreSQL ROI 완료 보고서를 확인했다. 기존 중단 보고서·운영 코드·학습/Calibration 코드는 변경하지 않았다. 현재 wrapper의 직접 생성과 predict는 검사 API/ID 발급/JSONL 저장에 의존하지 않음을 소스로 확인한 후 사용했다. get_settings 기반 singleton 대신 checkpoint·metadata·cpu를 명시한 constructor를 사용했다.

작업 전후 git status를 확인했고 기존 Agent/DB/영상/발표/테스트 변경을 보존했다. 기존237개 파일의 시작 SHA256을 기록했다. PostgreSQL에 접속하거나 Docker를 조작하지 않았다.

## 3. 모델과 환경

| 항목 | 실제 사용값 |
|---|---|
| 공식 모델 | `models/patchcore/patchcore_bottle.ckpt` |
| checkpoint SHA256 | `4b239d28e72c63bf782cd1d31981d7f4362c591e7c23164e4c0ac8b5e99b52a3` |
| memory bank | `[9216,384]` |
| 고정 비교값 | **34.1442** |
| 모델 모드 | CPU, 모든 model module eval, torch.inference_mode |
| CPU 실행 | 순차, torch threads=1, deterministic algorithms 활성 |
| torch / torchvision | `2.6.0+cu124` / `0.21.0+cu124` — CUDA 빌드라도 GPU 사용 안 함 |
| anomalib / lightning / timm | `2.7.0` / `2.6.6` / `1.0.30` |

공식 모델만 로딩했으며209장 실험 모델은 로딩·비교하지 않았다. optimizer/backward/학습/재저장은 없다. HF/Transformers offline, process 한정 GPU 비노출, bytecode 쓰기 비활성화를 적용했다. 환경변수·시스템 PATH를 영구 변경하지 않았다.

## 4. 결정적 합성 입력 — 실제 이미지 미사용

모두256×256×3 uint8 BGR 배열이며 파일을 읽거나 PNG로 저장하지 않았다. 기존 Registry에 등록하지 않았고 운영 image_id를 사용하지 않았다.

| ID | 생성식 | 원본 배열 SHA256 |
|---|---|---|
| SYN-001 | 모든 채널128의 constant gray | `83ab53863cf746efe2611c6b521cfbdefba4f5325cf123ab451c385035b394ef` |
| SYN-002 | x=0..255를 행마다 반복, 세 채널 동일 수평 gradient | `fb5f204ed84efa48484d193e260fcb573938c9153d852300b8f0cdf58cc2b85b` |
| SYN-003 | B=x, G=y, R=255×((floor(x/32)+floor(y/32)) mod2) | `5baa15d3dc5452deb0bef2d91a2eb8444cf9d85571b74c4ac586862176e2a8a0` |

난수 사용 없이 두 번 생성해 array equality를 검증했다. 채널 순서는 BGR→RGB 기준 Tensor와 대조했다. **정상 병 이미지가 아니며** 정상 분포·제품 성능·Calibration·ROI 적합성을 추정하는 데이터가 아니다. MVTec 원본, Calibration29건, 평가 데이터, Ground Truth, 컨베이어 프레임, 캡처 PNG를 사용하지 않았다.

## 5. 경로 구성 및 계측

### Path A

`PatchCoreInferencer` 원본 인스턴스의 **기존 predict() 자체**를 사용했다. BGR→RGB/PIL→Resize256(bilinear, antialias=True)→ToImage→float32(scale=True)→외부 Normalize→전체 Lightning 모델→내부 export_transform→core→후처리→pred_score 순서다.

### Path B

wrapper를 process 안에서 얕게 복사하고 외부 Compose의 **마지막 Normalize만 제외**했다. 나머지 Resize/ToImage/ToDtype 객체는 Path A와 같은 객체이고 model·checkpoint·memory bank·내부 전처리·후처리도 같은 객체다. 운영 소스나 모델의 preprocessor를 변경하지 않았다.

실제 내부 transform은 Resize256(antialias=True)+Normalize, 직접 forward에서 실행되는 export_transform은 **Resize256(antialias=False)+Normalize**였다. 내부에 추가 ToTensor/scale/Crop은 없었다. 양쪽 모두 같은 내부 경로를 사용했다.

### 실제 계측 결과

외부/내부 Normalize의 forward hook은 각각 실행 위치를 기록하고 반환값을 바꾸지 않았다. 외부 scale 직후, 모델 입력, 내부 preprocessor 출력, feature extractor 직전 입력을 clone해 통계만 저장했다. 실제 픽셀 배열이나 내부 절대경로는 기본 결과 파일에 저장하지 않았다.

| 입력 | A 관측 호출 순서 | B 관측 호출 순서 |
|---|---|---|
| SYN-001 | external → internal_export, **2회** | internal_export, **1회** |
| SYN-002 | external → internal_export, **2회** | internal_export, **1회** |
| SYN-003 | external → internal_export, **2회** | internal_export, **1회** |

세 입력 모두 scale 후 RGB Tensor는 A/B 정확히 같았고, A 모델 입력은 B 모델 입력에 ImageNet Normalize를 적용한 값과 정확히 같았다. B 모델 입력은0~1 float32 RGB BCHW, A는 이미 정규화된 BCHW였다. 내부 출력과 backbone 입력도 각 경로에서 정확히 같았다. 즉 계측된 범위에서 의도된 차이는 외부 Normalize 한 단계였다.

hook은 각 호출의 finally에서 해제했다. 호출 제한을 위한 임시 class forward 계수기도 finally에서 원복했고 process 종료 후 남지 않는다.

## 6. 기존 wrapper와 Path A 동등성

SYN-001에 대해 추가 기존 wrapper predict1회와 전체 계측 Path A1회를 비교했다. 추가 baseline에는 모델 입력을 읽는 pre-hook만 있었고 Normalize/feature/core 계측은 붙이지 않았다.

- 모델 전달 입력 Tensor: **정확히 일치**.
- 기존 wrapper score: **15.432870864868164**.
- 계측 Path A score: **15.432870864868164**, 절대 차이 **0.0**.
- anomaly_map: **array_equal=True**.

실행 전 정의한 score 허용오차는 rtol=1e-7, atol=1e-7이다. 동일 CPU float32 반복에 대해 상대 오차를 대략1 epsilon 수준으로 제한했고 Tensor/map은 오차 허용 없이 정확 일치를 요구했다. 실제 score도 정확 일치했다. 나머지2개 입력의 추가 무계측 반복은 호출 예산 절약을 위해 수행하지 않았다. Path A는 세 입력 모두 기존 predict를 직접 사용했다.

## 7. Tensor 통계 — OBSERVED

전체 모델 전달 Tensor 및 backbone 입력은 모두 `[1,3,256,256]`, torch.float32, CPU였다. scale 직후는 `[3,256,256]`이며 batch 추가 전이다. Resize 결과는 양쪽 모두256×256이다. std는 **전체 Tensor 원소에 대한 population std**이며 측정은 detach 후 float64로 집계했다.

### 모델 전달 직전

| 입력/경로 | min | max | mean | std |
|---|---:|---:|---:|---:|
| SYN-001 A | 0.074065 | 0.426493 | 0.235246 | 0.145440 |
| SYN-001 B | 0.501961 | 0.501961 | 0.501961 | 0.000000 |
| SYN-002 A | -2.117904 | 2.640000 | 0.226570 | 1.290712 |
| SYN-002 B | 0.000000 | 1.000000 | 0.500000 | 0.289805 |
| SYN-003 A | -2.117904 | 2.640000 | 0.226570 | 1.649598 |
| SYN-003 B | 0.000000 | 1.000000 | 0.500000 | 0.373262 |

### 내부 preprocessor 출력 = backbone 직전

| 입력/경로 | min | max | mean | std |
|---|---:|---:|---:|---:|
| SYN-001 A | -1.794478 | 0.091078 | -0.941041 | 0.780075 |
| SYN-001 B | 0.074065 | 0.426493 | 0.235246 | 0.145440 |
| SYN-002 A | -11.366392 | 9.928890 | -0.979441 | 5.729844 |
| SYN-002 B | -2.117904 | 2.640000 | 0.226570 | 1.290712 |
| SYN-003 A | -11.366392 | 9.928890 | -0.979441 | 7.276914 |
| SYN-003 B | -2.117904 | 2.640000 | 0.226570 | 1.649598 |

원래 합성 입력부터256×256이므로 이 실험은 크기가 다른 실제 이미지의 보간·antialias 차이를 검증하지 않는다. grayscale/alpha/16-bit 입력도 검증하지 않았다.

## 8. 실제 anomaly score 및 수학적 threshold 위치

상대 차이는 `abs(B-A)/abs(A)`다. 서버 final_result 또는 제품 정답을 생성하지 않았다.

| 입력 | A score | B score | 절대 차이 | 상대 차이 | A와34.1442 비교 | B와34.1442 비교 | 교차 |
|---|---:|---:|---:|---:|---|---|---|
| SYN-001 | 15.43287086 | 13.71425152 | 1.71861935 | 11.136096% | 이하 | 이하 | 아니오 |
| SYN-002 | 32.27065277 | 17.48858833 | 14.78206444 | 45.806524% | 이하 | 이하 | 아니오 |
| SYN-003 | 61.25930786 | 22.71374321 | 38.54556465 | 62.921972% | 초과 | 이하 | **예** |

모든 score는 finite였다. core hook score와 wrapper의 post 후 score는6건 모두 정확히 같았다. 후처리는 활성이나 image_min/image_max/_image_threshold가 NaN인 저장 상태였으며, 현재 라이브러리의 range 부재 처리와 일치한다. 이를 입력 Tensor/score의 NaN 발생으로 혼동하지 않는다.

**이 결과만으로 Path B가 우수하다는 뜻은 아니다.** 임의 합성 패턴의 점수가 내려갔고 한 패턴의 기준선 위치가 바뀌었다는 관측이다.

## 9. 실행 이력, 보호 검사 중단 및 호출 합계

출력 루트: `data/outputs/experiments/patchcore_synthetic_ab/`.

| 실행 | 결과 | 모델 로딩/추론 |
|---|---|---|
| diagnostic-01 | import 중 파일 보호 검사 STOPPED | 0 / 0 |
| import-diagnostic-01 | 원인 확인용 numpy/torch import, Windows NUL 접근 traceback 확보 | 0 / 0 |
| diagnostic-02 | 모델 로딩 및7회 추론·모든 측정 확보, 최종 UNEXPECTED_GUARD_ATTEMPT로 STOPPED | **1 / 7** |
| import-diagnostic-02 | import만 재현해 차단된 IPv6 probe 관측 | 0 / 0 |

### 첫 실행: Windows 환경 조회

torch import의 Windows DLL 로딩은 platform.machine→win32_ver→OS 버전 조회를 거치며 subprocess가 NUL을 열었다. 모든 실험 외부 쓰기를 막는 guard가 이를 거절했다. 실제 모델 로딩 전이었다. 새 script에서는 표준 라이브러리의 읽기 전용 `platform.uname()`을 guard 이전에 사전 조회해 cache를 준비했다. 운영 코드 수정이나 시스템 설정 변경은 없었고 파일·network 차단도 유지했다. 첫 실행 증거는 보존했다.

### 두 번째 실행: 최종 검사의 차단 사건

diagnostic-02의 guard 기록은 **network=1, forbidden_filesystem=0**이다. socket.connect/connect_ex/bind는 모두 실제 OS 연산 이전에 예외를 내도록 차단돼 있으므로, 이 카운트는 성공한 통신이나 API 요청 수가 아니다. 그러나 실행기는 “차단 시도도0이어야 함”이라는 최종 조건을 두어 exit1로 끝났다.

모델을 다시 로드하지 않는 import-only 재현에서는 `urllib3/util/connection.py:114`의 `_has_ipv6()`가 **IPv6 loopback bind(::1, port0)**를 시도했고 guard가 차단했다. 라이브러리는 예외를 잡고 import를 계속했다. 해당 소스의 `:127`은bind, `:137`은 import 시 capability probe다.

- **OBSERVED:** import-only 재현의 유일한 차단 사건은 이 IPv6 bind probe였다.
- **LIKELY:** diagnostic-02의1건도 같은 import probe일 가능성이 높다.
- **UNKNOWN:** 원래 diagnostic-02는 종류·call stack을 저장하지 않아 그1건의 원래 분류를 사후 확정할 수 없다.
- **CONFIRMED:** 실제 socket 연산은 차단 함수에서 진행되지 않았고 외부 네트워크 API 호출/Gemini 호출은 없다. guard를 해제하거나 네트워크 접근을 허용해 재시도하지 않았다.

이 제한 때문에 자동 실행 전체를 COMPLETE/PASS로 재분류하지 않고 **PARTIAL**로 보고한다. 기존 STOPPED metadata를 덮어쓰지 않았다. 비교 측정은 개별 검증을 통과했으며 별도 offline 검토로 JSON 및 계산 정합성을 확인했다.

### 호출 제한

추가 baseline1회 + 합성3종×A/B 각1회 = **논리적 PatchCore 추론7회**. Lightning/core/feature extractor 계수는 각각7이다. 이는 같은7개 호출 사슬의 중첩 경계이며21회 독립 추론이 아니다. 로딩 중 해당 경계의 예기치 않은 forward는 실행 전에 차단하도록 구성했고 실제 발생하지 않았다.

초기 실패·두 import 진단·단위/결과 검증은 모델 forward0회다. 전체 합계7≤12. 남은 예산을 이유로 전체7회 실험을 반복하면 상한을 넘기므로 반복하지 않았다. 모델 실행기의 process별 상한 외에 작업 전체 합계도 이 이력으로 확인했다.

## 10. 테스트 및 결과 검증

새 최소 단위 테스트는 실제 모델을 import·로딩·추론하지 않고 생성기·수학적 threshold 위치·비finite 거부·상대 차이/JSON 형식을 검증한다.

- 최초 단위 검증: **9 PASS, 0.15초**, 모델 forward0회.
- 최종 단위 검증: **9 PASS, 0.14초**, 모델 forward0회.
- 저장 결과의 별도 표준 라이브러리 검증: **PASS**. 입력3개/계측6건, 실제 Normalize 순서·횟수, CPU float32 shape, 통계 finite, core/post score 일치, score 차이·교차 산식, state fingerprint, wrapper 동등성, 운영 필드 비포함을 확인했다. 원래 STOPPED 상태도 보존되는지 확인했다.
- 전체 pytest/PostgreSQL/기존 모델 통합47건: **미실행**.
- 이전 전체1276 PASS /0 FAIL /51 SKIP은 과거 공식 결과이며 이번 결과가 아니다.

실행 명령:

```powershell
& 'C:/Users/USER/miniconda3/envs/vision-insight/python.exe' -B -m pytest tests/test_patchcore_synthetic_ab.py -q -p no:cacheprovider --basetemp=data/outputs/experiments/patchcore_synthetic_ab/unit-tests-02
& 'C:/Users/USER/miniconda3/envs/vision-insight/python.exe' -B scripts/experiments/compare_patchcore_synthetic_ab.py --run-name diagnostic-02
```

위 두 번째 명령은 이미 실행했고 exit1이었다. **그대로 재실행해 점수를 늘려 수집하지 말 것.** 추가 추론에는 별도 호출 예산 승인이 필요하다. timm/anomalib import deprecation 경고2건은 모델 오류나 새로운 성능 결과가 아니다.

## 11. 모델·운영 자산 보호

모델 state_dict 전체(parameter 및 buffer 포함)의 전후 SHA256:

`86fc668786331a8018bb55eb7024fc362a1820559356aabe718374fc9ff15e0b`

양쪽이 동일했다. memory bank를 포함하며 NaN buffer도 raw byte로 보존을 확인했다. embedding_store는 전후 비어 있고 모든 모델 모듈은 eval 상태였다. class 계수기/hook 외 모델 설정을 바꾸지 않았다. 파일 checkpoint는 쓰지 않았다.

기존237개 파일의 작업 전후 hash를 실제 비교해 **변경0건 / 누락0건**을 확인했다. 운영 전처리·학습·Calibration·threshold·검사/로그 JSONL·Agent·영상·DB 코드·기존 발표 및 병렬 작업 파일을 보호했다. 비교 대상 범위에 새로 추가된 것은 실험 스크립트·최소 테스트·보고서3개이며, 별도의 Git 무시 실험 출력만 생성했다.

이번 신규3개 파일 및 출력 summary.md의 공백 검사에서 진단0건, 줄 끝 공백0건이었다. `git diff --no-index --check -- NUL <신규파일>`의 exit1은 빈 파일과의 차이이며 공백 오류가 아니다. LF→CRLF 안내만 있었고 타 작업의 발표 문서는 수정하지 않았다.

- 운영 inspection_id/검사 API/최종 판정/JSONL append: **0건**.
- PostgreSQL 접속·ROI 데이터/스키마 변경·Docker/Volume 작업: **0건**.
- 실제 MVTec/Calibration/평가 이미지 및 Ground Truth 접근: **0건**.
- 실제 Gemini API 호출: **0회**.
- Git add/commit/push/reset/clean/restore: **0건**.
- 패키지 설치·가중치 다운로드·환경 영구 변경: **0건**.

보호 guard는 Python 파일/socket 계층의 실험 안전장치이며 완전한 OS sandbox라고 주장하지 않는다. 기존 자산의 전후 hash 검사와 실제 사용 경로 제한을 함께 적용했다.

## 12. 산출물

새 코드/문서:

- `scripts/experiments/compare_patchcore_synthetic_ab.py`: 생성기, 순수 wrapper 재사용 A/B, hook/호출 상한, 결과 및 보호 검사.
- `tests/test_patchcore_synthetic_ab.py`: 모델 호출 없는 최소9개 테스트.
- `docs/day5-step3-phaseb2b-r-synthetic-ab-results.md`: 본 보고서.

Git 무시 출력:

- diagnostic-01/experiment_metadata.json: 초기 STOPPED 기록.
- diagnostic-02/experiment_metadata.json: 실제 상태·호출 수·모델/입력 hash·transform·동등성·보호 실패 기록.
- diagnostic-02/tensor_statistics.json: 계측6건, 경계별 통계.
- diagnostic-02/score_comparison.json: score 및 수학적 기준선 비교3건.
- diagnostic-02/summary.md: 기존 측정값을 요약한 문서. STOPPED를 성공으로 바꾸지 않음.
- unit-tests-01/02와 import-diagnostic-01/02는 이번 실행 소유 격리 위치다. 기존 타 작업 임시 자료는 삭제하지 않았다.

## 13. 질문별 답변과 후속 승인

**Q1. 실제 Normalize 횟수가 다른가?** 예. 계측6건에서 A2회/B1회였다.

**Q2. Backbone Tensor가 달라지는가?** 예. 세 입력 모두 실제 통계 차이를 관측했다.

**Q3. Score도 변하는가?** 예. 세 입력 모두 변했고 SYN-003은 수학적 기준선을 교차했다. 성능 개선의 의미는 아니다.

**Q4. Path A가 기존 wrapper와 동등한가?** 기존 predict 자체를 호출했고 SYN-001 추가 비교에서 Tensor/score/map이 정확히 일치했다. 다른2종의 추가 무계측 반복은 미실행이다.

**Q5. Path B가 기술적 입력 계약을 만족하는가?** 시험한256×256 uint8 BGR 합성 입력 범위에서 예. RGB scale0~1 BCHW float32→내부 Resize/Normalize1회→CPU eval 모델을 만족했다. 일반 이미지·학습 당시 입력 완전 동등성·ROI 적합성까지 검증한 것은 아니다.

**Q6. 이 결과만으로34.1442를 재사용할 수 있는가?** **결론 불가**. 새 최적 threshold, 정상 score 분포, 불량 탐지 지표, Calibration 호환성 및 ROI 성능은 NOT TESTED다. 기존 threshold를 승인·폐기·재산출하지 않았다.

권장 순서:

1. 실험 보호 계측의 사건 분류를 보완하는 별도 승인: 실제 connect/API와 차단된 import capability probe를 구분해 기록하되, 네트워크 차단은 유지한다. 이번 실패 기록은 보존한다.
2. 원래 기준을 충족하는 실제 정상 개발 이미지가 확보되면, 명시 allowlist·출처·분할 비중복 근거를 승인받아 별도 제한 비교한다. 합성 패턴으로 이를 대체했다고 주장하지 않는다.
3. 필요시 독립Calibration29건의 읽기 전용 기존/후보 비교 범위·호출 예산을 별도 승인받는다. threshold 재계산·운영 metadata 수정은 자동으로 포함하지 않는다.
4. provenance 및 실제 이미지/Calibration 근거를 검토한 후 공식 전처리 변경 여부를 결정한다. 그 다음에야 AUTO/MANUAL 공통 ROI 입력 어댑터 연결을 별도 승인한다.

**현재 ROI→PatchCore 연결은 보류한다. 추가 추론·운영 수정 없이 이번 작업을 종료하고 사용자 승인을 기다린다.**

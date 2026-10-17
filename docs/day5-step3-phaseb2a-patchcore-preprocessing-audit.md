# Day5 Step 3 Phase B-2A — PatchCore Preprocessing Consistency Audit

작성일: 2026-10-17. **감사 작업: COMPLETE / 전처리 문제: UNRESOLVED / ROI 추론 연결: NOT IMPLEMENTED.**

## 1. 결론과 승인 경계

1. **CONFIRMED — 현재 소스의 호출 계약:** 학습은 ImageNet Normalize **1회**, calibration과 운영 wrapper는 **2회**다. 학습의 callback 기반 전처리와 운영의 전체 Lightning forward는 서로 다른 진입 경로다.
2. **CONFIRMED — 저장된 공식 checkpoint 설정:** 활성 pre_processor와 Resize256 → ImageNet Normalize 설정이 checkpoint 자체에 있다. 이번에는 모델을 생성·로딩하지 않고 ZIP 안의 pickle 명령을 정적으로 읽었다.
3. **LIKELY — 과거 실행:** 학습 1회 / calibration 2회 / 운영 2회의 **Case B**가 현존 소스·checkpoint·메타데이터에 가장 부합한다. 하지만 당시 실행 파일·라이브러리 fingerprint, callback 실행 trace, calibration run manifest가 없어 과거의 실제 횟수는 **UNKNOWN**으로 남긴다.
4. **Threshold provenance: PROVENANCE_PARTIAL.** 정상 180/29 분할, 공식 모델 연결 의도, 통계·선택식·저장값의 기록은 있다. calibration 실행 당시 checkpoint SHA256와 transform fingerprint를 함께 묶은 증거는 없다.
5. 지금 Normalize 하나를 제거하고 `34.1442`를 그대로 유효하다고 간주할 수 없다. **기존 경로 보존(Option D) → 격리된 외부 Normalize 제거 후보(Option A) 비교 → 공통 전처리 책임 정리(Option C)**를 권장한다. 이번에는 어느 대안도 구현하지 않았다.

실제 모델 추론, 이미지/Tensor 전처리 실험, calibration 재실행, 모델 재저장, threshold 변경, 검사 API 호출, pytest 실행, DB 연결·migration, Docker 조작 및 Gemini 호출은 **모두 수행하지 않았다**. 보고서만 새로 작성한다.

## 2. 문서·작업 트리·환경

작업 루트는 `C:\Users\USER\AI-NativeAgent\Project\InspectAgent`다. AGENTS.md 및 필수 문서 6개가 모두 존재했다.

- `docs/visioninsight-auto-manual-inspection-spec.md`
- `docs/visioninsight-tech-stack-decisions.md`
- `docs/day5-step3-phasea-roi-patchcore-audit.md`
- `docs/day5-step3-phaseb1-postgresql-roi-implementation.md`
- `docs/day5-step3-phaseb1-db-postgresql-roi-completion.md`
- `docs/day5-step3-phaseb1-db-regression-fix.md`

최우선 명세의 영상 미구현/1175 PASS, 초기 B-1의 BLOCKED, DB 구현 보고서의 과거 1 FAIL은 당시 상태다. 최신 회귀 보고는 **1276 PASS / 0 FAIL / 51 SKIP**이며 실제 모델 제외 47건과 T03 fixture 부재 4건을 포함한다. 이번 감사의 새 테스트 결과가 아니며 전처리 해결 증거도 아니다. 기존 문서를 수정해 이력을 지우지 않았다.

AUTO는 저장·승인·활성 ROI, MANUAL은 사용자 ROI를 사용하고 같은 모델·판정 정책으로 수렴한다. 이 요구사항, PostgreSQL ROI API, Grab/PNG/TTL 계약은 변경하지 않는다.

`git status --short` 및 현재 diff 목록을 확인했다. 기존 Agent·DB·영상·테스트·발표 자료 등의 수정/미추적 파일을 보존했다. backend/scripts/tests/docs/models에 별도 AGENTS.md는 없었다.

설치 배포 메타데이터를 `importlib.metadata.version()`으로만 읽었다: torch `2.6.0+cu124`, torchvision `0.21.0+cu124`, anomalib `2.7.0`, lightning `2.6.6`, timm `1.0.30`. torch/anomalib 모델 모듈은 import하지 않았다. 같은 버전 문자열이 과거와 일치하더라도 라이브러리 파일이 당시와 byte-identical하다는 증거는 아니다.

이하 `SITE/`는 `C:/Users/USER/miniconda3/envs/vision-insight/Lib/site-packages/`를 의미한다. 라이브러리 근거는 인터넷의 다른 버전이 아니라 설치된 파일의 읽기 전용 확인이다.

## 3. 공식 자산과 과거 기록

| 항목 | 공식 모델 | 과거 209장 모델 |
|---|---|---|
| checkpoint | `models/patchcore/patchcore_bottle.ckpt` | `models/patchcore/patchcore_bottle_all209.ckpt` |
| 파일 크기 | 25,354,538 bytes | 27,633,962 bytes |
| SHA256 | `4b239d28e72c63bf782cd1d31981d7f4362c591e7c23164e4c0ac8b5e99b52a3` | `a3c4ad78ea7c224cf2955705deb26522df589a8475623707e5a867254aaf1b20` |
| 기록상 학습/holdout | 180 / 29 | 209 / 독립 holdout 기록 없음 |
| memory bank 기록 | `[9216,384]` | `[10700,384]` |
| metadata created_at | 2026-10-14 17:55:56 | 2026-10-14 17:11:36 |
| 연결 metadata | `model_metadata.json` | `model_metadata_all209.json` |

공식 metadata의 backbone은 ResNet-18, layers는 layer2/layer3, coreset ratio는 0.05, 입력 크기는 256×256이다(`models/patchcore/model_metadata.json:7`, `:13`, `:18`, `:39`, `:40`). 현재 기본 checkpoint 설정은 `backend/config.py:80`, metadata는 `:81`, threshold는 `:83`에 있다. 환경설정으로 경로를 바꿀 수 있으므로 기본값만으로 과거 calibration 프로세스의 실제 선택을 증명하지 않는다.

**기록 간 혼동 위험:** all209 metadata의 `checkpoint_file`도 예전 이름 `patchcore_bottle.ckpt`로 남아 있다(`models/patchcore/model_metadata_all209.json:34`). `docs/patchcore-cpu-benchmark.md:40`은 209장과 `[10700,384]`, 평균 46.17ms의 과거 모델을 설명한다. 이 이름·수치를 현재 180장 모델과 혼합하지 않는다.

기존 공식 정적 평가 83장, AUROC 약 0.8286, Precision 100%, Recall 약 50.79%, 평균 모델 호출 42.53ms는 과거 보고 값이다. 이번에 재측정하거나 ROI/영상 성능으로 검증하지 않았다. 당시 평가의 성능 원인을 정규화 하나로 단정하지 않는다.

## 4. 학습 경로 — 현재 코드 CONFIRMED, 과거 실행 LIKELY

### 4.1 프로젝트 호출 그래프

```text
scripts/train_patchcore.py:36 train_patchcore()
  :54 dataset_split.json 읽기
  :57 train/val 파일 목록, :63 각 180/29 및 비중복 확인
  :68 정상 train 180장만 격리 디렉터리에 준비
  :102 anomalib.data.Folder(..., augmentation 지정 없음,
       normal_split_ratio=0, test_split=NONE, val_split=NONE)
  :122 Patchcore(resnet18, layer2/layer3, pre_trained=True, coreset=0.05)
       pre_processor를 끄거나 외부 Normalize를 추가하지 않음
  :131 Engine(..., max_epochs=1, limit_val_batches=0)
  :141 Engine.fit(model, datamodule)
  :160 생성 checkpoint를 공식 경로로 복사
  :175 학습 metadata 저장
```

스크립트는 전처리 설정을 metadata에 쓰지만(`:189`), 이것만으로 전처리를 수행하는 것은 아니다. 실제 실행 책임은 다음 library 경로에 있다.

### 4.2 Loader / callback / backbone 구분

```text
FolderDataset → AnomalibDataset.__getitem__
  SITE/anomalib/data/datasets/base/image.py:268
  → read_image(as_tensor=True)
    SITE/anomalib/data/utils/image.py:319
    PIL.open(...).convert("RGB")
    → to_image → to_dtype(float32, scale=True)
    → RGB float32 CHW, uint8 이미지의 경우 0~1
  → dataset augmentation: 모델의 Resize만 추출·추가
    SITE/anomalib/data/datamodules/base/image.py:198, :228
  → batch [N,3,256,256]
  → configure_callbacks에 등록된 PreProcessor.on_train_batch_start
    SITE/anomalib/models/components/base/anomalib_module.py:161
    SITE/anomalib/pre_processing/pre_processor.py:101, :111
    → transform: Resize256(antialias=True) + ImageNet Normalize 1회
  → Patchcore.training_step
    SITE/anomalib/models/image/patchcore/lightning_model.py:239, :255
    → self.model(batch.image) 〔내부 core 직접 호출〕
  → PatchcoreModel.forward → TimmFeatureExtractor
    SITE/anomalib/models/image/patchcore/torch_model.py:158, :164
  → feature pooling / layer embedding / embedding_store
    같은 파일 :166, :175
  → Patchcore.fit → subsample_embedding(0.05) → memory bank
    lightning_model.py:259, :266; torch_model.py:280
```

**중요:** datamodule이 모델 transform 전체를 dataset에 복제하는 것이 아니다. `extract_transforms_by_type(..., Resize)`만 추출하므로 추가 dataset Resize가 있어도 Normalize가 한 번 더 생기지 않는다. training_step은 전체 Lightning forward가 아닌 내부 core를 호출하므로 callback Normalize 뒤에 export_transform을 다시 호출하지 않는다. 모델 callback과 core 호출을 혼동하면 학습도 이중 정규화라고 잘못 판단하게 된다.

ResNet-18 특징 추출 진입 전에는 이미 `(u-mean)/std` 형태다. `SITE/anomalib/models/components/feature_extractors/timm.py:221`은 features_only 모델을 만들고 `:321`에서 입력을 그대로 전달한다. timm ResNet의 `SITE/timm/models/resnet.py:746`은 conv1부터 처리한다. 이 경로에 추가 ImageNet 이미지 Normalize는 보이지 않는다. BatchNorm 레이어는 별개 연산이며 여기서 세는 이미지 Normalize에 포함하지 않는다.

명시적 CenterCrop, padding, grayscale 변환 또는 추가 배치 Normalize는 현재 학습 경로에 없다. 256×256 Resize는 가로세로를 고정한다. 원본 이미지 실제 해상도·dtype 분포는 이미지를 읽지 않아 UNKNOWN이다.

### 4.3 과거 학습의 근거와 한계

- **CONFIRMED:** split metadata에는 seed 42, 총 209, train 180, val 29가 있다. 파일명 집합만 정적으로 비교했으며 각각 중복 0, 상호 겹침 0이다. 이미지 파일의 존재·내용 또는 실제 loader 소비 여부를 다시 검증한 것은 아니다.
- **CONFIRMED:** 공식 metadata에 학습 33.93초/GPU, memory bank shape, 생성 시각이 있고 checkpoint에 preprocessor 설정이 저장돼 있다.
- **CONFIRMED:** 관련 소스는 Git commit `4ef84b8`(2026-10-14 20:17:45+09:00)에 있으며 현재 해당 세 소스의 작업 트리 변경은 없다. commit 안의 Folder/Patchcore 및 calibration wrapper 호출도 동일한 구조다.
- **UNKNOWN:** 그 commit은 metadata 학습 시각 이후다. 당시 정확한 소스·설치 라이브러리 hash, 실제 callback 횟수, backbone 직전 Tensor trace를 고정한 실행 manifest는 확인하지 못했다. 학습 스크립트는 temp_engine을 정리하고 stdout을 자체 보관하지 않는다(`scripts/train_patchcore.py:164`). 조사한 경로에서 독립적인 당시 학습 stdout 기록을 확보하지 못했다.
- 따라서 **현재 소스의 1회 계약은 CONFIRMED**, 당시 실제 1회는 **LIKELY**다. 저장된 transform이 메모리 뱅크 생성의 모든 배치에 실제 적용됐음을 checkpoint 설정만으로 증명하지 않는다.

## 5. Calibration 경로와 threshold provenance

### 5.1 현재 코드 호출 그래프

```text
scripts/calibrate_threshold.py:31 calibrate_threshold()
  :43 split metadata → :46 val_files 29개
  :51 reset_patchcore_inferencer()
  :52 get_patchcore_inferencer() 〔기본 설정 경로, 환경변수 override 가능〕
  :58 memory_bank_shape == (9216,384) 확인
  :69 inferencer.predict(img_path)
    → PIL.open(path).convert("RGB")
    → 외부 Resize256 / ToImage / float32 scale / Normalize
    → 전체 Lightning model.forward
    → 내부 export_transform Resize256 / Normalize
    → core 특징 거리 → post_processor → output.pred_score
  :70 anomaly_score만 수집
  :80 mean, :81 sample std(ddof=1), min/max/percentiles
  :140 selected_threshold = round(max(score_max + 0.05, mu_plus_3sigma), 4)
  :178 metadata.calibrated_threshold 및 calibration 집계 기록
```

calibration은 `Engine.validate()`로 처리하는 것이 아니라 **운영과 같은 wrapper.predict()**를 호출한다. 경로 입력은 PIL RGB이고 운영은 ndarray BGR→PIL RGB지만, 그 이후의 외부·내부 정규화 경계는 같다. 같은 이미지의 PIL/OpenCV decode 및 Resize 결과까지 완전히 같은지는 NOT TESTED다.

### 5.2 34.1442 기록과 실제 선택식

`models/patchcore/model_metadata.json:45`와 `:46`에 threshold 및 calibration 집계가 있다. 기록값은 N=29, mean=31.0602, std=1.0280, min=29.7076, max=33.8527, 기록된 μ+3σ=34.1442, selected_threshold=34.1442다. 이 값들을 읽었을 뿐 이번에 점수·통계·threshold를 재계산하지 않았다.

**문서 요약과 코드의 차이:** 기존 문서의 “mean + 3 std”는 기록상 선택된 branch의 요약이다. 현재 코드의 일반 선택식은 **round(max(max_score+0.05, mean+3×sample_std),4)**다. `ddof=1`과 max+0.05 하한을 빼고 단순 μ+3σ만으로 재현하면 다른 calibration 집합에서 정책이 달라질 수 있다. 소표본의 3σ를 현장 99.7% 정확도 보장으로 해석하지 않는다.

### 5.3 Provenance 판정: PROVENANCE_PARTIAL

확인된 연결:

- seed/180/29 명세와 겹침 없는 파일명 집합.
- 공식 파일명, `[9216,384]` 확인 코드, 모델 버전 문자열 `PatchCore-ResNet18-180Train`.
- 현재 공식 파일 SHA256가 metadata의 `checkpoint_sha256`와 일치.
- calibration의 선택식·분포 집계·최종 값이 metadata 및 `docs/evaluation-results.md:12`에 남음.
- 현재/commit의 calibration이 동일한 wrapper.predict를 사용.

부족한 연결:

- calibration 실행 당시 checkpoint hash를 해당 run에 결합한 manifest와 실행 시각·코드 revision·라이브러리 hash.
- calibration 시 실제 변환 fingerprint 및 Normalize 실행 trace.
- 29개 개별 점수의 원본 실행 로그. 현재 스크립트는 stdout에만 개별 값을 출력하고 metadata에는 집계만 보관한다.
- 원본 calibration 이미지의 당시 content hash. 현재 감사는 이미지를 열지 않았다.
- 당시 환경변수 override 여부. memory bank shape만 같다고 같은 weights임이 증명되지는 않는다.

metadata의 현재 hash와 기록은 중요한 보조 증거지만 과거 calibration 실행 증명이 아니다. `docs/evaluation-results.md:8`의 별도 모델 버전 표기도 암호학적 식별자가 아니다. 과거 threshold가 **단일/이중 Normalize 중 어느 실행 결과였는지 확정할 수 없으므로** PROVENANCE_CONFIRMED로 올리지 않는다. 기록이 전혀 없는 것은 아니므로 UNKNOWN 전체로 분류하지도 않는다.

## 6. 운영 추론 호출 그래프

```text
backend/main.py:445 create_inspection_endpoint
  → registry / JSONL storage / get_patchcore_inferencer
  → backend/inspection.py:270 execute_inspection_workflow
    → ImageRegistry.get_path(:149)
    → cv2.imread(:404): 기본 COLOR, 통상 uint8 HWC BGR3
    → 품질 분석
    → inferencer.predict(image)(:508)
      backend/ml/patchcore_inferencer.py:174 _prepare_image
        :142 BGR→RGB → PIL
        :53 Resize256(PIL bilinear, antialias=True)
        :54 ToImage → :55 ToDtype(float32, scale=True)
        :56 ImageNet Normalize [1]
        :157 unsqueeze → device, [1,3,256,256]
      :178 self.model(input_tensor), torch.no_grad
        SITE/anomalib/models/components/base/anomalib_module.py:270
        → pre_processor.forward
          SITE/anomalib/pre_processing/pre_processor.py:164
          → export_transform: Resize256(antialias=False), Normalize [2]
        → 내부 core(:271) → feature_extractor → nearest neighbor / anomaly score
        → post_processor(:272)
      :182 output.pred_score → Python float
      :183 output.anomaly_map → ndarray
    → inspection.py:548 score > threshold → NG, score <= threshold → OK
    → backend/decision.py:28 determine_final_verdict
    → InspectionRecord 및 로그 저장
```

`_prepare_image()`는 파일/PIL을 RGB로, 2D ndarray를 RGB로 확장한다. 3채널 ndarray는 BGR로 가정한다. ndarray 4채널은 해당 분기에서 거절한다. 파일/PIL `convert("RGB")`와 기본 cv2 COLOR 로드는 alpha를 그대로 보존하는 계약이 아니다. float ndarray/16-bit 원본에 대한 범용 동일 scale 보장은 현재 계약에 없으므로 미래 ROI 어댑터에서 명시적으로 제한해야 한다.

timing은 `_prepare_image()` 이후의 모델 호출을 감싼다(`patchcore_inferencer.py:176`). 기존 42.53ms를 전체 HTTP/PNG/ROI 처리 시간으로 해석하지 않는다.

## 7. 체크포인트 안전한 정적 확인

### 7.1 방법

신뢰된 프로젝트 로컬 checkpoint 두 개에만 Python 표준 라이브러리 `zipfile`과 `pickletools.genops`를 사용했다. ZIP의 `archive/data.pkl` 한 항목만 최대 2 MiB 상한을 확인한 뒤 읽었다. `pickle.load`, `torch.load`, `load_from_checkpoint`, 모델 생성, Tensor 재구성 및 pickle GLOBAL/REDUCE 실행은 **하지 않았다**. 바이너리 metadata의 문자열·리터럴 opcode만 확인했으며 weight storage는 로딩하지 않았다.

관찰된 metadata 크기: 공식 25,932 bytes, all209 25,920 bytes. 각각 4,616개 opcode다. 텍스트 소스의 라인 번호 대신 아래는 공식 `archive/data.pkl`의 **byte offset** 근거다.

| 근거 | 공식 checkpoint 관찰 |
|---|---|
| offset 24735, hyper_parameters | resnet18, layer2/layer3, pre_trained=True, ratio=0.05, num_neighbors=9, precision=float32 |
| offset 25026 | anomalib_components_enabled: pre_processor=True, post_processor=True |
| offset 25161 | anomalib_pre_processor_config.transform = Compose |
| offset 25359 | Resize: size=[256,256], bilinear, max_size=None, antialias=True |
| offset 25535 | Normalize: mean=[0.485,0.456,0.406], std=[0.229,0.224,0.225], inplace=False |
| offset 25713 | post_processor config: normalization/thresholding/threshold_matching=True, sensitivities=0.5 |
| offset 40 | pytorch-lightning_version=2.6.6 |

all209에도 같은 종류의 transform과 활성 플래그가 있다. 그러나 memory bank와 모델 세대는 다르므로 calibration 대상으로 대체하지 않는다.

### 7.2 저장 설정과 실행 구성 연결

`SITE/anomalib/models/components/base/anomalib_module.py:201`의 on_load_checkpoint는 활성 플래그와 component config를 복원한다. `SITE/anomalib/pre_processing/pre_processor.py:208`은 spec을 transform으로 복원하고 export_transform을 만든다. `SITE/anomalib/pre_processing/utils/transform.py:50`은 복사 후 Resize antialias를 False로 만든다. 따라서 checkpoint의 antialias=True와 직접 forward의 export_transform=False를 구분해야 한다.

전회 B-1의 실제 로딩 진단은 동일한 공식 SHA에서 내부 transform/export_transform이 활성임을 확인했다(`docs/day5-step3-phaseb1-postgresql-roi-implementation.md:70`). 이번에는 로딩을 반복하지 않고 checkpoint의 정적 설정과 현재 복원 소스를 추가 확인했다. 이중 정규화의 기존 확인을 유지하되, 과거 학습의 모든 실행 상태까지 확인했다고 주장하지 않는다.

### 7.3 score 후처리는 별도의 책임

wrapper는 core의 거리값이 아니라 **전체 forward 후 pred_score**를 반환한다. checkpoint의 post_processor는 활성이고 `SITE/anomalib/post_processing/post_processor.py:268`은 내부 min/max 등으로 score를 정규화할 수 있다. `:374`부터 `:382`는 range 정보가 없으면 입력 score를 유지한다. 이는 ImageNet 입력 Normalize와 별도 처리다.

이번에는 post_processor의 Tensor buffer값이나 실제 출력을 평가하지 않았으므로 현재 출력을 무조건 “생 거리값” 또는 “0~1 점수”라고 단정하지 않는다. 후보 비교에서 core만 호출하면 후처리까지 달라진다. 다음 검증에서는 **core 전 Tensor / core score / post 후 score**를 분리해 관찰해야 한다.

## 8. 학습·Calibration·운영 추론 비교표

“현행”은 소스와 저장 설정을 연결한 정적 계약, “당시”는 과거 실행의 확정도를 의미한다.

| 검사 항목 | 학습 | Calibration | 운영 추론 |
|---|---|---|---|
| 이미지 Loader | Folder/AnomalibDataset/read_image | wrapper에 path→PIL | registry→cv2.imread→ndarray→PIL |
| RGB/BGR | PIL RGB | PIL RGB | BGR→RGB |
| Resize | float Tensor의 dataset Resize + callback Resize256 | 외부 PIL256 + 내부 Tensor256 | 외부 PIL256 + 내부 Tensor256 |
| ToTensor 상당 | to_image/to_dtype, float32 scale=True | ToImage/ToDtype, float32 scale=True | 동일, BCHW 추가 |
| 외부 Normalize | 명시적 추가 없음, dataset도 Resize만 | wrapper에서 1회 | wrapper에서 1회 |
| 내부 Normalize | train callback transform에서 1회 | 전체 forward export_transform에서 1회 | 동일 |
| 총 Normalize 횟수 | **현행 1 / 당시 UNKNOWN(1이 LIKELY)** | **현행 2 / 당시 UNKNOWN(2가 LIKELY)** | **현재 2 CONFIRMED / 과거 개별 run은 UNKNOWN** |
| 모델 호출 인터페이스 | Engine.fit→training_step→core | wrapper.predict→전체 Lightning | wrapper.predict→전체 Lightning |
| Backbone 입력 | RGB float32, N(u) 계약 | RGB float32, N(N(u)) 계약 | 동일 |
| 실행 당시 근거 | 학습 metadata, 저장 transform, commit | calibration 집계·분할 metadata, script, commit | 현행 소스, 전회 구성 진단, 저장 transform |
| 실행 당시 부족 | callback trace/라이브러리 hash 등 | run에 결합한 hash/transform/개별 score 등 | 당시 모든 run의 전처리 fingerprint |

현행 횟수는 정적 경로 확인이며 이번에 Tensor를 통과시켜 계측한 값이 아니다. 역사적으로 Case A/C를 절대 배제할 수 있다고 주장하지 않는다.

**Q1 — 세 경로는 같은가?** 현행 코드는 **NO**. 학습 1회와 calibration/운영 2회가 다르다. 과거 모든 실행의 일치성은 **UNKNOWN**. calibration과 운영의 같은 wrapper 사용은 확인되지만 decode/보간까지 bit-identical인지는 NOT TESTED다.

**Q2 — 모델이 기대하는 올바른 입력인가?** 저장 preprocessor와 ImageNet 사전학습 backbone은 0~1 RGB에서 1회 Normalize하는 계약을 뒷받침한다. 현재 이중 경로는 그 설계와 일치하지 않는다. 한편 실제 memory bank 생성과의 수치 정합성, threshold 유효성은 **미검증**이다. 단일화하면 기존 모델 품질이 회복된다고 단정하지 않는다.

## 9. 정규화 수식과 기술적 영향

확인한 mean=(0.485,0.456,0.406), std=(0.229,0.224,0.225)다. u를 uint8에서 scale한 RGB의 한 성분이라 하면:

```text
N(u)    = (u - mean) / std
N(N(u)) = ((u - mean) / std - mean) / std
        = u/std^2 - mean/std^2 - mean/std
```

두 식은 일반적으로 다르다. u∈[0,1]이면 단일 구간은 [-mean/std, (1-mean)/std], 이중 구간은 그 양 끝에 다시 N을 적용한 구간이다. 이는 **수식에 따른 입력 범위 설명**이지 실제 이미지 Tensor나 score를 계산한 결과가 아니다.

- 학습 memory bank가 N(u), 추론 특징이 N(N(u))에서 유래하면 backbone 입력과 정상 특징 거리의 정합성이 깨질 위험이 있다.
- CNN 비선형·pooling·nearest neighbor·가중 score·후처리가 있으므로 score가 반드시 상승/하락하거나 차이가 일정하고 정확도가 몇 % 개선된다는 결론은 낼 수 없다.
- calibration도 이중이면 운영과 같은 구현 단위에서 threshold를 설정했을 가능성은 있다. 정상 29건의 정합성은 학습 특징과의 일치나 이상 검출 성능을 보장하지 않는다.
- 기존 `verify_compatibility()`는 hash/shape/threshold 수치 대조이며 전처리 의미나 단일화 후 threshold 재사용을 증명하지 않는다(`backend/ml/patchcore_inferencer.py:91`).
- 과거 검사 기록·평가값·Day4 E2E는 당시 출력으로 보존한다. 오류로 간주해 덮어쓰거나 원인 확정 없이 판정을 뒤집지 않는다.

## 10. 수정 대안 — DESIGN PROPOSAL, 미구현

| 대안 | 장점 | 주요 위험/변경 범위 | 판단 |
|---|---|---|---|
| A 외부 Normalize 제거 | wrapper 최소 변경, 내부 1회로 수렴, checkpoint 유지 | calibration/score/threshold 변화 가능. PIL Resize와 학습 Tensor Resize 차이 잔존 | **첫 격리 후보**. 외부 Normalize만 바꿔 원인 분리 |
| B 내부 Normalize 비활성화 | 현행 외부 처리 유지 가능 | component 및 다른 호출자에 영향. pre_processor 전체를 끄면 Resize 등도 변경됨 | 첫 후보로 비권장. 필요시 process 내부 한정, checkpoint 쓰기 금지 |
| C 공통 전처리 어댑터 | AUTO/MANUAL/향후 calibration 책임 일원화 | 호출 경계·Resize·dtype·후처리·이력 호환의 검증 범위 증가 | **최종 설계 방향**. 격리 실험 후 별도 승인 |
| D 공식 경로와 격리 후보 병존 | 기존 checkpoint/threshold/기록 보호, 비교·rollback 명확 | 두 경로 식별 및 검증 출력 격리 필요 | **다음 단계 진행 방식으로 권장**. 운영 자동 전환 없음 |

**최소 변경 권고:** 운영 wrapper를 지금 수정하지 않는다. D로 공식 경로를 고정하고 A만 적용한 검증 전용 후보를 별도 process에 둔다. 내부 Lightning·post_processor·checkpoint·threshold는 공통으로 유지한다. 색상/Resize를 동시에 바꾸면 원인을 분리할 수 없다.

이후 C로 **입력 경계는 색상 순서·dtype·scale, 모델 측은 Resize/Normalize를 명시적으로 1회 담당**하는 설계를 검토한다. A 최소 후보에는 PIL Resize가 남으므로 최종 C와 완전한 동일성을 가정하지 않는다. 학습 Tensor Resize/antialias=True와 export 경로의 False 차이도 별도 인자로 검증한다. 단일 Normalize만으로 학습 입력과 완전히 같아졌다고 선언하지 않는다.

## 11. 후속 격리 비교 실험 — 설계만 수행

### 11.1 사전 승인 및 데이터 단계

| 단계 | 데이터/작업 | 결론 가능한 범위 |
|---|---|---|
| E0 | 중립적 색·계조 등의 새 합성 입력, 전처리만 조사 | dtype/색순서/Normalize 횟수/Resize 경계. 실제 모델 검출 품질은 알 수 없음 |
| E1 | 명시 승인된 정상 정적 이미지 3～5건을 중립 ID로 고정, 공식 checkpoint 읽기 전용 비교 | 동일 입력의 Tensor/feature/score/판정 차이. 분포·threshold의 충분한 검증은 아님 |
| E2 | 별도 승인으로 독립 calibration29건 전체를 기존 split 그대로 비교 | Path A의 기존 집계 정합성 및 Path B와의 차이. 정상 데이터만으로 검출 성능 판단 불가 |
| E3 | 필요시 추가 승인된 독립 평가 계획 | 정답 기반 성능 평가는 이번 권한·작업에 포함되지 않음 |

E1/E2의 **모델 로딩·추론, 대상 이미지 사용, 검증 코드 작성**은 다음 승인이 필요하다. calibration29건 사용 목적은 기존 경로 재현성과 후보 비교이지, 기존 calibration 스크립트를 실행해 metadata를 쓰는 것이 아니다. 재보정/threshold 변경은 추가 독립 승인 사항이다. 이번에는 어느 단계도 실행하지 않았다.

### 11.2 고정할 두 경로

- **Path A / Existing:** 현재 공식 wrapper, 외부＋내부 Normalize. 먼저 소스·checkpoint·metadata·split·라이브러리 hash 및 후처리 설정을 manifest에 고정한다.
- **Path B / Candidate:** 같은 소스 기준에서 **외부 Normalize만 제거**한 검증 전용 어댑터. 내부 transform/post_processor는 동일하게 유지한다. 공식 파일을 덮어쓰지 않고 별도 process로 구별한다.
- core만 직접 호출하거나 모델 재저장, train/eval 상태 변경, score 후처리 해제, threshold 조정을 동시에 하지 않는다. 후처리 buffer의 초기 상태도 같은지 확인한다.

### 11.3 관찰 지점과 출력

1. 입력 중립 ID/content hash, 색순서/dtype/shape, 획득 출처와 허용 범위를 기록한다.
2. 색변환 직후, 외부 변환 직후, 내부 전처리 직후, backbone 직전의 shape/dtype/device/finite/min/max/mean/std 및 fingerprint를 기록한다. forward hook 등은 검증 process 내부 한정이다.
3. Normalize 개수는 모듈 개수뿐 아니라 실제 호출로 계측한다. 학습 callback 경로의 전처리 재현은 실제 재학습과 구분하고 재학습하지 않는다.
4. layer2/layer3 특징 통계와 필요시 고정 memory bank와의 거리 요약을 관찰한다. 특징 차이만으로 검출 품질을 단정하지 않는다.
5. **core score와 post 후 score를 모두** 기록한다. 공식 API anomaly_score와 비교할 경계는 동일한 post 후다. 후처리가 실제 무변환인지도 확인한다.
6. 이미지별 A/B score 차이, 동일 경로 반응 반복성, 고정34.1442에 대한 판정 차이를 기록한다. 기존 strict `>`, 동점 OK 경계를 유지한다.
7. E2에서 Path A 분포를 기존 집계 기록과 대조한다. 반올림 전 개별 점수 부재의 한계를 기록하고 불일치하면 provenance 문제로 중단한다. 향후 수치 허용오차는 dtype/CPU 재현성에 근거해 실험 전에 정하고 결과에 맞춰 사후 변경하지 않는다.
8. Path B의 값 변화는 본래 비교 대상이므로 실패로 숨기지 않는다. 변화가 작거나 정상29건이 threshold를 넘지 않았다는 것만으로34.1442 재사용을 승인하지 않는다.

### 11.4 격리·중단·채택 기준

- 유일한 시험 디렉터리 예 `data/outputs/preprocessing-validation/<run-id>/`에 manifest/metrics를 저장한다. 기존 증거를 덮어쓰지 않는다. 이는 설계 예시이며 이번에 생성하지 않았다.
- 공식/실험 checkpoint·metadata·split, 운영 JSONL 및 기존 영상의 전후 hash를 확인한다. 평가 원본을 대량 해싱하지 않는다.
- 단독 스크립트의 순수 predict 비교로 제한한다. FastAPI 검사 workflow, inspection ID 발급, JSONL storage, Agent, DB, Grab session에 연결하지 않는다. 외부 통신·다운로드를 차단한다.
- 실제 원본 경로·클래스명·비밀정보를 출력/API/Agent에 전달하지 않고 중립 ID와 content hash로 기록한다. 실험 출력을 공식 검사 기록으로 취급하지 않는다.
- hash 불일치, 외부 통신/쓰기, 후보의 여러 동시 변경, 비finite, 후처리 차이, 입력 manifest 차이 또는 자원 문제가 있으면 중단한다. 운영 경로를 교체하지 않는다.
- score 방향·정확도 개선·threshold 재사용은 **결과를 검토해 별도 심사**한다. 재보정/재학습이 필요한지 여부도 이번 감사만으로 결정하지 않는다.

## 12. 후속 ROI 공통 입력 어댑터 — PROPOSED

```text
AUTO: 승인·active ROI snapshot ─┐
                               ├→ 원본/소유권/TTL/revision/ROI 검증
MANUAL: 사용자 ROI snapshot ───┘
  → uint8 HWC BGR ROI 배열〔원본 pixel 좌표, crop만〕
  → 공통 입력 경계: BGR→RGB, CHW float32 scale, batch
  → 명시한 Resize/Normalize 책임 주체〔Normalize 총1회〕
  → 같은 공식 checkpoint / Lightning 및 후처리
  → 같은 score/34.1442 경계/최종 판정/저장
```

이는 후보 비교와 정식 채택 이후의 설계이며 현행 구현을 바꾼 것이 아니다. crop 원본 해상도·ROI 크기는 가변이고 모델 입력256×256은 별도 전처리 책임이다. Resize 비율 왜곡·PIL/Tensor 보간·antialias·grayscale 확장·alpha 거절 정책을 fingerprint와 함께 고정한다. 이미 정규화된 Tensor를 raw0~1 경계에 넣어서는 안 된다.

추적 후보: 원본 capture_id/image_id, 원본 hash/size, video revision/frame index, ROI 좌표와 preset version, crop hash/size, checkpoint hash, preprocessing contract revision, score/postprocess revision, 사용 threshold. capture_id와 image_id는 별도 식별자로 유지한다.

ROI 관리 승인은 모델 적합성·성능 승인이 아니다. PostgreSQL 버전/승인/active binding, Grab PNG/소유 session/TTL은 이번 감사와 독립적으로 유지된다. 코드·DB·이미지를 바꾸지 않았으며 새로운 호환성 테스트도 실행하지 않았다. ROI 적용·실제 추론 연결은 계속 보류한다.

## 13. 정적 검증·자산 보호·남은 항목

실행한 명령 범위:

- `git status --short`, `git diff --name-only`, 관련 소스의 `git log`/`git show`.
- PowerShell 번호 기반 소스·metadata·기존 문서 읽기.
- `python -B -` 표준 라이브러리만으로 AST 문법 확인, split metadata 집합 확인, 설치 배포 버전 참조, ZIP/pickle opcode 읽기. GLOBAL/REDUCE 명령을 실행하지 않음.
- 시작 시 기존 파일235개 SHA256 기록 및 종료 비교. 소스/기존 문서/모델/운영 JSONL/영상/병렬 작업 파일 대상이며 데이터셋 이미지 대량 읽기 없음.
- 신규 보고서 공백 검사 및 종료 Git 상태 확인.

train/calibration/inferencer 3개 소스는 `ast.parse` 성공. 이는 실행이나 pytest가 아니다. **이번 pytest는 단일·전체 모두0회**, 전처리에 Tensor/이미지를 통과시키는 실험도0회다.

보호 결과: 기존235개 파일 변경·누락 없음, 이 보고서1개만 추가. 운영 JSONL, checkpoint2개, threshold, H.264, 기존 테스트, DB 코드/migration, 발표·타 에이전트 변경을 보존했다. DB 연결·Docker 작업, 캡처 PNG 생성/삭제, 외부 Ground Truth 읽기·목록 조회를 하지 않았다.

신규 보고서의 `git diff --no-index --check -- NUL <보고서>`에서 공백 오류 진단은 없었고, 줄 끝 공백 검사도 0건이었다. exit 1은 빈 파일과 신규 파일의 차이를 의미하며 공백 오류가 아니다. LF→CRLF 안내만 있었다. 다른 에이전트의 기존 발표 문서를 수정하거나 전체 diff의 무관한 공백 문제를 정리하지 않았다.

**NOT TESTED / UNKNOWN:** 과거 실제 batch Tensor/모든 callback trace, calibration의 완전한 run provenance, 후처리 buffer 실제값, 단일/이중 score 변화,34.1442 후보 재사용 가능성, 정적 평가에 대한 인과 영향, ROI 도메인 적합성·정확도, 브라우저 표시와 Grab의 픽셀 동기화.

다음 승인 대상은 E0/E1의 **격리 검증 코드 작성 및 제한적인 실제 모델 비교**, 대상 데이터·건수·출력 경로다. calibration29건 비교는 E2로 별도 명시 승인을 받는다. 공식 전처리 변경·재보정·threshold 변경·ROI 추론 연결까지 자동 승인된 것으로 해석하지 않는다.

**감사는 여기서 종료한다. 모델 문제는 UNRESOLVED이며 다음 사용자 승인을 기다린다.**

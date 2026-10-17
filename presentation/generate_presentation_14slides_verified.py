"""VisionInsight 기술 발표 자료 14장 최종 검증본 생성 스크립트
(14-Slide Verified Final Presentation with Day4 Completion & pytest 1089 PASS)

주요 작업:
1. 최신 Day4 최종 검증 결과 반영:
   - 전체 pytest 1089 PASS / 0 FAIL / 4 SKIP (경고 2건)
   - 4대 대표 시나리오 실제 Gemini E2E 전원 성공(PASS) 기록 확인:
     • T01 정상 (INSP-001396): 13.578초, 관측 사실 6개 PASS
     • T03 조도 경고 (INSP-001398): 24.600초, 관측 사실 12개 PASS
     • T05 로드 실패 (INSP-001405): 16.333초, 관측 사실 17개 PASS (조기 종료 성공)
     • T06 저장 OK (INSP-001406): 26.371초, 관측 사실 6개 PASS (판정 불변 OK 유지)
   - T06 10단계 개발 과정(504 극복 및 30초 적용)과 한계(30초 직접원인 미확정, 원본 ASGI 미보관) 반영
2. Slide 1 (표지): 최신 1089 PASS / 4대 시나리오 E2E 전원 성공 반영
3. Slide 4 (Vision 엔진): Recall 50.79%, FN 31건 미탐 한계 및 평가 문서 제약사항 보존
4. Slide 7 (Evidence 검증): 4대 시나리오 관측 사실 100% 결정적 검증 반영
5. Slide 9 (핵심 기술 난제): HTTP 400, HTTP 504 분리 계측, T05 조기종료/T06 불변성 완결 반영
6. Slide 10 (실제 E2E 결과): 4대 시나리오(T01, T03, T05, T06) 4열 비교 및 실측 수치 전면 반영
7. Slide 12 (구현 현황): 1단(Day4 완료), 2단(Day5 계획 분리), 3단(Day6~7 로드맵) 3단 체계 동기화
8. Slide 13 (엔지니어링 한계): 모델 미탐, 504 원인 UNKNOWN 및 30초 한계, 설비 미연동 및 사후 진단 한정
9. 산출물: presentation/VisionInsight_Presentation_14slides_verified.pptx
"""

import os
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE

def create_presentation_14slides_verified():
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank_layout = prs.slide_layouts[6]

    # Color Palette (Industrial Dark Navy & High Contrast Accents)
    BG_COLOR = RGBColor(12, 19, 34)          # #0C1322
    CARD_BG = RGBColor(22, 30, 46)           # #161E2E
    CARD_BG_ALT = RGBColor(16, 23, 38)       # #101726
    CARD_BORDER = RGBColor(42, 54, 73)       # #2A3649
    PRIMARY_CYAN = RGBColor(76, 215, 246)    # #4CD7F6
    SUCCESS_GREEN = RGBColor(52, 211, 153)   # #34D399
    WARNING_AMBER = RGBColor(251, 191, 36)   # #FBBF24
    DANGER_CORAL = RGBColor(248, 113, 113)   # #F87171
    TEXT_WHITE = RGBColor(248, 250, 252)     # #F8FAFC
    TEXT_LIGHT = RGBColor(203, 213, 225)     # #CBD5E1
    TEXT_MUTED = RGBColor(148, 163, 184)     # #94A3B8

    FONT_FAMILY = "Malgun Gothic"

    def set_slide_background(slide):
        bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), prs.slide_width, prs.slide_height)
        bg.fill.solid()
        bg.fill.fore_color.rgb = BG_COLOR
        bg.line.color.rgb = BG_COLOR
        return bg

    def add_header(slide, title_text, category_text="VISIONINSIGHT  |  INDUSTRIAL VISION AI AGENT", subtitle_text=None):
        cat_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.36), Inches(11.7), Inches(0.25))
        tf = cat_box.text_frame
        tf.word_wrap = True
        tf.margin_top = tf.margin_bottom = tf.margin_left = tf.margin_right = 0
        p = tf.paragraphs[0]
        p.text = category_text
        p.font.name = FONT_FAMILY
        p.font.size = Pt(10)
        p.font.bold = True
        p.font.color.rgb = PRIMARY_CYAN

        title_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.62), Inches(11.7), Inches(0.68))
        tf_t = title_box.text_frame
        tf_t.word_wrap = True
        tf_t.margin_top = tf_t.margin_bottom = tf_t.margin_left = tf_t.margin_right = 0
        p_t = tf_t.paragraphs[0]
        p_t.text = title_text
        p_t.font.name = FONT_FAMILY
        p_t.font.size = Pt(20)
        p_t.font.bold = True
        p_t.font.color.rgb = TEXT_WHITE

        if subtitle_text:
            p_sub = tf_t.add_paragraph()
            p_sub.text = subtitle_text
            p_sub.font.name = FONT_FAMILY
            p_sub.font.size = Pt(11)
            p_sub.font.color.rgb = TEXT_LIGHT
            p_sub.space_before = Pt(2)

    def add_card(slide, left, top, width, height, bg_color=CARD_BG, border_color=CARD_BORDER):
        shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
        shape.fill.solid()
        shape.fill.fore_color.rgb = bg_color
        shape.line.color.rgb = border_color
        shape.line.width = Pt(1)
        return shape

    # ==========================================
    # SLIDE 1: Title Slide (Updated to 1089 PASS & 4 E2E PASS)
    # ==========================================
    s1 = prs.slides.add_slide(blank_layout)
    set_slide_background(s1)

    add_card(s1, Inches(0.8), Inches(1.1), Inches(11.733), Inches(5.4), bg_color=CARD_BG_ALT, border_color=PRIMARY_CYAN)

    tbox = s1.shapes.add_textbox(Inches(1.4), Inches(1.7), Inches(10.5), Inches(2.2))
    tf = tbox.text_frame
    tf.word_wrap = True
    p0 = tf.paragraphs[0]
    p0.text = "VisionInsight"
    p0.font.name = FONT_FAMILY
    p0.font.size = Pt(44)
    p0.font.bold = True
    p0.font.color.rgb = PRIMARY_CYAN

    p1 = tf.add_paragraph()
    p1.text = "AI 기반 병 외관 이상 탐지 및 근거 기반 진단 시스템"
    p1.font.name = FONT_FAMILY
    p1.font.size = Pt(20)
    p1.font.bold = True
    p1.font.color.rgb = TEXT_WHITE
    p1.space_before = Pt(8)

    p2 = tf.add_paragraph()
    p2.text = "MVTec Bottle 기반 PatchCore 이상 탐지와 Gemini Function Calling의 결합"
    p2.font.name = FONT_FAMILY
    p2.font.size = Pt(13)
    p2.font.color.rgb = TEXT_LIGHT
    p2.space_before = Pt(10)

    bbox = s1.shapes.add_textbox(Inches(1.4), Inches(4.5), Inches(10.5), Inches(1.6))
    tf_b = bbox.text_frame
    tf_b.word_wrap = True
    bp0 = tf_b.paragraphs[0]
    bp0.text = "핵심 기술 스택: Python 3.11  |  FastAPI  |  PyTorch/PatchCore  |  Gemini 3.8 Flash (Function Calling)"
    bp0.font.name = FONT_FAMILY
    bp0.font.size = Pt(12)
    bp0.font.bold = True
    bp0.font.color.rgb = PRIMARY_CYAN

    bp1 = tf_b.add_paragraph()
    bp1.text = "검증 완료: 단일 이미지 CPU 추론 평균 42.53ms  |  4대 시나리오 실제 Gemini E2E 성공 (T01/T03/T05/T06 PASS)  |  전체 pytest 1089 PASS / 4 SKIP (경고 2건)"
    bp1.font.name = FONT_FAMILY
    bp1.font.size = Pt(11)
    bp1.font.color.rgb = TEXT_MUTED
    bp1.space_before = Pt(6)

    bp2 = tf_b.add_paragraph()
    bp2.text = "발표일: 2026년 10월 20일  |  발표자: VisionInsight 개발팀"
    bp2.font.name = FONT_FAMILY
    bp2.font.size = Pt(11)
    bp2.font.color.rgb = TEXT_LIGHT
    bp2.space_before = Pt(10)

    # ==========================================
    # SLIDE 2: Executive Summary & Problem
    # ==========================================
    s2 = prs.slides.add_slide(blank_layout)
    set_slide_background(s2)
    add_header(s2, "산업 비전 검사의 과제와 VisionInsight의 접근법")

    # Left Card: Traditional Rule/Deep Learning Limits
    add_card(s2, Inches(0.8), Inches(1.4), Inches(5.7), Inches(5.3), border_color=DANGER_CORAL)
    tb_l = s2.shapes.add_textbox(Inches(1.1), Inches(1.65), Inches(5.1), Inches(4.8))
    tf_l = tb_l.text_frame
    tf_l.word_wrap = True
    p = tf_l.paragraphs[0]
    p.text = "기존 산업용 비전 검사의 한계"
    p.font.name = FONT_FAMILY
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = DANGER_CORAL

    limits_points = [
        ("단순 흑백 판정의 부작용", "OK/NG 이분법 판정으로 인해 조도 변화나 먼지 등 환경적 요인 발생 시 과도한 불량(False Alarm) 발생"),
        ("불투명한 원인 분석", "검사기가 불량을 통보해도 원인(조명 문제인지, 실제 제품 파손인지)을 작업자가 즉각 파악하기 어려움"),
        ("단순 LLM 도입의 위험성", "외부 생성형 AI 모델을 검사 제어에 직접 연결할 경우 환각(Hallucination) 및 판정 변복 위험 상존")
    ]
    for title, desc in limits_points:
        p = tf_l.add_paragraph()
        p.text = "• " + title
        p.font.name = FONT_FAMILY
        p.font.size = Pt(12)
        p.font.bold = True
        p.font.color.rgb = TEXT_WHITE
        p.space_before = Pt(10)
        p_d = tf_l.add_paragraph()
        p_d.text = "   " + desc
        p_d.font.name = FONT_FAMILY
        p_d.font.size = Pt(10)
        p_d.font.color.rgb = TEXT_LIGHT

    # Right Card: VisionInsight Approach
    add_card(s2, Inches(6.8), Inches(1.4), Inches(5.7), Inches(5.3), border_color=PRIMARY_CYAN)
    tb_r = s2.shapes.add_textbox(Inches(7.1), Inches(1.65), Inches(5.1), Inches(4.8))
    tf_r = tb_r.text_frame
    tf_r.word_wrap = True
    p = tf_r.paragraphs[0]
    p.text = "VisionInsight 핵심 해결 전략"
    p.font.name = FONT_FAMILY
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = PRIMARY_CYAN

    solutions_points = [
        ("PatchCore 기반 이상 탐지", "정상 이미지 180장만으로 학습, 개발 환경 CPU 단일 이미지 PatchCore 추론 평균 42.53ms 측정"),
        ("재검사(REINSPECT) 규칙 분리", "조도 저하 등 영상 품질 경고 시 제품 불량(NG)과 구분하여 '재검사 필요'로 처리하는 결정 규칙 수립"),
        ("Gemini Function Calling 진단", "Gemini가 Function Calling으로 조회를 요청하면, 서버가 허용된 Python 도구를 검증·실행하여 실제 검사 근거를 수집"),
        ("판정 불변 가드레일", "Gemini는 사후 진단 보조만 수행하며, 서버가 확정한 판정(final_result)을 절대 변경할 수 없음")
    ]
    for title, desc in solutions_points:
        p = tf_r.add_paragraph()
        p.text = "✔ " + title
        p.font.name = FONT_FAMILY
        p.font.size = Pt(12)
        p.font.bold = True
        p.font.color.rgb = SUCCESS_GREEN
        p.space_before = Pt(8)
        p_d = tf_r.add_paragraph()
        p_d.text = "   " + desc
        p_d.font.name = FONT_FAMILY
        p_d.font.size = Pt(10)
        p_d.font.color.rgb = TEXT_LIGHT

    # ==========================================
    # SLIDE 3: System Architecture
    # ==========================================
    s3 = prs.slides.add_slide(blank_layout)
    set_slide_background(s3)
    add_header(s3, "시스템 아키텍처: 계층 분리와 단방향 책임 설계")

    layers = [
        ("1. Vision Core Layer",
         PRIMARY_CYAN,
         "OpenCV 이미지 전처리 & 품질 분석 (밝기 81.24/135.86 등)",
         "PatchCore Anomaly Detection Engine (ResNet-18)",
         "개발 환경 CPU 단일 이미지 PatchCore 추론 평균: 42.53ms 측정 (※ 순수 모델 추론 시간)"),

        ("2. Decision Layer (FastAPI)",
         WARNING_AMBER,
         "독립 검사 식별자 발급 (INSP-001396 등)",
         "결정 규칙 기반 종합 판정 (OK / NG / REINSPECT / ERROR)",
         "품질 이상 시 모델 결함과 분리하여 'REINSPECT' 분류"),

        ("3. Storage & Audit Layer",
         TEXT_LIGHT,
         "검사 결과(data/inspections.jsonl) 및 실행 이벤트(data/inspection_logs.jsonl) 로컬 기록",
         "inspection_id 기반 추적 및 Evidence ID(E0001, E0002) 자동 발급",
         "평가 Ground Truth와 운영 데이터 엄격 분리 (※ 로컬 저장은 개발용, Cloud Run 영구 저장은 GCS 연동 과제)"),

        ("4. Diagnostic Agent Layer (Gemini)",
         SUCCESS_GREEN,
         "Gemini 3.8 Flash Function Calling 기반 사후 원인 진단 보조",
         "Gemini가 도구 제안 ➔ 서버 인자 검증 후 Python 도구 실행 ➔ 단순 JSON 생성",
         "Python 결정적 Evidence 검증 통과 보고서만 운영자에게 제공")
    ]

    ly = 1.4
    for title, col, p1, p2, p3 in layers:
        add_card(s3, Inches(0.8), Inches(ly), Inches(11.733), Inches(1.15), border_color=col)
        tb_lay = s3.shapes.add_textbox(Inches(1.1), Inches(ly + 0.08), Inches(11.2), Inches(1.0))
        tf_lay = tb_lay.text_frame
        tf_lay.word_wrap = True
        p = tf_lay.paragraphs[0]
        p.text = title
        p.font.name = FONT_FAMILY
        p.font.size = Pt(13)
        p.font.bold = True
        p.font.color.rgb = col

        p_sub = tf_lay.add_paragraph()
        p_sub.text = f"• {p1}   • {p2}   • {p3}"
        p_sub.font.name = FONT_FAMILY
        p_sub.font.size = Pt(9.5)
        p_sub.font.color.rgb = TEXT_WHITE
        p_sub.space_before = Pt(3)

        ly += 1.35

    # ==========================================
    # SLIDE 4: Vision Model Metrics (Preserved)
    # ==========================================
    s4 = prs.slides.add_slide(blank_layout)
    set_slide_background(s4)
    add_header(s4, "Vision 엔진 성능: PatchCore 평가 및 엔지니어링 한계 분석")

    add_card(s4, Inches(0.8), Inches(1.4), Inches(5.7), Inches(5.3), border_color=PRIMARY_CYAN)
    tb_m = s4.shapes.add_textbox(Inches(1.1), Inches(1.65), Inches(5.1), Inches(4.8))
    tf_m = tb_m.text_frame
    tf_m.word_wrap = True
    p = tf_m.paragraphs[0]
    p.text = "PatchCore 모델 성능 지표 (MVTec Bottle)"
    p.font.name = FONT_FAMILY
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = PRIMARY_CYAN

    metrics_list = [
        ("학습 데이터셋", "정상 이미지 180장 (Unsupervised)", "비지도 Coreset 서브샘플링"),
        ("임계값 산출셋", "독립 정상 이미지 29장", "분포 기반 임계값 산출 (mu + 3sigma)"),
        ("이상 점수 임계값", "34.1442", "이상이면 결함(NG)으로 분류"),
        ("테스트셋 평가", "83장 (정상 20장 + 결함 63장)", "공식 평가셋 표본 기준"),
        ("Image AUROC", "0.8286", "이상 탐지 분별 성능"),
        ("정밀도 (Precision)", "100.0% (83장 표본 한정)", "해당 표본 기준 실측 (실전 전수 보장 아님)"),
        ("재현율 (Recall)", "50.79% (미탐 31건 발생)", "실제 불량 63건 중 32건 탐지, 31건 미탐"),
        ("CPU 단일 추론 시간", "평균 42.53ms (PatchCore만)", "Agent 전체나 라인 처리속도 아님")
    ]
    for name, val, desc in metrics_list:
        p = tf_m.add_paragraph()
        p.text = f"{name}: {val}"
        p.font.name = FONT_FAMILY
        p.font.size = Pt(11.5)
        p.font.bold = True
        p.font.color.rgb = TEXT_WHITE
        p.space_before = Pt(6)
        p_d = tf_m.add_paragraph()
        p_d.text = f"   ({desc})"
        p_d.font.name = FONT_FAMILY
        p_d.font.size = Pt(9.0)
        p_d.font.color.rgb = TEXT_MUTED

    add_card(s4, Inches(6.8), Inches(1.4), Inches(5.7), Inches(5.3), border_color=WARNING_AMBER)
    tb_cm = s4.shapes.add_textbox(Inches(7.1), Inches(1.65), Inches(5.1), Inches(4.8))
    tf_cm = tb_cm.text_frame
    tf_cm.word_wrap = True
    p = tf_cm.paragraphs[0]
    p.text = "혼동 행렬 및 엔지니어링 분석"
    p.font.name = FONT_FAMILY
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = WARNING_AMBER

    cm_points = [
        ("진양성 (TP): 32건 / 진음성 (TN): 20건", "실제 결함 32건 검출, 정상 제품 20건 정상 판정"),
        ("위양성 (FP): 0건 (정밀도 100%)", "83장 표본 내 과검 0건 (모든 공정의 FP 0% 보장 아님)"),
        ("위음성 (FN): 31건 (재현율 50.79%)", "미세 결함 31건 미탐지 (모델 OK != 무결점 제품)"),
        ("T06 미탐 사례 보존", "파손 불량 T06이 점수 32.27로 합격 처리된 한계 보존"),
        ("평가 문서 제약 보존", "과거 209장(46.17ms) 모델 대비 현재 180장(42.53ms) 차이 및 contamination FN 표기 불일치는 현황 제약으로 보존"),
        ("정답 격리 & 설비 미제어", "실제 정답 라벨은 Agent에 미제공, 물리적 PLC 제어 미수행")
    ]
    for title, desc in cm_points:
        p = tf_cm.add_paragraph()
        p.text = "• " + title
        p.font.name = FONT_FAMILY
        p.font.size = Pt(11.0)
        p.font.bold = True
        p.font.color.rgb = TEXT_WHITE
        p.space_before = Pt(5)
        p_d = tf_cm.add_paragraph()
        p_d.text = "   " + desc
        p_d.font.name = FONT_FAMILY
        p_d.font.size = Pt(9.0)
        p_d.font.color.rgb = TEXT_LIGHT

    # ==========================================
    # SLIDE 5: Decision Layer Rules (Overlap Fixed & Clear Bottom Box)
    # ==========================================
    s5 = prs.slides.add_slide(blank_layout)
    set_slide_background(s5)
    add_header(s5, "Decision 계층: 대표 판정 규칙 4가지와 REINSPECT 분류")

    rules = [
        ("Rule 1: 파이프라인 실패 ➔ ERROR  [INSPECTION_FAILED]",
         DANGER_CORAL,
         "조건: status == 'FAILED'",
         "영상 로드 실패, 디코딩 에러 등 검사 파이프라인 자체 오류 시 즉시 ERROR 발급 및 실패 감사 로그 기록"),

        ("Rule 2: 영상 품질 경고 ➔ REINSPECT  [IMAGE_QUALITY_WARNING]",
         WARNING_AMBER,
         "조건: image_quality_status != 'NORMAL'",
         "조도 저하(T03) 시 모델이 OK여도 제품 결함(NG)과 구분하여 '재검사 필요'로 분류 (오판 방지 핵심 규칙)"),

        ("Rule 4: 제품 이상 탐지 ➔ NG  [PRODUCT_ANOMALY_DETECTED]",
         DANGER_CORAL,
         "조건: 품질 NORMAL and result == 'NG'",
         "영상 품질이 정상이고 PatchCore 이상 점수가 임계값(34.1442)을 초과한 경우 서버 최종 불량(NG) 확정"),

        ("Rule 5: 정상 검사 통과 ➔ OK  [ALL_CHECKS_PASSED]",
         SUCCESS_GREEN,
         "조건: 품질 NORMAL and result == 'OK'",
         "영상 품질이 정상이고 PatchCore 이상 점수가 임계값 이하인 경우 최종 양품(OK) 판정 발급")
    ]

    # Rule 1, 2, 4, 5 Cards (Height: 0.95", Step: 1.05" -> Top range: 1.35" to 5.45")
    ry = 1.35
    for title, col, cond, desc in rules:
        add_card(s5, Inches(0.8), Inches(ry), Inches(11.733), Inches(0.95), border_color=col)
        tb_r = s5.shapes.add_textbox(Inches(1.05), Inches(ry + 0.06), Inches(11.2), Inches(0.85))
        tf_r = tb_r.text_frame
        tf_r.word_wrap = True
        p = tf_r.paragraphs[0]
        p.text = title
        p.font.name = FONT_FAMILY
        p.font.size = Pt(12.5)
        p.font.bold = True
        p.font.color.rgb = col

        p_c = tf_r.add_paragraph()
        p_c.text = f"• {cond}  ➔  {desc}"
        p_c.font.name = FONT_FAMILY
        p_c.font.size = Pt(10)
        p_c.font.color.rgb = TEXT_LIGHT
        p_c.space_before = Pt(2)
        ry += 1.05

    # Bottom notice banner: Separate box for Rule 3 & Rule 6 (Top: 5.60", Height: 1.45", Bottom: 7.05")
    # Perfectly separated from Rule 5 bottom (5.45") by 0.15" gap, no overlap!
    add_card(s5, Inches(0.8), Inches(5.60), Inches(11.733), Inches(1.45), bg_color=CARD_BG_ALT, border_color=PRIMARY_CYAN)
    tb_b5 = s5.shapes.add_textbox(Inches(1.05), Inches(5.68), Inches(11.2), Inches(1.30))
    tf_b5 = tb_b5.text_frame
    tf_b5.word_wrap = True

    p_b0 = tf_b5.paragraphs[0]
    p_b0.text = "🛡️ 보충 규칙 (예외 및 안전 보호 규칙) & 판정 원칙"
    p_b0.font.name = FONT_FAMILY
    p_b0.font.size = Pt(11)
    p_b0.font.bold = True
    p_b0.font.color.rgb = PRIMARY_CYAN

    p_b1 = tf_b5.add_paragraph()
    p_b1.text = "• Rule 3 [DEFECT_DETECTION_UNAVAILABLE]: 모델 추론 미실행·파이프라인 중단 시 발급 ➔ 추론 미수행 제품의 합격 오판 원천 방지"
    p_b1.font.name = FONT_FAMILY
    p_b1.font.size = Pt(10)
    p_b1.font.color.rgb = TEXT_LIGHT
    p_b1.space_before = Pt(3)

    p_b2 = tf_b5.add_paragraph()
    p_b2.text = "• Rule 6 [UNKNOWN_STATE_COMBINATION]: 정의되지 않은 상태 조합 발생 시 안전 거부 ➔ 시스템 미인지 위험 상태 방어"
    p_b2.font.name = FONT_FAMILY
    p_b2.font.size = Pt(10)
    p_b2.font.color.rgb = TEXT_LIGHT
    p_b2.space_before = Pt(2)

    p_b3 = tf_b5.add_paragraph()
    p_b3.text = "💡 주의: REINSPECT는 물리적 폐기/격리 제어가 아닌 서버 판정 상태 분류이며, 실시간 PLC/공압 하드웨어 제어는 포함하지 않습니다."
    p_b3.font.name = FONT_FAMILY
    p_b3.font.size = Pt(9.5)
    p_b3.font.color.rgb = TEXT_MUTED
    p_b3.space_before = Pt(2)

    # ==========================================
    # SLIDE 6: Gemini Function Calling
    # ==========================================
    s6 = prs.slides.add_slide(blank_layout)
    set_slide_background(s6)
    add_header(s6, "AI Agent: Gemini Function Calling 기반 정밀 조사 체계")

    tools = [
        ("1. get_inspection_result",
         PRIMARY_CYAN,
         "검사 기본 결과 조회",
         "검사 상태, 이상 점수, 모델 소견(result), 서버 최종 판정(final_result), 사유 코드 확인 (Evidence E0001)"),

        ("2. analyze_image_quality",
         WARNING_AMBER,
         "영상 품질 세부 분석",
         "평균 밝기, 표준편차, min/max 동적범위 등 세부 조도 통계 조회 (Evidence E0002)"),

        ("3. get_execution_logs",
         PRIMARY_CYAN,
         "실행 감사 로그 확인",
         "검사 파이프라인 시각순 이벤트 로그(IMAGE_LOAD_FAILED 등) 추적 및 오류 상세 확인"),

        ("4. get_inspection_history",
         WARNING_AMBER,
         "과거 검사 이력 조회",
         "동일 제품의 직전 검사 이력 트렌드를 비교하여 반복 불량 여부 확인")
    ]

    ty = 1.4
    for title, col, role, desc in tools:
        add_card(s6, Inches(0.8), Inches(ty), Inches(11.733), Inches(0.95), border_color=col)
        tb_t = s6.shapes.add_textbox(Inches(1.0), Inches(ty + 0.06), Inches(11.3), Inches(0.85))
        tf_t = tb_t.text_frame
        tf_t.word_wrap = True
        p = tf_t.paragraphs[0]
        p.text = f"{title}  —  {role}"
        p.font.name = FONT_FAMILY
        p.font.size = Pt(12.5)
        p.font.bold = True
        p.font.color.rgb = col

        p_d = tf_t.add_paragraph()
        p_d.text = f"• 기능: {desc}"
        p_d.font.name = FONT_FAMILY
        p_d.font.size = Pt(10)
        p_d.font.color.rgb = TEXT_LIGHT
        p_d.space_before = Pt(2)
        ty += 1.15

    add_card(s6, Inches(0.8), Inches(6.0), Inches(11.733), Inches(0.8), bg_color=CARD_BG_ALT, border_color=SUCCESS_GREEN)
    tb_c6 = s6.shapes.add_textbox(Inches(1.0), Inches(6.05), Inches(11.3), Inches(0.7))
    tf_c6 = tb_c6.text_frame
    tf_c6.word_wrap = True
    p_c6 = tf_c6.paragraphs[0]
    p_c6.text = "🔒 제어 흐름: 1.Gemini 도구 제안 ➔ 2.FastAPI 서버 인자 검증 ➔ 3.Python 실행 ➔ 4.FunctionResponse 전달 ➔ 5.단순 JSON 보고서 생성 ➔ 6.Pydantic/Evidence 검증"
    p_c6.font.name = FONT_FAMILY
    p_c6.font.size = Pt(10.5)
    p_c6.font.color.rgb = TEXT_WHITE
    p_c6.alignment = PP_ALIGN.CENTER

    # ==========================================
    # SLIDE 7: Deterministic Evidence Mechanism (Clean '관측 사실')
    # ==========================================
    s7 = prs.slides.add_slide(blank_layout)
    set_slide_background(s7)
    add_header(s7, "Evidence 메커니즘: 결정적 근거 검증을 통한 신뢰성 확보")

    ev_pillars = [
        ("Pillar 1: Evidence ID  (서버 발급 도구 영수증)",
         PRIMARY_CYAN,
         "도구 실행 시 서버가 E0001, E0002 고유 ID를 부여하여 모델의 허위 실행 주장 차단"),

        ("Pillar 2: Fact ID & Pointer  (JSON Pointer 1:1 결정적 검증)",
         SUCCESS_GREEN,
         "보고서에 포함된 구조화된 관측 사실(F0001~)을 서버의 실제 도구 결과(/data/final_result 등)와 결정적으로 대조"),

        ("Pillar 3: 근거 앵커링  (권장 조치-근거 필수 연결)",
         WARNING_AMBER,
         "모든 추천 조치(recommended_checks)는 반드시 유효한 관측 사실(evidence_refs)을 참조해야 통과"),

        ("Pillar 4: 판정 불변성  (서버 확정 판정 보호)",
         DANGER_CORAL,
         "Gemini는 사후 진단 보조 역할만 수행하며, 서버가 확정한 final_result를 절대 변경할 수 없음")
    ]

    ey = 1.4
    for title, col, desc in ev_pillars:
        add_card(s7, Inches(0.8), Inches(ey), Inches(11.733), Inches(0.95), border_color=col)
        tb_e = s7.shapes.add_textbox(Inches(1.0), Inches(ey + 0.06), Inches(11.3), Inches(0.85))
        tf_e = tb_e.text_frame
        tf_e.word_wrap = True
        p = tf_e.paragraphs[0]
        p.text = title
        p.font.name = FONT_FAMILY
        p.font.size = Pt(12.5)
        p.font.bold = True
        p.font.color.rgb = col

        p_d = tf_e.add_paragraph()
        p_d.text = f"• 동작 원리: {desc}"
        p_d.font.name = FONT_FAMILY
        p_d.font.size = Pt(10)
        p_d.font.color.rgb = TEXT_LIGHT
        p_d.space_before = Pt(2)
        ey += 1.15

    add_card(s7, Inches(0.8), Inches(6.0), Inches(11.733), Inches(0.8), bg_color=CARD_BG_ALT, border_color=SUCCESS_GREEN)
    tb_c7 = s7.shapes.add_textbox(Inches(1.0), Inches(6.05), Inches(11.3), Inches(0.7))
    tf_c7 = tb_c7.text_frame
    tf_c7.word_wrap = True
    p_c7 = tf_c7.paragraphs[0]
    p_c7.text = "💡 실제 실서버 검증 성과: 4대 대표 시나리오 T01(6개), T03(12개), T05(17개), T06(6개)의 관측 사실 전원이 서버의 Evidence 및 JSON Pointer 검증을 통과했습니다. (서버 등록 필드 1:1 결정적 일치를 확인하며, 모든 자연어 가설을 완전 검증한다고 과장하지 않음)"
    p_c7.font.name = FONT_FAMILY
    p_c7.font.size = Pt(10.0)
    p_c7.font.color.rgb = TEXT_WHITE
    p_c7.alignment = PP_ALIGN.CENTER

    # ==========================================
    # SLIDE 8: Structured Output Compatibility
    # ==========================================
    s8 = prs.slides.add_slide(blank_layout)
    set_slide_background(s8)
    add_header(s8, "기술적 문제 해결: Gemini 구조화 출력 호환성 개선")

    add_card(s8, Inches(0.8), Inches(1.4), Inches(5.7), Inches(4.3), border_color=DANGER_CORAL)
    tb_b8 = s8.shapes.add_textbox(Inches(1.1), Inches(1.65), Inches(5.1), Inches(3.8))
    tf_b8 = tb_b8.text_frame
    tf_b8.word_wrap = True
    p = tf_b8.paragraphs[0]
    p.text = "Before: 직접 구조화 출력 시도 ➔ HTTP 400"
    p.font.name = FONT_FAMILY
    p.font.size = Pt(15)
    p.font.bold = True
    p.font.color.rgb = DANGER_CORAL

    b_points_final = [
        ("복잡한 Pydantic 스키마 전달", "DiagnosisDraft 스키마를 response_json_schema로 직접 전송"),
        ("실서버 HTTP 400 거부", "Gemini 서버가 스키마 호환성 문제로 ClientError 반환 (정확한 거부 속성은 UNKNOWN)"),
        ("결과", "사후 진단 보고서 생성 실패")
    ]
    for title, desc in b_points_final:
        p = tf_b8.add_paragraph()
        p.text = "• " + title
        p.font.name = FONT_FAMILY
        p.font.size = Pt(12)
        p.font.bold = True
        p.font.color.rgb = TEXT_WHITE
        p.space_before = Pt(10)
        p_d = tf_b8.add_paragraph()
        p_d.text = "   " + desc
        p_d.font.name = FONT_FAMILY
        p_d.font.size = Pt(10.5)
        p_d.font.color.rgb = TEXT_LIGHT

    add_card(s8, Inches(6.8), Inches(1.4), Inches(5.7), Inches(4.3), border_color=SUCCESS_GREEN)
    tb_a8 = s8.shapes.add_textbox(Inches(7.1), Inches(1.65), Inches(5.1), Inches(3.8))
    tf_a8 = tb_a8.text_frame
    tf_a8.word_wrap = True
    p = tf_a8.paragraphs[0]
    p.text = "After: 스키마 단순화 + Python 검증 ➔ PASS"
    p.font.name = FONT_FAMILY
    p.font.size = Pt(15)
    p.font.bold = True
    p.font.color.rgb = SUCCESS_GREEN

    a_points_final = [
        ("출력 스키마 단순화", "Gemini에는 단순화된 JSON 스키마만 전송 (토큰 선택 지시)"),
        ("토큰 카탈로그 주입", "서버가 수집한 사실(K0001~)을 프롬프트로 전달, 모델은 토큰만 선택"),
        ("Python 엄격 검증 파이프라인", "Gemini 출력 ➔ Python DiagnosisDraft 변환 ➔ Pydantic ➔ 결정적 Evidence 검증")
    ]
    for title, desc in a_points_final:
        p = tf_a8.add_paragraph()
        p.text = "✔ " + title
        p.font.name = FONT_FAMILY
        p.font.size = Pt(12)
        p.font.bold = True
        p.font.color.rgb = PRIMARY_CYAN
        p.space_before = Pt(10)
        p_d = tf_a8.add_paragraph()
        p_d.text = "   " + desc
        p_d.font.name = FONT_FAMILY
        p_d.font.size = Pt(10.5)
        p_d.font.color.rgb = TEXT_LIGHT

    add_card(s8, Inches(0.8), Inches(5.95), Inches(11.733), Inches(0.8), bg_color=CARD_BG_ALT, border_color=PRIMARY_CYAN)
    tb_sum8 = s8.shapes.add_textbox(Inches(1.0), Inches(6.0), Inches(11.3), Inches(0.7))
    tf_s8 = tb_sum8.text_frame
    p_s8 = tf_s8.paragraphs[0]
    p_s8.text = "💡 핵심 설계: 모델을 맹신하는 구조가 아니라, 모델의 생성 결과를 서버가 엄격하게 검증하는 구조로 신뢰성을 확보했습니다."
    p_s8.font.name = FONT_FAMILY
    p_s8.font.size = Pt(11)
    p_s8.font.color.rgb = TEXT_WHITE
    p_s8.alignment = PP_ALIGN.CENTER

    # ==========================================
    # SLIDE 9: Core Engineering Challenges & Solutions (Updated T05 & 984 PASS)
    # ==========================================
    s9 = prs.slides.add_slide(blank_layout)
    set_slide_background(s9)
    add_header(s9, "핵심 기술 난제와 해결 과정", 
               category_text="VISIONINSIGHT  |  CORE ENGINEERING CHALLENGES & SOLUTIONS",
               subtitle_text="\"Gemini API 연결보다 어려웠던 것은, 검증 가능한 Agent를 만드는 과정\"")

    challenges_cards = [
        {
            "tag": "HTTP 400",
            "title": "구조화 출력 호환성",
            "color": PRIMARY_CYAN,
            "problem": "복잡한 Pydantic 스키마 직접 전달 시 HTTP 400",
            "problem_sub": "*(거부 속성은 Google 내부 원인으로 UNKNOWN)",
            "solution": "단순 JSON 생성 → Python 변환·검증",
            "solution_sub": "*(토큰 카탈로그 주입 + 서버 엄격 규칙 검증)",
            "result": "대표 4개 시나리오 E2E 성공 회차 확보",
            "result_sub": "단순 JSON 스키마 적용 ➔ Python 엄격 검증 통과"
        },
        {
            "tag": "HTTP 504",
            "title": "타임아웃 분리 및 계측",
            "color": WARNING_AMBER,
            "problem": "과거 T03/T06 최종 생성 15s 초과 504 발생",
            "problem_sub": "*(서버 내부 원인은 UNKNOWN, 반복 안정성 과제)",
            "solution": "요청별 timeout 계측 및 분리",
            "solution_sub": "*(조사 15s 유지 / 최종 JSON만 30s 선택, 전체 60s)",
            "result": "T03(18.97s) & T06(24.12s) PASS",
            "result_sub": "선택적 30초 설정 회차 성공 (504 직접 해결은 미확정)"
        },
        {
            "tag": "E2E 완결",
            "title": "T05 조기종료 & T06 불변성",
            "color": SUCCESS_GREEN,
            "problem": "T05 3차조사 504 FAIL & T06 정답 격리",
            "problem_sub": "*(T05 1회 FAIL 보존, T06 외부 정답 미제공)",
            "solution": "T05 전용 조기 종료 & T06 판정 가드레일",
            "solution_sub": "*(17개 사실 즉시종료, final_result=OK 불변)",
            "result": "T05(16.33s) & T06(26.37s) PASS",
            "result_sub": "T06 원본 ASGI 미보관 (재구성 코드 기반 검토 한계)"
        }
    ]

    card_w9 = Inches(3.7)
    cx9 = 0.8
    for item in challenges_cards:
        add_card(s9, Inches(cx9), Inches(1.4), card_w9, Inches(4.35), border_color=item["color"])
        tb_c = s9.shapes.add_textbox(Inches(cx9 + 0.18), Inches(1.50), card_w9 - Inches(0.36), Inches(4.15))
        tf_c = tb_c.text_frame
        tf_c.word_wrap = True
        
        # Tag & Title
        p_tag = tf_c.paragraphs[0]
        p_tag.text = item["tag"]
        p_tag.font.name = FONT_FAMILY
        p_tag.font.size = Pt(11)
        p_tag.font.bold = True
        p_tag.font.color.rgb = item["color"]

        p_title = tf_c.add_paragraph()
        p_title.text = item["title"]
        p_title.font.name = FONT_FAMILY
        p_title.font.size = Pt(16)
        p_title.font.bold = True
        p_title.font.color.rgb = TEXT_WHITE
        p_title.space_before = Pt(2)

        # 1. 문제
        p_prob_hdr = tf_c.add_paragraph()
        p_prob_hdr.text = "🚨 핵심 문제"
        p_prob_hdr.font.name = FONT_FAMILY
        p_prob_hdr.font.size = Pt(11)
        p_prob_hdr.font.bold = True
        p_prob_hdr.font.color.rgb = item["color"]
        p_prob_hdr.space_before = Pt(8)

        p_prob = tf_c.add_paragraph()
        p_prob.text = item["problem"]
        p_prob.font.name = FONT_FAMILY
        p_prob.font.size = Pt(11)
        p_prob.font.bold = True
        p_prob.font.color.rgb = TEXT_WHITE
        p_prob.space_before = Pt(1)

        p_prob_sub = tf_c.add_paragraph()
        p_prob_sub.text = item["problem_sub"]
        p_prob_sub.font.name = FONT_FAMILY
        p_prob_sub.font.size = Pt(9.5)
        p_prob_sub.font.color.rgb = TEXT_MUTED

        # 2. 해결
        p_sol_hdr = tf_c.add_paragraph()
        p_sol_hdr.text = "⚡ 해결 접근"
        p_sol_hdr.font.name = FONT_FAMILY
        p_sol_hdr.font.size = Pt(11)
        p_sol_hdr.font.bold = True
        p_sol_hdr.font.color.rgb = item["color"]
        p_sol_hdr.space_before = Pt(6)

        p_sol = tf_c.add_paragraph()
        p_sol.text = item["solution"]
        p_sol.font.name = FONT_FAMILY
        p_sol.font.size = Pt(11)
        p_sol.font.bold = True
        p_sol.font.color.rgb = TEXT_WHITE
        p_sol.space_before = Pt(1)

        p_sol_sub = tf_c.add_paragraph()
        p_sol_sub.text = item["solution_sub"]
        p_sol_sub.font.name = FONT_FAMILY
        p_sol_sub.font.size = Pt(9.5)
        p_sol_sub.font.color.rgb = TEXT_MUTED

        # 3. 결과
        p_res_hdr = tf_c.add_paragraph()
        p_res_hdr.text = "🎯 검증 결과"
        p_res_hdr.font.name = FONT_FAMILY
        p_res_hdr.font.size = Pt(11)
        p_res_hdr.font.bold = True
        p_res_hdr.font.color.rgb = SUCCESS_GREEN
        p_res_hdr.space_before = Pt(6)

        p_res = tf_c.add_paragraph()
        p_res.text = item["result"]
        p_res.font.name = FONT_FAMILY
        p_res.font.size = Pt(11.5)
        p_res.font.bold = True
        p_res.font.color.rgb = SUCCESS_GREEN
        p_res.space_before = Pt(1)

        p_res_sub = tf_c.add_paragraph()
        p_res_sub.text = item["result_sub"]
        p_res_sub.font.name = FONT_FAMILY
        p_res_sub.font.size = Pt(9.5)
        p_res_sub.font.color.rgb = TEXT_MUTED

        cx9 += 4.0

    # Bottom banner (Explicit 4 Scenarios E2E PASS & 1089 PASS with caveats)
    add_card(s9, Inches(0.8), Inches(5.95), Inches(11.733), Inches(0.8), bg_color=CARD_BG_ALT, border_color=PRIMARY_CYAN)
    tb_sum9 = s9.shapes.add_textbox(Inches(1.0), Inches(6.0), Inches(11.3), Inches(0.7))
    tf_sum9 = tb_sum9.text_frame
    p_sum9 = tf_sum9.paragraphs[0]
    p_sum9.text = "💡 현황: T01·T03·T05·T06 대표 4개 시나리오에서 각각 실제 Gemini E2E 성공 회차 확보 (단일 성공 회차가 반복 실행 안정성을 보증하는 것은 아님) | 전체 pytest 1089 PASS / 4 SKIP"
    p_sum9.font.name = FONT_FAMILY
    p_sum9.font.size = Pt(10.5)
    p_sum9.font.bold = True
    p_sum9.font.color.rgb = TEXT_WHITE
    p_sum9.alignment = PP_ALIGN.CENTER

    # ==========================================
    # SLIDE 10: Real Server E2E: 4 Scenarios (T01, T03, T05, T06)
    # ==========================================
    s10 = prs.slides.add_slide(blank_layout)
    set_slide_background(s10)
    add_header(s10, "실제 Gemini API E2E 검증 결과: 4대 대표 시나리오 전원 성공 (PASS)")

    scenarios_e2e = [
        {
            "tag": "T01 정상",
            "insp_id": "INSP-001396",
            "badge": "✔ E2E PASS",
            "verdict": "최종 OK",
            "verdict_sub": "(모델 OK ➔ Rule 5)",
            "verdict_color": SUCCESS_GREEN,
            "total_time": "13.58초",
            "facts": "Fact 6개",
            "facts_sub": "100% 검증 통과",
            "rule": "Rule 5 (ALL_CHECKS_PASSED)",
            "tools": "도구 1개 / 4,706 토큰",
            "action": "CONTINUE_MONITORING"
        },
        {
            "tag": "T03 품질 경고",
            "insp_id": "INSP-001398",
            "badge": "✔ E2E PASS",
            "verdict": "최종 REINSPECT",
            "verdict_sub": "(조도 저하 81.24 ➔ 재검)",
            "verdict_color": WARNING_AMBER,
            "total_time": "24.60초",
            "facts": "Fact 12개",
            "facts_sub": "100% 검증 통과",
            "rule": "Rule 2 (IMAGE_QUALITY_WARN)",
            "tools": "도구 2개 / 9,873 토큰",
            "action": "조명 점검 & 안전 재검사"
        },
        {
            "tag": "T05 로드 실패",
            "insp_id": "INSP-001405",
            "badge": "✔ E2E PASS",
            "verdict": "최종 ERROR",
            "verdict_sub": "(영상 손상 ➔ 조기 종료)",
            "verdict_color": DANGER_CORAL,
            "total_time": "16.33초",
            "facts": "Fact 17개",
            "facts_sub": "100% 검증 통과",
            "rule": "Rule 1 (INSPECTION_FAILED)",
            "tools": "도구 2개 / 11,426 토큰",
            "action": "파일/카메라 점검 (오추론 방지)"
        },
        {
            "tag": "T06 저장 OK",
            "insp_id": "INSP-001406",
            "badge": "✔ E2E PASS",
            "verdict": "최종 OK (불변)",
            "verdict_sub": "(서버 원본 판정 보존)",
            "verdict_color": SUCCESS_GREEN,
            "total_time": "26.37초",
            "facts": "Fact 6개",
            "facts_sub": "100% 검증 통과",
            "rule": "서버 원본 판정 가드레일",
            "tools": "도구 1개 / 7,202 토큰",
            "action": "정답 미노출 & 판정 보존"
        }
    ]

    card_w10 = Inches(2.75)
    card_gap10 = Inches(0.244)
    cx10 = 0.80

    for sc in scenarios_e2e:
        add_card(s10, Inches(cx10), Inches(1.38), card_w10, Inches(4.48), border_color=SUCCESS_GREEN)
        tb_sc = s10.shapes.add_textbox(Inches(cx10 + 0.12), Inches(1.44), card_w10 - Inches(0.24), Inches(4.35))
        tf_sc = tb_sc.text_frame
        tf_sc.word_wrap = True

        # 1. 시나리오 이름 (18pt Bold)
        p_tag = tf_sc.paragraphs[0]
        p_tag.text = sc["tag"]
        p_tag.font.name = FONT_FAMILY
        p_tag.font.size = Pt(18)
        p_tag.font.bold = True
        p_tag.font.color.rgb = TEXT_WHITE

        # 2. PASS 배지 (13pt Bold)
        p_badge = tf_sc.add_paragraph()
        p_badge.text = sc["badge"] + " (HTTP 200)"
        p_badge.font.name = FONT_FAMILY
        p_badge.font.size = Pt(12.5)
        p_badge.font.bold = True
        p_badge.font.color.rgb = SUCCESS_GREEN
        p_badge.space_before = Pt(2)

        # 3. 최종 판정 (14pt Bold)
        p_vrd_lbl = tf_sc.add_paragraph()
        p_vrd_lbl.text = "최종 판정"
        p_vrd_lbl.font.name = FONT_FAMILY
        p_vrd_lbl.font.size = Pt(11)
        p_vrd_lbl.font.color.rgb = TEXT_MUTED
        p_vrd_lbl.space_before = Pt(8)

        p_vrd = tf_sc.add_paragraph()
        p_vrd.text = sc["verdict"]
        p_vrd.font.name = FONT_FAMILY
        p_vrd.font.size = Pt(15)
        p_vrd.font.bold = True
        p_vrd.font.color.rgb = sc["verdict_color"]

        p_vrd_sub = tf_sc.add_paragraph()
        p_vrd_sub.text = sc["verdict_sub"]
        p_vrd_sub.font.name = FONT_FAMILY
        p_vrd_sub.font.size = Pt(10)
        p_vrd_sub.font.color.rgb = TEXT_LIGHT

        # 4. 전체 E2E 소요 시간 (17pt Bold)
        p_time_lbl = tf_sc.add_paragraph()
        p_time_lbl.text = "전체 E2E 소요시간"
        p_time_lbl.font.name = FONT_FAMILY
        p_time_lbl.font.size = Pt(11)
        p_time_lbl.font.color.rgb = TEXT_MUTED
        p_time_lbl.space_before = Pt(8)

        p_time = tf_sc.add_paragraph()
        p_time.text = sc["total_time"]
        p_time.font.name = FONT_FAMILY
        p_time.font.size = Pt(17)
        p_time.font.bold = True
        p_time.font.color.rgb = PRIMARY_CYAN

        # 5. 검증 Fact 개수 (14.5pt Bold)
        p_fact_lbl = tf_sc.add_paragraph()
        p_fact_lbl.text = "검증 Fact (근거)"
        p_fact_lbl.font.name = FONT_FAMILY
        p_fact_lbl.font.size = Pt(11)
        p_fact_lbl.font.color.rgb = TEXT_MUTED
        p_fact_lbl.space_before = Pt(8)

        p_fact = tf_sc.add_paragraph()
        p_fact.text = f"{sc['facts']} ({sc['facts_sub']})"
        p_fact.font.name = FONT_FAMILY
        p_fact.font.size = Pt(13.5)
        p_fact.font.bold = True
        p_fact.font.color.rgb = SUCCESS_GREEN

        # 6. 하단 메타정보 (ID & 권고)
        p_meta = tf_sc.add_paragraph()
        p_meta.text = f"• {sc['rule']}\n• {sc['tools']}\n• 권고: {sc['action']}\n• 검사 ID: {sc['insp_id']}"
        p_meta.font.name = FONT_FAMILY
        p_meta.font.size = Pt(9.5)
        p_meta.font.color.rgb = TEXT_LIGHT
        p_meta.space_before = Pt(8)

        cx10 += 2.75 + 0.244

    # Bottom banner (Detailed E2E summary & T06 limitations)
    add_card(s10, Inches(0.8), Inches(5.95), Inches(11.733), Inches(0.85), bg_color=CARD_BG_ALT, border_color=PRIMARY_CYAN)
    tb_sum10 = s10.shapes.add_textbox(Inches(1.0), Inches(6.0), Inches(11.3), Inches(0.75))
    tf_sum10 = tb_sum10.text_frame
    tf_sum10.word_wrap = True
    p_sum10 = tf_sum10.paragraphs[0]
    p_sum10.text = "💡 실서버 E2E 성과: 4대 대표 시나리오 전원 HTTP 200 / 관측 사실 100% 통과 달성\n*(T06: 30초 timeout 설정 회차 성공이나 504 직접 해결은 미확정이며, 원본 ASGI 본문 미보관으로 재구성 코드 기반 사후 검토 한계 명시)"
    p_sum10.font.name = FONT_FAMILY
    p_sum10.font.size = Pt(10.5)
    p_sum10.font.bold = True
    p_sum10.font.color.rgb = TEXT_WHITE
    p_sum10.alignment = PP_ALIGN.CENTER

    # ==========================================
    # SLIDE 11: Demo Presentation (Preserved)
    # ==========================================
    s11 = prs.slides.add_slide(blank_layout)
    set_slide_background(s11)
    add_header(s11, "발표 데모 시연: T01 양품 vs T03 조도 경고 정적 데모")

    # Left: Demo Process
    add_card(s11, Inches(0.8), Inches(1.4), Inches(5.7), Inches(5.3), border_color=PRIMARY_CYAN)
    tb_dl = s11.shapes.add_textbox(Inches(1.1), Inches(1.65), Inches(5.1), Inches(4.8))
    tf_dl = tb_dl.text_frame
    tf_dl.word_wrap = True
    p = tf_dl.paragraphs[0]
    p.text = "발표 시연 흐름 제안"
    p.font.name = FONT_FAMILY
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = PRIMARY_CYAN

    demo_steps = [
        ("Step 1. T01 정상 검사 데모 시연", "t01-report-demo.html 시연: 평균 밝기 135.86, 이상 점수 31.33 ➔ 모델 OK 및 Rule 5 최종 OK 확인"),
        ("Step 2. T03 조도 경고 데모 시연", "t03-report-demo.html 시연: 평균 밝기 81.24 저하 감지 ➔ 모델 OK이지만 Rule 2 최종 REINSPECT 확인"),
        ("Step 3. 판정 차이 및 분리 설명", "두 검사 모두 모델 판정은 OK지만, 환경 변화에 따라 서버가 오판 방지 재검사를 지시하는 차이 설명"),
        ("Step 4. 판정 불변 및 근거 앵커링", "Gemini가 도구 2개로 팩트 12개를 조회하되 최종 판정을 번복하지 않고 안전 조치(조명 점검 등) 권고 확인")
    ]
    for step, desc in demo_steps:
        p = tf_dl.add_paragraph()
        p.text = "• " + step
        p.font.name = FONT_FAMILY
        p.font.size = Pt(11.5)
        p.font.bold = True
        p.font.color.rgb = TEXT_WHITE
        p.space_before = Pt(8)
        p_d = tf_dl.add_paragraph()
        p_d.text = "   " + desc
        p_d.font.name = FONT_FAMILY
        p_d.font.size = Pt(10)
        p_d.font.color.rgb = TEXT_LIGHT

    # Right: Static Demo Safety
    add_card(s11, Inches(6.8), Inches(1.4), Inches(5.7), Inches(5.3), border_color=WARNING_AMBER)
    tb_dr = s11.shapes.add_textbox(Inches(7.1), Inches(1.65), Inches(5.1), Inches(4.8))
    tf_dr = tb_dr.text_frame
    tf_dr.word_wrap = True
    p = tf_dr.paragraphs[0]
    p.text = "실서버 성공 진단 보고서 비교 (T01 vs T03)"
    p.font.name = FONT_FAMILY
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = WARNING_AMBER

    demo_safety = [
        ("T01 종합 요약", "기록된 판정은 OK입니다. 실제 무결점 제품을 보증하지는 않습니다. (CONTINUE_MONITORING)"),
        ("T03 종합 요약", "종합 판정은 REINSPECT입니다. 제품 불량 확정과 구분하여 재검 필요. (조명점검/재검 권고)"),
        ("T05 로드 실패", "영상 로드 실패 시 원천 사실 17개 기반 조기 종료, 모델 체크포인트 장애 오추론 방지"),
        ("T06 판정 보존", "외부 평가상 미탐 사례라도 정답 미제공 상태에서 서버 원본 final_result=OK 불변 유지"),
        ("공통 안전 한계", "limitations 필수 명시 (물리적 원인 불명, 모델 무결점 비보증, 설비 미제어 등)"),
        ("정적 데모 원칙", "현장 네트워크 장애/과금 방지를 위해 사전 실서버 검증 데이터를 재생하는 독립 데모 사용")
    ]
    for title, desc in demo_safety:
        p = tf_dr.add_paragraph()
        p.text = "✔ " + title
        p.font.name = FONT_FAMILY
        p.font.size = Pt(11)
        p.font.bold = True
        p.font.color.rgb = PRIMARY_CYAN
        p.space_before = Pt(6)
        p_d = tf_dr.add_paragraph()
        p_d.text = "   " + desc
        p_d.font.name = FONT_FAMILY
        p_d.font.size = Pt(9.5)
        p_d.font.color.rgb = TEXT_LIGHT

    # ==========================================
    # SLIDE 12: Implementation Status & Roadmap (3-Tier Separation & 984 PASS)
    # ==========================================
    s12 = prs.slides.add_slide(blank_layout)
    set_slide_background(s12)
    add_header(s12, "구현 현황 및 향후 계획 (투명한 검증 상태 구분)")

    col_width = Inches(3.7)
    cols_data_final = [
        ("1. Day4 Agent PoC 완료 [공식 완료]",
         SUCCESS_GREEN,
         [
             ("전체 pytest 1089 PASS / 4 SKIP (경고 2건)", TEXT_WHITE, True),
             ("4대 시나리오 실제 Gemini E2E 전원 성공", SUCCESS_GREEN, True),
             ("T01(13.58s) · T03(24.60s)", TEXT_LIGHT, False),
             ("T05(16.33s) · T06(26.37s)", TEXT_LIGHT, False),
             ("Gemini 4대 조회 도구 바인딩 & 단순 JSON", PRIMARY_CYAN, False),
             ("결정적 근거 검증 (Evidence / JSON Pointer)", PRIMARY_CYAN, False),
             ("서버 최종 판정(final_result) 불변 보호", TEXT_WHITE, False)
         ]),

        ("2. Day5 반례 검증 & 영상 [진행 중]",
         PRIMARY_CYAN,
         [
             ("[Step 1] Agent 정책 감사: COMPLETE", SUCCESS_GREEN, True),
             ("T03 이력·T05 실패·T06 격리·무관 WARN 공백 식별", TEXT_LIGHT, False),
             ("[Step 1-B] 반례 5종 Mock 평가: 36회 PASS", SUCCESS_GREEN, True),
             ("오프라인 고정 계약 검증 통과 (PARTIAL)", TEXT_MUTED, False),
             ("[개정 Day5] 영상 파이프라인 (예정)", WARNING_AMBER, True),
             ("VideoFileSource 동영상 프레임 수동 Grab", TEXT_LIGHT, False),
             ("마우스 ROI 추출 ➔ 기존 PatchCore 추론 연결", TEXT_LIGHT, False),
             ("data/inspection_logs.jsonl 분리 정리", TEXT_LIGHT, False)
         ]),

        ("3. Day6~7 UI 및 클라우드 배포 [예정]",
         WARNING_AMBER,
         [
             ("[Day 6] React / TypeScript 웹 관제 (예정)", WARNING_AMBER, True),
             ("동영상 Live View & Grab Image 뷰어", TEXT_LIGHT, False),
             ("마우스 드래그 ROI & 검사/로그 실시간 표출", TEXT_LIGHT, False),
             ("Gemini 사후 진단 보고서 표출 UI 패널", TEXT_LIGHT, False),
             ("[Day 7] Cloud Run 경량 CPU 배포 (예정)", WARNING_AMBER, True),
             ("0.0.0.0 & PORT 컨테이너 패키징", TEXT_LIGHT, False),
             ("로컬 JSONL 한계 극복 ➔ Cloud Storage 연동", TEXT_LIGHT, False),
             ("HTTPS 실환경 통합 검증 및 시연", TEXT_LIGHT, False)
         ])
    ]
    cx = 0.8
    for ctitle, ccol, citems in cols_data_final:
        add_card(s12, Inches(cx), Inches(1.38), col_width, Inches(5.32), border_color=ccol)
        tb_col = s12.shapes.add_textbox(Inches(cx + 0.16), Inches(1.50), col_width - Inches(0.32), Inches(5.1))
        tf_col = tb_col.text_frame
        tf_col.word_wrap = True
        p = tf_col.paragraphs[0]
        p.text = ctitle
        p.font.name = FONT_FAMILY
        p.font.size = Pt(14)
        p.font.bold = True
        p.font.color.rgb = ccol

        for text_str, color, is_bold in citems:
            pi = tf_col.add_paragraph()
            prefix = "• " if is_bold else "   - "
            pi.text = prefix + text_str
            pi.font.name = FONT_FAMILY
            pi.font.size = Pt(11) if is_bold else Pt(10)
            pi.font.bold = is_bold
            pi.font.color.rgb = color
            pi.space_before = Pt(5) if is_bold else Pt(2)

        cx += 4.0

    # ==========================================
    # SLIDE 13: Engineering Limitations (Updated T05 Context)
    # ==========================================
    s13 = prs.slides.add_slide(blank_layout)
    set_slide_background(s13)
    add_header(s13, "한계 및 향후 개선 계획: 솔직한 엔지니어링 고찰")

    limits = [
        ("1. PatchCore 미탐 한계 (Recall 50.79%, FN 31건)",
         WARNING_AMBER,
         "현재 한계", "ResNet-18 기반 모델은 83장 테스트셋에서 미세 파손과 오염 31건을 미검출함 (T06 합격 사례 존재, 모델 OK != 무결점). 정밀도 100%는 83장 표본 내 지표이며, 과거 209장(46.17ms) 대비 180장(42.53ms) 차이 및 contamination FN 표기 불일치는 현황 제약으로 보존",
         "개선 계획", "WideResNet-50 등 백본 교체나 다해상도 패치 결합을 개선 후보로 검토 (성능 보장 아님)"),

        ("2. Gemini HTTP 504 및 타임아웃 안정성 이슈",
         DANGER_CORAL,
         "현재 한계", "과거 T03/T05/T06에서 HTTP 504가 발생했으며 서버 내부 원인은 UNKNOWN임. 30초 timeout 적용으로 4대 시나리오 E2E 전원 성공했으나 30초가 504의 직접 해결책인지는 미확정이며, T06은 원본 ASGI 본문 미보관으로 재구성 코드 기반 검토 한계가 남음",
         "개선 계획", "조기 종료 가드레일 확립, 프롬프트 압축, 비동기 작업 큐 전환 및 장기 모니터링 체계 확립 필요"),

        ("3. 외부 LLM 호출 지연시간 (13.58s ~ 26.37s)",
         PRIMARY_CYAN,
         "현재 한계", "Gemini API 호출에 수십 초가 소요되어 생산 라인 초고속 동기 인라인 제어에는 부적합하며, 실제 PLC·컨베이어·배출기 제어는 수행하지 않음 (사후 진단 보조 역할에 집중)",
         "개선 계획", "사후 비동기 진단 워크플로우로 한정하여 운영하고 라인 제어는 서버의 실시간 규칙 판정값에만 전담")
    ]

    ly13 = 1.4
    for title, col, l_hdr, l_desc, p_hdr, p_desc in limits:
        add_card(s13, Inches(0.8), Inches(ly13), Inches(11.733), Inches(1.6), border_color=col)
        tb_lim = s13.shapes.add_textbox(Inches(1.0), Inches(ly13 + 0.1), Inches(11.3), Inches(1.4))
        tf_lim = tb_lim.text_frame
        tf_lim.word_wrap = True
        p = tf_lim.paragraphs[0]
        p.text = title
        p.font.name = FONT_FAMILY
        p.font.size = Pt(13)
        p.font.bold = True
        p.font.color.rgb = col

        p_l = tf_lim.add_paragraph()
        p_l.text = f"• {l_hdr}: {l_desc}"
        p_l.font.name = FONT_FAMILY
        p_l.font.size = Pt(10)
        p_l.font.color.rgb = TEXT_LIGHT
        p_l.space_before = Pt(3)

        p_p = tf_lim.add_paragraph()
        p_p.text = f"• {p_hdr}: {p_desc}"
        p_p.font.name = FONT_FAMILY
        p_p.font.size = Pt(10)
        p_p.font.color.rgb = PRIMARY_CYAN
        p_p.space_before = Pt(2)

        ly13 += 1.8

    # ==========================================
    # SLIDE 14: Conclusion
    # ==========================================
    s14 = prs.slides.add_slide(blank_layout)
    set_slide_background(s14)
    add_header(s14, "VisionInsight — 근거 기반 산업 비전 AI Agent 설계")

    add_card(s14, Inches(0.8), Inches(1.4), Inches(11.733), Inches(4.3), border_color=PRIMARY_CYAN)
    tb_c = s14.shapes.add_textbox(Inches(1.2), Inches(1.65), Inches(10.9), Inches(3.8))
    tf_c = tb_c.text_frame
    tf_c.word_wrap = True
    p = tf_c.paragraphs[0]
    p.text = "VisionInsight 핵심 아키텍처 요약"
    p.font.name = FONT_FAMILY
    p.font.size = Pt(18)
    p.font.bold = True
    p.font.color.rgb = PRIMARY_CYAN

    final_roles = [
        ("PatchCore", "이상 점수 산출 및 모델 판정 소견(result) 제공 (개발 환경 CPU 단일 이미지 평균 42.53ms 측정, ※ 사후 진단 보조)"),
        ("FastAPI", "서버 규칙 기반 최종 검사 판정(final_result: REINSPECT 분리) 확정 및 로컬 JSONL 기록 (Cloud Run 영구 저장은 GCS 연동 과제)"),
        ("Gemini", "Function Calling 도구 조회를 통한 근거 기반 사후 진단 및 권고안 제안 (사후 진단 보조)"),
        ("Python 서버", "엄격한 근거 검증(Evidence ID / JSON Pointer) 및 판정 불변 보호 정책으로 신뢰성 확보")
    ]
    for subject, desc in final_roles:
        p = tf_c.add_paragraph()
        p.text = f"✔ {subject}: {desc}"
        p.font.name = FONT_FAMILY
        p.font.size = Pt(12)
        p.font.bold = True
        p.font.color.rgb = TEXT_WHITE
        p.space_before = Pt(10)

    p_last = tf_c.add_paragraph()
    p_last.text = "\"AI가 검사 판정을 대신하는 것이 아니라, 검증된 검사 정보를 운영자가 이해하고 활용하도록 돕는 시스템\""
    p_last.font.name = FONT_FAMILY
    p_last.font.size = Pt(13)
    p_last.font.bold = True
    p_last.font.color.rgb = SUCCESS_GREEN
    p_last.space_before = Pt(16)

    # Closing banner
    add_card(s14, Inches(0.8), Inches(5.95), Inches(11.733), Inches(0.8), bg_color=CARD_BG_ALT, border_color=PRIMARY_CYAN)
    tb_end = s14.shapes.add_textbox(Inches(1.0), Inches(6.0), Inches(11.3), Inches(0.7))
    tf_end = tb_end.text_frame
    p_end = tf_end.paragraphs[0]
    p_end.text = "경청해 주셔서 감사합니다.  |  Q&A (질의응답)"
    p_end.font.name = FONT_FAMILY
    p_end.font.size = Pt(14)
    p_end.font.bold = True
    p_end.font.color.rgb = PRIMARY_CYAN
    p_end.alignment = PP_ALIGN.CENTER

    output_path = os.path.abspath("presentation/VisionInsight_Presentation_14slides_verified.pptx")
    prs.save(output_path)
    print(f"VisionInsight Presentation 14slides verified successfully created at: {output_path}")

if __name__ == "__main__":
    create_presentation_14slides_verified()

"""VisionInsight 기술 발표 자료 16장 통합 검증본 생성 스크립트 (ver2 개정판)
(16-Slide Verified Final Presentation with Updated Image Inspection & Grab Quality Improvement Slides)

기존 14장 구성에서 데모 시연(Slide 11) 직후 신규 슬라이드 2장 삽입:
- Slide 12: 현재 이미지 검사의 기술적 한계 (환경 차이, 평균 GV 한계, Heatmap 상대 정규화, Grab 화질 흐림)
- Slide 13: 이미지 검사 검출력 향상 전략 (A·B·C 전략 및 이번 주 4대 실행 계획)
- Slide 14~16: 기존 구현 현황, 한계 및 고찰, 결론 (총 16장)
"""

import os
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE

def create_presentation_16slides_verified_v2():
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
        cat_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.34), Inches(11.7), Inches(0.24))
        tf = cat_box.text_frame
        tf.word_wrap = True
        tf.margin_top = tf.margin_bottom = tf.margin_left = tf.margin_right = 0
        p = tf.paragraphs[0]
        p.text = category_text
        p.font.name = FONT_FAMILY
        p.font.size = Pt(10)
        p.font.bold = True
        p.font.color.rgb = PRIMARY_CYAN

        title_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.58), Inches(11.7), Inches(0.68))
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
    # SLIDE 1: Title Slide
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
    # SLIDE 2: Problem Definition
    # ==========================================
    s2 = prs.slides.add_slide(blank_layout)
    set_slide_background(s2)
    add_header(s2, "산업 비전 검사의 과제와 VisionInsight의 접근법")

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
        ("1. Vision Core Layer", PRIMARY_CYAN,
         "OpenCV 이미지 전처리 & 품질 분석 (밝기 81.24/135.86 등)",
         "PatchCore Anomaly Detection Engine (ResNet-18)",
         "개발 환경 CPU 단일 이미지 PatchCore 추론 평균: 42.53ms 측정 (※ 순수 모델 추론 시간)"),
        ("2. Decision Layer (FastAPI)", WARNING_AMBER,
         "독립 검사 식별자 발급 (INSP-001396 등)",
         "결정 규칙 기반 종합 판정 (OK / NG / REINSPECT / ERROR)",
         "품질 이상 시 모델 결함과 분리하여 'REINSPECT' 분류"),
        ("3. Storage & Audit Layer", TEXT_LIGHT,
         "검사 결과(data/inspections.jsonl) 및 실행 이벤트(data/inspection_logs.jsonl) 로컬 기록",
         "inspection_id 기반 추적 및 Evidence ID(E0001, E0002) 자동 발급",
         "평가 Ground Truth와 운영 데이터 엄격 분리 (※ 로컬 저장은 개발용, Cloud Run 영구 저장은 GCS 연동 과제)"),
        ("4. Diagnostic Agent Layer (Gemini)", SUCCESS_GREEN,
         "Gemini 3.8 Flash Function Calling 기반 사후 진단 도구 조회 제안",
         "서버의 허용 도구 검증·실행을 통한 사실 수집 및 토큰 카탈로그 기반 단순 JSON 생성",
         "Python 결정적 Evidence 검증을 통과한 보고서만 운영자 제공 (※ 판정 불변)")
    ]
    y_pos = 1.35
    for title, color, item1, item2, item3 in layers:
        add_card(s3, Inches(0.8), Inches(y_pos), Inches(11.733), Inches(1.18), border_color=color)
        tb = s3.shapes.add_textbox(Inches(1.0), Inches(y_pos + 0.05), Inches(11.3), Inches(1.08))
        tf = tb.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = title
        p.font.name = FONT_FAMILY
        p.font.size = Pt(13)
        p.font.bold = True
        p.font.color.rgb = color
        for itm in [item1, item2, item3]:
            pi = tf.add_paragraph()
            pi.text = "• " + itm
            pi.font.name = FONT_FAMILY
            pi.font.size = Pt(9.5)
            pi.font.color.rgb = TEXT_LIGHT
        y_pos += 1.25

    add_card(s3, Inches(0.8), Inches(6.45), Inches(11.733), Inches(0.65), bg_color=CARD_BG_ALT, border_color=PRIMARY_CYAN)
    tb_bot3 = s3.shapes.add_textbox(Inches(1.0), Inches(6.5), Inches(11.3), Inches(0.55))
    tf_bot3 = tb_bot3.text_frame
    tf_bot3.word_wrap = True
    p_bot3 = tf_bot3.paragraphs[0]
    p_bot3.text = "💡 안전 가드레일: 현재 시스템은 서버에서 검사 결과를 생성하고 판정값을 확정하는 프로토타입이며 실제 물리적 PLC, 배출기 제어는 수행하지 않습니다. AI Agent는 판정을 변경할 수 없습니다."
    p_bot3.font.name = FONT_FAMILY
    p_bot3.font.size = Pt(9.5)
    p_bot3.font.color.rgb = TEXT_LIGHT

    # ==========================================
    # SLIDE 4: Vision Engine Performance
    # ==========================================
    s4 = prs.slides.add_slide(blank_layout)
    set_slide_background(s4)
    add_header(s4, "Vision 엔진 성능: PatchCore 평가 및 엔지니어링 한계 분석")

    add_card(s4, Inches(0.8), Inches(1.4), Inches(5.7), Inches(5.3), border_color=PRIMARY_CYAN)
    tb_m = s4.shapes.add_textbox(Inches(1.1), Inches(1.65), Inches(5.1), Inches(4.8))
    tf_m = tb_m.text_frame
    tf_m.word_wrap = True
    p = tf_m.paragraphs[0]
    p.text = "핵심 성능 지표 (MVTec Bottle 83장 테스트셋)"
    p.font.name = FONT_FAMILY
    p.font.size = Pt(15)
    p.font.bold = True
    p.font.color.rgb = PRIMARY_CYAN

    metrics = [
        ("학습 데이터셋", "정상 이미지 180장 (비지도 학습, Coreset 서브샘플링)"),
        ("임계값 산출셋", "독립 정상 이미지 29장 통계 기반 (μ + 3σ = 34.1442)"),
        ("Image AUROC", "0.8286 (비지도 이상 탐지 벤치마크 지표)"),
        ("정밀도 (Precision)", "100.0% (83장 표본 내 실측치, 실전 전수 보장 아님)"),
        ("재현율 (Recall)", "50.79% (실제 불량 63건 중 32건 탐지, 31건 미탐지)"),
        ("CPU 단일 이미지 추론 시간", "평균 42.53ms (개발 환경 CPU 기준 실측)")
    ]
    for label, val in metrics:
        p = tf_m.add_paragraph()
        p.text = f"• {label}: {val}"
        p.font.name = FONT_FAMILY
        p.font.size = Pt(11)
        p.font.color.rgb = TEXT_WHITE
        p.space_before = Pt(8)

    p_warn4 = tf_m.add_paragraph()
    p_warn4.text = "※ 42.53ms는 개발 환경 CPU 단일 이미지 PatchCore 모델 추론 시간이며, 영상 Grab·ROI·FastAPI·Gemini 응답 및 생산라인 배출 제어는 미포함."
    p_warn4.font.name = FONT_FAMILY
    p_warn4.font.size = Pt(9.5)
    p_warn4.font.color.rgb = TEXT_MUTED
    p_warn4.space_before = Pt(12)

    add_card(s4, Inches(6.8), Inches(1.4), Inches(5.7), Inches(5.3), border_color=WARNING_AMBER)
    tb_c4 = s4.shapes.add_textbox(Inches(7.1), Inches(1.65), Inches(5.1), Inches(4.8))
    tf_c4 = tb_c4.text_frame
    tf_c4.word_wrap = True
    p = tf_c4.paragraphs[0]
    p.text = "혼동 행렬 및 엔지니어링 분석"
    p.font.name = FONT_FAMILY
    p.font.size = Pt(15)
    p.font.bold = True
    p.font.color.rgb = WARNING_AMBER

    analysis_points = [
        ("진양성(TP) 32건 / 진음성(TN) 20건", "정상 제품에 대한 과검(False Positive) 0건 달성"),
        ("위음성(FN) 31건 (미탐지 한계)", "미세 파손 및 미세 오염 31건 미탐지 (모델 OK != 무결점 제품)"),
        ("T06 미탐 사례 보존", "실제 파손 불량(T06)이 점수 32.27로 정상 합격 처리된 한계를 인위적 조작 없이 그대로 보존"),
        ("평가 문서 제약 보존", "과거 209장(46.17ms) 대비 현재 180장(42.53ms) 벤치마크 차이 및 contamination FN 표기 불일치는 현황 제약으로 보존"),
        ("정답 격리 & 설비 미제어", "실제 정답 라벨은 Agent에 미제공, 물리적 PLC 제어 미수행")
    ]
    for title, desc in analysis_points:
        p = tf_c4.add_paragraph()
        p.text = "• " + title
        p.font.name = FONT_FAMILY
        p.font.size = Pt(11)
        p.font.bold = True
        p.font.color.rgb = TEXT_WHITE
        p.space_before = Pt(6)
        p_d = tf_c4.add_paragraph()
        p_d.text = "   " + desc
        p_d.font.name = FONT_FAMILY
        p_d.font.size = Pt(9.5)
        p_d.font.color.rgb = TEXT_LIGHT

    # ==========================================
    # SLIDE 5: Decision Layer
    # ==========================================
    s5 = prs.slides.add_slide(blank_layout)
    set_slide_background(s5)
    add_header(s5, "Decision 계층: 대표 판정 규칙 4가지와 REINSPECT 분류")

    rules = [
        ("Rule 1: 파이프라인 실패", DANGER_CORAL, "ERROR", "INSPECTION_FAILED", "영상 로드 실패, 디코딩 오류 발생 시 즉시 중단"),
        ("Rule 2: 영상 품질 경고", WARNING_AMBER, "REINSPECT", "IMAGE_QUALITY_WARNING", "조도 저하(T03) 시 모델이 OK여도 재검사 분류"),
        ("Rule 4: 제품 이상 탐지", DANGER_CORAL, "NG", "PRODUCT_ANOMALY_DETECTED", "품질 정상 and 이상 점수 > 34.1442 초과"),
        ("Rule 5: 정상 검사 통과", SUCCESS_GREEN, "OK", "ALL_CHECKS_PASSED", "품질 정상 and 이상 점수 <= 34.1442 이하")
    ]
    col_w = Inches(2.7)
    gap = Inches(0.244)
    cx = 0.8
    for rtitle, col, verdict, reason, desc in rules:
        add_card(s5, Inches(cx), Inches(1.4), col_w, Inches(4.3), border_color=col)
        tb_r = s5.shapes.add_textbox(Inches(cx + 0.15), Inches(1.55), col_w - Inches(0.3), Inches(4.0))
        tf_r = tb_r.text_frame
        tf_r.word_wrap = True
        p = tf_r.paragraphs[0]
        p.text = rtitle
        p.font.name = FONT_FAMILY
        p.font.size = Pt(13)
        p.font.bold = True
        p.font.color.rgb = col

        p_v = tf_r.add_paragraph()
        p_v.text = f"\n판정: {verdict}"
        p_v.font.name = FONT_FAMILY
        p_v.font.size = Pt(16)
        p_v.font.bold = True
        p_v.font.color.rgb = col

        p_rsn = tf_r.add_paragraph()
        p_rsn.text = f"사유 코드:\n{reason}"
        p_rsn.font.name = FONT_FAMILY
        p_rsn.font.size = Pt(10)
        p_rsn.font.color.rgb = TEXT_LIGHT
        p_rsn.space_before = Pt(8)

        p_d = tf_r.add_paragraph()
        p_d.text = f"\n설명:\n{desc}"
        p_d.font.name = FONT_FAMILY
        p_d.font.size = Pt(10)
        p_d.font.color.rgb = TEXT_MUTED

        cx += 2.7 + 0.244

    add_card(s5, Inches(0.8), Inches(5.85), Inches(11.733), Inches(1.15), bg_color=CARD_BG_ALT, border_color=WARNING_AMBER)
    tb_note = s5.shapes.add_textbox(Inches(1.0), Inches(5.9), Inches(11.3), Inches(1.0))
    tf_n = tb_note.text_frame
    tf_n.word_wrap = True
    pn = tf_n.paragraphs[0]
    pn.text = "보충 규칙 및 설계 원칙:"
    pn.font.name = FONT_FAMILY
    pn.font.size = Pt(11)
    pn.font.bold = True
    pn.font.color.rgb = WARNING_AMBER

    pn_sub = tf_n.add_paragraph()
    pn_sub.text = "• Rule 3 [DEFECT_DETECTION_UNAVAILABLE]: 모델 미실행 시 미탐 제품 합격 차단  |  Rule 6 [UNKNOWN_STATE_COMBINATION]: 정의되지 않은 상태 안전 거부\n• REINSPECT는 물리적 폐기/격리 제어가 아닌 서버 판정 상태 분류이며, 현장 작업자의 재검 또는 조명 점검을 유도함"
    pn_sub.font.name = FONT_FAMILY
    pn_sub.font.size = Pt(9.5)
    pn_sub.font.color.rgb = TEXT_LIGHT

    # ==========================================
    # SLIDE 6: AI Agent Architecture
    # ==========================================
    s6 = prs.slides.add_slide(blank_layout)
    set_slide_background(s6)
    add_header(s6, "AI Agent: Gemini Function Calling 기반 정밀 조사 체계")

    tools = [
        ("get_inspection_result", "검사 기본 상태, 판정, 사유 코드 조회 (Evidence E0001)"),
        ("analyze_image_quality", "영상 품질 밝기 통계 및 min/max 동적범위 조회 (Evidence E0002)"),
        ("get_execution_logs", "실행 감사 이벤트 추적 (IMAGE_LOAD_FAILED 등 실패 원인 규명)"),
        ("get_inspection_history", "과거 동일 제품의 직전 검사 이력 트렌드 확인 (장애 반복성 추적)")
    ]
    y_pos6 = 1.4
    for tname, tdesc in tools:
        add_card(s6, Inches(0.8), Inches(y_pos6), Inches(5.7), Inches(1.15), border_color=PRIMARY_CYAN)
        tb_t = s6.shapes.add_textbox(Inches(1.0), Inches(y_pos6 + 0.1), Inches(5.3), Inches(0.95))
        tf_t = tb_t.text_frame
        tf_t.word_wrap = True
        p = tf_t.paragraphs[0]
        p.text = f"🔧 {tname}"
        p.font.name = FONT_FAMILY
        p.font.size = Pt(12.5)
        p.font.bold = True
        p.font.color.rgb = PRIMARY_CYAN
        p_d = tf_t.add_paragraph()
        p_d.text = tdesc
        p_d.font.name = FONT_FAMILY
        p_d.font.size = Pt(10)
        p_d.font.color.rgb = TEXT_LIGHT
        y_pos6 += 1.3

    add_card(s6, Inches(6.8), Inches(1.4), Inches(5.7), Inches(5.05), border_color=SUCCESS_GREEN)
    tb_flow = s6.shapes.add_textbox(Inches(7.1), Inches(1.65), Inches(5.1), Inches(4.6))
    tf_f = tb_flow.text_frame
    tf_f.word_wrap = True
    p = tf_f.paragraphs[0]
    p.text = "도구 실행 제어 흐름 (단방향 파이프라인)"
    p.font.name = FONT_FAMILY
    p.font.size = Pt(15)
    p.font.bold = True
    p.font.color.rgb = SUCCESS_GREEN

    flow_steps = [
        ("1. Gemini 도구 제안", "사용자 진단 요청 시 Gemini가 필요한 도구와 인자(inspection_id)를 제안"),
        ("2. 서버 인자 검증", "제안된 도구가 화이트리스트에 있는지, 파라미터가 유효한지 서버가 검증"),
        ("3. Python 도구 실행", "서버가 로컬 데이터 저장소에서 실제 검사 결과/로그를 조회하여 반환"),
        ("4. FunctionResponse 전달", "도구 실행 결과에 Evidence ID(E0001 등)를 부여하여 Gemini에 주입"),
        ("5. 최종 단순 JSON 생성", "Gemini는 카탈로그 토큰만 선택하여 간소화된 JSON 보고서 작성"),
        ("6. Pydantic 및 Evidence 검증", "서버가 JSON을 Pydantic 모델로 변환하고 1:1 결정적 근거 대조 통과 시 수락")
    ]
    for step, desc in flow_steps:
        p = tf_f.add_paragraph()
        p.text = f"• {step}: {desc}"
        p.font.name = FONT_FAMILY
        p.font.size = Pt(9.5)
        p.font.color.rgb = TEXT_WHITE
        p.space_before = Pt(6)

    add_card(s6, Inches(0.8), Inches(6.55), Inches(11.733), Inches(0.6), bg_color=CARD_BG_ALT, border_color=PRIMARY_CYAN)
    tb_b6 = s6.shapes.add_textbox(Inches(1.0), Inches(6.6), Inches(11.3), Inches(0.5))
    tf_b6 = tb_b6.text_frame
    p_b6 = tf_b6.paragraphs[0]
    p_b6.text = "💡 원칙: 모델이 도구를 호출하지 않았을 때 호출했다고 보고하지 않으며, 실제 반환된 실행 결과만을 기반으로 보고서를 작성합니다."
    p_b6.font.name = FONT_FAMILY
    p_b6.font.size = Pt(9.5)
    p_b6.font.color.rgb = TEXT_LIGHT

    # ==========================================
    # SLIDE 7: Evidence Mechanism
    # ==========================================
    s7 = prs.slides.add_slide(blank_layout)
    set_slide_background(s7)
    add_header(s7, "Evidence 메커니즘: 결정적 근거 검증을 통한 신뢰성 확보")

    pillars = [
        ("Pillar 1: Evidence ID", PRIMARY_CYAN, "서버 발급 고유 영수증 (E0001, E0002)", "도구 실행 시 서버가 발급한 영수증 ID로 허위 주장 원천 차단"),
        ("Pillar 2: Fact ID & Pointer", SUCCESS_GREEN, "구조화된 관측 사실 (F0001~) 및 JSON Pointer", "서버의 실제 도구 반환값과 JSON Pointer로 1:1 결정적 대조"),
        ("Pillar 3: 근거 앵커링", WARNING_AMBER, "모든 권장 조치에 근거 참조 필수 (evidence_refs)", "근거 없는 환각 조치를 차단하고 모든 제안을 검증 사실에 앵커링"),
        ("Pillar 4: 판정 불변성", DANGER_CORAL, "서버의 final_result 절대 수정 불가 정책", "Gemini는 사후 진단 보조만 수행하며 확정된 판정을 변경할 수 없음")
    ]
    cx7 = 0.8
    for ptitle, pcolor, phead, pdesc in pillars:
        add_card(s7, Inches(cx7), Inches(1.4), col_w, Inches(4.7), border_color=pcolor)
        tb_p = s7.shapes.add_textbox(Inches(cx7 + 0.15), Inches(1.6), col_w - Inches(0.3), Inches(4.3))
        tf_p = tb_p.text_frame
        tf_p.word_wrap = True
        p = tf_p.paragraphs[0]
        p.text = ptitle
        p.font.name = FONT_FAMILY
        p.font.size = Pt(13)
        p.font.bold = True
        p.font.color.rgb = pcolor

        p_h = tf_p.add_paragraph()
        p_h.text = f"\n{phead}"
        p_h.font.name = FONT_FAMILY
        p_h.font.size = Pt(11)
        p_h.font.bold = True
        p_h.font.color.rgb = TEXT_WHITE

        p_d = tf_p.add_paragraph()
        p_d.text = f"\n{pdesc}"
        p_d.font.name = FONT_FAMILY
        p_d.font.size = Pt(10)
        p_d.font.color.rgb = TEXT_LIGHT

        cx7 += 2.7 + 0.244

    add_card(s7, Inches(0.8), Inches(6.25), Inches(11.733), Inches(0.85), bg_color=CARD_BG_ALT, border_color=PRIMARY_CYAN)
    tb_b7 = s7.shapes.add_textbox(Inches(1.0), Inches(6.3), Inches(11.3), Inches(0.75))
    tf_b7 = tb_b7.text_frame
    tf_b7.word_wrap = True
    p_b7 = tf_b7.paragraphs[0]
    p_b7.text = "💡 실제 실서버 검증 성과: 4대 대표 시나리오 T01(6개), T03(12개), T05(17개), T06(6개)의 관측 사실 전원이 서버의 Evidence 및 JSON Pointer 검증을 통과했습니다."
    p_b7.font.name = FONT_FAMILY
    p_b7.font.size = Pt(10.5)
    p_b7.font.bold = True
    p_b7.font.color.rgb = TEXT_WHITE
    p_b7.alignment = PP_ALIGN.CENTER

    # ==========================================
    # SLIDE 8: Gemini Schema Optimization
    # ==========================================
    s8 = prs.slides.add_slide(blank_layout)
    set_slide_background(s8)
    add_header(s8, "기술적 문제 해결: Gemini 구조화 출력 호환성 개선")

    add_card(s8, Inches(0.8), Inches(1.4), Inches(5.7), Inches(5.3), border_color=DANGER_CORAL)
    tb_b8 = s8.shapes.add_textbox(Inches(1.1), Inches(1.65), Inches(5.1), Inches(4.8))
    tf_b8 = tb_b8.text_frame
    tf_b8.word_wrap = True
    p = tf_b8.paragraphs[0]
    p.text = "Before: 직접 구조화 출력 시도 ➔ HTTP 400"
    p.font.name = FONT_FAMILY
    p.font.size = Pt(15)
    p.font.bold = True
    p.font.color.rgb = DANGER_CORAL

    before_points = [
        ("직접 Pydantic 스키마 전송", "복잡한 Pydantic 스키마(DiagnosisDraft)를 response_json_schema로 Gemini API에 직접 전달"),
        ("서버 측 스키마 거부 (HTTP 400)", "Gemini 서버가 스키마 호환성 문제로 ClientError(HTTP 400) 반환 (정확한 거부 속성은 UNKNOWN)"),
        ("진단 파이프라인 전면 차단", "Agent가 사후 진단 보고서를 생성하지 못하고 전체 요청이 중단되는 핵심 장애 발생")
    ]
    for title, desc in before_points:
        p = tf_b8.add_paragraph()
        p.text = "• " + title
        p.font.name = FONT_FAMILY
        p.font.size = Pt(11.5)
        p.font.bold = True
        p.font.color.rgb = TEXT_WHITE
        p.space_before = Pt(12)
        p_d = tf_b8.add_paragraph()
        p_d.text = "   " + desc
        p_d.font.name = FONT_FAMILY
        p_d.font.size = Pt(10)
        p_d.font.color.rgb = TEXT_LIGHT

    add_card(s8, Inches(6.8), Inches(1.4), Inches(5.7), Inches(5.3), border_color=SUCCESS_GREEN)
    tb_a8 = s8.shapes.add_textbox(Inches(7.1), Inches(1.65), Inches(5.1), Inches(4.8))
    tf_a8 = tb_a8.text_frame
    tf_a8.word_wrap = True
    p = tf_a8.paragraphs[0]
    p.text = "After: 스키마 단순화 + Python 검증 ➔ PASS"
    p.font.name = FONT_FAMILY
    p.font.size = Pt(15)
    p.font.bold = True
    p.font.color.rgb = SUCCESS_GREEN

    after_points = [
        ("출력 스키마 단순화", "Gemini에는 필수 필드(summary, findings, action_plan)만 포함된 단순 JSON 스키마를 전송"),
        ("토큰 카탈로그 주입", "서버가 도구 실행으로 수집한 사실(K0001, K0002 등)을 프롬프트에 주입하고, 모델은 토큰만 선택"),
        ("Python 엄격 검증 파이프라인", "Gemini 출력 ➔ Python에서 DiagnosisDraft 변환 ➔ Pydantic 검증 ➔ 결정적 Evidence 검증 ➔ 최종 승인"),
        ("완벽한 호환성과 신뢰성 달성", "Gemini API 호환성을 100% 확보하면서도, 보고서의 엄격한 규격과 진실성을 Python 계층에서 완벽 보장")
    ]
    for title, desc in after_points:
        p = tf_a8.add_paragraph()
        p.text = "✔ " + title
        p.font.name = FONT_FAMILY
        p.font.size = Pt(11)
        p.font.bold = True
        p.font.color.rgb = SUCCESS_GREEN
        p.space_before = Pt(8)
        p_d = tf_a8.add_paragraph()
        p_d.text = "   " + desc
        p_d.font.name = FONT_FAMILY
        p_d.font.size = Pt(9.5)
        p_d.font.color.rgb = TEXT_LIGHT

    # ==========================================
    # SLIDE 9: Key Technical Challenges
    # ==========================================
    s9 = prs.slides.add_slide(blank_layout)
    set_slide_background(s9)
    add_header(s9, "핵심 기술 난제와 해결 과정", subtitle_text="Gemini API 연결보다 어려웠던 것은, 검증 가능한 Agent를 만드는 과정")

    col_w9 = Inches(3.7)
    cards9 = [
        ("카드 1: HTTP 400 — 스키마 호환성", DANGER_CORAL,
         "🚨 핵심 문제", "복잡한 Pydantic 스키마 직접 전달 시 HTTP 400 발생 (거부 속성 UNKNOWN)",
         "⚡ 해결 접근", "단순 JSON 생성 → Python 변환·검증 (토큰 카탈로그 주입 + 서버 엄격 규칙 검증)",
         "🎯 검증 결과", "대표 4개 시나리오 E2E 성공 회차 확보"),
        ("카드 2: HTTP 504 — 타임아웃 계측", WARNING_AMBER,
         "🚨 핵심 문제", "T03/T06 최종 생성 15s 초과 504 발생 (서버 내부 원인 UNKNOWN, 반복 안정성 과제)",
         "⚡ 해결 접근", "요청별 timeout 계측 및 분리 (조사 15s / 최종 JSON 30s 선택, 전체 60s)",
         "🎯 검증 결과", "T03(18.97s) & T06(24.12s) PASS (선택적 30초 설정 회차 성공, 504 직접 해결은 미확정)"),
        ("카드 3: E2E 완결 — 조기종료 & 불변성", PRIMARY_CYAN,
         "🚨 핵심 문제", "T05 3차조사 504 FAIL & T06 정답 격리 (T05 1회 FAIL 보존, T06 외부 정답 미제공)",
         "⚡ 해결 접근", "T05 전용 조기 종료 & T06 판정 가드레일 (17개 사실 즉시종료, final_result=OK 불변)",
         "🎯 검증 결과", "T05(16.33s) & T06(26.37s) PASS (T06 원본 ASGI 본문 미보관으로 재구성 코드 기반 검토 한계 명시)")
    ]
    cx9 = 0.8
    for ctitle, ccolor, p1_h, p1_d, p2_h, p2_d, p3_h, p3_d in cards9:
        add_card(s9, Inches(cx9), Inches(1.4), col_w9, Inches(4.5), border_color=ccolor)
        tb_c9 = s9.shapes.add_textbox(Inches(cx9 + 0.15), Inches(1.55), col_w9 - Inches(0.3), Inches(4.2))
        tf_c9 = tb_c9.text_frame
        tf_c9.word_wrap = True
        p = tf_c9.paragraphs[0]
        p.text = ctitle
        p.font.name = FONT_FAMILY
        p.font.size = Pt(13)
        p.font.bold = True
        p.font.color.rgb = ccolor

        for h, d in [(p1_h, p1_d), (p2_h, p2_d), (p3_h, p3_d)]:
            pi_h = tf_c9.add_paragraph()
            pi_h.text = f"\n{h}"
            pi_h.font.name = FONT_FAMILY
            pi_h.font.size = Pt(11)
            pi_h.font.bold = True
            pi_h.font.color.rgb = TEXT_WHITE

            pi_d = tf_c9.add_paragraph()
            pi_d.text = d
            pi_d.font.name = FONT_FAMILY
            pi_d.font.size = Pt(9.5)
            pi_d.font.color.rgb = TEXT_LIGHT

        cx9 += 3.7 + 0.3

    add_card(s9, Inches(0.8), Inches(6.05), Inches(11.733), Inches(0.85), bg_color=CARD_BG_ALT, border_color=PRIMARY_CYAN)
    tb_b9 = s9.shapes.add_textbox(Inches(1.0), Inches(6.1), Inches(11.3), Inches(0.75))
    tf_b9 = tb_b9.text_frame
    tf_b9.word_wrap = True
    p_b9 = tf_b9.paragraphs[0]
    p_b9.text = "💡 현황: T01·T03·T05·T06 대표 4개 시나리오에서 각각 실제 Gemini E2E 성공 회차 확보 (단일 성공 회차가 반복 실행 안정성을 보증하는 것은 아님) | 전체 pytest 1089 PASS / 4 SKIP"
    p_b9.font.name = FONT_FAMILY
    p_b9.font.size = Pt(10.5)
    p_b9.font.bold = True
    p_b9.font.color.rgb = TEXT_WHITE
    p_b9.alignment = PP_ALIGN.CENTER

    # ==========================================
    # SLIDE 10: E2E Verification Results
    # ==========================================
    s10 = prs.slides.add_slide(blank_layout)
    set_slide_background(s10)
    add_header(s10, "실제 Gemini API E2E 검증 결과: 4대 대표 시나리오 전원 성공 (PASS)")

    scenarios = [
        {"title": "T01 정상", "border": SUCCESS_GREEN, "status": "✔ E2E PASS (HTTP 200)", "status_color": SUCCESS_GREEN,
         "verdict": "최종 OK", "verdict_sub": "(모델 OK ➔ Rule 5)", "verdict_color": SUCCESS_GREEN,
         "total_time": "13.58초", "facts": "Fact 6개", "facts_sub": "100% 통과",
         "rule": "Rule 5 [ALL_CHECKS_PASSED]", "tools": "도구 1개 / 4,706 토큰", "action": "CONTINUE_MONITORING", "insp_id": "INSP-001396"},
        {"title": "T03 품질 경고", "border": WARNING_AMBER, "status": "✔ E2E PASS (HTTP 200)", "status_color": SUCCESS_GREEN,
         "verdict": "최종 REINSPECT", "verdict_sub": "(조도 저하 81.24 ➔ 재검)", "verdict_color": WARNING_AMBER,
         "total_time": "24.60초", "facts": "Fact 12개", "facts_sub": "100% 통과",
         "rule": "Rule 2 [IMAGE_QUALITY_WARNING]", "tools": "도구 2개 / 9,873 토큰", "action": "조명 점검 & 안전 재검사", "insp_id": "INSP-001398"},
        {"title": "T05 로드 실패", "border": DANGER_CORAL, "status": "✔ E2E PASS (HTTP 200)", "status_color": SUCCESS_GREEN,
         "verdict": "최종 ERROR", "verdict_sub": "(영상 손상 ➔ 조기 종료)", "verdict_color": DANGER_CORAL,
         "total_time": "16.33초", "facts": "Fact 17개", "facts_sub": "100% 통과",
         "rule": "Rule 1 [INSPECTION_FAILED]", "tools": "도구 2개 / 11,426 토큰", "action": "파일/카메라 점검 (오추론 방지)", "insp_id": "INSP-001405"},
        {"title": "T06 저장 OK", "border": PRIMARY_CYAN, "status": "✔ E2E PASS (HTTP 200)", "status_color": SUCCESS_GREEN,
         "verdict": "최종 OK (불변)", "verdict_sub": "(서버 원본 판정 보존)", "verdict_color": PRIMARY_CYAN,
         "total_time": "26.37초", "facts": "Fact 6개", "facts_sub": "100% 통과",
         "rule": "서버 판정 가드레일", "tools": "도구 1개 / 7,202 토큰", "action": "정답 미노출 & 판정 보존", "insp_id": "INSP-001406"}
    ]
    cx10 = 0.8
    for sc in scenarios:
        add_card(s10, Inches(cx10), Inches(1.35), Inches(2.75), Inches(4.45), border_color=sc["border"])
        tb_sc = s10.shapes.add_textbox(Inches(cx10 + 0.12), Inches(1.45), Inches(2.51), Inches(4.25))
        tf_sc = tb_sc.text_frame
        tf_sc.word_wrap = True

        p_t = tf_sc.paragraphs[0]
        p_t.text = sc["title"]
        p_t.font.name = FONT_FAMILY
        p_t.font.size = Pt(14)
        p_t.font.bold = True
        p_t.font.color.rgb = sc["border"]

        p_st = tf_sc.add_paragraph()
        p_st.text = sc["status"]
        p_st.font.name = FONT_FAMILY
        p_st.font.size = Pt(11)
        p_st.font.bold = True
        p_st.font.color.rgb = sc["status_color"]
        p_st.space_before = Pt(4)

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

        p_meta = tf_sc.add_paragraph()
        p_meta.text = f"• {sc['rule']}\n• {sc['tools']}\n• 권고: {sc['action']}\n• 검사 ID: {sc['insp_id']}"
        p_meta.font.name = FONT_FAMILY
        p_meta.font.size = Pt(9.5)
        p_meta.font.color.rgb = TEXT_LIGHT
        p_meta.space_before = Pt(8)

        cx10 += 2.75 + 0.244

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
    # SLIDE 11: Demo Presentation
    # ==========================================
    s11 = prs.slides.add_slide(blank_layout)
    set_slide_background(s11)
    add_header(s11, "발표 데모 시연: T01 양품 vs T03 조도 경고 정적 데모")

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
    # SLIDE 12 (NEW - v2): 현재 이미지 검사의 기술적 한계 (4개 영역 그리드)
    # ==========================================
    s12 = prs.slides.add_slide(blank_layout)
    set_slide_background(s12)
    add_header(s12, "현재 이미지 검사의 기술적 한계",
               category_text="VISIONINSIGHT  |  IMAGE INSPECTION & QUALITY LIMITATIONS",
               subtitle_text="학습-실검사 환경 차이 · 평균 밝기 지표 종속 · 상대 정규화 Heatmap · Grab 세부 화질 저하 분석")

    col_w12 = Inches(5.72)
    card_h12 = Inches(2.45)
    left_x12 = Inches(0.8)
    right_x12 = Inches(6.81)
    row1_y12 = Inches(1.35)
    row2_y12 = Inches(3.95)

    # 1. 학습 이미지 vs LiveView Grab 환경 차이 (좌측 상단)
    add_card(s12, left_x12, row1_y12, col_w12, card_h12, border_color=WARNING_AMBER)
    tb_1 = s12.shapes.add_textbox(left_x12 + Inches(0.18), row1_y12 + Inches(0.12), col_w12 - Inches(0.36), card_h12 - Inches(0.2))
    tf_1 = tb_1.text_frame
    tf_1.word_wrap = True
    p1 = tf_1.paragraphs[0]
    p1.text = "1. 학습 이미지 ↔ 실시간 LiveView Grab 환경 차이"
    p1.font.name = FONT_FAMILY
    p1.font.size = Pt(13.5)
    p1.font.bold = True
    p1.font.color.rgb = WARNING_AMBER

    items_1 = [
        ("배경 조명 및 촬영 조건 불일치", "정적 MVTec 원본은 균일한 밝은 단색 배경이나, LiveView Grab은 컨베이어 배경 명도와 조명 반사광이 상이함"),
        ("ROI 구도 및 제품 위치·크기 변동", "정적 영상(900×900 중앙 정렬)과 달리, LiveView Crop은 제품 위치·기울기 및 배경 여백 비율이 가변적임"),
        ("정상 제품의 영상 품질 경고 유발", "실제 결함이 없는 양품임에도 환경 차이로 인해 평균 GV 120 전후의 'WARNING_LOW_BRIGHTNESS' 관측")
    ]
    for t, d in items_1:
        p = tf_1.add_paragraph()
        p.text = "• " + t
        p.font.name = FONT_FAMILY
        p.font.size = Pt(10.5)
        p.font.bold = True
        p.font.color.rgb = TEXT_WHITE
        p.space_before = Pt(4)
        pd = tf_1.add_paragraph()
        pd.text = "   " + d
        pd.font.name = FONT_FAMILY
        pd.font.size = Pt(9)
        pd.font.color.rgb = TEXT_LIGHT

    # 2. 평균 밝기(GV) 평가의 구조적 한계 (우측 상단)
    add_card(s12, right_x12, row1_y12, col_w12, card_h12, border_color=DANGER_CORAL)
    tb_2 = s12.shapes.add_textbox(right_x12 + Inches(0.18), row1_y12 + Inches(0.12), col_w12 - Inches(0.36), card_h12 - Inches(0.2))
    tf_2 = tb_2.text_frame
    tf_2.word_wrap = True
    p2 = tf_2.paragraphs[0]
    p2.text = "2. 평균 밝기(GV) 평가의 구조적 한계"
    p2.font.name = FONT_FAMILY
    p2.font.size = Pt(13.5)
    p2.font.bold = True
    p2.font.color.rgb = DANGER_CORAL

    items_2 = [
        ("전체 ROI 단순 평균치의 왜곡", "현재 125.0 기준은 ROI 전체 평균치를 측정하므로, 어두운 병 내부와 밝은 배경 비율에 따라 크게 변동"),
        ("서버 최종 REINSPECT 판정 유발 흐름", "Grab 이미지 → 평균 GV 평가 (125 미만 시 경고) → PatchCore OK라도 서버가 'REINSPECT' 판정 확정"),
        ("품질 평가 지표 분리 필요성", "조명 결함과 제품 형상을 구분하기 위해 병 전경과 배경을 분리한 독립 평가 체계가 필수적임")
    ]
    for t, d in items_2:
        p = tf_2.add_paragraph()
        p.text = "• " + t
        p.font.name = FONT_FAMILY
        p.font.size = Pt(10.5)
        p.font.bold = True
        p.font.color.rgb = TEXT_WHITE
        p.space_before = Pt(4)
        pd = tf_2.add_paragraph()
        pd.text = "   " + d
        pd.font.name = FONT_FAMILY
        pd.font.size = Pt(9)
        pd.font.color.rgb = TEXT_LIGHT

    # 3. PatchCore 이상지도(Heatmap) 해석 시 주의점 (좌측 하단)
    add_card(s12, left_x12, row2_y12, col_w12, card_h12, border_color=PRIMARY_CYAN)
    tb_3 = s12.shapes.add_textbox(left_x12 + Inches(0.18), row2_y12 + Inches(0.12), col_w12 - Inches(0.36), card_h12 - Inches(0.2))
    tf_3 = tb_3.text_frame
    tf_3.word_wrap = True
    p3 = tf_3.paragraphs[0]
    p3.text = "3. PatchCore 이상지도(Heatmap) 해석 주의점"
    p3.font.name = FONT_FAMILY
    p3.font.size = Pt(13.5)
    p3.font.bold = True
    p3.font.color.rgb = PRIMARY_CYAN

    items_3 = [
        ("제품 밖 배경 영역의 이상 반응", "모델 특성상 제품 경계 밖 흰 배경 모서리 영역에도 이상 점수가 수학적으로 존재하여 배경 반응 발생"),
        ("이미지별 상대 정규화(Min-Max) 착시", "각 이미지의 최솟값·최댓값 기준으로 색상을 매핑하므로 미세 편차도 시각적으로 붉게 강조됨"),
        ("빨간 영역 ≠ 실제 불량 확정", "붉은색 표시는 상대적 이상도 분포일 뿐이며, 단독으로 물리적 결함을 확정하지 않음 (빨강 ≠ 결함)")
    ]
    for t, d in items_3:
        p = tf_3.add_paragraph()
        p.text = "• " + t
        p.font.name = FONT_FAMILY
        p.font.size = Pt(10.5)
        p.font.bold = True
        p.font.color.rgb = TEXT_WHITE
        p.space_before = Pt(4)
        pd = tf_3.add_paragraph()
        pd.text = "   " + d
        pd.font.name = FONT_FAMILY
        pd.font.size = Pt(9)
        pd.font.color.rgb = TEXT_LIGHT

    # 4. LiveView Grab 세부 화질 저하 현상 (우측 하단)
    add_card(s12, right_x12, row2_y12, col_w12, card_h12, border_color=PRIMARY_CYAN)
    tb_4 = s12.shapes.add_textbox(right_x12 + Inches(0.18), row2_y12 + Inches(0.12), col_w12 - Inches(0.36), card_h12 - Inches(0.2))
    tf_4 = tb_4.text_frame
    tf_4.word_wrap = True
    p4 = tf_4.paragraphs[0]
    p4.text = "4. 원본 대비 LiveView Grab 세부 화질 저하 현상"
    p4.font.name = FONT_FAMILY
    p4.font.size = Pt(13.5)
    p4.font.bold = True
    p4.font.color.rgb = PRIMARY_CYAN

    items_4 = [
        ("실제 이미지 비교 관찰 현상", "정적 원본 대비 LiveView Grab Crop에서 병 림(Rim) 윤곽선과 미세 표면 무늬가 흐릿하게 관측됨"),
        ("원인 후보 분리 분석 (미확정)", "화질 저하 경로: 원본 소스 → 영상 합성 → H.264 인코딩 → 디코딩·Grab → Crop 저장 → 뷰어 확대"),
        ("검증 전 단정 금지 원칙", "초점 불량으로 단정하지 않으며, 각 단계별(압축·리사이즈·보간) 정보 손실 기여도를 정량 측정 예정")
    ]
    for t, d in items_4:
        p = tf_4.add_paragraph()
        p.text = "• " + t
        p.font.name = FONT_FAMILY
        p.font.size = Pt(10.5)
        p.font.bold = True
        p.font.color.rgb = TEXT_WHITE
        p.space_before = Pt(4)
        pd = tf_4.add_paragraph()
        pd.text = "   " + d
        pd.font.name = FONT_FAMILY
        pd.font.size = Pt(9)
        pd.font.color.rgb = TEXT_LIGHT

    # Bottom Banner Slide 12
    add_card(s12, Inches(0.8), Inches(6.55), Inches(11.733), Inches(0.6), bg_color=CARD_BG_ALT, border_color=CARD_BORDER)
    tb_fact12 = s12.shapes.add_textbox(Inches(0.95), Inches(6.6), Inches(11.4), Inches(0.5))
    tf_f12 = tb_fact12.text_frame
    tf_f12.word_wrap = True
    p_f12 = tf_f12.paragraphs[0]
    p_f12.text = "💡 실증 사실과 과제: 영상 Grab, PatchCore 추론, Heatmap 생성, 서버 판정(OK/NG/REINSPECT)은 실제 성공 검증되었습니다. 다만 조도 경고, 상대 정규화 착시, Grab 세부 흐림은 실측 데이터를 통한 단계별 정량 규명 과제로 관리합니다."
    p_f12.font.name = FONT_FAMILY
    p_f12.font.size = Pt(9.5)
    p_f12.font.color.rgb = TEXT_MUTED

    # ==========================================
    # SLIDE 13 (NEW - v2): 이미지 검사 검출력 향상 전략 (A·B·C 및 이번 주 개선 계획)
    # ==========================================
    s13 = prs.slides.add_slide(blank_layout)
    set_slide_background(s13)
    add_header(s13, "이미지 검사 검출력 향상 전략",
               category_text="VISIONINSIGHT  |  ACCURACY ENHANCEMENT STRATEGY",
               subtitle_text="품질·화질 개선(A) · 현장 데이터 정합성(B) · 복합 보조 검사(C) 및 이번 주 실행 계획")

    col_w13 = Inches(3.7)
    card_top_y13 = Inches(1.35)
    card_top_h13 = Inches(3.85)

    # Card A: 이미지 품질·촬영 환경 개선
    add_card(s13, Inches(0.8), card_top_y13, col_w13, card_top_h13, border_color=PRIMARY_CYAN)
    tb_a = s13.shapes.add_textbox(Inches(0.95), card_top_y13 + Inches(0.12), Inches(3.4), card_top_h13 - Inches(0.2))
    tf_a = tb_a.text_frame
    tf_a.word_wrap = True
    pa = tf_a.paragraphs[0]
    pa.text = "A. 이미지 품질·촬영 환경 개선"
    pa.font.name = FONT_FAMILY
    pa.font.size = Pt(14)
    pa.font.bold = True
    pa.font.color.rgb = PRIMARY_CYAN

    pa_sub = tf_a.add_paragraph()
    pa_sub.text = "[전경/배경 분리 & 선명도 개선]"
    pa_sub.font.name = FONT_FAMILY
    pa_sub.font.size = Pt(9.5)
    pa_sub.font.color.rgb = TEXT_MUTED
    pa_sub.space_before = Pt(2)

    card_a_items = [
        ("병 영역/배경 분리 품질 지표", "병 내부 GV, 배경 GV, 대비를 분리 측정하여 불필요한 REINSPECT 오경보 차단"),
        ("ROI 및 조명 조건 표준화", "병 중심 정렬 알고리즘 도입, 반사광 제어 및 Crop 주변 여백 비율 안정화"),
        ("Grab 화질·선명도 개선", "원본·영상·Crop 단계별 해상도 추적 및 병 림 라플라시안 분산 지표 정량 비교"),
        ("미세 결함 표현력 비교", "동일 결함 표본으로 원본 vs Grab의 작은 크랙·칩핑 가시성 손실 여부 확인")
    ]
    for t, d in card_a_items:
        p = tf_a.add_paragraph()
        p.text = "• " + t
        p.font.name = FONT_FAMILY
        p.font.size = Pt(10.5)
        p.font.bold = True
        p.font.color.rgb = TEXT_WHITE
        p.space_before = Pt(6)
        pd = tf_a.add_paragraph()
        pd.text = "   " + d
        pd.font.name = FONT_FAMILY
        pd.font.size = Pt(9)
        pd.font.color.rgb = TEXT_LIGHT

    # Card B: 검사 데이터와 모델 평가 개선
    add_card(s13, Inches(4.8), card_top_y13, col_w13, card_top_h13, border_color=WARNING_AMBER)
    tb_b = s13.shapes.add_textbox(Inches(4.95), card_top_y13 + Inches(0.12), Inches(3.4), card_top_h13 - Inches(0.2))
    tf_b = tb_b.text_frame
    tf_b.word_wrap = True
    pb = tf_b.paragraphs[0]
    pb.text = "B. 검사 데이터 & 평가 개선"
    pb.font.name = FONT_FAMILY
    pb.font.size = Pt(14)
    pb.font.bold = True
    pb.font.color.rgb = WARNING_AMBER

    pb_sub = tf_b.add_paragraph()
    pb_sub.text = "[현장 데이터셋 구축 & 재평가]"
    pb_sub.font.name = FONT_FAMILY
    pb_sub.font.size = Pt(9.5)
    pb_sub.font.color.rgb = TEXT_MUTED
    pb_sub.space_before = Pt(2)

    card_b_items = [
        ("Grab 독립 검증 데이터셋 확충", "정상·불량(파손/이물)·저품질 Grab 독립 수집 및 정답 라벨 엄격 분리"),
        ("영상 환경-학습 데이터 차이 분석", "컨베이어 LiveView 영상과 기존 MVTec 학습셋의 조명·배경 도메인 편차 분석"),
        ("고정 모델 기반 정량 재평가", "PatchCore 모델을 고정한 상태에서 Precision, Recall, 오탐(FP), 미검(FN) 실측"),
        ("실측 기반 임계값 재보정 검토", "임의 수치 변경 엄금, 독립 평가셋의 실측 ROC/PR 곡선 근거 34.1442 재보정 검토")
    ]
    for t, d in card_b_items:
        p = tf_b.add_paragraph()
        p.text = "• " + t
        p.font.name = FONT_FAMILY
        p.font.size = Pt(10.5)
        p.font.bold = True
        p.font.color.rgb = TEXT_WHITE
        p.space_before = Pt(6)
        pd = tf_b.add_paragraph()
        pd.text = "   " + d
        pd.font.name = FONT_FAMILY
        pd.font.size = Pt(9)
        pd.font.color.rgb = TEXT_LIGHT

    # Card C: 복합 검사 기술 보강
    add_card(s13, Inches(8.8), card_top_y13, col_w13, card_top_h13, border_color=SUCCESS_GREEN)
    tb_c = s13.shapes.add_textbox(Inches(8.95), card_top_y13 + Inches(0.12), Inches(3.4), card_top_h13 - Inches(0.2))
    tf_c = tb_c.text_frame
    tf_c.word_wrap = True
    pc = tf_c.paragraphs[0]
    pc.text = "C. 복합 검사 기술 보강"
    pc.font.name = FONT_FAMILY
    pc.font.size = Pt(14)
    pc.font.bold = True
    pc.font.color.rgb = SUCCESS_GREEN

    pc_sub = tf_c.add_paragraph()
    pc_sub.text = "[Edge 검출 & 다중 교차 검증]"
    pc_sub.font.name = FONT_FAMILY
    pc_sub.font.size = Pt(9.5)
    pc_sub.font.color.rgb = TEXT_MUTED
    pc_sub.space_before = Pt(2)

    card_c_items = [
        ("병 외곽 Edge 및 림 검출", "병 외곽 윤곽선 및 내부 림(Rim) 경계를 검출하여 구조적 형상 특징 추출"),
        ("병 영역 검출 정확도 검증", "병 마스킹 시각화 오버레이 정확도 검증 및 영역별 Heatmap 통계 분리 산출"),
        ("OpenCV 기하학적 보조 검사", "병 입구 원형도, 편심, 림 파손, 테두리 불균일 보조 규칙 병렬 실험"),
        ("Gemini Vision Judge 2차 참고", "실호출 성공한 Gemini 시각 분석을 독립 2차 참고 소견으로 활용 (서버 판정 대체 불가)")
    ]
    for t, d in card_c_items:
        p = tf_c.add_paragraph()
        p.text = "• " + t
        p.font.name = FONT_FAMILY
        p.font.size = Pt(10.5)
        p.font.bold = True
        p.font.color.rgb = TEXT_WHITE
        p.space_before = Pt(6)
        pd = tf_c.add_paragraph()
        pd.text = "   " + d
        pd.font.name = FONT_FAMILY
        pd.font.size = Pt(9)
        pd.font.color.rgb = TEXT_LIGHT

    # Bottom Area: 이번 주 개선 계획 (4대 실행 과제 칩 형태)
    bot_y13 = Inches(5.35)
    bot_h13 = Inches(1.8)
    add_card(s13, Inches(0.8), bot_y13, Inches(11.733), bot_h13, bg_color=CARD_BG_ALT, border_color=PRIMARY_CYAN)

    tb_plan_title = s13.shapes.add_textbox(Inches(1.0), bot_y13 + Inches(0.08), Inches(11.3), Inches(0.3))
    tf_pt = tb_plan_title.text_frame
    tf_pt.word_wrap = True
    ppt = tf_pt.paragraphs[0]
    ppt.text = "🎯 이번 주 핵심 실행 계획 (Weekly Action Plan — 현황 검증 및 오프라인 실험)"
    ppt.font.name = FONT_FAMILY
    ppt.font.size = Pt(11)
    ppt.font.bold = True
    ppt.font.color.rgb = PRIMARY_CYAN

    plans = [
        ("1. 병 테두리 검출·오버레이 검증", "Grab 이미지 병 외곽·림 Edge 검출 및 시각화 정확도 측정"),
        ("2. 단계별 선명도 비교·개선", "원본→영상→Crop 단계별 라플라시안 분산 측정 및 손실 분석"),
        ("3. 전경/배경 품질 평가 실험", "병 영역과 배경을 분리한 GV 지표의 오프라인 비교 평가"),
        ("4. 검증 데이터 구축 및 재평가", "정상·불량 Grab 표본 확보 및 PatchCore의 FP/FN 수치 실측")
    ]
    chip_w13 = Inches(2.7)
    chip_gap13 = Inches(0.17)
    chip_x13 = Inches(1.0)
    chip_y13 = bot_y13 + Inches(0.42)
    chip_h13 = Inches(0.85)

    for p_title, p_desc in plans:
        add_card(s13, chip_x13, chip_y13, chip_w13, chip_h13, bg_color=CARD_BG, border_color=CARD_BORDER)
        tb_cp = s13.shapes.add_textbox(chip_x13 + Inches(0.08), chip_y13 + Inches(0.06), chip_w13 - Inches(0.16), chip_h13 - Inches(0.12))
        tf_cp = tb_cp.text_frame
        tf_cp.word_wrap = True
        pcp0 = tf_cp.paragraphs[0]
        pcp0.text = p_title
        pcp0.font.name = FONT_FAMILY
        pcp0.font.size = Pt(9.5)
        pcp0.font.bold = True
        pcp0.font.color.rgb = TEXT_WHITE

        pcp1 = tf_cp.add_paragraph()
        pcp1.text = p_desc
        pcp1.font.name = FONT_FAMILY
        pcp1.font.size = Pt(8.5)
        pcp1.font.color.rgb = TEXT_LIGHT
        pcp1.space_before = Pt(2)

        chip_x13 += chip_w13 + chip_gap13

    tb_fn = s13.shapes.add_textbox(Inches(1.0), bot_y13 + Inches(1.35), Inches(11.3), Inches(0.35))
    tf_fn = tb_fn.text_frame
    pfn = tf_fn.paragraphs[0]
    pfn.text = "※ 위 항목은 이번 주 진행 목표이며 구현 완료나 검출률 향상이 확정된 결과가 아닙니다. 기존 코드·임계값은 근거 없이 변경하지 않습니다."
    pfn.font.name = FONT_FAMILY
    pfn.font.size = Pt(9)
    pfn.font.color.rgb = TEXT_MUTED

    # ==========================================
    # SLIDE 14 (OLD SLIDE 12): Implementation Status & Roadmap
    # ==========================================
    s14 = prs.slides.add_slide(blank_layout)
    set_slide_background(s14)
    add_header(s14, "구현 현황 및 향후 계획 (투명한 검증 상태 구분)")

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
    cx14 = 0.8
    for ctitle, ccol, citems in cols_data_final:
        add_card(s14, Inches(cx14), Inches(1.38), col_width, Inches(5.32), border_color=ccol)
        tb_col = s14.shapes.add_textbox(Inches(cx14 + 0.16), Inches(1.50), col_width - Inches(0.32), Inches(5.1))
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

        cx14 += 4.0

    # ==========================================
    # SLIDE 15 (OLD SLIDE 13): Engineering Limitations
    # ==========================================
    s15 = prs.slides.add_slide(blank_layout)
    set_slide_background(s15)
    add_header(s15, "한계 및 향후 개선 계획: 솔직한 엔지니어링 고찰")

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
    ly15 = 1.4
    for title, col, l_hdr, l_desc, p_hdr, p_desc in limits:
        add_card(s15, Inches(0.8), Inches(ly15), Inches(11.733), Inches(1.6), border_color=col)
        tb_lim = s15.shapes.add_textbox(Inches(1.0), Inches(ly15 + 0.1), Inches(11.3), Inches(1.4))
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

        ly15 += 1.8

    # ==========================================
    # SLIDE 16 (OLD SLIDE 14): Conclusion
    # ==========================================
    s16 = prs.slides.add_slide(blank_layout)
    set_slide_background(s16)
    add_header(s16, "VisionInsight — 근거 기반 산업 비전 AI Agent 설계")

    add_card(s16, Inches(0.8), Inches(1.4), Inches(11.733), Inches(4.3), border_color=PRIMARY_CYAN)
    tb_c = s16.shapes.add_textbox(Inches(1.2), Inches(1.65), Inches(10.9), Inches(3.8))
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

    add_card(s16, Inches(0.8), Inches(5.95), Inches(11.733), Inches(0.8), bg_color=CARD_BG_ALT, border_color=PRIMARY_CYAN)
    tb_end = s16.shapes.add_textbox(Inches(1.0), Inches(6.0), Inches(11.3), Inches(0.7))
    tf_end = tb_end.text_frame
    p_end = tf_end.paragraphs[0]
    p_end.text = "경청해 주셔서 감사합니다.  |  Q&A (질의응답)"
    p_end.font.name = FONT_FAMILY
    p_end.font.size = Pt(14)
    p_end.font.bold = True
    p_end.font.color.rgb = PRIMARY_CYAN
    p_end.alignment = PP_ALIGN.CENTER

    output_path = os.path.abspath("presentation/VisionInsight_Presentation_16slides_verified_v2.pptx")
    prs.save(output_path)
    print(f"VisionInsight Presentation 16slides verified v2 successfully created at: {output_path}")

if __name__ == "__main__":
    create_presentation_16slides_verified_v2()

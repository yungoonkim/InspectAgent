"""VisionInsight 프레젠테이션 PPTX 생성 스크립트
16:9 와이드스크린, Industrial Dark 테마, 13장 슬라이드 완전 생성
"""

import os
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

def create_presentation():
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank_layout = prs.slide_layouts[6]

    # Color Palette (DesignA Industrial Dark Navy)
    BG_COLOR = RGBColor(12, 19, 34)          # #0C1322
    CARD_BG = RGBColor(25, 31, 47)           # #191F2F
    CARD_BORDER = RGBColor(51, 65, 85)       # #334155
    CARD_BG_ALT = RGBColor(20, 27, 43)       # #141B2B
    PRIMARY_CYAN = RGBColor(76, 215, 246)    # #4CD7F6
    SECONDARY_GREEN = RGBColor(78, 222, 163) # #4EDEA3
    ACCENT_AMBER = RGBColor(251, 191, 36)    # #FBBF24
    TEXT_WHITE = RGBColor(255, 255, 255)
    TEXT_LIGHT = RGBColor(220, 226, 247)     # #DCE2F7
    TEXT_MUTED = RGBColor(148, 163, 184)     # #94A3B8
    TEXT_CORAL = RGBColor(255, 180, 171)     # #FFB4AB

    FONT_FAMILY = "Malgun Gothic"

    def set_slide_background(slide):
        bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), prs.slide_width, prs.slide_height)
        bg.fill.solid()
        bg.fill.fore_color.rgb = BG_COLOR
        bg.line.color.rgb = BG_COLOR
        return bg

    def add_header(slide, title_text, category_text="VISIONINSIGHT TECHNICAL PRESENTATION"):
        # Category / Overline
        cat_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.4), Inches(11.7), Inches(0.3))
        tf = cat_box.text_frame
        tf.word_wrap = True
        tf.margin_top = tf.margin_bottom = tf.margin_left = tf.margin_right = 0
        p = tf.paragraphs[0]
        p.text = category_text
        p.font.name = FONT_FAMILY
        p.font.size = Pt(10)
        p.font.bold = True
        p.font.color.rgb = PRIMARY_CYAN

        # Title
        title_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.65), Inches(11.7), Inches(0.6))
        tf_t = title_box.text_frame
        tf_t.word_wrap = True
        tf_t.margin_top = tf_t.margin_bottom = tf_t.margin_left = tf_t.margin_right = 0
        p_t = tf_t.paragraphs[0]
        p_t.text = title_text
        p_t.font.name = FONT_FAMILY
        p_t.font.size = Pt(20)
        p_t.font.bold = True
        p_t.font.color.rgb = TEXT_WHITE

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

    # Decorative accent card
    add_card(s1, Inches(0.8), Inches(1.2), Inches(11.733), Inches(5.2), bg_color=CARD_BG_ALT, border_color=CARD_BORDER)

    # Title Box
    tbox = s1.shapes.add_textbox(Inches(1.3), Inches(1.8), Inches(10.7), Inches(2.2))
    tf = tbox.text_frame
    tf.word_wrap = True
    p0 = tf.paragraphs[0]
    p0.text = "VisionInsight"
    p0.font.name = FONT_FAMILY
    p0.font.size = Pt(44)
    p0.font.bold = True
    p0.font.color.rgb = PRIMARY_CYAN

    p1 = tf.add_paragraph()
    p1.text = "산업용 Vision 검사 이상 진단 AI Agent 서비스"
    p1.font.name = FONT_FAMILY
    p1.font.size = Pt(24)
    p1.font.bold = True
    p1.font.color.rgb = TEXT_WHITE
    p1.space_before = Pt(8)

    p2 = tf.add_paragraph()
    p2.text = "MVTec AD Bottle 기반 비지도 이상 탐지(PatchCore)와 Gemini Function Calling의 결합"
    p2.font.name = FONT_FAMILY
    p2.font.size = Pt(14)
    p2.font.color.rgb = TEXT_LIGHT
    p2.space_before = Pt(12)

    # Badges container
    badges = [
        ("Python 3.11", PRIMARY_CYAN),
        ("FastAPI", SECONDARY_GREEN),
        ("Anomalib PatchCore (CPU 42ms)", ACCENT_AMBER),
        ("Gemini 3.8 Flash", PRIMARY_CYAN),
        ("661 Tests PASS (100%)", SECONDARY_GREEN)
    ]
    bx = 1.3
    for btext, bcol in badges:
        bcard = add_card(s1, Inches(bx), Inches(4.3), Inches(2.1), Inches(0.45), bg_color=CARD_BG, border_color=bcol)
        tb = s1.shapes.add_textbox(Inches(bx), Inches(4.3), Inches(2.1), Inches(0.45))
        tf_b = tb.text_frame
        tf_b.margin_top = Inches(0.08)
        p = tf_b.paragraphs[0]
        p.text = btext
        p.font.name = FONT_FAMILY
        p.font.size = Pt(10)
        p.font.bold = True
        p.font.color.rgb = bcol
        p.alignment = PP_ALIGN.CENTER
        bx += 2.2

    # Footer Info
    fbox = s1.shapes.add_textbox(Inches(1.3), Inches(5.3), Inches(10.7), Inches(0.6))
    tf_f = fbox.text_frame
    p_f = tf_f.paragraphs[0]
    p_f.text = "발표 일자: 2026년 10월 20일  |  프로젝트: VisionInsight Engineering Team"
    p_f.font.name = FONT_FAMILY
    p_f.font.size = Pt(11)
    p_f.font.color.rgb = TEXT_MUTED

    # ==========================================
    # SLIDE 2: Problem Definition
    # ==========================================
    s2 = prs.slides.add_slide(blank_layout)
    set_slide_background(s2)
    add_header(s2, "개발 배경 및 문제 정의: 머신러닝 비전 검사의 한계와 현장의 병목")

    # Left Card: Existing Pain Points
    add_card(s2, Inches(0.8), Inches(1.4), Inches(5.7), Inches(5.3))
    tb_l = s2.shapes.add_textbox(Inches(1.1), Inches(1.6), Inches(5.1), Inches(4.9))
    tf_l = tb_l.text_frame
    tf_l.word_wrap = True
    p = tf_l.paragraphs[0]
    p.text = "기존 인라인 비전 검사의 치명적 한계"
    p.font.name = FONT_FAMILY
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = TEXT_CORAL

    points_l = [
        ("블랙박스 이상 점수 (No Explainability)", "점수(예: 35.2)만 출력되고 결함의 구체적 원인이나 위치를 설명하지 못함"),
        ("환경 변화로 인한 오판 (False Positive)", "조명 조도 저하나 렌즈 오염을 제품 결함으로 오진단하여 정상 제품을 폐기"),
        ("숙련자 수작업 개입 의존 (Operational Cost)", "결함 발생 시 원인 분석 및 설비 점검을 위해 전문 엔지니어 수작업 필수"),
        ("불량 데이터 수집의 한계 (Data Scarcity)", "양품에 비해 불량 데이터가 극히 적어 지도 학습 기반 딥러닝 적용 불가")
    ]
    for title, desc in points_l:
        p = tf_l.add_paragraph()
        p.text = "• " + title
        p.font.name = FONT_FAMILY
        p.font.size = Pt(12)
        p.font.bold = True
        p.font.color.rgb = TEXT_WHITE
        p.space_before = Pt(12)
        p_sub = tf_l.add_paragraph()
        p_sub.text = "   " + desc
        p_sub.font.name = FONT_FAMILY
        p_sub.font.size = Pt(10)
        p_sub.font.color.rgb = TEXT_MUTED

    # Right Card: VisionInsight Approach
    add_card(s2, Inches(6.8), Inches(1.4), Inches(5.7), Inches(5.3))
    tb_r = s2.shapes.add_textbox(Inches(7.1), Inches(1.6), Inches(5.1), Inches(4.9))
    tf_r = tb_r.text_frame
    tf_r.word_wrap = True
    p = tf_r.paragraphs[0]
    p.text = "VisionInsight의 해결 접근법"
    p.font.name = FONT_FAMILY
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = SECONDARY_GREEN

    points_r = [
        ("비지도 이상 탐지 (PatchCore)", "양품 이미지 180장만으로 학습하여 미지의 결함까지 고속 탐지 (CPU 42ms)"),
        ("제품 결함과 영상 품질의 완전 분리", "조도 저하 시 불량(NG)이 아닌 재검사(REINSPECT)를 지시하는 규칙 기반 종합 판정"),
        ("자율 조사 Gemini AI Agent", "검사 결과, 조도 지표, 감사 로그를 도구로 자율 조회하여 원인과 대처 가이드 제시"),
        ("결정적 근거 검증 (Grounding)", "Evidence ID와 JSON Pointer로 입증된 사실만 보고서에 포함 (환각 억제)")
    ]
    for title, desc in points_r:
        p = tf_r.add_paragraph()
        p.text = "✔ " + title
        p.font.name = FONT_FAMILY
        p.font.size = Pt(12)
        p.font.bold = True
        p.font.color.rgb = PRIMARY_CYAN
        p.space_before = Pt(12)
        p_sub = tf_r.add_paragraph()
        p_sub.text = "   " + desc
        p_sub.font.name = FONT_FAMILY
        p_sub.font.size = Pt(10)
        p_sub.font.color.rgb = TEXT_LIGHT

    # ==========================================
    # SLIDE 3: System Architecture
    # ==========================================
    s3 = prs.slides.add_slide(blank_layout)
    set_slide_background(s3)
    add_header(s3, "전체 시스템 아키텍처: 3단계 책임 분리 (Vision — Decision — Agent)")

    layers = [
        ("Layer 1: Inspection Engine (Vision & ML)", 
         "OpenCV 영상 품질 분석 & PatchCore CPU 고속 추론", 
         PRIMARY_CYAN,
         ["중립 식별자 매핑 (IMG-BOTTLE-XXXX로 정답 완벽 은닉)",
          "OpenCV 실시간 밝기 통계(mean, std, min, max) 산출",
          "ResNet-18 PatchCore 비지도 결함 추론 (단일 42.5ms)",
          "이상 점수(anomaly_score) 및 모델 판정(result: OK/NG) 도출"]),

        ("Layer 2: Deterministic Decision Engine (Business Logic)", 
         "규칙 기반 6대 산업용 종합 판정 & JSONL 감사 추적", 
         SECONDARY_GREEN,
         ["제품 결함과 영상 품질을 결합한 final_result 도출",
          "조도 저하 시 불량 오판을 방지하고 REINSPECT(재검사) 지시",
          "결정론적 비즈니스 규칙 (backend/decision.py) 집행",
          "스레드 세이프 JSONL 이중 영구화 (inspections.jsonl & logs.jsonl)"]),

        ("Layer 3: Gemini AI Agent Service (Post-Diagnosis)", 
         "Gemini Function Calling & 결정적 근거 기반 사후 진단", 
         ACCENT_AMBER,
         ["사후 분석 API (POST /analyze/{inspection_id})",
          "4대 Python 도구 자율 호출 (결과, 밝기, 로그, 이력)",
          "Evidence ID 및 JSON Pointer 기반 Deterministic Grounding",
          "454B 단순 JSON 스키마 전송 + 서버 Python 엄격 검증"])
    ]

    top_y = 1.4
    for ltitle, lsub, lcol, items in layers:
        add_card(s3, Inches(0.8), Inches(top_y), Inches(11.733), Inches(1.65), bg_color=CARD_BG, border_color=lcol)
        tb = s3.shapes.add_textbox(Inches(1.1), Inches(top_y + 0.1), Inches(11.1), Inches(1.45))
        tf = tb.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = ltitle + "  |  " + lsub
        p.font.name = FONT_FAMILY
        p.font.size = Pt(13)
        p.font.bold = True
        p.font.color.rgb = lcol

        # Bullets in 2 columns
        p_b = tf.add_paragraph()
        p_b.text = f"• {items[0]}    |    • {items[1]}"
        p_b.font.name = FONT_FAMILY
        p_b.font.size = Pt(10)
        p_b.font.color.rgb = TEXT_LIGHT
        p_b.space_before = Pt(6)

        p_b2 = tf.add_paragraph()
        p_b2.text = f"• {items[2]}    |    • {items[3]}"
        p_b2.font.name = FONT_FAMILY
        p_b2.font.size = Pt(10)
        p_b2.font.color.rgb = TEXT_MUTED
        p_b2.space_before = Pt(3)

        top_y += 1.8

    # ==========================================
    # SLIDE 4: PatchCore & ML Evaluation
    # ==========================================
    s4 = prs.slides.add_slide(blank_layout)
    set_slide_background(s4)
    add_header(s4, "비지도 이상 탐지: PatchCore 엔진 및 실측 평가 성능")

    # Left: Model Architecture Specs
    add_card(s4, Inches(0.8), Inches(1.4), Inches(5.6), Inches(5.3))
    tb_ml = s4.shapes.add_textbox(Inches(1.1), Inches(1.6), Inches(5.0), Inches(4.9))
    tf_ml = tb_ml.text_frame
    tf_ml.word_wrap = True
    p = tf_ml.paragraphs[0]
    p.text = "PatchCore 모델 구성 및 CPU 최적화"
    p.font.name = FONT_FAMILY
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = PRIMARY_CYAN

    specs = [
        ("학습 데이터", "MVTec Bottle 양품(good) 180장 Coreset 서브샘플링"),
        ("백본 모델", "ResNet-18 (ImageNet 사전학습 가중치)"),
        ("메모리 뱅크", "형상 [9216, 384], 체크포인트 크기 단 24.18MB"),
        ("추론 지연시간", "x86 CPU 기준 단일 이미지 평균 42.53ms (초당 23 FPS)"),
        ("결정 임계값", "독립 검증 29장 통계 기반 34.1442 (μ + 3σ) 고정"),
        ("하드웨어 요구", "산업용 고가 GPU 불필요, 가벼운 CPU만으로 구동")
    ]
    for k, v in specs:
        p = tf_ml.add_paragraph()
        p.text = f"• {k}: {v}"
        p.font.name = FONT_FAMILY
        p.font.size = Pt(11)
        p.font.color.rgb = TEXT_LIGHT
        p.space_before = Pt(10)

    # Right: Real Evaluation Metrics (83 images)
    add_card(s4, Inches(6.8), Inches(1.4), Inches(5.7), Inches(5.3))
    tb_eval = s4.shapes.add_textbox(Inches(7.1), Inches(1.6), Inches(5.1), Inches(4.9))
    tf_ev = tb_eval.text_frame
    tf_ev.word_wrap = True
    p = tf_ev.paragraphs[0]
    p.text = "독립 테스트 세트 (83장) 실측 평가 지표"
    p.font.name = FONT_FAMILY
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = SECONDARY_GREEN

    metrics = [
        ("Image AUROC", "0.8286", "이상 점수의 양품/불량 분별력 지표", PRIMARY_CYAN),
        ("정밀도 (Precision)", "100.0%", "모델 NG 판정 중 실제 불량 비율 (FP = 0)", SECONDARY_GREEN),
        ("재현율 (Recall)", "50.79%", "실제 불량 63장 중 32장 검출 (FN = 31)", ACCENT_AMBER),
        ("F1-Score", "0.6737", "정밀도와 재현율의 조화 평균", TEXT_LIGHT),
        ("정확도 (Accuracy)", "62.65%", "전체 83장 중 올바른 판정 비율", TEXT_LIGHT)
    ]
    for mname, mval, mdesc, mcol in metrics:
        p = tf_ev.add_paragraph()
        p.text = f"{mname}: {mval}"
        p.font.name = FONT_FAMILY
        p.font.size = Pt(13)
        p.font.bold = True
        p.font.color.rgb = mcol
        p.space_before = Pt(8)
        p_d = tf_ev.add_paragraph()
        p_d.text = f"   ↳ {mdesc}"
        p_d.font.name = FONT_FAMILY
        p_d.font.size = Pt(9.5)
        p_d.font.color.rgb = TEXT_MUTED

    p_warn = tf_ev.add_paragraph()
    p_warn.text = "※ 미탐 한계: 미세 오염/파손 31건 미검출 (T06 사례로 정직하게 보존)"
    p_warn.font.name = FONT_FAMILY
    p_warn.font.size = Pt(9.5)
    p_warn.font.color.rgb = TEXT_CORAL
    p_warn.space_before = Pt(12)

    # ==========================================
    # SLIDE 5: Industrial Decision System
    # ==========================================
    s5 = prs.slides.add_slide(blank_layout)
    set_slide_background(s5)
    add_header(s5, "산업용 종합 판정 체계: 영상 품질과 제품 결함의 분리 (6대 규칙)")

    # Top Card: Concept separation
    add_card(s5, Inches(0.8), Inches(1.4), Inches(11.733), Inches(1.4), bg_color=CARD_BG, border_color=PRIMARY_CYAN)
    tb_c = s5.shapes.add_textbox(Inches(1.1), Inches(1.5), Inches(11.1), Inches(1.2))
    tf_c = tb_c.text_frame
    tf_c.word_wrap = True
    p = tf_c.paragraphs[0]
    p.text = "핵심 원칙: 모델 소견(result)과 공정 최종 조치(final_result)의 엄격한 분리"
    p.font.name = FONT_FAMILY
    p.font.size = Pt(14)
    p.font.bold = True
    p.font.color.rgb = PRIMARY_CYAN

    p1 = tf_c.add_paragraph()
    p1.text = "• result (AI 모델 소견): 영상 상태와 무관하게 PatchCore가 제품 외관만 보고 매긴 점수 (OK / NG)"
    p1.font.name = FONT_FAMILY
    p1.font.size = Pt(10.5)
    p1.font.color.rgb = TEXT_WHITE
    p1.space_before = Pt(4)

    p2 = tf_c.add_paragraph()
    p2.text = "• final_result (제조 라인 최종 조치): 영상 품질(조도 등)을 감안하여 오판을 방지하는 결정론적 판정 (OK / NG / REINSPECT / ERROR)"
    p2.font.name = FONT_FAMILY
    p2.font.size = Pt(10.5)
    p2.font.color.rgb = SECONDARY_GREEN
    p2.space_before = Pt(2)

    # Bottom: 6 Rules Matrix
    rules = [
        ("Rule 1: 파이프라인 실패", "ERROR", "INSPECTION_FAILED", "이미지 로드 실패 또는 파이프라인 오류 발생 시", TEXT_CORAL),
        ("Rule 2: 영상 품질 경고", "REINSPECT", "IMAGE_QUALITY_WARNING", "조도 저하/과다 발생 시 (불량 오판 방지 재검 지시)", ACCENT_AMBER),
        ("Rule 3: 추론 불가", "REINSPECT", "DEFECT_DETECTION_UNAVAILABLE", "PatchCore 비활성화 또는 추론 실패 시", ACCENT_AMBER),
        ("Rule 4: 제품 결함 검출", "NG", "PRODUCT_ANOMALY_DETECTED", "품질 정상이고 이상 점수 > 34.1442 불량 확정 시", TEXT_CORAL),
        ("Rule 5: 정상 통과", "OK", "ALL_CHECKS_PASSED", "품질 정상이고 이상 점수 <= 34.1442 기준 합격 시", SECONDARY_GREEN),
        ("Rule 6: 미정의 예외 조합", "REINSPECT", "SAFE_FALLBACK", "정의되지 않은 미정의 조합 발생 시 안전한 재검 처리", TEXT_MUTED)
    ]
    ry = 3.0
    for rtitle, rres, rcode, rdesc, rcol in rules:
        add_card(s5, Inches(0.8), Inches(ry), Inches(11.733), Inches(0.58), bg_color=CARD_BG_ALT, border_color=CARD_BORDER)
        tb_r = s5.shapes.add_textbox(Inches(1.1), Inches(ry + 0.05), Inches(11.1), Inches(0.5))
        tf_r = tb_r.text_frame
        tf_r.word_wrap = True
        p = tf_r.paragraphs[0]
        p.text = f"{rtitle}  ➔  final_result: {rres}  ({rcode})   |   {rdesc}"
        p.font.name = FONT_FAMILY
        p.font.size = Pt(10.5)
        p.font.bold = True
        p.font.color.rgb = rcol
        ry += 0.65

    # ==========================================
    # SLIDE 6: Gemini Agent & Function Calling
    # ==========================================
    s6 = prs.slides.add_slide(blank_layout)
    set_slide_background(s6)
    add_header(s6, "Gemini AI Agent와 Function Calling: 자율 조사 4대 도구")

    # Left: 4 Tools
    add_card(s6, Inches(0.8), Inches(1.4), Inches(5.7), Inches(5.3))
    tb_t = s6.shapes.add_textbox(Inches(1.1), Inches(1.6), Inches(5.1), Inches(4.9))
    tf_t = tb_t.text_frame
    tf_t.word_wrap = True
    p = tf_t.paragraphs[0]
    p.text = "Agent 전용 4대 Python 도구 (InspectionTools)"
    p.font.name = FONT_FAMILY
    p.font.size = Pt(15)
    p.font.bold = True
    p.font.color.rgb = PRIMARY_CYAN

    tools = [
        ("1. get_inspection_result", "검사 상태, 모델 이상 점수, 임계값, 종합 판정 결과 조회"),
        ("2. analyze_image_quality", "OpenCV 측정 밝기 통계(mean, std, min, max) 및 기준값 조회"),
        ("3. get_execution_logs", "시작~종료 전 생명주기 이벤트 감사 로그 조회 (타임스탬프, 단계)"),
        ("4. get_inspection_history", "동일 제품군 과거 검사 추세 및 반복 이상 이력 조회")
    ]
    for tname, tdesc in tools:
        p = tf_t.add_paragraph()
        p.text = tname
        p.font.name = FONT_FAMILY
        p.font.size = Pt(12)
        p.font.bold = True
        p.font.color.rgb = TEXT_WHITE
        p.space_before = Pt(10)
        p_d = tf_t.add_paragraph()
        p_d.text = "  ↳ " + tdesc
        p_d.font.name = FONT_FAMILY
        p_d.font.size = Pt(10)
        p_d.font.color.rgb = TEXT_LIGHT

    # Right: Security & Isolation
    add_card(s6, Inches(6.8), Inches(1.4), Inches(5.7), Inches(5.3))
    tb_sec = s6.shapes.add_textbox(Inches(7.1), Inches(1.6), Inches(5.1), Inches(4.9))
    tf_sec = tb_sec.text_frame
    tf_sec.word_wrap = True
    p = tf_sec.paragraphs[0]
    p.text = "보안 및 데이터 격리 원칙"
    p.font.name = FONT_FAMILY
    p.font.size = Pt(15)
    p.font.bold = True
    p.font.color.rgb = SECONDARY_GREEN

    secs = [
        ("정답 라벨 완전 은닉", "Agent에게 broken_large, contamination 등 원본 경로/정답 일절 비노출"),
        ("불투명 제품 별칭 (TARGET-PRODUCT)", "실제 제품 ID를 난독화하여 도구 실행 및 프롬프트에 제공"),
        ("평가 Ground Truth 물리적 분리", "평가 정답은 프로젝트 외부 폴더에 격리하여 Agent 읽기 원천 차단"),
        ("수동 Function Calling 바인딩", "SDK 자동 실행 비활성화, 서버가 허가한 도구만 수동 실행하여 제어권 확보")
    ]
    for stitle, sdesc in secs:
        p = tf_sec.add_paragraph()
        p.text = "✔ " + stitle
        p.font.name = FONT_FAMILY
        p.font.size = Pt(12)
        p.font.bold = True
        p.font.color.rgb = SECONDARY_GREEN
        p.space_before = Pt(10)
        p_d = tf_sec.add_paragraph()
        p_d.text = "   " + sdesc
        p_d.font.name = FONT_FAMILY
        p_d.font.size = Pt(10)
        p_d.font.color.rgb = TEXT_LIGHT

    # ==========================================
    # SLIDE 7: Deterministic Grounding & Guardrails
    # ==========================================
    s7 = prs.slides.add_slide(blank_layout)
    set_slide_background(s7)
    add_header(s7, "결정적 근거 검증과 판정 보호 정책: AI 환각 및 변조 원천 차단")

    # Left: Deterministic Grounding
    add_card(s7, Inches(0.8), Inches(1.4), Inches(5.7), Inches(5.3))
    tb_g = s7.shapes.add_textbox(Inches(1.1), Inches(1.6), Inches(5.1), Inches(4.9))
    tf_g = tb_g.text_frame
    tf_g.word_wrap = True
    p = tf_g.paragraphs[0]
    p.text = "1. 결정적 근거 검증 (Grounding)"
    p.font.name = FONT_FAMILY
    p.font.size = Pt(15)
    p.font.bold = True
    p.font.color.rgb = PRIMARY_CYAN

    g_points = [
        ("Evidence ID 영수증 체계", "도구가 성공 실행될 때마다 고유 영수증 ID(E0001 등) 발급"),
        ("RFC 6901 JSON Pointer 강제", "관측값의 정확한 데이터 위치(/data/status 등)를 포인터로 명시"),
        ("값 일치성 서버 Python 검증", "모델이 적은 값과 도구 실제 반환값을 서버에서 1:1 대조"),
        ("불일치 시 즉시 거부 (HTTP 502)", "근거가 없거나 조작된 관측 사실은 즉시 EVIDENCE_MISMATCH로 차단")
    ]
    for gtitle, gdesc in g_points:
        p = tf_g.add_paragraph()
        p.text = "• " + gtitle
        p.font.name = FONT_FAMILY
        p.font.size = Pt(11.5)
        p.font.bold = True
        p.font.color.rgb = TEXT_WHITE
        p.space_before = Pt(8)
        p_d = tf_g.add_paragraph()
        p_d.text = "   " + gdesc
        p_d.font.name = FONT_FAMILY
        p_d.font.size = Pt(9.5)
        p_d.font.color.rgb = TEXT_LIGHT

    # Right: Decision Guardrails
    add_card(s7, Inches(6.8), Inches(1.4), Inches(5.7), Inches(5.3))
    tb_gr = s7.shapes.add_textbox(Inches(7.1), Inches(1.6), Inches(5.1), Inches(4.9))
    tf_gr = tb_gr.text_frame
    tf_gr.word_wrap = True
    p = tf_gr.paragraphs[0]
    p.text = "2. 판정 보호 정책 (Decision Guardrail)"
    p.font.name = FONT_FAMILY
    p.font.size = Pt(15)
    p.font.bold = True
    p.font.color.rgb = ACCENT_AMBER

    gr_points = [
        ("Agent는 '설명자'이지 '판정자'가 아님", "최종 판정은 검사 파이프라인이 내리며 Agent는 번복 불가"),
        ("final_result 변조 불가", "Agent 응답의 판정 필드는 기존 파이프라인 값과 100% 일치 강제"),
        ("가설과 관측의 엄격한 분리", "조도 저하가 발생해도 조명 고장으로 단정하지 않고 가설/권고로 구분"),
        ("안전 한계 명시 의무화", "모델 판정 OK가 실제 무결점 보증이 아님을 보고서에 필수 고지")
    ]
    for grtitle, grdesc in gr_points:
        p = tf_gr.add_paragraph()
        p.text = "✔ " + grtitle
        p.font.name = FONT_FAMILY
        p.font.size = Pt(11.5)
        p.font.bold = True
        p.font.color.rgb = TEXT_WHITE
        p.space_before = Pt(8)
        p_d = tf_gr.add_paragraph()
        p_d.text = "   " + grdesc
        p_d.font.name = FONT_FAMILY
        p_d.font.size = Pt(9.5)
        p_d.font.color.rgb = TEXT_LIGHT

    # ==========================================
    # SLIDE 8: Technical Troubleshooting (HTTP 400)
    # ==========================================
    s8 = prs.slides.add_slide(blank_layout)
    set_slide_background(s8)
    add_header(s8, "기술적 문제 해결: Gemini HTTP 400 극복과 454B 토큰 카탈로그 전략")

    # 3-step Horizontal Flow
    steps = [
        ("Step 1: 난관 봉착 (HTTP 400 거부)",
         "구조화 출력 실패",
         TEXT_CORAL,
         ["최종 진단 보고서 생성을 위해 복잡한 Pydantic 스키마 전송 시도",
          "Gemini 서버가 $defs, Union, Enum 중첩 구조를 해석 못하고 ClientError(400) 거부",
          "SDK의 role='tool' 직렬화 불일치 및 다중 라운드 통신 한계 노출"]),

        ("Step 2: 스키마 분할 격리 실험",
         "원인 규명 및 검증",
         ACCENT_AMBER,
         ["A/B/C 단순 스키마 후보: Gemini 실서버 HTTP 200 수락 확인",
          "D/E2 복잡 스키마 후보: 동일한 HTTP 400 거부 재현 확인",
          "결론: Gemini에는 복잡한 스키마를 직접 강요하지 않는 패턴이 필수적임을 입증"]),

        ("Step 3: 최종 해결 (토큰 카탈로그 전략)",
         "454B 스키마 + Python 검증",
         SECONDARY_GREEN,
         ["Gemini에는 454바이트, 깊이 2의 극단적 단순 JSON 스키마만 전송",
          "서버가 수집한 사실을 토큰 카탈로그(K0001~)로 주입하고 모델은 토큰만 선택",
          "모델 응답을 서버 Python 계층에서 Pydantic 및 Evidence로 완전 복원/검증 (HTTP 200 달성)"])
    ]

    sx = 0.8
    for stitle, ssub, scol, sitems in steps:
        add_card(s8, Inches(sx), Inches(1.4), Inches(3.7), Inches(5.3), bg_color=CARD_BG, border_color=scol)
        tb_s = s8.shapes.add_textbox(Inches(sx + 0.2), Inches(1.6), Inches(3.3), Inches(4.9))
        tf_s = tb_s.text_frame
        tf_s.word_wrap = True
        p = tf_s.paragraphs[0]
        p.text = stitle
        p.font.name = FONT_FAMILY
        p.font.size = Pt(13)
        p.font.bold = True
        p.font.color.rgb = scol

        p_sub = tf_s.add_paragraph()
        p_sub.text = ssub
        p_sub.font.name = FONT_FAMILY
        p_sub.font.size = Pt(10)
        p_sub.font.color.rgb = TEXT_MUTED
        p_sub.space_before = Pt(2)

        for item in sitems:
            p_i = tf_s.add_paragraph()
            p_i.text = "• " + item
            p_i.font.name = FONT_FAMILY
            p_i.font.size = Pt(10)
            p_i.font.color.rgb = TEXT_LIGHT
            p_i.space_before = Pt(10)

        sx += 4.0

    # ==========================================
    # SLIDE 9: E2E Validation Results (T01 Success)
    # ==========================================
    s9 = prs.slides.add_slide(blank_layout)
    set_slide_background(s9)
    add_header(s9, "실제 운영 E2E 검증 성과: T01 성공과 T03/T05/T06 현황")

    # Top: T01 Real Server Success Box
    add_card(s9, Inches(0.8), Inches(1.4), Inches(11.733), Inches(2.3), bg_color=CARD_BG, border_color=SECONDARY_GREEN)
    tb_t01 = s9.shapes.add_textbox(Inches(1.1), Inches(1.55), Inches(11.1), Inches(2.0))
    tf_01 = tb_t01.text_frame
    tf_01.word_wrap = True
    p = tf_01.paragraphs[0]
    p.text = "T01 정상 시나리오 (INSP-001396) 실제 Gemini API E2E 완전 성공 (PASS)"
    p.font.name = FONT_FAMILY
    p.font.size = Pt(15)
    p.font.bold = True
    p.font.color.rgb = SECONDARY_GREEN

    t01_data = [
        ("API 엔드포인트", "POST /analyze/INSP-001396  ➔  HTTP 200 OK (analysis_status: COMPLETED)"),
        ("외부 통신 및 지연시간", "Gemini 2회 호출 모두 HTTP 200 (1차 도구호출 2.88s + 2차 단순JSON 10.53s = 총 13.58초)"),
        ("토큰 사용량", "입력 3,115 + 출력 125 + Thinking 1,466 = 총 4,706 토큰"),
        ("도구 실행 및 근거 검증", "get_inspection_result (2.23ms, E0001) 실행 ➔ 6대 핵심 사실 100% 매핑 통과"),
        ("최종 AI 요약", "기록된 모델 판정과 종합 판정은 OK입니다. 실제 무결점 제품을 보증하지 않습니다.")
    ]
    for k, v in t01_data:
        p = tf_01.add_paragraph()
        p.text = f"• {k}: {v}"
        p.font.name = FONT_FAMILY
        p.font.size = Pt(9.5)
        p.font.color.rgb = TEXT_LIGHT
        p.space_before = Pt(3)

    # Bottom: 4 Scenarios Summary Table
    scenarios = [
        ("T01", "정상 병 기준 검사", "IMG-BOTTLE-0084", "NORMAL", "OK", "OK", "실서버 E2E 완전 성공 (PASS)", SECONDARY_GREEN),
        ("T03", "조도 저하 (0.6x)", "IMG-BOTTLE-INJ-0001", "WARNING_LOW_BRIGHTNESS", "OK", "REINSPECT", "조기종료 운영통합 완료 (실서버 재검증 대기)", ACCENT_AMBER),
        ("T05", "로드 실패 재현", "IMG-BOTTLE-NONEXISTENT", "ERROR", "UNKNOWN", "ERROR", "파이프라인/Mock 완료 (실서버 대기)", TEXT_MUTED),
        ("T06", "불량 투입 (미탐 한계)", "IMG-BOTTLE-0001", "NORMAL", "OK", "OK", "파이프라인/Mock 완료 (실서버 대기)", TEXT_MUTED)
    ]
    sy = 3.9
    for sid, sdesc, simg, sq, sr, sfr, sstatus, scol in scenarios:
        add_card(s9, Inches(0.8), Inches(sy), Inches(11.733), Inches(0.65), bg_color=CARD_BG_ALT, border_color=CARD_BORDER)
        tb_sc = s9.shapes.add_textbox(Inches(1.1), Inches(sy + 0.08), Inches(11.1), Inches(0.55))
        tf_sc = tb_sc.text_frame
        tf_sc.word_wrap = True
        p = tf_sc.paragraphs[0]
        p.text = f"[{sid}] {sdesc}  |  {simg}  |  품질: {sq}  |  결과: {sr} ➔ {sfr}  |  상태: {sstatus}"
        p.font.name = FONT_FAMILY
        p.font.size = Pt(10)
        p.font.bold = True
        p.font.color.rgb = scol
        sy += 0.72

    # ==========================================
    # SLIDE 10: Live Demo Scenario
    # ==========================================
    s10 = prs.slides.add_slide(blank_layout)
    set_slide_background(s10)
    add_header(s10, "라이브 데모 시나리오: FastAPI Swagger 기반 검사 & AI 진단 시연")

    demo_steps = [
        ("Step 1: 헬스체크", "GET /health", SECONDARY_GREEN, "서버 가동 및 PatchCore 모델(24MB) 싱글톤 적재 확인 (status: ok)"),
        ("Step 2: 검사 생성", "POST /inspections", PRIMARY_CYAN, "IMG-BOTTLE-0084 투입 ➔ 42ms 추론 ➔ 점수 31.33 <= 34.1442 ➔ OK 발급"),
        ("Step 3: AI 사후 진단", "POST /analyze/INSP-001396", ACCENT_AMBER, "Gemini 실서버 보고서 확인: 6대 observed_facts, E0001 근거 일치, 안전 한계 고지"),
        ("Step 4: T03 경고 비교", "차이점 분석", TEXT_CORAL, "조도 저하 시 final_result: REINSPECT 발급 원리 및 조명 점검 권고 대조")
    ]
    dx = 0.8
    for dtitle, dapi, dcol, ddesc in demo_steps:
        add_card(s10, Inches(dx), Inches(1.4), Inches(2.78), Inches(5.3), bg_color=CARD_BG, border_color=dcol)
        tb_d = s10.shapes.add_textbox(Inches(dx + 0.15), Inches(1.6), Inches(2.48), Inches(4.9))
        tf_d = tb_d.text_frame
        tf_d.word_wrap = True
        p = tf_d.paragraphs[0]
        p.text = dtitle
        p.font.name = FONT_FAMILY
        p.font.size = Pt(14)
        p.font.bold = True
        p.font.color.rgb = dcol

        p_api = tf_d.add_paragraph()
        p_api.text = dapi
        p_api.font.name = FONT_FAMILY
        p_api.font.size = Pt(11)
        p_api.font.bold = True
        p_api.font.color.rgb = TEXT_WHITE
        p_api.space_before = Pt(4)

        p_desc = tf_d.add_paragraph()
        p_desc.text = ddesc
        p_desc.font.name = FONT_FAMILY
        p_desc.font.size = Pt(10)
        p_desc.font.color.rgb = TEXT_LIGHT
        p_desc.space_before = Pt(12)

        dx += 2.98

    # ==========================================
    # SLIDE 11: Current Status vs Roadmap
    # ==========================================
    s11 = prs.slides.add_slide(blank_layout)
    set_slide_background(s11)
    add_header(s11, "현재 구현 현황 vs 향후 개발 로드맵 (투명한 성과 구분)")

    # Left: Implemented (Day 1 - Day 4)
    add_card(s11, Inches(0.8), Inches(1.4), Inches(5.7), Inches(5.3))
    tb_imp = s11.shapes.add_textbox(Inches(1.1), Inches(1.6), Inches(5.1), Inches(4.9))
    tf_imp = tb_imp.text_frame
    tf_imp.word_wrap = True
    p = tf_imp.paragraphs[0]
    p.text = "구현 완료 및 실측 검증 완료 (Day 1 ~ Day 4)"
    p.font.name = FONT_FAMILY
    p.font.size = Pt(15)
    p.font.bold = True
    p.font.color.rgb = SECONDARY_GREEN

    impls = [
        ("FastAPI 백엔드 & 고유 ID 발급", "순차 검사 ID 발급, 중립 식별자, Swagger 문서"),
        ("PatchCore CPU 추론 엔진 (42.5ms)", "180장 Coreset 학습, 24MB 체크포인트, 임계값 34.1442"),
        ("6대 규칙 산업용 종합 판정 체계", "조도 경고 시 REINSPECT 분리, JSONL 감사 로그 저장"),
        ("Gemini AI Agent & 도구 4종", "Function Calling 바인딩, 불투명 별칭, sanitizer"),
        ("결정적 근거 검증 (Grounding)", "Evidence ID, JSON Pointer, 판정 보호 가드레일"),
        ("454B 단순 JSON 스키마 전략", "Gemini HTTP 400 극복, 서버 Python Pydantic 검증"),
        ("회귀 테스트 661개 100% 통과", "네트워크 격리 오프라인 pytest 스위트 전체 패스"),
        ("T01 실서버 Gemini E2E 성공", "실제 Gemini 호출 ➔ HTTP 200 ➔ 진단 보고서 완성")
    ]
    for ititle, idesc in impls:
        p = tf_imp.add_paragraph()
        p.text = f"✔ {ititle}"
        p.font.name = FONT_FAMILY
        p.font.size = Pt(10.5)
        p.font.bold = True
        p.font.color.rgb = TEXT_WHITE
        p.space_before = Pt(4)

    # Right: Future Roadmap (Day 5 - Day 7)
    add_card(s11, Inches(6.8), Inches(1.4), Inches(5.7), Inches(5.3))
    tb_fut = s11.shapes.add_textbox(Inches(7.1), Inches(1.6), Inches(5.1), Inches(4.9))
    tf_fut = tb_fut.text_frame
    tf_fut.word_wrap = True
    p = tf_fut.paragraphs[0]
    p.text = "향후 개발 예정 로드맵 (Day 5 ~ Day 7)"
    p.font.name = FONT_FAMILY
    p.font.size = Pt(15)
    p.font.bold = True
    p.font.color.rgb = ACCENT_AMBER

    futures = [
        ("Day 5: 잔여 시나리오 실서버 검증", "개선된 3요청 조기종료 기반 T03 재검증 및 T05/T06 실서버 E2E 완료"),
        ("Day 6: React 웹 관제 대시보드", "DesignA 다크 테마 기반 실시간 관제 화면, 검사 이력, AI 리포트 UI"),
        ("신규 로드맵: 컨베이어 동영상 Live View", "주행 영상 스트리밍 + 프레임 Grab + 마우스 드래그 ROI 선택"),
        ("신규 로드맵: ROI 이미지 실시간 검사", "크롭 영역에 기존 PatchCore 엔진 및 임계값(34.1442) 동일 적용"),
        ("Day 7: Google Cloud Run 컨테이너 배포", "경량 CPU Dockerfile 기반 배포 및 Google Cloud Storage 영구화")
    ]
    for ftitle, fdesc in futures:
        p = tf_fut.add_paragraph()
        p.text = f"⏳ {ftitle}"
        p.font.name = FONT_FAMILY
        p.font.size = Pt(10.5)
        p.font.bold = True
        p.font.color.rgb = ACCENT_AMBER
        p.space_before = Pt(8)
        p_d = tf_fut.add_paragraph()
        p_d.text = "   " + fdesc
        p_d.font.name = FONT_FAMILY
        p_d.font.size = Pt(9.5)
        p_d.font.color.rgb = TEXT_MUTED

    # ==========================================
    # SLIDE 12: Limitations & Future Work
    # ==========================================
    s12 = prs.slides.add_slide(blank_layout)
    set_slide_background(s12)
    add_header(s12, "프로젝트 한계 및 향후 개선 계획: 솔직한 엔지니어링 고찰")

    limits = [
        ("1. 불량 미검출 한계 (Recall 50.8%)",
         TEXT_CORAL,
         "현재 ResNet-18 백본 모델은 63개 불량 중 31개(미세 파손/오염)를 검출하지 못함 (T06 사례).",
         "향후 개선안: 더 깊은 백본(WideResNet-50) 교체, 다해상도 패치 결합, 결함 유형별 멀티 임계값 파이프라인 구축"),

        ("2. 29장 표본 기반 임계값의 통계적 한계",
         ACCENT_AMBER,
         "판정 임계값 34.1442는 독립 정상 검증 29장 표본에 기반하므로 추가 공정 편차 반영 필요.",
         "향후 개선안: 지속적 양품 데이터 수집 및 공정 라인별 온라인 통계적 재교정(Dynamic Calibration) 도입"),

        ("3. 외부 LLM 지연시간 (13.58초)",
         PRIMARY_CYAN,
         "Gemini API 호출 및 추론에 약 13초 소요되어 초당 수십 개가 통과하는 초고속 인라인 차단에는 부적합.",
         "향후 개선안: 42ms 인라인 검사와 분리된 비동기 작업 큐(Celery/Redis) 도입 및 사후 감사 진단에 특화")
    ]

    ly = 1.4
    for ltitle, lcol, lprob, lsol in limits:
        add_card(s12, Inches(0.8), Inches(ly), Inches(11.733), Inches(1.65), bg_color=CARD_BG, border_color=lcol)
        tb_l = s12.shapes.add_textbox(Inches(1.1), Inches(ly + 0.1), Inches(11.1), Inches(1.45))
        tf_l = tb_l.text_frame
        tf_l.word_wrap = True
        p = tf_l.paragraphs[0]
        p.text = ltitle
        p.font.name = FONT_FAMILY
        p.font.size = Pt(13.5)
        p.font.bold = True
        p.font.color.rgb = lcol

        p_p = tf_l.add_paragraph()
        p_p.text = "• 한계점: " + lprob
        p_p.font.name = FONT_FAMILY
        p_p.font.size = Pt(10)
        p_p.font.color.rgb = TEXT_LIGHT
        p_p.space_before = Pt(4)

        p_s = tf_l.add_paragraph()
        p_s.text = "✔ " + lsol
        p_s.font.name = FONT_FAMILY
        p_s.font.size = Pt(10)
        p_s.font.color.rgb = SECONDARY_GREEN
        p_s.space_before = Pt(3)

        ly += 1.8

    # ==========================================
    # SLIDE 13: Conclusion & Q&A
    # ==========================================
    s13 = prs.slides.add_slide(blank_layout)
    set_slide_background(s13)

    add_card(s13, Inches(0.8), Inches(1.2), Inches(11.733), Inches(5.2), bg_color=CARD_BG_ALT, border_color=PRIMARY_CYAN)

    tb_end = s13.shapes.add_textbox(Inches(1.3), Inches(1.6), Inches(10.7), Inches(4.4))
    tf_end = tb_end.text_frame
    tf_end.word_wrap = True

    p = tf_end.paragraphs[0]
    p.text = "결론: 신뢰할 수 있는 산업용 AI Agent의 표준"
    p.font.name = FONT_FAMILY
    p.font.size = Pt(28)
    p.font.bold = True
    p.font.color.rgb = PRIMARY_CYAN

    conclusions = [
        ("비지도 이상 탐지 (PatchCore)", "불량 데이터 없이 정상 180장만으로 CPU 42ms 초고속 인라인 결함 탐지 구현"),
        ("결정론적 종합 판정 (Decision Engine)", "영상 품질과 제품 결함을 분리하여 조도 이상에 따른 불량 오판 원천 방지 (REINSPECT)"),
        ("근거 기반 AI 진단 (Gemini Function Calling)", "도구 실행 증적(Evidence ID / JSON Pointer)과 판정 보호 가드레일로 환각 없는 안전한 사후 진단 제공")
    ]
    for ctitle, cdesc in conclusions:
        p_c = tf_end.add_paragraph()
        p_c.text = f"✔ {ctitle}: {cdesc}"
        p_c.font.name = FONT_FAMILY
        p_c.font.size = Pt(12)
        p_c.font.bold = True
        p_c.font.color.rgb = TEXT_LIGHT
        p_c.space_before = Pt(14)

    p_qa = tf_end.add_paragraph()
    p_qa.text = "경청해 주셔서 감사합니다.  |  Q&A (질의응답)"
    p_qa.font.name = FONT_FAMILY
    p_qa.font.size = Pt(20)
    p_qa.font.bold = True
    p_qa.font.color.rgb = SECONDARY_GREEN
    p_qa.space_before = Pt(28)
    p_qa.alignment = PP_ALIGN.CENTER

    # Save Presentation
    output_path = os.path.join("presentation", "VisionInsight_Presentation.pptx")
    prs.save(output_path)
    print(f"Presentation saved successfully to: {output_path}")

if __name__ == "__main__":
    create_presentation()

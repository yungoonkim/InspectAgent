"""VisionInsight 기술 발표 자료 14장 최종 검증본 생성 스크립트
(14-Slide Verified Final Presentation with pytest 984 PASS & Slide 5 Overlap Fix)

주요 작업:
1. 최신 Codex 검증 결과 반영:
   - 전체 pytest 984 PASS / 경고 3건 (886, 928, 972 모두 제거)
   - T01 실제 Gemini E2E PASS (13.578초, 6개 근거 통과)
   - T03 실제 Gemini E2E PASS (24.600초, 12개 근거 통과)
   - T05 상태 정정: 기존 실서버 1회 FAIL (후속 조사 HTTP 504) -> 조기 종료 개선 후 오프라인 PASS, 실서버 재검증 대기
   - T06 실제 Gemini E2E: NOT TESTED (미탐 사례 보존)
2. Slide 5 (Decision 규칙) 하단 텍스트 겹침 완벽 수정:
   - Rule 1, 2, 4, 5 카드 높이 0.95인치, 간격 1.05인치로 정밀 조정 (Y: 1.35~5.45)
   - Rule 3(DEFECT_DETECTION_UNAVAILABLE), Rule 6(UNKNOWN_STATE_COMBINATION)을 하단 별도 박스(Y: 5.60~7.05)로 배치하여 겹침 0% 해소
   - 슬라이드 경계(7.50) 바깥 넘침 없음, 폰트 과도한 축소 없음 (10~13pt)
3. Slide 7 (Evidence 검증):
   - 오타 잔존 확인 및 '관측 사실' 명문화 (T01 6개, T03 12개 검증)
4. Slide 9 (핵심 기술 난제):
   - 3열 카드 유지, T05 카드에 기존 1회 FAIL 및 조기 종료 개선 후 오프라인 PASS / 실서버 재검증 대기 반영
   - 전체 pytest 984 PASS 반영, HTTP 504 원인 UNKNOWN 유지
5. Slide 12 (구현 현황):
   - 1단: 실제 Gemini E2E PASS (T01, T03)
   - 2단: 구현 및 오프라인 검증 PASS (984 PASS, T05 조기종료, 계측기 WARNING 정합화)
   - 3단: 실제 E2E 미완료 & 향후 과제 (T05 재검증 대기, T06 NOT TESTED)
6. Slide 13 (엔지니어링 한계):
   - T05 상태 간결 보완, HTTP 504 원인 UNKNOWN 유지
7. 산출물: presentation/VisionInsight_Presentation_14slides_verified.pptx
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
    # SLIDE 1: Title Slide (Updated to 984 PASS)
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
    bp1.text = "검증 완료: 단일 이미지 CPU 추론 평균 42.53ms  |  E2E 실서버 검증 (T01 양품 PASS / T03 경고 PASS)  |  전체 pytest 984 PASS (경고 3건)"
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
        ("PatchCore 기반 이상 탐지", "정상 이미지 180장만으로 학습, CPU 42.53ms 고속 추론으로 결함 여부 및 점수 산출"),
        ("재검사(REINSPECT) 규칙 분리", "조도 저하 등 영상 품질 경고 시 제품 불량(NG)과 구분하여 '재검사 필요'로 처리하는 결정 규칙 수립"),
        ("Gemini Function Calling 진단", "Gemini가 서버 도구를 직접 호출하여 사실을 수집하고, 1:1 결정적 근거(Evidence)로 검증된 진단 보고서 작성"),
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
         "CPU 단일 이미지 평균 추론: 42.53ms 달성 (실시간성 확보)"),

        ("2. Decision Layer (FastAPI)",
         WARNING_AMBER,
         "독립 검사 식별자 발급 (INSP-001396 등)",
         "결정 규칙 기반 종합 판정 (OK / NG / REINSPECT / ERROR)",
         "품질 이상 시 모델 결함과 분리하여 'REINSPECT' 분류"),

        ("3. Storage & Audit Layer",
         TEXT_LIGHT,
         "불변 검사 로그 및 시각순 감사 로그(events.jsonl) 영구 기록",
         "도구 실행 시 고유 Evidence ID(E0001, E0002) 자동 발급",
         "원본 정답(Ground Truth)과 운영 데이터의 엄격한 격리"),

        ("4. Diagnostic Agent Layer (Gemini)",
         SUCCESS_GREEN,
         "Gemini 3.8 Flash Function Calling 기반 심층 진단",
         "도구 호출 ➔ 결과 수집 ➔ 토큰 카탈로그 기반 단순 JSON 생성",
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
        p_sub.font.size = Pt(10)
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
        ("학습 데이터셋", "정상 이미지 180장 (Unsupervised)", "비지도 학습 수행"),
        ("임계값 산출셋", "정상 이미지 29장", "분포 기반 임계값 산출"),
        ("이상 점수 임계값", "34.1442", "이상이면 결함(NG)으로 분류"),
        ("테스트셋 평가", "83장 (정상 20장 + 결함 63장)", "공식 평가셋"),
        ("Image AUROC", "0.8286", "이상 탐지 분별 성능"),
        ("정밀도 (Precision)", "100.0%", "검출 불량 중 실제 불량 비율"),
        ("재현율 (Recall)", "50.79%", "전체 63건 중 32건 탐지"),
        ("단일 이미지 추론 시간", "CPU 평균 42.53ms", "Intel Core i7-14700F")
    ]
    for name, val, desc in metrics_list:
        p = tf_m.add_paragraph()
        p.text = f"{name}: {val}"
        p.font.name = FONT_FAMILY
        p.font.size = Pt(12)
        p.font.bold = True
        p.font.color.rgb = TEXT_WHITE
        p.space_before = Pt(8)
        p_d = tf_m.add_paragraph()
        p_d.text = f"   ({desc})"
        p_d.font.name = FONT_FAMILY
        p_d.font.size = Pt(9.5)
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
        ("진양성 (TP): 32건", "실제 결함 63건 중 32건을 정확히 NG로 검출"),
        ("위양성 (FP): 0건", "정상 제품 20건 중 오판 0건 (정밀도 100% 달성)"),
        ("진음성 (TN): 20건", "정상 제품 20건을 모두 정상(OK)으로 판정"),
        ("위음성 (FN): 31건", "미세 결함 31건을 미탐지 (엔지니어링 한계 인식)"),
        ("T06 미탐 사례 보존", "파손 불량 T06이 점수 32.27로 합격 처리된 한계 보존"),
        ("안전 규칙 준수", "실제 정답 라벨은 Agent에 일절 미제공 (평가 격리 유지)")
    ]
    for title, desc in cm_points:
        p = tf_cm.add_paragraph()
        p.text = "• " + title
        p.font.name = FONT_FAMILY
        p.font.size = Pt(11.5)
        p.font.bold = True
        p.font.color.rgb = TEXT_WHITE
        p.space_before = Pt(6)
        p_d = tf_cm.add_paragraph()
        p_d.text = "   " + desc
        p_d.font.name = FONT_FAMILY
        p_d.font.size = Pt(9.5)
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
    p_c7.text = "💡 실제 실서버 검증 성과: T01의 관측 사실 6개와 T03의 관측 사실 12개가 서버의 Evidence 검증을 통과했습니다. (서버에 등록된 필드에 대해 엄밀한 1:1 결정적 일치를 확인하며, 모든 자연어 가설이나 미래의 출력을 완전 검증한다고 과장하지 않음)"
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
            "result": "T01/T03 실제 E2E PASS",
            "result_sub": "실제 Gemini 통신 완전 성공 및 무오류 수락"
        },
        {
            "tag": "HTTP 504",
            "title": "최종 JSON 생성 지연",
            "color": WARNING_AMBER,
            "problem": "T03 최종 JSON 요청 HTTP 504",
            "problem_sub": "*(15초 제한 초과 발생, 서버 내부 원인 UNKNOWN)",
            "solution": "요청별 timeout 계측 및 분리",
            "solution_sub": "*(조사 15s 유지 / 최종 JSON만 30s 선택, 전체 60s)",
            "result": "최종 요청 18.967초 / 전체 24.600초 PASS",
            "result_sub": "단일 실측치 (반복 안정성 보장 아님, 대본 보존)"
        },
        {
            "tag": "T05 ERROR",
            "title": "조기 종료 및 근거 검증",
            "color": DANGER_CORAL,
            "problem": "필수 근거 확보 후 불필요 추가 조사 발생",
            "problem_sub": "*(기존 실서버 1회 FAIL: 3차 조사 504, 원인 UNKNOWN)",
            "solution": "조기 종료 정책 + 계측기 WARNING 정합화",
            "solution_sub": "*(도구 2회+17개 사실 확보 후 즉시 최종 전환)",
            "result": "Mock PASS / 실서버 재검증 대기",
            "result_sub": "전체 pytest 984 PASS (경고 3건) / 조기 종료 통과"
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
        p_res_hdr.font.color.rgb = SUCCESS_GREEN if "PASS" in item["result"] and "대기" not in item["result"] else WARNING_AMBER
        p_res_hdr.space_before = Pt(6)

        p_res = tf_c.add_paragraph()
        p_res.text = item["result"]
        p_res.font.name = FONT_FAMILY
        p_res.font.size = Pt(12)
        p_res.font.bold = True
        p_res.font.color.rgb = SUCCESS_GREEN if "PASS" in item["result"] and "대기" not in item["result"] else WARNING_AMBER
        p_res.space_before = Pt(1)

        p_res_sub = tf_c.add_paragraph()
        p_res_sub.text = item["result_sub"]
        p_res_sub.font.name = FONT_FAMILY
        p_res_sub.font.size = Pt(9.5)
        p_res_sub.font.color.rgb = TEXT_MUTED

        cx9 += 4.0

    # Bottom banner (Explicit T05 Status & 984 PASS)
    add_card(s9, Inches(0.8), Inches(5.95), Inches(11.733), Inches(0.8), bg_color=CARD_BG_ALT, border_color=PRIMARY_CYAN)
    tb_sum9 = s9.shapes.add_textbox(Inches(1.0), Inches(6.0), Inches(11.3), Inches(0.7))
    tf_sum9 = tb_sum9.text_frame
    p_sum9 = tf_sum9.paragraphs[0]
    p_sum9.text = "💡 현황: T05 기존 실서버 E2E 1회 FAIL(후속 조사 HTTP 504) → 조기 종료 개선 후 오프라인 PASS, 실서버 재검증 대기 | 전체 pytest 984 PASS"
    p_sum9.font.name = FONT_FAMILY
    p_sum9.font.size = Pt(10.5)
    p_sum9.font.bold = True
    p_sum9.font.color.rgb = TEXT_WHITE
    p_sum9.alignment = PP_ALIGN.CENTER

    # ==========================================
    # SLIDE 10: Real Server E2E: T01 & T03 (Preserved)
    # ==========================================
    s10 = prs.slides.add_slide(blank_layout)
    set_slide_background(s10)
    add_header(s10, "실제 Gemini API E2E 검증 결과: T01 정상 및 T03 경고 검증 (PASS)")

    # Left: T01
    add_card(s10, Inches(0.8), Inches(1.4), Inches(5.7), Inches(5.3), border_color=SUCCESS_GREEN)
    tb_t01 = s10.shapes.add_textbox(Inches(1.1), Inches(1.65), Inches(5.1), Inches(4.8))
    tf_t01 = tb_t01.text_frame
    tf_t01.word_wrap = True
    p = tf_t01.paragraphs[0]
    p.text = "T01 정상 시나리오: 실서버 E2E 성공 (PASS)"
    p.font.name = FONT_FAMILY
    p.font.size = Pt(15)
    p.font.bold = True
    p.font.color.rgb = SUCCESS_GREEN

    t01_items = [
        ("검사 식별자", "INSP-001396 (정상 병 검사)"),
        ("판정 결과", "모델 OK  /  서버 최종 판정 OK (Rule 5 발급)"),
        ("FastAPI 응답", "HTTP 200 OK  (analysis_status: COMPLETED)"),
        ("Gemini 통신", "2회 모두 HTTP 200 성공 (전체 소요: 13.578초)"),
        ("토큰 사용량", "총 4,706 토큰 (입력 3,115, 출력 125, Thinking 1,466)"),
        ("도구 실행", "get_inspection_result 실행 (2.23ms, E0001 발급)"),
        ("근거 검증", "관측 사실 6개 (F0001~F0006) 1:1 결정적 검증 100% 통과"),
        ("권장 조치", "CONTINUE_MONITORING (근거 참조: F0003 앵커링)")
    ]
    for label, val in t01_items:
        p = tf_t01.add_paragraph()
        p.text = f"• {label}: {val}"
        p.font.name = FONT_FAMILY
        p.font.size = Pt(10.5)
        p.font.color.rgb = TEXT_WHITE if label in ["판정 결과", "FastAPI 응답", "근거 검증"] else TEXT_LIGHT
        p.space_before = Pt(5)

    # Right: T03
    add_card(s10, Inches(6.8), Inches(1.4), Inches(5.7), Inches(5.3), border_color=SUCCESS_GREEN)
    tb_t03 = s10.shapes.add_textbox(Inches(7.1), Inches(1.65), Inches(5.1), Inches(4.8))
    tf_t03 = tb_t03.text_frame
    tf_t03.word_wrap = True
    p = tf_t03.paragraphs[0]
    p.text = "T03 조도 저하 시나리오: 실서버 E2E 성공 (PASS)"
    p.font.name = FONT_FAMILY
    p.font.size = Pt(15)
    p.font.bold = True
    p.font.color.rgb = SUCCESS_GREEN

    t03_items = [
        ("검사 식별자", "INSP-001398 (조도 저하 주입 검사)"),
        ("판정 결과", "모델 OK  ➔  서버 최종 REINSPECT (Rule 2 발급)"),
        ("FastAPI 응답", "HTTP 200 OK  (analysis_status: COMPLETED, 회차 final30_1)"),
        ("Gemini 통신", "3회 모두 HTTP 200 성공 (전체 소요: 24.600초)"),
        ("토큰 사용량", "총 9,873 토큰 (입력 5,576, 출력 345, Thinking 3,952)"),
        ("도구 순차 실행", "도구1(E0001 2.43s) ➔ 도구2(E0002 3.05s) 순차 실행"),
        ("최종 단순 JSON 생성", "18.967초 (HTTP 200, 30초 timeout 선택 적용)"),
        ("근거 검증", "관측 사실 12개 (F0001~F0012) 1:1 결정적 검증 100% 통과"),
        ("판정 불변 보존", "Gemini가 서버의 REINSPECT 판정을 번복하지 않고 보존")
    ]
    for label, val in t03_items:
        p = tf_t03.add_paragraph()
        p.text = f"• {label}: {val}"
        p.font.name = FONT_FAMILY
        p.font.size = Pt(10)
        p.font.color.rgb = TEXT_WHITE if label in ["판정 결과", "최종 단순 JSON 생성", "근거 검증"] else TEXT_LIGHT
        p.space_before = Pt(4)

    # Note
    p_note = tf_t03.add_paragraph()
    p_note.text = "*(최종 JSON에 한해 30s timeout을 선택 적용하여 성공. 과거 504 원인은 UNKNOWN이며 단일 성공으로 향후 안정성을 보장하지 않음)"
    p_note.font.name = FONT_FAMILY
    p_note.font.size = Pt(8.5)
    p_note.font.color.rgb = TEXT_MUTED
    p_note.space_before = Pt(5)

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
        ("T01 종합 요약", "기록된 모델 판정과 종합 판정은 OK입니다. 실제 무결점 제품을 보증하지는 않습니다."),
        ("T01 권장 조치", "check_code: CONTINUE_MONITORING (근거 참조: F0003 앵커링)"),
        ("T03 종합 요약", "기록된 종합 판정은 REINSPECT입니다. 제품 불량 확정과 구분하여 재검사가 필요합니다."),
        ("T03 권장 조치", "LIGHTING_EXPOSURE_CHECK (F0004, F0007 참조), MANUAL_REINSPECTION (F0003 참조)"),
        ("공통 안전 한계", "4대 limitations 필수 명시 (물리적 원인 불명, 모델 무결점 비보증, 기준치 미기록 등)"),
        ("정적 데모 원칙", "발표 현장 네트워크 장애 및 과금 방지를 위해 사전 실서버 검증 데이터를 재생하는 독립 데모 사용")
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
        ("1. 실제 Gemini E2E PASS",
         SUCCESS_GREEN,
         ["FastAPI 백엔드 & 고유 ID 발급",
          "PatchCore CPU 추론 엔진 (42.53ms)",
          "규칙 기반 종합 판정 (REINSPECT 분리)",
          "Gemini 4대 조회 도구 바인딩",
          "결정적 근거 검증 (Evidence/Pointer)",
          "단순 JSON 스키마 호환 구조",
          "T01 정상 실서버 E2E (PASS, 13.578s)",
          "T03 경고 실서버 E2E (PASS, 24.600s)"]),

        ("2. 구현 및 오프라인 검증 PASS",
         PRIMARY_CYAN,
         ["전체 pytest 984개 PASS (경고 3건)",
          "ERROR 필수 17개 원천 사실 정책 구현",
          "T05 이미지 로드 실패 전용 조기 종료",
          "  - 필수 도구·로그 확보 후 최종 즉시 전환",
          "  - Mock 조사 2회 + 최종 1회 통과",
          "계측기 WARNING 오분류 정정",
          "  - IMAGE_LOAD_FAILURE 정상 인식",
          "T03 경고 조기 종료 오프라인 검증"]),

        ("3. 실제 E2E 미완료 & 향후 과제",
         WARNING_AMBER,
         ["※ T05 실제 E2E: 기존 1회 FAIL, 수정 후 재검증 대기",
          "※ T06 실제 E2E: NOT TESTED (미탐 사례 보존)",
          "React 웹 관제 대시보드 (Day 6)",
          "컨베이어 주행 동영상 Live View",
          "실시간 프레임 Grab & 마우스 ROI",
          "ROI 크롭 이미지 PatchCore 검사",
          "Google Cloud Run 컨테이너 배포 (Day 7)"])
    ]
    cx = 0.8
    for ctitle, ccol, citems in cols_data_final:
        add_card(s12, Inches(cx), Inches(1.4), col_width, Inches(5.3), border_color=ccol)
        tb_col = s12.shapes.add_textbox(Inches(cx + 0.18), Inches(1.65), col_width - Inches(0.36), Inches(4.8))
        tf_col = tb_col.text_frame
        tf_col.word_wrap = True
        p = tf_col.paragraphs[0]
        p.text = ctitle
        p.font.name = FONT_FAMILY
        p.font.size = Pt(13.5)
        p.font.bold = True
        p.font.color.rgb = ccol

        for item in citems:
            pi = tf_col.add_paragraph()
            pi.text = "• " + item
            pi.font.name = FONT_FAMILY
            pi.font.size = Pt(10)
            if "NOT TESTED" in item or "FAIL" in item or "대기" in item:
                pi.font.color.rgb = DANGER_CORAL
            elif "PASS" in item:
                pi.font.color.rgb = TEXT_WHITE
            else:
                pi.font.color.rgb = TEXT_LIGHT
            pi.space_before = Pt(5)

        cx += 4.0

    # ==========================================
    # SLIDE 13: Engineering Limitations (Updated T05 Context)
    # ==========================================
    s13 = prs.slides.add_slide(blank_layout)
    set_slide_background(s13)
    add_header(s13, "한계 및 향후 개선 계획: 솔직한 엔지니어링 고찰")

    limits = [
        ("1. PatchCore 미탐 한계 (Recall 50.8%)",
         WARNING_AMBER,
         "현재 한계", "현재 ResNet-18 기반 모델은 83장 테스트셋에서 미세 파손과 오염 31건을 놓침. (T06 합격 사례 존재, 모델 OK가 무결점을 보증하지 않음)",
         "개선 계획", "WideResNet-50 등 백본 교체나 다해상도 패치 결합을 개선 후보로 검토 (성능 보장 아님)"),

        ("2. Gemini HTTP 504 및 타임아웃 이슈",
         DANGER_CORAL,
         "현재 한계", "과거 T03 최종 JSON 요청 및 T05 3차 조사에서 HTTP 504가 발생했으며 서버 내부 원인은 UNKNOWN입니다. T03은 30초 timeout 적용 단일 재검증(최종 18.967s / 전체 24.600s)으로 PASS했으나 반복 안정성을 보장하지 않으며, T05는 조기 종료 개선 후 실서버 재검증 대기 상태입니다.",
         "개선 계획", "조기 종료 가드레일 정밀화, 프롬프트 압축, 비동기 작업 큐 전환, 장기 모니터링 체계 확립 필요"),

        ("3. 외부 LLM 호출 지연시간 (13.58s / 24.60s)",
         PRIMARY_CYAN,
         "현재 한계", "Gemini API 호출에 수십 초가 소요되어 생산 라인 초고속 동기 인라인 제어에는 부적합하며, 실제 PLC/배출기 제어는 수행하지 않음",
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
        ("PatchCore", "이상 점수 산출 및 모델 판정 소견(result) 제공 (CPU 42.53ms 실시간 추론)"),
        ("FastAPI", "서버 규칙 기반 최종 검사 판정(final_result: REINSPECT 분리) 확정 및 감사 추적 로그 보존"),
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

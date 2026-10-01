# -*- coding: utf-8 -*-
"""
pdf_generator.py
금융 보고서 마크다운(.md) 텍스트를 고품질 A4 PDF 문서로 변환하는 생성기 모듈.
ReportLab 및 Windows 맑은 고딕(Malgun Gothic) 한글 폰트를 활용합니다.
"""

import io
import re
import os
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

# 1. 한글 폰트 등록 (Windows 맑은 고딕 우선 탐색)
_FONT_INITIALIZED = False
_FONT_NORMAL = "Helvetica"
_FONT_BOLD = "Helvetica-Bold"

def _init_korean_fonts():
    global _FONT_INITIALIZED, _FONT_NORMAL, _FONT_BOLD
    if _FONT_INITIALIZED:
        return

    font_candidates = [
        # Linux (Streamlit Community Cloud / Ubuntu)
        ("NanumGothic", "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
        ("NanumGothicBold", "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"),
        # Windows
        ("Malgun", "C:/Windows/Fonts/malgun.ttf"),
        ("MalgunBold", "C:/Windows/Fonts/malgunbd.ttf"),
        ("NanumGothic", "C:/Windows/Fonts/NanumGothic.ttf"),
    ]

    normal_registered = False
    bold_registered = False

    for font_name, font_path in font_candidates:
        if os.path.exists(font_path):
            try:
                pdfmetrics.registerFont(TTFont(font_name, font_path))
                if "Bold" in font_name:
                    _FONT_BOLD = font_name
                    bold_registered = True
                else:
                    _FONT_NORMAL = font_name
                    normal_registered = True
            except Exception as e:
                print(f"[Warning] 폰트 로드 실패 ({font_name}): {e}")

    if normal_registered and not bold_registered:
        _FONT_BOLD = _FONT_NORMAL

    _FONT_INITIALIZED = True


class NumberedCanvas(canvas.Canvas):
    """2-패스 페이지 번호 및 공식 헤지펀드 푸터 렌더러"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont(_FONT_NORMAL, 8)
        self.setFillColor(colors.HexColor("#64748B"))

        # 상단 헤더 구분선 및 워터마크 텍스트
        self.setStrokeColor(colors.HexColor("#E2E8F0"))
        self.setLineWidth(0.5)
        self.line(40, 800, 555, 800)
        self.drawString(40, 805, "BULL-GOM | EQUITY RESEARCH COMPREHENSIVE INVESTMENT REPORT")

        # 하단 푸터 및 페이지 번호
        self.line(40, 45, 555, 45)
        self.drawString(40, 32, "Confidential - Equity Research Comprehensive Investment Report")
        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(555, 32, page_str)
        self.restoreState()


def markdown_to_pdf_bytes(md_content: str) -> bytes:
    """
    마크다운 문자열을 파싱하여 정갈한 A4 PDF 바이너리(bytes)로 변환합니다.
    """
    _init_korean_fonts()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=40,
        rightMargin=40,
        topMargin=55,
        bottomMargin=55
    )

    styles = getSampleStyleSheet()

    # 맞춤형 단락 스타일 정의
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName=_FONT_BOLD,
        fontSize=18,
        leading=24,
        textColor=colors.HexColor("#1E3A8A"),
        spaceAfter=12
    )

    h2_style = ParagraphStyle(
        'SectionH2',
        parent=styles['Heading2'],
        fontName=_FONT_BOLD,
        fontSize=13,
        leading=18,
        textColor=colors.HexColor("#0F172A"),
        spaceBefore=14,
        spaceAfter=8,
        keepWithNext=True
    )

    h3_style = ParagraphStyle(
        'SectionH3',
        parent=styles['Heading3'],
        fontName=_FONT_BOLD,
        fontSize=11,
        leading=15,
        textColor=colors.HexColor("#334155"),
        spaceBefore=10,
        spaceAfter=4,
        keepWithNext=True
    )

    body_style = ParagraphStyle(
        'DocBody',
        parent=styles['Normal'],
        fontName=_FONT_NORMAL,
        fontSize=9.5,
        leading=14.5,
        textColor=colors.HexColor("#1E293B"),
        spaceAfter=5
    )

    bullet_style = ParagraphStyle(
        'DocBullet',
        parent=body_style,
        leftIndent=15,
        firstLineIndent=-10,
        spaceAfter=4
    )

    quote_style = ParagraphStyle(
        'DocQuote',
        parent=body_style,
        leftIndent=18,
        rightIndent=18,
        textColor=colors.HexColor("#475569"),
        fontName=_FONT_NORMAL,
        spaceBefore=6,
        spaceAfter=8
    )

    story = []
    lines = md_content.splitlines()
    in_code_block = False

    for line in lines:
        stripped = line.strip()

        # 코드 블록 (JSON 등) 스킵 또는 단순화
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue

        # 빈 줄 처리
        if not stripped:
            story.append(Spacer(1, 4))
            continue

        # 구분선 (---)
        if re.match(r"^[-*_]{3,}$", stripped):
            story.append(Spacer(1, 4))
            story.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#CBD5E1"), spaceAfter=8))
            continue

        # # 대제목
        if stripped.startswith("# "):
            title_text = _format_inline_markdown(stripped[2:])
            story.append(Paragraph(title_text, title_style))
            story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#2563EB"), spaceAfter=10))
            continue

        # ## 중제목
        if stripped.startswith("## "):
            h2_text = _format_inline_markdown(stripped[3:])
            story.append(Paragraph(h2_text, h2_style))
            continue

        # ### 소제목
        if stripped.startswith("### "):
            h3_text = _format_inline_markdown(stripped[4:])
            story.append(Paragraph(h3_text, h3_style))
            continue

        # 불릿 목록 (- 또는 * 또는 +)
        if re.match(r"^[-*+]\s+", stripped):
            bullet_text = re.sub(r"^[-*+]\s+", "", stripped)
            formatted_bullet = f"• {_format_inline_markdown(bullet_text)}"
            story.append(Paragraph(formatted_bullet, bullet_style))
            continue

        # 인용구 (> )
        if stripped.startswith("> "):
            quote_text = _format_inline_markdown(stripped[2:])
            story.append(Paragraph(f"<i>{quote_text}</i>", quote_style))
            continue

        # 일반 문단
        p_text = _format_inline_markdown(stripped)
        story.append(Paragraph(p_text, body_style))

    # 문서 빌드 및 버퍼 안전 해제
    try:
        doc.build(story, canvasmaker=NumberedCanvas)
        pdf_bytes = buffer.getvalue()
        return pdf_bytes
    finally:
        buffer.close()


def _format_inline_markdown(text: str) -> str:
    """마크다운의 볼드(**), 이탤릭(*), 링크 등을 ReportLab 호환 HTML 태그로 치환"""
    # 1. XML 특수문자 이스케이프
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # 2. 볼드체 (**text** -> <b>text</b>)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)

    # 3. 이탤릭 (*text* -> <i>text</i>)
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)

    # 4. 인라인 코드 (`code` -> <b><code>code</code></b>)
    text = re.sub(r"`(.+?)`", r'<font color="#2563EB"><b>\1</b></font>', text)

    # 5. 하이퍼링크 ([text](url) -> <a href="url" color="#2563EB"><u>text</u></a>)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^\s\)]+)\)", r'<a href="\2" color="#2563EB"><u>\1</u></a>', text)

    return text

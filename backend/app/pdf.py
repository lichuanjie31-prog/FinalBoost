"""PDF rendering helpers for training and focused practice papers."""

from html import escape
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


_CJK_FONT_PATHS = (
    "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simsun.ttc",
)


def _register_cjk_font():
    """Register a system CJK font where available, with safe Helvetica fallback."""
    for font_path in _CJK_FONT_PATHS:
        if not Path(font_path).is_file():
            continue
        try:
            pdfmetrics.registerFont(TTFont("NotoSansCJK", font_path, subfontIndex=0))
            return "NotoSansCJK"
        except Exception:
            # Some systems ship a non-collection TTF under a TTC-like name, or
            # ReportLab/fontTools cannot read a particular collection face.
            try:
                pdfmetrics.registerFont(TTFont("NotoSansCJK", font_path))
                return "NotoSansCJK"
            except Exception:
                continue
    return "Helvetica"


def _safe_text(value):
    """Escape untrusted content for ReportLab Paragraph's XML-like markup."""
    text = "" if value is None else str(value)
    return escape(text, quote=False).replace("\n", "<br/>")


def _styles(font_name):
    return {
        "title": ParagraphStyle("PaperTitle", fontName=font_name, fontSize=21,
                                leading=29, alignment=TA_CENTER, textColor=colors.HexColor("#17324D"),
                                spaceAfter=8),
        "meta": ParagraphStyle("PaperMeta", fontName=font_name, fontSize=9.5,
                               leading=16, alignment=TA_CENTER, textColor=colors.HexColor("#586575")),
        "weak": ParagraphStyle("WeakPoint", fontName=font_name, fontSize=10,
                               leading=16, textColor=colors.HexColor("#7A3E00")),
        "section": ParagraphStyle("Section", fontName=font_name, fontSize=14,
                                   leading=20, textColor=colors.HexColor("#17324D"),
                                   spaceBefore=10, spaceAfter=7),
        "question": ParagraphStyle("Question", fontName=font_name, fontSize=11,
                                    leading=17, textColor=colors.HexColor("#202B38"),
                                    spaceAfter=4),
        "option": ParagraphStyle("Option", fontName=font_name, fontSize=10,
                                  leading=15, leftIndent=12, textColor=colors.HexColor("#364152"),
                                  spaceAfter=2),
        "answer": ParagraphStyle("Answer", fontName=font_name, fontSize=9.5,
                                  leading=15, leftIndent=12, textColor=colors.HexColor("#174A7E"),
                                  spaceBefore=3),
        "analysis": ParagraphStyle("Analysis", fontName=font_name, fontSize=9.5,
                                   leading=15, leftIndent=12, textColor=colors.HexColor("#56616F")),
        "footer": ParagraphStyle("Footer", fontName=font_name, fontSize=8,
                                  leading=12, alignment=TA_CENTER, textColor=colors.HexColor("#9AA3AD")),
    }


def render_training_pdf(path, title, meta, groups, include_answers=False, include_analysis=False):
    """Render a practice paper to ``path`` and return that path.

    The signature is shared by training exports and the materials API.
    """
    font_name = _register_cjk_font()
    style = _styles(font_name)
    story = [
        Spacer(1, 5 * mm),
        Paragraph(_safe_text(title or "薄弱考点专项强化练习卷"), style["title"]),
        Paragraph(_safe_text(meta or "姓名：___________　班级：___________　得分：___________"), style["meta"]),
        Spacer(1, 4 * mm),
        HRFlowable(width="100%", thickness=1.1, color=colors.HexColor("#91A5B7"), spaceAfter=5 * mm),
    ]
    weak_points = [str(label) for label, _ in groups if label]
    if weak_points:
        weak_text = "、".join(weak_points)
        box = Table([[Paragraph("<b>【针对性薄弱考点】</b> " + _safe_text(weak_text), style["weak"])]],
                    colWidths=[170 * mm])
        box.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFF7E8")),
            ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#E7B766")),
            ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
            ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
        story.extend([box, Spacer(1, 5 * mm)])

    for stage_label, questions in groups:
        story.append(Paragraph("【" + _safe_text(stage_label or "专项练习") + "】", style["section"]))
        for index, question in enumerate(questions, 1):
            block = [Paragraph(f"<b>第 {index} 题</b>　<span color='#7A8795'>[考点：{_safe_text(stage_label or '专项')} ]</span><br/>{_safe_text(question.get('content', ''))}", style["question"])]
            for option in question.get("options", []) or []:
                block.append(Paragraph(f"{_safe_text(option.get('key', ''))}. {_safe_text(option.get('text', ''))}", style["option"]))
            if include_answers and question.get("answer"):
                block.append(Paragraph("<b>【参考答案】</b> " + _safe_text(question["answer"]), style["answer"]))
            if include_analysis and question.get("analysis"):
                block.append(Paragraph("<b>【思路剖析】</b> " + _safe_text(question["analysis"]), style["analysis"]))
            story.extend([KeepTogether(block), Spacer(1, 4 * mm)])
    story.extend([Spacer(1, 5 * mm), Paragraph("本内容由 AI 生成，仅供参考（FinalBoost）", style["footer"])])

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(str(output_path), pagesize=A4, rightMargin=20 * mm,
                                 leftMargin=20 * mm, topMargin=17 * mm, bottomMargin=17 * mm,
                                 title=str(title or "专项练习卷"), author="FinalBoost")
    document.build(story)
    return output_path

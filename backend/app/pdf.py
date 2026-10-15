"""PDF rendering helpers for training and focused practice papers."""

from html import escape
import os
import re
from pathlib import Path
from io import BytesIO
from pypdf import PdfReader
from reportlab import rl_config

# The reported delivered file contained invalid ASCII85 streams. Prefer a
# standard binary Flate stream and transfer the complete file unchanged.
rl_config.useA85 = False

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


FONT_PATH = "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc"
FONT_NAME = "Helvetica"

if os.path.exists(FONT_PATH):
    try:
        # TTC 字体集合，subfontIndex=0 为简体中文 (SC)
        pdfmetrics.registerFont(TTFont("NotoSansCJK", FONT_PATH, subfontIndex=0))
        FONT_NAME = "NotoSansCJK"
    except Exception:
        try:
            pdfmetrics.registerFont(TTFont("NotoSansCJK", FONT_PATH))
            FONT_NAME = "NotoSansCJK"
        except Exception:
            pass

if FONT_NAME == 'Helvetica':
    # Local TrueType CJK fonts keep Chinese text embedded and extractable.
    for candidate in (Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts/msyh.ttc',
                      Path('/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc')):
        if candidate.exists():
            try:
                pdfmetrics.registerFont(TTFont('LocalCJK', str(candidate), subfontIndex=0))
                FONT_NAME = 'LocalCJK'
                break
            except Exception:
                continue
    if FONT_NAME == 'Helvetica':
        pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
        FONT_NAME = 'STSong-Light'


def sanitize_math_text(text: str) -> str:
    """Convert common LaTeX/Typst remnants into readable plain math text."""
    text = str(text or '')
    def group_at(source, start):
        if start >= len(source) or source[start] != '{':
            return None
        depth = 0
        for index in range(start, len(source)):
            depth += (source[index] == '{') - (source[index] == '}')
            if depth == 0:
                return source[start + 1:index], index + 1
        return None

    command = re.compile(r'\\(?:dfrac|tfrac|frac|sqrt)\s*')
    cursor = 0
    while match := command.search(text, cursor):
        first = group_at(text, match.end())
        if not first:
            cursor = match.end()
            continue
        inner, end = first
        if match.group().strip() == r'\sqrt':
            replacement = '√(' + sanitize_math_text(inner) + ')'
        else:
            second = group_at(text, end)
            if not second:
                cursor = end
                continue
            denominator, end = second
            replacement = '(' + sanitize_math_text(inner) + ')/(' + sanitize_math_text(denominator) + ')'
        text = text[:match.start()] + replacement + text[end:]
        cursor = match.start() + len(replacement)
    text = re.sub(r'bb\(R\)|\\mathbb\{R\}', 'R（实数集）', text)
    text = re.sub(r'\binfinity\b', '∞', text)
    replacements = {'infty': '∞', 'le': '≤', 'leq': '≤', 'ge': '≥', 'geq': '≥',
                    'neq': '≠', 'ne': '≠', 'alpha': 'α', 'beta': 'β', 'gamma': 'γ',
                    'theta': 'θ', 'pi': 'π', 'lambda': 'λ', 'Delta': 'Δ', 'in': '∈',
                    'cup': '∪', 'cap': '∩', 'subset': '⊂', 'cdot': '·', 'times': '×',
                    'div': '÷', 'left': '', 'right': ''}
    text = re.sub(r'\\([A-Za-z]+)', lambda match: replacements.get(match.group(1), match.group(0)), text)
    for old, new in (('<=', '≤'), ('>=', '≥'), ('!=', '≠')):
        text = text.replace(old, new)
    text = re.sub(r'\^\{([^{}]+)\}', r'^(\1)', text)
    text = re.sub(r'(?<![A-Za-z_])pi(?![A-Za-z_])', 'π', text)
    text = re.sub(r'sqrt\(([^()]+)\)', r'√(\1)', text)
    return text.replace('$', '')


def _safe_text(value):
    """Escape untrusted content for ReportLab Paragraph's XML-like markup."""
    text = sanitize_math_text("" if value is None else str(value))
    return escape(text, quote=False).replace("\n", "<br/>")


def verify_pdf_bytes(data: bytes, expected_stems=()):
    """Decode every stream and prove expected question text survived rendering."""
    if not data.startswith(b'%PDF-') or not data.rstrip().endswith(b'%%EOF'):
        raise ValueError('PDF 文件头或结尾不完整')
    try:
        reader = PdfReader(BytesIO(data), strict=True)
        if not reader.pages:
            raise ValueError('PDF 没有页面')
        texts = []
        for page in reader.pages:
            if page.get_contents() is not None:
                page.get_contents().get_data()
            texts.append(page.extract_text() or '')
        flat = re.sub(r'\s+', '', '\n'.join(texts))
        if not flat:
            raise ValueError('PDF 没有可读文字')
        for stem in expected_stems:
            expected = re.sub(r'\s+', '', sanitize_math_text(stem))
            if not expected or expected not in flat:
                raise ValueError('PDF 中缺少完整题干，已阻断空白试卷')
        return len(reader.pages)
    except Exception as exc:
        raise ValueError('PDF 内容流损坏或题目不完整') from exc


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
    stems = [question.get('content', '') for _, questions in groups for question in questions]
    if not stems or any(not re.sub(r'[\s\u200b\ufeff]', '', stem) for stem in stems):
        raise ValueError('禁止渲染没有题干的试卷')
    style = _styles(FONT_NAME)
    story = [
        Spacer(1, 5 * mm),
        Paragraph(_safe_text(title or "薄弱考点专项强化练习卷"), style["title"]),
        Paragraph(_safe_text("姓名：___________　班级：___________　得分：___________"), style["meta"]),
        Paragraph(_safe_text(meta or ''), style['meta']),
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

    numbered = []
    for stage_label, questions in groups:
        story.append(Paragraph("【" + _safe_text(stage_label or "专项练习") + "】", style["section"]))
        for question in questions:
            index = len(numbered) + 1
            numbered.append((index, question))
            block = [Paragraph(f"<b>第 {index} 题</b>　<span color='#7A8795'>[考点：{_safe_text(stage_label or '专项')} ]</span><br/>{_safe_text(question.get('content', ''))}", style["question"])]
            from .materials import _normalize_options
            for option_index, option in enumerate(_normalize_options(question.get('options'))):
                label = chr(65 + option_index % 26)
                block.append(Paragraph(f"{label}. {_safe_text(option['text'])}", style["option"]))
            story.extend([KeepTogether(block), Spacer(1, 15 * mm)])
    if include_answers or include_analysis:
        story.extend([PageBreak(), Paragraph('【参考答案与名师解析】', style['title']), Spacer(1, 5 * mm)])
        for index, question in numbered:
            block = [Paragraph(f'第 {index} 题', style['section'])]
            if include_answers:
                block.append(Paragraph('【参考答案】 ' + _safe_text(question.get('answer', '')), style['answer']))
            if include_analysis:
                block.append(Paragraph('【思路剖析】 ' + _safe_text(question.get('analysis', '')), style['analysis']))
            story.extend([KeepTogether(block), Spacer(1, 4 * mm)])
    story.extend([Spacer(1, 5 * mm), Paragraph("本内容由 AI 生成，仅供参考（FinalBoost）", style["footer"])])

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(str(output_path), pagesize=A4, rightMargin=20 * mm,
                                 leftMargin=20 * mm, topMargin=17 * mm, bottomMargin=17 * mm,
                                 title=str(title or "专项练习卷"), author="FinalBoost", pageCompression=1)
    document.build(story)
    verify_pdf_bytes(output_path.read_bytes(), stems)
    return output_path

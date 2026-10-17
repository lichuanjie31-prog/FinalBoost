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
    Flowable,
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
MATH_FONT_NAME = "STIXMath"
MATH_FONT_PATH = Path(__file__).parent / "assets" / "fonts" / "STIXTwoMath-Regular.ttf"
_PUNCTUATION_TRANSLATION = str.maketrans({
    '，': ',', '。': '.', '；': ';', '：': ':', '、': ',',
    '（': '(', '）': ')', '　': ' ', '．': '.',
})

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

# The bundled SIL OFL math face guarantees the symbol repertoire on Windows
# and Linux, independent of whichever CJK font is installed on the host.
pdfmetrics.registerFont(TTFont(MATH_FONT_NAME, str(MATH_FONT_PATH)))


_SUPERSCRIPTS = dict(zip(
    "0123456789+-=()abcdefghijklmnopqrstuvwxyz",
    "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖᑫʳˢᵗᵘᵛʷˣʸᶻ",
))
_SUBSCRIPTS = dict(zip("0123456789+-=()aehiklmnoprstx", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₕᵢₖₗₘₙₒₚᵣₛₜₓ"))
_CHINESE_NUMERALS = "零一二三四五六七八九十"
_VARIATION_TITLES = {
    "consolidation": "同构巩固（原题考点对应）",
    "reverse": "逆向检验",
    "extension": "综合拓展",
}


def _group_at(source, start):
    if start >= len(source) or source[start] != '{':
        return None
    depth = 0
    for index in range(start, len(source)):
        depth += (source[index] == '{') - (source[index] == '}')
        if depth == 0:
            return source[start + 1:index], index + 1
    return None


def _replace_group_commands(source):
    replacements = {
        'mathbb': lambda value: ''.join({'N': 'ℕ', 'Z': 'ℤ', 'Q': 'ℚ', 'R': 'ℝ', 'C': 'ℂ'}.get(c, c) for c in value),
        'widehat': lambda value: '⌒' + value,
        'overline': lambda value: ''.join(char + '\u0305' for char in value),
        'bar': lambda value: ''.join(char + '\u0305' for char in value),
        'vec': lambda value: value + '\u20d7',
        'overrightarrow': lambda value: value + '\u20d7',
        'sqrt': lambda value: '√(' + value + ')',
        'operatorname': lambda value: value,
        'mathrm': lambda value: value,
        'text': lambda value: value,
    }
    for command, replacement in replacements.items():
        pattern = re.compile(r'\\' + command + r'\s*')
        cursor = 0
        while match := pattern.search(source, cursor):
            grouped = _group_at(source, match.end())
            if grouped:
                value, end = grouped
            else:
                value, end = source[match.end():match.end() + 1], match.end() + 1
                if not value:
                    cursor = match.end()
                    continue
            rendered = replacement(value)
            source = source[:match.start()] + rendered + source[end:]
            cursor = match.start() + len(rendered)
    return source


def _replace_fractions(source):
    pattern = re.compile(r'\\(?:dfrac|tfrac|frac)\s*')
    cursor = 0
    while match := pattern.search(source, cursor):
        numerator = _group_at(source, match.end())
        if not numerator:
            cursor = match.end()
            continue
        top, next_start = numerator
        denominator = _group_at(source, next_start)
        if not denominator:
            cursor = next_start
            continue
        bottom, end = denominator
        rendered = '(' + sanitize_math_text(top) + ') / (' + sanitize_math_text(bottom) + ')'
        source = source[:match.start()] + rendered + source[end:]
        cursor = match.start() + len(rendered)
    return source


def _replace_scripts(source):
    for marker, mapping in (('^', _SUPERSCRIPTS), ('_', _SUBSCRIPTS)):
        cursor = 0
        while True:
            index = source.find(marker, cursor)
            if index < 0:
                break
            if index + 1 < len(source) and source[index + 1] == '{':
                grouped = _group_at(source, index + 1)
                if not grouped:
                    cursor = index + 1
                    continue
                value, end = grouped
            elif index + 1 < len(source):
                value, end = source[index + 1], index + 2
            else:
                cursor = index + 1
                continue
            if value and all(char in mapping for char in value):
                rendered = ''.join(mapping[char] for char in value)
                source = source[:index] + rendered + source[end:]
                cursor = index + len(rendered)
            else:
                cursor = end
    return source


def sanitize_math_text(text: str) -> str:
    """Convert common LaTeX and plain math notation into printable Unicode."""
    text = str(text or '').replace(r'\{', '{').replace(r'\}', '}').replace(r'\|', '∥')
    text = re.sub(r'\\not\s*\\(?:in|ni)\b', '∉', text)
    text = re.sub(r'\\not\s*\\subseteq\b', '⊈', text)
    replacements = {
        'infty': '∞', 'le': '≤', 'leq': '≤', 'ge': '≥', 'geq': '≥',
        'neq': '≠', 'ne': '≠', 'nleq': '≰', 'ngeq': '≱', 'nsubseteq': '⊈',
        'notin': '∉', 'notni': '∌', 'alpha': 'α', 'beta': 'β', 'gamma': 'γ',
        'theta': 'θ', 'lambda': 'λ', 'pi': 'π', 'Delta': 'Δ', 'in': '∈', 'ni': '∋',
        'cup': '∪', 'cap': '∩', 'subset': '⊂', 'supset': '⊃', 'subseteq': '⊆',
        'supseteq': '⊇', 'emptyset': '∅', 'varnothing': '∅', 'forall': '∀',
        'exists': '∃', 'Rightarrow': '⇒', 'Longrightarrow': '⇒',
        'Leftrightarrow': '⇔', 'Longleftrightarrow': '⇔', 'implies': '⇒',
        'iff': '⇔', 'complement': '∁', 'parallel': '∥', 'perp': '⊥', 'angle': '∠',
        'int': '∫', 'cdot': '·', 'times': '×', 'div': '÷', 'approx': '≈',
        'equiv': '≡', 'pm': '±', 'mp': '∓', 'left': '', 'right': '',
        'log': 'log', 'lg': 'lg', 'ln': 'ln', 'lim': 'lim', 'max': 'max', 'min': 'min',
    }
    text = re.sub(r'\\([A-Za-z]+)', lambda match: replacements.get(match.group(1), match.group(0)), text)
    text = _replace_group_commands(text)
    text = _replace_fractions(text)
    text = re.sub(r'bb\(R\)', 'ℝ', text)
    text = re.sub(r'\\binfinity\b|\\infinity\b', '∞', text)
    text = re.sub(r'\binfinity\b', '∞', text)
    for old, new in (('<=', '≤'), ('>=', '≥'), ('!=', '≠')):
        text = text.replace(old, new)
    text = re.sub(r'(?<![A-Za-z_])pi(?![A-Za-z_])', 'π', text)
    text = re.sub(r'sqrt\(([^()]+)\)', r'√(\1)', text)
    text = re.sub(r'\|\|([^|]+)\|\|', r'∥\1∥', text)
    text = _replace_scripts(text)
    text = text.replace('*', ' · ')
    text = re.sub(r'(?<=[\w)])\s*/\s*(?=\w|\()', ' / ', text)
    text = re.sub(r'\s*·\s*', ' · ', text)
    text = re.sub(r'(?<![\w)])-(?=\d)', '−', text)
    text = re.sub(r'(?<=\w)\+(?=[\w(√])', ' + ', text)
    text = re.sub(r'(?<=\w)-(?=[\w(√])', ' − ', text)
    text = re.sub(r'\s*(≤|≥|≠|=|<|>)\s*', r' \1 ', text)
    text = re.sub(r',(?=\S)', ', ', text)
    return re.sub(r' {2,}', ' ', text.replace('$', '').replace(r'\,', ' ').replace(r'\;', ' ')).strip()


def _protect_scripts(text):
    """Replace TeX scripts with safe placeholders for real baseline shifts."""
    placeholders = {}
    output = []
    index = 0
    while index < len(text):
        if text[index] not in '^_' or index + 1 >= len(text):
            output.append(text[index])
            index += 1
            continue
        marker = text[index]
        if marker == '_':
            previous = text[index - 1] if index else ''
            following = text[index + 1]
            previous_is_math_atom = previous.isalnum() or previous in ')]}'
            following_is_script = following == '{' or following.isalnum() or following in '+-='
            if not (previous_is_math_atom and following_is_script):
                output.append(marker)
                index += 1
                continue
        if text[index + 1] == '{':
            grouped = _group_at(text, index + 1)
            if not grouped:
                output.append(marker)
                index += 1
                continue
            value, end = grouped
        else:
            value, end = text[index + 1], index + 2
        token = f'\ue100{len(placeholders)}\ue101'
        tag = 'super' if marker == '^' else 'sub'
        placeholders[token] = f'<{tag}>{escape(sanitize_math_text(value), quote=False)}</{tag}>'
        output.append(token)
        index = end
    return ''.join(output), placeholders


def _safe_text(value):
    """Escape text and put mathematical runs in the bundled math font."""
    source = "" if value is None else str(value)
    protected, placeholders = _protect_scripts(source)
    text = sanitize_math_text(protected)
    cjk_run = r'[\u3400-\u9fff\uf900-\ufaff\u3000-\u303f\uff00-\uff65]+'
    runs = re.split(r'(' + cjk_run + r')', text)
    rendered = []
    for run in runs:
        if not run:
            continue
        safe = escape(run, quote=False).replace("\n", "<br/>")
        if re.fullmatch(cjk_run, run):
            rendered.append(safe)
        else:
            for token, markup in placeholders.items():
                safe = safe.replace(escape(token, quote=False), markup)
            rendered.append(f'<font name="{MATH_FONT_NAME}">{safe}</font>')
    return ''.join(rendered)


def _text_for_pdf_match(value):
    text = sanitize_math_text(str(value).translate(_PUNCTUATION_TRANSLATION))
    text = text.replace('−', '-')
    script_glyphs = {
        **{glyph: plain for plain, glyph in _SUPERSCRIPTS.items()},
        **{glyph: plain for plain, glyph in _SUBSCRIPTS.items()},
    }
    text = text.translate(str.maketrans(script_glyphs))
    text = re.sub(r'[\u3000-\u303f\uff00-\uff65]', '', text)
    return re.sub(r'[\s\x00_\^{}]+', '', text)


class AnswerArea(Flowable):
    """A ruled work area that gives students room to solve each question."""

    def __init__(self, height=31 * mm, guide_count=5):
        super().__init__()
        self.height = height
        self.guide_count = guide_count
        self.width = 0

    def wrap(self, availWidth, availHeight):
        self.width = availWidth
        return self.width, self.height

    def draw(self):
        self.canv.saveState()
        self.canv.setStrokeColor(colors.HexColor('#D5DDE5'))
        self.canv.setLineWidth(0.45)
        step = self.height / (self.guide_count + 0.5)
        for index in range(self.guide_count):
            y = self.height - (index + 0.65) * step
            self.canv.line(15 * mm, y, self.width, y)
        self.canv.setFillColor(colors.HexColor('#8A96A3'))
        self.canv.setFont(FONT_NAME, 7.5)
        self.canv.drawString(0, self.height - step * 0.65 - 1, '作答区')
        self.canv.restoreState()


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
            expected = _text_for_pdf_match(stem)
            readable_pdf_text = _text_for_pdf_match(flat)
            if not expected or expected not in readable_pdf_text:
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
        "requirement": ParagraphStyle("QuestionRequirement", fontName=font_name, fontSize=9,
                                      leading=13, textColor=colors.HexColor("#626D78")),
        "weak": ParagraphStyle("WeakPoint", fontName=font_name, fontSize=10,
                               leading=16, textColor=colors.HexColor("#7A3E00")),
        "section": ParagraphStyle("Section", fontName=font_name, fontSize=14,
                                   leading=20, textColor=colors.HexColor("#17324D"),
                                   spaceBefore=10, spaceAfter=7),
        "question": ParagraphStyle("Question", fontName=font_name, fontSize=10.5,
                                    leading=16, textColor=colors.HexColor("#202B38"),
                                    spaceAfter=6),
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


def _chinese_question_title(index, question):
    explicit = question.get('question_title') or question.get('title')
    if explicit:
        return str(explicit)
    tier = str(question.get('tier') or '').strip().lower()
    label = _VARIATION_TITLES.get(tier)
    if label is None:
        label = next((value for key, value in _VARIATION_TITLES.items()
                      if key in tier or value in str(question.get('tier') or '')), None)
    if label is None:
        return f'第 {index} 题'
    if index < len(_CHINESE_NUMERALS):
        numeral = _CHINESE_NUMERALS[index]
    elif index < 20:
        numeral = '十' + _CHINESE_NUMERALS[index - 10] if index > 10 else '十'
    else:
        numeral = str(index)
    return f'第{numeral}题：{label}'


def _default_requirement(question, stage_label):
    supplied = question.get('requirement') or question.get('instruction')
    if supplied:
        return str(supplied)
    tier = str(question.get('tier') or '').strip().lower()
    subject_context = f"{stage_label} {question.get('content', '')}"
    if tier in ('consolidation', '同构巩固') and any(
            term in subject_context for term in ('三角', '辅助角', '凑角', 'sin', 'cos', '正弦', '余弦')):
        return '写明辅助角公式的化简过程、凑角步骤及符号判断依据。'
    if tier in ('reverse', '逆向反思', '逆向检验'):
        return '写出由结论反推的过程，并说明结合定义域或已知条件筛选的依据。'
    if tier in ('extension', '综合拓展'):
        return '写出关键公式和推导步骤，并说明结论成立的条件。'
    return '请写出关键推导过程，并说明所用公式及适用条件。'


def _requirement_box(text, style, width):
    box = Table([[Paragraph('<b>【要求】</b> ' + _safe_text(text), style['requirement'])]],
                colWidths=[width])
    box.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F2F4F6')),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    return box


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
            question_title = _chinese_question_title(index, question)
            block = [Paragraph(
                f"<b>{_safe_text(question_title)}</b>　"
                f"<span color='#7A8795'>[考点：{_safe_text(stage_label or '专项')} ]</span><br/>"
                f"{_safe_text(question.get('content', ''))}", style["question"])]
            from .materials import _normalize_options
            for option_index, option in enumerate(_normalize_options(question.get('options'))):
                label = chr(65 + option_index % 26)
                block.append(Paragraph(f"{label}. {_safe_text(option['text'])}", style["option"]))
            requirement = _default_requirement(question, stage_label)
            block.extend([
                _requirement_box(requirement, style, 170 * mm),
                Spacer(1, 2 * mm),
                AnswerArea(height=31 * mm, guide_count=5),
            ])
            story.append(KeepTogether(block))
    if include_answers or include_analysis:
        story.extend([PageBreak(), Paragraph('【参考答案与名师解析】', style['title']), Spacer(1, 5 * mm)])
        for index, question in numbered:
            block = [Paragraph(f"<b>{_safe_text(_chinese_question_title(index, question))}</b>",
                               style['section'])]
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

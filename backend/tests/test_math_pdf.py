from io import BytesIO
from pathlib import Path

from pypdf import PdfReader
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm

from app.pdf import AnswerArea, render_training_pdf, sanitize_math_text
from app.pdf import _safe_text, _text_for_pdf_match


SYMBOL_CATALOG = r"""集合：$x\in\{1,2\}, x\notin A, A\subseteq U, A\nsubseteq B, A\cap B, A\cup B, \complement_U A, \varnothing$
逻辑：$\forall x\in\mathbb{R}, \exists x, P\Rightarrow Q, P\Leftrightarrow Q$
数集：$\mathbb{N}, \mathbb{N}_{+}, \mathbb{Z}, \mathbb{Q}, \mathbb{R}, \mathbb{C}, \infty$
区间与函数：$>, <, \ge, \le, \ne, [a,b], (a,b), [a,b), (a,b], |x|, \max, \min$
函数数列：$a_n, S_n, f(x), f^{-1}(x), \log_a x, \lg x, \ln x, e^x, f'(x), f''(x), \lim$
微积分：$\int f(x)\,dx, \int_a^b f(x)\,dx, \Delta = b^2-4ac$
几何向量：$AB\parallel CD, AB\perp CD, \angle ABC, \widehat{AB}, \vec{a}, \|\vec{a}\|, \vec{a}\cdot\vec{b}, \vec{a}\times\vec{b}$"""


def test_high_school_symbol_catalog_is_readable_after_pdf_render(tmp_path):
    path = tmp_path / "symbols.pdf"
    render_training_pdf(path, "高中数学符号测试", "A4 打印样张", [("符号对照", [{"content": SYMBOL_CATALOG}])])

    reader = PdfReader(BytesIO(path.read_bytes()), strict=True)
    extracted = "".join(page.extract_text() or "" for page in reader.pages)
    for symbol in (
        "∈", "∉", "⊆", "⊈", "∩", "∪", "∁", "∅", "∀", "∃", "⇒", "⇔",
        "ℕ", "ℤ", "ℚ", "ℝ", "ℂ", "∞", "≥", "≤", "≠", "∥", "⊥", "∠", "⌒",
        "∫", "Δ", "⃗", "·", "×",
    ):
        assert symbol in extracted, f"missing rendered symbol: {symbol!r}"
    assert "□" not in extracted
    assert "f−1(x)" in extracted
    assert abs(float(reader.pages[0].mediabox.width) - A4[0]) < 0.5
    assert abs(float(reader.pages[0].mediabox.height) - A4[1]) < 0.5


def test_tex_commands_convert_to_printable_high_school_notation():
    rendered = sanitize_math_text(
        r"\mathbb{R} \mathbb{N}_{+} \frac{a_n}{b^2} \sqrt{x+1} "
        r"\overline{AB} \widehat{AB} \vec{a} \parallel \perp \notin \nsubseteq"
    )
    assert "ℝ" in rendered and "ℕ" in rendered and "₊" in rendered
    assert " / " in rendered and "√" in rendered
    assert "A̅B̅" in rendered and "⌒AB" in rendered
    assert "a⃗" in rendered and "∥" in rendered and "⊥" in rendered
    assert "∉" in rendered and "⊈" in rendered
    assert "<super>−1</super>" in _safe_text(r"f^{-1}(x)")
    assert "<sub>U</sub>" in _safe_text(r"C_U A")


def test_printable_answer_area_has_five_handwriting_guides():
    area = AnswerArea(height=42 * mm)
    width, height = area.wrap(170 * mm, A4[1])
    assert width == 170 * mm
    assert height == 42 * mm
    assert area.guide_count == 5
    default_area = AnswerArea()
    assert 80 <= default_area.height <= 100
    assert default_area.guide_count == 5


def test_three_variations_keep_titles_requirements_and_separate_answer_page(tmp_path):
    questions = [
        {
            "tier": "consolidation",
            "content": r"已知 f(x)=sin(x)cos(x)+√3/2·cos(2x)，求 f(π/6)。",
            "requirement": "写明辅助角公式的使用过程和凑角依据。",
            "answer": "1/2",
            "analysis": "先用辅助角公式化简，再代入角度。最终答案：1/2",
        },
        {
            "tier": "reverse",
            "content": r"已知 sin(α+π/6)=1，且 α∈(0,π/3)，求 α。",
            "requirement": "说明由函数值反推角度时如何结合定义域筛选。",
            "answer": "π/3",
            "analysis": "由正弦函数取值为 1 得 α+π/6=π/2。最终答案：π/3",
        },
        {
            "tier": "extension",
            "content": r"已知 sin(x)+cos(x)=√2，求 sin(2x)。",
            "requirement": "写出必要的等式变形，并说明等号成立条件。",
            "answer": "1",
            "analysis": "两边平方后结合 sin²(x)+cos²(x)=1。最终答案：1",
        },
    ]
    path = tmp_path / "three_variations.pdf"
    render_training_pdf(
        path,
        "2026 年高中数学专项强化练习卷",
        "针对考点：三角函数辅助角公式与凑角求值",
        [("三角函数辅助角公式与凑角求值", questions)],
        include_answers=True,
        include_analysis=True,
    )

    reader = PdfReader(BytesIO(path.read_bytes()), strict=True)
    assert len(reader.pages) == 2
    question_page = reader.pages[0].extract_text()
    answer_page = reader.pages[1].extract_text()
    for text in (
        "2026 年高中数学专项强化练习卷",
        "针对考点：三角函数辅助角公式与凑角求值",
        "第一题：同构巩固（原题考点对应）",
        "第二题：逆向检验",
        "第三题：综合拓展",
        "【要求】",
        "写明辅助角公式的使用过程和凑角依据",
        "姓名：___________",
        "班级：___________",
        "得分：___________",
    ):
        assert text in question_page
    assert _text_for_pdf_match("已知 f(x)=sin(x)cos(x)+√3/2·cos(2x)，求 f(π/6)。") in _text_for_pdf_match(question_page)
    assert "参考答案" not in question_page
    assert "最终答案" not in question_page
    assert "【参考答案与名师解析】" in answer_page
    assert "【参考答案】" in answer_page and "【思路剖析】" in answer_page
    assert "π / 3" in answer_page
    assert "两边平方后结合" in answer_page
    assert abs(float(reader.pages[0].mediabox.width) - A4[0]) < 0.5
    assert abs(float(reader.pages[0].mediabox.height) - A4[1]) < 0.5


def test_tex_fraction_has_unambiguous_visible_separator():
    assert sanitize_math_text(r"\frac{5-12\sqrt{3}}{26}") == "(5 − 12√(3)) / (26)"

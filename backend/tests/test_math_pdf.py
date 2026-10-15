from io import BytesIO
from pathlib import Path

from pypdf import PdfReader
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm

from app.pdf import AnswerArea, render_training_pdf, sanitize_math_text
from app.pdf import _safe_text


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
    assert "⁄" in rendered and "√" in rendered
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

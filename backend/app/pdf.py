"""HTML based practice paper PDF rendering."""

from pathlib import Path
from tempfile import NamedTemporaryFile

from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.sync_api import sync_playwright


TEMPLATE_DIR = Path(__file__).parent / "templates"
_jinja = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(("html", "xml")),
)


def render_training_pdf(path, title, meta, groups, include_answers=False, include_analysis=False):
    """Render a practice paper to ``path`` and return that path.

    This keeps the signature used by training exports and the materials API.
    """
    sections = []
    weak_points = []
    for label, questions in groups:
        label = label or "专项练习"
        if label not in weak_points:
            weak_points.append(label)
        sections.append({"title": label, "questions": questions})

    html = _jinja.get_template("exam_template.html").render(
        title=title or "薄弱考点专项强化练习卷",
        meta=meta or "姓名：___________　班级：___________　考号：___________　得分：___________",
        weak_points=weak_points,
        sections=sections,
        include_answers=include_answers,
        include_analysis=include_analysis,
        katex_css=(Path(__file__).parent / "static" / "katex" / "katex.min.css").as_uri(),
        katex_js=(Path(__file__).parent / "static" / "katex" / "katex.min.js").as_uri(),
        auto_render_js=(Path(__file__).parent / "static" / "katex" / "contrib" / "auto-render.min.js").as_uri(),
    )

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w", suffix=".html", encoding="utf-8", dir=output_path.parent, delete=False) as handle:
        handle.write(html)
        html_path = Path(handle.name)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
            try:
                page = browser.new_page()
                page.goto(html_path.as_uri(), wait_until="load")
                page.evaluate("document.fonts.ready")
                page.wait_for_function("window.__mathReady === true")
                page.pdf(
                    path=str(output_path), format="A4", print_background=True,
                    prefer_css_page_size=True,
                    display_header_footer=False,
                )
            finally:
                browser.close()
    finally:
        html_path.unlink(missing_ok=True)
    return output_path

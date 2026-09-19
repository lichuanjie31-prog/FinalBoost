from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

PAGE = (1240, 1754)
MARGIN = 90
FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyh.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
]
BOLD_CANDIDATES = [r"C:\Windows\Fonts\msyhbd.ttc"] + FONT_CANDIDATES


def _font(size, bold=False):
    for path in (BOLD_CANDIDATES if bold else FONT_CANDIDATES):
        try: return ImageFont.truetype(path, size)
        except Exception: continue
    return ImageFont.load_default()


def _wrap(draw, text, font, max_width):
    lines, line = [], ""
    for char in text:
        if char == "\n":
            lines.append(line); line = ""; continue
        if draw.textlength(line + char, font=font) <= max_width:
            line += char
        else:
            lines.append(line); line = char
    lines.append(line)
    return lines


def render_training_pdf(path, title, meta, groups, include_answers=False, include_analysis=False):
    font_title, font_head, font_body, font_small = _font(46, True), _font(30, True), _font(24), _font(20)
    pages = []
    image = Image.new("RGB", PAGE, "white")
    draw = ImageDraw.Draw(image)
    y = MARGIN

    def new_page():
        nonlocal image, draw, y
        pages.append(image)
        image = Image.new("RGB", PAGE, "white")
        draw = ImageDraw.Draw(image)
        y = MARGIN

    def write(text, font, gap=10, color=(23, 25, 28)):
        nonlocal y
        for line in _wrap(draw, text, font, PAGE[0] - 2 * MARGIN):
            if y + font.size + gap > PAGE[1] - MARGIN: new_page()
            draw.text((MARGIN, y), line, font=font, fill=color)
            y += font.size + gap

    write(title, font_title, gap=16)
    write(meta, font_small, gap=8, color=(113, 113, 122))
    y += 16
    for stage_label, questions in groups:
        if y + font_head.size + 30 > PAGE[1] - MARGIN: new_page()
        write(f"【{stage_label}】", font_head, gap=14)
        for index, question in enumerate(questions, 1):
            write(f"{index}. {question['content']}", font_body, gap=8)
            for option in question.get("options", []):
                write(f"    {option['key']}. {option['text']}", font_small, gap=6)
            if include_answers and question.get("answer"):
                write(f"    答案：{question['answer']}", font_small, gap=6, color=(14, 128, 120))
            if include_analysis and question.get("analysis"):
                write(f"    解析：{question['analysis']}", font_small, gap=6, color=(82, 82, 91))
            y += 6
        y += 10
    write("本内容由 AI 生成，仅供参考（FinalBoost）", font_small, gap=6, color=(161, 161, 170))
    pages.append(image)
    pages[0].save(path, "PDF", resolution=150.0, save_all=True, append_images=pages[1:])
    return Path(path)

"""专项练习卷 PDF 排版：复用 pdf.py 的 Pillow 渲染，不调用任何大模型。

与 training 模块的区别：题目由平台模型动态生成后传入，不依赖数据库题库，
因此这里同步渲染并直接返回 PDF 文件（不是 202 + 轮询的导出任务）。
"""
import os
import tempfile

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from starlette.background import BackgroundTask

from .common import fail
from .pdf import render_training_pdf
from .service_auth import service_token_guard

router = APIRouter(prefix='/api/v1/materials', tags=['materials'])


class MaterialQuestion(BaseModel):
    stem: str = ''
    type: str = ''
    options: list[dict] = []
    answer: str = ''
    analysis: str = ''


class MaterialSection(BaseModel):
    knowledgePoint: str = ''
    questions: list[MaterialQuestion] = []


class MaterialPdfIn(BaseModel):
    model_config = ConfigDict(extra="allow")
    title: str = '专项练习卷'
    course: str = ''
    meta: str = ''
    sections: list[MaterialSection] = []
    includeAnswers: bool = False
    includeAnalysis: bool = False


def _normalize_options(options):
    """pdf.py 要求 options 为 [{'key': 'A', 'text': '...'}]；缺 key 时按顺序补 A/B/C。"""
    normalized = []
    for index, option in enumerate(options or [], 1):
        fallback_key = chr(64 + index) if index <= 26 else str(index)
        if isinstance(option, dict):
            normalized.append({
                'key': str(option.get('key') or fallback_key),
                'text': str(option.get('text') or ''),
            })
        else:
            normalized.append({'key': fallback_key, 'text': str(option)})
    return normalized


@router.post('/pdf')
def material_pdf(body: MaterialPdfIn, _=Depends(service_token_guard)):
    total = sum(len(section.questions) for section in body.sections)
    if total == 0:
        fail(422, '专项卷没有任何题目')

    groups = []
    for section in body.sections:
        items = [{
            'content': question.stem,
            'options': _normalize_options(question.options),
            'answer': question.answer,
            'analysis': question.analysis,
        } for question in section.questions]
        groups.append((section.knowledgePoint or body.course or '专项', items))

    meta = body.meta or f"{body.course} · 共 {total} 题"
    handle = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
    handle.close()
    render_training_pdf(handle.name, body.title, meta, groups,
                        include_answers=body.includeAnswers,
                        include_analysis=body.includeAnalysis)
    filename = f"{body.title or '专项练习卷'}.pdf"
    return FileResponse(handle.name, media_type='application/pdf', filename=filename,
                        background=BackgroundTask(os.unlink, handle.name))

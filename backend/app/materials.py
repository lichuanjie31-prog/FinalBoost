"""专项练习卷 PDF 排版：复用 pdf.py 的 Pillow 渲染，不调用任何大模型。

与 training 模块的区别：题目由平台模型动态生成后传入，不依赖数据库题库，
因此这里同步渲染并直接返回 PDF 文件（不是 202 + 轮询的导出任务）。
"""
import os
import tempfile
import re
from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator
from starlette.background import BackgroundTask

from .common import fail
from .pdf import render_training_pdf
from .service_auth import service_token_guard

router = APIRouter(prefix='/api/v1/materials', tags=['materials'])


class MaterialQuestion(BaseModel):
    stem: str = Field(min_length=1, validation_alias=AliasChoices('stem', 'content', 'question', 'text'))
    question_title: str = Field(default='', validation_alias=AliasChoices(
        'question_title', 'questionTitle', 'title'))
    tier: str = ''
    requirement: str = Field(default='', validation_alias=AliasChoices(
        'requirement', 'requirements', 'instruction'))
    type: str = ''
    options: list[dict] = []
    answer: str = ''
    analysis: str = ''
    validation_status: Literal['passed', 'failed', 'pending'] = 'passed'

    @field_validator('stem')
    @classmethod
    def require_visible_stem(cls, value):
        value = re.sub('[\u200b\u200c\u200d\ufeff]', '', value).strip()
        if not value:
            raise ValueError('题干不能为空或只有不可见字符')
        return value

    @model_validator(mode='before')
    @classmethod
    def normalize_status(cls, value):
        if isinstance(value, BaseModel):
            value = value.model_dump()
        if isinstance(value, dict):
            value = dict(value)
            # Conflicting aliases must never reopen the quality gate.
            statuses = [value[key] for key in ('validation_status', 'validationStatus') if key in value]
            if statuses:
                value['validation_status'] = next((s for s in statuses if s != 'passed'), 'passed')
        return value

    @field_validator('options', mode='before')
    @classmethod
    def normalize_options(cls, value):
        return _normalize_options(value)


class MaterialSection(BaseModel):
    knowledgePoint: str = Field(default='', validation_alias=AliasChoices(
        'knowledgePoint', 'sectionTitle', 'title', 'topic'))
    questions: list[MaterialQuestion] = Field(default_factory=list, validation_alias=AliasChoices(
        'questions', 'problems', 'items'))


class MaterialPdfIn(BaseModel):
    model_config = ConfigDict(extra="allow")
    title: str = '专项练习卷'
    course: str = ''
    meta: str = ''
    sections: list[MaterialSection] = []
    includeAnswers: bool = False
    includeAnalysis: bool = False

    @model_validator(mode='before')
    @classmethod
    def normalize_sections(cls, value):
        if not isinstance(value, dict):
            return value
        value = dict(value)
        entries = next((value[key] for key in ('sections', 'groups', 'problems', 'questions')
                        if key in value and value[key] is not None), [])
        if not isinstance(entries, list):
            raise ValueError('题卷分组必须为数组')
        # A top-level flat question list forms one section. A grouped list
        # uses exactly the same section aliases at every accepted entry point.
        groups = []
        for entry in entries:
            if isinstance(entry, BaseModel):
                entry = entry.model_dump()
            if not isinstance(entry, dict):
                raise ValueError('题目或分组结构无效')
            if any(key in entry for key in ('questions', 'problems', 'items')):
                groups.append(entry)
            else:
                if not groups or groups[-1].get('_flat') is not True:
                    groups.append({'knowledgePoint': entry.get('source_knowledge_point', ''),
                                   'questions': [], '_flat': True})
                groups[-1]['questions'].append(entry)
        value['sections'] = groups
        return value

    def approved_sections(self):
        """Remove rejected candidates before files or fallback content exist."""
        return self.model_copy(update={'sections': [
            section.model_copy(update={'questions': [question for question in section.questions
                                                    if question.validation_status == 'passed']})
            for section in self.sections]})


QUALITY_GATE_MESSAGE = '所有候选变式题均未通过质量校验(failed)，已阻断生成不合格试卷'


def _normalize_options(options):
    """pdf.py 要求 options 为 [{'key': 'A', 'text': '...'}]；缺 key 时按顺序补 A/B/C。"""
    if options is None:
        return []
    if not isinstance(options, list):
        raise ValueError('选项必须为数组')
    normalized = []
    for index, option in enumerate(options or [], 1):
        fallback_key = chr(64 + index) if index <= 26 else 'A'
        if isinstance(option, dict):
            normalized.append({
                'key': str(option.get('key') or option.get('label') or fallback_key),
                'text': str(next((option[key] for key in ('text', 'content', 'value')
                                  if key in option and option[key] is not None), '')),
            })
        else:
            if not isinstance(option, str):
                raise ValueError('选项必须为文本或字典')
            match = re.match(r'^\s*([A-Za-z]|\d+)[.、:：)）]\s*(.*)$', option, re.DOTALL)
            normalized.append({'key': match.group(1).upper() if match else fallback_key,
                               'text': match.group(2) if match else option})
    return normalized


@router.post('/pdf')
def material_pdf(body: MaterialPdfIn, _=Depends(service_token_guard)):
    candidate_total = sum(len(section.questions) for section in body.sections)
    body = body.approved_sections()
    total = sum(len(section.questions) for section in body.sections)
    if total == 0:
        fail(422, QUALITY_GATE_MESSAGE if candidate_total else '专项卷没有任何题目')

    groups = []
    for section in body.sections:
        items = [{
            'content': question.stem,
            'question_title': question.question_title,
            'tier': question.tier,
            'requirement': question.requirement,
            'options': _normalize_options(question.options),
            'answer': question.answer,
            'analysis': question.analysis,
        } for question in section.questions]
        groups.append((section.knowledgePoint or body.course or '专项', items))

    knowledge_points = '、'.join(section.knowledgePoint for section in body.sections
                                 if section.knowledgePoint)
    meta = body.meta or (f"针对考点：{knowledge_points} · 共 {total} 题"
                         if knowledge_points else f"{body.course} · 共 {total} 题")
    handle = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
    handle.close()
    render_training_pdf(handle.name, body.title, meta, groups,
                        include_answers=body.includeAnswers,
                        include_analysis=body.includeAnalysis)
    filename = f"{body.title or '专项练习卷'}.pdf"
    return FileResponse(handle.name, media_type='application/pdf', filename=filename,
                        background=BackgroundTask(os.unlink, handle.name))

"""Speed, correctness and byte-integrity regressions for mastery practice."""
import base64
import hashlib
from io import BytesIO
import time

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import EncodedStreamObject, NameObject

from app.mcp_bridge import create_mcp_server


SOURCE = ('第17题(1)：设f(t)=sin(t)*cos(t)+sqrt(3)/2*cos(2*t)。'
          '若f(x/2-pi/12)=3/5，pi/3<x<5*pi/6，求cos(x)。')
POINT = '辅助角公式与凑角求值'


def pdf_tool():
    return create_mcp_server()._tool_manager.get_tool('generate_practice_pdf').fn


@pytest.mark.parametrize('item', [{}, {'stem': ''}, {'content': ' \n\t'}, {'stem': '\u200b\ufeff'}])
def test_blank_questions_cannot_produce_pdf(item):
    result = pdf_tool()(sections=[{'questions': [item]}])
    assert result.get('error_code') == 'PARSE_FAILED'
    assert 'base64' not in result


def test_corrupted_ascii85_output_is_blocked(monkeypatch):
    import app.mcp_bridge as bridge
    def broken_renderer(operation, arguments, timeout):
        writer = PdfWriter()
        page = writer.add_blank_page(width=595, height=842)
        stream = EncodedStreamObject()
        stream._data = b'uuuuu~>'
        stream[NameObject('/Filter')] = NameObject('/ASCII85Decode')
        page[NameObject('/Contents')] = writer._add_object(stream)
        writer.write(arguments['path'])
    monkeypatch.setattr(bridge, '_run_isolated', broken_renderer)
    result = pdf_tool()(sections=[{'questions': [{'stem': '计算 1+1'}]}])
    assert result.get('is_error') is True
    assert 'base64' not in result


def test_auxiliary_angle_set_is_three_verified_questions_without_model():
    from app.services.verified_variations import auxiliary_angle_variations
    started = time.monotonic()
    result = auxiliary_angle_variations(SOURCE, POINT)
    assert time.monotonic() - started < 30
    assert len(result) == 3
    assert {q.tier for q in result} == {'consolidation', 'reverse', 'extension'}
    assert all(q.validation_status == 'passed' and q.stem.strip() and q.analysis.strip() for q in result)
    # Values derived independently for a 5-12-13 triangle rotated by pi/3.
    from app.marking.symbolic import check_answer
    expected = ['(5-12*sqrt(3))/26', '5/13', '-161/289']
    for question, answer in zip(result, expected):
        assert check_answer(question.stem, question.answer, answer)['verdict'] == 'correct'
    assert all('辅助角' in q.stem for q in result)
    assert '区间' in result[0].analysis or '象限' in result[0].analysis
    assert 'cos(x)' in result[1].stem and '求' in result[1].stem


def test_source_to_three_question_pdf_finishes_under_three_minutes():
    started = time.monotonic()
    result = pdf_tool()(sourceQuestion=SOURCE, sourceKnowledgePoint=POINT,
                        includeAnswers=True, includeAnalysis=True)
    elapsed = time.monotonic() - started
    assert result.get('mimeType') == 'application/pdf', result
    assert elapsed < 180
    reader = PdfReader(BytesIO(base64.b64decode(result['base64'])))
    texts = [p.extract_text() for p in reader.pages]
    assert len(reader.pages) >= 2
    student = '\n'.join(t for t in texts if '参考答案与名师解析' not in t)
    assert all(title in student for title in (
        '第一题：同构巩固（原题考点对应）', '第二题：逆向检验', '第三题：综合拓展'))
    assert '辅助角' in student
    assert '参考答案与名师解析' in '\n'.join(texts)


def test_download_artifact_round_trip_has_original_hash(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import create_app
    monkeypatch.setenv('MATERIAL_ARTIFACT_DIR', str(tmp_path / 'artifacts'))
    monkeypatch.setenv('MATERIAL_PUBLIC_BASE_URL', 'http://testserver')
    app = create_app(data_dir=tmp_path / 'db', grading_mode='mock', rag_enabled=False)
    result = pdf_tool()(sourceQuestion=SOURCE, sourceKnowledgePoint=POINT, delivery='download')
    assert 'base64' not in result and result['questionCount'] == 3
    with TestClient(app) as client:
        response = client.get(result['downloadUrl'])
        assert response.status_code == 200
        assert hashlib.sha256(response.content).hexdigest() == result['sha256']
        assert len(response.content) == result['sizeBytes']
        reader = PdfReader(BytesIO(response.content))
        assert '辅助角' in '\n'.join(p.extract_text() for p in reader.pages)


def test_download_artifact_expiry_and_unknown_token(tmp_path, monkeypatch):
    from app.services.practice_artifacts import store_pdf, load_pdf
    from app.pdf import render_training_pdf
    monkeypatch.setenv('MATERIAL_ARTIFACT_DIR', str(tmp_path / 'artifacts'))
    path = tmp_path / 'paper.pdf'
    render_training_pdf(path, '练习', '', [('代数', [{'content': '计算 1+1'}])])
    result = store_pdf(path.read_bytes(), 'paper.pdf', 1, ttl_seconds=1)
    token = result['downloadUrl'].rsplit('/', 1)[-1]
    assert load_pdf(token, now=time.time() + 2) is None
    assert load_pdf('../paper') is None


def test_unrelated_source_does_not_get_trigonometry_template():
    from app.services.verified_variations import auxiliary_angle_variations
    assert auxiliary_angle_variations('讨论导数符号与函数单调性', '导数应用') is None


def test_renderer_avoids_fragile_ascii85_streams(tmp_path):
    from app.pdf import render_training_pdf
    path = tmp_path / 'paper.pdf'
    render_training_pdf(path, '练习', '', [('代数', [{'content': '计算 1+1'}])])
    reader = PdfReader(path)
    assert all('/ASCII85Decode' not in str(page['/Contents'].get_object().get('/Filter'))
               for page in reader.pages)


def _stall_worker(connection, operation, arguments):
    connection.send(('ready', None))
    time.sleep(5)


def test_shared_deadline_stops_worker_even_during_startup(monkeypatch):
    import app.mcp_bridge as bridge
    monkeypatch.setattr(bridge, '_isolated_tool_worker', _stall_worker)
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        bridge._run_isolated('generate_variations', {}, 120, deadline=started + .5)
    assert time.monotonic() - started < 3


def test_generic_provider_requests_really_overlap():
    import json
    from app.services.variation_questions import generate_variation_questions
    starts = []
    class Provider:
        def invoke(self, prompt):
            starts.append(time.monotonic())
            time.sleep(.25)
            tier = next(t for t in ('consolidation', 'reverse', 'extension') if f'tier 固定为 {t}' in prompt)
            stems = {'consolidation': '解一元一次方程 x+1=3',
                     'reverse': '一元一次方程的解已知为2，请反求常数',
                     'extension': '一元一次方程应用：水果购买与数量关系'}
            return type('Response', (), {'content': json.dumps({
                'tier': tier, 'source_knowledge_point': '一元一次方程', 'difficulty': 'easy',
                'stem': stems[tier], 'answer': '2', 'analysis': '最终答案：2'})})()
    result = generate_variation_questions(Provider(), '解x+1=3', '一元一次方程', parallel=True)
    assert len(starts) == 3 and max(starts) - min(starts) < .2
    assert all(q.validation_status == 'passed' for q in result['questions'])


def test_checked_download_never_writes_corrupt_bytes(tmp_path, monkeypatch):
    import importlib.util
    from pathlib import Path
    script = Path(__file__).resolve().parents[2] / '.agents/skills/paper-boost-assistant/scripts/download_practice_pdf.py'
    spec = importlib.util.spec_from_file_location('checked_practice_download', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    good = b'%PDF-1.4\nverified bytes\n%%EOF'
    metadata = {'downloadUrl': 'https://example.test/api/v1/materials/artifacts/' + 'a' * 43,
                'sha256': hashlib.sha256(good).hexdigest(), 'sizeBytes': len(good), 'questionCount': 3}
    monkeypatch.setattr(module, 'urlopen', lambda *args, **kwargs: BytesIO(b'damaged'))
    destination = tmp_path / 'student.pdf'
    with pytest.raises(ValueError):
        module.download_pdf(metadata, destination)
    assert not destination.exists()


def test_practice_model_disables_hidden_retries(monkeypatch):
    import app.mcp_bridge as bridge
    captured = {}
    def factory(settings, **kwargs):
        captured.update(kwargs)
        return None
    monkeypatch.setattr(bridge, 'create_llm_from_settings', factory)
    result = bridge._generate_variation_payload('解方程 x+1=3', '一元一次方程')
    assert result['error_code'] == 'SERVICE_DEGRADED'
    assert captured['max_retries'] == 0
    assert captured['timeout'] <= 20


def test_solver_formulas_are_readable_in_pdf_text():
    from app.pdf import sanitize_math_text
    assert sanitize_math_text('5pi/6 + sqrt(3)') == '5π / 6 + √(3)'


def test_artifact_storage_failure_is_structured(monkeypatch):
    import app.mcp_bridge as bridge
    def full(*args):
        raise ValueError('storage full')
    monkeypatch.setattr(bridge, 'store_pdf', full)
    result = pdf_tool()(sections=[{'questions': [{'stem': '计算1+1'}]}], delivery='download')
    assert result['error_code'] == 'RESOURCE_LIMIT'
    assert 'downloadUrl' not in result


def test_downloader_cli_deadline_kills_slow_stream(tmp_path):
    import importlib.util
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from pathlib import Path
    import threading
    script = Path(__file__).resolve().parents[2] / '.agents/skills/paper-boost-assistant/scripts/download_practice_pdf.py'
    spec = importlib.util.spec_from_file_location('deadline_downloader', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    data = b'%PDF-1.4\n' + b'0' * 100 + b'\n%%EOF'
    class SlowResponse(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            try:
                for byte in data:
                    self.wfile.write(bytes([byte]))
                    self.wfile.flush()
                    time.sleep(.05)
            except (BrokenPipeError, ConnectionResetError):
                pass
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), SlowResponse)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    metadata = tmp_path / 'metadata.json'
    import json
    metadata.write_text(json.dumps({'downloadUrl': f'http://127.0.0.1:{server.server_port}/api/v1/materials/artifacts/' + 'a' * 43,
                                   'sha256': hashlib.sha256(data).hexdigest(), 'sizeBytes': len(data),
                                   'questionCount': 3}), encoding='utf-8')
    started = time.monotonic()
    try:
        with pytest.raises(ValueError, match='超时'):
            module.checked_download(metadata, tmp_path / 'paper.pdf', timeout_seconds=.3)
        assert time.monotonic() - started < 2
        assert not (tmp_path / 'paper.pdf').exists()
    finally:
        server.shutdown()
        server.server_close()


def test_auxiliary_angle_tags_cluster_under_trigonometry_code():
    tool = create_mcp_server()._tool_manager.get_tool('analyze_weak_points').fn
    result = tool(questions=[{'questionId': '17.1', 'correct': False,
                             'knowledgePoints': ['辅助角公式与凑角求值', '三角恒等变换']}])
    assert len(result['weakPoints']) == 1
    assert result['weakPoints'][0]['code'] == 'MATH-TRIG-01'

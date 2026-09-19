"""Qwen VL marking acceptance.

Only the HTTP boundary is faked: the real QwenMarkingProvider builds the real
payload, parses the real response shape and maps it to the unified DTO, while the
service, the database, the HTTP API and the status machine all run for real.
"""
import json
import logging
import time

import httpx
import pytest
from test_auth import client_for, register, bearer
from test_business import setup_exam, upload

from app.marking.qwen import QwenMarkingProvider

API_KEY = 'sk-test-not-a-real-key'


def qwen_answer(questions, subject='高等数学'):
    return {'subject': subject,
            'page_summary': {'recognized_questions': len(questions), 'correct': 0,
                             'incorrect': 0, 'undetermined': 0},
            'questions': questions}


def question(body, judgement='incorrect', answer='x^2/2', number='1', children=None, **over):
    data = {'question_id': number, 'question_number': number,
            'question_text': body, 'question_type': '计算题',
            'student_answer': answer, 'judgement': judgement,
            'correct_answer': 'x^2/2 + C', 'analysis': '漏写积分常数',
            'error_reason': '漏写常数 C', 'knowledge_points': ['不定积分', '积分常数'],
            'confidence': 0.92, 'children': children or []}
    data.update(over)
    return data


NESTED = [
    question('第 1 题 求不定积分', children=[
        question('第 1 题 第 (1) 问', judgement='correct', answer='x^2/2 + C', number='1.1',
                 analysis='过程与结果均正确', error_reason='', knowledge_points=['不定积分'])]),
    question('第 2 题 判断级数敛散性', judgement='undetermined', answer='', number='2',
             correct_answer='发散', analysis='学生作答无法辨认', error_reason='',
             knowledge_points=['级数敛散性']),
    question('第 3 题 求极限', judgement='correct', answer='1', number='3',
             correct_answer='1', analysis='正确', error_reason='', knowledge_points=['极限']),
]


class FakeResponse:
    def __init__(self, payload, status_code=200, headers=None):
        self._payload, self.status_code = payload, status_code
        self.headers = headers or {}
        self.text = json.dumps(payload) if not isinstance(payload, Exception) else ''

    def json(self):
        if isinstance(self._payload, Exception):
            raise ValueError('not json')
        return self._payload


class FakeHttp:
    """Stands in for the httpx client: the provider's own code still runs."""

    def __init__(self, response=None, raises=None, delay=0.0):
        self.response, self.raises, self.delay = response, raises, delay
        self.requests = []

    def post(self, url, headers=None, json=None):
        self.requests.append({'url': url, 'headers': headers or {}, 'json': json})
        if self.delay:
            time.sleep(self.delay)
        if self.raises is not None:
            raise self.raises
        return self.response


def dashscope_body(questions, model='qwen3-vl-plus'):
    return {'id': 'chatcmpl-test-1', 'model': model,
            'choices': [{'index': 0, 'finish_reason': 'stop',
                         'message': {'role': 'assistant',
                                     'content': json.dumps(qwen_answer(questions), ensure_ascii=False)}}],
            'usage': {'prompt_tokens': 1200, 'completion_tokens': 300, 'total_tokens': 1500}}


def qwen_client(tmp_path, fake, executor=None, **kwargs):
    """A real app whose qwen provider talks to a faked HTTP boundary, running inline.

    Model and base URL are pinned so the assertions below cannot drift with a
    developer's .env (Settings reads the environment directly).
    """
    kwargs.setdefault('marking_mode', 'qwen')
    kwargs.setdefault('dashscope_api_key', API_KEY)
    kwargs.setdefault('qwen_marking_model', 'qwen3-vl-plus')
    kwargs.setdefault('dashscope_base_url', 'https://dashscope.aliyuncs.com/compatible-mode/v1')
    kwargs.setdefault('marking_submit_interval', 0.01)
    kwargs.setdefault('marking_poll_interval', 0.01)
    client = client_for(tmp_path, **kwargs)
    client.app.state.marking_providers['qwen'] = QwenMarkingProvider(
        client.app.state.settings, http_client=fake)
    client.app.state.marking_executor = executor
    return client


def submit(c, auth, exam, file, key='page-1', page=0):
    return c.post('/api/v1/marking/jobs', headers=auth, json={
        'examId': exam['examId'], 'fileId': file['fileId'], 'requestKey': key, 'pageIndex': page})


# --------------------------------------------------------------------------
# 1/16. Wire format and readiness
# --------------------------------------------------------------------------

def test_request_uses_the_verified_dashscope_wire_format(tmp_path):
    fake = FakeHttp(FakeResponse(dashscope_body(NESTED)))
    with qwen_client(tmp_path, fake) as c:
        auth, exam, file = setup_exam(c)
        assert submit(c, auth, exam, file).status_code == 202
        assert len(fake.requests) == 1
        sent = fake.requests[0]
        assert sent['url'].endswith('/compatible-mode/v1/chat/completions')
        assert sent['headers']['Authorization'] == f'Bearer {API_KEY}'
        body = sent['json']
        assert body['model'] == 'qwen3-vl-plus'
        image_part, text_part = body['messages'][1]['content']
        assert image_part['type'] == 'image_url'
        assert image_part['image_url']['url'].startswith('data:image/png;base64,')
        assert text_part['type'] == 'text'
        # Structured output, exactly as documented: name is required, strict recommended.
        fmt = body['response_format']
        assert fmt['type'] == 'json_schema' and fmt['json_schema']['strict'] is True
        assert fmt['json_schema']['name'] == 'exam_marking_result'
        schema = fmt['json_schema']['schema']
        judgements = schema['properties']['questions']['items']['properties']['judgement']['enum']
        assert judgements == ['correct', 'incorrect', 'undetermined']
        # No credential is ever placed in the request body.
        assert API_KEY not in json.dumps(body)


@pytest.mark.parametrize('mode,provider,expected', [
    ('disabled', 'qwen', ('disabled', 'qwen')),
    ('disabled', 'tencent', ('disabled', 'tencent')),
    ('fixture', 'qwen', ('fixture', 'qwen')),
    ('fixture', 'tencent', ('fixture', 'tencent')),
    # `live` is what .env.example recommends; it must not fall through to disabled.
    ('live', 'qwen', ('live', 'qwen')),
    ('live', 'tencent', ('live', 'tencent')),
    # Legacy spelling: the mode names the provider and wins over MARKING_PROVIDER.
    ('qwen', 'tencent', ('live', 'qwen')),
    ('tencent', 'qwen', ('live', 'tencent')),
])
def test_every_marking_mode_resolves_to_the_right_pair(mode, provider, expected):
    from app.config import Settings
    settings = Settings(marking_mode=mode, marking_provider=provider, data_dir='.')
    assert settings.resolve_marking() == expected


def test_live_mode_without_a_key_is_not_silently_disabled(tmp_path, monkeypatch):
    """MARKING_MODE=live with no key must report NotConfigured, not MarkingDisabled."""
    for name in ('DASHSCOPE_API_KEY', 'EMBEDDING_API_KEY'):
        monkeypatch.delenv(name, raising=False)
    with client_for(tmp_path, marking_mode='live', marking_provider='qwen', dashscope_api_key='') as c:
        auth, _, _ = setup_exam(c)
        state = c.get('/api/v1/marking/readiness', headers=auth).json()['data']
        assert state['mode'] == 'live' and state['reason'] == 'NotConfigured'


def test_readiness_reports_the_qwen_provider_and_model(tmp_path):
    with qwen_client(tmp_path, FakeHttp(FakeResponse(dashscope_body(NESTED)))) as c:
        auth, _, _ = setup_exam(c)
        state = c.get('/api/v1/marking/readiness', headers=auth).json()['data']
        assert state['ready'] is True and state['provider'] == 'qwen'
        assert state['model'] == 'qwen3-vl-plus' and state['mode'] == 'live'
        health = c.get('/api/v1/health').json()['data']
        assert health['markingProvider'] == 'qwen' and health['markingModel'] == 'qwen3-vl-plus'


# --------------------------------------------------------------------------
# 1. Missing API key
# --------------------------------------------------------------------------

def test_missing_api_key_blocks_submission_without_fabricating_a_score(tmp_path, monkeypatch):
    for name in ('DASHSCOPE_API_KEY', 'EMBEDDING_API_KEY'):
        monkeypatch.delenv(name, raising=False)
    fake = FakeHttp(FakeResponse(dashscope_body(NESTED)))
    with client_for(tmp_path, marking_mode='qwen', dashscope_api_key='') as c:
        c.app.state.marking_providers['qwen'] = QwenMarkingProvider(c.app.state.settings, http_client=fake)
        c.app.state.marking_executor = None
        auth, exam, file = setup_exam(c)
        state = c.get('/api/v1/marking/readiness', headers=auth).json()['data']
        assert state['ready'] is False and state['provider'] == 'qwen'
        assert state['reason'] == 'NotConfigured' and '尚未配置' in state['message']
        blocked = submit(c, auth, exam, file)
        assert blocked.status_code == 503 and '尚未配置' in blocked.json()['message']
        # Nothing was sent, nothing was persisted, nothing was scored.
        assert fake.requests == []
        assert c.get('/api/v1/marking/jobs', params={'examId': exam['examId']},
                     headers=auth).json()['data']['items'] == []


# --------------------------------------------------------------------------
# 2/8/9. Correct JSON, multiple questions, parent + sub-question
# --------------------------------------------------------------------------

def test_structured_output_maps_onto_the_unified_result(tmp_path):
    fake = FakeHttp(FakeResponse(dashscope_body(NESTED)))
    with qwen_client(tmp_path, fake) as c:
        auth, exam, file = setup_exam(c)
        job = submit(c, auth, exam, file).json()['data']
        assert job['status'] == 'succeeded' and job['source'] == 'qwen'
        assert job['model'] == 'qwen3-vl-plus'
        result = job['result']
        # No rubric exists, so no percentage score may appear.
        assert result['totalScore'] is None and result['maxScore'] is None
        assert result['scoreStatus'] == 'unavailable'
        assert result['subject'] == '高等数学'
        # Three top-level questions, the first carrying a sub-question.
        assert [q['questionId'] for q in result['questions']] == ['1', '2', '3']
        parent = result['questions'][0]
        assert parent['children'][0]['questionId'] == '1.1'
        assert parent['children'][0]['answers'][0]['correct'] is True
        first = parent['answers'][0]
        assert first['handwriting'] == 'x^2/2' and first['correct'] is False
        assert first['rightAnswer'] == 'x^2/2 + C'
        assert first['analysis'] == '漏写积分常数'
        assert first['errorReason'] == '漏写常数 C'
        assert first['knowledgePoints'] == ['不定积分', '积分常数']
        assert first['confidence'] == pytest.approx(0.92)
        # Coordinates are reserved, never invented.
        assert first['boundingBox'] is None and first['polygon'] is None
        assert result['coordinateSpace'] == 'none'
        # Token accounting is kept for cost analysis.
        assert job['usage']['total_tokens'] == 1500
        assert job['usage']['prompt_tokens'] == 1200
        assert job['latencyMs'] is not None
        assert job['requestId'] == 'chatcmpl-test-1'


# --------------------------------------------------------------------------
# 3. Bad JSON
# --------------------------------------------------------------------------

def test_invalid_json_fails_the_page_instead_of_guessing(tmp_path):
    broken = {'id': 'x', 'choices': [{'message': {'content': 'sorry, I cannot read this'}}]}
    with qwen_client(tmp_path, FakeHttp(FakeResponse(broken))) as c:
        auth, exam, file = setup_exam(c)
        job = submit(c, auth, exam, file).json()['data']
        assert job['status'] == 'failed'
        assert job['error']['code'] == 'qwen:BadResponse'
        assert job['result'] is None


def test_empty_choices_fail_the_page(tmp_path):
    with qwen_client(tmp_path, FakeHttp(FakeResponse({'choices': []}))) as c:
        auth, exam, file = setup_exam(c)
        job = submit(c, auth, exam, file).json()['data']
        assert job['status'] == 'failed' and job['result'] is None


# --------------------------------------------------------------------------
# 4/5. Timeout and network failure
# --------------------------------------------------------------------------

def test_timeout_is_uncertain_and_never_retried(tmp_path):
    fake = FakeHttp(raises=httpx.ReadTimeout('timed out'))
    with qwen_client(tmp_path, fake) as c:
        auth, exam, file = setup_exam(c)
        job = submit(c, auth, exam, file, key='timeout').json()['data']
        # The model may have run and been billed, so it must not be auto-resubmitted.
        assert job['status'] == 'submission_unknown'
        assert job['error']['code'] == 'qwen:Timeout'
        assert job['result'] is None
        again = submit(c, auth, exam, file, key='timeout').json()['data']
        assert again['jobId'] == job['jobId'] and len(fake.requests) == 1


def test_connection_failure_is_a_definite_failure(tmp_path):
    fake = FakeHttp(raises=httpx.ConnectError('no route'))
    with qwen_client(tmp_path, fake) as c:
        auth, exam, file = setup_exam(c)
        job = submit(c, auth, exam, file).json()['data']
        assert job['status'] == 'failed' and job['error']['code'] == 'qwen:NetworkError'
        assert job['result'] is None


def test_unauthorized_and_rate_limited_are_reported(tmp_path):
    for status, code in ((401, 'qwen:Unauthorized'), (429, 'qwen:RateLimited')):
        with qwen_client(tmp_path / str(status),
                         FakeHttp(FakeResponse({'error': {'code': 'invalid_api_key'}}, status))) as c:
            auth, exam, file = setup_exam(c)
            job = submit(c, auth, exam, file).json()['data']
            assert job['status'] == 'failed' and job['error']['code'] == code
            assert job['result'] is None


# --------------------------------------------------------------------------
# 6. Empty result
# --------------------------------------------------------------------------

def test_empty_question_list_fails_rather_than_scoring_zero(tmp_path):
    with qwen_client(tmp_path, FakeHttp(FakeResponse(dashscope_body([])))) as c:
        auth, exam, file = setup_exam(c)
        job = submit(c, auth, exam, file).json()['data']
        assert job['status'] == 'failed' and job['error']['code'] == 'qwen:EmptyResult'
        assert job['result'] is None


def test_blank_questions_fail_rather_than_scoring_zero(tmp_path):
    blank = dashscope_body([question('', answer='', correct_answer='', number='1')])
    with qwen_client(tmp_path, FakeHttp(FakeResponse(blank))) as c:
        auth, exam, file = setup_exam(c)
        job = submit(c, auth, exam, file).json()['data']
        assert job['status'] == 'failed' and job['result'] is None


# --------------------------------------------------------------------------
# 7. undetermined is never incorrect
# --------------------------------------------------------------------------

@pytest.mark.parametrize('judgement,answer', [
    ('undetermined', 'x^2/2'),          # the model could not decide
    ('correct', ''),                    # no student answer was read
    ('incorrect', ''),                  # claiming wrong without reading anything
    ('maybe', 'x^2/2'),                 # an out-of-enum value
    (None, 'x^2/2'),                    # missing entirely
])
def test_unreliable_judgements_become_undetermined_not_wrong(tmp_path, judgement, answer):
    body = dashscope_body([question('第 1 题', judgement=judgement, answer=answer)])
    with qwen_client(tmp_path, FakeHttp(FakeResponse(body))) as c:
        auth, exam, file = setup_exam(c)
        job = submit(c, auth, exam, file).json()['data']
        assert job['status'] == 'succeeded'
        assert job['result']['questions'][0]['answers'][0]['correct'] is None


def test_a_blank_stem_forces_undetermined(tmp_path):
    body = dashscope_body([question('', judgement='incorrect', answer='x')])
    with qwen_client(tmp_path, FakeHttp(FakeResponse(body))) as c:
        auth, exam, file = setup_exam(c)
        job = submit(c, auth, exam, file).json()['data']
        assert job['result']['questions'][0]['answers'][0]['correct'] is None


def test_error_reason_is_dropped_when_the_answer_is_not_wrong(tmp_path):
    body = dashscope_body([question('第 1 题', judgement='correct', answer='x^2/2+C')])
    with qwen_client(tmp_path, FakeHttp(FakeResponse(body))) as c:
        auth, exam, file = setup_exam(c)
        job = submit(c, auth, exam, file).json()['data']
        answer = job['result']['questions'][0]['answers'][0]
        assert answer['correct'] is True and answer['errorReason'] == ''


# --------------------------------------------------------------------------
# 10/11/12. Idempotency, isolation, restart
# --------------------------------------------------------------------------

def test_request_key_is_idempotent_and_calls_the_model_once(tmp_path):
    fake = FakeHttp(FakeResponse(dashscope_body(NESTED)))
    with qwen_client(tmp_path, fake) as c:
        auth, exam, file = setup_exam(c)
        first = submit(c, auth, exam, file, key='same').json()['data']
        second = submit(c, auth, exam, file, key='same').json()['data']
        assert first['jobId'] == second['jobId'] and len(fake.requests) == 1
        conflict = c.post('/api/v1/marking/jobs', headers=auth, json={
            'examId': exam['examId'], 'fileId': file['fileId'], 'requestKey': 'same', 'pageIndex': 3})
        assert conflict.status_code == 409


def test_jobs_are_isolated_between_accounts(tmp_path):
    fake = FakeHttp(FakeResponse(dashscope_body(NESTED)))
    with qwen_client(tmp_path, fake) as c:
        auth, exam, file = setup_exam(c)
        job = submit(c, auth, exam, file).json()['data']
        other = bearer(register(c, 'other_user'))
        assert submit(c, other, exam, file, key='x').status_code == 403
        assert c.get('/api/v1/marking/jobs/' + job['jobId'], headers=other).status_code == 403
        assert c.get('/api/v1/marking/jobs', params={'examId': exam['examId']}, headers=other).status_code == 403
        assert c.get('/api/v1/marking/jobs', params={'examId': exam['examId']}).status_code == 401


def test_results_survive_a_restart(tmp_path):
    fake = FakeHttp(FakeResponse(dashscope_body(NESTED)))
    with qwen_client(tmp_path, fake) as c:
        auth, exam, file = setup_exam(c)
        job = submit(c, auth, exam, file).json()['data']
    # A brand new process over the same data directory.
    with client_for(tmp_path, marking_mode='qwen', dashscope_api_key=API_KEY) as c:
        login = c.post('/api/v1/auth/login', headers={'X-Requested-With': 'FinalBoost',
                                                      'Origin': 'http://127.0.0.1:5173'},
                       json={'username': 'student_one', 'password': 'Test-password-12345'})
        auth = bearer(login.json()['data'])
        listed = c.get('/api/v1/marking/jobs', params={'examId': exam['examId']}, headers=auth).json()['data']
        assert listed['items'][0]['jobId'] == job['jobId']
        assert listed['items'][0]['status'] == 'succeeded'
        assert listed['items'][0]['source'] == 'qwen'
        fetched = c.get('/api/v1/marking/jobs/' + job['jobId'], headers=auth).json()['data']
        assert fetched['result']['questions'][0]['answers'][0]['correct'] is False


def test_interrupted_sync_jobs_are_failed_on_restart(tmp_path):
    """A model call cannot survive a restart, so a stranded job must not hang forever."""
    from app.db import Database
    from app.marking.service import ExamMarkingTool
    fake = FakeHttp(FakeResponse(dashscope_body(NESTED)))
    with qwen_client(tmp_path, fake) as c:
        auth, exam, file = setup_exam(c)
        import sqlite3
        db_path = c.app.state.db.path
    # Simulate a crash mid-call by stranding a queued row.
    with sqlite3.connect(db_path) as conn:
        conn.execute("INSERT INTO marking_jobs(id,user_id,exam_id,file_id,request_key,fingerprint,status,"
                     "image_json,page_index,provider,created_at) "
                     "VALUES ('stranded',(SELECT id FROM users LIMIT 1),?,?,'k','f','running','{}',0,'qwen',?)",
                     (exam['examId'], file['fileId'], time.time()))
    settings = client_for(tmp_path, marking_mode='qwen', dashscope_api_key=API_KEY).app.state.settings
    providers = {'qwen': QwenMarkingProvider(settings, http_client=fake)}
    assert ExamMarkingTool(Database(tmp_path), providers, settings).reconcile_interrupted() == 1
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = dict(conn.execute("SELECT * FROM marking_jobs WHERE id='stranded'").fetchone())
    assert row['status'] == 'failed'
    assert json.loads(row['error_json'])['code'] == 'Interrupted'


# --------------------------------------------------------------------------
# 13/14. Provider switching
# --------------------------------------------------------------------------

def test_switching_provider_changes_which_backend_is_used(tmp_path):
    from app.marking.fixture import FixtureMarkingProvider
    fake = FakeHttp(FakeResponse(dashscope_body(NESTED)))
    with qwen_client(tmp_path, fake) as c:
        auth, exam, file = setup_exam(c)
        assert c.get('/api/v1/marking/readiness', headers=auth).json()['data']['provider'] == 'qwen'
        assert submit(c, auth, exam, file, key='q').json()['data']['source'] == 'qwen'
        # Flip the running app to the Tencent provider; the same API must keep working.
        c.app.state.marking_providers['tencent'] = FixtureMarkingProvider(
            c.app.state.settings, name='tencent')
        c.app.state.settings.marking_mode = 'tencent'
        assert c.get('/api/v1/marking/readiness', headers=auth).json()['data']['provider'] == 'tencent'
        job = submit(c, auth, exam, file, key='t').json()['data']
        assert job['source'] == 'tencent' and job['status'] == 'queued'
        polled = c.get('/api/v1/marking/jobs/' + job['jobId'], headers=auth).json()['data']
        assert polled['status'] in ('queued', 'running', 'succeeded')


def test_a_job_is_always_polled_by_the_provider_that_owns_it(tmp_path):
    """Switching providers must not orphan jobs already in flight."""
    from app.marking.fixture import FixtureMarkingProvider
    with client_for(tmp_path, marking_mode='fixture', marking_provider='tencent',
                     marking_submit_interval=0.01, marking_poll_interval=0.01) as c:
        c.app.state.marking_executor = None
        auth, exam, file = setup_exam(c)
        job = submit(c, auth, exam, file).json()['data']
        assert job['source'] == 'tencent'
        # Now the deployment switches to qwen; the tencent job keeps working.
        c.app.state.settings.marking_mode = 'qwen'
        c.app.state.marking_providers['qwen'] = FixtureMarkingProvider(c.app.state.settings, name='qwen')
        done = c.get('/api/v1/marking/jobs/' + job['jobId'], headers=auth).json()['data']
        assert done['source'] == 'tencent'
        assert done['status'] in ('queued', 'running', 'succeeded')


# --------------------------------------------------------------------------
# 15/16. No fallback, no leaked key
# --------------------------------------------------------------------------

def test_qwen_failure_never_falls_back_to_a_sample_score(tmp_path):
    for response in (FakeResponse({'choices': [{'message': {'content': 'nope'}}]}),
                     FakeResponse(dashscope_body([])),
                     FakeResponse({'error': {'code': 'x'}}, 500)):
        with qwen_client(tmp_path / str(id(response)), FakeHttp(response)) as c:
            auth, exam, file = setup_exam(c)
            job = submit(c, auth, exam, file).json()['data']
            assert job['status'] == 'failed'
            assert job['result'] is None
            assert job['usage'] is None
            # No score of any kind is present, not even as an empty field.
            assert 'totalScore' not in json.dumps(job)


def test_api_key_never_appears_in_responses_or_logs(tmp_path, caplog):
    fake = FakeHttp(FakeResponse(dashscope_body(NESTED)))
    with caplog.at_level(logging.DEBUG):
        with qwen_client(tmp_path, fake) as c:
            auth, exam, file = setup_exam(c)
            job = submit(c, auth, exam, file)
            listed = c.get('/api/v1/marking/jobs', params={'examId': exam['examId']}, headers=auth)
            health = c.get('/api/v1/health')
            readiness = c.get('/api/v1/marking/readiness', headers=auth)
            for response in (job, listed, health, readiness):
                assert API_KEY not in response.text
                assert 'sk-' not in response.text
    assert API_KEY not in caplog.text
    # The provider's environment is never serialized into the job payload either.
    assert 'dashscope' not in job.text.lower()


# --------------------------------------------------------------------------
# Async execution shape
# --------------------------------------------------------------------------

def test_synchronous_provider_runs_in_the_background(tmp_path):
    """A model call must not hold the HTTP request open."""
    from concurrent.futures import ThreadPoolExecutor
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        # The fake takes a full second; a blocking implementation would have to
        # return a terminal status, so a non-terminal one proves it did not wait.
        fake = FakeHttp(FakeResponse(dashscope_body(NESTED)), delay=1.0)
        with qwen_client(tmp_path, fake, executor=pool) as c:
            auth, exam, file = setup_exam(c)
            job = submit(c, auth, exam, file).json()['data']
            assert job['status'] in ('queued', 'running', 'submitting')
            assert job['result'] is None
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                data = c.get('/api/v1/marking/jobs/' + job['jobId'], headers=auth).json()['data']
                if data['status'] in ('succeeded', 'failed'):
                    break
                time.sleep(0.05)
            assert data['status'] == 'succeeded'
            assert data['result']['questions'][0]['answers'][0]['correct'] is False
    finally:
        pool.shutdown(wait=True)


def test_reference_answer_image_is_rejected_for_qwen(tmp_path):
    fake = FakeHttp(FakeResponse(dashscope_body(NESTED)))
    with qwen_client(tmp_path, fake) as c:
        auth, exam, file = setup_exam(c)
        reference = upload(c, auth).json()['data']
        response = c.post('/api/v1/marking/jobs', headers=auth, json={
            'examId': exam['examId'], 'fileId': file['fileId'],
            'referenceFileId': reference['fileId'], 'requestKey': 'ref', 'pageIndex': 0})
        # Saying so beats silently ignoring the upload.
        assert response.status_code == 422 and '参考答卷' in response.json()['message']
        assert fake.requests == []

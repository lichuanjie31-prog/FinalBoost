"""Offline acceptance for the Tencent marking pathway.

Only the vendor boundary is replaced: the real provider is exercised with a stub
HTTP client, and the fixture provider stands in for the SDK during HTTP tests.
Nothing here mocks the service, the router, persistence or the result mapping.
"""
import base64
import io
import json
import warnings

import pytest
from PIL import Image
from test_auth import client_for, register, bearer
from test_business import setup_exam, upload

from app.config import Settings
from app.marking.fixture import FixtureMarkingProvider
from app.marking.models import normalize_result
from app.marking.provider import (QUESTION_CONFIG, TencentMarkingProvider, build_submit_params,
                                  prepare_image, provider_message)

DONE_RAW = {
    'JobStatus': 'DONE', 'Angle': -1.5, 'ErrorCode': '', 'ErrorMessage': '',
    'MarkInfos': [{
        'MarkItemTitle': '第 1 题', 'QuestionPositions': [1, 2, 20, 2, 20, 30, 1, 30],
        'QuestionImagePositions': [{'Position': [3, 4, 30, 4, 30, 40, 3, 40]}, {'Position': 'bad'}],
        'RightAnswer': 'x^2/2 + C', 'Subject': '数学', 'QuestionType': '计算题',
        'AnswerInfos': [
            {'HandwriteInfo': 'x^2/2', 'IsCorrect': False, 'AnswerAnalysis': '漏掉常数',
             'HandwriteInfoPositions': [1, 2, 20, 2, 20, 30, 1, 30],
             'RightAnswer': 'x^2/2 + C', 'KnowledgePoints': ['不定积分']},
            {'HandwriteInfo': '不确定', 'AnswerAnalysis': '', 'KnowledgePoints': []},
        ],
        'MarkInfos': [{'MarkItemTitle': '第 1(1) 问', 'AnswerInfos': [
            {'HandwriteInfo': 'x', 'IsCorrect': True, 'KnowledgePoints': ['不定积分']}]}],
    }],
}


def png_bytes(size=(20, 20)):
    out = io.BytesIO()
    Image.new('RGB', size, 'white').save(out, 'PNG')
    return out.getvalue()


# --------------------------------------------------------------------------
# 1. SDK request boundary
# --------------------------------------------------------------------------

def test_submit_params_match_the_verified_sdk_contract():
    params = build_submit_params(png_bytes(), png_bytes())
    assert set(params) == {'ImageBase64', 'QuestionConfigMap', 'AssistMarkType', 'ImageBase64List'}
    config = json.loads(params['QuestionConfigMap'])
    assert config == QUESTION_CONFIG
    # The three switches the task explicitly asked for, plus sub-question coords.
    assert config['TrueAnswer'] and config['KnowledgePoints'] and config['StepCorrection']
    assert config['OutputSubQuestionsAndCoords']
    # 2 = whole-page assist: the answer paper rides in ImageBase64List (max two).
    assert params['AssistMarkType'] == 2
    assert len(params['ImageBase64List']) <= 2
    base64.b64decode(params['ImageBase64'])


def test_reference_answer_is_omitted_so_no_stitching_is_requested():
    params = build_submit_params(png_bytes(), None)
    # Without AssistMarkType=2 the vendor would stitch ImageBase64List across pages,
    # which this project never wants for a per-page job.
    assert 'ImageBase64List' not in params
    assert 'AssistMarkType' not in params


class _FakeClient:
    def __init__(self, payload):
        self.payload, self.requests = payload, []

    def SubmitQuestionMarkAgentJob(self, request):
        self.requests.append(request)
        return _FakeResponse(self.payload)


class _FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def to_json_string(self):
        return json.dumps(self.payload)


def test_provider_binds_verified_field_names_onto_the_real_sdk_request():
    client = _FakeClient({'JobId': 'remote-1', 'QuestionCount': '2', 'RequestId': 'r1'})
    settings = Settings(marking_mode='tencent', tencent_secret_id='id', tencent_secret_key='key',
                        tencent_region='ap-guangzhou')
    provider = TencentMarkingProvider(settings, client=client)
    result = provider.submit(png_bytes(), png_bytes())
    assert result['JobId'] == 'remote-1'
    request = client.requests[0]
    image, _ = prepare_image(png_bytes())
    assert request.ImageBase64 == base64.b64encode(image).decode('ascii')
    assert request.AssistMarkType == 2 and len(request.ImageBase64List) == 1
    assert request.ImageUrl is None and request.PdfPageNumber is None
    # Deprecated SDK knobs must not be set by us. Reading them warns by design.
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', DeprecationWarning)
        assert request.BoolSingleQuestion is None and request.EnableDeepThink is None


def test_actionable_vendor_codes_get_a_specific_message():
    # Observed in a real call on 2026-09-19: an account with valid credentials but
    # without the service activated returns FailedOperation.UnOpenError. The generic
    # text is not actionable, so this code maps to explicit console instructions.
    assert '开通' in provider_message('FailedOperation.UnOpenError')
    assert 'SecretKey' in provider_message('AuthFailure.SignatureFailure')
    # Unknown codes keep the generic wording: vendor text is never echoed through.
    assert provider_message('SomeUnknownVendorCode') == '腾讯云请求未完成，请根据错误码和 RequestId 排查'
    assert provider_message('X', 'fallback') == 'fallback'


def test_prepare_image_rejects_pdf_and_unbounded_payload():
    pdf = io.BytesIO()
    Image.new('RGB', (20, 20), 'white').save(pdf, 'PDF')
    with pytest.raises(ValueError, match='PDF'):
        prepare_image(pdf.getvalue())
    with pytest.raises(ValueError):
        prepare_image(b'not an image at all')


# --------------------------------------------------------------------------
# 2. Nested result mapping
# --------------------------------------------------------------------------

def test_nested_mapping_keeps_subject_type_coords_and_undetermined_answers():
    result = normalize_result(DONE_RAW)
    question = result['questions'][0]
    assert question['subject'] == '数学' and question['questionType'] == '计算题'
    assert question['imagePolygons'] == [[3, 4, 30, 4, 30, 40, 3, 40]]  # malformed entry dropped
    assert question['rightAnswer'] == 'x^2/2 + C'
    assert question['children'][0]['questionId'] == '1.1'
    wrong, undetermined = question['answers']
    assert wrong['correct'] is False and wrong['knowledgePoints'] == ['不定积分']
    # A missing IsCorrect is undetermined, never counted as wrong.
    assert undetermined['correct'] is None and undetermined['analysis'] == ''
    assert result['angle'] == -1.5
    assert result['totalScore'] is None and result['maxScore'] is None
    assert result['scoreStatus'] == 'unavailable'
    assert result['coordinateAlignmentVerified'] is False
    assert all(a['score'] is None for a in question['answers'])


def test_mapping_rejects_incomplete_payloads():
    with pytest.raises(ValueError):
        normalize_result({'JobStatus': 'DONE', 'MarkInfos': []})
    with pytest.raises(ValueError):
        normalize_result({'JobStatus': 'RUN', 'MarkInfos': []})
    with pytest.raises(ValueError):
        normalize_result({'JobStatus': 'DONE', 'Angle': float('inf'),
                          'MarkInfos': DONE_RAW['MarkInfos']})


# --------------------------------------------------------------------------
# 3. HTTP pathway: status flow, persistence, isolation
# --------------------------------------------------------------------------

def marking_client(tmp_path, **kwargs):
    kwargs.setdefault('marking_mode', 'fixture')
    kwargs.setdefault('marking_submit_interval', 0.01)
    kwargs.setdefault('marking_poll_interval', 0.01)
    return client_for(tmp_path, **kwargs)


def submit_page(c, auth, exam, file_id, key, page=0):
    return c.post('/api/v1/marking/jobs', headers=auth, json={
        'examId': exam['examId'], 'fileId': file_id, 'requestKey': key, 'pageIndex': page})


def test_status_flow_reaches_done_and_survives_restart(tmp_path, monkeypatch):
    monkeypatch.setenv('MARKING_FIXTURE_STAGES', '2')
    with marking_client(tmp_path) as c:
        auth, exam, file = setup_exam(c)
        created = submit_page(c, auth, exam, file['fileId'], 'page-1')
        assert created.status_code == 202, created.text
        job = created.json()['data']
        assert job['status'] == 'queued' and job['pageIndex'] == 0
        assert job['source'] == 'tencent' and job['providerJobId'].startswith('fixture-job-')
        assert job['requestId'].startswith('fixture-submit-')
        states = []
        for _ in range(6):
            data = c.get('/api/v1/marking/jobs/' + job['jobId'], headers=auth).json()['data']
            states.append(data['status'])
            if data['status'] == 'succeeded':
                break
        assert 'running' in states and states[-1] == 'succeeded'
        assert data['queryRequestId'].startswith('fixture-query-')
        # Submit RequestId is preserved, not overwritten by the query one.
        assert data['requestId'] == job['requestId']
        assert data['result']['totalScore'] is None
        assert data['raw']['JobStatus'] == 'DONE'
    # A fresh process over the same data dir still recovers the pages.
    with marking_client(tmp_path) as c:
        login = c.post('/api/v1/auth/login', json={'username': 'student_one',
                                                   'password': 'Test-password-12345'},
                       headers={'X-Requested-With': 'FinalBoost', 'Origin': 'http://127.0.0.1:5173'})
        auth = bearer(login.json()['data'])
        listed = c.get('/api/v1/marking/jobs', params={'examId': exam['examId']}, headers=auth)
        assert listed.status_code == 200, listed.text
        items = listed.json()['data']['items']
        assert [i['jobId'] for i in items] == [job['jobId']]
        assert items[0]['status'] == 'succeeded'
        assert c.get('/api/v1/marking/jobs/' + job['jobId'] + '/image', headers=auth).status_code == 200


def test_pages_keep_their_order_and_each_gets_its_own_job(tmp_path, monkeypatch):
    monkeypatch.setenv('MARKING_FIXTURE_STAGES', '0')
    with marking_client(tmp_path) as c:
        auth, exam, first = setup_exam(c)
        second = upload(c, auth).json()['data']
        third = upload(c, auth).json()['data']
        ids = []
        for page, fid in enumerate([first['fileId'], second['fileId'], third['fileId']]):
            response = submit_page(c, auth, exam, fid, f'page-{page}', page=page)
            assert response.status_code == 202, response.text
            ids.append(response.json()['data']['jobId'])
        items = c.get('/api/v1/marking/jobs', params={'examId': exam['examId']},
                      headers=auth).json()['data']['items']
        assert [i['pageIndex'] for i in items] == [0, 1, 2]
        assert [i['jobId'] for i in items] == ids
        assert len({i['providerJobId'] for i in items}) == 3


def test_rate_limit_blocks_before_any_chargeable_call(tmp_path, monkeypatch):
    monkeypatch.setenv('MARKING_FIXTURE_STAGES', '0')
    with marking_client(tmp_path, marking_submit_interval=60) as c:
        auth, exam, first = setup_exam(c)
        second = upload(c, auth).json()['data']
        assert submit_page(c, auth, exam, first['fileId'], 'a').status_code == 202
        blocked = submit_page(c, auth, exam, second['fileId'], 'b')
        assert blocked.status_code == 429, blocked.text
        # The rejection happened before insertion, so retrying the same intent is clean.
        assert c.get('/api/v1/marking/jobs', params={'examId': exam['examId']},
                     headers=auth).json()['data']['items'].__len__() == 1


def test_repeat_request_key_is_idempotent_and_not_recharged(tmp_path, monkeypatch):
    monkeypatch.setenv('MARKING_FIXTURE_STAGES', '0')
    with marking_client(tmp_path) as c:
        auth, exam, file = setup_exam(c)
        provider = c.app.state.marking_provider
        calls = []
        original = provider.submit
        provider.submit = lambda image, reference=None: (calls.append(1), original(image, reference))[1]
        body = {'examId': exam['examId'], 'fileId': file['fileId'], 'requestKey': 'same', 'pageIndex': 0}
        first = c.post('/api/v1/marking/jobs', headers=auth, json=body).json()['data']
        again = c.post('/api/v1/marking/jobs', headers=auth, json=body).json()['data']
        assert first['jobId'] == again['jobId'] and len(calls) == 1
        conflict = c.post('/api/v1/marking/jobs', headers=auth,
                          json={**body, 'pageIndex': 2})
        assert conflict.status_code == 409


def test_unknown_submission_is_never_retried(tmp_path, monkeypatch):
    monkeypatch.setenv('MARKING_FIXTURE_SCENARIO', 'submit_timeout')
    with marking_client(tmp_path) as c:
        auth, exam, file = setup_exam(c)
        provider = c.app.state.marking_provider
        calls = []
        original = provider.submit
        provider.submit = lambda image, reference=None: (calls.append(1), original(image, reference))[1]
        body = {'examId': exam['examId'], 'fileId': file['fileId'], 'requestKey': 'unknown', 'pageIndex': 0}
        first = c.post('/api/v1/marking/jobs', headers=auth, json=body).json()['data']
        # The vendor may or may not have accepted the job, so it stays unresolved.
        assert first['status'] == 'submission_unknown'
        assert first['error']['code'] == 'ClientNetworkError'
        assert first['providerJobId'] is None and first['result'] is None
        repeated = c.post('/api/v1/marking/jobs', headers=auth, json=body).json()['data']
        assert repeated['jobId'] == first['jobId']
        # Querying a job with no remote id must not attempt a vendor call either.
        assert c.get('/api/v1/marking/jobs/' + first['jobId'], headers=auth).json()['data']['status'] == 'submission_unknown'
        assert len(calls) == 1


def test_provider_failure_is_terminal_and_yields_no_score(tmp_path, monkeypatch):
    monkeypatch.setenv('MARKING_FIXTURE_SCENARIO', 'provider_error')
    with marking_client(tmp_path) as c:
        auth, exam, file = setup_exam(c)
        job = submit_page(c, auth, exam, file['fileId'], 'fails').json()['data']
        data = c.get('/api/v1/marking/jobs/' + job['jobId'], headers=auth).json()['data']
        assert data['status'] == 'failed'
        assert data['error']['code'] == 'FailedOperation.ImageNotSupported'
        assert data['result'] is None          # never a placeholder score
        assert data['error'].get('score') is None


def test_empty_provider_result_fails_rather_than_scoring_zero(tmp_path, monkeypatch):
    monkeypatch.setenv('MARKING_FIXTURE_SCENARIO', 'empty_result')
    monkeypatch.setenv('MARKING_FIXTURE_STAGES', '0')
    with marking_client(tmp_path) as c:
        auth, exam, file = setup_exam(c)
        job = submit_page(c, auth, exam, file['fileId'], 'empty').json()['data']
        data = c.get('/api/v1/marking/jobs/' + job['jobId'], headers=auth).json()['data']
        assert data['status'] == 'failed' and data['error']['code'] == 'InvalidProviderResult'
        assert data['result'] is None


def test_recovery_after_a_vendor_failure(tmp_path, monkeypatch):
    """Force a failure, then recover, without restarting the server."""
    control = tmp_path / 'fixture-control.json'
    monkeypatch.setenv('MARKING_FIXTURE_CONTROL', str(control))
    monkeypatch.setenv('MARKING_FIXTURE_STAGES', '0')
    with marking_client(tmp_path) as c:
        auth, exam, file = setup_exam(c)
        control.write_text(json.dumps({'scenario': 'provider_error'}), encoding='utf-8')
        failed = submit_page(c, auth, exam, file['fileId'], 'recover').json()['data']
        after_failure = c.get('/api/v1/marking/jobs/' + failed['jobId'], headers=auth).json()['data']
        assert after_failure['status'] == 'failed' and after_failure['result'] is None
        control.write_text(json.dumps({'scenario': 'success'}), encoding='utf-8')
        good_file = upload(c, auth).json()['data']
        recovered = submit_page(c, auth, exam, good_file['fileId'], 'recover-2').json()['data']
        after_recovery = c.get('/api/v1/marking/jobs/' + recovered['jobId'], headers=auth).json()['data']
        assert after_recovery['status'] == 'succeeded'
        assert after_recovery['result']['questions'][0]['answers'][0]['correct'] is False
        # The earlier failure is still a failure; nothing was rewritten.
        still = c.get('/api/v1/marking/jobs/' + failed['jobId'], headers=auth).json()['data']
        assert still['status'] == 'failed' and still['result'] is None


def test_exams_and_jobs_are_isolated_between_accounts(tmp_path, monkeypatch):
    monkeypatch.setenv('MARKING_FIXTURE_STAGES', '0')
    with marking_client(tmp_path) as c:
        auth, exam, file = setup_exam(c)
        job = submit_page(c, auth, exam, file['fileId'], 'isolated').json()['data']
        other = bearer(register(c, 'other_user'))
        assert submit_page(c, other, exam, file['fileId'], 'x').status_code == 403
        assert c.get('/api/v1/marking/jobs/' + job['jobId'], headers=other).status_code == 403
        assert c.get('/api/v1/marking/jobs/' + job['jobId'] + '/image', headers=other).status_code == 403
        assert c.get('/api/v1/marking/jobs', params={'examId': exam['examId']}, headers=other).status_code == 403
        assert c.get('/api/v1/marking/jobs', params={'examId': exam['examId']}).status_code == 401


# --------------------------------------------------------------------------
# 4. Missing credentials
# --------------------------------------------------------------------------

def test_missing_credentials_are_reported_and_never_scored(tmp_path, monkeypatch):
    for name in ('TENCENTCLOUD_SECRET_ID', 'TENCENTCLOUD_SECRET_KEY'):
        monkeypatch.delenv(name, raising=False)
    with client_for(tmp_path, marking_mode='tencent') as c:
        auth, exam, file = setup_exam(c)
        readiness = c.get('/api/v1/marking/readiness', headers=auth)
        assert readiness.status_code == 200, readiness.text
        state = readiness.json()['data']
        assert state['ready'] is False and state['mode'] == 'tencent'
        assert state['reason'] == 'NotConfigured' and '尚未配置' in state['message']
        # The secret never appears anywhere in the readiness payload.
        assert 'secret' not in readiness.text.lower().replace('tencentcloud_secret', '')
        health = c.get('/api/v1/health').json()['data']
        assert health['markingConfigured'] is False and health['markingMode'] == 'tencent'
        blocked = submit_page(c, auth, exam, file['fileId'], 'no-key')
        assert blocked.status_code == 503, blocked.text
        assert '尚未配置' in blocked.json()['message']
        # Nothing was persisted and no score was fabricated.
        assert c.get('/api/v1/marking/jobs', params={'examId': exam['examId']},
                     headers=auth).json()['data']['items'] == []


def test_disabled_mode_reports_disabled_and_rejects_submission(tmp_path):
    # Explicit, so a developer's .env (which may set MARKING_MODE=tencent) cannot
    # change what this test asserts.
    with client_for(tmp_path, marking_mode='disabled') as c:
        auth, exam, file = setup_exam(c)
        state = c.get('/api/v1/marking/readiness', headers=auth).json()['data']
        assert state['ready'] is False and state['mode'] == 'disabled'
        assert submit_page(c, auth, exam, file['fileId'], 'off').status_code == 503


def test_readiness_never_echoes_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv('TENCENTCLOUD_SECRET_ID', 'AKID-super-secret')
    monkeypatch.setenv('TENCENTCLOUD_SECRET_KEY', 'key-super-secret')
    with marking_client(tmp_path, marking_mode='tencent') as c:
        auth, _, _ = setup_exam(c)
        text = c.get('/api/v1/marking/readiness', headers=auth).text
        assert 'super-secret' not in text
        assert c.get('/api/v1/health').text.find('super-secret') == -1


def test_fixture_provider_is_ready_without_credentials(monkeypatch):
    monkeypatch.delenv('TENCENTCLOUD_SECRET_ID', raising=False)
    settings = Settings(marking_mode='fixture', data_dir='.')
    provider = FixtureMarkingProvider(settings)
    assert provider.readiness()['configured'] is True
    assert provider.readiness()['mode'] == 'fixture'

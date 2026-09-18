import base64
import io
import pytest
from PIL import Image
from test_auth import client_for, register, bearer
from test_business import setup_exam
from app.marking.models import normalize_result

RESULT = {'JobStatus':'DONE','Angle':0,'MarkInfos':[{'MarkItemTitle':'积分题','MarkInfos':[{'MarkItemTitle':'第一问','AnswerInfos':[{'HandwriteInfo':'x','IsCorrect':False,'AnswerAnalysis':'漏掉常数','HandwriteInfoPositions':[1,2,20,2,20,30,1,30],'KnowledgePoints':['积分'],'RightAnswer':'x+C'}]}]}]}

class Provider:
    calls = 0
    def submit(self, image, reference=None):
        self.calls += 1
        return {'JobId':'remote-job','RequestId':'submit-request'}
    def describe(self, job_id):
        return {**RESULT,'RequestId':'query-request'}

def test_nested_result_retains_evidence_without_scores():
    result = normalize_result(RESULT)
    answer=result['questions'][0]['children'][0]['answers'][0]
    assert answer['correct'] is False
    assert answer['polygon']==[1,2,20,2,20,30,1,30]
    assert result['totalScore'] is None and result['maxScore'] is None
    assert answer['score'] is None
    with pytest.raises(ValueError): normalize_result({'JobStatus':'DONE','MarkInfos':[]})

def test_marking_auth_ownership_dedup_and_persistence(tmp_path):
    provider=Provider()
    with client_for(tmp_path) as c:
        c.app.state.marking_provider=provider
        auth,exam,file=setup_exam(c)
        body={'examId':exam['examId'],'fileId':file['fileId'],'requestKey':'same-intent'}
        assert c.post('/api/v1/marking/jobs',json=body).status_code==401
        accepted=c.post('/api/v1/marking/jobs',json=body,headers=auth)
        assert accepted.status_code==202,accepted.text
        job=accepted.json()['data']
        repeated=c.post('/api/v1/marking/jobs',json=body,headers=auth).json()['data']
        assert repeated['jobId']==job['jobId'] and provider.calls==1
        other=bearer(register(c,'other_user'))
        assert c.post('/api/v1/marking/jobs',json={**body,'requestKey':'other'},headers=other).status_code==403
        assert c.get('/api/v1/marking/jobs/'+job['jobId'],headers=other).status_code==403
        done=c.get('/api/v1/marking/jobs/'+job['jobId'],headers=auth)
        assert done.status_code==200,done.text
        data=done.json()['data']
        assert data['status']=='succeeded'
        assert data['source']=='tencent' and data['result']['totalScore'] is None
        assert data['image']['width']==20
    with client_for(tmp_path) as c:
        c.app.state.marking_provider=provider
        assert c.get('/api/v1/marking/jobs/'+job['jobId'],headers=auth).json()['data']['status']=='succeeded'

def test_unknown_submission_is_not_retried(tmp_path):
    class TimeoutProvider(Provider):
        def submit(self,*args):
            self.calls+=1
            raise TimeoutError('remote acceptance unknown')
    provider=TimeoutProvider()
    with client_for(tmp_path) as c:
        c.app.state.marking_provider=provider
        auth,exam,file=setup_exam(c)
        body={'examId':exam['examId'],'fileId':file['fileId'],'requestKey':'retry-intent'}
        first=c.post('/api/v1/marking/jobs',json=body,headers=auth).json()['data']
        assert first['status']=='submission_unknown'
        assert c.post('/api/v1/marking/jobs',json=body,headers=auth).json()['data']['jobId']==first['jobId']
        assert provider.calls==1

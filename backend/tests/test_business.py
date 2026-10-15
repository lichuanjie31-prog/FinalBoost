import io
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pytest
from PIL import Image
from test_auth import client_for, register, bearer

def exam_body(**overrides):
    return {"course":"数据结构","examDate":(datetime.now(ZoneInfo("Asia/Shanghai")).date()+timedelta(days=7)).isoformat(),"targetScore":85,**overrides}

def post(c, path, data, auth, key=None):
    return c.post('/api/v1'+path,json=data,headers={**auth,"Idempotency-Key":key or str(uuid.uuid4())})

def image_bytes():
    out=io.BytesIO(); Image.new("RGB",(20,20),"white").save(out,"PNG"); return out.getvalue()

def upload(c, auth, key=None, content=None, name="answer.png"):
    return c.post('/api/v1/files/images',files={"file":(name,image_bytes() if content is None else content,"image/png")},headers={**auth,"Idempotency-Key":key or str(uuid.uuid4())})

def setup_exam(c):
    auth=bearer(register(c))
    r=post(c,"/exams",exam_body(),auth); assert r.status_code==201,r.text
    exam=r.json()["data"]
    f=upload(c,auth); assert f.status_code==201,f.text
    return auth,exam,f.json()["data"]

def wait_job(c,auth,gid):
    deadline=time.monotonic()+4
    while time.monotonic()<deadline:
        r=c.get('/api/v1/grading/'+gid,headers=auth); assert r.status_code==200,r.text
        data=r.json()["data"]
        if data["status"] in ("succeeded","failed"): return data
        time.sleep(.025)
    raise AssertionError("job failed to reach terminal status")

def test_complete_flow_scores_diagnosis_and_idempotency(tmp_path):
    with client_for(tmp_path,job_seconds=.15) as c:
        auth,exam,file=setup_exam(c)
        body={"examId":exam["examId"],"fileIds":[file["fileId"]]}
        key=str(uuid.uuid4())
        first=post(c,"/grading",body,auth,key)
        assert first.status_code==202
        assert post(c,"/grading",body,auth,key).json()==first.json()
        assert post(c,"/grading",{**body,"fileIds":["different"]},auth,key).status_code==409
        gid=first.json()["data"]["gradingId"]
        assert post(c,f'/exams/{exam["examId"]}/diagnosis',{"gradingId":gid},auth).status_code==409
        job=wait_job(c,auth,gid)
        assert job["source"]=="mock" and job["status"]=="succeeded"
        result=job["result"]
        assert result["totalScore"]==63 and result["maxScore"]==100
        assert len(result["questions"])==4
        assert sum(q["score"] for q in result["questions"])==63
        assert sum(q["maxScore"] for q in result["questions"])==100
        path=f'/exams/{exam["examId"]}/diagnosis'
        diag=post(c,path,{"gradingId":gid},auth).json()["data"]
        assert diag["estimatedScore"]==63 and diag["source"]=="mock"
        assert [x["scoreRate"] for x in diag["outline"]]==[100,60,33.3,72]
        assert all(x["mastery"] is None for x in diag["outline"])
        assert post(c,path,{"gradingId":gid},auth).json()["data"]==diag
        assert len(c.get(f'/api/v1/exams/{exam["examId"]}/diagnoses',headers=auth).json()["data"]["items"])==1
        download=c.get(file["url"],headers=auth)
        assert download.content==image_bytes() and download.headers["content-type"]=="image/png"

def test_exam_validation_pagination_and_atomic_creation(tmp_path):
    with client_for(tmp_path) as c:
        auth=bearer(register(c))
        for body in [exam_body(targetScore=101),exam_body(course=" "),exam_body(examDate="2000-01-01"),exam_body(maxScore=0)]:
            assert post(c,"/exams",body,auth).status_code==400
        assert c.post('/api/v1/exams',json=exam_body(),headers=auth).status_code==400
        key=str(uuid.uuid4())
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses=list(pool.map(lambda _:post(c,"/exams",exam_body(),auth,key),range(4)))
        assert all(r.status_code==201 for r in responses)
        assert len({r.json()["data"]["examId"] for r in responses})==1
        assert post(c,"/exams",exam_body(course="math"),auth,key).status_code==409
        post(c,"/exams",exam_body(course="math"),auth)
        page=c.get('/api/v1/exams?limit=1',headers=auth).json()["data"]
        assert len(page["items"])==1 and page["nextCursor"]
        following=c.get('/api/v1/exams',params={"cursor":page["nextCursor"],"limit":1},headers=auth).json()["data"]
        assert len(following["items"])==1 and following["nextCursor"] is None
        assert page["items"][0]["examId"]!=following["items"][0]["examId"]
        assert c.get('/api/v1/exams?limit=101',headers=auth).status_code==400

def test_cross_account_resources_and_foreign_inputs(tmp_path):
    with client_for(tmp_path,job_seconds=.05) as c:
        owner,exam,file=setup_exam(c)
        gid=post(c,"/grading",{"examId":exam["examId"],"fileIds":[file["fileId"]]},owner).json()["data"]["gradingId"]
        wait_job(c,owner,gid)
        other=bearer(register(c,"student_two"))
        paths=[f'/exams/{exam["examId"]}',file["url"].replace('/api/v1',''),f'/grading/{gid}',f'/exams/{exam["examId"]}/gradings',f'/exams/{exam["examId"]}/diagnoses']
        for path in paths:
            assert c.get('/api/v1'+path,headers=other).status_code==403
            assert c.get('/api/v1'+path).status_code==401
        assert c.get('/api/v1/exams',headers=other).json()["data"]["items"]==[]
        assert post(c,f'/exams/{exam["examId"]}/diagnosis',{"gradingId":gid},other).status_code==403
        mine=post(c,"/exams",exam_body(),other).json()["data"]["examId"]
        assert post(c,"/grading",{"examId":mine,"fileIds":[file["fileId"]]},other).status_code==403
        assert post(c,f'/exams/{mine}/diagnosis',{"gradingId":gid},other).status_code==403
        second=post(c,"/exams",exam_body(),owner).json()["data"]["examId"]
        assert post(c,f'/exams/{second}/diagnosis',{"gradingId":gid},owner).status_code==400

def test_upload_validation_and_idempotency(tmp_path):
    with client_for(tmp_path) as c:
        auth=bearer(register(c)); key=str(uuid.uuid4())
        first=upload(c,auth,key)
        assert first.status_code==201
        assert upload(c,auth,key).json()==first.json()
        assert upload(c,auth,key,name="other.png").status_code==409
        assert upload(c,auth,content=b"not an image").status_code==415
        import base64
        broken_png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aZ1cAAAAASUVORK5CYII=')
        assert upload(c,auth,content=broken_png).status_code==415
        assert upload(c,auth,content=b"x"*(10*1024*1024+1)).status_code==413
        assert c.post('/api/v1/files/images',files={"file":("a.png",image_bytes(),"image/png")}).status_code==401

@pytest.mark.parametrize('scenario,code', [('unreadable',42201),('provider_error',50201),('timeout',50401)])
def test_failures_reach_terminal_and_retry_creates_new_job(tmp_path,scenario,code):
    # Provider errors must be observed before their deadline; otherwise a busy
    # CI scheduler tests the timeout path instead. Keep that path explicit.
    timeout = .1 if scenario == 'timeout' else 2
    with client_for(tmp_path,mock_scenario=scenario,job_seconds=.04,job_timeout=timeout) as c:
        auth,exam,file=setup_exam(c)
        body={"examId":exam["examId"],"fileIds":[file["fileId"]]}
        gid=post(c,"/grading",body,auth).json()["data"]["gradingId"]
        result=wait_job(c,auth,gid)
        assert result["status"]=="failed" and result["error"]["code"]==code and result["result"] is None
        assert post(c,f'/exams/{exam["examId"]}/diagnosis',{"gradingId":gid},auth).status_code==409
        again=post(c,"/grading",body,auth).json()["data"]["gradingId"]
        assert again!=gid

def test_restart_recovers_pending_job_without_polling_side_effects(tmp_path):
    with client_for(tmp_path,job_seconds=.7) as c:
        auth,exam,file=setup_exam(c)
        gid=post(c,"/grading",{"examId":exam["examId"],"fileIds":[file["fileId"]]},auth).json()["data"]["gradingId"]
    time.sleep(.8)
    with client_for(tmp_path,job_seconds=.7) as c:
        time.sleep(.3)
        import sqlite3
        with sqlite3.connect(tmp_path/'finalboost.sqlite3') as db:
            assert db.execute('SELECT status FROM grading_jobs WHERE id=?',(gid,)).fetchone()[0]=='succeeded'
        assert c.get('/api/v1/exams/'+exam['examId'],headers=auth).status_code==200
        assert c.get(file['url'],headers=auth).content==image_bytes()
        assert wait_job(c,auth,gid)['status']=='succeeded'

def test_score_scaling_and_unsupported_references(tmp_path):
    with client_for(tmp_path,job_seconds=.05) as c:
        auth=bearer(register(c))
        exam=post(c,"/exams",exam_body(maxScore=150,targetScore=120),auth).json()["data"]
        file=upload(c,auth).json()["data"]
        body={"examId":exam["examId"],"fileIds":[file["fileId"]]}
        assert post(c,"/grading",{**body,"paperId":"unknown"},auth).status_code==422
        assert post(c,"/grading",{**body,"fileIds":[]},auth).status_code==400
        gid=post(c,"/grading",body,auth).json()["data"]["gradingId"]
        wait_job(c,auth,gid)
        assert post(c,f'/exams/{exam["examId"]}/diagnosis',{"gradingId":gid},auth).json()["data"]["estimatedScore"]==94.5

def test_production_refuses_mock_and_missing_configuration(tmp_path):
    with pytest.raises(RuntimeError):
        with client_for(tmp_path,environment='production'): pass
    from fastapi.testclient import TestClient
    from app.main import create_app
    with pytest.raises(RuntimeError):
        with TestClient(create_app(data_dir=tmp_path,grading_mode='disabled')): pass

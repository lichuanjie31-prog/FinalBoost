import hashlib
import io
import json
import time
import warnings
from datetime import datetime, date
from zoneinfo import ZoneInfo
from pathlib import PurePath
from fastapi import APIRouter, Depends, Request, UploadFile, Query
from fastapi.responses import FileResponse
from PIL import Image, UnidentifiedImageError
from .auth import current_user
from .common import envelope, fail, new_id
from .idempotency import execute
from .schemas import Envelope, Page, ExamIn, ExamOut, FileOut, GradingIn, GradingAccepted, GradingOut, DiagnosisIn, DiagnosisOut

router=APIRouter(prefix="/api/v1",tags=["study"])
def today(): return datetime.now(ZoneInfo("Asia/Shanghai")).date()

def owned(db,table,rid,user_id):
    # table names come only from internal callers.
    row=db.execute(f"SELECT * FROM {table} WHERE id=?",(rid,)).fetchone()
    if row is None: fail(404,"记录不存在")
    if row["user_id"] != user_id: fail(403,"无权访问这条记录")
    return row

def exam_out(row):
    return {"examId":row["id"],"course":row["course"],"examDate":row["exam_date"],"remainingDays":max(0,(date.fromisoformat(row["exam_date"])-today()).days),"targetScore":row["target_score"],"maxScore":row["max_score"],"stage":row["stage"]}

def grading_out(row):
    return {"gradingId":row["id"],"examId":row["exam_id"],"status":row["status"],"result":json.loads(row["result_json"]) if row["result_json"] else None,"error":json.loads(row["error_json"]) if row["error_json"] else None,"source":row["source"]}

def page_result(rows,limit,convert):
    return {"items":[convert(row) for row in rows[:limit]],"nextCursor":rows[limit-1]["id"] if len(rows)>limit else None}

@router.post("/exams",response_model=Envelope[ExamOut],status_code=201)
def create_exam(body:ExamIn,request:Request,user=Depends(current_user)):
    with request.app.state.db.transaction() as db:
        def create():
            if body.examDate<today(): fail(400,"考试日期不能早于今天")
            rid=new_id()
            db.execute("INSERT INTO exams(id,user_id,course,exam_date,target_score,max_score,created_at) VALUES (?,?,?,?,?,?,?)",(rid,user["id"],body.course,body.examDate.isoformat(),body.targetScore,body.maxScore,time.time()))
            return exam_out(owned(db,"exams",rid,user["id"]))
        return execute(db,user["id"],request,body.model_dump(mode="json"),201,create)

@router.get("/exams",response_model=Envelope[Page[ExamOut]])
def list_exams(request:Request,cursor:str|None=None,limit:int=Query(20,ge=1,le=100),user=Depends(current_user)):
    with request.app.state.db.transaction() as db:
        rows=db.execute("SELECT * FROM exams WHERE user_id=? AND id>? ORDER BY id LIMIT ?",(user["id"],cursor or "",limit+1)).fetchall()
    return envelope(page_result(rows,limit,exam_out))

@router.get("/exams/{exam_id}",response_model=Envelope[ExamOut])
def get_exam(exam_id:str,request:Request,user=Depends(current_user)):
    with request.app.state.db.transaction() as db: return envelope(exam_out(owned(db,"exams",exam_id,user["id"])))

@router.post("/files/images",response_model=Envelope[FileOut],status_code=201)
def upload_image(request:Request,file:UploadFile,user=Depends(current_user)):
    content=file.file.read(10*1024*1024+1)
    if len(content)>10*1024*1024: fail(413,"图片不能超过 10 MiB")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error",Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as img:
                fmt=img.format
                if fmt not in {"JPEG","PNG","WEBP"}: fail(415,"仅支持 JPEG、PNG 和 WebP 图片")
                img.verify()
    except (UnidentifiedImageError,OSError,ValueError,SyntaxError,Image.DecompressionBombWarning,Image.DecompressionBombError): fail(415,"文件不是有效的 JPEG、PNG 或 WebP 图片")
    mime={"JPEG":"image/jpeg","PNG":"image/png","WEBP":"image/webp"}[fmt]
    name=PurePath((file.filename or "image").replace('\\','/')).name[:200]
    payload={"name":name,"digest":hashlib.sha256(content).hexdigest(),"mime":mime}
    written=None
    try:
        with request.app.state.db.transaction() as db:
            def create():
                nonlocal written
                rid=new_id()
                written=request.app.state.db.data_dir / "uploads" / rid
                written.write_bytes(content)
                db.execute("INSERT INTO files VALUES (?,?,?,?,?,?,?)",(rid,user["id"],rid,name,mime,len(content),time.time()))
                return {"fileId":rid,"fileName":name,"mimeType":mime,"size":len(content),"url":f"/api/v1/files/{rid}"}
            result=execute(db,user["id"],request,payload,201,create)
        return result
    except BaseException:
        if written and written.exists(): written.unlink()
        raise

@router.get("/files/{file_id}",response_class=FileResponse)
def download(file_id:str,request:Request,user=Depends(current_user)):
    with request.app.state.db.transaction() as db: row=owned(db,"files",file_id,user["id"])
    path=request.app.state.db.data_dir / "uploads" / row["storage_key"]
    if not path.is_file(): fail(404,"文件暂时不可用")
    return FileResponse(path,media_type=row["mime_type"],headers={"Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff"})

@router.post("/grading",response_model=Envelope[GradingAccepted],status_code=202)
def create_grading(body:GradingIn,request:Request,user=Depends(current_user)):
    settings=request.app.state.settings
    with request.app.state.db.transaction() as db:
        def create():
            owned(db,"exams",body.examId,user["id"])
            if body.paperId is not None or body.mockExamId is not None: fail(422,"首版尚未接入题库与最终模拟，请直接上传图片")
            for fid in body.fileIds: owned(db,"files",fid,user["id"])
            rid=new_id(); now=time.time()
            db.execute("INSERT INTO grading_jobs(id,user_id,exam_id,status,scenario,created_at,ready_at,deadline_at,source) VALUES (?,?,?,'queued',?,?,?,?,?)",(rid,user["id"],body.examId,settings.mock_scenario if settings.grading_mode == "mock" else "success",now,now+settings.job_seconds,now+settings.job_timeout,"mock" if settings.grading_mode == "mock" else "provider"))
            db.executemany("INSERT INTO grading_files VALUES (?,?,?)",[(rid,fid,i) for i,fid in enumerate(body.fileIds)])
            return {"gradingId":rid,"status":"queued"}
        response=execute(db,user["id"],request,body.model_dump(),202,create)
    request.app.state.worker.wake.set()
    return response

@router.get("/grading/{grading_id}",response_model=Envelope[GradingOut])
def get_grading(grading_id:str,request:Request,user=Depends(current_user)):
    with request.app.state.db.transaction() as db: return envelope(grading_out(owned(db,"grading_jobs",grading_id,user["id"])))

@router.get("/exams/{exam_id}/gradings",response_model=Envelope[Page[GradingOut]])
def list_gradings(exam_id:str,request:Request,cursor:str|None=None,limit:int=Query(20,ge=1,le=100),user=Depends(current_user)):
    with request.app.state.db.transaction() as db:
        owned(db,"exams",exam_id,user["id"])
        rows=db.execute("SELECT * FROM grading_jobs WHERE exam_id=? AND user_id=? AND id>? ORDER BY id LIMIT ?",(exam_id,user["id"],cursor or "",limit+1)).fetchall()
    return envelope(page_result(rows,limit,grading_out))

@router.post("/exams/{exam_id}/diagnosis",response_model=Envelope[DiagnosisOut])
def create_diagnosis(exam_id:str,body:DiagnosisIn,request:Request,user=Depends(current_user)):
    with request.app.state.db.transaction() as db:
        def create():
            exam=owned(db,"exams",exam_id,user["id"])
            job=owned(db,"grading_jobs",body.gradingId,user["id"])
            if job["exam_id"] != exam_id: fail(400,"判卷记录不属于当前考试")
            if job["status"] != "succeeded": fail(409,"判卷尚未成功，暂时无法生成诊断")
            existing=db.execute("SELECT data_json FROM diagnoses WHERE grading_id=?",(body.gradingId,)).fetchone()
            if existing: return json.loads(existing["data_json"])
            result=json.loads(job["result_json"])
            if result["totalScore"] is None or any(q["score"] is None for q in result["questions"]): fail(422,"存在未评分题目，暂时无法生成诊断")
            outline=[{"knowledgePointId":q["knowledgePointIds"][0],"knowledgePoint":q["knowledgePoints"][0],"mastery":None,"scoreRate":round(q["score"]/q["maxScore"]*100,1)} for q in result["questions"]]
            rid=new_id()
            data={"diagnosisId":rid,"estimatedScore":round(result["totalScore"]/result["maxScore"]*exam["max_score"],1),"outline":outline,"weakPoints":[{"knowledgePointId":p["knowledgePointId"],"name":p["knowledgePoint"]} for p in outline if p["scoreRate"]<80],"source":job["source"]}
            db.execute("INSERT INTO diagnoses VALUES (?,?,?,?,?,?)",(rid,user["id"],exam_id,body.gradingId,json.dumps(data,ensure_ascii=False),time.time()))
            return data
        return execute(db,user["id"],request,body.model_dump(),200,create)

@router.get("/exams/{exam_id}/diagnoses",response_model=Envelope[Page[DiagnosisOut]])
def list_diagnoses(exam_id:str,request:Request,cursor:str|None=None,limit:int=Query(20,ge=1,le=100),user=Depends(current_user)):
    with request.app.state.db.transaction() as db:
        owned(db,"exams",exam_id,user["id"])
        rows=db.execute("SELECT * FROM diagnoses WHERE exam_id=? AND user_id=? AND id>? ORDER BY id LIMIT ?",(exam_id,user["id"],cursor or "",limit+1)).fetchall()
    return envelope(page_result(rows,limit,lambda r:json.loads(r["data_json"])))

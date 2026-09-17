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
from .schemas import Envelope, Page, ExamIn, ExamOut, FileOut, GradingIn, GradingAccepted, GradingOut, DiagnosisIn, DiagnosisOut, MockExamOut, MockExamSubmitIn, MockQuestionPublic, MockHistoryItem
from . import mock_bank

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


def mock_exam_out(row, include_grading_id=False):
    """把 mock_exams 表的 row 转成对外的 MockExamOut（不含标准答案）。"""
    questions_internal = json.loads(row["questions_json"])
    answers = json.loads(row["answers_json"])
    answered_map = {a["questionId"]: a["answer"] for a in answers}
    # 暴露给前端的题目：剥离 correctAnswer；如果学生已作答，把 answer 一起带回去
    public_questions = []
    for q in questions_internal:
        pq = MockQuestionPublic(
            questionId=q["questionId"],
            prompt=q["prompt"],
            options=q.get("options"),
            maxScore=q["maxScore"],
            knowledgePointIds=q["knowledgePointIds"],
            knowledgePoints=q["knowledgePoints"],
        ).model_dump()
        # 学生已作答的，附加 studentAnswer 字段（不影响 schema，仅前端展示用）
        if q["questionId"] in answered_map:
            pq["studentAnswer"] = answered_map[q["questionId"]]
        public_questions.append(pq)
    max_score = sum(q["maxScore"] for q in questions_internal)
    out = {
        "mockExamId": row["id"],
        "examId": row["exam_id"],
        "status": row["status"],
        "questions": public_questions,
        "maxScore": max_score,
        "createdAt": row["created_at"],
        "submittedAt": row["submitted_at"],
        "gradedAt": row["graded_at"],
    }
    if include_grading_id:
        out["gradingId"] = row.get("grading_id")
    return out

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
            if body.paperId is not None: fail(422,"首版尚未接入题库抽题，请直接上传图片")
            # mockExamId：必须存在、属于当前用户、属于当前考试、且状态=submitted
            if body.mockExamId is not None:
                mock_row = owned(db, "mock_exams", body.mockExamId, user["id"])
                if mock_row["exam_id"] != body.examId: fail(400, "最终模拟记录不属于当前考试")
                if mock_row["status"] != "submitted": fail(409, "请先作答并提交最终模拟")
            else:
                for fid in body.fileIds: owned(db,"files",fid,user["id"])
            rid=new_id(); now=time.time()
            if body.mockExamId is not None:
                # mock 判卷：题目结构已知，无需等图片，1 秒后就 ready
                ready_delay = 1.0
                db.execute("INSERT INTO grading_jobs(id,user_id,exam_id,mock_exam_id,status,scenario,created_at,ready_at,deadline_at) VALUES (?,?,?,?,'queued',?,?,?,?)",(rid,user["id"],body.examId,body.mockExamId,"success",now,now+ready_delay,now+settings.job_timeout))
            else:
                db.execute("INSERT INTO grading_jobs(id,user_id,exam_id,status,scenario,created_at,ready_at,deadline_at) VALUES (?,?,?,'queued',?,?,?,?)",(rid,user["id"],body.examId,settings.mock_scenario,now,now+settings.job_seconds,now+settings.job_timeout))
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


# ─────────────────────────────────────────────────────────────────────────
# 最终模拟（mock exam）端点 —— 对应 API 文档 v1.0 第 15 节
# 状态机：ready → submitted → graded
# ─────────────────────────────────────────────────────────────────────────

@router.post("/exams/{exam_id}/mock",response_model=Envelope[MockExamOut],status_code=201)
def create_mock_exam(exam_id:str,request:Request,user=Depends(current_user),force:bool=False):
    """创建/获取最终模拟卷。

    - 已有 ready/submitted 的卷 → 直接返回它（幂等，继续作答）
    - 已有 graded 的卷且 force=False → 返回最近一份已判卷的（查看成绩场景）
    - force=True → 无视已有卷，强制开一套新卷（"再来一套"）
    """
    with request.app.state.db.transaction() as db:
        def create():
            owned(db,"exams",exam_id,user["id"])
            existing = db.execute(
                "SELECT * FROM mock_exams WHERE exam_id=? AND user_id=? ORDER BY created_at DESC LIMIT 1",
                (exam_id, user["id"]),
            ).fetchone()
            if existing and (existing["status"] in ("ready","submitted") or not force):
                # 已判卷的旧卷要带上 gradingId，前端靠它拉判卷结果
                g = db.execute(
                    "SELECT id FROM grading_jobs WHERE mock_exam_id=? AND user_id=? ORDER BY created_at DESC LIMIT 1",
                    (existing["id"], user["id"]),
                ).fetchone()
                out_row = dict(existing)
                out_row["grading_id"] = g["id"] if g else None
                return mock_exam_out(out_row, include_grading_id=True)
            # 抽题
            questions = mock_bank.pick_for_exam(exam_id)
            if not questions:
                fail(422, "题库暂无可用题目，无法生成最终模拟卷")
            rid = new_id()
            db.execute(
                "INSERT INTO mock_exams(id,user_id,exam_id,status,questions_json,answers_json,source,created_at) VALUES (?,?,?,?,?,?,?,?)",
                (rid, user["id"], exam_id, "ready",
                 json.dumps([q.model_dump() for q in questions], ensure_ascii=False),
                 "[]", "mock", time.time()),
            )
            row = owned(db, "mock_exams", rid, user["id"])
            return mock_exam_out(row)
        return execute(db, user["id"], request, {"examId": exam_id}, 201, create)


@router.get("/exams/{exam_id}/mock/{mock_exam_id}",response_model=Envelope[MockExamOut])
def get_mock_exam(exam_id:str,mock_exam_id:str,request:Request,user=Depends(current_user)):
    """查询最终模拟卷（含题目和学生作答，但不含标准答案）。

    如果已判卷，还会把关联的 grading_id 一起返回，方便前端跳转判卷详情。
    """
    with request.app.state.db.transaction() as db:
        owned(db,"exams",exam_id,user["id"])
        row = owned(db,"mock_exams",mock_exam_id,user["id"])
        if row["exam_id"] != exam_id: fail(400, "最终模拟记录不属于当前考试")
        # 如果 graded，回填 grading_id 方便前端跳转
        grading = db.execute(
            "SELECT id FROM grading_jobs WHERE mock_exam_id=? AND user_id=? ORDER BY created_at DESC LIMIT 1",
            (mock_exam_id, user["id"]),
        ).fetchone()
        out_row = dict(row)
        out_row["grading_id"] = grading["id"] if grading else None
        return envelope(mock_exam_out(out_row, include_grading_id=True))


@router.post("/exams/{exam_id}/mock/{mock_exam_id}/submit",response_model=Envelope[MockExamOut])
def submit_mock_exam(exam_id:str,mock_exam_id:str,body:MockExamSubmitIn,request:Request,user=Depends(current_user)):
    """学生提交最终模拟作答。

    校验：
    - 考试归属正确
    - 模拟卷存在、归属正确、状态=ready（不能重复提交）
    - 所有作答 questionId 必须在这套卷子里
    提交后状态变为 submitted，前端可以接着调 POST /grading 触发判卷。
    """
    now = time.time()
    with request.app.state.db.transaction() as db:
        def create():
            owned(db,"exams",exam_id,user["id"])
            row = owned(db,"mock_exams",mock_exam_id,user["id"])
            if row["exam_id"] != exam_id: fail(400, "最终模拟记录不属于当前考试")
            if row["status"] != "ready": fail(409, "这份最终模拟已经提交过了，请勿重复作答")
            questions = json.loads(row["questions_json"])
            valid_ids = {q["questionId"] for q in questions}
            answers_payload = [a.model_dump(mode="json") for a in body.answers]
            for a in answers_payload:
                if a["questionId"] not in valid_ids:
                    fail(400, f"题目 {a['questionId']} 不属于这份最终模拟")
            db.execute(
                "UPDATE mock_exams SET status='submitted', answers_json=?, submitted_at=? WHERE id=?",
                (json.dumps(answers_payload, ensure_ascii=False), now, mock_exam_id),
            )
            row = owned(db,"mock_exams",mock_exam_id,user["id"])
            return mock_exam_out(row)
        return execute(db, user["id"], request, body.model_dump(mode="json"), 200, create)


@router.get("/exams/{exam_id}/mock-history",response_model=Envelope[list[MockHistoryItem]])
def list_mock_history(exam_id:str,request:Request,user=Depends(current_user)):
    """本场考试的全部最终模拟记录（判卷历史），按创建时间倒序。

    已判卷的记录附带最近一次成功判卷的 totalScore 与 gradingId（用于加载逐题详情）。
    """
    with request.app.state.db.transaction() as db:
        owned(db,"exams",exam_id,user["id"])
        rows=db.execute(
            "SELECT m.id, m.status, m.questions_json, m.created_at, m.submitted_at, m.graded_at,"
            " (SELECT g.id FROM grading_jobs g WHERE g.mock_exam_id=m.id AND g.status='succeeded'"
            "  ORDER BY g.created_at DESC LIMIT 1) AS grading_id,"
            " (SELECT g.result_json FROM grading_jobs g WHERE g.mock_exam_id=m.id AND g.status='succeeded'"
            "  ORDER BY g.created_at DESC LIMIT 1) AS result_json"
            " FROM mock_exams m WHERE m.user_id=? AND m.exam_id=? ORDER BY m.created_at DESC, m.id DESC",
            (user["id"],exam_id),
        ).fetchall()
        items=[]
        for r in rows:
            questions=json.loads(r["questions_json"])
            total=None
            if r["result_json"]:
                try: total=json.loads(r["result_json"]).get("totalScore")
                except (ValueError, TypeError): total=None
            items.append(MockHistoryItem(
                mockExamId=r["id"],status=r["status"],totalScore=total,
                maxScore=sum(q["maxScore"] for q in questions),
                createdAt=r["created_at"],submittedAt=r["submitted_at"],gradedAt=r["graded_at"],
                gradingId=r["grading_id"],
            ).model_dump())
        return envelope(items)

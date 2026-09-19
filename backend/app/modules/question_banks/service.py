import os
import shutil
import sqlite3
import time
from pathlib import Path

from fastapi import Request, UploadFile

from ...common import envelope, fail, new_id
from ...idempotency import execute
from . import repository as repo
from .xlsx_validator import XLSX_MIME, stage_upload


PRIVATE_LIMIT = 100


def _text(value: str, field: str, maximum: int) -> str:
    result = " ".join(value.split())
    if not result or len(result) > maximum:
        fail(400, f"{field}不符合要求")
    return result


def _like(value: str) -> str:
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def list_subjects(request: Request, user, q, cursor, limit):
    cursor_values = repo.decode_cursor(cursor, 2)
    params = [] if user["role"] == "admin" else [user["id"]]
    where = ["scope='system'"] if user["role"] == "admin" else ["(scope='system' OR (scope='private' AND owner_user_id=?))"]
    if q:
        _, normalized = repo.normalized_name(q)
        where.append("normalized_name LIKE ? ESCAPE '\\'")
        params.append(_like(normalized))
    if cursor_values:
        where.append("(normalized_name>? OR (normalized_name=? AND id>?))")
        params.extend([cursor_values[0], cursor_values[0], cursor_values[1]])
    sql = "SELECT * FROM subjects WHERE " + " AND ".join(where) + " ORDER BY normalized_name,id LIMIT ?"
    params.append(limit + 1)
    with request.app.state.db.transaction() as db:
        rows = db.execute(sql, params).fetchall()
    return envelope(repo.page(rows, limit, repo.subject_out, ("normalized_name", "id")))


def create_subject(request: Request, user, name, scope):
    if scope == "private" and user["role"] == "admin":
        fail(403, "管理员请使用系统标准科目")
    display, normalized = repo.normalized_name(name)
    if not display:
        fail(400, "科目名称不能为空")
    payload = {"name": display}
    with request.app.state.db.transaction() as db:
        def operation():
            system = db.execute("SELECT * FROM subjects WHERE scope='system' AND normalized_name=?", (normalized,)).fetchone()
            if system:
                return repo.subject_out(system)
            if scope == "private":
                existing = db.execute("SELECT * FROM subjects WHERE scope='private' AND owner_user_id=? AND normalized_name=?", (user["id"], normalized)).fetchone()
                if existing:
                    return repo.subject_out(existing)
            subject_id = new_id()
            db.execute(
                "INSERT INTO subjects(id,name,normalized_name,scope,owner_user_id,created_at) VALUES (?,?,?,?,?,?)",
                (subject_id, display, normalized, scope, None if scope == "system" else user["id"], time.time()),
            )
            return repo.subject_out(repo.get_subject(db, subject_id))
        try:
            return execute(db, user["id"], request, payload, 201, operation)
        except sqlite3.IntegrityError:
            fail(409, "同名科目已存在")


def _allowed_subject(db, subject_id, user, visibility):
    subject = repo.get_subject(db, subject_id)
    if subject is None:
        fail(404, "科目不存在")
    if visibility == "public":
        if user["role"] != "admin":
            fail(403, "学生不能上传公共试卷")
        if subject["scope"] != "system":
            fail(400, "公共试卷只能使用系统标准科目")
    elif subject["scope"] == "private" and subject["owner_user_id"] != user["id"]:
        fail(403, "无权使用这个私人科目")
    return subject


def upload_paper(request: Request, user, upload: UploadFile, subject_id, name, college, year, semester, visibility):
    if visibility == "public" and user["role"] != "admin":
        fail(403, "学生不能上传公共试卷")
    name = _text(name, "试卷名称", 200)
    college = _text(college, "学院", 100)
    semester = _text(semester, "学期", 30)
    temporary_dir = request.app.state.db.data_dir / "uploads" / ".tmp"
    staged = stage_upload(upload, temporary_dir)
    payload = {
        "fileName": staged.display_name, "fileSha256": staged.sha256,
        "subjectId": subject_id, "name": name, "college": college,
        "year": year, "semester": semester, "visibility": visibility,
    }
    final_path = None
    try:
        with request.app.state.db.transaction() as db:
            def operation():
                nonlocal final_path
                _allowed_subject(db, subject_id, user, visibility)
                if visibility == "private" and repo.private_count(db, user["id"]) >= PRIVATE_LIMIT:
                    fail(409, "私人题库最多保存 100 份试卷", 40913)
                file_id, paper_id = new_id(), new_id()
                final_path = request.app.state.db.data_dir / "uploads" / file_id
                os.replace(staged.path, final_path)
                now = time.time()
                db.execute(
                    "INSERT INTO files(id,user_id,storage_key,original_name,mime_type,size,created_at,sha256,purpose) VALUES (?,?,?,?,?,?,?,?,?)",
                    (file_id, user["id"], file_id, staged.display_name, XLSX_MIME, staged.size, now, staged.sha256, "question_bank"),
                )
                db.execute(
                    """INSERT INTO papers(id,owner_user_id,subject_id,name,college,year,semester,visibility,
                       publication_status,file_id,source_public_paper_id,created_at,published_at,updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (paper_id, user["id"], subject_id, name, college, year, semester, visibility,
                     "draft" if visibility == "public" else None, file_id, None, now, None, now),
                )
                return repo.paper_out(repo.get_paper(db, paper_id), download=visibility == "private")
            return execute(db, user["id"], request, payload, 201, operation)
    except BaseException:
        if final_path is not None:
            final_path.unlink(missing_ok=True)
        raise
    finally:
        staged.path.unlink(missing_ok=True)


def _paper_filters(subject_id=None, q=None, year=None, semester=None, status=None):
    clauses, params = [], []
    if subject_id:
        clauses.append("p.subject_id=?"); params.append(subject_id)
    if q:
        clauses.append("p.name LIKE ? ESCAPE '\\'"); params.append(_like(" ".join(q.split())))
    if year is not None:
        clauses.append("p.year=?"); params.append(year)
    if semester:
        clauses.append("p.semester=?"); params.append(" ".join(semester.split()))
    if status:
        clauses.append("p.publication_status=?"); params.append(status)
    return clauses, params


def list_private_papers(request, user, subject_id, q, year, semester, cursor, limit):
    clauses, params = _paper_filters(subject_id, q, year, semester)
    clauses[:0] = ["p.owner_user_id=?", "p.visibility='private'"]
    params[:0] = [user["id"]]
    cursor_values = repo.decode_cursor(cursor, 2)
    if cursor_values:
        clauses.append("(p.created_at<? OR (p.created_at=? AND p.id<?))")
        params.extend([cursor_values[0], cursor_values[0], cursor_values[1]])
    sql = repo.PAPER_SELECT + " WHERE " + " AND ".join(clauses) + " ORDER BY p.created_at DESC,p.id DESC LIMIT ?"
    params.append(limit + 1)
    with request.app.state.db.transaction() as db:
        rows = db.execute(sql, params).fetchall()
    return envelope(repo.page(rows, limit, lambda row: repo.paper_out(row), ("created_at", "id")))


def private_paper(request, user, paper_id):
    with request.app.state.db.transaction() as db:
        row = repo.get_paper(db, paper_id)
        if row is None:
            fail(404, "试卷不存在")
        if row["visibility"] != "private" or row["owner_user_id"] != user["id"]:
            fail(403, "无权访问这份试卷")
        return envelope(repo.paper_out(row, download=True))


def downloadable_private(request, user, paper_id):
    with request.app.state.db.transaction() as db:
        row = repo.get_paper(db, paper_id)
        if row is None:
            fail(404, "试卷不存在")
        if row["visibility"] != "private" or row["owner_user_id"] != user["id"]:
            fail(403, "无权下载这份试卷")
    return _download_path(request, row)


def _download_path(request, row):
    path = request.app.state.db.data_dir / "uploads" / row["storage_key"]
    if not path.is_file():
        fail(404, "文件暂时不可用")
    return path, row["original_name"]


def list_admin_papers(request, user, status, subject_id, q, year, semester, cursor, limit):
    clauses, params = _paper_filters(subject_id, q, year, semester, status)
    clauses[:0] = ["p.owner_user_id=?", "p.visibility='public'"]
    params[:0] = [user["id"]]
    cursor_values = repo.decode_cursor(cursor, 2)
    if cursor_values:
        clauses.append("(p.created_at<? OR (p.created_at=? AND p.id<?))")
        params.extend([cursor_values[0], cursor_values[0], cursor_values[1]])
    sql = repo.PAPER_SELECT + " WHERE " + " AND ".join(clauses) + " ORDER BY p.created_at DESC,p.id DESC LIMIT ?"
    params.append(limit + 1)
    with request.app.state.db.transaction() as db:
        rows = db.execute(sql, params).fetchall()
    return envelope(repo.page(rows, limit, repo.paper_out, ("created_at", "id")))


def admin_paper(request, user, paper_id):
    with request.app.state.db.transaction() as db:
        row = _owned_public(db, paper_id, user["id"])
        return envelope(repo.paper_out(row))


def downloadable_admin(request, user, paper_id):
    with request.app.state.db.transaction() as db:
        row = _owned_public(db, paper_id, user["id"])
    return _download_path(request, row)


def _owned_public(db, paper_id, owner_id):
    row = repo.get_paper(db, paper_id)
    if row is None:
        fail(404, "试卷不存在")
    if row["visibility"] != "public" or row["owner_user_id"] != owner_id:
        fail(403, "无权管理这份公共试卷")
    return row


def change_publication(request, user, paper_id, target):
    payload = {}
    with request.app.state.db.transaction() as db:
        def operation():
            row = _owned_public(db, paper_id, user["id"])
            current = row["publication_status"]
            if target == "published":
                _download_path(request, row)
            if current == target:
                return repo.paper_out(row)
            if target == "published":
                if current not in {"draft", "unpublished"}:
                    fail(409, "当前状态不允许发布", 40911)
                now = time.time()
                db.execute("UPDATE papers SET publication_status='published',published_at=?,updated_at=? WHERE id=?", (now, now, paper_id))
            else:
                if current != "published":
                    fail(409, "当前状态不允许下架", 40912)
                db.execute("UPDATE papers SET publication_status='unpublished',updated_at=? WHERE id=?", (time.time(), paper_id))
            return repo.paper_out(repo.get_paper(db, paper_id))
        return execute(db, user["id"], request, payload, 200, operation)


def list_public_papers(request, user, subject_id, college, year, semester, q, cursor, limit):
    clauses, params = _paper_filters(subject_id, q, year, semester)
    clauses[:0] = ["p.visibility='public'", "p.publication_status='published'"]
    if college:
        clauses.append("p.college=?"); params.append(" ".join(college.split()))
    cursor_values = repo.decode_cursor(cursor, 2)
    if cursor_values:
        clauses.append("(p.published_at<? OR (p.published_at=? AND p.id<?))")
        params.extend([cursor_values[0], cursor_values[0], cursor_values[1]])
    sql = """
    SELECT p.*, s.name AS subject_name, s.scope AS subject_scope,
           copied.id AS private_paper_id
    FROM papers p
    JOIN subjects s ON s.id=p.subject_id
    LEFT JOIN papers copied ON copied.owner_user_id=? AND copied.source_public_paper_id=p.id
    WHERE """ + " AND ".join(clauses) + " ORDER BY p.published_at DESC,p.id DESC LIMIT ?"
    params.insert(0, user["id"])
    params.append(limit + 1)
    with request.app.state.db.transaction() as db:
        rows = db.execute(sql, params).fetchall()
    return envelope(repo.page(rows, limit, repo.public_paper_out, ("published_at", "id")))


def copy_public_paper(request, user, paper_id):
    payload = {}
    final_path = None
    temporary_path = None
    try:
        with request.app.state.db.transaction() as db:
            def operation():
                nonlocal final_path, temporary_path
                source = repo.get_paper(db, paper_id)
                if source is None or source["visibility"] != "public":
                    fail(404, "公共试卷不存在")
                existing = db.execute("SELECT id FROM papers WHERE owner_user_id=? AND source_public_paper_id=?", (user["id"], paper_id)).fetchone()
                if existing:
                    return repo.paper_out(repo.get_paper(db, existing["id"]), download=True)
                if source["publication_status"] != "published":
                    fail(409, "公共试卷当前不可复制")
                if repo.private_count(db, user["id"]) >= PRIVATE_LIMIT:
                    fail(409, "私人题库最多保存 100 份试卷", 40913)
                source_path, _ = _download_path(request, source)
                file_id, private_id = new_id(), new_id()
                temporary_dir = request.app.state.db.data_dir / "uploads" / ".tmp"
                temporary_dir.mkdir(parents=True, exist_ok=True)
                temporary_path = temporary_dir / os.urandom(16).hex()
                shutil.copyfile(source_path, temporary_path)
                final_path = request.app.state.db.data_dir / "uploads" / file_id
                os.replace(temporary_path, final_path)
                now = time.time()
                db.execute(
                    "INSERT INTO files(id,user_id,storage_key,original_name,mime_type,size,created_at,sha256,purpose) VALUES (?,?,?,?,?,?,?,?,?)",
                    (file_id, user["id"], file_id, source["original_name"], XLSX_MIME, source["file_size"], now, source["sha256"], "question_bank"),
                )
                db.execute(
                    """INSERT INTO papers(id,owner_user_id,subject_id,name,college,year,semester,visibility,
                       publication_status,file_id,source_public_paper_id,created_at,published_at,updated_at)
                       VALUES (?,?,?,?,?,?,?,'private',NULL,?,?,?,?,?)""",
                    (private_id, user["id"], source["subject_id"], source["name"], source["college"], source["year"], source["semester"],
                     file_id, paper_id, now, None, now),
                )
                return repo.paper_out(repo.get_paper(db, private_id), download=True)
            return execute(db, user["id"], request, payload, 201, operation)
    except BaseException:
        if final_path is not None:
            final_path.unlink(missing_ok=True)
        raise
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

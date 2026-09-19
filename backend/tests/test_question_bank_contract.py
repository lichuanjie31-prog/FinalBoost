import io
import sqlite3
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor

import pytest

from test_auth import bearer, client_for, register


def key():
    return str(uuid.uuid4())


def xlsx_bytes(*, unsafe_part=None, external=False, bomb=False):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        def write(name, data):
            entry = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, data)

        write("[Content_Types].xml", "<Types></Types>")
        relationship = '<Relationships><Relationship TargetMode="External"/></Relationships>' if external else "<Relationships/>"
        write("_rels/.rels", relationship)
        write(
            "xl/workbook.xml",
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheets><sheet name="Sheet1" sheetId="1"/></sheets></workbook>',
        )
        write("xl/worksheets/sheet1.xml", "<worksheet/>")
        if unsafe_part:
            write(unsafe_part, b"unsafe")
        if bomb:
            write("xl/sharedStrings.xml", b"0" * (2 * 1024 * 1024))
    return output.getvalue()


def create_subject(client, auth, name="数据结构", system=False, request_key=None):
    path = "/api/v1/subjects/system" if system else "/api/v1/subjects/private"
    return client.post(path, json={"name": name}, headers={**auth, "Idempotency-Key": request_key or key()})


def upload_paper(client, auth, subject_id, *, visibility="private", content=None, filename="paper.xlsx", request_key=None, name="期末试卷"):
    return client.post(
        "/api/v1/papers",
        data={"subjectId": subject_id, "name": name, "college": "计算机学院", "year": "2025", "semester": "第一学期", "visibility": visibility},
        files={"file": (filename, xlsx_bytes() if content is None else content, "application/octet-stream")},
        headers={**auth, "Idempotency-Key": request_key or key()},
    )


def post_empty(client, path, auth, request_key=None):
    return client.post(path, json={}, headers={**auth, "Idempotency-Key": request_key or key()})


def test_question_bank_openapi_and_real_subject_endpoints(tmp_path):
    with client_for(tmp_path, admin_usernames=("ADMIN",)) as client:
        student_data = register(client)
        student = bearer(student_data)
        admin_data = register(client, "admin")
        admin = bearer(admin_data)
        assert student_data["user"]["role"] == "student"
        assert admin_data["user"]["role"] == "admin"
        assert client.get("/api/v1/auth/me", headers=admin).json()["data"]["role"] == "admin"
        assert create_subject(client, student, system=True).status_code == 403
        assert create_subject(client, admin).status_code == 403

        first = create_subject(client, admin, "  数据   结构  ", system=True, request_key="system-subject")
        assert first.status_code == 201
        assert first.json()["data"]["name"] == "数据 结构"
        assert create_subject(client, admin, "  数据   结构  ", system=True, request_key="system-subject").json() == first.json()
        reused = create_subject(client, student, "数据 结构")
        assert reused.status_code == 201
        assert reused.json()["data"]["scope"] == "system"

        subjects = client.get("/api/v1/subjects?q=数据", headers=student).json()["data"]
        assert len(subjects["items"]) == 1
        schema = client.get("/openapi.json").json()
        expected = {
            "/api/v1/subjects", "/api/v1/subjects/private", "/api/v1/subjects/system", "/api/v1/papers",
            "/api/v1/papers/private", "/api/v1/papers/private/{paper_id}", "/api/v1/papers/private/{paper_id}/file",
            "/api/v1/admin/papers", "/api/v1/admin/papers/{paper_id}", "/api/v1/admin/papers/{paper_id}/file",
            "/api/v1/admin/papers/{paper_id}/publish", "/api/v1/admin/papers/{paper_id}/unpublish",
            "/api/v1/public/papers", "/api/v1/public/papers/{paper_id}/copy",
        }
        assert expected <= set(schema["paths"])


def test_private_upload_idempotency_listing_download_and_isolation(tmp_path):
    with client_for(tmp_path) as client:
        owner = bearer(register(client))
        other = bearer(register(client, "student_two"))
        subject_id = create_subject(client, owner).json()["data"]["subjectId"]
        upload_key = key()
        first = upload_paper(client, owner, subject_id, request_key=upload_key)
        assert first.status_code == 201, first.text
        paper = first.json()["data"]
        repeated = upload_paper(client, owner, subject_id, request_key=upload_key)
        assert repeated.json() == first.json()
        conflict = upload_paper(client, owner, subject_id, request_key=upload_key, name="另一份试卷")
        assert conflict.status_code == 409

        listed = client.get("/api/v1/papers/private", headers=owner).json()["data"]["items"]
        assert len(listed) == 1 and "downloadUrl" not in listed[0]
        detail = client.get(f"/api/v1/papers/private/{paper['paperId']}", headers=owner)
        assert detail.status_code == 200 and detail.json()["data"]["downloadUrl"]
        downloaded = client.get(detail.json()["data"]["downloadUrl"], headers=owner)
        assert downloaded.content == xlsx_bytes()
        assert downloaded.headers["cache-control"] == "private, no-store"
        assert client.get(f"/api/v1/papers/private/{paper['paperId']}", headers=other).status_code == 403
        assert client.get(detail.json()["data"]["downloadUrl"], headers=other).status_code == 403

        with sqlite3.connect(tmp_path / "finalboost.sqlite3") as db:
            assert db.execute("SELECT COUNT(*) FROM papers").fetchone()[0] == 1
            assert db.execute("SELECT COUNT(*) FROM files WHERE purpose='question_bank'").fetchone()[0] == 1


def test_xlsx_security_and_capacity_limit(tmp_path, monkeypatch):
    from app.modules.question_banks import service, xlsx_validator

    long_name = "a" * 240 + ".xlsx"
    assert len(xlsx_validator.safe_display_name(long_name)) == 200
    assert xlsx_validator.safe_display_name(long_name).endswith(".xlsx")

    with client_for(tmp_path) as client:
        auth = bearer(register(client))
        subject_id = create_subject(client, auth).json()["data"]["subjectId"]
        assert upload_paper(client, auth, subject_id, filename="paper.xls").status_code == 415
        assert upload_paper(client, auth, subject_id, content=b"not a zip").status_code == 415
        damaged = upload_paper(client, auth, subject_id, content=xlsx_bytes()[:80])
        assert damaged.status_code == 422 and damaged.json()["code"] == 42210
        encrypted_ole = bytes.fromhex("D0CF11E0A1B11AE1") + "EncryptedPackage".encode("utf-16le")
        encrypted = upload_paper(client, auth, subject_id, content=encrypted_ole)
        assert encrypted.status_code == 422 and encrypted.json()["code"] == 42211
        macro = upload_paper(client, auth, subject_id, content=xlsx_bytes(unsafe_part="xl/vbaProject.bin"))
        assert macro.status_code == 422 and macro.json()["code"] == 42212
        assert upload_paper(client, auth, subject_id, content=xlsx_bytes(external=True)).status_code == 422
        assert upload_paper(client, auth, subject_id, content=xlsx_bytes(bomb=True)).status_code == 422
        monkeypatch.setattr(xlsx_validator, "MAX_UPLOAD_BYTES", 100)
        too_large = upload_paper(client, auth, subject_id)
        assert too_large.status_code == 413 and too_large.json()["code"] == 41310
        monkeypatch.setattr(xlsx_validator, "MAX_UPLOAD_BYTES", 20 * 1024 * 1024)

        monkeypatch.setattr(service, "PRIVATE_LIMIT", 1)
        assert upload_paper(client, auth, subject_id).status_code == 201
        full = upload_paper(client, auth, subject_id)
        assert full.status_code == 409 and full.json()["code"] == 40913
        with sqlite3.connect(tmp_path / "finalboost.sqlite3") as db:
            assert db.execute("SELECT COUNT(*) FROM papers").fetchone()[0] == 1


def test_public_lifecycle_safe_response_copy_and_existing_copy_survives(tmp_path):
    with client_for(tmp_path, admin_usernames=("admin",)) as client:
        admin = bearer(register(client, "admin"))
        student = bearer(register(client))
        second = bearer(register(client, "student_two"))
        subject_id = create_subject(client, admin, system=True).json()["data"]["subjectId"]
        draft_response = upload_paper(client, admin, subject_id, visibility="public")
        assert draft_response.status_code == 201, draft_response.text
        draft = draft_response.json()["data"]
        assert draft["publicationStatus"] == "draft"
        assert client.get("/api/v1/public/papers", headers=student).json()["data"]["items"] == []
        assert upload_paper(client, student, subject_id, visibility="public").status_code == 403

        publish_path = f"/api/v1/admin/papers/{draft['paperId']}/publish"
        published = post_empty(client, publish_path, admin)
        assert published.status_code == 200 and published.json()["data"]["publicationStatus"] == "published"
        public_item = client.get("/api/v1/public/papers", headers=student).json()["data"]["items"][0]
        assert not ({"fileId", "downloadUrl", "storageKey"} & public_item.keys())
        assert public_item["copied"] is False

        copy_path = f"/api/v1/public/papers/{draft['paperId']}/copy"
        with ThreadPoolExecutor(max_workers=4) as pool:
            copies = list(pool.map(lambda _: post_empty(client, copy_path, student), range(4)))
        assert all(response.status_code == 201 for response in copies)
        assert len({response.json()["data"]["paperId"] for response in copies}) == 1
        copied = copies[0]
        duplicate = post_empty(client, copy_path, student)
        assert duplicate.status_code == 201
        assert duplicate.json()["data"]["paperId"] == copied.json()["data"]["paperId"]
        assert client.get(copied.json()["data"]["downloadUrl"], headers=student).content == xlsx_bytes()

        unpublish_path = f"/api/v1/admin/papers/{draft['paperId']}/unpublish"
        assert post_empty(client, unpublish_path, admin).status_code == 200
        assert client.get("/api/v1/public/papers", headers=student).json()["data"]["items"] == []
        assert post_empty(client, copy_path, second).status_code == 409
        assert client.get(copied.json()["data"]["downloadUrl"], headers=student).status_code == 200
        republished = post_empty(client, publish_path, admin)
        assert republished.status_code == 200
        assert client.get("/api/v1/public/papers", headers=second).json()["data"]["items"]
        assert client.get(f"/api/v1/admin/papers/{draft['paperId']}/file", headers=student).status_code == 403


def test_invalid_cursor_and_missing_auth(tmp_path):
    with client_for(tmp_path) as client:
        auth = bearer(register(client))
        assert client.get("/api/v1/subjects?cursor=broken", headers=auth).status_code == 400
        assert client.get("/api/v1/public/papers").status_code == 401


def test_failed_file_move_rolls_back_database_and_cleans_staging(tmp_path, monkeypatch):
    from app.modules.question_banks import service

    with client_for(tmp_path) as client:
        auth = bearer(register(client))
        subject_id = create_subject(client, auth).json()["data"]["subjectId"]

        def fail_move(source, target):
            raise OSError("simulated storage failure")

        monkeypatch.setattr(service.os, "replace", fail_move)
        with pytest.raises(OSError, match="simulated storage failure"):
            upload_paper(client, auth, subject_id)
        with sqlite3.connect(tmp_path / "finalboost.sqlite3") as db:
            assert db.execute("SELECT COUNT(*) FROM papers").fetchone()[0] == 0
            assert db.execute("SELECT COUNT(*) FROM files WHERE purpose='question_bank'").fetchone()[0] == 0
        temporary = tmp_path / "uploads" / ".tmp"
        assert not temporary.exists() or list(temporary.iterdir()) == []

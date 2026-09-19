import base64
import json
from datetime import datetime, timezone

from ...common import fail


PAPER_SELECT = """
SELECT p.*, f.original_name, f.size AS file_size, f.storage_key, f.mime_type,
       f.sha256, s.name AS subject_name, s.scope AS subject_scope,
       s.owner_user_id AS subject_owner_user_id
FROM papers p
JOIN files f ON f.id=p.file_id
JOIN subjects s ON s.id=p.subject_id
"""


def normalized_name(value: str) -> tuple[str, str]:
    display = " ".join(value.split())
    return display, display.casefold()


def timestamp(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat() if value is not None else None


def subject_out(row):
    return {"subjectId": row["id"], "name": row["name"], "scope": row["scope"]}


def paper_out(row, *, download=False):
    result = {
        "paperId": row["id"],
        "subject": {"subjectId": row["subject_id"], "name": row["subject_name"], "scope": row["subject_scope"]},
        "name": row["name"], "college": row["college"], "year": row["year"],
        "semester": row["semester"], "visibility": row["visibility"],
        "publicationStatus": row["publication_status"], "fileId": row["file_id"],
        "fileName": row["original_name"], "fileSize": row["file_size"],
        "sourcePublicPaperId": row["source_public_paper_id"],
        "createdAt": timestamp(row["created_at"]), "publishedAt": timestamp(row["published_at"]),
    }
    if download:
        result["downloadUrl"] = f"/api/v1/papers/private/{row['id']}/file"
    return result


def public_paper_out(row):
    return {
        "paperId": row["id"],
        "subject": {"subjectId": row["subject_id"], "name": row["subject_name"], "scope": row["subject_scope"]},
        "name": row["name"], "college": row["college"], "year": row["year"],
        "semester": row["semester"], "publishedAt": timestamp(row["published_at"]),
        "copied": row["private_paper_id"] is not None,
        "privatePaperId": row["private_paper_id"],
    }


def encode_cursor(*values):
    raw = json.dumps(values, ensure_ascii=False, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor, expected):
    if not cursor:
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        values = json.loads(raw)
        if not isinstance(values, list) or len(values) != expected:
            raise ValueError
        return values
    except (ValueError, TypeError, json.JSONDecodeError):
        fail(400, "分页游标无效")


def page(rows, limit, convert, cursor_fields):
    items = [convert(row) for row in rows[:limit]]
    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = encode_cursor(*(last[field] for field in cursor_fields))
    return {"items": items, "nextCursor": next_cursor}


def get_subject(db, subject_id):
    return db.execute("SELECT * FROM subjects WHERE id=?", (subject_id,)).fetchone()


def get_paper(db, paper_id):
    return db.execute(PAPER_SELECT + " WHERE p.id=?", (paper_id,)).fetchone()


def private_count(db, owner_id):
    return db.execute("SELECT COUNT(*) FROM papers WHERE owner_user_id=? AND visibility='private'", (owner_id,)).fetchone()[0]

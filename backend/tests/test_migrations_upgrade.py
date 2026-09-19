"""迁移记账：空库初始化 + 已有数据库副本升级。

集成带入了 5 个新的迁移文件，其中 3 个与既有文件共用 `002_` 前缀。
`db.migrate()` 是按**完整文件名**排序并记账的（schema_migrations.version = 文件名），
而且 `003_training_answers.sql` 依赖 `002_training.sql` 已经建出 training_questions，
所以前缀顺序是有意义的：重复前缀不能靠改名"整理"，改名会让已有部署重复执行迁移。
"""
import sqlite3
import time
from pathlib import Path

from app.db import Database

MIGRATIONS = Path(__file__).resolve().parents[1] / "app" / "migrations"

# feature/myself-ai（集成前的交付版本）已有的迁移文件，内容未被本次集成改动。
PRE_INTEGRATION = [
    "001_initial.sql",
    "002_marking_jobs.sql",
    "003_agent_tables.sql",
    "004_agent_langchain.sql",
    "005_marking_pages.sql",
    "006_marking_providers.sql",
]
# 本次集成新增的迁移文件（分布来自 master / training / mock-exam）。
INTEGRATION_ADDED = [
    "002_mock_exams.sql",
    "002_question_banks.sql",
    "002_training.sql",
    "003_training_answers.sql",
    "004_training_exports.sql",
]


def all_migration_names():
    return sorted(p.name for p in MIGRATIONS.glob("*.sql"))


def recorded_versions(path: Path) -> set:
    conn = sqlite3.connect(path)
    try:
        return {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
    finally:
        conn.close()


def columns(path: Path, table: str) -> set:
    conn = sqlite3.connect(path)
    try:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


def tables(path: Path) -> set:
    conn = sqlite3.connect(path)
    try:
        return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()


def deploy_old_revision(path: Path):
    """复刻一次旧版本部署：只执行当时的迁移文件，并按文件名记账。"""
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations(version TEXT PRIMARY KEY)")
        for name in PRE_INTEGRATION:
            sql = (MIGRATIONS / name).read_text(encoding="utf-8")
            conn.executescript("BEGIN IMMEDIATE;\n" + sql + f"\nINSERT INTO schema_migrations VALUES ('{name}');\nCOMMIT;")
        conn.commit()
    finally:
        conn.close()


def test_empty_database_applies_every_migration_and_is_idempotent(tmp_path):
    db = Database(tmp_path)
    db.migrate()

    expected = set(all_migration_names())
    assert INTEGRATION_ADDED and set(PRE_INTEGRATION) < expected
    assert expected <= recorded_versions(db.path), "空库应记下全部迁移"

    present = tables(db.path)
    for name in ("mock_exams", "trainings", "training_stages", "training_questions",
                 "training_exports", "attempts", "quizzes", "mastery_evidence",
                 "marking_jobs", "subjects", "papers", "agent_messages"):
        assert name in present, f"缺少表 {name}"

    assert {"sha256", "purpose"} <= columns(db.path, "files")
    assert "mock_exam_id" in columns(db.path, "grading_jobs")
    assert "answer_json" in columns(db.path, "training_questions")

    # 再跑一次：不报错，也不重复记账。
    before = recorded_versions(db.path)
    db.migrate()
    assert recorded_versions(db.path) == before


def test_existing_deployment_upgrades_and_keeps_its_data(tmp_path):
    """已有数据库副本升级：只补跑缺失迁移，旧数据与旧结构不受损。"""
    db = Database(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "uploads").mkdir(exist_ok=True)
    deploy_old_revision(db.path)

    # 旧版本里已经存在的数据：一个用户、一场考试、一份文件、一个判卷任务。
    now = time.time()
    conn = sqlite3.connect(db.path)
    try:
        conn.execute("INSERT INTO users VALUES (?,?,?,?)", ("u1", "student_one", "hash", now))
        conn.execute("INSERT INTO exams VALUES (?,?,?,?,?,?,?,?)",
                     ("e1", "u1", "数据结构", "2026-10-01", 85.0, 100.0, "diagnosis", now))
        conn.execute("INSERT INTO files VALUES (?,?,?,?,?,?,?)",
                     ("f1", "u1", "storage-key-1", "answer.png", "image/png", 1234, now))
        conn.execute(
            "INSERT INTO grading_jobs(id,user_id,exam_id,status,scenario,created_at,ready_at,deadline_at,result_json,source)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("g1", "u1", "e1", "succeeded", "success", now, now, now + 60, '{"totalScore":63,"maxScore":100,"questions":[]}', "mock"),
        )
        conn.commit()
    finally:
        conn.close()

    # 升级前：新迁移还没跑过。
    assert "mock_exams" not in tables(db.path)
    assert "purpose" not in columns(db.path, "files")
    assert "mock_exam_id" not in columns(db.path, "grading_jobs")

    db.migrate()

    # 记账补齐，且旧的迁移不会被重新执行。
    assert set(all_migration_names()) <= recorded_versions(db.path)

    # 新结构到位，且旧列仍在（没有重建表导致列丢失）。
    assert {"sha256", "purpose"} <= columns(db.path, "files")
    assert "mock_exam_id" in columns(db.path, "grading_jobs")
    assert {"mock_exams", "trainings", "training_exports"} <= tables(db.path)

    # 旧数据原样保留；新增的 NOT NULL 列走默认值。
    conn = sqlite3.connect(db.path)
    try:
        file_row = conn.execute("SELECT id,original_name,size,purpose FROM files WHERE id='f1'").fetchone()
        assert file_row[:3] == ("f1", "answer.png", 1234)
        assert file_row[3] == "general", "新增列应对已有行使用默认值"

        job_row = conn.execute("SELECT id,status,result_json,mock_exam_id FROM grading_jobs WHERE id='g1'").fetchone()
        assert job_row[0] == "g1" and job_row[1] == "succeeded"
        assert job_row[2] == '{"totalScore":63,"maxScore":100,"questions":[]}'
        assert job_row[3] is None, "非模拟考试的历史任务不应被回填 mock_exam_id"

        assert conn.execute("SELECT course FROM exams WHERE id='e1'").fetchone()[0] == "数据结构"
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
    finally:
        conn.close()

    # 升级后的库可以直接被应用使用（外键与迁移记录都正常）。
    db2 = Database(tmp_path)
    db2.migrate()
    assert set(all_migration_names()) <= recorded_versions(db2.path)

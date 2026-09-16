import sqlite3
from contextlib import contextmanager
from pathlib import Path

class Database:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.path = self.data_dir / "finalboost.sqlite3"

    @contextmanager
    def transaction(self):
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally: conn.close()

    def migrate(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "uploads").mkdir(exist_ok=True)
        with sqlite3.connect(self.path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations(version TEXT PRIMARY KEY)")
            for path in sorted((Path(__file__).parent / "migrations").glob("*.sql")):
                if not conn.execute("SELECT 1 FROM schema_migrations WHERE version=?", (path.name,)).fetchone():
                    conn.executescript("BEGIN IMMEDIATE;\n" + path.read_text(encoding="utf-8") + "\nINSERT INTO schema_migrations VALUES ('" + path.name + "');\nCOMMIT;")

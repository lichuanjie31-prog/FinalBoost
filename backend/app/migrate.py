from .config import Settings
from .db import Database

if __name__ == "__main__":
    settings = Settings()
    db = Database(settings.data_dir)
    db.migrate()
    with db.transaction() as conn:
        versions = [row[0] for row in conn.execute("SELECT version FROM schema_migrations ORDER BY version")]
    print("Applied migrations: " + ", ".join(versions))

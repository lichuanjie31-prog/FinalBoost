"""MySQL database connection using SQLAlchemy.

Replaces SQLite with MySQL for production use.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from contextlib import contextmanager

Base = declarative_base()


class MySQLDatabase:
    def __init__(self, host: str, port: int, database: str,
                 user: str, password: str):
        url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4"
        self.engine = create_engine(
            url,
            pool_size=10,
            max_overflow=20,
            pool_recycle=3600,
            pool_pre_ping=True,
        )
        self.SessionLocal = sessionmaker(
            bind=self.engine,
            autocommit=False,
            autoflush=False,
        )

    def create_tables(self):
        """Create all tables defined in models."""
        Base.metadata.create_all(bind=self.engine)

    @contextmanager
    def session(self):
        """Provide a transactional session scope."""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def execute_raw(self, sql: str, params: dict = None):
        """Execute raw SQL and return results."""
        with self.engine.connect() as conn:
            result = conn.execute(sql, params or {})
            conn.commit()
            return result

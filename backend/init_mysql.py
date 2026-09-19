"""Initialize MySQL database for FinalBoost.

Creates the database and all required tables.

Usage:
    python init_mysql.py

Make sure MySQL is running and credentials are set in environment or .env file.
"""
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.config import Settings
from app.database import MySQLDatabase


def init_database():
    """Initialize the MySQL database with all tables."""
    settings = Settings()

    print(f"Connecting to MySQL: {settings.mysql_host}:{settings.mysql_port}")
    print(f"Database: {settings.mysql_database}")

    # Connect to MySQL server (without database) to create it if needed
    import pymysql

    # First, create the database if it doesn't exist
    conn = pymysql.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
    )

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{settings.mysql_database}` "
                f"DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            print(f"Database '{settings.mysql_database}' created/verified")
    finally:
        conn.close()

    # Now connect to the database and create tables
    db = MySQLDatabase(
        host=settings.mysql_host,
        port=settings.mysql_port,
        database=settings.mysql_database,
        user=settings.mysql_user,
        password=settings.mysql_password,
    )

    # Read and execute migration files
    migrations_dir = Path(__file__).parent / "app" / "migrations"
    migration_files = sorted(migrations_dir.glob("*.sql"))

    print(f"\nFound {len(migration_files)} migration files")

    for migration_file in migration_files:
        print(f"\nExecuting: {migration_file.name}")
        sql_content = migration_file.read_text(encoding="utf-8")

        # Split by semicolons and execute each statement
        statements = [s.strip() for s in sql_content.split(";") if s.strip()]

        for stmt in statements:
            if stmt.startswith("--") or not stmt:
                continue
            try:
                with db.engine.connect() as conn:
                    conn.execute(stmt)
                    conn.commit()
                print(f"  ✓ Executed statement")
            except Exception as e:
                # Table already exists is OK
                if "already exists" in str(e).lower():
                    print(f"  ⊘ Table already exists, skipping")
                else:
                    print(f"  ✗ Error: {e}")

    print("\n✓ Database initialization complete!")
    print(f"\nConnection string: mysql+pymysql://{settings.mysql_user}:***@{settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}")


if __name__ == "__main__":
    init_database()

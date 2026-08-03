#!/usr/bin/env python3
from __future__ import annotations

import hashlib
from pathlib import Path

from splitter.config import DATABASE_URL, ROOT_DIR

MIGRATIONS_DIR = ROOT_DIR / "migrations"
LOCK_ID = 786_453_912


def _migration_body(path: Path) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    return "\n".join(
        line
        for line in lines
        if line.strip().upper() not in {"BEGIN;", "COMMIT;"}
    )


def main() -> int:
    if not DATABASE_URL:
        raise SystemExit("DATABASE_URL is required")
    try:
        import psycopg
    except ImportError as exc:
        raise SystemExit("psycopg is required") from exc

    migration_paths = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not migration_paths:
        raise SystemExit("No migrations found")

    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                checksum TEXT NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        connection.execute("SELECT pg_advisory_lock(%s)", (LOCK_ID,))
        try:
            applied = {
                row[0]: row[1]
                for row in connection.execute(
                    "SELECT version, checksum FROM schema_migrations"
                ).fetchall()
            }
            for path in migration_paths:
                version = path.name
                body = _migration_body(path)
                checksum = hashlib.sha256(body.encode("utf-8")).hexdigest()
                if version in applied:
                    if applied[version] != checksum:
                        raise RuntimeError(f"migration_checksum_mismatch:{version}")
                    continue
                with connection.transaction():
                    connection.execute(body)
                    connection.execute(
                        "INSERT INTO schema_migrations (version, checksum) VALUES (%s, %s)",
                        (version, checksum),
                    )
                print(f"applied {version}")
        finally:
            connection.execute("SELECT pg_advisory_unlock(%s)", (LOCK_ID,))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

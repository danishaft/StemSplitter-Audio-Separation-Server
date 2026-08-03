#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")
    try:
        import psycopg
    except ImportError as exc:
        raise SystemExit("Install psycopg before running migrations") from exc
    migration = (ROOT / "migrations" / "001_control_plane.sql").read_text(encoding="utf-8")
    with psycopg.connect(database_url) as connection:
        connection.execute(migration)
    print("Applied migrations/001_control_plane.sql")


if __name__ == "__main__":
    main()

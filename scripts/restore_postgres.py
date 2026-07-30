#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from splitter.config import DATABASE_URL, OBJECT_STORAGE_CONFIG
from splitter.infrastructure.object_storage import object_store_from_config


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Restore a PostgreSQL custom dump from private object storage."
    )
    parser.add_argument("--key", required=True)
    parser.add_argument(
        "--confirm-database-host",
        required=True,
        help="Must exactly match the hostname in DATABASE_URL.",
    )
    args = parser.parse_args()

    if not DATABASE_URL:
        raise SystemExit("DATABASE_URL is required")
    database_host = urlparse(DATABASE_URL).hostname or ""
    if args.confirm_database_host != database_host:
        raise SystemExit("database_host_confirmation_mismatch")
    prefix = str(OBJECT_STORAGE_CONFIG["prefix"]).strip("/")
    if not args.key.startswith(f"{prefix}/backups/postgres/"):
        raise SystemExit("backup_key_outside_postgres_prefix")
    store = object_store_from_config()
    if store is None:
        raise SystemExit("S3-compatible object storage is required")

    reference = {
        "provider": "s3",
        "bucket": str(OBJECT_STORAGE_CONFIG["bucket"]),
        "key": args.key,
    }
    with tempfile.TemporaryDirectory(prefix="stemsplitter-restore-") as temp_dir:
        dump_path = Path(temp_dir) / "restore.dump"
        store.download(reference, dump_path)
        subprocess.run(
            [
                "pg_restore",
                "--dbname",
                DATABASE_URL,
                "--clean",
                "--if-exists",
                "--no-owner",
                "--no-privileges",
                "--exit-on-error",
                str(dump_path),
            ],
            check=True,
            env={**os.environ, "PGCONNECT_TIMEOUT": "15"},
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

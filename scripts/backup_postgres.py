#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from splitter.config import DATABASE_URL, OBJECT_STORAGE_CONFIG
from splitter.infrastructure.object_storage import object_store_from_config


def main() -> int:
    if not DATABASE_URL:
        raise SystemExit("DATABASE_URL is required")
    store = object_store_from_config()
    if store is None:
        raise SystemExit("S3-compatible object storage is required")

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    prefix = str(OBJECT_STORAGE_CONFIG["prefix"]).strip("/")
    key = f"{prefix}/backups/postgres/{timestamp}.dump"
    with tempfile.TemporaryDirectory(prefix="stemsplitter-backup-") as temp_dir:
        dump_path = Path(temp_dir) / f"{timestamp}.dump"
        environment = {**os.environ, "PGCONNECT_TIMEOUT": "15"}
        subprocess.run(
            [
                "pg_dump",
                "--dbname",
                DATABASE_URL,
                "--format=custom",
                "--compress=9",
                "--no-owner",
                "--no-privileges",
                "--file",
                str(dump_path),
            ],
            check=True,
            env=environment,
        )
        reference = store.upload(
            dump_path,
            key,
            "application/vnd.postgresql.custom-dump",
        )
    print(json.dumps(reference.as_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

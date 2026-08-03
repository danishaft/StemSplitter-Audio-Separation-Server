from __future__ import annotations

import zipfile
from pathlib import Path

from .util import dump_json, ensure_dir, safe_relpath


def write_manifest(job_root: Path, manifest: dict) -> Path:
    path = job_root / "analysis" / "manifest.json"
    ensure_dir(path.parent)
    dump_json(path, manifest)
    return path


def package_directories(job_root: Path, groups: dict[str, list[Path]]) -> dict[str, str]:
    package_dir = ensure_dir(job_root / "package")
    published: dict[str, str] = {}
    for bundle_name, files in groups.items():
        if not files:
            continue
        zip_path = package_dir / f"{bundle_name}.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for file_path in files:
                if not file_path.exists():
                    continue
                archive.write(file_path, arcname=safe_relpath(file_path, job_root))
        published[bundle_name] = str(zip_path.resolve())
    return published


from __future__ import annotations

from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def job_dirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)

    import splitter.config as config
    import splitter.jobs as jobs
    import audio_api

    monkeypatch.setattr(config, "JOBS_DIR", jobs_dir)
    monkeypatch.setattr(jobs, "JOBS_DIR", jobs_dir)
    monkeypatch.setattr(audio_api, "JOBS_DIR", jobs_dir)
    return jobs_dir

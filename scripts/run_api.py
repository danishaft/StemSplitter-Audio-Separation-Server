from __future__ import annotations

import os

import uvicorn

from splitter.config import APP_ENV, JOB_DISPATCH_BACKEND
from splitter.runtime import validate_runtime_config


def main() -> None:
    validate_runtime_config()
    default_workers = 2 if APP_ENV == "production" else 1
    workers = max(1, int(os.getenv("WEB_CONCURRENCY", str(default_workers))))
    if JOB_DISPATCH_BACKEND == "thread" and workers != 1:
        raise RuntimeError("thread_dispatch_requires_single_api_process")
    uvicorn.run(
        "audio_api:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "5000")),
        workers=workers,
        limit_concurrency=max(1, int(os.getenv("API_MAX_CONCURRENCY", "1000"))),
        timeout_keep_alive=max(1, int(os.getenv("WEB_KEEPALIVE", "5"))),
        timeout_graceful_shutdown=max(
            1,
            int(os.getenv("WEB_GRACEFUL_TIMEOUT", "30")),
        ),
        proxy_headers=True,
        forwarded_allow_ips=os.getenv("FORWARDED_ALLOW_IPS", "127.0.0.1"),
        server_header=False,
        access_log=False,
    )


if __name__ == "__main__":
    main()

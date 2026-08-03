from __future__ import annotations

import tempfile
from pathlib import Path

from starlette.datastructures import UploadFile


class UploadTooLargeError(RuntimeError):
    """Raised after a streamed upload crosses the configured byte limit."""


async def stream_upload_to_temp(
    upload: UploadFile,
    *,
    max_bytes: int,
    chunk_bytes: int = 1024 * 1024,
) -> Path:
    suffix = Path(upload.filename or "input.bin").suffix
    written = 0
    target: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix="stemsplitter-upload-",
            suffix=suffix,
            delete=False,
        ) as handle:
            target = Path(handle.name)
            while chunk := await upload.read(chunk_bytes):
                written += len(chunk)
                if written > max_bytes:
                    raise UploadTooLargeError("request_too_large")
                handle.write(chunk)
        return target
    except Exception:
        if target is not None:
            target.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()

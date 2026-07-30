from __future__ import annotations

from fastapi.responses import JSONResponse


class APIError(RuntimeError):
    def __init__(
        self,
        status_code: int,
        error: str,
        message: str | None = None,
    ) -> None:
        super().__init__(error)
        self.status_code = status_code
        self.error = error
        self.message = message


def error_response(status_code: int, error: str, message: str | None = None) -> JSONResponse:
    payload: dict[str, str] = {"error": error}
    if message is not None:
        payload["message"] = message
    return JSONResponse(payload, status_code=status_code)

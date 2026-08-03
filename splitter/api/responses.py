from __future__ import annotations

from fastapi.responses import JSONResponse

PUBLIC_ERROR_MESSAGES = {
    "direct_upload_required": "Create a private upload grant before submitting a production job.",
    "direct_upload_unavailable": "Configure S3-compatible object storage to use direct uploads.",
    "invalid_filename": "Use an allowed audio filename.",
    "invalid_json": "Request body must be a JSON object.",
    "invalid_object_input": "input.object and an allowed input.filename are required.",
    "invalid_pagination": "limit and offset must be integers.",
    "invalid_source": "JSON jobs currently require source.provider to be audius.",
    "invalid_track_id": "source.track_id is required.",
    "job_capacity_exceeded": "Job capacity is currently full.",
    "owner_job_capacity_exceeded": "Job capacity is currently full.",
    "job_dispatch_failed": "The job was persisted but could not be queued.",
    "job_not_resumable": "Only failed jobs with an existing remote worker can be resumed.",
}


class APIError(RuntimeError):
    def __init__(
        self,
        status_code: int,
        error: str,
    ) -> None:
        super().__init__(error)
        self.status_code = status_code
        self.error = error


def error_response(status_code: int, error: str) -> JSONResponse:
    payload: dict[str, str] = {"error": error}
    if message := PUBLIC_ERROR_MESSAGES.get(error):
        payload["message"] = message
    return JSONResponse(payload, status_code=status_code)

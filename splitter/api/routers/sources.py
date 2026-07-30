from __future__ import annotations

from fastapi import APIRouter, Query

from splitter.sources import AudiusClient, AudiusError

from ..responses import error_response
from ..schemas import AudiusSearchResponse

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get(
    "/audius/search",
    operation_id="searchAudius",
    response_model=AudiusSearchResponse,
)
def search_audius(
    q: str = "",
    limit: str = Query(default="20"),
    offset: str = Query(default="0"),
):
    try:
        parsed_limit = int(limit)
        parsed_offset = int(offset)
        tracks = AudiusClient().search(
            q,
            limit=parsed_limit,
            offset=parsed_offset,
        )
    except ValueError:
        return error_response(
            400,
            "invalid_pagination",
            "limit and offset must be integers.",
        )
    except AudiusError as exc:
        return error_response(exc.status_code, exc.code, str(exc))
    return {
        "provider": "audius",
        "tracks": tracks,
        "limit": max(1, min(parsed_limit, 50)),
        "offset": max(parsed_offset, 0),
    }


@router.get("/audius/tracks/{track_id}", operation_id="getAudiusTrack")
def audius_track(track_id: str):
    try:
        track = AudiusClient().track_details(track_id)
    except AudiusError as exc:
        return error_response(exc.status_code, exc.code, str(exc))
    return {"provider": "audius", "track": track}

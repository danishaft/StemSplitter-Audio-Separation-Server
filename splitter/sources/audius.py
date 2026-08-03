from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

import requests

from ..config import ALLOWED_EXTENSIONS, AUDIUS_CONFIG
from ..util import sanitize_filename


class AudiusError(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int = 502) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True)
class AudiusImport:
    filename: str
    content: bytes
    source: dict[str, object]


def _license_policy(license_name: object, *, allow_noncommercial: bool) -> tuple[bool, str]:
    if not isinstance(license_name, str) or not license_name.strip():
        return False, "license_missing"

    normalized = re.sub(r"[_\-]+", " ", license_name.upper())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if "ALL RIGHTS RESERVED" in normalized:
        return False, "all_rights_reserved"
    if "NO DERIV" in normalized or re.search(r"\bND\b", normalized):
        return False, "derivatives_not_allowed"
    if "CC0" in normalized or "PUBLIC DOMAIN" in normalized:
        return True, "license_allows_commercial_derivatives"
    if not re.search(r"\bCC BY(?:\b| )", normalized):
        return False, "license_not_supported"
    if "NONCOMMERCIAL" in normalized or re.search(r"\bNC\b", normalized):
        if allow_noncommercial:
            return True, "license_allows_noncommercial_derivatives"
        return False, "commercial_use_not_allowed"
    return True, "license_allows_commercial_derivatives"


class AudiusClient:
    def __init__(
        self,
        *,
        config: dict[str, object] | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.config = dict(AUDIUS_CONFIG if config is None else config)
        self.base_url = str(self.config["base_url"]).rstrip("/")
        self.session = session or requests.Session()

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "User-Agent": "StemSplitter/1.0"}
        api_key = self.config.get("api_key")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def _request_json(self, path: str, *, params: dict[str, object] | None = None) -> object:
        try:
            response = self.session.get(
                f"{self.base_url}{path}",
                params=params,
                headers=self._headers(),
                timeout=int(self.config.get("timeout", 30)),
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise AudiusError("audius_request_failed", f"Audius request failed: {exc}") from exc
        except ValueError as exc:
            raise AudiusError("audius_invalid_response", "Audius returned invalid JSON.") from exc
        if not isinstance(payload, dict) or "data" not in payload:
            raise AudiusError("audius_invalid_response", "Audius response has no data field.")
        return payload["data"]

    @staticmethod
    def _validate_track_id(track_id: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", track_id):
            raise AudiusError("invalid_track_id", "Invalid Audius track ID.", status_code=400)
        return track_id

    def evaluate_track(self, track: dict[str, object]) -> tuple[bool, str]:
        if not track.get("is_downloadable"):
            return False, "download_not_enabled"
        if track.get("is_download_gated") or track.get("download_conditions"):
            return False, "download_requires_access"
        duration = float(track.get("duration") or 0)
        max_duration = int(self.config.get("max_duration_seconds", 1200))
        if duration <= 0:
            return False, "duration_missing"
        if duration > max_duration:
            return False, "duration_limit_exceeded"
        return _license_policy(
            track.get("license"),
            allow_noncommercial=bool(self.config.get("allow_noncommercial_licenses", False)),
        )

    @staticmethod
    def _artwork_url(track: dict[str, object]) -> str | None:
        artwork = track.get("artwork")
        if isinstance(artwork, dict):
            for size in ("480x480", "150x150", "1000x1000"):
                value = artwork.get(size)
                if isinstance(value, str):
                    return value
        cover_art = track.get("cover_art")
        return cover_art if isinstance(cover_art, str) else None

    def public_track(self, track: dict[str, object]) -> dict[str, object]:
        can_import, import_reason = self.evaluate_track(track)
        user = track.get("user") if isinstance(track.get("user"), dict) else {}
        return {
            "id": str(track.get("id") or ""),
            "title": str(track.get("title") or "Untitled"),
            "artist": str(user.get("name") or user.get("handle") or "Unknown artist"),
            "artist_handle": user.get("handle"),
            "duration_seconds": float(track.get("duration") or 0),
            "genre": track.get("genre"),
            "mood": track.get("mood"),
            "license": track.get("license"),
            "isrc": track.get("isrc"),
            "permalink": track.get("permalink"),
            "artwork_url": self._artwork_url(track),
            "is_downloadable": bool(track.get("is_downloadable")),
            "can_import": can_import,
            "import_reason": import_reason,
        }

    def search(self, query: str, *, limit: int = 20, offset: int = 0) -> list[dict[str, object]]:
        query = query.strip()
        if len(query) < 2 or len(query) > 100:
            raise AudiusError(
                "invalid_search_query",
                "Search query must contain between 2 and 100 characters.",
                status_code=400,
            )
        data = self._request_json(
            "/tracks/search",
            params={
                "query": query,
                "limit": max(1, min(limit, 50)),
                "offset": max(offset, 0),
                "sort_method": "relevant",
                "only_downloadable": "true",
            },
        )
        if not isinstance(data, list):
            raise AudiusError("audius_invalid_response", "Audius search data is not a list.")
        return [self.public_track(track) for track in data if isinstance(track, dict)]

    def get_track(self, track_id: str) -> dict[str, object]:
        track_id = self._validate_track_id(track_id)
        data = self._request_json(f"/tracks/{track_id}")
        if not isinstance(data, dict):
            raise AudiusError("audius_track_not_found", "Audius track was not found.", status_code=404)
        return data

    def track_details(self, track_id: str) -> dict[str, object]:
        return self.public_track(self.get_track(track_id))

    @staticmethod
    def _filename(track: dict[str, object], content_type: str) -> str:
        original = sanitize_filename(str(track.get("orig_filename") or ""))
        if original and Path(original).suffix.lower().lstrip(".") in ALLOWED_EXTENSIONS:
            return original
        extension_by_type = {
            "audio/mpeg": "mp3",
            "audio/mp3": "mp3",
            "audio/wav": "wav",
            "audio/x-wav": "wav",
            "audio/flac": "flac",
            "audio/x-flac": "flac",
            "audio/ogg": "ogg",
            "audio/mp4": "m4a",
            "audio/x-m4a": "m4a",
        }
        extension = extension_by_type.get(content_type.split(";", 1)[0].lower())
        if not extension:
            raise AudiusError(
                "audius_unsupported_audio_format",
                "Audius returned an unsupported audio format.",
                status_code=415,
            )
        title = sanitize_filename(str(track.get("title") or "audius-track")) or "audius-track"
        return f"{title}.{extension}"

    def download(self, track_id: str) -> AudiusImport:
        track_id = self._validate_track_id(track_id)
        track = self.get_track(track_id)
        can_import, reason = self.evaluate_track(track)
        if not can_import:
            raise AudiusError(
                "audius_track_not_importable",
                f"Audius track cannot be imported: {reason}.",
                status_code=403,
            )

        try:
            response = self.session.get(
                f"{self.base_url}/tracks/{track_id}/download",
                headers={**self._headers(), "Accept": "audio/*"},
                timeout=int(self.config.get("timeout", 30)),
                stream=True,
                allow_redirects=True,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise AudiusError("audius_download_failed", f"Audius download failed: {exc}") from exc

        if response.url and not str(response.url).lower().startswith("https://"):
            response.close()
            raise AudiusError("audius_insecure_download", "Audius returned an insecure download URL.")

        max_bytes = int(self.config.get("max_import_bytes", 500 * 1024 * 1024))
        content_length = int(response.headers.get("Content-Length") or 0)
        if content_length > max_bytes:
            response.close()
            raise AudiusError(
                "audius_file_too_large",
                "Audius track exceeds the import size limit.",
                status_code=413,
            )

        content = bytearray()
        try:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                content.extend(chunk)
                if len(content) > max_bytes:
                    raise AudiusError(
                        "audius_file_too_large",
                        "Audius track exceeds the import size limit.",
                        status_code=413,
                    )
        finally:
            response.close()
        if not content:
            raise AudiusError("audius_empty_download", "Audius returned an empty audio file.")

        public = self.public_track(track)
        user = track.get("user") if isinstance(track.get("user"), dict) else {}
        source = {
            "type": "catalog",
            "provider": "audius",
            "track_id": track_id,
            "title": public["title"],
            "artist": public["artist"],
            "artist_handle": user.get("handle"),
            "license": public["license"],
            "license_decision": reason,
            "permalink": public["permalink"],
            "isrc": public["isrc"],
        }
        filename = self._filename(track, response.headers.get("Content-Type", ""))
        return AudiusImport(filename=filename, content=bytes(content), source=source)

from __future__ import annotations

import pytest

from splitter.sources.audius import AudiusClient, AudiusError


def _track(**overrides):
    payload = {
        "id": "track123",
        "title": "Open Song",
        "duration": 180,
        "license": "CC BY 4.0",
        "is_downloadable": True,
        "is_download_gated": False,
        "download_conditions": None,
        "orig_filename": "open-song.wav",
        "permalink": "https://audius.co/artist/open-song",
        "isrc": "US-AAA-26-00001",
        "user": {"name": "Open Artist", "handle": "openartist"},
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    ("license_name", "expected", "reason"),
    [
        ("CC0", True, "license_allows_commercial_derivatives"),
        ("CC BY 4.0", True, "license_allows_commercial_derivatives"),
        ("CC-BY-SA 4.0", True, "license_allows_commercial_derivatives"),
        ("Attribution CC BY", True, "license_allows_commercial_derivatives"),
        ("Attribution-ShareAlike CC BY-SA", True, "license_allows_commercial_derivatives"),
        ("CC BY-NC 4.0", False, "commercial_use_not_allowed"),
        ("Attribution-NonCommercial CC BY-NC", False, "commercial_use_not_allowed"),
        ("CC BY-ND 4.0", False, "derivatives_not_allowed"),
        ("Attribution-NoDerivs CC BY-ND", False, "derivatives_not_allowed"),
        ("All Rights Reserved", False, "all_rights_reserved"),
        (None, False, "license_missing"),
    ],
)
def test_audius_license_gate(license_name, expected, reason) -> None:
    client = AudiusClient(config={
        "base_url": "https://api.audius.test/v1",
        "timeout": 1,
        "max_duration_seconds": 1200,
        "allow_noncommercial_licenses": False,
    })

    assert client.evaluate_track(_track(license=license_name)) == (expected, reason)


class _Response:
    def __init__(self, *, payload=None, content=b"", content_type="application/json") -> None:
        self._payload = payload
        self._content = content
        self.headers = {"Content-Type": content_type, "Content-Length": str(len(content))}
        self.url = "https://creatornode.audius.test/audio"

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload

    def iter_content(self, chunk_size: int):
        yield self._content

    def close(self) -> None:
        return None


class _Session:
    def __init__(self, responses: list[_Response]) -> None:
        self.responses = responses
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


def test_audius_download_returns_audio_and_provenance() -> None:
    session = _Session([
        _Response(payload={"data": _track()}),
        _Response(content=b"RIFF-audio", content_type="audio/wav"),
    ])
    client = AudiusClient(
        config={
            "base_url": "https://api.audius.test/v1",
            "timeout": 1,
            "max_import_bytes": 1024,
            "max_duration_seconds": 1200,
            "allow_noncommercial_licenses": False,
        },
        session=session,
    )

    imported = client.download("track123")

    assert imported.filename == "open-song.wav"
    assert imported.content == b"RIFF-audio"
    assert imported.source["provider"] == "audius"
    assert imported.source["license"] == "CC BY 4.0"
    assert session.calls[1][0].endswith("/tracks/track123/download")


def test_audius_download_rejects_protected_track_before_fetching_audio() -> None:
    session = _Session([_Response(payload={"data": _track(license="All Rights Reserved")})])
    client = AudiusClient(
        config={
            "base_url": "https://api.audius.test/v1",
            "timeout": 1,
            "max_import_bytes": 1024,
            "max_duration_seconds": 1200,
            "allow_noncommercial_licenses": False,
        },
        session=session,
    )

    with pytest.raises(AudiusError) as raised:
        client.download("track123")

    assert raised.value.code == "audius_track_not_importable"
    assert len(session.calls) == 1
